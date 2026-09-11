/**
 * #4963 — A SHARE SURFACE PRINTS THE PAIR THE SERVER ALREADY DECIDED.
 *
 * ═══ THE DEFECT ═══
 *
 * The event share card printed two probabilities that add up to 101.
 *
 * Live specimen, `https://www.bainluck.com/events/15304803/opengraph-image`,
 * read 2026-09-10 23:03Z (Pirates @ Cubs):
 *
 *     PIR  48%          CUB  53%
 *
 * The data was never wrong. `GET /api/events/15304803` served
 * `home_probability 0.525 / away_probability 0.475` — an exact complement — and
 * ALSO served `home_rendered_percent: 53 / away_rendered_percent: 47`, which is
 * the whole-percent pair UX-P114 moved to the server precisely so that four
 * surfaces could not each answer differently.
 *
 * This card was the surface that never adopted it. It called
 * `formatShareProbability` on each side independently, and `Math.round` rounds
 * a half away from zero, so `52.5 → 53` and `47.5 → 48`. Each number is
 * individually defensible; the pair is arithmetically impossible. It is not an
 * edge case — the venues quote on a half-cent grid, so a blend landing on
 * `.5` is routine (34 of 414 live/upcoming events when UX-P114 measured it),
 * and when it lands there the sum is ALWAYS 101, never 99.
 *
 * ═══ THE SECOND SITE, WHICH IS THE ONE THAT MAKES THIS A CLASS ═══
 *
 * `components/discover/EventCard.tsx` had already adopted the served pair for
 * the strip it draws (`awayPct` / `homePct`, line ~91) and then re-derived the
 * SAME pair from the raw probabilities for its share SENTENCE. So the card on
 * screen read `53% / 47%` while the text handed to the share sheet said
 * `53%, 48%` — a number the reader cannot find on the card it came from, which
 * is the exact failure `buildBundleShareText` documents and avoids.
 *
 * A surface can therefore be half-fixed, and the half that is wrong is the half
 * a stranger receives. That is why this file asserts the PRINTED STRINGS on both
 * surfaces rather than asserting the helper, which was never the broken part.
 *
 * ═══ WHY IT ASSERTS THE RENDER AND NOT THE RULE ═══
 *
 * `servedDuelPercents` and `renderedDuelPercents` are already covered by their
 * own suites and by `contracts/rendered_percent.json`'s cross-runtime table.
 * Both were green throughout the bug. What was untested was whether these two
 * surfaces CALL them, and no test of a rounding rule can answer that. So the og
 * card is invoked for real (with `next/og` stubbed to capture the element tree)
 * and the Discover card is rendered for real (with `ActionBar` stubbed to
 * capture the share props), and the assertions read the strings a reader sees.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

/** The element `ImageResponse` was constructed with. `mock`-prefixed for jest hoisting. */
const mockImageResponseCalls: React.ReactElement[] = [];

jest.mock("next/og", () => ({
  __esModule: true,
  ImageResponse: function ImageResponse(element: React.ReactElement) {
    mockImageResponseCalls.push(element);
    return { __stub: "ImageResponse" };
  },
}));

/** Share props the Discover card handed `ActionBar`. `mock`-prefixed for hoisting. */
const mockShareCalls: { shareText: string }[] = [];

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

// Everything real except `ActionBar`. `requireActual` matters: this module also
// exports the badges, the signal bars and the chip this card renders, and
// stubbing those would change what is under test.
jest.mock("@/components/discover/shared", () => {
  const actual = jest.requireActual("@/components/discover/shared");
  const ReactLib = require("react");
  return {
    ...actual,
    ActionBar: (props: { shareText: string }) => {
      mockShareCalls.push({ shareText: props.shareText });
      return ReactLib.createElement("div", { "data-testid": "action-bar" });
    },
  };
});

import OgImage from "@/app/events/[id]/opengraph-image";
import { EventCard } from "@/components/discover/EventCard";
import type { FeedItem, FeedEventData } from "@/lib/types";

/* ─────────────────────────── the specimen table ─────────────────────────── */

/**
 * Each row is a payload shape the two surfaces genuinely meet, named by what
 * makes it different. `served` null means the payload predates UX-P114 — a real
 * case, because a Discover response is cached and the native and widget arms
 * ship on their own schedule.
 */
const PAIRS: ReadonlyArray<{
  name: string;
  home: number;
  away: number;
  servedHome: number | null;
  servedAway: number | null;
  /** What the card must print, `[away, home]`. */
  expect: [string, string];
}> = [
  {
    // The live specimen. This is the row that was 48/53 on production.
    name: "the half-percent blend, with the server's answer present",
    home: 0.525,
    away: 0.475,
    servedHome: 53,
    servedAway: 47,
    expect: ["47%", "53%"],
  },
  {
    // Same probabilities, pre-UX-P114 payload: the local fallback must reach
    // the same answer, or the fix only works on fresh responses.
    name: "the half-percent blend, with no served pair at all",
    home: 0.525,
    away: 0.475,
    servedHome: null,
    servedAway: null,
    expect: ["47%", "53%"],
  },
  {
    // #2279 — both served or neither. A payload carrying one field and not the
    // other must fall back WHOLE, not print a served value beside a derived one.
    name: "a torn payload carrying only the home side",
    home: 0.505,
    away: 0.495,
    servedHome: 51,
    servedAway: null,
    expect: ["49%", "51%"],
  },
  {
    // A settled game: `settled_hero` serves 1.0/0.0. The old code printed `--`
    // for the loser, because `formatShareProbability` returns null on a zero.
    // A finished game's loser is 0%, and 0% is a fact, not a missing value.
    name: "a settled game, where the loser is a real zero and not a blank",
    home: 1.0,
    away: 0.0,
    servedHome: 100,
    servedAway: 0,
    expect: ["0%", "100%"],
  },
  {
    // The ordinary case, to prove the fix did not move numbers that were fine.
    name: "an ordinary pair that was never at risk",
    home: 0.62,
    away: 0.38,
    servedHome: 62,
    servedAway: 38,
    expect: ["38%", "62%"],
  },
];

