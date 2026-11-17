"""#12577 — Server-side paired-metric register & live DB venue probability blending.

Moves equivalent-venue blending for paired-metric sets (such as Kalshi #5165726 +
Polymarket #27988771 for Best Picture Nominee) onto the server via
``blend_with_verdict`` in ``app.utils.futures_source_merge``, and hydrates live
``FuturesMarket`` / ``FuturesOutcome`` rows on reader-facing surfaces (Discover,
Oscars collection, event concept page, and category market pages).

Unbending rules (#12577):
1. Stage 1 (e.g. Nominated / Make Playoffs) and Stage 2 (e.g. Wins / Win Title)
   are distinct propositions and are NEVER blended with each other.
2. Equivalent venue legs for the SAME stage (e.g. Kalshi + Polymarket for Stage 1)
   are blended on the server via ``blend_with_verdict``, serving ``blend_rule``
   and ``divergence`` beside the number.
3. Reader-facing surfaces ALWAYS hydrate live DB ``FuturesMarket`` / ``FuturesOutcome``
   rows (``allow_register_fallback=False``) — static register numbers are never
   served as live prices if a market is missing or withdrawn.
"""

from __future__ import annotations

import copy
import json
import math
import re
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.utils.futures_source_merge import blend_with_verdict

PAIRED_METRIC_REGISTER_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "groupings"
    / "paired_metric_register.json"
)

SERVER_BLEND_AUTHORITY = "server:futures_source_merge.blend_with_verdict"
SINGLE_VENUE_AUTHORITY = "single_venue"
_SETTLED_STATUSES = frozenset({"resolved", "settled", "closed", "finalized", "final"})


def _valid_prob(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return None
    fval = float(value)
    if not math.isfinite(fval) or fval < 0.0 or fval > 1.0:
        return None
    return fval


def _iso_stamp(val: Any) -> str | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        dt = val if val.tzinfo is not None else val.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    s = str(val).strip()
    return s or None


def fold_outcome_key(text: str | None) -> str:
    """Normalize outcome names across venues (diacritics, '&' vs 'and', punctuation)."""
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", str(text))
    ascii_only = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    lowered = ascii_only.lower().replace("&", " and ")
    cleaned = re.sub(r"[^a-z0-9\s]", " ", lowered)
    return re.sub(r"\s+", " ", cleaned).strip()


def clean_card_face_subtitle(subtitle: str | None) -> str:
    """Strip internal market ID annotations (#5165726) and venue implementation notes."""
    raw = str(subtitle or "").strip()
    if not raw:
        return ""
    cleaned = re.sub(r"\s*·\s*Nominee\s*%.*$", "", raw, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*·\s*Paired by club.*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*·\s*Verified [A-Za-z0-9\s]+$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*\(ordered by [^)]*\)", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*\([^)]*#\d+[^)]*\)", "", cleaned)
    return cleaned.strip(" ·")


def compute_server_venue_blend(
    kalshi_prob: float | None,
    polymarket_prob: float | None,
    *,
    kalshi_updated_at: str | None = None,
    polymarket_updated_at: str | None = None,
) -> tuple[float | None, str | None, dict[str, Any] | None, str | None]:
    """Compute the server-side blend for a single stage across Kalshi and Polymarket."""
    _ = (kalshi_updated_at, polymarket_updated_at)
    k_val = _valid_prob(kalshi_prob)
    p_val = _valid_prob(polymarket_prob)

    rows: list[dict[str, Any]] = []
    if k_val is not None:
        rows.append({"source": "kalshi", "probability": k_val})
    if p_val is not None:
        rows.append({"source": "polymarket", "probability": p_val})

    if not rows:
        return None, None, None, None

    blended, divergence, rule_name = blend_with_verdict(rows)
    div_evidence = divergence.as_evidence() if divergence is not None else None
    authority = (
        SERVER_BLEND_AUTHORITY
        if (k_val is not None and p_val is not None)
        else SINGLE_VENUE_AUTHORITY
    )
    return blended, rule_name, div_evidence, authority


