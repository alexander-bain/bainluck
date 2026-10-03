# #9935 — Theme collection PRODUCER contract (Authority)

**PILLARS** MATCHING · DISCOVER · TRUTH.
**SHIP** An AI or Oscars preview opens the same complete, correctly scoped collection on a URL that still works when membership changes.

**Status: CONTRACT v3, DEFINED. Root has accepted the definition: AI continuing `ai` = A, finite Oscars 2027, Discover's six amendments, and the hydration-time fold.** #9935 stays **Conditional / Blocked / Defined / not Ready**. No app source changed, no production, API or provider call, no dispatch, no source claim. Current claims are unchanged: Authority owns identity and membership, Discover owns relevance, the NFL/MLB publication owners keep their files. The `container_member_decisions` table is **proposed, not approved**: its migration is D45, Alex's word only. Nothing here authorizes a migration, publication or activation.

Source basis: `6e4afb6` (v1). Re-checked 2026-10-03 01:3xZ: `git diff --stat 6e4afb6 origin/master(38601bf8f2) -- backend/app` touches 9 files, none of them cited here (events.py, futures.py, calibration ×4, search_headline_contender, sports_imminent_marquee, standings_shape). Every line number cited below was re-read at `38601bf8f2`. Examples come from #9925's evidence at `cbd3b254bc` (`artifacts/discovery-containers-release-plan/9925-theme-design/evidence/`), read from git, not re-queried.

**v3 changelog (2026-10-03 01:3xZ).** Applies the two definition repairs in `FROM-sol-design-20261003-0119Z-9935-V2-DELTA-RETURN-DEFINITION-ONLY` (review `9935-V2-DELTA-REVIEW.md`, which read v2 at SHA256 `12d51a9e…1222`, the file preserved beside this one as `.v2.md`):
- **A. A mapped target that is unavailable gives NO REF. There is no fallback to another subject** (§5, §8 case 18). The map now runs FIRST and is required. It names the one intended collection, and publication, revision and all-members are then checked against that collection only. v2's "the map breaks ties between candidates" shape is withdrawn, because it let a single published survivor win without a map entry.
- **B. The 14-day settled cutoff in the gather belongs to continuing AI only** (§4). The finite Oscars 2027 population is now defined on its own: the ceremony's Kalshi ticker family plus structurally titled Polymarket rows, with no status, `settled_at` or `created_at` cutoff, plus prior decisions. Finite `decide()` has no retention clause, so a member that settled 20 days before the first pass is gathered and admitted, and every rerun keeps it (new §8 cases 20, 21).
- Stale "waiting on root" / "if root accepts" wording is reconciled to the accepted state. No new acknowledgement gate.
- New §10: the producer source slice (exact files, current collisions, Discover dependency, proposed checks) and a separate migration/source/rollback packet boundary for Alex.

v2's own changelog follows, unchanged.

**v2 changelog (2026-10-03 00:4xZ).** Applies Discover's review `FROM-discover-20261003-0025Z-9935-RELEVANCE-REVIEW-accept-with-6-amendments` (read at `56572d727c`). Every line Discover cited was re-read at that sha before being adopted. Verdicts: AI continuing `ai` = A, both sides concur. Retention N = 14 days, accepted. §3 vocabulary and §6 accepted with amendments:
1. Retention clock is `settled_at`. `resolved_settle_time_unknown` is new, and the gather's settled signal is stated (§3 `ai-subject@1` clause 3, §4).
2. The Gemini AI context must sit next to the word (§3 clause 1).
3. "See all N" means questions SHOWN at the revision. The two presentation gates become hydration withholds and stay out of `decide()` (§4, §5).
4. §6 applies to any `kind: theme` bundle. That covers all three theme producers (§6.1).
5. The ref target is determined by a map and must be published. It is never searched for, and the link names the collection (§5, §6.1).
6. Fold parity: Authority's position for root is in §3. Membership is unchanged, and the fold happens at hydration if root accepts.
v1 is preserved beside this file as `PRODUCER-CONTRACT-9935.v1.md`.

---

## 0. What exists and what it can't carry (the evaluation the review asked for)

| Asset | Carries | Can't carry, with proof |
|---|---|---|
| `containers` (models.py:2705) + live `publication_state` / `membership_revision` (alembic `container_corrections`, live since v5297, 2026-09-30 07:12Z) | Unique slug = public identity; `category` for non-sport; window; revision; publication | No subject or edition field. Edition is read from the slug only, by `container_presentation.edition_for_slug`, which knows only NFL and MLB |
| `event_edges` `contains` (models.py:2892) | One market in many containers: `uq_event_edge` is `(parent_type, parent_id, child_type, child_id, kind)`. Reverse lookup `ix_event_edge_child` already exists. `class` / `source` / `confidence` | Exists only for ADMITTED members. No rule version, no evidence. An exclusion has no edge to hang on |
| `market_match_receipts` (models.py:2463) | The matcher's explanation | `uq_match_receipt_market`: **one row per market**, last writer wins on `container_id`. Two themes would overwrite each other and the matcher's receipt. Assembly already refuses to overwrite (`container_assembly._drop_matcher_owned_receipts`). Not usable |
| `container_corrections` ledger | Human withdraw/readmit/publish. Survives reruns. Taken under `lock_container_chain` | Append-only HUMAN decisions. Its own contract says "No correction adds a member", so automated per-pass admission doesn't belong there |
| `read_published` (container_corrections.py:690) | One statement gives one revision plus all member ids | No pagination or counts beyond `member_count`. That's fine: member ids are cheap, so pagination belongs at hydration (§5) |
| `event_awards.py` `CEREMONIES`, `classify_market`, `edition_year` | Ceremony from the Kalshi ticker stem; winner / nominations / novelty; edition from the ticker `-NN` | `edition_year` **falls back to the resolution-date year**, and Kalshi award dates are a Dec-31 placeholder. `derive_awards_concept` **falls back to the bare substring "oscar"** (the same hole as `_story_key` → Oscar Piastri/Collazo). Neither fallback may count as admission evidence (§3) |
| `_story_key` / `discover_bundles` theme bundles | Feed grouping hint. P3 category gate is Discover's | One key per market by cascade order (`13791997` "OpenAI IPO before 2027?" goes to IPOs). `story:major_entertainment_events` spans Met Gala, Grammys, Emmys and Oscars. Lexical, no edition. A *candidate* source only, never identity |
| `container_discovery.discover_collections` | Event-id-keyed collection offers; `DISCOVERABLE_SLUG_PATTERN` | Event-only and `nfl-`/`mlb-` only. A market-only theme can't be offered through it, so the feed needs a market-keyed reference (§6, Discover's) |

