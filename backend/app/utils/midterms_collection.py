"""Alex's reviewed Midterms collection. One market per race; venues attribute it.

The explicit manifest is the authorized membership policy. Published edges still
control visibility: a withdrawn member never comes back through this projection.
Official venue results override the blend as soon as either venue grades a winner.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
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


@dataclass(frozen=True)
class MidtermsTwinEntry:
    """Explicit Kalshi-to-Polymarket twin entry for the 2026 Midterms collection (#11871)."""

    kalshi_market_id: int
    kalshi_ticker: str
    kalshi_name: str
    polymarket_market_id: int | None
    polymarket_external_id: str | None
    polymarket_name: str | None
    note: str
    outcome_aliases: tuple[tuple[str, str], ...] = ()


# Explicit 14-market twin register for midterms-2026 (#11871), read from production
# on 2026-11-02 and verified outcome-for-outcome.
MIDTERMS_TWIN_REGISTER: tuple[MidtermsTwinEntry, ...] = (
    MidtermsTwinEntry(
        kalshi_market_id=108620,
        kalshi_ticker="CONTROLS-2026",
        kalshi_name="Which party will win the U.S. Senate?",
        polymarket_market_id=112902,
        polymarket_external_id="32224",
        polymarket_name="Which party will win the Senate in 2026?",
        note="paired (Democratic / Republican)",
    ),
    MidtermsTwinEntry(
        kalshi_market_id=108621,
        kalshi_ticker="CONTROLH-2026",
        kalshi_name="Which party will win the U.S. House?",
        polymarket_market_id=112903,
        polymarket_external_id="32225",
        polymarket_name="Which party will win the House in 2026?",
        note="paired (Democratic / Republican)",
    ),
    MidtermsTwinEntry(
        kalshi_market_id=108619,
        kalshi_ticker="KXBALANCEPOWERCOMBO-27FEB",
        kalshi_name="2026 Midterms: Congress Balance of Power?",
        polymarket_market_id=112905,
        polymarket_external_id="32228",
        polymarket_name="Balance of Power: 2026 Midterms",
        note="paired (4 chamber splits; Polymarket <1% Other dropped as residual)",
    ),
    MidtermsTwinEntry(
        kalshi_market_id=109085,
        kalshi_ticker="SENATEKS-26",
        kalshi_name="Kansas Senate winner?",
        polymarket_market_id=113093,
        polymarket_external_id="57648",
        polymarket_name="Kansas Senate Election Winner",
        note="paired (Adam Hamilton / Roger Marshall)",
    ),
    MidtermsTwinEntry(
        kalshi_market_id=109088,
        kalshi_ticker="SENATEIA-26",
        kalshi_name="Iowa Senate winner?",
        polymarket_market_id=113092,
        polymarket_external_id="57647",
        polymarket_name="Iowa Senate Election Winner",
        note="paired (Josh Turek / Ashley Hinson)",
    ),
    MidtermsTwinEntry(
        kalshi_market_id=109082,
        kalshi_ticker="SENATEME-26",
        kalshi_name="Maine Senate winner?",
        polymarket_market_id=113095,
        polymarket_external_id="57650",
        polymarket_name="Maine Senate Election Winner",
        note="paired (Troy Jackson / Susan Collins)",
    ),
    MidtermsTwinEntry(
        kalshi_market_id=109095,
        kalshi_ticker="SENATEAK-26",
        kalshi_name="Alaska Senate winner?",
        polymarket_market_id=None,
        polymarket_external_id=None,
        polymarket_name=None,
        note="no Polymarket market exists (Kalshi 109095 is a party-winner contract; Polymarket 113124 is a 7-candidate ranked-choice person contract)",
    ),
    MidtermsTwinEntry(
        kalshi_market_id=109065,
        kalshi_ticker="SENATETX-26",
        kalshi_name="Texas Senate winner?",
        polymarket_market_id=113109,
        polymarket_external_id="57672",
        polymarket_name="Texas Senate Election Winner",
        note="paired (James Talarico / Ken Paxton)",
    ),
    MidtermsTwinEntry(
        kalshi_market_id=109072,
        kalshi_ticker="SENATEOHS-26",
        kalshi_name="Ohio Senate winner?",
        polymarket_market_id=113116,
        polymarket_external_id="57682",
        polymarket_name="Ohio Senate Election Winner",
        note="paired (Sherrod Brown / Jon Husted)",
    ),
    MidtermsTwinEntry(
        kalshi_market_id=109068,
        kalshi_ticker="SENATESC-26",
        kalshi_name="South Carolina Senate winner?",
        polymarket_market_id=113106,
        polymarket_external_id="57669",
        polymarket_name="South Carolina Senate Election Winner",
        note="paired (Darline Graham / Annie Andrews)",
        outcome_aliases=(("darline graham nordone", "darline graham"),),
    ),
    MidtermsTwinEntry(
        kalshi_market_id=109081,
        kalshi_ticker="SENATEMI-26",
        kalshi_name="Michigan Senate winner?",
        polymarket_market_id=113097,
        polymarket_external_id="57658",
        polymarket_name="Michigan Senate Election Winner",
        note="paired (Abdul El-Sayed / Mike Rogers)",
    ),
    MidtermsTwinEntry(
        kalshi_market_id=108645,
        kalshi_ticker="GOVPARTYGA-26",
        kalshi_name="Georgia Governor winner?",
        polymarket_market_id=113056,
        polymarket_external_id="57161",
        polymarket_name="Georgia Governor Election Winner",
        note="paired (Keisha Lance Bottoms / Rick Jackson)",
    ),
    MidtermsTwinEntry(
        kalshi_market_id=109918,
        kalshi_ticker="KXDEMSWINGSTATEGOVSWEEP-26NOV03",
        kalshi_name="Will Democrats sweep all swing state Governor races?",
        polymarket_market_id=None,
        polymarket_external_id=None,
        polymarket_name=None,
        note="no Polymarket market exists",
    ),
    MidtermsTwinEntry(
        kalshi_market_id=108629,
        kalshi_ticker="KXCLOSESTGOVERNOR-27JAN20",
        kalshi_name="Closest Governor race in 2026?",
        polymarket_market_id=None,
        polymarket_external_id=None,
        polymarket_name=None,
        note="no Polymarket market exists (Kalshi 108629 lists 24 states; Polymarket 64546265 lists 36 states with >1% probability on states absent from Kalshi)",
    ),
)

MIDTERMS_TWIN_BY_KALSHI_ID: dict[int, MidtermsTwinEntry] = {
    entry.kalshi_market_id: entry for entry in MIDTERMS_TWIN_REGISTER
}
REGISTERED_POLYMARKET_TWIN_IDS: frozenset[int] = frozenset(
    entry.polymarket_market_id
    for entry in MIDTERMS_TWIN_REGISTER
    if entry.polymarket_market_id is not None
)


def outcome_key(name: str, entry: MidtermsTwinEntry | None = None) -> str:
    value = re.sub(r"\s*\((?:R|D|I)\)\s*$", "", name, flags=re.I).strip().casefold()
    parties = r"democrat(?:ic|s)?|republicans?|[dr]"
    chambers = {}
    for party, chamber in re.findall(
        # Kalshi spells a split "D-House, R-Senate"; Polymarket "R Senate, D House".
        rf"\b({parties})\b(?:\s+controls?)?[\s-]+(house|senate)\b", value
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
    if entry is not None and entry.outcome_aliases:
        value = dict(entry.outcome_aliases).get(value, value)
    return value


#: A contributor-only outcome under this prints as 0% and is no blend, so the card
#: drops it; at or above it the publisher refuses (`prepare_curated`).
RESIDUAL_BELOW = 0.01


def is_residual(outcome: dict) -> bool:
    probability = outcome.get("probability")
    return probability is None or probability < RESIDUAL_BELOW


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
    entry = MIDTERMS_TWIN_BY_KALSHI_ID.get(card.get("id"))
    outcomes = {outcome_key(o["name"], entry): o for o in card.get("top_outcomes", [])}
    primary_keys = set(outcomes)
    counts = []
    for contributor in contributors:
        dropped = 0
        for outcome in contributor.get("top_outcomes", []):
            key = outcome_key(outcome["name"], entry)
            if key in primary_keys:
                continue
            # A contributor-only outcome under 1% (Polymarket's balance-of-power
            # "Other", 0.05% on 2026-11-02) would be one venue's 0% row.
            if is_residual(outcome):
                dropped += 1
            elif key not in outcomes:
                outcomes[key] = copy.deepcopy(outcome)
        counts.append(contributor.get("outcome_count", 0) - dropped)
    card["top_outcomes"] = list(outcomes.values())
    card["outcome_count"] = max([len(outcomes), *counts])
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
                if outcome_key(o["name"], entry) == outcome_key(winner, entry)
            ),
            winner,
        )
        card["status"] = "resolved"
        for o in card["top_outcomes"]:
            o.update(
                probability=None,
                is_winner=outcome_key(o["name"], entry) == outcome_key(winner, entry),
                resolution_source=VENUE_SETTLEMENT_SOURCE,
            )
        return card
    for outcome in card.get("top_outcomes", []):
        rows = []
        for c in contributors:
            matches = [
                o
                for o in c.get("top_outcomes", [])
                if outcome_key(o["name"], entry) == outcome_key(outcome["name"], entry)
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
