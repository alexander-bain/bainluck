# Discover Human Labeling

Human labels are the editorial ground truth for Discover ranking quality. They
are advisory by default: a raw label must not change production ranking unless a
reviewer records an explicit bounded promote/downrank decision.

## Goals

- Measure whether the top of Discover is tapworthy, clear, diverse, and timely.
- Identify repeated failure classes that deterministic ranking can fix.
- Calibrate LLM judges against human majority labels before using auto-evals.
- Create a future training set for an offline reranker without replacing hard
  quality caps.

## Labeling Units

| Unit | Stable ID | Primary Use |
| --- | --- | --- |
| Single card | `item_type` + `market_id` or `event_id` | Tapworthiness, clarity, image/explanation quality |
| Pairwise comparison | `card_a_market_id` + `card_b_market_id` | Rank-order calibration |
| Story comparison | two item IDs or `story_key`/`group_id` | Duplicate and family suppression |
| Explanation review | item ID + current headline/hook snapshot | Hook/context evals |
| Image review | item ID + image URL snapshot | Media fit evals |
| Fixable-interest review | item ID + current card snapshot | Ranking repairs and issue creation |

Store enough snapshot context with every label to make it useful after ranking
changes: surface, rank seen, score, category, archetype, story key, group ID,
headline/hook, image URL, reviewer, batch ID, and timestamp.

## Core Labels

### Single-Card Labels

| Field | Values | Meaning | Product Use |
| --- | --- | --- | --- |
| `tapworthy_score` | `1` to `5` | Would the reviewer open or keep browsing because of this card? | Primary gold-set target, Precision@K, future reranker |
| `overall_label` | `love`, `fine`, `bad`, `kill` | Compact editorial verdict for existing admin flows | Backward-compatible summary and triage |
| `boring` | `true`, `false` | Card is not worth first-page placement for a casual user | `boring-rate@20`, downrank bucket discovery |
| `clarity` | `clear`, `needs_context`, `confusing` | Whether the market is understandable in a few seconds | Headline/context eval |
| `explanation_quality` | `good`, `generic`, `misleading`, `missing` | Whether hook/context explains why the market matters | Hook generation and auto-eval target |
| `image_fit` | `good`, `neutral`, `bad`, `wrong_entity`, `not_needed` | Whether the image improves the card | Image sourcing/eval target |
| `audience_scope` | `broad`, `category_fan`, `niche`, `almost_nobody` | Who would naturally care? | Broad-appeal and niche penalties |
| `resolution_importance` | `high`, `medium`, `low` | Whether the outcome will feel meaningful when it resolves | Low-stakes demotion |

### Fixable-Interest Labels

Some cards are not good as shown but reveal a high-value ranking or data-source
opportunity. Capture this as structured counterfactual feedback instead of only
marking the card bad.

| Field | Values | Meaning | Product Use |
| --- | --- | --- | --- |
| `would_be_interesting_if` | free text, optional | The smallest change that would make the card good | Human-readable repair context |
| `fixable_interest_score` | `1` to `5` | How good the card would be if the issue were fixed | Prioritize repair work |
| `fix_type` | `staleness`, `wrong_entity_rank`, `missing_context`, `bad_image`, `wrong_market_variant`, `duplicate_variant`, `category_mismatch`, `data_bug`, `ranking_rule`, `other` | What kind of fix is implied | Route to ranking, data, UI, or issue queue |
| `desired_entity_or_variant` | free text, optional | The entity/variant that should have appeared, such as "#1 Netflix movie" | Candidate recall and substitution diagnostics |
| `current_entity_or_variant` | free text, optional | The stale or less relevant entity/variant currently shown | Debug comparison |
| `create_issue_candidate` | `true`, `false` | Whether this should become a GitHub issue if repeated or severe | Admin triage queue |

Examples:

- "Interesting if this were about the #1 movie on Netflix, not #2."
- "Interesting if it were not stale and still had a live resolution date."
- "Interesting if the card explained why this local election matters."
- "Interesting if the image showed the actual person/entity."

Fixable-interest labels should flow into three buckets:

- Data bug or stale card: create or update a GitHub issue when severe or repeated.
- Ranking-rule problem: aggregate into gold-set evals and ranking-tune work.
- Better variant exists: use as candidate-recall or story-substitution training
  signal, not as a direct boost for the current card.

### Pairwise Labels

| Field | Values | Meaning | Product Use |
| --- | --- | --- | --- |
| `choice` | `a`, `b`, `both`, `neither`, `skip` | Which card belongs higher in Discover? | Pairwise accuracy and reranker training |
| `confidence` | `low`, `medium`, `high` | How obvious the choice was | Disagreement routing |
| `ranking_error` | `true`, `false` | Current order feels wrong enough to investigate | Ranking hill-climb queue |

