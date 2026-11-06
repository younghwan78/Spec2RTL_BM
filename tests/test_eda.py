import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from hwbench import eda
from hwbench.common import ROOT, load_suite
from hwbench.grader import grade
from hwbench.repository import file_hash


class EDATests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = tempfile.TemporaryDirectory(); cls.root = Path(cls.base.name)
        suite = load_suite(); suite['tasks'] = [t for t in suite['tasks'] if t['id'] == 'counter']
        task = suite['tasks'][0]
        import shutil
        shutil.copytree(ROOT / 'benchmarks/core/tasks/counter/reference', cls.root / 'submissions/counter')
        cls.result = cls.root / 'functional'
        grade(suite, cls.root / 'submissions', cls.result, kind='fixture_reference', seeds=[1], sandbox='required')
        assert json.loads((cls.result / 'results.json').read_text())['tasks'][0]['status'] == 'pass'

    @classmethod
    def tearDownClass(cls): cls.base.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup); self.work = Path(self.temp.name)
        self.c = json.loads((ROOT / 'configs/eda-mock.example.json').read_text())
        self.c['assets'] = {k: str((ROOT / 'configs' / v).resolve()) for k,v in self.c['assets'].items()}

    def queue(self, name='queue', timeout=2, budget=10):
        config = self.work / (name + '.json'); config.write_text(json.dumps(self.c))
        out = self.work / name; eda.plan(self.result, config, out, timeout, budget); return out

    def test_pass_snapshot_required_and_mutation_rejected(self):
        q = self.queue(); root,value=eda.load(q)
        j=value['jobs'][0]; (q / 'sources' / j['job_id'] / 'rtl/counter.sv').write_text('bad')
        with self.assertRaises(ValueError): eda.run(q)
        bad=copy.deepcopy(json.loads((self.result / 'results.json').read_text())); bad['kind']='upstream_import'
        f=self.work/'bad.json'; f.write_text(json.dumps(bad))
        with self.assertRaises(ValueError): eda.plan(f,self.work/'queue.json',self.work/'badq')

    def test_full_export_run_import_report_compare(self):
        q=self.queue(); sent=self.work/'sent'; eda.export(q,sent); eda.verify_transfer(sent)
        eda.run(sent); returned=self.work/'returned'; eda.export(sent,returned); eda.import_results(q,returned)
        s=eda.report(q,self.work/'report')
        self.assertEqual(s['counts']['valid_mock'],1); self.assertEqual(s['counts']['valid_measured'],0)
        self.assertEqual(s['rows'][0]['evidence_level'],'externally_reported')
        self.assertIsNone(s['rows'][0]['license_wait_seconds'])
        c=eda.compare(q,sent,self.work/'compare'); self.assertEqual(c['matched'],1)
        self.assertEqual(c['pairs'][0]['ratios_candidate_over_baseline']['area_um2'],1)

    def test_cache_integrity_and_conditions(self):
        cache=self.work/'cache'; a=self.queue('a'); eda.run(a,cache)
        b=self.queue('b'); eda.run(b,cache); _,q=eda.load(b)
        self.assertEqual(q['jobs'][0]['attempts'][0]['kind'],'cache')
        entry=next(x for x in cache.iterdir() if x.is_dir()); (entry/'synthetic-report.txt').write_text('tamper')
        c=self.queue('c'); eda.run(c,cache); _,q=eda.load(c)
        self.assertTrue(q['jobs'][0]['cache_rejected']); self.assertEqual(q['jobs'][0]['attempts'][0]['kind'],'local_wrapper')
        bad=eda.read(entry/'response.json');bad['status']='infra_error';eda.save(entry/'response.json',bad)
        e=self.queue('e');eda.run(e,cache);_,state=eda.load(e);self.assertTrue(state['jobs'][0]['cache_rejected'])
        self.c['workload']['id']='new-workload'; d=self.queue('d'); eda.run(d,cache)
        self.assertEqual(eda.compare(a,d,self.work/'compare')['matched'],0)

    def test_invalid_metric_unit_mode_source_and_raw_reports(self):
        q=self.queue(); eda.run(q); root,state=eda.load(q); j=state['jobs'][0]; p=root/j['result_dir']; value=eda.read(p/'response.json')
        for field, val in [('mode','measured'), ('source_hashes',{}), ('units',{'area_um2':'mm2'}), ('metrics',{'area_um2':float('nan'),'delay_ns':1,'power_mw':1})]:
            bad=copy.deepcopy(value); bad[field]=val
            with self.assertRaises(ValueError): eda.validate_response(j,bad,p)
        (p/'synthetic-report.txt').write_text('changed')
        with self.assertRaises(ValueError): eda.summary(q)

    def test_lock_and_interruption_budget_retention(self):
        q=self.queue(budget=2); root,state=eda.load(q)
        with eda.locked(q):
            with self.assertRaises(ValueError): eda.run(q)
        state['jobs'][0]['status']='running'; state['jobs'][0]['attempts']=[{'kind':'local_wrapper','reserved_seconds':2,'seconds':None}]; state['charged_seconds']=2
        eda.save(q/'queue.json',state)
        with self.assertRaises(ValueError): eda.run(q)
        recovered=eda.recover(q); self.assertEqual(recovered['jobs'][0]['status'],'interrupted'); self.assertEqual(recovered['charged_seconds'],2)
        eda.recover(q,retry=True); r=eda.run(q); self.assertEqual(r['jobs'][0]['status'],'budget_exhausted')

    def test_timeout_kills_descendants_and_keeps_evidence(self):
        wrapper=self.work/'slow.py'; pidfile=self.work/'child.pid'
        wrapper.write_text('import subprocess,time\np=subprocess.Popen(["sleep","60"])\nopen('+repr(str(pidfile))+',"w").write(str(p.pid))\ntime.sleep(60)\n')
        self.c['assets']['wrapper']=str(wrapper); q=self.queue(timeout=.15,budget=.15)
        state=eda.run(q); self.assertEqual(state['jobs'][0]['status'],'timeout')
        self.assertGreater(state['charged_seconds'],0)
        pid=int(pidfile.read_text()); stat=Path('/proc')/str(pid)/'stat'
        self.assertTrue(not stat.exists() or stat.read_text().split()[2]=='Z')

    def test_measured_request_cannot_use_mock_cache_or_wrapper(self):
        cache=self.work/'cache'; a=self.queue('a'); eda.run(a,cache)
        self.c['mode']='measured'; b=self.queue('b')
        with self.assertRaisesRegex(ValueError, 'offline resource kit'): eda.run(b,cache)
        self.assertEqual(eda.load(b)[1]['jobs'][0]['attempts'], [])
        from hwbench import offline
        spec = self.work/'resources.json'; eda.save(spec, {'schema_version':1, 'profiles':{'eda':['tools','config']}, 'resources':[
            {'id':'tools','role':'tool_installation','path':str(self.work/'b.json'),'destination':'tools.json'},
            {'id':'config','role':'configuration','path':str(self.work/'b.json'),'destination':'config.json'}]})
        offline.pack(spec,self.work/'kit'); r=eda.run(b,cache,kit=self.work/'kit')
        self.assertEqual(r['jobs'][0]['status'],'infra_error'); self.assertEqual(len(r['jobs'][0]['attempts']),1)
        self.assertEqual(eda.summary(b)['counts']['valid_measured'],0)

    def test_transfer_tamper_and_identity_rejected(self):
        a=self.queue('a'); eda.run(a); transfer=self.work/'transfer'; eda.export(a,transfer)
        self.c['workload']['id']='other'; b=self.queue('b')
        with self.assertRaises(ValueError): eda.import_results(b,transfer)
        (transfer/'assets/library').write_text('changed')
        with self.assertRaises(ValueError): eda.verify_transfer(transfer)

    def test_transfer_containment_rejected_without_mutation(self):
        q = self.queue(); before = eda.tree_hashes(q)
        with self.assertRaises(ValueError): eda.export(q, q / 'nested')
        with self.assertRaises(ValueError): eda.import_results(q, q)
        with self.assertRaises(ValueError): eda.import_results(q, q / 'nested')
        self.assertEqual(eda.tree_hashes(q), before)

    def test_multijob_import_prevalidation_and_interrupted_commit_retry(self):
        from unittest.mock import patch
        import shutil
        original = self.result; functional = self.work/'functional'; shutil.copytree(original,functional)
        r=eda.read(functional/'results.json'); second=copy.deepcopy(r['tasks'][0]);second['repeat']=2
        r['tasks'].append(second);r['task_plan'].append({**r['task_plan'][0],'repeat':2});r['planned_runs']=2;r['repeats']=2
        eda.save(functional/'results.json',r);self.result=functional
        q=self.queue('multi'); initial=(q/'queue.json').read_bytes()
        eda.export(q,self.work/'sent');eda.run(self.work/'sent');eda.export(self.work/'sent',self.work/'returned')
        returned=self.work/'returned'; incoming=eda.read(returned/'queue.json'); response=returned/incoming['jobs'][1]['result_dir']/'response.json'
        valid=eda.read(response);bad=copy.deepcopy(valid);bad['units']={'area_um2':'mm2'};eda.save(response,bad)
        def rehash():
            hashes=eda.tree_hashes(returned);hashes.pop('TRANSFER_SHA256.json',None);hashes.pop('.lock',None);eda.save(returned/'TRANSFER_SHA256.json',hashes)
        rehash()
        with self.assertRaises(ValueError):eda.import_results(q,returned)
        self.assertEqual((q/'queue.json').read_bytes(),initial);self.assertFalse((q/'imported-transfers').exists())
        eda.save(response,valid);rehash()
        real_save=eda.save
        def crash(path,value):
            if Path(path)==q/'queue.json':raise OSError('simulated commit interruption')
            return real_save(path,value)
        with patch.object(eda,'save',side_effect=crash):
            with self.assertRaises(OSError):eda.import_results(q,returned)
        self.assertEqual((q/'queue.json').read_bytes(),initial)
        eda.import_results(q,returned);self.assertEqual(eda.summary(q)['counts']['valid_mock'],2)

    def test_executable_wrapper_mode_is_preserved(self):
        wrapper=self.work/'direct-wrapper'; wrapper.write_text('#!/usr/bin/env python3\n'+(ROOT/'scripts/eda_mock_wrapper.py').read_text()); wrapper.chmod(0o755)
        self.c['assets']['wrapper']=str(wrapper);self.c['argv']=['{asset:wrapper}','{request}','{response}']
        q=self.queue();self.assertTrue(os.access(q/'assets/wrapper',os.X_OK));eda.run(q)
        self.assertEqual(eda.summary(q)['counts']['valid_mock'],1)

    def test_asset_mutation_invalidates_run_and_missing_provenance(self):
        a=self.queue(); (a/'assets/workload').write_text('different')
        with self.assertRaises(ValueError): eda.run(a)
        self.c['tool']['version']='unknown'
        with self.assertRaises(ValueError): self.queue('invalid')

    def test_owner_death_reaps_tool_group_before_recovery(self):
        import time, signal
        wrapper=self.work/'orphan.py'; pidfile=self.work/'orphan.pid'
        wrapper.write_text('import subprocess,time,os\np=subprocess.Popen(["sleep","60"])\nopen('+repr(str(pidfile))+',"w").write(str(os.getpid())+" "+str(p.pid))\ntime.sleep(60)\n')
        self.c['assets']['wrapper']=str(wrapper); q=self.queue(timeout=5,budget=10)
        worker=subprocess.Popen([sys.executable,'-m','hwbench','eda-run',str(q)],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            deadline=time.time()+3
            while not pidfile.exists() and time.time()<deadline: time.sleep(.02)
            self.assertTrue(pidfile.exists()); pids=[int(x) for x in pidfile.read_text().split()]
            worker.kill(); worker.wait(timeout=3)
            deadline=time.time()+3
            while time.time()<deadline:
                alive=[pid for pid in pids if (Path('/proc')/str(pid)/'stat').exists() and (Path('/proc')/str(pid)/'stat').read_text().split()[2]!='Z']
                if not alive: break
                time.sleep(.02)
            self.assertFalse(alive)
            r=eda.recover(q); self.assertEqual(r['jobs'][0]['status'],'interrupted'); self.assertEqual(r['charged_seconds'],5)
        finally:
            if worker.poll() is None:worker.kill();worker.wait()

    def test_argv_and_functional_protocol_change_comparison(self):
        a=self.queue('a');eda.run(a)
        self.c['argv'].append('--different-setting'); b=self.queue('b');eda.run(b)
        self.assertEqual(eda.compare(a,b,self.work/'cmp')['matched'],0)
        state=eda.read(b/'queue.json');self.assertNotEqual(eda.read(a/'queue.json')['jobs'][0]['input_fingerprint'],state['jobs'][0]['input_fingerprint'])
        original=self.result
        import shutil
        other=self.work/'other';shutil.copytree(original,other)
        r=eda.read(other/'results.json');r['protocol_fingerprint']='different-functional-protocol';eda.save(other/'results.json',r)
        self.result=other
        c=self.queue('c');eda.run(c)
        self.assertEqual(eda.compare(b,c,self.work/'cmp2')['matched'],0)

    def test_functional_fail_and_unrequested_coverage(self):
        c=self.work/'config.json'; c.write_text(json.dumps(self.c))
        r=copy.deepcopy(json.loads((self.result/'results.json').read_text())); r['tasks'][0]['status']='fail'
        r['task_plan'].append({'task_id':'unrequested','repeat':1,'category':'generation','difficulty':'unknown','backend':'native'});r['planned_runs']=2
        f=self.work/'fail.json'; f.write_text(json.dumps(r)); q=self.work/'failed'; eda.plan(f,c,q)
        s=eda.summary(q); self.assertEqual(s['counts']['functional_planned'],2); self.assertEqual(s['counts']['requested'],1); self.assertEqual(s['counts']['eligible'],0)
        self.assertEqual([x['status'] for x in s['rows']],['skipped_functional_fail','not_requested'])

if __name__=='__main__': unittest.main()
