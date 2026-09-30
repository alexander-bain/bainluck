"""#9484 — an open Polymarket contract streams its price whatever its event's phase.

The Polymarket socket subscribes from events that are ``live``, ``scheduled``
within 6 h, or recently ``suspended`` (``polymarket_ws._slate_event_window``).
Every market outside that join — a standalone future or prop with no
``event_id``, or a game market whose event is days away — never reached the
wire, so its stored price moved only when the REST poll's rotating cursor came
round, and the #9484 post-commit market invalidation had nothing to say about
it. Alex's ruling on #9484: market lifecycle, not game phase, decides
streaming; Codex's 2026-09-29 05:26Z decision: every open contract is eligible,
over the existing 500-asset sharding, with no demand ranking that excludes one.

Eligibility is the contract's own unsettled truth, never a kickoff horizon:

- the market is not ``resolved`` (NULL fails OPEN — the column is nullable in
  production and a plain ``!=`` drops a NULL, as ``_slate_market_filter``
  says) and carries no ``settled_at``;
- the leg is not graded: ``is_winner IS NOT TRUE`` and no
  ``resolution_source``. Not ``is_winner IS NULL`` — the column defaults to
  FALSE server-side, so a NULL test would drop ungraded legs a raw INSERT wrote.

**Prices only, never settlement.** These tokens join the price maps and ride a
second ``PolymarketWebSocket`` with no ``on_resolved``: the settlement maps
(``condition_to_market`` / ``outcomes_by_market``) stay the linked slate's.

**Persisted tokens only, no catalogue read.** A market's own book is
``market_metadata.clob_token_ids``; a field row's per-outcome books are
``clob_yes_token_by_outcome`` (``polymarket_token_topup``). Nothing here calls
Gamma, so the admission read can never delay the game socket or spend the
top-up's budget. A market with neither key is COUNTED
(``open_contract_markets_without_tokens``), never silently dropped from the
story; the ingest stamp reaches it on its rotation.

``WS_OPEN_CONTRACT_PRICES=0`` (both venues) or
``POLYMARKET_WS_OPEN_CONTRACT_PRICES=0`` (this one) turns the arm off at the
next recycle with no deploy — the undo line.
"""

import json
import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Optional

from app.tasks.polymarket_token_topup import OUTCOME_TOKEN_METADATA_KEY

#: Concurrent handshakes (and initial book dumps) the open-contract client
#: allows. ~70 shards dialled at once would hold ~70 dumps of up to
#: MAX_MESSAGE_BYTES in memory together; four at a time bounds that to four.
OPEN_CONTRACT_MAX_CONCURRENT_HANDSHAKES = int(
    os.getenv("POLYMARKET_WS_OPEN_CONTRACT_HANDSHAKES", "4")
)

#: Received-but-unread messages per open-contract connection (the library
#: default is 16). Standalone books tick rarely; a small queue keeps the
#: per-shard worst case near one message instead of seventeen.
OPEN_CONTRACT_MAX_QUEUE = 4

#: Rows per flush transaction. Each chunk commits and publishes on its own, so
#: a failed chunk costs only its rows (they stay buffered for the next flush).
FLUSH_CHUNK_ROWS = 500

#: Open-contract chunks one periodic flush writes after every linked row. The
#: rest stay in the buffer — nothing is dropped — and go first next time,
#: because the buffer is drained oldest-dirty first. Bounds how long a flood of
#: standalone quotes can hold the next linked quote behind it.
OPEN_FLUSH_CHUNKS_PER_FLUSH = 2


#: Markets per leg read. Small enough that the planner walks the market_id
#: index (see `open_contract_outcomes_stmt`), large enough that ~21,000 open
#: markets are about ten statements.
OUTCOME_READ_MARKETS = 2_000


def open_contract_prices_enabled() -> bool:
    """False when either undo flag is set to ``0``."""
    return all(
        os.getenv(name, "1").strip() != "0"
        for name in ("WS_OPEN_CONTRACT_PRICES", "POLYMARKET_WS_OPEN_CONTRACT_PRICES")
    )


