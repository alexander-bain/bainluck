"""#5324, second half — the authority says nobody has started, so the row stops saying LIVE.

`events.status` is a LATCH. `transition_event_statuses` promotes
`scheduled -> live` the moment `commence_time <= now` and NOTHING re-derives it,
so a start that slides leaves the row asserting `live` against a game nobody has
begun.

live/171 (`f74829566`, PR #5590) closed the half that is decidable from the row
alone — `live` with its OWN start still in the future — inside
`served_event_status`. ux/1198's own sample table says why that is only half:

    read    commence_time   does the row refute itself?
    19:04Z  19:05:00Z       yes — start ahead
    19:06Z  19:05:00Z       NO  — start has passed
    19:07Z  19:10:00Z       yes
    19:14Z  19:12:43Z       NO
    19:17Z  19:12:43Z       NO

Between slides the row is internally consistent and still wrong. Closing those
minutes needs a fact from OUTSIDE the row, and this is it: ESPN's own
`STATUS_SCHEDULED`.

═══ WHY NOT THE CHEAP RULE ═══

"live, nothing ever observed, started less than N minutes ago" was MEASURED and
ruled out (M-20260912-live171, production 23:37Z 2026-09-12). Twelve rows would
have been demoted at N>=25 and ALL TWELVE were genuinely being played — eleven
merely had `home_score IS NULL` because we hold no observation channel for their
sport. That is gotcha #53: absence of an observation read as an observation of
absence, and no N repairs it while whole sports observe nothing. Re-taken after
#5697 released (production 02:55Z 2026-09-13) the same set is 1 of 6 rows, and
that row is anchorless AFLW — a row this rule is silent on by construction.

═══ WHY `scheduled` AND NOT `state == "pre"` ═══

MEASURED against ESPN's own API, 02:52Z 2026-09-13, the 80-event NCAAF board:

    status_in_progress / state=in    17
    status_halftime    / state=in     2
    status_final       / state=post  59
    status_scheduled   / state=pre    2

`ESPNEvent.status` is derived from `status.type.NAME`, not `state`
(`espn_api.py:696`), and the two disagree in the direction that matters:
`STATUS_DELAYED` carries `state="in"` before a ball is bowled, which
`espn_terminal_state`'s own docstring records. So `state` is the wrong field to
read and `status_halftime` is a third thing again. Zero of the 80 games sat at
`STATUS_SCHEDULED` past their own listed start, so ESPN flips promptly and the
demotion signal does not fire on a board merely lagging a kickoff.

THE WIRING TESTS DRIVE `_process_live_sport`, NOT THE PREDICATE. CERT-2700 filed
`4971-FEED-ROUTE-GUARD-PINS-HERO-FIELDS` against exactly the habit of guarding a
pure helper and calling the feature tested; deleting the call site must turn one
of these red.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.services.espn_api import ESPNEvent, ESPNTeam
from app.tasks.espn_sync import _process_live_sport, espn_team_matches
from app.utils.espn_helpers import espn_scheduled_demotes_live, match_event_to_espn

SPORT = "americanfootball_ncaaf"

# Frozen literals are safe HERE and only here: the predicate takes no clock at
# all, and `_process_live_sport` is driven with its cutoffs passed in as
# arguments below, so nothing in this file is measured against the real clock.
# (Gotcha #44 — three suites aged out of their own windows on 2026-09-12.)
KICKOFF = datetime(2026, 9, 12, 23, 0, tzinfo=timezone.utc)
NOW = KICKOFF + timedelta(minutes=8)


# ════════════════════════════════════════════════════════════════════════
# THE POLICY, pure
# ════════════════════════════════════════════════════════════════════════


def test_the_authority_saying_scheduled_demotes_a_live_row():
    """The ship. ESPN says this game has not begun; we are serving it live."""
    assert espn_scheduled_demotes_live("live", "scheduled") is True


def test_a_real_score_of_ours_outranks_the_authoritys_denial():
    """21-14 on our board and ESPN says not-started: the anchor is wrong, so
    write NOTHING rather than blank a game in progress."""
    assert espn_scheduled_demotes_live(
        "live", "scheduled", home_score=21, away_score=14,
    ) is False


def test_one_side_scoring_is_enough_to_refuse():
    assert espn_scheduled_demotes_live(
        "live", "scheduled", home_score=7, away_score=0,
    ) is False
    assert espn_scheduled_demotes_live(
        "live", "scheduled", home_score=0, away_score=3,
    ) is False


def test_a_period_is_an_observation_and_refuses():
    assert espn_scheduled_demotes_live("live", "scheduled", period=2) is False


def test_a_game_clock_is_an_observation_and_refuses():
    assert espn_scheduled_demotes_live(
        "live", "scheduled", game_clock="4:32",
    ) is False


def test_nil_nil_is_NOT_an_observation_and_still_demotes():
    """live/182's rider 2, as a test. `COALESCE(home_score,0) = 0` maps ABSENT
    and ZERO onto one value and that erasure is what turned a 1-row finding into
    a 12-row one. A 0-0 with no clock is the ambiguous shape; the authority is
    the tiebreak on exactly it."""
    assert espn_scheduled_demotes_live(
        "live", "scheduled", home_score=0, away_score=0,
    ) is True


def test_an_absent_score_demotes():
    assert espn_scheduled_demotes_live(
        "live", "scheduled", home_score=None, away_score=None,
    ) is True


def test_the_authority_reporting_play_never_demotes():
    assert espn_scheduled_demotes_live("live", "in") is False


def test_delayed_is_ambiguous_so_it_writes_nothing():
    """ESPN publishes STATUS_DELAYED both before a start and mid-game, and it
    carries `state="in"` either way. Silence is the correct read."""
    assert espn_scheduled_demotes_live("live", "status_delayed") is False


def test_halftime_is_not_not_started():
    assert espn_scheduled_demotes_live("live", "status_halftime") is False


def test_a_final_never_demotes():
    assert espn_scheduled_demotes_live("live", "post") is False


@pytest.mark.parametrize("settled", ["completed", "closed", "suspended"])
def test_a_settled_row_is_a_different_class_and_is_left_alone(settled):
    """A settled row contradicted by `scheduled` is the cross-merge/fold case
    and belongs to `_is_bogus_future_settled`, which judges it on different
    evidence. Churning it here would rewrite history for no reader."""
    assert espn_scheduled_demotes_live(settled, "scheduled") is False


def test_a_row_already_scheduled_is_a_no_op():
    assert espn_scheduled_demotes_live("scheduled", "scheduled") is False


def test_an_unknown_authority_state_writes_nothing():
    """Gotcha #53 — an unrecognised value is not evidence of anything."""
    for unknown in ("", None, "status_postponed", "pre", "upcoming"):
        assert espn_scheduled_demotes_live("live", unknown) is False


