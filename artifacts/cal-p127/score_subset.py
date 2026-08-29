"""Score one NAMED subset of a fold's classes, re-pooled bucket by bucket.

``calibration_rule_search`` ranks the whole 2^k lattice and prints a top-N. A
rule design also needs the number for ONE subset the searcher did not rank —
the arms a human can justify, which are rarely the arms that minimise ECE.

The pooling is imported from the searcher, never restated: two files that pool
the same buckets differently produce two numbers for one rule.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "backend" / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rs = _load("calibration_rule_search")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--drop", nargs="*", default=[],
                    help="class keys to EXCLUDE; everything else is kept")
    args = ap.parse_args()

    d = json.loads(Path(args.inp).read_text())
    by_key = {k: {int(b): v for b, v in bb.items()}
              for k, bb in d["by_key"].items()}
    halves = {h: {k: {int(b): v for b, v in bb.items()}
                  for k, bb in hh.items()}
              for h, hh in (d.get("halves") or {}).items()}

    unknown = [k for k in args.drop if k not in by_key]
    if unknown:
        raise SystemExit(f"no such class: {unknown}\n  have: {sorted(by_key)}")

    allk = sorted(by_key)
    keep = [k for k in allk if k not in args.drop]

    n0, e0, g0 = rs.score(by_key, allk)
    n1, e1, g1 = rs.score(by_key, keep)
    print(f"  as published   n={n0:>7}  ECE={e0:>6}  gap={g0:>+7}")
    print(f"  after rule     n={n1:>7}  ECE={e1:>6}  gap={g1:>+7}")
    print(f"  dropped        {n0 - n1} rows ({(n0 - n1) / n0 * 100:.1f}%)"
          f"   delta ECE {e1 - e0:+.2f}")
    for h in ("OLD", "NEW"):
        if h in halves:
            hk = [k for k in keep if k in halves[h]]
            hall = sorted(halves[h])
            hn0, he0, _ = rs.score(halves[h], hall)
            hn1, he1, hg1 = rs.score(halves[h], hk) if hk else (0, None, None)
            print(f"  {h:<14} n={hn1:>7}  ECE={he1:>6}  gap={hg1:>+7}"
                  f"   (before: n={hn0} ECE={he0})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
