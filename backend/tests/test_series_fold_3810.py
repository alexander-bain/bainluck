"""#3810 — the win-probability CHART reads the rows we declined to print.

The ship, in one sentence: `/events/15305016` is a US Open semi-final whose
chart plots Polymarket's 461 readings and silently omits Kalshi's 1,446, because
those 1,446 `win_prob_snapshots` rows carry ghost `15304989`'s `event_id` and the
page only ever asked for its own.

#2693 already folded the MARKET book onto the canonical. It stopped there on
purpose, and this is the other half — but it is deliberately NOT the same edit,
for a reason that is the subject of most of this file:

    a market is self-describing (it names its own outcomes, so it means the
    same thing whichever row it is read from)

    a win-prob snapshot is not: it stores `home_win_probability`, a number whose
    meaning is supplied entirely by ITS OWN event row's `home_team_name`

So folding a series has two failure modes folding markets does not have, and
both of them produce a confident, plausible, WRONG picture rather than an error:

    1. ORIENTATION. Fold a row that disagrees about which side is "home" and the
       chart draws one player's curve as the other's — exactly inverted.
    2. INTERLEAVING. Fold two rows that both hold the same source and the line
       is drawn from two partial recordings of one price history, with a stray
       point spliced into it.

Every test below exists for one of those two, for the no-change case, or for the
ship itself. Measured population, production 2026-09-07, all 12 tagged US Open
pairs: orientation agrees 12/12 — so test 1's guard is a no-op on today's data
BY MEASUREMENT. It is here for the pair that does not agree, which nothing else
in the system would catch.
"""

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app.models.models import Base, Event, Sport, WinProbSnapshot
from app.services.anchor_channel import duplicate_tag
from app.utils.proven_duplicates import (
    folded_series_event_ids,
    orientation_agrees,
    series_row_for_each_source,
)


# DDL shims so `Base.metadata.create_all` can build the real schema on SQLite —
# the same pair `test_proven_duplicate_2263` declares, for the same reason: the
# fold's Postgres arm is an `@>` operator, so the portable arm has to be
# exercised against a real engine rather than a mock.
@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


# ── Rig support for the route tests that drive `get_event_odds_history` ──────
#
# Five modules drive that route against hand-rolled fake sessions that dispatch
# on SQL text. The fold adds a second read of `events`, so each of them needs to
# tell it apart from the route's own entity lookup — and the knowledge of what
# the fold's SQL looks like belongs HERE, beside the fold's tests, not copied
# into five rigs that would then drift apart the first time the projection
# changes.


#: The fold's exact projection. Matched with `startswith`, never as a substring:
#: `select(Event)` also mentions `events.home_team_name`, so a looser test
#: captures the entity lookup too and the route 404s on its own event.
SERIES_FOLD_SELECT = "SELECT events.id, events.home_team_name, events.away_team_name"


def is_series_fold(sql: str) -> bool:
    """True when this statement is `folded_series_event_ids`' lookup."""
    return " ".join(sql.split()).startswith(SERIES_FOLD_SELECT)


def fold_row(event):
    """An event's own ``(id, home, away)`` — what an UNTAGGED row returns.

    A rig answering with this puts the fold back where it was before this ship:
    `[event_id]`, one id, every downstream assertion unchanged.
    """
    return (
        getattr(event, "id", None),
        getattr(event, "home_team_name", None),
        getattr(event, "away_team_name", None),
    )


# The production pair this issue was filed on.
CANON_ID = 15305016  # Ben Shelton v Stefanos Tsitsipas — the row the page renders
GHOST_ID = 15304989  # Shelton v Tsitsipas — the row holding kalshi x 1,446
S_TENNIS = 77
SF_TIME = datetime(2026, 9, 6, 23, 11, tzinfo=timezone.utc)


def _event(id, *, home, away, tags=None):
    return Event(
        id=id,
        sport_id=S_TENNIS,
        home_team_name=home,
        away_team_name=away,
        commence_time=SF_TIME,
        status="completed",
        event_tags=tags,
    )


