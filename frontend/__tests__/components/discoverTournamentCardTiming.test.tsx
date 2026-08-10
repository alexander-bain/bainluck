/**
 * UX-P050 — the eight cards on the default landing page say what they are.
 *
 * Discover is the default landing page. On 2026-08-10 `/api/feed` returned 21
 * items and the client suppressed 13 of them as empty concept envelopes, so the
 * EIGHT golf tournament cards asserted here were, literally, the whole page.
 *
 * Three of them said nothing about time at all, and a fourth said something
 * false. Both directions are guarded per gotcha #43: the broken cards gain an
 * honest line AND the four that already read correctly are byte-identical.
 *
 * The clock is FROZEN, never seeded from `Date.now()` (gotcha #44) — the card
 * reads the ambient clock, so a run straddling a date boundary could otherwise
 * flip "Starts Thu, Aug 13" to "Starts tomorrow".
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { FeedTournamentData } from "@/lib/types";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

jest.mock("@/components/Analytics", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: () => {} }),
}));

import { TournamentCard } from "../../components/discover/TournamentCard";

/** Monday 2026-08-10 22:40:00Z — the instant the slate below was captured. */
const NOW_T = Date.parse("2026-08-10T22:40:00Z");

beforeAll(() => {
  jest.useFakeTimers();
  jest.setSystemTime(NOW_T);
});
afterAll(() => {
  jest.useRealTimers();
});

function card(over: Partial<FeedTournamentData>): FeedTournamentData {
  return {
    key: "k",
    name: "A Tournament",
    is_major: false,
    golfers: [{ name: "A Golfer", probability: 0.27, rank: 1, movement_24h: null }],
    market_ids: [1],
    source_count: 1,
    ...over,
  } as FeedTournamentData;
}

function render(data: FeedTournamentData): string {
  return renderToStaticMarkup(
    <TournamentCard data={data} liked={false} setLiked={() => {}} />,
  );
}

/** Verbatim from the production payload, in the order the feed returned them. */
const SLATE: Array<{
  name: string;
  commence_time: string;
  resolution_date: string;
  expect: string;
}> = [
  { name: "Danish Golf Championship", commence_time: "2026-08-13T00:00:00+00:00", resolution_date: "2026-08-30T00:00:00+00:00", expect: "Starts Thu, Aug 13" },
  { name: "Golfers To Win A Pga Tour Major Before 2030", commence_time: "2026-07-19T18:17:17+00:00", resolution_date: "2030-07-07T14:00:00+00:00", expect: "Resolves Jul 7, 2030" },
  { name: "Fedex St Jude Championship", commence_time: "2026-08-08T16:01:09+00:00", resolution_date: "2026-08-16T00:00:00+00:00", expect: "Started Sat, Aug 8" },
  { name: "Golfers To Win A Pga Tour Major In 2027", commence_time: "2028-01-14T15:00:00+00:00", resolution_date: "2028-01-14T15:00:00+00:00", expect: "Resolves Jan 14, 2028" },
  { name: "The Standard Portland Classic", commence_time: "2026-08-30T00:00:00+00:00", resolution_date: "2026-08-30T00:00:00+00:00", expect: "Starts Sun, Aug 30" },
  { name: "Indianapolis", commence_time: "2026-08-20T00:00:00+00:00", resolution_date: "2026-08-23T00:00:00+00:00", expect: "Starts Thu, Aug 20" },
  { name: "Aig Women S Open Womens", commence_time: "2026-08-02T18:58:17+00:00", resolution_date: "2026-08-16T00:00:00+00:00", expect: "Resolves Aug 16, 2026" },
  { name: "Golfers To Win A Pga Tour Major In 2026", commence_time: "2026-06-22T00:57:03+00:00", resolution_date: "2026-12-31T15:00:00+00:00", expect: "Resolves Dec 31, 2026" },
];

describe("UX-P050: every card on the landing page carries a timing line", () => {
  test.each(SLATE)("$name → $expect", ({ expect: label, ...data }) => {
    expect(render(card(data))).toContain(label);
  });

  test("no card claims a start it cannot stand behind", () => {
    // The specific regression: "Golfers To Win A PGA Tour Major In 2027" printed
    // "Starts Fri, Jan 14, 2028" — a resolution timestamp sold as a tee time.
    const html = render(
      card({
        name: "Golfers To Win A Pga Tour Major In 2027",
        commence_time: "2028-01-14T15:00:00+00:00",
        resolution_date: "2028-01-14T15:00:00+00:00",
      }),
    );
    expect(html).not.toContain("Starts Fri, Jan 14, 2028");
    expect(html).toContain("Resolves Jan 14, 2028");
  });

  test("a real start date is never joined by a resolution line", () => {
    const html = render(
      card({
        name: "Danish Golf Championship",
        commence_time: "2026-08-13T00:00:00+00:00",
        resolution_date: "2026-08-30T00:00:00+00:00",
      }),
    );
    expect(html).toContain("Starts Thu, Aug 13");
    expect(html).not.toContain("Resolves");
  });

  test("a settled marquee still leads with its champion, not a date", () => {
    const html = render(
      card({
        name: "The Open",
        commence_time: "2026-08-13T00:00:00+00:00",
        resolution_date: "2026-08-30T00:00:00+00:00",
        marquee_whathit: true,
      }),
    );
    expect(html).toContain("Champion");
    expect(html).not.toContain("Starts");
    expect(html).not.toContain("Resolves");
  });

  test("a card with neither a usable start nor a future resolution stays silent", () => {
    const html = render(
      card({
        commence_time: "2026-06-22T00:57:03+00:00", // stale
        resolution_date: "2026-08-01T00:00:00+00:00", // already passed
      }),
    );
    expect(html).not.toContain("Starts");
    expect(html).not.toContain("Started");
    expect(html).not.toContain("Resolves");
  });
});

describe("UX-P050: the title reads its acronyms", () => {
  test("'Pga' becomes 'PGA' — three of the eight landing cards carried it", () => {
    const html = render(card({ name: "Golfers To Win A Pga Tour Major In 2026" }));
    expect(html).toContain("Golfers To Win A PGA Tour Major In 2026");
    expect(html).not.toContain("Pga");
  });

  test("'Aig' becomes 'AIG'", () => {
    expect(render(card({ name: "Aig Women S Open Womens" }))).toContain("AIG Women S Open Womens");
  });

  test("an ordinary tournament name is left exactly as it arrived", () => {
    // The whole risk of a display-side caser is that it mangles the correct case.
    for (const name of [
      "Danish Golf Championship",
      "The Standard Portland Classic",
      "Indianapolis",
    ]) {
      expect(render(card({ name }))).toContain(name);
    }
  });

  test("the share text is repaired with the title, so the two cannot disagree", () => {
    const html = render(card({ name: "Golfers To Win A Pga Tour Major In 2026" }));
    expect(html).not.toContain("Pga");
  });
});
