"""#10388 — an /economics raw ladder breaks a price tie by threshold.

Seen on production 2026-10-03: the "30-year mortgage rate at the end of
2026" ladder (Kalshi 63115873) served its last two rungs out of order —
``Above 9.00%`` before ``Above 8.75%``, both at 1.5%.

``_distribution_row`` orders ladder rungs by the stored ``rank``, a
PROBABILITY rank assigned at ingestion by a stable sort on price. On a tie
the ranks follow venue ingestion order, which has nothing to do with
threshold order. Where prices are strict, rank order already IS threshold
order, so only contiguous equal-price runs are reordered.

The reorder is conservative: a tied run is touched only when every label
is a threshold the grammar reads COMPLETELY and all share one shape. The
retained ``parse_threshold`` reads a partial span — "At least $750
billion" parses 750, "At least $1 trillion" parses 1 — so a guard that
only refused parsed-value collisions would still sort the trillion before
the 750 billion. Spelled magnitudes, dates, mixed directions and trailing
words keep the order they have always served.
"""

from types import SimpleNamespace

from app.routes.economics import _distribution_row


def _outcome(name: str, prob: float, rank: int):
    return SimpleNamespace(
        id=rank,
        name=name,
        current_probability=prob,
        rank=rank,
        external_id=f"kx-{rank}-{name}",
    )


def _market(name: str, outcomes: list):
    return SimpleNamespace(
        id=63115873,
        name=name,
        source="kalshi",
        external_id="KXMORTGAGE-26DEC31",
        outcomes=outcomes,
    )


def _labels(row: dict) -> list[str]:
    return [label for _, label in row["rows"]]


def _served(outcomes: list, name: str = "Ladder", min_outcomes: int = 3) -> dict:
    row = _distribution_row(_market(name, outcomes), min_outcomes=min_outcomes)
    assert row is not None
    assert row["kind"] == "ladder"
    return row


class TestTiedRungsServeInThresholdOrder:
    def test_the_mortgage_tie_serves_875_before_900(self):
        """The production shape: the tied pair carries ranks in reverse
        threshold order (venue ingestion order on a tie)."""
        row = _served(
            [
                _outcome("Above 8.50%", 0.05, 1),
                _outcome("Above 9.00%", 0.015, 2),
                _outcome("Above 8.75%", 0.015, 3),
            ],
            name="30-year mortgage rate at the end of 2026",
        )
        assert row["rows"] == [
            [5.0, "Above 8.50%"],
            [1.5, "Above 8.75%"],
            [1.5, "Above 9.00%"],
        ]

    def test_threshold_order_holds_on_the_default_width_path(self):
        """``gov_distributions`` calls with the default floor of 6; a
        supported suffix ladder ($…T) breaks its tie there too."""
        row = _served(
            [
                _outcome("Above $6.0T", 0.90, 1),
                _outcome("Above $6.5T", 0.70, 2),
                _outcome("Above $7.0T", 0.40, 3),
                _outcome("Above $8.0T", 0.015, 4),
                _outcome("Above $7.5T", 0.015, 5),
                _outcome("Above $9.0T", 0.001, 6),
            ],
            name="Federal spending ladder",
            min_outcomes=6,
        )
        assert _labels(row) == [
            "Above $6.0T",
            "Above $6.5T",
            "Above $7.0T",
            "Above $7.5T",
            "Above $8.0T",
            "Above $9.0T",
        ]

    def test_a_below_ladder_tie_follows_its_own_descending_order(self):
        """A ``below`` ladder lists its loosest bound — the HIGHEST
        threshold — first, so its tie breaks descending and the tied rungs
        read in the same direction as their neighbours."""
        row = _served(
            [
                _outcome("Below 5.00%", 0.60, 1),
                _outcome("Below 3.00%", 0.30, 2),
                _outcome("Below 4.00%", 0.30, 3),
            ],
        )
        assert _labels(row) == ["Below 5.00%", "Below 4.00%", "Below 3.00%"]

    def test_reordering_keeps_each_label_with_its_own_probability(self):
        before = {
            "Above 8.50%": 0.05,
            "Above 9.00%": 0.015,
            "Above 8.75%": 0.015,
            "Above 9.25%": 0.004,
        }
        row = _served(
            [_outcome(n, p, i + 1) for i, (n, p) in enumerate(before.items())],
        )
        assert {label: prob for prob, label in row["rows"]} == {
            n: round(p * 100, 1) for n, p in before.items()
        }

    def test_a_strictly_priced_ladder_keeps_rank_order(self):
        """Only ties are reordered: a ladder whose prices are strict serves
        the rows it served before, whatever its direction."""
        row = _served(
            [
                _outcome("Below 5.00%", 0.60, 1),
                _outcome("Below 4.00%", 0.30, 2),
                _outcome("Below 3.00%", 0.10, 3),
            ],
        )
        assert _labels(row) == ["Below 5.00%", "Below 4.00%", "Below 3.00%"]


