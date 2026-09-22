#!/usr/bin/env python3
"""grade-reconnect-8079.py — live/515. Turn a reconnect-watch-8079.mjs capture into per-phase verdicts.

Every clause is phrased so that a rig that silently did nothing FAILS it rather than passing it.
The BASE clause exists for exactly that reason: if the page was not delivering before the first
cut, no statement about recovery afterwards means anything, so BASE is graded first and a red BASE
voids the run.

Usage: grade-reconnect-8079.py <capture.jsonl> [venue_timeline.json]
"""
import json
import sys
from collections import defaultdict

cap = sys.argv[1]
rows = [json.loads(l) for l in open(cap)]
t0 = rows[0]["t"]
rel = lambda r: r["t"] - t0  # noqa: E731

start = next((r for r in rows if r["kind"] == "start"), {})
scale = start.get("scale", 1)
cut_via = start.get("cut_via", "?")

# Phase windows, from the capture's own boundary records — never recomputed from the plan, so a
# phase that drifted (a slow screenshot, a hung evaluate) is graded where it ACTUALLY ran.
bounds = [(rel(r), r["phase"]) for r in rows if r["kind"] == "phase"]
end = rel(rows[-1])
windows = []
for i, (at, name) in enumerate(bounds):
    stop = bounds[i + 1][0] if i + 1 < len(bounds) else end
    windows.append((name, at, stop))


def during(name, kinds=None, pred=None):
    lo, hi = next((a, b) for n, a, b in windows if n == name)
    out = []
    for r in rows:
        if kinds and r["kind"] not in kinds:
            continue
        if not (lo <= rel(r) < hi):
            continue
        if pred and not pred(r):
            continue
        out.append(r)
    return out


def line(ok, label, detail):
    print(f"  [{'GREEN' if ok else '  RED'}] {label}: {detail}")
    return ok


print(f"capture={cap}  scale={scale}  cut_via={cut_via}  duration={end:.0f}s")
print("phases: " + ", ".join(f"{n}@{a:.0f}-{b:.0f}s" for n, a, b in windows))
if scale != 1:
    print("\n!! SCALE != 1 — the OFFLINE_LONG arm does not cross SILENCE_TIMEOUT_MS. Rig check only.\n")

verdicts = {}

print("\nBASE — the positive control. A red here voids every later clause.")
frames = during("BASE", {"sse"}, lambda r: r.get("type") == "probability")
vis = during("BASE", {"visible"})
heroes = {v.get("heroProb") for v in vis if v.get("heroProb")}
base_ok = line(len(frames) >= 1, "push delivered", f"{len(frames)} probability frame(s) received")
base_ok &= line(len(vis) >= 1, "DOM moved", f"{len(vis)} visible change(s), hero values {sorted(heroes)}")
verdicts["BASE"] = base_ok

for arm, expect_recover in (("OFFLINE_SHORT", True), ("OFFLINE_LONG", False)):
    print(f"\n{arm} — was the transport genuinely severed?")
    hb = during(arm, {"sse"}, lambda r: r.get("type") == "heartbeat")
    errs = during(arm, {"sse"}, lambda r: r.get("type") == "error")
    fails = during(arm, {"request_failed"})
    cut_ok = line(len(hb) == 0, "no heartbeats crossed the cut",
                  f"{len(hb)} heartbeat(s) during the outage (setOffline let 2 through in 50s)")
    cut_ok &= line(len(errs) >= 1 or len(fails) >= 1,
                   "the page saw the failure", f"{len(errs)} EventSource error(s), {len(fails)} failed request(s)")
    verdicts[f"{arm}:severed"] = cut_ok

    after = "RECOVER_SHORT" if arm == "OFFLINE_SHORT" else "AFTER"
    print(f"{after} — did push come back?")
    opens = during(after, {"sse"}, lambda r: r.get("type") == "open")
    newframes = during(after, {"sse"}, lambda r: r.get("type") == "probability")
    streams = during(after, {"request"}, lambda r: r.get("which") == "stream")
    got = len(opens) >= 1 or len(newframes) >= 1
    if expect_recover:
        verdicts[f"{after}:push"] = line(
            got, "push resumed", f"{len(opens)} open, {len(newframes)} frame(s), {len(streams)} stream request(s)")
    else:
        # NOT graded as a defect: `liveStreamController.stop()` is documented terminal, and the
        # hook's promise is polling, not a reopen. Recorded as the fact the next clause turns on.
        print(f"  [ note] push resumed: {got} — {len(opens)} open, {len(newframes)} frame(s), "
              f"{len(streams)} stream request(s) (terminal stop is by design; the poll clause below is the test)")
        verdicts[f"{after}:push_resumed"] = got

print("\nAFTER — the contract: 'degrade to polling, never to a frozen number.'")
polls = during("AFTER", {"request"}, lambda r: r.get("which") == "poll" and "/events/" in r.get("url", ""))
poll_times = [round(rel(r)) for r in polls]
verdicts["AFTER:polling"] = line(len(polls) >= 2, "the poll fallback ran",
                                 f"{len(polls)} event poll(s) at {poll_times}s")
vis_after = during("AFTER", {"visible"})
hero_after = [v.get("heroProb") for v in vis_after if v.get("heroProb")]
moved = len(set(hero_after)) > 1
print(f"  [ note] hero values observed in AFTER: {hero_after or '(no visible change recorded)'}")

badges = defaultdict(list)
for r in rows:
    if r["kind"] == "badge":
        badges[r.get("phase")].append(r.get("badge"))
print("\nBADGE HONESTY — what the page claimed about freshness while the transport was dead.")
for name, _, _ in windows:
    b = badges.get(name) or []
    if b:
        print(f"  {name:14s} first={b[0]!r} last={b[-1]!r} ({len(b)} changes)")
    else:
        print(f"  {name:14s} (no badge change recorded)")

print("\nSUMMARY")
for k, v in verdicts.items():
    print(f"  {'GREEN' if v else 'RED  '}  {k}")
reds = [k for k, v in verdicts.items() if not v]
print(f"\n{len(verdicts) - len(reds)} GREEN / {len(reds)} RED" + (f" -> {reds}" if reds else ""))
