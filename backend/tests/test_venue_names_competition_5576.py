"""#5576 — a Nations League game is filed under the Nations League when the venue says so.

THE DEFECT, seen at 390px on 2026-09-27: ``/search?q=portugal`` shows Norway v
Portugal (09-27) and Denmark v Portugal (10-01) under UEFA NATIONS LEAGUE with
flags, and Portugal v Norway (10-04) under OTHER SOCCER with "P"/"N" letter
tiles. 60 Nations League rows for 09-27..10-06 sat on ``soccer_other``; every
one carries a Polymarket ``unl-`` slug or a Kalshi ``KXUEFANLGAME`` leg.

Measured with the placer's own two reads, the clubs failed three ways — 45
season-guard refusals (the rows are minted ~13 days out), 9 two-competition
ambiguities (Portugal and Norway are also World Cup sides), 6 names ``teams``
does not carry ("Republic of Ireland"). The venue named the competition for all
60. This file pins:

  1. what the venue says (``venue_named_league``), both venues;
  2. what the placement requires besides the venue (``venue_placed_league``);
  3. the real create flow on the specimen and each failure arm, each against a
     control proving the clubs alone would have left the row on the catch-all
     — so a test that passes is the venue arm working, not a rig that never
     reached a refusal;
  4. that #6392's own specimen (a friendly in a finished World Cup) and #8636's
     (a club friendly between two Bundesliga clubs) are untouched.
"""

from datetime import datetime, timezone

import pytest

import app.services.event_registry as event_registry
import app.tasks.prediction_market_matching as pmm
from app.utils.venue_competition import (
    KALSHI_SERIES_LEAGUES,
    POLYMARKET_EVENT_SLUG_KEY as SLUG_FIELD,
    POLYMARKET_LEAGUE_CODES,
    venue_named_league,
)
from app.utils.sport_keys import get_sport_key_from_ticker
from tests.lib_placement_predicate import PredicateSession, ScheduleRow

UNL = "soccer_uefa_nations_league"
WC = "soccer_fifa_world_cup"
WCQ = "soccer_fifa_world_cup_qualifiers_europe"


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


# ═══ 1. What the venue says ══════════════════════════════════════════════════


class TestWhatTheVenueSays:
    @pytest.mark.parametrize(
        "slug",
        [
            "unl-prt-nor-2026-10-04",
            "unl-prt-nor-2026-10-04-more-markets",
            "unl-cze-eng-2026-09-29-total-corners",
        ],
    )
    def test_a_polymarket_unl_slug_names_the_nations_league(self, slug):
        assert venue_named_league("polymarket", "1057948", {SLUG_FIELD: slug}) == UNL

    @pytest.mark.parametrize(
        "ticker",
        [
            "KXUEFANLGAME-26OCT04PORNOR",
            "KXUEFANLGAME-26OCT04PORNOR-POR",
            "kxuefanlgame-26oct06suimkd-tie",
        ],
    )
    def test_a_kalshi_nations_league_game_ticker_names_it(self, ticker):
        assert venue_named_league("kalshi", ticker, None) == UNL

    @pytest.mark.parametrize(
        "source,external_id,meta",
        [
            # Friendlies are no league — #6392's and #8636's specimens.
            ("polymarket", "1", {SLUG_FIELD: "fif-fra-can-2026-09-17"}),
            ("polymarket", "1", {SLUG_FIELD: "clf-vfb-fch-2026-09-25"}),
            # Volleyball's Euro code is not in the soccer map.
            ("polymarket", "1", {SLUG_FIELD: "vbeuro-ita2-slo4-2026-09-17"}),
            # `ucl` is two leagues (the competition and its qualifying rounds).
            ("polymarket", "1", {SLUG_FIELD: "ucl-rma-mci-2026-10-01"}),
            # A futures slug has no code.
            ("polymarket", "1", {SLUG_FIELD: "uefa-nations-league-2027-winner"}),
            # No stamp yet — most far-future rows on 2026-09-27.
            ("polymarket", "1", {"polymarket_event_id": "1057948"}),
            ("polymarket", "1", None),
            # Kalshi: only the series the map names; the derivative series of
            # the same fixture (BTTS/TOTAL/SPREAD) are not a GAME listing.
            ("kalshi", "KXUEFANLBTTS-26OCT04PORNOR", None),
            ("kalshi", "KXEPLGAME-26OCT04ARSCHE", None),
            ("kalshi", "", None),
            ("kalshi", None, None),
            # Each venue is read only through its own channel.
            ("kalshi", "KXFOO", {SLUG_FIELD: "unl-prt-nor-2026-10-04"}),
            ("polymarket", "KXUEFANLGAME-26OCT04PORNOR", {}),
            ("espn", "401861126", {SLUG_FIELD: "unl-prt-nor-2026-10-04"}),
        ],
    )
    def test_anything_else_names_nothing(self, source, external_id, meta):
        assert venue_named_league(source, external_id, meta) is None

    def test_the_kalshi_map_holds_only_series_the_sport_key_map_does_not_spell(self):
        """If the ticker map ever learns a series, this map must drop it —
        two spellings of one venue fact is how they drift apart."""
        assert KALSHI_SERIES_LEAGUES
        for series, league in KALSHI_SERIES_LEAGUES.items():
            assert series == series.lower() and "-" not in series
            assert get_sport_key_from_ticker(f"{series.upper()}-26OCT04AAABBB") is None
            assert league in POLYMARKET_LEAGUE_CODES, league


