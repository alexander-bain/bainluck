"""Offline census: does the NAME-site family key identify ONE ladder on Polymarket?

CAL-P133 built ``app/utils/ladder_monotonicity`` and measured its NAME site on
``polymarket/tech``, where every rung market carries its own subject in its own
name ("Will OpenAI's valuation hit (HIGH) $1.0T by December 31?"). CAL-P134
parked "run ``--by mono`` on the rest of the board" and named four Polymarket
cells as the remaining value: baseball (rank 1), esports (rank 3), soccer
(rank 4), basketball (rank 11).

Those four cells do not write tech's grammar. Polymarket writes SUB-MARKETS of
an event, and a sub-market's name is frequently context-free::

    Map 1 Total Rounds: Over/Under 24.5     <- which match? the name cannot say
    Map 1 Total Rounds: Over/Under 21.5     <- a DIFFERENT match, same 3 words
    O/U 52.5                                <- which game?

``blanked_key`` replaces the rung span and casefolds, so both esports names
collapse to ``map 1 total rounds: over/under <rung>`` — one family key spanning
two unrelated matches. That is the hazard the module's own docstring names, and
``read_name_ladders`` has exactly one guard against it: ``duplicate_values``,
which fires when two rows land on the SAME rung value and makes the family
ambiguous, hence never condemned.

**That guard is blind to the case that matters here.** Two unrelated matches
contributing DISJOINT rungs — match A prices only O/U 21.5, match B only
O/U 24.5 — produce a two-rung family with no duplicate value at all. The law
then compares match A's price against match B's, and any ordering it dislikes is
condemned. Nothing in the census output distinguishes that from a real
violation. It is lesson 16 pointing the other way: not an instrument blind to a
book, but an instrument that manufactures a finding and reports it as one.

So this script measures, offline and on the raw cell, the one number a fold of
these cells needs before any of its output can be believed:

  1. how many NAME-site families the shipped key builds, and how many are
     multi-rung and non-ambiguous — i.e. eligible to be condemned;
  2. of those, how many span MORE THAN ONE Polymarket event identity — the
     manufactured share. Polymarket hands us that identity directly:
     ``group_id`` is ``polymarket:{event.id}`` for multi-market events, with
     ``event_id`` as the linked-game fallback;
  3. the same counts under a key REFINED by that identity, so the size of the
     correction is measured rather than asserted.

The law itself is never restated here. ``ladder_report``, ``read_name_ladders``,
``condemned_families`` and ``monotonicity_violations`` are imported from the
shipped module; the only thing this file adds is the identity join and the
comparison between the two keys.

⚠️ Its counts are RAW-CELL counts. Lesson 19: the published population is a
different and much smaller thing, and only the exact rail can measure it. This
script decides whether a fold is worth running and whether its output can be
read — it does not decide a rule.

Usage:  python3 artifacts/cal-p135/polymarket-name-ladder-census.py <category> [...]
"""
import collections
import gzip
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from app.utils.ladder_monotonicity import (  # noqa: E402
    condemned_families,
    monotonicity_violations,
    name_rungs,
    read_name_ladders,
)

API = os.environ["BAINLUCK_API"]
TOK = os.environ["ADMIN_TOKEN"]
CAP = 1000
HERE = os.path.dirname(os.path.abspath(__file__))


def q(sql, limit=CAP):
    r = subprocess.run(
        ["curl", "-s", "-X", "POST", f"{API}/api/admin/db-query",
         "-H", f"Authorization: Bearer {TOK}", "-H", "Content-Type: application/json",
         "-d", json.dumps({"sql": sql, "limit": limit})],
        capture_output=True, text=True)
    try:
        return json.loads(r.stdout)
    except Exception:
        raise RuntimeError(r.stdout[:400])


# One row per market: the YES leg's price, plus the two identity columns.
# Shaped to match MONO_ROWS_SQL in calibration_cell_exact.py so the census and
# the rail see the same population, with group_id/event_id carried alongside.
ROWS_SQL = """
SELECT fm.id AS market_id,
       MAX(fm.name) AS name,
       MAX(fm.group_id) AS group_id,
       MAX(fm.event_id) AS event_id,
       MAX(CASE WHEN lower(btrim(fo.name)) = 'yes'
                THEN COALESCE(fo.calibration_probability, fo.opening_probability)
           END) AS yes_price
FROM futures_markets fm
JOIN futures_outcomes fo ON fo.market_id = fm.id
WHERE fm.source = 'polymarket'
  AND COALESCE(fm.llm_sport_category, 'uncategorized') = '{cat}'
  AND fm.id >= {lo} AND fm.id < {hi}
GROUP BY fm.id
"""


