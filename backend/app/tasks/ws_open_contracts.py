"""#9484 — an open Kalshi contract streams its price whatever its event's phase.

The Kalshi socket subscribes from events that are ``live``, ``scheduled``
within 6 h, or recently ``suspended`` (``kalshi_ws._kalshi_slate_event_window``).
Every market outside that join — a standalone future or prop with no
``event_id``, or a game market whose event is days away — never reached the
wire, so its stored price moved only when the 2 h REST poll came round, and
the #9484 post-commit invalidation had nothing to say about it. Alex's ruling
on #9484: market lifecycle, not game phase, decides streaming.

This is that rule for PRICES on Kalshi. Eligibility is the contract's own
unsettled truth, never a kickoff horizon:

- the market is not ``resolved`` (NULL fails OPEN — the column is nullable and
  a plain ``!=`` drops a NULL, as ``ws_slate`` says) and carries no
  ``settled_at``;
- the market has not passed its ``expiration_time`` (NULL fails open);
- the outcome has a venue ticker and no ``is_winner``.

Measured once to size this (production 2026-09-29 04:5xZ): 4,941 such Kalshi
markets outside the event link, 48,051 tickers, 5,104 of which moved price in
the previous 24 h — a write load well under the linked slate's.

**Never the two-sided settlement handler.** ``handle_lifecycle`` treats a
market as a two-sided game line: when one ticker settles it marks the whole
market ``resolved`` and writes the OPPOSITE ``is_winner`` onto every other
outcome. On a multi-candidate future one candidate settling "no" would crown
every other candidate. So these tickers never join the lifecycle map
(``market_id_by_ext``), which stays the linked slate.

**#10022 — but their settlement is graded PER LEG, from the socket.** Shipped
prices-only, the arm streamed a contract right up to its close and then left
its result to the REST sweep — hours to a day. Production 2026-10-01: Kalshi
finalized all seven CHC–SD Wild Card series contracts at 05:11Z; 80 minutes
later the finished series still printed ``SD wins 2-1 12%`` and ``Over 2.5
total games 38%``, and the one leg the sweep had graded (``CHC20``) took 23 h.
The open-contract connections now also subscribe ``market_lifecycle_v2``, and
:func:`grade_open_contract_leg` writes exactly what the REST grader writes for
the same declaration (``backfill_winners``: ``kms.gradeable_winner`` →
``api_settlement`` + the settled price) onto the ONE leg the frame names. It
never touches a sibling: every Kalshi ticker carries its own ``result``, so a
sibling is graded by its own frame. The market becomes ``resolved`` only when
no leg is left without a venue-authoritative grade — a stricter rule than the
poller's ``all_terminal``, so the socket can never close a board the sweep
would have left open.

**Their own connections, so the live game never pays for them.** The linked
slate's socket is unchanged. The admitted tickers are fanned over separate
connections of at most ``OPEN_CONTRACT_TICKERS_PER_CONNECTION``: production has
held 23,456 tickers on one Kalshi socket with full delivery (#837 measurement,
2026-09-22), so 20,000 sits under a size already observed to work, and a
rejected or throttled open-contract subscribe cannot take the game slate's
prices down with it.

``WS_OPEN_CONTRACT_PRICES=0`` turns the whole arm off at the next recycle with
no deploy — the undo line. ``WS_OPEN_CONTRACT_SETTLEMENT=0`` turns off only the
per-leg grading (the connections go back to ``ticker`` alone).
"""

import os
from collections.abc import Iterable, Mapping

#: Tickers per open-contract connection. Below the 23,456 one production socket
#: has carried in full; see the module docstring.
OPEN_CONTRACT_TICKERS_PER_CONNECTION = int(
    os.getenv("KALSHI_WS_OPEN_CONTRACT_TICKERS_PER_CONNECTION", "20000")
)


