"""One command: automated checks + real positive/negative RTL evidence reports."""
import argparse
import datetime
import html
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from hwbench.common import digest, execute, sandbox_available, write_json


def main():
    p=argparse.ArgumentParser();p.add_argument('--out');args=p.parse_args()
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=Path(args.out or ROOT/'artifacts'/('validation-'+stamp)).resolve()
    if out.exists() and any(out.iterdir()):p.error('Output must be empty')
    out.mkdir(parents=True,exist_ok=True)
    steps=[]
    commands=[('unit-tests',[sys.executable,'-m','unittest','discover','-s','tests','-v']),
              ('fixture-controls',[sys.executable,'benchmarks/core/verify.py']),
              ('core-demo',[sys.executable,'-m','hwbench','demo','--out',str(out/'core'),'--sandbox','required' if sandbox_available() else 'auto']),
              ('cvdp-adapted',[sys.executable,'-m','hwbench','demo','--suite','benchmarks/cvdp_adapted/suite.json','--out',str(out/'cvdp'),'--sandbox','required' if sandbox_available() else 'auto'])]
    for name,argv in commands:
        result=execute(argv,ROOT,out/(name+'.log'),180)
        result['name']=name;steps.append(result)
        print(name, 'PASS' if result['returncode']==0 and not result['timeout'] else 'FAIL',flush=True)
    if sandbox_available():
        # Explicitly deny network access for the entire offline smoke invocation.
        argv=['bwrap','--ro-bind','/','/','--bind',str(out),str(out),'--tmpfs','/tmp','--proc','/proc','--dev','/dev','--unshare-net','--die-with-parent',
              '--setenv','PYTHONDONTWRITEBYTECODE','1','--',sys.executable,'-m','hwbench','demo',
              '--tasks','counter','--out',str(out/'offline'),'--sandbox','required']
        result=execute(argv,ROOT,out/'offline.log',90);result['name']='network-denied-smoke';steps.append(result)
        print(result['name'],'PASS' if result['returncode']==0 else 'FAIL',flush=True)
    else:
        steps.append({'name':'network-denied-smoke','returncode':None,'skipped':True,'reason':'bubblewrap unavailable'})
    status=all(s.get('returncode')==0 and not s.get('timeout') and not s.get('output_limit') for s in steps if not s.get('skipped'))
    tests_log=(out/'unit-tests.log').read_text(errors='replace')
    m=re.search(r'Ran (\d+) tests',tests_log)
    result={'status':'pass' if status else 'fail','created_at':stamp,'unit_tests':int(m.group(1)) if m else None,
            'steps':steps,'actual_model_evaluated':False,'commercial_eda_evaluated':False,
            'official_cvdp_evaluator_executed':False,'official_hwe_evaluator_executed':False,
            'source_hashes':{str(f.relative_to(ROOT)):digest(f.read_bytes()) for f in sorted((ROOT/'hwbench').glob('*.py'))}}
    write_json(out/'validation.json',result)
    links=[('기본 6과제 기준 구현','core/reference/report.html'),('기본 과제 오류 주입 1','core/mutant0/report.html'),
           ('기본 과제 오류 주입 2','core/mutant1/report.html'),('기본 시작 코드','core/starter/report.html'),
           ('CVDP 예제 변형 실행 기준 구현','cvdp/reference/report.html'),('CVDP 예제 오류 검출','cvdp/mutant0/report.html'),
           ('인터넷 차단 검증','offline/reference/report.html')]
    text='<!doctype html><html lang="ko"><meta charset="utf-8"><title>HW BM 검증 결과</title><style>body{max-width:1000px;margin:40px auto;font:16px/1.7 system-ui;padding:0 20px}table{border-collapse:collapse}td,th{padding:10px;border:1px solid #ccc}.notice{padding:20px;background:#fff0cd}</style><body><h1>HW BM 구현 검증 결과</h1>'
    text+='<p class="notice">기준 RTL과 오류 구현을 사용한 채점기 검증입니다. 실제 모델의 능력 평가 결과가 아닙니다. CVDP는 변형 실행 예제이며 HWE·상용 EDA 전체 실행은 포함하지 않습니다.</p>'
    text+='<p>실행: '+stamp+' / 결과: '+result['status']+' / 자동 테스트: '+str(result['unit_tests'])+'</p><table><tr><th>검증</th><th>결과</th><th>로그</th></tr>'
    for step in steps:
        name=step['name'];log=Path(step['log']).name if step.get('log') else ''
        text+='<tr><td>'+html.escape(name)+'</td><td>'+('SKIPPED' if step.get('skipped') else 'PASS' if step.get('returncode')==0 else 'FAIL')+'</td><td><a href="'+html.escape(log,quote=True)+'">로그</a></td></tr>'
    text+='</table><h2>상세 평가 보고서</h2><ul>'
    text+=''.join('<li><a href="'+href+'">'+label+'</a></li>' for label,href in links if (out/href).is_file())
    text+='</ul><p>각 보고서에 JSON·CSV, 파일 해시, simulator 버전, seed, 항목별 로그와 실패 원인을 보존했습니다.</p></body></html>'
    (out/'index.html').write_text(text)
    print(out/'index.html')
    return 0 if status else 1

if __name__=='__main__':raise SystemExit(main())
