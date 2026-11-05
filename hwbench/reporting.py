"""Offline evidence reports. Scores count submitted task runs, never test seeds."""
import copy
import shutil
import csv
import html
import json
import math
import os
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import quote

STATUSES = {'pass', 'fail', 'infra_error', 'invalid_submission', 'agent_error', 'timeout', 'missing', 'empty_patch', 'unresolved'}

def validate(result):
    if not isinstance(result, dict) or result.get('schema_version') != 1:
        raise ValueError('Unsupported report schema')
    for key in ('label', 'kind', 'protocol_fingerprint'):
        if not isinstance(result.get(key), str) or not result[key]:
            raise ValueError('Missing report field: ' + key)
    rows = result.get('tasks')
    planned = result.get('planned_runs')
    if not isinstance(rows, list) or isinstance(planned, bool) or not isinstance(planned, int) or planned < len(rows) or planned < 1:
        raise ValueError('Invalid planned_runs/tasks')
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('task_id'), str) or row.get('status') not in STATUSES:
            raise ValueError('Invalid task row')
        key = (row['task_id'], row.get('repeat', 1))
        if key in seen:
            raise ValueError('Duplicate task/repeat')
        seen.add(key)
        checks = row.get('checks', [])
        if not isinstance(checks, list):
            raise ValueError('Invalid checks')
        checkkeys = set()
        for check in checks:
            if not isinstance(check, dict) or not isinstance(check.get('id'), str) or check.get('status') not in STATUSES:
                raise ValueError('Invalid check')
            ck = (check['id'], check.get('seed'))
            if ck in checkkeys:
                raise ValueError('Duplicate check/seed')
            checkkeys.add(ck)
            if check['status'] == 'pass' and result['kind'] != 'upstream_import':
                if check.get('completion_verified') is not True:
                    raise ValueError('Passing check lacks verified completion')
                for required_stage in ('compile', 'simulation'):
                    evidence = check.get(required_stage)
                    if (not isinstance(evidence, dict) or evidence.get('returncode') != 0
                            or evidence.get('timeout') is not False
                            or evidence.get('output_limit') is not False or evidence.get('error')):
                        raise ValueError('Passing check lacks successful execution evidence')
            for stage in ('compile', 'simulation'):
                data = check.get(stage, {})
                if isinstance(data, dict) and check['status'] == 'pass' and data and (data.get('returncode', 0) != 0 or data.get('timeout') or data.get('output_limit') or data.get('error')):
                    raise ValueError('Passing check has failed tool execution')
                if not isinstance(data, dict):
                    raise ValueError('Invalid tool execution record')
                seconds = data.get('seconds', 0)
                if not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or seconds < 0:
                    raise ValueError('Invalid timing')
        if row['status'] == 'pass' and result['kind'] != 'upstream_import':
            if not checks or len(checks) != row.get('required_checks') or any(c['status'] != 'pass' for c in checks):
                raise ValueError('Pass row lacks all required checks')
    return result


def summary(result):
    validate(result)
    counts = Counter(t['status'] for t in result['tasks'])
    return {'planned_runs': result['planned_runs'], 'recorded_runs': len(result['tasks']),
            'passed': counts['pass'], 'pass_rate': counts['pass']/result['planned_runs'],
            'infra_errors': counts['infra_error'], 'missing_runs': result['planned_runs']-len(result['tasks']),
            'statuses': dict(counts)}


def text(value):
    return html.escape(str(value), quote=True)


def table(headers, rows):
    return '<table><thead><tr>'+''.join('<th>'+text(h)+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+text(v)+'</td>' for v in row)+'</tr>' for row in rows)+'</tbody></table>'


