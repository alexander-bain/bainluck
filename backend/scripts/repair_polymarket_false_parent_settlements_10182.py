"""#10182 — reopen Polymarket boards the venue still trades that were stamped "settled".

THE SHIP: a board the venue is still trading — the World Series Exact Matchup
(/futures/63490287), the Korn Ferry Compliance Solutions Winner (/futures/63049616)
and their siblings — stops reading "This market has been settled · RESOLVED" with
every row "Lost".

WHY (production, 2026-10-02)
----------------------------

``sync_polymarket_resolved_status`` resolved a parent when none of the legs WE
store was still trading. For a partial negRisk field we hold only the closed
slice (World Series: 16 of the venue's 37 legs, all eliminated; Korn Ferry
Winner: 2 of 113), so the guard could not see the open legs and resolved a live
board with ``resolution_gate = {task: sync_polymarket_resolved_status,
proof_kind: winner}`` and no winner. PR #10183 (live at ``6ba5c04862``, v5413)
stops new cases: a parent keyed by the Gamma event id is withheld while the venue
reports that event ``closed: false`` AND lists an open leg. Its 11:30Z after-check
counted 0 such closures, against 20 in the 05:30Z run before it. Those 20, plus
the World Series board resolved 2026-10-01 11:30Z, are still marked resolved.
This script repairs them.

WHO IS SELECTED
---------------

Only the pinned ``CANDIDATES`` (market id, Gamma event id) — the retained 05:30Z
cohort plus the specimen. There is no population scan. Each one must, AT RUN TIME:

* still be ``source='polymarket'`` with its pinned ``external_id``, and its
  ``polymarket_event_id`` / ``group_id`` (``GAMMA_EVENT_ID_EXPR``'s inputs) must
  agree with that id or be absent;
* be ``status='resolved'`` with a ``settled_at`` and a ``resolution_gate`` written
  by ``sync_polymarket_resolved_status``. Another writer's resolution is not ours
  to undo;
* carry the shipped guard's witness on a fresh Gamma ``/events/{id}`` read. That
  read goes through the same ``settled_legs`` the guard uses: the payload's id is
  the pinned id, the event is not ``closed``, and it lists at least one open leg;
* have every stored leg on that venue event: its condition id (bare or
  ``_yes``/``_no``) appears among the event's markets.

A board that fails identity, state or evidence is REFUSED and not written. A board
the venue now reports closed, or with no open leg, is SKIP_NO_WITNESS: it may
really be over, and the regular sync owns it. A board already reopened is a NOOP.

WHAT IS WRITTEN
---------------

Parent (the invalid state): ``status 'resolved' -> 'open'``, ``settled_at -> NULL``,
and the ``resolution_gate`` key is removed from ``market_metadata``. Every other
metadata key stays.

Legs: a verdict the VENUE gave is kept. That means a leg the venue reports closed,
whose stored ``is_winner`` matches the venue's terminal price for that side. This
covers the SK hynix legs that hit, the soccer player props that paid, and every
eliminated matchup. The leg rule:

* a DERIVED stamp (``all_losers`` / ``clean_resolution`` / ``pass2_loser``) on a leg
  the venue still TRADES is cleared to ``is_winner = NULL, resolution_source =
  NULL``. Nothing settled it; a ``backfill_winners`` pass guessed from the false
  parent;
* any other verdict on a still-trading leg refuses the board (unsupported);
* a verdict on a closed leg that contradicts the venue, or that the venue gives no
  terminal price for, refuses the board;
* a DERIVED stamp on a venue-CLOSED leg whose value the venue confirms is
  PROMOTED to ``resolution_source = 'api_settlement'``. That happens only when
  the stored price already sits at the terminal price for the leg's side, so the
  row becomes byte-identical to what the sync's ``settle_outcomes_stmt`` writes
  for that condition; a non-terminal stored price refuses the board. These are
  the specimen's 16 legs, which Pass 4 relabelled ``all_losers`` at 2026-10-01
  15:58Z.

WHY THE PROMOTION IS NOT OPTIONAL. ``writable_leg_sql`` (``futures_liveness``)
treats ``is_winner=false`` + ``all_losers`` as still writable, so a reopened
specimen would enter ``polymarket_condition_refresh``'s hourly pool. That rail
grades those legs ``api_settlement`` and then runs ``tournament_price_refresh``'s
#6919 deferred close, which resolves any Polymarket market whose STORED legs are
all graded. That is the same stored-legs-only blindness as #10182, and the repair
would be undone within the hour. A board whose legs are all ``api_settlement`` is
not writable and never enters that pool. Measured 2026-10-02: the other 20 boards
already carry only ``api_settlement``, and all 1,116 sibling rows sharing their
conditions are ``resolved`` with 0 writable legs.

The resolve sync will not re-close a reopened board while the witness holds (that
is #10183), and Pass 4 reads only ``status='resolved'``. So a reopened board stays
open until the venue settles it, and then resolves through the normal path.

THE BACKUP, THE COMPARE-AND-SWAP, THE UNDO
------------------------------------------

``--apply`` first banks each selected board's BEFORE ``status / settled_at /
resolution_gate`` in ``backup_10182_markets``, and each leg it will clear or
promote in ``backup_10182_outcomes``, then commits the bank. It writes nothing to a board
whose bank does not hold exactly the state it planned from. Each board is then
written inside its own SAVEPOINT. Every UPDATE matches on the full state it read:
parent status, settled_at and the gate itself; each leg's id, external id,
is_winner and source (and, for a promotion, the terminal price). A miss rolls back that board alone and is counted as
``drift``. ``--restore`` writes the banked values back, but only onto rows still in
the exact AFTER state, under the same savepoint and drift rules. The DDL is
``CREATE TABLE IF NOT EXISTS`` behind a person's invocation on a named app: notice
47(c), not migration-class.

    heroku run:detached -a bainluck -- python3 scripts/repair_polymarket_false_parent_settlements_10182.py                        # dry run
    heroku run:detached -a bainluck -- python3 scripts/repair_polymarket_false_parent_settlements_10182.py --apply --only 63490287  # specimen first
    heroku run:detached -a bainluck -- python3 scripts/repair_polymarket_false_parent_settlements_10182.py --apply                 # the rest
    heroku run:detached -a bainluck -- python3 scripts/repair_polymarket_false_parent_settlements_10182.py --restore               # undo

Refuses unless ``HEROKU_APP_NAME`` is ``bainluck`` or ``bainluck-heavy``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from app.utils.polymarket_settlement_scan import settled_legs  # noqa: E402

PRODUCTION_APPS = frozenset({"bainluck", "bainluck-heavy"})

BACKUP_MARKETS = "backup_10182_markets"
BACKUP_OUTCOMES = "backup_10182_outcomes"

#: The writer whose resolutions this repairs. Nothing else is undone.
SYNC_TASK = "sync_polymarket_resolved_status"
GATE_KEY = "resolution_gate"

#: Stamps ``backfill_winners`` derives from a market's ``status='resolved'`` rather
#: than from a settlement of the leg itself. Only these may be cleared, and only
#: on a leg the venue still trades.
DERIVED_SOURCES = frozenset({"all_losers", "clean_resolution", "pass2_loser"})

#: The venue-settlement label ``settle_outcomes_stmt`` writes.
SETTLEMENT_SOURCE = "api_settlement"

#: A leg priced at or past this is a settled winner; ``1 - x`` or below a loser.
#: The same envelope as ``SettledLegs.terminal_condition_ids``.
_TERMINAL_WIN = 0.95

#: (market id, Gamma event id). The retained 05:30Z 2026-10-02 cohort: the 20
#: boards that run closed while Gamma ``/events/{id}``, read right after, still
#: listed them open with a trading leg. Plus the specimen, closed 2026-10-01 11:30Z.
SPECIMEN = (63490287, "1110298")  # MLB Playoffs: World Series Exact Matchup
CANDIDATES: tuple[tuple[int, str], ...] = (
    SPECIMEN,
    (62275323, "1078048"),  # What will SK hynix (SKHY) hit in October 2026?
    (62275324, "1078047"),  # What will MicroStrategy (MSTR) hit in October 2026?
    (62554308, "1086147"),  # PGA Tour: Bank of Utah Championship Third Round Leader
    (62554309, "1086146"),  # PGA Tour: Bank of Utah Championship Second Round Leader
    (62554313, "1086156"),  # PGA Tour: Bank of Utah Championship To Make the Cut
    (63045536, "1098315"),  # LPGA: LOTTE Championship First Round Leader
    (63049612, "1098453"),  # Korn Ferry: Compliance Solutions Third Round Leader
    (63049613, "1098452"),  # Korn Ferry: Compliance Solutions Second Round Leader
    (63049616, "1098408"),  # Korn Ferry: Compliance Solutions Championship Winner
    (63049618, "1098448"),  # Korn Ferry: Compliance Solutions Top 20
    (63049620, "1098445"),  # Korn Ferry: Compliance Solutions Top 10
    (63049621, "1098444"),  # Korn Ferry: Compliance Solutions Top 5
    (63049660, "1098369"),  # DP World Tour: Alfred Dunhill Links Third Round Leader
    (63049661, "1098368"),  # DP World Tour: Alfred Dunhill Links Second Round Leader
    (63049667, "1098354"),  # DP World Tour: Alfred Dunhill Links Top 20
    (63049670, "1098353"),  # DP World Tour: Alfred Dunhill Links Top 10
    (63049671, "1098351"),  # DP World Tour: Alfred Dunhill Links Top 5
    (63646318, "1115031"),  # Israel vs. Kosovo - Player Props
    (63656412, "1115049"),  # Greece vs. Netherlands - Player Props
    (63656414, "1115048"),  # Wales vs. Norway - Player Props
)

REOPEN = "REOPEN"
NOOP = "NOOP"
SKIP_NO_WITNESS = "SKIP_NO_WITNESS"
REFUSED = "REFUSED"


class Refused(RuntimeError):
    """The run stops before any write."""


class _Drift(RuntimeError):
    """A compare-and-swap missed; the board's savepoint rolls back."""


