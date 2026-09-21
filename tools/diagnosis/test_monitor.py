import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("monitor", Path(__file__).with_name("monitor.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class MonitorTests(unittest.TestCase):
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
