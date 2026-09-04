/**
 * ux/1053 — THE /sports "Finished" SECTION: which finals it shows, in what
 * order, and where the ones it does not show can be found.
 *
 * ═══ WHAT ALEX SAW, MEASURED ═══
 *
 * `GET /api/feed?limit=40&mode=sports`, 2026-09-03: 25 event cards, **14 of them
 * settled**. They were not gathered anywhere — the sectioner filed them under
 * "Just Happened" ABOVE Upcoming, so more than half the games on the browse
 * surface were games you could no longer watch, sitting on top of the ones you
 * could. D54 = A: results get their own section, and it sits below the two
 * sections about things that have not finished.
 *
 * ═══ WHY THIS TAKES THE FINISHED CARDS OFF `applyFinishedCardGuard` ═══
 *
 * 🔴 THE MOST LOAD-BEARING PARAGRAPH IN THIS FILE. UX-1034f's guard ages a
 * settled card out at `COMPLETED_EVENT_MAX_AGE_HOURS` (8h past commence). Its
 * own docblock says what it is and is not:
 *
 *   *"THIS IS THE SYMPTOM GUARD, NOT THE RANKING FIX. It ages out results that
 *   have stopped being results. It does NOT decide how much of page one a day's
 *   finished games may occupy — a day-turnover wall of 13 same-day finals is a
 *   ranking call, it belongs to the feed scorer, and no frontend filter should
 *   quietly make that decision on the scorer's behalf."*
 *
 * This section IS that ranking fix, so it takes the decision back. An 8-hour
 * clock cannot coexist with the ask: at 1:20pm PT every one of last night's
 * finals is over 8 hours old, so "today's finals first, then yesterday's" is
 * literally unrenderable while the guard owns them — it had already deleted the
 * whole section. What replaces the clock is a CALENDAR BOUND plus a CAP: today
 * and yesterday, most recent first, capped at one screen. The cap is what stops
 * the flood the guard was standing in front of, and it is declared.
 *
 * The guard is NOT deleted and NOT weakened. It keeps running, over everything
 * else in the payload — a `closed`/`resolved` futures market is still stale and
 * still goes. It simply no longer sees game cards, because this module removes
 * them from the list first.
 *
 * ═══ D27: STATE COMES FROM THE AUTHORITY ═══
 *
 * "Finished" is `eventSectionKey(status) === "finished"` — i.e.
 * `completed`/`closed`, something with standing saying the event is over. Never
 * a price at 0.99, never "the clock says it should be done by now". A
 * `suspended` match is NOT finished and does not appear here; it stays in the
 * live bucket, which is the one honest place for it (live/048).
 *
 * PURE, and `now` is always injectable — an anchor that branches on the real
 * clock is not an anchor (gotcha #44).
 */

import type { FeedEventData, FeedItem, SportHierarchy } from "@/lib/types";
import { eventSectionKey } from "@/lib/eventState";
import { finishedDayOffset } from "@/lib/gameTimeLabel";

/**
 * How many finals the section shows before it declares a cap.
 *
 * ONE SCREEN AT THE WIDTH ALEX SHOPS AT. A settled shared card is ~135px tall at
 * 390px and this section never starts at the top of the viewport — Live Now and
 * Upcoming are above it — so four cards is the row count that fills the fold
 * without pushing Player Props and Top Markets off the end of a reader's
 * patience. Not a magic number so much as a stated one: it is declared on the
 * card row below the grid, which is what makes it a cap rather than coverage.
 */
export const FINISHED_SECTION_CAP = 4;

/**
 * The oldest day the section will carry. `1` = yesterday.
 *
 * The queue's own bound, and it is a better rule than the hours it replaces: a
 * reader asking "what happened?" means today and last night, and a calendar day
 * is a unit they already hold. An hours count answers a different question
 * (how stale is this row) and answers it differently at 9am than at 11pm.
 */
export const FINISHED_SECTION_MAX_DAY_OFFSET = 1;

/** Why a settled card the payload carried is not on screen. */
export type FinishedDropReason =
  /** Older than yesterday — a result that has stopped being a result. */
  | "finished_older_than_yesterday"
  /** No trustworthy finish date, so no day to file it under (gotcha #14). */
  | "finished_undated"
  /** In the window, cut by the cap. The "more" links lead to these. */
  | "finished_section_cap";

export interface FinishedSplit {
  /** Every settled GAME card in the payload, by authority, in payload order. */
  finished: FeedItem[];
  /** Everything else, in payload order. This is what the freshness guard sees. */
  rest: FeedItem[];
}

/**
 * Take the settled game cards out of the payload.
 *
 * Games only. A settled FUTURES market is not a result a reader watched and it
 * belongs to Top Markets and to the freshness guard, exactly as before.
 */
export function partitionFinishedGames(items: FeedItem[]): FinishedSplit {
  const finished: FeedItem[] = [];
  const rest: FeedItem[] = [];
  for (const item of items) {
    if (isFinishedGame(item)) finished.push(item);
    else rest.push(item);
  }
  return { finished, rest };
}

function isFinishedGame(item: FeedItem): boolean {
  if (item.type !== "event") return false;
  return eventSectionKey((item.data as FeedEventData).status) === "finished";
}

export interface FinishedSection {
  /** The cards to render, today's first and most recent first within a day. */
  shown: FeedItem[];
  /** Everything the window or the cap held back, with the reason it was held. */
  dropped: { item: FeedItem; reason: FinishedDropReason }[];
  /** True when the cap (not the window) held something back — declare it. */
  cappedMore: boolean;
}

