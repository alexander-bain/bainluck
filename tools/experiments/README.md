# Isolated latency experiments: review index

These are separate, opt-in synthetic candidates, not production integration or
permission to merge/deploy. No application path, root dependency, CI workflow or
production setting is changed. Read each module's README and limits before reuse.
Frozen predecessor copies are intentional comparison controls, not a shared
production dependency or a combined pipeline.

The table records the pre-renewal, pre-security baseline verification. Follow-on results and failures are listed separately below.

| Module | What to review | Historical verification |
| --- | --- | --- |
| [display-before-persist](display-before-persist/README.md) | Publish provisional value before PG commit; bounded writer; truthful ACK state | 19 checks; original focused handoff code/tests unchanged |
| [provisional-recovery](provisional-recovery/README.md) | Retained unresolved jobs; memory vs WAL-after vs WAL-before custody | 29 candidate + 5 independent; 26 SIGKILL; real owned-PG outage |
| [fenced-display-authority](fenced-display-authority/README.md) | Single broker, session/epoch/challenge leases; journal control custody | 36 candidate + 24 independent; schedules, 22 SIGKILL; owned-PG outage |
| [stream-reconnect](stream-reconnect/README.md) | Actual loopback SSE disconnect/reconnect; fresh session; latest snapshot | 36 model + 4 transport + 16 independent; 20 real-wire cases |
| [stream-backpressure](stream-backpressure/README.md) | Stop after write(false); bounded app/Node queue; drain deadline and unsent-owner invalidation | 15 writer + 36 model + 4 transport + 21 independent; 20 regressions + 6 pressure cases |

Each module has explicit run commands and source manifests. Database modules need
an existing Node>=22/PostgreSQL installation and pinned pg package; stream modules
need only Node>=22 and Bash. All listeners bind loopback, all fixtures are synthetic,
and owned resources stop after tests. Generated traces/databases stay gitignored.
Clean online dependency installation has not been verified in this environment.

## Non-negotiable limits

- Original authority model timing includes a 2.063 s memory-broker outlier. The
  packaged rerun includes a 2.028 s journal-before outlier. These shared-host model
  observations establish neither cause nor a subsecond bound. The rerun overlapped
  other work; no idle-host, causal overhead, or performance ranking is claimed.
- Real-stream normal publication timing excludes a preceding authority renewal.
  The full user-intent-to-DOM interval is unknown; do not add unmatched maxima.
- Snapshots recover latest state, not omitted intermediate history. A reconnect
  can intentionally leave a gap. New gap-replay successors are not included yet.
- Slow-client bounds cover encoded application queues plus Node writableLength,
  not kernel, proxy, peer or process-RSS memory. Deadlines depend on event-loop
  scheduling. Already-written bytes cannot be recalled.
- DOM mutation, second-rAF observation and physical paint are different. Neither
  the old 402.551 ms recording nor these separate candidates establishes a maximum
  unnecessary delay or a production/raw-source-to-physical-display guarantee.
- Memory can lose provisional values on crash. Prepublication fsync deliberately
  adds local durability work before display. Source freshness and cross-machine
  singleton authority remain separate unsolved requirements.

Historical measurements and packaged reruns are labeled separately. Full original
raw recordings/evidence archives, private links, credentials, runtime DBs and
node_modules are not committed. Estimator/PM dispatch policy changes, newer copy-cost
and replay-gap experiments remain excluded until separately reviewed.

## Targeted renewal follow-on

The two stream modules now include [event-driven, nonce-specific renewal confirmation](RENEWAL-UPDATE.md). This is a separate cherry-pickable experimental change. The prior full-suite receipts remain pinned to the predecessor source; current verification is separate. It is not a full-history or end-to-end latency fix.

## Filesystem security follow-on

[Descriptor-bound journals and safe schedule output](SECURITY-UPDATE.md) address the seven high CodeQL findings in the experimental files. This remains draft review material; do not equate focused local tests with a clean repository security rescan or production acceptance.
