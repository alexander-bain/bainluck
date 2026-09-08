"""CAL-P1054 (D90 option B): the gate reads the artifacts' own rung disclosure.

Rule 3 refuses a category that loses more than ``CATEGORY_DROP_TOLERANCE`` of
its outcomes without a ``population_version`` bump. That is the right alarm and
its threshold does not move here.

What it could not see is a rung change that the build DISCLOSES. CAL-P1002F
(#1978, D66) added ``('kalshi','entertainment')`` to ``SUM_ARM_ONLY_EXCLUDED_CELLS``
and reached the dyno 95 seconds AFTER the last successful publish, so from then
on every hourly candidate was a post-ruling build measured against a pre-ruling
baseline. entertainment read 12,395 -> 7,060 (-43%), Rule 3 refused, and the
public page served a three-day-old artifact as if it were current — while BOTH
artifacts stated the difference in a key they already publish
(``esports_multi_bundle_filter.excluded_cells``, precompute_calibration.py:6518).

The bump branch already holds the principle: "a change in WHICH ROWS QUALIFY
reshapes individual categories by definition", so it RECORDS the movement rather
than vetoing it. It just could only reach that conclusion from a version string.
A rung that names the cell it started deleting is the same fact stated by the
build itself.

So these tests pin BOTH directions. The excuse applies only where the candidate
newly names that category as excluded by a named rung; every other collapse
refuses exactly as before. The negative controls are the point of the file — an
alarm that can be talked out of firing by any disclosure at all would be worse
than the stale page it exists to prevent.
"""

from __future__ import annotations

import json

import pytest

from app.utils.calibration_publish_gate import (
    CATEGORY_DROP_TOLERANCE,
    census,
    evaluate_publish,
    gate_ledger_record,
)

from tests.test_calibration_publish_gate_297 import payload

#: Big enough to clear CATEGORY_MIN_N, and a 43% fall — the real shape.
_HEALTHY = {
    "politics": 400_000,
    "sports": 350_000,
    "entertainment": 12_395,
    "economics": 200_000,
}
_COLLAPSED = {
    "politics": 400_000,
    "sports": 350_000,
    "entertainment": 7_060,
    "economics": 200_000,
}


def _with_cells(
    p: dict, cells: list[list[str]], *, key: str = "excluded_cells"
) -> dict:
    """Attach a rung disclosure of the shape the build actually emits."""
    p.setdefault("esports_multi_bundle_filter", {})[key] = cells
    return p


def _observation(verdict, code: str):
    for o in verdict.observations:
        if o["code"] == code:
            return o
    return None


# ---------------------------------------------------------------------------
# The case this exists for
# ---------------------------------------------------------------------------


def test_a_collapse_the_candidate_discloses_is_recorded_not_refused():
    """The D66 shape: -43% on entertainment, and the candidate says why."""
    published = _with_cells(
        payload(categories=_HEALTHY),
        [["kalshi", "crypto"], ["kalshi", "economics"]],
    )
    candidate = _with_cells(
        payload(categories=_COLLAPSED),
        [["kalshi", "crypto"], ["kalshi", "economics"], ["kalshi", "entertainment"]],
    )

    verdict = evaluate_publish(candidate, published)

    assert verdict.ok
    assert "category_collapse" not in verdict.codes
    obs = _observation(verdict, "category_collapse_disclosed_exclusion")
    assert obs is not None, "an admitted collapse that records nothing is the hazard"
    assert obs["category"] == "entertainment"
    assert obs["previous"] == 12_395 and obs["candidate"] == 7_060
    # The rung is NAMED. "Something excluded it" is not an explanation.
    assert obs["disclosed_by"] == [
        {
            "section": "esports_multi_bundle_filter",
            "source": "kalshi",
            "category": "entertainment",
        }
    ]


