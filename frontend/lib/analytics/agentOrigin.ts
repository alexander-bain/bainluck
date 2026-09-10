/**
 * Agent origin — the client half of #1916 / notice 39 (rung 3).
 *
 * THE SHIP. Our own tooling stops counting itself as an audience. Every shot
 * `tools/look.sh` takes is a real page load of production, and nine lanes plus
 * the bus's probes shoot all day. Rung 1 stopped those loads voting in the
 * search head (`x-bainluck-origin`, read by `routes/events.py`
 * `_request_is_automation`) and set the `bl_agent` cookie for this half to key
 * on. Until now that cookie had no reader, so the fleet still showed up in the
 * numbers we tune the site on.
 *
 * 🔴 WHICH RAIL ACTUALLY NEEDED THIS, WHICH DID NOT, AND WHY THAT IS BACKWARDS
 * FROM THE OBVIOUS READING. Notice 39 words rung 3 as "Vercel `beforeSend` +
 * GA4 drop". Measured against the consent authority, the GA4 and Vercel
 * Analytics rails were ALREADY silent for a shot: `look.sh` drives a fresh
 * Playwright context, a fresh context has no `localStorage`, so the stored
 * consent level is `null` — and `decideTelemetry(null)` returns `NOTHING`
 * (`telemetryConsent.ts`: "`null` (no choice yet) and `'none'` are BOTH
 * denials"). A drop keyed on the cookie for those two rails is inert code.
 *
 * The rail that fires on every single shot is the one nobody would name first:
 * **Speed Insights**, precisely because Alex ruling D30 mounts it OUTSIDE the
 * consent gate. So the pollution lands squarely on the page-speed number the
 * latency lane exists to tune — our screenshot tool was dragging the p75 it
 * photographs. That is what `speedInsightsAgentDropSnippet()` fixes, and it is
 * the load-bearing half of this module.
 *
 * The gated rails are still closed here (via `TelemetryGate`), and that is not
 * ceremony: it is only the fresh-context assumption that makes them safe today.
 * A shot rig with a persistent profile, or one that accepts the banner in order
 * to photograph the post-consent state, re-opens all three at once. An agent is
 * not a person whatever it has stored, so the gate says so directly rather than
 * resting on a property of the current harness.
 *
 * 🔴 THE PREDICATE IS THE BACKEND'S, DELIBERATELY. `_request_is_automation`
 * reads: absent or empty ⇒ a PERSON; otherwise trimmed-and-lowercased and
 * compared to the literal `user`. This file reproduces that exactly, including
 * the empty case. One load must not be a machine to the search log and a person
 * to Speed Insights — a split definition would put the two halves of the same
 * visit in different populations, which is worse than not filtering at all.
 *
 * That empty case is not hypothetical: rung 1 shipped with a live bug where the
 * wire carried `x-bainluck-origin:` with NO value (an assignment prefixed to
 * `.` does not persist outside POSIX mode), the backend's `if not raw` read it
 * as a person, and nothing errored. Hence `isAgentOriginValue('')` is `false`
 * here too, and is asserted in the guard rather than left to be re-derived.
 */

/** The cookie `tools/shop-shot.mjs` sets on the target origin for every shot. */
export const AGENT_COOKIE = 'bl_agent';

/**
 * The one value that means "measure me as a person". `BL_AGENT=user` is a
 * deliberate escape hatch so a lane can shoot as a visitor when that is the
 * thing being tested; the backend honours the same spelling positively.
 */
export const AGENT_ORIGIN_USER = 'user';

/**
 * The pure predicate, split out from any DOM read so it is testable without a
 * document and so the guard can assert it against the inline snippet below.
 *
 * FAILS TOWARD MEASURING, matching the backend's stated direction: anything we
 * cannot read confidently is a person. Over-suppression silently deletes real
 * visitors from the numbers and leaves nothing to notice; under-suppression
 * leaves an agent row that is visible and countable.
 */
export function isAgentOriginValue(raw: string | null | undefined): boolean {
  if (!raw) return false;
  return raw.trim().toLowerCase() !== AGENT_ORIGIN_USER;
}

/**
 * Pull the agent cookie out of a `document.cookie` string. Pure, so the parse
 * is tested directly instead of through a DOM.
 *
 * Matches on a cookie BOUNDARY (`^` or `; `) rather than a bare substring: a
 * cookie named `not_bl_agent` must not answer for `bl_agent`.
 */
