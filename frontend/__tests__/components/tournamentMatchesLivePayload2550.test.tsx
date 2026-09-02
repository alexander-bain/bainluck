/**
 * #2550 — THE SHIP, replayed through the unedited production payload.
 *
 * The sibling suite (`tournamentMatches.test.tsx`) proves the MECHANISM on a
 * hand-built row. This one proves the SHIP: the exact bytes
 * `GET https://api.bainluck.com/api/tournaments/us-open` served at 2026-09-01
 * ~17:45 PT, when the shopper photographed the hub printing "4:05 PM" over
 * Monfils v Vallejo — a match that was, at that moment, in its third set.
 *
 * The fixture is captured, never edited. That is the whole point: a hand-built
 * row can be built to pass, and this cohort was found precisely because the
 * mechanism looked fine in isolation. If a future payload change moves
 * `live_state` or `status_detail`, this suite goes red on the real shape while
 * the hand-built one stays green — which is the signal we want.
 *
 * WHAT IT DOES NOT CLAIM. It does not prove the browser rendered it; only a
 * production LOOK does, and that is logged on the queue. It proves that the
 * payload the browser was handed, through the pure builder and the real
 * component, produces a live row and no stale clock.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";

import TournamentMatches from "@/components/tournament/TournamentMatches";
import { liveMatchLabel, matchListFromSlate } from "@/lib/matchList";
import type { SlateMatch } from "@/lib/slate";

const CAPTURE = JSON.parse(
  fs.readFileSync(
    path.join(__dirname, "..", "fixtures", "tournamentSlateUsOpenLive.20260901.json"),
    "utf8"
  )
) as { slate: { in_progress: number }; matches: SlateMatch[] };

const MATCHES = CAPTURE.matches;

/** Monfils v Vallejo — the row in the shopper's screenshot. */
const LIVE_KEY = "mens-singles:adolfo-daniel-vallejo-vs-gael-monfils:2026-08-30";

describe("#2550 — the captured US Open payload renders its live match as live", () => {
  it("the capture still contains the cohort this guard is about", () => {
    // If this fails the fixture was edited or replaced, and every assertion
    // below is measuring a population it was not written for.
    expect(MATCHES.length).toBe(10);
    expect(CAPTURE.slate.in_progress).toBe(1);
    const live = MATCHES.filter((m) => m.live_state === "in_progress");
    expect(live).toHaveLength(1);
    expect(live[0].matchup_key).toBe(LIVE_KEY);
    expect(live[0].status_detail).toBe("3rd Set");
    // And the nine others carry a SCHEDULE in that same field — the reason
    // `liveMatchLabel` refuses `status_detail` on its face.
    const upcoming = MATCHES.filter((m) => m.live_state === "upcoming");
    expect(upcoming).toHaveLength(9);
    expect(upcoming.every((m) => / at /i.test(m.status_detail ?? ""))).toBe(true);
  });

  it("labels the live row from the payload and leaves the other nine alone", () => {
    const entries = matchListFromSlate(MATCHES);
    const labelled = entries.filter((e) => liveMatchLabel(e) !== null);
    expect(labelled).toHaveLength(1);
    expect(labelled[0].id).toBe(LIVE_KEY);
    expect(liveMatchLabel(labelled[0])).toBe("3rd Set");
  });

  it("renders one LIVE badge, and the live row prints no start time", () => {
    const entries = matchListFromSlate(MATCHES);
    const html = renderToStaticMarkup(<TournamentMatches entries={entries} />);

    // One badge on the page, not ten and not none.
    expect(html.match(/data-testid="match-live"/g) ?? []).toHaveLength(1);
    expect(html).toContain("3rd Set");

    // The defect, isolated to its own row: pull the live <li> out of the
    // markup and assert the clock is gone from IT, while the page as a whole
    // still prints times for the fixtures that really are fixtures.
    const liveRow = html.slice(
      html.indexOf(`data-match="${LIVE_KEY}"`),
      html.indexOf("</li>", html.indexOf(`data-match="${LIVE_KEY}"`))
    );
    expect(liveRow).toContain('data-testid="match-live"');
    expect(liveRow).not.toMatch(/\d{1,2}:\d{2}\s?(AM|PM)/i);
    // CONTROL: the upcoming rows kept their clocks. Without this the guard
    // passes just as well against a fix that deleted every time on the page.
    expect(html).toMatch(/\d{1,2}:\d{2}\s?(AM|PM)/i);
  });

  it("prints no scheduled sentence inside the badge", () => {
    const html = renderToStaticMarkup(
      <TournamentMatches entries={matchListFromSlate(MATCHES)} />
    );
    // The nine upcoming details are full datetimes. None of them may reach a
    // LIVE pill, on this payload or on one where ESPN flips state early.
    expect(html).not.toContain("September 1st at");
    expect(html).not.toContain("September 2nd at");
  });
});
