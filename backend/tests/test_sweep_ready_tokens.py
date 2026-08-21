"""Ruling 109 — the never-merge containment check, pinned.

The ruling exists because the closure was REMEMBERED and the memory was wrong:
INT-092 named two heads never-merge, and the constraint ran through a third one
that was still advertising ``ready_for_integration``. So the property worth
testing is not that the report renders — it is that a branch containing a
never-merge ancestor comes back **VOID**, and that a run which could not compute
the closure says so instead of reporting everything clean.

Ruling 102 applies to this file's subject, and is obeyed here: the two tests
below marked IMPURE **start the script** — one through ``main()`` over a stub,
one as a subprocess against a REAL git repository built in a tmpdir, so the
``git rev-list`` closure is genuinely computed rather than asserted about. The
pure tests underneath cover the decisions.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from io import StringIO
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "sweep_ready_tokens.py"


def _load():
    spec = importlib.util.spec_from_file_location("sweep_ready_tokens", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sweep_mod = _load()


def _token(path: Path, name: str, body: str) -> None:
    (path / name).write_text(body, encoding="utf-8")


def _git(repo: Path, *args) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=True,
    )
    return proc.stdout.strip()


# ---------------------------------------------------------------- IMPURE ----


def test_main_starts_and_reports_a_void_token(tmp_path):
    """IMPURE (ruling 102): drives ``main()``, the entry point a human calls.

    The runner is stubbed, but ``main`` does its own argparse, its own directory
    read, its own token parse and its own rendering — the wiring that shipped
    broken in #1978 is the wiring exercised here.
    """
    handoff = tmp_path / "handoff"
    handoff.mkdir()
    _token(handoff, "READY-codex-adhoc-provenance-r5.md",
           "status: blocked\nnever_merge: true\nbranch: **`codex-adhoc/provenance-r5`**\n")
    _token(handoff, "READY-codex-adhoc-coldfeed.md",
           "status: ready_for_integration\nbranch: **`codex-adhoc/coldfeed`**\nhead: **`fa8021ea`**\n")

    r5 = "e031999796f181bc70a0fdc3904f582515f1abbc"
    coldfeed = "fa8021ea" + "0" * 32
    poison = "02cd7ad81c393286b79f1040646c60d7ec0e4a98"
    heads = {"codex-adhoc/provenance-r5": r5, "codex-adhoc/coldfeed": coldfeed}

    # The shape that matters: coldfeed is NOT downstream of r5 — the two share an
    # upstream commit. An ancestry test answers "clean" here; the closure
    # intersection answers VOID. This is the production topology of #2002.
    revlist = {r5: [r5, poison], coldfeed: [coldfeed, poison]}

    def runner(argv, **kwargs):
        assert argv[0] == "git"
        if argv[3] == "rev-parse":
            out = heads.get(argv[4], "")
            return subprocess.CompletedProcess(argv, 0 if out else 128, out, "")
        if argv[3] == "rev-list":
            head = argv[4].split("..", 1)[1]
            return subprocess.CompletedProcess(argv, 0, "\n".join(revlist.get(head, [])), "")
        if argv[3] == "merge-base":
            return subprocess.CompletedProcess(argv, 1, "", "")  # nothing is on master
        raise AssertionError(f"unexpected git call: {argv}")

    out = StringIO()
    code = sweep_mod.main(
        ["--handoff-dir", str(handoff), "--repo", str(tmp_path)],
        runner=runner, stdout=out,
    )
    text = out.getvalue()

    assert code == 0
    assert "VOID" in text
    assert "READY-codex-adhoc-coldfeed.md" in text
    assert "contains 02cd7ad8" in text
    assert "containment: RAN" in text

    # and --strict turns the same state into a failing exit
    out2 = StringIO()
    assert sweep_mod.main(
        ["--handoff-dir", str(handoff), "--repo", str(tmp_path), "--strict"],
        runner=runner, stdout=out2,
    ) == 1


@pytest.mark.skipif(
    subprocess.run(["git", "--version"], capture_output=True).returncode != 0,
    reason="git unavailable",
)
def test_the_script_runs_as_a_subprocess_against_a_real_git_repo(tmp_path):
    """IMPURE (ruling 102): a real repo, a real ancestry, the real CLI.

    The stub above can only prove the script asks git the right question. This
    proves the ANSWER is read correctly, by computing the closure with real
    ``git rev-list`` output over a real topology — which is the one call the
    whole ruling turns on. Ruling 102's charter case is precisely a rail whose 37 pure
    tests all passed over code that had never executed.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "master")
    _git(repo, "config", "user.email", "int094@example.invalid")
    _git(repo, "config", "user.name", "INT-094 test")

    (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(repo, "add", "seed.txt")
    _git(repo, "commit", "-qm", "seed")
    _git(repo, "branch", "-f", "origin/master", "HEAD")

    # The never-merge commit lives OFF master, and a branch is built on top of it.
    # Keeping it off master matters: the first draft of this fixture committed the
    # poison on master itself, so the "clean" branch inherited it and the script
    # correctly reported VOID. The fixture was wrong, not the sweep — which is a
    # fair demonstration of how far ancestry travels without anyone intending it.
    _git(repo, "checkout", "-q", "-b", "nm/head")
    (repo / "poison.txt").write_text("edits a migration master already ran\n", encoding="utf-8")
    _git(repo, "add", "poison.txt")
    _git(repo, "commit", "-qm", "the never-merge commit")
    _git(repo, "checkout", "-q", "-b", "contaminated")
    (repo / "innocent.txt").write_text("looks like an artifacts-only branch\n", encoding="utf-8")
    _git(repo, "add", "innocent.txt")
    _git(repo, "commit", "-qm", "downstream work")

    # ...and a branch cut from the seed, which does NOT contain it
    _git(repo, "checkout", "-q", "-b", "clean", "master")
    (repo / "fine.txt").write_text("fine\n", encoding="utf-8")
    _git(repo, "add", "fine.txt")
    _git(repo, "commit", "-qm", "clean work")

    handoff = repo / "handoff"
    handoff.mkdir()
    _token(handoff, "READY-nm.md", "status: blocked\nnever_merge: true\nbranch: `nm/head`\n")
    _token(handoff, "READY-contaminated.md",
           "status: ready_for_integration\nbranch: `contaminated`\n")
    _token(handoff, "READY-clean.md", "status: ready_for_integration\nbranch: `clean`\n")

    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--handoff-dir", str(handoff),
         "--repo", str(repo), "--json"],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)

    by_file = {r["file"]: r for r in result["rows"]}
    assert result["containment_ran"] is True
    assert by_file["READY-contaminated.md"]["verdict"] == "VOID"
    assert by_file["READY-contaminated.md"]["contains_never_merge"]
    assert by_file["READY-clean.md"]["verdict"] == "LIVE-READY"
    assert by_file["READY-nm.md"]["verdict"] == "HELD"

    # A branch is not "contained by" itself — otherwise every never-merge head
    # would report as containing one and the verdict would be meaningless.
    assert by_file["READY-nm.md"]["contains_never_merge"] == []

    # The closure holds only the never-merge lineage, NOT everything reachable:
    # master's own commits are excluded by construction, which is why `clean`
    # survives even though master is an ancestor of every never-merge head.
    assert result["closure_size"] == 1


