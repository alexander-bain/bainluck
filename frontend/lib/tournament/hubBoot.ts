/**
 * LAT-P217 — the tournament hub's request leaves at PARSE time, not after hydration.
 *
 * WHY THIS SURFACE, AND WHY NOW. On the corrected (hero-based) felt table the US Open hub is the
 * worst row a reader on a phone meets: **3,726 ms to the first real card on Chrome's Slow-4G profile**,
 * against a 3 s target, measured from production on 2026-09-02. The waterfall says where those seconds
 * go, and it is not bytes:
 *
 *     0 -  643 ms   the HTML             (TTFB 50 ms — the rest is one 562 ms round trip)
 *   625 - 2395 ms   CSS + 20 JS chunks   (all in parallel, bandwidth-bound)
 *        2144 ms    first paint
 *   2489 - 3690 ms  /api/tournaments/us-open   <- STARTS 345 ms AFTER the paint, 1,846 ms after the
 *                                                 HTML was already in the browser's hands
 *        3726 ms    first real card
 *
 * The hub's one API call cannot start until every chunk of the entry graph has downloaded, parsed,
 * executed and hydrated, because it is issued from an effect. Nothing about it needs to wait: it is a
 * GET with no body, no session and no principal. So this module parks that fetch in the document, the
 * way `lib/discover/feedBoot.ts` (LAT-P184) already does for Discover's `/api/feed`.
 *
 * WHY A SEPARATE MODULE RATHER THAN A PARAMETER ON feedBoot. The two boots agree on mechanism and
 * disagree on the only thing that matters — WHO MAY BE SERVED THE PARKED RESPONSE. Discover's feed is
 * personalised, so its eligibility is a proven subset of `decideFeedPrincipal` over four device-state
 * keys. The hub is not personalised at all, so those four keys are irrelevant here and importing them
 * would state a constraint this surface does not have. Generalising feedBoot into a shared engine
 * would have meant editing the guarded path LAT-P184 shipped; the duplication is ~40 lines and the
 * shared constant that actually matters (`BOOT_AUTH_KEY_PREFIX`) IS imported, not copied.
 *
 * WHO IT FIRES FOR. Signed-out readers only. Not because the endpoint is personalised — it takes
 * `(slug, db)` and no principal — but because that keeps the correctness argument LOCAL to this file:
 * for a signed-out reader the client's own request is byte-identical to the boot request (same URL, no
 * `Authorization` header), so claiming the parked response cannot hand anyone a body their own request
 * would not have produced. A signed-in reader gets exactly today's behaviour. Making the boot depend
 * on the backend staying principal-free would be a cross-repo invariant with no guard on it.
 */

import { BOOT_AUTH_KEY_PREFIX, type FeedBootRecord } from "@/lib/discover/feedBoot";

/** Where the hub document parks its boot record. Distinct from Discover's slot so a claim can never
 *  cross surfaces even before the URL check runs. */
export const HUB_BOOT_GLOBAL = "__blHubBoot";

/**
 * THE TWO HALVES OF THE HUB PAYLOAD (latency/135).
 *
 * Measured on production 2026-09-03: the full response is 902,423 bytes (86,838 gzipped) and 76% of
 * it renders nothing on the first screen — `grids` is the Bracket tab, `results` is the finished list
 * below the day's card. `first` is 207,193 bytes (19,822 gzipped) — 77.2% off the wire.
 *
 * The names are the SERVER's (`app/routes/tournaments.py`, `SECTION_FIRST` / `SECTION_REST`) and an
 * unknown one is a 400, not a full payload — so a typo here fails loudly on the first render rather
 * than quietly shipping none of the saving.
 */
export const HUB_SECTIONS_FIRST = "first";
export const HUB_SECTIONS_REST = "rest";

/**
 * The path `fetchTournament` puts on the wire. Exported and CONSUMED by `fetchTournament` itself, so
 * the boot URL and the real URL are one expression rather than two that must be kept equal —
 * LAT-P184's URL-identity failure mode (a silent duplicate request while every test still passes)
 * cannot arise if there is only one builder.
 *
 * `sections` is part of the path for exactly that reason. `claimHubBoot` matches on the whole URL, so
 * a boot that parked `?sections=first` and a page effect that asked for the full payload would not be
 * a wasted claim — it would be TWO requests, the slow one on the critical path. One builder, one
 * argument, and the jest suite pins that the boot script and the fetcher produce the same string.
 */
