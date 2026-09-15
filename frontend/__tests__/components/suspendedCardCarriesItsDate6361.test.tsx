// A SUSPENDED CARD MUST SAY WHEN — #6361 (live/262's photograph).
//
// live/262's specimen, at 390px on production: `/search?q=Lotte Giants` returned
// six "No result reported" cards with NO DATE on any of them, stacked between an
// "Aug 18 FINAL" and an "Aug 23 FINAL" that both carried one. Re-measured by
// ux/1274 before this file was written: 6 suspended cards / 6 undated, 12 finished
// cards / 0 undated — the asymmetry is total, on one page, in one card family.
//
// The harm is not the missing glyph, it is that the cards STOP BEING TELLABLE
// APART. Two of the six were the same fixture pair (Lotte Giants v KT Wiz),
// separable only by their probabilities. `distinguishable` below is that harm
// written as an assertion, and it is deliberately formula-free: it does not care
// what the date looks like, only that two fixtures played on different days do not
// render as the same card.
//
// ALL THREE CARD SURFACES, PER NOTICE 35. The issue names `components/EventCard`,
// but `FeedCard` and the Discover card gate their date on the finished state the
// same way (`isFinished ? … : null`, `isDone ? … : ""`), so pinning one component
// would leave the other two with the bug — this repo's recorded failure mode.
//
// DATE ONLY, NEVER A CLOCK — and that is why this does not simply reuse each
// card's finished label. `FeedCard`'s and the Discover card's finished arms use
// the "relative" style, which renders `Today 7:00 PM` for a same-day fixture. A
// time of day beside "No result reported" is the future-tense start time live/048
// refused on exactly this branch, so the suspended arm takes the "compact"
// (date-only) style on all three. `noClock` asserts it.
//
// RENDERED, NOT GREPPED (#2060) and BOTH DIRECTIONS (gotcha #43): every case that
// asserts a date APPEARS has a sibling asserting the finished and scheduled arms
// are unchanged, so a fix written one condition too wide cannot pass.

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
jest.mock("@/hooks", () => ({
  useAnalytics: () => ({ trackEventCardClick: () => {}, track: () => {} }),
}));

import EventCard from "@/components/EventCard";
import FeedCard from "@/components/FeedCard";
import { EventCard as DiscoverEventCard } from "@/components/discover/EventCard";
import type { Event, FeedEventData, FeedItem } from "@/lib/types";

// Offsets, not literals (gotcha #44): a hard-coded "Aug 18" starts carrying a year
// suffix the moment the calendar rolls into the next one. Both anchors are days,
// not hours, so neither can drift across a local midnight mid-run.
const DAY = 24 * 3600_000;
const PLAYED_28D_AGO = new Date(Date.now() - 28 * DAY).toISOString();
const PLAYED_20D_AGO = new Date(Date.now() - 20 * DAY).toISOString();
const STARTS_IN_3H = new Date(Date.now() + 3 * 3600_000).toISOString();

/** The day-of-month of an ISO instant, as the card's locale renders it. */
function dayOfMonth(iso: string): string {
  return String(new Date(iso).getDate());
}

function makeEvent(over: Partial<Event> = {}): Event {
  return {
    id: 15295047,
    external_id: "evt-15295047",
    sport: "baseball_kbo",
    sport_name: "KBO",
    home_team: "KT Wiz",
    away_team: "Lotte Giants",
    commence_time: PLAYED_28D_AGO,
    status: "suspended",
    home_score: null,
    away_score: null,
    home_team_data: { primary_color: "#2563eb", logo_small: "h.png" },
    away_team_data: { primary_color: "#64748b", logo_small: "a.png" },
    current_odds: {
      captured_at: PLAYED_28D_AGO,
      home_probability: 0.54,
      away_probability: 0.46,
      spread: null,
      over_under: null,
      projected_home_score: null,
      projected_away_score: null,
    },
    ...over,
  } as unknown as Event;
}

// Takes `Partial<Event>` because it delegates to `makeEvent`: the three cards
// want the same payload under two type names, and the overrides below are
// written once for all of them.
function makeData(over: Partial<Event> = {}): FeedEventData {
  return makeEvent(over) as unknown as FeedEventData;
}

function makeItem(data: FeedEventData): FeedItem {
  return { type: "event", score: 50, reason: "", headline: "", data } as unknown as FeedItem;
}

