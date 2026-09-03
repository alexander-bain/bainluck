import { API_URL } from "@/lib/api";
import { hubBootScript } from "@/lib/tournament/hubBoot";

/**
 * LAT-P217 — the inline script that puts the tournament hub's request on the wire while the browser
 * is still parsing the document.
 *
 * IT LIVES ON THE HUB ROUTE, NOT IN THE ROOT LAYOUT, ON PURPOSE — the same rule
 * `components/discover/FeedBootScript.tsx` follows. The root layout renders for every surface, and a
 * boot fetch nobody claims is a 79 KB download charged to every cold entry to the site. Only
 * `/tournaments/{slug}` renders this, so only it boots, and it boots for the slug it is rendering.
 *
 * A CLIENT NAVIGATION INTO THE HUB DOES NOT DOUBLE-FETCH. React inserts this node via `innerHTML` on
 * the client, and scripts inserted that way do not execute — so on a soft navigation nothing is
 * parked, `claimHubBoot` returns null, and the page's own fetch runs exactly as it does today. The
 * boot path is reachable only from the server-rendered HTML of a real cold load, which is the only
 * case it is for.
 */
export default function HubBootScript({ slug }: { slug: string }) {
  return (
    <script
      data-testid="hub-boot"
      dangerouslySetInnerHTML={{ __html: hubBootScript(API_URL, slug) }}
    />
  );
}
