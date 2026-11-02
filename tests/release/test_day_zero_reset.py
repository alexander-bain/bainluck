import importlib.util
from pathlib import Path
import unittest
from datetime import datetime, timezone
ROOT = Path(__file__).resolve().parents[2]

class ResetTest(unittest.TestCase):
    def test_cutoffs_and_enhancement_exception(self):
        file = ROOT / 'tools/release/day_zero_reset.py'
        self.assertTrue(file.exists(), 'reset policy missing')
        spec = importlib.util.spec_from_file_location('reset',file)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        now = datetime(2026,11,1,tzinfo=timezone.utc)
        self.assertTrue(module.old_pr({'state':'open','created_at':'2026-10-17T00:00:00Z'},now))
        self.assertFalse(module.old_pr({'state':'open','created_at':'2026-10-18T00:00:00Z'},now))
        stale = {'state':'open','updated_at':'2026-08-02T00:00:00Z','labels':[]}
        self.assertTrue(module.stale_issue(stale,now))
        self.assertFalse(module.stale_issue({**stale,'labels':[{'name':'enhancement'}]},now))
        self.assertFalse(module.stale_issue({**stale,'pull_request':{}},now))
        self.assertFalse(module.stale_issue({**stale,'updated_at':'2026-08-03T00:00:00Z'},now))
if __name__ == '__main__': unittest.main()
