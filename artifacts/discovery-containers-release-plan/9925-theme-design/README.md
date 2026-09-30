# #9925: theme collection page, first design direction (Awards Season, with AI as the second theme)

**Pillars:** DISCOVER · FORMATTING (membership accuracy draws on MATCHING and TRUTH)
**Ship:** a reader taps a whole Discover theme, sees its full collection that maintains itself, opens a question, and Back returns them to the same place in the feed.

**Status: a local design prototype. It is not deployed and it is not an acceptance.** No frontend, backend or iOS source was changed. No production writes were made. Production was read-only: one served `/api/feed` and bounded `db-query` reads, 2026-09-30 20:39–20:55Z (1:39–1:55 PM PT). Corrected 2026-09-30 21:03Z (2:03 PM PT) with one more bounded read (lifetime volume for the 591 candidate rows); see **Corrections** below.

## Corrections (2026-09-30, root's copy review)

Four pieces of prototype copy claimed more than the evidence shows. Each is now fixed in `prototype.template.html` and `build_prototype.py`, and the frames are re-shot.

| Was | Why it was wrong | Now |
|---|---|---|
| AI "**Most followed**" | It was the feed bundle's member order. No follow count backs it, and none is served. | "**On Discover now**": the questions the Discover card currently shows. |
| "**Not traded yet (N)**" | All 83 awards rows it covered have `volume_24h` **NULL**, not 0. 49 of them have lifetime `volume` > 0, so they *have* traded. The other 34 have no volume figure at all. The Kalshi writer stores a summed 0 as NULL (`backend/app/tasks/kalshi.py` `total_volume_24h = sum(...) or None`, and the same for lifetime `volume`), so NULL cannot be read as "no trades". | Three states, kept apart. **"No trades in the last 24h (N)"** appears only for a *measured* 0, and 0 rows qualify today. **"24h volume not reported (N)"** covers NULL. "Not traded yet" may only be printed on a measured lifetime 0, and 0 rows qualify. Evidence: `evidence/volume-lifetime-2026-09-30T2103Z.json` (+ `.query.json`). |
| Headliners "**+38 more nominees**" / "+12 more nominees" | Winner markets list pre-nomination candidates. 2027 Oscar and Grammy nominations are not announced, so no row has a confirmed nominee identity. | "**+38 more films listed**", "+12 more albums listed", derived from the served `outcome_count` (41 / 15), not hand-typed. "Chance of a nomination" stays only on questions that ask *about* the nomination. |
| "**See all 133 questions**", "133 questions" | 133 assumes the cross-venue fold (P2), which does not exist. Production serves no collection count at all. | Tagged **PROPOSED** on the card and the page. The unfolded figure (152 after today's venue-group collapse) is stated beside it. The chip counts carry the same assumption. AI's 150 is labelled as an offline application of the existing predicates, not a served count. |

**Source labels.** A ◆ row used to print the *union* of venues ("Kalshi · Polymarket") beside the representative row's single price, which reads as a blend. Now the price carries **only its own venue's name**, and the other venue's copy is printed separately under its own name and price ("Also on Polymarket: The Odyssey 47%"), for both representative rows and served twins. Two examples of why this matters: Kalshi calls one film "La Bola Negra" (80%) and Polymarket calls it "The Black Ball" (79%), and Best New Artist has Ella Langley at 68% on Kalshi and 54% on Polymarket. Nothing on the page blends them.

| Open | What |
|---|---|
| `prototype.html` | the prototype, ten phone frames (390px), built from `evidence/` by `build_prototype.py` |
| `shots/proto-frame-NN.png` | each frame at 390×844, and `proto-gallery-overview.png` |
| `shots/00-BEFORE-*.png` | the production Discover cards today (Awards Season, AI) |
| `shots/04-*.png`, `shots/05-*.png` | production member page `/futures/6173044` and the existing ceremony page `/event/awards/oscars` |
| `evidence/` | served bundles, the full candidate inventories (216 awards, 375 AI), the queries, and the scripts that apply the system's own membership predicates |

## The flow (frames ①–⑥)

1. **Discover card:** unchanged three-row preview. The header gets a `›` and opens the page. "All 6 questions" (an inline expand of the feed sample) becomes **"See all N questions ›"**. N counts the whole collection, never the feed sample. In the prototype N = 133 is **PROPOSED**: it assumes P2, and it is 152 without the fold. Production serves no collection count today.
2. **Page top:** in order, `‹ Discover`, then eyebrow `Collection · 2026–27 season`, title, the group's own question (`Who wins awards season?`, from `AUTHORED_STORY_QUESTIONS`), one plain line saying what is included, the question count (PROPOSED, see above) with the price time, and ceremony chips (earned: 4 sections ≥ 3, entity-page grammar §4). **No combined percentage.**
3. **Headliners:** each ceremony's marquee category, which is the one `event_awards.py` already uses as the ceremony-page hero: Oscars Best Picture (The Odyssey 48% · The Black Ball 27% · Dune: Part Three 10%) and Grammys Album of the Year (Olivia Rodrigo 45% · Olivia Dean 21% · Rosalía 14%).
4. **One section per ceremony:** each section links to the **existing ceremony page** ("Ceremony page ›" → `/event/awards/oscars`, `/event/awards/grammys`). Inside it:
   - **Winners** first, showing the 5 most traded, with "Show all N".
   - **Nominations** folded. These are questions *about* who gets nominated, so each row reads "chance of a nomination". Several candidates can each be nominated, so this is not a race. Winner-market outcomes are **candidates the venue lists**, never "nominees", until nominations are announced.
   - **"24h volume not reported (N)"** folded (the D102 pattern). **"No trades in the last 24h (N)"** is a separate fold used only for a measured 0 (none today). See Corrections.
5. **Tap a question:** the existing member page opens. The one proposed change is that its back link reads "‹ Back to Awards Season" when the reader came from the collection.
6. **Back:** the page returns to the same row, via CollectionHub's existing `collection-reading:{slug}` context. **Back again:** Discover returns to the same card, via the feed snapshot and scroll mark (#7417) that `DiscoverCollectionCard` already relies on.

**⑦ Sparse inside a big theme:** 12 of 36 Grammy winner questions and 1 of 40 Daytime Emmy questions report 24h volume. Many Kalshi rows with no 24h figure sit at an identical 29.5% leader. The page shows rows with reported volume and folds the rest under "24h volume not reported". Of those 83 rows, 49 have lifetime volume, so they must not be called untraded. **⑧ States:**
- sparse theme (the real Oil bundle, 2 questions): no chips, headers or count
- one member can't load: existing copy, and its siblings still render
- settled question: moves to "Decided" with its result (FIXTURE shape)
- withdrawn and load-failed: existing CollectionHub states

**⑨–⑩ AI, the second theme:** AI has no ceremony structure. Sections therefore come from the questions' own decide-by dates (October 33 · by New Year 90 · later 27). The top block is "On Discover now", the Discover card's current selection. It is not "Most followed", because no follow counts back it. It is the same template, and nothing new had to be classified.

## Membership: the system's own predicates, applied to the full inventory

`evidence/classify.py` runs `_story_key` → the entertainment gate (`_is_entertainment`, from the awards bundler) → `_member_season` edition filter → `_member_answers_story_question` → `_dedupe_same_question_members`. `evidence/sections.py` then collapses rows by venue `group_id`, as `_dedupe_futures_by_group_id` does.

| | Awards Season (edition 2027) | AI (rolling) |
|---|---|---|
| name-regex candidates, open | 216 | 375 |
| pass the existing gates | 188 | 348 |
| after `group_id` collapse | 153 | 150 |
| after the **proposed** cross-venue award fold (P2); a prototype proposal, not served | 133 (attendance row excluded; 152 unfolded) | n/a |
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
- **P6 · volume states and "Awaiting result":** a NULL 24h figure is "not reported", never "no trades". "No trades in the last 24h" needs a measured 0. The Kalshi writer erases measured zeros (`sum(...) or None`), so for Kalshi that state is unreachable until the writer keeps 0. That writer change is parked, not part of this ship. "Not traded yet" needs a measured lifetime 0. For "Awaiting result", use a passed deadline until grading lands (settled means settled).
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

## Smallest concrete grouping fix (for root to split against current owners; not started)

**P3, the awards story membership gate.** Checked on `origin/master` `484e177771`.

- **Owner / file:** Discover · `backend/app/utils/discover_bundles.py` only.
- **Defect:** `assemble_story_theme_bundles` admits a member when three things hold: `_theme_member_eligible`, `_theme_story_key` equals the key, and `_member_answers_story_question`. None of these reads category. So `story:major_entertainment_events` (`_story_key` returns this key for these names, checked locally) can seat `61082201` "Ricardo Rafael Sandoval vs Oscar Collazo" (boxing) and `63448382`/`63448383` "M15 Baku: Oscar Brown vs …" (tennis) under "Who wins awards season?". The awards bundler's `_is_entertainment` (same file) already refuses them. The theme path never calls it.
- **Change:** add one predicate beside `_member_answers_story_question`, for example `_member_fits_story(story_key, item)`. For `story:major_entertainment_events` it returns `_is_entertainment(item)`; for every other key it returns `True`. Call it at **both** theme admission sites:
  - the main loop, where `_member_answers_story_question(story_key, item)` is called (~L1673);
  - the overflow top-up in `_with_story_overflow` (~L1605).
  Two sites, so a guard must pin the set, not one file line.
- **Guard tests:** a new `backend/tests/test_discover_theme_awards_category_gate_9925.py`, modelled on `test_discover_bundle_candidacy_is_not_victory_7552.py`:
  - the three near-miss ids are refused on both paths;
  - `6173044` (Oscar Best Picture, entertainment) is kept;
  - a refused member still emits as its own card, not dropped (D1 clause c);
  - a control shows a non-awards key is unaffected.
- **Reach:** latent today. Today's served bundle has 6 correct members. The defect is reader-visible whenever a fighter or player named Oscar is in the feed beside the awards family. No production writes. It changes feed grouping, so under 49(d) it goes to review as ranking-class. It adds no gate to the NFL/MLB release.
- **Not in this scope (next, separately):**
  - P4, the per-member edition filter: 25 `other_season:2026` rows, for example `109565` "Oscar for Best Actress?". It needs a bundle-level edition rule, more than one clause.
  - P1, durable identity.
  - P2, the cross-venue fold. That is a matching item for lane1 under #2693.
  - The Kalshi zero-volume writer.

## Next action

1. Root splits scopes against current owners. Discover then builds **P3** (above) first, and P1 separately after it. No product source is touched before that split.
2. File **P2** with lane1 as a matching symptom under #2693 (18 award pairs, evidence here).
3. Authority stages the theme assembler after the current NFL/MLB publication. This design adds **no gate** to that release.
4. Before claiming any theme is supported in general, re-run `evidence/classify.py` on a third theme.
