"""Reusable ``register_closest`` producer kind (#11949 Order 5).

PILLAR: DISCOVER / FORMATTING / TRUTH · SHIP: ``roundup-closest-races``
("The closest races still open") — selects the closest unsettled races from a
published election register (`midterms-2026.json`), blended only where the
register pairs Kalshi and Polymarket (`MIDTERMS_TWIN_REGISTER`).

Rules enforced:
* **Unsettled only**: settled races in the register are excluded from the
  open-race pool.
* **Settled-in-register vs still-priced guard**: if a race's primary or paired
  twin is settled/graded while its counterpart still carries an open price, the
  producer refuses (`settled_in_register_still_priced:<id>`).
* **#11995 decision 6-A normalization**: each open race's outcomes are blended
  across registered twins via ``blend_probabilities`` and normalized via
  ``display_probability_divisor`` / ``normalize_display_probs``.
* **Minimum 3 unsettled races**: fewer than 3 open races withholds the card and
  container (`too_few_open_races`). Today 7 of 8 Senate races in
  ``midterms-2026.json`` are settled and only Alaska is open, so the producer
  cleanly refuses until a register has >= 3 open races.
"""

from __future__ import annotations

import importlib
import json
import math
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

from app.utils.container_presentation import MEMBER_MARKET, market_destination
from app.utils.field_band import _iso_utc, _validate_narrative_copy
from app.utils.futures_liveness import leg_is_graded
from app.utils.futures_source_merge import blend_probabilities
from app.utils.midterms_collection import (
    MANIFEST as MIDTERMS_MANIFEST,
    MIDTERMS_TWIN_BY_KALSHI_ID,
    MidtermsTwinEntry,
    outcome_key,
)
from app.utils.outcome_display import (
    display_probability_divisor,
    normalize_display_probs,
)


def _rc() -> Any:
    return importlib.import_module("app.utils.roundup_containers")


__all__ = [
    "CLOSEST_RACES_DEFINITION",
    "CLOSEST_RACES_DEFINITION_PATH",
    "CLOSEST_RACES_ID",
    "CLOSEST_RACES_PRODUCER",
    "CLOSEST_RACES_SLUG",
    "PRODUCER_KIND_REGISTER_CLOSEST",
    "build_register_closest_producer",
    "closest_races",
    "load_register_closest_definition",
    "produce_register_closest",
    "register_closest_enabled",
    "select_register_closest",
]

PRODUCER_KIND_REGISTER_CLOSEST = "register_closest"

CLOSEST_RACES_SLUG = "roundup-closest-races"
CLOSEST_RACES_ID = "roundup:closest-races"
CLOSEST_RACES_DEFINITION_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "containers"
    / f"{CLOSEST_RACES_SLUG}.json"
)


