"""The rail's report path (#12231): one comment per period on a named issue, never a filing.

Fable, Nov 6, 9:28 PM: the grouping sentinel's report-only weeks post their
counts on #12221 through the sentinel rail, once per week, with "Redis claim
plus a marker line read back so a re-run or a manual run never posts twice,
never filing". Every GitHub call here is faked; nothing leaves the test.
"""

import pytest

import app.tasks.bug_report_github as gh
import app.tasks.sentinel_filing as sf

MARKER = "grouping-sentinel-report"
PERIOD = "2026-11-12"
LINE = sf.report_marker_line(MARKER, PERIOD)


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


@pytest.fixture
def rail(monkeypatch):
    """A faked GitHub: ``pages`` is what each comments page returns, ``posted``
    records every comment, and any create, close or body edit fails the test."""
    state = {"pages": [[]], "posted": [], "gets": [], "claim": "won"}
    monkeypatch.setattr(gh, "GITHUB_TOKEN", "test-token")

    def fake_get(url, headers=None, params=None, timeout=None):
        state["gets"].append((url, dict(params or {})))
        page = (params or {}).get("page", 1)
        pages = state["pages"]
        if isinstance(pages, Exception):
            raise pages
        return _Resp(pages[page - 1] if page - 1 < len(pages) else [])

    monkeypatch.setattr(sf.httpx, "get", fake_get)
    monkeypatch.setattr(gh, "comment_on_issue", lambda n, body: state["posted"].append((n, body)))
    monkeypatch.setattr(sf, "_claim_fingerprint", lambda marker, key: state["claim"])

    def forbidden(*a, **k):
        raise AssertionError("the report path must never create, close or edit an issue")

    monkeypatch.setattr(gh, "create_github_issue", forbidden)
    monkeypatch.setattr(gh, "close_issue", forbidden)
    monkeypatch.setattr(gh, "update_issue_body", forbidden)
    return state


def _post(body="**Grouping sentinel**\ncounts…", since=None):
    return sf.post_report(issue=12221, marker_key=MARKER, period_key=PERIOD, body=body, since=since)


def test_no_token_posts_nothing(monkeypatch, rail):
    monkeypatch.setattr(gh, "GITHUB_TOKEN", "")
    assert _post()["action"] == "skipped_no_token"
    assert rail["posted"] == [] and rail["gets"] == []


def test_first_run_of_a_period_posts_once_with_the_marker_line(rail):
    result = _post()
    assert result["action"] == "posted"
    ((issue, body),) = rail["posted"]
    assert issue == 12221
    assert body.rstrip().splitlines()[-1] == LINE


def test_a_second_run_finds_the_earlier_post_and_posts_nothing(rail):
    rail["pages"] = [[{"body": f"counts\n\n{LINE}\n", "html_url": "https://x/1"}]]
    result = _post()
    assert result == {**result, "action": "already_posted", "url": "https://x/1"}
    assert rail["posted"] == []


def test_a_quoted_marker_inside_a_sentence_is_not_a_post(rail):
    rail["pages"] = [[{"body": f"last week's report carried {LINE} at the end"}]]
    assert _post()["action"] == "posted"


def test_an_unreadable_comment_list_is_a_no_op_never_a_blind_post(rail):
    rail["pages"] = RuntimeError("502 from GitHub")
    result = _post()
    assert result["action"] == "read_unknown_no_op"
    assert "502" in result["error"]
    assert rail["posted"] == []


def test_a_truncated_comment_list_is_a_no_op(rail):
    full = [{"body": "unrelated"}] * sf._PER_PAGE
    rail["pages"] = [full] * sf._REPORT_COMMENT_MAX_PAGES
    assert _post()["action"] == "read_unknown_no_op"
    assert rail["posted"] == []


def test_a_lost_claim_posts_nothing(rail):
    rail["claim"] = "lost"
    assert _post()["action"] == "claim_lost"
    assert rail["posted"] == []


def test_the_claim_winner_rereads_and_yields_to_a_racing_post(monkeypatch, rail):
    reads = iter([[], [{"body": LINE, "html_url": "https://x/race"}]])

    def racing_get(url, headers=None, params=None, timeout=None):
        return _Resp(next(reads))

    monkeypatch.setattr(sf.httpx, "get", racing_get)
    result = _post()
    assert result["action"] == "already_posted" and result["url"] == "https://x/race"
    assert rail["posted"] == []


def test_a_failed_comment_is_reported_not_raised(monkeypatch, rail):
    def boom(n, body):
        raise RuntimeError("403")

    monkeypatch.setattr(gh, "comment_on_issue", boom)
    result = _post()
    assert result["action"] == "comment_failed" and "403" in result["error"]


def test_a_body_that_already_ends_with_the_marker_is_not_marked_twice(rail):
    _post(body=f"counts\n\n{LINE}\n")
    ((_, body),) = rail["posted"]
    assert body.count(LINE) == 1


def test_since_bounds_the_read_back_to_the_period(rail):
    _post(since="2026-11-12T12:00:00Z")
    assert all(params.get("since") == "2026-11-12T12:00:00Z" for _, params in rail["gets"])


def test_the_report_marker_never_reads_as_an_alert_declaration():
    # A report on #12221 must never be mistaken for owning an alert fingerprint.
    assert sf.declared_fingerprints(f"counts\n{LINE}\n") == set()


def test_with_redis_down_the_read_back_alone_stops_a_second_post(rail):
    # No claim means no re-read, so the first read of the issue's comments is
    # the only thing between a manual run and a duplicate post.
    rail["claim"] = "no_redis"
    rail["pages"] = [[{"body": f"counts\n\n{LINE}\n", "html_url": "https://x/1"}]]
    assert _post()["action"] == "already_posted"
    assert rail["posted"] == []


def test_with_redis_down_a_new_period_still_posts(rail):
    rail["claim"] = "no_redis"
    assert _post()["action"] == "posted"
