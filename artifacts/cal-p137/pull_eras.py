"""Cache the same Polymarket rows as CAL-P136, with the COALESCE SPLIT OPEN.

CAL-P136 reached the O/U book and refused to bank a rule, on the ground that the
package condemns 28-70% of the laddered population and that the holdout reverses
on two cells of four. It parked the obvious next question — WHY — with two
hypotheses it had no budget to test (its README §4, notes item CAL-P136-2):

  (a) the rungs of one family are priced at different TIMES, so the law compares
      a stale rung against a fresh one and calls the pair a reversal;
  (b) ``COALESCE(calibration_probability, opening_probability)`` mixes two ERAS
      inside one family — some rungs carrying a closing/settled price and their
      siblings carrying an opening price — which is (a) with a name, and which
      would explain baseball's 2.6x holdout split directly.

Both are questions about WHERE a rung's price came from, and every measurement
so far has thrown that away: ``MONO_ROWS_SQL`` and CAL-P136's ``pull_rows.py``
both select the COALESCE, which is a single number with no provenance. This
pull selects the two branches SEPARATELY and re-derives the coalesce in Python,
so every row carries both the price the shipped rail sees and the answer to
"which branch produced it".

🔴 THE DERIVED PRICE MUST EQUAL THE CACHED ONE, BYTE FOR BYTE. ``verify_against_
p136`` asserts exactly that against ``artifacts/cal-p136/legs-*.json.gz``. It is
a claim about agreement rather than about truth (lesson 9), but it is the claim
that matters here: if the derived price differs anywhere, this is a DIFFERENT
population from the one CAL-P136 measured and no comparison between the two is
readable (lesson 14).

The as-of columns, for hypothesis (a):

  * ``opening_captured_at`` is a real as-of, but only for the OPEN branch;
  * ``price_changed_at`` (#2024) is populated forward by the polls and reads
    NULL for every row not polled since it shipped, so a NULL here means "never
    observed to change since the column existed", NOT "never changed" — gotcha
    #53, and the analysis must treat it as unknown rather than as a zero;
  * the CAL branch has no as-of at all. That is a measurement ceiling, and
    lesson 21 says a ceiling is not a measurement: where the whole family is on
    the CAL branch, hypothesis (a) is simply UNANSWERABLE from this table and
    the analysis says so instead of inferring one.

⚠️ ``MAX(CASE WHEN ...)`` per leg, exactly as CAL-P136 did. The unique
constraint on ``futures_outcomes`` is ``(market_id, external_id)``, not
``(market_id, name)``, so a market carrying two legs both named ``yes`` would
have its columns combined across rows. ``legs_per_name`` counts that shape so
it is a measured zero rather than an assumption.

Usage:  python3 artifacts/cal-p137/pull_eras.py [category ...]
"""
import gzip
import json
import os
import subprocess
import sys

API = os.environ["BAINLUCK_API"]
TOK = os.environ["ADMIN_TOKEN"]
CAP = 1000
HERE = os.path.dirname(os.path.abspath(__file__))
P136 = os.path.join(HERE, "..", "cal-p136")

#: Same window width CAL-P136 measured as reaching the whole source without an
#: irreducible chunk. The extra columns do not change the ROW count, so they do
#: not change how often the cap is hit or how deep the halving goes.
WIDTH = 1_000_000


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


#: One leg's provenance: both COALESCE branches, plus the two stamps that exist.
def _leg(leg, *, stamps):
    parts = [
        f"""MAX(CASE WHEN lower(btrim(fo.name)) = '{leg}'
                 THEN fo.calibration_probability END) AS {leg}_cal""",
        f"""MAX(CASE WHEN lower(btrim(fo.name)) = '{leg}'
                 THEN fo.opening_probability END) AS {leg}_open""",
    ]
    if stamps:
        parts += [
            f"""MAX(CASE WHEN lower(btrim(fo.name)) = '{leg}'
                     THEN fo.opening_captured_at END) AS {leg}_open_at""",
            f"""MAX(CASE WHEN lower(btrim(fo.name)) = '{leg}'
                     THEN fo.price_changed_at END) AS {leg}_changed_at""",
        ]
    parts.append(
        f"""COUNT(*) FILTER (WHERE lower(btrim(fo.name)) = '{leg}') AS {leg}_legs""")
    return ",\n       ".join(parts)


