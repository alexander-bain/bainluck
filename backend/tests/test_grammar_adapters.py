"""A2 (#1021) — grammar adapters v1 tests.

Covers the three per-source adapters (Kalshi ticker/series, Polymarket
event/negrisk, Odds API structured) plus the dispatcher, the stored-row
measurement path, and the ≥95%-of-new-ingests-get-≥1-mention acceptance bar
(measured over a representative fixture corpus — the live count lands with the
ingest-time write-hook / A6 scoreboard).

Load-bearing invariant tested here: every mention's ``norm`` is produced by the
SAME ``entity_registry.normalize_alias`` the A1 seed and read path use — a
mention normalized differently from an alias would never resolve in A4.
"""

from __future__ import annotations

from app.services.entity_registry import (
    KIND_COMPETITION,
    KIND_EVENT_CONCEPT,
    KIND_PERSON,
    KIND_TEAM,
    normalize_alias,
)
from app.services.grammar_adapters import (
    DIR_OVER,
    DIR_UNDER,
    ROLE_OUTCOME,
    ROLE_PARTICIPANT,
    EntityMention,
    MarketAnnotation,
    annotate,
    annotate_kalshi,
    annotate_odds_api,
    annotate_polymarket,
    annotate_stored_market,
    coverage,
)


# ---------------------------------------------------------------------------
# EntityMention / normalize identity
# ---------------------------------------------------------------------------
def test_mention_norm_matches_registry_normalizer():
    """A2 mentions MUST normalize identically to A1 aliases (the resolve key)."""
    m = EntityMention.make(
        "St. Louis Cardinals",
        kind=KIND_TEAM,
        role=ROLE_PARTICIPANT,
        source="odds_api",
    )
    assert m is not None
    assert m.norm == normalize_alias("St. Louis Cardinals") == "st louis cardinals"


def test_mention_make_returns_none_for_empty():
    assert EntityMention.make("   ", kind=KIND_TEAM, role=ROLE_PARTICIPANT, source="x") is None
    assert EntityMention.make("!!!", kind=KIND_TEAM, role=ROLE_PARTICIPANT, source="x") is None


# ---------------------------------------------------------------------------
# Kalshi
# ---------------------------------------------------------------------------
def test_kalshi_nba_game_emits_team_participants():
    ann = annotate_kalshi(
        event_ticker="KXNBAGAME-26FEB19BOSGSW",
        title="Celtics vs Warriors",
        markets=[{"yes_sub_title": "Boston Celtics"}, {"yes_sub_title": "Golden State Warriors"}],
    )
    assert ann.source == "kalshi"
    assert ann.market_type == "game"
    assert ann.competition == "basketball_nba"
    assert not ann.unparsed
    # Team abbreviations decoded from the ticker are present as team participants.
    norms = {m.norm for m in ann.mentions}
    assert "celtics" in norms or "boston celtics" in norms
    assert "warriors" in norms or "golden state warriors" in norms
    assert all(m.kind == KIND_TEAM for m in ann.mentions if m.role == ROLE_PARTICIPANT)


def test_kalshi_ufc_fight_emits_person_participants_from_title():
    ann = annotate_kalshi(
        event_ticker="KXUFCFIGHT-26JAN18OLIHOL",
        title="Oliveira vs. Holloway",
        markets=[{"yes_sub_title": "Charles Oliveira"}, {"yes_sub_title": "Max Holloway"}],
    )
    assert ann.market_type == "game"
    persons = {m.norm for m in ann.mentions if m.kind == KIND_PERSON}
    assert "oliveira" in persons or "charles oliveira" in persons
    assert "holloway" in persons or "max holloway" in persons


def test_kalshi_ufc_method_prop_type():
    ann = annotate_kalshi(
        event_ticker="KXUFCMOF-26JAN18",
        title="Method of victory",
        markets=[{"yes_sub_title": "KO/TKO"}],
    )
    assert ann.market_type == "method_of_victory"


def test_kalshi_futures_emits_competition_and_concept():
    ann = annotate_kalshi(
        event_ticker="KXPGAMAKECUT-26MASTERS",
        title="Will Scottie Scheffler make the cut at the Masters?",
        markets=[{"yes_sub_title": "Yes"}],
    )
    kinds = {m.kind for m in ann.mentions}
    assert KIND_COMPETITION in kinds  # golf
    assert KIND_EVENT_CONCEPT in kinds  # the title
    assert ann.competition == "golf"


