"""Pure helpers for the CU v2 quantitative frame (C1) and grounded subject (C2).

No DB, no LLM, no imports from ``app.tasks`` — everything decidable from
``(raw LLM output, market title)`` alone lives here so it is cheap to test and
safe to import from anywhere. The writer owns the DB half of grounding (the
alias lookup); this module owns the shapes, the vocabularies, and the
invariant.

**The frame invariant (#1809).** ``value`` and ``unit`` must appear LITERALLY in
the market title. This is a property, not a label: a number the title does not
contain is a hallucination, and the eight regex parsers this profile is meant
to retire (`market_grouping`, `discover_card_archetypes` rung extraction,
`prop_families._parse`, …) each shipped their own version of that bug —
"Pan Am 103" -> 103, "2026-27" -> 27, "W7M" -> 7,000,000. On violation the
sanitizer drops the WHOLE frame and keeps the rest of the profile: a
half-verified frame is worse than none, because a consumer cannot tell which
slot was the invented one.

Literal presence is an ANTI-HALLUCINATION check, not a semantic one. "Pan Am
103" still yields a literal 103; what stops that becoming a rung is the
``measure`` slot, not this predicate. The check's job is only to guarantee that
every number in the frame came out of the title.

**Grounding markers (#1809, gotcha #53 discipline).** An unresolved subject is
written as an explicit ``unresolved:<string>`` marker and a market with no
entities at all as ``unresolved:__none__``. Never a silent empty: "the registry
had no match for 'Lionel Messi'" and "the model returned no entities" are
different facts, and a consumer that sees ``None`` for both cannot tell a
coverage gap from a resolver bug.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

# The five frame slots, in the order #1809 names them.
FRAME_SLOTS = ("measure", "comparator", "value", "unit", "horizon_kind")

# Comparator vocabulary. Closed set — an unrecognised comparator becomes None
# rather than dropping the frame, because a measure+value with an unreadable
# comparator is still a usable (and verifiable) extraction.
COMPARATORS = frozenset({"gte", "gt", "lte", "lt", "eq", "ne", "range"})

_COMPARATOR_ALIASES = {
    ">=": "gte", "=>": "gte", "≥": "gte", "at_least": "gte", "at least": "gte",
    "no_less_than": "gte", "or_more": "gte", "minimum": "gte",
    ">": "gt", "above": "gt", "over": "gt", "more_than": "gt", "greater_than": "gt",
    "<=": "lte", "=<": "lte", "≤": "lte", "at_most": "lte", "at most": "lte",
    "no_more_than": "lte", "or_fewer": "lte", "or_less": "lte", "maximum": "lte",
    "<": "lt", "below": "lt", "under": "lt", "less_than": "lt", "fewer_than": "lt",
    "=": "eq", "==": "eq", "eq": "eq", "exactly": "eq", "equals": "eq", "is": "eq",
    "!=": "ne", "≠": "ne", "not_equal": "ne", "not": "ne",
    "between": "range", "range": "range", "within": "range",
}

# Horizon vocabulary — the SHAPE of the resolution window, not its date. Kept
# deliberately coarse: consumers bucket by it, they do not do arithmetic on it.
HORIZON_KINDS = frozenset({
    "intraday", "daily", "weekly", "monthly", "quarterly",
    "annual", "multi_year", "open_ended",
})

# Entity types the v2 prompt emits, in primary-subject preference order. A
# resolved entity always outranks an unresolved one; this order only breaks
# ties among equals (a market about "Lionel Messi at the World Cup" is about
# the team/person, not the place).
ENTITY_TYPES = ("team", "person", "org", "event", "work", "place")
_ENTITY_TYPE_RANK = {t: i for i, t in enumerate(ENTITY_TYPES)}

UNRESOLVED_PREFIX = "unresolved:"
# Distinguishes "the model gave us nothing to resolve" from "we tried and
# missed" — two different facts, per the module docstring.
NO_SUBJECT_MARKER = "unresolved:__none__"

# Frame drop reasons. Returned alongside the frame so the writer can count them
# separately: a frame the model declined to emit ("absent") and a frame we threw
# away for failing the invariant are not the same event.
DROP_ABSENT = "absent"
DROP_NOT_AN_OBJECT = "not_an_object"
DROP_NO_MEASURE = "no_measure"
DROP_VALUE_NOT_IN_TITLE = "value_not_in_title"
DROP_UNIT_NOT_IN_TITLE = "unit_not_in_title"

_WS = re.compile(r"\s+")
_MEASURE_STRIP = re.compile(r"[^a-z0-9_]+")


def normalize_measure(value: Any, *, max_len: int = 40) -> str | None:
    """Lowercase snake_case measure token, or None when unusable."""
    if not isinstance(value, str):
        return None
    token = _WS.sub("_", value.strip().lower())
    token = _MEASURE_STRIP.sub("_", token).strip("_")
    token = re.sub(r"_{2,}", "_", token)
    return token[:max_len] or None


def normalize_comparator(value: Any) -> str | None:
    """Map a comparator (symbol or word) into :data:`COMPARATORS`, else None."""
    if not isinstance(value, str):
        return None
    raw = value.strip().lower()
    if not raw or raw in {"null", "none", "n/a"}:
        return None
    if raw in COMPARATORS:
        return raw
    collapsed = _WS.sub("_", raw)
    return _COMPARATOR_ALIASES.get(raw) or _COMPARATOR_ALIASES.get(collapsed)


def normalize_horizon_kind(value: Any) -> str | None:
    """Map a horizon into :data:`HORIZON_KINDS`, else None."""
    if not isinstance(value, str):
        return None
    token = _WS.sub("_", value.strip().lower())
    return token if token in HORIZON_KINDS else None


def normalize_value(value: Any) -> str | None:
    """Render an extracted value as the string we will look for in the title.

    Numbers arrive as JSON ints/floats or as strings. A float that is integral
    renders without its ``.0`` (json gives ``70.0`` for a title's ``70``).
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else repr(value)
    if isinstance(value, str):
        token = value.strip()
        if not token or token.lower() in {"null", "none", "n/a"}:
            return None
        return token[:40]
    return None


def value_appears_in_title(value: str, title: str) -> bool:
    r"""Is ``value`` present in ``title`` as a standalone literal?

    Boundary-anchored on BOTH sides so a value cannot be satisfied by a
    fragment of a larger number: ``5`` must not match inside ``2025``, and ``2``
    must not match inside ``2.5``. The comma-stripped title is accepted as well,
    so a title's ``7,000`` satisfies a value of ``7000`` (same digits, same
    order — still literal).

    The ``(?<!\d-)`` guard kills the "2026-27" -> 27 rung class by construction:
    the tail of a compact digit-hyphen-digit range (a season, a date, a
    scoreline) is never a standalone value. A spaced range ("August 10 - August
    16") is untouched, and so is a genuinely negative value, which carries its
    own sign into ``value``.
    """
    if not value or not title:
        return False
    pattern = re.compile(
        r"(?<![0-9A-Za-z.])(?<!\d-)" + re.escape(value) + r"(?![0-9A-Za-z])(?!\.\d)",
        re.IGNORECASE,
    )
    if pattern.search(title):
        return True
    return bool(pattern.search(title.replace(",", "")))


def unit_appears_in_title(unit: str, title: str) -> bool:
    r"""Is ``unit`` present in ``title`` literally?

    Alphanumeric units ("points", "goals") are boundary-matched so ``m`` cannot
    be satisfied by the ``m`` in "Market". The leading boundary also accepts a
    preceding DIGIT, because a magnitude suffix is written flush against its
    number — "13M", "300K", "8.0km" — and rejecting those would throw away the
    exact unit shape the frame most needs to keep verbatim. Symbol units ("%",
    "°F", "$") fall back to a case-insensitive substring, having no word
    boundary to anchor against.
    """
    if not unit or not title:
        return False
    token = unit.strip()
    if not token:
        return False
    if token.isalnum():
        return bool(
            re.search(
                r"(?:\b|(?<=\d))" + re.escape(token) + r"\b", title, re.IGNORECASE
            )
        )
    return token.lower() in title.lower()


def sanitize_cu_frame(
    raw: Any, *, title: str | None
) -> tuple[dict[str, Any] | None, str | None]:
    """Validate the LLM's frame against the title.

    Returns ``(frame, drop_reason)``. Exactly one is non-None: a surviving frame
    carries all five slots (``measure`` always populated, the rest nullable), and
    a dropped frame carries the reason it was dropped so the writer can count
    invariant violations apart from frames the model simply did not emit.
    """
    if raw is None:
        return None, DROP_ABSENT
    if not isinstance(raw, dict):
        return None, DROP_NOT_AN_OBJECT

    measure = normalize_measure(raw.get("measure"))
    if not measure:
        return None, DROP_NO_MEASURE

    title_text = title or ""

    value = normalize_value(raw.get("value"))
    if value is not None and not value_appears_in_title(value, title_text):
        return None, DROP_VALUE_NOT_IN_TITLE

    unit = raw.get("unit")
    unit = unit.strip()[:20] if isinstance(unit, str) and unit.strip() else None
    if unit is not None and unit.lower() in {"null", "none", "n/a"}:
        unit = None
    if unit is not None and not unit_appears_in_title(unit, title_text):
        return None, DROP_UNIT_NOT_IN_TITLE

    return {
        "measure": measure,
        "comparator": normalize_comparator(raw.get("comparator")),
        "value": value,
        "unit": unit,
        "horizon_kind": normalize_horizon_kind(raw.get("horizon_kind")),
    }, None


def clean_entity_mentions(raw: Any, *, max_items: int = 8) -> list[dict[str, str]]:
    """Normalize the v2 ``entities`` array into ``{name, type}`` dicts.

    Tolerates the bare-string form (v1's shape, and what the model falls back to
    under pressure): such a mention keeps an empty ``type``, which ranks last for
    primary-subject selection but still resolves and can still become the
    subject when it is all we have.
    """
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw:
        if isinstance(item, str):
            name, etype = item, ""
        elif isinstance(item, dict):
            name = item.get("name") if isinstance(item.get("name"), str) else ""
            etype = item.get("type") if isinstance(item.get("type"), str) else ""
        else:
            continue
        name = _WS.sub(" ", (name or "").strip())[:80]
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        etype = (etype or "").strip().lower()
        out.append({"name": name, "type": etype if etype in _ENTITY_TYPE_RANK else ""})
        if len(out) >= max_items:
            break
    return out


def unresolved_ref(name: str) -> str:
    """The explicit marker for a mention the registry could not resolve."""
    return f"{UNRESOLVED_PREFIX}{name}"


def is_resolved_ref(ref: Any) -> bool:
    """True for a grounded ref (``entity:12``, ``team:7``), False for a marker.

    The ref prefix is the authoritative resolution signal — NOT ``entity_id``,
    which is populated only for registry entities and is legitimately None on a
    ``team:`` ref from the team-identity fallback.
    """
    return isinstance(ref, str) and bool(ref) and not ref.startswith(UNRESOLVED_PREFIX)


def ground_subjects(
    mentions: Iterable[dict[str, str]],
    resolved: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], str, int | None, bool]:
    """Attach registry refs to entity mentions and pick the primary subject.

    ``resolved`` maps a mention's name to ``{"ref", "entity_id", "kind",
    "source"}`` as produced by the writer's DB lookup (registry alias first,
    team-identity mapping as fallback). Anything absent from that map is written
    with an explicit ``unresolved:`` ref — never dropped, never silently empty.

    Returns ``(subjects, subject_ref, subject_entity_id, subject_resolved)``.
    The primary subject is the highest-preference RESOLVED mention; resolution
    always outranks the model's own ordering, since a grounded ref is the point
    of C2. With nothing resolved it is the highest-preference mention's
    unresolved marker, and with no mentions at all it is
    :data:`NO_SUBJECT_MARKER`.

    ``subject_resolved`` is carried explicitly so no consumer has to infer
    resolution from a null ``subject_entity_id`` — a ``team:`` ref is grounded
    and still has no entity id.
    """
    subjects: list[dict[str, Any]] = []
    for index, mention in enumerate(mentions):
        name = mention.get("name") or ""
        etype = mention.get("type") or ""
        hit = resolved.get(name)
        rank = (_ENTITY_TYPE_RANK.get(etype, len(ENTITY_TYPES)), index)
        if hit:
            subjects.append({
                "name": name,
                "type": etype,
                "ref": hit["ref"],
                "entity_id": hit.get("entity_id"),
                "entity_kind": hit.get("kind"),
                "match": hit.get("source", "alias"),
                "_rank": rank,
            })
        else:
            subjects.append({
                "name": name,
                "type": etype,
                "ref": unresolved_ref(name),
                "entity_id": None,
                "entity_kind": None,
                "match": "unresolved",
                "_rank": rank,
            })

    if not subjects:
        return [], NO_SUBJECT_MARKER, None, False

    resolved_subjects = [s for s in subjects if is_resolved_ref(s["ref"])]
    primary = min(resolved_subjects or subjects, key=lambda s: s["_rank"])
    subject_ref = primary["ref"]
    subject_entity_id = primary["entity_id"]
    subject_resolved = is_resolved_ref(subject_ref)

    for s in subjects:
        s.pop("_rank", None)
    return subjects, subject_ref, subject_entity_id, subject_resolved