def refuse_unless_production(env: dict) -> None:
    app = env.get("HEROKU_APP_NAME", "")
    if app not in PRODUCTION_APPS:
        raise Refused(
            f"HEROKU_APP_NAME={app!r} is not a production app "
            f"({sorted(PRODUCTION_APPS)}); refusing"
        )


@dataclass
class MarketPlan:
    market_id: int
    event_id: str
    verdict: str
    reason: str = ""
    name: str | None = None
    before: dict = field(default_factory=dict)
    venue: dict = field(default_factory=dict)
    #: ``(outcome_id, external_id, is_winner, resolution_source)`` per leg to clear.
    clear_legs: list[tuple[int, str, bool | None, str | None]] = field(default_factory=list)
    #: ``(outcome_id, external_id, is_winner, resolution_source, terminal_price)``
    #: per venue-closed leg whose derived stamp is promoted to ``api_settlement``.
    promote_legs: list[tuple[int, str, bool, str, float]] = field(default_factory=list)
    legs_preserved: int = 0
    #: The read value itself, so the compare-and-swap binds what was read.
    settled_at: Any = None

    def as_dict(self) -> dict:
        after = {}
        if self.verdict == REOPEN:
            after = {"status": "open", "settled_at": None, GATE_KEY: None}
        return {
            "market_id": self.market_id,
            "event_id": self.event_id,
            "name": self.name,
            "verdict": self.verdict,
            "reason": self.reason,
            "before": self.before,
            "after": after,
            "venue": self.venue,
            "legs_preserved": self.legs_preserved,
            "legs_cleared": [
                {"outcome_id": oid, "external_id": ext, "is_winner": w, "resolution_source": s}
                for oid, ext, w, s in self.clear_legs
            ],
            "legs_promoted": [
                {"outcome_id": oid, "external_id": ext, "is_winner": w,
                 "resolution_source": f"{s} -> {SETTLEMENT_SOURCE}"}
                for oid, ext, w, s, _price in self.promote_legs
            ],
        }


