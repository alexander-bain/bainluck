"""#1529 — the shared game-market recognizer rolled into the game-page classifier.

`routes/events.py::_classify_game_market` re-implemented game-winner recognition
and only rescued a bare-matchup title through a Kalshi `…GAME` ticker, so every
Polymarket "Yankees vs. Red Sox" winner was labelled `other`. Three gaps rode
with it, and each is pinned here per sport with a healthy control beside it:

  * A period named only by its Kalshi ticker ("Rays at Braves" on `KXMLBRFI`,
    the first inning) must never be read as the game by the title rescue.
    Kalshi's F5 winner ("Los Angeles Dodgers vs Milwaukee: First 5 Innings",
    `KXMLBF5-…`) is labelled a segment and keeps the `other` SECTION: the web
    renders it there as a readable three-way card, and `period_markets` would
    bury it (production LOOK, event 15329040, 2026-10-12).
  * Map / set / numbered-period winners were labelled `moneyline` (they carry
    the word) or `other` (they do not). They are `segment_winner` now — and stay
    in the `other` section the web and the app already render them in.
  * The admin calibration-by-type CASE knew only `KXNHLGAME`.

What must NOT move is pinned just as hard: the player-contract rescue of a
bare-matchup container, the "- Player Props" container, the shared classifier's
own answers (the blend, settlement and stored understanding read those), and a
period that only its Kalshi ticker names.
"""

import inspect
from unittest.mock import AsyncMock

import pytest

from app.routes import admin_data_quality
from app.routes.events import (
    _PM_PERIOD_SCOPES,
    _PM_SCOPES_DEFERRING_TO_OUTCOMES,
    _classify_game_market,
    _is_kalshi_game_winner_series,
    get_game_markets,
)
from app.tasks.backfill_winners import _PERIOD_SERIES_RE
from app.utils.game_market_class import (
    KALSHI_PERIOD_SERIES_RE,
    classify_game_market_class,
    kalshi_series_period,
    names_a_scoped_segment,
)
from tests.test_game_markets import (
    _make_event,
    _make_market,
    _make_outcome,
    _make_result,
)

PM_HASH = "0x5c0c5cd1a9b9c329fa03076140"

# (sport, name, external_id, expected game-page label)
GAME_PAGE_CASES = [
    # ── MLB ──
    ("mlb", "Yankees vs. Red Sox", PM_HASH, "moneyline"),
    ("mlb", "Philadelphia Phillies vs. Atlanta Braves", "1097824", "moneyline"),
    ("mlb", "New York Y vs Boston", "KXMLBGAME-26SEP011910NYYBOS", "moneyline"),
    # production id 62972601 — the F5 winner with no "Winner" in its title
    # keeps its section (see the module docstring)
    ("mlb", "Philadelphia vs Atlanta: First 5 Innings", "KXMLBF5-26SEP291400PHIATL", "segment_winner"),
    ("mlb", "Philadelphia vs Atlanta: First 5 Innings Winner", None, "half_winner"),
    ("mlb", "Philadelphia vs Atlanta: First 5 Innings Total", "KXMLBF5TOTAL-26SEP291400PHIATL", "half_total"),
    # A period named only by its ticker is never the game.
    ("mlb", "Rays at Braves", "KXMLBF5-26SEP091915TBATL", "other"),
    ("mlb", "Rays at Braves", "KXMLBRFI-26SEP091915TBATL-T0.5", "other"),
    ("mlb", "Rays at Braves", "KXMLBF3-26SEP091915TBATL", "other"),
    ("mlb", "Rays at Braves", "KXMLBF7-26SEP091915TBATL", "other"),
    ("mlb", "Philadelphia vs Atlanta: 9th Inning Winner", "KXMLBINNINGWIN-26SEP291400PH", "inning_winner"),
    ("mlb", "Philadelphia vs Atlanta: Total Runs", "KXMLBTOTAL-26SEP291400PHIATL", "game_total"),
    # ── NBA ──
    ("nba", "Celtics at Warriors", None, "moneyline"),
    ("nba", "Celtics at Warriors", "KXNBA2HSPREAD-26MAY17BOSGSW", "half_spread"),
    ("nba", "76ers vs. Celtics: 1H Moneyline", PM_HASH, "half_winner"),
    ("nba", "Lakers vs Celtics: Game Winner", None, "moneyline"),
    ("nba", "Celtics vs. Knicks - Player Props", PM_HASH, "other"),
    # ── NFL ──
    ("nfl", "Steelers vs. Browns", "885112", "moneyline"),
    ("nfl", "Steelers vs. Browns: 1H Moneyline", PM_HASH, "half_winner"),
    # ── NHL ──
    ("nhl", "Bruins vs. Maple Leafs", PM_HASH, "moneyline"),
    ("nhl", "Bruins vs Maple Leafs: 2nd Period Winner", None, "segment_winner"),
    # ── soccer ──
    ("soccer", "1. FC Köln vs. SV Werder Bremen", PM_HASH, "moneyline"),
    ("soccer", "Arsenal vs Chelsea", "KXEPL1H-26SEP12ARSCHE", "other"),
    ("soccer", "Arsenal vs Chelsea: Halftime Result", PM_HASH, "segment_winner"),
    ("soccer", "Round of 16 Winner: Arsenal vs Chelsea", None, "moneyline"),
    # ── tennis ──
    ("tennis", "US Open ATP: Alexander Zverev vs Ben Shelton", "123456", "moneyline"),
    ("tennis", "Hodzic vs Chan", "KXWTAMATCH-26JUL11HODCHA", "moneyline"),
    ("tennis", "Set 1 Winner: Aboian vs Martin", PM_HASH, "segment_winner"),
    # ── esports ──
    ("esports", "Phantom Academy vs. Noir Verse: Map 1", PM_HASH, "segment_winner"),
    ("esports", "Team Liquid vs. G2: Map 2", PM_HASH, "segment_winner"),
    ("esports", "Counter-Strike: 1WIN vs B8 - Map 1 Winner", PM_HASH, "segment_winner"),
    ("esports", "Counter-Strike: Eternal Fire vs WBT (BO3) - Stake Ranked Episode 5", PM_HASH, "moneyline"),
    # ── series sports: a numbered GAME is the whole match ──
    ("mlb", "Game 3 Winner: Dodgers vs Padres", None, "moneyline"),
]


