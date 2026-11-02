import importlib.util
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[2]
class ArchiveTest(unittest.TestCase):
    def test_both_hold_conditions_are_required(self):
        file=ROOT/'tools/release/archive_process.py'
        self.assertTrue(file.exists(),'archive guard missing')
        spec=importlib.util.spec_from_file_location('archive',file)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        for paused,merged in [('',True),('lanes are paused',False),('',False)]:
            with self.assertRaises(ValueError):module.authorized(paused,merged)
        module.authorized('lanes are paused',True)
        self.assertFalse(module.archive_path('YOUR-TURN.md'))
        self.assertTrue(module.archive_path('YOUR-TURN-20261031.md'))
        self.assertTrue(module.archive_path('.claude/handoff/LANE-authority.lock'))
        self.assertTrue(module.archive_path('artifacts/speed-tools/check.py'))
if __name__=='__main__':unittest.main()
