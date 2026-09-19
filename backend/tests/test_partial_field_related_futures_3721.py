"""#3721, THE SECOND DOOR — Bigger Picture stops drawing a slice as the field.

The event page is built from TWO payloads and the reader cannot tell them
apart. `/api/events/{id}/game-markets` feeds the props sections;
`/api/events/{id}/related-futures` feeds "Bigger Picture". The first half of
#3721 withheld short fields from `/game-markets` only, so the fragment kept
arriving on the same page through the other door.

THE SPECIMEN, read on production 2026-09-18 with the first half ALREADY LIVE at
`6044e4b47`. `/events/15195325`, Germany v Greece (Sep 27). `/game-markets`
served `other = 0` rows — the first half working exactly as shipped — and the
page still rendered, under a heading reading `OTHER (3)`:

    Germany 3 - 2 Greece     50%     market 61032702, 2 legs stored of 17
    Germany 2 - 1 Greece     49%     market 61032702
    Germany                  79%     market 61032733, 1 leg stored of 3

Seventeen scorelines exist at the venue and the card showed two of them at ~50%
each, which is not a ladder a reader can read: the two rungs shown are the two
we happened to store, not the two most likely.

MEASURED REACH, same hour, upcoming events only: 2,257 short Polymarket fields
across 671 events holding 3,729 stored legs, and 0 short Kalshi fields of 768 —
the same source asymmetry the first half measured. On eight sampled event pages
89 of 250 served Bigger Picture rows came from short fields.

THE CONTROLS BELOW ARE THE POINT. The failure this guard can cause is worse
than the defect it fixes, and it has a specific shape here that the first door
does not have: a 3-way result splits its legs across the two lists, so a
per-list count would read every complete draw-carrying market as short. That is
`test_three_way_result_split_across_sides_is_complete`, and it fails against a
per-list implementation.
"""

from types import SimpleNamespace

import pytest

from app.routes.events import _withhold_partial_field_futures


def _market(market_id, name, *, declared=None, event_title=None, mex=True):
    """A futures market as the builder holds it: id, name, mex flag, metadata."""
    meta = {}
    if event_title is not None:
        meta["event_title"] = event_title
    if declared is not None:
        meta["market_count"] = declared
    return SimpleNamespace(
        id=market_id,
        name=name,
        mutually_exclusive=mex,
        market_metadata=meta,
    )


def _row(market_id, outcome_name):
    return {"market_id": market_id, "outcome_name": outcome_name}


EXACT = "Germany vs. Greece - Exact Score"
RESULT = "Germany vs. Greece"


def _names(rows):
    return [r["outcome_name"] for r in rows]


# ── The ship ────────────────────────────────────────────────────────────────


def test_two_legs_of_a_seventeen_leg_field_are_withheld():
    """The measured specimen: 2 of 17 exact-score rungs leave the payload."""
    home = [_row(61032702, "Germany 3 - 2 Greece"), _row(61032702, "Germany 2 - 1 Greece")]
    markets = {61032702: _market(61032702, EXACT, declared=17, event_title=EXACT)}

    home_out, away_out = _withhold_partial_field_futures(home, [], markets)

    assert home_out == []
    assert away_out == []


def test_one_leg_of_a_three_way_result_is_withheld():
    """`Germany 79%` with no Draw and no Greece is 1 of the venue's 3 legs."""
    home = [_row(61032733, "Germany")]
    markets = {61032733: _market(61032733, RESULT, declared=3, event_title=RESULT)}

    home_out, _ = _withhold_partial_field_futures(home, [], markets)

    assert home_out == []


def test_sixteen_of_seventeen_is_still_short():
    """The missing rung is `Any Other Score`, which outranks most shown rungs.

    Measured on `/events/15313074` the same hour: the 16 rungs served sum to
    ~0.88, so the absent leg is worth ~12% and would rank at or near the top of
    the ladder. The rule is the first door's rule — short is short — and the
    two doors may not drift into two thresholds.
    """
    home = [_row(7, f"A {i} - 0 B") for i in range(16)]
    markets = {7: _market(7, EXACT, declared=17, event_title=EXACT)}

    home_out, _ = _withhold_partial_field_futures(home, [], markets)

    assert home_out == []


