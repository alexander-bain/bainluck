/**
 * #10207 — WHICH /sports CARDS ARE HEADLINES, AND WHAT THE PAGE LEADS WITH.
 *
 * ═══ WHAT ALEX SAW (2026-10-02, saved under
 *     artifacts/sports-editorial-specimens-20261002) ═══
 *
 * /sports opened on Live Now: a regional MMA bout, three fall-series golf
 * events, a Nations League match, a Finnish Liiga game and the same MMA bout
 * again as a card. The MLB postseason sat below all of it, under Upcoming.
 *
 * The served order was not the fault. `GET /api/feed?mode=sports&limit=100`
 * led with Yankees–Rays (score 79, slot 0) and carried White Sox–Guardians
 * (slot 3) and Padres–Brewers (slot 18) on page one; the Liiga game was slot 19
 * at score 30. The SECTIONER moved them: `groupFeedIntoSections` puts every
 * live card above every upcoming one, so a 30 that is live outranks a 79 that
 * starts tomorrow. Supply ✓, membership ✓, within-section order ✓, section
 * priority ✗. That is the one layer this module decides.
 *
 * Finished had the same shape one section lower: four early-round China Open
 * matches (all `tier:4`) filled the four slots, and last night's Thursday Night
 * Football final and an MLB postseason final were capped behind a "More results
 * in … NFL" link — because they ended before midnight and the tennis after it.
 *
 * ═══ THE RULE, ONE DEFINITION FOR BOTH SECTIONS ═══
 *
 * A headline is a card the serializer has already labelled as one. No new
 * scoring: every input here is a field the payload carries today.
 *
 *  - a game tagged `tier:1` (NFL, NBA, MLB, NHL, EPL, La Liga, UCL, …), or
 *    `importance:playoff` / `importance:championship`, unless it is an
 *    exhibition;
 *  - a Grand Slam tennis match — tennis at `tier:2`, which the backend tier
 *    table (`highlights.LEAGUE_TIERS`) gives to the four Slams and nothing
 *    else. This clause is what keeps #4454 true: the Shelton–Alcaraz US Open
 *    quarter-final, the card that section exists for, is stored with
 *    `llm_importance = unknown` and serves `tier:2`, so without it a Slam
 *    match would lose a results slot to a regular-season ballgame;
 *  - a tournament or event-concept card flagged `is_major` or `is_marquee`.
 *
 * A quiet slate has no headline and the page reads exactly as before — this
 * never invents prominence the supply does not have.
 */

import type {
  FeedConceptData,
  FeedEventData,
  FeedItem,
  FeedTournamentData,
} from "@/lib/types";
import { countCards, type FeedSection } from "@/lib/feedSections";

/** Is this game, tournament or event concept a headline? See the module docblock. */
export function isHeadlineCard(item: FeedItem): boolean {
  if (item.type === "tournament") {
    const td = item.data as unknown as FeedTournamentData;
    return !!(td.is_major || td.is_marquee);
  }
  if (item.type === "concept") {
    const cd = item.data as unknown as FeedConceptData;
    return !!(cd.is_major || cd.is_marquee);
  }
  if (item.type !== "event") return false;
  const tags = new Set((item.data as FeedEventData).event_tags ?? []);
  if (tags.has("importance:exhibition")) return false;
  if (tags.has("importance:playoff") || tags.has("importance:championship")) return true;
  if (tags.has("tier:1")) return true;
  return tags.has("sport:tennis") && tags.has("tier:2");
}

/**
 * The Finished section's band: 0 a postseason headline (playoff/championship),
 * 1 any other headline, 2 everything else. Lower is shown first.
 *
 * Why postseason gets its own band among results: on 2026-10-02 two early-
 * October NHL games tagged `importance:regular_season` ended after the
 * Phillies–Braves postseason final and took the last of the four slots from
 * it. A result that decides a series outranks one that decides nothing. A
 * Grand Slam match and a regular-season ballgame still share band 1 and are
 * ordered by when they ended, which is #4454's contract.
 */
export function finishedHeadlineBand(item: FeedItem): 0 | 1 | 2 {
  if (!isHeadlineCard(item)) return 2;
  if (item.type !== "event") return 1;
  const tags = (item.data as FeedEventData).event_tags ?? [];
  return tags.includes("importance:playoff") || tags.includes("importance:championship")
    ? 0
    : 1;
}

/**
 * How many headline games the Top Games row lifts above Live Now.
 * One row at desktop width (four 320px columns) and about one phone screen at
 * 390px. It is a lead, not a second Upcoming — the rest stay where they were.
 */
export const TOP_GAMES_CAP = 4;

/** Stable: headlines first, each half in the order it was served. */
function headlinesFirst(items: FeedItem[]): FeedItem[] {
  const lead: FeedItem[] = [];
  const rest: FeedItem[] = [];
  for (const item of items) (isHeadlineCard(item) ? lead : rest).push(item);
  return lead.length === 0 || rest.length === 0 ? items : [...lead, ...rest];
}

function withItems(section: FeedSection, items: FeedItem[]): FeedSection {
  return { ...section, items, count: countCards(items) };
}

/**
 * Order the /sports game sections (everything `groupFeedIntoSections` returns
 * except Top Markets).
 *
 *  1. Inside Live Now, headlines come first. A live NFL game is never seventh
 *     behind six minor live cards because of where it fell in the served list.
 *  2. When Live Now holds NO headline and Upcoming does, the first
 *     `TOP_GAMES_CAP` upcoming headlines become a "Top Games" section above
 *     Live Now, and leave Upcoming. Moved, never copied.
 *
 * Why a lead row and not "put Upcoming above Live Now": /sports pages more
 * games into Upcoming as the reader scrolls, so a Live Now section placed
 * after it would move further down with every page and stop being reachable on
 * a phone. Live Now stays second; it just stops being first by default.
 *
 * A Live Now section that holds a headline still leads, unchanged. A slate with
 * no headline anywhere returns its sections untouched.
 */
export function orderSportsGameSections(sections: FeedSection[]): FeedSection[] {
  const live = sections.find((s) => s.key === "live");
  const upcoming = sections.find((s) => s.key === "upcoming");

  const ordered = sections.map((s) =>
    s.key === "live" ? withItems(s, headlinesFirst(s.items)) : s,
  );

  if (live && live.items.some(isHeadlineCard)) return ordered;
  if (!upcoming) return ordered;

  const top: FeedItem[] = [];
  const remaining: FeedItem[] = [];
  for (const item of upcoming.items) {
    if (top.length < TOP_GAMES_CAP && isHeadlineCard(item)) top.push(item);
    else remaining.push(item);
  }
  if (top.length === 0) return ordered;

  const topGames: FeedSection = {
    key: "top-games",
    emoji: "⭐",
    title: "Top Games",
    accent: "text-text-primary",
    items: top,
    count: countCards(top),
  };
  const out: FeedSection[] = [topGames];
  for (const s of ordered) {
    if (s.key !== "upcoming") out.push(s);
    else if (remaining.length > 0) out.push(withItems(s, remaining));
  }
  return out;
}