class TestTiesTheGrammarCannotReadCompletelyKeepRankOrder:
    def test_spelled_magnitudes_with_distinct_parsed_values_keep_order(self):
        """The root counterexample. "At least $750 billion" parses 750 and
        "At least $1 trillion" parses 1 — distinct values, no collision — so
        a collision-only guard would sort the trillion first. The stored
        order is correct and must survive."""
        row = _served(
            [
                _outcome("At least $50 billion", 0.968, 1),
                _outcome("At least $750 billion", 0.015, 2),
                _outcome("At least $1 trillion", 0.015, 3),
            ],
            name="Government spending increase in 2026",
        )
        assert _labels(row) == [
            "At least $50 billion",
            "At least $750 billion",
            "At least $1 trillion",
        ]

    def test_spelled_magnitudes_with_a_parsed_collision_keep_order(self):
        """ "At least $1 billion" and "At least $1 trillion" both parse 1.
        Whatever order the venue stored, the run is left alone."""
        row = _served(
            [
                _outcome("At least $50 billion", 0.968, 1),
                _outcome("At least $1 trillion", 0.015, 2),
                _outcome("At least $750 billion", 0.015, 3),
                _outcome("At least $1 billion", 0.015, 4),
            ],
            name="Government spending increase in 2026",
        )
        assert _labels(row) == [
            "At least $50 billion",
            "At least $1 trillion",
            "At least $750 billion",
            "At least $1 billion",
        ]

    def test_one_unsupported_label_leaves_the_whole_tied_run_alone(self):
        row = _served(
            [
                _outcome("Above 8.50%", 0.05, 1),
                _outcome("Above 9.00% or higher", 0.015, 2),
                _outcome("Above 8.75%", 0.015, 3),
            ],
        )
        assert _labels(row) == ["Above 8.50%", "Above 9.00% or higher", "Above 8.75%"]

    def test_a_tied_date_run_is_untouched(self):
        """ "Before Mar 1, 2028" is not a threshold label; a tie across
        date rungs keeps the rank order it has always served."""
        row = _served(
            [
                _outcome("Before Jan 1, 2027", 0.50, 1),
                _outcome("Before Jun 1, 2028", 0.10, 2),
                _outcome("Before Mar 1, 2028", 0.10, 3),
            ],
            name="Launch date ladder",
        )
        assert _labels(row) == [
            "Before Jan 1, 2027",
            "Before Jun 1, 2028",
            "Before Mar 1, 2028",
        ]

    def test_a_tied_mixed_direction_run_is_untouched(self):
        row = _served(
            [
                _outcome("Above 7%", 0.50, 1),
                _outcome("Above 5%", 0.30, 2),
                _outcome("Below 3%", 0.30, 3),
            ],
            name="Mixed ladder",
        )
        assert _labels(row) == ["Above 7%", "Above 5%", "Below 3%"]

    def test_a_tied_run_mixing_units_is_untouched(self):
        row = _served(
            [
                _outcome("Above 9%", 0.50, 1),
                _outcome("Above $8T", 0.30, 2),
                _outcome("Above 5%", 0.30, 3),
            ],
        )
        assert _labels(row) == ["Above 9%", "Above $8T", "Above 5%"]

    def test_bracket_partitions_keep_rank_order(self):
        """The fix is ladder-scoped: partitions still serve rank order."""
        row = _distribution_row(
            _market(
                "Deficit brackets",
                [
                    _outcome("800-900B", 0.30, 1),
                    _outcome("700-800B", 0.30, 2),
                    _outcome("900B+", 0.10, 3),
                ],
            ),
            min_outcomes=3,
        )
        assert row["kind"] == "brackets"
        assert _labels(row) == ["800-900B", "700-800B", "900B+"]
