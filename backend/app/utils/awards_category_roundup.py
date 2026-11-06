"""Reusable ``awards_category_roundup`` producer kind (#11949 Order 6).

PILLAR: DISCOVER / FORMATTING / TRUTH · SHIP: ``roundup-golden-globes-best-picture``
("Best Picture: who's nominated, who wins") — pairs each nominee's nomination
binary ("Will <film> be nominated for ...?", independent, sums > 100%) with its
winner share in the category's mutually-exclusive winner field ("Best ...
winner", normalized under #11995 decision 6-A), orders by win chance, and emits
the two-bar row contract (`probability` = wins %, `secondary_probability` =
nominated %).

Refuses when:
* No open winner field market exists or it fails #11995 decision 6-A
  (`missing_winner_field` / `winner_field_guard_failed`).
* Fewer than 3 nominees have both a valid winner share and an open nomination
  binary (`too_few_paired_nominees`). Today Golden Globe nomination markets have
  not opened yet, so the producer withholds cleanly until >= 3 nominees are paired.
* A nominee's win probability exceeds its nomination probability by more than
  the 2-percentage-point rounding tolerance (`win_exceeds_nomination:<subject>`),
  since winning requires being nominated.
"""

from __future__ import annotations

import importlib
import json
import math
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

from app.utils.container_presentation import MEMBER_MARKET, market_destination
from app.utils.field_band import _iso_utc, _validate_narrative_copy
from app.utils.futures_liveness import leg_is_graded
from app.utils.outcome_display import (
    display_probability_divisor,
    normalize_display_probs,
)


def _rc() -> Any:
    return importlib.import_module("app.utils.roundup_containers")


__all__ = [
    "GOLDEN_GLOBES_BEST_PICTURE_DEFINITION",
    "GOLDEN_GLOBES_BEST_PICTURE_DEFINITION_PATH",
    "GOLDEN_GLOBES_BEST_PICTURE_ID",
    "GOLDEN_GLOBES_BEST_PICTURE_PRODUCER",
    "GOLDEN_GLOBES_BEST_PICTURE_SLUG",
    "PRODUCER_KIND_AWARDS_CATEGORY",
    "WIN_EXCEEDS_NOMINATION_TOLERANCE",
    "awards_category_enabled",
    "build_awards_category_producer",
    "golden_globes_best_picture",
    "load_awards_category_definition",
    "produce_awards_category_roundup",
    "select_awards_category_roundup",
]

PRODUCER_KIND_AWARDS_CATEGORY = "awards_category_roundup"
WIN_EXCEEDS_NOMINATION_TOLERANCE = 0.02

GOLDEN_GLOBES_BEST_PICTURE_SLUG = "roundup-golden-globes-best-picture"
GOLDEN_GLOBES_BEST_PICTURE_ID = "roundup:golden-globes-best-picture"
GOLDEN_GLOBES_BEST_PICTURE_DEFINITION_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "containers"
    / f"{GOLDEN_GLOBES_BEST_PICTURE_SLUG}.json"
)

_NOMINATION_BINARY_RE = re.compile(
    r"^\s*Will\s+(?P<subject>.+?)\s+be\s+nominated\s+for\s+(?P<category>.+?)\??\s*$",
    re.IGNORECASE,
)


