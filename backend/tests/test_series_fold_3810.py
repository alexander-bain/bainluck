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


#: The BLEND fold's projection (#3810 Fold A, `folded_probability_sources`) is
#: this one plus a fourth column. It lives here, beside its sibling and in the
#: module the rigs already import, because since #3911 BOTH folds run on the
#: history route and no rig can tell them apart without knowing both.
BLEND_FOLD_SELECT = f"{SERIES_FOLD_SELECT}, events.win_probability_sources"


def is_blend_fold(sql: str) -> bool:
    """True when this statement is `folded_probability_sources`' lookup."""
    return " ".join(sql.split()).startswith(BLEND_FOLD_SELECT)


def is_series_fold(sql: str) -> bool:
    """True when this statement is `folded_series_event_ids`' lookup.

    🔴 EXCLUSIVE of the blend fold, since #3911 put both folds on the history
    route. The blend fold's projection EXTENDS this one, so a bare `startswith`
    claims it too — and a rig that believed it handed a four-column lookup its
    three-column rows, which `merge_probability_sources` unpacks into a
    `ValueError` and the route serves as a 500. Every rig driving
    `get_event_odds_history` inherits the fix by asking this question.
    """
    flat = " ".join(sql.split())
    return flat.startswith(SERIES_FOLD_SELECT) and not is_blend_fold(flat)


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


def blend_fold_row(event):
    """An event's own ``(id, home, away, sources)`` — the BLEND fold's shape.

    The neutral answer for a rig that is not testing Fold A: the row's own
    readings fold to the row's own dict, so the pinned chart edge is exactly the
    number it was before #3911.
    """
    return fold_row(event) + (getattr(event, "win_probability_sources", None),)


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


# ── THE REAL ROUTE ───────────────────────────────────────────────────────────
#
# 🔴 REQUIRED REPAIR `CHART-SERIES-FOLD-REAL-ROUTE-GUARD-3810` (CERT-2208 BLOCK).
#
# Everything above this line is correct and none of it touches the shipping
# seam. `_plotted` RE-IMPLEMENTS the route's grouping loop — the `.in_()`, the
# `Counter`, the `series_row.get(...) != snap.event_id` skip — so mutating the
# route's own query back from `.in_(series_event_ids)` to `event_id == event_id`
# deletes the entire ship and leaves all 15 tests above green. The cert found
# exactly that, and it is the oldest trap in this repo: a composed test proves
# the helpers compose, never that the caller calls them.
#
# So these drive the REAL `get_event_odds_history` and assert on the payload a
# reader's browser receives.

from types import SimpleNamespace  # noqa: E402
from unittest.mock import MagicMock  # noqa: E402

from app.routes.events import get_event_odds_history  # noqa: E402


