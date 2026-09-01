/**
 * #2448 — THREE LABELS FOR ONE LINE, AND TWO THINGS AROUND IT.
 *
 * Alex, on `/events/15293846`:
 *
 *   > the y-axis is labelled with both player names vertically, while the
 *   > single plotted line is labelled `Betting Odds` — three labels, one line.
 *   > Also `Tap/hover for details` printed as body text, and no link back to
 *   > the tournament (only `Back to events`).
 *
 * Three findings, three fixes, three arms below.
 *
 * ## 1. The gutter is an axis, so it points
 *
 * The names were never the error: the chart's y-axis genuinely runs from "the
 * away player wins" at 0% to "the home player wins" at 100%, so both names are
 * its POLES. What was missing is the one thing that turns two names into an
 * axis — a direction. Without it there are two names, a 0–100 scale and a line,
 * and no rule saying which name the line's height belongs to. One caret per
 * pole supplies the rule and adds no words.
 *
 * ## 2. `Tap/hover for details` is deleted
 *
 * A caption whose whole content was an instruction about our own UI, in the
 * slot the page uses for facts.
 *
 * ## 3. A container needs a way out
 *
 * The tournament page routes a match card to `/events/{id}`; this page routed
 * back to `/` — Discover, not the tournament. Verified against the live
 * `/api/tournaments/by-event/15293846` on 2026-09-01, which answers
 * `{slug: "us-open", title: "US Open 2026", url: "/tournaments/us-open"}`.
 *
 * ## Why arms 1 and 2 scan source and arm 3 renders
 *
 * `OddsChart` is Recharts, and Recharts measures its container: server-rendered
 * it emits an empty box, so a "render" of it would assert against a blank
 * rectangle. `usOpenEventPage.test.tsx` says so at length and this file inherits
 * the constraint rather than pretending otherwise. The scan therefore RAISES if
 * it cannot find the block it is meant to be checking — a source guard that
 * silently matches nothing is the failure mode of source guards, and a renamed
 * gutter would otherwise turn this file green by making it vacuous.
 *
 * `TournamentBackLink` is ordinary markup and is rendered, both arms: present
 * for an event in a register, absent for one that is not.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "fs";
import { join } from "path";

import { TournamentBackLink } from "@/components/event/TournamentExtensions";
import { eventTournamentKey } from "@/lib/eventOutcome";
import type { EventTournamentResponse } from "@/lib/types";

/** What `useSWR` will answer for the next render. */
let swrAnswer: { data?: EventTournamentResponse } = {};

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => (key === null ? { data: undefined } : swrAnswer),
}));

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});

const CHART = join(__dirname, "../../components/OddsChart.tsx");

/** Source with comments stripped, so our own notes about the fix cannot pass it. */
function chartSource(): string {
  return readFileSync(CHART, "utf8")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/\/\/.*$/gm, "");
}