def test_the_admitted_collapse_admits_it_cannot_check_the_magnitude():
    """No rung publishes a per-cell count, so the size is explained in kind only.

    An unchecked read must never pass as a clean one — the flag is the whole
    difference between the two.
    """
    published = _with_cells(payload(categories=_HEALTHY), [["kalshi", "crypto"]])
    candidate = _with_cells(
        payload(categories=_COLLAPSED),
        [["kalshi", "crypto"], ["kalshi", "entertainment"]],
    )

    obs = _observation(
        evaluate_publish(candidate, published), "category_collapse_disclosed_exclusion"
    )

    assert obs is not None
    assert obs["magnitude_uncheckable"] is True


def test_a_key_the_baseline_predates_entirely_still_reads_as_new():
    """`sum_arm_only_cells` is D66's own additive key: absent on the baseline.

    An absent key is an empty disclosure, not an unknown one — a rung disclosed
    for the first time is precisely the change this rule exists to see.
    """
    published = payload(categories=_HEALTHY)
    published["esports_multi_bundle_filter"] = {"applies_to": "esports"}
    candidate = _with_cells(
        payload(categories=_COLLAPSED),
        [["kalshi", "entertainment"]],
        key="sum_arm_only_cells",
    )

    verdict = evaluate_publish(candidate, published)

    assert verdict.ok
    assert _observation(verdict, "category_collapse_disclosed_exclusion") is not None


def test_the_mapping_shaped_disclosure_is_read_too():
    """`excluded_by_cell` is a dict keyed 'source/category' or a bare category."""
    published = payload(categories=_HEALTHY)
    published["nonexclusive_bundle_filter"] = {
        "excluded_by_cell": {"kalshi/crypto": 10}
    }
    candidate = payload(categories=_COLLAPSED)
    candidate["nonexclusive_bundle_filter"] = {
        "excluded_by_cell": {"kalshi/crypto": 10, "kalshi/entertainment": 5_335}
    }

    verdict = evaluate_publish(candidate, published)

    assert verdict.ok
    obs = _observation(verdict, "category_collapse_disclosed_exclusion")
    assert obs is not None
    assert obs["disclosed_by"][0]["section"] == "nonexclusive_bundle_filter"


def test_a_bare_category_key_carries_no_invented_source():
    """'esports' is a category with no source; the gate must not guess one."""
    reduced = census(
        {"esports_multi_bundle_filter": {"excluded_by_cell": {"esports": 1}}}
    )

    assert reduced["excluded_cells"]["esports_multi_bundle_filter"] == [["", "esports"]]


def test_the_durable_record_says_WHICH_rung_excused_the_category():
    """An excused collapse whose reason is not retained is CAL-P213 again.

    ``observation_codes`` carries only the class name, and the ledger record is
    what a reader has three days later — so the rung, the cell and the
    unchecked-magnitude admission all have to survive into it.
    """
    published = _with_cells(payload(categories=_HEALTHY), [["kalshi", "crypto"]])
    candidate = _with_cells(
        payload(categories=_COLLAPSED),
        [["kalshi", "crypto"], ["kalshi", "entertainment"]],
    )

    record = gate_ledger_record(evaluate_publish(candidate, published))

    assert record["ok"] is True
    assert "category_collapse_disclosed_exclusion" in record["observations"]
    assert record["disclosed_exclusions"] == [
        {
            "category": "entertainment",
            "previous": 12_395,
            "candidate": 7_060,
            "drop_pct": 43.04,
            "disclosed_by": [
                {
                    "section": "esports_multi_bundle_filter",
                    "source": "kalshi",
                    "category": "entertainment",
                }
            ],
            "magnitude_uncheckable": True,
        }
    ]
    assert record["disclosed_exclusions_omitted"] == 0
    # The ledger is serialised; a record that cannot round-trip is not a record.
    json.dumps(record)


def test_a_record_with_nothing_excused_carries_an_empty_list():
    """Absent is not the same as empty, and the reader must not have to guess."""
    record = gate_ledger_record(evaluate_publish(payload(), payload()))

    assert record["disclosed_exclusions"] == []
    assert record["disclosed_exclusions_omitted"] == 0


