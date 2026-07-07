# Search Curation Spec — grouped family rows ("the Fed test")

Written 2026-07-06 (Fable). Gates L2-40. Origin: Alex-Test Interview #1 — Kalshi won "fed rate decision" not on search but on *composition*: a curated family (July decision 85% · cut-before-2027 23% · dissents · dollar-move), each row an inline answer. Alex's decision: that's our target shape. Binding context: `docs/chart-design-spec.md` (P2/P3 chrome), D1 (no odds — probabilities only), the stale-suppression rule (resolved/overtaken never surface), no LLM in request paths.

## The one-sentence spec

A topical query returns a **composed answer set**: the headline market first, then its family — related markets about the same question-space — each rendered as an inline answer (leader + probability + 24h movement arrow), not a link list.

## Family formation (deterministic, all signals already in the DB)

Assemble candidate families from, in priority order:
1. **`group_id`** — sub-markets of one real-world question collapse to ONE row (the group's volume-winning representative), never shown as siblings.
2. **Series/ticker prefix** — Kalshi series siblings (e.g. the KXFED* family) and `market_metadata` event linkage.
3. **Story keys** — the existing feed story-key machinery (`story:*`) for topical clusters.
4. **Cross-source pairs** — `find_cross_source_markets()` matches merge into one row (blended display; never two rows for the same question from two venues).

A family forms only when ≥2 distinct member questions survive dedup + stale-suppression; otherwise return flat results (a lone answer needs no scaffolding).

## Response shape (backend-composed — the frontend must not reassemble)

Extend the search response with `futures_families: [{family_key, label, headline, members[]}]`, where headline/members reuse the existing formatted-market shape (`top_outcomes` normalized, placeholder-filtered). Flat `futures` stays for non-family results and API compatibility. Typeahead is NOT composed — it keeps single best-answer suggestions (the 150ms budget rules).

## Ordering

Family relevance = best member's name-match score (the L2-38 rerank machinery — name-match beats outcome-match, volume orders within). Headline = the family's volume-winning name-match. Members: relevance, then volume; show ≤4 with "+N more" expanding. Families interleave with flat results by their headline's rank — a strong flat result is not buried under a weak family.

## Row rendering (per chart-spec P2/P3 + D1)

Question title · leader name + probability (normalized, leader-pick rule applied — "Other/Field" never leads) · 24h movement arrow (≥2pts) · resolution date if <30d out. No odds, no source names (blend only), no images required in v1. One tap → detail page.

## Acceptance

The interview's exact trace: "fed rate decision" on Bain Luck composes ≥4 distinct Fed markets with inline answers — matching or beating the Kalshi composition Alex pasted (July decision / cut-by / funds-rate level / dissents-class). Plus: "lebron james" (family = Next Team headline + MVP/scoring props), "super bowl" (winner + related), benchmark re-run, latency within the 400ms search budget, and the Alex eyeball as the final gate.

## Sequencing

L2-40 after L2-39 (readability + suppression land first — composing unreadable rows would compound the flagship failure). The backend composition is one queue; frontend family rows a second if needed. Entity *pages* (Phase 4) remain evidence-gated — this spec may be enough destination.
