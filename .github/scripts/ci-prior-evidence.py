#!/usr/bin/env python3
"""#11091: reuse only a complete, exact-commit compose PUSH run; uncertainty runs CI.

No PR/synthetic-tree credit. This is test evidence, never a build artifact for
Heroku. The public decision interface always emits reuse=false on uncertainty.
Only the original Actions run can supply the authenticated provenance artifact.
"""

from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import os
from pathlib import Path
import re
import subprocess
import time
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ".github/workflows/ci.yml"
SHA = re.compile(r"[0-9a-f]{40}")
REFUSAL = re.compile(r"high|critical|medium|security vulnerabilit", re.I)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def git(*args):
    return subprocess.check_output(
        ["git", "-C", str(ROOT), *args], text=True, timeout=10
    ).strip()


def record(env, identity="change-scope"):
    head, tree, base = (
        git("rev-parse", "HEAD"),
        git("rev-parse", "HEAD^{tree}"),
        git("rev-parse", "origin/master"),
    )
    require(head == env["GITHUB_SHA"], "checkout is not event commit")
    subprocess.run(
        ["git", "-C", str(ROOT), "merge-base", "--is-ancestor", base, head],
        check=True,
        timeout=10,
    )
    job = env["GITHUB_JOB"]
    require(
        identity == job
        or (
            job == "backend-tests"
            and re.fullmatch(r"backend-tests-[1-9][0-9]*", identity)
        ),
        "unexpected provenance identity",
    )
    return {
        "schema": 2,
        "identity": identity,
        "job": job,
        "head": head,
        "tree": tree,
        "base": base,
        "run_id": int(env["GITHUB_RUN_ID"]),
        "attempt": int(env["GITHUB_RUN_ATTEMPT"]),
        "repository_id": int(env["GITHUB_REPOSITORY_ID"]),
        "ref": env["GITHUB_REF"],
        "event": env["GITHUB_EVENT_NAME"],
        "environment": {
            key: env.get(key, "unavailable")
            for key in (
                "RUNNER_OS",
                "RUNNER_ARCH",
                "ImageOS",
                "ImageVersion",
                "GITHUB_WORKFLOW_REF",
            )
        },
    }


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        require(newurl.startswith("https://"), "non-HTTPS artifact redirect")
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is not None:
            redirected.remove_header("Authorization")
        return redirected


