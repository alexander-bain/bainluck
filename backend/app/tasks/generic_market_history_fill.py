"""#7351 — fetch ONE generic market's own venue history and cache it, off the request path.

PILLAR: TRUTH. SHIP: opening a generic Discover market shows its supported
historical observations on the phone and the web, including history our
periodic polls missed.

The arithmetic and the identity rules are pure and live in
`app/utils/generic_market_history.py`. This is the half that talks to Kalshi, to
Polymarket, to Postgres (READ ONLY) and to Redis.

REUSED, NOT REBUILT. Tier plans (`candle_calls`, `clob_calls`), the candlestick
windowing and batching (`fetch_candle_tier` → `candle_windows`, `ticker_batches`),
the candle price rule (`event_chart_backfill.normalize_candle`), the CLOB tier
fetch that tells an empty answer from a failure (`fetch_clob_tier`, gotcha #53),
finest-first layering (`layer_tiers`) and per-range compaction
(`compact_by_band`) are all `futures_chart_series[_fill]`'s own. What is new is
only what the concept fill cannot give a single question:

  * NO LEGS, NO BLEND. `find_venue_legs` / `blend_venues` are never called. One
    market, its own venue, its own contracts. Cross-source matching is not
    widened by a character.
  * EXACT CONTRACTS. Kalshi: the outcome row's own ticker. Polymarket: the
    condition id in the outcome row's own `external_id`, resolved to a CLOB
    token BY NAME through `polymarket_token_topup.token_for_outcome` (Q489: a
    mis-attributed token is an INVERTED line). `_polymarket_token_id`'s
    rank-indexed shortcut is deliberately not used here.
  * THE BOOK IS KEPT with each Kalshi point, so the readers can ask the
    canonical support predicates at read time.

WHAT IT NEVER DOES. It writes nothing to Postgres — not `futures_odds_snapshots`,
not an outcome, not a calibration column (the concept fill's own reasoning, and
gotcha #21). It sweeps no population: there is no beat entry and no "eligible
set"; the only caller is a reader that just served a thin chart, through a claim
that is per-market AND globally budgeted per hour.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Sequence
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

from app.utils.generic_market_history import (
    VENUE_SOURCES,
    VenuePoint,
    budget_key,
    build_payload,
    cache_key,
    claim_key,
    kalshi_contract,
    merge_last_good,
    payload_age_seconds,
    polymarket_contract,
    strip_polymarket_leg,
    validate_payload,
    wanted_gamma_outcome_name,
)

logger = logging.getLogger(__name__)

#: Outcomes that get a venue series. The generic chart draws ten lines by
#: default; past this each outcome is three more requests for a line at 0.1%.
#: Same number, same reason, as the concept fill's `TOP_N_OUTCOMES`.
TOP_N_OUTCOMES = 12

#: Markets one task invocation may fill. The on-demand caller always sends ONE;
#: the cap is what stops a hand-dispatched list becoming a sweep.
MAX_MARKETS_PER_TASK = 3

#: How long one market stays claimed after a reader asks for its fill. Longer
#: than the task's worst case (37 paced Polymarket requests ≈ 15 s, or a venue
#: timing out on each), so two fills of one market cannot overlap; short enough
#: that a fill that died is retried the same quarter-hour. It EXPIRES ON ITS OWN:
#: nothing has to succeed for a market to become claimable again.
CLAIM_TTL_SECONDS = 15 * 60

#: Ceiling on fills started in any one clock hour, site-wide. Both readers are
#: public GETs; without this a crawler walking market ids converts page views
#: into outbound venue traffic (`event_chart_backfill.ON_DEMAND_HOURLY_CAP`'s
#: lesson). 60 markets × ≤37 requests is far inside either venue's limits.
HOURLY_FILL_CAP = 60

#: How old the last ATTEMPT may be before a reader asks again. Under this the
#: captures cover the difference. Applies to an EMPTY or DEGRADED answer too —
#: that is the negative cache that stops a venue with nothing to say being asked
#: on every page view.
REFRESH_AFTER_SECONDS = 3 * 3600

CACHE_TTL_SECONDS = 36 * 3600
SETTLED_CACHE_TTL_SECONDS = 7 * 24 * 3600

_SETTLED_STATUSES = {"settled", "closed", "resolved"}


# ---------------------------------------------------------------------------
# Cache I/O
# ---------------------------------------------------------------------------


def _client(rc: Any = None):
    if rc is not None:
        return rc
    from app.tasks.redis_state import get_redis_client

    return get_redis_client()


def read_cached_history(market_id: int, rc: Any = None) -> dict | None:
    """The cached payload, or None. NEVER raises — a dead Redis costs the chart
    its venue history, not its existence."""
    try:
        raw = _client(rc).get(cache_key(market_id))
        if not raw:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else None
    except Exception as exc:  # noqa: BLE001 — a cache read never breaks a page
        logger.warning("generic market history: cache read failed for %s: %s",
                       market_id, str(exc)[:160])
        return None


def write_cached_history(market_id: int, payload: dict, *, settled: bool, rc: Any = None) -> bool:
    try:
        ttl = SETTLED_CACHE_TTL_SECONDS if settled else CACHE_TTL_SECONDS
        _client(rc).set(cache_key(market_id), json.dumps(payload, separators=(",", ":")), ex=ttl)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("generic market history: cache write failed for %s: %s",
                       market_id, str(exc)[:160])
        return False


# ---------------------------------------------------------------------------
# The claim — per market, and budgeted per hour
# ---------------------------------------------------------------------------


def market_is_fillable(market: Any, outcomes: Sequence[Any]) -> bool:
    """Does this market have a venue that publishes history for its own contracts?"""
    if (getattr(market, "source", None) or "") not in VENUE_SOURCES:
        return False
    return any((getattr(o, "external_id", None) or "").strip() for o in outcomes)


def answers_a_settled_market(payload: dict | None) -> bool:
    """Does this cached attempt settle the question for a settled market?

    🔴 THE SETTLED SHORT-CIRCUIT IS A STATEMENT ABOUT AN ANSWER, NOT ABOUT A DATE.
    The first presentation suppressed every further request the moment a settled
    market had ANY dated attempt on file, and the settled TTL is SEVEN DAYS. So a
    fill that came back empty because the venue was rate-limited, a fill that came
    back `degraded` because one window errored, and a fill that succeeded the day
    BEFORE the market settled — which cannot contain the hours that decided it —
    each froze the chart for a week with no way back. The failure is silent by
    construction: the reader sees a thin chart and a `warm` cache, and nothing
    ever asks again.

    Three things must all hold for an attempt to be that answer:

      * `status == "ok"` — not `empty`, not `degraded`;
      * it actually carries a series (an `ok` payload with no outcomes is the
        venue saying nothing, which is a result but not an answer);
      * it was taken while the market was ALREADY settled, which is the only way
        it can cover the run-in to settlement. The fill stamps that at write
        time, so this is read evidence rather than an inference from the clock.

    Anything else falls through to `REFRESH_AFTER_SECONDS` — the same bounded
    three-hour retry an open market gets. That is a retry ceiling, not a sweep:
    the per-market claim and the site-wide hourly cap are unchanged, and a
    successful post-settlement fill ends the retries on the next read.
    """
    if not isinstance(payload, dict):
        return False
    if payload.get("status") != "ok" or not payload.get("outcomes"):
        return False
    return payload.get("market_settled") is True


def plan_on_demand_fill(
    market: Any,
    outcomes: Sequence[Any],
    payload: dict | None,
    *,
    chart_is_thin: bool,
    now: datetime | None = None,
    rc: Any = None,
) -> dict:
    """Decide whether THIS read should start one fill, and win the claim if so.

    Returns `{"enqueue": bool, "reason": str}`. The DISPATCH is the caller's —
    `test_no_task_dispatches_another_task` keeps `.apply_async` out of
    `app/tasks/`, and the route that spends a claim is the route that hands it
    back (`release_claim`) when the broker refuses.

    🔴 A REDIS FAILURE REFUSES THE CLAIM (fail closed), exactly as
    `event_chart_backfill.claim_on_demand_fill` does and for its reason: with no
    Redis there is no dedupe, and the caller is a public GET.
    """
    stamp = now or datetime.now(timezone.utc)
    if not market_is_fillable(market, outcomes):
        return {"enqueue": False, "reason": "source_has_no_venue_history"}
    age = payload_age_seconds(payload, now=stamp)
    if age is None:
        if not chart_is_thin:
            # A chart our own polls already draw densely does not spend a venue
            # request to get denser. It is the thin chart this ship is for.
            return {"enqueue": False, "reason": "chart_not_thin"}
    else:
        settled = (getattr(market, "status", None) or "").lower() in _SETTLED_STATUSES
        if settled and answers_a_settled_market(payload):
            # A settled market's venue series cannot change, so ONE SUCCESSFUL
            # ANSWER TAKEN AFTER SETTLEMENT is the answer, and it is kept for the
            # 7-day settled TTL rather than re-fetched.
            return {"enqueue": False, "reason": "settled_and_already_answered"}
        if age <= REFRESH_AFTER_SECONDS:
            return {"enqueue": False, "reason": "answered_recently"}
        if not chart_is_thin and not (payload or {}).get("outcomes"):
            return {"enqueue": False, "reason": "chart_not_thin"}

    try:
        client = _client(rc)
        key = claim_key(market.id)
        if not client.set(key, stamp.isoformat(), nx=True, ex=CLAIM_TTL_SECONDS):
            return {"enqueue": False, "reason": "already_claimed"}
        bkey = budget_key(stamp.strftime("%Y%m%d%H"))
        spent = client.incr(bkey)
        # Set every time: an INCR whose EXPIRE was lost to a crash would
        # otherwise cap that hour's key forever.
        client.expire(bkey, 7200)
        if spent > HOURLY_FILL_CAP:
            client.delete(key)
            return {"enqueue": False, "reason": "hourly_cap"}
        return {"enqueue": True, "reason": "claimed"}
    except Exception:
        logger.warning("generic market history: claim refused for market %s — Redis "
                       "unavailable, so there is no dedupe to enqueue behind",
                       getattr(market, "id", None), exc_info=True)
        return {"enqueue": False, "reason": "no_redis"}


def release_claim(market_id: int, rc: Any = None) -> None:
    """Hand a won claim back, for a caller whose dispatch then failed."""
    try:
        _client(rc).delete(claim_key(market_id))
    except Exception:
        logger.warning("generic market history: could not release claim for %s",
                       market_id, exc_info=True)


# ---------------------------------------------------------------------------
# Which outcomes, which contracts
# ---------------------------------------------------------------------------


def fillable_outcomes(market: Any, limit: int = TOP_N_OUTCOMES) -> list:
    """The outcomes whose lines a generic chart can draw, leader first, BOUNDED.

    Past `drop_duplicate_legs` for the readers' own reason (#6641): a `_yes`/`_no`
    pair that duplicates a bare rung on the same market is not a line, and a
    history fetched for it would be the resurrection the readers refuse.
    """
    from app.utils.duplicate_condition_outcomes import drop_duplicate_legs
    from app.utils.outcome_display import is_field_outcome

    deduped = drop_duplicate_legs(list(market.outcomes or []), lambda o: o.external_id)
    real = [
        o for o in deduped
        if (o.external_id or "").strip() and o.name and not is_field_outcome(o.name)
    ]
    real.sort(key=lambda o: float(o.current_probability or 0), reverse=True)
    return real[: max(1, int(limit))]


async def resolve_polymarket_tokens(
    service: Any, market: Any, outcomes: Sequence[Any], *, stats: dict
) -> dict[int, dict]:
    """`{outcome_id: contract}` for the outcomes whose EXACT token can be proved.

    Order: the ingest-stamped per-outcome map (keyed by `FuturesOutcome.id`, so
    it cannot name another row), then ONE Gamma event read for the whole market
    and an exact `conditionId` match per outcome, token chosen BY NAME. Anything
    that cannot be proved is counted in `stats` and gets no series — a missing
    line is honest, an inverted one is not.
    """
    from app.tasks.polymarket_token_topup import (
        OUTCOME_TOKEN_METADATA_KEY,
        token_for_outcome,
    )

    metadata = market.market_metadata or {}
    stamped = metadata.get(OUTCOME_TOKEN_METADATA_KEY) or {}
    contracts: dict[int, dict] = {}
    unresolved: list = []
    for outcome in outcomes:
        token = stamped.get(str(outcome.id)) if isinstance(stamped, dict) else None
        contract = (
            polymarket_contract(outcome, token_id=str(token), resolved_via="outcome_token_metadata")
            if token else None
        )
        if contract:
            contracts[outcome.id] = contract
        else:
            unresolved.append(outcome)
    if not unresolved:
        return contracts

    event_external = (
        metadata.get("polymarket_event_id")
        or (market.group_id or "").replace("polymarket:", "")
        or market.external_id
    )
    if not event_external:
        stats["no_event_id"] = stats.get("no_event_id", 0) + len(unresolved)
        return contracts
    try:
        event_data = await service.get_event_by_id(str(event_external))
        stats["gamma_requests"] = stats.get("gamma_requests", 0) + 1
    except Exception as exc:  # noqa: BLE001 — identity unknown is not identity guessed
        stats["fetch_errors"] = stats.get("fetch_errors", 0) + 1
        stats.setdefault("errors", []).append(
            f"gamma/event: {type(exc).__name__}: {str(exc)[:100]}"
        )
        return contracts
    sub_markets = (event_data or {}).get("markets") or []
    by_condition = {
        sub.get("conditionId"): sub for sub in sub_markets if sub.get("conditionId")
    }
    for outcome in unresolved:
        condition_id = strip_polymarket_leg((outcome.external_id or "").strip())
        sub = by_condition.get(condition_id)
        if not condition_id.startswith("0x") or sub is None:
            stats["no_exact_condition"] = stats.get("no_exact_condition", 0) + 1
            continue
        names = _json_list(sub.get("outcomes"))
        tokens = _json_list(sub.get("clobTokenIds"))
        if not tokens or len(names) != len(tokens):
            stats["no_aligned_tokens"] = stats.get("no_aligned_tokens", 0) + 1
            continue
        wanted = wanted_gamma_outcome_name(outcome)
        if wanted.lower() in ("yes", "no") and wanted.lower() not in {n.strip().lower() for n in names}:
            # The row says it is the No (or Yes) leg and Gamma names no such
            # side. `token_for_outcome` would fall back to the Yes token — for a
            # `_no` row that is the inversion. Refuse.
            stats["leg_not_named_by_venue"] = stats.get("leg_not_named_by_venue", 0) + 1
            continue
        token = token_for_outcome(
            SimpleNamespace(clob_token_ids=tokens, outcomes=names), wanted
        )
        contract = (
            polymarket_contract(outcome, token_id=str(token), resolved_via="gamma_condition_by_name")
            if token else None
        )
        if contract:
            contracts[outcome.id] = contract
        else:
            stats["no_token_by_name"] = stats.get("no_token_by_name", 0) + 1
    return contracts


def _json_list(raw: Any) -> list[str]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return []
    return [str(x) for x in raw] if isinstance(raw, list) else []


# ---------------------------------------------------------------------------
# The build
# ---------------------------------------------------------------------------


def _lifetime_hours(market: Any, now: datetime) -> float:
    from app.tasks.futures_chart_series_fill import DEFAULT_LIFETIME_HOURS

    stamp = getattr(market, "created_at", None)
    if stamp is None:
        return DEFAULT_LIFETIME_HOURS
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return max(1.0, (now - stamp).total_seconds() / 3600.0)


class _CandleBook:
    """Collects, per (ticker, instant), the book of the FINEST priced candle.

    `fetch_candle_tier` reduces each candle to one price for the layering, which
    is what the layering needs and not enough for a reader that must ask the
    support predicates of the point's own bid/ask/last. This rides along as the
    tier fetch's `on_candle` sink. Tiers arrive finest first, so `setdefault`
    keeps the same candle `layer_tiers` will keep.
    """

    def __init__(self) -> None:
        self.books: dict[tuple[str, int], tuple[float, float | None, float | None, float | None, str]] = {}
        self.seen = 0
        self.unpriced: list[dict] = []

    def __call__(self, ticker: str, candle: dict, period_interval: int) -> None:
        from app.tasks.event_chart_backfill import _dollars, normalize_candle

        self.seen += 1
        end_ts = candle.get("end_period_ts")
        price = normalize_candle(candle)
        tier = f"kalshi_candle_{int(period_interval)}m"
        if price is None or end_ts is None:
            if len(self.unpriced) < 50:
                self.unpriced.append({"ticker": ticker, "end_period_ts": end_ts, "tier": tier,
                                      "reason": "no_supported_price_in_candle"})
            return
        last = _dollars(candle.get("price"), "close_dollars", "previous_dollars")
        self.books.setdefault(
            (ticker, int(end_ts)),
            (
                price,
                _dollars(candle.get("yes_bid"), "close_dollars"),
                _dollars(candle.get("yes_ask"), "close_dollars"),
                last,
                tier,
            ),
        )

    def point(self, ticker: str, ts: datetime, probability: float) -> VenuePoint:
        book = self.books.get((ticker, int(ts.timestamp())))
        if book is None or abs(book[0] - probability) > 1e-9:
            # The layered price did not come from the candle we hold a book for.
            # Serve the price without a book rather than pair it with a wrong one.
            return VenuePoint(ts, probability, tier="kalshi_candle")
        return VenuePoint(ts, probability, book[1], book[2], book[3], book[4])


async def build_generic_history(
    session: Any,
    market: Any,
    *,
    kalshi_service: Any = None,
    polymarket_service: Any = None,
    last_good: dict | None = None,
    now: datetime | None = None,
) -> dict:
    """The identity-bound venue series for ONE market's own top outcomes.

    Never raises for one bad outcome or one bad tier: a lost window is counted
    (`window_errors` / `fetch_errors`), the payload is marked `degraded`, and the
    last-good points of the same contract are carried (`merge_last_good`).
    `session` is unused today and accepted so the signature matches the concept
    fill's and a future contract lookup does not change every caller.
    """
    from app.tasks.futures_chart_series_fill import (
        REQUEST_PAUSE_SECONDS,
        fetch_clob_tier,
        kalshi_field_series,
    )
    from app.utils.futures_chart_series import clob_calls, compact_by_band, layer_tiers

    now = now or datetime.now(timezone.utc)
    stats: dict = {"source": market.source, "outcomes_built": 0, "outcomes_empty": 0}
    owned: list[Any] = []
    entries: dict[int, dict] = {}
    outcomes = fillable_outcomes(market)
    stats["outcomes_considered"] = len(outcomes)
    lifetime = _lifetime_hours(market, now)

    try:
        if market.source == "kalshi" and outcomes:
            if kalshi_service is None:
                from app.services.kalshi_api import KalshiAPIService

                kalshi_service = KalshiAPIService()
                owned.append(kalshi_service)
            contracts = {o.id: c for o in outcomes if (c := kalshi_contract(o))}
            book = _CandleBook()
            by_ticker = await kalshi_field_series(
                kalshi_service, [o for o in outcomes if o.id in contracts],
                listed_at=getattr(market, "created_at", None),
                now=now, lifetime_hours=lifetime, stats=stats, on_candle=book,
            )
            stats["candles_seen"] = book.seen
            if book.unpriced:
                stats["candles_unpriced"] = book.unpriced
            for outcome in outcomes:
                contract = contracts.get(outcome.id)
                if not contract:
                    continue
                layered = by_ticker.get(contract["ticker"], [])
                entries[outcome.id] = {
                    "contract": contract,
                    "points": [book.point(contract["ticker"], ts, p) for ts, p in layered],
                }
        elif market.source == "polymarket" and outcomes:
            if polymarket_service is None:
                from app.services.polymarket_api import PolymarketAPIService

                polymarket_service = PolymarketAPIService()
                owned.append(polymarket_service)
            contracts = await resolve_polymarket_tokens(
                polymarket_service, market, outcomes, stats=stats
            )
            for outcome in outcomes:
                contract = contracts.get(outcome.id)
                if not contract:
                    continue
                tiers = []
                labels: dict[datetime, str] = {}
                try:
                    for call in clob_calls(lifetime):
                        tier = await fetch_clob_tier(
                            polymarket_service, contract["token_id"], call, stats=stats
                        )
                        for ts, _p in tier:
                            labels.setdefault(ts, f"polymarket_clob_{call.interval}_f{call.fidelity}")
                        tiers.append(tier)
                        await asyncio.sleep(REQUEST_PAUSE_SECONDS)
                except Exception as exc:  # noqa: BLE001 — one outcome, not the market
                    stats["fetch_errors"] = stats.get("fetch_errors", 0) + 1
                    stats.setdefault("errors", []).append(
                        f"polymarket/{outcome.id}: {type(exc).__name__}: {str(exc)[:100]}"
                    )
                entries[outcome.id] = {
                    "contract": contract,
                    "points": [
                        VenuePoint(ts, p, tier=labels.get(ts, "polymarket_clob"))
                        for ts, p in layer_tiers(tiers)
                    ],
                }
    except Exception as exc:  # noqa: BLE001 — one venue, never the last-good cache
        stats["fetch_errors"] = stats.get("fetch_errors", 0) + 1
        stats.setdefault("errors", []).append(f"{market.source}: {type(exc).__name__}: {str(exc)[:120]}")
    finally:
        for service in owned:
            try:
                await service.close()
            except Exception:  # noqa: BLE001, S110 — closing never masks the run
                pass

    degraded = bool(stats.get("fetch_errors") or stats.get("window_errors"))

    # LAST-GOOD. Only series that still pass every identity binding against the
    # CURRENT rows are carried, and only onto the SAME contract.
    carried, _refusals = validate_payload(last_good, market, outcomes) if last_good else ({}, [])
    last_good_contracts = {
        int(k): (v or {}).get("contract")
        for k, v in ((last_good or {}).get("outcomes") or {}).items()
        if str(k).isdigit()
    }
    for outcome in outcomes:
        previous = carried.get(outcome.id)
        if not previous:
            continue
        entry = entries.get(outcome.id)
        if entry is None:
            entries[outcome.id] = {"contract": last_good_contracts[outcome.id], "points": list(previous)}
            stats["carried_whole"] = stats.get("carried_whole", 0) + 1
            continue
        if entry["contract"] != last_good_contracts.get(outcome.id):
            continue
        before = len(entry["points"])
        entry["points"] = merge_last_good(entry["points"], previous)
        if len(entry["points"]) > before:
            stats["carried_points"] = stats.get("carried_points", 0) + (len(entry["points"]) - before)

    for entry in entries.values():
        points: list[VenuePoint] = entry["points"]
        by_ts = {p.observed_at: p for p in points}
        kept = compact_by_band([(p.observed_at, p.probability) for p in points], now)
        entry["points"] = [by_ts[ts] for ts, _p in kept]
        if entry["points"]:
            stats["outcomes_built"] += 1
        else:
            stats["outcomes_empty"] += 1

    return build_payload(market, entries, now=now, stats=stats, degraded=degraded)


async def fill_generic_market_history(
    session: Any, market_id: int, *, dry_run: bool = False,
    kalshi_service: Any = None, polymarket_service: Any = None,
    now: datetime | None = None, rc: Any = None,
) -> dict:
    """Build and cache one market's series. The unit the task calls."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models.models import FuturesMarket

    market = (
        await session.execute(
            select(FuturesMarket)
            .options(selectinload(FuturesMarket.outcomes))
            .where(FuturesMarket.id == market_id)
        )
    ).scalar_one_or_none()
    if market is None:
        return {"market_id": market_id, "status": "not_found"}
    if (market.source or "") not in VENUE_SOURCES:
        return {"market_id": market_id, "status": "source_has_no_venue_history"}

    last_good = read_cached_history(market_id, rc)
    payload = await build_generic_history(
        session, market,
        kalshi_service=kalshi_service, polymarket_service=polymarket_service,
        last_good=last_good, now=now,
    )
    settled = (market.status or "").lower() in _SETTLED_STATUSES
    # Stamped into the payload, not just used to pick the TTL: `plan_on_demand_fill`
    # has to tell a fill taken AFTER settlement (which covers the run-in, and is
    # the answer) from one taken before it (which cannot). Recording the state the
    # fill actually ran under is evidence; comparing timestamps to a settlement
    # time we do not carry would be a guess.
    payload["market_settled"] = settled
    written = False
    if not dry_run:
        written = write_cached_history(market_id, payload, settled=settled, rc=rc)
        if written:
            # THE CLAIM MEANS "A FILL IS IN FLIGHT", and this one has landed. From
            # here the payload's own `attempted_at` decides when a reader may ask
            # again (`REFRESH_AFTER_SECONDS`) — for an empty or degraded answer
            # too. A fill that dies BEFORE this line leaves the claim to its TTL,
            # which is the bounded retry: one attempt per `CLAIM_TTL_SECONDS`.
            release_claim(market_id, rc)
    return {
        "market_id": market_id,
        "status": payload["status"],
        "outcomes_built": payload["stats"]["outcomes_built"],
        "points": {k: len(v["points"]) for k, v in payload["outcomes"].items()},
        "cached": written,
        "stats": {k: v for k, v in payload["stats"].items() if k != "candles_unpriced"},
    }


async def run_generic_market_history_fill(
    market_ids: Sequence[int] | None = None, *, dry_run: bool = False,
) -> dict:
    """Fill the NAMED markets. There is no unnamed mode: no ids, no work."""
    from app.tasks.base import get_task_session

    ids = [int(m) for m in (market_ids or [])][:MAX_MARKETS_PER_TASK]
    results = []
    if ids:
        async with get_task_session() as session:
            for market_id in ids:
                try:
                    results.append(
                        await fill_generic_market_history(session, market_id, dry_run=dry_run)
                    )
                except Exception as exc:  # noqa: BLE001 — one market, not the call
                    logger.warning("generic market history: fill failed for %s: %s",
                                   market_id, str(exc)[:200])
                    results.append({
                        "market_id": market_id, "status": "error",
                        "error": f"{type(exc).__name__}: {str(exc)[:160]}",
                    })
    return {
        "markets_attempted": len(results),
        "markets_with_history": sum(1 for r in results if r.get("outcomes_built")),
        "truncated_to": MAX_MARKETS_PER_TASK if len(market_ids or []) > MAX_MARKETS_PER_TASK else None,
        "dry_run": dry_run,
        "results": results,
    }