def _base_condition(external_id: str) -> str:
    for suffix in ("_yes", "_no"):
        if external_id.endswith(suffix):
            return external_id[: -len(suffix)]
    return external_id


def plan_market(
    candidate: tuple[int, str],
    market: dict | None,
    legs: list[dict],
    venue_raw: dict | None,
) -> MarketPlan:
    """Decide one board. Pure, so the unit file drives every branch.

    ``market``: ``{id, source, external_id, name, status, settled_at,
    polymarket_event_id, group_id, gate}`` or None when the row is gone.
    ``legs``: ``[{id, external_id, is_winner, resolution_source, current_probability}, ...]``.
    ``venue_raw``: the Gamma ``/events/{id}`` payload, or None when unreadable.
    """
    market_id, event_id = candidate
    p = MarketPlan(market_id=market_id, event_id=event_id, verdict=REFUSED)

    def refuse(reason: str) -> MarketPlan:
        p.verdict, p.reason = REFUSED, reason
        return p

    if market is None:
        return refuse("market row missing")
    p.name = market.get("name")
    p.settled_at = market.get("settled_at")
    gate = market.get("gate")
    p.before = {
        "status": market.get("status"),
        "settled_at": None if market.get("settled_at") is None else str(market["settled_at"]),
        GATE_KEY: gate,
    }

    # Identity: the row is still the board the cohort named.
    if market.get("source") != "polymarket" or market.get("external_id") != event_id:
        return refuse(
            f"identity drift: source={market.get('source')!r} "
            f"external_id={market.get('external_id')!r}, pinned polymarket/{event_id}"
        )
    pe = market.get("polymarket_event_id")
    if pe not in (None, "", event_id):
        return refuse(f"identity drift: polymarket_event_id={pe!r}, pinned {event_id}")
    gid = market.get("group_id")
    if gid not in (None, "", f"polymarket:{event_id}"):
        return refuse(f"identity drift: group_id={gid!r}, pinned polymarket:{event_id}")

    # State: resolved by the sync, or already repaired.
    status = market.get("status")
    if status == "open" and gate is None and market.get("settled_at") is None:
        p.verdict, p.reason = NOOP, "already open (repaired or never closed)"
        return p
    if status != "resolved":
        return refuse(f"state drift: status={status!r}")
    if market.get("settled_at") is None:
        return refuse("state drift: resolved with no settled_at")
    if not isinstance(gate, dict) or gate.get("task") != SYNC_TASK:
        return refuse(f"resolved by another writer ({gate!r}); not this repair's to undo")

    # Evidence: the shipped guard's witness, through the guard's own reader.
    if venue_raw is None:
        return refuse("venue unreadable (Gamma /events/{id} returned nothing)")
    venue = settled_legs(venue_raw)
    if venue is None:
        return refuse("venue payload carries no event id")
    if venue.event_id != event_id:
        return refuse(f"identity drift: venue answered event {venue.event_id}, pinned {event_id}")
    p.venue = {
        "event_closed": venue.event_closed,
        "open_legs": len(venue.open_condition_ids),
        "closed_legs": len(venue.settled_condition_ids),
        "stored_legs": len(legs),
    }
    if venue.event_closed or not venue.open_condition_ids:
        p.verdict = SKIP_NO_WITNESS
        p.reason = (
            "venue reports the event closed"
            if venue.event_closed
            else "venue lists no open leg"
        )
        return p

    open_set = set(venue.open_condition_ids)
    closed_set = set(venue.settled_condition_ids)
    terminal = set(venue.terminal_condition_ids)
    clear: list[tuple[int, str, bool | None, str | None]] = []
    promote: list[tuple[int, str, bool, str, float]] = []
    preserved = 0
    for leg in legs:
        ext = leg.get("external_id") or ""
        base = _base_condition(ext)
        w, src = leg.get("is_winner"), leg.get("resolution_source")
        if base in open_set:
            if src in DERIVED_SOURCES:
                clear.append((int(leg["id"]), ext, w, src))
            elif w is None and src is None:
                preserved += 1
            else:
                return refuse(
                    f"unsupported: leg {leg['id']} ({ext}) carries is_winner={w!r} "
                    f"source={src!r} while the venue still trades it"
                )
        elif base in closed_set:
            if w is None:
                preserved += 1
                continue
            if base not in terminal:
                return refuse(
                    f"unsupported: leg {leg['id']} ({ext}) graded is_winner={w!r} but the "
                    "venue gives no terminal price"
                )
            yes_won = venue.settlement_prices[base][0] >= _TERMINAL_WIN
            expected = (not yes_won) if ext.endswith("_no") else yes_won
            if bool(w) != expected:
                return refuse(
                    f"drift: leg {leg['id']} ({ext}) is_winner={w!r} contradicts the "
                    f"venue (expected {expected})"
                )
            if src in DERIVED_SOURCES:
                price = 1.0 if expected else 0.0
                stored = leg.get("current_probability")
                if stored is None or float(stored) != price:
                    return refuse(
                        f"unsupported: leg {leg['id']} ({ext}) carries derived {src!r} at "
                        f"price {stored!r}, not the terminal {price}; promoting it would "
                        "leave a settled leg carrying a price (#5246)"
                    )
                promote.append((int(leg["id"]), ext, bool(w), src, price))
                continue
            preserved += 1
        else:
            return refuse(f"identity drift: leg {leg['id']} ({ext!r}) is not on venue event {event_id}")

    p.verdict = REOPEN
    p.reason = (
        f"venue event open with {len(open_set)} open leg(s); "
        f"{preserved} venue verdict(s) kept, {len(promote)} derived stamp(s) promoted, "
        f"{len(clear)} derived stamp(s) cleared"
    )
    p.clear_legs = clear
    p.promote_legs = promote
    p.legs_preserved = preserved
    return p