# ═══ 2. What the placement requires besides the venue ═══════════════════════


class _Market:
    def __init__(self, source="polymarket", external_id="1057948", slug=None):
        self.source = source
        self.external_id = external_id
        self.market_metadata = {SLUG_FIELD: slug} if slug else {}


def _sides(monkeypatch, a: set, b: set):
    calls = []

    async def fake(session, team_a, team_b, sport_key):
        calls.append((team_a, team_b, sport_key))
        return [set(a), set(b)]

    monkeypatch.setattr(pmm, "leagues_by_side_for_matchup", fake)
    return calls


class TestWhatThePlacementRequires:
    @pytest.mark.asyncio
    async def test_two_competitions_shared_the_venue_picks_one(self, monkeypatch):
        _sides(monkeypatch, {WC, UNL}, {WC, UNL})
        league = await pmm.venue_placed_league(
            object(), "Portugal", "Norway", "soccer_other",
            _Market(slug="unl-prt-nor-2026-10-04"),
        )
        assert league == UNL

    @pytest.mark.asyncio
    async def test_one_resolvable_side_is_enough(self, monkeypatch):
        """'Republic of Ireland' is not a name `teams` carries; Israel is."""
        _sides(monkeypatch, set(), {UNL})
        league = await pmm.venue_placed_league(
            object(), "Republic of Ireland", "Israel", "soccer_other",
            _Market("kalshi", "KXUEFANLGAME-26OCT04IRLISR"),
        )
        assert league == UNL

    @pytest.mark.asyncio
    async def test_no_side_in_the_named_league_places_nothing(self, monkeypatch):
        """The venue's code must mean OUR league — one side has to agree."""
        _sides(monkeypatch, {WCQ}, set())
        league = await pmm.venue_placed_league(
            object(), "Poland", "Somewhere", "soccer_other",
            _Market(slug="unl-pol-xxx-2026-10-02"),
        )
        assert league is None

    @pytest.mark.asyncio
    async def test_nothing_resolvable_places_nothing(self, monkeypatch):
        async def none(*args):
            return None

        monkeypatch.setattr(pmm, "leagues_by_side_for_matchup", none)
        league = await pmm.venue_placed_league(
            None, "Portugal", "Norway", "soccer_other",
            _Market(slug="unl-prt-nor-2026-10-04"),
        )
        assert league is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "sport_key",
        ["basketball_other", "_other", "other", "soccer_epl", "", None],
    )
    async def test_only_a_same_family_catch_all_is_relabelled(
        self, monkeypatch, sport_key
    ):
        calls = _sides(monkeypatch, {UNL}, {UNL})
        league = await pmm.venue_placed_league(
            object(), "Portugal", "Norway", sport_key,
            _Market(slug="unl-prt-nor-2026-10-04"),
        )
        assert league is None
        assert calls == [], "a key the venue cannot place still cost a round trip"

    @pytest.mark.asyncio
    async def test_a_covered_league_is_never_placed_into(self, monkeypatch):
        """Refusal 3 stands: MLS is the Odds API's, and the schedule carries it."""
        _sides(monkeypatch, {"soccer_usa_mls"}, {"soccer_usa_mls"})
        league = await pmm.venue_placed_league(
            object(), "LAFC", "FC Dallas", "soccer_other",
            _Market(slug="mls-lafc-dal-2026-10-04"),
        )
        assert league is None

    @pytest.mark.asyncio
    async def test_no_venue_signal_costs_no_round_trip(self, monkeypatch):
        calls = _sides(monkeypatch, {UNL}, {UNL})
        league = await pmm.venue_placed_league(
            object(), "Portugal", "Norway", "soccer_other", _Market(slug=None),
        )
        assert league is None
        assert calls == []