def test_a_boolean_score_is_not_read_as_a_number():
    """`isinstance(True, int)` is True in Python. A bool in a score column is
    garbage, not an observation, and must not silently mean 1."""
    assert espn_scheduled_demotes_live(
        "live", "scheduled", home_score=True, away_score=False,
    ) is True


# ════════════════════════════════════════════════════════════════════════
# THE WIRING, driven through `_process_live_sport`
# ════════════════════════════════════════════════════════════════════════


def _team(name, short):
    return ESPNTeam(
        espn_id="t-" + short.lower().replace(" ", ""),
        name=name,
        abbreviation=short[:4].upper(),
        display_name=name,
        short_name=short,
        nickname=None,
        primary_color=None,
        secondary_color=None,
        logo_url=None,
        logo_url_dark=None,
        record=None,
    )


def _espn_event(espn_id, *, status, hs=None, aws=None, clock=None, period=None):
    return ESPNEvent(
        espn_id=espn_id,
        name="Fresno State Bulldogs at Nevada Wolf Pack",
        short_name="FRES @ NEV",
        date=KICKOFF,
        status=status,
        status_detail=None,
        period=period,
        clock=clock,
        home_team=_team("Nevada Wolf Pack", "Nevada"),
        away_team=_team("Fresno State Bulldogs", "Fresno State"),
        home_score=hs,
        away_score=aws,
        venue=None,
        broadcasts=[],
        home_win_probability=None,
    )


class _FakeSport:
    def __init__(self, key):
        self.key = key
        self.id = 1


