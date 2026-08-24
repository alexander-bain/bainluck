# Discover Interestingness — Cycle One Findings

**UX-P124 · 2026-08-24 · measurement only, read-only against production, no ranking changes.**
Instruments: `tools/discover-interest/{capture-top20.sh,run-hourly.sh,analyze-captures.py}` (new).
Deployed commit throughout: `b5c2a750`. All times UTC in evidence lines.

The directive's question: *"open the app twice a day and see something worth the second open"* —
is that true? This cycle measured it for the first time. The short answer is that the question
cannot currently be answered from production data, for a reason worth knowing, and that the
interestingness scorer is not doing the job its name implies.

---

## 0. Read this first — Discover telemetry has been 100% dark for six days

Not a finding about taste. A production defect found while measuring taste, and it is bigger
than anything else in this memo.

**Every `INSERT` into `discover_interactions` has failed since 2026-08-18 19:34 UTC.**

```
last successful row      2026-08-18 19:34:13 UTC   (web, impression)
db now at time of query  2026-08-24 18:07:29 UTC
rows in the last 48h     0
prior baseline           100–350 rows/day, web + native, for the preceding three months
```

Cause, and it is unambiguous:

```
Sentry BAINLUCK-12J  (id 7680322384)
  DatatypeMismatchError: column "provenance" is of type discover_provenance
                         but expression is of type character varying
  firstSeen 2026-08-19T09:17:04Z   lastSeen 2026-08-24T16:59:29Z   still firing
```

Two writers disagreed about one column's type:

| | declares | binds/expects |
|---|---|---|
| `backend/app/models/models.py:1359` | `mapped_column(String(20), ...)` | asyncpg sends `$13::VARCHAR` |
| deployed Postgres | `udt_name = discover_provenance` (a PG enum), default `'unknown'::discover_provenance` | refuses the implicit cast |

Timeline: `81defc26` *"provenance: discover_interactions.provenance column with write-time
tagging"* is dated 2026-08-18 12:18:22 -0700 = **19:18 UTC**. The last row that ever landed is
**19:34 UTC — sixteen minutes later**. The follow-up `92b9b786` *"fix(prov): the enum could not
store what the receiver accepted"* (2026-08-18 22:45 PT) widened the **enum**; it did not change
the model's column type, so it did not restore writes. Both are ancestors of `origin/master`.

Corroborating detail: all 25,536 surviving rows carry `provenance = 'unknown'` — the backfill
default. **Not one row has ever been written through the new tagging path.** The feature has
produced zero of the data it was built to produce, while destroying the data that already worked.

What this silently disables:

- **Impression-based seen-suppression** — the only thing that stops a returning user being served
  the identical page. (`user_seen_markets` is empty: 0 rows, and the feed's own comment at
  `feed.py:175` says so.) The returning-user protection is therefore currently *off*.
- **All personalization inputs** — dismiss propagation, semantic penalties, category escalation.
  The most elaborate machinery in the ranking stack has had no new signal for six days.
- **The eval/labeling loop**, which is already blocked on labels (24-row corpus).

Nothing alarmed, and the reason is structural rather than bad luck. **No watchdog or sentinel
references `discover_interactions` at all** — grepping `app/tasks/` for the table yields exactly
one consumer, `export_engagement.py`, and that task is *not* enrolled in `task_verdict` /
`ENFORCED_TASKS`. It aggregates an empty table, computes zeros, and returns successfully on every
beat. This is gotcha #53 in task form: a run that exported nothing is indistinguishable from a run
with nothing to export, and it has been recording success throughout the outage. Whatever fixes
the column should also give this table a write-rate floor that can go red.