/**
 * Order the settled cards and cut them to one screen.
 *
 * ORDER: day ascending (today, then yesterday), then most recent first inside a
 * day. The feed's own order is by SCORE, which is the right answer to "which
 * game is interesting" and the wrong one to "what just happened" — a results
 * list is read from the top for the most recent thing, which is the same rule
 * `sortedResults` applies on the tournament hub.
 */
export function buildFinishedSection(
  finished: FeedItem[],
  now: number = Date.now(),
): FinishedSection {
  const dropped: { item: FeedItem; reason: FinishedDropReason }[] = [];
  const dated: { item: FeedItem; day: number; at: number }[] = [];

  for (const item of finished) {
    const data = item.data as FeedEventData;
    const day = finishedDayOffset(data.commence_time, now);
    if (day === null) {
      // The card cannot say WHEN it finished, so it cannot be filed under a day.
      // Same three cases `formatFinishedGameLabel` renders no date for, and the
      // loudest of them is real: `commence_time` sometimes holds a Kalshi
      // close/resolution stamp, which can be a future instant on a settled row.
      dropped.push({ item, reason: "finished_undated" });
      continue;
    }
    if (day > FINISHED_SECTION_MAX_DAY_OFFSET) {
      dropped.push({ item, reason: "finished_older_than_yesterday" });
      continue;
    }
    dated.push({ item, day, at: new Date(data.commence_time).getTime() });
  }

  dated.sort((a, b) => (a.day !== b.day ? a.day - b.day : b.at - a.at));

  const shown = dated.slice(0, FINISHED_SECTION_CAP).map((e) => e.item);
  const overflow = dated.slice(FINISHED_SECTION_CAP);
  for (const e of overflow) {
    dropped.push({ item: e.item, reason: "finished_section_cap" });
  }

  return { shown, dropped, cappedMore: overflow.length > 0 };
}

// ---------------------------------------------------------------------------
// Where "more" goes
// ---------------------------------------------------------------------------

export interface LeagueResultsLink {
  /** The league's own name, from the register. */
  label: string;
  /** Its league page, whose Recent Results rail is THIS component. */
  href: string;
}

/**
 * How many leagues the cap declaration will name before it stops.
 *
 * A declaration is a sentence a reader finishes. Six league names is a nav bar
 * that has wandered into a footnote.
 */
export const MAX_RESULTS_LINKS = 3;

/**
 * The league pages holding the results this section had to leave out.
 *
 * ═══ WHY THE REGISTER AND NOT A MAP IN THIS FILE ═══
 *
 * `/api/sports/hierarchy` already answers "which league page owns this sport
 * key" — `SportLeague.sport_keys` is exactly that edge, and `grid_slug` was
 * lifted out of a hardcoded page-local `GRID_SLUG_MAP` under UX-P062 for the
 * identical reason: register data copied into a component is a second register
 * that drifts the first time a league is renamed. A hand-written map here would
 * also be the UX-P145 class — a fact about the world hard-coded in a component
 * and wrong the afternoon it changes.
 *
 * ═══ AND A LEAGUE THE REGISTER DOES NOT KNOW GETS NO LINK ═══
 *
 * Measured on the 2026-09-03 payload: the 14 finals span `baseball_mlb`,
 * `tennis_atp_us_open`, `tennis_wta_us_open` and
 * `soccer_switzerland_superleague`. The register knows the first three; it has
 * no Swiss Super League page. That league is therefore simply not named. A
 * guessed `/sport/soccer/superleague` would be UX-P062 register E5 — *"a link
 * that goes nowhere teaches a reader their tap did not register"* — and the cap
 * is still declared with or without any link at all.
 *
 * Keys are matched on an exact hit or a `_`-delimited prefix, longest first:
 * the register carries `tennis_atp` and the feed serves `tennis_atp_us_open`,
 * and the ATP Tour page is where that match's result lives. The `_` boundary is
 * what stops a prefix bleeding into an unrelated key.
 */
export function leagueResultsLinks(
  items: FeedItem[],
  sports: SportHierarchy[] | undefined,
  limit: number = MAX_RESULTS_LINKS,
): LeagueResultsLink[] {
  if (!sports || sports.length === 0) return [];

  const index: { key: string; link: LeagueResultsLink }[] = [];
  for (const sport of sports) {
    for (const league of sport.leagues ?? []) {
      for (const key of league.sport_keys ?? []) {
        if (!key) continue;
        index.push({
          key,
          link: { label: league.name, href: `/sport/${sport.slug}/${league.slug}` },
        });
      }
    }
  }
  // Longest key first, so a specific registration always beats a broader one
  // that happens to prefix it.
  index.sort((a, b) => b.key.length - a.key.length);

  const links: LeagueResultsLink[] = [];
  const seen = new Set<string>();
  for (const item of items) {
    if (item.type !== "event") continue;
    const sportKey = (item.data as FeedEventData).sport;
    if (!sportKey) continue;
    const hit = index.find(
      (entry) => sportKey === entry.key || sportKey.startsWith(`${entry.key}_`),
    );
    if (!hit || seen.has(hit.link.href)) continue;
    seen.add(hit.link.href);
    links.push(hit.link);
    if (links.length >= limit) break;
  }
  return links;
}
