from pathlib import Path
import subprocess,json,tempfile
r=Path(__file__).parent
s=json.loads((r/'suite.json').read_text());count=0
with tempfile.TemporaryDirectory() as d:
 for t in s['tasks']:
  p=r/t['path']
  for variant in ['reference']+[m['path'] for m in t['mutants']]:
   failed=[]
   for c in t['checks']:
    cmd=['iverilog','-g2012','-s','tb','-o',d+'/a']+[str(p/variant/f)for f in t['files']]+[str(p/c['tb'])]
    x=subprocess.run(cmd,capture_output=True,text=True);assert x.returncode==0,(t['id'],variant,x.stderr)
    for seed in [1,7,42]:
     x=subprocess.run(['vvp',d+'/a',f'+SEED={seed}'],capture_output=True,text=True,timeout=10)
     ok=x.returncode==0 and 'HWBENCH_PASS' in x.stdout
     if variant=='reference':assert ok,(t['id'],c['id'],seed,x.stdout,x.stderr)
     elif not ok:failed.append(c['id'])
     count+=1
   if variant!='reference':
    m=next(m for m in t['mutants'] if m['path']==variant)
    assert all(c in failed for c in m['expected_fail_checks']),(t['id'],variant,failed)
   print(t['id'],variant,'PASS' if variant=='reference' else 'DETECTED',sorted(set(failed)))
print('Verified simulations:',count)
