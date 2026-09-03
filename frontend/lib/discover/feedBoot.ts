/**
 * LAT-P184 — the first screen's request leaves at PARSE time, not after hydration.
 *
 * D-C (Alex, 2026-09-01): *"stage the loading so that the user sees SOMETHING
 * that they can interact with functionally instantly while we continue to load
 * the rest."* The nav, the Discover header and the nine skeleton cards already
 * arrive as server-rendered HTML in a 32 KB document at ~50 ms TTFB — that half
 * of staged loading is done. What is NOT staged is the DATA: the `/api/feed`
 * request that turns skeletons into cards is issued by SWR from an effect, so it
 * cannot start until every render-blocking chunk of the entry graph has
 * downloaded, parsed, executed and hydrated. Measured on production
 * 2026-09-01 (22 chunks, ~201 KB compressed excluding the `noModule` polyfill),
 * the feed body was ready at 853-875 ms serialised behind the chunks and at
 * 573-580 ms when issued in parallel with them — and that comparison EXCLUDES
 * parse/execute/hydrate CPU, which is additive to the serialised arm only.
 *
 * So this module parks one `fetch()` for the first screen in the document
 * itself. It is deliberately not a `<link rel=preload>`: a preload is claimed by
 * URL+mode matching inside the browser's cache and silently degrades to a SECOND
 * request when the match is imperfect, which is precisely the duplicate-feed
 * defect LAT-P171/P172 spent two cycles removing. Handing over the Promise makes
 * the hand-off explicit and single-valued.
 *
 * WHO IT FIRES FOR, AND WHY THAT SET IS NARROWER THAN IT COULD BE.
 * Only a reader the device can PROVE is a brand-new, signed-out, zero-interaction
 * visitor — the exact principal `decideFeedPrincipal` routes to the shared warm
 * `anon` cache key (`sharedAnonFeed.ts`), whose request carries no `x-session-id`
 * and no `Authorization`, and which the prewarm beat keeps warm (measured
 * `x-feed-cache: hit`, `x-feed-elapsed-ms` 6.96-7.08 ms). `bootEligibleFromKeys`
 * is a strict SUBSET of that decision, not a re-derivation of it: it fires only
 * when all four device-state keys are ABSENT, where the real decision also
 * accepts keys that are present but empty. Being narrower can only cost the
 * optimisation, never correctness — and `feedBootIsSubsetOfSuppression` in the
 * guard suite proves the containment over the whole 32-state key power set.
 *
 * AND THE CONSUMER VALIDATES ANYWAY. `claimBootFeed` hands the parked response
 * back only when the caller's own URL matches byte-for-byte, and consumes the
 * record either way, so a boot fetch that fired for the wrong reader costs one
 * warm 7 ms request and can never be rendered to them.
 */

import { FEED_EVENT_PCT, initialFeedRequest } from "@/lib/discover/feedPaging";

/** Where the document parks the boot record. Read once, then deleted. */
export const FEED_BOOT_GLOBAL = "__blFeedBoot";

/**
 * Device-state keys whose PRESENCE proves this is not a brand-new install.
 * Mirrors the storage keys owned by `sharedAnonFeed.ts` — renaming any of them
 * is a data migration there and must be mirrored here, which
 * `feedBootMirrorsPrincipalKeys` in the guard suite asserts.
 */
export const BOOT_BLOCKING_KEYS: readonly string[] = [
  "bainluck_session_id",
  "discover_interaction_profile_v1",
  "discover_dismissed",
  "discover_has_swiped",
];

/**
 * Firebase persists the signed-in user under `firebase:authUser:<apiKey>:[NAME]`
 * in localStorage (`lib/firebase.ts` sets `browserLocalPersistence` FIRST,
 * ahead of IndexedDB, precisely so this is synchronously readable). A signed-in
 * reader must never be served the shared anonymous feed, and auth restore is
 * async, so the presence of that key is the only synchronous signal available
 * at parse time.
 */
export const BOOT_AUTH_KEY_PREFIX = "firebase:authUser:";

/** The record the document parks for the app to claim. */
export interface FeedBootRecord {
  /** The absolute URL the boot fetch was issued against. */
  url: string;
  /** `performance.now()` when the fetch was issued. */
  startedAt: number;
  /** `performance.now()` when the response headers arrived, or null if pending. */
  readyAt: number | null;
  /** The in-flight (or settled) response. */
  response: Promise<Response> | null;
}

/**
 * The path the SWR-owned initial Discover request issues for a shared-anon
 * reader, built from the SAME constants that request is built from. A drift
 * here does not break anything — the claim simply misses and the normal fetch
 * runs — but `feedBootUrlMatchesTheRealRequest` pins it against the URL
 * `fetchFeed` actually puts on the wire.
 */
