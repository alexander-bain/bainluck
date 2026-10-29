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

Steps 2 through 8 are the outage window: **all** Kalshi and Polymarket websocket
live prices, committed and preview alike, pause while `worker-ws` is stopped.
Scores, odds polling and pages keep working.

0. **Record before.** Read `heroku config:get LIVE_BLEND_PREVIEW_RESERVATIONS -a bainluck`.
   Empty output means unset, which gives the defaults. Read the authority row:
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
   This creates a release and restarts the non-writer dynos; `worker-ws` stays
   at 0. Read the value back with `config:get` and keep the exact output.
4. **Bind releases.** For both apps, record the current release version, its
   slug id and that slug's commit in `apps.json`:
   `{"bainluck": {"release", "slug", "commit"}, "bainluck-heavy": {...}}`. A
   config release has no commit in `heroku releases`, so take the commit from
   the slug. The two commits must be equal.
5. **Build plans.** Run `python3 scripts/reservation_relimit_plan.py
   --expected-authority authority.json --primary <primary> --apps apps.json --to
   <sizes> --configured "<exact step-3 readback>" --out-dir <new private dir>`.
   Require `PLANS_WRITTEN`, and check `to_fingerprint` against the expected
   value. For the default proposal that is
   `v1-six-hour-ba82e47ee634aba7:128,48,96,48,160,32`.
6. **Activate.** Run `python -m app.services.dnpl_activation_operator
   execute-plan --plan <dir>/activate-plan.json --lock <LANE-integrator.lock>
   --owner <identity> --run-dir <new dir A>`. Require `PLAN_DONE`, exit 0. The
   final step reads the ready row back under the hold.
7. **Retire.** Run the same command with `--plan <dir>/retire-plan.json --run-dir
   <new dir B>`. Require `PLAN_DONE`.
8. **Start.** Run `heroku ps:scale worker-ws=1 -a bainluck`. Open a
   `tail:true` log session before the dyno starts.
9. **Readback**, within 3 minutes of the start:
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

- scale-down and the config release take about 1–2 min;
- five operator steps, each with pre/post writer verification, take about 1–3 min;
- worker boot takes about 1 min.

Previews resume about a minute after the start, with an empty ledger.

**If a step stops** (`REFUSED`, `UNCERTAIN`, `UNCERTAIN-WRITER`, `STOPPED`):

- Do not retry or improvise.
- Starting `worker-ws` is always safe. Without a ready authority whose
  fingerprint matches the configured sizes, producers refuse to bind and
  deliver committed prices only. That is today's fail-closed path, so the
  outage can end while the plan is resolved.
- Before step 6 nothing durable has changed. Restore the recorded config value
  (`config:unset` if it was unset, otherwise `config:set` it back), then start.
- After step 6 began, resolve with the operator contract's readback-only paths
  (`docs/contracts/dnpl-authority-v3-command.md`), then continue or roll back.

## Rollback (to `192,64,128,64,48,16`)

**Triggers**, any of:

- an alarm status listed in step 9 after the start;
- no ready receipts from both venues within 3 minutes;
- the claim-failure warning;
- Tier 1/2 refusals, i.e. `bucket_full` naming a Tier 1/2 event, or receipts
  showing buckets 0–3 at their new limits;
- Alex says so.

**Procedure:** repeat steps 0–9 with these changes:

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
  invalid or mismatched configured sizes; private files; rollback input.
- `backend/tests/integration/test_dnpl_reservation_relimit_10090_pg.py`: real PG +
  Redis.
  - The default Other-active bucket refuses event 49 (`bucket_full`).
  - The plans run through the actual operator/runner/controller. Only platform
    observations are simulated.
  - The new incarnation admits 160 and refuses 161.
  - An old-sized producer cannot bind, an old-fingerprint command gets
    `policy_mismatch`, and the retired namespace refuses its token.
  - The rollback restores 48.

These qualify the procedure's source mechanics. They are not a production
execution, a measured capacity requirement, or reader acceptance.
