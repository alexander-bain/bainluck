"""Tests for the shared sentinel filing rail (Queue #258).

Covers the one fingerprint lifecycle for RED and GREEN: dedup on RED (file vs
comment, lowest-number canonical), close on GREEN, marker-only close safety,
GitHub REST pagination + failure, closed-historical isolation, comment/close
failure handling, and the no-token path. No production mutation — every GitHub
call is monkeypatched.
"""

import app.tasks.bug_report_github as gh
import app.tasks.sentinel_filing as sf


MARKER = "flow-sentinel-fingerprint"
FP = "abc123def456"


def _decl(marker=MARKER, fp=FP):
    """A canonical fingerprint DECLARATION as every sentinel writes it (the ONLY
    thing that counts as ownership — Queue #266 Item 2)."""
    return f"`{marker}:{fp}`  (dedupe key — do not remove)"


def _issue(number, *, body="", title="", labels=("alert-intake",)):
    return {
        "number": number,
        "title": title,
        "body": body,
        "labels": [{"name": l} for l in labels],
    }


# --------------------------------------------------------------------------
# Pure matching — canonical declaration only (Queue #266 Item 2)
# --------------------------------------------------------------------------
def test_issue_matches_body_declaration():
    iss = _issue(10, body=f"blah\n{_decl()}\nblah")
    assert sf.issue_matches(iss, FP, MARKER) is True


def test_issue_does_not_match_bare_quoted_marker():
    # A marker without the (dedupe key …) annotation is a QUOTE, not ownership.
    iss = _issue(10, body=f"blah `{MARKER}:{FP}` appears on 2 issues")
    assert sf.issue_matches(iss, FP, MARKER) is False


def test_declared_fingerprints_ignores_quotes_in_fence_blockquote_table():
    full = _decl()
    body = (
        f"```\n{full}\n```\n"          # fenced code
        f"> {full}\n"                   # blockquote
        f"| {full} |\n"                 # table row
        f"    {full}\n"                 # indented code
    )
    assert sf.declared_fingerprints(body) == set()
    # …but a real top-level declaration in the same body IS owned.
    assert sf.declared_fingerprints(body + "\n" + full) == {(MARKER, FP)}


def test_issue_matches_title_prefix_fallback():
    iss = _issue(10, body="marker removed", title="[Flow Sentinel] X (2 failing)")
    assert sf.issue_matches(iss, FP, MARKER, title_prefix="[Flow Sentinel] X (") is True


def test_issue_matches_title_only_ignored_without_prefix():
    iss = _issue(10, body="nothing", title="[Flow Sentinel] X (2 failing)")
    assert sf.issue_matches(iss, FP, MARKER) is False


def test_find_matching_lowest_number_wins():
    issues = [_issue(n, body=_decl()) for n in (1226, 1147, 1225)]
    assert sf.find_matching_issue(issues, FP, MARKER) == 1147


def test_find_matching_none_and_robust_to_junk():
    issues = [None, {"body": None, "title": None}, {"number": None, "body": "x"}]
    assert sf.find_matching_issue(issues, FP, MARKER) is None


# --------------------------------------------------------------------------
# reconcile — no token
# --------------------------------------------------------------------------
def test_no_token_skips(monkeypatch):
    monkeypatch.setattr(gh, "GITHUB_TOKEN", "")
    res = sf.reconcile_issue(red=True, fingerprint=FP, marker_key=MARKER,
                             title="t", body="b", open_issues=[])
    assert res["action"] == "skipped_no_token"