def test_a_spent_branch_is_reported_spent_against_a_real_repo(tmp_path):
    """IMPURE: the INT-034 failure — a ready token over already-merged work."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "master")
    _git(repo, "config", "user.email", "int094@example.invalid")
    _git(repo, "config", "user.name", "INT-094 test")
    (repo / "a.txt").write_text("a\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-qm", "shipped")
    _git(repo, "branch", "spent")
    _git(repo, "branch", "-f", "origin/master", "HEAD")

    handoff = repo / "handoff"
    handoff.mkdir()
    _token(handoff, "READY-spent.md", "status: ready_for_integration\nbranch: `spent`\n")

    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--handoff-dir", str(handoff),
         "--repo", str(repo), "--json"],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    rows = json.loads(proc.stdout)["rows"]
    assert rows[0]["verdict"] == "SPENT"


# ------------------------------------------------------------------ PURE ----


def test_an_empty_never_merge_set_is_reported_not_run_never_clean(tmp_path):
    """Gotcha #53 / ruling 109 obligation 4: an absent comparison is not health."""
    handoff = tmp_path / "handoff"
    handoff.mkdir()
    _token(handoff, "READY-x.md", "status: ready_for_integration\nbranch: `x`\n")

    def runner(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 1, "", "")

    out = StringIO()
    sweep_mod.main(["--handoff-dir", str(handoff), "--repo", str(tmp_path)],
                   runner=runner, stdout=out)
    text = out.getvalue()
    assert "containment: NOT RUN" in text
    assert "NOT a clean result" in text


