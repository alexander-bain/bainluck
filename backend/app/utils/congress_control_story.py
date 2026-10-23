"""Pure identity and chamber-completeness rules for the US Congress control story (#9880).

Anchors membership on Kalshi's whole-chamber party-control event tickers
(``CONTROLS-<YYYY>`` for Senate, ``CONTROLH-<YYYY>`` for House) together with
Kalshi provenance, title chamber confirmation, and a complete two-party board
(Democratic vs Republican). Never derives membership or election edition from
titles alone, canonical season keys, or closing-date arithmetic.
"""

from __future__ import annotations

import re
from typing import Any

US_CONGRESS_CONTROL_STORY_PREFIX = "story:us_congress_control:"
US_CONGRESS_CONTROL_TITLE = "Congress"
US_CONGRESS_CONTROL_QUESTION = "Who wins control of Congress?"

_STORY_KEY_RE = re.compile(r"^story:us_congress_control:(?P<edition>\d{4})$")
_KALSHI_CONTROL_TICKER_RE = re.compile(
    r"^CONTROL(?P<chamber>S|H)-(?P<edition>\d{4})$",
    re.IGNORECASE,
)

# Whole-label US national party patterns, aligned with frontend/lib/seriesColors.ts (#8095).
_DEMOCRATIC_PARTY_RE = re.compile(
    r"^(?:the\s+)?(?:democrats?|democratic(?:\s+party)?)$",
    re.IGNORECASE,
)
_REPUBLICAN_PARTY_RE = re.compile(
    r"^(?:the\s+)?(?:republicans?|republican\s+party|gop)$",
    re.IGNORECASE,
)

_CANDIDACY_OR_NON_CONTROL_RE = re.compile(
    r"\b("
    r"announc(?:e|es|ed|ing)|declar(?:e|es|ed|ing)|enter(?:s|ed|ing)?\s+the\s+race|"
    r"explor(?:e|es|ed|ing)|fil(?:e|es|ed|ing)|launch(?:es|ed|ing)?|"
    r"seek(?:s|ing)?|drop(?:s|ped|ping)?\s+out|withdraw(?:s|n|ing)?|"
    r"suspend(?:s|ed|ing)?|endors(?:e|es|ed|ing)|nominat(?:e|es|ed|ing|ion)|"
    r"running\s+mate|vp\s+pick|cabinet|confirm(?:s|ed|ing|ation)?|"
    r"balance\s+of\s+power|sweep|combo|joint|"
    r"state\s+senate|state\s+house|state\s+legislature|"
    r"how\s+many|number\s+of|margin|seats?\s+won|vote\s+share|popular\s+vote|"
    r"turnout|filibuster|veto|bluest|reddest"
    r")\b",
    re.IGNORECASE,
)
_PARTY_CONTROL_PROMPT_RE = re.compile(
    r"\bparty\b.*\b(?:win|wins|winning|control|controls|controlling|majority)\b",
    re.IGNORECASE,
)
_US_SENATE_RE = re.compile(
    r"\b(?:u\.?s\.?|united\s+states)\s+senate\b",
    re.IGNORECASE,
)
_US_HOUSE_RE = re.compile(
    r"\b(?:u\.?s\.?|united\s+states)\s+house(?:\s+of\s+representatives)?\b",
    re.IGNORECASE,
)
_ANY_SENATE_RE = re.compile(r"\bsenate\b", re.IGNORECASE)
_ANY_HOUSE_RE = re.compile(r"\bhouse\b", re.IGNORECASE)


def is_congress_control_story_key(story_key: str | None) -> bool:
    """Return whether ``story_key`` is a valid edition-scoped US Congress control key."""
    return isinstance(story_key, str) and bool(_STORY_KEY_RE.match(story_key))


def congress_control_edition_from_story_key(story_key: str | None) -> str | None:
    """Return the 4-digit election edition from ``story_key``, or ``None``."""
    if not isinstance(story_key, str):
        return None
    match = _STORY_KEY_RE.match(story_key)
    return match.group("edition") if match else None