@pytest.mark.parametrize(
    "sport,name,external_id,expected",
    GAME_PAGE_CASES,
    ids=[f"{c[0]}:{c[1]}:{c[2]}" for c in GAME_PAGE_CASES],
)
def test_the_game_page_labels_each_sports_markets(sport, name, external_id, expected):
    assert _classify_game_market(name, external_id) == expected


# The shared classifier is read by the blend, venue settlement, the stored
# content understanding and the capture census. This rollout gives it two new
# public helpers and changes NONE of its answers; these pin that.
SHARED_UNCHANGED = [
    ("Yankees vs. Red Sox", PM_HASH, "moneyline"),
    ("Celtics vs. Knicks - Player Props", PM_HASH, "other"),
    ("New York Y vs Boston", "KXMLBGAME-26SEP011910NYYBOS", "moneyline"),
]

# The three rows this file used to pin as `other`, MOVED on purpose by the census
# follow-up (review of #10936: the route's `segment_winner` never reached the
# shared classifier, so the census could not see it). Their full guard, both
# directions, is `test_segment_winner_is_a_shared_class_1529.py`.
SHARED_MOVED_TO_SEGMENT = [
    ("Philadelphia vs Atlanta: First 5 Innings", "KXMLBF5-26SEP291400PHIATL", "segment_winner"),
    ("Phantom Academy vs. Noir Verse: Map 1", PM_HASH, "segment_winner"),
    ("Counter-Strike: 1WIN vs B8 - Map 1 Winner", PM_HASH, "segment_winner"),
]


@pytest.mark.parametrize("name,external_id,expected", SHARED_UNCHANGED)
def test_the_shared_classifier_answers_exactly_as_before(name, external_id, expected):
    assert classify_game_market_class(name, external_id) == expected


@pytest.mark.parametrize("name,external_id,expected", SHARED_MOVED_TO_SEGMENT)
def test_the_named_segments_reach_the_shared_class(name, external_id, expected):
    assert classify_game_market_class(name, external_id) == expected


def test_the_period_grammar_is_the_graders_character_for_character():
    # Restated, not imported (the shared module is stdlib-only). Two copies of a
    # grammar may only coexist if they cannot differ.
    assert KALSHI_PERIOD_SERIES_RE.pattern == _PERIOD_SERIES_RE.pattern
    assert KALSHI_PERIOD_SERIES_RE.flags == _PERIOD_SERIES_RE.flags