def _open_market_clauses() -> list:
    from sqlalchemy import or_

    from app.models.models import FuturesMarket

    return [
        FuturesMarket.source == "polymarket",
        or_(
            FuturesMarket.status.is_(None),
            FuturesMarket.status != "resolved",
        ),
        FuturesMarket.settled_at.is_(None),
    ]


def open_contract_markets_stmt():
    """Every unsettled Polymarket market with its persisted token keys.

    ``(market_id, clob_token_ids, clobTokenIds, clob_yes_token_by_outcome)`` —
    the three keys only, never the whole metadata blob. No event join and no
    event window: that is the point.
    """
    from sqlalchemy import select

    from app.models.models import FuturesMarket

    meta = FuturesMarket.market_metadata
    return select(
        FuturesMarket.id,
        meta["clob_token_ids"],
        meta["clobTokenIds"],
        meta[OUTCOME_TOKEN_METADATA_KEY],
    ).where(*_open_market_clauses())


def open_contract_outcomes_stmt(market_ids: Iterable[int] = ()):
    """Every leg of those markets, in id order, with whether it is graded.

    ``(outcome_id, market_id, external_id, graded)``. ALL legs, graded ones
    included, because a market's tokens pair with its legs by position; the
    graded ones are dropped after pairing.

    Addressed by market id (one array bind, ``= ANY``) and read in chunks of
    ``OUTCOME_READ_MARKETS`` (``open_contract_outcome_stmts``). Production
    plans, 2026-09-29, plan-only: the join form re-applied the market predicate
    and planned a sequential scan of all ~4.8M outcomes on every recycle; one
    21,000-id array planned the same scan; 2,000 ids plan a bitmap scan of
    ``ix_futures_outcomes_market_id``.
    """
    from sqlalchemy import Integer, any_, bindparam, or_, select
    from sqlalchemy.dialects.postgresql import ARRAY

    from app.models.models import FuturesOutcome

    graded = or_(
        FuturesOutcome.is_winner.is_(True),
        FuturesOutcome.resolution_source.isnot(None),
    )
    ids = bindparam("market_ids", value=list(market_ids), type_=ARRAY(Integer))
    return (
        select(
            FuturesOutcome.id,
            FuturesOutcome.market_id,
            FuturesOutcome.external_id,
            graded,
        )
        .where(FuturesOutcome.market_id == any_(ids))
        .order_by(FuturesOutcome.id)
    )


def open_contract_outcome_stmts(market_ids: Iterable[int]) -> list:
    """The leg reads for these markets, ``OUTCOME_READ_MARKETS`` per statement.

    Chunked by MARKET, so every leg of one market comes back in one statement,
    in id order — the order the token pairing reads.
    """
    ids = list(market_ids)
    size = max(1, int(OUTCOME_READ_MARKETS))
    return [
        open_contract_outcomes_stmt(ids[i:i + size])
        for i in range(0, len(ids), size)
    ]


