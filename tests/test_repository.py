import copy
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from hwbench import repository as repo
from hwbench.common import digest, write_json

spec = importlib.util.spec_from_file_location('repository_controls', repo.ROOT / 'scripts/repository_controls.py')
controls = importlib.util.module_from_spec(spec); spec.loader.exec_module(controls)


@unittest.skipUnless(shutil.which('git'), 'git required')
class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.prepared = controls.make_fixture(self.root / 'fixture')
        self.work = self.root / 'work'; repo.export(self.prepared, self.work)

    def tearDown(self): self.tmp.cleanup()

    def response(self):
        snap = repo.snapshot(self.prepared, self.work, self.root / 'submission')
        _, plan = repo.load_prepared(self.prepared)
        (self.root / 'raw.txt').write_text('Externally supplied fixture verdict; not actual evaluator output')
        return {'schema_version': 1, 'prepared_fingerprint': plan['fingerprint'], 'submission_fingerprint': snap['fingerprint'],
                'evaluator_revision': 'fixture-v1', 'image_digest': 'sha256:' + '0'*64, 'protocol_id': 'fixture-protocol',
                'reports': {'raw.txt': repo.file_hash(self.root / 'raw.txt')},
                'tasks': [{'task_id': controls.TASK, 'status': 'fail', 'reason': 'fixture external claim',
                           'source_hashes': snap['tasks'][0]['source_hashes']}]}

    def test_sanitized_export_has_no_history_remote_or_harness(self):
        work = self.work / controls.TASK
        self.assertEqual(repo.git(['rev-list', '--count', 'HEAD'], work).strip(), b'1')
        self.assertEqual(repo.git(['remote'], work), b'')
        self.assertFalse((work / 'harness').exists())
        self.assertNotIn('hidden.txt', repo.tree_hashes(work, workspace=True))
        self.assertEqual((work / 'rtl/top.sv').read_text(), controls.TOP % controls.VARIANTS['starter'])

    def test_path_escape_and_symlink_rejected(self):
        (self.work / controls.TASK / 'escape').symlink_to('/tmp')
        with self.assertRaises(ValueError): repo.snapshot(self.prepared, self.work, self.root / 'bad')
        with self.assertRaises(ValueError): repo.within(self.root, '../outside')

    def test_unauthorized_and_missing_file_rejected(self):
        p = self.work / controls.TASK / 'rtl/adder.sv'; original = p.read_text(); p.write_text('tampered')
        with self.assertRaises(ValueError): repo.snapshot(self.prepared, self.work, self.root / 'bad1')
        p.write_text(original); (self.work / controls.TASK / 'rtl/top.sv').unlink()
        with self.assertRaises(ValueError): repo.snapshot(self.prepared, self.work, self.root / 'bad2')

    def test_baseline_tamper_rejected(self):
        (self.prepared / 'trusted' / controls.TASK / 'rtl').mkdir()
        (self.prepared / 'trusted' / controls.TASK / 'baseline/README.md').write_text('tampered')
        with self.assertRaises(ValueError): repo.export(self.prepared, self.root / 'bad')

    def test_import_requires_all_tasks_hashes_and_provenance(self):
        raw = self.response(); response = self.root / 'response.json'; write_json(response, raw)
        result = repo.import_evaluation(self.prepared, self.root / 'submission', response, self.root / 'import')
        self.assertEqual(result['metadata']['evidence_level'], 'externally_reported')
        for field, value in [('tasks', []), ('submission_fingerprint', 'bad'), ('evaluator_revision', '')]:
            bad = copy.deepcopy(raw); bad[field] = value; write_json(response, bad)
            with self.assertRaises(ValueError): repo.import_evaluation(self.prepared, self.root / 'submission', response, self.root / ('bad-' + field))
        raw['reports']['raw.txt'] = '0'*64; write_json(response, raw)
        with self.assertRaises(ValueError): repo.import_evaluation(self.prepared, self.root / 'submission', response, self.root / 'bad-hash')

    def test_snapshot_tamper_rejected(self):
        self.response(); (self.root / 'submission/sources' / controls.TASK / 'rtl/top.sv').write_text('tampered')
        with self.assertRaises(ValueError): repo.load_submission(self.root / 'submission', self.prepared)

    def test_frozen_submission_mode_tamper_rejected(self):
        self.response()
        target = self.root / 'submission/sources' / controls.TASK / 'rtl/top.sv'
        for mode in (0o755, 0o4644):
            target.chmod(mode)
            with self.assertRaisesRegex(ValueError, 'mode mismatch'):
                repo.load_submission(self.root / 'submission', self.prepared)

    def test_complete_reproduction_transfer_is_relocatable(self):
        import sys
        repo.snapshot(self.prepared, self.work, self.root / 'submission')
        config = self.root / 'evaluator.json'
        write_json(config, {'isolation': 'operator_managed_container', 'offline': True,
                           'argv': [sys.executable, str(repo.ROOT / 'scripts/repository_external_fixture.py'), '{request}']})
        repo.evaluate_external(self.prepared, self.root / 'submission', config, self.root / 'evaluation', 5)
        with self.assertRaises(ValueError):
            repo.transfer(self.prepared, self.root / 'submission', self.root / 'evaluation', self.prepared / 'nested')
        self.assertFalse((self.prepared / 'nested').exists())
        repo.transfer(self.prepared, self.root / 'submission', self.root / 'evaluation', self.root / 'transfer')
        shutil.move(self.root / 'transfer', self.root / 'moved')
        shutil.rmtree(self.prepared); shutil.rmtree(self.root / 'submission'); shutil.rmtree(self.root / 'evaluation')
        result = repo.verify_transfer(self.root / 'moved')
        self.assertEqual(result['status'], 'resources_verified')
        self.assertFalse(result['official_execution_reverified'])

    def test_official_mode_rejects_fixture_dataset(self):
        with self.assertRaises(ValueError): repo.prepare(self.root / 'fixture/fixture.jsonl', self.root / 'fixture/bundles', self.root / 'bad-official')

    def test_submodule_dependency_is_not_silently_dropped(self):
        source = self.root / 'fixture/source'
        commit = repo.git(['rev-parse', 'HEAD'], source).decode().strip()
        repo.git(['update-index', '--add', '--cacheinfo', '160000,' + commit + ',dependency'], source)
        repo.git(['commit', '-qm', 'unresolved local submodule'], source)
        commit = repo.git(['rev-parse', 'HEAD'], source).decode().strip()
        bundle = self.root / 'submodule.bundle'
        repo.git(['bundle', 'create', str(bundle), '--all'], source)
        with self.assertRaisesRegex(ValueError, 'submodules'):
            repo.bundle_tree(bundle, commit, self.root / 'submodule-tree')

    def test_agent_failure_has_plan_but_no_submission(self):
        import sys
        config = self.root / 'agent.json'
        write_json(config, {'argv': [sys.executable, '-c', 'raise SystemExit(3)']})
        records = repo.run_agent(self.prepared, config, self.root / 'agent-run', 3)
        self.assertEqual(records[0]['returncode'], 3)
        execution = json.loads((self.root / 'agent-run/agent-execution.json').read_text())
        self.assertEqual(execution['planned_ids'], [controls.TASK])
        self.assertFalse((self.root / 'agent-run/submission').exists())
        result = json.loads((self.root / 'agent-run/results.json').read_text())
        self.assertEqual(result['planned_runs'], 1)
        self.assertEqual(result['tasks'][0]['status'], 'agent_error')
        self.assertTrue((self.root / 'agent-run/report.html').is_file())

    def test_agent_success_is_not_functional_pass(self):
        import sys
        config = self.root / 'agent.json'; write_json(config, {'argv': [sys.executable, '-c', 'pass']})
        repo.run_agent(self.prepared, config, self.root / 'agent-success', 3)
        result = json.loads((self.root / 'agent-success/results.json').read_text())
        self.assertEqual(result['tasks'][0]['status'], 'unresolved')
        self.assertTrue((self.root / 'agent-success/submission').is_dir())

    def test_external_wrapper_contract(self):
        import sys
        repo.snapshot(self.prepared, self.work, self.root / 'submission')
        config = self.root / 'evaluator.json'
        write_json(config, {'isolation': 'operator_managed_container', 'offline': True,
                           'argv': [sys.executable, str(repo.ROOT / 'scripts/repository_external_fixture.py'), '{request}']})
        result = repo.evaluate_external(self.prepared, self.root / 'submission', config, self.root / 'evaluated', 5)
        self.assertTrue(result['metadata']['fixture'])
        self.assertEqual(result['tasks'][0]['status'], 'unresolved')
        self.assertTrue((self.root / 'evaluated/imported/raw/fixture-report.txt').is_file())

    @unittest.skipUnless(shutil.which('iverilog') and repo.sandbox_available(), 'Icarus and bubblewrap required')
    def test_real_positive_and_functional_negative(self):
        for variant in ('starter', 'reference'):
            (self.work / controls.TASK / 'rtl/top.sv').write_text(controls.TOP % controls.VARIANTS[variant])
            result = repo.grade_control(self.prepared, self.work, repo.ROOT / 'benchmarks/repository/checks.json', self.root / variant)
            row = result['tasks'][0]
            self.assertEqual(row['status'], 'pass' if variant == 'reference' else 'fail')
            self.assertTrue(all(c['compile']['returncode'] == 0 for c in row['checks']))

if __name__ == '__main__': unittest.main()
