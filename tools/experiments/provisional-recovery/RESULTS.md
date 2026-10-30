# Recovery findings and scope

## Verified original experiment

The original isolated experiment passed 29 candidate checks and five independent
adversarial checks. It exercised 26 actual SIGKILL scenarios (23 single-item boundary
cases plus three five-publication bursts), a real owned-PostgreSQL outage/restart,
and 720 synthetic offers. All 720 were accepted, callback-published and stored in
the timing cells; those counts are not crash-recovery or browser success rates.

Across single-item boundaries, displayed items still missing after recovery were:
3 for memory, 1 for WAL-after, and 0 for WAL-before. In the five-publication burst,
those missing counts were 5, 1, and 0 respectively. Some WAL-before recovered rows
were never published; recovery does not fabricate evidence that they were displayed.

The outage retained four accepted/WAL-recorded/published values, refused a fifth
before publication, and recovered all four without duplicates. Reconnect while the
authority database was unavailable stayed empty.

## Failed alternatives remain visible

Database generation checks alone do not prevent a stale connected client display or
the reconnect check/use race. Both are retained expected-failure controls. Neither a
successful SQL replay nor a new generation column establishes distributed display
safety. Pre-publication fsync's stronger local custody is a latency/durability trade-off,
not removal of all persistence from the critical path.

## Packaged rerun

See `results/verification.json` for this PR's final rerun and exact-source hashes.
The local runner is synthetic and generates its own small fixtures. It does not
replay the earlier raw market/browser corpus. The original evidence archive filename
is `provisional-recovery-20261020.zip`; it is intentionally not copied here.
