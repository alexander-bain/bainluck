/**
 * #11182 — A SUSPENDED FIXTURE IS NOT A PLAYED 0-0.
 *
 * ═══ WHAT A READER SAW ═══
 *
 * Production 2026-10-17 13:44Z, `https://www.bainluck.com/futures/199045`
 * (MLB: 2026 American League Champion) at 390px, "Games This Week":
 *
 *     Fri 5:00 PM   Tampa Bay Rays 0 - 0 Cleveland Guardians
 *
 * listed below "Today 5:00 PM" and "Tomorrow 2:00 PM" rows for the same two
 * teams, with no state word. The stored row (`/api/events/15330795`) is
 * `suspended`, commence 2026-10-17T00:00Z, home 0 / away 0, no
 * `status_detail`. The row knew live, completed and closed; every other status
 * got a start time, and any two non-null scores were drawn.
 *
 * ═══ WHAT THIS FILE PINS ═══
 *
 * The specimen reads `No result reported` (the shared `SUSPENDED_LABEL`) with
 * its fixture as `Away at Home`. No start time, no 0-0. Around it are the
 * states that must NOT move: a live 0-0 and a final 0-0 are real scores, a
 * suspended 2-1 keeps its last score, and a scheduled row's pre-game 0-0 is
 * filler. The fixture link, the market's per-team odds, duel and settled
 * withholding, and #7416's phone-width gutter are unchanged.
 *
 * The clock is injected (`now`), never read (gotcha #44).
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import GamesThisWeek, { RelatedEventRow } from "@/components/futures/GamesThisWeek";
import { SUSPENDED_DESCRIPTION, SUSPENDED_LABEL } from "@/lib/eventState";
import type { EventStatus, RelatedEvent } from "@/lib/types";

/** When the screenshot was taken. */
const NOW = Date.parse("2026-10-17T13:44:00Z");
const HOUR = 60 * 60 * 1000;

/**
 * Status, scores, commence, teams and id are the stored row from the issue.
 * The two prices are illustrative (CLE 0.624 is the Polymarket read the
 * issue quotes, TB its complement); no assertion depends on their values.
 */
const SPECIMEN: RelatedEvent = {
  event_id: 15330795,
  home_team: "Cleveland Guardians",
  away_team: "Tampa Bay Rays",
  commence_time: "2026-10-17T00:00:00+00:00",
  status: "suspended",
  sport: "baseball_mlb",
  home_score: 0,
  away_score: 0,
  linked_teams: [
    {
      side: "home",
      team_name: "Cleveland Guardians",
      outcome_name: "Cleveland Guardians",
      probability: 0.624,
      american_odds: -166,
      rank: 1,
    },
    {
      side: "away",
      team_name: "Tampa Bay Rays",
      outcome_name: "Tampa Bay Rays",
      probability: 0.376,
      american_odds: 166,
      rank: 2,
    },
  ],
};

function row(over: Partial<RelatedEvent>): RelatedEvent {
  return { ...SPECIMEN, ...over };
}

function markup(event: RelatedEvent, showOdds = true): string {
  return renderToStaticMarkup(
    <RelatedEventRow event={event} showOdds={showOdds} now={NOW} />,
  );
}

/** Visible text only, tags stripped, whitespace collapsed. */
function text(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();
}

/** The score span, if the row drew one: `<a> - <b>` in its own element. */
function drawnScore(html: string): string | null {
  const m = text(html).match(/(\d+) - (\d+)/);
  return m ? `${m[1]} - ${m[2]}` : null;
}

describe("#11182 the reported suspended row", () => {
  const html = markup(SPECIMEN);
  const t = text(html);

  it("does not draw the 0-0 placeholder as a scoreline", () => {
    expect(drawnScore(html)).toBeNull();
  });

  it("names its state with the shared no-result label, not a start time", () => {
    expect(t).toContain(SUSPENDED_LABEL);
    // The old row printed the commence as a weekday time ("Fri 8:00 PM" in UTC).
    expect(t).not.toMatch(/\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun|Today|Tomorrow)\b/);
    expect(t).not.toMatch(/\d{1,2}:\d{2}\s?(AM|PM)/);
  });

  it("invents no other state: no Final, Live, Postponed or Suspended", () => {
    expect(t).not.toMatch(/\bfinal\b/i);
    expect(t).not.toMatch(/\blive\b/i);
    expect(t).not.toMatch(/postpon/i);
    expect(t).not.toMatch(/\bsuspended\b/i);
  });

  it("carries the longer sentence on the badge's title, not the page body", () => {
    expect(html).toContain(`title="${SUSPENDED_DESCRIPTION}"`);
  });

  it("keeps the fixture, its link and the market's per-team odds", () => {
    expect(t).toContain("Tampa Bay Rays at Cleveland Guardians");
    expect(html).toContain('href="/events/15330795"');
    expect(t).toContain("62%");
    expect(t).toContain("38%");
  });

  it("bolds no side, because nothing reported an end", () => {
    expect(html).not.toContain("font-semibold\">Tampa Bay Rays");
    expect(html).not.toContain("font-semibold\">Cleveland Guardians");
  });

  it("keeps #7416's phone-width gutter (sm:w-16, never a bare w-16)", () => {
    const gutter = html.match(/<div class="([^"]*sm:w-16[^"]*)"/);
    expect(gutter).not.toBeNull();
    expect(gutter![1].split(/\s+/)).not.toContain("w-16");
  });
});

