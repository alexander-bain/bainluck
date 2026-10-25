"""#2027 / #10955 — withdraw the Over price the old history rail filed under Under.

## what a reader sees

/futures/31519211 (Devin Vassell 3-pointers O/U 2.5) draws an Under line that
tracks the Over line within 0.025 and falls to 0.0005 on the night Under WON.
The Under leg's stored history is the Over contract's history.

## the writer, and only that writer

From `12fd249622` (Jun 1) until `de405e4351` reached the heavy worker,
`_backfill_polymarket_price_history` looked a `{cid}_no` leg's token up with
``cid.rstrip("_yes").rstrip("_no")`` and so handed EVERY Under leg
``clobTokenIds[0]``, the Over token. Before `12fd249622` a `_no` leg found no
token and was skipped. Since the fix, `history_token_for_outcome` reads the
second token.

That rail is the only writer of the row shape this module scopes ("history
shape"): ``bookmaker='polymarket'``, ``american_odds``, ``yes_bid`` and
``yes_ask`` all NULL, ``last_price`` equal to ``probability`` at 4 places, and a
``captured_at`` with no sub-second part (``datetime.fromtimestamp`` of the
CLOB's integer ``t``). Every other Polymarket snapshot writer (the poll's
sub-market and Under arms, the event writer, the futures/tournament refresh, the
live matcher) stamps ``captured_at=now`` and writes ``american_odds`` and the
book. The other CLOB-history readers (the live matcher's moneyline backfill,
the event chart backfill, the outright chart fill) write `win_prob_snapshots`
or a cache, never this table. Census of writers: the PR that added this file.

## which rows: era AND witness

A history-shape row on a `_no` leg is in scope only when BOTH hold:

* **era** — its id is at or below :data:`PRE_FIX_MAX_SNAPSHOT_ID`, the id
  frontier before the first fixed run (pinned from one production read; see
  its comment). Rows above it were written by the fixed writer and are never
  touched; a leg whose only rows are above it yet still read as the Over price
  is reported ``AMBIGUOUS`` (``post_fix_only_reads_as_over``), never skipped
  in silence. With the constant unpinned the dry run still classifies, and every
  apply is refused.
* **witness** — the leg's rows, compared with its Over sibling's own
  observations, read as the Over price and never as its complement. An exact
  pair is a sibling row at the identical second (the same pass backfilled
  both legs from the same token, so they agree to 6 places). Otherwise the
  nearest sibling row within :data:`NEAR_WINDOW_MIN` minutes testifies, at a
  looser tolerance. A pair testifies only when exactly one reading fits it, so
  prices near 0.5, where Over and its complement coincide, say nothing.

Leg verdicts: ``INVERTED`` (planned), ``COMPLEMENT`` (the falsifier: the rows
read as the Under token's own history; refused) and ``AMBIGUOUS`` (refused,
with a reason). The token was chosen per leg from its external id alone, so
one leg's rows share one verdict.

## what the false rows fed

* **openings** — the old rail wrote ``opening_probability = first_price``,
  ``opening_source='clob_history'`` and no capture time. Phase 0c-repair
  (`_PHASE_0C_REPAIR_TEMPLATE`) can promote an inverted row as
  ``first_snapshot`` with that row's ``captured_at``. And the #137 Under
  sign-flip beat (`_regrade_polymarket_under_signflip`) complements an Under
  opening and calibration price that match their Over sibling, so either can
  now hold ``1 - p``. That is a computed number, not an observation, so it is
  withdrawn the same way.
* **calibration price** — derived from snapshots (Part A/B/C) or copied from
  the opening.

An opening is withdrawn when its provenance is exact: an old-rail opening
(``clob_history`` with no capture time) whose value is the leg's first false
row or that row's complement, or any opening whose capture time IS a false row's
and whose value is that row or its complement. A calibration price is withdrawn
when it is a false row's value (or complement) or the withdrawn opening's, and
it is NOT the value of a row this rail keeps. Anything else that half-matches
refuses the whole leg: one leg is repaired whole or not at all.

Withdraw means back up and set NULL. Nothing is complemented, smoothed,
synthesized or moved to the Over leg; `is_winner` is never read for a decision
and never written.

## after an apply

The ordinary pipeline re-derives what is NULL from what remains: Phase 0c
promotes the first honest remaining row as the opening, `_compute_calibration_prices`
refills the calibration price, and a resolved leg left with no rows at all is
picked up by the FIXED history rail (`resolved_zero`), which asks the Under
token itself. None of that is this rail's write, and the restore never undoes
it (see below).

## pinned identity and drift

An apply recomputes the page with the same ``after_id``/``limit``/``only_ids``
and refuses unless the content address (:func:`plan_hash_for`, over every row
id, time and value, every prior field and the era bound) is the one the
operator read. Each leg is one transaction: its planned rows are locked and
must still hold the planned values, and its outcome must still hold the
planned priors, or the leg is left whole and counted ``drift_refused``.

## D51: backup and restore

Rows are copied whole into :data:`BAK_ROWS` and the outcome's prior fields
into :data:`BAK_FIELDS` in the same transaction as the delete/withdrawal. A
copy keeps an older bank row on conflict, so before anything is deleted or
withdrawn every planned row must have a bank row equal to it in every
restorable column, and the field bank must hold exactly the locked priors and
this plan's withdrawal flags. An absent or different copy (a retry after a
restore whose state then moved) rolls the whole leg back and is reported as
``backup_refused`` by outcome id: the restore would otherwise put back a state
this run never removed. An exact bank from an earlier run is a valid retry.
The undo is one statement::

    curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \\
      "$BAINLUCK_API/api/admin/repairs/pm-under-inverted-history-restore?apply=true"

It re-inserts each backed-up row under its own id unless the leg now holds a
different row at that same second (the fixed rail refiled it). It restores a
field only while that field is still NULL, so a later writer's value is never
overwritten. Both are reported, not guessed.

ATTENDED ONLY: never wire this to a beat. Runtime DDL (the two backup tables)
runs only inside an attended apply.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

ISSUE = "#2027"
BAK_ROWS = "bak_2027_pm_under_rows"
BAK_FIELDS = "bak_2027_pm_under_fields"

#: The id frontier before the first FIXED history run. Heavy v168 (`7a15bcd7`,
#: the first heavy release carrying `de405e4351`) released 2026-10-12 08:59:35Z;
#: the first beat run after it was 09:15Z (`open_sparse`). The main app carried
#: the fix from v5662 (05:43:13Z), which matters only for the admin-route run.
#: Pin it from ONE read: the largest snapshot id with a sub-second
#: ``captured_at`` (a poll row, stamped at write time) captured before 09:15Z,
#: AND confirm zero history-shape `_no` rows with ids between that frontier
#: taken at 08:59Z and at 09:15Z. ``None`` = unpinned: dry runs classify,
#: applies refuse.
PRE_FIX_MAX_SNAPSHOT_ID: Optional[int] = None

DEFAULT_SCAN = 100
MAX_SCAN = 500
#: Wall clock per call. Below the router's 30 s with room for the commit.
WALL_BUDGET_S = 20.0

#: Exact pair: the same token at the same second, written to 6 places.
EXACT_EQUAL_TOL = 1e-6
#: Two tokens of one binary market at the same second.
EXACT_COMPLEMENT_TOL = 0.02
#: Nearest sibling observation within the window: prices move between the two.
NEAR_TOL = 0.03
NEAR_WINDOW_MIN = 60
MIN_EXACT_TESTIMONY = 1
MIN_NEAR_TESTIMONY = 3
#: Numeric(7, 6) equality.
VALUE_TOL = 5e-7

INVERTED = "INVERTED"
COMPLEMENT = "COMPLEMENT"
AMBIGUOUS = "AMBIGUOUS"

_EXAMPLES_PER_CLASS = 10
_ROW_SAMPLE = 6

#: The history rail's row shape, as a predicate over snapshot alias ``s``.
HISTORY_SHAPE_SQL = """(
    s.bookmaker = 'polymarket'
    AND s.american_odds IS NULL
    AND s.yes_bid IS NULL
    AND s.yes_ask IS NULL
    AND s.last_price IS NOT NULL
    AND abs(s.last_price - s.probability) <= 0.00006
    AND s.captured_at = date_trunc('second', s.captured_at)
)"""

# `right(..., 3)` rather than LIKE: no escaping, no bind-param parse (gotcha #45).
_PAGE_SQL = """
    SELECT fo.id AS outcome_id, fo.market_id, fo.external_id, fo.name,
           fo.opening_probability, fo.opening_american_odds,
           fo.opening_captured_at, fo.opening_source,
           fo.calibration_probability,
           fm.status AS market_status, fm.resolution_date
    FROM futures_outcomes fo
    JOIN futures_markets fm ON fm.id = fo.market_id
    WHERE fm.source = 'polymarket'
      AND right(fo.external_id, 3) = '_no'
      AND fo.id > :after_id
    ORDER BY fo.id
    LIMIT :scan
