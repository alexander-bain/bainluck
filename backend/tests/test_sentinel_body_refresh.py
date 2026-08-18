"""A deduped sentinel issue's BODY must track the current failures (UX-P092).

WHY, with the cost measured. `reconcile_issue`'s dedupe path was comment-only —
"no duplicate, no label edit" — so the body was frozen at whatever the FIRST run
happened to see, forever. #1483 was filed 2026-07-29 describing two failures and
was re-observed for nineteen days. On 2026-08-17 the same flow was failing eight
checks, one of them a NEW p1 class (four MLB games rendering LIVE 40-46h before
their own commence_time, plus a `completed_at` inverted by 68.2h), and a reader
of #1483 could see none of it: the body said two unrelated failures and the
comments said "8 failing of 49 checked. Still open."

UX-P091 fixed the CHANNEL — the re-detect comment now carries the failures. This
fixes the ARTEFACT: the body is what a reader reads first and what the title is
judged against, and a frozen one makes a worsening flow look identical to a
stable one. That is gotcha #53's shape at the reporting layer.
"""

import importlib

sf = importlib.import_module("app.tasks.sentinel_filing")
fs = importlib.import_module("app.tasks.flow_sentinel")


class _GH:
    """Stand-in for `app.tasks.bug_report_github`."""

    GITHUB_TOKEN = "t"

    def __init__(self, *, body_raises=False):
        self.comments: list[tuple[int, str]] = []
        self.bodies: list[tuple[int, str]] = []
        self.created: list[tuple[str, str]] = []
        self.closed: list[int] = []
        self._body_raises = body_raises

    def comment_on_issue(self, n, body):
        self.comments.append((n, body))

    def update_issue_body(self, n, body):
        if self._body_raises:
            raise RuntimeError("GitHub 502")
        self.bodies.append((n, body))

    def create_github_issue(self, title, body, labels):
        self.created.append((title, body))
        return 4242, "node"

    def add_to_project_board(self, node_id):
        pass

    def close_issue(self, n, comment=None):
        self.closed.append(n)


def _reconcile(gh_stub, monkeypatch, **kw):
    import app.tasks.bug_report_github as real_gh

    for name in (
        "comment_on_issue",
        "update_issue_body",
        "create_github_issue",
        "add_to_project_board",
        "close_issue",
    ):
        monkeypatch.setattr(real_gh, name, getattr(gh_stub, name), raising=False)
    monkeypatch.setattr(real_gh, "GITHUB_TOKEN", "t", raising=False)
    return sf.reconcile_issue(**kw)


OPEN_ISSUE = [
    {
        "number": 1483,
        "title": "[Flow Sentinel] Resolved games still rendering as live (2 failing)",
        "body": "`flow-sentinel-fingerprint:abc123` (dedupe key)\n\n2 failures, from July.",
        "labels": [{"name": "alert-intake"}],
    }
]


def test_a_deduped_issue_gets_its_body_rewritten_with_the_current_failures(monkeypatch):
    """THE #1483 REGRESSION."""
    stub = _GH()
    res = _reconcile(
        stub,
        monkeypatch,
        red=True,
        fingerprint="abc123",
        marker_key="flow-sentinel-fingerprint",
        red_comment="re-observed",
        red_body="`flow-sentinel-fingerprint:abc123`\n\n8 failing, incl. a new p1 class",
        open_issues=OPEN_ISSUE,
    )

    assert res["action"] == "commented"
    assert res["body_refresh"] == "refreshed"
    assert stub.bodies == [
        (1483, "`flow-sentinel-fingerprint:abc123`\n\n8 failing, incl. a new p1 class")
    ], "the body was left frozen at first-file — this IS #1483's nineteen days"
    assert stub.comments, "the comment channel must survive too"
    assert not stub.created, "a dedupe must never create a second issue"


