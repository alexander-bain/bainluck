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

# NOTE ON THE THIRD RETURN VALUE. #3980 added `unpriced_dropped` and this file
# was updated to unpack it, deliberately without folding the two counters
# together. Every assertion below still says what it said on 2026-09-08: these
# tests own the EMPTY-outcome rule, and `unpriced` is asserted `{}` in each of
# them so that a change which quietly re-routes an empty row into the other
# counter fails HERE. The unpriced rule has its own file,
# `test_an_unpriced_card_is_not_admitted_3980.py`.

import ast
import inspect
from datetime import datetime, timezone

from app.routes.league_futures import _drawable_sections

NOW = datetime(2026, 9, 8, 19, 0, tzinfo=timezone.utc)


def _row(id_, *probabilities):
    return {"id": id_, "top_outcomes": [{"probability": p} for p in probabilities]}


class TestDrawableSections:
    def test_a_row_with_no_outcomes_is_not_served(self):
        served, dropped, unpriced = _drawable_sections(
            {"matches": [_row(1, 0.495), _row(2), _row(3)]}, now=NOW
        )
        assert [m["id"] for m in served["matches"]] == [1]
        assert dropped == {"matches": 2}
        assert unpriced == {}, "an EMPTY row is counted as empty, not as unpriced"

    def test_a_section_whose_every_row_is_undrawable_is_removed(self):
        # Not served empty: an empty list is still a key, and a key is what a
        # client draws a heading from. This is baseball_mlb's `season_stats`.
        served, dropped, unpriced = _drawable_sections(
            {"season_stats": [_row(1)]}, now=NOW
        )
        assert "season_stats" not in served
        assert dropped == {"season_stats": 1}
        assert unpriced == {}

    def test_a_healthy_section_is_untouched_and_reports_no_drop(self):
        rows = [_row(1, 0.6), _row(2, 0.4, 0.6)]
        served, dropped, unpriced = _drawable_sections({"futures": rows}, now=NOW)
        assert served == {"futures": rows}
        assert dropped == {}, "a section that lost nothing must not appear at all"
        assert unpriced == {}

    def test_one_bad_section_never_empties_a_healthy_sibling(self):
        # gotcha #42 — one item's fate must not decide another's.
        served, dropped, unpriced = _drawable_sections(
            {"matches": [_row(1)], "futures": [_row(2, 0.5)]}, now=NOW
        )
        assert list(served) == ["futures"]
        assert dropped == {"matches": 1}
        assert unpriced == {}

    def test_an_empty_row_and_a_priceless_row_are_counted_apart(self):
        # WAS `test_a_row_with_a_none_probability_still_counts_as_drawable`, and
        # #3980 reversed its verdict on purpose: a card whose every outcome is
        # priceless draws names and no numbers, which is the defect that issue
        # filed. What this file still owns — and what this test now pins — is
        # that the two absences keep SEPARATE names. `no_outcomes` is an ingest
        # gap (#3412); `unpriced` is a row we have and cannot price. Merging
        # them would hide the first inside the second.
        served, dropped, unpriced = _drawable_sections(
            {"props": [_row(1, None), _row(2)]}, now=NOW
        )
        assert "props" not in served
        assert dropped == {"props": 1}, "row 2 is the EMPTY one"
        assert unpriced == {"props": 1}, "row 1 is the PRICELESS one"

    def test_the_input_is_not_mutated(self):
        # The caller's census holds the ORIGINAL lists; mutating them in place
        # would re-tier the page through the back door.
        original = {"matches": [_row(1, 0.5), _row(2)]}
        census_view = {name: rows for name, rows in original.items()}
        _drawable_sections(original, now=NOW)
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
        # Matched on the call OPENER, not on its arguments: #3980 added a keyword
        # and Black rewrapped the line, which would have broken an exact-text
        # match while the ordering this test exists to guard was untouched.
        filter_at = src.index("_drawable_sections(")
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
        assert '"shown": s["total"] - no_outcomes - unpriced_gone' in src, (
            "`shown` must be what the section SERVES; reading the census total "
            "here is the defect #3964 filed, and leaving the #3980 term off "
            "re-opens it one step along"
        )