**Conclusion: one schema addition is necessary, the rest is code.** No DB CHECK constrains `containers.kind`, `event_edges.source` or `class` (checked in `containers_phase1.py`; the only CHECKs are not-own-parent, contains-has-class, not-self and confidence range). So the vocabulary below is code-only.

---

## 1. Subjects for the first ship (exactly two)

| | Oscars 2027 (finite edition) | AI (continuing) |
|---|---|---|
| slug | `oscars-2027` | `ai` |
| `containers.kind` | `award_show` (**existing**, no vocab change) | `theme` (**new code-only entry** in `CONTAINER_KINDS`) |
| `category` | `awards` | `ai` |
| window | `window_start` NULL; `window_end` = the edition's resolution backstop. It is a deadline bound, never a published date (`ceremony_end_date` rule) | both NULL. Continuing scope is stated in the definition, not inferred from NULL |
| scope | `finite`, edition `2027` (99th Academy Awards) | `continuing` |
| parent | none. An "Awards Season 2027" parent over several ceremonies is **later** (one level of `parent_container_id` already exists) | none |

**Why Oscars and not "Awards Season".** The review is right that `story:major_entertainment_events` can't name an edition. One ceremony has deterministic ceremony + edition + category evidence today: the Kalshi ticker grammar plus Polymarket's stated "Oscars 2027" / "99th Academy Awards". It is the materially different control the issue asks for.

**AI: continuing (`ai`), A. Authority recommended it, Discover concurred (v2), root accepted (v3).** A dated slug (`ai-2026-q4`) dies every quarter, and the URL is the ship. The decide-by sections (October / by New Year / later) are presentation. Retiring a resolved member is a *rule* exclusion with evidence (`resolved_beyond_retention`, §3), never absence. Advertising ongoing membership waits on **#9936**. Alternative B (dated) changes only the slug builder and window.

**Definitions live in code and are versioned, never a member list.** New pure module `backend/app/utils/theme_definitions.py` holds a registry of SUBJECTS (`oscars` editions, `ai`), on the precedent of `TENNIS_DRAWS`: "nobody writes a list of MEMBERS, not that nobody names the draws". Each definition carries:
`subject`, `scope ∈ {finite, continuing}`, `edition` (finite only), `rule_version` (e.g. `oscars-edition@1`, `ai-subject@1`), `slug()`, `gather_sql` (bounded, full-population; §4), `decide(candidate) -> Decision`.

**Canonical slug builder (deterministic, round-trips).**
- finite: `f"{subject}-{yyyy}"`
- continuing: `subject`

`edition_for_slug` gains one branch *after* the NFL/MLB branches. It returns `{"kind": "theme_edition", "subject": "oscars", "edition": 2027}` or `{"kind": "theme_continuing", "subject": "ai"}` **only if** the registry's own `slug()` reproduces the slug byte for byte. That is the same round-trip rule as `NflWeek` and `MlbPostseason`. Any other slug returns `None`. The slug never contains member ids, title or rank. `oscars-2031` parses, but no container exists, so `read_published` → `unavailable` (404) with no nearest guess.

---

## 2. One schema addition: `container_member_decisions` (migration-class, D45 attended)

```
id BIGSERIAL PK
container_id BIGINT NOT NULL REFERENCES containers(id) ON DELETE CASCADE
child_type VARCHAR(16) NOT NULL  -- 'market' | 'event'  (EDGE_NODE_TYPES)
child_id BIGINT NOT NULL
outcome VARCHAR(12) NOT NULL     -- 'admitted' | 'excluded' | 'withheld'
reason VARCHAR(40) NOT NULL      -- closed enum, §3
rule_version VARCHAR(32) NOT NULL
evidence JSONB NOT NULL          -- clause-by-clause, §3
revision INTEGER NOT NULL        -- containers.membership_revision written in the same txn
first_decided_at, last_decided_at TIMESTAMPTZ NOT NULL; attempt_count INTEGER NOT NULL DEFAULT 1
UNIQUE (container_id, child_type, child_id)   -- upsert target; bounded by candidates × collections
INDEX (child_type, child_id)                  -- "which collections decided about this question"
CHECK (outcome IN ('admitted','excluded','withheld'))
```

