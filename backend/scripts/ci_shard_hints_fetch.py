"""The CI shard timings, refreshed from green master runs instead of a PR.

Why this exists. `ci_shard_durations.json` balances the eight `backend-tests`
shards, and `test_ci_shard.py` turns master red once 600 test files have no
recorded timing. The refresh workflow used to propose a new file as a PR, but
Actions cannot open PRs in this repo and the one PR it kept updating (#6115) had
been closed since September, so nothing ever landed and master went red at 601
(Nov 15). Now every green master run uploads its recorded timings as the
artifact `ci-shard-durations`, and every CI run applies the newest one.

    python scripts/ci_shard_hints_fetch.py                 # apply (CI shards)
    python scripts/ci_shard_hints_fetch.py job-logs OUT    # refresh workflow

APPLY. Reads this run's `created_at`, takes the newest unexpired
`ci-shard-durations` artifact made on master BEFORE that instant, and writes its
`ci_shard_durations.json` over the committed copy. Every shard of one run asks
the same question with the same instant, so all of them partition from the same
file. No such artifact: the committed file is kept (exit 0). Any failure after an
artifact was chosen exits 1: a shard that quietly fell back while its siblings
used the artifact would split the suite differently and drop or double files.

JOB-LOGS. Concatenates the latest-attempt log of every `backend-tests` job of
`SOURCE_RUN_ID` into OUT. Per job, not the run archive: after a re-run the
archive holds only the re-run jobs. Exit 3 (hold, nothing to record) when a
shard's "Run tests" step did not run — a frontend-only or reused-evidence run
succeeds without running pytest, which is why the old refresh failed with "no
duration lines found".

Standard library only: it runs before `pip install`.
"""

from __future__ import annotations

import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable, Optional

ARTIFACT = "ci-shard-durations"
MEMBER = "ci_shard_durations.json"
DURATIONS_FILE = Path(__file__).resolve().parent / MEMBER
API = "https://api.github.com"
EXPECTED_SHARDS = 8
HOLD = 3

Opener = Callable[[urllib.request.Request], bytes]


def _default_open(req: urllib.request.Request) -> bytes:
    with urllib.request.urlopen(req, timeout=60) as resp:  # redirects are followed
        return resp.read()


def _get(url: str, token: str, opener: Opener, *, raw: bool = False, tries: int = 3, sleep=time.sleep) -> bytes:
    headers = {"Authorization": f"Bearer {token}", "X-GitHub-Api-Version": "2022-11-28"}
    if not raw:
        headers["Accept"] = "application/vnd.github+json"
    last: Optional[Exception] = None
    for attempt in range(tries):
        try:
            return opener(urllib.request.Request(url, headers=headers))
        except urllib.error.HTTPError as exc:
            if exc.code < 500 and exc.code != 429:
                raise
            last = exc
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last = exc
        if attempt + 1 < tries:
            sleep(2 ** attempt * 2)
    assert last is not None
    raise last


def _json(url: str, token: str, opener: Opener, **kw) -> dict:
    return json.loads(_get(url, token, opener, **kw).decode())


def validate(payload: dict) -> int:
    """The number of files the timings cover; raises ValueError if malformed."""
    files = payload.get("files") if isinstance(payload, dict) else None
    if not isinstance(files, dict) or not files:
        raise ValueError("no 'files' object")
    for path, secs in files.items():
        if not isinstance(path, str) or not path.startswith("tests/") or not path.endswith(".py"):
            raise ValueError(f"not a test file path: {path!r}")
        if isinstance(secs, bool) or not isinstance(secs, (int, float)) or secs < 0:
            raise ValueError(f"bad seconds for {path}: {secs!r}")
    return len(files)


def choose(artifacts: list[dict], before: str) -> Optional[dict]:
    """The newest unexpired master artifact made strictly before ``before``."""
    ok = [
        a for a in artifacts
        if a.get("name") == ARTIFACT and not a.get("expired")
        and (a.get("workflow_run") or {}).get("head_branch") == "master"
        and str(a.get("created_at") or "") < before
    ]
    return max(ok, key=lambda a: (a["created_at"], a["id"])) if ok else None


