# CAL-P149 — the bracket's risk was on the wrong layer, and the singleton check that lies

**TL;DR.** Nothing landed; the freeze holds (`git diff backend/` **0 bytes**, D13/D22 still
unanswered, YOUR-TURN.md unmodified since 07:12 PT, `land-12cal.sh` not run). All five carried
instruments re-run green. Two findings, both from checking a *carried number* against the
mechanism it was supposed to describe:

1. ✅ **CAL-P148's 1-in-102 was attributed to the wrong layer, and now has a bound.** That number
   is the **serve's** miss rate. The promotion bracket does not depend on the serve — it depends on
   the **banker** polling while a worker happens to be serving. Nobody had costed that second
   sampling layer, because the banker was built (CAL-P147) *before* the two worker clocks were
   discovered (CAL-P148). Bounded at **9.5e-7 per beat, 0.02% of the serve's**. The carried
   1-in-102 stands — but now because it was checked, not because it was assumed.
2. 🔴 **`pgrep -af` reports 6 pids where the truth is 2 — on the watcher's own singleton pattern.**
   On macOS BSD pgrep `-a` means *include ancestors*, not *show args*. The lane token is in the
   argv of the shell running the check, so the check matches itself. This is the lane's most
   protected invariant, and the standing remedy for "two watchers" is to kill one. See §2.

**Beat 18 landed during the session** (16:39:29Z) and was gauged before hand-off: **CLEAN, margin
43,458 ms, model agrees — 16 gauged, 16 agreements, 0 disagreements.** Window now **18 beats, 15
clean, 3 misses (4=B, 7=C, 15=B, all attributed)**, not re-baselined. Watcher 3016/3019 untouched,
zero restarts.

---

## 1. Carried instruments — all re-run

| check | result |
|---|---|
| watcher singleton | **2 pids** (3016/3019) unchanged, checked first thing and again after §2 |
| banker liveness | 75909/75911, heartbeat advancing `16:19:07 -> 16:22:10` |
| probe liveness | 37525/37527, heartbeat advancing, 8 samples |
| freeze | `git diff backend/` **0 bytes** at entry and exit |
| D13 / D22 | **both still unanswered**; nothing applied; `backend/` untouched |
| `cal-p144/window-beat-margins.py` | **exit 0 — 16 gauged, 16 agreements, 0 disagreements** (incl. beat 18) |
| `cal-p146/promotion-datapoint.py` | **exit 0** re-run after beat 18 — no RECOVERABLE beat unread; beat 14 still ⚫ permanent |
| `cal-p148/serve-phase-probe.py --report` | **exit 0** — 0 settled skips, verdict withheld, 3 backward moves |
| `cal-p145/refusal-register.py` | **exit 0** — no unregistered `RULE-DESIGN-*.md`; authored none |
| unattributed misses | **none** |

Tightest CLEAN margins unchanged: beat 11 by 4.3 s, beat 8 by 4.6 s, beat 16 by 7.3 s.

## 2. 🔴 The singleton check that reports a healthy watcher as a violation

Found by accident: `banker-capture-bound.py` reached for `pgrep -af` to read the banker's live
`--interval`, and got six pids for a two-pid process. Run on the **watcher's** pattern, same shell:

```
pgrep -f  "rebaseline.py --baseline-at"   ->  3016 3019                            2 ✅
pgrep -af "rebaseline.py --baseline-at"   ->  3016 3019 72103 72119 72452 84770    6 ❌
pgrep -lf "rebaseline.py --baseline-at"   ->  3016 3019 + full argv                2 ✅
```

`-a` is not "show args" — that is `-l`. On BSD it means **include pgrep's own ancestors in the
match**, and since the lane-unique token sits in the argv of the shell running the check, the
check matches itself. Nothing errors; the count is just wrong, and it is only wrong *upward*.

Why this is worth a section rather than a footnote: **`-a` is the natural reach.** You run
`pgrep -f`, get bare pids, and want to see which process you matched — `-af` looks like the
answer and on Linux procps it is. Here it converts the lane's one hard invariant (exactly one
watcher; two corrupt the log) into an apparent violation, and the directive's standing remedy for
a violation is to kill the duplicate. The failure mode is a session doing the *correct* thing with
a lying instrument and killing the real watcher.

