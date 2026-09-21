"""Confirm the guard-test specimen on its real production rows.

Two questions, because a guard built on a card the feed already refuses cannot
fail for the reason it claims (which is how the invented Buffalo ladder got
through the first draft):

  1. Is guard 1 the ONLY thing declining the clause on this field? (Run the
     shipped function both ways.)
  2. Does this card reach a reader at all? (`classify_market_quality` — a
     numeric rung ladder is `is_ladder_or_bucket` and the feed suppresses it.)
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
from app.utils.feed_market_quality import (  # noqa: E402
    classify_fabricated_book,
    classify_market_quality,
)

with open(
    os.path.join(os.path.dirname(__file__), "nonexclusive_specimens.json")
) as fh:
    d = json.load(fh)
rows = [dict(zip(d["columns"], r)) for r in d["rows"]]
by = {}
for r in rows:
    by.setdefault(r["market_id"], []).append(r)

for mid, legs in sorted(by.items()):
    triples = [
        (
            float(x["p"]),
            None if x["b"] is None else float(x["b"]),
            None if x["a"] is None else float(x["a"]),
        )
        for x in legs
    ]
    is_excl = legs[0]["group_type"] == "negrisk"
    ship = classify_fabricated_book(triples, is_exclusive=is_excl, field_is_mutually_exclusive=False)
    bare = classify_fabricated_book(triples, is_exclusive=is_excl, field_is_mutually_exclusive=True)
    q = classify_market_quality(
        market_name=legs[0]["mname"],
        outcome_names=[x["name"] for x in legs],
    )
    only_guard1 = ship != bare
    kept_bare = [x["name"] for x, k in zip(legs, bare[0]) if k]
    print(
        f"{mid} {str(legs[0]['mname'])[:52]:54} "
        f"guard1_is_only_defence={str(only_guard1):5} "
        f"ladder_or_bucket={str(q.is_ladder_or_bucket):5} "
        f"reaches_a_card={str(not q.is_ladder_or_bucket):5}"
    )
    if only_guard1:
        print(f"      without it the card would be led by {kept_bare[0]!r}"
              f" instead of {legs[0]['name']!r}")