def open_contract_prices_enabled() -> bool:
    """False only when ``WS_OPEN_CONTRACT_PRICES`` is set to ``0``."""
    return os.getenv("WS_OPEN_CONTRACT_PRICES", "1").strip() != "0"


def open_contract_settlement_enabled() -> bool:
    """False only when ``WS_OPEN_CONTRACT_SETTLEMENT`` is set to ``0``."""
    return os.getenv("WS_OPEN_CONTRACT_SETTLEMENT", "1").strip() != "0"


def open_contract_channels() -> list[str]:
    """The channels an open-contract connection subscribes to."""
    if open_contract_settlement_enabled():
        return ["ticker", "market_lifecycle_v2"]
    return ["ticker"]


def lifecycle_state(msg: Mapping) -> str | None:
    """The venue state a lifecycle frame declares: ``status``, else ``event_type``."""
    return msg.get("status") or msg.get("event_type")


def lifecycle_verdict(msg: Mapping) -> tuple[str, bool] | None:
    """``(TICKER, is_winner)`` for a lifecycle frame that declares a side, else None.

    The venue's state is read from ``status`` or, failing that, ``event_type``:
    the v2 lifecycle channel names the transition (``determined``) in
    ``event_type``, and the repo's existing frames and fakes spell it
    ``status``. Either way the judgment is the shared three-state
    :func:`~app.utils.kalshi_market_status.gradeable_winner` — ``yes``/``no`` on a
    result-carrying state only; ``scalar``, ``""`` and a ``closed`` market grade
    nothing (#5304, #7987, CAL-P053).
    """
    from app.utils.kalshi_market_status import gradeable_winner

    if not isinstance(msg, Mapping):
        return None
    ticker = str(msg.get("market_ticker") or "").upper()
    if not ticker:
        return None
    won = gradeable_winner(lifecycle_state(msg), msg.get("result"))
    if won is None:
        return None
    return ticker, won


async def grade_open_contract_leg(session, *, market_id: int, outcome_id: int,
                                  state: str | None, result: str | None):
    """Grade ONE open-contract leg from a venue declaration; maybe resolve its market.

    ``state``/``result`` are the frame's own (``lifecycle_state``); the grade is
    :func:`~app.utils.kalshi_market_status.graded_columns` of them, the pair
    every Kalshi grader writes — so a declaration it cannot read writes nothing,
    and the settlement-writer census (#5246) discovers this site by that call.

    Returns ``(graded, resolved)``: ``graded`` is the outcome's
    ``(id, last_updated)`` row or None when nothing changed, ``resolved`` the
    market's ``(id, settled_at)`` row or None.

    * The leg write mirrors ``backfill_winners``' Kalshi grader column for
      column, so the socket and the sweep are one writer to every reader.
    * It never overwrites a leg that already carries a venue-authoritative
      source — a re-delivered frame (one per connection) writes 0 rows, and a
      grade the venue already gave is never downgraded or flipped by a stray
      frame.
    * No sibling is written. The market flips to ``resolved`` only when no leg
      is left without an authoritative grade.
    """
    from sqlalchemy import exists, func, or_, select, update

    from app.models.models import FuturesMarket, FuturesOutcome
    from app.utils.kalshi_market_status import graded_columns
    from app.utils.market_settlement import settled_values
    from app.utils.price_change_stamp import price_changed_at_value
    from app.utils.resolution_authority import AUTHORITATIVE_SOURCES
    from app.utils.settled_price import settled_price_values

    def _not_authoritative(col):
        return or_(col.is_(None), col.notin_(sorted(AUTHORITATIVE_SOURCES)))

    grade = graded_columns(state, result)
    if not grade:
        return None, None
    is_winner = grade["is_winner"]

    graded = (
        await session.execute(
            update(FuturesOutcome)
            .execution_options(synchronize_session=False)
            .where(
                FuturesOutcome.id == outcome_id,
                FuturesOutcome.market_id == market_id,
                _not_authoritative(FuturesOutcome.resolution_source),
            )
            .values(
                **grade,
                last_updated=func.now(),
                **settled_price_values(is_winner),
                price_changed_at=price_changed_at_value(
                    FuturesOutcome.current_probability,
                    FuturesOutcome.price_changed_at,
                    1.0 if is_winner else 0.0,
                ),
            )
            .returning(FuturesOutcome.id, FuturesOutcome.last_updated)
        )
    ).first()
    if graded is None:
        return None, None

    sibling = FuturesOutcome.__table__.alias("sibling")
    resolved = (
        await session.execute(
            update(FuturesMarket)
            .execution_options(synchronize_session=False)
            .where(
                FuturesMarket.id == market_id,
                or_(
                    FuturesMarket.status.is_(None),
                    FuturesMarket.status != "resolved",
                ),
                ~exists(
                    select(sibling.c.id).where(
                        sibling.c.market_id == market_id,
                        _not_authoritative(sibling.c.resolution_source),
                    )
                ),
            )
            .values(status="resolved", **settled_values(FuturesMarket.settled_at))
            .returning(FuturesMarket.id, FuturesMarket.settled_at)
        )
    ).first()
    return graded, resolved


