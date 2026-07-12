#!/usr/bin/env python3
"""A4 (#1023) — Resolution-engine shadow-mode agreement audit.

Runs the A4 :class:`~app.services.resolution_engine.ResolutionEngine` against the
links that ALREADY exist in production and reports **agreement % per link-type**.
This is the "engine must EARN each link-type's ownership" gate: v1 ships in
SHADOW MODE — it writes nothing; it only measures whether the one engine, fed A2
grammar + A1 entity resolution, independently reproduces the links the current
per-mechanism code produced.

Link types measured:

* ``market_event``   — a game market's stored ``event_id`` vs the event the
  ticker/participant strategy proposes (the win-prob blend; must not regress the
  100% L1-L4 game matching).
* ``family``         — a grouped market's container (``group_id`` /
  ``polymarket_event_id`` / Kalshi series) vs the family key the container
  strategy emits (coverage: does the engine key every grouped market?).
* ``cross_source``   — Kalshi↔Polymarket same-question pairs the question
  strategy proposes vs the exact-normalized pairs the existing
  ``utils.cross_source_matching`` keys produce, over a mixed-source sample.

Data path: this reads production through the admin read-only ``/api/admin/db-query``
endpoint (needs ``ADMIN_TOKEN`` + ``BAINLUCK_API`` in the env — ``source
~/.claude/.env``). It resolves market/event names through the A1 registry by
pulling ONLY the aliases the sample references (one bounded query), so it
exercises real A1 resolution without dumping the whole alias table. When run
inside the backend a future ``--session`` mode can use a live AsyncSession; v1
uses the API path so it runs from anywhere.

Usage:
    source ~/.claude/.env
    python3 scripts/audit_resolution_engine.py                # default sample
    python3 scripts/audit_resolution_engine.py --limit 600
    python3 scripts/audit_resolution_engine.py --show-disagreements 20
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import date, datetime
from typing import Any, Optional
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.entity_registry import normalize_alias  # noqa: E402
from app.services.grammar_adapters import (  # noqa: E402
    ROLE_PARTICIPANT,
    annotate_stored_market,
)
from app.services.resolution_engine import (  # noqa: E402
    LINK_CROSS_SOURCE,
    LINK_FAMILY,
    LINK_MARKET_EVENT,
    ConceptSignature,  # noqa: F401  (kept for parity / future concept cell)
    EventSignature,
    MarketSignature,
    MatchUniverse,
    ResolutionEngine,
    TickerParticipantStrategy,
    build_signature,
    normalize_question,
)

API = os.environ.get("BAINLUCK_API", "https://api.bainluck.com")
TOKEN = os.environ.get("ADMIN_TOKEN", "")


# ---------------------------------------------------------------------------
# Read-only production access
# ---------------------------------------------------------------------------
def db_query(sql: str, limit: int = 1000) -> list[dict]:
    """Run a read-only SQL query via the admin endpoint; return list-of-dicts."""
    body = json.dumps({"sql": sql, "limit": limit}).encode()
    req = Request(
        f"{API}/api/admin/db-query",
        data=body,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=60) as resp:
            payload = json.load(resp)
    except HTTPError as exc:  # surface the server's reason instead of a bare 400
        detail = exc.read().decode(errors="replace")[:500]
        raise RuntimeError(f"db-query {exc.code}: {detail}\nSQL: {sql[:200]}") from None
    cols = payload["columns"]
    return [dict(zip(cols, row)) for row in payload["rows"]]


def _md(value: Any) -> dict:
    """market_metadata may come back as a dict or a JSON string."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return {}
    return {}


def _as_date(value: Any) -> Optional[date]:
    if not value:
        return None
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except ValueError:
            return None
    if isinstance(value, datetime):
        return value.date()
    return None


