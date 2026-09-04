# lane1/099 — the merge was never stuck, night two was never today, and both duplicates are on-page

**PILLAR: TRUTH. SHIP: a 49ers fan stops seeing their team play twice in Week 1.**
Session ran Fri 2026-09-04, 02:02–03:0x PDT. Kickoff Thu 9/10 — **six days.**

---

## TL;DR

1. **§1 merge — waited, correctly, and it LANDED at 02:57 PDT.** `69c9ac98` is on master as merge
   commit **`3a1e6c9f`** (`--no-ff`, so the granted sha is a parent verbatim and the token is not
   stranded). The integrator held 152 out of its 151/153/154 batch on a real conflict
   (`backend/app/tasks/__init__.py` overlaps 151, whose cert pins an exact beat count), then landed
   it as its own train via PR **#3000**. **No orchestrator escalation was warranted and none was
   written.** The §1 "no live integrator" branch never opened.
1b. **The owed item is DISCHARGED: `047f57ba` is staged as CERT-906**, PR
   [#3001](https://github.com/alexander-bain/bainluck/pull/3001). See §6.
2. **§2 night two — NOT readable, and reading it today would have filed a false P1.** The run this
   session could see is **night ONE**. Two of the amendment's falsification clauses trip verbatim on
   it. Details below; this is the session's most load-bearing finding.
3. **§3 Week 1 = 18.** Alex has not run the gate. Held the line for the ninth session; no bypass
   built, no new note written.
4. **D48 mystery-shop found a stale belief and corrected it:** the NFL league page does **not** cap
   at 8, so **both** duplicate pairs are user-visible, not just the 49ers one.
5. **Cert staged: CERT-906**, PR #3001, sha `047f57ba`, issue #2983. Bus-graded (not Tier A — notice
   10 is frontend-only and this is `backend/tests/`).

---

## 1. §1 — the merge, and why "queued behind" was the wrong worry

At session start: `NOT-YET`, lock `HELD` (01:23, integrator/149+150). During the session the lock
released at 02:12, was retaken at 02:18 by `integrator-151-41054`, and master took three merge
commits — `6a1e4cd9` (151), `2c37f8f6` (153), `7720bacd` (154). **152 was passed over**, and 153/154
were stamped `consumed-…-merged-in-batch-7720bacd-deployed` while 152 stayed suffix-less.

That looked like a skip worth escalating. It was not. The integrator's own runner log
(`runner-logs/integrator-20260904-021413.log`) records the reason and the resolution:

> l.32 — "Only `backend/app/tasks/__init__.py` overlaps (151 ↔ 152), and 151's cert pins an exact
> beat count — so 152 goes in a separate train."
> l.65 — "Directive 152 was held out by my own beat-count reasoning; I hold the lock, so let me land
> it as its own train now."
> l.71 — pushes `3a1e6c9f…` to `refs/heads/integrator/152-window-pass-m…` → PR **#3000**, then
> `sleep 580` on CI.

**Lesson worth carrying:** an inbox item passed over while *later* items are consumed is not
evidence of a skip. Read the integrator's runner log before writing anything — the reason is
usually already recorded there, and it cost one grep to find.

### Gates pre-verified on `69c9ac98` this session, so nothing surprises the next reader

