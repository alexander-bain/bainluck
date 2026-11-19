"""Observed GitHub-hosted jobs for the repository, sampled only at a stalled dock."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import re
import urllib.error

from signals import moment

MAX_RUNS = 20
HOSTED_LABEL = re.compile(r"(?:ubuntu|windows|macos)-[a-z0-9.]+(?:-[a-z0-9.]+)*", re.I)


def machine_queue(api, repo, now):
    """Count actual jobs and require an unassigned master CI job for attribution."""
    prefix = f"repos/{repo}/actions/runs"
    try:
        runs = {}
        for status in ("queued", "in_progress"):
            response = api.request(
                f"{prefix}?status={status}&per_page={MAX_RUNS}", timeout=5
            )
            if response["total_count"] != len(response["workflow_runs"]):
                return None
            runs.update((item["id"], item) for item in response["workflow_runs"])
        if len(runs) > MAX_RUNS:
            return None

        def jobs(run):
            return api.request(f'{prefix}/{run["id"]}/jobs?per_page=100', timeout=5)

        running, waiting = set(), set()
        master_waiting = False
        with ThreadPoolExecutor(max_workers=4) as workers:
            for run, response in zip(runs.values(), workers.map(jobs, runs.values())):
                if response["total_count"] != len(response["jobs"]):
                    return None
                for job in response["jobs"]:
                    labels = job.get("labels") or []
                    if "self-hosted" in labels or not any(
                        HOSTED_LABEL.fullmatch(v) for v in labels
                    ):
                        continue
                    if (
                        job["status"] == "in_progress"
                        and job.get("runner_name")
                        and job.get("started_at")
                    ):
                        if (
                            timedelta(0)
                            <= now - moment(job["started_at"])
                            <= timedelta(hours=6)
                        ):
                            running.add(job["id"])
                    elif job["status"] == "queued" and not job.get("runner_name"):
                        waiting.add(job["id"])
                        master_waiting |= (
                            run.get("name") == "CI"
                            and run.get("head_branch") == "master"
                            and run.get("event") == "push"
                        )
        if master_waiting:
            return {"running": len(running), "waiting": len(waiting)}
    except (OSError, urllib.error.URLError, KeyError, ValueError, TypeError):
        # A partial read cannot explain a delay.
        return None
    return None


def attach_machine_reason(result, queue):
    if queue is None:
        return
    holds = {stop["line"] for stop in result["stops"] if stop["kind"] == "hold"}
    for stop in result["stops"]:
        if stop["kind"] == "line-stalled" and stop["line"] not in holds:
            stop["machines"] = queue
