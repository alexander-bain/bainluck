"""Tests for the Board Sentinel (Queue #258, extended by Queue #265).

Pure fixtures cover: full-board population counting, canonical-declaration vs
quoted-marker fingerprint ownership, every routing invariant (stale-inbox,
label/status parity, needs-agent conflict, area completeness, Ready scoping,
missing-from-project), green/red/unknown classification, filing lifecycle, and the
REST + Project GraphQL fetch layer (pagination beyond 1,000, closed filtering,
duplicate cards, truncation → UNKNOWN). No production mutation — GitHub calls are
monkeypatched.
"""

import importlib
from datetime import datetime, timedelta, timezone

import app.tasks.bug_report_github as gh

# app.tasks.board_sentinel as a bare attribute resolves to the Celery task object,
# not the module — import the module explicitly (gotcha noted in test_grid_sentinel).
bs = importlib.import_module("app.tasks.board_sentinel")

NOW = datetime(2026, 7, 27, 12, 0, 0, tzinfo=timezone.utc)


def _iss(number, *, labels=("alert-intake",), body="", title="", column=None,
         age_hours=1.0, assignees=()):
    return {
        "number": number,
        "title": title,
        "body": body,
        "labels": list(labels),
        "assignees": list(assignees),
        "created_at": (NOW - timedelta(hours=age_hours)).isoformat(),
        "column": column,
    }


def _decl(marker, fp):
    """A canonical fingerprint DECLARATION as every sentinel writes it."""
    return f"`{marker}:{fp}`  (dedupe key — do not remove)"


# --------------------------------------------------------------------------
# Fingerprint stability + repeat-run dedup
# --------------------------------------------------------------------------
def test_fingerprint_stable_across_runs():
    assert bs.board_fingerprint() == bs.board_fingerprint()
    assert len(bs.board_fingerprint()) == 12


# --------------------------------------------------------------------------
# Item 2 — canonical declaration vs quoted marker
# --------------------------------------------------------------------------
def test_declared_fingerprints_only_counts_declarations():
    fp = "aed6b9f57b97"
    body = (
        f"{_decl('sentinel-fingerprint', fp)}\n\n"
        "some prose here"
    )
    assert bs._declared_fingerprints_in(body) == {("sentinel-fingerprint", fp)}


def test_declared_fingerprints_ignores_quoted_marker():
    fp = "aed6b9f57b97"
    # A cleanup-report / evidence-table QUOTE — marker not followed by the dedupe key.
    body = (
        f"- **[duplicate_fingerprint]** `sentinel-fingerprint:{fp}` appears on 2 "
        "open alert-intake issues [1140, 1447]\n"
        f"original #1140 and re-file #1437 carry the marker `sentinel-fingerprint:{fp}` "
        "(series KXNHLAST)"
    )
    assert bs._declared_fingerprints_in(body) == set()


def test_duplicate_fingerprints_flagged():
    fp = "deadbeef1234"
    issues = [
        _iss(10, body=_decl("flow-sentinel-fingerprint", fp)),
        _iss(20, body=_decl("flow-sentinel-fingerprint", fp)),
        _iss(30, body=_decl("flow-sentinel-fingerprint", "other99999")),
    ]
    out = bs.check_duplicate_fingerprints(issues)
    assert len(out) == 1
    assert out[0]["fingerprint"] == fp
    assert out[0]["issues"] == [10, 20]


def test_duplicate_fingerprints_declaration_owner_beats_quote():
    """#1140 declares the fingerprint; a cleanup/meta issue #1449 only QUOTES it in
    an evidence table. The quoter must NOT become a phantom duplicate owner."""
    fp = "aed6b9f57b97"
    issues = [
        _iss(1140, body=_decl("sentinel-fingerprint", fp)),
        _iss(1449, body=(
            f"- **[duplicate_fingerprint]** `sentinel-fingerprint:{fp}` appears on 2 "
            "open alert-intake issues"
        )),
    ]
    assert bs.check_duplicate_fingerprints(issues) == []


