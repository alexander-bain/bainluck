import { API_URL } from "@/lib/api";
import { feedBootScript } from "@/lib/discover/feedBoot";

/**
 * LAT-P184 — the inline script that puts the first screen's request on the wire
 * while the browser is still parsing the document.
 *
 * IT LIVES ON THE DISCOVER ROUTE, NOT IN THE ROOT LAYOUT, ON PURPOSE. The root
 * layout renders for every surface, and `/politics`, `/event/<id>`, `/search`
 * and the rest never issue a Discover feed request — booting one there would be
 * 65 KB of download nobody claims, paid on every cold entry to the site. Only
 * `/` and `/discover` render this page, so only they boot.
 *
 * A CLIENT NAVIGATION INTO DISCOVER DOES NOT DOUBLE-FETCH. React inserts this
 * node via `innerHTML` on the client, and scripts inserted that way do not
 * execute — so on a soft navigation nothing is parked, `claimBootFeed` returns
 * null, and SWR's own fetch runs exactly as it does today. The boot path is
 * reachable only from the server-rendered HTML of a real cold load, which is the
 * only case it is for.
 */
export default function FeedBootScript() {
  return (
    <script
      data-testid="feed-boot"
      dangerouslySetInnerHTML={{ __html: feedBootScript(API_URL) }}
    />
  );
}
