# Independent review: producer-chain metadata seam

Reviewed 2026-10-21. **The isolated additive registry change supplies stable, nonrenewing producer metadata on the exercised real-source paths without replacing the existing ordered publication batch.** No blocking issue was found within this narrow scope. This is a writer-metadata integration result, not a deployed feature, visible-latency result, or completed retained-recovery implementation.

## Source and scope

The builder saved two current modules from commit `b2b92fe86467d0accdb02f7b765ada020b594aec`: PreviewRegistry and LiveBlendRefresher. The candidate changes only the saved registry copy. I inspected those bytes, their exact patch, and the current publisher. Tests load these current modules over pinned `a43949050b966b8009bddd5dda1afd65ddf1f9f6` fixture dependencies. This is not full-current-checkout validation. The pinned application checkout remains unchanged and clean.

The existing current `_publish_previews` stays byte-identical: one claim lock, complete serialization before one ordered fenced EVAL, with the current optional `prepare_frames` callback after claim. The explicit `retention_input.prepare` helper composes commands only. It neither sends them nor substitutes per-frame EVALs for that batch.

## What the result establishes

- Identity and original expiry attach to the actual per-source Pending chain, not the changing probability, observation, sequence, base revision, or replacement Pending object. Quiet retries and changed values retain the chain's immutable lease object.
- The oldest still-pending chain determines frame metadata. Removing that chain may reveal a sibling's later original deadline; this is not a fresh full lease. Equal-start siblings have distinct identities.
- Existing original observations, probability calculations, attempt clocks, TTL semantics, commit/refusal/expiry markers and event-state bounds are preserved. `lease_issued_at_ms` is the current metadata attempt's budget timestamp, not a source observation or the original chain start.
- Initial optional metadata failure remains live-only for that entire chain. Later retries do not reconstruct a new deadline. Subsequent true settlement can open a new chain. Wall jumps do not restamp the stored deadline; a backward-offset command can conservatively become uncached.
- A preclaim frame can keep its identity while the existing publisher fills its authoritative epoch after claim. `pending:<counter>` must remain jointly scoped by the claimed epoch and event; it is not globally unique alone.
- Known owner loss still fences blends without reclaiming and still permits revokes. An unknown publication acknowledgement still disconnects, does not resend, does not claim a successful receipt, and does not undo registry transitions or reset the lease.

## Independent checks

Twelve reviewer-authored Python tests passed against the final pinned candidate and included driver. They cover actual current refresh → quiet refresh_pending → commit, changed values, wall jumps, initial metadata failure, equal-start siblings, partial expiry, old/new commit settlement, eviction bounds, one ordered batch, owner loss, ambiguous acknowledgement and empty postclaim preparation. Final output is `results-final.txt`.

I also independently reran the builder's seven composition checks against generated producer commands, the already-reviewed numeric Lua script, and deterministic fake Redis commands. All passed in the official vendored Lua 5.1 interpreter. These checks cover original deadline/expiry, commit-floor retirement, retained-write failure and disabled replay, and superseded ownership. They are model composition evidence, not a Redis command run or atomic batch implementation.

The builder's corrected combined Python suite reports 27 passes. Its initial combined run had nine failures and 18 passes because repeated source-loader calls left stale module globals. That result is preserved at `python-results-initial-combined-failure.txt`. The loader is now idempotent and rejects mixed variants; the registry/publisher source was not altered to fix this fixture error. I inspected the correction and pinned the loader as an input.

All twelve recorded input hashes were unchanged before and after final tests. No Redis server/socket launch, full application build, production operation, push, or browser benchmark occurred in this review.

## Important current-source distinction

Observation-only previews in the newer producer intentionally create no UPDATE/lock-retry debt. A quiet `refresh_pending` call therefore need not republish that preview. This differs from the lock-pending fixture, where the actual quiet entry point retries the owed stamp and republishes. No global two-second republish bound is established.

Current `prepare_frames` may claim before its final validation returns no allowed frames. Thus an empty rejected preparation can mean no registry mutation and no publication, but not necessarily no owner claim. Final validation must remain under the existing claim lock before registry mutation. The metadata patch leaves this behavior intact.

## Remaining owner work, not hidden acceptance claims

1. Wire a genuinely coherent ordered batch retention/publication path without weakening source ownership or retrying an ambiguous outcome. The singleton command preparation here is not that implementation.
2. Establish producer-to-authority-clock alignment, or use a coherent duration-based authority protocol. One local wall/monotonic anchor and a quantization margin prevent local retry restamping but do not prove cross-process clock safety. A positive producer offset followed by delayed admission is not solved by checking that issued time is no longer in the future.
3. Exercise real Redis admission/error behavior in an already-permitted environment. The earlier socket/wrapper blockers remain unresolved. Storage-loss, SQL status/commit ordering and lifecycle integration limits from the atomic packet still apply.

No new broad latency benchmark is required to interpret this small result. No user-visible improvement is claimed from metadata alone.

## Reproduction and identities

From the experiment root, with the already-prepared dependencies:

    venv/bin/python -m pytest -q review/producer-chain/test_integration.py
    atomic-redis-runtime/redis-source/deps/lua/src/lua producer-chain-metadata/tests/test_composition.lua

- Candidate registry SHA256: `30b899f2a72f0cfa993842fa3b5c38d354a6dc03c6f44ada7ad483469e107fdf`
- Reference registry SHA256: `a02404b14b6aba5df63da81add1bebe422c776ec956eeee12d454068bcf28281`
- Unchanged current publisher module SHA256: `1939e56e07a36e3d0071df88e4d2a1ba310b5e975ffcf667613b9e5e9141a22b`
- Corrected loader SHA256: `e17e3bbf4e7577af343b4b95ba259cd3c15127069394400d12c796ec4da42116`
- Included driver SHA256: `6ee49f5623ba7988ab2b677f63ba6a5a7f1e021c0585c34f5840492cbeb8eb6b`

See `final-inputs.json`, `test_integration.py`, `results-final.txt`, `composition-rerun.txt`, and the version-scoped source audit `source-contract.md` in this review directory. Earlier independent runs remain saved; the final run uses the included driver so the small packet does not depend on an omitted older driver directory.
