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

    def test_same_attempt_rechecks_disabled_flag_and_removed_label(self):
        m=self.module()
        event={'pull_request':{'number':17}}
        pr={'number':17,'state':'open','head':{'sha':'abc'},'base':{'ref':'master'},'labels':[]}
        def read(path):return {'value':'true'} if '/actions/variables/' in path else pr
        with self.assertRaises(ValueError):m.verify_eligibility('pull_request',event,'abc',read)
        pr['labels']=[{'name':'live-path'}]
        m.verify_eligibility('pull_request',event,'abc',read)
        with self.assertRaises(ValueError):m.verify_eligibility('pull_request',event,'abc',lambda p:{'value':'false'} if '/actions/variables/' in p else pr)

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
