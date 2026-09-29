"""#9494 — a Challenger match's Polymarket moneyline joins the row Kalshi made.

## What a reader saw, on production (2026-09-28 23:34Z)

Dickerson v Pereira (ATP Challenger Curitiba, event 15320435) served Kalshi
alone. Polymarket's group `polymarket:1094815` holds the parent (62900257,
refused as `parent_row` by design) and ONE child, 62912920, "Curitiba: Ryan
Dickerson vs Jose Pereira", which Gamma labels `moneyline`. Its receipt:
`pass2_general · rejected · not_game_level`. The bare city label is not on
`_CATEGORY_PREFIX_RE`'s tournament list, and the group has no O/U sibling to
link the row first for #9450 to pull the match market onto.

## What this file gates

* the venue's `moneyline` label plus a bare matchup after the one colon reads
  the title as `A vs B`, and each missing signal refuses exactly as before;
* the attempt searches on `A vs B` and may only JOIN: `allow_create=False`;
* `_try_link_market(allow_create=False)` never reaches the minter, whether the
  finder found nothing or the fixture guard refused what it found;
* a name that was already game level still auto-creates (`allow_create=True`).
"""

from datetime import datetime, timezone

import pytest

from app.tasks import prediction_market_matching as pmm
from app.utils import match_receipts as _receipts
from app.utils.prediction_market_matching import is_game_level_market

NOW = datetime(2026, 9, 28, 23, 34, tzinfo=timezone.utc)
ROW = 15320435
SPECIMEN = "Curitiba: Ryan Dickerson vs Jose Pereira"


def _understanding(venue_type):
    cu = {"v": 1, "semantic_type": "moneyline", "rule": "content_understanding@5273"}
    if venue_type is not None:
        cu["venue_type"] = venue_type
        cu["agreement"] = "corroborated"
    else:
        cu["agreement"] = "unconfirmed"
    return {"content_understanding_v1": cu}


class _Market:
    def __init__(
        self, *, id=62912920, name=SPECIMEN, source="polymarket",
        venue_type="moneyline", sport="tennis", metadata=None,
    ):
        self.id = id
        self.name = name
        self.source = source
        self.category = "game_prop"
        self.group_id = "polymarket:1094815"
        self.group_type = "polymarket_sub_market"
        self.external_id = "0x86455ef0777d3caeae718e38f5e135f7fa874ba42664baa42a340afd03947f29"
        self.event_id = None
        self.sport_id = None
        self.llm_sport_category = sport
        self.commence_time = None
        self.market_metadata = (
            metadata if metadata is not None else _understanding(venue_type)
        )


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


