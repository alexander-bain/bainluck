"""Self-contained regression tests for #11040 cross-venue departure story.

PILLARS: DISCOVER · MATCHING · FORMATTING · TRUTH.
SHIP (#11040): One departure story preserves related markets while accurately
explaining their different settlement rules.

All fixtures in this file are self-contained in-memory records (zero external
file dependencies).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
import copy
import dataclasses
from datetime import datetime, timezone
import hashlib
import json
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.dialects import postgresql

from app.routes.containers import CLASS_ORDER, _theme_order_classes, theme_page_window
from app.tasks import theme_assembly as ta
from app.utils.container_graph import CLASS_UNCLASSIFIED, EDGE_CLASSES
from app.utils.departure_story_contract import (
    DEPARTURE_ORDER,
    DEPARTURE_SUBJECTS,
    KATIE_ZACHARIA_PRESS_SECRETARY,
    MISSING_RULES_TEXT_POLICY,
    PETE_HEGSETH_DEFENSE_SECRETARY,
    REGISTRATIONS,
    decide_departure_subject,
    departure_predicate,
    departure_story_key_for_market,
    evaluate_departure_equivalence,
)
from app.utils.search_collections import attach_search_collections
from app.utils.theme_collection_ref import (
    PublishedTheme,
    PublishedThemes,
)
from app.utils.theme_definitions import (
    DECISION_REASONS,
    DEFAULT_CLASS_RANK,
    DEFAULT_OTHER_CLASS_RANK,
    KATIE_ZACHARIA_PRESS_SECRETARY_2026,
    PETE_HEGSETH_DEFENSE_SECRETARY_2025,
    candidate_population,
    parse_theme_slug,
    theme_class_rank,
)

NOW = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)

# Exact retained Polymarket event 1183118 rules (SHA-256 cc46e9a2b8bf04167ca6c9374555c00aa0e6ee4d87cd98d59a19053ee4a11269).
PM_1183118_FULL_RULES = (
    "This market will resolve to \u201cYes\u201d if Katie Zacharia ceases to be White House "
    "Press Secretary for any period of time between market creation and the specified date, "
    "11:59 PM ET. Otherwise, this market will resolve to \u201cNo\u201d.\n\n"
    "An announcement of Katie Zacharia's resignation/removal by this market's end date will "
    'immediately resolve this market to "Yes", regardless of when the announced '
    "resignation/removal goes into effect.\n\n"
    "If Katie Zacharia has not yet taken office as White House Press Secretary at market "
    'creation, this market will also resolve to "Yes" if, by the specified date, 11:59 PM ET, '
    "her appointment is withdrawn or it is announced that she will not take the position.\n\n"
    "The resolution source for this market will be official information from Katie Zacharia "
    "and the U.S. government; however, a consensus of credible reporting may also be used."
)

# Exact retained Kalshi KXZACHARIAOUT-26OCT rules_secondary (SHA-256 2d191cebfb1cadff2e4aa8cc736e035dcc26c5ff76a3fedd6603893dfa2a71a1).
KALSHI_KXZACHARIAOUT_SECONDARY_RULES = (
    "Katie Zacharia must have an actual departure date and vacate the role within the time period.\n\n"
    "Temporary leaves of absence, suspensions, or recusals do not constitute leaving, resigning "
    "from, or retiring from the role unless the individual formally and permanently ceases to "
    "hold the position. If the person vacates the role and then re-occupies the role, the "
    "contract shall settle on the initial vacation of the role.\n\n"
    'For "leave," cessation of holding the role qualifies, including resignation, retirement, '
    "removal, expulsion, expiration of term without renewal, recall, or other means by which "
    "the individual no longer occupies the role. This includes both voluntary and involuntary "
    "early departure AND the natural expiration of a term."
)

KALSHI_KXZACHARIAOUT_PRIMARY_RULES = (
    "If Katie Zacharia leaves as White House Press Secretary before Nov 1, 2026, "
    "then the market resolves to Yes."
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
            assert res.section in CLASS_ORDER

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


class TestEvidenceBoundRegistrationsB2:
    """B2: Predicate registrations validate provider, event, edition, and stored rules."""

    def test_retained_rules_hashes_match_registrations(self):
        assert (
            hashlib.sha256(PM_1183118_FULL_RULES.encode("utf-8")).hexdigest()
            == REGISTRATIONS[("polymarket_event", "1183118")]["rules_sha256"]
        )
        assert (
            hashlib.sha256(KALSHI_KXZACHARIAOUT_SECONDARY_RULES.encode("utf-8")).hexdigest()
            == REGISTRATIONS[("kalshi_series", "KXZACHARIAOUT")]["rules_sha256"]
        )

    def test_true_retained_rules_assign_registered_sections(self):
        pm_row = {
            "source": "polymarket",
            "name": "Katie Zacharia out as Press Secretary by October 31?",
            "llm_sport_category": "politics",
            "group_id": "polymarket:1183118",
            "description": PM_1183118_FULL_RULES,
            "deadline": {"instant": {"utc": "2026-11-01T03:59Z"}},
        }
        k_row = {
            "source": "kalshi",
            "external_id": "KXZACHARIAOUT-26OCT-26NOV01",
            "name": "Will Katie Zacharia be out as White House Press Secretary before Nov 1, 2026?",
            "llm_sport_category": "politics",
            "market_metadata": {
                "series_ticker": "KXZACHARIAOUT",
                "event_ticker": "KXZACHARIAOUT-26OCT",
                "rules_primary": KALSHI_KXZACHARIAOUT_PRIMARY_RULES,
                "rules_secondary": KALSHI_KXZACHARIAOUT_SECONDARY_RULES,
            },
            "deadline": {"instant": {"utc": "2026-11-01T03:59Z"}},
        }

        pm_res = decide_departure_subject(KATIE_ZACHARIA_PRESS_SECRETARY, pm_row)
        assert pm_res.outcome == "admitted"
        assert pm_res.section == "departure_announced"
        pred_ev = pm_res.evidence[-1]
        assert pred_ev["basis"] == "rules"
        assert pred_ev["observed_rules_sha256"] == pred_ev["rules_sha256"]

        k_res = decide_departure_subject(KATIE_ZACHARIA_PRESS_SECRETARY, k_row)
        assert k_res.outcome == "admitted"
        assert k_res.section == "departure_vacated"
        k_pred_ev = k_res.evidence[-1]
        assert k_pred_ev["basis"] == "rules"
        assert k_pred_ev["observed_rules_sha256"] == k_pred_ev["rules_sha256"]

    def test_missing_stored_rules_uses_explicit_registration_only_policy(self):
        pm_no_desc = {
            "source": "polymarket",
            "name": "Katie Zacharia out as Press Secretary by October 31?",
            "llm_sport_category": "politics",
            "group_id": "polymarket:1183118",
            "description": None,
            "deadline": {"instant": {"utc": "2026-11-01T03:59Z"}},
        }
        res = decide_departure_subject(KATIE_ZACHARIA_PRESS_SECRETARY, pm_no_desc)
        assert res.outcome == "admitted"
        assert res.section == "departure_announced"
        pred_ev = res.evidence[-1]
        assert pred_ev["basis"] == "registration_only"
        assert pred_ev["missing_text_policy"] == MISSING_RULES_TEXT_POLICY

    def test_changed_or_contradictory_rules_route_to_rules_unread_while_preserving_membership(self):
        pm_changed = {
            "source": "polymarket",
            "name": "Katie Zacharia out as Press Secretary by October 31?",
            "llm_sport_category": "politics",
            "group_id": "polymarket:1183118",
            "description": (
                "This market resolves to Yes only if Katie Zacharia actually vacates "
                "the office of White House Press Secretary before the deadline. "
                "An announcement alone does not resolve this market."
            ),
            "deadline": {"instant": {"utc": "2026-11-01T03:59Z"}},
        }
        k_changed = {
            "source": "kalshi",
            "external_id": "KXZACHARIAOUT-26OCT-26NOV01",
            "name": "Will Katie Zacharia be out as White House Press Secretary before Nov 1, 2026?",
            "llm_sport_category": "politics",
            "market_metadata": {
                "series_ticker": "KXZACHARIAOUT",
                "event_ticker": "KXZACHARIAOUT-26OCT",
                "rules_secondary": (
                    'An announcement of Katie Zacharia\'s resignation by the deadline '
                    'will immediately resolve this market to "Yes", regardless of when '
                    "the announced resignation goes into effect."
                ),
            },
            "deadline": {"instant": {"utc": "2026-11-01T03:59Z"}},
        }

        for row in (pm_changed, k_changed):
            res = decide_departure_subject(KATIE_ZACHARIA_PRESS_SECRETARY, row)
            assert res.outcome == "admitted"
            assert res.section == "departure_rules_unread"
            pred_ev = res.evidence[-1]
            assert pred_ev["result"] == "unknown"
            assert pred_ev["basis"] == "registration_mismatch"
            assert pred_ev["reason"] == "contradictory_settlement_clause"

    def test_matching_quote_inside_contradictory_text_is_rejected_to_rules_unread(self):
        """B2 requirement: A matching quote inside otherwise contradictory text is
        not sufficient; preserving the original quote while adding a conflicting
        settlement clause must produce `departure_rules_unread` with an inspectable reason."""
        pm_quote_plus_conflict = {
            "source": "polymarket",
            "name": "Katie Zacharia out as Press Secretary by October 31?",
            "llm_sport_category": "politics",
            "group_id": "polymarket:1183118",
            "description": (
                PM_1183118_FULL_RULES
                + "\n\nHowever, an announcement alone does not resolve this market; "
                "Katie Zacharia must have an actual departure date and vacate the role "
                "within the time period."
            ),
            "deadline": {"instant": {"utc": "2026-11-01T03:59Z"}},
        }
        k_quote_plus_conflict = {
            "source": "kalshi",
            "external_id": "KXZACHARIAOUT-26OCT-26NOV01",
            "name": "Will Katie Zacharia be out as White House Press Secretary before Nov 1, 2026?",
            "llm_sport_category": "politics",
            "market_metadata": {
                "series_ticker": "KXZACHARIAOUT",
                "event_ticker": "KXZACHARIAOUT-26OCT",
                "rules_primary": KALSHI_KXZACHARIAOUT_PRIMARY_RULES,
                "rules_secondary": (
                    KALSHI_KXZACHARIAOUT_SECONDARY_RULES
                    + "\n\nAn announcement of Katie Zacharia's resignation/removal by this "
                    'market\'s end date will immediately resolve this market to "Yes", '
                    "regardless of when the announced resignation/removal goes into effect."
                ),
            },
            "deadline": {"instant": {"utc": "2026-11-01T03:59Z"}},
        }
        pm_quote_plus_unverified_amendment = {
            "source": "polymarket",
            "name": "Katie Zacharia out as Press Secretary by October 31?",
            "llm_sport_category": "politics",
            "group_id": "polymarket:1183118",
            "description": (
                PM_1183118_FULL_RULES
                + "\n\nAmendment: settlement also requires a formal FEC filing."
            ),
            "deadline": {"instant": {"utc": "2026-11-01T03:59Z"}},
        }

        for row in (pm_quote_plus_conflict, k_quote_plus_conflict):
            res = decide_departure_subject(KATIE_ZACHARIA_PRESS_SECRETARY, row)
            assert res.outcome == "admitted"
            assert res.section == "departure_rules_unread"
            pred_ev = res.evidence[-1]
            assert pred_ev["result"] == "unknown"
            assert pred_ev["basis"] == "registration_mismatch"
            assert pred_ev["reason"] == "contradictory_settlement_clause"

        res_amend = decide_departure_subject(
            KATIE_ZACHARIA_PRESS_SECRETARY, pm_quote_plus_unverified_amendment
        )
        assert res_amend.outcome == "admitted"
        assert res_amend.section == "departure_rules_unread"
        assert res_amend.evidence[-1]["basis"] == "registration_mismatch"
        assert res_amend.evidence[-1]["reason"] == "rules_sha256_mismatch"

    def test_later_event_in_same_kalshi_series_does_not_inherit_registration(self):
        """B2 requirement: Do not silently extend retained evidence for one event or
        edition to every future event in a provider series."""
        k_later_event = {
            "source": "kalshi",
            "external_id": "KXZACHARIAOUT-28JAN-T280101",
            "name": "Will Katie Zacharia be out as White House Press Secretary before Jan 1, 2028?",
            "llm_sport_category": "politics",
            "market_metadata": {
                "series_ticker": "KXZACHARIAOUT",
                "event_ticker": "KXZACHARIAOUT-28JAN",
                "rules_secondary": KALSHI_KXZACHARIAOUT_SECONDARY_RULES,
            },
            "deadline": {"instant": {"utc": "2028-01-01T04:59Z"}},
        }
        res = decide_departure_subject(KATIE_ZACHARIA_PRESS_SECRETARY, k_later_event)
        assert res.outcome == "admitted"
        assert res.section == "departure_rules_unread"
        pred_ev = res.evidence[-1]
        assert pred_ev["result"] == "unknown"
        assert pred_ev["basis"] == "registration_mismatch"
        assert pred_ev["reason"] == "unregistered_series_event"

    def test_provider_and_edition_mismatches_are_refused(self):
        wrong_provider = {
            "source": "kalshi",
            "name": "Katie Zacharia out as Press Secretary by October 31?",
            "llm_sport_category": "politics",
            "group_id": "polymarket:1183118",
        }
        wrong_edition = {
            "source": "polymarket",
            "name": "Katie Zacharia out as Press Secretary by October 31?",
            "llm_sport_category": "politics",
            "group_id": "polymarket:1183118",
            "edition": 2025,
        }
        wrong_person = {
            "source": "polymarket",
            "name": "Susie Wiles out as White House Chief of Staff by December 31?",
            "llm_sport_category": "politics",
            "group_id": "polymarket:1183118",
        }

        res_prov = decide_departure_subject(KATIE_ZACHARIA_PRESS_SECRETARY, wrong_provider)
        assert res_prov.outcome == "admitted"
        assert res_prov.section == "departure_rules_unread"
        assert res_prov.evidence[-1]["reason"] == "provider_mismatch"

        res_ed = decide_departure_subject(KATIE_ZACHARIA_PRESS_SECRETARY, wrong_edition)
        assert res_ed.outcome == "admitted"
        assert res_ed.section == "departure_rules_unread"
        assert res_ed.evidence[-1]["reason"] == "edition_or_subject_mismatch"

        pred_wrong_person = departure_predicate(wrong_person)
        assert pred_wrong_person["predicate"] == "unknown"
        assert pred_wrong_person["reason"] == "edition_or_subject_mismatch"


class TestUnregisteredRulesRemainUnreadB3:
    """B3: Unregistered markets never infer a predicate from rules-text regexes."""

    @pytest.mark.parametrize(
        "label,rules_text",
        [
            (
                "announce_verb",
                "Resolves Yes if Pete Hegseth resigns, is removed, or announces he will step down as Secretary of Defense before the deadline.",
            ),
            (
                "it_is_announced_that",
                "This market resolves to Yes if it is announced that Pete Hegseth will leave the Department of Defense.",
            ),
            (
                "announcement_excluded",
                "Resolves Yes if Pete Hegseth ceases to hold office. An announcement of resignation before he leaves office does not resolve this market.",
            ),
            (
                "plain_vacancy",
                "Resolves Yes if Pete Hegseth ceases to be Secretary of Defense before Dec 31, 2026.",
            ),
            (
                "successor_nomination_counts",
                "Resolves Yes if Pete Hegseth ceases to be Secretary of Defense or if a successor is formally nominated before the deadline.",
            ),
        ],
    )
    def test_unregistered_hegseth_rules_stay_in_rules_unread(self, label, rules_text):
        row = {
            "source": "polymarket",
            "external_id": f"pm-hegseth-{label}",
            "name": "Pete Hegseth out as Secretary of Defense by December 31?",
            "llm_sport_category": "politics",
            "description": rules_text,
        }
        pred = departure_predicate(row, subject=PETE_HEGSETH_DEFENSE_SECRETARY)
        assert pred == {
            "predicate": "unknown",
            "basis": "rules_not_read",
            "reason": "unregistered_market",
        }
        res = decide_departure_subject(PETE_HEGSETH_DEFENSE_SECRETARY, row)
        assert res.outcome == "admitted"
        assert res.section == "departure_rules_unread"

    def test_unregistered_zacharia_market_with_rules_text_stays_in_rules_unread(self):
        unregistered_pm = {
            "source": "polymarket",
            "external_id": "0xunregistered",
            "name": "Katie Zacharia out as Press Secretary by November 30?",
            "llm_sport_category": "politics",
            "description": PM_1183118_FULL_RULES,
        }
        res = decide_departure_subject(KATIE_ZACHARIA_PRESS_SECRETARY, unregistered_pm)
        assert res.outcome == "admitted"
        assert res.section == "departure_rules_unread"
        assert res.evidence[-1]["reason"] == "unregistered_market"


class TestDepartureMeaningEquivalenceDecision2:
    """Decision 2: Probability equivalence across venues (evidence-bound)."""

    def test_registered_polymarket_vs_kalshi_aligned_cutoffs_are_never_equivalent(self):
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
            "market_metadata": {
                "series_ticker": "KXZACHARIAOUT",
                "event_ticker": "KXZACHARIAOUT-26OCT",
                "rules_primary": KALSHI_KXZACHARIAOUT_PRIMARY_RULES,
                "rules_secondary": KALSHI_KXZACHARIAOUT_SECONDARY_RULES,
            },
            "resolution_date": "2026-11-01T03:59:00+00:00",
        }

        verdict = evaluate_departure_equivalence(pm_oct31, kalshi_nov1)
        assert verdict.verdict == "different"
        assert not verdict.is_equivalent
        assert "predicate_mismatch" in verdict.reason

        ladder_verdict = evaluate_departure_equivalence(pm_oct31, pm_dec31)
        assert ladder_verdict.verdict == "different"
        assert "horizon_mismatch" in ladder_verdict.reason

    def test_unregistered_market_returns_unknown_never_same(self):
        pm_unregistered = {
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
            "market_metadata": {
                "series_ticker": "KXZACHARIAOUT",
                "event_ticker": "KXZACHARIAOUT-26OCT",
                "rules_secondary": KALSHI_KXZACHARIAOUT_SECONDARY_RULES,
            },
            "resolution_date": "2026-11-01T03:59:00+00:00",
        }
        verdict = evaluate_departure_equivalence(pm_unregistered, kalshi_nov1)
        assert verdict.verdict == "unknown"
        assert verdict.reason == "missing_settlement_rules"

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


class TestActualAssemblyFoldProtection:
    """Item 4 (N9): Protect the actual assembly path against folding cross-venue
    same-title and different-month departure markets."""

    def test_default_class_rank_for_non_departure_themes_is_preserved(self):
        assert dict(DEFAULT_CLASS_RANK) == {
            "title": 0,
            "advancement": 1,
            "side_question": 2,
        }
        assert DEFAULT_OTHER_CLASS_RANK == 3

    def test_parse_theme_slug_and_candidate_population(self):
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

    def test_build_snapshot_fold_trap_regression_fails_if_departure_guard_is_removed(self):
        """Regression guard for N9: includes cross-venue identical-title departure
        markets (`65265180` Polymarket vs `99000010` Kalshi on `"Katie Zacharia out
        as Press Secretary by October 31?"`, plus `"by December 31?"` pair).
        Proves that:
        1. `ta.build_snapshot` keeps `folded_ids == ()` and all members in `shown_ids`.
        2. Removing the `resolved_defn.family == "departure"` guard causes
           `ta.build_snapshot` to fold `99000010` and `99000011` into `folded_ids`.
        """
        pm_oct = ta.MemberRow(
            id=65265180,
            name="Katie Zacharia out as Press Secretary by October 31?",
            source="polymarket",
            external_id="0x57e97ab7f68a11013e7e4096ce6b0601b40b9e5a8609c4cb4196ef1b753e6953",
            status="resolved",
            llm_sport_category="politics",
            resolution_date=datetime(2026, 11, 1, 3, 59, tzinfo=timezone.utc),
            settled_at=datetime(2026, 10, 16, 22, 57, tzinfo=timezone.utc),
            description=PM_1183118_FULL_RULES,
            market_metadata={"polymarket_event_id": "1183118", "group_id": "polymarket:1183118"},
            outcomes=(
                ta.OutcomeRow("Yes", True, "api_settlement", 1.0, 1),
                ta.OutcomeRow("No", False, "api_settlement", 0.0, 2),
            ),
        )
        pm_dec = ta.MemberRow(
            id=65678074,
            name="Katie Zacharia out as Press Secretary by December 31?",
            source="polymarket",
            external_id="0xc587f97b3eaac5948ed7e148bb5248f51f98795ea0e1c3bc9acf635b0a2f95b0",
            status="open",
            llm_sport_category="politics",
            resolution_date=datetime(2027, 1, 1, 4, 59, tzinfo=timezone.utc),
            description=PM_1183118_FULL_RULES,
            market_metadata={"polymarket_event_id": "1183118", "group_id": "polymarket:1183118"},
            outcomes=(
                ta.OutcomeRow("Yes", None, None, 0.245, 3),
                ta.OutcomeRow("No", None, None, 0.755, 4),
            ),
        )
        k_same_title_oct = ta.MemberRow(
            id=99000010,
            name="Katie Zacharia out as Press Secretary by October 31?",
            source="kalshi",
            external_id="KXZACHARIAOUT-26OCT-T261101",
            status="open",
            llm_sport_category="politics",
            resolution_date=datetime(2026, 11, 1, 3, 59, tzinfo=timezone.utc),
            market_metadata={
                "series_ticker": "KXZACHARIAOUT",
                "event_ticker": "KXZACHARIAOUT-26OCT",
                "rules_primary": KALSHI_KXZACHARIAOUT_PRIMARY_RULES,
                "rules_secondary": KALSHI_KXZACHARIAOUT_SECONDARY_RULES,
            },
            outcomes=(
                ta.OutcomeRow("Yes", None, None, 0.42, 5),
                ta.OutcomeRow("No", None, None, 0.58, 6),
            ),
        )
        k_same_title_dec = ta.MemberRow(
            id=99000011,
            name="Katie Zacharia out as Press Secretary by December 31?",
            source="kalshi",
            external_id="KXZACHARIAOUT-26OCT-T270101",
            status="open",
            llm_sport_category="politics",
            resolution_date=datetime(2027, 1, 1, 4, 59, tzinfo=timezone.utc),
            market_metadata={
                "series_ticker": "KXZACHARIAOUT",
                "event_ticker": "KXZACHARIAOUT-26OCT",
                "rules_secondary": KALSHI_KXZACHARIAOUT_SECONDARY_RULES,
            },
            outcomes=(
                ta.OutcomeRow("Yes", None, None, 0.36, 7),
                ta.OutcomeRow("No", None, None, 0.64, 8),
            ),
        )
        k_ladder = ta.MemberRow(
            id=62603363,
            name="Will Katie Zacharia leave her role as White House Press Secretary?",
            source="kalshi",
            external_id="KXZACHARIAOUT-26OCT",
            status="open",
            llm_sport_category="politics",
            resolution_date=datetime(2029, 1, 1, 4, 59, tzinfo=timezone.utc),
            market_metadata={
                "series_ticker": "KXZACHARIAOUT",
                "event_ticker": "KXZACHARIAOUT-26OCT",
                "rules_primary": KALSHI_KXZACHARIAOUT_PRIMARY_RULES,
                "rules_secondary": KALSHI_KXZACHARIAOUT_SECONDARY_RULES,
            },
            outcomes=(
                ta.OutcomeRow("Before Jan 1, 2029", None, None, 0.85, 11),
                ta.OutcomeRow("Before Nov 1, 2026", None, None, 0.10, 12),
            ),
        )
        new_role = ta.MemberRow(
            id=66944824,
            name="Will Katie Zacharia be officially given a new role in the Trump administration by December 31?",
            source="polymarket",
            external_id="pm-new-role",
            status="open",
            llm_sport_category="politics",
            resolution_date=datetime(2027, 1, 1, 4, 59, tzinfo=timezone.utc),
            outcomes=(
                ta.OutcomeRow("Yes", None, None, 0.28, 31),
                ta.OutcomeRow("No", None, None, 0.72, 32),
            ),
        )
        briefing = ta.MemberRow(
            id=65809353,
            name="Will Katie Zacharia give another press briefing as Press Secretary?",
            source="polymarket",
            external_id="pm-briefing",
            status="open",
            llm_sport_category="politics",
            resolution_date=datetime(2027, 1, 1, 4, 59, tzinfo=timezone.utc),
            outcomes=(
                ta.OutcomeRow("Yes", None, None, 0.035, 21),
                ta.OutcomeRow("No", None, None, 0.965, 22),
            ),
        )

        rows = {
            r.id: r
            for r in (
                pm_oct,
                pm_dec,
                k_same_title_oct,
                k_same_title_dec,
                k_ladder,
                new_role,
                briefing,
            )
        }
        members = {
            rid: KATIE_ZACHARIA_PRESS_SECRETARY_2026.decide(row, now=NOW).edge_class
            for rid, row in rows.items()
        }
        assert members == {
            65265180: "departure_announced",
            65678074: "departure_announced",
            99000010: "departure_vacated",
            99000011: "departure_vacated",
            62603363: "departure_vacated",
            66944824: "after_role",
            65809353: "side_question",
        }

        container = {
            "id": 911040,
            "slug": "katie-zacharia-press-secretary-2026",
            "name": "Katie Zacharia",
        }
        snap = ta.build_snapshot(
            container,
            revision=7,
            members=members,
            rows=rows,
            inventory_complete=True,
            defn=KATIE_ZACHARIA_PRESS_SECRETARY_2026,
        )
        assert snap.folded_ids == ()
        # Note: after_role (66944824) ranks before side_question (65809353) per DEPARTURE_ORDER.
        assert snap.shown_ids == (
            65265180,
            65678074,
            62603363,
            99000010,
            99000011,
            66944824,
            65809353,
        )
        assert snap.shown_count == 7 and snap.eligible_count == 7

        # Prove this test fails if the `family == "departure"` fold skip in
        # `theme_assembly.build_snapshot` is removed.
        unguarded_defn = dataclasses.replace(
            KATIE_ZACHARIA_PRESS_SECRETARY_2026, family=None
        )
        unguarded_snap = ta.build_snapshot(
            container,
            revision=7,
            members=members,
            rows=rows,
            inventory_complete=True,
            defn=unguarded_defn,
        )
        assert 99000010 in unguarded_snap.folded_ids
        assert 99000011 in unguarded_snap.folded_ids
        assert 99000010 not in unguarded_snap.shown_ids

    @pytest.mark.asyncio
    async def test_run_assemble_theme_collections_end_to_end_preserves_cross_venue_same_title_members(
        self, monkeypatch
    ):
        """Exercises `_run_assemble_theme_collections` through edge upserts,
        decision rows, and Redis snapshot publication on `katie-zacharia-press-secretary-2026`."""
        from tests.test_theme_assembly_9935 import _FakeDB, _FakeRedis

        database = _FakeDB()
        redis_client = _FakeRedis()

        @asynccontextmanager
        async def _session():
            yield database.session()

        async def _page_ids(session, defn, container_id, now, cursor, limit):
            prior = {
                child for (cid, child) in session.work["decisions"] if cid == container_id
            }
            ids = sorted((database.population.get(defn.slug(), set()) | prior))
            return [i for i in ids if i > cursor][:limit]

        async def _load_markets(session, ids):
            return {i: database.markets[i] for i in ids if i in database.markets}

        import app.tasks.base

        monkeypatch.setattr(app.tasks.base, "get_task_session", _session)
        monkeypatch.setattr(ta, "_page_ids", _page_ids)
        monkeypatch.setattr(ta, "_load_markets", _load_markets)
        monkeypatch.setattr(ta, "_redis_client", lambda: redis_client)
        monkeypatch.setenv(ta.THEME_ASSEMBLY_ENABLED_ENV, "1")

        slug = "katie-zacharia-press-secretary-2026"
        pm_oct = ta.MemberRow(
            id=65265180,
            name="Katie Zacharia out as Press Secretary by October 31?",
            source="polymarket",
            external_id="0x57e9",
            status="resolved",
            llm_sport_category="politics",
            resolution_date=datetime(2026, 11, 1, 3, 59, tzinfo=timezone.utc),
            settled_at=datetime(2026, 10, 16, 22, 57, tzinfo=timezone.utc),
            description=PM_1183118_FULL_RULES,
            market_metadata={"polymarket_event_id": "1183118", "group_id": "polymarket:1183118"},
            outcomes=(
                ta.OutcomeRow("Yes", True, "api_settlement", 1.0, 1),
                ta.OutcomeRow("No", False, "api_settlement", 0.0, 2),
            ),
        )
        k_same_title_oct = ta.MemberRow(
            id=99000010,
            name="Katie Zacharia out as Press Secretary by October 31?",
            source="kalshi",
            external_id="KXZACHARIAOUT-26OCT-T261101",
            status="open",
            llm_sport_category="politics",
            resolution_date=datetime(2026, 11, 1, 3, 59, tzinfo=timezone.utc),
            market_metadata={
                "series_ticker": "KXZACHARIAOUT",
                "event_ticker": "KXZACHARIAOUT-26OCT",
                "rules_primary": KALSHI_KXZACHARIAOUT_PRIMARY_RULES,
                "rules_secondary": KALSHI_KXZACHARIAOUT_SECONDARY_RULES,
            },
            outcomes=(
                ta.OutcomeRow("Yes", None, None, 0.42, 5),
                ta.OutcomeRow("No", None, None, 0.58, 6),
            ),
        )
        k_later_series_event = ta.MemberRow(
            id=99000028,
            name="Will Katie Zacharia be out as White House Press Secretary before Jan 1, 2028?",
            source="kalshi",
            external_id="KXZACHARIAOUT-28JAN-T280101",
            status="open",
            llm_sport_category="politics",
            resolution_date=datetime(2028, 1, 1, 4, 59, tzinfo=timezone.utc),
            market_metadata={
                "series_ticker": "KXZACHARIAOUT",
                "event_ticker": "KXZACHARIAOUT-28JAN",
                "rules_secondary": KALSHI_KXZACHARIAOUT_SECONDARY_RULES,
            },
            outcomes=(
                ta.OutcomeRow("Yes", None, None, 0.81, 9),
                ta.OutcomeRow("No", None, None, 0.19, 10),
            ),
        )
        false_friend = ta.MemberRow(
            id=8122710,
            name="Offensive Rookie of the Year Winner?",
            source="kalshi",
            external_id="KXOROY-26",
            status="open",
            llm_sport_category="football",
            outcomes=(ta.OutcomeRow("Zachariah Branch", None, None, 0.15, 20),),
        )

        database.add_markets(
            pm_oct, k_same_title_oct, k_later_series_event, false_friend, slug=slug
        )
        report = await ta._run_assemble_theme_collections(only=slug, now=NOW)
        assert report["terminal"] == "complete"
        assert database.theme_edges(slug) == {
            65265180: "departure_announced",
            99000010: "departure_vacated",
            99000028: "departure_rules_unread",
        }
        assert database.decision(slug, 8122710)["outcome"] == "excluded"
        assert database.decision(slug, 8122710)["reason"] == "lexical_false_friend"

        cid = database.container_id(slug)
        rev = database.revision(slug)
        snap = json.loads(redis_client.store[ta.snapshot_key(cid, rev)])
        assert snap["folded_ids"] == []
        assert snap["shown_ids"] == [65265180, 99000010, 99000028]

    def test_theme_page_window_and_section_order_keep_departure_order_and_unclassified_last(self):
        shown_ids = [
            65678073,
            65678074,
            900000001,
            8422080,
            8422081,
            66944824,
            65809353,
            999999999,
        ]
        classes = {
            65678073: "departure_announced",
            65678074: "departure_announced",
            900000001: "departure_vacated",
            8422080: "departure_rules_unread",
            8422081: "departure_left_administration",
            66944824: "after_role",
            65809353: "side_question",
            999999999: CLASS_UNCLASSIFIED,
        }
        defn = KATIE_ZACHARIA_PRESS_SECRETARY_2026
        window = theme_page_window(
            shown_ids, classes, cursor_key=None, limit=50, defn=defn
        )
        assert window == (shown_ids, None)
        ordered_sections = _theme_order_classes(set(classes.values()), defn=defn)
        assert ordered_sections == list(DEPARTURE_ORDER) + [CLASS_UNCLASSIFIED]
        assert _theme_order_classes(
            {"title", "advancement", "side_question", CLASS_UNCLASSIFIED}, defn=None
        ) == ["title", "advancement", "side_question", CLASS_UNCLASSIFIED]


class TestSearchFuturesFamilyCollectionRef:
    """WU-2 + N2: Search futures_families carry collection_ref when both Search
    collection switches (`CONTAINER_DISCOVERY_ENABLED` and `CONTAINERS_READ_ENABLED`)
    are enabled, and never bypass `CONTAINER_DISCOVERY_ENABLED`."""

    @pytest.mark.asyncio
    async def test_attach_search_collections_attaches_ref_when_both_switches_enabled(
        self, monkeypatch
    ):
        monkeypatch.setenv("CONTAINER_DISCOVERY_ENABLED", "true")
        monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")
        payload = {
            "query": "katie zacharia",
            "results": [],
            "futures_families": [
                {
                    "family_key": "polymarket:1183118",
                    "headline": {
                        "id": 65678073,
                        "name": "Katie Zacharia out as Press Secretary by October 31?",
                    },
                    "members": [
                        {
                            "id": 65678074,
                            "name": "Katie Zacharia out as Press Secretary by December 31?",
                        },
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
            themes=(
                PublishedTheme(
                    container_id=911040,
                    slug="katie-zacharia-press-secretary-2026",
                    revision=7,
                ),
            )
        )

        async def _fake_attach(
            items,
            *,
            published,
            budget_seconds=0.25,
            read_snapshot=None,
            session_factory=None,
        ):
            assert len(items) == 1
            assert items[0]["data"]["story_key"] == "polymarket:1183118"
            assert items[0]["data"]["member_ids"] == [65678073, 65678074]
            return [
                {
                    **items[0],
                    "data": {**items[0]["data"], "collection_ref": expected_ref},
                }
            ]

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
    async def test_attach_search_collections_respects_container_discovery_switch(
        self, monkeypatch
    ):
        """N2 guard: when `CONTAINERS_READ_ENABLED=true` but `CONTAINER_DISCOVERY_ENABLED`
        is unset/false, `attach_search_collections` does not bypass `search_collections_enabled()`."""
        monkeypatch.delenv("CONTAINER_DISCOVERY_ENABLED", raising=False)
        monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")
        payload = {
            "query": "katie zacharia",
            "results": [],
            "futures_families": [
                {
                    "family_key": "polymarket:1183118",
                    "headline": {"id": 65678073},
                    "members": [{"id": 65678074}],
                }
            ],
        }
        with patch(
            "app.utils.theme_collection_ref.read_published_themes",
            new=AsyncMock(side_effect=AssertionError("should not be called when switch is off")),
        ):
            out = await attach_search_collections(AsyncMock(), payload)
        assert out is payload
        assert "collection_ref" not in payload["futures_families"][0]

    @pytest.mark.asyncio
    async def test_attach_search_collections_family_ref_fails_open(self, monkeypatch):
        monkeypatch.setenv("CONTAINER_DISCOVERY_ENABLED", "true")
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
        assert "collection_ref" not in payload["futures_families"][0]
