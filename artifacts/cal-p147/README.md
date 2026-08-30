# CAL-P147 — the next promotion is now banked by a timer, not by someone being awake

**TL;DR.** Nothing landed and the freeze holds — `git diff backend/` empty, `precompute_calibration.py`
untouched, no exception taken, D13/D22 still unanswered in YOUR-TURN §4 (file unmodified since
07:12 PT). The carried instruments were re-run and are green, and beat 17 arrived and classifies
CLEAN. The budget then went to the queue's item 2, which turned out not to be doable as written:

1. 🔴 **"Bank a render on the next promotion" cannot be executed by a session.** The next
   promotion is ~8 beats (~8 h) out, on the producer's cadence. The instruction requires someone
   to be awake at the right beat — and *that is exactly how beat 14 was lost*. So the answer is a
   timer, not vigilance: **`render-banker.py` is running unattended** (pids 75909/75911) and banks
   a scorecard render for every distinct census the API serves. Whichever beat the promotion lands
   on is then bracketed 1+1.
2. 🔴 **The guard could never have gone green again, and would have hidden the next miss.**
   `promotion-datapoint.py` accumulated *every* unreadable promotion including beat 14, whose loss
   is permanent — so it was pinned at exit 4 forever. A permanently-red guard is an ignored guard,
   and the thing it would then fail to announce is the *next* promotion being missed the same way.
   Beat 14 is now acknowledged as a closed permanent loss (printed loudly, with the argument for
   why nothing recovers it) and the exit code is reserved for a promotion that **can still be saved**.
3. ✅ **The whole chain is proven end-to-end on a planted control**, including the success path:
   banker-shaped renders on adjacent beats make the guard isolate exactly the promoted change.
4. 🔴 **The serve lags the producer, and it is not yet established that it exposes every beat.**
   At 15:51Z the API served census 14:38:38 (beat 16) while the producer was already at 15:37:22
   (beat 17), and it was still serving 14:38:38 at 15:58Z — past the 1 h cache. Measured, flagged,
   not guessed at; `--report` prints beat coverage so the next session reads it rather than assuming.

Window: **17 beats, 14 clean, 3 misses (all attributed)**, still arithmetically lost, **not
re-baselined**. Watcher 3016/3019 untouched throughout, 11 h+, zero restarts.

---

## 1. Carried instruments — all re-run

| check | result |
|---|---|
| watcher singleton | pids **3016/3019** unchanged, verified BEFORE anything ran, and re-verified after every process action in §3 |
| freeze | `git status --porcelain` clean of `backend/` at entry and exit; `git diff backend/` **0 bytes** |
| D13 / D22 | **both still unanswered**; YOUR-TURN.md mtime 07:12 PT. `land-12cal.sh` not run. Nothing applied. |
| `cal-p144/window-beat-margins.py` | **exit 0 — 15 gauged, 15 agreements, 0 disagreements.** Beat 17 gauged and agrees (CLEAN, cleared by 47.0 s) |
| `cal-p145/refusal-register.py` | **exit 0** — no unregistered `RULE-DESIGN-*.md`; this session authored none |
| `cal-p146/promotion-datapoint.py` | exit 4 on entry (as banked), **exit 0 after the §2 amendment**, exit 4 again on a planted new promotion |
| unattributed misses | **none**. Beats 4 (B), 7 (C), 15 (B) all attributed |

**Beat 17** — `2026-08-30T15:37:22`, CLEAN / REPUBLISH, rebuild **33/128**, `beats_to_publish: 8`.
Progress is ~12 units/beat, so the next MEASUREMENT beat is ~8 beats out. Nothing in it disagrees
with the margin model.

## 2. The guard could not go green, and that was the dangerous part

`promotion-datapoint.py` appended beat 14 to `unreadable` on every run. Beat 14 is unrepairable:
closing its bracket needs a render of the payload served at beats 13 and 15, both censuses have
been evicted from the serve cache, and the producer cannot be asked to re-serve them — `?bust=1`
is **gone from the public route**, and the admin variant (`/api/admin/calibration/mce?bust=true`)
**QUEUES the heavy task**, which would inject a phantom producer run into the very beat log the
window is measuring. So exit 4 was permanent.

That is worse than cosmetic. The guard's *entire job* is to announce a promotion that is about to
be lost. Pinned red, it announces that on every run, forever, indistinguishably from the days when
nothing is wrong — so the run where it means it reads exactly like the 200 runs where it didn't.

The amendment splits the two:

* `PERMANENTLY_UNREADABLE` — an explicit dict, keyed by beat, whose value is *the argument that no
  future session can recover it*. Beat 14's entry spells out the evicted censuses and the two
  reasons the producer cannot be asked to re-serve. The docstring states the only admissible
  reason for an entry, and that "unbracketed **so far**" is not it: leave those red.
* Permanent losses print with ⚫ and the full reason, and are excluded from the exit code.
* Anything else prints 🔴 and returns 4.

