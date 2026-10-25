"""Cross-venue departure story membership and meaning equivalence contract (#11040).

PILLARS: DISCOVER · MATCHING · FORMATTING · TRUTH.
SHIP (#11040): A reader opens one departure story from Discover or Search, sees
related Polymarket and Kalshi markets organized by their actual settlement rules
and deadlines, opens a market, and returns with the collection context preserved.

This module is pure stdlib (no ORM, task, route or database imports) so
``app.utils.theme_definitions`` can import it without circular imports or
startup side effects.

Two distinct relationship decisions live here:

1. **Same-story membership** (:func:`decide_departure_subject`):
   - Evaluates supported subject, role, departure/in-role/after-role relation,
     category gate, tenure boundary, and settlement predicate from stored
     market fields and ``#5318`` registrations.
   - Admits related markets across different settlement predicates into
     rule-based collection sections (``departure_announced``,
     ``departure_vacated``, ``departure_left_administration``,
     ``departure_rules_unread``, ``side_question``, ``after_role``).
   - Refuses lexical false friends (e.g. ``"Zachariah Branch"``) with
     ``lexical_false_friend``, mention/field markets (e.g.
     ``"What will Trump say this week?"``, ``"Who will leave their role in the
     Trump administration in 2026?"``) with ``name_only_mention``, other offices
     with ``other_office``, earlier stints with ``other_edition``, and other
     subjects with ``not_this_subject`` / ``not_this_story``.

2. **Probability equivalence** (:func:`evaluate_departure_equivalence`):
   - Requires the same subject, role, edition, verified settlement predicate,
     and normalized cutoff horizon.
   - Never infers equivalence from title similarity or aligned timestamps alone.
   - Keeps announcement-based Polymarket contracts and actual-vacancy Kalshi
     contracts ``different`` even when their cutoffs align to the minute.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import re
from typing import Any, Mapping, Optional

# ---------------------------------------------------------------------------
# Rule versions & decision reasons (all fit container_member_decisions widths).
# ---------------------------------------------------------------------------

RULE_VERSION = "departure-story@1"
DEPARTURE_STORY_RULE_VERSION = RULE_VERSION
DEPARTURE_MEANING_RULE_VERSION = "departure-meaning@1"
DEPARTURE_RETENTION_DAYS = 14

ADMITTED_SUBJECT_RELATION = "admitted_subject_relation"
ADMITTED_DEPARTURE_ANNOUNCEMENT = "admitted_departure_announcement"
ADMITTED_DEPARTURE_VACATED = "admitted_departure_vacated"
ADMITTED_DEPARTURE_SEPARATE_RULE = "admitted_departure_separate_rule"

NAME_ONLY_MENTION = "name_only_mention"
OTHER_OFFICE = "other_office"
NOT_THIS_STORY = "not_this_story"
UNRELATED_SUBJECT_MENTION = "unrelated_subject_mention"

DEPARTURE_ADMITTED_REASONS = frozenset(
    {
        ADMITTED_SUBJECT_RELATION,
        ADMITTED_DEPARTURE_ANNOUNCEMENT,
        ADMITTED_DEPARTURE_VACATED,
        ADMITTED_DEPARTURE_SEPARATE_RULE,
    }
)
DEPARTURE_EXCLUDED_REASONS = frozenset(
    {
        NAME_ONLY_MENTION,
        OTHER_OFFICE,
        NOT_THIS_STORY,
        UNRELATED_SUBJECT_MENTION,
    }
)

DEPARTURE_ORDER: tuple[str, ...] = (
    "departure_announced",
    "departure_vacated",
    "departure_rules_unread",
    "departure_left_administration",
    "side_question",
    "after_role",
)

# Canonical predicate classes.
PREDICATE_ANNOUNCEMENT = "announcement_or_withdrawal"
PREDICATE_ACTUAL_DEPARTURE = "actual_departure_vacated_role"
PREDICATE_LEFT_ADMINISTRATION = "left_administration"
PREDICATE_CABINET_NO_OSTP_2027 = "cabinet_departure_no_ostp_2027"
PREDICATE_CABINET_WITH_OSTP = "cabinet_departure_with_ostp"
PREDICATE_UNKNOWN = "unknown_predicate"

SCOPE_SINGLE_OFFICEHOLDER = "single_officeholder"
SCOPE_CABINET_NO_OSTP = "confirmed_cabinet_no_ostp"
SCOPE_CABINET_WITH_OSTP = "official_cabinet_with_ostp"
SCOPE_UNKNOWN = "unknown_scope"

EDITION_TRUMP_47 = "trump_47_admin"

CATEGORY_GATE = frozenset({"politics", "geopolitics"})
DEPARTURE_ALLOWED_CATEGORIES = frozenset({"politics", "culture", "geopolitics", "economics"})
DEPARTURE_STRICT_CONFLICT_CATEGORIES = frozenset(
    {
        "sports",
        "football",
        "basketball",
        "nfl",
        "nba",
        "mlb",
        "nhl",
        "soccer",
        "tennis",
        "golf",
        "ufc",
        "boxing",
        "f1",
        "college_football",
        "college_basketball",
        "weather",
    }
)


# ---------------------------------------------------------------------------
# #11040 DepartureSubject + #5318 rule registrations (departure-story@1).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DepartureSubject:
    subject: str
    edition: int
    person: str
    surname: str
    office_terms: tuple[str, ...]
    role_display: str
    display_name: str
    tenure_start: date
    kalshi_ticker_prefixes: tuple[str, ...] = ()

    @property
    def person_pg(self) -> str:
        parts = [re.escape(p) for p in self.person.split() if p]
        return r"\y" + r"\s+".join(parts) + r"\y"


KATIE_ZACHARIA_PRESS_SECRETARY = DepartureSubject(
    subject="katie-zacharia-press-secretary",
    edition=2026,
    person="Katie Zacharia",
    surname="Zacharia",
    office_terms=("press secretary",),
    role_display="White House press secretary",
    display_name="Katie Zacharia",
    tenure_start=date(2026, 10, 9),
    kalshi_ticker_prefixes=("KXZACHARIAOUT", "KXPRESSSECOUT"),
)

PETE_HEGSETH_DEFENSE_SECRETARY = DepartureSubject(
    subject="pete-hegseth-defense-secretary",
    edition=2025,
    person="Pete Hegseth",
    surname="Hegseth",
    office_terms=("secretary of defense", "defense secretary", "secretary of war"),
    role_display="Secretary of Defense",
    display_name="Pete Hegseth",
    tenure_start=date(2025, 1, 25),
    kalshi_ticker_prefixes=("KXHEGSETHOUT", "KXHEGSETHANNOUNCEOUT"),
)

DEPARTURE_SUBJECTS: dict[str, DepartureSubject] = {
    KATIE_ZACHARIA_PRESS_SECRETARY.subject: KATIE_ZACHARIA_PRESS_SECRETARY,
    PETE_HEGSETH_DEFENSE_SECRETARY.subject: PETE_HEGSETH_DEFENSE_SECRETARY,
}


#: #5318 rule registrations keyed by (provider_kind, provider_key).
REGISTRATIONS: dict[tuple[str, str], dict[str, Any]] = {
    ("kalshi_series", "KXZACHARIAOUT"): {
        "predicate": "vacated",
        "basis": "rules",
        "quote": (
            "Katie Zacharia must have an actual departure date and vacate the role "
            "within the time period."
        ),
        "rules_sha256": "2d191cebfb1cadff2e4aa8cc736e035dcc26c5ff76a3fedd6603893dfa2a71a1",
    },
    ("polymarket_event", "1183118"): {
        "predicate": "announced",
        "basis": "rules",
        "quote": (
            'An announcement of Katie Zacharia\'s resignation/removal by this market\'s '
            'end date will immediately resolve this market to "Yes", regardless of when '
            "the announced resignation/removal goes into effect."
        ),
        "rules_sha256": "cc46e9a2b8bf04167ca6c9374555c00aa0e6ee4d87cd98d59a19053ee4a11269",
    },
}


# ---------------------------------------------------------------------------
# Clause patterns for departure-story@1.
# ---------------------------------------------------------------------------

_DEPARTURE_RE = re.compile(
    r"\b(out as|leave|leaves|leaving|resign\w*|step\w* down|depart\w*|"
    r"removed|fired|dismissed|replaced|vacate\w*|cease\w* to be|no longer)\b",
    re.I,
)
_ROLE_FRAME_RE = re.compile(r"\b(out as|resign\w* as|step\w* down as|leave\w* as)\s+([^?.,;]+)", re.I)
_IN_ROLE_RE = re.compile(r"\bgive another press briefing\b", re.I)
_AFTER_ROLE_RE = re.compile(r"\bgiven a new role in the [a-z ]+ administration\b", re.I)
_ANNOUNCED_TITLE_RE = re.compile(
    r"\b(departure announced|announces? (?:her|his|their)? ?(?:resignation|departure))\b",
    re.I,
)
_WINDOW_TITLE_RE = re.compile(
    r"\b(?:in|during)\s+(?:january|february|march|april|may|june|july|august|"
    r"september|october|november|december|q[1-4]|20\d\d)\b",
    re.I,
)
_LEFT_ADMIN_TITLE_RE = re.compile(
    r"\bleave\w*\s+the\s+(?:[a-z]+\s+)?administration\b",
    re.I,
)


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _metadata(obj: Any) -> Mapping[str, Any]:
    meta = _get(obj, "market_metadata")
    return meta if isinstance(meta, Mapping) else {}


def _full_name_re(person: str) -> re.Pattern[str]:
    parts = [re.escape(p) for p in person.split() if p]
    return re.compile(r"\b" + r"\s+".join(parts) + r"\b", re.I)


def _surname_prefix_re(surname: str) -> re.Pattern[str]:
    return re.compile(r"\b" + re.escape(surname) + r"\w*\b", re.I)


def _office_in(text: str, office_terms: tuple[str, ...]) -> bool:
    low = text.lower()
    return any(term.lower() in low for term in office_terms)


def _outcome_texts(row: Any) -> list[str]:
    names = _get(row, "outcome_names")
    if isinstance(names, (list, tuple)):
        return [str(x) for x in names if x is not None]
    outcomes = _get(row, "outcomes")
    if isinstance(outcomes, (list, tuple)):
        out: list[str] = []
        for o in outcomes:
            n = _get(o, "name")
            if n is not None:
                out.append(str(n))
        return out
    return []


def _ends_utc(row: Any) -> tuple[Optional[date], Optional[str]]:
    deadline = _get(row, "deadline")
    if isinstance(deadline, Mapping):
        inst = deadline.get("instant")
        if isinstance(inst, Mapping) and isinstance(inst.get("utc"), str):
            raw = inst["utc"]
            return date.fromisoformat(raw[:10]), raw
    res = _get(row, "resolution_date")
    if isinstance(res, datetime):
        dt = res if res.tzinfo is not None else res.replace(tzinfo=timezone.utc)
        return dt.date(), dt.isoformat()
    if isinstance(res, str) and len(res) >= 10:
        try:
            return date.fromisoformat(res[:10]), res
        except ValueError:
            return None, None
    return None, None


def _registration_key(row: Any) -> Optional[tuple[str, str]]:
    rk = _get(row, "registration_key")
    if isinstance(rk, (list, tuple)) and len(rk) == 2:
        return (str(rk[0]), str(rk[1]))
    meta = _metadata(row)
    source = str(_get(row, "source") or "").lower()
    ext = str(_get(row, "external_id") or "").upper()
    series = str(
        meta.get("series_ticker")
        or meta.get("kalshi_series_ticker")
        or meta.get("series")
        or ""
    ).upper()
    if not series and (source == "kalshi" or ext.startswith("KX")) and ext:
        series = ext.split("-", 1)[0]
    if series and ("kalshi_series", series) in REGISTRATIONS:
        return ("kalshi_series", series)
    pm_ev = str(meta.get("polymarket_event_id") or "").strip()
    if not pm_ev:
        gid = str(_get(row, "group_id") or meta.get("group_id") or "").strip()
        if gid.startswith("polymarket:"):
            pm_ev = gid.split(":", 1)[1].strip()
    if pm_ev and ("polymarket_event", pm_ev) in REGISTRATIONS:
        return ("polymarket_event", pm_ev)
    return None


def departure_predicate(row: Any) -> dict[str, Any]:
    """Classify a departure market's settlement predicate from #5318 registration,
    explicit title literal, or stored rules text (never from venue name alone)."""
    key = _registration_key(row)
    if key and key in REGISTRATIONS:
        reg = REGISTRATIONS[key]
        return {
            "predicate": reg["predicate"],
            "basis": reg["basis"],
            "registration": list(key),
            "quote": reg["quote"],
            "rules_sha256": reg["rules_sha256"],
        }
    name = str(_get(row, "name") or "")
    if _ANNOUNCED_TITLE_RE.search(name) and not _WINDOW_TITLE_RE.search(name):
        return {
            "predicate": "announced",
            "basis": "title_literal",
            "title": name,
        }
    if _LEFT_ADMIN_TITLE_RE.search(name):
        return {
            "predicate": "left_administration",
            "basis": "title_literal",
            "title": name,
        }
    rules_text = _extract_rules_text(row)
    if rules_text:
        pred_cls, _scope, _edge = _classify_katie_zacharia_predicate(rules_text)
        if pred_cls == PREDICATE_ANNOUNCEMENT:
            return {"predicate": "announced", "basis": "rules_text"}
        if pred_cls == PREDICATE_ACTUAL_DEPARTURE:
            return {"predicate": "vacated", "basis": "rules_text"}
    return {
        "predicate": "unknown",
        "basis": "rules_not_read",
    }


@dataclass(frozen=True)
class SubjectDecisionResult:
    outcome: str
    reason: str
    section: Optional[str]
    evidence: list[dict[str, Any]]
    rule_version: str = RULE_VERSION

    @property
    def edge_class(self) -> Optional[str]:
        return self.section

    @property
    def admitted(self) -> bool:
        return self.outcome == "admitted"

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome,
            "reason": self.reason,
            "section": self.section,
            "evidence": list(self.evidence),
            "rule_version": self.rule_version,
        }


def decide_departure_subject(subject: DepartureSubject, row: Any) -> SubjectDecisionResult:
    """Evaluate ``row`` against ``subject`` under ``departure-story@1``."""
    evidence: list[dict[str, Any]] = []
    name = str(_get(row, "name") or "")
    full_re = _full_name_re(subject.person)
    surname_re = _surname_prefix_re(subject.surname)
    outcome_blob = " | ".join(_outcome_texts(row))

    # Clause 1 — person in the market's own title (never outcome-only or substring).
    if not full_re.search(name):
        evidence.append({"clause": "person", "result": "fail", "input": name})
        if full_re.search(outcome_blob) or re.search(
            r"\b" + re.escape(subject.surname) + r"\b", outcome_blob, re.I
        ):
            return SubjectDecisionResult("excluded", NAME_ONLY_MENTION, None, evidence)
        if surname_re.search(name) or surname_re.search(outcome_blob):
            reason = (
                NOT_THIS_SUBJECT_REASON
                if re.search(r"\b" + re.escape(subject.surname) + r"\b", name, re.I)
                else "lexical_false_friend"
            )
            return SubjectDecisionResult("excluded", reason, None, evidence)
        return SubjectDecisionResult("excluded", NOT_THIS_SUBJECT_REASON, None, evidence)
    evidence.append({"clause": "person", "result": "pass", "input": subject.person})

    # Clause 2 — second-signal category gate.
    cat = (_get(row, "llm_sport_category") or "").strip().lower() or None
    if cat not in CATEGORY_GATE:
        evidence.append({"clause": "category", "result": "fail", "input": cat})
        return SubjectDecisionResult("excluded", "wrong_category", None, evidence)
    evidence.append({"clause": "category", "result": "pass", "input": cat})

    # Clause 3 — relation & office.
    office_named = _office_in(name, subject.office_terms)
    framed = _ROLE_FRAME_RE.search(name)
    if framed and not _office_in(framed.group(2), subject.office_terms):
        evidence.append({"clause": "relation", "result": "other_office", "input": name})
        return SubjectDecisionResult("excluded", OTHER_OFFICE, None, evidence)

    if _DEPARTURE_RE.search(name):
        relation = "departure"
    elif _IN_ROLE_RE.search(name) and office_named:
        relation = "in_role"
    elif _AFTER_ROLE_RE.search(name):
        relation = "after_role"
    else:
        evidence.append({"clause": "relation", "result": "fail", "input": name})
        return SubjectDecisionResult("excluded", NOT_THIS_STORY, None, evidence)
    evidence.append(
        {
            "clause": "relation",
            "result": relation,
            "office": "named" if office_named else "implied",
        }
    )

    # Clause 4 — tenure window (only end before tenure_start excludes; creation before start does not).
    ends_date, ends_raw = _ends_utc(row)
    created_at = _get(row, "created_at")
    if isinstance(created_at, datetime):
        created_at = created_at.isoformat()
    if ends_date is not None and ends_date < subject.tenure_start:
        evidence.append(
            {
                "clause": "tenure",
                "result": "ended_before_tenure",
                "ends": ends_raw,
                "created_at": created_at,
            }
        )
        return SubjectDecisionResult("excluded", "other_edition", None, evidence)
    evidence.append(
        {
            "clause": "tenure",
            "result": "pass" if ends_date is not None else "deadline_not_in_evidence",
            "ends": ends_raw,
            "created_at": created_at,
        }
    )

    # Clause 5 — section from settlement predicate.
    if relation == "in_role":
        return SubjectDecisionResult("admitted", ADMITTED_SUBJECT_RELATION, "side_question", evidence)
    if relation == "after_role":
        return SubjectDecisionResult("admitted", ADMITTED_SUBJECT_RELATION, "after_role", evidence)

    pred = departure_predicate(row)
    evidence.append({"clause": "predicate", "result": pred["predicate"], **pred})
    section = {
        "announced": "departure_announced",
        "vacated": "departure_vacated",
        "left_administration": "departure_left_administration",
        "unknown": "departure_rules_unread",
    }[pred["predicate"]]
    return SubjectDecisionResult("admitted", ADMITTED_SUBJECT_RELATION, section, evidence)


NOT_THIS_SUBJECT_REASON = "not_this_subject"


# ---------------------------------------------------------------------------
# DepartureStorySpec + evidence extraction + equivalence (with F1 fix).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DepartureStorySpec:
    subject: str
    story_key: str
    display_name: str
    shared_question: str
    subject_key: str
    role_key: str
    edition_key: str
    rule_version: str
    kalshi_ticker_prefixes: tuple[str, ...]
    name_entity_pg: str
    departure_subject: Optional[DepartureSubject] = None


KATIE_ZACHARIA_ENTITY_PG = KATIE_ZACHARIA_PRESS_SECRETARY.person_pg
PETE_HEGSETH_ENTITY_PG = PETE_HEGSETH_DEFENSE_SECRETARY.person_pg
TRUMP_CABINET_ENTITY_PG = r"\y(trump(?:'s)?\s+cabinet|cabinet\s+of\s+donald\s+trump)\y"

KATIE_ZACHARIA_DEPARTURE_SPEC = DepartureStorySpec(
    subject="katie-zacharia-press-secretary",
    story_key="story:katie_zacharia_departure",
    display_name="Katie Zacharia",
    shared_question="Will Katie Zacharia leave as White House Press Secretary?",
    subject_key="katie_zacharia",
    role_key="white_house_press_secretary",
    edition_key=EDITION_TRUMP_47,
    rule_version=DEPARTURE_STORY_RULE_VERSION,
    kalshi_ticker_prefixes=("KXZACHARIAOUT", "KXPRESSSECOUT"),
    name_entity_pg=KATIE_ZACHARIA_ENTITY_PG,
    departure_subject=KATIE_ZACHARIA_PRESS_SECRETARY,
)

PETE_HEGSETH_DEPARTURE_SPEC = DepartureStorySpec(
    subject="pete-hegseth-defense-secretary",
    story_key="story:pete_hegseth_departure",
    display_name="Pete Hegseth",
    shared_question="Will Pete Hegseth leave as Secretary of Defense?",
    subject_key="pete_hegseth",
    role_key="secretary_of_defense",
    edition_key=EDITION_TRUMP_47,
    rule_version=DEPARTURE_STORY_RULE_VERSION,
    kalshi_ticker_prefixes=("KXHEGSETHOUT", "KXHEGSETHANNOUNCEOUT"),
    name_entity_pg=PETE_HEGSETH_ENTITY_PG,
    departure_subject=PETE_HEGSETH_DEFENSE_SECRETARY,
)

TRUMP_CABINET_DEPARTURE_SPEC = DepartureStorySpec(
    subject="trump-cabinet-departure",
    story_key="story:trump_cabinet_departure",
    display_name="Trump Cabinet Departures",
    shared_question="Who will leave the Trump Cabinet next?",
    subject_key="trump_cabinet",
    role_key="us_cabinet_member",
    edition_key=EDITION_TRUMP_47,
    rule_version=DEPARTURE_STORY_RULE_VERSION,
    kalshi_ticker_prefixes=("KXCABOUT", "KXCABINETOUT"),
    name_entity_pg=TRUMP_CABINET_ENTITY_PG,
    departure_subject=None,
)

DEPARTURE_SPECS_BY_SUBJECT: dict[str, DepartureStorySpec] = {
    KATIE_ZACHARIA_DEPARTURE_SPEC.subject: KATIE_ZACHARIA_DEPARTURE_SPEC,
    "katie-zacharia-departure": KATIE_ZACHARIA_DEPARTURE_SPEC,
    PETE_HEGSETH_DEPARTURE_SPEC.subject: PETE_HEGSETH_DEPARTURE_SPEC,
    TRUMP_CABINET_DEPARTURE_SPEC.subject: TRUMP_CABINET_DEPARTURE_SPEC,
}

DEPARTURE_SPECS_BY_STORY_KEY: dict[str, DepartureStorySpec] = {
    KATIE_ZACHARIA_DEPARTURE_SPEC.story_key: KATIE_ZACHARIA_DEPARTURE_SPEC,
    PETE_HEGSETH_DEPARTURE_SPEC.story_key: PETE_HEGSETH_DEPARTURE_SPEC,
    TRUMP_CABINET_DEPARTURE_SPEC.story_key: TRUMP_CABINET_DEPARTURE_SPEC,
}


# ---------------------------------------------------------------------------
# Lexical & semantic patterns for rules text and horizon parsing.
# ---------------------------------------------------------------------------

_ZACHARIA_FALSE_FRIEND_RE = re.compile(
    r"\b(?:zachariah?\s+branch|zacharia\s+stadium|zachariah\s+prophet)\b",
    re.IGNORECASE,
)
_ZACHARIA_BARE_LAST_NAME_RE = re.compile(r"\bzachariah?\b", re.IGNORECASE)
_KATIE_ZACHARIA_SUBJECT_RE = re.compile(r"\bkatie\s+zacharia\b", re.IGNORECASE)
_PRESS_SECRETARY_ROLE_RE = re.compile(
    r"\b(?:white\s+house\s+)?press\s+secretary\b", re.IGNORECASE
)
_PETE_HEGSETH_SUBJECT_RE = re.compile(r"\bpete\s+hegseth\b", re.IGNORECASE)
_DEFENSE_SECRETARY_ROLE_RE = re.compile(
    r"\b(?:secretary\s+of\s+defense|defense\s+secretary|secretary\s+of\s+war)\b",
    re.IGNORECASE,
)

_CABINET_FALSE_FRIEND_RE = re.compile(
    r"\b(?:uk\s+(?:shadow\s+)?cabinet|shadow\s+cabinet|british\s+cabinet|"
    r"canadian\s+cabinet|australian\s+cabinet|israeli\s+cabinet|war\s+cabinet|"
    r"kitchen\s+cabinet|file\s+cabinet|medicine\s+cabinet|cabinet\s+maker|"
    r"liquor\s+cabinet|display\s+cabinet|arcade\s+cabinet)\b",
    re.IGNORECASE,
)
_TRUMP_CABINET_SUBJECT_RE = re.compile(
    r"\b(?:trump(?:'s)?\s+cabinet|cabinet\s+of\s+(?:president\s+)?(?:donald\s+)?trump)\b",
    re.IGNORECASE,
)
_OTHER_ADMIN_CABINET_RE = re.compile(
    r"\b(?:biden(?:'s)?\s+cabinet|obama(?:'s)?\s+cabinet|bush(?:'s)?\s+cabinet|"
    r"first\s+trump\s+(?:administration|cabinet|term)|"
    r"trump(?:'s)?\s+first\s+(?:administration|cabinet|term)|"
    r"in\s+(?:2017|2018|2019|2020))\b",
    re.IGNORECASE,
)
_OTHER_EDITION_YEAR_RE = re.compile(r"\b(201[6-9]|202[0-4])\b")

_SPEECH_OR_MENTION_RE = re.compile(
    r"\b(?:what\s+will\s+[^?]*\b(?:say|mention|tweet|post|wear)\b|"
    r"will\s+[^?]*\b(?:say|mention|utter)\b|"
    r"how\s+many\s+times\s+will\s+[^?]*\bsay\b|"
    r"words?\s+(?:said|spoken|mentioned)|"
    r"hold\s+a\s+(?:cabinet\s+meeting|press\s+briefing)|"
    r"attend\s+the\s+cabinet\s+meeting)\b",
    re.IGNORECASE,
)
_CONFIRMATION_OR_APPOINTMENT_ONLY_RE = re.compile(
    r"\b(?:who\s+will\s+be\s+(?:confirmed|appointed|nominated)\b|"
    r"will\s+[^?]*\bbe\s+(?:confirmed|appointed|nominated)\s+(?:to|as)\b)",
    re.IGNORECASE,
)
_SPEECH_TICKER_PREFIXES = ("KXTRUMPSAY", "KXMENTION", "KXSPEECH", "KXBRIEFING")

_DEPARTURE_ACTION_RE = re.compile(
    r"\b(?:leave|leaves|leaving|left|out\s+as|out\s+of|depart|departs|departing|"
    r"departure|step\s+down|steps\s+down|stepping\s+down|resign|resigns|resigning|"
    r"resignation|removed|fired|dismissed|replaced|vacate|vacates|cease\s+to\s+be|"
    r"no\s+longer\s+(?:serve|serving|hold|holding)|first\s+to\s+leave|next\s+to\s+leave|"
    r"exit|exits|exiting)\b",
    re.IGNORECASE,
)

# Predicate classification patterns on stored rules text.
# F1 fix: Polymarket's verbatim rules say:
# 'An announcement of Katie Zacharia\'s resignation/removal by this market\'s end
# date will immediately resolve this market to "Yes", regardless of when the
# announced resignation/removal goes into effect.'
# and also mention "ceases to be White House Press Secretary" in the lead-in.
# Announcement-included must match "an announcement of <person>'s resignation/removal"
# and win whenever announcement is not negated.
_ANNOUNCEMENT_NEGATED_RE = re.compile(
    r"\b(?:announcement\s+(?:alone\s+|of\s+a\s+future\s+departure\s+)?(?:does\s+not|will\s+not|is\s+not\s+sufficient)|"
    r"merely\s+announcing\s+[^.]*does\s+not|"
    r"must\s+have\s+an\s+actual\s+departure\s+date\s+and\s+vacate\s+the\s+role)\b",
    re.IGNORECASE,
)
_ANNOUNCEMENT_INCLUDED_RE = re.compile(
    r"\b(?:an?\s+announcement\s+of\s+[^.]{0,120}?\b(?:resignation|removal|departure|retirement|exit)\b|"
    r"announces?\s+(?:she|he|they|an?\s+intention\s+to)?\s*(?:will\s+)?"
    r"(?:leave|depart|resign|step\s+down|vacate|retire)|"
    r"announces?\s+(?:a|an|her|his|their)?\s*(?:departure|resignation|retirement|exit)|"
    r"receives?\s+a\s+departure\s+notice|"
    r"submits?\s+(?:a|her|his|their)\s+resignation|"
    r"leaves?,?\s+is\s+removed\s+from,?\s+or\s+announces?|"
    r"official\s+announcement\s+of\s+(?:her|his|their|a)?\s*(?:departure|resignation))\b",
    re.IGNORECASE,
)
_ACTUAL_DEPARTURE_RE = re.compile(
    r"\b(?:must\s+have\s+an\s+actual\s+departure\s+date\s+and\s+vacate|"
    r"ceases?\s+to\s+(?:be|hold|serve)|"
    r"no\s+longer\s+(?:holds?|serves?\s+in|occupies)\s+(?:the\s+)?(?:office|position|role)|"
    r"vacates?\s+(?:the\s+|her\s+|his\s+|their\s+)?(?:office|position|role)|"
    r"leaves?\s+office\s+before|"
    r"actually\s+(?:leaves?|departs?|vacates?)\s+(?:office|the\s+position))\b",
    re.IGNORECASE,
)
_CABINET_NO_OSTP_RE = re.compile(
    r"\b(?:does\s+not\s+include\s+(?:the\s+)?(?:director\s+of\s+(?:the\s+)?)?"
    r"(?:office\s+of\s+science\s+and\s+technology\s+policy|ostp)|"
    r"exclud(?:es?|ing)\s+(?:the\s+)?(?:director\s+of\s+)?ostp|"
    r"senate[- ]confirmed\s+heads?\s+of\s+the\s+15\s+executive\s+departments)\b",
    re.IGNORECASE,
)
_CABINET_WITH_OSTP_RE = re.compile(
    r"\b(?:includ(?:es?|ing)\s+(?:the\s+)?(?:director\s+of\s+(?:the\s+)?)?"
    r"(?:office\s+of\s+science\s+and\s+technology\s+policy|ostp)|"
    r"cabinet[- ]rank\s+officials?\s+including\s+ostp|"
    r"official\s+white\s+house\s+cabinet\s+roster\s+including\s+ostp)\b",
    re.IGNORECASE,
)

# Horizon parsing patterns.
_UNSUPPORTED_VAGUE_HORIZON_RE = re.compile(
    r"\b(?:someday|eventually|at\s+some\s+point|without\s+deadline|open[- ]ended)\b",
    re.IGNORECASE,
)
_MONTHS: Mapping[str, int] = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}
_MONTH_PATTERN = "|".join(sorted(_MONTHS, key=len, reverse=True))
_PREP_DATE_RE = re.compile(
    rf"\b(before|prior\s+to|by|on\s+or\s+before|through|until)\s+"
    rf"({_MONTH_PATTERN})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(20\d{{2}}))?\b",
    re.IGNORECASE,
)
_BEFORE_YEAR_RE = re.compile(r"\bbefore\s+(20\d{2})\b", re.IGNORECASE)
_IN_YEAR_RE = re.compile(r"\b(?:in|during)\s+(20\d{2})\b", re.IGNORECASE)
_KALSHI_TICKER_DATE_RE = re.compile(
    r"-(\d{2})(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)(\d{2})(?:-|$)",
    re.IGNORECASE,
)


def _aware(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _extract_rules_text(market: Any) -> str:
    meta = _metadata(market)
    parts: list[str] = []
    for raw in (
        _get(market, "description"),
        meta.get("rules_primary"),
        meta.get("rules_secondary"),
        meta.get("resolution_rules"),
        meta.get("description"),
    ):
        if isinstance(raw, str) and raw.strip():
            text = raw.strip()
            if text not in parts:
                parts.append(text)
    return "\n".join(parts)


def _extract_custom_strike(market: Any) -> str:
    meta = _metadata(market)
    strike = meta.get("custom_strike")
    parts: list[str] = []
    if isinstance(strike, Mapping):
        for v in strike.values():
            if isinstance(v, str) and v.strip():
                parts.append(v.strip())
    elif isinstance(strike, str) and strike.strip():
        parts.append(strike.strip())
    for key in ("subtitle", "yes_sub_title", "group_item_title"):
        val = meta.get(key)
        if isinstance(val, str) and val.strip():
            parts.append(val.strip())
    return " ".join(parts)


def _normalize_horizon(
    name: str,
    rules_text: str,
    external_id: str,
    resolution_date: Optional[datetime],
) -> tuple[Optional[str], str]:
    """Return ``(normalized_yyyy_mm_dd, horizon_source)`` or ``(None, reason)``."""
    if _UNSUPPORTED_VAGUE_HORIZON_RE.search(name):
        return None, "unsupported_vague_horizon"

    for source_label, text_blob in (("name", name), ("rules", rules_text)):
        if not text_blob:
            continue
        m = _PREP_DATE_RE.search(text_blob)
        if m and m.group(4):
            prep = re.sub(r"\s+", " ", m.group(1).strip().lower())
            month = _MONTHS[m.group(2).lower().rstrip(".")]
            day = int(m.group(3))
            year = int(m.group(4))
            try:
                parsed = date(year, month, day)
            except ValueError:
                continue
            if prep in ("before", "prior to") and day == 1:
                parsed = parsed - timedelta(days=1)
            return parsed.isoformat(), f"{source_label}_date"

        m_before_yr = _BEFORE_YEAR_RE.search(text_blob)
        if m_before_yr:
            year = int(m_before_yr.group(1)) - 1
            return date(year, 12, 31).isoformat(), f"{source_label}_before_year"

        m_in_yr = _IN_YEAR_RE.search(text_blob)
        if m_in_yr:
            year = int(m_in_yr.group(1))
            return date(year, 12, 31).isoformat(), f"{source_label}_in_year"

    m_ticker = _KALSHI_TICKER_DATE_RE.search(external_id or "")
    if m_ticker:
        year = 2000 + int(m_ticker.group(1))
        month = _MONTHS[m_ticker.group(2).lower()]
        day = int(m_ticker.group(3))
        try:
            parsed = date(year, month, day)
            if day == 1:
                parsed = parsed - timedelta(days=1)
            return parsed.isoformat(), "ticker_date"
        except ValueError:
            pass

    if resolution_date is not None:
        res_date = resolution_date.date()
        if res_date.day == 1 and res_date.month in (1, 4, 7, 11):
            res_date = res_date - timedelta(days=1)
        return res_date.isoformat(), "resolution_date"

    return None, "missing_horizon"


@dataclass(frozen=True)
class DepartureEvidence:
    spec_subject: Optional[str]
    subject_key: Optional[str]
    role_key: Optional[str]
    edition_key: Optional[str]
    has_departure_framing: bool
    predicate_class: str
    population_scope: str
    horizon_key: Optional[str]
    horizon_source: str
    edge_class: str
    rules_present: bool
    false_friend: Optional[str]
    unrelated_mention: Optional[str]
    other_edition_token: Optional[str]


def _classify_katie_zacharia_predicate(
    rules_text: str, market: Any = None
) -> tuple[str, str, str]:
    """Return ``(predicate_class, population_scope, edge_class)``."""
    if market is not None:
        reg_key = _registration_key(market)
        if reg_key and reg_key in REGISTRATIONS:
            reg_pred = REGISTRATIONS[reg_key]["predicate"]
            if reg_pred == "announced":
                return PREDICATE_ANNOUNCEMENT, SCOPE_SINGLE_OFFICEHOLDER, "title"
            if reg_pred == "vacated":
                return PREDICATE_ACTUAL_DEPARTURE, SCOPE_SINGLE_OFFICEHOLDER, "advancement"
        name = str(_get(market, "name") or "")
        if _LEFT_ADMIN_TITLE_RE.search(name):
            return (
                PREDICATE_LEFT_ADMINISTRATION,
                SCOPE_SINGLE_OFFICEHOLDER,
                "side_question",
            )
        if _ANNOUNCED_TITLE_RE.search(name) and not _WINDOW_TITLE_RE.search(name):
            return PREDICATE_ANNOUNCEMENT, SCOPE_SINGLE_OFFICEHOLDER, "title"

    if not rules_text.strip():
        return PREDICATE_UNKNOWN, SCOPE_UNKNOWN, "side_question"
    announcement_negated = bool(_ANNOUNCEMENT_NEGATED_RE.search(rules_text))
    has_announcement = bool(_ANNOUNCEMENT_INCLUDED_RE.search(rules_text)) and not announcement_negated
    has_actual = bool(_ACTUAL_DEPARTURE_RE.search(rules_text)) or announcement_negated
    if has_announcement:
        return PREDICATE_ANNOUNCEMENT, SCOPE_SINGLE_OFFICEHOLDER, "title"
    if has_actual:
        return PREDICATE_ACTUAL_DEPARTURE, SCOPE_SINGLE_OFFICEHOLDER, "advancement"
    return PREDICATE_UNKNOWN, SCOPE_UNKNOWN, "side_question"


def _classify_trump_cabinet_predicate(rules_text: str) -> tuple[str, str, str]:
    """Return ``(predicate_class, population_scope, edge_class)``."""
    if not rules_text.strip():
        return PREDICATE_UNKNOWN, SCOPE_UNKNOWN, "side_question"
    if _CABINET_NO_OSTP_RE.search(rules_text):
        return PREDICATE_CABINET_NO_OSTP_2027, SCOPE_CABINET_NO_OSTP, "title"
    if _CABINET_WITH_OSTP_RE.search(rules_text):
        return PREDICATE_CABINET_WITH_OSTP, SCOPE_CABINET_WITH_OSTP, "advancement"
    announcement_negated = bool(_ANNOUNCEMENT_NEGATED_RE.search(rules_text))
    if _ANNOUNCEMENT_INCLUDED_RE.search(rules_text) and not announcement_negated:
        return PREDICATE_CABINET_NO_OSTP_2027, SCOPE_CABINET_NO_OSTP, "title"
    if _ACTUAL_DEPARTURE_RE.search(rules_text) or announcement_negated:
        return PREDICATE_CABINET_WITH_OSTP, SCOPE_CABINET_WITH_OSTP, "advancement"
    return PREDICATE_UNKNOWN, SCOPE_UNKNOWN, "side_question"


def extract_departure_evidence(
    spec: DepartureStorySpec,
    market: Any,
) -> DepartureEvidence:
    """Extract structured meaning & rule evidence for ``market`` against ``spec``."""
    name = str(_get(market, "name") or "")
    source = str(_get(market, "source") or "").lower()
    external_id = str(_get(market, "external_id") or "")
    upper_ext = external_id.upper()
    meta = _metadata(market)
    event_title = str(meta.get("event_title") or "")
    custom_strike = _extract_custom_strike(market)
    rules_text = _extract_rules_text(market)
    resolution_date = _aware(_get(market, "resolution_date"))
    if resolution_date is None:
        ends_d, _ = _ends_utc(market)
        if ends_d is not None:
            resolution_date = datetime(ends_d.year, ends_d.month, ends_d.day, tzinfo=timezone.utc)
    combined_title = " ".join(p for p in (name, event_title, custom_strike) if p)

    false_friend: Optional[str] = None
    unrelated_mention: Optional[str] = None
    other_edition_token: Optional[str] = None
    subject_key: Optional[str] = None
    role_key: Optional[str] = None
    edition_key: Optional[str] = EDITION_TRUMP_47

    has_departure = (
        bool(_DEPARTURE_ACTION_RE.search(combined_title))
        or bool(_IN_ROLE_RE.search(name))
        or bool(_AFTER_ROLE_RE.search(name))
        or (
            source == "kalshi"
            and any(upper_ext.startswith(prefix) for prefix in spec.kalshi_ticker_prefixes)
        )
    )

    if any(upper_ext.startswith(p) for p in _SPEECH_TICKER_PREFIXES) or (
        _SPEECH_OR_MENTION_RE.search(name) and not _DEPARTURE_ACTION_RE.search(name)
    ):
        unrelated_mention = "speech_or_mention_market"
    elif (
        _CONFIRMATION_OR_APPOINTMENT_ONLY_RE.search(name)
        and not _DEPARTURE_ACTION_RE.search(name)
        and not _AFTER_ROLE_RE.search(name)
    ):
        unrelated_mention = "confirmation_or_appointment_market"

    if spec.departure_subject is not None:
        subj = spec.departure_subject
        subj_decision = decide_departure_subject(subj, market)
        if subj_decision.reason == "lexical_false_friend":
            false_friend = "lexical_false_friend"
        elif subj_decision.reason in (NAME_ONLY_MENTION, NOT_THIS_STORY, OTHER_OFFICE):
            if unrelated_mention is None:
                unrelated_mention = subj_decision.reason
        elif subj_decision.reason == "other_edition":
            other_edition_token = "ended_before_tenure"
            edition_key = "other_edition:ended_before_tenure"

        m_old = _OTHER_EDITION_YEAR_RE.search(name)
        if m_old:
            other_edition_token = m_old.group(1)
            edition_key = f"other_edition:{other_edition_token}"

        is_kalshi_ticker = source == "kalshi" and any(
            upper_ext.startswith(prefix) for prefix in spec.kalshi_ticker_prefixes
        )
        full_re = _full_name_re(subj.person)
        has_person = bool(full_re.search(combined_title)) or (
            is_kalshi_ticker and subj.surname.lower() in (upper_ext.lower() + " " + rules_text.lower())
        )
        has_role = (
            _office_in(combined_title, subj.office_terms)
            or _office_in(rules_text, subj.office_terms)
            or is_kalshi_ticker
            or bool(_AFTER_ROLE_RE.search(name))
            or bool(_LEFT_ADMIN_TITLE_RE.search(name))
            or bool(_ANNOUNCED_TITLE_RE.search(name))
        )
        if false_friend is None and unrelated_mention is None and has_person and has_role:
            subject_key = spec.subject_key
            role_key = spec.role_key

        predicate_class, population_scope, edge_class = _classify_katie_zacharia_predicate(
            rules_text, market
        )
        if subj_decision.admitted and subj_decision.section in ("side_question", "after_role"):
            edge_class = "side_question"
            predicate_class = subj_decision.section

    else:
        ff_match = _CABINET_FALSE_FRIEND_RE.search(combined_title)
        if ff_match:
            false_friend = ff_match.group(0)
        else:
            m_other_admin = _OTHER_ADMIN_CABINET_RE.search(combined_title)
            if m_other_admin:
                other_edition_token = m_other_admin.group(0)
                edition_key = f"other_edition:{other_edition_token}"
            is_cab_ticker = source == "kalshi" and upper_ext.startswith("KXCABOUT")
            has_trump_cabinet = bool(_TRUMP_CABINET_SUBJECT_RE.search(combined_title)) or is_cab_ticker
            if has_trump_cabinet:
                subject_key = spec.subject_key
                role_key = spec.role_key
            elif "trump" in combined_title.lower() and unrelated_mention is None and not has_departure:
                unrelated_mention = "trump_mention_without_cabinet_departure"

        predicate_class, population_scope, edge_class = _classify_trump_cabinet_predicate(
            rules_text
        )

    horizon_key, horizon_source = _normalize_horizon(
        name=name,
        rules_text=rules_text,
        external_id=external_id,
        resolution_date=resolution_date,
    )

    return DepartureEvidence(
        spec_subject=spec.subject if subject_key == spec.subject_key else None,
        subject_key=subject_key,
        role_key=role_key,
        edition_key=edition_key,
        has_departure_framing=has_departure,
        predicate_class=predicate_class,
        population_scope=population_scope,
        horizon_key=horizon_key,
        horizon_source=horizon_source,
        edge_class=edge_class,
        rules_present=bool(rules_text.strip()) or (_registration_key(market) in REGISTRATIONS),
        false_friend=false_friend,
        unrelated_mention=unrelated_mention,
        other_edition_token=other_edition_token,
    )


def extract_any_departure_evidence(market: Any) -> Optional[DepartureEvidence]:
    """Return the matching ``DepartureEvidence`` if ``market`` matches any registered
    departure story spec, or ``None`` if it belongs to none."""
    seen: set[str] = set()
    for spec in DEPARTURE_SPECS_BY_SUBJECT.values():
        if spec.subject_key in seen:
            continue
        seen.add(spec.subject_key)
        ev = extract_departure_evidence(spec, market)
        if (
            ev.subject_key == spec.subject_key
            and ev.role_key == spec.role_key
            and ev.has_departure_framing
            and ev.false_friend is None
            and ev.unrelated_mention is None
        ):
            return ev
    return None


def departure_story_key_for_market(
    name: Optional[str],
    sport_category: Optional[str] = None,
    *,
    external_id: Optional[str] = None,
    source: Optional[str] = None,
) -> Optional[str]:
    """Return the story key when a market genuinely belongs to one of the
    supported departure stories. Refuses lexical false friends and speech/mention rows."""
    if not name and not external_id:
        return None
    cat = (sport_category or "").strip().lower()
    if cat in DEPARTURE_STRICT_CONFLICT_CATEGORIES:
        return None
    probe = {
        "name": name or "",
        "llm_sport_category": cat or "politics",
        "external_id": external_id or "",
        "source": source or ("kalshi" if (external_id or "").upper().startswith("KX") else "polymarket"),
    }
    for spec in (
        KATIE_ZACHARIA_DEPARTURE_SPEC,
        PETE_HEGSETH_DEPARTURE_SPEC,
        TRUMP_CABINET_DEPARTURE_SPEC,
    ):
        ev = extract_departure_evidence(spec, probe)
        if (
            ev.false_friend is None
            and ev.unrelated_mention is None
            and ev.other_edition_token is None
            and ev.subject_key == spec.subject_key
            and ev.role_key == spec.role_key
            and ev.has_departure_framing
        ):
            return spec.story_key
    return None


# ---------------------------------------------------------------------------
# Decision 2: Probability equivalence across venues.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DepartureEquivalenceVerdict:
    verdict: str  # "same" | "different" | "unknown"
    reason: str
    canonical_proposition_key: Optional[str]
    rule_version: str = DEPARTURE_MEANING_RULE_VERSION

    @property
    def is_equivalent(self) -> bool:
        return self.verdict == "same"


def evaluate_departure_equivalence(
    market_a: Any,
    market_b: Any,
) -> DepartureEquivalenceVerdict:
    """Evaluate whether two markets state the SAME probability-equivalent
    departure proposition (same subject, role, edition, verified settlement
    predicate, population scope and normalized cutoff horizon)."""
    ev_a = extract_any_departure_evidence(market_a)
    ev_b = extract_any_departure_evidence(market_b)
    if ev_a is None or ev_b is None:
        return DepartureEquivalenceVerdict(
            verdict="different",
            reason="not_both_departure_story_markets",
            canonical_proposition_key=None,
        )
    if ev_a.subject_key != ev_b.subject_key or ev_a.role_key != ev_b.role_key:
        return DepartureEquivalenceVerdict(
            verdict="different",
            reason=f"subject_or_role_mismatch:{ev_a.subject_key}:{ev_a.role_key}_vs_{ev_b.subject_key}:{ev_b.role_key}",
            canonical_proposition_key=None,
        )
    if ev_a.edition_key != ev_b.edition_key:
        return DepartureEquivalenceVerdict(
            verdict="different",
            reason=f"edition_mismatch:{ev_a.edition_key}_vs_{ev_b.edition_key}",
            canonical_proposition_key=None,
        )
    if ev_a.predicate_class in ("side_question", "after_role") or ev_b.predicate_class in (
        "side_question",
        "after_role",
    ):
        return DepartureEquivalenceVerdict(
            verdict="different",
            reason=f"predicate_mismatch:{ev_a.predicate_class}_vs_{ev_b.predicate_class}",
            canonical_proposition_key=None,
        )
    # If one is left_administration and the other is not, they are different predicates
    # even when the other's rules are unread.
    if (ev_a.predicate_class == PREDICATE_LEFT_ADMINISTRATION) != (
        ev_b.predicate_class == PREDICATE_LEFT_ADMINISTRATION
    ):
        return DepartureEquivalenceVerdict(
            verdict="different",
            reason=f"predicate_mismatch:{ev_a.predicate_class}_vs_{ev_b.predicate_class}",
            canonical_proposition_key=None,
        )
    if ev_a.predicate_class == PREDICATE_UNKNOWN or ev_b.predicate_class == PREDICATE_UNKNOWN:
        return DepartureEquivalenceVerdict(
            verdict="unknown",
            reason="missing_settlement_rules",
            canonical_proposition_key=None,
        )
    if ev_a.predicate_class != ev_b.predicate_class or ev_a.population_scope != ev_b.population_scope:
        return DepartureEquivalenceVerdict(
            verdict="different",
            reason=(
                f"predicate_mismatch:{ev_a.predicate_class}:{ev_a.population_scope}"
                f"_vs_{ev_b.predicate_class}:{ev_b.population_scope}"
            ),
            canonical_proposition_key=None,
        )
    if ev_a.horizon_key is None or ev_b.horizon_key is None:
        return DepartureEquivalenceVerdict(
            verdict="unknown",
            reason="unsupported_or_missing_horizon",
            canonical_proposition_key=None,
        )
    if ev_a.horizon_key != ev_b.horizon_key:
        return DepartureEquivalenceVerdict(
            verdict="different",
            reason=f"horizon_mismatch:{ev_a.horizon_key}_vs_{ev_b.horizon_key}",
            canonical_proposition_key=None,
        )
    canonical_key = (
        f"{ev_a.subject_key}:{ev_a.role_key}:{ev_a.predicate_class}"
        f":{ev_a.population_scope}:{ev_a.horizon_key}"
    )
    return DepartureEquivalenceVerdict(
        verdict="same",
        reason="equivalent_departure_proposition",
        canonical_proposition_key=canonical_key,
    )


def departure_equivalence_for_fold(
    left_data: Mapping[str, Any],
    right_data: Mapping[str, Any],
) -> Optional[DepartureEquivalenceVerdict]:
    """Hook for Discover / collection snapshot folding."""
    ev_left = extract_any_departure_evidence(left_data)
    ev_right = extract_any_departure_evidence(right_data)
    if ev_left is None and ev_right is None:
        return None
    return evaluate_departure_equivalence(left_data, right_data)