export function bootFeedPath(): string {
  const { limit, offset } = initialFeedRequest();
  const params = new URLSearchParams();
  if (limit) params.set("limit", limit.toString());
  // `fetchFeed` omits a zero offset entirely (`if (params?.offset)`), so the
  // boot URL must omit it too or it is a different URL.
  if (offset) params.set("offset", offset.toString());
  params.set("event_pct", FEED_EVENT_PCT.toString());
  return `/api/feed?${params.toString()}`;
}

/** The absolute URL for `bootFeedPath()` against an API origin. */
export function bootFeedUrl(apiBase: string): string {
  return `${apiBase}${bootFeedPath()}`;
}

/**
 * May the document boot-fetch, given the full list of localStorage keys?
 *
 * Pure, so the containment proof against `decideFeedPrincipal` is a table test
 * rather than a browser observation.
 */
export function bootEligibleFromKeys(keys: readonly string[]): boolean {
  for (const key of keys) {
    if (BOOT_BLOCKING_KEYS.includes(key)) return false;
    if (key.startsWith(BOOT_AUTH_KEY_PREFIX)) return false;
  }
  return true;
}

/**
 * The inline `<script>` body rendered into the Discover document.
 *
 * Generated from the constants above so the script and the claim can never
 * describe different requests. Everything is wrapped in one try/catch: a
 * private-mode localStorage throw, a blocked fetch or a missing `performance`
 * must leave the page exactly as it is today.
 */
export function feedBootScript(apiBase: string): string {
  const url = JSON.stringify(bootFeedUrl(apiBase));
  const blocking = JSON.stringify(BOOT_BLOCKING_KEYS);
  const authPrefix = JSON.stringify(BOOT_AUTH_KEY_PREFIX);
  const slot = JSON.stringify(FEED_BOOT_GLOBAL);
  return (
    `(function(){try{` +
    `var w=window,s=w.localStorage;if(!s)return;` +
    `var b=${blocking};for(var i=0;i<b.length;i++){if(s.getItem(b[i])!==null)return;}` +
    `for(var j=0;j<s.length;j++){var k=s.key(j);if(k&&k.indexOf(${authPrefix})===0)return;}` +
    `var n=function(){return (w.performance&&w.performance.now)?w.performance.now():Date.now();};` +
    `var r={url:${url},startedAt:n(),readyAt:null,response:null};` +
    `var p=fetch(r.url).then(function(x){r.readyAt=n();return x;});` +
    // Mark the rejection handled here so a dead network cannot surface as an
    // unhandled rejection before the app has hydrated enough to claim it.
    `p.catch(function(){});` +
    `r.response=p;w[${slot}]=r;` +
    `}catch(e){}})();`
  );
}

/**
 * Claim the parked boot response for a request the caller is about to issue.
 *
 * Returns the record only when its URL matches `expectedUrl` exactly. The
 * record is CONSUMED either way: a boot fetch aimed at a different request is
 * dead weight, and leaving it parked would let a later, differently-principled
 * request pick it up.
 */
export function claimBootFeed(
  expectedUrl: string,
  scope?: Record<string, unknown>
): FeedBootRecord | null {
  const host =
    scope ??
    (typeof globalThis === "undefined"
      ? undefined
      : (globalThis as unknown as Record<string, unknown>));
  if (!host) return null;

  const parked = host[FEED_BOOT_GLOBAL];
  if (parked === undefined) return null;
  delete host[FEED_BOOT_GLOBAL];

  if (!parked || typeof parked !== "object") return null;
  const record = parked as FeedBootRecord;
  if (record.url !== expectedUrl) return null;
  const response = record.response as Promise<Response> | null;
  if (!response || typeof response.then !== "function") return null;
  return record;
}

/**
 * How long the consumer waits for a parked feed response before abandoning it (LAT-P218).
 *
 * A parked fetch has no timeout and no retries — it is a bare `fetch()` in a script tag. `apiFetch`
 * has both (20 s per attempt, two retries), so before this existed a claim was strictly WORSE than no
 * boot at all in one specific case: during a #2724 database spell the bare await stranded the reader
 * on a skeleton for as long as the server held the connection, where the normal path would have
 * given up and retried. `HUB_BOOT_CLAIM_TIMEOUT_MS` in `lib/tournament/hubBoot.ts` is the same
 * deadline for the same reason and the two are deliberately equal; they are separate constants only
 * because the two modules are separate, and a guard test asserts they agree.
 *
 * The value matches `apiFetch`'s own per-attempt timeout, so the worst case a claim can cost is one
 * extra attempt's wait rather than an unbounded one.
 */
export const FEED_BOOT_CLAIM_TIMEOUT_MS = 20000;

/**
 * The client duration to report for a claimed boot fetch: the wire time of the
 * boot request itself, NOT the time from parse to claim (which would fold the
 * whole JS download into a "feed latency" number and read as a regression).
 */
export function bootDurationMs(record: FeedBootRecord, fallbackNow: number): number {
  const readyAt = typeof record.readyAt === "number" ? record.readyAt : fallbackNow;
  const duration = readyAt - record.startedAt;
  return duration >= 0 ? duration : 0;
}