def test_a_short_field_is_removed_from_BOTH_sides():
    """Withholding half a short field is not withholding it.

    A 3-way result missing its Draw leg still puts one leg on each list. A
    version that filters only `home_futures` leaves Greece on the page under a
    heading that still claims to be the whole question — and every ship test
    above passes, because none of them has an away-side row. Found by mutation,
    not by reading.
    """
    home = [_row(9, "Germany")]
    away = [_row(9, "Greece")]
    markets = {9: _market(9, RESULT, declared=3, event_title=RESULT)}

    home_out, away_out = _withhold_partial_field_futures(home, away, markets)

    assert home_out == []
    assert away_out == []


def test_short_field_leaves_the_other_markets_on_the_page():
    """Withholding is per market — the rest of Bigger Picture is untouched."""
    home = [
        _row(61032702, "Germany 3 - 2 Greece"),
        _row(55674162, "Germany"),  # 2028 UEFA Euros Champion — a season future
        _row(61040105, "Over"),  # O/U 11.5 Total Corners
    ]
    markets = {
        61032702: _market(61032702, EXACT, declared=17, event_title=EXACT),
        55674162: _market(55674162, "2028 UEFA Euros Champion", declared=24),
        61040105: _market(61040105, "Germany vs. Greece: O/U 11.5 Total Corners"),
    }

    home_out, _ = _withhold_partial_field_futures(home, [], markets)

    assert _names(home_out) == ["Germany", "Over"]


# ── The controls: rows that MUST survive ────────────────────────────────────


def test_three_way_result_split_across_sides_is_complete():
    """🔴 THE OVER-REACH THIS GUARD EXISTS FOR.

    A complete 3-leg result puts Germany on the home list and Greece on the
    away list. Counted per list it reads 1-of-3 on each side and BOTH vanish —
    the guard would delete exactly the complete fields it was written to
    protect. Counted across both lists it is 3 of 3 and survives.
    """
    home = [_row(9, "Germany")]
    away = [_row(9, "Greece"), _row(9, "Draw")]
    markets = {9: _market(9, RESULT, declared=3, event_title=RESULT)}

    home_out, away_out = _withhold_partial_field_futures(home, away, markets)

    assert _names(home_out) == ["Germany"]
    assert _names(away_out) == ["Greece", "Draw"]


def test_market_count_that_counts_parent_siblings_is_never_judged():
    """The sibling-count trap: `event_title != name`, so the predicate refuses.

    A game's moneyline carries its parent venue event's `market_count` (40-odd
    siblings) and stores two outcomes. Judged naively it is 2 of 40 and every
    ordinary card on the site disappears.
    """
    home = [_row(11, "Germany"), _row(11, "Greece")]
    markets = {
        11: _market(
            11,
            "Germany vs. Greece: Moneyline",
            declared=40,
            event_title="Germany vs. Greece",  # the PARENT's title, not this row's
        )
    }

    home_out, _ = _withhold_partial_field_futures(home, [], markets)

    assert _names(home_out) == ["Germany", "Greece"]


def test_non_exclusive_market_is_never_judged():
    """Only a field the venue itself calls a partition can be short."""
    home = [_row(12, "Over")]
    markets = {12: _market(12, "Total Corners", declared=23, event_title="Total Corners", mex=False)}

    home_out, _ = _withhold_partial_field_futures(home, [], markets)

    assert _names(home_out) == ["Over"]


def test_market_with_no_declared_count_is_never_judged():
    """No `market_count` means no claim about the venue's field."""
    home = [_row(13, "Over"), _row(13, "Under")]
    markets = {13: _market(13, "O/U 11.5 Total Corners", event_title="O/U 11.5 Total Corners")}

    home_out, _ = _withhold_partial_field_futures(home, [], markets)

    assert _names(home_out) == ["Over", "Under"]


