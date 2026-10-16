# Comparison Feed Trial: an instrumented 26-card feed, with its evidence

PILLARS: DISCOVER, with TRUTH gates. Prepared by Fable for Alex, Tue 2026-10-06, 10:50am PT. Offline; nothing touched in the repository, production, GitHub or any lane. Not a ruling, a spec or an assignment.

**Page:** https://claude.ai/artifact/VwqBwow1UbyK3twjSQw1s6 (private to Alex). Not yet used as of this writing.

## 1. What it is for

Founder grading has stopped separating good cards from each other. This page tests whether behaviour can: Alex scrolls a feed, and the page records per card how long it was on screen and what he tapped. A grading round follows on the same cards, so stated and observed interest can be compared.

It is one person on a prototype page. A result here is a direction for #5105, not evidence about readers.

## 2. What the page records

Stored in the page's own store, readable only by Alex and Fable.

| Record | Fields |
|---|---|
| `signals/<card id>` | impressions, reading time in ms, visits, liked, would-share, details opened, order first seen, later viewing time, card type, row count, character count |
| `grades/<card id>` | amazing, fine or no |
| `meta/run` | start time, when grading began, viewport size |

Rules, chosen to match #5105 where it is specific:
- A card is on screen when half of it is visible, or when it fills 60% of the screen.
- An impression is one second on screen.
- Reading time goes only to the on-screen card showing the most pixels, so two cards visible together do not both accrue.
- Counting stops after 30 seconds without a scroll, tap or key, and when the tab is hidden.
- Once the grading round scrolls into view, further time on feed cards is stored separately.

Row and character counts are stored so reading time can be compared against the card's length.

## 3. What is in the feed

Pulled Tue 10/6, 10:02 to 10:03am PT. 1,657 liquid labelled claims. Venue prices, not the blend.

| Type | Cards | Note |
|---|---|---|
| Movers | 7 | three "since yesterday", two "this week", two "this month" |
| Round-up (new) | 2 | the four MLB Division Series; NFL divisions whose favorite changed this month |
| New favorite | 3 | |
| The swing | 3 | |
| Same deadline | 4 | |
| Checklist | 3 | |
| Same question, dead heat, same odds, tipping point | 1 each | |

Order is by rule: no two cards of one type in a row. No card was picked by hand. Single-question cards Alex graded in v3 or v4 were excluded.

## 4. Changes made because of Root's review

1. **Every earlier value is an observation of the same quantity.** Kalshi's hourly and daily price history is now used alongside Polymarket's. A Kalshi-only claim uses Kalshi at both ends; a Polymarket-only claim uses Polymarket; a claim on both uses the average of the two at both ends. All 44 movement rows on the page carry the time and venue of the earlier observation in their details.
2. **A bounded window, not "last point before".** Since yesterday: an observation 20 to 28 hours old. A week: 6.5 to 7.5 days. A month: 28.5 to 31.5 days.
3. **The history must match the listing.** A claim is used only if its latest history point is within 3 points of the price pulled. 56 of 562 failed this and were dropped.
4. **Two-sided quotes only for Kalshi's earlier value.** Of 50 earlier values checked, 3 Kalshi values came from a last trade with a spread wider than 10 points. Those rows were removed, and four candidate cards fell below their minimum size as a result (one of them jointly with a checker drop).
5. **One window of a "when" question is not shown as a faller.**
6. **Headlines say "Moves", not "Biggest moves".** The pool is the claims screened, not every question.
7. **Rivalry is checked against rules text by the independent checker**, not inferred from probability sums.
8. **The series card states no cause.** It says "since yesterday", not "after Game N". No game result or series score was verified, so none is shown.

Still true: market age is judged from the earliest retained history, not a creation date. Polymarket claims were pre-screened using its own change fields before history was fetched, so a Polymarket mover that field under-reports could be missed.

## 5. Checks

43 candidates went to three independent truth checkers and one whole-feed checker: 42 pass, 1 pass after a fix, 0 fail; 0 contradictions, 6 duplicate pairs, 0 misleading. Verdicts were applied mechanically.

The page was tested by script before publishing: all 26 cards scrolled, taps on a sample, all 26 graded, against a stand-in store. Result: 26 signal records and 26 grade records written across all ten card types, reading time tracked the scripted pauses, no script errors, no sideways scroll in either theme. That is a test of the page, not of the real store or a phone.

## 6. Supply, measured once

With Kalshi history added, verified moves over the bar this morning: 38 since yesterday (5 points), 108 this week (8 points), 94 this month (15 points). About two thirds are Kalshi-only. One morning does not establish daily supply.

## 7. Evidence bundle

`fable-evidence-20261006-feed/`, with `MANIFEST.json` of SHA-256 hashes:

- `table.json`: the claim table. `extra_claims.json`: the four series claims.
- `hist5.json.gz`: raw price history from both venues with timestamps. `hist5_ids.json`: venue identifiers per claim.
- `moves.json`: every verified move with the venue, time and value of each earlier observation.
- `series5.json`: series questions, rules and hourly history.
- `cands3.json`, `cands5m.json`, `cand_slate5.json`: candidates. `final5.json`: final selection with ids and checker verdicts. `cards5.json`: exactly what the page renders.
- `check_out_0..2.json`, `slatecheck_out.json`: checker verdicts. `quality5.json`, `quality5_detail.json`, `drops5.json`: quote-quality gate and what it removed.
- `venue-pull-k.jsonl.gz`, `venue-pull-p.jsonl.gz`: venue listings as pulled, in the reduced row format `pull.py` writes.
- `code/`: every script, both checker prompts, the page source and the page test.

The grade and signal exports will be added after Alex uses the page.
