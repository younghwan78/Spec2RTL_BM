import contextlib
import http.server
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from hwbench.cli import main, verify_bundle
from hwbench.common import DEFAULT_SUITE, execute, load_suite, task_base, within
from hwbench.execution import export_suite, openai_completion, parse_files, run
from hwbench.grader import grade_task, inspect_rtl
from hwbench.reporting import summary
from hwbench.upstream import import_hwe


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.root = Path(self.temp.name)
        self.suite = load_suite();self.task = self.suite['tasks'][0]
        self.suite['tasks'] = [self.task]

    def tearDown(self): self.temp.cleanup()

    def candidate(self, variant='reference'):
        target = self.root / 'candidate'
        shutil.copytree(task_base(self.suite, self.task) / variant, target)
        return target

    def grade(self, path, timeout=3):
        return grade_task(self.suite, self.task, path, self.root/'logs', [1], timeout, False)

    def test_positive_and_real_mutant(self):
        self.assertEqual(self.grade(self.candidate())['status'], 'pass')
        path = self.root/'bad';shutil.copytree(task_base(self.suite,self.task)/'mutants/wrap',path)
        row=self.grade(path)
        self.assertEqual(row['status'],'fail')
        self.assertTrue(all(c['compile']['returncode']==0 for c in row['checks']))
        self.assertTrue(any(c.get('simulation',{}).get('returncode')==1 for c in row['checks']))

    def test_missing_file(self):
        self.assertEqual(self.grade(self.root/'absent')['status'],'invalid_submission')

    def test_symlink_rejected(self):
        p=self.root/'candidate/rtl';p.mkdir(parents=True)
        (p/'saturating_add.sv').symlink_to(task_base(self.suite,self.task)/'reference/rtl/saturating_add.sv')
        self.assertEqual(self.grade(p.parent)['status'],'invalid_submission')

    def test_early_finish_forged_pass_and_testbench_control_rejected(self):
        for src in ['module x; initial $finish; endmodule', 'module x; initial $display("HWBENCH_PASS"); endmodule',
                    'module x; initial force tb.x=1; endmodule','`include "/tmp/a"', 'module tb; endmodule']:
            with self.subTest(src=src),self.assertRaises(ValueError): inspect_rtl(src)

    def test_path_traversal(self):
        for path in ['../escape','/etc/passwd','a/../../b','a\\b','a//b']:
            with self.subTest(path=path),self.assertRaises(ValueError):within(self.root,path)

    def test_compile_failure_is_not_infra_or_pass(self):
        p=self.candidate();(p/self.task['files'][0]).write_text('module broken SYNTAX')
        row=self.grade(p);self.assertEqual(row['status'],'fail')
        self.assertTrue(all(c['reason']=='compile_error' for c in row['checks']))

    def test_simulation_hang_timeout(self):
        p=self.candidate();f=p/self.task['files'][0]
        f.write_text(f.read_text().replace('endmodule','initial begin forever #0; end\nendmodule'))
        row=self.grade(p,0.3)
        self.assertEqual(row['status'],'fail')
        self.assertTrue(any(c['reason']=='simulation_timeout' for c in row['checks']))

    def test_process_timeout_and_output_limit(self):
        row=execute([sys.executable,'-c','import time;time.sleep(10)'],self.root,self.root/'sleep.log',0.1)
        self.assertTrue(row['timeout']);self.assertNotEqual(row['returncode'],0)
        row=execute([sys.executable,'-c','print("x"*100000)'],self.root,self.root/'big.log',1,max_bytes=1000)
        self.assertTrue(row['output_limit']);self.assertLessEqual((self.root/'big.log').stat().st_size,1000)

    def test_nonfinite_timeouts_rejected(self):
        for value in (float('nan'),float('inf'),-1,0):
            with self.subTest(value=value),self.assertRaises(ValueError):
                execute([sys.executable,'-c','pass'],self.root,self.root/'nan.log',value)
            with self.subTest(value=value),self.assertRaises(ValueError):
                run(self.suite,{'type':'command','argv':['true']},self.root/'nan',agent_timeout=value)

    def test_sandbox_custom_tool_is_infra(self):
        p=self.candidate()
        with patch('hwbench.grader.shutil.which',return_value='/opt/private/iverilog'):
            row=grade_task(self.suite,self.task,p,self.root/'sandbox-logs',[1],3,True)
        self.assertEqual(row['status'],'infra_error')

    def test_missing_binary_is_infra(self):
        row=execute(['/no/such/binary'],self.root,self.root/'missing.log',1)
        self.assertIn('error',row)

    def test_export_excludes_answers_and_grader(self):
        out=self.root/'export';export_suite(self.suite,out)
        files={str(x.relative_to(out)) for x in out.rglob('*') if x.is_file()}
        self.assertEqual(files, {'manifest.json','saturating_add/prompt.md','saturating_add/task.json','saturating_add/rtl/saturating_add.sv'})
        with self.assertRaises(ValueError):export_suite(self.suite,out)

    def test_testbench_change_changes_fingerprint(self):
        copied=self.root/'suite';shutil.copytree(DEFAULT_SUITE.parent,copied)
        first=load_suite(copied/'suite.json')['fingerprint']
        checker=copied/'tasks/saturating_add/checks/boundary.sv'
        checker.write_text(checker.read_text()+'\n// altered checker\n')
        self.assertNotEqual(first,load_suite(copied/'suite.json')['fingerprint'])

    def test_malformed_manifest_rejected(self):
        p=self.root/'suite.json';p.write_text('{"schema_version":1,"tasks":[]}')
        with self.assertRaises(ValueError):load_suite(p)

    def test_strict_model_output(self):
        allowed=['rtl/a.sv']
        self.assertEqual(parse_files('```json\n{"files":{"rtl/a.sv":"module a;endmodule"}}\n```',allowed), {'rtl/a.sv':'module a;endmodule'})
        for text in ['{}','{"files":{"../a":"x"}}','{"files":{"rtl/a.sv":12}}']:
            with self.assertRaises(ValueError):parse_files(text,allowed)

    def test_real_command_adapter_smoke(self):
        source=(task_base(self.suite,self.task)/'reference/rtl/saturating_add.sv').read_text()
        script=self.root/'agent.py'
        script.write_text('from pathlib import Path\nPath("rtl/saturating_add.sv").write_text('+repr(source)+')\n')
        cfg={'type':'command','kind':'fixture_adapter','label':'scripted-positive-control','harness':'test-script',
             'argv':[sys.executable,str(script)]}
        result=run(self.suite,cfg,self.root/'run',seeds=[1],sandbox='off')
        self.assertEqual(summary(result)['passed'],1);self.assertEqual(result['kind'],'fixture_adapter')
        self.assertIn('agent',result['tasks'][0])
        self.assertFalse(Path(result['tasks'][0]['checks'][0]['compile']['log']).is_absolute())

    def test_agent_timeout_is_failure_and_missing_command_is_infra(self):
        cfg={'type':'command','argv':[sys.executable,'-c','import time;time.sleep(10)']}
        r=run(self.suite,cfg,self.root/'timeout',seeds=[1],agent_timeout=.1,sandbox='off')
        self.assertEqual(r['tasks'][0]['status'],'timeout')
        cfg['argv']=['/no/such/agent'];r=run(self.suite,cfg,self.root/'missing',seeds=[1],sandbox='off')
        self.assertEqual(r['tasks'][0]['status'],'infra_error')

    def test_generation_budget_changes_comparison_protocol(self):
        cfg={'type':'command','argv':['/no/agent'],'max_tokens':100}
        a=run(self.suite,cfg,self.root/'a',seeds=[1],sandbox='off')
        cfg['max_tokens']=200
        b=run(self.suite,cfg,self.root/'b',seeds=[1],sandbox='off')
        self.assertNotEqual(a['protocol_fingerprint'],b['protocol_fingerprint'])

    def test_local_http_adapter_mock_not_real_model(self):
        source=(task_base(self.suite,self.task)/'reference/rtl/saturating_add.sv').read_text()
        requests=[]
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(handler):
                requests.append(json.loads(handler.rfile.read(int(handler.headers['Content-Length']))))
                body=json.dumps({'choices':[{'message':{'content':json.dumps({'files':{'rtl/saturating_add.sv':source}})}}],
                                 'usage':{'prompt_tokens':1,'completion_tokens':2}}).encode()
                handler.send_response(200);handler.end_headers();handler.wfile.write(body)
            def log_message(self,*args): pass
        server=http.server.HTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            cfg={'type':'openai','kind':'fixture_adapter','base_url':f'http://127.0.0.1:{server.server_port}/v1',
                 'model':'mock-control','label':'mock-http'}
            r=run(self.suite,cfg,self.root/'http',seeds=[1],sandbox='off')
            self.assertEqual(summary(r)['passed'],1)
            self.assertEqual(r['tasks'][0]['agent']['usage']['completion_tokens'],2)
            self.assertNotIn('HWBENCH_PASS',requests[0]['messages'][1]['content'])
        finally:server.shutdown();server.server_close();thread.join()

    def test_http_total_deadline_slow_stream(self):
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(handler):
                handler.rfile.read(int(handler.headers['Content-Length']))
                handler.send_response(200);handler.end_headers()
                try:
                    for i in range(100):
                        handler.wfile.write(b'    ');handler.wfile.flush();time.sleep(.03)
                except (BrokenPipeError,ConnectionResetError):pass
            def log_message(self,*args):pass
        server=http.server.HTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        export_suite(self.suite,self.root/'prompts')
        cfg={'base_url':f'http://127.0.0.1:{server.server_port}/v1','model':'mock'}
        try:
            start=time.monotonic()
            row=openai_completion(cfg,self.root/'prompts/saturating_add',self.task,.25,self.root/'http-logs')
            self.assertEqual(row['status'],'timeout')
            self.assertLess(time.monotonic()-start,1.5)
        finally:server.shutdown();server.server_close();thread.join()

    def test_hwe_import_groups_and_expected_ids(self):
        p=self.root/'hwe.json';obj={'resolved_ids':['a'],'unresolved_ids':['b'],'empty_patch_ids':['c'],'error_ids':['d']}
        p.write_text(json.dumps(obj));r=import_hwe(p,self.root/'import','demo','hwe-test',['a','b','c','d'])
        self.assertEqual(summary(r)['pass_rate'],.25);self.assertEqual(summary(r)['infra_errors'],1)
        with self.assertRaises(ValueError):import_hwe(p,self.root/'bad','demo','hwe-test',['a'])
        obj['error_ids']=['a'];p.write_text(json.dumps(obj))
        with self.assertRaises(ValueError):import_hwe(p,self.root/'duplicate','demo','test')

    def test_cli_exit_for_bad_config_and_invalid_seeds(self):
        with contextlib.redirect_stderr(io.StringIO()):
            code=main(['grade','--submissions',str(self.root),'--out',str(self.root/'out'),'--seeds','1,1'])
        self.assertEqual(code,2)


if __name__=='__main__':unittest.main()
