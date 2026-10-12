# NFL week automatic publication (#5341) — operator and activation note

**Ship:** the next authority-defined NFL week becomes a complete usable hub
without a per-week declaration or publication command; wrong or partial weeks
stay withheld and corrected hubs stay corrected. Pillars: MATCHING / DISCOVER /
TRUTH. Code: `backend/app/utils/container_nfl_publication.py`, called once per
week from `backend/app/tasks/container_nfl_assembly.py`.

## What merging changes

Nothing on production. The policy has its own switch,
`CONTAINER_NFL_AUTO_PUBLISH_ENABLED`, unset by default. With it unset the policy
issues no database statement; each NFL week's pass report gains a
`publication` block reading `decision: disabled` plus `harvest_complete` /
`harvest_refusal` — what the harvest alone says, before any stored check.

It is NOT `CONTAINER_COLLECTIONS_ENABLED`. That switch lets the hourly pass
write NFL/MLB member edges; it never granted publication and still does not.

## What it does when on

Inside the same transaction as an applied week assembly (`run_nfl_collection`
→ `run_nfl_week_assembly`), after the edges are written, it publishes the hub
through `container_corrections.publish_container` — the helper and ledger the
reviewed operator (`scripts/collection_publication.py`) uses — with
`actor = auto:container_nfl_publication`, `expected_revision` pinned to the
revision read under the chain lock, and evidence naming the policy version, the
week's contest ids and member event ids. The pass commits the edges and the
publication together, or rolls both back.

It publishes only when all of these hold (each refusal is named in the report):

| Check | Refusal reason |
|---|---|
| authority named the week: season read, is the declared season, week scheduled | `schedule_season_unknown`, `schedule_is_another_season`, `week_not_in_schedule` |
| every contest is exactly one member game — compared as sets of contest ids, never counts | `contest_without_event_row`, `contest_with_duplicate_event_rows`, `week_contest_with_conflicting_identity`, `contests_not_exactly_members` |
| question read was not capped | `market_read_truncated` |
| no id-less or placeholder slot filed under this week | `week_slot_without_contest_id`, `week_slot_is_placeholder` |
| hub is `unpublished`, no prior publication decision, no member withdrawal | `publication_withdrawn`, `prior_publication_decision`, `member_withdrawn` |
| assembly ran clean, and the stored edges equal what this pass proved | `not_assembled`, `assembly_errors`, `stored_members_differ` (with the ids) |
| the reader's own eligibility (`collection_card`) accepts it as this exact week | `reader_ineligible:<why>`, `not_this_week_edition` |

Decisions: `published`, `already_published` (no write), `retained` (published
hub, this pass could not vouch — nothing changed), `withheld`, `not_applied`
(dry run), `disabled`.

## What it never does

Never withdraws, unpublishes, re-publishes a `withdrawn` hub, adds a member or
commits. A schedule outage or a partial re-read of a published week leaves it
published (`retained`, or the collection's own `schedule_unreadable` run).
Taking a hub back remains a named decision: the operator's `withdraw`.

`stored_members_differ` is the expected refusal when the authority moves a game
to another week after it was edged: assembly never retires an edge, so the old
week holds a game that is no longer its own. Correct it with the operator's
reviewed `withdraw-members`; the policy then still waits for a person
(`member_withdrawn`), by design.

## Activation (not authorized by this change)

Authority owns the activation decision. Preconditions, in order:

1. #9651's correction schema is applied on the target database (else every
   decision is `withheld: publication_schema_absent`).
2. The hourly pass is running the NFL collection (`CONTAINER_COLLECTIONS_ENABLED`
   on, or an explicit `only=nfl-<season>` dispatch).
3. Read at least one pass report with the switch off and check `publication`
   for the current week reads `harvest_complete: true` where expected.
4. Set `CONTAINER_NFL_AUTO_PUBLISH_ENABLED=true` on the main app (`bainluck`):
   `assemble_containers` runs there on the `background` queue and is not in
   `HEAVY_TASKS`. Production config vars are attended.

Undo: unset the switch — later passes stop deciding. A hub it already published
is withdrawn with the reviewed operator (`--operation withdraw`); the ledger row
it wrote names `actor = auto:container_nfl_publication` and the policy version.
Nothing here restores `unpublished` (the helpers have no such action).
