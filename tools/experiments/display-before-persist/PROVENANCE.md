# Source provenance and deliberately separate follow-ups

This directory contains original experimental code prepared for BainLuck. It
reuses no production module at runtime and vendors no downloaded application
source. The repository's [MIT license](../../../LICENSE), copyright 2026
Alexander Bain, applies; installed npm packages retain their own licenses.

The reviewed repository baseline was [`c20105dc16dc9c86a133b66b61d7e49a41224b25`](https://github.com/alexander-bain/bainluck/commit/c20105dc16dc9c86a133b66b61d7e49a41224b25).
Its tracked `CLAUDE.md`, README, PR template, CI triggers, change-scope classifier
and Heroku release classifier were inspected. No tracked `AGENTS.md` or
`.agents/skills` was present at that commit. Referenced local lane queues were
not present in the remote tree. This branch is a separate draft handoff, not a
claim on or mutation of an active implementation lane.

## Experiment source pinning

The first-pass implementation was taken from the tested V2 mechanism in
`display-before-persist-evidence-20261020.zip`. Original input file SHA-256s:

- `pipeline.mjs`: `85979c1189a9fcd8857410d89affd4863c7c761d172d06c291d9f4a5eaf939cb`
- `client-core.mjs`: `1bcad480d08216513dc2f5670e80ab13ace0110523925aad72331ff66b2a1119`
- `test.mjs`: `95eda9cbf935c39aac66dcee53221c8dbe7ad74c06d2ece4a9fc714b7528f6f5`
- `crash-child.mjs`: `58d6d0694dbd24c429d330ef463296c2645aa1941640209627c5e652639f75b1`

Packaging changes: `PgStore` is split into `src/postgres.mjs`, the absolute
machine-specific dependency path is replaced with a normal local `pg` import,
`client-core.mjs` is renamed `client.mjs`, and the copied integration checks have
relative import paths. The crash-child URL uses `fileURLToPath` for checkout paths
with spaces. PG checks require an owned-cluster marker and match its process/port
receipt before connecting. The new unit checks use synthetic frames. `run.sh` is a
new opt-in portable runner owning only a disposable local database. No claim is
made that those packaging edits were in the earlier browser-measured code.
`results/source-sha256.json` pins this handoff's runnable files.

## Separate experiment inventory

The original focused handoff excluded these; the approved expansion now includes
separate recovery, authority, real-stream and backpressure directories. Estimator
and PM dispatch changes remain outside the PR. Their
existing deliverable filenames identify the evidence without exposing private
file-service links or copying nested bundles into the repository:

- `estimator-matrix-offline-handoff-20261020.zip`: source-selection counterfactuals.
  Quote-first changes estimator semantics; it is not a free transport speedup.
- `dispatch-matrix-20261020.zip`: guarded Polymarket dispatch. No missing changed
  BBO was observed in the 2,741 ignored messages; synthetic BBO-loss recovery is
  not an observed speed improvement.
- `provisional-recovery-20261020.zip`: memory / post-publication WAL /
  pre-publication WAL recovery. Pre-publication fsync adds durability work before
  display and requires its own trade-off review.
- `display-authority-review-20261020.zip`: independent review of the later fenced
  authority candidate. Its architecture and timing evidence are separate from
  this baseline and carry no inherited subsecond bound.

Actual SSE reconnect and bounded slow-client transport are now included in separate
modules with their own verified scope. New copy-cost and replay-gap successors are
not included. Review and accept each mechanism separately before any production
adaptation; these are not one combined end-to-end implementation.