@pytest.mark.parametrize(
    "external_id,expected",
    [
        ("KXMLBF5-26SEP291400PHIATL", "f5"),
        ("KXMLBF5TOTAL-26SEP291400PHIATL", "f5total"),
        ("KXMLBRFI-26SEP091915TBATL-T0.5", "rfi"),
        ("KXEPL1H-26SEP12ARSCHE", "1h"),
        ("KXNBA1QWINNER-26MAY17BOSGSW", "1q"),
        ("KXNCAAF3QSPREAD-26SEP12OSUMICH", "3q"),
        # whole-game controls
        ("KXEPLH2H-26SEP12ARSCHE", None),           # the (?<!h) carve-out
        ("KXWTAMATCH-26JUL11HODCHA", None),          # "1h" in the SUFFIX only
        ("KXMLBGAME-26SEP011910NYYBOS", None),
        (PM_HASH, None),                              # never read a non-Kalshi id
        ("1097824", None),
        (None, None),
    ],
)
def test_kalshi_series_period_reads_the_series_token_only(external_id, expected):
    assert kalshi_series_period(external_id) == expected


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Bruins vs Maple Leafs: 2nd Period Winner", True),
        ("Set 1 Winner: Aboian vs Martin", True),
        ("76ers vs. Celtics: 1H Moneyline", True),
        ("Lakers vs Celtics: Game Winner", False),
        ("Round of 16 Winner: Arsenal vs Chelsea", False),
        ("Game 3 Winner: Dodgers vs Padres", False),
        ("Yankees vs. Red Sox", False),
        (None, False),
    ],
)
def test_names_a_scoped_segment(name, expected):
    assert names_a_scoped_segment(name) is expected


def test_a_segment_never_prices_the_projection_and_a_matchup_still_defers():
    assert "segment_winner" in _PM_PERIOD_SCOPES
    # The NCAAF control (#3951): a matchup-named market still hands the
    # question to its outcomes — `moneyline` exactly as `other` did.
    assert _classify_game_market("Old Dominion vs. Virginia Tech", None) in (
        _PM_SCOPES_DEFERRING_TO_OUTCOMES
    )


# ── the endpoint ────────────────────────────────────────────────────────────


async def _serve(event_id, market, outcomes, **event_kw):
    event = _make_event(id=event_id, **event_kw)
    market.event_id = event_id
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[
        _make_result(scalar=event),
        _make_result(),  # #3391 serve-fold sports read
        _make_result(rows=[]),  # #2693 folded_event_ids
        _make_result(rows=[market]),
        _make_result(all_rows=[]),
        _make_result(rows=[]),
        _make_result(rows=outcomes),
        _make_result(all_rows=[]),  # #4970 load_latest_observed_at
    ])
    return await get_game_markets(event_id, db)


MLB = dict(
    home_team_name="Atlanta Braves",
    away_team_name="Philadelphia Phillies",
    sport_key="baseball_mlb",
)


@pytest.mark.asyncio
async def test_the_f5_winner_keeps_the_card_the_reader_sees():
    # Production specimen shape (15329040, 2026-10-12): served in `other`, which
    # the web renders as "First 5 Innings · Dodgers 46% · Milwaukee 36% · Tie
    # 19%". The title rescue must not relabel it the game, and nothing here may
    # move it behind the collapsed period browser.
    market = _make_market(
        id=152901,
        name="Los Angeles Dodgers vs Milwaukee: First 5 Innings",
        external_id="KXMLBF5-26OCT121400LADMIL",
        sport_category="baseball",
    )
    outcomes = [
        _make_outcome(id=1529011, market_id=152901, name="Los Angeles Dodgers", probability=0.46),
        _make_outcome(id=1529012, market_id=152901, name="Milwaukee", probability=0.36),
        _make_outcome(id=1529013, market_id=152901, name="Tie", probability=0.19),
    ]
    response = await _serve(
        9152901, market, outcomes,
        home_team_name="Milwaukee Brewers", away_team_name="Los Angeles Dodgers",
        sport_key="baseball_mlb",
    )
    assert response["period_markets"] == []
    assert [r["outcome_name"] for r in response["other"]] == [
        "Los Angeles Dodgers", "Milwaukee", "Tie",
    ]


