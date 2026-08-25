# RULING 134 — Build lanes BUILD: measurement is its own lane, and an idle build lane is a signal

date: 2026-08-25
author: Alex (banked by lane1, Q406 SHIP directive)
issues:
supersedes:

---

## The ruling

Verbatim, as ratified into `CLAUDE.md` under the PROGRESS, NOT MEASUREMENT section:

> **LANE ROLES (Alex ruling 2026-08-25):** build lanes BUILD — their only permitted measurement is
> their own gates (tests, deploy checks, rollback verification). All other measurement — censuses,
> probes, audits, diagnosis, and every cert — belongs to the measurement lane (the non-Claude
> windows on the mission bus), fed by PARKED-MEASUREMENTS.md and staged only when a named ship
> needs the answer. Heavy measurement queries never run while an attended fold or apply is in
> flight. An idle build lane is a signal, not a failure — never fill it with measurement.

## Why — the drift this stops, in this repo's own recent record

A build lane holding a measurement capability will use it, and every individual use is defensible.
That is the whole problem: nothing in the moment tells you that you have stopped building. The lane
runs a census because the census would answer something; it files what the census found; the finding
earns a probe; the probe earns a re-measurement. Each step is real work producing real artifacts, and
at the end of it the product has not changed.

The failure is not laziness and it is not rigour. It is that **measurement is the path of least
resistance for a lane that is blocked, waiting, or between ships** — it always has something to
offer, it never fails outright, and it produces an artifact that reads like progress. So the fix is
not "measure less." It is to make measurement a thing a lane *cannot* reach for, by moving it to a
different lane entirely and requiring a named ship to pull it.

## The three parts, and what each one is load-bearing against

**1. A build lane's only permitted measurement is its own gates.** Tests, deploy checks, rollback
verification — the things that tell it whether the thing it just built works. Not "measurement is
banned"; the boundary is *whose* correctness is being established. A gate answers "did my change
do what I said." A census answers "what is the state of the world," and that is a different lane's
question even when the same lane is curious.

**2. Measurement is pulled by a ship, not pushed by curiosity.** `PARKED-MEASUREMENTS.md` is the
mechanism, and parking is a real state rather than a polite refusal: the finding is true, it was
paid for, and it waits. A measurement staged with no named ship behind it is the drift this ruling
names, whichever lane runs it.

**3. Heavy measurement never runs during an attended fold or apply.** This one is operational, not
philosophical, and it has the sharpest edge. An attended apply is a human watching a production
mutation; a heavy query landing beside it competes for the same database and turns a clean
observation into an ambiguous one. It also does the thing ruling 132 forbids — mutating or loading
the population you were about to measure. The apply is the ship; the measurement can wait an hour.

## An idle build lane is a signal

This is the clause that will be hardest to obey, so it is stated as an instruction rather than an
observation. A build lane with nothing to build is telling you something true: there is no named
ship ready for it. The correct responses are to find the ship, unblock the one that is stuck, or
leave the lane idle. The incorrect response — and the one that feels responsible — is to fill it
with measurement, because that converts a legible signal ("we have no ship queued") into an
illegible one ("everyone is busy").

An idle lane is cheap and visible. A lane busy on work that serves no ship is expensive and looks
exactly like a lane serving one.

## Binds

- **A build lane that finds itself running a census, probe, audit or diagnosis has already broken
  this** — the correct move is to stop, park the finding, and stage it to the measurement lane with
  the ship named. Discovering the breach mid-run is not a reason to finish the run.
- **Certs are measurement.** They belong to the non-Claude windows on the mission bus. This
  reinforces author-never-certifies from the other direction: the author's lane is the wrong lane
  for the cert not only because it is the author, but because it is a build lane.
- **A lane may always measure to establish that its own change works.** If the distinction is
  genuinely unclear, the test is whether the answer would still matter if the change were reverted:
  if yes, it is world-state and belongs to the measurement lane.
- **Never fill an idle build lane with measurement**, and never report an idle lane as a failure of
  the lane.

## What this does NOT say

It does not devalue measurement, and it is not a licence to build on unmeasured assumptions. The
measurement lane exists, is staffed, and is fed by a real queue; this ruling routes the work rather
than reducing it. Nor does it forbid a build lane from *reading* an existing measurement — consuming
`PARKED-MEASUREMENTS.md`, a prior cert or an audit doc is exactly what those artifacts are for.

It also does not make "is this a gate or a census" a self-certifying judgment. A lane that labels a
world-state query as a gate to keep running it has mis-declared the thing the routing was computed
from, which is the more serious finding — the same shape as ruling 133's read-only-tier clause.

## General form

**Give the work that always has something to offer its own lane, and require a named ship to pull
it. Capability in the wrong lane is not capacity — it is drift with an artifact trail.**
