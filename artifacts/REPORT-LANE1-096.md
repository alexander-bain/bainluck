# lane1/096 — the sentinel can close, the follow-ups are discharged, the 49ers still play twice

**PILLAR: TRUTH.** Session Fri 2026-09-04, 07:32Z → (see stamps below). Branch
`lane1/096-the-window-pass-is-what-closes-2983`, PR #2987.

**SHIP: a 49ers fan stops seeing their team play twice in Week 1.** Kickoff Thu 9/10 — six days.
Not delivered this session, and the reason is the same as the last five: the repair is behind a
token lane sessions are deliberately not issued. Everything that *could* be built without it, was.

---

## 1. What shipped (built, pushed, in cert)

Three commits on one branch. All are read-only, no migration, no data write.

| sha | subject |
|---|---|
| `ec7c0e7a` | #2983 — the window PASS is what closes the anchor-schedule sentinel, not one run |
| `fef8b4e7` | the two CERT-890 follow-ups — measured cost in `/docs`, no stale zero tail |
| `69c9ac98` | CERT-896 repair — bind the pass marker to the cursor it was written beside |

Certs: **CERT-896 BLOCK** (first presentation, real finding) → **CERT-898** staged as the repair.

### 1a. #2983 — the sentinel could file and could never close

`complete = stopped_by is None and not resumed` gated the GREEN close, and neither arm is
satisfiable at this population. A fresh run cannot cover 685 rows in a 300s deadline (night one
measured 600/685, `stopped_by: deadline`, >0.50 s/row); and the night that *does* reach the end
gets there by resuming. Coverage was never broken — nights 1+2 see the window, which is what
CERT-843's continuation is for. **Nothing recorded the union.**

The fix tracks a **window pass** beside the position. A run starting at the oldest row begins a
pass; a resumed run continues it; a chain reaching the end with its pass intact has seen the
window, and that is what may close. `_sweep` now reports `reached_window_end` (a fact about the
run); the caller turns it into `complete` (a fact about the chain).

Three things void a pass, each failing toward "cannot close", each on the operator line:

| void | operator line |
|---|---|
| broken chain (no marker to continue) | `CHAIN-BROKEN` |
| expired, `MAX_PASS_AGE_SECONDS` = 3d | `PASS-EXPIRED` |
| drift seen anywhere in the chain | `PASS-SAW-DRIFT-EARLIER` |

**Two design points worth carrying forward, because both are traps I had to build past:**

- **The drift-seen rule is not in #2983's design note, and without it the fix is worse than the
  bug.** Night one files five drifting rows; night two sweeps a clean tail and reaches the end; the
  naive version closes an issue whose five rows are still wrong. GREEN is the pass's verdict, not
  the last run's.
- **Expiry voids the CLAIM and never the POSITION.** Clearing the continuation on expiry would
  restart the sweep at the oldest row every cycle, so a window that outgrew three nights of budget
  would never have its tail examined — CERT-843's blind spot with extra steps. The cost of that
  choice is that such a window stops closing; the cost is paid *visibly*, via `PASS-EXPIRED`, which
  is the loud version of the failure #2983 reported as a silent one.

### 1b. CERT-896 — the BLOCK was right, and it is repaired

> a transient marker-write failure after a drift slice advances the cursor but leaves the older
> clean marker … emits a false GREEN close after the prior night filed RED.

Reproduces exactly. The marker and the continuation are two Redis keys, cannot be written
atomically, and **both writes swallow their exceptions**:

| night | what happens | store afterwards |
|---|---|---|
| 1 | clean front slice, truncates | cursor `c1`, marker `{clean, c1}` |
| 2 | finds drift, truncates; the `drift_seen: true` write **fails** | cursor `c2`, marker still `{clean, c1}` |
| 3 | clean tail, reaches the end | `pass_drift_seen` False → **false GREEN** |

The BLOCK offered two repairs. I took **binding**, not ordering-as-guarantee, and the reason
matters: "require marker persistence before cursor advancement" cannot be made airtight across two
non-atomic writes — it narrows the window without closing it. Binding *detects* the divergence,
which is the only guarantee actually available. The marker now records the continuation it was
written beside and a run refuses any marker whose cursor is not the position it is resuming from.
Ordering was implemented **as well**, as defence in depth, and is asserted rather than described.

### 1c. The two CERT-890 follow-ups, discharged

- `LANE1-094-OPENAPI-COST-DESCRIPTION` — `/docs` advertised ~0.2s per ESPN call after #2953 re-sized
  every constant on the measured ~0.59s. Wrong by 3x, and **the one reader who could still act on
  the stale figure was the only one not told.** Guarded by reading the description off the live
  signature.
- `LANE1-094-BUDGET-TAIL-COUNT-COPY` — `MORE (0 after this page; pass cursor=…)` told an operator
  in a hurry to stop paging one page early: the abandoned tail `budget_cut_tail` exists to prevent,
  reinstated in the copy. Now "at least 1 after this page" when the count is stale, the real number
  when it is not.

---

## 2. Evidence

- **193 focused tests green**: sentinel (31), rail, paging, budget-2953, undo-D51, startup, beat
  wiring. Full suite is CI's under D40.
- **Six ablations**, each killing exactly its own guard and nothing else:

  | ablation | fails |
  |---|---|
  | old `complete` rule restored | the 3 close tests |
  | `green = complete` (drop drift-seen) | the drift test |
  | drop `pass_expired` from `complete` | the age test |
  | expiry also clears the position | the CERT-843 regression test |
  | unbind the marker from its cursor | the three-night marker-write-failure test |
  | reverse the write order | the write-order test |

- **All 21 pre-existing sentinel tests pass unchanged under every ablation.** That is the ablation
  claim that matters: the old suite could not catch this class, because every assertion in it is
  about a *single run's* verdict.
