"""#3640 — the tennis hub's match card is the MATCH, not one of its props.

`/hub/tennis` on 2026-09-06 did not carry Carlos Alcaraz while he was on court
(notice 27, the Marquee Axiom). He was not unmatched, not unpriced, not stale and
not capped: event `15304847` held 15 in-scope open markets, its own status was
`live`, and the rail's pool read 1,132 rows against a 4,000 cap. He was
RECLASSIFIED, by two functions that were each right on their own:

1. `build_linked_matches` elects exactly ONE card per event and ranked the
   candidates `(not-a-submarket-bundle, len(outcomes))`. Kalshi's
   "Tommy Paul vs Carlos Alcaraz: Exact Match Score" has six outcomes
   ("Carlos Alcaraz wins 3-0", …) where the head-to-head "Paul vs Alcaraz" has
   two, and neither is a bundle — so the prop was elected.
2. `build_hub` then moves every row `classify_tennis_prop` tags out of `matches`
   and into `props`. It tagged that row `'exact score'`, correctly.

Composed, step 2 deletes the only row step 1 left for the event, and the match
leaves the rail. Replaying both functions over production data read at
2026-09-06 19:20Z, the elected card was a prop for NINE of the 34 playable
in-scope events, and those nine were exactly the absent US Open singles:
Alcaraz–Paul (LIVE), Medvedev–Tiafoe (LIVE), Michelsen, Kalinskaya, Jovic–Gauff,
Gea, Osaka, Zverev, Khachanov. The rail carried 23 cards where it should have
carried 32.

Nothing in the envelope could show this: the eviction happens BEFORE
`resolve_entity_tier` runs, so `section_counts.matches` read
`{"total": 27, "shown": 20, "dropped": 7}` — those 7 being the unrelated
`is_unpriced_card` drop — while nine matches had already been relocated
uncounted.

Every market name and outcome in this file is verbatim from `futures_markets`
on 2026-09-06. Both directions are pinned throughout: a rank that suppressed
props outright would empty a rail whose event has nothing else, which is the
same defect with a different victim.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routes.hub import _PROP_CLASSIFIERS, HUB_CONFIGS
from app.routes.league_futures import _is_submarket_bundle, _match_card_rank
from app.utils.event_tennis import classify_tennis_prop

NOW = datetime(2026, 9, 6, 19, 20, tzinfo=timezone.utc)


class _Outcome:
    def __init__(self, oid, name, prob):
        self.id = oid
        self.name = name
        self.current_probability = prob
        self.opening_probability = None
        self.rank = None
        self.probability_change_24h = None
        self.team_id = None


class _Market:
    """Only the attributes the election and serialisation actually read."""

    def __init__(self, mid, name, outcomes, *, event_id=15304847, external_id=None):
        self.id = mid
        self.event_id = event_id
        self.name = name
        self.outcomes = outcomes
        self.external_id = external_id or f"KXATPMATCH-{mid}"
        self.source = "kalshi"
        self.market_tier = 5
        self.category = "game_prop"
        self.llm_sport_category = "tennis"
        self.llm_league = None
        self.group_id = None
        self.canonical_market_key = None
        self.resolution_date = None


# ── Event 15304847, verbatim. Alcaraz was LIVE when this was read. ───────────


def _head_to_head():
    """Kalshi `KXATPMATCH-26SEP06PAUALC`. Two outcomes, and it names both men."""
    return _Market(
        60218569,
        "Paul vs Alcaraz",
        [_Outcome(1, "Carlos Alcaraz", 0.93), _Outcome(2, "Tommy Paul", 0.08)],
        external_id="KXATPMATCH-26SEP06PAUALC",
    )


def _exact_score_prop():
    """Kalshi `KXATPEXACTMATCH-26SEP06PAUALC`. Six outcomes — and it is a prop."""
    return _Market(
        60218586,
        "Tommy Paul vs Carlos Alcaraz: Exact Match Score",
        [
            _Outcome(11, "Carlos Alcaraz wins 3-0", 0.66),
            _Outcome(12, "Carlos Alcaraz wins 3-1", 0.21),
            _Outcome(13, "Carlos Alcaraz wins 3-2", 0.07),
            _Outcome(14, "Tommy Paul wins 3-2", 0.04),
            _Outcome(15, "Tommy Paul wins 3-0", 0.01),
            _Outcome(16, "Tommy Paul wins 3-1", 0.01),
        ],
        external_id="KXATPEXACTMATCH-26SEP06PAUALC",
    )


def _submarket_bundle():
    """Polymarket serialises the nested sub-markets as outcomes (gotcha #18).

    Fourteen outcomes, thirteen of them prefixed by the market's own name — the
    pre-existing bundle rule already demotes this one, and must keep doing so.
    """
    name = "US Open ATP: Tommy Paul vs Carlos Alcaraz"
    outcomes = [_Outcome(20, "Tommy Paul", 0.07)]
    outcomes += [
        _Outcome(21 + i, f"{name} {leg}", 0.5)
        for i, leg in enumerate(
            [
                "Set 1 Winner",
                "Set 2 Winner",
                "Set 3 Winner",
                "Total Sets: O/U 3.5",
                "Total Sets: O/U 4.5",
                "Match O/U 36.5",
                "Match O/U 38.5",
                "Match O/U 40.5",
                "Set 1 Games O/U 8.5",
                "Set 1 Games O/U 9.5",
                "Set 1 Games O/U 10.5",
                "Set Handicap (-1.5)",
                "Set Handicap (-2.5)",
            ]
        )
    ]
    return _Market(60218896, name, outcomes, external_id="967050")


class TestThePropCannotSpeakForTheMatch:
    def test_the_exact_score_row_loses_to_the_head_to_head(self):
        h2h, prop = _head_to_head(), _exact_score_prop()
        assert _match_card_rank(h2h, classify_tennis_prop) > _match_card_rank(
            prop, classify_tennis_prop
        ), (
            "the rail would elect 'Exact Match Score' to represent Alcaraz–Paul, "
            "and the hub's own prop split then removes it — with it, the match"
        )

    def test_it_loses_precisely_BECAUSE_it_has_more_outcomes_no_longer_wins(self):
        """The defect was arithmetic: 6 > 2. Pin that the count no longer decides."""
        prop = _exact_score_prop()
        h2h = _head_to_head()
        assert len(prop.outcomes) > len(h2h.outcomes)
        assert _match_card_rank(prop, classify_tennis_prop)[0] == 0
        assert _match_card_rank(h2h, classify_tennis_prop)[0] == 1

    def test_the_classifier_really_does_tag_this_row(self):
        """If this ever stops being true the guard above proves nothing."""
        assert classify_tennis_prop(None, _exact_score_prop().name) == "exact score"
        assert classify_tennis_prop(None, _head_to_head().name) is None

    def test_without_a_predicate_the_old_order_is_byte_identical(self):
        """The control. Every non-hub caller passes nothing and must be unchanged
        — including in the direction that was wrong, so this test genuinely
        fails on the parent commit's behaviour rather than passing everywhere."""
        h2h, prop = _head_to_head(), _exact_score_prop()
        assert _match_card_rank(prop) > _match_card_rank(h2h)

    def test_a_submarket_bundle_still_loses_to_a_head_to_head(self):
        """UX-P181's rule is older than this one and survives it intact."""
        bundle = _submarket_bundle()
        assert _is_submarket_bundle(bundle)
        for predicate in (None, classify_tennis_prop):
            assert _match_card_rank(_head_to_head(), predicate) > _match_card_rank(
                bundle, predicate
            )

    def test_a_bundle_outranks_a_prop_and_that_is_deliberate(self):
        """The prop key is FIRST, above the bundle key, and this is the pair that
        proves why the order is that way round rather than the other.

        On readability alone the prop wins: "Exact Match Score" names both
        players and prices a distribution, while a sub-market bundle led with
        "Set 2 Winner >99%" on production and never named anyone (#2167). But
        readability is not the question being decided here. The caller that
        passes a predicate is the caller that is about to DELETE every row the
        predicate tags, and this function elects exactly one row per event — so
        electing the prop does not give the reader a better card, it gives them
        no card and no match. A poor card that survives beats a good one that is
        removed with the event attached to it.
        """
        assert _match_card_rank(
            _submarket_bundle(), classify_tennis_prop
        ) > _match_card_rank(_exact_score_prop(), classify_tennis_prop)

    def test_and_without_a_predicate_that_pair_flips_back(self):
        """Nobody who is not about to evict props inherits that trade-off: with
        no predicate the bundle rule alone decides, and the readable row wins."""
        assert _match_card_rank(_exact_score_prop()) > _match_card_rank(
            _submarket_bundle()
        )

    def test_an_event_whose_every_market_is_a_prop_still_gets_a_card(self):
        """It is a RANK key, not a filter. Suppressing props outright would empty
        the rail for any match we only carry derivative markets on — the same
        disappearance this fix exists to remove."""
        props = [
            _exact_score_prop(),
            _Market(
                60221054,
                "Tommy Paul vs. Carlos Alcaraz: Total Sets O/U 3.5",
                [_Outcome(31, "Over", 0.6), _Outcome(32, "Under", 0.4)],
            ),
        ]
        best = max(props, key=lambda m: _match_card_rank(m, classify_tennis_prop))
        assert best is not None
        assert best.id == 60218586, "the richer prop should still lead its own field"


class TestTheRailReturnsTheMatch:
    """End to end through `build_linked_matches` on the real specimen."""

    @staticmethod
    def _db(markets, event_rows):
        pool = MagicMock()
        pool.unique.return_value = pool
        pool.all.return_value = markets
        first = MagicMock()
        first.scalars.return_value = pool
        second = MagicMock()
        second.all.return_value = event_rows
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[first, second])
        return db

    @staticmethod
    def _specimen():
        return [_head_to_head(), _exact_score_prop(), _submarket_bundle()]

    #: `15304847` as production held it: live, and started 73 minutes ago.
    EVENT_ROWS = [(15304847, NOW - timedelta(minutes=73), "live")]

    async def test_alcaraz_is_on_the_rail_and_his_card_is_the_match(self):
        from app.routes.league_futures import build_linked_matches

        rows = await build_linked_matches(
            "tennis_atp",
            self._db(self._specimen(), self.EVENT_ROWS),
            now=NOW,
            also_sport_keys=("tennis_wta",),
            is_prop=classify_tennis_prop,
        )

        assert len(rows) == 1, "one card per event, and the event must have one"
        assert rows[0]["id"] == 60218569
        assert classify_tennis_prop(rows[0]["external_id"], rows[0]["name"]) is None, (
            "the hub's prop split will delete this row, and it is the event's "
            "only one — Alcaraz leaves the rail exactly as he did on 2026-09-06"
        )

    async def test_the_control_reproduces_the_defect(self):
        """Same population, no predicate: the rail still elects the prop. Without
        this the test above could be passing for some unrelated reason."""
        from app.routes.league_futures import build_linked_matches

        rows = await build_linked_matches(
            "tennis_atp",
            self._db(self._specimen(), self.EVENT_ROWS),
            now=NOW,
            also_sport_keys=("tennis_wta",),
        )

        assert [r["id"] for r in rows] == [60218586]
        assert classify_tennis_prop(rows[0]["external_id"], rows[0]["name"]) == (
            "exact score"
        )

    async def test_an_event_of_props_only_keeps_its_card(self):
        """Both directions at the rail level too: the fix must not be able to
        empty a rail it was written to fill."""
        from app.routes.league_futures import build_linked_matches

        rows = await build_linked_matches(
            "tennis_atp",
            self._db([_exact_score_prop()], self.EVENT_ROWS),
            now=NOW,
            is_prop=classify_tennis_prop,
        )

        assert [r["id"] for r in rows] == [60218586]