"""

#: Over-side candidates: the bare condition id or its `_yes` spelling, same market.
_SIBLINGS_SQL = """
    SELECT fo.id, fo.market_id, fo.external_id
    FROM futures_outcomes fo
    WHERE fo.market_id = ANY(:mids)
      AND (right(fo.external_id, 3) <> '_no')
    ORDER BY fo.id
"""

_ROWS_SQL = f"""
    SELECT s.id, s.outcome_id, s.probability, s.captured_at,
           ex.probability AS exact_p,
           nr.probability AS near_p, nr.captured_at AS near_at
    FROM unnest(CAST(:legs AS bigint[]), CAST(:sibs AS bigint[])) AS m(leg_id, sib_id)
    JOIN futures_odds_snapshots s ON s.outcome_id = m.leg_id
    LEFT JOIN LATERAL (
        SELECT w.probability FROM futures_odds_snapshots w
        WHERE w.outcome_id = m.sib_id AND w.captured_at = s.captured_at
        ORDER BY w.id LIMIT 1
    ) ex ON true
    LEFT JOIN LATERAL (
        SELECT w.probability, w.captured_at FROM futures_odds_snapshots w
        WHERE w.outcome_id = m.sib_id
          AND w.captured_at BETWEEN s.captured_at - make_interval(mins => {NEAR_WINDOW_MIN})
                                AND s.captured_at + make_interval(mins => {NEAR_WINDOW_MIN})
        ORDER BY abs(extract(epoch FROM (w.captured_at - s.captured_at))), w.id
        LIMIT 1
    ) nr ON true
    WHERE {HISTORY_SHAPE_SQL}
    ORDER BY s.outcome_id, s.captured_at, s.id
