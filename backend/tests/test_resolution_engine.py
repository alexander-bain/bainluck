"""A4 (#1023) — resolution engine tests.

Covers: signature building from A2 annotations, each of the four strategies, the
four emitted link types, the L2-62 negative-case discipline (a Challenger match
must NEVER join Wimbledon), the line-direction guard (gotcha #17), and the
competition/date guards.
"""

from __future__ import annotations

from datetime import date

from app.services.grammar_adapters import (
    annotate_kalshi,
    annotate_odds_api,
    annotate_polymarket,
)
from app.services.resolution_engine import (
    ConceptSignature,
    EventSignature,
    LINK_CROSS_SOURCE,
    LINK_FAMILY,
    LINK_MARKET_CONCEPT,
    LINK_MARKET_EVENT,
    MarketSignature,
    MatchUniverse,
    ResolutionEngine,
    build_signature,
    competition_agrees,
    dates_within_window,
    family_key,
    line_agrees,
    normalize_question,
    participants_agree,
)


# ---------------------------------------------------------------------------
# Signature construction
# ---------------------------------------------------------------------------
def test_build_signature_from_odds_api_game():
    ann = annotate_odds_api(
        sport_key="basketball_nba",
        home_team="Boston Celtics",
        away_team="Miami Heat",
        market_key="h2h",
    )
    sig = build_signature(ann, external_id="odds:evt1", event_date=date(2026, 1, 5))
    assert sig.is_game
    assert sig.market_type == "moneyline"
    assert sig.participants == frozenset({"n:boston celtics", "n:miami heat"})
    assert sig.surnames == frozenset({"celtics", "heat"})
    assert sig.competition == "basketball nba"


def test_build_signature_uses_resolved_entity_ids():
    ann = annotate_odds_api(
        sport_key="basketball_nba",
        home_team="Boston Celtics",
        away_team="Miami Heat",
    )
    sig = build_signature(
        ann,
        external_id="odds:evt1",
        resolved={"boston celtics": 10, "miami heat": 20},
    )
    assert sig.participants == frozenset({"e:10", "e:20"})


def test_build_signature_line_carried_from_totals():
    ann = annotate_odds_api(
        sport_key="basketball_nba",
        market_key="totals",
        point=220.5,
        outcomes=[{"name": "Over", "point": 220.5}, {"name": "Under", "point": 220.5}],
    )
    sig = build_signature(ann, external_id="odds:tot1")
    assert sig.line == 220.5
    assert sig.market_type == "total"


# ---------------------------------------------------------------------------
# Predicates
# ---------------------------------------------------------------------------
def test_participants_agree_requires_set_equality():
    a = frozenset({"n:a", "n:b"})
    assert participants_agree(a, frozenset({"n:b", "n:a"}))
    assert not participants_agree(a, frozenset({"n:a", "n:c"}))
    assert not participants_agree(frozenset(), frozenset())


def test_line_agrees_direction_guard():
    assert line_agrees(None, None, None, None)
    assert line_agrees(220.5, "over", 220.5, None)
    assert line_agrees(220.5, "over", 220.5, "over")
    # explicit opposite directions never agree (gotcha #17)
    assert not line_agrees(220.5, "over", 220.5, "under")
    # different values never agree
    assert not line_agrees(220.5, None, 221.5, None)
    # one present, one absent
    assert not line_agrees(220.5, None, None, None)


def test_dates_within_window_and_competition_guards():
    assert dates_within_window(date(2026, 1, 5), date(2026, 1, 6))
    assert not dates_within_window(date(2026, 1, 5), date(2026, 1, 20))
    assert dates_within_window(None, date(2026, 1, 5))  # unknown never blocks
    assert competition_agrees("nba", "nba")
    assert not competition_agrees("nba", "nhl")
    assert competition_agrees("nba", None)  # unknown never blocks


# ---------------------------------------------------------------------------
# Strategy 1 — market→event (ticker/participant)
# ---------------------------------------------------------------------------
def _nba_game_market():
    ann = annotate_odds_api(
        sport_key="basketball_nba",
        home_team="Boston Celtics",
        away_team="Miami Heat",
    )
    return build_signature(ann, external_id="k:GAME1", event_date=date(2026, 1, 5))