**Filed as [#2156](https://github.com/alexander-bain/bainluck/issues/2156)** (`type:bug`,
`priority:p1`, `area:discover`, `area:backend`, `needs-agent`). **No fix was written — this cycle
was scoped `measurement only`** — but filing was not optional: CLAUDE.md is explicit that GitHub
Issues is the only source of priority and status, so a six-day production outage that lives in a
doc has no owner and no priority. The fix itself is one line (make the model column match the
deployed enum, or drop `provenance` from the INSERT column list and let the server default
apply). The issue carries the missing alarm as the second half of the bug, and requires a
real-Postgres test rather than a mock session — `92b9b786`'s own commit message already explains
why: a unit test, a mock session, and a migration-source assertion were *all green* while the
defect was live, because the recording double does not enforce PostgreSQL's enum type.

*Unrelated, so nobody chases it:* Sentry **BAINLUCK-YM** (`column "interaction_type" does not
exist`, culprit `/api/admin/db-query`) is a hand-typed admin query with a wrong column name — its
18:06 UTC occurrence today is mine, from this cycle. Not a product defect.

---

## 1. What Discover actually serves

### 1a. Repeat rate — measured, with an explicit limit on what it proves

12 pulls over 43 minutes (17:54:48Z → 18:37:01Z), cadences of ~80 s and ~10 min deliberately
crossing the 60 s anon response-cache TTL, three surfaces each, all on one deployed commit
(`b5c2a750` — stamped per pull, so this is one population and not a straddled release):

```
anon      12 pulls  ->  1 distinct ordering,  1 distinct card set
session   12 pulls  ->  2 distinct orderings, 1 distinct card set
debug     12 pulls  ->  2 distinct orderings, 1 distinct card set   <- cache-disabled, cold build
```

**One card set across all 36 slates. Nothing ever entered and nothing ever left.** And the two
orderings differ by a single adjacent swap at ranks 2–3 in the final pull — which turns out to be
tie-break noise between two cards the demotion cap had already flattened to the same integer, not
a ranking decision. §1c has the specimens. Read as churn, this page produced *one* event in 43
minutes and that event carried no information.

The `debug` surface is what rules out the cache: it is `cache: disabled_debug`, a cold rebuild
every pull, ~5 s each. **So the stability is the ranker, not the response cache.**

**And the window is not as short as its clock suggests.** `precompute_interestingness` ran at
**18:22:38Z — inside the window** — and rescored every market (`scored: 41941, total_markets:
41941, errors: 0`). Pulls sit on both sides of it, at 18:16:35Z and 18:26:51Z, four minutes after.
The one input designed to make this page move fired against all 41,941 markets mid-capture and
**the page did not move by a single position.**

That interlocks with §2a rather than duplicating it: a signal with a 43-point spread and 8.9
stdev, at weight 0.2, cannot re-order a base score spanning 109 points. A full rescore of every
market in the database is therefore *invisible by arithmetic*, not by coincidence. Waiting longer
does not test a different mechanism; it tests the same one at a larger `n`.

**What this still does NOT prove:** 43 minutes is not "twice a day". Base score moves on inputs
this window cannot exercise — the slate turning over as events settle, new markets being created,
prices moving materially. The hourly series (§5) samples those. But the precompute crossing means
cycle one is no longer *waiting* for its answer on the ranking question; it has one.

**What this DOES prove, and it is the harder finding:** the anon and session surfaces returned
**the same twenty cards on every one of the twelve pulls**. Carrying a stable `x-session-id`
changed nothing. (The single order difference on the last pull is the *cache*, not
personalization: `anon` was still serving the pre-swap slate that `session` and `debug` had both
already left. It resolves the same way as everything else in §1c — a tie between two capped
cards.) Given §0 this is expected rather than surprising: with impressions dark, a returning user
is indistinguishable from a first-time visitor by construction. *Today, a returning user sees 100%
repeats.* That is a real answer to the directive's question; it is just not an answer about
ranking.

### 1b. Who is actually opening it twice

```
distinct identities touching Discover, last 14 days:  200
  active on exactly 1 day:                            198
  active on 5 days:                                     1
  active on 7 days:                                     1
```