class _SyncAsAsync:
    """`folded_series_event_ids` is async because every caller is.

    The statement it runs is ordinary Core, so this shim executes it against a
    real engine rather than asserting on a mock's call args — the same device
    `test_proven_duplicate_2263` uses, and for the same reason: a fold test that
    inspects a mock cannot tell a working predicate from a typo'd one.
    """

    def __init__(self, session):
        self._session = session

    async def execute(self, statement):
        return self._session.execute(statement)


def _engine(*events):
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Sport(id=S_TENNIS, key="tennis_atp", name="ATP"))
        for e in events:
            s.add(e)
        s.commit()
    return eng


def _folded(eng, event_id):
    with Session(eng) as s:
        return asyncio.run(folded_series_event_ids(_SyncAsAsync(s), event_id))


# ── The ship, and the no-change case that has to survive it ──────────────────


class TestTheSeriesFold:
    def test_the_canonical_reads_its_suppressed_twins_series(self):
        """THE SHIP. `/events/15305016` can now reach ghost 15304989's rows."""
        eng = _engine(
            _event(CANON_ID, home="Ben Shelton", away="Stefanos Tsitsipas"),
            _event(
                GHOST_ID,
                home="Shelton",
                away="Tsitsipas",
                tags=[duplicate_tag(CANON_ID)],
            ),
        )
        assert _folded(eng, CANON_ID) == [CANON_ID, GHOST_ID]

    def test_an_untagged_event_folds_to_exactly_itself(self):
        """🔴 The no-change case, and it is the overwhelming majority of pages.

        Acceptance 3. If this ever returned `[]` the caller's `.in_(...)` becomes
        `IN ()` and every chart on the site goes blank at once, so the canonical
        is unconditionally first and unconditionally present.
        """
        eng = _engine(_event(CANON_ID, home="Ben Shelton", away="Stefanos Tsitsipas"))
        assert _folded(eng, CANON_ID) == [CANON_ID]

    def test_a_tag_naming_a_different_canonical_is_not_folded(self):
        """The control: the TAG is the only thing that reaches the ghost's rows.

        Same sport, same two names, same time — only `event_tags` differs. If
        this ever starts folding, the fold has found a name/time route to the
        ghost, which is the absorption ruling 048 bans.
        """
        eng = _engine(
            _event(CANON_ID, home="Ben Shelton", away="Stefanos Tsitsipas"),
            _event(
                GHOST_ID,
                home="Shelton",
                away="Tsitsipas",
                tags=[duplicate_tag(CANON_ID + 1)],
            ),
        )
        assert _folded(eng, CANON_ID) == [CANON_ID]


# ── Failure mode 1: orientation ──────────────────────────────────────────────


