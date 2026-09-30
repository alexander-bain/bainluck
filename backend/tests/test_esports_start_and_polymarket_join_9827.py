"""#9827 — an esports match page shows its real start and carries Polymarket.

## What a reader saw, on production (2026-09-30 12:37Z)

`/events/15321207` (CS2, Passion Academy v Revenge) read "Oct 1, 2026 · 7:30 AM
PDT" for a match that starts at 3:30 AM PDT, and drew a Kalshi-only line:

* Kalshi's ticker `KXCS2GAME-26OCT010630PSNAREV` names 06:30 US Eastern
  (10:30Z), and Polymarket's `gameStartTime` for `cs2-rev-psna-2026-10-01` says
  10:30Z too. The row said 14:30Z: Kalshi's `occurrence_datetime`, the expected
  EXPIRATION. 404 of the Kalshi esports rows minted in 10 days sat exactly
  +4.00h after their ticker, none at 0.
* Polymarket's match winner (63428729, Gamma `moneyline`) sat unlinked with
  `pass2_general · rejected · not_game_level`: nothing reads
  "<Game>: A vs B (BOn) - <Tournament>".

## What this file gates

* the mint: a Kalshi esports ticker carrying HHMM dates its row at the ticker's
  real instant, stamped `kalshi_ticker_time`, and that stamp is a reported
  start, not occurrence-timed, and market-born everywhere the house lists them;
* the title: `esports_winner_matchup_name` reads the match and refuses every
  derivative title Gamma labels (the real production names below);
* the join: an esports winner with Gamma's exact `moneyline` label searches on
  `A vs B` and may only JOIN — `allow_create=False` — and #2947's decision that
  these titles never mint is untouched.
"""

from datetime import datetime, timezone

import pytest

from app.tasks import prediction_market_matching as pmm
from app.utils import match_receipts as _receipts
from app.utils.event_completion import (
    KALSHI_TICKER_TIME_COMMENCE_SOURCE,
    commence_time_is_a_reported_start,
)
from app.utils.kalshi_occurrence_start import KALSHI_OCCURRENCE_TIMED_SOURCES
from app.utils.prediction_market_matching import (
    esports_winner_matchup_name,
    extract_matchup,
    is_game_level_market,
)

UTC = timezone.utc
NOW = datetime(2026, 9, 30, 12, 37, tzinfo=UTC)
ROW = 15321207
GAME_TICKER = "KXCS2GAME-26OCT010630PSNAREV"
MAP_TICKER = "KXCS2MAP-26OCT010630PSNAREV-2"
REAL_START = datetime(2026, 10, 1, 10, 30, tzinfo=UTC)  # 06:30 EDT
EXPECTED_EXPIRATION = datetime(2026, 10, 1, 14, 30, tzinfo=UTC)  # what the row held
PM_SPECIMEN = "Counter-Strike: Revenge vs Passion Academy (BO3) - United21 Group B"


class _Kalshi:
    def __init__(self, external_id=GAME_TICKER, commence_time=EXPECTED_EXPIRATION):
        self.source = "kalshi"
        self.external_id = external_id
        self.commence_time = commence_time
        self.market_metadata = {}


# ═══ 1. The mint: the ticker's instant, not the expected expiration ═════════


