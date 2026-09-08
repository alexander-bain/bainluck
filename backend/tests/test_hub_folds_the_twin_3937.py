"""#3937 — the hub and the list formatter fold the twin, in ONE lookup.

ux/1128 · PILLAR: TRUTH · SHIP: the US Open hub row and the match page it opens
print one percentage for one match, even when the match's Kalshi price lives on a
suppressed duplicate row.

═══ WHAT WENT WRONG, MEASURED ═══

#3903 made the hub and the match page call one helper, ``resolve_hero``. That is
half of "one number": they called it on DIFFERENT SOURCE SETS. #3810 Fold A gave
the detail page a ``FoldedBlendView`` — the canonical's readings plus any venue
only a suppressed twin holds — and deliberately left the hub and the list
formatter unfolded, because a per-row fold is an N+1 on a page of 400 fixtures.

#3937 was filed predicting the reopening and measured exposure as ZERO at 11:05Z
on 2026-09-08, because the twin's Kalshi happened to equal the canonical's
Polymarket to the digit. Two hours later, on production ``f18fedd0`` at 13:04Z,
it was not zero — read from both surfaces in the same minute and screenshotted::

    hub  /tournaments/us-open   Alcaraz 76%   Shelton 24%
    page /events/15306813       Alcaraz 77%   Shelton 23%

    canonical 15306813 : betting 0.2381, polymarket 0.215     <- 2 sources
    twin      15306391 : kalshi 0.22                          <- the canonical LACKS it

Reproduced across three reads with unchanged ``observed_at``, so not ingest lag —
a genuine lag case in the same census (Tiafoe, briefly 58 vs 59) cleared on the
second read and is not counted.

═══ WHY THE BATCH IS THE SHIP AND NOT AN OPTIMISATION ═══

The correctness fix is one line — fold the hub. The reason it had not been done
is cost, so a fold that reintroduces the N+1 would be reverted by the first
latency measurement and the divergence would reopen a third time.
``test_one_lookup_serves_a_whole_page`` is therefore a CORRECTNESS test in this
file, not a performance nicety: it is the property that lets the fold stay.

═══ THE MUTANT EACH SECTION MUST FAIL ═══

Deleting the ``folded_probability_sources_batch`` call from ``_load_blends`` and
handing ``resolve_hero`` the bare row is the exact regression, and it is what
``TestTheHubLoaderItself`` fails on — those tests run the real loader's real
``select()`` against a session that answers real SQL, rather than injecting a
blend map below the seam (the CERT-2235 lesson).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app.models.models import Base, Event, Sport
from app.routes import events as events_route
from app.routes import tournaments as route
from app.services.anchor_channel import duplicate_tag
from app.utils.proven_duplicates import (
    _tag_elements,
    folded_probability_sources,
    folded_probability_sources_batch,
)


# DDL shims so `create_all` can build the real schema on SQLite — the same pair
# `test_blend_fold_3810` declares, for the same reason: the fold's Postgres arm
# is an `@>` operator, so the portable arm has to be exercised against a real
# engine rather than a mock.
@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


#: The production pair above.
CANON_ID = 15306813  # Ben Shelton v Carlos Alcaraz — the row the hub renders
TWIN_ID = 15306391  # Shelton v Alcaraz — the row holding Kalshi
#: The sibling pair that did NOT diverge on the same page, so the fixtures below
#: exercise a page carrying more than one canonical.
OTHER_ID = 15307463
OTHER_TWIN_ID = 15307454
S_TENNIS = 77
QF_TIME = datetime(2026, 9, 9, 0, 30, tzinfo=timezone.utc)

#: The measured readings. `betting` at weight 3.0 dominates a weighted median, so
#: these are the PRODUCTION numbers and the assertions below are about the SOURCE
#: SET rather than about a particular percentage — see
#: `test_a_folded_venue_joins_the_evidence_without_moving_a_well_sourced_hero`
#: in `test_blend_fold_3810`, which pins that a robust hero often will not move.
CANON_SOURCES = {"betting": 0.2381, "polymarket": 0.215}
TWIN_SOURCES = {"kalshi": 0.22}


def _event(event_id, *, home, away, sources=None, tags=None):
    return Event(
        id=event_id,
        sport_id=S_TENNIS,
        home_team_name=home,
        away_team_name=away,
        commence_time=QF_TIME,
        status="scheduled",
        win_probability_sources=sources,
        event_tags=tags,
    )


def _engine(*events):
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Sport(id=S_TENNIS, key="tennis_atp", name="ATP"))
        for e in events:
            s.add(e)
        s.commit()
    return eng


class _CountingSession:
    """Runs real Core statements and COUNTS them.

    The count is the whole point of the batch, so it is measured rather than
    reasoned about: a fold that regressed to one lookup per row would keep every
    equivalence test below green and only this counter would move.
    """

    def __init__(self, session):
        self._session = session
        self.executed = 0

    async def execute(self, statement):
        self.executed += 1
        return self._session.execute(statement)


def _batch(eng, *event_ids):
    with Session(eng) as s:
        db = _CountingSession(s)
        events = [s.get(Event, eid) for eid in event_ids]
        folded = asyncio.run(folded_probability_sources_batch(db, events))
        return folded, db.executed


def _standard_page():
    """Two canonicals, each with a twin holding a venue the canonical lacks."""
    return _engine(
        _event(
            CANON_ID,
            home="Ben Shelton",
            away="Carlos Alcaraz",
            sources=dict(CANON_SOURCES),
        ),
        _event(
            TWIN_ID,
            home="Shelton",
            away="Alcaraz",
            sources=dict(TWIN_SOURCES),
            tags=[duplicate_tag(CANON_ID)],
        ),
        _event(
            OTHER_ID,
            home="Karen Khachanov",
            away="Alexander Blockx",
            sources={"betting": 0.5923},
        ),
        _event(
            OTHER_TWIN_ID,
            home="Khachanov",
            away="Blockx",
            sources={"kalshi": 0.585},
            tags=[duplicate_tag(OTHER_ID)],
        ),
    )


# ── The batch itself ─────────────────────────────────────────────────────────


class TestTheBatchedFold:
    def test_the_canonical_gains_the_twins_kalshi(self):
        """THE SHIP, through the real predicate against a real engine."""
        folded, _ = _batch(_standard_page(), CANON_ID)
        assert folded[CANON_ID] == {
            "betting": 0.2381,
            "polymarket": 0.215,
            "kalshi": 0.22,
        }

    def test_one_lookup_serves_a_whole_page(self):
        """🔴 The property that lets the fold exist at all.

        Two canonicals, one query. This is why #3810 left the hub unfolded and
        why a per-row fold would be reverted by the first latency measurement,
        reopening the divergence a third time.
        """
        _, executed = _batch(_standard_page(), CANON_ID, OTHER_ID)
        assert executed == 1

    def test_a_page_wider_than_one_chunk_is_CHUNKED_and_not_TRUNCATED(self):
        """🔴 Every event is folded, however wide the page.

        `_FOLD_BATCH_ARMS` bounds the `@>` arms in one statement because a
        500-arm plan measured ~125 ms on production. A CAP would have been the
        cheap way to bound it and would silently leave everything past the first
        chunk on the divergent number — this ship's own bug, reintroduced as a
        "limit". So the assertion is on BOTH halves: the statement count grows,
        and the last canonical on an oversized page still gets its twin.
        """
        from app.utils.proven_duplicates import _FOLD_BATCH_ARMS

        width = _FOLD_BATCH_ARMS * 2 + 1
        # Ids held as plain ints: the `Event` objects are detached once
        # `_engine`'s session closes, and reading `.id` off one then raises
        # `DetachedInstanceError` rather than returning the number.
        filler_ids = [9_000_000 + i for i in range(width - 1)]
        eng = _engine(
            _event(
                CANON_ID,
                home="Ben Shelton",
                away="Carlos Alcaraz",
                sources=dict(CANON_SOURCES),
            ),
            _event(
                TWIN_ID,
                home="Shelton",
                away="Alcaraz",
                sources=dict(TWIN_SOURCES),
                tags=[duplicate_tag(CANON_ID)],
            ),
            *(
                _event(fid, home=f"P{fid}", away=f"Q{fid}", sources={"betting": 0.5})
                for fid in filler_ids
            ),
        )
        ids = filler_ids + [CANON_ID]
        folded, executed = _batch(eng, *ids)
        assert executed == 3
        assert len(folded) == width
        # CANON_ID sorts LAST of these ids, so it lands in the final chunk — the
        # one a cap would have dropped.
        assert folded[CANON_ID]["kalshi"] == 0.22

    def test_every_event_gets_an_entry_even_with_no_twin(self):
        """Callers index the result unconditionally, so an unfolded event must
        still be a KEY — a `.get()` miss would blank the row's own readings."""
        eng = _engine(
            _event(
                CANON_ID,
                home="Ben Shelton",
                away="Carlos Alcaraz",
                sources=dict(CANON_SOURCES),
            ),
        )
        folded, _ = _batch(eng, CANON_ID)
        assert folded == {CANON_ID: CANON_SOURCES}

    def test_an_empty_page_asks_the_database_nothing(self):
        """`or_()` of nothing is a constant-false WHERE — a round trip that
        cannot return a row. The hub calls this on every request, including the
        ones with no linked events at all."""
        with Session(_standard_page()) as s:
            db = _CountingSession(s)
            assert asyncio.run(folded_probability_sources_batch(db, [])) == {}
            assert db.executed == 0

    def test_each_twin_is_attributed_to_its_OWN_canonical(self):
        """🔴 The `OR` says a row matched SOME arm, never WHICH.

        Both twins come back in one result set. Reading each twin's own tags is
        the only thing that stops Khachanov's Kalshi landing on the
        Shelton–Alcaraz card — a confidently wrong percentage under the right
        names, with nothing on the page to reveal it.
        """
        folded, _ = _batch(_standard_page(), CANON_ID, OTHER_ID)
        assert folded[CANON_ID]["kalshi"] == 0.22
        assert folded[OTHER_ID]["kalshi"] == 0.585

    def test_a_twin_is_not_folded_onto_a_LOOKALIKE_canonical_on_the_same_page(self):
        """🔴 The tag, and ONLY the tag, attributes a twin.

        The test above cannot fail this: when the two canonicals are different
        fixtures, `orientation_agrees` refuses the cross-fold on the names alone,
        so a batch that ignored tags entirely would still pass it. Measured — a
        mutant replacing the tag lookup with "every twin onto every canonical"
        went green on all 25 tests in this file before this case existed.

        So the two canonicals here carry the SAME player names — one fixture the
        hub renders and one it also renders (a rematch, a twin pair that has not
        been merged, the same pairing in two rounds). Orientation cannot separate
        them and the tag is the only thing left. If this reddens, the fold has
        found a name route to a suppressed row, which is the absorption
        ruling 048 bans.
        """
        rematch_id = CANON_ID + 900
        eng = _engine(
            _event(
                CANON_ID,
                home="Ben Shelton",
                away="Carlos Alcaraz",
                sources=dict(CANON_SOURCES),
            ),
            _event(
                rematch_id,
                home="Ben Shelton",
                away="Carlos Alcaraz",
                sources=dict(CANON_SOURCES),
            ),
            _event(
                TWIN_ID,
                home="Shelton",
                away="Alcaraz",
                sources=dict(TWIN_SOURCES),
                tags=[duplicate_tag(CANON_ID)],
            ),
        )
        folded, _ = _batch(eng, CANON_ID, rematch_id)
        assert folded[CANON_ID]["kalshi"] == 0.22
        assert "kalshi" not in folded[rematch_id]

    def test_a_swapped_twin_is_refused(self):
        """Orientation, for the reason the singular fold checks it: a reading is
        a HOME win probability whose meaning comes from its own row's names."""
        eng = _engine(
            _event(
                CANON_ID,
                home="Ben Shelton",
                away="Carlos Alcaraz",
                sources=dict(CANON_SOURCES),
            ),
            _event(
                TWIN_ID,
                home="Alcaraz",
                away="Shelton",
                sources=dict(TWIN_SOURCES),
                tags=[duplicate_tag(CANON_ID)],
            ),
        )
        folded, _ = _batch(eng, CANON_ID)
        assert folded[CANON_ID] == CANON_SOURCES

    def test_a_tag_naming_a_different_canonical_is_not_folded(self):
        """The control: the TAG is the only route to a twin's readings. Same
        sport, same names, same time — only `event_tags` differs. A name/time
        route to the ghost is the absorption ruling 048 bans."""
        eng = _engine(
            _event(
                CANON_ID,
                home="Ben Shelton",
                away="Carlos Alcaraz",
                sources=dict(CANON_SOURCES),
            ),
            _event(
                TWIN_ID,
                home="Shelton",
                away="Alcaraz",
                sources=dict(TWIN_SOURCES),
                tags=[duplicate_tag(CANON_ID + 1)],
            ),
        )
        folded, _ = _batch(eng, CANON_ID)
        assert folded[CANON_ID] == CANON_SOURCES

    @pytest.mark.parametrize("event_id", [CANON_ID, OTHER_ID])
    def test_the_batch_agrees_with_the_singular_fold(self, event_id):
        """🔴 The batch is a COST change, not a semantics change.

        Two implementations of one meaning is how they drift. Asserting the
        equivalence — rather than trusting that both were written from the same
        docstring — is what makes a future edit to either one visible here.
        """
        eng = _standard_page()
        batched, _ = _batch(eng, CANON_ID, OTHER_ID)
        with Session(eng) as s:
            singular = asyncio.run(
                folded_probability_sources(_CountingSession(s), s.get(Event, event_id))
            )
        assert batched[event_id] == singular