# --- reads ------------------------------------------------------------------

def _gate_of(meta: Any) -> Any:
    if isinstance(meta, str):
        meta = json.loads(meta)
    if not isinstance(meta, dict):
        return None
    return meta.get(GATE_KEY)


async def _read_market(session, market_id: int) -> tuple[dict | None, list[dict]]:
    got = await session.execute(
        text(
            "SELECT id, source, external_id, name, status, settled_at, group_id, "
            "market_metadata->>'polymarket_event_id' AS pe, market_metadata "
            "FROM futures_markets WHERE id = :mid"
        ),
        {"mid": market_id},
    )
    r = got.first()
    if r is None:
        return None, []
    market = {
        "id": int(r.id),
        "source": r.source,
        "external_id": r.external_id,
        "name": r.name,
        "status": r.status,
        "settled_at": r.settled_at,
        "group_id": r.group_id,
        "polymarket_event_id": r.pe,
        "gate": _gate_of(r.market_metadata),
    }
    rows = await session.execute(
        text(
            "SELECT id, external_id, is_winner, resolution_source, current_probability "
            "FROM futures_outcomes WHERE market_id = :mid ORDER BY id"
        ),
        {"mid": market_id},
    )
    legs = [
        {
            "id": int(x.id),
            "external_id": x.external_id,
            "is_winner": x.is_winner,
            "resolution_source": x.resolution_source,
            "current_probability": x.current_probability,
        }
        for x in rows
    ]
    return market, legs