class TestAnEsportsTickerMintsAtItsRealStart:
    @pytest.mark.parametrize(
        "ticker, stored, late_h",
        [
            (GAME_TICKER, EXPECTED_EXPIRATION, 4),
            # The map leg's own occurrence is 13:30Z; the ticker is the same.
            (MAP_TICKER, datetime(2026, 10, 1, 13, 30, tzinfo=UTC), 3),
            ("KXLOLGAME-26SEP300900TOSFEC", datetime(2026, 9, 30, 17, 0, tzinfo=UTC), 4),
            ("KXVALORANTGAME-26OCT010500TYLOOTL", datetime(2026, 10, 1, 13, 0, tzinfo=UTC), 4),
        ],
    )
    def test_production_specimens_take_the_ticker_instant(self, ticker, stored, late_h):
        chosen, source = pmm.auto_create_commence_time(_Kalshi(ticker, stored), stored)

        assert source == KALSHI_TICKER_TIME_COMMENCE_SOURCE
        assert chosen == pmm.ticker_start_utc(pmm.extract_game_date_from_ticker(ticker))
        assert (stored - chosen).total_seconds() == late_h * 3600

    def test_the_specimen_is_ten_thirty_utc_not_the_eastern_clock(self):
        """The ONE Eastern→UTC conversion is used — 06:30Z would be the carrier."""
        chosen, _ = pmm.auto_create_commence_time(_Kalshi(), EXPECTED_EXPIRATION)
        assert chosen == REAL_START

    def test_a_fallback_already_at_the_start_is_left_alone(self):
        assert pmm.auto_create_commence_time(_Kalshi(), REAL_START) == (REAL_START, None)

    @pytest.mark.parametrize(
        "market",
        [
            # Another sport's HHMM ticker, 30 min off its first pitch: untouched.
            _Kalshi("KXMLBGAME-26OCT011905NYYBOS", datetime(2026, 10, 1, 23, 35, tzinfo=UTC)),
            # A date-only esports ticker names no time of day to place.
            _Kalshi("KXCS2GAME-26OCT01PSNAREV", EXPECTED_EXPIRATION),
        ],
    )
    def test_what_the_arm_does_not_reach(self, market):
        chosen, source = pmm.auto_create_commence_time(market, market.commence_time)
        assert source != KALSHI_TICKER_TIME_COMMENCE_SOURCE
        assert chosen == market.commence_time

    def test_polymarket_never_takes_the_arm(self):
        market = _Kalshi()
        market.source = "polymarket"
        assert pmm.auto_create_commence_time(market, EXPECTED_EXPIRATION) == (
            EXPECTED_EXPIRATION, None,
        )


class TestTheStampSaysWhatItIs:
    def test_a_clock_may_run_from_it(self):
        """A published time of day — the row goes live at the start, not the end."""
        assert commence_time_is_a_reported_start(KALSHI_TICKER_TIME_COMMENCE_SOURCE)

    def test_no_reader_treats_it_as_the_expected_expiration(self):
        """`kalshi` would have told every chart/rail reader 'this is the far end'."""
        assert KALSHI_TICKER_TIME_COMMENCE_SOURCE not in KALSHI_OCCURRENCE_TIMED_SOURCES

    def test_it_is_market_born_in_every_list(self):
        from app.services.anchor_channel import MARKET_BORN_COMMENCE_SOURCES as drain
        from app.utils.search_fixture_dedup import MARKET_BORN_COMMENCE_SOURCES as search

        for members in (drain, search, pmm.MARKET_BORN_COMMENCE_SOURCES):
            assert KALSHI_TICKER_TIME_COMMENCE_SOURCE in members

    def test_it_ranks_with_kalshi_so_a_schedule_still_corrects_it(self):
        from app.services.event_registry import (
            _SOURCE_PRIORITY,
            commence_time_write_authorized,
        )

        assert _SOURCE_PRIORITY[KALSHI_TICKER_TIME_COMMENCE_SOURCE] == _SOURCE_PRIORITY["kalshi"]
        assert commence_time_write_authorized(KALSHI_TICKER_TIME_COMMENCE_SOURCE, "espn")[0]
        assert not commence_time_write_authorized("espn", KALSHI_TICKER_TIME_COMMENCE_SOURCE)[0]


class _Matchup:
    def __init__(self, team_a, team_b):
        self.team_a = team_a
        self.team_b = team_b


async def test_the_call_site_hands_the_registry_the_real_start(monkeypatch):
    """Ruling 102 obligation 4: the minter itself, not only the helper."""
    import app.services.event_registry as registry
    from app.tasks.prediction_market_matching import _create_event_from_prediction_market

    seen = {}

    async def _capture(session, identity):
        seen["identity"] = identity
        raise ValueError("stop here — the identity is what this test reads")

    monkeypatch.setattr(registry, "find_or_create_event", _capture)
    market = _Kalshi()
    market.name = "Passion Academy vs. Revenge"
    market.llm_sport_category = None
    market.id = 63398000

    await _create_event_from_prediction_market(
        None, _Matchup("Passion Academy", "Revenge"), market,
        datetime(2026, 9, 29, 0, 55, tzinfo=UTC),
    )

    identity = seen["identity"]
    assert identity.commence_time == REAL_START
    assert identity.commence_time_source == KALSHI_TICKER_TIME_COMMENCE_SOURCE
    assert identity.status == "scheduled"
    assert identity.claim.schedule_derived is False  # ruling 048 untouched


