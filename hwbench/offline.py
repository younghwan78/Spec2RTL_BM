"""File-only transfer inventories. Verification never installs or downloads tools."""
import hashlib
import json
from pathlib import Path
import shutil

from .common import canonical, digest, relative_path, within, write_json
from .repository import empty_dir, tree_hashes

ROLES = {'source_bundle', 'dataset', 'git_bundle', 'evaluator', 'image_archive',
         'runtime_package', 'configuration', 'evidence', 'license_notice', 'tool_installation'}
MANIFEST = 'OFFLINE_INVENTORY.json'


def stream_hash(stream):
    value = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b''):
        value.update(block)
    return value.hexdigest()


def inventory_files(root):
    root = Path(root)
    hashes = tree_hashes(root)
    return {name: {'sha256': sha, 'bytes': within(root, name).stat().st_size,
                   'mode': within(root, name).stat().st_mode & 0o7777}
            for name, sha in hashes.items() if name != MANIFEST}


def pack(spec_path, out):
    spec_path = Path(spec_path).resolve()
    spec = json.loads(spec_path.read_text())
    if spec.get('schema_version') != 1 or not isinstance(spec.get('resources'), list) or not spec['resources']:
        raise ValueError('Offline spec needs schema_version=1 and resources')
    profiles = spec.get('profiles')
    if not isinstance(profiles, dict) or not profiles:
        raise ValueError('Explicit offline profiles required')
    ids = set(); resources = []; paths = []
    for row in spec['resources']:
        rid = row.get('id'); role = row.get('role'); dest = row.get('destination')
        if not isinstance(rid, str) or not rid or rid in ids or role not in ROLES:
            raise ValueError('Invalid/duplicate offline resource identity or role')
        relative_path(dest)
        if dest == MANIFEST or any(dest == x or dest.startswith(x + '/') or x.startswith(dest + '/') for x in paths):
            raise ValueError('Overlapping or reserved offline destination')
        source = Path(row['path']); source = source if source.is_absolute() else spec_path.parent / source
        if source.is_symlink() or not source.exists():
            raise ValueError('Missing local resource: ' + rid)
        if source.is_dir(): tree_hashes(source)
        elif not source.is_file(): raise ValueError('Resource must be a regular file or directory')
        ids.add(rid); paths.append(dest)
        resources.append((row, source.resolve()))
    for name, required in profiles.items():
        if not isinstance(name, str) or not name or not isinstance(required, list) or not required or len(required) != len(set(required)) or any(x not in ids for x in required):
            raise ValueError('Profile must list known unique required resource IDs')
    destination_root = Path(out).resolve()
    if any(source.is_dir() and destination_root.is_relative_to(source) for _, source in resources):
        raise ValueError('Output cannot be inside a resource')
    out = empty_dir(out)
    manifest = {'schema_version': 1, 'kind': 'offline_inventory', 'profiles': profiles, 'resources': [],
                'runtime_status': 'not_checked; files are not installed tools or loaded images'}
    for row, source in resources:
        if out.is_relative_to(source): raise ValueError('Output cannot be inside a resource')
        target = within(out, row['destination']); target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir(): shutil.copytree(source, target)
        else: shutil.copy2(source, target)
        entry = {k: row[k] for k in ('id', 'role', 'destination')}
        entry['revision'] = row.get('revision', 'operator_supplied')
        entry['type'] = 'directory' if source.is_dir() else 'file'
        if row.get('expected_sha256'):
            with target.open('rb') as stream: actual = stream_hash(stream)
            if actual != row['expected_sha256']: raise ValueError('Pinned resource hash mismatch: ' + row['id'])
        manifest['resources'].append(entry)
    manifest['files'] = inventory_files(out)
    manifest['fingerprint'] = digest(canonical(manifest))
    write_json(out / MANIFEST, manifest)
    verify(out)
    return manifest


def verify(kit, profile=None, required_roles=()):
    if kit is None: raise ValueError('A verified offline resource kit is required before external execution')
    root = Path(kit)
    if root.is_symlink(): raise ValueError('Offline kit root cannot be a symlink')
    root = root.resolve(); manifest = json.loads(within(root, MANIFEST).read_text())
    body = dict(manifest); fingerprint = body.pop('fingerprint', None)
    if manifest.get('schema_version') != 1 or manifest.get('kind') != 'offline_inventory' or digest(canonical(body)) != fingerprint:
        raise ValueError('Offline inventory identity mismatch')
    if inventory_files(root) != manifest.get('files'):
        raise ValueError('Offline resource missing or content/mode changed')
    resources = {r['id']: r for r in manifest['resources']}
    if len(resources) != len(manifest['resources']): raise ValueError('Duplicate resource ID')
    selected = manifest['profiles'].get(profile) if profile else list(resources)
    if selected is None or not selected or any(x not in resources for x in selected):
        raise ValueError('Missing offline profile or required resource')
    roles = {resources[x]['role'] for x in selected}
    if set(required_roles) - roles:
        raise ValueError('Offline profile missing required roles: ' + ', '.join(sorted(set(required_roles) - roles)))
    for rid in selected:
        resource = resources[rid]; dest = within(root, resource['destination'])
        if resource['type'] == 'file' and not dest.is_file(): raise ValueError('Required resource is absent: ' + rid)
        if resource['type'] == 'directory' and not dest.is_dir(): raise ValueError('Required resource is absent: ' + rid)
    return {'status': 'resources_verified', 'fingerprint': fingerprint, 'profile': profile,
            'resources': selected, 'runtime_status': manifest['runtime_status'],
            'external_network_used': False}