def test_complete_field_survives():
    """3 legs declared, 3 rendered — the card accounts for the whole question."""
    home = [_row(14, "Germany"), _row(14, "Greece"), _row(14, "Draw")]
    markets = {14: _market(14, RESULT, declared=3, event_title=RESULT)}

    home_out, _ = _withhold_partial_field_futures(home, [], markets)

    assert len(home_out) == 3


def test_more_rendered_than_declared_survives():
    """A venue count that undercounts our rows is not evidence of a short field."""
    home = [_row(15, "A"), _row(15, "B"), _row(15, "C")]
    markets = {15: _market(15, RESULT, declared=2, event_title=RESULT)}

    home_out, _ = _withhold_partial_field_futures(home, [], markets)

    assert len(home_out) == 3


def test_row_without_a_market_id_is_passed_through():
    """Unattributable rows cannot be proved short, so they stay."""
    home = [{"outcome_name": "Germany"}, _row(61032702, "Germany 3 - 2 Greece")]
    markets = {61032702: _market(61032702, EXACT, declared=17, event_title=EXACT)}

    home_out, _ = _withhold_partial_field_futures(home, [], markets)

    assert _names(home_out) == ["Germany"]


def test_market_missing_from_the_map_is_passed_through():
    """A row whose market the builder did not collect is never judged."""
    home = [_row(99, "Germany")]

    home_out, _ = _withhold_partial_field_futures(home, [], {})

    assert _names(home_out) == ["Germany"]


def test_empty_payload_is_returned_unchanged():
    assert _withhold_partial_field_futures([], [], {}) == ([], [])


def test_nothing_short_returns_the_inputs_untouched():
    """The no-op path must not reorder or copy-mangle the lists."""
    home = [_row(14, "Germany"), _row(14, "Greece"), _row(14, "Draw")]
    away = [_row(55674162, "Greece")]
    markets = {
        14: _market(14, RESULT, declared=3, event_title=RESULT),
        55674162: _market(55674162, "2030 FIFA World Cup Champion", declared=48),
    }

    home_out, away_out = _withhold_partial_field_futures(home, away, markets)

    assert home_out is home
    assert away_out is away


# ── CERT-3099: the merges re-attribute legs, so the count precedes them ─────


def test_split_source_complete_field_survives_the_dedup_reattribution():
    """🔴 THE BLOCK. Two COMPLETE three-leg fields, erased entirely.

    `dedup_by_merge_group` keeps one winner per `(merge_group, outcome_name)`,
    and the winner carries its OWN `market_id`. A field both sources serve has
    its legs re-attributed: Germany's winner comes from market A, Greece's and
    Draw's from market B. Counted on the POST-merge rows that reads 1-of-3 and
    2-of-3 and every row goes — reproduced by the grader as
    `after_dedup=[('Germany',1),('Greece',2),('Draw',2)]` → `after_filter=[]`.

    Counted on `pre_merge_rows`, where each market still owns its own three
    legs, both are complete and nothing is withheld.
    """
    pre_merge = (
        [_row(101, "Germany"), _row(101, "Greece"), _row(101, "Draw")]
        + [_row(102, "Germany"), _row(102, "Greece"), _row(102, "Draw")]
    )
    # what the merges leave behind: one row per outcome, attributed by winner
    home = [_row(101, "Germany")]
    away = [_row(102, "Greece"), _row(102, "Draw")]
    markets = {
        101: _market(101, RESULT, declared=3, event_title=RESULT),
        102: _market(102, RESULT, declared=3, event_title=RESULT),
    }

    home_out, away_out = _withhold_partial_field_futures(
        home, away, markets, pre_merge_rows=pre_merge
    )

    assert _names(home_out) == ["Germany"]
    assert _names(away_out) == ["Greece", "Draw"]


