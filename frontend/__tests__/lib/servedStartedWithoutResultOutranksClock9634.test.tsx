// #9634 — THE SERVED `started_without_result` OUTRANKS THE CLOCK.
//
// `/events/15320754` (Bublik / Shang v Cerundolo / Rinderknech, China Open
// doubles) served `status: scheduled, started_without_result: false` on
// 2026-09-29: its venue stamp was hours past, but StatPal has it at 02:00Z and
// live's #9613 holds it. The web recomputed the answer from the clock alone
// (`commence_time < now − 2h`) and the hero read "No result reported".
//
// Every arm is asserted BOTH ways (gotcha #43): the same row with the key
// ABSENT must still read "No result reported" — the feed, search and league
// envelopes do not carry the key, and dropping the clock there would put a
// start time back on #3211's fixtures. Clock pinned by offset (#44).

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
import {
  eventSectionKey,
  hasNoReportedResult,
  serverHeldPastKickoff,
  startBadgeLabel,
  startedWithoutResult,
  SUSPENDED_LABEL,
  UPCOMING_GRACE_MS,
} from "@/lib/eventState";
import { hasNoReportedResultForShare } from "@/lib/eventShareMeta";
import type { Event } from "@/lib/types";
import * as fs from "fs";
import * as path from "path";

const HOUR = 3600_000;
const NOW = Date.parse("2026-09-29T15:50:00Z");
// 13h past its venue stamp — the specimen's shape, far outside the grace.
const STAMP = new Date(NOW - 13 * HOUR).toISOString();
const INSIDE_GRACE = new Date(NOW - (UPCOMING_GRACE_MS - 10 * 60_000)).toISOString();

describe("#9634 · startedWithoutResult prefers the served key", () => {
  it("served false wins over a run-out clock; absent falls back to the clock", () => {
    expect(startedWithoutResult("scheduled", STAMP, NOW, false)).toBe(false);
    expect(startedWithoutResult("scheduled", STAMP, NOW)).toBe(true);
    expect(startedWithoutResult("scheduled", STAMP, NOW, undefined)).toBe(true);
    expect(startedWithoutResult("scheduled", STAMP, NOW, null)).toBe(true);
  });

  it("served true wins over a clock still inside the grace", () => {
    expect(startedWithoutResult("scheduled", INSIDE_GRACE, NOW, true)).toBe(true);
    expect(startedWithoutResult("scheduled", INSIDE_GRACE, NOW)).toBe(false);
  });

  it("the status gate still runs first — a stray true on another status reads nothing", () => {
    for (const status of ["live", "completed", "closed", "suspended", null]) {
      expect(startedWithoutResult(status, STAMP, NOW, true)).toBe(false);
    }
  });
});

describe("#9634 · hasNoReportedResult", () => {
  it("threads the served key through its scheduled arm", () => {
    expect(hasNoReportedResult("scheduled", STAMP, NOW, false)).toBe(false);
    expect(hasNoReportedResult("scheduled", STAMP, NOW)).toBe(true);
  });

  it("leaves the suspended arm alone — served false cannot un-suspend a row", () => {
    expect(hasNoReportedResult("suspended", STAMP, NOW, false)).toBe(true);
  });
});

describe("#9634 · eventSectionKey buckets on the same answer the card prints", () => {
  it("a held row files under upcoming, not the live bucket", () => {
    expect(eventSectionKey("scheduled", STAMP, NOW, { started_without_result: false })).toBe(
      "upcoming",
    );
    expect(eventSectionKey("scheduled", STAMP, NOW, {})).toBe("live");
    expect(eventSectionKey("scheduled", STAMP, NOW)).toBe("live");
  });
});

describe("#9634 · the share preview reads the served key", () => {
  it("a held row does not unfurl as no-result", () => {
    const row = { status: "scheduled", commence_time: STAMP };
    expect(hasNoReportedResultForShare({ ...row, started_without_result: false }, NOW)).toBe(
      false,
    );
    expect(hasNoReportedResultForShare(row, NOW)).toBe(true);
  });
});

// The card reads `Date.now()` itself, so its fixture is an offset from the
// real clock rather than from NOW.
function makeEvent(over: Partial<Event> = {}): Event {
  return {
    id: 15320754,
    external_id: "evt-15320754",
    sport: "tennis_atp",
    sport_name: "ATP",
    home_team: "Cerundolo / Rinderknech",
    away_team: "Bublik / Shang",
    commence_time: new Date(Date.now() - 13 * HOUR).toISOString(),
    status: "scheduled",
    home_score: null,
    away_score: null,
    current_odds: {
      captured_at: new Date(Date.now() - HOUR).toISOString(),
      home_probability: 0.55,
      away_probability: 0.45,
      spread: null,
      over_under: null,
    },
    ...over,
  } as unknown as Event;
}

function text(event: Event): string {
  return renderToStaticMarkup(<EventCard event={event} />)
    .replace(/<[^>]*>/g, " ")
    .replace(/\s+/g, " ");
}

describe("#9634 · EventCard, rendered", () => {
  it("a held row served false prints no 'No result reported'", () => {
    expect(text(makeEvent({ started_without_result: false }))).not.toContain(SUSPENDED_LABEL);
  });

  it("CONTROL: the same row with the key absent still prints it", () => {
    expect(text(makeEvent())).toContain(SUSPENDED_LABEL);
  });
});

// Taking the row out of "No result reported" drops it to the badge that speaks
// about the START. Without the held clause that badge said "Started" — the
// server had just told us it had not.
describe("#9634 · the hero badge says Pregame, not Started, for a held row", () => {
  it("held = served false AND the clock alone past the grace", () => {
    expect(serverHeldPastKickoff("scheduled", STAMP, NOW, false)).toBe(true);
    // Inside the grace the server's false is the same clock — proves nothing.
    expect(serverHeldPastKickoff("scheduled", INSIDE_GRACE, NOW, false)).toBe(false);
    expect(serverHeldPastKickoff("scheduled", STAMP, NOW)).toBe(false);
    expect(serverHeldPastKickoff("scheduled", STAMP, NOW, true)).toBe(false);
    expect(serverHeldPastKickoff("live", STAMP, NOW, false)).toBe(false);
  });

  it("the badge word", () => {
    expect(startBadgeLabel(true, null, true)).toBe("Pregame");
    // #6031 unchanged: started, not held.
    expect(startBadgeLabel(true, null, false)).toBe("Started");
    expect(startBadgeLabel(true, null)).toBe("Started");
    expect(startBadgeLabel(false, "2h 10m", false)).toBe("Starts in 2h 10m");
  });

  it("the page passes the held answer to the badge (a page has no exports to call)", () => {
    const page = fs.readFileSync(
      path.join(__dirname, "../../app/events/[id]/page.tsx"),
      "utf8",
    );
    expect(page).toMatch(
      /startBadgeLabel\(\s*hasStarted,\s*gameCountdown,[\s\S]{0,200}?serverHeldPastKickoff\(\s*event\?\.status,\s*event\?\.commence_time,\s*undefined,\s*event\?\.started_without_result,(?:\s*event\?\.authority_not_started,?)?\s*\)/,
    );
  });
});