class _FakeEvent:
    _next_id = 15306900

    def __init__(self, *, espn_id=None, status="live", home_score=None,
                 away_score=None, period=None, game_clock=None):
        self.id = _FakeEvent._next_id
        _FakeEvent._next_id += 1
        self.sport = _FakeSport(SPORT)
        self.sport_id = 1
        self.home_team_name = "Nevada Wolf Pack"
        self.away_team_name = "Fresno State Bulldogs"
        self.home_team_normalized = None
        self.away_team_normalized = None
        self.home_team_alt_names = None
        self.away_team_alt_names = None
        self.home_team_id = None
        self.away_team_id = None
        self.espn_id = espn_id
        self.commence_time = KICKOFF
        self.commence_time_source = None
        self.status = status
        self.home_score = home_score
        self.away_score = away_score
        self.period = period
        self.game_clock = game_clock
        self.broadcast_info = None
        self.completed_at = None
        self.llm_importance = None


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, events):
        self._queued = [_Result(events), _Result([])]
        self.added = []

    async def execute(self, *_a, **_k):
        if self._queued:
            return self._queued.pop(0)
        return _Result([])

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None


class _Recorder:
    async def upsert_team(self, session, name, espn_team, sport_id, cache, stats):
        return None

    async def register_identities(self, *a, **k):
        return None

    async def update_fields(self, session, event, ee, claimed, stats):
        # The real writer only ever WRITES a score ESPN actually holds; a
        # `scheduled` board entry carries None and must not blank ours.
        if ee.home_score is not None:
            event.home_score = ee.home_score
        if ee.away_score is not None:
            event.away_score = ee.away_score
        if ee.clock:
            event.game_clock = ee.clock
        return True

    async def write_win_prob(self, *a, **k):
        return False

    async def compute_stat_model(self, *a, **k):
        return False

    async def create_unmatched(self, session, our_events, espn_events, sport_key, stats):
        return None


def _run(events, board):
    """Drive one live pass. Returns stats; the events are mutated in place."""
    import asyncio

    rec = _Recorder()
    stats = {"events_synced": 0, "events_updated": 0, "errors": []}
    asyncio.run(
        _process_live_sport(
            _FakeSession(events), SPORT, board, stats,
            NOW - timedelta(hours=6), NOW - timedelta(hours=5),
            espn_team_matches, rec.upsert_team, rec.register_identities,
            match_event_to_espn, rec.update_fields, rec.write_win_prob,
            rec.compute_stat_model, rec.create_unmatched,
        )
    )
    return stats


def test_an_anchored_live_row_is_demoted_when_the_authority_says_scheduled():
    """THE SHIP, through the wiring. Delete the call site in
    `_process_live_sport` and this goes red."""
    ours = _FakeEvent(espn_id="401860883", status="live")
    stats = _run([ours], [_espn_event("401860883", status="scheduled")])

    assert ours.status == "scheduled"
    assert stats["live_demoted_by_authority"] == 1


def test_THE_CONTROL_the_same_pass_leaves_a_genuinely_live_game_alone():
    """Non-vacuity. The identical harness, the identical row, one field
    different — a demotion that fires on everything proves nothing."""
    ours = _FakeEvent(espn_id="401860883", status="live")
    stats = _run(
        [ours],
        [_espn_event("401860883", status="in", hs=0, aws=0, clock="10:27")],
    )

    assert ours.status == "live"
    assert stats.get("live_demoted_by_authority", 0) == 0


def test_a_NAME_matched_row_is_never_demoted():
    """Anchored rows only. A name match can fold onto the wrong sibling
    (gotcha #32 — the same two teams play again on Thursday) and a status write
    driven by a mis-matched board entry would blank a real game. Ruling 048's
    id-anchored correspondence is the bar for a claim about identity."""
    ours = _FakeEvent(espn_id=None, status="live")
    stats = _run([ours], [_espn_event("401860883", status="scheduled")])

    assert ours.status == "live"
    assert stats.get("live_demoted_by_authority", 0) == 0


def test_our_own_score_survives_the_pass_and_refuses_the_demotion():
    """The observation guard, reached through the wiring rather than asserted
    on the helper."""
    ours = _FakeEvent(espn_id="401860883", status="live", home_score=21,
                      away_score=14)
    stats = _run([ours], [_espn_event("401860883", status="scheduled")])

    assert ours.status == "live"
    assert ours.home_score == 21
    assert stats.get("live_demoted_by_authority", 0) == 0


def test_a_row_the_authority_never_mentions_is_untouched():
    """The anchorless-AFLW shape: ESPN has no entry for this game, so the pass
    is silent. This is the property that makes the rule safe for the sports we
    hold no channel for."""
    ours = _FakeEvent(espn_id="401860883", status="live")
    stats = _run([ours], [])

    assert ours.status == "live"
    assert stats.get("live_demoted_by_authority", 0) == 0