def test_duplicate_fingerprints_two_real_declarations_still_red():
    fp = "aed6b9f57b97"
    issues = [
        _iss(1140, body=_decl("sentinel-fingerprint", fp)),
        _iss(1437, body=_decl("sentinel-fingerprint", fp)),
    ]
    out = bs.check_duplicate_fingerprints(issues)
    assert len(out) == 1
    assert out[0]["issues"] == [1140, 1437]


def test_duplicate_fingerprints_ignores_board_own_marker():
    fp = bs.board_fingerprint()
    issues = [
        _iss(10, body=_decl("board-sentinel-fingerprint", fp)),
        _iss(20, body=_decl("board-sentinel-fingerprint", fp)),
    ]
    # Would be single-by-construction; never self-flag.
    assert bs.check_duplicate_fingerprints(issues) == []


# --------------------------------------------------------------------------
# Item 3 — routing invariant checks
# --------------------------------------------------------------------------
def test_stale_inbox_flagged_only_past_bar_board_wide():
    issues = [
        _iss(10, column="Inbox", age_hours=72),                     # stale intake
        _iss(20, column="Inbox", age_hours=12),                     # fresh — exempt
        _iss(30, column="Ready", age_hours=200),                    # not in Inbox
        _iss(40, labels=("bug-report",), column="Inbox", age_hours=90),  # non-intake, stale
    ]
    out = bs.check_stale_inbox(issues, NOW, max_hours=48)
    assert sorted(o["issue"] for o in out) == [10, 40]


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
        _iss(20, labels=("blocked",), column="Blocked"),  # blocked + in Blocked — ok
    ]
    out = bs.check_blocked_in_inbox(issues)
    assert [o["issue"] for o in out] == [10]


def test_missing_area_label_flagged_board_wide_with_meta_exemption():
    issues = [
        _iss(10, labels=("alert-intake", "needs-agent")),   # no area:* → flagged
        _iss(20, labels=("alert-intake", "area:infra")),    # ok
        _iss(30, labels=("bug-report",)),                    # non-intake, no area → flagged
        _iss(40, labels=("epic",)),                          # meta-exempt → skipped
    ]
    out = bs.check_missing_area_label(issues)
    assert [o["issue"] for o in out] == [10, 30]


def test_label_status_parity_both_directions():
    issues = [
        # label present, wrong column (non-Inbox) → flagged
        _iss(10, labels=("blocked",), column="Ready"),
        # in column, label missing → flagged
        _iss(20, labels=(), column="Needs User"),
        # correct pairing → ok
        _iss(30, labels=("parked",), column="Parked"),
        # blocked in Inbox → owned by check_blocked_in_inbox, NOT double-flagged here
        _iss(40, labels=("blocked",), column="Inbox"),
        # unknown column → skipped
        _iss(50, labels=("needs-user",), column=None),
    ]
    out = bs.check_label_status_parity(issues)
    flagged = sorted(o["issue"] for o in out)
    assert flagged == [10, 20]


def test_needs_agent_conflict_flagged():
    issues = [
        _iss(10, labels=("needs-agent", "blocked")),
        _iss(20, labels=("needs-agent", "parked")),
        _iss(30, labels=("needs-agent", "area:infra")),  # fine
        _iss(40, labels=("blocked",)),                    # blocked but no needs-agent — fine
    ]
    out = bs.check_needs_agent_conflict(issues)
    assert sorted(o["issue"] for o in out) == [10, 20]


def test_missing_from_project_flagged():
    issues = [_iss(10), _iss(20), _iss(30)]
    out = bs.check_missing_from_project(issues, project_numbers={10, 30})
    assert [o["issue"] for o in out] == [20]


def test_ready_scoping_flags_no_owner_and_thin_body():
    long_body = "x" * (bs.READY_MIN_BODY_CHARS + 10)
    issues = [
        # Ready, no owner signal → flagged
        _iss(10, labels=("area:infra",), column="Ready", body=long_body),
        # Ready, has needs-agent + long body → ok
        _iss(20, labels=("needs-agent",), column="Ready", body=long_body),
        # Ready, has assignee but thin body → flagged (under-scoped)
        _iss(30, labels=(), column="Ready", body="tiny", assignees=("alice",)),
        # Ready, owner-ready + long body → ok
        _iss(40, labels=("owner-ready",), column="Ready", body=long_body),
        # not Ready → skipped
        _iss(50, labels=(), column="Inbox", body="tiny"),
    ]
    out = bs.check_ready_scoping(issues)
    assert sorted(o["issue"] for o in out) == [10, 30]


