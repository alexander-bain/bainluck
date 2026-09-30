# #9925: theme collection page, first design direction (Awards Season, with AI as the second theme)

**Pillars:** DISCOVER · FORMATTING (membership accuracy draws on MATCHING and TRUTH)
**Ship:** a reader taps a whole Discover theme, sees its full collection that maintains itself, opens a question, and Back returns them to the same place in the feed.

**Status: a local design prototype. It is not deployed and it is not an acceptance.** No frontend, backend or iOS source was changed. No production writes were made. Production was read-only: one served `/api/feed` and bounded `db-query` reads, 2026-09-30 20:39–20:55Z (1:39–1:55 PM PT).

| Open | What |
|---|---|
| `prototype.html` | the prototype, ten phone frames (390px), built from `evidence/` by `build_prototype.py` |
| `shots/proto-frame-NN.png` | each frame at 390×844, and `proto-gallery-overview.png` |
| `shots/00-BEFORE-*.png` | the production Discover cards today (Awards Season, AI) |
| `shots/04-*.png`, `shots/05-*.png` | production member page `/futures/6173044` and the existing ceremony page `/event/awards/oscars` |
| `evidence/` | served bundles, the full candidate inventories (216 awards, 375 AI), the queries, and the scripts that apply the system's own membership predicates |

## The flow (frames ①–⑥)

1. **Discover card:** unchanged three-row preview. The header gets a `›` and opens the page. "All 6 questions" (an inline expand of the feed sample) becomes **"See all 133 questions ›"**. That is the count for the whole collection, never the feed sample.
2. **Page top:** in order, `‹ Discover`, then eyebrow `Collection · 2026–27 season`, title, the group's own question (`Who wins awards season?`, from `AUTHORED_STORY_QUESTIONS`), one plain line saying what is included, the question count with the price time, and ceremony chips (earned: 4 sections ≥ 3, entity-page grammar §4). **No combined percentage.**
3. **Headliners:** each ceremony's marquee category, which is the one `event_awards.py` already uses as the ceremony-page hero: Oscars Best Picture (The Odyssey 48% · The Black Ball 27% · Dune: Part Three 10%) and Grammys Album of the Year (Olivia Rodrigo 45% · Olivia Dean 21% · Rosalía 14%).
4. **One section per ceremony:** each section links to the **existing ceremony page** ("Ceremony page ›" → `/event/awards/oscars`, `/event/awards/grammys`). Inside it:
   - **Winners** first, showing the 5 most traded, with "Show all N".
   - **Nominations** folded. Each row reads "chance of a nomination" because several nominees can each be likely, so this is not a race.
   - **"Not traded yet (N)"** folded (the D102 pattern).
5. **Tap a question:** the existing member page opens. The one proposed change is that its back link reads "‹ Back to Awards Season" when the reader came from the collection.
6. **Back:** the page returns to the same row, via CollectionHub's existing `collection-reading:{slug}` context. **Back again:** Discover returns to the same card, via the feed snapshot and scroll mark (#7417) that `DiscoverCollectionCard` already relies on.

**⑦ Sparse inside a big theme:** 12 of 36 Grammy winner questions and 1 of 40 Daytime Emmy questions have any 24h volume. Many untraded Kalshi rows sit at an identical 29.5% leader. The page shows only what is traded and folds the rest. **⑧ States:**
- sparse theme (the real Oil bundle, 2 questions): no chips, headers or count
- one member can't load: existing copy, and its siblings still render
- settled question: moves to "Decided" with its result (FIXTURE shape)
- withdrawn and load-failed: existing CollectionHub states

**⑨–⑩ AI, the second theme:** AI has no ceremony structure. Sections therefore come from the questions' own decide-by dates (October 33 · by New Year 90 · later 27), and "Most followed" comes from feed rank. It is the same template, and nothing new had to be classified.

## Membership: the system's own predicates, applied to the full inventory

`evidence/classify.py` runs `_story_key` → the entertainment gate (`_is_entertainment`, from the awards bundler) → `_member_season` edition filter → `_member_answers_story_question` → `_dedupe_same_question_members`. `evidence/sections.py` then collapses rows by venue `group_id`, as `_dedupe_futures_by_group_id` does.

| | Awards Season (edition 2027) | AI (rolling) |
|---|---|---|
| name-regex candidates, open | 216 | 375 |
| pass the existing gates | 188 | 348 |
| after `group_id` collapse | 153 | 150 |
| after the **proposed** cross-venue award fold (P2) | 133 (attendance row excluded) | n/a |
| in today's feed bundle | 6 | 5 |

