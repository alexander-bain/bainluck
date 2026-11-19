from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ci_queue import attach_machine_reason, machine_queue
from model import instant


class TestMachineQueue(unittest.TestCase):
    def setUp(self):
        self.master = {"id": 1, "head_branch": "master", "name": "CI", "event": "push"}
        self.jobs = {
            1: [{"id": 1, "status": "queued", "labels": ["ubuntu-latest"]}],
            2: [
                *(
                    {"id": 100 + i, "status": "queued", "labels": ["ubuntu-latest"]}
                    for i in range(94)
                ),
                *(
                    {
                        "id": 1000 + i,
                        "status": "in_progress",
                        "labels": ["ubuntu-latest"],
                        "runner_name": "GitHub Actions 1",
                        "started_at": "2026-11-19T02:15:00Z",
                    }
                    for i in range(40)
                ),
                {
                    "id": 2000,
                    "status": "queued",
                    "labels": ["self-hosted", "ubuntu-latest"],
                },
                {"id": 2001, "status": "pending", "labels": ["ubuntu-latest"]},
            ],
        }
        other_jobs = self.jobs.pop(2)
        self.others = []
        for index, start in enumerate(range(0, len(other_jobs), 24), 2):
            self.others.append(
                {
                    "id": index,
                    "head_branch": "codex/other",
                    "name": "CI",
                    "event": "pull_request",
                }
            )
            self.jobs[index] = other_jobs[start : start + 24]

    def response(self, endpoint, **kwargs):
        if "?status=" in endpoint:
            records = [self.master] if "status=queued" in endpoint else self.others
            return {"total_count": len(records), "workflow_runs": records}
        run = int(endpoint.split("/")[-2])
        return {"total_count": len(self.jobs[run]), "jobs": self.jobs[run]}

    def measured(self):
        return machine_queue(
            Mock(request=Mock(side_effect=self.response)),
            "owner/repo",
            instant("2026-11-19T02:20:00Z"),
        )

    def test_40_running_and_95_waiting_when_the_master_job_has_no_machine(self):
        queue = self.measured()
        self.assertEqual(queue, {"running": 40, "waiting": 95})
        result = {
            "stops": [
                {"kind": "line-stalled", "line": "Server"},
                {"kind": "line-stalled", "line": "Apps"},
                {"kind": "hold", "line": "Apps"},
            ]
        }
        attach_machine_reason(result, queue)
        self.assertEqual(result["stops"][0]["machines"], queue)
        self.assertNotIn("machines", result["stops"][1])

    def test_an_unrelated_queue_does_not_explain_the_dock(self):
        self.jobs[1][0]["status"] = "completed"
        self.assertIsNone(self.measured())

    def test_partial_response_gives_no_cause(self):
        original = self.response

        def partial(endpoint, **kwargs):
            result = original(endpoint, **kwargs)
            if "/jobs?" in endpoint:
                result["total_count"] += 1
            return result

        self.response = partial
        self.assertIsNone(self.measured())
