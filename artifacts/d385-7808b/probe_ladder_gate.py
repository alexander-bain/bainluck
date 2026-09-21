"""Which gate drops the Buffalo-total-wins ladder fixture out of the feed?

Not part of the ship. #7808 half two's ladder guard asserted through the whole
feed and the card was absent, and the classifier keeps all four of its legs
either way — so something else in `_score_futures` refuses it. This names that
something before the guard is rewritten, rather than tuning the fixture until it
goes green.
"""

import asyncio
import importlib.util

spec = importlib.util.spec_from_file_location(
    "t", "tests/test_feed_phantom_midpoint_suppression.py"
)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def ladder(cat, gt, name, *, me=False, tier=None):
    outs = [
        m._Outcome(6001, "1+ wins", 1.0, bid=0.0, ask=1.0),
        m._Outcome(6002, "2+ wins", 0.98, bid=0.96, ask=0.99),
        m._Outcome(6003, "5+ wins", 0.72, bid=0.70, ask=0.74),
        m._Outcome(6004, "9+ wins", 0.31, bid=0.29, ask=0.33),
    ]
    mk = m._Market(12230832, name, cat, outs, group_type=gt, mutually_exclusive=me)
    if tier is not None:
        mk.market_tier = tier
    return mk


CASES = [
    ("baseline sports/kalshi_event", ladder("sports", "kalshi_event", "Pro Football: Buffalo Total Wins")),
    ("category tennis", ladder("tennis", "kalshi_event", "Pro Football: Buffalo Total Wins")),
    ("no group_type", ladder("sports", None, "Pro Football: Buffalo Total Wins")),
    ("winner-shaped name", ladder("sports", "kalshi_event", "2027 US Open Men's Singles Winner")),
    ("tier 1", ladder("sports", "kalshi_event", "Pro Football: Buffalo Total Wins", tier=1)),
    ("tier 2", ladder("sports", "kalshi_event", "Pro Football: Buffalo Total Wins", tier=2)),
]

for label, mk in CASES:
    items = asyncio.run(m._run([mk, m._fed()]))
    served = [i["data"]["id"] for i in items if i["type"] == "futures"]
    print(f"{label:34s} tier={getattr(mk,'market_tier',None)!r:5} -> {served}")
