"""Read the hosted machine queue and the evidence for a stalled merge line."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import re
import urllib.error
from urllib.parse import urlencode

from signals import moment

HOSTED_MACHINE_CAPACITY = 40
PAGE_SIZE = 100
RUN_SEARCH_LIMIT = 1000
HOSTED_LABEL = re.compile(r"(?:ubuntu|windows|macos)-[a-z0-9.]+(?:-[a-z0-9.]+)*", re.I)


def _page(api, endpoint: str, query: dict[str, str], number: int) -> dict:
    params = urlencode({**query, "per_page": PAGE_SIZE, "page": number})
    return api.request(f"{endpoint}?{params}", timeout=5)


def _complete_pages(
    api, endpoint: str, query: dict[str, str], field: str, first: dict
) -> list[dict]:
    total = first["total_count"]
    records = list(first[field])
    for offset in range(PAGE_SIZE, total, PAGE_SIZE):
        page = _page(api, endpoint, query, 1 + offset // PAGE_SIZE)
        if page["total_count"] != total:
            raise ValueError("The queue changed during paging")
        records.extend(page[field])
    if len(records) != total or len({row["id"] for row in records}) != total:
        raise ValueError("Incomplete GitHub queue response")
    return records


def _active_runs(
    api,
    endpoint: str,
    status: str,
    now: datetime,
    interval: tuple[int, int] | None = None,
) -> list[dict]:
    query = {"status": status}
    if interval is not None:
        start, end = interval
        query["created"] = "..".join(
            datetime.fromtimestamp(bound, timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
            for bound in interval
        )
    first = _page(api, endpoint, query, 1)
    if first["total_count"] < RUN_SEARCH_LIMIT:
        return _complete_pages(api, endpoint, query, "workflow_runs", first)
    # GitHub status-filtered searches return at most 1,000 runs per query.
    # Split the created-time filter into disjoint ranges when it reaches that cap.
    if interval is None:
        return _active_runs(api, endpoint, status, now, (0, int(now.timestamp())))
    if start == end:
        raise ValueError("GitHub capped the runs in one second")
    middle = (start + end) // 2
    return _active_runs(api, endpoint, status, now, (start, middle)) + _active_runs(
        api, endpoint, status, now, (middle + 1, end)
    )


def _run_inventory(api, endpoint: str, now: datetime) -> dict:
    def read():
        return {
            run["id"]: run
            for status in ("queued", "in_progress")
            for run in _active_runs(api, endpoint, status, now)
        }

    try:
        return read()
    except (OSError, ValueError):
        # A run can finish between pages, or a list request can time out.
        return read()


def machine_queue(api, repo: str, now: datetime) -> dict | None:
    """Return run counts and the independent job counts used for dock attribution."""
    prefix = f"repos/{repo}/actions/runs"
    try:
        runs = _run_inventory(api, prefix, now)

        def jobs(run):
            endpoint = f'{prefix}/{run["id"]}/jobs'
            return _complete_pages(
                api, endpoint, {}, "jobs", _page(api, endpoint, {}, 1)
            )

        running_jobs, waiting_jobs = set(), set()
        runs_running = runs_waiting = no_jobs = 0
        oldest = None
        unknown_wait = master_waiting = False
        with ThreadPoolExecutor(max_workers=4) as workers:
            for run, records in zip(runs.values(), workers.map(jobs, runs.values())):
                no_jobs += not records and run.get("status") == "queued"
                waiting_since = []
                running = False
                for job in records:
                    labels = job.get("labels") or []
                    if "self-hosted" in labels or not any(
                        HOSTED_LABEL.fullmatch(label) for label in labels
                    ):
                        continue
                    if job["status"] == "in_progress" and job.get("runner_name"):
                        if job.get("started_at") and (
                            timedelta(0)
                            <= now - moment(job["started_at"])
                            <= timedelta(hours=6)
                        ):
                            running_jobs.add(job["id"])
                            running = True
                    elif job["status"] == "queued" and not job.get("runner_name"):
                        waiting_jobs.add(job["id"])
                        # For a queued job, GitHub records the time it created
                        # the job even when no separate queued timestamp is sent.
                        created = job.get("queued_at") or job.get("created_at")
                        waiting_since.append(moment(created) if created else None)
                        master_waiting |= (
                            run.get("name") == "CI"
                            and run.get("head_branch") == "master"
                            and run.get("event") == "push"
                        )
                if running:
                    runs_running += 1
                elif waiting_since:
                    runs_waiting += 1
                    for since in waiting_since:
                        if since is None:
                            unknown_wait = True
                        elif oldest is None or since < oldest:
                            oldest = since
        return {
            "display": {
                "machines": HOSTED_MACHINE_CAPACITY,
                "running": runs_running,
                "waiting": runs_waiting,
                "longest_wait_minutes": (
                    max(0, int((now - oldest).total_seconds() // 60))
                    if oldest is not None and not unknown_wait
                    else None
                ),
                "queued_without_jobs": no_jobs,
            },
            "master_jobs": (
                {"running": len(running_jobs), "waiting": len(waiting_jobs)}
                if master_waiting
                else None
            ),
        }
    except (OSError, urllib.error.URLError, KeyError, ValueError, TypeError):
        # An incomplete read cannot supply counts or a cause for a delay.
        return None


def attach_machine_reason(result, queue):
    if queue is None:
        return
    holds = {stop["line"] for stop in result["stops"] if stop["kind"] == "hold"}
    for stop in result["stops"]:
        if stop["kind"] == "line-stalled" and stop["line"] not in holds:
            stop["machines"] = queue