def register_closest_enabled() -> bool:
    return os.getenv("REGISTER_CLOSEST_ENABLED", "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _half_up_percent(prob: float) -> int:
    return int(math.floor(prob * 100.0 + 0.5))


def _race_label(name: str) -> str:
    cleaned = re.sub(
        r"\s*(?:Election\s+Winner|winner\??)\s*$",
        "",
        str(name or "").strip(),
        flags=re.IGNORECASE,
    ).strip(" -–—:?")
    return cleaned or str(name or "").strip()


def _market_is_settled(m: Mapping[str, Any]) -> bool:
    status = str(m.get("status") or "open").strip().lower()
    if status != "open":
        return True
    if m.get("settled_winner"):
        return True
    outcomes = m.get("outcomes") or m.get("top_outcomes") or ()
    for o in outcomes:
        if isinstance(o, Mapping) and leg_is_graded(
            o.get("is_winner"), o.get("resolution_source")
        ):
            return True
    return False


def _market_has_open_price(m: Mapping[str, Any]) -> bool:
    if str(m.get("status") or "open").strip().lower() != "open":
        return False
    outcomes = m.get("outcomes") or m.get("top_outcomes") or ()
    for o in outcomes:
        if not isinstance(o, Mapping):
            continue
        if leg_is_graded(o.get("is_winner"), o.get("resolution_source")):
            continue
        p = (
            o.get("probability")
            if "probability" in o
            else o.get("current_probability")
        )
        if isinstance(p, (int, float)) and not isinstance(p, bool) and 0.0 < float(p) < 1.0:
            return True
    return False


@dataclass(frozen=True)
class _OpenRaceCandidate:
    market_id: int
    race_name: str
    leader_outcome_id: int
    leader_name: str
    leader_probability: float
    leader_rendered_percent: int
    observed_at: Optional[str]
    pair_ids: Optional[dict[str, int]]
    card: dict[str, Any]


def select_register_closest(
    markets: Mapping[int, Mapping[str, Any]] | Sequence[Mapping[str, Any]],
    *,
    section_keys: Sequence[str] = ("senate_races", "governors"),
    excluded_market_ids: Sequence[int] = (109918, 108629),
    min_open_races: int = 3,
    card_rows: int = 3,
    section_title: str = "Open races",
    footer: str = "Bain Luck blend · both venues where paired",
    title: Optional[str] = None,
    kicker: Optional[str] = None,
) -> Any:
    """Pure selector for ``register_closest`` (#11949 Order 5)."""
    rc = _rc()
    RoundupMembers = rc.RoundupMembers
    RoundupRefusal = rc.RoundupRefusal

    _validate_narrative_copy(footer, title or "", kicker or "", section_title)

    by_id: dict[int, Mapping[str, Any]] = {}
    seq = markets.values() if isinstance(markets, Mapping) else markets
    for m in seq:
        if isinstance(m, Mapping):
            mid = m.get("id")
            if isinstance(mid, int) and not isinstance(mid, bool) and mid > 0:
                by_id[int(mid)] = m

    if not by_id:
        return RoundupRefusal((("register_closest", "empty_pool"),))

    allowed_sections = set(section_keys)
    excluded_ids = {int(mid) for mid in excluded_market_ids}
    register_ids: list[int] = []
    for sec in MIDTERMS_MANIFEST.get("sections", ()):
        if sec.get("key") not in allowed_sections:
            continue
        for mid in sec.get("market_ids", ()):
            if int(mid) in MIDTERMS_TWIN_BY_KALSHI_ID:
                register_ids.append(int(mid))

    open_candidates: list[_OpenRaceCandidate] = []

    for kalshi_id in register_ids:
        entry: Optional[MidtermsTwinEntry] = MIDTERMS_TWIN_BY_KALSHI_ID.get(kalshi_id)
        if entry is None:
            continue
        # Skip multi-state meta-markets configured in rule.excluded_market_ids
        if kalshi_id in excluded_ids:
            continue

        primary = by_id.get(kalshi_id)
        poly_id = entry.polymarket_market_id
        twin = by_id.get(poly_id) if poly_id is not None else None

        if primary is None:
            continue

        primary_settled = _market_is_settled(primary)
        twin_settled = _market_is_settled(twin) if twin is not None else False

        # Refusal: one leg settled in register while its paired venue still prices it open.
        if primary_settled and twin is not None and not twin_settled and _market_has_open_price(twin):
            return RoundupRefusal(
                (("register_closest", f"settled_in_register_still_priced:{kalshi_id}"),)
            )
        if twin is not None and twin_settled and not primary_settled and _market_has_open_price(primary):
            return RoundupRefusal(
                (("register_closest", f"settled_in_register_still_priced:{kalshi_id}"),)
            )

        if primary_settled or twin_settled:
            continue

        # Blend outcomes across primary and twin (when paired and present).
        contributors = [primary] + ([twin] if twin is not None else [])
        raw_primary_outs = (
            primary.get("outcomes") or primary.get("top_outcomes") or ()
        )
        outcome_dicts: list[dict[str, Any]] = []
        oldest_obs: Optional[str] = None

        for idx, o in enumerate(raw_primary_outs):
            if not isinstance(o, Mapping):
                continue
            oname = str(o.get("name") or o.get("label") or "").strip()
            if not oname:
                continue
            okey = outcome_key(oname, entry)
            oid_raw = o.get("id")
            oid = (
                int(oid_raw)
                if isinstance(oid_raw, int) and not isinstance(oid_raw, bool) and oid_raw > 0
                else kalshi_id * 100 + idx + 1
            )
            contrib_rows: list[dict[str, Any]] = []
            for c in contributors:
                c_src = str(c.get("source") or "kalshi").strip().lower()
                c_outs = c.get("outcomes") or c.get("top_outcomes") or ()
                matches = [
                    co
                    for co in c_outs
                    if isinstance(co, Mapping)
                    and outcome_key(str(co.get("name") or co.get("label") or ""), entry) == okey
                ]
                if len(matches) == 1:
                    cp = (
                        matches[0].get("probability")
                        if "probability" in matches[0]
                        else matches[0].get("current_probability")
                    )
                    if isinstance(cp, (int, float)) and not isinstance(cp, bool):
                        contrib_rows.append({"source": c_src, "probability": float(cp)})
                        obs = _iso_utc(
                            matches[0].get("observed_at")
                            or matches[0].get("last_updated")
                            or c.get("prices_updated_at")
                            or c.get("updated_at")
                        )
                        if obs and (oldest_obs is None or obs < oldest_obs):
                            oldest_obs = obs

            blended_p = blend_probabilities(contrib_rows)
            if blended_p is None:
                return RoundupRefusal((("register_closest", f"unpriced_outcome:{kalshi_id}"),))
            outcome_dicts.append(
                {
                    "id": oid,
                    "name": oname,
                    "probability": float(blended_p),
                }
            )

        if len(outcome_dicts) < 2:
            return RoundupRefusal((("register_closest", f"too_few_outcomes:{kalshi_id}"),))

        divisor = display_probability_divisor(
            outcome_dicts,
            mutually_exclusive=True,
            field_complete=True,
            question=str(primary.get("name") or entry.kalshi_name),
        )
        if divisor is None:
            return RoundupRefusal((("register_closest", f"guard_failed:{kalshi_id}"),))
        normalize_display_probs(
            outcome_dicts,
            mutually_exclusive=True,
            field_complete=True,
            question=str(primary.get("name") or entry.kalshi_name),
        )

        outcome_dicts.sort(key=lambda od: (-float(od["probability"]), int(od["id"])))
        leader = outcome_dicts[0]
        leader_prob = float(leader["probability"])
        leader_pct = (
            int(leader["rendered_percent"])
            if isinstance(leader.get("rendered_percent"), int)
            else _half_up_percent(leader_prob)
        )

        sources = sorted({str(c.get("source") or "kalshi").lower() for c in contributors})
        race_title = _race_label(str(primary.get("name") or entry.kalshi_name))
        card = {
            "id": kalshi_id,
            "name": str(primary.get("name") or entry.kalshi_name),
            "category": "politics",
            "llm_sport_category": "politics",
            "market_tier": 1,
            "market_type": "field",
            "status": "open",
            "source": "both" if len(sources) > 1 else sources[0],
            "sources": sources,
            "source_count": len(sources),
            "mutually_exclusive": True,
            "resolution_date": _iso_utc(primary.get("resolution_date")),
            "top_outcomes": [
                {
                    "id": int(od["id"]),
                    "name": str(od["name"]),
                    "probability": float(od["probability"]),
                    "rendered_percent": (
                        int(od["rendered_percent"])
                        if isinstance(od.get("rendered_percent"), int)
                        else _half_up_percent(float(od["probability"]))
                    ),
                    "american_odds": None,
                    "rank": idx + 1,
                    "movement": None,
                    "is_winner": False,
                    "resolution_source": None,
                }
                for idx, od in enumerate(outcome_dicts)
            ],
            "outcome_count": len(outcome_dicts),
            "updated_at": oldest_obs,
            "prices_updated_at": oldest_obs,
            "price_observed_at": oldest_obs,
        }
        pair_info = (
            {"kalshi_market_id": kalshi_id, "polymarket_market_id": int(poly_id)}
            if twin is not None and poly_id is not None
            else None
        )
        open_candidates.append(
            _OpenRaceCandidate(
                market_id=kalshi_id,
                race_name=race_title,
                leader_outcome_id=int(leader["id"]),
                leader_name=str(leader["name"]),
                leader_probability=leader_prob,
                leader_rendered_percent=leader_pct,
                observed_at=oldest_obs,
                pair_ids=pair_info,
                card=card,
            )
        )

    if len(open_candidates) < min_open_races:
        return RoundupRefusal((("register_closest", "too_few_open_races"),))

    # Pick the closest races (lowest leader probability), then sort highest-first for RoundupCard.
    closest_picked = sorted(
        open_candidates,
        key=lambda c: (c.leader_probability, c.race_name.casefold(), c.market_id),
    )[:card_rows]
    ordered_rows = sorted(
        closest_picked,
        key=lambda c: (-c.leader_probability, c.race_name.casefold(), c.market_id),
    )

    rows_out: list[dict[str, Any]] = []
    members_out: list[dict[str, Any]] = []
    revision_ids: list[int] = []

    for c in ordered_rows:
        row_dict: dict[str, Any] = {
            "market_id": c.market_id,
            "outcome_id": c.leader_outcome_id,
            "label": f"{c.race_name} · {c.leader_name}",
            "probability": c.leader_probability,
            "rendered_percent": c.leader_rendered_percent,
            "observed_at": c.observed_at,
        }
        if c.pair_ids is not None:
            row_dict["pair"] = c.pair_ids
        rows_out.append(row_dict)
        members_out.append(
            {
                "type": MEMBER_MARKET,
                "id": c.market_id,
                "destination": market_destination(c.market_id),
                "card": c.card,
                "event_id": None,
            }
        )
        revision_ids.append(c.market_id)

    sections_out = [
        {
            "class": "title",
            "title": section_title,
            "layout": "duel",
            "count": len(members_out),
            "members": members_out,
        }
    ]

    return RoundupMembers(
        members_out,
        rows_out,
        footer=footer,
        title=title,
        kicker=kicker,
        sections=sections_out,
        revision_ids=revision_ids,
    )


async def produce_register_closest(
    db: Any,
    definition: Mapping[str, Any],
    *,
    now: Optional[datetime] = None,
) -> Any:
    """Evaluate a stored ``register_closest`` definition against ``db`` (or an in-memory fixture)."""
    rule = definition.get("rule")
    if not isinstance(rule, Mapping) or rule.get("producer") != PRODUCER_KIND_REGISTER_CLOSEST:
        raise ValueError(
            f"Unsupported producer kind; expected {PRODUCER_KIND_REGISTER_CLOSEST!r}"
        )

    if isinstance(db, Mapping):
        by_id = {int(k): v for k, v in db.items() if isinstance(v, Mapping)}
    elif isinstance(db, (list, tuple)):
        by_id = {
            int(m["id"]): m
            for m in db
            if isinstance(m, Mapping)
            and isinstance(m.get("id"), int)
            and not isinstance(m.get("id"), bool)
        }
    elif hasattr(db, "execute") and callable(db.execute):
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        from app.models import FuturesMarket

        all_ids: set[int] = set()
        for entry in MIDTERMS_TWIN_BY_KALSHI_ID.values():
            all_ids.add(entry.kalshi_market_id)
            if entry.polymarket_market_id is not None:
                all_ids.add(entry.polymarket_market_id)

        stmt = (
            select(FuturesMarket)
            .options(selectinload(FuturesMarket.outcomes))
            .where(FuturesMarket.id.in_(sorted(all_ids)))
        )
        res = await db.execute(stmt)
        scalars_obj = res.scalars() if hasattr(res, "scalars") and callable(res.scalars) else None
        rows = list(scalars_obj.all()) if scalars_obj is not None and hasattr(scalars_obj, "all") else []
        by_id = {}
        for m in rows:
            mid = getattr(m, "id", None)
            if not isinstance(mid, int) or isinstance(mid, bool):
                continue
            by_id[int(mid)] = {
                "id": int(mid),
                "name": getattr(m, "name", None),
                "status": getattr(m, "status", None),
                "source": getattr(m, "source", None),
                "resolution_date": getattr(m, "resolution_date", None),
                "updated_at": getattr(m, "updated_at", None),
                "outcomes": [
                    {
                        "id": int(o.id),
                        "name": o.name,
                        "probability": (
                            float(o.current_probability)
                            if o.current_probability is not None
                            else None
                        ),
                        "is_winner": getattr(o, "is_winner", None),
                        "resolution_source": getattr(o, "resolution_source", None),
                        "observed_at": (
                            o.last_updated.isoformat()
                            if getattr(o, "last_updated", None) is not None
                            else None
                        ),
                    }
                    for o in (getattr(m, "outcomes", None) or ())
                ],
            }
    else:
        by_id = {}

    raw_sections = rule.get("sections")
    section_keys = (
        tuple(str(s) for s in raw_sections)
        if isinstance(raw_sections, (list, tuple))
        else ("senate_races", "governors")
    )
    raw_excluded = rule.get("excluded_market_ids")
    excluded_market_ids = (
        tuple(int(x) for x in raw_excluded if isinstance(x, int) and not isinstance(x, bool))
        if isinstance(raw_excluded, (list, tuple))
        else (109918, 108629)
    )
    return select_register_closest(
        by_id,
        section_keys=section_keys,
        excluded_market_ids=excluded_market_ids,
        min_open_races=int(rule.get("min_open_races", 3)),
        card_rows=int(rule.get("card_rows", 3)),
        section_title=str(definition.get("section_title") or "Open races"),
        footer=str(definition.get("footer") or "Bain Luck blend · both venues where paired"),
        title=str(definition.get("name") or "") or None,
        kicker=str(definition.get("kicker") or "") or None,
    )


def load_register_closest_definition(
    path: Path = CLOSEST_RACES_DEFINITION_PATH,
) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("kind") != "roundup":
        raise ValueError(f"Invalid register_closest definition at {path}")
    rule = data.get("rule")
    if not isinstance(rule, Mapping) or rule.get("producer") != PRODUCER_KIND_REGISTER_CLOSEST:
        raise ValueError(
            f"Definition {path} must declare rule.producer={PRODUCER_KIND_REGISTER_CLOSEST!r}"
        )
    _validate_narrative_copy(
        str(data.get("name") or ""),
        str(data.get("footer") or ""),
        str(data.get("kicker") or ""),
        str(data.get("section_title") or ""),
    )
    return data


def build_register_closest_producer(
    definition: Mapping[str, Any],
    *,
    enabled: Optional[Callable[[], bool]] = None,
) -> Any:
    RoundupProducer = _rc().RoundupProducer
    slug = str(definition["slug"])
    story_key = f"roundup:{slug.removeprefix('roundup-')}"

    async def _produce(db: Any) -> Any:
        return await produce_register_closest(db, definition)

    return RoundupProducer(
        slug=slug,
        name=str(definition["name"]),
        kind=str(definition.get("kind") or "roundup"),
        category=str(definition.get("category") or "politics"),
        section_title=definition.get("section_title") or "",
        footer=str(definition["footer"]),
        produce=_produce,
        membership=str(definition.get("membership") or "computed-produced"),
        rule=definition.get("rule") if isinstance(definition.get("rule"), Mapping) else None,
        tag=str(definition.get("tag") or "POLITICS"),
        kicker=str(definition.get("kicker") or "CLOSEST RACES"),
        story_key=story_key,
        enabled=enabled if enabled is not None else register_closest_enabled,
    )


CLOSEST_RACES_DEFINITION: dict[str, Any] = load_register_closest_definition(
    CLOSEST_RACES_DEFINITION_PATH
)


async def closest_races(db: Any, *, now: Optional[datetime] = None) -> Any:
    return await produce_register_closest(db, CLOSEST_RACES_DEFINITION, now=now)


CLOSEST_RACES_PRODUCER = build_register_closest_producer(CLOSEST_RACES_DEFINITION)
# Required when register_closest is imported before roundup_containers completes initialization.
_rc().register_roundup_producer(CLOSEST_RACES_PRODUCER)


