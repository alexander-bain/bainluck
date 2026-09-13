import { ImageResponse } from "next/og";

import { UnfurlCard, accentFor } from "@/components/og/UnfurlCard";
import {
  eventConceptShareFacts,
  type EventConceptShareSource,
} from "@/lib/eventConceptShareMeta";

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
 * The pill, from the route's own segment.
 *
 * The domain is the one signal available BEFORE the payload — and, unlike
 * anything in the envelope, it is still available when the fetch fails, so the
 * unresolved card is still coloured and labelled like the family it belongs to.
 * Spellings the segment uses that a reader would not: everything else is
 * capitalised as-is.
 */
const DOMAIN_LABEL: Record<string, string> = {
  ufc: "UFC",
  mma: "MMA",
  f1: "Formula 1",
  election: "Election",
  awards: "Awards",
};

function domainLabel(domain: string): string {
  const known = DOMAIN_LABEL[domain.toLowerCase()];
  if (known) return known;
  return domain.charAt(0).toUpperCase() + domain.slice(1);
}

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
  const eyebrow = domainLabel(domain);
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
      size,
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
      size,
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
    size,
  );
}