class TestOrientation:
    """🔴 The guard against plotting one player's curve under the other's name."""

    def test_the_production_population_agrees_and_is_folded(self):
        """All 12 tagged pairs, verbatim from the production read of 2026-09-07.

        The ghost spells the surname and the canonical spells the full name, in
        corresponding slots, in every pair. This is the case the guard must NOT
        refuse — a check that also rejects the real population ships the bug it
        was written to prevent, with a clean conscience.
        """
        pairs = [
            ("Ben Shelton", "Carlos Alcaraz", "Shelton", "Alcaraz"),
            ("Alexander Zverev", "Luciano Darderi", "Zverev", "Darderi"),
            ("Karen Khachanov", "Learner Tien", "Khachanov", "Tien"),
            ("Naomi Osaka", "Elena Rybakina", "Osaka", "Rybakina"),
            ("Francisco Cerundolo", "Alexander Blockx", "Cerundolo", "Blockx"),
            ("Iga Swiatek", "Qinwen Zheng", "Swiatek", "Zheng"),
            ("Mirra Andreeva", "Anastasia Potapova", "Andreeva", "Potapova"),
            ("Ben Shelton", "Stefanos Tsitsipas", "Shelton", "Tsitsipas"),
            ("Jessica Pegula", "Sorana Cirstea", "Pegula", "Cirstea"),
            ("Alex Michelsen", "Tomas Martin Etcheverry", "Michelsen", "Etcheverry"),
            ("Marta Kostyuk", "Linda Noskova", "Kostyuk", "Noskova"),
            ("Aryna Sabalenka", "Taylor Townsend", "Sabalenka", "Townsend"),
        ]
        assert [orientation_agrees(*p) for p in pairs] == [True] * 12

    def test_a_swapped_ghost_is_refused(self):
        """The inverted chart, which is worse than the omission being fixed.

        `home_win_probability` on this ghost means Tsitsipas, and the canonical
        would plot it as Shelton: a smooth, confident, exactly-backwards curve
        on a Slam semi-final, with nothing anywhere reporting a problem.
        """
        assert not orientation_agrees(
            "Ben Shelton", "Stefanos Tsitsipas", "Tsitsipas", "Shelton"
        )

    def test_a_swapped_ghost_is_dropped_from_the_fold_not_just_flagged(self):
        """End to end: the refusal has to reach the id list, not only the predicate."""
        eng = _engine(
            _event(CANON_ID, home="Ben Shelton", away="Stefanos Tsitsipas"),
            _event(
                GHOST_ID,
                home="Tsitsipas",
                away="Shelton",
                tags=[duplicate_tag(CANON_ID)],
            ),
        )
        assert _folded(eng, CANON_ID) == [CANON_ID]

    def test_an_ambiguous_pair_is_refused_rather_than_guessed(self):
        """🔴 The both-directions half of the check, and why `aligned` is not enough.

        Two sides whose names match each other as well as they match themselves.
        `aligned` is True here BY ACCIDENT — every comparison succeeds — so a
        check that stopped at `aligned` would fold a row it cannot actually
        orient. The honest answer is to refuse, not to pick a side.
        """
        assert not orientation_agrees("Williams", "Williams", "Williams", "Williams")

    def test_a_shared_last_token_is_not_a_match(self):
        """Why subset and not last-token equality.

        `Red Sox` and `White Sox` end in the same word and are different teams.
        Last-token matching would call this aligned AND crossed, and a reader
        who fixed the resulting refusal by dropping the crossed test would then
        fold two genuinely different teams' series together.
        """
        assert not orientation_agrees(
            "Boston Red Sox", "Chicago White Sox", "White Sox", "Red Sox"
        )

    def test_a_blank_name_matches_nothing(self):
        """`frozenset() <= anything` is True, so emptiness is tested explicitly.

        Without that test an empty name is a subset of BOTH sides at once and
        every nameless row folds onto every canonical.
        """
        assert not orientation_agrees("Ben Shelton", "Stefanos Tsitsipas", "", "")


# ── Failure mode 2: interleaving ─────────────────────────────────────────────


class TestOneRowPerSource:
    """🔴 Two rows' readings of ONE source are not one series."""

    def test_the_richest_row_wins_so_the_kalshi_curve_arrives_whole(self):
        """The measured shape of the specimen pair.

        canonical 15305016: polymarket x 461, no kalshi
        ghost     15304989: kalshi x 1,446,   polymarket x 1

        Kalshi comes from the ghost (the canonical has none) and Polymarket
        stays on the canonical's clean 461 — the ghost's single stray reading is
        dropped rather than spliced into the middle of the line.
        """
        counts = {
            ("polymarket", CANON_ID): 461,
            ("polymarket", GHOST_ID): 1,
            ("kalshi", GHOST_ID): 1446,
        }
        assert series_row_for_each_source(counts, CANON_ID) == {
            "polymarket": CANON_ID,
            "kalshi": GHOST_ID,
        }

    def test_the_canonical_does_not_win_on_being_canonical(self):
        """🔴 The rule that would have looked safest is the one that loses the ship.

        "Prefer the canonical" keeps a 2-point stub over a 1,446-point curve the
        moment the canonical holds any readings at all — and 15306813 (Shelton v
        Alcaraz, the NEXT semi-final) is exactly that row: 2 snapshots against
        its ghost's 67. A chart drawn from 2 points is the bug wearing a legend
        chip that says it is fixed.
        """
        counts = {("kalshi", CANON_ID): 2, ("kalshi", GHOST_ID): 67}
        assert series_row_for_each_source(counts, CANON_ID) == {"kalshi": GHOST_ID}

    def test_a_tie_breaks_to_the_canonical(self):
        """Determinism: the chart must not depend on row order."""
        counts = {("kalshi", GHOST_ID): 10, ("kalshi", CANON_ID): 10}
        assert series_row_for_each_source(counts, CANON_ID) == {"kalshi": CANON_ID}

    def test_an_unfolded_event_selects_every_source_it_has(self):
        """The no-change case again, at the second stage.

        With one event id in play every source resolves to it, so the filter in
        the caller drops nothing and the grouping is byte-identical to the one
        this replaced.
        """
        counts = {("kalshi", CANON_ID): 3, ("polymarket", CANON_ID): 9}
        assert series_row_for_each_source(counts, CANON_ID) == {
            "kalshi": CANON_ID,
            "polymarket": CANON_ID,
        }


