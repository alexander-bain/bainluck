// THE SHARED CARD MUST SHOW IT TOO — live/048, CERT-792 (the surface 786 missed).
//
// CERT-786's repair taught `FeedCard` and the Discover card what `suspended`
// means, and `suspendedCardsCert786.test.tsx` proves both of them print it.
// CERT-792's finding, verbatim: "the active shared `EventCard` still treats
// `suspended` as not-live/not-finished and renders the stale 72%/28% chips plus
// probability bar beside 'No result reported · last score 1-2'."
//
// That is the third card surface — `components/EventCard.tsx`, the one behind
// the league rails, the category grids, search results, pinned rows and My
// Stuff — and it was missed because its conditionals are written as `!isLive &&
// !isFinished` and `!isFinished`. `suspended` is neither, so it fell straight
// through to the PREGAME treatment: a confident 72%/28%, a filled probability
// bar, and a "Proj" footer, all two lines under a summary that says nobody is
// reporting a result. One card, two contradictory claims.
//
// It lives in its own file rather than inside the 786 one because the props are
// a different shape (`Event`, not `FeedItem`), and because a cert that names a
// specific surface should be answerable by a file that names it back.
//
// RENDERED, NOT GREPPED. #2060's lesson holds here: a source scan cannot tell a
// rendered field from a declared one, and wrapping a branch in `{false && (`
// leaves every string in the file intact. Everything below asserts markup.
//
// BOTH DIRECTIONS PER GOTCHA #43. Every suppression case has a live or scheduled
// sibling asserted UNCHANGED. Without them, a card that showed no probability
// for any status would pass the whole suspended half and empty the product.

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
import { suspendedSummary } from "@/lib/eventState";
import type { Event } from "@/lib/types";

// The CERT-752 specimen, same numbers as the 786 file so the two surfaces are
// compared on one payload. The commence time is deliberately IN THE PAST — a
// suspended match started and stopped, it is not upcoming.
const COMMENCE_IN_THE_PAST = new Date(Date.now() - 15 * 3600_000).toISOString();

function makeEvent(over: Partial<Event> = {}): Event {
  return {
    id: 15295047,
    external_id: "evt-15295047",
    sport: "tennis_atp_us_open",
    sport_name: "US Open",
    home_team: "Francesco Passaro",
    away_team: "Jesper de Jong",
    commence_time: COMMENCE_IN_THE_PAST,
    status: "suspended",
    home_score: 2,
    away_score: 1,
    home_team_data: { primary_color: "#2563eb", logo_small: "h.png" },
    away_team_data: { primary_color: "#64748b", logo_small: "a.png" },
    current_odds: {
      captured_at: COMMENCE_IN_THE_PAST,
      home_probability: 0.72,
      away_probability: 0.28,
      spread: null,
      over_under: null,
      // The pregame footer's other arm. Present so its suppression is a real
      // assertion and not a vacuous one — see the "Proj" case below.
      projected_home_score: 6,
      projected_away_score: 4,
    },
    ...over,
  } as unknown as Event;
}

function render(event: Event): string {
  return renderToStaticMarkup(<EventCard event={event} />);
}

/** Rendered text with entities decoded, so `·` compares sanely.
 *
 * `&amp;` is unescaped LAST, and that ordering is the whole point rather than a
 * style choice (CodeQL `js/double-escaping`). Doing it first turns a literal
 * `&amp;#x27;` in the markup into `&#x27;` and then into an apostrophe — one
 * escape too many — so an assertion could pass on text the page never showed.
 * Every specific entity is decoded before the ampersand that introduces them.
 */
function text(html: string): string {
  return html
    .replace(/<[^>]*>/g, " ")
    .replace(/&middot;|&#xB7;/g, "·")
    .replace(/&#x27;|&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ");
}

const EXPECTED = suspendedSummary(1, 2); // "No result reported · last score 1-2"

describe("the shared EventCard renders the suspended state", () => {
  it("prints the shared summary", () => {
    // The control for every suppression below: if this card were not reaching
    // the suspended arm at all, the assertions that things are ABSENT would
    // pass for the wrong reason.
    expect(text(render(makeEvent()))).toContain(EXPECTED);
  });

  it("drops both probability chips", () => {
    // THE cert finding. 0.72/0.28 is the last live blend on a match nothing is
    // reporting on; printed at full weight beside "no result reported" it sells
    // a stale line as the current one.
    const rendered = text(render(makeEvent()));
    expect(rendered).not.toContain("72%");
    expect(rendered).not.toContain("28%");
  });

  it("still prints both chips on a LIVE card", () => {
    const rendered = text(render(makeEvent({ status: "live" } as Partial<Event>)));
    expect(rendered).toContain("72%");
    expect(rendered).toContain("28%");
  });

  it("still prints both chips on a SCHEDULED card", () => {
    // The second control, and the one the fix could most easily have broken:
    // `suspended` shares the `!isLive && !isFinished` branch with `scheduled`,
    // so a fix written one condition too wide takes the pregame chip with it.
    const rendered = text(
      render(
        makeEvent({
          status: "scheduled",
          commence_time: new Date(Date.now() + 3 * 3600_000).toISOString(),
          home_score: null,
          away_score: null,
        } as Partial<Event>),
      ),
    );
    expect(rendered).toContain("72%");
    expect(rendered).toContain("28%");
  });

  it("draws no probability bar", () => {
    // The bar is the loudest claim on the card — a filled two-tone strip at
    // 72/28 — and there is no live price behind it. Asserted on the element's
    // own accessibility contract (`role="meter"` + this label), not on text:
    // the bar renders no characters at all, so a visible-text check would pass
    // whether it was there or not, and an added `data-testid` would be a hook
    // that only the test can see.
    expect(render(makeEvent())).not.toContain('aria-label="Win probability"');
  });

  it("still draws the bar on a LIVE card", () => {
    expect(render(makeEvent({ status: "live" } as Partial<Event>))).toContain(
      'aria-label="Win probability"',
    );
  });

  it("drops the pregame footer", () => {
    // "Proj 6-4" is a promise about a game that is going to be played. This one
    // stopped. The payload above carries real projections so this case cannot
    // pass merely because the fields were absent.
    expect(text(render(makeEvent()))).not.toContain("Proj");
  });

  it("still shows the pregame footer on a SCHEDULED card", () => {
    const rendered = text(
      render(
        makeEvent({
          status: "scheduled",
          commence_time: new Date(Date.now() + 3 * 3600_000).toISOString(),
          home_score: null,
          away_score: null,
        } as Partial<Event>),
      ),
    );
    expect(rendered).toContain("Proj");
  });
});
