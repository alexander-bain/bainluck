#!/usr/bin/env python3
"""CAL-P199 (#2052): how many calibration beats are killed by a DEPLOY, not a fence?

Read-only. Cross-references two artifacts that already exist:

  * ``artifacts/cal-p118/beat-ring-full.json`` — 168 consecutive production beats,
    each with ``generated_at`` (the beat's START) and ``elapsed_ms``.
  * a Heroku release dump (``heroku releases -a bainluck -n 400 --json``) — every
    dyno-restarting event in the same window.

A beat's END is ``generated_at + elapsed_ms``. If a release lands inside a small
window around that END, the beat did not stop at a fence: the dyno went away
underneath it.

THE CONTROL ARM (P198's lesson — a sweep that returns zero is worthless until it
first reproduces a known hit). Two controls, both required to pass:

  * POSITIVE: the 2026-09-01T18:24:55Z live beat is a hand-verified deploy kill
    (release v3980 landed 17.8 s before the ledger write). It is not in the ring,
    so it is injected explicitly and must classify as DEPLOY_KILL.
  * NEGATIVE: beats that terminated ``complete`` are the population that stopped
    on purpose. If they match releases at the same rate as the cancelled ones,
    the detector is matching noise, not deploys, and the run is VOID.

Runs from any cwd.
"""

from __future__ import annotations

import bisect
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

RING = REPO_ROOT / "artifacts" / "cal-p118" / "beat-ring-full.json"

#: How close a release must land to a beat's END to be called its killer. Chosen
#: from the hand-verified specimen (17.8 s) with room for the teardown handler to
#: persist the ledger, and deliberately far tighter than the ~60 min beat cadence
#: so a match cannot be manufactured by density alone. Swept below.
KILL_WINDOW_S = 120

#: The hand-verified positive control (see module docstring).
CONTROL_BEAT_END = "2026-09-01T18:24:55.805978+00:00"
CONTROL_RELEASE = "2026-09-01T18:24:38Z"


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def load_releases(path: Path) -> list[datetime]:
    rows = json.loads(path.read_text())
    return sorted(_parse(r["created_at"]) for r in rows)


def nearest_release_s(end: datetime, releases: list[datetime]) -> float:
    """Signed seconds from the nearest release to ``end`` (positive = release first)."""
    i = bisect.bisect_left(releases, end)
    best = None
    for j in (i - 1, i):
        if 0 <= j < len(releases):
            delta = (end - releases[j]).total_seconds()
            if best is None or abs(delta) < abs(best):
                best = delta
    return best if best is not None else float("inf")


def load_beats(path: Path) -> list[dict]:
    beats = []
    for b in json.loads(path.read_text()):
        start = _parse(b["generated_at"])
        elapsed = int(b["elapsed_ms"])
        beats.append(
            {
                "generation": b["generation"],
                "start": start,
                "end": start + timedelta(milliseconds=elapsed),
                "elapsed_ms": elapsed,
                "terminal": b.get("terminal"),
                "published": b.get("published") == "true",
                "gauges": b.get("gauges", {}),
            }
        )
    return beats


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: cal_p199_deploy_kill_census.py <releases.json>", file=sys.stderr)
        return 2
    releases = load_releases(Path(sys.argv[1]))
    beats = load_beats(RING)

    span_lo, span_hi = min(b["start"] for b in beats), max(b["end"] for b in beats)
    covered = [r for r in releases if span_lo <= r <= span_hi]
    print(f"ring: {len(beats)} beats, {span_lo.isoformat()} .. {span_hi.isoformat()}")
    print(f"releases in span: {len(covered)} of {len(releases)} loaded")

    # ---- POSITIVE CONTROL -------------------------------------------------
    ctl = nearest_release_s(_parse(CONTROL_BEAT_END), releases)
    ctl_ok = abs(ctl) <= KILL_WINDOW_S
    print(f"\nCONTROL+ live 18:24:55Z beat: nearest release {ctl:+.1f}s "
          f"(expected {CONTROL_RELEASE}) -> {'DEPLOY_KILL' if ctl_ok else 'MISS'}")
    if not ctl_ok:
        print("CONTROL+ FAILED — detector cannot see a hand-verified kill. VOID.")
        return 1

    # ---- the census -------------------------------------------------------
    for b in beats:
        b["delta_s"] = nearest_release_s(b["end"], releases)
        b["deploy_kill"] = abs(b["delta_s"]) <= KILL_WINDOW_S

    done = [b for b in beats if b["terminal"] == "complete"]
    notdone = [b for b in beats if b["terminal"] != "complete"]

    def rate(pop):
        if not pop:
            return 0, 0, 0.0
        hits = sum(1 for b in pop if b["deploy_kill"])
        return hits, len(pop), 100.0 * hits / len(pop)

    h_all, n_all, p_all = rate(beats)
    h_nd, n_nd, p_nd = rate(notdone)
    h_d, n_d, p_d = rate(done)

    print(f"\nALL beats          : {h_all}/{n_all} = {p_all:.1f}% end within {KILL_WINDOW_S}s of a release")
    print(f"terminal != complete: {h_nd}/{n_nd} = {p_nd:.1f}%   <-- the claim")
    print(f"terminal == complete: {h_d}/{n_d} = {p_d:.1f}%   <-- CONTROL- (must be much lower)")

    # ---- NEGATIVE CONTROL -------------------------------------------------
    if n_d == 0:
        print("\nCONTROL- FAILED — no completed beats to compare against. VOID.")
        return 1
    if p_nd <= p_d:
        print("\nCONTROL- FAILED — cancelled beats match releases no more often than "
              "completed ones. The detector is matching density, not deploys. VOID.")
        return 1
    print(f"\nCONTROL- PASS — separation {p_nd - p_d:+.1f} pp")

    # ---- window sweep: is the result an artefact of KILL_WINDOW_S? --------
    print("\nwindow sweep (not-complete% vs complete%):")
    for w in (30, 60, 120, 300, 600, 1800):
        a = 100.0 * sum(1 for b in notdone if abs(b["delta_s"]) <= w) / max(1, n_nd)
        c = 100.0 * sum(1 for b in done if abs(b["delta_s"]) <= w) / max(1, n_d)
        print(f"  +/-{w:>4}s : {a:5.1f}%  vs  {c:5.1f}%   sep {a - c:+6.1f} pp")

    # ---- what the kills cost ---------------------------------------------
    killed = [b for b in notdone if b["deploy_kill"]]
    if killed:
        lost = [b["gauges"].get("staged:units_completed_this_beat", 0) for b in killed]
        print(f"\nof the {len(killed)} deploy-killed beats: "
              f"{sum(1 for x in lost if x == 0)} banked ZERO units")
    print("\nreleases in span per beat-hour: "
          f"{len(covered) / max(1e-9, (span_hi - span_lo).total_seconds() / 3600):.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
