/**
 * First-party mirror of the three performance packets (LAT-P232, #2751).
 *
 * WHY THIS EXISTS. `first_card_ms` — the felt number, marked "🔴 THE NEEDLE" in
 * `lib/screenTiming.ts` — is computed on every screen arrival on every route and
 * then thrown away. Not for a privacy reason: `ScreenTimingReporter` and
 * `TelemetryGate` both say so in-source. It is thrown away because its only
 * transport is gtag, and the latency lane holds no GA credential, so the number
 * it exists to read is unreadable. This module gives it a second transport to a
 * first-party store the lane CAN read.
 *
 * WHAT IS MIRRORED, AND WHY IT IS NOT NEW COLLECTION. This is called from inside
 * `trackEvent`'s `sendEvent()`, immediately after `sanitizeEvent` returns and
 * after BOTH consent checks — so it receives the exact packet gtag receives,
 * post-sanitizer, from a reader who has already granted consent. It forwards
 * three event names and nothing else. Every field sent here is a field being
 * sent to Google in the same breath, for the same reader, under the same grant.
 *
 * The server does NOT trust any of that: `app/utils/client_timing_contract.py`
 * re-enforces the same per-event key allowlist, because this endpoint is public
 * and a browser-side allowlist is not a security boundary.
 *
 * WHAT IS NOT DONE HERE. The mirror sits behind the identical consent gate the
 * packets already sit behind. Un-gating it — so the number describes all readers
 * rather than the banner-answering subset, as Speed Insights already does under
 * ruling D30 — is Stage 2, is new collection from readers who declined, touches
 * `/privacy`, and is Alex's call. Nothing here anticipates it.
 *
 * WHY `fetch(keepalive)` AND NOT `sendBeacon`. The design artifact named
 * `sendBeacon`. It is the wrong primitive HERE: the API is cross-origin
 * (`api.bainluck.com` from `bainluck.com`), and a beacon carrying an
 * `application/json` Blob triggers a CORS preflight that a beacon fired during
 * unload will often lose. `fetch(..., { keepalive: true })` gives the same
 * survive-the-unload guarantee, handles the preflight normally, and is already
 * the idiom this repo uses for exactly this job (`lib/discoverInteractions.ts`).
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const INGEST_PATH = "/api/telemetry/client-timing";

/**
 * The three names mirrored. Must stay a subset of the events whose
 * `PERF_EVENT_KEYS` contract in `sanitize.ts` strips even the enrichment keys
 * (`session_id`, `platform`, `event_timestamp`).
 *
 * `feed_exit` is deliberately absent though it is also a perf event: it KEEPS
 * the enrichment keys, so it carries a client session marker, and a session
 * marker in a durable first-party table is a different privacy question than
 * the one this module answers.
 */
export const MIRRORED_EVENTS: ReadonlySet<string> = new Set([
  "screen_timing",
  "feed_telemetry",
  "web_vital",
]);

/** Mirrors the server's `MAX_EVENTS_PER_REQUEST`. */
export const MAX_BATCH = 20;

/**
 * How long a packet may wait for company before it is sent.
 *
 * Batching is not an optimisation here, it is a correctness requirement. One
 * screen arrival emits up to seven mirrored packets (one `screen_timing`, one
 * `feed_telemetry`, up to five `web_vital`). Sent individually those are seven
 * requests against the reader's OWN 60/minute anonymous rate-limit budget
 * (`app/utils/rate_limit.py`), which this endpoint shares with every real API
 * call the page makes — so an un-batched mirror would make the page's telemetry
 * compete with the page. Coalescing collapses a screen arrival into one request.
 */
export const FLUSH_DELAY_MS = 2000;

type Packet = { name: string; params: Record<string, unknown> };

let queue: Packet[] = [];
let timer: ReturnType<typeof setTimeout> | null = null;
let unloadHooked = false;

function clearTimer(): void {
  if (timer !== null) {
    clearTimeout(timer);
    timer = null;
  }
}

/**
 * Send whatever is queued. Best-effort by contract: a telemetry failure must
 * never surface on the reader's page, so every error path is swallowed.
 */
export function flushFirstPartySink(): void {
  clearTimer();
  if (queue.length === 0) return;

  const batch = queue;
  queue = [];

  try {
    void fetch(`${API_URL}${INGEST_PATH}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ events: batch }),
      keepalive: true,
      // No cookies: the sink must not be able to attribute a row to a session
      // even by accident. This is a property of the request, not a promise.
      credentials: "omit",
    }).catch(() => {});
  } catch {
    /* best-effort by contract */
  }
}

/**
 * Flush on the last moment the document is reliably alive.
 *
 * `visibilitychange`→hidden is the event that actually fires on mobile Safari
 * backgrounding; `pagehide` covers bfcache eviction. `unload` is deliberately
 * not used — it suppresses bfcache and is unreliable on iOS.
 */
function hookUnloadFlush(): void {
  if (unloadHooked || typeof document === "undefined") return;
  unloadHooked = true;
  const flush = () => {
    if (document.visibilityState === "hidden") flushFirstPartySink();
  };
  document.addEventListener("visibilitychange", flush);
  window.addEventListener("pagehide", () => flushFirstPartySink());
}

/**
 * Mirror one already-sanitized packet.
 *
 * Callers must have passed both consent checks and the sanitizer first — this
 * function re-checks the NAME but deliberately does not re-check consent, since
 * doing so would duplicate the gate rather than enforce it, and the one place
 * that can see the execution-time grant is `sendEvent` itself.
 */
export function mirrorToFirstPartySink(
  name: string,
  params: Record<string, unknown>
): void {
  if (typeof window === "undefined") return;
  if (!MIRRORED_EVENTS.has(name)) return;

  queue.push({ name, params });
  hookUnloadFlush();

  // A full batch goes now rather than waiting out the timer — otherwise a burst
  // would silently overflow the server's per-request cap and lose the tail.
  if (queue.length >= MAX_BATCH) {
    flushFirstPartySink();
    return;
  }

  if (timer === null) {
    timer = setTimeout(flushFirstPartySink, FLUSH_DELAY_MS);
  }
}

/**
 * Drop everything queued but unsent.
 *
 * Called from the consent-denial path in `core.ts` beside `cancelPendingSends`.
 * A packet admitted under a grant that has since been revoked must not land:
 * the queue can hold a packet for up to `FLUSH_DELAY_MS`, which is exactly the
 * window a revoke has to win.
 */
export function dropPendingFirstPartyMirror(): void {
  clearTimer();
  queue = [];
}

/** Test/introspection helper: how many packets are waiting to be sent. */
export function pendingFirstPartyMirrorCount(): number {
  return queue.length;
}
