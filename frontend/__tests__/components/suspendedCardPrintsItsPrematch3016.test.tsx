// A SUSPENDED CARD PRINTS THE ONE NUMBER IT CAN STATE HONESTLY — live/207, #3016.
//
// CERT-792 (`suspendedSharedEventCardCert792.test.tsx`, beside this file) took
// the live chip, the probability bar and the `Proj` footer off a `suspended`
// row, and every one of those suppressions is still right: all three assert
// something about a match nothing is reporting on. What it left behind was a
// card with NO number from any branch, because `prematch` — the grey pre-match
// pair the FINAL card prints — was gated on `isFinished` alone.
//
// live/207's specimen, production 2026-09-13: `/search?q=Hanwha Eagles` served
// 24 results, of which 17 were `suspended`, and ALL 17 carried `opening_odds`
// AND `current_odds`. A reader saw seventeen cards reading "No result
// reported" with nothing else on them, directly beside a `closed` sibling
// printing `44% / 56% · Pre-match · sportsbooks` off the same rung. Across the
// events table, 668 of 2,648 suspended rows carry an opening line.
//
// The fix is one condition: a suspended row takes the pre-match branch a
// finished row takes. The pre-match reading is what the market thought BEFORE
// the match, which stays true whatever happened afterwards — the opposite of
// the stale live blend the cert refused to show. This file is the both-
// directions guard for that: what now prints, what must STILL not print, and
// the no-opening-line case that must stay silent rather than invent a number.
//
// RENDERED, NOT GREPPED (#2060): every assertion below is on markup.

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
import { BOOKS_LABEL } from "@/lib/prematchReading";
import type { Event } from "@/lib/types";

// Event 15311074 as production served it: a KBO fixture whose clock ran out
// with nobody reporting, carrying both an opening line and a last live blend.
// The two DISAGREE on purpose — 0.4368 opening against 0.72 live — so the
// "still no live chip" assertions cannot be satisfied by the pre-match pair
// this fix adds, and the favourite the two rungs name is not the same side.
const COMMENCE_IN_THE_PAST = new Date(Date.now() - 15 * 3600_000).toISOString();

function makeEvent(over: Partial<Event> = {}): Event {
  return {
    id: 15311074,
    external_id: "evt-15311074",
    sport: "baseball_kbo",
    sport_name: "KBO",
    home_team: "Kia Tigers",
    away_team: "Hanwha Eagles",
    commence_time: COMMENCE_IN_THE_PAST,
    status: "suspended",
    home_score: null,
    away_score: null,
    current_odds: {
      captured_at: COMMENCE_IN_THE_PAST,
      home_probability: 0.72,
      away_probability: 0.28,
      spread: null,
      over_under: null,
      // Present so the footer's suppression stays a real assertion.
      projected_home_score: 6,
      projected_away_score: 4,
    },
    opening_odds: {
      captured_at: COMMENCE_IN_THE_PAST,
      home_probability: 0.4368,
      away_probability: 0.5632,
      spread: null,
      over_under: null,
    },
    ...over,
  } as unknown as Event;
}

function render(event: Event): string {
  return renderToStaticMarkup(<EventCard event={event} />);
}

