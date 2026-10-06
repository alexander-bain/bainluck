# Comparison cards: what four graded slates established, and how to carry it forward

PILLARS: DISCOVER, with TRUTH gates. Prepared by Fable for Alex, Tue 2026-10-06, 9:25am PT. For Root and the Discover owners to read alongside #4463 and its children #10353 to #10357.

This file holds the knowledge. Scope, ownership and status live in GitHub. It is evidence and recommendation, not a ruling, a spec or an assignment. Nothing here was run against production, the repository or the blend.

## 1. What was done

Between Sun 10/4 and Tue 10/6 a program built 98 comparison cards in four slates from public Kalshi and Polymarket prices, and Alex graded every one as amazing ("would forward it"), fine, or no ("should not ship").

| Slate | Cards graded | Amazing | Fine | No | What was new |
|---|---|---|---|---|---|
| v1 (Mon 10/5) | 30 | 12 | 13 | 5 | five card types, six of each |
| v2 (Tue 10/6) | 29 | 15 | 14 | 0 | wider question pool, every card truth-checked, weak types removed |
| v3 (Tue 10/6) | 20 | 11 | 6 | 3 | seven new card types |
| v4 (Tue 10/6) | 19 | 8 | 11 | 0 | movers in five cuts, four more new types, movement verified against price history |

No card in any slate was chosen, removed or reordered by hand. Rules chose them; independent checkers' verdicts were applied mechanically.

## 2. Results by card type

"Amazing" counts are Alex's grades across all slates in which the type appeared.

| Card type | What it shows | Amazing | Recommendation |
|---|---|---|---|
| Movers | 3 to 4 biggest probability moves over a span (week, month, overnight), by theme or mixed | 7 of 7 | Strong first shipping candidate. Not to be promised in Discover until the three checks in section 4 pass |
| Same deadline (board) | unrelated claims sharing one deadline, ranked by probability | 13 of 17 | Ready; supply runs out if near-copies are excluded |
| Same question | one question asked of several subjects | 2 of 2 | Strong but scarce (3 candidates on the morning measured) |
| Head to head | two subjects on several questions | 1 of 1 | Scarce (1 candidate) |
| As likely as (yardstick) | an unfamiliar claim beside a familiar one at the same probability | 9 of 16 | Usable; quality varies card to card |
| Clock | one question at several deadlines | 6 of 16 | Weak in v2 (2 of 10); use sparingly |
| Tipping point | first date the market rates it likelier than not | 1 of 3 | Unproven |
| Same odds | unrelated claims at one probability ("About 1 in 5") | 3 of 7 | Fading: 3 of 4, then 0 of 3 |
| Dead heat | top two outcomes of one question, level | 1 of 3 | Fine filler |
| The swing | two outcomes of one question, one up, one down | 1 of 2 | Promising; small sample |
| New favorite | the leader of a question changed | 1 of 3 | Promising for sports (the Rays overtaking the Yankees) |
| Checklist | outcomes of one question that can all happen | 1 of 4 | Fine filler |
| Trading places | two unrelated claims that swapped order | 0 of 2 | Drop: pairs are arbitrary |
| Dossier | everything about one subject | 0 of 6 | Drop from the feed |
| Reversal | "guess which is likelier" pairs | 0 of 6, 4 no | Drop |
| The path | one team's playoffs, division, title chances | 0 of 3, 3 no | Not for the Discover feed. Alex: valuable on team pages, where they already exist |

Alex's direction, in his words summarised: movers are very valuable and he wants more; variety and context are both important and he wants many card types available; diversity will matter and personalization will matter quickly; he expects to iterate on comparison types for at least a year. He singled out the Rays–Yankees series card: game results are easy to follow, but what they add up to for the series is not, and seeing that was real added value.

## 3. Findings that should change how the work is done

1. **Card type is the only thing that predicts his grade.** A score fitted to his first 59 grades, tested on held-out cards: type alone ranks an amazing card above another 72% of the time. Question labels (recognisability, appeal, weight, tone) ordered only 56 of 159 within-type pairs his way. The lever is new card types and gates, not finer ranking inside a type.
2. **A simulated reader panel is not a substitute for him.** Five model personas rated cards. Their ranking matched his grades on v1 (28.5 of 33 within-type pairs) and failed on v2 (19 of 49). About 12M tokens went into this. Use model budget for generation, truth checks and labels, not for standing in for readers.
3. **The gates removed the bad cards; ranking did not.** "No" grades fell from 5 of 30 in v1 to 0 of 29 in v2. Inference: three changes did that. Every sentence checked against the venue's wording and rules, two weak types removed, foreign elections filtered.
4. **Plain-English restatements cannot be trusted unchecked.** In v1 the checker rewrote 31 of 101 sentences. Typical faults: "achieves AGI" where the rules pay on an announcement; "highest-grossing" where the rules count US and Canada only.
5. **A venue's own "change" figure cannot be trusted.** See section 4.
6. **Venue flags for "only one outcome can win" are unreliable** on both venues. v4 used probability sums instead.
7. **Three-level grading by one person has reached its ceiling.** Two of the last three slates had no "no" grades, and Alex said reasonable people could disagree on which card is most interesting. Further separation needs behavioural signals or more people.

