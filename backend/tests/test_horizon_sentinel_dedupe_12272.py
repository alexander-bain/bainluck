"""The Horizon sentinel files one issue per fingerprint, however many nights (#12272).

On the night of Nov 6 it filed all eight open conditions a second time
(#12259–#12266): it deduped through GitHub's /search index, which is eventually
consistent, and every lookup came back empty. A lookup could also land on any
issue that merely quoted the fingerprint (four open issues matched one
fingerprint's search on Nov 7). It now files through the sentinel rail. Every
GitHub call here is faked; nothing leaves the test.
"""

import pytest

import app.tasks.bug_report_github as gh
import app.tasks.horizon_sentinel as hs
import app.tasks.sentinel_filing as sf
from app.tasks.sentinel_filing import OpenIssuesResult

EXHAUSTED = {
    "competition": "mlb-all-star-game",
    "severity": "p1",
    "last_edition_slug": "mlb-all-star-game-2026",
    "last_edition_end": "2026-07-14",
    "days_left": -116,
    "detail": "The calendar has no edition after 2026-07-14.",
}
NEEDS_PAGE = {
    "slug": "f1-abu-dhabi-2026",
    "name": "Abu Dhabi Grand Prix 2026",
    "phase": "needs_page",
    "severity": "p2",
    "start": "2026-12-04",
    "end": "2026-12-06",
    "days_to_start": 27,
    "archetype": "winner field",
    "concept_key": "f1-abu-dhabi-2026",
    "domain": "f1",
    "marquee": False,
    "date_confidence": "confirmed",
    "detail": "No page yet.",
}


def _issue(number, body, title="[Horizon] x"):
    return {"number": number, "title": title, "body": body, "comments": 0, "labels": [{"name": "alert-intake"}]}


def _exhaustion_issue(number):
    return _issue(number, hs.build_exhaustion_issue_body(EXHAUSTED))


@pytest.fixture
def github(monkeypatch):
    """A faked GitHub: ``created`` and ``commented`` record writes; the claim is won."""
    state = {"created": [], "commented": [], "boarded": [], "reads": 0, "fresh": OpenIssuesResult(ok=True, issues=[])}
    monkeypatch.setattr(gh, "GITHUB_TOKEN", "test-token")

    def fake_create(title, body, labels):
        state["created"].append({"title": title, "body": body, "labels": labels})
        return 9000 + len(state["created"]), f"NODE{len(state['created'])}"

    monkeypatch.setattr(gh, "create_github_issue", fake_create)
    monkeypatch.setattr(gh, "comment_on_issue", lambda n, body: state["commented"].append((n, body)))
    monkeypatch.setattr(gh, "add_to_project_board", lambda node: state["boarded"].append(node))
    monkeypatch.setattr(sf, "_claim_fingerprint", lambda marker, fp: "won")

    def fresh_read():
        state["reads"] += 1
        return state["fresh"]

    monkeypatch.setattr(sf, "fetch_open_alert_issues", fresh_read)
    return state


def test_a_second_night_comments_on_the_open_issue_and_files_nothing(github):
    snapshot = OpenIssuesResult(ok=True, issues=[_exhaustion_issue(12136)])
    result = hs.file_exhaustion_issue(EXHAUSTED, snapshot)
    assert result["action"] == "commented" and result["issue"] == 12136
    assert github["created"] == []
    ((issue, body),) = github["commented"]
    assert issue == 12136 and "mlb-all-star-game" in body


def test_an_unreadable_open_issue_list_files_nothing(github):
    # The Nov 6 failure class: "could not look" must never read as "absent".
    snapshot = OpenIssuesResult(ok=False, error="502 from GitHub")
    for result in (hs.file_exhaustion_issue(EXHAUSTED, snapshot), hs.file_horizon_issue(NEEDS_PAGE, snapshot)):
        assert result["action"] == "dedup_unknown_no_op"
    assert github["created"] == [] and github["commented"] == []


