# GitHub drafts for Root's review: comparison-card evidence

Prepared by Fable for Alex, Tue 2026-10-06, 9:25am PT. Nothing here has been posted. No owner, milestone, label, release scope or issue state is changed. Parent links are Dot's to make.

**No new issues are proposed.** Every piece maps onto an existing issue, so each draft is a comment. An earlier version of this file proposed three new issues; Alex asked for the mapping first, and the mapping removed all three.

The knowledge file is `artifacts/discovery-containers-release-plan/fable-ranking-github-20261004/11-COMPARISON-WORKSTREAM-HANDOFF.md`. It must be in the repository before any comment is posted.

## Map

| Piece of the work | Existing home | Draft |
|---|---|---|
| Summary of the 98 graded cards | #4463 (parent of the comparison children) | 1 |
| Case material, evidence contract | #10353 | 2 |
| Generation rules, unreliable inputs | #10354 (related: #880 duel pairing, #933 competition-field bundle) | 3 |
| What predicted grades | #10355 (related: #597 learned reranker) | 4 |
| Variety, repetition, surface | #10356 (related: #5106 adapt to interests) | 5 |
| Card designs | #10357 | 6 |
| Movers | #948 (today's-biggest-swings bundle), #5440 (dated movement claims), #4079 (dated baseline), #1844 | 7 |
| Series state and playoff round-up | #10346 (event highlights before, during, after), #9237 stage 2 (MLB, series depth) | 8 |
| Interest signals: impression, dwell, tap, like, share | #5105 (attributed exposure, already specified), #2299, #2606 | 9 |
| More than one rater, friends and family | #10365 (freeze before recruiting), #671 (friends-and-family reviewer access) | no draft; see note at end |

Read in full for this map: #10353 to #10357, #9237, #948, #4079, #5440, #5105, #10346, #2299, #10365, #1844, #2606. Mapped by title only: #880, #933, #597, #5106, #671, #5321.

---

## Draft 1. Comment on #4463

**Founder evidence for the comparison children: 98 graded cards (Oct 4 to 6)**

Fable built four slates of machine-generated comparison cards offline from public Kalshi and Polymarket prices; Alex graded all 98 as amazing, fine or no. Results, rules, designs and limits: `artifacts/discovery-containers-release-plan/fable-ranking-github-20261004/11-COMPARISON-WORKSTREAM-HANDOFF.md`.

- Card type is the only measured predictor of his grade. Movers 7 of 7 amazing; same-deadline boards 13 of 17; reversals 0 of 6 with 4 "no"; team paths 0 of 3 in a feed.
- Truth gates removed the bad cards. "No" grades went from 5 of 30 to 0 of 29 once every sentence was checked against venue wording.
- A simulated reader panel did not predict his grades on the second slate.

Limits: venue prices, not the blend; venue identifiers, not Bain Luck IDs; one rater; grading sheets, not a feed; nothing rendered in the app.

Alex's direction, Oct 6: shipping moves to the coordinator; Fable keeps inventing and testing card types with him and audits what ships. Per-child evidence is on #10353 to #10357. No dispatch requested; no scope changed.

---

## Draft 2. Comment on #10353

**Case material: 98 founder-graded comparison cards**

For this issue's "small frozen case set": four graded slates with per-card grades and independent checker notes (handoff file, sections 2 and 10). They include compelling and weak examples of sixteen card types, cross-topic pairs, near-equal probabilities and the same question at different moments.

They do not meet this issue's evidence contract. Each card records venue, venue event, outcome name, price and pull time, with no Bain Luck question, entity or option ID and no blend lineage. They are founder judgments, not reviewer labels and not a holdout; Alex saw each slate before the next was built.

One suggested addition: a "same question at different moments" case needs proof the earlier moment was a market view. 15 of 214 large venue-reported moves were opening prices of markets younger than the span.

---

## Draft 3. Comment on #10354

**Generation rules behind the graded cards, and two unreliable inputs**

This issue places cross-topic generation after "demonstrated editorial value". Founder evidence now exists: cross-topic same-deadline boards were graded amazing 13 of 17 times. Sequencing stays the coordinator's call.

The offline rules are in section 5 of the handoff file: liquidity gates, cross-venue merge, price-blind labels, fixed per-type generators, variety caps, then independent truth and whole-set checks applied mechanically. They ran on venue listings, not on `discover_bundles.py` or #823's bundles.

Do not trust:
- Venue flags for mutually exclusive outcomes, on either venue. Probability sums were used instead.
- Plain-English restatements. An independent check rewrote 31 of 101 in the first slate.

