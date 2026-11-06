"""Run real native PASS -> mock EDA transfer/queue/cache/report without Internet."""
import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from hwbench import eda
from hwbench.common import load_suite
from hwbench.grader import grade


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);args=p.parse_args();out=eda.empty_dir(args.out)
    suite=load_suite();suite['tasks']=[t for t in suite['tasks'] if t['id']=='counter']
    shutil.copytree(ROOT/'benchmarks/core/tasks/counter/reference',out/'submissions/counter')
    r=grade(suite,out/'submissions',out/'functional',kind='fixture_reference',sandbox='required')
    assert r['tasks'][0]['status']=='pass'
    q=out/'queue';eda.plan(out/'functional',ROOT/'configs/eda-mock.example.json',q,5,20)
    eda.export(q,out/'sent');eda.verify_transfer(out/'sent');eda.run(out/'sent',out/'cache')
    eda.export(out/'sent',out/'returned');eda.import_results(q,out/'returned');s=eda.report(q,out/'report')
    eda.plan(out/'functional',ROOT/'configs/eda-mock.example.json',out/'cached',5,20);eda.run(out/'cached',out/'cache')
    c=eda.compare(q,out/'cached',out/'comparison')
    assert s['counts']['valid_mock']==1 and s['counts']['valid_measured']==0 and c['matched']==1
    eda.save(out/'validation.json',{'status':'pass','commercial_eda_executed':False,'actual_model_evaluated':False,
        'checks':['real_native_PASS','offline_export_verify','mock_wrapper','result_import','cache_hit','separate_report','matched_comparison']})
    print(out/'validation.json')

if __name__=='__main__':main()
