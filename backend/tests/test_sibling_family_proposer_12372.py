"""Red-first tests for the ``sibling_family`` proposer (#12372, Epic #12288, Decide 61-A / 92-C).

PILLAR: DISCOVER / MATCHING / TRUTH · SHIP: a program finds sibling families in
live markets and proposes selector-based ``sibling_family`` definitions (never a
list of IDs), checked by ``sibling_family``'s own truth checks and bounded model
spend under Decide 61-A ($5/run, $30/Nov, price printed before each run), while
the old daily pair task ``generate-discover-comparison-candidates`` is retired
off its timer.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import pytest

from app.utils.roundup_containers import validate_roundup_definition
from app.utils.sibling_family_proposer import (
    DEFAULT_JSON_OUT,
    DEFAULT_MD_OUT,
    HARD_RUN_COST_CAP_USD,
    NOVEMBER_MONTHLY_CAP_USD,
    build_proposed_sibling_definition,
    enforce_proposer_cost_cap,
    estimate_proposer_cost_usd,
    is_excluded_sibling_market,
    nominate_sibling_families,
    print_preflight_cost_banner,
    propose_sibling_families,
    verify_heading_from_market_words,
    verify_word_for_word_quote,
)

NOW_NOV_8 = datetime(2026, 11, 8, 18, 0, 0, tzinfo=timezone.utc)


def _make_sibling_market(
    market_id: int,
    name: str,
    *,
    source: str = "polymarket",
    group_id: str | None = "polymarket:99001",
    category: str = "weather",
    resolution_date: str = "2026-12-31T23:59:00Z",
    yes_prob: float | None = 0.42,
    description: str | None = None,
) -> dict[str, Any]:
    rule_text = (
        description
        if description is not None
        else f"This market resolves to Yes if {name.rstrip('?')} according to official NOAA records by December 31, 2026."
    )
    return {
        "id": market_id,
        "source": source,
        "external_id": f"{source}-{market_id}",
        "group_id": group_id,
        "name": name,
        "category": category,
        "llm_sport_category": category,
        "status": "open",
        "market_type": "yes_no",
        "mutually_exclusive": True,
        "resolution_date": resolution_date,
        "updated_at": "2026-11-08T17:00:00Z",
        "description": rule_text,
        "outcomes": [
            {
                "id": market_id * 10 + 1,
                "name": "Yes",
                "probability": yes_prob,
                "is_winner": False,
                "resolution_source": None,
                "observed_at": "2026-11-08T17:00:00Z",
            },
            {
                "id": market_id * 10 + 2,
                "name": "No",
                "probability": (1.0 - yes_prob) if yes_prob is not None else None,
                "is_winner": False,
                "resolution_source": None,
                "observed_at": "2026-11-08T17:00:00Z",
            },
        ],
    }


def test_old_pair_task_is_off_its_timer() -> None:
    """Exit check: ``generate-discover-comparison-candidates`` is off ``celery_app.conf.beat_schedule``."""
    from app.tasks import celery_app

    assert "generate-discover-comparison-candidates" not in celery_app.conf.beat_schedule


def test_standing_exclusions_reject_forbidden_market_classes() -> None:
    """Guardrail 5: exclude mention/statement, daily, financial, combo/path, foreign elections, and death/health/crime."""
    assert is_excluded_sibling_market("What will Jerome Powell say during his November press conference?")[0] is True
    assert is_excluded_sibling_market("Will Bitcoin go up or down between 10:00am - 10:15am ET?")[0] is True
    assert is_excluded_sibling_market("Will Bitcoin close above $100,000 in 2026?")[0] is True
    assert is_excluded_sibling_market("Senate Combo: Will Democrats win Pennsylvania and Michigan in 2026?")[0] is True
    assert is_excluded_sibling_market("Who will be the next Prime Minister of Canada in 2026?")[0] is True
    assert is_excluded_sibling_market("Will John Doe be sentenced to prison in 2026?")[0] is True
    assert is_excluded_sibling_market("Will rain exceed 3 inches in Seattle in November 2026?")[0] is False


def test_proposed_definition_is_selector_never_id_list() -> None:
    """Every proposed definition uses ``group_id`` or ``title_ilike`` + ``template``, never ``candidates``."""
    markets = [
        _make_sibling_market(7001, "Will Seattle record 3 inches of rain in November 2026?", yes_prob=0.68),
        _make_sibling_market(7002, "Will Portland record 3 inches of rain in November 2026?", yes_prob=0.54),
        _make_sibling_market(7003, "Will Boston record 3 inches of rain in November 2026?", yes_prob=0.39),
        _make_sibling_market(7004, "Will Miami record 3 inches of rain in November 2026?", yes_prob=0.25),
    ]
    families = nominate_sibling_families(markets)
    assert len(families) == 1
    defn = build_proposed_sibling_definition(families[0], generated_at="2026-11-08T18:00:00Z", model="rules-only")

    assert defn["kind"] == "roundup"
    assert defn["membership"] == "sibling-family"
    assert defn["relations"] == ["same_measure", "same_window", "sibling"]
    assert defn["level"] == "member"
    assert defn["rule"]["producer"] == "sibling_family"
    assert "candidates" not in defn["rule"]
    assert defn["rule"].get("group_id") == "polymarket:99001" or defn["rule"].get("title_ilike")
    assert defn["rule"].get("template") == "will * record 3 inches of rain"

    # Must pass #12371's selector rule validator without error.
    validate_roundup_definition(defn, path="test_proposal")


def test_word_for_word_quote_and_heading_verification() -> None:
    """Model checks must quote rules word for word and take headings from the markets' own words."""
    m_a = _make_sibling_market(7001, "Will Seattle record 3 inches of rain in November 2026?")
    m_b = _make_sibling_market(7002, "Will Portland record 3 inches of rain in November 2026?")

    exact_quote_a = "This market resolves to Yes if Will Seattle record 3 inches of rain in November 2026 according to official NOAA records"
    assert verify_word_for_word_quote(exact_quote_a, m_a) is True
    assert verify_word_for_word_quote("Fabricated rule text not in market description", m_a) is False

    # Heading from market words passes; invented words or venue names fail.
    assert verify_heading_from_market_words(
        "Will cities record 3 inches of rain {deadline}?",
        [m_a, m_b],
        subject_unit="cities",
    ) is True
    assert verify_heading_from_market_words(
        "Kalshi rainfall showdown {deadline}?",
        [m_a, m_b],
        subject_unit="cities",
    ) is False
    assert verify_heading_from_market_words(
        "Tropical cyclone barometer {deadline}?",
        [m_a, m_b],
        subject_unit="cities",
    ) is False


