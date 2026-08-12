"""LAT-P040 (#835) — mutants for "a p95 must carry its own window".

WHAT THIS PROVES
----------------
`schedule_adherence` exists because a COUNT of unknown age is not a measurement.
It fixed that for the fire counter and left the identical defect one field to
the right: `p95_duration_ms` is computed over a COUNT-bounded sample (50 runs)
and was printed beside `window_s`, which ages the STARTS counter on a 24h TTL.

Measured in production 2026-08-11 on `poll_odds`: 50 samples (exactly the cap),
p95 5,821ms, reported with `window_s: 68550` — 19.1 hours. The task's own
counters date the sample at ~50 minutes (1,149 starts / 68,673s = one run per
59.8s). A 23x mismatch, and the reason a transient 46.2s burst an hour earlier
was recorded as a standing property of the beat and staged as a queue item.

A passing suite proves the fields exist. It does not prove the suite would
NOTICE if the span silently went back to being the counter's. Each mutant below
reintroduces a specific way of getting that wrong, and the harness demands the
oracle FAIL.

BOTH DIRECTIONS, DELIBERATELY
-----------------------------
Half the mutants REMOVE the fix (the span stops being measured). The other half
OVER-APPLY it — inventing a span where none is known, or refusing to report a
real overrun because the sample is saturated. An over-correction that suppresses
a true `overruns` is a worse outcome than the mislabelling this queue fixes, so
it is mutated for explicitly rather than trusted not to happen.

WHY THE FAKE MATTERS HERE (Alex ruling, 2026-08-11)
---------------------------------------------------
`M10-drop-durations-expire` is only killable because the fake Redis in
`tests/test_schedule_adherence_wiring.py` was changed in this same queue to
actually apply a TTL on `expire()`. It used to append to a `calls` list and
return. LAT-P039's `M19` survived its first pass for exactly that reason: the
double had nothing for the mutation to change. A test double that cannot express
the bug cannot catch it, and blind reads as green.

That fake is IMPORTED here rather than re-declared. A second copy of a double is
how one copy drifts and quietly goes blind again.

MEASURED, and it sharpens the ruling. Running M10 under both doubles:

    FIXED fake (applies TTL): control=pass  mutant=FAIL  -> discriminates
    OLD no-op fake          : control=FAIL  mutant=FAIL  -> BLIND

With the no-op double the mutant still reports as KILLED — because the oracle
fails for EVERY input, mutated or not. LAT-P039's `M19` failed OPEN (survived
and looked fine); this one fails CLOSED (dies and looks like a kill). Both are
the same blindness and the second is the more dangerous reading, because a
harness tallying kills would score it as coverage.

That is why ``run()`` executes the oracles against UNMUTATED source first and
says so out loud. A kill count without a passing control is not a measurement.

Run: ``python3 scripts/evals/duration_sample_window_mutations.py``
Exits non-zero if any mutant SURVIVES **or** if any mutant fails to APPLY.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"
ADHERENCE = BACKEND / "app/utils/schedule_adherence.py"
REDIS_STATE = BACKEND / "app/tasks/redis_state.py"
WIRING_TEST = BACKEND / "tests/test_schedule_adherence_wiring.py"

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

#: A fixed epoch second. The clock is never sampled — an anchor that moves with
#: the wall clock is gotcha #44, and a span assertion is the exact shape that
#: would hide it.
BASE_TS = 1_786_500_000


# --------------------------------------------------------------------------
# Mutants on the pure grader
# --------------------------------------------------------------------------
ADHERENCE_MUTANTS = [
    {
        "id": "M01-p95-window-is-the-counter-window",
        "needle": '        "p95_window_s": durations_window_s,',
        "replacement": '        "p95_window_s": starts_window_s,',
        "why": "THE regression. The p95's span silently becomes the starts "
               "counter's window again — the original defect, restored.",
    },
    {
        "id": "M02-overrun-reason-drops-its-scope",
        "needle": '            f"{_sample_scope(out)}"\n',
        "replacement": "",
        "why": "The verdict string reverts to a bare number, readable as a "
               "property of window_s. This is the string LAT-P039 read.",
    },
    {
        "id": "M03-invent-a-span-when-unknown",
        "needle": '    if span is None:\n        return f" (over the last {n} runs; span unknown)"',
        "replacement": '    if span is None:\n        span = 0.0',
        "why": "OVER-APPLY: a legacy unstamped history reports '0min' instead "
               "of admitting the span is unknown. An invented span looks "
               "authoritative, which is worse than the silence it replaces.",
    },
    {
        "id": "M04-saturation-never-reported",
        "needle": '    if out.get("p95_sample_saturated"):',
        "replacement": "    if False:",
        "why": "Drops the load-bearing half: at the cap, older runs existed and "
               "were discarded, and the reader is no longer told.",
    },
    {
        "id": "M05-sample-n-is-hardcoded",
        "needle": '        "p95_sample_n": len(durations_ms or []),',
        "replacement": '        "p95_sample_n": 50,',
        "why": "Reports a full sample for a task that has barely run — the "
               "'confident wrong number' this module refuses elsewhere.",
    },
    {
        "id": "M06-suppress-overruns-when-saturated",
        "needle": '    if out["p95_over_interval"] is not None and out["p95_over_interval"] >= OVERRUN_RATIO:',
        "replacement": '    if (out["p95_over_interval"] is not None\n'
                       '            and out["p95_over_interval"] >= OVERRUN_RATIO\n'
                       '            and not out.get("p95_sample_saturated")):',
        "why": "OVER-APPLY: refuses to report a REAL overrun because the sample "
               "is saturated. Saturation qualifies the scope; it never makes a "
               "46s p95 untrue. Muting the detector is the worse failure.",
    },
]

# --------------------------------------------------------------------------
# Mutants on the storage
# --------------------------------------------------------------------------
REDIS_MUTANTS = [
    {
        "id": "M07-stop-stamping-the-sample",
        "needle": '    pipe.lpush(\n        hist_key, f"{round(duration_ms)}{_DURATION_STAMP_SEP}{int(ts)}"\n    )',
        "replacement": '    pipe.lpush(hist_key, str(round(duration_ms)))',
        "why": "Reverts to the unstamped write, so the span becomes "
               "permanently unknowable — the pre-LAT-P040 state.",
    },
    {
        "id": "M08-infer-the-span-instead-of-measuring-it",
        "needle": '        if len(duration_stamps) >= 2:\n'
                  '            durations_window_s = float(max(duration_stamps) - min(duration_stamps))',
        "replacement": '        if len(duration_stamps) >= 2:\n'
                       '            durations_window_s = float(len(durations) * 60)',
        "why": "Infers the span from a guessed cadence rather than reading the "
               "stamps. Plausible, confident and wrong for any task not on a "
               "60s beat — the failure mode stamps exist to remove.",
    },
    {
        "id": "M09-legacy-entries-read-as-empty",
        "needle": '    try:\n        ms = int(ms_part)\n    except (TypeError, ValueError):\n        return None',
        "replacement": '    if not ts_part:\n        return None\n'
                       '    try:\n        ms = int(ms_part)\n    except (TypeError, ValueError):\n        return None',
        "why": "Rejects the pre-LAT-P040 bare-int history, so every task reads "
               "as having NEVER RUN for one cap-length after deploy. A false "
               "absence — gotcha #53.",
    },
    {
        "id": "M10-drop-durations-expire",
        "needle": "    pipe.ltrim(hist_key, 0, DURATION_HISTORY_LEN - 1)\n    pipe.expire(hist_key, TASK_METRICS_TTL)",
        "replacement": "    pipe.ltrim(hist_key, 0, DURATION_HISTORY_LEN - 1)",
        "why": "The M19 class. Only killable because the fake now models "
               "expire(); with a no-op double this mutant survives silently.",
    },
    {
        "id": "M11-saturation-off-by-one",
        "needle": '            "recent_durations_saturated": len(durations) >= DURATION_HISTORY_LEN,',
        "replacement": '            "recent_durations_saturated": len(durations) > DURATION_HISTORY_LEN,',
        "why": "A count LTRIM'd to exactly the cap can never exceed it, so "
               "saturation is never reported — true at precisely the boundary "
               "where it matters and nowhere else.",
    },
    {
        "id": "M12-history-bound-off-by-one",
        "needle": "    pipe.ltrim(hist_key, 0, DURATION_HISTORY_LEN - 1)",
        "replacement": "    pipe.ltrim(hist_key, 0, DURATION_HISTORY_LEN)",
        "why": "Keeps cap+1 samples. Small, but it is the bound the saturation "
               "flag and the memory argument both rest on.",
    },
    {
        "id": "M13-stamp-and-duration-swapped",
        "needle": "    return ms, ts",
        "replacement": "    return (ts if ts is not None else ms), ms",
        "why": "Field swap: the epoch second is reported as the duration. "
               "Produces enormous plausible-looking millisecond values.",
    },
]


def apply_mutant(source: str, mutant: dict) -> str:
    """Replace exactly once, or refuse.

    A mutation that fails to APPLY reports GREEN — the harness would count a kill
    it never attempted. So an anchor that does not match exactly once is a hard
    error, not a skip.
    """
    needle, replacement = mutant["needle"], mutant["replacement"]
    count = source.count(needle)
    if count != 1:
        raise AssertionError(
            f"mutant {mutant['id']!r}: anchor matched {count} times, expected "
            "exactly 1. The source was refactored — re-target the mutant "
            "rather than deleting it."
        )
    mutated = source.replace(needle, replacement)
    if mutated == source:
        raise AssertionError(f"mutant {mutant['id']!r}: replacement was a no-op")
    return mutated


def load_module(source: str, name: str, path: Path):
    """Exec ``source`` as a standalone module. Never touches disk."""
    spec = importlib.util.spec_from_loader(name, loader=None)
    module = importlib.util.module_from_spec(spec)
    module.__file__ = str(path)
    exec(compile(source, str(path), "exec"), module.__dict__)
    return module


def _fake_redis_class():
    """The ONE fake, imported from the wiring suite rather than re-declared."""
    spec = importlib.util.spec_from_file_location(
        "_lat_p040_wiring", str(WIRING_TEST)
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._Redis


_Redis = _fake_redis_class()


# --------------------------------------------------------------------------
# Oracles
# --------------------------------------------------------------------------
def _seed(rs_mod, fake, samples, task="t"):
    from app.tasks.redis_state import TASK_METRICS_PREFIX
    for ms, ts in samples:
        rs_mod._push_duration(fake, task, ms, now_s=ts)
    fake.hashes.setdefault(
        f"{TASK_METRICS_PREFIX}:{task}", {b"consecutive_failures": b"0"}
    )


def oracle_adherence(adh_mod) -> None:
    """Assertions the grader must satisfy. Raises on violation."""
    # 1. The span is the sample's, never the counter's.
    g = adh_mod.adherence(
        starts=1149, starts_window_s=68673.0, interval_s=30.0,
        durations_ms=[46000, 5000], durations_window_s=3000.0,
        durations_saturated=False,
    )
    assert g["p95_window_s"] == 3000.0, g["p95_window_s"]
    assert g["window_s"] == 68673.0, g["window_s"]
    assert g["p95_window_s"] != g["window_s"]
    assert g["p95_sample_n"] == 2, g["p95_sample_n"]

    # 2. A real overrun stays a real overrun, and names its scope.
    g2 = adh_mod.adherence(
        starts=1149, starts_window_s=68673.0, interval_s=30.0,
        durations_ms=[46000] * 50, durations_window_s=2940.0,
        durations_saturated=True,
    )
    assert g2["verdict"] == "overruns", g2["verdict"]
    assert "over the last 50 runs" in g2["reason"], g2["reason"]
    assert "49min" in g2["reason"], g2["reason"]
    assert "saturated" in g2["reason"], g2["reason"]

    # 3. An unknown span is admitted, never invented.
    g3 = adh_mod.adherence(
        starts=1149, starts_window_s=68673.0, interval_s=30.0,
        durations_ms=[46000] * 10, durations_window_s=None,
    )
    assert "span unknown" in g3["reason"], g3["reason"]
    assert "0min" not in g3["reason"], g3["reason"]


def oracle_storage(rs_mod) -> None:
    """Assertions the storage must satisfy. Raises on violation."""
    from app.tasks.redis_state import TASK_METRICS_PREFIX

    # 1. The span is measured from the stamps.
    fake = _Redis()
    _seed(rs_mod, fake, [(100, BASE_TS), (200, BASE_TS + 600), (300, BASE_TS + 1800)])
    rs_mod.get_redis_client = lambda: fake
    m = rs_mod.get_task_metrics("t")
    assert m["recent_durations_ms"] == [300, 200, 100], m["recent_durations_ms"]
    assert m["recent_durations_window_s"] == 1800.0, m["recent_durations_window_s"]
    assert m["recent_durations_saturated"] is False

    # 2. Saturation is reported at exactly the cap, and the history is bounded.
    fake2 = _Redis()
    n = rs_mod.DURATION_HISTORY_LEN
    _seed(rs_mod, fake2, [(i, BASE_TS + i * 60) for i in range(n + 20)])
    rs_mod.get_redis_client = lambda: fake2
    m2 = rs_mod.get_task_metrics("t")
    assert m2["recent_durations_n"] == n, m2["recent_durations_n"]
    assert m2["recent_durations_saturated"] is True
    assert m2["recent_durations_window_s"] == float((n - 1) * 60), \
        m2["recent_durations_window_s"]
    assert len(fake2.lists[f"{TASK_METRICS_PREFIX}:t:durations"]) == n

    # 3. Legacy bare-int entries still read, with an honestly unknown span.
    fake3 = _Redis()
    fake3.lists[f"{TASK_METRICS_PREFIX}:t:durations"] = [b"300", b"200"]
    fake3.hashes[f"{TASK_METRICS_PREFIX}:t"] = {b"consecutive_failures": b"0"}
    rs_mod.get_redis_client = lambda: fake3
    m3 = rs_mod.get_task_metrics("t")
    assert m3["recent_durations_ms"] == [300, 200], m3["recent_durations_ms"]
    assert m3["recent_durations_window_s"] is None, m3["recent_durations_window_s"]

    # 4. The durations key carries a TTL — the M19-class assertion, which only
    #    has something to fail against because the fake models expire().
    fake4 = _Redis()
    _seed(rs_mod, fake4, [(100, BASE_TS)])
    assert fake4.ttl(f"{TASK_METRICS_PREFIX}:t:durations") == rs_mod.TASK_METRICS_TTL


def run() -> int:
    adh_src = ADHERENCE.read_text()
    rs_src = REDIS_STATE.read_text()

    # Control: unmutated sources must PASS both oracles, or every "kill" below
    # is just a broken harness reporting success.
    adh_ctl = load_module(adh_src, "_ctl_adherence", ADHERENCE)
    oracle_adherence(adh_ctl)
    rs_ctl = load_module(rs_src, "_ctl_redis_state", REDIS_STATE)
    oracle_storage(rs_ctl)
    print("control: both oracles PASS on unmutated source")

    killed, survived, unapplied = [], [], []

    for group, src, path, oracle, prefix in (
        (ADHERENCE_MUTANTS, adh_src, ADHERENCE, oracle_adherence, "adh"),
        (REDIS_MUTANTS, rs_src, REDIS_STATE, oracle_storage, "rs"),
    ):
        for mutant in group:
            try:
                mutated = apply_mutant(src, mutant)
            except AssertionError as exc:
                unapplied.append((mutant["id"], str(exc)))
                print(f"  UNAPPLIED  {mutant['id']}: {exc}")
                continue
            try:
                mod = load_module(mutated, f"_mut_{prefix}_{mutant['id']}", path)
                oracle(mod)
            except Exception as exc:
                killed.append(mutant["id"])
                print(f"  killed     {mutant['id']}  ({type(exc).__name__})")
            else:
                survived.append((mutant["id"], mutant["why"]))
                print(f"  SURVIVED   {mutant['id']}  <-- {mutant['why']}")

    total = len(ADHERENCE_MUTANTS) + len(REDIS_MUTANTS)
    print(f"\n{len(killed)}/{total} killed, {len(survived)} survived, "
          f"{len(unapplied)} unapplied")

    if survived or unapplied:
        # Non-zero on EITHER. An unapplied mutant is not a pass; it is a mutant
        # that was never attempted, and counting it as one is how a harness
        # reports coverage it does not have.
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
