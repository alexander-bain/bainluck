"""Targeted price refresh for register-pinned tournament markets (UX-P139).

═══ THE DEFECT THIS EXISTS TO FIX ═══

Alex, item 2: "was that the real current price-dark state or a mock artifact?
Then state the production guarantee: with the freshness gates, silently-stale
data can never render."

The freshness gates work — that half of the guarantee has held since UX-P131.
What the gates cannot do is make a number fresh, and measured 2026-08-26 the
entire playoff grid was 27 hours old:

    futures_odds_snapshots, all 672 US Open ladder outcomes
        newest captured_at : 2026-08-25 20:21:47 UTC
        oldest captured_at : 2026-08-25 16:15:28 UTC
    futures_odds_snapshots, Polymarket overall
        newest captured_at : 2026-08-26 23:39:28 UTC   (current to the minute)

So the poller was healthy and these particular markets were not being reached.
The cause is structural, not a bug: Gamma caps offset pagination at 2000
(gotcha "Poly creation freeze"), so ``_poll_polymarket_markets`` rotates a
20-page window across the active-event space and re-prices a given event only
when the cursor lands on it.  For most of the catalogue a once-a-day reading is
fine.  For the 336 markets that ARE the bracket grid on the page whose subject
is what the market thinks right now, it is not.

═══ WHY A REGISTER MAKES THE FIX TRIVIAL ═══

The scanning poll has to discover what exists.  This task does not: the
register already names every market the page will render, as an exact
``(source, market_id, outcome_id)`` triple.  So it asks Gamma for precisely
those condition ids — ``/markets?condition_ids=...``, which does not paginate
and is therefore not subject to the offset cap at all — and updates them.

The whole US Open register is ~420 Polymarket markets, which is 11 batched
requests.  At the 10-minute cadence below that is ~66 Gamma calls an hour
against a limit around 1,000, and it is bounded by the register rather than by
the catalogue: a tournament that ends stops costing anything the moment its
register is retired.

This task NEVER creates a market and never touches identity.  It updates prices
for outcomes the register already pins, which is why it is safe to run at a
cadence the discovery poll could not sustain.

═══ WHY BOTH RAILS SPEAK THE TERMINAL VOCABULARY (CERT P2, gotcha #53) ═══

Both functions here return a ``terminal`` and both labels are in
``task_verdict.ENFORCED_TASKS``.  CERT C-UX-P139-GRID-REGISTER-1's P2 found them
returning a bare ``verdict`` string that nothing reads: ``verdict_for`` produced
``TaskVerdict(unknown, authoritative=False)``, whose ``blocks_success`` is False,
so a rail that refreshed nothing forever was indistinguishable from a healthy one
in task metrics.

That is this codebase's founding false-GREEN shape and it is especially sharp
here, because the failure is SILENT BY CONSTRUCTION: the page keeps rendering.
A dead refresh rail does not blank the grid — it lets every number on it age,
wearing whatever freshness word the gates give it, which is precisely the
27-hour state this task was written to end.  "It returned" is not "it worked",
so the zero-yield states below are terminals and not log lines.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

#: How many condition ids per Gamma request.  See
#: ``PolymarketAPIService.get_markets_by_conditions``.
BATCH_SIZE = 40

#: A hard ceiling on how many markets one run will refresh, so a mis-sized
#: register can never turn a 10-minute task into a Gamma flood.  Well above the
#: US Open's ~420 and well below anything that would matter.
MAX_MARKETS = 2000

#: What the scheduled run refreshes when nobody named anything.  Named, like the
#: route's own table.
DEFAULT_PRICE_TARGETS: list[tuple[str, str]] = [("us-open", "2026")]
DEFAULT_RESULT_TARGETS: list[tuple[str, str]] = [("us-open", "US Open")]


def registered_polymarket_conditions(register: dict[str, Any]) -> dict[str, list[int]]:
    """``condition_id -> [outcome_id, ...]`` for every Polymarket identity pinned.

    Walks players, matchups AND reaches.  Matchups are included even though
    their identities live under ``sides`` — the slate is the other half of the
    page and it has the same problem for the same reason.
    """
    out: dict[str, list[int]] = {}

    def add(block: Any) -> None:
        if not isinstance(block, dict) or block.get("source") != "polymarket":
            return
        condition = block.get("market_external_id")
        if not isinstance(condition, str) or not condition:
            return
        ids = out.setdefault(condition, [])
        if isinstance(block.get("outcome_id"), int):
            ids.append(block["outcome_id"])
        for side in (block.get("sides") or {}).values():
            if isinstance(side, dict) and isinstance(side.get("outcome_id"), int):
                ids.append(side["outcome_id"])

    for player in register.get("players") or []:
        if isinstance(player, dict):
            for block in player.get("sources") or []:
                add(block)
    for matchup in register.get("matchups") or []:
        if isinstance(matchup, dict):
            for block in matchup.get("sources") or []:
                add(block)
    for reach in register.get("reaches") or []:
        if isinstance(reach, dict):
            for block in reach.get("sources") or []:
                add(block)
    return out


async def _refresh_registered_tournament_prices(
    tournaments: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """Re-price every Polymarket market a committed tournament register pins."""
    from app.services.polymarket_api import PolymarketAPIService
    from app.utils.tournament_register import load_register

    # Explicit, like the route's own table: a register is refreshed because
    # somebody said so, never because a file appeared in a directory.
    #
    # `is None` and not `or`: an explicitly EMPTY list means "refresh nothing"
    # and must reach the `no_work` terminal below. Falling back to the default
    # on `[]` would turn a deliberate no-op into a full run, and — worse for
    # this file — make the terminal unreachable and its guard untestable.
    targets = DEFAULT_PRICE_TARGETS if tournaments is None else tournaments
    if not targets:
        return _refresh_terminal(
            {"tournaments": 0, "conditions_requested": 0, "errors": []},
            "no_work",
            "no_targets",
        )

    stats: dict[str, Any] = {
        "tournaments": 0,
        "conditions_requested": 0,
        "markets_returned": 0,
        # UX-P158: how many markets had their venue volume figure written down
        # with a stamp. Counted separately from `outcomes_updated` because the
        # two can diverge — an unpriced market is observed but not re-priced —
        # and a rail whose volume writes silently stopped would otherwise look
        # exactly like one whose prices are fine.
        "volume_observed": 0,
        "outcomes_updated": 0,
        "snapshots_written": 0,
        "unpriced": 0,
        "not_returned": 0,
        "errors": [],
    }

    wanted: dict[str, list[int]] = {}
    for tournament, season in targets:
        register = load_register(tournament, season)
        if register is None:
            stats["errors"].append(f"{tournament}-{season}: no readable register")
            continue
        stats["tournaments"] += 1
        for condition, outcome_ids in registered_polymarket_conditions(register).items():
            wanted.setdefault(condition, []).extend(outcome_ids)

    if not stats["tournaments"]:
        # NOT `no_work`. The registers are committed files in this repo; if none
        # of the named ones loads, something is broken here, not absent upstream.
        return _refresh_terminal(stats, "failed", "no_readable_register")

    conditions = sorted(wanted)[:MAX_MARKETS]
    stats["conditions_requested"] = len(conditions)
    if not conditions:
        # A loaded register that pins no Polymarket identity. Authoritative
        # UNKNOWN rather than failed — a retired tournament is the honest case —
        # but never GREEN: a refresh rail that refreshed nothing has not proved
        # it can refresh anything.
        return _refresh_terminal(stats, "no_work", "no_registered_polymarket_identities")

    service = PolymarketAPIService()
    try:
        markets = await service.get_markets_by_conditions(
            conditions, batch_size=BATCH_SIZE
        )
    except Exception as exc:  # noqa: BLE001 — reported, never swallowed
        stats["errors"].append(f"gamma fetch failed: {exc}")
        return _refresh_terminal(stats, "failed", "fetch_failed")

    stats["markets_returned"] = len(markets)
    stats["not_returned"] = len(conditions) - len({m.condition_id for m in markets})

    if not markets:
        # We asked for identities the register pins BY ID and Gamma returned
        # none of them. Either the ids are wrong or the rail cannot reach Gamma;
        # both are ours to fix and neither is a run that worked.
        return _refresh_terminal(stats, "failed", "no_markets_returned")

    now = datetime.now(timezone.utc)
    try:
        await _write_refreshed_prices(markets, stats, now=now)
    except Exception as exc:  # noqa: BLE001
        # A WRITE THAT FAILED IS THE QUIETEST FAILURE THIS RAIL HAS. The fetch
        # worked, the numbers are in memory, and nothing reaches the page. It is
        # caught here rather than left to raise so the summary itself carries the
        # terminal — task metrics then distinguish "could not write" from "wrote
        # nothing to write" instead of showing one bare exception string.
        logger.exception("tournament price refresh: write failed")
        stats["errors"].append(f"write failed: {exc}")
        return _refresh_terminal(stats, "failed", "write_failed")

    if not stats["snapshots_written"]:
        # Markets came back and not one price landed. The grid keeps rendering
        # and every number on it keeps ageing — the exact invisible failure.
        return _refresh_terminal(stats, "failed", "no_prices_written")

    return _refresh_terminal(stats, "complete", "prices_written")


def _refresh_terminal(stats: dict[str, Any], terminal: str, reason: str) -> dict[str, Any]:
    """Stamp the contract fields and log once. Every return goes through here."""
    stats["terminal"] = terminal
    stats["reason"] = reason
    logger.info("tournament price refresh: %s", stats)
    return stats


async def _write_refreshed_prices(
    markets: list[Any], stats: dict[str, Any], *, now: datetime
) -> None:
    """Update every registered outcome these markets price, and snapshot it."""
    from sqlalchemy import select, update
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.models import FuturesMarket, FuturesOddsSnapshot, FuturesOutcome
    from app.tasks.base import get_task_session
    from app.tasks.polymarket import (
        _resolve_market_probability,
        complementary_book,
    )
    from app.utils.odds_math import probability_to_american

    async with get_task_session() as session:
        for market in markets:
            # ── THE VOLUME OBSERVATION TRAVELS WITH THE PRICE TOO (UX-P158).
            #
            # Q428 taught this rail to write the BOOK alongside the price it
            # produced, for the reason its own comment gives: two observations
            # must not wear one timestamp. The venue's 24h volume is the third
            # thing in that same Gamma response and it was still being thrown
            # away, so the illiquidity mark's "did anybody trade it" half was
            # reading a column the hourly scan last wrote on 2026-08-25 —
            # measured 83 hours stale on every one of the 336 US Open ladder
            # rows, against a price this task had refreshed nine minutes
            # earlier. A fact graded from those two together is not one
            # observation, and `market_liquidity` now refuses it as such.
            #
            # `volume_updated_at` is what makes the NULL readable. UX-P158
            # measured, on 328 markets against the Polymarket trade tape with
            # no exceptions, that Gamma OMITS a zero-valued `volume24hr` rather
            # than serving it — so "asked at 05:10, no figure came back" is a
            # measured zero, while "never asked" is nothing at all. The stamp
            # is the only thing that separates them, which is why it is written
            # unconditionally and the figure is written NULL-preserving.
            #
            # Written for every market Gamma RETURNED, including one this task
            # cannot price: whether we could resolve a probability is a fact
            # about the book, and how much of it traded is a fact about the
            # market. Skipping the unpriced ones would leave the stalest rows
            # on the surface permanently unreadable.
            await session.execute(
                update(FuturesMarket)
                .where(FuturesMarket.external_id == market.condition_id)
                .values(
                    volume_24h=(
                        int(market.volume_24h)
                        if market.volume_24h is not None
                        else None
                    ),
                    volume_updated_at=now,
                )
            )
            stats["volume_observed"] += 1

            probability = _resolve_market_probability(market)
            if probability is None:
                # A placeholder or an untradeable book. Not an error, and not a
                # number: gotcha #19's rule, unchanged.
                stats["unpriced"] += 1
                continue

            rows = (
                await session.execute(
                    select(FuturesOutcome.id, FuturesOutcome.name)
                    .join(FuturesMarket, FuturesMarket.id == FuturesOutcome.market_id)
                    .where(FuturesMarket.external_id == market.condition_id)
                )
            ).all()
            if not rows:
                continue

            for outcome_id, name in rows:
                # The YES side carries the market's resolved probability; the
                # NO side is its complement. Read off the outcome NAME rather
                # than from position: `outcome_prices[1]` and "the row called
                # No" are the same thing only when the source ordered them the
                # way we assumed, and this task has no business re-deriving an
                # ordering the ingest already pinned.
                label = (name or "").strip().lower()
                if label == "yes":
                    value = probability
                    bid, ask, last = (
                        market.best_bid,
                        market.best_ask,
                        market.last_trade_price,
                    )
                elif label == "no":
                    value = 1.0 - probability
                    # The two tokens of a binary share ONE book, so the No side
                    # is the same orders addressed from the other token — an
                    # identity, not an estimate. Shared rather than restated:
                    # CAL-P095 measured 493,415 Under/No legs carrying no book
                    # at all precisely because a writer named these columns on
                    # one leg and not the other.
                    bid, ask, last = complementary_book(
                        market.best_bid, market.best_ask, market.last_trade_price
                    )
                else:
                    continue

                value = max(0.0, min(1.0, value))
                await session.execute(
                    update(FuturesOutcome)
                    .where(FuturesOutcome.id == outcome_id)
                    .values(
                        current_probability=value,
                        current_american_odds=probability_to_american(value),
                        # Q428: THE BOOK TRAVELS WITH THE PRICE IT PRODUCED.
                        # Without these two columns this rail moved the number
                        # every ten minutes and left the book frozen at whatever
                        # the last full poll wrote, so 181 of 328 US Open ladder
                        # rows held a probability sitting OUTSIDE their own
                        # stored [bid, ask] — not a stale book but two different
                        # observations wearing one timestamp. Every book-based
                        # predicate downstream (is_fabricated_midpoint #1578,
                        # classify_fabricated_book UX-P011, the wide-spread
                        # exclusion in precompute_calibration) was therefore
                        # judging the wrong book on this surface, and the site
                        # had no signal with which to mark an illiquid cell as
                        # illiquid — which is what Alex's 2026-08-28 ruling asks
                        # for. NULL-preserving: a market that arrives with no
                        # book leaves with no book, never with a fabricated 0
                        # that would read downstream as a real, empty one.
                        current_yes_bid=bid,
                        current_yes_ask=ask,
                        last_updated=now,
                    )
                )
                stats["outcomes_updated"] += 1

                # The snapshot is what `price_observed_at` reads, so a refresh
                # that updated the outcome and wrote no snapshot would move the
                # price while leaving the page's freshness verdict at 27 hours
                # — a number that changed without admitting it had.
                #
                # Q428: and a snapshot without its book is a permanent one. The
                # outcome row is at least overwritten by the next full poll;
                # 34,638 ladder snapshots written in 12 hours carry a NULL book
                # and that history cannot be reconstructed from anywhere.
                await session.execute(
                    pg_insert(FuturesOddsSnapshot).values(
                        outcome_id=outcome_id,
                        bookmaker="polymarket",
                        probability=value,
                        american_odds=probability_to_american(value),
                        yes_bid=bid,
                        yes_ask=ask,
                        last_price=last,
                        captured_at=now,
                    )
                )
                stats["snapshots_written"] += 1

        await session.commit()


# ---------------------------------------------------------------------------
# ESPN results sync (UX-P139, Alex's item 9)
# ---------------------------------------------------------------------------

#: How long a cached results payload stays servable.  Generous relative to the
#: 3-minute sync so one missed run does not blank the section; a genuinely dead
#: task lets it expire, which is the honest outcome — an empty section with a
#: stated reason beats an hour-old result presented as current.
RESULTS_TTL_SECONDS = 900
RESULTS_PREFIX = "bainluck:tournament-results:"


async def _sync_tournament_results(
    tournaments: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """Fetch ESPN's tennis results into Redis for the hub route to read.

    THE FETCH LIVES HERE AND NOT IN THE ROUTE, and that is the point of the
    task rather than an implementation detail.  A third-party call inside
    ``GET /api/tournaments/{slug}`` is the shape the feed's standing rule
    forbids by name: the first request after every cache expiry pays the round
    trip, a slow ESPN becomes a slow page for whoever is unlucky, and the route
    contract tests start making live network calls.

    Three minutes, because a finished match should appear while the reader is
    still on the page, and because two scoreboard requests every three minutes
    is nothing.
    """
    from app.tasks.redis_state import get_async_redis_client

    # Named, like the route's own table: a tournament is synced because
    # somebody wrote it down. `espn_event_name` selects it out of a scoreboard
    # that also carries whatever else is on that week. `is None`, not `or`, for
    # the reason given on the price rail: an explicit `[]` means nothing to sync
    # and has to be able to say so.
    targets = DEFAULT_RESULT_TARGETS if tournaments is None else tournaments

    stats: dict[str, Any] = {"tournaments": 0, "written": 0, "errors": []}
    if not targets:
        return _results_terminal(stats, "no_work", "no_targets")

    for slug, event_name in targets:
        try:
            from app.services.espn_tennis import fetch_tournament_results

            results = await fetch_tournament_results(event_name)
        except Exception as exc:  # noqa: BLE001 — reported, never swallowed
            stats["errors"].append(f"{slug}: {exc}")
            continue

        stats["tournaments"] += 1
        if results.get("errors"):
            # A partial fetch is written anyway — half the tours is better than
            # none — but the failure travels in the payload so the section can
            # say "we could not reach the feed" rather than "nothing finished".
            stats["errors"].extend(f"{slug}: {e}" for e in results["errors"])

        try:
            await get_async_redis_client().setex(
                f"{RESULTS_PREFIX}{slug}",
                RESULTS_TTL_SECONDS,
                json.dumps(results, default=str),
            )
            stats["written"] += 1
        except Exception as exc:  # noqa: BLE001
            stats["errors"].append(f"{slug} cache write: {exc}")

    # gotcha #53: "it returned" is not "it worked". A run that wrote nothing is
    # a failure even when nothing raised — and it is INVISIBLE from the page,
    # because the results section falls back to its cached payload and then to
    # an honest empty. Neither of those is a signal that the rail is dead.
    if not stats["written"]:
        return _results_terminal(stats, "failed", "nothing_written")
    # A run that wrote SOME tours and errored on others returns `complete` here
    # and is downgraded to PARTIAL by the contract's own damage rule — the
    # `errors` list is the caveat, and it is read rather than restated.
    return _results_terminal(stats, "complete", "results_cached")


def _results_terminal(stats: dict[str, Any], terminal: str, reason: str) -> dict[str, Any]:
    """Stamp the contract fields and log once. Every return goes through here."""
    stats["terminal"] = terminal
    stats["reason"] = reason
    logger.info("tournament results sync: %s", stats)
    return stats