def test_kalshi_threshold_line_over_by_default():
    # gotcha #17: a bare numeric threshold is the OVER side.
    ann = annotate_kalshi(
        event_ticker="KXHIGHTEMP-26JUL12NYC",
        title="NYC high temperature",
        markets=[{"yes_sub_title": "90 or above"}],
    )
    assert ann.line == 90.0
    assert ann.line_direction == DIR_OVER


def test_kalshi_threshold_under_direction():
    ann = annotate_kalshi(
        event_ticker="KXHIGHTEMP-26JUL12NYC",
        title="NYC high temperature",
        markets=[{"yes_sub_title": "Under 75"}],
    )
    assert ann.line == 75.0
    assert ann.line_direction == DIR_UNDER


def test_kalshi_unknown_prefix_notes_sentinel():
    ann = annotate_kalshi(event_ticker="KXTOTALLYNEWSERIES-26", title="Some new thing")
    assert any(n.startswith("unknown_ticker_prefix") for n in ann.notes)
    # Still not unparsed — the title becomes a concept mention.
    assert not ann.unparsed


# ---------------------------------------------------------------------------
# Polymarket
# ---------------------------------------------------------------------------
def test_polymarket_negrisk_championship_decomposes_candidates():
    # gotcha #18: nested sub-markets, each a candidate.
    ann = annotate_polymarket(
        event_id="0xEVENT",
        title="2025-26 NBA Championship",
        tags=["Sports", "NBA"],
        neg_risk=True,
        markets=[
            {"group_item_title": "Boston Celtics", "condition_id": "0xa"},
            {"question": "Will the Denver Nuggets win the 2025-26 NBA Championship?", "condition_id": "0xb"},
        ],
    )
    outcomes = {m.norm for m in ann.mentions if m.role == ROLE_OUTCOME}
    assert "boston celtics" in outcomes
    assert "denver nuggets" in outcomes  # parsed from the "Will X win…" question
    assert ann.concept_ref == "0xEVENT"


def test_polymarket_best_picture_negrisk():
    ann = annotate_polymarket(
        event_id="0xOSCAR",
        title="Best Picture 2026",
        tags=["Entertainment", "Oscars"],
        neg_risk=True,
        markets=[
            {"group_item_title": "Oppenheimer"},
            {"group_item_title": "Barbie"},
        ],
    )
    outcomes = {m.norm for m in ann.mentions if m.role == ROLE_OUTCOME}
    assert {"oppenheimer", "barbie"} <= outcomes


def test_polymarket_game_matchup_from_title():
    ann = annotate_polymarket(
        event_id="0xGAME",
        title="Lakers vs. Celtics",
        tags=["Sports", "NBA"],
        neg_risk=False,
        markets=[{"question": "Will the Lakers win?", "condition_id": "0xc"}],
    )
    assert ann.market_type == "game"
    participants = {m.norm for m in ann.mentions if m.role == ROLE_PARTICIPANT}
    assert "lakers" in participants
    assert "celtics" in participants


def test_polymarket_threshold_line_and_still_has_mention():
    ann = annotate_polymarket(
        event_id="0xTEMP",
        title="Highest temperature in NYC on July 12?",
        neg_risk=True,
        markets=[{"group_item_title": "90°F or above"}, {"group_item_title": "89°F or below"}],
    )
    assert ann.line is not None
    assert not ann.unparsed  # threshold labels still count as (low-conf) mentions


def test_polymarket_non_sports_concept_gets_mention():
    ann = annotate_polymarket(
        event_id="0xFED",
        title="Fed decision in July 2026",
        tags=["Economics"],
        neg_risk=True,
        markets=[{"group_item_title": "50+ bps decrease"}, {"group_item_title": "No change"}],
    )
    assert not ann.unparsed
    assert any(m.kind == KIND_EVENT_CONCEPT for m in ann.mentions)


# ---------------------------------------------------------------------------
# Odds API
# ---------------------------------------------------------------------------
def test_odds_api_h2h_team_participants():
    ann = annotate_odds_api(
        sport_key="basketball_nba",
        home_team="Los Angeles Lakers",
        away_team="Boston Celtics",
        market_key="h2h",
    )
    assert ann.market_type == "moneyline"
    assert {m.norm for m in ann.mentions} == {"los angeles lakers", "boston celtics"}
    assert all(m.kind == KIND_TEAM for m in ann.mentions)


def test_odds_api_spread_captures_line():
    ann = annotate_odds_api(
        sport_key="americanfootball_nfl",
        home_team="Kansas City Chiefs",
        away_team="Buffalo Bills",
        market_key="spreads",
        point=-3.5,
    )
    assert ann.market_type == "spread"
    assert ann.line == -3.5


