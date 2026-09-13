/**
 * THE COPY A PASTED `/tournaments/<slug>` LINK UNFURLS WITH (#5813).
 *
 * Pure, so the decision is testable without a browser and without the network:
 * `app/tournaments/[slug]/layout.tsx` fetches, this module decides, and the two
 * jobs never mix. `lib/eventShareMeta.ts` is the same split for game links.
 *
 * ═══ WHAT WAS ON PRODUCTION BEFORE THIS ═══
 *
 * `app/tournaments/[slug]/` held one `"use client"` `page.tsx` and no layout, so
 * the route rendered the ROOT metadata verbatim — title "Bain Luck — Prediction
 * Market Discovery", and `canonical`/`og:url` naming `https://www.bainluck.com`.
 * A real slug, a second real slug and a slug that does not exist unfurled
 * byte-identically: the card could not tell the US Open from a typo.
 *
 * ═══ THE TITLE NAMES LEADERS WITHOUT THEIR DRAW, ON PURPOSE ═══
 *
 * A hub has one board per draw — the US Open has two, Men's and Women's
 * Singles — so the honest long form is "Alexander Zverev 57% (Men's Singles),
 * Elena Rybakina 99% (Women's Singles)". That is 89 characters before the site
 * suffix, and unfurlers truncate a title well before that; buying precision
 * there spends the tournament's own name, which is the one word a reader needs.
 *
 * So the split is: the TITLE carries `<tournament>: <leader> <p>%, <leader> <p>%`
 * — the same shape `/events/[id]` already ships for a two-sided game — and the
 * DESCRIPTION, which every unfurler renders directly beneath it, names each
 * leader's draw in a full sentence. The ambiguity lasts one line.
 *
 * ═══ WHAT THIS DELIBERATELY DOES NOT DO ═══
 *
 * **It does not branch on a board row's `state`.** That field reads `"live"` on
 * every row of the served payload and sits beside `price_state`, `age_hours`
 * and `stale_sources` — it describes the freshness of the PRICE, not whether
 * anyone has won. Writing a settled branch on it would be inventing a
 * vocabulary. A finished tournament's champion lives in the `results` section,
 * which is in the payload's `rest` half and is not fetched here; naming the
 * winner is a follow-up with a settled specimen to test against, not a guess.
 *
 * Until then a decided draw still reads honestly, because a decided market
 * prices its winner at ~99%: "Elena Rybakina 99%" is true, and is not a claim
 * about a result.
 */

import { formatShareProbability, truncateShareText } from "@/lib/share";

/** The slice of `GET /api/tournaments/{slug}?sections=first` this copy reads. */
export interface TournamentShareBoardRow {
  display_name?: string | null;
  probability?: number | null;
}

export interface TournamentShareBoard {
  label?: string | null;
  rows?: TournamentShareBoardRow[] | null;
}

export interface TournamentShareSource {
  title?: string | null;
  subtitle?: string | null;
  boards?: TournamentShareBoard[] | null;
}

/** One board's front-runner, once it has a name and a printable probability. */
export interface BoardLeader {
  name: string;
  /** Already formatted, e.g. `"57%"`. */
  probability: string;
  /**
   * The raw 0..1 value `probability` was formatted from.
   *
   * Carried rather than parsed back out of the string (#5888). The share CARD
   * needs a bar width, and `Number.parseFloat("57%") / 100` would be a second
   * derivation of a number this module already has — the seam where a picture
   * starts disagreeing with the sentence beneath it.
   */
  fraction: number;
  /** The draw, e.g. `"Men's Singles"`. Absent when the board is unlabelled. */
  draw: string | null;
}

/**
 * How many leaders the title names before it stops.
 *
 * Two is the number of draws a Slam has. A hub with more boards than this is
 * not served worse by the cap — the description still names every one of them.
 */
const MAX_TITLE_LEADERS = 2;

function cleanText(value: string | null | undefined): string | null {
  const trimmed = (value ?? "").trim();
  return trimmed.length > 0 ? trimmed : null;
}

/**
 * The board's front-runner, chosen by probability rather than by position.
 *
 * The payload does ship `rank`, and its rows do arrive sorted — but trusting
 * arrival order makes the copy depend on a property of the producer that
 * nothing on this side asserts. `/futures/[id]`'s `topOutcome` sorts for the
 * same reason.
 */
