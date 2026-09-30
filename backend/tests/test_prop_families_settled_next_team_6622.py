"""#6622 — a team page stops listing a closed Next Team question this team did not win.

Production, 2026-09-30 09:38Z, ``/api/teams/seattle-kraken/prop-families``: the
Kraken's only prop race was "Next Team — 2 in the mix", both rows ``settled`` with
``result: null``, which the page prints as "NO RESULT":

* Sergei Bobrovsky's Next Team (Kalshi 55686441) — resolved, Kalshi graded
  Toronto Maple Leafs; the Kraken leg is ungraded (the route hands it over as
  ``is_winner: False``) with no price.
* NHL: Quinn Hughes Next Team (Polymarket 60495616) — marked resolved on
  2026-09-22 when Polymarket archived event 988786 without resolving it; the
  Kraken leg reads 0.085 and prints as 9%.

The Yankees page had the same shape (Juan Soto, market 34607706, winner New York
Mets, Yankees leg ``is_winner=false`` at 1.0 — "No result 100%").

The page only reaches such a market through this team's own leg, so a closed
question with no winning leg among the ones it holds is another team's signing or
a withdrawn market. The row is dropped. A leg that won keeps its row, and a live
Next Team question is untouched.
"""

from app.utils.prop_families import group_prop_families


def _market(mid, name, source, status, legs):
    return {
        "market_id": mid,
        "name": name,
        "source": source,
        "group_id": None,
        "status": status,
        "outcomes": [
            {"outcome_id": mid * 10 + i, "name": n, "probability": p, "is_winner": w}
            for i, (n, p, w) in enumerate(legs)
        ],
    }


# The production specimens exactly as the route hands them over for the Kraken:
# only the Kraken's own leg, ``is_winner`` coerced to a bool.
BOBROVSKY = _market(
    55686441, "Sergei Bobrovsky's Next Team", "kalshi", "resolved",
    [("Seattle Kraken", None, False)],
)
HUGHES = _market(
    60495616, "NHL: Quinn Hughes Next Team", "polymarket", "resolved",
    [("Seattle Kraken", 0.085, False)],
)


def _live(mid, player, prob):
    return _market(mid, f"{player} Next Team", "kalshi", "open", [("Seattle Kraken", prob, False)])


class TestClosedNextTeamOnAnotherTeamsPage:
    def test_the_kraken_page_has_no_next_team_card(self):
        # BEFORE: one family, two rows, both "NO RESULT", one at 9%.
        assert group_prop_families([BOBROVSKY, HUGHES]) == []

    def test_live_questions_keep_their_card_without_the_closed_rows(self):
        families = group_prop_families(
            [BOBROVSKY, HUGHES, _live(1, "Jared McCann", 0.3), _live(2, "Connor McDavid", 0.05)]
        )
        assert len(families) == 1
        rows = families[0]["rows"]
        assert {r["entity"] for r in rows} == {"Jared McCann", "Connor McDavid"}
        assert all(not r["settled"] for r in rows)
        assert families[0]["entity_count"] == 2

    def test_the_yankees_soto_row_is_dropped(self):
        soto = _market(
            34607706, "Juan Soto Next Team", "polymarket", "resolved",
            [("New York Yankees", 1.0, False)],
        )
        families = group_prop_families([soto, _live(3, "Aaron Judge", 0.2), _live(4, "Max Fried", 0.1)])
        assert {r["entity"] for r in families[0]["rows"]} == {"Aaron Judge", "Max Fried"}

    def test_a_closed_question_past_its_date_is_dropped_too(self):
        # Settled by resolution date alone (status still "open"), nothing graded.
        past = _market(
            5, "Bronny James' Next Team", "kalshi", "open", [("Seattle Kraken", 0.02, False)],
        )
        other = _market(
            6, "Bryce James' Next Team", "kalshi", "open", [("Seattle Kraken", 0.01, False)],
        )
        for m in (past, other):
            m["resolution_date"] = "2026-01-01T00:00:00+00:00"
        # No live row beside them: `_drop_earlier_results` leaves an all-settled
        # family alone, so only this rule can empty it.
        assert group_prop_families([past, other]) == []


class TestControls:
    def test_the_team_that_won_keeps_its_row(self):
        # Toronto's page: Toronto's own leg is the graded winner.
        won = _market(
            55686441, "Sergei Bobrovsky's Next Team", "kalshi", "resolved",
            [("Toronto Maple Leafs", 0.98, True)],
        )
        other_won = _market(
            8, "John Tavares Next Team", "kalshi", "resolved",
            [("Toronto Maple Leafs", 0.97, True)],
        )
        families = group_prop_families([won, other_won])
        assert len(families) == 1
        rows = {r["entity"]: r for r in families[0]["rows"]}
        assert rows["Sergei Bobrovsky"]["settled"] is True
        assert rows["Sergei Bobrovsky"]["result"] == "won"

    def test_a_closed_award_race_still_prints_its_loser(self):
        # The rule is scoped to Next Team: an award loser is a real result.
        award = _market(
            9, "NBA MVP", "kalshi", "resolved",
            [("Nikola Jokic", 1.0, True), ("Joel Embiid", 0.0, False)],
        )
        rows = {r["entity"]: r for r in group_prop_families([award])[0]["rows"]}
        assert rows["Joel Embiid"]["result"] == "lost"

    def test_a_closed_one_player_question_of_another_family_is_kept(self):
        # "X to win the Hart Trophy" with a graded No is a one-entity market in a
        # different family; it keeps its settled row.
        def hart(mid, player, yes_won):
            return _market(
                mid, f"{player} to win the Hart Trophy", "kalshi", "resolved",
                [("Yes", 1.0 if yes_won else 0.0, yes_won), ("No", 0.0 if yes_won else 1.0, not yes_won)],
            )

        families = group_prop_families([hart(10, "Connor McDavid", True), hart(11, "Nathan MacKinnon", False)])
        assert {r["entity"] for r in families[0]["rows"]} == {"Connor McDavid", "Nathan MacKinnon"}
