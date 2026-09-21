"""#7674 — price the `question=` widening at every site the ONE predicate feeds.

Reads the payloads d349's AFTER run already banked under /tmp/d349_pages_after
(one `/api/futures/{id}` per feed card). It never refetches: a looping probe
books HTTP 429 as "this market has no page", which is how #7641's own offer
under-claimed by two cards.
"""
import glob, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

from app.utils.ladder_monotonicity import cumulative_outcome_ladder
from app.utils.outcome_display import (
    drop_incoherent_ladder_outcomes, ladder_treatment_collapsed)

NAME = lambda o: o["name"]
PROB = lambda o: o["probability"]

def scale(rows):
    """`_feed_display_scale`'s arithmetic on the rows, gate excluded."""
    top = [r for r in rows[:3] if r["probability"]]
    if not top:
        return 1.0
    s = sum(r["probability"] for r in rows if r["probability"])
    return 1.0 if (s <= (1.01 if len(top) == 2 else 1.05) or s > 2.0) else s

flips = {"ladder": [], "divisor": [], "bars": [], "collapse": [], "leader": []}
read = 0
for path in sorted(glob.glob('/tmp/d349_pages_after/*.json')):
    d = json.load(open(path))
    if not isinstance(d, dict):
        continue
    q = d.get("name") or ""
    rows = [{"name": o.get("name") or "", "probability": o.get("probability")}
            for o in (d.get("outcomes") or [])]
    if len(rows) < 2:
        continue
    read += 1
    mid = os.path.basename(path)[:-5]

    was = cumulative_outcome_ladder(rows, dates=True) is not None
    now = cumulative_outcome_ladder(rows, dates=True, question=q) is not None
    if was != now:
        flips["ladder"].append((mid, q[:56]))
        # the divisor is gated on the predicate, so only a flip can move it
        before = 1.0 if was else scale(rows)
        after = 1.0 if now else scale(rows)
        if before != after:
            lead = rows[0]["probability"] or 0
            flips["divisor"].append(
                (mid, q[:50], round(before, 3), round(after, 3),
                 round(abs(lead/before - lead/after) * 100, 1)))
    # the other two sites, measured directly rather than inferred
    if (drop_incoherent_ladder_outcomes(rows, NAME, PROB)
            != drop_incoherent_ladder_outcomes(rows, NAME, PROB, q)):
        flips["bars"].append((mid, q[:56]))
    if (ladder_treatment_collapsed(rows, NAME, PROB)
            != ladder_treatment_collapsed(rows, NAME, PROB, q)):
        flips["collapse"].append((mid, q[:56]))
    if was != now:
        flips["leader"].append((mid, q[:56]))

print(f"=== #7674 sibling census · {read} feed cards read ===\n")
print(f"  predicate flips to LADDER      : {len(flips['ladder'])}")
print(f"  divisor MOVES (reader-visible) : {len(flips['divisor'])}")
print(f"  bars change (rung drop)        : {len(flips['bars'])}")
print(f"  fields collapse                : {len(flips['collapse'])}")
print(f"  leader copy flips              : {len(flips['leader'])}\n")
for mid, q, b, a, pts in flips["divisor"]:
    print(f"  REPAIRED  {mid:<10} {pts:>5}pt   divisor {b} -> {a}   {q!r}")
for mid, q in flips["ladder"]:
    if mid not in {d[0] for d in flips["divisor"]}:
        print(f"  flip/no-op {mid:<10} {q!r}")
for mid, q in flips["bars"]:
    print(f"  BARS      {mid:<10} {q!r}")
for mid, q in flips["collapse"]:
    print(f"  COLLAPSE  {mid:<10} {q!r}")
json.dump({k: v for k, v in flips.items()},
          open(os.path.join(os.path.dirname(__file__), 'census.json'), 'w'), indent=1)