# --------------------------------------------------------------------------
# Population counts (Item 1)
# --------------------------------------------------------------------------
def test_counts_scan_full_open_population_not_just_alerts():
    issues = [_iss(n, labels=("alert-intake", "area:infra")) for n in range(1, 27)]
    issues += [_iss(1000 + n, labels=("bug-report",), column="Inbox") for n in range(63)]
    c = bs.classify_board(
        issues, NOW, columns_available=True,
        project_numbers={i["number"] for i in issues}, open_project_items=89,
    )
    counts = c["counts"]
    assert counts["open_issues_scanned"] == 89
    assert counts["open_alert_intake"] == 26
    assert counts["open_project_items"] == 89
    assert counts["by_column"]["Inbox"] == 63


# --------------------------------------------------------------------------
# classify + verdict
# --------------------------------------------------------------------------
def test_classify_green_clean_board():
    issues = [_iss(10, labels=("alert-intake", "area:infra", "needs-agent"),
                   column="In Progress")]
    c = bs.classify_board(issues, NOW, columns_available=True, project_numbers={10})
    assert c["real"] == []
    assert c["unknown"] == []
    assert bs.board_verdict(c) == "green"


def test_classify_mixed_red():
    fp = "deadbeef1234"
    issues = [
        _iss(10, labels=("alert-intake", "area:infra"),
             body=_decl("flow-sentinel-fingerprint", fp), column="In Progress"),
        _iss(20, labels=("alert-intake", "area:infra"),
             body=_decl("flow-sentinel-fingerprint", fp), column="In Progress"),
        _iss(30, labels=("alert-intake",), column="Inbox", age_hours=100),  # missing area + stale
    ]
    c = bs.classify_board(issues, NOW, columns_available=True, project_numbers={10, 20, 30})
    kinds = {f["check"] for f in c["real"]}
    assert {"duplicate_fingerprint", "missing_area_label", "stale_inbox"} <= kinds
    assert bs.board_verdict(c) == "red"


def test_classify_unknown_when_columns_unavailable():
    issues = [_iss(10, labels=("alert-intake", "area:infra"))]
    c = bs.classify_board(issues, NOW, columns_available=False, project_numbers={10})
    assert c["real"] == []
    assert any(u["check"] == "inbox_column_checks" for u in c["unknown"])
    assert bs.board_verdict(c) == "unknown"


def test_classify_unknown_when_project_membership_unavailable():
    issues = [_iss(10, labels=("alert-intake", "area:infra"), column="In Progress")]
    c = bs.classify_board(issues, NOW, columns_available=True, project_numbers=None)
    assert c["real"] == []
    assert any(u["check"] == "project_membership" for u in c["unknown"])
    assert bs.board_verdict(c) == "unknown"


def test_classify_fetch_error_is_unknown_not_green():
    c = bs.classify_board([], NOW, columns_available=False,
                          fetch_errors=[{"detail": "GITHUB_TOKEN unset"}])
    assert bs.board_verdict(c) == "unknown"
    assert any(u["check"] == "fetch_error" for u in c["unknown"])


def test_red_takes_precedence_over_unknown():
    fp = "deadbeef1234"
    issues = [
        _iss(10, labels=("alert-intake", "area:infra"),
             body=_decl("flow-sentinel-fingerprint", fp)),
        _iss(20, labels=("alert-intake", "area:infra"),
             body=_decl("flow-sentinel-fingerprint", fp)),
    ]
    c = bs.classify_board(issues, NOW, columns_available=False)  # columns + membership unknown
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


