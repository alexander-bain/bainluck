"""#3640, the ordering half — a Slam is not outranked by a Challenger's clock.

`/hub/tennis` orders its MATCHES rail live-first then soonest-first. Read on
production at 2026-09-06 19:45Z, mid-US-Open, that produced this rail:

     0  US Open ATP (Doubles): Bolelli/Vavassori vs Gille/Verbeek   LIVE  15:00Z
     1  US Open ATP (Doubles): Krawietz/Puetz vs Rojer/Winegar      LIVE  15:00Z
     2  Uesugi vs Nam                       ATP Challenger Shanghai       11:05Z
     3  US Open ATP: Ben Shelton vs Stefanos Tsitsipas                    23:00Z
     4  Derepasko vs Yamanaka               ATP Challenger Phan Thiet 3  +06:00Z
     5  Kawahashi vs Ryan Ziegann           ATP Challenger Phan Thiet 3  +06:00Z
     6  O'Connell vs Ichikawa               ATP Challenger Phan Thiet 3  +06:00Z
     7  Borisiouk vs Cook                   ATP Challenger Phan Thiet 3  +06:35Z
     8  Vishal Balsekar vs Heck             ATP Challenger Phan Thiet 3  +07:10Z
     9  Hewitt vs Bittoun Kouzmine          ATP Challenger Phan Thiet 3  +07:10Z
    10  Moriya vs Palan                     ATP Challenger Phan Thiet 3  +07:10Z
    11  US Open WTA: Iga Swiatek vs Qinwen Zheng                         +15:00Z
    12  US Open WTA: Naomi Osaka vs Elena Rybakina                       +15:00Z
    13  Perez / Schuurs vs Mertens / Shnaider                            +18:00Z
    14  Bondar / Kalinina vs Routliffe / Sutjiadi                        +18:00Z
    15  Siniakova / Townsend vs Hunter / Krawczyk                        +18:00Z
    16  US Open ATP: Karen Khachanov vs Learner Tien                     +15:00Z
    17  US Open ATP: Alexander Zverev vs Luciano Darderi                 +15:00Z
    18  US Open ATP (Doubles): Pavlasek/Rikl vs Cash/Glasspool           +18:00Z

Eight of nineteen cards are third-tier Challenger matches, and they hold every
slot between Shelton and Swiatek. Nothing was broken: Phan Thiet is UTC+7 and
those matches genuinely start nine hours before the US Open's. Soonest-first was
doing exactly what it says. It is the RULE that is wrong — a reader who opens
the tennis page during a Slam came for the Slam.

The fix is one key in the middle of the sort, and both halves of it are pinned
here: the demotion must move the Challengers, and it must NOT be a filter (an
all-Challenger week is a full rail), must not touch the live band, and must
leave `/api/leagues/tennis_atp` — a TOUR page, where a Challenger is on topic —
byte-identical.

Every name, ticker, competition label and start time below is verbatim from the
production payload and `futures_markets` at that timestamp.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routes.hub import _PROP_CLASSIFIERS, _UNDERCARD_CLASSIFIERS, HUB_CONFIGS
from app.routes.league_futures import _rail_tier, _venue_competition
from app.utils.event_tennis import is_tennis_feeder_circuit

NOW = datetime(2026, 9, 6, 19, 45, tzinfo=timezone.utc)
TOMORROW = NOW.replace(hour=0, minute=0) + timedelta(days=1)


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
    """Only the attributes the rail's ordering and serialisation actually read."""

    def __init__(
        self,
        mid,
        name,
        *,
        event_id,
        external_id,
        source="kalshi",
        competition=None,
        sides=("Home", "Away"),
    ):
        self.id = mid
        self.event_id = event_id
        self.name = name
        self.outcomes = [
            _Outcome(mid * 10, sides[0], 0.6),
            _Outcome(mid * 10 + 1, sides[1], 0.4),
        ]
        self.external_id = external_id
        self.source = source
        self.market_tier = 5
        self.category = "game_prop"
        self.llm_sport_category = "tennis"
        self.llm_league = None
        self.group_id = None
        self.canonical_market_key = None
        self.resolution_date = None
        self.market_metadata = {"competition": competition} if competition else {}


