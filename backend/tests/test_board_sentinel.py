"""Tests for the Board Sentinel (Queue #258).

Pure fixtures cover: green, each red class, mixed red, column-unknown, fetch
failure → UNKNOWN, stable fingerprint, repeat-run dedup, and GraphQL pagination.
No production mutation — GitHub calls are monkeypatched.
"""

import importlib
from datetime import datetime, timedelta, timezone

import app.tasks.bug_report_github as gh

# app.tasks.board_sentinel as a bare attribute resolves to the Celery task object,
# not the module — import the module explicitly (gotcha noted in test_grid_sentinel).
bs = importlib.import_module("app.tasks.board_sentinel")

NOW = datetime(2026, 7, 27, 12, 0, 0, tzinfo=timezone.utc)


def _iss(number, *, labels=("alert-intake",), body="", title="", column=None, age_hours=1.0):
    return {
        "number": number,
        "title": title,
        "body": body,
        "labels": list(labels),
        "created_at": (NOW - timedelta(hours=age_hours)).isoformat(),
        "column": column,
    }


# --------------------------------------------------------------------------
# Fingerprint stability + repeat-run dedup
# --------------------------------------------------------------------------
def test_fingerprint_stable_across_runs():
    assert bs.board_fingerprint() == bs.board_fingerprint()
    assert len(bs.board_fingerprint()) == 12


# --------------------------------------------------------------------------
# Individual checks
# --------------------------------------------------------------------------
def test_duplicate_fingerprints_flagged():
    fp = "deadbeef1234"
    issues = [
        _iss(10, body=f"`flow-sentinel-fingerprint:{fp}`"),
        _iss(20, body=f"`flow-sentinel-fingerprint:{fp}`"),
        _iss(30, body="`flow-sentinel-fingerprint:other99999`"),
    ]
    out = bs.check_duplicate_fingerprints(issues)
    assert len(out) == 1
    assert out[0]["fingerprint"] == fp
    assert out[0]["issues"] == [10, 20]


def test_duplicate_fingerprints_ignores_board_own_marker():
    fp = bs.board_fingerprint()
    issues = [
        _iss(10, body=f"`board-sentinel-fingerprint:{fp}`"),
        _iss(20, body=f"`board-sentinel-fingerprint:{fp}`"),
    ]
    # Would be single-by-construction; never self-flag.
    assert bs.check_duplicate_fingerprints(issues) == []


def test_stale_inbox_flagged_only_past_bar():
    issues = [
        _iss(10, column="Inbox", age_hours=72),   # stale
        _iss(20, column="Inbox", age_hours=12),   # fresh
        _iss(30, column="Ready", age_hours=200),  # not in Inbox
    ]
    out = bs.check_stale_inbox(issues, NOW, max_hours=48)
    assert [o["issue"] for o in out] == [10]


def test_template_p1_share_flagged_above_cap():
    intake = [_iss(n, labels=("alert-intake", "priority:p1")) for n in range(1, 6)]
    intake += [_iss(99, labels=("alert-intake", "priority:p2"))]
    out = bs.check_template_p1_share(intake, cap=0.35, min_population=6)
    assert len(out) == 1
    assert out[0]["share"] > 0.35


def test_template_p1_share_below_floor_never_flags():
    intake = [_iss(n, labels=("alert-intake", "priority:p1")) for n in range(1, 4)]
    assert bs.check_template_p1_share(intake, cap=0.35, min_population=6) == []


def test_blocked_in_inbox_flagged():
    issues = [
        _iss(10, labels=("alert-intake", "blocked"), column="Inbox"),
        _iss(20, labels=("blocked",), column="Ready"),  # blocked but out of Inbox — ok
    ]
    out = bs.check_blocked_in_inbox(issues)
    assert [o["issue"] for o in out] == [10]


def test_missing_area_label_flagged():
    issues = [
        _iss(10, labels=("alert-intake", "needs-agent")),         # no area:*
        _iss(20, labels=("alert-intake", "area:infra")),          # ok
        _iss(30, labels=("bug-report",)),                          # not intake — skipped
    ]
    out = bs.check_missing_area_label(issues)
    assert [o["issue"] for o in out] == [10]


# --------------------------------------------------------------------------
# classify + verdict
# --------------------------------------------------------------------------
def test_classify_green_clean_board():
    issues = [_iss(10, labels=("alert-intake", "area:infra"), column="Ready")]
    c = bs.classify_board(issues, NOW, columns_available=True)
    assert c["real"] == []
    assert c["unknown"] == []
    assert bs.board_verdict(c) == "green"


