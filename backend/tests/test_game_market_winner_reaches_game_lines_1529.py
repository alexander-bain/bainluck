"""#1529 reader gate — a full-game winner must reach the reader's Game lines.

Reader failure (Shopper, event 15195694, 390 px, 2026-10-21 03:57Z): the Kalshi
question "Philadelphia vs New York" was the sole question under All markets →
Other. The classifier was not the cause: `_classify_game_market` already calls
a bare-matchup winner `moneyline`. `_build_game_markets` has no branch for
`moneyline`, so its legs fall through to the `else` branch, which rescues
player-shaped legs and appends the rest to `other_markets` WITHOUT the class it
had already established. The web catalog then maps `data.other` straight to
Other — it had nothing to read the class from.

The repair is additive: an `other` row of a market the classifier called
full-game `moneyline` carries `market_type: "moneyline"` (the key every totals
and period row already carries for the same classifier answer). The rows stay in
`other[]`, so the section the app and the existing controls read is unchanged.

Cases come from the fenced fixture
`tests/evals/fixtures/1529-reader-moneyline-other.json` (Codex commit 48d8c7cd).
Its synthetic cases are guard specifications, not venue evidence; the Kalshi
ticker below is synthetic and shaped only to exercise the `…GAME` series path.
"""

import json
from pathlib import Path

import pytest

from app.routes.events import _classify_game_market
from tests.test_game_market_class_rollout_1529 import PM_HASH, _serve
from tests.test_game_markets import _make_market, _make_outcome

FIXTURE = json.loads(
    (
        Path(__file__).parent
        / "evals"
        / "fixtures"
        / "1529-reader-moneyline-other.json"
    ).read_text()
)
CASES = {c["case"]: c for c in FIXTURE["synthetic_guard_specs_not_venue_evidence"]}

NBA = dict(
    home_team_name="Philadelphia 76ers",
    away_team_name="New York Knicks",
    sport_key="basketball_nba",
)

# SYNTHETIC — not the live row's ticker, which was never read (fixture `unpaid`).
SYNTHETIC_KALSHI_GAME_TICKER = "KXNBAGAME-26OCT20NYKPHI"


def _legs(market_id, names, probability=0.5):
    return [
        _make_outcome(id=market_id * 10 + i, market_id=market_id, name=n,
                      probability=probability)
        for i, n in enumerate(names, start=1)
    ]


def test_the_fixture_is_the_one_codex_fenced():
    assert FIXTURE["issue"] == 1529
    assert FIXTURE["observed"]["catalog_family"] == "Other"
    assert FIXTURE["expected_reader_contract"]["full_game_winner_family"] == "Game lines"
    assert set(CASES) == {
        "full-game winner survives response projection",
        "same matchup name is a player-contract container",
        "segment winner is not a full-game winner",
        "unclassified question remains unknown",
    }


# ── the failure: an established winner loses its class at the response ──────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    # A DISTINCT event id per case: `/game-markets` caches by event id, and a
    # shared id serves the first case's payload to the rest (measured: the
    # Polymarket case read back `source: kalshi`).
    "event_id,source,external_id",
    [
        (9152910, "kalshi", SYNTHETIC_KALSHI_GAME_TICKER),
        (9152920, "polymarket", PM_HASH),
        (9152930, "kalshi", None),
    ],
)
async def test_a_full_game_winner_keeps_its_class_in_the_served_row(
    event_id, source, external_id
):
    case = CASES["full-game winner survives response projection"]
    market = _make_market(id=152910, name=case["market_name"],
                          external_id=external_id, source=source)
    outcomes = _legs(152910, case["outcome_names"])
    # The classifier already knew (Root's attribution correction).
    assert _classify_game_market(market.name, market.external_id) == (
        case["upstream_semantic_class"]
    )

    response = await _serve(event_id, market, outcomes, **NBA)

    rows = response["other"]
    assert [r["outcome_name"] for r in rows] == case["outcome_names"]
    assert [r.get("market_type") for r in rows] == ["moneyline", "moneyline"]
    # Nothing else about the row moves: price, source, identity.
    assert [r["probability"] for r in rows] == [0.5, 0.5]
    assert {r["source"] for r in rows} == {source}
    assert {r["_market_id"] for r in rows} == {152910}
    assert response["player_props"] == []


