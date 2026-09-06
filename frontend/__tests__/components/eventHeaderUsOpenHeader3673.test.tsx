/**
 * #3673 — the concept header stops making two false claims about a tournament
 * that is being played.
 *
 * Shot on production Sun 2026-09-06, mid-US-Open, with matches live on court:
 *
 *     TENNIS   [ UPCOMING ]   [ MAJOR ]
 *     US Open Men's Singles Winner
 *     Sep 27  ·  2056 markets tracked
 *
 * The men's final was Sep 13. "Sep 27" is Kalshi's contract expiration backstop
 * (`2026-09-28 02:00Z`) rendered in the reader's zone, and "UPCOMING" is what a
 * `default:` arm answers when it is handed a state it does not recognise.
 * `/hub/tennis` printed "Ends Sun, Sep 13" for the same tournament in the same
 * session, one click away.
 *
 * THE HEADER IS RENDERED, not the helpers called: the claim under test is the
 * one a reader actually sees, and two of the three defects here are only
 * visible in composition (a chip that must vanish, a date whose day moves).
 *
 * ⚠️ THE ZONE STUB, AND WHY THE FIRST TEST IS A CONTROL. CI runs `TZ=UTC`,
 * where the unpinned call and the pinned one produce the SAME string — a guard
 * that trusts the runner's zone is vacuous exactly where it runs. Mutating
 * `process.env.TZ` does not help either: ICU resolves the default zone once per
 * process and jest shares a process across files, so it is order-dependent. So
 * the ambient default is substituted at the formatter, and the first test
 * proves the substitution BITES before anything is concluded from the rest
 * passing. Technique lifted from `hubUpcomingRailDateUxp178.test.tsx`, which
 * fixed this same defect on the rail.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import EventHeader from "@/components/event/EventHeader";
import type { EventConceptResponse } from "@/lib/types";

/** Visible words, with markup and entities stripped the way a reader sees it. */
function visibleText(markup: string): string {
  return markup
    .replace(/<[^>]*>/g, " ")
    .replace(/&[a-z]+;|&#x?[0-9a-f]+;/gi, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/** The day of the men's final, in the shape the payload actually carries. */
const FINAL_DAY_UTC = "2026-09-13T00:00:00+00:00";
/** Kalshi's expiration backstop for the same market — fifteen days later. */
const KALSHI_BACKSTOP_UTC = "2026-09-28T02:00:00+00:00";

const RealDateTimeFormat = Intl.DateTimeFormat;

/**
 * Make an unpinned formatter resolve to Los Angeles, as a US reader's browser
 * does. A formatter that names its own `timeZone` is untouched, because the
 * pin is spread last.
 */
function stubAmbientZone(): jest.SpyInstance {
  return jest
    .spyOn(Intl, "DateTimeFormat")
    .mockImplementation(
      ((locale?: string, opts?: Intl.DateTimeFormatOptions) =>
        new RealDateTimeFormat(locale ?? "en-US", {
          timeZone: "America/Los_Angeles",
          ...opts,
        })) as unknown as typeof Intl.DateTimeFormat,
    );
}

type ConceptEvent = EventConceptResponse["event"];

function usOpenHeader(over: Partial<ConceptEvent> = {}): string {
  const event = {
    key: "event:tennis:us-open-men-s-singles-winner",
    domain: "tennis",
    name: "US Open Men's Singles Winner",
    status: "live",
    // Tennis has no tournament start to give — the adapter sets this null by
    // construction, which is why the header's only date is an end date.
    start_date: null,
    end_date: FINAL_DAY_UTC,
    venue: null,
    location: null,
    is_major: true,
    ...over,
  } as ConceptEvent;
  return renderToStaticMarkup(
    <EventHeader
      event={event}
      marketsTracked={2056}
      nav={[]}
      fallbackName="US Open"
    />,
  );
}

afterEach(() => {
  jest.restoreAllMocks();
});

describe("#3673 the US Open header, mid-tournament", () => {
  test("CONTROL: the zone stub bites — an unpinned formatter reads a day early", () => {
    const spy = stubAmbientZone();
    const unpinned = new Intl.DateTimeFormat("en-US", {
      month: "short",
      day: "numeric",
    }).format(new Date(FINAL_DAY_UTC));
    spy.mockRestore();
    // Without this, every assertion below would pass against the bug.
    expect(unpinned).toBe("Sep 12");
  });

  test("prints the tournament's own day, not the reader's — and says it is an end", () => {
    stubAmbientZone();
    const text = visibleText(usOpenHeader());
    // The rail says "Ends Sun, Sep 13" for this tournament at this moment.
    // Same day, or the two surfaces contradict each other one click apart.
    expect(text).toContain("Ends Sep 13");
    expect(text).not.toContain("Sep 12");
  });

  test("does not call an in-progress Grand Slam UPCOMING", () => {
    stubAmbientZone();
    const text = visibleText(usOpenHeader({ status: "live" }));
    expect(text).toContain("Live");
    expect(text).not.toMatch(/Upcoming/i);
  });

  test("a state we cannot read prints no phase at all, and loses nothing else", () => {
    stubAmbientZone();
    // `unknown` is what `tennis_status` emits with no start signal (UX-P209 /
    // CERT-519). It is outside the payload's TS union deliberately — the cast
    // is the point: this guards the `default:` arm, which is reachable by any
    // string the backend can send, union or not.
    const text = visibleText(
      usOpenHeader({ status: "unknown" as ConceptEvent["status"] }),
    );
    expect(text).not.toMatch(/Upcoming|Live|Settled/i);
    // The apostrophe arrives HTML-escaped, and `visibleText` renders entities
    // as the space a reader sees between the words.
    expect(text).toMatch(/US Open Men.s Singles Winner/);
    expect(text).toContain("Ends Sep 13");
    expect(text).toContain("2056 markets tracked");
  });

  // The other direction (gotcha #43): the repair must not eat the true claims.
  test("a genuinely forthcoming tournament still says Upcoming", () => {
    stubAmbientZone();
    const text = visibleText(
      usOpenHeader({ status: "upcoming", end_date: KALSHI_BACKSTOP_UTC }),
    );
    expect(text).toContain("Upcoming");
  });

  test("a finished tournament still says Settled", () => {
    stubAmbientZone();
    const text = visibleText(usOpenHeader({ status: "settled" }));
    expect(text).toContain("Settled");
    expect(text).not.toMatch(/Upcoming/i);
  });

  test("a real range still prints bare, with no 'Ends' prefix", () => {
    stubAmbientZone();
    const text = visibleText(
      usOpenHeader({
        domain: "golf",
        name: "The Open",
        start_date: "2026-07-16T00:00:00+00:00",
        end_date: "2026-07-19T00:00:00+00:00",
      }),
    );
    expect(text).toContain("Jul 16");
    expect(text).toContain("Jul 19");
    expect(text).not.toContain("Ends");
  });
});
