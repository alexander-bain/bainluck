/**
 * #8954 — AN UPCOMING GAME IN THE RELATED RAIL SAYS WHEN.
 *
 * Production 2026-09-26 3:20 PM PT, 390px, `/events/15315847` (Wake Forest @
 * Louisville, Final): the MORE NCAAF rail dealt `Oregon Ducks @ USC Trojans`
 * 63% / 37% with no day and no time. It kicked off an hour later. The live card
 * above it had its dot and score and a finished card has FINAL (#5558), but a
 * scheduled card printed nothing, and "63%" read the same an hour out as a month out.
 *
 * The rail now prints the Discover card's start line (`formatScheduledGameLabel`,
 * moved unchanged out of `FeedCard`). A start the venue has not announced
 * (`start_is_tbd`, #8841, now served on the feed) prints its day and "TBD" and
 * never the placeholder hour, on BOTH feed cards.
 *
 * ## Fixture
 *
 * `ux1493_related_football_finished_5558` — PRODUCTION BYTES, unedited:
 * `GET /api/feed?limit=80&tags=["sport:football"]`, 2026-09-25 18:53Z. Item 3 is
 * the specimen itself, `Oregon Ducks @ USC Trojans` (14870010), `scheduled`,
 * `commence_time 2026-09-26T23:30Z`. The TBD and past-start arms derive from
 * that row by changing only the fields they name.
 *
 * Assertions test the PRESENCE OR ABSENCE OF A CLOCK, never a particular hour,
 * so they hold in every timezone (the #3829 / #8841 rule). Every TBD arm has a
 * control on the same row that DOES print a clock.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import FOOTBALL from "../fixtures/ux1493_related_football_finished_5558.20260925.json";

let swrPayload: unknown;

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({ data: swrPayload, error: undefined, isLoading: false }),
}));
jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({ track: () => {} }),
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
const RelatedByTag = require("@/components/RelatedByTag").default;
// eslint-disable-next-line @typescript-eslint/no-var-requires
const FeedCard = require("@/components/FeedCard").default;
import { formatScheduledGameLabel } from "@/lib/gameTimeLabel";

type Item = { type: string; data: Record<string, unknown> };
type Payload = { items: Item[] };

const football = FOOTBALL as unknown as Payload;
const SPECIMEN_ID = 14870010;
const specimenItem = football.items.find(
  (item) => item.type === "event" && item.data.id === SPECIMEN_ID,
)!;
const finishedItem = football.items.find(
  (item) => item.type === "event" && item.data.status === "completed",
)!;
/** One hour before the specimen's kickoff, as it was when the rail was photographed. */
const ONE_HOUR_BEFORE = Date.parse(specimenItem.data.commence_time as string) - 3_600_000;

/** Any "H:MM" — the clock a TBD start must not show. */
const CLOCK = /\b\d{1,2}:\d{2}\b/;

function withRow(item: Item, patch: Record<string, unknown>): Item {
  return { ...item, data: { ...item.data, ...patch } };
}

function renderRail(items: Item[]): string {
  swrPayload = { items };
  return renderToStaticMarkup(
    React.createElement(RelatedByTag as React.FC, {
      tags: ["sport:x"],
      limit: items.length,
      title: "More",
    } as never),
  );
}

function eventCard(html: string, id: unknown): string {
  const start = html.search(new RegExp(`<a [^>]*href="/events/${id}"`));
  if (start < 0) throw new Error(`no card for event ${id}`);
  return html.slice(start, html.indexOf("</a>", start) + 4);
}

function startLines(card: string): string[] {
  const out: string[] = [];
  const re = /<span[^>]*data-testid="related-card-start"[^>]*>([^<]*)<\/span>/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(card))) out.push(m[1]);
  return out;
}

beforeEach(() => {
  jest.useFakeTimers({ now: ONE_HOUR_BEFORE });
});
afterEach(() => {
  jest.useRealTimers();
});

