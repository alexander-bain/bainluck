"""#1206 (Queue #248 Item 2): the search event-concept query-token gate.

Regression guard for r260/r262's find: an Emmys market's TV-"Series" nominee
FTS-matched unrelated queries ("world series", "champions league winner"), and the
awards deriver surfaced "The Emmys" concept ABOVE the correct futures. The fix
gates the loop-derived awards concept on `_query_names_concept` — the query must
share a distinctive token/stem with the concept's own identity.

Pure unit tests (no DB): the acceptance is expressed directly on the gate.
- broken queries must NOT name the Emmys concept  -> futures lead
- ceremony-named queries MUST still name it        -> concept leads (via loop or
  the query-gated prepend)
"""

from app.routes.events import _query_names_concept, _concept_match_tokens

_EMMYS = {"key": "event:awards:emmys", "name": "The Emmys", "domain": "awards"}
_OSCARS = {"key": "event:awards:oscars", "name": "The Oscars", "domain": "awards"}
_GRAMMYS = {"key": "event:awards:grammys", "name": "The Grammys", "domain": "awards"}
_GOLF_MASTERS = {"key": "event:golf:the-masters", "name": "The Masters", "domain": "golf"}


class TestConceptMatchTokens:
    def test_drops_generic_and_short_tokens(self):
        assert _concept_match_tokens("The World Series Winner") == {"series"}

    def test_empty(self):
        assert _concept_match_tokens("") == set()
        assert _concept_match_tokens(None) == set()


class TestQueryNamesConcept:
    # --- the two broken queries must NOT surface the Emmys concept ------------
    def test_world_series_does_not_name_emmys(self):
        assert _query_names_concept("world series", _EMMYS) is False

    def test_champions_league_winner_does_not_name_emmys(self):
        assert _query_names_concept("champions league winner", _EMMYS) is False

    # --- the ceremony-named queries MUST still name their concept -------------
    def test_the_emmys_names_emmys(self):
        assert _query_names_concept("the emmys", _EMMYS) is True

    def test_bare_emmys_names_emmys(self):
        assert _query_names_concept("emmys", _EMMYS) is True

    def test_singular_emmy_stem_matches(self):
        assert _query_names_concept("emmy predictions", _EMMYS) is True

    def test_oscars_and_stemmed_oscar(self):
        assert _query_names_concept("oscars", _OSCARS) is True
        assert _query_names_concept("best picture oscar", _OSCARS) is True

    def test_grammys(self):
        assert _query_names_concept("grammys", _GRAMMYS) is True

    # --- cross-concept isolation --------------------------------------------
    def test_world_series_does_not_name_masters(self):
        assert _query_names_concept("world series", _GOLF_MASTERS) is False

    def test_masters_names_masters(self):
        # (golf surfaces via the query-gated prepend, but the gate agrees)
        assert _query_names_concept("masters", _GOLF_MASTERS) is True

    def test_world_series_does_not_name_grammys(self):
        assert _query_names_concept("world series", _GRAMMYS) is False

    # --- degenerate inputs ---------------------------------------------------
    def test_empty_query_is_false(self):
        assert _query_names_concept("", _EMMYS) is False
        assert _query_names_concept(None, _EMMYS) is False

    def test_all_generic_query_is_false(self):
        # a query of only stopwords shares nothing distinctive
        assert _query_names_concept("the winner", _EMMYS) is False
