"""Alex's reviewed Midterms collection. One market per race; venues attribute it.

The explicit manifest is the authorized membership policy. Published edges still
control visibility: a withdrawn member never comes back through this projection.
Official venue results override the blend as soon as either venue grades a winner.
"""

from __future__ import annotations

import copy
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from app.utils.container_presentation import market_destination
from app.utils.futures_source_merge import blend_probabilities
from app.utils.graded_card import rendered_duel_percents
from app.utils.venue_settlement import VENUE_SETTLEMENT_SOURCE

MANIFEST_PATH = (
    Path(__file__).resolve().parents[2] / "data/collections/midterms-2026.json"
)
MANIFEST = json.loads(MANIFEST_PATH.read_text())
SLUG = MANIFEST["slug"]
MARKET_IDS = tuple(mid for s in MANIFEST["sections"] for mid in s["market_ids"])
SECTION_CLASSES = frozenset(s["key"] for s in MANIFEST["sections"])


def outcome_key(name: str) -> str:
    value = re.sub(r"\s*\((?:R|D|I)\)\s*$", "", name, flags=re.I).strip().casefold()
    parties = r"democrat(?:ic|s)?|republicans?|[dr]"
    chambers = {}
    for party, chamber in re.findall(
        rf"\b({parties})\b(?:\s+controls?)?\s+(house|senate)\b", value
    ):
        chambers[chamber] = "democratic" if party.startswith("d") else "republican"
    if (
        len(chambers) == 1
        and "house" in value
        and "senate" in value
        and len(re.findall(rf"\b({parties})\b", value)) == 1
    ):
        party = next(iter(chambers.values()))
        chambers = {"house": party, "senate": party}
    if len(chambers) == 2:
        return f"house:{chambers['house']}|senate:{chambers['senate']}"
    if value in {"democrat", "democrats", "democratic", "democratic party"}:
        return "democratic"
    if value in {"republican", "republicans", "republican party", "gop"}:
        return "republican"
    return value


def _official_result(card: dict) -> tuple[str, str] | None:
    winners = [
        o["name"]
        for o in card.get("top_outcomes", [])
        if o.get("is_winner") is True
        and o.get("resolution_source") == VENUE_SETTLEMENT_SOURCE
    ]
    if len(winners) != 1:
        return None
    # settled_at is the existing first-observation stamp, never the scheduled
    # resolution date or a mutable updated_at. Unknown stamps sort last.
    stamp = card.get("settled_at") or "9999-12-31T00:00:00+00:00"
    return stamp, winners[0]


def blend_card(primary: dict, contributors: list[dict]) -> dict:
    card = copy.deepcopy(primary)
    outcomes = {outcome_key(o["name"]): o for o in card.get("top_outcomes", [])}
    for contributor in contributors:
        for outcome in contributor.get("top_outcomes", []):
            key = outcome_key(outcome["name"])
            if key not in outcomes:
                outcomes[key] = copy.deepcopy(outcome)
    card["top_outcomes"] = list(outcomes.values())
    card["outcome_count"] = max(
        len(outcomes), *(c.get("outcome_count", 0) for c in contributors)
    )
    sources = sorted({c["source"] for c in contributors})
    card.update(
        sources=sources,
        source_count=len(sources),
        source="both" if len(sources) > 1 else sources[0],
    )
    official = sorted(r for c in contributors if (r := _official_result(c)))
    if official:
        winner = official[0][1]
        # Prefer the primary venue's spelling, retaining the result's name if
        # its winner was not present in a partial primary card.
        card["settled_winner"] = next(
            (
                o["name"]
                for o in card["top_outcomes"]
                if outcome_key(o["name"]) == outcome_key(winner)
            ),
            winner,
        )
        card["status"] = "resolved"
        for o in card["top_outcomes"]:
            o.update(
                probability=None,
                is_winner=outcome_key(o["name"]) == outcome_key(winner),
                resolution_source=VENUE_SETTLEMENT_SOURCE,
            )
        return card
    for outcome in card.get("top_outcomes", []):
        rows = []
        for c in contributors:
            matches = [
                o
                for o in c.get("top_outcomes", [])
                if outcome_key(o["name"]) == outcome_key(outcome["name"])
            ]
            if len(matches) == 1:
                rows.append(
                    {
                        "source": c["source"],
                        "probability": matches[0].get("probability"),
                    }
                )
        outcome["probability"] = blend_probabilities(rows)
    return card


def present_midterms_sections(
    members: list, cards: dict, twins: dict | None = None
) -> tuple[list, list]:
    visible = {(m["id"], m["class"]) for m in members if m.get("type") == "market"}
    sections, withheld = [], []
    for section in MANIFEST["sections"]:
        entries = []
        for mid in section["market_ids"]:
            if (mid, section["key"]) not in visible:
                continue
            if mid == 112905:  # source of the one reviewed balance-of-power market
                continue
            if mid not in cards or cards[mid].get("_withheld_reason"):
                withheld.append(
                    {
                        "type": "market",
                        "id": mid,
                        "reason": cards.get(mid, {}).get(
                            "_withheld_reason", "row_missing"
                        ),
                    }
                )
                continue
            source_ids = [mid, *((twins or {}).get(mid, []))]
            if mid == 108619 and (112905, section["key"]) in visible:
                source_ids.append(112905)
                if 112905 not in cards:
                    withheld.append(
                        {"type": "market", "id": 112905, "reason": "row_missing"}
                    )
            contributors = [
                cards[i]
                for i in dict.fromkeys(source_ids)
                if i in cards and not cards[i].get("_withheld_reason")
            ]
            blended = blend_card(cards[mid], contributors)
            if section["layout"] == "field" and not blended.get("settled_winner"):
                blended["top_outcomes"].sort(
                    key=lambda o: (
                        o.get("probability") is None,
                        -(o.get("probability") or 0),
                    )
                )
            entries.append(
                {
                    "type": "market",
                    "id": mid,
                    "destination": market_destination(mid),
                    "card": blended,
                    "event_id": None,
                }
            )
        sections.append(
            {
                "class": section["key"],
                "title": section["title"],
                "layout": section["layout"],
                "count": len(entries),
                "members": entries,
            }
        )
    return sections, withheld


def midterms_pin(payload: dict, now: datetime | None = None) -> dict | None:
    now = now or datetime.now(timezone.utc)
    if (
        payload.get("state") != "published"
        or payload.get("slug") != SLUG
        or now >= datetime.fromisoformat(MANIFEST["pin_until"])
    ):
        return None
    cards = {
        m["id"]: m["card"] for s in payload.get("sections", []) for m in s["members"]
    }
    parts = []
    for mid, chamber in ((108620, "Senate"), (108621, "House")):
        card = cards.get(mid)
        if card is None:
            return None  # no empty/dead pin while its headline markets are unavailable
        winner = card.get("settled_winner")
        if winner:
            parts.append(f"{chamber} Settled - {winner}")
            continue
        outcomes = {
            outcome_key(o["name"]): o.get("probability") for o in card["top_outcomes"]
        }
        gop, dem = outcomes.get("republican"), outcomes.get("democratic")
        _, dem_pct = rendered_duel_percents(gop, dem)
        if dem_pct is None:
            return None
        parts.append(f"{chamber} {dem_pct}% D")
    return {
        "slug": SLUG,
        "name": MANIFEST["title"],
        "href": f"/collections/{SLUG}",
        "subtitle": " - ".join(parts),
        "pin_until": MANIFEST["pin_until"],
    }