def hydrate_paired_metric_entry(raw_entry: Mapping[str, Any]) -> dict[str, Any]:
    """Hydrate a single paired-metric entry with server-blended stage probabilities."""
    entry = copy.deepcopy(dict(raw_entry))

    s1_k = _valid_prob(entry.get("stage_1_kalshi_probability"))
    s1_p = _valid_prob(entry.get("stage_1_polymarket_probability"))
    if s1_k is not None or s1_p is not None:
        blended_s1, rule_s1, div_s1, auth_s1 = compute_server_venue_blend(
            s1_k,
            s1_p,
            kalshi_updated_at=entry.get("stage_1_kalshi_updated_at"),
            polymarket_updated_at=entry.get("stage_1_polymarket_updated_at"),
        )
        entry["stage_1_probability"] = blended_s1
        entry["stage_1_blend_rule"] = rule_s1
        entry["stage_1_divergence"] = div_s1
        entry["stage_1_blend_authority"] = auth_s1
    elif _valid_prob(entry.get("stage_1_probability")) is not None:
        entry["stage_1_blend_rule"] = None
        entry["stage_1_divergence"] = None
        entry["stage_1_blend_authority"] = SINGLE_VENUE_AUTHORITY
    else:
        entry["stage_1_probability"] = None
        entry["stage_1_blend_rule"] = None
        entry["stage_1_divergence"] = None
        entry["stage_1_blend_authority"] = None

    s2_k = _valid_prob(entry.get("stage_2_kalshi_probability"))
    s2_p = _valid_prob(entry.get("stage_2_polymarket_probability"))
    if s2_k is not None or s2_p is not None:
        blended_s2, rule_s2, div_s2, auth_s2 = compute_server_venue_blend(
            s2_k,
            s2_p,
            kalshi_updated_at=entry.get("stage_2_kalshi_updated_at"),
            polymarket_updated_at=entry.get("stage_2_polymarket_updated_at"),
        )
        entry["stage_2_probability"] = blended_s2
        entry["stage_2_blend_rule"] = rule_s2
        entry["stage_2_divergence"] = div_s2
        entry["stage_2_blend_authority"] = auth_s2
    elif _valid_prob(entry.get("stage_2_probability")) is not None:
        entry["stage_2_blend_rule"] = None
        entry["stage_2_divergence"] = None
        entry["stage_2_blend_authority"] = SINGLE_VENUE_AUTHORITY
    else:
        entry["stage_2_probability"] = None
        entry["stage_2_blend_rule"] = None
        entry["stage_2_divergence"] = None
        entry["stage_2_blend_authority"] = None

    return entry


def hydrate_paired_metric_set(raw_set: Mapping[str, Any]) -> dict[str, Any]:
    """Hydrate a paired-metric set's entries from register fields (for `/grade/groupings`)."""
    hydrated = copy.deepcopy(dict(raw_set))
    entries = [
        hydrate_paired_metric_entry(e)
        for e in (raw_set.get("entries") or [])
        if isinstance(e, Mapping)
    ]
    hydrated["entries"] = entries
    hydrated["blend_authority"] = SERVER_BLEND_AUTHORITY
    return hydrated


def load_paired_metric_register(
    register_path: Path | None = None,
) -> dict[str, Any]:
    """Load `paired_metric_register.json` and hydrate every set on the server."""
    target = register_path or PAIRED_METRIC_REGISTER_PATH
    raw = json.loads(target.read_text(encoding="utf-8"))
    out = copy.deepcopy(raw)
    out.setdefault("rules", {})["blend_authority"] = SERVER_BLEND_AUTHORITY
    raw_sets = raw.get("sets") or {}
    out["sets"] = {
        set_id: hydrate_paired_metric_set(set_data)
        for set_id, set_data in raw_sets.items()
        if isinstance(set_data, Mapping)
    }
    return out


