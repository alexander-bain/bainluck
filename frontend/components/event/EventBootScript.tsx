import { API_URL } from "@/lib/api";
import { eventBootScript } from "@/lib/event/detailBoot";

/**
 * LAT-P219 (#2846) — the inline script that puts the Event page's four hero requests on the wire
 * while the browser is still parsing the document.
 *
 * IT LIVES ON THE EVENT ROUTE, NOT IN THE ROOT LAYOUT, ON PURPOSE — the same rule
 * `components/discover/FeedBootScript.tsx`, `components/tournament/HubBootScript.tsx` and
 * `components/sports/SportsFeedBootScript.tsx` all follow. The root layout renders for every
 * surface, and four boot fetches nobody claims would be four wasted requests charged to every cold
 * entry to the site. Only `/events/{id}` renders this, so only it boots, and it boots for the id it
 * is rendering.
 *
 * A CLIENT NAVIGATION INTO AN EVENT DOES NOT DOUBLE-FETCH. React inserts this node via `innerHTML`
 * on the client, and scripts inserted that way do not execute — so on a soft navigation nothing is
 * parked, every `claimEventBoot` returns null, and the page's own fetches run exactly as they do
 * today. The boot path is reachable only from the server-rendered HTML of a real cold load, which is
 * the only case it is for.
 */
export default function EventBootScript({ eventId }: { eventId: number }) {
  return (
    <script
      data-testid="event-boot"
      dangerouslySetInnerHTML={{ __html: eventBootScript(API_URL, eventId) }}
    />
  );
}
