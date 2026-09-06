import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import EventCard from "../../components/EventCard";
import type { Event } from "../../lib/types";

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});

jest.mock("../../hooks", () => ({
  useAnalytics: () => ({
    trackEventCardClick: jest.fn(),
  }),
}));

function makeEvent(overrides: Partial<Event> = {}): Event {
  return {
    id: 100,
    external_id: "evt-100",
    sport: "basketball_nba",
    home_team: "Boston Celtics",
    away_team: "New York Knicks",
    commence_time: "2030-01-01T12:00:00.000Z",
    status: "scheduled",
    home_score: null,
    away_score: null,
    current_odds: {
      captured_at: "2030-01-01T11:00:00.000Z",
      home_probability: 0.62,
      away_probability: 0.38,
      spread: null,
      over_under: null,
      projected_home_score: 111,
      projected_away_score: 104,
    },
    opening_odds: {
      home_probability: 0.55,
      away_probability: 0.45,
      spread: null,
      over_under: null,
      favorite: "home",
    },
    ...overrides,
  };
}

describe("EventCard", () => {
  it("shows projected score footer for scheduled events", () => {
    const html = renderToStaticMarkup(
      React.createElement(EventCard, { event: makeEvent() })
    );

    expect(html).toContain("Proj");
    expect(html).toContain("111-104");
    expect(html).not.toContain("Final");
  });

  it("shows live badge and opening split for live started events", () => {
    const html = renderToStaticMarkup(
      React.createElement(EventCard, {
        event: makeEvent({
          status: "live",
          commence_time: "2020-01-01T12:00:00.000Z",
          pulse: {
            score: 88,
            status: "racing",
            label: "Must-Watch",
            emoji: "🫀",
          },
        }),
      })
    );

    expect(html).toContain("LIVE");
    expect(html).toContain("Opened");
    expect(html).toContain("55/45");
    // L2-156 Item 1: Excitement Index display is stripped from cards (still computed
    // in the backend for ranking). The EI badge must not render.
    expect(html).not.toContain("🫀 88");
    expect(html).not.toContain("Excitement Index");
  });

  it("treats not-yet-started live events as pregame (no live badge)", () => {
    const html = renderToStaticMarkup(
      React.createElement(EventCard, {
        event: makeEvent({
          status: "live",
          commence_time: "2999-01-01T12:00:00.000Z",
        }),
      })
    );

    expect(html).not.toContain("LIVE");
    expect(html).toContain("Proj");
  });

  it("shows settled treatment on final cards: score block, no probability chips", () => {
    const html = renderToStaticMarkup(
      React.createElement(EventCard, {
        event: makeEvent({
          status: "completed",
          home_score: 102,
          away_score: 99,
          current_odds: {
            captured_at: "2030-01-01T11:00:00.000Z",
            home_probability: 0.2,
            away_probability: 0.8,
            spread: null,
            over_under: null,
            projected_home_score: 95,
            projected_away_score: 110,
          },
        }),
      })
    );

    // L2-112 settled treatment: a FINAL card drops the live-style probability
    // chips and the probability bar in favor of the centered score block. It
    // shows "Final" + the final score (102-99).
    expect(html).toContain("Final");
    expect(html).toContain("102");
    expect(html).toContain("99");

    // The bar is what L2-112 removed, and it is still gone. `role="meter"` /
    // `aria-label="Win probability"` is `ProbabilityBar`'s own wrapper and
    // nothing else in this card emits it. Proven non-vacuous at the bottom of
    // this test, which asserts a PREGAME card does contain it.
    expect(html).not.toContain('aria-label="Win probability"');
    expect(html).not.toContain('role="meter"');

    // And the live-style chip is gone. Spelled as "every percent on this card
    // belongs to a pre-match span" rather than as a class name: the chip's
    // classes are `font-mono tabular-nums` plus a colour, which the pre-match
    // span shares, so no single class distinguishes them. Deleting the
    // `data-prematch` spans and then demanding no `%` survives is exact, and
    // it fails if a chip ever returns to this branch.
    const withoutPrematch = html.replace(
      /<span [^>]*data-testid="event-card-prematch-(?:home|away)"[^>]*>[\s\S]*?%<\/span>/g,
      "",
    );
    // Non-vacuous in both directions: the replace must actually have removed
    // the two spans (otherwise a regex that matches nothing would make the
    // assertion below a test of the raw markup and it would fail loudly), and
    // what remains must carry no percent at all.
    expect(html).toContain("55%");
    expect(withoutPrematch).not.toContain("event-card-prematch-home");
    expect(withoutPrematch).not.toContain("%");

    // ── #2764 AMENDMENT ──────────────────────────────────────────────────
    //
    // This test used to assert `not.toContain("55%")` / `not.toContain("45%")`
    // — the opening-odds pair — with the note "removed with the settled
    // redesign". That was true of the redesign and is no longer the product's
    // intent. Alex, on a column of FINAL cards: *"How come none of these show
    // pre-event probability?"* (#2764, and ux/1036 before it on the other
    // three surfaces).
    //
    // So 55/45 is back on a settled card, and it is NOT a regression of
    // L2-112: it is a different element making a different claim. The chip was
    // a live-weight number in the card's loudest slot; this is a grey
    // `text-[11px]` prior beside the name it is about, under an explicit
    // `Pre-match · books` label. L2-112 removed a number that read as current.
    // #2764 adds one that says out loud that it is not.
    //
    // The assertion is kept — inverted — rather than deleted, so the pair is
    // still pinned to a fixed expectation and a future change has to come
    // through this comment.
    expect(html).toContain("55%");
    expect(html).toContain("45%");
    expect(html).toContain('data-testid="event-card-prematch-home"');
    expect(html).toContain("Pre-match · books");

    // The absence assertions above are only worth anything if they name
    // strings something actually emits. A PREGAME card renders the bar and the
    // chips, so this pins both: a rename or a typo goes red here instead of
    // making the `not.toContain` lines pass forever on a string nothing
    // produces. (This caught a real one — see the note below.)
    const pregame = renderToStaticMarkup(
      React.createElement(EventCard, { event: makeEvent() })
    );
    expect(pregame).toContain('aria-label="Win probability"');
    expect(pregame).toContain("62%");

    // The defect this comment used to record — `text-prob-md` / `text-prob-sm`
    // never reaching the DOM, because tailwind-merge read the custom fontSize
    // as a `text-*` colour and kept only `text-text-primary` — was filed as
    // #3592 and is fixed in `lib/utils.ts`. It is asserted in its own block
    // below ("the chips keep the size the design asks for"), not here, because
    // this test's subject is the SETTLED card, which renders no chip at all.
  });
});

