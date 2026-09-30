/**
 * #5811 (consumer half; producer = live's PR #9821) — A FIGHT THE VENUE CLOSED
 * WITH NO WINNER STOPS SITTING UNDER "LIVE & PAUSED".
 *
 * ═══ WHAT A READER SAW ═══
 *
 * `/sports` at 390px, 2026-09-30 09:39Z: Live & Paused, one card —
 * `MMA · No result reported · Sep 29 · Erick Visconde / Ilias Bulaid`
 * (15320964, `suspended`, no score). The fight was over: Kalshi finalized both
 * `KXUFCFIGHT-26SEP29BULVIS-*` markets as `scalar` — a split settlement, no
 * winner — and all six attached markets carry #7035's `venue_voided` stamp.
 * Nothing names a winner, so `venue_settled` is rightly false and the card had
 * no end state to give. It would have sat there until the row retired.
 *
 * ═══ THE CONTRACT ═══
 *
 * PR #9821 serves `venue_closed_no_winner: true` beside the `venue_settled`
 * pair, on every door that serves the pair, and ONLY when true. This card
 * reads it through `venueSettledSummary` — the one sentence every surface
 * already asks — so the card says "Ended · no winner" and the section files it
 * where results file, from one reading.
 *
 * The corpus is #5811's own (`feedDwcsBouts.20260930-5811.json`, the bout as
 * production served it) with the producer's key grafted on; `asServed` is the
 * card before #9821 and every cached page after it.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync, readdirSync, statSync } from "fs";
import { join } from "path";

import corpus from "../fixtures/feedDwcsBouts.20260930-5811.json";
import FeedCard from "@/components/FeedCard";
import { feedEventSectionKey, groupFeedIntoSections } from "@/lib/feedSections";
import { partitionFinishedGames } from "@/lib/sports/finishedSection";
import { leagueSectionKey } from "@/lib/sports/leagueSections";
import { unreportedRailTitle, MIXED_UNREPORTED_RAIL_TITLE } from "@/lib/leagueCards";
import {
  SUSPENDED_LABEL,
  VENUE_CLOSED_NO_WINNER_LABEL,
  venueSettledSummary,
} from "@/lib/eventState";
import type { Event, FeedEventData, FeedItem } from "@/lib/types";

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});

jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({ track: () => {} }),
}));

const VOID_ID = 15320964;

function asServed(): FeedItem {
  const item = (corpus.feed_items as unknown as FeedItem[]).find(
    (i) => (i.data as FeedEventData).id === VOID_ID,
  );
  if (!item) throw new Error(`corpus lost ${VOID_ID}`);
  return JSON.parse(JSON.stringify(item));
}

/** The bout as PR #9821 serves it: the pair unchanged, the new key present. */
function closedNoWinner(): FeedItem {
  const item = asServed();
  Object.assign(item.data as FeedEventData, {
    venue_settled: false,
    venue_settled_result: null,
    venue_closed_no_winner: true,
  });
  return item;
}