/* ──────────────────────────── the og share card ──────────────────────────── */

/** `current_odds` as `/api/events/{id}` serves it, minus the fields neither surface reads. */
function currentOdds(row: (typeof PAIRS)[number]) {
  return {
    captured_at: "2026-09-10T23:03:00Z",
    home_probability: row.home,
    away_probability: row.away,
    ...(row.servedHome === null ? {} : { home_rendered_percent: row.servedHome }),
    ...(row.servedAway === null ? {} : { away_rendered_percent: row.servedAway }),
    spread: null,
    over_under: null,
    projected_home_score: null,
    projected_away_score: null,
  };
}

/** Every string the element tree prints at the hero's own font size. */
function heroPercents(element: React.ReactElement): string[] {
  const found: string[] = [];
  const walk = (node: unknown): void => {
    if (Array.isArray(node)) {
      node.forEach(walk);
      return;
    }
    if (!React.isValidElement(node)) return;
    const props = node.props as { style?: { fontSize?: number }; children?: unknown };
    if (props?.style?.fontSize === 74 && typeof props.children === "string") {
      found.push(props.children);
    }
    walk(props?.children);
  };
  walk(element);
  return found;
}

/** Render the share card for one payload and return `[awayPct, homePct]` as printed. */
async function shareCardPercents(row: (typeof PAIRS)[number]): Promise<string[]> {
  mockImageResponseCalls.length = 0;
  global.fetch = jest.fn().mockResolvedValue({
    ok: true,
    json: async () => ({
      id: 15304803,
      home_team: "Chicago Cubs",
      away_team: "Pittsburgh Pirates",
      status: "scheduled",
      sport_key: "baseball_mlb",
      current_odds: currentOdds(row),
    }),
  }) as unknown as typeof fetch;

  await OgImage({ params: { id: "15304803" } });

  if (mockImageResponseCalls.length !== 1) {
    throw new Error(
      `expected exactly 1 ImageResponse, captured ${mockImageResponseCalls.length}`,
    );
  }
  return heroPercents(mockImageResponseCalls[0]);
}

describe("#4963 — the event share card prints one decision, not two roundings", () => {
  it.each(PAIRS)("$name", async (row) => {
    expect(await shareCardPercents(row)).toEqual(row.expect);
  });

  it("never prints a pair that does not total 100", async () => {
    for (const row of PAIRS) {
      const printed = await shareCardPercents(row);
      const total = printed.reduce((sum, p) => sum + Number.parseInt(p, 10), 0);
      expect({ row: row.name, printed, total }).toEqual({
        row: row.name,
        printed,
        total: 100,
      });
    }
  });

  it("still draws the card when the event cannot be fetched", async () => {
    // The no-data arm is unchanged by this fix and is the one path with no pair
    // to reconcile: both sides default to 0.5 and the card reads 50/50. Asserted
    // so that adopting the contract cannot quietly turn a coin-flip placeholder
    // into two blanks.
    mockImageResponseCalls.length = 0;
    global.fetch = jest.fn().mockResolvedValue({ ok: false }) as unknown as typeof fetch;

    await OgImage({ params: { id: "15304803" } });

    expect(heroPercents(mockImageResponseCalls[0])).toEqual(["50%", "50%"]);
  });
});

/* ─────────────────── the Discover card's share SENTENCE ─────────────────── */

const FEED_ITEM = {
  id: "event-15304803",
  type: "event",
  score: 90,
  reason: "Close game",
} as unknown as FeedItem;

function eventData(row: (typeof PAIRS)[number]): FeedEventData {
  return {
    id: 15304803,
    home_team: "Chicago Cubs",
    away_team: "Pittsburgh Pirates",
    sport_key: "baseball_mlb",
    sport_name: "MLB",
    status: "scheduled",
    commence_time: "2026-09-11T18:20:00Z",
    current_odds: currentOdds(row),
  } as unknown as FeedEventData;
}

/** Render the Discover card for one payload and return the share sentence. */
function shareSentence(row: (typeof PAIRS)[number]): string {
  mockShareCalls.length = 0;
  renderToStaticMarkup(
    <EventCard
      item={FEED_ITEM}
      data={eventData(row)}
      liked={false}
      setLiked={() => {}}
      onDismiss={() => {}}
      trending={false}
    />,
  );
  if (mockShareCalls.length !== 1) {
    throw new Error(`expected exactly 1 ActionBar render, captured ${mockShareCalls.length}`);
  }
  return mockShareCalls[0].shareText;
}

describe("#4963 — the Discover card's share text quotes the card, not a re-rounding", () => {
  it("names the same two percents the strip above it prints", () => {
    const row = PAIRS[0];
    expect(shareSentence(row)).toBe(
      "Chicago Cubs 53%, Pittsburgh Pirates 47% on Bain Luck.",
    );
  });

  it("never hands the share sheet a pair that does not total 100", () => {
    for (const row of PAIRS) {
      const sentence = shareSentence(row);
      const percents = [...sentence.matchAll(/(\d+)%/g)].map((m) => Number(m[1]));
      // Either the sentence prices the game, or it is the unpriced fallback —
      // never a priced sentence whose two numbers disagree with each other.
      if (percents.length === 0) {
        expect(sentence).toContain("Track ");
        continue;
      }
      expect({ row: row.name, percents }).toEqual({
        row: row.name,
        percents: [percents[0], 100 - percents[0]],
      });
    }
  });
});
