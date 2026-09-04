# REPORT — lane1/109

**Stamped from `date`:** Fri 2026-09-04 **11:20Z / 04:20am PT**.
**PILLAR: TRUTH. SHIP: a 49ers fan stops seeing their team play twice in Week 1.** Kickoff Thu 9/10 — **six days.**

**Outcome: held the line. Nothing was due, nothing was mine, Week 1 is still 18. Nothing filed, no shot burned.**
This is the **ninth** consecutive session with that shape (101–109) and it remains the correct one.

---

## 1. Clock first — night two is 19h 27m out. Correctly NOT read.

`date -u` → `Fri Sep  4 11:20:09 UTC 2026`. The threshold is `2026-09-05T06:40Z`, poll no earlier than
**06:47Z**. **19h 27m out.**

**Eleventh** consecutive session in which reading the clock before the endpoint prevented a false
finding. §1.1's grading table in the queue is **still unused and still carries forward verbatim** —
101 through 109 have each declined to spend it early.

Nothing was polled. `anchor_schedule_sentinel` was not touched. The night-one baseline
(`2026-09-04T06:40:40Z`, examined 600/685, pages 6, `resumed_from: null`) is unchanged and is still a
baseline, not a finding.

**Saturday 9/5 after 06:47Z is the session that finally grades night two.** It is by far the
highest-value item in this queue and it is now one sleep away.

## 2. No PR to watch — and the one in flight is not lane1's.

PR 3006 is merged, deployed and closed (108). No lane1 PR is open.

The integrator **is** live and working right now — directive **160**, merging
`d15e9b989f1a2477f5307d3d3943c53290ac7def` under **CERT-907**. I checked whose it is rather than
assuming:

```
CODEX-CERT-LOG.md:660 | CERT-907 -- #2947 THE COLLISION CHECK DIES ON REAL POSTGRES ...
                      | lane1b/032 (#2947; first presentation) | GREEN -- TOKEN GRANTED
```

**`lane1b/032`, not lane1.** Under D39 lane1b owns matching receipts / golden set / link-change
history; lane1 owns twins, authority ids, the unique index and tennis sync. This merge is the
integrator's and lane1b's. I did not touch it, did not run gates on it, and did not comment.

Integrator log mtime check (the trap from §8 — a bare directive looks identical to a stall):

```
-rw-r--r--  1343  Sep  4 04:20  runner-logs/integrator-20260904-041848.log
```

**1 second old at read time.** Healthy lane mid-work, not wedged. That is now nine sessions
(101–109) where the mtime check correctly distinguished working from stalled. It has never once
been a stall.

⚠ Carried forward: **do not implement ordered (strictly-ahead) marker acceptance** in the sentinel
if a grader suggests it. 098's counterexample is in the arm's docstring —
`restarted_from_exhausted_cursor` walks the position backwards, so a marker that looks "ahead" can be
a stale claim missing that night's drift. Strict equality has no such hole.

## 3. Week 1 = 18. The destructive line held for the 19th session.

Branched on `'rows' not in d` first, per the trap. Query returned cleanly, `COUNT: 18`.

Both phantom rows re-confirmed **byte-for-byte**, unchanged from 108's read and matching the queue's
§3 table exactly:

| id | matchup | espn_id | stored clock | belongs | clock stolen from |
|---|---|---|---|---|---|
| `14780595` | SF @ LA **Chargers** | `401873124` | `2026-09-11 00:35:00+00` | 2026-12-18 | SF@LAR (`14632820`) |
| `14781140` | ARI @ LA **Rams** | `401873004` | `2026-09-13 20:25:00+00` | 2026-10-18 | ARI@LAC (`14780147`) |

Each phantom's clock is still byte-identical to its correct neighbour's (`14632820` also reads
`2026-09-11 00:35:00+00`; `14780147` also reads `2026-09-13 20:25:00+00`). Both collisions are
between the two Los Angeles clubs.

