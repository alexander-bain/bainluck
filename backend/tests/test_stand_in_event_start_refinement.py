"""#3544: the tennis EVENT page stops advertising midnight.

## the half #3488 could not reach

`#3488` (CERT-2075) made the MARKET carry the venue's published hour. The cert
bus blocked it on exactly the right ground: **the user does not read the
market.** `/events/15305789` renders `events.commence_time`, and that column
was — and without this change stays — a midnight stand-in.

Measured on production 2026-09-06 13:40Z, the public payload itself:

    GET /api/events/15305789  ->  "commence_time": "2026-09-07T00:00:00+00:00"

for Zverev vs Darderi, which the venue times at `2026-09-07T18:00:00Z`. The
page read **"Sep 6, 2026 · 8:00 PM EDT · Starts in 11h 27m"**. That payload is
the rendered consumer the BLOCK asked to be identified, and it is this column.

## why nothing already in the tree would ever fix those rows

Both doors are shut, and each is shut for a different reason:

1. **The auto-create path never runs again.** `find_or_create_event` is offered
   a Kalshi claim only from `_create_event_from_prediction_market`, which
   `_try_link_market` reaches only for an **unlinked** market (gotcha #15 — if
   `event_id` is set, trust it). All 185 of these events already hold their
   market. Measured: `185` tennis events at `commence_time_source='kalshi_ticker'`
   with an open Kalshi market, production 2026-09-06.

2. **The authority rule refuses anyway**, so loosening door 1 would not help:

       commence_time_write_authorized('kalshi_ticker', 'kalshi')
         -> (False, 'priority: kalshi(0) does not outrank kalshi_ticker(0)')

   Both rank 0 in `_SOURCE_PRIORITY` and a tie loses. The q066b
   `same_record_revision` clause — written for precisely "one provider's row at
   two points in time" — misses too, because it tests source STRINGS for
   equality and Kalshi writes itself under two names (`kalshi_ticker` is
   Kalshi's own stamp). Only `odds_api`/`espn` outrank, and tennis has no ESPN
   anchor. The stand-in is permanent **by construction**, not by accident.

So the repair has to be a writer of its own, and this file is the case for its
three gates being individually load-bearing. The real server drives the SQL and
the commit: `tests/integration/test_stand_in_event_starts_real_postgres.py`.

## the gate that is easiest to get wrong

Gate 2 (`_is_dated_fixture_ticker`) is not decoration. For any ticker that is NOT
a dated per-match one, `futures_markets.commence_time` is still Kalshi's +14d
settlement close (gotcha #14). Without gate 2 the repair would drag an event
from a right-day midnight to a **fortnight out** — strictly worse than the bug.
`test_an_outright_never_drags_its_event_to_the_settlement_backstop` is that row.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.tasks.kalshi import (
    _REFINE_ADOPT,
    _REFINE_AGREES,
    _REFINE_INELIGIBLE,
    _STAND_IN_REFINEMENT_MAX,
    _STAND_IN_REFINEMENT_MIN_MOVE,
    _stand_in_refinement_decision,
    _stand_in_refinement_target,
)
from app.utils.event_completion import (
    DERIVED_COMMENCE_SOURCES,
    KALSHI_OCCURRENCE_COMMENCE_SOURCE,
    TICKER_DERIVED_COMMENCE_SOURCE,
    commence_time_is_a_reported_start,
)

UTC = timezone.utc

#: The specimen, exactly as production holds it.
TICKER = "KXATPMATCH-26SEP07ZVEDAR"
STAND_IN = datetime(2026, 9, 7, 0, 0, tzinfo=UTC)   # what the page renders today
PUBLISHED = datetime(2026, 9, 7, 18, 0, tzinfo=UTC)  # occurrence_datetime
BACKSTOP = datetime(2026, 9, 21, 6, 5, tzinfo=UTC)   # close_time, +14d


#: The revision arm's specimen is SOCCER, and that is the ship, not a detail.
#: CERT-3342: Kalshi's occurrence IS its expected expiration, recoverable as a
#: start only where the pad is measured exact. The tennis ticker above stays the
#: STAND-IN arm's specimen (that arm is ungated, exactly as #3544 shipped it) and
#: becomes the revision arm's REFUSAL control further down.
SOCCER_TICKER = "KXEPLGAME-26SEP07FULMUN"
SOCCER_KEY = "soccer_epl"
TENNIS_KEY = "tennis_atp"


def _target(**kw):
    args = {
        "external_id": TICKER,
        "event_commence": STAND_IN,
        "event_commence_source": TICKER_DERIVED_COMMENCE_SOURCE,
        "market_commence": PUBLISHED,
        "sport_key": TENNIS_KEY,
    }
    args.update(kw)
    return _stand_in_refinement_target(**args)


# ---------------------------------------------------------------------------
# the ship
# ---------------------------------------------------------------------------

def test_the_specimen_moves_off_midnight_to_the_hour_the_venue_published():
    assert _target() == PUBLISHED


def test_the_asian_itf_draw_moves_even_though_it_lands_the_next_utc_day():
    """The row that refutes a "same UTC day" rule.

    MEASURED at the venue (notice 26), Kalshi `/markets status=open`,
    2026-09-06: of 212 dated-match markets carrying an `occurrence_datetime`,
    **56 sit past +24h** of their own ticker-day midnight — the Asian ITF
    morning draw. `KXITFMATCH-26SEP06STOISH` is a real one: ticker day Sep 6,
    occurrence `2026-09-07T09:30Z`, i.e. **+33.5h**. A day-equality rule would
    have refused a quarter of the population, so the bound is a forward window
    and this row is why.
    """
    stand_in = datetime(2026, 9, 6, 0, 0, tzinfo=UTC)
    published = datetime(2026, 9, 7, 9, 30, tzinfo=UTC)
    assert published - stand_in > timedelta(hours=24)
    assert _target(
        external_id="KXITFMATCH-26SEP06STOISH-STO",
        event_commence=stand_in,
        market_commence=published,
    ) == published


# ---------------------------------------------------------------------------
# gate 1 — the non-overwrite control, and it fails CLOSED
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "source",
    ["espn", "odds_api", "statpal", "mlb_schedule_repair", "kalshi", "polymarket",
     None, "", "something_new"],
)
def test_only_a_named_derived_stand_in_is_ever_rewritten(source):
    """Every non-derived provenance is untouchable, including None.

    None is the important one: it is most of the `events` table, and a rule
    written as "not a reported start" or "not one of these good sources" would
    admit it. This is an allowlist of one named set, so a new provenance is
    excluded until somebody adds it deliberately.

    `kalshi_occurrence` is deliberately NOT in this list: #3565 gives it its
    own revision rule (below), because the venue restating its own hour is one
    provider's row at two points in time, not two authorities disagreeing.
    """
    assert source not in DERIVED_COMMENCE_SOURCES
    assert source != KALSHI_OCCURRENCE_COMMENCE_SOURCE
    assert _target(event_commence_source=source) is None


def test_the_allowlist_is_the_derived_set_itself_not_a_copy_of_it():
    """If a second derived provenance is added, this repair covers it without
    an edit here — and this assertion is what proves the coupling is real
    rather than two lists that happen to agree today."""
    for derived in DERIVED_COMMENCE_SOURCES:
        assert _target(event_commence_source=derived) == PUBLISHED


# ---------------------------------------------------------------------------
# gate 2 — the gotcha #14 protection
# ---------------------------------------------------------------------------

def test_an_outright_never_drags_its_event_to_the_settlement_backstop():
    """THE row that makes gate 2 load-bearing.

    `KXWTA-26USO` is a tournament outright. Its `commence_time` is the +14d
    close, because for an outright the close IS the horizon. Without the
    dated-match gate this repair would read "stand-in event, Kalshi market,
    forward move" and move the event from Sep 7 midnight to **Sep 21** — a
    fortnight out, strictly worse than the midnight it replaced.
    """
    assert _target(external_id="KXWTA-26USO", market_commence=BACKSTOP) is None
    # ...and it is the TICKER that refuses it, not the distance: the same
    # outright with a plausible hour is still refused.
    assert _target(external_id="KXWTA-26USO") is None


@pytest.mark.parametrize(
    "ticker",
    ["KXATP1RANK-26DEC31", "KXATPADVANCE-26USOSEMI",
     "KXHONEYDEUCE-01JAN27", "KXBBCHARTPOSITIONALBUM-26SEP08TAYSWI",
     "KXNCAAFCFPPOLL-26SEP16", "KXJOINCLUB-26OCT02AGORDON", None, ""],
)
def test_a_ticker_that_is_not_a_dated_fixture_is_refused(ticker):
    """None of these is one contest on a day. `KXATP1RANK-26DEC31` is the
    day-backtracking trap, `KXATPADVANCE-26USOSEMI` is an outright wearing a
    fixture's market-type token, and the last three are #3562's refuted-widening
    specimens: a Billboard chart position and a poll ranking have an
    `occurrence_datetime` that is not a kick-off, and `KXJOINCLUB`'s 7-character
    tail is what killed the "matchup tails are 5-6 characters" rescue."""
    assert _target(external_id=ticker) is None


def test_an_nfl_game_stand_in_now_gets_the_published_hour():
    """#3562's behaviour change, asserted rather than merely un-asserted.

    This ticker used to be refused here, and its own test said so. It is a real
    NFL fixture: `is_game` was already True so the MARKET carried the venue's
    kick-off, while the EVENT the user opens kept a midnight nobody published.
    The gate widening is what closes that gap, and deleting the old refusal
    without stating the new truth would have left the flip invisible.
    """
    assert _target(external_id="KXNFLGAME-26SEP07KCPHI") == PUBLISHED


def test_the_gate_is_the_same_predicate_that_armed_the_market_side_write():
    """One definition, so the writer that stores the hour and the repair that
    propagates it can never disagree about which rows they mean (#3488)."""
    from app.tasks.kalshi import _is_dated_fixture_ticker

    assert _is_dated_fixture_ticker(TICKER)
    assert not _is_dated_fixture_ticker("KXWTA-26USO")


# ---------------------------------------------------------------------------
# gate 3 — the window, which is what keeps #2020 closed
# ---------------------------------------------------------------------------

def test_a_market_still_on_the_settlement_backstop_is_left_alone():
    """A dated-match ticker whose market the poll has not re-timed yet.

    This is the ordering hazard made harmless: between deploy and the first
    poll, the market still holds the +14d close. +336h is far outside the
    window, so the event keeps its right-day midnight instead of being thrown
    a fortnight out. The repair is safe to run before its own upstream lands.
    """
    assert BACKSTOP - STAND_IN > _STAND_IN_REFINEMENT_MAX
    assert _target(market_commence=BACKSTOP) is None


def test_a_start_is_never_moved_earlier():
    """A stand-in IS midnight of the fixture's day, so a real start on that
    fixture cannot precede it. All 212 venue observations are positive; a
    negative delta means we are looking at a different fixture."""
    assert _target(market_commence=STAND_IN - timedelta(hours=6)) is None


def test_the_window_boundary_is_inclusive_and_one_second_past_it_is_not():
    edge = STAND_IN + _STAND_IN_REFINEMENT_MAX
    assert _target(market_commence=edge) == edge
    assert _target(market_commence=edge + timedelta(seconds=1)) is None


def test_a_move_too_small_to_matter_is_not_written():
    small = STAND_IN + _STAND_IN_REFINEMENT_MIN_MOVE - timedelta(seconds=1)
    assert _target(market_commence=small) is None
    big = STAND_IN + _STAND_IN_REFINEMENT_MIN_MOVE
    assert _target(market_commence=big) == big


def test_the_window_cannot_manufacture_a_link_the_2020_guard_would_refuse():
    """The property the window exists to preserve, asserted against the guard
    itself rather than restated as a number.

    `_ticker_date_conflicts_with_event` is the predicate whose refusals drove
    the #2020 duplicate loop — the auto-create wrote rows its own guard was
    guaranteed to reject, forever. A repair that moved an event outside that
    guard's tolerance would re-open it from the other end. So: every value
    this repair can possibly write must still be accepted by the guard.
    """
    from app.tasks.prediction_market_matching import (
        _kalshi_prefix,
        _ticker_date_conflicts_with_event,
    )
    from app.utils.prediction_market_matching import extract_game_date_from_ticker

    ticker_date = extract_game_date_from_ticker(TICKER)
    prefix = _kalshi_prefix(TICKER)

    # Sweep the whole writable window at 30-minute resolution.
    step = timedelta(minutes=30)
    offset = timedelta(0)
    checked = 0
    while offset <= _STAND_IN_REFINEMENT_MAX:
        candidate = STAND_IN + offset
        if _target(market_commence=candidate) is not None:
            assert not _ticker_date_conflicts_with_event(
                ticker_date, candidate, prefix
            ), f"+{offset} would be refused by the #2020 linkage guard"
            checked += 1
        offset += step
    assert checked > 60, f"the sweep must actually exercise the window ({checked})"


# ---------------------------------------------------------------------------
# gate 1b — the same-provider revision (#3565)
# ---------------------------------------------------------------------------

#: The specimen after the first repair: the page renders the venue's hour.
REVISED_FROM = datetime(2026, 9, 7, 18, 0, tzinfo=UTC)


def _revision(**kw):
    args = {
        "external_id": SOCCER_TICKER,
        "event_commence": REVISED_FROM,
        "event_commence_source": KALSHI_OCCURRENCE_COMMENCE_SOURCE,
        "market_commence": datetime(2026, 9, 7, 20, 30, tzinfo=UTC),
        "sport_key": SOCCER_KEY,
    }
    args.update(kw)
    return _stand_in_refinement_target(**args)


def test_a_restated_hour_on_the_same_ticker_day_is_adopted():
    """The defect arm 1 names: Kalshi moves the order of play (rain, a long
    preceding match, a night-session reshuffle) and the event follows instead
    of advertising a time the venue itself has withdrawn."""
    later = datetime(2026, 9, 7, 20, 30, tzinfo=UTC)
    assert _revision(market_commence=later) == later


def test_a_revision_may_move_a_match_earlier():
    """A reshuffle moves matches earlier too. The stand-in path's never-earlier
    rule exists because a stand-in IS the fixture day's midnight; a revision
    starts from a published hour, so an earlier published hour is still a
    forward position on the ticker day."""
    earlier = datetime(2026, 9, 7, 16, 0, tzinfo=UTC)
    assert _revision(market_commence=earlier) == earlier


def test_a_revision_below_the_ticker_day_is_refused():
    """Before the ticker's own midnight is a different fixture (or a poisoned
    market), not a restatement."""
    assert _revision(market_commence=STAND_IN - timedelta(hours=1)) is None


def test_a_revision_is_measured_against_the_ticker_day_not_the_last_write():
    """The anti-walk bound: repeated restatements cannot ratchet a row forward
    one window at a time. The market sits 6h past the previously written
    18:00Z — inside a 36h window measured from the last write — but past
    ticker-midnight + 36h, so it is refused."""
    past_ticker_window = STAND_IN + _STAND_IN_REFINEMENT_MAX + timedelta(seconds=1)
    assert past_ticker_window - REVISED_FROM < _STAND_IN_REFINEMENT_MAX
    assert _revision(market_commence=past_ticker_window) is None
    # ...while the ticker-day edge itself is inclusive.
    edge = STAND_IN + _STAND_IN_REFINEMENT_MAX
    assert _revision(market_commence=edge) == edge


def test_a_settlement_backstop_is_still_refused_on_a_revised_row():
    """Gate 3 keeps working after the first write: a market that falls back to
    the +14d close must not drag a correctly-timed event a fortnight out."""
    assert BACKSTOP - REVISED_FROM > _STAND_IN_REFINEMENT_MAX
    assert _revision(market_commence=BACKSTOP) is None


def test_repeating_the_same_hour_is_a_no_op():
    """Convergence. The rail runs every cycle and now re-selects occurrence
    rows; a venue that restates nothing must not produce a write (which is
    also what keeps `test_a_second_run_is_a_no_op` green)."""
    assert _revision(market_commence=REVISED_FROM) is None
    small = REVISED_FROM + _STAND_IN_REFINEMENT_MIN_MOVE - timedelta(seconds=1)
    assert _revision(market_commence=small) is None
    big = REVISED_FROM + _STAND_IN_REFINEMENT_MIN_MOVE
    assert _revision(market_commence=big) == big


def test_a_revision_still_requires_a_dated_fixture_ticker():
    """Gate 2 is not relaxed by the revision: an outright's +14d close is not
    a restated hour."""
    assert _revision(external_id="KXWTA-26USO", market_commence=BACKSTOP) is None
    assert _revision(external_id="KXWTA-26USO") is None


def test_a_revision_cannot_manufacture_a_link_the_2020_guard_would_refuse():
    """The revision band's half of `test_the_window_cannot_manufacture_a_link...
    Every value the revision arm can write must still be accepted by the #2020
    linkage guard — swept across the whole ticker-day window rather than
    restated as a number."""
    from app.tasks.prediction_market_matching import (
        _kalshi_prefix,
        _ticker_date_conflicts_with_event,
    )
    from app.utils.prediction_market_matching import extract_game_date_from_ticker

    ticker_date = extract_game_date_from_ticker(TICKER)
    prefix = _kalshi_prefix(TICKER)

    step = timedelta(minutes=30)
    offset = timedelta(0)
    checked = 0
    while offset <= _STAND_IN_REFINEMENT_MAX:
        candidate = STAND_IN + offset
        if _revision(market_commence=candidate) is not None:
            assert not _ticker_date_conflicts_with_event(
                ticker_date, candidate, prefix
            ), f"+{offset} would be refused by the #2020 linkage guard"
            checked += 1
        offset += step
    assert checked > 60, f"the sweep must actually exercise the window ({checked})"


def test_a_revision_with_an_unparseable_ticker_day_fails_closed(monkeypatch):
    """The ticker-day floor needs a parsed day. If the parse ever fails on a
    ticker the dated-fixture gate admitted, the revision is refused rather
    than measured against nothing."""
    import app.utils.prediction_market_matching as pmm

    monkeypatch.setattr(pmm, "extract_game_date_from_ticker", lambda _t: None)
    assert _revision() is None


# ---------------------------------------------------------------------------
# what the repair writes, and what it deliberately does not
# ---------------------------------------------------------------------------

def test_the_stamped_provenance_says_a_clock_may_run_from_the_new_value():
    """The row stops being a stand-in, and that is the point.

    q076 refuses to start a clock on `kalshi_ticker` because midnight is a day
    rendered as an instant — and MEASURED, of every event ever stamped with it,
    705 closed rows carried no score, promoted off a time nobody reported. A
    published `occurrence_datetime` is the opposite case: the venue said the
    hour. Declining to promote it would keep the row frozen `scheduled` through
    a match it is correctly timed for.

    Stated explicitly because it is a behaviour change with reach: 185 tennis
    events become promotable at their real start rather than at midnight. The
    repair itself never writes `status` — that stays the promotion gate's
    decision, now asked of a real time.
    """
    assert KALSHI_OCCURRENCE_COMMENCE_SOURCE not in DERIVED_COMMENCE_SOURCES
    assert commence_time_is_a_reported_start(KALSHI_OCCURRENCE_COMMENCE_SOURCE)
    assert not commence_time_is_a_reported_start(TICKER_DERIVED_COMMENCE_SOURCE)


def test_the_two_provenances_are_distinct_strings():
    """`kalshi_ticker` and `kalshi_occurrence` must not collapse: the whole
    repair turns on telling a parsed day from a published hour."""
    assert KALSHI_OCCURRENCE_COMMENCE_SOURCE != TICKER_DERIVED_COMMENCE_SOURCE


def test_a_naive_datetime_from_the_driver_does_not_crash_the_window():
    """`events.commence_time` is `timestamptz` so asyncpg hands back an aware
    value, but the arithmetic must not be one driver change away from a
    TypeError that would take the whole post-loop block's `except` arm."""
    assert _target(
        event_commence=STAND_IN.replace(tzinfo=None),
        market_commence=PUBLISHED.replace(tzinfo=None),
    ) == PUBLISHED


@pytest.mark.parametrize("missing", ["event_commence", "market_commence"])
def test_a_missing_time_is_no_signal(missing):
    assert _target(**{missing: None}) is None


# ---------------------------------------------------------------------------
# wiring — every assertion above is about a function nobody has to call
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# #3565 — the two Nones. `target is None` is not one answer.
# ---------------------------------------------------------------------------

def _reason(**kw):
    """The revision specimen's REASON, defaulting to a restatement."""
    args = {
        "external_id": SOCCER_TICKER,
        "event_commence": REVISED_FROM,
        "event_commence_source": KALSHI_OCCURRENCE_COMMENCE_SOURCE,
        "market_commence": datetime(2026, 9, 7, 20, 30, tzinfo=UTC),
        "sport_key": SOCCER_KEY,
    }
    args.update(kw)
    return _stand_in_refinement_decision(**args)[1]


def test_an_adopted_restatement_reports_adopt():
    assert _reason() == _REFINE_ADOPT


# ---------------------------------------------------------------------------
# CERT-3342: the hour must be RECOVERABLE as a start before it may be written.
#
# Kalshi's `occurrence_datetime` is byte-identical to `expected_expiration_time`
# (venue-read, #5905). It is a kick-off NOWHERE — only, for soccer, a fixed
# 180 minutes after one. Tennis has no such measurement, so adopting a restated
# tennis occurrence persists an expiration and stamps it as the venue's
# published start. These are the refusal controls.
# ---------------------------------------------------------------------------

def test_a_restated_tennis_hour_is_refused_not_adopted():
    """🔴 THE CERT-3342 DEFECT, on the arm this SHA adds.

    Same restatement, same ticker day, same everything the revision arm asks
    for — and it must still be refused, because the number on offer is an
    expected expiration and tennis has no measured pad to turn it into a
    start. Production specimen 15317314 stored 09:10Z while play was in the
    07:00Z hour.

    Delete the gate and this returns `_REFINE_ADOPT`: the event takes the new
    expiration, and `commence_time_source = 'kalshi_occurrence'` then asserts
    the venue published it as the kick-off. Nothing downstream can tell.
    """
    assert _reason(
        external_id=TICKER, sport_key=TENNIS_KEY
    ) == _REFINE_INELIGIBLE


def test_the_refusal_is_the_sport_and_not_the_ticker():
    """Pin WHICH input does the refusing.

    The test above moves the ticker and the sport together, so on its own it
    cannot say whether the gate reads the sport or merely dislikes a tennis
    ticker. Hold the soccer ticker and change only the sport: still refused.
    The gate is the sport key, which is what `kalshi_occurrence_scheduled_start`
    keys on and therefore the only thing that predicts recoverability.
    """
    assert _reason(sport_key=TENNIS_KEY) == _REFINE_INELIGIBLE
    assert _reason(external_id=TICKER, sport_key=SOCCER_KEY) == _REFINE_ADOPT


@pytest.mark.parametrize("unknown", [None, "", "mma_ufc", "boxing_boxing"])
def test_an_unrecoverable_or_unknown_sport_fails_closed(unknown):
    """Fails CLOSED, and the unmeasured sports are named for a reason.

    MMA's ghost/real delta is 255/265/275/285/295/345 minutes and boxing's is
    ~14 days — spreads, not pads, so there is nothing to recover. `None` is the
    caller that could not say what it holds: a writer that does not know the
    sport must not write.
    """
    assert _reason(sport_key=unknown) == _REFINE_INELIGIBLE


def test_the_stand_in_arm_is_deliberately_NOT_gated_on_recoverability():
    """The scope line of this repair, pinned so a later edit states its intent.

    Copying an occurrence onto a MIDNIGHT stand-in is master's behaviour since
    #3544 and reaches the 104 non-tennis stand-ins #3562 measured. It has the
    same expiration-vs-start problem, but narrowing it here would re-date all
    of them as a side effect of a revision-arm repair — a different ship, filed
    rather than smuggled. This SHA gates only the arm it adds.

    If a later change DOES gate the stand-in arm, this test is the one that
    should fail and be deliberately rewritten — not quietly deleted.
    """
    assert _target(sport_key=TENNIS_KEY) == PUBLISHED
    assert _target(sport_key=None) == PUBLISHED


async def test_the_loop_writes_nothing_for_a_restated_tennis_fixture():
    """The refusal at the rail, not just the predicate.

    The reachability repair means these rows now genuinely arrive here — that
    was the whole of CERT-3339 — so the gate has to hold on the loop that
    writes, not only on the pure function under it.
    """
    moved, written = await _run_loop([
        _row("KXATPMATCH-26SEP07AAAZZZ", RESTATED_HOUR, REVISED_FROM,
             KALSHI_OCCURRENCE_COMMENCE_SOURCE, sport_key=TENNIS_KEY),
    ])
    assert (moved, written) == (0, [])


async def test_the_loop_still_writes_for_a_restated_soccer_fixture():
    """The positive control for the test above.

    Without it, "the loop wrote nothing" is satisfied by a loop that writes
    nothing ever — including one where the reachability repair has regressed.
    """
    moved, written = await _run_loop([
        _row(AAA, RESTATED_HOUR, REVISED_FROM, KALSHI_OCCURRENCE_COMMENCE_SOURCE),
    ])
    assert (moved, written) == (1, [RESTATED_HOUR])


def test_an_eligible_market_holding_the_stored_hour_reports_agrees():
    """The anti-flap case, and the ONLY None allowed to end an event's turn."""
    assert _reason(market_commence=REVISED_FROM) == _REFINE_AGREES


def test_an_hour_outside_its_own_ticker_day_reports_ineligible_not_agrees():
    """🔴 The #3565 defect, at the source.

    Both of these return `None`, and a rail that reads only the value cannot
    tell them apart. Conflated, the market below speaks for an event it is not
    entitled to speak for: sorted first by `external_id`, it freezes every
    later sibling — including the venue's actual restatement — forever.
    """
    assert _reason(
        market_commence=datetime(2026, 9, 9, 18, 0, tzinfo=UTC)
    ) == _REFINE_INELIGIBLE


def test_an_undated_ticker_reports_ineligible():
    assert _reason(external_id="KXWTA-26USO") == _REFINE_INELIGIBLE


def test_a_protected_provenance_reports_ineligible():
    """An ESPN start is not an agreeing speaker; it is not a speaker."""
    assert _reason(event_commence_source="espn") == _REFINE_INELIGIBLE


@pytest.mark.parametrize("missing", ["event_commence", "market_commence"])
def test_a_missing_time_reports_ineligible(missing):
    assert _reason(**{missing: None}) == _REFINE_INELIGIBLE


def test_the_stand_in_arm_reports_the_same_vocabulary():
    """The reasons are not revision-only: the stand-in arm distinguishes a
    market that agrees from one the window refused, so the loop can never grow
    a second, divergent notion of "nothing to say"."""
    assert _stand_in_refinement_decision(
        TICKER, STAND_IN, TICKER_DERIVED_COMMENCE_SOURCE, PUBLISHED,
        sport_key=TENNIS_KEY,
    ) == (PUBLISHED, _REFINE_ADOPT)
    assert _stand_in_refinement_decision(
        TICKER, STAND_IN, TICKER_DERIVED_COMMENCE_SOURCE, STAND_IN,
        sport_key=TENNIS_KEY,
    )[1] == _REFINE_AGREES
    assert _stand_in_refinement_decision(
        TICKER, STAND_IN, TICKER_DERIVED_COMMENCE_SOURCE, BACKSTOP,
        sport_key=TENNIS_KEY,
    )[1] == _REFINE_INELIGIBLE


def test_the_value_half_still_answers_exactly_what_it_used_to():
    """`_stand_in_refinement_target` is now a wrapper. Its contract is that
    every caller and every test above it cannot tell — the tuple's first
    element IS the old return value, for all four outcomes."""
    for kw in (
        {},
        {"market_commence": REVISED_FROM},
        {"external_id": "KXWTA-26USO"},
        {"event_commence_source": "espn"},
    ):
        args = {
            "external_id": SOCCER_TICKER,
            "event_commence": REVISED_FROM,
            "event_commence_source": KALSHI_OCCURRENCE_COMMENCE_SOURCE,
            "market_commence": datetime(2026, 9, 7, 20, 30, tzinfo=UTC),
            "sport_key": SOCCER_KEY,
        }
        args.update(kw)
        assert (
            _stand_in_refinement_target(**args)
            == _stand_in_refinement_decision(**args)[0]
        )


async def _run_loop(rows):
    """Drive the REAL loop over `rows`, returning `(moved, [written values])`.

    The only seam is the session, so the ordering, the dedupe, the anti-flap
    control and the compare-and-set gating are all production code. The DB
    contract itself is not in scope here and is proved against a real server
    in `tests/integration/test_stand_in_event_starts_real_postgres.py`.
    """
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    from unittest.mock import patch

    import app.tasks.kalshi as kalshi_task

    class _Session:
        def __init__(self):
            self.writes = []

        async def execute(self, sql, args=None):
            if str(sql).lstrip().startswith("SELECT"):
                return SimpleNamespace(fetchall=lambda: rows)
            self.writes.append(args)
            return SimpleNamespace(rowcount=1)

        async def commit(self):
            pass

    session = _Session()

    @asynccontextmanager
    async def _factory(**_budget):
        yield session

    with patch.object(kalshi_task, "get_task_session", _factory):
        moved = await kalshi_task._refine_stand_in_event_starts()
    return moved, [w["dt"] for w in session.writes]


def _row(external_id, market_commence, event_commence, source,
         sport_key=SOCCER_KEY):
    from types import SimpleNamespace

    return SimpleNamespace(
        event_id=1,
        event_commence=event_commence,
        event_source=source,
        sport_key=sport_key,
        external_id=external_id,
        market_commence=market_commence,
    )


#: The loop specimens are SOCCER for the same reason the predicate ones are
#: (CERT-3342): these arms drive the REVISION arm, which only serves sports
#: whose occurrence hour is recoverable as a start.
AAA = "KXEPLGAME-26SEP07AAAZZZ"
BBB = "KXEPLGAME-26SEP07BBBZZZ"
RESTATED_HOUR = datetime(2026, 9, 7, 20, 30, tzinfo=UTC)
OFF_TICKER_DAY = datetime(2026, 9, 9, 18, 0, tzinfo=UTC)


async def test_an_ineligible_first_market_does_not_end_the_events_turn():
    """🔴 The #3565 defect in the rail, not the predicate.

    `AAA` sorts first and its hour is outside its own ticker day, so it is not
    an eligible speaker. `BBB` is the venue's restatement. Treating AAA's
    `None` as agreement returns `(0, [])` and the event is frozen forever —
    the sort is stable, so AAA sorts first on every future run too.
    """
    moved, written = await _run_loop([
        _row(AAA, OFF_TICKER_DAY, REVISED_FROM, KALSHI_OCCURRENCE_COMMENCE_SOURCE),
        _row(BBB, RESTATED_HOUR, REVISED_FROM, KALSHI_OCCURRENCE_COMMENCE_SOURCE),
    ])
    assert (moved, written) == (1, [RESTATED_HOUR])


async def test_an_eligible_first_market_that_agrees_still_ends_the_turn():
    """The anti-flap control, which the fix above must not cost us.

    Both markets are eligible and they disagree. The event already holds AAA's
    hour, so AAA agrees — and BBB must NOT be consulted. Consulting it adopts
    22:00; the run after that, AAA differs and is adopted again; the event
    flaps between two hours forever.
    """
    moved, written = await _run_loop([
        _row(AAA, REVISED_FROM, REVISED_FROM, KALSHI_OCCURRENCE_COMMENCE_SOURCE),
        _row(BBB, datetime(2026, 9, 7, 22, 0, tzinfo=UTC), REVISED_FROM,
             KALSHI_OCCURRENCE_COMMENCE_SOURCE),
    ])
    assert (moved, written) == (0, [])


async def test_two_disagreeing_markets_reach_a_fixed_point_not_a_flap():
    """The two tests above, composed over successive runs — which is the only
    place a flap can be observed at all."""
    first_moved, first_written = await _run_loop([
        _row(AAA, REVISED_FROM, STAND_IN, TICKER_DERIVED_COMMENCE_SOURCE),
        _row(BBB, datetime(2026, 9, 7, 22, 0, tzinfo=UTC), STAND_IN,
             TICKER_DERIVED_COMMENCE_SOURCE),
    ])
    assert (first_moved, first_written) == (1, [REVISED_FROM])

    adopted = first_written[0]
    second_moved, second_written = await _run_loop([
        _row(AAA, REVISED_FROM, adopted, KALSHI_OCCURRENCE_COMMENCE_SOURCE),
        _row(BBB, datetime(2026, 9, 7, 22, 0, tzinfo=UTC), adopted,
             KALSHI_OCCURRENCE_COMMENCE_SOURCE),
    ])
    assert (second_moved, second_written) == (0, [])


async def test_an_all_ineligible_event_writes_nothing():
    """Silence adopts nothing either — the fix widens what is REACHED, never
    what is written."""
    moved, written = await _run_loop([
        _row(AAA, OFF_TICKER_DAY, REVISED_FROM, KALSHI_OCCURRENCE_COMMENCE_SOURCE),
        _row(BBB, datetime(2026, 9, 11, 18, 0, tzinfo=UTC), REVISED_FROM,
             KALSHI_OCCURRENCE_COMMENCE_SOURCE),
    ])
    assert (moved, written) == (0, [])


def test_the_poll_actually_calls_the_repair():
    """Delete the call site and every other test in this file still passes.

    The same hole #3488's own guard was written for: the tests all drive the
    helper directly, so the ONE thing that makes the ship reach production —
    the poll invoking it — is exactly what nothing asserts. Read off the AST
    rather than a substring, so a mention in a comment or docstring cannot
    satisfy it.
    """
    import ast
    import inspect

    import app.tasks.kalshi as kalshi_task

    tree = ast.parse(inspect.getsource(kalshi_task._poll_kalshi_markets))
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "_refine_stand_in_event_starts" in called


def test_the_repair_runs_after_the_market_side_fixup_it_reads():
    """Ordering is load-bearing, not cosmetic: the repair reads
    `futures_markets.commence_time` and `_fix_tennis_commence_times` is a
    writer of that column in the same post-loop block. Reversed, the first
    poll after deploy would refine events off markets still on the +14d
    backstop — refused by the window, so merely a wasted cycle, but the next
    writer added there would not be so lucky. This is the composition hazard
    #3532 was filed for, pinned.
    """
    import inspect

    import app.tasks.kalshi as kalshi_task

    src = inspect.getsource(kalshi_task._poll_kalshi_markets)
    assert src.index("_fix_tennis_commence_times()") < src.index(
        "_refine_stand_in_event_starts()"
    )


# ---------------------------------------------------------------------------
# CERT-3339: reachability. The revision arm is only worth its unit contracts
# if the scheduled reads actually deliver a restatement to it. These drive the
# REAL `_refresh_dated_fixture_starts` over a faked session and venue; the
# same ground is covered against a real server in
# `tests/integration/test_stand_in_event_starts_real_postgres.py`, but that
# file cannot run in the sandbox, so these are the arms that fail locally.
# ---------------------------------------------------------------------------

async def _candidate_query_call():
    """Call the REAL candidate query with a recording session.

    Returns `(sql_text, bound_params)`. The query is the gate that decides
    whether a repaired fixture is ever re-read at all.
    """
    from types import SimpleNamespace

    import app.tasks.kalshi as kalshi_task

    seen = {}

    class _Session:
        async def execute(self, sql, args=None):
            seen["sql"] = str(sql)
            seen["args"] = args
            return SimpleNamespace(fetchall=lambda: [])

    await kalshi_task._dated_fixture_refresh_candidates(_Session(), 25)
    return seen["sql"], seen["args"]


async def test_a_repaired_fixture_is_still_a_refresh_candidate():
    """🔴 Half of why #3565 was inert in production.

    Stamping `kalshi_occurrence` took the event out of
    `DERIVED_COMMENCE_SOURCES` and therefore out of this query, so the venue
    was never asked about that fixture again. A restatement nobody fetches is
    a restatement nobody can adopt — the revision arm's unit contracts all
    passed over rows the rail could never be handed.
    """
    import app.tasks.kalshi as kalshi_task

    sql, args = await _candidate_query_call()

    assert args["occurrence"] == kalshi_task.KALSHI_OCCURRENCE_COMMENCE_SOURCE
    assert ":occurrence" in sql, (
        "bound but unreferenced is not admitted — the predicate itself must "
        "name the occurrence source"
    )


async def test_the_refresh_rotation_stays_bounded_while_it_looks_wider():
    """Widening WHICH series rotate must not widen HOW MANY run per pass.

    The cost control is the budget and the horizon, not the provenance filter,
    so removing the latter may not quietly remove the former.
    """
    sql, args = await _candidate_query_call()

    assert args["budget"] == 25
    assert ":budget" in sql and ":floor" in sql and ":ceiling" in sql


#: One Ligue 1 fixture, its ticker day, and the two hours the venue publishes.
#: `_REV_RESTATED` is 2h45m EARLIER than `_REV_STORED` — an order-of-play
#: reshuffle, which the revision arm accepts (measured against the ticker day,
#: either direction) and the stand-in arm refuses (forward only). That is why
#: the stand-in control below starts from midnight rather than from the stored
#: hour: handed the same row, the two arms are answering different questions.
_REV_SERIES = "KXLIGUE1GAME"
_REV_DAY = datetime(2026, 9, 11, tzinfo=UTC)
_REV_TICKER = f"{_REV_SERIES}-26SEP11RENOLM"
_REV_STORED = _REV_DAY + timedelta(hours=21, minutes=45)
_REV_RESTATED = _REV_DAY + timedelta(hours=19)


async def _run_refresh(event_source, event_commence=_REV_STORED,
                       sport_key="soccer_france_ligue_one"):
    """Drive the REAL `_refresh_dated_fixture_starts` for one seeded fixture.

    Returns `(stats, market_writes, event_writes, restated, selects)`. The
    venue publishes `_REV_RESTATED`, a restatement inside the ticker day.
    """
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    from unittest.mock import patch

    import app.services.kalshi_api as kalshi_api
    import app.tasks.kalshi as kalshi_task

    series = _REV_SERIES
    day = _REV_DAY
    ticker = _REV_TICKER
    stored = _REV_STORED
    restated = _REV_RESTATED

    market_writes, event_writes = [], []
    selects = []

    class _Session:
        async def execute(self, sql, args=None):
            body = str(sql)
            if body.lstrip().startswith("SELECT"):
                selects.append((body, args))
                if "split_part" in body:          # the candidate query
                    return SimpleNamespace(
                        fetchall=lambda: [SimpleNamespace(series=series)]
                    )
                return SimpleNamespace(fetchall=lambda: [SimpleNamespace(
                    market_id=7,
                    external_id=ticker,
                    market_commence=stored,
                    event_id=1,
                    event_commence=event_commence,
                    event_source=event_source,
                    sport_key=sport_key,
                )])
            (event_writes if "UPDATE events" in body else market_writes).append(args)
            return SimpleNamespace(rowcount=1)

        async def commit(self):
            pass

    @asynccontextmanager
    async def _factory(**_):
        yield _Session()

    class _Venue:
        async def get_markets(self, **_):
            return [{}], None

        def parse_markets(self, raw):
            return [SimpleNamespace(
                event_ticker=ticker,
                occurrence_datetime=restated,
                close_time=day + timedelta(days=3),
            )]

    with patch.object(kalshi_task, "get_task_session", _factory), \
            patch.object(kalshi_api, "KalshiAPIService", lambda *a, **k: _Venue()):
        stats = await kalshi_task._refresh_dated_fixture_starts()

    return stats, market_writes, event_writes, restated, selects


async def test_the_market_write_is_not_filtered_by_its_events_provenance():
    """🔴 The other half, and the one this change itself introduced.

    The first cut of #3565 added `e.commence_time_source = ANY(:derived)` to
    the market SELECT, meaning to keep the EVENT half stand-in-only. It took
    the MARKET half with it: once an event was repaired, its market stopped
    receiving the venue's current hour, and the refine rail — which reads that
    stored value and nothing else — had nothing to adopt forever after.
    """
    stats, market_writes, _, restated, selects = await _run_refresh(
        "kalshi_occurrence"
    )

    assert stats["markets_moved"] == 1, (
        "an occurrence-stamped event's market must still take the restatement"
    )
    assert [w["dt"] for w in market_writes] == [restated]

    market_select = [a for body, a in selects if "split_part" not in body][0]
    assert "derived" not in market_select, (
        "the market SELECT must not filter on the event's provenance at all — "
        "the two halves state their own eligibility"
    )


async def test_the_refresh_task_never_adopts_a_revision_itself():
    """The disjoint half: widening everything is NOT the fix.

    `_stand_in_refinement_decision` derives `revision` from the source it is
    handed, so an occurrence-stamped row reaching the event half here would be
    adopted — by a loop with no anti-flap control, which lives only in
    `_refine_stand_in_event_starts`. Two writers of one revision, one of them
    unguarded, is the flap that control exists to prevent.
    """
    stats, _, event_writes, _, _ = await _run_refresh("kalshi_occurrence")

    assert stats["events_moved"] == 0
    assert event_writes == []


async def test_a_genuine_stand_in_is_still_repaired_here():
    """The positive control: the guard above must not disable the task.

    Without this, deleting the event half outright would pass every assertion
    in the test above. Starts from the MIDNIGHT stand-in, because the forward
    -only stand-in arm is a different question from the revision arm — see
    `_REV_RESTATED`.
    """
    stats, _, event_writes, restated, _ = await _run_refresh(
        "kalshi_ticker", event_commence=_REV_DAY
    )

    assert stats["events_moved"] == 1
    assert [w["dt"] for w in event_writes] == [restated]


# ── CERT-3344: one fixture, several Kalshi series, one kick-off ──────────────
#
# #6715 measured a normal soccer event carrying GAME at 22:30Z and
# BTTS/SPREAD/TOTAL at 23:30Z — 117/117 derivative pairs at GAME+60m. The
# candidate join is `ORDER BY fm.external_id`, so `KXLIGUE1BTTS` sorts ahead of
# `KXLIGUE1GAME` and the first-eligible anti-flap rail reached the DERIVATIVE
# first. Its hour is the venue's truth for its own series and a lie about the
# fixture: carried onto the event it survives the 180-minute pad and serves
# 20:30Z for a match that kicks off at 19:30Z.

_MS_DAY = datetime(2026, 9, 20, 0, 0, tzinfo=timezone.utc)
_MS_GAME_HOUR = datetime(2026, 9, 20, 22, 30, tzinfo=timezone.utc)
_MS_DERIVATIVE_HOUR = datetime(2026, 9, 20, 23, 30, tzinfo=timezone.utc)
_MS_SOCCER = "soccer_france_ligue_one"

#: In `ORDER BY fm.external_id` order. BTTS genuinely sorts first — that is the
#: whole defect, so the tuple is written in the order the rail sees, not the
#: order that makes the point comfortably.
_MS_SIBLINGS = (
    ("KXLIGUE1BTTS-26SEP20OLMPSG", _MS_DERIVATIVE_HOUR),
    ("KXLIGUE1GAME-26SEP20OLMPSG", _MS_GAME_HOUR),
    ("KXLIGUE1SPREAD-26SEP20OLMPSG", _MS_DERIVATIVE_HOUR),
    ("KXLIGUE1TOTAL-26SEP20OLMPSG", _MS_DERIVATIVE_HOUR),
)


def test_the_siblings_really_do_sort_derivative_first():
    """Anti-vacuity for every test below: if GAME sorted first, the defect
    could not arise and the guards would pass on the unrepaired code."""
    first = sorted(t for t, _ in _MS_SIBLINGS)[0]
    assert first == "KXLIGUE1BTTS-26SEP20OLMPSG", first
    assert first != "KXLIGUE1GAME-26SEP20OLMPSG"


@pytest.mark.parametrize("ticker, hour", _MS_SIBLINGS, ids=[t for t, _ in _MS_SIBLINGS])
def test_every_sibling_series_mints_the_same_kickoff(ticker, hour):
    """🔴 CERT-3344. Whichever series the rail happens to reach first, the event
    is minted on the GAME clock — so the outcome no longer depends on
    `external_id` ordering, and `20:30Z` is unreachable."""
    target, reason = _stand_in_refinement_decision(
        ticker, _MS_DAY, "kalshi_ticker", hour, sport_key=_MS_SOCCER,
    )
    assert (target, reason) == (_MS_GAME_HOUR, "adopt"), (
        f"{ticker} minted {target}, not the GAME hour {_MS_GAME_HOUR} — a page "
        f"an hour late once the 180-minute pad comes off"
    )


@pytest.mark.parametrize("ticker, hour", _MS_SIBLINGS, ids=[t for t, _ in _MS_SIBLINGS])
def test_no_sibling_moves_an_event_already_on_the_game_hour(ticker, hour):
    """The no-change half, and the fixed point. An event already on the GAME
    hour must be left alone by EVERY sibling — including the derivatives, whose
    unnormalised hour differs from it by exactly the 60 minutes of excess.

    `agrees` rather than `ineligible` is the load-bearing part: only `agrees`
    may end the event's turn, so a derivative that answered `ineligible` here
    would leave the turn open and re-raise the ordering question it just settled.
    """
    target, reason = _stand_in_refinement_decision(
        ticker, _MS_GAME_HOUR, "kalshi_occurrence", hour, sport_key=_MS_SOCCER,
    )
    assert (target, reason) == (None, "agrees"), (
        f"{ticker} answered {reason!r} against an event already on the GAME "
        f"hour; a second pass would move a correct page"
    )


def test_a_restatement_of_the_whole_fixture_is_followed_on_the_game_clock():
    """The restatement half. The venue moves the fixture an hour later and every
    series moves with it; the event must follow ONCE, onto the new GAME hour —
    not onto the derivative's, and not by two different amounts depending on
    which sibling spoke."""
    moved_game = _MS_GAME_HOUR + timedelta(hours=1)
    moved_derivative = _MS_DERIVATIVE_HOUR + timedelta(hours=1)
    adopted = {
        ticker: _stand_in_refinement_decision(
            ticker,
            _MS_GAME_HOUR,
            "kalshi_occurrence",
            moved_game if "GAME" in ticker else moved_derivative,
            sport_key=_MS_SOCCER,
        )
        for ticker, _ in _MS_SIBLINGS
    }
    assert {v for v in adopted.values()} == {(moved_game, "adopt")}, adopted


def test_a_derivative_in_an_unmeasured_league_is_left_exactly_where_it_is():
    """Fails SAFE: the correction is only ever applied where it was MEASURED.

    `KXBUNDESLIGABTTS` is a real BTTS derivative and a dated fixture ticker, so
    unlike `KXEPLTOTALCORNERS` below it genuinely reaches this arm — but
    Bundesliga is not one of the six leagues the 60-minute excess was measured
    on. Subtracting 60 minutes from it would invent a kick-off out of a
    measurement nobody took, so its hour is adopted unchanged.

    🔵 STATED LIMIT, NOT A CLAIM OF CORRECTNESS: this row may well also sit 60
    minutes late, and if it does the event is minted 60 minutes late. That is
    master's behaviour and it is unchanged here; closing it needs the same
    league-by-league measurement `KALSHI_MEASURED_SOCCER_LEAGUE_PREFIXES`
    records, which is a census and not an edit (see the module header).
    """
    target, reason = _stand_in_refinement_decision(
        "KXBUNDESLIGABTTS-26SEP20BAYDOR", _MS_DAY, "kalshi_ticker",
        _MS_DERIVATIVE_HOUR, sport_key="soccer_germany_bundesliga",
    )
    assert (target, reason) == (_MS_DERIVATIVE_HOUR, "adopt"), (
        "an unmeasured league must be adopted unchanged, never shifted by a "
        "measurement that was not taken on it"
    )


def test_series_membership_is_equality_and_not_a_prefix():
    """The primitive, asked directly, because the arm cannot reach this ticker.

    `KXEPLTOTALCORNERS` opens with the measured `KXEPLTOTAL`, so a `startswith`
    test would shift it by 60 minutes. It is a different market with no measured
    pad — and `_is_dated_fixture_ticker` rejects it outright, which is why this
    is asked of `kalshi_derivative_series_excess` rather than of the decision:
    a guard routed through the arm would pass on the prefix bug too, for the
    unrelated reason that the ticker never arrives.
    """
    from app.tasks.kalshi import _is_dated_fixture_ticker
    from app.utils.kalshi_occurrence_start import kalshi_derivative_series_excess

    assert kalshi_derivative_series_excess("KXEPLTOTALCORNERS-26SEP20ARSCHE") == (
        timedelta(0)
    )
    assert kalshi_derivative_series_excess("KXEPLTOTAL-26SEP20ARSCHE") == (
        timedelta(hours=1)
    )
    assert not _is_dated_fixture_ticker("KXEPLTOTALCORNERS-26SEP20ARSCHE")