# --- backup -----------------------------------------------------------------

async def _ensure_backup_tables(session) -> None:
    await session.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {BACKUP_MARKETS} ("
            " market_id bigint PRIMARY KEY,"
            " external_id text NOT NULL,"
            " status text NOT NULL,"
            " settled_at timestamptz,"
            " resolution_gate jsonb,"
            " taken_at timestamptz NOT NULL DEFAULT now())"
        )
    )
    await session.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {BACKUP_OUTCOMES} ("
            " outcome_id bigint PRIMARY KEY,"
            " market_id bigint NOT NULL,"
            " action text NOT NULL,"
            " external_id text,"
            " is_winner boolean,"
            " resolution_source text,"
            " last_updated timestamptz,"
            " taken_at timestamptz NOT NULL DEFAULT now())"
        )
    )


async def _bank(session, plans: list[MarketPlan]) -> set[int]:
    """Bank every REOPEN board, commit, and return the ids whose bank matches the plan.

    ``ON CONFLICT DO NOTHING`` keeps the FIRST state ever banked, so a second
    apply after a restore re-banks nothing. The check below then compares that
    first bank with what this run planned from. A bank holding any other state
    would make the undo lie, so that board is not written.
    """
    await _ensure_backup_tables(session)
    for p in plans:
        await session.execute(
            text(
                f"INSERT INTO {BACKUP_MARKETS} (market_id, external_id, status, settled_at, "
                "resolution_gate) SELECT id, external_id, status, settled_at, "
                f"market_metadata->'{GATE_KEY}' FROM futures_markets WHERE id = :mid "
                "ON CONFLICT (market_id) DO NOTHING"
            ),
            {"mid": p.market_id},
        )
        for action, ids in (
            ("clear", [oid for oid, *_ in p.clear_legs]),
            ("promote", [oid for oid, *_ in p.promote_legs]),
        ):
            if not ids:
                continue
            await session.execute(
                text(
                    f"INSERT INTO {BACKUP_OUTCOMES} (outcome_id, market_id, action, "
                    "external_id, is_winner, resolution_source, last_updated) SELECT id, "
                    "market_id, :action, external_id, is_winner, resolution_source, "
                    "last_updated FROM futures_outcomes WHERE market_id = :mid "
                    "AND id = ANY(:ids) ON CONFLICT (outcome_id) DO NOTHING"
                ),
                {"mid": p.market_id, "ids": ids, "action": action},
            )
    await session.commit()

    good: set[int] = set()
    for p in plans:
        b = (
            await session.execute(
                text(
                    f"SELECT external_id, status, settled_at, resolution_gate "
                    f"FROM {BACKUP_MARKETS} WHERE market_id = :mid"
                ),
                {"mid": p.market_id},
            )
        ).first()
        if b is None or b.external_id != p.event_id or b.status != "resolved":
            continue
        if b.settled_at != p.settled_at or _gate_of(
            {GATE_KEY: b.resolution_gate}
        ) != p.before[GATE_KEY]:
            continue
        planned = {oid: ("clear", ext, w, s) for oid, ext, w, s in p.clear_legs}
        planned.update(
            {oid: ("promote", ext, w, s) for oid, ext, w, s, _pr in p.promote_legs}
        )
        if planned:
            banked = {
                int(r.outcome_id): (r.action, r.external_id, r.is_winner, r.resolution_source)
                for r in await session.execute(
                    text(
                        f"SELECT outcome_id, action, external_id, is_winner, "
                        f"resolution_source FROM {BACKUP_OUTCOMES} WHERE market_id = :mid"
                    ),
                    {"mid": p.market_id},
                )
            }
            if any(banked.get(oid) != want for oid, want in planned.items()):
                continue
        good.add(p.market_id)
    return good


