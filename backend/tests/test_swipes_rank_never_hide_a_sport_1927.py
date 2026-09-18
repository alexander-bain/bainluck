"""#1927, wide half — swipes rank; they don't hide a sport. The unit-level half.

Alex's ruling, 2026-09-17: "a nah swipe should NOT hide the whole sport. I hate
the Yankees baseball team, and would be likely to swipe away any game card from
the Yankees, but wouldn't intend that to mean that I don't like baseball at all.
Swiping needs to be a ranking signal, not a death certificate."

What shipped (BRIEF-24):

* the sport "Nah" term — explicit `<= NAH_AFFINITY_THRESHOLD` OR a sport absent
  from the reader's affinities — is RANK-ONLY. It still carries the full
  `NAH_AFFINITY_PENALTY` in `multiplier`; it is held out of
  `admission_multiplier` exactly as CERT-2676/2681 hold out the swipe terms;
* the two `continue`-on-`sport_nah` hard filters in `routes/feed.py` (event
  gate, Discover futures gate) are retired, and `_score_golf_tournaments` no
  longer deletes tournaments in a Nah'd or absent tour;
* ONE dial (`sport_affinity_term`) is read by all four sports card types —
  events, futures, concepts (UFC/F1/cycling) and golf tournaments — the last two
  through `_rank_keyed_items_by_sport_affinity` on the viewer's side of the
  principal-independent cache;
* "if it's wild" (`sport_suppress`) keeps its existing interpretation: its
  penalty stays inside the admission number and the 55 bar still reads it.

The route-level half, on a real Postgres through the real dependencies, is
`tests/integration/test_feed_swipes_rank_never_hide_a_sport_1927_pg.py`.

Controls are written to be discriminating: the Nah made INERT fails the rank
assertions; the Nah left EXCLUDING fails the admission assertions; "if it's
wild" made rank-only fails its bar; the keyed-item pass mutating the shared
list in place fails the identity assertion.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routes import feed as feed_module
from app.routes.feed import (
    _discover_admission_score,
    _keyed_item_sport_identity,
    _rank_keyed_items_by_sport_affinity,
    _score_events,
    _score_golf_tournaments,
)
from app.utils.personalization import (
    FOLLOW_BONUS,
    HIGH_AFFINITY_BONUS,
    LOCAL_BONUS,
    LOW_AFFINITY_PENALTY,
    MIN_MULTIPLIER,
    NAH_AFFINITY_PENALTY,
    NAH_AFFINITY_THRESHOLD,
    STANDING_TEAM_RELATIONSHIPS,
    PersonalizationContext,
    compute_event_multiplier,
    compute_futures_multiplier,
    compute_sport_affinity_multiplier,
    sport_affinity_term,
)

NOW = datetime(2026, 9, 17, 22, 50, 0, tzinfo=timezone.utc)
MLB = "baseball_mlb"
NBA = "basketball_nba"
NAH, IF_WILD, SOMETIMES, LOVE = 0.0, 0.1, 0.3, 1.0

#: The gate bars as written in `routes/feed.py` — the event floor for a reader
#: whose multiplier is below 1.0, the futures floor, and the "if it's wild" bar.
EVENT_FLOOR = 30
FUTURES_FLOOR = 15
WILD_BAR = 55
BASE_SCORES = (40, 60, 98)

HOME, AWAY = 4101, 4202


def _ctx(affinities=None, relations=None, **kw):
    return PersonalizationContext(
        is_authenticated=True,
        sport_affinities=dict(affinities or {}),
        team_relations={HOME: set(relations)} if relations else {},
        team_weights={HOME: 1.0} if relations else {},
        **kw,
    )


def _event(ctx, sport_key=MLB, **kw):
    return compute_event_multiplier(ctx, HOME, AWAY, sport_key, **kw)


def _futures(ctx, sport_key=MLB, category="baseball", **kw):
    return compute_futures_multiplier(
        ctx, category, [HOME], futures_market_id=None, sport_key=sport_key, **kw
    )


# ==========================================================================
# 1. The dial: four distinct states, one contract
# ==========================================================================


class TestTheFourStatesAreDistinctAndNoneOfThemExcludes:
    """Stored Nah, missing preference, "if it's wild" and explicit interest are
    four states; only "if it's wild" is allowed to reach an admission bar."""

    @pytest.mark.parametrize("scorer", [_event, _futures])
    def test_an_explicit_nah_ranks_down_and_admits_at_neutral(self, scorer):
        r = scorer(_ctx({MLB: NAH, NBA: LOVE}))
        assert r.sport_nah is True
        assert any(x.startswith("sport_nah") for x in r.reasons), r.reasons
        assert r.multiplier == pytest.approx(1.0 + NAH_AFFINITY_PENALTY)
        assert r.admission_multiplier == pytest.approx(1.0)

    @pytest.mark.parametrize("scorer", [_event, _futures])
    def test_a_missing_preference_is_the_implicit_nah_and_admits_at_neutral(
        self, scorer
    ):
        """"Missing preference is not an explicit rejection" (BRIEF-24). It
        ranks like a Nah — the reader went through onboarding and did not pick
        the sport — and, like a Nah, it excludes nothing."""
        r = scorer(_ctx({NBA: LOVE}))
        assert r.sport_nah is True
        assert r.multiplier == pytest.approx(1.0 + NAH_AFFINITY_PENALTY)
        assert r.admission_multiplier == pytest.approx(1.0)

    @pytest.mark.parametrize("scorer", [_event, _futures])
    def test_if_its_wild_keeps_its_penalty_inside_the_admission_number(self, scorer):
        """The separate explicit control retains its existing interpretation:
        a higher bar. Its penalty is NOT lifted out."""
        r = scorer(_ctx({MLB: IF_WILD}))
        assert r.sport_nah is False
        assert any(x.startswith("sport_suppress") for x in r.reasons), r.reasons
        assert r.multiplier == pytest.approx(1.0 + LOW_AFFINITY_PENALTY)
        assert r.admission_multiplier == pytest.approx(1.0 + LOW_AFFINITY_PENALTY)

    @pytest.mark.parametrize("scorer", [_event, _futures])
    def test_explicit_interest_boosts_both_numbers(self, scorer):
        r = scorer(_ctx({MLB: LOVE}))
        assert r.sport_nah is False
        assert r.multiplier == pytest.approx(1.0 + HIGH_AFFINITY_BONUS)
        assert r.admission_multiplier == pytest.approx(1.0 + HIGH_AFFINITY_BONUS)

    @pytest.mark.parametrize("scorer", [_event, _futures])
    def test_sometimes_is_neutral(self, scorer):
        r = scorer(_ctx({MLB: SOMETIMES}))
        assert r.multiplier == pytest.approx(1.0)
        assert r.sport_nah is False

    def test_the_nah_specimen_really_is_a_nah(self):
        assert NAH <= NAH_AFFINITY_THRESHOLD < IF_WILD

    def test_the_dial_is_silent_for_a_reader_with_no_affinities(self):
        """Signed in, never onboarded: not a Nah on everything."""
        assert sport_affinity_term(_ctx({}), sport_key=MLB) == (0.0, None)
        assert _event(_ctx({})).sport_nah is False

    def test_the_dial_is_silent_for_an_anonymous_reader(self):
        assert _event(PersonalizationContext()) == compute_event_multiplier(
            PersonalizationContext(), HOME, AWAY, MLB
        )
        assert _event(PersonalizationContext()).multiplier == 1.0

    def test_the_dial_is_silent_for_a_non_sports_future(self):
        """Queue #255 Item 2 preserved through the refactor: politics is not a
        sport the reader skipped."""
        r = compute_futures_multiplier(_ctx({NBA: LOVE}), "politics", [], sport_key=None)
        assert not any(x.startswith("sport_") for x in r.reasons), r.reasons
        assert r.sport_nah is False


class TestTheAdmissionInvariant:
    """For a reader whose only NEGATIVE signal is a sport Nah — with or without
    swipes on top — the admission number is exactly 1.0."""

    def test_nah_alone(self):
        assert _event(_ctx({MLB: NAH})).admission_multiplier == 1.0
        assert _futures(_ctx({MLB: NAH})).admission_multiplier == 1.0

    def test_nah_plus_eight_swipes_worth_of_category_dismissal(self):
        ctx = _ctx(
            {MLB: NAH},
            discover_category_affinities={"baseball": -0.80},
            discover_category_negative_counts={"baseball": 8},
        )
        r = _event(ctx)
        assert r.multiplier == pytest.approx(MIN_MULTIPLIER)  # clamped: -0.6 - 0.8
        assert r.admission_multiplier == pytest.approx(1.0)

    @pytest.mark.parametrize("base", BASE_SCORES)
    def test_no_nah_reaches_the_event_floor(self, base):
        r = _event(_ctx({MLB: NAH}))
        assert min(98, int(base * r.multiplier)) < base  # it ranks down
        assert _discover_admission_score(base, r) >= EVENT_FLOOR  # it is admitted

    @pytest.mark.parametrize("base", BASE_SCORES)
    def test_no_nah_reaches_the_futures_floor(self, base):
        r = _futures(_ctx({MLB: NAH}))
        assert min(98, int(base * r.multiplier)) < base
        assert _discover_admission_score(base, r) >= FUTURES_FLOOR
        # and the recycled variant — the recycle penalty is a real serving floor
        # and stays applied; it is not fed the Nah.
        assert _discover_admission_score(base, r, recycled=True) == max(
            1, base - feed_module.FEED_RECYCLE_PENALTY
        )

    def test_if_its_wild_still_faces_the_bar(self):
        """CONTROL: a real eligibility rule that also uses a score is kept."""
        r = _event(_ctx({MLB: IF_WILD}))
        assert _discover_admission_score(70, r) < WILD_BAR
        assert _discover_admission_score(98, r) >= WILD_BAR

    def test_the_red_arithmetic_this_repair_retired(self):
        """What the base tree computed: `base * (1 + NAH)` at the gate. Pinned
        so the test above cannot go green for a vacuous reason."""
        for base in BASE_SCORES:
            assert int(base * (1.0 + NAH_AFFINITY_PENALTY)) < base
        assert int(60 * (1.0 + NAH_AFFINITY_PENALTY)) < EVENT_FLOOR


# ==========================================================================
# 2. Standing relationships, rivals — the narrow #1927 fix, preserved
# ==========================================================================


class TestStandingRelationshipsStillWinAndRivalsAreNotFavourites:
    @pytest.mark.parametrize("relation", sorted(STANDING_TEAM_RELATIONSHIPS))
    def test_a_performed_relationship_in_a_nah_sport_still_nets_a_boost_or_rescue(
        self, relation
    ):
        r = _event(_ctx({MLB: NAH}, {relation}))
        assert r.has_standing_team_relationship is True
        assert r.sport_nah is True
        unrelated = _event(_ctx({MLB: NAH}))
        assert r.multiplier > unrelated.multiplier

    def test_follow_beats_the_nah_outright(self):
        r = _event(_ctx({MLB: NAH}, {"follow"}))
        assert r.multiplier == pytest.approx(1.0 + FOLLOW_BONUS + NAH_AFFINITY_PENALTY)
        assert r.multiplier > 1.0

    def test_local_in_a_nah_sport_is_the_measured_0_70(self):
        """The after-check's own number for account-shaped state (issue #1927
        comment): `1 + 0.30 - 0.60 = 0.70`. Ranked below neutral, served."""
        r = _event(_ctx({MLB: NAH}, {"local"}))
        assert r.multiplier == pytest.approx(1.0 + LOCAL_BONUS + NAH_AFFINITY_PENALTY)
        assert r.admission_multiplier == pytest.approx(1.0 + LOCAL_BONUS)

    def test_a_rival_is_not_a_standing_relationship(self):
        r = _event(_ctx({MLB: NAH}, {"rival"}))
        assert r.has_standing_team_relationship is False
        assert any(x.startswith("rival_") for x in r.reasons)


# ==========================================================================
# 3. The event gate, driven through the real `_score_events`
# ==========================================================================


def _sport(key=MLB):
    s = MagicMock()
    s.key = key
    s.name = key
    return s


def _game(event_id=1, importance="regular", sport_key=MLB, raw_ei=0.95):
    e = MagicMock()
    e.id = event_id
    e.status = "completed"
    e.commence_time = NOW - timedelta(hours=4)
    e.completed_at = NOW - timedelta(hours=1)
    e.statpal_end_time = None
    e.home_team_id = HOME
    e.away_team_id = AWAY
    e.home_team_name = "Red Sox"
    e.away_team_name = "Yankees"
    e.opening_home_probability = 0.20
    e.opening_away_probability = 0.80
    e.win_probability_sources = {"betting": {"home_probability": 0.95}}
    e.opening_home_spread = -3.5
    e.opening_over_under = 8.5
    e.opening_favorite = "Yankees"
    e.llm_importance = importance
    e.llm_gender = None
    e.llm_level = None
    e.llm_league = None
    e.sport = _sport(sport_key)
    e.period = None
    e.raw_ei = raw_ei
    e.ei_metadata = None
    e.home_score = 7
    e.away_score = 2
    e.external_id = f"ext-{event_id}"
    e.game_clock = None
    e.broadcast_info = None
    e.event_tags = []
    return e


def _mock_db(events):
    db = AsyncMock()

    def make_result(rows):
        r = MagicMock()
        r.scalars.return_value.all.return_value = rows
        r.all.return_value = []
        return r

    async def execute(stmt, *a, **k):
        s = str(stmt).lower()
        if "win_prob_snapshots" in s:
            return make_result([])
        if "events" in s:
            return make_result(events)
        return make_result([])

    db.execute = AsyncMock(side_effect=execute)
    return db


async def _served(ctx, events=None, *, my_teams_only=False):
    with patch(
        "app.routes.feed._get_championship_probabilities",
        new=AsyncMock(return_value={}),
    ):
        return await _score_events(
            _mock_db(events or [_game()]), NOW, None, ctx, my_teams_only=my_teams_only
        )


@pytest.mark.asyncio
async def test_the_event_gate_serves_a_nah_sport_game_with_no_relationship():
    """THE ARM at the event gate. Restoring the `continue` fails exactly this."""
    items = await _served(_ctx({MLB: NAH}))
    assert len(items) == 1, "the Nah deleted the game"
    assert items[0]["personalized"] is True
    assert any(r.startswith("sport_nah") for r in items[0]["personalization_reasons"])


@pytest.mark.asyncio
async def test_the_event_gate_ranks_the_nah_sport_game_below_the_same_game_unpersonalized():
    nah = (await _served(_ctx({MLB: NAH})))[0]
    anon = (await _served(PersonalizationContext()))[0]
    assert nah["score"] < anon["score"], (nah["score"], anon["score"])
    assert nah["_rank_score"] < anon["_rank_score"]


@pytest.mark.asyncio
async def test_the_missing_preference_game_is_served_too():
    items = await _served(_ctx({NBA: LOVE}))
    assert len(items) == 1


@pytest.mark.asyncio
async def test_a_championship_in_a_nah_sport_keeps_its_rank_floor():
    """The one RANK effect the old block had survives: a title game in a Nah
    sport is floored at 35 so it does not sink under the routine slate."""
    items = await _served(_ctx({MLB: NAH}), [_game(importance="championship")])
    assert len(items) == 1
    assert items[0]["score"] >= 35


@pytest.mark.asyncio
async def test_if_its_wild_still_refuses_a_routine_game():
    """CONTROL — a genuine eligibility rule that uses a score is untouched: the
    reader who said "only if it's wild" does not get a routine game."""
    items = await _served(_ctx({MLB: IF_WILD}), [_game(raw_ei=0.50)])
    assert items == [], [i["score"] for i in items]


@pytest.mark.asyncio
async def test_if_its_wild_still_admits_a_wild_one():
    """Vacuity companion for the control above."""
    items = await _served(_ctx({MLB: IF_WILD}), [_game(raw_ei=0.95)])
    assert len(items) == 1


@pytest.mark.asyncio
async def test_my_stuff_is_unchanged():
    assert len(await _served(_ctx({MLB: NAH}, {"rival"}), my_teams_only=True)) == 1


@pytest.mark.asyncio
async def test_the_anonymous_reader_is_unchanged():
    items = await _served(PersonalizationContext())
    assert len(items) == 1
    assert "personalized" not in items[0]


# ==========================================================================
# 4. Keyed cards — UFC concept, golf tournament — through the shared pass
# ==========================================================================


def _concept(domain="ufc", score=60, key="event:ufc:26sep19", **extra):
    return {
        "type": "concept",
        "score": score,
        "reason": "x",
        "headline": None,
        "data": {"key": key, "name": "UFC Fight Night", "domain": domain, **extra},
    }


def _tournament(tour="pga", score=60, key="the_open", **extra):
    return {
        "type": "tournament",
        "score": score,
        "reason": "x",
        "headline": None,
        "data": {"key": key, "name": "The Open", "tour": tour, **extra},
        "_marquee_pin": False,
    }


class TestKeyedCardIdentityComesFromExistingMappings:
    def test_a_ufc_concept_is_mma(self):
        assert _keyed_item_sport_identity(_concept("ufc")) == (None, "mma")

    def test_an_f1_concept_is_motorsports(self):
        assert _keyed_item_sport_identity(_concept("f1")) == (None, "motorsports")

    def test_an_unknown_domain_has_no_identity(self):
        assert _keyed_item_sport_identity(_concept("darts")) == (None, None)

    def test_a_pga_tournament_is_golf_pga(self):
        assert _keyed_item_sport_identity(_tournament("pga")) == ("golf_pga", None)

    def test_the_identity_is_read_from_the_concept_enumeration_not_copied(self):
        from app.utils.event_concept_population import CONCEPT_SOURCES

        for source in CONCEPT_SOURCES:
            assert _keyed_item_sport_identity(_concept(source.label)) == (
                None,
                source.category,
            )

    def test_an_event_or_future_is_not_this_pass_s_business(self):
        assert _keyed_item_sport_identity({"type": "event", "data": {}}) == (None, None)


class TestTheKeyedPassRanksAndNeverRemoves:
    def _run(self, items, ctx, my_teams_only=False):
        return _rank_keyed_items_by_sport_affinity(
            items, ctx=ctx, my_teams_only=my_teams_only
        )

    def test_a_nah_on_mma_ranks_the_ufc_card_down_and_keeps_it(self):
        ctx = _ctx({"mma_mixed_martial_arts": NAH, NBA: LOVE})
        out = self._run([_concept("ufc")], ctx)
        assert len(out) == 1
        assert out[0]["score"] == int(60 * (1.0 + NAH_AFFINITY_PENALTY))
        assert out[0]["personalization_reasons"] == [f"sport_nah:{NAH_AFFINITY_PENALTY:.2f}"]

    def test_a_missing_mma_preference_ranks_the_ufc_card_down_and_keeps_it(self):
        out = self._run([_concept("ufc")], _ctx({NBA: LOVE}))
        assert len(out) == 1 and out[0]["score"] < 60

    def test_a_loved_mma_leaves_the_ufc_card_at_its_own_score(self):
        """Brief24A: the keyed pass applies the dial's NEGATIVE side only.
        Before #1927's wide half a UFC card carried no preference term and a
        loved golf tour was simply kept at its own score; that positive
        behaviour is preserved rather than replaced by a new ×1.5 boost. The
        shared helper still reports the boost — it is this call site that
        declines it — so the dial's contract for events/futures is unchanged."""
        out = self._run([_concept("ufc")], _ctx({"mma_mixed_martial_arts": LOVE}))
        assert out[0]["score"] == 60 and "personalized" not in out[0]
        helper = compute_sport_affinity_multiplier(
            _ctx({"mma_mixed_martial_arts": LOVE}), sport_key=None, sport_category="mma"
        )
        assert helper.multiplier == pytest.approx(1.0 + HIGH_AFFINITY_BONUS)

    def test_a_nah_on_a_golf_tour_ranks_the_tournament_down_and_keeps_it(self):
        ctx = _ctx({"golf_pga": NAH, "golf_lpga": LOVE})
        out = self._run([_tournament("pga"), _tournament("lpga", key="lpga1")], ctx)
        by_key = {it["data"]["key"]: it["score"] for it in out}
        assert set(by_key) == {"the_open", "lpga1"}, "a tournament was removed"
        # the Nah tour ranks down; the LOVED tour stays at its own score
        # (pre-Brief24 positive behaviour, Brief24A)
        assert by_key["the_open"] < 60 == by_key["lpga1"]
        assert "personalized" not in next(it for it in out if it["data"]["key"] == "lpga1")

    def test_if_its_wild_on_a_golf_tour_ranks_the_tournament_down_and_keeps_it(self):
        """The dial's other negative term is applied too — a bounded downrank,
        never a removal — so "negative side only" is not "Nah only"."""
        from app.utils.personalization import LOW_AFFINITY_PENALTY

        out = self._run([_tournament("pga")], _ctx({"golf_pga": 0.1}))
        assert len(out) == 1
        assert out[0]["score"] == int(60 * (1.0 + LOW_AFFINITY_PENALTY))

    def test_a_reader_with_no_golf_at_all_still_gets_the_tournament(self):
        """The old `_compute_user_feed_tours` returned `set()` here and the
        builder returned `[]` — no golf for anyone who skipped golf at
        onboarding. Now: ranked down, served."""
        out = self._run([_tournament("pga")], _ctx({NBA: LOVE}))
        assert len(out) == 1 and 0 < out[0]["score"] < 60

    def test_an_unknown_tour_is_neutral(self):
        out = self._run([_tournament(None)], _ctx({"golf_pga": NAH}))
        assert out[0]["score"] == 60 and "personalized" not in out[0]

    def test_an_unknown_domain_is_neutral(self):
        out = self._run([_concept("darts")], _ctx({NBA: LOVE}))
        assert out[0]["score"] == 60 and "personalized" not in out[0]

    def test_a_marquee_pin_is_a_position_not_a_score_and_survives(self):
        item = _tournament("pga")
        item["_marquee_pin"] = True
        out = self._run([item], _ctx({"golf_pga": NAH}))
        assert out[0]["_marquee_pin"] is True and out[0]["score"] < 60

    def test_the_score_never_scales_to_zero(self):
        out = self._run([_concept("ufc", score=1)], _ctx({NBA: LOVE}))
        assert out[0]["score"] >= 1

    def test_the_shared_list_is_never_mutated(self):
        """The concept build is served from a principal-independent cache —
        a per-viewer score written into its dicts would be served to the next
        viewer. New dicts, or nothing."""
        items = [_concept("ufc"), _tournament("pga")]
        before = [dict(it) for it in items]
        self._run(items, _ctx({NBA: LOVE}))
        assert items == before

    def test_anonymous_and_unonboarded_readers_are_untouched(self):
        items = [_concept("ufc"), _tournament("pga")]
        assert self._run(items, PersonalizationContext()) == items
        assert self._run(items, _ctx({})) == items

    def test_my_stuff_is_untouched(self):
        items = [_concept("ufc")]
        assert self._run(items, _ctx({NBA: LOVE}), my_teams_only=True) == items

    def test_the_keyed_multiplier_is_rank_only_by_construction(self):
        r = compute_sport_affinity_multiplier(
            _ctx({"mma_mixed_martial_arts": NAH}), sport_key=None, sport_category="mma"
        )
        assert r.sport_nah is True
        assert r.multiplier == pytest.approx(1.0 + NAH_AFFINITY_PENALTY)
        assert r.admission_multiplier == 1.0
        assert compute_sport_affinity_multiplier(None, sport_key=None).multiplier == 1.0


