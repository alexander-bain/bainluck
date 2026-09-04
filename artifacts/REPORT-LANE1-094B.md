# lane1/094 (continuation) — the sentinel fired, and it found the 49ers phantom by itself

**PILLAR: TRUTH. SHIP: a 49ers fan stops seeing their team play twice in Week 1.**
Kickoff Thu 9/10 — six days.

Session ran 06:09Z–07:0xZ Fri 2026-09-04 (11:09pm PT Thu onward). This window continues the
094 session that ended before 06:40Z with `REPORT-LANE1-094.md` §5.1 unwritten.

---

## 0. TL;DR

| item | state |
|---|---|
| **Item One — the 06:40Z sentinel** | **DISCHARGED.** It fired on time, ran 5m18s, filed one issue (#2978), and did not close anything on a partial sweep. §1 |
| **The sentinel re-derived the ship** | **Both Week-1 phantoms found independently, from ESPN, night one.** §1.3 |
| **Item Two — Week 1** | **18.** Alex has not run it. Ask is live and correctly placed as `YOUR-TURN.md` DO 1. §2 |
| **CERT-890** | **GREEN — TOKEN GRANTED** for `07ca1622` (my HEAD). Gates 13+18 pass, merge is conflict-free, **queued with the integrator as directive 143**. §3 |
| **#2980** | **New.** task-metrics calls a *running* task hard-killed. It nearly cost me a wrong finding tonight. §4 |
| **#2978** | Triaged into 4 classes with a comment — they are not 25 bugs. §1.3 |
| **Owed** `LANE1-093-BONDAR-CARD-LOOK` | Still one leg short; 095 has a dated, specific chance. §5 |

---

## 1. ITEM ONE — discharged, from the run

**The loop is broken.** 090 was restocked four times and was correct every time: the sentinel's code
only reached production at ~8pm PT Thursday, and sessions 091/092/093 all ran between the deploy and
the first firing. There was never a run to read. This session started at 06:09Z, held the window
open across the 06:40Z fire, and read it.

### 1.1 Before/after control, so "it ran" is not an assumption

`date -u` first, per the restock. Then the ledger endpoint
(`/api/admin/celery/task-metrics/anchor_schedule_sentinel`) was polled **before** the fire and read
`{"status":"no_data"}` at **06:13:39Z** and again at **06:38:41Z**. Anything present afterwards is
unambiguously the first firing, not a leftover.

Wiring was confirmed *in the deployed tree*, not just in mine: `git show origin/master:...` carries
`crontab(minute=40, hour=6)` on the `heavy` queue, and production was serving `708afee7` (which
contains it) with 2,672s uptime. A wired beat is not a working one — but an unwired one cannot fire,
and that was worth eliminating first.

### 1.2 The three questions, answered from the run

**Verdict.** Not "no exception":

```
terminal: "partial"    complete: false    stopped_by: "deadline"    applied: false
last_verdict: "unverified"    last_verdict_reason: "not_enforced(partial:terminal:partial)"
```

Started **06:40:40Z**, succeeded **06:45:58Z**, `last_duration_ms: 317588`.

**Filing — one deduped issue, correctly.**
`filing: {fingerprint: "anchor-schedule-drift", marker: "anchor-schedule-sentinel-fingerprint",
action: "filed", issue: 2978}`. One issue, labelled `type:bug` / `priority:p1` / `alert-intake` /
`area:backend` / **`matching-symptom`** (D35-compliant), and its body leads with
`partial: CONTINUES-TOMORROW examined=600/685`. **It filed and it did not close** — correct, because
`complete: false`. A truncated sweep closing an issue was the named hazard and it did not happen.

**Budgets — the documented model was validated by measurement.**

| bound | value | outcome |
|---|---|---|
| inner deadline | 300s | **bound first** — `stopped_by: deadline` |
| page cap | 12 | slack — used **6** |
| soft limit (heavy) | 840s | 317.6s, ample |
| ahead of the 07:05–07:50 block | — | done 06:45:58Z ✓ |

The module docstring predicted "~5 pages fit the deadline and the page cap stays slack" and
"~500 rows a night". Actual: **6 pages, 600 rows, deadline-bound, cap slack.** I went in expecting to
find the comment inverted and it is not — the design held on contact.

**One real wrinkle:** `elapsed_seconds: 314.4` **exceeds** the 300s deadline, because the deadline is
checked *between* pages, so the final page overshoots by up to one page-duration (~59s worst case).
Harmless against 840s, but it is an overshoot, and anyone tightening the soft limit toward 300s must
account for it.

**`authority_dark` did not happen.** The restock was right to call it a FINDING rather than a pass —
it simply did not occur. `no_answer: 28` of 600 (4.7%) is per-row silence, not a dark authority.

### 1.3 What it found — and it found the ship

`eligible: 685`, `examined: 600`, `by_verdict: {agrees: 546, authority_moves_us: 25,
teams_disagree: 1, no_answer: 28, refused_*: 0}`.

**The sentinel independently re-derived both Week-1 phantoms on its first night, from ESPN, with no
knowledge of them:**

| event | anchor | ours | ESPN says | drift |
|---|---|---|---|---|
| `14780595` Chargers v 49ers | `401873124` | Sep 11 00:35Z | **Dec 18** | 98.03d |
| `14781140` Rams v Cardinals | `401873004` | Sep 13 20:25Z | **Oct 18** | 34.99d |

That is the strongest evidence yet that the pending Week-1 correction is aimed at the right two rows:
it now has two independent derivations (the reconcile dry run, and a sentinel that was not looking
for it).

I triaged the 25 into four classes on #2978 rather than letting them read as 25 equal bugs:

- **Class A — midnight-ET placeholder, 12 of 25 (48%).** `ours` is exactly `04:00Z`/`05:00Z`; all
  sub-day. The anchor and the game are right; only the time is a fill-in. One mechanism, half the list.
- **Class B — a swapped pair, 2 rows.** `15297957` and `15298413` hold **each other's kickoff times,
  exactly**. That is two rows crossed, a matching signature, not drift.
- **Class C — wrong-game anchors, 6 rows (≥7d).** The #2804 class, including both Week-1 phantoms.
  ⚠️ Two of the six (`15175988`, `14870016`) have an **authority-side** midnight placeholder — where
  ESPN itself has not published a time, "authority says" is weaker than it looks. Do not auto-move those.
- **Class D — sub-hour, 4 rows.** Plausibly genuine broadcast changes.

**85 eligible rows were never examined.** `continuation: "2026-11-28T00:00:00+00:00|15197566"` is
saved, so tomorrow resumes there rather than rescanning from the oldest row — the CERT-843 blind-spot
design, working. **The 25 is a floor, not a total.**

---

## 2. ITEM TWO — Week 1 is still 18

Counted first, branching on `'rows' not in d` before reading anything. **18 rows**, both phantoms
present, unchanged from 093 and from 094's first window.

Per the restock I did **not** run the apply and did **not** build a way around the gate. The generic
repair rail (`POST /api/admin/repairs/{name}`, `_check_admin_secret` only) remains the available
bypass and remains refused — 091 refused `heroku config`, 092 direct-Celery, 093 and both 094 windows
this one.

**I did not write a fourth note, and I checked why before deciding.** `YOUR-TURN.md` §1 carries the
ask as **DO 1**, first item, ~3 minutes, pointing at `alex-inbox/lane1-091-…`, with the refusal
explained and the undo named. The ask is live and correctly placed; another note would be noise. The
unreconciled authority question (D51 says the Week-1 fix is lane1's; the mechanism says it is not)
stays open in `NOTE-TO-FABLE-FROM-LANE1-092-…` — **this is the one line.**

### D48 shop — the bug, photographed

`artifacts/lane1-094b-shots/nfl-week1-49ers-twice-phone.png`, phone width (390×844), 06:20Z,
`/sport/americanfootball/nfl`. Two **adjacent** cards, both `Sep 10 5:35 PM`, both badged Netflix:

- Los Angeles Chargers 57% / **San Francisco 49ers** 43%  ← the phantom
- Los Angeles Rams 65% / **San Francisco 49ers** 35%  ← the real fixture

A fan sees the 49ers kick off twice at the same minute, and **nothing on either card distinguishes
the fake from the real one.** Six days out. This is the ship, in one frame.

---

## 3. CERT-890 — granted, gated, and handed to the integrator

`07ca162244fe57522ee403e9428c2d385baab3b2` — my HEAD — is **GREEN, TOKEN GRANTED** (05:48Z, first
presentation, zero strikes; 192/192 focused gates, full exact-SHA CI green).

Both merge gates run and pass: gate 13 (`TOKEN GRANTED` row exists) and gate 18 (no later row names
CERT-890 after "supersedes"). `git merge-tree` against current master is **conflict-free**.

**I did not merge it, and that is deliberate.** The integrator lock is HELD by a *live* session
(integrator/135, pid 96453 alive, actively draining), and its watcher has **already queued my sha** as
`runner-inbox/integrator/143-merge-07ca1622….md`. Ruling 017 puts the master push behind that lock;
contending for it against a live holder to save an hour is how two writers land on one tree. Master
moved 708afee7 → b6be5b88 during the session, so 135 is working the queue and 143 is in it.

**Consequence for 095:** CERT-890's owed POST-DEPLOY check is **not discharged** — it needs the
deploy. When `07ca1622` is on master and production's `/api/health` commit reflects it:

```
POST /api/admin/events/reconcile-anchor-schedule?sport=americanfootball_nfl   # no limit
```
must return JSON with **`examined: 25`** and a resumable cursor (the old default would have 500'd).
Two non-blocking follow-ups also remain named: `LANE1-094-OPENAPI-COST-DESCRIPTION`,
`LANE1-094-BUDGET-TAIL-COUNT-COPY`.

---

## 4. #2980 — the metric that called a healthy run dead

**This nearly cost me tonight's finding, and it is the reason to read a number's derivation before
believing it.**

Polled 212s after the fire, the ledger said:

```
"hard_kills_24h": 1, "successes_24h": 0, "health": "critical",
"health_reason": "1 runs started, none reached an end handler — hard-killed (memory / hard time limit)"
```

The obvious write-up was "the sentinel's first firing was hard-killed" — a clean, dramatic, **false**
finding. What stopped it: 212s is *inside* the task's own 300s budget, so a run with no end handler
yet is simply still working. Re-polled at 06:52Z: `successes_24h: 1`, `hard_kills_24h: 0`,
`health: healthy`, full summary.

Cause, stated in the code at `app/routes/admin.py:1927`: **`hard_kills_24h = starts - terminals`.**
There is no third state for "in flight", so every long-running task is a hard kill until it finishes.
The count alone would be a wart; the damage is that `health_reason` upgrades the arithmetic into an
**assertion of cause** — it names memory and the hard time limit for a process that is merely busy.

**093's detached watcher walked straight into it.** It breaks its poll loop on the *absence* of the
string `"no_data"` — and at 06:43:03Z the ledger already carried `starts_24h: 1`, so it broke on the
first poll, snapshotted the in-flight run, and exited `DONE` **two minutes before the task finished**.
So `artifacts/lane1-090-anchor-sentinel-run.detached.json` holds the **premature, wrong** reading
(`hard_kills_24h: 1`, `health: critical`, no summary). ⚠️ **Do not cite that file** — the real result
is the 06:52:37Z re-poll recorded in §1.2. "Has a row" is not "has finished"; the watcher needed a
terminal state as its break condition, not merely non-emptiness. Same class as gotcha #53.

The anchor sentinel takes ~5 minutes by design, nightly. As written this endpoint will report
`critical` / "hard-killed" **every night for five minutes**, indistinguishable from the real kill the
field exists to catch. Filed **#2980** (`type:bug`, `area:admin-ops`, `priority:p2`) with a fix that
adds an `in_flight` state and an acceptance test asserting **both** arms — so it cannot be satisfied
by just silencing the alarm. Gotcha #53's class: the ambiguous shape needed a second signal.

---

## 5. Still owed

**`LANE1-093-BONDAR-CARD-LOOK`.** 094's first window discharged the intent on three legs (the render
path photographed live; all four newly-resolved names fetched 200 at the CDN; the accent rendering
correctly) and was honest that the missing leg is a *newly-resolved accented player on screen*, because
Bondár is out of the draw.

**095 has a dated chance:** Iva Jović has fixture `15304374`, **Sat 00:00Z**. If it is on screen,
60 seconds closes this properly.

---

## 6. Traps this window added

- **A derived count cannot see "in flight."** `starts - terminals` calls every running task dead.
  Before believing a health string, check the poll's age against the task's own budget. (#2980)
- **The integrator lock can be held by a live session with your sha already queued.** Check
  `runner-inbox/integrator/` for a `*-merge-<sha>.md` before deciding you must merge it yourself —
  the watcher may have done the routing already, and then waiting *is* the correct action.
- **A restock that has been wrong four times may have been right four times.** 090's reason
  (deploy at ~8pm, every session after it but before 06:40Z) was structural, not sloppiness. Read the
  stated cause before treating a repeat as a slip.
- **`git merge-tree` needs the merge base explicitly** to give a usable conflict read here.
- Re-confirmed: `look.sh` defaults to 1280 wide — `SHOT_W=390 SHOT_H=844` for D48; crop with PIL
  before `Read` (tonight: **64,644px** tall); `cd backend &&` persists into later Bash calls;
  `area:matching` is not a label (used `area:admin-ops`).
