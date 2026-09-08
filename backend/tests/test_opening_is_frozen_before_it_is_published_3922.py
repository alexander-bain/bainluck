"""A MATCH STOPS CLAIMING IT OPENED AT TODAY'S PRICE (#3922).

ux/1129 · PILLAR: TRUTH · SHIP: before a match starts, the US Open hub row and
the match page it opens no longer print an "opened at" figure or a movement
arrow — because the figure they were printing was this minute's sportsbook
price, not an opening.

═══ WHAT WAS MEASURED, ON PRODUCTION, 2026-09-08 ═══

``Event.opening_home_probability`` is not the price a market opened at. It is the
LAST PREGAME consensus: ``_maybe_set_opening_odds`` rewrites it on every poll
while the fixture is still scheduled, and freezes it at the first ball. Its own
docstring says so ("they keep updating on every poll while the game is still
scheduled"), and ``prematch_reading``'s module docstring repeats it. Three read
paths published it under the word "Opened" anyway.

Rendered and read at 390px, both surfaces in the same minute::

    hub   "Frances Tiafoe opened at 58%."   +1  59%
    page  22% – 78%   "Opened 24% – 76%"   "↓ −2% Shelton since open"

Against the books' own first-sight median (earliest ``odds_snapshots`` capture,
every one of them 1-2 days before the match), all eight quarter-finals disagreed:

    ================  ============  ==============  ======
    event             books opened  column claimed  gap
    ================  ============  ==============  ======
    15306160 Sabalenka      0.6580          0.7012  +4.3pp
    15306225 Tiafoe         0.5690          0.5830  +1.4pp
    15306813 Shelton        0.2699          0.2381  −3.2pp
    15306814 Pegula         0.7874          0.7681  −1.9pp
    15307331 Zheng          0.2968          0.2909  −0.6pp
    15307447 Andreeva       0.4119          0.3819  −3.0pp
    15307463 Khachanov      0.5410          0.5923  +5.1pp
    15307525 Zverev         0.8467          0.8587  +1.2pp
    ================  ============  ==============  ======

**8 of 8**, mean 2.6pp, worst 5.1pp — Khachanov's page said he opened at 59% when
the books opened him at 54%, printing +1pp of a real +6.6pp move.

And the reference point was not merely wrong, it was MOVING. Two reads of
``/api/tournaments/us-open`` five minutes apart (13:49Z, 13:54Z): three of eight
matches changed their *opening* — Sabalenka .6986→.7012, Andreeva .3783→.3819,
Zheng .2934→.2909 — while their current did not move at all. An arrow whose
baseline drifts is not measuring the market.

═══ WHY THE FLAT ARROWS WERE THE WORST OF IT ═══

Before the freeze the column tracks the books NOW, so ``blend − opening`` is not
movement over time at all: it is ``blend_now − books_now``. Where the blend is
books-only the two are the same number and the arrow is structurally 0.0 —
Zverev printed a flat arrow on a day his book ran 84.7 → 85.9. Where the blend
does carry prediction markets, the arrow is the venue disagreement, which is the
one thing Alex's standing ruling says a surface must never show as a feature.

CLAUDE.md: *a flat arrow is a claim*. Two of the eight rows were making it.

═══ WHAT THIS FILE PINS, AND THE ONE TEST THAT MATTERS ═══

``TestTheReaderAgreesWithTheWriter`` is the class guard and the reason the fix is
a shared predicate rather than three ``if`` statements. It drives the REAL
``_maybe_set_opening_odds`` over a matrix of states and asserts, for every one,
that it wrote its column if and only if ``opening_consensus_has_frozen`` says the
column is unpublishable. The defect being fixed is a column meaning one thing to
its writer and another to its readers, so a test that restated the reader's rule
in its own words would be the same defect wearing a fixture. Change either side
alone — add a guard to the writer, drop one from the reader — and this goes red.

The rest are the three read paths, each driven through the code that actually
serves it: the hub through the real ``_load_blends`` into the real
``build_slate``, and the card through the real ``_format_event_with_aggregated_odds``.

═══ THE MUTANT EACH SECTION MUST FAIL ═══

Delete the ``opening_consensus_has_frozen`` call from ``_load_blends`` and
``TestTheHubRow::test_a_match_that_has_not_started_shows_no_opening_and_no_arrow``
goes red while every level assertion stays green — the split that says these
guards measure the claim and not the number under it.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.sql import Update

from app.routes import events as events_route
from app.routes.tournaments import _load_blends
from app.tasks.odds_polling import _maybe_set_opening_odds
from app.utils.prematch_reading import opening_consensus_has_frozen
from app.utils.tournament_slate import PRICE_BASIS_BLEND

# The Shelton / Alcaraz quarter-final, the row both surfaces were read from.
EVENT_ID = 15306813
HOME, AWAY = "Ben Shelton", "Carlos Alcaraz"

#: The production readings. `betting` IS the blend here (a weighted median over
#: one dominant 3.0-weight source lands on it), and the column was tracking
#: `betting`, which is why this row printed a flat arrow.
BETTING = 0.2381
COLUMN_OPENING = 0.2381
#: What the books ACTUALLY opened him at, from the earliest `odds_snapshots`
#: capture on 2026-09-07. Never reachable from `Event.opening_*` — quoted here so
#: the fixture's numbers carry their provenance, not to be asserted against.
BOOKS_REALLY_OPENED = 0.2699


def _offset(hours: float) -> datetime:
    """A stamp relative to the clock, never an absolute date.

    Both directions matter here and only one of them is safe as a literal. A
    fixed PAST date stays past forever; a fixed FUTURE date is a fixture with an
    expiry on it, and this file's whole subject is a predicate that reads
    `commence_time` against `now`. Gotcha #44: offset first.
    """
    return datetime.now(timezone.utc) + timedelta(hours=hours)


# ── THE CLASS GUARD: THE READER AGREES WITH THE WRITER ───────────────────────


class _WriterSession:
    """Answers ``_maybe_set_opening_odds``' status read; records its UPDATE.

    Dispatches on the statement TYPE rather than on a where-clause shape. The
    two statements this task issues are a `select` and a Core `update`, and
    reaching into `whereclause` to tell them apart is the fake-session mistake
    that broke two unrelated files when #3937 added a query.
    """

    def __init__(self, status: str | None) -> None:
        self._status = status
        self.updates: list[Update] = []

    async def execute(self, stmt):  # noqa: ANN001, ANN201
        if isinstance(stmt, Update):
            self.updates.append(stmt)
            return SimpleNamespace()
        return SimpleNamespace(scalar_one_or_none=lambda: self._status)


#: Every combination of the two inputs the writer guards on, including the two
#: absent cases. `scheduled` + a past start is not hypothetical: the status
#: advance lags the first ball, and it is the case `status` alone gets wrong.
STATES = [
    pytest.param(_offset(8), "scheduled", id="upcoming-scheduled"),
    pytest.param(_offset(8), None, id="upcoming-status-unknown"),
    pytest.param(_offset(-2), "scheduled", id="started-status-lagging"),
    pytest.param(_offset(-2), "in_progress", id="started-in-progress"),
    pytest.param(_offset(-8), "completed", id="completed"),
    pytest.param(None, "scheduled", id="no-start-time-scheduled"),
    pytest.param(None, None, id="no-start-time-no-status"),
    pytest.param(None, "completed", id="no-start-time-completed"),
]


class TestTheReaderAgreesWithTheWriter:
    """The column is publishable exactly when its writer has stopped writing."""

    @pytest.mark.parametrize("commence_time,status", STATES)
    def test_the_predicate_is_the_writers_own_rule_inverted(
        self, commence_time, status
    ):
        """🔴 The one assertion that keeps the two ends of this column in step.

        Driven through the REAL writer, so it cannot agree with itself: the
        writer's behaviour is observed (did an UPDATE reach the session?) and the
        reader's is asked, and the two must be opposites in all eight states.
        """
        session = _WriterSession(status)
        asyncio.run(
            _maybe_set_opening_odds(
                session,
                EVENT_ID,
                0.4,
                0.6,
                None,
                None,
                commence_time=commence_time,
            )
        )
        writer_still_overwrites = bool(session.updates)
        reader_will_publish = opening_consensus_has_frozen(
            commence_time, status, datetime.now(timezone.utc)
        )
        assert writer_still_overwrites != reader_will_publish, (
            f"writer overwrites={writer_still_overwrites} while reader "
            f"publishes={reader_will_publish} for "
            f"commence_time={commence_time!r} status={status!r} — the column "
            "means two different things to its two ends, which is #3922 itself"
        )

    def test_the_matrix_exercises_both_answers(self):
        """The vacuity gate. A matrix that was all one way would prove nothing."""
        answers = {
            opening_consensus_has_frozen(
                c.values[0], c.values[1], datetime.now(timezone.utc)
            )
            for c in STATES
        }
        assert answers == {True, False}

    def test_a_naive_commence_time_is_read_as_utc_and_does_not_raise(self):
        """🔴 A `TypeError` here is a 500 on the event page hero, not a test nit.

        The writer can afford a bare `<=` inside a task's error handling. This
        predicate now sits on a render path.
        """
        now = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
        assert opening_consensus_has_frozen(
            datetime(2026, 9, 8, 11, 0), "scheduled", now
        )
        assert not opening_consensus_has_frozen(
            datetime(2026, 9, 8, 13, 0), "scheduled", now
        )


# ── THE HUB ROW, THROUGH THE REAL LOADER AND THE REAL BUILDER ────────────────


class _Row:
    """What ``session.execute(select(cols))`` yields — attributes by name only.

    Built from the statement's own `column_descriptions`, so a loader that stops
    selecting `commence_time` raises here exactly as it would in production
    rather than quietly reading `None` and withholding every opening on the site.
    """

    def __init__(self, values: dict) -> None:
        for key, value in values.items():
            setattr(self, key, value)


class _LoaderSession:
    def __init__(self, columns: dict) -> None:
        self.columns = columns

    async def execute(self, stmt):  # noqa: ANN001, ANN201
        labels = [desc["name"] for desc in stmt.column_descriptions]
        if "event_tags" in labels:
            # The #3937 batched fold. Keyed on `event_tags` and dispatched FIRST,
            # because the id-list branch below reads a where-clause this
            # statement does not have.
            return SimpleNamespace(all=lambda: [])
        return SimpleNamespace(
            all=lambda: [_Row({label: self.columns.get(label) for label in labels})]
        )


def _event_columns(commence_time: datetime, status: str = "scheduled") -> dict:
    return {
        "id": EVENT_ID,
        "home_team_name": HOME,
        "away_team_name": AWAY,
        "status": status,
        "commence_time": commence_time,
        "home_score": None,
        "away_score": None,
        "completed_at": None,
        "win_probability_sources": {
            "betting": {
                "value": BETTING,
                "updated_at": "2026-09-08T13:00:20+00:00",
            },
            "betting_book_count": 11,
        },
        "espn_win_prob_home": None,
        "opening_home_probability": COLUMN_OPENING,
        "opening_away_probability": round(1 - COLUMN_OPENING, 4),
    }


def _blend_for(commence_time: datetime, status: str = "scheduled") -> dict:
    session = _LoaderSession(_event_columns(commence_time, status))
    blends = asyncio.run(_load_blends(session, [EVENT_ID]))  # type: ignore[arg-type]
    assert EVENT_ID in blends, "the loader resolved no hero; the test proves nothing"
    return blends[EVENT_ID]


class TestTheHubRow:
    def test_a_match_that_has_not_started_shows_no_opening_and_no_arrow(self):
        """🔴 The ship. The level survives; only the claim about it goes."""
        entry = _blend_for(_offset(8))

        assert entry["opening_home_probability"] is None
        assert entry["opening_away_probability"] is None
        # THE CONTROL THAT MAKES THIS A TRUTH FIX AND NOT A DELETION: the number
        # the row prints is untouched. A change that withheld the hero along with
        # its opening would satisfy every assertion above and ship a blank card.
        assert entry["home_probability"] == pytest.approx(BETTING)
        assert entry["away_probability"] == pytest.approx(round(1 - BETTING, 6))

    def test_a_match_that_has_started_still_shows_its_opening(self):
        """🔴 The other half. Once frozen the column IS a real fixed reference."""
        entry = _blend_for(_offset(-2), status="in_progress")

        assert entry["opening_home_probability"] == pytest.approx(COLUMN_OPENING)
        assert entry["opening_away_probability"] == pytest.approx(
            round(1 - COLUMN_OPENING, 4)
        )

    def test_a_lagging_status_does_not_keep_an_opening_hidden(self):
        """🔴 Why `commence_time` is selected at all.

        `status` alone reads `scheduled` on a fixture whose first ball has been
        and gone, and that row's opening HAS frozen. A reader gated on status
        only would withhold openings from every match in play.
        """
        assert _blend_for(_offset(-2), status="scheduled")[
            "opening_home_probability"
        ] == pytest.approx(COLUMN_OPENING)

    def test_the_builder_clears_the_venue_arrow_rather_than_mixing_bases(self):
        """🔴 End to end: withholding must not hand the row back to the venue.

        `orient_event_blend`'s `BLEND_HAS_NO_OPEN` branch already does this and
        is certified (CERT-2251/2252); this pins that the pre-start case reaches
        it, because the alternative failure is silent and is the #3903 symptom —
        the event's level printed against the venue's origin.
        """
        from tests.test_tournament_slate_serves_the_event_blend_3903 import (
            _the_row,
            _linked_register,
            _venue_prices,
        )
        from tests.test_tournament_slate_serves_the_event_blend_3903 import (
            EVENT_ID as SLATE_EVENT_ID,
        )

        entry = _blend_for(_offset(8))
        row = _the_row(
            _linked_register(),
            _venue_prices(),
            {
                SLATE_EVENT_ID: {
                    **entry,
                    "home_name": "Clara Burel",
                    "away_name": "Yexin Ma",
                }
            },
        )

        assert row["price_basis"] == PRICE_BASIS_BLEND
        assert row["blend_refusal"] == "BLEND_HAS_NO_OPEN"
        for side in row["sides"]:
            assert side["opening_probability"] is None, (
                "the venue's opening survived beside the event's level — the "
                "mixed basis #3903 exists to prevent"
            )
            assert side["move"] is None


# ── THE CARD, THROUGH THE REAL LIST FORMATTER ────────────────────────────────


class TestTheCard:
    """`_format_event_with_aggregated_odds` feeds the surfaces printing `Opened X/Y`."""

    def _event(self, commence_time: datetime, status: str = "scheduled"):
        from app.models.models import Event, Sport

        event = Event(
            id=EVENT_ID,
            sport_id=1,
            home_team_name=HOME,
            away_team_name=AWAY,
            commence_time=commence_time,
            status=status,
            win_probability_sources={"betting": {"value": BETTING}},
            opening_home_probability=COLUMN_OPENING,
            opening_away_probability=round(1 - COLUMN_OPENING, 4),
        )
        event.sport = Sport(id=1, key="tennis_atp", name="ATP")
        return event

    def test_an_upcoming_card_serves_no_opening_odds(self):
        """🔴 The card and the page it opens must agree that there is no open."""
        response = events_route._format_event_with_aggregated_odds(
            self._event(_offset(8)), None
        )
        assert "opening_odds" not in response

    def test_a_started_card_still_serves_its_opening_odds(self):
        response = events_route._format_event_with_aggregated_odds(
            self._event(_offset(-2), status="in_progress"), None
        )
        assert response["opening_odds"]["home_probability"] == pytest.approx(
            COLUMN_OPENING
        )