# --- writes -----------------------------------------------------------------

_REOPEN = text(
    "UPDATE futures_markets SET status = 'open', settled_at = NULL, "
    f"market_metadata = market_metadata - '{GATE_KEY}' "
    "WHERE id = :mid AND source = 'polymarket' AND external_id = :ext "
    "AND status = 'resolved' AND settled_at = :settled_at "
    f"AND market_metadata->'{GATE_KEY}' = CAST(:gate AS jsonb)"
)

_CLEAR_LEG = text(
    "UPDATE futures_outcomes SET is_winner = NULL, resolution_source = NULL, "
    "last_updated = NOW() "
    "WHERE id = :oid AND market_id = :mid AND external_id = :ext "
    "AND is_winner IS NOT DISTINCT FROM :w AND resolution_source = :src"
)

_PROMOTE_LEG = text(
    f"UPDATE futures_outcomes SET resolution_source = '{SETTLEMENT_SOURCE}', "
    "last_updated = NOW() "
    "WHERE id = :oid AND market_id = :mid AND external_id = :ext "
    "AND is_winner = :w AND resolution_source = :src "
    "AND current_probability = CAST(:price AS numeric)"
)

_RESTORE_MARKET = text(
    "UPDATE futures_markets fm SET status = b.status, settled_at = b.settled_at, "
    "market_metadata = COALESCE(fm.market_metadata, '{}'::jsonb) "
    f"|| jsonb_build_object('{GATE_KEY}', b.resolution_gate) "
    f"FROM {BACKUP_MARKETS} b "
    "WHERE fm.id = b.market_id AND fm.id = :mid AND fm.source = 'polymarket' "
    "AND fm.external_id = b.external_id AND fm.status = 'open' "
    f"AND fm.settled_at IS NULL AND fm.market_metadata->'{GATE_KEY}' IS NULL"
)

