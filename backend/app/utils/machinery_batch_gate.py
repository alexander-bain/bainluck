"""Automated CI & PR batch gate for Discover container machinery (#12288 Item 6).

Provides:
- (a) ``audit_public_assembly_for_definition``: runs public-rule assembly for
      every added or changed set and fails whenever a ``public`` set comes up
      short of its minimum or hits member-number parity errors.
- (b) ``check_machinery_wording`` & ``estimate_headline_lines_390px``: checks
      for the four live wording regressions:
        1. Doubled word across label and answer (e.g. ``"rank: Rank"``).
        2. Repeated name in a single row.
        3. Banned words (``trading``, ``bet``/``bets``/``betting``, ``stale``, ``question``/``questions``).
        4. Card headline exceeding 5 wrapped lines at 390 px mobile width.
- (c) ``audit_picture_policy_for_definition``: reuses ``discover_image_policy``
      to validate card and row imagery against ``verified_discover_art.json``
      and sanitization rules.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Sequence

from app.utils.container_machinery import (
    _compute_member_number_parity,
    _effective_market_volume,
    _market_matches_query,
    build_container_machinery_producer,
    produce_container_machinery,
)
from app.utils.discover_fun_tags import CURATED_GROUPING_SETS_PATHS
from app.utils.discover_image_policy import (
    _REGISTER_PATH,
    is_blocked_pexels_photo,
    is_pexels_url,
    sanitize_discover_feed_item,
)
from app.utils.roundup_containers import (
    RoundupRefusal,
    compose_roundup_container,
    compose_roundup_feed_item,
)

MAX_HEADLINE_LINES_390PX = 5
DUEL_BAR_MIN_TRAILING_PCT = 20
HISTORY_CHART_MIN_SWING_PP = 10
# Card headline (`text-base font-bold`) inside 390px viewport:
# 390 - 2*16 (Discover feed horizontal padding) - 2*16 (card p-4) - 2 (border) = 324px.
DEFAULT_CARD_HEADLINE_WIDTH_PX_390 = 324.0

BANNED_COPY_WORDS_RE = re.compile(
    r"\b(?:trading|bets?|betting|stale|questions?)\b",
    re.IGNORECASE,
)
BANNED_JARGON_UNITS_RE = re.compile(
    r"(?<![A-Za-z])(?:pts|pp|bps)\b",
    re.IGNORECASE,
)
BANNED_CARD_FACE_VENUES_RE = re.compile(
    r"\b(?:kalshi|polymarket|predictit|metaculus|manifold(?:\s+markets)?|"
    r"draftkings|fanduel|betmgm|caesars(?:\s+sportsbook)?|espn\s*bet|bet365|"
    r"fanatics\s+sportsbook|robinhood|pinnacle|bovada|betonline|mybookie|"
    r"betrivers|hard\s+rock\s+bet|underdog|prizepicks)\b",
    re.IGNORECASE,
)
ELLIPSIS_RE = re.compile(r"(?:…|\.\.\.)")

_FIRST_PARTY_CONTAINER_ART_RE = re.compile(
    r"^https://api\.bainluck\.com/api/containers/[^/]+/(?:card-art\.jpg|map\.png)$"
)
_LABEL_ANSWER_SEPARATORS: tuple[str, ...] = (" · ", " — ", " - ", ": ")
_TRAILING_ALPHA_WORD_RE = re.compile(r"([A-Za-z]{2,})[\"'.,)!?]*$")
_LEADING_ALPHA_WORD_RE = re.compile(r"^[\"'(\[]*([A-Za-z]{2,})\b")
_CONSECUTIVE_DUP_WORD_RE = re.compile(r"\b([a-z]{3,})\s+\1\b", re.IGNORECASE)
_REPEATED_PROPER_PHRASE_RE = re.compile(
    r"(?<!\w)([A-Z][A-Za-z0-9'.-]+(?:\s+(?:of|the|and|&|de|van|von|la))?\s+[A-Z][A-Za-z0-9'.-]+)(?!\w)"
)
_ALLOWED_REDUPLICATED_WORDS: frozenset[str] = frozenset(
    {"bora", "mahi", "cha", "choo", "duran", "bon", "pili"}
)
_GENERIC_NON_ENTITY_ANSWERS: frozenset[str] = frozenset(
    {
        "yes",
        "no",
        "other",
        "tie",
        "draw",
        "none",
        "cut",
        "hold",
        "hike",
        "over",
        "under",
        "stay",
        "leave",
        "win",
        "loss",
        "up",
        "down",
        "more",
        "less",
        "same",
        "first",
        "last",
        "any",
    }
)


@dataclass(frozen=True)
class GateViolation:
    """Single machine-check violation emitted by the batch gate."""

    rule: str
    location: str
    detail: str
    text: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "rule": self.rule,
            "location": self.location,
            "detail": self.detail,
            "text": self.text,
        }


@dataclass(frozen=True)
class WordingCheckResult:
    """Result of checking a set's copy against Item 6(b) wording rules."""

    slug: str
    ok: bool
    headline: str
    estimated_lines_390px: int
    errors: tuple[GateViolation, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "ok": self.ok,
            "headline": self.headline,
            "estimated_lines_390px": self.estimated_lines_390px,
            "errors": [e.to_dict() for e in self.errors],
        }


@dataclass(frozen=True)
class PicturePolicyResult:
    """Result of checking a set against Item 6(c) Discover image policy."""

    slug: str
    ok: bool
    errors: tuple[GateViolation, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "ok": self.ok,
            "errors": [e.to_dict() for e in self.errors],
        }


@dataclass(frozen=True)
class FormRulesResult:
    """Result of checking visual-form gating rules (duel >=20%, tile pictures, history >=10pt/sentence)."""

    slug: str
    ok: bool
    errors: tuple[GateViolation, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "ok": self.ok,
            "errors": [e.to_dict() for e in self.errors],
        }


@dataclass(frozen=True)
class PublicAssemblyResult:
    """Full `(a) + (b) + (c) + visual-form` batch gate result for a single machinery set."""

    slug: str
    stage: str
    ok: bool
    status: str
    min_items: int
    member_count: int
    surviving_ids: tuple[int, ...] = ()
    surviving_titles: tuple[str, ...] = ()
    refused_members: tuple[dict[str, Any], ...] = ()
    refusal_reasons: tuple[Any, ...] = ()
    parity_mismatches: tuple[dict[str, Any], ...] = ()
    wording: Optional[WordingCheckResult] = None
    picture: Optional[PicturePolicyResult] = None
    form_rules: Optional[FormRulesResult] = None
    card: Optional[dict[str, Any]] = None
    container: Optional[dict[str, Any]] = None
    feed_item: Optional[dict[str, Any]] = None

    def to_dict(self, *, include_payloads: bool = False) -> dict[str, Any]:
        out: dict[str, Any] = {
            "slug": self.slug,
            "stage": self.stage,
            "ok": self.ok,
            "status": self.status,
            "min_items": self.min_items,
            "member_count": self.member_count,
            "surviving_ids": list(self.surviving_ids),
            "surviving_titles": list(self.surviving_titles),
            "refused_members": list(self.refused_members),
            "refusal_reasons": list(self.refusal_reasons),
            "parity_mismatches": list(self.parity_mismatches),
            "wording": self.wording.to_dict() if self.wording else None,
            "picture": self.picture.to_dict() if self.picture else None,
            "form_rules": self.form_rules.to_dict() if self.form_rules else None,
        }
        if include_payloads:
            out["card"] = self.card
            out["container"] = self.container
        return out


