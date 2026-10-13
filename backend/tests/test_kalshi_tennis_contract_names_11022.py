"""#11022 — a Kalshi tennis match joins Polymarket's row for it when the two
venues shorten a compound surname differently.

Production, 2026-10-13 08:16Z: `KXATPCHALLENGERMATCH-26OCT13JUSHUE` ("Justo vs
Huertas Del Pino Cordova", contracts "Guido Ivan Justo" / "Arklon Huertas Del
Pino Cordova") retrieved 15329605 ("Guido Justo" / "Arklon Del Pino",
`tennis_other`, minted from Polymarket 39 minutes earlier, the user-supplied
`atp-justo-pin-2026-10-13` condition) inside its window and refused it with
verdict `name_mismatch` (receipt 11275879). It then minted 15329612, so the
Santa Cruz 2 match lived on two live pages, Kalshi on one and Polymarket on the
other.

The decision is asserted through `_score_candidates` (the gate the matcher
calls) and through both attempt paths, and every acceptance is paired with the
refusal it must NOT loosen: the other match with a shared surname, the wrong
first name, the wrong tour, a doubles row, an ambiguous contract pair, and a
non-tennis or non-Kalshi market.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.tasks import prediction_market_matching as pmm
from app.tasks.prediction_market_matching import _score_candidates
from app.utils.match_receipts import MatchReceipt
from app.utils.prediction_market_matching import (
    MatchupInfo,
    extract_game_date_from_ticker,
    extract_matchup_with_ticker_fallback,
    is_kalshi_tennis_match_ticker,
    kalshi_contract_name_matchup,
)

TICKER = "KXATPCHALLENGERMATCH-26OCT13JUSHUE"
NAME = "Justo vs Huertas Del Pino Cordova"
CONTRACTS = ["Guido Ivan Justo", "Arklon Huertas Del Pino Cordova"]
#: When the Kalshi market was matched on production.
NOW = datetime(2026, 10, 13, 8, 16, 53, tzinfo=timezone.utc)
#: Where 15329605 stood at that moment (receipt candidate commence_time).
PM_START = datetime(2026, 10, 13, 19, 30, tzinfo=timezone.utc)


def _title():
    return extract_matchup_with_ticker_fallback(NAME, external_id=TICKER)


def _event(eid, home, away, sport_key="tennis_other", commence=PM_START):
    return SimpleNamespace(
        id=eid,
        sport=SimpleNamespace(key=sport_key),
        home_team_name=home,
        away_team_name=away,
        commence_time=commence,
        status="scheduled",
        external_id=None,  # both specimen rows are id-less mints
        sport_id=1,
    )


def _market(ticker=TICKER, name=NAME, source="kalshi"):
    return SimpleNamespace(
        id=65633052, external_id=ticker, name=name, source=source,
        llm_sport_category="tennis", commence_time=None,
    )


def _score(candidates, matchup):
    return _score_candidates(
        candidates, matchup, _market(), NOW, extract_game_date_from_ticker(TICKER),
    )


SPECIMEN = lambda: _event(15329605, "Guido Justo", "Arklon Del Pino")  # noqa: E731


class TestTheContractMatchup:
    def test_the_specimen_contracts_rename_both_title_sides(self):
        m = kalshi_contract_name_matchup(_title(), CONTRACTS)
        assert m is not None
        assert (m.team_a, m.team_b) == ("Guido Ivan Justo", "Arklon Huertas Del Pino Cordova")
        assert m.yes_team == "Guido Ivan Justo", "yes_team follows its title side"
        assert m.format_type == _title().format_type

    def test_contract_order_does_not_matter(self):
        m = kalshi_contract_name_matchup(_title(), list(reversed(CONTRACTS)))
        assert (m.team_a, m.team_b) == ("Guido Ivan Justo", "Arklon Huertas Del Pino Cordova")

    @pytest.mark.parametrize("contracts", [
        ["Guido Ivan Justo"],                                       # one contract
        CONTRACTS + ["Someone Else"],                               # a third name
        ["Yes", "No"],                                              # not players
        ["Guido Ivan Justo", "Guido Ivan Justo"],                   # one player twice
        ["Guido Ivan Justo", "Juan Pablo Ficovich"],                # side B named by neither
        ["Guido Justo Huertas Del Pino Cordova", "Arklon Huertas Del Pino Cordova"],  # one names both
        [],
        None,
    ])
    def test_anything_but_the_titles_two_players_one_each_is_refused(self, contracts):
        assert kalshi_contract_name_matchup(_title(), contracts) is None

    def test_a_one_sided_title_gets_no_contract_matchup(self):
        one_sided = MatchupInfo("Justo", "", "Justo", "will_win")
        assert kalshi_contract_name_matchup(one_sided, CONTRACTS) is None

    def test_only_kalshi_tennis_match_series_qualify(self):
        assert is_kalshi_tennis_match_ticker(TICKER)
        assert is_kalshi_tennis_match_ticker("KXWTAMATCH-26SEP25SAKGIB")
        assert not is_kalshi_tennis_match_ticker("KXATPSETWINNER-26OCT13JUSHUE-1")
        assert not is_kalshi_tennis_match_ticker("KXMLBGAME-26AUG291610KCCLE")
        assert not is_kalshi_tennis_match_ticker(None)


class TestTheGate:
    def test_before_the_title_alone_refuses_the_polymarket_row(self):
        """The defect, reproduced: this is the receipt's `name_mismatch`."""
        assert _score([SPECIMEN()], _title()) is None

    def test_after_the_contract_names_link_it_home_side_correct(self):
        result = _score([SPECIMEN()], kalshi_contract_name_matchup(_title(), CONTRACTS))
        assert result is not None and result["event_id"] == 15329605
        assert result["yes_is_home"] is True, "Justo is the home side of 15329605"

    def test_a_reversed_row_orients_the_other_way(self):
        row = _event(7, "Arklon Del Pino", "Guido Justo")
        result = _score([row], kalshi_contract_name_matchup(_title(), CONTRACTS))
        assert result is not None and result["yes_is_home"] is False

    @pytest.mark.parametrize("home,away,why", [
        ("Guido Justo", "Juan Del Pino", "same surname, another player"),
        ("Federico Justo", "Arklon Del Pino", "same surname, another first name"),
        ("Guido Justo/Tomas Lopez", "Arklon Del Pino/Ivan Diaz", "the doubles match"),
        ("Guido Justo", "Mateus Alves", "another match of one player"),
    ])
    def test_other_matches_stay_refused(self, home, away, why):
        result = _score([_event(9, home, away)], kalshi_contract_name_matchup(_title(), CONTRACTS))
        assert result is None, why

    def test_the_wrong_tour_stays_refused(self):
        row = _event(10, "Guido Justo", "Arklon Del Pino", sport_key="tennis_wta")
        assert _score([row], kalshi_contract_name_matchup(_title(), CONTRACTS)) is None