Two identities in fourteen days have opened Discover on more than one day. Both are worth naming:

```
8BBCB6B5-…  7 days active, 125 rows, surface = native, 2026-08-10 → 08-18
D4190449-…  5 days active,  70 rows, surface = native, 2026-08-11 → 08-18
```

**Both are `native`** — uppercase-UUID iOS vendor identifiers, so real devices, not warmers (a
warmer would show up as `web`). Meanwhile web carried 4,316 rows over 30 days and produced
**zero** multi-day identities. Two readings, and they point the same way: the core loop this cycle
was asked to measure is executed by about two people, and the only surface where it happens at all
is the iPhone/iPad app. **Any "was the second open worth it" metric built from production
behaviour today is measuring Alex's phone.** Cycle one's honest recommendation is to keep judging
this by taste and specimen review, not by an engagement metric, until there is traffic — and to
weight the native surface when doing so.

All-time action mix, for what the signal has ever contained:

```
impression 24,306 (to 2026-08-18)   unlike 429 (to 08-11)   dismiss 300 (to 2026-06-21)
like 290 (to 08-11)   context_expand 105   open 45   detail_click 21   … 
```

`dismiss` — the input to the most elaborate suppression machinery in the stack — last fired
**2026-06-21, two months ago.**

### 1c. Mix, staleness, and what the correctness rules did to it

Top 20 (anon, 18:00 UTC):

```
types       futures 12 · bundle 5 · event 2 · concept 1
categories  (none) 8 · tech 2 · motorsports 2 · baseball 1 · football 1 · hockey 1 ·
            tennis 1 · entertainment 1 · geopolitics 1 · health 1 · politics 1
quality     compelling 10 · normal 10
archetypes  other 6 · sports_story 5 · world_event 2 · health_weather_risk 2 ·
            political_power 1 · culture_moment 1 · company_drama 1 · absurd_but_real 1 ·
            macro_signal 1
```

Content freshness of that page:

```
resolution horizon (days out)   min 3 · median 128 · max 1412
  resolving within 7 days        2 / 20
  resolving beyond 90 days       6 / 20
cards with no resolution_date   10 / 20
cards whose numbers moved ≥1pt in 24h    5 / 20      (flat: 15)
```

**Three quarters of the page did not move yesterday, and the median card resolves in four
months.** A user opening twice a day is being shown, mostly, the same long-horizon questions with
the same numbers. That is the mechanism behind "nothing worth the second open" — not repetition
of *cards* so much as repetition of *state*.

What the correctness-tuned rules are doing to the mix:

- **The Discover event demotion is not a tiebreak, it is the score.** Both event cards on the page
  carry display score **exactly 35** — the `event_pct < 0.3` non-exceptional cap. Nothing about
  those two games influenced their rank; the cap did.

  **And this is the only thing that moved all cycle.** Across 12 pulls and 43 minutes, the entire
  page changed exactly once: at 18:37:01Z, ranks 2 and 3 swapped, on the `session` and `debug`
  surfaces only (`anon` was cache-served and identical). Nothing entered, nothing left, no other
  card moved. The two cards that swapped:

  ```
  event:14959572   Lazio @ Bologna        (Serie A, LIVE, 1 source: betting)   display 35
  event:15186676   Levante @ CA Osasuna   (La Liga,  LIVE, 1 source: betting)  display 35
  ```

  Two live games, flattened to the same integer by the same cap, trading places because a tie has
  no stable order. **Discover's only movement in 43 minutes was tie-break noise between two cards
  the correctness rules had already erased the difference between.** These are also the only two
  live games on the page — the cards with the strongest claim to being *newly* worth looking at —
  and the rule that decided their rank could not see that they were live.