class TestTagElements:
    """`event_tags` comes back as a list on Postgres and as TEXT on SQLite."""

    def test_a_real_list_is_used_as_is(self):
        assert _tag_elements([duplicate_tag(CANON_ID)]) == [duplicate_tag(CANON_ID)]

    def test_a_serialised_array_is_decoded(self):
        """🔴 Iterating the string instead would yield single CHARACTERS.

        That matches no tag, so the batch would silently fold nothing while
        every Postgres test stayed green — a guard hole shaped exactly like the
        one CERT-2235 found.
        """
        assert _tag_elements(f'["{duplicate_tag(CANON_ID)}"]') == [
            duplicate_tag(CANON_ID)
        ]

    @pytest.mark.parametrize("tags", [None, "", "not json", 7, {"a": 1}, [1, None]])
    def test_anything_unreadable_is_no_tags(self, tags):
        """Degrades to today's unfolded answer, never to a raise on a read path."""
        assert _tag_elements(tags) == []


# ── THE REAL HUB LOADER ──────────────────────────────────────────────────────
#
# 🔴 Everything above proves the helper works. None of it would fail if
# `_load_blends` never called it. These run the REAL loader — its real
# `select()`, its real fold call — against a session that answers real SQL.


class _Row:
    def __init__(self, values: dict[str, Any]) -> None:
        for key, value in values.items():
            setattr(self, key, value)


