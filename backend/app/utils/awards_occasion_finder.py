"""Discover proposed ceremony sets from venue evidence (#11935, decision 64).

PILLAR DISCOVER / TRUTH. SHIP: a newly listed awards ceremony gets its own
card and container without a typed ceremony roster. This draft slice finds
the occasion and its reproducible selector; it never publishes a proposal.

Inputs are venue events, not hand-picked market ids. An explicit ordinal
ceremony name in primary rules is evidence; a ticker year, close time or
resolution deadline is not. Missing ceremony dates and completion stay None.
Provider events establish membership only, never equivalent probabilities.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

_CEREMONY = re.compile(
    r"\b(?P<label>[1-9][0-9]{0,2}(?:st|nd|rd|th)\s+"
    r"[A-Z][A-Za-z’'&. -]{1,70}?\bAwards)\b"
)
_KALSHI_EVENT = re.compile(r"[A-Z0-9]+(?:-[A-Z0-9]+)+")
_POLYMARKET_EVENT = re.compile(r"[1-9][0-9]{0,17}")


@dataclass(frozen=True, order=True)
class OccasionEvent:
    provider: str
    event_id: str
    label: str
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class AwardsOccasion:
    """One proposed set, with a selector rather than a frozen member list."""

    label: str
    events: tuple[OccasionEvent, ...]
    relation: str = "same_event"
    level: str = "member"
    trigger: str = "market_availability"
    state: str = "proposed"
    ceremony_date: None = None
    completed_at: None = None

    @property
    def selector(self) -> dict[str, str]:
        return {"evidence": "primary_rules_ordinal_awards", "label": self.label}


@dataclass(frozen=True)
class OccasionDiscovery:
    occasions: tuple[AwardsOccasion, ...]
    refused: tuple[tuple[str, str, str], ...]


def _identity(event: Mapping[str, Any]) -> tuple[str, str] | None:
    provider = event.get("provider")
    if provider == "kalshi":
        raw = event.get("event_ticker")
        if isinstance(raw, str) and _KALSHI_EVENT.fullmatch(raw):
            return provider, raw
    if provider == "polymarket":
        raw = str(event.get("id") or "")
        if _POLYMARKET_EVENT.fullmatch(raw):
            return provider, raw
    return None


def _evidence(event: Mapping[str, Any]) -> dict[str, set[str]]:
    labels: dict[str, set[str]] = defaultdict(set)
    markets = event.get("markets")
    if not isinstance(markets, list):
        return labels
    for market in markets:
        if not isinstance(market, Mapping):
            continue
        # Secondary rules contain disclaimers and expected dates, which cannot
        # establish the traded ceremony. Titles alone can name a comparison.
        rules = market.get("rules_primary")
        if not isinstance(rules, str):
            continue
        for match in _CEREMONY.finditer(rules):
            label = " ".join(match.group("label").split())
            labels[label].add(rules)
    return labels


def find_awards_occasions(events: Iterable[Mapping[str, Any]]) -> OccasionDiscovery:
    """Return reproducible proposals and loud refusals, with no I/O or clock.

    A venue event naming two ceremonies is ambiguous, even if a majority of
    its markets name one. A conflicting duplicate of the same provider event
    is also refused as a whole, so input order never chooses its membership.
    """
    by_identity: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    refused: set[tuple[str, str, str]] = set()
    for event in events:
        if not isinstance(event, Mapping):
            refused.add(("unknown", "", "malformed_event"))
            continue
        identity = _identity(event)
        if identity is None:
            refused.add(
                (str(event.get("provider") or "unknown"), "", "invalid_identity")
            )
            continue
        by_identity[identity].append(event)

    grouped: dict[str, list[OccasionEvent]] = defaultdict(list)
    for (provider, event_id), observations in sorted(by_identity.items()):
        observations_evidence = [_evidence(event) for event in observations]
        keys = {tuple(sorted(evidence)) for evidence in observations_evidence}
        if len(keys) != 1:
            refused.add((provider, event_id, "conflicting_event_evidence"))
            continue
        labels = next(iter(keys))
        if len(labels) != 1:
            reason = "ceremony_identity_unknown" if not labels else "ambiguous_ceremony"
            refused.add((provider, event_id, reason))
            continue
        label = labels[0]
        quotes = tuple(
            sorted(
                {
                    quote
                    for evidence in observations_evidence
                    for quote in evidence[label]
                }
            )
        )
        grouped[label].append(OccasionEvent(provider, event_id, label, quotes))
    return OccasionDiscovery(
        occasions=tuple(
            AwardsOccasion(label, tuple(sorted(members)))
            for label, members in sorted(grouped.items())
        ),
        refused=tuple(sorted(refused)),
    )


def select_awards_occasion(
    selector: Mapping[str, str], events: Iterable[Mapping[str, Any]]
) -> AwardsOccasion | None:
    """Re-run the proposed definition on current venue data, admitting new categories."""
    if (
        set(selector) != {"evidence", "label"}
        or selector.get("evidence") != "primary_rules_ordinal_awards"
    ):
        raise ValueError("Unsupported ceremony selector")
    if not isinstance(selector.get("label"), str) or not _CEREMONY.fullmatch(
        selector["label"]
    ):
        raise ValueError("An explicit venue ceremony label is required")
    return next(
        (
            occasion
            for occasion in find_awards_occasions(events).occasions
            if occasion.label == selector["label"]
        ),
        None,
    )
