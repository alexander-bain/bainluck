"""#3810 Fold A — the HERO NUMBER reads the rows we declined to print.

The ship, in one sentence: on a twin-paired match the page can now draw Kalshi's
curve (Fold B, shipped) under a big number that had never heard of Kalshi,
because the hero does not read `win_prob_snapshots` at all — it reads the
`win_probability_sources` JSONB on the row being rendered, and on 11 of the 12
measured US Open pairs Kalshi is on the ghost and absent from the canonical.

Three user-visible things read that one dict, which is why the fold is applied
to the DICT and not to the aggregate:

    the hero number       `compute_aggregate_probability`
    the confidence bars   `confidenceFromSources({sourceCount})`   (#490)
    the hero's age stamp  MAX(`updated_at`) across the sources

Folding only the number would light three bars' worth of evidence into a two-bar
hero and date it from the wrong set, so all three move together or none do.

## Two boundaries this file pins ON PURPOSE, because they look like bugs

1. 🔴 **A COMPLETED pair does not move its hero, and that is correct.**
   `_EXCLUDE_WHEN_COMPLETED = {"kalshi", "polymarket"}` drops both venues from
   the blend once a game is over. Every one of the 12 pairs in the issue is
   finished now, so a reader who folds them expecting the number to change will
   find it does not. Acceptance 1 asks for the folded readings to be weighted
   "exactly as `compute_aggregate_probability` would have weighted them had they
   arrived on the canonical" — and had they arrived on a completed canonical,
   they would have been excluded. The fold supplies the dict; the aggregator
   keeps every rule it had. `test_a_completed_pair_lists_kalshi_and_does_not_reblend`
   is that boundary, asserted rather than left for someone to rediscover.

2. 🔴 **A weighted MEDIAN is robust, so gaining a 0.8-weight venue usually will
   not move a hero that already has `betting` at 3.0.** The number changes where
   the canonical had little or nothing — which is exactly the population this
   issue is about (`15305578` and `15305579` hold no win-prob readings at all).
   `test_a_folded_venue_joins_the_evidence_without_moving_a_well_sourced_hero`
   pins that, so nobody "fixes" the fold by making it overwrite.

## Why the route tests exist at all

CERT-2208 blocked Fold B for having none: a composed test proves the helpers
compose, never that the caller calls them. Mutating the route back to
`compute_aggregate_probability(event)` deletes this entire ship and leaves every
pure test below green. So the second half of this file drives the real
`get_event` and asserts on the payload a reader's browser receives.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app.models.models import Base, Event, Sport
from app.services.anchor_channel import duplicate_tag
from app.utils.aggregation import compute_aggregate_probability
from app.utils.proven_duplicates import (
    FoldedBlendView,
    folded_probability_sources,
    merge_probability_sources,
)


# DDL shims so `Base.metadata.create_all` can build the real schema on SQLite —
# the same pair `test_series_fold_3810` declares, for the same reason: the fold's
# Postgres arm is an `@>` operator, so the portable arm has to be exercised
# against a real engine rather than a mock.
@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


# The production pair this fold is aimed at: the semi-final that had not been
# played when #3810 was filed, whose live Kalshi readings accumulate on the ghost.
CANON_ID = 15306813  # Ben Shelton v Carlos Alcaraz — the row the page renders
GHOST_ID = 15306391  # Shelton v Alcaraz — the row holding Kalshi
S_TENNIS = 77
SF_TIME = datetime(2026, 9, 9, 0, 30, tzinfo=timezone.utc)
STAMP = "2026-09-08T23:55:00+00:00"


# ── The pure merge ───────────────────────────────────────────────────────────


class TestMergeProbabilitySources:
    def test_a_source_only_the_twin_holds_is_folded_in(self):
        """THE SHIP, at the smallest scale: Kalshi reaches the canonical's dict."""
        merged = merge_probability_sources(
            {"betting": 0.24}, [(GHOST_ID, {"kalshi": {"value": 0.31}})]
        )
        assert merged == {"betting": 0.24, "kalshi": {"value": 0.31}}

    def test_the_canonical_reading_wins_and_is_never_overwritten(self):
        """🔴 GAP-FILL, not "richest wins".

        A series has a size, so two partial recordings can be compared. A
        point-in-time reading has none — there is nothing to prefer the twin's
        copy ON — so the canonical's own number stands and the fold stays
        strictly additive. If this ever inverts, a page rendering a correct
        number today can have it silently replaced by a suppressed row's.
        """
        merged = merge_probability_sources(
            {"kalshi": 0.55}, [(GHOST_ID, {"kalshi": 0.31})]
        )
        assert merged == {"kalshi": 0.55}

    def test_a_json_null_reading_is_a_gap_and_is_filled(self):
        """🔴 Presence of the KEY is not presence of a reading.

        A `None` write stores JSON `null`, which is a present key carrying
        nothing — and `COUNT` counts it, which is how this class of gap stays
        invisible. A fold that tested `key in sources` would decline to fill the
        very hole it exists for.
        """
        merged = merge_probability_sources(
            {"kalshi": None}, [(GHOST_ID, {"kalshi": 0.31})]
        )
        assert merged == {"kalshi": 0.31}

    def test_a_twins_unreadable_entry_is_not_folded(self):
        """The mirror: a twin offering `null` supplies nothing to fill with."""
        merged = merge_probability_sources(
            {"betting": 0.24}, [(GHOST_ID, {"kalshi": None})]
        )
        assert merged == {"betting": 0.24}

    def test_content_arrays_in_the_same_jsonb_bag_are_not_folded(self):
        """🔴 `win_probability_sources` is a shared bag, not a source list.

        It also carries `statpal_plays` and `statpal_injuries` as ARRAYS and
        `_`-prefixed metadata. Those are content: moving one row's play-by-play
        onto another row is a different question with different correctness, and
        `_format_event` would try to serialise a list where a reading belongs.
        Only keys the aggregator actually weights are folded.
        """
        merged = merge_probability_sources(
            {"betting": 0.24},
            [(GHOST_ID, {"statpal_plays": [{"x": 1}], "_meta": "z", "kalshi": 0.31})],
        )
        assert merged == {"betting": 0.24, "kalshi": 0.31}

    def test_two_twins_offering_one_source_resolve_deterministically(self):
        """The hero must not depend on the order the database returned rows in."""
        twins = [
            (GHOST_ID + 5, {"kalshi": 0.90}),
            (GHOST_ID, {"kalshi": 0.31}),
        ]
        assert merge_probability_sources({}, twins) == {"kalshi": 0.31}
        assert merge_probability_sources({}, list(reversed(twins))) == {"kalshi": 0.31}

    def test_no_twins_returns_the_canonicals_own_dict(self):
        """The no-change case, and it is the overwhelming majority of pages."""
        assert merge_probability_sources({"betting": 0.24}, []) == {"betting": 0.24}

    def test_a_null_column_folds_to_a_plain_dict(self):
        """`win_probability_sources` is nullable; the caller must still get a dict."""
        assert merge_probability_sources(None, []) == {}

    def test_the_canonicals_dict_is_not_mutated(self):
        """The fold is a READ. It may not edit the ORM row's own JSONB in place —
        that object is live in an async session and a later flush would persist
        it, which acceptance 4 forbids."""
        original = {"betting": 0.24}
        merge_probability_sources(original, [(GHOST_ID, {"kalshi": 0.31})])
        assert original == {"betting": 0.24}


