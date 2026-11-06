"""Synthetic EDA contract fixture. Never presents these values as measured PPA."""
import hashlib
import json
from pathlib import Path
import sys
import time

request = json.loads(Path(sys.argv[1]).read_text())
out = Path(sys.argv[2]); out.parent.mkdir(parents=True, exist_ok=True)
if request['condition']['mode'] != 'mock':
    raise SystemExit('Mock wrapper refuses measured jobs')
canonical = lambda x: json.dumps(x, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
sha = lambda x: hashlib.sha256(x).hexdigest()
activity = out.parent / 'candidate-activity.txt'
activity.write_text('Synthetic activity, not SAIF: ' + json.dumps(request['source_hashes'], sort_keys=True))
raw = out.parent / 'synthetic-report.txt'; raw.write_text('MOCK area=100 um^2 delay=2 ns power=3 mW; no EDA executed\n')
value = {k: request[k] for k in ('job_id', 'input_fingerprint', 'condition_fingerprint', 'source_hashes')}
value.update(schema_version=1, mode='mock', stage=request['condition']['stage'], status='ok', reason='Synthetic contract fixture',
             metrics={'area_um2': 100.0, 'delay_ns': 2.0, 'power_mw': 3.0}, units={'area_um2': 'um^2', 'delay_ns': 'ns', 'power_mw': 'mW'},
             quality={'lint': 'not_requested', 'xprop': 'not_requested'}, license_wait_seconds=None,
             reports={raw.name: sha(raw.read_bytes()), activity.name: sha(activity.read_bytes())},
             activity={'source_fingerprint': sha(canonical(request['source_hashes'])), 'workload_fingerprint': sha(canonical(request['condition']['workload'])), 'report': activity.name})
out.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
