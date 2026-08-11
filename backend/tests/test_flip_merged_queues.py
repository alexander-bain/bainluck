"""The post-merge queue flip, pinned to CONTENT rather than prose.

INT-038's flip step matched any handoff file *mentioning* a landed queue id, and
wrongly marked UX-P052 `merged` while UX-P052 was still unmerged. Reverted in two
minutes, but the class is expensive in both directions:

* a falsely-`merged` entry makes real work **invisible** — the ready-set IS the
  Integrator's work queue;
* a falsely-`ready` entry makes the next Integrator content-verify a list of
  ghosts. INT-034 spent a cycle on exactly that: 15 `ready_for_integration`
  entries of which 0 were real.

So the tests that matter here are the two false directions, not the happy path.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "flip_merged_queues.py"


def _module():
    spec = importlib.util.spec_from_file_location("flip_merged_queues", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_script_exists():
    assert SCRIPT.is_file()


@pytest.mark.parametrize(
    "line,branch,sha",
    [
        ("  - program/ux-38 @ 130d8d1c (base origin/master 10968d84)", "program/ux-38", "130d8d1c"),
        ("branch: lane1/q315 @ 987abf12", "lane1/q315", "987abf12"),
        ("program/calibration-27 @ e500892a, stacked", "program/calibration-27", "e500892a"),
    ],
)
def test_it_reads_the_declared_branch_and_head(line, branch, sha):
    """A queue file DECLARES its head. That is the key, and it is checkable."""
    m = _module().DECLARED.search(line)
    assert m and m.group("branch") == branch and m.group("sha") == sha


def test_it_does_not_match_a_bare_queue_id():
    """THE REGRESSION. INT-038's step keyed on text like this and mis-fired.

    A mention of a queue id — in prose, in a `prev_report:` line, in someone
    else's cross-reference — must not be mistaken for a claim that the work
    landed. Only `branch @ sha` is a claim.
    """
    mod = _module()
    for prose in (
        "prev_report: PROGRAM-UX-REPORT.md @ UX-P051 (cycle 51 — MERGED mid-cycle)",
        "this supersedes UX-P052 and CAL-P029",
        "depends_on: 314. Content-independent; the chain is sequential.",
    ):
        assert mod.DECLARED.search(prose) is None, prose


def test_an_unknown_sha_is_not_landed(tmp_path):
    """An object this repo has never seen is a refusal, not an assumption."""
    ok, why = _module().content_is_on_master("0" * 40)
    assert ok is False
    assert "not an object" in why


def test_a_commit_on_master_reads_as_landed():
    """Content, not ancestry — a rebased/cherry-picked commit lands under a
    different SHA, so `--merged` and `cherry` both lie. The tree is the truth."""
    mod = _module()
    head = subprocess.run(
        ["git", "-C", str(mod.REPO), "rev-parse", "origin/master"],
        capture_output=True,
        text=True,
    ).stdout.strip()
    ok, why = mod.content_is_on_master(head)
    assert ok is True, why
    assert "match origin/master" in why


def test_a_commit_whose_content_is_absent_reads_as_not_landed(tmp_path):
    """The other false direction: do not flip something that has not landed."""
    mod = _module()
    repo = tmp_path / "r"
    repo.mkdir()

    def git(*a):
        return subprocess.run(
            ["git", "-C", str(repo), *a], capture_output=True, text=True
        ).stdout.strip()

    git("init", "-q", "-b", "master")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    (repo / "a.txt").write_text("base\n")
    git("add", "a.txt")
    git("commit", "-qm", "base")
    git("branch", "-f", "origin/master", "master")  # stand-in for the remote ref
    (repo / "a.txt").write_text("unlanded change\n")
    git("add", "a.txt")
    git("commit", "-qm", "not on master")
    unlanded = git("rev-parse", "HEAD")

    monkey = mod.REPO
    try:
        mod.REPO = repo
        ok, why = mod.content_is_on_master(unlanded)
    finally:
        mod.REPO = monkey

    assert ok is False, why
    assert "differ from master" in why