class _Session:
    """Answers the one outcome-name read; counts every query."""

    def __init__(self, names):
        self.names = names
        self.executed = 0

    async def execute(self, _stmt):
        self.executed += 1
        names = self.names
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: list(names)))


def _wire(monkeypatch, *, contract_hit):
    finds, links = [], []

    async def fake_find(session, matchup, market, now, game_date_override=None,
                        *, receipt=None, probe_allowed=False):
        finds.append(SimpleNamespace(
            matchup=matchup, game_date=game_date_override, probe_allowed=probe_allowed,
        ))
        if contract_hit and matchup.team_a == "Guido Ivan Justo":
            return {"event_id": 15329605, "home_team": "Guido Justo",
                    "away_team": "Arklon Del Pino", "yes_is_home": True,
                    "score": 30, "sport_id": 1}
        return None

    async def fake_link(session, market, matchup, matched_event, stats, *a, **k):
        links.append((matchup, matched_event))

    monkeypatch.setattr(pmm, "_find_matching_event", fake_find)
    monkeypatch.setattr(pmm, "_try_link_market", fake_link)
    return finds, links


def _receipt(market):
    return MatchReceipt(
        market_id=market.id, source=market.source, external_id=market.external_id,
        market_name=market.name, phase="pass1_ticker", attempted_at=NOW,
    )


def _stats():
    return {"funnel": {}}


async def _attempt(session, market, receipt, stats):
    await pmm._attempt_ticker_market(
        session, market, receipt, stats, NOW, [], lambda: 999.0,
    )


