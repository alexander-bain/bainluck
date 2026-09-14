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
 *
 * AMENDED (#6149). That last paragraph held only as far as the rounding. A
 * price at or above 0.995 prints "100%", and "leads at 100%" is not a forecast
 * whoever is ahead — so `boardLeader` now withholds such a board entirely. The
 * refusal above is unchanged and is the reason this is the right shape: the
 * module still never reads a result out of a price, it just stops narrating a
 * certainty as a lead. See `PRINTS_AS_CERTAIN`.
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

/**
 * The probability at or above which a board stops being a FORECAST (#6149).
 *
 * `formatShareProbability` rounds, so the reader-visible claim turns over one
 * rounding step below 1.0: 0.995 prints "100%" and 0.994 prints "99%". The
 * constant is the formatter's own boundary rather than a taste judgement about
 * what counts as nearly certain, and `tournamentCertaintyUnfurl6149.test.tsx`
 * asserts both sides of it against `formatShareProbability` itself — if the
 * formatter ever stops rounding, that test fails rather than this drifting.
 *
 * Deliberately a second declaration rather than an import of
 * `eventConceptShareMeta`'s. That module is `/event/[domain]/[slug]`'s copy and
 * this one is the hub's; nothing else crosses between them, and importing a
 * private constant through a module boundary that carries no other traffic
 * would tie two independently-evolving surfaces together for three characters.
 * The shared thing is `formatShareProbability`, and both are pinned to it.
 */
const PRINTS_AS_CERTAIN = 0.995;

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
  const fraction = top.probability as number;

  // ═══ "LEADS AT 100%" IS NOT A SENTENCE A LIVE DRAW CAN PRODUCE (#6149) ═══
  //
  // Measured on production: the men's singles FINAL (event 15310688, Zverev vs
  // Shelton, completed 2026-09-13 21:53:36Z) carried four blend readings at or
  // above 0.995 BEFORE it completed — 0.9950 at 21:47:16Z rising to 0.9990 at
  // 21:53:20Z. Throughout that ~6.3-minute window the draw was undecided, so
  // `apply_final_result` had nothing to null, and `apply_final_match_blend` was
  // correctly promoting the live match blend onto the board. The payload was
  // right; this line printed "Alexander Zverev leads the Men's Singles at 100%"
  // over a match still being played. Across the two draws, 102 of 229 match
  // events have held a reading in that band (363 readings, max 0.9995).
  //
  // A second route needs no live match at all. #5917 exists because the board
  // published "Elena Rybakina 99% TO WIN THE TITLE" seventeen hours after she
  // won it, and `apply_final_result`'s own docstring concedes "a miss here is a
  // real miss". At 0.997 rather than 0.99 that same lag prints "100%".
  //
  // So this is NOT #6029's stale-read occasion repeated — the payload here is
  // current and correct, and the branch is the defect. It claims strictly less,
  // never more: no result is inferred from a price, and the card upgrades
  // itself the moment `apply_final_result` publishes `decided`.
  //
  // THE BOARD IS WITHHELD WHOLE, NOT THE PLAYER. Dropping only the certain
  // leader would promote the runner-up, so a draw whose title is effectively
  // decided would be captioned "Ben Shelton leads at 0%" — a top price that is
  // not a forecast makes the whole ranking meaningless. Returning null is the
  // trade this function already makes for a leader with no price at all, and it
  // is per-BOARD, so the other draw still prints.
  //
  // The band is one rounding step wide on purpose: 0.994 still prints "99%" and
  // a genuinely lopsided live draw is untouched.
  if (fraction >= PRINTS_AS_CERTAIN) return null;

  return {
    name,
    probability,
    fraction,
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
    // No board this module will put a number on — every one is unpriced, or
    // settled, or (since #6149) priced at a certainty that is no longer a
    // forecast. Say what the page is and claim nothing about who is ahead.
    // `venue` is the hub's own subtitle ("Flushing Meadows"), not a sentence
    // written for a reviewer.
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
