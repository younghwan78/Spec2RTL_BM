import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from hwbench import offline, repository
from hwbench.common import write_json


class OfflineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); (self.root / 'resource').mkdir()
        (self.root / 'resource/tool').write_text('local resource'); (self.root / 'resource/tool').chmod(0o755)
        self.spec = self.root / 'spec.json'
        write_json(self.spec, {'schema_version': 1, 'profiles': {'native': ['runtime']},
            'resources': [{'id': 'runtime', 'role': 'runtime_package', 'path': 'resource', 'destination': 'payload/runtime'}]})

    def pack(self):
        offline.pack(self.spec, self.root / 'kit'); return self.root / 'kit'

    def test_resource_relocation_and_runtime_boundary(self):
        kit = self.pack(); shutil.move(kit, self.root / 'moved'); shutil.rmtree(self.root / 'resource')
        result = offline.verify(self.root / 'moved', 'native')
        self.assertEqual(result['status'], 'resources_verified'); self.assertIn('not_checked', result['runtime_status'])
        self.assertEqual((self.root / 'moved/payload/runtime/tool').stat().st_mode & 0o777, 0o755)

    def test_hash_mode_missing_extra_and_profile_rejection(self):
        kit = self.pack(); tool = kit / 'payload/runtime/tool'
        with self.assertRaises(ValueError): offline.verify(kit, 'absent')
        with self.assertRaises(ValueError): offline.verify(kit, 'native', ('image_archive',))
        tool.chmod(0o644)
        with self.assertRaises(ValueError): offline.verify(kit)
        tool.chmod(0o755); tool.write_text('tamper')
        with self.assertRaises(ValueError): offline.verify(kit)
        tool.unlink()
        with self.assertRaises(ValueError): offline.verify(kit)

    def test_pack_rejects_missing_symlink_escape_and_containment(self):
        with self.assertRaises(ValueError): offline.pack(self.spec, self.root / 'resource/nested')
        self.assertFalse((self.root / 'resource/nested').exists())
        (self.root / 'resource/link').symlink_to('/etc/passwd')
        with self.assertRaises(ValueError): self.pack()
        (self.root / 'resource/link').unlink()
        spec = json.loads(self.spec.read_text()); spec['resources'][0]['destination'] = '../escape'; write_json(self.spec, spec)
        with self.assertRaises(ValueError): self.pack()
        self.assertFalse((self.root / 'kit').exists())

    def test_nonfixture_evaluator_requires_resources_before_launch(self):
        with patch.object(repository, 'load_submission', return_value=(None, {}, {'kind': 'cvdp_heavy_prepared'})), patch.object(repository, 'execute') as execute:
            with self.assertRaisesRegex(ValueError, 'offline resource kit'):
                repository.evaluate_external('prepared', 'submission', 'missing-config', self.root / 'out')
            execute.assert_not_called(); self.assertFalse((self.root / 'out').exists())

if __name__ == '__main__': unittest.main()