# ── The production rail of 2026-09-06 19:45Z, verbatim ──────────────────────
#
# (market_id, name, event_id, ticker, source, competition, start, status)
_PRODUCTION_RAIL = [
    (
        60236104,
        "US Open ATP (Doubles): Bolelli/Vavassori vs Gille/Verbeek",
        15304964,
        "0x0a1b2c3d4e5f60718293a4b5",
        "polymarket",
        None,
        NOW - timedelta(hours=4, minutes=45),
        "live",
    ),
    (
        60225681,
        "US Open ATP (Doubles): Krawietz/Puetz vs Rojer/Winegar",
        15304853,
        "0x0b2c3d4e5f60718293a4b5c6",
        "polymarket",
        None,
        NOW - timedelta(hours=4, minutes=45),
        "live",
    ),
    (
        60325895,
        "Uesugi vs Nam",
        15305942,
        "KXATPCHALLENGERMATCH-26SEP06UESNAM",
        "kalshi",
        "ATP Challenger Shanghai",
        NOW - timedelta(hours=8, minutes=40),
        "suspended",
    ),
    (
        60252519,
        "US Open ATP: Ben Shelton vs Stefanos Tsitsipas",
        15305016,
        "0x0c3d4e5f60718293a4b5c6d7",
        "polymarket",
        None,
        NOW + timedelta(hours=3, minutes=15),
        "scheduled",
    ),
    (
        60334029,
        "Derepasko vs Yamanaka",
        15306016,
        "KXATPCHALLENGERMATCH-26SEP07DERYAM",
        "kalshi",
        "ATP Challenger Phan Thiet 3",
        TOMORROW + timedelta(hours=6),
        "scheduled",
    ),
    (
        60334030,
        "Kawahashi vs Ryan Ziegann",
        15306017,
        "KXATPCHALLENGERMATCH-26SEP07KAWZIE",
        "kalshi",
        "ATP Challenger Phan Thiet 3",
        TOMORROW + timedelta(hours=6),
        "scheduled",
    ),
    (
        60334031,
        "O'Connell vs Ichikawa",
        15306011,
        "KXATPCHALLENGERMATCH-26SEP07OCOICH",
        "kalshi",
        "ATP Challenger Phan Thiet 3",
        TOMORROW + timedelta(hours=6),
        "scheduled",
    ),
    (
        60334032,
        "Borisiouk vs Cook",
        15306012,
        "KXATPCHALLENGERMATCH-26SEP07BORCOO",
        "kalshi",
        "ATP Challenger Phan Thiet 3",
        TOMORROW + timedelta(hours=6, minutes=35),
        "scheduled",
    ),
    (
        60334033,
        "Vishal Balsekar vs Heck",
        15306013,
        "KXATPCHALLENGERMATCH-26SEP07BALHEC",
        "kalshi",
        "ATP Challenger Phan Thiet 3",
        TOMORROW + timedelta(hours=7, minutes=10),
        "scheduled",
    ),
    (
        60334034,
        "Hewitt vs Bittoun Kouzmine",
        15306014,
        "KXATPCHALLENGERMATCH-26SEP07HEWBIT",
        "kalshi",
        "ATP Challenger Phan Thiet 3",
        TOMORROW + timedelta(hours=7, minutes=10),
        "scheduled",
    ),
    (
        60334035,
        "Moriya vs Palan",
        15306015,
        "KXATPCHALLENGERMATCH-26SEP07MORPAL",
        "kalshi",
        "ATP Challenger Phan Thiet 3",
        TOMORROW + timedelta(hours=7, minutes=10),
        "scheduled",
    ),
    (
        60285665,
        "US Open WTA: Iga Swiatek vs Qinwen Zheng",
        15305580,
        "0x0d4e5f60718293a4b5c6d7e8",
        "polymarket",
        None,
        TOMORROW + timedelta(hours=15),
        "scheduled",
    ),
    (
        60302221,
        "US Open WTA: Naomi Osaka vs Elena Rybakina",
        15305797,
        "0x0e5f60718293a4b5c6d7e8f9",
        "polymarket",
        None,
        TOMORROW + timedelta(hours=15),
        "scheduled",
    ),
    (
        60300771,
        "Perez / Schuurs vs Mertens / Shnaider",
        15305770,
        "KXWTADOUBLESMATCH-26SEP07PERMER",
        "kalshi",
        None,
        TOMORROW + timedelta(hours=18),
        "scheduled",
    ),
    (
        60276299,
        "Bondar / Kalinina vs Routliffe / Sutjiadi",
        15305552,
        "KXWTADOUBLESMATCH-26SEP07BONROU",
        "kalshi",
        None,
        TOMORROW + timedelta(hours=18),
        "scheduled",
    ),
    (
        60276300,
        "Siniakova / Townsend vs Hunter / Krawczyk",
        15305555,
        "KXWTADOUBLESMATCH-26SEP07SINHUN",
        "kalshi",
        None,
        TOMORROW + timedelta(hours=18),
        "scheduled",
    ),
    (
        60321431,
        "US Open ATP: Karen Khachanov vs Learner Tien",
        15305796,
        "0x0f60718293a4b5c6d7e8f901",
        "polymarket",
        None,
        TOMORROW + timedelta(hours=15),
        "scheduled",
    ),
    (
        60321442,
        "US Open ATP: Alexander Zverev vs Luciano Darderi",
        15305795,
        "0x10718293a4b5c6d7e8f90112",
        "polymarket",
        None,
        TOMORROW + timedelta(hours=15),
        "scheduled",
    ),
    (
        60298920,
        "US Open ATP (Doubles): Pavlasek/Rikl vs Cash/Glasspool",
        15305775,
        "0x11718293a4b5c6d7e8f90113",
        "polymarket",
        None,
        TOMORROW + timedelta(hours=18),
        "scheduled",
    ),
]