# ═══ 3/4. The real create flow ═══════════════════════════════════════════════
#
# Production shape around the day the specimen was minted (2026-09-21): the
# Nations League's schedule-born fixtures ran to 09-29 and nothing after, so
# #6392's guard refuses a 10-04 kickoff — nothing after it, a 5-day block, and
# no fixture of its own within 3 days. The same schedule is exactly what let
# France v Italy (10-02, 3.0 days past 09-29) be placed on 09-19, so the rig
# reproduces BOTH production outcomes. The World Cup's last fixture was the
# 07-19 final.

MINTED = _utc("2026-09-21 10:22:24")
UNL_SCHEDULE = [
    ScheduleRow(UNL, _utc(f"2026-09-{d} 18:45:00"), "espn")
    for d in (24, 25, 26, 27, 28, 29)
]
WC_SCHEDULE = [
    ScheduleRow(WC, _utc(f"2026-07-{d} 19:00:00"), "odds_api")
    for d in ("04", "09", 14, 15, 18, 19)
]


class _CreateMarket:
    def __init__(self, name, kickoff, slug):
        self.source = "polymarket"
        self.external_id = "0x5576"
        self.name = name
        self.commence_time = kickoff
        self.llm_sport_category = None
        self.market_metadata = {SLUG_FIELD: slug} if slug else {}
        self.event_id = None


class _Matchup:
    def __init__(self, a, b):
        self.team_a = a
        self.team_b = b
        self.yes_team = a
        self.format_type = "vs"


class _Created:
    def __init__(self):
        self.identity = None

    async def __call__(self, session, identity, *args, **kwargs):
        self.identity = identity
        return type("E", (), {"id": 999, "sport_id": 1})(), True


async def _none(*args, **kwargs):
    return None


async def _drive(monkeypatch, a, b, kickoff, slug, sides, now=MINTED):
    """The real create flow; only the club tables, coverage and the registry
    are faked. The season guard runs for real against ``PredicateSession``."""
    created = _Created()

    async def fake_sides(session, team_a, team_b, sport_key):
        if not sport_key or not sport_key.endswith("_other"):
            return None
        return [set(sides[0]), set(sides[1])]

    monkeypatch.setattr(
        pmm, "_polymarket_container_sibling_event_id", lambda s, m: _none()
    )
    monkeypatch.setattr(pmm, "covered_league_for_matchup", lambda s, x, y: _none())
    monkeypatch.setattr(pmm, "leagues_by_side_for_matchup", fake_sides)
    monkeypatch.setattr(
        pmm, "auto_create_sport_key_from_category", lambda category: "soccer_other"
    )
    monkeypatch.setattr(event_registry, "find_or_create_event", created)
    session = PredicateSession(UNL_SCHEDULE + WC_SCHEDULE)
    await pmm._create_event_from_prediction_market(
        session, _Matchup(a, b), _CreateMarket(f"{a} vs. {b}", kickoff, slug), now
    )
    assert (
        created.identity is not None
    ), "the create flow returned before the registry — this measured nothing"
    return created.identity.sport_key


PORTUGAL_NORWAY = ("Portugal", "Norway", _utc("2026-10-04 18:45:00"))
CROATIA_ENGLAND = ("Croatia", "England", _utc("2026-10-03 16:00:00"))
GREECE_GERMANY = ("Greece", "Germany", _utc("2026-10-04 18:45:00"))
IRELAND_ISRAEL = ("Republic of Ireland", "Israel", _utc("2026-10-04 18:45:00"))


