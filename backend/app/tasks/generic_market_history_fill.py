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

WHAT IT NEVER DOES. It writes no MARKET DATA to Postgres — not
`futures_odds_snapshots`, not an outcome, not a calibration column (the concept
fill's own reasoning, and gotcha #21). It sweeps no population: there is no beat
entry and no "eligible set"; the only caller is a reader that just served a thin
chart, through a claim that is per-market AND globally budgeted per hour.

THE ONE POSTGRES WRITE (#7736, added after this file's "writes nothing" line was
written — it was true until then). `_stamp_bank_marker` merges a single key into
`futures_markets.market_metadata` recording that this market HAS venue history.
It is bookkeeping about the CACHE, never market data, and it is written at most
once per market. It exists because the bank is Redis-only under `allkeys-lru`:
when eviction takes the bank it also takes the only evidence the bank existed,
and `plan_on_demand_fill` then cannot tell a market whose history was evicted
from one that never had any — so the recovery is silently abandoned for ever.
It pins `updated_at` to itself so the row's data-freshness clock does NOT move
(CERT-949, and #7351's D1 byte-equality contract): see `_stamp_bank_marker`.
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
    BANK_MARKER_KEY,
    CACHE_VERSION,
    VENUE_SOURCES,
    VenuePoint,
    budget_key,
    build_bank_marker,
    build_payload,
    cache_key,
    claim_key,
    durable_identity,
    kalshi_contract,
    market_had_bank,
    merge_last_good,
    payload_age_seconds,
    payload_built_at,
    payload_point_count,
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

#: How many post-settlement attempts may come back with nothing of their own
#: before the carried series is accepted as all there is. THREE, one per
#: `REFRESH_AFTER_SECONDS`, so a venue that publishes its terminal candle late
#: has ~9 hours to do it while a venue that has purged the market (gotcha #35 —
#: Kalshi market data goes at ≥74 days) is asked three times rather than every
#: three hours for the seven-day settled TTL. Without a ceiling, the repair for
#: "one bad attempt froze the chart for a week" is "every settled chart asks
#: forever", which is the same bug spent on the venue instead of the reader.
MAX_SETTLED_EMPTY_ATTEMPTS = 3

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


def declared_ttl_seconds(*, settled: bool) -> int:
    """The lifetime this bank is WRITTEN with — the one number both tiers obey."""
    return SETTLED_CACHE_TTL_SECONDS if settled else CACHE_TTL_SECONDS


def write_cached_history(
    market_id: int, payload: dict, *, settled: bool, rc: Any = None,
    ttl_s: int | None = None,
) -> bool:
    """Cache the bank. ``ttl_s`` overrides the declared TTL with what is LEFT of it.

    The override exists for one caller — the durable tier's rehydration (#7807).
    A bank recovered from Postgres is not a new bank and must not be given a new
    36 hours: re-caching it at full TTL would let a payload outlive the lifetime
    it was written with, every time it were evicted and restored. So the reader
    passes the remainder and the bank expires when it always would have.
    """
    try:
        ttl = declared_ttl_seconds(settled=settled) if ttl_s is None else int(ttl_s)
        if ttl <= 0:
            return False
        _client(rc).set(cache_key(market_id), json.dumps(payload, separators=(",", ":")), ex=ttl)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("generic market history: cache write failed for %s: %s",
                       market_id, str(exc)[:160])
        return False


# ---------------------------------------------------------------------------
# The durable tier (#7807) — the same bank, where `allkeys-lru` cannot reach it
# ---------------------------------------------------------------------------
#
# THE BANK'S DECLARED TTL WAS ASPIRATIONAL AND #7563 MEASURED IT. Redis here is
# 100 MB under `allkeys-lru`; a ~35 KB value that is read rarely is the ideal
# eviction victim, so the `ex=36h` above bought a real lifetime under four hours
# on 3 of 3 markets. Eviction ignores TTL by design. The series has no other
# home — `FuturesOddsSnapshot` holds OUR polls and nothing else — so an evicted
# bank is not stale data to refresh, it is lost data, and the reader gets the
# thin chart back with the dashed gap #7351 had just closed.
#
# This tier is the same payload in `durable_state_snapshots`, the existing
# cross-process store built for exactly this (#1512) — no migration and no new
# table, which is the ruling `utils/matcher_pass_runs.py` already recorded for
# this class. Redis stays the fast tier and is read first; this is only paid
# when it has already missed.
#
# 🔴 IT DOES NOT EXTEND THE BANK'S LIFE, AND THAT IS A DELIBERATE LIMIT. The read
# applies the SAME declared TTL, so this ship makes 36 h real rather than making
# it longer. A durable row past its declared life is not served — the market is
# cold, the planner re-asks the venue, and the reader is told the truth about
# what we hold.

#: Recorded on the row so an operator reading `durable_state_snapshots` can see
#: which producer wrote it without decoding the payload.
DURABLE_SOURCE = "generic_market_history_fill"


async def publish_durable_history(
    session: Any, market_id: int, payload: dict, *, settled: bool = False
) -> dict:
    """Stage the bank in the caller's transaction. NEVER raises, NEVER commits.

    Staged rather than committed so it lands in the same transaction as #7736's
    marker and the fill's own work — the bank and the receipt that it exists are
    one fact, and CERT-851's rule is that they land together or not at all.

    🔴 AN EMPTY ANSWER IS NEVER PERSISTED. `payload_point_count` is the gate, the
    same one the marker uses. A durable `empty` would be a negative cache with no
    expiry: one venue outage, and the market is frozen as "nothing here" for
    everyone, for ever. The Redis negative cache is bounded by
    `REFRESH_AFTER_SECONDS` precisely so it can be wrong for three hours instead.
    """
    from app.services.durable_snapshots import publish_snapshot_in_txn
    from app.utils.durable_state import DurableEnvelope

    points = payload_point_count(payload)
    if points <= 0:
        return {"status": "skipped", "reason": "no_points"}
    stamp = payload_built_at(payload)
    if stamp is None:
        # The generation IS the build stamp; without one there is no ordering and
        # a later write could lose to an earlier one. Refuse rather than invent.
        return {"status": "skipped", "reason": "no_built_at"}
    try:
        return await publish_snapshot_in_txn(
            session,
            DurableEnvelope.build(
                identity=durable_identity(market_id),
                schema_version=CACHE_VERSION,
                payload=payload,
                generated_at=stamp,
                source=DURABLE_SOURCE,
            ),
        )  # ← trailing comment is load-bearing; see the note on the read below
    except Exception as exc:  # noqa: BLE001 — a durable write never fails a fill
        logger.warning("generic market history: durable publish failed for %s: %s",
                       market_id, str(exc)[:160])
        return {"status": "error", "error": str(exc)[:200]}


async def read_durable_history(
    db: Any, market_id: int, *, now: datetime | None = None
) -> dict | None:
    """The durable bank if it is within its declared life, else None. NEVER raises.

    🔴 THE READ RUNS IN A SAVEPOINT THAT IS ROLLED BACK, AND THE ROLLBACK IS THE
    POINT. `read_snapshot` bounds itself with `SET LOCAL statement_timeout =
    2000`, and `SET LOCAL` lasts until the end of the TRANSACTION — not until the
    end of the statement. The house pattern calls it straight on the request
    session (`routes/calibration.py`), which is safe there and is not safe here:
    `get_probability_timeline` runs its 30/90-day auto-extend query AFTER this
    read, on this same session, and a 2 s ceiling is exactly what that query can
    breach. Reading on a standalone session is not the alternative —
    `get_task_session` builds its own engine, i.e. a second pool per web process,
    which is #1197's hazard.
    A savepoint's GUC stack unwinds on ROLLBACK and NOT on RELEASE (measured both
    ways on Postgres; `async with db.begin_nested()` RELEASEs on a clean exit,
    which leaks the 2 s). Hence the explicit rollback in `finally`, and
    `test_durable_read_restores_the_outer_statement_timeout_7807` holds it there.
    """
    from app.services.durable_snapshots import read_snapshot

    stamp = now or datetime.now(timezone.utc)
    nested = None
    read = None
    try:
        nested = await db.begin_nested()
        read = await read_snapshot(
            db,
            durable_identity(market_id),
            expected_version=CACHE_VERSION,
            # The generous bound of the two, because which one applies is a fact
            # carried BY the payload and cannot be known before reading it.
            max_age_s=SETTLED_CACHE_TTL_SECONDS,
            now=stamp,
        )  # ← THE TRAILING COMMENT IS LOAD-BEARING, and not for a reader.
        # `scan_mutation_residue` Pass B sweeps every CHANGED file for the
        # REPLACEMENT half of every registered mutant, and
        # `typeahead_outcome_arm_mutations:M2-NO-LIMIT` replaces its needle with
        # a bare `        )` followed by exactly `    except Exception as exc:
        # # noqa: BLE001`. A closing paren at this indent directly above such a
        # handler therefore reds CI as residue in a file that harness has never
        # touched. Deleting either comment restores the collision; the scan is
        # right to be blunt, and the cost is one clause. Same fix as
        # `repair_polymarket_single_leg_label.py` and four siblings.
    except Exception as exc:  # noqa: BLE001 — a durable read never breaks a chart
        logger.warning("generic market history: durable read failed for %s: %s",
                       market_id, str(exc)[:160])
        return None
    finally:
        if nested is not None:
            try:
                await nested.rollback()
            except Exception:  # noqa: BLE001 — the read is done; nothing to undo
                pass

    if read is None or not read.ok or read.envelope is None:
        return None
    payload = read.envelope.payload
    if not isinstance(payload, dict):
        return None
    # The declared TTL, applied for real. `market_settled` is the state the fill
    # RAN under, which is the state that chose the Redis TTL — so this reproduces
    # the lifetime the bank was actually written with, rather than re-deciding it
    # from a status that may have changed since.
    ttl = declared_ttl_seconds(settled=bool(payload.get("market_settled")))
    age = (stamp - read.envelope.generated_at).total_seconds()
    if age > ttl:
        return None
    return payload


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

    🔴 AN `ok` PAYLOAD IS NOT AN ANSWERED ATTEMPT (CERT-3152). Three of those
    four words were tested and the fourth was assumed: a market with a HEALTHY
    pre-settlement series that settles and is then asked once, unsuccessfully,
    carries its old points forward (that is what last-good is for and it is
    right), and `build_payload` calls a payload with points `ok`. Stamped
    `market_settled` by the fill that ran, it read as the week's answer — while
    the hours that decided the question, the only hours a settled market's chart
    is missing, were exactly the ones never fetched. The reader sees a full-
    looking chart that stops before the end, a warm cache, and no retry for a
    week: the same silent freeze one layer in.

    So the question is asked of THIS ATTEMPT — `stats.fetched_points`, counted
    before the last-good merge — and not of the payload's display series.

    ⏳ AND THE RETRY IS BOUNDED, because a venue can be empty FOREVER: Kalshi
    purges a settled market's candles (gotcha #35), so "ask again until it
    answers" is an unbounded three-hourly request for every settled market for
    its whole TTL. After `MAX_SETTLED_EMPTY_ATTEMPTS` post-settlement attempts
    that fetched nothing, the carried series is accepted as all there is and the
    chart holds it for the rest of the settled TTL. A payload that predates this
    counter has no attempt to describe, so it is not an answer — it costs one
    bounded retry, which rewrites it with the counter.

    🔴 ONLY A CLEAN EMPTY COUNTS AGAINST THAT CEILING (CERT-3156). "The venue
    fetched me nothing" and "I could not ask the venue" are different facts, and
    the first cut of the ceiling spent both: three 429s or three 500s inside nine
    hours exhausted it, and the payload — `degraded`, no points, possibly not one
    byte of history ever fetched — then read as the week's answer. That is the
    freeze this ship exists to remove, rebuilt out of the repair for it. A
    failed attempt therefore neither ADVANCES the counter (see
    :func:`next_settled_empty_attempts`) nor SATISFIES it here: an errored
    attempt is always retryable at `REFRESH_AFTER_SECONDS`, however many have
    gone before, because a venue that is erroring has not told us anything about
    what it holds.
    """
    if not isinstance(payload, dict):
        return False
    if payload.get("market_settled") is not True:
        return False
    stats = payload.get("stats")
    stats = stats if isinstance(stats, dict) else {}
    if attempt_reached_the_venue(payload) and (
        settled_empty_attempts(payload) >= MAX_SETTLED_EMPTY_ATTEMPTS
    ):
        # The venue has been asked its ceiling of times since this market
        # settled, answered every time, and published nothing. Stop asking; keep
        # the chart. `attempt_reached_the_venue` is what keeps a run of failures
        # from spending a ceiling that is about SILENCE.
        return True
    if payload.get("status") != "ok" or not payload.get("outcomes"):
        return False
    return int(stats.get("fetched_points") or 0) > 0


def attempt_reached_the_venue(payload: dict | None) -> bool:
    """Did the fill behind this payload get an ANSWER, as opposed to an error?

    Keyed on the error counters `build_generic_history` writes — `fetch_errors`
    (the venue call or the whole source raised) and `window_errors` (one window
    of a multi-window fetch failed) — because those are the CAUSE; `status ==
    "degraded"` is derived from exactly them and is checked too, so a payload
    that arrives degraded without counters (an older schema, a hand-written
    test) is still read as a failure rather than as silence.

    An attempt that reached the venue and was handed nothing is a RESULT: it is
    the only thing the settled-empty ceiling is allowed to count.
    """
    if not isinstance(payload, dict):
        return False
    if payload.get("status") == "degraded":
        return False
    stats = payload.get("stats")
    stats = stats if isinstance(stats, dict) else {}
    return not (stats.get("fetch_errors") or stats.get("window_errors"))


def settled_empty_attempts(payload: dict | None) -> int:
    """How many post-settlement attempts in a row have fetched nothing."""
    if not isinstance(payload, dict):
        return 0
    try:
        return max(0, int(payload.get("settled_empty_attempts") or 0))
    except (TypeError, ValueError):
        return 0


def next_settled_empty_attempts(last_good: dict | None, payload: dict, *,
                                settled: bool) -> int:
    """The counter this fill's payload carries forward.

    Counts only attempts made WHILE SETTLED that REACHED THE VENUE and were
    handed nothing. Three rules, and each one is a different fact:

      * an OPEN market's empty fill is an ordinary retry and is not on this
        clock at all;
      * one fetched point RESETS it — a venue that answered once is not the
        silent venue the ceiling exists for;
      * a FAILED attempt (429, 500, one window erroring) HOLDS it where it is —
        neither advancing nor resetting. Advancing would let a bad afternoon at
        the venue spend a ceiling that is about silence (CERT-3156); resetting
        would let a flaky venue erase clean empties we really did observe.
    """
    if not settled:
        return 0
    stats = payload.get("stats")
    fetched = int((stats if isinstance(stats, dict) else {}).get("fetched_points") or 0)
    if fetched > 0:
        return 0
    if not attempt_reached_the_venue(payload):
        return settled_empty_attempts(last_good)
    return settled_empty_attempts(last_good) + 1


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
            #
            # 🔴 UNLESS THIS MARKET IS KNOWN TO HAVE HELD A BANK (#7736). `age is
            # None` means THE KEY IS NOT THERE, and that is two states, not one:
            # a market that never had venue history, and one whose bank Redis
            # evicted. The first is the case the comment above is about. For the
            # second, refusing means the history #7351 recovered is gone for
            # good — nothing else re-fetches it, because the serve path never
            # calls a provider and Postgres holds only our own poll snapshots.
            # The durable marker is what tells the two apart once the evidence
            # in Redis has been evicted along with the bank.
            if not market_had_bank(market):
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

    # 🔴 WHAT *THIS* ATTEMPT GOT, COUNTED BEFORE THE LAST-GOOD MERGE — the only
    # line in this function from which that is still visible. Past it, a series
    # carried out of the cache and a series fetched a second ago are the same
    # list of points, and `status` says `ok` for either. A settled market's
    # payload is kept for SEVEN DAYS on the strength of being an answer, so
    # "the payload has points" is not the question `answers_a_settled_market`
    # can ask; "this attempt was answered" is (CERT-3152).
    stats["fetched_points"] = sum(len(e["points"]) for e in entries.values())
    stats["fetched_outcomes"] = sum(1 for e in entries.values() if e["points"])

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


async def _stamp_bank_marker(session: Any, market_id: int, marker: dict) -> None:
    """Record durably that this market HAS venue history (#7736).

    Merged into `market_metadata` with a Core ``||`` JSONB merge (gotcha #4 — no
    ORM attribute assignment for JSONB, and `_write_seed_marker`'s idiom), so a
    sibling writing a different key of the same column is not clobbered by a
    read-modify-write. Does NOT commit: the caller owns the transaction, and
    `get_task_session` commits it on a clean exit.

    🔴 `updated_at` IS PINNED TO ITSELF, AND THAT IS THE POINT (CERT-949). The
    column is `onupdate=func.now()`, so SQLAlchemy appends `updated_at=now()` to
    any `update()` that omits it — and 58 call sites read it as "this market's
    DATA changed": `max(FuturesMarket.updated_at)` is the cache version for the
    concept / related-futures / game-markets payloads, `taxonomy` and
    `data_quality` select on `updated_at >= cutoff`, and `admin_judgments` calls
    a row stale at `updated_at < now - 14d`. This write is bookkeeping about the
    CACHE and touches no market data, so letting it bump that clock would tell
    all of them a lie — the exact lie CERT-949 is the record of, where the
    six-hourly hook enricher's `market_metadata` write made stale markets read as
    hours fresh. Self-assigning the column emits `updated_at=futures_markets.
    updated_at` and suppresses the `onupdate`; the served detail payload is then
    byte-identical across a fill, which is #7351's D1 contract.
    """
    from sqlalchemy import cast, func, literal, update
    from sqlalchemy.dialects.postgresql import JSONB

    from app.models.models import FuturesMarket

    await session.execute(
        update(FuturesMarket)
        .where(FuturesMarket.id == int(market_id))
        .values(
            market_metadata=func.coalesce(
                FuturesMarket.market_metadata, cast(literal("{}"), JSONB)
            ).op("||")(cast(literal(json.dumps({BANK_MARKER_KEY: marker})), JSONB)),
            updated_at=FuturesMarket.updated_at,
        )
    )


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
    # Carried forward across fills, so the ceiling counts ATTEMPTS and not reads.
    # It rides the payload rather than a Redis key of its own for the reason the
    # rest of this state does: one key, one TTL, and a counter that cannot
    # outlive the series it describes.
    payload["settled_empty_attempts"] = next_settled_empty_attempts(
        last_good, payload, settled=settled
    )
    written = False
    marker_written = False
    durable_status = "not_attempted"
    if not dry_run:
        # THE DURABLE HALF OF THE BANK (#7736). The series itself goes to Redis
        # below, where `allkeys-lru` may evict it at any time; this stamp is what
        # survives that and lets `plan_on_demand_fill` tell an EVICTED bank from
        # a market that never had one. Written ONCE — it records that venue
        # history exists for this row, which does not change — so every later
        # fill of the same market costs no write at all. It is deliberately NOT
        # conditional on the Redis write succeeding: the fact it records is about
        # the market, not about the cache.
        marker = build_bank_marker(payload, now=now or datetime.now(timezone.utc))
        if marker is not None and not market_had_bank(market):
            await _stamp_bank_marker(session, market_id, marker)
            marker_written = True
        # THE SERIES ITSELF, WHERE EVICTION CANNOT REACH IT (#7807). Staged in
        # this same transaction as the marker above, so the bank and the record
        # that it exists can never disagree. Unlike the marker this is written on
        # EVERY fill that carries points — it is the data, not a one-off fact
        # about the market, and a later build must replace an earlier one.
        durable = await publish_durable_history(
            session, market_id, payload, settled=settled
        )
        durable_status = str(durable.get("status"))
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
        "bank_marker_written": marker_written,
        "durable": durable_status,
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
