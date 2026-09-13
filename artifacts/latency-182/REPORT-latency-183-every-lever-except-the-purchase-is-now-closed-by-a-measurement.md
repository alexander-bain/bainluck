# latency/183 — every lever except the purchase is now closed by a measurement

**PILLAR: DISCOVER. SHIP: the search box stops going cold every morning.** Same ship as 178–182.
Written 2026-09-06 11:35Z / 04:35am PT (PT = local `date` minus 3h, notice 24).

## What shipped to users today

**#3399 / LAT-P241 is live and the post-deploy check is PAID.** Typing `red` or `sta` cost 6.5–7.5
seconds on *every single request* — not the first one, every one, with byte-identical bodies
recomputed from scratch. It now costs 0.17s and 0.20s at p50, which is the network floor: the
`/api/health` control measures 0.17s from the same place. Full table and method in
`artifacts/latency-180/REPORT-latency-180-...md` under "The production AFTER-measurement".

The categorical proof is the warmer's own defect category, not the stopwatch: `no_writes` went from
`['sta','red']` to **`[]` on 44 of 44 terminal-filtered real passes**, and `terminal: complete` —
which the warmer had **never** reached in the 11 pre-deploy ring records — now appears in 18 of 32.

## The three things a reader should take from this session

### 1. The deploy question was "is it an ancestor", and the equality answer would have been silence

`7cb6531d` merged at 08:59:51Z and **never deployed and never will**. Master CI at that sha went
`completed/failure` on a decayed shard-hints guard that redded every branch for nobody's diff, and
`deploy` is gated on `backend-tests`, so five merges piled up behind it. `138fc435` repaired the
guard, overtook `7cb6531d` in the queue, and carried it to production at 10:03:13Z. A watcher
testing `commit == 7cb6531d` would have run to its deadline reporting nothing — not an error, just
silence indistinguishable from patience. 183's armed watcher gated on
`git merge-base --is-ancestor` and fired correctly; its cutover reading is banked at
`artifacts/latency-180/postdeploy-3399-cutover.txt` and is the best single datum this ship has,
because it caught the **write→hit transition** rather than a warm steady state:

    q='sta'  #1=9.657s  #2=0.132s  #3=0.195s
    q='red'  #1=7.186s  #2=0.129s  #3=0.161s

### 2. `soft_time_limit` unset is not zero, and reading it as zero nearly shipped the wrong repair

CERT-2053 asked for "another topology". The obvious $0 answer is to move the warmer to `realtime`,
and it survives the obvious check: **nine of realtime's ten beats declare no `soft_time_limit` at
all**, so scoring unset as `0` gives ONE over-budget resident against FOUR slots. It clears. It
looks like the free home that makes the dyno ask unnecessary.

It is wrong twice. Unset falls back to celery's global hard `task_time_limit` of **300s** — still
over the 120s budget — and #3060 had already *measured* that lane at ~9 slots of standing demand on
4, with `prewarm_live_feed_shapes` completing **7.0%** of its fires there before being moved off.

**My own occupancy measurement said realtime was fine, and it was worthless.** 70.9 minutes, 64.6%
of 4 slots, longest all-4-busy interval 52.2s, zero over the budget. It is a 03:15–04:25am PT Sunday
window and `poll_all_odds` — the largest known resident at 3.81 slots p95 — **does not appear in it
at all**. The rail, now parked in `PARKED-MEASUREMENTS.md` as `LAT-P243-REALTIME-AT-A-BUSY-HOUR`:
name a queue's largest known residents before you sample, and assert each one appears in the window
before you believe the result.

### 3. Every lever is now closed, and the closures are measurements rather than opinions

| lever | closed by |
|---|---|
| schedule | 59 background beats declare a hold over the budget, 1,222 fires/day, only 7 minutes in 1,440 with none resident. No 28-minute window exists anywhere on the clock. |
| move to `heavy` | 26 residents over the budget on 2 slots, and they are the 600–1350s class, so its both-busy intervals are minutes. |
| move to `realtime` | 10 residents over the budget on 4 slots (§2), plus #3060's measurement. |
| raise / remove `expires` | Refuted by this lane's own prior work, recorded in `_EXPIRING_WARMER_BEATS`: *"the broker pile drains on the first free slot either way, so the next pass starts at the same instant whether the older messages were discarded or executed as no-ops."* I proposed it, then found it already answered. |
| raise `background` concurrency | 2 × 200MB + ~100MB ≈ 512MB Standard-1X **exactly**. A memory bound, so a purchase, not a config edit. |

The first three are now a checked rule rather than prose —
`queues_that_cannot_guarantee_a_slot` + `TestNoQueueWeAlreadyPayForIsAHomeForTheWarmer`, which
fails in the good-news direction: a queue *leaving* the disqualified set means somewhere we already
pay for might house the warmer, and the answer is to measure that queue, never to raise a bound.

## Where the ship actually stands, stated without varnish

**CERT-2061 BLOCK, 11:19Z — the fourth merits BLOCK in the chain (2038 → 2045 → 2053 → 2061), and
its criticism is correct.** The presentation "adds a declaration-based queue disqualifier, tests,
and artifacts but no routing, capacity, schedule, or expiry-behaviour change; the new helper has no
production caller." True on every count.

Every BLOCK requires the same invariant: *an eligible warmer fire starts inside 120s **throughout**
every compaction window*. The table above is the argument that **that invariant is arithmetically
unreachable on the capacity we own.** So the position is not a disagreement with the bus; it is that
the bus is asking for something only a purchase can buy, and the purchase is Alex's.

**The part that is worth escalating rather than presenting again:** the schedule fix in `85d052bc`
removes a real, daily, five-beats-on-two-slots collision, and it is being held behind an invariant
**it never claimed and cannot meet**. Those are two questions that have been merged into one. That
is a routing decision above a lane, and it is now in `alex-inbox` as **option D** — land the
collision fix on the smaller promise it actually keeps, and keep the dedicated-worker question
separate on its existing default C. One sentence unsticks it. Recommended; not decided here.

## The named regression: built, run, and deliberately not shipped as a guard

`artifacts/latency-182/cert-2053-named-regression.py`, with its output beside it. The scenario is
confirmed against the live schedule, not transcribed — and the block undercounted: 02:10Z has
**five** over-budget arrivals, not four. It produces 100% warmer loss on the shared pool and 89% on
a dedicated one, against a production ring reading period p50 42.5s. It is not calibratable today
(self-gating unmodelled; declared holds overstate ~5x) and the file says so in its own output rather
than being tuned into agreement. CERT-2061's demand to model `MIN_PASS_PERIOD_SECONDS` and the lock
is the right criticism and is the work that makes it shippable — after LAT-P242 (#3466, live) has a
week of durations for the 78 beats that have none.

## Also filed

**#3506** — 1–6 of the 40 head terms fail with `reason=error` on most passes, on BOTH sides of
today's deploy (8 of 11 ring records before, 13 of 32 after). Not a regression from #3399; it is
what is left standing between the warmer and a complete pass, and it is why most passes still read
`partial`. Not claimed by this lane.

## Still running when this was written

`.lat182-sampler.sh`, extended to **19:10Z** by `.lat247-sampler-continuation.sh` (same script, same
file, one series — 183's rule about not restarting against a fresh window still binds). Production
runs the *parent* schedule, so today's two-grinder BEFORE is **12:30Z + 12:45Z** and the next
compaction window of any kind is **18:30Z + 18:45Z**. 183's stated AFTER times of 14:08Z / 15:57Z
are times in the *repaired* schedule and mean nothing until #3480 lands. Full handover:
`runner-inbox/latency/184-...`.