# ---------------------------------------------------------------------------
# The negative controls — the reason this file is longer than the change
# ---------------------------------------------------------------------------


def test_an_undisclosed_collapse_still_refuses():
    """The alarm's whole job. No rung claims it, so it is still a data loss."""
    published = _with_cells(payload(categories=_HEALTHY), [["kalshi", "crypto"]])
    candidate = _with_cells(payload(categories=_COLLAPSED), [["kalshi", "crypto"]])

    verdict = evaluate_publish(candidate, published)

    assert not verdict.ok
    assert "category_collapse" in verdict.codes
    assert "entertainment" in verdict.summary()


def test_a_disclosure_naming_a_DIFFERENT_category_does_not_excuse_this_one():
    """Any-disclosure-excuses-anything would be worse than the stale page."""
    published = _with_cells(payload(categories=_HEALTHY), [["kalshi", "crypto"]])
    candidate = _with_cells(
        payload(categories=_COLLAPSED),
        [["kalshi", "crypto"], ["kalshi", "weather"]],
    )

    verdict = evaluate_publish(candidate, published)

    assert not verdict.ok
    assert "category_collapse" in verdict.codes


def test_a_cell_excluded_in_BOTH_artifacts_excuses_nothing():
    """The rung did not change, so it cannot explain a change.

    This is the loophole that matters: a rung permanently listing a cell would
    otherwise grant that category a standing exemption from Rule 3 forever.
    """
    cells = [["kalshi", "crypto"], ["kalshi", "entertainment"]]
    published = _with_cells(payload(categories=_HEALTHY), list(cells))
    candidate = _with_cells(payload(categories=_COLLAPSED), list(cells))

    verdict = evaluate_publish(candidate, published)

    assert not verdict.ok
    assert "category_collapse" in verdict.codes


def test_a_rung_being_LOOSENED_does_not_excuse_a_collapse():
    """Dropping a cell from an exclusion list GROWS a category, never shrinks it.

    A candidate that both stops excluding a cell and loses 43% of it is saying
    two contradictory things, and the gate keeps refusing.
    """
    published = _with_cells(
        payload(categories=_HEALTHY),
        [["kalshi", "crypto"], ["kalshi", "entertainment"]],
    )
    candidate = _with_cells(payload(categories=_COLLAPSED), [["kalshi", "crypto"]])

    verdict = evaluate_publish(candidate, published)

    assert not verdict.ok
    assert "category_collapse" in verdict.codes


def test_the_drop_tolerance_itself_is_unmoved():
    """The alarm was right. This ship never widens it."""
    assert CATEGORY_DROP_TOLERANCE == 0.20


def test_a_disclosed_category_below_the_tolerance_needs_no_excuse():
    """A rung change that moves a cell a little publishes with no observation."""
    published = _with_cells(payload(categories=_HEALTHY), [["kalshi", "crypto"]])
    gentle = dict(_HEALTHY, entertainment=12_000)  # -3.2%
    candidate = _with_cells(
        payload(categories=gentle),
        [["kalshi", "crypto"], ["kalshi", "entertainment"]],
    )

    verdict = evaluate_publish(candidate, published)

    assert verdict.ok
    assert _observation(verdict, "category_collapse_disclosed_exclusion") is None


# ---------------------------------------------------------------------------
# The reduction stays tolerant — census must never raise on a bad artifact
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "section",
    [
        {"excluded_cells": "not-a-list"},
        {"excluded_cells": [["only-one"], ["a", "b", "c"], None, 7]},
        {"excluded_cells": [[1, 2]]},
        {"excluded_by_cell": ["not", "a", "mapping"]},
        {"excluded_by_cell": {"": 1}},
    ],
)
def test_a_malformed_disclosure_contributes_nothing_and_never_raises(section):
    reduced = census({"esports_multi_bundle_filter": section})

    assert reduced["excluded_cells"] == {}


def test_a_non_dict_payload_still_reduces():
    assert census("not a payload")["excluded_cells"] == {}