# ═══ 2. The title ═══════════════════════════════════════════════════════════


class TestTheTitleReadsTheMatch:
    @pytest.mark.parametrize(
        "name, expected",
        [
            (PM_SPECIMEN, "Revenge vs Passion Academy"),
            ("LoL: T1 vs Gen.G (BO5)", "T1 vs Gen.G"),
            ("Dota 2: Team Spirit vs 1win (BO3) - BLAST Slam Group B",
             "Team Spirit vs 1win"),
            # A tournament that holds its own colon (the accident that linked).
            ("Counter-Strike: KUUSAMO.gg vs Noir Verse (BO3) - CCT Europe Closed "
             "Qualifier: Series #10 Group D", "KUUSAMO.gg vs Noir Verse"),
            # A tournament that holds a word the refusal must not misread.
            ("Valorant: 100 Thieves vs FUT Esports (BO3) - VCT Game Changers: "
             "Winners Bracket", "100 Thieves vs FUT Esports"),
        ],
    )
    def test_production_winner_titles(self, name, expected):
        assert esports_winner_matchup_name(name) == expected
        matchup = extract_matchup(expected)
        assert matchup is not None and matchup.team_b

    @pytest.mark.parametrize(
        "name",
        [
            # Every real derivative title Gamma labels, read 2026-09-30.
            "Counter-Strike: ALKA vs METANOIA WOLVES - Map 1 Winner",
            "Game Handicap: 1WIN (-1.5) vs Natus Vincere (+1.5)",
            "Map 1 Total Rounds: Over/Under 15.5",
            "Games Total: O/U 2.5",
            "Game 1: Odd/Even Total Kills?",
            "Total Kills Over/Under 18.5 in Game 4?",
            "First Blood in Game 1?",
            "Game 1: Any Player Rampage?",
            # The marker with a derivative tail, both vocabularies.
            "Counter-Strike: Revenge vs Passion Academy (BO3) - Map 1 Winner",
            "Counter-Strike: Revenge vs Passion Academy (BO3) - Games Total",
            "Counter-Strike: Revenge vs Passion Academy (BO3) - Map Handicap",
            # No game title, or no matchup behind it.
            "Revenge vs Passion Academy (BO3)",
            "Counter-Strike: Revenge (BO3) - United21 Group B",
            "",
        ],
    )
    def test_everything_else_refuses(self, name):
        assert esports_winner_matchup_name(name) is None

    def test_the_raw_title_still_cannot_mint(self):
        """#2947's non-decision stands: nothing about the RAW title moved."""
        assert not is_game_level_market(PM_SPECIMEN, "game_prop")
        assert extract_matchup(PM_SPECIMEN) is None


# ═══ 3. The join ════════════════════════════════════════════════════════════


def _understanding(venue_type):
    cu = {"v": 1, "semantic_type": "moneyline", "rule": "content_understanding@5273"}
    if venue_type is not None:
        cu["venue_type"] = venue_type
        cu["agreement"] = "corroborated"
    else:
        cu["agreement"] = "unconfirmed"
    return {
        "content_understanding_v1": cu,
        "venue_game_start": "2026-10-01T10:30:00+00:00",
        "polymarket_event_id": "1107298",
    }


class _Polymarket:
    def __init__(self, *, name=PM_SPECIMEN, venue_type="moneyline",
                 sport="esports", source="polymarket"):
        self.id = 63428729
        self.name = name
        self.source = source
        self.category = "game_prop"
        self.group_id = "polymarket:1107298"
        self.group_type = "polymarket_sub_market"
        self.external_id = "0x71dc04570c0888c7ed82"
        self.event_id = None
        self.sport_id = None
        self.llm_sport_category = sport
        self.commence_time = None
        self.market_metadata = _understanding(venue_type)