def awards_category_enabled() -> bool:
    return os.getenv("AWARDS_CATEGORY_ROUNDUP_ENABLED", "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _half_up_percent(prob: float) -> int:
    return int(math.floor(prob * 100.0 + 0.5))


def _fold_subject(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip(" \"'“”‘’?.!")).casefold()


_CONFLICTING_AWARD_CATEGORY_TOKENS = (
    "best director",
    "best actor",
    "best actress",
    "best supporting",
    "best screenplay",
    "best original score",
    "best original song",
    "best animated",
    "musical or comedy",
    "television",
    "limited series",
)


def _category_matches(
    text: str,
    *,
    ceremony: str,
    category_name: str,
    category_aliases: Sequence[str] = (),
) -> bool:
    folded = _fold_subject(text)
    if not folded:
        return False
    cat_folded = _fold_subject(category_name)
    for token in _CONFLICTING_AWARD_CATEGORY_TOKENS:
        if token in folded and token not in cat_folded:
            return False
    candidates = [cat_folded] + [
        _fold_subject(alias) for alias in category_aliases if _fold_subject(alias)
    ]
    if "motion picture" in cat_folded or "best picture" in cat_folded:
        candidates.extend(["best motion picture", "best picture"])
    return any(cand and cand in folded for cand in candidates)


def _winner_market_matches_rule(
    name: str,
    *,
    ceremony: str,
    category_name: str,
    category_aliases: Sequence[str] = (),
) -> bool:
    folded = _fold_subject(name)
    if not folded:
        return False
    ceremony_folded = _fold_subject(ceremony)
    if ceremony_folded:
        ceremony_stem = ceremony_folded.rstrip("s")
        if ceremony_stem and ceremony_stem not in folded:
            return False
    return _category_matches(
        name,
        ceremony=ceremony,
        category_name=category_name,
        category_aliases=category_aliases,
    )


@dataclass(frozen=True)
class _PairedNominee:
    subject: str
    winner_market_id: int
    winner_outcome_id: int
    nomination_market_id: int
    win_probability: float
    win_rendered_percent: int
    nomination_probability: float
    nomination_rendered_percent: int
    observed_at: Optional[str]


def select_awards_category_roundup(
    markets: Mapping[int, Mapping[str, Any]] | Sequence[Mapping[str, Any]],
    *,
    ceremony: str = "Golden Globes",
    category_name: str = "Best Motion Picture - Drama",
    category_aliases: Sequence[str] = (),
    winner_market_ids: Sequence[int] = (),
    nomination_market_ids: Sequence[int] = (),
    min_paired_nominees: int = 3,
    card_rows: int = 3,
    require_guard_11995: bool = True,
    win_exceeds_nomination_tolerance: float = WIN_EXCEEDS_NOMINATION_TOLERANCE,
    section_title: str = "Best Picture",
    footer: str = "Several nominees are nominated; one wins.",
    title: Optional[str] = None,
    kicker: Optional[str] = None,
) -> Any:
    """Pure selector for ``awards_category_roundup`` (#11949 Order 6)."""
    rc = _rc()
    RoundupMembers = rc.RoundupMembers
    RoundupRefusal = rc.RoundupRefusal

    _validate_narrative_copy(footer, title or "", kicker or "", section_title)

    seq = markets.values() if isinstance(markets, Mapping) else markets
    raw_list = [
        m
        for m in seq
        if isinstance(m, Mapping)
        and isinstance(m.get("id"), int)
        and not isinstance(m.get("id"), bool)
        and int(m["id"]) > 0
    ]
    if not raw_list:
        return RoundupRefusal((("awards_category", "empty_pool"),))

    winner_id_set = {
        int(x)
        for x in winner_market_ids
        if isinstance(x, int) and not isinstance(x, bool) and int(x) > 0
    }
    nomination_id_set = {
        int(x)
        for x in nomination_market_ids
        if isinstance(x, int) and not isinstance(x, bool) and int(x) > 0
    }

    winner_markets: list[Mapping[str, Any]] = []
    nomination_by_subject: dict[str, tuple[int, float, Optional[str], Mapping[str, Any]]] = {}

    for m in raw_list:
        mid = int(m["id"])
        if str(m.get("status") or "open").strip().lower() != "open":
            continue
        name = str(m.get("name") or "").strip()
        outcomes = m.get("outcomes") or m.get("top_outcomes") or ()
        if not isinstance(outcomes, Sequence) or isinstance(outcomes, (str, bytes)):
            continue

        # Check if this is a per-film nomination binary ("Will <film> be nominated for ...?")
        m_nom = _NOMINATION_BINARY_RE.match(name)
        is_explicit_nom = mid in nomination_id_set or m.get("awards_role") == "nomination"
        if m_nom is not None or is_explicit_nom:
            if nomination_id_set and mid not in nomination_id_set:
                continue
            captured_cat = (
                str(m.get("category_name") or "").strip()
                or (m_nom.group("category").strip() if m_nom is not None else "")
            )
            if not is_explicit_nom and not _category_matches(
                captured_cat,
                ceremony=ceremony,
                category_name=category_name,
                category_aliases=category_aliases,
            ):
                continue
            if is_explicit_nom and captured_cat and not _category_matches(
                captured_cat,
                ceremony=ceremony,
                category_name=category_name,
                category_aliases=category_aliases,
            ):
                continue
            subj = (
                str(m.get("subject") or "").strip()
                or (m_nom.group("subject").strip() if m_nom is not None else "")
            )
            if not subj:
                continue
            yes_prob: Optional[float] = None
            obs_ts = _iso_utc(
                m.get("prices_updated_at")
                or m.get("price_observed_at")
                or m.get("updated_at")
            )
            for o in outcomes:
                if not isinstance(o, Mapping):
                    continue
                if leg_is_graded(o.get("is_winner"), o.get("resolution_source")):
                    yes_prob = None
                    break
                oname = str(o.get("name") or o.get("label") or "").strip().casefold()
                if oname in ("yes", _fold_subject(subj)):
                    p_raw = (
                        o.get("probability")
                        if "probability" in o
                        else o.get("current_probability")
                    )
                    if isinstance(p_raw, (int, float)) and not isinstance(p_raw, bool):
                        p_val = float(p_raw)
                        if math.isfinite(p_val) and 0.0 < p_val < 1.0:
                            yes_prob = p_val
                            obs_ts = (
                                _iso_utc(o.get("observed_at") or o.get("last_updated"))
                                or obs_ts
                            )
                            break
            if yes_prob is not None:
                nomination_by_subject[_fold_subject(subj)] = (mid, yes_prob, obs_ts, m)
            continue

        # Otherwise check if this is the category winner field market
        if len(outcomes) >= 3 and m.get("mutually_exclusive") is not False:
            if winner_id_set:
                if mid not in winner_id_set:
                    continue
            elif m.get("awards_role") != "winner" and not _winner_market_matches_rule(
                name,
                ceremony=ceremony,
                category_name=category_name,
                category_aliases=category_aliases,
            ):
                continue
            winner_markets.append(m)

    if not winner_markets:
        return RoundupRefusal((("awards_category", "missing_winner_field"),))

    winner_market = winner_markets[0]
    w_mid = int(winner_market["id"])
    w_outcomes_raw = (
        winner_market.get("outcomes") or winner_market.get("top_outcomes") or ()
    )
    w_outcome_dicts: list[dict[str, Any]] = []
    w_market_obs = _iso_utc(
        winner_market.get("prices_updated_at")
        or winner_market.get("price_observed_at")
        or winner_market.get("updated_at")
    )

    for idx, o in enumerate(w_outcomes_raw):
        if not isinstance(o, Mapping):
            continue
        if leg_is_graded(o.get("is_winner"), o.get("resolution_source")):
            return RoundupRefusal((("awards_category", f"graded_winner_field:{w_mid}"),))
        label = str(o.get("name") or o.get("label") or "").strip()
        if not label:
            continue
        oid_raw = o.get("id")
        oid = (
            int(oid_raw)
            if isinstance(oid_raw, int) and not isinstance(oid_raw, bool) and oid_raw > 0
            else w_mid * 100 + idx + 1
        )
        p_raw = (
            o.get("probability")
            if "probability" in o
            else o.get("current_probability")
        )
        if not isinstance(p_raw, (int, float)) or isinstance(p_raw, bool):
            return RoundupRefusal((("awards_category", f"unpriced_winner_outcome:{w_mid}"),))
        p_val = float(p_raw)
        if not math.isfinite(p_val) or p_val < 0.0 or p_val > 1.0:
            return RoundupRefusal((("awards_category", f"invalid_winner_probability:{w_mid}"),))
        obs = _iso_utc(o.get("observed_at") or o.get("last_updated")) or w_market_obs
        w_outcome_dicts.append(
            {
                "id": oid,
                "name": label,
                "probability": p_val,
                "observed_at": obs,
            }
        )

    if require_guard_11995:
        divisor = display_probability_divisor(
            w_outcome_dicts,
            mutually_exclusive=True,
            field_complete=True,
            question=str(winner_market.get("name") or category_name),
        )
        if divisor is None:
            return RoundupRefusal(
                (("awards_category", f"winner_field_guard_failed:{w_mid}"),)
            )
        normalize_display_probs(
            w_outcome_dicts,
            mutually_exclusive=True,
            field_complete=True,
            question=str(winner_market.get("name") or category_name),
        )

    paired: list[_PairedNominee] = []
    for od in w_outcome_dicts:
        subj = str(od["name"])
        subj_key = _fold_subject(subj)
        nom_entry = nomination_by_subject.get(subj_key)
        if nom_entry is None:
            continue
        nom_mid, nom_prob, nom_obs, _ = nom_entry
        win_prob = float(od["probability"])
        win_pct = (
            int(od["rendered_percent"])
            if isinstance(od.get("rendered_percent"), int)
            else _half_up_percent(win_prob)
        )
        nom_pct = _half_up_percent(nom_prob)

        # Containment check: winning requires being nominated (allow 2pt rounding tolerance).
        if win_prob > nom_prob + float(win_exceeds_nomination_tolerance) + 1e-9:
            return RoundupRefusal(
                (("awards_category", f"win_exceeds_nomination:{subj_key}"),)
            )

        w_obs = od.get("observed_at")
        oldest_obs = (
            min(w_obs, nom_obs)
            if w_obs and nom_obs
            else (w_obs or nom_obs)
        )
        paired.append(
            _PairedNominee(
                subject=subj,
                winner_market_id=w_mid,
                winner_outcome_id=int(od["id"]),
                nomination_market_id=nom_mid,
                win_probability=win_prob,
                win_rendered_percent=win_pct,
                nomination_probability=nom_prob,
                nomination_rendered_percent=nom_pct,
                observed_at=oldest_obs,
            )
        )

    if len(paired) < min_paired_nominees:
        return RoundupRefusal((("awards_category", "too_few_paired_nominees"),))

    # Order by win chance descending.
    paired.sort(
        key=lambda p: (
            -p.win_probability,
            -p.nomination_probability,
            p.subject.casefold(),
            p.winner_outcome_id,
        )
    )
    shown = paired[:card_rows]

    rows_out: list[dict[str, Any]] = []
    for p in shown:
        rows_out.append(
            {
                "market_id": p.winner_market_id,
                "outcome_id": p.winner_outcome_id,
                "label": p.subject,
                "probability": p.win_probability,
                "rendered_percent": p.win_rendered_percent,
                "secondary_probability": p.nomination_probability,
                "secondary_rendered_percent": p.nomination_rendered_percent,
                "primary_bar_label": "Wins",
                "secondary_bar_label": "Nominated",
                "observed_at": p.observed_at,
            }
        )

    # Container members include the winner field market followed by the paired nomination binaries.
    member_entries: list[dict[str, Any]] = [
        {
            "type": MEMBER_MARKET,
            "id": w_mid,
            "destination": market_destination(w_mid),
            "card": {
                "id": w_mid,
                "name": str(winner_market.get("name") or f"{ceremony}: {category_name} Winner"),
                "category": "entertainment",
                "llm_sport_category": "entertainment",
                "market_tier": 1,
                "market_type": "field",
                "status": "open",
                "source": str(winner_market.get("source") or "kalshi").lower(),
                "sources": [str(winner_market.get("source") or "kalshi").lower()],
                "source_count": 1,
                "mutually_exclusive": True,
                "resolution_date": _iso_utc(winner_market.get("resolution_date")),
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
                    for idx, od in enumerate(w_outcome_dicts)
                ],
                "outcome_count": len(w_outcome_dicts),
                "updated_at": w_market_obs,
                "prices_updated_at": w_market_obs,
                "price_observed_at": w_market_obs,
            },
            "event_id": None,
        }
    ]
    revision_ids: list[int] = [w_mid]
    for p in paired:
        revision_ids.append(p.nomination_market_id)

    sections_out = [
        {
            "class": "title",
            "title": section_title,
            "layout": "field",
            "count": len(member_entries),
            "members": member_entries,
        }
    ]

    return RoundupMembers(
        member_entries,
        rows_out,
        footer=footer,
        title=title,
        kicker=kicker,
        sections=sections_out,
        revision_ids=revision_ids,
    )