def test_proposer_applies_sibling_family_truth_checks_serve_and_refuse() -> None:
    """``propose_sibling_families`` runs ``select_sibling_family`` and separates ``serve`` from ``refuse``."""
    # Valid 4-member family (serve)
    valid_family = [
        _make_sibling_market(7001, "Will Seattle record 3 inches of rain in November 2026?", resolution_date="2026-11-30T23:59:00Z", yes_prob=0.68),
        _make_sibling_market(7002, "Will Portland record 3 inches of rain in November 2026?", resolution_date="2026-11-30T23:59:00Z", yes_prob=0.54),
        _make_sibling_market(7003, "Will Boston record 3 inches of rain in November 2026?", resolution_date="2026-11-30T23:59:00Z", yes_prob=0.39),
        _make_sibling_market(7004, "Will Miami record 3 inches of rain in November 2026?", resolution_date="2026-11-30T23:59:00Z", yes_prob=0.25),
    ]
    # Refused family: stored resolution_date disagrees across members in the same cohort
    refused_family = [
        _make_sibling_market(
            8001,
            "Will Austin hit 90 degrees in November 2026?",
            group_id="polymarket:99002",
            resolution_date="2026-11-30T23:59:00Z",
            yes_prob=0.61,
        ),
        _make_sibling_market(
            8002,
            "Will Dallas hit 90 degrees in November 2026?",
            group_id="polymarket:99002",
            resolution_date="2026-11-29T23:59:00Z",
            yes_prob=0.48,
        ),
        _make_sibling_market(
            8003,
            "Will Houston hit 90 degrees in November 2026?",
            group_id="polymarket:99002",
            resolution_date="2026-11-30T23:59:00Z",
            yes_prob=0.52,
        ),
    ]

    report = propose_sibling_families(
        valid_family + refused_family,
        now=NOW_NOV_8,
        use_llm=False,
    )
    by_template = {f["template_key"]: f for f in report["families"]}
    rain = by_template["will * record 3 inches of rain"]
    heat = by_template["will * hit 90 degrees"]

    assert rain["kind_verdict"] == "serve"
    assert rain["refusal_reasons"] == []
    assert rain["trust_pass"] is True
    assert rain["quotes"]["quotes_verified"] is True
    assert "candidates" not in rain["proposed_definition"]["rule"]
    assert rain["card_words_390px"] is not None

    assert heat["kind_verdict"] == "refuse"
    assert "resolution_date_disagrees_with_title" in heat["refusal_reasons"]
    assert heat["trust_pass"] is False


