from pathlib import Path
import sys
import unittest
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ci_queue import attach_machine_reason, machine_queue
from model import instant

NOW = instant("2026-11-19T02:20:00Z")


def queued_job(id, created_at="2026-11-19T02:10:00Z"):
    return {
        "id": id,
        "status": "queued",
        "labels": ["ubuntu-latest"],
        "created_at": created_at,
    }


class TestMachineQueue(unittest.TestCase):
    def setUp(self):
        self.master = {
            "id": 1,
            "head_branch": "master",
            "name": "CI",
            "event": "push",
            "status": "queued",
        }
        self.queued = [self.master]
        self.running = [{"id": 2, "status": "in_progress", "event": "pull_request"}]
        self.jobs = {
            1: [queued_job(1)],
            2: [
                *(queued_job(100 + i) for i in range(94)),
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

    def response(self, endpoint, **kwargs):
        parsed = urlsplit(endpoint)
        params = parse_qs(parsed.query)
        start = (int(params["page"][0]) - 1) * int(params["per_page"][0])
        end = start + int(params["per_page"][0])
        if parsed.path.endswith("/jobs"):
            rows = self.jobs[int(parsed.path.split("/")[-2])]
            return {"total_count": len(rows), "jobs": rows[start:end]}
        rows = self.queued if params["status"][0] == "queued" else self.running
        if "created" in params:
            first, last = map(instant, params["created"][0].split(".."))
            rows = [run for run in rows if first <= instant(run["created_at"]) <= last]
        rows = rows[:1000]  # GitHub caps a status-filtered search.
        return {"total_count": len(rows), "workflow_runs": rows[start:end]}

    def measured(self):
        return machine_queue(
            Mock(request=Mock(side_effect=self.response)), "owner/repo", NOW
        )

    def test_keeps_run_counts_separate_from_the_40_running_and_95_waiting_jobs(self):
        queue = self.measured()
        self.assertEqual(
            queue["display"],
            {
                "machines": 40,
                "running": 1,
                "waiting": 1,
                "longest_wait_minutes": 10,
                "queued_without_jobs": 0,
            },
        )
        jobs = {"running": 40, "waiting": 95}
        self.assertEqual(queue["master_jobs"], jobs)
        result = {
            "stops": [
                {"kind": "line-stalled", "line": "Server"},
                {"kind": "line-stalled", "line": "Apps"},
                {"kind": "hold", "line": "Apps"},
            ]
        }
        attach_machine_reason(result, queue["master_jobs"])
        self.assertEqual(result["stops"][0]["machines"], jobs)
        self.assertNotIn("machines", result["stops"][1])

    def test_large_queue_includes_waiting_runs_and_longest_wait_on_the_second_page(
        self,
    ):
        for run in range(3, 133):
            self.queued.append({"id": run, "status": "queued"})
            self.jobs[run] = [queued_job(3000 + run)]
        self.jobs[132][0]["created_at"] = "2026-11-18T23:00:00Z"
        queue = self.measured()["display"]
        self.assertEqual(queue["waiting"], 131)
        self.assertEqual(queue["running"], 1)
        self.assertEqual(queue["longest_wait_minutes"], 200)

    def test_status_search_cap_does_not_hide_additional_waiting_runs(self):
        self.master["created_at"] = "2020-01-01T00:00:00Z"
        for run in range(3, 1004):
            created = "2020-01-01T00:00:00Z" if run < 505 else "2026-11-18T00:00:00Z"
            self.queued.append({"id": run, "status": "queued", "created_at": created})
            self.jobs[run] = [queued_job(5000 + run)]
        self.assertEqual(self.measured()["display"]["waiting"], 1002)

    def test_a_queued_run_without_jobs_has_no_machine_wait_or_wait_time(self):
        self.queued.append(
            {"id": 3, "status": "queued", "created_at": "2026-11-01T00:00:00Z"}
        )
        self.jobs[3] = []
        queue = self.measured()["display"]
        self.assertEqual(queue["waiting"], 1)
        self.assertEqual(queue["longest_wait_minutes"], 10)
        self.assertEqual(queue["queued_without_jobs"], 1)

    def test_a_wait_with_no_timestamp_keeps_the_count_and_omits_the_longest_time(self):
        self.jobs[1][0].pop("created_at")
        queue = self.measured()["display"]
        self.assertEqual(queue["waiting"], 1)
        self.assertIsNone(queue["longest_wait_minutes"])

    def test_an_unrelated_queue_does_not_explain_the_dock(self):
        self.jobs[1][0]["status"] = "completed"
        result = self.measured()
        self.assertEqual(result["display"]["waiting"], 0)
        self.assertIsNone(result["master_jobs"])

    def test_partial_response_gives_no_counts_or_cause(self):
        original = self.response

        def partial(endpoint, **kwargs):
            result = original(endpoint, **kwargs)
            if "/jobs?" in endpoint:
                result["total_count"] += 1
            return result

        self.response = partial
        self.assertIsNone(self.measured())

    def test_retries_an_inventory_that_shifted_during_the_read(self):
        original = self.response
        incomplete = True

        def shifting(endpoint, **kwargs):
            nonlocal incomplete
            result = original(endpoint, **kwargs)
            if incomplete and "status=queued" in endpoint:
                incomplete = False
                result["total_count"] += 1
            return result

        self.response = shifting
        self.assertEqual(self.measured()["display"]["waiting"], 1)
