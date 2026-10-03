# #9935 — Discover CONSUMER slice definition: collection_ref · folded reader count · hub Back

**PILLARS** MATCHING · DISCOVER · TRUTH.
**SHIP** An AI or Oscars preview on Discover opens the same complete collection at a stable URL, says how many questions it holds, and Back returns the reader to where they were.

**Status: DEFINITION ONLY.** No source edit, claim, test run, production call, publication or dispatch. #9935 stays Conditional / Blocked / Defined / not Ready. Root has already accepted AI = A (continuing), finite Oscars 2027, Discover's six amendments and the hydration fold, and nothing here reopens them. D45 (`container_member_decisions`) stays Alex's word only. #9916 stays human publication and #9936 stays the maintained-membership boundary.

Read at `origin/master` `38601bf8f2` (discover worktree HEAD, 2026-10-03 01:2xZ). It answers Authority contract v2 (#9935 comment 5963676371) plus Sol's 01:19Z delta review (repairs A and B). Line numbers below are at that sha.

---

## 0. What the consumer stands on today (read, not measured)

| Fact at 38601bf8f2 | Where | Consequence for this slice |
|---|---|---|
| There are exactly three `kind: "theme"` emitters: story-key (`grouped_by: story_key`), awards (`grouped_by: group_id`) and swings (`story_key: "swings"`). `assemble_geopolitics_theme_bundles` is an alias of the story bundler | `discover_bundles.py:1104`, `:1937`, `:2073`, `:1739`; called `feed.py:2544-2549` | The ref rule binds all three. Swings fails on its own (§1.3) |
| The feed's IPO key is **`story:ipo_markets`**, and the `"ipo"` arm runs **before** the AI arm in the cascade. `"OpenAI IPO before 2027?"` is therefore keyed IPOs | `feed_market_quality.py:2862`, AI arm `:2893-2897` | The contract's `story:ipos` (§5, §8 case 18) is not a real key. Map entries must be checked against the vocabulary (§2) |
| `story:major_entertainment_events` (header "Who wins awards season?") spans Met Gala, Oscars, Grammys and Emmys | `feed_market_quality.py:2899`, `discover_bundles.py:63/273` (`AUTHORED_STORY_TITLES` / authored question) | It gets **no map entry** (§2) |
| `_theme_member_eligible(item)` reads the feed's precomputed `item["_quality_class"]` and the card flag. It is **not** a function of stored fields as written | `discover_bundles.py:720-734`; `_quality_class` set at `feed.py:12106` from `classify_market_quality(name, llm_sport_category, outcome names, external_id, status)` at `feed.py:11860` | The lift has to recompute from the same five stored inputs (§3.1) |
| The feed **drops `quality_class == "suppress"` before bundling** (`continue`, `feed.py:11867`), so the bundler's gate never sees one | `feed.py:11867` | The hub has to withhold `suppress` too, or the page shows rows the feed refuses (§3.1, amendment D-7) |
| The bundle fold and the standalone fold both go through `is_same_question` after `_comparison_title`. The fold requires different venues. The survivor is the first in input order | `discover_bundles.py:1409-1470`, `:1473` | The hub fold calls these functions. The survivor choice is the hub's own order, so the agreement test cannot be "preview ⊆ shown" (§3.3) |
| The card footer reads "All N questions", where N is `items.length` (the preview, ≤8), and it expands inline | `ThemeBundleCard.tsx:97` | The ship turns this into a link reading the collection's count (§1.4) |
| The NFL/MLB collection path reads publication **at GET** inside a 250 ms budget, and on failure rolls back and keeps the ordinary cards | `feed_collections.py:89-156`, call site `feed.py:5383` | The theme ref uses the same budget and failure behaviour (§1.2) |
| The feed page cache (#10003) is keyed on `id:membership_revision` of published root hubs, **filtered by `DISCOVERABLE_SLUG_PATTERN` (nfl/mlb only)** | `feed_collections.py:27-34`, `container_discovery.py:87` | A cached page would keep a withdrawn `ai` link. The fingerprint has to cover theme slugs (§1.5) |
| `parseCollection` **throws** for a published hub whose edition it can't label. `editionLabel` knows only NFL/MLB. Section titles map `title` to "Championship". The partial note fires on **any** `withheld_count > 0` or on `members.length !== member_count` | `frontend/lib/collections.ts:70-120` | A published `ai` or `oscars-2027` hub would read "isn't available", Oscars winners would sit under "Championship", and every low-quality or folded row would print "Some games or questions aren't available right now" (§3.4) |
| Back from a card: any **client transition** into Discover restores the #7417 snapshot and scroll mark (`shouldRestoreOnMount`), and `/` re-exports the Discover page | `feedRestore.ts:238-258`, `app/page.tsx` | The feed→hub→Back path already works. The hub's in-page "Back to Discover" is a `<Link href="/discover">` **push**, so the reader's history becomes feed→hub→feed (§4) |
| The hub's reading context (`collection-reading:{slug}`) restores a scroll offset against **one unpaginated** read | `CollectionHub.tsx:11/62-76` | Once theme pagination arrives, this is the #7417 clamp defect again unless the pages come back before the scroll does (§4.3) |

---

## 1. `collection_ref` — the feed half

### 1.1 Shape (additive, optional on any `kind: "theme"` bundle's `data`)
```
collection_ref: { slug, name, revision, collection_count }
```
- `name` = `containers.name` ("Oscars 2027"). It is never the bundle header or the chip label.
- `collection_count` = the snapshot's `shown_count` at `revision` (§3.2).
- If the field is absent, the card behaves exactly as it does today. Native ignores the key (Decodable drops unknown keys), so this slice owes no native change.

### 1.2 Where it is computed
New module **`backend/app/utils/feed_theme_refs.py`** (Discover, Green). It has one async entry, `add_theme_collection_refs(db, items, *, budget_seconds)`, called **on the build path beside `add_feed_collections` (`feed.py:5383`)** under the same `_collections_enabled` gate (the existing read flags; publication stays behind them per contract §9.5).
- It makes **one bounded statement** over the preview ids of every theme bundle in the deck (at most ~10 bundles × 8 members), using `ix_event_edge_child`. It reads the current `theme_rule` `contains` edges, the owning containers (`slug`, `name`, `publication_state`, `membership_revision`, any state) and the producer snapshot for those containers (§3.2).
- Budget is `min(remaining, 0.25 s)`. On timeout or error it calls `db.rollback()` and returns the deck unchanged, with no ref. This copies `feed_collections.py:113-124`.
- No gather, no `decide()`, no hydration, no LLM. Static guard: `feed_theme_refs` imports neither `theme_assembly` nor any `gather_sql` (this extends contract case 13).
- It decides with a **pure core**, `resolve_theme_ref(bundle, rows, feed_key_map) -> (ref | None, reason)`, so every case in §5 is a unit test.

### 1.3 Target resolution. Publication can remove a link but never redirect it (incorporates repair A)
For each theme bundle, with P = its `member_ids`:
1. **Feed key.** Use `story_key` if present (story bundles, plus `"swings"`), otherwise `group_id` (awards).
2. **Candidates C** = theme containers that currently admit **every** id in P through a `theme_rule` edge, **in any publication state**. Publication is not used for resolution.
3. **Intended target.**
   - If the feed key **has a map entry**, the intended target is the unique c ∈ C with `subject(c) == mapped subject`, where `subject` comes from `edition_for_slug(c.slug)`, the round-trip parser.
     - Zero matches gives no ref (`mapped_target_absent`).
     - More than one match gives no ref (`mapped_target_ambiguous`).
     - **The map never falls back to another member of C.**
   - If the key has **no map entry**:
     - |C| = 1: that container is the intended target.
     - |C| = 0: no ref (`preview_spans_collections`).
     - |C| > 1: no ref (`no_map_entry_ambiguous`).
4. **Checks on the intended target, after resolution.** Every one of these must hold or there is no ref, with the named reason:
   - it is `published` (`target_unpublished`);
   - a snapshot exists whose `revision` equals the live `membership_revision` (`snapshot_stale`);
   - every id in P is in the snapshot's raw admitted set, shown ∪ folded (`preview_member_not_admitted`);
   - no id in P is in the snapshot's withheld set (`preview_member_withheld`).
5. Otherwise emit `collection_ref`. The reason for any missing ref goes into `debug_bundles.collection_ref_reason` for ops. It never reaches reader text (notice 34).

Because step 2 includes unpublished containers, step 3 for a no-map key fails **closed** whenever a second subject exists in any state. An OpenAI-IPO pack admitted to published `ai` and unpublished `ipos` gets no ref. It does not get `ai`.

**Awards feed keys.** An awards bundle's `group_id` (`polymarket:{event_id}`) can't be listed in a map: a list of event ids would be a member list in disguise, which the contract forbids. So awards bundles carry **no map entry** and resolve by rule 3's no-map arm. The only theme containers an Oscars cluster can be admitted to are single `oscars-YYYY` editions, and a market can't pass two editions' strict edition clause, so |C| ≤ 1 by construction. If a later Awards-Season parent ever admits the same members, rule 3 returns `no_map_entry_ambiguous`. That is a visible state, never a guess.

### 1.4 The card (frontend)
- New **`frontend/lib/discover/themeCollectionRef.ts`**: `admitThemeRef(data)`. It accepts the ref only if:
  - `safeCollectionSlug(slug)` passes;
  - `revision` is a positive integer;
  - `collection_count` is an integer ≥ 1;
  - `name` is non-empty after trim.

  Anything else makes the ref invisible, and the card is unchanged. The href is built only through `collectionPath(slug)`.
- **`ThemeBundleCard.tsx`**: with an admitted ref, the collapsed footer becomes a client-side `<Link href="/collections/{slug}">` reading **"See all {collection_count} questions"**. The header chevron's inline expand stays as it is. Without a ref, today's footer is byte-identical. There is no caption about folding or completeness (notice 34). The analytics event `theme_bundle_collection_open` carries `{story_key|group_id, slug, revision, collection_count, position}` through the existing `trackEvent`, after checking the `lib/analytics/sanitize.ts` allowlist.
- **`DiscoverCard.tsx:195`**: pass `collectionRef` through. **`lib/types.ts`**: add `FeedBundleData.collection_ref?`.

### 1.5 Feed cache fingerprint
In **`feed_collections.py`** (Discover-authored), `_FINGERPRINT_SQL` gains `OR slug = ANY(:theme_slugs)`. `theme_slugs` is the registry's slug set from `theme_definitions.py`, which is pure and imported. **`container_discovery.DISCOVERABLE_SLUG_PATTERN` is NOT edited**: PR #9721 is open on that file, and widening it would also change NFL/MLB discovery. Two controls:
- with no theme container published, the fingerprint is byte-identical to today's;
- publishing or withdrawing `ai`, or bumping its revision, changes the fingerprint.

---

## 2. Feed-key → subject map: Discover's review of the entries

These entries are for `theme_definitions.py`. Authority owns the file and Discover owns the keys. Each entry must be a member of the real key vocabulary: a test asserts every map key ∈ `discover_bundles.AUTHORED_STORY_TITLES` keys ∪ `{"swings"}`, so a misspelled key like `story:ipos` fails CI instead of silently never matching.

| Feed key | Entry | Why |
|---|---|---|
| `story:ai` | → `ai` | The story key is lexical and includes bare `gemini`. Any bundle that seats a Gemini-exchange row is refused by step 4 (`preview_member_not_admitted`) and fails closed. That's correct |
| `story:ipo_markets` | **no entry in the first ship**. Test-only: `story:ipo_markets → ipos` | `ipos` is not a first-ship subject. Case 18 must use the **real** key |
| `story:major_entertainment_events` | **no entry** | The key names a season of four ceremonies. An all-Oscars pack still resolves through the no-map single-candidate arm, and the link says "Oscars 2027" |
| `story:spacex_ipo`, `story:music_charts`, other keys | no entry | No subject |
| `swings` | **no entry** | It groups by price movement across subjects |
| awards `group_id` | **no entry** (§1.3) | An event-id list would be a member list |

---

## 3. Folded reader count: one shown set per revision, read by both card and page

### 3.1 The lifted gate (Discover's file, `discover_bundles.py`)
- New public helper **`theme_member_withhold_reason(*, name, llm_sport_category, outcome_names, external_id, status, discover_card) -> str | None`**. It calls `classify_market_quality` with **the same five arguments `feed.py:11860` passes** and returns:
  - `"suppressed"` when `quality_class == "suppress"`;
  - `"low_quality"` when `quality_class == "low_quality"`;
  - `"public_source_disagreement"` when the card flag is set;
  - `None` otherwise.
- `_theme_member_eligible(item)` becomes a thin wrapper that keeps reading the item's carried `_quality_class` (so bundler output stays byte-identical, and existing bundle tests are untouched) and the card flag.
- A parity test pins the wrapper and the helper to the same verdict for the same row.
- Authority's hydration calls the helper by identity (contract case 16's identity assertion now names `theme_member_withhold_reason`).

**Amendment D-7 (Discover relevance call, for Authority's enum): add hydration withhold `suppressed`.** The feed never deals a `suppress` row, whether that's a suppressed ticker prefix, a narrow ladder rung or daily-direction filler. If the hub showed one, the hub would be the only surface printing what Discover rules out. Membership is unchanged: it stays an admitted member with an edge and a decision row, and it is counted in `withheld_by_reason.suppressed`. It never appears in page prose.

### 3.2 The snapshot: what both readers need (an interface request to Authority; storage is Authority's choice inside existing infrastructure, no new table)
One producer function builds, per published theme container and revision:
```
{container_id, slug, name, revision, inventory_complete,
 shown_ids: [...]            # page order = contract cursor order (class order, sort key, id)
 folded: {survivor_id: [folded_id, ...]},
 withheld: {reason: [ids]},  # row_missing · unserializable · suppressed · low_quality · public_source_disagreement
 shown_count, eligible_count}
```
- **Same bytes for card and page.** The feed reads `shown_count` and the raw sets. The hub route paginates `shown_ids` and hydrates live prices per page. Neither reader re-derives the shown set, so `card collection_count == page shown_count` holds by construction instead of by coincidence.
- **The revision moves whenever the shown set moves** (request R-1 to Authority). It moves on membership changes as today, and also when a pass finds the shown set or `shown_count` changed (for example a member turning `low_quality`). This is the existing principle stated at `feed_collections.py:21-24`: "the revision moves … whenever anything its reader would see changes". The snapshot is then immutable per revision, and the feed fingerprint (§1.5) stays sound.
- A human correction bumps the revision under the lock before a new snapshot exists. Both readers treat a snapshot at a different revision as absent: the feed drops the ref, and the hub route uses its existing build/503 "building" path (#9984). Request R-2: the correction path triggers a snapshot rebuild, so the link's absence lasts seconds, not one producer cadence.

### 3.3 The fold
- It runs **once over the whole post-withhold shown set, before pagination**. If it ran per page, a pair split across pages would fold on neither.
- It calls `_dedupe_same_question_members` and therefore `is_same_question` and `_comparison_title` **by identity, never reimplemented**, over items built in the feed's `{type:"futures", data: card}` shape. The input is in page order, so the survivor is the better-placed row on the page.
- **Agreement assertion, restated.** At equal revision:
  - card `collection_count == page shown_count`;
  - **every preview id ∈ shown_ids ∪ folded values**.

  The feed's fold kept the better **feed-ranked** venue, and the page's fold keeps the better **page-ordered** one, so "preview ⊆ shown" would be a false FAIL whenever the two pick different venues of one question. That is one question with one blended number either way.
- The survivor carries `data-folded-ids` (notice 34: numbers go into data attributes so probes can read them). No caption.

### 3.4 The hub page (Discover's files, `lib/collections.ts` and `CollectionHub.tsx`)
- **Editions.** `editionLabel` learns `theme_edition` (`slug === `${subject}-${edition}``) and `theme_continuing` (`slug === subject`), using the same client round-trip rule as NFL/MLB. Either one is **recognized with no edition line**, because the title (`containers.name`) already says "Oscars 2027" or "AI". `parseCollection`'s `!base.edition` throw becomes "edition recognized".
- **Sections.**
  - `theme_edition` / `oscars`: `title` → **"Winners"**, `advancement` → **"Nominations"**, `side_question` → **"More questions"**.
  - `theme_continuing` / `ai`: two reader sections, **"Open questions"** and then **"Decided recently"** (settled within retention, showing their results; settled means settled). The split is by the served settled state, never by `resolution_date` (the Dec-31 placeholder).
  - **Gap, request R-3 to Authority:** `ai-subject@1` assigns no edge class, but the `contains-has-class` CHECK forces one. Proposal: every `ai` admission takes `side_question`, and Discover's page does the open/decided split.
- **Partial note.** It is drawn only for `inventory_complete === false`, for hydration failures (`row_missing` / `unserializable` > 0), or for rendered rows ≠ `shown_count`. `suppressed`, `low_quality`, `public_source_disagreement`, folded partners and `edition_unknown` never produce page prose. The existing one-line note text is unchanged.
- **Pagination.** An explicit **"Show more questions"** button fetches `?revision=N&cursor=…&limit=50` and stays until the rendered count equals `shown_count`. A button, not an auto-pager, keeps the hub out of the sentinel loop #7417 documents. On `revision_moved: true` the hub replaces itself with page 1 of the new revision and drops its reading context.

---

## 4. Hub Back: what has to be built

1. **Feed → hub → browser Back.** No build. "See all" is a client `<Link>`, and #7417 restores the deck and scroll mark on every client transition. It is proved by a check, not by new code.
2. **The hub's in-page Back.**
   - When "See all" is tapped, the card writes a one-shot `sessionStorage` marker `{slug, at}`.
   - On mount, the hub consumes it if it is under 10 s old and for the same slug, and stamps its own history entry: `history.replaceState({...history.state, blFromDiscover: slug})`. A later Back or Forward to that entry keeps the flag, and a fresh navigation to the URL doesn't have it.
   - If the flag is present, "Back to Discover" calls `router.back()`, so history stays feed→hub and the browser's own Back agrees with the button. Otherwise it is a `<Link href="/">`.
   - Build risk to prove in jest plus a 390 px walk: Next 14 must preserve merged `history.state` across its own navigations. If it doesn't, the fallback is the plain Link, which is today's behaviour.
3. **Hub → member → Back on a paginated hub.**
   - The reading context grows to `{slug, revision, loadedCursor, memberKey, offset}`.
   - On restore at the **same** revision, the hub re-fetches pages up to `loadedCursor` **before** scrolling, and scrolls only once the member's DOM node exists. This is the #7417 lesson: the items come back first.
   - At a different revision, or after `revision_moved`, the context is dropped and the hub lands at the top. It never clamps against a short document.
4. **The Oscars hub ↔ `/event/awards/oscars` cross-link (contract §6.4) is NOT in this slice.** UX owns the ceremony page, the two pages must first be shown to show the same edition, and it rides a later UX ship.

---

## 5. Proposed checks (the build's acceptance; not run here)

**Backend, `tests/test_feed_theme_refs_9935.py` (pure core + fake rows):**

| # | Case | Expected |
|---|---|---|
| R1 | An awards bundle whose members are all admitted to published `oscars-2027` at the snapshot revision | ref `{slug:"oscars-2027", name:"Oscars 2027", revision, collection_count = shown_count}` |
| R2 | The same bundle with one Grammys member | no ref, `preview_spans_collections` |
| R3 | A swings bundle | no ref |
| R4a | An OpenAI-IPO `story:ipo_markets` pack admitted to `ai` and `ipos` (test-only map `story:ipo_markets → ipos`), with `ipos` published | ref `ipos` |
| R4b | The same pack with no map entry | no ref, `no_map_entry_ambiguous` |
| **R4c** | **The map points at `ipos`, `ipos` is UNPUBLISHED, and `ai` is published and holds every member** | **NO REF, `target_unpublished`. The mapped-unpublished control; it must not fall back to `ai`** |
| R4d | The map points at `ipos`, no `ipos` container admits the pack, and `ai` admits every member | no ref, `mapped_target_absent` |
| R4e | No map entry; only `ai` admits every member, and `ai` is published | ref `ai` (the single-candidate control) |
| R5 | A `story:major_entertainment_events` pack whose members are all `oscars-2027` | ref named "Oscars 2027", not "Awards Season" |
| R6 | A human withdraw bumps the revision to N+1 while the snapshot is at N | no ref, `snapshot_stale` |
| R7 | The read raises or times out | deck unchanged, no ref, `rollback` called |
| R8 | Static guard | no `theme_assembly`, gather or LLM import |
| R9 | Snapshot with one `low_quality`, one `suppressed` and one folded pair | `collection_count = eligible − 3`. Gate and fold are identity-asserted |
| R10 | Fingerprint | byte-identical with no theme hub published; changes on publish, withdraw or revision bump of `ai` |
| R11 | Map vocabulary | every map key ∈ `AUTHORED_STORY_TITLES` ∪ {"swings"} |

**Mutations that must go red:**
- step 2 restricted to published candidates → R4c returns `ai`;
- the name taken from the bundle title → R1/R5;
- the fold run per page → the split-pair case;
- the gate copied instead of called → R9's identity assertion.

**Gate parity, `tests/test_discover_bundles_*`:** the wrapper and `theme_member_withhold_reason` agree on the same row, and existing bundle outputs are byte-identical.

**Frontend, jest (`npx jest --testPathPatterns=…`):**

| # | Case |
|---|---|
| F1 | With a ref the footer is a Link to `/collections/{slug}` reading "See all N questions". Without one, today's footer is byte-identical |
| F2 | `admitThemeRef` refuses bad slug, revision, count or name |
| F3 | Theme editions round-trip; `oscars-2031` carrying edition 2027 is refused; no edition line; Oscars and AI section labels |
| F4 | No partial note for suppressed, low_quality, folded or edition_unknown; a note for row_missing |
| F5 | "Show more" stays at the same revision; `revision_moved` resets |
| F6 | In-page Back with the flag calls `router.back`; without it, a Link to `/`; restore re-fetches through `loadedCursor` before scrolling |

**LOOK (D48), owed after the build:** a 390 px headless walk of card → hub → member → Back → Back, screenshots read. It is only payable once a theme hub is **published** (#9916, human), so it is the conditional after-check, not a build gate.

---

## 6. Exact files and current collisions (at 38601bf8f2)

| File | Owner | Change | Collision now |
|---|---|---|---|
| `backend/app/utils/feed_theme_refs.py` | Discover, NEW | §1.2-1.3 | none |
| `backend/app/utils/discover_bundles.py` | Discover | §3.1 helper + wrapper | none open |
| `backend/app/utils/feed_collections.py` | Discover-authored (#9905/#10003) | §1.5 fingerprint term | none open |
| `backend/app/routes/feed.py` | shared route | one call beside `:5383` | open PRs touching it are #2353/#2546/#2617/#3008, all stale (opened 2026-08-30 to 09-04). Coordinator confirms |
| `frontend/lib/types.ts`, `frontend/components/DiscoverCard.tsx` | shared | additive optional field, one prop | those same stale PRs only |
| `frontend/lib/discover/themeCollectionRef.ts` | Discover, NEW | §1.4 | none |
| `frontend/components/discover/ThemeBundleCard.tsx` | Discover | §1.4 | none |
| `frontend/lib/collections.ts`, `frontend/components/collections/CollectionHub.tsx` | Discover (#9886/#9982/#10146 author) | §3.4, §4 | none open |
| tests above | Discover, NEW | §5 | none |
| **Not Discover's:** `theme_definitions.py` (map, slugs, `edition_for_slug` theme branch), `routes/containers.py` (revision/cursor/counts, snapshot serve), `container_presentation.py`, `theme_assembly.py`, `models.py`, alembic | Authority / current #9636/#9886 holders | — | `container_discovery.py` has open PR #9721 (codex). This slice does not touch it |

**Sequencing.** The frontend half is inert without the payload field and could land on its own. `feed_theme_refs.py` and the fingerprint import the registry from `theme_definitions.py`, so the backend half lands **with or after** Authority's pure module and the route's revision/cursor/counts. No ref can appear until a theme container is assembled (`theme_assembly`, which needs D45's table) and **published by a human** (#9916). Until then the whole slice is a no-op in production.

## 7. Requests and amendments returned to Authority's corrected contract
- **D-7:** add hydration withhold `suppressed` (§3.1).
- **R-1:** the revision moves when the shown set moves (§3.2).
- **R-2:** a correction triggers a snapshot rebuild (§3.2).
- **R-3:** `ai-subject@1` assigns an edge class; proposal `side_question` (§3.4).
- **R-4:** contract §5 / case 18 adopt §1.3's resolution order (candidates in any state, map before checks, no fallback) and the **real** key `story:ipo_markets`. Case 18 is R4a–R4e.
- **R-5:** contract §5's agreement assertion becomes "preview ids ⊆ shown ∪ folded" (§3.3).
- **R-6 (dependency, not a ruling):** an Oscars awards preview is a Polymarket `group_id` cluster: a parent "Oscars 2027: Best Picture Winner" plus children. The ref needs **every child admitted**. If a child title lacks the structural "Oscars 2027"/"Academy Awards" form, clause 1 excludes it and the main Oscars preview source can never carry a ref. Authority's corrected definition should state how a `group_id` child of an admitted Polymarket parent is decided (the venue's own structure first, notice 40 rule 1) and carry a parent+children fixture. This consumer slice makes no assumption either way: it fails closed (`preview_member_not_admitted`).
