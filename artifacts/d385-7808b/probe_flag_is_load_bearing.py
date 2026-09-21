"""Is `field_is_mutually_exclusive` load-bearing on a card that REACHES a reader?

Half two's first ladder guard used a Buffalo total-wins ladder, and the probe
beside this one shows that card never reaches Discover at all: its rungs read as
`numeric_outcome_ladder`, `is_ladder_or_bucket=True`, and the feed suppresses the
family (the audit target is `ladder/bucket-rate@20=0`). A guard built on a card
the feed already refuses cannot fail for the reason it claims.

The cumulative bundles that DO reach a reader are the Polymarket ones already in
the fixture file — SpaceX and NVIDIA, `group_type='polymarket_event'`, prices
that legitimately sum past 100%. This asks whether the flag is what keeps half
two off them, by running the classifier over their real books both ways.
"""

import importlib.util

spec = importlib.util.spec_from_file_location(
    "t", "tests/test_feed_phantom_midpoint_suppression.py"
)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

from app.utils.feed_market_quality import classify_fabricated_book  # noqa: E402


def books(market):
    return [
        (o.current_probability, o.current_yes_bid, o.current_yes_ask)
        for o in market.outcomes
    ]


for name, market in (("spacex", m._spacex()), ("nvidia", m._nvidia()), ("us_open", m._us_open())):
    outs = books(market)
    exclusive = market.group_type == "negrisk"
    off = classify_fabricated_book(outs, is_exclusive=exclusive, field_is_mutually_exclusive=False)
    on = classify_fabricated_book(outs, is_exclusive=exclusive, field_is_mutually_exclusive=True)
    hidden_off = [i for i, k in enumerate(off[0]) if not k]
    hidden_on = [i for i, k in enumerate(on[0]) if not k]
    extra = sorted(set(hidden_on) - set(hidden_off))
    print(f"\n{name}: {len(outs)} legs, sum={sum(p for p, _, _ in outs if p is not None):.2f}")
    print(f"  flag False -> {len(hidden_off)} hidden, drop_card={off[1]}")
    print(f"  flag True  -> {len(hidden_on)} hidden, drop_card={on[1]}")
    if extra:
        print("  THE FLAG IS LOAD-BEARING. It alone keeps these legs on the card:")
        for i in extra:
            print(f"    {market.outcomes[i].name!r} p={outs[i][0]} bid={outs[i][1]} ask={outs[i][2]}")
    else:
        print("  flag changes NOTHING on this card — it is not the defence here.")