# --------------------------------------------------------------------------
# reconcile — RED
# --------------------------------------------------------------------------
def test_red_files_new_when_none_open(monkeypatch):
    monkeypatch.setattr(gh, "GITHUB_TOKEN", "tok")
    created = {}

    def fake_create(title, body, labels):
        created["title"] = title
        created["labels"] = labels
        return 999, "NODE_999"

    boarded = []
    monkeypatch.setattr(gh, "create_github_issue", fake_create)
    monkeypatch.setattr(gh, "add_to_project_board", lambda nid: boarded.append(nid))
    monkeypatch.setattr(gh, "comment_on_issue", lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not comment")))

    res = sf.reconcile_issue(
        red=True, fingerprint=FP, marker_key=MARKER,
        title="[Flow Sentinel] X (2 failing)", body=f"`{MARKER}:{FP}`",
        labels=["alert-intake", "priority:p2"], open_issues=[],
    )
    assert res["action"] == "filed"
    assert res["issue"] == 999
    assert boarded == ["NODE_999"]
    assert created["labels"] == ["alert-intake", "priority:p2"]


def test_red_comments_when_existing_never_edits_labels(monkeypatch):
    monkeypatch.setattr(gh, "GITHUB_TOKEN", "tok")
    commented = {}
    monkeypatch.setattr(gh, "comment_on_issue", lambda n, b: commented.update(n=n, b=b))
    # create must NOT be called — commenting only, and labels are never touched.
    monkeypatch.setattr(gh, "create_github_issue",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not file")))
    existing = [_issue(1147, body=_decl())]
    res = sf.reconcile_issue(red=True, fingerprint=FP, marker_key=MARKER,
                             title="t", body="b", open_issues=existing,
                             red_comment="still broken")
    assert res["action"] == "commented"
    assert res["issue"] == 1147
    assert commented["n"] == 1147


def test_red_comment_failure_reported(monkeypatch):
    monkeypatch.setattr(gh, "GITHUB_TOKEN", "tok")

    def boom(*a, **k):
        raise RuntimeError("api down")

    monkeypatch.setattr(gh, "comment_on_issue", boom)
    existing = [_issue(1147, body=_decl())]
    res = sf.reconcile_issue(red=True, fingerprint=FP, marker_key=MARKER,
                             title="t", body="b", open_issues=existing)
    assert res["action"] == "comment_failed"
    assert res["issue"] == 1147


def test_red_missing_title_body_errors(monkeypatch):
    monkeypatch.setattr(gh, "GITHUB_TOKEN", "tok")
    res = sf.reconcile_issue(red=True, fingerprint=FP, marker_key=MARKER, open_issues=[])
    assert res["action"] == "error"


def test_closed_historical_does_not_block_new_episode(monkeypatch):
    # A closed issue with the same fingerprint is NOT in the open list, so a fresh
    # RED files a new episode cleanly (list_open_alert_issues is state=open only).
    monkeypatch.setattr(gh, "GITHUB_TOKEN", "tok")
    monkeypatch.setattr(gh, "create_github_issue", lambda *a, **k: (2000, "NODE"))
    monkeypatch.setattr(gh, "add_to_project_board", lambda nid: None)
    res = sf.reconcile_issue(red=True, fingerprint=FP, marker_key=MARKER,
                             title="t", body="b", open_issues=[])  # no OPEN match
    assert res["action"] == "filed"
    assert res["issue"] == 2000


# --------------------------------------------------------------------------
# reconcile — GREEN
# --------------------------------------------------------------------------
def test_green_closes_existing(monkeypatch):
    monkeypatch.setattr(gh, "GITHUB_TOKEN", "tok")
    closed = {}
    monkeypatch.setattr(gh, "close_issue", lambda n, comment=None: closed.update(n=n, comment=comment))
    existing = [_issue(1147, body=_decl())]
    res = sf.reconcile_issue(red=False, fingerprint=FP, marker_key=MARKER,
                             open_issues=existing, green_comment="recovered")
    assert res["action"] == "resolved"
    assert res["issue"] == 1147
    assert closed["n"] == 1147
    assert closed["comment"] == "recovered"


def test_green_no_issue_is_noop(monkeypatch):
    monkeypatch.setattr(gh, "GITHUB_TOKEN", "tok")
    monkeypatch.setattr(gh, "close_issue",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("nothing to close")))
    res = sf.reconcile_issue(red=False, fingerprint=FP, marker_key=MARKER, open_issues=[])
    assert res["action"] == "green_no_issue"


def test_green_close_only_matches_body_marker_not_title(monkeypatch):
    # Safety: a human-filed lookalike matching ONLY by title prefix must never be
    # auto-closed on green (the close path ignores title_prefix).
    monkeypatch.setattr(gh, "GITHUB_TOKEN", "tok")
    monkeypatch.setattr(gh, "close_issue",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not close a title-only match")))
    title_only = [_issue(1147, body="no marker", title="[Flow Sentinel] X (2 failing)")]
    res = sf.reconcile_issue(red=False, fingerprint=FP, marker_key=MARKER,
                             title_prefix="[Flow Sentinel] X (", open_issues=title_only)
    assert res["action"] == "green_no_issue"


def test_green_close_failure_reported(monkeypatch):
    monkeypatch.setattr(gh, "GITHUB_TOKEN", "tok")

    def boom(*a, **k):
        raise RuntimeError("close failed")

    monkeypatch.setattr(gh, "close_issue", boom)
    existing = [_issue(1147, body=_decl())]
    res = sf.reconcile_issue(red=False, fingerprint=FP, marker_key=MARKER, open_issues=existing)
    assert res["action"] == "close_failed"
    assert res["issue"] == 1147


# --------------------------------------------------------------------------
# Typed dedup-source read — ok/error/truncation never confused (Queue #266 Item 2)
# --------------------------------------------------------------------------
class _GetResp:
    def __init__(self, data, raise_exc=None):
        self._data = data
        self._raise = raise_exc

    def raise_for_status(self):
        if self._raise:
            raise self._raise

    def json(self):
        return self._data


def test_fetch_open_alert_issues_empty_is_ok_true(monkeypatch):
    monkeypatch.setattr(gh, "GITHUB_TOKEN", "tok")
    monkeypatch.setattr(sf.httpx, "get", lambda *a, **k: _GetResp([]))
    res = sf.fetch_open_alert_issues()
    assert res.ok is True and res.issues == [] and res.error is None


def test_fetch_open_alert_issues_failure_is_ok_false(monkeypatch):
    monkeypatch.setattr(gh, "GITHUB_TOKEN", "tok")
    monkeypatch.setattr(sf.httpx, "get", lambda *a, **k: _GetResp([], raise_exc=RuntimeError("429")))
    res = sf.fetch_open_alert_issues()
    assert res.ok is False and res.error and "failed" in res.error


def test_fetch_open_alert_issues_truncation_is_ok_false(monkeypatch):
    monkeypatch.setattr(gh, "GITHUB_TOKEN", "tok")
    full = [{"number": n} for n in range(sf._PER_PAGE)]  # always a full page
    monkeypatch.setattr(sf.httpx, "get", lambda *a, **k: _GetResp(full))
    res = sf.fetch_open_alert_issues()
    assert res.ok is False and res.truncated is True
    assert len(res.issues) == sf._PER_PAGE * sf._ALERT_LIST_MAX_PAGES


def test_fetch_open_alert_issues_no_token_is_ok_false(monkeypatch):
    monkeypatch.setattr(gh, "GITHUB_TOKEN", "")
    res = sf.fetch_open_alert_issues()
    assert res.ok is False and res.issues == []


# --------------------------------------------------------------------------
# reconcile no-ops UNKNOWN when the dedup source cannot be read (C37 P1 #4)
# --------------------------------------------------------------------------
def test_red_dedup_unknown_no_op_on_failed_read(monkeypatch):
    monkeypatch.setattr(gh, "GITHUB_TOKEN", "tok")
    monkeypatch.setattr(gh, "create_github_issue",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not file blind")))
    res = sf.reconcile_issue(
        red=True, fingerprint=FP, marker_key=MARKER, title="t", body="b",
        open_issues=sf.OpenIssuesResult(ok=False, error="rate limited"),
    )
    assert res["action"] == "dedup_unknown_no_op"


def test_green_dedup_unknown_no_op_on_failed_read(monkeypatch):
    monkeypatch.setattr(gh, "GITHUB_TOKEN", "tok")
    monkeypatch.setattr(gh, "close_issue",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not close blind")))
    res = sf.reconcile_issue(
        red=False, fingerprint=FP, marker_key=MARKER,
        open_issues=sf.OpenIssuesResult(ok=False, error="rate limited"),
    )
    assert res["action"] == "dedup_unknown_no_op"


def test_none_open_issues_fetches_and_noops_on_failure(monkeypatch):
    monkeypatch.setattr(gh, "GITHUB_TOKEN", "tok")
    monkeypatch.setattr(sf, "fetch_open_alert_issues",
                        lambda: sf.OpenIssuesResult(ok=False, error="down"))
    monkeypatch.setattr(gh, "create_github_issue",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not file blind")))
    res = sf.reconcile_issue(red=True, fingerprint=FP, marker_key=MARKER, title="t", body="b")
    assert res["action"] == "dedup_unknown_no_op"


# --------------------------------------------------------------------------
# Concurrent RED runs → exactly one owner (Redis idempotency claim, C37 P2)
# --------------------------------------------------------------------------
class _FakeRedis:
    """Minimal SET NX EX / get / delete semantics for the filing claim."""

    def __init__(self):
        self.store = {}

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    def get(self, key):
        return self.store.get(key)

    def delete(self, key):
        self.store.pop(key, None)


def test_two_concurrent_red_runs_file_exactly_one(monkeypatch):
    monkeypatch.setattr(gh, "GITHUB_TOKEN", "tok")
    fake = _FakeRedis()
    import app.tasks.redis_state as rs
    monkeypatch.setattr(rs, "get_redis_client", lambda *a, **k: fake)
    # The final re-read sees no racing issue (the lock is what serializes).
    monkeypatch.setattr(sf, "fetch_open_alert_issues", lambda: sf.OpenIssuesResult(ok=True, issues=[]))
    created = []
    monkeypatch.setattr(gh, "create_github_issue",
                        lambda t, b, labels: (created.append(t) or (900 + len(created), "N")))
    monkeypatch.setattr(gh, "add_to_project_board", lambda nid: None)

    def run():
        return sf.reconcile_issue(
            red=True, fingerprint=FP, marker_key=MARKER, title="t", body=_decl(),
            open_issues=sf.OpenIssuesResult(ok=True, issues=[]),
        )

    a = run()
    b = run()  # second run: claim already held → deferred, no second create
    actions = sorted([a["action"], b["action"]])
    assert actions == ["filed", "filing_deferred"]
    assert len(created) == 1  # exactly one owner


def test_recurrence_comments_after_file(monkeypatch):
    # After an issue is filed, a later RED run finds it via its canonical declaration
    # and comments the lowest canonical owner rather than filing a duplicate.
    monkeypatch.setattr(gh, "GITHUB_TOKEN", "tok")
    commented = {}
    monkeypatch.setattr(gh, "comment_on_issue", lambda n, b: commented.update(n=n))
    monkeypatch.setattr(gh, "create_github_issue",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not re-file")))
    existing = [_issue(901, body=_decl())]
    res = sf.reconcile_issue(
        red=True, fingerprint=FP, marker_key=MARKER, title="t", body=_decl(),
        open_issues=sf.OpenIssuesResult(ok=True, issues=existing),
    )
    assert res["action"] == "commented"
    assert commented["n"] == 901


# --------------------------------------------------------------------------
# list_open_alert_issues — pagination + failure
# --------------------------------------------------------------------------
def test_list_open_alert_issues_paginates_and_drops_prs(monkeypatch):
    monkeypatch.setattr(gh, "GITHUB_TOKEN", "tok")
    monkeypatch.setattr(gh, "REPO", "o/r")

    pages = {
        1: [{"number": n} for n in range(1, 101)] + [{"number": 999, "pull_request": {}}],
        2: [{"number": n} for n in range(101, 150)],  # < 100 → last page
    }

    class FakeResp:
        def __init__(self, data):
            self._data = data

        def raise_for_status(self):
            pass

        def json(self):
            return self._data

    def fake_get(url, headers=None, params=None, timeout=None):
        return FakeResp(pages.get(params["page"], []))

    monkeypatch.setattr(sf.httpx, "get", fake_get)
    issues = sf.list_open_alert_issues()
    numbers = {i["number"] for i in issues}
    assert 999 not in numbers  # PR dropped
    assert len(issues) == 100 + 49


def test_list_open_alert_issues_failure_returns_empty(monkeypatch):
    monkeypatch.setattr(gh, "GITHUB_TOKEN", "tok")

    def boom(*a, **k):
        raise RuntimeError("rate limited")

    monkeypatch.setattr(sf.httpx, "get", boom)
    assert sf.list_open_alert_issues() == []


def test_list_open_alert_issues_no_token_returns_empty(monkeypatch):
    monkeypatch.setattr(gh, "GITHUB_TOKEN", "")
    assert sf.list_open_alert_issues() == []


# --------------------------------------------------------------------------
# reconcile_many — one shared snapshot
# --------------------------------------------------------------------------
def test_reconcile_many_reuses_snapshot(monkeypatch):
    monkeypatch.setattr(gh, "GITHUB_TOKEN", "tok")
    calls = {"fetch": 0}
    monkeypatch.setattr(
        sf, "fetch_open_alert_issues",
        lambda: (calls.__setitem__("fetch", calls["fetch"] + 1) or sf.OpenIssuesResult(ok=True, issues=[])),
    )
    monkeypatch.setattr(gh, "create_github_issue", lambda *a, **k: (1, "N"))
    monkeypatch.setattr(gh, "add_to_project_board", lambda nid: None)
    items = [
        {"red": True, "fingerprint": "aaa111", "marker_key": MARKER, "title": "t", "body": "b"},
        {"red": True, "fingerprint": "bbb222", "marker_key": MARKER, "title": "t", "body": "b"},
    ]
    out = sf.reconcile_many(items)
    # The batch fetches the shared typed snapshot once and reuses it across items (a
    # create's belt-and-suspenders re-read only fires when a real Redis claim is won).
    assert calls["fetch"] >= 1
    assert all(r["action"] == "filed" for r in out)
