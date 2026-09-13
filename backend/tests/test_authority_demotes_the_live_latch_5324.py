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

import contextlib
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

import app.tasks.espn_sync as espn_sync_mod
from app.services.espn_api import ESPNEvent, ESPNTeam
from app.tasks.espn_sync import _process_live_sport, espn_team_matches
from app.utils.espn_helpers import (
    AUTHORITY_NOT_STARTED_TTL,
    ESPN_NOT_STARTED_KEY,
    authority_not_started_holds,
    espn_scheduled_demotes_live,
    espn_scheduled_marks_not_started,
    match_event_to_espn,
    play_evidence,
)

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
        # CERT-2777's repair rides the JSONB mirror, so the fake has to carry
        # the column or the wiring tests pass by never reaching the write.
        self.win_probability_sources = None


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


# ═══════════════════════════════════════════════════════════════════════════
# CERT-2777's REQUIRED REPAIR: THE DEMOTION HAS TO SURVIVE THE OTHER TASK
# ═══════════════════════════════════════════════════════════════════════════
#
# Everything above drives ONE task. The BLOCK was that the ship is spent across
# TWO: `_process_live_sport` writes `scheduled`, and sixty seconds later
# `_transition_event_statuses_impl` selects `scheduled AND commence_time <= now`
# and promotes the same row straight back to `live`. Both beats are 60s on the
# realtime queue, so a reader sees the demotion for at most one minute and the
# ship is inert.
#
# So these run the two REAL tasks back to back, in production order, over one
# row. The harness for the second is the one
# `test_the_shadow_anchor_repair_survives_both_lifecycle_tasks_4075.py` built
# for the same reason — a predicate returning the right answer into a loop that
# does not ask it.


class _TransitionSession:
    """The selects `_transition_event_statuses_impl` issues, in order.

    Index 0 is the `scheduled -> live` pool — the one this repair is about.
    Every later select is empty so nothing else in the task moves, and the
    assertions below can only be about the promotion arm.
    """

    def __init__(self, scheduled):
        self._selects = [scheduled, [], [], [], []]

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "MAX(x.captured_at)" in sql:
            return type("R", (), {"all": lambda _s: []})()
        if sql.startswith("UPDATE"):
            return None
        rows = self._selects.pop(0) if self._selects else []
        return type(
            "R", (), {"scalars": lambda _s: type("S", (), {"all": lambda _x: rows})()}
        )()

    async def commit(self):
        return None


