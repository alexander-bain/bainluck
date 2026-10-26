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
     market fields and evidence-bound ``#5318`` registrations.
   - Admits related markets across different settlement predicates into
     rule-based collection sections (``departure_announced``,
     ``departure_vacated``, ``departure_rules_unread``,
     ``departure_left_administration``, ``after_role``, ``side_question``).
   - Refuses lexical false friends (e.g. ``"Zachariah Branch"``) with
     ``lexical_false_friend``, mention/field markets (e.g.
     ``"What will Trump say this week?"``, ``"Who will leave their role in the
     Trump administration in 2026?"``) with ``name_only_mention``, other offices
     with ``other_office``, earlier stints with ``other_edition``, and other
     subjects with ``not_this_subject`` / ``not_this_story``.

2. **Probability equivalence** (:func:`evaluate_departure_equivalence`):
   - Requires the same subject, role, edition, verified settlement predicate
     (from an evidence-bound ``#5318`` registration or explicit title literal,
     never from unregistered rules-text heuristics), and normalized cutoff
     horizon.
   - Never infers equivalence from title similarity or aligned timestamps alone.
   - Keeps announcement-based Polymarket contracts and actual-vacancy Kalshi
     contracts ``different`` even when their cutoffs align to the minute.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import re
from typing import Any, Mapping, Optional

# ---------------------------------------------------------------------------
# Rule versions, policies & decision reasons (fit container_member_decisions).
# ---------------------------------------------------------------------------

RULE_VERSION = "departure-story@1"
DEPARTURE_STORY_RULE_VERSION = RULE_VERSION
DEPARTURE_MEANING_RULE_VERSION = "departure-meaning@1"

#: Explicit policy when a row belongs to a verified provider + registered event
#: + subject/edition, but the stored row omits rules text (e.g. Bain Luck's
#: `/api/futures/65678073` where `description` is `null` while the retained
#: Polymarket event `1183118` rules were verified in `#5318`).
#: An unstored-rules row on the registered event is admitted with
#: `basis="registration_only"` and `missing_text_policy=MISSING_RULES_TEXT_POLICY`.
#: Unregistered events in the same provider series (e.g. `KXZACHARIAOUT-28JAN`)
#: NEVER inherit this policy and stay in `departure_rules_unread`.
MISSING_RULES_TEXT_POLICY = "allow_registered_event_when_unstored"

ADMITTED_SUBJECT_RELATION = "admitted_subject_relation"
ADMITTED_DEPARTURE_ANNOUNCEMENT = "admitted_departure_announcement"
ADMITTED_DEPARTURE_VACATED = "admitted_departure_vacated"
ADMITTED_DEPARTURE_SEPARATE_RULE = "admitted_departure_separate_rule"

NAME_ONLY_MENTION = "name_only_mention"
OTHER_OFFICE = "other_office"
NOT_THIS_STORY = "not_this_story"
UNRELATED_SUBJECT_MENTION = "unrelated_subject_mention"
NOT_THIS_SUBJECT_REASON = "not_this_subject"

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

#: Reader section order (`READER-FLOW.md` §2):
#: 1. An announced exit counts (`departure_announced`)
#: 2. Only an actual departure counts (`departure_vacated`)
#: 3. Leaving the job · rules not checked yet (`departure_rules_unread`)
#: 4. Leaving the administration (`departure_left_administration`)
#: 5. What comes next (`after_role`)
#: 6. About the job (`side_question`)
DEPARTURE_ORDER: tuple[str, ...] = (
    "departure_announced",
    "departure_vacated",
    "departure_rules_unread",
    "departure_left_administration",
    "after_role",
    "side_question",
)

# Canonical predicate classes.
PREDICATE_ANNOUNCEMENT = "announcement_or_withdrawal"
PREDICATE_ACTUAL_DEPARTURE = "actual_departure_vacated_role"
PREDICATE_LEFT_ADMINISTRATION = "left_administration"
PREDICATE_UNKNOWN = "unknown_predicate"

SCOPE_SINGLE_OFFICEHOLDER = "single_officeholder"
SCOPE_UNKNOWN = "unknown_scope"

EDITION_TRUMP_47 = "trump_47_admin"

CATEGORY_GATE = frozenset({"politics", "geopolitics"})
DEPARTURE_ALLOWED_CATEGORIES = CATEGORY_GATE
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
# #11040 DepartureSubject + evidence-bound #5318 rule registrations.
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


#: Evidence-bound #5318 rule registrations keyed by (provider_kind, provider_key).
#: Each entry binds provider, subject, edition, specific event identifier,
#: primary rules field, verbatim decisive quote, retained rules SHA-256, and
#: the allowed sentence patterns from the retained rules text so that modified
#: or contradictory rules (even when preserving the original quote) are
#: rejected and routed to `departure_rules_unread`.
REGISTRATIONS: dict[tuple[str, str], dict[str, Any]] = {
    ("kalshi_series", "KXZACHARIAOUT"): {
        "provider": "kalshi",
        "subject": "katie-zacharia-press-secretary",
        "person": "Katie Zacharia",
        "edition": 2026,
        "series_ticker": "KXZACHARIAOUT",
        "event_ticker": "KXZACHARIAOUT-26OCT",
        "predicate": "vacated",
        "basis": "rules",
        "rules_field": "rules_secondary",
        "quote": (
            "Katie Zacharia must have an actual departure date and vacate the role "
            "within the time period."
        ),
        "rules_sha256": "2d191cebfb1cadff2e4aa8cc736e035dcc26c5ff76a3fedd6603893dfa2a71a1",
        "rules_primary_template": (
            "If Katie Zacharia leaves as White House Press Secretary before <DATE>, "
            "then the market resolves to Yes."
        ),
        "fetched_at": "2026-10-14T23:51:09Z",
        "source": "https://api.elections.kalshi.com/trade-api/v2/events/KXZACHARIAOUT-26OCT",
    },
    ("polymarket_event", "1183118"): {
        "provider": "polymarket",
        "subject": "katie-zacharia-press-secretary",
        "person": "Katie Zacharia",
        "edition": 2026,
        "event_id": "1183118",
        "condition_ids": (
            "0x57e97ab7f68a11013e7e4096ce6b0601b40b9e5a8609c4cb4196ef1b753e6953",
            "0xc587f97b3eaac5948ed7e148bb5248f51f98795ea0e1c3bc9acf635b0a2f95b0",
        ),
        "predicate": "announced",
        "basis": "rules",
        "rules_field": "description",
        "quote": (
            'An announcement of Katie Zacharia\'s resignation/removal by this market\'s '
            'end date will immediately resolve this market to "Yes", regardless of when '
            "the announced resignation/removal goes into effect."
        ),
        "rules_sha256": "cc46e9a2b8bf04167ca6c9374555c00aa0e6ee4d87cd98d59a19053ee4a11269",
        "fetched_at": "2026-10-14T23:51:09Z",
        "source": "https://polymarket.com/event/katie-zacharia-out-as-press-secretary-by",
    },
}

_KALSHI_ZACHARIA_PRIMARY_RE = re.compile(
    r"^If Katie Zacharia leaves as White House Press Secretary before "
    r"[A-Z][a-z]{2,8} \d{1,2}, 202\d, then the market resolves to Yes\.$"
)

# Explicit contradiction patterns for settlement rules.
_ANNOUNCED_CONTRADICTION_RE = re.compile(
    r"\b(?:"
    r"announcement\s+(?:alone\s+|of\s+a\s+future\s+departure\s+|of\s+resignation\s+)?"
    r"(?:does\s+not|will\s+not|shall\s+not|is\s+not\s+sufficient)|"
    r"merely\s+announcing\s+[^.]*does\s+not|"
    r"must\s+have\s+an\s+actual\s+departure\s+date\s+and\s+vacate|"
    r"resolves?\s+to\s+[\"'\u201c]?yes[\"'\u201d]?\s+only\s+(?:if|when|after)\s+[^.]*\bvacat"
    r")\b",
    re.I,
)
_VACATED_CONTRADICTION_RE = re.compile(
    r"\b(?:"
    r"an?\s+announcement\s+of\s+[^.]*?\bwill\s+(?:immediately\s+)?resolve\s+this\s+market\s+to\s+[\"'\u201c]?yes|"
    r"regardless\s+of\s+when\s+the\s+announced\s+[^.]*?\bgoes\s+into\s+effect|"
    r"announcement\s+alone\s+(?:is\s+sufficient|resolves|will\s+resolve|counts)|"
    r"(?:if|when)\s+a\s+successor\s+is\s+(?:formally\s+)?nominated|"
    r"(?:does\s+not|need\s+not)\s+need\s+to\s+vacate"
    r")\b",
    re.I,
)


# ---------------------------------------------------------------------------
# Clause patterns for departure-story@1.
# ---------------------------------------------------------------------------

_DEPARTURE_RE = re.compile(
    r"\b(out as|leave|leaves|leaving|resign\w*|step\w* down|depart\w*|"
    r"removed|fired|dismissed|replaced|vacate\w*|cease\w* to be|no longer)\b",
    re.I,
)
_ROLE_FRAME_RE = re.compile(
    r"\b(out as|resign\w* as|step\w* down as|leave\w* as)\s+([^?.,;]+)", re.I
)
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


def _provider_identity(obj: Any) -> Mapping[str, Any]:
    pi = _get(obj, "provider_identity")
    return pi if isinstance(pi, Mapping) else {}


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


def _norm_ws(text: str) -> str:
    return " ".join(text.replace("\u201c", '"').replace("\u201d", '"').split())


def _split_sentences(text: str) -> list[str]:
    normalized = text.replace("\u201c", '"').replace("\u201d", '"')
    chunks: list[str] = []
    for para in re.split(r"\n+", normalized):
        para = para.strip()
        if not para:
            continue
        for sent in re.split(r"(?<=\.)\s+", para):
            s = " ".join(sent.split())
            if s:
                chunks.append(s)
    return chunks


_RULES_FIELD_KEYS: tuple[str, ...] = (
    "description",
    "rules_primary",
    "rules_secondary",
    "resolution_rules",
)


def _extract_rules_carriers(row: Any) -> tuple[dict[str, str], list[str], bool]:
    """Return ``(merged_fields, all_carrier_texts, has_conflicting_duplicate)``.

    Inspects both top-level and ``market_metadata`` carriers for every rules
    field so a populated top-level field never hides a conflicting metadata
    carrier (#11040 B2).
    """
    meta = _metadata(row)
    fields: dict[str, str] = {}
    all_texts: list[str] = []
    has_conflict = False
    for key in _RULES_FIELD_KEYS:
        top_raw = _get(row, key)
        meta_raw = meta.get(key)
        top_val = top_raw.strip() if isinstance(top_raw, str) and top_raw.strip() else None
        meta_val = meta_raw.strip() if isinstance(meta_raw, str) and meta_raw.strip() else None
        if top_val is not None:
            all_texts.append(top_val)
        if meta_val is not None:
            all_texts.append(meta_val)
        if top_val is not None and meta_val is not None and top_val != meta_val:
            has_conflict = True
        chosen = top_val if top_val is not None else meta_val
        if chosen is not None:
            fields[key] = chosen
    return fields, all_texts, has_conflict


def _extract_rules_fields(row: Any) -> dict[str, str]:
    fields, _, _ = _extract_rules_carriers(row)
    return fields


def _polymarket_event_carriers(row: Any) -> list[str]:
    meta = _metadata(row)
    pi = _provider_identity(row)
    carriers: list[str] = []
    for raw in (meta.get("polymarket_event_id"), pi.get("event_id")):
        if raw is not None and str(raw).strip():
            carriers.append(str(raw).strip())
    for raw_gid in (_get(row, "group_id"), meta.get("group_id"), pi.get("group_id")):
        if raw_gid is not None and str(raw_gid).strip():
            gid = str(raw_gid).strip()
            if gid.startswith("polymarket:"):
                ev = gid.split(":", 1)[1].strip()
                if ev:
                    carriers.append(ev)
            else:
                carriers.append(f"non_polymarket:{gid}")
    return carriers


def _polymarket_condition_carriers(row: Any) -> list[str]:
    meta = _metadata(row)
    pi = _provider_identity(row)
    carriers: list[str] = []
    for raw in (
        _get(row, "external_id"),
        meta.get("condition_id"),
        meta.get("conditionId"),
        pi.get("condition_id"),
        pi.get("conditionId"),
    ):
        if isinstance(raw, str) and raw.strip():
            carriers.append(raw.strip().lower())
    return carriers


def _kalshi_ticker_carriers(row: Any) -> list[str]:
    meta = _metadata(row)
    pi = _provider_identity(row)
    source = str(_get(row, "source") or pi.get("venue") or "").strip().lower()
    tickers: list[str] = []
    for raw in (
        _get(row, "external_id"),
        meta.get("external_id"),
        meta.get("ticker"),
        meta.get("market_ticker"),
        meta.get("kalshi_ticker"),
        pi.get("market_ticker"),
        pi.get("ticker"),
        pi.get("external_id"),
    ):
        if raw is not None and str(raw).strip():
            ticker = str(raw).strip().upper()
            if source == "kalshi" or ticker.startswith("KX"):
                tickers.append(ticker)
    return tickers


def _kalshi_series_carriers(row: Any) -> list[str]:
    meta = _metadata(row)
    pi = _provider_identity(row)
    carriers: list[str] = []
    for raw in (
        meta.get("series_ticker"),
        meta.get("kalshi_series_ticker"),
        meta.get("series"),
        pi.get("series"),
    ):
        if raw is not None and str(raw).strip():
            carriers.append(str(raw).strip().upper())
    for ticker in _kalshi_ticker_carriers(row):
        carriers.append(ticker.split("-", 1)[0])
    for raw_gid in (_get(row, "group_id"), meta.get("group_id"), pi.get("group_id")):
        if raw_gid is not None and str(raw_gid).strip():
            gid = str(raw_gid).strip()
            if gid.upper().startswith("KALSHI:"):
                suffix = gid.split(":", 1)[1].strip().upper()
                if suffix:
                    carriers.append(suffix.split("-", 1)[0])
    return carriers


def _registration_key(row: Any) -> Optional[tuple[str, str]]:
    rk = _get(row, "registration_key")
    if isinstance(rk, (list, tuple)) and len(rk) == 2:
        return (str(rk[0]), str(rk[1]))
    for series in _kalshi_series_carriers(row):
        if ("kalshi_series", series) in REGISTRATIONS:
            return ("kalshi_series", series)
    for pm_ev in _polymarket_event_carriers(row):
        if ("polymarket_event", pm_ev) in REGISTRATIONS:
            return ("polymarket_event", pm_ev)
    return None


def _validate_registration(
    key: tuple[str, str],
    reg: Mapping[str, Any],
    row: Any,
    subject: Optional[DepartureSubject],
) -> dict[str, Any]:
    """Validate provider, subject/edition, simultaneous identity carriers, and
    stored rules text before assigning a known predicate section (#11040 B2)."""
    meta = _metadata(row)
    pi = _provider_identity(row)

    # 1. Subject & edition check.
    expected_subject = str(reg["subject"])
    expected_edition = int(reg["edition"])
    if subject is not None and (
        subject.subject != expected_subject or subject.edition != expected_edition
    ):
        return {
            "predicate": "unknown",
            "basis": "registration_mismatch",
            "reason": "edition_or_subject_mismatch",
            "registration": list(key),
        }

    row_subject = _get(row, "subject") or meta.get("subject")
    if row_subject is not None and str(row_subject) != expected_subject:
        return {
            "predicate": "unknown",
            "basis": "registration_mismatch",
            "reason": "edition_or_subject_mismatch",
            "registration": list(key),
        }

    row_edition = _get(row, "edition") or meta.get("edition")
    if row_edition is not None:
        try:
            if int(row_edition) != expected_edition:
                return {
                    "predicate": "unknown",
                    "basis": "registration_mismatch",
                    "reason": "edition_or_subject_mismatch",
                    "registration": list(key),
                }
        except (TypeError, ValueError):
            return {
                "predicate": "unknown",
                "basis": "registration_mismatch",
                "reason": "edition_or_subject_mismatch",
                "registration": list(key),
            }

    name = str(_get(row, "name") or "")
    person_name = str(reg.get("person") or "")
    if name and person_name and not _full_name_re(person_name).search(name):
        return {
            "predicate": "unknown",
            "basis": "registration_mismatch",
            "reason": "edition_or_subject_mismatch",
            "registration": list(key),
        }

    reg_subj_obj = DEPARTURE_SUBJECTS.get(expected_subject)
    ends_date, _ = _ends_utc(row)
    if reg_subj_obj is not None and ends_date is not None and ends_date < reg_subj_obj.tenure_start:
        return {
            "predicate": "unknown",
            "basis": "registration_mismatch",
            "reason": "edition_or_subject_mismatch",
            "registration": list(key),
        }

    # 2. Provider check across all venue carriers.
    expected_provider = str(reg["provider"]).lower()
    for raw_source in (_get(row, "source"), pi.get("venue")):
        if raw_source is not None and str(raw_source).strip():
            if str(raw_source).strip().lower() != expected_provider:
                return {
                    "predicate": "unknown",
                    "basis": "registration_mismatch",
                    "reason": "provider_mismatch",
                    "registration": list(key),
                }

    has_explicit_reg_key = isinstance(_get(row, "registration_key"), (list, tuple))

    # 3. Simultaneous identity carrier check (never extend one Kalshi event's
    # evidence to every future event in a series, and never accept conflicting
    # simultaneous event/group/condition carriers).
    if key[0] == "kalshi_series":
        expected_series = str(reg["series_ticker"]).upper()
        series_carriers = _kalshi_series_carriers(row)
        if any(s != expected_series for s in series_carriers):
            return {
                "predicate": "unknown",
                "basis": "registration_mismatch",
                "reason": "conflicting_provider_identity",
                "registration": list(key),
                "observed_series": sorted(set(series_carriers)),
                "expected_series": expected_series,
            }

        expected_event = str(reg["event_ticker"]).upper()
        event_carriers: list[str] = []
        for raw_ev in (
            meta.get("event_ticker"),
            meta.get("kalshi_event_ticker"),
            pi.get("event"),
            pi.get("event_ticker"),
        ):
            if raw_ev is not None and str(raw_ev).strip():
                event_carriers.append(str(raw_ev).strip().upper())
        for raw_gid in (_get(row, "group_id"), meta.get("group_id"), pi.get("group_id")):
            if raw_gid is not None and str(raw_gid).strip():
                gid = str(raw_gid).strip()
                if gid.upper().startswith("KALSHI:"):
                    ev_from_gid = gid.split(":", 1)[1].strip().upper()
                    if ev_from_gid:
                        event_carriers.append(ev_from_gid)
                else:
                    return {
                        "predicate": "unknown",
                        "basis": "registration_mismatch",
                        "reason": "conflicting_provider_identity",
                        "registration": list(key),
                        "observed_group_id": gid,
                    }

        ticker_carriers = _kalshi_ticker_carriers(row)

        if any(ev != expected_event for ev in event_carriers):
            return {
                "predicate": "unknown",
                "basis": "registration_mismatch",
                "reason": "unregistered_series_event",
                "registration": list(key),
                "observed_event": next(ev for ev in event_carriers if ev != expected_event),
                "expected_event": expected_event,
            }
        for ticker in ticker_carriers:
            if not (ticker == expected_event or ticker.startswith(expected_event + "-")):
                return {
                    "predicate": "unknown",
                    "basis": "registration_mismatch",
                    "reason": "unregistered_series_event",
                    "registration": list(key),
                    "observed_ticker": ticker,
                    "expected_event": expected_event,
                }
        child_tickers = {
            ticker
            for ticker in ticker_carriers
            if ticker.startswith(expected_event + "-")
        }
        if len(child_tickers) > 1:
            return {
                "predicate": "unknown",
                "basis": "registration_mismatch",
                "reason": "conflicting_provider_identity",
                "registration": list(key),
                "observed_tickers": sorted(child_tickers),
                "expected_event": expected_event,
            }
        if not event_carriers and not ticker_carriers and not has_explicit_reg_key:
            return {
                "predicate": "unknown",
                "basis": "registration_mismatch",
                "reason": "unregistered_series_event",
                "registration": list(key),
                "expected_event": expected_event,
            }

    elif key[0] == "polymarket_event":
        expected_event_id = str(reg["event_id"]).strip()
        event_carriers = _polymarket_event_carriers(row)
        distinct_events = set(event_carriers)
        if len(distinct_events) > 1:
            return {
                "predicate": "unknown",
                "basis": "registration_mismatch",
                "reason": "conflicting_provider_identity",
                "registration": list(key),
                "observed_events": sorted(distinct_events),
                "expected_event": expected_event_id,
            }
        if distinct_events and next(iter(distinct_events)) != expected_event_id:
            return {
                "predicate": "unknown",
                "basis": "registration_mismatch",
                "reason": "unregistered_provider_event",
                "registration": list(key),
                "observed_event": next(iter(distinct_events)),
                "expected_event": expected_event_id,
            }
        if not distinct_events and not has_explicit_reg_key:
            return {
                "predicate": "unknown",
                "basis": "registration_mismatch",
                "reason": "unregistered_provider_event",
                "registration": list(key),
                "expected_event": expected_event_id,
            }

        cond_carriers = _polymarket_condition_carriers(row)
        if len(set(cond_carriers)) > 1:
            return {
                "predicate": "unknown",
                "basis": "registration_mismatch",
                "reason": "conflicting_provider_identity",
                "registration": list(key),
                "observed_condition_ids": sorted(set(cond_carriers)),
            }

    # 4. Stored rules text verification & bounded registration-only policy.
    rules_fields, all_carrier_texts, has_carrier_conflict = _extract_rules_carriers(row)
    if not all_carrier_texts:
        if key[0] == "polymarket_event":
            allowed_cids = {
                str(c).strip().lower()
                for c in reg.get("condition_ids", ())
                if str(c).strip()
            }
            if allowed_cids:
                cond_carriers = _polymarket_condition_carriers(row)
                if not cond_carriers or cond_carriers[0] not in allowed_cids:
                    return {
                        "predicate": "unknown",
                        "basis": "registration_mismatch",
                        "reason": "unregistered_condition_id",
                        "registration": list(key),
                        "observed_condition_id": cond_carriers[0] if cond_carriers else None,
                    }
        return {
            "predicate": reg["predicate"],
            "basis": "registration_only",
            "missing_text_policy": MISSING_RULES_TEXT_POLICY,
            "registration": list(key),
            "quote": reg["quote"],
            "rules_sha256": reg["rules_sha256"],
        }

    all_rules_text = "\n".join(all_carrier_texts)
    expected_pred = str(reg["predicate"])
    contradiction_re = (
        _ANNOUNCED_CONTRADICTION_RE
        if expected_pred == "announced"
        else _VACATED_CONTRADICTION_RE
    )
    if contradiction_re.search(all_rules_text):
        return {
            "predicate": "unknown",
            "basis": "registration_mismatch",
            "reason": "contradictory_settlement_clause",
            "registration": list(key),
        }

    if has_carrier_conflict:
        return {
            "predicate": "unknown",
            "basis": "registration_mismatch",
            "reason": "conflicting_rules_carriers",
            "registration": list(key),
        }

    primary_field = str(reg.get("rules_field") or "description")
    primary_text = rules_fields.get(primary_field) or ""
    if not primary_text or _norm_ws(str(reg["quote"])) not in _norm_ws(primary_text):
        return {
            "predicate": "unknown",
            "basis": "registration_mismatch",
            "reason": "registered_quote_missing",
            "registration": list(key),
        }

    observed_sha = hashlib.sha256(primary_text.encode("utf-8")).hexdigest()
    if observed_sha != str(reg["rules_sha256"]):
        return {
            "predicate": "unknown",
            "basis": "registration_mismatch",
            "reason": "rules_sha256_mismatch",
            "registration": list(key),
            "observed_rules_sha256": observed_sha,
            "expected_rules_sha256": reg["rules_sha256"],
        }

    for other_key, other_val in rules_fields.items():
        if other_key == primary_field:
            continue
        if key == ("kalshi_series", "KXZACHARIAOUT") and other_key == "rules_primary":
            rp = " ".join(other_val.split())
            if not _KALSHI_ZACHARIA_PRIMARY_RE.match(rp):
                return {
                    "predicate": "unknown",
                    "basis": "registration_mismatch",
                    "reason": "contradictory_settlement_clause",
                    "registration": list(key),
                }
            continue
        if other_val != primary_text:
            return {
                "predicate": "unknown",
                "basis": "registration_mismatch",
                "reason": "unreviewed_additional_rules_field",
                "registration": list(key),
                "unreviewed_field": other_key,
            }

    return {
        "predicate": expected_pred,
        "basis": reg["basis"],
        "registration": list(key),
        "quote": reg["quote"],
        "rules_sha256": reg["rules_sha256"],
        "observed_rules_sha256": observed_sha,
    }


def departure_predicate(
    row: Any, *, subject: Optional[DepartureSubject] = None
) -> dict[str, Any]:
    """Classify a departure market's settlement predicate strictly from an
    evidence-bound ``#5318`` registration or an explicit title literal.

    Never infers a predicate from venue name or from unregistered rules-text
    regex heuristics (#11040 B2, B3).
    """
    key = _registration_key(row)
    if key and key in REGISTRATIONS:
        return _validate_registration(key, REGISTRATIONS[key], row, subject)

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
    return {
        "predicate": "unknown",
        "basis": "rules_not_read",
        "reason": "unregistered_market",
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

    pred = departure_predicate(row, subject=subject)
    evidence.append({"clause": "predicate", "result": pred["predicate"], **pred})
    section = {
        "announced": "departure_announced",
        "vacated": "departure_vacated",
        "left_administration": "departure_left_administration",
        "unknown": "departure_rules_unread",
    }[pred["predicate"]]
    return SubjectDecisionResult("admitted", ADMITTED_SUBJECT_RELATION, section, evidence)


# ---------------------------------------------------------------------------
# DepartureStorySpec + horizon normalization + Decision 2 equivalence.
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
    departure_subject: DepartureSubject


KATIE_ZACHARIA_ENTITY_PG = KATIE_ZACHARIA_PRESS_SECRETARY.person_pg
PETE_HEGSETH_ENTITY_PG = PETE_HEGSETH_DEFENSE_SECRETARY.person_pg

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

DEPARTURE_SPECS_BY_SUBJECT: dict[str, DepartureStorySpec] = {
    KATIE_ZACHARIA_DEPARTURE_SPEC.subject: KATIE_ZACHARIA_DEPARTURE_SPEC,
    "katie-zacharia-departure": KATIE_ZACHARIA_DEPARTURE_SPEC,
    PETE_HEGSETH_DEPARTURE_SPEC.subject: PETE_HEGSETH_DEPARTURE_SPEC,
}

DEPARTURE_SPECS_BY_STORY_KEY: dict[str, DepartureStorySpec] = {
    KATIE_ZACHARIA_DEPARTURE_SPEC.story_key: KATIE_ZACHARIA_DEPARTURE_SPEC,
    PETE_HEGSETH_DEPARTURE_SPEC.story_key: PETE_HEGSETH_DEPARTURE_SPEC,
}

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
    r"-T?(\d{2})(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)(\d{2})(?:-|$)",
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


def _normalize_horizon(
    name: str,
    external_id: str,
    resolution_date: Optional[datetime],
) -> tuple[Optional[str], str]:
    """Return ``(normalized_yyyy_mm_dd, horizon_source)`` or ``(None, reason)``."""
    if _UNSUPPORTED_VAGUE_HORIZON_RE.search(name):
        return None, "unsupported_vague_horizon"

    if name:
        m = _PREP_DATE_RE.search(name)
        if m and m.group(4):
            prep = re.sub(r"\s+", " ", m.group(1).strip().lower())
            month = _MONTHS[m.group(2).lower().rstrip(".")]
            day = int(m.group(3))
            year = int(m.group(4))
            try:
                parsed = date(year, month, day)
                if prep in ("before", "prior to") and day == 1:
                    parsed = parsed - timedelta(days=1)
                return parsed.isoformat(), "name_date"
            except ValueError:
                pass

        m_before_yr = _BEFORE_YEAR_RE.search(name)
        if m_before_yr:
            year = int(m_before_yr.group(1)) - 1
            return date(year, 12, 31).isoformat(), "name_before_year"

        m_in_yr = _IN_YEAR_RE.search(name)
        if m_in_yr:
            year = int(m_in_yr.group(1))
            return date(year, 12, 31).isoformat(), "name_in_year"

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


def departure_story_key_for_market(
    name: Optional[str],
    sport_category: Optional[str] = None,
    *,
    external_id: Optional[str] = None,
    source: Optional[str] = None,
) -> Optional[str]:
    """Return the story key when a market genuinely belongs to one of the
    supported departure stories. Refuses lexical false friends and speech/mention rows."""
    if not name:
        return None
    cat = (sport_category or "").strip().lower()
    if cat in DEPARTURE_STRICT_CONFLICT_CATEGORIES:
        return None
    probe = {
        "name": name,
        "llm_sport_category": cat if cat in CATEGORY_GATE else "politics",
        "external_id": external_id or "",
        "source": source or ("kalshi" if (external_id or "").upper().startswith("KX") else "polymarket"),
    }
    for spec in (KATIE_ZACHARIA_DEPARTURE_SPEC, PETE_HEGSETH_DEPARTURE_SPEC):
        res = decide_departure_subject(spec.departure_subject, probe)
        if res.admitted:
            return spec.story_key
    return None


# ---------------------------------------------------------------------------
# Decision 2: Probability equivalence across venues (evidence-bound).
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


def _match_admitted_subject(market: Any) -> Optional[tuple[DepartureStorySpec, SubjectDecisionResult]]:
    for spec in (KATIE_ZACHARIA_DEPARTURE_SPEC, PETE_HEGSETH_DEPARTURE_SPEC):
        res = decide_departure_subject(spec.departure_subject, market)
        if res.admitted:
            return spec, res
    return None


def evaluate_departure_equivalence(
    market_a: Any,
    market_b: Any,
) -> DepartureEquivalenceVerdict:
    """Evaluate whether two markets state the SAME probability-equivalent
    departure proposition (same subject, role, edition, verified settlement
    predicate from `#5318` registration or title literal, and normalized cutoff
    horizon).

    Note: In the collection hub snapshot, non-folding is enforced directly by
    ``theme_assembly.build_snapshot`` (``resolved_defn.family == "departure"``).
    This function is the pure Decision 2 equivalence evaluator.
    """
    matched_a = _match_admitted_subject(market_a)
    matched_b = _match_admitted_subject(market_b)
    if matched_a is None or matched_b is None:
        return DepartureEquivalenceVerdict(
            verdict="different",
            reason="not_both_departure_story_markets",
            canonical_proposition_key=None,
        )
    spec_a, res_a = matched_a
    spec_b, res_b = matched_b
    if spec_a.subject_key != spec_b.subject_key or spec_a.role_key != spec_b.role_key:
        return DepartureEquivalenceVerdict(
            verdict="different",
            reason=(
                f"subject_or_role_mismatch:{spec_a.subject_key}:{spec_a.role_key}"
                f"_vs_{spec_b.subject_key}:{spec_b.role_key}"
            ),
            canonical_proposition_key=None,
        )
    if spec_a.edition_key != spec_b.edition_key:
        return DepartureEquivalenceVerdict(
            verdict="different",
            reason=f"edition_mismatch:{spec_a.edition_key}_vs_{spec_b.edition_key}",
            canonical_proposition_key=None,
        )

    sec_a = res_a.section or "departure_rules_unread"
    sec_b = res_b.section or "departure_rules_unread"

    if sec_a in ("side_question", "after_role") or sec_b in ("side_question", "after_role"):
        return DepartureEquivalenceVerdict(
            verdict="different",
            reason=f"predicate_mismatch:{sec_a}_vs_{sec_b}",
            canonical_proposition_key=None,
        )
    if (sec_a == "departure_left_administration") != (sec_b == "departure_left_administration"):
        return DepartureEquivalenceVerdict(
            verdict="different",
            reason=f"predicate_mismatch:{sec_a}_vs_{sec_b}",
            canonical_proposition_key=None,
        )
    if sec_a == "departure_rules_unread" or sec_b == "departure_rules_unread":
        return DepartureEquivalenceVerdict(
            verdict="unknown",
            reason="missing_settlement_rules",
            canonical_proposition_key=None,
        )
    if sec_a != sec_b:
        return DepartureEquivalenceVerdict(
            verdict="different",
            reason=f"predicate_mismatch:{sec_a}_vs_{sec_b}",
            canonical_proposition_key=None,
        )

    res_dt_a = _aware(_get(market_a, "resolution_date"))
    if res_dt_a is None:
        ends_a, _ = _ends_utc(market_a)
        if ends_a is not None:
            res_dt_a = datetime(ends_a.year, ends_a.month, ends_a.day, tzinfo=timezone.utc)
    res_dt_b = _aware(_get(market_b, "resolution_date"))
    if res_dt_b is None:
        ends_b, _ = _ends_utc(market_b)
        if ends_b is not None:
            res_dt_b = datetime(ends_b.year, ends_b.month, ends_b.day, tzinfo=timezone.utc)

    horizon_a, _ = _normalize_horizon(
        str(_get(market_a, "name") or ""),
        str(_get(market_a, "external_id") or ""),
        res_dt_a,
    )
    horizon_b, _ = _normalize_horizon(
        str(_get(market_b, "name") or ""),
        str(_get(market_b, "external_id") or ""),
        res_dt_b,
    )
    if horizon_a is None or horizon_b is None:
        return DepartureEquivalenceVerdict(
            verdict="unknown",
            reason="unsupported_or_missing_horizon",
            canonical_proposition_key=None,
        )
    if horizon_a != horizon_b:
        return DepartureEquivalenceVerdict(
            verdict="different",
            reason=f"horizon_mismatch:{horizon_a}_vs_{horizon_b}",
            canonical_proposition_key=None,
        )

    canonical_key = (
        f"{spec_a.subject_key}:{spec_a.role_key}:{sec_a}"
        f":{SCOPE_SINGLE_OFFICEHOLDER}:{horizon_a}"
    )
    return DepartureEquivalenceVerdict(
        verdict="same",
        reason="equivalent_departure_proposition",
        canonical_proposition_key=canonical_key,
    )