# ---------------------------------------------------------------------------
# Alias resolution (bounded — only the norms the sample references)
# ---------------------------------------------------------------------------
# The read-only db-query endpoint keyword-scans the WHOLE statement (including
# string literals) and 400s if a blocked keyword appears anywhere. A normalized
# market/outcome name can contain one ("...update...", "...create..."), so we
# only ever embed team-name norms (clean) and defensively drop any that still
# carry a blocked token — those simply count as unresolved.
_SQL_BLOCK_TOKENS = frozenset(
    {"insert", "update", "delete", "drop", "alter", "create", "truncate",
     "grant", "revoke", "exec", "merge", "into", "table"}
)


def _sql_safe(norm: str) -> bool:
    return not (_SQL_BLOCK_TOKENS & set(norm.split()))


def resolve_norms(norms: set[str]) -> dict[str, int]:
    """Resolve a set of normalized names → entity id via the A1 alias table.

    Deterministic best-match per norm: highest alias confidence, then lowest
    entity id (mirrors ``entity_registry.resolve_aliases``). Chunks the IN-list to
    stay under the endpoint's row cap. Only pass CLEAN team-name norms here.
    """
    norms = {n for n in norms if n and _sql_safe(n)}
    if not norms:
        return {}
    resolved: dict[str, tuple[float, int]] = {}
    chunk: list[str] = []

    def flush(batch: list[str]) -> None:
        if not batch:
            return
        in_list = ",".join("'" + n.replace("'", "''") + "'" for n in batch)
        rows = db_query(
            f"SELECT alias_norm, entity_id, confidence FROM entity_aliases "
            f"WHERE alias_norm IN ({in_list})",
            limit=1000,
        )
        for r in rows:
            n = r["alias_norm"]
            conf = float(r["confidence"]) if r["confidence"] is not None else 1.0
            eid = int(r["entity_id"])
            cur = resolved.get(n)
            if cur is None or (conf, -eid) > (cur[0], -cur[1]):
                resolved[n] = (conf, eid)

    for n in norms:
        chunk.append(n)
        if len(chunk) >= 300:
            flush(chunk)
            chunk = []
    flush(chunk)
    return {n: eid for n, (_c, eid) in resolved.items()}


