"""#4854 — a price nobody has looked at since kickoff may not decide a live match.

THE OTHER TWO SILENCES CANNOT SEE THIS ONE. `count_admissible_speakers` (#5031)
catches a group holding nothing but Player Props. `admissible_speakers_are_all_settled`
(#5548) catches a winner market that has stopped being able to answer. Both are
reached from `_retire_unbacked_blend_source`, which only ever runs when the
reading is None — and this book's whole problem is that it resolves perfectly
well. It is the right kind of market, its outcomes refute nothing, it carries a
price strictly between 0 and 1, and that price is from before the whistle.

    Bournemouth 2-2 Brentford, LIVE at 78' (event 15297674), 2026-09-12 15:55Z:
      our page served Polymarket 40.5% stamped 15:46:41Z
      Gamma event 934157 the same minute: active, markets updated 15:42:50Z,
        `Will AFC Bournemouth win` = 0.215
      our outcomes for that market: last_updated 13:08:06Z — 52 minutes BEFORE
        the 14:00Z kickoff, condition ids matching Gamma's exactly

So the venue lists it, trades it and updates it every minute; we simply had not
read it since before the game started. The gate therefore lives in
`admissible_as_blend_speaker`, not beside the other two silences: gating
admission is what makes the reading None, after which #5031's existing
`count_admissible_speakers == 0` retirement clears the stored leg unchanged.

DECAY IS NOT ENOUGH. An honest stamp lets `_relative_staleness_multiplier`
demote the leg, and a demoted leg is still a leg — a weighted median is decided
by POSITION, not by weight, so a 10%-weight source still picks the published
number when it sits in the middle. Only removing it removes it.

THE GRACE IS THE WHOLE DESIGN PROBLEM and it is DERIVED, not chosen. The bare
predicate ("every price predates kickoff") is true for a couple of minutes at
EVERY kickoff, because the last healthy poll landed just before the whistle;
retiring on it would drop and re-add the leg at the start of every game, which
is exactly the twitch `count_admissible_speakers`' docstring forbids.
`test_grace_is_derived_from_the_polls_enforced_clock` pins the derivation to the
beat and the hard kill AS DECLARED IN THE TASK MODULE, so moving either reddens
here rather than silently widening the window.

Measured on production 2026-09-12 17:0xZ over `status='live'` events:

    polymarket   323 legs   134 with no observation since kickoff   134 past grace
    kalshi       477 legs   102 with no observation since kickoff    73 past grace

and a further 8 Polymarket legs sat 6 minutes past kickoff — inside the grace,
protected, and the reason the grace exists. Kalshi is deliberately not asked:
its primary is exempt before any clause runs, so a Kalshi group always keeps a
speaker and could never be retired by this; asking its fallbacks would only
change which Kalshi row speaks, in a population this queue did not measure.
"""

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.utils.live_blend import (
    UNOBSERVED_SINCE_KICKOFF_GRACE,
    UNOBSERVED_SINCE_KICKOFF_WINDOW_CLOSES,
    MarketOutcomes,
    admissible_as_blend_speaker,
    admissible_speakers,
    admissible_speakers_are_all_settled,
    admissible_speakers_are_unobserved_since_kickoff,
    compute_source_home_probability,
    count_admissible_speakers,
    speaker_unobserved_since_kickoff,
)


