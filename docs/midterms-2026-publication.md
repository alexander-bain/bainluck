# Midterms 2026 publication

PILLAR: DISCOVER. SHIP: one live collection for Congress control, balance of
power, eight close Senate races and three governors' races, with official
results replacing live probabilities. Deadline: Monday, November 2, evening
Pacific. The Discover and Politics pin ends after November 6 Pacific
(`2026-11-07T08:00:00Z`); the collection itself remains available.

## Integration and publication

Delivery Speed owns the next master integration and deployment. The feature
author opens one PR against master and does not merge or push master. Label
the PR `tier-b`: publication inserts production container/member rows and
records the decision in the existing correction ledger.

The existing publisher now accepts `--curated-manifest`, restricted to the
exact committed [Midterms manifest](../backend/data/collections/midterms-2026.json).
It previews without writes, refuses missing markets, unaligned balance-of-power
outcomes, changed revisions, extra members and nested children, and applies
membership plus publication in one transaction. It never replaces existing
membership or silently readmits a withdrawn race.

After this code reaches the coordinated integration, run the preview on the
configured database from `backend/`:

```sh
python3 scripts/collection_publication.py --slug midterms-2026 \
  --curated-manifest data/collections/midterms-2026.json \
  --operation publish --expected-revision 0
```

Revision `0` is for a new collection only. If it already exists, first preview
that exact slug with the ordinary operator, review its membership/revision,
and use the reviewed revision; do not substitute a newer number blindly.
The receipt includes `hand_curated_accepted` and a per-market `twin_report`.
`no_twin_found` means no aligned stored Polymarket twin in the targeted read;
`ambiguous` is distinct and never contributes to the blend.

Apply from the existing heavy app, with the actual PR number in the evidence:

```sh
heroku run:detached -a bainluck-heavy -- python3 scripts/collection_publication.py \
  --slug midterms-2026 --curated-manifest data/collections/midterms-2026.json \
  --operation publish --expected-revision 0 --apply --actor Alex \
  --reason 'Publish the reviewed Midterms 2026 collection' \
  --evidence '{"spec":"Alex and Fable, 2026-11-01","pr":"REVIEWED_PR_NUMBER"}'
```

Read the named dyno's logs and verify `committed=true`. The publisher itself
requires `HEROKU_APP_NAME=bainluck-heavy` for apply. The served API needs
`COLLECTIONS_ENABLED=true`, the existing `CONTAINER_COLLECTIONS_ENABLED=true`,
and the existing shared hub gate `CONTAINERS_READ_ENABLED=true`. Coordinate any
flag activation inside Delivery Speed's integration; restarting the current
web dynos independently can discard its fast deployments. The publisher does
not change flags.

Verify `/api/containers/midterms-2026`, `/collections/midterms-2026`, and the top
card on `/discover` and `/politics`. Confirm the 14 displayed markets, the four
sections and reviewed Senate order; the balance-of-power card combines 108619
and 112905. Compare the live Congress headline to the pin and read the actual
twin receipt before reporting which races lack a stored Polymarket twin.

## Visibility rollback

Use the existing guarded withdrawal, retaining members and ledger history:

```sh
python3 scripts/collection_publication.py --slug midterms-2026
# Review this fresh receipt, then use its exact ID and revision:
heroku run:detached -a bainluck-heavy -- python3 scripts/collection_publication.py \
  --slug midterms-2026 --container-id REVIEWED_CONTAINER_ID \
  --operation withdraw --expected-revision REVIEWED_REVISION --apply \
  --actor Alex --reason 'Withdraw Midterms publication' \
  --evidence '{"review":"FRESH_ROLLBACK_REVIEW"}'
```

Verify the named dyno's acknowledged commit, then the API's `withdrawn` state
and removal of both pins on the next refresh. Withdrawal preserves the URL
with an explicit unavailable state; it does not delete production rows.

## Verification limits for the author session

The publisher accepts the exact curated list in tests using the real correction
helpers through a SQL double. This proves the caller's guards and transaction
flow, not production row existence or Postgres isolation. Production preview,
the actual Polymarket twin report, upload and PR creation are blocked by this
session's external-network restrictions. No production rows have been written.
The 390 px local screenshot uses explicitly illustrative data. A normal build
cannot download Google Fonts in this session; local compilation uses Next's
font-response test hook with an installed monospace font, and the normal
network-enabled build remains an integration gate.
