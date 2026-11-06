"""Linux local EDA watchdog: reap tool groups even when the queue owner dies."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def identity(pid):
    try: return Path('/proc/' + str(pid) + '/stat').read_text().rsplit(')', 1)[1].split()[19]
    except (OSError, IndexError): return None


def save(path, value):
    p=Path(path); tmp=p.with_suffix('.tmp'); tmp.write_text(json.dumps(value, allow_nan=False)); os.replace(tmp,p)


def main():
    cfg=json.loads(Path(sys.argv[1]).read_text()); start=time.monotonic(); state=Path(cfg['state']); log=Path(cfg['log'])
    record={'argv':cfg['argv'], 'cwd':cfg['cwd'], 'log':str(log), 'returncode':None, 'timeout':False, 'output_limit':False, 'owner_lost':False}
    owner_ok=lambda: identity(cfg['owner_pid']) == cfg['owner_identity']
    if not owner_ok(): return 2
    meta={'supervisor_pid':os.getpid(),'supervisor_identity':identity(os.getpid()),'state':'starting'};save(state,meta)
    proc=None
    try:
        with log.open('wb') as stream:
            proc=subprocess.Popen(cfg['argv'],cwd=cfg['cwd'],stdout=stream,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True)
            meta.update(state='running',tool_pid=proc.pid,tool_identity=identity(proc.pid));save(state,meta)
            while proc.poll() is None:
                record['owner_lost']=not owner_ok()
                record['timeout']=time.monotonic()-start >= cfg['timeout']
                record['output_limit']=log.stat().st_size > 2_000_000
                if record['owner_lost'] or record['timeout'] or record['output_limit']: break
                time.sleep(.02)
            try: os.killpg(proc.pid,signal.SIGKILL)
            except ProcessLookupError: pass
            record['returncode']=proc.wait()
        if log.stat().st_size > 2_000_000:
            record['output_limit']=True
            with log.open('r+b') as f:f.truncate(2_000_000)
    except OSError as exc:
        record['error']=str(exc)
    finally:
        if proc:
            try:os.killpg(proc.pid,signal.SIGKILL)
            except ProcessLookupError:pass
        record['seconds']=round(time.monotonic()-start,6);save(cfg['result'],record)
        meta['state']='finished';save(state,meta)
    return 0

if __name__=='__main__':raise SystemExit(main())
