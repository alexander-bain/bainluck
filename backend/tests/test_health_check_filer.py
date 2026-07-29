"""Tests for the Daily Health Check GitHub filer (Queue 276).

The old filer fuzzy-matched ``[Health Check]`` in a title (GitHub ``in:title`` +
``per_page=1``) and PATCHed the first hit — which hijacked #1477 (whose title
merely CONTAINED the substring), replacing its title/body/labels. The fix
identifies the filer's OWN card by a stable hidden body marker, fails closed on
ambiguity, and merges (never replaces) labels on PATCH.

``scripts/daily_health_check.py`` is a stdlib-only standalone script (runs in a
GitHub Actions workflow with no backend runtime), so it is imported by path here
and every GitHub call is monkeypatched — NO production or GitHub mutation.
"""

import sys
from pathlib import Path

import pytest

# The script lives at repo-root/scripts, not under backend/ — add it to the path.
_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import daily_health_check as dhc  # noqa: E402


REPO = "alexander-bain/bainluck"
TOKEN = "gh-test-token"


def _report(summary="UNHEALTHY — 2 failed, 0 warnings, 5 passed", priority="p1"):
    """A minimal HealthReport-like double with a failing check so the filer runs."""
    r = dhc.HealthReport(timestamp="2026-07-29 03:00 UTC")
    r.checks.append(
        dhc.CheckResult(
            name="is_winner: kalshi", status="fail",
            value="53.8%", threshold="> 90%", priority=priority,
        )
    )
    # A couple of passes so summary_line reads naturally (value not asserted).
    r.checks.append(dhc.CheckResult(name="API Reachable", status="pass", value="healthy", threshold="200 OK"))
    return r


def _issue(number, *, title="", body="", labels=()):
    return {"number": number, "title": title, "body": body,
            "labels": [{"name": l} for l in labels]}


def _owned_body():
    """A body that canonically OWNS the marker (real line, not fenced/quoted)."""
    return "## Health Check — old\n\n" + dhc.HEALTH_MARKER_LINE


class _FakeGitHub:
    """Records every _github_request call and serves a fixed open-issue list.

    ``pages`` maps page number → list of issue dicts for the paginated GET.
    PATCH/POST/create are recorded, never executed.
    """

    def __init__(self, pages=None, raise_on_get=False):
        self.pages = pages or {1: []}
        self.raise_on_get = raise_on_get
        self.calls = []  # (method, path, data)

    def __call__(self, method, path, *, data=None, token=None):
        self.calls.append((method, path, data))
        if method == "GET" and "/issues?" in path:
            if self.raise_on_get:
                raise RuntimeError("boom (rate limit / network)")
            # Extract page=N
            page = 1
            for part in path.split("&"):
                if part.startswith("page="):
                    page = int(part.split("=")[1])
            return self.pages.get(page, [])
        if method == "POST" and path.endswith("/issues"):
            return {"html_url": f"https://github.com/{REPO}/issues/9999", "number": 9999}
        if method == "PATCH":
            return {}
        if method == "POST" and path.endswith("/comments"):
            return {}
        return {}

    # --- assertion helpers ---
    def patched(self):
        return [(p, d) for (m, p, d) in self.calls if m == "PATCH"]

    def created(self):
        return [d for (m, p, d) in self.calls if m == "POST" and p.endswith("/issues")]

    def commented(self):
        return [(p, d) for (m, p, d) in self.calls if m == "POST" and p.endswith("/comments")]

    def wrote_anything(self):
        return bool(self.patched() or self.created() or self.commented())


@pytest.fixture
def gh(monkeypatch):
    fake = _FakeGitHub()
    monkeypatch.setattr(dhc, "_github_request", fake)
    return fake


# ---------------------------------------------------------------------------
# The #1477 clobber: title lookalikes must never be selected.
# ---------------------------------------------------------------------------

def test_lookalike_title_never_selected_bootstrap_targets_pin(gh, monkeypatch):
    """The exact #1477 scenario: a lookalike whose TITLE contains ``[Health
    Check]`` sits alongside the canonical #869 (no marker yet). Bootstrap must
    stamp/patch #869 by NUMBER and never touch the lookalike."""
    monkeypatch.delenv(dhc.CANONICAL_ISSUE_ENV, raising=False)  # default pin 869
    lookalike = _issue(
        1477,
        title="[Health Check] UNHEALTHY — 2 failed, 0 w…",  # hijacked-style title
        body="## Defect\n\nTracks the filer bug.",
        labels=["area:infra", "type:bug", "priority:p2"],
    )
    canonical = _issue(
        869, title="[Health Check] UNHEALTHY — 2 failed, 0 warnings, 2 passed",
        body="## Health Check — old", labels=["type:ops", "priority:p1"],
    )
    gh.pages = {1: [canonical, lookalike]}

    dhc.create_or_update_issue(_report(), REPO, TOKEN)

    patched = gh.patched()
    assert len(patched) == 1
    assert "/issues/869" in patched[0][0]
    # The lookalike #1477 was NEVER written to.
    assert all("/issues/1477" not in p for (p, _d) in gh.patched())
    assert all("/issues/1477" not in p for (p, _d) in gh.commented())
    assert gh.created() == []
    # The bootstrap PATCH stamps the marker into the canonical body.
    assert dhc.HEALTH_MARKER in patched[0][1]["body"]


