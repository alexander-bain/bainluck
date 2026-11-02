# Filesystem security follow-on

This follow-on addresses seven high CodeQL findings on experimental head
`64b9a82ba70588713f848b7bbd25d204a87fcf7e`. It is separate from the targeted renewal
commit. No production code, CI configuration, protocol, TTL or source policy changes.
Do not integrate while the review hold is active. Local test success does not itself
establish a clean CodeQL rescan or production acceptance.

## Findings and scope

- Six `js/file-system-race` findings (CWE-367) in the identical `src/journal.mjs`
  copies in fenced-display-authority, stream-reconnect and stream-backpressure.
  Previously, an existence check, recovery read and append open resolved the path
  separately. A mutable namespace could substitute a different inode between them.
- One `js/insecure-temporary-file` finding (CWE-377/378) in
  `fenced-display-authority/src/schedule-matrix.mjs`. Its predictable default output
  path could follow or overwrite a precreated destination.
- Four unused-name notes in tests are removed without changing their assertions.

The affected journal and schedule code was introduced earlier in this PR and was
unchanged by the renewal commit. That provenance does not make the issues harmless.
The alerts have not been dismissed or suppressed.

[Original check](https://github.com/alexander-bain/bainluck/runs/118745843548),
[representative journal alert](https://github.com/alexander-bain/bainluck/security/code-scanning/4287),
[temporary-file alert](https://github.com/alexander-bain/bainluck/security/code-scanning/4286).

## Changes

- Each journal now opens one held descriptor. Exclusive creation uses mode 0600;
  existing files reopen without create and with O_NOFOLLOW. fstat rejects
  non-regular and multiple-hard-link files; O_NONBLOCK avoids blocking on a FIFO.
  Recovery uses bounded positional reads from that same descriptor, and append
  uses it too. Constructor failures close acquired descriptors.
- Every successful constructor admission fsyncs the held inode and then the
  parent directory, including a retry after a failed creation sync. Successful
  appends still fsync before return. Torn suffixes and write/fsync errors retain
  their fail-closed behavior.
- Schedule output uses a private mkdtemp default and exclusive mode 0600 report
  creation. Preexisting report files/symlinks are refused, not overwritten.
- Five adjacent direct-invocation defaults are also private: authority
  src/test.mjs, src/crash-matrix.mjs and src/benchmark.mjs, and both stream
  tests/inherited-model.mjs copies. Only their output initialization changed,
  not model/crash/benchmark algorithms. New private output paths are printed to
  stderr and retained for the caller to inspect/remove. Explicit OUT remains
  caller-owned and trusted. The initializer does not change its existing
  permissions/content; subsequent experiment output writes retain their
  documented behavior.

## Boundary

The caller must control and trust the journal/output parent directory and its
ancestors, and provide a single writer. Final-component no-follow protection is
not safe traversal through adversarial ancestors, a lock, or a guarantee that a
pathname remains attached to the opened inode. No existing user-directory
permissions are changed. Unsupported no-follow protection fails closed.

Durability remains process-crash recovery on a surviving filesystem, not a
power-loss/host-loss or multi-host guarantee. Retained source manifests separate
old timings and browser observations from this changed journal implementation.
The earlier 18/20 real-wire compatibility result remains a failed qualification;
new focused filesystem tests do not replace it.

## Verification

Node 24.19.0 on Linux. No live feed, production service, browser or timing
benchmark was run for this follow-on.

- 79 focused filesystem/schedule contracts and 21 independent filesystem checks
  passed on the exact hardened journals and schedule source.
- 36 model checks in each of the three modules (108 total) and 22 actual SIGKILL
  scenarios passed on that same hardened journal source. These runs preceded
  the five path-only default edits; the algorithms were unchanged. The 14
  journal-backed crash scenarios retained all 10 emitted publication callbacks.
- The final-stage five default-initializer contracts passed. They execute only
  the actual initializer, not benchmark/model bodies, and assert unique 0700
  directories, printed paths, and unchanged explicit OUT permissions/content.
- Final-stage legacy independent 24/24, renewal-focused 28/28, pure contracts 16/16
  and captured-failure replay 2/2 passed.
- No new complete real-wire, PostgreSQL outage, browser or timing run is claimed.
  The prior 18/20 wire failure remains disclosed. No latency benefit is measured.
- Repository CI/CodeQL rescan is a separate remote gate, pending publication of
  this follow-on. There are no alert suppressions or workflow/config changes.

Run from tools/experiments/fenced-display-authority after its documented Node/pg
setup (the schedule comparison imports pg but starts no database):

    node --test --test-concurrency=1 review/test_journal_security.mjs review/test_journal_security_independent.mjs review/test_private_output_defaults.mjs

The first two suites resolve all three journal copies from sibling modules.
[Compact verification](fenced-display-authority/results/security-verification.json)
records the scope. Each module's results/source-sha256-before-security.json is an
exact preserved predecessor inventory; historical result references point to it.
Current results/source-sha256.json inventories the new files. Inventories are
recorded after tests, not contemporaneous copied per-run source snapshots.

API background: [Node filesystem flags and exclusive creation](https://nodejs.org/api/fs.html#file-system-flags).


## First rescan and test-only correction

The [first rescan on b297ae6](https://github.com/alexander-bain/bainluck/runs/118758427665)
no longer listed the original seven high findings/four notes, but failed on one
new `js/file-system-race` in the added independent verifier at line 40
([alert 4301](https://github.com/alexander-bain/bainluck/security/code-scanning/4301)).
This was a test-side pathname stat followed by a later pathname byte read, not a
finding in the hardened Journal. It is not suppressed or treated as clearance.

The verifier now checks mode/size with fstat and compares exact bytes using
explicit positional reads on one held descriptor; standalone reopen comparisons
hold a no-follow descriptor through the byte read and close it in finally.
Its UTF-8, capacity, torn/corrupt recovery and EIO assertions are preserved. The
corrected 21 cases passed in both the reviewer and final staged reruns. No runtime
source changed, no other suite was relabeled as rerun, and the prior verifier hash
is retained in the compact verification record. Another exact-head remote rescan
is still required before clearing the security hold.