class _Result:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return self._rows


class _LoaderSession:
    """Answers the two queries ``_load_blends`` makes, and counts each.

    Dispatch is on the labels the statements THEMSELVES asked for, so a change
    to either `select()` shows up here rather than being absorbed by a fake that
    was told what to expect.
    """

    def __init__(self, columns: dict[str, Any], twin_rows: list[tuple[Any, ...]]):
        self.columns = columns
        self.twin_rows = twin_rows
        self.event_lookups = 0
        self.twin_lookups = 0

    async def execute(self, stmt: Any) -> _Result:
        labels = [desc["name"] for desc in stmt.column_descriptions]
        if "event_tags" in labels:
            self.twin_lookups += 1
            return _Result(list(self.twin_rows))
        self.event_lookups += 1
        return _Result([_Row({lab: self.columns.get(lab) for lab in labels})])


def _hub_columns() -> dict[str, Any]:
    return {
        "id": CANON_ID,
        "home_team_name": "Ben Shelton",
        "away_team_name": "Carlos Alcaraz",
        "status": "scheduled",
        "home_score": None,
        "away_score": None,
        "completed_at": None,
        "win_probability_sources": dict(CANON_SOURCES),
        "espn_win_prob_home": None,
        "opening_home_probability": 0.2381,
        "opening_away_probability": 0.7619,
    }


