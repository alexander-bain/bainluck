// THE CARD FOR A MATCH NOBODY REPORTED — #3211, lane1/134.
//
// ═══ WHAT THIS GRADES ═══
//
// The rails now return a row that still says `scheduled` days after its own
// kickoff (`test_the_two_rails_are_jointly_exhaustive_3211.py`). 171 US Open
// matches were in that state on production 2026-09-05 and reachable from no
// rail at all; making them reachable is only half a ship, because the shared
// `EventCard` decides what the reader is then told about them.
//
// Before this change the card's conditionals were `!isLive && !isFinished &&
// !isSuspended`, and `isSuspended` tested the literal status — so a match that
// should have been played hours ago fell straight through to the PREGAME
// treatment: a start time in the top-right ("Sep 1 5:00 PM"), a confident
// probability pair, a filled probability bar and a "Proj" footer. That is
// `lib/eventState.ts`'s opening paragraph exactly — the upcoming-branch
// fall-through, "a quieter lie than 'Final', not a smaller one".
//
// ═══ WHY IT IS THE SAME TREATMENT AS `suspended`, NOT A NEW ONE ═══
//
// CERT-786 blocked on four surfaces reading one state four different ways. The
// answer then was one shared string; the answer here is the same string, via
// `hasNoReportedResult`. To a reader the two states are one sentence — this
// match should have happened and nobody has told us anything — and a second
// badge would ask them to care about which of our sources failed.
//
// RENDERED, NOT GREPPED (#2060): a source scan cannot tell a rendered branch
// from a declared one, and `{false && (` leaves every string intact.
//
// BOTH DIRECTIONS PER GOTCHA #43: every suppression has a sibling asserted
// UNCHANGED. A card that showed no probability for any status would pass the
// whole suppression half of this file and empty the product.

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
import { SUSPENDED_LABEL, UPCOMING_GRACE_MS } from "@/lib/eventState";
import type { Event } from "@/lib/types";

// The specimen: Bucsa/Melichar-Martinez v Dart/Lumsden, a US Open doubles match
// stamped at exactly midnight UTC by a Kalshi ticker (gotcha #14) and still
// `scheduled` days later because nothing ever settled it (#2700).
//
// The card reads `Date.now()` internally, so the fixture is expressed as an
// OFFSET from it rather than as a literal date — gotcha #44: offset first, and
// never write an anchor whose meaning changes tomorrow.
const WELL_PAST_KICKOFF = new Date(Date.now() - 3 * 24 * 3600_000).toISOString();
const INSIDE_THE_GRACE = new Date(
  Date.now() - (UPCOMING_GRACE_MS - 10 * 60_000),
).toISOString();
const NOT_YET_KICKED_OFF = new Date(Date.now() + 6 * 3600_000).toISOString();

function makeEvent(over: Partial<Event> = {}): Event {
  return {
    id: 15304868,
    external_id: "evt-15304868",
    sport: "tennis_wta",
    sport_name: "WTA",
    home_team: "Dart / Lumsden",
    away_team: "Bucsa / Melichar-Martinez",
    commence_time: WELL_PAST_KICKOFF,
    status: "scheduled",
    // No score, and that is the shape rather than an omission: unlike a
    // suspended match, nothing ever reported a single point of this one.
    home_score: null,
    away_score: null,
    current_odds: {
      captured_at: WELL_PAST_KICKOFF,
      home_probability: 0.72,
      away_probability: 0.28,
      spread: null,
      over_under: null,
      // Present so the "Proj" suppression below is a real assertion rather
      // than a vacuous one.
      projected_home_score: 6,
      projected_away_score: 4,
    },
    ...over,
  } as unknown as Event;
}

function render(event: Event): string {
  return renderToStaticMarkup(<EventCard event={event} />);
}

function text(html: string): string {
  return html
    .replace(/<[^>]*>/g, " ")
    .replace(/&middot;|&#xB7;/g, "·")
    .replace(/&#x27;|&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ");
}

describe("#3211 · a past-kickoff scheduled card states what is not known", () => {
  it("prints the shared label", () => {
    // The control for every suppression below: if the card were not reaching
    // this arm at all, the ABSENCE assertions would pass for the wrong reason.
    expect(text(render(makeEvent()))).toContain(SUSPENDED_LABEL);
  });

  it("prints the BARE label, with no invented score", () => {
    // `suspendedSummary` appends "· last score 2-1" only when BOTH sides have
    // one. This row has neither, so half a score must not appear — the partial
    // line that graded the CERT-752 specimen 1.0/0.0, told smaller.
    const rendered = text(render(makeEvent()));
    expect(rendered).toContain(SUSPENDED_LABEL);
    expect(rendered).not.toContain("last score");
  });

  it("does NOT advertise a start time", () => {
    // The defect in one assertion. The old card printed the commence stamp in
    // this slot — a date three days gone, in the position a reader reads as
    // "when this begins".
    const rendered = text(render(makeEvent()));
    const started = new Date(WELL_PAST_KICKOFF);
    const dateLabel = `${started.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
    })}`;
    expect(rendered).not.toContain(dateLabel);
  });

  it("does not claim a Final", () => {
    // The other direction. live/048 removed a false Final; replacing it with a
    // different false Final would not be a repair.
    expect(text(render(makeEvent()))).not.toMatch(/\bFinal\b/);
  });

  it("withholds the probability pair and the projection", () => {
    // CERT-792's argument, inherited: a filled bar is the loudest claim on the
    // card and there is no live price behind a match that may already be over.
    const rendered = text(render(makeEvent()));
    expect(rendered).not.toContain("72");
    expect(rendered).not.toContain("28");
    expect(rendered).not.toContain("Proj");
  });
});

describe("#3211 · CONTROLS — the healthy card is untouched", () => {
  it("a fixture INSIDE the grace still renders as upcoming, with its number", () => {
    // The boundary from the other side. Without this arm the suite would pass
    // over a card that had simply stopped printing probabilities.
    const rendered = text(render(makeEvent({ commence_time: INSIDE_THE_GRACE })));
    expect(rendered).not.toContain(SUSPENDED_LABEL);
    expect(rendered).toContain("72");
  });

  it("a fixture that has not kicked off is unchanged", () => {
    const rendered = text(render(makeEvent({ commence_time: NOT_YET_KICKED_OFF })));
    expect(rendered).not.toContain(SUSPENDED_LABEL);
    expect(rendered).toContain("72");
  });

  it("a LIVE match hours past its start is still LIVE, not result-less", () => {
    // The control that keeps this from becoming a rule about elapsed time. A
    // five-set match runs long; that is not a reporting failure.
    const rendered = text(
      render(makeEvent({ status: "live", home_score: 2, away_score: 1 } as Partial<Event>)),
    );
    expect(rendered).not.toContain(SUSPENDED_LABEL);
  });

  it("a settled match still says Final", () => {
    const rendered = text(
      render(
        makeEvent({
          status: "completed",
          home_score: 6,
          away_score: 3,
        } as Partial<Event>),
      ),
    );
    expect(rendered).toMatch(/\bFinal\b/);
    expect(rendered).not.toContain(SUSPENDED_LABEL);
  });

  it("a genuinely suspended match keeps its last score", () => {
    // live/056's ship, asserted here so this change cannot be read as replacing
    // it: that state carries a partial score and must still print it.
    const rendered = text(
      render(
        makeEvent({
          status: "suspended",
          home_score: 2,
          away_score: 1,
        } as Partial<Event>),
      ),
    );
    expect(rendered).toContain("last score 2-1");
  });
});
