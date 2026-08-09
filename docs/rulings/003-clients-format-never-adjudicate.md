# RULING 003 — Clients format, never adjudicate

date: 2026-08-09
author: Alex
via: Fable, from the over-engineering audit
issues: #1546 · #1547

**DO NOT REMOVE (CI-guarded).**

> The backend publishes **typed decisions** — lifecycle, results, availability, calibration
> evidence. Web and native **render** them. No client independently derives ECE or Brier,
> winners, lifecycle labels, or availability. **Every parity bug routes to a typed backend
> decision, not a client patch.**

## Named failures

- **Native fabricated winners on one missing score.** A client deriving "who won" from partial
  data invents an answer when the data is incomplete, because a renderer has no way to say
  "undecided" unless something upstream gave it that state.
- **Playoff clinched/eliminated dropped.** A real, computed lifecycle decision existed and simply
  did not survive the trip to the surface.
- **Dual ECE derivations.** The same calibration number computed twice, in two languages, which
  guarantees they drift and guarantees nobody can say which is right.

## Why it is stated as an absolute

Every one of those is the same bug: a client asked a question it was not authorised to answer.
Once N clients each derive a decision, the product has N answers to a question the user believes
has one — which directly violates the standing ruling that **the blend is the product**, one
number per question, at the surface layer instead of the source layer.

The corollary is the operative half. "Route the parity bug to a typed backend decision" means a
client-side patch that makes two surfaces agree is **not** a fix; it is a third derivation. The
fix is upstream, once, and every surface gets it — including the ones nobody has reported yet.

This also makes *settled means settled* enforceable rather than aspirational: if settled state is
a typed decision, a surface cannot render a settled thing as live without ignoring a field, which
is visible in review. Today it can do it just by computing.