export function hubBootPath(slug: string, sections?: string): string {
  const path = `/api/tournaments/${encodeURIComponent(slug)}`;
  return sections ? `${path}?sections=${encodeURIComponent(sections)}` : path;
}

/** The absolute URL for `hubBootPath()` against an API origin. */
export function hubBootUrl(apiBase: string, slug: string, sections?: string): string {
  return `${apiBase}${hubBootPath(slug, sections)}`;
}

/**
 * May the document boot-fetch, given the full list of localStorage keys?
 *
 * Pure, so the rule is a table test rather than a browser observation. The only disqualifier is a
 * persisted Firebase user: `lib/firebase.ts` sets `browserLocalPersistence` FIRST, ahead of IndexedDB,
 * precisely so this is synchronously readable at parse time.
 */
export function hubBootEligibleFromKeys(keys: readonly string[]): boolean {
  for (const key of keys) {
    if (key.startsWith(BOOT_AUTH_KEY_PREFIX)) return false;
  }
  return true;
}

/**
 * The inline `<script>` body rendered into the hub document.
 *
 * Generated from the helpers above so the script and the claim can never describe different requests.
 * Everything is wrapped in one try/catch: a private-mode localStorage throw, a blocked fetch or a
 * missing `performance` must leave the page exactly as it is today.
 */
export function hubBootScript(apiBase: string, slug: string): string {
  // THE FIRST SCREEN, NOT THE PAGE (latency/135). The parked request is the one the reader is
  // waiting on, so it asks for the 20 KB half rather than the 87 KB one. The `rest` request is
  // issued from the page's own effect after the first render and is deliberately NOT booted: it is
  // off the critical path by construction, and parking a second promise would put 67 KB back on the
  // wire beside the bytes this change exists to get out of the way.
  const url = JSON.stringify(hubBootUrl(apiBase, slug, HUB_SECTIONS_FIRST));
  const authPrefix = JSON.stringify(BOOT_AUTH_KEY_PREFIX);
  const slot = JSON.stringify(HUB_BOOT_GLOBAL);
  return (
    `(function(){try{` +
    `var w=window,s=w.localStorage;if(!s)return;` +
    `for(var j=0;j<s.length;j++){var k=s.key(j);if(k&&k.indexOf(${authPrefix})===0)return;}` +
    `var n=function(){return (w.performance&&w.performance.now)?w.performance.now():Date.now();};` +
    `var r={url:${url},startedAt:n(),readyAt:null,response:null};` +
    `var p=fetch(r.url).then(function(x){r.readyAt=n();return x;});` +
    // Mark the rejection handled here so a dead network cannot surface as an unhandled rejection
    // before the app has hydrated enough to claim it.
    `p.catch(function(){});` +
    `r.response=p;w[${slot}]=r;` +
    `}catch(e){}})();`
  );
}

/**
 * Claim the parked hub response for a request the caller is about to issue.
 *
 * Returns the record only when its URL matches `expectedUrl` exactly — a hub document that parked
 * `/api/tournaments/us-open` can never satisfy a request for `/api/tournaments/roland-garros`. The
 * record is CONSUMED either way: a boot fetch aimed at a different request is dead weight, and leaving
 * it parked would let a later navigation pick up a stale body.
 */
export function claimHubBoot(
  expectedUrl: string,
  scope?: Record<string, unknown>
): FeedBootRecord | null {
  const host =
    scope ??
    (typeof globalThis === "undefined"
      ? undefined
      : (globalThis as unknown as Record<string, unknown>));
  if (!host) return null;

  const parked = host[HUB_BOOT_GLOBAL];
  if (parked === undefined) return null;
  delete host[HUB_BOOT_GLOBAL];

  if (!parked || typeof parked !== "object") return null;
  const record = parked as FeedBootRecord;
  if (record.url !== expectedUrl) return null;
  const response = record.response as Promise<Response> | null;
  if (!response || typeof response.then !== "function") return null;
  return record;
}

/**
 * How long the consumer waits for a parked response before abandoning it.
 *
 * A parked fetch has no timeout and no retries — it is a bare `fetch()` in a script tag. `apiFetch`
 * has both (20 s per attempt, two retries), and during the multi-minute database spells of #2724 a
 * bare await on the parked promise would strand the reader on a skeleton for as long as the server
 * held the connection. So the claim is RACED against this deadline and falls through to the normal
 * retrying path when it expires. The deadline matches `apiFetch`'s own per-attempt timeout so the
 * worst case is one extra attempt's wait, not an unbounded one.
 */
export const HUB_BOOT_CLAIM_TIMEOUT_MS = 20000;