def _run_transition(scheduled, now=NOW):
    """Drive the REAL `_transition_event_statuses_impl` over these rows."""
    import asyncio

    session = _TransitionSession(scheduled)

    @contextlib.asynccontextmanager
    async def _fake_session():
        yield session

    class _FrozenNow(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    async def _go():
        with patch("app.tasks.base.get_task_session", _fake_session), patch.object(
            espn_sync_mod, "datetime", _FrozenNow
        ):
            return await espn_sync_mod._transition_event_statuses_impl()

    return asyncio.run(_go())


def _run_frozen(events, board, now=NOW):
    """`_run`, with the module clock frozen so the stamp it writes is `now`."""

    class _FrozenNow(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    with patch.object(espn_sync_mod, "datetime", _FrozenNow):
        return _run(events, board)


def test_authority_demotion_survives_transition_cycle_5324():
    """THE REPAIR, through both real tasks in production order.

    Revert either half — the stamp in `_process_live_sport` or the hold in the
    promotion loop — and the row comes back `live`, which is precisely the
    production behaviour CERT-2777 measured.
    """
    ours = _FakeEvent(espn_id="401860883", status="live")

    demote_stats = _run_frozen([ours], [_espn_event("401860883", status="scheduled")])
    assert ours.status == "scheduled"
    assert demote_stats["live_demoted_by_authority"] == 1
    # The fact is ON THE ROW, not only in the status — the status alone is what
    # did not survive.
    assert ESPN_NOT_STARTED_KEY in (ours.win_probability_sources or {})

    promote_stats = _run_transition([ours], now=NOW + timedelta(seconds=60))

    assert ours.status == "scheduled", "the clock re-promoted the demoted row"
    assert promote_stats["held_authority_not_started"] == 1
    assert promote_stats["scheduled_to_live"] == 0


def test_THE_CONTROL_positive_play_is_promoted_through_the_same_cycle():
    """Non-vacuity, and the "until positive play supersedes it" half.

    The identical two-task harness over a row carrying the SAME marker plus a
    real score. A hold that fires on everything would freeze every scheduled
    row on the site, so this must promote.
    """
    ours = _FakeEvent(espn_id="401860883", status="scheduled",
                      home_score=21, away_score=14)
    ours.win_probability_sources = {ESPN_NOT_STARTED_KEY: NOW.isoformat()}

    stats = _run_transition([ours], now=NOW + timedelta(seconds=60))

    assert ours.status == "live"
    assert stats["scheduled_to_live"] == 1
    assert stats["held_authority_not_started"] == 0


def test_THE_STRAWMAN_without_the_marker_the_clock_re_promotes():
    """The defect itself, pinned.

    The same row, the same cycle, the marker absent — the promoter takes it
    back to `live`. This is what the shipped code did to EVERY demoted row, and
    it is why a single-task band passed while the ship was inert. If this ever
    goes green with the marker present, the hold has stopped working.
    """
    ours = _FakeEvent(espn_id="401860883", status="scheduled")
    assert ours.win_probability_sources is None

    stats = _run_transition([ours], now=NOW + timedelta(seconds=60))

    assert ours.status == "live"
    assert stats["scheduled_to_live"] == 1


def test_an_anchored_pass_that_reports_play_clears_the_marker():
    """The hold ends on EVIDENCE, not on a timeout.

    A row still carrying the marker, and an ESPN pass that reports the game in
    progress: the marker goes, so the very next transition cycle promotes
    normally instead of waiting out the TTL.
    """
    ours = _FakeEvent(espn_id="401860883", status="scheduled")
    ours.win_probability_sources = {ESPN_NOT_STARTED_KEY: NOW.isoformat()}

    stats = _run_frozen(
        [ours],
        [_espn_event("401860883", status="in", hs=7, aws=0, clock="9:14")],
    )

    assert ESPN_NOT_STARTED_KEY not in (ours.win_probability_sources or {})
    assert stats.get("authority_not_started_cleared", 0) == 1

    _run_transition([ours], now=NOW + timedelta(seconds=60))
    assert ours.status == "live"


def test_an_ordinary_live_pass_does_not_write_a_clearing_update():
    """The clearing arm must not add an UPDATE to every anchored pass on the
    site. No marker, nothing to clear, no write, no counter."""
    ours = _FakeEvent(espn_id="401860883", status="live")

    stats = _run_frozen(
        [ours], [_espn_event("401860883", status="in", hs=14, aws=7, clock="2:02")]
    )

    assert stats.get("authority_not_started_cleared", 0) == 0


def test_the_hold_expires_so_a_dead_poller_cannot_freeze_a_row():
    """The TTL is the backstop for ESPN going dark, not a second policy.

    One second past it, the clock wins again and the row promotes normally.
    """
    ours = _FakeEvent(espn_id="401860883", status="scheduled")
    stale = NOW - AUTHORITY_NOT_STARTED_TTL - timedelta(seconds=1)
    ours.win_probability_sources = {ESPN_NOT_STARTED_KEY: stale.isoformat()}

    stats = _run_transition([ours], now=NOW)

    assert ours.status == "live"
    assert stats["scheduled_to_live"] == 1
    assert stats["held_authority_not_started"] == 0


def test_the_hold_still_holds_one_second_INSIDE_the_ttl():
    """The other side of the same boundary — without this the test above is
    satisfied by a hold that never holds at all."""
    ours = _FakeEvent(espn_id="401860883", status="scheduled")
    fresh = NOW - AUTHORITY_NOT_STARTED_TTL + timedelta(seconds=1)
    ours.win_probability_sources = {ESPN_NOT_STARTED_KEY: fresh.isoformat()}

    stats = _run_transition([ours], now=NOW)

    assert ours.status == "scheduled"
    assert stats["held_authority_not_started"] == 1


def test_the_ttl_is_derived_from_the_beat_that_refreshes_it():
    """Two records of one capability drift, so the gap is asserted.

    The marker is re-written by `sync-espn-live`; if that beat ever slows past
    the TTL a single missed pass releases the hold and the ship flickers again.
    """
    from app.tasks import celery_app

    beat = celery_app.conf.beat_schedule["sync-espn-live"]["schedule"]
    assert AUTHORITY_NOT_STARTED_TTL.total_seconds() >= beat * 10, (
        "the hold must outlive several missed ESPN passes"
    )


@pytest.mark.parametrize("junk", [None, "", "not-a-timestamp", 12345, {"a": 1}, []])
def test_an_unreadable_marker_fails_OPEN(junk):
    """A hold is a REFUSAL to act on the clock, so an unreadable marker must
    never strand a row out of `live`. Fail open, every time."""
    assert authority_not_started_holds({ESPN_NOT_STARTED_KEY: junk}, NOW) is False


def test_a_marker_from_the_future_is_a_clock_fault_not_a_statement():
    assert authority_not_started_holds(
        {ESPN_NOT_STARTED_KEY: (NOW + timedelta(hours=1)).isoformat()}, NOW
    ) is False


def test_a_naive_stamp_is_read_as_utc_rather_than_crashing():
    """Nothing writes one today, but a JSONB value outlives the writer that
    made it and a `TypeError` here would take the whole transition task down."""
    naive = (NOW - timedelta(minutes=1)).replace(tzinfo=None)
    assert authority_not_started_holds({ESPN_NOT_STARTED_KEY: naive.isoformat()}, NOW) is True


def test_a_period_arriving_on_a_HELD_row_releases_it_through_the_promoter():
    """M3's survivor: the predicate's period guard had no test at all.

    A demoted row that later gains a period is being played by some source
    other than the one that demoted it — StatPal, MLB, a score write — and the
    clock must be allowed to promote it again without waiting for either the
    clearing pass or the TTL. Driven through the real promoter, not asserted on
    the helper, because the helper is only as good as the loop that calls it.
    """
    ours = _FakeEvent(espn_id="401860883", status="scheduled", period=2)
    ours.win_probability_sources = {ESPN_NOT_STARTED_KEY: NOW.isoformat()}

    stats = _run_transition([ours], now=NOW + timedelta(seconds=60))

    assert ours.status == "live"
    assert stats["scheduled_to_live"] == 1
    assert stats["held_authority_not_started"] == 0


def test_a_game_clock_arriving_on_a_HELD_row_releases_it_through_the_promoter():
    """The other half of the same guard. A clock is running; nobody may hold
    this row out of `live` on a minutes-old statement that it had not begun."""
    ours = _FakeEvent(espn_id="401860883", status="scheduled", game_clock="11:48")
    ours.win_probability_sources = {ESPN_NOT_STARTED_KEY: NOW.isoformat()}

    stats = _run_transition([ours], now=NOW + timedelta(seconds=60))

    assert ours.status == "live"
    assert stats["scheduled_to_live"] == 1
    assert stats["held_authority_not_started"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# CERT-2782's REQUIRED REPAIR: THE SECOND `scheduled` PASS MUST NOT CLEAR
# ═══════════════════════════════════════════════════════════════════════════
#
# The first repair held for exactly one cycle. `espn_scheduled_demotes_live` is
# False once the row is already `scheduled` — there is nothing left to demote —
# and the clearing arm read that as "the authority has stopped saying it", so
# the SECOND consecutive `scheduled` pass deleted the marker the first one wrote
# and the next transition restored LIVE. Same flicker, period two passes.
#
# `espn_scheduled_marks_not_started` now answers the marker's own question, and
# clearing requires positive play rather than the mere absence of a demotion.


def test_repeated_authority_scheduled_pass_retains_hold_5324():
    """THE REPAIR: two ESPN passes and two transition passes, in production
    order, exactly the cycle CERT-2782 reproduced.

    The grader's sequence was
    `scheduled/marker=true -> held -> marker=false/cleared -> live`.
    It must now be `scheduled/marker -> held -> scheduled/marker -> held`.
    """
    ours = _FakeEvent(espn_id="401860883", status="live")
    board = [_espn_event("401860883", status="scheduled")]

    # Pass 1: demote and stamp.
    s1 = _run_frozen([ours], board, now=NOW)
    assert ours.status == "scheduled"
    assert s1["live_demoted_by_authority"] == 1
    first_stamp = ours.win_probability_sources[ESPN_NOT_STARTED_KEY]

    # Transition 1: held.
    t1 = _run_transition([ours], now=NOW + timedelta(seconds=60))
    assert ours.status == "scheduled"
    assert t1["held_authority_not_started"] == 1

    # Pass 2 — THE ONE THAT USED TO WIPE IT. Nothing to demote; the authority is
    # still saying not started, so the marker is refreshed, never cleared.
    later = NOW + timedelta(seconds=120)
    s2 = _run_frozen([ours], board, now=later)
    assert ESPN_NOT_STARTED_KEY in (ours.win_probability_sources or {})
    assert s2.get("authority_not_started_cleared", 0) == 0
    assert s2.get("authority_not_started_refreshed", 0) == 1
    assert s2.get("live_demoted_by_authority", 0) == 0
    assert ours.win_probability_sources[ESPN_NOT_STARTED_KEY] != first_stamp, (
        "the marker must be REFRESHED, or the hold ages out while ESPN is "
        "still saying the game has not begun"
    )

    # Transition 2: still held. This is the assertion that was exit 1.
    t2 = _run_transition([ours], now=later + timedelta(seconds=60))
    assert ours.status == "scheduled", "the second cycle restored LIVE"
    assert t2["held_authority_not_started"] == 1
    assert t2["scheduled_to_live"] == 0


def test_the_hold_outlives_its_own_TTL_while_the_authority_keeps_saying_it():
    """The refresh is not cosmetic: a start that slides past the TTL must stay
    demoted, because ESPN is still reporting it has not begun every 60s."""
    ours = _FakeEvent(espn_id="401860883", status="live")
    board = [_espn_event("401860883", status="scheduled")]

    _run_frozen([ours], board, now=NOW)
    # Well past the TTL, but re-stamped on the way there.
    far = NOW + AUTHORITY_NOT_STARTED_TTL + timedelta(minutes=30)
    _run_frozen([ours], board, now=far)

    stats = _run_transition([ours], now=far + timedelta(seconds=60))

    assert ours.status == "scheduled"
    assert stats["held_authority_not_started"] == 1


def test_an_ambiguous_state_does_not_retract_the_marker():
    """`status_delayed` is published before a start AND mid-game. It stamps
    nothing and — the half CERT-2782 caught — it must clear nothing either.
    Silence retracts no fact."""
    ours = _FakeEvent(espn_id="401860883", status="live")
    _run_frozen([ours], [_espn_event("401860883", status="scheduled")], now=NOW)
    assert ESPN_NOT_STARTED_KEY in ours.win_probability_sources

    stats = _run_frozen(
        [ours], [_espn_event("401860883", status="status_delayed")],
        now=NOW + timedelta(seconds=120),
    )

    assert ESPN_NOT_STARTED_KEY in (ours.win_probability_sources or {})
    assert stats.get("authority_not_started_cleared", 0) == 0


def test_play_ARRIVING_is_what_clears_the_marker():
    """The only retraction there is. A score lands, so the claim that the game
    has not begun is false and the marker goes."""
    ours = _FakeEvent(espn_id="401860883", status="live")
    _run_frozen([ours], [_espn_event("401860883", status="scheduled")], now=NOW)
    assert ESPN_NOT_STARTED_KEY in ours.win_probability_sources

    stats = _run_frozen(
        [ours], [_espn_event("401860883", status="in", hs=7, aws=3, clock="4:01")],
        now=NOW + timedelta(seconds=120),
    )

    assert ESPN_NOT_STARTED_KEY not in (ours.win_probability_sources or {})
    assert stats["authority_not_started_cleared"] == 1

    _run_transition([ours], now=NOW + timedelta(seconds=180))
    assert ours.status == "live"


# ── `play_evidence`, the one definition the four sites share ────────────────


def test_the_marker_question_accepts_an_already_scheduled_row():
    """The whole difference from the demotion predicate, stated directly."""
    assert espn_scheduled_marks_not_started("scheduled", "scheduled") is True
    assert espn_scheduled_demotes_live("scheduled", "scheduled") is False


def test_the_marker_question_refuses_a_settled_row():
    for settled in ("completed", "closed", "suspended"):
        assert espn_scheduled_marks_not_started(settled, "scheduled") is False


def test_the_marker_question_refuses_play_evidence():
    assert espn_scheduled_marks_not_started(
        "scheduled", "scheduled", home_score=21, away_score=14,
    ) is False
    assert espn_scheduled_marks_not_started(
        "scheduled", "scheduled", period=3,
    ) is False
    assert espn_scheduled_marks_not_started(
        "scheduled", "scheduled", game_clock="0:42",
    ) is False


@pytest.mark.parametrize("espn_status", ["in", "post", "status_halftime",
                                         "status_delayed", "", None])
def test_only_scheduled_marks_not_started(espn_status):
    assert espn_scheduled_marks_not_started("live", espn_status) is False


def test_play_evidence_is_the_shared_definition():
    """If these four ever disagree the row ping-pongs between two tasks, which
    is the defect class twice over. Pinned as one question."""
    assert play_evidence() is False
    assert play_evidence(home_score=0, away_score=0) is False
    assert play_evidence(home_score=True, away_score=False) is False
    assert play_evidence(home_score=1) is True
    assert play_evidence(away_score=2) is True
    assert play_evidence(period=1) is True
    assert play_evidence(game_clock="12:00") is True