# ── The view that carries it to the aggregator ───────────────────────────────


class TestFoldedBlendView:
    def test_it_serves_the_folded_sources_and_proxies_everything_else(self):
        event = Event(
            id=CANON_ID,
            sport_id=S_TENNIS,
            home_team_name="Ben Shelton",
            away_team_name="Carlos Alcaraz",
            commence_time=SF_TIME,
            status="scheduled",
            win_probability_sources={"betting": 0.24},
        )
        view = FoldedBlendView(event, {"betting": 0.24, "kalshi": 0.31})

        assert view.win_probability_sources == {"betting": 0.24, "kalshi": 0.31}
        assert view.status == "scheduled"
        assert view.home_team_name == "Ben Shelton"

    def test_it_cannot_write_the_fold_back_onto_the_event(self):
        """🔴 Acceptance 4, structurally.

        Ruling 048 permits reading a ghost's content onto the page and does not
        permit `UPDATE events SET win_probability_sources`. Assigning the merged
        dict onto the ORM row is the obvious way to fold every reader at once and
        is exactly the thing that must not happen. A wrapper makes that a
        property of the type rather than a rule a future editor has to know.
        """
        event = Event(
            id=CANON_ID,
            sport_id=S_TENNIS,
            home_team_name="Ben Shelton",
            away_team_name="Carlos Alcaraz",
            commence_time=SF_TIME,
            status="scheduled",
            win_probability_sources={"betting": 0.24},
        )
        FoldedBlendView(event, {"betting": 0.24, "kalshi": 0.31})

        assert event.win_probability_sources == {"betting": 0.24}

    def test_a_missing_attribute_raises_rather_than_recursing(self):
        """The proxy's `__getattr__` must not loop on a half-built object."""
        view = FoldedBlendView(object(), {})
        with pytest.raises(AttributeError):
            view.no_such_attribute


