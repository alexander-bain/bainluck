"""Golf tournament "More Markets" cross-source dedup (Queue #81 — #956).

Two source markets for one question rendered as two stacked cards with
conflicting probabilities (Polymarket "Will there be a playoff..." 27% vs Kalshi
"U.S. Open: Playoff" 22%). Their normalized question text does NOT match, so the
playoff family is keyed explicitly; everything else falls back to the normalized
question (collapses only exact cross-source dupes, not the distinct multi-winner
family).
"""

from app.routes.golf import _related_dedup_key, _RELATED_SOURCE_PRIORITY


class TestRelatedDedupKey:
    def test_both_playoff_phrasings_collapse(self):
        poly = _related_dedup_key("Will there be a playoff at the 2026 U.S. Open?")
        kalshi = _related_dedup_key("U.S. Open: Playoff")
        assert poly == kalshi == "playoff"

    def test_distinct_questions_do_not_collapse(self):
        # Hole-in-one and nationality must NOT merge with each other or playoff.
        hio = _related_dedup_key("U.S. Open: Hole-in-One")
        nat = _related_dedup_key("2026 U.S. Open: Winner Nationality")
        playoff = _related_dedup_key("U.S. Open: Playoff")
        assert len({hio, nat, playoff}) == 3

    def test_non_playoff_falls_back_to_normalized_question(self):
        # Non-playoff markets key on the normalized question, so only EXACT
        # cross-source dupes collapse (not the distinct multi-winner family).
        from app.utils.cross_source_matching import normalize_question

        name = "U.S. Open: Winning Score"
        assert _related_dedup_key(name) == normalize_question(name)
        assert _related_dedup_key(name) != "playoff"

    def test_source_priority_prefers_datagolf_then_liquidity(self):
        assert _RELATED_SOURCE_PRIORITY["datagolf"] < _RELATED_SOURCE_PRIORITY["polymarket"]
        assert _RELATED_SOURCE_PRIORITY["polymarket"] < _RELATED_SOURCE_PRIORITY["kalshi"]
        assert _RELATED_SOURCE_PRIORITY["kalshi"] < _RELATED_SOURCE_PRIORITY["odds_api"]