# ── what must NOT gain the class ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_matchup_named_player_container_still_serves_props():
    case = CASES["same matchup name is a player-contract container"]
    market = _make_market(id=152911, name=case["market_name"], external_id=PM_HASH,
                          source="polymarket")
    outcomes = _legs(152911, case["outcome_names"], probability=0.38)

    response = await _serve(9152911, market, outcomes, **NBA)

    assert response["other"] == []
    assert [p["outcome_name"] for p in response["player_props"]] == case["outcome_names"]


@pytest.mark.asyncio
async def test_a_container_leg_the_rescue_leaves_behind_is_not_called_the_winner():
    # A matchup-named market with ANY player-shaped leg is a player container,
    # whatever its title says. A sibling leg the rescue does not take (here a
    # bare "Tie") stays in Other unlabelled — never promoted to Game lines.
    market = _make_market(id=152912, name="Celtics at Warriors", external_id=PM_HASH,
                          source="polymarket")
    outcomes = _legs(152912, ["Jaylen Brown: 25+", "Tie"], probability=0.4)
    assert _classify_game_market(market.name, market.external_id) == "moneyline"

    response = await _serve(9152912, market, outcomes, **NBA)

    assert [p["outcome_name"] for p in response["player_props"]] == ["Jaylen Brown: 25+"]
    [tie] = response["other"]
    assert tie["outcome_name"] == "Tie"
    assert "market_type" not in tie


@pytest.mark.asyncio
async def test_a_segment_winner_is_not_relabelled_the_game():
    case = CASES["segment winner is not a full-game winner"]
    market = _make_market(id=152913, name=case["market_name"], external_id=PM_HASH,
                          source="polymarket", sport_category="esports")
    outcomes = _legs(152913, ["TeamA", "TeamB"])
    assert _classify_game_market(market.name, market.external_id) == (
        case["upstream_semantic_class"]
    )

    response = await _serve(9152913, market, outcomes, home_team_name="TeamA",
                            away_team_name="TeamB", sport_key="esports_cs2")

    assert response["other"], "the segment winner keeps its section"
    assert all("market_type" not in r for r in response["other"])


@pytest.mark.asyncio
async def test_an_unclassified_question_stays_unknown():
    case = CASES["unclassified question remains unknown"]
    market = _make_market(id=152914, name=case["market_name"])
    outcomes = _legs(152914, ["Yes", "No"])
    assert _classify_game_market(market.name, market.external_id) == (
        case["upstream_semantic_class"]
    )

    response = await _serve(9152914, market, outcomes, **NBA)

    assert response["other"]
    assert all("market_type" not in r for r in response["other"])


@pytest.mark.asyncio
async def test_a_period_book_titled_with_the_matchup_is_not_the_game():
    # Kalshi's first-three-innings series titled with the matchup alone, and
    # the F5 winner: both stay unlabelled in their section.
    for mid, name, ticker, legs in [
        (152915, "Rays at Braves", "KXMLBF3-26SEP091915TBATL", ["Rays", "Braves"]),
        (152916, "Los Angeles Dodgers vs Milwaukee: First 5 Innings",
         "KXMLBF5-26OCT121400LADMIL", ["Los Angeles Dodgers", "Milwaukee", "Tie"]),
    ]:
        market = _make_market(id=mid, name=name, external_id=ticker,
                              sport_category="baseball")
        response = await _serve(
            9000000 + mid, market, _legs(mid, legs, probability=0.3),
            home_team_name="Atlanta Braves", away_team_name="Tampa Bay Rays",
            sport_key="baseball_mlb",
        )
        assert [r["outcome_name"] for r in response["other"]] == legs
        assert all("market_type" not in r for r in response["other"]), name