def kalshi_open_contract_stmt():
    """Every unsettled Kalshi outcome with a ticker:
    (ticker, market_id, outcome_id, market event_id, market ticker).

    No event join and no event window — that is the point. The caller removes
    the tickers the linked slate already carries. The last two columns are the
    market's own row, read so a game winner can be bridged to its event's blend
    (:func:`open_contract_event_candidates`) without re-imposing the window.
    """
    from sqlalchemy import or_, select, text

    from app.models.models import FuturesMarket, FuturesOutcome

    return (
        select(
            FuturesOutcome.external_id,
            FuturesOutcome.market_id,
            FuturesOutcome.id,
            FuturesMarket.event_id,
            FuturesMarket.external_id,
        )
        .join(FuturesMarket, FuturesOutcome.market_id == FuturesMarket.id)
        .where(
            FuturesMarket.source == "kalshi",
            or_(
                FuturesMarket.status.is_(None),
                FuturesMarket.status != "resolved",
            ),
            FuturesMarket.settled_at.is_(None),
            or_(
                FuturesMarket.expiration_time.is_(None),
                FuturesMarket.expiration_time > text("NOW()"),
            ),
            FuturesOutcome.external_id.isnot(None),
            FuturesOutcome.is_winner.is_(None),
        )
    )


def open_contract_ticker_map(
    rows: Iterable[tuple[str, int, int]],
    linked: Mapping[str, tuple[int, int]],
) -> dict[str, tuple[int, int]]:
    """ticker → (market_id, outcome_id) for the rows the linked slate lacks.

    Keys are upper-cased like the linked map's, so a ticker the game socket
    already carries is never subscribed twice.
    """
    out: dict[str, tuple[int, int]] = {}
    for row in rows:
        ext_id, market_id, outcome_id = row[0], row[1], row[2]
        if not ext_id:
            continue
        ticker = ext_id.upper()
        if ticker in linked:
            continue
        out[ticker] = (market_id, outcome_id)
    return out


# ── the event bridge (#9484, existing cohort → event blend) ──────────────────
#
# Admitted for prices only, an open game-winner contract on an event more than
# 6 h out streamed its stored price and then stopped: the flush re-stamps the
# event blend from `event_id_by_outcome`, which was built from the linked slate
# alone, so the number on the card — `Event.win_probability_sources`, not the
# outcome row — waited for the REST poll. Production 2026-10-01 14:02Z: PIT @
# CLE (event 14780550, kickoff 10.2 h out) had its winner contract
# `KXNFLGAME-26OCT01PITCLE` subscribed on this arm and its event stream refused
# `not_live`. The bridge hands the flush the event behind the contracts it is
# ALREADY carrying. It adds no ticker to any subscription.
#
# Only game winners: `feeds_win_prob_blend` on the market ticker is the rule the
# blend itself applies to every Kalshi speaker (`live_blend._reading_for_entry`),
# so a spread, total or prop moving can never cost an event a refresh it cannot
# change. Only events still to be decided: scheduled or live, no
# `completed_at` — what the slate's own window admits, minus its horizon.

