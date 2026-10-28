# #10090 passive held-page case recorder (#11674)

**PILLARS: TRUTH / FORMATTING. SHIP:** the predeclared 180-second held production web case can be scored from evidenced eligibility to headline and chart. #10090 can only finish when that case passes.

This is a recorder, not a verdict. It records one held product page for one predeclared case and stops. Measurement binds it to a case. Speed's operative grant supplies every limit. Scoring happens elsewhere (`../compare/score.py` and Measurement's adapter).

## Commands

```sh
node passive_case_recorder.cjs --help
node passive_case_recorder.cjs validate --scope production --manifest M.json --manifest-sha256 HEX \
  --grant G.json --grant-sha256 HEX
node passive_case_recorder.cjs record --scope production --manifest M.json --manifest-sha256 HEX \
  --grant G.json --grant-sha256 HEX --out NEW_DIR --playwright-module DIR \
  --browser-channel chrome|chromium --browser-mode multi-process|single-process
```

Every option is required and none has a default. `validate` is offline: it hashes files, checks schemas, case edges, grant limits and timing, and opens no socket. `record` re-runs the same validation, refuses an existing `--out`, and re-hashes every pin immediately before the first navigation. Exit codes:

- `0`: the case window was recorded with complete coverage.
- `1`: recorded, but STOPPED or UNRESOLVED. This is a result.
- `2`: recorder failure.
- `3`: refused before any network.

`--scope local` refuses every non-loopback origin, even one the manifest or grant names. `--scope production` refuses to start if the qualification fault variable is set. Otherwise both scopes run the same code.

## What a run does

1. Validates the manifest and grant, then waits for the manifest's earliest setup edge. It refuses if it is already past the setup cutoff. There is no rolling start and no later case.
2. Starts a loopback transport proxy and launches one browser that routes only through it. Loopback traffic is not bypassed.
3. Before navigation, installs a passive `EventSource` subclass. It keeps the product's constructor arguments unchanged and only adds listeners for every event type the product handles. Each listener forwards the raw `data` before anything parses it. There is no second subscription and no URL rewrite.
   The case stream is the EventSource on the manifest's stream path. Other product EventSources, such as the page's market stream, are recorded raw and counted against requests and response bytes, but they are not subject to case-envelope or duplicate-stream checks.
4. Opens the manifest's product page and, if the manifest names it, opens the "Probability observed" readout. It then installs the staged primary recorder (`primary_recorder.cjs`, byte-for-byte) and the 100 ms sampler. The sampler uses `../compare/display_sample.cjs`, unchanged and hash-pinned, and adds full chart geometry: path `d` (whole when it changes), bounding boxes, ticks, and endpoint/callout attributes. All of this must finish before the setup cutoff.
5. Exchanges clocks at setup, T0−5 s, T0, every 15 s, T0+180 s and the end.
6. A single watchdog ends acquisition at T0+185 s on the collector's monotonic clock. It fires even on a quiet or hung stream. A cap, error or cancellation ends it earlier with a STOP.
7. Teardown is bounded. It stops the sampler, exports the primary recorder, closes the browser and transport, and writes `STOP.json` and `SUMMARY.json` from the reserved budget.

Output (`--out`):

- `BINDINGS.json`: recorder/sampler/Playwright hashes, browser channel and mode, the byte boundary, constants and the clock anchor.
- `records.jsonl`: every receipt, written immediately with one sequential id.
- `STOP.json`: the reason and all counters.
- `SUMMARY.json`: coverage, holes, faults and the clock exchanges.

## Manifest (`bainluck.passive-case-manifest/1`) and grant (`bainluck.passive-case-grant/1`)

Unknown keys refuse, and so do duplicate JSON keys. Every referenced file is `{path, sha256}` and re-hashed. The authoritative list is `contract.cjs`.

- **Manifest:**
  - `policy`, `case_id`, and `selection` (selected_at, max_age_s, selected_by, inventory evidence/order/rejections/replacement_rule).
  - `event`: canonical id, members (strictly increasing, including the event), contributing sources with contract and orientation.
  - `owner_receipts`: backend/worker/frontend source sha + pinned release receipt, authority incarnation/namespace, pinned preview-activation evidence.
  - `entry`: page_url must be `/events/{id}`; api_origin; readout_activation; expected_stream_url must equal `{api}/api/events/{id}/stream?preview_protocol=authority-v3`; expected stream events.
  - `trace` (or null), `cleanup.custody`, and `page` (viewport, exactly one held page, visibility requirements).
  - `clock`: t0_utc, scoring fixed at 0..180000 ms, acquisition fixed at −5000..185000 ms, setup earliest/cutoff ≤ −5000 ms.