# ---------------------------------------------------------------------------
# Link-type 1: market → event
# ---------------------------------------------------------------------------
def audit_market_event(limit: int, show: int) -> dict:
    rows = db_query(
        "SELECT fm.source, fm.external_id, fm.name, fm.market_metadata, "
        "fm.event_id, e.home_team_name, e.away_team_name, e.commence_time "
        "FROM futures_markets fm JOIN events e ON e.id = fm.event_id "
        "WHERE fm.event_id IS NOT NULL AND fm.source IN ('kalshi','polymarket') "
        "ORDER BY fm.id DESC",
        limit=limit,
    )

    # Build annotations first so we know which norms to resolve.
    prepared = []
    norms: set[str] = set()
    for r in rows:
        md = _md(r.get("market_metadata"))
        ann = annotate_stored_market(
            source=r["source"],
            external_id=r["external_id"],
            name=r.get("name") or "",
            market_metadata=md,
        )
        home_n = normalize_alias(r.get("home_team_name") or "")
        away_n = normalize_alias(r.get("away_team_name") or "")
        # Only resolve PARTICIPANT norms (team/person names) + event team names.
        # Outcome-name norms are prop junk that never resolves and can trip the
        # endpoint's keyword scan.
        for m in ann.mentions:
            if m.role == ROLE_PARTICIPANT:
                norms.add(m.norm)
        norms.add(home_n)
        norms.add(away_n)
        prepared.append((r, ann, home_n, away_n))

    resolver = resolve_norms(norms)

    engine = ResolutionEngine([TickerParticipantStrategy()])
    agree = 0
    classes: Counter = Counter()
    per_source_total: Counter = Counter()
    per_source_agree: Counter = Counter()
    disagreements = []

    for r, ann, home_n, away_n in prepared:
        sig = build_signature(
            ann,
            external_id=r["external_id"],
            event_date=_as_date(r.get("commence_time")),
            resolved=resolver,
        )
        # Event signature keyed the SAME way (resolved entity ids where possible).
        ev_participants = frozenset(
            f"e:{resolver[n]}" if n in resolver else f"n:{n}"
            for n in (home_n, away_n)
            if n
        )
        event = EventSignature(
            event_id=int(r["event_id"]),
            participants=ev_participants,
            event_date=_as_date(r.get("commence_time")),
        )
        links = engine.resolve(sig, MatchUniverse(events=[event]))
        proposed = {l.right for l in links if l.link_type == LINK_MARKET_EVENT}
        per_source_total[r["source"]] += 1
        if str(r["event_id"]) in proposed:
            agree += 1
            per_source_agree[r["source"]] += 1
        else:
            # Classify why the engine did NOT reproduce the stored link.
            if not sig.is_game:
                cls = "no_two_participants"
            elif len(ev_participants) < 2:
                cls = "event_missing_team_name"
            elif sig.participants != ev_participants:
                unresolved = [p for p in sig.participants if p.startswith("n:")]
                cls = "unresolved_participant" if unresolved else "participant_key_mismatch"
            else:
                cls = "date_window"
            classes[cls] += 1
            if len(disagreements) < show:
                disagreements.append(
                    {
                        "source": r["source"],
                        "external_id": r["external_id"],
                        "name": (r.get("name") or "")[:60],
                        "event_teams": f"{r.get('home_team_name')} / {r.get('away_team_name')}",
                        "market_participants": sorted(sig.participants),
                        "event_participants": sorted(ev_participants),
                        "class": cls,
                    }
                )

    total = len(prepared)
    per_source = {
        src: {
            "total": per_source_total[src],
            "agree": per_source_agree[src],
            "rate": per_source_agree[src] / per_source_total[src]
            if per_source_total[src]
            else 0.0,
        }
        for src in per_source_total
    }
    return {
        "link_type": LINK_MARKET_EVENT,
        "total": total,
        "agree": agree,
        "rate": (agree / total) if total else 0.0,
        "per_source": per_source,
        "disagreement_classes": dict(classes),
        "samples": disagreements,
    }


# ---------------------------------------------------------------------------
# Link-type 2: family / container coverage
# ---------------------------------------------------------------------------
def audit_family(limit: int) -> dict:
    rows = db_query(
        "SELECT source, external_id, group_id, market_metadata "
        "FROM futures_markets WHERE group_id IS NOT NULL "
        "AND source IN ('kalshi','polymarket') ORDER BY id DESC",
        limit=limit,
    )
    engine = ResolutionEngine()
    keyed = 0
    total = len(rows)
    for r in rows:
        md = _md(r.get("market_metadata"))
        ann = annotate_stored_market(
            source=r["source"], external_id=r["external_id"], market_metadata=md
        )
        sig = build_signature(ann, external_id=r["external_id"])
        links = engine.resolve(sig, MatchUniverse())
        if any(l.link_type == LINK_FAMILY for l in links):
            keyed += 1
    return {
        "link_type": LINK_FAMILY,
        "total": total,
        "keyed": keyed,
        "rate": (keyed / total) if total else 0.0,
        "note": "coverage: fraction of grouped markets the container strategy assigns a family key",
    }


