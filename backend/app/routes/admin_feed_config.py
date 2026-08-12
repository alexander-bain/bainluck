"""Admin endpoint for feed experiment/config state.

Returns current Redis-backed feed flags so experiment conditions
are provable in audit reports.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.routes.admin_utils import _check_admin_secret
from app.services.database import get_db

router = APIRouter()


@router.get("/feed-config")
async def get_feed_config(request: Request, secret: str = Query(None)):
    """Return current feed experiment state from Redis."""
    _check_admin_secret(secret, request=request)

    from app.tasks.redis_state import get_redis_client

    r = get_redis_client()

    def _get(key: str, default: str = "") -> str:
        val = r.get(key)
        if val is None:
            return default
        return val.decode() if isinstance(val, bytes) else str(val)

    # `_get`'s default is indistinguishable from a real value of the same
    # string — gotcha #53 in miniature, and it mattered: reading "0.2" here
    # could not tell "the weight is 0.2" from "there is no key at all", which
    # are different production states with the same rendering. The presence
    # flags disambiguate, and the blend default is 0.0 to match `feed.py`,
    # where an absent key now means DARK rather than 0.2 (LAT-P043).
    keys = {
        "interestingness_blend_weight": ("interestingness:blend_weight", "0"),
        "snippet_v2_enabled": ("snippet_v2:enabled", "false"),
        "cold_start_boost": ("cold_start:boost_factor", "2.0"),
    }
    out = {name: _get(key, default) for name, (key, default) in keys.items()}
    out["key_present"] = {
        name: bool(r.exists(key)) for name, (key, _default) in keys.items()
    }
    return out


@router.post("/feed-config")
async def set_feed_config(
    request: Request,
    secret: str = Query(None),
    key: str = Query(..., description="Redis key suffix"),
    value: str = Query(..., description="Value to set"),
):
    """Set a feed config Redis key. Admin-only."""
    _check_admin_secret(secret, request=request)

    ALLOWED_KEYS = {
        "interestingness:blend_weight",
        "snippet_v2:enabled",
        "cold_start:boost_factor",
    }
    if key not in ALLOWED_KEYS:
        raise HTTPException(status_code=400, detail=f"Key not in allowed set: {ALLOWED_KEYS}")

    from app.tasks.redis_state import get_redis_client

    r = get_redis_client()
    r.set(key, value)

    return {"key": key, "value": value, "status": "set"}


@router.get("/interestingness-side-by-side")
async def interestingness_side_by_side(
    request: Request,
    secret: str = Query(None),
    weights: str = Query("0,0.2", description="Comma-separated blend weights"),
    limit: int = Query(25, ge=1, le=60),
    db=Depends(get_db),
):
    """Render ONE Discover slate at two or more blend weights, side by side.

    The ratification artifact for Alex's 2026-08-12 ruling: the interestingness
    signal stays dark until he has seen what turning it on does, at a specific
    weight, on a real slate. That decision needs a comparison, and until now the
    only way to produce one was to set the live Redis key — i.e. to ship the
    change to every user in order to find out whether to ship it.

    So the weight is injected per scoring pass (`_score_futures`'s `config`),
    never written anywhere. Nothing about the served feed changes while this
    runs; the live key is not read, not written, and not restored, because it is
    never touched. That is deliberate — a diagnostic that briefly switches the
    blend on for real traffic is the precise accident the dark ruling exists to
    prevent.

    Reads the SAME scorer the feed uses rather than re-deriving the arithmetic.
    An offline replay (`scripts/replay_discover_ranking.py`) models the ranking
    chain faithfully but not the display chain's `+15` cap and `0-98` clamp, so
    a weight ratified against the replay would be a weight ratified against a
    function Discover does not run.

    PRECONDITION, and it is not optional: the `interestingness:*` cache must be
    populated, which it has not been since the OOM that LAT-P042 fixed. With an
    empty cache every weight returns an identical slate and `identical: true`
    is the honest answer — the same output an actually-neutral weight produces.
    `cache_hits` disambiguates those two states; read it before reading anything
    else (gotcha #53).
    """
    _check_admin_secret(secret, request=request)

    from datetime import datetime, timezone

    from app.routes.feed import (
        PersonalizationContext,
        _dedupe_futures_by_canonical,
        _discover_runtime_config_defaults,
        _rank_key,
        _score_futures,
    )

    try:
        parsed = [float(w) for w in weights.split(",") if w.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="weights must be floats")
    if not 2 <= len(parsed) <= 4:
        raise HTTPException(status_code=400, detail="pass 2-4 weights")
    if any(w < 0 or w > 1 for w in parsed):
        raise HTTPException(status_code=400, detail="weights must be within 0..1")

    now = datetime.now(timezone.utc)
    slates: dict[str, list[dict]] = {}

    for w in parsed:
        config = dict(_discover_runtime_config_defaults())
        config["interestingness_blend_weight_override"] = w
        rows = await _score_futures(
            db,
            now,
            sport_filter=None,
            ctx=PersonalizationContext(),
            my_teams_only=False,
            config=config,
        )
        rows = _dedupe_futures_by_canonical(rows)
        rows.sort(key=_rank_key, reverse=True)
        key = str(w)
        slates[key] = [
            {
                "rank": i,
                "market_id": (r.get("data") or {}).get("id"),
                "name": (r.get("data") or {}).get("name"),
                "category": (r.get("data") or {}).get("llm_sport_category"),
                "rank_score": round(float(r.get("_rank_score") or 0), 2),
                "display_score": round(float(r.get("score") or 0), 2),
                "headline": r.get("headline"),
            }
            for i, r in enumerate(rows[:limit], start=1)
        ]

    base_key = str(parsed[0])

    # How many of these cards even HAVE a cached interestingness score. Counted
    # from Redis directly rather than inferred from the slate, because "the
    # slates are identical" has two causes with one appearance: a weight that
    # genuinely changes nothing, and an empty cache that cannot change anything
    # (gotcha #53). Without this number the ratification artifact is unreadable.
    slate_ids = [
        row["market_id"] for row in slates[base_key] if row["market_id"] is not None
    ]
    cache_hits = {"sampled_market_ids": len(slate_ids), "cached": None}
    if slate_ids:
        try:
            from app.utils.request_cache import bounded_redis_call, get_shared_async_redis

            _redis = await get_shared_async_redis()
            res = await bounded_redis_call(
                lambda: _redis.mget([f"interestingness:{i}" for i in slate_ids]),
                treat_none_as_miss=False,
            )
            if res.is_ok:
                cache_hits["cached"] = sum(1 for v in (res.value or []) if v is not None)
        except Exception:
            # `None` stays `None`: unmeasured is not zero.
            pass

    base_ranks = {row["market_id"]: row["rank"] for row in slates[base_key]}
    comparison = {}
    for key, rows in slates.items():
        if key == base_key:
            continue
        moved, entered = [], []
        for row in rows:
            was = base_ranks.get(row["market_id"])
            if was is None:
                entered.append(row)
            elif was != row["rank"]:
                moved.append({**row, "rank_at_base": was, "delta": was - row["rank"]})
        left = [
            r for r in slates[base_key]
            if r["market_id"] not in {x["market_id"] for x in rows}
        ]
        comparison[key] = {
            "identical": not moved and not entered and not left,
            "positions_changed": len(moved),
            "entered_top_n": entered,
            "left_top_n": left,
            "biggest_movers": sorted(
                moved, key=lambda m: abs(m["delta"]), reverse=True
            )[:10],
        }

    return {
        "generated_at": now.isoformat(),
        "weights": parsed,
        "limit": limit,
        "live_key_untouched": True,
        "cache_hits": cache_hits,
        "cache_populated": bool(cache_hits.get("cached")),
        "comparison": comparison,
        "slates": slates,
    }