# ── The fold against a real engine (orientation) ─────────────────────────────


class _SyncAsAsync:
    """`folded_probability_sources` is async because every caller is.

    The statement is ordinary Core, so this runs it against a real engine rather
    than asserting on a mock's call args — the device `test_series_fold_3810`
    uses, for the same reason: a fold test that inspects a mock cannot tell a
    working predicate from a typo'd one.
    """

    def __init__(self, session):
        self._session = session

    async def execute(self, statement):
        return self._session.execute(statement)


def _event(id, *, home, away, sources=None, tags=None):
    return Event(
        id=id,
        sport_id=S_TENNIS,
        home_team_name=home,
        away_team_name=away,
        commence_time=SF_TIME,
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


def _folded(eng, event_id):
    with Session(eng) as s:
        event = s.get(Event, event_id)
        return asyncio.run(folded_probability_sources(_SyncAsAsync(s), event))


class TestFoldedProbabilitySources:
    def test_the_canonical_gains_the_ghosts_kalshi(self):
        """THE SHIP, through the real predicate against a real engine."""
        eng = _engine(
            _event(CANON_ID, home="Ben Shelton", away="Carlos Alcaraz",
                   sources={"betting": 0.24}),
            _event(GHOST_ID, home="Shelton", away="Alcaraz",
                   sources={"kalshi": 0.31}, tags=[duplicate_tag(CANON_ID)]),
        )
        assert _folded(eng, CANON_ID) == {"betting": 0.24, "kalshi": 0.31}

    def test_an_untagged_event_folds_to_exactly_its_own_sources(self):
        """Acceptance 3's no-change half, at the fold itself."""
        eng = _engine(
            _event(CANON_ID, home="Ben Shelton", away="Carlos Alcaraz",
                   sources={"betting": 0.24}),
        )
        assert _folded(eng, CANON_ID) == {"betting": 0.24}

    def test_a_swapped_twin_is_refused(self):
        """🔴 Orientation, and the hazard is sharper here than on the chart.

        A `win_probability_sources` entry is a HOME win probability, a number
        whose meaning comes from its own row's `home_team_name`. Fold a twin that
        disagrees about which player is home and the page prints one player's
        number under the other's name — a single confident percentage, with no
        curve shape for a reader to notice is wrong.
        """
        eng = _engine(
            _event(CANON_ID, home="Ben Shelton", away="Carlos Alcaraz",
                   sources={"betting": 0.24}),
            _event(GHOST_ID, home="Alcaraz", away="Shelton",
                   sources={"kalshi": 0.31}, tags=[duplicate_tag(CANON_ID)]),
        )
        assert _folded(eng, CANON_ID) == {"betting": 0.24}

    def test_a_tag_naming_a_different_canonical_is_not_folded(self):
        """The control: the TAG is the only route to the twin's readings.

        Same sport, same names, same time — only `event_tags` differs. If this
        ever starts folding, the fold has found a name/time route to the ghost,
        which is the absorption ruling 048 bans.
        """
        eng = _engine(
            _event(CANON_ID, home="Ben Shelton", away="Carlos Alcaraz",
                   sources={"betting": 0.24}),
            _event(GHOST_ID, home="Shelton", away="Alcaraz",
                   sources={"kalshi": 0.31}, tags=[duplicate_tag(CANON_ID + 1)]),
        )
        assert _folded(eng, CANON_ID) == {"betting": 0.24}


# ── THE REAL ROUTE ───────────────────────────────────────────────────────────
#
# 🔴 Everything above proves the helpers work. None of it would fail if
# `get_event` never called them — mutate the route back to
# `compute_aggregate_probability(event)` and `_format_event(event, ...)` and the
# whole ship vanishes with every test above still green. That is the trap
# CERT-2208 blocked Fold B for, so these drive the real route.

#: The blend fold's exact projection, and the predicate for it, now live in
#: `test_series_fold_3810` — the rig-support module the history-route rigs
#: already import. The adjacency this comment used to warn about ("a future rig
#: driving both routes would silently route one into the other's arm") stopped
#: being hypothetical with the #3911 repair, which put both folds on
#: `get_event_odds_history`: it cost four red tests in that module. The fix is
#: at the source — `is_series_fold` is now EXCLUSIVE of this projection — so a
#: rig inherits the distinction instead of having to know about it.
from tests.test_series_fold_3810 import is_blend_fold  # noqa: E402


class _Result:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)

    def scalars(self):
        return self

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class _RouteSession:
    """Answers the reads `get_event` makes, keyed on what each statement reads."""

    def __init__(self, event, twin_rows):
        self.event = event
        self.twin_rows = list(twin_rows)
        #: Every fold lookup the route issued, so a test can assert the WIRING
        #: and not only its visible effect.
        self.fold_lookups = 0

    async def execute(self, statement, *_a, **_kw):
        sql = " ".join(str(statement).split())

        # The blend fold, tested BEFORE the entity lookup: both read `events`.
        if is_blend_fold(sql):
            self.fold_lookups += 1
            return _Result(self.twin_rows)
        if "FROM events" in sql and "odds_snapshots" not in sql:
            return _Result([self.event])
        return _Result([])


