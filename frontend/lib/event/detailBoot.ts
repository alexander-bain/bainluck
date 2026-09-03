/**
 * LAT-P219 (#2846) — the Event page's FOUR hero calls leave at PARSE time, not after hydration.
 *
 * WHY THIS SURFACE, AND WHY FOUR. Measured on production 2026-09-03, Slow-4G + 4x CPU
 * (`tools/felt-waterfall.mjs https://www.bainluck.com/events/15293206 slow4g`):
 *
 *      0 -  650 ms   the HTML (6,565 B)        TTFB 52 ms — the rest is one 562 ms round trip
 *    633 - 2488 ms   26 render-blocking chunks, ~250 KB, all parallel, bandwidth-bound
 *         2163 ms    DCL
 *         2172 ms    first paint
 *   2618 - 3404 ms   FOUR /api/events/{id}* calls   <- start 1,968 ms after the HTML landed
 *         3401 ms    the hero prints its answer
 *
 * The document is in the browser's hands at 650 ms and the page asks for NOTHING until 2,618 ms.
 * That gap is the entry graph downloading, parsing, executing and hydrating, and it is dead network
 * time: all four requests are GETs keyed on nothing but the route's own id.
 *
 * ── WHY PARKING, NOT COLLAPSING ───────────────────────────────────────────────────────────────────
 * The obvious read of "seven API calls before the first screen" is that the page makes too many
 * requests and should make fewer. The waterfall says otherwise, and the distinction decides the fix:
 *
 *   - The four calls below ALREADY ISSUE CONCURRENTLY, in one 786 ms window (731/748/742/785 ms).
 *     Collapsing them into a single endpoint would save the spread between the fastest and the
 *     slowest — about 50 ms — at the cost of a new backend surface.
 *   - The other three (`/api/feed?tags=[...]`, `/api/events/search/trending`, `related-futures`)
 *     start at 3,394 / 4,245 / 6,341 ms — AFTER the hero has already painted. They cost the reader
 *     nothing on the first screen.
 *   - Moving this 786 ms window from after hydration to before first paint overlaps it entirely with
 *     the entry-graph download, which is bandwidth-bound and already in flight. That is worth
 *     ~1,000-1,200 ms, i.e. the whole distance between a 3,401 ms hero and the 3 s bar.
 *
 * So the count is not the defect; the START TIME is. A fifth boot is cheap, and cutting the count
 * would have bought fifty milliseconds while leaving the two-second hole exactly where it was.
 *
 * ── WHY A MAP-SHAPED SLOT, WHERE THE OTHER THREE BOOTS PARK ONE RECORD ────────────────────────────
 * `lib/discover/feedBoot`, `lib/tournament/hubBoot` and `lib/sports/feedBoot` each park a single
 * record in a dedicated global, because each of those surfaces has exactly one first-screen request.
 * This one has four, and they are claimed by four different functions in `lib/api.ts` at four
 * different moments. Four more globals would mean four more claim helpers that differ only in a
 * string; one global holding a `url -> record` map means one claim helper, and the URL check that
 * makes the whole pattern safe is unchanged — a claim still returns a record only for its own exact
 * URL, and still consumes it.
 *
 * The slot is deleted once its last entry is claimed, so a soft navigation cannot find a stale map.
 *
 * ── THE URLS ARE THE WHOLE RISK ───────────────────────────────────────────────────────────────────
 * If a parked URL and the URL `lib/api.ts` actually issues differ by one character, the claim misses
 * silently and the page pays for EIGHT requests instead of seven — LAT-P171/P172's duplicate-fetch
 * defect, which passes every test that does not look at the wire. Two mitigations, both load-bearing:
 *
 *   1. `EVENT_BOOT_HISTORY_HOURS` is exported and CONSUMED by the page's own `fetchEventHistory`
 *      call, so the `?hours=48` in the parked URL and the one on the wire are one expression. It was
 *      a bare literal at the call site before this shipped, which is exactly the two-builders shape
 *      that failed twice.
 *   2. The guard suite does not compare this builder against another builder. It drives the real
 *      `fetchEvent` / `fetchGameMarkets` / `fetchTeamProgression` / `fetchEventHistory` against a
 *      stubbed `fetch` and asserts each captured URL equals its `eventBootUrls()` entry.
 *
 * ── WHO IT FIRES FOR ──────────────────────────────────────────────────────────────────────────────
 * Signed-out readers only — the same rule, and the same imported constant, as `hubBoot`. Not because
 * these endpoints are personalised (they take an id and no principal) but because that keeps the
 * correctness argument LOCAL to this file: for a signed-out reader the client's own request is
 * byte-identical to the boot request, so claiming the parked response cannot hand anyone a body their
 * own request would not have produced. A signed-in reader gets exactly today's behaviour.
 */

import { BOOT_AUTH_KEY_PREFIX, type FeedBootRecord } from "@/lib/discover/feedBoot";

/** Where the event document parks its boot map. Distinct from the other three surfaces' slots so a
 *  claim can never cross surfaces even before the URL check runs. */
export const EVENT_BOOT_GLOBAL = "__blEventBoot";

/**
 * The `hours` window the event page's history call asks for.
 *
 * Exported so the page and the boot script cannot drift: `app/events/[id]/page.tsx` passes this
 * constant to `fetchEventHistory` rather than repeating `48`. See the URL note in the header — this
 * is the one parameter in the four that is not derivable from the id alone, and therefore the only
 * one that could silently disagree.
 */