def _twin_row(home="Shelton", away="Alcaraz", sources=None):
    """The 5-tuple the fold's `select()` yields, in its column order."""
    return (
        TWIN_ID,
        home,
        away,
        dict(TWIN_SOURCES) if sources is None else sources,
        [duplicate_tag(CANON_ID)],
    )


class TestTheHubLoaderItself:
    def test_the_loader_folds_the_twins_venue_into_the_hub_row(self):
        """🔴 THE SHIP AT THE SEAM THAT BROKE.

        Delete the `folded_probability_sources_batch` call from `_load_blends`
        and hand `resolve_hero` the bare row — the exact regression — and the
        source count drops back to 2 here.
        """
        session = _LoaderSession(_hub_columns(), [_twin_row()])
        blends = asyncio.run(route._load_blends(session, [CANON_ID]))
        assert session.twin_lookups == 1
        assert blends[CANON_ID]["source_count"] == 3

    def test_without_a_twin_the_row_is_exactly_what_it_was(self):
        """Acceptance 3's no-change half, at the loader: the overwhelming
        majority of matches have no suppressed duplicate and must be untouched."""
        session = _LoaderSession(_hub_columns(), [])
        blends = asyncio.run(route._load_blends(session, [CANON_ID]))
        assert blends[CANON_ID]["source_count"] == 2
        assert blends[CANON_ID]["home_name"] == "Ben Shelton"

    def test_a_swapped_twin_is_refused_at_the_loader_too(self):
        """The orientation guard has to hold THROUGH the route, not only in the
        helper — this is the reading that would print Alcaraz's number under
        Shelton's name."""
        session = _LoaderSession(
            _hub_columns(), [_twin_row(home="Alcaraz", away="Shelton")]
        )
        blends = asyncio.run(route._load_blends(session, [CANON_ID]))
        assert blends[CANON_ID]["source_count"] == 2

    def test_the_loader_asks_for_the_twins_ONCE_for_the_whole_page(self):
        """The N+1 guard at the caller, not only at the helper."""
        session = _LoaderSession(_hub_columns(), [_twin_row()])
        asyncio.run(route._load_blends(session, [CANON_ID, OTHER_ID, 15307525]))
        assert session.twin_lookups == 1

    def test_an_empty_id_list_still_touches_nothing(self):
        """`_load_blends` returns early; the fold must not turn that into a
        round trip on every hub request that has no linked events."""
        session = _LoaderSession(_hub_columns(), [_twin_row()])
        assert asyncio.run(route._load_blends(session, [])) == {}
        assert session.twin_lookups == 0
        assert session.event_lookups == 0


