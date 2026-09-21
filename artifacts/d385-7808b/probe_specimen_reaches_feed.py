"""Does the 40+ Passing Touchdowns specimen actually produce a card in `_run`?

Asked BEFORE the guard is written, because the first draft's ladder guard was
green-by-absence: the card was not in the feed at all, so "the ladder kept its
rung" was never tested.
"""

import asyncio
import importlib.util

spec = importlib.util.spec_from_file_location(
    "t", "tests/test_feed_phantom_midpoint_suppression.py"
)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

LEGS = [
    ("Patrick Mahomes", 0.84, 0.00, 0.85),
    ("Drake Maye", 0.49, 0.00, 0.81),
    ("Joe Burrow", 0.33, 0.00, 0.33),
    ("Jared Goff", 0.245, 0.17, 0.32),
    ("Brock Purdy", 0.20, 0.00, 0.85),
    ("Dak Prescott", 0.15, 0.00, 0.33),
    ("Josh Allen", 0.14, 0.07, 0.21),
    ("Justin Herbert", 0.10, 0.00, 0.85),
    ("Lamar Jackson", 0.08, 0.00, 0.08),
    ("Baker Mayfield", 0.07, 0.00, 0.81),
]


def specimen(me):
    outs = [
        m._Outcome(7100 + i, name, p, bid=b, ask=a)
        for i, (name, p, b, a) in enumerate(LEGS)
    ]
    return m._Market(
        59165029, "Pro Football: 40+ Passing Touchdowns Season", "sports", outs,
        group_type="kalshi_event", mutually_exclusive=me,
    )


for me in (False, True):
    items = asyncio.run(m._run([specimen(me), m._fed()]))
    card = m._card(items, 59165029)
    printed = [o["name"] for o in card["top_outcomes"]] if card else None
    print(f"mutually_exclusive={me!s:5} card={'served' if card else 'ABSENT'} printed={printed}")
