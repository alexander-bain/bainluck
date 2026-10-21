# Corrected real-Redis handoff, NOT EXECUTED

The historical blocked-runtime packet selected the pre-numeric Lua. It remains unchanged as evidence and cannot validate the later correction. This separate harness selects the numeric-corrected Lua and adapter by exact SHA256, checks adapter.SCRIPT equality before launch, and sends ordinary claim/offer/commit/snapshot through actual Commands tuples. Raw malformed/OOM and no-rollback microprobes are explicitly separate.

Only import/selection and fake-command dispatch checks run here. All 23 real Redis methods remain unexecuted. No live Redis/OOM/eviction result is claimed. Do not retry the blocked server in this environment. A later authorized runner must explicitly provide DNPL_REDIS_BINARY (absolute regular executable path), DNPL_REDIS_EXPECTED_VERSION, DNPL_REDIS_EXPECTED_SHA256 and DNPL_RUN_REAL_REDIS=1. The hash must come from independent operator-approved provenance, not be silently computed as its own expected value. The fixture hashes the selected file before Popen and checks the owned process INFO version after startup. There is no install, download, version fallback or alternate transport. The harness retains private Unix socket, port0, no persistence, owned-process verification, subscribe ACK, cleanup and measured memory outcomes; no alternate transport or security configuration change is offered.

Tests intentionally demonstrate remaining key-loss/status-coverage prerequisites. Supplying status arguments is not a SQL transaction race. The independent microprobes are not candidate EVAL rollback proof. Concurrent order coverage is not exhaustive. The exact no-shebang Lua may behave differently under real OOM than injected fake failures; this remains unmeasured.

Selection-only command (no socket/process):

    python real-redis-unexecuted/test_selection.py

## Portable runtime successor

The initial selected harness hard-pinned the cloud Linux Redis7.2.16 binary. The owner reported that this blocked the available Mac redislite Redis6.2.14 binary before any of 23 runtime cases ran. This successor preserves the exact Lua/adapter pins while making the runtime contract explicitly operator-supplied.

Reviewed version matrix:
- Redis7.2.16: primary version; actual platform, binary SHA256 and build identity must still be reported.
- Redis6.2.14: compatibility execution only. It cannot validate Redis7.2.16 behavior, especially memory admission or later engine semantics.
- Any other, missing or malformed version: reject before launch.

Existing runtime identities, not binaries supplied by this PR:
- Cloud official Redis7.2.16 Linux build: SHA256 304e1a2ed1bb51bf62592a68d16a81a678d228599bacc039af832a5a6407d5dd.
- Owner-reported redislite Redis6.2.14 Mach-O arm64 build: SHA256 5827327e29a6203b3a943e22448ff6bd3de1b72bce84abca904f199d6dbacd2e. This cloud task has not executed or independently hashed that Mac binary.

No runtime selection is automatic. An operator selecting a different approved 7.2.16 platform build must supply that build's independently verified hash. A matching file hash does not by itself certify vendor provenance; approval/provenance is the operator's prerequisite. The file must remain unchanged between validation and launch. The owned-process version check is separate from the filename/hash claim.

No-socket successor checks:

    python real-redis-unexecuted/test_runtime_selection.py
    python real-redis-unexecuted/test_selection.py

These checks use inert temporary file bytes and mocked process/socket boundaries. They are selection tests, not 23 passing engine cases. Unknown bytes/versions are refused, not downloaded or accepted heuristically.

Example for the separately authorized Mac owner, after replacing the path with the existing approved executable (this is NOT a request to run it in the blocked cloud environment):

    DNPL_REDIS_BINARY=/absolute/operator-selected/redis-server \
    DNPL_REDIS_EXPECTED_VERSION=6.2.14 \
    DNPL_REDIS_EXPECTED_SHA256=5827327e29a6203b3a943e22448ff6bd3de1b72bce84abca904f199d6dbacd2e \
    DNPL_RUN_REAL_REDIS=1 python real-redis-unexecuted/test_real_redis.py

Use the same Python environment containing redis-py. Any resulting report is Redis6.2.14 compatibility evidence. A Redis7.2.16 run requires its own approved binary/path/hash and expected version7.2.16. Results are written to the ignored `.work/real-redis/` directory; share status, runtime contract and actual outcomes, including blocked/failed cases rather than only attempted method names.