class TestTheHubHandsItsOwnPredicateToTheRail:
    """The wiring, which is the whole class.

    Neither function was wrong alone; the defect was that the hub kept its prop
    predicate to itself until after the rail had already picked. A guard on the
    rank alone would pass on the parent commit for the tennis hub too, because
    nothing there ever calls it with a predicate.
    """

    @staticmethod
    async def _spy_on(cfg, monkeypatch):
        import app.routes.hub as hub_module

        seen = {}

        async def _spy(sport_key, db, *, now=None, also_sport_keys=(), is_prop=None):
            seen["is_prop"] = is_prop
            return []

        monkeypatch.setattr(hub_module, "build_linked_matches", _spy)

        async def _empty_league(**kwargs):
            return {"sections": {}}

        monkeypatch.setattr(hub_module, "get_league_futures", _empty_league)
        await hub_module.build_hub(cfg, db=None)
        return seen

    async def test_tennis_passes_the_classifier_it_will_evict_with(self, monkeypatch):
        seen = await self._spy_on(HUB_CONFIGS["tennis"], monkeypatch)
        assert (
            seen["is_prop"] is _PROP_CLASSIFIERS["tennis"]
        ), "the hub elects a card with one rule and deletes it with another"

    @pytest.mark.parametrize("slug", sorted(HUB_CONFIGS))
    async def test_every_hub_passes_exactly_the_predicate_it_splits_with(
        self, slug, monkeypatch
    ):
        """Not a tennis fix. Any hub that gains a classifier inherits the defect
        the moment its sport starts matching — MMA and boxing read match-shaped
        today only because combat markets carry no `event_id`."""
        cfg = HUB_CONFIGS[slug]
        expected = (
            _PROP_CLASSIFIERS.get(cfg.prop_classifier_domain)
            if cfg.prop_classifier_domain
            else None
        )
        seen = await self._spy_on(cfg, monkeypatch)
        assert seen["is_prop"] is expected

    async def test_a_hub_without_a_classifier_passes_none(self, monkeypatch):
        """The degenerate direction: a hub that splits nothing must not acquire a
        ranking rule out of nowhere."""
        plain = [
            slug
            for slug, cfg in HUB_CONFIGS.items()
            if cfg.prop_classifier_domain is None
        ]
        assert plain, "every hub now classifies — this guard has lost its subject"
        seen = await self._spy_on(HUB_CONFIGS[plain[0]], monkeypatch)
        assert seen["is_prop"] is None