describe("#11182 sibling states keep their honest scores", () => {
  it("live 0-0 is a real score and still draws", () => {
    const html = markup(row({ status: "live" }));
    expect(drawnScore(html)).toBe("0 - 0");
    expect(text(html)).toContain("LIVE");
    expect(text(html)).not.toContain(SUSPENDED_LABEL);
  });

  it("final 0-0 is a real score and still draws", () => {
    for (const status of ["completed", "closed"] as const) {
      const html = markup(row({ status }));
      expect(drawnScore(html)).toBe("0 - 0");
      expect(text(html)).toContain("FINAL");
      expect(text(html)).not.toContain(SUSPENDED_LABEL);
    }
  });

  it("a final still bolds its winner", () => {
    const html = markup(row({ status: "completed", away_score: 3, home_score: 1 }));
    expect(html).toContain("font-semibold\">Tampa Bay Rays");
  });

  it("a suspended row with play keeps its last score beside the badge, no winner bolded", () => {
    const html = markup(row({ away_score: 2, home_score: 1 }));
    expect(drawnScore(html)).toBe("2 - 1");
    expect(text(html)).toContain(SUSPENDED_LABEL);
    expect(html).not.toContain("font-semibold\">Tampa Bay Rays");
  });

  it("a suspended row with one side scored keeps that observation too", () => {
    const html = markup(row({ away_score: 0, home_score: 1 }));
    expect(drawnScore(html)).toBe("0 - 1");
  });

  it("a suspended row with no scores reads the label over the fixture", () => {
    const html = markup(row({ away_score: null, home_score: null }));
    expect(drawnScore(html)).toBeNull();
    expect(text(html)).toContain(SUSPENDED_LABEL);
    expect(text(html)).toContain("Tampa Bay Rays at Cleveland Guardians");
  });
});

describe("#11182 placeholder scores never masquerade as results", () => {
  const upcoming = new Date(NOW + 3 * HOUR).toISOString();

  it("a scheduled row's pre-game 0-0 is not drawn; its start time is", () => {
    const html = markup(row({ status: "scheduled", commence_time: upcoming }));
    expect(drawnScore(html)).toBeNull();
    expect(text(html)).toContain("Today");
    expect(text(html)).toContain("Tampa Bay Rays at Cleveland Guardians");
    expect(text(html)).not.toContain(SUSPENDED_LABEL);
  });

  it("a scheduled row long past its start with no result reads the shared label", () => {
    const stale = new Date(NOW - 5 * HOUR).toISOString();
    const html = markup(row({ status: "scheduled", commence_time: stale }));
    expect(drawnScore(html)).toBeNull();
    expect(text(html)).toContain(SUSPENDED_LABEL);
  });

  it("a status this row has no reading for draws no score, even a non-zero one", () => {
    const html = markup(
      row({
        status: "postponed" as EventStatus,
        commence_time: upcoming,
        away_score: 3,
        home_score: 2,
      }),
    );
    expect(drawnScore(html)).toBeNull();
    expect(text(html)).not.toMatch(/\bfinal\b/i);
  });
});

describe("#11182 the section's withholding is unchanged", () => {
  it("a duel's rows print no price and no caption around the specimen", () => {
    const html = renderToStaticMarkup(
      <GamesThisWeek events={[SPECIMEN]} marketIsDuel />,
    );
    expect(text(html)).toContain(SUSPENDED_LABEL);
    expect(text(html)).not.toMatch(/\d+%/);
    expect(text(html)).not.toContain("odds in this market");
  });

  it("a settled market withholds the whole section", () => {
    expect(
      renderToStaticMarkup(<GamesThisWeek events={[SPECIMEN]} marketResolved />),
    ).toBe("");
  });
});