# ── The two stages composed, over real snapshot rows ─────────────────────────


def _snap(event_id, source, minutes, home_prob):
    return WinProbSnapshot(
        event_id=event_id,
        source=source,
        captured_at=SF_TIME + timedelta(minutes=minutes),
        home_win_probability=home_prob,
        away_win_probability=1 - home_prob,
    )


def _plotted(eng, event_id):
    """What the route's grouping loop would draw, as `{source: [probabilities]}`."""
    with Session(eng) as s:
        ids = asyncio.run(folded_series_event_ids(_SyncAsAsync(s), event_id))
        snaps = (
            s.query(WinProbSnapshot)
            .filter(WinProbSnapshot.event_id.in_(ids))
            .order_by(WinProbSnapshot.captured_at)
            .all()
        )
        from collections import Counter

        chosen = series_row_for_each_source(
            Counter((x.source, x.event_id) for x in snaps), event_id
        )
        out = {}
        for snap in snaps:
            if chosen.get(snap.source) != snap.event_id:
                continue
            out.setdefault(snap.source, []).append(float(snap.home_win_probability))
        return out


class TestComposed:
    def test_the_ghosts_kalshi_curve_is_drawn_and_the_stray_point_is_not(self):
        """The whole ship in one assertion, on the shape production actually holds."""
        eng = _engine(
            _event(CANON_ID, home="Ben Shelton", away="Stefanos Tsitsipas"),
            _event(
                GHOST_ID,
                home="Shelton",
                away="Tsitsipas",
                tags=[duplicate_tag(CANON_ID)],
            ),
        )
        with Session(eng) as s:
            s.add_all(
                [
                    _snap(CANON_ID, "polymarket", 0, 0.60),
                    _snap(CANON_ID, "polymarket", 2, 0.62),
                    # the ghost's single stray polymarket reading, mid-series
                    _snap(GHOST_ID, "polymarket", 1, 0.11),
                    _snap(GHOST_ID, "kalshi", 0, 0.71),
                    _snap(GHOST_ID, "kalshi", 1, 0.73),
                    _snap(GHOST_ID, "kalshi", 2, 0.75),
                ]
            )
            s.commit()

        drawn = _plotted(eng, CANON_ID)

        assert set(drawn) == {"polymarket", "kalshi"}, "acceptance 2: kalshi is drawn"
        assert drawn["kalshi"] == [0.71, 0.73, 0.75]
        assert drawn["polymarket"] == [0.60, 0.62], "the 0.11 stray is not spliced in"

    def test_a_swapped_ghost_contributes_nothing_at_all(self):
        """🔴 The inverted curve never reaches the chart, not even partially."""
        eng = _engine(
            _event(CANON_ID, home="Ben Shelton", away="Stefanos Tsitsipas"),
            _event(
                GHOST_ID,
                home="Tsitsipas",
                away="Shelton",
                tags=[duplicate_tag(CANON_ID)],
            ),
        )
        with Session(eng) as s:
            s.add_all(
                [
                    _snap(CANON_ID, "polymarket", 0, 0.60),
                    _snap(GHOST_ID, "kalshi", 0, 0.29),
                ]
            )
            s.commit()

        assert _plotted(eng, CANON_ID) == {"polymarket": [0.60]}