def test_board_issue_body_carries_full_counts():
    c = {
        "real": [{"check": "missing_area_label", "detail": "x"}],
        "unknown": [],
        "counts": {"open_issues_scanned": 89, "open_project_items": 90,
                   "open_alert_intake": 26},
    }
    body = bs.build_board_issue_body(c)
    assert "Open issues scanned:** 89" in body
    assert "Open Project items:** 90" in body
    assert "Open alert-intake scanned:** 26" in body


# --------------------------------------------------------------------------
# REST open-issue fetch (Item 1)
# --------------------------------------------------------------------------
class _FakeGetResp:
    def __init__(self, data, raise_exc=None):
        self._data = data
        self._raise = raise_exc

    def raise_for_status(self):
        if self._raise:
            raise self._raise

    def json(self):
        return self._data


def test_fetch_open_issues_complete(monkeypatch):
    monkeypatch.setattr(gh, "GITHUB_TOKEN", "tok")
    batch = [{"number": 1, "title": "a"}, {"number": 2, "title": "b"},
             {"number": 3, "pull_request": {}}]  # PR dropped

    def fake_get(url, headers=None, params=None, timeout=None):
        return _FakeGetResp(batch if params["page"] == 1 else [])

    monkeypatch.setattr(bs.httpx, "get", fake_get)
    issues, ok, err = bs._fetch_open_issues()
    assert ok is True and err is None
    assert [i["number"] for i in issues] == [1, 2]


def test_fetch_open_issues_no_token_unknown(monkeypatch):
    monkeypatch.setattr(gh, "GITHUB_TOKEN", "")
    issues, ok, err = bs._fetch_open_issues()
    assert issues == [] and ok is False and "GITHUB_TOKEN" in err


def test_fetch_open_issues_rate_limit_unknown(monkeypatch):
    monkeypatch.setattr(gh, "GITHUB_TOKEN", "tok")

    def fake_get(url, headers=None, params=None, timeout=None):
        return _FakeGetResp([], raise_exc=RuntimeError("403 rate limit"))

    monkeypatch.setattr(bs.httpx, "get", fake_get)
    issues, ok, err = bs._fetch_open_issues()
    assert ok is False and "failed" in err


def test_fetch_open_issues_truncated_unknown(monkeypatch):
    monkeypatch.setattr(gh, "GITHUB_TOKEN", "tok")
    full = [{"number": n} for n in range(bs._PER_PAGE)]  # always a full page

    def fake_get(url, headers=None, params=None, timeout=None):
        return _FakeGetResp(full)

    monkeypatch.setattr(bs.httpx, "get", fake_get)
    issues, ok, err = bs._fetch_open_issues()
    assert ok is False and "truncated" in err
    assert len(issues) == bs._PER_PAGE * bs._OPEN_ISSUES_MAX_PAGES


# --------------------------------------------------------------------------
# Project GraphQL fetch — pagination beyond 1,000, closed filtering, dup cards
# --------------------------------------------------------------------------
class _FakePostResp:
    def __init__(self, d):
        self._d = d

    def raise_for_status(self):
        pass

    def json(self):
        return self._d


def _node(num, status, *, typename="Issue", state="OPEN"):
    return {
        "content": {"__typename": typename, "number": num, "state": state},
        "fieldValueByName": {"name": status},
    }


def _page(nodes, *, has_next, cursor=None):
    return {"data": {"node": {"items": {
        "pageInfo": {"hasNextPage": has_next, "endCursor": cursor},
        "nodes": nodes,
    }}}}


def test_fetch_project_items_paginates_beyond_1000(monkeypatch):
    monkeypatch.setattr(gh, "GITHUB_TOKEN", "tok")
    monkeypatch.setattr(gh, "PROJECT_ID", "PVT_x")
    # 1,012 open Project items across 11 pages (10 full + 1 partial).
    pages = []
    num = 1
    for p in range(10):
        nodes = [_node(num + i, "Ready") for i in range(100)]
        num += 100
        pages.append(_page(nodes, has_next=True, cursor=f"c{p}"))
    tail = [_node(num + i, "Ready") for i in range(12)]
    pages.append(_page(tail, has_next=False))
    state = {"i": 0}

    def fake_post(url, headers=None, json=None, timeout=None):
        d = pages[state["i"]]
        state["i"] += 1
        return _FakePostResp(d)

    monkeypatch.setattr(bs.httpx, "post", fake_post)
    proj = bs._fetch_project_items()
    assert proj["open_project_items"] == 1012
    assert len(proj["columns"]) == 1012
    assert proj["duplicate_cards"] == []