"""

#: Does the leg keep a row (one this rail does not remove) at this value?
_KEPT_VALUE_SQL = """
    SELECT EXISTS (
        SELECT 1 FROM futures_odds_snapshots s
        WHERE s.outcome_id = :oid
          AND NOT (s.id = ANY(:removed))
          AND abs(s.probability - :v) <= :tol
    )
"""

_BAK_ROWS_CREATE = f"""
    CREATE TABLE IF NOT EXISTS {BAK_ROWS} (
        id BIGINT PRIMARY KEY,
        outcome_id BIGINT NOT NULL,
        bookmaker VARCHAR(50) NOT NULL,
        probability NUMERIC(7, 6),
        american_odds INTEGER,
        yes_bid NUMERIC(5, 4),
        yes_ask NUMERIC(5, 4),
        last_price NUMERIC(5, 4),
        captured_at TIMESTAMPTZ,
        reading_count INTEGER,
        valid_until TIMESTAMPTZ,
        plan_hash TEXT NOT NULL,
        backed_up_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
"""

_BAK_FIELDS_CREATE = f"""
    CREATE TABLE IF NOT EXISTS {BAK_FIELDS} (
        outcome_id BIGINT PRIMARY KEY,
        withdrew_opening BOOLEAN NOT NULL,
        prior_opening_probability NUMERIC(7, 6),
        prior_opening_american_odds INTEGER,
        prior_opening_captured_at TIMESTAMPTZ,
        prior_opening_source VARCHAR(30),
        withdrew_cp BOOLEAN NOT NULL,
        prior_calibration_probability NUMERIC(7, 6),
        plan_hash TEXT NOT NULL,
        backed_up_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
"""

_SNAP_COLS = ("id, outcome_id, bookmaker, probability, american_odds, yes_bid, "
              "yes_ask, last_price, captured_at, reading_count, valid_until")

_LOCK_ROWS = f"""
    SELECT s.id, s.probability, s.captured_at FROM futures_odds_snapshots s
    WHERE s.id = ANY(:ids) AND s.outcome_id = :oid AND {HISTORY_SHAPE_SQL}
    ORDER BY s.id
    FOR UPDATE
"""

_BAK_ROWS_COPY = f"""
    INSERT INTO {BAK_ROWS} ({_SNAP_COLS}, plan_hash)
    SELECT {_SNAP_COLS}, :plan_hash FROM futures_odds_snapshots
    WHERE id = ANY(:ids) AND outcome_id = :oid
    ON CONFLICT (id) DO NOTHING
"""

_RESTORABLE_ROW = ("outcome_id, bookmaker, probability, american_odds, yes_bid, yes_ask, "
                   "last_price, captured_at, reading_count, valid_until")

#: Planned rows with no bank copy equal in every restorable column. A count of
#: bank rows would pass on an older row the copy's conflict clause kept.
_BAK_ROWS_UNPAIRED = f"""
    SELECT s.id FROM futures_odds_snapshots s
    WHERE s.id = ANY(:ids) AND s.outcome_id = :oid
      AND NOT EXISTS (
          SELECT 1 FROM {BAK_ROWS} b
          WHERE b.id = s.id
            AND ({", ".join("b." + c for c in _RESTORABLE_ROW.split(", "))})
                IS NOT DISTINCT FROM
                ({", ".join("s." + c for c in _RESTORABLE_ROW.split(", "))})
      )
    ORDER BY s.id
"""

_DELETE_ROWS = """
    DELETE FROM futures_odds_snapshots WHERE id = ANY(:ids) AND outcome_id = :oid
"""

_LOCK_FIELDS = """
    SELECT opening_probability, opening_american_odds, opening_captured_at,
           opening_source, calibration_probability
    FROM futures_outcomes WHERE id = :oid
    FOR UPDATE
"""

#: A conflict keeps the older copy; :data:`_BAK_FIELDS_PAIRED` then refuses the
#: leg unless that copy is exactly this run's prior.
_BAK_FIELDS_COPY = f"""
    INSERT INTO {BAK_FIELDS} (outcome_id, withdrew_opening, prior_opening_probability,
                              prior_opening_american_odds, prior_opening_captured_at,
                              prior_opening_source, withdrew_cp,
                              prior_calibration_probability, plan_hash)
    SELECT id, :wo, opening_probability, opening_american_odds, opening_captured_at,
           opening_source, :wc, calibration_probability, :plan_hash
    FROM futures_outcomes WHERE id = :oid
    ON CONFLICT (outcome_id) DO NOTHING
"""

#: Does the field bank hold exactly this leg's locked priors and this plan's flags?
_BAK_FIELDS_PAIRED = f"""
    SELECT EXISTS (
        SELECT 1 FROM {BAK_FIELDS} b
        JOIN futures_outcomes fo ON fo.id = b.outcome_id
        WHERE b.outcome_id = :oid
          AND b.withdrew_opening = :wo AND b.withdrew_cp = :wc
          AND (b.prior_opening_probability, b.prior_opening_american_odds,
               b.prior_opening_captured_at, b.prior_opening_source,
               b.prior_calibration_probability)
              IS NOT DISTINCT FROM
              (fo.opening_probability, fo.opening_american_odds, fo.opening_captured_at,
               fo.opening_source, fo.calibration_probability)
    )
"""

_WITHDRAW_OPENING = """
    UPDATE futures_outcomes
    SET opening_probability = NULL, opening_american_odds = NULL,
        opening_captured_at = NULL, opening_source = NULL, last_updated = NOW()
    WHERE id = :oid
"""

_WITHDRAW_CP = """
    UPDATE futures_outcomes
    SET calibration_probability = NULL, last_updated = NOW()
    WHERE id = :oid
"""

_EXISTS = "SELECT to_regclass(:t) IS NOT NULL"

#: A backed-up row collides when the leg now holds a row at the same second that
#: is not itself one of ours (the fixed rail refiled the instant).
_ROW_RESTORABLE = f"""
    NOT EXISTS (SELECT 1 FROM futures_odds_snapshots s WHERE s.id = b.id)
    AND EXISTS (SELECT 1 FROM futures_outcomes fo WHERE fo.id = b.outcome_id)
    AND NOT EXISTS (
        SELECT 1 FROM futures_odds_snapshots s
        WHERE s.outcome_id = b.outcome_id AND s.captured_at = b.captured_at
          AND NOT EXISTS (SELECT 1 FROM {BAK_ROWS} b2 WHERE b2.id = s.id)
    )
"""

_ROWS_CENSUS = f"""
    SELECT count(*) AS backed_up,
           count(*) FILTER (WHERE EXISTS (
               SELECT 1 FROM futures_odds_snapshots s WHERE s.id = b.id)) AS present,
           count(*) FILTER (WHERE {_ROW_RESTORABLE}) AS restorable
    FROM {BAK_ROWS} b
"""

_ROWS_RESTORE = f"""
    INSERT INTO futures_odds_snapshots ({_SNAP_COLS})
    SELECT b.id, b.outcome_id, b.bookmaker, b.probability, b.american_odds, b.yes_bid,
           b.yes_ask, b.last_price, b.captured_at, b.reading_count, b.valid_until
    FROM {BAK_ROWS} b
    WHERE {_ROW_RESTORABLE}
"""

_OPENING_STILL_WITHDRAWN = """(
    fo.opening_probability IS NULL AND fo.opening_american_odds IS NULL
    AND fo.opening_captured_at IS NULL AND fo.opening_source IS NULL
)"""

_FIELDS_CENSUS = f"""
    SELECT count(*) FILTER (WHERE b.withdrew_opening) AS openings_backed_up,
           count(*) FILTER (WHERE b.withdrew_opening AND {_OPENING_STILL_WITHDRAWN})
               AS openings_restorable,
           count(*) FILTER (WHERE b.withdrew_cp) AS cp_backed_up,
           count(*) FILTER (WHERE b.withdrew_cp AND fo.calibration_probability IS NULL)
               AS cp_restorable
    FROM {BAK_FIELDS} b
    JOIN futures_outcomes fo ON fo.id = b.outcome_id
"""

_OPENING_RESTORE = f"""
    UPDATE futures_outcomes fo
    SET opening_probability = b.prior_opening_probability,
        opening_american_odds = b.prior_opening_american_odds,
        opening_captured_at = b.prior_opening_captured_at,
        opening_source = b.prior_opening_source,
        last_updated = NOW()
    FROM {BAK_FIELDS} b
    WHERE fo.id = b.outcome_id AND b.withdrew_opening AND {_OPENING_STILL_WITHDRAWN}
"""

_CP_RESTORE = f"""
    UPDATE futures_outcomes fo
    SET calibration_probability = b.prior_calibration_probability, last_updated = NOW()
    FROM {BAK_FIELDS} b
    WHERE fo.id = b.outcome_id AND b.withdrew_cp AND fo.calibration_probability IS NULL
"""


def restore_command() -> str:
    """The one command that puts it back (D51). Printed by every apply."""
    return (
        'source ~/.claude/.env && curl -s -X POST -H '
        '"Authorization: Bearer $ADMIN_TOKEN" '
        '"$BAINLUCK_API/api/admin/repairs/pm-under-inverted-history-restore?apply=true"'
    )


# ---------------------------------------------------------------------------
# pure decisions
# ---------------------------------------------------------------------------

def _f(v) -> Optional[float]:
    return None if v is None else float(v)


def over_sibling_ids(under_external_id: str, siblings: list[dict]) -> list[int]:
    """The Over legs of an Under leg's own condition: the bare id or `_yes`."""
    cid = under_external_id.removesuffix("_no")
    return [s["id"] for s in siblings if s["external_id"] in (cid, f"{cid}_yes")]


def pair_testimony(p: float, q: float, exact: bool) -> Optional[str]:
    """What one (Under row, Over observation) pair says: ``"equal"`` (the Under
    row is the Over price), ``"complement"`` (it is the other side's), or None
    when neither or both readings fit."""
    eq = abs(p - q) <= (EXACT_EQUAL_TOL if exact else NEAR_TOL)
    comp = abs(p + q - 1.0) <= (EXACT_COMPLEMENT_TOL if exact else NEAR_TOL)
    if eq == comp:
        return None
    return "equal" if eq else "complement"


def testify(rows: list[dict]) -> dict:
    """Tally a set of rows' testimonies. Exact pairs, when any testify, are the
    evidence; the near pairs are used only when no exact pair says anything."""
    exact = {"equal": 0, "complement": 0}
    near = {"equal": 0, "complement": 0}
    for r in rows:
        p = _f(r["probability"])
        if r.get("exact_p") is not None:
            t = pair_testimony(p, _f(r["exact_p"]), exact=True)
            if t:
                exact[t] += 1
                continue
        if r.get("near_p") is not None:
            t = pair_testimony(p, _f(r["near_p"]), exact=False)
            if t:
                near[t] += 1
    if exact["equal"] or exact["complement"]:
        return {"kind": "exact", **exact}
    return {"kind": "near", **near}


def classify_testimony(t: dict) -> tuple[str, Optional[str]]:
    """Leg verdict from its pre-fix rows' tally."""
    eq, comp = t["equal"], t["complement"]
    if eq and comp:
        return AMBIGUOUS, "mixed_testimony"
    if comp:
        return COMPLEMENT, None
    floor = MIN_EXACT_TESTIMONY if t["kind"] == "exact" else MIN_NEAR_TESTIMONY
    if eq >= floor:
        return INVERTED, None
    return AMBIGUOUS, ("no_testimony" if eq == 0 else "too_few_testimonies")


def _matches(v: Optional[float], p: float) -> Optional[str]:
    if v is None:
        return None
    if abs(v - p) <= VALUE_TOL:
        return "raw"
    if abs(v - (1.0 - p)) <= VALUE_TOL:
        return "complemented"
    return None


def opening_derivation(leg: dict, removed: list[dict]) -> tuple[str, Optional[str]]:
    """``("keep", None)``, ``("withdraw", how)`` or ``("ambiguous", reason)``.

    ``removed`` are the leg's planned rows, oldest first."""
    v = _f(leg.get("opening_probability"))
    if v is None:
        return "keep", None
    src = leg.get("opening_source")
    at = leg.get("opening_captured_at")
    if src == "clob_history" and at is None:
        # The old rail's own write: price only, its pass's first point.
        how = _matches(v, _f(removed[0]["probability"]))
        if how:
            return "withdraw", f"clob_history_{how}"
        return "ambiguous", "old_rail_opening_value_unexplained"
    if at is not None:
        same_instant = [r for r in removed if r["captured_at"] == at]
        for r in same_instant:
            how = _matches(v, _f(r["probability"]))
            if how:
                return "withdraw", f"{src or 'unsourced'}_{how}"
        if same_instant:
            return "ambiguous", "opening_instant_matches_value_does_not"
    return "keep", None


def cp_candidates(leg: dict, removed: list[dict], opening_withdrawn: bool) -> Optional[str]:
    """How the calibration price derives from the false rows, or None."""
    cp = _f(leg.get("calibration_probability"))
    if cp is None:
        return None
    if opening_withdrawn:
        how = _matches(cp, _f(leg["opening_probability"]))
        if how == "raw":
            return "copy_of_withdrawn_opening"
    for r in removed:
        how = _matches(cp, _f(r["probability"]))
        if how:
            return f"false_row_{how}"
    return None


def plan_hash_for(planned: list[dict], boundary: Optional[int]) -> str:
    """Content address of a page's writes, over every fact an apply re-checks."""
    body = json.dumps(
        {"boundary": boundary,
         "legs": sorted(planned, key=lambda p: p["outcome_id"])},
        separators=(",", ":"), sort_keys=True, default=str,
    )
    return hashlib.sha256(body.encode()).hexdigest()[:32]


def parse_only_ids(only_ids: Optional[str]) -> Optional[set[int]]:
    """``None`` = whole plan. An empty or non-integer list raises."""
    if only_ids is None:
        return None
    parts = [p.strip() for p in only_ids.split(",")]
    if not parts or any(not p.isdigit() for p in parts):
        raise ValueError(f"only_ids must be comma-separated outcome ids, got {only_ids!r}")
    return {int(p) for p in parts}


# ---------------------------------------------------------------------------
# the page
# ---------------------------------------------------------------------------

def _count(d: dict, key: str, n: int = 1) -> None:
    d[key] = d.get(key, 0) + n


def _row_view(r: dict) -> dict:
    return {"id": r["id"], "at": r["captured_at"].isoformat(),
            "p": _f(r["probability"]), "exact_over": _f(r.get("exact_p")),
            "near_over": _f(r.get("near_p")),
            "near_at": r["near_at"].isoformat() if r.get("near_at") else None}


def _planned_fields(leg: dict) -> dict:
    return {
        "opening_probability": _f(leg.get("opening_probability")),
        "opening_american_odds": leg.get("opening_american_odds"),
        "opening_captured_at": (leg["opening_captured_at"].isoformat()
                                if leg.get("opening_captured_at") else None),
        "opening_source": leg.get("opening_source"),
        "calibration_probability": _f(leg.get("calibration_probability")),
    }


async def _plan_page(session, cursor: int, scan: int, pinned: Optional[set[int]],
                     boundary: Optional[int], started: float) -> dict:
    legs = [dict(r._mapping) for r in
            (await session.execute(text(_PAGE_SQL), {"after_id": cursor, "scan": scan})).all()]
    out: dict[str, Any] = {
        "planned": [], "verdicts": {}, "ambiguous_reasons": {},
        "examples": {INVERTED: [], COMPLEMENT: [], AMBIGUOUS: []},
        "legs_examined": len(legs), "legs_with_history_rows": 0,
        "withheld_by_only_ids": 0, "stopped_on": None,
        "next_after_id": legs[-1]["outcome_id"] if legs else cursor,
    }
    out["exhausted"] = len(legs) < scan
    if not legs:
        return out

    siblings = [dict(r._mapping) for r in (await session.execute(
        text(_SIBLINGS_SQL), {"mids": sorted({lg["market_id"] for lg in legs})})).all()]
    by_market: dict[int, list[dict]] = {}
    for s in siblings:
        by_market.setdefault(s["market_id"], []).append(s)
    sib_of: dict[int, list[int]] = {
        lg["outcome_id"]: over_sibling_ids(lg["external_id"], by_market.get(lg["market_id"], []))
        for lg in legs
    }
    pairs = [(oid, ids[0]) for oid, ids in sib_of.items() if len(ids) == 1]
    no_sib = [lg["outcome_id"] for lg in legs if len(sib_of[lg["outcome_id"]]) != 1]

    rows_by_leg: dict[int, list[dict]] = {}
    lone_legs = [(oid, 0) for oid in no_sib]  # sibling 0 matches no row
    all_pairs = pairs + lone_legs
    if all_pairs:
        res = await session.execute(text(_ROWS_SQL), {
            "legs": [a for a, _ in all_pairs], "sibs": [b for _, b in all_pairs]})
        for r in res.all():
            rows_by_leg.setdefault(r.outcome_id, []).append(dict(r._mapping))

    for lg in legs:
        if time.monotonic() - started > WALL_BUDGET_S:
            out["stopped_on"] = "wall_budget"
            out["next_after_id"] = lg["outcome_id"] - 1
            out["exhausted"] = False
            break
        oid = lg["outcome_id"]
        rows = rows_by_leg.get(oid, [])
        pre = [r for r in rows if boundary is None or r["id"] <= boundary]
        post = [r for r in rows if boundary is not None and r["id"] > boundary]
        # A leg with rows only above the bound is the fixed writer's own Under
        # history and is left alone, unless those rows read as the Over price:
        # then it is reported, never planned (the era bound does not clear it).
        if not pre and not testify(post)["equal"]:
            continue
        out["legs_with_history_rows"] += 1
        sibs = sib_of[oid]
        tally = testify(pre or post)
        if len(sibs) != 1:
            verdict, reason = AMBIGUOUS, ("no_over_sibling" if not sibs
                                          else "multiple_over_siblings")
        elif not pre:
            verdict, reason = AMBIGUOUS, "post_fix_only_reads_as_over"
        else:
            verdict, reason = classify_testimony(tally)
            if verdict == INVERTED and post and testify(post)["equal"]:
                verdict, reason = AMBIGUOUS, "post_fix_row_reads_as_over"

        opening = cp = None
        if verdict == INVERTED:
            o_act, o_how = opening_derivation(lg, pre)
            if o_act == "ambiguous":
                verdict, reason = AMBIGUOUS, o_how
            else:
                c_how = cp_candidates(lg, pre, o_act == "withdraw")
                if c_how:
                    kept = (await session.execute(text(_KEPT_VALUE_SQL), {
                        "oid": oid, "removed": [r["id"] for r in pre],
                        "v": _f(lg["calibration_probability"]), "tol": VALUE_TOL,
                    })).scalar_one()
                    if kept:
                        verdict, reason = AMBIGUOUS, "cp_matches_a_kept_row"
                    else:
                        cp = c_how
                opening = o_how if o_act == "withdraw" else None

        _count(out["verdicts"], verdict)
        if reason:
            _count(out["ambiguous_reasons"], reason)
        example = {
            "outcome_id": oid, "market_id": lg["market_id"], "name": lg.get("name"),
            "market_status": lg.get("market_status"), "over_sibling": sibs,
            "testimony": tally, "reason": reason, "rows": len(pre),
            "post_fix_rows": len(post),
            "sample": [_row_view(r) for r in (pre or post)[:_ROW_SAMPLE]],
            "fields": _planned_fields(lg),
            "withdraw_opening": opening, "withdraw_cp": cp,
        }
        if len(out["examples"][verdict]) < _EXAMPLES_PER_CLASS:
            out["examples"][verdict].append(example)
        if verdict != INVERTED:
            continue
        if pinned is not None and oid not in pinned:
            out["withheld_by_only_ids"] += 1
            continue
        out["planned"].append({
            "outcome_id": oid, "market_id": lg["market_id"], "over_sibling": sibs[0],
            "rows": [[r["id"], r["captured_at"].isoformat(), str(r["probability"])]
                     for r in pre],
            "prior": _planned_fields(lg),
            "withdraw_opening": opening, "withdraw_cp": cp,
        })
    return out


def _same_prior(now, prior: dict) -> bool:
    return (_f(now.opening_probability) == prior["opening_probability"]
            and now.opening_american_odds == prior["opening_american_odds"]
            and (now.opening_captured_at.isoformat() if now.opening_captured_at else None)
            == prior["opening_captured_at"]
            and now.opening_source == prior["opening_source"]
            and _f(now.calibration_probability) == prior["calibration_probability"])


DRIFT = "drift"
BACKUP_ROWS_MISMATCH = "backup_rows_mismatch"
BACKUP_FIELDS_MISMATCH = "backup_fields_mismatch"


async def _apply_leg(session, p: dict, digest: str) -> Optional[str]:
    """One leg, one transaction. None when written; otherwise the refusal
    reason, with nothing written."""
    oid = p["outcome_id"]
    ids = [r[0] for r in p["rows"]]
    locked = (await session.execute(text(_LOCK_ROWS), {"ids": ids, "oid": oid})).all()
    now_rows = sorted([[r.id, r.captured_at.isoformat(), str(r.probability)] for r in locked])
    if now_rows != sorted(p["rows"]):
        await session.rollback()
        return DRIFT
    fields = (await session.execute(text(_LOCK_FIELDS), {"oid": oid})).one_or_none()
    if fields is None or not _same_prior(fields, p["prior"]):
        await session.rollback()
        return DRIFT
    # Every copy is checked before the first DELETE or UPDATE.
    await session.execute(text(_BAK_ROWS_COPY), {"ids": ids, "oid": oid, "plan_hash": digest})
    unpaired = (await session.execute(text(_BAK_ROWS_UNPAIRED), {"ids": ids, "oid": oid})).all()
    if unpaired:
        await session.rollback()
        return BACKUP_ROWS_MISMATCH
    wo, wc = bool(p["withdraw_opening"]), bool(p["withdraw_cp"])
    if wo or wc:
        await session.execute(text(_BAK_FIELDS_COPY),
                              {"oid": oid, "wo": wo, "wc": wc, "plan_hash": digest})
        paired = (await session.execute(text(_BAK_FIELDS_PAIRED),
                                        {"oid": oid, "wo": wo, "wc": wc})).scalar_one()
        if not paired:
            await session.rollback()
            return BACKUP_FIELDS_MISMATCH
    deleted = (await session.execute(text(_DELETE_ROWS), {"ids": ids, "oid": oid})).rowcount
    if deleted != len(ids):
        await session.rollback()
        return DRIFT
    if wo:
        await session.execute(text(_WITHDRAW_OPENING), {"oid": oid})
    if wc:
        await session.execute(text(_WITHDRAW_CP), {"oid": oid})
    await session.commit()
    return None


async def _set_bounds(session) -> None:
    await session.execute(text("SET LOCAL statement_timeout = '20s'"))
    await session.execute(text("SET LOCAL lock_timeout = '2s'"))


async def repair(
    session,
    apply: bool = False,
    limit: Optional[int] = None,
    after_id: Optional[int] = None,
    only_ids: Optional[str] = None,
    plan_hash: Optional[str] = None,
) -> dict[str, Any]:
    """Plan (and with ``apply`` + the plan's own hash, write) one page of `_no`
    legs. Dry-run by default."""
    started = time.monotonic()
    scan = max(1, min(int(limit or DEFAULT_SCAN), MAX_SCAN))
    cursor = int(after_id or 0)
    boundary = PRE_FIX_MAX_SNAPSHOT_ID
    base = {"issue": ISSUE, "apply": apply, "after_id": cursor, "limit": scan,
            "pre_fix_max_snapshot_id": boundary,
            "boundary": "pinned" if boundary is not None else "unpinned",
            "backup_tables": [BAK_ROWS, BAK_FIELDS],
            "restore_command": restore_command()}
    try:
        pinned = parse_only_ids(only_ids)
    except ValueError as e:
        return {**base, "terminal": "refused_bad_only_ids", "detail": str(e),
                "legs_written": 0}
    if apply and boundary is None:
        return {**base, "terminal": "refused_boundary_unpinned", "legs_written": 0,
                "detail": "PRE_FIX_MAX_SNAPSHOT_ID must be pinned from the production "
                          "read in its comment before any apply"}
    if apply and not plan_hash:
        return {**base, "terminal": "refused_no_plan_hash", "legs_written": 0,
                "detail": "run the dry run with the same after_id/limit/only_ids "
                          "and pass its plan_hash"}

    await _set_bounds(session)
    plan = await _plan_page(session, cursor, scan, pinned, boundary, started)
    digest = plan_hash_for(plan["planned"], boundary)
    planned = plan["planned"]
    summary = {
        **base,
        "only_ids": sorted(pinned) if pinned is not None else None,
        "legs_examined": plan["legs_examined"],
        "legs_with_history_rows": plan["legs_with_history_rows"],
        "verdicts": plan["verdicts"],
        "ambiguous_reasons": plan["ambiguous_reasons"],
        "legs_planned": len(planned),
        "rows_planned": sum(len(p["rows"]) for p in planned),
        "openings_planned": sum(1 for p in planned if p["withdraw_opening"]),
        "cp_planned": sum(1 for p in planned if p["withdraw_cp"]),
        "withheld_by_only_ids": plan["withheld_by_only_ids"],
        "planned_outcome_ids": [p["outcome_id"] for p in planned],
        "examples": plan["examples"],
        "stopped_on": plan["stopped_on"],
        "exhausted": plan["exhausted"],
        "next_after_id": plan["next_after_id"],
        "plan_hash": digest,
        "legs_written": 0,
        "drift_refused": 0,
        "backup_refused": 0,
        "refused_legs": [],
    }
    if not apply:
        await session.rollback()
        return {**summary, "terminal": "dry_run"}
    if plan_hash != digest:
        await session.rollback()
        return {**summary, "terminal": "refused_plan_drift",
                "detail": {"reviewed": plan_hash, "now": digest}}

    await session.commit()
    if planned:
        await session.execute(text(_BAK_ROWS_CREATE))
        await session.execute(text(_BAK_FIELDS_CREATE))
        await session.commit()
    written = drift = backup = 0
    refused: list[dict] = []
    for p in planned:
        await _set_bounds(session)
        try:
            reason = await _apply_leg(session, p, digest)
        except Exception as e:  # noqa: BLE001 — one leg never stops its siblings
            await session.rollback()
            logger.warning("%s leg %s refused: %s", ISSUE, p["outcome_id"], e)
            reason = "error"
        if reason is None:
            written += 1
            continue
        refused.append({"outcome_id": p["outcome_id"], "reason": reason})
        if reason in (BACKUP_ROWS_MISMATCH, BACKUP_FIELDS_MISMATCH):
            backup += 1
            logger.warning("%s leg %s refused: an existing backup is not this run's "
                           "locked prior (%s); nothing withdrawn", ISSUE, p["outcome_id"],
                           reason)
        else:
            drift += 1
    if written:
        logger.warning(
            "%s withdrew the Over-token history from %s Under legs (%s refused on "
            "drift, %s on backup mismatch). Backup in %s / %s. D51 undo:\n%s",
            ISSUE, written, drift, backup, BAK_ROWS, BAK_FIELDS, restore_command(),
        )
    return {**summary, "terminal": "applied", "legs_written": written,
            "drift_refused": drift, "backup_refused": backup, "refused_legs": refused}


async def restore(session, apply: bool = False) -> dict[str, Any]:
    """Put back every row and field this rail withdrew, where nothing replaced it."""
    have_rows = (await session.execute(text(_EXISTS), {"t": BAK_ROWS})).scalar_one()
    have_fields = (await session.execute(text(_EXISTS), {"t": BAK_FIELDS})).scalar_one()
    if not (have_rows or have_fields):
        return {"issue": ISSUE, "terminal": "refused_no_backup",
                "backup_tables": [BAK_ROWS, BAK_FIELDS], "restored_rows": 0,
                "restored_openings": 0, "restored_cp": 0}
    out: dict[str, Any] = {"issue": ISSUE, "backup_tables": [BAK_ROWS, BAK_FIELDS]}
    if have_rows:
        c = (await session.execute(text(_ROWS_CENSUS))).one()
        out.update(rows_backed_up=int(c.backed_up), rows_present=int(c.present),
                   rows_restorable=int(c.restorable),
                   # A different row now holds the same leg and second.
                   rows_collide=int(c.backed_up) - int(c.present) - int(c.restorable))
    if have_fields:
        c = (await session.execute(text(_FIELDS_CENSUS))).one()
        out.update(openings_backed_up=int(c.openings_backed_up),
                   openings_restorable=int(c.openings_restorable),
                   cp_backed_up=int(c.cp_backed_up), cp_restorable=int(c.cp_restorable))
    if not apply:
        await session.rollback()
        return {**out, "terminal": "dry_run", "restored_rows": 0,
                "restored_openings": 0, "restored_cp": 0}
    rows = openings = cps = 0
    if have_rows:
        rows = (await session.execute(text(_ROWS_RESTORE))).rowcount or 0
    if have_fields:
        openings = (await session.execute(text(_OPENING_RESTORE))).rowcount or 0
        cps = (await session.execute(text(_CP_RESTORE))).rowcount or 0
    await session.commit()
    logger.warning("%s restore: %s rows, %s openings, %s calibration prices put back",
                   ISSUE, rows, openings, cps)
    return {**out, "terminal": "restored", "restored_rows": rows,
            "restored_openings": openings, "restored_cp": cps}
