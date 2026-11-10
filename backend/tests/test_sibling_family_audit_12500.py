"""Tests for sibling_family caption grammar, family-level titles, and priced-row completeness (#12500)."""

from __future__ import annotations

from datetime import datetime, timezone

from app.routes.admin_ranking_eval import (
    _build_proposed_card_preview,
    load_grouping_grade_deck,
)
from app.utils.grouping_licences import (
    _check_title_caption_violation,
    default_grouping_licences_registry,
    detect_served_card_violation,
    promote_licensed_proposal_to_definition,
)
from app.utils.sibling_family import _clean_subject_display
from app.utils.sibling_family_proposer import (
    _build_default_heading,
    verify_heading_from_market_words,
)

FIXED_NOW = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)


def test_clean_subject_display_strips_trailing_possessive() -> None:
    assert _clean_subject_display("Alex Pereira's", strip_state_suffix=False) == "Alex Pereira"
    assert _clean_subject_display("Ilia Topuria’s", strip_state_suffix=False) == "Ilia Topuria"
    assert _clean_subject_display("Arsenal", strip_state_suffix=False) == "Arsenal"


def test_default_heading_never_emits_inverted_will_which_or_raw_placeholders() -> None:
    now = FIXED_NOW
    assert now.year == 2026

    cl_heading = _build_default_heading(
        "will * win the 2026 27 champions league",
        [
            "Will Arsenal win the 2026–27 Champions League?",
            "Will Real Madrid win the 2026–27 Champions League?",
            "Will Barcelona win the 2026–27 Champions League?",
        ],
        subject_unit="contenders",
    )
    assert "will which" not in cl_heading.lower()
    assert "contenders" not in cl_heading.lower()
    assert cl_heading == "Who will win the 2026–27 Champions League?"

    nba_heading = _build_default_heading(
        "will the * win the 2027 nba finals",
        [
            "Will the Dallas Mavericks win the 2027 NBA Finals?",
            "Will the Boston Celtics win the 2027 NBA Finals?",
            "Will the Los Angeles Lakers win the 2027 NBA Finals?",
        ],
        subject_unit="teams",
    )
    assert "will which" not in nba_heading.lower()
    assert nba_heading == "Which team will win the 2027 NBA Finals?"

    recount_heading = _build_default_heading(
        "will there be a recount in the * senate race",
        [
            "Will there be a recount in the Michigan Senate race?",
            "Will there be a recount in the Georgia Senate race?",
            "Will there be a recount in the North Carolina Senate race?",
        ],
        subject_unit="candidates",
    )
    assert "candidates" not in recount_heading.lower()
    assert recount_heading == "Will there be a recount in which Senate race?"

    next_man_out = _build_default_heading(
        "who will win the next man out *",
        [
            "Who will win the Next Man Out: Tommy?",
            "Who will win the Next Man Out: Jake?",
            "Who will win the Next Man Out: Chris?",
        ],
        subject_unit="candidates",
    )
    assert "candidates" not in next_man_out.lower()
    assert next_man_out == "Who will win the Next Man Out?"

    ufc_distance = _build_default_heading(
        "* next fight go the distance",
        [
            "Alex Pereira's next fight go the distance?",
            "Ilia Topuria's next fight go the distance?",
            "Max Holloway's next fight go the distance?",
        ],
        subject_unit="subjects",
    )
    assert "subjects" not in ufc_distance.lower()
    assert ufc_distance == "Whose next fight go the distance?"


def test_verify_heading_from_market_words_rejects_single_member_names_and_bad_grammar() -> None:
    markets = [
        {"name": "Will Gavin Newsom run for President in 2028?"},
        {"name": "Will Alexandria Ocasio-Cortez run for President in 2028?"},
        {"name": "Will JD Vance run for President in 2028?"},
    ]
    assert verify_heading_from_market_words(
        "Who will run for President in 2028?", markets, subject_unit="candidates"
    )
    # Single-member subject leaked into heading must be refused.
    assert not verify_heading_from_market_words(
        "Will JD Vance run for President in 2028?", markets, subject_unit="candidates"
    )
    # Inverted interrogative must be refused.
    assert not verify_heading_from_market_words(
        "Will which candidate run for President in 2028?", markets, subject_unit="candidates"
    )
    # Raw placeholder token must be refused.
    assert not verify_heading_from_market_words(
        "Will subjects run for President in 2028?", markets, subject_unit="subjects"
    )
    # Mixed-case brand name at start of heading (e.g. iPhone, eBay, xAI) is allowed.
    iphone_markets = [
        {"name": "Will iPhone 18 Pro ship in 2026?"},
        {"name": "Will iPhone 18 Air ship in 2026?"},
        {"name": "Will iPhone 18 Fold ship in 2026?"},
    ]
    assert verify_heading_from_market_words(
        "iPhone 18 ship in 2026?", iphone_markets, subject_unit="models"
    )


