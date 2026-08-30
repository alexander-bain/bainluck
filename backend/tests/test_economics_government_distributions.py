"""UX-P171 — the economics government section stops claiming markets it drops.

`GET /api/economics` served ``government: {count: 3, markets: []}``. The page
gated the section on ``count`` and rendered from ``markets``, so a reader got a
section header, a pill reading "3 active", and an empty bordered card.

The three markets were not missing. They were live and priced — a nine-rung
"At least $X" federal-spending ladder and two US-trade-deficit bracket
distributions — and ``_market_row()`` refuses anything above five outcomes, so
the producer discarded all three without a word.

``_distribution_row()`` keeps them, and it keeps them in the right SHAPE: a
cumulative threshold ladder stays raw because its rows are independent "at or
above X" probabilities that legitimately sum past 100% (gotcha #17), while a
genuine partition is normalized. Getting that backwards would have swapped one
lie for a subtler one — the spending ladder sums to 571%.

Every fixture row below is the verbatim production outcome set banked before a
line of the fix was written:
``backend/tests/fixtures/uxp171_economics_government.json``.
"""

import json
import pathlib
from types import SimpleNamespace

import pytest

from app.routes.economics import (
    _distribution_row,
    _is_cumulative_ladder,
    _market_row,
)

FIXTURE = (
    pathlib.Path(__file__).parent / "fixtures" / "uxp171_economics_government.json"
)


def _outcome(name: str, prob: float, rank: int = 0):
    return SimpleNamespace(id=rank, name=name, current_probability=prob, rank=rank)


def _market(name: str, outcomes: list, source: str = "kalshi", external_id: str = "kxgovt"):
    return SimpleNamespace(
        id=1, name=name, source=source, external_id=external_id, outcomes=outcomes
    )


@pytest.fixture(scope="module")
def banked():
    return json.loads(FIXTURE.read_text())


# ---------------------------------------------------------------------------
# The banked BEFORE
# ---------------------------------------------------------------------------


class TestTheBankedBeforeIsTheBrokenState:
    def test_the_served_payload_really_was_count_three_zero_rows(self, banked):
        gov = banked["served_before"]["themes"]["government"]
        assert gov["count"] == 3
        assert gov["markets"] == []

    def test_government_was_the_only_section_gated_open_on_nothing(self, banked):
        census = banked["_section_census"]["sections"]
        assert len(census) == 9
        lying = [
            k
            for k, s in census.items()
            if s["gate_count"] > 0 and s["rendered_rows"] == 0
        ]
        assert lying == ["government"]

    def test_the_three_were_dropped_by_width_not_by_absence(self, banked):
        pop = banked["_government_population"]
        # Five markets classify as government; two lead at 99.85% and 100% and
        # are dropped by should_exclude_from_featured before the section is
        # built. Three survive — which is exactly the `count: 3` the badge
        # printed — and NONE of them fits a Market row.
        assert pop["classified_government"] == 5
        assert pop["excluded_probability_extreme"] == 2
        assert pop["surviving_government"] == 3
        assert pop["renderable_as_market_row"] == 0
        assert len(pop["market_ids"]) == 3
        assert pop["surviving_government"] == banked["served_before"]["themes"]["government"]["count"]


# ---------------------------------------------------------------------------
# The predicate
# ---------------------------------------------------------------------------


class TestCumulativeLadderDetection:
    @pytest.mark.parametrize(
        "prefix",
        [
            "Above ",
            "At least ",
            "More than ",
            "Over ",
            "Greater than ",
            "Below ",
            "Before ",
        ],
    )
    def test_every_threshold_wording_is_recognised(self, prefix):
        m = _market(
            "Spending",
            [_outcome(f"{prefix}${n}B", 0.5, rank=i) for i, n in enumerate((1, 50, 100))],
        )
        assert _is_cumulative_ladder(m) is True

    def test_wording_is_case_insensitive(self):
        m = _market(
            "Spending",
            [_outcome("AT LEAST $1B", 0.9, 1), _outcome("at least $2B", 0.4, 2)],
        )
        assert _is_cumulative_ladder(m) is True

    def test_a_bracket_partition_is_not_a_ladder(self):
        m = _market(
            "Deficit",
            [_outcome("700-800B", 0.3, 1), _outcome("800-900B", 0.5, 2)],
        )
        assert _is_cumulative_ladder(m) is False

    def test_a_partly_threshold_market_is_not_a_ladder(self):
        """All rows or none — a mixed market must not be read as cumulative."""
        m = _market(
            "Mixed",
            [
                _outcome("At least $1B", 0.9, 1),
                _outcome("At least $2B", 0.5, 2),
                _outcome("Something else entirely", 0.2, 3),
            ],
        )
        assert _is_cumulative_ladder(m) is False

    def test_a_single_threshold_outcome_is_not_a_ladder(self):
        m = _market("One rung", [_outcome("At least $1B", 0.9, 1)])
        assert _is_cumulative_ladder(m) is False


# ---------------------------------------------------------------------------
# The producer
# ---------------------------------------------------------------------------


