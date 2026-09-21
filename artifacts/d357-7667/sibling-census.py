"""#7667 — price the DEADLINE-question widening at every site the ONE predicate feeds.

`cumulative_outcome_ladder` is one predicate read by four reader-visible sites:

  1. `feed._outcomes_are_cumulative_ladder` -> `_feed_display_scale`  — THE DIVISOR (the ship)
  2. `outcome_display.drop_incoherent_ladder_outcomes`                — which bars a card draws
  3. `outcome_display.ladder_treatment_collapsed`                     — whether the field draws AT ALL
  4. `futures_highlights.leader_is_ladder_rung` / `feed._leader_is_ladder_rung` — the leader COPY

All four already pass `question=` (#7674), so this widening reaches them with no
new wiring — which is exactly why it has to be priced at all four before it lands
rather than after.

═══ THREE THINGS THIS INSTRUMENT DOES DELIBERATELY ═══

**BEFORE IS THIS TREE WITH ONE READER STUBBED, NOT A DIFFERENT TREE.** The BEFORE
arm stubs `question_ladder_date_word` to `None` and nothing else. So the delta it
reports is #7667's ALONE: #7674's magnitude grammar is live in both arms, and a
card the strike fix already repaired cannot be re-counted here as this fix's work.

**IT NEVER REFETCHES A FEED CARD.** Arm A reads the payloads banked under
/tmp/d349_pages_after. A looping probe books HTTP 429 as "this market has no
page", which is how #7641's own offer under-claimed by two cards.

**ARM B IS THE POPULATION, NOT THE FEED.** A widening lands on the predicate, so
the 102 cards on page one are not its blast radius. Arm B pulls every OPEN market
whose name could possibly match — a SQL superset (two consecutive underscores or
dots) filtered by the real Python regex — and prices the whole set. A market whose
name cannot match is byte-identical by construction: `question_ladder_date_word`
returns `None` and the leg falls through the same branches it falls through today.

Run:  source ~/.claude/.env && python3 artifacts/d357-7667/sibling-census.py
"""
import glob
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from app.utils import ladder_monotonicity  # noqa: E402
from app.utils.ladder_monotonicity import cumulative_outcome_ladder  # noqa: E402
from app.utils import outcome_display  # noqa: E402

drop_incoherent_ladder_outcomes = outcome_display.drop_incoherent_ladder_outcomes
ladder_treatment_collapsed = outcome_display.ladder_treatment_collapsed

API = os.environ["BAINLUCK_API"]
TOK = os.environ["ADMIN_TOKEN"]

NAME = lambda o: o["name"]              # noqa: E731
PROB = lambda o: o["probability"]       # noqa: E731

_REAL_DATE_WORD = ladder_monotonicity.question_ladder_date_word


class before_7667:
    """`question_ladder_date_word` -> None, and nothing else changed.

    Rebound on the MODULE object, because `_cumulative_leg_parts` and
    `cumulative_outcome_ladder` resolve it through the module's own globals; a
    flat import here would bind a name neither of them consults.
    """

    def __enter__(self):
        ladder_monotonicity.question_ladder_date_word = lambda _q: None

    def __exit__(self, *_exc):
        ladder_monotonicity.question_ladder_date_word = _REAL_DATE_WORD


def scale(rows):
    """`_feed_display_scale`'s arithmetic on the rows, gate excluded.

    Verbatim from d353's census so the two runs report one number.
    """
    top = [r for r in rows[:3] if r["probability"]]
    if not top:
        return 1.0
    s = sum(r["probability"] for r in rows if r["probability"])
    return 1.0 if (s <= (1.01 if len(top) == 2 else 1.05) or s > 2.0) else s


def four_sites(rows, question):
    """The four verdicts, as a comparable tuple."""
    ladder = cumulative_outcome_ladder(
        [{"name": r["name"]} for r in rows], dates=True,
        question=question) is not None
    return (
        ladder,
        1.0 if ladder else scale(rows),
        tuple(sorted(drop_incoherent_ladder_outcomes(rows, NAME, PROB, question)[0])),
        ladder_treatment_collapsed(rows, NAME, PROB, question),
    )


def price(subjects):
    """`{id: (question, rows)}` -> the per-site flip lists."""
    flips = {"ladder": [], "divisor": [], "bars": [], "collapse": [], "leader": []}
    for mid, (question, rows) in sorted(subjects.items()):
        with before_7667():
            was = four_sites(rows, question)
        now = four_sites(rows, question)
        if was[0] != now[0]:
            flips["ladder"].append((mid, question[:56]))
            flips["leader"].append((mid, question[:56]))
        if was[1] != now[1]:
            lead = max((r["probability"] or 0) for r in rows)
            flips["divisor"].append(
                (mid, question[:50], round(was[1], 3), round(now[1], 3),
                 round(abs(lead / was[1] - lead / now[1]) * 100, 1)))
        if was[2] != now[2]:
            flips["bars"].append((mid, question[:56]))
        if was[3] != now[3]:
            flips["collapse"].append((mid, question[:56]))
    return flips


