/**
 * #10161 — a concept card's "Today / Tomorrow / This week" pill is counted on the
 * READER's calendar, not the server's UTC one.
 *
 * Specimen, `/sports` at 390px, Thu 10/1 9:05 PM PT (04:05Z Fri 10/2):
 *
 *     Today · MMA     Mohammad Fahmi vs Ahmed El Sisy … Fri, Oct 2
 *     (four cards down, the same bout)  MMA          Tomorrow 8:00 AM
 *     Marquee · Tomorrow · UFC 332: Silva vs Cong … Sat, Oct 3
 *
 * Served: `event:ufc:26oct02` headline "Today", start_date 2026-10-02T15:00Z;
 * `event:ufc:26oct03` headline "Tomorrow", start_date 2026-10-03T20:00Z.
 *
 * Part 1 runs the helper with the reader's zone pinned to Pacific, because jest
 * pins TZ=UTC and in UTC the server's and the reader's calendars agree, so the
 * defect can't be seen there. Part 2 renders the card to prove the pill reads the
 * helper and not `item.headline`. Its case is chosen so the served word is wrong
 * even in UTC, so a reverted render fails here too.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

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

import FeedCard from "@/components/FeedCard";
import { conceptCountdownHeadline } from "@/lib/eventConceptDisplay";
import type { FeedItem } from "@/lib/types";

const PT = "America/Los_Angeles";
const SPECIMEN_NOW = new Date("2026-10-02T04:05:00Z"); // Thu 10/1 9:05 PM PT

describe("#10161 part 1 — the pill counts days on the reader's calendar", () => {
  it("Fahmi–El Sisy (Fri 8 AM PT) reads Tomorrow for a Pacific reader on Thursday night, not Today", () => {
    expect(conceptCountdownHeadline("Today", "2026-10-02T15:00:00+00:00", SPECIMEN_NOW, PT)).toBe(
      "Tomorrow",
    );
  });

  it("UFC 332 (opens Sat 1 PM PT) reads This week on Thursday night, not Tomorrow", () => {
    expect(
      conceptCountdownHeadline("Tomorrow", "2026-10-03T20:00:00+00:00", SPECIMEN_NOW, PT),
    ).toBe("This week");
  });

  it("CONTROL: in UTC the same instants keep the server's words — only the calendar moved", () => {
    expect(conceptCountdownHeadline("Today", "2026-10-02T15:00:00+00:00", SPECIMEN_NOW, "UTC")).toBe(
      "Today",
    );
    expect(
      conceptCountdownHeadline("Tomorrow", "2026-10-03T20:00:00+00:00", SPECIMEN_NOW, "UTC"),
    ).toBe("Tomorrow");
  });

  it("the morning after, the Pacific reader's Fahmi card says Today", () => {
    expect(
      conceptCountdownHeadline(
        "Today",
        "2026-10-02T15:00:00+00:00",
        new Date("2026-10-02T13:00:00Z"),
        PT,
      ),
    ).toBe("Today");
  });

  it("same thresholds as the server: 7 days is This week, 8 is no pill", () => {
    const now = new Date("2026-10-01T12:00:00Z");
    expect(conceptCountdownHeadline("This week", "2026-10-08T18:00:00Z", now, PT)).toBe("This week");
    expect(conceptCountdownHeadline("This week", "2026-10-09T18:00:00Z", now, PT)).toBeNull();
  });

  it("a DST day still counts as one day", () => {
    // US clocks fall back on Sun 2026-11-01; Sat 9 PM PT -> Sun 9 PM PT is 25h.
    expect(
      conceptCountdownHeadline(
        "This week",
        "2026-11-02T05:00:00Z",
        new Date("2026-11-01T04:00:00Z"),
        PT,
      ),
    ).toBe("Tomorrow");
  });

  it.each([
    ["Live", "2026-10-02T15:00:00Z"],
    [null, "2026-10-02T15:00:00Z"],
    ["Today", null],
    ["Today", "not a date"],
  ])("keeps the server's value when there is nothing to re-count (%p, %p)", (headline, start) => {
    expect(conceptCountdownHeadline(headline, start, SPECIMEN_NOW, PT)).toBe(headline);
  });
});

function concept(headline: string | null, start_date: string): FeedItem {
  return {
    type: "concept",
    score: 80,
    reason: "14 fights on the card",
    headline,
    data: {
      key: "event:ufc:26oct03",
      name: "UFC 332: Silva vs Cong",
      domain: "ufc",
      status: "upcoming",
      start_date,
      is_major: true,
      fight_count: 14,
      headline_bout: {
        competitors: [
          { name: "Natalia Silva", probability: 0.66 },
          { name: "Wang Cong", probability: 0.34 },
        ],
        commence_time: "2026-10-04T06:20:00+00:00",
      },
    },
  } as unknown as FeedItem;
}

describe("#10161 part 2 — the rendered pill is the reader's count", () => {
  beforeEach(() => {
    jest.useFakeTimers().setSystemTime(new Date("2026-10-01T12:00:00Z"));
  });
  afterEach(() => {
    jest.useRealTimers();
  });

  function pill(html: string): string | null {
    const m = html.match(/data-testid="concept-countdown-pill"[^>]*>([^<]*)</);
    return m ? m[1] : null;
  }

  it("prints This week, not the served Today, for a card two days out", () => {
    const html = renderToStaticMarkup(<FeedCard item={concept("Today", "2026-10-03T20:00:00+00:00")} />);
    expect(html).toContain("UFC 332: Silva vs Cong");
    expect(pill(html)).toBe("This week");
  });

  it("prints no pill when the card is more than a week out, whatever was served", () => {
    const html = renderToStaticMarkup(<FeedCard item={concept("Tomorrow", "2026-10-20T20:00:00+00:00")} />);
    expect(html).toContain("UFC 332: Silva vs Cong");
    expect(pill(html)).toBeNull();
  });

  it("CONTROL: a served word that is already right renders unchanged", () => {
    const html = renderToStaticMarkup(<FeedCard item={concept("Tomorrow", "2026-10-02T20:00:00+00:00")} />);
    expect(pill(html)).toBe("Tomorrow");
  });
});