class TestTheCreateFlow:
    # The specimen: two shared competitions AND a season-guard refusal.
    @pytest.mark.asyncio
    async def test_portugal_v_norway_is_filed_under_the_nations_league(
        self, monkeypatch
    ):
        a, b, kickoff = PORTUGAL_NORWAY
        key = await _drive(
            monkeypatch, a, b, kickoff, "unl-prt-nor-2026-10-04",
            ({WC, UNL}, {WC, UNL}),
        )
        assert key == UNL

    @pytest.mark.asyncio
    async def test_control_without_the_venue_it_stays_on_other_soccer(
        self, monkeypatch
    ):
        a, b, kickoff = PORTUGAL_NORWAY
        key = await _drive(monkeypatch, a, b, kickoff, None, ({WC, UNL}, {WC, UNL}))
        assert key == "soccer_other"

    # The 45: one shared league, refused by the season guard alone.
    @pytest.mark.asyncio
    async def test_the_season_guard_arm_is_answered_by_the_venue(self, monkeypatch):
        a, b, kickoff = GREECE_GERMANY
        key = await _drive(
            monkeypatch, a, b, kickoff, "unl-grc-ger-2026-10-04", ({UNL}, {UNL}),
        )
        assert key == UNL

    @pytest.mark.asyncio
    async def test_control_the_season_guard_refuses_it_without_the_venue(
        self, monkeypatch
    ):
        """Proves the rig reaches #6392's refusal: same clubs, same schedule,
        no slug — if this ever places, the test above measures nothing."""
        a, b, kickoff = GREECE_GERMANY
        key = await _drive(monkeypatch, a, b, kickoff, None, ({UNL}, {UNL}))
        assert key == "soccer_other"

    @pytest.mark.asyncio
    async def test_control_the_clubs_place_it_once_the_schedule_is_near(
        self, monkeypatch
    ):
        """And the guard is the ONLY thing refusing it: a 10-02 kickoff sits
        within 3 days of the 09-29 fixtures and the clubs place it unaided —
        France v Italy, placed 09-19."""
        key = await _drive(
            monkeypatch, "France", "Italy", _utc("2026-10-02 18:45:00"), None,
            ({UNL}, {UNL}), now=_utc("2026-09-19 10:22:22"),
        )
        assert key == UNL

    # The 6: one side our tables cannot name.
    @pytest.mark.asyncio
    async def test_an_unresolvable_side_is_answered_by_the_venue(self, monkeypatch):
        a, b, kickoff = IRELAND_ISRAEL
        key = await _drive(
            monkeypatch, a, b, kickoff, "unl-irl-isr-2026-10-04", (set(), {UNL}),
        )
        assert key == UNL

    @pytest.mark.asyncio
    async def test_control_an_unresolvable_side_stays_without_the_venue(
        self, monkeypatch
    ):
        a, b, kickoff = IRELAND_ISRAEL
        key = await _drive(monkeypatch, a, b, kickoff, None, (set(), {UNL}))
        assert key == "soccer_other"

    # #6392's and #8636's specimens are untouched.
    @pytest.mark.asyncio
    async def test_a_friendly_is_not_filed_into_a_finished_world_cup(
        self, monkeypatch
    ):
        key = await _drive(
            monkeypatch, "France", "Canada", _utc("2026-09-17 19:00:00"),
            "fif-fra-can-2026-09-17", ({WC, UNL}, {WC}),
            now=_utc("2026-09-10 10:00:00"),
        )
        assert key == "soccer_other"

    @pytest.mark.asyncio
    async def test_a_nations_league_slug_does_not_place_where_no_side_plays(
        self, monkeypatch
    ):
        key = await _drive(
            monkeypatch, "Poland", "Romania", _utc("2026-10-02 18:45:00"),
            "unl-pol-rou-2026-10-02", ({WCQ}, {WCQ}),
        )
        assert key == "soccer_other"


class TestThePlacerIsUnchanged:
    """The split-out read returns what the placer used to read inline."""

    @pytest.mark.asyncio
    async def test_the_placer_still_refuses_two_shared_competitions(
        self, monkeypatch
    ):
        _sides(monkeypatch, {WC, UNL}, {WC, UNL})
        assert (
            await pmm.placeable_league_for_matchup(
                object(), "Portugal", "Norway", "soccer_other"
            )
            is None
        )

    @pytest.mark.asyncio
    async def test_the_placer_still_places_one_shared_competition(
        self, monkeypatch
    ):
        _sides(monkeypatch, {UNL}, {WC, UNL})
        assert (
            await pmm.placeable_league_for_matchup(
                object(), "France", "Italy", "soccer_other"
            )
            == UNL
        )

    @pytest.mark.asyncio
    async def test_the_read_asks_nothing_without_a_catch_all(self):
        for key in ("soccer_epl", "_other", "", None):
            assert (
                await pmm.leagues_by_side_for_matchup(object(), "A", "B", key)
                is None
            )
        assert (
            await pmm.leagues_by_side_for_matchup(None, "A", "B", "soccer_other")
            is None
        )
