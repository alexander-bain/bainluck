import importlib.util
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[2]
class RetireTest(unittest.TestCase):
    def test_targets_stay_in_personal_roots_and_preserve_unmerged_and_locked(self):
        file=ROOT/'tools/release/retire_worktrees.py'
        self.assertTrue(file.exists(),'retirement policy missing')
        spec=importlib.util.spec_from_file_location('retire',file)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        row={'path':'/Users/bain/.codex-personal/worktrees/example/bainluck','merged':True,'locked':False,'valid':True}
        self.assertTrue(module.eligible(row))
        for field in ('merged','valid'):
            self.assertFalse(module.eligible({**row,field:False}))
        self.assertFalse(module.eligible({**row,'locked':True}))
        self.assertTrue(module.eligible({**row,'merged':False,'abandoned':True}))
        self.assertFalse(module.eligible({**row,'path':'/private/tmp/wt-fe-bank'}))
        self.assertFalse(module.eligible({**row,'path':'/Users/bain/bainluck'}))
        manifest={'master':'abc','rows':[row]}
        self.assertTrue(hasattr(module,'inventory_markdown'),'publication guard is missing')
        body=module.inventory_markdown(manifest)
        self.assertTrue(module.publication_matches([{'body':body}],manifest))
        self.assertFalse(module.publication_matches([{'body':'unreviewed list'}],manifest))
if __name__=='__main__':unittest.main()
