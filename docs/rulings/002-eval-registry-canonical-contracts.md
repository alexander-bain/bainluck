# RULING 002 — Eval registry: canonical contracts by domain

date: 2026-08-09
author: Alex
via: Fable, from the over-engineering audit
issues: #1544

**DO NOT REMOVE (CI-guarded).**

> One registry file lists the canonical eval contracts, by domain. Codex owns it. **Every new
> eval must extend or explicitly supersede a canonical contract, and name it in its header.**

## Named failure

**286 eval artifacts with overlapping oracles.** Not 286 things tested — 286 files, many
asserting the same behaviour through differently-shaped fixtures, with no way to tell which one
is authoritative when two disagree.

## Why this is the fix rather than a cleanup

The instinct is to dedupe. Deduping 286 artifacts is a one-time cost that buys nothing durable,
because the mechanism that produced them is still running: each new audit writes a fresh corpus
from scratch, since finding the prior contract is harder than writing a new one.

Naming the parent in the header inverts that. The cheap path becomes "find the canonical contract
and extend it", and the expensive path — a new canonical contract — is exactly the one that
should be deliberate. **Supersession stays available and must be explicit**, so a contract can be
replaced but not silently forked.

The registry also makes a disagreement legible: when two evals contradict, the one that names the
canonical contract wins, and the other is a bug rather than a second opinion.
