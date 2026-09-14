"""A RAIL FILES A ROW UNDER THE SAME CLOCK ITS CARD PRINTS — #6031, live/217.

═══ WHY THIS SUITE EXISTS ═══

#5905 recovers a soccer kick-off from the Kalshi expected-expiration instant we
stored as one, and says of itself — correctly, and in bold — that **it writes
nothing**. It is a serve-time reading that corrects the hydrated row in place.

That is a complete fix for everything downstream of it in PYTHON. It is no fix
at all for anything that asks the QUESTION in SQL, and the rails ask it in SQL.
So a row was filed under `events.commence_time` (Kalshi's expected expiration)
while its own card printed `commence_time - 3h` (the kick-off), and the two
clocks are three hours apart by construction.

`started_without_result_rows` already names the failure this produces, in its
own docstring, as the thing it exists to prevent:

    one definition is the only thing that keeps a rail's position agreeing
    with its card's label

It was one definition in Python and a different one in SQL.

═══ THE SPECIMENS ═══

MEASURED on production 2026-09-14 00:16Z, `/api/leagues/soccer_other` — six of
the eight "Upcoming" cards were past their own printed kick-off, and two were
2h47m into play while filed as upcoming:

    id        match                  card printed   row stored     state
    15310509  Rubio Nu v Nacional    21:30Z         00:30:00Z      upcoming
    15308584  Caracas v Monagas      21:30Z         00:30:00Z      upcoming

Neither had reached `now - 2h` on the stored column; neither would for another
three hours. Over the whole table at that instant: 2 rows in that state, and
~260 Kalshi-timed soccer rows in seven days — each of which spends the three
hours of its own match being advertised as still to come.

═══ RED-FIRST ═══

`TestTheDefectReproduces` rebuilds the PRE-FIX conditions — the stored column,
where the recovery cannot reach — and asserts they get both specimens WRONG.
That arm is the only thing that proves the rest of the suite is not asserting
today's behaviour and calling it a guard: it is a hand-written copy of the old
predicate, and being a copy is the entire point (the same device, for the same
reason, as `test_the_two_rails_are_jointly_exhaustive_3211`).

═══ WHAT EACH EXCLUSION COSTS IF IT ROTS ═══

The recovery refuses three populations, and every refusal is asserted in its
POSITIVE form here — the row is on the upcoming rail — rather than as an absence
from a result set. An absence passes just as happily when the whole expression
has stopped matching anything:

  * `kalshi_ticker` — a DATE parsed out of a ticker, resolving to midnight UTC.
    Subtracting the pad would move a stand-in to 21:00 the previous day and call
    it a kick-off. Production row 15311150 (Denver v Kansas City) is exactly
    this and must not move.
  * `external_id IS NOT NULL` — a schedule provider reported the start. That
    time is a reported start and is not ours to shift.
  * any sport but soccer — the pad is 180 minutes on 11 of 11 anchored soccer
    comparisons and a SPREAD on MMA (255–345) and ~14 days on boxing. Exact for
    soccer is a fabrication anywhere else.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import and_, create_engine, or_, select
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

# SQLite cannot render Postgres-native column types. DDL shims for the sqlite
# dialect ONLY — production is Postgres and never reaches them. Without them
# `events` cannot be created and this suite degrades to shape-only coverage,
# which for a claim about which rows a WHERE returns would be no coverage.


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


from app.models import Event, Sport  # noqa: E402
from app.models.models import Base  # noqa: E402
from app.utils import event_rails as rails_module  # noqa: E402
from app.utils import kalshi_occurrence_start as recovery_module  # noqa: E402
from app.utils.event_completion import UPCOMING_GRACE  # noqa: E402
from app.utils.event_rails import (  # noqa: E402
    started_without_result_rows,
    upcoming_rail_condition,
)
from app.utils.kalshi_occurrence_start import (  # noqa: E402
    KALSHI_EXPECTED_EXPIRATION_PAD,
    KALSHI_OCCURRENCE_TIMED_SOURCES,
    kalshi_occurrence_scheduled_start,
)

NOW = datetime(2026, 9, 14, 0, 16, tzinfo=timezone.utc)

S_SOCCER = 901
S_MMA = 902
SOCCER_KEY = "soccer_other"
MMA_KEY = "mma_mixed_martial_arts"

#: A stored hour that is 30 minutes AHEAD of `now` — so on the stored column the
#: row has not even started — while the kick-off it encodes is 2h30m BEHIND, i.e.
#: past the grace. This is the production shape exactly: Caracas v Monagas
#: stored 00:30Z and printed 21:30Z against a 00:16Z clock.
STORED_PAST_GRACE = NOW + timedelta(minutes=30)

#: Stored two hours ahead ⇒ kick-off one hour behind ⇒ inside the grace. A match
#: an hour into play is NOT "no result reported"; it is being played, and the
#: grace is what protects it from being labelled as finished-without-a-result.
STORED_INSIDE_GRACE = NOW + timedelta(hours=2)

#: No Kalshi instant involved: a plainly-dated row already past the grace. It
#: must behave exactly as it did before this change.
PLAINLY_PAST = NOW - UPCOMING_GRACE - timedelta(minutes=30)
PLAINLY_FUTURE = NOW + timedelta(minutes=30)

# id -> (sport_id, external_id, commence_time_source, stored commence, label)
CORPUS = {
    101: (S_SOCCER, None, "kalshi", STORED_PAST_GRACE, "kalshi hour, 2h30m into play"),
    102: (S_SOCCER, None, "kalshi", STORED_INSIDE_GRACE, "kalshi hour, 1h into play"),
    103: (
        S_SOCCER,
        None,
        "kalshi_occurrence",
        STORED_PAST_GRACE,
        "the explicit provenance label, 2h30m into play",
    ),
    104: (
        S_SOCCER,
        None,
        "kalshi_ticker",
        STORED_PAST_GRACE,
        "a ticker DATE — refused by the recovery",
    ),
    105: (
        S_SOCCER,
        "ext-105",
        "kalshi",
        STORED_PAST_GRACE,
        "a schedule provider reported this start",
    ),
    106: (S_MMA, None, "kalshi", STORED_PAST_GRACE, "not soccer — the pad is a spread"),
    107: (S_SOCCER, None, "odds_api", PLAINLY_PAST, "no kalshi hour, plainly past"),
    108: (S_SOCCER, None, "odds_api", PLAINLY_FUTURE, "no kalshi hour, plainly ahead"),
}

#: The rows whose stored hour IS the expected-expiration instant and whose
#: recovered kick-off is past the grace. These are the two production specimens.
RECOVERED_AND_PAST_GRACE = (101, 103)

#: Every row that must remain on the upcoming rail. Three of them are the
#: recovery's refusals, stated positively; two are ordinary rows.
STILL_UPCOMING = (102, 104, 105, 106, 108)


def _event(eid):
    sport_id, external_id, source, commence, _label = CORPUS[eid]
    return Event(
        id=eid,
        sport_id=sport_id,
        external_id=external_id,
        commence_time_source=source,
        commence_time=commence,
        status="scheduled",
        home_team_name=f"Home {eid}",
        away_team_name=f"Away {eid}",
    )


@pytest.fixture(scope="module")
def corpus():
    """A real engine executing the real conditions.

    A hand-evaluated predicate would be a re-implementation of the thing under
    test, and this suite exists because there already were two implementations.
    It also makes the SQLite run meaningful in a way the sibling suite's cannot
    be: that corpus is entirely tennis, so the `CASE`'s THEN branch never
    evaluates there and the datetime arithmetic inside it is never exercised.
    Here it is, on every soccer row.
    """
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Sport(id=S_SOCCER, key=SOCCER_KEY, name="Soccer"))
        session.add(Sport(id=S_MMA, key=MMA_KEY, name="MMA"))
        session.add_all(_event(eid) for eid in CORPUS)
        session.commit()
        yield session


def _ids(session, condition):
    return set(session.execute(select(Event.id).where(condition)).scalars().all())


def _upcoming(session):
    return _ids(session, upcoming_rail_condition(NOW))


def _unreported(session):
    return _ids(session, started_without_result_rows(NOW))


def _label(eid):
    return f"{eid} ({CORPUS[eid][4]})"


class TestThePlayedMatchLeavesTheUpcomingRail:
    def test_a_match_past_its_recovered_kickoff_is_not_upcoming(self, corpus):
        """The production defect, in one assertion."""
        upcoming = _upcoming(corpus)
        wrongly_upcoming = [_label(e) for e in RECOVERED_AND_PAST_GRACE if e in upcoming]
        assert not wrongly_upcoming, (
            "these rows are past their own printed kick-off and are still being "
            f"advertised as upcoming: {wrongly_upcoming}"
        )

    def test_it_lands_on_the_unreported_rail_instead(self, corpus):
        """Leaving one rail is only half a fix — #3211's whole lesson is that a
        row on NO rail vanishes from the surface entirely."""
        unreported = _unreported(corpus)
        missing = [_label(e) for e in RECOVERED_AND_PAST_GRACE if e not in unreported]
        assert not missing, f"these rows left upcoming and landed nowhere: {missing}"

    def test_both_kalshi_provenance_labels_are_recovered(self, corpus):
        """`kalshi` and `kalshi_occurrence` mean the same instant by
        construction, so a fix that only reached one of them would leave the
        explicitly-labelled half of the population broken."""
        unreported = _unreported(corpus)
        assert 101 in unreported and 103 in unreported


class TestTheRecoverysRefusalsKeepTheirStoredClock:
    """Each refusal in its POSITIVE form — the row is ON the upcoming rail."""

    @pytest.mark.parametrize("eid", STILL_UPCOMING)
    def test_the_row_is_still_upcoming(self, corpus, eid):
        assert eid in _upcoming(corpus), (
            f"{_label(eid)} must keep the upcoming rail; the recovery does not "
            "touch it, so this change must not either"
        )

    @pytest.mark.parametrize("eid", STILL_UPCOMING)
    def test_and_is_not_also_called_unreported(self, corpus, eid):
        assert eid not in _unreported(corpus), _label(eid)

    def test_the_ticker_exclusion_is_load_bearing_not_incidental(self, corpus):
        """15311150 (Denver v Kansas City) carries `kalshi_ticker` and a stored
        midnight-UTC hour; on production 2026-09-14 00:16Z its rail clock equalled
        its stored clock exactly.

        Asserting only "104 is upcoming" would pass just as well if the pad were
        never applied to anything at all. So this asserts the counterfactual too:
        had the pad reached this row it WOULD have moved rails, and it did not.
        """
        stored = CORPUS[104][3]
        assert stored - KALSHI_EXPECTED_EXPIRATION_PAD < NOW - UPCOMING_GRACE, (
            "the fixture no longer proves anything — pick a stored hour the pad "
            "would actually move across the grace"
        )
        assert 104 in _upcoming(corpus)
        assert 104 not in _unreported(corpus)


class TestRowsWithNoKalshiHourAreUntouched:
    def test_a_plainly_past_row_is_still_unreported(self, corpus):
        assert 107 in _unreported(corpus)
        assert 107 not in _upcoming(corpus)

    def test_a_plainly_future_row_is_still_upcoming(self, corpus):
        assert 108 in _upcoming(corpus)
        assert 108 not in _unreported(corpus)


class TestTheTwoRailsStayDisjoint:
    def test_no_row_is_on_both(self, corpus):
        both = _upcoming(corpus) & _unreported(corpus)
        assert not both, sorted(both)

    def test_and_no_scheduled_row_is_on_neither(self, corpus):
        """Every row in this corpus is `scheduled`, so between them the two
        conditions must account for all of it. The pair is only correct as a
        pair: moving the floor on one and not the other opens a hole that the
        surface renders as a missing match."""
        covered = _upcoming(corpus) | _unreported(corpus)
        assert covered == set(CORPUS), sorted(set(CORPUS) - covered)


class TestTheSqlTwinAgreesWithThePythonRecovery:
    """The two implementations, compared value-for-value on the same rows.

    This is the assertion that would have caught the defect the day #5905
    shipped: it does not ask whether either side is self-consistent, it asks
    whether they answer the same question.
    """

    @pytest.mark.parametrize("eid", sorted(CORPUS))
    def test_the_rail_files_the_row_under_the_clock_its_card_prints(self, corpus, eid):
        """For every row: does the rail agree with the served kick-off?

        The comparison is between the rail's VERDICT and the verdict implied by
        the hour the page renders — not between two timestamps. That is the
        claim `started_without_result_rows` makes about itself, and it is the one
        a reader can actually see broken.
        """
        event = corpus.get(Event, eid)
        sport_key = SOCCER_KEY if CORPUS[eid][0] == S_SOCCER else MMA_KEY
        recovered = kalshi_occurrence_scheduled_start(event, sport_key)
        served_start = _as_utc(recovered if recovered is not None else CORPUS[eid][3])

        card_says_past_grace = served_start < NOW - UPCOMING_GRACE
        rail_says_past_grace = eid in _unreported(corpus)
        assert rail_says_past_grace == card_says_past_grace, (
            f"{_label(eid)}: the card prints a kick-off of {served_start} "
            f"(past grace: {card_says_past_grace}) while the rail files it as "
            f"past grace: {rail_says_past_grace}"
        )

    def test_the_python_recovery_actually_fires_on_this_corpus(self):
        """The agreement above is vacuous if `kalshi_occurrence_scheduled_start`
        returns None for every row — both sides would then read the stored hour
        and agree perfectly while the feature was dead."""
        fired = [
            eid
            for eid in CORPUS
            if kalshi_occurrence_scheduled_start(
                _event(eid), SOCCER_KEY if CORPUS[eid][0] == S_SOCCER else MMA_KEY
            )
            is not None
        ]
        assert sorted(fired) == [101, 102, 103], sorted(fired)


class TestTheConstantsAreReadNotRestated:
    def test_the_pad_is_the_recovery_modules_own_object(self):
        """A second literal `3 hours` in the rails is a second answer to a
        question #5905 measured. If that census ever finds a second value, the
        rails must move with it and not be a place it was forgotten."""
        assert (
            rails_module.KALSHI_EXPECTED_EXPIRATION_PAD
            is recovery_module.KALSHI_EXPECTED_EXPIRATION_PAD
        )

    def test_the_provenance_set_is_the_recovery_modules_own_object(self):
        assert (
            rails_module.KALSHI_OCCURRENCE_TIMED_SOURCES
            is recovery_module.KALSHI_OCCURRENCE_TIMED_SOURCES
        )

    def test_kalshi_ticker_is_absent_from_the_recovered_sources(self):
        """Stated here as well as in the recovery module because this suite is
        what fails if somebody 'fixes' the Denver row by widening the set."""
        assert "kalshi_ticker" not in KALSHI_OCCURRENCE_TIMED_SOURCES

    @pytest.mark.parametrize(
        "sport_key,is_soccer",
        [
            ("soccer_other", True),
            ("soccer_uefa_europa_league", True),
            ("soccer", True),
            ("mma_mixed_martial_arts", False),
            ("tennis_wta", False),
            ("baseball_mlb", False),
            ("", False),
        ],
    )
    def test_the_like_prefix_agrees_with_the_recovery_modules_gate(
        self, sport_key, is_soccer
    ):
        """`Sport.key.like("soccer%")` is `startswith("soccer")` written where a
        WHERE can spend it. If that module ever swaps its prefix test for an
        enumeration, the two stop meaning the same thing and this fails."""
        assert recovery_module._soccer(sport_key) is is_soccer
        assert sport_key.startswith("soccer") is is_soccer


class TestTheDefectReproduces:
    """The pre-fix conditions, hand-copied, asserted to get both specimens wrong.

    Without this arm every assertion above could be describing behaviour that
    was already correct.
    """

    @staticmethod
    def _prefix_upcoming(now):
        # Flattened rather than nested, and that is not a style choice: the
        # 16-space form of the line below is `search_suggestions_cold_mutations`
        # M23's replacement literal verbatim, so `scan_mutation_residue` reads it
        # as a mutant left in the tree and fails the whole guard.
        scheduled_arm = and_(
            Event.status == "scheduled",
            Event.commence_time >= now - UPCOMING_GRACE,
        )
        return or_(Event.status == "live", scheduled_arm)

    @staticmethod
    def _prefix_unreported(now):
        return and_(
            Event.status == "scheduled",
            Event.commence_time < now - UPCOMING_GRACE,
        )

    def test_the_stored_column_kept_the_played_match_upcoming(self, corpus):
        upcoming = _ids(corpus, self._prefix_upcoming(NOW))
        assert all(e in upcoming for e in RECOVERED_AND_PAST_GRACE), (
            "the pre-fix arm must reproduce the defect, or the suite above is "
            "asserting behaviour that never changed"
        )

    def test_and_kept_it_off_the_unreported_rail(self, corpus):
        unreported = _ids(corpus, self._prefix_unreported(NOW))
        assert not any(e in unreported for e in RECOVERED_AND_PAST_GRACE)

    def test_the_refusals_are_not_what_changed(self, corpus):
        """The rows the recovery refuses answer the SAME on both arms. A change
        that moved them would be a widening, not this fix."""
        before = _ids(corpus, self._prefix_upcoming(NOW))
        after = _upcoming(corpus)
        for eid in STILL_UPCOMING:
            assert (eid in before) == (eid in after) is True, _label(eid)


def _as_utc(value):
    """SQLite hands back a naive datetime; Postgres hands back an aware one."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class TestTheRedundantPlannerBoundsAreActuallyRedundant:
    """`_at_or_after_rail_floor` and `_before_rail_floor` each state a bound the
    `CASE` beside them already implies, to keep an indexable range the planner
    cannot otherwise infer (measured: 160.31 -> 103.32 total plan cost).

    A bound that is redundant TODAY is a semantic change the day somebody edits
    it, and nothing about reading the code would say so. These assert the
    redundancy directly: the pair answers exactly what the `CASE` answers alone,
    over every row in the corpus.
    """

    @staticmethod
    def _case_only_upcoming(now):
        # Flattened for the same reason as the sibling above — M23's literal.
        scheduled_arm = and_(
            Event.status == "scheduled",
            Event.commence_time >= rails_module.rail_commence_floor(now),
        )
        return or_(Event.status == "live", scheduled_arm)

    @staticmethod
    def _case_only_unreported(now):
        return and_(
            Event.status == "scheduled",
            Event.commence_time < rails_module.rail_commence_floor(now),
        )

    def test_the_upcoming_bound_changes_no_verdict(self, corpus):
        assert _upcoming(corpus) == _ids(corpus, self._case_only_upcoming(NOW))

    def test_the_unreported_bound_changes_no_verdict(self, corpus):
        assert _unreported(corpus) == _ids(corpus, self._case_only_unreported(NOW))

    def test_the_corpus_actually_spans_the_bound(self, corpus):
        """Redundancy over an empty or one-sided corpus is not redundancy. Rows
        must exist on BOTH sides of the pad-shifted floor, or the two tests above
        agree vacuously."""
        assert _unreported(corpus), "no row is below the floor"
        assert _upcoming(corpus), "no row is above it"
        assert any(
            eid in _unreported(corpus) for eid in RECOVERED_AND_PAST_GRACE
        ), "no recovered row crosses the pad-shifted floor"