# ---------------------------------------------------------------------------
# Link-type 3: cross-source pairs (vs existing normalized-question keys)
# ---------------------------------------------------------------------------
def audit_cross_source(limit: int) -> dict:
    rows = db_query(
        "SELECT source, external_id, name, market_type "
        "FROM futures_markets WHERE source IN ('kalshi','polymarket') "
        "AND status = 'open' AND llm_sport_category IN "
        "('politics','economics','entertainment','tech','culture','health') "
        "ORDER BY volume_24h DESC NULLS LAST",
        limit=limit,
    )
    sigs = [
        MarketSignature(
            source=r["source"],
            external_id=r["external_id"],
            market_type=r.get("market_type"),
            question_norm=normalize_question(r.get("name") or ""),
        )
        for r in rows
        if (r.get("name") or "").strip()
    ]
    # Ground truth: exact-normalized-question keys shared across the two sources
    # (the mechanism utils.cross_source_matching keys on).
    by_norm: dict[str, set[str]] = {}
    for s in sigs:
        if s.question_norm:
            by_norm.setdefault(s.question_norm, set()).add(s.source)
    truth_pairs = {n for n, srcs in by_norm.items() if {"kalshi", "polymarket"} <= srcs}

    engine = ResolutionEngine()
    universe = MatchUniverse(markets=sigs)
    engine_pair_norms: set[str] = set()
    for s in sigs:
        for l in engine.resolve(s, universe):
            if l.link_type == LINK_CROSS_SOURCE:
                engine_pair_norms.add(l.evidence.get("question_norm", ""))
    engine_pair_norms.discard("")

    reproduced = len(truth_pairs & engine_pair_norms)
    return {
        "link_type": LINK_CROSS_SOURCE,
        "sample_markets": len(sigs),
        "truth_pairs": len(truth_pairs),
        "engine_pairs": len(engine_pair_norms),
        "reproduced": reproduced,
        "rate": (reproduced / len(truth_pairs)) if truth_pairs else 1.0,
        "note": "reproduction of exact-normalized cross-source pairs (near-match paraphrase pass excluded in v1)",
    }


