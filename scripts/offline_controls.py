"""Relocate a source/resource kit and run controls without original files or network."""
import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from hwbench import offline, repository
from hwbench.cli import bundle, verify_bundle
from hwbench.common import execute, sandbox_available, write_json, within


def sandbox(source, kit, output):
    argv = ['bwrap', '--unshare-all', '--die-with-parent', '--new-session']
    for path in ('/usr', '/bin', '/lib', '/lib64'):
        if Path(path).exists(): argv += ['--ro-bind', path, path]
    return argv + ['--ro-bind', str(source), '/source', '--ro-bind', str(kit), '/kit',
                   '--bind', str(output), '/output', '--tmpfs', '/tmp', '--proc', '/proc', '--dev', '/dev',
                   '--chdir', '/source', '--clearenv', '--setenv', 'PATH', '/usr/bin:/bin',
                   '--setenv', 'HOME', '/tmp', '--setenv', 'LANG', 'C.UTF-8',
                   '--setenv', 'PYTHONDONTWRITEBYTECODE', '1', '--']


def inside(args):
    out = Path('/output')
    if Path(args.original).exists() or os.readlink('/proc/self/ns/net') == args.host_net:
        raise ValueError('Original checkout or host network is still visible')
    sock = socket.socket(); sock.settimeout(.2)
    try:
        if sock.connect_ex(('1.1.1.1', 53)) == 0: raise ValueError('Unexpected external network access')
    finally: sock.close()
    readiness = offline.verify('/kit', 'native')
    steps = []
    commands = [('native', [sys.executable, '-m', 'hwbench', 'demo', '--tasks', 'counter', '--sandbox', 'required', '--out', str(out / 'native')]),
                ('repository', [sys.executable, 'scripts/repository_controls.py', '--out', str(out / 'repository')]),
                ('eda', [sys.executable, 'scripts/eda_controls.py', '--out', str(out / 'eda')])]
    for name, command in commands:
        record = execute(command, ROOT, out / (name + '.log'), 120); record['name'] = name; steps.append(record)
        if record['returncode'] != 0 or record['timeout'] or record['output_limit']:
            raise ValueError('Relocated control failed: ' + name)
    # Transfer/reimport an entire normalized external fixture using moved relative paths.
    prepared = out / 'repository/fixture/prepared'
    submission = out / 'repository/reference/grade/frozen'
    config = out / 'fixture-evaluator.json'
    write_json(config, {'offline': True, 'isolation': 'operator_managed_container',
                       'argv': [sys.executable, str(ROOT / 'scripts/repository_external_fixture.py'), '{request}']})
    repository.evaluate_external(prepared, submission, config, out / 'external')
    repository.transfer(prepared, submission, out / 'external', out / 'reproduction-original')
    shutil.move(out / 'reproduction-original', out / 'reproduction-moved')
    # A second namespace exposes only transferred evidence, no original /output tree.
    recheck = out / 'transfer-check'; recheck.mkdir()
    cmd = sandbox(ROOT, out / 'reproduction-moved', recheck) + [sys.executable, '-m', 'hwbench', 'repo-verify-transfer', '/kit']
    record = execute(cmd, ROOT, out / 'transfer-check.log', 30); record['name'] = 'repository-transfer'; steps.append(record)
    if record['returncode'] != 0: raise ValueError('Relocated repository transfer verification failed')
    cvdp = None
    if (Path('/kit') / 'datasets').exists():
        offline.verify('/kit', 'cvdp_prepare')
        cvdp = repository.catalog('/kit/datasets', out / 'catalog')
        repository.prepare('/kit/datasets/cvdp_v1.1.0_agentic_heavy_code_generation_no_commercial.jsonl',
                           '/kit/bundles', out / 'rvx-prepared', ['cvdp_agentic_heavy_rvx_0004'])
        repository.export(out / 'rvx-prepared', out / 'rvx-work')
    write_json(out / 'validation.json', {'status': 'pass', 'steps': steps, 'original_checkout_visible': False,
               'external_network_available': False, 'source_bundle_has_agents': (ROOT / 'AGENTS.md').is_file(),
               'resource_readiness': readiness, 'runtime': 'preinstalled system tools mounted read-only; OS package installation not tested',
               'cvdp_catalog_tasks': cvdp['task_count'] if cvdp else None, 'actual_rvx_prepared': cvdp is not None,
               'official_cvdp_evaluator_executed': False, 'commercial_eda_executed': False, 'actual_model_evaluated': False})


def main():
    p = argparse.ArgumentParser(); p.add_argument('--out'); p.add_argument('--cvdp-dir')
    p.add_argument('--inside', action='store_true'); p.add_argument('--original'); p.add_argument('--host-net')
    args = p.parse_args()
    if args.inside: inside(args); return
    if not args.out: p.error('--out required')
    if not sandbox_available(): raise ValueError('Relocated offline verification requires bubblewrap')
    out = repository.empty_dir(args.out)
    archive = out / 'source.tar.gz'; bundle(archive); verify_bundle(archive)
    source = out / 'moved/source'; source.mkdir(parents=True)
    with tarfile.open(archive) as tar:
        for member in tar:
            if member.name == 'BUNDLE_SHA256.json': continue
            target = within(source, member.name); target.parent.mkdir(parents=True, exist_ok=True)
            with tar.extractfile(member) as src, target.open('wb') as dst: shutil.copyfileobj(src, dst)
            target.chmod(0o755 if member.mode & 0o111 else 0o644)
    resources = [{'id': 'source', 'role': 'source_bundle', 'path': str(archive), 'destination': 'source.tar.gz'}]
    profiles = {'native': ['source']}
    if args.cvdp_dir:
        cvdp_dir = Path(args.cvdp_dir).resolve()
        lock = json.loads(repository.LOCK.read_text())
        for index, entry in enumerate(lock['files']):
            resources.append({'id': 'dataset' + str(index), 'role': 'dataset', 'path': str(cvdp_dir / entry['file']),
                'destination': 'datasets/' + entry['file'], 'revision': lock['revision'], 'expected_sha256': entry['sha256']})
        resources.append({'id': 'rvx', 'role': 'git_bundle', 'path': str(cvdp_dir / 'bundles/cvdp_agentic_heavy_rvx.bundle'),
                          'destination': 'bundles/cvdp_agentic_heavy_rvx.bundle', 'revision': lock['revision']})
        profiles['cvdp_prepare'] = [r['id'] for r in resources]
    spec = out / 'spec.json'; write_json(spec, {'schema_version': 1, 'profiles': profiles, 'resources': resources})
    offline.pack(spec, out / 'kit-original'); shutil.move(out / 'kit-original', out / 'moved/kit')
    output = out / 'results'; output.mkdir()
    command = sandbox(source, out / 'moved/kit', output) + [sys.executable, 'scripts/offline_controls.py', '--inside',
        '--original', str(ROOT), '--host-net', os.readlink('/proc/self/ns/net')]
    record = execute(command, ROOT, out / 'relocated.log', 180)
    write_json(out / 'execution.json', record)
    if record['returncode'] != 0 or record['timeout'] or record['output_limit']:
        raise ValueError('Relocated offline controls failed; inspect ' + str(out / 'relocated.log'))
    print(output / 'validation.json')

if __name__ == '__main__': main()
