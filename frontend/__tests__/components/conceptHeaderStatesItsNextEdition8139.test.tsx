/**
 * #8139 concept-page half — a standing competition states WHEN it is.
 *
 * Shot on production `83a20bc7`, 2026-09-23 03:42Z, at 390px:
 *
 *     GOLF   [ UPCOMING ]
 *     Ryder Cup
 *     3 markets tracked
 *
 * No date anywhere. The cup is two years out and the page cannot say so; only
 * the prop titles ("U.S. Team Captain at 2027 Ryder Cup") hint at it.
 *
 * THE DATE WAS IN THE PAYLOAD THE WHOLE TIME, one field over — verified against
 * production the same night:
 *
 *     GET /api/event/event:golf:ryder-cup
 *       event.status             : "upcoming"
 *       event.start_date         : null          <- why the header printed nothing
 *       competition.next_edition : { start: "2027-09-17", end: "2027-09-19" }
 *
 * It used to reach the screen through the NEXT EDITION strip, which is a
 * *concluded-event* affordance: it was only ever mounted because the page
 * wrongly believed the cup had finished. live/524's #8141 correctly flipped the
 * badge settled→upcoming, the strip retired with it, and the page's only date
 * went with the strip. So this is not a regression of #8141 — it is a hole
 * #8141 uncovered, and the fix is the header reading the field directly.
 *
 * ⚠️ THE YEAR IS THE WHOLE SHIP, WHICH IS WHY TEST 2 IS HERE. The header's own
 * date helper, `eventDateRange`, prints NO year — routing the edition window
 * through it yields "Sep 17 – Sep 19", which a reader in September 2026 reads
 * as *this week*, for a cup two years away. That is a worse lie than the blank
 * this replaces, and it is the obvious implementation. live/523 refused to ship
 * #8139's backend half alone for exactly that reason and live/524 re-flagged it
 * when handing this surface over; test 2 is the line that fails if anyone ever
 * "simplifies" the two formatters into one.
 *
 * THE HEADER IS RENDERED, not the helper called (the #3673 rig's discipline, one
 * file over): the claim under test is the one a reader sees.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import EventHeader from "@/components/event/EventHeader";
import NextEditionStrip from "@/components/event/NextEditionStrip";
import { conceptHeaderDate } from "@/lib/eventConceptDisplay";
import type { EventConceptResponse } from "@/lib/types";

/** Visible words, with markup and entities stripped the way a reader sees it. */
function visibleText(markup: string): string {
  return markup
    .replace(/<[^>]*>/g, " ")
    .replace(/&[a-z]+;|&#x?[0-9a-f]+;/gi, " ")
    .replace(/\s+/g, " ")
    .trim();
}

type ConceptEvent = EventConceptResponse["event"];

/** The 2027 cup, exactly as `competition.next_edition` serves it. */
const RYDER_2027 = {
  name: "Ryder Cup 2027",
  slug: "ryder-cup-2027",
  concept_key: "event:golf:ryder-cup-2027",
  start: "2027-09-17",
  end: "2027-09-19",
};

function ryderCupHeader(
  over: Partial<ConceptEvent> = {},
  nextEdition: typeof RYDER_2027 | null = RYDER_2027,
): string {
  const event = {
    key: "event:golf:ryder-cup",
    domain: "golf",
    name: "Ryder Cup",
    status: "upcoming",
    // The defect's precondition, and it is structural: a STANDING concept is the
    // competition, not an edition of it, so it has no window of its own to give.
    start_date: null,
    end_date: null,
    venue: null,
    location: null,
    is_major: false,
    ...over,
  } as ConceptEvent;
  return renderToStaticMarkup(
    <EventHeader
      event={event}
      marketsTracked={3}
      nav={[]}
      fallbackName="Ryder Cup"
      nextEdition={nextEdition}
    />,
  );
}

describe("#8139 the Ryder Cup header states when the cup is", () => {
  test("THE SHIP: an upcoming standing competition prints its next edition's window", () => {
    const text = visibleText(ryderCupHeader());
    expect(text).toContain("September 17–19, 2027");
    // The rest of the header is untouched by the new date.
    expect(text).toContain("Ryder Cup");
    expect(text).toContain("Upcoming");
    expect(text).toContain("3 markets tracked");
  });

  test("THE YEAR IS LOAD-BEARING: never the yearless 'Sep 17 – Sep 19' grammar", () => {
    const text = visibleText(ryderCupHeader());
    // `eventDateRange`'s shape. Its presence would mean the edition window was
    // routed through the header's in-season formatter, printing a 2027 date as
    // if it were this September.
    expect(text).not.toMatch(/Sep 17\s*–\s*Sep 19/);
    expect(text).not.toMatch(/\bSep 17\b/);
    // Belt and braces: whatever grammar is used, the year has to be on screen.
    expect(text).toContain("2027");
  });

  test("an event with its OWN window is unchanged — the edition never overrides it", () => {
    // The Open: a real edition with real dates, whose competition also declares a
    // next edition. A fallback that fired here would replace the tournament a
    // reader is looking at with one two years out.
    const text = visibleText(
      ryderCupHeader({
        name: "The Open",
        start_date: "2026-07-16T00:00:00+00:00",
        end_date: "2026-07-19T00:00:00+00:00",
      }),
    );
    expect(text).toContain("Jul 16");
    expect(text).toContain("Jul 19");
    expect(text).not.toContain("2027");
  });

  test("a LIVE competition does not advertise a future edition as its date", () => {
    // A future window beside a LIVE chip contradicts it: the reader is watching
    // this one now.
    const text = visibleText(ryderCupHeader({ status: "live" }));
    expect(text).toContain("Live");
    expect(text).not.toContain("2027");
  });

  test("a SETTLED competition leaves the sentence to the strip — stated once, not twice", () => {
    const text = visibleText(ryderCupHeader({ status: "settled" }));
    expect(text).toContain("Settled");
    expect(text).not.toContain("2027");
  });

  // The other direction (gotcha #43): suppressing the header's copy must not
  // lose the fact. The settled page still says it, in the strip's own grammar.
  test("...and the settled page still says it, in the strip", () => {
    const text = visibleText(
      renderToStaticMarkup(
        <NextEditionStrip
          competition={{
            slug: "ryder-cup",
            name: "Ryder Cup",
            domain: "golf",
            next_edition: RYDER_2027,
            last_edition: null,
          }}
          settled
        />,
      ),
    );
    expect(text).toContain("Ryder Cup returns September 17–19, 2027");
  });

  test("honest-empty: no window and no declared edition prints no date, and no debris", () => {
    const text = visibleText(ryderCupHeader({}, null));
    expect(text).toContain("Ryder Cup");
    // Ruling 027 / notice 34: the space is left empty, never explained.
    expect(text).not.toMatch(/undefined|NaN|null|Invalid Date/);
    expect(text).not.toMatch(/\b20\d\d\b/);
  });
});

describe("#8139 conceptHeaderDate, the rule underneath", () => {
  const EDITION = { start: "2027-09-17", end: "2027-09-19" };

  test("falls back to the edition only when there is no own window", () => {
    expect(conceptHeaderDate("upcoming", null, null, EDITION)).toBe(
      "September 17–19, 2027",
    );
    expect(
      conceptHeaderDate("upcoming", "2026-07-16T00:00:00+00:00", null, EDITION),
    ).toBe("Jul 16");
  });

  test("an end-only own window still wins, and still says it is an end", () => {
    // Tennis: `start_date` null by construction, so the own window is one bound.
    // It is still the event's own date and must beat a declared edition.
    expect(
      conceptHeaderDate("upcoming", null, "2026-09-13T00:00:00+00:00", EDITION),
    ).toBe("Ends Sep 13");
  });

  test("live and settled take no fallback; an unreadable state does", () => {
    expect(conceptHeaderDate("live", null, null, EDITION)).toBeNull();
    expect(conceptHeaderDate("settled", null, null, EDITION)).toBeNull();
    // `unknown` is what an adapter emits with no start signal (#3673). It is not
    // live and not settled, so the page has not begun as far as we can tell and
    // the declared edition is the best date we have.
    expect(conceptHeaderDate("unknown", null, null, EDITION)).toBe(
      "September 17–19, 2027",
    );
  });

  test("no edition, or an unparseable one, is null rather than debris", () => {
    expect(conceptHeaderDate("upcoming", null, null, null)).toBeNull();
    expect(conceptHeaderDate("upcoming", null, null, undefined)).toBeNull();
    expect(
      conceptHeaderDate("upcoming", null, null, { start: null, end: null }),
    ).toBeNull();
    expect(
      conceptHeaderDate("upcoming", null, null, { start: "soon", end: "later" }),
    ).toBeNull();
  });
});
