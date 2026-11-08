import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from hwbench import eda
from hwbench.checker_audit import audit_design
from hwbench.common import ROOT, load_suite
from hwbench.execution import run
from hwbench.grader import grade
from hwbench.quality import analyze, patch_size
from hwbench.reporting import compare_reports, failure_cause, sign_test, summary, wilson

sys.path.insert(0, str(ROOT / 'scripts'))
import eda_profile_wrapper as profile_wrapper  # noqa: E402

FIXTURE = ROOT / 'benchmarks/eda_controls/profile_fixture'
OK = dict(returncode=0, timeout=False, output_limit=False, seconds=1)


def check(cid, seed, status, reason='x'):
    row = dict(id=cid, seed=seed, status=status, reason=reason, compile=dict(OK))
    if status == 'pass':
        row.update(completion_verified=True, simulation=dict(OK))
    return row


def base_result(rows, label='a'):
    plan = [{k: r[k] for k in ('task_id', 'repeat', 'category', 'difficulty', 'backend', 'tier', 'domain')} for r in rows]
    return dict(schema_version=1, label=label, kind='model_run', protocol_fingerprint='p', planned_runs=len(plan), task_plan=plan, tasks=rows)


def run_row(tid, status, repeat=1, tier='soc_block', checks=(), required=2):
    return dict(task_id=tid, repeat=repeat, category='generation', difficulty='hard', backend='native', tier=tier, domain='interface',
                status=status, checks=list(checks), required_checks=required, seconds=1)


