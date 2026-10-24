# Reservation cutover tooling

PILLAR: TRUTH. SHIP: Tier 1/2 pages retain DNPL capacity through a cutover whose owner evidence can be checked.

These files package the accepted C1–C4 owner-fence/readback bytes in the backend slug. They must ride an ordinary release **before reservation activation and T−1**, so the selected old release and subsequent new release both contain them. Shipping them only with #11564 would not satisfy that prerequisite. Nothing imports or invokes them automatically; there is no startup hook, new dependency or activation switch.

Packaging is not permission to execute a fence, readback, reset, outage or rollback, and selects neither Option F nor Option D. Integrator retains execution custody and the separately reviewed all-writer/process inventory, formation/start interlocks and actual-release binding. Delayed NEW claims after reset remain unresolved; this tooling is not a drain guarantee.

## Exact accepted bytes

C1–C4 manifest SHA256: `ba55f8650c92f8df53a10f8a521973b63f797bbd3229d956326cdafa1e3ea245`.

| File | SHA256 |
|---|---|
| `old-owner-fence.py` | `add82908ea909734800c1aa9d2a69b6100f3f84837fa7e3a85c89c128d895bf7` |
| `readback.lua` | `46981112b1b84c68ec66823710ee6c4fda9eed4eeb0eaff70df74478ff214c2f` |

`MANIFEST.sha256` contains these literal hashes with paths relative to the **backend slug root**, which contains `app/` and `scripts/`. The Python file locates `readback.lua` beside itself. Keep the pair together. The fence pins the old module/Lua bytes from `0cc1521f435aeeec33e22f9ebbd64b70b0bb42b5`; actual old release/slug identity still requires T−1 binding. Relevant source drift requires an explicit rebind; the presence of these files proves no deployed identity.

## W2: fail closed in the same one-off

Only after separate operational authorization and the external preconditions hold, the executor substitutes the trusted release/slug receipt and runs from the verified backend slug root. The command explicitly targets `bainluck`, never heavy. Print both file hashes, validate them against the accepted manifest literals, and start Python **only after** checksum success. This is a command template, not an invocation performed by packaging:

```sh
heroku run:detached -a bainluck 'set -eu
  test -f app/utils/blend_preview.py
  sha256sum scripts/reservation_cutover/old-owner-fence.py scripts/reservation_cutover/readback.lua
  sha256sum -c scripts/reservation_cutover/MANIFEST.sha256 &&
    PYTHONPATH="$PWD" python3 scripts/reservation_cutover/old-owner-fence.py \
      --mode fence --release-identity REPLACE_WITH_EXTERNALLY_BOUND_RELEASE_SLUG_RECEIPT'
```

For an independently authorized readback, use the same hashes, cwd and shell failure handling with `--mode readback`. That mode does not import application code or claim an owner. Fence mode imports the hash-verified old module only when explicitly invoked. There is no reset operation in this directory.

Capture logs from dyno creation. Take `run.N` from the create response's **`done, run.N`** line, never echoed arguments. T0c success requires matching in-dyno hashes/checksum success, both source `claim_ack` lines, `fence_complete`, accepted final metadata, and trusted `heroku[run.N] Process exited with status 0` from that same run. A post-run empty log session cannot substitute. Missing/ambiguous output is INCONCLUSIVE; a lost reply may already have moved owners. No automatic retry or repeat claim.

## W1: retained JSON must be complete

The invocation's 65,536-character raw-evidence cap exceeds Heroku's approximately 10 KB per-log-line limit. A retained `raw_snapshot` counts only if **both its complete outer log JSON and its `raw_snapshot` string parse as JSON**. Truncated, split, missing or unparsable output is INCONCLUSIVE; never reconstruct success from a prefix. Preserve the raw owner/field evidence and fixed STOP code. A partial pair does not imply no write.

## W3: bind the actual topology

Read `WS_VENUE_PROCESSES` at T−1; do not inherit a preparation-time value. Open logs before worker startup. Split-child mode requires the parent's `Started <venue> child pid=` and child's `Starting <venue> WebSocket process pid=` startup mapping in the trusted dyno/release envelope. Shared-loop mode emits **no per-venue PID line**: bind the platform dyno-start line plus the shared receipt `pid`/`registry_id`. Missing required mapping evidence is INCONCLUSIVE.

Readiness requires positive, complete `ready` receipts from the actual workers within 45 seconds, using the selected tree/configuration's precomputed fingerprint. Sequence gaps are normal; sequences must increase within a registry. Record `local.proofs`; nonzero is not a zero-proof failure. Alarm absence is not readiness. Ordinary `retire_idle late` is not a fenced alarm, and aggregate `ledger_refused` is not a cutover-failure signal. `malformed` remains STOP; trusted-new `fenced` and `legacy_owner` have no automatic-reclaim grace.