def collect_paired_register_market_ids(
    raw_sets: Mapping[str, Mapping[str, Any]],
) -> set[int]:
    """Return every `FuturesMarket.id` referenced across `raw_sets`."""
    ids: set[int] = set()
    for s in raw_sets.values():
        if not isinstance(s, Mapping):
            continue
        for mkey in ("stage_1_market", "stage_2_market"):
            m = s.get(mkey)
            if isinstance(m, Mapping):
                mid = m.get("id")
                if isinstance(mid, int) and not isinstance(mid, bool) and mid > 0:
                    ids.add(mid)
                comp = m.get("companion_polymarket_id")
                if isinstance(comp, int) and not isinstance(comp, bool) and comp > 0:
                    ids.add(comp)
        for e in s.get("entries") or ():
            if not isinstance(e, Mapping):
                continue
            for ekey in (
                "stage_1_market_id",
                "stage_1_polymarket_market_id",
                "stage_2_market_id",
            ):
                eid = e.get(ekey)
                if isinstance(eid, int) and not isinstance(eid, bool) and eid > 0:
                    ids.add(eid)
    return ids


def find_paired_set_id_for_market(
    market_id: int,
    register_path: Path | None = None,
) -> str | None:
    """Return the `set_id` whose `stage_1` or `stage_2` market matches `market_id`, if any."""
    if not isinstance(market_id, int) or isinstance(market_id, bool) or market_id <= 0:
        return None
    target = register_path or PAIRED_METRIC_REGISTER_PATH
    raw = json.loads(target.read_text(encoding="utf-8"))
    for set_id, s in (raw.get("sets") or {}).items():
        if not isinstance(s, Mapping):
            continue
        if market_id in collect_paired_register_market_ids({set_id: s}):
            return str(set_id)
    return None


def _match_outcome_in_market(
    market: Mapping[str, Any] | None,
    *candidate_names: str | None,
) -> Mapping[str, Any] | None:
    if not isinstance(market, Mapping):
        return None
    outcomes = market.get("outcomes") or market.get("top_outcomes") or ()
    if not isinstance(outcomes, Sequence) or isinstance(outcomes, (str, bytes)):
        return None
    folded_targets = [fold_outcome_key(c) for c in candidate_names if fold_outcome_key(c)]
    if not folded_targets:
        return None
    by_folded: dict[str, Mapping[str, Any]] = {}
    for out in outcomes:
        if isinstance(out, Mapping):
            key = fold_outcome_key(out.get("name") or out.get("label"))
            if key and key not in by_folded:
                by_folded[key] = out
    for target in folded_targets:
        if target in by_folded:
            return by_folded[target]
    return None


def _category_short_label_from_kicker(kicker: str, fallback: str) -> str:
    if "·" in kicker:
        tail = kicker.split("·", 1)[1].strip()
        if tail:
            return tail.title() if tail.isupper() else tail
    return fallback


def _compose_live_paired_title(
    raw_set: Mapping[str, Any],
    entries: Sequence[Mapping[str, Any]],
    *,
    stage_1_settled: bool,
    stage_2_winner: str | None,
) -> str:
    kicker = str(raw_set.get("kicker") or "")
    cat_label = _category_short_label_from_kicker(kicker, "this category")
    if stage_2_winner:
        return f"{stage_2_winner} wins {cat_label}"

    ranked = sorted(
        entries,
        key=lambda e: (
            -(e.get("stage_2_probability") if isinstance(e.get("stage_2_probability"), (int, float)) else -1.0),
            -(e.get("stage_1_probability") if isinstance(e.get("stage_1_probability"), (int, float)) else -1.0),
            str(e.get("subject") or ""),
        ),
    )
    if not ranked:
        return str(raw_set.get("title") or cat_label)

    leader = str(ranked[0].get("subject") or "").strip()
    if stage_1_settled:
        nom_count = sum(1 for e in entries if e.get("stage_1_settled_state") == "yes")
        if nom_count >= 2:
            return f"{leader} leads the {nom_count} {cat_label} nominees"
        return f"{leader} leads {cat_label}"

    is_person_set = any(
        str(e.get("subject_key") or "").startswith("person:") for e in entries
    )
    is_team_set = any(
        str(e.get("subject_key") or "").startswith("team:") for e in entries
    )
    unit = "contenders" if is_person_set else "teams" if is_team_set else "films"
    s1_verb = (
        "to make the playoffs"
        if "playoff" in str(raw_set.get("stage_1_label") or "").lower()
        else "to be nominated"
    )
    high_s1 = sum(
        1
        for e in entries
        if isinstance(e.get("stage_1_probability"), (int, float))
        and float(e["stage_1_probability"]) >= 0.75
    )
    if high_s1 >= 2:
        return f"{leader} leads {cat_label}, with {high_s1} {unit} at 75%+ {s1_verb}"
    if len(ranked) >= 2:
        runner_up = str(ranked[1].get("subject") or "").strip()
        if runner_up:
            return f"{leader} leads {cat_label} ahead of {runner_up}"
    return f"{leader} leads {cat_label}"