class TestTheTickerPassWiring:
    @pytest.mark.asyncio
    async def test_the_specimen_links_under_its_contract_names(self, monkeypatch):
        finds, links = _wire(monkeypatch, contract_hit=True)
        market, stats = _market(), _stats()
        receipt = _receipt(market)
        await _attempt(_Session(CONTRACTS), market, receipt, stats)

        assert [f.matchup.team_a for f in finds] == ["Justo", "Guido Ivan Justo"]
        second = finds[1]
        assert second.game_date == finds[0].game_date, "same ticker window, never a wider one"
        assert second.probe_allowed is False
        (matchup, matched), = links
        assert matched["event_id"] == 15329605
        assert matchup.team_b == "Arklon Huertas Del Pino Cordova"
        assert receipt.detail["contract_name_pass"]["matched_event_id"] == 15329605
        assert stats["funnel"]["contract_name_linked"] == 1

    @pytest.mark.asyncio
    async def test_no_contract_match_mints_from_the_title_as_before(self, monkeypatch):
        finds, links = _wire(monkeypatch, contract_hit=False)
        market = _market()
        receipt = _receipt(market)
        await _attempt(_Session(CONTRACTS), market, receipt, _stats())
        (matchup, matched), = links
        assert matched is None
        assert (matchup.team_a, matchup.team_b) == ("Justo", "Huertas Del Pino Cordova")
        assert receipt.detail["contract_name_pass"]["matched_event_id"] is None

    @pytest.mark.asyncio
    async def test_a_non_tennis_ticker_reads_no_outcomes_and_searches_once(self, monkeypatch):
        finds, links = _wire(monkeypatch, contract_hit=True)
        market = _market(ticker="KXMLBGAME-26AUG291610KCCLE", name="Kansas City vs Cleveland")
        session = _Session(["Kansas City Royals", "Cleveland Guardians"])
        await _attempt(session, market, _receipt(market), _stats())
        assert session.executed == 0
        assert len(finds) == 1

    @pytest.mark.asyncio
    async def test_a_title_match_never_reads_the_contracts(self, monkeypatch):
        finds, links = _wire(monkeypatch, contract_hit=True)

        async def title_hits(session, matchup, *a, **k):
            finds.append(matchup)
            return {"event_id": 1, "home_team": "x", "away_team": "y",
                    "yes_is_home": True, "score": 30, "sport_id": 1}

        monkeypatch.setattr(pmm, "_find_matching_event", title_hits)
        session = _Session(CONTRACTS)
        market = _market()
        await _attempt(session, market, _receipt(market), _stats())
        assert session.executed == 0 and len(finds) == 1


class TestTheBacklogPassWiring:
    @pytest.mark.asyncio
    async def test_the_general_attempt_retries_on_contract_names_too(self, monkeypatch):
        """Pass 3 takes Kalshi rows Pass 1 yielded on; it must not mint the twin."""
        finds, links = _wire(monkeypatch, contract_hit=True)
        market = SimpleNamespace(**vars(_market()), category="championship")
        stats = {"funnel": {"game_level_detected": 0, "no_matchup_extracted": 0,
                            "not_game_level": 0, "sample_not_game_level": []}}
        await pmm._run_one_attempt(
            _Session(CONTRACTS), market, _receipt(market), stats, NOW, [], lambda: 999.0,
        )
        (matchup, matched), = links
        assert matched is not None and matched["event_id"] == 15329605
        assert matchup.team_a == "Guido Ivan Justo"

    @pytest.mark.asyncio
    async def test_a_polymarket_market_is_never_retried(self, monkeypatch):
        finds, links = _wire(monkeypatch, contract_hit=True)
        market = SimpleNamespace(
            **vars(_market(ticker="0xabc", name="Santa Cruz 2: Guido Justo vs Arklon Del Pino",
                           source="polymarket")),
            category="game_prop",
        )
        session = _Session(CONTRACTS)
        stats = {"funnel": {"game_level_detected": 0, "no_matchup_extracted": 0,
                            "not_game_level": 0, "sample_not_game_level": []}}
        await pmm._run_one_attempt(session, market, _receipt(market), stats, NOW, [], lambda: 999.0)
        assert len(finds) <= 1
        assert session.executed == 0
