"""#6568 acceptance 2 — a bout already fought stops being advertised as upcoming.

The specimen, production 2026-09-16: `/events/15309068` printed "Starts in 10d 2h
· Sep 26, 2026 · 3:00 PM PDT" for Opetaia J. v Mikaelyan N., a bout Kalshi
graded on September 12, and four of the eight upcoming cards on
`/sports/boxing_boxing` were September 3 fights.

The stored hour is not an approximate start: it is `futures_markets
.expiration_time` to the second — the ~14-day settlement backstop Kalshi hangs
on a combat card (gotcha #14). `app/utils/kalshi_occurrence_start` names and
declines this class; its 180-minute pad is a soccer constant.

Every control here fails EXACTLY ONE clause of the predicate, so a control that
goes green isolates the clause it names rather than any of the others.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.utils.kalshi_expiration_start import (
    KALSHI_EXPIRATION_RECOVERY_STAMP,
    TICKER_CONTEST_DATE_SOURCE,
    apply_contest_date,
    contest_date_behind_expiration,
    is_expiration_start_candidate,
    recover_kalshi_expiration_starts,
    still_upcoming_after_recovery,
)
from app.utils.kalshi_occurrence_start import (
    KALSHI_RECOVERY_STAMP,
    kalshi_occurrence_scheduled_start,
)

# The production row, verbatim (event 15309068 / market 60644426).
STORED = datetime(2026, 9, 26, 22, 0, tzinfo=timezone.utc)
TICKER = "KXBOXING-26SEP12JN"
CONTEST = datetime(2026, 9, 12, 0, 0, tzinfo=timezone.utc)


class Ev:
    """A plain double, deliberately not an ORM row.

    The module's ORM arm is exercised separately; everything about the PREDICATE
    is true of any object with these four attributes, and a double keeps each
    control's single changed clause visible on one line.
    """

    def __init__(self, **kw):
        self.id = kw.pop("id", 15309068)
        self.external_id = kw.pop("external_id", None)
        self.commence_time = kw.pop("commence_time", STORED)
        self.commence_time_source = kw.pop("commence_time_source", "kalshi")
        for k, v in kw.items():
            setattr(self, k, v)


# ─────────────────────────── the specimen recovers ───────────────────────────


def test_the_september_12_bout_stops_claiming_september_26():
    assert contest_date_behind_expiration(Ev(), TICKER, STORED) == CONTEST


def test_the_recovered_row_says_where_its_date_came_from():
    """A ticker-derived date wearing `commence_time_source='kalshi'` would be a
    value disagreeing with the column that names its writer."""
    event = Ev()
    apply_contest_date(event, CONTEST)
    assert event.commence_time == CONTEST
    assert event.commence_time_source == TICKER_CONTEST_DATE_SOURCE


def test_the_house_reads_the_corrected_row_as_date_only_rather_than_as_an_hour():
    """The representation claim, proved against its actual consumer instead of
    asserted in the docstring: midnight UTC + `kalshi_ticker` is the pair
    `event_twin_fold.is_kalshi_date_only` already means by "asserts a DATE and
    no kick-off hour". If that predicate ever stops agreeing, this module is
    making a claim the house does not share."""
    from app.utils.event_twin_fold import is_kalshi_date_only

    event = Ev()
    assert is_kalshi_date_only(event) is False  # before: an hour it cannot support
    apply_contest_date(event, CONTEST)
    assert is_kalshi_date_only(event) is True


# ───────────────────── one control per clause, each alone ─────────────────────


def test_a_start_a_schedule_provider_reported_is_never_moved():
    """Gate 1 alone. `external_id` set means Odds API or ESPN said when this is;
    that is a reported start and not ours to re-date (ruling 048, #2693)."""
    event = Ev(external_id="d2d5b9cc47ff")
    assert contest_date_behind_expiration(event, TICKER, STORED) is None


def test_a_start_that_did_not_come_from_kalshi_is_never_moved():
    """Gate 2 alone."""
    event = Ev(commence_time_source="espn")
    assert contest_date_behind_expiration(event, TICKER, STORED) is None


def test_an_hour_that_is_not_the_contracts_expiration_is_left_alone():
    """Gate 3 alone, and it is the whole proof: ONE SECOND of daylight between
    the two columns means the stored hour was not copied from the backstop, so
    nothing here has established that it is wrong.

    This is the control that refuses a near-match. A predicate that tolerated a
    few minutes would re-date a real start that merely sits near a settlement
    instant.
    """
    near = STORED + timedelta(seconds=1)
    assert contest_date_behind_expiration(Ev(), TICKER, near) is None


def test_a_ticker_with_no_date_in_it_recovers_nothing():
    """Gate 4 alone. `ticker_game_date` returns None for a ticker it cannot
    read, and unreadable must never mean "agrees"."""
    assert contest_date_behind_expiration(Ev(), "KXBOXING-OPETAIAJ", STORED) is None
    assert contest_date_behind_expiration(Ev(), None, STORED) is None


def test_a_ticker_naming_the_same_day_changes_nothing():
    """Gate 5, lower edge. The row and the ticker agree about the day, so there
    is nothing to correct — and `>=` rather than `>` is what makes that true."""
    same_day = datetime(2026, 9, 12, 22, 0, tzinfo=timezone.utc)
    event = Ev(commence_time=same_day)
    assert contest_date_behind_expiration(event, TICKER, same_day) is None


def test_a_later_ticker_never_pushes_a_fixture_further_out():
    """Gate 5, the other direction, and it is a safety property rather than a
    refinement: moving a stand-in FORWARD is
    `kalshi._stand_in_refinement_target`'s job and is bounded there at 36h. This
    module must be incapable of it however the ticker reads."""
    early = datetime(2026, 9, 1, 22, 0, tzinfo=timezone.utc)
    event = Ev(commence_time=early)
    assert contest_date_behind_expiration(event, TICKER, early) is None


def test_the_day_compared_is_the_eastern_one_the_ticker_uses():
    """The clause no boundary control would catch, and it is a real bug if the
    comparison ever becomes `commence_time.date()`.

    2026-09-13 02:00Z is the 13th in UTC and the **12th** in US Eastern, which is
    the calendar Kalshi tickers are written in. Against the UTC day a `26SEP12`
    ticker looks strictly earlier and the row would be dragged back a day for no
    reason; against the Eastern day the two agree and nothing moves.
    """
    from app.utils.market_identity import eastern_game_date

    night = datetime(2026, 9, 13, 2, 0, tzinfo=timezone.utc)
    assert night.date() == date(2026, 9, 13)  # the tempting, wrong comparison
    assert eastern_game_date(night) == date(2026, 9, 12)  # the ticker's calendar
    event = Ev(commence_time=night)
    assert contest_date_behind_expiration(event, TICKER, night) is None


def test_a_naive_expiration_still_matches_an_aware_stored_hour():
    """Drivers can hand back a naive column, and comparing naive to aware raises
    TypeError inside a caller's bare `except` — which would not fail loudly, it
    would silently disable the correction for the whole page (gotcha #42)."""
    naive = STORED.replace(tzinfo=None)
    assert contest_date_behind_expiration(Ev(), TICKER, naive) == CONTEST


# ───────────────────────── idempotence and interlock ─────────────────────────


def test_a_row_is_corrected_once_however_many_times_it_is_offered():
    event = Ev()
    assert contest_date_behind_expiration(event, TICKER, STORED) == CONTEST
    setattr(event, KALSHI_EXPIRATION_RECOVERY_STAMP, True)
    assert contest_date_behind_expiration(event, TICKER, STORED) is None


def test_the_soccer_pad_and_this_module_refuse_each_other_in_both_directions():
    """The mutual exclusion the call sites rely on, so no arrangement of the two
    corrections can stack. Asserting only one direction would leave the call
    order load-bearing and untested."""
    # 1. soccer pad ran first -> this module declines the row.
    padded = Ev()
    setattr(padded, KALSHI_RECOVERY_STAMP, True)
    assert is_expiration_start_candidate(padded) is False
    assert contest_date_behind_expiration(padded, TICKER, STORED) is None

    # 2. this module ran first -> the soccer pad declines the row, because the
    #    source it keys on is no longer one of its own two.
    corrected = Ev()
    apply_contest_date(corrected, CONTEST)
    assert kalshi_occurrence_scheduled_start(corrected, "soccer_epl") is None


# ───────────────────────────── the batch rail ─────────────────────────────────


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class FakeSession:
    """Counts its own use, because "this costs nothing on pages that do not need
    it" is a claim about queries NOT made."""

    def __init__(self, rows=(), raises=False):
        self.rows = list(rows)
        self.raises = raises
        self.executions = 0

    async def execute(self, _stmt):
        self.executions += 1
        if self.raises:
            raise RuntimeError("database is unreachable")
        return FakeResult(self.rows)


@pytest.mark.asyncio
async def test_the_rail_corrects_the_candidate_and_leaves_its_neighbour_alone():
    bout = Ev(id=15309068)
    anchored = Ev(id=15313117, external_id="d2d5b9cc47ff")
    session = FakeSession([(15309068, TICKER, STORED), (15313117, TICKER, STORED)])

    assert await recover_kalshi_expiration_starts(session, [bout, anchored]) == 1
    assert bout.commence_time == CONTEST
    assert anchored.commence_time == STORED


@pytest.mark.asyncio
async def test_a_page_with_no_candidate_row_never_touches_the_database():
    anchored = Ev(external_id="d2d5b9cc47ff")
    espn = Ev(id=2, commence_time_source="espn")
    session = FakeSession([(15309068, TICKER, STORED)])

    assert await recover_kalshi_expiration_starts(session, [anchored, espn]) == 0
    assert session.executions == 0


@pytest.mark.asyncio
async def test_two_markets_on_one_event_correct_it_once_and_deterministically():
    """An event can hold several Kalshi markets carrying different tickers. The
    served date must not depend on the order the server returned rows, and the
    count must be events moved rather than rows examined."""
    bout = Ev(id=15309068)
    session = FakeSession(
        [
            (15309068, "KXBOXING-26SEP12JN", STORED),
            (15309068, "KXBOXING-26SEP14ZZ", STORED),
        ]
    )
    assert await recover_kalshi_expiration_starts(session, [bout]) == 1
    assert bout.commence_time == CONTEST  # the first, not the last


@pytest.mark.asyncio
async def test_a_database_that_will_not_answer_serves_the_stored_column():
    bout = Ev()
    session = FakeSession(raises=True)
    assert await recover_kalshi_expiration_starts(session, [bout]) == 0
    assert bout.commence_time == STORED
    assert bout.commence_time_source == "kalshi"


@pytest.mark.asyncio
async def test_a_second_pass_over_the_same_objects_corrects_nothing_further():
    """`/api/leagues` hands the same row objects through its fold twice in one
    request; `kalshi_occurrence_start` measured the ladder that produced
    (21:45 -> 18:45 -> 15:45). This rail must be flat."""
    bout = Ev()
    session = FakeSession([(15309068, TICKER, STORED)])
    assert await recover_kalshi_expiration_starts(session, [bout]) == 1
    assert await recover_kalshi_expiration_starts(session, [bout]) == 0
    assert bout.commence_time == CONTEST


# ─────────────────────── the rail keeps its own surface ───────────────────────

NOW = datetime(2026, 9, 16, 19, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_the_rail_marks_its_own_corrections_so_the_drop_can_find_them():
    """The two halves joined, with nothing stamped by hand.

    Every other test in this section sets the stamp itself, which makes them all
    blind to the one thing that has to be true in production: the rail is what
    puts the stamp on. A mutation pass removed `setattr(..., True)` from the
    rail and all 23 tests stayed green — the source rewrite alone was enough to
    keep the correction idempotent, so nothing noticed that
    `still_upcoming_after_recovery` had lost the only signal it reads and the
    September 3 fights went back on the rail re-dated.
    """
    bout = Ev()
    session = FakeSession([(15309068, TICKER, STORED)])
    assert await recover_kalshi_expiration_starts(session, [bout]) == 1
    assert still_upcoming_after_recovery(bout, NOW) is False


def test_a_fight_the_correction_moved_into_the_past_leaves_the_upcoming_rail():
    bout = Ev()
    setattr(bout, KALSHI_EXPIRATION_RECOVERY_STAMP, True)
    apply_contest_date(bout, CONTEST)
    assert still_upcoming_after_recovery(bout, NOW) is False


def test_a_row_this_correction_never_touched_is_never_dropped():
    """The drop is gated on the stamp and not on "is it in the past", so a row
    that is past for any other reason stays exactly where the rail put it. A
    filter that dropped those would be a different ship wearing these tests."""
    stale = Ev(commence_time=datetime(2026, 9, 1, tzinfo=timezone.utc))
    assert still_upcoming_after_recovery(stale, NOW) is True


def test_a_corrected_fight_that_is_genuinely_still_ahead_stays_on_the_rail():
    """The correction only ever moves a start earlier, so a corrected row CAN
    still be upcoming — an October bout whose ticker names September 30. The
    drop must be the clock's answer, not the stamp's."""
    ahead = Ev()
    setattr(ahead, KALSHI_EXPIRATION_RECOVERY_STAMP, True)
    apply_contest_date(ahead, datetime(2026, 9, 30, tzinfo=timezone.utc))
    assert still_upcoming_after_recovery(ahead, NOW) is True


def test_the_boxing_rail_does_not_empty_when_the_four_ghosts_go():
    """The withholding check, at the shape the production rail actually had:
    eight upcoming cards, four of them this class. A rule that removes rows owes
    the surface-still-a-surface assertion, and an empty rail would pass every
    refusal assertion above.
    """
    ghosts = []
    for i in range(4):
        g = Ev(id=15293325 + i)
        setattr(g, KALSHI_EXPIRATION_RECOVERY_STAMP, True)
        apply_contest_date(g, datetime(2026, 9, 3, tzinfo=timezone.utc))
        ghosts.append(g)
    real = [
        Ev(
            id=15313009 + i,
            commence_time=datetime(2026, 9, 19, 16, tzinfo=timezone.utc),
        )
        for i in range(4)
    ]

    kept = [e for e in ghosts + real if still_upcoming_after_recovery(e, NOW)]
    assert len(kept) == 4
    assert {e.id for e in kept} == {15313009, 15313010, 15313011, 15313012}


# ─────────────────── the two surfaces may not disagree again ──────────────────


def test_every_occurrence_recovery_site_also_runs_the_expiration_recovery():
    """#6568 acceptance 1 was filed because `/api/events/{id}` and its `/history`
    sibling served two different kick-offs for one event in the same second.
    Correcting one route and not the other would re-open exactly that, on a new
    class of row — and an unconverted call site is precisely where a gate
    silently does not apply.

    Reads the source rather than the behaviour on purpose: the failure this
    guards is a site that was never wired, which no test of the wired sites can
    see.
    """
    import pathlib

    import app.routes.events as events_module

    source = pathlib.Path(events_module.__file__).read_text()
    occurrence = source.count("recover_kalshi_occurrence_starts([event])")
    expiration = source.count("await recover_kalshi_expiration_starts(db, [event])")
    assert occurrence >= 2, "the sites this invariant is about have moved"
    assert expiration == occurrence, (
        f"{occurrence} occurrence-recovery call sites but {expiration} "
        "expiration-recovery ones — one surface will serve a different kick-off "
        "from the other (#6568 acceptance 1)"
    )


def test_the_upcoming_rail_both_corrects_and_drops():
    """The league wiring, which no other test here can see.

    `build_league` is the only reason the four September 3 cards leave
    `/sports/boxing_boxing`, and the correction and the drop are two statements
    that have to appear together: correcting without dropping prints a
    September 3 fight under "Upcoming" — a different lie rather than one fewer
    — and dropping without correcting removes rows on a stamp nothing set.

    Source-reading, like its sibling in `events.py`, because the failure it
    guards is a call site that was never wired, which no test of the wired ones
    can see. CERT-2980 blocked a neighbouring ship for exactly this gap.
    """
    import inspect

    from app.routes.league_futures import build_league

    body = inspect.getsource(build_league)
    assert (
        "await recover_kalshi_expiration_starts(db, _g_events)" in body
    ), "the upcoming rail no longer corrects Kalshi expiration starts"
    assert "still_upcoming_after_recovery(_e, now)" in body, (
        "the rail corrects the rows but no longer drops the ones the correction "
        "moved into the past — a September 3 fight under 'Upcoming'"
    )


def test_the_drop_runs_before_anything_counts_the_rows():
    """#5496's ordering, pinned. `_more_games`, the competition share and the cap
    all count rows, so a fixture that is not upcoming must not be counted as
    availability the reader never gets. The correction has to land before the
    fold, not after it.
    """
    import inspect

    from app.routes.league_futures import build_league

    body = inspect.getsource(build_league)
    assert body.index("still_upcoming_after_recovery") < body.index(
        "_folded_upcoming(_g_events)"
    ), "the drop moved after the fold; everything downstream now counts ghosts"
