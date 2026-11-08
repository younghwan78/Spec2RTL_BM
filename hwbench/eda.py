"""Offline EDA wrapper contract and serial, durable job queue (stdlib only)."""
import contextlib
import csv
import fcntl
import html
import json
import math
import os
from pathlib import Path
import shutil
import signal
import sys
import tempfile
import time

from .common import canonical, digest, execute, relative_path, within
from .repository import empty_dir, file_hash, tree_hashes
from .reporting import validate as validate_functional, write_csv
from .eda_supervisor import identity as process_identity

METRICS = {'area_um2': 'um^2', 'delay_ns': 'ns', 'power_mw': 'mW'}
TERMINAL = {'complete', 'timeout', 'infra_error', 'invalid_result', 'interrupted', 'budget_exhausted'}


def save(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.write-')
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(raw); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def read(path):
    return json.loads(Path(path).read_text(), parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Nonfinite JSON value')))


def positive(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def nonnegative(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


@contextlib.contextmanager
def locked(root):
    root = Path(root)
    if root.is_symlink() or not root.is_dir(): raise ValueError('Queue/cache must be a real local directory')
    with (root / '.lock').open('a+') as f:
        try: fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise ValueError('Queue/cache is already owned by another worker')
        try: yield
        finally: fcntl.flock(f, fcntl.LOCK_UN)


def config(path):
    path = Path(path).resolve(); c = read(path)
    if 'REPLACE_' in path.read_text() or '/REPLACE/' in path.read_text(): raise ValueError('EDA config still has REPLACE_ placeholders; fill in the actual site tool values')
    if c.get('schema_version') != 1 or c.get('mode') not in ('mock', 'measured') or c.get('stage') not in ('synthesis', 'rtl_estimate'):
        raise ValueError('EDA config requires mode and analysis stage')
    for field, keys in [('tool', ('name', 'version')), ('library', ('name', 'corner')), ('workload', ('id', 'clock_period_ns', 'window'))]:
        if not isinstance(c.get(field), dict) or any(k not in c[field] for k in keys): raise ValueError('Incomplete provenance: ' + field)
    for value in [c['tool']['name'], c['tool']['version'], c['library']['name'], c['library']['corner'], c.get('effort'), c['workload']['id'], c['workload']['window']]:
        if not isinstance(value, str) or not value.strip() or value.lower() in ('unknown', 'unspecified'): raise ValueError('Explicit provenance labels required')
    if c['mode'] == 'measured':
        components = c['tool'].get('components')
        if not isinstance(components, dict) or not {'area_delay', 'power'} <= set(components): raise ValueError('Measured results require every contributing tool/version (area_delay and power roles)')
        for component in components.values():
            if not isinstance(component, dict) or any(not isinstance(component.get(k), str) or not component[k].strip() or component[k].lower() == 'unknown' for k in ('name', 'version')): raise ValueError('Incomplete tool component identity')
    if not positive(c['workload']['clock_period_ns']): raise ValueError('Positive clock period required')
    if not isinstance(c.get('argv'), list) or not c['argv'] or not all(isinstance(x, str) for x in c['argv']): raise ValueError('Wrapper argv list required')
    if not isinstance(c.get('assets'), dict) or not {'wrapper', 'library', 'constraints', 'workload'} <= set(c['assets']): raise ValueError('Local wrapper/library/constraints/workload assets required')
    assets = {}
    for name, value in c['assets'].items():
        if not isinstance(name, str) or not name.replace('_', '').isalnum(): raise ValueError('Invalid asset name')
        p = Path(value); p = p if p.is_absolute() else path.parent / p
        if p.is_symlink() or not p.is_file(): raise ValueError('Missing local regular asset: ' + name)
        assets[name] = p.resolve()
    if '{asset:wrapper}' not in c['argv']: raise ValueError('argv must execute the fingerprinted wrapper asset')
    if not all(any(token in arg for arg in c['argv']) for token in ('{request}', '{response}')): raise ValueError('Request/response placeholders required')
    if not isinstance(c.get('tasks'), dict) or not c['tasks']: raise ValueError('Explicit PPA task scope required')
    for tid, task in c['tasks'].items():
        relative_path(tid)
        if '/' in tid or not isinstance(task.get('top'), str) or not task['top'] or not isinstance(task.get('parameters'), dict): raise ValueError('Task top and parameters required')
        limits = task.get('limits', {})
        if not isinstance(limits, dict) or set(limits) - set(METRICS) or any(not nonnegative(v) for v in limits.values()): raise ValueError('Invalid PPA limits')
    if not isinstance(c.get('env_names', []), list) or any(not isinstance(x, str) or not x.isidentifier() for x in c.get('env_names', [])): raise ValueError('env_names must be explicit environment variable names')
    normalized = {k: c[k] for k in ('schema_version', 'mode', 'stage', 'tool', 'library', 'effort', 'workload', 'argv', 'tasks')}
    normalized['env_names'] = c.get('env_names', [])
    normalized['asset_hashes'] = {k: file_hash(p) for k, p in assets.items()}
    return normalized, assets


def condition(c, task):
    return {k: c[k] for k in ('mode', 'stage', 'tool', 'library', 'effort', 'workload', 'asset_hashes', 'argv', 'env_names')} | {'task': task}


def plan(results, config_path, out, timeout=3600, budget=14400):
    if not positive(timeout) or not positive(budget): raise ValueError('Positive finite timeout and budget required')
    source = Path(results).resolve(); source = source / 'results.json' if source.is_dir() else source
    r = validate_functional(read(source))
    if r['kind'] == 'upstream_import' or any(t.get('backend', 'native') != 'native' for t in r['tasks']): raise ValueError('Externally claimed functional results are not locally verified EDA inputs')
    c, assets = config(config_path)
    task_ids = {t['task_id'] for t in r.get('task_plan', r['tasks'])}
    if set(c['tasks']) - task_ids: raise ValueError('Requested EDA task outside functional plan')
    out = empty_dir(out)
    for name, path in assets.items():
        target = out / 'assets' / name; target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(path, target)
    identities = r.get('task_plan', [{'task_id': t['task_id'], 'repeat': t.get('repeat', 1)} for t in r['tasks']])
    if 'task_plan' not in r and len(identities) != r['planned_runs']: raise ValueError('Incomplete legacy functional plan cannot define EDA scope')
    rows = {(x['task_id'], x.get('repeat', 1)): x for x in r['tasks']}
    q = {'schema_version': 1, 'kind': 'eda_queue', 'label': r['label'], 'created_at': time.time(),
         'functional_kind': r['kind'], 'functional_protocol': r['protocol_fingerprint'], 'functional_planned': r['planned_runs'],
         'functional_result_sha256': file_hash(source), 'config': c, 'timeout_seconds': timeout, 'budget_seconds': budget,
         'charged_seconds': 0.0, 'concurrency': 1, 'jobs': []}
    for item in identities:
        tid, repeat = item['task_id'], item.get('repeat', 1); row = rows.get((tid, repeat))
        job = {'task_id': tid, 'repeat': repeat, 'requested': tid in c['tasks'], 'functional_status': row['status'] if row else 'missing',
               'status': 'not_requested', 'attempts': [], 'queued_at': q['created_at'], 'queue_wait_seconds': None, 'license_wait_seconds': None}
        if job['requested']:
            job['status'] = 'pending' if row and row['status'] == 'pass' else 'skipped_functional_fail'
        if job['status'] == 'pending':
            hashes = row.get('source_hashes')
            if not isinstance(hashes, dict) or not hashes: raise ValueError('Functional PASS source hashes required')
            # Native grade and run have explicit, established snapshot locations.
            key = tid + '-r' + str(repeat) if row.get('agent') else tid
            snap = within(source.parent, 'tasks/' + key + '/submission')
            if tree_hashes(snap) != hashes: raise ValueError('Functional PASS snapshot hash mismatch')
            cond = condition(c, c['tasks'][tid]); cond['functional_protocol'] = r['protocol_fingerprint']; cf = digest(canonical(cond))
            inp = {'source_hashes': hashes, 'condition_fingerprint': cf, 'functional_kind': r['kind'], 'functional_protocol': r['protocol_fingerprint']}
            fingerprint = digest(canonical(inp)); jid = digest(canonical([tid, repeat, fingerprint]))[:24]
            job.update(job_id=jid, source_hashes=hashes, condition=cond, condition_fingerprint=cf, input_fingerprint=fingerprint)
            shutil.copytree(snap, out / 'sources' / jid)
        q['jobs'].append(job)
    q['plan_fingerprint'] = plan_hash(q)
    save(out / 'queue.json', q)
    return q


def plan_hash(q):
    return digest(canonical({k: q[k] for k in ('functional_kind', 'functional_protocol', 'functional_planned', 'functional_result_sha256', 'config', 'timeout_seconds', 'budget_seconds')} |
                           {'jobs': [{k: j[k] for k in ('task_id', 'repeat', 'requested', 'functional_status', 'job_id', 'source_hashes', 'condition', 'condition_fingerprint', 'input_fingerprint') if k in j} for j in q['jobs']]}))


def load(queue):
    root = Path(queue).resolve(); q = read(root / 'queue.json')
    if q.get('schema_version') != 1 or q.get('kind') != 'eda_queue' or q.get('plan_fingerprint') != plan_hash(q): raise ValueError('Queue immutable plan mismatch')
    if not nonnegative(q.get('charged_seconds')): raise ValueError('Invalid persistent budget')
    for name, expected in q['config']['asset_hashes'].items():
        if file_hash(within(root, 'assets/' + name)) != expected: raise ValueError('EDA asset hash mismatch: ' + name)
    for j in q['jobs']:
        if 'job_id' in j and tree_hashes(within(root, 'sources/' + j['job_id'])) != j['source_hashes']: raise ValueError('EDA source hash mismatch')
    return root, q


def validate_response(job, value, directory):
    for key in ('job_id', 'input_fingerprint', 'condition_fingerprint', 'source_hashes'):
        if value.get(key) != job[key]: raise ValueError('EDA response identity mismatch: ' + key)
    if value.get('schema_version') != 1 or value.get('mode') != job['condition']['mode'] or value.get('stage') != job['condition']['stage']: raise ValueError('EDA response mode/stage mismatch')
    if value.get('status') not in ('ok', 'infra_error'): raise ValueError('Invalid EDA result status')
    if not isinstance(value.get('reason'), str): raise ValueError('EDA reason required')
    if value.get('license_wait_seconds') is not None and not nonnegative(value['license_wait_seconds']): raise ValueError('Invalid license wait')
    if not isinstance(value.get('reports'), dict) or not value['reports']: raise ValueError('Raw report hashes required')
    for name, expected in value['reports'].items():
        if file_hash(within(directory, name)) != expected: raise ValueError('EDA raw report mismatch')
    if value['status'] == 'ok':
        if value.get('units') != METRICS or not isinstance(value.get('metrics'), dict) or set(value['metrics']) != set(METRICS) or any(not nonnegative(x) for x in value['metrics'].values()): raise ValueError('Require finite nonnegative PPA metrics in declared units')
        activity = value.get('activity', {})
        if (activity.get('source_fingerprint') != digest(canonical(job['source_hashes'])) or
            activity.get('workload_fingerprint') != digest(canonical(job['condition']['workload'])) or activity.get('report') not in value['reports']):
            raise ValueError('Candidate-specific activity provenance required')
        quality = value.get('quality')
        if not isinstance(quality, dict) or set(quality) != {'lint', 'xprop'} or any(x not in ('pass', 'fail', 'not_requested', 'infra_error') for x in quality.values()): raise ValueError('Separate lint/xprop statuses required')
        if job['condition']['mode'] == 'measured' and any(v != 'not_requested' and k not in job['condition']['tool'].get('components', {}) for k, v in quality.items()):
            raise ValueError('Quality result requires contributing tool/version')
    return value


def completed(root, job):
    p = within(root, job['result_dir'])
    return validate_response(job, read(p / 'response.json'), p)


def request(root, job):
    return {'schema_version': 1, **{k: job[k] for k in ('job_id', 'task_id', 'repeat', 'input_fingerprint', 'condition_fingerprint', 'source_hashes', 'condition')},
            'sources': str(root / 'sources' / job['job_id']), 'assets': {k: str(root / 'assets' / k) for k in job['condition']['asset_hashes']},
            'offline': True, 'activity_requirement': 'Generate activity for these candidate sources using the fixed workload; do not reuse baseline SAIF'}


def install_response(root, job, source, evidence):
    source = Path(source); value = validate_response(job, read(source / 'response.json'), source)
    target = root / 'results' / job['job_id'] / str(len(job['attempts']))
    if target.exists(): raise ValueError('Refusing to overwrite EDA evidence')
    target.mkdir(parents=True)
    for name in value['reports']:
        dst = within(target, name); dst.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(within(source, name), dst)
    save(target / 'response.json', value)
    job.update(status='complete' if value['status'] == 'ok' else 'infra_error', result_dir=str(target.relative_to(root)),
               evidence_level=evidence, license_wait_seconds=value.get('license_wait_seconds'))
    return value


def run(queue, cache=None, max_jobs=None, kit=None, profile='eda'):
    root = Path(queue).resolve()
    if max_jobs is not None and (isinstance(max_jobs, bool) or not isinstance(max_jobs, int) or max_jobs < 1): raise ValueError('max_jobs must be positive')
    cache = Path(cache).resolve() if cache else None
    if cache: cache.mkdir(parents=True, exist_ok=True)
    with locked(root), locked(cache) if cache else contextlib.nullcontext():
        root, q = load(root)
        if kit is not None or q['config']['mode'] == 'measured':
            from .offline import verify
            q['offline_resources'] = verify(kit, profile, required_roles=('tool_installation', 'configuration'))
        if any(j['status'] == 'running' for j in q['jobs']): raise ValueError('Interrupted worker detected; run eda-recover explicitly')
        processed = 0
        for job in q['jobs']:
            if job['status'] != 'pending' or (max_jobs is not None and processed >= max_jobs): continue
            processed += 1
            entry = cache / job['input_fingerprint'] if cache else None
            if entry and (entry / 'response.json').is_file():
                try:
                    cached = read(entry / 'response.json')
                    if cached.get('status') != 'ok': raise ValueError('Only successful cache entries are reusable')
                    # Cache identity excludes task/repeat; remap only job ID after validating input/conditions.
                    cached['job_id'] = job['job_id']
                    validate_response(job, cached, entry)
                    with tempfile.TemporaryDirectory(prefix='hwbench-cache-') as tmp:
                        temp = Path(tmp)
                        for name in cached['reports']:
                            dest = within(temp, name); dest.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(within(entry, name), dest)
                        save(temp / 'response.json', cached)
                        job['attempts'].append({'kind': 'cache', 'seconds': 0.0}); install_response(root, job, temp, 'local_wrapper_cache')
                    save(root / 'queue.json', q); continue
                except (ValueError, OSError, KeyError, TypeError):
                    job['cache_rejected'] = True
            remaining = q['budget_seconds'] - q['charged_seconds']
            if remaining <= 0:
                job['status'] = 'budget_exhausted'; save(root / 'queue.json', q); continue
            allowance = min(q['timeout_seconds'], remaining)
            job['status'] = 'running'; job['queue_wait_seconds'] = max(0.0, time.time() - job['queued_at'])
            attempt = {'kind': 'local_wrapper', 'started_at': time.time(), 'reserved_seconds': allowance, 'seconds': None}
            job['attempts'].append(attempt); q['charged_seconds'] += allowance
            save(root / 'queue.json', q)  # Reserve before launch: crashes cannot reset total budget.
            work = root / 'attempts' / job['job_id'] / str(len(job['attempts'])); work.mkdir(parents=True)
            save(work / 'request.json', request(root, job))
            args = q['config']['argv'][:]
            replacements = {'{request}': str(work / 'request.json'), '{response}': str(work / 'response.json')}
            replacements.update({'{asset:' + k + '}': str(root / 'assets' / k) for k in q['config']['asset_hashes']})
            for key, val in replacements.items(): args = [a.replace(key, val) for a in args]
            env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'HOME': str(work), 'LANG': 'C'}
            env.update({key: os.environ[key] for key in q['config']['env_names'] if key in os.environ})
            supervisor_cfg = {'argv': args, 'cwd': str(work), 'log': str(work / 'wrapper.log'), 'timeout': allowance,
                              'owner_pid': os.getpid(), 'owner_identity': process_identity(os.getpid()),
                              'state': str(work / 'supervisor.json'), 'result': str(work / 'execution.json')}
            save(work / 'supervisor-request.json', supervisor_cfg)
            watcher = execute([sys.executable, str(Path(__file__).with_name('eda_supervisor.py')), str(work / 'supervisor-request.json')],
                              work, work / 'supervisor.log', allowance + 3, env)
            record = read(work / 'execution.json') if (work / 'execution.json').is_file() else {**watcher, 'error': 'EDA supervisor did not finish; recovery required'}
            record['tool_seconds'] = record['seconds']; record['seconds'] = watcher['seconds']
            record['log'] = str((work / 'wrapper.log').relative_to(root)); attempt['execution'] = record; attempt['seconds'] = record['seconds']
            q['charged_seconds'] += record['seconds'] - allowance
            try:
                # Wrapper is operator-trusted, but changed inputs still invalidate its result.
                load(root)
                if record['timeout']: job['status'] = 'timeout'
                elif record.get('error') or record['returncode'] != 0 or record['output_limit']: job['status'] = 'infra_error'
                else:
                    value = install_response(root, job, work, 'local_wrapper')
                    if job['status'] == 'complete' and entry:
                        # Cache has a separate lock; never cache imports, errors, or invalid evidence.
                        if entry.exists(): shutil.rmtree(entry)
                        shutil.copytree(root / job['result_dir'], entry)
            except (ValueError, OSError, KeyError, TypeError) as exc:
                job.update(status='invalid_result', reason=str(exc))
            save(root / 'queue.json', q)
        return q


def recover(queue, retry=False):
    root = Path(queue).resolve()
    with locked(root):
        root, q = load(root)
        for job in q['jobs']:
            if job['status'] == 'running' or (retry and job['status'] in TERMINAL - {'complete'}):
                state = root / 'attempts' / job['job_id'] / str(len(job['attempts'])) / 'supervisor.json'
                if state.exists():
                    process = read(state)
                    if process.get('state') != 'finished':
                        if process_identity(process['supervisor_pid']) == process['supervisor_identity']:
                            raise ValueError('EDA supervisor still owns cleanup; retry recovery after it exits')
                        pid = process.get('tool_pid')
                        if pid and process_identity(pid) == process.get('tool_identity'):
                            os.killpg(pid, signal.SIGKILL)
                        elif pid:
                            try: os.killpg(pid, 0)
                            except ProcessLookupError: pass
                            else: raise ValueError('Orphan process group exists without verifiable leader; operator cleanup required before retry')
                if job['status'] == 'running':
                    job['status'] = 'interrupted'; job['reason'] = 'Owner ended without result; reserved budget retained'
            if retry and job['status'] in ('interrupted', 'timeout', 'infra_error', 'invalid_result', 'budget_exhausted'):
                job['status'] = 'pending'; job['queued_at'] = time.time()
        save(root / 'queue.json', q)
        return q


def export(queue, out):
    root = Path(queue).resolve()
    destination = Path(out).resolve()
    if destination.is_relative_to(root) or root.is_relative_to(destination):
        raise ValueError('EDA export source and destination must not contain each other')
    with locked(root):
        root, q = load(root)
        if any(j['status'] == 'running' for j in q['jobs']): raise ValueError('Cannot export a running queue')
        for job in q['jobs']:
            if job['status'] == 'complete': completed(root, job)
        out = empty_dir(out)
        for p in root.iterdir():
            if p.name in ('.lock', 'TRANSFER_SHA256.json'): continue
            if p.is_symlink(): raise ValueError('Symlink in EDA export')
            if p.is_dir(): shutil.copytree(p, out / p.name, symlinks=True)
            elif p.is_file(): shutil.copy2(p, out / p.name)
        hashes = tree_hashes(out)
        save(out / 'TRANSFER_SHA256.json', hashes)
        return hashes


def verify_transfer(path):
    root = Path(path).resolve(); hashes = read(root / 'TRANSFER_SHA256.json')
    actual = tree_hashes(root); actual.pop('TRANSFER_SHA256.json', None); actual.pop('.lock', None)
    if actual != hashes: raise ValueError('EDA transfer membership/hash mismatch')
    load(root)
    return root


def import_results(queue, transfer):
    source_path, destination_path = Path(transfer).resolve(), Path(queue).resolve()
    if source_path.is_relative_to(destination_path) or destination_path.is_relative_to(source_path):
        raise ValueError('EDA import source and destination must not contain each other')
    source = verify_transfer(transfer); _, incoming = load(source)
    root = destination_path
    with locked(root):
        root, q = load(root)
        if incoming['plan_fingerprint'] != q['plan_fingerprint']: raise ValueError('Imported EDA plan mismatch')
        if any(j['status'] == 'running' for j in q['jobs']): raise ValueError('Cannot import into running queue')
        if q['charged_seconds'] and incoming['charged_seconds'] != q['charged_seconds']: raise ValueError('Divergent execution histories; use a fresh destination plan')
        # Validate every response before installing any evidence or changing queue state.
        for job, other in zip(q['jobs'], incoming['jobs']):
            if job.get('job_id') != other.get('job_id'): raise ValueError('Imported job identity mismatch')
            if other['status'] == 'complete':
                value = completed(source, other)
                if job['status'] == 'complete' and completed(root, job) != value:
                    raise ValueError('Refusing to replace completed evidence')
        transfer_id = digest(canonical(read(source / 'TRANSFER_SHA256.json')))[:32]
        relative = Path('imported-transfers') / transfer_id
        dest = root / relative
        # One immutable directory rename commits all payload files. A crash before the
        # atomic queue write leaves reusable, verified evidence rather than a poison partial job.
        if dest.exists():
            if tree_hashes(dest) != tree_hashes(source): raise ValueError('Existing imported evidence differs')
        else:
            dest.parent.mkdir(exist_ok=True)
            with tempfile.TemporaryDirectory(dir=dest.parent, prefix='.stage-') as temp:
                staged = Path(temp) / 'payload'; shutil.copytree(source, staged)
                verify_transfer(staged)
                os.replace(staged, dest)
        for job, other in zip(q['jobs'], incoming['jobs']):
            if other['status'] == 'complete' and job['status'] != 'complete':
                job.update({k: other[k] for k in ('status', 'attempts', 'queue_wait_seconds', 'license_wait_seconds')})
                job.update(result_dir=str(relative / other['result_dir']), evidence_level='externally_reported')
            elif job['status'] == 'pending' and other['status'] in TERMINAL:
                job.update({k: other[k] for k in ('status', 'attempts', 'reason', 'queue_wait_seconds') if k in other})
        q['charged_seconds'] = max(q['charged_seconds'], incoming['charged_seconds'])
        save(root / 'queue.json', q)
        return q


def summary(queue):
    root, q = load(queue); rows = []; counts = {'functional_planned': q['functional_planned'], 'requested': 0, 'eligible': 0, 'attempted': 0, 'valid_measured': 0, 'valid_mock': 0, 'constraints_satisfied': 0, 'constraint_requested': 0}
    for job in q['jobs']:
        counts['constraint_requested'] += bool(job['requested'] and q['config']['tasks'][job['task_id']].get('limits')); counts['requested'] += job['requested']; counts['eligible'] += 'job_id' in job
        counts['attempted'] += any(a['kind'] != 'cache' for a in job['attempts'])
        row = {k: job.get(k) for k in ('task_id', 'repeat', 'status', 'functional_status', 'condition_fingerprint', 'queue_wait_seconds', 'license_wait_seconds', 'evidence_level')}
        row['metrics'] = None; row['quality'] = None; row['constraints_satisfied'] = None
        if job['status'] == 'complete':
            v = completed(root, job); row.update(metrics=v['metrics'], quality=v['quality'])
            limits = job['condition']['task'].get('limits', {}); row['constraints_satisfied'] = all(v['metrics'][k] <= limit for k, limit in limits.items()) if limits else None
            counts['valid_mock' if q['config']['mode'] == 'mock' else 'valid_measured'] += 1
            counts['constraints_satisfied'] += row['constraints_satisfied'] is True
        rows.append(row)
    return {'schema_version': 1, 'kind': 'eda_report', 'label': q['label'], 'mode': q['config']['mode'], 'stage': q['config']['stage'],
            'functional_kind': q['functional_kind'], 'counts': counts, 'charged_seconds': q['charged_seconds'], 'budget_seconds': q['budget_seconds'],
            'function_and_ppa_rate_constrained_scope': counts['constraints_satisfied'] / counts['constraint_requested'] if counts['constraint_requested'] else None,
            'rows': rows, 'limitations': ['Mock values are contract fixtures, not measured PPA.', 'Local wrapper execution verifies the contract, not vendor report semantics.', 'External imports are claimed measurements, not re-executed tools.', 'Lint/Xprop are separate quality results; no signoff claim.', 'Queue is serial and single-host; wrapper/environment isolation and internal license routing are operator responsibilities.']}


def report(queue, out):
    s = summary(queue); out = Path(out); out.mkdir(parents=True, exist_ok=True); save(out / 'eda-summary.json', s)
    body = '<h1>EDA 평가</h1><p>mode: '+html.escape(s['mode'])+' · stage: '+html.escape(s['stage'])+'</p><pre>'+html.escape(json.dumps(s['counts'], ensure_ascii=False, indent=2))+'</pre>'
    body += '<p>기능 통과 제출 중 요청 범위만 평가합니다. 누락·실패는 분모에 남습니다. 모의 값은 실제 PPA가 아닙니다.</p><table><tr><th>과제/반복</th><th>상태</th><th>측정값</th><th>품질</th><th>증거</th></tr>'
    for r in s['rows']:
        body += '<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in (str(r['task_id'])+'/'+str(r['repeat']), r['status'], r['metrics'], r['quality'], r['evidence_level']))+'</tr>'
    body += '</table><ul>'+''.join('<li>'+html.escape(x)+'</li>' for x in s['limitations'])+'</ul>'
    (out / 'eda-report.html').write_text('<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><style>body{font:16px/1.6 system-ui;margin:30px}table{border-collapse:collapse}td,th{border:1px solid #bbb;padding:8px}pre{white-space:pre-wrap}</style><title>EDA 평가</title><body>'+body+'</body></html>')
    write_csv(out / 'eda.csv', ['task_id', 'repeat', 'status', *METRICS, 'evidence_level'],
              [[r['task_id'], r['repeat'], r['status'], *((r['metrics'] or {}).get(k) for k in METRICS), r['evidence_level']] for r in s['rows']])
    return s


def compare(baseline, candidate, out):
    a = summary(baseline); b = summary(candidate)
    compatible = (a['mode'], a['stage'], a['functional_kind']) == (b['mode'], b['stage'], b['functional_kind'])
    left = {(x['task_id'], x['repeat'], x['condition_fingerprint']): x for x in a['rows'] if x['metrics'] is not None}
    right = {(x['task_id'], x['repeat'], x['condition_fingerprint']): x for x in b['rows'] if x['metrics'] is not None}
    matches = sorted(set(left) & set(right)) if compatible else []
    values = []
    for key in matches:
        x,y=left[key],right[key]
        values.append({'task_id': key[0], 'repeat': key[1], 'condition_fingerprint': key[2], 'baseline_evidence': x['evidence_level'], 'candidate_evidence': y['evidence_level'],
                       'ratios_candidate_over_baseline': {k: y['metrics'][k] / x['metrics'][k] if x['metrics'][k] > 0 else None for k in METRICS}})
    result = {'baseline_counts': a['counts'], 'candidate_counts': b['counts'], 'compatible_domains': compatible,
              'matched': len(matches), 'unmatched_baseline_valid': len(left)-len(matches), 'unmatched_candidate_valid': len(right)-len(matches),
              'pairs': values, 'interpretation': 'Ratios below 1 are smaller for this matched task/condition only. No survivor-only overall ranking. Zero baseline yields null.'}
    out = Path(out); out.mkdir(parents=True, exist_ok=True); save(out / 'eda-comparison.json', result)
    (out / 'eda-comparison.html').write_text('<!doctype html><html lang="ko"><meta charset="utf-8"><title>EDA 비교</title><body><h1>동일 조건 PPA 비교</h1><pre>'+html.escape(json.dumps(result, ensure_ascii=False, indent=2))+'</pre></body></html>')
    return result
