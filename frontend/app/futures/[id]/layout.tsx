import type { Metadata } from "next";
import type { FuturesMarketDetailResponse, FuturesOutcome } from "@/lib/types";
import {
  buildShareUrl,
  endShareSentence,
  formatShareProbability,
  truncateShareText,
} from "@/lib/share";
import { gradedWinner, leaderLabel, futuresTitleText } from "@/lib/futuresDetailDisplay";
import {
  unresolvedMetadata,
  unresolvedPath,
  type ResolutionFailure,
} from "@/lib/unresolvedShareMeta";

type FuturesMarketMetadata = FuturesMarketDetailResponse & {
  image_url?: string | null;
  hook_description?: string | null;
};

/** The market, or WHY there is no market — #5840 needs the two apart. */
type MarketLookup =
  | { ok: true; market: FuturesMarketMetadata }
  | { ok: false; failure: ResolutionFailure };

const API_URL = (process.env.NEXT_PUBLIC_API_URL || "https://api.bainluck.com").replace(/\/$/, "");

/**
 * #5840: a 404 and a bad minute are NOT the same answer.
 *
 * This used to return `null` for both, and the miss branch then claimed the
 * market did not exist. Claiming absence on a 500 or a dropped connection would
 * `noindex` a real market for as long as the failure lasted, so absence is
 * claimed only on a 404 — the one status that means it — or on a segment that
 * could never be an id at all.
 */
async function fetchMarket(id: string): Promise<MarketLookup> {
  const marketId = Number.parseInt(id, 10);
  if (!Number.isFinite(marketId) || marketId <= 0) {
    return { ok: false, failure: "not-found" };
  }

  try {
    const response = await fetch(`${API_URL}/api/futures/${marketId}`, {
      next: { revalidate: 60 },
    });
    if (response.status === 404) return { ok: false, failure: "not-found" };
    if (!response.ok) return { ok: false, failure: "unavailable" };
    return { ok: true, market: await response.json() };
  } catch {
    return { ok: false, failure: "unavailable" };
  }
}

function topOutcome(market: FuturesMarketMetadata): FuturesOutcome | null {
  const outcomes = market.outcomes ?? market.top_outcomes ?? [];
  if (outcomes.length === 0) return null;
  return [...outcomes].sort((a, b) => (b.probability ?? -1) - (a.probability ?? -1))[0];
}

/** How many priced names the description leads with before the standing tail. */
const BOARD_NAMES = 3;

/**
 * The board, in words: the leading names and what they are priced at.
 *
 * This is the "plain probability copy" half of check 8, and it is the DESCRIPTION
 * rather than a nicety because the description is the only line a pasted market
 * link gets that the title does not already carry. The title names the leader and
 * one number; a reader who pastes "Brazil Presidential election winner?" into a
 * chat wants to know who ELSE is on the board and by how much.
 *
 * Every name after the leader is dropped unless it carries a real price —
 * `formatShareProbability` returns null for absent/zero, and an unpriced name
 * beside two priced ones reads as 0% rather than as unknown.
 */