- **Grant:**
  - Identity, issue/expiry (it must outlive the acquisition end), and `manifest_sha256`/`case_id` binding.
  - `allowed_origins` and `allowed_routes` (origin, methods, path prefix, resource types).
  - `detail_requests`: at most two, explicit, each at a declared offset inside the window.
  - `limits`, all finite positive integers: `max_request_attempts`, `max_eventsource_constructions`, `max_stream_attempts` (case stream), `max_active_streams` (exactly 1 case stream), `max_response_bytes`, `max_stream_bytes`, `max_request_bytes`, `max_record_bytes`, `max_saved_bytes`, `reserved_stop_bytes`, `max_queue_records`, `max_detail_requests` (0..2), and `received_overshoot_bytes` (≥ 65536, see below).

## Ceilings: where each is enforced

| Ceiling | Boundary | Overshoot |
|---|---|---|
| request attempts | browser route layer, checked **before** `continue`. Refused-by-grant requests never leave. Redirect hops and any request the route never saw are counted when they settle. | 0 for routed requests. A redirect hop the route does not see is counted after the fact; qualification measures which applies. |
| response bytes (all HTTP + the product stream) | loopback proxy, counted **before** each write to the browser socket. The chunk that would cross the cap is never forwarded. | forwarded: **0**. Received and discarded: ≤ one socket read (libuv 64 KiB), which the grant must authorize. |
| product stream bytes (sub-ceiling) | CDP `Network.dataReceived` (encoded) for the case stream URL | **not enforceable; diagnostic only.** Measured against a 500,000-byte sub-cap: one run had counted 18.9 MB when it reacted; in another, a 50 MB loopback burst starved the recorder's loop, so CDP counted 0 before the hard ceiling tripped. The product stream's enforceable ceiling is `max_response_bytes`. A hard per-stream boundary under https would need TLS interception at the proxy (a local CA), which this recorder deliberately does not do. |
| request bytes | loopback proxy, before writing upstream | 0 |
| saved bytes | journal; ordinary records stop before `reserved_stop_bytes` | 0. STOP/SUMMARY spend only the reserve; a minimal form is written if the full one does not fit. |
| page queue | in-page outstanding-binding counter; drops are counted and reported | explicit loss, a coverage hole. |

Counted bytes are **encoded wire bytes**. HTTP bodies pass through with their `Content-Encoding` untouched. An https origin is a CONNECT tunnel whose TLS records are counted, which is never less than the response bytes inside. Streams without `Content-Length` are counted chunk by chunk.

## Clocks

The comparison clock is the collector's monotonic clock relative to T0. Each exchange retains:

- the collector monotonic/wall bracket;
- the document's `performance.now()`, `timeOrigin` and `Date.now()`;
- the offset interval and read uncertainty.

These are loud faults:

- the offset interval leaves the running intersection (2 ms tolerance);
- the collector's wall-minus-monotonic moves more than 50 ms (wall jump or suspend);
- `timeOrigin` changes (document replaced);
- a read takes more than 250 ms.

Worker, Redis and DB clocks are **not** mapped by the page recorder. Missing upstream mapping stays unresolved eligibility.

## Coverage, holes and faults

`COMPLETE` requires:

- both 180 s edges covered;
- no sample gap over 300 ms;
- headline and chart `present` and visible (and in the viewport if required) for every in-window sample;
- every expected stream event seen;
- no stream outage, page-queue loss or oversize record, and no fault.

Faults are recorded with raw evidence and include:

- malformed/duplicate-key JSON, wrong event/members/domain/session, missing/duplicated `preview_protocol`;
- a parallel subscription, document replacement and clock faults.

A reconnection (native retry or the product's own reopen) is a retained `stream-outage` hole from the error/close to the next open. It is never bridged.

## Local qualification (`qualify.cjs`)

```sh
node qualify.cjs --arm fixture --out NEW_DIR --playwright-module DIR --browser-channel chromium --browser-mode single-process
node qualify.cjs --arm product-lab --lab-facts FACTS.json --out NEW_DIR --playwright-module DIR --browser-channel chromium --browser-mode single-process
```

Each control writes its own pinned case, labelled LOCAL QUALIFICATION, and runs the recorder as a subprocess in `--scope local`. It then checks the recorder's own STOP, SUMMARY and journal.

- `fixture_arm.cjs` is synthetic: a page with the same DOM contract and one EventSource, against a scripted SSE stream. It covers refusals, malformed and mismatched frames, hidden or unsupported surfaces, every ceiling (including TLS CONNECT), quiet and hung streams, reconnects, clock faults, export loss and cancellation.
- `product-lab` drives the real product page served by the #10669 lab. The lab scenario is started by the harness at T0, never by the recorder.
- Qualification faults are injected only through `PASSIVE_RECORDER_QUAL_FAULT`, which production scope refuses.

Browser-free units: `node --test test_recorder_units.cjs`.

**A qualification covers the browser channel and mode it ran in, and nothing else.** A sandboxed lane shell can launch only Playwright's bundled Chromium with `--single-process`; system Chrome and multi-process Chromium die on the macOS Mach-port rendezvous there. A production invocation in another mode needs its own qualification run first.

No production run is authorized by this tool or its qualification.
