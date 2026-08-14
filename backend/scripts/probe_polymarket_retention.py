#!/usr/bin/env python3
"""Re-derive the Polymarket addressability boundary from the venue. No DB, no key.

Gotcha #35's lesson, applied before it costs us three rails instead of after:
*a predicate cannot consume a range written in prose.* Kalshi's retention was
documented as "~2-3 months" for months; three separate recovery rails were
written by people who had read that sentence, and every one of them still
ground purged markets. The fix there was a probe plus an importable constant.
This is that, for Polymarket, written at the moment of first measurement rather
than after the third failure.

Run it to answer one question the code cannot answer for itself:

    HAS THE BOUNDARY MOVED?

If it has, the cohort is EXPIRING and the backfill is urgent — promote to P1 and
re-order the sweep. If it has not moved across several months, the boundary is
structural (pre-CLOB markets Polymarket never indexed) and the backfill can be
scheduled at leisure. **One measurement cannot tell these apart**, which is
precisely why this script exists rather than a paragraph asserting one of them.

    python3 backend/scripts/probe_polymarket_retention.py

Exit 0 = constants still hold. Exit 1 = a bound moved; go read the output.

Two things this script does that the obvious version would not:

1. **It probes a CONTROL first and aborts if the control fails.** The first
   probe attempted during CAL-P060 (``gamma/markets?condition_ids=``) returned
   ``[]`` for five specimens spanning 2021-2025 — and also for a market that had
   resolved five days earlier and carries volume in our own database. Read
   without a control that is a textbook retention cliff, and it is nothing but a
   non-functional query parameter. Ruling 050: a control that cannot fail is not
   a control, and a probe with no control is worse.

2. **It never infers a fact from an empty 200.** ``data-api/trades`` answers
   ``200 []`` for purged and untraded markets identically (gotcha #53), so
   existence is read from a second endpoint and consulted first.
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import date

sys.path.insert(0, __file__.rsplit("/scripts/", 1)[0])

from app.utils.polymarket_evidence import (  # noqa: E402
    GAMMA_MARKETS_MAX_OFFSET,
    PM_ADDRESSABLE_FROM,
    PM_BOUNDARY_MEASURED_ON,
    PM_UNADDRESSABLE_THROUGH,
    PMEvidence,
    classify_pm_evidence,
)

CLOB = "https://clob.polymarket.com"
DATA = "https://data-api.polymarket.com"
GAMMA = "https://gamma-api.polymarket.com"

# Specimens pinned at first measurement (2026-08-14). Condition ids are
# immutable, so re-running this compares like with like — the point is to detect
# a specimen CHANGING verdict, which a freshly-sampled cohort could never show.
SPECIMENS: list[tuple[str, str]] = [
    ("2021-01-02", "0x9b946f54f3428aafc308c33aa04a943fe13a011bdac9a9b66e1ba16c416ca256"),
    ("2021-01-21", "0x2552743e295cc1c0fcb8d1b1a1207cacd0702d22f6df27ad5b2a87288b0a1654"),
    ("2022-01-01", "0xe681cf6b2afad7020355ba997fb8b58c01f0d25910c8322aab382142728c7136"),
    ("2022-06-01", "0xa4e7bb2cd13108f6335b44fd44e514f8f25edb4b4538514857712c444c2c90eb"),
    ("2023-01-01", "0xfac9f2b2658782a0b6bdadf34243faf4d7f53cf9743b2419f03b440053511f87"),
    ("2023-11-03", "0x46d8e52d7e7434756af45e5c6d5030899fd5f61a652f0d420ffb4a11981d556c"),
    ("2023-11-05", "0x872fce12a82796ab43ca3cd7c2b9d34d8258c7a2ed75f091d4f3120d26b397da"),
    ("2024-02-11", "0xd867730ef739616aee1fab6fb67d896a66aed33f9b03e231907da1be3bfdae13"),
    ("2025-01-03", "0x9c54876dd846054006634f4fc58366f3d14f17ff375f142bd73d077b7a28f9f8"),
]

# Resolved 2026-08-09, carries volume=240 in production. If THIS reads as
# unaddressable the probe is broken, not the venue.
CONTROL = ("2026-08-09", "0x4225f2b7adb679445f814271142c5adb175e2a1c1a7a460cc6b63f3c0040ab8c")


def _get(url: str, timeout: int = 25) -> tuple[int, str]:
    """curl, not urllib: Polymarket 403s urllib's default User-Agent."""
    p = subprocess.run(
        ["curl", "-s", "-m", str(timeout), "-w", "\n%{http_code}", url],
        capture_output=True,
        text=True,
    )
    parts = p.stdout.rsplit("\n", 1)
    if len(parts) != 2:
        return 0, ""
    try:
        return int(parts[1].strip()), parts[0]
    except ValueError:
        return 0, parts[0]