export const EVENT_BOOT_HISTORY_HOURS = 48;

/**
 * The four paths the Event page puts on the wire before its hero can print an answer.
 *
 * Order is the waterfall's order and carries no meaning — all four are issued together. Kept as one
 * function rather than four so that "what does this page boot" has a single answer, and so the guard
 * suite can assert the set as a set.
 */
export function eventBootPaths(eventId: number): string[] {
  return [
    `/api/events/${eventId}`,
    `/api/events/${eventId}/game-markets`,
    `/api/events/${eventId}/team-progression`,
    `/api/events/${eventId}/history?hours=${EVENT_BOOT_HISTORY_HOURS}`,
  ];
}

/** The absolute URLs for `eventBootPaths()` against an API origin. */
export function eventBootUrls(apiBase: string, eventId: number): string[] {
  return eventBootPaths(eventId).map((path) => `${apiBase}${path}`);
}

/**
 * May the event document boot-fetch, given the full list of localStorage keys?
 *
 * Pure, so the rule is a table test rather than a browser observation. The only disqualifier is a
 * persisted Firebase user: `lib/firebase.ts` sets `browserLocalPersistence` FIRST, ahead of
 * IndexedDB, precisely so this is synchronously readable at parse time.
 */
export function eventBootEligibleFromKeys(keys: readonly string[]): boolean {
  for (const key of keys) {
    if (key.startsWith(BOOT_AUTH_KEY_PREFIX)) return false;
  }
  return true;
}

/**
 * The inline `<script>` body rendered into the Event document.
 *
 * Generated from the helpers above so the script and the claims can never describe different
 * requests. Everything is wrapped in one try/catch: a private-mode localStorage throw, a blocked
 * fetch or a missing `performance` must leave the page exactly as it is today.
 */
export function eventBootScript(apiBase: string, eventId: number): string {
  const urls = JSON.stringify(eventBootUrls(apiBase, eventId));
  const authPrefix = JSON.stringify(BOOT_AUTH_KEY_PREFIX);
  const slot = JSON.stringify(EVENT_BOOT_GLOBAL);
  return (
    `(function(){try{` +
    `var w=window,s=w.localStorage;if(!s)return;` +
    `for(var j=0;j<s.length;j++){var k=s.key(j);if(k&&k.indexOf(${authPrefix})===0)return;}` +
    `var n=function(){return (w.performance&&w.performance.now)?w.performance.now():Date.now();};` +
    `var u=${urls},m={};` +
    `for(var i=0;i<u.length;i++){(function(url){` +
    `var r={url:url,startedAt:n(),readyAt:null,response:null};` +
    `var p=fetch(url).then(function(x){r.readyAt=n();return x;});` +
    // Mark the rejection handled here so a dead network cannot surface as an unhandled rejection
    // before the app has hydrated enough to claim it.
    `p.catch(function(){});` +
    `r.response=p;m[url]=r;` +
    `})(u[i]);}` +
    `w[${slot}]=m;` +
    `}catch(e){}})();`
  );
}

/**
 * Claim the parked response for a request the caller is about to issue.
 *
 * Returns the record only when the map holds `expectedUrl` exactly — an event document that parked
 * `/api/events/17/game-markets` can never satisfy a request for `/api/events/18/game-markets`, and
 * `fetchEvent` called in a loop by `fetchEventsByIds` can match at most the one booted id.
 *
 * The matched entry is CONSUMED, and the slot itself is removed once empty, so a later soft
 * navigation cannot pick up a stale body. Unlike the single-record boots this does NOT discard the
 * whole slot on a miss: the other three entries belong to sibling requests that have not run yet.
 */
export function claimEventBoot(
  expectedUrl: string,
  scope?: Record<string, unknown>
): FeedBootRecord | null {
  const host =
    scope ??
    (typeof globalThis === "undefined"
      ? undefined
      : (globalThis as unknown as Record<string, unknown>));
  if (!host) return null;

  const parked = host[EVENT_BOOT_GLOBAL];
  if (!parked || typeof parked !== "object") return null;
  const map = parked as Record<string, unknown>;

  const entry = map[expectedUrl];
  if (entry !== undefined) delete map[expectedUrl];
  // Drop the slot once it is exhausted rather than leaving an empty object behind for the next
  // navigation to find.
  if (Object.keys(map).length === 0) delete host[EVENT_BOOT_GLOBAL];

  if (!entry || typeof entry !== "object") return null;
  const record = entry as FeedBootRecord;
  if (record.url !== expectedUrl) return null;
  const response = record.response as Promise<Response> | null;
  if (!response || typeof response.then !== "function") return null;
  return record;
}

/**
 * How long a consumer waits for a parked response before abandoning it.
 *
 * A parked fetch has no timeout and no retries — it is a bare `fetch()` in a script tag. `apiFetch`
 * has both (20 s per attempt, two retries), and during the multi-minute database spells of #2724 a
 * bare await on the parked promise would strand the reader on a skeleton for as long as the server
 * held the connection. So every claim is RACED against this deadline and falls through to the normal
 * retrying path when it expires. Equal to `HUB_BOOT_CLAIM_TIMEOUT_MS` and `FEED_BOOT_CLAIM_TIMEOUT_MS`
 * for the same reason they are equal to each other; a guard test asserts all three agree.
 */
export const EVENT_BOOT_CLAIM_TIMEOUT_MS = 20000;
