# docs/ — the Bain Luck documentation index

One screen to navigate the drawer. `CLAUDE.md` (repo root) is the always-loaded
index + gotcha hot-list; everything below is the deeper reference it points to.
When you change something, update the doc named in **Update trigger** in the same change.

> **Priority lives on the board, not here.** The
> [GitHub Issues board](https://github.com/alexander-bain/bainluck/issues) is the
> only source of priority and status. These docs hold judgment, architecture, and
> reference — never ordering. (`backlog.md` was retired 2026-07-31; its final
> snapshot is `archive/backlog-2026-07-24-final.md`.)

> Convention: living docs sit in `docs/`. Point-in-time artifacts (superseded
> strategy, old prompts, dated diagnoses, finished programs) live in `docs/archive/`
> (see `docs/archive/README.md`). Don't let a dated one-off masquerade as living.

## Judgment & product voice
| Doc | Purpose | Update trigger |
|-----|---------|----------------|
| `PRODUCT-BRAIN.md` | The judgment layer: standing rulings, the WHY behind them, how Alex works, the lane split | When Alex issues a new ruling (append + date) |
| `PRD.md` | Product voice: vision, reliability bar, journeys, principles (rev 2026-07-14) | When product theses change (Alex rulings) |
| `decisions-2026-07-06.md` | Decision register (the calibration "done" bar and related rulings) | When a durable product/eng decision is ratified |
| `github-workflow.md` | GitHub Issues/Project operating model, labels, columns, agent-handoff rules | When labels, templates, columns, or handoff rules change |

## Architecture & engineering reference
| Doc | Purpose | Update trigger |
|-----|---------|----------------|
| `architecture-reference.md` | Core system design: aggregation, resilience, matching, tasks, sentinels, cockpit, admin | When architecture changes |
| `gotchas-reference.md` | Full gotcha catalog + incident learnings (CLAUDE.md keeps the hot list) | When a new gotcha is discovered |
| `quality-audit.md` | Audit-script usage + check catalog | When checks are added/removed |
| `hill-climb-guide.md` | Matching-accuracy hill-climb playbook (measure → fix bucket → re-measure) | When matching layers/gotchas change |
| `aggregation-weighting-methodology.md` | How the blended probability + source weights are computed | When source weights or the blend change |

## Feature & product docs
| Doc | Purpose | Update trigger |
|-----|---------|----------------|
| `feature-reference.md` | Detailed per-feature documentation (files, endpoints, behavior) | When features ship or change |
| `completed-features.md` | Chronological shipped-features log | When features ship |
| `design-system.md` | Visual system: color, type, motion, voice, components, settled-state & concept-page patterns | When design tokens or patterns change |
| `interestingness-rules.md` | Alex's Discover interestingness rules (R1–R10) | When Discover ranking rules change |
| `discover-labeling.md` | Discover labeling/eval methodology | When the labeling/eval loop changes |
| `product-pitch.md` | The short external product pitch | When positioning changes |
| `chart-design-spec.md` | Chart principles (fixed 0–100 axis, no smoothing, settled journey) | When chart rules change |

## Strategy & program docs (living)
| Doc | Purpose | Update trigger |
|-----|---------|----------------|
| `strategy-instant-answers.md` | Instant Answers program: fastest merged entity-question answer (search + speed) | When the search/speed program changes |
| `search-curation-spec.md` | Search result curation spec | When search curation rules change |
| `app-store-launch-plan.md` | App Store submission plan & checklist | When the launch plan changes |

## Runbooks & playbooks
| Doc | Purpose | Update trigger |
|-----|---------|----------------|
| `calibration-diagnosis-playbooks.md` | Step-by-step calibration diagnosis recipes | When a new diagnosis class is learned |
| `search-fts-runbook.md` | Postgres full-text search runbook | When search indexing changes |
| `alert-intake.md` | Alert-intake operating model (auto-filed issues → board) | When the alert/sentinel rails change |

## Specialized references
| Path | Purpose |
|------|---------|
| `chart_census.md` | Inventory of chart surfaces across web and native |
| `audits/` | Point-in-time audit outputs |
| `designs/`, `mockups/`, `design-handoffs/` | HTML mockups & design handoff bundles |

## Archive
`docs/archive/` holds superseded strategy docs, retired program plans, old prompts,
dated diagnoses, setup guides, and the final backlog snapshot — preserved, never
deleted. See `archive/README.md`. Notable entries retired on 2026-07-31:

- `archive/backlog-2026-07-24-final.md` — the retired strategic backlog (board owns priority now)
- `archive/execution-plan-2026-07-13.md`, `archive/issue-roadmap-2026-q3.md` — superseded planning docs
- `archive/calibration-project.md`, `archive/championship-grids-project.md`, `archive/prediction-market-improvement-plan.md`,
  `archive/golf-product-strategy.md`, `archive/tv-mode-plan.md`, `archive/ios-code-quality-plan.md` — finished or superseded programs
- `archive/ga4-setup-guide.md`, `archive/ga4-setup-prompt.md`, `archive/ios-app-setup-guide.md` — one-time setup guides
- `archive/design-brief-event-detail-v2.md`, `archive/claude-design-context.md`, `archive/design-handoffs/` (the weather + economics chat transcripts) — consumed design briefs
- `archive/sports-page-leak-diagnosis-2026-06-18.md`, `archive/us-open-market-coverage-diagnosis-2026-06-18.md`,
  `archive/weather-market-inventory.md`, `archive/ds-veteran-analysis.md`, `archive/trip-recap-and-next-steps.md` — dated one-offs