_RESTORE_LEGS = text(
    "UPDATE futures_outcomes fo SET is_winner = b.is_winner, "
    "resolution_source = b.resolution_source, last_updated = b.last_updated "
    f"FROM {BACKUP_OUTCOMES} b "
    "WHERE fo.id = b.outcome_id AND fo.market_id = b.market_id AND b.market_id = :mid "
    "AND fo.external_id IS NOT DISTINCT FROM b.external_id "
    "AND ((b.action = 'clear' AND fo.is_winner IS NULL AND fo.resolution_source IS NULL) "
    f"OR (b.action = 'promote' AND fo.is_winner IS NOT DISTINCT FROM b.is_winner "
    f"AND fo.resolution_source = '{SETTLEMENT_SOURCE}'))"
)


async def _apply_one(session, p: MarketPlan) -> None:
    async with session.begin_nested():
        r = await session.execute(
            _REOPEN,
            {
                "mid": p.market_id,
                "ext": p.event_id,
                "settled_at": p.settled_at,
                "gate": json.dumps(p.before[GATE_KEY]),
            },
        )
        if r.rowcount != 1:
            raise _Drift(f"market {p.market_id} parent changed under the run")
        for oid, ext, w, src in p.clear_legs:
            r = await session.execute(
                _CLEAR_LEG, {"oid": oid, "mid": p.market_id, "ext": ext, "w": w, "src": src}
            )
            if r.rowcount != 1:
                raise _Drift(f"market {p.market_id} leg {oid} changed under the run")
        for oid, ext, w, src, price in p.promote_legs:
            r = await session.execute(
                _PROMOTE_LEG,
                {"oid": oid, "mid": p.market_id, "ext": ext, "w": w, "src": src,
                 "price": str(price)},
            )
            if r.rowcount != 1:
                raise _Drift(f"market {p.market_id} leg {oid} changed under the run")


async def _restore_one(session, market_id: int) -> str:
    """Return ``restored`` / ``noop`` / raise ``_Drift``."""
    b = (
        await session.execute(
            text(
                f"SELECT external_id, status, settled_at, resolution_gate "
                f"FROM {BACKUP_MARKETS} WHERE market_id = :mid"
            ),
            {"mid": market_id},
        )
    ).first()
    if b is None:
        return "not_banked"
    market, _legs = await _read_market(session, market_id)
    if (
        market is not None
        and market["status"] == b.status
        and market["settled_at"] == b.settled_at
        and market["gate"] == _gate_of({GATE_KEY: b.resolution_gate})
    ):
        return "noop"
    n_legs = (
        await session.execute(
            text(f"SELECT count(*) FROM {BACKUP_OUTCOMES} WHERE market_id = :mid"),
            {"mid": market_id},
        )
    ).scalar() or 0
    async with session.begin_nested():
        r = await session.execute(_RESTORE_MARKET, {"mid": market_id})
        if r.rowcount != 1:
            raise _Drift(f"market {market_id} is not in the AFTER state")
        if n_legs:
            r = await session.execute(_RESTORE_LEGS, {"mid": market_id})
            if r.rowcount != n_legs:
                raise _Drift(
                    f"market {market_id}: {r.rowcount} of {n_legs} banked legs in the AFTER state"
                )
    return "restored"


FetchEvent = Callable[[str], Awaitable[dict | None]]


def _selected(only: list[int] | None) -> list[tuple[int, str]]:
    if not only:
        return list(CANDIDATES)
    pinned = dict(CANDIDATES)
    unknown = [m for m in only if m not in pinned]
    if unknown:
        raise Refused(f"--only names {unknown}, which are not pinned candidates; refusing")
    return [(m, pinned[m]) for m in only]