class _Result:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)

    def scalars(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class _RouteSession:
    """Answers `get_event_odds_history` by the table each statement reads.

    Matched on the FROM clause and on the fold's exact projection, never on a
    bare substring: `events` carries a `win_probability_sources` column, so
    testing `"win_prob" in sql` routes the entity lookup into the snapshot arm
    and the route 404s on its own event (the trap `is_series_fold` exists for).
    """

    def __init__(self, event, fold_rows, snapshots):
        self.event = event
        self.fold_rows = list(fold_rows)
        self.snapshots = list(snapshots)
        #: Every id set the route asked `win_prob_snapshots` for, so a test can
        #: assert the WIDENING itself and not only its visible effect.
        self.win_prob_id_filters: list[set] = []

    @staticmethod
    def _requested_ids(statement):
        """The event ids this statement actually asked for.

        🔴 THE RIG HONOURS THE FILTER, and that is what makes the fold
        load-bearing here. A fake that hands back every snapshot regardless
        answers an unfolded query with the ghost's rows anyway — so the mutant
        that deletes the ship still passes, which is precisely the hole
        CERT-2208 blocked. `event_id_1` binds the whole list for `.in_()` and
        the scalar for `==`, so both forms are read the same way.
        """
        for key, value in statement.compile().params.items():
            if not key.startswith("event_id"):
                continue
            if isinstance(value, (list, tuple, set)):
                return set(value)
            return {value}
        return None

    async def execute(self, statement, *_a, **_kw):
        sql = " ".join(str(statement).split())

        if "FROM win_prob_snapshots" in sql:
            ids = self._requested_ids(statement)
            self.win_prob_id_filters.append(ids)
            rows = [s for s in self.snapshots if ids is None or s.event_id in ids]
            if "min(" in sql:
                return _Result([min((s.captured_at for s in rows), default=None)])
            return _Result(sorted(rows, key=lambda s: s.captured_at))
        if "FROM odds_snapshots" in sql:
            return _Result([])
        if is_series_fold(sql):
            return _Result(self.fold_rows)
        # #3911: the same route now also folds the BLEND's sources before it
        # pins the chart's right edge. Answered with this module's own rows so
        # nothing here depends on Fold A — the parity itself is
        # `test_blend_fold_chart_pin_parity_3911`.
        if is_blend_fold(sql):
            return _Result([blend_fold_row(self.event)])
        if "FROM events" in sql:
            return _Result([self.event])
        return _Result([])


def _route_event(*, finished=True):
    """The specimen, IN PLAY by default.

    SETTLED BY DEFAULT, because the production specimen is: `15305016` is a
    completed US Open semi-final, and a settled chart is the surface #3810 was
    filed on. The route therefore appends a terminal settlement point (1.0 to
    the winner's side) to every series it draws, which is correct behaviour and
    is asserted here rather than engineered away -- a fixture that avoided it
    would be testing a page no reader opens. `finished=False` is the in-play
    shape, where the route instead carries the last reading forward to now.
    """
    return SimpleNamespace(
        id=CANON_ID,
        status="completed" if finished else "live",
        commence_time=SF_TIME,
        completed_at=SF_TIME + timedelta(hours=2) if finished else None,
        home_team_name="Ben Shelton",
        away_team_name="Stefanos Tsitsipas",
        home_score=3 if finished else None,
        away_score=0 if finished else None,
        sport=SimpleNamespace(key="tennis_atp_us_open"),
        sport_id=S_TENNIS,
        box_score_data=None,
        win_probability_sources={"kalshi": {"value": 0.75}},
    )


def _route_snap(event_id, source, minutes, home_prob):
    return SimpleNamespace(
        event_id=event_id,
        source=source,
        captured_at=SF_TIME + timedelta(minutes=minutes),
        home_win_probability=home_prob,
        away_win_probability=round(1.0 - home_prob, 4),
        draw_probability=None,
        game_state=None,
    )


#: The production shape, one order of magnitude down: the canonical holds a
#: clean Polymarket series, the ghost holds ONE stray Polymarket reading in the
#: middle of it, and the ghost alone holds Kalshi.
def _production_shape():
    return [
        _route_snap(CANON_ID, "polymarket", 0, 0.60),
        _route_snap(GHOST_ID, "polymarket", 1, 0.11),
        _route_snap(CANON_ID, "polymarket", 2, 0.62),
        _route_snap(GHOST_ID, "kalshi", 0, 0.71),
        _route_snap(GHOST_ID, "kalshi", 1, 0.73),
        _route_snap(GHOST_ID, "kalshi", 2, 0.75),
    ]


#: The fold's two rows, oriented in agreement — what production holds for this
#: pair (12/12 agree, measured 2026-09-07).
def _aligned_fold_rows():
    return [
        (CANON_ID, "Ben Shelton", "Stefanos Tsitsipas"),
        (GHOST_ID, "Shelton", "Tsitsipas"),
    ]


async def _real_history(session):
    return await get_event_odds_history(
        event_id=CANON_ID, hours=720, response=MagicMock(headers={}), db=session
    )


#: The route appends this to every series it draws for a SETTLED event -- the
#: winner's side resolved to certainty. Named rather than inlined so each
#: expectation below reads as "the folded readings, then settlement", and so a
#: change to the settlement rule fails these tests loudly instead of shifting a
#: magic number in five places.
SETTLED = 1.0


def _curves(payload):
    """`{source: [home probabilities]}` as the payload actually carries them."""
    return {
        source: [point["home_probability"] for point in points]
        for source, points in (payload.get("win_prob_history") or {}).items()
    }


class TestTheRealRoute:
    """`CHART-SERIES-FOLD-REAL-ROUTE-GUARD-3810`."""

    def test_the_route_returns_the_ghosts_kalshi_and_a_clean_canonical(self):
        """🔴 THE SHIP, through the real route.

        Kalshi is in the payload AT ALL only because the fold reached the ghost,
        and Polymarket is two points rather than three only because one row per
        source was chosen. Both halves, one payload.
        """
        session = _RouteSession(
            _route_event(), _aligned_fold_rows(), _production_shape()
        )
        curves = _curves(asyncio.run(_real_history(session)))

        assert set(curves) == {"polymarket", "kalshi"}
        assert curves["kalshi"] == [0.71, 0.73, 0.75, SETTLED], "the ghost's whole curve"
        assert curves["polymarket"] == [0.60, 0.62, SETTLED], "the 0.11 stray is not spliced in"

    def test_the_route_asked_for_both_ids(self):
        """The wiring itself, not only its effect: an `IN` over the folded set.

        Asserted on the compiled statement because the effect above could in
        principle be produced by a route that read only the canonical and got
        lucky with fixtures — this cannot.
        """
        session = _RouteSession(
            _route_event(), _aligned_fold_rows(), _production_shape()
        )
        asyncio.run(_real_history(session))

        assert session.win_prob_id_filters, "the route never read win_prob_snapshots"
        assert any(
            ids == {CANON_ID, GHOST_ID} for ids in session.win_prob_id_filters
        ), f"the snapshot read was not over the folded set: {session.win_prob_id_filters}"

    def test_the_source_metadata_counts_the_ghosts_rows(self):
        """The legend is built from the same folded history, so `snapshot_count`
        must report the curve that is drawn — a legend that says Kalshi while
        the series is empty is the failure this ship is named for."""
        session = _RouteSession(
            _route_event(), _aligned_fold_rows(), _production_shape()
        )
        payload = asyncio.run(_real_history(session))
        meta = payload.get("win_prob_sources") or {}

        assert meta["kalshi"]["snapshot_count"] == 3
        assert meta["polymarket"]["snapshot_count"] == 2

    # ── mutation proofs ──────────────────────────────────────────────────────
    #
    # The route imports both helpers INSIDE the request (`events.py`, above the
    # try), so patching them here reproduces the two mutants the cert named
    # without writing a mutated file to disk — the shape
    # `test_mutation_guard.test_every_on_disk_harness_is_guarded` says to prefer,
    # and structurally immune to a SIGTERM leaving residue in the tree.

    def test_mutant_unfolded_query_loses_the_kalshi_curve(self, monkeypatch):
        """MUTANT 1 — the folded-ID wiring.

        `folded_series_event_ids` returning `[canonical]` makes the route's
        `.in_(series_event_ids)` compile to exactly the `event_id == event_id`
        read it replaced. That is the cert's mutant, expressed where the route
        actually consumes it. The ship must vanish.
        """
        async def _unfolded(db, canonical_event_id):
            return [canonical_event_id]

        monkeypatch.setattr(
            "app.utils.proven_duplicates.folded_series_event_ids", _unfolded
        )
        session = _RouteSession(
            _route_event(), _aligned_fold_rows(), _production_shape()
        )
        # The fake answers with every snapshot regardless, so this isolates the
        # ROUTE's own selection: with one id folded, the ghost's rows are no
        # longer attributable and Kalshi must leave the chart entirely.
        curves = _curves(asyncio.run(_real_history(session)))

        assert "kalshi" not in curves, (
            "the unfolded route still drew Kalshi — this test cannot tell the "
            "ship from its absence, which is what CERT-2208 blocked"
        )

    def test_mutant_no_per_source_selection_splices_the_stray_point(
        self, monkeypatch
    ):
        """MUTANT 2 — per-source selection.

        Without `series_row_for_each_source` picking ONE row per source, the
        canonical's clean Polymarket line is drawn from two partial recordings
        and the ghost's 0.11 is spliced into the middle of it. Timestamps
        interleave, so the defect is a visible jag rather than an error.
        """

        class _Anything:
            """Equal to every event_id, so the route's skip never fires."""

            def __eq__(self, other):
                return True

            def __ne__(self, other):
                return False

            __hash__ = None

        monkeypatch.setattr(
            "app.utils.proven_duplicates.series_row_for_each_source",
            lambda counts, canonical_event_id: SimpleNamespace(
                get=lambda _source: _Anything()
            ),
        )
        session = _RouteSession(
            _route_event(), _aligned_fold_rows(), _production_shape()
        )
        curves = _curves(asyncio.run(_real_history(session)))

        assert curves["polymarket"] == [0.60, 0.11, 0.62, SETTLED], (
            "expected the un-selected route to splice the stray reading in; if "
            "it did not, this file cannot prove the one-row-per-source rule"
        )

    def test_an_untagged_event_is_unchanged_through_the_real_route(self):
        """The no-change case, through the route rather than beside it: an event
        with no tagged twin returns exactly what it always did."""
        session = _RouteSession(
            _route_event(),
            [(CANON_ID, "Ben Shelton", "Stefanos Tsitsipas")],
            [
                _route_snap(CANON_ID, "polymarket", 0, 0.60),
                _route_snap(CANON_ID, "polymarket", 2, 0.62),
            ],
        )
        curves = _curves(asyncio.run(_real_history(session)))

        assert curves == {"polymarket": [0.60, 0.62, SETTLED]}

    def test_a_swapped_ghost_reaches_the_real_route_not_at_all(self):
        """Orientation, through the route. An inverted ghost must contribute no
        point to any series — a smooth, confident, exactly-backwards curve is
        the one failure mode nothing downstream would catch."""
        session = _RouteSession(
            _route_event(),
            [
                (CANON_ID, "Ben Shelton", "Stefanos Tsitsipas"),
                (GHOST_ID, "Tsitsipas", "Shelton"),
            ],
            _production_shape(),
        )
        curves = _curves(asyncio.run(_real_history(session)))

        assert "kalshi" not in curves, "the swapped ghost's curve was drawn"
        assert curves["polymarket"] == [0.60, 0.62, SETTLED]