Pairwise batches should target adjacent ranks, score ties, current-vs-near-miss
pairs, ground-truth misses, and cases where LLM/eval signals disagree.

### Story And Duplicate Labels

| Field | Values | Meaning | Product Use |
| --- | --- | --- | --- |
| `story_relationship` | `same_question`, `same_story_family`, `related`, `unrelated` | How strongly two cards overlap | `group_id`, `story_key`, family caps |
| `duplicate_severity` | `none`, `minor`, `major` | Whether both cards can appear in one session/page | Duplicate-family eval |

Use `same_question` when two markets ask the same real-world question. Use
`same_story_family` when they differ but would still feel repetitive in the feed
such as multiple Russia/Ukraine territory markets.

## Reason Chips

Positive chips explain why a card is interesting:

- `movement`
- `public_story`
- `high_stakes`
- `close_probability`
- `source_disagreement`
- `celebrity_or_person`
- `sports_relevance`
- `fun_or_weird`
- `timely`
- `surprising_probability`
- `major_event`

Failure chips explain why a card should be downranked or repaired:

- `finance_ladder`
- `commodity_ladder`
- `too_niche`
- `duplicate`
- `stale`
- `unclear`
- `bad_image`
- `low_stakes`
- `repetitive`
- `misleading`
- `generic_hook`
- `wrong_category`
- `not_a_real_prediction`

Reason chips are multi-select. They should be used for diagnostics and training
features, not as direct ranking rules until reviewed.

Backend ingestion, exports, and evals canonicalize legacy chip aliases so labels
from older web/native surfaces remain comparable. Unknown experimental tags are
kept in normalized snake case instead of dropped. Current aliases:

| Legacy alias | Canonical chip |
| --- | --- |
| `fun`, `weird`, `funny` | `fun_or_weird` |
| `important` | `high_stakes` |
| `newsworthy`, `public` | `public_story` |
| `close` | `close_probability` |
| `disagreement` | `source_disagreement` |
| `celebrity`, `person` | `celebrity_or_person` |
| `sports` | `sports_relevance` |
| `surprising` | `surprising_probability` |
| `major` | `major_event` |
| `needs_context`, `no_context`, `missing_context`, `confusing` | `unclear` |
| `bad_explanation`, `generic` | `generic_hook` |
| `wrong_image` | `bad_image` |
| `niche` | `too_niche` |
| `duplicate_family` | `duplicate` |
| `bucket`, `dated_bucket` | `repetitive` |

## Gold-Set Metrics

Human labels should feed offline evals before production ranking changes:

| Metric | Source Labels | Target |
| --- | --- | --- |
| `tapworthy@20` | `tapworthy_score >= 4` or `overall_label = love` | Increase |
| `boring-rate@20` | `boring = true` or `overall_label in (bad, kill)` | 0 |
| `duplicate-family-rate@20` | `story_relationship`, `duplicate_severity` | 0 major duplicates |
| `unclear-rate@20` | `clarity != clear` | Decrease |
| `bad-explanation-rate@20` | `explanation_quality in (generic, misleading, missing)` | Decrease |
| `bad-image-rate@20` | `image_fit in (bad, wrong_entity)` | Decrease |
| `broad-appeal@20` | `audience_scope in (broad, category_fan)` | Increase |
| `pairwise-accuracy` | `choice` against rank order or proposed scores | Increase |

Eval reports should split by category, source, story family, and surface when
sample size allows.

## LLM Judge Calibration

LLM judges can expand advisory coverage only after calibration against human
majority labels. Track agreement by label type before trusting auto-labels.

Likely high-signal LLM targets:

- duplicate/story family
- clarity
- explanation quality
- niche versus broad appeal
- generic or misleading hook detection

Lower-confidence LLM targets:

- true tapworthiness
- personal taste
- sports fan relevance
- image quality

LLM labels must include prompt/schema version, confidence, and whether they were
human-reviewed. They must not run inside `GET /api/feed`.

## Rollout Order

1. Label 100-200 real Discover cards and pairwise comparisons.
2. Compute gold-set evals against the current ranking.
3. Fix the largest deterministic failure bucket.
4. Re-run the same labeled eval before shipping.
5. Calibrate an LLM judge against the human set.
6. Consider an offline reranker only after roughly 1,000-2,000 single-card
   labels, 500+ pairwise labels, and repeated labels for agreement.
