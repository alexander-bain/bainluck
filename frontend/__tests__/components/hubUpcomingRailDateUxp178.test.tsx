/**
 * UX-P178 (#2167) — THE DATE ON A HUB CARD, AND WHAT IT IS CALLED.
 *
 * Two defects, one card, both live on production 2026-08-29:
 *
 *   1. `formatDate` called the formatter with no `timeZone`, so a midnight-UTC
 *      instant moved back a DAY for every reader west of Greenwich.
 *      `2026-09-13T00:00:00+00:00` reads "Sat, Sep 12" in Los Angeles and
 *      "Sun, Sep 13" in UTC. All 48 upcoming cards on all five hubs.
 *   2. The tennis rail served the winner market's `resolution_date` — an END —
 *      under the key `start_date`, so the card printed a bare future date that
 *      a reader takes to mean "when it starts".
 *
 * ── WHY THIS FILE STUBS THE AMBIENT ZONE INSTEAD OF SETTING process.env.TZ ───
 *
 * CI runs `TZ=UTC`. Under UTC the buggy unpinned call and the fixed pinned one
 * return the IDENTICAL string, so any guard that reads the runner's own zone is
 * vacuous in the one environment that gates the merge — it would go green
 * against the bug. (integrator/218 flagged exactly this: "a test that does not
 * pin a US timezone will pass against the bug".) Mutating `process.env.TZ` is
 * not a fix: ICU resolves the default zone once per process and jest shares a
 * process across files, so it is order-dependent.
 *
 * So the ambient default is substituted at the formatter instead, which is
 * deterministic under any TZ. `stubAmbientZone` makes every UNPINNED
 * `Intl.DateTimeFormat` resolve to Los Angeles while leaving a pinned one
 * alone — the pin overrides because it is spread last. The first test proves
 * the stub BITES before anything is concluded from it passing; without that
 * control a broken stub would make this whole file green against the bug it
 * exists to catch.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { HubUpcomingRail, formatDate } from "@/components/hub/HubUpcomingRail";
import type { HubUpcoming } from "@/lib/api";

/** Visible words, with markup and attributes stripped the way a reader sees it. */
function visibleText(markup: string): string {
  return markup
    .replace(/<[^>]*>/g, " ")
    .replace(/&[a-z]+;|&#x?[0-9a-f]+;/gi, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/** Midnight UTC — the shape every one of these dates actually has. */
const MIDNIGHT_UTC = "2026-09-13T00:00:00+00:00";
const IN_UTC = "Sun, Sep 13";
const IN_LOS_ANGELES = "Sat, Sep 12";

const RealDateTimeFormat = Intl.DateTimeFormat;

/**
 * Make an unpinned formatter resolve to Los Angeles, as a US reader's browser
 * does. A formatter that names its own `timeZone` is untouched.
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

function card(over: Partial<HubUpcoming> & { status: string }): HubUpcoming {
  return {
    key: "event:tennis:us-open",
    name: "2026 Women's US Open Winner (Tennis)",
    domain: "tennis",
    start_date: null,
    end_date: MIDNIGHT_UTC,
    is_major: false,
    ...over,
  } as HubUpcoming;
}

function renderRail(cards: HubUpcoming[]): string {
  return renderToStaticMarkup(
    <HubUpcomingRail cards={cards} label="Upcoming Tournaments" neutralLabel="Tournaments" />,
  );
}

afterEach(() => {
  jest.restoreAllMocks();
});

describe("the stub itself", () => {
  it("really does move the day, so a green result below means something", () => {
    // THE VACUITY CONTROL. This is the buggy call — no `timeZone` — and under
    // the stub it must read a day early. If this ever prints "Sun, Sep 13" the
    // stub has stopped biting and every other test in this file is worthless.
    const spy = stubAmbientZone();
    const unpinned = new Intl.DateTimeFormat("en-US", {
      weekday: "short",
      month: "short",
      day: "numeric",
    }).format(new Date(MIDNIGHT_UTC));
    expect(unpinned).toBe(IN_LOS_ANGELES);
    expect(spy).toHaveBeenCalled();
  });
});

describe("a hub card prints the date the data states, in every reader's zone", () => {
  it("does not slip a day for a reader west of Greenwich", () => {
    stubAmbientZone();
    expect(formatDate(MIDNIGHT_UTC)).toBe(IN_UTC);
  });

  it("reads the same under the runner's own zone", () => {
    // No stub: the pinned formatter is zone-invariant, so both environments
    // agree. Together with the test above this pins the whole disjunction —
    // a formatter pinned to the WRONG fixed zone fails one or the other.
    expect(formatDate(MIDNIGHT_UTC)).toBe(IN_UTC);
  });

  it("puts that date on the rendered card, not just through the helper", () => {
    stubAmbientZone();
    const text = visibleText(renderRail([card({ status: "unknown" })]));
    expect(text).toContain(IN_UTC);
    expect(text).not.toContain(IN_LOS_ANGELES);
  });

  it("still renders nothing for a card with no date at all", () => {
    expect(formatDate(null)).toBe("");
    expect(formatDate(undefined)).toBe("");
    expect(formatDate("not-a-date")).toBe("");
    const text = visibleText(
      renderRail([card({ status: "unknown", start_date: null, end_date: null })]),
    );
    expect(text).toContain("TBD");
  });
});

describe("an end date is labelled as one, and a start is not", () => {
  it("labels the tennis rail's date, because it is when the tournament ENDS", () => {
    const text = visibleText(renderRail([card({ status: "unknown" })]));
    expect(text).toContain(`Ends ${IN_UTC}`);
  });

  it("prints a real start bare, because a bare date reads as a start", () => {
    // The control (gotcha #43, both directions): a fix that labelled every date
    // "Ends" would pass the test above and mislabel every golf and combat card.
    const text = visibleText(
      renderRail([
        card({ status: "upcoming", start_date: MIDNIGHT_UTC, end_date: null, domain: "golf" }),
      ]),
    );
    expect(text).toContain(IN_UTC);
    expect(text).not.toContain("Ends");
  });

  it("prefers the start during the split-deploy window", () => {
    /**
     * Vercel deploys ahead of Heroku, so for that window this build reads a
     * payload whose backend still serves the value under `start_date`. The
     * start arm is tried first precisely so that window degrades to TODAY's
     * behaviour — a bare date — rather than to a blank card or a doubled one.
     */
    const text = visibleText(
      renderRail([card({ status: "unknown", start_date: MIDNIGHT_UTC, end_date: MIDNIGHT_UTC })]),
    );
    expect(text).toContain(IN_UTC);
    expect(text).not.toContain("Ends");
  });
});

describe("a Grand Slam can say it is one", () => {
  it("renders the marquee chip when the payload declares a major", () => {
    const text = visibleText(renderRail([card({ status: "unknown", is_major: true })]));
    expect(text).toContain("Marquee");
  });

  it("and withholds it otherwise", () => {
    const text = visibleText(renderRail([card({ status: "unknown", is_major: false })]));
    expect(text).not.toContain("Marquee");
  });
});
