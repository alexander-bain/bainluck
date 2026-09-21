"""#6985 — replay the place guard over every cross-source row production SERVES.

A tightened matcher fails SILENTLY: an under-paired spotlight leaves nothing on
the page for a reader to notice. So the gate is not "the specimen is refused" but
"of the rows a reader can see right now, exactly these are lost, and here is each
one read by hand".

Scope is the four surfaces that call `find_cross_source_markets`, and only the
rows they actually serve — not a census of the market table (that is the
measurement lane's, per the routing note).

Usage, from the repo root:
    python3 artifacts/d392-6985/replay_served_pairs.py <pairs.json>

where <pairs.json> is [{surface, q_kalshi, q_poly, delta, ...}, ...] captured
from production.
"""
import json
import sys

sys.path.insert(0, "backend")

from app.utils.cross_source_matching import (  # noqa: E402
    _near_match_signature,
    is_same_question,
    normalize_question,
)

with open(sys.argv[1]) as fh:
    pairs = json.load(fh)

lost, kept = [], []
for p in pairs:
    k, po = p["q_kalshi"], p["q_poly"]
    exact = normalize_question(k) == normalize_question(po)
    ks, ps = _near_match_signature(k), _near_match_signature(po)
    (kept if is_same_question(k, po) else lost).append(
        {**p, "exact_arm": exact, "places": (sorted(ks[3]), sorted(ps[3]))}
    )

print(f"SERVED ROWS READ: {len(pairs)}    KEPT: {len(kept)}    LOST: {len(lost)}")
print()
print("=== LOST — every one of these must be read by hand before this ships ===")
for p in lost or [{}]:
    if not p:
        print("  (none)")
        break
    print(f"  [{p['surface']}] delta {p['delta']}")
    print(f"      kalshi: {p['q_kalshi']}")
    print(f"      poly  : {p['q_poly']}")
    print(f"      places: {p['places'][0]} vs {p['places'][1]}   exact_arm={p['exact_arm']}")
print()
print("=== KEPT ===")
for p in kept:
    print(
        f"  [{p['surface']:14}] delta {str(p['delta']):5} "
        f"{'exact' if p['exact_arm'] else 'near '} "
        f"places {p['places'][0]} vs {p['places'][1]} | {p['q_kalshi'][:58]}"
    )