function boardLeader(board: TournamentShareBoard): BoardLeader | null {
  const rows = (board.rows ?? []).filter(
    (row): row is TournamentShareBoardRow => row != null
  );
  if (rows.length === 0) return null;

  const top = [...rows].sort(
    (a, b) => (b.probability ?? -1) - (a.probability ?? -1)
  )[0];

  const name = cleanText(top.display_name);
  // `formatShareProbability` returns null for null/NaN/0 — a board whose leader
  // has no price is a board we say nothing numeric about, rather than one we
  // print "0%" for.
  const probability = formatShareProbability(top.probability);
  if (!name || !probability) return null;

  // `formatShareProbability` returned a string, so `top.probability` is a
  // finite non-zero number — that is exactly the condition it rejects on.
  return {
    name,
    probability,
    fraction: top.probability as number,
    draw: cleanText(board.label),
  };
}

function leaders(source: TournamentShareSource): BoardLeader[] {
  return (source.boards ?? [])
    .filter((board): board is TournamentShareBoard => board != null)
    .map(boardLeader)
    .filter((leader): leader is BoardLeader => leader !== null);
}

/**
 * The facts the unfurl reads, before anything decides how to say them.
 *
 * #5888 — the CARD needs these too. A pasted tournament link unfurls with a
 * title and a picture, and until this existed only the title was built from the
 * payload: the picture was the site's house card, identical for the US Open, the
 * Masters and a slug that does not exist.
 *
 * Extracted rather than re-derived, and that is the whole point. A second
 * "find the leader" in the image route would be a second answer to a question
 * this module has already answered carefully — `boardLeader` sorts by
 * probability rather than trusting arrival order, and drops a leader whose price
 * is null/NaN/0 instead of printing "0%". A picture disagreeing with the words
 * beneath it is the defect that split implementation produces, so there is one
 * implementation and both readers take it.
 */
export interface TournamentShareFacts {
  /** The hub's own title, or `"Tournament"` when it has none. */
  name: string;
  /** The hub's subtitle ("Flushing Meadows"), or null. */
  venue: string | null;
  /** One front-runner per priced board, in board order. */
  leaders: BoardLeader[];
}

export function tournamentShareFacts(
  source: TournamentShareSource
): TournamentShareFacts {
  return {
    name: cleanText(source.title) ?? "Tournament",
    venue: cleanText(source.subtitle),
    leaders: leaders(source),
  };
}

/**
 * The unfurl copy for one tournament hub.
 *
 * `title` carries NO site suffix: the root layout's template is `%s | Bain
 * Luck` and appending one here is what printed `| Bain Luck | Bain Luck` on
 * every event page. The `og:`/`twitter:` tags bypass the template, so the
 * layout adds the suffix for those with `eventShareMeta`'s `withSiteSuffix` —
 * the one idempotent implementation, rather than a second spelling of it
 * (#3292 is open about exactly that kind of copy).
 */
export function buildTournamentShareCopy(source: TournamentShareSource): {
  title: string;
  description: string;
} {
  const { name, venue, leaders: found } = tournamentShareFacts(source);

  if (found.length === 0) {
    // No priced board — say what the page is, and claim nothing about who is
    // ahead. `venue` is the hub's own subtitle ("Flushing Meadows"), not a
    // sentence written for a reviewer.
    return {
      title: name,
      description: truncateShareText(
        venue
          ? `${name}, ${venue}. Every contender's chance of winning, as one clean probability.`
          : `${name}: every contender's chance of winning, as one clean probability.`
      ),
    };
  }

  const titleLeaders = found
    .slice(0, MAX_TITLE_LEADERS)
    .map((leader) => `${leader.name} ${leader.probability}`)
    .join(", ");

  const sentences = found.map((leader) =>
    leader.draw
      ? `${leader.name} leads the ${leader.draw} at ${leader.probability}.`
      : `${leader.name} leads at ${leader.probability}.`
  );

  return {
    title: `${name}: ${titleLeaders}`,
    description: truncateShareText(
      venue ? `${venue}. ${sentences.join(" ")}` : sentences.join(" ")
    ),
  };
}
