# RULING 006 — Process artifact hygiene

date: 2026-08-09
author: Alex
via: Fable, from the over-engineering audit
issues: #1621

**DO NOT REMOVE (CI-guarded).**

> The Integrator **sweeps redundant handoff/status artifacts** — `.bak`, `.tmp`, dead queue
> files — **under standing scope**, needing no per-cycle approval.
>
> **Process success is measured by deployment latency and escaped defects, not artifact count.**

## Why the second sentence is the real ruling

The first sentence is permission. The second is the thing that stops the process from becoming
the work.

A process layer that measures itself by its own artifacts will always report progress: more
queues, more reports, more locks, more scoreboards. None of that is visible to a user. Deployment
latency and escaped defects are, and they can both get *worse* while artifact count improves —
which is precisely the failure mode of a lane system that is optimising itself.

Making the sweep standing scope removes the other half of the trap: needing approval to delete a
dead `.tmp` file guarantees the file survives, because nobody spends a decision on it. The
Integrator already holds the lock and already touches the handoff directory every cycle.

## The one carve-out

Sweeping is for **redundant** artifacts. A handoff file that is stale is not automatically
redundant — INT-027 found queue files describing shipped work as pending, and the fix was to
*correct* them, not delete them, because the drift itself was the evidence. Delete duplicates and
debris; rotate stale records.
