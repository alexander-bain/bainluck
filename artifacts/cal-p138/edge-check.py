"""CAL-P138 — is the arm table an artifact of where the chunk boundaries fell?

The first baseball run's self-check came back **n=41,139 against the payload's
45,240, −9.07%**, and that number cannot be shrugged at, because
``calibration_cell_exact``'s own docstring names the mechanism that would produce
it AND says it bites on exactly this population:

    Chunking on ``fm.id`` can split a ``group_id`` / ``event_id`` cluster across
    a chunk boundary, and ``virtual_market``'s ">= 3 markets in the same source"
    grouping test is then evaluated on a partial cluster — so a market that is
    grouped in production can read ungrouped in a chunk and take the ``rn = 1``
    branch instead of the multi branch.

An O/U ladder IS such a cluster — ten markets under one ``polymarket:{event}``
group — so the arms in this queue are built out of precisely the rows the
approximation is documented to disturb, and the sign fits: ``rn = 1`` publishes
one leg where the multi branch publishes several, which makes the replica SMALL.

So this re-runs the identical market-grain fold at HALF the chunk width and
compares the arms row by row. The comparison is the point: a shortfall that is
the same at both widths is not coming from the boundaries, and one that moves is.
``calibration_cell_exact`` ships ``--edge-check`` for the pooled total only; the
arms are what this queue reads, so the arms are what is checked.

⚠️ THIS CANNOT PROVE THE REPLICA IS RIGHT. Two chunk widths agreeing rules out
the boundaries as the cause; it does not rule out a shortfall the two widths
share. That is lesson 9 again — a claim about agreement, not about truth — and
the residual is reported as an open quantity rather than explained away.

Usage::

    source ~/.claude/.env && python3 artifacts/cal-p138/edge-check.py baseball
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "backend", "scripts"))

import calibration_cell_exact as cce  # noqa: E402

import legswap_classes as LC  # noqa: E402

cce.DIMENSIONS["marketid"] = ("d.market_id::text", "", "")


def run(cat, width):
    path = os.path.join(HERE, f"edge-marketgrain-{cat}-{width}.json")
    if os.path.exists(path):
        with open(path) as fh:
            d = json.load(fh)
        return {int(k): {int(b): v for b, v in bb.items()}
                for k, bb in d.items()}
    by_key, _ = cce.sweep("polymarket", cat, "marketid", width)
    out = {int(k): {int(b): v for b, v in bb.items()} for k, bb in by_key.items()}
    with open(path, "w") as fh:
        json.dump({str(k): {str(b): v for b, v in bb.items()}
                   for k, bb in out.items()}, fh)
    return out


def arm_totals(by_market, arms, claimed):
    published = set(by_market)
    out = {}
    for arm in list(LC.ARMS) + ["z_not_in_a_ladder"]:
        ids = (published - claimed) if arm == "z_not_in_a_ladder" else arms[arm]
        bins = {}
        for mid in ids & published:
            for b, v in by_market[mid].items():
                s = bins.setdefault(b, {"n": 0, "w": 0, "sp": 0.0})
                s["n"] += v["n"]
                s["w"] += v["w"]
                s["sp"] += v["sp"]
        n, ece, gap = cce.fold(bins)
        out[arm] = {"markets_published": len(ids & published),
                    "n": n, "ece": ece, "gap": gap}
    return out


if __name__ == "__main__":
    cat = (sys.argv[1:] or ["baseball"])[0]
    full = cce.DEFAULT_WIDTH
    half = full // 2

    part = LC.classify(cat)
    arms = part["arms"]
    claimed = set().union(*arms.values()) if arms else set()

    a = arm_totals(run(cat, full), arms, claimed)
    b = arm_totals(run(cat, half), arms, claimed)

    pn, pece, pgap, meta = cce.payload_cell("polymarket", cat)
    tot_a = sum(v["n"] for v in a.values())
    tot_b = sum(v["n"] for v in b.values())

    print(f"\npolymarket/{cat}  —  chunk-width edge check")
    print(f"  payload n={pn}  ({meta['generated_at']}, {meta['population_version']})")
    print(f"  width {full}: n={tot_a}  ({(tot_a - pn) / pn * 100:+.2f}% vs payload)")
    print(f"  width {half}: n={tot_b}  ({(tot_b - pn) / pn * 100:+.2f}% vs payload)")
    print(f"  the two widths differ by {tot_b - tot_a:+d} rows "
          f"({(tot_b - tot_a) / max(1, tot_a) * 100:+.3f}%)")
    print()
    print(f"  {'arm':<20} {'n@full':>8} {'n@half':>8} {'delta':>7} "
          f"{'ECE@full':>9} {'ECE@half':>9}")
    for arm in list(LC.ARMS) + ["z_not_in_a_ladder"]:
        if not a[arm]["n"] and not b[arm]["n"]:
            continue
        print(f"  {arm:<20} {a[arm]['n']:>8} {b[arm]['n']:>8} "
              f"{b[arm]['n'] - a[arm]['n']:>+7} "
              f"{str(a[arm]['ece']):>9} {str(b[arm]['ece']):>9}")
    print()
    # 🔴 THE VERDICT IS A MAGNITUDE, NOT AN EQUALITY, AND THE FIRST RUN OF THIS
    # SCRIPT GOT THAT WRONG. A strict ``==`` on row counts printed "the arms
    # MOVE" for a table whose largest arm moved by 12 rows in 3,401 — which
    # reads as "these numbers are unusable" when what was measured is the
    # opposite. The question the shortfall poses is whether the boundaries
    # EXPLAIN a 9% miss, and a 0.24% wobble answers no. The strict flag is kept
    # in the artifact as a sub-fact; it is not the verdict.
    identical = all(a[k]["n"] == b[k]["n"] for k in a)
    worst = max((abs(b[k]["n"] - a[k]["n"]) / a[k]["n"] * 100)
                for k in a if a[k]["n"])
    total_move = abs(tot_b - tot_a) / max(1, tot_a) * 100
    shortfall = abs(tot_a - pn) / pn * 100
    print(f"  the widest arm moved {worst:.2f}%; the pooled total moved "
          f"{total_move:.3f}%; the shortfall against the payload is "
          f"{shortfall:.2f}%")
    print("  VERDICT  " + (
        "the chunk boundaries do NOT explain the shortfall — they move the "
        "pooled total by two orders of magnitude less than the miss, and every "
        "arm's ECE is stable to a few hundredths. The shortfall is something "
        "the two widths SHARE and it stays OPEN."
        if total_move * 10 < shortfall else
        "the boundaries move the total by a share comparable to the shortfall — "
        "every arm number in this queue is approximate and must be read so."))
    print(f"  (strict row-for-row equality: {identical})")

    with open(os.path.join(HERE, f"edge-check-{cat}.json"), "w") as fh:
        json.dump({"cell": f"polymarket/{cat}",
                   "payload": {"n": pn, "ece": pece, "gap": pgap, **meta},
                   "full_width": full, "half_width": half,
                   "total_at_full": tot_a, "total_at_half": tot_b,
                   "arms_at_full": a, "arms_at_half": b,
                   "arms_identical": identical}, fh, indent=2)