## 4. The movement truth rule (required for any Movers card)

v3's movers used Polymarket's own one-week change field. For v4 every large move was compared with Polymarket's public price history.

| | Week moves of 8+ points | Month moves of 15+ points |
|---|---|---|
| Claimed by the venue field | 118 | 96 |
| Market younger than the span | 12 | 3 |
| Checked against history | 106 | 93 |
| History differs from the field by more than 5 points | 6 | 8 |
| Real move is under the bar | 14 | 10 |

About one in five "big weekly moves" was an artifact or overstated. Example: a Texas data-centre moratorium "fell from 27% to 5% in a week" in a market seven days old; the 27% was its opening price.

Rules v4 applied, proposed for the product:

- Both ends of a move are the same quantity. In the product that means the blend then against the blend now, never a venue summary field and never one source against a blend.
- The market must be at least three days older than the span shown.
- A fall on a dated question inside its last 30 days is not shown as a move; a deadline running out is not news.
- No two rows that are the same claim, a claim and its complement, or two buckets of one date question.
- A row that is one window of a "when" question can fall because the event is expected sooner. Treat as unverified meaning.

### Before Movers is promised in Discover (Alex, Oct 6)

Alex's instruction: treat Movers' 7 of 7 as a strong first shipping candidate, and verify that the movement uses our displayed blend's history, with comparable timestamps and adequate coverage, before promising it in Discover. The graded cards used Polymarket history, so none of this is established for the product.

| Check | What must be true | What is known |
|---|---|---|
| Same quantity | Both ends are the blend we display, with the same sources in it | Not verified. #5440 already requires that a source entering or leaving the blend is never narrated as news. #1844 (open) is this defect on the playoff grid; #3013 and #8692 (closed) were the same class on golf cards |
| Comparable timestamps | The earlier value is a dated observation at the stated distance | #4079 (open) records that `probability_change_24h` was a per-write delta, not a 24-hour change, and proposes a daily baseline bank. Whether that bank landed is not verified |
| Coverage | Enough eligible questions carry a valid baseline to fill a card on most days | #4079 measured 11% of top-5 outcomes with any delta on Sep 8. Today's figure is not verified |

Source-level reading, Tue 10/6 about 9:10am PT, default branch at `0f3f3a6`, no production read: `/api/futures/movers` and `futures_markets.max_movement_24h` derive from `probability_change_24h` (`backend/app/utils/movement_pool.py`). A code search of `backend` found no `daily_baseline`, `baseline_captured_at`, `baseline_probability` or seven-day change field. Code search can lag and does not cover branches, so this is a lead, not proof of absence.

The existing home for a movers card is #948 (today's-biggest-swings bundle), which is scoped on `probability_change_24h`. A "since yesterday" card is nearest the existing substrate; week and month spans need history the product may not keep.

## 5. The pipeline that produced the cards

1. Pull open questions from both venues.
2. Reduce to propositions; drop crypto, financial, single-game, daily and "mentions" markets.
3. Liquidity gates: volume floors, bid-ask spread of 6 points or less, price between 3% and 97%.
4. Merge the same question across venues (titles match, deadlines within days, prices within 6 points); drop pairs that disagree.
5. Label each question blind to its price: plain sentence, subject, domain, recognisability, appeal, weight, tone, and what could be misread.
6. Generate candidates per card type with fixed rules.
7. Select by rule with variety caps: a question in at most three cards, a subject in at most four, no two cards of one type sharing most members.
8. Independent truth check of every candidate against the venue's wording and rules. The checker judges correctness, never interest.
9. Whole-slate check for contradictions (the same event at two numbers), duplicate stories and cards that mislead in context.
10. Apply verdicts mechanically; refill from checked reserves.

Standing filters: no foreign elections; no named person's death, health or crime; no betting price formats.

## 6. Card design

Alex said of the slate designs "we should use those designs", and of Movers "I really like the biggest moves idea and the design for it". They are candidates for #10357's sketches, not approved product designs. They were drawn in the product's colours from `frontend/tailwind.config.ts`, `globals.css` and `design-tokens.css`.

