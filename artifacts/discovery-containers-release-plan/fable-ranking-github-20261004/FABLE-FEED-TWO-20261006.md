# Comparison Feed Two: what was built and why

PILLARS: DISCOVER, with TRUTH gates. Prepared by Fable for Alex, Tue 2026-10-06, 3:05pm PT. Offline prototype; nothing touched in the repository, production, GitHub or any lane. Not a ruling, a spec or an assignment.

**Page:** https://claude.ai/artifact/5EHf72HWsKB9nmekebwFxE (private to Alex). Not yet used as of this writing.

## 1. What changed from feed trial one

Each change answers a point from Alex's feedback or an error in the first trial.

| Problem in trial one | Change |
|---|---|
| Questions repeated across cards | Each question appears once. 64 claims shown, 64 distinct, from 53 venue events, none repeated across cards. A topic that already appeared is also trimmed from later list cards. |
| A separate grading round biased grades down | No grading round. Three in-feed reactions: Like, Share, Not for me. |
| Reading time gave zero to short cards | Each quarter second is split among the on-screen cards by the pixels each shows. In the page test at the same 950 by 1028 window, no card recorded zero. |
| Returns to the page inflated early cards | The first visit to each card is stored separately from total time. |
| Taylor Swift row: an event that had already happened | Every claim was checked against the news today by an independent checker with web search. |
| Round-ups were the best lead (both shared) | Five round-ups, four of them new kinds. |
| "Some cards might benefit from images" | Three of the six two-outcome cards carry a small chart of the two lines. See section 4. |
| Cards already seen feel stale | Nothing shown in trial one is repeated, except that round-ups may include a question seen before. |

## 2. What is in the feed

Pulled Tue 10/6, 2:41 to 2:44pm PT. 1,659 liquid labelled claims. Venue prices, not the blend.

21 cards: 5 round-ups, 3 movers, 3 new favorite, 3 swing, 2 same deadline, 2 tipping point, 2 same odds, 1 dead heat.

The round-ups:

1. Division Series: who is likely to advance (with movement since yesterday)
2. The closest Senate races
3. Oscar front-runners
4. The Fed's next meetings: the likeliest decision
5. NFL awards: the front-runners

Each row of a new round-up is the outcome with the highest probability in its contest, confirmed against the venue's full listing and not only the liquid questions.

## 3. Checks

39 candidate cards holding 106 distinct claims were checked before selection.

- **Truth, three independent checkers, no network:** 34 pass, 3 pass after a fix, 2 fail.
- **Whole feed, one checker:** 1 contradiction, 3 duplicate pairs, 1 misleading card.
- **Already happened, eight checkers with web search:** 103 open, 2 already happened, 1 unsure.
  - Aaron Rodgers joining the Steelers was priced at 92% as a future event. He re-signed in May.
  - Ryan Reynolds appearing as Deadpool in Avengers: Doomsday was priced at 88%. Marvel confirmed it in August.
  - Google releasing Gemini 4 before October 16 was marked unsure: a version was shown to selected partners on September 30.
- **Quote quality for earlier values:** 42 ok, 1 removed.

All verdicts were applied by rule. Claims marked happened or unsure were removed. Five candidate cards were dropped whole. The two "already happened" claims sat on a "About 9 in 10" card, which is where such claims collect.

This gate is new, and it found two in 106. That is the same failure as the Taylor Swift row, caught this time before a card was shown.

## 4. The image question

I cannot test photographs here. Team logos, film posters and portraits belong to others, and a prototype should not borrow them. What I can test is the one picture Bain Luck owns: the chart.

Six cards compare two outcomes of one question. Five have a clean single-venue history. Cards 2, 12 and 19 show a small chart of the two lines; cards 6 and 16 could have had one and do not; card 8 could not. The chart uses a fixed 0 to 100 scale and no smoothing, per the standing chart rules.

Three against three is a first look, not a measurement. A real image test needs licensed images and a product decision, which sits with #882, #9238 and #3050.

## 5. What the page records

Per card: impressions, reading time (share-weighted), first-visit reading time, visits, liked, shared, not for me, details opened, order first seen, card type, row count, character count, and whether it carried a chart. Per run: start time, window size, touch or not.

The page was tested by script at 390 by 800 and 950 by 1028 before publishing: 21 of 21 signal records written, reactions mutually exclusive as designed, no script errors, no sideways scroll in either theme. That is a test of the page, not of the real store or a phone.

## 6. Limits

- One person, 21 cards, one afternoon, venue prices.
- The round-up kinds are written by hand as rules. Six kinds produced a card today; two more did not have enough contests.
- "Closest" and "front-runner" are computed from the venue listing. The truth checkers could not verify them and were told so.
- The already-happened checkers rely on web search. A miss is possible in either direction. Their sources are in the bundle.
- The MLB series may be settled within hours of the pull.

## 7. Evidence bundle

`fable-evidence-20261006-feed-two/`, with `MANIFEST.json` verified after writing:

- `table.json`, `extra_claims.json`: the claims. `venue-pull-k.jsonl.gz`, `venue-pull-p.jsonl.gz`: venue listings as pulled.
- `hist5.json.gz`, `hist5_ids.json`, `series5.json`: raw price history with timestamps and venue identifiers.
- `moves.json`: every verified move with the venue, time and value of each earlier observation.
- `cands3.json`, `cands5m.json`, `cands6r.json`, `cand_slate5.json`: candidates. `final5.json`: final selection with ids and verdicts. `cards5.json`: exactly what the page renders.
- `check_in_*`, `check_out_*`, `slatecheck_*`, `happened_in_*`, `happened_out_*`: every checker's input and verdict. `quality5*.json`, `drops5.json`.
- `feed_two_stats.py` and its output: prints every number in this file from the bundle alone.
- `code/`: every script, the three checker prompts and the page source.

File names keep a "5" from the scripts they were adapted from. The reaction and reading-time export will be added after Alex uses the page.