def test_odds_api_totals_over_under_not_entities():
    ann = annotate_odds_api(
        sport_key="basketball_nba",
        market_key="totals",
        outcomes=[{"name": "Over", "point": 220.5}, {"name": "Under", "point": 220.5}],
    )
    assert ann.market_type == "total"
    assert ann.line == 220.5
    # Over/Under are directions, not entity mentions.
    assert ann.unparsed


def test_odds_api_outrights_names_are_entities():
    ann = annotate_odds_api(
        sport_key="basketball_nba_championship",
        market_key="outrights",
        outcomes=["Los Angeles Lakers", "Boston Celtics", "Denver Nuggets"],
    )
    assert ann.market_type == "championship"
    assert len(ann.mentions) == 3


# ---------------------------------------------------------------------------
# Dispatcher + stored-row path + coverage
# ---------------------------------------------------------------------------
def test_dispatcher_routes_by_source():
    ann = annotate("odds_api", {"home_team": "A", "away_team": "B", "market_key": "h2h"})
    assert ann.source == "odds_api"
    assert len(ann.mentions) == 2
    unknown = annotate("mystery_source", {})
    assert unknown.unparsed
    assert any(n.startswith("unknown_source") for n in unknown.notes)


def test_annotate_stored_market_kalshi():
    ann = annotate_stored_market(
        source="kalshi",
        external_id="KXNBAGAME-26FEB19BOSGSW",
        name="Celtics vs Warriors",
        market_metadata={"kalshi_event_ticker": "KXNBAGAME-26FEB19BOSGSW"},
        outcome_names=["Boston Celtics", "Golden State Warriors"],
    )
    assert not ann.unparsed
    assert ann.market_type == "game"


def test_annotate_stored_market_polymarket_negrisk():
    ann = annotate_stored_market(
        source="polymarket",
        external_id="0xEVENT",
        name="2025-26 NBA Championship",
        market_metadata={"polymarket_event_id": "0xEVENT", "neg_risk": True},
        outcome_names=["Boston Celtics", "Denver Nuggets"],
    )
    outcomes = {m.norm for m in ann.mentions if m.role == ROLE_OUTCOME}
    assert {"boston celtics", "denver nuggets"} <= outcomes


def test_coverage_helper():
    anns = [
        annotate_odds_api(home_team="A", away_team="B", market_key="h2h"),
        MarketAnnotation(source="kalshi"),  # unparsed
    ]
    stats = coverage(anns)
    assert stats["total"] == 2
    assert stats["with_mention"] == 1
    assert stats["rate"] == 0.5


