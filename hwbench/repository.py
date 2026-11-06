"""Local repository bridge. Never downloads repositories, images or evaluators."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile

from .common import ROOT, canonical, digest, execute, portable_logs, relative_path, sandbox_available, within, write_json
from .grader import grade_task, new_result
from .reporting import write_report

REVISION = '5b807d945f6a99aa645f7e43a64a2115e281b4bf'
LOCK = ROOT / 'third_party/cvdp/catalog-lock.json'
PROMPT = '.hwbench_prompt.md'


def file_hash(path):
    import hashlib
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def empty_dir(path):
    path = Path(path)
    if path.is_symlink() or (path.exists() and (not path.is_dir() or any(path.iterdir()))):
        raise ValueError('Destination must be an empty real directory')
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def tree_hashes(root, workspace=False):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Expected real directory')
    result = {}
    for p in sorted(root.rglob('*')):
        rel = p.relative_to(root)
        if workspace and rel.parts[0] == '.git':
            continue
        if p.is_symlink():
            raise ValueError('Symlink in repository: ' + str(rel))
        if p.is_file():
            if workspace and str(rel) == PROMPT:
                continue
            result[str(rel)] = file_hash(p)
        elif not p.is_dir():
            raise ValueError('Nonregular repository entry')
    return result


def read_rows(path):
    rows = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    ids = set()
    for row in rows:
        tid = row.get('id')
        if not isinstance(tid, str) or not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*', tid) or tid in ids:
            raise ValueError('Invalid/duplicate dataset ID')
        ids.add(tid)
        cats = row.get('categories')
        if not isinstance(cats, list) or len(cats) != 2 or cats[1] not in ('easy', 'medium', 'hard'):
            raise ValueError('Expected category and declared difficulty')
    if not rows:
        raise ValueError('Empty dataset')
    return rows


def catalog(dataset_dir, out):
    lock = json.loads(LOCK.read_text())
    all_ids = set()
    result = {'schema_version': 1, 'kind': 'cvdp_catalog', 'revision': lock['revision'],
              'files': [], 'tasks': [], 'official_evaluator_executed': False}
    for item in lock['files']:
        path = within(dataset_dir, item['file'])
        if file_hash(path) != item['sha256']:
            raise ValueError('Pinned dataset hash mismatch: ' + item['file'])
        rows = read_rows(path)
        if len(rows) != item['count']:
            raise ValueError('Pinned dataset count mismatch')
        counts = {}
        for row in rows:
            if row['id'] in all_ids:
                raise ValueError('Duplicate ID across files')
            all_ids.add(row['id'])
            counts[row['categories'][1]] = counts.get(row['categories'][1], 0) + 1
            result['tasks'].append({'task_id': row['id'], 'category': row['categories'][0],
                                    'difficulty': row['categories'][1], 'track': item['track']})
        result['files'].append({**item, 'difficulty_counts': counts})
    result['task_count'] = len(all_ids)
    write_json(Path(out) / 'catalog.json', result)
    return result


def git(argv, cwd):
    env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'HOME': str(cwd),
           'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull,
           'GIT_TERMINAL_PROMPT': '0', 'GIT_ALLOW_PROTOCOL': 'file',
           'GIT_AUTHOR_NAME': 'HWBench', 'GIT_AUTHOR_EMAIL': 'fixture@invalid',
           'GIT_COMMITTER_NAME': 'HWBench', 'GIT_COMMITTER_EMAIL': 'fixture@invalid'}
    p = subprocess.run(['git', '-c', 'core.hooksPath=/dev/null', *argv], cwd=cwd,
                       env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    if p.returncode:
        raise ValueError('Local git operation failed: ' + p.stderr.decode(errors='replace')[:500])
    return p.stdout


def bundle_tree(bundle, commit, dest):
    bundle = Path(bundle)
    if bundle.is_symlink() or not bundle.is_file() or not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('Need a local regular Git bundle and full context commit')
    with tempfile.TemporaryDirectory(prefix='hwbench-bundle-') as tmp:
        temp = Path(tmp)
        # A local file argument and file-only protocol prevent network access.
        git(['clone', '--bare', str(bundle.resolve()), 'repo.git'], temp)
        repo = temp / 'repo.git'
        actual = git(['rev-parse', commit + '^{commit}'], repo).decode().strip()
        if actual != commit:
            raise ValueError('Sanitized context commit mismatch')
        if any(entry.startswith(b'160000 ') for entry in git(['ls-tree', '-rz', commit], repo).split(b'\0')):
            raise ValueError('Bundle has unresolved submodules; supply a complete sanitized repository baseline before evaluation')
        archive = temp / 'tree.tar'
        git(['archive', '--format=tar', '--output', str(archive), commit], repo)
        dest.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive) as tar:
            seen = set()
            for member in tar:
                name = member.name.rstrip('/')
                relative_path(name)
                if name in seen or '.git' in Path(name).parts or not (member.isfile() or member.isdir()):
                    raise ValueError('Unsafe bundle tree entry: ' + name)
                seen.add(name)
                target = within(dest, name)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with tar.extractfile(member) as src, target.open('wb') as dst:
                        shutil.copyfileobj(src, dst)
                    target.chmod(0o755 if member.mode & 0o111 else 0o644)


def prepare(dataset, bundles, out, ids=None, fixture=False):
    rows = read_rows(dataset)
    source_hash = file_hash(dataset)
    if not fixture:
        lock = json.loads(LOCK.read_text())
        entry = next((x for x in lock['files'] if x['track'] == 'heavy'), None)
        if source_hash != entry['sha256']:
            raise ValueError('Heavy dataset must match the pinned no-commercial release')
    selected = set(ids) if ids else {r['id'] for r in rows}
    if not selected or selected - {r['id'] for r in rows} or (ids and len(selected) != len(ids)):
        raise ValueError('Unknown/duplicate task selection')
    out = empty_dir(out)
    manifest = {'schema_version': 1, 'kind': 'repository_fixture' if fixture else 'cvdp_heavy_prepared',
                'revision': 'local_fixture' if fixture else REVISION, 'dataset_sha256': source_hash,
                'tasks': [], 'official_evaluator_executed': False,
                'requirements': ['pre-staged evaluator revision', 'pre-loaded Docker images',
                                 'offline container dependencies', 'operator isolation policy'],
                'readiness': 'repository_prepared_only; evaluator/images not verified'}
    for row in rows:
        if row['id'] not in selected:
            continue
        context = row.get('context', {})
        repo, commit = context.get('repo'), context.get('commit')
        if not isinstance(repo, str) or not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*', repo):
            raise ValueError('Invalid sanitized context.repo')
        patch = row.get('patch')
        if not isinstance(patch, dict) or not patch:
            raise ValueError('Missing patch path allowlist')
        for name in patch:
            relative_path(name)
            if '.git' in Path(name).parts or name == PROMPT:
                raise ValueError('Reserved patch path')
        bundle = within(bundles, repo + '.bundle')
        taskroot = out / 'trusted' / row['id']
        bundle_tree(bundle, commit, taskroot / 'baseline')
        hashes = tree_hashes(taskroot / 'baseline')
        if PROMPT in hashes:
            raise ValueError('Reserved prompt path in baseline')
        harness = row.get('harness', {})
        if not isinstance(harness, dict):
            raise ValueError('Invalid harness')
        for name, content in harness.items():
            if not isinstance(content, str):
                raise ValueError('Harness must contain text files')
            dest = within(taskroot / 'harness', name)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content)
        prompt = row.get('prompt')
        if not isinstance(prompt, str) or not prompt:
            raise ValueError('Missing task prompt')
        (taskroot / 'prompt.md').write_text(prompt + '\n\nAllowed changes:\n' + '\n'.join(sorted(patch)))
        manifest['tasks'].append({'task_id': row['id'], 'category': row['categories'][0],
            'difficulty': row['categories'][1], 'backend': 'repository', 'context': context,
            'origin': row.get('origin'), 'bundle_sha256': file_hash(bundle), 'allowed_files': sorted(patch),
            'baseline_hashes': hashes, 'baseline_modes': {name: (within(taskroot / 'baseline', name).stat().st_mode & 0o777) for name in hashes}, 'harness_hashes': tree_hashes(taskroot / 'harness') if harness else {},
            'prompt_sha256': file_hash(taskroot / 'prompt.md')})
    manifest['fingerprint'] = digest(canonical(manifest))
    write_json(out / 'prepared.json', manifest)
    return manifest


def load_prepared(path):
    root = Path(path).resolve()
    m = json.loads((root / 'prepared.json').read_text())
    body = dict(m); fp = body.pop('fingerprint', None)
    if m.get('schema_version') != 1 or m.get('kind') not in ('repository_fixture', 'cvdp_heavy_prepared') or digest(canonical(body)) != fp:
        raise ValueError('Invalid prepared manifest fingerprint')
    for task in m['tasks']:
        base = within(root, 'trusted/' + task['task_id'])
        if tree_hashes(base / 'baseline') != task['baseline_hashes'] or file_hash(base / 'prompt.md') != task['prompt_sha256']:
            raise ValueError('Prepared baseline/prompt was modified')
        if {name: within(base / 'baseline', name).stat().st_mode & 0o7777 for name in task['baseline_hashes']} != task['baseline_modes']:
            raise ValueError('Prepared baseline file modes were modified')
        actual = tree_hashes(base / 'harness') if (base / 'harness').exists() else {}
        if actual != task['harness_hashes']:
            raise ValueError('Trusted harness was modified')
    return root, m


def export(prepared, out):
    root, m = load_prepared(prepared)
    out = empty_dir(out)
    for task in m['tasks']:
        dest = out / task['task_id']
        base = root / 'trusted' / task['task_id']
        shutil.copytree(base / 'baseline', dest)
        shutil.copyfile(base / 'prompt.md', dest / PROMPT)
        # New root commit only: no upstream history, remote, hidden harness or golden patch.
        git(['init', '-q'], dest)
        git(['add', '--all'], dest)
        git(['commit', '-qm', 'Sanitized benchmark baseline'], dest)
    return m


def snapshot(prepared, submissions, out):
    root, m = load_prepared(prepared)
    out = empty_dir(out)
    rows = []
    for task in m['tasks']:
        source = within(submissions, task['task_id'])
        hashes = tree_hashes(source, workspace=True)
        baseline = task['baseline_hashes']; allowed = set(task['allowed_files'])
        changed = {name for name in set(hashes) | set(baseline) if hashes.get(name) != baseline.get(name)}
        if changed - allowed or any(name not in hashes for name in allowed):
            raise ValueError('Changes outside allowlist or missing allowed file: ' + task['task_id'])
        for name in hashes:
            target = within(out / 'sources' / task['task_id'], name)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(within(source, name), target)
            target.chmod(task['baseline_modes'].get(name, 0o644))
        rows.append({'task_id': task['task_id'], 'source_hashes': hashes, 'changed_files': sorted(changed)})
    value = {'schema_version': 1, 'kind': 'repository_submission', 'prepared_fingerprint': m['fingerprint'], 'tasks': rows}
    value['fingerprint'] = digest(canonical(value)); write_json(out / 'submission.json', value)
    return value


def load_submission(path, prepared):
    root = Path(path).resolve(); _, plan = load_prepared(prepared)
    value = json.loads((root / 'submission.json').read_text())
    body = dict(value); fp = body.pop('fingerprint', None)
    if value.get('kind') != 'repository_submission' or digest(canonical(body)) != fp or value.get('prepared_fingerprint') != plan['fingerprint']:
        raise ValueError('Submission identity mismatch')
    if {t['task_id'] for t in value['tasks']} != {t['task_id'] for t in plan['tasks']} or len(value['tasks']) != len(plan['tasks']):
        raise ValueError('Submission task membership mismatch')
    for task in value['tasks']:
        original = next(t for t in plan['tasks'] if t['task_id'] == task['task_id'])
        hashes = task['source_hashes']; baseline = original['baseline_hashes']
        changed = {name for name in set(hashes) | set(baseline) if hashes.get(name) != baseline.get(name)}
        if changed - set(original['allowed_files']) or any(name not in hashes for name in original['allowed_files']):
            raise ValueError('Frozen submission violates allowlist')
        if tree_hashes(within(root, 'sources/' + task['task_id'])) != task['source_hashes']:
            raise ValueError('Submission source hash mismatch')
        modes = {name: within(root, 'sources/' + task['task_id'] + '/' + name).stat().st_mode & 0o7777 for name in hashes}
        expected_modes = {name: original['baseline_modes'].get(name, 0o644) for name in hashes}
        if modes != expected_modes:
            raise ValueError('Frozen submission file mode mismatch')
    return root, value, plan


def grade_control(prepared, submissions, checks, out, sandbox='required'):
    root, plan = load_prepared(prepared)
    if plan['kind'] != 'repository_fixture':
        raise ValueError('Native repository control grader is not the official Heavy evaluator')
    out = empty_dir(out)
    snap = snapshot(prepared, submissions, out / 'frozen')
    config_path = Path(checks).resolve(); config = json.loads(config_path.read_text())
    if set(config) != {t['task_id'] for t in plan['tasks']}:
        raise ValueError('Trusted check configuration task mismatch')
    isolated = sandbox_available() if sandbox != 'off' else False
    if sandbox == 'required' and not isolated:
        raise ValueError('Required bubblewrap unavailable')
    suite = {'id': 'repository-controls', 'fingerprint': plan['fingerprint'], 'file_hashes': {}, 'origin': 'local_repository_fixture'}
    result = new_result(suite, 'Local Git/RTL controls', 'fixture_repository', [1, 7, 42], 10, isolated)
    result.update(planned_runs=len(plan['tasks']), task_count=len(plan['tasks']), repeats=1,
                  task_plan=[{k: t[k] for k in ('task_id', 'category', 'difficulty', 'backend')} | {'repeat': 1} for t in plan['tasks']])
    result['repository'] = {'prepared_fingerprint': plan['fingerprint'], 'submission_fingerprint': snap['fingerprint']}
    # Include trusted checks in comparison identity; never reuse native or official score groups.
    protocol_checks = {}
    for task in plan['tasks']:
        c = config[task['task_id']]
        if not c.get('files') or not c.get('checks'):
            raise ValueError('Native controls need files/checks')
        for name in c['files']:
            relative_path(name)
            if Path(name).suffix not in ('.v', '.sv'):
                raise ValueError('Native control grader accepts RTL only')
        for check in c['checks']:
            if not re.fullmatch(r'[A-Za-z0-9_-]+', check['id']) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', check.get('top', 'tb')):
                raise ValueError('Unsafe native checker identity')
        protocol_checks[task['task_id']] = {'config': c, 'files': {x['tb']: file_hash(within(config_path.parent, x['tb'])) for x in c['checks']}}
    result['protocol']['repository_checks'] = protocol_checks
    result['protocol_fingerprint'] = digest(canonical(result['protocol']))
    write_json(out / 'results.json', result)
    for task in plan['tasks']:
        c = config[task['task_id']]
        spec = {'id': task['task_id'], 'title': task['task_id'], 'category': task['category'], 'difficulty': task['difficulty'],
                'path': '.', 'files': c['files'], 'checks': c['checks']}
        # grade_task only needs a base path and trusted checker files; use an explicit directory path.
        suite['_path'] = str(config_path.parent / 'suite.json')
        spec['path'] = 'checks-root'
        with tempfile.TemporaryDirectory(prefix='hwbench-repo-check-') as tmp:
            checkroot = Path(tmp) / 'checks-root'; checkroot.mkdir()
            for check in c['checks']:
                dest = within(checkroot, check['tb']); dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(within(config_path.parent, check['tb']), dest)
            suite['_path'] = str(Path(tmp) / 'suite.json')
            row = grade_task(suite, spec, out / 'frozen/sources' / task['task_id'], out / 'tasks' / task['task_id'], [1, 7, 42], 10, isolated)
        row.update(repeat=1, backend='repository'); portable_logs(row, out)
        row['repository_source_hashes'] = next(t['source_hashes'] for t in snap['tasks'] if t['task_id'] == task['task_id'])
        result['tasks'].append(row); write_json(out / 'results.json', result)
    write_report(result, out)
    return result


def import_evaluation(prepared, submission, response, out, label='CVDP external evaluation'):
    source, snap, plan = load_submission(submission, prepared)
    response = Path(response).resolve(); raw = json.loads(response.read_text())
    if raw.get('schema_version') != 1 or raw.get('prepared_fingerprint') != plan['fingerprint'] or raw.get('submission_fingerprint') != snap['fingerprint']:
        raise ValueError('External evaluation identity mismatch')
    for key in ('evaluator_revision', 'image_digest', 'protocol_id'):
        if not isinstance(raw.get(key), str) or not raw[key].strip():
            raise ValueError('Missing external evaluator provenance: ' + key)
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', raw['image_digest']):
        raise ValueError('Expected immutable sha256 image digest')
    rows = raw.get('tasks', [])
    ids = [x.get('task_id') for x in rows]
    if len(ids) != len(set(ids)) or set(ids) != {x['task_id'] for x in plan['tasks']}:
        raise ValueError('External response must explicitly account for every planned task')
    if not isinstance(raw.get('reports'), dict) or not raw['reports']:
        raise ValueError('Raw report hashes required')
    for name, expected in raw['reports'].items():
        if file_hash(within(response.parent, name)) != expected:
            raise ValueError('Raw report hash mismatch')
    byid = {r['task_id']: r for r in rows}
    for task in plan['tasks']:
        row = byid[task['task_id']]
        if row.get('status') not in ('pass', 'fail', 'infra_error', 'timeout', 'missing', 'unresolved'):
            raise ValueError('Invalid external task status')
        hashes = next(x['source_hashes'] for x in snap['tasks'] if x['task_id'] == task['task_id'])
        if row.get('source_hashes') != hashes or not isinstance(row.get('reason'), str):
            raise ValueError('External task sources/reason mismatch')
    out = empty_dir(out)
    for name in raw['reports']:
        dest = within(out / 'raw', name); dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(within(response.parent, name), dest)
    shutil.copyfile(response, out / 'external-response.json')
    protocol = {'prepared_fingerprint': plan['fingerprint'], 'evaluator_revision': raw['evaluator_revision'],
                'image_digest': raw['image_digest'], 'protocol_id': raw['protocol_id'],
                'backend': 'cvdp_external_normalized', 'evidence_level': 'externally_reported', 'source_kind': plan['kind']}
    result = {'schema_version': 1, 'label': label, 'kind': 'upstream_import', 'protocol': protocol,
              'protocol_fingerprint': digest(canonical(protocol)), 'planned_runs': len(rows), 'tasks': [],
              'task_count': len(rows), 'repeats': 1, 'task_plan': [],
              'metadata': {'evidence_level': 'externally_reported', 'fixture': plan['kind'] == 'repository_fixture', 'source_kind': plan['kind'], 'parser': 'HWBench normalized contract; not official raw-report parser'},
              'limitations': ['Original external execution was not reverified. Aggregate percentages are never converted into task verdicts.',
                              'Fixture imports do not establish actual model capability or official CVDP scores.']}
    for task in plan['tasks']:
        row = byid[task['task_id']]
        identity = {k: task[k] for k in ('task_id', 'category', 'difficulty')}
        identity.update(repeat=1, backend='cvdp_external_normalized')
        result['task_plan'].append(identity)
        result['tasks'].append({**identity, 'status': row['status'], 'reason': row['reason'],
                                'source_hashes': row['source_hashes'], 'checks': [], 'seconds': None})
    write_json(out / 'results.json', result); write_report(result, out)
    return result


def run_agent(prepared, config, out, timeout=300):
    """Explicit operator wrapper, like the native command adapter; not agent isolation."""
    config_path = Path(config)
    config = json.loads(config_path.read_text())
    argv = config.get('argv')
    if not isinstance(argv, list) or not argv or not all(isinstance(x, str) for x in argv):
        raise ValueError('Agent wrapper needs argv list')
    out = empty_dir(out); plan = export(prepared, out / 'workspaces')
    records = []
    execution = {'planned_ids': [t['task_id'] for t in plan['tasks']], 'tasks': records, 'agent_isolation': 'operator responsibility',
                 'functional_evaluation': 'not_run', 'config_sha256': file_hash(config_path),
                 'metadata': {k: config[k] for k in ('model', 'model_revision', 'harness', 'harness_version') if k in config}}
    protocol = {'prepared_fingerprint': plan['fingerprint'], 'backend': 'repository_agent',
                'timeout_seconds': timeout, 'config_sha256': file_hash(config_path)}
    result = {'schema_version': 1, 'kind': 'fixture_repository_agent' if plan['kind'] == 'repository_fixture' else 'repository_agent_attempt',
              'label': config.get('label', 'repository agent attempts'), 'protocol': protocol,
              'protocol_fingerprint': digest(canonical(protocol)), 'planned_runs': len(plan['tasks']),
              'task_count': len(plan['tasks']), 'repeats': 1, 'tasks': [], 'metadata': execution['metadata'],
              'task_plan': [{k: t[k] for k in ('task_id', 'category', 'difficulty')} | {'repeat': 1, 'backend': 'repository_agent'} for t in plan['tasks']],
              'limitations': ['Agent attempts only: successful command exit is unresolved until functional evaluation.',
                              'All planned attempts remain in the denominator; do not compare only exported submissions.']}
    write_json(out / 'results.json', result)
    write_json(out / 'agent-execution.json', execution)
    for task in plan['tasks']:
        work = out / 'workspaces' / task['task_id']
        args = [x.replace('{workspace}', str(work)).replace('{prompt}', str(work / PROMPT)).replace('{task_id}', task['task_id']) for x in argv]
        record = execute(args, work, out / 'logs' / (task['task_id'] + '.log'), timeout)
        status = 'infra_error' if record.get('error') else 'timeout' if record['timeout'] else 'agent_error' if record['returncode'] != 0 or record['output_limit'] else 'unresolved'
        record['task_id'] = task['task_id']; record['status'] = 'ok' if status == 'unresolved' else status
        portable_logs(record, out); records.append(record)
        identity = next(x for x in result['task_plan'] if x['task_id'] == task['task_id'])
        result['tasks'].append({**identity, 'status': status, 'agent': record, 'checks': [], 'source_hashes': {}, 'seconds': None,
                               'failure_phase': 'unknown' if status == 'unresolved' else 'agent',
                               'reason': 'Agent returned successfully; functional evaluation not performed' if status == 'unresolved' else 'Agent execution failed; no automatic submission'})
        write_json(out / 'results.json', result)
        write_report(result, out)
        write_json(out / 'agent-execution.json', execution)
    if all(r['returncode'] == 0 and not r['timeout'] and not r['output_limit'] and not r.get('error') for r in records):
        snapshot(prepared, out / 'workspaces', out / 'submission')
    else:
        execution['submission_status'] = 'not_created_agent_failure'; write_json(out / 'agent-execution.json', execution)
    return records


def evaluate_external(prepared, submission, config, out, timeout=3600, kit=None, profile='heavy'):
    """Call an operator-owned wrapper; never execute dataset harness code directly."""
    _, snap, plan = load_submission(submission, prepared)
    readiness = None
    if kit is not None or plan['kind'] != 'repository_fixture':
        from .offline import verify
        readiness = verify(kit, profile, required_roles=('evaluator', 'image_archive'))
    cfg = json.loads(Path(config).read_text())
    argv = cfg.get('argv')
    if cfg.get('isolation') != 'operator_managed_container' or cfg.get('offline') is not True:
        raise ValueError('Explicit offline operator-managed container contract required')
    if not isinstance(argv, list) or not argv or not all(isinstance(x, str) for x in argv):
        raise ValueError('Evaluator wrapper needs argv list')
    out = empty_dir(out)
    request = {'schema_version': 1, 'prepared': str(Path(prepared).resolve()), 'submission': str(Path(submission).resolve()),
               'prepared_fingerprint': plan['fingerprint'], 'submission_fingerprint': snap['fingerprint'],
               'expected_ids': [t['task_id'] for t in plan['tasks']], 'offline': True,
               'response': str(out / 'response.json'), 'offline_resources': readiness}
    write_json(out / 'request.json', request)
    args = [x.replace('{request}', str(out / 'request.json')).replace('{response}', str(out / 'response.json')) for x in argv]
    record = execute(args, out, out / 'wrapper.log', timeout); portable_logs(record, out)
    write_json(out / 'wrapper-execution.json', record)
    if record.get('error') or record['returncode'] != 0 or record['timeout'] or record['output_limit']:
        raise ValueError('External evaluator wrapper failed; preserved execution evidence')
    return import_evaluation(prepared, submission, out / 'response.json', out / 'imported')


def transfer(prepared, submission, evaluation, out):
    """Preserve the complete external evaluation reproduction unit, not just its score."""
    load_submission(submission, prepared)
    evaluation = Path(evaluation).resolve()
    if not (evaluation / 'wrapper-execution.json').is_file():
        raise ValueError('Evaluation transfer requires wrapper-execution.json')
    with tempfile.TemporaryDirectory(prefix='hwbench-response-check-') as temp:
        import_evaluation(prepared, submission, evaluation / 'response.json', Path(temp) / 'checked')
    from .offline import pack
    spec = {'schema_version': 1, 'profiles': {'reproduction': ['prepared', 'submission', 'evaluation']},
            'resources': [{'id': name, 'role': 'evidence', 'path': str(Path(path).resolve()), 'destination': name}
                          for name, path in [('prepared', prepared), ('submission', submission), ('evaluation', evaluation)]]}
    with tempfile.TemporaryDirectory(prefix='hwbench-transfer-spec-') as temp:
        path = Path(temp) / 'spec.json'; write_json(path, spec)
        value = pack(path, out)
    return {'fingerprint': value['fingerprint'], 'evidence_level': 'externally_reported', 'official_execution_reverified': False}


def verify_transfer(path):
    from .offline import verify
    result = verify(path, 'reproduction')
    root = Path(path).resolve()
    load_submission(root / 'submission', root / 'prepared')
    if not (root / 'evaluation/wrapper-execution.json').is_file():
        raise ValueError('Missing wrapper execution evidence')
    with tempfile.TemporaryDirectory(prefix='hwbench-response-check-') as temp:
        import_evaluation(root / 'prepared', root / 'submission', root / 'evaluation/response.json', Path(temp) / 'checked')
    return {**result, 'evidence_level': 'externally_reported', 'official_execution_reverified': False}
