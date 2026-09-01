#!/usr/bin/env python3
"""UX-P249 mutation battery — is the LIVE LOOK's honesty actually guarded?

This ship is three claims about TIME, and every one of them fails in a way that
looks perfect on a screenshot. A screenshot cannot show you that the number is
tweening through values nobody quoted, that the age belongs to a different
number than the one on screen, or that the sparkline auto-fitted a flat window
into a dramatic climb. So the mutants are those three, plus the ways each
degrades quietly.

  A-D  the throttle: too fast, too slow, wrong value, swallowed last update
  E-H  the age: bound to the wrong point, no upper limit, still pulsing
  I-K  the sparkline: auto-fitted, smoothed, drawn on too little data
  L-M  the frame parser: the sibling-event filter and the age requirement

  N-O  the render details: the reduced-motion class, and whole-point output

⚠️ N IS A KILL WITH A NAMED LIMIT. It proves only that the `motion-reduce` CLASS
is emitted — no jsdom in this repo evaluates a media query, so "a reader with
reduced motion really sees no transition" is not proven anywhere here. That is a
browser check and it is OWED, not claimed.

⚠️ O WAS SCORED SURVIVE, CAME BACK KILL, AND IS RE-SCORED TO THE MEASUREMENT.
Its comment keeps the wrong prediction and the reason it was wrong, because a
battery whose predictions are quietly edited to match its results measures
nothing.

Every edit is proven to apply, sources restore inside `finally:`, and the
restore is verified byte-for-byte by sha256.

Run from `frontend/`:  python3 scripts/uxp249_live_look_battery.py
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

LOGIC = Path("lib/live/liveNumber.ts")
VIEW = Path("components/live/LiveLook.tsx")
WIRE = Path("hooks/useLiveBlend.ts")

TEST_PATTERN = "liveLook"

# (id, file, find, replace, expect, what it models)
MUTANTS: list[tuple[str, Path, str, str, str, str]] = [
    (
        "A",
        LOGIC,
        "export const LIVE_CHANGE_MIN_INTERVAL_MS = 5_000;",
        "export const LIVE_CHANGE_MIN_INTERVAL_MS = 0;",
        "KILL",
        "the throttle is off — every frame repaints, which is the flickering "
        "hero the <=1-change/~5s ruling exists to prevent",
    ),
    (
        "B",
        LOGIC,
        "  if (now - state.shownAt >= LIVE_CHANGE_MIN_INTERVAL_MS) {\n    return commit(state, point, now);\n  }\n  return { ...state, pending: point };",
        "  if (now - state.shownAt >= LIVE_CHANGE_MIN_INTERVAL_MS) {\n    return commit(state, point, now);\n  }\n  return state.pending ? state : { ...state, pending: point };",
        "KILL",
        "🔴 THE HELD POINT IS QUEUED RATHER THAN REPLACED — a burst paints its "
        "FIRST value and the display is a whole interval behind the market",
    ),
    (
        "C",
        LOGIC,
        "export function tickLiveDisplay(state: LiveDisplayState, now: number): LiveDisplayState {\n  if (!state.pending) return state;",
        "export function tickLiveDisplay(state: LiveDisplayState, now: number): LiveDisplayState {\n  if (!state.pending) return state;\n  if (true) return state;",
        "KILL",
        "🔴 THE LAST UPDATE OF A BURST IS SWALLOWED — traffic stops while a point "
        "is held and no later frame carries it in. Invisible under the steady "
        "traffic a test naturally sends",
    ),
    (
        "D",
        LOGIC,
        "  const moved = Math.round(point.value) - Math.round(previous);",
        "  const moved = point.value - previous;",
        "KILL",
        "direction judged on the RAW float, so 61.4 -> 61.6 tints digits that "
        "did not move — the animation crying wolf on nearly every frame",
    ),
    (
        "E",
        LOGIC,
        "  if (state.shown && point.observedAt <= state.shown.observedAt) return state;",
        "  if (false) return state;",
        "KILL",
        "a replayed SSE frame walks the hero BACKWARDS. Reconnects replay, so "
        "this is not hypothetical",
    ),
    (
        "F",
        LOGIC,
        "  if (ageMs > LIVE_AGE_LIMIT_MS) {\n    return { tone: \"paused\", label: `updates paused · ${formatLiveAge(ageMs)}`, ageMs };\n  }",
        "",
        "KILL",
        "🔴 NO UPPER LIMIT ON 'LIVE' — a green pulsing dot over a five-minute-old "
        "number. This is the Flow Sentinel's own defect class, rendered",
    ),
    (
        "G",
        LOGIC,
        "  const ageMs = Math.max(0, now - observedAt);",
        "  const ageMs = now - observedAt;",
        "KILL",
        "a clock disagreement prints a NEGATIVE age — '-3s ago', a number more "
        "live than the present",
    ),
    (
        "H",
        VIEW,
        '  live: { dot: "bg-accent-live animate-pulse motion-reduce:animate-none", text: "text-accent-live" },\n  waiting: { dot: "bg-text-muted", text: "text-text-muted" },\n  paused: { dot: "bg-accent-warning", text: "text-accent-warning" },',
        '  live: { dot: "bg-accent-live animate-pulse motion-reduce:animate-none", text: "text-accent-live" },\n  waiting: { dot: "bg-text-muted", text: "text-text-muted" },\n  paused: { dot: "bg-accent-live animate-pulse", text: "text-accent-live" },',
        "KILL",
        "the DEGRADED state still pulses green. The label is honest and the "
        "pixel is not, which is the version a reader actually believes",
    ),
    (
        "I",
        VIEW,
        "      <Sparkline\n        data={windowed.map((p) => p.value)}\n        width={width}\n        height={height}\n        color=\"trend\"\n        stroke={1.5}\n      />",
        "      <Sparkline\n        data={windowed.map((p) => p.value)}\n        domain=\"auto\"\n        width={width}\n        height={height}\n        color=\"trend\"\n        stroke={1.5}\n      />",
        "KILL",
        "🔴 THE AXIS IS AUTO-FITTED — a 0.4-point wobble draws a dramatic climb "
        "across the full height of the box. The most tempting change to this "
        "component and the one that makes it lie",
    ),
    (
        "J",
        LOGIC,
        "export const LIVE_SPARKLINE_MIN_POINTS = 3;",
        "export const LIVE_SPARKLINE_MIN_POINTS = 1;",
        "KILL",
        "a one-point window is drawn — a zero-length path, an empty box that "
        "reads 'no data' when the truth is 'nothing has changed'",
    ),
    (
        "K",
        LOGIC,
        "    .filter((p) => Number.isFinite(p.value) && p.observedAt > floor && p.observedAt <= now)",
        "    .filter((p) => Number.isFinite(p.value))",
        "KILL",
        "the ten-minute window is not a window — an hour-old observation is "
        "drawn as part of the last ten minutes",
    ),
    (
        "L",
        WIRE,
        "  if (Number(frame.event_id) !== expectEventId) return null;",
        "",
        "KILL",
        "🔴 A SIBLING'S FRAME PAINTS THIS CARD. The endpoint takes a comma list, "
        "so one connection really does carry other events' numbers",
    ),
    (
        "M",
        WIRE,
        "  const observedAt = Date.parse(String(frame.observed_at ?? \"\"));\n  if (!Number.isFinite(observedAt)) return null;",
        "  const observedAt = Date.parse(String(frame.observed_at ?? \"\"));\n  const _ = observedAt;",
        "KILL",
        "a frame with no honest age is accepted, in a feature whose entire claim "
        "is the age",
    ),
    (
        "N",
        VIEW,
        "motion-reduce:transition-none ",
        "",
        "KILL",
        "⚠️ SCORED AS A KILL BUT READ THE LIMIT: this proves only that the CLASS "
        "is emitted. No jsdom in this repo evaluates a media query, so 'a reader "
        "with reduced motion really sees no transition' is NOT proven by any "
        "test here — it is a browser check, and it is owed rather than claimed.",
    ),
    (
        "O",
        VIEW,
        "      {Math.round(value)}%",
        "      {value.toFixed(1)}%",
        "KILL",
        "a decimal hero — '61.6%' where the product prints whole points. "
        "⚠️ FIRST SCORED SURVIVE AND THE BATTERY SAID OTHERWISE. I reasoned that "
        "`data-live-value` rounds independently of the text and talked myself "
        "into a survivor; the run came back KILL because the text assertion is "
        "`toBe('62%')`, which is exactly the coverage I was unsure about. "
        "Re-scored to what was MEASURED. The lesson is the cheap one: a "
        "prediction is a hypothesis, and the battery is the instrument.",
    ),
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_guards() -> int:
    return subprocess.run(
        ["npx", "jest", "--testPathPatterns", TEST_PATTERN],
        capture_output=True,
        text=True,
        env={**os.environ, "TZ": "UTC"},
    ).returncode


def main() -> int:
    files = sorted({m[1] for m in MUTANTS})
    original = {f: f.read_text() for f in files}
    original_sha = {f: sha(f) for f in files}

    baseline = run_guards()
    if baseline != 0:
        print(f"BASELINE IS NOT GREEN (exit {baseline}) — battery is meaningless")
        return 2
    print("baseline: GREEN\n")

    wrong: list[str] = []
    try:
        for mid, path, find, repl, expect, why in MUTANTS:
            src = original[path]
            if src.count(find) != 1:
                print(f"{mid}: ANCHOR NOT UNIQUE ({src.count(find)} hits in {path}) — battery invalid")
                return 2
            mutated = src.replace(find, repl)
            assert mutated != src, f"{mid}: mutation is a no-op"
            path.write_text(mutated)
            assert sha(path) != original_sha[path], f"{mid}: file unchanged on disk"
            if repl:
                assert repl in path.read_text(), f"{mid}: mutant text absent after write"

            code = run_guards()
            path.write_text(src)
            assert sha(path) == original_sha[path], f"{mid}: restore not byte-identical"

            got = "KILL" if code != 0 else "SURVIVE"
            ok = got == expect
            if not ok:
                wrong.append(mid)
            print(f"{'OK ' if ok else '***'} {mid}: expected {expect}, got {got} (exit {code}) — {why}")
    finally:
        for f in files:
            f.write_text(original[f])
            assert sha(f) == original_sha[f], f"RESIDUE: {f} not restored"
        print("\nsources restored, sha256 verified")

    killed = sum(1 for m in MUTANTS if m[4] == "KILL")
    print(f"\n{killed} predicted kills, {len(MUTANTS) - killed} scored survivors, "
          f"{len(wrong)} unexpected")
    return 1 if wrong else 0


if __name__ == "__main__":
    sys.exit(main())