async def _load_awards_markets_from_db(
    db: Any, rule: Mapping[str, Any]
) -> dict[int, dict[str, Any]]:
    from sqlalchemy import or_, select
    from sqlalchemy.orm import selectinload

    from app.models.models import FuturesMarket

    ceremony = str(rule.get("ceremony") or "Golden Globes").strip()
    category_name = str(
        rule.get("category_name") or "Best Motion Picture - Drama"
    ).strip()
    raw_winner_ids = rule.get("winner_market_ids") or ()
    raw_nom_ids = rule.get("nomination_market_ids") or ()
    explicit_ids = [
        int(x)
        for x in (*raw_winner_ids, *raw_nom_ids)
        if isinstance(x, int) and not isinstance(x, bool) and int(x) > 0
    ]

    clauses = [
        FuturesMarket.name.ilike(f"%{ceremony}%"),
        FuturesMarket.name.ilike(f"%{category_name}%"),
        FuturesMarket.name.ilike("Will % be nominated for %"),
    ]
    if explicit_ids:
        clauses.append(FuturesMarket.id.in_(explicit_ids))

    stmt = (
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.outcomes))
        .where(
            FuturesMarket.status == "open",
            FuturesMarket.llm_sport_category == "entertainment",
            or_(*clauses),
        )
        .limit(200)
    )
    res = await db.execute(stmt)
    if not hasattr(res, "scalars") or not callable(res.scalars):
        return {}
    scalars_obj = res.scalars()
    if not hasattr(scalars_obj, "all") or not callable(scalars_obj.all):
        return {}
    rows = list(scalars_obj.all())
    out: dict[int, dict[str, Any]] = {}
    for fm in rows:
        if isinstance(fm, Mapping):
            raw_id = fm.get("id")
            if isinstance(raw_id, int) and not isinstance(raw_id, bool) and raw_id > 0:
                entry = dict(fm)
                entry["id"] = int(raw_id)
                out[int(raw_id)] = entry
            continue
        raw_mid = getattr(fm, "id", None)
        if not isinstance(raw_mid, int) or isinstance(raw_mid, bool) or raw_mid <= 0:
            continue
        mid = int(raw_mid)
        out[mid] = {
            "id": mid,
            "name": getattr(fm, "name", None),
            "status": getattr(fm, "status", None),
            "source": getattr(fm, "source", None),
            "resolution_date": getattr(fm, "resolution_date", None),
            "updated_at": getattr(fm, "updated_at", None),
            "mutually_exclusive": getattr(fm, "mutually_exclusive", True),
            "outcomes": [
                {
                    "id": getattr(o, "id", None),
                    "name": getattr(o, "name", None),
                    "probability": getattr(o, "current_probability", None),
                    "is_winner": getattr(o, "is_winner", None),
                    "resolution_source": getattr(o, "resolution_source", None),
                    "observed_at": (
                        o.last_updated.isoformat()
                        if hasattr(getattr(o, "last_updated", None), "isoformat")
                        else getattr(o, "last_updated", None)
                    ),
                }
                for o in (getattr(fm, "outcomes", None) or [])
            ],
        }
    return out


