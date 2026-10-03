import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("monitor", Path(__file__).with_name("monitor.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class MonitorTests(unittest.TestCase):
    def test_status_displays_cause_and_retry_including_legacy_errors(self):
        text = m.status_text({'state':'retry_wait', 'issue':1763,
                              'reason':'runtime timed out; retry eligible at 19:00 UTC'})
        self.assertIn('issue=1763', text)
        self.assertIn('runtime timed out', text)
        self.assertIn('19:00 UTC', text)
        self.assertIn('old error', m.status_text({'state':'error', 'error':'old error'}))

    def test_partial_record_and_run_switch(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "worker.jsonl"
            record = json.dumps({"payload_type": "tool.result", "payload": {"text": "work done"}})
            p.write_text(record[:20])
            tail = m.Tail()
            self.assertEqual(tail.poll(p), [])
            with p.open("a") as f:
                f.write(record[20:] + "\n")
            self.assertEqual(tail.poll(p), ["TOOL: work done"])
            self.assertEqual(tail.poll(p), [])
            other = Path(d) / "new.jsonl"
            other.write_text(record + "\n")
            self.assertEqual(tail.poll(other), ["TOOL: work done"])

    def test_terminal_controls_and_prompts_are_not_replayed(self):
        self.assertEqual(m.safe_text("ok\x1b]0;bad\x07"), "ok]0;bad")
        self.assertEqual(m.event_text({"payload_type": "turn.input.user", "payload": {"prompt": "not progress"}}), "")
        self.assertEqual(m.event_text({"payload_type": "run.terminal.completed", "payload": {"text": "done"}}), "RESULT: done")


if __name__ == "__main__":
    unittest.main()