ROWS_SQL = """
SELECT fm.id AS market_id,
       MAX(fm.name) AS name,
       MAX(fm.group_id) AS group_id,
       MAX(fm.event_id) AS event_id,
       {yes},
       {over},
       {under}
FROM futures_markets fm
JOIN futures_outcomes fo ON fo.market_id = fm.id
WHERE fm.source = 'polymarket'
  AND COALESCE(fm.llm_sport_category, 'uncategorized') = '{cat}'
  AND fm.id >= {lo} AND fm.id < {hi}
GROUP BY fm.id
""".format(yes=_leg("yes", stamps=True), over=_leg("over", stamps=True),
           under=_leg("under", stamps=False), cat="{cat}", lo="{lo}", hi="{hi}")

#: Positional, matching ROWS_SQL. db-query rows are ARRAYS.
COLUMNS = (
    "market_id", "name", "group_id", "event_id",
    "yes_cal", "yes_open", "yes_open_at", "yes_changed_at", "yes_legs",
    "over_cal", "over_open", "over_open_at", "over_changed_at", "over_legs",
    "under_cal", "under_open", "under_legs",
)


def pull(cat, lo, hi, depth=0):
    """Rows in an id range, halving on the 1000-row cap (never trust exactly CAP).

    ⚠️ A missing ``rows`` key is a REFUSAL — a statement timeout returns one, and
    CAL-P136 hit exactly that on one window of ``polymarket/tech``. Halving is
    the right response to a refusal as well as to the cap, but the two must not
    be conflated at the leaf, so an irreducible window RAISES rather than
    returning the empty list a caller would read as a clean zero.
    """
    d = q(ROWS_SQL.format(cat=cat, lo=lo, hi=hi))
    if "rows" in d and d.get("row_count", CAP) < CAP:
        return d["rows"]
    if hi - lo <= 1 or depth > 30:
        raise RuntimeError(f"irreducible {lo}-{hi}: {json.dumps(d)[:300]}")
    mid = lo + (hi - lo) // 2
    return pull(cat, lo, mid, depth + 1) + pull(cat, mid, hi, depth + 1)


def path_for(cat):
    return os.path.join(HERE, f"eras-polymarket-{cat}.json.gz")


def load_rows(cat):
    """Cached row pull. Re-analysis after the first pull is free."""
    path = path_for(cat)
    if os.path.exists(path):
        with gzip.open(path, "rt") as fh:
            return json.load(fh)
    rng = q("SELECT MIN(id), MAX(id) FROM futures_markets WHERE source='polymarket'",
            limit=5)
    lo, hi = rng["rows"][0]
    rows, e, n = [], lo, 0
    while e <= hi:
        nxt = min(e + WIDTH, hi + 1)
        n += 1
        print(f"    pull [{n}] ids {e}-{nxt}", file=sys.stderr, flush=True)
        rows.extend(pull(cat, e, nxt))
        e = nxt
    with gzip.open(path, "wt") as fh:
        json.dump(rows, fh)
    return rows


#: The branch a leg's price came from. Doubles as the COLUMN SUFFIX for the two
#: real branches, so a caller narrowing the book to one branch and a caller
#: labelling a row cannot drift apart. ``None`` — no price at all — is a THIRD
#: state and not a synonym for either.
CAL, OPEN = "cal", "open"

#: 🔴 A FOURTH STATE, and reading the WRITER is what found it.
#: ``backfill_winners.compute_calibration_prices`` does not compute one thing.
#: It has five producers — Part A (last snapshot before the EVENT's
#: commence_time), A2 (before the MARKET's), B (first snapshot ≥1h after
#: opening, i.e. a SETTLED price), C (last non-extreme snapshot before start) —
#: and a Fallback that executes ``SET calibration_probability =
#: fo.opening_probability``. Nothing records which one ran.
#:
#: So a row on the CAL branch is not necessarily a row from the calibration era:
#: where the Fallback produced it, the value IS the opening price and the branch
#: label is a costume. The database keeps no provenance column, but the Fallback
#: leaves a signature — ``calibration_probability = opening_probability`` — and
#: ``backfill_winners`` itself reads that equality as exactly this signal in two
#: separate places (its lines 4498 and 6611). This module classifies it as its
#: own state rather than folding it into either branch.
#:
#: ⚠️ IT IS A SIGNATURE, NOT A PROOF. A genuinely computed closing line that
#: happens to equal the opening price is indistinguishable from a Fallback copy
#: and lands here too. That biases this class LARGE, which is the safe
#: direction for a class being tested as a suspect, and the analysis says so
#: rather than claiming a clean read.
CAL_EQ_OPEN = "cal_eq_open"