# The production specimen, by name, so a reader can find it at the venue.
EVENT_ID = 15297674
HOME = "AFC Bournemouth"
AWAY = "Brentford FC"
# The specimen's clock is anchored to the RUN, not to the calendar — and the
# clause under test is the reason.
#
# These were the literals above: KICKOFF 2026-09-12 14:00Z, frozen 13:08:06Z,
# observed 15:55Z. `speaker_unobserved_since_kickoff` is the one clause in
# `live_blend` that reads the wall clock, and it ABSTAINS once a kickoff is more
# than `UNOBSERVED_SINCE_KICKOFF_WINDOW_CLOSES` (12h) old. That abstention is
# deliberate, and the constant's own comment gives this exact reason:
#
#     "a fixed-date fixture replayed months later drifts arbitrarily far from
#      its own anchor; outside this window the gate abstains rather than acting
#      on a date it has no business trusting"
#
# So at 2026-09-13 02:00:00Z — twelve hours to the minute after the literal —
# the gate stopped applying, the frozen book became admissible again, and three
# arms below inverted on a tree nobody had touched (CI at 02:04Z, on a master
# whose own run was green). The fixture aged into the very abstention the code
# it tests documents. Gotcha #44, in the form `clock_sweep` cannot see: the
# anchor does not branch on the clock, it ages past it.
#
# Anchored to the run the specimen keeps its exact shape — frozen 51m54s before
# kickoff, observed at 78' on the match clock, which is 115 minutes of wall
# clock after kickoff once halftime and stoppage are counted — and "now" IS that
# observation. 115 minutes is far past GRACE and sits in the first sixth of the
# 12h window, where production measured the entire population (under 3.4h).
_OBSERVED_AT = datetime.now(timezone.utc)
KICKOFF = _OBSERVED_AT - timedelta(minutes=115)
FROZEN_AT = KICKOFF - timedelta(minutes=51, seconds=54)  # 52m pre-kickoff
AT_78_MINUTES = _OBSERVED_AT

GRACE = UNOBSERVED_SINCE_KICKOFF_GRACE


class _Market:
    def __init__(self, mid, name, *, source="polymarket", external_id=None):
        self.id = mid
        self.name = name
        self.source = source
        self.external_id = external_id


class _Outcome:
    def __init__(self, rank, name, probability, last_updated=None):
        self.rank = rank
        self.name = name
        self.current_probability = probability
        self.last_updated = last_updated


def _book(stamp, *, mid=60258512, source="polymarket", external_id=None):
    """The specimen's winner market — a live, two-sided, perfectly resolvable book."""
    return MarketOutcomes(
        market=_Market(
            mid, f"{HOME} vs. {AWAY}", source=source, external_id=external_id
        ),
        outcomes=[
            _Outcome(0, HOME, 0.215, stamp),
            _Outcome(1, AWAY, 0.785, stamp),
        ],
        event_commence_time=KICKOFF,
    )


# =============================================================================
# The specimen — and the proof that the OTHER TWO silences cannot see it
# =============================================================================


def test_the_specimens_clock_is_inside_the_window_the_gate_acts_in():
    """The precondition every default-clock arm below silently depends on.

    Three arms call the gate with no explicit `now`, so they read the real
    clock. They are assertions about the gate ACTING; outside
    `UNOBSERVED_SINCE_KICKOFF_WINDOW_CLOSES` the gate abstains by design and
    each one inverts. Nothing asserted that precondition, which is why the
    expiry at 02:00:00Z read as three product failures instead of as one
    fixture that had aged out.
    """
    elapsed = datetime.now(timezone.utc) - KICKOFF
    assert elapsed > GRACE, (
        f"the specimen must be past grace for the gate to bite; {elapsed} <= {GRACE}"
    )
    assert elapsed < UNOBSERVED_SINCE_KICKOFF_WINDOW_CLOSES, (
        f"the specimen has aged out of the window ({elapsed} >= "
        f"{UNOBSERVED_SINCE_KICKOFF_WINDOW_CLOSES}); the gate now abstains and "
        f"every default-clock arm below is asserting the opposite of its name"
    )
    # Not merely inside — inside with room, so a long suite cannot walk out of
    # the window mid-run the way an import-time anchor can.
    assert UNOBSERVED_SINCE_KICKOFF_WINDOW_CLOSES - elapsed > timedelta(hours=8)