- **The score the user could see does not order the page.** Reading display scores down the served
  slate: `40, 35, 35, 89, 85, 83, 82, 85, 43, 88, 88, 78, 80, 87, 71, 68, 52, 51, 85, 44`. Rank 9
  scores 43 and rank 10 scores 88. The sort is on the uncapped `_rank_score` float while the
  displayed integer comes off the capped-and-clamped display chain (§2a), so the two disagree by
  construction. Not user-facing today, but it means any future "why is this ranked here" surface
  built on the visible number will be wrong.
- **`top20_max_category<=5` is the one failing strict target** (`max_category_count = 6`,
  `category_spread = 13`). The oversubscribed bucket is `"?"` — the *category-less* cards
  (bundles, concepts, tournaments, events), which escape the category diversity cap because they
  have no category to cap. The cap is working as written and the mix is unbalanced anyway.
- **Four of twenty cards carry no ranking reason at all**; one fails `explanation_ok`; four have
  `repeats_title` snippet issues.
- **The curator ground-truth misses 80 items** the page did not show:
  `candidate_recall_gap 27 · game_market_noise 25 · ranking_too_low 15 ·
  already_represented_by_sibling_story 10 · quality_filter_too_harsh 3`. Note the shape: the
  largest bucket is *recall* (the candidate never entered the pool), not *ranking*. Tuning weights
  cannot fix 27 of those 80.

---

## 2. What the interestingness blend is actually doing

Measured with `/api/admin/interestingness-side-by-side` (`live_key_untouched: true`,
`cache_populated: true`, 20/20 sampled markets cache-hit) at weights 0.0 and 0.2.

### 2a. The blend is live, and it is a rescale, not a re-rank

`GET /api/admin/feed-config` → `interestingness_blend_weight: "0.2"`, `key_present: true`. Live,
not dark.

`stage=ranked`, per-card, w=0.0 vs w=0.2:

```
rank  base(w=0)  blended(w=0.2)  delta   card
 1      187.0        161.18      -25.82  2028 U.S. Presidential Election winner?
 2      181.5        154.95      -26.55  MLB World Series Winner
 3      176.5        148.70      -27.80  NFL Super Bowl Winner
 4      159.0        137.46      -21.54  2028 Democratic presidential nominee
 …
19       84.0         75.34       -8.66  Will Tropical Storm Saudel make landfall in China?
20       78.0         69.88       -8.12  Will Samuel Alito announce his retirement by…?
```

**Every single card loses score. Not one gains.** The blend is
`base·(1−w) + interest·w`, and the two terms are not on the same scale:

```
base rank_score across the page   78 → 187      (spread 109)
interestingness across 50 cards   20.2 → 63.1   (spread 43, stdev 8.9, median 40.5)
```

Because interestingness is *always below* base on this page, w=0.2 subtracts a roughly
proportional amount from everyone. It removes `0.2 × 109 ≈ 22` points of the base's discriminating
spread and contributes `0.2 × 43 ≈ 8.6` points of its own. **The net effect of turning the signal
on is to compress the ranking.**

The consequence, measured end-to-end:

```
stage=ranked   positions_changed 5   entered_top_n []   left_top_n []   max |delta| 2
stage=served   positions_changed 4   entered_top_n []   left_top_n []
               interleave: absorbed 5 · amplified 4 · moved_in_both 0 · moved_in_neither 24 (of 33)
```

**Turning the interestingness signal from 0 to 0.2 changes which cards Discover serves: not at
all.** Four to five cards shuffle by one or two positions. Nothing enters the page. Nothing leaves.

### 2b. The served order is mildly *anti*-correlated with interestingness

Over the top 60 served cards:

```
Spearman(served rank, interestingness) = −0.255
mean interestingness, ranks  1–20:  40.4   (n=12)
mean interestingness, ranks 21–60:  41.8   (n=38)
```

The cards Discover ranks *lower* score slightly *higher* on its own interestingness signal. The
bench is not less interesting than the page in front of it.

### 2c. The scorer cannot see a third of the top of the page