def test_fetch_project_items_filters_closed_and_prs(monkeypatch):
    monkeypatch.setattr(gh, "GITHUB_TOKEN", "tok")
    monkeypatch.setattr(gh, "PROJECT_ID", "PVT_x")
    nodes = [
        _node(1, "Inbox"),
        _node(2, "Done", state="CLOSED"),                 # closed → excluded
        _node(3, "Ready", typename="PullRequest"),        # PR → excluded
    ]
    monkeypatch.setattr(bs.httpx, "post",
                        lambda *a, **k: _FakePostResp(_page(nodes, has_next=False)))
    proj = bs._fetch_project_items()
    assert proj["project_numbers"] == {1}
    assert proj["open_project_items"] == 1


def test_fetch_project_items_detects_duplicate_cards(monkeypatch):
    monkeypatch.setattr(gh, "GITHUB_TOKEN", "tok")
    monkeypatch.setattr(gh, "PROJECT_ID", "PVT_x")
    nodes = [_node(7, "Inbox"), _node(7, "Ready"), _node(8, "Done")]
    monkeypatch.setattr(bs.httpx, "post",
                        lambda *a, **k: _FakePostResp(_page(nodes, has_next=False)))
    proj = bs._fetch_project_items()
    assert proj["duplicate_cards"] == [7]


def test_fetch_project_items_truncation_returns_none(monkeypatch):
    monkeypatch.setattr(gh, "GITHUB_TOKEN", "tok")
    monkeypatch.setattr(gh, "PROJECT_ID", "PVT_x")
    # Always hasNextPage=True → never terminates → truncated → None.
    monkeypatch.setattr(bs.httpx, "post",
                        lambda *a, **k: _FakePostResp(_page([_node(1, "Inbox")], has_next=True, cursor="c")))
    assert bs._fetch_project_items() is None


def test_fetch_project_items_failure_returns_none(monkeypatch):
    monkeypatch.setattr(gh, "GITHUB_TOKEN", "tok")
    monkeypatch.setattr(gh, "PROJECT_ID", "PVT_x")

    def boom(*a, **k):
        raise RuntimeError("graphql down")

    monkeypatch.setattr(bs.httpx, "post", boom)
    assert bs._fetch_project_items() is None


def test_fetch_project_items_graphql_errors_returns_none(monkeypatch):
    monkeypatch.setattr(gh, "GITHUB_TOKEN", "tok")
    monkeypatch.setattr(gh, "PROJECT_ID", "PVT_x")
    monkeypatch.setattr(bs.httpx, "post",
                        lambda *a, **k: _FakePostResp({"errors": [{"message": "bad"}]}))
    assert bs._fetch_project_items() is None


# Back-compat wrapper still returns the column map (or None).
def test_fetch_project_columns_wrapper(monkeypatch):
    monkeypatch.setattr(gh, "GITHUB_TOKEN", "tok")
    monkeypatch.setattr(gh, "PROJECT_ID", "PVT_x")
    nodes = [_node(1, "Inbox"), _node(2, "Ready")]
    monkeypatch.setattr(bs.httpx, "post",
                        lambda *a, **k: _FakePostResp(_page(nodes, has_next=False)))
    assert bs._fetch_project_columns() == {1: "Inbox", 2: "Ready"}