# ---------------------------------------------------------------------------
# Acceptance bar: ≥95% of a representative NEW-ingest sample get ≥1 mention.
# The corpus mirrors real ingest shapes across all three sources + many sports
# and non-sports classes. The live count (over stored rows) lands with the
# ingest-time write-hook / A6 scoreboard; this is the interim proxy per #1021.
# ---------------------------------------------------------------------------
_FIXTURE_CORPUS = [
    # --- Kalshi games ---
    ("kalshi", {"event_ticker": "KXNBAGAME-26FEB19BOSGSW", "title": "Celtics vs Warriors",
                "markets": [{"yes_sub_title": "Boston Celtics"}, {"yes_sub_title": "Golden State Warriors"}]}),
    ("kalshi", {"event_ticker": "KXNHLGAME-26MAR02TORMTL", "title": "Maple Leafs vs Canadiens",
                "markets": [{"yes_sub_title": "Toronto Maple Leafs"}]}),
    ("kalshi", {"event_ticker": "KXMLBGAME-26APR291840COLCIN", "title": "Rockies vs Reds",
                "markets": [{"yes_sub_title": "Colorado Rockies"}]}),
    ("kalshi", {"event_ticker": "KXNFLGAME-26SEP13KCBUF", "title": "Chiefs vs Bills",
                "markets": [{"yes_sub_title": "Kansas City Chiefs"}]}),
    ("kalshi", {"event_ticker": "KXUFCFIGHT-26JAN18", "title": "Oliveira vs. Holloway",
                "markets": [{"yes_sub_title": "Charles Oliveira"}, {"yes_sub_title": "Max Holloway"}]}),
    ("kalshi", {"event_ticker": "KXUFCMOF-26JAN18", "title": "Method of victory",
                "markets": [{"yes_sub_title": "KO/TKO"}]}),
    ("kalshi", {"event_ticker": "KXATPMATCH-26JAN20", "title": "Alcaraz vs. Sinner",
                "markets": [{"yes_sub_title": "Carlos Alcaraz"}, {"yes_sub_title": "Jannik Sinner"}]}),
    ("kalshi", {"event_ticker": "KXNCAABGAME-26FEB10DUKUNC", "title": "Duke vs UNC",
                "markets": [{"yes_sub_title": "Duke"}]}),
    # --- Kalshi futures / awards / props ---
    ("kalshi", {"event_ticker": "KXNBA-26", "title": "2025-26 NBA Championship Winner",
                "markets": [{"yes_sub_title": "Boston Celtics"}, {"yes_sub_title": "Denver Nuggets"}]}),
    ("kalshi", {"event_ticker": "KXPGAMAKECUT-26MASTERS", "title": "Will Scheffler make the cut at the Masters?",
                "markets": [{"yes_sub_title": "Yes"}]}),
    ("kalshi", {"event_ticker": "KXHIGHTEMP-26JUL12NYC", "title": "NYC high temperature July 12",
                "markets": [{"yes_sub_title": "90 or above"}, {"yes_sub_title": "Under 75"}]}),
    ("kalshi", {"event_ticker": "KXEPLGAME-26MAR07ARSCHE", "title": "Arsenal vs Chelsea",
                "markets": [{"yes_sub_title": "Arsenal"}]}),
    # --- Polymarket ---
    ("polymarket", {"event_id": "0x1", "title": "2025-26 NBA Championship", "tags": ["Sports", "NBA"],
                    "neg_risk": True, "markets": [{"group_item_title": "Boston Celtics"},
                                                   {"question": "Will the Denver Nuggets win the 2025-26 NBA Championship?"}]}),
    ("polymarket", {"event_id": "0x2", "title": "Best Picture 2026", "tags": ["Entertainment"],
                    "neg_risk": True, "markets": [{"group_item_title": "Oppenheimer"}, {"group_item_title": "Barbie"}]}),
    ("polymarket", {"event_id": "0x3", "title": "Lakers vs. Celtics", "tags": ["Sports", "NBA"],
                    "neg_risk": False, "markets": [{"question": "Will the Lakers win?"}]}),
    ("polymarket", {"event_id": "0x4", "title": "Fed decision in July 2026", "tags": ["Economics"],
                    "neg_risk": True, "markets": [{"group_item_title": "50+ bps decrease"}, {"group_item_title": "No change"}]}),
    ("polymarket", {"event_id": "0x5", "title": "Highest temperature in NYC on July 12?", "tags": ["Weather"],
                    "neg_risk": True, "markets": [{"group_item_title": "90°F or above"}, {"group_item_title": "89°F or below"}]}),
    ("polymarket", {"event_id": "0x6", "title": "2026 US Senate control", "tags": ["Politics"],
                    "neg_risk": True, "markets": [{"group_item_title": "Republicans"}, {"group_item_title": "Democrats"}]}),
    ("polymarket", {"event_id": "0x7", "title": "Will Man City win the 2025-26 Premier League?", "tags": ["Sports", "EPL"],
                    "neg_risk": False, "markets": [{"question": "Will Man City win the 2025-26 Premier League?"}]}),
    ("polymarket", {"event_id": "0x8", "title": "UFC 329: Jones vs. Aspinall", "tags": ["Sports", "MMA"],
                    "neg_risk": False, "markets": [{"question": "Will Jon Jones win?"}]}),
    # --- Odds API games + outrights ---
    ("odds_api", {"sport_key": "basketball_nba", "home_team": "Los Angeles Lakers",
                  "away_team": "Boston Celtics", "market_key": "h2h"}),
    ("odds_api", {"sport_key": "americanfootball_nfl", "home_team": "Kansas City Chiefs",
                  "away_team": "Buffalo Bills", "market_key": "spreads", "point": -3.5}),
    ("odds_api", {"sport_key": "soccer_epl", "home_team": "Arsenal", "away_team": "Chelsea", "market_key": "h2h"}),
    ("odds_api", {"sport_key": "icehockey_nhl", "home_team": "Toronto Maple Leafs",
                  "away_team": "Montreal Canadiens", "market_key": "h2h"}),
    ("odds_api", {"sport_key": "baseball_mlb", "home_team": "New York Yankees",
                  "away_team": "Boston Red Sox", "market_key": "h2h"}),
    ("odds_api", {"sport_key": "basketball_nba_championship", "market_key": "outrights",
                  "outcomes": ["Los Angeles Lakers", "Boston Celtics", "Denver Nuggets"]}),
    ("odds_api", {"sport_key": "americanfootball_nfl_super_bowl_winner", "market_key": "outrights",
                  "outcomes": ["Kansas City Chiefs", "San Francisco 49ers"]}),
]


