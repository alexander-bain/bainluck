"""#3094 / D55 — the LIVE endpoint's id is not always the anchor's id space.

`events.statpal_fixture_id` is the column every StatPal linkage joins on, and on
MLB it holds two id spaces at once. Measured on production 2026-09-06:

    6-digit  (season-schedule.id)   1,653 rows
    10-digit (livescores.id)          364 rows   <- the wrong space

364, up from the 322 counted when #3094 was filed on 09-04, with the newest row
dated the day of this fix: the writer was still producing them. All 5 duplicate
MLB StatPal ids in the table sit in the 10-digit space; the 6-digit space has
zero.

`authority/016`'s measured ruling (`tests/test_statpal_mlb_id_spaces.py`) says
anchor on `oddsid` -> `id`, never `livescores.id`, never `stats_id`. The live
parser instead builds `id or contestid or fixture_id`, and for MLB `item["id"]`
on a livescores payload IS `livescores.id`.

## Why a declaration and not a shape check — the trap that makes this D55

`livescores.id` spans 1329192580..1329202652. Schedule `stats_id` spans
1329190986..1329201329. Same width, same prefix, overlapping ranges, **not one
value in common**. A rule that picks the space by digit count or numeric range
joins them confidently and wrongly, which is precisely the failure #2879 removed
from the anchor key. So the sport declares its field and nothing is inferred.

## What these tests are careful NOT to assert

That every sport should use `oddsid`. The parser's answer is right everywhere it
has been measured except MLB, and a rule applied to sports nobody has measured is
the standing appointment #2879's docstring warns about. The map is the exception
list; the tests below pin the exception, the default, and the two couplings that
would break silently.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pytest

from app.tasks.statpal_sync import _live_anchor_id
from app.utils.sport_keys import (
    STATPAL_LIVE_ANCHOR_FIELD,
    STATPAL_PBP_SPORTS,
    STATPAL_SPORT_MAPPING,
)

#: The two spaces, from the 2026-09-04 measurement in the artifact.
LIVE_ID = "1329192580"  # livescores.id — dereferences to nothing on the schedule
ODDS_ID = "354453"  # livescores.oddsid == season-schedule.id — the anchor


@dataclass
class _Fixture:
    """Only the two attributes the helper reads.

    Deliberately not the real `StatPalFixture`: this pins the CONTRACT (which
    attribute is chosen), and a real object would let a future field appear in
    the fallback chain without any test noticing.
    """

    fixture_id: str = ""
    odds_id: Optional[str] = None


# ---------------------------------------------------------------------------
# The exception, and the default it is an exception to
# ---------------------------------------------------------------------------


def test_mlb_anchors_on_oddsid_and_not_on_the_live_id():
    """The whole of #3094 in one assertion, with both ids present.

    Both fields are populated on purpose. If only `odds_id` were set, a helper
    that had simply stopped reading `fixture_id` would pass, and so would one
    that read neither and returned the first non-empty attribute it found.
    """
    got = _live_anchor_id(_Fixture(fixture_id=LIVE_ID, odds_id=ODDS_ID), "mlb")

    assert got == ODDS_ID
    assert got != LIVE_ID, "the live id is the space the anchor must not be in"


@pytest.mark.parametrize("statpal_sport", ["nfl", "nba", "nhl", "tennis", "soccer"])
def test_every_other_sport_keeps_the_parser_answer_unchanged(statpal_sport):
    """The must-not-regress arm (gotcha #43).

    This change is a declaration for one measured exception. A version that
    routed every sport through `oddsid` would blank the anchor for the four
    sports that do not serve the field — NFL alone holds 293 live anchors — and
    the census would read as a clean run having stamped nothing.
    """
    assert _live_anchor_id(_Fixture(fixture_id=LIVE_ID), statpal_sport) == LIVE_ID


def test_an_unmapped_sport_still_gets_an_anchor():
    """A sport nobody has added to the map is a sport whose live id is fine
    until measured otherwise — not a sport that stops being anchorable."""
    assert _live_anchor_id(_Fixture(fixture_id="999999"), "handball") == "999999"


# ---------------------------------------------------------------------------
# The refusal: an empty declared field writes NOTHING, never the live id
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("odds_id", [None, "", "   "])
def test_mlb_without_an_oddsid_refuses_rather_than_falling_back(odds_id):
    """3 of 16 live MLB rows carried `oddsid: ""` when this was measured, so the
    residue is the normal case and not an edge.

    Falling back to `fixture_id` here is the single most tempting edit in this
    change and it would reinstate the entire bug for those rows. An empty column
    is a row the schedule pass can still anchor correctly; a wrong-space id is a
    linkage that reads as authoritative and dereferences to nothing.
    """
    assert _live_anchor_id(_Fixture(fixture_id=LIVE_ID, odds_id=odds_id), "mlb") is None


def test_a_missing_fixture_id_is_still_no_anchor_for_an_undeclared_sport():
    """The default path refuses a blank too — 8,272 rows once carried `''`
    (`scripts/repair_statpal_fixture_id_blanks.py`), and a blank id is not an
    absence, it is an unusable linkage."""
    assert _live_anchor_id(_Fixture(fixture_id=""), "nfl") is None
    assert _live_anchor_id(_Fixture(fixture_id="   "), "nfl") is None


def test_the_id_is_stringified_and_stripped_like_the_column_expects():
    """`statpal_fixture_id` is compared by equality all over the codebase, so a
    stray int or a padded string is a join that silently misses."""
    assert _live_anchor_id(_Fixture(fixture_id=LIVE_ID, odds_id="  354453  "), "mlb") == "354453"

    numeric = _Fixture(fixture_id=LIVE_ID)
    numeric.odds_id = 354453  # type: ignore[assignment]
    assert _live_anchor_id(numeric, "mlb") == "354453"


# ---------------------------------------------------------------------------
# The two couplings that would break silently
# ---------------------------------------------------------------------------


def test_no_sport_both_declares_an_anchor_field_and_serves_play_by_play():
    """`events.statpal_fixture_id` has a SECOND consumer with the opposite need.

    `sync_statpal_playbyplay` passes that column to `fixtures/{id}/playbyplay`,
    which is keyed by the LIVE id. A sport in both sets would have its PBP calls
    keyed by the schedule id and get 404s — a live feature going quiet, with no
    error, because a linkage fix changed what the column means.

    Disjoint today (PBP is NFL-only; the map is MLB-only) and this is what makes
    adding MLB to `STATPAL_PBP_SPORTS` fail loudly. If that day comes the fix is
    to give PBP its own id, not to delete this test.
    """
    overlap = set(STATPAL_LIVE_ANCHOR_FIELD) & STATPAL_PBP_SPORTS
    assert not overlap, (
        f"{sorted(overlap)} both declare an anchor field and serve play-by-play; "
        f"the PBP call needs the LIVE id and would now be handed the schedule id"
    )


def test_the_map_only_names_sports_we_actually_sync():
    """A key nobody reaches is a rule that looks applied and is not — the
    zero-yield sweep that reads as a success (gotcha #53)."""
    known = set(STATPAL_SPORT_MAPPING.values())
    unknown = set(STATPAL_LIVE_ANCHOR_FIELD) - known
    assert not unknown, f"{sorted(unknown)} is not a StatPal sport we sync"


def test_every_declared_field_exists_on_the_real_fixture_object():
    """The map names ATTRIBUTES, and `_live_anchor_id` reads them with `getattr`.

    A typo would therefore not raise — it would return `None` for every row of
    that sport, forever, and present as "this sport just does not serve the
    field". Checked against the real dataclass rather than the stand-in above,
    because the stand-in is where a typo would be copied to.
    """
    from app.services.statpal_api import StatPalFixture

    for sport, field in STATPAL_LIVE_ANCHOR_FIELD.items():
        assert field in StatPalFixture.__annotations__, (
            f"{sport} declares anchor field {field!r}, which StatPalFixture does "
            f"not have — getattr would silently return None for every row"
        )


# ---------------------------------------------------------------------------
# The schedule writer is deliberately NOT changed
# ---------------------------------------------------------------------------


def test_the_schedule_endpoint_for_mlb_is_the_one_whose_id_is_the_anchor():
    """Why only the LIVE write site moved.

    `get_fixtures` reads `_SCHEDULE_ENDPOINTS[sport]`, and for MLB that is
    `season-schedule`, whose `id` IS the anchor space (227/227 filled, 227
    distinct, 0 collisions). Routing that path through `oddsid` too would blank
    the anchor on every scheduled MLB row, because `season-schedule` does not
    serve the field.

    Pinned against the live constant: if MLB's schedule endpoint is ever pointed
    at `livescores`, the schedule writer becomes wrong in exactly the way the
    live one was, and this fails instead of the bug re-appearing quietly.
    """
    from app.services.statpal_api import StatPalAPIService

    assert StatPalAPIService._SCHEDULE_ENDPOINTS["mlb"] == "season-schedule"