export function readAgentCookie(cookieString: string | null | undefined): string | null {
  if (!cookieString) return null;
  for (const part of cookieString.split(';')) {
    const eq = part.indexOf('=');
    if (eq === -1) continue;
    if (part.slice(0, eq).trim() !== AGENT_COOKIE) continue;
    const value = part.slice(eq + 1).trim();
    try {
      return decodeURIComponent(value);
    } catch {
      // A malformed percent-escape is not a reason to throw inside a telemetry
      // path; take the raw value and let the predicate judge it.
      return value;
    }
  }
  return null;
}

/**
 * Is THIS client one of our agents? Browser-only; `false` during server render
 * so the SSR snapshot is always "a person" and hydration cannot disagree with
 * itself. Never throws — a telemetry decision must not be able to break a page.
 */
export function isAgentClient(): boolean {
  if (typeof document === 'undefined') return false;
  try {
    return isAgentOriginValue(readAgentCookie(document.cookie));
  } catch {
    return false;
  }
}

/**
 * `useSyncExternalStore` subscribe for {@link isAgentClient}.
 *
 * Intentionally inert: the cookie is fixed for the life of the document, so
 * there is no change to publish. It exists because the hook requires a
 * subscribe, and because reusing the consent store's subscribe here — the
 * obvious shortcut — would claim a dependency that does not exist and would
 * re-read this value on every unrelated consent change.
 *
 * A never-firing subscribe is still correct across hydration: React compares
 * the client snapshot against the server snapshot after hydrating and schedules
 * the re-render itself, which is exactly the transition from "assume a person"
 * to the cookie's answer.
 */
export function subscribeAgentOrigin(): () => void {
  return () => {};
}

/**
 * The pre-hydration inline script that drops Speed Insights beacons for agents.
 *
 * 🔴 WHY A STRING IN THE HEAD AND NOT THE `beforeSend` PROP. The prop is the
 * documented seam, and it is unreachable from where the mount lives:
 * `app/layout.tsx` is a SERVER component (it exports `metadata`), and a
 * function cannot cross the RSC boundary into a client component. Moving the
 * mount to a client wrapper would work and is the wrong trade — the mount site
 * is pinned to that file by `__tests__/lib/speedInsightsPreConsent.test.ts`,
 * which encodes Alex ruling D30, and whose own docstring says a move "renames
 * the claim and must be made deliberately". Conditionally rendering it instead
 * would be worse still: reading a cookie in the root layout opts the whole tree
 * into dynamic rendering, so the latency lane would have paid for this filter
 * with a slower first byte for every real visitor.
 *
 * The package makes a third way legitimate rather than clever. It registers
 * `beforeSend` by calling `window.si('beforeSend', fn)` against a queue stub
 * (`initQueue`), draining `window.siq` once the real script loads — so any code
 * that runs first can register the callback with no prop and no moved mount.
 * This snippet defines the identical stub, and `initQueue`'s own `if (window.si)
 * return` then leaves it in place.
 *
 * Running inline in the document beats the race outright: the script parses
 * during initial HTML, while `<SpeedInsights />` injects its tag from a
 * `useEffect` after hydration. A `useEffect` of our own could lose an early
 * LCP/FCP beacon; this cannot.
 *
 * Generated from the constants above so there is exactly ONE definition of
 * "agent" on the client. `agentOrigin.contract.test.ts` evaluates this string
 * and asserts it agrees with `isAgentOriginValue` value-for-value — a second
 * hand-written copy of the predicate is precisely the drift this avoids.
 */
export function speedInsightsAgentDropSnippet(): string {
  return [
    '(function(){try{',
    'var c=document.cookie||"";var raw=null;var parts=c.split(";");',
    'for(var i=0;i<parts.length;i++){var p=parts[i];var eq=p.indexOf("=");',
    `if(eq===-1)continue;if(p.slice(0,eq).trim()!==${JSON.stringify(AGENT_COOKIE)})continue;`,
    'var v=p.slice(eq+1).trim();try{raw=decodeURIComponent(v);}catch(e){raw=v;}break;}',
    `if(!raw)return;if(raw.trim().toLowerCase()===${JSON.stringify(AGENT_ORIGIN_USER)})return;`,
    'window.si=window.si||function(){(window.siq=window.siq||[]).push([].slice.call(arguments));};',
    'window.si("beforeSend",function(){return null;});',
    '}catch(e){}})();',
  ].join('');
}