# --------------------------------------------------------------------------
# _fetch_board_state integration (fetch layer glued together)
# --------------------------------------------------------------------------
def test_fetch_board_state_joins_and_flags_duplicate_cards(monkeypatch):
    raw = [
        {"number": 1, "title": "a", "labels": [{"name": "alert-intake"}],
         "assignees": [{"login": "alice"}], "created_at": NOW.isoformat()},
        {"number": 2, "title": "b", "labels": ["area:infra"], "created_at": NOW.isoformat()},
    ]
    monkeypatch.setattr(bs, "_fetch_open_issues", lambda: (raw, True, None))
    monkeypatch.setattr(bs, "_fetch_project_items", lambda: {
        "columns": {1: "Inbox", 2: "Ready"},
        "project_numbers": {1, 2},
        "duplicate_cards": [2],
        "open_project_items": 2,
    })
    issues, board, errors = bs._fetch_board_state()
    assert board["columns_available"] is True
    assert board["project_numbers"] == {1, 2}
    assert issues[0]["column"] == "Inbox"
    assert issues[0]["assignees"] == ["alice"]
    assert any("Duplicate Project cards" in e["detail"] for e in errors)


def test_fetch_board_state_total_rest_failure_is_unknown(monkeypatch):
    monkeypatch.setattr(bs, "_fetch_open_issues", lambda: ([], False, "GITHUB_TOKEN unset"))
    issues, board, errors = bs._fetch_board_state()
    assert issues == []
    assert board["columns_available"] is False
    assert board["project_numbers"] is None
    assert errors


def test_fetch_board_state_project_failure_keeps_issues(monkeypatch):
    raw = [{"number": 1, "title": "a", "labels": [], "created_at": NOW.isoformat()}]
    monkeypatch.setattr(bs, "_fetch_open_issues", lambda: (raw, True, None))
    monkeypatch.setattr(bs, "_fetch_project_items", lambda: None)
    issues, board, errors = bs._fetch_board_state()
    assert len(issues) == 1
    assert board["columns_available"] is False
    assert board["project_numbers"] is None
    assert any("Project board read failed" in e["detail"] for e in errors)


# --------------------------------------------------------------------------
# End-to-end runner
# --------------------------------------------------------------------------
class TestRunBoardSentinel:
    """End-to-end runner with fetch + Redis monkeypatched (no network)."""

    def _run(self, monkeypatch, issues, *, columns_available=True,
             project_numbers="all", errors=None):
        import asyncio

        if project_numbers == "all":
            project_numbers = {i["number"] for i in issues}
        board = {
            "columns_available": columns_available,
            "project_numbers": project_numbers,
            "open_project_items": None if project_numbers is None else len(project_numbers),
        }
        monkeypatch.setattr(bs, "_fetch_board_state", lambda: (issues, board, errors or []))
        monkeypatch.setattr(bs, "_load_overrides", lambda: None)

        class FakeRedis:
            def setex(self, *a, **k):
                pass

        monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda *a, **k: FakeRedis())
        return asyncio.run(bs._run_board_sentinel(file_issues=False, now=NOW))

    def test_run_green(self, monkeypatch):
        issues = [_iss(10, labels=("alert-intake", "area:infra", "needs-agent"),
                       column="In Progress")]
        stats = self._run(monkeypatch, issues, columns_available=True)
        assert stats["verdict"] == "green"
        assert stats["offenders"] == []
        assert stats["filed"] is None  # detect-only
        assert stats["generated_at"] == NOW.isoformat()

    def test_run_red_aggregates_offenders(self, monkeypatch):
        fp = "deadbeef1234"
        issues = [
            _iss(10, labels=("alert-intake", "area:infra"),
                 body=_decl("flow-sentinel-fingerprint", fp), column="In Progress"),
            _iss(20, labels=("alert-intake", "area:infra"),
                 body=_decl("flow-sentinel-fingerprint", fp), column="In Progress"),
            _iss(30, labels=("alert-intake",), column="Inbox", age_hours=100),
        ]
        stats = self._run(monkeypatch, issues, columns_available=True)
        assert stats["verdict"] == "red"
        # offenders unions duplicate-issue lists + single-issue findings
        assert set(stats["offenders"]) >= {10, 20, 30}

    def test_run_unknown_on_fetch_error(self, monkeypatch):
        stats = self._run(monkeypatch, [], columns_available=False, project_numbers=None,
                          errors=[{"detail": "GITHUB_TOKEN unset"}])
        assert stats["verdict"] == "unknown"