- Residue scan CLEAN (550 needles, 2,954 broad checks, exit 0). black + ruff clean on every file
  this touched that was clean on master. **Not reformatted:** `app/tasks/__init__.py` and
  `app/tasks/reconcile_anchor_schedule.py` are pre-existing not-black-clean, and
  `admin_events.py` carries a pre-existing unused `selectinload` import — black reformats the whole
  file, so a docstring change is not a licence to touch 200 unrelated lines.

---

## 3. Week 1 is still 18 — Alex has not run the repair

Counted first, branching on `'rows' not in d` before reading any number.

```
COUNT: 18
14780595  San Francisco 49ers @ Los Angeles Chargers  2026-09-11 00:35Z  401873124
14632820  San Francisco 49ers @ Los Angeles Rams      2026-09-11 00:35Z  401872657
14780147  Arizona Cardinals   @ Los Angeles Chargers  2026-09-13 20:25Z  401872926
14781140  Arizona Cardinals   @ Los Angeles Rams      2026-09-13 20:25Z  401873004
```

**The line held for the seventh session.** `_check_admin_destructive`
(`app/routes/admin_utils.py:151`) says in as many words that lanes are not issued
`ADMIN_TOKEN_DESTRUCTIVE` *so that a lane physically cannot run these routes*. The generic repair
rail `POST /api/admin/repairs/{name}` is gated on `_check_admin_secret` only and IS a real bypass;
refused again. The ask is already `YOUR-TURN.md` DO 1 and no second note was written.

### D48 mystery shop — the duplicate is the second and third card on the page

`artifacts/lane1-096-nfl-week1-49ers-twice-phone.png`, phone width (390), production
`/sport/americanfootball/nfl`, 08:07Z.

Both 49ers cards are **adjacent, above the fold, both stamped `Sep 10 5:35 PM`, both `Netflix`**:

```
Sep 10 5:35 PM   Los Angeles Chargers 57%  /  San Francisco 49ers 43%   Netflix
Sep 10 5:35 PM   Los Angeles Rams     65%  /  San Francisco 49ers 35%   Netflix
```

New detail worth having: the upcoming list is capped — *"Showing the next 8 — more exist."* So the
**Cardinals** duplicate (Sep 13) is **not** on this page at all, and the SF pair is. The one a fan
actually meets is the SF one, and it is maximally visible. That raises the value of the fix and
lowers the value of any "how many duplicates are there" framing.

---

## 4. What 096 did NOT do, and why

- **Night two (Sat 9/5 06:40Z) was not read** — it is ~23h after this session. Item three is
  carried to 097 with its prediction amended (below).
- **#2878 not started.** p1, `needs-agent`, lane1's under D35 — but **#2693 is still OPEN**, so it
  is FILED, NOT FIXED. Unchanged.
- **`LANE1-093-BONDAR-CARD-LOOK` not closed.** Still one leg short; 095's finding stands (accents
  are stripped in our own data, so a tour-page card cannot prove it). A `tennis_*_us_open` card is
  the cheapest close and was not reached.
- **The drain was not re-run.** It is at its floor at 5; running it "to check" is the mistake the
  restock names.

---

## 5. The night-two prediction is now CONFOUNDED — by this fix, deliberately

Recorded on #2983 rather than left to be read against a moved target. If #2987 deploys before
06:40Z Sat, night two runs the **new** code.

What still holds either way: `resumed_from` non-null, `restarted_from_exhausted_cursor: false`,
`examined ≈ 85`, `pages: 1`, `stopped_by: null`, `continuation: null`, **`complete: false`**.
The falsification rules are unweakened — `resumed_from: null` or
`restarted_from_exhausted_cursor: true` is still a different and more serious bug (CERT-843
reopening), still its own issue.

**What changes is the REASON `complete` is false.** New payload fields disambiguate:

| field | night two, new code |
|---|---|
| `pass_open` | `false` (the legacy bare cursor has no marker beside it) |
| `pass_started_at` | `null` |
| `pass_expired` | `false` |

If night two returns `pass_open: true` while `resumed_from` is non-null, **the migration path is
wrong and that is a finding.**

**The first night that can actually close is night four (Mon 9/7).** Night 2 = broken chain, clears
both keys. Night 3 = fresh pass, truncates. Night 4 = resumes, reaches the end, `complete: true`.
That sequence is the migration guard working, not a defect.

---

## 6. Traps 096 hit

- **A cert can be graded before you finish the session.** CERT-896 was staged at 07:55Z and BLOCKed
  at 07:55Z — by the time I looked to add the follow-up commits, the verdict was already banked.
  **Check the block's `status:` before assuming a staged sha is still yours to amend.**
- **A branch cut from an artifacts branch is not cut from master.** `lane1/094b-artifacts` was 94
  files behind; an edit made against its `app/tasks/__init__.py` was against a stale file. Compare
  the *touched paths* to `origin/master` before branching (`git diff --stat origin/master HEAD --
  <paths>`), then `git checkout -b <new> origin/master` carries the identical ones cleanly.
- **A guard can trip on its own explanatory prose.** `assert "0.2s" not in description` failed
  because the new description explained that it used to say ~0.2s. The history belongs in a code
  comment; the description carries the number only.
- **Two Redis keys are a distributed write.** Both `setex` calls swallow exceptions by design, so
  "the write failed" is a state to survive, not to exclude. Ordering narrows it; only binding one
  key's value to the other's detects it.
- Standing and re-confirmed: black reformats the WHOLE file — check whether a file was already
  dirty **on master** before letting black touch it. `look.sh` at `SHOT_W=390` returns a 65,174px
  image; crop with PIL before `Read`.
