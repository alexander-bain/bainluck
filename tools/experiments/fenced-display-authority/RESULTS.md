# Authority findings and limits

## Verified original experiment

- 36 candidate and 24 independent checks passed, including 192 interleavings.
- 22 SIGKILL cases, deterministic scheduling matrices, six browser cases,
  real owned-PostgreSQL outage/restart, and 5,400 model timing samples were audited.
- Lost handshake challenge, nonce replay extending a lease, and ownerless startup
  defects were found and fixed before the original source freeze.
- PostgreSQL outage retained four unresolved values, refused overflow, recovered
  their history without restoring old-epoch current display, then persisted a new
  current publication.

## Do not hide the negative results

The final original model benchmark had a **2.063-second maximum observation latency**
although its memory-broker medians were approximately 0.154–0.190 ms. These are
synthetic model accepts, not browser or end-to-end raw venue measurements. The
outlier invalidates an unqualified subsecond claim; a later faster sample would
not erase it or establish a general bound.

Already-taken old bytes may still be accepted before their invalidation arrives,
within the lease. Scheduler stalls delay actual expiry handling. Singleton broker
enforcement and source freshness remain assumed, not established. Optional journal
fsync adds prepublication work. None of these limits inherits the historical
402.551 ms replay number from the separate display-first experiment.

## Packaged rerun

`results/verification.json` records the exact packaged rerun. The six original
browser cases were not rerun by the command-line packaging checks. Browser/rAF
observations are not physical-paint certificates. Full original evidence is in
`fenced-display-authority-20261020.zip` and `display-authority-review-20261020.zip`,
not raw data committed to the PR. This remains experimental, not deployment approval.

The packaged synthetic rerun passed 36 candidate / 24 independent checks and again
exceeded two seconds: journal-before with injected 100 ms async persistence had a
2,027.898 ms maximum model-observation sample (round 2). Its actual producer offer
returned at 2,027.408 ms. This run shared the host with other authorized work; the
cause is not established and no idle-host or intrinsic-cost claim is made. The
original 2.063 s memory outlier remains valid historical evidence and is not erased.