def branch(row, leg):
    cal, opening = row.get(f"{leg}_cal"), row.get(f"{leg}_open")
    if cal is not None:
        return CAL_EQ_OPEN if opening is not None and cal == opening else CAL
    if opening is not None:
        return OPEN
    return None


def coalesced(row, leg):
    """``COALESCE(calibration_probability, opening_probability)``, in Python."""
    v = row.get(f"{leg}_cal")
    return v if v is not None else row.get(f"{leg}_open")


def as_dicts(cat):
    """Rows as dicts, carrying BOTH the shipped coalesced price and its branch.

    The ``*_price`` keys are named exactly as ``pull_rows.py`` named them, so
    ``proposition_price`` and ``ladder_report`` read these rows unchanged.
    """
    out = []
    for r in load_rows(cat):
        row = dict(zip(COLUMNS, r))
        for leg in ("yes", "over", "under"):
            row[f"{leg}_price"] = coalesced(row, leg)
            row[f"{leg}_branch"] = branch(row, leg)
        out.append(row)
    return out


def verify_against_p136(cat):
    """Is this the same population, priced identically, as CAL-P136 measured?

    Lesson 14: before a measurement decides anything, check its two halves are
    about the same population. Compares on the raw STRING db-query returns, so a
    float round-trip cannot paper over a real difference.
    """
    p136 = os.path.join(P136, f"legs-polymarket-{cat}.json.gz")
    if not os.path.exists(p136):
        return {"compared": False, "reason": "no cal-p136 cache for this cell"}
    with gzip.open(p136, "rt") as fh:
        old = {r[0]: r for r in json.load(fh)}
    new = {r["market_id"]: r for r in as_dicts(cat)}
    shared = set(old) & set(new)
    structural = [m for m in shared
                  if old[m][1] != new[m]["name"] or old[m][2] != new[m]["group_id"]]
    priced = [m for m in shared
              if (old[m][4], old[m][5], old[m][6]) != (
                  new[m]["yes_price"], new[m]["over_price"], new[m]["under_price"])]
    return {
        "compared": True,
        "p136_rows": len(old),
        "p137_rows": len(new),
        "only_in_p136": len(set(old) - set(new)),
        "only_in_p137": len(set(new) - set(old)),
        # A pull an hour after another pull is allowed to see the pollers'
        # work, so the two mismatch kinds mean opposite things and are counted
        # apart: a moved PRICE is drift and bounds how much of CAL-P136's table
        # this session can hold fixed, while a changed NAME or group_id would
        # mean the identity itself moved and no comparison is readable at all.
        "price_drifted": len(priced),
        "price_drift_pct": round(100.0 * len(priced) / max(1, len(shared)), 3),
        "structurally_mismatched": len(structural),
        "example_structural": structural[:5],
        "ok": (not structural and set(old) == set(new)),
    }


def legs_per_name(cat):
    """The ``MAX(CASE WHEN ...)`` hazard, counted rather than assumed away."""
    over_one = {leg: 0 for leg in ("yes", "over", "under")}
    for row in as_dicts(cat):
        for leg in over_one:
            if (row.get(f"{leg}_legs") or 0) > 1:
                over_one[leg] += 1
    return over_one


if __name__ == "__main__":
    for cat in sys.argv[1:] or ["baseball", "basketball", "esports", "soccer"]:
        print(f"=== polymarket/{cat}", file=sys.stderr, flush=True)
        rows = load_rows(cat)
        print(f"{cat}: {len(rows)} rows -> {path_for(cat)}", flush=True)
    print("PULL COMPLETE", flush=True)