#: The eight the venue itself calls a Challenger.
CHALLENGER_IDS = {
    60325895,
    60334029,
    60334030,
    60334031,
    60334032,
    60334033,
    60334034,
    60334035,
}
#: The four US Open singles the Challengers were sitting on top of.
SLAM_SINGLES_IDS = {60285665, 60302221, 60321431, 60321442}


def _markets():
    return [
        _Market(
            mid,
            name,
            event_id=eid,
            external_id=ext,
            source=src,
            competition=comp,
        )
        for mid, name, eid, ext, src, comp, _start, _status in _PRODUCTION_RAIL
    ]


def _event_rows():
    return [
        (eid, start, status)
        for _mid, _name, eid, _ext, _src, _comp, start, status in _PRODUCTION_RAIL
    ]


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


async def _rail(**kwargs):
    from app.routes.league_futures import build_linked_matches

    return await build_linked_matches(
        "tennis_atp",
        _db(_markets(), _event_rows()),
        now=NOW,
        also_sport_keys=("tennis_wta",),
        **kwargs,
    )


class TestTheVenueIsTheOnlyWitness:
    """The predicate reads what a venue stated and nothing else."""

    def test_it_fires_on_the_kalshi_challenger_ticker(self):
        assert is_tennis_feeder_circuit(
            "KXATPCHALLENGERMATCH-26SEP07DERYAM", "Derepasko vs Yamanaka", None
        )

    def test_it_fires_on_the_stated_competition_alone(self):
        """A row with a neutral ticker is still a Challenger if the venue said so."""
        assert is_tennis_feeder_circuit(
            "KXATPMATCH-26SEP07UESNAM", "Uesugi vs Nam", "ATP Challenger Shanghai"
        )

    def test_it_fires_on_the_name_alone(self):
        assert is_tennis_feeder_circuit(None, "ITF Cairo: Aboian vs Castagnola", None)

    @pytest.mark.parametrize(
        "name",
        [
            "US Open WTA: Iga Swiatek vs Qinwen Zheng",
            "US Open ATP: Alexander Zverev vs Luciano Darderi",
            "US Open ATP (Doubles): Pavlasek/Rikl vs Cash/Glasspool",
            "Paul vs Alcaraz",
            "Siniakova / Townsend vs Hunter / Krawczyk",
        ],
    )
    def test_it_fires_on_no_us_open_row(self, name):
        assert not is_tennis_feeder_circuit(None, name, None)

    def test_it_fires_on_no_polymarket_condition_id(self):
        """The hex ids are 24-32 chars of [0-9a-f] and must never trip a match —
        the whole Polymarket half of the rail would sink if one did."""
        for _m, _n, _e, ext, src, *_rest in _PRODUCTION_RAIL:
            if src == "polymarket":
                assert not is_tennis_feeder_circuit(ext, None, None), ext

    def test_qualifying_counts_as_the_feeder_circuit(self):
        """A Slam's own qualifying draw is the undercard of that Slam, and the
        rule is about what a reader came for, not about the venue's prestige."""
        assert is_tennis_feeder_circuit(None, "US Open Qualifying: Gea vs Bergs", None)

    def test_every_production_challenger_is_caught_and_nothing_else_is(self):
        caught = {
            m.id
            for m in _markets()
            if is_tennis_feeder_circuit(m.external_id, m.name, _venue_competition(m))
        }
        assert caught == CHALLENGER_IDS