**Both directions fired, plus the success path** (a guard nobody has seen pass is as untested as
one nobody has seen fail — CAL-P145's lesson, and here the *green* path was the untested one):

```
live state, beat 14 acknowledged            -> EXIT 0   permanent loss still printed in full
planted beat 18 promotion, no renders       -> EXIT 4   "no bracket" — and the ⚫ does NOT mask it
planted beat 18 + renders on beats 17,18    -> EXIT 0   "✅ bracket is adjacent — what moved IS
                                                        the promotion: counts.cells_at_bar 29 -> 31"
```

The third line is the one that matters: it is the shape the banker produces, and it shows the
guard isolating exactly the one planted change out of a 136 KB payload. The control ran in a
scratch tree (`/tmp/cal147-control`) with its own copy of the script and a *copy* of the window
log — **the live log was never written to**, because the watcher owns that file.

## 3. The banker

`artifacts/cal-p147/render-banker.py` — ruff clean, `--once` / `--watch` / `--report`.

Every `--interval` (180 s) it GETs `/api/calibration`, and if the payload's `generated_at` is one
it has never banked, scores it offline into `artifacts/cal-p147-renders/scorecard-<census>.txt`.
Renders land **one level under `artifacts/`** because the guard discovers them with
`artifacts/*/scorecard*.txt` — nested, they would be banked and then never found.

What it deliberately does not do:

* **Never perturbs the producer.** Poll and take what is served; see §2 on why `bust` is off limits.
* **Never passes `--record`**, so the CAL-P128 sigma ledger is not written.
* **Cannot be mistaken for a second watcher** — its name cannot match
  `pgrep -f "rebaseline.py --baseline-at"`, and it carries a lane-unique token
  (`CAL-P147-RENDER-BANKER`) so it can be pgrep'd and killed without a pattern that hits another
  lane. Verified before killing: the token matched exactly its own two pids.
* **Heartbeats.** `banker-heartbeat.json` is rewritten atomically each cycle. Without it, "alive
  and polling" and "wedged four hours ago" look identical to the next session — across an 8-hour
  unattended stretch that is the difference between having the datapoint and not.

**Two defects found by running it, not by reading it:**

* Its dedup used a strict `json.load`, but sessions bank renders as *JSON followed by the printed
  board*. So it saw 3 of the 8 censuses already on disk, re-banked one it already had, and would
  have re-scored the same census every 3 minutes forever. Fixed to the prefix decoder the sibling
  instrument already uses.
* `--report` first compared beat and render stamps with string equality and reported **0/17
  covered** while the sibling mapped five renders. The beat's `generated_at` is the *watcher's*
  observation and the render's is the *payload's* — beat 16 differs from its own render by 0.5 s.
  Fixed to the same 5 s tolerance. Now reports 4/17, which reconciles with the sibling exactly.

Both are the same shape as CAL-P144's lesson: an instrument that has never run its default path is
a document.

## 4. 🔴 The serve lags, and may skip

This is measured and unresolved, and the next session should read it rather than assume:

```
15:51Z  producer at beat 17 (census 15:37:22)   API serving census 14:38:38  (beat 16)
15:58Z  producer at beat 17                     API serving census 14:38:38  (still)
```

The serve is behind a 1 h cache and beats run 57–77 min apart, so a census could in principle be
superseded before it is ever served. If that happens the banker cannot capture it — polling faster
does not help, because the payload was never exposed. **It is not established either way yet.**
`--report` prints per-beat coverage; after a few more beats the answer will be readable off it. If
the serve does skip, the honest conclusion is that some promotions are unreadable no matter who is
awake, and that belongs in front of Alex rather than being worked around.

## 5. Deliberately not done

* **Landed nothing.** D13, D21, D22 remain Alex's and ungranted; the two pre-builds are applied
  nowhere; `land-12cal.sh` was not run.
* **Did not re-baseline** — D22 has not landed.
* **Did not build the class-B cure** — still touches the frozen file, still nobody has asked.
* **Did not extend the missing-loser census** — 45 cells stay PARKED as CAL-P122-1 (ruling 134).
* **Did not fire any `bust`**, on either route, for the reason in §2.
* **Did not touch the live window log**, and did not restart the watcher.
* **Authored no `RULE-DESIGN-*.md`**, so the refusal register's reconciliation is unaffected.

## Evidence

| file | what |
|---|---|
| `render-banker.py` | §3 — the banker; `--report` for beat coverage |
| `../cal-p147-renders/` | banked renders, `banker-log.jsonl`, `banker-heartbeat.json` |
| `banker-stdout.log` | the running process's own output |
| `../cal-p146/promotion-datapoint.py` | §2 — amended; `PERMANENTLY_UNREADABLE` carries the argument |
| `control-planted-new-promotion.txt` / `control-bracketed.txt` | §2 — the two planted controls |
| `window-beat-margins-p147.txt` | §1 — 15/15, exit 0 |
