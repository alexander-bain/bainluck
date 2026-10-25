"""Self-contained regression tests for #11040 cross-venue departure story.

PILLARS: DISCOVER · MATCHING · FORMATTING · TRUTH.
SHIP (#11040): A reader opens one departure story from Discover or Search, sees
related Polymarket and Kalshi markets organized by their actual settlement rules
and deadlines, opens a market, and returns with the collection context preserved.

All fixtures in this file are self-contained in-memory records (zero external
file dependencies).
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.dialects import postgresql

from app.routes.containers import _theme_order_classes, theme_page_window
from app.tasks import theme_assembly as ta
from app.utils.container_graph import CLASS_UNCLASSIFIED, EDGE_CLASSES
from app.utils.departure_story_contract import (
    DEPARTURE_ORDER,
    DEPARTURE_SUBJECTS,
    KATIE_ZACHARIA_DEPARTURE_SPEC,
    KATIE_ZACHARIA_PRESS_SECRETARY,
    PETE_HEGSETH_DEFENSE_SECRETARY,
    PREDICATE_ACTUAL_DEPARTURE,
    PREDICATE_ANNOUNCEMENT,
    PREDICATE_UNKNOWN,
    TRUMP_CABINET_DEPARTURE_SPEC,
    decide_departure_subject,
    departure_equivalence_for_fold,
    departure_predicate,
    departure_story_key_for_market,
    evaluate_departure_equivalence,
    extract_departure_evidence,
)
from app.utils.search_collections import attach_search_collections
from app.utils.theme_collection_ref import (
    PublishedTheme,
    PublishedThemes,
    attach_search_family_collection_refs,
    attach_theme_collection_refs,
)
from app.utils.theme_definitions import (
    AI,
    DECISION_REASONS,
    KATIE_ZACHARIA_PRESS_SECRETARY_2026,
    OSCARS_2027,
    PETE_HEGSETH_DEFENSE_SECRETARY_2025,
    REGISTRY,
    candidate_population,
    parse_theme_slug,
    theme_class_rank,
)

NOW = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)

# Full verbatim Polymarket rules for event 1183118 (including both the "ceases to be"
# lead-in and the decisive "An announcement of Katie Zacharia's resignation/removal
# ... will immediately resolve" sentence — F1 regression guard).
PM_1183118_FULL_RULES = (
    "This market will resolve to \"Yes\" if Katie Zacharia ceases to be White House "
    "Press Secretary between market creation and the specified date, 11:59 PM ET. "
    "An announcement of Katie Zacharia's resignation/removal by this market's end date "
    "will immediately resolve this market to \"Yes\", regardless of when the announced "
    "resignation/removal goes into effect."
)

KALSHI_KXZACHARIAOUT_FULL_RULES = (
    "If Katie Zacharia leaves as White House Press Secretary before Nov 1, 2026, then "
    "the market resolves to Yes. Katie Zacharia must have an actual departure date and "
    "vacate the role within the time period."
)


# ---------------------------------------------------------------------------
# Embedded self-contained 40 decided cases + 1 unknown case (departure-story@1).
# ---------------------------------------------------------------------------

DECIDED_MEMBERSHIP_CASES = [
    # --- Katie Zacharia positives (Polymarket announcement ladder) ---
    (
        "Z-PM-65678073",
        "katie-zacharia-press-secretary",
        {
            "internal_id": 65678073,
            "source": "polymarket",
            "name": "Katie Zacharia out as Press Secretary by October 31?",
            "llm_sport_category": "politics",
            "created_at": "2026-10-13T16:16:56.690979+00:00",
            "registration_key": ["polymarket_event", "1183118"],
            "deadline": {"instant": {"utc": "2026-11-01T03:59Z"}},
        },
        "admitted",
        "departure_announced",
        ["admitted_subject_relation"],
    ),
    (
        "Z-PM-65678074",
        "katie-zacharia-press-secretary",
        {
            "internal_id": 65678074,
            "source": "polymarket",
            "name": "Katie Zacharia out as Press Secretary by December 31?",
            "llm_sport_category": "politics",
            "created_at": "2026-10-13T16:16:56.690979+00:00",
            "registration_key": ["polymarket_event", "1183118"],
            "deadline": {"instant": {"utc": "2027-01-01T04:59Z"}},
        },
        "admitted",
        "departure_announced",
        ["admitted_subject_relation"],
    ),
    # --- Katie Zacharia positives (Kalshi vacated-office ladder) ---
    *(
        (
            f"Z-K-KXZACHARIAOUT-26OCT-{suffix}",
            "katie-zacharia-press-secretary",
            {
                "internal_id": None,
                "source": "kalshi",
                "name": "Katie Zacharia out as White House Press Secretary?",
                "llm_sport_category": "politics",
                "created_at": "2026-10-13T13:53:36.167816Z",
                "registration_key": ["kalshi_series", "KXZACHARIAOUT"],
                "deadline": {"instant": {"utc": utc}},
            },
            "admitted",
            "departure_vacated",
            ["admitted_subject_relation"],
        )
        for suffix, utc in [
            ("26OCT20", "2026-10-20T03:59Z"),
            ("26OCT24", "2026-10-24T03:59Z"),
            ("26NOV01", "2026-11-01T03:59Z"),
            ("27JAN01", "2027-01-01T04:59Z"),
            ("27JUL01", "2027-07-01T03:59Z"),
            ("28JAN01", "2028-01-01T04:59Z"),
            ("28JUL01", "2028-07-01T03:59Z"),
            ("29JAN01", "2029-01-01T04:59Z"),
        ]
    ),
    # --- Katie Zacharia positives (in-role & after-role) ---
    (
        "Z-PM-briefing",
        "katie-zacharia-press-secretary",
        {
            "internal_id": 65809353,
            "source": "polymarket",
            "name": "Will Katie Zacharia give another press briefing as Press Secretary?",
            "llm_sport_category": "politics",
            "created_at": "2026-10-14T12:31:34Z",
            "deadline": {"instant": {"utc": "2027-01-01T04:59Z"}},
        },
        "admitted",
        "side_question",
        ["admitted_subject_relation"],
    ),
    (
        "Z-PM-new-role",
        "katie-zacharia-press-secretary",
        {
            "internal_id": 66944824,
            "source": "polymarket",
            "name": "Will Katie Zacharia be officially given a new role in the Trump administration by December 31?",
            "llm_sport_category": "politics",
            "created_at": None,
            "deadline": {"instant": {"utc": "2027-01-01T04:59Z"}},
        },
        "admitted",
        "after_role",
        ["admitted_subject_relation"],
    ),
    # --- Katie Zacharia negatives (Zachariah Branch football false friends & field rows) ---
    (
        "Z-NEG-8122710",
        "katie-zacharia-press-secretary",
        {
            "internal_id": 8122710,
            "source": "kalshi",
            "name": "Offensive Rookie of the Year Winner?",
            "outcome_names": ["Zachariah Branch", "Carnell Tate", "Denzel Boston"],
            "llm_sport_category": "football",
        },
        "excluded",
        None,
        ["lexical_false_friend", "not_this_subject"],
    ),
    (
        "Z-NEG-59693629",
        "katie-zacharia-press-secretary",
        {
            "internal_id": 59693629,
            "source": "kalshi",
            "name": "Top Fantasy Rookie WR",
            "outcome_names": ["Zachariah Branch", "Denzel Boston", "Germie Bernard"],
            "llm_sport_category": "football",
        },
        "excluded",
        None,
        ["lexical_false_friend", "not_this_subject"],
    ),
    (
        "Z-NEG-59165061",
        "katie-zacharia-press-secretary",
        {
            "internal_id": 59165061,
            "source": "kalshi",
            "name": "Top Fantasy Rookie",
            "outcome_names": ["Zachariah Branch", "Denzel Boston", "Carnell Tate"],
            "llm_sport_category": "football",
        },
        "excluded",
        None,
        ["lexical_false_friend", "not_this_subject"],
    ),
    (
        "Z-NEG-59164986",
        "katie-zacharia-press-secretary",
        {
            "internal_id": 59164986,
            "source": "kalshi",
            "name": "Offensive Rookie of the Year Finalists",
            "outcome_names": ["Jadarian Price", "Antonio Williams", "Fernando Mendoza"],
            "llm_sport_category": "football",
        },
        "excluded",
        None,
        ["lexical_false_friend", "not_this_subject"],
    ),
    (
        "Z-NEG-65536762",
        "katie-zacharia-press-secretary",
        {
            "internal_id": 65536762,
            "source": "kalshi",
            "name": "Offensive Rookie of the Month in October",
            "outcome_names": ["Zachariah Branch", "Carnell Tate", "Demond Claiborne"],
            "llm_sport_category": "football",
        },
        "excluded",
        None,
        ["lexical_false_friend", "not_this_subject"],
    ),
    (
        "Z-NEG-66770165",
        "katie-zacharia-press-secretary",
        {
            "internal_id": 66770165,
            "source": "kalshi",
            "name": "San Francisco vs Atlanta: Touchdowns",
            "outcome_names": ["Zachariah Branch: 1+", "Bijan Robinson: 1+"],
            "llm_sport_category": "football",
        },
        "excluded",
        None,
        ["lexical_false_friend", "not_this_subject"],
    ),
    (
        "Z-NEG-66821185",
        "katie-zacharia-press-secretary",
        {
            "internal_id": 66821185,
            "source": "kalshi",
            "name": "San Francisco vs Atlanta: Receiving Yards",
            "outcome_names": ["Zachariah Branch: 10+", "Drake London: 40+"],
            "llm_sport_category": "football",
        },
        "excluded",
        None,
        ["lexical_false_friend", "not_this_subject"],
    ),
    (
        "Z-NEG-56775613",
        "katie-zacharia-press-secretary",
        {
            "internal_id": 56775613,
            "source": "kalshi",
            "name": "Atlanta: Team Specials",
            "outcome_names": ["Zachariah Branch records 80+ receiving yards in a single game"],
            "llm_sport_category": "football",
        },
        "excluded",
        None,
        ["lexical_false_friend", "not_this_subject"],
    ),
    # --- Katie Zacharia negatives & synthetic controls ---
    (
        "Z-NEG-trump-say",
        "katie-zacharia-press-secretary",
        {
            "internal_id": None,
            "source": "kalshi",
            "name": "What will Trump say this week?",
            "outcome_names": ["Zacharia"],
            "llm_sport_category": "politics",
        },
        "excluded",
        None,
        ["name_only_mention"],
    ),
    (
        "Z-NEG-other-person",
        "katie-zacharia-press-secretary",
        {
            "internal_id": None,
            "source": "polymarket",
            "name": "Susie Wiles out as White House Chief of Staff by December 31?",
            "llm_sport_category": "politics",
        },
        "excluded",
        None,
        ["not_this_subject"],
    ),
    (
        "Z-NEG-surname-only-synthetic",
        "katie-zacharia-press-secretary",
        {
            "internal_id": None,
            "source": "polymarket",
            "name": "Will Zacharia Smith win the Ohio primary?",
            "llm_sport_category": "politics",
        },
        "excluded",
        None,
        ["not_this_subject"],
    ),
    (
        "Z-NEG-other-office-synthetic",
        "katie-zacharia-press-secretary",
        {
            "internal_id": None,
            "source": "polymarket",
            "name": "Katie Zacharia out as Trump Media spokesperson by December 31?",
            "llm_sport_category": "politics",
            "created_at": "2026-10-20T00:00:00Z",
        },
        "excluded",
        None,
        ["other_office"],
    ),
    (
        "Z-NEG-namesake-category-synthetic",
        "katie-zacharia-press-secretary",
        {
            "internal_id": None,
            "source": "kalshi",
            "name": "Katie Zacharia out as team captain before Jan 1, 2027?",
            "llm_sport_category": "basketball",
            "created_at": "2026-10-20T00:00:00Z",
        },
        "excluded",
        None,
        ["wrong_category"],
    ),
    (
        "Z-SYN-left-administration",
        "katie-zacharia-press-secretary",
        {
            "internal_id": None,
            "source": "polymarket",
            "name": "Will Katie Zacharia leave the Trump administration by December 31?",
            "llm_sport_category": "politics",
            "created_at": "2026-10-20T00:00:00Z",
        },
        "admitted",
        "departure_left_administration",
        ["admitted_subject_relation"],
    ),
    (
        "Z-NEG-other-office-resign-synthetic",
        "katie-zacharia-press-secretary",
        {
            "internal_id": None,
            "source": "kalshi",
            "name": "Will Katie Zacharia resign as Trump Media spokesperson before Jan 1, 2027?",
            "llm_sport_category": "politics",
            "created_at": "2026-10-20T00:00:00Z",
        },
        "excluded",
        None,
        ["other_office"],
    ),
    (
        "Z-SYN-earlier-stint",
        "katie-zacharia-press-secretary",
        {
            "internal_id": None,
            "source": "polymarket",
            "name": "Katie Zacharia out as Press Secretary by June 30?",
            "llm_sport_category": "politics",
            "created_at": "2025-03-01T00:00:00Z",
            "deadline": {"instant": {"utc": "2025-07-01T03:59Z"}},
        },
        "excluded",
        None,
        ["other_edition"],
    ),
    (
        "Z-SYN-listed-before-start",
        "katie-zacharia-press-secretary",
        {
            "internal_id": None,
            "source": "polymarket",
            "name": "Katie Zacharia out as Press Secretary by November 30?",
            "llm_sport_category": "politics",
            "created_at": "2026-10-05T00:00:00Z",
            "deadline": {"instant": {"utc": "2026-12-01T04:59Z"}},
        },
        "admitted",
        "departure_rules_unread",
        ["admitted_subject_relation"],
    ),
    # --- Pete Hegseth positives & negatives (second story proof) ---
    (
        "H-SYN-announced-window",
        "pete-hegseth-defense-secretary",
        {
            "internal_id": None,
            "source": "kalshi",
            "name": "Pete Hegseth departure announced in November?",
            "llm_sport_category": "politics",
            "created_at": "2026-10-20T00:00:00Z",
        },
        "admitted",
        "departure_rules_unread",
        ["admitted_subject_relation"],
    ),
    (
        "H-K-9428542",
        "pete-hegseth-defense-secretary",
        {
            "internal_id": 9428542,
            "source": "kalshi",
            "name": "Pete Hegseth out as Secretary of Defense?",
            "llm_sport_category": "politics",
            "registration_key": ["kalshi_series", "KXHEGSETHOUT"],
        },
        "admitted",
        "departure_rules_unread",
        ["admitted_subject_relation"],
    ),
    (
        "H-K-9428543",
        "pete-hegseth-defense-secretary",
        {
            "internal_id": 9428543,
            "source": "kalshi",
            "name": "Pete Hegseth departure announced?",
            "llm_sport_category": "politics",
        },
        "admitted",
        "departure_announced",
        ["admitted_subject_relation"],
    ),
    (
        "H-PM-8422080",
        "pete-hegseth-defense-secretary",
        {
            "internal_id": 8422080,
            "source": "polymarket",
            "name": "Pete Hegseth out as Secretary of Defense by December 31?",
            "llm_sport_category": "geopolitics",
        },
        "admitted",
        "departure_rules_unread",
        ["admitted_subject_relation"],
    ),
    (
        "H-PM-63843267",
        "pete-hegseth-defense-secretary",
        {
            "internal_id": 63843267,
            "source": "polymarket",
            "name": "Pete Hegseth out as Secretary of Defense by November 30?",
            "llm_sport_category": "politics",
        },
        "admitted",
        "departure_rules_unread",
        ["admitted_subject_relation"],
    ),
    (
        "H-NEG-108687",
        "pete-hegseth-defense-secretary",
        {
            "internal_id": 108687,
            "name": "Who will leave their role in the Trump administration in 2026?",
            "llm_sport_category": "politics",
            "outcome_names": ["Pete Hegseth"],
        },
        "excluded",
        None,
        ["name_only_mention"],
    ),
    (
        "H-NEG-113281",
        "pete-hegseth-defense-secretary",
        {
            "internal_id": 113281,
            "name": "Who will leave Trump Administration before 2027?",
            "llm_sport_category": "politics",
            "outcome_names": ["Pete Hegseth"],
        },
        "excluded",
        None,
        ["name_only_mention"],
    ),
    (
        "H-NEG-58918693",
        "pete-hegseth-defense-secretary",
        {
            "internal_id": 58918693,
            "name": "Who will attend a round of US-Iran peace talks by December 31?",
            "llm_sport_category": "politics",
            "outcome_names": ["Pete Hegseth"],
        },
        "excluded",
        None,
        ["name_only_mention"],
    ),
    (
        "H-NEG-108501",
        "pete-hegseth-defense-secretary",
        {
            "internal_id": 108501,
            "name": "Who will run for the 2028 Republican presidential nomination?",
            "llm_sport_category": "politics",
            "outcome_names": ["Pete Hegseth"],
        },
        "excluded",
        None,
        ["name_only_mention"],
    ),
    (
        "H-NEG-108324",
        "pete-hegseth-defense-secretary",
        {
            "internal_id": 108324,
            "name": "Who will Trump pardon?",
            "llm_sport_category": "politics",
            "outcome_names": ["Pete Hegseth"],
        },
        "excluded",
        None,
        ["name_only_mention"],
    ),
    (
        "H-NEG-58920450",
        "pete-hegseth-defense-secretary",
        {
            "internal_id": 58920450,
            "name": "Will Pete Hegseth attend a US x Iran diplomatic meeting by December 31, 2026?",
            "llm_sport_category": "politics",
            "outcome_names": ["Pete Hegseth"],
        },
        "excluded",
        None,
        ["not_this_story"],
    ),
]


class TestDepartureStoryMembershipCases:
    """Decision 1: all 40 decided membership cases across Katie Zacharia and Pete Hegseth."""

    def test_case_inventory_count(self):
        assert len(DECIDED_MEMBERSHIP_CASES) == 40

    @pytest.mark.parametrize(
        "case_id,story_key,row,expected_outcome,expected_section,allowed_reasons",
        DECIDED_MEMBERSHIP_CASES,
        ids=[c[0] for c in DECIDED_MEMBERSHIP_CASES],
    )
    def test_decided_membership_case(
        self, case_id, story_key, row, expected_outcome, expected_section, allowed_reasons
    ):
        subject = DEPARTURE_SUBJECTS[story_key]
        res = decide_departure_subject(subject, row)
        assert res.outcome == expected_outcome, f"{case_id}: {res}"
        assert res.section == expected_section, f"{case_id}: {res}"
        assert res.reason in allowed_reasons, f"{case_id}: {res}"
        assert res.reason in DECISION_REASONS
        if res.section is not None:
            assert res.section in EDGE_CLASSES

        # Also verify via ThemeDefinition.decide()
        defn = (
            KATIE_ZACHARIA_PRESS_SECRETARY_2026
            if story_key == "katie-zacharia-press-secretary"
            else PETE_HEGSETH_DEFENSE_SECRETARY_2025
        )
        d = defn.decide(row, now=NOW)
        assert d.outcome == expected_outcome
        assert d.edge_class == expected_section
        assert d.reason == res.reason
        assert d.rule_version == "departure-story@1"


class TestDepartureMeaningEquivalenceAndF1Guard:
    """Decision 2: Probability equivalence + F1 regression guard on verbatim Polymarket rules."""

    def test_f1_verbatim_polymarket_rules_never_misclassify_announcement_as_vacated(self):
        pm_oct31 = {
            "id": 65678073,
            "name": "Katie Zacharia out as Press Secretary by October 31?",
            "source": "polymarket",
            "external_id": "0x57e97ab7f68a11013e7e4096ce6b0601b40b9e5a8609c4cb4196ef1b753e6953",
            "group_id": "polymarket:1183118",
            "llm_sport_category": "politics",
            "description": PM_1183118_FULL_RULES,
            "resolution_date": "2026-11-01T03:59:00+00:00",
        }
        pm_dec31 = {
            "id": 65678074,
            "name": "Katie Zacharia out as Press Secretary by December 31?",
            "source": "polymarket",
            "external_id": "0xc587f97b3eaac5948ed7e148bb5248f51f98795ea0e1c3bc9acf635b0a2f95b0",
            "group_id": "polymarket:1183118",
            "llm_sport_category": "politics",
            "description": PM_1183118_FULL_RULES,
            "resolution_date": "2027-01-01T04:59:00+00:00",
        }
        kalshi_nov1 = {
            "id": 900000001,
            "name": "Will Katie Zacharia be out as White House Press Secretary before Nov 1, 2026?",
            "source": "kalshi",
            "external_id": "KXZACHARIAOUT-26OCT-26NOV01",
            "llm_sport_category": "politics",
            "description": KALSHI_KXZACHARIAOUT_FULL_RULES,
            "resolution_date": "2026-11-01T03:59:00+00:00",
        }

        # Even if registration_key is stripped and only rules text is inspected,
        # PM's announcement sentence wins over "ceases to be".
        pm_no_reg = {k: v for k, v in pm_oct31.items() if k != "group_id"}
        ev_pm = extract_departure_evidence(KATIE_ZACHARIA_DEPARTURE_SPEC, pm_no_reg)
        ev_k = extract_departure_evidence(KATIE_ZACHARIA_DEPARTURE_SPEC, kalshi_nov1)
        assert ev_pm.predicate_class == PREDICATE_ANNOUNCEMENT
        assert ev_pm.edge_class == "title"
        assert ev_pm.horizon_key == "2026-10-31"
        assert ev_k.predicate_class == PREDICATE_ACTUAL_DEPARTURE
        assert ev_k.edge_class == "advancement"
        assert ev_k.horizon_key == "2026-10-31"

        # Aligned cutoffs (2026-11-01T03:59Z) across announcement vs vacated NEVER return "same".
        verdict = evaluate_departure_equivalence(pm_oct31, kalshi_nov1)
        assert verdict.verdict == "different"
        assert not verdict.is_equivalent
        assert "predicate_mismatch" in verdict.reason
        assert departure_equivalence_for_fold(pm_oct31, kalshi_nov1).verdict == "different"

        # Same venue ladder legs with different deadlines NEVER return "same".
        ladder_verdict = evaluate_departure_equivalence(pm_oct31, pm_dec31)
        assert ladder_verdict.verdict == "different"
        assert "horizon_mismatch" in ladder_verdict.reason

    def test_missing_rules_returns_unknown_never_same(self):
        pm_no_rules = {
            "id": 65678073,
            "name": "Katie Zacharia out as Press Secretary by October 31?",
            "source": "polymarket",
            "external_id": "0x57e9",
            "llm_sport_category": "politics",
            "description": "",
            "resolution_date": "2026-11-01T03:59:00+00:00",
        }
        kalshi_nov1 = {
            "id": 900000001,
            "name": "Will Katie Zacharia be out as White House Press Secretary before Nov 1, 2026?",
            "source": "kalshi",
            "external_id": "KXZACHARIAOUT-26OCT-26NOV01",
            "llm_sport_category": "politics",
            "description": KALSHI_KXZACHARIAOUT_FULL_RULES,
            "resolution_date": "2026-11-01T03:59:00+00:00",
        }
        ev = extract_departure_evidence(KATIE_ZACHARIA_DEPARTURE_SPEC, pm_no_rules)
        assert ev.predicate_class == PREDICATE_UNKNOWN
        verdict = evaluate_departure_equivalence(pm_no_rules, kalshi_nov1)
        assert verdict.verdict == "unknown"
        assert verdict.reason == "missing_settlement_rules"

    def test_hegseth_kalshi_series_and_unread_polymarket_equivalence(self):
        heg_vac = {
            "id": 9428542,
            "name": "Pete Hegseth out as Secretary of Defense?",
            "source": "kalshi",
            "external_id": "KXHEGSETHOUT-26APR",
            "llm_sport_category": "politics",
        }
        heg_ann = {
            "id": 9428543,
            "name": "Pete Hegseth departure announced?",
            "source": "kalshi",
            "external_id": "KXHEGSETHANNOUNCEOUT-26APR",
            "llm_sport_category": "politics",
        }
        heg_pm = {
            "id": 8422080,
            "name": "Pete Hegseth out as Secretary of Defense by December 31?",
            "source": "polymarket",
            "external_id": "pm-8422080",
            "llm_sport_category": "geopolitics",
        }
        assert departure_predicate(heg_vac)["predicate"] == "unknown"
        assert departure_predicate(heg_ann)["predicate"] == "announced"
        assert departure_predicate(heg_pm)["predicate"] == "unknown"
        assert evaluate_departure_equivalence(heg_pm, heg_ann).verdict == "unknown"
        assert evaluate_departure_equivalence(heg_pm, heg_vac).verdict == "unknown"

    def test_cabinet_ostp_scope_difference_is_different(self):
        pm_cab = {
            "id": 7001,
            "name": "Who will be the first to leave the Trump Cabinet before 2027?",
            "source": "polymarket",
            "external_id": "pm-cab-1",
            "llm_sport_category": "politics",
            "description": (
                "Resolves to the first Senate-confirmed head of the 15 executive "
                "departments to leave. Does not include the Director of the Office "
                "of Science and Technology Policy (OSTP)."
            ),
        }
        kalshi_cab = {
            "id": 7002,
            "name": "Who will be the first to leave the Trump Cabinet before 2027?",
            "source": "kalshi",
            "external_id": "KXCABOUT-27JAN01",
            "llm_sport_category": "politics",
            "description": (
                "Resolves to the first member of the official White House Cabinet "
                "roster including OSTP to vacate office."
            ),
        }
        verdict = evaluate_departure_equivalence(pm_cab, kalshi_cab)
        assert verdict.verdict == "different"
        assert "predicate_mismatch" in verdict.reason

    def test_story_key_minting_admits_true_subjects_and_refuses_false_friends(self):
        assert (
            departure_story_key_for_market(
                "Katie Zacharia out as Press Secretary by October 31?", "politics"
            )
            == "story:katie_zacharia_departure"
        )
        assert (
            departure_story_key_for_market(
                "Pete Hegseth out as Secretary of Defense by December 31?", "politics"
            )
            == "story:pete_hegseth_departure"
        )
        assert (
            departure_story_key_for_market(
                "Zachariah Branch touchdowns vs Atlanta", "football"
            )
            is None
        )
        assert (
            departure_story_key_for_market(
                "What will Trump say this week?", "politics"
            )
            is None
        )


class TestThemeSlugOrderingAndSnapshotNonFold:
    """WU-1 & WU-2: theme definitions, slug parsing, section ordering, and non-fold."""

    def test_parse_theme_slug_emits_departure_family_and_role_while_keeping_ai_and_oscars_unchanged(self):
        assert parse_theme_slug("katie-zacharia-press-secretary-2026") == {
            "kind": "theme_edition",
            "family": "departure",
            "subject": "katie-zacharia-press-secretary",
            "edition": 2026,
            "role": "White House press secretary",
        }
        assert parse_theme_slug("pete-hegseth-defense-secretary-2025") == {
            "kind": "theme_edition",
            "family": "departure",
            "subject": "pete-hegseth-defense-secretary",
            "edition": 2025,
            "role": "Secretary of Defense",
        }
        assert parse_theme_slug("ai") == {"kind": "theme_continuing", "subject": "ai"}
        assert parse_theme_slug("oscars-2027") == {
            "kind": "theme_edition",
            "subject": "oscars",
            "edition": 2027,
        }

    def test_candidate_population_uses_postgres_word_boundaries(self):
        dialect = postgresql.dialect()
        for defn in (
            KATIE_ZACHARIA_PRESS_SECRETARY_2026,
            PETE_HEGSETH_DEFENSE_SECRETARY_2025,
        ):
            arms = candidate_population(defn, container_id=42, now=NOW)
            assert set(arms) == {"person_title", "prior_decision"}
            compiled = str(
                arms["person_title"].compile(
                    dialect=dialect, compile_kwargs={"literal_binds": True}
                )
            )
            assert r"\y" in compiled
            assert r"\b" not in compiled

    def test_build_snapshot_orders_departure_sections_and_never_folds_same_venue_deadline_legs(self):
        pm_oct = ta.MemberRow(
            id=65678073,
            name="Katie Zacharia out as Press Secretary by October 31?",
            source="polymarket",
            external_id="0x57e9",
            status="open",
            llm_sport_category="politics",
            resolution_date=datetime(2026, 11, 1, 3, 59, tzinfo=timezone.utc),
            outcomes=(
                ta.OutcomeRow("Yes", None, None, 0.073, 1),
                ta.OutcomeRow("No", None, None, 0.927, 2),
            ),
        )
        pm_dec = ta.MemberRow(
            id=65678074,
            name="Katie Zacharia out as Press Secretary by December 31?",
            source="polymarket",
            external_id="0xc587",
            status="open",
            llm_sport_category="politics",
            resolution_date=datetime(2027, 1, 1, 4, 59, tzinfo=timezone.utc),
            outcomes=(
                ta.OutcomeRow("Yes", None, None, 0.245, 3),
                ta.OutcomeRow("No", None, None, 0.755, 4),
            ),
        )
        kalshi = ta.MemberRow(
            id=900000001,
            name="Katie Zacharia out as White House Press Secretary?",
            source="kalshi",
            external_id="KXZACHARIAOUT-26OCT",
            status="open",
            llm_sport_category="politics",
            outcomes=(
                ta.OutcomeRow("Before Jan 1, 2029", None, None, 0.85, 11),
                ta.OutcomeRow("Before Nov 1, 2026", None, None, 0.10, 12),
            ),
        )
        briefing = ta.MemberRow(
            id=65809353,
            name="Will Katie Zacharia give another press briefing as Press Secretary?",
            source="polymarket",
            external_id="pm-briefing",
            status="open",
            llm_sport_category="politics",
            outcomes=(
                ta.OutcomeRow("Yes", None, None, 0.99, 21),
                ta.OutcomeRow("No", None, None, 0.037, 22),
            ),
        )
        new_role = ta.MemberRow(
            id=66944824,
            name="Will Katie Zacharia be officially given a new role in the Trump administration by December 31?",
            source="polymarket",
            external_id="pm-new-role",
            status="open",
            llm_sport_category="politics",
            outcomes=(
                ta.OutcomeRow("Yes", None, None, 0.28, 31),
                ta.OutcomeRow("No", None, None, 0.72, 32),
            ),
        )

        members = {
            66944824: "after_role",
            65809353: "side_question",
            900000001: "departure_vacated",
            65678074: "departure_announced",
            65678073: "departure_announced",
        }
        rows = {r.id: r for r in (pm_oct, pm_dec, kalshi, briefing, new_role)}
        snap = ta.build_snapshot(
            {
                "id": 911040,
                "slug": "katie-zacharia-press-secretary-2026",
                "name": "Katie Zacharia",
            },
            revision=7,
            members=members,
            rows=rows,
            inventory_complete=True,
        )
        assert snap.folded_ids == ()
        assert snap.shown_ids == (65678073, 65678074, 900000001, 65809353, 66944824)
        assert snap.shown_count == 5 and snap.eligible_count == 5

    def test_theme_page_window_and_section_order_keep_departure_order_and_unclassified_last(self):
        shown_ids = [65678073, 65678074, 900000001, 8422080, 8422081, 65809353, 66944824, 999999999]
        classes = {
            65678073: "departure_announced",
            65678074: "departure_announced",
            900000001: "departure_vacated",
            8422080: "departure_rules_unread",
            8422081: "departure_left_administration",
            65809353: "side_question",
            66944824: "after_role",
            999999999: CLASS_UNCLASSIFIED,
        }
        for defn in (KATIE_ZACHARIA_PRESS_SECRETARY_2026, None):
            window = theme_page_window(
                shown_ids, classes, cursor_key=None, limit=50, defn=defn
            )
            assert window == (shown_ids, None)
            ordered_sections = _theme_order_classes(set(classes.values()), defn=defn)
            assert ordered_sections == list(DEPARTURE_ORDER) + [CLASS_UNCLASSIFIED]


class TestSearchFuturesFamilyCollectionRef:
    """WU-2: Search futures_families carry collection_ref even when event_ids is empty."""

    @pytest.mark.asyncio
    async def test_attach_search_collections_attaches_ref_to_futures_family(self, monkeypatch):
        monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")
        payload = {
            "query": "katie zacharia",
            "results": [],
            "futures_families": [
                {
                    "family_key": "polymarket:1183118",
                    "headline": {"id": 65678073, "name": "Katie Zacharia out as Press Secretary by October 31?"},
                    "members": [
                        {"id": 65678074, "name": "Katie Zacharia out as Press Secretary by December 31?"},
                    ],
                }
            ],
        }
        expected_ref = {
            "slug": "katie-zacharia-press-secretary-2026",
            "name": "Katie Zacharia",
            "revision": 7,
            "collection_count": 5,
        }
        published = PublishedThemes(
            themes=(PublishedTheme(container_id=911040, slug="katie-zacharia-press-secretary-2026", revision=7),)
        )

        async def _fake_attach(items, *, published, budget_seconds=0.25, read_snapshot=None, session_factory=None):
            assert len(items) == 1
            assert items[0]["data"]["story_key"] == "polymarket:1183118"
            assert items[0]["data"]["member_ids"] == [65678073, 65678074]
            return [{**items[0], "data": {**items[0]["data"], "collection_ref": expected_ref}}]

        with (
            patch(
                "app.utils.theme_collection_ref.read_published_themes",
                new=AsyncMock(return_value=published),
            ),
            patch(
                "app.utils.theme_collection_ref.attach_theme_collection_refs",
                side_effect=_fake_attach,
            ),
        ):
            out = await attach_search_collections(AsyncMock(), payload)

        assert out["futures_families"][0]["collection_ref"] == expected_ref
        assert "collection_ref" not in payload["futures_families"][0]

    @pytest.mark.asyncio
    async def test_attach_search_collections_family_ref_fails_open(self, monkeypatch):
        monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")
        payload = {
            "query": "katie zacharia",
            "results": [],
            "futures_families": [
                {
                    "family_key": "polymarket:1183118",
                    "markets": [{"id": 65678073}],
                }
            ],
        }
        with patch(
            "app.utils.theme_collection_ref.read_published_themes",
            side_effect=RuntimeError("db down"),
        ):
            out = await attach_search_collections(AsyncMock(), payload)
        assert out is payload
        assert "collection_ref" not in out["futures_families"][0]