function boardSentence(
  outcomes: FuturesOutcome[],
  leader: FuturesOutcome,
  leaderProbability: string,
): string {
  const chasers = [...outcomes]
    .sort((a, b) => (b.probability ?? -1) - (a.probability ?? -1))
    .filter((o) => o !== leader)
    .map((o) => ({ name: o.name, label: formatShareProbability(o.probability) }))
    .filter((o): o is { name: string; label: string } => Boolean(o.label))
    .slice(0, BOARD_NAMES - 1);

  const parts = [
    `${leader.name} ${leaderProbability}`,
    ...chasers.map((o) => `${o.name} ${o.label}`),
  ];
  return `${parts.join(", ")}.`;
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  const lookup = await fetchMarket(id);
  if (!lookup.ok) {
    // #5840 — this branch used to return title+description and nothing else, so
    // Next inherited the root's `canonical: "/"` and `og:url: "/"` and a dead
    // market link previewed as the Bain Luck home page.
    // #5846 — the 4th argument. Next's `opengraph-image.tsx` file convention
    // overrides `og:image` and NOT `twitter:image`, so with nothing passed here
    // a dead link shipped two different pictures. Measured on production
    // 2026-09-13 11:49:13Z: `og:image` named
    // `…/futures/99999999/opengraph-image?d3e46b…` while `twitter:image` named
    // `https://www.bainluck.com/opengraph-image`. X reads the `twitter:`
    // namespace, so the same rotted link previewed as this route's own card in
    // Slack and as the HOME PAGE on X.
    const deadPath = unresolvedPath("futures", id);
    return unresolvedMetadata(
      deadPath,
      "market",
      lookup.failure,
      buildShareUrl(`${deadPath}/opengraph-image`),
    );
  }

  const market = lookup.market;
  const leader = topOutcome(market);
  const probability = formatShareProbability(leader?.probability);
  // #883 L2-55: a settled market's title must NOT carry the last-traded % — it's
  // "<winner> won", mirroring the L2-53 hero. Same winner selection as the page.
  const isResolved = market.status === "resolved";
  const outcomes = market.outcomes ?? market.top_outcomes ?? [];
  // #6079 — the GRADE, not the hero. This line used to call `pickHeroOutcome`,
  // whose ungraded fallback is the price leader, so the title crowned whichever
  // row happened to be expensive when trading stopped: production 05:36Z,
  // `/futures/61000391` served "No won - … Game 4 Winner" beside its own picture's
  // grey RESOLVED pill. `gradedWinner` is the one test all three surfaces use.
  const winnerName = leaderLabel(gradedWinner(outcomes, leader, market.status));

  const titleText = futuresTitleText({
    marketName: market.name,
    isResolved,
    winnerName,
    leaderName: leader?.name,
    probabilityLabel: probability,
  });
  // ── THE HOOK NO LONGER PRE-EMPTS THE PRICE ─────────────────────────────────
  // Check 8 is "a pasted game/market link unfurls with plain probability copy".
  // The game half already did; this half did not, because `hook_description ||`
  // sat in front of the probability sentence and won on every market that has a
  // hook — 10,997 of 15,560 tier-1-3 markets (70.7%) per /api/admin/hook-coverage
  // at 15:28Z, i.e. essentially every market anyone would paste. Measured on
  // production 2026-09-13 15:31Z, `/futures/60276241`:
  //
  //   og:description  "As Texas braces for another scorching summer, the question
  //                    of rainfall in Dallas for September 2026 has become
  //                    increasingly pertinent, with shifts in climate patterns
  //                    raising conc..."
  //
  // 180 characters of editorial scene-setting, no probability anywhere in it, cut
  // mid-word. The hook is not deleted and not wasted: `opengraph-image.tsx` still
  // draws it as the grey supporting line UNDER the big number, which is where
  // D102 says small grey type belongs — beside a figure it supports. What changed
  // is that the text a chat client prints beside the picture now states the board.
  // ── AND THE NAME IS OFTEN A QUESTION ───────────────────────────────────────
  // Both branches that embed `market.name` in a sentence used to assume it was a
  // noun phrase. Most market names are not: 136,601 resolved and 9,684 open names
  // end in `?` (production db-query 2026-09-13 21:52Z). Measured the same minute:
  //
  //   /futures/60544511  "77° or above won Temperature in New York City on
  //                       Sep 3, 2026 at 7pm EDT?. See the full probability…"
  //
  // A question mark cannot sit mid-sentence and cannot take a period after it.
  // The two branches fix it the two different ways the shapes demand, both of
  // them already house style:
  //
  //  - RESOLVED puts the name in PARENTHESES after the result, the pattern
  //    `buildBundleShareText` adopted for exactly this reason — a question
  //    reads fine parenthesised, and the terminator then belongs to OUR
  //    sentence, so the winner still leads (settled means settled, #883 L2-55).
  //  - The UNPRICED fallback LEADS with the name, where a trailing `?` is
  //    correct punctuation on its own, and `endShareSentence` supplies the
  //    period only for the names that end in none.
  //  - #6079 adds the third shape the first two were hiding between. A resolved
  //    market with nothing graded is neither: it has no winner to name, and its
  //    prices are the frozen last trades that L2-55 keeps out of settled copy, so
  //    letting it fall into the board branch would have swapped "No won" for
  //    "No 91%, Yes 9%." — a live-looking board on a closed market. It states the
  //    market and its state, in the picture's own word, and stops there.
  const description = truncateShareText(
    winnerName
      ? `${winnerName} won (${market.name}). See the full probability board on Bain Luck.`
      : isResolved
        ? `${endShareSentence(market.name)} This market has resolved. See the full probability board on Bain Luck.`
        : leader && probability
          ? `${boardSentence(outcomes, leader, probability)} See the full probability board on Bain Luck.`
          : `${endShareSentence(market.name)} See this market translated into intuitive probabilities on Bain Luck.`
  );
  const url = buildShareUrl(`/futures/${market.id}`);
  const image = buildShareUrl(`/futures/${market.id}/opengraph-image`);

  return {
    title: titleText,
    description,
    alternates: { canonical: url },
    openGraph: {
      title: `${titleText} | Bain Luck`,
      description,
      url,
      siteName: "Bain Luck",
      type: "article",
      images: [{ url: image, alt: market.name, width: 1200, height: 630 }],
    },
    twitter: {
      card: "summary_large_image",
      title: `${titleText} | Bain Luck`,
      description,
      images: [image],
    },
  };
}

export default function FuturesDetailLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