```
cards with no interestingness score at all: 10 / 60   at ranks 1, 2, 3, 4, 7, 11, 14, 15, 32, 44
their types: bundle 6 · event 2 · concept 1 · tournament 1
```

**Eight of the first fifteen cards are outside the signal's reach entirely.** The scorer is a
`FuturesMarket` scorer; bundles, concepts, tournaments and events are placed by the display chain
and never scored. Raising the blend weight cannot move them by any amount.

### 2d. Two of the eight signals are constants, and one reads a key that has never existed

`InterestingnessWeights` (sums to 100): decisiveness 15 · **volume 15** · movement 16 ·
recency 12 · resolution_proximity 12 · multi_source 10 · **category_novelty 10** ·
**llm_quality 10**.

- **`category_novelty` (10 pts) is never supplied.** `precompute_interestingness` builds
  `MarketInterestingnessInputs` without `category_recent_count` or `category_feed_share`, so
  `category_novelty_signal(None, None)` returns its neutral `0.5` for **every market ever scored**.
  A flat +5 for everyone.
- **`llm_quality` (10 pts) reads a key that does not exist.** The task passes
  `llm_quality = market_metadata['discover_llm']['quality_score']`. Measured in production:

  ```
  open futures_markets                                    47,669
    …with discover_llm.quality_score                           0
  ```

  Zero. The `discover_llm` profile carries `salience_score, oddity, stakes, breadth, arc,
  recurrence, liveness, hook_facts, why_interesting, junk_flags, …` — and **no `quality_score`**.
  So this signal is also pinned at its `0.5` default. Another flat +5 for everyone.

**20 of the scorer's 100 weight points are a constant added to every card in the database.** The
effective range is `[10, 90]`, and the observed max is 63.1.

Two further consequences:

- **The display chain's `+15` uplift cap is mathematically unreachable at w=0.2.** Max uplift is
  `w × (interest − base)`, so the cap needs `interest − base > 75`; with `interest ≤ 63` and
  page-bottom `base = 78`, uplift is never positive at all. The safety bound the #142/#143 work
  left in place as "rarely binding" is, at the configured weight, *never* binding. (It begins to
  matter above w ≈ 0.25.) The ranking chain has no cap — `w` is the only bound.
- **`volume` (15 pts, joint-largest weight) is missing data for 81% of markets.**
  `volume_24h > 0` on 8,945 of 47,669 open markets. `volume_signal(None)` returns `0.0`, so four
  markets in five are docked the full 15 points **for having no volume field, not for being
  boring.** Missing data and genuine disinterest are being priced identically — gotcha #53's
  lesson, inside the scorer.

Reasons that fired across 50 scored cards:
`fresh 28 · multi_source 22 · decisive_but_not_settled 16 · trading_volume 15 · moving 14 ·
resolving_soon 5 · charting_music 1`. **`novel_category`, `well_explained` and `trending_on_tmdb`
fired on zero cards** — the first two for the reasons above.

### 2e. The one place LLM taste reaches ranking is a punishment, not a reward

`_discover_llm_score_adjustment` (`app/tasks/enrich_markets.py:141`) is the only LLM-derived
ranking nudge. It is clamped `max(-30, min(10, …))`:

- penalties: `local -25 · specialist -20 · niche -15`, junk flags `-15..-25`, unknown flags `-6`
- rewards: `(salience − 3) × 3` → **+6 max**, plus `+2` for having named entities

**−30 available for punishment, +8 realistically available for reward.** It is a junk filter
wearing a taste signal's clothes.

And the taste vocabulary the enricher already computes goes nowhere:

```
markets with a discover_llm profile   1,430 of 47,669 open (3.0%)
fields written                        oddity, stakes, breadth, arc, recurrence, liveness,
                                      frame, why_interesting, hook_facts, salience_score, …
fields any ranking code reads         stakes + breadth  →  collapsed into one salience scalar
fields read by nothing at all         oddity, recurrence, arc, liveness, frame, why_interesting
```

