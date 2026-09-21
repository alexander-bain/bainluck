"""Re-bisect DECODE_BUDGET_OUTCOMES / DECODE_BUDGET_NODES after #7808's column.

`mutually_exclusive` joins `MARKET_COLUMNS`, so every market row on the wire is
one cell heavier. Both constants in
`test_feed_market_load_fits_the_shared_wire_lat_p221.py` are measurements of
where the 6 MiB envelope stops fitting, so both move.

The method is the one that file's own comment prescribes, and it is prescribed
because the FIRST bisection there was wrong: find the ceiling by DOUBLING until
the envelope is PROVEN over the cap, never assume one, because a bisection whose
bracket does not contain the answer converges to its own ceiling and reports it
with confidence. Then one-outcome granularity.
"""

import importlib.util
import os
import sys

BACKEND = os.path.join(os.path.dirname(__file__), "..", "..", "backend")
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

spec = importlib.util.spec_from_file_location(
    "wire", "tests/test_feed_market_load_fits_the_shared_wire_lat_p221.py"
)
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)

CAP = w.pic.MAX_ENVELOPE_BYTES


def fits(n):
    return w._envelope_bytes(w._production_scale_payload(n)) <= CAP


print(f"cap = {CAP:,} B   PROD_MARKETS = {w.PROD_MARKETS}")
print(f"recorded in file: DECODE_BUDGET_OUTCOMES={w.DECODE_BUDGET_OUTCOMES:,} "
      f"DECODE_BUDGET_NODES={w.DECODE_BUDGET_NODES:,}")

# 1. a ceiling PROVEN over the cap, by doubling.
hi = w.DECODE_BUDGET_OUTCOMES
while fits(hi):
    hi *= 2
    print(f"  doubling: {hi:,} does not fit? {not fits(hi)}")
lo = hi // 2
print(f"bracket proven: lo={lo:,} (fits) hi={hi:,} (over)")

# 2. one-outcome granularity.
while hi - lo > 1:
    mid = (lo + hi) // 2
    if fits(mid):
        lo = mid
    else:
        hi = mid

at = w._production_scale_payload(lo)
past_one = w._production_scale_payload(lo + 1)
past_step = w._production_scale_payload(lo + w.PROD_MARKETS)

print()
print(f"DECODE_BUDGET_OUTCOMES = {lo:,}")
print(f"  {lo:,} encodes to {w._envelope_bytes(at):,} B "
      f"({CAP - w._envelope_bytes(at):,} B of margin)")
print(f"  {lo + 1:,} encodes to {w._envelope_bytes(past_one):,} B — does not fit")
print(f"  +PROD_MARKETS ({lo + w.PROD_MARKETS:,}) encodes to "
      f"{w._envelope_bytes(past_step):,} B — does not fit")
print(f"DECODE_BUDGET_NODES = {w._count_validator_nodes(at):,}")
print(f"  against _MAX_NODES = {w.pic._MAX_NODES:,} "
      f"({100 * w._count_validator_nodes(at) / w.pic._MAX_NODES:.1f}% of it)")

print()
print(f"MEASURED_NODES (default shape) = "
      f"{w._count_validator_nodes(w._production_scale_payload()):,} "
      f"(file records {w.MEASURED_NODES:,})")
