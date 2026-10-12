# Provider event collections — consumer and activation contract (#5343, #5344)

PILLARS MATCHING · DISCOVER · TRUTH. SHIP: a politics, economics, technology or
entertainment event on Polymarket becomes one complete collection at a stable URL,
and the next provider event uses the same code with no member list.

Source: `backend/app/utils/provider_event_collections.py` (the rules, pure) and
`backend/app/tasks/provider_event_collection_assembly.py` (the writer). The writer
is **not mounted** and sits behind `PROVIDER_EVENT_COLLECTIONS_ENABLED`, which is
unset everywhere.

## 1. Identity and destination

| | |
|---|---|
| Identity | Polymarket's immutable `event.id`, read from `group_id = 'polymarket:{id}'`. When a row also carries `market_metadata.polymarket_event_id`, the two must agree. |
| Slug / URL | `polymarket-event-{id}` → `/collections/polymarket-event-{id}`, `/api/containers/polymarket-event-{id}`. Built from the id only, so a renamed event keeps its URL. `edition_for_slug` returns `null` for it. |
| Label | The provider's event title (`containers.name`). It is updated when the provider renames the event. It never decides membership. |
| Container | `kind = 'theme'` (the closed vocabulary has no provider-event kind; no reader branches on it). `category` = the event's single domain. `window_start` / `window_end` = the provider's own event dates. `status` = `final` only when the provider's roster says the event is closed. |
| Edges | `contains`, `source = 'venue_grouping'`, `class = 'unclassified'`, confidence 1.000, child type `market`. |
| Provenance | One `container_member_decisions` row per child (`rule_version = provider-event-v1`). Its evidence names the provider, the event id, the `group_id`, the member's condition id, the identity signals used, the roster instant and state, and the provider's closed flag. |

Supported domains (`llm_sport_category`): politics, geopolitics, economics, tech,
entertainment. Sports events (which have game pages and NFL/MLB adapters), crypto,
mixed-domain events and events with no domain link nothing. A collection is minted
only when an event has at least 2 admissible members. Single-market and negRisk
events are one row each, so they never mint one.

## 2. Completeness: the roster ingestion must stamp (NOT stored today)

A collection is complete only against the provider's own full market list for
that event. Ingestion writes no such list today. It stores `market_count`, which
is not enough, because ingestion skips markets with no positive price. Proposed
key on the **parent** row's `market_metadata`:

```json
"polymarket_event_roster": {
  "observed_at": "2026-10-12T00:49:13+00:00",
  "complete": true,
  "event_closed": false,
  "markets": [{"id": "0x<64 hex conditionId>", "closed": false}]
}
```

`complete` must be literally `true`, written only when the payload was the whole
event. Ids must be condition ids, each listed once, and the list must not be
empty. Any doubt reads as `roster_malformed`.

Complete means: a usable roster (no older than the newest roster already
applied), every listed market held as a row of this event, no identity conflicts,
and one supported domain.

## 3. What a pass changes (correction policy, #5344)

- **Admits** a row that claims this event and is listed by a usable roster. With
  no usable roster, it admits on row identity alone. The collection still
  assembles, but it is never complete.
- **Removes** a member only when (a) a correction withdrew it, (b) its own row now
  names another event, or (c) a usable roster no older than the last one applied
  no longer lists it.
- **Never removes** anything because of an outage: no roster, an older roster, an
  expired roster, or a row we cannot see. The last good membership is carried.
- **Never resurrects**: a member a roster removed stays out until a newer roster
  lists it again. Every decision row carries the newest applied roster instant
  (`applied_roster_at`), so a stale pass cannot reset it.
- **Corrections** use the existing ledger (`container_corrections`) and the
  existing row lock. A withdrawn member is excluded on every later pass, and
  `readmit_member` writes no edge (the next pass re-proves the member).
  Publication is never changed by a pass.
- **One transaction per event**, under `lock_container_chain`, with every read
  inside the lock. Revision moves at most once per pass, and only when membership
  or the header changed. An unchanged pass writes nothing.

## 4. Publication eligibility (structural; publishes nothing)

`evaluate_provider_event_collection(session, slug, now=…)` returns `eligible` and
the named refusals: `domain_unknown|domain_ambiguous|domain_unsupported`,
`roster_absent|roster_malformed|roster_older_than_applied`, `roster_expired`
(older than 6 h), `roster_members_unstored`, `identity_conflicts`,
`too_few_members` (fewer than 2), `label_absent`, `retired` (14 days after a
closed provider window), and `publication_withdrawn` (re-publishing is a named
decision). A publisher calls it inside its own `lock_container_chain`
transaction.

## 5. Reader contract

The existing route serves a published collection through the simple envelope
with no change. `edition: null`, one section `unclassified` holding every member
as a market card, and `withheld` naming members whose row is gone. Readers should
present `unclassified` here as the collection's single list. It means "the
provider grouped these", not "we could not place this". Nothing in a collection
is a blended or averaged number. Members are independent questions.

## 6. Mounts still owed (each a disjoint owner's file)

| # | File | Owner | What |
|---|---|---|---|
| 1 | `backend/app/tasks/polymarket.py` (parent `poly_metadata`, beside `market_count`) | Polymarket ingestion (current Live ingestion claim) | Stamp `polymarket_event_roster` per §2 from the event payload already in hand. |
| 2 | `backend/app/tasks/polymarket.py` (sub-market loop, `prob <= 0: continue`) | same | Closed legs priced Yes = 0 never become rows, so an event with resolved-No legs can never be complete. Store them as resolved rows. |
| 3 | `backend/app/tasks/__init__.py` + `tests/test_tasks_wiring.py` | Integrator / Containers | Celery wrapper `assemble_provider_event_collections` that persists `resume_after` between runs. **No cadence is authorized**: a beat entry needs the coordinator's word. |
| 4 | `backend/scripts/collection_publication.py` (#9916 operator; PR #10902 in flight) | Authority | A `polymarket-event-*` preflight that calls `evaluate_provider_event_collection` under the lock. |
| 5 | `backend/app/services/container_discovery.py` / `routes/containers.py` `/discover` (`league` is NFL/MLB only) | Containers / Discover (#9925) | List published provider-event collections. |
| 6 | web `/collections/[slug]`, native hub (#9652 / #9653) | ux / native | Render the §5 envelope. |
| 7 | `backend/app/utils/container_graph.py` (optional) | Authority | A `provider_event` container kind and an `event` anchor id kind, so the immutable id can live in `container_provider_anchors`. Until then the unique slug is the identity. |

## 7. Activation and rollback

Activation, in order: mount 1 live on `bainluck-heavy` → mount 3 (no beat) → one
dry run (`apply=False`) read by the operator → flag `PROVIDER_EVENT_COLLECTIONS_ENABLED=true`
on `bainluck-heavy` (attended config) → one attended run → review the eligible
list → publish slug by slug through the operator.

Rollback:
- **Stop writing**: unset the flag.
- **Take a collection off readers' screens**: `withdraw_publication` through the
  operator. The URL is kept.
- **Remove everything** (after `pg_dump -t` of the three tables): delete the
  edges first, because `event_edges` has no FK:
  `DELETE FROM event_edges WHERE parent_type='container' AND source='venue_grouping' AND parent_id IN (SELECT id FROM containers WHERE slug LIKE 'polymarket-event-%');`
  then `DELETE FROM containers WHERE slug LIKE 'polymarket-event-%';`, which
  cascades the decisions and corrections.
