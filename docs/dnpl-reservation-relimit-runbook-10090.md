# DNPL reservation sizes: limits-only change and rollback (#10090)

PILLAR: TRUTH / FORMATTING. SHIP: busy live games in the "Other" reservation
(tier 3/4 and unknown leagues) stop having their sub-second price previews
refused for want of a slot, so their prices reach the page through the preview
instead of waiting for the committed stamp.

This is a prepared procedure, not a grant. Changing the sizes needs Alex's
product OK (it shrinks the Tier 1/2 reservations), the attended
`LIVE_BLEND_PREVIEW_RESERVATIONS` change, and Integrator custody of the stop
window. Nothing here runs automatically.

## Why a size change is a new incarnation

The six sizes are part of the policy fingerprint
`v1-six-hour-<league-map hash>:<sizes>`. A ready v3 authority binds that
fingerprint in three places: the PostgreSQL `dnpl_authority` row, the Redis guard
token, and the ledger's `reservation_policy`. A producer whose configured sizes
differ refuses to bind (`ready authority reservation policy mismatch`) and keeps
committed-only delivery. A guarded command with another fingerprint returns
`policy_mismatch` and halts that registry. So the sizes are never edited in
place. The supported change is the existing reviewed recovery sequence:

1. `prepare` a fresh incarnation whose fingerprint differs **only** in its sizes;
2. `arm`, `initialize`, `ready` (a new, empty namespace in the other slot);
3. `retire` the predecessor namespace.

`backend/scripts/reservation_relimit_plan.py` builds those two operator plans
and refuses anything that is not a limits-only change. It is offline (no
network, database or Redis). The operator command
`python -m app.services.dnpl_activation_operator execute-plan` keeps its writer
verifier, desk hold, single-send records and fences unchanged. No new mutation
primitive is introduced.

The legacy tooling in `backend/scripts/reservation_cutover/` is not reused. It
pins the pre-reservation module bytes and the legacy `live:blend_preview:ledger`
namespace, and it STOPs when policy fields exist, which they now do. Its
coordinated stop is the same in spirit: every ledger writer is stopped, then the
v3 operator's writer verifier proves the stopped formation on both apps before
each step.

**What a new incarnation means for readers.** The new ledger starts empty. Every
event is re-admitted on its next price change, under the new sizes. The v3
contract's new-domain rule applies: old previews are not revived in the new
namespace (`docs/contracts/dnpl-authority-v3-activation.md`). Committed frames
are unaffected.

## Allocation

Default proposal (Speed): `128,48,96,48,160,32`, which is T1 active/upcoming,
then T2 active/upcoming, then Other active/upcoming. The total is 512.

Measured peaks: Wed 10/28 evening to Thu 10/29 afternoon, from the retained
worker-ws reservation receipts (authority 1952Z return).

| Bucket | Today | Proposal | Measured peak |
| --- | ---: | ---: | ---: |
| T1 active | 192 | 128 | 14 |
| T1 upcoming | 64 | 48 | 17 |
| T2 active | 128 | 96 | 16 |
| T2 upcoming | 64 | 48 | 15 |
| Other active | 48 | 160 | 48 (full all day) |
| Other upcoming | 16 | 32 | 16 (full most samples) |

**Is T2 active 96 safe for an NFL Sunday?** For the NFL itself, yes: the NFL is
**Tier 1**, not Tier 2. A full Sunday 1 pm ET slot is at most about 14 games,
far below 128. Tier 2 on a Sunday is mostly European soccer and MLS. The
unmeasured Tier 2 risk is **college Saturdays**:

- NCAAF and NCAAB are both Tier 2.
- An FBS Saturday has roughly 60 games in noon / 3:30 / 7:30 ET waves.
- College basketball season starts in early November. Its Saturdays have well
  over 100 Division I games.
- Upcoming means a start within six hours. On those mornings that count can
  exceed 48, and even today's 64.