def test_the_anchor_is_derived_from_the_run_not_typed_as_a_date():
    """Teeth for the guard above — teeth that do not dull after twelve hours.

    A typed-in date satisfies the window check for the twelve hours FOLLOWING
    whatever was typed, so a guard that only reads the window goes green on the
    machine of whoever wrote the literal and red for everyone else the next
    night. That is exactly the failure this file just had, so the window check
    alone cannot be the whole guard.

    Measured against the import stamp, not against a fresh `now`: this file is
    imported once and its arms run thousands of tests later, so a tolerance read
    off the wall clock at assert time is itself an ageing anchor. The first
    version of this guard was exactly that and failed in CI at 10m49s of drift.

    Both halves are needed and neither is vacuous. The second alone passes if
    `_OBSERVED_AT` is also typed; the first alone passes if `KICKOFF` is typed
    while `_OBSERVED_AT` stays live. Together they are false for any literal at
    any clock, so a restored date cannot survive one CI run.
    """
    since_import = datetime.now(timezone.utc) - _OBSERVED_AT
    assert timedelta(0) <= since_import < timedelta(hours=1), (
        f"_OBSERVED_AT is {since_import} from now, so it is not this run's "
        f"clock — no shard takes an hour. It has been typed as a date."
    )
    assert KICKOFF == _OBSERVED_AT - timedelta(minutes=115), (
        f"KICKOFF ({KICKOFF}) is not derived from _OBSERVED_AT "
        f"({_OBSERVED_AT}) — a typed-in date expires again at kickoff + "
        f"{UNOBSERVED_SINCE_KICKOFF_WINDOW_CLOSES}."
    )


def test_the_frozen_book_resolves_fine_which_is_why_the_old_arms_miss_it():
    """Both #5031's and #5548's predicates say "nothing to do" on this group."""
    group = [_book(FROZEN_AT)]

    # It is priced strictly between 0 and 1, so it is not a settled book...
    assert admissible_speakers_are_all_settled(group) is False
    # ...and with the observation clause withheld it has a speaker, so #5031's
    # counter would not have retired it either.
    assert len(admissible_speakers(group, apply_observation_gate=False)) == 1

    # And it really does produce a number — that is the defect, not a detail.
    # Modelled by the SAME book with no kickoff travelling, which is precisely
    # the state every caller was in before this change: same market, same frozen
    # outcomes, no evidence of when the game started.
    as_it_was = [
        MarketOutcomes(market=group[0].market, outcomes=group[0].outcomes)
    ]
    reading = compute_source_home_probability(as_it_was, HOME, AWAY)
    assert reading is not None
    assert reading.home_probability == pytest.approx(0.215)


def test_frozen_since_before_kickoff_may_not_speak():
    group = [_book(FROZEN_AT)]
    assert count_admissible_speakers(group) == 0
    assert compute_source_home_probability(group, HOME, AWAY) is None


def test_a_book_observed_after_kickoff_still_speaks_however_quiet():
    """Freshness is about being LOOKED AT, not about the price moving."""
    observed = KICKOFF + timedelta(seconds=30)
    group = [_book(observed)]
    assert count_admissible_speakers(group) == 1
    assert compute_source_home_probability(group, HOME, AWAY) is not None


# =============================================================================
# The grace — the twitch this must not cause
# =============================================================================


def test_grace_protects_the_first_minutes_of_every_kickoff():
    """The last healthy poll lands just before the whistle. That is not a defect."""
    just_before = KICKOFF - timedelta(seconds=90)
    inside = KICKOFF + GRACE - timedelta(seconds=1)
    assert (
        speaker_unobserved_since_kickoff(
            _Market(1, "x"), [_Outcome(0, HOME, 0.5, just_before)], KICKOFF, inside
        )
        is False
    )


def test_just_past_the_grace_it_fires():
    just_before = KICKOFF - timedelta(seconds=90)
    outside = KICKOFF + GRACE + timedelta(seconds=1)
    assert (
        speaker_unobserved_since_kickoff(
            _Market(1, "x"), [_Outcome(0, HOME, 0.5, just_before)], KICKOFF, outside
        )
        is True
    )


def test_the_production_specimen_is_well_past_the_grace():
    """78 minutes in, frozen 52 minutes before kickoff — not a boundary case."""
    assert AT_78_MINUTES - KICKOFF > GRACE
    assert (
        speaker_unobserved_since_kickoff(
            _Market(1, "x"), [_Outcome(0, HOME, 0.215, FROZEN_AT)], KICKOFF,
            AT_78_MINUTES,
        )
        is True
    )


