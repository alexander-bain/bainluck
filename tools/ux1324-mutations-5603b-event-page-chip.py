# ux1324-mutations-5603b-event-page-chip.py — the #5603 event-page guard's own
# battery. Run from the repo root; it edits `EventHeader.tsx` in place and
# restores it in a `finally`, so a Ctrl-C does not leave a mutant on disk.
#
# Measured 2026-09-18 02:58Z: 5/5 caught, 4 distinct signatures, control green.
# The one worth reading is `label-arg-dropped` (the helper called with the
# namespace only) — it is caught by exactly ONE arm, "a real UFC card keeps its
# name", which is what makes that control load-bearing rather than decoration.
import subprocess, re
F = "frontend/components/event/EventHeader.tsx"
ORIG = open(F).read()
LINE = "<span>{conceptDomainLabel(event.sport_label, event.domain)}</span>"
MUTANTS = {
  # The exact shape codex named as the trap: correct on a fresh payload, the
  # defect again on every envelope cached before the backend half released.
  "or-fallback": "<span>{event.sport_label || event.domain}</span>",
  # The ship clause alone is satisfied by this.
  "hardcode-combat": "<span>COMBAT</span>",
  # Reading the namespace through the helper's SECOND argument only.
  "label-arg-dropped": "<span>{conceptDomainLabel(undefined, event.domain)}</span>",
  # The reverse: trusting the label and losing the unevidenced arm entirely.
  "namespace-arg-dropped": "<span>{conceptDomainLabel(event.sport_label, undefined)}</span>",
  # Suppress the chip: passes nothing-says-UFC, loses a true label.
  "chip-deleted": "<span></span>",
}
CONTROL = LINE  # unmutated
def run():
    r = subprocess.run(["npx","jest","--testPathPatterns=theEventPageChipNamesTheSportNotTheNamespace5603"],
                       cwd="frontend", capture_output=True, text=True)
    m = re.search(r"Tests:\s+(?:(\d+) failed, )?(\d+) passed", r.stdout + r.stderr)
    return r.returncode, (m.group(0) if m else "?")
try:
    caught, sigs = 0, {}
    for name, repl in MUTANTS.items():
        open(F,"w").write(ORIG.replace(LINE, repl))
        code, summary = run()
        status = "CAUGHT" if code != 0 else "SURVIVED"
        caught += code != 0
        sigs[summary] = sigs.get(summary, 0) + 1
        print(f"{name:24} {status:9} exit={code}  {summary}")
    open(F,"w").write(ORIG)
    code, summary = run()
    print(f"{'CONTROL (unmutated)':24} {'GREEN' if code==0 else 'RED':9} exit={code}  {summary}")
    print(f"\n{caught}/{len(MUTANTS)} caught, {len(sigs)} distinct signatures, control {'survived' if code==0 else 'FAILED'}")
finally:
    open(F,"w").write(ORIG)
