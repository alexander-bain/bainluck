# Event-Page Atlas Design Authority (`2026-10`)

Tracked design authority files copied unchanged from `~/bainluck/artifacts/discovery-containers-release-plan/event-page-design-20261011/` so builders and reviewers can open them directly on GitHub `master` (`#12016`, `#11974`).

## Rulings that supersede sections of these files

These design documents and prototype sources predate three later product rulings. Builders must build to the rulings below (do not reopen):

1. **#11929 — Solid line through unobserved time (no gap call-outs)**: Charts draw a continuous solid line across unobserved intervals (`NEVER_A_HOLE_MS`). Never port the prototype's blank chart gaps, gap call-outs, or refusal to tap inside an unobserved interval.
2. **#11995 (decision 6-A) — Server-side normalization for one-winner fields**: Mutually exclusive one-winner fields are normalized server-side inside existing guards (160% raw-sum ceiling, one-cent floor exclusion, scale-down only). The client prints the server's numbers and never normalizes on the client. Independent sets (qualifiers, thresholds) are never normalized.
3. **#11990 — Whole numbers by default; one decimal for DNPL fast-moving probabilities**: Display whole-number percentages by default, using one decimal place (`0.1%`) only where the probability is DNPL-fed and fast-moving.

## Source Paths (copied unchanged)

| Tracked file | Exact source path under `~/bainluck/artifacts/discovery-containers-release-plan/event-page-design-20261011/` |
|---|---|
| `COMPONENT-CONTRACT.md` | `atlas-v6/COMPONENT-CONTRACT.md` |
| `IMPLEMENTATION-CONTRACT.md` | `event-system-handoff-v133/IMPLEMENTATION-CONTRACT.md` |
| `HEADLINE-PHASE-CONTRACT-20261021.md` | `HEADLINE-PHASE-CONTRACT-20261021.md` |
| `PROBABILITY-LANGUAGE.md` | `PROBABILITY-LANGUAGE.md` |
| `ADOPTION-MAP.json` | `event-system-adoption-current-v473/ADOPTION-MAP.json` |
| `src/` | `t20-chart-first-v471/prototype/src/` |
