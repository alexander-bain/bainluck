import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / 'tools/release/live_path.py'

class LivePathTests(unittest.TestCase):
    def load(self):
        self.assertTrue(SCRIPT.exists(), 'live path classifier has not been built')
        spec = importlib.util.spec_from_file_location('live_path', SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_push_requires_all_associated_prs_to_be_labeled_and_merged(self):
        m = self.load()
        good = {'merged_at': '2026-11-02T10:00:00Z', 'base': {'ref': 'master'}, 'labels': [{'name': 'live-path'}], 'merge_commit_sha': 'abc'}
        self.assertTrue(m.is_live_event('push', {}, [good], 'abc'))
        self.assertFalse(m.is_live_event('push', {}, [], 'abc'))
        self.assertFalse(m.is_live_event('push', {}, [good, {**good, 'labels': []}], 'abc'))
        self.assertFalse(m.is_live_event('push', {}, [good], 'other'))
        self.assertFalse(m.is_live_event('push', {}, [{**good, 'merged_at': None}], 'abc'))

    def test_pull_request_label_is_recomputed(self):
        m = self.load()
        self.assertTrue(m.is_live_event('pull_request', {'pull_request': {'labels': [{'name': 'live-path'}]}}, [], ''))
        self.assertFalse(m.is_live_event('pull_request', {'pull_request': {'labels': []}}, [], ''))

    def test_selection_follows_test_helper_imports_and_literal_source_reads(self):
        m = self.load()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files = {
                'backend/app/utils/prob.py': 'VALUE = 1\n',
                'backend/app/services/blend.py': 'from app.utils.prob import VALUE\n',
                'backend/tests/test_helper.py': 'from app.utils.prob import VALUE\n',
                'backend/tests/test_blend.py': 'from tests.test_helper import VALUE\ndef test_blend(): assert VALUE == 1\n',
                'backend/tests/test_source.py': 'from pathlib import Path\ndef test_read(): Path("backend/app/utils/prob.py").read_text()\n',
                'backend/tests/test_unrelated.py': 'def test_ok(): assert True\n',
            }
            for name, body in files.items():
                p = root / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(body)
            selected = m.select_tests(root, ['backend/app/utils/prob.py'])
            self.assertEqual(selected, ['tests/test_blend.py', 'tests/test_helper.py', 'tests/test_source.py', 'tests/test_startup.py'])

    def test_unknown_or_global_changes_keep_full_ci(self):
        m = self.load()
        for path in ['backend/requirements.txt', 'backend/app/main.py', 'backend/alembic/versions/x.py', 'frontend/app/page.tsx', '.github/workflows/ci.yml']:
            self.assertIsNone(m.select_tests(ROOT, [path]), path)

    def test_builder_a_canonical_speed_tools_are_admitted(self):
        m = self.load()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / 'tools/speed/check.py'
            path.parent.mkdir(parents=True)
            path.write_text('print("ready")\n')
            shell = path.with_name('watch.sh'); shell.write_text('echo ready\n')
            self.assertEqual(m.select_tests(root, ['tools/speed/check.py', 'tools/speed/watch.sh']), ['tests/test_startup.py'])
            test = root / 'tools/speed/tests/test_check.py'
            test.parent.mkdir(); test.write_text('def test_check(): assert True\n')
            self.assertEqual(m.select_tests(root, ['tools/speed/check.py']), ['../tools/speed/tests/test_check.py', 'tests/test_startup.py'])

    def test_no_coverage_or_deleted_module_keeps_full_ci(self):
        m = self.load()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertIsNone(m.select_tests(root, ['backend/app/tasks/missing.py']))

    def test_python311_rejects_pep701_fstrings_without_using_feature_version(self):
        m = self.load()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'bad.py'; p.write_text('x = f"{data["key"]}"\n')
            self.assertTrue(m.pep701_errors(p))
            p.write_text('x = f"{data[\'key\']}"\n')
            self.assertEqual(m.pep701_errors(p), [])

if __name__ == '__main__': unittest.main()
