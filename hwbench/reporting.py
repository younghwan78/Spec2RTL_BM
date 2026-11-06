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
    plan = result.get('task_plan')
    planned_keys = {}
    if plan is not None:
        if not isinstance(plan, list) or len(plan) != planned:
            raise ValueError('Invalid task_plan length')
        task_metadata = {}
        for item in plan:
            if not isinstance(item, dict):
                raise ValueError('Invalid planned task')
            key = identity(item)
            if key in planned_keys:
                raise ValueError('Duplicate planned task/repeat')
            metadata = tuple(item.get(field, 'unknown') for field in ('category', 'difficulty', 'backend'))
            if any(not isinstance(value, str) or not value.strip() for value in metadata):
                raise ValueError('Invalid planned metadata')
            if key[0] in task_metadata and task_metadata[key[0]] != metadata:
                raise ValueError('Inconsistent planned task metadata')
            task_metadata[key[0]] = metadata
            planned_keys[key] = item
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('task_id'), str) or row.get('status') not in STATUSES:
            raise ValueError('Invalid task row')
        key = identity(row)
        if plan is not None:
            if key not in planned_keys:
                raise ValueError('Recorded task/repeat outside task_plan')
            for field in ('category', 'difficulty', 'backend'):
                if row.get(field, 'unknown') != planned_keys[key].get(field, 'unknown'):
                    raise ValueError('Recorded task metadata differs from task_plan')
        for record in (row, row.get('agent', {})):
            if not isinstance(record, dict):
                raise ValueError('Invalid execution record')
            if record.get('seconds') is not None and number(record['seconds']) is None:
                raise ValueError('Invalid elapsed time')
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


def identity(row):
    tid, repeat = row.get('task_id'), row.get('repeat', 1)
    if not isinstance(tid, str) or not tid or isinstance(repeat, bool) or not isinstance(repeat, int) or repeat < 1:
        raise ValueError('Invalid task/repeat identity')
    return tid, repeat


def number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0 else None


def failure_phase(row):
    if row['status'] == 'pass':
        return 'none'
    if row.get('failure_phase') in {'submission', 'setup', 'agent', 'compile', 'simulation', 'multiple'}:
        return row['failure_phase']
    agent = row.get('agent', {})
    if agent.get('status') and agent['status'] != 'ok':
        return 'agent'
    phases = set()
    for check in row.get('checks', []):
        if check['status'] == 'pass':
            continue
        if check.get('simulation'):
            phases.add('simulation')
        elif check.get('compile'):
            phases.add('compile')
        else:
            phases.add('unknown')
    return next(iter(phases)) if len(phases) == 1 else 'multiple' if phases else 'unknown'


def observations(values):
    values = [v for v in values if number(v) is not None]
    return {'observed_runs': len(values), 'total': sum(values) if values else None,
            'mean': sum(values) / len(values) if values else None}


def run_timing(row):
    compiles = {}
    simulations = []
    for check in row.get('checks', []):
        if 'seconds' in check.get('compile', {}):
            compiles.setdefault(check['id'], check['compile']['seconds'])
        if 'seconds' in check.get('simulation', {}):
            simulations.append(check['simulation']['seconds'])
    return {'agent_seconds': row.get('agent', {}).get('seconds'), 'grading_seconds': row.get('seconds'),
            'compile_seconds': observations(compiles.values())['total'],
            'simulation_seconds': observations(simulations)['total']}