def apply(repo: str, run_id: str, token: str, *, opener: Opener = _default_open, target: Path = DURATIONS_FILE, sleep=time.sleep) -> int:
    try:
        run = _json(f"{API}/repos/{repo}/actions/runs/{run_id}", token, opener, sleep=sleep)
        listing = _json(f"{API}/repos/{repo}/actions/artifacts?name={ARTIFACT}&per_page=100", token, opener, sleep=sleep)
    except Exception as exc:  # noqa: BLE001 — every shard must make the same choice
        print(f"::error::could not list {ARTIFACT} artifacts ({type(exc).__name__}: {exc}); "
              "refusing to guess, since sibling shards may have seen the list")
        return 1
    chosen = choose(listing.get("artifacts") or [], str(run.get("created_at") or ""))
    if chosen is None:
        print(f"::notice::no {ARTIFACT} artifact from master before this run; using the committed timings")
        return 0
    src = (chosen.get("workflow_run") or {}).get("id")
    try:
        blob = _get(chosen["archive_download_url"], token, opener, raw=True, sleep=sleep)
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            payload = json.loads(zf.read(MEMBER).decode())
        n = validate(payload)
    except Exception as exc:  # noqa: BLE001
        print(f"::error::artifact {chosen.get('id')} was chosen but could not be used "
              f"({type(exc).__name__}: {exc}). Failing rather than partition from a different file than the other shards.")
        return 1
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"shard timings: artifact {chosen['id']} ({n} files), made {chosen['created_at']} by run {src}")
    return 0


def job_logs(repo: str, run_id: str, token: str, out: Path, *, expect: int = EXPECTED_SHARDS, opener: Opener = _default_open, sleep=time.sleep) -> int:
    jobs = _json(f"{API}/repos/{repo}/actions/runs/{run_id}/jobs?filter=latest&per_page=100", token, opener, sleep=sleep)
    shards = [j for j in jobs.get("jobs") or [] if str(j.get("name", "")).startswith("backend-tests")]
    if len(shards) != expect:
        print(f"::error::run {run_id} has {len(shards)} backend-tests jobs, expected {expect}; refusing to record a partial suite")
        return 1
    bad = [j["name"] for j in shards if j.get("conclusion") != "success"]
    if bad:
        print(f"::error::not every shard succeeded ({', '.join(bad)}); refusing to record")
        return 1
    ran = [
        j for j in shards
        if any(str(s.get("name", "")).startswith("Run tests") and s.get("conclusion") == "success" for s in j.get("steps") or [])
    ]
    if len(ran) != len(shards):
        print(f"HOLD — {len(shards) - len(ran)} of {len(shards)} shards ran no tests in run {run_id} "
              "(frontend-only, native or reused evidence); nothing to record")
        return HOLD
    with out.open("wb") as fh:
        for j in shards:
            fh.write(_get(f"{API}/repos/{repo}/actions/jobs/{j['id']}/logs", token, opener, raw=True, sleep=sleep))
            fh.write(b"\n")
    print(f"wrote {len(shards)} shard logs from run {run_id} to {out}")
    return 0


def main(argv: list[str]) -> int:
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    if not repo or not token:
        print("::error::GITHUB_REPOSITORY and GH_TOKEN are required")
        return 1
    if argv[:1] == ["job-logs"] and len(argv) == 2:
        return job_logs(repo, os.environ.get("SOURCE_RUN_ID", ""), token, Path(argv[1]))
    if not argv:
        # The refresh workflow sets RUN_FOR to the triggering CI run, so it reads
        # the artifact that run itself used.
        return apply(repo, os.environ.get("RUN_FOR") or os.environ.get("GITHUB_RUN_ID", ""), token)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