def test_parse_token_strips_the_markdown_the_tokens_are_actually_written_in():
    parsed = sweep_mod.parse_token(
        "status: ready_for_integration\n"
        "branch: **`program/calibration-74`**\n"
        "head: **`db4928a5`**\n"
    )
    assert parsed["branch"] == "program/calibration-74"
    assert parsed["head"] == "db4928a5"
    assert parsed["status"] == "ready_for_integration"


def test_only_the_first_occurrence_of_a_field_counts():
    """A token's prose quotes other tokens; the header is the claim."""
    parsed = sweep_mod.parse_token(
        "status: merged\nbranch: `a`\n\n"
        "merge_note: the previous cycle read `status: ready_for_integration` here\n"
        "status: ready_for_integration\n"
    )
    assert parsed["status"] == "merged"


def test_a_trailing_comment_does_not_become_part_of_the_status():
    parsed = sweep_mod.parse_token("status: merged   # INT-092 landed this\n")
    assert parsed["status"] == "merged"
    assert sweep_mod.is_ready(parsed["status"]) is False


def test_the_short_form_status_ready_still_counts_as_ready():
    """READY-lane1-380.md wrote `ready` while carrying three branches and three PRs."""
    assert sweep_mod.is_ready("ready") is True
    assert sweep_mod.is_ready("ready_for_integration") is True


def test_a_token_with_no_status_field_is_MALFORMED_not_quietly_not_ready():
    """Ruling 115. `is_ready(None)` is LOUD — it must not manufacture a boolean.

    A missing field has not said "no". Five consecutive cycles hid live work
    behind the silent False this replaces: READY-calibration-75.md, then
    READY-ux-99.md and READY-lane1-386.md in the cycle that banked the ruling.
    """
    for absent in (None, "", "   ", "\t\n"):
        with pytest.raises(sweep_mod.MalformedToken):
            sweep_mod.is_ready(absent)

    # ...and a status that is PRESENT and simply not ready still answers False.
    # The ruling separates absence from negation; it does not abolish negation.
    assert sweep_mod.is_ready("merged") is False


def _token_file(tmp_path, name, body):
    (tmp_path / name).write_text(body, encoding="utf-8")


def test_a_malformed_token_over_unmerged_work_is_reported_not_dropped(tmp_path):
    """The whole ruling, end to end, on the shape that caused it.

    `READY-ux-99.md` carried three unmerged commits and no `status:` field, so the
    sweep dropped it at the same `continue` that discards an honestly-merged
    token — and it had no PR either, so ruling 113's second source could not
    catch it. It must now appear, resolved, flagged, and named in the footer.
    """
    _token_file(tmp_path, "READY-live.md", "queue: UX-P112\nbranch: `program/ux-99`\n")
    _token_file(tmp_path, "READY-spent.md", "queue: old\nbranch: `program/ux-1`\n")

    def run(cmd, **kwargs):
        if cmd[0] == "gh":
            return _FakeProc("[]", 0)
        if "rev-parse" in cmd:
            return _FakeProc("f" * 40 if "program/ux-99" in cmd else "a" * 40, 0)
        if "merge-base" in cmd and "--is-ancestor" in cmd:
            # program/ux-1 resolves to a…a and IS on master; ux-99's f…f is not.
            return _FakeProc("", 0 if cmd[-2] == "a" * 40 else 1)
        if "rev-list" in cmd:
            return _FakeProc("", 0)
        return _FakeProc("", 0)

    result = sweep_mod.sweep(str(tmp_path), ".", runner=run)

    assert result["status_readable"] == 0
    assert result["malformed_tokens"] == ["READY-live.md", "READY-spent.md"]

    by_file = {r["file"]: r for r in result["rows"]}
    assert by_file["READY-live.md"]["verdict"] == "MALFORMED"
    assert by_file["READY-live.md"]["underlying"] == "LIVE-READY"
    assert by_file["READY-live.md"]["over_live_work"] is True

    # Malformed over ALREADY-SHIPPED work is bookkeeping, not an emergency, and
    # the two must stay distinguishable or the loud half becomes noise.
    assert by_file["READY-spent.md"]["verdict"] == "MALFORMED"
    assert by_file["READY-spent.md"]["underlying"] == "SPENT"
    assert by_file["READY-spent.md"]["over_live_work"] is False

    out = sweep_mod.render(result)
    assert "status coverage: 0 of 2" in out
    assert "MALFORMED" in out
    assert "REAL WORK, INVISIBLE" in out
    assert "RULING 115" in out and "READY-live.md" in out.split("RULING 115")[1]
    # The bookkeeping one must NOT be dragged into the footer's action list.
    assert "READY-spent.md" not in out.split("RULING 115")[1]


