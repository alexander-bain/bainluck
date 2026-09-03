/**
 * LAT-P218 — the Sports tab's request leaves at PARSE time, not after hydration.
 *
 * WHY THIS SURFACE, AND WHY NOW. On the corrected (hero-based) felt table, once the US Open hub's
 * parse-time fetch shipped (LAT-P217), **Sports is the worst row a reader on a phone meets**:
 * 3,427 ms and 3,461 ms to the first real card on Chrome's Slow-4G profile, measured from production
 * 75 minutes apart on 2026-09-02, against a 3 s target. Its shape is the hub's shape exactly:
 *
 *   `/sports` is a `"use client"` page whose first screen depends on ONE request,
 *   `GET /api/feed?limit=20&mode=sports`, issued by SWR from an effect — so it cannot start until
 *   every render-blocking chunk of the entry graph has downloaded, parsed, executed and hydrated.
 *
 * Chrome's Slow-4G profile has a 562 ms round trip. One sequential request costs more than 100 KB of
 * extra bytes, and the fix is the one this repo has now shipped twice: park the fetch in the document.
 *
 * ── WHAT THIS MODULE DOES *NOT* DUPLICATE ─────────────────────────────────────────────────────────
 * This is the third boot on the site and it is deliberately the smallest of the three:
 *
 *   the eligibility rule   IMPORTED from `lib/discover/feedBoot` — not re-stated. `/api/feed` is
 *                          personalised, so the reader set is Discover's exact set (the proven subset
 *                          of `decideFeedPrincipal` that routes to the shared warm `anon` cache key),
 *                          and a second copy of that rule is a second thing to keep true.
 *   the parking slot       `FEED_BOOT_GLOBAL` — the SAME slot Discover uses. Not a new one: the
 *                          consumer already validates by exact URL, and giving Sports its own slot
 *                          would need a second claim site inside `fetchFeed` to read it.
 *   the claim              NONE. `fetchFeed` already claims from that slot under
 *                          `suppressSessionId && !headers` and hands the record back only on a
 *                          byte-for-byte URL match, so a `/sports` document that parks the sports URL
 *                          is claimed by code that already shipped and is already guarded.
 *
 * What is genuinely new is therefore ONE THING: the URL. The hub needed its own module because its
 * eligibility rule differs from Discover's; Sports does not, so this file is a URL builder and a
 * script generator over borrowed rules.
 *
 * ── THE URL IS THE WHOLE RISK, SO IT IS PINNED TO THE WIRE ────────────────────────────────────────
 * If this URL and the URL `fetchFeed` actually issues ever differ by one character, the claim misses
 * silently and the page pays for TWO requests instead of one — LAT-P171/P172's duplicate-feed defect,
 * which passes every test that does not look at the wire. `bootFeedPath()` cannot be reused here: it
 * hard-codes Discover's `event_pct` and omits `mode`. So the guard suite does not compare this
 * builder against another builder; it drives the real `fetchFeed` against a stubbed `fetch` and
 * asserts the captured URL equals `bootSportsFeedUrl()`.
 */

import {
  BOOT_AUTH_KEY_PREFIX,
  BOOT_BLOCKING_KEYS,
  FEED_BOOT_GLOBAL,
  bootEligibleFromKeys,
} from "@/lib/discover/feedBoot";
import { initialFeedRequest } from "@/lib/discover/feedPaging";

/**
 * The `mode` the Sports tab asks for. A named constant because it is the ONE token that makes this
 * URL different from Discover's, and `app/sports/page.tsx` passes the same literal — a guard test
 * asserts the page's request carries it.
 */
export const SPORTS_FEED_MODE = "sports";

/**
 * The path the SWR-owned initial Sports request issues for a shared-anon reader.
 *
 * Built to mirror `fetchFeed`'s own parameter handling exactly, which is why the shape looks fussy:
 *   - `limit` is set from `initialFeedRequest()`, the same source the page reads;
 *   - a ZERO offset is omitted entirely, because `fetchFeed` writes it only `if (params?.offset)`;
 *   - there is NO `event_pct` — the Sports page does not pass one, and Discover's boot does. Copying
 *     `bootFeedPath()` here would have added it and missed on every single claim.
 */
export function bootSportsFeedPath(): string {
  const { limit, offset } = initialFeedRequest();
  const params = new URLSearchParams();
  if (limit) params.set("limit", limit.toString());
  if (offset) params.set("offset", offset.toString());
  params.set("mode", SPORTS_FEED_MODE);
  return `/api/feed?${params.toString()}`;
}

/** The absolute URL for `bootSportsFeedPath()` against an API origin. */
export function bootSportsFeedUrl(apiBase: string): string {
  return `${apiBase}${bootSportsFeedPath()}`;
}

/**
 * May the Sports document boot-fetch, given the full list of localStorage keys?
 *
 * A thin re-export rather than a new rule, kept as a named function so the call site reads as a
 * decision about this surface and so the guard suite can assert the two are the SAME function's
 * behaviour rather than two implementations that happen to agree today.
 */
export function sportsBootEligibleFromKeys(keys: readonly string[]): boolean {
  return bootEligibleFromKeys(keys);
}

/**
 * The inline `<script>` body rendered into the Sports document.
 *
 * Byte-for-byte the Discover script's structure with a different URL, and generated from the
 * constants above so the script and the claim can never describe different requests. Everything is
 * wrapped in one try/catch: a private-mode localStorage throw, a blocked fetch or a missing
 * `performance` must leave the page exactly as it is today.
 */
export function sportsFeedBootScript(apiBase: string): string {
  const url = JSON.stringify(bootSportsFeedUrl(apiBase));
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
    // Mark the rejection handled here so a dead network cannot surface as an unhandled rejection
    // before the app has hydrated enough to claim it.
    `p.catch(function(){});` +
    `r.response=p;w[${slot}]=r;` +
    `}catch(e){}})();`
  );
}
