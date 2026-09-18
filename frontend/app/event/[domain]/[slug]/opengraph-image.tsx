import { ImageResponse } from "next/og";

import { conceptDomainLabel } from "@/components/discover/utils";
import { UnfurlCard, accentFor } from "@/components/og/UnfurlCard";
import {
  eventConceptShareFacts,
  type EventConceptShareSource,
} from "@/lib/eventConceptShareMeta";
import { unfurlImageOptions } from "@/lib/unfurlImageCache";

export const runtime = "edge";
export const alt = "Bain Luck event probabilities";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const API_URL = (process.env.NEXT_PUBLIC_API_URL || "https://api.bainluck.com").replace(/\/$/, "");

/** The same screens `layout.tsx` applies, and for the same reason. */
const DOMAIN = /^[a-z0-9][a-z0-9-]{0,31}$/;
const SLUG = /^[a-z0-9][a-z0-9-]{0,95}$/;

/**
 * A separate request from the layout's, so it fetches again — see the note on
 * `/tournaments/[slug]/opengraph-image.tsx`. `revalidate: 300` matches the
 * layout's so the picture and the words price the same five minutes.
 */
async function fetchConcept(
  domain: string,
  slug: string,
): Promise<EventConceptShareSource | null> {
  if (!DOMAIN.test(domain) || !SLUG.test(slug)) return null;

  try {
    const response = await fetch(
      `${API_URL}/api/event/${encodeURIComponent(`event:${domain}:${slug}`)}`,
      { next: { revalidate: 300 } },
    );
    if (!response.ok) return null;
    return await response.json();
  } catch {
    return null;
  }
}

/**
 * THE PILL (#6849). One helper, whether or not the payload arrived.
 *
 * ═══ WHAT IT USED TO SAY ═══
 *
 * A local `DOMAIN_LABEL` map keyed on the URL SEGMENT, whose `ufc: "UFC"` entry
 * put a **UFC** pill on Power Slap 23. Read from production 2026-09-18 03:00Z,
 * `/event/ufc/power-slap-23-26sep18powerslap23/opengraph-image`: a slap-fighting
 * card, in the one picture that reaches iMessage, Slack and X, naming a
 * promotion the event has nothing to do with. `domain` is the event-key
 * namespace this codebase ROUTES on — `UFC_CONFIG` declares it to cover all of
 * MMA plus every `KXUFC*` Kalshi ticker — so it was never a sport (#5603).
 *
 * ═══ WHY THE OLD COMMENT WAS RIGHT AND STILL LOST ═══
 *
 * It defended the segment as "the one signal available BEFORE the payload, and
 * still available when the fetch fails". Both halves are true, and neither is a
 * reason to ignore the payload when it DOES resolve — which it does on line 97,
 * three lines above the pill. `conceptDomainLabel` is the same function
 * `ConceptCard`, `FeedCard` and (since #6842) the event page's own header call,
 * so the picture and the page it depicts cannot drift: one card family, one
 * label (notice 35). Measured 04:40Z, `/api/event` serves
 * `event.sport_label: "Combat"` for this card and `"UFC"` for `event:ufc:26sep20`
 * — the evidence to tell them apart is on the wire today.
 *
 * ═══ THE UNRESOLVED CARD KEEPS THE FALLBACK, BUT NOT THE UFC ENTRY ═══
 *
 * Passing `null` as the label is the honest input for a card that has no
 * payload, and the helper's own unevidenced arm answers it: a combat-namespace
 * link with nothing behind it falls to `COMBAT`, which is strictly less than the
 * envelope knows rather than more. That is #5603's fallback doing the work it
 * was written for, not a second rule.
 *
 * 🪤 THIS RETIRES THE MAP, SO TWO LIVE PILLS CHANGE BEYOND THE FILED DEFECT:
 * `/event/election/2026-midterms` (linked from `BottomNav` on every page of the
 * site) goes `Election` → `ELECTION`, and `/event/f1/2026-azerbaijan-grand-prix`
 * goes `Formula 1` → `F1`; both carry `sport_label: null` today, measured 04:41Z.
 * Deliberate, and the reason not to keep a prettifier beside the helper: those
 * two PAGES already print `ELECTION` and `F1` in their own chips, so the card
 * disagreed with its subject before this and agrees with it after.
 *
 * There is no wrapper and no branch: `concept?.event?.sport_label` is `undefined`
 * on exactly the failed fetch, which is the input the unevidenced arm answers.
 */