class TestDistributionRow:
    def test_it_declines_what_market_row_already_handles(self):
        """No market may be served twice — narrow ones stay Market rows."""
        m = _market("Narrow", [_outcome("Yes", 0.4, 1), _outcome("No", 0.6, 2)])
        assert _market_row(m) is not None
        assert _distribution_row(m) is None

    def test_it_takes_over_exactly_where_market_row_gives_up(self):
        six = _market("Six", [_outcome(f"b{i}", 0.1, i) for i in range(6)])
        five = _market("Five", [_outcome(f"b{i}", 0.1, i) for i in range(5)])
        assert _market_row(five) is not None and _distribution_row(five) is None
        assert _market_row(six) is None and _distribution_row(six) is not None

    def test_an_unpriced_market_is_still_declined(self):
        """A card of zeroes is not content — do not trade one empty for another."""
        m = _market("Dark", [_outcome(f"b{i}", 0.0, i) for i in range(8)])
        assert _distribution_row(m) is None

    def test_a_ladder_is_served_raw(self):
        m = _market(
            "Spending",
            [
                _outcome("At least $1B", 0.97, 1),
                _outcome("At least $500B", 0.34, 2),
                _outcome("At least $1T", 0.075, 3),
                _outcome("At least $2T", 0.05, 4),
                _outcome("At least $3T", 0.04, 5),
                _outcome("At least $4T", 0.03, 6),
            ],
        )
        row = _distribution_row(m)
        assert row["kind"] == "ladder"
        # 97 + 34 + 7.5 + 5 + 4 + 3 = 150.5, and it must STAY 150.5.
        assert sum(r[0] for r in row["rows"]) == pytest.approx(150.5, abs=0.2)
        assert row["rows"][0] == [97.0, "At least $1B"]

    def test_a_partition_is_normalized(self):
        m = _market(
            "Deficit",
            [_outcome(f"bucket {i}", 0.4, i) for i in range(1, 7)],
        )
        row = _distribution_row(m)
        assert row["kind"] == "brackets"
        # Raw sum 240% — a real partition, so it gets scaled back.
        assert sum(r[0] for r in row["rows"]) == pytest.approx(100.0, abs=1.0)

    def test_the_row_carries_what_the_card_needs(self):
        m = _market(
            "Spending",
            [_outcome(f"At least ${i}B", 0.5, i) for i in range(1, 8)],
            source="polymarket",
        )
        row = _distribution_row(m)
        assert set(row) == {"q", "kind", "rows", "src", "market_id"}
        assert row["q"] == "Spending"
        assert row["src"] == "polymarket"
        assert row["market_id"] == 1


# ---------------------------------------------------------------------------
# Against the real production markets
# ---------------------------------------------------------------------------


class TestTheThreeRealGovernmentMarkets:
    @staticmethod
    def _rebuild(md):
        m = _market(
            md["name"],
            [_outcome(o["name"], o["current_probability"], o["rank"]) for o in md["outcomes"]],
            source="polymarket" if md["external_id"].isdigit() else "kalshi",
            external_id=md["external_id"],
        )
        m.id = md["id"]
        return m

    def test_all_three_were_refused_by_market_row(self, banked):
        raw = banked["_raw_markets"]
        assert len(raw) == 3
        for md in raw:
            m = self._rebuild(md)
            assert _market_row(m) is None, f"{md['name']} was renderable all along"
            assert len(md["outcomes"]) > 5

    def test_the_spending_ladder_keeps_its_571_percent(self, banked):
        served = banked["served_after_government"]["distributions"]
        ladder = next(d for d in served if d["q"] == "Government spending increase in 2026")
        assert ladder["kind"] == "ladder"
        assert len(ladder["rows"]) == 9
        assert sum(r[0] for r in ladder["rows"]) == pytest.approx(571.3, abs=0.5)

    def test_the_ladder_descends_so_the_thresholds_read_in_order(self, banked):
        served = banked["served_after_government"]["distributions"]
        ladder = next(d for d in served if d["q"] == "Government spending increase in 2026")
        probs = [r[0] for r in ladder["rows"]]
        assert probs == sorted(probs, reverse=True)
        assert ladder["rows"][0][1] == "At least $1 billion"
        assert ladder["rows"][-1][1] == "At least $1 trillion"

    def test_the_deficit_partition_is_the_only_one_normalized(self, banked):
        served = banked["served_after_government"]["distributions"]
        partitions = [d for d in served if d["kind"] == "brackets"]
        assert [p["q"] for p in partitions] == ["US Trade Deficit in 2026?"]
        total = sum(r[0] for r in partitions[0]["rows"])
        assert 99.0 <= total <= 101.5, f"summed to {total}"

    def test_the_temporal_ladder_is_also_left_raw(self, banked):
        """"Before Jan 1, 2028" nests exactly like "At least $400 billion"."""
        served = banked["served_after_government"]["distributions"]
        deadline = next(d for d in served if d["q"] == "When will the debt limit be increased?")
        assert deadline["kind"] == "ladder"
        assert sum(r[0] for r in deadline["rows"]) == pytest.approx(264.5, abs=0.5)
        assert deadline["rows"][0][1] == "Before Jan 1, 2028"

    def test_rebuilding_from_the_raw_outcomes_reproduces_what_was_banked(self, banked):
        """The banked AFTER is a real producer output, not a hand-drawn one.

        This is the arm that fails if someone changes the ladder/partition
        rules and only updates the fixture.
        """
        served = banked["served_after_government"]["distributions"]
        rebuilt = [_distribution_row(self._rebuild(md)) for md in banked["_raw_markets"]]
        assert rebuilt == served