class TestTheProductionPopulationIsCovered:
    """The nine, by name. A rank rule that fixed Alcaraz and left Osaka is not a
    fix, and the names are what a reader of the issue will check."""

    #: The elected card for each absent event, verbatim from production
    #: 2026-09-06 19:20Z, with the head-to-head that should have won instead.
    NINE = [
        ("Tommy Paul vs Carlos Alcaraz: Exact Match Score", "Paul vs Alcaraz"),
        ("Daniil Medvedev vs Frances Tiafoe: Exact Match Score", "Medvedev vs Tiafoe"),
        (
            "Alex Michelsen vs Tomas Martin Etcheverry: Exact Match Score",
            "Michelsen vs Etcheverry",
        ),
        ("Anna Kalinskaya vs Emma Navarro: Exact Match Score", "Kalinskaya vs Navarro"),
        ("Iva Jovic vs Coco Gauff: Exact Match Score", "Jovic vs Gauff"),
        (
            "Arthur Gea vs Botic Van de Zandschulp: Exact Match Score",
            "Gea vs Van de Zandschulp",
        ),
        ("Naomi Osaka vs Elena Rybakina: Exact Match Score", "Osaka vs Rybakina"),
        ("Alexander Zverev vs Luciano Darderi: Exact Match Score", "Zverev vs Darderi"),
        ("Karen Khachanov vs Learner Tien: Exact Match Score", "Khachanov vs Tien"),
    ]

    @pytest.mark.parametrize("prop_name,match_name", NINE)
    def test_the_match_outranks_the_prop_that_buried_it(self, prop_name, match_name):
        prop = _Market(1, prop_name, [_Outcome(i, f"score {i}", 0.1) for i in range(6)])
        match = _Market(2, match_name, [_Outcome(7, "A", 0.6), _Outcome(8, "B", 0.4)])
        assert _match_card_rank(match, classify_tennis_prop) > _match_card_rank(
            prop, classify_tennis_prop
        )
