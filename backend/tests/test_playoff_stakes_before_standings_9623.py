"""#9623 — a playoff game's stakes chip says it is a playoff game.

Seen on production 2026-09-29 13:20Z at 390px: `/events/15319563`, Red Sox @
Yankees, AL Wild Card Game 1. The event carried `importance:playoff` and the
page's only context chip read "Division rivals" — the standings rule (same
division, div_rank within 2) answered first because it never looked at the
event's own importance. In a Wild Card round every pairing is two winning teams
and often two from one division, so the whole round read as regular season.

Every case that asserts the playoff words has a sibling asserting the standings
rule still answers an untagged game, so a blanket rewrite of the chip fails.
"""

import ast
from pathlib import Path
from types import SimpleNamespace

from app.routes.events import _compute_standings_context

# The specimen as production served it (records 93-68 / 87-75, both AL East,
# div_rank 2 and 3 — exactly the pair the division rule fires on).
YANKEES = SimpleNamespace(
    standings_data={"division": "East", "div_rank": 2, "wins": 93, "losses": 68}
)
RED_SOX = SimpleNamespace(
    standings_data={"division": "East", "div_rank": 3, "wins": 87, "losses": 75}
)


def _ctx(importance):
    return _compute_standings_context(
        YANKEES, RED_SOX, "New York Yankees", "Boston Red Sox", importance=importance
    )


class TestImportanceComesFirst:
    def test_the_wild_card_specimen_reads_playoff_game(self):
        ctx = _ctx("playoff")
        assert ctx["stakes"] == "Playoff game"
        # The records are untouched — only the chip changes.
        assert ctx["home"] == "93-68, #2 East"
        assert ctx["away"] == "87-75, #3 East"

    def test_the_same_pair_untagged_still_reads_division_rivals(self):
        # Control: the standings rule is right for a regular-season game.
        assert _ctx(None)["stakes"] == "Division rivals"
        assert _ctx("regular")["stakes"] == "Division rivals"

    def test_a_championship_reads_championship_game(self):
        assert _ctx("championship")["stakes"] == "Championship game"

    def test_the_words_match_the_feed_card_for_the_same_importance(self):
        # The card and the page it opens say the same thing.
        from app.utils import highlights

        src = Path(highlights.__file__).read_text()
        assert '("playoff", "Playoff game")' in src
        assert '("championship", "Championship game")' in src

    def test_no_standings_rows_still_returns_none(self):
        # The chip rides the standings box; with no records there is no box,
        # so importance alone does not invent one.
        empty = SimpleNamespace(standings_data=None)
        assert (
            _compute_standings_context(empty, empty, "A", "B", importance="playoff")
            is None
        )


def test_the_event_route_passes_the_events_importance():
    """The helper change is inert unless the route hands it the importance."""
    src = Path(__file__).resolve().parents[1] / "app" / "routes" / "events.py"
    tree = ast.parse(src.read_text())
    calls = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and getattr(n.func, "id", None) == "_compute_standings_context"
    ]
    assert calls, "no call site found"
    for call in calls:
        kw = {k.arg: k.value for k in call.keywords}
        assert "importance" in kw, "a call site does not pass importance"
        assert "llm_importance" in ast.unparse(kw["importance"])