def test_the_window_closes_so_this_never_eats_4024s_class():
    """An event still "live" half a day after kickoff is a status defect.

    latency/346 split the population measured on live pages: the rows over 24h
    old all carry a settlement flag and are #4024's wrong-fixture attachment,
    which has a different fix. Retiring their legs here would hide that defect
    instead of fixing it, so the window closes well before them.
    """
    long_past = KICKOFF + UNOBSERVED_SINCE_KICKOFF_WINDOW_CLOSES + timedelta(minutes=1)
    assert (
        speaker_unobserved_since_kickoff(
            _Market(1, "x"), [_Outcome(0, HOME, 0.5, FROZEN_AT)], KICKOFF, long_past
        )
        is False
    )
    # ...and just inside it, the gate is still live.
    still_inside = (
        KICKOFF + UNOBSERVED_SINCE_KICKOFF_WINDOW_CLOSES - timedelta(minutes=1)
    )
    assert (
        speaker_unobserved_since_kickoff(
            _Market(1, "x"), [_Outcome(0, HOME, 0.5, FROZEN_AT)], KICKOFF, still_inside
        )
        is True
    )


def test_the_window_costs_the_ship_nothing():
    """Every frozen leg measured on a live event sits in the window's first quarter.

    Production 2026-09-12 17:3xZ: the oldest is 3.4 hours past kickoff. A bound
    that excluded real rows would be a bug dressed as caution.
    """
    measured_oldest = timedelta(hours=3.4)
    assert UNOBSERVED_SINCE_KICKOFF_GRACE < measured_oldest
    assert measured_oldest < UNOBSERVED_SINCE_KICKOFF_WINDOW_CLOSES


def test_an_unstarted_game_is_never_touched():
    """#4028's rule governs before kickoff: stamp honestly, do not retire."""
    four_hours_early = KICKOFF - timedelta(hours=4)
    assert (
        speaker_unobserved_since_kickoff(
            _Market(1, "x"),
            [_Outcome(0, HOME, 0.5, KICKOFF - timedelta(hours=22))],
            KICKOFF,
            four_hours_early,
        )
        is False
    )


def test_grace_is_derived_from_the_polls_enforced_clock():
    """The bound is the OBSERVER's, and it is the enforced one, not a p95.

    Pinned against the numbers actually declared in `app/tasks/__init__.py` so
    that moving the beat or the hard kill reddens here instead of quietly
    widening the window. Two records of one capability must not disagree.
    """
    src = Path(__file__).resolve().parents[1] / "app" / "tasks" / "__init__.py"
    text = src.read_text()

    beat = re.search(
        r'"poll-live-prediction-markets":\s*\{.*?"schedule":\s*([0-9.]+)',
        text,
        re.S,
    )
    assert beat, "the live poll's beat entry moved — re-derive the grace"
    assert float(beat.group(1)) == 120.0

    hard_kill = re.search(r'"task_time_limit":\s*(\d+)', text)
    assert hard_kill, "the global hard task_time_limit moved — re-derive the grace"
    assert int(hard_kill.group(1)) == 300

    # The poll declares no override, so the global hard limit is its hard limit.
    decorator = re.search(
        r'@celery_app\.task\([^)]*name="app\.tasks\.poll_live_prediction_markets"[^)]*\)',
        text,
    )
    assert decorator, "the live poll task decorator moved"
    assert "time_limit" not in decorator.group(0)

    assert GRACE == timedelta(seconds=float(beat.group(1)) + int(hard_kill.group(1)))
    assert GRACE == timedelta(minutes=7)


# =============================================================================
# Abstentions — every one of them is "no evidence", never "fresh"
# =============================================================================


@pytest.mark.parametrize(
    "kickoff,outcomes,why",
    [
        (None, [_Outcome(0, HOME, 0.5, FROZEN_AT)], "caller does not know kickoff"),
        (KICKOFF, [], "book not fetched yet"),
        (KICKOFF, [_Outcome(0, HOME, 0.5, None)], "no readable observation stamp"),
        (KICKOFF, [_Outcome(0, HOME, 0.5, "not-a-datetime")], "unreadable stamp"),
    ],
)
def test_abstains_on_no_evidence(kickoff, outcomes, why):
    assert (
        speaker_unobserved_since_kickoff(
            _Market(1, "x"), outcomes, kickoff, AT_78_MINUTES
        )
        is False
    ), why