@pytest.mark.asyncio
async def test_a_bare_matchup_on_a_period_ticker_is_not_relabelled_the_game():
    # The first-THREE-innings series titled with the matchup alone.
    market = _make_market(
        id=152902,
        name="Rays at Braves",
        external_id="KXMLBF3-26SEP091915TBATL",
        sport_category="baseball",
    )
    outcomes = [
        _make_outcome(id=1529021, market_id=152902, name="Rays", probability=0.40),
        _make_outcome(id=1529022, market_id=152902, name="Braves", probability=0.45),
    ]
    assert _classify_game_market(market.name, market.external_id) == "other"
    response = await _serve(9152902, market, outcomes, **MLB)
    assert response["period_markets"] == []
    assert [r["outcome_name"] for r in response["other"]] == ["Rays", "Braves"]


@pytest.mark.asyncio
async def test_a_polymarket_bare_matchup_container_of_player_contracts_stays_props():
    # THE HARD GATE (#1529): a bare-matchup NAME whose OUTCOMES are player
    # contracts is a prop container. It now classifies `moneyline`, and must
    # still serve every leg as a player prop — on a Polymarket hash, the exact
    # shape whose label this change moves.
    market = _make_market(
        id=152903,
        name="Celtics vs. Knicks",
        external_id=PM_HASH,
        source="polymarket",
    )
    outcomes = [
        _make_outcome(id=1529031, market_id=152903, name="Jaylen Brown: 25+",
                      probability=0.38, opening_probability=0.42),
    ]
    assert _classify_game_market(market.name, market.external_id) == "moneyline"
    response = await _serve(9152903, market, outcomes)

    assert response["other"] == []
    [prop] = response["player_props"]
    assert prop["outcome_name"] == "Jaylen Brown: 25+"
    assert prop["threshold"] == 25.0


@pytest.mark.asyncio
async def test_a_polymarket_bare_matchup_winner_keeps_its_section():
    # Control for the label move: the winner's two legs are served where they
    # were, so no reader-facing section changes for this shape.
    market = _make_market(
        id=152904,
        name="Celtics vs. Knicks",
        external_id=PM_HASH,
        source="polymarket",
    )
    outcomes = [
        _make_outcome(id=1529041, market_id=152904, name="Boston Celtics", probability=0.58),
        _make_outcome(id=1529042, market_id=152904, name="New York Knicks", probability=0.42),
    ]
    response = await _serve(9152904, market, outcomes)
    assert response["player_props"] == []
    assert response["period_markets"] == []
    assert [r["outcome_name"] for r in response["other"]] == [
        "Boston Celtics", "New York Knicks",
    ]


# ── the admin calibration-by-type CASE ──────────────────────────────────────


@pytest.mark.parametrize(
    "ticker,is_game",
    [
        ("KXNHLGAME-26OCT09TBFLA", True),
        ("KXMLBGAME-26SEP011910NYYBOS", True),
        ("KXNBAGAME-26MAY17BOSGSW", True),
        ("KXNFLGAME-26OCT04GBTB", True),
        ("KXMLBSTGAME-26MAR01NYYBOS", True),
        ("KXMLBTOTAL-26SEP291400PHIATL", False),
        ("KXMLBF5-26SEP291400PHIATL", False),
        ("KXNBAPTS-26MAY17BOSGSW-JTATUM", False),
        # "game" inside the SUFFIX is not the series
        ("KXATPMATCH-26SEP01GAMEX", False),
    ],
)
def test_the_admin_game_bucket_is_every_leagues_winner_series(ticker, is_game):
    # The SQL rule, `split_part(ext, '-', 1) LIKE 'KX%GAME'`, restated in
    # Python and held against the route's own reader of the same question.
    series = ticker.split("-", 1)[0]
    sql_says = series.startswith("KX") and series.endswith("GAME")
    assert sql_says is is_game
    assert _is_kalshi_game_winner_series(ticker) is is_game


def test_the_admin_case_names_no_single_league():
    sql = admin_data_quality._KALSHI_GAME_WINNER_SERIES_SQL
    assert sql == (
        "(fm.source = 'kalshi' AND split_part(fm.external_id, '-', 1) LIKE 'KX%GAME')"
    )
    # No bind-parameter-shaped text (gotcha #45) inside `text()`.
    assert ":" not in sql
    source = inspect.getsource(admin_data_quality.calibration_mce_by_sport)
    assert "KXNHLGAME" not in source
    # the CASE's "game" arm and all three prop read-outs use the one rule
    assert source.count("_KALSHI_GAME_WINNER_SERIES_SQL") == 4
    assert "+ _KALSHI_GAME_WINNER_SERIES_SQL + \"\"\" THEN 'game'" in source