def recognized_us_party(label: str | None) -> str | None:
    """Map a whole-label US national party outcome name to its canonical key."""
    if not isinstance(label, str):
        return None
    text = label.strip()
    if not text:
        return None
    if _DEMOCRATIC_PARTY_RE.match(text):
        return "democratic"
    if _REPUBLICAN_PARTY_RE.match(text):
        return "republican"
    return None


def has_two_distinct_us_parties(
    outcome_names: list[str] | tuple[str, ...] | None,
) -> bool:
    """Return whether ``outcome_names`` is an exact two-answer Democratic/Republican pair."""
    if not isinstance(outcome_names, (list, tuple)) or len(outcome_names) != 2:
        return False
    parties = [recognized_us_party(name) for name in outcome_names]
    return parties[0] is not None and parties[1] is not None and parties[0] != parties[1]


def _parse_kalshi_control_anchor(
    raw: str | None,
    *,
    require_kalshi_prefix: bool,
) -> tuple[str, str] | None:
    """Parse ``CONTROLS-<YYYY>`` / ``kalshi:CONTROLS-<YYYY>`` into ``(edition, chamber)``."""
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    if ":" in text:
        prefix, _, rest = text.partition(":")
        if prefix.strip().lower() != "kalshi" or ":" in rest:
            return None
        ticker = rest.strip()
    else:
        if require_kalshi_prefix:
            return None
        ticker = text
    match = _KALSHI_CONTROL_TICKER_RE.match(ticker)
    if not match:
        return None
    chamber = "senate" if match.group("chamber").upper() == "S" else "house"
    return match.group("edition"), chamber


def _title_chamber(market_name: str | None) -> str | None:
    """Confirm that ``market_name`` asks which party wins/controls the US Senate or House."""
    if not isinstance(market_name, str):
        return None
    text = market_name.strip()
    if not text:
        return None
    if _CANDIDACY_OR_NON_CONTROL_RE.search(text):
        return None
    if not _PARTY_CONTROL_PROMPT_RE.search(text):
        return None
    has_us_senate = bool(_US_SENATE_RE.search(text))
    has_us_house = bool(_US_HOUSE_RE.search(text))
    if has_us_senate and not _ANY_HOUSE_RE.search(text):
        return "senate"
    if has_us_house and not _ANY_SENATE_RE.search(text):
        return "house"
    return None


def congress_control_identity_for_market(
    *,
    market_name: str | None,
    external_id: str | None = None,
    outcome_names: list[str] | tuple[str, ...] | None = None,
    source: str | None = None,
    group_id: str | None = None,
    group_type: str | None = None,
    market_type: str | None = None,
    outcome_count: int | None = None,
    remaining_outcome_count: int | None = None,
    mutually_exclusive: bool | None = None,
) -> tuple[str, str] | None:
    """Return ``(edition, chamber)`` when a market satisfies Rule S (#9880), else ``None``."""
    if source is not None and str(source).strip().lower() != "kalshi":
        return None
    if group_type is not None and str(group_type).strip():
        if str(group_type).strip().lower() != "kalshi_event":
            return None
    if market_type is not None and str(market_type).strip().lower() != "duel":
        return None
    if mutually_exclusive is not None and mutually_exclusive is not True:
        return None
    if outcome_count is not None and outcome_count != 2:
        return None
    if remaining_outcome_count is not None and remaining_outcome_count != 0:
        return None

    has_ext = external_id is not None and bool(str(external_id).strip())
    has_grp = group_id is not None and bool(str(group_id).strip())
    if not has_ext and not has_grp:
        return None

    ext_anchor = (
        _parse_kalshi_control_anchor(str(external_id), require_kalshi_prefix=False)
        if has_ext
        else None
    )
    if has_ext and ext_anchor is None:
        return None

    grp_anchor = (
        _parse_kalshi_control_anchor(str(group_id), require_kalshi_prefix=True)
        if has_grp
        else None
    )
    if has_grp and grp_anchor is None:
        return None

    if ext_anchor is not None and grp_anchor is not None and ext_anchor != grp_anchor:
        return None

    anchor = ext_anchor or grp_anchor
    if anchor is None:
        return None

    edition, chamber = anchor
    if _title_chamber(market_name) != chamber:
        return None
    if not has_two_distinct_us_parties(outcome_names):
        return None

    return edition, chamber


