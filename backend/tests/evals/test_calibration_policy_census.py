from unittest.mock import AsyncMock, MagicMock

import pytest

from scripts.evals.calibration_policy_census import (
    build_report, classify_size_two, datagolf_counterfactual, load_from_session,
    sports_counterfactual, tail_census, volume_census,
)


def row(i, q, p, won, source="kalshi", **extra):
    return {"outcome_id": i, "market_id": i, "question_id": q,
            "probability": p, "is_winner": won, "source": source,
            "market_type": extra.pop("market_type", "claim"), **extra}


def test_bid_with_zero_volume_is_visible_contradiction():
    report = volume_census([
        {"outcome_id": 1, "question_id": "q", "source": "kalshi", "volume": 0,
         "has_bid": True, "has_trade": False, "snapshot_evidence_available": True,
         "canonical_included": False},
    ])
    assert report["bid_with_zero_volume_outcomes"] == 1
    assert report["cells"][0]["canonical_included"] is False
    assert "may overlap" in report["universe"]


def test_sports_weighting_can_improve_or_worsen():
    good_double = [
        row(1, "m1", .9, True, kind="moneyline", positive_leg=True),
        row(2, "m1", .1, False, kind="moneyline", positive_leg=False),
        row(3, "s1", .9, False, kind="spread", positive_leg=True),
    ]
    bad_double = [
        row(1, "m1", .9, False, kind="moneyline", positive_leg=True),
        row(2, "m1", .1, True, kind="moneyline", positive_leg=False),
        row(3, "s1", .9, True, kind="spread", positive_leg=True),
    ]
    a, b = sports_counterfactual(good_double), sports_counterfactual(bad_double)
    assert a["question_weighted"]["brier"] > a["current"]["brier"]
    assert b["question_weighted"]["brier"] < b["current"]["brier"]
    assert "one declared positive leg" in a["estimands"]["question"]


def test_datagolf_inclusion_can_improve_or_worsen():
    good_dg = [row(1, "q1", .7, True), row(2, "d1", .9, True, "datagolf")]
    bad_dg = [row(1, "q1", .7, True), row(2, "d1", .9, False, "datagolf")]
    a, b = datagolf_counterfactual(good_dg), datagolf_counterfactual(bad_dg)
    assert a["combined_current"]["brier"] < a["combined_without_datagolf"]["brier"]
    assert b["combined_current"]["brier"] > b["combined_without_datagolf"]["brier"]
    assert a["label"].startswith("DataGolf model forecast")


def test_extremes_are_split_by_evidence_not_assumed():
    canonical = [row(1, "base", .5, True)]
    tails = [
        row(2, "real", .99, True, has_trade=True, canonical_included=False,
            resolution_source="api_settlement"),
        row(3, "placeholder", .99, False, has_trade=False, has_bid=False,
            canonical_included=False, resolution_source="api_settlement"),
    ]
    report = tail_census(canonical, tails)
    assert {c["trading_evidence"] for c in report["cells"]} == {"traded", "none"}
    assert report["include_candidates"]["outcomes"] == 3
    assert sum(abs(c["delta"]) for c in report["bucket_deltas"]) == 2


def _family(relation="competitors", explicit=True, unrelated=False):
    rows = []
    for market, name, won in ((1, "Alice", True), (2, "Bob", False)):
        common = {"family_key": "g:race", "source": "polymarket", "market_id": market,
                  "market_name": name, "outcome_relation": relation,
                  "exhaustive": True if explicit else None,
                  "expected_winners": 1 if explicit else None}
        rows.append({**common, "outcome_id": market * 10, "outcome_name": "Yes",
                     "is_winner": won})
        rows.append({**common, "outcome_id": market * 10 + 1, "outcome_name": "No",
                     "is_winner": not won})
    if unrelated:
        rows[2]["outcome_relation"] = "conditional"
        rows[3]["outcome_relation"] = "conditional"
    return rows


def test_size_two_requires_contract_and_positive_leg_projection():
    safe = classify_size_two(_family())
    assert safe["families"][0]["verdict"] == "structurally_safe_candidate"
    assert safe["families"][0]["raw_outcomes"] == 4
    assert safe["families"][0]["positive_legs"] == 2
    unknown = classify_size_two(_family(explicit=False))
    assert unknown["families"][0]["verdict"] == "unknown"
    unsafe = classify_size_two(_family(unrelated=True))
    assert unsafe["families"][0]["verdict"] == "unsafe"


def test_unknown_shape_fails_visible():
    rows = _family(relation="new_relation")
    report = classify_size_two(rows)
    assert report["counts"] == {"unknown": 1}
    assert report["families"][0]["reason"] == "unrecognized_relation"


def test_unknown_resolution_source_fails_visible():
    payload = {"canonical": [row(1, "q", .7, True,
                                  resolution_source="brand_new_writer")],
               "volume_universe": [], "tail_candidates": [], "sports": [], "size_two": []}
    report = build_report(payload)
    assert report["contract"]["contract_ok"] is False
    assert report["contract"]["unknown_resolution_sources"] == ["brand_new_writer"]


def test_report_is_deterministic_and_labeled():
    payload = {"canonical": [row(1, "q", .7, True)], "volume_universe": [],
               "tail_candidates": [], "sports": [], "size_two": []}
    assert build_report(payload) == build_report(payload)
    assert build_report(payload)["contract"]["current_population"] == "canonical deduped row identity"


@pytest.mark.asyncio
async def test_session_loader_composes_canonical_population_and_named_universes():
    empty = MagicMock(); empty.all.return_value = []
    session = MagicMock(); session.execute = AsyncMock(side_effect=[empty] * 5)
    payload = await load_from_session(session)
    assert set(payload) == {"canonical", "volume_universe", "tail_candidates", "sports", "size_two"}
    sql = [str(call.args[0]) for call in session.execute.await_args_list]
    assert "FROM deduped d" in sql[0]
    assert "LEFT JOIN canonical_ids" in sql[1]
    assert "FROM normalized n" in sql[2]
    assert "UNION ALL" in sql[3]
    assert sql[4].count("HAVING COUNT(*)=2") == 2
    assert "'event:' || e.family_id" in sql[4]
    # Canonical eligibility is composed, not copied into the eval.
    assert "field_completeness AS" in sql[0]
    assert "CALIBRATION_TRUTH_ELIGIBLE" not in sql[0]
