# #10678 live-priority lab — receipt (lane1b, bounded contributor)

PILLARS: TRUTH / FORMATTING · SHIP: a live game's ready probability reaches the page before
scheduled-game work that does not need the same urgency.

**Verdict: PARK (do not reject).** The candidate is correct, small, and has a trustworthy status
input that needs no new query. But whether it helps real readers can't be shown here. Its only
effect is to reorder work inside one flush, so it pays off only when scheduled-game components
tick in the same 2 s flush as a live game and arrive before it. This lab is not allowed to
measure how often that happens in production, or what one phase costs in time.

## Source / branch
- Branch `codex/10678-live-priority-lab` @ base `eaa8027a59` (reviewed #10655 planner, NOT on
  master). Worktree `/Users/bain/bainluck-dev/lane1b/.worktrees/codex-10678-live-priority-lab`
  (the sandbox refused a new top-level dir under `bainluck-dev/`).
- No application file in the lab tree was edited. Files: `tools/live-speed-lab/live-priority-*`
  and this directory only.

| File | What |
|---|---|
| `tools/live-speed-lab/live-priority-planner.py` | Pure wrapper `live_first_phases()`: calls the pinned `linked_first_phases` and only RE-ORDERS its phases. Tier 0 = live (component touches any event in a frozen `live_event_ids`), 1 = other game, 2 = unrelated. Stable sort. Empty set returns the #10655 plan exactly |
| `tools/live-speed-lab/live-priority-test.py` | 19 controls: baseline vs candidate on identical inputs, plus 4 that run the real pinned `flush_prices` closure (AST-extracted, the #10655 rig technique) with only the planner name rebound |
| `tools/live-speed-lab/live-priority-replay.py` | SYNTHETIC seeded mixed buffers (no retained buffer exists; none collected) |
| `tools/live-speed-lab/live-priority-proposed.patch` | Proposed application patch (kalshi_ws.py +62/−2, #10655 rig +2/−1). NOT applied anywhere persistent |

## Trustworthy live-status input (found: reuse, no new collection)
The #9418 admission watcher in `_run_kalshi_ws_consumer` already re-reads every Kalshi-linked event
with `Event.status == 'live'` every `ADMISSION_CHECK_SECONDS` (30 s) and then filters the result down
to the unadmitted ones. The patch keeps the unfiltered event ids in a run-local
`live_event_snapshot["ids"]`. The flush reads that once per flush. The snapshot starts empty (which
plans exactly as #10655), and a failed re-read keeps the previous set. It never uses TailReceipts.

## Controls (all on identical inputs; `lab-controls-pytest.txt`: 19 passed, EXIT 0)
all-live = baseline · all-scheduled = baseline · empty set = baseline · live game moves ahead whole
(same phase multiset, re-order only) · mixed component (market shared by live+scheduled events) stays
whole and is live-tier · live event reached via an un-ticked sibling (1 hop) and via an un-ticked
market (2 hops) marks the phase · unknown membership → single transaction · pending refresh debt →
the #10655 all-games phase is left as is · stable within tiers · unrelated phase last · snapshot
copied on entry, a status flip only affects the next call · inputs not mutated. Real-flush rig:
the live refresh happens after 2 writes (candidate) vs 6 (baseline), both write and pay the same 7
rows · one snapshot read per flush · a failed scheduled phase keeps its rows plus the later ones,
and the next flush pays them · pending-debt commit/refresh trace is identical to baseline ·
200-flush sustained-arrival sim: nothing dropped, no tier waits more than 1 flush.

Mutation check: M1 no-reorder 8 fail · M2 no-sibling-walk 1 fail (after adding the 2-hop control) ·
M3 unstable sort 4 fail · M5 drop pending fallback 2 fail. M4 (unrelated ranks as scheduled)
survives, and it is an EQUIVALENT mutant: the planner always puts that phase last, and the sort is
stable.

Patched-tree gates (throwaway detached checkout at eaa8027a59, removed afterwards): the 10 Kalshi
WS suites + startup = **245 passed, EXIT 0** (unpatched baseline also 245 passed). Patched in-module
`live_first_phases` vs lab wrapper over 8,000 synthetic plans (with and without debt): **0 differ**.

## Synthetic comparison (`replay-results.json`, 2,000 seeds/mix, uniform first-seen order)
"Saved" = how much earlier the LAST live game's phase finishes. The units are phases (each one is
a commit, a publish and a blend refresh) and rows (each one an UPDATE round trip until #10664
lands). The two units are reported separately. Total flush work is identical by assertion.

| mix (live/sched/open/tick) | flushes moved | phases saved mean/p90/max | rows saved mean/p90 | last-scheduled delay mean/max (phases) |
|---|---|---|---|---|
| 3/0/40/.5 (all-live control) | 0/1998 | 0/0/0 | 0/0 | — |
| 0/6/40/.5 (no-live control) | 0/0 | — | — | — |
| 1/1/40/.5 | 787/1797 | 0.44/1/1 | 1.1/3 | 0.49/1 |
| 2/6/40/.5 | 1842/1969 | 3.4/6/6 | 8.4/14 | 0.28/2 |
| 4/12/40/.5 | 1995/2000 | 8.3/11/12 | 20/28 | 0.29/4 |
| 6/4/40/.5 | 1978/2000 | 3.0/4/4 | 7.1/11 | 1.18/6 |
| 2/6/40/.15 (quiet pre-game) | 1035/1415 | 1.5/3/6 | 2.1/5 | 0.37/2 |
| 8/30/200/.3 | 2000/2000 | 18.3/23/28 | 32/41 | 0.26/3 |

## Honest limits
1. **No time figure.** No phase or row costs were observed, so nothing here is in milliseconds.
   #10664 shrinks the row term but not the phase term.
2. **Unknown real flush mix.** It is unknown how many scheduled-game components tick inside one
   2 s flush alongside a live game. That is the issue's own park condition, and this lab may not
   measure it.
3. **Does nothing while refresh debt is owed.** Then #10655 collapses all games into one phase, and
   the candidate leaves it alone (by design). How often that happens in production is unknown.
4. **A game that is live but not in the snapshot gets demoted.** This covers status-writer lag, up
   to 30 s of re-read lag, the window before the first read, and an event reached only through the
   #9484 bridge with no Kalshi-linked market. Such a game is ordered behind the games the snapshot
   does mark live, which is worse than baseline for that game alone. Kickoff, when status flips, is
   the likeliest moment for this.
5. Kalshi only. Polymarket `plan_flush_chunks` and blend refresh order were not touched.

## What would un-park it (for the measurement lane, not this lab)
Two numbers, both after #10655 and #10664: (a) the share of Kalshi flushes where at least one
scheduled-game component comes before a live one, and how many; (b) the median cost of one game
phase (commit, publish and refresh). If (a)×(b) is material (the issue's 20%/1 s screen is a
hypothesis, not a gate), apply the patch. Otherwise close it.

## Reproduce
```
cd /Users/bain/bainluck-dev/lane1b/.worktrees/codex-10678-live-priority-lab/backend
python3 -m pytest ../tools/live-speed-lab/live-priority-test.py -c pytest.ini --rootdir . -p no:cacheprovider
python3 ../tools/live-speed-lab/live-priority-replay.py --out ../artifacts/10678-live-priority-lab/replay-results.json
# patch check (throwaway): git worktree add --detach /tmp/x eaa8027a59 && cd /tmp/x && git apply ../<lab>/tools/live-speed-lab/live-priority-proposed.patch
```
