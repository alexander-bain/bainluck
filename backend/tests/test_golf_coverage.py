"""Golf tournament coverage fixes (Queue #83 — #951 Round-N regex, #952 yes/no props).

#951: "Round N Top M Finishers" markets were classified as tournament top_M by the
bare \\bTop\\s+N\\b patterns and averaged INTO the tournament Top-N grid column
(data corruption). They now classify as "round_top", excluded from placement.

#952: non-winner yes/no markets (playoff, hole-in-one, first-time winner, ...)
were dropped at the <=2-outcome gate; they now surface as single-probability props.
"""

from types import SimpleNamespace

from app.routes.golf import _detect_market_type, _extract_yes_no_prop


def _mkt(name, source="kalshi", outcomes=None):
    return SimpleNamespace(name=name, source=source, outcomes=outcomes or [])


def _oc(name, prob):
    return SimpleNamespace(name=name, current_probability=prob)


class TestRoundTopCollision:
    def test_round_top_not_classified_as_tournament_top(self):
        # The exact prod names that were corrupting the Top-N columns.
        assert _detect_market_type("U.s. Open: Round 1 Top 10 Finishers")[0] == "round_top"
        assert _detect_market_type("U.s. Open: Round 2 Top 5 Finishers")[0] == "round_top"
        assert _detect_market_type("The Memorial Tournament: Round 3 Top 10 Finishers")[0] == "round_top"

    def test_tournament_top_still_classified(self):
        # Tournament-wide Top-N (no "Round N") is unchanged.
        assert _detect_market_type("U.S. Open: Top 5 Finishers")[0] == "top_5"
        assert _detect_market_type("U.S. Open: Top 10")[0] == "top_10"
        assert _detect_market_type("U.S. Open: Top 20")[0] == "top_20"
        # Alex's ruling (The Open 2026): Top 40 is a placement column, not "other".
        assert _detect_market_type("The Open Championship: Top 40 Finishers")[0] == "top_40"
        assert _detect_market_type("U.S. Open: Round 1 Top 40 Finishers")[0] == "round_top"

    def test_round_leader_still_classified(self):
        # The round_top guard must NOT swallow "Round N Leader".
        assert _detect_market_type("U.S. Open: Round 1 Leader")[0] == "round_leader"

    def test_round_top_excluded_from_placement_set(self):
        # The placement columns the tournament grid averages — round_top must NOT
        # be one of them (that's the corruption guard).
        placement_types = ("top_5", "top_10", "top_20", "make_cut", "round_leader")
        assert "round_top" not in placement_types


class TestYesNoProp:
    def test_yes_outcome_surfaces_as_single_prob(self):
        m = _mkt("U.S. Open: Playoff", outcomes=[_oc("Yes", 0.22), _oc("No", 0.78)])
        prop = _extract_yes_no_prop(m, "kalshi")
        assert prop is not None
        assert prop["kind"] == "binary"
        assert prop["yes_probability"] == 0.22
        assert prop["outcomes"] == [{"name": "Yes", "probability": 0.22}]

    def test_no_only_market_infers_yes(self):
        m = _mkt("U.S. Open: First Time Winner?", outcomes=[_oc("No", 0.6)])
        prop = _extract_yes_no_prop(m, "kalshi")
        assert prop is not None and abs(prop["yes_probability"] - 0.4) < 1e-9

    def test_kalshi_untraded_half_is_dropped(self):
        m = _mkt("U.S. Open: Hole-in-One", source="kalshi", outcomes=[_oc("Yes", 0.5)])
        assert _extract_yes_no_prop(m, "kalshi") is None

    def test_no_probability_returns_none(self):
        m = _mkt("U.S. Open: Albatross", outcomes=[_oc("Yes", None)])
        assert _extract_yes_no_prop(m, "kalshi") is None


class TestRoundTopGroups:
    """#951 + L2-89: round_top AND round_leader markets exposed per-round/tier
    with outcomes (both surface in the frontend Rounds panel)."""

    def test_round_top_groups_built_and_exposed(self):
        import inspect
        from app.routes.golf import get_golf_tournament
        src = inspect.getsource(get_golf_tournament)
        # builds the structure from the round_top + round_leader market groups
        assert "round_top_groups" in src
        assert 'g["type"] == "round_top"' in src
        assert 'g["type"] == "round_leader"' in src  # L2-89: leaders folded in
        # parses the round number from the market name (shared by both kinds)
        assert r"Round\s+(\d+)" in src
        # tags each entry so the frontend can label leader vs top-N
        assert '"kind": kind,' in src
        # false-positive-safe: skips groups with no outcomes (no bare cards)
        assert "if not outs:" in src
        # exposed on the response
        assert '"round_top_groups": round_top_groups,' in src

    def test_round_top_name_parse(self):
        # the round/tier parse the builder relies on
        import re
        for name, rnd, top in [
            ("2026 U.S. Open: Round 1 Top 5 Finishers", 1, 5),
            ("The Memorial Tournament: Round 3 Top 10 Finishers", 3, 10),
            ("U.S. Open: Round 2 Top 20 Finishers", 2, 20),
        ]:
            m = re.search(r"Round\s+(\d+)\s+Top\s+(\d+)", name, re.I)
            assert m and int(m.group(1)) == rnd and int(m.group(2)) == top
