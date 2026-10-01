# latency/186 — the bound was aimed at the wrong quantity

**PILLAR: DISCOVER. SHIP: the `/search` head warmer's fires stop being discarded before they
reach a slot.** Not "the search box stops going cold" — see §4.

Session 2026-09-06, ~05:45–06:15am PT (PT = local `date` minus 3h, notice 24).

---

## 1. What happened

186 opened on directive 186, whose §2 said the next move was #3539 and that it needed a
decision rather than a patch. Before routing that decision I checked #3539's own premise
against production, and the premise was wrong in a way that changed the whole board.

**#3539 prices its three options against an effective pass period of 60 s. The real period is
~576 s.** `warm_search_head` records **102 starts against 2,949 expected fires** — a delivered
ratio of **0.03**. Nothing in #3539 — polling faster, leasing the old answer for 85 s, or
cheapening rebuilds — can cover a 576 s gap. The cadence arithmetic was never the binding
constraint; delivery was.

So the ship this session is #3364, not #3539.

## 2. The defect, and why it had been read down twice

`_EXPIRING_WARMER_BEATS["warm-search-head"]` was `20` — one beat period — under a comment
justifying it against the task's own **wall**: "~4-8 s steady state, shorter than its period,
so a fire that could not start a pass IS a superseded message."

The reasoning is sound and its premise is the wrong quantity. An `expires` bound is compared
against **delivery latency** — the wait for a free slot on `worker-background`'s
`--concurrency=2` against 57+ beat entries (#1609). The wall only decides whether a *delivered*
fire can start.

**latency/182 wrote exactly this on #3364, called it "the natural next ship here", and did not
claim it.** 183/184/185 then spent four queues on #3480, #2304/#3526 and #3539. The directive I
inherited listed #3364 under "Open, not owned by us" and called its headline **false**, on the
grounds that production shows 98 starts / 97 successes / 0 failures in 24 h.

That is evidence the task is healthy **when it runs**. It runs 3% of the time. A health field
computed over the runs that happened cannot see the runs that did not.

## 3. Evidence — three instruments, and each eliminates a different suspect

| instrument | reading | what it rules out |
|---|---|---|
| `task-metrics?task=warm_search_head` | 102 starts / 2,949 expected, `ratio` 0.03 | the deficit is real and long-window |
| `celery/schedule-adherence` | `matched_emitted` **30** per 600 s bucket = *exactly* the 20 s cadence; `matched_delivered` **0**; `undelivered_fraction` 1.0; `matched_coverage_proven` true; `bucket_attribution` `broker_or_worker`; `self_gated_fires` **0** | the BEAT (emitting fine) and the task's own 45 s FLOOR (never fires) |
| same endpoint, other `background` warmers | delivered ratio tracks `expires`, not the queue: 300s→0.87, 120s→0.37/0.35, 110s→0.23, **20s→0.03** | the QUEUE as the differentiator — they all share it |

`last_result_summary` corroborates from the consumer side: `expired: 8` of 8, `fresh: 0`,
`period_s: 574.6`.

## 4. What shipped

PR **#3546**, `f6dbabef`, branch cut from `origin/master` (**not** from latency/247, which
carries the blocked #3480 work). CERT-**2072** staged.

`20 → 180`, derived in `search_head_warmer.derive_message_expiry_s` from `_LOCK_TTL_SECONDS`
and never from a sampled latency — a bound read off a sampled maximum has been wrong twice in
this program. The derivation raises rather than clamping.

Also corrected, because they are the numbers the ENABLED decision was justified on: the beat
comment and the module docstring both priced a pass at "~1–2 s of database time" (measured
**3.3–26.1 s**, p50 ~7.9 s) and both said the head was one term when it is now **eight**
attested ones — `chiefs`, `alcaraz`, `sabalenka`, … Real people did start asking the same
questions, which is the mechanism `MIN_HEAD_SESSIONS` was built to wait for.

**The ship line is narrow on purpose.** It claims delivery, not residency. #3539 stays open and
the code, the docstring and the PR body all say so.

## 5. Handed to #3539 rather than built (see the issue comment)

1. `P_effective` is ~576 s, not 60 s — every option there is priced against a period the
   system never achieves.
2. The invariant `R − P > D_max` is **necessary**, not just sufficient. Proof: a rebuilding
   pass avoids a hole iff `D ≤ r < R`; that window has width `R − D`; passes are `P` apart; a
   window of width `R − D` is guaranteed to contain a pass iff `P ≤ R − D`. CERT-2068's
   `max(0, D_next − D_prev)` falls out as the `P = TTL` special case.
3. The feasible set is tiny. `R ≤ TTL = 60` and `R > P + 25` ⇒ `P < 35` ⇒ with a 20 s beat,
   **option 1 is forced to `P = 20`** (3×), or the beat itself moves to 30 s (2×). And
   **option 3 (#1866) alone can never satisfy it** — at `D → 0` it still needs `60 < 25`.
4. **A fourth option nobody listed, and the only one cheaper than today:** `T = 180`, `R = 90`,
   `P = 60` gives `90 − 60 = 30 > 25` ✓ with zero hole and **half** the rebuild load, at a
   ≤120 s served answer age. It is the same freshness ruling #3398's TTL route already needs —
   one decision closes both rather than a fourth question to Alex.
5. A second defect in the same predicate: **`fresh` is a false verdict over `[R, P)`.** With
   `P = TTL = 60`, anything with 25–60 s left cannot survive to the next pass. Unreachable in
   the steady state, but organic traffic reaches it — the route writes its own cache on a MISS
   at an arbitrary phase. The honest form is `ttl < max(R, P_effective)`.

## 6. Traps this session paid for, or dodged

- 🔴 **A health field computed over completed runs cannot testify about runs that never
  started.** `successes: 101 / failures: 0 / health: healthy` was read twice as "the task is
  fine" when the task was executing 3% of its schedule. The instrument that could see it —
  `schedule-adherence`'s `expected_fires` vs `deliveries` — was already deployed and already
  in the lane's own memory. Reach for the adherence row before the health row.
- **A directive is a snapshot, and it can be confidently wrong about what is not ours.** §5 of
  directive 186 called #3364 a "false headline… not ours". It is a p1, unclaimed, and this
  lane's own 182 had already named its fix. Re-read the issue, not the summary of the issue.
- **`expires` is not compared against the wall.** The general clause: *a bound on a message's
  lifetime is compared against the delay the message actually suffers, not against the work the
  message will do when it arrives.* The same file already learned this once, for a different
  delay (LAT-P075, the run lock), and the lesson did not travel two entries down the same dict.
- **The blocked branch is the default branch.** The worktree opened on latency/247, which is 16
  commits ahead of master with the blocked #3480 work. Committing there would have put a
  four-times-blocked change inside a clean one-constant PR. Check
  `git log origin/master..HEAD` **before** committing, not after (gotcha #47).

## 7. Owed

- **Post-deploy check is this lane's**, and it has a specific shape: 24 h after the merge, read
  `task-metrics?task=warm_search_head` `starts_24h` and `schedule-adherence`'s
  `matched_delivered` / `undelivered_fraction`. The claim to test is delivery, **not**
  residency — `expired: 8/8` may well persist, and that would be #3539, not a failure of this
  fix.
- `precompute_discover_candidate_base`, the other half of #3364's title, is now at 0.35 with
  `expires: 120` and is **not** covered by PR #3546. #3364 stays open for it.