def summary(result):
    validate(result)
    rows = result['tasks']
    counts = Counter(t['status'] for t in rows)
    plan = result.get('task_plan')
    groups = {}
    for field in ('category', 'difficulty', 'backend'):
        names = sorted({r.get(field, 'unknown') for r in (plan if plan is not None else rows)})
        groups[field] = {}
        for name in names:
            recorded = [r for r in rows if r.get(field, 'unknown') == name]
            passed = sum(r['status'] == 'pass' for r in recorded)
            planned = sum(r.get(field, 'unknown') == name for r in plan) if plan is not None else None
            groups[field][name] = {'passed': passed, 'recorded_runs': len(recorded), 'planned_runs': planned,
                'missing_runs': planned - len(recorded) if planned is not None else None,
                'pass_rate': passed / planned if planned else None,
                'recorded_pass_rate': passed / len(recorded) if recorded else None,
                'coverage': 'planned' if plan is not None else 'unknown_legacy'}
    repeats = []
    for tid in sorted({r['task_id'] for r in (plan if plan is not None else rows)}):
        recorded = [r for r in rows if r['task_id'] == tid]
        passed = sum(r['status'] == 'pass' for r in recorded)
        planned = sum(r['task_id'] == tid for r in plan) if plan is not None else None
        complete = planned is not None and planned == len(recorded)
        repeats.append({'task_id': tid, 'passed': passed, 'recorded_runs': len(recorded), 'planned_runs': planned,
                        'coverage': 'complete' if complete else 'incomplete' if planned is not None else 'unknown_legacy',
                        'outcome': ('all_pass' if passed == planned else 'never_pass' if passed == 0 else 'mixed') if complete else 'incomplete' if planned is not None else 'unknown',
                        'pass_rate': passed / planned if planned else None})
    timing_rows = [run_timing(r) for r in rows]
    timings = {key: observations(r[key] for r in timing_rows)
               for key in ('agent_seconds', 'grading_seconds', 'compile_seconds', 'simulation_seconds')}
    usage = {key: observations(r.get('agent', {}).get('usage', {}).get(key)
                              for r in rows if isinstance(r.get('agent', {}).get('usage'), dict))
             for key in ('prompt_tokens', 'completion_tokens', 'total_tokens')}
    usage['cost'] = {'observed_runs': 0, 'total': None, 'mean': None}
    return {'planned_runs': result['planned_runs'], 'recorded_runs': len(rows),
            'passed': counts['pass'], 'pass_rate': counts['pass']/result['planned_runs'],
            'infra_errors': counts['infra_error'], 'missing_runs': result['planned_runs']-len(rows),
            'statuses': dict(counts), 'subgroups': groups, 'repeat_consistency': repeats,
            'failure_phases': dict(Counter(failure_phase(r) for r in rows if r['status'] != 'pass')),
            'timing': timings, 'usage': usage,
            'metric_notes': ['Subgroup planned coverage is unknown for legacy results without task_plan.',
                             'Repeat consistency is not pass@k; simulator seeds are not task repeats.',
                             'Timing totals cover observed runs only; compile time is counted once per task/repeat/check.',
                             'Missing usage and cost remain null; cost currency is not inferred or compared.']}


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
    notice=('외부 응답 계약의 fixture 검증 결과입니다. 실제 모델 또는 공식 evaluator 점수가 아닙니다.' if result.get('metadata', {}).get('fixture') is True else
            '기준 구현·오류 주입 채점기 검증 결과입니다. 실제 모델 능력 점수가 아닙니다.' if kind.startswith('fixture_') else
            'CVDP 변형 실행 경로 결과입니다. 공식 CVDP 전체 점수가 아닙니다.' if kind=='cvdp_adapted' else
            '외부 evaluator가 보고한 결과를 가져왔습니다. 원본 실행을 이 보고서 생성기가 재검증하지 않았습니다.' if kind=='upstream_import' else
            '제출 RTL / agent 실행 결과입니다. 모델·harness 식별 정보와 실행 조건을 함께 확인하십시오.')
    incomplete=s['infra_errors'] or s['missing_runs']
    md=['# HW 평가 보고서', '', result['label'], '', notice, '',f"- 종류: {kind}",f"- 성공/계획: {s['passed']}/{s['planned_runs']} ({s['pass_rate']:.1%})",f"- 인프라 오류: {s['infra_errors']}, 미기록: {s['missing_runs']}", '', '과제 성공은 요구된 모든 check/seed 통과입니다. seed 수를 독립 과제 표본 수로 취급하지 않습니다.', '']
    parts=['<h1>HW 평가 보고서</h1><h2>'+text(result['label'])+'</h2><p class="warning">'+text(notice)+'</p>']
    if incomplete:
        parts+=['<p class="warning">평가 미완료: 인프라 오류 또는 미기록 실행이 있습니다. 계획 실행 수를 분모에 유지했습니다.</p>'];md+=['**평가 미완료: 인프라 오류/미기록 실행을 확인하십시오.**','']
    parts+=['<p>과제 수: '+text(result.get('task_count','unknown'))+' · 반복: '+text(result.get('repeats','unknown'))+' · seeds: '+text(result.get('protocol',{}).get('seeds',[]))+'</p><pre>'+text(json.dumps(result.get('metadata',{}),ensure_ascii=False,indent=2))+'</pre>']
    parts+=[table(['종류','성공/계획','성공률','인프라 오류','미기록'],[[kind,f"{s['passed']}/{s['planned_runs']}",f"{s['pass_rate']:.1%}",s['infra_errors'],s['missing_runs']]])]
    def metric_table(title, headers, data):
        parts.extend(['<h2>'+text(title)+'</h2>', table(headers, data)])
        md.extend(['## '+title, '', '| '+' | '.join(headers)+' |',
                   '|'+'|'.join('---' for _ in headers)+'|'])
        md.extend('| '+' | '.join(str(v).replace('|', r'\|') for v in row)+' |' for row in data)
        md.append('')
    def display(value):
        return '알 수 없음' if value is None else value
    def rate(value):
        return '알 수 없음' if value is None else f'{value:.1%}'
    parts.append('<p>계획이 저장된 결과는 미기록 실행도 분모에 포함합니다. 구형 결과의 업무·난이도별 계획 분모는 알 수 없습니다. unknown은 난이도 미지정입니다.</p>')
    md.append('계획이 없는 구형 결과의 분류별 계획 분모는 알 수 없습니다. unknown은 난이도 미지정입니다.')
    group_csv = []
    for field, title in [('category', '업무별 결과'), ('difficulty', '난이도별 결과'), ('backend', '실행 방식별 결과')]:
        data = []
        for name, group in s['subgroups'][field].items():
            data.append([name, group['passed'], group['recorded_runs'], display(group['planned_runs']),
                         display(group['missing_runs']), rate(group['pass_rate']), group['coverage']])
            group_csv.append([field, name, group['passed'], group['recorded_runs'], group['planned_runs'],
                              group['missing_runs'], group['pass_rate'], group['coverage']])
        metric_table(title, ['분류', '성공', '기록', '계획', '미기록', '계획 대비 성공률', '분모 근거'], data)
    write_csv(out/'subgroups.csv', ['dimension', 'group', 'passed', 'recorded_runs', 'planned_runs', 'missing_runs', 'pass_rate', 'coverage'], group_csv)
    repeat_headers = ['task_id', 'passed', 'recorded_runs', 'planned_runs', 'coverage', 'outcome', 'pass_rate']
    repeat_data = [[r[k] for k in repeat_headers] for r in s['repeat_consistency']]
    metric_table('과제별 반복 일관성', repeat_headers, [[display(v) for v in row] for row in repeat_data])
    write_csv(out/'repeats.csv', repeat_headers, repeat_data)
    metric_table('실패 단계', ['단계', '실행 수'], sorted(s['failure_phases'].items()))
    metric_table('관측 시간과 사용량', ['지표', '관측 실행 수', '합계', '관측 평균'],
                 [[name, item['observed_runs'], display(item['total']), display(item['mean'])]
                  for group in ('timing', 'usage') for name, item in s[group].items()])
    parts.append('<p>반복 일관성은 pass@k가 아닙니다. 시간은 관측된 실행만 합산하며 compile은 check당 한 번 셉니다. 미측정 사용량·비용은 0이 아닙니다. 비용은 통화 계약이 없어 집계하지 않습니다.</p>')
    md.append('반복 일관성은 pass@k가 아닙니다. 시간은 관측 실행만 집계하고 compile은 check당 한 번 셉니다. 미측정 사용량·비용은 0이 아닙니다.')
    tasks=[]; checks=[]
    for t in result['tasks']:
        tasks.append([t['task_id'],t.get('repeat',1),t.get('category','unknown'),t['status'],t.get('reason',''),t.get('seconds',''),len(t.get('checks',[])),t.get('required_checks',''),t.get('agent',{}).get('status',''),t.get('agent',{}).get('seconds',''),json.dumps(t.get('agent',{}).get('usage',{}),ensure_ascii=False),t.get('difficulty','unknown'),t.get('backend','unknown'),failure_phase(t),run_timing(t)['compile_seconds'],run_timing(t)['simulation_seconds']])
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
    headers=['task_id','repeat','category','status','reason','seconds','checks','required_checks','agent_status','agent_seconds','usage','difficulty','backend','failure_phase','compile_seconds_unique','simulation_seconds']
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
    groups = defaultdict(list)
    for path in paths:
        p = Path(path); p = p/'results.json' if p.is_dir() else p
        r = json.loads(p.read_text()); s = summary(r)
        groups[(r['protocol_fingerprint'], r['kind'])].append({'label': r['label'], 'summary': s})
    parts = ['<h1>평가 구성 비교</h1><p>동일 protocol hash와 결과 종류끼리만 묶었습니다. 서로 다른 그룹의 직접 순위 비교는 지원하지 않습니다. fixture는 실제 모델 점수가 아닙니다.</p>']
    exported = []
    csv_rows = []
    for (protocol, kind), entries in groups.items():
        rows = []
        for entry in entries:
            s = entry['summary']
            row = [entry['label'], s['passed'], s['planned_runs'], f"{s['pass_rate']:.1%}", s['infra_errors'], s['missing_runs'],
                   s['timing']['agent_seconds']['total'], s['timing']['grading_seconds']['total']]
            rows.append(['알 수 없음' if v is None else v for v in row])
            csv_rows.append([protocol, kind] + row)
        parts += ['<h2>'+text(kind)+'</h2><p>protocol: '+text(protocol)+'</p>',
                  table(['구성', '성공', '계획', '성공률', '인프라', '미기록', '관측 agent 초', '관측 채점 초'], rows)]
        for entry in entries:
            parts += ['<details><summary>'+text(entry['label'])+' — 업무·난이도·반복·실패·사용량</summary><p>legacy의 계획 분모는 unknown_legacy / null입니다. 시간은 관측 실행만 합산합니다.</p><pre>'+text(json.dumps(entry['summary'], ensure_ascii=False, indent=2))+'</pre></details>']
        exported.append({'protocol_fingerprint': protocol, 'kind': kind, 'runs': entries})
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    (out/'comparison.html').write_text('<!doctype html><html lang="ko"><meta charset="utf-8"><title>HW 비교</title><style>'+STYLE+'</style><body>'+''.join(parts)+'</body></html>', encoding='utf-8')
    (out/'comparison.json').write_text(json.dumps({'groups': exported}, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    write_csv(out/'comparison.csv', ['protocol_fingerprint', 'kind', 'label', 'passed', 'planned_runs', 'pass_rate', 'infra_errors', 'missing_runs', 'agent_seconds_observed', 'grading_seconds_observed'], csv_rows)