def pull(cat, lo, hi, depth=0):
    """Rows in an id range, halving on the 1000-row cap (never trust exactly CAP)."""
    d = q(ROWS_SQL.format(cat=cat, lo=lo, hi=hi))
    if "rows" in d and d.get("row_count", CAP) < CAP:
        return d["rows"]
    if hi - lo <= 1 or depth > 30:
        raise RuntimeError(f"irreducible {lo}-{hi}")
    mid = lo + (hi - lo) // 2
    return pull(cat, lo, mid, depth + 1) + pull(cat, mid, hi, depth + 1)


def load_rows(cat):
    """Cached row pull. Ten minutes of production load buys free re-analysis."""
    path = os.path.join(HERE, f"rows-polymarket-{cat}.json.gz")
    if os.path.exists(path):
        with gzip.open(path, "rt") as fh:
            return json.load(fh)
    rng = q("SELECT MIN(id), MAX(id) FROM futures_markets WHERE source='polymarket'", limit=5)
    lo, hi = rng["rows"][0]
    rows, e, n = [], lo, 0
    width = 1_000_000
    while e <= hi:
        nxt = min(e + width, hi + 1)
        n += 1
        print(f"    pull [{n}] ids {e}-{nxt}", file=sys.stderr, flush=True)
        rows.extend(pull(cat, e, nxt))
        e = nxt
    with gzip.open(path, "wt") as fh:
        json.dump(rows, fh)
    return rows


def identity(row):
    """The Polymarket event a market belongs to.

    ``group_id`` is ``polymarket:{event.id}`` for multi-market events and is the
    authority when present; ``event_id`` is the linked-game fallback. A market
    with neither gets a per-market identity, which is the conservative choice:
    it can never be the thing that MERGES two families.
    """
    gid, eid, mid = row["group_id"], row["event_id"], row["market_id"]
    if gid:
        return f"g:{gid}"
    if eid:
        return f"e:{eid}"
    return f"m:{mid}"


#: The rung shape the four Polymarket sports cells actually write, which NO
#: grammar in ``NAME_GRAMMARS`` parses. Used ONLY to size the instrument's
#: refusals — never to condemn anything. An all-clear that cannot tell itself
#: apart from blindness is the failure CAL-P134 paid a session for (lesson 16),
#: so the census reports what the grammar could not see next to what it found.
OU_RE = re.compile(r"(?:\bO/U\b|\bOver\s*/\s*Under\b)\s*(\d+(?:\.\d+)?)", re.I)
SPREAD_RE = re.compile(r"\(([+-]\d+(?:\.\d+)?)\)")


def blindness(rows):
    """What the NAME site could not see, and how much ladder was in it.

    Three numbers, because the two sites fail independently and a reader who
    sees only one will draw the wrong conclusion:

    ``names_with_ou_rung`` — markets whose name carries an O/U rung.
    ``parsed_by_name_grammars`` — markets any shipped grammar parsed at all.
    ``ou_markets_with_yes_leg`` — the PRICE site's own blindness: an O/U market
    prices ``Over``/``Under`` legs, not a ``yes`` leg, so ``MONO_ROWS_SQL``
    reads its price as NULL and drops the row before the grammar ever runs.

    ``ou_families_multi_rung`` sizes the ladder book that is being missed, using
    the event identity so the count is of REAL ladders rather than of collapses.
    """
    ou = [r for r in rows if r["name"] and OU_RE.search(r["name"])]
    fam = collections.defaultdict(set)
    name_only = collections.defaultdict(set)
    for r in ou:
        m = OU_RE.search(r["name"])
        key = (r["name"][:m.start(1)] + "<RUNG>" + r["name"][m.end(1):]).casefold().strip()
        fam[(key, identity(r))].add(float(m.group(1)))
        name_only[key].add(identity(r))
    multi = {k: v for k, v in fam.items() if len(v) >= 2}
    spanning = {k for k, v in name_only.items() if len(v) > 1}
    return {
        "names_with_ou_rung": len(ou),
        "names_with_spread_rung": sum(
            1 for r in rows if r["name"] and SPREAD_RE.search(r["name"])),
        "parsed_by_name_grammars": sum(
            1 for r in rows if r["name"] and name_rungs(r["name"])),
        "ou_names_parsed_by_name_grammars": sum(
            1 for r in ou if name_rungs(r["name"])),
        "ou_markets_with_yes_leg": sum(1 for r in ou if r["yes_price"] is not None),
        "ou_families_multi_rung_with_identity": len(multi),
        "ou_name_only_keys": len(name_only),
        "ou_name_only_keys_spanning_multi_event": len(spanning),
        "ou_name_only_keys_spanning_multi_event_pct": round(
            100.0 * len(spanning) / max(1, len(name_only)), 1),
    }