class TestTheVenueLabelGatesTheRead:
    def test_the_specimen(self):
        assert pmm._venue_moneyline_match_name(_Polymarket()) == "Revenge vs Passion Academy"

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"venue_type": None},  # the group's container: unlabelled
            {"venue_type": "child_moneyline"},  # a map winner — exact match only
            {"venue_type": "totals", "name": "Games Total: O/U 2.5"},
            {"source": "kalshi"},
            {"sport": "soccer"},
            {"name": "Counter-Strike: ALKA vs METANOIA WOLVES - Map 1 Winner"},
        ],
    )
    def test_each_missing_signal_refuses(self, kwargs):
        assert pmm._venue_moneyline_match_name(_Polymarket(**kwargs)) is None

    def test_the_tennis_read_is_unchanged(self):
        """#9494's path, control: a city-labelled tennis moneyline still reads."""
        market = _Polymarket(
            name="Curitiba: Ryan Dickerson vs Jose Pereira", sport="tennis",
        )
        assert pmm._venue_moneyline_match_name(market) == "Ryan Dickerson vs Jose Pereira"


def _stats():
    return {
        "markets_scanned": 0,
        "newly_linked": 0,
        "funnel": {
            "not_game_level": 0,
            "sample_not_game_level": [],
            "linked": 0,
            "no_matchup_extracted": 0,
            "game_level_detected": 0,
            "no_event_found": 0,
            "sample_game_level_no_event": [],
        },
    }


class _Recorder:
    def __init__(self, monkeypatch, *, found=None, link_to=None):
        self.searched = []
        self.link_calls = []

        async def _no_group_row(session, market):
            return None

        async def _find(session, matchup, market, now, **kw):
            self.searched.append((matchup.team_a, matchup.team_b))
            return found

        async def _link(session, market, matchup, matched_event, stats,
                        game_date, now, queue, *, receipt=None, allow_create=True):
            self.link_calls.append(allow_create)
            if link_to is not None:
                receipt.link(link_to, how="matched_existing_event")

        monkeypatch.setattr(pmm, "_polymarket_group_sibling_event_id", _no_group_row)
        monkeypatch.setattr(pmm, "_find_matching_event", _find)
        monkeypatch.setattr(pmm, "_try_link_market", _link)


async def _attempt(market):
    stats, queue, receipts = _stats(), [], []
    await pmm._attempt_market(
        None, market, stats, NOW, queue, lambda: 600.0,
        receipts, _receipts.PHASE_PASS2_GENERAL,
    )
    return stats, receipts[0]


@pytest.mark.asyncio
class TestTheWinnerJoinsAndNeverMints:
    async def test_the_specimen_searches_the_teams_and_may_not_mint(self, monkeypatch):
        rec = _Recorder(monkeypatch, found={"event_id": ROW}, link_to=ROW)

        stats, receipt = await _attempt(_Polymarket())

        assert rec.searched == [("Revenge", "Passion Academy")]
        assert rec.link_calls == [False], "the esports winner was allowed to mint"
        assert receipt.outcome == _receipts.OUTCOME_LINKED
        assert stats["funnel"]["venue_moneyline_joins"] == 1
        assert stats["funnel"]["not_game_level"] == 0

    async def test_the_container_is_refused_before_any_search(self, monkeypatch):
        rec = _Recorder(monkeypatch, found={"event_id": ROW}, link_to=ROW)

        stats, receipt = await _attempt(_Polymarket(venue_type=None))

        assert rec.searched == [] and rec.link_calls == []
        assert receipt.outcome != _receipts.OUTCOME_LINKED
        assert stats["funnel"]["not_game_level"] == 1


def test_the_fixture_guard_judges_the_join_by_the_row_start():
    """The join lands only on a correctly-timed row: #4965's ±3h guard, unchanged,
    refuses the 4h-late rows and accepts the ones the mint now writes."""
    market = _Polymarket()
    assert pmm._venue_fixture_disagrees(market, EXPECTED_EXPIRATION) is True
    assert pmm._venue_fixture_disagrees(market, REAL_START) is False
