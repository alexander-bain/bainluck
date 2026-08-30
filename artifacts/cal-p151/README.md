# CAL-P151 — cricket's miss is one family, and that family's markets carry other markets as their outcomes

> ⚠️ **THIS FILE HAS TWO PARTS AND §1–§7 ARE PART ONE.** They were written
> before `CERT-485` came back `BLOCK — TOKEN WITHHELD` (18:26Z). §6's
> "did NOT touch the five commits / `.gitleaksignore`" is TRUE OF PART ONE ONLY
> and was overtaken the same session — **read §8 for the current state of the
> branch.** Part one's measurements (the cricket fold, the window, the read
> rail) are unaffected and still stand.

**TL;DR.** The directive's one named fold is done, and it answers more than it
asked. The producer's own chain now runs on the admin read rail — it never had —
and on the DEPLOYED predicate it reproduces the published `polymarket/cricket`
cell to **0.03 pp** (3,260 rows vs the payload's 3,258). That agreement is what
makes the rest readable. The cell's entire miss sits in ONE of seven
name-families, and the reason is not pricing and not grading: **Polymarket's
cricket sub-markets are being ingested as OUTCOMES of the match-winner market**,
so a duel carries two or three winners. The other three big families are at
−0.05, +0.32 and +0.41 pp.

| item | state |
|---|---|
| 1 beat classification | ✅ beat 20 landed and is classified — **MISS, class C_DEPLOY_KILL** — §1 |
| 2 post-deploy headline | ⛔ still correctly blocked — the lift is NOT merged; master's tip is the **latency** lane — §1 |
| 3 cricket, the named fold | ✅ done, and the cause is measured — §2–§4 |
| 4 `board-d15.py` | ✅ exit 0 |
| 5 promotion-datapoint / refusal-register | ✅ exit 0 / exit 0 |
| 6 E2 scope | ⛔ still not possible — needs the deployed repaired population |
| — the chain on the read rail | ✅ **new capability**, four obstacles measured — §5 |

Watcher 3016/3019, banker 75909/75911, probe 37525/37527 — all alive at entry
and exit, heartbeats advancing, **zero restarts**.

---

## 1. The window, and why the headline is still not takeable

**Beat 20 landed at 18:17:12Z and it is a MISS.** The watcher classified it at
18:51:16Z: `terminal: cancelled`, `elapsed_ms: 132524`, class **C_DEPLOY_KILL**,
attribution *"task cancelled mid-flight after 132524 ms — a release, not the
producer"*. `window-beat-margins.py` gauges it `(no gauge)`, which is right — a
cancellation is not a margin question.

**Window now stands 20 beats, 16 clean, 4 misses (4=B, 7=C, 15=B, 20=C), all
attributed. 17 gauged, 17 agreements, 0 disagreements.** Beat 19 remains the
tightest CLEAN margin at 2,691 ms.

🔴 **The release that killed it was NOT ours.** `origin/master` is
`1b38f6fb Merge program/latency-151 @ c0c77f42 (CERT-484)`, committed
2026-08-30T10:49:37-07:00. `program/calibration-119` is **NOT** an ancestor of
master. `CERT-485` was still `status: running` (codex-cert, claimed
18:15:29Z) throughout this session. So the freeze-lift remains undeployed and
**item 2 stays blocked for exactly the reason CAL-P150 gave** — the board still
reads 1.88 pp on q268 and a reading taken now would be the defect wearing the
repair's name.

For the same reason **E2's scope was not re-derived**: the repaired population
still does not exist.

*(A note for whoever takes the headline: the serve path and Redis both sat at
17:37:40 for the whole session while the window log already carried an 18:17:12
census. That is not the two-clock defect — beat 20 was cancelled, so no new
census was ever published. `queued_recompute` was `False` and
`cache_age_seconds` reached 5,743 against a 1 h TTL.)*

---

## 2. 🔴 THE FOLD REPRODUCES THE PUBLISHED CELL, AND THAT IS THE LOAD-BEARING NUMBER

Everything below is worth reading only because of this row. The fold was run on
the **deployed** predicate (`682c0b37`, the branch's base) and compared against
`GET /api/calibration` at `generated_at 2026-08-30T17:37:40Z`, q268:

| | rows / n | mean price | realized | gap (actual − predicted) |
|---|--:|--:|--:|--:|
| **published payload** | 3,258 | 0.4018 | 0.4469 | **+4.51 pp** |
| **CAL-P151 fold, base chain** | 3,260 | 0.4019 | 0.4466 | **+4.48 pp** |

Two rows apart on a live database. No prior instrument in this program has
folded the published curve's own population per-cell; CAL-P078 built the twin
and recorded the read rail as a hard wall (§5 is how the wall came down).

**This also settles CAL-P150's open sign question.** CAL-P150 flagged that its
raw fold's gaps ran opposite to the published cell's and refused to reason
across the two. It was right to. The flip is real and the chain is what creates
it: on the raw tables the toss family realizes 0.181 against a 0.500 price, but
**96% of those markets never reach `deduped`** — 647 raw markets become 25
published ones. The published population is a different animal, and the base
fold lands exactly on it.

---

## 3. WHICH FAMILIES REACH `deduped` — the directive's question, answered

All seven reach it. None is fully excluded. But the rates differ enormously, and
so do the contributions.

**Deployed chain — i.e. the cell as served today:**

| family | in `normalized` | published rows | distinct | phantom | reach | mean price | realized | gap pp |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| **match_winner** | 1,327 | **1,124** | 770 | **354** | 84.7% | 0.5037 | 0.6263 | **+12.27** |
| toss match double | 746 | 699 | 699 | 0 | 93.7% | 0.3396 | 0.3391 | **−0.05** |
| team top batter | 724 | 676 | 672 | 4 | 93.4% | 0.3385 | 0.3417 | **+0.32** |
| most sixes | 660 | 625 | 625 | 0 | 94.7% | 0.3351 | 0.3392 | **+0.41** |
| completed match? | 210 | 55 | 30 | 25 | 26.2% | 0.4907 | 0.6182 | +12.75 |
| who wins the toss? | 150 | 56 | 33 | 23 | 37.3% | 0.5170 | 0.3750 | −14.20 |
| more markets | 80 | 25 | 13 | 12 | 31.2% | 0.4980 | 0.6800 | +18.20 |
| **POOLED** | | **3,260** | 2,842 | **418** | | 0.4019 | 0.4466 | **+4.48** |

Three findings fall straight out:

* **The two no-winner families are NOT the cause.** The directive's conditional
  was *"if the no-winner families are already excluded, the published miss is
  elsewhere."* They are ~96% excluded, and together they contribute **111 of
  3,260 rows (3.4%)**. The miss is elsewhere.
* **`match_winner` is the cell.** 34.5% of the rows at +12.27 pp. Remove it and
  the remaining three big families average well under half a point.
* **418 of the 3,260 published rows (12.8%) are phantom duplicates**, and **354
  of them (85%) are in `match_winner`** — the same family that carries the miss.
  That is D5's fan-out, visible inside a live published cell for the first time.
  On the branch chain it is **0 of 2,951 (0.0%)**.

**"The venue is bad at cricket" is refuted for a third time and no such label
ships.** A book whose toss market prices 0.4997 and whose three well-formed
families land at −0.05/+0.32/+0.41 is not the broken component. D14's premise
holds.

---

## 4. 🔴 WHY `match_winner` MISSES — the markets carry other markets as outcomes

The tell is arithmetic and it cannot be a pricing story. `toss match double`
publishes **0.99 winners per market**, exactly what a single-winner question
resolves to. `match_winner` publishes **1.96** on the deployed chain and **1.32**
after the lift. A duel cannot have more than one winner.

`match-winner-shape.py` turns the ratio into a distribution, then reads the book:

* **RAW:** of 1,787 resolved Polymarket cricket match-winner markets, **1,112
  (62.2%) have `win_count != 1`**. The largest classes are 3-outcome markets
  with **2 winners (395)** and with **3 winners (231)**.
* **The malformed-binary rung catches 308 of them and is BLIND to 804.** It
  fires only on `mutually_exclusive = true AND n_outcomes = 2`; these markets
  have three outcomes and `mutually_exclusive = false`, so they walk past it.
* **PUBLISHED:** among rows that actually reach `deduped`, **247 of 360 (68.6%)
  match-winner markets have `win_count != 1`** on the deployed chain, and **212
  of 377 (56.2%)** after the lift.

And the book says why:

```
market 129934: 'T20 World Cup: Australia vs Oman (Game 1)'   -- 3 outcomes, 3 winners
   is_winner=True   outcome='T20 World Cup: Australia vs Oman (Game 1)'
   is_winner=True   outcome='T20 World Cup: Australia vs Oman (Game 1) - Completed match'
   is_winner=True   outcome='T20 World Cup: Australia vs Oman (Game 1) - Who wins the toss'
```

Those outcome names are **the names of three sibling MARKETS**. The event's
sub-markets have been collapsed into one market's outcome list rather than
decomposed — **gotcha #18** (*"Polymarket game events are nested sub-markets —
decompose by `condition_id`"*), unapplied to cricket. Each sibling resolved YES
on its own question, so the market records two or three winners and the realized
rate is pulled far above the price.

**What is NOT claimed.** The four sampled markets all carry `opening_probability`
and `calibration_probability` of `NULL`, so those specific rows cannot publish —
the sample proves the SHAPE, not that these exact markets are in the cell. What
puts the shape in the cell is the published distribution above (68.6% / 56.2%),
which is measured on rows that do reach `deduped`. Naming a fix is out of scope
here: this is a matching/ingestion defect, it belongs to an ingestion queue with
its own ship, and **the lift must land before anything else touches this cell.**

**The lift helps but does not close it.** D5 removes the fan-out entirely
(phantom 418 → 0) and the cell moves **+4.48 → +3.49 pp**, but `match_winner`
still reads +11.37 post-lift because the multi-winner structure is upstream of
everything the lift changes. Per the directive's order, that makes the
leg-mapping/ingestion class the live lead and **staleness the one behind it**.

⚠️ **The +3.49 is a PREVIEW, not the post-deploy headline.** It is the branch's
predicate folded over today's live database, for one cell. The published cell is
a staged bank, the rebuild resets on merge, and §1's rule stands: the composite
is ONE post-deploy reading. **Do not add it to anything.**

---

## 5. The chain runs on the read rail now — four obstacles, each measured

`_calibration_population_ctes` had never been executed through
`POST /api/admin/db-query`. CAL-P084 recorded that as a wall. It is four
obstacles, and each is a fact the next reader will hit:

1. **The rail counts semicolons lexically (gotcha #149).** The chain carries
   **20**, every one inside a `--` comment, so it is refused as
   `Multi-statement queries not allowed` before it is planned. Fixed by reusing
   `app.utils.sql_comment_strip` — the repo already owned the tool. *(Its
   docstring says 15; D5 added comments today. The count is prose, the assert is
   what holds.)*
2. **The category predicate has NO INDEX.** `futures_markets` carries 23
   indexes and **every one mentioning `llm_sport_category` is PARTIAL on
   `status='open'`**. The calibration population is `status='resolved'`, so a
   category-scoped read of it seq-scans a wide JSONB table and blows the 10 s
   budget — the COALESCE form, the sargable form and a bare `COUNT(*)` all
   time out. Fixed by collecting an explicit **primary-key list** first.
3. **`market_info` is not `MATERIALIZED`**, so each of its dozen references
   re-runs it (~1.8 s per inline even as a pkey list). Fixed by chunking.
4. **🔴 Chunking this chain is a documented hazard.** `_virtual_market_ctes`
   says it outright: `group_sizes`/`event_sizes` are counted over `market_info`,
   so a filtered `market_info` silently re-assigns virtual-question identity.
   The designed answer, `frozen_vm_roster=True`, needs bind-parameter arrays the
   read rail cannot carry. So chunks are built from **connected components**
   under shared `(group_id, source)` and `(event_id, source)`, and a component
   is never split — every group and event is whole inside one chunk, so the
   aggregates equal their global values and each chunk is a REPLAY. Measured:
   7,992 markets, 5,626 components, **largest 21**. The only other global
   aggregates are two window functions and both `PARTITION BY vm_id`, which is
   component-local. A scope proof re-measures it every run and exits 4 if any
   key's ≥3 gate could flip (measured: 0 mixed groups of 5,914; 7 mixed events
   of 240, all kalshi `total=2`, gate-identical either way).

**The instrument defect this session caught in itself.** The first tail selected
from `normalized` and LEFT JOINed `deduped` to mark survivors. `deduped` is
**not unique on `outcome_id`** — 418 of 3,260 rows are duplicates — so the join
multiplied the left side and read **4,096** published rows for a cell that
publishes 3,258. Counting `deduped`'s own rows gives 3,260. **The agreement in
§2 only appeared once the join was removed**, and the wrong number was the
flattering one. *(Lesson: when an instrument disagrees with the thing it is
supposed to reproduce, suspect the instrument before the subject.)*

---

## 6. What this session did NOT do

* **Deployed nothing, merged nothing, certified nothing.** `CERT-485` is the
  cert window's and was `running` throughout.
* **Did not take the headline** — §1. Nothing is deployed.
* **Did not re-derive E2's scope** — the repaired population does not exist yet.
* **Did not touch the five commits**, the branch, or `.gitleaksignore` (the
  inherited CAL-P147 lane-token finding stands as CAL-P150 described it).
* **Did not restart any watcher.** Zero restarts.
* **Did not fix the ingestion defect in §4.** It is not this lane's cargo, the
  lift is mid-cert, and a second change to the cricket cell while the first is
  being graded is how a cert gets confused.

## 7. Gates and evidence

| file | what |
|---|---|
| `cricket-population-fold.py` | the fold; `--chain=base|head`, exit 0 both arms |
| `cricket-population-fold-base.{txt,json}` | §2/§3 — the DEPLOYED predicate, reproduces the cell |
| `cricket-population-fold-head.{txt,json}` | §4 — the post-lift preview, phantom 0 |
| `match-winner-shape.{py,txt,json}` | §4 — raw + samples + published distributions, exit 0 |
| `board-d15.py` (cal-p150) | exit 0, 32 cells, ordering intact |
| `promotion-datapoint.py` (cal-p146) | exit 0 |
| `refusal-register.py` (cal-p145) | exit 0 |
| `window-beat-margins.py` (cal-p144) | exit 0, 17 gauged / 17 agree / 0 disagree |

**A note on load.** Production got materially slower during this session: the
collection scan needed 1 halving at 18:35Z and 5 at 18:50Z, and a scope-proof
query that returned in 2.0 s returned `statement_timeout` minutes later. This
lane's reads are bounded SELECTs on the 10 s rail and beat 20 was killed by a
release, not by contention — but the coincidence is recorded rather than
explained away.

---

# PART TWO — the CERT-485 rework

**TL;DR.** `CERT-485` came back **`BLOCK — TOKEN WITHHELD`** at 18:26Z with three
P1s. All three are now discharged, in the order the directive named, and the
head is **green in mandatory CI** for the first time in the branch's life. The
third P1 was not a bug — it was an undeclared ruling, and it is now declared.

| P1 | verdict | commit |
|---|---|---|
| **c** — the head is RED in mandatory CI (gitleaks + mutation residue) | ✅ both reds were INHERITED FALSE POSITIVES | `49b24691` |
| **b** — D21 mis-handles valid JSON of the wrong shape | ✅ every shape now degrades by name, on BOTH paths | `1a64d027` |
| **a** — D5 can DELETE graded loss rows | ✅ real; **ruled per-VARIANT, disclosed, and pinned** | §8.3 |

**D22 / D13 / D12 were not touched.** They were green on their reviewed deltas
and the directive said so.

## 8.1 P1-c — two CI reds, neither of them ours, and the ride is over

* **gitleaks** fired on two tracked CAL-P147 **lane tokens** — the `pgrep` tags
  this lane publishes in argv on purpose (`render-banker.py:75`,
  `banker-heartbeat.json`), both from ancestor `f5a465ac`. They are not
  credentials: **nothing to rotate**, and the standing rule's ROTATE branch does
  not apply. Allowlisted by fingerprint in `.gitleaksignore`.
* **Mutation residue** (shard 3, four candidates) was a **prefix false
  positive** that exists ONLY in the merge composition: the scanner lives on
  master, four of this lane's artifact scripts contain `raise RuntimeError(...)`,
  and the mutation's replacement token is the bare `raise` prefix. Reproduced
  red in a merge worktree and green after. 🔴 **The shared scanner was
  deliberately NOT weakened** — a scanner loosened to clear one lane's artifacts
  is a scanner that stops catching the thing it exists for.

915 and 916 both said "ride it with the next change to that file." That was
spent the moment a cert made it token-blocking, which is the general lesson:
**an inherited red stops being inheritable when someone else's gate blocks on it.**

## 8.2 P1-b — a valid JSON document of the wrong shape

`json.loads` at `precompute_calibration.py:199` returned, and nothing then
checked that `raw` was a list of mappings.

* `{}` → `([], 0, None)` — a **silent zero**, which recreated the exact 96K
  shortfall D21 was written to end;
* `null` → `TypeError`, `[1]` → `AttributeError` — **and both raised on the
  PUBLIC fallback too**, with `refuse=False`.

Now: a non-empty list of mappings with the required row shape is required, and
every other shape routes through the EXISTING unreadable/absent degradation
contract, on the producer AND the serve path. The cert also corrected the
test's premise — the writer (`backfill_winners.py:7126`) only writes when
`buckets` is non-empty, so `[]` is **not** the writer's valid no-work answer.
17 red → 31 green.

## 8.3 P1-a — a real row loss, and it turns out to be an undeclared ruling

**THE FINDING IS REAL AND IT IS THE MISSION'S OWN ADMITTED RESIDUAL CLASS.**
`clean_vms` admits a variant on `has_winner >= 1`, or on D13's lone-claim arm
(`market_count = 1 AND total_outcomes = 1 AND graded >= 1`). **Those counts are
per VARIANT.** So a variant holding TWO independently-graded lone claims that
both LOST is admitted by neither arm, and D5's exact five-column join correctly
finds no row for it. Under the old two-column join those outcomes published
anyway — by matching a **sibling** variant's admission row. **D5 did not create
the exclusion; it removed the accident that hid it.**

**Why the PG gate could not see it, quoted by line number in the cert:** every
variant the fixture seeds has `has_winner == 2`. A fixture in which every
variant is admitted can only ever exercise de-duplication.

**What shipped:**

1. **The asymmetric fixture, added to the real-PG gate** — a second virtual
   market whose two variants are a LOSS-ONLY variant (two one-outcome markets
   graded FALSE by an eligible authority) and a WINNER variant. Two new arms:
   the premise (the loss variant is refused, and refused for the stated reason —
   `graded = 2` is asserted so it is not being excluded as unknown truth
   instead), and the behaviour (**the reverted two-column join publishes all
   four, under the sibling's category — that is the accident, executed**; the
   shipped join publishes only the winners). 🔴 It is **not** a narrowing of the
   existing fixture; the cert refused that escape in advance and it was not taken.
2. **The ruling, written into the SQL.** `alex-inbox/calibration-919` put the
   call to Alex with a stated default — **B, per-variant, leave it** — and B is
   what the lane does when he says nothing. The `clean_vms` comment now says
   per-variant is RULED, says option A (per-market) is arguably more correct by
   D13's own argument, and says why A is not smuggled in here: **A moves the
   published population**, so it wants its own queue, its own rebuild and its own
   measured headline. Flipping the arm now fails the gate BY NAME.
3. **The magnitude is PARKED, not dropped** —
   `.claude/handoff/PARKED-MEASUREMENTS.md`, entry `CAL-P151-P1a`. How many rows
   the exclusion costs is a third arm on `cricket-population-fold.py` (the chain
   already runs on the read rail), it is measurement rather than a build gate
   (ruling 134), and it decides nothing until someone proposes option A — at
   which point that number IS A's headline.

**Tripwires.** The derived fingerprint map was regenerated and the **only**
field that moved is `source_sha256`: `uncovered_sql_shaping` (22),
`covered_by_value` (4), `input_count` and every per-input row are identical. The
change is a comment, so it adds no SQL-shaping constant — and it adds no
semicolon either, which matters because the read rail counts them lexically
(gotcha #149).

## 8.4 The window, the gates, and what is STILL not takeable

* **Beat 21 landed 19:41:06Z and is CLEAN**, margin **86,133 ms** — the roomiest
  since beat 5. Window: **21 beats, 17 clean, 4 misses** (4=B, 7=C, 15=B, 20=C),
  all attributed. **18 gauged, 18 agreements, 0 disagreements.** Beat 19 is still
  the tightest clean margin at 2,691 ms.
* `board-d15.py` **exit 0** · `promotion-datapoint.py` **exit 0** ·
  `refusal-register.py` **exit 0**.
* Watcher 3016/3019, banker 75909/75911, probe 37525/37527 — alive with
  advancing heartbeats. **Zero restarts across the whole session.**
* ⛔ **The headline is STILL not takeable and E2's scope is still not derivable.**
  Nothing is deployed. `origin/master` is the latency lane's `1b38f6fb`;
  `program/calibration-119` is not an ancestor of it. The board reads 1.88 pp on
  q268 and **all six commits are still ONE deploy** — each moves
  `_main_input_fingerprint`, and D22 must ride with D13 regardless.