# ── THE LIST FORMATTER ───────────────────────────────────────────────────────


class TestTheListFormatter:
    """Acceptance 1's third surface: `_format_event_with_aggregated_odds`.

    It is SYNC and runs once per row, so it takes the fold as a parameter the
    caller batched — awaiting inside it is impossible and looping the caller
    would be the N+1 this ship exists to avoid.
    """

    def _event_orm(self, sources=None):
        event = _event(
            CANON_ID,
            home="Ben Shelton",
            away="Carlos Alcaraz",
            sources=dict(CANON_SOURCES) if sources is None else sources,
        )
        event.sport = Sport(id=S_TENNIS, key="tennis_atp", name="ATP")
        return event

    def test_a_folded_source_set_reaches_the_hero(self):
        """🔴 The formatter must read the FOLD, not the row it was handed.

        The canonical here holds NOTHING and the twin holds everything — the
        strongest case, and the one #3937's body names ("the detail page prints
        a number and the hub prints none"). A well-sourced canonical is the wrong
        fixture for this assertion: `betting` at weight 3.0 dominates a weighted
        median, so gaining a 0.8-weight venue usually does not move the hero and
        a formatter that ignored the fold entirely would still print the same
        percentage. Measured: with a well-sourced canonical, a mutant reverting
        this line to `resolve_hero(event)` left this test green.
        """
        response = events_route._format_event_with_aggregated_odds(
            self._event_orm(sources={}),
            None,
            folded_sources={"kalshi": {"value": 0.22}},
        )
        assert response["hero_probability"] == pytest.approx(0.22)
        assert response["hero_probability_source"] == "blend"

    def test_no_fold_supplied_is_the_unfolded_answer_and_not_a_crash(self):
        """🔴 The honest default.

        `None` means "this caller has not been taught to batch". The fold is
        strictly additive, so the unfolded hero is under-informed, never wrong
        in the other direction — but it must still be a hero. The CONTROL for
        the test above: same empty canonical, no fold, no number.
        """
        unfolded = events_route._format_event_with_aggregated_odds(
            self._event_orm(), None
        )
        assert unfolded["hero_probability"] is not None
        assert (
            "hero_probability"
            not in events_route._format_event_with_aggregated_odds(
                self._event_orm(sources={}), None
            )
        )

    def test_an_empty_fold_does_not_read_as_absent(self):
        """🔴 `{}` is a fold that found nothing; `None` is no fold at all.

        A truthiness test instead of an `is not None` test would collapse the
        two, so a canonical whose readings are all unparseable would silently
        fall back to reading the raw row.
        """
        response = events_route._format_event_with_aggregated_odds(
            self._event_orm(), None, folded_sources={}
        )
        assert "hero_probability" not in response
