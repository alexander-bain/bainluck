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
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from app.utils.container_machinery import (
    _compute_member_number_parity,
    _effective_market_volume,
    _market_matches_query,
    build_container_machinery_producer,
    discover_machinery_candidate_paths,
    load_machinery_definition,
    produce_container_machinery,
)
from app.utils.discover_fun_tags import (
    CURATED_GROUPING_SETS_PATHS,
    load_fun_markets_registry,
)
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
# Card headline (`text-base font-bold`) inside 390px viewport:
# 390 - 2*16 (Discover feed horizontal padding) - 2*16 (card p-4) - 2 (border) = 324px.
DEFAULT_CARD_HEADLINE_WIDTH_PX_390 = 324.0

BANNED_COPY_WORDS_RE = re.compile(
    r"\b(?:trading|bets?|betting|stale|questions?)\b",
    re.IGNORECASE,
)

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
class PublicAssemblyResult:
    """Full `(a) + (b) + (c)` batch gate result for a single machinery set."""

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


def check_machinery_wording(
    card: Optional[Mapping[str, Any]] = None,
    *,
    container: Optional[Mapping[str, Any]] = None,
    definition: Optional[Mapping[str, Any]] = None,
    slug: str = "",
    max_headline_lines_390px: int = MAX_HEADLINE_LINES_390PX,
) -> WordingCheckResult:
    """Validate card, container, and definition copy against Item 6(b) rules."""
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
        def_fields: list[tuple[str, Any]] = [
            ("definition.name", definition.get("name")),
            ("definition.kicker", definition.get("kicker")),
            ("definition.section_title", definition.get("section_title")),
            ("definition.footer", definition.get("footer")),
        ]
        for idx, sec in enumerate(rule.get("sections") or ()):
            if isinstance(sec, Mapping):
                def_fields.append((f"definition.sections[{idx}].title", sec.get("title")))
                def_fields.append(
                    (f"definition.sections[{idx}].fallback_title", sec.get("fallback_title"))
                )
                def_fields.append((f"definition.sections[{idx}].note", sec.get("note")))
        for loc, val in def_fields:
            if val:
                errors.extend(_scan_text_violations(str(val), location=loc, check_row_rules=False))

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
            for rk in ("name", "label", "answer", "answer_label", "away_short", "home_short"):
                rval = row.get(rk)
                if rval:
                    errors.extend(
                        _scan_text_violations(
                            str(rval),
                            location=f"card.rows[{idx}].{rk}",
                            check_row_rules=True,
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
            for rk in ("label", "answer", "name"):
                if row.get(rk):
                    errors.extend(
                        _scan_text_violations(
                            str(row[rk]),
                            location=f"container.rows[{ridx}].{rk}",
                            check_row_rules=True,
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
                                )
                            )
                    for oidx, out in enumerate(item.get("outcomes") or ()):
                        if isinstance(out, Mapping) and out.get("name"):
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


def discover_changed_machinery_slugs(
    base_ref: str = "origin/master",
    repo_root: Optional[Path] = None,
) -> tuple[str, ...]:
    """Return machinery definition slugs touched by a branch or working tree."""
    root = repo_root or Path(__file__).resolve().parents[3]
    all_paths = discover_machinery_candidate_paths()
    by_slug = {p.stem: p for p in all_paths}

    changed_files: set[str] = set()
    for cmd in (
        ["git", "-C", str(root), "diff", "--name-only", f"{base_ref}...HEAD"],
        ["git", "-C", str(root), "diff", "--name-only"],
        ["git", "-C", str(root), "diff", "--name-only", "--cached"],
        ["git", "-C", str(root), "ls-files", "--others", "--exclude-standard"],
    ):
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode == 0:
            changed_files.update(line.strip() for line in proc.stdout.splitlines() if line.strip())

    slugs: list[str] = []
    seen: set[str] = set()
    curated_tags_touched: set[str] = set()

    for rel in sorted(changed_files):
        p = Path(rel)
        if (
            "backend/data/groupings/candidates" in rel
            and p.name.startswith("machinery-")
            and p.suffix == ".json"
        ):
            stem = p.stem
            if stem in by_slug and stem not in seen:
                seen.add(stem)
                slugs.append(stem)
        elif rel.startswith("backend/data/groupings/batch") and rel.endswith("_curated_sets.json"):
            cur_path = root / rel
            if cur_path.exists():
                doc = json.loads(cur_path.read_text(encoding="utf-8"))
                curated_tags_touched.update(
                    str(k).strip().lower() for k in (doc.get("sets") or {})
                )

    if curated_tags_touched:
        for stem, path in sorted(by_slug.items()):
            if stem in seen:
                continue
            defn = load_machinery_definition(path)
            for sec in defn.get("rule", {}).get("sections") or ():
                sub_tag = str((sec.get("atom_query") or {}).get("fun_sub_tag") or "").strip().lower()
                if sub_tag and sub_tag in curated_tags_touched:
                    seen.add(stem)
                    slugs.append(stem)
                    break

    return tuple(slugs)


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
) -> PublicAssemblyResult:
    """Run public-rule assembly, wording check, and picture policy for one set."""
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
        slug=slug,
    )
    picture_res = audit_picture_policy_for_definition(definition, card=card)

    ok = (
        wording_res.ok
        and picture_res.ok
        and len(mismatches) == 0
        and len(surviving_ids) >= min_items
    )
    status = "PASS" if ok else "FAIL_GATE"
    if len(surviving_ids) < min_items:
        status = "FAIL_PUBLIC_SHORTFALL" if stage == "public" else "PREVIEW_SHORTFALL"
        if stage != "public" and not require_preview_pass and wording_res.ok and picture_res.ok:
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
        card=card,
        container=container_payload,
        feed_item=feed_item,
    )


