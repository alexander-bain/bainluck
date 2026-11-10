"""The rail's "Still RED" cadence (#12276): an unchanged finding at most once a
day, a changed one at once.

Measured Nov 7: #12144 received 96 comments in 29 hours, 95 of them the same
"Still RED: 1 adjudicated pairs regressed, …" line 10–45 minutes apart while
nothing changed; the one comment a reader needed was #39 of 96. Every GitHub and
Redis call here is faked.
"""

import json

import pytest

import app.tasks.bug_report_github as gh
import app.tasks.sentinel_filing as sf
from app.tasks.sentinel_filing import OpenIssuesResult

MARKER = "matching-reconciliation-fingerprint"
FP = "e6ec282d2e28"
DECL = f"`{MARKER}:{FP}`  (dedupe key — do not remove)"
T0 = 1_762_500_000.0


class FakeRedis:
    def __init__(self):
        self.kv = {}
        self.down = False

    def get(self, key):
        if self.down:
            raise ConnectionError("redis down")
        return self.kv.get(key)

    def set(self, key, value, ex=None, nx=False):
        if self.down:
            raise ConnectionError("redis down")
        if nx and key in self.kv:
            return False
        self.kv[key] = value
        return True


@pytest.fixture
def rail(monkeypatch):
    import app.tasks.redis_state as redis_state

    state = {"now": T0, "comments": [], "bodies": [], "created": [], "redis": FakeRedis()}
    monkeypatch.setenv("SENTINEL_RED_COMMENT_CADENCE", "on")
    monkeypatch.setattr(gh, "GITHUB_TOKEN", "test-token")
    monkeypatch.setattr(gh, "comment_on_issue", lambda n, body: state["comments"].append((n, body)))
    monkeypatch.setattr(gh, "update_issue_body", lambda n, body: state["bodies"].append((n, body)))
    monkeypatch.setattr(gh, "add_to_project_board", lambda node: None)

    def create(title, body, labels):
        state["created"].append(title)
        return 7000 + len(state["created"]), "NODE"

    monkeypatch.setattr(gh, "create_github_issue", create)
    monkeypatch.setattr(redis_state, "get_redis_client", lambda *a, **k: state["redis"])
    monkeypatch.setattr(sf, "_now", lambda: state["now"])
    monkeypatch.setattr(sf, "fetch_open_alert_issues", lambda: OpenIssuesResult(ok=True, issues=[]))
    return state


def _open(number=12144):
    return OpenIssuesResult(ok=True, issues=[{"number": number, "title": "t", "body": f"x\n{DECL}\n", "comments": 3}])


def _red(detail="1 adjudicated pairs regressed, 2 negative pairs", rows="row-a,row-b", snapshot=None):
    return sf.reconcile_issue(
        red=True,
        fingerprint=FP,
        marker_key=MARKER,
        title="Matching drift",
        body=f"body\n{DECL}\n{rows}",
        red_body=f"body\n{DECL}\n{rows}",
        red_comment=f"Still RED: {detail} (fingerprint `{FP}`).",
        open_issues=snapshot or _open(),
    )


def test_an_unchanged_finding_is_commented_once_and_then_held(rail):
    assert _red()["action"] == "commented"
    rail["now"] += 15 * 60
    held = _red()
    assert held["action"] == "comment_skipped_unchanged" and held["issue"] == 12144
    assert len(rail["comments"]) == 1


def test_the_body_refresh_still_runs_when_the_comment_is_held(rail):
    _red()
    rail["now"] += 15 * 60
    assert _red()["body_refresh"] == "refreshed"
    assert len(rail["bodies"]) == 2


def test_an_unchanged_finding_is_commented_again_after_a_day(rail):
    _red()
    rail["now"] += sf.RED_COMMENT_MIN_INTERVAL_S - sf.RED_COMMENT_DAILY_SLACK_S - 1
    assert _red()["action"] == "comment_skipped_unchanged"
    rail["now"] += 1
    again = _red()
    assert again["action"] == "commented" and again["comment_reason"] == "daily"
    assert len(rail["comments"]) == 2


def test_a_nightly_run_a_few_seconds_short_of_a_day_is_still_commented(rail):
    """A daily sentinel's runs land seconds either side of 24 h apart; a strict
    24 h would hold every other night's comment at random."""
    _red()
    rail["now"] += sf.RED_COMMENT_MIN_INTERVAL_S - 3
    assert _red()["comment_reason"] == "daily"


def test_the_matching_beat_comments_an_unchanged_finding_exactly_once_in_24_hours(rail):
    """The 15-minute beat #12144's 96 comments came from: one comment, then the
    95 cycles after it held, then the daily one at exactly 24 h."""
    _red()
    actions = []
    for _ in range(96):
        rail["now"] += 15 * 60
        actions.append(_red()["action"])
    assert actions[:95] == ["comment_skipped_unchanged"] * 95
    assert actions[95] == "commented"
    assert len(rail["comments"]) == 2


def test_a_changed_count_is_commented_on_the_run_that_sees_it(rail):
    _red()
    rail["now"] += 15 * 60
    changed = _red(detail="0 adjudicated pairs regressed, 0 negative pairs")
    assert changed["action"] == "commented" and changed["comment_reason"] == "changed"


def test_a_changed_row_set_is_a_change_even_with_the_same_line(rail):
    _red()
    rail["now"] += 15 * 60
    assert _red(rows="row-a,row-c")["comment_reason"] == "changed"


def test_unreadable_state_comments_as_before(rail):
    rail["redis"].down = True
    _red()
    rail["now"] += 15 * 60
    assert _red()["action"] == "commented"
    assert len(rail["comments"]) == 2


def test_a_new_canonical_issue_is_commented(rail):
    _red()
    rail["now"] += 15 * 60
    moved = _red(snapshot=_open(13000))
    assert moved["action"] == "commented" and moved["comment_reason"] == "new_issue"


def test_a_just_filed_issue_is_not_followed_by_an_identical_still_red(rail):
    filed = _red(snapshot=OpenIssuesResult(ok=True, issues=[]))
    assert filed["action"] == "filed"
    issue = filed["issue"]
    rail["now"] += 15 * 60
    held = _red(snapshot=_open(issue))
    assert held["action"] == "comment_skipped_unchanged"
    assert rail["comments"] == []


def test_the_switch_off_restores_a_comment_every_run(rail, monkeypatch):
    monkeypatch.setenv("SENTINEL_RED_COMMENT_CADENCE", "off")
    _red()
    rail["now"] += 15 * 60
    assert _red()["comment_reason"] == "cadence_off"
    assert len(rail["comments"]) == 2
    assert rail["redis"].kv == {}


def test_the_state_records_issue_digest_and_time(rail):
    _red()
    (value,) = rail["redis"].kv.values()
    state = json.loads(value)
    assert state == {
        "issue": 12144,
        "digest": sf.red_finding_digest(
            f"Still RED: 1 adjudicated pairs regressed, 2 negative pairs (fingerprint `{FP}`).",
            f"body\n{DECL}\nrow-a,row-b",
        ),
        "at": T0,
    }


def test_a_failed_comment_is_not_recorded_so_the_next_run_retries(rail, monkeypatch):
    def boom(n, body):
        raise RuntimeError("403")

    monkeypatch.setattr(gh, "comment_on_issue", boom)
    assert _red()["action"] == "comment_failed"
    assert rail["redis"].kv == {}
