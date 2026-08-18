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
    stage: str = Query(
        "ranked",
        description="'ranked' (pre-interleave, the historical default) or 'served'",
    ),
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

    ## `?stage=` — WHICH list you are ratifying against (#1923)

    `ranked` (the default, and unchanged) stops at the sort, exactly as this
    endpoint always has. That is a real list, but **it is not the page.**
    `get_feed` runs eleven more stages after that sort — the Discover demotion,
    the noise filter, the category-mix balance, the literal interleave, a
    first-page re-pick under per-story/per-category/per-archetype quotas, the
    editorial tail, four bundle assemblers and lead composition — and it
    interleaves an events pool this mode does not even build.

    So a `ranked` delta can go two ways, and the old output could not tell them
    apart:

    * **ABSORBED** — two cards in one category group swap ranks 6 and 9,
      `positions_changed` moves by 2, and the served page is byte-identical.
    * **AMPLIFIED** — one card crosses a quota boundary, evicts another and
      pulls a third up from rank 24.

    `served` runs the **shared** `apply_discover_display_chain` — the same
    function `get_feed` calls, never a second copy — over the same populations,
    and reports `absorbed` / `amplified` per weight. `ranked` remains the
    default so every artifact produced before this change stays comparable
    (ruling 069: a changed default silently re-bases every prior comparison).

    `served` is a full Discover build per weight, so it is bounded: **2 weights,
    `limit <= 20`**, 400 outside that, and `build_ms` per weight so the
    instrument prices itself in its own output.

    The events pool is scored ONCE and **deep-copied per weight**, which is
    reported as `events_scored_once` rather than left for a reader to assume.
    The copy is not defensive habit: the chain writes `score`/`_rank_score` onto
    event dicts in place, so a shared pool would hand weight 2 weight 1's
    demotions.
    """
    _check_admin_secret(secret, request=request)

    import copy
    import time
    from datetime import datetime, timezone

    from app.routes.feed import (
        PersonalizationContext,
        _dedupe_futures_by_canonical,
        _discover_runtime_config_defaults,
        _rank_key,
        _score_event_concepts,
        _score_events,
        _score_futures,
        _score_golf_tournaments,
        _suppress_zero_probability_cards,
        apply_discover_display_chain,
        enrich_event_team_data,
    )

    stage = (stage or "ranked").strip().lower()
    if stage not in ("ranked", "served"):
        raise HTTPException(
            status_code=400, detail="stage must be 'ranked' or 'served'"
        )

    try:
        parsed = [float(w) for w in weights.split(",") if w.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="weights must be floats")
    if not 2 <= len(parsed) <= 4:
        raise HTTPException(status_code=400, detail="pass 2-4 weights")
    if any(w < 0 or w > 1 for w in parsed):
        raise HTTPException(status_code=400, detail="weights must be within 0..1")
    if stage == "served" and (len(parsed) > 2 or limit > 20):
        # Refused rather than silently truncated: a bound that quietly clips the
        # request produces an artifact whose caption ("4 weights") disagrees
        # with its body.
        raise HTTPException(
            status_code=400,
            detail=(
                "stage=served runs a full Discover build per weight: pass exactly "
                "2 weights and limit<=20 "
                f"(got {len(parsed)} weights, limit={limit})"
            ),
        )

    # Discover's own event ratio. `get_feed` substitutes 0.15 for an
    # unparameterized main-feed request, and that is the slate under discussion.
    SERVED_EVENT_PCT = 0.15

    now = datetime.now(timezone.utc)
    slates: dict[str, list[dict]] = {}
    served_slates: dict[str, list[dict]] = {}
    build_ms: dict[str, dict] = {}

    # --- the events pool, built ONCE ----------------------------------------
    events_pool: list[dict] = []
    events_pool_meta: dict = {"events_scored_once": False}
    if stage == "served":
        _t0 = time.perf_counter()
        _ctx = PersonalizationContext()
        _counts = {}
        for label, coro in (
            ("events", _score_events(db, now, None, _ctx)),
            ("golf_tournaments", _score_golf_tournaments(db, now, None, _ctx)),
            ("concepts", _score_event_concepts(db, now, None, _ctx)),
        ):
            try:
                got = await coro
            except Exception as exc:  # noqa: BLE001
                # A pool that failed to build is NOT an empty pool, and the
                # difference decides whether the artifact is readable.
                _counts[label] = f"error:{type(exc).__name__}"
                continue
            got = got or []
            _counts[label] = len(got)
            events_pool.extend(got)
        # Without this the noise filter drops live games for having no team
        # media, and the served population silently shrinks. See
        # `enrich_event_team_data`.
        await enrich_event_team_data(db, events_pool)
        events_pool_meta = {
            "events_scored_once": True,
            "event_pct": SERVED_EVENT_PCT,
            "pool_size": len(events_pool),
            "pool_counts": _counts,
            "deep_copied_per_weight": True,
            "build_ms": round((time.perf_counter() - _t0) * 1000, 1),
        }

    def _card_key(item: dict) -> str:
        data = item.get("data") or {}
        ident = data.get("id")
        if ident is None:
            ident = data.get("slug") or data.get("name") or item.get("headline")
        return f"{item.get('type')}:{ident}"

    def _row(i: int, r: dict) -> dict:
        data = r.get("data") or {}
        return {
            "rank": i,
            "card_key": _card_key(r),
            "type": r.get("type"),
            "market_id": data.get("id") if r.get("type") == "futures" else None,
            "name": data.get("name"),
            "category": data.get("llm_sport_category"),
            "rank_score": round(float(r.get("_rank_score") or 0), 2),
            "display_score": round(float(r.get("score") or 0), 2),
            "headline": r.get("headline"),
        }

    for w in parsed:
        key = str(w)
        _t_score = time.perf_counter()
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
        _score_ms = (time.perf_counter() - _t_score) * 1000

        # `ranked` is computed in BOTH modes — it is the pre-interleave arm of
        # the absorbed/amplified comparison, not merely the other option.
        ranked_rows = sorted(rows, key=_rank_key, reverse=True)
        slates[key] = [_row(i, r) for i, r in enumerate(ranked_rows[:limit], start=1)]

        if stage == "served":
            _t_chain = time.perf_counter()
            pool = copy.deepcopy(events_pool)
            items = pool + list(rows)
            items, _zero_dropped = _suppress_zero_probability_cards(items)
            served, _meta = apply_discover_display_chain(
                items,
                limit=limit,
                ctx=PersonalizationContext(),
                event_pct=SERVED_EVENT_PCT,
                include_events=True,
                my_teams_only=False,
            )
            served_slates[key] = [
                _row(i, r) for i, r in enumerate(served[:limit], start=1)
            ]
            build_ms[key] = {
                "score_futures_ms": round(_score_ms, 1),
                "display_chain_ms": round((time.perf_counter() - _t_chain) * 1000, 1),
                "zero_probability_dropped": _zero_dropped,
                "pool_in": len(items),
                "chain_out": len(served),
            }
        else:
            build_ms[key] = {"score_futures_ms": round(_score_ms, 1)}

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

    def _compare(all_slates: dict[str, list[dict]]) -> dict:
        """Base-vs-weight movement within one stage.

        Keyed on `card_key`, not `market_id`, because a served slate carries
        events and bundles whose `market_id` is `None` — they would all collide
        onto one key. For a futures-only `ranked` slate `card_key` is a
        bijection with `market_id`, so this changes no historical number.
        """
        base_ranks_local = {row["card_key"]: row["rank"] for row in all_slates[base_key]}
        out = {}
        for key, rows in all_slates.items():
            if key == base_key:
                continue
            moved, entered = [], []
            for row in rows:
                was = base_ranks_local.get(row["card_key"])
                if was is None:
                    entered.append(row)
                elif was != row["rank"]:
                    moved.append({**row, "rank_at_base": was, "delta": was - row["rank"]})
            left = [
                r
                for r in all_slates[base_key]
                if r["card_key"] not in {x["card_key"] for x in rows}
            ]
            out[key] = {
                "identical": not moved and not entered and not left,
                "positions_changed": len(moved),
                "entered_top_n": entered,
                "left_top_n": left,
                "biggest_movers": sorted(
                    moved, key=lambda m: abs(m["delta"]), reverse=True
                )[:10],
            }
        return out

    comparison = _compare(slates)

    served_comparison = None
    interleave_effect = None
    if stage == "served":
        served_comparison = _compare(served_slates)

        # ABSORBED / AMPLIFIED — the two numbers this mode exists to produce.
        #
        # A card is ABSORBED when the weight moved it in the pre-interleave list
        # and the display chain put it back: the delta was real and the page
        # never saw it. It is AMPLIFIED when the weight left it alone
        # pre-interleave and the page moved it anyway — a second-order effect of
        # some OTHER card crossing a quota boundary. Neither is bounded by
        # `positions_changed`, which is why that number alone cannot support
        # "this weight is worth N".
        #
        # Absence is a rank: a card outside the top-N is recorded as `None`, so
        # entering and leaving count as movement in exactly the same way a
        # re-rank does. Comparing `None` to `None` is "did not move", which is
        # correct — a card nobody sees at either weight did not change the page.
        interleave_effect = {}
        for key in served_slates:
            if key == base_key:
                continue
            ranked_base = {r["card_key"]: r["rank"] for r in slates[base_key]}
            ranked_w = {r["card_key"]: r["rank"] for r in slates[key]}
            served_base = {r["card_key"]: r["rank"] for r in served_slates[base_key]}
            served_w = {r["card_key"]: r["rank"] for r in served_slates[key]}

            universe = (
                set(ranked_base) | set(ranked_w) | set(served_base) | set(served_w)
            )
            absorbed, amplified, both, neither = [], [], [], []
            for ck in universe:
                moved_ranked = ranked_base.get(ck) != ranked_w.get(ck)
                moved_served = served_base.get(ck) != served_w.get(ck)
                rec = {
                    "card_key": ck,
                    "ranked_rank_base": ranked_base.get(ck),
                    "ranked_rank_weight": ranked_w.get(ck),
                    "served_rank_base": served_base.get(ck),
                    "served_rank_weight": served_w.get(ck),
                }
                if moved_ranked and not moved_served:
                    absorbed.append(rec)
                elif moved_served and not moved_ranked:
                    amplified.append(rec)
                elif moved_ranked and moved_served:
                    both.append(rec)
                else:
                    neither.append(rec)

            interleave_effect[key] = {
                "absorbed": len(absorbed),
                "amplified": len(amplified),
                "moved_in_both": len(both),
                "moved_in_neither": len(neither),
                "cards_considered": len(universe),
                "absorbed_cards": absorbed[:20],
                "amplified_cards": amplified[:20],
                # The registered expectation (ruling 050) for #1923: if this is
                # false on every weight, the display chain passes ranking deltas
                # through untouched, `ranked` was always sufficient, and this
                # mode should be DELETED rather than kept. Stated in the
                # response so the refutation is as visible as the confirmation.
                "registered_expectation_absorbed_gt_0": len(absorbed) > 0,
            }

    out = {
        "generated_at": now.isoformat(),
        "weights": parsed,
        "limit": limit,
        "stage": stage,
        "live_key_untouched": True,
        "cache_hits": cache_hits,
        "cache_populated": bool(cache_hits.get("cached")),
        "build_ms": build_ms,
        "comparison": comparison,
        "slates": slates,
    }
    if stage == "served":
        out["events_pool"] = events_pool_meta
        out["served_comparison"] = served_comparison
        out["served_slates"] = served_slates
        out["interleave_effect"] = interleave_effect
    return out