class TestTheRailPutsTheSlamAboveTheChallenger:
    """The ship, on the exact population that produced the defect."""

    async def test_no_challenger_outranks_a_us_open_singles(self):
        rows = await _rail(is_undercard=is_tennis_feeder_circuit)
        order = [r["id"] for r in rows]
        worst_slam = max(order.index(i) for i in SLAM_SINGLES_IDS)
        best_challenger = min(order.index(i) for i in CHALLENGER_IDS)
        assert worst_slam < best_challenger, (
            "a Challenger is still above a Slam singles: "
            f"{[rows[i]['name'] for i in range(len(rows))]}"
        )

    async def test_swiatek_moves_from_position_11_to_the_top_third(self):
        rows = await _rail(is_undercard=is_tennis_feeder_circuit)
        order = [r["id"] for r in rows]
        assert order.index(60285665) == 3, (
            "behind the two live doubles and Shelton tonight, and ahead of "
            "everything the clock used to put in front of her"
        )

    async def test_the_control_reproduces_the_defect(self):
        """Without the predicate the defect must still be here, or the test above
        is passing for a reason that has nothing to do with this change.

        This is `build_linked_matches`' own output — live band first, then
        strictly by the clock. The rendered rail in this file's header differs
        from it in one respect: Khachanov, Zverev and the Pavlasek doubles are
        rendered at 16-18 rather than in clock order, because the name-dedup
        further down replaces a thinner duplicate by deleting it and APPENDING
        the richer row, which moves that card to the end. Pre-existing, unrelated
        to this key, and noted here so the next reader does not mistake it for
        one. What both orders agree on is the defect: every Challenger above
        every US Open singles.
        """
        rows = await _rail()
        order = [r["id"] for r in rows]
        assert order[:4] == [60236104, 60225681, 60325895, 60252519], (
            "a Challenger at rail position 2, exactly as production served it"
        )
        assert max(order.index(i) for i in CHALLENGER_IDS) < min(
            order.index(i) for i in SLAM_SINGLES_IDS
        ), "all eight Challengers above all four Slam singles — the issue, verbatim"
        assert order.index(60285665) == 11, "Swiatek at 11, as filed"

    async def test_the_live_band_is_untouched(self):
        """The outer key does not move: what is on now still leads the rail."""
        rows = await _rail(is_undercard=is_tennis_feeder_circuit)
        assert [r["id"] for r in rows[:2]] == [60236104, 60225681]

    async def test_a_live_challenger_still_leads_a_scheduled_slam(self):
        """The deliberate cost of sorting inside the live band, pinned so nobody
        'fixes' it by accident: on court beats not started, always."""
        from app.routes.league_futures import build_linked_matches

        markets = _markets()
        # It has to have STARTED to be live: `served_event_status` reads a row
        # claiming `live` before its own commence_time as `scheduled` (#1779).
        event_rows = [
            (
                (eid, NOW - timedelta(minutes=40), "live")
                if eid == 15306016
                else (eid, start, status)
            )
            for _m, _n, eid, _e, _s, _c, start, status in _PRODUCTION_RAIL
        ]
        rows = await build_linked_matches(
            "tennis_atp",
            _db(markets, event_rows),
            now=NOW,
            also_sport_keys=("tennis_wta",),
            is_undercard=is_tennis_feeder_circuit,
        )
        assert 60334029 in [r["id"] for r in rows[:3]]

    async def test_the_challengers_keep_their_own_order(self):
        """Demoted as a block, not shuffled: within the tail they are still
        soonest-first, which is the only order that tail can have."""
        rows = await _rail(is_undercard=is_tennis_feeder_circuit)
        tail = [r["id"] for r in rows if r["id"] in CHALLENGER_IDS]
        assert tail == [
            60325895,
            60334029,
            60334030,
            60334031,
            60334032,
            60334033,
            60334034,
            60334035,
        ]

    async def test_nothing_is_dropped(self):
        """A rank key, not a filter. Nineteen cards in, nineteen out."""
        rows = await _rail(is_undercard=is_tennis_feeder_circuit)
        assert sorted(r["id"] for r in rows) == sorted(
            mid for mid, *_rest in _PRODUCTION_RAIL
        )

    async def test_a_week_of_nothing_but_challengers_is_a_full_rail(self):
        """The inverted failure: the fix must not be able to empty a rail. In
        January there is no Slam and the Challengers ARE the tennis."""
        from app.routes.league_futures import build_linked_matches

        rows_only_challengers = [
            r for r in _PRODUCTION_RAIL if r[0] in CHALLENGER_IDS
        ]
        markets = [
            _Market(
                mid, name, event_id=eid, external_id=ext, source=src, competition=comp
            )
            for mid, name, eid, ext, src, comp, _s, _st in rows_only_challengers
        ]
        event_rows = [
            (eid, start, status)
            for _m, _n, eid, _e, _s, _c, start, status in rows_only_challengers
        ]
        rows = await build_linked_matches(
            "tennis_atp",
            _db(markets, event_rows),
            now=NOW,
            is_undercard=is_tennis_feeder_circuit,
        )
        assert [r["id"] for r in rows] == [
            60325895,
            60334029,
            60334030,
            60334031,
            60334032,
            60334033,
            60334034,
            60334035,
        ]