def report(title, read, flips):
    print(f"\n=== {title} · {read} read ===\n")
    print(f"  predicate flips to LADDER      : {len(flips['ladder'])}")
    print(f"  divisor MOVES (reader-visible) : {len(flips['divisor'])}")
    print(f"  bars change (rung drop)        : {len(flips['bars'])}")
    print(f"  fields collapse                : {len(flips['collapse'])}")
    print(f"  leader copy flips              : {len(flips['leader'])}\n")
    for mid, q, b, a, pts in sorted(flips["divisor"], key=lambda r: -r[4]):
        print(f"  REPAIRED  {mid:<10} {pts:>5}pt   divisor {b} -> {a}   {q!r}")
    moved = {d[0] for d in flips["divisor"]}
    for mid, q in flips["ladder"]:
        if mid not in moved:
            print(f"  flip/no-op {mid:<10} {q!r}")
    for mid, q in flips["bars"]:
        print(f"  BARS      {mid:<10} {q!r}")
    for mid, q in flips["collapse"]:
        print(f"  COLLAPSE  {mid:<10} {q!r}")


def db(sql, limit=500):
    """One read-only db-query. A truncated answer is LOUD, never silently short."""
    body = json.dumps({"sql": sql, "limit": limit})
    out = subprocess.run(
        ["curl", "-s", "-H", f"Authorization: Bearer {TOK}",
         "-H", "Content-Type: application/json", "-d", body,
         f"{API}/api/admin/db-query"],
        capture_output=True, text=True, check=True).stdout
    payload = json.loads(out)
    if payload.get("truncated"):
        raise SystemExit(f"TRUNCATED at {limit} rows — chunk harder:\n  {sql[:120]}")
    return payload["rows"]


# ── ARM A — the 102 banked feed cards, the reader's page one ────────────────
#
# THE MARKET NAME COMES FROM THE DATABASE, NOT THE PAGE PAYLOAD, for the reason
# d352's census already gives about the LEG text: `/api/futures/{id}` serves a
# HUMANIZED name and the feed path passes `market.name` off the ORM. They are
# different strings on exactly this population — the specimen is stored
# `Next Muse Spark (1.4+) released by...?` and served `... released?` — so
# asking the grammar about the served one measures the humanizer and silently
# under-counts. The first run of this arm did that and reported 0.
cards = {}
banked = {}
for path in sorted(glob.glob("/tmp/d349_pages_after/*.json")):
    with open(path) as handle:
        d = json.load(handle)
    if not isinstance(d, dict):
        continue
    rows = [{"name": o.get("name") or "", "probability": o.get("probability")}
            for o in (d.get("outcomes") or [])]
    if len(rows) >= 2:
        banked[os.path.basename(path)[:-5]] = rows

orm_names = {}
card_ids = sorted(banked)
for start in range(0, len(card_ids), 60):
    chunk = card_ids[start:start + 60]
    for mid, name in db("SELECT id::text, name FROM futures_markets "
                        f"WHERE id IN ({','.join(chunk)})", limit=5000):
        orm_names[mid] = name
absent = [mid for mid in card_ids if mid not in orm_names]
if absent:
    print(f"[arm A] {len(absent)} banked cards have no futures_markets row"
          f" (reported, never silently dropped): {absent[:8]}")
cards = {mid: (orm_names[mid], rows) for mid, rows in banked.items()
         if mid in orm_names}
report("#7667 arm A · banked FEED cards (ORM names)", len(cards), price(cards))

# ── ARM B — the whole population the widening can reach ─────────────────────
# The SQL is a SUPERSET (any two consecutive underscores or dots); the real
# Python predicate does the deciding, so the census can never be narrower than
# the code it is measuring.
#
# POSIX regex, NOT `LIKE`: in a LIKE pattern `_` is a single-character wildcard,
# so `'%__%'` means "any two characters" and matches all 32,727 open markets.
# The first run of this census truncated on exactly that — the trap #7674's own
# body names, walked into one file over.
names = db(r"""SELECT id::text, name FROM futures_markets
               WHERE status='open' AND name ~ '(_{2,}|\.{2,})'
               ORDER BY id""", limit=5000)
candidates = [
    (mid, name) for mid, name in names if _REAL_DATE_WORD(name) is not None]
print(f"\n[arm B] {len(names)} open names in the SQL superset"
      f" -> {len(candidates)} the real regex reads as a deadline question")

subjects = {}
ids = [mid for mid, _ in candidates]
by_id = dict(candidates)
for start in range(0, len(ids), 60):
    chunk = ids[start:start + 60]
    rows = db(f"""SELECT market_id::text, name, current_probability::text
                  FROM futures_outcomes WHERE market_id IN ({','.join(chunk)})""",
              limit=5000)
    for mid, leg, prob in rows:
        subjects.setdefault(mid, (by_id[mid], []))[1].append(
            {"name": leg or "",
             "probability": float(prob) if prob not in (None, "None") else None})

missing = set(ids) - set(subjects)
if missing:
    print(f"[arm B] {len(missing)} candidate markets returned NO outcome rows"
          f" (reported, never silently dropped): {sorted(missing)[:8]}")
for mid in list(subjects):
    subjects[mid][1].sort(key=lambda r: -(r["probability"] or 0))
    if len(subjects[mid][1]) < 2:
        del subjects[mid]

flips_b = price(subjects)
report("#7667 arm B · OPEN deadline-question population", len(subjects), flips_b)

with open(os.path.join(os.path.dirname(__file__), "census.json"), "w") as out:
    json.dump({"arm_b_candidates": len(candidates),
               "arm_b_priced": len(subjects), **flips_b}, out, indent=1)
