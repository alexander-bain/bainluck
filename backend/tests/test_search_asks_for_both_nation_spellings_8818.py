"""#8818 — search "czechia" asks for "czech republic" too.

Production 2026-09-27 15:2xZ, 390px: search `czechia` printed Tuesday's game as
Polymarket's copy 15313497 `Czechia v England` (OTHER SOCCER, letter badges,
venue price only), while `england` printed the Nations League row 15315653
`Czech Republic v England` with flags and every source. The serve fold
(`event_twin_fold._pair_matches_after_nation_spelling`) already joins the two —
but only when both rows are retrieved, and "czechia" never asked for the other
spelling. Same shape as #3391's `lafc`.
"""



class TestNationSpellingExpansion:
    def test_czechia_asks_for_czech_republic(self):
        from app.utils.name_normalization import expand_search_terms

        assert expand_search_terms(["czechia"]) == [("czechia", "czech republic")]
        assert expand_search_terms(["Czechia"]) == [("Czechia", "czech republic")]

    def test_turkiye_with_the_dotted_u_asks_for_turkey(self):
        from app.utils.name_normalization import expand_search_terms

        assert expand_search_terms(["türkiye"]) == [("türkiye", "turkey")]

    def test_the_event_predicate_asks_for_both_spellings(self):
        from app.routes.events import _event_name_match
        from app.utils.name_normalization import expand_search_terms

        term, expansion = expand_search_terms(["czechia"])[0]
        patterns = set(_event_name_match(term, expansion).compile().params.values())
        assert {"%czechia%", "%czech republic%"} <= patterns


class TestControls:
    def test_plain_keyboard_turkiye_keeps_its_diacritic_fold(self):
        """The nation entry is LAST: it fills an empty slot, displaces nothing."""
        from app.utils.name_normalization import expand_search_terms

        assert expand_search_terms(["turkiye"]) == [("turkiye", "türkiye")]

    def test_other_expansions_are_untouched(self):
        from app.utils.name_normalization import expand_search_terms

        assert expand_search_terms(["lafc"]) == [("lafc", "los angeles fc")]
        assert expand_search_terms(["la"]) == [("la", "los angeles")]
        assert expand_search_terms(["czech"]) == [("czech", None)]
        assert expand_search_terms(["england"]) == [("england", None)]
        # Already the one spelling: nothing to ask for.
        assert expand_search_terms(["turkey"]) == [("turkey", None)]


class TestTheRetrievedPairIsOneCard:
    """With both rows retrieved, the existing serve fold prints one card: the
    production specimen's two name pairs at one minute."""

    def test_the_specimen_pair_matches_after_spelling(self):
        from app.utils.event_twin_fold import _pair_matches

        assert _pair_matches(("czechia", "england"), ("czech republic", "england"))
        # Control: a different opponent never joins.
        assert not _pair_matches(("czechia", "croatia"), ("czech republic", "england"))