- **Admitted** members ALSO get the existing `event_edges` `contains` row with `source='theme_rule'` (new code-only `EDGE_SOURCES` entry), `confidence=1.000` for id- or ticker-structured admission, and `receipt_id=NULL`. `read_published`, hydration, corrections and the revision bump therefore work **unchanged**.
- **Excluded / withheld** members get only a decision row. No edge, and the matcher's receipt is never touched.
- **Corrections win.** A human `withdraw` in `container_corrections` still deletes the edge and blocks re-admission under the lock. The decision row records `reason='container_member_withdrawn'` (reusing `WITHHELD_WITHDRAWN`) so the evidence and the page agree.
- **Rejected alternative (smaller migration):** nullable `rule_version` + `evidence` columns on `event_edges`. It records admissions only, and per-member exclusion evidence would live only in per-pass logs. That fails the acceptance line "per collection/member evidence of admission/exclusion". It's listed so root can choose it knowingly.

---

## 3. Versioned predicates, reasons and evidence

Every `decide()` returns `{outcome, reason, rule_version, evidence: {clauses: [{clause, input, result}], inputs: {external_id, source, llm_sport_category, canonical_market_key, resolution_date, name}}}`. A confidence number alone is never the explanation.

**`oscars-edition@1`** runs its clauses in order, and the first failure decides:
1. `ceremony`: the Kalshi `external_id` contains `KXOSCAR` (the `CEREMONIES['oscars'].ticker` stem), or the Polymarket title matches `^(oscars?|academy awards?)\b` at a *title-structural* position (`"Oscars 2027: …"`, `"… at the 99th Academy Awards"`). **The bare substring "oscar" anywhere in a name is never sufficient.** Fail → `excluded/not_this_ceremony`.
2. `category_gate`: `llm_sport_category == 'entertainment'` (second independent signal, notice 40 rule 2). Fail → `excluded/wrong_category`.
3. `edition`: in strict precedence (a) the Kalshi ticker `-NN` token with `20≤NN≤45` (`edition_year`'s ticker arm **only**); (b) a title-stated year adjacent to the ceremony word; (c) `Nth Academy Awards` → `1928+N`. The resolution date is a **consistency check only**: it must be ≤ the edition backstop, or be the Dec-31 placeholder. It is never the sole evidence. Edition ≠ 2027 → `excluded/other_edition`. No (a)/(b)/(c) → `withheld/edition_unknown`.
4. `class` (section, never an exclusion) via `classify_market`: `category` → `title` (Winners), `nominations` → `advancement` (Nominations, "chance of a nomination"), `novelty` → `side_question` (attendance etc. are part of the ceremony, notice 40). Winner and nomination questions are both members, in different classes, so they are never one race.
5. `venue_title_conflict` (flag, not exclusion): a ticker category disagreeing with the title is recorded in evidence. Same-venue folding isn't ours.

**`ai-subject@1`:**
1. `entity`: the name names an AI company, model or product (`openai|anthropic|claude|gpt-?\d|chatgpt|deepseek|gemini|grok|xai|ai model|best ai|agi`). **Every ambiguous term carries a deny clause**: `claude` not followed by `monet|debussy|…` (the existing #8742 guard). **`gemini` counts only when the AI context is ADJACENT to the word (v2, Discover amendment 2):** `\bgoogle\s+gemini\b`, `\bgemini\s+\d`, or `\bgemini\s+(pro|flash|ultra|app|model)\b`. A context word anywhere else in the name does not count. Without adjacency, a Gemini-exchange row stored as `economics` with "app" or "pro" elsewhere in its name would pass clauses 1 and 2. Same for the constellation. Fail → `excluded/lexical_false_friend` (deny hit, or `gemini` with no adjacent context) or not a candidate. The Kalshi `KXGEMINI` stem in clause 2 does not rescue a clause-1 failure. The clauses run in order. Possible false negatives were checked against #9925's evidence (`cbd3b254bc`), not re-queried. Every observed AI Gemini market name has the context adjacent ("Next Gemini Flash Model…", "Next Google Gemini Pro Model…", "Gemini 3.5 Pro debut arena score", "Gemini App Downloads in September"). Bare "Gemini" appears only as an outcome label under "best AI model" markets, which pass on `best ai`. If a future AI title fails adjacency, it shows up as `lexical_false_friend` in the evidence, which is visible and fixable by bumping the rule version. It is never a silent admission.
2. `second_signal`: `llm_sport_category ∈ {tech, economics}`, **or** a Kalshi series stem whose own ticker names the entity (`KXCLAUDE`, `KXGEMINI`, `KXOPUS…`, `KXOAIANTH`, `KXIPOOPENAI`). This matters because `31835408` `KXOPUS48Y-27` is stored as `crypto`. A category alone is noisy. Fail → `excluded/wrong_category`.
3. `retention` (continuing scope; N = **14 days**, Discover's call, accepted v2). **The clock is `FuturesMarket.settled_at` and nothing else.** It is the observed transition stamp, written only through `market_settlement.settled_at_sql`/`settled_values` with COALESCE, so the first observation is kept (models.py:813). `resolution_date` is never the clock. It is a schedule, and Kalshi uses a Dec-31 placeholder there.
   - **Settled signal, stated because `status='open'` is not one (gotcha #33).** A row is settled if `status='resolved'` **or** `futures_liveness.market_reads_settled(market)` (futures_liveness.py:450) is true. That function has two arms, a graded winner that ends the contest and a confirmed venue-settled stamp, and it fails toward silence. Authority reuses it read-only and does not fork it. A bare `status='open'` therefore never admits a settled Kalshi AI row as a live member.
   - Settled and `settled_at` within 14 days → stays **admitted** with its result (settled means settled). Evidence records `settled_at` and which settled arm fired.
   - Settled and `settled_at` older than 14 days → `excluded/resolved_beyond_retention`.
   - Settled and `settled_at IS NULL` → `excluded/resolved_settle_time_unknown` (**new reason, v2**). NULL means "we did not see it settle", so it never means "within retention", and the ~400k rows resolved before the column existed stay out. Excluded, not withheld, on purpose: a withhold would add that ancient population to the withheld counts permanently. Expected live shape: a Kalshi row that reads settled while still `status='open'` sits here until the settled-events backfill moves it to `resolved`. That writer stamps `settled_at`, and the next pass re-decides it as admitted with its result. The stamp is late, never early, so retention can only run slightly long.
   - Why 14 days (Discover): the feed never shows a resolved future (`routes/feed.py:11246` filters `resolution_date >= now`), so this page is the only place a reader sees an AI result. Two weeks covers a reader who comes back weekly.
   - **This clause belongs to `ai-subject@1` only (v3, repair B).** `oscars-edition@1` has no retention clause and never reads `settled_at`: a settled Oscars 2027 member is admitted with its result however long ago it settled, including `settled_at IS NULL`. `resolved_beyond_retention` and `resolved_settle_time_unknown` can never be emitted by a finite definition. A finite edition's window ends at the edition backstop, and a settled member stays until the container's own lifecycle retires it (a container action, not a per-member rule).

**Closed reason enum (v1):**
- admitted: `admitted_ticker_edition`, `admitted_title_edition`, `admitted_entity_signal`
- excluded: `not_this_ceremony`, `wrong_category`, `other_edition`, `lexical_false_friend`, `resolved_beyond_retention`, `resolved_settle_time_unknown` (v2), `container_member_withdrawn`
- withheld (decision rows): `edition_unknown`
- hydration withholds (never decision rows; computed at read time, §4): `row_missing`, `unserializable`, `low_quality` (v2), `public_source_disagreement` (v2)

**Same-question duplicates are NOT folded in membership.** Kalshi `6173044` and Polymarket `57313556` (both 2027 Best Picture) are **two admitted members**, with two edges and two decision rows. The producer never averages or picks a winner (dedup is not aggregation). Lane1's P2 fold (#2693) and #9387's equivalence still own any change to that.

**Fold parity (Discover amendment 6; root ACCEPTED the hydration fold, v3).** The feed already folds this pair: `discover_bundles._dedupe_same_question_members` (:1409) inside bundles, and `fold_same_question_cards` (:1473) for standalone cards, both through `cross_source_matching.is_same_question` (:371). An unfolded page would show two rows for one question that Discover hides. **Accepted rule:** fold at **hydration** in the producer-refreshed read with those same functions, called and not reimplemented, and count folded questions. Membership, edges and decision rows stay per market, so a fold mistake can never delete evidence, and corrections still act on single markets. The page carries **no "unfolded" caption** (notice 34). v1's "the count states what is unfolded" is withdrawn.

---

## 4. Full inventory, counts, pagination

- **Gathering is full-population and bounded**, never the feed sample. Each definition declares its OWN candidate population (v3, repair B: v2 applied AI's 14-day cutoff to every definition, which on a first finite pass would never gather an Oscars member settled more than 14 days earlier). Every population is the union of the definition's own arms **plus** a prior-decision arm. It is paged by id cursor to the end, and `inventory_complete=true` only if the cursor reached the end inside the pass budget. A truncated pass writes `inventory_complete=false`. It **never retires** an unseen member (assembly's degraded-availability rule) and the payload says `partial`.
  - **Continuing `ai` (`ai-subject@1`)**: `futures_markets` rows whose `name` matches clause 1's entity pattern, any category, in **(a)** `status='open'` (clause 3's settled test is then applied in `decide()`, because an open Kalshi row may be settled, gotcha #33) **∪ (b)** `status='resolved' AND settled_at >= now() − interval '14 days'` (`settled_at` carries `index=True`). The 14-day cutoff exists only because continuing scope retires settled members by rule.
  - **Finite `oscars-2027` (`oscars-edition@1`)**: **no status, `settled_at`, `resolution_date` or `created_at` cutoff.** **(K)** `source='kalshi' AND external_id LIKE 'KXOSCAR%'`, any status. That is the ceremony's own ticker family (`CEREMONIES['oscars'].ticker`), every edition, so clause 3 writes `other_edition` evidence for `-26` rows (case 4). It is left-anchored, unlike the awards adapter's unanchored `ilike('%KXOSCAR%')` (event_awards.py:318). No index use is claimed: whether `uq_futures_source_external` serves a `LIKE` prefix depends on the column collation, and the population is one ticker family either way. **(P)** `source='polymarket' AND name ~* <clause-1 structural ceremony pattern>` (`^(oscars?|academy awards?)\b`, or `\b\d{1,3}(st|nd|rd|th) academy awards?\b`), any status, any category, so clause 2 writes `wrong_category` evidence where it bites. The edition is decided in `decide()` by clause 3, never by the gather. This is the same "the edition gate keeps a prior edition out, not the status" rule as event_awards.py:305–312 (#7979). Size is bounded by one ceremony's ticker family plus ceremony-titled Polymarket rows.
  - **Prior-decision arm (both scopes)**: every child that already has a decision row for this container. For `ai` this is what makes retirement an explicit rule exclusion: a member that ages out of arms (a)/(b) is re-decided to `resolved_beyond_retention`, not silently dropped. For `oscars-2027` it guarantees a decided member is re-decided on every rerun even if its row later stops matching (K)/(P), for example a renamed Polymarket title, so its outcome changes only with evidence.
- **Counts at revision N** (one statement with `read_published`'s ids):
  - `eligible_count` = admitted edges after corrections. This is the membership number, for admin and evidence.
  - `withheld_count{reason}` = decision rows `withheld` + hydration withholds: `row_missing` / `unserializable` (the existing `container_presentation` reasons), plus **`low_quality` and `public_source_disagreement` (v2, Discover amendment 3)**.
  - `excluded_count{reason}` = admin/evidence only, **never on the reader page** (notice 34).
  - **`shown_count` (v2)** = the number of questions the page SHOWS at revision N. That is admitted members minus every hydration withhold, after the same-question fold (§3, accepted).
- **Presentation gates stay OUT of `decide()`, but the count honours them (v2, Discover amendment 3).** Feed bundles never seat a `low_quality` or `public_source_disagreement` member (`discover_bundles._theme_member_eligible`, :720–734). Membership stays correct either way, because a low-quality AI question is still an AI question. The page applies the same gate at hydration, otherwise the card says 14 and the page shows 12. **One predicate, two callers:** the hydration read calls the bundler's own gate, which Discover lifts to a public helper in its own file, rather than an Authority copy. `classify_market_quality` (feed_market_quality.py:2948) is a pure function of stored fields, so the gate is computable outside the feed. Recorded at `56572d727c`: every write site sets `public_source_disagreement` to the literal `False` (discover_card_archetypes.py:938, discover_bundles.py:597), so today only `low_quality` can actually withhold. Calling the shared gate keeps card and page in step if that ever changes.
- **`preview_count` is Discover's**: how many members the card shows. The card's "See all N" reads **`collection_count = shown_count`** (v2; v1 said `eligible_count`) at a stated revision. It is computed by the producer-refreshed published read and **never inside `GET /api/feed`**.
- **Pagination**: `GET /api/containers/{slug}?revision=N&cursor=…&limit=…`. The id set comes from one `read_published` snapshot, so only hydration is paged. The cursor is `(class order, sort key, id)`. Counts are identical on every page of one revision. If the requested `revision` ≠ current, respond with page 1 of the current revision and `revision_moved: true`, never a mix. With no `revision` param, today's NFL/MLB behaviour is unchanged.

---

## 5. Same-revision identity and read controls

- One revision pins one payload: `membership_revision` is bumped in the same transaction as any edge or decision change, under `lock_container_chain` (existing).
- The feed's `collection_ref = {slug, name, revision, collection_count}` comes from a cached published read (producer-refreshed). It is not a live gather, and there is no synchronous LLM in any GET. **`name` is `containers.name` ("Oscars 2027"), never the bundle header ("Who wins awards season?")** (v2, amendment 5).
- **The ref target is DETERMINED, never searched for (v2 amendment 5; v3 repair A).** The map runs first and is required. There is no candidate search and no fallback.
  1. **Resolve the intended collection from the bundle's own feed key.** `theme_definitions.intended_collection(bundle) -> slug | None` is a pure function:
     - `grouped_by: story_key`: a static entry in the registry's **feed-key → collection map**. Each definition declares the `story_key` values it answers for (`story:ai → ai`, plus the entries Discover approves). No entry → `None`.
     - `grouped_by: group_id` (awards): the finite definitions' own clause 1 (ceremony) and clause 3 (edition) applied to **every preview member**. All members must yield the same `(ceremony, edition)` and that pair must be a registry definition (`oscars-2027`). A mixed pair or an unknown edition gives `None`. This is the definition's own deterministic evidence about each preview member, not an overlap count.
     - `grouped_by: swing_magnitude` and every other producer: no entry, `None`.
     A key that resolves to two collections is a registry bug, caught by a static test. At runtime it would also give `None`.
  2. **Check that one collection, and only that one.** It must be **published at the cached revision** (`read_published`), and it must hold **every** preview member as an admitted edge at that revision. Fail either check → **no ref**.
  3. **No ref** whenever step 1 gives `None` or step 2 fails, **even if some other published collection holds every preview member.** That case is exactly the one repair A closes: an OpenAI-IPO bundle keyed `story:ipos` maps to `ipos`. If `ipos` is unpublished, the bundle gets no ref, and it does NOT link to `ai`, which also holds every member. A link's meaning never changes with the publication state of a collection it was not keyed to. There is no largest-overlap, nearest or sole-survivor inference. The card keeps its current behaviour.
  Discover reviews every map entry because it owns the feed keys. The map is a list of SUBJECTS per feed key, never a list of members.
- Agreement assertion: at equal revision, card `collection_count` = page `shown_count`, and card preview ids ⊆ page member ids. If the revision moved, the page wins and the card refreshes on its next feed build.
- Publication stays human: `publish_container` through Sol's #9916 operator. Assembly never publishes.

---

## 6. Consumer scope (Discover reviews meaning and relevance first; listed, not claimed)

1. Feed preview → collection reference. The rule binds **any `kind: theme` bundle** (v2, Discover amendment 4), not only the story-key bundler. The target comes from §5 step 1, never from the edge lookup. At `56572d727c` there are three theme producers: the story-key bundler (`discover_bundles.py:1104`, `grouped_by: story_key`), **`assemble_awards_theme_bundles`** (:1958, emitting at :1937, `grouped_by: group_id`, where most feed Oscars previews actually come from), and the swings bundler (:2073, `grouped_by: swing_magnitude`). A theme bundle carries `collection_ref` **only when §5 step 1 names one collection and that collection is published at the cached revision and holds every preview member** (§5). Otherwise it carries no ref (`no_intended_collection` / `intended_collection_unavailable` / `preview_spans_collections`). A `story:major_entertainment_events` bundle mixing Grammys and Oscars gets no Oscars link. Swings bundles group by price movement across subjects, so they fail the rule on their own and carry no ref. Step 2's membership check uses `ix_event_edge_child`, which already exists. It verifies the named target and never selects one.
2. P3 category gate at both theme admission sites (Discover's, already scoped in #9925 README). This is independent of this producer.
3. The existing hub consumer `/collections/[slug]` plus `CollectionHub` reads `theme_edition` / `theme_continuing` and paginates. **Back needs building, not just wiring** (Discover, v2). Today the hub has a "Back to Discover" link and `collection-reading:{slug}` reading state (CollectionHub.tsx:11/66/85) but no feed-snapshot restore. Discover defines it now under root's acceptance (its own inbox note, same disposition).
4. **Settled (v2, §6.4 per Discover):** `/collections/oscars-2027` and the existing `/event/awards/oscars` ceremony page **link to each other and are not merged**. Both must show the same edition. The ceremony page is UX's file. Discover's card links to the collection.

---

## 7. Exact producer files (Authority) and collision notes

| File | Change | Class |
|---|---|---|
| `backend/app/utils/theme_definitions.py` | NEW, pure: registry, slug builder, strict edition parser, predicates, reason enum, evidence builder, and the per-definition **feed-key → subject map** (v2; Discover reviews the entries). It imports `event_awards.CEREMONIES` / `classify_market` and `futures_liveness.market_reads_settled` read-only, and edits neither | Green |
| Discover's file (`discover_bundles.py`), **not Authority's** | Lift `_theme_member_eligible` to a public helper so the hydration read calls the same gate (v2). It is listed so the dependency is visible. Authority does not edit it | Discover |
| `backend/app/tasks/theme_assembly.py` | NEW: gather → decide → upsert edges + decisions → bump revision, under the existing lock. Reuses `container_corrections` helpers. Does **not** edit `container_assembly.py` | Yellow |
| `backend/app/utils/container_graph.py` | `CONTAINER_KINDS += 'theme'`, `EDGE_SOURCES += 'theme_rule'` | Yellow (shared vocab) |
| `backend/app/models/models.py` | `ContainerMemberDecision` model | **Red** (shared models; never parallel) |
| `backend/alembic/versions/<≤32 char id>.py` | `container_member_decisions` | **Migration-class, D45: Alex's word only** |
| `backend/app/utils/container_presentation.py` | `edition_for_slug` theme branch after NFL/MLB | Yellow: #9636 is CLOSED (v3 check); #9886 (open, MLB arm) is the live reader of this path, coordinator confirms clear |
| `backend/app/routes/containers.py` | `revision`/`cursor`/`limit`, counts block. Default behaviour unchanged | Yellow: #9886 (open, MLB published-reader arm) holder clears first, coordinator confirms |
| beat schedule in `backend/app/tasks/__init__.py` (`celery_app.conf.beat_schedule`, :6562) + `backend/tests/test_tasks_wiring.py` | one scheduled entry, disabled by flag until publication | Yellow |
| tests (new) | `test_theme_definitions_9935.py` (pure), `test_theme_assembly_9935.py`, `tests/integration/test_theme_collections_9935_pg.py` (real PG: two-collection membership, same-revision read, correction survives rerun) | Green |

---

## 8. Required proofs (the build's acceptance tests; real ids from #9925 evidence)

| # | Case | Expected |
|---|---|---|
| 1 | `13791997` "OpenAI IPO before 2027?" admitted to `ai`, plus a **test-only** second definition (`ipos`) | two edges, two decision rows, both `admitted`. Matcher receipt byte-identical before and after. `_story_key` still files it under IPOs in the feed (independent) |
| 2 | "Claude Monet …" (#8742 shape) vs `61461524` `KXCLAUDE-CLAUDE6` | Monet `excluded/lexical_false_friend`; Claude 6 `admitted_entity_signal` |
| 3 | `61082201` Sandoval vs **Oscar** Collazo (boxing), `63448382` M15 Baku **Oscar** Brown (tennis), an Oscar Piastri fixture (F1) | each `excluded/not_this_ceremony` (no ticker stem, no structural title) or `wrong_category`. They never enter via a substring fallback |
| 4 | `109566` `KXOSCARACTO-26` "Oscar for Best Actor?", `109303` `KXOSCARGUESTS-26` | `excluded/other_edition` (still `status='open'`, gotcha #33) |
| 5 | `6173044` `KXOSCARPIC-27` (res. 2027-12-31 placeholder) and `57313556` "Oscars 2027: Best Picture Winner" | both admitted, `title` class. The placeholder neither decides nor disqualifies the edition. Two members, not folded |
| 6 | `5165726` `KXOSCARNOMPIC-27`, `27988771` "Oscars 2027: Best Picture Nominations" | admitted, `advancement` (Nominations), separate from winners. The different (earlier) deadline doesn't change the edition |
| 7 | `115607` "…most Oscar nominations at the 99th Academy Awards" | admitted via the ordinal rule (`admitted_title_edition`, 99 → 2027) |
| 8 | Polymarket Oscars-shaped row whose only year signal is `resolution_date` | `withheld/edition_unknown`, counted under `withheld_count.edition_unknown`, absent from the page |
| 9 | `59164593` `KXOSCARVIS-27` titled "Best Makeup and Hairstyling" | admitted `title`, evidence flag `venue_title_conflict` |
| 10 | `oscars-2031`, `nfl-2026-week-04`, `ai-2026` | `edition_for_slug` → None for non-round-tripping slugs; no container → 404 `unavailable` |
| 11 | page 2 at stale revision; withdrawal mid-read | `revision_moved: true` + current page 1; counts equal across pages of one revision |
| 12 | human `withdraw` of `57313556`, rerun pass | edge stays deleted, decision `container_member_withdrawn`, revision bumped once |
| 13 | static guard | `routes/feed.py` imports neither `theme_assembly` nor any gather; no LLM call in either module |
| 14 | (v2) AI row with `settled_at` = now−3d; another with now−20d; a Kalshi row `status='open'` that reads settled through `market_reads_settled` with `settled_at` NULL; a `status='resolved'` row with `settled_at` NULL and a future `resolution_date` | admitted with result (evidence names the settled arm) · `excluded/resolved_beyond_retention` · `excluded/resolved_settle_time_unknown` · `excluded/resolved_settle_time_unknown`. Changing `resolution_date` alone changes none of the four outcomes (mutation: swap the clock to `resolution_date` → the test goes red) |
| 15 | (v2) "Will Gemini list XRP? (app)" stored `economics`; "Google Gemini 3 released before…"; "Gemini Pro tops LMArena…"; "Gemini 2.5 Flash …" | the first is `excluded/lexical_false_friend` even with a `KXGEMINI`-shaped stem; the other three are `admitted_entity_signal` |
| 16 | (v2) one admitted `ai` member whose `classify_market_quality` is `low_quality` | still admitted (decision + edge). `withheld_count.low_quality` = 1, `shown_count` = eligible − 1, card `collection_count` = page `shown_count` at the same revision. The gate called is the bundler's own helper (identity-asserted, not a copy) |
| 17 | (v2) an `assemble_awards_theme_bundles` bundle whose members are all `oscars-2027`; the same with one Grammys member; a swings bundle | ref `{slug: oscars-2027, name: "Oscars 2027"}` · no ref (`no_intended_collection`: members yield two ceremonies) · no ref (swings has no map entry) |
| 18 | (v3, repair A) OpenAI-IPO bundle whose members are all admitted to `ai` and to `ipos` (test-only definition): (i) map entry `story:ipos → ipos`, both published; (ii) bundle key with no map entry, both published; (iii) map entry `story:ipos → ipos`, `ipos` UNPUBLISHED, `ai` published and holding every member; (iv) no map entry, only `ai` published (single-other-published control); (v) map entry → `ipos` published at a revision other than the cached one | ref `ipos` · no ref (`no_intended_collection`) · **no ref** (`intended_collection_unavailable`; never `ai`) · no ref (`no_intended_collection`; no sole-survivor inference) · no ref (`intended_collection_unavailable`) |
| 19 | (v2; fold accepted v3) `6173044` + `57313556` both admitted | two decision rows and two edges, one shown question. `shown_count` counts 1 for the pair, and no caption string mentions folding |
| 20 | (v3, repair B) first finite pass, **no decision rows exist**: a Kalshi `KXOSCARNOMPIC-27`-shaped row `status='resolved'`, `settled_at` = now−20d; a Polymarket "Oscars 2027: …" row `status='resolved'`, `settled_at` NULL | both are gathered (arms K / P) and `admitted` with their result. Evidence carries no retention clause. A second pass with the clock advanced 30 more days re-decides both through the prior-decision arm and keeps both admitted: no `resolved_beyond_retention`, no revision bump. Mutation: apply the AI 14-day arm to the finite population → the Kalshi row is never gathered and the test goes red |
| 21 | (v3, repair B control) the same `settled_at` = now−20d shape on an `ai` row with no decision row; the same on an `ai` row that WAS admitted on an earlier pass | not gathered (not a candidate, no decision row written) · gathered through the prior-decision arm and re-decided `excluded/resolved_beyond_retention`, edge removed, revision bumped once |
| 22 | (v3, static) every `story_key` map entry resolves to exactly one registry collection; no two definitions claim the same key; `intended_collection` has no branch that reads publication state or edge membership | static test over the registry and the function source |

---

## 9. Dependencies (in order) and what this does NOT do

1. **Definition: ACCEPTED by root (v3)** — the definition, AI = A, finite Oscars 2027, the six amendments and the hydration fold. Discover defines the feed `collection_ref` consumer, the folded reader count and hub Back now, from this text. The one table is accepted as the proposed substrate only; its migration is item 3. Source work still waits on items 2 and 3 and on a dispatch (§10).
2. **Coordinator resolves claims** on `container_presentation.py`, `routes/containers.py` and `models.py`, after the current NFL/MLB publication handback. Theme branches are additive after the NFL/MLB branches.
3. **D45:** the migration merges only on Alex's word. It needs a YOUR-TURN entry via the coordinator. No lane sets a default.
4. **#9936** rolling refresh before "maintained" is advertised. **#9387** owns blending, and **lane1 P2 (#2693)** owns the cross-venue award fold in membership. The hydration-time fold (§3, accepted) is presentation only and doesn't wait on either. No page caption either way (notice 34).
5. **Publication:** human, via #9916's operator, behind the existing read flags.

Not done here: no census, no corpus probe, no Native or tool ownership, no publication, no member-id URL, no hand inventory, no synchronous LLM or GET-time gather, no production activation.

---

## 10. Producer source slice and the migration boundary (v3; definition only, nothing dispatched)

### 10.1 Slice P1: the smallest coherent producer source slice

**Two new files, no shared file, no schema, no writer, no route.**

| File | Contents |
|---|---|
| `backend/app/utils/theme_definitions.py` (NEW, pure) | `ThemeDefinition` + `REGISTRY` (`oscars-2027`, `ai`); `slug()` and `parse_theme_slug(slug)`, a round-trip parser that `edition_for_slug` will call in P2; `decide(market, *, now) -> Decision` for `oscars-edition@1` and `ai-subject@1` (§3, with AI-only retention); the closed reason enum; the evidence builder; `candidate_population(defn)`, which returns Core `select()` expressions per §4 arms and is built but **never executed** in P1; `intended_collection(bundle)` and the feed-key map (§5 step 1). Read-only imports: `event_awards.CEREMONIES` / `classify_market` / `edition_year`'s ticker arm, and `futures_liveness.market_reads_settled`. It does **not** import `discover_bundles`, because Discover's gate is a hydration (P2) dependency |
| `backend/tests/test_theme_definitions_9935.py` (NEW, pure) | §8 cases 2–9, 14, 15 and 20–22 at the `decide()` / population-shape level; case 10's round-trip half on `parse_theme_slug`; the step-1 halves of cases 17 and 18 on `intended_collection`. The publication and edge checks in step 2 belong to P2's integration test |

- **Collisions at `38601bf8f2`:** neither path exists on master. `gh pr list` shows no open PR touching either. No lane claims them. The two imported modules are read, never edited. Class: new utility + new test file = **Green** (Parallel Work Protocol).
- **What it changes for a reader on its own: nothing.** It is inert substrate that rides the queued #9935 ship (rider rule), and it says so in its PR. Under 49(d) it is not production data, migration, settlement, blending or ranking, so it goes to the desk on CI green with its guard tests.
- **Proposed gates (its own, CLAUDE.md):** `pytest tests/test_theme_definitions_9935.py tests/test_startup.py`, plus four mutation checks that must each turn a named case red: clock swapped to `resolution_date` → case 14; the AI 14-day arm applied to the finite population → case 20; a fallback to any published holder in `intended_collection` → case 18(iii)/(iv); Gemini adjacency dropped → case 15.
- **Starts only on dispatch.** This section defines the slice. It does not claim it.

### 10.2 Slice P2: writer + read (after P1, after claims, after the D45 word)

| File | Class | Current holder / collision at `38601bf8f2` |
|---|---|---|
| `backend/app/models/models.py` (`ContainerMemberDecision`) | **Red** | No container-area PR. Four stale open migration PRs touch models.py + alembic: #2262, #4037, #4570, #4912. Never run in parallel with another models/migration session; the coordinator sequences |
| `backend/alembic/versions/container_member_decisions.py` | **D45** | §10.3 |
| `backend/app/utils/container_graph.py` (`CONTAINER_KINDS += theme`, `EDGE_SOURCES += theme_rule`) | Yellow | no open PR |
| `backend/app/tasks/theme_assembly.py` (NEW) | Yellow | absent on master. Not in `HEAVY_TASKS`, same as `container_assembly`. If P2 routes it to heavy, notice 48's heavy-release line applies |
| `backend/app/tasks/__init__.py` beat entry (flag-off) + `backend/tests/test_tasks_wiring.py` allowlist | Yellow (huge shared file) | stale open PRs #2262, #2466, #2487, #3468, #3483 touch `tasks/__init__.py` |
| `backend/app/utils/container_presentation.py` (`edition_for_slug` → `parse_theme_slug`, after NFL/MLB) | Yellow | #9636 CLOSED. No open PR |
| `backend/app/routes/containers.py` (`revision`/`cursor`/`limit`, counts, hydration fold + gate) | Yellow | no open PR. #9886 (open, MLB published-reader arm) reads this path, so its holder confirms clear |
| tests: `test_theme_assembly_9935.py`, `tests/integration/test_theme_collections_9935_pg.py` | Green | new |

- **Discover dependency (hard, ordered):** Discover lifts `_theme_member_eligible` (discover_bundles.py:720) to a public helper **in its own file** before P2's hydration read lands. P2 imports it and does not copy it, and case 16 asserts identity (`gate is discover_bundles.<public name>`, name chosen by Discover). `fold_same_question_cards` (:1473) and `is_same_question` (cross_source_matching.py:371) are already public. Discover owns the map entries' review (§5) and the `collection_ref` / reader count / Back consumer. That consumer's step-2 check reads P2's published counts.
- **Other dependencies:** #9916's human operator for publication. #9936 before "maintained" is advertised. Lane1 P2 (#2693) / #9387 for any membership-level fold (none proposed).
- Under 49(d), P2 writes production membership data, so it is the **reviewed** class (bus) in addition to D45.

### 10.3 The migration / source / rollback packet (prepared for the coordinator → YOUR-TURN; not an ask yet)

- **Migration (Alex's word only, D45/notice 47b):** one file, revision id `container_member_decisions` (26 chars ≤ 32), `down_revision` = the head at merge time (`container_corrections` at `38601bf8f2`). `upgrade`: create the §2 table with its UNIQUE, its `(child_type, child_id)` index and its CHECK. The table is new and empty, so a plain `CREATE INDEX` is instant (gotcha #31 is about large tables; never `CONCURRENTLY` in Alembic). `downgrade`: `DROP TABLE container_member_decisions`. No existing table is altered.
- **Source that needs it:** P2 only. It composes with the migration as one co-arriving unit (model + migration + writer), with the writer behind a production flag that is **unset** (proposed `THEME_ASSEMBLY_ENABLED`). Flipping it is attended config (notice 39 rule), and it is not part of the merge word.
- **Rollback, in reader order:** (1) **Reader:** withdraw the collection with #9916's operator. `read_published` → `unavailable`, §5 step 2 fails, and every card loses its ref on the next feed build. (2) **Writer:** unset the flag, so nothing more is written. (3) **Data (D51: backup first, one-command restore):** copy then delete `event_edges WHERE source='theme_rule'` under `lock_container_chain` with a revision bump. Decision rows are inert without edges. (4) **Schema:** `alembic downgrade -1` drops the table. Steps 1–3 never need step 4.
- **Exact approval boundary.** Alex's word: merging the migration-class sha ("merge NNNN"). Attended config: setting the writer flag in production. Human operator (#9916): publication and withdrawal. Not Alex's: P1, and P2's non-migration code under the normal reviewed path. No lane sets a default for any of these (notice 36). The coordinator writes the YOUR-TURN entry when P2 is composed. This packet is its source.