Every process check in this session used `-f` to count and `-lf` to read args. The instrument uses
`-lf` with the reason in its docstring, and it is banked to memory as
`reference_pgrep_dash_a_matches_ancestors`.

## 3. The bracket's risk is the banker's, and the banker's was never the number carried

CAL-P148 measured that ~1 published census in 203 is never served by any worker, so ~1 promotion
bracket in 102 breaks. That got carried forward as the bracket's risk. It is one layer short: a
census being *served* does not bank it. The **banker** has to poll at an instant when some worker
is serving it, and that is a second, independent sampling stage.

Its empirical rate cannot answer this yet — the banker's `--watch` era is ~25 minutes old
(up 15:57:54Z) and contains exactly **one** census. n=1 is not a reading (CAL-P146). So it is
bounded from inputs the instrument **re-reads on every run** rather than from constants:

* **`CACHE_TTL = 3600`**, read out of `routes/calibration.py:35`. Tier 1 serves an admitted
  unmarked copy for the full TTL (`:1128-1164`); the only path that shortens a hold is a
  *stale-marked* payload, which is deliberately excluded from tier 1 (`:1133-1136`). So any census
  a worker pins is exposed by that worker for a full hour. **Read, not assumed** — a short or
  sliding hold would have changed the answer completely.
* **`--interval 180`**, read from the *running* banker's argv — not the script's default, which is
  240. A bound off the default would describe a banker that is not running.
* **2 clocks**, from the probe log's backward moves (a single memo cannot move backward).

20 polls land inside each hold; the banker misses only if all 20 land on a worker that never
pinned the census. Worst case (random balancing; round-robin is strictly better):

| quantity | value |
|---|---|
| P(banker misses a census some worker pinned) | **9.5e-7** |
| CAL-P148 serve miss / beat | 0.0049 (1 in 204) |
| banker layer as a share of the serve's | **0.02%** |
| bracket risk, carried | 0.0098 (1 in 102) — **stands** |

So the conclusion is unchanged and the reason for believing it is not. The instrument exits 0 now
and **exit 4** if the layer ever stops being negligible — proven, not asserted: at `--interval 900`
it goes red at 1275% of the serve's and prints the correct remedy (180 s). A guard with no
reachable red path is decorative, the mirror of CAL-P147's guard with no reachable green path.

The remedy it names is a **banker restart**, not a code change — deliberately. Nothing here
touches a frozen file and nothing here is proposed as work.

## 4. Deliberately not done

* **Landed nothing.** D13, D21, D22 remain Alex's and ungranted; the pre-builds are applied nowhere.
* **Did not re-baseline** — D22 has not landed.
* **Did not build the class-B cure** — frozen file, nobody has asked.
* **Did not re-derive the serve-skip question** — closed in CAL-P148; the probe runs only to catch
  a *settled* skip, and there is still none (0 settled, verdict withheld).
* **Did not add an entry to `PERMANENTLY_UNREADABLE`** to make anything green. Beat 14 stays ⚫.
* **Did not fire `bust`** on either route; **did not restart** the watcher, banker, or probe.
* **Did not extend the missing-loser census** — 45 cells stay PARKED as CAL-P122-1 (ruling 134).
* **Authored no `RULE-DESIGN-*.md`**, so the refusal register's reconciliation is unaffected.
* **Filed nothing to alex-inbox.** Both findings are lane-internal: one confirms a carried number,
  one is a tooling hazard. Neither is a decision and neither changes 913–917.

## Evidence

| file | what |
|---|---|
| `banker-capture-bound.py` | §3 — the bound; exit 0 live, exit 4 at `--interval 900`. ruff clean |
| `../cal-p148/serve-phase-log.jsonl` | the clock count the bound reads (backward moves) |
| `../cal-p147-renders/banker-log.jsonl` | the banker's 2 banks; the `--watch` era is 1 census |

## Running processes at hand-off

```
pgrep -f "rebaseline.py --baseline-at"      -> 3016 3019    watcher — NEVER restart, never duplicate
pgrep -f "CAL-P147-RENDER-BANKER"           -> 75909 75911  render banker
pgrep -f "CAL-P148-SERVE-PHASE-PROBE"       -> 37525 37527  serve-phase probe
```

Count with `-f`, read args with `-lf`. **Never `-af`** — see §2.
