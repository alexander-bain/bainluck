"""#989 CLOB authoritative re-resolve — the writing drain (verify-then-write).

Conforms to the BINDING mapper spec `.claude/handoff/clob_mapper_spec.md`
(Fable, 2026-07-06). The curve-dropped cohort (pass2_loser / all_losers) was
excluded from the published calibration curve (#754-curve/#116) because it was
'resolved' by heuristics with a 0% win rate — i.e. UNDER-GRADED (both sides
False). This module re-resolves those markets AUTHORITATIVELY via the CLOB API
and writes the real `is_winner` with `resolution_source='clob_authoritative'`, a
NEW distinct source that re-admits them to the curve (not in the #116 exclusion
list) and makes the whole cohort revertible in one predicate.

## Source of truth
CLOB `GET /markets/{condition_id}` -> `tokens[]: {token_id, outcome, winner}`.
`condition_id` == our `FuturesMarket.external_id`. All-tokens-`winner=false`
(or !=1 winner) = VOID -> curve-excluded, counted, never forced.

## Mapping by shape (classify FIRST, map SECOND) — per the binding spec
- **rule 1 binary yes/no props**: CLOB tokens {Yes,No} + our outcomes {Yes,No}
  -> direct case-insensitive label map. (resolved_direct)
- **rule 3 totals**: CLOB tokens {Over,Under}; if our names carry the direction
  ("Over 2.5"/"Under 2.5") -> direction-prefix map (resolved_direct). If our
  names are plain Yes/No (line not stored) -> NOT hand-derived -> ambiguous.
- **rule 2 moneyline / rule 4a spread with team-name outcomes**: CLOB winning
  token is a TEAM/PLAYER name -> match to our team-name outcome via normalized
  equality / conservative near-match. NEVER naive substring (L2-32). If it
  matches neither our outcomes -> integrity failure. (resolved_name_match)
- **rule 4b spread/handicap stored Yes/No against a named line — THE dangerous
  class**: do NOT hand-derive from the token. Game-linked -> score-based
  (#939/#944) is forwarded (counted, not written this session). Not game-linked
  -> ambiguous_skipped.
- **rule 5 multi-candidate groups**: each sub-market is its own condition_id
  binary -> rule 1 per sub-market (handled by the per-market cohort).

## Integrity guard (MANDATORY, before ANY write)
Name concordance between our `FuturesMarket.name` and the CLOB question/slug via
the conservative near-match machinery (Jaccard >=0.72, containment >=0.85). If
either side has <3 comparable tokens the near-match cannot apply — fall back to a
token-overlap>=1 check (condition_id identity already guarantees the market; this
is defense-in-depth vs gross CLOB corruption). Date sanity: if both sides carry a
resolution/close date they must agree within +/-14d.

Anti-gotcha-#21: authoritative source + per-market integrity guard +
skip-on-ambiguity, Batch-0-proven before any write. `cal_prob` is NEVER touched.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone

from sqlalchemy import text

from app.utils.cross_source_matching import (
    _is_conservative_near_match,
    _near_match_tokens,
)

logger = logging.getLogger(__name__)

# Heuristic-resolved classes that were dropped from the curve and are eligible
# for authoritative CLOB re-resolution.
_DROPPED_SOURCES = ("pass2_loser", "all_losers")
_WRITE_SOURCE = "clob_authoritative"
# Amendment 1 (BLESSED): the ordinal tier writes a DISTINCT source so the whole
# ~15K cohort is separately revertible in one predicate.
_WRITE_SOURCE_ORDINAL = "clob_ordinal"

# Tiers whose mapping is authoritative + confident enough to WRITE by default.
# The ordinal tier is NOT here — it stays dry-run until its own vintage-stratified
# Batch-0 signs off, then is enabled explicitly with a first-batch cap (<=2000).
_DEFAULT_WRITE_TIERS = ("resolved_direct", "resolved_name_match")

# First-batch cap for the ordinal tier (Amendment 1, condition 5): verify winrate
# sanity + curve stability on <=2,000 before the full ~15K drain.
_ORDINAL_FIRST_BATCH_CAP = 2000
_ORDINAL_WRITTEN_KEY = "clob_resolve:ordinal_written"

# Politeness: CLOB tolerates low concurrency (L2-32). ~1.2s effective spacing.
_CONCURRENCY = 5
_CURSOR_KEY = "clob_resolve:cursor_max_id"
_DATE_TOLERANCE_DAYS = 14


def _norm(s: str) -> str:
    """Normalize an outcome/label for matching: lowercase, strip punctuation."""
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def _suffix_of(external_id: str | None) -> str | None:
    if not external_id:
        return None
    if external_id.endswith("_yes"):
        return "_yes"
    if external_id.endswith("_no"):
        return "_no"
    return None


def _is_yes_no(name: str) -> bool:
    return _norm(name) in ("yes", "no")


def _direction(name: str) -> str | None:
    """'over' / 'under' if the name carries a totals direction, else None."""
    n = _norm(name)
    if n.startswith("over"):
        return "over"
    if n.startswith("under"):
        return "under"
    return None


def _name_concordance_ok(market_name: str, clob_question: str) -> bool:
    """MANDATORY integrity guard: our market name vs the CLOB question. Uses the
    conservative near-match (>=0.72/>=0.85); falls back to token-overlap>=1 when
    the near-match cannot apply (a side has <3 comparable tokens)."""
    if not clob_question:
        return True  # nothing to compare; condition_id identity stands
    if _is_conservative_near_match(market_name, clob_question):
        return True
    lt = _near_match_tokens(market_name)
    rt = _near_match_tokens(clob_question)
    if len(lt) < 3 or len(rt) < 3:
        # near-match inapplicable — require at least one shared meaningful token
        return len(lt & rt) >= 1
    return False


def _parse_date(v) -> datetime | None:
    if not v:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    try:
        s = str(v).replace("Z", "+00:00")
        d = datetime.fromisoformat(s)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _date_sanity_ok(our_date, clob_market: dict) -> bool:
    a = _parse_date(our_date)
    b = _parse_date((clob_market or {}).get("end_date_iso")
                    or (clob_market or {}).get("end_date"))
    if not a or not b:
        return True  # can't compare -> don't block
    return abs((a - b).days) <= _DATE_TOLERANCE_DAYS


def _match_team_outcome(clob_winner: str, our_outcomes: list[dict]) -> int | None:
    """Rule 2/4a: match a team/player CLOB winner label to our outcome. Exact
    normalized equality first, then conservative near-match (both need >=3
    tokens, so this mostly helps multi-word org names). Returns the outcome id
    when EXACTLY one confidently matches, else None (never naive substring)."""
    w = _norm(clob_winner)
    if not w:
        return None
    exact = [o["id"] for o in our_outcomes if _norm(o["name"]) == w]
    if len(exact) == 1:
        return exact[0]
    near = [o["id"] for o in our_outcomes
            if _is_conservative_near_match(clob_winner, o["name"])]
    if len(near) == 1:
        return near[0]
    return None


def map_clob_to_outcome(
    clob_market: dict | None, our_outcomes: list[dict], event_linked: bool,
    enable_ordinal: bool = False,
) -> dict:
    """Classify the market shape and map the CLOB winner to OUR outcomes per the
    binding spec. Returns a resolution dict (tier/winner_id/loser_id) or a
    ``{"skip": <counter>}`` dict. Never guesses.

    our_outcomes: list of {"id","name","external_id"}. event_linked: whether the
    market has an event_id (game-linked -> score-based is possible downstream).

    enable_ordinal (Amendment 1): when True, the Yes/No-STORED ambiguous class
    (spread/totals with no stored label) is resolved via the ordinal invariant —
    winner token INDEX -> `_yes`/`_no` suffix (`_yes`==tokens[0] by our own write
    contract). Every result also carries ``ordinal_agree`` (label-chosen winner ==
    ordinal winner) so the invariant can be validated per ingestion vintage.
    """
    tokens = (clob_market or {}).get("tokens") or []
    if len(tokens) != 2:
        return {"skip": "ambiguous_skipped", "why": "not_binary_clob"}
    winners = [i for i, t in enumerate(tokens) if t.get("winner") is True]
    if len(winners) != 1:
        return {"skip": "void"}
    win_idx = winners[0]
    win_label = str(tokens[win_idx].get("outcome") or "")

    by_suf: dict[str, dict] = {}
    for o in our_outcomes:
        s = _suffix_of(o.get("external_id"))
        if s:
            by_suf[s] = o
    if set(by_suf) != {"_yes", "_no"}:
        return {"skip": "ambiguous_skipped", "why": "no_binary_suffix"}
    yes_o, no_o = by_suf["_yes"], by_suf["_no"]

    tok_norm = {_norm(tokens[0].get("outcome") or ""),
                _norm(tokens[1].get("outcome") or "")}
    our_yes_no = _is_yes_no(yes_o["name"]) and _is_yes_no(no_o["name"])

    # Ordinal invariant: `_yes`==tokens[0], `_no`==tokens[1] by our write contract.
    ordinal_winner = yes_o if win_idx == 0 else no_o
    ordinal_loser = no_o if win_idx == 0 else yes_o

    def _result(tier, winner_id, loser_id):
        # ordinal_agree: does the label/name-chosen winner equal the ordinal
        # winner? This is the per-market invariant cross-check (Amendment cond 2).
        return {"tier": tier, "winner_id": winner_id, "loser_id": loser_id,
                "clob_winner": win_label,
                "clob_tokens": [tokens[0].get("outcome"), tokens[1].get("outcome")],
                "ordinal_agree": (winner_id == ordinal_winner["id"])}

    def _ordinal_result(why):
        return {"tier": "resolved_ordinal", "winner_id": ordinal_winner["id"],
                "loser_id": ordinal_loser["id"], "clob_winner": win_label,
                "clob_tokens": [tokens[0].get("outcome"), tokens[1].get("outcome")],
                "ordinal_agree": None, "ordinal_why": why}

    # ---- rule 1: binary yes/no props ----
    if tok_norm == {"yes", "no"}:
        if not our_yes_no:
            return {"skip": "ambiguous_skipped", "why": "yn_clob_nonyn_ours"}
        wname = _norm(win_label)
        win_o = next((o for o in (yes_o, no_o) if _norm(o["name"]) == wname), None)
        if not win_o:
            return {"skip": "integrity_skipped", "why": "yn_label_unmatched"}
        lose_o = no_o if win_o is yes_o else yes_o
        return _result("resolved_direct", win_o["id"], lose_o["id"])

    # ---- rule 3: totals (Over/Under) ----
    if tok_norm == {"over", "under"}:
        yd, nd = _direction(yes_o["name"]), _direction(no_o["name"])
        if yd and nd:  # our names carry the direction
            wd = _norm(win_label)
            win_o = yes_o if yd == wd else (no_o if nd == wd else None)
            if not win_o:
                return {"skip": "integrity_skipped", "why": "ou_dir_unmatched"}
            lose_o = no_o if win_o is yes_o else yes_o
            return _result("resolved_direct", win_o["id"], lose_o["id"])
        # esports totals stored Yes/No: line not stored. Spec-conformant = skip;
        # ordinal tier (Amendment 1) resolves via token index.
        if enable_ordinal:
            return _ordinal_result("totals_stored_yesno")
        return {"skip": "ambiguous_skipped", "why": "totals_stored_yesno"}

    # ---- rules 2 / 4a / 4b: CLOB tokens are team/player names ----
    if not our_yes_no:
        # rule 2 / 4a: our outcomes are team names -> name-match the winner
        win_id = _match_team_outcome(win_label, [yes_o, no_o])
        if win_id is None:
            return {"skip": "integrity_skipped", "why": "team_label_unmatched"}
        lose_o = no_o if win_id == yes_o["id"] else yes_o
        return _result("resolved_name_match", win_id, lose_o["id"])

    # rule 4b: Yes/No against a named line — the dangerous class.
    # Game-linked stays score-based-forward (final score is even more
    # authoritative). Non-game-linked: spec-conformant = skip; ordinal tier
    # (Amendment 1) resolves via token index.
    if event_linked:
        return {"skip": "resolved_score_based", "why": "game_linked_forward"}
    if enable_ordinal:
        return _ordinal_result("spread_yesno_nogame")
    return {"skip": "ambiguous_skipped", "why": "spread_yesno_nogame"}


# ---------------------------------------------------------------------------
# Cohort loading + fetch
# ---------------------------------------------------------------------------


async def _load_cohort(session, limit: int, before_id: int | None) -> list:
    clause = "AND fm.id < :before" if before_id else ""
    rows = (await session.execute(text(f"""
        SELECT fm.id, fm.external_id AS cond_id, LEFT(fm.name, 100) AS market_name,
               fm.resolution_date, fm.created_at, (fm.event_id IS NOT NULL) AS event_linked
        FROM futures_markets fm
        JOIN futures_outcomes fo ON fo.market_id = fm.id
        WHERE fm.source = 'polymarket' AND fm.status = 'resolved'
          AND fm.external_id LIKE '0x%' {clause}
        GROUP BY fm.id, fm.external_id, fm.name, fm.resolution_date, fm.created_at, fm.event_id
        HAVING bool_or(fo.is_winner) IS NOT TRUE
           AND bool_or(fo.resolution_source = ANY(:srcs))
        ORDER BY fm.id DESC
        LIMIT :lim
    """), {"srcs": list(_DROPPED_SOURCES), "lim": limit,
           **({"before": before_id} if before_id else {})})).all()
    return rows


async def _load_outcomes(session, market_ids: list[int]) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {}
    if not market_ids:
        return out
    orows = (await session.execute(text("""
        SELECT market_id, id, name, external_id FROM futures_outcomes
        WHERE market_id = ANY(:ids)
    """), {"ids": market_ids})).all()
    for o in orows:
        out.setdefault(o.market_id, []).append(
            {"id": o.id, "name": o.name, "external_id": o.external_id})
    return out


def _vintage_bucket(created_at) -> str:
    """Coarse ingestion-vintage bucket (YYYY-Qn) for stratification."""
    d = _parse_date(created_at)
    if not d:
        return "unknown"
    return f"{d.year}-Q{(d.month - 1) // 3 + 1}"


async def _fetch_and_map(service, r, outcomes_by_market: dict,
                         enable_ordinal: bool = False) -> dict:
    try:
        clob = await service.get_clob_market_by_condition(str(r.cond_id))
    except Exception as e:  # 429/5xx/timeout — surfaced, never treated as void
        return {"market_id": r.id, "error": str(e)[:120]}
    if clob is None:
        return {"market_id": r.id, "not_found": True, "market": r.market_name}

    our = outcomes_by_market.get(r.id, [])
    clob_q = str(clob.get("question") or clob.get("market_slug") or "")
    res = map_clob_to_outcome(clob, our, bool(r.event_linked),
                              enable_ordinal=enable_ordinal)
    # MANDATORY integrity guards (only meaningful when we would write)
    integrity_ok = _name_concordance_ok(r.market_name, clob_q) and \
        _date_sanity_ok(r.resolution_date, clob)
    res.update({
        "market_id": r.id,
        "market": r.market_name,
        "clob_question": clob_q[:90],
        "integrity_ok": integrity_ok,
        "event_linked": bool(r.event_linked),
        "vintage": _vintage_bucket(getattr(r, "created_at", None)),
        "our_outcomes": [f"{o['name']}({_suffix_of(o['external_id'])})"
                         for o in our][:4],
    })
    return res


# Ordered counter keys per the binding spec (+ resolved_ordinal, Amendment 1).
_COUNTERS = ("resolved_direct", "resolved_name_match", "resolved_ordinal",
             "resolved_score_based", "void", "integrity_skipped",
             "ambiguous_skipped", "not_found")


def _tally(out: dict, res: dict) -> None:
    """Fold one mapped result into the spec counters."""
    if res.get("error"):
        out["errors"].append(res["error"])
        return
    if res.get("not_found"):
        out["not_found"] += 1
        return
    if not res.get("integrity_ok", True):
        out["integrity_skipped"] += 1
        return
    skip = res.get("skip")
    if skip:
        out[skip] = out.get(skip, 0) + 1
        return
    out[res["tier"]] += 1


async def clob_resolve_sample(limit: int = 60) -> dict:
    """Batch-0 dry-run: fetch CLOB winners for a sample of the dropped cohort and
    report the shape/tier breakdown with the spec counters. Writes NOTHING."""
    from app.tasks.base import get_task_session
    from app.services.polymarket_api import PolymarketAPIService

    out: dict = {"dry_run": True, "checked": 0, "errors": [], "samples": []}
    for k in _COUNTERS:
        out[k] = 0

    async with get_task_session() as session:
        rows = await _load_cohort(session, limit, None)
        outcomes_by_market = await _load_outcomes(session, [r.id for r in rows])

    service = PolymarketAPIService()
    sem = asyncio.Semaphore(_CONCURRENCY)

    async def _one(r):
        async with sem:
            return await _fetch_and_map(service, r, outcomes_by_market)

    try:
        results = await asyncio.gather(*[_one(r) for r in rows])
    finally:
        await service.close()

    for res in results:
        out["checked"] += 1
        _tally(out, res)
        out["samples"].append(res)
    return out


async def _load_cohort_stratified(session, limit: int) -> list:
    """Load a vintage-stratified cohort sample: oldest half + newest half, so the
    ordinal invariant is tested against every historical poller version
    (Amendment 1, condition 1). Writes nothing."""
    half = max(1, limit // 2)
    q = """
        WITH cohort AS (
            SELECT fm.id, fm.external_id AS cond_id, LEFT(fm.name, 100) AS market_name,
                   fm.resolution_date, fm.created_at, (fm.event_id IS NOT NULL) AS event_linked
            FROM futures_markets fm
            JOIN futures_outcomes fo ON fo.market_id = fm.id
            WHERE fm.source = 'polymarket' AND fm.status = 'resolved'
              AND fm.external_id LIKE '0x%'
            GROUP BY fm.id, fm.external_id, fm.name, fm.resolution_date, fm.created_at, fm.event_id
            HAVING bool_or(fo.is_winner) IS NOT TRUE
               AND bool_or(fo.resolution_source = ANY(:srcs))
        )
        (SELECT * FROM cohort ORDER BY created_at ASC LIMIT :half)
        UNION
        (SELECT * FROM cohort ORDER BY created_at DESC LIMIT :half)
    """
    return (await session.execute(
        text(q), {"srcs": list(_DROPPED_SOURCES), "half": half})).all()


async def clob_ordinal_batch0(limit: int = 120) -> dict:
    """Amendment 1 Batch-0 (dry-run): vintage-stratified sample proving the
    ordinal invariant. For markets where the label is determinable
    (resolved_direct/name_match), ``ordinal_agree`` cross-checks ordinal==label
    per vintage — ANY disagreement in a vintage means the invariant is broken for
    that poller version. Reports per-vintage agreement + per-shape ordinal winrate.
    Writes NOTHING."""
    from app.tasks.base import get_task_session
    from app.services.polymarket_api import PolymarketAPIService

    out: dict = {"dry_run": True, "checked": 0, "errors": [],
                 "label_checkable": 0, "label_agree": 0, "label_disagree": 0,
                 "by_vintage": {}, "ordinal_yes_win": 0, "ordinal_no_win": 0,
                 "disagreements": [], "samples": []}
    for k in _COUNTERS:
        out[k] = 0

    async with get_task_session() as session:
        rows = await _load_cohort_stratified(session, limit)
        outcomes_by_market = await _load_outcomes(session, [r.id for r in rows])

    service = PolymarketAPIService()
    sem = asyncio.Semaphore(_CONCURRENCY)

    async def _one(r):
        async with sem:
            return await _fetch_and_map(service, r, outcomes_by_market,
                                        enable_ordinal=True)

    try:
        results = await asyncio.gather(*[_one(r) for r in rows])
    finally:
        await service.close()

    for res in results:
        out["checked"] += 1
        _tally(out, res)
        vint = res.get("vintage", "unknown")
        vb = out["by_vintage"].setdefault(
            vint, {"label_checkable": 0, "label_agree": 0, "ordinal": 0, "total": 0})
        vb["total"] += 1
        agree = res.get("ordinal_agree")
        if agree is not None:  # label-determinable -> invariant cross-check
            out["label_checkable"] += 1
            vb["label_checkable"] += 1
            if agree:
                out["label_agree"] += 1
                vb["label_agree"] += 1
            else:
                out["label_disagree"] += 1
                out["disagreements"].append(
                    {"market_id": res.get("market_id"), "vintage": vint,
                     "market": res.get("market"), "tokens": res.get("clob_tokens")})
        if res.get("tier") == "resolved_ordinal":
            vb["ordinal"] += 1
            side = _ordinal_side(res)  # winrate sanity: which stored side won
            out["ordinal_yes_win"] += 1 if side == "_yes" else 0
            out["ordinal_no_win"] += 1 if side == "_no" else 0
        out["samples"].append(res)

    ck = out["label_checkable"]
    out["label_agree_rate"] = round(out["label_agree"] / ck, 4) if ck else None
    out["verdict"] = (
        "PASS" if ck >= 20 and out["label_disagree"] == 0
        else ("FAIL_DISAGREEMENT" if out["label_disagree"] else "INSUFFICIENT_LABEL_SAMPLE"))
    return out


def _ordinal_side(res: dict) -> str | None:
    """Which stored side (_yes/_no) the ordinal winner is: `_yes`==tokens[0] by
    the write contract, so the winning side is `_yes` iff the CLOB winner label
    is tokens[0]."""
    toks = res.get("clob_tokens") or []
    if len(toks) == 2 and res.get("clob_winner"):
        return "_yes" if res["clob_winner"] == toks[0] else "_no"
    return None


async def clob_resolve_drain(
    limit: int = 300,
    dry_run: bool = False,
    write_tiers: tuple = _DEFAULT_WRITE_TIERS,
    enable_ordinal: bool = False,
    ordinal_cap: int = _ORDINAL_FIRST_BATCH_CAP,
) -> dict:
    """The writing drain. Resumable via a Redis cursor (newest market id first).
    Per market: fetch CLOB, classify+map per the binding spec, run the mandatory
    integrity guard, and — for tiers in ``write_tiers`` — write authoritative
    is_winner (winner True / loser False) via Core SQL, per-market commit
    (gotchas #6/#13/#34). cal_prob is never touched. Void / ambiguous /
    integrity-fail stay untouched (honest floor). Idempotent.

    Amendment 1: pass ``enable_ordinal=True`` and include ``'resolved_ordinal'``
    in ``write_tiers`` to write the ordinal class with resolution_source
    ='clob_ordinal'. Cumulative ordinal writes are capped at ``ordinal_cap``
    (Redis-tracked) so the first batch stays <=2,000 until sanity is verified."""
    from app.tasks.base import get_task_session
    from app.services.polymarket_api import PolymarketAPIService
    from app.tasks.redis_state import get_redis_client

    ordinal_write = enable_ordinal and "resolved_ordinal" in write_tiers
    out: dict = {"dry_run": dry_run, "write_tiers": list(write_tiers),
                 "enable_ordinal": enable_ordinal,
                 "checked": 0, "written": 0, "written_ordinal": 0,
                 "errors": [], "cursor_reset": False}
    for k in _COUNTERS:
        out[k] = 0

    before_id: int | None = None
    redis = None
    ordinal_written_total = 0
    try:
        redis = get_redis_client()
        raw = redis.get(_CURSOR_KEY)
        if raw:
            before_id = int(raw)
        if ordinal_write:
            ov = redis.get(_ORDINAL_WRITTEN_KEY)
            ordinal_written_total = int(ov) if ov else 0
    except Exception as e:
        logger.warning("clob_resolve_drain: redis unavailable: %s", e)

    async with get_task_session() as session:
        rows = await _load_cohort(session, limit, before_id)
        if not rows and before_id:
            out["cursor_reset"] = True
            if redis:
                try:
                    redis.delete(_CURSOR_KEY)
                except Exception:
                    pass
            return out
        outcomes_by_market = await _load_outcomes(session, [r.id for r in rows])

    service = PolymarketAPIService()
    sem = asyncio.Semaphore(_CONCURRENCY)

    async def _one(r):
        async with sem:
            return await _fetch_and_map(service, r, outcomes_by_market,
                                        enable_ordinal=enable_ordinal)

    min_id_seen: int | None = None
    try:
        results = await asyncio.gather(*[_one(r) for r in rows])
        async with get_task_session() as wsession:
            for res in results:
                out["checked"] += 1
                mid = res.get("market_id")
                if mid is not None:
                    min_id_seen = mid if min_id_seen is None else min(min_id_seen, mid)
                _tally(out, res)
                if res.get("skip") or res.get("error") or res.get("not_found"):
                    continue
                if not res.get("integrity_ok", True):
                    continue
                if dry_run or res["tier"] not in write_tiers:
                    continue
                is_ordinal = res["tier"] == "resolved_ordinal"
                if is_ordinal:
                    # first-batch cap (Amendment cond 5)
                    if ordinal_written_total >= ordinal_cap:
                        continue
                src = _WRITE_SOURCE_ORDINAL if is_ordinal else _WRITE_SOURCE
                try:
                    await wsession.execute(text("""
                        UPDATE futures_outcomes
                        SET is_winner = (id = :win_id),
                            resolution_source = :src,
                            last_updated = now()
                        WHERE id IN (:win_id, :lose_id)
                    """), {"win_id": res["winner_id"],
                           "lose_id": res["loser_id"], "src": src})
                    await wsession.commit()
                    out["written"] += 1
                    if is_ordinal:
                        out["written_ordinal"] += 1
                        ordinal_written_total += 1
                        if redis:
                            try:
                                redis.set(_ORDINAL_WRITTEN_KEY, str(ordinal_written_total))
                            except Exception:
                                pass
                except Exception as e:
                    await wsession.rollback()
                    out["errors"].append(f"write m{mid}: {str(e)[:100]}")
    finally:
        await service.close()
    if ordinal_write:
        out["ordinal_written_total"] = ordinal_written_total
        out["ordinal_cap"] = ordinal_cap

    if redis and min_id_seen is not None:
        try:
            if len(rows) < limit:
                redis.delete(_CURSOR_KEY)
                out["cursor_reset"] = True
            else:
                redis.set(_CURSOR_KEY, str(min_id_seen))
                out["next_cursor"] = min_id_seen
        except Exception as e:
            logger.warning("clob_resolve_drain: cursor advance failed: %s", e)

    return out