const data = (item: FeedItem) => item.data as FeedEventData;
const render = (item: FeedItem) => renderToStaticMarkup(<FeedCard item={item} />);
const slotText = (html: string) =>
  html.match(/max-w-\[46%\]"[^>]*>([^<]*)<\/span>/)?.[1] ?? null;
const DATE = / · [A-Z][a-z]{2} \d{1,2}$/;

describe("A · the sentence", () => {
  test("venueSettledSummary: the key alone ends the contest with no winner", () => {
    expect(venueSettledSummary(false, null, true)).toBe(VENUE_CLOSED_NO_WINNER_LABEL);
    expect(venueSettledSummary(undefined, undefined, true)).toBe(VENUE_CLOSED_NO_WINNER_LABEL);
    expect(VENUE_CLOSED_NO_WINNER_LABEL).toBe("Ended · no winner");
  });

  test("absent or false says nothing — absent is 'not established', not 'still going'", () => {
    expect(venueSettledSummary(false, null)).toBeNull();
    expect(venueSettledSummary(false, null, false)).toBeNull();
    expect(venueSettledSummary(false, null, null)).toBeNull();
  });

  test("a graded winner outranks the key", () => {
    expect(venueSettledSummary(true, "Ian Escuza wins", true)).toBe("Settled · Ian Escuza wins");
  });
});

describe("B · FeedCard", () => {
  test("the closed bout reads `Ended · no winner`, not `No result reported`", () => {
    const html = render(closedNoWinner());
    expect(slotText(html)?.replace(DATE, "")).toBe("Ended · no winner");
    expect(html).not.toContain(SUSPENDED_LABEL);
    expect(html).toContain('aria-label="Erick Visconde at Ilias Bulaid - Ended · no winner"');
  });

  test("CONTROL: as served (key absent) the card is exactly what it was", () => {
    const html = render(asServed());
    expect(html).toContain(SUSPENDED_LABEL);
    expect(html).not.toContain(VENUE_CLOSED_NO_WINNER_LABEL);
  });
});

describe("C · the section is the card's sentence", () => {
  test("the feed files the closed bout as finished; as served it stays live", () => {
    expect(feedEventSectionKey(data(closedNoWinner()))).toBe("finished");
    expect(feedEventSectionKey(data(asServed()))).toBe("live");
  });

  test("a stray key cannot move a LIVE row", () => {
    const live = closedNoWinner();
    data(live).status = "live";
    expect(feedEventSectionKey(data(live))).toBe("live");
  });

  test("/sports: Live & Paused empties and the Finished partition takes the bout", () => {
    const sections = groupFeedIntoSections([closedNoWinner()]);
    expect(sections.map((s) => s.key)).not.toContain("live");
    const { finished, rest } = partitionFinishedGames([closedNoWinner()]);
    expect(finished.map((i) => data(i).id)).toEqual([VOID_ID]);
    expect(rest).toEqual([]);
  });

  test("the league page files it the same way", () => {
    const event = {
      ...(data(closedNoWinner()) as unknown as Event),
    };
    expect(leagueSectionKey(event)).toBe("finished");
    const served = { ...(data(asServed()) as unknown as Event) };
    expect(leagueSectionKey(served)).toBe("live");
  });

  test("an unreported rail holding the closed bout stops heading itself `No result reported`", () => {
    expect(unreportedRailTitle([{ venue_settled: false, venue_closed_no_winner: true }])).toBe(
      MIXED_UNREPORTED_RAIL_TITLE,
    );
    expect(unreportedRailTitle([{ venue_settled: false }])).toBe(SUSPENDED_LABEL);
  });
});

describe("D · every surface that asks the sentence passes the key", () => {
  // The census, not a list: a caller that passes the pair and not the key
  // prints "No result reported" on the one surface nobody photographed.
  const ROOT = join(__dirname, "..", "..");
  const files: string[] = [];
  const walk = (dir: string) => {
    for (const name of readdirSync(dir)) {
      if (name === "node_modules" || name === "__tests__" || name.startsWith(".")) continue;
      const p = join(dir, name);
      if (statSync(p).isDirectory()) walk(p);
      else if (/\.tsx?$/.test(name)) files.push(p);
    }
  };
  for (const d of ["app", "components", "lib"]) walk(join(ROOT, d));

  const calls = files.flatMap((f) => {
    const src = readFileSync(f, "utf8");
    return Array.from(src.matchAll(/venueSettledSummary\(([^)]*)\)/g))
      .filter((m) => !src.slice(Math.max(0, m.index! - 20), m.index!).includes("function "))
      .filter((m) => m[1].trim().length > 0 && !m[1].includes("…") && !m[1].includes("..."))
      .map((m) => ({ file: f.slice(ROOT.length + 1), args: m[1] }));
  });

  test("the census found the surfaces (strawman)", () => {
    expect(calls.length).toBeGreaterThanOrEqual(8);
  });

  test.each(calls.map((c) => [c.file, c.args]))("%s passes venue_closed_no_winner", (_f, args) => {
    expect(args).toMatch(/venue_closed_no_winner/);
  });
});