def probe(cid: str, pause: float = 0.7):
    status, _ = _get(f"{CLOB}/markets/{cid}")
    time.sleep(pause)
    tcode, tbody = _get(f"{DATA}/trades?market={cid}&limit=500")
    time.sleep(pause)
    trades = None
    if tcode == 200:
        try:
            parsed = json.loads(tbody)
            trades = parsed if isinstance(parsed, list) else None
        except (json.JSONDecodeError, ValueError):
            trades = None
    return status, trades, classify_pm_evidence(clob_status=status, trades=trades)


def probe_offset_cap() -> int:
    """Re-derive the /markets offset ceiling by bisection."""
    lo, hi = 0, 20000
    while lo < hi - 50:
        mid = (lo + hi) // 2
        code, _ = _get(f"{GAMMA}/markets?closed=true&limit=100&offset={mid}")
        time.sleep(0.7)
        if code == 200:
            lo = mid
        else:
            hi = mid
    return lo


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--skip-offset", action="store_true", help="skip the offset bisection")
    args = ap.parse_args()

    print(f"Polymarket addressability probe — constants measured {PM_BOUNDARY_MEASURED_ON}")
    print(f"today: {date.today()}\n")

    # --- CONTROL FIRST. Everything below is meaningless if this fails. -----
    cstat, ctrades, cverdict = probe(CONTROL[1])
    print(f"CONTROL {CONTROL[0]}  clob={cstat}  verdict={cverdict.value}")
    if cverdict in (PMEvidence.UNADDRESSABLE, PMEvidence.INDETERMINATE):
        print(
            "\nABORT: the control did not read as addressable. The PROBE is broken, "
            "not the venue. Do not read a cliff out of the rows below."
        )
        return 1
    print()

    newest_dead, oldest_alive = None, None
    print(f"{'resolution':<12} {'clob':<6} {'n_trades':<9} verdict")
    for rd, cid in SPECIMENS:
        status, trades, verdict = probe(cid)
        n = len(trades) if trades is not None else "-"
        print(f"{rd:<12} {status:<6} {str(n):<9} {verdict.value}")
        d = date.fromisoformat(rd)
        if verdict is PMEvidence.UNADDRESSABLE:
            newest_dead = d if newest_dead is None else max(newest_dead, d)
        elif verdict is not PMEvidence.INDETERMINATE:
            oldest_alive = d if oldest_alive is None else min(oldest_alive, d)

    print(f"\nmeasured boundary: ({newest_dead}, {oldest_alive}]")
    print(f"recorded boundary: ({PM_UNADDRESSABLE_THROUGH}, {PM_ADDRESSABLE_FROM}]")

    drift = []
    if newest_dead != PM_UNADDRESSABLE_THROUGH:
        drift.append(f"PM_UNADDRESSABLE_THROUGH {PM_UNADDRESSABLE_THROUGH} -> {newest_dead}")
    if oldest_alive != PM_ADDRESSABLE_FROM:
        drift.append(f"PM_ADDRESSABLE_FROM {PM_ADDRESSABLE_FROM} -> {oldest_alive}")

    if not args.skip_offset:
        cap = probe_offset_cap()
        print(f"\ngamma /markets offset cap: measured ~{cap}, recorded {GAMMA_MARKETS_MAX_OFFSET}")
        if abs(cap - GAMMA_MARKETS_MAX_OFFSET) > 100:
            drift.append(f"GAMMA_MARKETS_MAX_OFFSET {GAMMA_MARKETS_MAX_OFFSET} -> ~{cap}")

    if drift:
        print("\nBOUNDS MOVED — update app/utils/polymarket_evidence.py:")
        for d in drift:
            print(f"  · {d}")
        print(
            "\nA specimen that was ADDRESSABLE and is now 404 means the boundary ROLLS.\n"
            "That makes the NULL cohort an EXPIRING population: promote #1870 to P1,\n"
            "and keep the sweep oldest-first WITHIN its floor (gotcha #41 / CAL-P009)."
        )
        return 1

    print("\nAll bounds hold. No evidence the boundary has moved since first measurement.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
