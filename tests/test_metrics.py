import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hwbench.common import load_suite
from hwbench.execution import run
from hwbench.grader import grade
from hwbench.reporting import compare_reports, summary, write_report


class MetricsTests(unittest.TestCase):
    def result(self):
        plan = [dict(task_id='a', repeat=i, category='repair', difficulty='hard', backend='native') for i in (1, 2)]
        plan.append(dict(task_id='b', repeat=1, category='generation', difficulty='unknown', backend='native'))
        ok = dict(returncode=0, timeout=False, output_limit=False, seconds=2)
        checks = [dict(id='logic', seed=seed, status='pass', completion_verified=True,
                       compile=copy.deepcopy(ok), simulation=dict(ok, seconds=3)) for seed in (1, 7)]
        first = dict(plan[0], status='pass', required_checks=2, checks=checks, seconds=9,
                     agent=dict(status='ok', seconds=4, usage={'total_tokens': 10}))
        second = dict(plan[1], status='infra_error', checks=[], seconds=0,
                      agent=dict(status='infra_error', seconds=1))
        return dict(schema_version=1, label='metrics', kind='model_run', protocol_fingerprint='same',
                    planned_runs=3, task_plan=plan, tasks=[first, second])

    def test_planned_subgroups_and_missing(self):
        s = summary(self.result())
        self.assertEqual(s['pass_rate'], 1/3)
        self.assertEqual(s['subgroups']['category']['generation']['missing_runs'], 1)
        self.assertEqual(s['subgroups']['category']['generation']['pass_rate'], 0)
        self.assertEqual(s['subgroups']['difficulty']['unknown']['planned_runs'], 1)
        self.assertEqual(s['repeat_consistency'][0]['outcome'], 'mixed')
        self.assertEqual(s['repeat_consistency'][1]['coverage'], 'incomplete')
        self.assertEqual(s['repeat_consistency'][1]['outcome'], 'incomplete')
        self.assertEqual(s['failure_phases'], {'agent': 1})

    def test_legacy_coverage_unknown(self):
        r = self.result(); del r['task_plan']
        s = summary(r)
        self.assertIsNone(s['subgroups']['category']['repair']['planned_runs'])
        self.assertIsNone(s['subgroups']['category']['repair']['pass_rate'])
        self.assertEqual(s['subgroups']['category']['repair']['recorded_pass_rate'], .5)
        self.assertEqual(s['repeat_consistency'][0]['coverage'], 'unknown_legacy')

    def test_timing_and_usage_availability(self):
        s = summary(self.result())
        self.assertEqual(s['timing']['compile_seconds']['total'], 2)
        self.assertEqual(s['timing']['simulation_seconds']['total'], 6)
        self.assertEqual(s['timing']['agent_seconds']['total'], 5)
        self.assertEqual(s['timing']['grading_seconds']['total'], 9)
        self.assertEqual(s['usage']['total_tokens']['observed_runs'], 1)
        self.assertEqual(s['usage']['total_tokens']['total'], 10)
        self.assertIsNone(s['usage']['prompt_tokens']['total'])
        self.assertIsNone(s['usage']['cost']['total'])

    def test_plan_rejects_invalid_identity_or_metadata(self):
        mutations = [lambda r: r['task_plan'].pop(),
                     lambda r: r['task_plan'].__setitem__(1, copy.deepcopy(r['task_plan'][0])),
                     lambda r: r['task_plan'][0].update(repeat=True),
                     lambda r: r['task_plan'][0].update(repeat=0),
                     lambda r: r['task_plan'][0].update(task_id=''),
                     lambda r: r['task_plan'][0].update(difficulty=None),
                     lambda r: r['task_plan'][1].update(category='different'),
                     lambda r: r['tasks'][0].update(task_id='outside'),
                     lambda r: r['tasks'][0].update(difficulty='easy')]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                r = self.result(); mutate(r)
                with self.assertRaises(ValueError): summary(r)

    def test_unknown_failure_and_absent_measurements(self):
        r = self.result(); r['tasks'] = [dict(r['task_plan'][0], status='fail')]
        s = summary(r)
        self.assertEqual(s['failure_phases'], {'unknown': 1})
        self.assertIsNone(s['timing']['grading_seconds']['total'])
        self.assertIsNone(s['usage']['total_tokens']['total'])

    def test_complete_repeat_outcomes(self):
        r = self.result(); r['task_plan'] = r['task_plan'][:2]; r['planned_runs'] = 2
        r['tasks'][1] = copy.deepcopy(r['tasks'][0]); r['tasks'][1]['repeat'] = 2
        self.assertEqual(summary(r)['repeat_consistency'][0]['outcome'], 'all_pass')
        for row in r['tasks']:
            row.update(status='fail', checks=[])
        self.assertEqual(summary(r)['repeat_consistency'][0]['outcome'], 'never_pass')

    def test_report_and_comparison_preserve_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp); r = self.result(); write_report(r, p)
            for name in ('subgroups.csv', 'repeats.csv', 'tasks.csv', 'report.md', 'report.html'):
                self.assertTrue((p/name).is_file())
            self.assertIn('난이도별 결과', (p/'report.html').read_text())
            self.assertIn('compile_seconds_unique', (p/'tasks.csv').read_text(encoding='utf-8-sig'))
            (p/'results.json').write_text(json.dumps(r))
            compare_reports([p], p/'compare')
            c = json.loads((p/'compare/comparison.json').read_text())
            self.assertEqual(c['groups'][0]['runs'][0]['summary']['subgroups']['category']['generation']['planned_runs'], 1)

    def test_grade_persists_plan_before_execution(self):
        suite = load_suite(); suite['tasks'] = suite['tasks'][:1]
        suite['tasks'][0]['difficulty'] = 'declared'
        with tempfile.TemporaryDirectory() as tmp, patch('hwbench.grader.grade_task', side_effect=RuntimeError('interruption')):
            with self.assertRaises(RuntimeError): grade(suite, tmp, Path(tmp)/'out', sandbox='off')
            r = json.loads((Path(tmp)/'out/results.json').read_text())
            self.assertEqual(r['tasks'], [])
            self.assertEqual(r['task_plan'][0]['difficulty'], 'declared')
            self.assertEqual(summary(r)['missing_runs'], 1)

    def test_run_persists_all_repeats_before_export(self):
        suite = load_suite(); suite['tasks'] = suite['tasks'][:1]
        with tempfile.TemporaryDirectory() as tmp, patch('hwbench.execution.export_task', side_effect=RuntimeError('interruption')):
            with self.assertRaises(RuntimeError):
                run(suite, {'type': 'command', 'argv': ['/bin/true']}, Path(tmp)/'out', repeats=3, sandbox='off')
            r = json.loads((Path(tmp)/'out/results.json').read_text())
            self.assertEqual([p['repeat'] for p in r['task_plan']], [1, 2, 3])
            self.assertEqual(summary(r)['missing_runs'], 3)


if __name__ == '__main__':
    unittest.main()