def _token_list(raw: Any) -> list[str]:
    """``clob_token_ids`` as stored: a list, or (legacy) its JSON string."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            return []
    if not isinstance(raw, list):
        return []
    return [str(t) for t in raw if t is not None and str(t)]


@dataclass
class OpenContractAdmission:
    """What the open-contract socket subscribes, and how its ticks attribute."""

    asset_to_outcome: dict[str, int] = field(default_factory=dict)
    asset_to_market: dict[str, int] = field(default_factory=dict)
    #: #9736 — token → ``(outcome_id, market_id)`` of every OTHER market's leg
    #: that names a token already owned (by an earlier open market, or by the
    #: game socket). Price-only fan-out: the token is subscribed once, and each
    #: of its ticks is buffered on the owner AND on every mirror.
    asset_mirrors: dict[str, list[tuple[int, int]]] = field(default_factory=dict)
    #: #9733 follow-on — leg → the other leg of its binary, both admitted
    #: (``complement_pairs``). A price accepted for one also prices the other.
    complement_of: dict[int, int] = field(default_factory=dict)
    counts: dict[str, int] = field(
        default_factory=lambda: {
            "markets": 0,
            "markets_admitted": 0,
            "markets_on_game_slate": 0,
            "markets_without_tokens": 0,
            "markets_unpaired": 0,
            "legs_graded": 0,
            "assets_already_streaming": 0,
            "assets_duplicate": 0,
            "legs_mirrored": 0,
            "legs_mirrored_by_condition": 0,
            "legs_complemented": 0,
        }
    )

    def mirrored_outcomes(self) -> dict[int, int]:
        """``outcome_id → market_id`` for every mirror leg."""
        return {
            oid: mid
            for legs in self.asset_mirrors.values()
            for oid, mid in legs
        }


def contract_key(ext: str) -> Optional[tuple[str, int]]:
    """``(condition id, CLOB token index)`` a leg's ``external_id`` names.

    ``0xabc`` and ``0xabc_yes`` are both token 0 of condition ``0xabc``;
    ``0xabc_no`` and ``0xabc_side1`` are token 1 (``_token_index``, the rule the
    pairing already orders by). ``None`` for anything that is not a Polymarket
    condition id or whose suffix names no token, so it can never be matched.
    """
    from app.tasks.polymarket_ws import _token_index

    index = _token_index(ext or "")
    if index is None:
        return None
    condition = ext.split("_", 1)[0]
    if not condition.startswith("0x") or len(condition) < 3:
        return None
    return condition, index


def tokens_by_contract(
    asset_to_outcome: Mapping[str, int], ext_by_outcome: Mapping[int, str]
) -> dict[str, str]:
    """``contract_key → token`` for every paired leg whose id names a contract.

    Keys are ``"<condition>:<index>"`` strings so the map stays plain data.
    """
    out: dict[str, str] = {}
    for token, oid in asset_to_outcome.items():
        key = contract_key(ext_by_outcome.get(oid, ""))
        if key is not None:
            out.setdefault(f"{key[0]}:{key[1]}", token)
    return out


def open_contract_asset_map(
    market_rows: Iterable[tuple],
    outcome_rows: Iterable[tuple],
    taken_assets: Iterable[str] = (),
    excluded_market_ids: Iterable[int] = (),
    taken_tokens_by_contract: Optional[Mapping[str, str]] = None,
) -> OpenContractAdmission:
    """Token → leg for every open contract the game socket does not carry.

    Pairing, per market:

    - its own ``clob_token_ids`` when their COUNT equals its leg count, paired
      in CLOB token order (``legs_in_token_order``, #8403);
    - else its persisted per-outcome tokens (``clob_yes_token_by_outcome``),
      attributed directly by outcome id;
    - else it is counted, not guessed: ``markets_unpaired`` when tokens exist
      but cannot be paired one-to-one (a positional zip there would put one
      leg's price on another), ``markets_without_tokens`` when none are stored.

    A market on the game slate (``excluded_market_ids``) is skipped and
    counted. A token the game socket already carries (``taken_assets``) or a
    second market also names is subscribed ONCE and never re-owned, but the
    leg that names it is MIRRORED (``asset_mirrors``) so the token's ticks
    reach it too. #9736: the NLDS board's Cubs leg and the standalone "Will
    the Cubs advance" binary name one Polymarket condition; one owner meant
    the board's leg sat at its pre-game price while the binary streamed. The
    two legs are the same contract, so they carry the same price.

    A mirror is only ever ANOTHER market's leg: two legs of one market naming
    one token is a pairing defect, not a shared contract, and the second is
    still dropped (``assets_duplicate``).

    #9736 repair: a market with NO usable tokens (``markets_without_tokens`` /
    ``markets_unpaired``) can still name a contract by its legs' ids. The live
    NLDS board 60087232 stores no token key at all, so the token mirror above
    never met it; its Cubs leg is ``0x52f9…dc27`` — condition ``0x52f9…dc27``,
    token 0 — the very contract the standalone binary's ``0x52f9…dc27_yes``
    leg streams. Such a leg mirrors the token of the leg, in another market,
    whose id names the same ``(condition, token index)`` (``contract_key``):
    an open owner here, or the game socket's (``taken_tokens_by_contract``).
    Matched by id, never by position, so a shape it cannot read stays unpriced.
    """
    from app.tasks.polymarket_ws import legs_in_token_order

    out = OpenContractAdmission()
    counts = out.counts
    taken = set(taken_assets)
    excluded = set(excluded_market_ids)

    legs_by_market: dict[int, list[tuple[int, str]]] = {}
    graded: set[int] = set()
    ext_by_outcome: dict[int, str] = {}
    for outcome_id, market_id, ext, is_graded in outcome_rows:
        legs_by_market.setdefault(market_id, []).append((outcome_id, ext or ""))
        ext_by_outcome[outcome_id] = ext or ""
        if is_graded:
            graded.add(outcome_id)
    #: markets with no usable tokens, for the by-condition pass below
    tokenless: list[int] = []

    for market_id, tokens_a, tokens_b, by_outcome in market_rows:
        counts["markets"] += 1
        if market_id in excluded:
            counts["markets_on_game_slate"] += 1
            continue
        legs = legs_by_market.get(market_id, [])
        tokens = _token_list(tokens_a) or _token_list(tokens_b)

        pairs: list[tuple[str, int]]
        if tokens and len(tokens) == len(legs):
            pairs = [
                (token, oid)
                for token, (oid, _ext) in zip(tokens, legs_in_token_order(legs))
            ]
        elif isinstance(by_outcome, Mapping) and by_outcome:
            pairs = [
                (str(by_outcome[str(oid)]), oid)
                for oid, _ext in legs
                if by_outcome.get(str(oid))
            ]
        elif tokens:
            counts["markets_unpaired"] += 1
            tokenless.append(market_id)
            continue
        else:
            counts["markets_without_tokens"] += 1
            tokenless.append(market_id)
            continue

        admitted = False
        for token, outcome_id in pairs:
            if outcome_id in graded:
                counts["legs_graded"] += 1
            elif token in taken or token in out.asset_to_outcome:
                shared_across_markets = (
                    token in taken or out.asset_to_market[token] != market_id
                )
                counts[
                    "assets_already_streaming" if token in taken
                    else "assets_duplicate"
                ] += 1
                mirrors = out.asset_mirrors.setdefault(token, [])
                if shared_across_markets and all(
                    oid != outcome_id for oid, _mid in mirrors
                ):
                    mirrors.append((outcome_id, market_id))
                    counts["legs_mirrored"] += 1
                    admitted = True
                if not mirrors:
                    del out.asset_mirrors[token]
            else:
                out.asset_to_outcome[token] = outcome_id
                out.asset_to_market[token] = market_id
                admitted = True
        if admitted:
            counts["markets_admitted"] += 1

    if tokenless:
        by_contract = dict(taken_tokens_by_contract or {})
        for key, token in tokens_by_contract(
            out.asset_to_outcome, ext_by_outcome
        ).items():
            by_contract.setdefault(key, token)
        for market_id in tokenless:
            admitted = False
            seen: set[str] = set()
            for outcome_id, ext in legs_by_market.get(market_id, []):
                key = contract_key(ext)
                if outcome_id in graded or key is None:
                    continue
                token = by_contract.get(f"{key[0]}:{key[1]}")
                if token is None or out.asset_to_market.get(token) == market_id:
                    continue
                if token in seen:  # two legs of one market, one contract
                    counts["assets_duplicate"] += 1
                    continue
                seen.add(token)
                mirrors = out.asset_mirrors.setdefault(token, [])
                if all(oid != outcome_id for oid, _mid in mirrors):
                    mirrors.append((outcome_id, market_id))
                    counts["legs_mirrored"] += 1
                    counts["legs_mirrored_by_condition"] += 1
                    admitted = True
            if admitted:
                counts["markets_admitted"] += 1

    out.complement_of = complement_pairs(
        legs_by_market,
        set(out.asset_to_outcome.values()) | set(out.mirrored_outcomes()),
        graded,
        excluded,
    )
    counts["legs_complemented"] = len(out.complement_of)
    return out


def complement_pairs(
    legs_by_market: Mapping[int, list[tuple[int, str]]],
    admitted: set[int],
    graded: set[int],
    excluded: set[int] = frozenset(),
) -> dict[int, int]:
    """``leg → other leg`` for every open market that is one binary contract.

    A market qualifies only when it has exactly two legs, and they are token 0
    and token 1 of the same condition (``contract_key``). Both legs must be
    admitted to this arm and neither graded. Two tokens of one condition pay
    out 1 between them, so either price fixes the other. That makes this a
    structural test, not a guess from names.

    #9733 follow-on. Each tick priced only its own token's leg. A leg whose
    next quote was refused (a wide book) or never came kept its old number
    while its sibling moved. Measured 2026-09-30 13:3xZ: 29 of 7,883 streamed
    binaries stored a pair more than 10 points from 100. Specimens: George
    Kittle 524.5+ receiving yards, market 61352683, served Yes 77% / No 10%
    after a 20-share No sell at 0.10 (venue 76.5 / 23.5); HOOD $125 week
    high, market 62403481, stored Yes 0.815 / No 0.55.

    Anything else (a field board, a market on the game slate, a leg this arm
    does not carry, a suffix naming no token) has no complement. Those legs
    are priced exactly as before.
    """
    out: dict[int, int] = {}
    for market_id, legs in legs_by_market.items():
        if market_id in excluded or len(legs) != 2:
            continue
        (a, ext_a), (b, ext_b) = legs
        key_a, key_b = contract_key(ext_a), contract_key(ext_b)
        if key_a is None or key_b is None or key_a[0] != key_b[0]:
            continue
        if {key_a[1], key_b[1]} != {0, 1}:
            continue
        if a in graded or b in graded or a not in admitted or b not in admitted:
            continue
        out[a] = b
        out[b] = a
    return out


def plan_flush_chunks(
    outcome_ids: Iterable[int],
    open_outcome_ids: "set[int] | frozenset[int]",
    chunk_rows: int = FLUSH_CHUNK_ROWS,
    open_chunk_limit: Optional[int] = OPEN_FLUSH_CHUNKS_PER_FLUSH,
    complement_of: Optional[Mapping[int, int]] = None,
) -> list[list[int]]:
    """The flush's transactions: every linked row first, then open rows.

    ``outcome_ids`` in buffer order (oldest-dirty first). Linked rows are all
    written; open rows are capped at ``open_chunk_limit`` chunks (None = all,
    for the final drain). Rows past the cap are simply not planned — they stay
    in the buffer, keep their place at its head, and are planned next flush.

    CERT-3868 repair (``9733-ATOMIC-COMPLEMENT-FLUSH``). ``complement_of``
    (``complement_pairs``) ties the two legs of one binary together. When
    both are buffered they are one unit: planned into the SAME chunk, at the
    first leg's place, or deferred together. A chunk is never split between
    them and the cap never admits one without the other. Before this, 999 rows
    ahead of a pair put leg 1000 in the second chunk and deferred leg 1001, so
    one side committed and was read while the other still held its old price.
    A unit that would overflow the current chunk starts the next one.
    """
    size = max(1, int(chunk_rows))
    complement_of = complement_of or {}
    order = list(outcome_ids)
    buffered = set(order)
    placed: set[int] = set()
    linked: list[list[int]] = []
    opened: list[list[int]] = []
    for oid in order:
        if oid in placed:
            continue
        unit = [oid]
        other = complement_of.get(oid)
        if other is not None and other in buffered and other not in placed:
            unit.append(other)
        placed.update(unit)
        is_open = any(o in open_outcome_ids for o in unit)
        (opened if is_open else linked).append(unit)

    def pack(units: list[list[int]]) -> list[list[int]]:
        packed: list[list[int]] = []
        for unit in units:
            if not packed or len(packed[-1]) + len(unit) > size:
                packed.append([])
            packed[-1].extend(unit)
        return packed

    chunks = pack(linked)
    open_chunks = pack(opened)
    if open_chunk_limit is not None:
        open_chunks = open_chunks[: max(0, int(open_chunk_limit))]
    return chunks + open_chunks