class TestTheTitleIsReadOnlyWhenTheVenueSaysMoneyline:
    @pytest.mark.parametrize(
        "name, expected",
        [
            (SPECIMEN, "Ryan Dickerson vs Jose Pereira"),
            ("M15 Ann Arbor, MI: Oscar Corwin vs Danil Panarin",
             "Oscar Corwin vs Danil Panarin"),
            ("W35 Reims: Kim Chiarello vs Meline Lataste",
             "Kim Chiarello vs Meline Lataste"),
            ("M25 Setubal: Joao Silva vs Pedro Sousa", "Joao Silva vs Pedro Sousa"),
        ],
    )
    def test_production_city_labels_read_as_the_matchup(self, name, expected):
        assert not is_game_level_market(name, "game_prop"), (
            "the title is game level on its own — this path never runs for it"
        )
        assert pmm._venue_moneyline_match_name(_Market(name=name)) == expected

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"source": "kalshi"},
            {"sport": "soccer"},
            {"venue_type": None},  # absent on ~21% of markets
            {"metadata": {}},  # stamped before the record existed
            {"venue_type": "child_moneyline"},  # exact match, not containment
            {"venue_type": "tennis_first_set_winner",
             "name": "Set 1 Winner: James Connel vs Ivan Gretskiy"},
            {"venue_type": "tennis_set_handicap",
             "name": "Set Handicap: Ivan Gretskiy (-1.5) vs James Connel (+1.5)"},
            {"venue_type": "tennis_completed_match",
             "name": "Curitiba: Completed Match: Ryan Dickerson vs Jose Pereira"},
            # Two colons refuse even under a moneyline label.
            {"name": "W35 Reims, Qualifying: Completed Match: Evita Ramirez vs Julie Myatovic"},
            {"name": "Ryan Dickerson vs Jose Pereira"},  # no label to strip
            {"name": ": Ryan Dickerson vs Jose Pereira"},  # empty label
            {"name": "Curitiba: Ryan Dickerson"},  # no matchup behind it
        ],
    )
    def test_each_missing_signal_refuses(self, kwargs):
        assert pmm._venue_moneyline_match_name(_Market(**kwargs)) is None


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
class TestTheAttemptSearchesTheMatchupAndOnlyJoins:
    async def test_the_specimen_searches_on_the_players_and_may_not_mint(
        self, monkeypatch
    ):
        rec = _Recorder(monkeypatch, found={"event_id": ROW}, link_to=ROW)

        stats, receipt = await _attempt(_Market())

        assert rec.searched == [("Ryan Dickerson", "Jose Pereira")]
        assert rec.link_calls == [False], "the venue-label path was allowed to mint"
        assert receipt.outcome == _receipts.OUTCOME_LINKED
        assert stats["funnel"]["venue_moneyline_joins"] == 1
        assert stats["funnel"]["not_game_level"] == 0

    async def test_a_refused_link_is_not_counted_as_a_join(self, monkeypatch):
        rec = _Recorder(monkeypatch, found=None)

        stats, receipt = await _attempt(_Market())

        assert rec.link_calls == [False]
        assert receipt.outcome != _receipts.OUTCOME_LINKED
        assert "venue_moneyline_joins" not in stats["funnel"]

    async def test_a_market_without_the_label_is_refused_before_any_search(
        self, monkeypatch
    ):
        rec = _Recorder(monkeypatch, found={"event_id": ROW}, link_to=ROW)

        stats, receipt = await _attempt(_Market(venue_type=None))

        assert rec.searched == [] and rec.link_calls == []
        assert receipt.reject_reason == _receipts.REJECT_NOT_GAME_LEVEL
        assert stats["funnel"]["not_game_level"] == 1

    async def test_a_game_level_name_still_may_create(self, monkeypatch):
        """Control: the path the O/U line takes is unchanged, and it does not
        pass the flag at all, so every existing fake keeps its signature."""
        rec = _Recorder(monkeypatch, found=None)

        await _attempt(_Market(name="Dickerson vs. Pereira: Total Sets O/U 2.5",
                               venue_type="tennis_set_totals"))

        assert rec.link_calls == [True]


class _Session:
    async def commit(self):
        raise AssertionError("nothing may be written")


@pytest.mark.asyncio
class TestTryLinkWithoutCreateNeverMints:
    @pytest.fixture(autouse=True)
    def _no_minter(self, monkeypatch):
        async def _mint(*a, **k):
            raise AssertionError("the minter was reached")

        monkeypatch.setattr(pmm, "_create_event_from_prediction_market", _mint)

    async def _call(self, matched_event):
        from app.utils.prediction_market_matching import extract_matchup

        stats = _stats()
        market = _Market()
        receipt = pmm._new_receipt(market, _receipts.PHASE_PASS2_GENERAL, NOW)
        await pmm._try_link_market(
            _Session(), market, extract_matchup("Ryan Dickerson vs Jose Pereira"),
            matched_event, stats, None, NOW, [], receipt=receipt,
            allow_create=False,
        )
        return market, stats, receipt

    async def test_no_candidate_ends_declined(self):
        market, stats, receipt = await self._call(None)

        assert market.event_id is None
        assert receipt.reject_reason == _receipts.REJECT_AUTO_CREATE_DECLINED
        assert receipt.detail["auto_create"] == "declined"
        assert stats["funnel"]["no_event_found"] == 1

    async def test_a_fixture_refused_candidate_does_not_fall_through_to_mint(
        self, monkeypatch
    ):
        async def _refuse(session, event_id, market, ticker_game_date):
            return pmm._REFUSAL_VENUE_FIXTURE

        monkeypatch.setattr(pmm, "_check_duplicate_kalshi_linkage_reason", _refuse)

        market, stats, receipt = await self._call(
            {"event_id": ROW, "home_team": "Dickerson", "away_team": "Pereira"}
        )

        assert market.event_id is None
        # The more specific refusal stays THE reason.
        assert receipt.reject_reason == _receipts.REJECT_EVENT_DATE_CONFLICT
        assert receipt.detail["auto_create"] == "declined"
