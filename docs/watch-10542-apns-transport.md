# Background Live Activity transport source

PILLARS: TRUTH · FORMATTING.
SHIP: Continue the selected game's reading while the signed-in phone app is suspended.

This source supplies one bounded HTTP/2 update/end request for the existing
delivery command. It is not mounted in a worker or API. No Apple configuration,
credential acquisition, signing-key creation, database operation or real APNs
send is part of this slice. All tests use injected fake transports.

The caller supplies an approved app bundle/environment, a currently valid APNs
provider JWT, and the account-owned registered activity token. TLS verification
is enabled; environment selects only Apple's two fixed hosts. A real sender uses
the declared httpx HTTP/2 extra. It bypasses AsyncClient's ordinary URL-bearing
INFO log, never logs credentials/exceptions, and returns only fixed outcomes.
Custom observability must not capture request URL paths or authorization headers.

The command body and observation clocks remain byte-for-byte unchanged. A stable
UUID derived from the logical command ID supplies apns-id across retries; this
does not promise APNs exactly-once delivery. There are no internal retries,
redirects, alerts or implicit source timestamps. Per-operation and overall time
limits bound requests, cleanup is separately bounded, and response size is capped.

200 means APNs accepted the request, never proof the device received/displayed
it. 410 signals an unavailable token. Other 4xx failures reject the request without
claiming token revocation; 429/5xx and network failures are retryable. The future
durable worker must honor both Retry-After forms and its finite retry policy,
fence attempt acknowledgments, recheck active ownership before sending, cancel
old-token work after replacement/revocation, and stop after authoritative end.

Still required: durable registry/state/transport composition; approved provider
credentials/configuration; phone push-token acquisition and logout reconciliation;
composed Swift decoding; hosted gates; physical suspended-device acceptance #10543.
Public Watch and foreground activity remain account-free. No release claim.