describe("#2448 — the chart's labels, and the way back up", () => {
  /**
   * ARM 1. Both poles carry a direction glyph AND a sentence, and the scan
   * proves it found two poles before believing either — `toHaveLength(2)` is
   * the assertion that keeps this test from going vacuous the day the gutter is
   * restructured.
   */
  it("gives each axis pole a direction, so the line's height means something", () => {
    const src = chartSource();
    const poles = src.match(/data-pole="(home|away)"/g) ?? [];
    expect(poles).toHaveLength(2);
    expect(poles).toContain('data-pole="home"');
    expect(poles).toContain('data-pole="away"');

    // The glyphs. Up is the home pole, down is the away pole — a chart that
    // pointed both the same way would be worse than pointing neither.
    expect(src).toContain('{"↑"} {homeShort}');
    expect(src).toContain('{"↓"} {awayShort}');

    // And the sentence, because a screen reader cannot see which end of a
    // gutter a label sits at, so the glyph carries nothing for it.
    expect(src).toContain("The line rises towards {homeShort}");
    expect(src).toContain("The line falls towards {awayShort}");
  });

  /** ARM 2. The instruction-as-copy is gone and nothing took its place. */
  it("prints no instruction about its own UI where a fact should be", () => {
    const src = chartSource();
    expect(src).not.toContain("Tap/hover for details");
    expect(src).not.toMatch(/Tap (or|\/)\s*hover/i);
    expect(src).not.toMatch(/hover for (details|more)/i);
  });

  /**
   * ARM 3, BOTH DIRECTIONS (gotcha #43). A tournament event gets the link; an
   * event with no register entry — which is nearly every event on the site —
   * gets nothing at all, not an empty slot and not a link to a guessed slug.
   */
  it("links back to the tournament for an event that is in one", () => {
    swrAnswer = {
      data: {
        event_id: 15293846,
        tournament: {
          slug: "us-open",
          title: "US Open 2026",
          url: "/tournaments/us-open",
        },
        props: [],
        props_count: 0,
        props_dropped: {},
        decided: true,
      } as EventTournamentResponse,
    };
    const html = renderToStaticMarkup(
      <TournamentBackLink eventId={15293846} sportKey="tennis_atp_us_open" />
    );
    expect(html).toContain('data-testid="tournament-back-link"');
    expect(html).toContain('href="/tournaments/us-open"');
    expect(html).toContain("US Open 2026");
  });

  it("renders nothing for an event that is not in a tournament", () => {
    swrAnswer = {
      data: {
        event_id: 1,
        tournament: null,
        reason: "NOT_IN_REGISTER",
        props: [],
        props_count: 0,
        props_dropped: {},
        decided: false,
      } as EventTournamentResponse,
    };
    expect(
      renderToStaticMarkup(<TournamentBackLink eventId={1} sportKey="tennis_atp_us_open" />)
    ).toBe("");

    // And an off-sport event never even asks: the SWR key is null, so there is
    // no request to dedupe and no link either.
    swrAnswer = {};
    expect(
      renderToStaticMarkup(<TournamentBackLink eventId={2} sportKey="basketball_nba" />)
    ).toBe("");
    expect(renderToStaticMarkup(<TournamentBackLink eventId={3} sportKey={null} />)).toBe("");
  });

  /**
   * ONE REQUEST, NOT TWO. `TournamentBackLink` and `TournamentExtensions` share
   * the SWR key verbatim so SWR dedupes them. A key spelled differently in the
   * two components would be a silent doubling of the round trip the eligibility
   * gate exists to avoid, and nothing on the page would look wrong.
   *
   * ⚠️ THIS GUARD PINNED THE LITERAL AND #2447 MOVED IT. The key was written
   * out at each call site when this was authored; #2447 lifted it into
   * `eventTournamentKey()` so the event page could share it, and the third
   * assertion here — `toContain('["event-tournament", eventId]')` — went red
   * against its own ship. The guard was right to redden, so the repair is not
   * to delete the clause but to move it to where the key now lives: the call
   * sites are asserted to route through the ONE resolver, and the resolver is
   * asserted to still produce the wire key. Pinning only the call sites would
   * let the key itself be renamed silently, which is the exact failure this
   * test exists for.
   */
  it("every register read in this module uses ONE SWR key", () => {
    // Comments stripped: the doc comments quote the key, and a guard that
    // counted prose would pass on mentions rather than on call sites.
    const src = readFileSync(
      join(__dirname, "../../components/event/TournamentExtensions.tsx"),
      "utf8"
    )
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/\/\/.*$/gm, "");

    // Every `useSWR(` call's first argument, whatever it is. Counting a literal
    // would go vacuous the moment somebody renamed the key; this reddens
    // instead, because it asserts against what the calls actually pass.
    const calls = [...src.matchAll(/useSWR<[^>]*>\(\s*([^\n]*?),\s*$/gm)].map((m) =>
      m[1].trim()
    );
    expect(calls.length).toBeGreaterThanOrEqual(2);
    expect(new Set(calls).size).toBe(1);
    expect(calls[0]).toContain("eventTournamentKey(eventId)");

    // The other surface — the event page's own read — goes through the same
    // resolver, which is the half of "one request" this file cannot see.
    const page = readFileSync(join(__dirname, "../../app/events/[id]/page.tsx"), "utf8");
    expect(page).toContain("eventTournamentKey(eventId)");

    // And the resolver still spells the wire key the route is mounted at.
    expect(eventTournamentKey(4242)).toEqual(["event-tournament", 4242]);
  });
});
