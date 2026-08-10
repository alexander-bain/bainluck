// UX-P045 — a finished game on the Discover feed must say WHEN it finished, and
// must describe itself in the past tense.
//
// MEASURED ON PRODUCTION 2026-08-10 07:04 PT: the Discover feed's event slot was
// 15 of 15 finished games, 14 of them over 12 hours old. Every one rendered the
// bare word "Final" with no date, and five were captioned "Line moving" — present
// progressive — over a game that had ended 13-19 hours earlier, while the wire
// carried the correct past-tense sentence in `reason` and the card threw it away.
//
// Guards run BOTH directions per gotcha #43: the settled card gains a date and an
// honest caption, AND the unsettled card is asserted unchanged.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { FeedItem, FeedEventData } from "@/lib/types";

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), prefetch: jest.fn() }),
}));

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

jest.mock("next/image", () => ({
  __esModule: true,
  default: ({ alt }: { alt: string }) => <img alt={alt} />,
}));

import { EventCard } from "../../components/discover/EventCard";
import { feedContextSnippet } from "../../components/discover/utils";

const NOW = Date.parse("2026-08-10T14:00:00Z");

/** The real production shape of a settled Discover event card. */
function settledItem(overrides: Partial<FeedItem> = {}, dataOverrides: Partial<FeedEventData> = {}): FeedItem {
  return {
    type: "event",
    headline: "Line moving",
    reason: "San Diego Padres odds shifted 49% during the game",
    context_summary: null,
    score: 50,
    data: {
      id: 15191038,
      status: "completed",
      commence_time: "2026-08-09T20:10:00Z",
      away_team: "Houston Astros",
      home_team: "San Diego Padres",
      away_score: 2,
      home_score: 5,
      sport: "baseball_mlb",
      ...dataOverrides,
    } as unknown as FeedEventData,
    ...overrides,
  } as unknown as FeedItem;
}

function render(item: FeedItem) {
  return renderToStaticMarkup(
    <EventCard
      item={item}
      data={item.data as FeedEventData}
      liked={false}
      setLiked={() => {}}
      trending={false}
    />,
  );
}

describe("a settled Discover card says when the game finished", () => {
  beforeAll(() => jest.useFakeTimers().setSystemTime(NOW));
  afterAll(() => jest.useRealTimers());

  test("yesterday's final carries a readable date, not just the word Final", () => {
    const html = render(settledItem());
    expect(html).toContain("Yesterday 8:10 PM");
    expect(html).toContain('data-testid="event-card-finished-at"');
  });

  test("the date renders even when the scores never arrived", () => {
    // The old markup nested the settled treatment inside a decisive-score check,
    // so a scoreless or drawn settled card showed nothing but the crest label.
    const html = render(settledItem({}, { away_score: null, home_score: null } as Partial<FeedEventData>));
    expect(html).toContain("Yesterday 8:10 PM");
    expect(html).toContain("Final");
  });

  test("the date renders on a draw", () => {
    const html = render(settledItem({}, { away_score: 1, home_score: 1 } as Partial<FeedEventData>));
    expect(html).toContain("Yesterday 8:10 PM");
    // No winner is claimed on a draw.
    expect(html).not.toContain(" won");
  });

  test("a decisive result still names the winner", () => {
    const html = render(settledItem());
    expect(html).toContain("Padres won");
  });

  test("an impossible future-dated FINAL shows no date at all (gotcha #14)", () => {
    // commence_time can hold a Kalshi close/resolution timestamp. A future date
    // beside a Final badge is an impossible state — render nothing instead.
    const html = render(settledItem({}, { commence_time: "2026-08-12T18:00:00Z" } as Partial<FeedEventData>));
    expect(html).not.toContain('data-testid="event-card-finished-at"');
    expect(html).toContain("Final");
  });

  test("BOTH DIRECTIONS — an unsettled card gains no finished-at date", () => {
    const html = render(
      settledItem({}, { status: "scheduled", commence_time: "2026-08-10T23:07:00Z" } as Partial<FeedEventData>),
    );
    expect(html).not.toContain('data-testid="event-card-finished-at"');
    expect(html).not.toContain("Yesterday");
  });
});

describe("a settled card stops narrating itself in the present tense", () => {
  test("the past-tense reason wins over the live-tensed bucket headline", () => {
    // "Line moving" over a game that ended 18 hours ago was the measured defect.
    expect(feedContextSnippet(settledItem())).toBe(
      "San Diego Padres odds shifted 49% during the game",
    );
  });

  test("the card renders that sentence, not the bucket label", () => {
    jest.useFakeTimers().setSystemTime(NOW);
    const html = render(settledItem());
    expect(html).toContain("odds shifted 49% during the game");
    expect(html).not.toContain("Line moving");
    jest.useRealTimers();
  });

  test("a settled card with no reason still carries a caption (never blank)", () => {
    // Suppression was sized before it was chosen: falling back to the headline
    // means no settled card loses its caption.
    expect(feedContextSnippet(settledItem({ reason: "" }))).toBe("Line moving");
  });

  test("context_summary still outranks both when the backend sends one", () => {
    expect(feedContextSnippet(settledItem({ context_summary: "A curated line." }))).toBe(
      "A curated line.",
    );
  });

  test("BOTH DIRECTIONS — an UNSETTLED card keeps preferring headline", () => {
    const upcoming = settledItem({}, { status: "scheduled" } as Partial<FeedEventData>);
    expect(feedContextSnippet(upcoming)).toBe("Line moving");
  });

  test("BOTH DIRECTIONS — futures cards are untouched", () => {
    const futures = {
      type: "futures",
      headline: "Line moving",
      reason: "some reason",
      context_summary: null,
      data: {},
    } as unknown as FeedItem;
    expect(feedContextSnippet(futures)).toBe("Line moving");
  });

  test("a 'closed' event counts as settled, same as 'completed'", () => {
    const closed = settledItem({}, { status: "closed" } as Partial<FeedEventData>);
    expect(feedContextSnippet(closed)).toBe(
      "San Diego Padres odds shifted 49% during the game",
    );
  });
});
