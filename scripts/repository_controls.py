"""Reproducible local Git + RTL controls; no model or official CVDP score."""
import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from hwbench import repository as repo
from hwbench.common import write_json

TASK = 'local_repository_saturation'
TOP = 'module top(input [3:0] a,b,output [3:0] y); wire [4:0] sum; adder u(a,b,sum); assign y = %s; endmodule\n'
VARIANTS = {'starter': 'sum[3:0]', 'reference': "sum[4] ? 4'hf : sum[3:0]", 'mutant': "sum[4] ? 4'he : sum[3:0]"}


def make_fixture(out):
    out = repo.empty_dir(out)
    source = out / 'source'; (source / 'rtl').mkdir(parents=True)
    (source / 'rtl/top.sv').write_text(TOP % VARIANTS['starter'])
    (source / 'rtl/adder.sv').write_text('module adder(input [3:0] a,b,output [4:0] sum); assign sum={1\'b0,a}+{1\'b0,b}; endmodule\n')
    (source / 'README.md').write_text('Unsigned four-bit saturating adder. Only rtl/top.sv may change.\n')
    repo.git(['init', '-q'], source); repo.git(['add', '--all'], source); repo.git(['commit', '-qm', 'broken sanitized baseline'], source)
    commit = repo.git(['rev-parse', 'HEAD'], source).decode().strip()
    bundles = out / 'bundles'; bundles.mkdir()
    repo.git(['bundle', 'create', str(bundles / 'local_saturation.bundle'), '--all'], source)
    row = {'id': TASK, 'categories': ['cid004', 'hard'],
           'prompt': 'Repair rtl/top.sv so y=min(a+b,15) for unsigned four-bit inputs. Keep all other files unchanged. This difficulty label is a fixture, not a calibrated benchmark rating.',
           'context': {'repo': 'local_saturation', 'commit': commit},
           'origin': {'repo': 'fixture-only', 'commit': '0'*40}, 'patch': {'rtl/top.sv': ''},
           'harness': {'hidden.txt': 'Trusted harness is not exported to the agent.'}}
    dataset = out / 'fixture.jsonl'; dataset.write_text(json.dumps(row)+'\n')
    repo.prepare(dataset, bundles, out / 'prepared', fixture=True)
    return out / 'prepared'


def main():
    p = argparse.ArgumentParser(); p.add_argument('--out', required=True); args = p.parse_args()
    out = repo.empty_dir(args.out)
    prepared = make_fixture(out / 'fixture')
    results = {}
    for variant, expression in VARIANTS.items():
        work = out / variant / 'work'; repo.export(prepared, work)
        (work / TASK / 'rtl/top.sv').write_text(TOP % expression)
        result = repo.grade_control(prepared, work, ROOT / 'benchmarks/repository/checks.json', out / variant / 'grade', 'required')
        row = result['tasks'][0]; results[variant] = row['status']
        expected = 'pass' if variant == 'reference' else 'fail'
        if row['status'] != expected:
            raise ValueError('Unexpected control verdict: ' + variant)
        if expected == 'fail' and not all(c['compile']['returncode'] == 0 and c['simulation']['returncode'] != 0 for c in row['checks']):
            raise ValueError('Negative control did not fail functionally')
    write_json(out / 'validation.json', {'status': 'pass', 'variants': results, 'official_cvdp_evaluator_executed': False, 'real_model_evaluated': False})
    print(json.dumps(results))

if __name__ == '__main__': main()