def test_newest_stamp_in_the_book_wins():
    """One lagging outcome is not evidence the book is unobserved."""
    outcomes = [
        _Outcome(0, HOME, 0.215, FROZEN_AT),
        _Outcome(1, AWAY, 0.785, KICKOFF + timedelta(minutes=1)),
    ]
    assert (
        speaker_unobserved_since_kickoff(
            _Market(1, "x"), outcomes, KICKOFF, AT_78_MINUTES
        )
        is False
    )


def test_a_group_without_the_kickoff_behaves_exactly_as_it_does_today():
    """`MarketOutcomes` built the old way acquires no new gate."""
    group = [
        MarketOutcomes(
            market=_Market(1, f"{HOME} vs. {AWAY}"),
            outcomes=[
                _Outcome(0, HOME, 0.215, FROZEN_AT),
                _Outcome(1, AWAY, 0.785, FROZEN_AT),
            ],
        )
    ]
    assert count_admissible_speakers(group) == 1
    assert compute_source_home_probability(group, HOME, AWAY) is not None


def test_naive_stamps_are_read_as_utc_not_refused():
    naive_kickoff = KICKOFF.replace(tzinfo=None)
    naive_frozen = FROZEN_AT.replace(tzinfo=None)
    assert (
        speaker_unobserved_since_kickoff(
            _Market(1, "x"),
            [_Outcome(0, HOME, 0.5, naive_frozen)],
            naive_kickoff,
            AT_78_MINUTES,
        )
        is True
    )


# =============================================================================
# The Kalshi delta is provably zero
# =============================================================================


def test_kalshi_primary_is_untouched():
    frozen = _book(FROZEN_AT, source="kalshi", external_id="KXEPLGAME-26SEP12BOUBRE")
    assert (
        admissible_as_blend_speaker(
            frozen.market,
            is_primary=True,
            outcomes=frozen.outcomes,
            event_commence_time=KICKOFF,
            now=AT_78_MINUTES,
        )
        is True
    )


def test_kalshi_fallback_is_not_asked_the_observation_question():
    """Refusing it would change which Kalshi row speaks, for no ship."""
    frozen = _book(FROZEN_AT, source="kalshi", external_id="KXEPLGAME-26SEP12BOUBRE")
    with_kickoff = admissible_as_blend_speaker(
        frozen.market,
        is_primary=False,
        outcomes=frozen.outcomes,
        event_commence_time=KICKOFF,
        now=AT_78_MINUTES,
    )
    without_kickoff = admissible_as_blend_speaker(
        frozen.market, is_primary=False, outcomes=frozen.outcomes
    )
    assert with_kickoff == without_kickoff


# =============================================================================
# The funnel must say WHICH silence — a new cause is not a spike in an old one
# =============================================================================


def test_cause_is_the_new_one_only_for_the_new_case():
    assert admissible_speakers_are_unobserved_since_kickoff(
        [_book(FROZEN_AT)], AT_78_MINUTES
    ) is True


def test_a_group_with_no_speaker_at_all_keeps_5031s_counter():
    """Player-Props-only: structural silence, not an observation failure."""
    props = MarketOutcomes(
        market=_Market(7, "Total Corners Over/Under 9.5"),
        outcomes=[_Outcome(0, "Over 9.5", 0.51, FROZEN_AT)],
        event_commence_time=KICKOFF,
    )
    assert count_admissible_speakers([props]) == 0
    assert (
        admissible_speakers_are_unobserved_since_kickoff([props], AT_78_MINUTES)
        is False
    )


def test_5548_settled_book_is_still_reported_as_settled():
    """A settled container is stamped AT settlement, which is after kickoff."""
    settled = MarketOutcomes(
        market=_Market(60258512, f"{HOME} vs. {AWAY}"),
        outcomes=[_Outcome(0, AWAY, 1.0, KICKOFF + timedelta(hours=2))],
        event_commence_time=KICKOFF,
    )
    assert admissible_speakers_are_all_settled([settled]) is True
    assert (
        admissible_speakers_are_unobserved_since_kickoff([settled], AT_78_MINUTES)
        is False
    )


