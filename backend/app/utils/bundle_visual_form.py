"""Single source of truth for Discover bundle visual form identifiers (353: A).

Machinery round-ups already carry ``data.roundup.machinery_card.form_id``. Older
(non-machinery) round-ups, themes, and comparisons draw in specific frontend/iOS
layouts too, but carried no ``form_id`` on the wire — leaving 353: A unable to
count or diversify them alongside machinery cards.

This module assigns an additive ``data["form_id"]`` (and ``data["roundup"]["form_id"]``
for round-ups) naming **how the card draws**, without ever adding or mutating
``machinery_card`` so card rendering and appearance stay byte-for-byte unchanged.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Optional

from app.utils.congress_control_story import is_congress_control_story_key
from app.utils.deadline_family_story import is_deadline_family_story_key

FORM_BENCHMARK_STRIP = "benchmark_strip"
FORM_MATCHUP_STRIP = "matchup_strip"
FORM_PAIRED_STAGE_BARS = "paired_stage_bars"
FORM_DEADLINE_LADDER = "deadline_ladder"
FORM_PARTY_CONTROL_BARS = "party_control_bars"
FORM_THEME_COMPACT_ROWS = "theme_compact_rows"
FORM_COMPARISON_COMPACT_ROWS = "comparison_compact_rows"

# Opening-mix look-alike grouping (#13542 / 353: A): cards that draw the same
# visual layout count as one look under the opening form cap while keeping their
# distinct wire `form_id` intact.
OPENING_FORM_LOOK_ALIASES: dict[str, str] = {
    FORM_THEME_COMPACT_ROWS: "compact_rows",
    FORM_COMPARISON_COMPACT_ROWS: "compact_rows",
    FORM_PARTY_CONTROL_BARS: "compact_rows",
    "coin_flip_matchups": "duel_matchups",
    "matchup_slate": "duel_matchups",
}


def discover_opening_form_look(form_id: Optional[str]) -> Optional[str]:
    """Map look-alike visual form names to one counting key for opening mix."""
    cleaned = _nonempty_str(form_id)
    if cleaned is None:
        return None
    return OPENING_FORM_LOOK_ALIASES.get(cleaned, cleaned)


def _nonempty_str(value: Any) -> Optional[str]:
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return None


def infer_bundle_visual_form_id(data: Mapping[str, Any]) -> Optional[str]:
    """Infer the visual form name describing how a ``type=='bundle'`` card draws."""
    if not isinstance(data, Mapping):
        return None
    kind = _nonempty_str(data.get("kind"))

    if kind == "roundup":
        roundup = data.get("roundup")
        if isinstance(roundup, Mapping):
            mc = roundup.get("machinery_card")
            if isinstance(mc, Mapping):
                mc_form = _nonempty_str(mc.get("form_id"))
                if mc_form is not None:
                    return mc_form
            explicit_ru_form = _nonempty_str(roundup.get("form_id"))
            if explicit_ru_form is not None:
                return explicit_ru_form
            paired = roundup.get("paired_metric_set")
            if isinstance(paired, Mapping) and paired:
                return FORM_PAIRED_STAGE_BARS
            pres = _nonempty_str(roundup.get("presentation"))
            if pres is not None and pres.lower() == "strip":
                return FORM_MATCHUP_STRIP
        # Legacy Round-ups without `presentation="strip"` or `paired_metric_set`
        # render vertical labeled rows with a percentage + bar (`RoundupRow`),
        # matching machinery `benchmark_strip` so 353: A counts them together.
        return FORM_BENCHMARK_STRIP

    if kind == "theme":
        story_key = _nonempty_str(data.get("story_key"))
        if data.get("deadline_family") or is_deadline_family_story_key(story_key):
            return FORM_DEADLINE_LADDER
        if is_congress_control_story_key(story_key):
            return FORM_PARTY_CONTROL_BARS
        return FORM_THEME_COMPACT_ROWS

    if kind == "comparison":
        return FORM_COMPARISON_COMPACT_ROWS

    return _nonempty_str(data.get("form_id"))


def stamp_bundle_form_id(item: dict[str, Any]) -> Optional[str]:
    """Attach additive ``data['form_id']`` (and ``data['roundup']['form_id']``) in place.

    Preserves any non-empty explicit ``form_id`` already on the payload and never
    creates or modifies ``machinery_card``.
    """
    if not isinstance(item, dict) or item.get("type") != "bundle":
        return None
    data = item.get("data")
    if not isinstance(data, dict):
        return None

    inferred = infer_bundle_visual_form_id(data)
    form_id = _nonempty_str(data.get("form_id")) or inferred
    if form_id is None:
        return None

    data["form_id"] = form_id
    if _nonempty_str(data.get("kind")) == "roundup":
        roundup = data.get("roundup")
        if isinstance(roundup, dict) and _nonempty_str(roundup.get("form_id")) is None:
            roundup["form_id"] = form_id
    return form_id


def card_visual_form_id(item: Mapping[str, Any]) -> Optional[str]:
    """Return the visual form identifier of a Discover item, or ``None``."""
    if not isinstance(item, Mapping):
        return None
    data = item.get("data")
    if not isinstance(data, Mapping):
        return None
    roundup = data.get("roundup")
    if isinstance(roundup, Mapping):
        mc = roundup.get("machinery_card")
        if isinstance(mc, Mapping):
            mc_form = _nonempty_str(mc.get("form_id"))
            if mc_form is not None:
                return mc_form
        ru_form = _nonempty_str(roundup.get("form_id"))
        if ru_form is not None:
            return ru_form
    explicit = _nonempty_str(data.get("form_id"))
    if explicit is not None:
        return explicit
    if item.get("type") == "bundle":
        return infer_bundle_visual_form_id(data)
    return None
