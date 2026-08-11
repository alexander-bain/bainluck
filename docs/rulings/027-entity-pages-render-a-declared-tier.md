# RULING 027 — Entity pages render a backend-declared tier; chrome is earned by counts

date: 2026-08-11
author: Alex
via: Fable, ratified
issues: #1548
relates: ruling 003 (backend declares, clients render), ruling 021 (two graders reading one input share the DECISION), ruling 025 (the availability envelope — `degraded` and `empty` are different renderings), ruling 026 (freshness is one architecture; the same envelope carries `as_of`)

Every auto-generated entity page — league, competition, team, player — renders a **tier declared
by the backend** (`full | standard | answer | present`), computed from countable answers next to
`availability`. Clients never infer a layout by measuring arrays. Chrome is **earned by the count
it organizes**: a tab row needs two tabs of three, a rail needs four items, a section header needs
a second section, and a cap is always counted ("Showing 12 of 112"). And **degraded ≠ empty** — a
page with nothing to say says so at full identity fidelity with the record we uniquely keep, while
a page whose query died says *that* instead. The full system, its thresholds, and the build order
are in [docs/entity-page-templates.md](../entity-page-templates.md).

**WHY.** Auto-generated pages die one specific death: the template is designed for the rich case,
and the thin case renders the rich case's chrome with nothing in it — a section header over one
card, a two-card carousel, "+1 more", an empty state that says "check back later" and names
neither a why nor a when. We already grow all three at home. The fix is not more empty states; it
is refusing to treat a thin page as a broken rich page. **A page with two markets is a complete
two-answer page**, and the only thing that makes that true in practice is that the *tier is a typed
decision made once, server-side*. The moment web and SwiftUI each count arrays to pick a layout,
the same team renders as a map on one and an answer on the other, and the parity bug is unfindable
because both clients are "correct" (ruling 021's named failure, applied to layout). This is the
availability envelope promoted from a response field to a page architecture, and the probability
doctrine's "the number is honest or absent" applied to layout: **chrome is honest or absent too.**