def test_decide_61a_cost_printing_and_caps(capsys: pytest.CaptureFixture[str]) -> None:
    """Decide 61-A: print price before each run, enforce $5/run and $30/Nov caps, block December without Alex's word."""
    assert HARD_RUN_COST_CAP_USD == 5.0
    assert NOVEMBER_MONTHLY_CAP_USD == 30.0

    banner = print_preflight_cost_banner(
        family_count=20,
        estimated_cost_usd=0.042,
        november_spent_prior_usd=1.20,
        now=NOW_NOV_8,
    )
    captured = capsys.readouterr().out
    assert "$0.0420" in banner
    assert "$5.00" in banner
    assert "$30.00" in banner
    assert "[61-A]" in captured

    # Exceeding $5/run cap truncates or refuses.
    dummy_prompts = ["x" * 20000 for _ in range(400)]
    kept, cost = enforce_proposer_cost_cap(
        dummy_prompts,
        max_run_cost_usd=5.0,
        november_spent_prior_usd=0.0,
        input_cost_per_mtok=3.0,
        output_cost_per_mtok=15.0,
        now=NOW_NOV_8,
    )
    assert cost <= 5.0
    assert len(kept) < len(dummy_prompts)

    # Exceeding $30 November cumulative cap raises ValueError.
    with pytest.raises(ValueError, match="November"):
        enforce_proposer_cost_cap(
            ["test prompt"],
            max_run_cost_usd=5.0,
            november_spent_prior_usd=29.9999,
            input_cost_per_mtok=3.0,
            output_cost_per_mtok=15.0,
            now=NOW_NOV_8,
        )

    # Running in December without Alex's December cap raises ValueError.
    dec_now = datetime(2026, 12, 1, 12, 0, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="December"):
        enforce_proposer_cost_cap(
            ["test prompt"],
            max_run_cost_usd=5.0,
            november_spent_prior_usd=0.0,
            now=dec_now,
        )


def test_committed_grouping_candidates_2026_11_artifact() -> None:
    """Exit check: ``docs/discover/grouping-candidates-2026-11.{json,md}`` lists >=15 families with members, quotes, verdict, and cost."""
    assert DEFAULT_JSON_OUT.exists(), f"Missing {DEFAULT_JSON_OUT}"
    assert DEFAULT_MD_OUT.exists(), f"Missing {DEFAULT_MD_OUT}"

    payload = json.loads(DEFAULT_JSON_OUT.read_text(encoding="utf-8"))
    md_text = DEFAULT_MD_OUT.read_text(encoding="utf-8")

    assert payload["run_cost_cap_usd"] == 5.0
    assert payload["november_cost_cap_usd"] == 30.0
    assert 0.0 <= float(payload["estimated_cost_usd"]) <= 5.0
    assert 0.0 <= float(payload["actual_cost_usd"]) <= 5.0
    assert "[61-A]" in payload["preflight_cost_banner"]

    families = payload["families"]
    assert isinstance(families, list)
    assert len(families) >= 15

    for fam in families:
        assert fam["kind_verdict"] in ("serve", "refuse")
        assert isinstance(fam["members"], list) and len(fam["members"]) >= 2
        quotes = fam["quotes"]
        assert isinstance(quotes.get("market_a_quote"), str) and quotes["market_a_quote"]
        assert isinstance(quotes.get("market_b_quote"), str) and quotes["market_b_quote"]
        assert quotes.get("quotes_verified") is True
        defn = fam["proposed_definition"]
        assert "candidates" not in defn["rule"]
        validate_roundup_definition(defn, path=fam["slug"])

    assert "Sibling-Family Grouping Candidates" in md_text
    assert "$5.00" in md_text
    assert "$30.00" in md_text