class API:
    def __init__(self, repo, token):
        require(
            re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo), "invalid repository"
        )
        require(bool(token), "no Actions read token")
        self.prefix = f"https://api.github.com/repos/{repo}/"
        self.token = token
        self.deadline = time.monotonic() + 75
        self.opener = urllib.request.build_opener(SafeRedirect())

    def raw(self, path, limit=2_000_000):
        remaining = self.deadline - time.monotonic()
        require(remaining > 0, "evidence decision deadline")
        request = urllib.request.Request(
            self.prefix + path,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with self.opener.open(request, timeout=min(10, remaining)) as response:
            require(response.status == 200, "non-200 evidence response")
            content = response.read(limit + 1)
        require(len(content) <= limit, "oversize evidence response")
        return content

    def get(self, path):
        return json.loads(self.raw(path))

    def pages(self, path, key):
        rows, expected, page = [], None, 1
        while True:
            require(page <= 20, "pagination bound exceeded")
            result = self.get(
                f"{path}{'&' if '?' in path else '?'}per_page=100&page={page}"
            )
            total = result["total_count"]
            require(isinstance(total, int) and total >= 0, "invalid total_count")
            require(expected is None or total == expected, "pagination moved")
            expected = total
            batch = result[key]
            require(isinstance(batch, list), "invalid pagination rows")
            rows.extend(batch)
            require(len(rows) <= total, "pagination exceeds total_count")
            if len(rows) == total:
                require(
                    len({row["id"] for row in rows}) == len(rows),
                    "duplicate pagination row",
                )
                return rows
            require(len(batch) == 100, "short pagination")
            page += 1


def membership(text):
    """Read only the deliberately constrained job/matrix grammar we support.

    No YAML package install in change-scope. Unknown matrix syntax refuses reuse;
    CI's normal path remains able to execute a future workflow without this parser.
    Tests compare this projection with PyYAML's actual workflow interpretation.
    """
    text = text.split("\njobs:\n", 1)[1]
    blocks = dict(
        re.findall(r"^  ([\w-]+):\n(.*?)(?=^  [\w-]+:|\Z)", text, re.M | re.S)
    )
    expected = {}
    for job, block in blocks.items():
        if job in ("release-required", "deploy"):
            continue
        name = re.search(r"^    name: (.+)$", block, re.M)
        label = name.group(1).strip() if name else job
        matrices = re.findall(r"^        (shard|group): \[([^\]\n]+)\]$", block, re.M)
        if "    strategy:" in block:
            require(
                len(matrices) == 1 and job in ("backend-tests", "database-integration"),
                "unreviewed matrix grammar",
            )
            axis, values = matrices[0]
            values = [v.strip() for v in values.split(",")]
            require(
                all(re.fullmatch(r"[\w-]+", v) for v in values)
                and len(set(values)) == len(values),
                "invalid matrix",
            )
            require(
                (job, axis)
                in (("backend-tests", "shard"), ("database-integration", "group")),
                "unexpected matrix axis",
            )
            for value in values:
                expected[f"{label} ({value})"] = (job, value, len(values), block)
        else:
            expected[label] = (job, None, None, block)
    require(
        {
            "backend-tests",
            "database-integration",
            "change-scope",
            "shard-completeness",
            "golden-baseline-floor",
            "frontend-build",
            "e2e-contract",
            "search-recall",
        }
        == {v[0] for v in expected.values()},
        "unreviewed job set",
    )
    return expected


def stamp(value):
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def expected_steps(kind, value, count, block):
    """Only the reviewed condition grammar; unknown conditions refuse reuse."""
    reuse = "needs.change-scope.outputs.reuse != 'true'"
    scope = "needs.change-scope.outputs.scope != 'frontend'"
    compose = "github.event_name == 'push' && startsWith(github.ref, 'refs/heads/integrator/compose-')"
    executing = {
        None,
        reuse,
        f"{scope} && {reuse}",
        compose,
        f"{scope} && {reuse} && {compose}",
    }
    skipped = {
        "needs.change-scope.outputs.reuse == 'true'",
        "needs.change-scope.outputs.scope == 'frontend'",
        "github.event_name == 'push' && github.ref == 'refs/heads/master'",
    }
    required = []
    for definition in re.split(r"^      - ", block, flags=re.M)[1:]:
        match = re.match(r"name: (.+)\n", definition)
        condition = re.search(r"^        if: (.+)$", definition, re.M)
        expression = condition.group(1) if condition else None
        group = re.fullmatch(
            r"matrix\.group == '([\w-]+)' && " + re.escape(reuse), expression or ""
        )
        require(
            expression in executing | skipped
            or (kind == "database-integration" and group is not None),
            "unreviewed step condition",
        )
        if expression in skipped or (group and group.group(1) != value) or not match:
            continue
        label = match.group(1).strip()
        if label.startswith('"'):
            label = json.loads(label)
        elif label.startswith("'"):
            require(label.endswith("'"), "unterminated step quote")
            label = label[1:-1].replace("''", "'")
        else:
            label = re.split(r"\s+#", label, maxsplit=1)[0].rstrip()
        label = label.replace("${{ matrix.shard }}", str(value)).replace(
            "${{ strategy.job-total }}", str(count)
        )
        required.append(label)
    require(
        bool(required) and len(required) == len(set(required)),
        "missing/ambiguous expected steps",
    )
    return required


def validate_jobs(jobs, expected):
    names = [j["name"] for j in jobs]
    require(len(names) == len(set(names)), "ambiguous job names")
    actual = {j["name"]: j for j in jobs}
    require(
        set(actual) == set(expected) | {"release-required", "deploy"},
        "incomplete or unexpected job membership",
    )
    for name, (kind, value, count, block) in expected.items():
        job = actual[name]
        require(
            job["status"] == "completed" and job["conclusion"] == "success",
            f"unpaid job {name}",
        )
        steps = job["steps"]
        for label in expected_steps(kind, value, count, block):
            found = [step for step in steps if step["name"] == label]
            require(
                len(found) == 1
                and found[0]["status"] == "completed"
                and found[0]["conclusion"] == "success",
                f"unpaid executing step {name}: {label}",
            )


def provenance_ids(expected):
    """Every history-sensitive checkout must witness the same original master."""
    identities = {
        "change-scope": "change-scope",
        "golden-baseline-floor": "golden-baseline-floor",
    }
    for kind, value, _, _ in expected.values():
        if kind == "backend-tests":
            identities[f"backend-tests-{value}"] = kind
    return identities


def validate_provenance(api, artifacts, run, expected, head, tree, before, repo_id):
    for identity, job in provenance_ids(expected).items():
        name = f"compose-source-provenance-{run['run_attempt']}-{identity}"
        matched = [artifact for artifact in artifacts if artifact["name"] == name]
        require(
            len(matched) == 1 and not matched[0]["expired"],
            "missing/ambiguous/expired provenance",
        )
        archive = zipfile.ZipFile(
            io.BytesIO(api.raw(f"actions/artifacts/{matched[0]['id']}/zip", 1_000_000))
        )
        require(
            archive.namelist() == ["ci-provenance.json"],
            "unexpected provenance archive",
        )
        require(
            archive.getinfo("ci-provenance.json").file_size <= 64_000,
            "oversize provenance",
        )
        proof = json.loads(archive.read("ci-provenance.json"))
        require(
            proof["schema"] == 2
            and proof["identity"] == identity
            and proof["job"] == job,
            "provenance job mismatch",
        )
        require(
            proof["event"] == "push"
            and proof["head"] == head
            and proof["tree"] == tree
            and proof["base"] == before,
            "provenance source/base mismatch",
        )
        require(
            proof["repository_id"] == repo_id
            and proof["run_id"] == run["id"]
            and proof["attempt"] == run["run_attempt"]
            and proof["ref"] == f"refs/heads/{run['head_branch']}",
            "provenance run mismatch",
        )


def decide(api, env, text, tree, before):
    head, repo_id = env["GITHUB_SHA"], int(env["GITHUB_REPOSITORY_ID"])
    require(SHA.fullmatch(head) and SHA.fullmatch(before), "invalid source identity")
    require(
        env["GITHUB_EVENT_NAME"] == "push" and env["GITHUB_REF"] == "refs/heads/master",
        "master push only",
    )
    current = api.get(f"actions/runs/{env['GITHUB_RUN_ID']}")
    require(
        current["event"] == "push"
        and current["head_branch"] == "master"
        and current["head_sha"] == head,
        "current run identity",
    )
    runs = api.pages(f"actions/runs?head_sha={head}&event=push", "workflow_runs")
    candidates = []
    for row in runs:
        if (
            row.get("path") != WORKFLOW
            or row.get("event") != "push"
            or not str(row.get("head_branch", "")).startswith("integrator/compose-")
        ):
            continue
        require(
            row["head_sha"] == head
            and row["repository"]["id"] == repo_id
            and row["head_repository"]["id"] == repo_id,
            "foreign source run",
        )
        run = api.get(f"actions/runs/{row['id']}")
        require(
            all(
                run[k] == row[k]
                for k in (
                    "id",
                    "head_sha",
                    "head_branch",
                    "path",
                    "event",
                    "run_attempt",
                )
            ),
            "run moved",
        )
        require(
            run["status"] == "completed" and run["conclusion"] == "success",
            "compose latest attempt not successful",
        )
        age = (stamp(current["created_at"]) - stamp(run["updated_at"])).total_seconds()
        require(
            0 <= age <= 3 * 3600,
            "compose evidence too old or finished after master push",
        )
        candidates.append(run)
    require(len(candidates) == 1, "missing or ambiguous compose evidence")
    run = candidates[0]
    expected = membership(text)
    validate_jobs(
        api.pages(f"actions/runs/{run['id']}/jobs?filter=latest", "jobs"), expected
    )
    artifacts = api.pages(f"actions/runs/{run['id']}/artifacts", "artifacts")
    validate_provenance(api, artifacts, run, expected, head, tree, before, repo_id)
    checks = api.pages(f"commits/{head}/check-runs?filter=all", "check_runs")
    suites = {}
    security_paid = set()
    security_required = {
        ("CodeQL", 57789),
        ("Analyze (python)", 15368),
        ("Analyze (javascript-typescript)", 15368),
        ("gitleaks secret scan", 15368),
    }
    for check in checks:
        suite_id = check["check_suite"]["id"]
        if suite_id not in suites:
            suites[suite_id] = api.get(f"check-suites/{suite_id}")
        suite = suites[suite_id]
        require(suite["head_sha"] == head, "check suite source mismatch")
        # Master's own CodeQL/CI is still running during this decision. Its
        # branch is authoritative, not newest-check order. Completed failures
        # from ANY branch still refuse; older failed/security evidence is never
        # hidden by a later green.
        if check["status"] != "completed":
            require(
                suite["head_branch"] == "master",
                "unfinished pre-push security/check evidence",
            )
            continue
        require(
            check["conclusion"] != "failure"
            and not REFUSAL.search((check.get("output") or {}).get("title") or ""),
            "security/check refusal",
        )
        identity = (check["name"], check["app"]["id"])
        if suite["head_branch"] == run["head_branch"] and identity in security_required:
            # A successful older check cannot pay an unpaid/cancelled rerun.
            # Conservatively require every completed required source check to
            # succeed instead of inferring its workflow attempt from ordering.
            require(check["conclusion"] == "success", "unpaid compose security check")
            security_paid.add(identity)
    require(
        security_required <= security_paid,
        "missing complete compose security checks",
    )
    reread = api.get(f"actions/runs/{run['id']}")
    require(
        reread["run_attempt"] == run["run_attempt"]
        and reread["status"] == "completed"
        and reread["conclusion"] == "success",
        "source rerun moved",
    )
    return {
        "reuse": "true",
        "reuse_run": str(run["id"]),
        "reuse_attempt": str(run["run_attempt"]),
        "reuse_head": head,
        "reuse_base": before,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", type=Path)
    parser.add_argument("--identity", default="change-scope")
    args = parser.parse_args()
    if args.record:
        args.record.write_text(
            json.dumps(record(os.environ, args.identity), sort_keys=True) + "\n"
        )
        return
    result = {"reuse": "false"}
    try:
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
        require(
            git("rev-parse", "HEAD") == os.environ["GITHUB_SHA"],
            "master checkout mismatch",
        )
        api = API(os.environ["GITHUB_REPOSITORY"], os.environ.get("GH_TOKEN", ""))
        result = decide(
            api,
            os.environ,
            (ROOT / WORKFLOW).read_text(),
            git("rev-parse", "HEAD^{tree}"),
            event["before"],
        )
    except Exception as exc:
        # Never print URLs/token/API bodies. No error path removes a full gate.
        print(f"Prior evidence unavailable ({type(exc).__name__}); running full CI.")
    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
        for key, value in result.items():
            output.write(f"{key}={value}\n")
    print(f"reuse={result['reuse']}")


if __name__ == "__main__":
    main()