def test_a_quote_of_the_fingerprint_in_another_issue_is_not_the_alert(github):
    # #12272's own body quotes `4dfe6d2cfae1`; the old search matched it.
    fp = hs.exhaustion_fingerprint(EXHAUSTED["competition"])
    quoting = _issue(12272, f"each pair carrying the identical fingerprint (for example `{fp}` on both)")
    result = hs.file_exhaustion_issue(EXHAUSTED, OpenIssuesResult(ok=True, issues=[quoting]))
    assert result["action"] == "filed"
    assert github["commented"] == []
    ((created,),) = [github["created"]]
    assert f"`{hs.HORIZON_MARKER}:{fp}`" in created["body"]


def test_duplicates_already_open_take_the_lowest_number(github):
    # Three open issues declared mlb-all-star-game's fingerprint on Nov 7
    # (#2491, #12075, #12136): the comment goes to the oldest, and nothing is filed.
    snapshot = OpenIssuesResult(ok=True, issues=[_exhaustion_issue(n) for n in (12136, 2491, 12075)])
    result = hs.file_exhaustion_issue(EXHAUSTED, snapshot)
    assert result["issue"] == 2491 and github["created"] == []


def test_a_new_condition_is_filed_once_with_its_labels_and_board(github):
    result = hs.file_horizon_issue(NEEDS_PAGE, OpenIssuesResult(ok=True, issues=[]))
    assert result == {
        "slug": "f1-abu-dhabi-2026",
        "fingerprint": hs.horizon_fingerprint("f1-abu-dhabi-2026"),
        "action": "filed",
        "issue": 9001,
        "severity": "p2",
    }
    ((created,),) = [github["created"]]
    assert {"alert-intake", "needs-agent", "area:event-details", "priority:p2"} <= set(created["labels"])
    assert github["boarded"] == ["NODE1"]


def test_needs_page_and_exhaustion_fingerprints_never_collide(github):
    # An open needs-page issue for an edition does not absorb its competition's
    # exhaustion notice: separate namespaces, as before.
    page_issue = _issue(500, hs.build_horizon_issue_body({**NEEDS_PAGE, "slug": "mlb-all-star-game-2026"}))
    result = hs.file_exhaustion_issue(EXHAUSTED, OpenIssuesResult(ok=True, issues=[page_issue]))
    assert result["action"] == "filed"


def test_the_module_no_longer_dedupes_through_search():
    import inspect

    source = inspect.getsource(hs)
    assert "search/issues" not in source
    assert not hasattr(hs, "_find_open_issue_by_fingerprint")


async def test_a_run_reads_the_open_issue_list_once_and_comments(monkeypatch, github):
    # Both conditions already open: one snapshot for the run, two comments,
    # no re-read (re-reads happen only right before a create), nothing filed.
    open_now = OpenIssuesResult(
        ok=True,
        issues=[_exhaustion_issue(12136), _issue(12259, hs.build_horizon_issue_body(NEEDS_PAGE))],
    )
    github["fresh"] = open_now
    entry = {"slug": NEEDS_PAGE["slug"], "concept_key": NEEDS_PAGE["concept_key"], "name": NEEDS_PAGE["name"]}

    async def no_page(client, key):
        return False

    async def published(**kw):
        return {"durable": "ok", "volatile": "ok"}

    import app.services.durable_snapshots as ds

    monkeypatch.setattr(hs, "load_calendar", lambda: [entry])
    monkeypatch.setattr(hs, "horizon_phase", lambda e, today: "needs_page")
    monkeypatch.setattr(hs, "_check_page_exists", no_page)
    monkeypatch.setattr(hs, "classify_entry", lambda e, today, has_page: dict(NEEDS_PAGE))
    monkeypatch.setattr(hs, "competitions_running_out", lambda entries, today: [dict(EXHAUSTED)])
    monkeypatch.setattr(ds, "publish_sentinel_evidence", published)

    stats = await hs._run_horizon_sentinel(file_issues=True)
    assert [f["action"] for f in stats["filed"]] == ["commented", "commented"]
    assert github["reads"] == 1
    assert github["created"] == []
    assert sorted(n for n, _ in github["commented"]) == [12136, 12259]