# ---------------------------------------------------------------------------
# A5 (#1024): per-card MMA association — the tournament-completeness cells.
# ---------------------------------------------------------------------------
def audit_mma_card_association(limit: int = 400) -> dict:
    """Per UFC card (grouped by the Kalshi fight ticker's date-token), report
    how many bouts are (a) linked to an Event and (b) MULTI-SOURCE — the event's
    ``win_probability_sources`` blend carries a Kalshi or Polymarket reading, not
    just the Odds API ``betting`` line. This is the A5 acceptance made countable:
    the whole point is upcoming fights gaining cross-source blend coverage.

    Read-only. Uses the shared ``card_token`` grammar so a "card" here is the
    exact same date-token the UFC card page groups on.
    """
    from app.utils.event_ufc import ufc_card_token

    rows = db_query(
        "SELECT fm.external_id, fm.name, fm.event_id, "
        "e.status AS event_status, e.commence_time, "
        "e.win_probability_sources AS wps "
        "FROM futures_markets fm "
        "LEFT JOIN events e ON e.id = fm.event_id "
        "WHERE fm.source = 'kalshi' AND lower(fm.external_id) LIKE 'kxufcfight-%' "
        "ORDER BY e.commence_time DESC NULLS LAST",
        limit=limit,
    )

    cards: dict[str, dict] = {}
    for r in rows:
        token = ufc_card_token(r["external_id"])
        if not token:
            continue
        c = cards.setdefault(
            token,
            {"fights": 0, "linked": 0, "kalshi": 0, "poly": 0, "multi": 0,
             "commence": r.get("commence_time")},
        )
        c["fights"] += 1
        if r.get("event_id"):
            c["linked"] += 1
        wps = r.get("wps")
        if isinstance(wps, str):
            try:
                wps = json.loads(wps.replace("'", '"'))
            except Exception:
                wps = {}
        wps = wps or {}
        has_k = "kalshi" in wps
        has_p = "polymarket" in wps
        if has_k:
            c["kalshi"] += 1
        if has_p:
            c["poly"] += 1
        if has_k or has_p:
            c["multi"] += 1

    total_fights = sum(c["fights"] for c in cards.values())
    total_linked = sum(c["linked"] for c in cards.values())
    total_multi = sum(c["multi"] for c in cards.values())
    return {
        "cards": cards,
        "total_cards": len(cards),
        "total_fights": total_fights,
        "total_linked": total_linked,
        "total_multi": total_multi,
        "link_rate": (total_linked / total_fights) if total_fights else 0.0,
        "multi_rate": (total_multi / total_fights) if total_fights else 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--show-disagreements", type=int, default=12)
    parser.add_argument(
        "--mma-cards", action="store_true",
        help="Only run the A5 per-card MMA association table.",
    )
    args = parser.parse_args()

    if not TOKEN:
        print("ERROR: ADMIN_TOKEN not set. Run: source ~/.claude/.env", file=sys.stderr)
        return 2

    if args.mma_cards:
        mma = audit_mma_card_association(args.limit)
        print("=" * 72)
        print("A5 (#1024) — PER-CARD MMA ASSOCIATION (tournament-completeness cells)")
        print("=" * 72)
        print(f"{'card (date-token)':20} {'fights':>7} {'linked':>7} "
              f"{'kalshi':>7} {'poly':>6} {'multi-source':>13}")
        for token, c in sorted(
            mma["cards"].items(),
            key=lambda kv: (kv[1]["commence"] or ""), reverse=True,
        ):
            print(f"{token:20} {c['fights']:>7} {c['linked']:>7} "
                  f"{c['kalshi']:>7} {c['poly']:>6} {c['multi']:>13}")
        print("-" * 72)
        print(f"{'TOTAL':20} {mma['total_fights']:>7} {mma['total_linked']:>7} "
              f"{'':>7} {'':>6} {mma['total_multi']:>13}")
        print(f"\nlink rate  : {mma['total_linked']}/{mma['total_fights']} "
              f"= {mma['link_rate']*100:.1f}%")
        print(f"multi-source rate (kalshi|poly in blend): {mma['total_multi']}/"
              f"{mma['total_fights']} = {mma['multi_rate']*100:.1f}%")
        return 0

    print("=" * 72)
    print("A4 RESOLUTION ENGINE — SHADOW-MODE AGREEMENT (no writes, no cutover)")
    print("=" * 72)

    me = audit_market_event(args.limit, args.show_disagreements)
    print(f"\n[{me['link_type']}]  agreement {me['agree']}/{me['total']} "
          f"= {me['rate']*100:.1f}%")
    for src, st in sorted(me["per_source"].items()):
        print(f"  by source: {src:11} {st['agree']}/{st['total']} = {st['rate']*100:.1f}%")
    if me["disagreement_classes"]:
        print("  disagreement classes:")
        for cls, n in sorted(me["disagreement_classes"].items(), key=lambda x: -x[1]):
            print(f"    {cls:28} {n}")
    for d in me["samples"]:
        print(f"    - [{d['class']}] {d['source']} {d['external_id']}: "
              f"mkt={d['market_participants']} ev={d['event_participants']}")

    fam = audit_family(args.limit)
    print(f"\n[{fam['link_type']}]  coverage {fam['keyed']}/{fam['total']} "
          f"= {fam['rate']*100:.1f}%")
    print(f"  {fam['note']}")

    xs = audit_cross_source(args.limit)
    print(f"\n[{xs['link_type']}]  reproduced {xs['reproduced']}/{xs['truth_pairs']} "
          f"= {xs['rate']*100:.1f}%  "
          f"(sample={xs['sample_markets']} markets, engine_pairs={xs['engine_pairs']})")
    print(f"  {xs['note']}")

    print("\n" + "=" * 72)
    print("SUMMARY (shadow — engine EARNS ownership as each rate proves out):")
    print(f"  market_event : {me['rate']*100:.1f}%  (n={me['total']})")
    print(f"  family       : {fam['rate']*100:.1f}%  (n={fam['total']})")
    print(f"  cross_source : {xs['rate']*100:.1f}%  (truth_pairs={xs['truth_pairs']})")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