def hydrate_paired_metric_set_from_markets(
    raw_set: Mapping[str, Any],
    markets_by_id: Mapping[int, Mapping[str, Any]],
    *,
    min_paired_entries: int = 3,
    allow_register_fallback: bool = False,
) -> dict[str, Any] | None:
    """Hydrate `raw_set` strictly from live `markets_by_id` rows (never stale snapshot numbers)."""
    s1_meta = raw_set.get("stage_1_market") if isinstance(raw_set.get("stage_1_market"), Mapping) else {}
    s2_meta = raw_set.get("stage_2_market") if isinstance(raw_set.get("stage_2_market"), Mapping) else {}
    s1_id = int(s1_meta.get("id") or 0)
    s1_poly_id = int(s1_meta.get("companion_polymarket_id") or 0)
    s2_id = int(s2_meta.get("id") or 0)

    m_s1 = markets_by_id.get(s1_id) if s1_id > 0 else None
    m_s1_poly = markets_by_id.get(s1_poly_id) if s1_poly_id > 0 else None
    m_s2 = markets_by_id.get(s2_id) if s2_id > 0 else None

    if m_s2 is None and m_s1 is None and m_s1_poly is None:
        if allow_register_fallback:
            return hydrate_paired_metric_set(raw_set)
        return None

    if m_s2 is None or str(m_s2.get("status") or "open").strip().lower() == "withdrawn":
        return None
    if (
        (m_s1 is None or str(m_s1.get("status") or "open").strip().lower() == "withdrawn")
        and (m_s1_poly is None or str(m_s1_poly.get("status") or "open").strip().lower() == "withdrawn")
    ):
        return None

    s1_primary_status = str((m_s1 or m_s1_poly or {}).get("status") or "open").strip().lower()
    s1_outs_all = ((m_s1 or m_s1_poly or {}).get("outcomes") or ())
    s1_has_graded_winner = any(
        isinstance(o, Mapping) and o.get("is_winner") is True for o in s1_outs_all
    )
    stage_1_settled = (s1_primary_status in _SETTLED_STATUSES and s1_has_graded_winner) or bool(
        raw_set.get("stage_1_settled")
    )

    s2_status = str(m_s2.get("status") or "open").strip().lower()
    s2_outs_all = m_s2.get("outcomes") or ()
    stage_2_winner_out = next(
        (o for o in s2_outs_all if isinstance(o, Mapping) and o.get("is_winner") is True),
        None,
    )
    stage_2_settled = s2_status in _SETTLED_STATUSES and stage_2_winner_out is not None

    hydrated_entries: list[dict[str, Any]] = []
    observed_stamps: list[str] = []
    stage_2_winner_subject: str | None = None

    for raw_entry in raw_set.get("entries") or ():
        if not isinstance(raw_entry, Mapping):
            continue
        entry = copy.deepcopy(dict(raw_entry))
        # Clear static snapshot probabilities so every served figure comes strictly from `markets_by_id`
        for k in (
            "stage_1_probability",
            "stage_1_kalshi_probability",
            "stage_1_polymarket_probability",
            "stage_2_probability",
            "stage_2_kalshi_probability",
            "stage_2_polymarket_probability",
        ):
            entry.pop(k, None)

        e_s1_market = markets_by_id.get(int(entry.get("stage_1_market_id") or s1_id)) or m_s1
        e_s1_poly_market = (
            markets_by_id.get(int(entry.get("stage_1_polymarket_market_id") or s1_poly_id))
            or m_s1_poly
        )
        e_s2_market = markets_by_id.get(int(entry.get("stage_2_market_id") or s2_id)) or m_s2

        out_s1_k = _match_outcome_in_market(
            e_s1_market, entry.get("stage_1_outcome"), entry.get("subject")
        )
        out_s1_p = _match_outcome_in_market(
            e_s1_poly_market,
            entry.get("stage_1_polymarket_outcome"),
            entry.get("stage_1_outcome"),
            entry.get("subject"),
        )
        out_s2 = _match_outcome_in_market(
            e_s2_market, entry.get("stage_2_outcome"), entry.get("subject")
        )

        # Populate per-venue Stage 1 probabilities based on venue source
        if out_s1_k is not None:
            src_1 = str((e_s1_market or {}).get("source") or "kalshi").strip().lower()
            p1 = _valid_prob(out_s1_k.get("probability"))
            obs1 = _iso_stamp(out_s1_k.get("observed_at") or out_s1_k.get("last_updated"))
            if obs1:
                observed_stamps.append(obs1)
            if "poly" in src_1 and out_s1_p is None:
                entry["stage_1_polymarket_probability"] = p1
            else:
                entry["stage_1_kalshi_probability"] = p1
            if stage_1_settled:
                if out_s1_k.get("is_winner") is True:
                    entry["stage_1_settled_state"] = "yes"
                elif out_s1_k.get("is_winner") is False:
                    entry["stage_1_settled_state"] = "no"

        if out_s1_p is not None and e_s1_poly_market is not e_s1_market:
            p1_poly = _valid_prob(out_s1_p.get("probability"))
            obs1p = _iso_stamp(out_s1_p.get("observed_at") or out_s1_p.get("last_updated"))
            if obs1p:
                observed_stamps.append(obs1p)
            entry["stage_1_polymarket_probability"] = p1_poly

        if out_s2 is not None:
            src_2 = str((e_s2_market or {}).get("source") or "kalshi").strip().lower()
            p2 = _valid_prob(out_s2.get("probability"))
            obs2 = _iso_stamp(out_s2.get("observed_at") or out_s2.get("last_updated"))
            if obs2:
                observed_stamps.append(obs2)
            if "poly" in src_2:
                entry["stage_2_polymarket_probability"] = p2
            else:
                entry["stage_2_kalshi_probability"] = p2
            entry["stage_2_outcome_id"] = out_s2.get("id")
            if stage_2_settled and out_s2.get("is_winner") is True:
                stage_2_winner_subject = str(entry.get("subject") or "")

        hydrated_entry = hydrate_paired_metric_entry(entry)
        has_s1 = (
            hydrated_entry.get("stage_1_probability") is not None
            or hydrated_entry.get("stage_1_settled_state") in {"yes", "no"}
        )
        if has_s1:
            hydrated_entries.append(hydrated_entry)

    both_priced_count = sum(
        1
        for e in hydrated_entries
        if (
            e.get("stage_1_probability") is not None
            or e.get("stage_1_settled_state") in {"yes", "no"}
        )
        and e.get("stage_2_probability") is not None
    )
    if both_priced_count < min_paired_entries and not stage_2_settled:
        return None

    hydrated = copy.deepcopy(dict(raw_set))
    hydrated["entries"] = hydrated_entries
    hydrated["stage_1_settled"] = stage_1_settled
    hydrated["stage_2_settled"] = stage_2_settled
    hydrated["stage_2_winner_subject"] = stage_2_winner_subject
    hydrated["blend_authority"] = SERVER_BLEND_AUTHORITY
    hydrated["title"] = _compose_live_paired_title(
        raw_set,
        hydrated_entries,
        stage_1_settled=stage_1_settled,
        stage_2_winner=stage_2_winner_subject,
    )
    cleaned_sub = clean_card_face_subtitle(str(raw_set.get("subtitle") or ""))
    hydrated["subtitle"] = (
        cleaned_sub
        or f"{raw_set.get('stage_1_label', 'Nominated')} % and {raw_set.get('stage_2_label', 'Wins')} % side by side"
    )
    if observed_stamps:
        # #7785 floor rule: oldest observed timestamp across rendered contenders
        hydrated["as_of"] = min(observed_stamps)
    return hydrated


