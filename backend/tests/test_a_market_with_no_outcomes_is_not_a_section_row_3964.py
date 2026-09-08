"""#3964 defect 2 — a market with no outcomes is not a row a client can draw.

WHAT A READER SAW. `https://bainluck.com/sport/boxing/boxing` at 390px on
2026-09-08, twice, so not a mid-load frame:

    📋  UPCOMING MATCHES   (10)

                                    <- nothing. At all.

    🎯  YES / NO   (2)

`GET /api/leagues/boxing_boxing` explains it and indicts itself in the same
breath: `sections.matches` carries twelve rows, **ten of them with
`top_outcomes: []` and `outcome_count: 0`** — the markets have no
`futures_outcomes` rows at all — while `section_counts.matches` reads

    {total: 12, shown: 12, dropped: 10, answers: 2}

Twelve rows called SHOWN, of which two can draw, and `shown + dropped` exceeding
`total` by the size of the lie.

TWO HALVES, AND THIS IS THE SECOND. `533ff05d` stopped the web header outliving
its cards (the count now measures what will draw). That fix is web-only: the iOS
app decodes the same `sections` off the same endpoint. Stopping the rows from
being SERVED is the half that reaches every client, and it is the half that stops
the next zero-outcome row re-opening the hole somewhere new.

MEASURED, production 2026-09-08, served payloads at ten league pages:

    boxing_boxing     10 of 12 `matches` rows undrawable
    soccer_epl        18 rows across FOUR sections (series 3/5, props 6/22,
                      season_stats 3/5, more_markets 6/20)
    americanfootball_nfl   15 of 88 `more_markets`
    tennis_atp         6 of 73 `matches`
    baseball_mlb       1 of 1 `season_stats` — the whole section is undrawable
    basketball_nba, icehockey_nhl   none

and 4,471 open `soccer_other` markets carry zero outcomes in the table behind it.

THE TRAP THIS CHANGE COULD HAVE FALLEN INTO. The tier resolver reads the same
dict. Filtering BEFORE the census is taken would have re-tiered every affected
page — MLB would lose a whole populated section from its chrome decision — on
the strength of today's serialization. The census counts what the LEAGUE HAS;
the payload carries what a CLIENT CAN DRAW. `test_the_census_is_taken_before_the
_filter` is that ordering, made executable.
"""

import ast
import inspect

from app.routes.league_futures import _drawable_sections


def _row(id_, *probabilities):
    return {"id": id_, "top_outcomes": [{"probability": p} for p in probabilities]}


class TestDrawableSections:
    def test_a_row_with_no_outcomes_is_not_served(self):
        served, dropped = _drawable_sections(
            {"matches": [_row(1, 0.495), _row(2), _row(3)]}
        )
        assert [m["id"] for m in served["matches"]] == [1]
        assert dropped == {"matches": 2}

    def test_a_section_whose_every_row_is_undrawable_is_removed(self):
        # Not served empty: an empty list is still a key, and a key is what a
        # client draws a heading from. This is baseball_mlb's `season_stats`.
        served, dropped = _drawable_sections({"season_stats": [_row(1)]})
        assert "season_stats" not in served
        assert dropped == {"season_stats": 1}

    def test_a_healthy_section_is_untouched_and_reports_no_drop(self):
        rows = [_row(1, 0.6), _row(2, 0.4, 0.6)]
        served, dropped = _drawable_sections({"futures": rows})
        assert served == {"futures": rows}
        assert dropped == {}, "a section that lost nothing must not appear at all"

    def test_one_bad_section_never_empties_a_healthy_sibling(self):
        # gotcha #42 — one item's fate must not decide another's.
        served, dropped = _drawable_sections(
            {"matches": [_row(1)], "futures": [_row(2, 0.5)]}
        )
        assert list(served) == ["futures"]
        assert dropped == {"matches": 1}

    def test_a_row_with_a_none_probability_still_counts_as_drawable(self):
        # An outcome with no price is a row the card CAN draw (it renders the
        # name and no number); a row with no outcomes at all is not. The two
        # absences are different and only the second one is this rule's.
        served, dropped = _drawable_sections({"props": [_row(1, None)]})
        assert [m["id"] for m in served["props"]] == [1]
        assert dropped == {}

    def test_the_input_is_not_mutated(self):
        # The caller's census holds the ORIGINAL lists; mutating them in place
        # would re-tier the page through the back door.
        original = {"matches": [_row(1, 0.5), _row(2)]}
        census_view = {name: rows for name, rows in original.items()}
        _drawable_sections(original)
        assert len(census_view["matches"]) == 2
        assert len(original["matches"]) == 2


class TestTheRouteIsWiredTheRightWayRound:
    """Correct is not called, and called is not called IN THE RIGHT ORDER."""

    def _route_source(self):
        from app.routes.league_futures import build_league

        # `build_league`, not the cached `get_league_futures` wrapper: the
        # builder is where the census and the payload part company.
        return inspect.getsource(build_league)

    def test_the_route_calls_the_filter(self):
        tree = ast.parse(self._route_source().lstrip())
        called = {
            n.func.id
            for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        }
        assert "_drawable_sections" in called, (
            "the payload must be filtered through the helper, not by a second "
            "inline rule that can drift from it"
        )

    def test_the_census_is_taken_before_the_filter(self):
        # THE ORDERING IS THE WHOLE GUARD. Reversed, the tier resolver would see
        # the filtered world and every affected page could silently change tier.
        src = self._route_source()
        census_at = src.index("census_sections = dict(sections)")
        filter_at = src.index("_drawable_sections(sections)")
        assert census_at < filter_at, (
            "census_sections must be copied from the UNFILTERED sections — the "
            "census counts what the league has, the payload carries what a "
            "client can draw"
        )

    def test_the_envelope_declares_the_drop_under_its_own_name(self):
        # A drop that is not counted is a drop nobody finds, and folding it into
        # `dropped` would hide an ingest gap inside a pricing statistic.
        src = self._route_source()
        assert '"no_outcomes": no_outcomes' in src
        assert '"shown": s["total"] - no_outcomes' in src, (
            "`shown` must be what the section SERVES; reading the census total "
            "here is the defect #3964 filed"
        )
