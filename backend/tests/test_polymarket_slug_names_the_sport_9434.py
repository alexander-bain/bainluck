"""#9434 — an Arizona Cardinals NFL game shows its Polymarket price.

Production, 2026-09-28: Cardinals @ Giants (Sun Oct 4, event 14780551) was
priced by Kalshi only while the 15 other Week 5 games carried Polymarket too.
Polymarket event 909440 (``nfl-ari-nyg-2026-10-04``, 70 markets) sat unlinked.
Receipt 7021681 shows the matcher retrieved 14780551, matched BOTH sides, and
refused it with verdict ``wrong_sport``: the market's ``llm_sport_category`` is
``baseball``, because "Cardinals" and "Giants" are MLB clubs too, and a
Polymarket market has no ticker, so the LLM's guess was the only sport
``_market_sport_prefix`` could read.

Measured over every open Polymarket game market with a US league slug code:
74 NFL markets tagged baseball (every one an Arizona Cardinals game: Oct 4,
Oct 11, Oct 18), 46 college-football markets tagged soccer/basketball/politics,
and 0 linked markets whose event's sport contradicts the code.

GUARD DESIGN. The BEFORE arm asserts the LLM tag still refuses the NFL row on
its own, so nothing but the slug can produce the link and a revert fails
here. Every relaxation is paired with the refusal it must not loosen: an
``nfl-`` market on an MLB row, an ``mlb-`` market on an NFL row, and a code
outside the map, which keeps today's answer.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.tasks.prediction_market_matching import (
    _is_cross_sport_link,
    _market_sport_prefix,
    _score_candidates,
)
from app.utils.prediction_market_matching import extract_matchup
from app.utils.sport_keys import LLM_CATEGORY_TO_SPORT_PREFIX
from app.utils.venue_competition import (
    POLYMARKET_SPORT_FAMILY_CODES,
    venue_named_sport_family,
)

#: The production moneyline, verbatim (futures_markets 62246637).
CONDITION_ID = "0x96b3caf87aeaae3cf5fe87e2faaf72c56ab4161d626a1898df469c0b02a9de62"
NAME = "Cardinals vs. Giants"
SLUG = "nfl-ari-nyg-2026-10-04"
KICKOFF = datetime(2026, 10, 4, 17, 0, tzinfo=timezone.utc)
#: When the specimen was read on production.
NOW = datetime(2026, 9, 28, 18, 5, tzinfo=timezone.utc)


def _market(slug=SLUG, llm="baseball", name=NAME, external_id=CONDITION_ID):
    meta = {"venue_game_start": KICKOFF.isoformat(), "polymarket_event_id": "909440"}
    if slug is not None:
        meta["polymarket_event_slug"] = slug
    return SimpleNamespace(
        external_id=external_id, name=name, source="polymarket",
        llm_sport_category=llm, commence_time=None, market_metadata=meta,
    )


def _event(eid, away, home, sport_key, commence=KICKOFF):
    return SimpleNamespace(
        id=eid,
        sport=SimpleNamespace(key=sport_key),
        home_team_name=home,
        away_team_name=away,
        commence_time=commence,
        status="scheduled",
        external_id=f"odds-{eid}",
        sport_id=1,
    )


#: 14780551 as it stands on production.
NFL_ROW = _event(14780551, "Arizona Cardinals", "New York Giants", "americanfootball_nfl")
#: A same-named MLB game at the same instant: the hazard in the other direction.
MLB_ROW = _event(1, "St. Louis Cardinals", "San Francisco Giants", "baseball_mlb")


def _score(market, candidates):
    return _score_candidates(
        candidates, extract_matchup(market.name, None), market, NOW, KICKOFF,
    )


class TestTheSpecimenLinks:
    def test_before_the_llm_tag_alone_refuses_the_nfl_row(self):
        """The defect at the gate, and it must keep holding after the fix: the
        tag is still wrong. Without the slug the market cannot link."""
        assert _score(_market(slug=None), [NFL_ROW]) is None

    def test_cardinals_giants_links_to_the_nfl_row(self):
        result = _score(_market(), [NFL_ROW])
        assert result is not None, (
            "the nfl- slug market refused its own game as wrong_sport (#9434)"
        )
        assert result["event_id"] == 14780551

    def test_the_nfl_row_beats_a_same_named_mlb_row(self):
        result = _score(_market(), [MLB_ROW, NFL_ROW])
        assert result is not None and result["event_id"] == 14780551

    @pytest.mark.parametrize(
        "slug", ["nfl-ari-nyg-2026-10-04-player-props",
                 "nfl-ari-nyg-2026-10-04-highest-scoring-quarter"],
    )
    def test_the_side_events_of_the_game_read_the_same_code(self, slug):
        """Two of the measured 74 carry a suffixed slug (production groups
        1098822 and 1092926)."""
        assert _market_sport_prefix(_market(slug=slug)) == "americanfootball"

    def test_a_college_game_tagged_soccer_links_to_its_ncaaf_row(self):
        """cfb-stan-wake-2026-10-03, 42 markets tagged soccer."""
        market = _market(
            slug="cfb-stan-wake-2026-10-03", llm="soccer",
            name="Stanford vs. Wake Forest",
        )
        row = _event(
            2, "Stanford Cardinal", "Wake Forest Demon Deacons",
            "americanfootball_ncaaf",
        )
        assert _score(market, [row]) is not None


class TestWhatStaysRefused:
    def test_an_nfl_market_still_refuses_the_mlb_row(self):
        assert _score(_market(), [MLB_ROW]) is None

    def test_an_mlb_market_tagged_football_refuses_the_nfl_row(self):
        """The mirror image: the slug overrules a wrong tag in BOTH directions."""
        market = _market(slug="mlb-stl-sf-2026-10-04", llm="football")
        assert _score(market, [NFL_ROW]) is None
        assert _score(market, [MLB_ROW]) is not None

    @pytest.mark.parametrize(
        "slug",
        [
            "nflx-ari-nyg-2026-10-04",   # a longer code is not the code
            "nfl-2026-mvp",              # a futures slug has no game shape
            "will-the-cardinals-win-2026-10-04",
            "",
        ],
    )
    def test_a_slug_without_a_mapped_game_code_keeps_the_llm_answer(self, slug):
        assert venue_named_sport_family({"polymarket_event_slug": slug}) is None
        assert _market_sport_prefix(_market(slug=slug)) == "baseball"

    def test_a_kalshi_ticker_still_outranks_everything(self):
        market = _market(external_id="KXMLBGAME-26OCT041300STLSF")
        assert _market_sport_prefix(market) == "baseball_mlb"

    def test_a_market_without_metadata_is_unchanged(self):
        market = SimpleNamespace(
            external_id=CONDITION_ID, name=NAME, llm_sport_category="baseball",
        )
        assert _market_sport_prefix(market) == "baseball"


def test_every_code_names_a_family_the_llm_map_can_also_name():
    """A code must yield exactly the prefix a correctly tagged market gets, so
    it faces the same gate: a family, never a narrower league key."""
    families = set(LLM_CATEGORY_TO_SPORT_PREFIX.values())
    assert set(POLYMARKET_SPORT_FAMILY_CODES.values()) <= families


@pytest.mark.parametrize(
    "code,real_key",
    [("nfl", "americanfootball_nfl"), ("cfb", "americanfootball_ncaaf"),
     ("mlb", "baseball_mlb"), ("nba", "basketball_nba"),
     ("wnba", "basketball_wnba"), ("nhl", "icehockey_nhl"),
     ("mls", "soccer_usa_mls")],
)
def test_each_code_reaches_its_own_league(code, real_key):
    family = venue_named_sport_family(
        {"polymarket_event_slug": f"{code}-aaa-bbb-2026-10-04"}
    )
    assert _is_cross_sport_link(family, real_key) is False