def test_strict_exits_1_on_a_malformed_token_over_live_work(tmp_path):
    """Obligation 5. INT-102 wrote the fix request down and it was ignored for a
    cycle; a finding that cannot red a gate is a finding that gets written down."""
    _token_file(tmp_path, "READY-live.md", "branch: `program/ux-99`\n")

    def run(cmd, **kwargs):
        if cmd[0] == "gh":
            return _FakeProc("[]", 0)
        if "rev-parse" in cmd:
            return _FakeProc("f" * 40, 0)
        if "merge-base" in cmd and "--is-ancestor" in cmd:
            return _FakeProc("", 1)
        return _FakeProc("", 0)

    out = StringIO()
    assert sweep_mod.main(["--handoff-dir", str(tmp_path), "--strict"],
                          runner=run, stdout=out) == 1

    # A well-formed, honestly-merged token in the same directory does not.
    _token_file(tmp_path, "READY-live.md", "status: merged\nbranch: `program/ux-99`\n")
    out2 = StringIO()
    assert sweep_mod.main(["--handoff-dir", str(tmp_path), "--strict"],
                          runner=run, stdout=out2) == 0


def test_an_unresolvable_branch_is_not_claimed_to_be_real_work(tmp_path):
    """Ruling 115 refusing to commit its OWN error.

    A malformed token whose `branch:` will not resolve might name a live branch
    or a deleted one. Flagging it "REAL WORK, INVISIBLE" would assert a fact from
    an absence — precisely what this ruling exists to stop — so it gets an honest
    label and does NOT red --strict, since adding a status field cannot fix a
    broken branch field.
    """
    _token_file(tmp_path, "READY-nobranch.md", "queue: ancient\n")

    def run(cmd, **kwargs):
        if cmd[0] == "gh":
            return _FakeProc("[]", 0)
        return _FakeProc("", 128)          # git resolves nothing

    result = sweep_mod.sweep(str(tmp_path), ".", runner=run)
    row = result["rows"][0]
    assert row["verdict"] == "MALFORMED"
    assert row["underlying"] == "UNRESOLVED"
    assert row["over_live_work"] is False

    out = sweep_mod.render(result)
    assert "cannot rule out live work" in out
    assert "REAL WORK, INVISIBLE" not in out
    assert "RULING 115" not in out        # nothing actionable to demand

    strict = StringIO()
    assert sweep_mod.main(["--handoff-dir", str(tmp_path), "--strict"],
                          runner=run, stdout=strict) == 0


def test_coverage_ratio_is_printed_even_when_every_token_is_readable(tmp_path):
    """Obligation 4 is unconditional. A ratio only shown when it is bad is a ratio
    the reader learns to expect the absence of."""
    _token_file(tmp_path, "READY-a.md", "status: merged\nbranch: `x`\n")
    result = sweep_mod.sweep(str(tmp_path), ".", runner=_pr_runner([]))
    assert result["status_readable"] == 1 and result["malformed_tokens"] == []
    assert "status coverage: 1 of 1" in sweep_mod.render(result)


def test_void_outranks_spent_and_moved_head():
    """A branch that is both spent and contaminated is reported VOID — the void is
    the fact that needs acting on, and a SPENT verdict would close the file."""
    token = {"head": "deadbeef", "never_merge": False}
    assert sweep_mod.classify(token, "aaaaaaaa" * 5, True, [{"head": "x"}]) == "VOID"
    assert sweep_mod.classify(token, "deadbeef" * 5, False, []) == "LIVE-READY"
    assert sweep_mod.classify(token, "cafebabe" * 5, False, []) == "MOVED-HEAD"
    assert sweep_mod.classify(token, None, False, []) == "UNRESOLVED"
    assert sweep_mod.classify({"never_merge": True}, "a" * 40, False, []) == "HELD"


def test_an_unresolvable_head_is_unresolved_not_clean():
    assert sweep_mod.classify({"head": "abc", "never_merge": False}, None, False, []) == "UNRESOLVED"


# ---------------------------------------------------------------------------
# Ruling 113 — the OPEN-PR source, and its NOT-RUN discipline.
#
# The ruling's charter case is two Integrator cycles missing live merge-eligible
# work, so the property worth pinning is not that PRs render — it is that a PR
# source which CANNOT BE READ says so, because an unreadable list and an empty
# list are the same bytes (gotcha #53) and one of them is a lie.
# ---------------------------------------------------------------------------