def test_licence_promotion_and_served_card_guard_refuse_caption_and_data_violations() -> None:
    reg = default_grouping_licences_registry()
    reg["kinds"]["sibling_family"]["status"] = "PASS"
    reg["kinds"]["sibling_family"]["exam_receipt"] = "docs/discover/sibling-family-exam-2026-11.md"

    bad_grammar_out = promote_licensed_proposal_to_definition(
        {
            "kind": "sibling_family",
            "slug": "bad-will-which",
            "name": "Will which contender win the 2026–27 Champions League?",
            "rule": {"producer": "sibling_family"},
        },
        registry=reg,
    )
    assert not bad_grammar_out.promoted
    assert bad_grammar_out.reason.startswith("caption_violation:")

    single_member_out = promote_licensed_proposal_to_definition(
        {
            "kind": "sibling_family",
            "slug": "bad-single-member-title",
            "name": "Will JD Vance run for President in 2028?",
            "subjects": ["Gavin Newsom", "Alexandria Ocasio-Cortez", "JD Vance"],
            "rule": {"producer": "sibling_family"},
        },
        registry=reg,
    )
    assert not single_member_out.promoted
    assert "Single-member subject" in single_member_out.reason

    unpriced_out = promote_licensed_proposal_to_definition(
        {
            "kind": "sibling_family",
            "slug": "bad-unpriced-row",
            "name": "Who will run for President in 2028?",
            "rows": [
                {"label": "Gavin Newsom", "value": "No number yet"},
                {"label": "JD Vance", "value": "45%"},
            ],
            "rule": {"producer": "sibling_family"},
        },
        registry=reg,
    )
    assert not unpriced_out.promoted
    assert unpriced_out.reason == "data_violation:unpriced_row"

    # Served card violation checks:
    assert (
        detect_served_card_violation(
            {
                "slug": "served-bad-grammar",
                "kind": "sibling_family",
                "title": "Will which contender win the 2026–27 Champions League?",
                "rows": [
                    {"label": "Arsenal", "probability": 0.18, "value": "18%"},
                    {"label": "Barcelona", "probability": 0.14, "value": "14%"},
                ],
            }
        )
        is not None
    )
    assert (
        detect_served_card_violation(
            {
                "slug": "served-unpriced",
                "kind": "sibling_family",
                "title": "Who will win the 2026–27 Champions League?",
                "rows": [
                    {"label": "Arsenal", "value": "No number yet"},
                    {"label": "Barcelona", "probability": 0.14, "value": "14%"},
                ],
            }
        )
        is not None
    )
    assert (
        detect_served_card_violation(
            {
                "slug": "served-dup-labels",
                "kind": "sibling_family",
                "title": "Senate seat margin",
                "rows": [
                    {"label": "51", "probability": 0.55, "value": "55%"},
                    {"label": "51", "probability": 0.45, "value": "45%"},
                ],
            }
        )
        is not None
    )
    # Non-sibling kinds (e.g. series_hub) with repeated row labels across games or
    # 'contenders' in title must NOT be flagged for runtime suspension.
    assert (
        detect_served_card_violation(
            {
                "slug": "series-hub-celtics-heat",
                "kind": "series_hub",
                "title": "Eastern Conference contenders: Celtics vs Heat",
                "rows": [
                    {"label": "Boston Celtics", "probability": 0.62, "value": "62%"},
                    {"label": "Boston Celtics", "probability": 0.58, "value": "58%"},
                ],
            },
            allow_settled_members=True,
        )
        is None
    )
    # Mixed-case brand title (iPhone) on a sibling_family card must NOT be flagged.
    assert (
        detect_served_card_violation(
            {
                "slug": "sibling-iphone-18",
                "kind": "sibling_family",
                "title": "iPhone 18 ship in 2026?",
                "rows": [
                    {"label": "iPhone 18 Pro", "probability": 0.85, "value": "85%"},
                    {"label": "iPhone 18 Air", "probability": 0.64, "value": "64%"},
                ],
            }
        )
        is None
    )


def test_build_proposed_card_preview_excludes_unpriced_rows_and_disambiguates_numeric_labels() -> None:
    preview = _build_proposed_card_preview(
        {
            "slug": "refused-family",
            "name": "Who will run for President in 2028?",
            "category": "politics",
            "member_count": 3,
            "members": [
                {"id": 1, "subject": "Gavin Newsom", "name": "Will Gavin Newsom run?", "yes_probability": 0.42},
                {"id": 2, "subject": "JD Vance", "name": "Will JD Vance run?", "yes_probability": 0.51},
                {"id": 3, "subject": "Marco Rubio", "name": "Will Marco Rubio run?", "yes_probability": None},
            ],
        }
    )
    assert [r["value"] for r in preview["rows"]] == ["51%", "42%"]
    assert all(r["value"] != "No number yet" for r in preview["rows"])
    assert "1 without a live Yes price withheld" in preview["count_line"]

    dup_num_preview = _build_proposed_card_preview(
        {
            "slug": "numeric-labels",
            "name": "Senate seats",
            "category": "politics",
            "member_count": 2,
            "members": [
                {"id": 10, "subject": "51", "name": "Republicans 51+ Senate seats", "yes_probability": 0.58},
                {"id": 11, "subject": "51", "name": "Democrats 51+ Senate seats", "yes_probability": 0.42},
            ],
        }
    )
    assert [r["label"] for r in dup_num_preview["rows"]] == [
        "Republicans 51+ Senate seats",
        "Democrats 51+ Senate seats",
    ]


def test_all_twenty_two_deck_sibling_family_cards_pass_caption_and_row_audit() -> None:
    deck = load_grouping_grade_deck()
    sibling_items = [it for it in deck["items"] if it.get("proposed_kind") == "sibling_family"]
    assert len(sibling_items) == 22

    for item in sibling_items:
        card = item["proposed_card"]
        title = card["title"]
        rows = card["rows"]
        labels = [r["label"] for r in rows]
        assert _check_title_caption_violation(title, row_labels=labels) is None, (
            f"Position {item['position']} ({item['item_key']}) failed caption check: {title!r}"
        )
        assert len(labels) == len({l.lower() for l in labels}), (
            f"Position {item['position']} ({item['item_key']}) has duplicate row labels: {labels}"
        )
        assert all(r["value"] != "No number yet" for r in rows), (
            f"Position {item['position']} ({item['item_key']}) rendered 'No number yet': {rows}"
        )