async def produce_awards_category_roundup(
    db: Any,
    definition: Mapping[str, Any],
    *,
    now: Optional[datetime] = None,
) -> Any:
    rule = definition.get("rule")
    if not isinstance(rule, Mapping) or rule.get("producer") != PRODUCER_KIND_AWARDS_CATEGORY:
        raise ValueError(
            f"Unsupported producer kind; expected {PRODUCER_KIND_AWARDS_CATEGORY!r}"
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
    elif hasattr(db, "execute"):
        by_id = await _load_awards_markets_from_db(db, rule)
    else:
        by_id = {}

    raw_aliases = rule.get("category_aliases")
    category_aliases = (
        tuple(str(a) for a in raw_aliases if isinstance(a, str) and a.strip())
        if isinstance(raw_aliases, (list, tuple))
        else ()
    )
    raw_winner_ids = rule.get("winner_market_ids")
    winner_market_ids = (
        tuple(
            int(x)
            for x in raw_winner_ids
            if isinstance(x, int) and not isinstance(x, bool) and int(x) > 0
        )
        if isinstance(raw_winner_ids, (list, tuple))
        else ()
    )
    raw_nom_ids = rule.get("nomination_market_ids")
    nomination_market_ids = (
        tuple(
            int(x)
            for x in raw_nom_ids
            if isinstance(x, int) and not isinstance(x, bool) and int(x) > 0
        )
        if isinstance(raw_nom_ids, (list, tuple))
        else ()
    )

    return select_awards_category_roundup(
        by_id,
        ceremony=str(rule.get("ceremony") or "Golden Globes"),
        category_name=str(rule.get("category_name") or "Best Motion Picture - Drama"),
        category_aliases=category_aliases,
        winner_market_ids=winner_market_ids,
        nomination_market_ids=nomination_market_ids,
        min_paired_nominees=int(rule.get("min_paired_nominees", 3)),
        card_rows=int(rule.get("card_rows", 3)),
        require_guard_11995=bool(rule.get("require_guard_11995", True)),
        win_exceeds_nomination_tolerance=float(
            rule.get("win_exceeds_nomination_tolerance", WIN_EXCEEDS_NOMINATION_TOLERANCE)
        ),
        section_title=str(definition.get("section_title") or "Best Picture"),
        footer=str(definition.get("footer") or "Several nominees are nominated; one wins."),
        title=str(definition.get("name") or "") or None,
        kicker=str(definition.get("kicker") or "") or None,
    )


def load_awards_category_definition(
    path: Path = GOLDEN_GLOBES_BEST_PICTURE_DEFINITION_PATH,
) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("kind") != "roundup":
        raise ValueError(f"Invalid awards_category_roundup definition at {path}")
    rule = data.get("rule")
    if not isinstance(rule, Mapping) or rule.get("producer") != PRODUCER_KIND_AWARDS_CATEGORY:
        raise ValueError(
            f"Definition {path} must declare rule.producer={PRODUCER_KIND_AWARDS_CATEGORY!r}"
        )
    _validate_narrative_copy(
        str(data.get("name") or ""),
        str(data.get("footer") or ""),
        str(data.get("kicker") or ""),
        str(data.get("section_title") or ""),
    )
    return data


def build_awards_category_producer(
    definition: Mapping[str, Any],
    *,
    enabled: Optional[Callable[[], bool]] = None,
) -> Any:
    RoundupProducer = _rc().RoundupProducer
    slug = str(definition["slug"])
    story_key = f"roundup:{slug.removeprefix('roundup-')}"

    async def _produce(db: Any) -> Any:
        return await produce_awards_category_roundup(db, definition)

    return RoundupProducer(
        slug=slug,
        name=str(definition["name"]),
        kind=str(definition.get("kind") or "roundup"),
        category=str(definition.get("category") or "entertainment"),
        section_title=definition.get("section_title") or "",
        footer=str(definition["footer"]),
        produce=_produce,
        membership=str(definition.get("membership") or "computed-produced"),
        rule=definition.get("rule") if isinstance(definition.get("rule"), Mapping) else None,
        tag=str(definition.get("tag") or "ENTERTAINMENT"),
        kicker=str(definition.get("kicker") or "GOLDEN GLOBES"),
        story_key=story_key,
        enabled=enabled if enabled is not None else awards_category_enabled,
    )


GOLDEN_GLOBES_BEST_PICTURE_DEFINITION: dict[str, Any] = load_awards_category_definition(
    GOLDEN_GLOBES_BEST_PICTURE_DEFINITION_PATH
)


async def golden_globes_best_picture(
    db: Any, *, now: Optional[datetime] = None
) -> Any:
    return await produce_awards_category_roundup(
        db, GOLDEN_GLOBES_BEST_PICTURE_DEFINITION, now=now
    )


GOLDEN_GLOBES_BEST_PICTURE_PRODUCER = build_awards_category_producer(
    GOLDEN_GLOBES_BEST_PICTURE_DEFINITION
)
# Required when awards_category_roundup is imported before roundup_containers completes initialization.
_rc().register_roundup_producer(GOLDEN_GLOBES_BEST_PICTURE_PRODUCER)