// #3592 — the chip sizes have to survive `cn`.
//
// `cn` is `twMerge(clsx(...))`. `text-prob-md` is a custom fontSize; without
// the scale registered, tailwind-merge filed it in the same group as
// `text-text-primary` and dropped it, so the favourite and the underdog
// rendered at the SAME inherited size on every league, team and search card —
// the card's "this one is the favourite" signal carried only by the bar.
//
// These assert PRESENCE IN THE RENDERED MARKUP, deliberately. A test that
// checked the class was passed to `cn` would have passed throughout the bug:
// passing it is exactly what already happened.
describe("EventCard — the chips keep the size the design asks for", () => {
  it("renders the favourite at text-prob-md and the underdog at text-prob-sm", () => {
    const html = renderToStaticMarkup(
      React.createElement(EventCard, { event: makeEvent() })
    );

    // Non-vacuity: these are the chips those classes belong to.
    expect(html).toContain("62%");
    expect(html).toContain("38%");

    expect(html).toContain("text-prob-md");
    expect(html).toContain("text-prob-sm");
    // and the colours they were losing to are still there.
    expect(html).toContain("text-text-primary");
    expect(html).toContain("text-text-secondary");
  });

  it("binds the sizes to favourite/underdog, not to home/away", () => {
    // Away is the favourite here, so the md/sm pairing has to flip with it.
    const awayFavourite = makeEvent({
      current_odds: {
        captured_at: "2030-01-01T11:00:00.000Z",
        home_probability: 0.38,
        away_probability: 0.62,
        spread: null,
        over_under: null,
        projected_home_score: 104,
        projected_away_score: 111,
      },
    } as Partial<Event>);
    const html = renderToStaticMarkup(
      React.createElement(EventCard, { event: awayFavourite })
    );

    // The home chip is now the underdog: its span carries prob-sm, and the
    // away chip carries prob-md. Assert on the ORDER the two sizes appear in,
    // which is the only thing that distinguishes this from the case above.
    const md = html.indexOf("text-prob-md");
    const sm = html.indexOf("text-prob-sm");
    expect(md).toBeGreaterThan(-1);
    expect(sm).toBeGreaterThan(-1);
    expect(sm).toBeLessThan(md); // home (underdog, sm) renders before away (favourite, md)
  });

  it("still renders no chip at all on a settled card", () => {
    const html = renderToStaticMarkup(
      React.createElement(EventCard, {
        event: makeEvent({
          status: "completed",
          home_score: 110,
          away_score: 104,
        }),
      })
    );
    expect(html).not.toContain("text-prob-md");
    expect(html).not.toContain("text-prob-sm");
  });
});

// UX-P074 (#1860) — a shared card must not depend on how its callers spell
// absence.
//
// The league rails started feeding this card a `current_odds` that carries a
// blend and no projection. The footer guard was `projected_home_score !== null`,
// which an ABSENT key passes (`undefined !== null` is true), so the card printed
// "Proj NaN-NaN" on every league fixture. The adapter now also sends explicit
// nulls — but that is the CALLER being polite, and this test is here because the
// card's own guard has to hold for the next caller that is not.
describe("EventCard — absence is absence, however it is spelled", () => {
  it("prints no projection when the projected-score keys are simply missing", () => {
    const partial = makeEvent();
    // Exactly the shape a producer that has a probability and no projection
    // sends: the two projected keys are not present at all.
    partial.current_odds = {
      captured_at: "2030-01-01T11:00:00.000Z",
      home_probability: 0.62,
      away_probability: 0.38,
      spread: null,
      over_under: null,
    } as unknown as Event["current_odds"];

    const html = renderToStaticMarkup(
      React.createElement(EventCard, { event: partial })
    );

    expect(html).not.toContain("NaN");
    expect(html).not.toContain("Proj");
  });

  it("still prints the projection when it is actually there", () => {
    // The other direction (gotcha #43): loosening the guard must not have
    // deleted the feature it guards.
    const html = renderToStaticMarkup(
      React.createElement(EventCard, { event: makeEvent() })
    );
    expect(html).toContain("Proj");
    expect(html).toContain("111-104");
  });
});