# ==========================================================================
# 5. `_score_golf_tournaments` itself no longer deletes by tour
# ==========================================================================


def _golf_base_entry(key: str, tour: str | None) -> dict:
    start = NOW + timedelta(days=1)
    return {
        "key": key,
        "name": key,
        "slug": key,
        "tour": tour,
        "tour_label": None,
        "is_major": False,
        "is_tour_event": True,
        "commence_time": start.isoformat(),
        "resolution_date": (start + timedelta(days=3)).isoformat(),
        "start_date": start.isoformat(),
        "end_date": (start + timedelta(days=3)).isoformat(),
        "market_names": [f"{key} Winner"],
        "market_ids": [1],
        "golfers": [
            {
                "id": 1,
                "name": "Adrian Meronk",
                "probability": 0.10,
                "movement_24h": 0.0,
                "probability_change_24h": 0.0,
                "american_odds": None,
                "is_winner": None,
                "rank": 1,
            }
        ],
    }


def _golf(monkeypatch, tournaments, ctx):
    import asyncio

    import app.utils.golf_base as golf_base

    async def _fake_base(db, now, stages=None):
        return (tournaments, "fresh")

    monkeypatch.setattr(golf_base, "get_golf_base", _fake_base)
    return asyncio.run(_score_golf_tournaments(None, NOW, None, ctx))


