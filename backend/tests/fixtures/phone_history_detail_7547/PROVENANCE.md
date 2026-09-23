# Provenance — `phone_history_detail_7547/`

Two named production specimens for the #7547 PHONE slice (the
`/api/futures/{id}/probability-timeline` reader `EvolutionChartView` mounts).
Both are derived VERBATIM from saved production `/history?hours=168` receipts;
no timestamp or value in either file was typed by hand.

| fixture | derived from | receipt sha256 | read at (UTC) | by |
|---|---|---|---|---|
| `61097129-receipt.json` | `artifacts/codex-7807-positive-review/61097129-history.json` | `e6aec14057477b7d2d64d2f92d3f78466d6624dca2ab06e59add892d043a3822` | 2026-09-22 ~18:26 | codex (#7807 positive review) |
| `56775596-receipt.json` | `artifacts/codex-7807-positive-review/56775596-history.json` | `12e0d3015125cfe22cd8e4fa9537f134327ee90f912a3ab11d37662a365fcd98` | 2026-09-22 18:26:21 | codex (#7807 positive review) |

The receipt directory lives in the repo checkout on Alex's Mac (`~/bainluck/artifacts/…`);
the raw bytes are also preserved beside this slice's report under
`artifacts/other-model-7547-phone-detail/inputs/`.

## What each fixture carries

* `outcomes[].captures` — every `/history` point WITHOUT `provenance: venue_history`
  (our own captures, `bookmaker: consensus`), as `[timestamp, probability]`.
* `outcomes[].venue` — every point WITH `provenance: venue_history`
  (`bookmaker: kalshi`), as `[timestamp, probability]`. A `/history` receipt's
  venue rows are the output of `_GenericVenueHistory.in_window` — the same call
  the phone route makes — so replaying them as the bank replays what the phone
  reader was handed.
* market identity (`source`, `external_id`, `mutually_exclusive`,
  `commence_time`, `created_at`) — from the PUBLIC detail read
  `GET https://api.bainluck.com/api/futures/{id}` on 2026-09-22 (raw bytes beside
  the report: `inputs/detail-{id}.json`).
* `outcomes[].replica_ticker` — NOT a venue fact. Kalshi leg tickers are in
  neither payload, so each leg is minted `{market external_id}-R{id % 1000}`.
  The identity binding (`validate_payload` / `kalshi_contract`) checks bank
  contract == seeded `FuturesOutcome.external_id`, and that is the only
  property these strings carry.

## What the replay cannot claim

* The bank rows are labelled `kalshi_candle_1m`. The tier label is not in a
  `/history` receipt; the real bank's FINEST declared tier is 1m, and the label
  drives exactly one thing — the ±30 s capture claim in `unclaimed_instants`.
* No bid/ask/last_price (not in a receipt). The support filter fails OPEN on
  absent columns, and the tests assert `unsupported_points_withheld == 0`, so
  the replay admits exactly the rows the receipt served.
* The 61097129 replay is read at a PRE-KICKOFF clock (2026-09-21T20:00Z); the
  receipt's bank was built after the game (2026-09-22T16:02Z). A bank built on
  the 21st would have had a different band layout for the last day, so this
  replay can UNDER-serve what a phone reader saw that day — never invent a row.

## Derivation

`artifacts/other-model-7547-phone-detail/derive_fixture.py` (deterministic;
re-running it on the same receipts reproduces these files byte for byte).