describe("#8954 the rail's scheduled card prints its start", () => {
  it("the specimen reads 'Today <clock>', the Discover card's own wording", () => {
    const card = eventCard(renderRail([specimenItem]), SPECIMEN_ID);
    const lines = startLines(card);
    expect(lines).toHaveLength(1);
    expect(lines[0]).toMatch(/^Today /);
    expect(lines[0]).toMatch(CLOCK);
    expect(lines[0]).toBe(
      formatScheduledGameLabel(specimenItem.data.commence_time as string, ONE_HOUR_BEFORE),
    );
    // The price line is untouched (#5558 ARM 4's rule).
    expect(card).toMatch(/Oregon Ducks[\s\S]*\d+%[\s\S]*USC Trojans[\s\S]*\d+%/);
  });

  it("an unannounced start prints its day and TBD, and no clock", () => {
    const card = eventCard(
      renderRail([withRow(specimenItem, { start_is_tbd: true })]),
      SPECIMEN_ID,
    );
    const lines = startLines(card);
    expect(lines).toHaveLength(1);
    expect(lines[0]).toMatch(/· TBD$/);
    expect(lines[0]).not.toMatch(CLOCK);
  });

  it("a start already past on a card still marked scheduled prints nothing", () => {
    const past = withRow(specimenItem, {
      commence_time: new Date(ONE_HOUR_BEFORE - 600_000).toISOString(),
    });
    expect(startLines(eventCard(renderRail([past]), SPECIMEN_ID))).toHaveLength(0);
  });

  it("live and finished cards carry no start line", () => {
    const live = withRow(specimenItem, { status: "live", home_score: 7, away_score: 3 });
    expect(startLines(eventCard(renderRail([live]), SPECIMEN_ID))).toHaveLength(0);
    expect(
      startLines(eventCard(renderRail([finishedItem]), finishedItem.data.id)),
    ).toHaveLength(0);
  });
});

describe("#8954 the Discover card honours the feed's start_is_tbd", () => {
  function feedCardText(item: Item): string {
    return renderToStaticMarkup(React.createElement(FeedCard, { item: { ...item, score: 50, reason: "" } }))
      .replace(/<[^>]+>/g, " ")
      .replace(/\s+/g, " ");
  }

  it("control: an announced start prints its clock", () => {
    const text = feedCardText(specimenItem);
    expect(text).toContain(
      formatScheduledGameLabel(specimenItem.data.commence_time as string, ONE_HOUR_BEFORE),
    );
  });

  it("a TBD start prints 'Today · TBD' and not the placeholder hour", () => {
    const text = feedCardText(withRow(specimenItem, { start_is_tbd: true }));
    expect(text).toContain("Today · TBD");
    expect(text).not.toContain(
      formatScheduledGameLabel(specimenItem.data.commence_time as string, ONE_HOUR_BEFORE),
    );
  });
});

describe("#8954 formatScheduledGameLabel — the body moved out of FeedCard", () => {
  const base = Date.parse("2026-09-26T12:00:00"); // local noon, so +1h stays today everywhere
  it("today / tomorrow / weekday / date", () => {
    expect(formatScheduledGameLabel(new Date(base + 3_600_000).toISOString(), base)).toMatch(
      /^Today /,
    );
    expect(formatScheduledGameLabel(new Date(base + 24 * 3_600_000).toISOString(), base)).toMatch(
      /^Tomorrow /,
    );
    expect(
      formatScheduledGameLabel(new Date(base + 3 * 24 * 3_600_000).toISOString(), base),
    ).toMatch(/^[A-Z][a-z]{2} \d{1,2}:\d{2}/);
    expect(
      formatScheduledGameLabel(new Date(base + 10 * 24 * 3_600_000).toISOString(), base),
    ).toMatch(/^[A-Z][a-z]{2} \d{1,2} \d{1,2}:\d{2}/);
  });

  it("past, absent and unparseable starts print nothing", () => {
    expect(formatScheduledGameLabel(new Date(base - 60_000).toISOString(), base)).toBe("");
    expect(formatScheduledGameLabel(null, base)).toBe("");
    expect(formatScheduledGameLabel("not a date", base)).toBe("");
  });
});
