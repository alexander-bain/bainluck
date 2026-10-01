// #9968 — A MARQUEE GAME READ "Started" FOR THE MINUTES BEFORE ITS FIRST PITCH.
//
// BOS@NYY (2026-09-30) said "Started" at 00:07Z; first pitch was ≈00:15Z. The
// listed time had passed and ESPN still read `pre`, but inside the two-hour
// grace the served `started_without_result: false` is the clock itself, so
// #9634's hold could not speak. live now serves `authority_not_started: true`
// (PR #9976) — present only when ESPN stamped "not begun" within 15 minutes.
//
// Both directions (gotcha #43): the key ABSENT — tennis, unanchored rows, ESPN
// silent — must still read #6031's "Started". Clock pinned by offset (#44).

import {
  serverHeldPastKickoff,
  startBadgeLabel,
  UPCOMING_GRACE_MS,
} from "@/lib/eventState";
import * as fs from "fs";
import * as path from "path";

const NOW = Date.parse("2026-10-01T00:07:00Z");
// Eight minutes past the listed 23:59Z-ish start — deep inside the grace.
const JUST_PASSED = new Date(NOW - 8 * 60_000).toISOString();
const PAST_GRACE = new Date(NOW - UPCOMING_GRACE_MS - 60 * 60_000).toISOString();

describe("#9968 · authority_not_started holds the row inside the grace", () => {
  it("served true on a scheduled row is held", () => {
    expect(serverHeldPastKickoff("scheduled", JUST_PASSED, NOW, false, true)).toBe(true);
    // The served false is still the clock here — it alone proves nothing.
    expect(serverHeldPastKickoff("scheduled", JUST_PASSED, NOW, false)).toBe(false);
  });

  it("CONTROL: absent / null / false keeps the old answer", () => {
    for (const key of [undefined, null, false]) {
      expect(serverHeldPastKickoff("scheduled", JUST_PASSED, NOW, false, key)).toBe(false);
      expect(serverHeldPastKickoff("scheduled", JUST_PASSED, NOW, undefined, key)).toBe(false);
    }
  });

  it("a stray true on a row that left `scheduled` holds nothing", () => {
    for (const status of ["live", "completed", "closed", "suspended", null]) {
      expect(serverHeldPastKickoff(status, JUST_PASSED, NOW, false, true)).toBe(false);
    }
  });

  it("past the grace it agrees with #9634's hold rather than replacing it", () => {
    expect(serverHeldPastKickoff("scheduled", PAST_GRACE, NOW, false, true)).toBe(true);
    expect(serverHeldPastKickoff("scheduled", PAST_GRACE, NOW, false)).toBe(true);
  });
});

describe("#9968 · the hero badge word", () => {
  it("started on the clock, held by ESPN: Pregame, not Started", () => {
    const held = serverHeldPastKickoff("scheduled", JUST_PASSED, NOW, false, true);
    expect(startBadgeLabel(true, null, held)).toBe("Pregame");
  });

  it("CONTROL: the same row without the key still says Started (#6031)", () => {
    const held = serverHeldPastKickoff("scheduled", JUST_PASSED, NOW, false);
    expect(startBadgeLabel(true, null, held)).toBe("Started");
  });

  it("the page passes the payload key to the hold (a page has no exports to call)", () => {
    const page = fs.readFileSync(
      path.join(__dirname, "../../app/events/[id]/page.tsx"),
      "utf8",
    );
    expect(page).toMatch(
      /serverHeldPastKickoff\(\s*event\?\.status,\s*event\?\.commence_time,\s*undefined,\s*event\?\.started_without_result,\s*event\?\.authority_not_started,?\s*\)/,
    );
  });
});
