# Futures-Page Atlas Study (`2026-11`)

Tracked futures study documents and source checks copied unchanged from branch `design/futures-page-proto` (`7a5f4a88c7`) so builders and reviewers can open them directly on GitHub `master` (`#12016`, `#883`, `#11974`). The prototype route `/kernels-preview` is intentionally omitted.

## Rulings that supersede sections of these files

These study documents predate three product rulings. Builders must build to the rulings below (do not reopen):

1. **#11929 — Solid line through unobserved time (no gap call-outs)**: Charts draw a continuous solid line across unobserved intervals (`NEVER_A_HOLE_MS`). Never port the prototype's blank chart gaps, gap call-outs, or refusal to tap inside an unobserved interval.
2. **#11995 (decision 6-A) — Server-side normalization for one-winner fields**: Mutually exclusive one-winner fields are normalized server-side inside existing guards (160% raw-sum ceiling, one-cent floor exclusion, scale-down only). The client prints the server's numbers and never normalizes on the client. Independent sets (qualifiers, thresholds) are never normalized.
3. **#11990 — Whole numbers by default; one decimal for DNPL fast-moving probabilities**: Display whole-number percentages by default, using one decimal place (`0.1%`) only where the probability is DNPL-fed and fast-moving.

## Source Paths on `design/futures-page-proto` (`7a5f4a88c7`, copied unchanged)

| Tracked file | Exact source path on `7a5f4a88c7` |
|---|---|
| `futures-page-2026-11.md` (and `../futures-page-2026-11.md`) | `docs/designs/futures-page-2026-11.md` |
| `STUDY-README.md` | `artifacts/discovery-containers-release-plan/event-page-design-20261011/futures-page-20261103/README.md` |
| `SOURCE-CHECKS.md` | `artifacts/discovery-containers-release-plan/event-page-design-20261011/futures-page-20261103/SOURCE-CHECKS.md` |
| `ADOPTION-MAP.json` | `artifacts/discovery-containers-release-plan/event-page-design-20261011/futures-page-20261103/ADOPTION-MAP.json` |
| `HOSTED-RECEIPT.json` | `artifacts/discovery-containers-release-plan/event-page-design-20261011/futures-page-20261103/HOSTED-RECEIPT.json` |
| `compose.py` | `artifacts/discovery-containers-release-plan/event-page-design-20261011/futures-page-20261103/compose.py` |
| `hosted-dialog-console-checks.json` | `artifacts/discovery-containers-release-plan/event-page-design-20261011/futures-page-20261103/hosted-dialog-console-checks.json` |
| `hosted-extra-checks.json` | `artifacts/discovery-containers-release-plan/event-page-design-20261011/futures-page-20261103/hosted-extra-checks.json` |
| `hosted-field-checks.json` | `artifacts/discovery-containers-release-plan/event-page-design-20261011/futures-page-20261103/hosted-field-checks.json` |
| `hosted-journey-checks.json` | `artifacts/discovery-containers-release-plan/event-page-design-20261011/futures-page-20261103/hosted-journey-checks.json` |
| `hosted-qualification-checks.json` | `artifacts/discovery-containers-release-plan/event-page-design-20261011/futures-page-20261103/hosted-qualification-checks.json` |
| `hosted-render-checks.json` | `artifacts/discovery-containers-release-plan/event-page-design-20261011/futures-page-20261103/hosted-render-checks.json` |
| `hosted-wide-checks.json` | `artifacts/discovery-containers-release-plan/event-page-design-20261011/futures-page-20261103/hosted-wide-checks.json` |
| `local-render-checks.json` | `artifacts/discovery-containers-release-plan/event-page-design-20261011/futures-page-20261103/local-render-checks.json` |
| `screenshot-manifest.json` | `artifacts/discovery-containers-release-plan/event-page-design-20261011/futures-page-20261103/screenshot-manifest.json` |
| `source-manifest.json` | `artifacts/discovery-containers-release-plan/event-page-design-20261011/futures-page-20261103/source-manifest.json` |