The measured window holds no college Saturday and no college basketball. If T2
protection on college days matters, a variant that leaves Tier 2 untouched and
takes all the room from Tier 1 is `96,48,128,64,144,32`. Its T1 active 96 is
still about 7× the measured T1 peak. Either value is a parameter to the same
procedure.

## Totals above 512: the v2 ledger cap

The ledger's resident cap is part of the fingerprint version. Totals 1..512
stay `v1-six-hour-<map>:…` (today's bytes, cap 512); totals 513..1024 are
`v2-six-hour-<map>:…` (same classification, status and window semantics, cap
1024). Every allocation has exactly one fingerprint, so the default and any
512 split keep v1 and the release changes nothing for the ready authority. The
same procedure moves sizes AND version in one operation (`--to` a split whose
total exceeds 512); the summary prints `to_ledger_cap`. Rollback with `--to
default` returns to v1 and 512.

**Order is binding.** A writer that predates v2 parses no v2 fingerprint: it
refuses to claim and every command it sends to a v2 ledger is
`policy_mismatch` (fail closed). Old Python raises `ValueError` for a
configured total above 512 when it builds the registry, the same path as any
invalid value of this var today (its effect on the old process is not
qualified here). So: (1) the release
carrying v2 is live on `bainluck` AND heavy has converged to it; (2) then this
runbook. **Never roll the code back while the config var totals more than
512** — roll the sizes back first (`--to default`), then the code.

Proposed 1024 split (Alex picks): `96,48,192,128,448,112`.

| Bucket | Today | 512 resize (item 35) | 1024 proposal | Measured peak |
| --- | ---: | ---: | ---: | ---: |
| T1 active | 192 | 96 | 96 | 14 |
| T1 upcoming | 64 | 48 | 48 | 17 |
| T2 active | 128 | 128 | 192 | 16 |
| T2 upcoming | 64 | 64 | 128 | 15 |
| Other active | 48 | 144 | 448 | 48 (full) |
| Other upcoming | 16 | 32 | 112 | 16 (full) |

T2 rises because college basketball starts in early November (100+ Division I
games on a Saturday, plus the six-hour upcoming window) and no measured peak
contains a college Saturday. Other active 448 is about 9× today's full 48; the
retained 15:36–19:52Z logs name at least 102 Kalshi and 131 Polymarket
distinct refused events (a lower bound: one id per alarm line).

Cost at the cap, private `redis-server` 6.2 (libc malloc, laptop CPU, both
venues pending on every event, committed base padded to production's largest
stored `win_probability_sources`, 1,599 bytes):

| | 512 (v1) | 1024 (v2) |
| --- | ---: | ---: |
| ledger hash fields | 6,674 | 13,330 |
| `MEMORY USAGE` ledger key | 1.57 MB | 3.14 MB |
| bytes per resident | 3,067 | 3,067 |
| `capacity_ticket` Lua, p50 / max, sort reading each clock once (this change) | 6.5 / 7.2 ms | 11.4 / 13.2 ms |
| `capacity_ticket` Lua, p50 / max, before (per-comparison reads) | 16.1 / 17.0 ms | 39.7 / 47.2 ms |
| at-capacity `read_ticket` candidates, p50 / max | 3.5 / 4.6 ms | 6.8 / 7.9 ms |
| hot path (`read_ticket`, refused open), p50 | 0.07–0.08 ms | 0.07–0.08 ms |

Production Redis at 21:15Z 10/29 (`/api/admin/redis-census`, read-only):
69.0 MB used of 500 MB (13.8%), peak 95.2 MB, `allkeys-lru`, 0 evicted keys.
The 1024 ledger adds about 1.6 MB over 512. Eviction would hit ledger keys only
under pressure that does not exist today; a lost ledger is detected (`lost`)
and fails closed. The per-base guard (`LEDGER_MAX_BASE_BYTES`, 256 KiB) is
unchanged.

## Runbook (Integrator)

Assumptions: Integrator holds `LANE-integrator.lock`. Heavy is converged to the
main app's commit, and no heavy-sync deploy is in flight: the verifier refuses
any release change on either app during the plans. The reviewed checkout is at
the live commit, and you run from its `backend/` directory on the Integrator
machine. A one-off dyno is not a non-writer dyno type, so the verifier would
refuse it. Credentials come from the environment
(`DNPL_COMMAND_DATABASE_URL`, `DNPL_COMMAND_REDIS_URL`), never from arguments.
Pick a quiet window. Kalshi's weekly closure, Thursday 03:00–05:00 ET, is one
such window.

**Hold inputs** (record before step 0; steps 6 and 7 refuse without them):

```bash
LOCK=/Users/bain/bainluck/.claude/handoff/LANE-integrator.lock   # absolute: the hold refuses a relative path
OWNER=$(awk '/^owner_identity:/ {print $2}' "$LOCK")
python3 /Users/bain/bainluck/scripts/claim_lane_lock.py check "$LOCK" --identity "$OWNER"   # must end "HELD BY ME"
```

`--owner` is the lock's own `owner_identity`, not a free label: 3–120
characters of letters, digits, `.`, `_`, `:` and `-`, starting with a letter or
digit. The hold refuses `@` and `+`, which the lock helper would accept. The
session that claimed the lock (its `owner_pid`) must stay alive through steps 6
and 7: the hold re-checks it before and after every send.

Steps 2 through 8 are the outage window: **all** Kalshi and Polymarket websocket
live prices, committed and preview alike, pause while `worker-ws` is stopped.
Scores, odds polling and pages keep working.

0. **Record before.** Read `heroku config -a bainluck --json` and keep the
   `LIVE_BLEND_PREVIEW_RESERVATIONS` entry: absent means unset, which gives the
   defaults (`config:get` prints the same empty line for unset and for an empty
   string). Read the authority row:
   `SELECT protocol, incarnation, namespace, operation_id, state, redis_run_id,
   redis_master_replid, policy_fingerprint FROM dnpl_authority WHERE id = 1`.
   Require `state = 'ready'` and that `SELECT count(*) FROM
   dnpl_namespace_retirement` = 0. Write the eight fields to a private
   `authority.json`, with integers as JSON integers. The primary is
   `<redis_run_id>:<redis_master_replid>`. Record the current fingerprint from a
   `blend_preview reservation receipt` line.
1. **Snapshot.** Run `python -m app.services.dnpl_activation_command preview
   --expected-authority "$(cat authority.json)" --expected-primary <primary>`.
   Require `SNAPSHOT_MATCH`, exit 0. Anything else: stop, nothing has changed.
2. **Stop writers.** Run `heroku ps:scale worker-ws=0 -a bainluck`. Confirm
   that `heroku ps -a bainluck` lists no `worker-ws` dyno and that heavy's
   `worker-ws` formation is 0.
3. **Config.** Run `heroku config:set LIVE_BLEND_PREVIEW_RESERVATIONS=<sizes> -a bainluck`.
   This creates a release and restarts every running `bainluck` dyno;
   `worker-ws` stays at 0. Read the value back with `config:get` and keep the
   exact output.
4. **Bind releases, then wait for the restart.** For both apps, record the
   current release version, its slug id and that slug's commit in `apps.json`:
   `{"bainluck": {"release", "slug", "commit"}, "bainluck-heavy": {...}}`. A
   config release has no commit in `heroku releases`, so take the commit from
   the slug. The two commits must be equal. Then wait until every dyno on
   **both** apps runs the bound release:

   ```bash
   heroku ps -a bainluck --json | jq -r '.[] | "\(.name) \(.release.version) \(.state)"'
   heroku ps -a bainluck-heavy --json | jq -r '.[] | "\(.name) \(.release.version) \(.state)"'
   ```

   Every line must show its app's bound release. Re-read every 15 s until it
   does; do not start step 6 before. The verifier checks every dyno's release
   and refuses (`dyno release changed`) while any dyno still runs the old one.
   That refusal comes before any send, but the operator still prints `STOPPED`.
5. **Build plans.** Run `python3 scripts/reservation_relimit_plan.py
   --expected-authority authority.json --primary <primary> --apps apps.json --to
   <sizes> --configured "<exact step-3 readback>" --out-dir <new private dir>`.
   Require `PLANS_WRITTEN`, and check `to_fingerprint` against the expected
   value. For the default proposal that is
   `v1-six-hour-ba82e47ee634aba7:128,48,96,48,160,32`. Keep the plan files as
   written (0600); the operator refuses a plan file that is not private.
6. **Activate.** Create a fresh run dir, then run the operator:

   ```bash
   RUN_A=<new absolute path>; mkdir -m 700 "$RUN_A"
   python -m app.services.dnpl_activation_operator execute-plan \
     --plan <dir>/activate-plan.json --lock "$LOCK" --owner "$OWNER" --run-dir "$RUN_A"
   ```

   The operator does not create `--run-dir`. It must already exist, be owned by
   you, have mode 0700 and be empty. Require `PLAN_DONE`, exit 0. The final
   step reads the ready row back under the hold.
7. **Retire.** Same, with its own fresh dir:

   ```bash
   RUN_B=<new absolute path>; mkdir -m 700 "$RUN_B"
   python -m app.services.dnpl_activation_operator execute-plan \
     --plan <dir>/retire-plan.json --lock "$LOCK" --owner "$OWNER" --run-dir "$RUN_B"
   ```

   Require `PLAN_DONE`.
8. **Start.** Run `heroku ps:scale worker-ws=1 -a bainluck`. Open a
   `tail:true` log session before the dyno starts.
9. **Readback**, within 3 minutes of the start:
   - Committed live prices resumed on **both** venues: `worker-ws` minute lines
     for Kalshi and Polymarket, delivery-receipt commits, and heartbeat
     `lag max` back to its usual range. Not resumed within 3 minutes is a
     restart/escalate trigger, **not** a rollback trigger: rollback would not
     fix it.
   - Both venues log `preview display claimed epoch=`.
   - Both venues' `blend_preview reservation receipt` lines carry the **new**
     `policy_fingerprint`, `"ready": true`, a progressing `sample_seq` and new
     `registry_id` values. `shared.counts["4"]` may now exceed 48 when Other
     demand exists.
   - There are **no** `blend_preview ledger ALARM status=` lines with
     `policy_mismatch`, `policy_required`, `legacy_owner`, `fenced`,
     `malformed` or `lost`.
   - There is **no** `preview display claim failed at startup` warning.
   - Previews are flowing: delivery receipts, and Other-tier `bucket_full`
     alarm counts well below the earlier ~130/min (Polymarket) and ~34/min
     (Kalshi).
   - The PG row shows incarnation +1, `ready`, the new fingerprint, and no
     retirement row.
   - LOOK at one live Other-tier game page at phone width.

**Expected interruption (estimate, not measured).** About 5–10 minutes of
paused Kalshi/Polymarket live prices (steps 2–8):

- scale-down, the config release and its dyno restart take about 1–2 min;
- five operator steps, each with pre/post writer verification, take about 1–3 min;
- worker boot takes about 1 min.

Previews resume about a minute after the start, with an empty ledger.

### If a step stops

The operator prints `REFUSED`, `UNCERTAIN`, `UNCERTAIN-WRITER` or `STOPPED`.
Do not retry the same run dir and do not improvise.

**`STOPPED` does not mean something was sent.** The operator labels *every*
exception `STOPPED` with `may_have_sent: true`, including refusals that come
before any send: a missing or non-0700 run dir, a relative `--lock`, a wrong
`--owner`, or the verifier refusing while a dyno still runs the old release.
The run dir tells you what actually happened:

- **No `*.send-consumed` file in the run dir** (`ls "$RUN_A"/*.send-consumed`
  finds nothing): nothing was sent in that run. Every send is preceded by its
  fsynced `<sha256>.send-consumed` latch. Fix the cause (the `error_type`, or
  the step that refused), then run the **same plan** again in a fresh
  `mkdir -m 700` dir. Never reuse the stopped dir.
- **One or more `*.send-consumed` files**: a send may have happened. Go to
  "Resolving a stop after a send". Do not re-run the plan.
- `REFUSED` with exit 2: the plan file could not be read; no client was
  created and nothing was sent.

Starting `worker-ws` (step 8) is always safe, whatever state the plan is in.
Without a ready authority whose fingerprint matches the configured sizes,
producers refuse to bind and deliver committed prices only. That is today's
fail-closed path, so the outage of committed prices can end while the plan is
resolved. Before step 6 sent anything, nothing durable has changed: restore the
recorded config value (`config:unset` if it was unset, otherwise `config:set` it
back), then start.

### Resolving a stop after a send

Read the row and its progress, read-only:
`SELECT protocol, incarnation, namespace, operation_id, state, redis_run_id,
redis_master_replid, policy_fingerprint, activation_step FROM dnpl_authority
WHERE id = 1`, and `SELECT count(*) FROM dnpl_namespace_retirement`. Write the
first eight fields to a private `current.json`. Compare with `authority.json`
(the old row) and `<dir>/next-expected-authority.json` (the planned row):

| Row | Retirement rows | Meaning | Exit |
| --- | ---: | --- | --- |
| equals `authority.json` | 0 | `prepare` did not land | Same as a stop before any send: same plan, fresh 0700 dir; or restore config and start |
| planned row, but `state = 'preparing'` | 1 | Activation stopped between prepare and ready | **Continuation**, below |
| equals the planned row (`ready`) | 1 | Activation finished; only its final readback was lost, or step 7 had not finished | `--resume`, then `retire-plan.json` if step 7 sent nothing, `acknowledge-plan.json` if it did |
| equals the planned row (`ready`) | 0 | Activation and retirement both finished | Continue at step 8 |
| anything else | any | Not this procedure's state | Start `worker-ws` (committed prices only) and escalate to authority and speed |

**Activation stopped between prepare and ready.** From this point **previews
are off on every tier**, not only Other. No producer binds a `preparing`
authority: not with the new sizes, and not with the restored old ones.
Committed live prices are not affected: start `worker-ws` and they flow. A
rollback cannot be built from a `preparing` row (the tool requires a ready
one), and the activate plan cannot be replayed (its sends are burned). Previews
stay off until the continuation below reaches `ready`. If no one runs it, that
is hours, not minutes.

The scripted exit is the continuation. The tool builds exactly the remaining
steps from the row's own `activation_step`: from 0, `arm`, `initialize`,
`ready`; from 1, `initialize`, `ready`; from 2, `ready`. Each arm/initialize
send is burned in PostgreSQL before it is made, so nothing repeats. A wrong
step is refused at runtime by PostgreSQL and Lua.

1. Keep `LIVE_BLEND_PREVIEW_RESERVATIONS` at the target sizes. If you restored
   it, set it back and repeat step 4's wait.
2. If `worker-ws` was started, stop it again (step 2): the verifier requires
   every writer stopped. If the stop is understood and you are still inside the
   window, continue straight away without starting it.
3. Re-bind `apps.json` (step 4) and build:

   ```bash
   python3 scripts/reservation_relimit_plan.py --resume <dir> \
     --expected-authority current.json --activation-step <activation_step> \
     --primary <primary> --apps apps.json --configured "<exact readback>" \
     --out-dir <new private dir R>
   ```

   Require `RESUME_WRITTEN`, and check `remaining_activation_steps`. Anything
   else, for example a row that is not the planned incarnation, is `REFUSED`:
   escalate.
4. Run `R/continue-plan.json` as in step 6, in a fresh 0700 dir. Require
   `PLAN_DONE`. Then step 7 with `R/retire-plan.json`, then steps 8 and 9.

The Integrator runs the continuation under the same hold rules as steps 6 and
7. If the continuation itself stops after a send, no scripted path remains.
For example, an `arm` send that was burned but never reached Redis makes
`initialize` refuse. Start `worker-ws`: committed prices flow and previews stay
off. Authority (owner of this tool) and speed (owner of #10090) own the
recovery, which is a contract-level change and can take hours.

**Activation finished, retirement outstanding.** Previews already flow under
the new sizes once `worker-ws` starts. Only the next size change, including a
rollback, waits for the retirement. Build with `--resume` as above (the row's
`activation_step` is 2). If step 7 never ran or its run dir has no latch, run
`R/retire-plan.json`. If step 7's run dir has a latch, run
`R/acknowledge-plan.json`: it confirms the old namespace is gone with reads and
never deletes again. If the acknowledgement refuses, escalate.

## Rollback (to `192,64,128,64,48,16`, v1, cap 512)

**Triggers**, any of:

- an alarm status listed in step 9 after the start;
- no ready receipts from both venues within 3 minutes;
- the claim-failure warning;
- Tier 1/2 refusals, i.e. `bucket_full` naming a Tier 1/2 event, or receipts
  showing buckets 0–3 at their new limits;
- Alex says so.

**Procedure:** repeat steps 0–9, including the hold inputs, the step-4 wait,
fresh 0700 run dirs and the stop rules above, with these changes:

- The expected authority is the new ready row. It must equal
  `<dir>/next-expected-authority.json`.
- In step 3, restore the recorded pre-change value: `heroku config:unset
  LIVE_BLEND_PREVIEW_RESERVATIONS -a bainluck` if it was unset, with
  `--configured ""`.
- In step 5, use `--to default`.

The rollback is itself a new incarnation, so it restores the sizes, not the old
ledger contents.

## Controls

- `backend/tests/test_reservation_relimit_plan_10090.py`: exact plan shape,
  validated by the operator's own `parse_plan`/`read_plan`; refusal of a
  map/version change, equal sizes, a non-ready or wrong-primary authority, and
  invalid or mismatched configured sizes; private files; rollback input;
  `--resume` remaining steps per `activation_step`, and refusal of any row that
  is not the planned incarnation.
- `backend/tests/integration/test_dnpl_reservation_relimit_10090_pg.py`: real PG +
  Redis.
  - The default Other-active bucket refuses event 49 (`bucket_full`).
  - The plans run through the actual operator/runner/controller. Only platform
    observations are simulated.
  - The new incarnation admits 160 and refuses 161.
  - An old-sized producer cannot bind, an old-fingerprint command gets
    `policy_mismatch`, and the retired namespace refuses its token.
  - The rollback restores 48.
  - `--resume` after a real stop: after `prepare`, after a lost `arm` reply,
    and after `initialize`. Each stalled row binds no producer at either size
    and cannot build a rollback. A continuation that claims an earlier step is
    refused by PostgreSQL. The continuation, then the retirement, admits 160
    Other events.
  - A lost ready readback, then a lost retire reply. The acknowledgement plan
    clears the retirement with reads only, with no second deletion.
  - An `arm` send that never reached Redis: the continuation stops and the row
    stays `preparing`. This is the case with no scripted exit.
  - Across 512: one plan moves to `v2` at `96,48,192,128,448,112`; the ledger
    holds exactly 1024 residents and refuses the next in every bucket; a
    pre-v2 writer is refused at claim and on an existing owner's command;
    rollback returns to v1 and 48.
- `backend/tests/test_preview_ledger_cap_v2_10090.py`: one fingerprint per
  allocation (512 is v1, 513 and 1024 are v2, 1025 refused); the producer passes
  its policy's cap (resident 513 admitted); the capacity receipt validates at
  1024; the script refuses a fingerprint outside its version's range; capacity
  candidates keep their order (clockless first, oldest context, numeric id).

These qualify the procedure's source mechanics. They are not a production
execution, a measured capacity requirement, or reader acceptance.