def test_market_event_link_emitted():
    sig = _nba_game_market()
    event = EventSignature(
        event_id=777,
        participants=frozenset({"n:boston celtics", "n:miami heat"}),
        event_date=date(2026, 1, 5),
        competition="basketball nba",
    )
    links = ResolutionEngine().resolve(sig, MatchUniverse(events=[event]))
    ev_links = [l for l in links if l.link_type == LINK_MARKET_EVENT]
    assert len(ev_links) == 1
    assert ev_links[0].right == "777"
    assert ev_links[0].strategy == "ticker_participant"


def test_market_event_link_blocked_by_wrong_participants():
    sig = _nba_game_market()
    event = EventSignature(
        event_id=888,
        participants=frozenset({"n:boston celtics", "n:new york knicks"}),
        event_date=date(2026, 1, 5),
    )
    links = ResolutionEngine().resolve(sig, MatchUniverse(events=[event]))
    assert not [l for l in links if l.link_type == LINK_MARKET_EVENT]


def test_market_event_link_blocked_by_date_window():
    sig = _nba_game_market()
    event = EventSignature(
        event_id=999,
        participants=frozenset({"n:boston celtics", "n:miami heat"}),
        event_date=date(2026, 2, 5),  # a month off
    )
    links = ResolutionEngine().resolve(sig, MatchUniverse(events=[event]))
    assert not [l for l in links if l.link_type == LINK_MARKET_EVENT]


def test_market_event_link_blocked_by_competition_mismatch():
    sig = _nba_game_market()
    event = EventSignature(
        event_id=1000,
        participants=frozenset({"n:boston celtics", "n:miami heat"}),
        event_date=date(2026, 1, 5),
        competition="icehockey_nhl",  # normalized differently -> mismatch
    )
    links = ResolutionEngine().resolve(sig, MatchUniverse(events=[event]))
    assert not [l for l in links if l.link_type == LINK_MARKET_EVENT]


# ---------------------------------------------------------------------------
# Strategy 2 — market→concept (entrant-set, L2-62)
# ---------------------------------------------------------------------------
def _tennis_match(a: str, b: str, external_id: str) -> MarketSignature:
    ann = annotate_kalshi(
        event_ticker=f"KXATPMATCH-{external_id}",
        title=f"{a} vs {b}",
    )
    return build_signature(ann, external_id=external_id, event_date=date(2026, 7, 1))


def test_entrant_set_links_match_in_field():
    """Sabalenka vs Osaka — both in the Wimbledon field — joins the concept."""
    match = _tennis_match("Aryna Sabalenka", "Naomi Osaka", "WIMB-M1")
    wimbledon = ConceptSignature(
        concept_ref="concept:wimbledon-2026",
        entrant_keys=frozenset({"sabalenka", "osaka", "gauff", "swiatek"}),
    )
    links = ResolutionEngine().resolve(match, MatchUniverse(concepts=[wimbledon]))
    concept_links = [l for l in links if l.link_type == LINK_MARKET_CONCEPT]
    assert len(concept_links) == 1
    assert concept_links[0].right == "concept:wimbledon-2026"


def test_entrant_set_negative_case_challenger_never_joins_wimbledon():
    """L2-62 discipline: a concurrent Challenger match whose players are NOT in
    the Wimbledon field must NEVER join Wimbledon, even in the same date-window."""
    challenger = _tennis_match("Bertran", "Soto", "CHALL-M1")
    wimbledon = ConceptSignature(
        concept_ref="concept:wimbledon-2026",
        entrant_keys=frozenset({"sabalenka", "osaka", "gauff", "swiatek"}),
        event_date=date(2026, 7, 1),
    )
    links = ResolutionEngine().resolve(challenger, MatchUniverse(concepts=[wimbledon]))
    assert not [l for l in links if l.link_type == LINK_MARKET_CONCEPT]


def test_entrant_set_partial_overlap_does_not_join():
    """One player in the field is not enough — BOTH must be entrants."""
    mixed = _tennis_match("Sabalenka", "Bertran", "MIX-M1")
    wimbledon = ConceptSignature(
        concept_ref="concept:wimbledon-2026",
        entrant_keys=frozenset({"sabalenka", "osaka", "gauff"}),
    )
    links = ResolutionEngine().resolve(mixed, MatchUniverse(concepts=[wimbledon]))
    assert not [l for l in links if l.link_type == LINK_MARKET_CONCEPT]