async def run(
    session,
    *,
    mode: str,
    fetch_event: FetchEvent | None = None,
    only: list[int] | None = None,
) -> dict:
    """``mode`` is ``dry-run`` / ``apply`` / ``restore``."""
    selected = _selected(only)
    counts = {
        "candidates": len(selected),
        REOPEN: 0,
        NOOP: 0,
        SKIP_NO_WITNESS: 0,
        REFUSED: 0,
        "bank_mismatch": 0,
        "drift": 0,
        "written": 0,
        "restored": 0,
        "legs_cleared": 0,
        "legs_promoted": 0,
        "legs_preserved": 0,
    }
    rows: list[dict] = []

    if mode == "restore":
        for market_id, _event_id in selected:
            try:
                outcome = await _restore_one(session, market_id)
            except _Drift as exc:
                counts["drift"] += 1
                rows.append({"market_id": market_id, "restore": "drift", "reason": str(exc)})
                continue
            if outcome == "restored":
                counts["restored"] += 1
            rows.append({"market_id": market_id, "restore": outcome})
        await session.commit()
    else:
        if fetch_event is None:
            raise Refused("no venue reader; refusing")
        plans: list[MarketPlan] = []
        for candidate in selected:
            market, legs = await _read_market(session, candidate[0])
            fetch_error = None
            try:
                venue_raw = await fetch_event(candidate[1])
            except Exception as exc:  # 429 / 5xx / timeout: no evidence, no write
                venue_raw = None
                fetch_error = f"{type(exc).__name__}: {str(exc)[:80]}"
            plan = plan_market(candidate, market, legs, venue_raw)
            if fetch_error and plan.verdict == REFUSED and "venue unreadable" in plan.reason:
                plan.reason = f"venue unreadable ({fetch_error})"
            plans.append(plan)
        for p in plans:
            counts[p.verdict] += 1
            counts["legs_preserved"] += p.legs_preserved if p.verdict == REOPEN else 0
        # The read phase opened a transaction; end it before banking.
        await session.rollback()

        to_write = [p for p in plans if p.verdict == REOPEN]
        written_ids: set[int] = set()
        drifted: dict[int, str] = {}
        if mode == "apply" and to_write:
            good = await _bank(session, to_write)
            for p in to_write:
                if p.market_id not in good:
                    counts["bank_mismatch"] += 1
                    drifted[p.market_id] = "bank holds a different state; not written"
                    continue
                try:
                    await _apply_one(session, p)
                except _Drift as exc:
                    counts["drift"] += 1
                    drifted[p.market_id] = str(exc)
                    continue
                written_ids.add(p.market_id)
                counts["written"] += 1
                counts["legs_cleared"] += len(p.clear_legs)
                counts["legs_promoted"] += len(p.promote_legs)
            await session.commit()
        for p in plans:
            d = p.as_dict()
            if mode == "apply" and p.verdict == REOPEN:
                d["written"] = p.market_id in written_ids
                if p.market_id in drifted:
                    d["not_written_because"] = drifted[p.market_id]
            rows.append(d)

    # Read back from disk rather than trusting rowcount (gotcha #53).
    now = {}
    for market_id, _event_id in selected:
        market, legs = await _read_market(session, market_id)
        now[str(market_id)] = None if market is None else {
            "status": market["status"],
            "settled_at": None if market["settled_at"] is None else str(market["settled_at"]),
            GATE_KEY: market["gate"],
            "legs_graded": sum(1 for x in legs if x["is_winner"] is not None),
            "legs": len(legs),
        }
    return {"mode": mode, "counts": counts, "markets": rows, "now": now}


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_true")
    group.add_argument("--restore", action="store_true")
    ap.add_argument(
        "--only", type=int, action="append", help="market id (repeatable); must be pinned"
    )
    args = ap.parse_args()
    mode = "restore" if args.restore else ("apply" if args.apply else "dry-run")

    try:
        refuse_unless_production(dict(os.environ))
        _selected(args.only)
    except Refused as exc:
        print(f"REFUSED: {exc}")
        return 2

    from app.services.polymarket_api import PolymarketAPIService
    from app.tasks.base import get_task_session

    service = PolymarketAPIService()

    async def fetch(event_id: str) -> dict | None:
        await asyncio.sleep(0.2)
        return await service.get_event_by_id(event_id)

    try:
        async with get_task_session() as session:
            try:
                out = await run(session, mode=mode, fetch_event=fetch, only=args.only)
            except Refused as exc:
                await session.rollback()
                print(f"REFUSED: {exc}")
                return 2
    finally:
        await service.close()
    print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    if mode == "apply" and out["counts"]["written"]:
        print(
            "UNDO: heroku run:detached -a bainluck -- python3 "
            "scripts/repair_polymarket_false_parent_settlements_10182.py --restore"
        )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