`oddity` — the model's explicit *"is this surprising?"* rating, 1–5 — is written on 1,226 markets
and consumed by **zero** lines of ranking code. Its measured distribution is also telling:
`oddity=1` on 1,170 of 1,226 (95%), `oddity=2` on 55, `oddity=5` on exactly one. Either the
prompt's "baseline 1" instruction is too strong, or almost nothing in the corpus is odd. Worth
knowing which before rewarding it.

---

## 3. Proposed taste-ruling pack for Alex

Five dimensions, each with a real card from today's served page on both sides, and each phrased so
the ruling is a **choice**, not an abstraction. The recommendation column is this cycle's read;
the ruling is Alex's.

Before the five: **the structural precondition.** None of these rulings can take effect at the
current blend weight. §2a shows w=0.2 changes nothing, and §2c shows a third of the top of the
page is unreachable at any weight. A taste ruling is worth issuing now — it tells the next cycle
what to build — but "raise the weight" is not the mechanism. The mechanism is (a) put the signal
on the base's scale, (b) extend it past `FuturesMarket`, (c) feed it the inputs it already asks
for. Those are next cycle's work, not this ruling's.

---

### D1 — Movement vs. magnitude: does a *change* beat a *big question*?

In today's *ranked* slate (pre-display-chain, so the scorer's raw preference is visible),
**"2028 U.S. Presidential Election winner?"** tops the board at base **187** on nothing but
magnitude — while **"Will Tropical Storm Saudel make landfall in China?"**, whose headline is
literally *"Not Tropical Storm Saudel up 17.5 points from opening"*, sits at **84, rank 19**, and
the Alito-retirement card — also a mover — is rank 20. On the *served* page, three quarters of
the twenty cards did not move at all in the last 24 hours (§1c).

> **Ruling asked:** should a card that *moved materially in the last 24h* outrank a card that is
> merely *important and static*, on the second open of the day?

Options: (a) yes, movement is the second-open payload — a moved card is new information;
(b) no, magnitude wins, a stale 2028 election is still the biggest question on the page;
(c) split — movement wins on the *second* open of a day, magnitude on the first.

*Recommendation: (a), scoped to "material" (≥5pts).* The whole premise of a twice-daily open is
that something changed. `movement` is already the largest weight (16) in the scorer and it is
being drowned by the rescale, not by a bad weight.

---

### D2 — Resolution horizon: is "resolves this week" a virtue?

Median card on today's page resolves in **128 days**; six of twenty resolve beyond 90 days; two
resolve within seven. `resolution_proximity` is worth 12 points and is being outvoted.

> **Ruling asked:** does a market resolving inside a week deserve to outrank a structurally more
> important market resolving in 2028?

Real pair from today's served page, and it runs the wrong way: **"Dutch Grand Prix: Driver
Winner"** resolves in **5 days**, scores 35.3, and is served at **rank 17** — while **"Canadian
Team to Win the Stanley Cup Before the 2035 Season"** resolves in **1,412 days**, carries the
*lowest* interestingness on the page (20.2), and is served at **rank 13**, four places higher.
(The page's nearest-resolving card of all, "Dutch Grand Prix: Sprint Qualifying Pole Winner", 3
days out, is dead last at rank 20.)

Options: (a) yes — near resolution is inherent drama, promote hard; (b) no — horizon is neutral,
a great question is a great question; (c) yes but only inside a category, so the page keeps one
long-horizon anchor.

*Recommendation: (c).* A page of only imminent markets is a sports ticker; a page of only 2028
markets is a museum. One anchor, the rest live.

---

### D3 — Oddity: does weird earn a slot on merit?

Today's page served **"Who will Taylor Swift's bridesmaids be?"** (interestingness 53.5, the
highest scored card in the top 20, served at rank 10) and one card the classifier labelled
`absurd_but_real`. The `top20_has_weird_or_absurd` strict target passes — via keyword matching,
not via the LLM's `oddity` field, which no ranking code reads (§2e).

