#!/usr/bin/env python3
"""#11091: reuse only a complete, exact-commit compose PUSH run; uncertainty runs CI.

No PR/synthetic-tree credit. This is test evidence, never a build artifact for
Heroku. The public decision interface always emits reuse=false on uncertainty.
Only the original Actions run can supply the authenticated provenance artifact.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import math
import datetime as dt
import io
import json
import os
from pathlib import Path
import re
import subprocess
import time
import urllib.request
import urllib.parse
import zipfile

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ".github/workflows/ci.yml"
SHA = re.compile(r"[0-9a-f]{40}")
CODEQL_WORKFLOW = ".github/workflows/codeql.yml"
CODEQL_ANALYSIS_KEY = CODEQL_WORKFLOW + ":analyze"
SECURITY_LANGUAGES = ("python", "javascript-typescript")
SARIF_MAX_BYTES = 8_000_000  # >2x the observed 3.54 MB Python snapshot; SARIF ONLY.
# Pending analysis-step rereads: 1/2/4 s, then every 4 s. The sleeps total the
# 75 s API deadline, so that deadline (request time included), never this
# count, ends a pending wait; the count only keeps the reads finite (#11445).
ANALYSIS_READINESS_DELAYS = (1, 2, 4) + (4,) * 17
SECURITY_RECORD_STEP = "Record CodeQL checkout provenance"
SECURITY_QUALIFY_STEP = "Qualify compose security or record master baseline"
SECURITY_PUBLISH_STEP = "Publish CodeQL security receipt"
UUID = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")
REFUSAL = re.compile(r"high|critical|medium|security vulnerabilit", re.I)
# The producer titles its two exit classes so a failed check names its class.
EVIDENCE_INCOMPLETE = "SECURITY EVIDENCE INCOMPLETE"
NEW_FINDING = "SECURITY NEW-FINDING"
CODEQL_ANALYSIS_CHECKS = {
    (f"Analyze ({language})", 15368) for language in SECURITY_LANGUAGES
}
# Integrator 2135Z ruling, explicitly approved by Alex: repair-only transition.
# These remain COMPOSE receipts; the failed master is never called paid.
TRANSITION_BASE = "d714d4a62318175bc750201ad42514eeee595f73"
TRANSITION_TREE = "f3ab18e65903289f3ea8c4acfcc3c49a96fba15d"
TRANSITION_PARENT = "761227a49d721e764edbdd41b3bb357ac584efd5"
TRANSITION_REPOSITORY = "alexander-bain/bainluck"
TRANSITION_REPOSITORY_ID = 1143038283
TRANSITION_MASTER_RUN = 38964094925
TRANSITION_MASTER_ATTEMPT = 2
TRANSITION_RUN = 38962211223
TRANSITION_ATTEMPT = 1
TRANSITION_BRANCH = "integrator/compose-683-11131-d714d4a6"
TRANSITION_SELECTION = "d714-compose-transition"


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
        self.repository_id = None
        self.token = token
        self.deadline = time.monotonic() + 75
        self.opener = urllib.request.build_opener(SafeRedirect())

    def bind_repository(self, repository):
        """Bind numeric pagination aliases to authenticated official run metadata."""
        require(
            _positive(repository.get("id"))
            and isinstance(repository.get("full_name"), str)
            and repository["full_name"].casefold()
            == self.prefix.removeprefix("https://api.github.com/repos/")
            .rstrip("/")
            .casefold()
            and self.repository_id in (None, repository["id"]),
            "foreign repository pagination identity",
        )
        self.repository_id = repository["id"]

    def _response(self, path, limit=2_000_000, accept="application/vnd.github+json"):
        require(
            not path.startswith(("/", "http:", "https:")), "invalid API relative path"
        )
        remaining = self.deadline - time.monotonic()
        require(remaining > 0, "evidence decision deadline")
        request = urllib.request.Request(
            self.prefix + path,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": accept,
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with self.opener.open(request, timeout=min(10, remaining)) as response:
            require(response.status == 200, "non-200 evidence response")
            content = response.read(limit + 1)
            headers = dict(response.headers.items())
        require(len(content) <= limit, "oversize evidence response")
        return content, headers

    def raw(self, path, limit=2_000_000):
        return self._response(path, limit)[0]

    def sarif(self, path):
        """Only this endpoint receives the larger named SARIF byte allowance."""
        require(
            re.fullmatch(r"code-scanning/analyses/[1-9][0-9]*", path),
            "not a SARIF analysis endpoint",
        )
        return json.loads(
            self._response(path, SARIF_MAX_BYTES, "application/sarif+json")[0]
        )

    def array_pages(self, path, *, older_than=None):
        """Read a complete authenticated Link chain, or a complete created-time window.

        older_than is an ISO UTC lower watermark, supported ONLY with explicit
        sort=created&direction=desc. Ties are consumed fully. A page/time/size
        limit before the older watermark or genuine EOF is an error, never a
        clean partial history. Other API payload limits remain 2 MB.
        """
        initial = urllib.parse.urlsplit(self.prefix + path)
        filters = urllib.parse.parse_qs(initial.query, strict_parsing=True)
        require(
            "page" not in filters and "per_page" not in filters,
            "caller pagination is unsupported",
        )
        filters.update({"per_page": ["100"], "page": ["1"]})
        if older_than is not None:
            require(
                filters.get("sort") == ["created"]
                and filters.get("direction") == ["desc"],
                "watermark requires descending created order",
            )
            watermark = stamp(older_than)
        else:
            watermark = None
        current = path + ("&" if "?" in path else "?") + "per_page=100&page=1"
        rows, seen, previous = [], set(), None
        for page in range(1, 21):
            content, headers = self._response(current)
            batch = json.loads(content)
            require(isinstance(batch, list) and len(batch) <= 100, "invalid array page")
            crossed = False
            for row in batch:
                require(
                    isinstance(row, dict)
                    and _positive(row.get("id"))
                    and row["id"] not in seen,
                    "duplicate or invalid analysis ID",
                )
                seen.add(row["id"])
                if watermark is not None:
                    created = stamp(row["created_at"])
                    require(
                        previous is None or created <= previous,
                        "analysis history is not descending",
                    )
                    previous = created
                    crossed |= created < watermark
            rows.extend(batch)
            links = [value for key, value in headers.items() if key.lower() == "link"]
            require(len(links) <= 1, "ambiguous pagination header")
            relations = {}
            if links and links[0].strip():
                for segment in links[0].split(","):
                    match = re.fullmatch(
                        r'\s*<([^<>]+)>;\s*rel="(next|prev|first|last)"\s*', segment
                    )
                    require(
                        match is not None, "malformed or unsupported pagination link"
                    )
                    url, relation = match.groups()
                    require(relation not in relations, "ambiguous pagination relation")
                    target = urllib.parse.urlsplit(url)
                    query = urllib.parse.parse_qs(target.query, strict_parsing=True)
                    require(
                        len(query.get("page", [])) == 1
                        and query["page"][0].isdigit()
                        and int(query["page"][0]) >= 1,
                        "invalid pagination page",
                    )
                    expected = {**filters, "page": query["page"]}
                    canonical_path = (
                        f"/repositories/{self.repository_id}/code-scanning/analyses"
                        if self.repository_id is not None
                        and initial.path.endswith("/code-scanning/analyses")
                        else None
                    )
                    require(
                        target.scheme == "https"
                        and target.netloc == initial.netloc
                        and target.path in (initial.path, canonical_path)
                        and not target.fragment
                        and query == expected,
                        "untrusted or changed pagination link",
                    )
                    relations[relation] = url
            next_links = [relations["next"]] if "next" in relations else []
            if next_links:
                query = urllib.parse.parse_qs(
                    urllib.parse.urlsplit(next_links[0]).query, strict_parsing=True
                )
                require(query["page"] == [str(page + 1)], "skipped or looped next page")
                require(bool(batch), "empty page with a successor")
            if crossed or not next_links:
                return rows
            # GitHub may canonicalize /repos/owner/name to /repositories/ID.
            # After identity validation, keep requests on our original prefix.
            current = (
                initial.path.removeprefix(urllib.parse.urlsplit(self.prefix).path)
                + "?"
                + urllib.parse.urlsplit(next_links[0]).query
            )
        raise ValueError("analysis window pagination bound exceeded")

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
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(
        parsed.tzinfo is not None and parsed.utcoffset() == dt.timedelta(0),
        "timestamp must be UTC",
    )
    return parsed


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
    evidence_failures = []
    security_required = {
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
        # hidden by a later green, except the one narrow CodeQL class below.
        if check["status"] != "completed":
            require(
                suite["head_branch"] == "master",
                "unfinished pre-push security/check evidence",
            )
            continue
        if (
            check["conclusion"] == "failure"
            and suite["head_branch"] == run["head_branch"]
            and (check["name"], check["app"]["id"]) in CODEQL_ANALYSIS_CHECKS
            and not REFUSAL.search((check.get("output") or {}).get("title") or "")
        ):
            # Alex 10/28, narrow: a later receipted pass of this CodeQL run clears an
            # evidence-only failure; tests stay strict so reruns never hide a flake.
            evidence_failures.append(check)
            continue
        require(
            check["conclusion"] != "failure"
            and not REFUSAL.search((check.get("output") or {}).get("title") or ""),
            "security/check refusal",
        )
        identity = (check["name"], check["app"]["id"])
        if suite["head_branch"] == run[
            "head_branch"
        ] and identity in security_required | {("CodeQL", 57789)}:
            # A successful older check cannot pay an unpaid/cancelled rerun.
            # Conservatively require every completed required source check to
            # succeed instead of inferring its workflow attempt from ordering.
            require(check["conclusion"] == "success", "unpaid compose security check")
            security_paid.add(identity)
    require(
        security_required <= security_paid,
        "missing complete compose security checks",
    )
    codeql = validate_security_receipts(
        api,
        runs,
        head,
        tree,
        before,
        repo_id,
        run["head_branch"],
        master_created_at=current["created_at"],
    )
    for failed in evidence_failures:
        clear_evidence_failure(api, failed, checks, suites, codeql)
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


def clear_evidence_failure(api, failed, checks, suites, codeql):
    """Only an earlier evidence-incomplete attempt of the receipted run clears."""
    job = api.get(f"actions/jobs/{failed['id']}")
    require(
        job["id"] == failed["id"]
        and job["name"] == failed["name"]
        and job["head_sha"] == codeql["head_sha"]
        and job["status"] == "completed"
        and job["conclusion"] == "failure",
        "failed CodeQL check identity",
    )
    require(job["run_id"] == codeql["id"], "failed check is not the receipted run")
    require(
        type(job["run_attempt"]) is int
        and 1 <= job["run_attempt"] < codeql["run_attempt"],
        "failed check is not an earlier attempt",
    )
    # Class, from the job: analysis paid, then only the qualifier failed...
    steps = job["steps"]
    names = [step["name"] for step in steps]
    require(names.count(SECURITY_QUALIFY_STEP) == 1, "no single CodeQL qualifier")
    qualifier = names.index(SECURITY_QUALIFY_STEP)
    require(
        "Perform CodeQL Analysis" in names[:qualifier]
        and all(
            (step["status"], step["conclusion"]) == ("completed", "success")
            for step in steps[:qualifier]
        )
        and steps[qualifier]["conclusion"] == "failure"
        and names[qualifier + 1 : qualifier + 2] == [SECURITY_PUBLISH_STEP]
        and steps[qualifier + 1]["conclusion"] == "skipped",
        "failed CodeQL steps are not the evidence-incomplete class",
    )
    # ...and the qualifier's own titled annotation says it was evidence, not a finding.
    notes = api.get(f"check-runs/{failed['id']}/annotations?per_page=100")
    require(isinstance(notes, list) and len(notes) < 100, "unbounded annotations")
    titles = [(note.get("annotation_level"), note.get("title")) for note in notes]
    require(
        titles.count(("failure", EVIDENCE_INCOMPLETE)) == 1
        and not any(title == NEW_FINDING for _, title in titles),
        "failed CodeQL check is not the evidence-incomplete class",
    )
    passes = []
    for check in checks:
        if (
            (check["name"], check["app"]["id"]) == (failed["name"], failed["app"]["id"])
            and check["status"] == "completed"
            and check["conclusion"] == "success"
            and suites[check["check_suite"]["id"]]["head_branch"]
            == codeql["head_branch"]
        ):
            rerun = api.get(f"actions/jobs/{check['id']}")
            passes.append(
                rerun["id"] == check["id"]
                and rerun["name"] == failed["name"]
                and rerun["run_id"] == codeql["id"]
                and rerun["run_attempt"] == codeql["run_attempt"]
                and rerun["head_sha"] == codeql["head_sha"]
                and (rerun["status"], rerun["conclusion"]) == ("completed", "success")
            )
    require(any(passes), "no receipted later pass for the failed CodeQL check")


class NewFinding(ValueError):
    """A known qualifying new CodeQL result: fail before master push."""


class SecurityIncomplete(ValueError):
    """UNKNOWN with a bounded, token-free recovery for the exact base run."""

    def __init__(self, recovery):
        super().__init__("baseline security evidence incomplete")
        self.recovery = recovery


def _positive(value):
    return type(value) is int and value > 0


def _security_context(env, language):
    require(language in SECURITY_LANGUAGES, "unsupported CodeQL language")
    require(env["GITHUB_EVENT_NAME"] == "push", "security producer is push-only")
    require(env.get("GITHUB_JOB") == "analyze", "not the official CodeQL job")
    ref = env["GITHUB_REF"]
    require(
        ref == "refs/heads/master" or ref.startswith("refs/heads/integrator/compose-"),
        "unsupported security push ref",
    )
    require(SHA.fullmatch(env["GITHUB_SHA"]) is not None, "invalid security head")
    repo = env["GITHUB_REPOSITORY"]
    require(
        re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo),
        "invalid security repository",
    )
    return {
        "schema": 1,
        "type": "codeql_security",
        "repository": repo,
        "repository_id": int(env["GITHUB_REPOSITORY_ID"]),
        "head": env["GITHUB_SHA"],
        "ref": ref,
        "event": "push",
        "run_id": int(env["GITHUB_RUN_ID"]),
        "attempt": int(env["GITHUB_RUN_ATTEMPT"]),
        "job": "analyze",
        "role": "baseline" if ref == "refs/heads/master" else "compose",
        "language": language,
        "category": "/language:" + language,
        "analysis_key": CODEQL_ANALYSIS_KEY,
        "environment": {"language": language},
    }


def security_record(env, language):
    """Capture push checkout before analysis; env is the normal Actions mapping."""
    proof = _security_context(env, language)
    require(env.get("GITHUB_JOB") == "analyze", "not the official CodeQL job")
    head, tree, base = (
        git("rev-parse", "HEAD"),
        git("rev-parse", "HEAD^{tree}"),
        git("rev-parse", "origin/master"),
    )
    require(
        head == proof["head"] and SHA.fullmatch(tree) and SHA.fullmatch(base),
        "security checkout mismatch",
    )
    if proof["role"] == "compose":
        subprocess.run(
            ["git", "-C", str(ROOT), "merge-base", "--is-ancestor", base, head],
            check=True,
            timeout=10,
        )
    return {**proof, "tree": tree, "base": base}


def _validate_codeql_run(
    run, head, branch, repo_id, *, attempt=None, successful=True, queued=False
):
    require(
        run["path"] == CODEQL_WORKFLOW
        and run["event"] == "push"
        and run["head_sha"] == head
        and run["head_branch"] == branch,
        "wrong official CodeQL run",
    )
    require(
        run["repository"]["id"] == repo_id and run["head_repository"]["id"] == repo_id,
        "foreign CodeQL run",
    )
    require(
        _positive(run["id"]) and _positive(run["run_attempt"]), "invalid CodeQL attempt"
    )
    require(
        attempt is None or run["run_attempt"] == attempt, "CodeQL latest attempt moved"
    )
    if successful:
        require(
            run["status"] == "completed" and run["conclusion"] == "success",
            "CodeQL latest attempt not successful",
        )
    else:
        require(
            run["status"] == "in_progress"
            or (queued and run["status"] == "queued" and run["conclusion"] is None)
            or (run["status"] == "completed" and run["conclusion"] == "success"),
            "CodeQL producer attempt unpaid",
        )


def _official_jobs(api, run, *, producer=False):
    jobs = api.pages(f"actions/runs/{run['id']}/jobs?filter=latest", "jobs")
    require(len(jobs) == len(SECURITY_LANGUAGES), "wrong CodeQL matrix membership")
    mapped = {}
    for language in SECURITY_LANGUAGES:
        selected = [job for job in jobs if job["name"] == f"Analyze ({language})"]
        require(len(selected) == 1, "missing or duplicate official CodeQL job")
        job = selected[0]
        require(
            job["run_attempt"] == run["run_attempt"]
            and job["status"] == "completed"
            and job["conclusion"] == "success",
            "unpaid official CodeQL job",
        )
        required = ["Perform CodeQL Analysis"]
        if producer:
            required += [
                SECURITY_RECORD_STEP,
                SECURITY_QUALIFY_STEP,
                SECURITY_PUBLISH_STEP,
            ]
        for name in required:
            steps = [step for step in job["steps"] if step["name"] == name]
            require(
                len(steps) == 1
                and steps[0]["status"] == "completed"
                and steps[0]["conclusion"] == "success",
                "unpaid CodeQL producer/analysis step",
            )
        analysis = next(
            step for step in job["steps"] if step["name"] == "Perform CodeQL Analysis"
        )
        require(
            stamp(analysis["started_at"]) <= stamp(analysis["completed_at"]),
            "invalid analysis step window",
        )
        mapped[language] = {"job": job, "step": analysis}
    return mapped


def _security_diagnostic(checkpoint, **fields):
    """Print only fixed checkpoints and bounded, allowlisted primitive fields.

    Never render an API string, exception, URL, environment or response body.
    Unrecognized values are represented by a fixed sentinel.
    """
    checkpoints = {
        "context",
        "provenance",
        "run-lookup",
        "run-validation",
        "liveness-witness",
        "repository-binding",
        "jobs-lookup",
        "matrix-membership",
        "matrix-attempts",
        "producer-job",
        "analysis-step",
        "analysis-window",
        "analysis-readiness-wait",
        "upload-lookup",
        "upload-count",
        "upload-identity",
        "upload-processing",
        "upload-window",
        "candidate-snapshot",
        "baseline",
        "alert-comparison",
        "analysis-reread",
        "run-reread",
        "run-revalidation",
        "liveness-rebind",
        "qualified",
    }
    numeric = {
        "run_id",
        "attempt",
        "expected_attempt",
        "job_id",
        "job_attempt",
        "matrix_count",
        "step_count",
        "upload_count",
        "analysis_id",
        "read_count",
        "wait_seconds",
        "rules_count",
        "results_count",
    }
    enums = {
        "status": {
            "queued",
            "waiting",
            "pending",
            "requested",
            "in_progress",
            "completed",
        },
        "conclusion": {
            "success",
            "failure",
            "cancelled",
            "timed_out",
            "skipped",
            "neutral",
            "action_required",
            "stale",
            "startup_failure",
        },
        "language": set(SECURITY_LANGUAGES),
        "processing_error": {"none", "present"},
        "processing_warning": {"none", "present"},
    }
    label = checkpoint if checkpoint in checkpoints else "untrusted"
    values = []
    for key in sorted(fields):
        value = fields[key]
        if key in numeric:
            safe = (
                str(value)
                if type(value) is int and 0 <= value <= 10**15
                else "untrusted"
            )
        elif key in enums:
            safe = (
                "null"
                if value is None
                else (
                    value if type(value) is str and value in enums[key] else "untrusted"
                )
            )
        else:
            continue
        values.append(f"{key}={safe}")
    print("SECURITY CHECKPOINT " + label + (" " + " ".join(values) if values else ""))


def _producer_run(api, expected, branch):
    """Read and fully validate the producer's own attempt once.

    The runs API can report the exact attempt `queued conclusion=null` for
    minutes while its own jobs run (#11445, 39793061366 attempts 1 and 2), so
    a queued read is returned unpaid: it qualifies nothing unless the
    producer's own executing job and completed analysis step witness it.
    """
    require(time.monotonic() < api.deadline, "evidence decision deadline")
    run = api.get(f"actions/runs/{expected['run_id']}")
    require(time.monotonic() < api.deadline, "evidence decision deadline")
    _security_diagnostic(
        "run-validation",
        run_id=run.get("id"),
        attempt=run.get("run_attempt"),
        expected_attempt=expected["attempt"],
        status=run.get("status"),
        conclusion=run.get("conclusion"),
    )
    _validate_codeql_run(
        run,
        expected["head"],
        branch,
        expected["repository_id"],
        attempt=expected["attempt"],
        successful=False,
        queued=True,
    )
    return run


def _producer_analysis_step(api, run, language, *, diagnostic=False, rebind=None):
    """Bounded rereads of only the observed current analysis-step pending state.

    All other states/errors refuse immediately. Identity pins and the original
    API deadline survive every read; the selected step must still finish green.
    The jobs API can lag the finished step by more than 7 s (#11445), so a
    pending read waits on until the next wait would reach that same deadline.
    A queued run read is witnessed only by every job of this exact run, head
    and attempt with the producer's own job executing since before its
    analysis step started. `rebind` is the identity a final reread must
    match on its first read, with no wait. Returns (step, identity).
    """
    witness = run["status"] == "queued"
    pinned = rebind
    for read_index in range(len(ANALYSIS_READINESS_DELAYS) + 1):
        require(time.monotonic() < api.deadline, "evidence decision deadline")
        if diagnostic:
            _security_diagnostic("jobs-lookup")
        jobs = api.pages(f"actions/runs/{run['id']}/jobs?filter=latest", "jobs")
        require(time.monotonic() < api.deadline, "evidence decision deadline")
        if diagnostic:
            _security_diagnostic("matrix-membership", matrix_count=len(jobs))
        require(
            len(jobs) == len(SECURITY_LANGUAGES)
            and {job["name"] for job in jobs}
            == {f"Analyze ({lang})" for lang in SECURITY_LANGUAGES},
            "wrong producer matrix membership",
        )
        if diagnostic:
            _security_diagnostic("matrix-attempts")
            for item in jobs:
                _security_diagnostic(
                    "matrix-attempts",
                    job_id=item.get("id"),
                    job_attempt=item.get("run_attempt"),
                    expected_attempt=run.get("run_attempt"),
                )
        require(
            all(job["run_attempt"] == run["run_attempt"] for job in jobs),
            "mixed producer attempts; re-run ALL jobs of this exact CodeQL run",
        )
        job = next(job for job in jobs if job["name"] == f"Analyze ({language})")
        if diagnostic:
            _security_diagnostic(
                "producer-job",
                language=language,
                job_id=job.get("id"),
                job_attempt=job.get("run_attempt"),
                status=job.get("status"),
                conclusion=job.get("conclusion"),
            )
        require(
            job["run_attempt"] == run["run_attempt"]
            and (
                (job["status"] == "in_progress" and job["conclusion"] is None)
                or (job["status"] == "completed" and job["conclusion"] == "success")
            ),
            "producer job belongs to an unpaid attempt",
        )
        steps = [
            step for step in job["steps"] if step["name"] == "Perform CodeQL Analysis"
        ]
        if diagnostic:
            _security_diagnostic("analysis-step", step_count=len(steps))
            if len(steps) == 1:
                _security_diagnostic(
                    "analysis-step",
                    status=steps[0].get("status"),
                    conclusion=steps[0].get("conclusion"),
                )
        require(len(steps) == 1, "producer analysis step is unpaid")
        step = steps[0]
        require(
            _positive(job["id"]) and _positive(step["number"]),
            "invalid producer step identity",
        )
        require(
            all(
                _positive(item["id"]) and _positive(item["run_attempt"])
                for item in jobs
            )
            and len({item["id"] for item in jobs}) == len(jobs),
            "invalid producer matrix identity",
        )
        stamp(step["started_at"])
        identity = (
            tuple(
                sorted((item["id"], item["name"], item["run_attempt"]) for item in jobs)
            ),
            job["id"],
            step["number"],
            step["name"],
            step["started_at"],
        )
        require(
            pinned is None or pinned == identity, "producer readiness identity moved"
        )
        pinned = identity
        if witness:
            if diagnostic:
                _security_diagnostic(
                    "liveness-witness",
                    job_id=job.get("id"),
                    job_attempt=job.get("run_attempt"),
                    status=job.get("status"),
                    conclusion=job.get("conclusion"),
                )
            require(
                job["status"] == "in_progress"
                and job["conclusion"] is None
                and all(
                    item["run_id"] == run["id"]
                    and item["head_sha"] == run["head_sha"]
                    and item["head_branch"] == run["head_branch"]
                    for item in jobs
                )
                and isinstance(job["started_at"], str)
                and stamp(job["started_at"]) <= stamp(step["started_at"]),
                "producer liveness witness unpaid",
            )
        if step["status"] == "completed" and step["conclusion"] == "success":
            if diagnostic:
                _security_diagnostic("analysis-window")
            require(
                stamp(step["started_at"]) <= stamp(step["completed_at"]),
                "invalid producer analysis window",
            )
            return step, identity
        pending = (
            job["status"] == "in_progress"
            and job["conclusion"] is None
            and step["status"] == "in_progress"
            and step["conclusion"] is None
            and step["completed_at"] is None
        )
        require(
            pending and rebind is None and read_index < len(ANALYSIS_READINESS_DELAYS),
            "producer analysis step is unpaid",
        )
        delay = ANALYSIS_READINESS_DELAYS[read_index]
        require(time.monotonic() + delay < api.deadline, "evidence decision deadline")
        if diagnostic:
            _security_diagnostic(
                "analysis-readiness-wait", read_count=read_index + 1, wait_seconds=delay
            )
        time.sleep(delay)
    raise ValueError("producer analysis step is unpaid")


def _analysis_identity(metadata):
    return {
        key: metadata[key]
        for key in (
            "id",
            "sarif_id",
            "ref",
            "commit_sha",
            "analysis_key",
            "category",
            "environment",
            "created_at",
            "tool",
            "error",
            "warning",
            "results_count",
            "rules_count",
        )
    }


def _validate_analysis(metadata, head, ref, language, *, sarif_id=None):
    require(
        _positive(metadata["id"]) and UUID.fullmatch(metadata["sarif_id"]),
        "invalid analysis/upload ID",
    )
    require(
        sarif_id is None or metadata["sarif_id"].lower() == sarif_id.lower(),
        "wrong SARIF upload",
    )
    require(
        metadata["commit_sha"] == head and metadata["ref"] == ref,
        "wrong analysis revision/ref",
    )
    require(
        metadata["analysis_key"] == CODEQL_ANALYSIS_KEY
        and metadata["category"] == "/language:" + language
        and json.loads(metadata["environment"]) == {"language": language},
        "wrong analysis key/category/environment",
    )
    require(
        metadata["tool"]["name"] == "CodeQL" and bool(metadata["tool"]["version"]),
        "wrong analysis tool",
    )
    require(
        metadata["error"] == "" and metadata["warning"] == "",
        "analysis processing incomplete or warned",
    )
    require(
        type(metadata["results_count"]) is int
        and metadata["results_count"] >= 0
        and _positive(metadata["rules_count"]),
        "missing analysis coverage/counts",
    )
    stamp(metadata["created_at"])


def parse_security_snapshot(sarif, metadata, repository):
    """Validate GitHub SARIF; return canonical IDs, qualifying IDs and query profile.

    Native github/alertNumber is the identity. Both driver AND extensions map
    rules. The effective level follows SARIF's result override, rule default,
    then the specified default warning. No local fingerprints excuse a result.
    """
    require(
        sarif["version"] == "2.1.0" and len(sarif["runs"]) == 1,
        "unsupported SARIF shape",
    )
    run = sarif["runs"][0]
    vcs = run["versionControlProvenance"]
    require(
        len(vcs) == 1
        and vcs[0]["revisionId"] == metadata["commit_sha"]
        and vcs[0]["branch"] == metadata["ref"]
        and vcs[0]["repositoryUri"].rstrip("/") == f"https://github.com/{repository}",
        "wrong SARIF VCS identity",
    )
    driver = run["tool"]["driver"]
    require(
        driver["name"] == "CodeQL"
        and driver.get("semanticVersion", driver.get("version"))
        == metadata["tool"]["version"],
        "wrong SARIF tool version",
    )
    require(
        run["automationDetails"]["id"].rstrip("/") == metadata["category"].rstrip("/"),
        "wrong SARIF automation category",
    )
    extensions = run["tool"].get("extensions", [])
    require(isinstance(extensions, list), "invalid SARIF extensions")
    rules = {}
    for component in [driver] + extensions:
        for rule in component.get("rules", []):
            require(
                isinstance(rule.get("id"), str)
                and rule["id"]
                and rule["id"] not in rules,
                "duplicate/unknown rule ID",
            )
            rules[rule["id"]] = rule
    require(len(rules) == metadata["rules_count"], "incomplete SARIF rules")
    results = run["results"]
    require(
        isinstance(results, list) and len(results) == metadata["results_count"],
        "incomplete SARIF results",
    )
    alerts, qualifying = {}, []
    for result in results:
        # Official retained uploads use ruleId plus the modern rule reference.
        # A legacy top-level index is an additional identity claim; never ignore
        # it, even when it happens to agree with the supported representation.
        require("ruleIndex" not in result, "unsupported legacy result ruleIndex")
        identity = result["properties"]["github/alertNumber"]
        require(
            _positive(identity) and identity not in alerts,
            "missing/duplicate native alert ID",
        )
        url = result["properties"].get("github/alertUrl")
        require(
            url is None
            or url
            == f"https://api.github.com/repos/{repository}/code-scanning/alerts/{identity}",
            "foreign native alert URL",
        )
        rule_id = result["ruleId"]
        require(rule_id in rules, "result references an unknown rule")
        reference = result.get("rule", {})
        require(reference.get("id", rule_id) == rule_id, "ambiguous result rule")
        if "index" in reference:
            component_ref = reference.get("toolComponent")
            if component_ref is None:
                component = driver
            else:
                index = component_ref["index"]
                require(
                    type(index) is int and 0 <= index < len(extensions),
                    "invalid extension reference",
                )
                component = extensions[index]
            index = reference["index"]
            require(
                type(index) is int
                and 0 <= index < len(component.get("rules", []))
                and component["rules"][index]["id"] == rule_id,
                "inconsistent indexed rule",
            )
        rule = rules[rule_id]
        properties = rule.get("properties", {})
        tags = properties.get("tags", [])
        require(
            isinstance(tags, list) and all(isinstance(tag, str) for tag in tags),
            "invalid rule tags",
        )
        score = properties.get("security-severity")
        if score is not None:
            require(type(score) in (str, int, float), "invalid security severity type")
            score = float(score)
            require(
                math.isfinite(score) and 0 <= score <= 10, "invalid security severity"
            )
        else:
            require("security" not in tags, "security rule lacks severity")
        default = rule.get("defaultConfiguration", {})
        require(isinstance(default, dict), "invalid default rule configuration")
        level = result.get("level", default.get("level", "warning"))
        require(
            level in ("none", "note", "warning", "error"),
            "unsupported effective SARIF level",
        )
        qualifies = (score is not None and score >= 4) or level == "error"
        alerts[identity] = {"rule_id": rule_id, "level": level, "qualifying": qualifies}
        if qualifies:
            qualifying.append(identity)
    profile = {
        "tool": run["tool"],
        "metadata_tool": metadata["tool"],
        "configuration": run.get("properties", {}),
    }
    return {
        "alerts": alerts,
        "qualifying_ids": sorted(qualifying),
        "profile": profile,
        "results_count": len(results),
        "rules_count": len(rules),
        "sarif_digest": hashlib.sha256(
            json.dumps(sarif, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }


def compare_security_snapshots(base, candidate):
    """Return canonical new IDs; a profile/classification change is UNKNOWN."""
    require(
        base["profile"] == candidate["profile"],
        "CodeQL query/tool/severity profile changed",
    )
    for identity in base["alerts"].keys() & candidate["alerts"].keys():
        require(
            base["alerts"][identity] == candidate["alerts"][identity],
            "inherited alert classification changed",
        )
    new_ids = sorted(candidate["alerts"].keys() - base["alerts"].keys())
    qualifying = sorted(set(new_ids) & set(candidate["qualifying_ids"]))
    if qualifying:
        raise NewFinding(
            "new qualifying GitHub alert IDs: " + ",".join(str(i) for i in qualifying)
        )
    return {"new_alert_ids": new_ids, "new_qualifying_ids": []}


def _security_artifact(api, artifacts, run, language):
    name = f"codeql-security-{run['run_attempt']}-{language}"
    selected = [artifact for artifact in artifacts if artifact["name"] == name]
    require(
        len(selected) == 1 and not selected[0]["expired"],
        "missing/ambiguous security receipt; rerun the exact CodeQL run with a fresh full attempt",
    )
    archive = zipfile.ZipFile(
        io.BytesIO(api.raw(f"actions/artifacts/{selected[0]['id']}/zip", 1_000_000))
    )
    require(
        archive.namelist() == ["codeql-security.json"]
        and archive.getinfo("codeql-security.json").file_size <= 64_000,
        "invalid security receipt archive",
    )
    return json.loads(archive.read("codeql-security.json"))


def _receipt_identity(
    receipt, run, repo_id, language, *, role, head, tree=None, base=None
):
    require(
        receipt["schema"] == 1
        and receipt["type"] == "codeql_security"
        and receipt["job"] == "analyze"
        and receipt["role"] == role,
        "wrong security receipt type/role",
    )
    require(
        receipt["repository_id"] == repo_id
        and receipt["head"] == head
        and receipt["event"] == "push"
        and receipt["ref"] == f"refs/heads/{run['head_branch']}"
        and receipt["run_id"] == run["id"]
        and receipt["attempt"] == run["run_attempt"],
        "security receipt source/run mismatch",
    )
    require(
        SHA.fullmatch(receipt["tree"]) and SHA.fullmatch(receipt["base"]),
        "invalid security receipt source",
    )
    require(tree is None or receipt["tree"] == tree, "security receipt tree mismatch")
    require(base is None or receipt["base"] == base, "security receipt base mismatch")
    require(
        receipt["language"] == language
        and receipt["category"] == "/language:" + language
        and receipt["analysis_key"] == CODEQL_ANALYSIS_KEY
        and receipt["environment"] == {"language": language},
        "security receipt category mismatch",
    )
    require(
        _positive(receipt["analysis_id"]) and UUID.fullmatch(receipt["sarif_id"]),
        "invalid receipt analysis/upload",
    )
    require(
        type(receipt["results_count"]) is int
        and receipt["results_count"] >= 0
        and _positive(receipt["rules_count"]),
        "invalid receipt coverage",
    )
    if role == "compose":
        require(
            receipt["qualified"] is True
            and receipt["qualification"] == "PASS"
            and receipt["delta"]["new_qualifying_ids"] == [],
            "compose security is not qualified",
        )
        baseline = receipt["baseline"]
        require(
            baseline["head"] == base
            and _positive(baseline["run_id"])
            and _positive(baseline["attempt"])
            and _positive(baseline["analysis_id"])
            and UUID.fullmatch(baseline["sarif_id"])
            and baseline["selection"]
            in ("receipt", "legacy-window", TRANSITION_SELECTION),
            "invalid qualified baseline identity",
        )
        if baseline["selection"] == TRANSITION_SELECTION:
            require(
                base == TRANSITION_BASE
                and baseline["run_id"] == TRANSITION_RUN
                and baseline["attempt"] == TRANSITION_ATTEMPT,
                "foreign transition baseline",
            )
    else:
        require(
            receipt["qualified"] is False
            and receipt["qualification"] == "BASELINE"
            and receipt["baseline"] is None
            and receipt["delta"] is None,
            "baseline receipt is not an analysis-only record",
        )


def _base_declares_producer(api, base):
    content = api.get(f"contents/{CODEQL_WORKFLOW}?ref={base}")
    require(
        content["type"] == "file" and content["encoding"] == "base64",
        "missing exact base workflow",
    )
    text = base64.b64decode(
        re.sub(r"\s+", "", content["content"]), validate=True
    ).decode()
    markers = [
        bool(
            re.search(
                r"^      - name: [\"']?" + re.escape(name) + r"[\"']?\s*$", text, re.M
            )
        )
        for name in (SECURITY_RECORD_STEP, SECURITY_QUALIFY_STEP, SECURITY_PUBLISH_STEP)
    ]
    require(
        all(markers) or not any(markers), "partial security producer in base workflow"
    )
    require(
        any(markers) or "--security-" not in text, "unrecognized base security producer"
    )
    return all(markers)


def _transition_base_security(api, master, base, repo_id, language):
    """One explicitly ruled exact-base transition; no failed receipt promotion."""
    require(
        base == TRANSITION_BASE
        and repo_id == TRANSITION_REPOSITORY_ID
        and master["id"] == TRANSITION_MASTER_RUN
        and master["run_attempt"] == TRANSITION_MASTER_ATTEMPT
        and master["head_sha"] == base
        and master["head_branch"] == "master"
        and master["path"] == CODEQL_WORKFLOW
        and master["event"] == "push"
        and master["status"] == "completed"
        and master["conclusion"] == "failure"
        and master["repository"]["id"] == repo_id
        and master["head_repository"]["id"] == repo_id
        and master["repository"]["full_name"] == TRANSITION_REPOSITORY,
        "transition is not the ruled unpaid master attempt",
    )
    if isinstance(api, API):
        api.bind_repository(master["repository"])

    def current_master():
        ref = api.get("git/ref/heads/master")
        require(
            ref["ref"] == "refs/heads/master"
            and ref["object"]["type"] == "commit"
            and ref["object"]["sha"] == base,
            "master moved; transition ruling is void",
        )

    current_master()
    commit = api.get(f"git/commits/{base}")
    require(
        commit["sha"] == base and commit["tree"]["sha"] == TRANSITION_TREE,
        "transition base tree mismatch",
    )
    run = api.get(f"actions/runs/{TRANSITION_RUN}")
    _validate_codeql_run(
        run, base, TRANSITION_BRANCH, repo_id, attempt=TRANSITION_ATTEMPT
    )
    require(
        run["repository"]["full_name"] == TRANSITION_REPOSITORY,
        "foreign transition repository",
    )
    jobs = _official_jobs(api, run, producer=True)
    artifacts = api.pages(f"actions/runs/{run['id']}/artifacts", "artifacts")
    selected = {}
    for lang in SECURITY_LANGUAGES:
        receipt = _security_artifact(api, artifacts, run, lang)
        _receipt_identity(
            receipt,
            run,
            repo_id,
            lang,
            role="compose",
            head=base,
            tree=TRANSITION_TREE,
            base=TRANSITION_PARENT,
        )
        require(
            receipt["repository"] == TRANSITION_REPOSITORY,
            "foreign transition receipt",
        )
        metadata = api.get(f"code-scanning/analyses/{receipt['analysis_id']}")
        _validate_analysis(
            metadata,
            base,
            f"refs/heads/{TRANSITION_BRANCH}",
            lang,
            sarif_id=receipt["sarif_id"],
        )
        step = jobs[lang]["step"]
        require(
            stamp(step["started_at"])
            <= stamp(metadata["created_at"])
            <= stamp(step["completed_at"]),
            "transition upload outside official attempt",
        )
        snapshot = parse_security_snapshot(
            api.sarif(f"code-scanning/analyses/{metadata['id']}"),
            metadata,
            TRANSITION_REPOSITORY,
        )
        require(
            metadata["results_count"] == receipt["results_count"]
            and metadata["rules_count"] == receipt["rules_count"]
            and snapshot["sarif_digest"] == receipt["sarif_digest"]
            and len(snapshot["qualifying_ids"]) == receipt["qualifying_count"],
            "transition receipt snapshot mismatch",
        )
        reread = api.get(f"code-scanning/analyses/{metadata['id']}")
        require(
            _analysis_identity(reread) == _analysis_identity(metadata),
            "transition analysis moved",
        )
        selected[lang] = {
            "run": run,
            "metadata": metadata,
            "snapshot": snapshot,
            "selection": TRANSITION_SELECTION,
        }
    latest = api.get(f"actions/runs/{run['id']}")
    _validate_codeql_run(
        latest, base, TRANSITION_BRANCH, repo_id, attempt=TRANSITION_ATTEMPT
    )
    require(latest["updated_at"] == run["updated_at"], "transition source moved")
    require(
        api.get(f"actions/runs/{master['id']}") == master,
        "master baseline changed during transition",
    )
    current_master()
    return selected[language]


def select_base_security(api, base, repo_id, language):
    """Select exact successful master CodeQL attempt and one complete analysis.

    Future bases use authenticated receipts. Only an exact workflow predating
    the producer may bootstrap through its complete official analysis-step time
    window. The array paginator must reach an older watermark/EOF, never merely
    a bounded prefix. Return run/metadata/snapshot/selection for qualification.
    """
    require(
        SHA.fullmatch(base) and language in SECURITY_LANGUAGES,
        "invalid security baseline",
    )
    rows = api.pages(
        f"actions/runs?head_sha={base}&branch=master&event=push", "workflow_runs"
    )
    candidates = [row for row in rows if row.get("path") == CODEQL_WORKFLOW]
    require(len(candidates) == 1, "missing or ambiguous exact base CodeQL run")
    row = candidates[0]
    try:
        run = api.get(f"actions/runs/{row['id']}")
        require(
            run["id"] == row["id"] and run["run_attempt"] == row["run_attempt"],
            "baseline listing/latest attempt mismatch",
        )
        # A paid ordinary master always wins. No exception catch selects this
        # path: API errors, missing receipts and any other failure still refuse.
        if (
            base == TRANSITION_BASE
            and run["status"] == "completed"
            and run["conclusion"] == "failure"
        ):
            return _transition_base_security(api, run, base, repo_id, language)
        _validate_codeql_run(run, base, "master", repo_id, attempt=row["run_attempt"])
        if isinstance(api, API):
            api.bind_repository(run["repository"])
        declared = _base_declares_producer(api, base)
        jobs = _official_jobs(api, run, producer=declared)
        if declared:
            artifacts = api.pages(f"actions/runs/{run['id']}/artifacts", "artifacts")
            # Both categories must have receipts; no legacy escape for a failed or
            # incomplete declared producer. Rerun that exact master CodeQL run.
            receipts = {
                lang: _security_artifact(api, artifacts, run, lang)
                for lang in SECURITY_LANGUAGES
            }
            for lang, receipt in receipts.items():
                _receipt_identity(
                    receipt, run, repo_id, lang, role="baseline", head=base
                )
            receipt = receipts[language]
            metadata = api.get(f"code-scanning/analyses/{receipt['analysis_id']}")
            _validate_analysis(
                metadata,
                base,
                "refs/heads/master",
                language,
                sarif_id=receipt["sarif_id"],
            )
            require(
                metadata["results_count"] == receipt["results_count"]
                and metadata["rules_count"] == receipt["rules_count"],
                "baseline receipt count mismatch",
            )
            selection = "receipt"
        else:
            earliest = min(item["step"]["started_at"] for item in jobs.values())
            rows = api.array_pages(
                "code-scanning/analyses?ref=refs%2Fheads%2Fmaster&tool_name=CodeQL&sort=created&direction=desc",
                older_than=earliest,
            )
            selected = {}
            for lang, item in jobs.items():
                step = item["step"]
                matches = [
                    meta
                    for meta in rows
                    if meta.get("commit_sha") == base
                    and meta.get("ref") == "refs/heads/master"
                    and meta.get("category") == "/language:" + lang
                    and stamp(step["started_at"])
                    <= stamp(meta["created_at"])
                    <= stamp(step["completed_at"])
                ]
                require(
                    len(matches) == 1, "ambiguous/incomplete legacy analysis window"
                )
                _validate_analysis(matches[0], base, "refs/heads/master", lang)
                selected[lang] = matches[0]
            metadata = selected[language]
            selection = "legacy-window"
        step = jobs[language]["step"]
        require(
            stamp(step["started_at"])
            <= stamp(metadata["created_at"])
            <= stamp(step["completed_at"]),
            "baseline upload outside official latest attempt",
        )
        reread = api.get(f"code-scanning/analyses/{metadata['id']}")
        require(
            _analysis_identity(reread) == _analysis_identity(metadata),
            "baseline analysis moved",
        )
        repository = run["repository"]["full_name"]
        snapshot = parse_security_snapshot(
            api.sarif(f"code-scanning/analyses/{metadata['id']}"), metadata, repository
        )
        latest = api.get(f"actions/runs/{run['id']}")
        _validate_codeql_run(
            latest, base, "master", repo_id, attempt=run["run_attempt"]
        )
        return {
            "run": run,
            "metadata": metadata,
            "snapshot": snapshot,
            "selection": selection,
        }
    except Exception as exc:
        run_id = row["id"] if _positive(row.get("id")) else "unknown"
        raise SecurityIncomplete(
            f"Recovery: if the master baseline producer/receipt is unpaid, re-run the exact master CodeQL run {run_id} with a fresh full attempt. "
            "Declared producers never use legacy bootstrap. Repair API/identity uncertainty as applicable, then use a fresh full attempt of the exact compose CodeQL run. "
            "No manual override; a full test run does not clear security uncertainty."
        ) from exc


def qualify_security(api, env, provenance, sarif_id, language):
    """Produce a baseline or paid compose receipt; errors are UNKNOWN to the CLI."""
    _security_diagnostic("context", language=language)
    expected = _security_context(env, language)
    _security_diagnostic("provenance")
    for key, value in expected.items():
        require(
            provenance[key] == value, "security checkout provenance context mismatch"
        )
    require(
        SHA.fullmatch(provenance["tree"]) and SHA.fullmatch(provenance["base"]),
        "invalid security checkout provenance",
    )
    require(UUID.fullmatch(sarif_id), "missing official SARIF upload output")
    _security_diagnostic(
        "run-lookup", run_id=expected["run_id"], expected_attempt=expected["attempt"]
    )
    branch = expected["ref"].removeprefix("refs/heads/")
    run = _producer_run(api, expected, branch)
    _security_diagnostic("repository-binding")
    if isinstance(api, API):
        api.bind_repository(run["repository"])
    upload_step, pinned_witness = _producer_analysis_step(
        api, run, language, diagnostic=True
    )
    _security_diagnostic("upload-lookup")
    rows = api.array_pages(
        "code-scanning/analyses?sarif_id=" + urllib.parse.quote(sarif_id, safe="")
    )
    _security_diagnostic("upload-count", upload_count=len(rows))
    require(len(rows) == 1, "missing or ambiguous actual SARIF upload")
    metadata = rows[0]
    _security_diagnostic("upload-identity", analysis_id=metadata.get("id"))
    # GitHub can finish an upload yet record the analysis as failed: 2cd03b03
    # attempt 1 python read error "Unknown Error" with 0 rules, unchanged an
    # hour later, while its rerun read 172 rules. That is not a race a wait can
    # fix; name it here so the log says "rerun" without exposing the string.
    _security_diagnostic(
        "upload-processing",
        processing_error="none" if metadata.get("error") == "" else "present",
        processing_warning="none" if metadata.get("warning") == "" else "present",
        rules_count=metadata.get("rules_count"),
        results_count=metadata.get("results_count"),
    )
    _validate_analysis(
        metadata, expected["head"], expected["ref"], language, sarif_id=sarif_id
    )
    _security_diagnostic("upload-window")
    require(
        stamp(upload_step["started_at"])
        <= stamp(metadata["created_at"])
        <= stamp(upload_step["completed_at"]),
        "SARIF upload is outside the current official analysis attempt",
    )
    _security_diagnostic("candidate-snapshot")
    snapshot = parse_security_snapshot(
        api.sarif(f"code-scanning/analyses/{metadata['id']}"),
        metadata,
        expected["repository"],
    )
    receipt = {
        **provenance,
        "sarif_id": metadata["sarif_id"],
        "analysis_id": metadata["id"],
        "results_count": snapshot["results_count"],
        "rules_count": snapshot["rules_count"],
        "sarif_digest": snapshot["sarif_digest"],
        "qualifying_count": len(snapshot["qualifying_ids"]),
        "qualified": False,
        "qualification": "BASELINE",
        "baseline": None,
        "delta": None,
    }
    if expected["role"] == "compose":
        _security_diagnostic("baseline")
        base = select_base_security(
            api, provenance["base"], expected["repository_id"], language
        )
        _security_diagnostic("alert-comparison")
        delta = compare_security_snapshots(base["snapshot"], snapshot)
        receipt.update(
            {
                "qualified": True,
                "qualification": "PASS",
                "delta": delta,
                "baseline": {
                    "head": provenance["base"],
                    "run_id": base["run"]["id"],
                    "attempt": base["run"]["run_attempt"],
                    "analysis_id": base["metadata"]["id"],
                    "sarif_id": base["metadata"]["sarif_id"],
                    "selection": base["selection"],
                },
            }
        )
    _security_diagnostic("analysis-reread")
    reread = api.get(f"code-scanning/analyses/{metadata['id']}")
    require(
        _analysis_identity(reread) == _analysis_identity(metadata),
        "candidate analysis moved",
    )
    _security_diagnostic("run-reread")
    latest = api.get(f"actions/runs/{run['id']}")
    _security_diagnostic(
        "run-revalidation",
        run_id=latest.get("id"),
        attempt=latest.get("run_attempt"),
        expected_attempt=expected["attempt"],
        status=latest.get("status"),
        conclusion=latest.get("conclusion"),
    )
    _validate_codeql_run(
        latest,
        expected["head"],
        branch,
        expected["repository_id"],
        attempt=expected["attempt"],
        successful=False,
        queued=True,
    )
    if latest["status"] == "queued":
        _security_diagnostic("liveness-rebind")
        rebound, _ = _producer_analysis_step(
            api, latest, language, rebind=pinned_witness
        )
        require(rebound == upload_step, "producer liveness witness moved")
    if receipt["baseline"] and receipt["baseline"]["selection"] == TRANSITION_SELECTION:
        require(
            api.get("git/ref/heads/master")["object"]["sha"] == TRANSITION_BASE,
            "master moved before transition qualification",
        )
    _security_diagnostic("qualified")
    return receipt


def validate_security_receipts(
    api, runs, head, tree, before, repo_id, branch, *, master_created_at=None
):
    """Master consumes both qualified receipts from one current CodeQL attempt."""
    rows = [
        row
        for row in runs
        if row.get("path") == CODEQL_WORKFLOW
        and row.get("event") == "push"
        and row.get("head_branch") == branch
    ]
    require(len(rows) == 1, "missing or ambiguous compose CodeQL run")
    row = rows[0]
    run = api.get(f"actions/runs/{row['id']}")
    _validate_codeql_run(run, head, branch, repo_id, attempt=row["run_attempt"])
    if master_created_at is not None:
        age = (stamp(master_created_at) - stamp(run["updated_at"])).total_seconds()
        require(
            0 <= age <= 3 * 3600,
            "security source not paid within the pre-push evidence window",
        )
    _official_jobs(api, run, producer=True)
    artifacts = api.pages(f"actions/runs/{run['id']}/artifacts", "artifacts")
    transition = False
    for language in SECURITY_LANGUAGES:
        receipt = _security_artifact(api, artifacts, run, language)
        _receipt_identity(
            receipt,
            run,
            repo_id,
            language,
            role="compose",
            head=head,
            tree=tree,
            base=before,
        )
        require(
            receipt["repository"] == run["repository"]["full_name"],
            "foreign security receipt repository",
        )
        transition |= receipt["baseline"]["selection"] == TRANSITION_SELECTION
    latest = api.get(f"actions/runs/{run['id']}")
    _validate_codeql_run(latest, head, branch, repo_id, attempt=run["run_attempt"])
    require(
        latest["updated_at"] == run["updated_at"],
        "CodeQL source updated during decision",
    )
    require(not transition, "transition requires full master tests; no evidence reuse")
    return latest


def _security_recovery(env):
    run_id = env.get("GITHUB_RUN_ID", "unknown")
    if not str(run_id).isdigit():
        run_id = "unknown"
    if env.get("GITHUB_REF") == "refs/heads/master":
        try:
            event_path = Path(env["GITHUB_EVENT_PATH"])
            require(event_path.stat().st_size <= 1_000_000, "oversize push event")
            event = json.loads(event_path.read_text())
            require(
                event["ref"] == "refs/heads/master"
                and event["after"] == env["GITHUB_SHA"]
                and SHA.fullmatch(event["before"]),
                "unbound push recovery context",
            )
            if event["before"] == TRANSITION_BASE and event["after"] != TRANSITION_BASE:
                return "STOP: transition master qualification failed; return to Integrator. No retry or second transition is authorized."
        except Exception:
            return "STOP: master recovery context unavailable; obtain Integrator's ruling before any retry."
        return f"Recovery: re-run that exact master CodeQL run {run_id} with a fresh full attempt; a declared producer never uses legacy bootstrap."
    return f"Recovery: use a fresh full attempt of the exact compose CodeQL run {run_id}. No manual override; a full test run does not clear security uncertainty."


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", type=Path)
    parser.add_argument("--identity", default="change-scope")
    parser.add_argument("--security-record", type=Path)
    parser.add_argument("--security-qualify", type=Path)
    parser.add_argument("--sarif-id")
    parser.add_argument("--security-output", type=Path)
    parser.add_argument("--language")
    args = parser.parse_args()
    if args.security_record or args.security_qualify:
        try:
            if args.security_output:
                args.security_output.unlink(missing_ok=True)
            require(
                not args.record
                and not (args.security_record and args.security_qualify),
                "mixed producer modes",
            )
            if args.security_record:
                args.security_record.unlink(missing_ok=True)
                args.security_record.write_text(
                    json.dumps(
                        security_record(os.environ, args.language), sort_keys=True
                    )
                    + "\n"
                )
            else:
                require(
                    args.security_output is not None and args.sarif_id is not None,
                    "missing security output/upload",
                )
                api = API(
                    os.environ["GITHUB_REPOSITORY"], os.environ.get("GH_TOKEN", "")
                )
                receipt = qualify_security(
                    api,
                    os.environ,
                    json.loads(args.security_qualify.read_text()),
                    args.sarif_id,
                    args.language,
                )
                args.security_output.write_text(
                    json.dumps(receipt, sort_keys=True) + "\n"
                )
                print(
                    "SECURITY PASS"
                    if receipt["qualified"]
                    else "SECURITY BASELINE RECORDED"
                )
        except NewFinding as exc:
            print(f"::error title={NEW_FINDING}::new qualifying CodeQL finding")
            print("SECURITY NEW-FINDING: " + str(exc))
            print(
                "Repair the finding on a new exact candidate and pay its full compose CodeQL run before offering; no override or test-run waiver."
            )
            raise SystemExit(1)
        except Exception as exc:
            print(f"::error title={EVIDENCE_INCOMPLETE}::{type(exc).__name__}")
            print(f"SECURITY EVIDENCE INCOMPLETE ({type(exc).__name__})")
            if isinstance(exc, SecurityIncomplete):
                print(exc.recovery)
            recovery = _security_recovery(os.environ)
            print(recovery)
            if recovery.startswith("STOP:"):
                raise SystemExit(1)
            print(
                "Re-run ALL jobs, not only failed jobs. On a compose run, a later "
                "full attempt that passes with valid receipts clears this failure "
                "for test reuse; failed tests, gitleaks or findings still force "
                "full master CI on this head. Never re-stamp the same tree to shed "
                "a failure. If a fresh full attempt is UNKNOWN again, do not land; "
                "return the printed reason to Root and the owner. Only a normal "
                "reviewed fix or revert of the producer can resolve persistent "
                "UNKNOWN; no waiver."
            )
            raise SystemExit(1)
        return
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