- **Card:** white surface, 1px border, 16px radius, 18px padding. Uppercase 11px kicker naming the type ("MOVERS"), optional pill tag for a theme ("Culture and sport"), 23px bold headline.
- **Row:** the probability on the left in a monospaced bold face with a small percent sign; the claim in plain words beside it; a thin blue bar under the claim on a fixed 0 to 100 scale.
- **Movers row:** under the claim, one grey line, "Up 23 in a week, from 28%". On the bar, a short dark tick marks where the number was.
- **Two-outcome cards (swing, new favorite):** the headline is the question with a blank ("The ____ win the 2026 American League title"); each row is just the name that fills it; an italic connector between rows ("has overtaken").
- **Footer:** one quiet line naming the sources.
- Light and dark themes; bar colours checked for colour-blind separation.
- Each card carries fine print: the exact venue wording per row, each venue's number, and what is easy to misread.

The page source for each slate is the working reference. It is in the session workspace and should be copied into the repository's artifacts folder beside this file.

## 7. What the slates do not show

- **Nothing about feed mix.** Every slate was a sheet of comparisons. Whether a comparison beats the ordinary card it displaces is #10356's question and is untested.
- **Venue prices, not the blend.** Identifiers are venue identifiers, not Bain Luck question IDs. #10353's evidence contract (exact IDs, lineage, timestamps) is not met by these cards.
- **One rater, who had seen earlier slates.** These are founder judgments, not a holdout.
- **A grading page is not the app.** Nothing was rendered in the product or on a phone.
- **Supply was measured on single mornings.**

## 8. Split of work, and where each piece lives in GitHub

Alex chose a combination on Oct 6: shipping moves to the coordinator; Fable keeps inventing and testing card types with him and audits what ships. He also asked that the pieces be mapped onto existing issues before any are created. The mapping found a home for every piece, so no new issue is proposed.

| Piece | Existing issue |
|---|---|
| Comparison meaning, cases, evidence contract | #10353 |
| Candidate generation | #10354 |
| Value added beyond either member | #10355 |
| Feed mix, repetition, variety | #10356 |
| Card presentation | #10357 |
| Movers | #948, with #5440 (dated movement claims) and #4079 (dated baseline) |
| Series state and playoff round-up | #10346 (event highlights), #9237 stage 2 (MLB, series depth) |
| Interest signals | #5105 (attributed exposure is already specified there), #2299, analytics #2606 |
| More raters, friends and family | #10365, #671 |
| Whole-feed evaluation and replay | #5105, #10290 |

All comparison children sit under #4463. Draft comments for Root's review are in `12-GITHUB-DRAFTS-FOR-ROOT.md`.

**Graduation bar (proposed, not adopted):** a card type moves from the lab to the coordinator when it has at least six graded cards across two slates, no "no" grades, a written generation rule, a written truth rule, and a measured daily supply. By that bar Movers and Same deadline qualify on founder evidence. Same question and Head to head pass on quality and fail on supply.

## 9. Next card ideas, not yet built

- **Series state:** for a playoff series, the series probability before and after the last game. From Alex's Rays–Yankees comment.
- **Playoff round-up:** every live series on one card, each with last night's change; a natural member of the MLB playoffs collection (#9237 stage 2).
- **What last night changed:** the same shape for any dated event: a debate, a jobs report, a trailer.
- **Signals:** #5105 already specifies impression and exposure duration. Additions suggested by this work: record card type and row count so dwell can be compared against expected reading time; treat tap-through as the strongest intent signal; use declared interests (an interest chooser shipped under #9635) while behaviour is sparse.

## 10. Where the evidence is

- Project documents (claude.ai project "bainluck"): `claude/comparison-slate-v1-2026-10-05.md`, `claude/comparison-panel-and-slate-v2-2026-10-06.md`, `claude/comparison-slate-v2-sealed-predictions.md`, `claude/comparison-slate-v2-result-and-v3-2026-10-06.md`, `claude/comparison-slate-v4-2026-10-06.md`, and the code files `claude/comparison-slate-v1-code.md` and `claude/comparison-slate-v2-code.md`.
- Repository artifacts folder `artifacts/discovery-containers-release-plan/fable-ranking-github-20261004/`: files 09, 10 and 10a, the panel dataset and 3,652 labelled questions.
- Grading pages (private to Alex): v1 https://claude.ai/artifact/VCMucCq155eX4wdH15kdft, v2 https://claude.ai/artifact/4gJ1W2nGpWxhvSJEofmQYw, v3 https://claude.ai/artifact/1py1DLUJ1HzqCdZe5fbB7Z, v4 https://claude.ai/artifact/1JymcV3NH1u5HqTm2XECZB.
- v3 and v4 generator code, checker prompts and the history check: `claude/comparison-slate-v3-v4-code.md`. Page source for v3 and v4: `comparison-slate-v3-page-source.html` and `comparison-slate-v4-page-source.html`, to sit beside this file.