/**
 * #5888 — a pasted `/event/<domain>/<slug>` link unfurled with the home page's
 * picture.
 *
 * #5833 gave this route its words, including for the `/event/election/2026-midterms`
 * link that sits in `BottomNav` and `DesktopNav` on every page of the site. It
 * did not give it a card: measured with a crawler UA on 2026-09-13 10:13:53Z,
 * this route, `/tournaments/us-open` and the home page all named one image, md5
 * `99618661539802337202ef69dc6595bc`.
 *
 * ═══ THE BRANCHES ARE THE TITLE'S BRANCHES ═══
 *
 * `eventConceptShareFacts` is the same call `buildEventConceptShareCopy` makes,
 * so the card cannot claim a winner the sentence does not. That is load-bearing
 * here rather than merely tidy, because the interesting branch is a REFUSAL:
 * `winner` is read only from the authoritative `won` flag and is never inferred
 * from a price, and `event:ufc:26sep12` was `live` with its favourite at 0.99
 * while `lib/eventConceptShareMeta.ts` was written. A card that re-derived the
 * winner from the price would have drawn "Hunt won" over a fight in progress.
 *
 * A settled event therefore prints a verdict and NO probabilities — a forecast
 * on a closed question is not a smaller lie in a picture than in a sentence
 * (#1495).
 */
export default async function Image({
  params,
}: {
  params: Promise<{ domain: string; slug: string }>;
}) {
  const { domain, slug } = await params;
  const concept = await fetchConcept(domain, slug);
  const eyebrow = conceptDomainLabel(concept?.event?.sport_label, domain);
  // Still the routing segment, deliberately: the accent is the family's COLOUR
  // and every `event:ufc:*` card belongs to the same one whatever it is called.
  const accent = accentFor(domain);

  if (!concept) {
    return new ImageResponse(
      (
        <UnfurlCard
          eyebrow={eyebrow}
          title="This event isn't on Bain Luck"
          subtitle="The link may be old, or the card may not have been announced yet."
          rows={[]}
          accent={accent}
        />
      ),
      // #6166 — MOVING, because this is the retractable card. A dead slug and a
      // restarting API are the same 5xx here, so the picture that says "isn't on
      // Bain Luck" may be wrong about a live event; `unfurlImageCache`'s header
      // makes exactly this case moving.
      unfurlImageOptions(size, "moving"),
    );
  }

  const { name, label, where, priced, settled, winner } = eventConceptShareFacts(concept);

  // ── SETTLED ────────────────────────────────────────────────────────────────
  // A result, or an honest admission that we do not have one. No numbers either
  // way: the prices left on a closed question are a forecast, not an outcome.
  if (settled) {
    return new ImageResponse(
      (
        <UnfurlCard
          eyebrow={eyebrow}
          title={name}
          subtitle={label ?? where}
          rows={[]}
          verdict={winner ? `${winner} won` : "Final"}
          note={winner ? null : "Result not yet confirmed"}
          accent={accent}
        />
      ),
      // #6166 — `settled` alone is NOT enough to cache this as settled. The
      // no-winner arm draws "Result not yet confirmed", which is a statement
      // that our RECORD is incomplete and is expected to change the moment
      // resolution writes the `won` flag. Freezing that for a day would leave a
      // graded event captioned "Final / Result not yet confirmed" long after the
      // winner was known — `/events/[id]` declined the same trade for
      // `suspended`. Only the authoritative winner is terminal.
      unfurlImageOptions(size, winner ? "settled" : "moving"),
    );
  }

  // A duel names both sides; a field names only the leader. Exactly the split
  // the title makes, for the reason it makes it — the runner-up of a 25-way
  // race at 4% is not what the reader stopped for.
  const rows = (priced.length === 2 ? priced : priced.slice(0, 1)).map((competitor) => ({
    name: competitor.name,
    probability: competitor.probability,
    fraction: competitor.fraction,
    sublabel: null,
  }));

  const note =
    priced.length > 2 ? `${priced.length} priced contenders` : null;

  return new ImageResponse(
    (
      <UnfurlCard
        eyebrow={eyebrow}
        title={name}
        subtitle={[where, label].filter(Boolean).join(" · ") || null}
        rows={rows}
        note={note}
        accent={accent}
      />
    ),
    // #6166 — live prices under a URL that cannot change. This is the defect.
    unfurlImageOptions(size, "moving"),
  );
}