def test_quoted_marker_is_not_ownership():
    """A meta issue that merely QUOTES the marker inside a code fence / blockquote
    / table is NOT a phantom owner (the C37 hardening)."""
    fenced = f"```\n{dhc.HEALTH_MARKER_LINE}\n```"
    quoted = f"> {dhc.HEALTH_MARKER_LINE}"
    tabled = f"| evidence | {dhc.HEALTH_MARKER} |"
    indented = f"    {dhc.HEALTH_MARKER_LINE}"
    for body in (fenced, quoted, tabled, indented):
        assert dhc._declares_health_marker(body) is False
    # A real line DOES own it.
    assert dhc._declares_health_marker(_owned_body()) is True


# ---------------------------------------------------------------------------
# Ownership resolution branches.
# ---------------------------------------------------------------------------

def test_unique_marker_owner_updates_in_place(gh):
    owner = _issue(
        869, title="[Health Check] OLD TITLE",
        body=_owned_body(), labels=["type:ops", "priority:p1"],
    )
    gh.pages = {1: [owner]}
    url = dhc.create_or_update_issue(_report(), REPO, TOKEN)
    assert url.endswith("/issues/869")
    patched = gh.patched()
    assert len(patched) == 1 and "/issues/869" in patched[0][0]
    assert len(gh.commented()) == 1
    assert gh.created() == []


def test_ambiguous_multiple_owners_noop(gh):
    a = _issue(869, title="[Health Check] a", body=_owned_body(), labels=["type:ops"])
    b = _issue(1500, title="[Health Check] b", body=_owned_body(), labels=["type:ops"])
    gh.pages = {1: [a, b]}
    result = dhc.create_or_update_issue(_report(), REPO, TOKEN)
    assert result is None
    assert not gh.wrote_anything()


def test_read_failure_noop(gh):
    gh.raise_on_get = True
    result = dhc.create_or_update_issue(_report(), REPO, TOKEN)
    assert result is None
    assert not gh.patched() and not gh.created() and not gh.commented()


def test_truncated_read_noop(monkeypatch):
    # Every page is full up to the cap → truncated → fail closed.
    full_page = [_issue(n, title="x", body="y") for n in range(dhc._LIST_PER_PAGE)]
    pages = {p: full_page for p in range(1, dhc._LIST_MAX_PAGES + 1)}
    fake = _FakeGitHub(pages=pages)
    monkeypatch.setattr(dhc, "_github_request", fake)
    result = dhc.create_or_update_issue(_report(), REPO, TOKEN)
    assert result is None
    assert not fake.patched() and not fake.created() and not fake.commented()


def test_unchanged_report_skips(gh):
    title = f"{dhc.TITLE_PREFIX} {_report().summary_line()}"
    owner = _issue(869, title=title, body=_owned_body(), labels=["type:ops"])
    gh.pages = {1: [owner]}
    url = dhc.create_or_update_issue(_report(), REPO, TOKEN)
    assert url.endswith("/issues/869")
    # No write at all — same marker owner, identical title.
    assert not gh.wrote_anything()


def test_cold_start_create_when_pin_unset(gh, monkeypatch):
    monkeypatch.setenv(dhc.CANONICAL_ISSUE_ENV, "")  # pin disabled → allow create
    gh.pages = {1: []}  # no owners, no canonical card
    url = dhc.create_or_update_issue(_report(), REPO, TOKEN)
    created = gh.created()
    assert len(created) == 1
    assert dhc.HEALTH_MARKER in created[0]["body"]
    assert "type:ops" in created[0]["labels"] and "needs-agent" in created[0]["labels"]
    assert url.endswith("/issues/9999")


def test_pin_set_but_not_found_fails_closed(gh, monkeypatch):
    monkeypatch.setenv(dhc.CANONICAL_ISSUE_ENV, "869")
    # #869 is absent; a lookalike title exists but is a different number.
    gh.pages = {1: [_issue(1477, title="[Health Check] lookalike", body="tracker")]}
    result = dhc.create_or_update_issue(_report(), REPO, TOKEN)
    assert result is None
    # No create (would be a duplicate), no patch of the lookalike.
    assert not gh.wrote_anything()


# ---------------------------------------------------------------------------
# Label merge: preserve everything, seed only when missing, never replace.
# ---------------------------------------------------------------------------

def test_patch_merges_labels_preserves_human_and_area(gh):
    owner = _issue(
        869, title="[Health Check] OLD",
        body=_owned_body(),
        labels=["area:admin-ops", "parked", "priority:p1", "type:ops"],
    )
    gh.pages = {1: [owner]}
    dhc.create_or_update_issue(_report(priority="p0"), REPO, TOKEN)
    sent = gh.patched()[0][1]["labels"]
    # r305/r306 hand-fixes survive:
    assert "area:admin-ops" in sent
    assert "parked" in sent
    # Human priority NOT overridden (report says p0, but p1 stays; no p0 added):
    assert "priority:p1" in sent
    assert "priority:p0" not in sent
    # Owned lifecycle present, nothing removed:
    assert "type:ops" in sent and "needs-agent" in sent


def test_merge_seeds_priority_only_when_absent():
    # No priority present → seed it.
    seeded = dhc._merge_labels(["area:infra"], "p1")
    assert "priority:p1" in seeded and "area:infra" in seeded
    # Priority present → never add another / override.
    kept = dhc._merge_labels(["priority:p2", "area:infra"], "p0")
    assert "priority:p2" in kept and "priority:p0" not in kept


def test_merge_never_removes_labels():
    existing = ["area:x", "type:bug", "needs-user", "priority:p3", "custom-label"]
    merged = dhc._merge_labels(existing, "p1")
    for lab in existing:
        assert lab in merged
