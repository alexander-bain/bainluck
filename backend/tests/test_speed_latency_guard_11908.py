"""#11908: the release watch's 5 s guard counts only slow waits that start after the release.

On Nov 3 a tennis match (event 15340299) had Kalshi waits of 15-40 s every minute from 6:52 AM PT, cause
`na_proof`. A release at 7:13 was rolled back for them. The guard now excludes a slow wait whose event was
already slow in the 30 minutes before the release, or which began before it.
"""

import subprocess
import sys
from pathlib import Path

GUARD = Path(__file__).resolve().parents[2] / "tools" / "speed" / "latency_guard2.py"
FAST_P = "15341316:120:receipt(c100,p20)[f100,a1]"


def minute(hhmm, kalshi, polymarket=FAST_P):
    k = int(kalshi.split(",")[0].split(":")[1])
    return f"{hhmm} {'FAIL' if k >= 500 else 'PASS'} K={k}ms P=120ms streak=0 best=0 | K {kalshi} | P {polymarket}\n"


def verdict(tmp_path, rows, start="15:15", release="15:13"):
    log = tmp_path / "streak.log"
    log.write_text("".join(rows))
    out = subprocess.run([sys.executable, str(GUARD), str(log), start, "5000", "2", release],
                         capture_output=True, text=True, check=True).stdout.strip().splitlines()
    return out[-1]


def slow(event, ms):
    return f"{event}:{ms}:na_proof[f2,a12],{event}:{ms - 1000}:na_proof[f1,a9],15341379:170:na_proof[f1,a2]"


def test_a_game_already_slow_before_the_release_does_not_roll_it_back(tmp_path):
    before = [minute(f"15:{m:02d}", slow(15340299, 30000)) for m in range(0, 13)]
    after = [minute(f"15:{m:02d}", slow(15340299, 30000)) for m in range(13, 18)]
    assert verdict(tmp_path, before + after).startswith("VERDICT PASS")


def test_a_game_slow_only_after_the_release_still_rolls_it_back(tmp_path):
    before = [minute(f"15:{m:02d}", slow(15340299, 30000)) for m in range(0, 13)]
    # The same pre-existing match, plus a different game that turns slow after the release.
    after = [minute(f"15:{m:02d}", f"15339952:9000:receipt(c900,p100)[f900,a1],{slow(15340299, 8000)}")
             for m in range(13, 18)]
    assert verdict(tmp_path, before + after).startswith("VERDICT ROLLBACK")


def test_a_wait_that_began_before_the_release_is_not_counted(tmp_path):
    # Listed at 15:14 and 15:15 but 150 s and 200 s long: each began before the 15:13 release.
    rows = [minute("15:12", FAST_P), minute("15:14", "15339952:150000:late:old_graph,15341316:120:receipt"),
            minute("15:15", "15339952:200000:late:old_graph,15341316:120:receipt")]
    assert verdict(tmp_path, rows, start="15:14").startswith("VERDICT PASS")


def test_the_nov_3_rollback_minutes_now_pass(tmp_path):
    """The real 15:00-15:16Z meter lines (abridged to their Kalshi lists) that rolled back v6121."""
    real = {
        "15:00": "15340299:18885:na_proof[f2,a6],15340299:16393:na_proof[f1,a9],15340299:2957:na_proof>stamp_unobserved[f1,a4]",
        "15:04": "15340299:39706:na_proof[f33,a10],15340299:19588:na_proof[f2,a4],15341379:170:na_proof[f1,a2]",
        "15:10": "15340299:42550:na_proof[f0,a6],15340299:19716:na_proof>stamp_unobserved[f6,a11],15339634:159:receipt(c101,p57)[f101,a1]",
        "15:12": "15340299:32050:na_proof[f1,a21],15340299:17708:na_proof[f1,a9],15340299:2858:na_proof[f6,a5]",
        "15:15": "15340299:7630:na_proof[f4,a5],15340299:6711:na_proof>stamp_unobserved[f1,a5],15340299:4866:na_proof[f2,a4]",
        "15:16": "15340299:30350:na_proof[f2,a12],15340299:30033:na_proof[f2,a10],15340299:11282:na_proof[f7,a9]",
    }
    rows = [minute(m, k) for m, k in real.items()]
    assert verdict(tmp_path, rows).startswith("VERDICT PASS")