class EvaluationLevels(unittest.TestCase):
    def test_tier_and_domain_keep_planned_denominators(self):
        passing = run_row('a', 'pass', checks=[check('x', 1, 'pass'), check('x', 7, 'pass')])
        s = summary(base_result([passing, run_row('b', 'fail', tier='public_small', checks=[check('x', 1, 'fail', 'compile_error')])]))
        self.assertEqual(s['subgroups']['tier']['soc_block']['pass_rate'], 1)
        self.assertEqual(s['subgroups']['tier']['public_small']['planned_runs'], 1)
        self.assertEqual(s['subgroups']['domain']['interface']['distinct_tasks'], 2)

    def test_interval_uses_distinct_tasks_not_repeats(self):
        rows = [run_row('a', 'pass', repeat=i, checks=[check('x', 1, 'pass'), check('x', 7, 'pass')]) for i in (1, 2, 3)]
        s = summary(base_result(rows))
        self.assertEqual(s['distinct_tasks'], 1)
        self.assertEqual(s['pass_rate_ci95'], wilson(1.0, 1))
        self.assertLess(s['pass_rate_ci95'][0], .5)

    def test_failure_causes_prefer_earliest_stage(self):
        compile_first = run_row('a', 'fail', checks=[check('x', 1, 'fail', 'compile_error'), check('y', 1, 'fail', 'assertion_or_completion_failure')])
        self.assertEqual(failure_cause(compile_first), 'compile_error')
        self.assertEqual(failure_cause(run_row('b', 'fail', checks=[check('x', 1, 'fail', 'assertion_or_completion_failure')])), 'functional_mismatch')
        self.assertEqual(failure_cause(dict(run_row('c', 'timeout'), agent={'status': 'timeout'})), 'agent_timeout')
        self.assertEqual(failure_cause(run_row('d', 'infra_error')), 'infra_error')

    def test_partial_credit_is_diagnostic_only(self):
        mixed = run_row('a', 'fail', checks=[check('x', 1, 'pass'), check('x', 7, 'fail', 'assertion_or_completion_failure')])
        no_checks = dict(run_row('b', 'agent_error'), agent={'status': 'agent_error'}, required_checks=2)
        s = summary(base_result([mixed, no_checks]))
        self.assertEqual(s['passed'], 0)
        self.assertEqual(s['diagnostics']['partial_runs'], 1)
        self.assertEqual(s['diagnostics']['seed_dependent_runs'], 1)
        self.assertEqual(s['diagnostics']['check_pass_fraction']['observed_runs'], 1)

    def test_sign_test_matches_exact_binomial(self):
        self.assertIsNone(sign_test(0, 0))
        self.assertAlmostEqual(sign_test(6, 0), 2 / 64)
        self.assertAlmostEqual(sign_test(1, 1), 1.0)

    def test_paired_comparison_excludes_infra_and_counts_failures(self):
        ok = [check('x', 1, 'pass'), check('x', 7, 'pass')]
        a = base_result([run_row('t1', 'pass', checks=ok), run_row('t2', 'pass', checks=ok), run_row('t3', 'infra_error')], 'A')
        b = base_result([run_row('t1', 'fail'), run_row('t2', 'pass', checks=ok), run_row('t3', 'pass', checks=ok)], 'B')
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / 'a.json').write_text(json.dumps(a)); (p / 'b.json').write_text(json.dumps(b))
            compare_reports([p / 'a.json', p / 'b.json'], p / 'out')
            pair = json.loads((p / 'out/comparison.json').read_text())['groups'][0]['paired'][0]
        self.assertEqual((pair['compared_tasks'], pair['excluded_infra_or_missing']), (2, 1))
        self.assertEqual((pair['a_better'], pair['b_better'], pair['ties']), (1, 0, 1))

    def test_paired_comparison_treats_unjudged_as_excluded(self):
        ok = [check('x', 1, 'pass'), check('x', 7, 'pass')]
        a = base_result([run_row('t1', 'unresolved'), run_row('t2', 'missing'), run_row('t3', 'pass', checks=ok)], 'A')
        b = base_result([run_row('t1', 'pass', checks=ok), run_row('t2', 'pass', checks=ok), run_row('t3', 'pass', checks=ok)], 'B')
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / 'a.json').write_text(json.dumps(a)); (p / 'b.json').write_text(json.dumps(b))
            compare_reports([p / 'a.json', p / 'b.json'], p / 'out')
            pair = json.loads((p / 'out/comparison.json').read_text())['groups'][0]['paired'][0]
        self.assertEqual((pair['compared_tasks'], pair['excluded_infra_or_missing']), (1, 2))
        self.assertEqual(pair['b_better'], 0)

    def test_paired_comparison_never_pools_tiers(self):
        ok = [check('x', 1, 'pass'), check('x', 7, 'pass')]
        a = base_result([run_row('t1', 'pass', checks=ok), run_row('t2', 'fail', tier='soc_repair')], 'A')
        b = base_result([run_row('t1', 'fail'), run_row('t2', 'pass', checks=ok, tier='soc_repair')], 'B')
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / 'a.json').write_text(json.dumps(a)); (p / 'b.json').write_text(json.dumps(b))
            compare_reports([p / 'a.json', p / 'b.json'], p / 'out')
            paired = json.loads((p / 'out/comparison.json').read_text())['groups'][0]['paired']
        self.assertEqual([(x['tier'], x['a_better'], x['b_better']) for x in paired], [('soc_block', 1, 0), ('soc_repair', 0, 1)])

    def test_audit_flags_unchecked_output_and_constant_design(self):
        design = 'module m(input clk, input [3:0] a, output reg [3:0] y, output reg v);\n always @(posedge clk) begin y <= a; v <= &a; end\nendmodule\n'
        prologue = 'module tb; reg clk=0; reg [3:0] a=0; wire [3:0] y; wire v; m d(clk,a,y,v); always #5 clk=~clk; integer i; initial begin '
        strong = prologue + 'for(i=0;i<16;i=i+1) begin @(negedge clk); a=i; @(posedge clk); #1; if(y!==a||v!==(&a)) $fatal(1,"x"); end $display("HWBENCH_PASS"); $finish; end endmodule\n'
        no_flag = prologue + 'for(i=0;i<16;i=i+1) begin @(negedge clk); a=i; @(posedge clk); #1; if(y!==a) $fatal(1,"x"); end $display("HWBENCH_PASS"); $finish; end endmodule\n'
        single = prologue + '@(negedge clk); a=9; @(posedge clk); #1; if(y!==9) $fatal(1,"x"); $display("HWBENCH_PASS"); $finish; end endmodule\n'
        run_audit = lambda tb: audit_design({'rtl/m.sv': design}, 'm', [(tb, 'tb')], [1, 7], True)
        self.assertEqual(run_audit(strong)['status'], 'pass')
        self.assertTrue(any(f.startswith('tie:v') for f in run_audit(no_flag)['findings']))
        self.assertTrue(any(f.startswith('constant') or f.startswith('tie:v') for f in run_audit(single)['findings']))

    def test_audit_flags_bench_with_single_stimulus(self):
        design = 'module m(input [3:0] a, output [3:0] y);\n assign y = a + 1;\nendmodule\n'
        tb = 'module tb; reg [3:0] a=3; wire [3:0] y; m d(a,y); initial begin #1; if(y!==4) $fatal(1,"x"); $display("HWBENCH_PASS"); $finish; end endmodule\n'
        result = audit_design({'rtl/m.sv': design}, 'm', [(tb, 'tb')], [1], True)
        self.assertEqual(result['status'], 'weak')
        self.assertTrue(any(f.startswith('constant') for f in result['findings']))

    def test_audit_accepts_correct_constant_design(self):
        design = 'module z(output out);\n assign out = 1\'b0;\nendmodule\n'
        tb = 'module tb; wire o; z d(o); initial begin #1; if(o!==1\'b0) $fatal(1,"x"); $display("HWBENCH_PASS"); $finish; end endmodule\n'
        self.assertEqual(audit_design({'rtl/z.sv': design}, 'z', [(tb, 'tb')], [1], True)['status'], 'pass')

    def test_patch_size_ignores_comments_and_indentation(self):
        self.assertEqual(patch_size('a;\n  b; // x\n', ' a;\nb;\n'), 0)
        self.assertEqual(patch_size('a;\nb;\n', 'a;\nc;\n'), 2)

    def test_quality_is_separate_and_verifies_copy_hash(self):
        suite = load_suite(); suite['tasks'] = [t for t in suite['tasks'] if t['id'] == 'counter']
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            shutil.copytree(ROOT / 'benchmarks/core/tasks/counter/reference', p / 'sub/counter')
            r = grade(suite, p / 'sub', p / 'res', kind='fixture_reference', seeds=[1], sandbox='required')
            self.assertEqual(r['tasks'][0]['status'], 'pass')
            report = analyze(p / 'res', suite, p / 'q', 'required')
            self.assertEqual(report['functional_pass_runs'], 1)
            self.assertEqual(report['runs'][0]['patch_lines'] is None, False)
            self.assertIn('version', report['tools']['yosys'])
            self.assertEqual(report['commands']['verilator'][0], '--lint-only')
            (p / 'res/tasks/counter/submission/rtl/counter.sv').write_text('module changed; endmodule\n')
            with self.assertRaises(ValueError):
                analyze(p / 'res', suite, p / 'q2', 'required')

    def test_placeholder_config_and_profile_refused(self):
        with self.assertRaises(ValueError):
            eda.config(ROOT / 'configs/eda-company.template.json')
        with self.assertRaises(profile_wrapper.ProfileError):
            profile_wrapper.load_profile(ROOT / 'configs/eda-tool-profile.template.json')

    def test_filled_template_is_accepted(self):
        text = (ROOT / 'configs/eda-tool-profile.template.json').read_text()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, 'p.json'); path.write_text(text.replace('REPLACE_', 'SITE_'))
            self.assertEqual(len(profile_wrapper.load_profile(path)['steps']), 3)

    def test_soc_checkers_accept_structurally_different_rtl(self):
        suite = load_suite(ROOT / 'benchmarks/soc_blocks/suite.json')
        alternates = ROOT / 'benchmarks/soc_blocks/alternates'
        names = {p.name for p in alternates.iterdir()}
        suite['tasks'] = [t for t in suite['tasks'] if t['id'] in names]
        self.assertEqual(len(suite['tasks']), 5)
        with tempfile.TemporaryDirectory() as tmp:
            result = grade(suite, alternates, Path(tmp, 'r'), kind='fixture_reference', sandbox='required')
        self.assertEqual({t['task_id']: t['status'] for t in result['tasks']}, {n: 'pass' for n in names})

    def test_claude_code_wrapper_contract(self):
        stub = (
            '#!/usr/bin/env python3\n'
            'import json, os, shutil, sys\n'
            'json.dump(dict(argv=sys.argv[1:], stdin=sys.stdin.read(), memory=os.environ.get("CLAUDE_CODE_DISABLE_AUTO_MEMORY")), open(os.environ["STUB_OUT"], "w"))\n'
            f'shutil.copyfile({str(ROOT / "benchmarks/core/tasks/counter/reference/rtl/counter.sv")!r}, "rtl/counter.sv")\n'
        )
        suite = load_suite(); suite['tasks'] = [t for t in suite['tasks'] if t['id'] == 'counter']
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp); tool = p / 'fake-claude'; tool.write_text(stub); tool.chmod(0o755)
            config = dict(type='command', label='stub', model='m', harness='claude-code', harness_version='stub', kind='fixture_adapter',
                          argv=[sys.executable, str(ROOT / 'scripts/wrappers/claude_code_agent.py'), '{workspace}', '{prompt}'])
            with patch.dict(os.environ, dict(HWB_CC_MODEL='some-model', HWB_CC_BIN=str(tool), STUB_OUT=str(p / 'seen.json'))):
                result = run(suite, config, p / 'out', seeds=[1], sandbox='required')
            seen = json.loads((p / 'seen.json').read_text())
        self.assertEqual(result['tasks'][0]['status'], 'pass')
        self.assertEqual(seen['argv'][:5], ['-p', '--output-format', 'json', '--model', 'some-model'])
        self.assertIn('Allowed submission files', seen['stdin'])
        self.assertEqual(seen['memory'], '1')

    def test_claude_code_wrapper_requires_model(self):
        wrapper = ROOT / 'scripts/wrappers/claude_code_agent.py'
        env = {k: v for k, v in os.environ.items() if k != 'HWB_CC_MODEL'}
        with tempfile.TemporaryDirectory() as tmp:
            prompt = Path(tmp, 'p.md'); prompt.write_text('x')
            done = subprocess.run([sys.executable, str(wrapper), tmp, str(prompt)], capture_output=True, text=True, env=env)
        self.assertNotEqual(done.returncode, 0)

    def fixture_reports(self, root):
        for role in ('synth', 'power', 'lint'):
            subprocess.run([sys.executable, str(FIXTURE / 'fake_eda_tool.py'), role, 'top'], cwd=root, check=True)

    def test_profile_parses_units_and_sums_terms(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.fixture_reports(tmp)
            profile = profile_wrapper.load_profile(FIXTURE / 'profile.json')
            values = profile_wrapper.parse_metrics(profile, Path(tmp))
            self.assertEqual(values['delay_ns'], 2.5)
            self.assertAlmostEqual(values['power_mw'], 2.0)
            self.assertEqual(profile_wrapper.parse_quality(profile, Path(tmp))['lint'], 'pass')

    def calibrate(self, tmp, expected):
        Path(tmp, 'e.json').write_text(json.dumps(expected))
        return subprocess.run([sys.executable, str(ROOT / 'scripts/eda_calibrate.py'), 'reports', '--profile', str(FIXTURE / 'profile.json'),
                               '--reports', str(tmp), '--expected', str(Path(tmp, 'e.json')), '--out', str(Path(tmp, 'c.json'))], capture_output=True, text=True)

    def test_calibration_detects_scale_error(self):
        good = dict(read_by='fixture', metrics=dict(area_um2=1250.5, delay_ns=2.5, power_mw=2.0), quality=dict(lint='pass'))
        with tempfile.TemporaryDirectory() as tmp:
            self.fixture_reports(tmp)
            done = self.calibrate(tmp, good)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertEqual(json.loads(Path(tmp, 'c.json').read_text())['status'], 'calibrated')
        with tempfile.TemporaryDirectory() as tmp:
            self.fixture_reports(tmp)
            done = self.calibrate(tmp, good | dict(metrics=dict(area_um2=1250.5, delay_ns=2.5, power_mw=2000.0)))
            self.assertEqual(done.returncode, 1)
            self.assertEqual(json.loads(Path(tmp, 'c.json').read_text())['status'], 'mismatch')

    def test_calibration_rejects_invalid_expected_values(self):
        for bad in (-1250.5, True, 'x'):
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as tmp:
                self.fixture_reports(tmp)
                done = self.calibrate(tmp, dict(read_by='fixture', metrics=dict(area_um2=bad, delay_ns=2.5, power_mw=2.0)))
                self.assertNotEqual(done.returncode, 0)
                self.assertFalse(Path(tmp, 'c.json').exists())

    def test_calibration_reports_missing_pattern(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.fixture_reports(tmp)
            Path(tmp, 'area.rpt').write_text('format changed\n')
            done = self.calibrate(tmp, dict(read_by='fixture', metrics=dict(area_um2=1, delay_ns=1, power_mw=1)))
            self.assertEqual(done.returncode, 1)
            self.assertEqual(json.loads(Path(tmp, 'c.json').read_text())['status'], 'parse_failed')

    def queue(self, tmp, mutate=None):
        suite = load_suite(); suite['tasks'] = [t for t in suite['tasks'] if t['id'] == 'counter']
        p = Path(tmp)
        shutil.copytree(ROOT / 'benchmarks/core/tasks/counter/reference', p / 'sub/counter')
        grade(suite, p / 'sub', p / 'res', kind='fixture_reference', seeds=[1], sandbox='required')
        profile = json.loads((FIXTURE / 'profile.json').read_text())
        if mutate:
            mutate(profile)
        (p / 'profile.json').write_text(json.dumps(profile))
        cfg = json.loads((ROOT / 'configs/eda-mock.example.json').read_text())
        cfg['argv'] = ['python3', '{asset:wrapper}', '{asset:profile}', '{request}', '{response}']
        for name, source in dict(wrapper=ROOT / 'scripts/eda_profile_wrapper.py', profile=p / 'profile.json', faketool=FIXTURE / 'fake_eda_tool.py',
                                 library=ROOT / 'benchmarks/eda_controls/library.txt', constraints=ROOT / 'benchmarks/eda_controls/constraints.txt',
                                 workload=ROOT / 'benchmarks/eda_controls/workload.txt').items():
            cfg['assets'][name] = str(source)
        (p / 'cfg.json').write_text(json.dumps(cfg))
        eda.plan(p / 'res', p / 'cfg.json', p / 'q', 20, 60)
        return eda.run(p / 'q')['jobs'][0], p

    def test_profile_wrapper_runs_through_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            job, p = self.queue(tmp)
            self.assertEqual(job['status'], 'complete', job)
            response = json.loads((p / 'q' / job['result_dir'] / 'response.json').read_text())
            self.assertEqual(response['metrics'], dict(area_um2=1250.5, delay_ns=2.5, power_mw=2.0))
            self.assertEqual(response['mode'], 'mock')
            self.assertEqual(response['quality']['lint'], 'pass')

    def test_failed_step_is_infra_not_measurement(self):
        def fail(profile):
            profile['steps'][0]['argv'][2] = 'fail'
        with tempfile.TemporaryDirectory() as tmp:
            job, p = self.queue(tmp, fail)
            self.assertEqual(job['status'], 'infra_error', job)
            response = json.loads((p / 'q' / job['result_dir'] / 'response.json').read_text())
            self.assertNotIn('metrics', response)


if __name__ == '__main__':
    unittest.main()