class TestTheTournamentBuilderIsPrincipalIndependent:
    _BASE = [
        _golf_base_entry("pga1", "pga"),
        _golf_base_entry("lpga1", "lpga"),
        _golf_base_entry("unknown1", None),
    ]

    def test_a_reader_with_no_golf_key_is_no_longer_returned_nothing(self, monkeypatch):
        """RED on base: `_compute_user_feed_tours` -> `set()` -> `return []`."""
        keys = {it["data"]["key"] for it in _golf(monkeypatch, self._BASE, _ctx({NBA: LOVE}))}
        assert keys == {"pga1", "lpga1", "unknown1"}, keys

    def test_a_nah_d_tour_is_no_longer_dropped(self, monkeypatch):
        """RED on base: `lpga` at 0.0 failed `> 0.05` and was `continue`d."""
        ctx = _ctx({"golf_pga": LOVE, "golf_lpga": NAH})
        keys = {it["data"]["key"] for it in _golf(monkeypatch, self._BASE, ctx)}
        assert "lpga1" in keys, keys

    def test_the_builder_returns_the_same_list_for_every_principal(self, monkeypatch):
        anon = _golf(monkeypatch, self._BASE, PersonalizationContext())
        nah = _golf(monkeypatch, self._BASE, _ctx({"golf_pga": NAH}))
        assert [i["data"]["key"] for i in anon] == [i["data"]["key"] for i in nah]
        assert [i["score"] for i in anon] == [i["score"] for i in nah]

    def test_the_builder_no_longer_reads_the_context(self):
        """Principal independence, pinned the way the concept builder's is."""
        src = inspect.getsource(_score_golf_tournaments)
        assert "_compute_user_feed_tours" not in src
        assert "ctx.sport_affinities" not in src


# ==========================================================================
# 6. The gates no longer parse display strings to decide eligibility
# ==========================================================================


def test_no_gate_reads_sport_nah_off_the_reason_strings():
    """The CERT-2676 / narrow-#1927 lesson, pinned: a reason string is a
    display vocabulary. The retired filters were `any("sport_nah" in r for r
    in p_result.reasons)`; restoring either one fails here before it fails
    the behavioural arms above."""
    src = inspect.getsource(feed_module)
    assert '"sport_nah" in r' not in src
    assert "'sport_nah' in r" not in src