**18 means Alex has not run the attended apply.** Per the queue: I did **not** run it and did **not**
build a way around the gate. The generic rail `POST /api/admin/repairs/{name}` is gated on
`_check_admin_secret` only and remains a real bypass — **refused for the 19th consecutive session
(091–109).** The ask is `YOUR-TURN.md` DO 1; no second note was written and `YOUR-TURN.md` was not
edited.

The dry run was **not** re-run. 100 ran it at 10:1xZ on 9/4 and 102–109 have all confirmed the count
is unchanged; re-running it proves nothing new and costs a production call.

## 4. D48 — no shot owed, and none burned.

```
GET /api/health → commit: 1175d3ae
```

Production is **still `1175d3ae`** and this session shipped nothing, so 108's photograph is current
by the queue's own rule. **No shot burned.**

108's corrected real/phantom table stands and was not re-derived:

| slot | real game | phantom directly beside it |
|---|---|---|
| Sep 10 5:35 PM | LA **Rams** v SF 49ers | LA **Chargers** v SF 49ers |
| Sep 13 1:25 PM | LA **Chargers** v Arizona | LA **Rams** v Arizona |

The DB read above independently corroborates it: `14780147` is ARI @ LA **Chargers** (real Week 1),
`14781140` is ARI @ LA **Rams** (phantom, belongs 2026-10-18). **104's photograph table had this row
swapped; 108's correction is the right one. Do not "correct" it back.**

**Note for whoever runs next:** the integrator is merging CERT-907 right now, so master and then
production are likely to move off `1175d3ae` within this hour. **The next session probably DOES owe a
re-shot** — check `/api/health` before assuming 108's LOOK is still current.

## 5. #2869 — ninth consecutive correct silence.

```
2869 OPEN assignees=0 comments=4 labels=priority:p1 needs-agent area:backend matching-symptom
```

Unchanged: open, unassigned, four comments (099, 100, the authority lane's LOOK, and the dry-run
receipt). Held under D35 while #2693 is open — **file, do not build.**

I had nothing the issue does not already say. "It survived another deploy" is **not new** — 104
through 108 each considered exactly that and stayed silent, and 108 stayed silent across a real
deploy to a new sha. Adding a ninth "still there" would be noise on a p1 that is already fully
described.

Still on the issue and still the sharpest fact in it: **all six rows carry
`commence_time_source = 'espn'`, so on the two phantoms that stamp is false** — ESPN's own summary
says December and October. Something copied the sibling's clock and signed ESPN's name. Which rail
wrote it is untraced and unowned, and it is **diagnosis**, which LANE ROLES assigns to the
measurement lane. Parked, not chased.

Discarded theory, still discarded: the rows are *not* frozen by the parity rule in
`commence_time_write_authorized` (`event_registry.py:82`) — `event_registry.py:376` does compute and
pass `claim_is_same_record(...)`, so an exact-id ESPN claim may revise its own record.

## 6. Filed, not re-filed

#2447 (not lane1's), #2983, #2878, #2978, #2980, #2964, #2957, #2737, #2693, #2644, #2741, #2869 —
all unchanged. Nothing new filed this session, correctly.

## 7. What this session cost

Five production/CLI reads total: `date`, `/api/health`, one db-query, the integrator log mtime, and
two cheap greps (`gh issue view`, `CODEX-CERT-LOG.md`). No writes, no merges, no dry run, no
screenshot, no comment. An idle build lane is a signal, not a failure — it was not filled with
measurement.

## 8. New for the trap list

- **`gh issue view --template` without `--json` errors out** (`cannot use --template without
  specifying --json`). The `--template` workaround for jq-alternation failures still requires the
  `--json` field list alongside it: `gh issue view N --json a,b,c --template '...'`.
- **A live integrator directive can name a sha from a *sibling* lane with a confusingly close name.**
  `lane1b/032`'s CERT-907 sha appeared in the integrator log while lane1 had nothing in flight.
  Grep the ledger row for the `queue_id` before assuming a directive is yours *or* isn't — the
  lane1/lane1b prefix collision makes eyeballing unsafe.