const RENDERERS: ReadonlyArray<{ name: string; render: (over?: Partial<Event>) => string }> = [
  {
    name: "the shared EventCard (search, rails, grids, My Stuff)",
    render: (over = {}) => renderToStaticMarkup(<EventCard event={makeEvent(over)} />),
  },
  {
    name: "FeedCard",
    render: (over = {}) =>
      renderToStaticMarkup(<FeedCard item={makeItem(makeData(over))} />),
  },
  {
    name: "the Discover EventCard",
    render: (over = {}) => {
      const data = makeData(over);
      return renderToStaticMarkup(
        <DiscoverEventCard
          item={makeItem(data)}
          data={data}
          liked={false}
          setLiked={() => {}}
          trending={false}
        />,
      );
    },
  },
];

/** Rendered text with entities decoded.
 *
 * `&amp;` is unescaped LAST — the ordering is load-bearing, not style (CodeQL
 * `js/double-escaping`, the class already fixed on the CERT-786/792 siblings):
 * unescaping the ampersand first turns a literal `&amp;#x27;` into an apostrophe,
 * one escape too many, so an assertion could pass on text the page never showed.
 */
function text(html: string): string {
  return html
    .replace(/<[^>]*>/g, " ")
    .replace(/&middot;|&#xB7;/g, "·")
    .replace(/&#x27;|&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ");
}

describe.each(RENDERERS)("$name: a suspended card carries its date", ({ render }) => {
  it("prints the day the fixture was played", () => {
    // The control for everything else here: if the card were not reaching the
    // suspended arm at all, the absence assertions below would pass for the
    // wrong reason. `No result reported` is that arm's own words.
    const rendered = text(render());
    expect(rendered).toContain("No result reported");
    expect(rendered).toContain(dayOfMonth(PLAYED_28D_AGO));
  });

  it("distinguishable: two fixtures played on different days do not render alike", () => {
    // THE REPORTED HARM, formula-free. Same teams, same absent scores, same
    // status — only the day differs. On production these two were adjacent and
    // a reader had no way to tell them apart. This case cannot be satisfied by
    // printing any constant, and it does not encode the date's format.
    const a = text(render({ commence_time: PLAYED_28D_AGO } as Partial<Event>));
    const b = text(render({ commence_time: PLAYED_20D_AGO } as Partial<Event>));
    expect(a).not.toEqual(b);
  });

  it("noClock: prints no time of day beside the unreported words", () => {
    // live/048's refusal, kept. A suspended match must not advertise a start
    // time, and the "relative" style these cards use for FINISHED fixtures
    // renders `Today 7:00 PM` on a same-day one. The suspended arm is date-only,
    // so no `7:00 PM`-shaped token may appear.
    const sameDay = new Date(Date.now() - 2 * 3600_000).toISOString();
    const rendered = text(render({ commence_time: sameDay } as Partial<Event>));
    expect(rendered).toContain("No result reported");
    expect(rendered).not.toMatch(/\d{1,2}:\d{2}\s?(AM|PM)/i);
  });

  it("fails closed on the impossible future fixture (gotcha #14)", () => {
    // A Kalshi close/resolution timestamp parked in `commence_time` makes a row
    // that has already stopped look like it starts tomorrow. The shared helper
    // returns "" for that, meaning "render no date" — a card that cannot date
    // itself honestly prints nothing rather than a future one. Asserted as the
    // absence of the future day number, with the suspended words still present
    // so this is not passing on an unrendered card.
    const future = new Date(Date.now() + 9 * DAY).toISOString();
    const rendered = text(render({ commence_time: future, status: "suspended" } as Partial<Event>));
    expect(rendered).toContain("No result reported");
    expect(rendered).not.toContain(`${dayOfMonth(future)},`);
  });

  it("control: a SCHEDULED card is unchanged", () => {
    // The arm a too-wide fix takes with it. An upcoming card must keep its
    // countdown/start treatment and must not gain a past-tense finished date.
    const rendered = text(
      render({ status: "scheduled", commence_time: STARTS_IN_3H } as Partial<Event>),
    );
    expect(rendered).not.toContain("No result reported");
  });

  it("control: a FINISHED card still dates itself", () => {
    // The sibling this fix is drawing its symmetry from. If it stopped printing
    // a date, the suspended assertions above would still pass and the product
    // would be worse.
    const rendered = text(
      render({
        status: "completed",
        home_score: 4,
        away_score: 2,
        commence_time: PLAYED_28D_AGO,
      } as Partial<Event>),
    );
    expect(rendered).toContain(dayOfMonth(PLAYED_28D_AGO));
  });
});
