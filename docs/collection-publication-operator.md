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
write field explicitly. Apply refuses unless `HEROKU_APP_NAME=bainluck-heavy`,
before importing the database module or opening a connection. Preview remains
allowed anywhere with explicitly configured `DATABASE_URL`. Use an attended
`heroku run:detached -a bainluck-heavy` invocation (gotcha 48), then save the JSON
receipt from that named detached dyno's logs:

```sh
heroku run:detached -a bainluck-heavy -- python3 scripts/collection_publication.py \
  --container-id "$REVIEWED_ID" --slug "$REVIEWED_SLUG" \
  --operation publish --apply --expected-revision "$REVIEWED_REVISION" \
  --actor "$OPERATOR" --reason "$APPROVED_REASON" \
  --evidence "$REVIEWED_EVIDENCE_JSON"
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

## Theme collections (#9935)

The same `publish` / `withdraw` operations accept the two theme slugs the
registry builds, `ai` (continuing) and `oscars-2027` (finite edition). Any other
spelling (`ai-2026`, `oscars-27`) has no edition and is refused. A theme page is
served from the producer's immutable snapshot at the live revision, so stored
edges alone cannot show that the page will render. Preview and apply read that
snapshot at the target's revision, under the lock for an apply, using the
page's own bounded reader. Publication is refused when:

- `theme_snapshot_absent_at_revision`: there is no snapshot, so readers would
  get 503 "building".
- `theme_inventory_incomplete`: the pass behind it did not see the whole
  population.
- `theme_snapshot_empty`: the snapshot shows no members.
- `theme_snapshot_disagrees_with_membership`: a shown id has no edge, so the
  page would be served as "building".

None of these refuse a withdrawal. The receipt's `theme_snapshot` shows the
revision and the shown, eligible and withheld counts that would go live. A
publish or withdrawal bumps the revision and sends one `rebuild_theme_snapshot`,
so the page answers "building" until that rebuild writes the new revision's
snapshot on `worker-background` (main app; the apply dyno shares its Redis).

## Theme member corrections (#9936)

`withdraw-members` / `readmit-members --restore-from-ledger` also take `ai` and
`oscars-2027`, but only from a manifest whose pin says `"variant": "theme"`. A
theme slug without it, or an NFL/MLB pin that carries it, is refused before any
database. A pin with no `variant` is the original NFL/MLB shape, so existing
manifests and backups read exactly as before.

A theme target names a `theme_rule` market edge. It pins `edge_id`,
`edge_class`, `edge_source: "theme_rule"`, `market_id`, `venue`, `external_id`
and the market's stored `market_type` and `event_id` (either may be `null`). No
game, winner rule or admitted game edge is asked for, and none may be invented
to pass validation. The hub pin is the same as for sports: `slug`,
`publication_state`, `membership_revision`, `events` (0 for a theme),
`market_edges`, `targets` and `ledger_rows`. Under the root-first lock and the
market row locks, the apply refuses the whole hub before its first write if any
of these has drifted: the revision, publication state, ledger, edge counts, the
edge's container, class or source (another source's edge is not a theme member),
or the market's venue, external id, type or game link. A missing edge or market
refuses the same way.

Writes, preimage backup, fingerprint, ledger readback and receipts are the
sports path's. The correction helper sends one `rebuild_theme_snapshot` after
commit (one per hub transaction; none on rollback). While theme assembly is
stopped, that rebuild writes the corrected page only for a published
collection whose live revision has no page. It allocates the next revision
without a ledger row, so the withdrawn member is gone from the page, an old
`revision` is answered with the live page (`revision_moved`), and withdrawing
the last member gives an `empty` page, not "building". A duplicate delivery
writes nothing (`assembly_stopped_page_present`). Automatic assembly stays
stopped throughout.

Undo has two separate meanings. A bare `readmit_member` only lifts the
withdrawal and writes no edge: the member returns when an enabled assembly pass
proves it again under the theme's rule. This operator does not offer it. The
exact undo (`--restore-from-ledger --backup`) re-inserts the backed-up edge row
under the unchanged sports guards: hub at the backup's `post_revision`, no later
ledger row, same edge columns, free slot, unchanged market identity. Its theme
variant also requires the backed-up row to be this collection's own
`theme_rule` edge for that market. Its receipt states that the theme's rule,
not this tool, decides the restored member once assembly runs. The sports
"never re-proves" wording is not used for themes.

**Known limit.** The rebuild a withdrawal sends normally moves the hub one
revision past `post_revision`, with no ledger row. After that rebuild has run,
the exact undo refuses as a stale revision. The withdrawal receipt says so in
`undo.theme_limit`.

Coverage: `backend/tests/test_collection_publication_operator.py` (SQL double,
real helpers) and `backend/tests/integration/test_theme_collections_9935_pg.py`
(real Postgres, the real rebuild and page reader; CI `shared-tail`, PG15).
