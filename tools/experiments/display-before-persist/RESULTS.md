# Verification and historical results

## This PR's small synthetic fixture

Local rerun on 2026-10-20: **19 checks passed, 0 failed/skipped** (Node 24.19.0,
PostgreSQL 17.11). The runner created and stopped its own loopback-only cluster.
The tests used the existing installed `pg` 8.23.1 dependency and its pinned
transitive packages. `npm ci --offline --ignore-scripts` was attempted separately
and could not complete because the local npm cache lacked a transitive tarball;
an online clean dependency install has not been verified in this environment.

Coverage includes display before an unresolved commit, commit-first control,
input-copy isolation, delayed/failed writes, bounded admission, out-of-order
commits, duplicate/conflicting identities, old/current ACKs, terminal rejection,
new-epoch clearing, an actual SIGKILL before commit, lost commit ACK retries and
reconciliation, explicit unresolved uncertainty, and delivery exceptions not
being confused with failed database commits.

These are correctness checks of an already-validated payload mechanism. They do
not benchmark a browser, reprocess source quotes, or establish production safety.
Full application startup/build/typecheck suites were not run in this isolated
stage: it is not a complete current application checkout. Exact-head repository
CI is a separate gate, not a pass inferred from these 19 checks.

## Earlier full-recording experiment (not reproduced by this small fixture)

The separately delivered `display-before-persist-evidence-20261020.zip` contains
frozen source, raw/browser/SQL receipts and offline analysis reproduction.
Its SHA-256 is
`db3a3876418bf56dc7e6d929837fabc97ddb4072256ff757a57bb8b113ce010d`.
No copy of that 16.6 MB archive or its raw recordings is committed here.

Historical paired payload-stage runs used 69 previously validated payloads:

| PostgreSQL condition | Display-first scheduled offer to current second-rAF, median / maximum | Commit-first, median / maximum |
| --- | --- | --- |
| No injected delay | 21.106 / 107.738 ms | 41.446 / 122.396 ms |
| Injected 1,200 ms delay | 30.380 / 388.725 ms | 1,256.714 / 1,670.969 ms |

Both arms in each payload-stage run observed and persisted 69/69 publications.
Their approximately 11-second longest intervals between numeric changes remained.
The schedule already contains original upstream processing; those rows are not
raw-input end-to-end measurements.

A separate historical immediate raw-adapter replay (adapter **not included in
this PR**) produced 77 publication opportunities. With normal PostgreSQL:

- Display-first wrote all 77 numbers to the DOM and observed 74/77 while still
  current at second-rAF. Median / maximum scheduled triggering input to that
  observation: 32.742 / 402.551 ms. Three superseded observations are missing,
  not counted as successful current observations.
- Commit-first had 75 DOM writes and 73/77 current second-rAF observations;
  median / maximum 57.712 / 891.764 ms. Both arms persisted 77/77 exact payloads.
- The 72 mutually observed sequences had a median 25.800 ms and maximum
  580.300 ms commit-first penalty, measured on the same browser clock.
- In the worst display-first second-rAF example, the DOM write was at 143.250 ms;
  the later second-rAF observation was at 402.551 ms. That observation interval
  is not a deliberate display timer or proven unnecessary delay. Across all
  display-first DOM writes, the maximum was 162.564 ms.

The 402.551 ms figure is a conditional historical observation, **not a maximum
unnecessary delay**, all-input bound, physical-paint measurement or production
promise. No maximum avoidable delay remaining has been established. Injected
SQL delay is a causal control, not normal database performance. These runs cannot
validate the separate later journal/recovery/authority candidates.

## Do not promote from this evidence alone

The implementation deliberately loses pending memory on process death. Hashes
and run/epoch checks are harness identity checks, not distributed authentication
or ownership. It does not preserve uncommitted display values across owners or
make stale live connections safe. Production integration still needs an explicit
recovery/authority design, overload policy, current source semantics, integration
tests and a separately authorized rollout.