def test_acceptance_new_ingest_sample_ge_95pct_one_mention():
    anns = [annotate(source, payload) for source, payload in _FIXTURE_CORPUS]
    stats = coverage(anns)
    unparsed = [
        (src, ann.notes) for (src, _), ann in zip(_FIXTURE_CORPUS, anns) if ann.unparsed
    ]
    assert stats["rate"] >= 0.95, (
        f"only {stats['with_mention']}/{stats['total']} got a mention "
        f"(rate={stats['rate']:.3f}); unparsed: {unparsed}"
    )


def test_acceptance_market_type_and_line_coverage():
    """Sanity: market-type is near-universal; lines captured where present."""
    anns = [annotate(source, payload) for source, payload in _FIXTURE_CORPUS]
    stats = coverage(anns)
    assert stats["with_market_type"] == stats["total"]  # every market gets a type
    assert stats["with_line"] >= 3  # spreads/totals/thresholds captured lines


# ---------------------------------------------------------------------------
# Queue #170 — MMA combat-ticker grammar hardening + poly matchup title backfill
# ---------------------------------------------------------------------------
def test_kalshi_ufc_fight_night_prefix_yields_exactly_two_fighters():
    """A stored UFC fight name carries an event-title PREFIX and surname-only
    fighters ("Fight Night: Abdullayev vs Nascimento"). The grammar must strip
    the prefix and emit EXACTLY two person participants — the date-token ticker
    ("KXUFCFIGHT-26JUN27ABDNAS") must NOT fragment into junk 'ABD'/'NAS'
    participants that push the market past the engine's is_game two-participant
    gate."""
    from app.services.resolution_engine import build_signature

    ann = annotate_stored_market(
        source="kalshi",
        external_id="KXUFCFIGHT-26JUN27ABDNAS",
        name="Fight Night: Abdullayev vs Nascimento",
        market_metadata={"kalshi_event_ticker": "KXUFCFIGHT-26JUN27ABDNAS"},
    )
    participants = {m.norm for m in ann.mentions if m.role == ROLE_PARTICIPANT}
    assert participants == {"abdullayev", "nascimento"}, participants
    assert all(
        m.kind == KIND_PERSON for m in ann.mentions if m.role == ROLE_PARTICIPANT
    )
    sig = build_signature(ann, external_id="KXUFCFIGHT-26JUN27ABDNAS")
    assert sig.is_game  # exactly two participants
    assert sig.surnames == {"abdullayev", "nascimento"}


def test_kalshi_ufc_fight_night_full_prefix_variant():
    ann = annotate_stored_market(
        source="kalshi",
        external_id="KXUFCFIGHT-26JUN06SOUCAR",
        name="UFC Fight Night: Souza vs Carnelossi",
        market_metadata={"kalshi_event_ticker": "KXUFCFIGHT-26JUN06SOUCAR"},
    )
    participants = {m.norm for m in ann.mentions if m.role == ROLE_PARTICIPANT}
    assert participants == {"souza", "carnelossi"}, participants


def test_poly_stored_market_uses_backfilled_matchup_title():
    """A decomposed poly spread row names only one team; with a backfilled
    ``matchup_title`` the grammar recovers BOTH participants so the engine can
    reproduce the event link."""
    from app.services.resolution_engine import build_signature

    ann = annotate_stored_market(
        source="polymarket",
        external_id="0xspread",
        name="Spread: San Diego Padres (-2.5)",
        market_metadata={"matchup_title": "Toronto Blue Jays vs. San Diego Padres"},
    )
    sig = build_signature(ann, external_id="0xspread")
    assert sig.is_game
    assert sig.participants == {"n:toronto blue jays", "n:san diego padres"}


def test_poly_stored_market_without_matchup_title_unchanged():
    """Additive: absent a matchup_title, a spread row still yields no participants
    (behaviour is unchanged for un-backfilled rows)."""
    from app.services.resolution_engine import build_signature

    ann = annotate_stored_market(
        source="polymarket",
        external_id="0xspread",
        name="Spread: San Diego Padres (-2.5)",
        market_metadata={},
    )
    sig = build_signature(ann, external_id="0xspread")
    assert not sig.is_game


def test_split_vs_strips_event_prefix_but_keeps_plain_matchups():
    from app.services.grammar_adapters import _split_vs

    assert _split_vs("Fight Night: Abdullayev vs Nascimento") == ("Abdullayev", "Nascimento")
    assert _split_vs("Oliveira vs. Holloway") == ("Oliveira", "Holloway")
    assert _split_vs("USA at Canada") == ("USA", "Canada")