def test_a_merged_row_survives_when_any_market_behind_it_is_complete():
    """The partial-source / complete-sibling control.

    A SHORT market's row can win the merge against a COMPLETE sibling's row for
    the same outcome. Keyed on the winner's `market_id` alone, that row is
    removed and the complete field is served 2-of-3 — the filter would have
    turned a whole field into a fragment, which is the defect it exists to
    prevent. `contributor_market_ids` keeps the complete market visible on the
    merged row, and a row goes only when EVERY market behind it is short.
    """
    pre_merge = [
        _row(201, "Germany"),  # market 201: short, 1 of 3
        _row(202, "Germany"),
        _row(202, "Greece"),
        _row(202, "Draw"),  # market 202: complete, 3 of 3
    ]
    winner = _row(201, "Germany")
    winner["contributor_market_ids"] = [201, 202]
    home = [winner, _row(202, "Greece"), _row(202, "Draw")]
    markets = {
        201: _market(201, RESULT, declared=3, event_title=RESULT),
        202: _market(202, RESULT, declared=3, event_title=RESULT),
    }

    home_out, _ = _withhold_partial_field_futures(
        home, [], markets, pre_merge_rows=pre_merge
    )

    assert _names(home_out) == ["Germany", "Greece", "Draw"]


def test_a_merged_row_goes_when_every_market_behind_it_is_short():
    """The other direction: two short markets merged is still short."""
    pre_merge = [_row(301, "Germany"), _row(302, "Germany")]
    winner = _row(301, "Germany")
    winner["contributor_market_ids"] = [301, 302]
    markets = {
        301: _market(301, RESULT, declared=3, event_title=RESULT),
        302: _market(302, RESULT, declared=3, event_title=RESULT),
    }

    home_out, _ = _withhold_partial_field_futures(
        [winner], [], markets, pre_merge_rows=pre_merge
    )

    assert home_out == []


def test_the_named_two_of_seventeen_still_goes_after_the_repair():
    """The BLOCK required this be retained: the original ship still ships."""
    pre_merge = [
        _row(61032702, "Germany 3 - 2 Greece"),
        _row(61032702, "Germany 2 - 1 Greece"),
    ]
    markets = {61032702: _market(61032702, EXACT, declared=17, event_title=EXACT)}

    home_out, _ = _withhold_partial_field_futures(
        list(pre_merge), [], markets, pre_merge_rows=pre_merge
    )

    assert home_out == []


def test_dedup_records_the_markets_behind_its_winner():
    """The provenance the filter depends on is actually written by the merge."""
    from app.utils.related_futures import dedup_by_merge_group

    rows = [
        {"market_id": 401, "merge_group": "pennant", "outcome_name": "Germany",
         "source": "kalshi", "bookmaker_count": 3, "last_updated": None},
        {"market_id": 402, "merge_group": "pennant", "outcome_name": "Germany",
         "source": "polymarket", "bookmaker_count": 1, "last_updated": None},
    ]

    out = dedup_by_merge_group(rows)

    assert len(out) == 1
    assert out[0]["contributor_market_ids"] == [401, 402]


# ── The predicate is shared with the first door, not restated ───────────────


def test_both_doors_use_one_predicate():
    """If these two ever disagree, a market shows on one surface and not the other.

    Not a style assertion: the two consumers must import the SAME
    `venue_leg_count`, which is why it was hoisted into `utils.market_shape`.
    """
    import inspect

    from app.routes.events import _withhold_partial_field_markets

    for fn in (_withhold_partial_field_markets, _withhold_partial_field_futures):
        assert "from app.utils.market_shape import venue_leg_count" in inspect.getsource(fn)


@pytest.mark.parametrize(
    "declared,rendered,expect_withheld",
    [
        (17, 2, True),
        (17, 16, True),
        (17, 17, False),
        (9, 5, True),
        (3, 1, True),
        (3, 3, False),
    ],
)
def test_the_boundary_is_strictly_less_than(declared, rendered, expect_withheld):
    home = [_row(21, f"leg {i}") for i in range(rendered)]
    markets = {21: _market(21, RESULT, declared=declared, event_title=RESULT)}

    home_out, _ = _withhold_partial_field_futures(home, [], markets)

    assert (home_out == []) is expect_withheld
