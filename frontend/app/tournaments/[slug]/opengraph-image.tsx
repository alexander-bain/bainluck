import { ImageResponse } from "next/og";

import { UnfurlCard, accentFor } from "@/components/og/UnfurlCard";
import {
  tournamentShareFacts,
  type TournamentShareSource,
} from "@/lib/tournamentShareMeta";

export const runtime = "edge";
export const alt = "Bain Luck tournament probabilities";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const API_URL = (process.env.NEXT_PUBLIC_API_URL || "https://api.bainluck.com").replace(/\/$/, "");

/**
 * The same screen `layout.tsx` applies, for the same reason: this route runs on
 * every crawl of an attacker-supplied path, and a segment that could never name
 * a register is not worth an upstream round trip.
 */
const SLUG = /^[a-z0-9][a-z0-9-]{0,63}$/;

/**
 * ═══ WHY THIS FETCHES AGAIN INSTEAD OF TAKING THE LAYOUT'S PAYLOAD ═══
 *
 * It cannot. `opengraph-image.tsx` is its own route handler — a separate request
 * from a separate process, made by the unfurler after it has read the HTML — so
 * there is no layout render in scope to share state with. `/events/[id]` and
 * `/futures/[id]` fetch twice for the same reason.
 *
 * `revalidate: 300` matches the layout's, so the picture and the words come from
 * the same five-minute window of prices rather than drifting apart.
 */
async function fetchTournament(slug: string): Promise<TournamentShareSource | null> {
  if (!SLUG.test(slug)) return null;

  try {
    const response = await fetch(
      `${API_URL}/api/tournaments/${encodeURIComponent(slug)}?sections=first`,
      { next: { revalidate: 300 } },
    );
    if (!response.ok) return null;
    return await response.json();
  } catch {
    return null;
  }
}

/**
 * #5888 — a pasted `/tournaments/<slug>` link unfurled with the home page's
 * picture.
 *
 * #5813 gave this route its words. It did not give it a card, so the title read
 * "US Open 2026: Alexander Zverev 57%, Elena Rybakina 99%" beside the same house
 * image the front door uses — measured on production 2026-09-13 10:13:53Z, md5
 * `99618661539802337202ef69dc6595bc`, byte-identical to the one `/event/...`
 * and the home page served.
 *
 * ═══ THE LEADERS ARE NOT RE-DERIVED HERE ═══
 *
 * `tournamentShareFacts` is the same call the title makes. That matters more
 * than it looks: `boardLeader` picks by probability rather than by arrival
 * order, and drops a board whose leader prices null/NaN/0 rather than printing
 * "0%". A second implementation here would eventually pick a different leader
 * than the sentence directly beneath it — which is a worse failure than the one
 * this ship fixes, because the reader can see both at once.
 *
 * ═══ THE UNRESOLVED BRANCH DRAWS A QUIET CARD, NOT AN EMPTY CONFIDENT ONE ═══
 *
 * A dead slug must not render the live layout with the numbers missing. That is
 * the open defect on `/events/[id]`, whose dead card currently draws
 * "Prediction market", a `- -` glyph and "0 outcomes tracked" — a card that
 * looks authoritative and says nothing. Here an unresolved slug says what it is,
 * in the same words `unresolvedShareCopy` gives the title.
 */
export default async function Image({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const tournament = await fetchTournament(slug);

  if (!tournament) {
    return new ImageResponse(
      (
        <UnfurlCard
          eyebrow="Tournament"
          title="This tournament isn't on Bain Luck"
          subtitle="The link may be old, or the hub may not have opened yet."
          rows={[]}
          accent={accentFor(null)}
        />
      ),
      size,
    );
  }

  const { name, venue, leaders } = tournamentShareFacts(tournament);

  const rows = leaders.map((leader) => ({
    name: leader.name,
    probability: leader.probability,
    fraction: leader.fraction,
    sublabel: leader.draw,
  }));

  const note =
    rows.length > 0
      ? `${rows.length} draw${rows.length === 1 ? "" : "s"} tracked`
      : null;

  return new ImageResponse(
    (
      <UnfurlCard
        eyebrow="Tournament"
        title={name}
        subtitle={venue}
        rows={rows}
        note={note}
        accent={accentFor(null)}
      />
    ),
    size,
  );
}
