# Root receipt: founder feed-trial result, October 6

PILLARS: DISCOVER / TRUTH. Evidence for existing issues only; no dispatch, ownership, priority, milestone, scope, acceptance or gate changes.

## Preservation and checks

The supplied result write-up and five-file result bundle are copied unchanged. `ROOT-FEED-RESULT-RECEIVED-HASHES-20261006.json` records the actual bytes received, independently of Fable's original manifest. All three JSON exports match that manifest. The CSV does not: the supplied manifest describes an empty file, while the received CSV is 2,549 bytes, SHA-256 `3063ff7baf95cbf06bd3373f8f8fa138e507fec08eb2150059e0c3628fcd1158`. The original manifest and CSV are both preserved, not silently repaired. The CSV has 26 rows with IDs/grades matching the JSON exports.

Grades and signals have the same 26 card IDs. Recomputed: 6 amazing / 17 fine / 3 no; likes 5/6, 9/17, 0/3 respectively (14 total); two shares, both of the only two round-ups (positions 15 and 19); four detail opens, positions 8–11. Eight cards have multiple visits. Three cards have zero recorded dwell (positions 6, 18, 22), including two liked cards. Median recorded dwell: amazing 4s, fine 13s, no 22.25s; largest values 72s and 79.75s. Recorded impressions support exposure, not proof that every card was read.

Archived `cards5.json` confirms six repeated claim IDs, one on three cards. Seven later cards repeat a previously shown ID (positions 3, 5, 7, 8, 12, 16, 25); all seven were graded fine. The remaining 19 have 6 amazing / 10 fine / 3 no. This checks retained IDs, not independently established semantic equivalence. Alex's stated preference is one question per feed; this note does not change an issue's existing acceptance.

Fable's quoted rank correlations (+0.44 with length / −0.64 with grade) do not reproduce as standard Spearman over all 26 records: +0.4513 / −0.5092 (grade ordered no < fine < amazing). Excluding three zero-dwell records gives +0.4324 / −0.4161. Calculation/filter definitions were not supplied. These are a reproducibility discrepancy, not replacement product findings: the dwell instrument is faulty and its values should not be used to tune ranking.

One founder, one prototype, 950×1028 desktop window, repeated visits, separate grading round and venue-price data. Likes/share/dedup findings are leads, not reader estimates or causal effects; two shared round-ups are not a reliable format win rate. Clicks can reflect confusion, and destination quality can suppress clicks independently of card interest. No comparison with earlier grading slates establishes a trend.

## Does our feed check whether it already happened?

Source pin: remote master `a7dcf4fb26af522425844ffda7b477ec41d936ed`. **Partial stale/settled checks exist, but no general dated, cited real-world occurrence check when the venue still calls a question open.** This is a source-contract conclusion, not a production reproduction of the Taylor Swift row.

- `backend/app/tasks/kalshi_resolution_sweep.py:28–37` consumes Kalshi's settled status, including early settlements. It handles venue-settled / DB-open drift, not an independently known occurrence while the venue remains open.
- `backend/app/utils/market_staleness.py:154–255` infers expiry from explicit title dates/months and a limited recurring-event calendar. `backend/app/routes/feed.py:13415–13432` applies it independently of venue status; SQL at 12769–12776 also filters open status and resolution dates. This catches elapsed known dates, not every early occurrence.
- Runtime price/quote filters (`feed.py:8727`, applied around 13739–13752) and all-zero suppression (3017, applied 5622) catch settled-looking or stale price states. A fresh quote is not evidence that its proposition remains unresolved in the world.
- `backend/app/tasks/enrich_markets.py:1198–1212` can emit `stale_context`, but consumes titles, metadata and prices without a retrieved/cited current-news record. It is normally a bounded −6 score penalty (144–178), applied in `feed.py:14045–14052`, not a factual exclusion guarantee. Liveness (1354–1374) likewise derives from stored status/prices. The judge's passed-event downranking instruction (1878) is not independent occurrence verification.

A still-open question with a future deadline and active-looking prices can therefore survive while a future-tense sentence is already wrong. A robust decision must distinguish the exact proposition, occurrence time and market rules; historical “what happened” coverage can still be useful when accurately dated. Do not equate all “already happened” content with content that must disappear.

The cited Irish Times URL was opened successfully during this review. Its July 4, 2026 article reports that Swift and Kelce married on Friday and that their outfits were Christian Dior Haute Couture. The cited ABC7 URL also returned a corresponding wedding headline. This supports the example's factual premise, but we did not verify why Kalshi's contract stayed open, inspect a live settlement response, or claim its formal resolution. Fable's retained source lists the contract `KXSWIFTWEDDING-26DEC31` (Dior) as open in its prototype pull. No live Bain Luck instance of that exact future-tense card was established here.

News sources:
- https://www.irishtimes.com/world/us/2026/07/04/taylor-swift-marries-travis-kelce-in-dress-designed-by-derrys-jonathan-anderson/
- https://abc7.com/post/taylor-swift-weds-travis-kelce-christian-dior-wedding-dress/19444387/

## Routing

Comments: #5105 signals/limits; #10356 question repetition and feed opportunity cost; #10346 event/series round-up lead; #883 destination quality and click confounding; #882 subject-correct imagery/fallback within its entertainment scope; #9238 a bounded pointer only (no renewed repair); #10353 occurrence/phase evidence gap. No comment on #3050 because no feed/detail serializer parity defect is demonstrated, or #2299 because no distinct durable-signal failure was demonstrated. Existing owners and acceptance remain unchanged; no new issue or production action.