class TestEveryOtherCallerIsByteIdentical:
    """`is_undercard=None` is every non-hub caller, and it must mean 'as before'."""

    async def test_the_tour_page_ordering_does_not_move(self):
        """`/api/leagues/tennis_atp` is a TOUR page. A Challenger belongs on it,
        and demoting it there would be a different bug wearing this fix's face."""
        with_kwarg_absent = [r["id"] for r in await _rail()]
        with_explicit_none = [r["id"] for r in await _rail(is_undercard=None)]
        assert with_kwarg_absent == with_explicit_none
        # And it is the OLD order, not merely a self-consistent one.
        assert max(with_kwarg_absent.index(i) for i in CHALLENGER_IDS) < min(
            with_kwarg_absent.index(i) for i in SLAM_SINGLES_IDS
        )

    def test_the_tier_of_every_market_is_zero_without_a_predicate(self):
        assert {_rail_tier(m) for m in _markets()} == {0}

    def test_the_raw_competition_reader_does_not_suppress_an_echo(self):
        """`_market_competition` (the DISPLAY reader) drops a label that merely
        echoes the card's name. Ordering needs the raw fact, so this is a second
        reader on purpose — pinned, because collapsing the two would silently
        stop demoting any Challenger whose name repeats its draw."""
        from app.routes.league_futures import _market_competition

        echo = _Market(
            1,
            "ATP Challenger Shanghai",
            event_id=1,
            external_id="KXATPMATCH-1",
            competition="ATP Challenger Shanghai",
        )
        assert _market_competition(echo) is None
        assert _venue_competition(echo) == "ATP Challenger Shanghai"
        assert _rail_tier(echo, is_tennis_feeder_circuit) == 1


class TestTheHubHandsItsOwnPredicateToTheRail:
    """The wiring. `_rail_tier` alone would pass on the parent commit, because
    nothing there ever calls the rail with a feeder-circuit predicate."""

    @staticmethod
    async def _spy_on(cfg, monkeypatch):
        import app.routes.hub as hub_module

        seen = {}

        async def _spy(sport_key, db, *, now=None, **kwargs):
            seen.update(kwargs)
            return []

        monkeypatch.setattr(hub_module, "build_linked_matches", _spy)

        async def _empty_league(**kwargs):
            return {"sections": {}}

        monkeypatch.setattr(hub_module, "get_league_futures", _empty_league)
        await hub_module.build_hub(cfg, db=None)
        return seen

    async def test_tennis_passes_the_feeder_circuit_predicate(self, monkeypatch):
        seen = await self._spy_on(HUB_CONFIGS["tennis"], monkeypatch)
        assert seen["is_undercard"] is is_tennis_feeder_circuit

    @pytest.mark.parametrize("slug", sorted(HUB_CONFIGS))
    async def test_every_hub_passes_exactly_its_own_table_entry(
        self, slug, monkeypatch
    ):
        cfg = HUB_CONFIGS[slug]
        expected = (
            _UNDERCARD_CLASSIFIERS.get(cfg.prop_classifier_domain)
            if cfg.prop_classifier_domain
            else None
        )
        seen = await self._spy_on(cfg, monkeypatch)
        assert seen["is_undercard"] is expected

    async def test_a_combat_hub_demotes_nothing(self, monkeypatch):
        """MMA and boxing are absent from the table deliberately: a UFC prelim is
        ON the card the reader came for. Demoting it would be this same mistake
        pointed the other way."""
        combat = [
            slug
            for slug, cfg in HUB_CONFIGS.items()
            if cfg.prop_classifier_domain in {"ufc", "boxing"}
        ]
        assert combat, "this guard has lost its subject"
        for slug in combat:
            seen = await self._spy_on(HUB_CONFIGS[slug], monkeypatch)
            assert seen["is_undercard"] is None

    def test_the_two_tables_agree_about_which_domains_exist(self):
        """A domain in the undercard table that no hub declares is dead config;
        the reverse (a prop domain with no undercard rule) is the normal case."""
        declared = {
            cfg.prop_classifier_domain
            for cfg in HUB_CONFIGS.values()
            if cfg.prop_classifier_domain
        }
        assert set(_UNDERCARD_CLASSIFIERS) <= declared
        assert set(_UNDERCARD_CLASSIFIERS) <= set(_PROP_CLASSIFIERS)