def _char_width_px_16_bold(ch: str) -> float:
    if ch == " ":
        return 4.4
    if ch in "iljftI.,:;'!|()[]/\\\"":
        return 5.0
    if ch in "-":
        return 5.8
    if ch in "—–":
        return 12.5
    if ch in "mw":
        return 12.6
    if ch in "MWOQGD":
        return 12.8
    if ch.isdigit():
        return 9.2
    if ch.isupper():
        return 10.2
    if ch.islower():
        return 8.1
    return 9.0


def _token_width_px_16_bold(token: str) -> float:
    return sum(_char_width_px_16_bold(ch) for ch in token)


def estimate_headline_lines_390px(
    text: str,
    *,
    max_width_px: float = DEFAULT_CARD_HEADLINE_WIDTH_PX_390,
) -> int:
    """Estimate wrapped line count of a Discover card headline at 390 px width."""
    clean = " ".join(str(text or "").split())
    if not clean:
        return 0
    if max_width_px <= 0:
        return 1
    space_w = _char_width_px_16_bold(" ")
    lines = 1
    cur_w = 0.0
    for word in clean.split(" "):
        word_w = _token_width_px_16_bold(word)
        if cur_w == 0.0:
            if word_w <= max_width_px:
                cur_w = word_w
            else:
                # Break an oversized unspaced token evenly across lines.
                lines += max(0, int((word_w - 0.01) // max_width_px))
                cur_w = word_w % max_width_px or max_width_px
        elif cur_w + space_w + word_w <= max_width_px:
            cur_w += space_w + word_w
        else:
            lines += 1
            if word_w <= max_width_px:
                cur_w = word_w
            else:
                lines += max(0, int((word_w - 0.01) // max_width_px))
                cur_w = word_w % max_width_px or max_width_px
    return lines


def _iter_label_answer_splits(text: str) -> list[tuple[str, str]]:
    splits: list[tuple[str, str]] = []
    for sep in _LABEL_ANSWER_SEPARATORS:
        start = 0
        while True:
            idx = text.find(sep, start)
            if idx < 0:
                break
            left = text[:idx].strip()
            right = text[idx + len(sep) :].strip()
            if left and right:
                splits.append((left, right))
            start = idx + len(sep)
    return splits


def _scan_text_violations(
    text: str,
    *,
    location: str,
    check_row_rules: bool = False,
    check_venue: bool = False,
    check_ellipsis: bool = False,
) -> list[GateViolation]:
    out: list[GateViolation] = []
    val = str(text or "").strip()
    if not val:
        return out

    m_banned = BANNED_COPY_WORDS_RE.search(val)
    if m_banned:
        out.append(
            GateViolation(
                rule="banned_word",
                location=location,
                detail=f"Contains banned copy word {m_banned.group(0)!r}",
                text=val,
            )
        )

    m_jargon = BANNED_JARGON_UNITS_RE.search(val)
    if m_jargon:
        out.append(
            GateViolation(
                rule="banned_jargon_unit",
                location=location,
                detail=f"Contains jargon unit {m_jargon.group(0)!r}",
                text=val,
            )
        )

    if check_venue:
        m_venue = BANNED_CARD_FACE_VENUES_RE.search(val)
        if m_venue:
            out.append(
                GateViolation(
                    rule="venue_name_on_card_face",
                    location=location,
                    detail=f"Contains venue name {m_venue.group(0)!r} on card face",
                    text=val,
                )
            )

    if check_ellipsis and ELLIPSIS_RE.search(val):
        out.append(
            GateViolation(
                rule="ellipsis_in_headline_or_number",
                location=location,
                detail="Contains truncated ellipsis in headline or number cell",
                text=val,
            )
        )

    for m_dup in _CONSECUTIVE_DUP_WORD_RE.finditer(val):
        word = m_dup.group(1).lower()
        if word not in _ALLOWED_REDUPLICATED_WORDS:
            out.append(
                GateViolation(
                    rule="doubled_label_answer_word",
                    location=location,
                    detail=f"Doubled consecutive word {m_dup.group(1)!r}",
                    text=val,
                )
            )
            break

    for left, right in _iter_label_answer_splits(val):
        m_left = _TRAILING_ALPHA_WORD_RE.search(left)
        m_right = _LEADING_ALPHA_WORD_RE.search(right)
        if m_left and m_right and m_left.group(1).lower() == m_right.group(1).lower():
            out.append(
                GateViolation(
                    rule="doubled_label_answer_word",
                    location=location,
                    detail=(
                        f"Doubled word across label and answer: "
                        f"{m_left.group(1)!r} -> {m_right.group(1)!r}"
                    ),
                    text=val,
                )
            )
            break

        if check_row_rules:
            ans_clean = re.sub(r"\s*\([^)]*\)\s*", " ", right).strip(" .:;-—–'\"")
            if (
                len(ans_clean) >= 3
                and re.search(r"[A-Za-z]", ans_clean)
                and ans_clean.lower() not in _GENERIC_NON_ENTITY_ANSWERS
                and re.search(rf"(?<!\w){re.escape(ans_clean)}(?!\w)", left, re.IGNORECASE)
            ):
                out.append(
                    GateViolation(
                        rule="repeated_name_in_row",
                        location=location,
                        detail=f"Row repeats name {ans_clean!r} in both label and answer",
                        text=val,
                    )
                )
                break

    if check_row_rules and not any(e.rule == "repeated_name_in_row" for e in out):
        seen_phrases: dict[str, int] = {}
        for m_prop in _REPEATED_PROPER_PHRASE_RE.finditer(val):
            key = " ".join(m_prop.group(1).lower().split())
            seen_phrases[key] = seen_phrases.get(key, 0) + 1
            if seen_phrases[key] >= 2:
                out.append(
                    GateViolation(
                        rule="repeated_name_in_row",
                        location=location,
                        detail=f"Row repeats proper name {m_prop.group(1)!r}",
                        text=val,
                    )
                )
                break

    return out


def _scan_explicit_pair_violations(
    label: str,
    answer: str,
    *,
    location: str,
) -> list[GateViolation]:
    out: list[GateViolation] = []
    l_clean = str(label or "").strip()
    a_clean = str(answer or "").strip()
    if not l_clean or not a_clean:
        return out
    combined = f"{l_clean}: {a_clean}"
    m_left = _TRAILING_ALPHA_WORD_RE.search(l_clean)
    m_right = _LEADING_ALPHA_WORD_RE.search(a_clean)
    if m_left and m_right and m_left.group(1).lower() == m_right.group(1).lower():
        out.append(
            GateViolation(
                rule="doubled_label_answer_word",
                location=location,
                detail=(
                    f"Doubled word across label and answer: "
                    f"{m_left.group(1)!r} -> {m_right.group(1)!r}"
                ),
                text=combined,
            )
        )
    ans_norm = re.sub(r"\s*\([^)]*\)\s*", " ", a_clean).strip(" .:;-—–'\"")
    if (
        len(ans_norm) >= 3
        and re.search(r"[A-Za-z]", ans_norm)
        and ans_norm.lower() not in _GENERIC_NON_ENTITY_ANSWERS
        and re.search(rf"(?<!\w){re.escape(ans_norm)}(?!\w)", l_clean, re.IGNORECASE)
    ):
        out.append(
            GateViolation(
                rule="repeated_name_in_row",
                location=location,
                detail=f"Row repeats name {ans_norm!r} in label and answer",
                text=combined,
            )
        )
    return out


_NUMBER_CELL_KEYS: tuple[str, ...] = (
    "rendered_percent",
    "probability",
    "value",
    "number",
    "metric",
    "delta",
    "change",
    "pct",
    "score",
    "away_pct",
    "home_pct",
    "display_value",
    "rendered_value",
    "stage_1_value",
    "stage_2_value",
    "stage_1_rendered_percent",
    "stage_2_rendered_percent",
    "label",
    "answer",
    "answer_label",
    "name",
)


def _scan_number_cells_for_ellipsis(obj: Mapping[str, Any], *, prefix: str) -> list[GateViolation]:
    out: list[GateViolation] = []
    for key in _NUMBER_CELL_KEYS:
        val = obj.get(key)
        if val is not None and not isinstance(val, (dict, list, bool)):
            txt = str(val).strip()
            if txt and ELLIPSIS_RE.search(txt):
                out.append(
                    GateViolation(
                        rule="ellipsis_in_headline_or_number",
                        location=f"{prefix}.{key}",
                        detail=f"Contains truncated ellipsis in number/cell field {key}",
                        text=txt,
                    )
                )
    return out


def _norm_card_copy(val: Any) -> str:
    return " ".join(str(val or "").split()).casefold()


def _check_duplicate_card_headline(
    card: Optional[Mapping[str, Any]],
    feed_item: Optional[Mapping[str, Any]],
) -> list[GateViolation]:
    """Ensure secondary text slots on a Discover card do not repeat its headline."""
    data = feed_item.get("data") if isinstance(feed_item, Mapping) and isinstance(feed_item.get("data"), Mapping) else {}
    roundup = data.get("roundup") if isinstance(data.get("roundup"), Mapping) else {}
    paired = roundup.get("paired_metric_set") if isinstance(roundup.get("paired_metric_set"), Mapping) else None
    cref = data.get("collection_ref") if isinstance(data.get("collection_ref"), Mapping) else {}

    raw_headline = ""
    if paired is not None:
        raw_headline = str(paired.get("title") or "").strip()
    if not raw_headline and isinstance(card, Mapping):
        raw_headline = str(card.get("title") or "").strip()
    if not raw_headline and isinstance(feed_item, Mapping):
        raw_headline = str(feed_item.get("headline") or "").strip()

    norm_headline = _norm_card_copy(raw_headline)
    if not norm_headline:
        return []

    secondary_slots: list[tuple[str, Any]] = []
    if isinstance(card, Mapping):
        for field_name in ("kicker", "subtitle", "footer"):
            secondary_slots.append((f"card.{field_name}", card.get(field_name)))
        mini_chart = card.get("mini_chart")
        if isinstance(mini_chart, Mapping):
            secondary_slots.append(("card.mini_chart.title", mini_chart.get("title")))
    if paired is not None:
        for field_name in ("kicker", "subtitle", "footer_note"):
            secondary_slots.append((f"paired_metric_set.{field_name}", paired.get(field_name)))
        secondary_slots.append(("collection_ref.name", cref.get("name")))

    violations: list[GateViolation] = []
    for location, candidate_val in secondary_slots:
        candidate_text = str(candidate_val or "").strip()
        if candidate_text and _norm_card_copy(candidate_text) == norm_headline:
            violations.append(
                GateViolation(
                    rule="duplicate_card_headline",
                    location=location,
                    detail=f"Secondary card slot {location} repeats the card headline",
                    text=candidate_text,
                )
            )
    return violations


def check_machinery_wording(
    card: Optional[Mapping[str, Any]] = None,
    *,
    container: Optional[Mapping[str, Any]] = None,
    definition: Optional[Mapping[str, Any]] = None,
    feed_item: Optional[Mapping[str, Any]] = None,
    slug: str = "",
    max_headline_lines_390px: int = MAX_HEADLINE_LINES_390PX,
) -> WordingCheckResult:
    """Validate card, container, and definition copy against Item 6(b) & Item 2 wording rules."""
    resolved_slug = (
        slug
        or str((card or {}).get("slug") or "")
        or str((container or {}).get("slug") or "")
        or str((definition or {}).get("slug") or "")
    )
    errors: list[GateViolation] = []
    headline = ""

    if isinstance(definition, Mapping):
        rule = definition.get("rule") if isinstance(definition.get("rule"), Mapping) else {}
        def_fields: list[tuple[str, Any, bool]] = [
            ("definition.name", definition.get("name"), True),
            ("definition.kicker", definition.get("kicker"), False),
            ("definition.section_title", definition.get("section_title"), True),
            ("definition.footer", definition.get("footer"), False),
        ]
        for idx, sec in enumerate(rule.get("sections") or ()):
            if isinstance(sec, Mapping):
                def_fields.append((f"definition.sections[{idx}].title", sec.get("title"), True))
                def_fields.append(
                    (f"definition.sections[{idx}].fallback_title", sec.get("fallback_title"), True)
                )
                def_fields.append((f"definition.sections[{idx}].note", sec.get("note"), False))
        for loc, val, is_head in def_fields:
            if val:
                errors.extend(
                    _scan_text_violations(
                        str(val),
                        location=loc,
                        check_row_rules=False,
                        check_ellipsis=is_head,
                    )
                )

    if isinstance(card, Mapping):
        headline = str(card.get("title") or "").strip()
        lines = estimate_headline_lines_390px(headline) if headline else 0
        if headline and lines > max_headline_lines_390px:
            errors.append(
                GateViolation(
                    rule="headline_too_long_390px",
                    location="card.title",
                    detail=(
                        f"Headline wraps to {lines} lines at 390 px "
                        f"(max {max_headline_lines_390px}; len={len(headline)})"
                    ),
                    text=headline,
                )
            )
        for field_name in ("kicker", "title", "subtitle", "footer"):
            val = card.get(field_name)
            if val:
                errors.extend(
                    _scan_text_violations(
                        str(val),
                        location=f"card.{field_name}",
                        check_row_rules=False,
                        check_venue=True,
                        check_ellipsis=(field_name == "title"),
                    )
                )
        for idx, row in enumerate(card.get("rows") or ()):
            if not isinstance(row, Mapping):
                continue
            row_label = row.get("label")
            row_answer = row.get("answer") or row.get("answer_label")
            if row_label and row_answer:
                errors.extend(
                    _scan_explicit_pair_violations(
                        str(row_label),
                        str(row_answer),
                        location=f"card.rows[{idx}]",
                    )
                )
            errors.extend(_scan_number_cells_for_ellipsis(row, prefix=f"card.rows[{idx}]"))
            for rk in ("name", "label", "answer", "answer_label", "away_short", "home_short"):
                rval = row.get(rk)
                if rval:
                    errors.extend(
                        _scan_text_violations(
                            str(rval),
                            location=f"card.rows[{idx}].{rk}",
                            check_row_rules=True,
                            check_venue=True,
                            check_ellipsis=True,
                        )
                    )
        for fidx, sf in enumerate(card.get("sibling_fields") or ()):
            if not isinstance(sf, Mapping):
                continue
            if sf.get("title"):
                errors.extend(
                    _scan_text_violations(
                        str(sf["title"]),
                        location=f"card.sibling_fields[{fidx}].title",
                        check_row_rules=False,
                        check_venue=True,
                        check_ellipsis=True,
                    )
                )
            for oidx, out in enumerate(sf.get("outcomes") or ()):
                if isinstance(out, Mapping):
                    errors.extend(
                        _scan_number_cells_for_ellipsis(
                            out, prefix=f"card.sibling_fields[{fidx}].outcomes[{oidx}]"
                        )
                    )
                    if out.get("name"):
                        errors.extend(
                            _scan_text_violations(
                                str(out["name"]),
                                location=f"card.sibling_fields[{fidx}].outcomes[{oidx}].name",
                                check_row_rules=False,
                                check_venue=True,
                                check_ellipsis=True,
                            )
                        )
        mini_ch = card.get("mini_chart")
        if isinstance(mini_ch, Mapping):
            for ck in ("title", "subtitle"):
                if mini_ch.get(ck):
                    errors.extend(
                        _scan_text_violations(
                            str(mini_ch[ck]),
                            location=f"card.mini_chart.{ck}",
                            check_row_rules=False,
                            check_venue=True,
                            check_ellipsis=(ck == "title"),
                        )
                    )
            for sidx, ser in enumerate(mini_ch.get("series") or ()):
                if isinstance(ser, Mapping) and ser.get("name"):
                    errors.extend(
                        _scan_text_violations(
                            str(ser["name"]),
                            location=f"card.mini_chart.series[{sidx}].name",
                            check_row_rules=False,
                            check_venue=True,
                        )
                    )
    else:
        headline = str((container or {}).get("title") or (definition or {}).get("name") or "").strip()
        lines = estimate_headline_lines_390px(headline) if headline else 0

    if isinstance(container, Mapping):
        for field_name in ("title", "subtitle", "caption", "footer"):
            val = container.get(field_name)
            if val and not isinstance(val, Mapping):
                errors.extend(
                    _scan_text_violations(
                        str(val),
                        location=f"container.{field_name}",
                        check_row_rules=False,
                        check_venue=(field_name in ("title", "subtitle", "footer")),
                        check_ellipsis=(field_name == "title"),
                    )
                )
        pms = container.get("paired_metric_set")
        if isinstance(pms, Mapping):
            for pk in ("kicker", "title", "subtitle", "stage_1_label", "stage_2_label"):
                if pms.get(pk):
                    errors.extend(
                        _scan_text_violations(
                            str(pms[pk]),
                            location=f"container.paired_metric_set.{pk}",
                            check_row_rules=False,
                            check_venue=True,
                            check_ellipsis=(pk == "title"),
                        )
                    )
            for eidx, entry in enumerate(pms.get("entries") or ()):
                if not isinstance(entry, Mapping):
                    continue
                errors.extend(
                    _scan_number_cells_for_ellipsis(
                        entry, prefix=f"container.paired_metric_set.entries[{eidx}]"
                    )
                )
                for ek in ("subject", "detail"):
                    if entry.get(ek):
                        errors.extend(
                            _scan_text_violations(
                                str(entry[ek]),
                                location=f"container.paired_metric_set.entries[{eidx}].{ek}",
                                check_row_rules=False,
                                check_venue=True,
                            )
                        )
        for ridx, row in enumerate(container.get("rows") or ()):
            if not isinstance(row, Mapping):
                continue
            if row.get("label") and row.get("answer"):
                errors.extend(
                    _scan_explicit_pair_violations(
                        str(row["label"]),
                        str(row["answer"]),
                        location=f"container.rows[{ridx}]",
                    )
                )
            errors.extend(_scan_number_cells_for_ellipsis(row, prefix=f"container.rows[{ridx}]"))
            for rk in ("label", "answer", "name"):
                if row.get(rk):
                    errors.extend(
                        _scan_text_violations(
                            str(row[rk]),
                            location=f"container.rows[{ridx}].{rk}",
                            check_row_rules=True,
                            check_ellipsis=True,
                        )
                    )
        for sidx, sec in enumerate(container.get("sections") or ()):
            if not isinstance(sec, Mapping):
                continue
            for sk in ("title", "note"):
                if sec.get(sk):
                    errors.extend(
                        _scan_text_violations(
                            str(sec[sk]),
                            location=f"container.sections[{sidx}].{sk}",
                            check_row_rules=False,
                            check_ellipsis=(sk == "title"),
                        )
                    )
            vb = sec.get("visual_block")
            if isinstance(vb, Mapping):
                for iidx, item in enumerate(vb.get("items") or ()):
                    if not isinstance(item, Mapping):
                        continue
                    for ik in ("title", "headline_phrase", "headline_with_phrase", "subtitle"):
                        if item.get(ik):
                            errors.extend(
                                _scan_text_violations(
                                    str(item[ik]),
                                    location=f"container.sections[{sidx}].visual_block.items[{iidx}].{ik}",
                                    check_row_rules=True,
                                    check_ellipsis=(ik == "title"),
                                )
                            )
                    for oidx, out in enumerate(item.get("outcomes") or ()):
                        if isinstance(out, Mapping):
                            errors.extend(
                                _scan_number_cells_for_ellipsis(
                                    out,
                                    prefix=(
                                        f"container.sections[{sidx}].visual_block.items[{iidx}]"
                                        f".outcomes[{oidx}]"
                                    ),
                                )
                            )
                            if out.get("name"):
                                errors.extend(
                                    _scan_text_violations(
                                        str(out["name"]),
                                        location=(
                                            f"container.sections[{sidx}].visual_block.items[{iidx}]"
                                            f".outcomes[{oidx}].name"
                                        ),
                                        check_row_rules=False,
                                    )
                                )

    if isinstance(card, Mapping) or isinstance(feed_item, Mapping):
        errors.extend(_check_duplicate_card_headline(card, feed_item))

    # Deduplicate identical violations while preserving order.
    deduped: list[GateViolation] = []
    seen_keys: set[tuple[str, str, str]] = set()
    for err in errors:
        key = (err.rule, err.location, err.detail)
        if key not in seen_keys:
            seen_keys.add(key)
            deduped.append(err)

    return WordingCheckResult(
        slug=resolved_slug,
        ok=len(deduped) == 0,
        headline=headline,
        estimated_lines_390px=lines,
        errors=tuple(deduped),
    )


def audit_picture_policy_for_definition(
    definition: Mapping[str, Any],
    *,
    card: Optional[Mapping[str, Any]] = None,
) -> PicturePolicyResult:
    """Verify definition and card artwork against ``verified_discover_art.json`` and Discover policy."""
    slug = str(definition.get("slug") or "")
    rule = definition.get("rule") if isinstance(definition.get("rule"), Mapping) else {}
    errors: list[GateViolation] = []

    reg = json.loads(_REGISTER_PATH.read_text(encoding="utf-8"))
    allowed_hosts = set(reg.get("allowed_hosts") or ())
    verified_urls = {
        str(entry.get("url") or "").strip()
        for entry in (reg.get("entries") or ())
        if isinstance(entry, dict)
    }

    url = str(rule.get("card_image_url") or "").strip()
    if url:
        if not url.startswith("https://"):
            errors.append(
                GateViolation(
                    rule="picture_policy",
                    location="rule.card_image_url",
                    detail="card_image_url must use https://",
                    text=url,
                )
            )
        if is_pexels_url(url) or is_blocked_pexels_photo(url):
            errors.append(
                GateViolation(
                    rule="picture_policy",
                    location="rule.card_image_url",
                    detail="Pexels URL is blocked on grouped Discover cards",
                    text=url,
                )
            )
        is_first_party = bool(_FIRST_PARTY_CONTAINER_ART_RE.match(url))
        if not is_first_party:
            if allowed_hosts and not any(host in url for host in allowed_hosts):
                errors.append(
                    GateViolation(
                        rule="picture_policy",
                        location="rule.card_image_url",
                        detail="card_image_url host is not in verified_discover_art allowed_hosts",
                        text=url,
                    )
                )
            if url not in verified_urls:
                errors.append(
                    GateViolation(
                        rule="picture_policy",
                        location="rule.card_image_url",
                        detail="card_image_url is not listed in verified_discover_art.json",
                        text=url,
                    )
                )
            for req_field in (
                "card_image_credit",
                "card_image_author",
                "card_image_license",
                "card_image_source_page",
            ):
                if not str(rule.get(req_field) or "").strip():
                    errors.append(
                        GateViolation(
                            rule="picture_policy",
                            location=f"rule.{req_field}",
                            detail=f"Missing required attribution field {req_field}",
                            text=url,
                        )
                    )
            lic = str(rule.get("card_image_license") or "").lower()
            if lic and not any(tok in lic for tok in ("cc0", "public domain", "tmdb", "verified")):
                errors.append(
                    GateViolation(
                        rule="picture_policy",
                        location="rule.card_image_license",
                        detail=f"Unapproved card image license {rule.get('card_image_license')!r}",
                        text=url,
                    )
                )
        if not str(rule.get("card_image_alt") or "").strip():
            errors.append(
                GateViolation(
                    rule="picture_policy",
                    location="rule.card_image_alt",
                    detail="Missing required card_image_alt text",
                    text=url,
                )
            )
        if rule.get("suppress_card_photo") is not True:
            errors.append(
                GateViolation(
                    rule="picture_policy",
                    location="rule.suppress_card_photo",
                    detail="Explicit card_image_url requires suppress_card_photo=true",
                    text=url,
                )
            )

        if str(definition.get("stage") or "public") == "public":
            mc_probe: dict[str, Any] = {
                "slug": slug,
                "image_url": url,
                "image_alt": str(rule.get("card_image_alt") or ""),
            }
            if rule.get("card_image_credit"):
                mc_probe["image_credit"] = str(rule["card_image_credit"])
            if rule.get("card_image_author"):
                mc_probe["image_author"] = str(rule["card_image_author"])
            if rule.get("card_image_license"):
                mc_probe["image_license"] = str(rule["card_image_license"])
            if rule.get("card_image_source_page"):
                mc_probe["image_source_page"] = str(rule["card_image_source_page"])
            sanitized = sanitize_discover_feed_item(
                {
                    "type": "bundle",
                    "data": {
                        "title": str(definition.get("name") or slug),
                        "image_url": url,
                        "roundup": {"machinery_card": mc_probe},
                    },
                }
            )
            kept_mc = (
                (sanitized.get("data") or {}).get("roundup") or {}
            ).get("machinery_card") or {}
            if kept_mc.get("image_url") != url:
                errors.append(
                    GateViolation(
                        rule="picture_policy",
                        location="sanitize_discover_feed_item",
                        detail="card_image_url was stripped by Discover image sanitizer",
                        text=url,
                    )
                )

    if isinstance(card, Mapping):
        for ridx, row in enumerate(card.get("rows") or ()):
            if not isinstance(row, Mapping):
                continue
            for art_key in ("art", "away_art", "home_art"):
                art = row.get(art_key)
                if not isinstance(art, Mapping):
                    continue
                rurl = str(art.get("url") or "").strip()
                if not rurl:
                    continue
                if not rurl.startswith("https://") or is_pexels_url(rurl) or is_blocked_pexels_photo(rurl):
                    errors.append(
                        GateViolation(
                            rule="picture_policy",
                            location=f"card.rows[{ridx}].{art_key}.url",
                            detail="Row art URL fails Discover HTTPS/non-Pexels policy",
                            text=rurl,
                        )
                    )

    return PicturePolicyResult(slug=slug, ok=len(errors) == 0, errors=tuple(errors))


def _has_real_tile_picture(art: Any) -> bool:
    if not isinstance(art, Mapping):
        return False
    if str(art.get("kind") or "").strip().lower() == "monogram":
        return False
    url = str(art.get("url") or "").strip()
    return (
        url.startswith("https://")
        and not is_pexels_url(url)
        and not is_blocked_pexels_photo(url)
    )


def _side_percent(side: Mapping[str, Any]) -> Optional[float]:
    rp = side.get("rendered_percent")
    if isinstance(rp, (int, float)) and not isinstance(rp, bool):
        return float(rp)
    prob = side.get("probability")
    if isinstance(prob, (int, float)) and not isinstance(prob, bool):
        return float(prob) * 100.0
    return None


def _history_window_swing_pp(chart: Mapping[str, Any]) -> float:
    series = [s for s in (chart.get("series") or ()) if isinstance(s, Mapping)]
    point_spans: list[float] = []
    for s in series:
        vals: list[float] = []
        for pt in s.get("points") or ():
            if not isinstance(pt, Mapping):
                continue
            if isinstance(pt.get("pct"), (int, float)) and not isinstance(pt.get("pct"), bool):
                vals.append(float(pt["pct"]))
            elif isinstance(pt.get("probability"), (int, float)) and not isinstance(
                pt.get("probability"), bool
            ):
                vals.append(float(pt["probability"]) * 100.0)
        if len(vals) >= 2:
            point_spans.append(max(vals) - min(vals))
    if point_spans:
        return max(point_spans)
    raw_swing = chart.get("max_swing_pp")
    if isinstance(raw_swing, (int, float)) and not isinstance(raw_swing, bool):
        return float(raw_swing)
    return 0.0


_SENTENCE_FINITE_VERB_RE = re.compile(
    r"\b(?:is|are|was|were|be|been|has|have|had|moved|slid|rose|fell|jumped|dropped|"
    r"climbed|surged|rallied|rebounded|narrowed|widened|led|leads|trails|held|"
    r"holds|gained|lost|shifted|swung|opened|closed|remained|stays|stayed|shows|"
    r"showed|tracks|tracked|priced|repriced|traded|sits|stand|stands|reaches|reached|hits|"
    r"hit|beats|beat|wins|won|earns|earned|finished|finishes|pushed|pulled|cooled|"
    r"dipped|spiked|tumbled|tightened|settled|backed|cut|raised|trimmed)\b",
    re.IGNORECASE,
)
_JOINED_TITLES_TEMPLATE_RE = re.compile(
    r"(?:^\s*(?:7-day\s+)?odds\s+movement\s+across\b|"
    r"^\s*a\s+look\s+back\s+at\b.+\bacross\b.+\band\b|"
    r"\b(?:which|what|who|will|when|whether)\b.+\b(?:and|or)\b\s+(?:which|what|who|will|when|whether)\b|"
    r",\s*and\s+more\.?\s*$)",
    re.IGNORECASE,
)


def _check_history_chart_subhead(
    subtitle: str,
    *,
    location: str,
    candidate_titles: Sequence[str] = (),
) -> list[GateViolation]:
    sub = str(subtitle or "").strip()
    if len(sub) < 12:
        return [
            GateViolation(
                rule="form_history_chart_bad_subhead",
                location=location,
                detail="History chart subhead must be a written sentence (missing or too short)",
                text=sub,
            )
        ]
    if any(sep in sub for sep in ("?", "·", "|", ";", "…", "...", " / ")):
        return [
            GateViolation(
                rule="form_history_chart_bad_subhead",
                location=location,
                detail="History chart subhead contains non-sentence separator or question mark",
                text=sub,
            )
        ]
    if not sub.endswith((".", "!")):
        return [
            GateViolation(
                rule="form_history_chart_bad_subhead",
                location=location,
                detail="History chart subhead must end cleanly as a full written sentence",
                text=sub,
            )
        ]
    if _JOINED_TITLES_TEMPLATE_RE.search(sub):
        return [
            GateViolation(
                rule="form_history_chart_bad_subhead",
                location=location,
                detail="History chart subhead joins market titles or topic fragments instead of writing a sentence",
                text=sub,
            )
        ]
    sub_low = sub.lower()
    matched_titles = 0
    for t in candidate_titles:
        clean_t = str(t or "").strip().rstrip("?").strip().lower()
        if len(clean_t) >= 8 and clean_t in sub_low:
            matched_titles += 1
            if matched_titles >= 2:
                return [
                    GateViolation(
                        rule="form_history_chart_bad_subhead",
                        location=location,
                        detail="History chart subhead concatenates market titles from the set",
                        text=sub,
                    )
                ]
    if not _SENTENCE_FINITE_VERB_RE.search(sub):
        return [
            GateViolation(
                rule="form_history_chart_bad_subhead",
                location=location,
                detail="History chart subhead must read as a written sentence with a verb, not a noun list",
                text=sub,
            )
        ]
    return []


def check_machinery_form_rules(
    *,
    card: Optional[Mapping[str, Any]] = None,
    container: Optional[Mapping[str, Any]] = None,
    slug: str = "",
    check_tile_pictures: bool = True,
) -> FormRulesResult:
    """Enforce visual-form admission rules learned from the 390 px sheet (Item 2)."""
    resolved_slug = (
        slug
        or str((card or {}).get("slug") or "")
        or str((container or {}).get("slug") or "")
    )
    errors: list[GateViolation] = []

    candidate_titles: list[str] = []
    if isinstance(container, Mapping):
        for sec in container.get("sections") or ():
            if not isinstance(sec, Mapping):
                continue
            vb = sec.get("visual_block")
            if isinstance(vb, Mapping):
                for it in vb.get("items") or ():
                    if isinstance(it, Mapping):
                        for tk in ("title", "raw_title"):
                            if it.get(tk):
                                candidate_titles.append(str(it[tk]))

    if isinstance(card, Mapping):
        c_form = str(card.get("form_id") or "").strip()
        c_scale = bool(card.get("scale_ordered"))
        c_rows = [r for r in (card.get("rows") or ()) if isinstance(r, Mapping)]

        if c_form == "duel_bar":
            if len(c_rows) != 2:
                errors.append(
                    GateViolation(
                        rule="form_duel_trailing_under_20",
                        location="card.rows",
                        detail=f"duel_bar card must compare 2 sides (got {len(c_rows)})",
                        text=str(card.get("title") or ""),
                    )
                )
            else:
                pcts = [p for r in c_rows if (p := _side_percent(r)) is not None]
                if len(pcts) != 2 or min(pcts) < DUEL_BAR_MIN_TRAILING_PCT:
                    trailing = min(pcts) if pcts else 0.0
                    errors.append(
                        GateViolation(
                            rule="form_duel_trailing_under_20",
                            location="card.rows",
                            detail=(
                                f"duel_bar trailing side is {trailing:g}% "
                                f"(requires >= {DUEL_BAR_MIN_TRAILING_PCT}%)"
                            ),
                            text=str(card.get("title") or ""),
                        )
                    )

        if check_tile_pictures and not c_scale:
            if c_form == "contender_spotlight":
                shown = c_rows[:3]
                if shown:
                    missing = [
                        str(r.get("name") or r.get("label") or idx)
                        for idx, r in enumerate(shown)
                        if not _has_real_tile_picture(r.get("art"))
                    ]
                    if missing:
                        errors.append(
                            GateViolation(
                                rule="form_spotlight_missing_picture",
                                location="card.rows",
                                detail=(
                                    "contender_spotlight card requires a real picture on every tile "
                                    f"(missing: {', '.join(missing)})"
                                ),
                                text=str(card.get("title") or ""),
                            )
                        )
            elif c_form == "sibling_fields_grid":
                sibs = [s for s in (card.get("sibling_fields") or ()) if isinstance(s, Mapping)]
                if sibs:
                    missing = [
                        str(sf.get("title") or idx)
                        for idx, sf in enumerate(sibs[:4])
                        if not (
                            (sf.get("outcomes") or ())
                            and isinstance(sf["outcomes"][0], Mapping)
                            and _has_real_tile_picture(sf["outcomes"][0].get("art"))
                        )
                    ]
                else:
                    missing = [
                        str(r.get("name") or r.get("label") or idx)
                        for idx, r in enumerate(c_rows[:3])
                        if not _has_real_tile_picture(r.get("art"))
                    ]
                if missing:
                    errors.append(
                        GateViolation(
                            rule="form_tile_grid_missing_picture",
                            location="card.sibling_fields" if sibs else "card.rows",
                            detail=(
                                "sibling_fields_grid tile grid requires a real picture on every tile "
                                f"(missing: {', '.join(missing)})"
                            ),
                            text=str(card.get("title") or ""),
                        )
                    )

        if c_form == "probability_history_chart":
            chart = card.get("mini_chart")
            swing = _history_window_swing_pp(chart) if isinstance(chart, Mapping) else 0.0
            if swing < HISTORY_CHART_MIN_SWING_PP:
                errors.append(
                    GateViolation(
                        rule="form_history_chart_under_10_pts",
                        location="card.mini_chart",
                        detail=(
                            f"probability_history_chart moved {swing:g} percentage points in window "
                            f"(requires >= {HISTORY_CHART_MIN_SWING_PP})"
                        ),
                        text=str(card.get("title") or ""),
                    )
                )
            errors.extend(
                _check_history_chart_subhead(
                    str(card.get("subtitle") or ""),
                    location="card.subtitle",
                    candidate_titles=candidate_titles,
                )
            )

    if isinstance(container, Mapping):
        for sidx, sec in enumerate(container.get("sections") or ()):
            if not isinstance(sec, Mapping):
                continue
            vb = sec.get("visual_block")
            if not isinstance(vb, Mapping):
                continue
            s_form = str(vb.get("form_id") or "").strip()
            items = [it for it in (vb.get("items") or ()) if isinstance(it, Mapping)]
            if s_form == "duel_bar":
                for iidx, it in enumerate(items):
                    outs = [o for o in (it.get("outcomes") or ()) if isinstance(o, Mapping)]
                    pcts = [p for o in outs[:2] if (p := _side_percent(o)) is not None]
                    if len(pcts) >= 2 and min(pcts) < DUEL_BAR_MIN_TRAILING_PCT:
                        errors.append(
                            GateViolation(
                                rule="form_duel_trailing_under_20",
                                location=f"container.sections[{sidx}].visual_block.items[{iidx}]",
                                detail=(
                                    f"duel_bar trailing side is {min(pcts):g}% "
                                    f"(requires >= {DUEL_BAR_MIN_TRAILING_PCT}%)"
                                ),
                                text=str(it.get("title") or ""),
                            )
                        )
            elif (
                check_tile_pictures
                and s_form == "contender_spotlight"
                and items
                and not any(it.get("scale_ordered") for it in items)
            ):
                for iidx, it in enumerate(items):
                    outs = [o for o in (it.get("outcomes") or ()) if isinstance(o, Mapping)]
                    shown = outs[:3]
                    missing = [
                        str(o.get("name") or oidx)
                        for oidx, o in enumerate(shown)
                        if not _has_real_tile_picture(o.get("art"))
                    ]
                    if missing:
                        errors.append(
                            GateViolation(
                                rule="form_spotlight_missing_picture",
                                location=f"container.sections[{sidx}].visual_block.items[{iidx}]",
                                detail=(
                                    "contender_spotlight section requires a real picture on every tile "
                                    f"(missing: {', '.join(missing)})"
                                ),
                                text=str(it.get("title") or ""),
                            )
                        )

    return FormRulesResult(slug=resolved_slug, ok=len(errors) == 0, errors=tuple(errors))


def _load_curated_entries_by_sub_tag() -> dict[str, list[dict[str, Any]]]:
    by_sub_tag: dict[str, list[dict[str, Any]]] = {}
    for cp in CURATED_GROUPING_SETS_PATHS:
        if not cp.exists():
            continue
        doc = json.loads(cp.read_text(encoding="utf-8"))
        for sub_tag, spec in (doc.get("sets") or {}).items():
            if isinstance(spec, Mapping):
                by_sub_tag[str(sub_tag).strip().lower()] = [
                    dict(e) for e in (spec.get("entries") or ()) if isinstance(e, Mapping)
                ]
    return by_sub_tag


def _definition_min_items(definition: Mapping[str, Any]) -> int:
    rule = definition.get("rule") if isinstance(definition.get("rule"), Mapping) else {}
    total = 0
    for sec in rule.get("sections") or ():
        if not isinstance(sec, Mapping):
            continue
        aq = sec.get("atom_query") if isinstance(sec.get("atom_query"), Mapping) else {}
        if aq.get("min_items") is not None:
            total += int(aq["min_items"])
        elif aq.get("kind") == "paired_metric":
            total += int(aq.get("min_entries") or 4)
    if total == 0 and rule.get("min_items") is not None:
        total = int(rule["min_items"])
    return total


def _diagnose_snapshot_candidates(
    definition: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    surviving_ids: set[int],
    curated_by_tag: Mapping[str, list[dict[str, Any]]],
    *,
    now: datetime,
) -> list[dict[str, Any]]:
    rule = definition.get("rule") if isinstance(definition.get("rule"), Mapping) else {}
    markets_by_id = {
        int(m["id"]): m
        for m in (snapshot.get("markets") or ())
        if isinstance(m, Mapping) and m.get("id") is not None
    }
    refused: list[dict[str, Any]] = []
    seen_refused: set[int] = set()

    for sec in rule.get("sections") or ():
        if not isinstance(sec, Mapping):
            continue
        aq = sec.get("atom_query") if isinstance(sec.get("atom_query"), Mapping) else {}
        sub_tag = str(aq.get("fun_sub_tag") or "").strip().lower()
        curated = curated_by_tag.get(sub_tag) or []
        candidate_ids: list[int] = []
        title_hints: dict[int, str] = {}
        if curated:
            for e in curated:
                if e.get("id") is not None:
                    cid = int(e["id"])
                    candidate_ids.append(cid)
                    title_hints[cid] = str(e.get("short_label") or f"market {cid}")
        elif isinstance(aq.get("market_ids"), Sequence):
            for cid_raw in aq["market_ids"]:
                candidate_ids.append(int(cid_raw))

        raw_min_vol = aq.get("min_lifetime_volume")
        if raw_min_vol is None:
            raw_min_vol = aq.get("min_volume")
        min_volume = float(raw_min_vol) if raw_min_vol is not None else None
        for cid in candidate_ids:
            if cid in surviving_ids or cid in seen_refused:
                continue
            mkt = markets_by_id.get(cid)
            if mkt is None:
                seen_refused.add(cid)
                refused.append(
                    {
                        "market_id": cid,
                        "title": title_hints.get(cid, f"market {cid}"),
                        "reason": "missing_or_closed_in_snapshot",
                    }
                )
                continue
            eff_vol = _effective_market_volume(
                mkt.get("volume"),
                volume_24h=mkt.get("volume_24h"),
                market_metadata=mkt.get("market_metadata"),
            )
            if min_volume is not None and (eff_vol is None or eff_vol < min_volume):
                reason = "missing_volume" if eff_vol is None else "below_min_volume"
            elif not _market_matches_query(mkt, aq, now_dt=now):
                reason = "filtered_by_section_query_or_staleness"
            else:
                reason = "surviving_subset_refused_elsewhere"
            seen_refused.add(cid)
            refused.append(
                {
                    "market_id": cid,
                    "title": str(mkt.get("title") or title_hints.get(cid) or f"market {cid}"),
                    "reason": reason,
                }
            )
    return refused


async def audit_public_assembly_for_definition(
    definition: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    *,
    now: Optional[datetime] = None,
    require_preview_pass: bool = False,
    check_tile_pictures: bool = True,
) -> PublicAssemblyResult:
    """Run public-rule assembly, wording check, picture policy, and visual-form rules."""
    cur_now = now or datetime.now(timezone.utc)
    slug = str(definition.get("slug") or "")
    stage = str(definition.get("stage") or "public")
    min_items = _definition_min_items(definition)
    curated_by_tag = _load_curated_entries_by_sub_tag()

    picture_res = audit_picture_policy_for_definition(definition)
    res = await produce_container_machinery(snapshot, definition, now=cur_now)

    if isinstance(res, RoundupRefusal):
        refused = _diagnose_snapshot_candidates(
            definition, snapshot, set(), curated_by_tag, now=cur_now
        )
        wording_def = check_machinery_wording(definition=definition, slug=slug)
        fail = stage == "public" or require_preview_pass or not wording_def.ok or not picture_res.ok
        status = (
            "FAIL_PUBLIC_SHORTFALL"
            if (stage == "public" or require_preview_pass)
            else "PREVIEW_SHORTFALL"
        )
        return PublicAssemblyResult(
            slug=slug,
            stage=stage,
            ok=not fail,
            status=status,
            min_items=min_items,
            member_count=0,
            refused_members=tuple(refused),
            refusal_reasons=tuple(res.reasons),
            wording=wording_def,
            picture=picture_res,
            form_rules=FormRulesResult(slug=slug, ok=True),
        )

    producer = build_container_machinery_producer(definition)
    container_payload = compose_roundup_container(producer, res) or {}
    feed_item = compose_roundup_feed_item(producer, res) or {}
    _, parity = _compute_member_number_parity(feed_item, container_payload)
    mismatches = tuple(parity.get("card_mismatches") or ()) + tuple(
        parity.get("page_mismatches") or ()
    )

    surviving_ids = tuple(int(m["id"]) for m in res.members if m.get("id") is not None)
    surviving_titles = tuple(
        str(r.get("label") or r.get("title") or m.get("title") or m.get("id"))
        for r, m in zip(res.rows, res.members, strict=False)
    )
    if not surviving_titles:
        surviving_titles = tuple(str(m.get("id")) for m in res.members)

    refused = _diagnose_snapshot_candidates(
        definition, snapshot, set(surviving_ids), curated_by_tag, now=cur_now
    )
    card = dict(res.machinery_card) if isinstance(res.machinery_card, Mapping) else {}
    wording_res = check_machinery_wording(
        card=card,
        container=container_payload,
        definition=definition,
        feed_item=feed_item,
        slug=slug,
    )
    picture_res = audit_picture_policy_for_definition(definition, card=card)
    form_res = check_machinery_form_rules(
        card=card,
        container=container_payload,
        slug=slug,
        check_tile_pictures=check_tile_pictures,
    )

    ok = (
        wording_res.ok
        and picture_res.ok
        and form_res.ok
        and len(mismatches) == 0
        and len(surviving_ids) >= min_items
    )
    status = "PASS" if ok else "FAIL_GATE"
    if len(surviving_ids) < min_items:
        status = "FAIL_PUBLIC_SHORTFALL" if stage == "public" else "PREVIEW_SHORTFALL"
        if (
            stage != "public"
            and not require_preview_pass
            and wording_res.ok
            and picture_res.ok
            and form_res.ok
        ):
            ok = True

    return PublicAssemblyResult(
        slug=slug,
        stage=stage,
        ok=ok,
        status=status,
        min_items=min_items,
        member_count=len(surviving_ids),
        surviving_ids=surviving_ids,
        surviving_titles=surviving_titles,
        refused_members=tuple(refused),
        parity_mismatches=mismatches,
        wording=wording_res,
        picture=picture_res,
        form_rules=form_res,
        card=card,
        container=container_payload,
        feed_item=feed_item,
    )


__all__ = [
    "BANNED_CARD_FACE_VENUES_RE",
    "BANNED_COPY_WORDS_RE",
    "BANNED_JARGON_UNITS_RE",
    "DEFAULT_CARD_HEADLINE_WIDTH_PX_390",
    "DUEL_BAR_MIN_TRAILING_PCT",
    "ELLIPSIS_RE",
    "FormRulesResult",
    "GateViolation",
    "HISTORY_CHART_MIN_SWING_PP",
    "MAX_HEADLINE_LINES_390PX",
    "PicturePolicyResult",
    "PublicAssemblyResult",
    "WordingCheckResult",
    "audit_picture_policy_for_definition",
    "audit_public_assembly_for_definition",
    "check_machinery_form_rules",
    "check_machinery_wording",
    "estimate_headline_lines_390px",
]
