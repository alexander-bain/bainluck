"""Mutation coverage for the absent-shape net on the feed warm rail (LAT-P112).

WHY THIS HARNESS AND NOT JUST THE TESTS. Every failure mode of a warm rail is
SILENT in both directions, and this net adds a third silence on top of the two
`typeahead_warmer_mutations.py` already names:

* It can fail to notice a hole, in which case the product is exactly what it was
  before the fix — a 3,722.7 ms Discover open, some of the time — and the beat
  reports `no_live_shapes` on every pass, which is also what a healthy night
  looks like.
* It can notice a hole that is not there, in which case it quietly puts five
  cold feed builds on the `realtime` queue every 40 seconds forever, and the
  only symptom is a bill and a slower live-price poll.
* It can notice correctly and then push the live republish past `#2236`'s
  ceiling, reintroducing the defect it is sitting next to.

None of those three throws, 500s, or changes a rendered byte. So each guard gets
a mutant that breaks it the way it would break in production, and the suite has
to catch every one.

Every mutation is proven APPLIED before it is scored (an anchor that matches 0
or 2+ times is NOT-APPLIED, never a silent SURVIVED), the control must be green
on unmutated source first (gotcha #122), and every target is restored
SHA-identical under the shared signal guard.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

from _mutation_guard import guarded_targets  # noqa: E402

BACKEND = Path(__file__).resolve().parents[2]

PCP = BACKEND / "app" / "tasks" / "precompute_category_pages.py"

TARGETS = (PCP,)
BACKUP_DIR = Path("/tmp/lat_p112_backups")

ORACLES = [
    "tests/test_feed_prewarm_absent_shape_net.py",
    "tests/test_feed_live_prewarm.py",
    "tests/test_feed_prewarm.py",
]

MUTATIONS: list[tuple[str, Path, str, str, str]] = [
    (
        "M1", PCP,
        "the net is never consulted — the whole fix becomes inert while every "
        "pass keeps reporting the healthy `no_live_shapes`. The load-bearing "
        "mutant: this is the state of production today",
        "    absent_labels = _absent_prewarm_labels(rc, exclude=live_labels)\n",
        "    absent_labels = set()\n",
    ),
    (
        "M2", PCP,
        "the net's targets are selected but never appended to the build list, "
        "so the hole is DETECTED, REPORTED in `absent_labels`, and not fixed — "
        "the shape of a fix that reads correct in the status payload and does "
        "nothing to the user's wait",
        "    targets += [\n"
        '        (s["label"], s) for s in FEED_PREWARM_SHAPES if s["label"] in absent_labels\n'
        "    ]\n",
        "",
    ),
    (
        "M3", PCP,
        "the probe reads the HEAD instead of the stale mirror — the head dies "
        "at 60s under a 120s host beat, so every shape reads as absent on "
        "almost every pass and the net rebuilds the entire feed surface every "
        "40 seconds",
        '            if not rc.exists(f"{cache_key}:stale"):\n',
        '            if not rc.exists(cache_key):\n',
    ),
    (
        "M4", PCP,
        "an unknown label fails OPEN instead of closed — after every deploy the "
        "hash is empty, so the first pass puts five cold builds on the realtime "
        "queue at the moment it can least absorb them",
        "        if not cache_key:\n"
        "            # Unknown OR blank.",
        "        if not cache_key:\n"
        "            absent.add(label)\n"
        "            # Unknown OR blank.",
    ),
    (
        "M5", PCP,
        "absent targets are ordered BEFORE live ones, so a safety net can "
        "consume the budget slice a live republish needs and #2236's ceiling "
        "is breached by its own neighbour",
        '    targets = [(s["label"], s) for s in FEED_PREWARM_SHAPES if s["label"] in live_labels]\n'
        "    targets += [\n"
        '        (s["label"], s) for s in FEED_PREWARM_SHAPES if s["label"] in absent_labels\n'
        "    ]\n",
        '    targets = [(s["label"], s) for s in FEED_PREWARM_SHAPES if s["label"] in absent_labels]\n'
        "    targets += [\n"
        '        (s["label"], s) for s in FEED_PREWARM_SHAPES if s["label"] in live_labels\n'
        "    ]\n",
    ),
    (
        "M6", PCP,
        "the live set stops excluding itself, so a shape that is BOTH live and "
        "missing is built twice in one pass — double cost at the exact moment "
        "the pass is most loaded, and the older build publishes over the newer",
        "    absent_labels = _absent_prewarm_labels(rc, exclude=live_labels)\n",
        "    absent_labels = _absent_prewarm_labels(rc)\n",
    ),
    (
        "M7", PCP,
        "the resolved cache key is never remembered, so the net has nothing to "
        "probe, fails closed on every shape forever, and is inert in the way "
        "that reports success",
        "    _record_shape_cache_key(rc, label, cache_key)\n",
        "",
    ),
    (
        "M8", PCP,
        "the net re-derives the key by convention instead of reading the one "
        "the route resolved — the LAT-P001 two-writers trap, and it fails by "
        "probing a key nobody publishes, i.e. by rebuilding everything forever",
        "        cache_key = known.get(label)\n",
        '        cache_key = known.get(label) or f"feed_response:{label}"\n',
    ),
    (
        "M9", PCP,
        "a Redis error on the hash read fails OPEN — one transient blip turns "
        "into five cold feed builds every 40 seconds until it clears",
        "    except Exception:\n"
        '        logger.debug("shape-key marker read failed", exc_info=True)\n'
        "        return set()\n",
        "    except Exception:\n"
        '        logger.debug("shape-key marker read failed", exc_info=True)\n'
        "        return {s[\"label\"] for s in FEED_PREWARM_SHAPES}\n",
    ),
    (
        "M10", PCP,
        "an EMPTY remembered key is probed as if it were a key — `EXISTS "
        '":stale"` is 0 for every shape, so one bad hash write marks the whole '
        "pool absent",
        "        if not cache_key:\n",
        "        if cache_key is None:\n",
    ),
    (
        "M11", PCP,
        "the hole disappears from the status payload, so a starved host rail "
        "reads like a quiet night and the incident this net covers for can "
        "never be seen from outside (gotcha #53)",
        '        "absent_labels": sorted(absent_labels),\n',
        "",
    ),
    (
        "M12", PCP,
        "the remembered key inherits the liveness hash's 300s dead-man TTL, so "
        "the mapping lapses during exactly the outage it exists to cover and "
        "the net is armed only when it is not needed",
        "FEED_PREWARM_SHAPE_KEYS_TTL_S = 86_400\n",
        "FEED_PREWARM_SHAPE_KEYS_TTL_S = 300\n",
    ),
    (
        "M13", PCP,
        "bytes from a non-decoding Redis client are no longer decoded, so every "
        "label silently matches no shape and the net selects nothing while "
        "reporting the healthy state",
        "        label = (\n"
        "            label_raw.decode() if isinstance(label_raw, (bytes, bytearray)) else str(label_raw)\n"
        "        )\n",
        "        label = str(label_raw)\n",
    ),
]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_oracles() -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *ORACLES, "-q", "--no-header"],
        cwd=BACKEND, capture_output=True, text=True,
    )
    if proc.returncode not in (0, 1):
        raise SystemExit(
            f"oracle exited {proc.returncode} — a usage error, not a result "
            f"(gotcha #124). Refusing to score.\n{proc.stdout[-2000:]}"
        )
    tail = [ln for ln in proc.stdout.strip().splitlines() if ln.strip()]
    return proc.returncode == 0, (tail[-1] if tail else "<no output>")


def _main() -> int:
    BACKUP_DIR.mkdir(exist_ok=True)
    original = {t: _sha(t) for t in TARGETS}
    backups = {}
    for t in TARGETS:
        b = BACKUP_DIR / t.name
        shutil.copy2(t, b)
        backups[t] = b

    print("=" * 78)
    print("CONTROL — oracles against UNMUTATED source")
    ok, summary = _run_oracles()
    print(f"  {summary}")
    if not ok:
        print("\nCONTROL IS RED. Every mutant below would score a KILL it did not")
        print("earn (gotcha #122). Aborting without running any mutation.")
        return 2
    print("  control: oracles PASS on unmutated source")
    print("=" * 78)

    killed, survived, not_applied = [], [], []
    for mid, target, desc, old, new in MUTATIONS:
        source = backups[target].read_text()
        count = source.count(old)
        if count != 1:
            not_applied.append((mid, f"anchor matched {count}x, expected 1"))
            print(f"{mid:>4}  NOT-APPLIED  ({count}x anchor)  {desc}")
            continue

        target.write_text(source.replace(old, new, 1))
        if _sha(target) == original[target]:
            not_applied.append((mid, "file unchanged after write"))
            print(f"{mid:>4}  NOT-APPLIED  (no byte change)  {desc}")
            shutil.copy2(backups[target], target)
            continue

        ok, summary = _run_oracles()
        shutil.copy2(backups[target], target)
        assert _sha(target) == original[target], "restore did not reproduce the original"

        if ok:
            survived.append((mid, desc))
            print(f"{mid:>4}  SURVIVED     {desc}\n        {summary}")
        else:
            killed.append((mid, desc))
            print(f"{mid:>4}  KILLED       {desc}")

    print("=" * 78)
    print(f"killed {len(killed)}/{len(MUTATIONS)} · survived {len(survived)} · "
          f"not-applied {len(not_applied)}")
    for mid, desc in survived:
        print(f"  SURVIVOR {mid}: {desc}")
    for mid, why in not_applied:
        print(f"  NOT-APPLIED {mid}: {why}")
    for t in TARGETS:
        assert _sha(t) == original[t], f"{t.name} not restored"
    print("target restored, SHA matches original")
    return 0 if (not survived and not not_applied) else 1


def main() -> int:
    """Run the harness with an UNCONDITIONAL restore around it — the #2107 net.

    `_main()` restores after each mutant; this is the net under it, for the
    exit-143-between-write-and-restore case that `try/finally` alone does not
    survive. See `_mutation_guard.py`.
    """
    with guarded_targets(TARGETS, BACKUP_DIR, "lat_p112_absent_shape_net"):
        return _main()


if __name__ == "__main__":
    raise SystemExit(main())