def test_classify_mixed_red():
    fp = "deadbeef1234"
    issues = [
        _iss(10, labels=("alert-intake", "area:infra"), body=f"`flow-sentinel-fingerprint:{fp}`"),
        _iss(20, labels=("alert-intake", "area:infra"), body=f"`flow-sentinel-fingerprint:{fp}`"),
        _iss(30, labels=("alert-intake",), column="Inbox", age_hours=100),  # missing area + stale
    ]
    c = bs.classify_board(issues, NOW, columns_available=True)
    kinds = {f["check"] for f in c["real"]}
    assert "duplicate_fingerprint" in kinds
    assert "missing_area_label" in kinds
    assert "stale_inbox" in kinds
    assert bs.board_verdict(c) == "red"


def test_classify_unknown_when_columns_unavailable():
    issues = [_iss(10, labels=("alert-intake", "area:infra"))]
    c = bs.classify_board(issues, NOW, columns_available=False)
    assert c["real"] == []
    assert any(u["check"] == "inbox_column_checks" for u in c["unknown"])
    assert bs.board_verdict(c) == "unknown"


def test_classify_fetch_error_is_unknown_not_green():
    c = bs.classify_board([], NOW, columns_available=False,
                          fetch_errors=[{"detail": "GITHUB_TOKEN unset"}])
    assert bs.board_verdict(c) == "unknown"
    assert any(u["check"] == "fetch_error" for u in c["unknown"])


def test_red_takes_precedence_over_unknown():
    fp = "deadbeef1234"
    issues = [
        _iss(10, labels=("alert-intake", "area:infra"), body=f"`flow-sentinel-fingerprint:{fp}`"),
        _iss(20, labels=("alert-intake", "area:infra"), body=f"`flow-sentinel-fingerprint:{fp}`"),
    ]
    c = bs.classify_board(issues, NOW, columns_available=False)  # columns unknown
    assert c["real"]  # duplicate still detected
    assert bs.board_verdict(c) == "red"  # RED wins over unknown


# --------------------------------------------------------------------------
# Filing lifecycle
# --------------------------------------------------------------------------
def test_file_board_issue_unknown_no_op(monkeypatch):
    monkeypatch.setattr(gh, "GITHUB_TOKEN", "tok")
    c = {"real": [], "unknown": [{"check": "fetch_error", "detail": "x"}], "counts": {}}
    res = bs.file_board_issue(c, open_issues=[])
    assert res["action"] == "unknown_no_op"


def test_file_board_issue_green_closes(monkeypatch):
    monkeypatch.setattr(gh, "GITHUB_TOKEN", "tok")
    closed = {}
    monkeypatch.setattr(gh, "close_issue", lambda n, comment=None: closed.update(n=n))
    fp = bs.board_fingerprint()
    existing = [_iss(500, body=f"`board-sentinel-fingerprint:{fp}`")]
    c = {"real": [], "unknown": [], "counts": {}}
    res = bs.file_board_issue(c, open_issues=existing)
    assert res["action"] == "resolved"
    assert closed["n"] == 500


def test_file_board_issue_red_files_p1_for_duplicates(monkeypatch):
    monkeypatch.setattr(gh, "GITHUB_TOKEN", "tok")
    created = {}
    monkeypatch.setattr(gh, "create_github_issue",
                        lambda t, b, labels: (created.update(labels=labels) or (777, "N")))
    monkeypatch.setattr(gh, "add_to_project_board", lambda nid: None)
    c = {
        "real": [{"check": "duplicate_fingerprint", "detail": "dup"}],
        "unknown": [],
        "counts": {"open_alert_intake": 5},
    }
    res = bs.file_board_issue(c, open_issues=[])
    assert res["action"] == "filed"
    assert "priority:p1" in created["labels"]
    assert "area:admin-ops" in created["labels"]


def test_file_board_issue_red_files_p2_default(monkeypatch):
    monkeypatch.setattr(gh, "GITHUB_TOKEN", "tok")
    created = {}
    monkeypatch.setattr(gh, "create_github_issue",
                        lambda t, b, labels: (created.update(labels=labels) or (778, "N")))
    monkeypatch.setattr(gh, "add_to_project_board", lambda nid: None)
    c = {
        "real": [{"check": "missing_area_label", "detail": "x"}],
        "unknown": [],
        "counts": {"open_alert_intake": 5},
    }
    res = bs.file_board_issue(c, open_issues=[])
    assert "priority:p2" in created["labels"]


