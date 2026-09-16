// #6438 — A SETTLED HERO PRINTS "No price" IN THE LARGEST TYPE ON THE PAGE.
//
// Measured on production 2026-09-15 22:20Z by live/304, 31 minutes after
// release 4599 carried #6381's consumer half.
// `https://bainluck.com/events/15310639` — Liverpool FC v Fulham FC, tier 1,
// played and graded four days earlier on Sep 11. One card, two sentences about
// the same graded match:
//
//   pill, top-left of the card     "Settled · Draw 0-0"      <- correct
//   between the crests, largest    "No price"                <- what a reader
//   type on the page                                            reads first
//
// And the `Correct Score` card immediately below reads `Draw 0-0 — Won`. So the
// page HELD the result, in the same payload, and shouted the wrong thing.
//
// NOT A REGRESSION OF #6381 — that ship strictly improved this card (the pill
// said "No result reported" an hour before). This is the half of the hero the
// settled ruling never reached: the main slot knew only `started`.
//
// THE COMMON ARM, NOT AN EDGE CASE: of the 1,471 events holding a venue grade,
// only 68 also hold a score of our own and take the settled-outcome hero. The
// other ~1,400 fall through to this component with no reading at all.
//
// ── WHY EMPTY AND NOT THE RESULT ────────────────────────────────────────────
//
// The obvious repair — print "Draw 0-0" between the crests — states one fact
// twice in one card, ~150px apart, from the same two payload keys. Alex's
// standing ruling supplies the other half: if a number cannot be shown
// honestly, leave the space empty and do not explain the emptiness. A settled
// market having no price is its normal end state, not a deficiency to announce.
// So the slot goes silent and the pill does the talking.
//
// The container STAYS in the DOM. `tools/hero-clip-probe.mjs` and
// `tools/felt-load.mjs` both anchor on `[data-testid="event-hero-probability"]`;
// returning null would have taken the page out of two rails to delete a string.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import EventHeroProbabilityPair from "@/components/EventHeroProbabilityPair";
import { venueSettledSummary } from "@/lib/eventState";

/**
 * The page passes its own settled answer, derived through the shared helper.
 * Driving the REAL helper here rather than hand-passing `true` is the point:
 * the pill and this slot must come from one derivation, and a test that passed
 * its own boolean could not notice them drifting apart.
 */
function settledFromPayload(
  venue_settled: boolean | null | undefined,
  venue_settled_result: string | null | undefined,
): boolean {
  return venueSettledSummary(venue_settled, venue_settled_result) !== null;
}

/** The production specimen's hero: graded, and no reading left to print. */
function heroMarkup(over: Record<string, unknown> = {}): string {
  return renderToStaticMarkup(
    <EventHeroProbabilityPair
      homeProb={null}
      awayProb={null}
      homePct={null}
      awayPct={null}
      homeColor="#C8102E"
      awayColor="#FFFFFF"
      probSourceLabel={null}
      started
      {...over}
    />,
  );
}

describe("#6438 — a graded contest says nothing where the price used to be", () => {
  it("prints neither price sentence on the Liverpool–Fulham specimen", () => {
    const markup = heroMarkup({ venueSettled: settledFromPayload(true, "Draw 0-0") });

    expect(markup).not.toContain("No price");
    expect(markup).not.toContain("No price yet");
  });

  it("keeps the element the two production rails anchor on", () => {
    // `hero-clip-probe` waits on this selector for 30s and `felt-load` uses it
    // as a paint anchor. Deleting a string must not delete the page's anchor.
    const markup = heroMarkup({ venueSettled: settledFromPayload(true, "Draw 0-0") });

    expect(markup).toContain('data-testid="event-hero-probability"');
    expect(markup).toContain('data-probability=""');
  });

  it("is silent for a venue grade that carries no result string at all", () => {
    // `venueSettledSummary` returns the bare label when the result is missing,
    // so the pill still speaks and the hero must still not contradict it.
    expect(settledFromPayload(true, null)).toBe(true);
    expect(heroMarkup({ venueSettled: settledFromPayload(true, null) })).not.toContain("No price");

    // A blank string is trimmed to nothing by the helper and is still settled.
    expect(settledFromPayload(true, "   ")).toBe(true);
    expect(heroMarkup({ venueSettled: settledFromPayload(true, "   ") })).not.toContain("No price");
  });
});

describe("#6438 — and the two states it must not touch (gotcha #43, both directions)", () => {
  it("still says 'No price' for a started match the venue has NOT graded", () => {
    // #5890's case, unchanged: the prices existed and were withdrawn.
    expect(settledFromPayload(false, null)).toBe(false);
    expect(heroMarkup({ venueSettled: settledFromPayload(false, null) })).toContain("No price");
  });

  it("still says 'No price yet' before kick-off", () => {
    // #3459's case, unchanged: a promise about the future that is still true.
    const markup = heroMarkup({ started: false, venueSettled: false });

    expect(markup).toContain("No price yet");
  });

  it("does not touch a settled event that still has a reading to print", () => {
    // The suppression lives ONLY in the no-reading branch. A graded event that
    // somehow still carries a probability prints it exactly as before — this
    // ship removes a sentence, it does not withhold a number.
    const markup = renderToStaticMarkup(
      <EventHeroProbabilityPair
        homeProb={0.62}
        awayProb={0.38}
        homePct={62}
        awayPct={38}
        homeColor="#C8102E"
        awayColor="#000000"
        probSourceLabel="Kalshi"
        started
        venueSettled={settledFromPayload(true, "Draw 0-0")}
      />,
    );

    expect(markup).toContain('data-probability="0.62"');
    expect(markup).toContain("62");
  });

  it("defaults to the old behaviour when the page says nothing", () => {
    // Every caller that does not pass the prop keeps the string it had.
    expect(heroMarkup()).toContain("No price");
  });
});

describe("#6438 — the page hands over its own settled answer, not a second reading", () => {
  // A SOURCE SCAN, scoped to the one call site, for the reason the whole fix
  // turns on: `venueSettledSummary` exists because four surfaces once read this
  // state four different ways. If this slot re-derived it from
  // `event.venue_settled` directly it could disagree with the pill it sits
  // under — which is the defect, rebuilt with different words.
  const source = require("fs").readFileSync(
    require("path").join(__dirname, "..", "..", "app", "events", "[id]", "page.tsx"),
    "utf8",
  ) as string;

  it("passes the pill's own sentence, not the raw payload key", () => {
    const line = source.split("\n").find((l) => l.includes("venueSettled="));

    expect(line).toBeDefined();
    expect(line).toContain("venueSettledSentence !== null");
    expect(line).not.toContain("event.venue_settled");
  });

  it("still derives that sentence through the shared helper", () => {
    expect(source).toContain(
      "venueSettledSummary(event?.venue_settled, event?.venue_settled_result)",
    );
  });
});