Evidence against one existing idea: "which is likelier" pairs (the shape of #880) graded 0 of 6, with 4 "no".

Supply on single mornings: movers, same-odds groups and dead heats renew daily; same-question tables (3) and head-to-heads (1) are scarce.

---

## Draft 4. Comment on #10355

**What predicted the founder's grades, and what did not**

On held-out cards from his first 59 grades:
- Card type alone ranked an amazing card above another 72% of the time.
- Question labels (recognisability, appeal, weight, tone, gap from a naive guess) ordered 56 of 159 within-type pairs his way.
- A five-persona simulated panel ordered 28.5 of 33 within-type pairs his way on slate 1 and 19 of 49 on slate 2.

This supports the rule already here: do not substitute probability distance, rarity or closeness to 50% for editorial quality. "Same odds" cards, which exist only because numbers match, went from 3 of 4 amazing to 0 of 3.

Limits: pair-versus-single and pair-versus-alternative comparisons, which this issue requires, were not run. And a three-level grade from one rater no longer separates cards within the good types.

---

## Draft 5. Comment on #10356

**What the slates do and do not say about feed mix**

Nothing about whether a comparison beats the ordinary card it displaces: every slate was a sheet of comparisons. That test is still this issue's.

Inputs they do offer:
- Alex, Oct 6: variety and context are both important; he wants many comparison types available, and expects diversity to matter and personalization to matter quickly.
- Repetition rules used: a question in at most three cards, a subject in at most four, no two cards of one type sharing most members. Whole-set checking still caught 2 and 5 duplicate stories in the last two slates.
- Surface matters, as this issue says: team "path" cards graded 0 of 3 in a feed. Alex: not interesting in Discover, very valuable on team pages, where they already exist.

---

## Draft 6. Comment on #10357

**Candidate card designs the founder has endorsed**

Alex on the slate designs: "we should use those designs". On Movers: "I really like the biggest moves idea and the design for it." These are reactions to grading pages in a browser, not acceptance of a rendered product card.

Layout (handoff file, section 6; page source saved beside it): type kicker, optional theme tag, headline, then rows of number, plain claim and a thin bar on a fixed 0 to 100 scale. Movers add "Up 23 in a week, from 28%" and a tick on the bar at the earlier value. Two-outcome cards use the question as the headline with a blank, and names as rows.

Consistent with this issue: nothing to guess or tap; no quiz. Not done: phone, large text, accessibility, stale or partial states, the feed-to-question-to-Back journey.

---

## Draft 7. Comment on #948 (cross-post a pointer on #5440 and #4079)

**Founder evidence for a movers card, and three checks before it is promised in Discover**

Movers is the strongest comparison type measured: 7 of 7 graded amazing by Alex across two slates and five cuts (week, month, overnight, by theme, mixed). Alex's instruction, Oct 6: treat it as a strong first shipping candidate, and verify the movement before promising it in Discover.

Those cards used Polymarket price history, not our blend. The checks that remain:

1. **Same quantity.** Both ends of a move are the blend we display, with the same sources in it. #5440 already says a source entering or leaving the blend is never narrated as news; #1844 is this defect on the playoff grid.
2. **Comparable timestamps.** The earlier value is a dated observation at the stated distance. #4079 records that `probability_change_24h` was a per-write delta, not a 24-hour change. This issue's scope is built on that column.
3. **Coverage.** Enough eligible questions carry a valid baseline to fill a card on most days. #4079 measured 11% of top-5 outcomes with any delta on Sep 8.

Source-level reading on Oct 6 (default branch; no production read): `/api/futures/movers` and `max_movement_24h` derive from `probability_change_24h`. A code search found no `daily_baseline`, `baseline_captured_at`, or seven-day change in `backend`. Whether #4079's daily bank landed is not verified.

Measured reason to insist: about one in five large weekly moves in a venue's own change field was an artifact or overstated (handoff file, section 4). Additional guards used offline, beyond this issue's: market at least three days older than the span; a fall on a dated question in its last 30 days is not a move; no claim beside its complement or duplicate.

Suggested order: a "since yesterday" card first, since it is nearest the existing substrate and this issue; week and month spans once history supports them.

---

## Draft 8. Comment on #10346 (cross-post a pointer on #9237)

**Founder seed: the series, not the game, was the added value**

Alex, Oct 6, on a card showing the Rays overtaking the Yankees for the AL title over the month: game results are easy to follow, but a quick read on how the series is likely to finish was real added value. He asked for the same across all the MLB playoffs on one card, ideally inside a well-designed playoffs collection page with prompts to click through.

This fits this issue's "after" phase (expectation versus actual) and "series/futures" context, and #9237's stage 2 (MLB, series depth). Proposed shapes, unbuilt:
- Series state: series probability before and after the most recent game, with the result as the stated cause.
- Round-up: every live series on one card, each with its change.

Same movement checks as #948. A finished series reads as settled, never as a move. This is a seed, not a V3 gate; #9237 says no new child silently joins V3 gates. It only matters while the playoffs are on, so timing is Alex's call.

---

## Draft 9. Comment on #5105 (cross-post a pointer on #2299)

**Founder direction on interest signals, and one caution on exposure duration**

Alex, Oct 6: the feed needs careful use of signals; he is not sure readers can be counted on to swipe, like or share, and wants dwell time considered. He expects personalization to matter quickly.

This issue already specifies attributed exposure (impression at 50% visible for 1 second, exposure duration, visible rank, cohorts). Three additions from the comparison work:
- Record card type and row count with each exposure. Raw duration rewards long cards: a five-row checklist takes longer to read than a two-row swing. Compare within type and length.
- Tap-through to the question or entity is likely the strongest intent signal for comparison cards.
- Founder grading has reached its ceiling for telling good cards apart (#10355). Behaviour, or more raters under #10365, is the next source of separation.

No change to this issue's acceptance, owner or scope.

---

## Note: more than one rater

Alex said on Oct 6 he is happy to recruit friends and family for feedback on ranking signals, which reverses his Oct 4 "no recruitment". #10365 requires decisions and stimuli to be frozen before recruiting, and #671 covers friends-and-family reviewer access. No draft is offered: whether to act on his Oct 6 statement under those issues is his and Root's call.
