# Reviewed collection publication operator (#9916)

PILLARS: TRUTH / MATCHING / DISCOVER. SHIP: the release owner can publish or
withdraw the specifically reviewed NFL-week and MLB-postseason hubs with exact
identity/revision guards and a usable visibility rollback.

Authority owns the semantic contract and eventual operation. The operator does
not assemble collections, select a week from the calendar, change flags, choose
extra targets, create schema, or grant activation approval. Existing
`publish_container` / `withdraw_publication` helpers own publication, row locks,
revision bumps and correction ledger writes. One hub per invocation/transaction
keeps each receipt's scope explicit; repeat target flags are refused.

Run from `backend/` using the owner's already configured `DATABASE_URL`. No URL,
credential or environment dump appears in the receipt. The variables below are
placeholders populated from Authority's actual reviewed assembly receipts, not
fixture IDs, guessed weeks or approval supplied by this document.

```sh
# Default: explicit targeted preview, database READ ONLY, rollback, no commit.
python3 scripts/collection_publication.py --slug "$REVIEWED_SLUG"
# ID + slug must resolve to the same row; also checks the reviewed revision.
python3 scripts/collection_publication.py \
  --container-id "$REVIEWED_ID" --slug "$REVIEWED_SLUG" \
  --expected-revision "$REVIEWED_REVISION" --operation publish
```

The JSON preview includes the canonical edition from the adapters' slug
builders; row identity, status, windows, publication state and membership
revision; known game/question/edge counts, missing-row count and member classes;
and prospective publication eligibility from the discovery producer's own pure
check. Counts describe stored membership only. Completeness/partial-terminal
coverage still requires Authority's named assembly receipt; this operator cannot
reconstruct unread provider days or games that were never assembled.

No target returns a refusal, not an empty successful report. Noncanonical,
wrong-edition and nested targets are refused. Empty or dangling-only membership
cannot publish; an empty hub may still be withdrawn using the existing helper.
When no publication operation is requested, an empty target can be previewed
with `publish_eligible=false`. Withdrawal never rebuilds or erases membership.

Only after the separately authorized named operation, the owner supplies every
write field explicitly and saves the resulting JSON receipt:

```sh
python3 scripts/collection_publication.py \
  --container-id "$REVIEWED_ID" --slug "$REVIEWED_SLUG" \
  --operation publish --apply --expected-revision "$REVIEWED_REVISION" \
  --actor "$OPERATOR" --reason "$APPROVED_REASON" \
  --evidence "$REVIEWED_EVIDENCE_JSON" > "$PUBLICATION_RECEIPT"
```

`REVIEWED_EVIDENCE_JSON` is a nonempty JSON object naming the actual review and
operation evidence. `--operation withdraw` uses the same required fields.
An apply locks with the helper's established order, then rechecks the ID, slug,
root/edition and exact revision under that lock before calling the write helper.
The caller commits only explicit apply; preview and refusal roll back. No stale
revision is silently refreshed/retried. A fresh preview plus renewed review is
required after drift.

Receipts distinguish `preview`, `applied`, `noop`, `refused` and `failed`, with a
nonzero exit for refusal/failure. `before`, updated `target`, `correction`,
`decision`, `committed` and `committed_at` distinguish reviewed state, helper
result, supplied decision and acknowledged commit. A no-op records no new
correction and offers no inverse that would undo someone else's existing action.

Rollback information is **prerequisites, not a runnable stale command**. It
records the same ID/slug and `expected_revision_at_commit`, the permissible
inverse, and mandatory fresh targeted review. A later assembly/correction can
change that revision; never paste its replacement into a write without reviewing
what changed. A failed commit reports `commit_outcome_unknown` with
`committed=null`; resolve current row/ledger state before retry or rollback.
Cleanup failure after an acknowledged commit preserves `committed=true` and the
receipt. Neither case claims an automatic rollback or offers an inverse without renewed review.

Publication visibility rollback uses guarded `withdraw`, keeping membership and
the correction ledger. It yields `withdrawn`, not the original `unpublished`
state. A withdrawal of a previously published hub can be undone only by a newly
reviewed, eligible `publish`; the helpers have no operation that restores an
original unpublished state. The operator changes no reader/discovery/assembly
flags. Authority's existing activation packet owns flag order and served-reader
verification.

Focused tests use the real helpers through a SQL double for CLI/default-no-write,
identity/revision/eligibility guards, transaction outcomes and receipts. They do
not establish Postgres isolation/lock behavior or production completeness; the
existing Authority real-Postgres correction coverage retains that responsibility.
