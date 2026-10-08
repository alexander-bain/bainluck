import { API_URL } from "@/lib/api";
import { feedBootScriptSrc } from "@/lib/discover/feedBoot";

/**
 * LAT-P184 — the script that puts the first screen's request on the wire
 * while the browser is still parsing the document.
 *
 * IT LIVES ON THE DISCOVER ROUTE, NOT IN THE ROOT LAYOUT, ON PURPOSE. The root
 * layout renders for every surface, and `/politics`, `/event/<id>`, `/search`
 * and the rest never issue a Discover feed request — booting one there would be
 * 65 KB of download nobody claims, paid on every cold entry to the site. Only
 * `/` and `/discover` render this page, so only they boot.
 *
 * #1469: IT IS AN `async` SCRIPT, NOT AN INLINE ONE. An inline script waits for
 * every stylesheet above it; an async one does not, and React hoists it into the
 * head. See `feedBootScriptSrc`.
 *
 * A CLIENT NAVIGATION INTO DISCOVER DOES NOT DOUBLE-FETCH. React does insert an
 * async script on a soft navigation, and inserted scripts do execute — so the
 * script itself returns when `document.readyState` is "complete", which on a
 * cold load it can never be (the load event waits for async scripts). Nothing is
 * parked, `claimBootFeed` returns null, and SWR's own fetch runs exactly as
 * before.
 */
export default function FeedBootScript() {
  return <script data-testid="feed-boot" async src={feedBootScriptSrc(API_URL)} />;
}
