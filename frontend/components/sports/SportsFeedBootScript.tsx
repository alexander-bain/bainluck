import { API_URL } from "@/lib/api";
import { sportsFeedBootScript } from "@/lib/sports/feedBoot";

/**
 * LAT-P218 — the inline script that puts the Sports tab's request on the wire while the browser is
 * still parsing the document.
 *
 * IT LIVES ON THE /sports ROUTE, NOT IN THE ROOT LAYOUT, ON PURPOSE — the rule
 * `components/discover/FeedBootScript.tsx` and `components/tournament/HubBootScript.tsx` both follow.
 * The root layout renders for every surface, and a boot fetch nobody claims is a feed-sized download
 * charged to every cold entry to the site. Only `/sports` renders this, so only `/sports` boots.
 *
 * IT IS THE FIRST NODE OF THE PAGE'S TREE, not inside a loading branch. The hub puts its script in
 * the `loading` branch because that is what the hub's server render emits; `/sports` server-renders
 * its whole tree including the skeleton grid, so the parser reaches the script earliest here — and
 * "earliest" is the entire value of the change.
 *
 * A CLIENT NAVIGATION INTO SPORTS DOES NOT DOUBLE-FETCH. React inserts this node via `innerHTML` on
 * the client, and scripts inserted that way do not execute — so on a soft navigation nothing is
 * parked, the claim inside `fetchFeed` returns null, and the page's own fetch runs exactly as it does
 * today. The boot path is reachable only from the server-rendered HTML of a real cold load, which is
 * the only case it is for.
 */
export default function SportsFeedBootScript() {
  return (
    <script
      data-testid="sports-feed-boot"
      dangerouslySetInnerHTML={{ __html: sportsFeedBootScript(API_URL) }}
    />
  );
}