/** Rendered text with entities decoded. `&amp;` LAST (CodeQL js/double-escaping). */
function text(html: string): string {
  return html
    .replace(/<[^>]*>/g, " ")
    .replace(/&middot;|&#xB7;/g, "·")
    .replace(/&#x27;|&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ");
}

/** The class attribute of the element whose whole text is this team's name. */
function nameClass(html: string, team: string): string {
  const match = new RegExp(`class="([^"]*)"[^>]*>${team}<`).exec(html);
  if (!match) throw new Error(`no rendered element found for "${team}"`);
  return match[1];
}

describe("a suspended card prints its pre-match reading", () => {
  it("prints both pre-match percents", () => {
    // 0.4368 / 0.5632 rounded ONCE as a pair. The whole finding: before this,
    // neither number appeared anywhere on the card.
    const rendered = text(render(makeEvent()));
    expect(rendered).toContain("44%");
    expect(rendered).toContain("56%");
  });

  it("labels them, so the rung is never implied", () => {
    // `Pre-match · sportsbooks` — the same label the FINAL sibling wears, and
    // the approved word (notice 33). Asserted through `BOOKS_LABEL` rather
    // than a spelling, so a change to the word moves both at once.
    expect(text(render(makeEvent()))).toContain(`Pre-match · ${BOOKS_LABEL}`);
  });

  it("attaches them to the right sides", () => {
    // A pair printed in two fixed slots is only honest if the slots are right.
    // The `data-prematch` attribute carries the raw probability, so this
    // cannot pass on a card that prints 44 and 56 the wrong way round.
    const html = render(makeEvent());
    expect(html).toMatch(/data-testid="event-card-prematch-home"[^>]*data-prematch="0.4368"/);
    expect(html).toMatch(/data-testid="event-card-prematch-away"[^>]*data-prematch="0.5632"/);
  });

  it("STILL drops the live chips — CERT-792 unchanged", () => {
    // 0.72/0.28 is the last live blend on a match nothing is reporting on.
    const rendered = text(render(makeEvent()));
    expect(rendered).not.toContain("72%");
    expect(rendered).not.toContain("28%");
  });

  it("STILL draws no probability bar — CERT-792 unchanged", () => {
    expect(render(makeEvent())).not.toContain('aria-label="Win probability"');
  });

  it("STILL drops the pregame footer — CERT-792 unchanged", () => {
    expect(text(render(makeEvent()))).not.toContain("Proj");
  });

  it("emphasises neither name", () => {
    // Emphasis on this card is `homeFavorite`, computed from `current_odds` —
    // the number the cert refuses to print. Bolding a side on the strength of
    // it is that claim made quietly, and here it would contradict the grey
    // pair outright: the live blend favours HOME, the opening line favours
    // AWAY. No result, no favourite.
    const html = render(makeEvent());
    expect(nameClass(html, "Kia Tigers")).toContain("text-text-primary");
    expect(nameClass(html, "Hanwha Eagles")).toContain("text-text-primary");
  });

  it("emphasises the favourite on a SCHEDULED sibling", () => {
    // The both-directions control for the assertion above (gotcha #43): a fix
    // one condition too wide would flatten every upcoming card's emphasis and
    // this is the only thing that would notice.
    const html = render(
      makeEvent({
        status: "scheduled",
        commence_time: new Date(Date.now() + 3 * 3600_000).toISOString(),
      } as Partial<Event>),
    );
    expect(nameClass(html, "Kia Tigers")).toContain("text-text-primary");
    expect(nameClass(html, "Hanwha Eagles")).toContain("text-text-secondary");
  });

  it("prints no percent at all when no opening line was ever captured", () => {
    // 1,980 of the 2,648 suspended rows, and all 820 `scheduled`-past-grace
    // ones, hold no opening line. A card with nothing to say says nothing —
    // it must not fall back to the live blend to fill the space.
    // The key is typed optional and the serializer omits it, so ABSENT is the
    // shape production sends. `prematchReading` tests it for falsiness, so a
    // served `null` takes the identical branch.
    const rendered = text(render(makeEvent({ opening_odds: undefined })));
    expect(rendered).not.toMatch(/\d+%/);
    expect(rendered).toContain("No result reported");
  });

  it("prints the pair on a SCHEDULED row hours past its own kickoff", () => {
    // #3211's arm of the same display question: `hasNoReportedResult` covers
    // both, so the card must not treat them differently. No production row is
    // in this state WITH an opening line today (measured: 0 of 820), which is
    // exactly why it needs a test rather than a sighting.
    const rendered = text(
      render(makeEvent({ status: "scheduled" } as Partial<Event>)),
    );
    expect(rendered).toContain("44%");
    expect(rendered).toContain("56%");
    expect(rendered).not.toContain("72%");
  });

  it("still prints the live chips on a LIVE card", () => {
    // The control that stops all of the above passing on a card that shows no
    // probability for any status.
    const rendered = text(render(makeEvent({ status: "live" } as Partial<Event>)));
    expect(rendered).toContain("72%");
    expect(rendered).toContain("28%");
  });

  it("still prints the pre-match pair on a FINISHED card", () => {
    const rendered = text(render(makeEvent({ status: "closed" } as Partial<Event>)));
    expect(rendered).toContain("44%");
    expect(rendered).toContain("56%");
  });
});
