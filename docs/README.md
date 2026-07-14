# docs/ — the Bain Luck documentation index

One screen to navigate the drawer. `CLAUDE.md` (repo root) is the always-loaded
index + gotcha hot-list; everything below is the deeper reference it points to.
When you change something, update the doc named in **Update trigger** in the same change.

> Convention: living docs sit in `docs/`. Point-in-time artifacts (superseded
> strategy, old prompts, dated diagnoses, trip plans) live in `docs/archive/`
> (see `docs/archive/README.md`). Don't let a dated one-off masquerade as living.

## Plan of record & priorities
| Doc | Purpose | Update trigger |
|-----|---------|----------------|
| `execution-plan-2026-07-13.md` | Current operating plan: programs P1–P7, week table, Opus operating model, standing rules | Weekly; when programs ship/change |
| `PRD.md` | Product voice: vision, reliability bar, journeys, principles (rev 2026-07-14) | When product theses change (Alex rulings) |
| `backlog.md` | Strategic backlog: priorities, rationale, long-term context | When items ship, are added, or reprioritized |
| `github-workflow.md` | GitHub Issues/Project operating model + backlog-sync rules | When labels, templates, columns, or agent-handoff rules change |
| `decisions-2026-07-06.md` | Decision register (the calibration "done" bar and related rulings) | When a durable product/eng decision is ratified |

## Architecture & engineering reference
| Doc | Purpose | Update trigger |
|-----|---------|----------------|
| `architecture-reference.md` | Core system design: aggregation, resilience, matching, tasks, sentinels, cockpit, admin | When architecture changes |
| `gotchas-reference.md` | Full gotcha catalog + incident learnings (CLAUDE.md keeps the hot ~15) | When a new gotcha is discovered |
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
| `golf-product-strategy.md` | Golf coverage & product strategy | When golf strategy changes |
| `calibration-project.md` | Calibration program scope & outcomes | When the calibration program changes |
| `championship-grids-project.md` | Championship-grid program | When grid scope changes |
| `prediction-market-improvement-plan.md` | Prediction-market coverage/matching improvement plan | When the plan changes |
| `search-curation-spec.md` | Search result curation spec | When search curation rules change |
| `app-store-launch-plan.md` | App Store submission plan & checklist | When the launch plan changes |

## Runbooks, playbooks & setup guides
| Doc | Purpose | Update trigger |
|-----|---------|----------------|
| `calibration-diagnosis-playbooks.md` | Step-by-step calibration diagnosis recipes | When a new diagnosis class is learned |
| `search-fts-runbook.md` | Postgres full-text search runbook | When search indexing changes |
| `alert-intake.md` | Alert-intake operating model (auto-filed issues → board) | When the alert/sentinel rails change |
| `ios-app-setup-guide.md` | iOS/macOS build & signing setup | When the native build setup changes |
| `ga4-setup-guide.md` | GA4 analytics setup guide | When analytics config changes |

## Design briefs & specialized references
| Doc | Purpose |
|-----|---------|
| `design-brief-event-detail-v2.md` | Event-detail redesign brief (props = the script) |
| `claude-design-context.md` | Context handed to Claude Design projects |
| `ios-code-quality-plan.md` | iOS code-quality/refactor plan |
| `tv-mode-plan.md` | TV / second-screen mode plan |
| `designs/`, `mockups/`, `design-handoffs/` | HTML mockups & design handoff bundles |

## Point-in-time diagnoses & inventories
Dated, single-purpose captures — read for context, not as living spec. Candidates
for `archive/` once fully consumed:
`sports-page-leak-diagnosis-2026-06-18.md`, `us-open-market-coverage-diagnosis-2026-06-18.md`,
`weather-market-inventory.md`, `issue-roadmap-2026-q3.md` (superseded by the execution plan),
`ds-veteran-analysis.md`, `ga4-setup-prompt.md`, and the trip cluster
(`trip-recap-and-next-steps.md`, `italy-trip-masters-plan.md`, `travel-guide.md`).

## Archive
`docs/archive/` holds superseded strategy docs, old prompts, dated diagnoses, and
trip plans — preserved, never deleted. See `docs/archive/README.md`.