def serialize_futures_market_for_pairing(fm: Any) -> dict[str, Any]:
    """Convert an ORM `FuturesMarket` (with `.outcomes` loaded) into a plain dict."""
    mkt_obs = _iso_stamp(getattr(fm, "prices_updated_at", None) or getattr(fm, "updated_at", None))
    outs_list: list[dict[str, Any]] = []
    for o in getattr(fm, "outcomes", None) or []:
        raw_p = getattr(o, "current_probability", None)
        if raw_p is None:
            raw_p = getattr(o, "probability", None)
        outs_list.append(
            {
                "id": int(o.id),
                "name": str(getattr(o, "name", "") or ""),
                "probability": _valid_prob(raw_p),
                "is_winner": getattr(o, "is_winner", None),
                "observed_at": _iso_stamp(getattr(o, "last_updated", None)) or mkt_obs,
            }
        )
    return {
        "id": int(fm.id),
        "name": str(getattr(fm, "name", "") or ""),
        "status": str(getattr(fm, "status", "open") or "open"),
        "source": str(getattr(fm, "source", "") or ""),
        "category": str(getattr(fm, "llm_sport_category", None) or getattr(fm, "category", None) or "entertainment"),
        "mutually_exclusive": getattr(fm, "mutually_exclusive", None),
        "resolution_date": _iso_stamp(getattr(fm, "resolution_date", None)),
        "prices_updated_at": mkt_obs,
        "updated_at": mkt_obs,
        "outcomes": outs_list,
    }


