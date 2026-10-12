# #5343 resolved zero-price legs: fixture provenance

`gamma-event-106884.json` is Polymarket Gamma `GET /events/106884` ("Fed rate cut
by...?", economy/fed tags, negRisk false, 13 markets), byte-identical to lane1's
capture for #5343 (`tests/fixtures/provider_event_collections_5343/` on PR #10916),
captured 2026-10-12T00:49:13Z from the public Gamma API, sha256
`5ce0eea19067bd1691544f8d650a501bb3a3ef3b31fd2c8f630267883068c224`. Copied, not
edited, so this slice does not depend on that PR landing first.

It is the PROVIDER's payload. Bain Luck never served it, and no test that reads
it proves anything about production.

What it holds that this slice reads: six legs `closed: true`,
`umaResolutionStatus: "resolved"`, `outcomePrices ["0","1"]`; seven open legs.
Every negative in the tests is derived from these real legs by changing one field.