# =============================================================================
# A contributor is gated like a speaker (CERT-2646)
# =============================================================================


def test_devig_will_not_average_a_live_price_with_a_pre_kickoff_one():
    fresh = MarketOutcomes(
        market=_Market(1, f"{HOME} vs. {AWAY}"),
        outcomes=[
            _Outcome(0, HOME, 0.40, KICKOFF + timedelta(minutes=70)),
            _Outcome(1, AWAY, 0.60, KICKOFF + timedelta(minutes=70)),
        ],
        event_commence_time=KICKOFF,
    )
    frozen_sibling = MarketOutcomes(
        market=_Market(2, f"{AWAY} vs. {HOME}"),
        outcomes=[
            _Outcome(0, AWAY, 0.90, FROZEN_AT),
            _Outcome(1, HOME, 0.10, FROZEN_AT),
        ],
        event_commence_time=KICKOFF,
    )
    reading = compute_source_home_probability([fresh, frozen_sibling], HOME, AWAY)
    assert reading is not None
    # The frozen sibling contributed nothing — the number is the live book's.
    assert reading.home_probability == pytest.approx(0.40)


# =============================================================================
# The FOURTH WRITER must not put back what the matcher retired
# =============================================================================
#
# `/api/admin/matching/backfill-wps` writes exactly where the key is ABSENT,
# which is precisely the state `_retire_unbacked_blend_source` leaves behind.
# #5273 CU-1 clause (1) put it behind `admissible_as_blend_speaker`; without the
# event's kickoff travelling it would abstain from THIS clause and re-add a leg
# the matcher had just cleared. Asserted behaviourally — a source-scan for the
# keyword would stay green if the value passed were always None.


def _admin_event(commence_time):
    from types import SimpleNamespace

    return SimpleNamespace(
        id=15307884,
        home_team_name=HOME,
        away_team_name=AWAY,
        win_probability_sources={},
        commence_time=commence_time,
    )


def _admin_market():
    from types import SimpleNamespace

    return SimpleNamespace(
        id=60725992,
        name=f"{HOME} vs. {AWAY}",
        source="polymarket",
        external_id="0x60725992",
        outcomes=[
            SimpleNamespace(name=HOME, current_probability=0.215, rank=0,
                            last_updated=FROZEN_AT),
            SimpleNamespace(name=AWAY, current_probability=0.785, rank=1,
                            last_updated=FROZEN_AT),
        ],
    )


async def _run_backfill(monkeypatch, event):
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from sqlalchemy.sql.dml import Update

    from app.routes.admin_matching import backfill_win_probability_sources

    class _FakeDb:
        def __init__(self, rows):
            self._rows = rows
            self.updates = []

        async def execute(self, stmt):
            if isinstance(stmt, Update):
                self.updates.append(stmt)
                return MagicMock()
            result = MagicMock()
            result.unique.return_value.all.return_value = self._rows
            return result

        async def commit(self):
            return None

    monkeypatch.setenv("ADMIN_TOKEN", "test-secret")
    db = _FakeDb([(_admin_market(), event)])
    stats = await backfill_win_probability_sources(
        request=SimpleNamespace(headers={"authorization": "Bearer test-secret"}),
        secret=None,
        limit=500,
        event_id=None,
        db=db,
    )
    return stats, db


@pytest.mark.asyncio
async def test_admin_backfill_will_not_re_add_a_leg_frozen_since_kickoff(monkeypatch):
    stats, db = await _run_backfill(monkeypatch, _admin_event(KICKOFF))
    assert stats["refused_inadmissible"] == 1
    assert db.updates == []


@pytest.mark.asyncio
async def test_admin_backfill_still_writes_a_book_observed_since_kickoff(monkeypatch):
    """The gate must not swallow the endpoint's legitimate writes."""
    long_ago = datetime(2020, 1, 1, tzinfo=timezone.utc)
    stats, db = await _run_backfill(monkeypatch, _admin_event(long_ago))
    assert stats["refused_inadmissible"] == 0
    assert db.updates, "a book observed after kickoff must still be written"