def _route_event(*, status="scheduled", sources=None, finished=False):
    """The specimen. SCHEDULED by default — where the hero can actually move.

    Every one of the 12 pairs in the issue is finished now, and on a finished
    game `_EXCLUDE_WHEN_COMPLETED` drops kalshi and polymarket from the blend.
    So a fixture that defaulted to `completed` would be testing a page whose
    number this ship cannot change, and would pass just as well with the fold
    deleted.
    """
    return Event(
        id=CANON_ID,
        sport_id=S_TENNIS,
        home_team_name="Ben Shelton",
        away_team_name="Carlos Alcaraz",
        commence_time=SF_TIME,
        status=status,
        home_score=3 if finished else None,
        away_score=0 if finished else None,
        completed_at=SF_TIME + timedelta(hours=2) if finished else None,
        win_probability_sources=sources,
    )


def _aligned_twin(sources):
    """The twin row as the fold's own projection returns it, oriented in
    agreement — what production holds for this class (12/12 agree, 2026-09-07)."""
    return [(GHOST_ID, "Shelton", "Alcaraz", sources)]


@pytest.fixture()
def serve(monkeypatch):
    """`get_event` with its heavy reads stubbed, returning the real payload."""
    from app.models.models import Sport
    from app.routes import events as events_route

    events_route._event_detail_cache.clear()

    async def _no_percentiles(_db):
        return {}

    async def _no_teams(_db, _names):
        return {}

    async def _no_drain(_db, _event_id):
        return None

    monkeypatch.setattr(events_route, "_load_gei_percentiles", _no_percentiles)
    monkeypatch.setattr(events_route, "_build_team_lookup", _no_teams)
    monkeypatch.setattr(events_route, "resolve_market_born_duplicate", _no_drain)

    def _serve(event, twin_rows):
        event.sport = Sport(id=S_TENNIS, key="tennis_atp_us_open", name="US Open")
        events_route._event_detail_cache.clear()
        session = _RouteSession(event, twin_rows)
        payload = asyncio.run(events_route.get_event(CANON_ID, db=session))
        return payload, session

    return _serve