def write_csv(path, headers, rows):
    with path.open('w', newline='', encoding='utf-8-sig') as f:
        w=csv.writer(f); w.writerow(headers)
        for row in rows:
            # Prevent spreadsheet formula execution in untrusted labels/reasons.
            w.writerow(["'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v for v in row])


def log_fragment(record, out, failed):
    if not record or not record.get('log'):
        return '<p>로그 없음</p>'
    p=Path(record['log'])
    if not p.is_absolute(): p=out/p
    try:
        p=p.resolve(); p.relative_to(out.resolve())
    except (ValueError, OSError):
        return '<p>보고서 외부 로그 경로: 링크/본문 제외</p>'
    rel=os.path.relpath(p,out)
    s='<p><a href="'+quote(rel,safe='/')+'">'+text(rel)+'</a></p>'
    if failed and p.is_file():
        with p.open(errors='replace') as f: excerpt=f.read(6000)
        s+='<pre>'+text(excerpt)+'</pre>'
    return s


STYLE='body{font:15px/1.6 system-ui,sans-serif;max-width:1200px;margin:32px auto;padding:0 24px;color:#182838;background:#f6f8fc}table{border-collapse:collapse;width:100%;background:white;margin:16px 0}td,th{border:1px solid #d5dce5;padding:8px;text-align:left;vertical-align:top}th{background:#e9eff6}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#e9eff6;padding:14px}details{background:white;border:1px solid #d5dce5;padding:12px;margin:10px 0}.warning{padding:16px;background:#fff0cd;border-left:5px solid #c77d00}h1,h2{color:#12385c}a{color:#135eaa}'


def write_report(result, out, source_root=None):
    s=summary(result); out=Path(out); out.mkdir(parents=True,exist_ok=True)
    if source_root is not None and Path(source_root).resolve() != out.resolve():
        source_root=Path(source_root).resolve()
        result=copy.deepcopy(result)
        for task in result['tasks']:
            records=[task.get('agent',{})]
            for check in task.get('checks',[]):
                records.extend([check.get('compile',{}),check.get('simulation',{})])
            for record in records:
                if not record.get('log'):
                    continue
                source=Path(record['log'])
                if not source.is_absolute(): source=source_root/source
                try:
                    source=source.resolve()
                    relative=source.relative_to(source_root)
                except (ValueError,OSError):
                    record.pop('log',None)
                    continue
                if source.is_file():
                    destination=out/'evidence'/relative
                    try: destination.resolve().relative_to(out.resolve())
                    except ValueError: raise ValueError('Unsafe evidence destination')
                    destination.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copyfile(source,destination)
                    record['log']=str(destination.resolve())
                else: record.pop('log',None)
    kind=result['kind']
    notice=('기준 구현·오류 주입 채점기 검증 결과입니다. 실제 모델 능력 점수가 아닙니다.' if kind.startswith('fixture_') else
            'CVDP 변형 실행 경로 결과입니다. 공식 CVDP 전체 점수가 아닙니다.' if kind=='cvdp_adapted' else
            '공식 evaluator 결과를 가져왔습니다. 원본 실행을 이 보고서 생성기가 재검증하지 않았습니다.' if kind=='upstream_import' else
            '제출 RTL / agent 실행 결과입니다. 모델·harness 식별 정보와 실행 조건을 함께 확인하십시오.')
    incomplete=s['infra_errors'] or s['missing_runs']
    md=['# HW 평가 보고서', '', result['label'], '', notice, '',f"- 종류: {kind}",f"- 성공/계획: {s['passed']}/{s['planned_runs']} ({s['pass_rate']:.1%})",f"- 인프라 오류: {s['infra_errors']}, 미기록: {s['missing_runs']}", '', '과제 성공은 요구된 모든 check/seed 통과입니다. seed 수를 독립 과제 표본 수로 취급하지 않습니다.', '']
    parts=['<h1>HW 평가 보고서</h1><h2>'+text(result['label'])+'</h2><p class="warning">'+text(notice)+'</p>']
    if incomplete:
        parts+=['<p class="warning">평가 미완료: 인프라 오류 또는 미기록 실행이 있습니다. 계획 실행 수를 분모에 유지했습니다.</p>'];md+=['**평가 미완료: 인프라 오류/미기록 실행을 확인하십시오.**','']
    parts+=['<p>과제 수: '+text(result.get('task_count','unknown'))+' · 반복: '+text(result.get('repeats','unknown'))+' · seeds: '+text(result.get('protocol',{}).get('seeds',[]))+'</p><pre>'+text(json.dumps(result.get('metadata',{}),ensure_ascii=False,indent=2))+'</pre>']
    parts+=[table(['종류','성공/계획','성공률','인프라 오류','미기록'],[[kind,f"{s['passed']}/{s['planned_runs']}",f"{s['pass_rate']:.1%}",s['infra_errors'],s['missing_runs']]])]
    groups=defaultdict(list)
    for t in result['tasks']: groups[t.get('category','unknown')].append(t)
    cats=[[c,sum(t['status']=='pass' for t in ts),len(ts),f"{sum(t['status']=='pass' for t in ts)/len(ts):.1%}"]for c,ts in sorted(groups.items())]
    parts+=['<h2>업무별 결과</h2><p>업무별 분모는 기록된 실행 수입니다. 미기록 실행의 업무 분류는 알 수 없습니다.</p>',table(['업무','성공','기록된 실행','성공률'],cats)]
    md+=['## 업무별 결과','', '| 업무 | 성공 | 기록된 실행 | 성공률 |','|---|---:|---:|---:|']+['| '+' | '.join(map(str,x))+' |' for x in cats]+['']
    tasks=[]; checks=[]
    for t in result['tasks']:
        tasks.append([t['task_id'],t.get('repeat',1),t.get('category','unknown'),t['status'],t.get('reason',''),t.get('seconds',''),len(t.get('checks',[])),t.get('required_checks',''),t.get('agent',{}).get('status',''),t.get('agent',{}).get('seconds',''),json.dumps(t.get('agent',{}).get('usage',{}),ensure_ascii=False)])
        parts+=['<details><summary>'+text(t['task_id'])+' — '+text(t['status'])+' (repeat '+text(t.get('repeat',1))+')</summary><p>'+text(t.get('reason',''))+'</p><pre>'+text(json.dumps(t.get('source_hashes',{}),ensure_ascii=False,indent=2))+'</pre>']
        md+=['### '+t['task_id']+' / repeat '+str(t.get('repeat',1)),'',t['status']+': '+t.get('reason',''),'']
        agent=t.get('agent',{})
        if agent:
            parts+=['<h3>Agent 실행</h3><pre>'+text(json.dumps(agent,ensure_ascii=False,indent=2))+'</pre>',log_fragment(agent,out,agent.get('status')!='ok')]
            md+=['Agent: '+json.dumps(agent,ensure_ascii=False),'']
        if not t.get('checks'): parts+=['<p>세부 check 로그 없음. 원본 evaluator 기록 또는 제출 오류를 확인하십시오.</p>']
        for c in t.get('checks',[]):
            comp=c.get('compile',{});sim=c.get('simulation',{})
            row=[t['task_id'],t.get('repeat',1),c['id'],c.get('seed',''),c['status'],c.get('reason',''),comp.get('returncode',''),comp.get('seconds',''),sim.get('returncode',''),sim.get('seconds','')]
            checks.append(row)
            parts+=['<pre>'+text(json.dumps({'compile_argv':comp.get('argv',comp.get('command',[])),'simulation_argv':sim.get('argv',sim.get('command',[]))},ensure_ascii=False,indent=2))+'</pre>']
            parts+=['<h3>'+text(c['id'])+' / seed '+text(c.get('seed',''))+'</h3><p>'+text(c.get('description',''))+'</p>',table(['결과','원인','compile exit','compile s','sim exit','sim s'],[row[4:]]),log_fragment(comp,out,c['status']!='pass'),log_fragment(sim,out,c['status']!='pass')]
            md+=['- '+c['id']+' seed='+str(c.get('seed',''))+': '+c['status']+' — '+c.get('reason','')]
        parts+=['</details>'];md+=['']
    headers=['task_id','repeat','category','status','reason','seconds','checks','required_checks','agent_status','agent_seconds','usage']
    write_csv(out/'tasks.csv',headers,tasks)
    write_csv(out/'checks.csv',['task_id','repeat','check','seed','status','reason','compile_exit','compile_seconds','simulation_exit','simulation_seconds'],checks)
    provenance={k:result.get(k) for k in ('run_id','created_at','suite_id','origin','suite_fingerprint','protocol_fingerprint','protocol','tools','metadata','file_hashes')}
    body=json.dumps(provenance,ensure_ascii=False,indent=2)
    parts+=['<h2>재현 정보 · 모델/harness · 도구 · 해시</h2><pre>'+text(body)+'</pre><h2>해석 한계</h2>']
    limitations=['유한 시뮬레이션은 전체 RTL 정확성의 증명이 아닙니다.','반복 seed는 독립 과제가 아닙니다. 이 보고서는 seed 기반 신뢰구간을 만들지 않습니다.','상용 EDA/PPA/formal signoff 결과는 이 기능 점수에서 추정하지 않습니다.']+result.get('limitations',[])
    parts+=['<ul>'+''.join('<li>'+text(x)+'</li>' for x in limitations)+'</ul>']
    md+=['## 재현 정보','','```json',body,'```','','## 해석 한계','']+['- '+x for x in limitations]
    (out/'report.html').write_text('<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>HW 평가 보고서</title><style>'+STYLE+'</style><body>'+''.join(parts)+'</body></html>',encoding='utf-8')
    (out/'report.md').write_text('\n'.join(md)+'\n',encoding='utf-8')
    (out/'summary.json').write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def compare_reports(paths, out):
    groups=defaultdict(list)
    for path in paths:
        p=Path(path);p=p/'results.json' if p.is_dir() else p
        r=json.loads(p.read_text());s=summary(r)
        groups[(r['protocol_fingerprint'],r['kind'])].append([r['label'],s['passed'],s['planned_runs'],f"{s['pass_rate']:.1%}",s['infra_errors'],s['missing_runs']])
    parts=['<h1>평가 구성 비교</h1><p>동일 protocol hash와 결과 종류끼리만 묶었습니다. 서로 다른 그룹의 직접 순위 비교는 지원하지 않습니다. fixture는 실제 모델 점수가 아닙니다.</p>']
    for (protocol,kind),rows in groups.items():
        parts+=['<h2>'+text(kind)+'</h2><p>protocol: '+text(protocol)+'</p>',table(['구성','성공','계획','성공률','인프라','미기록'],rows)]
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    (out/'comparison.html').write_text('<!doctype html><html lang="ko"><meta charset="utf-8"><title>HW 비교</title><style>'+STYLE+'</style><body>'+''.join(parts)+'</body></html>',encoding='utf-8')