# ---------------------------------------------------------------------------
# Strategy 3 — cross-source pairs (question normalization)
# ---------------------------------------------------------------------------
def test_cross_source_pair_emitted():
    kalshi = MarketSignature(
        source="kalshi",
        external_id="k:FEDCUT",
        market_type="binary",
        question_norm=normalize_question("Will the Fed cut rates in March?"),
    )
    poly = MarketSignature(
        source="polymarket",
        external_id="p:FEDCUT",
        market_type="binary",
        question_norm=normalize_question("Will the Fed cut rates in March?"),
    )
    links = ResolutionEngine().resolve(kalshi, MatchUniverse(markets=[poly]))
    xs = [l for l in links if l.link_type == LINK_CROSS_SOURCE]
    assert len(xs) == 1
    assert xs[0].right == "p:FEDCUT"


def test_cross_source_same_source_not_paired():
    a = MarketSignature(source="kalshi", external_id="k:1", question_norm="same q")
    b = MarketSignature(source="kalshi", external_id="k:2", question_norm="same q")
    links = ResolutionEngine().resolve(a, MatchUniverse(markets=[b]))
    assert not [l for l in links if l.link_type == LINK_CROSS_SOURCE]


def test_cross_source_line_direction_blocks_pair():
    over = MarketSignature(
        source="kalshi",
        external_id="k:OU",
        question_norm="points total",
        line=220.5,
        line_direction="over",
    )
    under = MarketSignature(
        source="polymarket",
        external_id="p:OU",
        question_norm="points total",
        line=220.5,
        line_direction="under",
    )
    links = ResolutionEngine().resolve(over, MatchUniverse(markets=[under]))
    assert not [l for l in links if l.link_type == LINK_CROSS_SOURCE]


# ---------------------------------------------------------------------------
# Strategy 4 — family / container
# ---------------------------------------------------------------------------
def test_family_key_from_container():
    ann = annotate_polymarket(
        event_id="12345",
        title="Best Picture 2026",
        markets=[{"group_item_title": "Oppenheimer"}, {"group_item_title": "Barbie"}],
    )
    sig = build_signature(ann, external_id="p:bestpic")
    links = ResolutionEngine().resolve(sig, MatchUniverse())
    fam = [l for l in links if l.link_type == LINK_FAMILY]
    assert len(fam) == 1
    assert fam[0].right == family_key("polymarket", "12345")


def test_family_key_deterministic():
    assert family_key("Kalshi", "KXNBA") == "kalshi:KXNBA"


# ---------------------------------------------------------------------------
# All four link types from one code path
# ---------------------------------------------------------------------------
def test_engine_emits_all_link_types_from_one_path():
    """One resolve() call over a rich universe emits every link type — proving the
    'one code path emits all four link types' acceptance criterion."""
    # A tennis match market that is: a game (2 participants), in a concept field,
    # cross-source-pairable, and inside a container.
    ann = annotate_kalshi(event_ticker="KXATPMATCH-1", title="Sabalenka vs Osaka")
    sig = build_signature(
        ann,
        external_id="k:MATCH1",
        event_date=date(2026, 7, 1),
        question="Sabalenka vs Osaka",
    )
    # give it a container so ContainerStrategy fires
    sig = MarketSignature(**{**sig.__dict__, "concept_ref": "SERIES-WIMB"})

    event = EventSignature(
        event_id=42,
        participants=sig.participants,
        event_date=date(2026, 7, 1),
    )
    concept = ConceptSignature(
        concept_ref="concept:wimb",
        entrant_keys=frozenset({"sabalenka", "osaka"}),
    )
    poly = MarketSignature(
        source="polymarket",
        external_id="p:MATCH1",
        question_norm=sig.question_norm,
    )
    buckets = ResolutionEngine().links_by_type(
        sig, MatchUniverse(events=[event], concepts=[concept], markets=[poly])
    )
    assert buckets[LINK_MARKET_EVENT], "expected a market→event link"
    assert buckets[LINK_MARKET_CONCEPT], "expected a market→concept link"
    assert buckets[LINK_CROSS_SOURCE], "expected a cross-source pair"
    assert buckets[LINK_FAMILY], "expected a family key"