> **Ruling asked:** is oddity a *ranking dimension* (an odd market genuinely outranks a
> conventional one of equal weight) or a *quota* (guarantee one per page, don't otherwise reward
> it)?

Options: (a) dimension — reward `oddity` continuously; (b) quota — keep the current
guarantee-one-slot behaviour and leave ranking alone; (c) dimension, but capped so the page never
becomes a novelty feed.

*Recommendation: (c).* Note the measurement first: 95% of profiled markets are rated `oddity=1`,
so as written the signal would fire almost never. Ruling (a) or (c) implies re-prompting for a
usable distribution — that is real work, and worth knowing before choosing.

---

### D4 — Missing data vs. genuine disinterest

81% of open markets have no `volume_24h`, and the scorer docks each of them the full 15-point
volume weight (§2d). A market with no volume field is currently treated as *proven boring*.

> **Ruling asked:** when a signal is absent, should a card be scored as if the signal were bad, or
> as if the signal were neutral?

Real pair: **"WTA Toronto Winner"** carries the highest interestingness on the served page
(59.3) yet ranks 18 — versus **"Canadian Team to Win the Stanley Cup"**, interestingness 20.2, the
lowest on the page, ranked 13 on base score alone.

Options: (a) absent ⇒ neutral (score on the signals present, renormalize the weight);
(b) absent ⇒ penalty, as today — no volume is real evidence of no interest;
(c) absent ⇒ neutral for Kalshi/Polymarket, penalty for markets that *should* report volume.

*Recommendation: (a).* This is gotcha #53 in scorer form: an empty field is a response shape, not
a fact about the market. The blast radius is four markets in five.

---

### D5 — Repetition: what does a returning user have the right to not see again?

Impression suppression is currently off (§0), `user_seen_markets` is empty, and the recycling rule
(`FEED_RECYCLE_AFTER_HOURS = 12`, plus "moved ≥8pts or still contested") is written but only
reachable once impressions exist. Today, the second open is 100% repeats.

> **Ruling asked:** on the second open of the same day, what fraction of the page should be cards
> the user has already seen — and what earns a repeat?

Options: (a) hard — nothing repeats within 12h, period; (b) earned — a card may repeat only if
its number moved materially since it was last shown (the existing recycle rule, made primary
rather than a fallback); (c) soft — repeats allowed but always ranked below anything unseen.

*Recommendation: (b).* It is the only option that makes the second open *informative* rather than
merely *different*, and the rule already exists — it just has no input. This ruling is blocked on
§0 either way.

---

## 4. What cycle two should do, in order

1. **Fix the telemetry** (§0). One line. Everything about repeat-rate, personalization and
   labelling is unmeasurable until this lands, and it should carry an alarm on write-rate → 0.
2. **Make interestingness commensurate with base score** (§2a) — as written the blend can only
   subtract. Until then the weight knob is not a taste knob.
3. **Feed the scorer its own declared inputs** (§2d) — `category_novelty` and `llm_quality` are
   20 constant points; `volume` misprices 81% of the corpus as boring.
4. **Extend the signal past `FuturesMarket`** (§2c) — eight of the top fifteen cards are outside
   it.
5. **Then** apply Alex's D1–D5 ruling, and re-run this memo's instruments to measure the delta.

Note the sequencing claim: steps 2–4 are prerequisites for the ruling *having an effect*, not for
*issuing* it. Issue it first; it tells 2–4 what to aim at.

---

## 5. Hourly capture series

`tools/discover-interest/run-hourly.sh` (COUNT=13, INTERVAL=3600, out `/tmp/ux-p124-captures`) and
a 10-minute series (COUNT=18, out `/tmp/ux-p124-10min`) were launched at 17:55 and 18:06 UTC.
Analyse with:

```
python3 tools/discover-interest/analyze-captures.py /tmp/ux-p124-captures
```

