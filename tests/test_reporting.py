import copy
import json
import tempfile
import unittest
from pathlib import Path
from hwbench.reporting import write_report, summary, compare_reports

class ReportingTests(unittest.TestCase):
 def fixture(self):
  return dict(schema_version=1,label='<script>alert(1)</script>',kind='fixture_reference',protocol_fingerprint='abc',planned_runs=2,tasks=[dict(task_id='a',category='repair',status='pass',required_checks=1,checks=[dict(id='x',seed=1,status='pass',completion_verified=True,compile=dict(returncode=0,timeout=False,output_limit=False),simulation=dict(returncode=0,timeout=False,output_limit=False))])])
 def test_outputs_and_escape(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);write_report(self.fixture(),p)
   self.assertEqual(summary(self.fixture())['pass_rate'],.5)
   s=(p/'report.html').read_text();self.assertNotIn('<script>',s);self.assertIn('평가 미완료',s);self.assertIn('실제 모델 능력 점수가 아닙니다',s)
   for f in ['report.md','tasks.csv','checks.csv','summary.json']:self.assertTrue((p/f).exists())
 def test_false_pass_rejected(self):
  r=self.fixture();r['tasks'][0]['checks'][0]['status']='fail'
  with self.assertRaises(ValueError):summary(r)
 def test_missing_tool_evidence_rejected(self):
  r=self.fixture();r['tasks'][0]['checks'][0].pop('simulation')
  with self.assertRaises(ValueError):summary(r)
 def test_missing_completion_rejected(self):
  r=self.fixture();r['tasks'][0]['checks'][0].pop('completion_verified')
  with self.assertRaises(ValueError):summary(r)
 def test_relocated_log(self):
  with tempfile.TemporaryDirectory() as d:
   base=Path(d);src=base/'src';src.mkdir();out=base/'new';(src/'failed.log').write_text('failure <unsafe>')
   r=self.fixture();r['tasks'][0]['status']='fail';c=r['tasks'][0]['checks'][0];c['status']='fail';c['simulation']['log']='failed.log'
   write_report(r,out,source_root=src)
   self.assertTrue((out/'evidence'/'failed.log').is_file())
   report=(out/'report.html').read_text();self.assertIn('evidence/failed.log',report);self.assertIn('failure &lt;unsafe&gt;',report)
   self.assertEqual(c['simulation']['log'],'failed.log')
 def test_false_tool_pass_rejected(self):
  r=self.fixture();r['tasks'][0]['checks'][0]['compile']={'returncode':1}
  with self.assertRaises(ValueError):summary(r)
 def test_agent_details(self):
  r=self.fixture();r['tasks'][0]['agent']={'status':'ok','seconds':1.2,'usage':{'total_tokens':42}}
  with tempfile.TemporaryDirectory() as d:
   write_report(r,Path(d));self.assertIn('total_tokens',(Path(d)/'report.html').read_text());self.assertIn('agent_seconds',(Path(d)/'tasks.csv').read_text())
 def test_duplicate_rejected(self):
  r=self.fixture();r['tasks']*=2
  with self.assertRaises(ValueError):summary(r)
 def test_upstream_no_checks(self):
  r=self.fixture();r['kind']='upstream_import';r['tasks'][0]['checks']=[]
  self.assertEqual(summary(r)['passed'],1)
 def test_bad_denominator(self):
  r=self.fixture();r['planned_runs']=0
  with self.assertRaises(ValueError):summary(r)
 def test_comparison_groups(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);a=self.fixture();b=copy.deepcopy(a);b['kind']='submission';b['label']='real'
   for name,r in [('a',a),('b',b)]: (p/name).write_text(json.dumps(r))
   compare_reports([p/'a',p/'b'],p)
   self.assertIn('submission',(p/'comparison.html').read_text())
 def test_external_log_not_read(self):
  r=self.fixture();r['tasks'][0]['checks'][0]['compile']['log']='/etc/passwd'
  with tempfile.TemporaryDirectory() as d:
   write_report(r,Path(d));s=(Path(d)/'report.html').read_text();self.assertNotIn('root:x:',s);self.assertIn('외부 로그',s)
if __name__=='__main__':unittest.main()