class _FakeProc:
    def __init__(self, stdout="", returncode=0, stderr=""):
        self.stdout, self.returncode, self.stderr = stdout, returncode, stderr


def _pr_runner(payload, *, rc=0, stderr="", ancestors=()):
    """A runner that answers `gh pr list` and `git merge-base --is-ancestor`."""
    def run(cmd, **kwargs):
        if cmd[0] == "gh":
            return _FakeProc(json.dumps(payload), rc, stderr)
        if "merge-base" in cmd and "--is-ancestor" in cmd:
            return _FakeProc("", 0 if cmd[-2] in ancestors else 1)
        return _FakeProc("", 0)
    return run


def test_a_gh_that_is_not_installed_is_NOT_RUN_never_an_empty_list():
    def run(cmd, **kwargs):
        if cmd[0] == "gh":
            raise FileNotFoundError("gh")
        return _FakeProc("", 0)
    rows, err = sweep_mod.open_pull_requests(run, ".", "origin/master")
    assert rows == []
    assert err == "gh not installed", err


def test_a_gh_that_exits_nonzero_reports_the_reason():
    rows, err = sweep_mod.open_pull_requests(
        _pr_runner([], rc=4, stderr="HTTP 401: Bad credentials\n"), ".", "origin/master")
    assert rows == []
    assert "gh exited 4" in err and "401" in err, err


def test_non_json_output_is_NOT_RUN():
    def run(cmd, **kwargs):
        return _FakeProc("<html>rate limited</html>", 0)
    rows, err = sweep_mod.open_pull_requests(run, ".", "origin/master")
    assert rows == [] and err == "gh returned output that is not JSON"


def test_a_pr_already_on_base_is_not_an_offer():
    payload = [
        {"number": 1, "headRefName": "a", "headRefOid": "aaaa1111", "statusCheckRollup": []},
        {"number": 2, "headRefName": "b", "headRefOid": "bbbb2222", "statusCheckRollup": []},
    ]
    rows, err = sweep_mod.open_pull_requests(
        _pr_runner(payload, ancestors={"aaaa1111"}), ".", "origin/master")
    assert err is None
    assert [r["number"] for r in rows] == [2], rows


@pytest.mark.parametrize("checks,expected", [
    ([], "NO CHECKS"),
    ([{"conclusion": "SUCCESS"}, {"conclusion": "SUCCESS"}], "GREEN"),
    ([{"conclusion": "SUCCESS"}, {"conclusion": "FAILURE"}], "RED (1)"),
    ([{"conclusion": "SUCCESS"}, {"state": "PENDING"}], "PENDING (1)"),
    ([{"conclusion": "SUCCESS"}, {"conclusion": "TIMED_OUT"}], "RED (1)"),
])
def test_ci_rollup_classification(checks, expected):
    payload = [{"number": 9, "headRefName": "x", "headRefOid": "cccc3333",
                "statusCheckRollup": checks}]
    rows, _ = sweep_mod.open_pull_requests(_pr_runner(payload), ".", "origin/master")
    assert rows[0]["ci"] == expected


def test_render_never_prints_an_empty_PR_SECTION_AS_CLEAN():
    """The whole ruling, in one assertion.

    A failed PR read must not render as silence. If this ever passes with the
    NOT-RUN line absent, the sweep is back to answering a narrower question than
    Phase 0 asked, which is the defect ruling 113 was written for.
    """
    base = {
        "handoff_dir": "/x", "tokens_read": 0, "rows": [], "base": "origin/master",
        "never_merge_heads": [], "unreadable_never_merge_heads": [], "closure_size": 0,
        "containment_ran": False,
    }
    out = sweep_mod.render({**base, "open_prs": [], "open_prs_error": "gh not installed"})
    assert "open PRs: NOT RUN" in out
    assert "gh not installed" in out
    assert "NOT a clean result" in out

    # ...and a genuinely-empty, successfully-read list is allowed to say so.
    ok = sweep_mod.render({**base, "open_prs": [], "open_prs_error": None})
    assert "open PRs: RAN against origin/master" in ok
    assert "NOT RUN" not in ok.split("open PRs")[1][:120]


def test_no_prs_flag_is_reported_as_NOT_RUN_not_as_absence(tmp_path):
    result = sweep_mod.sweep(str(tmp_path), ".", runner=_pr_runner([]),
                             include_prs=False)
    assert result["open_prs_error"] == "disabled"
    assert "open PRs: NOT RUN" in sweep_mod.render(result)