class TestTheRealRoute:
    def test_the_hero_appears_at_all_because_the_twin_had_the_only_readings(
        self, serve
    ):
        """🔴 THE SHIP, through the real route.

        The sharpest form, and it is a real shape rather than a contrived one:
        `15305578` and `15305579` hold NO win-prob readings whatsoever while
        their ghosts hold both venues. Unfolded, tier 1 is empty and the page
        publishes no hero at all. Folded, the reader gets a number.
        """
        payload, _ = serve(
            _route_event(sources=None),
            _aligned_twin({"kalshi": {"value": 0.31, "updated_at": STAMP}}),
        )

        assert payload["hero_probability"] == 0.31
        assert "kalshi" in payload["win_probability_sources"]

    def test_the_source_list_carries_the_twins_venue_and_its_stamp(self, serve):
        """The confidence bars (#490) and the age stamp read this list.

        `sourceCount` drives `confidenceFromSources` and MAX(`updated_at`) dates
        the hero, so a fold that moved the number and left this behind would
        under-count the evidence and date it from the wrong set.
        """
        payload, _ = serve(
            _route_event(sources={"betting": 0.24}),
            _aligned_twin({"kalshi": {"value": 0.31, "updated_at": STAMP}}),
        )
        sources = payload["win_probability_sources"]

        assert set(sources) == {"betting", "kalshi"}
        assert sources["kalshi"]["value"] == 0.31
        assert sources["kalshi"]["updated_at"] == STAMP

    def test_the_route_issued_the_fold_lookup(self, serve):
        """The wiring itself: the effect above could in principle come from a
        fixture accident, a missing lookup cannot."""
        _, session = serve(
            _route_event(sources={"betting": 0.24}),
            _aligned_twin({"kalshi": 0.31}),
        )
        assert session.fold_lookups == 1

    def test_a_folded_venue_joins_the_evidence_without_moving_a_well_sourced_hero(
        self, serve
    ):
        """🔴 BOUNDARY 2, pinned so nobody "fixes" it by overwriting.

        The blend is a weighted MEDIAN, deliberately outlier-resistant. Kalshi at
        0.8 cannot move a hero that already rests on `betting` at 3.0 — so on a
        canonical that is already well sourced the honest outcome is that the
        venue joins the evidence (the legend, the bars, the stamp) and the number
        stands. Reading that as a broken fold and making the twin overwrite is
        how this ship would turn into a regression.
        """
        unfolded, _ = serve(_route_event(sources={"betting": 0.24}), [])
        folded, _ = serve(
            _route_event(sources={"betting": 0.24}),
            _aligned_twin({"kalshi": 0.31}),
        )

        assert unfolded["hero_probability"] == folded["hero_probability"] == 0.24
        assert "kalshi" not in unfolded["win_probability_sources"]
        assert "kalshi" in folded["win_probability_sources"]

    def test_a_completed_pair_lists_kalshi_and_does_not_reblend(self, serve):
        """🔴 BOUNDARY 1 — and every pair in the issue is now in this state.

        `_EXCLUDE_WHEN_COMPLETED` drops kalshi and polymarket from a finished
        game's blend. Acceptance 1 asks for the folded readings to be weighted
        exactly as they would have been HAD THEY ARRIVED ON THE CANONICAL — and
        on a completed canonical they would have been excluded. So the fold hands
        the aggregator the merged dict and the aggregator keeps every rule it
        had. A reader checking `/events/15305016` expecting the number to move
        will find it does not, and that is the correct behaviour, not a failure
        of the wiring.
        """
        payload, session = serve(
            _route_event(status="completed", finished=True, sources={"espn": 0.62}),
            _aligned_twin({"kalshi": 0.31}),
        )

        assert session.fold_lookups == 1, "the fold still ran"
        assert "kalshi" in payload["win_probability_sources"], "the venue is listed"
        # A completed game resolves its hero from the SCORE (`resolve_settled_hero`),
        # which outranks the blend entirely — so assert the blend directly.
        assert compute_aggregate_probability(
            FoldedBlendView(
                _route_event(status="completed", finished=True,
                             sources={"espn": 0.62}),
                {"espn": 0.62, "kalshi": 0.31},
            )
        ) == 0.62

    def test_an_untagged_event_is_unchanged_through_the_real_route(self, serve):
        """Acceptance 3, through the route: no tagged twin, no difference."""
        payload, _ = serve(_route_event(sources={"betting": 0.24}), [])

        assert payload["hero_probability"] == 0.24
        assert set(payload["win_probability_sources"]) == {"betting"}

    def test_a_swapped_twin_reaches_the_real_route_not_at_all(self, serve):
        """Orientation, through the route. An inverted twin must contribute
        nothing — a single confident percentage under the wrong player's name is
        the one failure mode nothing downstream would catch."""
        payload, _ = serve(
            _route_event(sources={"betting": 0.24}),
            [(GHOST_ID, "Alcaraz", "Shelton", {"kalshi": 0.31})],
        )

        assert set(payload["win_probability_sources"]) == {"betting"}
        assert payload["hero_probability"] == 0.24

    # ── mutation proofs ──────────────────────────────────────────────────────
    #
    # The route imports the helpers INSIDE the request, so patching them here
    # reproduces each mutant without writing a mutated file to disk — the shape
    # `test_mutation_guard` prefers, and structurally immune to a SIGTERM
    # leaving residue in the tree.

    def test_mutant_unfolded_blend_loses_the_hero_entirely(self, serve, monkeypatch):
        """MUTANT 1 — the fold itself.

        `folded_probability_sources` returning the canonical's own dict makes the
        route compile to exactly the `compute_aggregate_probability(event)` read
        it replaced. The ship must vanish.
        """

        async def _unfolded(_db, event):
            return event.win_probability_sources or {}

        monkeypatch.setattr(
            "app.utils.proven_duplicates.folded_probability_sources", _unfolded
        )
        payload, _ = serve(
            _route_event(sources=None),
            _aligned_twin({"kalshi": {"value": 0.31, "updated_at": STAMP}}),
        )

        assert payload.get("hero_probability") is None, (
            "the unfolded route still published a hero — this test cannot tell "
            "the ship from its absence, which is what CERT-2208 blocked"
        )
        assert "win_probability_sources" not in payload

    def test_mutant_hero_reading_the_raw_event_ignores_the_fold(
        self, serve, monkeypatch
    ):
        """MUTANT 2 — the HERO's own seam, which mutant 1 cannot reach.

        The fold could run correctly and reach `_format_event` (so the source
        list looks folded) while the hero was still computed from the raw row.
        That is the half-fold this ship exists to avoid: a two-source legend over
        a number blended from one. Patching the aggregator to read `_event`
        reproduces `compute_aggregate_probability(event)` precisely.

        🔴 TWO bindings are patched because the name resolves in two modules,
        and the `hero_probability` one is the load-bearing half — MEASURED, not
        assumed: drop it and this test passes while the hero is still folded
        (it did exactly that when #3903 landed). Since #3903 the hero cascade
        lives in `app.utils.hero_probability.resolve_hero`, which does a
        MODULE-LEVEL `from app.utils.aggregation import
        compute_aggregate_probability`, so its binding is captured at import and
        patching the `aggregation` module alone never reaches it.

        The `aggregation` patch is kept anyway, and NOT because this test's
        assertions need it — dropping it alone leaves this test green. It is
        kept so the mutant is a faithful reproduction: `routes/events.py`
        imports the same function inside the request function to compute
        `agg_prob`, which still feeds `current_odds` and `hero_home_prob`. A
        mutant that flipped the hero to the raw row while leaving those folded
        would be a state the codebase cannot actually be in, and a control that
        models an impossible state is not a control.
        """
        real = compute_aggregate_probability

        def _ignores_the_fold(event, event_status=None):
            raw = getattr(event, "_event", event)
            return real(raw, event_status)

        monkeypatch.setattr(
            "app.utils.aggregation.compute_aggregate_probability", _ignores_the_fold
        )
        monkeypatch.setattr(
            "app.utils.hero_probability.compute_aggregate_probability",
            _ignores_the_fold,
        )
        payload, _ = serve(
            _route_event(sources=None),
            _aligned_twin({"kalshi": {"value": 0.31, "updated_at": STAMP}}),
        )

        assert payload.get("hero_probability") is None, (
            "the hero was computed from the folded view even when the aggregator "
            "was made to read the raw row — this test proves nothing"
        )
        # The fold still reached the source list, which is exactly why the hero
        # needs its own mutant: mutant 1 would not have caught this.
        assert "kalshi" in payload["win_probability_sources"]