def _sample_outcomes_for_query(
    aq: Mapping[str, Any],
    base_id: int,
    now_iso: str,
    *,
    prob: float,
    with_opening_delta: float = 0.0,
) -> list[dict[str, Any]]:
    shape = str(aq.get("shape") or "any").strip().lower()
    open_p = max(0.02, min(0.98, round(prob - with_opening_delta, 4)))
    if shape == "binary":
        return [
            {
                "id": base_id * 10 + 1,
                "name": "Yes",
                "probability": prob,
                "opening_probability": open_p,
                "last_updated": now_iso,
            },
            {
                "id": base_id * 10 + 2,
                "name": "No",
                "probability": round(1.0 - prob, 4),
                "opening_probability": round(1.0 - open_p, 4),
                "last_updated": now_iso,
            },
        ]
    if shape == "two_way":
        return [
            {
                "id": base_id * 10 + 1,
                "name": "Democratic Party",
                "probability": prob,
                "opening_probability": open_p,
                "last_updated": now_iso,
            },
            {
                "id": base_id * 10 + 2,
                "name": "Republican Party",
                "probability": round(1.0 - prob, 4),
                "opening_probability": round(1.0 - open_p, 4),
                "last_updated": now_iso,
            },
        ]
    return [
        {
            "id": base_id * 10 + 1,
            "name": "Example Leader",
            "probability": prob,
            "opening_probability": open_p,
            "last_updated": now_iso,
        },
        {
            "id": base_id * 10 + 2,
            "name": "Runner Up",
            "probability": round(max(0.02, min(prob * 0.65, 1.0 - prob - 0.03)), 4),
            "opening_probability": round(max(0.02, min(open_p * 0.65, 1.0 - open_p - 0.03)), 4),
            "last_updated": now_iso,
        },
        {
            "id": base_id * 10 + 3,
            "name": "Third Option",
            "probability": round(max(0.01, min(prob * 0.30, 0.05)), 4),
            "opening_probability": round(max(0.01, min(open_p * 0.30, 0.05)), 4),
            "last_updated": now_iso,
        },
    ]