| check | result |
|---|---|
| Gate 13 — `TOKEN GRANTED` present | **PASS** (ledger line 630, CERT-898) |
| Gate 18 — later row with `supersedes` naming CERT-898 | **PASS** — none |
| CERT-898 premerge: "EXACT-SHA FULL CI REQUIRED BEFORE MERGE" | **SATISFIED** — 14 checks `success`, `deploy` `skipped` (expected off-master) |
| `git rev-parse 047f57ba^` | `69c9ac98…` — parent **verbatim**, token not stranded |
| `ec7c0e7a` (#2983 / PR #2987) ancestor of `69c9ac98` | **YES** — the merge carries the whole window-pass mechanism |

⚠ A gate-18 grep of the shape `grep -i supersedes … | grep -i 898` **false-positives**: ledger line
571 matches on the *event id* `15293898`. Anchor it — `grep -iE 'supersedes:?[[:space:]]*\`?CERT-898'`.

---

## 2. §2 — the night-numbering slip that would have filed a false P1

**This is the finding of the session.** The 099 directive said night two "is now readable". It was
not, and the run that *was* readable trips the falsification clauses.

`lane1/099` started ~3 minutes after `lane1/098` ended, not a day later. So:

| | |
|---|---|
| run visible this session | `last_started_at 2026-09-04T06:40:40Z`, success `06:45:58Z`, 317.6s |
| the amendment comment | `#2983#issuecomment-5537445111`, created **2026-09-04T07:52:08Z** |
| therefore | the amendment was authored **after** that run — it is night **ONE** |
| night two | `06:40Z Sat 2026-09-05` |

The clincher is not the clock, it is the payload: the continuation the amendment names as night
two's expected `resumed_from`, `2026-11-28T00:00:00+00:00|15197566`, is **exactly the value the
visible run wrote**. It is the baseline the prediction was written *from*, not a test of it.

Read as night two, this run trips **two** clauses verbatim — `resumed_from: null` (the directive's
"different and worse bug … P1, its own issue") and `examined` 600 rather than ~85. Read correctly it
is the expected baseline. **No finding was filed.**

### Night one, banked (posted to `#2983#issuecomment-5538283652`)

`terminal partial` · `complete false` · `stopped_by deadline` · `resumed_from null` ·
`restarted_from_exhausted_cursor false` · `continuation 2026-11-28T00:00:00+00:00|15197566` ·
`pages 6` · `examined 600` · `eligible 685` · `applied false` ·
verdicts: agrees 546, authority_moves_us 25, teams_disagree 1, no_answer 28, all three `refused_*` 0 ·
filing `anchor-schedule-drift` → #2978.

### The old code was deployed, and it is checkable rather than inferable

Night one's full key set is `applied, by_verdict, complete, continuation, elapsed_seconds, eligible,
examined, filing, fingerprint, measured, moves, pages, restarted_from_exhausted_cursor,
resumed_from, stopped_by, terminal`. **Every `pass_*` field is absent — not `null`, absent.** That is
the amendment's own "had not deployed" case and is not a finding.

### It is FIVE new fields, not three — and the amendment's table omits the decisive one

Read from source at `69c9ac98` (`app/tasks/anchor_schedule_sentinel.py`): the new payload adds
`reached_window_end`, `pass_open`, `pass_drift_seen`, `pass_started_at`, `pass_expired`. Line 696:

```python
complete = bool(state["reached_window_end"] and pass_open and not pass_expired)
```

So `complete: false` has **three** distinguishable causes and the next reader must name which fired:

| `reached_window_end` | `pass_open` | `pass_expired` | reading |
|---|---|---|---|
| `false` | — | — | sweep truncated (deadline/pages) — expected on the middle nights |
| `true` | `false` | `false` | **`CHAIN-BROKEN`** — the case predicted for night two |
| `true` | `true` | `true` | the pass aged out |
| `true` | `true` | `false` | would be `complete: true` |

This was appended to the #2983 comment so the next reader meets it there.

### A scheduling hazard nobody has named yet

The sentinel starts 06:40Z and runs **317s**, so it is live until ~06:46Z. Under D45's recorded
cause, *every master merge cycles `worker-heavy` and kills a running beat*. **A merge deploying
between 06:40Z and 06:46Z on any of nights two/three/four kills that night's run and slides the
close by a night.** Not actionable from a build lane, but the integrator should avoid that six-minute
window while #2978's chain is running.

---

## 3. §3 — Week 1 is still 18

Counted with the `'rows' not in d` branch first (a failed db-query has no `rows` key and
`d.get('rows') or []` prints a confident `0`). **18 rows.** Alex has not run the destructive repair.

Held the line for the ninth consecutive session: did not run it, did not use the
`POST /api/admin/repairs/{name}` bypass (gated on `_check_admin_secret` only and therefore a real
hole in `_check_admin_destructive`, `app/routes/admin_utils.py:151`), did not write another note, did
not touch `YOUR-TURN.md`.

The two movers are unchanged: `14780595` (SF @ LAC, espn_id `401873124`) and `14781140`
(ARI @ LAR, espn_id `401873004`).

---

## 4. D48 mystery-shop — a stale belief corrected

`tools/look.sh https://bainluck.com/sports/americanfootball_nfl` at `SHOT_W=390` (780×9052, cropped
in 1400px bands). Posted as `#2737#issuecomment-5538273860`.

| slot | position | pair |
|---|---|---|
| Sep 10 5:35 PM | **card 2** | LA Rams 65% / **San Francisco 49ers** 35% (`14632820`) |
| Sep 10 5:35 PM | **card 3** | LA Chargers 57% / **San Francisco 49ers** 43% (`14780595`) |
| Sep 13 1:25 PM | — | LA Chargers 83% / **Arizona Cardinals** 17% (`14780147`) |
| Sep 13 1:25 PM | 2 cards later | LA Rams 86% / **Arizona Cardinals** 14% (`14781140`) |