**Near-misses the page must refuse** (ids are production `futures_markets`):
- **A person named Oscar.** `_story_key` returns `story:major_entertainment_events` for `61082201` "Ricardo Rafael Sandoval vs Oscar Collazo" (boxing) and `63448382/63448383` "M15 Baku: Oscar Brown vs …" (tennis). I checked this locally against `_story_key` itself. The awards bundler's `_is_entertainment` gate refuses them. **The story-theme bundler has no such gate**, so the same key can seat them under "Who wins awards season?" whenever they are in the feed at the same time.
- **Last season's ceremony, still `status='open'`.** 24 Kalshi 2026 Oscar rows (e.g. `109566` "Oscar for Best Actor?", Jesse Plemons 50%) plus 1 Polymarket row (gotcha #33). The edition filter must drop them. `_members_span_multiple_seasons` only refuses a whole bundle, so it would not.
- **Attendance.** `109587` "Who will attend The Met Gala?" (2026 season) and `109303` "Who will attend the Oscars?" do not answer "who wins". They stay on the ceremony page.
- **Routed to another theme by cascade order.** 23 OpenAI-IPO rows (e.g. `13791997`) go to IPOs, and `115378` goes to SpaceX IPO. That is correct: one theme per market.
- **Venue mistitle, same venue.** Kalshi `KXOSCARVIS-27` is titled "Best Makeup and Hairstyling" on Kalshi's own API, but its nominees are visual-effects films (Avengers: Doomsday, Dune: Part Three, Godzilla Minus Zero). `KXOSCARMAH-27` has the same title. The page would print two "Best Makeup and Hairstyling" rows (28% and 18%). This is an upstream gap, and same-venue folding is not ours to do. It needs a decision.

## Prerequisites the prototype exposed (these are not built)

- **P1 · durable identity:** `_theme_bundle_id` embeds the current member ids, so it cannot be a shared URL. Proposed identity: `{story slug}-{edition}` (e.g. `awards-season-2027`), or `ai` for rolling themes. The bundle carries `collection_href` plus a cached `collection_count` read from the published revision. **Never fetch the inventory inside `GET /api/feed`.**
- **P2 · cross-venue award fold (MATCHING):** `is_same_question` refuses all 18 Kalshi↔Polymarket pairs of one award category, e.g. "Oscar Winner: Best Picture" vs "Oscars 2027: Best Picture Winner". Without a fold, the page shows Best Picture twice (47.5% / 46.5%). The ticker already encodes ceremony + category + edition (`event_awards.py` docstring), which is the natural key. Matching symptoms go to lane1 under #2693 (D35). ◆ rows in the prototype depend on this fold.
- **P3 · the entertainment gate** for the awards story key (the "Oscar" names above). This is Discover's to build and is a one-clause change, with the near-miss ids as guard fixtures.
- **P4 · edition filter per member**, not only a whole-bundle refusal.
- **P5 · display names:** the page hydrates through the served serializers, so it gets `clean_market_display_name` (#3513). Frame ⑩ deliberately shows the raw stored titles ("released on...?", "hit __") to make the point.
- **P6 · "Not traded yet" and "Awaiting result":** use 24h volume for the first. For the second, use a passed deadline, until grading lands (settled means settled).
- **Honesty note on sources:** today's served `sources` for `6173044` reads `[kalshi, polymarket]` because it is keyed on the `canonical_market_key` bucket (`feed.py` `_canonical_source_names_cache`), which holds the Oscar beside the Grammy (#4446's own census). The prototype prints each row's own venue instead.
- **To verify, not a claim:** `event_awards` name stems (`emmy`, `grammy`) may attach Daytime Emmy and Latin Grammy rows to "The Emmys" and "The Grammys" ceremony pages.

## Recommended implementation files (owners follow notice 41 and the issue's split)

- **Discover (grouping + feed card):**
  - `backend/app/utils/feed_market_quality.py` (P3)
  - `backend/app/utils/discover_bundles.py`: identity, plus `collection_href`/`collection_count` on theme bundles (P1)
  - `frontend/components/discover/ThemeBundleCard.tsx` and `BundleHeader.tsx`: header link and "See all N"
- **Authority (membership + publication contract):** a theme assembler beside `backend/app/services/container_assembly.py` that calls the predicates above over the full open inventory, on a beat.
  - Publish through the existing `read_published` revision path.
  - Sections come from the existing classes in `backend/app/utils/container_class.py` (`title` → Winners, `advancement` → Nominations, `side_question`), grouped by the ceremony concept key from `backend/app/utils/event_awards.py`.
  - `edition_for_slug` in `backend/app/routes/containers.py` gains a theme edition kind.
  - Beat allowlist in `backend/tests/test_tasks_wiring.py`.
  - Corrections and withdrawals through `backend/app/utils/container_corrections.py`.
- **Matching (lane1):** `backend/app/utils/cross_source_matching.py` for award-category pairing (P2).
- **Web collection reader (current owner of `/collections`):**
  - `frontend/lib/collections.ts`: theme edition label, section titles, the untraded split.
  - `frontend/components/collections/CollectionHub.tsx`: hero question and caption, earned chips, headliners, "Not traded yet (N)", back label.
  - `frontend/components/collections/CollectionMemberCard.tsx`: compact dense-row variant.
- **UX:** member page back label from the reading context (the `/futures/[id]` layout).
- **Native:** the hub equivalent, after web.

## Next action

1. Discover builds **P3 + P1**: the gate plus durable identity on the theme bundle, with guard tests pinned to the near-miss ids. It ships inert until a collection is published.
2. File **P2** with lane1 as a matching symptom under #2693 (18 award pairs, evidence here).
3. Authority stages the theme assembler after the current NFL/MLB publication. This design adds **no gate** to that release.
4. Before claiming any theme is supported in general, re-run `evidence/classify.py` on a third theme.