def congress_control_story_key_for_market(
    *,
    market_name: str | None,
    external_id: str | None = None,
    outcome_names: list[str] | tuple[str, ...] | None = None,
    source: str | None = None,
    group_id: str | None = None,
    group_type: str | None = None,
    market_type: str | None = None,
    outcome_count: int | None = None,
    remaining_outcome_count: int | None = None,
    mutually_exclusive: bool | None = None,
) -> str | None:
    """Mint ``story:us_congress_control:<edition>`` when a market satisfies Rule S."""
    identity = congress_control_identity_for_market(
        market_name=market_name,
        external_id=external_id,
        outcome_names=outcome_names,
        source=source,
        group_id=group_id,
        group_type=group_type,
        market_type=market_type,
        outcome_count=outcome_count,
        remaining_outcome_count=remaining_outcome_count,
        mutually_exclusive=mutually_exclusive,
    )
    if identity is None:
        return None
    edition, _ = identity
    return f"{US_CONGRESS_CONTROL_STORY_PREFIX}{edition}"


def congress_control_member_identity(item: dict[str, Any]) -> tuple[str, str] | None:
    """Return ``(edition, chamber)`` for a feed item dict, or ``None`` if ineligible."""
    if not isinstance(item, dict) or item.get("type") != "futures":
        return None
    data = item.get("data")
    if not isinstance(data, dict):
        return None

    source = data.get("source")
    if not isinstance(source, str) or source.strip().lower() != "kalshi":
        return None

    top_outcomes = data.get("top_outcomes")
    if not isinstance(top_outcomes, list) or len(top_outcomes) != 2:
        return None
    outcome_names = [
        str(o.get("name") or "") if isinstance(o, dict) else ""
        for o in top_outcomes
    ]

    discover_card = data.get("discover_card")
    remaining = (
        discover_card.get("remaining_outcome_count", 0)
        if isinstance(discover_card, dict)
        else data.get("remaining_outcome_count", 0)
    )

    return congress_control_identity_for_market(
        market_name=data.get("name"),
        external_id=data.get("external_id"),
        outcome_names=outcome_names,
        source=source,
        group_id=data.get("group_id"),
        group_type=data.get("group_type"),
        market_type=data.get("market_type") or "duel",
        outcome_count=data.get("outcome_count", 2),
        remaining_outcome_count=0 if remaining is None else remaining,
        mutually_exclusive=data.get("mutually_exclusive"),
    )


def congress_control_story_key_for_item(item: dict[str, Any]) -> str | None:
    """Return ``story:us_congress_control:<edition>`` for a verified feed item, else ``None``."""
    identity = congress_control_member_identity(item)
    if identity is None:
        return None
    edition, _ = identity
    return f"{US_CONGRESS_CONTROL_STORY_PREFIX}{edition}"


def congress_control_bundle_members(
    story_key: str,
    members: list[dict[str, Any]],
    folded: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]] | None:
    """Verify exact chamber completeness (one Senate + one House for the edition).

    Refuses folding if fewer or more than two distinct chamber representations
    remain after ``_dedupe_same_question_members``, or if any member fails
    Rule S verification for ``story_key``'s edition.
    """
    edition = congress_control_edition_from_story_key(story_key)
    if edition is None or len(members) != 2:
        return None

    chambers: list[str] = []
    for member in members:
        identity = congress_control_member_identity(member)
        if identity is None:
            return None
        member_edition, chamber = identity
        if member_edition != edition:
            return None
        chambers.append(chamber)

    if set(chambers) != {"senate", "house"}:
        return None

    for dup in folded or ():
        dup_identity = congress_control_member_identity(dup)
        if dup_identity is None or dup_identity[0] != edition:
            return None

    return members
