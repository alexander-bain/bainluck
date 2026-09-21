"""#6985 — measure the two-sided place guard against every specimen and control.

Run from backend/:  python3 ../artifacts/d392-6985/probe_6985.py
"""
import sys

sys.path.insert(0, ".")

from app.utils.cross_source_matching import (  # noqa: E402
    _conservative_near_match_score,
    _near_match_signature,
    is_same_question,
)

FAILS = []


def show(left, right, want):
    ls, rs = _near_match_signature(left), _near_match_signature(right)
    got = is_same_question(left, right)
    ok = got == want
    if not ok:
        FAILS.append((left, right, want, got))
    print(
        f"{'OK ' if ok else '>>> MISMATCH':12} want={want!s:5} got={got!s:5} | "
        f"{left[:50]:50} | {right[:50]:50} | "
        f"places {sorted(ls[3])} vs {sorted(rs[3])} | "
        f"score={_conservative_near_match_score(ls, rs)}"
    )


print("--- THE ROUTED SPECIMEN AND ITS SIBLING (must REFUSE) ---")
show(
    "How many House seats will Democrats win in Georgia?",
    "How many House seats will the Democrats win in Ohio?",
    False,
)
show(
    "How many House seats will Democrats win in Louisiana?",
    "How many House seats will the Democrats win in Ohio?",
    False,
)
show("Will North Korea test a nuclear weapon before July 2027?",
     "Will South Korea test a nuclear weapon before July 2027?", False)
show("Texas Governor election winner 2026?", "Florida Governor election winner 2026?", False)

print()
print("--- ADMITTED CONTROLS (must still MATCH) ---")
show("2027 FIFA Women's World Cup Champion", "FIFA Women's World Cup 2027 Winner", True)
show(
    "Will Donald Trump win the 2028 US presidential election?",
    "Donald Trump to win the 2028 US presidency?",
    True,
)
# #6537's pair reaches this predicate only AFTER `_comparison_title` sets the
# year qualifier aside; the raw titles are refused by the numeric guard on both
# master and here. The post-strip form is the control the place guard must not
# touch: one side carries `us`, the other carries no place at all.
show("Which party will win the U.S. House?", "Which party will win the House?", True)
show("Oscar Winner", "oscar winner!", True)
show(
    "How many House seats will Democrats win in Georgia?",
    "How many House seats will the Democrats win in Georgia?",
    True,
)

print()
print("--- ADMITTED, place-synonym: the alias table earns its place ---")
show("Next French Presidential Election Winner", "Next France Presidential Election Winner", True)
show("Who wins the 2028 USA presidential election?", "Who wins the 2028 US presidential election?", True)

print()
print("--- RESIDUAL, one-sided place: stays open on #6985, must be UNCHANGED (True) ---")
show("#2 Artist on Spotify U.S. in 2026?", "#2 Spotify Artist 2026", True)

print()
print(f"{'ALL EXPECTATIONS MET' if not FAILS else f'{len(FAILS)} MISMATCH(ES)'}")
sys.exit(1 if FAILS else 0)