def test_a_body_that_lost_its_fingerprint_is_REFUSED(monkeypatch):
    """The guard that matters more than the feature.

    The GREEN path matches the canonical issue by its body declaration and
    NOTHING else (`title_prefix` is deliberately ignored on close). A refreshed
    body without the fingerprint could therefore never be auto-closed again —
    the refresh would permanently strand the issue in exactly the stale state it
    was built to prevent. A frozen body is bad; an un-closeable one is worse.
    """
    stub = _GH()
    res = _reconcile(
        stub,
        monkeypatch,
        red=True,
        fingerprint="abc123",
        marker_key="flow-sentinel-fingerprint",
        red_comment="re-observed",
        red_body="8 failing — but somebody dropped the dedupe key",
        open_issues=OPEN_ISSUE,
    )

    assert res["body_refresh"] == "refused_no_fingerprint"
    assert stub.bodies == []
    assert stub.comments, "refusing the body must not cost us the comment"


def test_a_failed_body_refresh_degrades_to_the_comment_and_says_so(monkeypatch):
    """Non-fatal by design: the comment already carried the failures, so a
    GitHub 502 on the PATCH must not lose the re-detection. But it is RECORDED —
    a silently-skipped refresh would be indistinguishable from a successful one.
    """
    stub = _GH(body_raises=True)
    res = _reconcile(
        stub,
        monkeypatch,
        red=True,
        fingerprint="abc123",
        marker_key="flow-sentinel-fingerprint",
        red_comment="re-observed",
        red_body="`flow-sentinel-fingerprint:abc123` 8 failing",
        open_issues=OPEN_ISSUE,
    )

    assert res["action"] == "commented"
    assert res["body_refresh"] == "failed"
    assert stub.comments


def test_no_red_body_supplied_is_recorded_as_not_requested(monkeypatch):
    """Back-compat: every other sentinel still calls without `red_body`."""
    stub = _GH()
    res = _reconcile(
        stub,
        monkeypatch,
        red=True,
        fingerprint="abc123",
        marker_key="flow-sentinel-fingerprint",
        red_comment="re-observed",
        open_issues=OPEN_ISSUE,
    )
    assert res["body_refresh"] == "not_requested"
    assert stub.bodies == []


def test_a_first_file_does_not_patch_a_body(monkeypatch):
    stub = _GH()
    res = _reconcile(
        stub,
        monkeypatch,
        red=True,
        fingerprint="zzz999",
        marker_key="flow-sentinel-fingerprint",
        title="[Flow Sentinel] something (1 failing)",
        body="`flow-sentinel-fingerprint:zzz999` first",
        red_body="`flow-sentinel-fingerprint:zzz999` refreshed",
        open_issues=[],
    )
    assert res["action"] == "filed"
    assert stub.created and stub.bodies == []


# ---------------------------------------------------------------------------
# The flow sentinel's own body
# ---------------------------------------------------------------------------


def _flow_result(n=8):
    return {
        "flow": "resolved_state",
        "checked": 49,
        "failures": [
            {"detail": f"event {i} live 40h before commence_time", "event_id": 15200380 + i}
            for i in range(n)
        ],
        "evidence": {"sampled": 49},
    }


def test_the_refreshed_body_says_it_is_refreshed():
    """A reader who cannot tell a rewritten body from the original cannot tell
    how old the finding is either."""
    first = fs.build_flow_issue_body(_flow_result())
    later = fs.build_flow_issue_body(_flow_result(), refreshed=True)

    assert "refreshed by a later run" in later
    assert "refreshed by a later run" not in first
    assert "comment thread below is the history" in later


def test_the_refreshed_body_keeps_the_dedupe_key_so_the_refresh_is_not_refused():
    """Ties the two halves together: `reconcile_issue` refuses a body without
    the fingerprint, so the builder must always emit it — including on the
    refresh path, where a missing key would silently disable the whole feature.
    """
    fp = fs.flow_fingerprint("resolved_state")
    body = fs.build_flow_issue_body(_flow_result(), refreshed=True)
    assert fp in body


def test_the_refreshed_body_carries_the_structured_keys_not_just_prose():
    """UX-P091's finding, held on the refresh path too: a filed issue used to
    lose every structured key, so #1942 was filed naming two teams and NO id.
    """
    body = fs.build_flow_issue_body(_flow_result(), refreshed=True)
    assert "15200380" in body, "the event id did not survive into the refreshed body"


def test_the_flow_sentinel_passes_a_refreshed_body_to_the_rail():
    """The wiring. Without this the whole feature is dead code."""
    import inspect

    src = inspect.getsource(fs.file_flow_issue)
    assert "red_body=" in src
    assert "refreshed=True" in src
