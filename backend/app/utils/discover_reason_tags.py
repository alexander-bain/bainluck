"""Canonical Discover human-label reason tags and legacy aliases."""

from __future__ import annotations

from typing import Iterable

CANONICAL_REASON_TAGS = frozenset(
    {
        "movement",
        "public_story",
        "high_stakes",
        "close_probability",
        "source_disagreement",
        "celebrity_or_person",
        "sports_relevance",
        "fun_or_weird",
        "timely",
        "surprising_probability",
        "major_event",
        "finance_ladder",
        "commodity_ladder",
        "too_niche",
        "duplicate",
        "stale",
        "unclear",
        "bad_image",
        "low_stakes",
        "repetitive",
        "misleading",
        "generic_hook",
        "wrong_category",
        "not_a_real_prediction",
        # UX-P117 / #2060 item 1. The one chip in Alex's six with nothing to fold
        # onto: `misleading` is about the HOOK TEXT overselling a card, which is a
        # different complaint from "the number itself is wrong", and the web
        # ReviewTab's `too_high`/`too_low` were never registered here at all — so
        # a labeller who thought the probability was wrong had no canonical way to
        # say it. Both directions alias onto this because the defect is the same
        # one (`data_bug`); which way it is wrong belongs in `notes`.
        "wrong_probability",
    }
)

REASON_TAG_ALIASES = {
    "fun": "fun_or_weird",
    "weird": "fun_or_weird",
    "funny": "fun_or_weird",
    "important": "high_stakes",
    "newsworthy": "public_story",
    "public": "public_story",
    "close": "close_probability",
    "disagreement": "source_disagreement",
    "celebrity": "celebrity_or_person",
    "person": "celebrity_or_person",
    "sports": "sports_relevance",
    "surprising": "surprising_probability",
    "major": "major_event",
    "needs_context": "unclear",
    "no_context": "unclear",
    "missing_context": "unclear",
    "confusing": "unclear",
    "bad_explanation": "generic_hook",
    "generic": "generic_hook",
    "wrong_image": "bad_image",
    "wrong_category": "wrong_category",
    "niche": "too_niche",
    "too_niche": "too_niche",
    "duplicate_family": "duplicate",
    "bucket": "repetitive",
    "dated_bucket": "repetitive",
    # ── UX-P117: the forks the store was already carrying ────────────────────
    #
    # `boring` is what `/admin/labeling` writes and it was never registered, so
    # `canonical_reason_tag` preserved it verbatim as an unknown tag. Measured on
    # production 2026-08-21 that is 2 rows sitting beside 6 `low_stakes` — one
    # complaint, counted twice, and each half too small to look like anything.
    # Folding it here fixes new writes; the 2 historical rows keep their spelling
    # and are folded at ROUTE time by the same function, which is the point of
    # canonicalising on read as well as write.
    "boring": "low_stakes",
    "dull": "low_stakes",
    # The web ReviewTab has offered these two since it shipped and neither was
    # ever canonical, so both would have landed as unknown tags.
    "too_high": "wrong_probability",
    "too_low": "wrong_probability",
    "wrong_prob": "wrong_probability",
    "wrong_probability": "wrong_probability",
}


def canonical_reason_tag(tag: object) -> str:
    """Return the canonical reason tag for a raw label chip.

    Unknown tags are preserved in normalized snake_case form so historical or
    experimental labels stay analyzable instead of being dropped.
    """

    normalized = _normalize_tag(tag)
    if not normalized:
        return ""
    return REASON_TAG_ALIASES.get(normalized, normalized)


def canonical_reason_tags(tags: Iterable[object] | str | None) -> list[str]:
    """Normalize reason tags, preserving input order and removing duplicates."""

    if not tags:
        return []
    raw_tags = tags.split(",") if isinstance(tags, str) else tags
    seen: set[str] = set()
    normalized_tags: list[str] = []
    for raw_tag in raw_tags:
        tag = canonical_reason_tag(raw_tag)
        if tag and tag not in seen:
            seen.add(tag)
            normalized_tags.append(tag)
    return normalized_tags


def _normalize_tag(tag: object) -> str:
    return str(tag or "").strip().lower().replace("-", "_").replace(" ", "_")