# --------------------------------------------------------------------------
# GraphQL column fetch — pagination + failure
# --------------------------------------------------------------------------
def test_fetch_project_columns_paginates(monkeypatch):
    monkeypatch.setattr(gh, "GITHUB_TOKEN", "tok")
    monkeypatch.setattr(gh, "PROJECT_ID", "PVT_x")

    def node(num, status):
        return {"content": {"number": num}, "fieldValueByName": {"name": status}}

    pages = [
        {"data": {"node": {"items": {
            "pageInfo": {"hasNextPage": True, "endCursor": "c1"},
            "nodes": [node(1, "Inbox"), node(2, "Ready")],
        }}}},
        {"data": {"node": {"items": {
            "pageInfo": {"hasNextPage": False, "endCursor": None},
            "nodes": [node(3, "Done")],
        }}}},
    ]
    state = {"i": 0}

    class FakeResp:
        def __init__(self, d):
            self._d = d

        def raise_for_status(self):
            pass

        def json(self):
            return self._d

    def fake_post(url, headers=None, json=None, timeout=None):
        d = pages[state["i"]]
        state["i"] += 1
        return FakeResp(d)

    monkeypatch.setattr(bs.httpx, "post", fake_post)
    cols = bs._fetch_project_columns()
    assert cols == {1: "Inbox", 2: "Ready", 3: "Done"}


def test_fetch_project_columns_failure_returns_none(monkeypatch):
    monkeypatch.setattr(gh, "GITHUB_TOKEN", "tok")
    monkeypatch.setattr(gh, "PROJECT_ID", "PVT_x")

    def boom(*a, **k):
        raise RuntimeError("graphql down")

    monkeypatch.setattr(bs.httpx, "post", boom)
    assert bs._fetch_project_columns() is None


def test_fetch_project_columns_graphql_errors_returns_none(monkeypatch):
    monkeypatch.setattr(gh, "GITHUB_TOKEN", "tok")
    monkeypatch.setattr(gh, "PROJECT_ID", "PVT_x")

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"errors": [{"message": "bad"}]}

    monkeypatch.setattr(bs.httpx, "post", lambda *a, **k: FakeResp())
    assert bs._fetch_project_columns() is None


class TestRunBoardSentinel:
    """End-to-end runner with fetch + Redis monkeypatched (no network)."""

    def _run(self, monkeypatch, issues, columns_available, errors=None):
        import asyncio

        monkeypatch.setattr(bs, "_fetch_board_state",
                            lambda: (issues, columns_available, errors or []))
        monkeypatch.setattr(bs, "_load_overrides", lambda: None)

        class FakeRedis:
            def setex(self, *a, **k):
                pass

        monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda *a, **k: FakeRedis())
        return asyncio.run(bs._run_board_sentinel(file_issues=False, now=NOW))

    def test_run_green(self, monkeypatch):
        issues = [_iss(10, labels=("alert-intake", "area:infra"), column="Ready")]
        stats = self._run(monkeypatch, issues, columns_available=True)
        assert stats["verdict"] == "green"
        assert stats["offenders"] == []
        assert stats["filed"] is None  # detect-only
        assert stats["generated_at"] == NOW.isoformat()

    def test_run_red_aggregates_offenders(self, monkeypatch):
        fp = "deadbeef1234"
        issues = [
            _iss(10, labels=("alert-intake", "area:infra"), body=f"`flow-sentinel-fingerprint:{fp}`"),
            _iss(20, labels=("alert-intake", "area:infra"), body=f"`flow-sentinel-fingerprint:{fp}`"),
            _iss(30, labels=("alert-intake",), column="Inbox", age_hours=100),
        ]
        stats = self._run(monkeypatch, issues, columns_available=True)
        assert stats["verdict"] == "red"
        # offenders unions duplicate-issue lists + single-issue findings
        assert set(stats["offenders"]) >= {10, 20, 30}

    def test_run_unknown_on_fetch_error(self, monkeypatch):
        stats = self._run(monkeypatch, [], columns_available=False,
                          errors=[{"detail": "GITHUB_TOKEN unset"}])
        assert stats["verdict"] == "unknown"
