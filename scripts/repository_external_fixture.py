"""Normalized response contract fixture. Does not run Docker or assess model ability."""
import hashlib
import json
from pathlib import Path
import sys

request = json.loads(Path(sys.argv[1]).read_text())
submission = json.loads((Path(request['submission']) / 'submission.json').read_text())
response = Path(request['response'])
raw = response.parent / 'fixture-report.txt'
raw.write_text('FIXTURE ONLY: tests the external response contract; no official evaluator was executed.\n')
result = {'schema_version': 1, 'prepared_fingerprint': request['prepared_fingerprint'],
          'submission_fingerprint': request['submission_fingerprint'], 'evaluator_revision': 'fixture-only-v1',
          'image_digest': 'sha256:' + '0' * 64, 'protocol_id': 'fixture-normalized-response',
          'reports': {raw.name: hashlib.sha256(raw.read_bytes()).hexdigest()},
          'tasks': [{'task_id': t['task_id'], 'source_hashes': t['source_hashes'], 'status': 'unresolved',
                     'reason': 'Fixture contract only; no functional evaluator executed'} for t in submission['tasks']]}
response.write_text(json.dumps(result, indent=2)+'\n')