**The correction:** the NFL league page does **not** cap its list at 8. The header reads
`Upcoming 19` and it renders the whole slate, so the Cardinals pair is **not** off-page — it sits two
cards apart with Vikings/Packers between. **Two franchises are visibly doubled in Week 1, not one.**
The 49ers pair is still the worst of it: adjacent, cards 2 and 3, above the fold.

Incidental tell consistent with `14781140` being the phantom: the LAR/ARI card is the only card in
its slot with **no `Proj` line**; its neighbours all carry one.

Logos render correctly throughout (Seahawks, Patriots, Rams, 49ers, Chargers, Jaguars, Browns,
Steelers, Falcons, Colts, Ravens, Titans, Jets, Bengals, Buccaneers, Texans, Bills, Panthers, Bears,
Lions, Saints, Cardinals, Vikings, Packers, Raiders, Dolphins) — the contrast with #2447's WTA
initials on the *same component* still holds.

---

## 5. Gates run this session

| gate | result |
|---|---|
| `pytest tests/test_anchor_schedule_sentinel.py tests/test_startup.py` @ `047f57ba` | **36 passed, exit 0** |
| `python3 scripts/evals/scan_mutation_residue.py` | **CLEAN — 0 residual mutants, 550 needles, 2954 broad checks, exit 0** |

Frontend gates: N/A (no frontend files touched); this worktree has no `node_modules`, so
`npm run build` would exit 127 — a harness story, not a pass. Take them from CI.

---

## 6. The merge landed and the cert is staged — 098's owed item is discharged

At **02:57 PDT** `69c9ac98` became an ancestor of master via merge commit `3a1e6c9f`:

```
3a1e6c9f Merge lane1/096-window-pass-marker @ 69c9ac988f7191c6bb5ff74202626c10a03909da
         (CERT-898: bind the window-pass marker to the cursor it was written for) into master
```

`--no-ff`, so the granted sha is a **parent verbatim** — no rebase was needed and the token is not
stranded. `git diff origin/master...047f57ba --stat` is the single test file, 106 insertions, 0
deletions, and the branch is exactly one commit ahead of master.

Then, in order: PR **[#3001](https://github.com/alexander-bain/bainluck/pull/3001)** opened, and
`tools/stage-cert.sh` (never a hand-picked id) returned **CERT-906**. Block verified at top level at
the end of `CERT-QUEUE.md` — `status: staged`, `lane: lane1`, `issue: 2983`, sha `047f57ba…`, not
nested inside a neighbouring block.

The presentation carries: what it is, the four-night claim table, the direct raw-store assertion of
the divergence, the ablation, the SETTLED counterexample, the gates re-run this session, and the
merge context with gates 13/18 shown passing.

### One thing the next session should watch

Master is `3a1e6c9f`; `/api/health` still reported `commit: 7720bacd` (uptime 981s) minutes after
the merge — the release was mid-rollout, which is normal and the integrator verifies it. But **the
#2978 close chain now depends on that deploy**, so confirm `/api/health` reports `3a1e6c9f` or later
well before `06:40Z Sat 9/5`. If it has not deployed by then, night two runs the old code, every
`pass_*` field is absent again, and the first night that can close #2978 slides one night per night
of delay.

---

## 7. Traps this session added

- **`cd <path> && …` in one Bash call silently scopes every LATER git command in the session.** Half
  an hour was nearly lost to `git ls-tree -r HEAD` reporting 2,480 files and no `artifacts/` — the
  shell was still in `backend/`, so the tree listing was prefix-scoped to it and `ls artifacts/`
  correctly said "No such file or directory". **Use `git -C <abs>` for every git call.**
- **`grep -i '898'` over the cert ledger false-positives on event ids** (`15293898` on line 571).
  Anchor gate-18 greps to `supersedes:?\s*\`?CERT-898`.
- **An inbox item passed over while later items are consumed is not a skip.** Read
  `.claude/handoff/runner-logs/integrator-*.log` first — the integrator records its own reasoning
  and it cost one grep.
- **`grep status` on `LANE-integrator.lock` still returns ~15k chars of August.** `head -5` only.
  (Restated because it was nearly repeated.)
- **`sleep 240` in a Bash call exceeds the default 120s timeout and dies with exit 143** — a harness
  story, not a result. Pass an explicit `timeout` or keep sleeps under ~110s.
- **A `look.sh` PNG at `SHOT_W=390` was 780×9052 here** — four 1400px bands. The card you want is
  rarely in band one; the Cardinals pair was in band 3.
