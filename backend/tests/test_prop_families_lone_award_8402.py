"""#8402 — a team with ONE candidate in a live season-award race gets its card.

Not a regression of #8386. That fix (08c6f5ebee, live 16:24:51Z 2026-09-24)
correctly took the Super Bowl MVP question out of the Chiefs' season-MVP card —
and the card vanished, because the team route narrows every market to the team's
own players before grouping and ``group_prop_families`` wanted two distinct
entities. The Chiefs hold exactly one MVP candidate: Patrick Mahomes, 8.75%. The
card had only ever shown because the Super Bowl question counted as a second.

The fixtures are the production titles of the specimen's rows (read-only
db-query, 2026-09-24 16:3xZ).
"""

from app.utils.prop_families import group_prop_families


def _market(mid, name, source, group_id, outcomes, status="open", sport="football"):
    return {
        "market_id": mid,
        "name": name,
        "source": source,
        "group_id": group_id,
        "status": status,
        "sport": sport,
        "resolution_date": None,
        "market_metadata": None,
        "outcomes": [
            {"outcome_id": oid, "name": n, "probability": p, "is_winner": w}
            for oid, n, p, w in outcomes
        ],
    }


# The Chiefs page's MVP inputs as the team route hands them to the grouper.
POLY_MVP = _market(7585490, "Pro Football: 2026 MVP Winner", "polymarket",
                   "polymarket:315364", [(40281028, "Patrick Mahomes", 0.0875, False)])
KALSHI_MVP = _market(40532, "MVP Winner?", "kalshi", "kalshi:KXNFLMVP-27",
                     [(643789, "Patrick Mahomes", 0.085, False)])
KALSHI_MVP_FINALISTS = _market(59164988, "MVP Finalists", "kalshi",
                               "kalshi:KXNFLAWARDFIN-27MVP",
                               [(225945039, "Patrick Mahomes", None, False),
                                (230044459, "Kenneth Walker", None, False)])
KALSHI_SB_MVP = _market(479, "Pro Football Championship MVP?", "kalshi",
                        "kalshi:KXNFLSBMVP-26",
                        [(6968, "Will Kenneth Walker III win the Pro Football "
                                "Championship Game MVP?", 0.085, False)])


def _by_key(families):
    return {f["family_key"]: f for f in families}


class TestTheChiefsMvpCardComesBack:
    def test_mahomes_heads_a_one_row_mvp_card(self):
        fams = _by_key(group_prop_families(
            [POLY_MVP, KALSHI_MVP, KALSHI_MVP_FINALISTS, KALSHI_SB_MVP]))
        assert "mvp" in fams, f"no MVP card; families={sorted(fams)}"
        mvp = fams["mvp"]
        assert mvp["label"] == "MVP"
        assert [r["entity"] for r in mvp["rows"]] == ["Patrick Mahomes"]
        assert mvp["entity_count"] == 1
        # Both venues' winner markets, never the finalists market (#8385).
        assert sorted(mvp["rows"][0]["sources"]) == ["kalshi", "polymarket"]
        assert 59164988 not in (mvp["rows"][0].get("merged_market_ids") or [])
        assert 0.08 <= mvp["rows"][0]["probability"] <= 0.09

    def test_the_super_bowl_question_stays_out_and_gets_no_card_of_its_own(self):
        fams = group_prop_families(
            [POLY_MVP, KALSHI_MVP, KALSHI_MVP_FINALISTS, KALSHI_SB_MVP])
        assert [f["family_key"] for f in fams] == ["mvp"]
        for f in fams:
            for r in f["rows"]:
                assert "Championship" not in (r["entity"] or "")


class TestTheExceptionIsNarrow:
    def test_a_lone_of_the_year_candidate_renders(self):
        fams = _by_key(group_prop_families([_market(
            1, "Pro Football: Offensive Player of the Year", "polymarket",
            "polymarket:1", [(1, "Kenneth Walker III", 0.076, False)])]))
        assert list(fams) == ["offensive player of the year"]

    def test_a_lone_single_game_mvp_does_not(self):
        assert group_prop_families([KALSHI_SB_MVP]) == []

    def test_a_lone_finals_mvp_does_not(self):
        assert group_prop_families([_market(
            2, "NBA Finals MVP", "kalshi", None,
            [(2, "Nikola Jokic", 0.2, False)], sport="basketball")]) == []

    def test_a_lone_non_award_prop_does_not(self):
        assert group_prop_families([_market(
            3, "Travis Kelce Next Team", "kalshi", None,
            [(3, "Kansas City Chiefs", 0.6, False)])]) == []

    def test_a_lone_settled_award_does_not(self):
        """Last season's resolved MVP question is a result, not a race to show alone."""
        assert group_prop_families([_market(
            4, "Pro Football: 2025 MVP Winner", "polymarket", "polymarket:4",
            [(4, "Patrick Mahomes", 0.0, False)], status="settled")]) == []

    def test_two_entity_families_are_unchanged(self):
        fams = group_prop_families([_market(
            5, "NBA MVP", "kalshi", None,
            [(5, "Nikola Jokic", 0.4, False), (6, "Jamal Murray", 0.01, False)],
            sport="basketball")])
        assert [(f["family_key"], f["entity_count"]) for f in fams] == [("mvp", 2)]