The 43-minute result (§1a) is complete: **one card set across 36 slates, spanning a full
`precompute_interestingness` run**, with a single adjacent swap between two cap-tied cards as the
only movement. The multi-hour series keeps running past the end of this
cycle; it samples the inputs the short window cannot exercise (events settling out of the slate,
new market creation, material price movement), and it is the honest way to distinguish "the
ranker is deterministic" — which §1a proves — from "the *page* is static across a day", which
it does not.

Whoever picks this up: re-run the analyser against the merged set, not one directory. The three
capture dirs (`-captures`, `-10min`, `-churn`) are the same population at different cadences and
must be deduped on `captured_at` before counting, or overlapping pulls inflate the denominator:

```
python3 tools/discover-interest/analyze-captures.py /tmp/ux-p124-captures
```

**One thing to check when reading a longer series:** `precompute_interestingness` shows
`starts_24h: 12, successes_24h: 8, hard_kills_24h: 3` and `last_verdict: unverified
(not_enforced)`. Runs complete in 30–70 s, far inside any limit, so the kills are not timeouts —
but the task is not enrolled in `task_verdict`, so a killed run is silent and the Redis scores it
would have refreshed simply stay stale. That is not this cycle's finding to chase; it is a reason
not to read a flat hour as proof of a flat ranker without checking whether the rescore ran.

---

## Appendix — event 14877917 verdict (prior micro-mission)

Reported here because it never reached the report file.

**Verdict: (c), a real routing bug — and not the #2107 outage.** The backend is healthy:
`/api/events/14877917` returns 200 in 2.09 s (Yankees/Red Sox, `status: completed`, 6–1, five
win-probability sources) and `/api/events/14877917/game-markets` returns 200 in 0.40 s with **199
priced rows**, 81 of them extreme. #2107 is confined to `/api/feed`. The failure is URL shape:
`/event/<id>` (**singular**) is the event-*concept* router, while the canonical numeric game page
is `/events/<id>` (**plural**). `frontend/app/event/[domain]/page.tsx` — the L2-113 legacy
redirector, `7f9553a1`, 2026-07-14 — hands any single-segment value to `parseEventKey`, whose
final fallback (`frontend/lib/eventKey.ts:174`) returns `{domain: "golf"}` for anything without a
colon. So `/event/14877917` issues a **permanent 308 to `/event/golf/14877917`**, which is a golf
concept page, which correctly renders "Event not found." It is universal (`/event/15177664` and
`/event/14788546` 308 to golf identically), six weeks old, and not reachable from any internal
link — every internal link goes through `eventPath()` or `/events/<id>`. But the redirect is a
**308**, so a browser caches it: one hand-typed URL poisons that id for that user indefinitely.
`https://www.bainluck.com/events/14877917` returns 200 and renders the game correctly.

**Specimen handed over for the #2086 rendered check:
`https://www.bainluck.com/events/14788546`** — Cardinals @ Reds, MLB, settled 2026-08-18, final
6–5. Chosen on three grounds: its `completed_at` (08-18 01:37 UTC) is *after* its `commence_time`
(08-17 22:40 UTC), so it is not on the inverted-`completed_at` corruption class and cannot flip
back to `scheduled` overnight; it serves **306 priced rows**, 177 extreme, of which **5 are
extreme-and-ungraded** (`is_winner: null` at 0.99); and it carries a real final score, so #2086's
"the endpoint could not derive a winner" escape hatch — which *is* available for 15177664, whose
scores are null — does not apply. Any failure there is a pure display failure. Event 14877917 was
deliberately not re-used: its `commence_time` is 2026-08-29, in the future, while its `status` is
`completed`.

*Observed, not chased:* duplicate MLB event rows — 15201119 and 15291158 are the same Tigers/Rays
game, and the `152909xx` copies of Sunday's games serve **zero** markets while their siblings serve
dozens.
