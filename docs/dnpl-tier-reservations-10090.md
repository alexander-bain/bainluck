# DNPL tier reservations (#10090)

PILLAR: TRUTH. SHIP: Tier 1 and Tier 2 eligible pages cannot be excluded by
lower-priority shared preview capacity. This is bounded admission, not a claim
that every eligible page always has a preview. Same-tier overload and retained
local authority evidence remain explicit limits; committed delivery continues.

## Allocation and classification

The existing 512-event Redis ledger has six non-borrowed reservations:

| Tier | Active | Upcoming |
| --- | ---: | ---: |
| Tier 1 | 192 | 64 |
| Tier 2 | 128 | 64 |
| Other | 48 | 16 |

These are provisional product allocations, not measured capacity requirements.
No lower tier borrows an unused higher-tier reservation. All contributions to
one event share one charged slot, regardless of venue count.

Classification uses `get_league_tier` and canonical `Sport.key` joined through
`Event.sport_id`; there is no second league table. Unknown sport keys are Other.
Live, suspended, and already-started scheduled rows are active. Upcoming means
scheduled with a known aware future start no more than six hours after the
statement's database clock. Unknown scheduled starts, later starts, completed
rows and other lifecycle states are outside admission. Missing graph fields or
clock proof fail closed. The prepared graph carries `preview_context_at` from
PostgreSQL `statement_timestamp()`.

The charged bucket is distinct from the current target classification. A
promotion into a full bucket can retain its issued charge until capacity allows
transfer. Demotion or postponement cannot keep borrowing a higher-priority slot
through renewal: it creates explicit debt, suppresses new/sibling opens and
lease extensions, and preserves the already-issued deadline. A committed write
still adopts the base and consumes progress dimensions when renewal is denied.

## First cutover and configuration limit

This first ship requires a coordinated stop/drain of every old ledger writer
before upgraded writers start. An old Lua script cannot be compelled to obey
new fingerprint metadata. Ordinary rolling deployment with old writers is
**not supported**. A process restart is not proof that all old writers stopped.

`LIVE_BLEND_PREVIEW_RESERVATIONS` accepts six comma-separated nonnegative
integers totaling 1..512, in the table's row order (active then upcoming).
It is **initial-bootstrap configuration only**. The persistent fingerprint
includes sizes, league-map hash, and the classification semantics version.
An existing ledger rejects mismatches, including after an ordinary restart.
Changing environment sizes or the league mapping is therefore not an
operational tuning mechanism in this ship. No automatic reconfiguration,
namespace reset, counter reset, or rekey procedure is supplied.

Migration keeps the existing Redis namespace, generations, sequences, owners,
revision floors, read tickets, and issued expiry deadlines. Initialization
checks actual resident IDs against the recorded count before writing policy
metadata. Bounded batches of at most 32 residents receive fresh locked database
classification; unclassified residents block new opens. Compatible workers can
continue classification across restarts. Partial accounting fails closed.

Legacy over-budget or outside-window chains retain their exact issued expiry,
but cannot extend it or open replacement/sibling chains. Drain time comes from
actual Redis deadlines: do not assume sixty seconds, because lease duration is
configurable. Capacity status exposes unclassified residents, charged counts,
debt, compatibility and readiness. A green process startup alone does not prove
the cutover is complete.

## Reclamation and authority evidence

Ordinary lifecycle retirement retains the existing future-scheduled-only idle
rule and its live/in-play protections. Separate policy retirement can reclaim a
full or indebted class only after fresh authoritative classification under an
Event row lock held through the Redis acknowledgement, and only when Redis
finds no valid pending contributor. Busy rows are skipped; a candidate hint is
not deletion authority. Owner, ticket, revision, generation and sequence fences
remain in force. Retirement emits an ordered revoke.

Local bookkeeping is also bounded. Pending chains, expired values and
`expired_through` evidence are never evicted for admission. A capacity-retirement
ACK converts only still-matching pre-EVAL local work into expiry evidence;
newer local work survives a delayed ACK. Thus an unchanged expired value cannot
receive a fresh lease just because maintenance reclaimed its Redis residency.
Drained proof follows the current classification, exposing debt instead of
silently occupying a high-tier reservation. A newcomer can replace a clean
same-class context when its bucket is full; with bucket headroom but total
local saturation, it can reclaim a clean lower-priority or indebted context.

If all 512 local contexts genuinely carry pending work or retained authority
proof, admission can refuse even with a high-tier Redis reservation available.
This explicit safety fallback is not universal starvation protection. Local
counts, proof count and debt are reported alongside shared readiness. No proof
is erased to make a coverage claim. Existing TTL/reader fences and ordinary
committed frames remain the fallback.

## Verification boundaries

`test_preview_reservation_policy_10090.py` covers classification and allocation.
`test_preview_reservations_redis_10090.py` exercises real Redis saturation,
transition, migration, deadline, restart, proof-retention and local debt cases.
`integration/test_dnpl_reservations_10090_pg.py` exercises the actual Sport join,
database clock, bounded restart classification and row locks held through Redis
acknowledgement, including pending-contributor races.

These tests qualify source mechanics. They are not production cutover evidence,
served-page acceptance, measured capacity sufficiency or permission to deploy.
