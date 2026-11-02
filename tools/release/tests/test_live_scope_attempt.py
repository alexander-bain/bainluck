import importlib.util
import unittest
import sys
import os
import subprocess
import yaml
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
FILE=ROOT/'tools/release/verify_fast.py'

class ScopeAttempt(unittest.TestCase):
    def module(self):
        self.assertTrue(FILE.exists(),'fresh fast eligibility verifier is missing')
        sys.path.insert(0,str(FILE.parent))
        spec=importlib.util.spec_from_file_location('verify_fast',FILE)
        loaded=importlib.util.module_from_spec(spec);spec.loader.exec_module(loaded)
        return loaded

    def test_old_scope_attempt_is_refused_even_if_tests_were_selected(self):
        m=self.module()
        with self.assertRaises(ValueError):m.verify_attempt('1','2')
        m.verify_attempt('2','2')

    def test_same_attempt_rechecks_policy_receipt_and_removed_label(self):
        m=self.module()
        event={'pull_request':{'number':17}}
        pr={'number':17,'state':'open','head':{'sha':'abc'},'base':{'ref':'master'},'labels':[]}
        receipt={'id':9,'payload':{'authority':'release-loop-policy-v1','fast_enabled':True,'master_sha':'a'*40}}
        status={'id':20,'state':'success'}
        def read(path):
            if '/statuses?' in path:return [status]
            if '/deployments?' in path:return [receipt]
            return pr
        with self.assertRaises(ValueError):m.verify_eligibility('pull_request',event,'abc',read)
        pr['labels']=[{'name':'live-path'}]
        m.verify_eligibility('pull_request',event,'abc',read)
        receipt['payload']['fast_enabled']=False
        with self.assertRaises(ValueError):m.verify_eligibility('pull_request',event,'abc',read)

    def test_missing_failed_or_newer_disabled_policy_cannot_admit_fast_gate(self):
        m=self.module()
        event={'pull_request':{'number':17}}
        pr={'number':17,'state':'open','head':{'sha':'abc'},'base':{'ref':'master'},'labels':[{'name':'live-path'}]}
        enabled={'id':9,'payload':{'authority':'release-loop-policy-v1','fast_enabled':True,'master_sha':'a'*40}}
        disabled={'id':10,'payload':{'authority':'release-loop-policy-v1','fast_enabled':False,'master_sha':'a'*40}}
        for rows,statuses in [([],[]),([{'id':10,'payload':{'fast_enabled':True}}],[]),([enabled,disabled],[])]:
            def read(path):
                if '/statuses?' in path:return statuses
                if '/deployments?' in path:return rows
                return pr
            with self.subTest(rows=rows,statuses=statuses),self.assertRaises(ValueError):
                m.verify_eligibility('pull_request',event,'abc',read)
        def failure(path):raise RuntimeError('policy API unavailable')
        with self.assertRaises(RuntimeError):m.verify_eligibility('pull_request',event,'abc',failure)

    def test_retained_scope_fails_every_marker_and_deploy_barrier(self):
        jobs=yaml.safe_load((ROOT/'.github/workflows/ci.yml').read_text())['jobs']
        for name in ['fast-gate','backend-tests','e2e-contract','golden-baseline-floor','deploy']:
            guard=jobs[name]['steps'][0]
            self.assertEqual(guard['name'], "Require this run's change-scope attempt")
            result=subprocess.run(['bash','-c',guard['run']],env={**os.environ,'SCOPE_ATTEMPT':'1','CURRENT_ATTEMPT':'2'},capture_output=True,text=True)
            self.assertEqual(result.returncode,1,name+' retained an old scope')
            self.assertIn('rerun ALL jobs',result.stdout)
        for name in ['fast-gate','deploy']:
            self.assertTrue(any(step.get('name')=='Recheck current fast eligibility' for step in jobs[name]['steps']))

if __name__=='__main__':unittest.main()