def build_synthetic_snapshot_for_definition(
    definition: Mapping[str, Any],
    *,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """Build an in-memory snapshot satisfying a definition's structural queries for CI."""
    from app.services.paired_metric_register import load_paired_metric_register
    from app.utils.draw_priced_winner import printable_away
    from app.utils.graded_card import rendered_duel_percents

    cur_now = now or datetime.now(timezone.utc)
    now_iso = cur_now.isoformat()
    res_future = (cur_now + timedelta(days=240)).isoformat()
    hist_old_iso = (cur_now - timedelta(hours=120)).isoformat()
    rule = definition.get("rule") if isinstance(definition.get("rule"), Mapping) else {}
    curated_by_tag = _load_curated_entries_by_sub_tag()
    fun_reg = load_fun_markets_registry()
    paired_reg = load_paired_metric_register()

    events: list[dict[str, Any]] = []
    seen_eids: set[int] = set()
    markets: list[dict[str, Any]] = []
    paired_sets: dict[str, Any] = dict(paired_reg.get("sets") or {})
    market_histories: dict[int, list[dict[str, Any]]] = {}
    seen_mids: set[int] = set()
    category = str(definition.get("category") or "other")

    for sidx, sec in enumerate(rule.get("sections") or ()):
        if not isinstance(sec, Mapping):
            continue
        aq = sec.get("atom_query") if isinstance(sec.get("atom_query"), Mapping) else {}
        kind = str(aq.get("kind") or "markets")

        if kind == "events":
            sport_key = str(
                aq.get("sport_key")
                or ((aq.get("sport_keys") or ["basketball_nba"])[0])
            )
            sport_name = "NFL" if "nfl" in sport_key else ("NBA" if "nba" in sport_key else sport_key)
            needed = max(int(aq.get("min_items") or 3), 4)
            teams = [
                ("Lakers", "Celtics"),
                ("Knicks", "Heat"),
                ("Nuggets", "Suns"),
                ("Warriors", "Mavericks"),
                ("Bucks", "76ers"),
                ("Chiefs", "Bills"),
            ]
            # Seed toss-up probabilities when probability_band is specified.
            band = aq.get("probability_band")
            for eidx in range(needed):
                away, home = teams[eidx % len(teams)]
                if isinstance(band, Sequence) and len(band) == 2:
                    hp = round(0.51 + eidx * 0.02, 4)
                else:
                    hp = round(0.52 + eidx * 0.05, 4)
                ap = round(1.0 - hp, 4)
                c_ap = printable_away(ap, hp, sport_key)
                a_pct, h_pct = rendered_duel_percents(c_ap, hp)
                eid = 910000 + sidx * 100 + eidx
                if eid in seen_eids:
                    continue
                seen_eids.add(eid)
                events.append(
                    {
                        "id": eid,
                        "sport": sport_key,
                        "sport_name": sport_name,
                        "away_team": away,
                        "home_team": home,
                        "commence_time": (cur_now + timedelta(hours=3 + eidx * 4)).isoformat(),
                        "status": "scheduled",
                        "hero_probability": hp,
                        "hero_probability_away": ap,
                        "current_odds": {
                            "away_probability": ap,
                            "home_probability": hp,
                            "away_rendered_percent": int(a_pct),
                            "home_rendered_percent": int(h_pct),
                        },
                    }
                )
            continue

        if kind == "paired_stage":
            # `paired_sets` is pre-populated from `paired_metric_register`.
            continue

        sub_tag = str(aq.get("fun_sub_tag") or "").strip().lower()
        row_specs: list[tuple[int, str]] = []
        if sub_tag and sub_tag in curated_by_tag:
            for e in curated_by_tag[sub_tag]:
                row_specs.append((int(e["id"]), str(e.get("short_label") or f"Market {e['id']}")))
        elif sub_tag:
            for mid in fun_reg.ordered_market_ids:
                meta = fun_reg.markets[mid]
                if any(st.lower() == sub_tag for st in meta.sub_tags):
                    row_specs.append((int(mid), meta.title))
        elif isinstance(aq.get("market_ids"), Sequence):
            for mid_raw in aq["market_ids"]:
                mid = int(mid_raw)
                row_specs.append((mid, f"Configured market {mid}"))
        else:
            all_tokens = [str(t) for t in (aq.get("title_all_tokens") or ())]
            any_tokens = [str(t) for t in (aq.get("any_tokens") or ())]
            count = max(int(aq.get("min_items") or 3), 3)
            base_tokens = " ".join(all_tokens)
            cities = ["Pittsburgh", "Milwaukee", "Minneapolis", "Chicago", "Boston", "Denver"]
            couples = ["Alex & Jordan", "Sam and Taylor", "Riley & Casey", "Morgan and Jamie"]
            if "engaged" in [t.lower() for t in all_tokens]:
                for i in range(max(count, 4)):
                    mid = 930000 + sidx * 100 + i
                    row_specs.append((mid, f"{couples[i % len(couples)]} engaged"))
            elif any_tokens:
                for i in range(max(count, min(len(any_tokens), int(aq.get("max_items") or count)))):
                    tok = any_tokens[i % len(any_tokens)].strip()
                    missing_tokens = [t for t in all_tokens if t.lower() not in tok.lower()]
                    title = " ".join([tok, *missing_tokens]).strip()
                    mid = 930000 + sidx * 100 + i
                    row_specs.append((mid, title))
            else:
                for i in range(count):
                    mid = 930000 + sidx * 100 + i
                    suffix = cities[i % len(cities)]
                    title = f"{base_tokens or sec.get('title') or 'Item'} {suffix}".strip()
                    row_specs.append((mid, title))

        prob_band = aq.get("prob_band")
        high_prob = 0.22 if isinstance(prob_band, Sequence) and len(prob_band) == 2 else 0.78
        low_prob = 0.08 if isinstance(prob_band, Sequence) and len(prob_band) == 2 else 0.32
        max_lead = aq.get("max_lead_probability")
        if isinstance(max_lead, (int, float)) and not isinstance(max_lead, bool):
            high_prob = min(high_prob, max(0.06, float(max_lead) - 0.02))
            low_prob = min(low_prob, max(0.03, high_prob - 0.06))
        req_vol = aq.get("min_lifetime_volume")
        if req_vol is None:
            req_vol = aq.get("min_volume")
        span = max(1, len(row_specs) - 1)
        is_history = kind == "market_history"
        content_kind = str(aq.get("content_kind") or "futures")
        for idx, (mid, title) in enumerate(row_specs):
            if mid in seen_mids:
                continue
            seen_mids.add(mid)
            prob = round(high_prob - (high_prob - low_prob) * (idx / span), 4)
            outs = _sample_outcomes_for_query(
                aq,
                mid,
                now_iso,
                prob=prob,
                with_opening_delta=0.14 if is_history else 0.0,
            )
            markets.append(
                {
                    "id": mid,
                    "name": title,
                    "title": title,
                    "status": "open",
                    "source": "kalshi",
                    "content_kind": content_kind,
                    "category": category,
                    "llm_sport_category": category,
                    "market_tier": 1,
                    "volume": float(max(50000.0, (req_vol or 1000) * 5)),
                    "resolution_date": res_future,
                    "newest_outcome_updated_at": now_iso,
                    "top_outcomes": outs,
                    "outcomes": outs,
                }
            )
            if is_history:
                lead_oid = int(outs[0]["id"])
                market_histories[lead_oid] = [
                    {"outcome_id": lead_oid, "probability": max(0.05, prob - 0.14), "captured_at": hist_old_iso},
                    {"outcome_id": lead_oid, "probability": prob, "captured_at": now_iso},
                ]

    return {
        "events": events,
        "markets": markets,
        "paired_sets": paired_sets,
        "market_histories": market_histories,
    }


__all__ = [
    "BANNED_COPY_WORDS_RE",
    "DEFAULT_CARD_HEADLINE_WIDTH_PX_390",
    "GateViolation",
    "MAX_HEADLINE_LINES_390PX",
    "PicturePolicyResult",
    "PublicAssemblyResult",
    "WordingCheckResult",
    "audit_picture_policy_for_definition",
    "audit_public_assembly_for_definition",
    "build_synthetic_snapshot_for_definition",
    "check_machinery_wording",
    "discover_changed_machinery_slugs",
    "estimate_headline_lines_390px",
]
