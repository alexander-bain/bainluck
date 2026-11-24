"""Tests for #13572 split: member art resolution/conference tables and 7 pre-draw truth checks (#13551)."""

from __future__ import annotations

import json
from pathlib import Path

from app.utils.forms_lab_truth import (
    check_ladder_monotonic,
    check_no_computed_number,
    check_no_price_floor,
    check_one_date_per_family,
    check_one_unit_per_axis,
    check_one_winner_adds_to_100,
    check_ties_handled,
    evaluate_truth_checks,
)
from app.utils.member_art_13551 import (
    NBA_CONFERENCES,
    NFL_CONFERENCES,
    NHL_CONFERENCES,
    canonical_contender_name,
    compose_short_member_label,
    resolve_member_art,
    team_conference,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_canonical_aliases_unicode_and_conference_tables() -> None:
    assert canonical_contender_name("Gemini") == "Google"
    assert canonical_contender_name("Claude") == "Anthropic"
    assert canonical_contender_name("ChatGPT") == "OpenAI"
    assert canonical_contender_name("Grok") == "xAI"

    assert len(NHL_CONFERENCES["Eastern"]) == 16
    assert len(NHL_CONFERENCES["Western"]) == 16
    assert len(NBA_CONFERENCES["Eastern"]) == 15
    assert len(NBA_CONFERENCES["Western"]) == 15
    assert len(NFL_CONFERENCES["AFC"]) == 16
    assert len(NFL_CONFERENCES["NFC"]) == 16
    assert team_conference("Anaheim Ducks", "nhl") == "Western"
    assert team_conference("Boston Bruins", "nhl") == "Eastern"

    for name in (
        "Apple",
        "NVIDIA",
        "Microsoft",
        "Gemini",
        "Claude",
        "ChatGPT",
        "Victor Wembanyama",
        "Luka Dončić",
        "Penélope Cruz",
        "Alabama Crimson Tide",
        "Utah Mammoth",
    ):
        art = resolve_member_art(name)
        assert art["url"], f"Expected verified url for {name}: {art}"

    assert compose_short_member_label("Actor cast as Felix Leiter") == "Felix Leiter"


def test_seven_pre_draw_truth_checks_pass_and_refuse() -> None:
    c1_ok = check_one_winner_adds_to_100([51, 29, 5, 4, 3, 10.5], field_label="MVP")
    assert c1_ok.passed
    bad_sum = check_one_winner_adds_to_100([68, 61, 55], field_label="NBA Scoring")
    assert not bad_sum.passed
    assert "184" in bad_sum.reason

    c2_ok = check_ladder_monotonic([("Nov 30", 14), ("Dec 15", 65), ("Dec 31", 85)])
    assert c2_ok.passed
    bad_climb = check_ladder_monotonic([("Apr 28", 62), ("Jul 28", 52)], ladder_label="AGI")
    assert not bad_climb.passed

    c3_ok = check_one_date_per_family(["2026-12-31", "Dec 31, 2026"])
    assert c3_ok.passed
    bad_date = check_one_date_per_family(["2026-12-31", "2027-03-31"])
    assert not bad_date.passed

    c4_ok = check_one_unit_per_axis(["$M", "$m"])
    assert c4_ok.passed
    bad_unit = check_one_unit_per_axis(["$M", "% RT Score"])
    assert not bad_unit.passed

    c5_ok = check_ties_handled([("Holbrook", 11.0), ("Mackie", 11.0)], tie_rule="Tie badge")
    assert c5_ok.passed
    bad_tie = check_ties_handled([("Holbrook", 11.0), ("Mackie", 11.0)], tie_rule=None)
    assert not bad_tie.passed
    bad_cut_tie = check_ties_handled(
        [("T1", 90), ("T2", 80), ("T3", 70), ("T4", 60), ("T5", 55), ("T6", 50), ("T7", 45), ("Ducks", 38), ("Blues", 38)],
        cut_index=8,
        cut_tie_rule=None,
    )
    assert not bad_cut_tie.passed

    c6_ok = check_no_price_floor([45, 22, 11])
    assert c6_ok.passed
    assert not check_no_price_floor([3, 2, 1, 1]).passed

    c7_ok = check_no_computed_number(has_computed_numbers=False, allowed=False)
    assert c7_ok.passed
    bad_d367 = check_no_computed_number(has_computed_numbers=True, allowed=False)
    assert not bad_d367.passed
    assert "decision 367" in bad_d367.reason

    ok_all, reasons_ok, wires_ok = evaluate_truth_checks([c1_ok, c2_ok, c3_ok, c4_ok, c5_ok, c6_ok, c7_ok])
    assert ok_all is True
    assert reasons_ok == []
    assert len(wires_ok) == 7

    ok_bad, reasons_bad, _ = evaluate_truth_checks([c1_ok, bad_sum, bad_climb])
    assert ok_bad is False
    assert len(reasons_bad) == 2


def test_verified_discover_art_backend_frontend_parity_and_unique_keys() -> None:
    backend_data = json.loads((REPO_ROOT / "backend/data/discover/verified_discover_art.json").read_text(encoding="utf-8"))
    frontend_data = json.loads((REPO_ROOT / "frontend/lib/discover/verifiedDiscoverArt.json").read_text(encoding="utf-8"))
    assert backend_data == frontend_data

    keys = [e["entity_key"] for e in backend_data["entries"]]
    assert len(keys) == len(set(keys)), "Duplicate entity_key in verified_discover_art.json"
    # Includes both #13526 portraits and #13572 additive Batch 1 entries
    key_set = set(keys)
    for expected in (
        "matthew-rhys",
        "tina-fey",
        "apple-inc",
        "nvidia-corp",
        "anthropic-pbc",
        "hugh-jackman",
        "lana-del-rey",
    ):
        assert expected in key_set

    urls = [e["url"] for e in backend_data["entries"]]
    assert len(urls) == len(set(urls)), "Duplicate image url in verified_discover_art.json"

    for e in backend_data["entries"]:
        if e["entity_key"] in {"hugh-jackman", "lana-del-rey", "google-gemini-brand", "baidu-inc", "sinners-film", "victor-wembanyama-nba"}:
            assert str(e.get("source_page") or "").startswith("https://"), f"Missing source_page on {e['entity_key']}"


def test_short_company_names_match_whole_name_only_not_nature_or_horoscope() -> None:
    from app.utils.container_machinery import SubjectArtResolver

    resolver = SubjectArtResolver()
    for positive in ("Amazon", "Apple", "Gemini", "Meta", "Claude", "Tesla"):
        assert resolve_member_art(positive, resolver=resolver)["url"], f"Expected logo for {positive}"
        assert resolver.resolve(positive, allow_team_lookup=False)["url"], f"Expected resolver match for {positive}"

    for negative in (
        "Amazon rainforest",
        "Amazon River",
        "Amazon deforestation before 2027",
        "Apple harvest 2027",
        "Gemini zodiac sign",
        "Meta-analysis on sleep",
        "Claude Monet exhibition",
    ):
        art_m = resolve_member_art(negative, resolver=resolver)
        art_r = resolver.resolve(negative, allow_team_lookup=False)
        assert art_m["url"] is None, f"Unexpected logo on {negative!r}: {art_m}"
        assert art_r["url"] is None, f"Unexpected resolver logo on {negative!r}: {art_r}"