async def load_live_paired_metric_sets(
    db: Any,
    *,
    set_ids: Sequence[str] | None = None,
    prefix: str | None = None,
    register_path: Path | None = None,
) -> dict[str, dict[str, Any]]:
    """Query PostgreSQL once for all referenced markets and return live-hydrated paired sets."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models.models import FuturesMarket

    target = register_path or PAIRED_METRIC_REGISTER_PATH
    raw = json.loads(target.read_text(encoding="utf-8"))
    raw_sets = raw.get("sets") or {}

    selected_raw: dict[str, Mapping[str, Any]] = {}
    wanted = set(set_ids) if set_ids is not None else None
    for sid, sdata in raw_sets.items():
        if not isinstance(sdata, Mapping):
            continue
        if wanted is not None and sid not in wanted:
            continue
        if prefix is not None and not str(sid).startswith(prefix):
            continue
        selected_raw[str(sid)] = sdata

    if not selected_raw:
        return {}

    market_ids = collect_paired_register_market_ids(selected_raw)
    if not market_ids:
        return {}

    markets_by_id: dict[int, Mapping[str, Any]] = {}
    if isinstance(db, Mapping):
        markets_by_id = {int(k): v for k, v in db.items() if isinstance(v, Mapping)}
    elif isinstance(db, (list, tuple)):
        markets_by_id = {
            int(m["id"]): m
            for m in db
            if isinstance(m, Mapping)
            and isinstance(m.get("id"), int)
            and not isinstance(m.get("id"), bool)
        }
    elif hasattr(db, "execute"):
        stmt = (
            select(FuturesMarket)
            .options(selectinload(FuturesMarket.outcomes))
            .where(FuturesMarket.id.in_(sorted(market_ids)))
        )
        rows = (await db.execute(stmt)).scalars().all()
        for fm in rows:
            if isinstance(fm, Mapping):
                mid = fm.get("id")
                if isinstance(mid, int) and not isinstance(mid, bool) and mid in market_ids:
                    markets_by_id[int(mid)] = fm
            elif getattr(fm, "id", None) is not None:
                mid = int(fm.id)
                if mid in market_ids:
                    markets_by_id[mid] = serialize_futures_market_for_pairing(fm)

    hydrated_sets: dict[str, dict[str, Any]] = {}
    for sid, sdata in selected_raw.items():
        hydrated = hydrate_paired_metric_set_from_markets(
            sdata, markets_by_id, allow_register_fallback=False
        )
        if hydrated is not None:
            hydrated_sets[sid] = hydrated
    return hydrated_sets