def census(cat):
    raw = load_rows(cat)
    rows = [{"market_id": r[0], "name": r[1], "group_id": r[2],
             "event_id": r[3], "yes_price": r[4]} for r in raw]
    priced = [r for r in rows if r["name"] and r["yes_price"] is not None]

    ident = {r["market_id"]: identity(r) for r in rows}

    # --- the shipped key, exactly as --by mono would build it ---------------
    ladders = read_name_ladders(priced)
    condemned = condemned_families(ladders)
    multi = {k: v for k, v in ladders.items() if len(v["rungs"]) >= 2}
    ambiguous = {k for k, v in ladders.items() if v["duplicate_values"]}
    eligible = {k: v for k, v in multi.items() if k not in ambiguous}

    def spans(key):
        return {ident[m] for m in ladders[key]["member_ids"] if m in ident}

    eligible_multi_ctx = {k for k in eligible if len(spans(k)) > 1}
    condemned_multi_ctx = {k for k in condemned if len(spans(k)) > 1}

    viol_total = sum(len(monotonicity_violations(v["rungs"], k[1]))
                     for k, v in eligible.items())
    viol_multi_ctx = sum(len(monotonicity_violations(v["rungs"], k[1]))
                         for k, v in eligible.items() if k in eligible_multi_ctx)

    # --- the refined key: identity is part of the family --------------------
    # Rebuilt by partitioning rows on identity and grouping WITHIN each, which
    # is the same law applied to a population the key can actually identify.
    by_ident = collections.defaultdict(list)
    for r in priced:
        by_ident[ident[r["market_id"]]].append(r)
    r_condemned = r_eligible = r_viol = 0
    r_drop = set()
    for ctx, group in by_ident.items():
        lad = read_name_ladders(group)
        cond = condemned_families(lad)
        amb = {k for k, v in lad.items() if v["duplicate_values"]}
        elig = {k: v for k, v in lad.items()
                if len(v["rungs"]) >= 2 and k not in amb}
        r_eligible += len(elig)
        r_condemned += len(cond)
        r_viol += sum(len(monotonicity_violations(v["rungs"], k[1]))
                      for k, v in elig.items())
        for k in cond:
            r_drop.update(lad[k]["member_ids"])

    drop = set()
    for k in condemned:
        drop.update(ladders[k]["member_ids"])

    return {
        "category": cat,
        "markets_total": len(rows),
        "markets_priced": len(priced),
        "blindness": blindness(rows),
        "shipped_key": {
            "families": len(ladders),
            "families_multi_rung": len(multi),
            "families_ambiguous": len(ambiguous),
            "families_eligible": len(eligible),
            "families_condemned": len(condemned),
            "violation_pairs": viol_total,
            "markets_dropped": len(drop),
        },
        "cross_event_collapse": {
            "eligible_spanning_multi_event": len(eligible_multi_ctx),
            "eligible_spanning_multi_event_pct": round(
                100.0 * len(eligible_multi_ctx) / max(1, len(eligible)), 1),
            "condemned_spanning_multi_event": len(condemned_multi_ctx),
            "condemned_spanning_multi_event_pct": round(
                100.0 * len(condemned_multi_ctx) / max(1, len(condemned)), 1),
            "violation_pairs_from_multi_event": viol_multi_ctx,
            "violation_pairs_from_multi_event_pct": round(
                100.0 * viol_multi_ctx / max(1, viol_total), 1),
        },
        "refined_key": {
            "families_eligible": r_eligible,
            "families_condemned": r_condemned,
            "violation_pairs": r_viol,
            "markets_dropped": len(r_drop),
        },
        "worst_collapsed_families": [
            {"key": k[0][:90], "direction": k[1], "rungs": len(ladders[k]["rungs"]),
             "events_spanned": len(spans(k)),
             "member_ids": sorted(ladders[k]["member_ids"])[:6]}
            for k in sorted(eligible_multi_ctx,
                            key=lambda k: -len(spans(k)))[:8]
        ],
    }


if __name__ == "__main__":
    cats = sys.argv[1:] or ["baseball", "esports", "soccer", "basketball"]
    out = {}
    for cat in cats:
        print(f"=== polymarket/{cat}", file=sys.stderr, flush=True)
        out[cat] = census(cat)
        print(json.dumps(out[cat], indent=2))
    with open(os.path.join(HERE, "name-ladder-collapse.json"), "w") as fh:
        json.dump(out, fh, indent=2)
