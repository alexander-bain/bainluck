import importlib.util
from pathlib import Path
import unittest
import tempfile
import hashlib
from unittest.mock import patch
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
        self.assertFalse(module.archive_path('YOUR-TURN-REPAIR-STEPS.md'))
        self.assertTrue(module.archive_path('YOUR-TURN-REPAIR-STEPS-ARCHIVE-20260915.md'))
        self.assertTrue(module.archive_path('YOUR-TURN-20261031.md'))
        self.assertTrue(module.archive_path('.claude/handoff/LANE-authority.lock'))
        self.assertTrue(module.archive_path('artifacts/speed-tools/check.py'))
        self.assertTrue(hasattr(module,'scan_archive'),'archive requires a pre-publication secret scan')
        with patch.object(module.shutil,'which',return_value=None):
            with self.assertRaisesRegex(ValueError,'gitleaks'):
                module.scan_archive([],ROOT)
        self.assertTrue(hasattr(module,'snapshot_rows'),'archive must scan and publish immutable snapshots')
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'source';source.mkdir()
            scan=Path(temp)/'scan';scan.mkdir()
            original=source/'YOUR-TURN-ARCHIVE-20261101.md';original.write_text('original')
            rows=module.snapshot_rows([original],source,scan)
            original.write_text('changed after snapshot')
            self.assertEqual(rows[0]['snapshot'].read_text(),'original')
            self.assertEqual(rows[0]['sha256'],hashlib.sha256(b'original').hexdigest())
            with self.assertRaises(RuntimeError):module.verify_sources(rows,source)
if __name__=='__main__':unittest.main()
