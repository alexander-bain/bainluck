import { ImageResponse } from "next/og";

import { UnfurlCard, accentFor } from "@/components/og/UnfurlCard";
import {
  tournamentShareFacts,
  TOURNAMENT_SHARE_REVALIDATE_SECONDS,
  type TournamentShareSource,
} from "@/lib/tournamentShareMeta";
import { unfurlImageOptions } from "@/lib/unfurlImageCache";

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
 * `TOURNAMENT_SHARE_REVALIDATE_SECONDS` is the layout's own window — one shared
 * constant since #6161, rather than two `300`s tied together by this sentence —
 * so the picture and the words come from the same five minutes of prices.
 *
 * That alignment was verified and is NOT the reason a stale card shipped on
 * 2026-09-14 (#6161): both halves fetch an identical url with an identical
 * window, and the render still drew a body generated the previous day. The
 * refusal for that lives in `tournamentShareMeta`'s `payloadIsStale`, on the
 * facts both halves read, not in these options.
 */
async function fetchTournament(slug: string): Promise<TournamentShareSource | null> {
  if (!SLUG.test(slug)) return null;

  try {
    const response = await fetch(
      `${API_URL}/api/tournaments/${encodeURIComponent(slug)}?sections=first`,
      { next: { revalidate: TOURNAMENT_SHARE_REVALIDATE_SECONDS } },
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
 * order, drops a board whose leader prices null/NaN/0 rather than printing
 * "0%", since #6149 drops one whose leader prices at or above 0.995 rather than
 * captioning a live final "100%", and since #6161 drops every board on a body
 * older than an hour rather than publishing yesterday's forecast. A second
 * implementation here would eventually pick a different leader
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
      // #6166 — moving, for the reason below: an unresolved slug is retractable.
      unfurlImageOptions(size, "moving"),
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
    // #6166 — THIS ROUTE HAS NO "settled" ARM, AND THAT IS A FINDING RATHER THAN
    // AN OMISSION.
    //
    // `TournamentShareFacts` exposes `name`, `venue` and `leaders` — no terminal
    // signal, and there is nowhere honest to read one from. A hub is a
    // COLLECTION of boards: the US Open's men's draw can be decided while the
    // women's is still being played, so "the tournament is settled" is not a
    // property any single board carries.
    //
    // The tempting proxy — empty `leaders` — is the trap, because THREE
    // different causes land on it and only one is terminal: every board decided
    // (#6161 measured that `_settle_row` nulls `probability` before
    // `apply_final_result` writes `decided`, so a decided board is an unpriced
    // one), no board priced yet, and #6161's own staleness refusal. Caching the
    // last two as settled would freeze a card we are deliberately withholding
    // until it can be trusted — the withholding would outlive the reason for it.
    //
    // Moving costs one revalidation per minute on a one-slug population
    // (`routes/tournaments.py:86`) and cannot freeze anything.
    unfurlImageOptions(size, "moving"),
  );
}