#: Event statuses whose blend the bridge may re-stamp. Suspended events keep
#: their own slate arm (`ws_slate.suspended_open_market_arm`).
BRIDGE_EVENT_STATUSES = ("scheduled", "live")


def open_contract_event_candidates(
    rows: Iterable[tuple],
    linked: Mapping[str, tuple[int, int]],
) -> dict[int, int]:
    """outcome_id → event_id for admitted open contracts that are game winners.

    Same exclusions as :func:`open_contract_ticker_map` (no ticker, or a ticker
    the linked slate carries), plus: the market has an event and its ticker
    feeds the win-probability blend. The event's own state is checked by the
    caller (:func:`open_contract_bridge_event_stmt`).
    """
    from app.utils.prediction_market_matching import feeds_win_prob_blend

    out: dict[int, int] = {}
    for row in rows:
        if len(row) < 5:
            continue
        ext_id, _market_id, outcome_id, event_id, market_ticker = row[:5]
        if not ext_id or event_id is None or not market_ticker:
            continue
        if ext_id.upper() in linked:
            continue
        if not feeds_win_prob_blend(market_ticker):
            continue
        out[outcome_id] = event_id
    return out


def open_contract_bridge_event_stmt(event_ids: Iterable[int]):
    """The candidate events still to be decided: id only, by primary key."""
    from sqlalchemy import select

    from app.models.models import Event

    return select(Event.id).where(
        Event.id.in_(sorted(set(event_ids))),
        Event.completed_at.is_(None),
        Event.status.in_(BRIDGE_EVENT_STATUSES),
    )


def open_contract_event_bridge(
    candidates: Mapping[int, int], admitted_event_ids: Iterable[int],
) -> dict[int, int]:
    """The candidates whose event the state read admitted."""
    admitted = set(admitted_event_ids)
    return {oid: eid for oid, eid in candidates.items() if eid in admitted}


def shard_tickers(
    tickers: Iterable[str],
    per_connection: int = OPEN_CONTRACT_TICKERS_PER_CONNECTION,
) -> list[list[str]]:
    """Sorted tickers in connection-sized shards, none lost.

    Sorted so a recycle re-deals the same shards when the population has not
    moved.
    """
    ordered = sorted(tickers)
    size = max(1, int(per_connection))
    return [ordered[i:i + size] for i in range(0, len(ordered), size)]


def prepared_shard_indexes(
    ids: Mapping[str, tuple[int, int]], shards: list[list[str]],
) -> set[int]:
    """Opt in only when each market has one key and that key owns one shard.

    Numeric shard boundaries can split sibling tickers. Ambiguous or split
    cohorts keep their original inline callback on every affected shard.
    This is a finite admission check, never a per-frame queue or history.
    """
    keys = {}
    market_keys = {}
    for ticker, (market_id, _outcome_id) in ids.items():
        parts = ticker.upper().rsplit("-", 1) if isinstance(ticker, str) else []
        key = parts[0] if len(parts) == 2 and all(parts) else None
        keys[ticker] = key
        market_keys.setdefault(market_id, set()).add(key)
    owners = {}
    for index, shard in enumerate(shards):
        for ticker in shard:
            owners.setdefault(keys.get(ticker), set()).add(index)
    ambiguous = {
        market_id for market_id, cohort in market_keys.items()
        if len(cohort) != 1 or None in cohort
    }
    return {
        index for index, shard in enumerate(shards)
        if shard and all(
            ticker in ids and keys[ticker] is not None
            and ids[ticker][0] not in ambiguous
            and len(owners[keys[ticker]]) == 1
            for ticker in shard
        )
    }
