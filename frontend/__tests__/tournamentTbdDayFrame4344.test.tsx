// #4344 — A TBD MATCH'S DAY IS READ IN THE PLACEHOLDER'S FRAME, NOT THE READER'S.
//
// ── WHAT THE READER SAW ──────────────────────────────────────────────────────
//
// Production `/tournaments/us-open`, 390x844, anonymous, Wed 2026-09-09 ~07:05
// PT, browser in `America/Los_Angeles`. Both singles semi-finals had no
// published order of play, and both were listed A DAY EARLY:
//
//     Women's SF (Sabalenka v Pegula)   TIME TBD                 — actually Thu Sep 10
//     Men's SF   (Shelton v Tiafoe)     TOMORROW · TBD           — actually Fri Sep 11
//
// The men's contradicted our own match page, which said `Sep 11, 2026 - TBD`.
// The women's is the worse read: resolving to the reader's TODAY, the day token
// is suppressed by design, so the card said `Time TBD` — today, hour unknown —
// for a match a day away.
//
// ── THE MECHANISM ────────────────────────────────────────────────────────────
//
// A fixture with no order of play carries ESPN's midnight placeholder in the
// VENUE's timezone. Flushing Meadows is UTC-4, so Friday arrives as
// `2026-09-11T04:00:00Z`. `localDayKey` reads the calendar day in the READER's
// timezone — right for a real published start, wrong for this, because midnight
// is the one moment of the day that changes date when you carry it west. 04:00Z
// in Pacific is 9pm the PREVIOUS day.
//
// Q463 already caught half of this: it stopped printing the placeholder's HOUR
// ("a confident 12:00 AM for a match played in the afternoon"). It kept
// localising the placeholder's DATE, and the date is the half that moves.
//
// The fix reads a placeholder in UTC — the frame THE REST OF THE SYSTEM already
// reads it in. `tournament_link_resolver._as_date` takes `.date()` off the same
// string for its one-day match window and `tournament_matchup_linker` calls that
// "still the right DATE". The frontend was the only place reading it otherwise.
//
// ── WHY THIS FILE MOCKS TWO FUNCTIONS ────────────────────────────────────────
//
// THE HONEST REASON, because it decides whether this guard is worth anything:
// `jest.config.js:13` pins the whole suite to UTC, and proves it inside the
// realm (`jest.setup.timezone.js`), because a suite whose assertions drift with
// the machine's zone is worse than no suite. In UTC `localDayKey` and
// `placeholderDayKey` RETURN THE SAME STRING FOR EVERY INPUT. So a test that
// renders the card and asserts the day it prints CANNOT SEE THIS BUG — it
// passes identically before and after the fix, and would be a guard that never
// fails, which is how a defect gets marked covered.
//
// The zone cannot be moved to see it: the config comment records that assigning
// `process.env.TZ` inside a test file is a measured no-op, because jest builds
// each file's realm before `setupFiles` run and that realm's `Date` keeps the
// zone it was born with.
//
// So the render half asserts the WIRING instead — which of the two frames the
// TBD branch asks for — by giving each helper a different, recognisable answer.
// Sentinels DIFFER from each other on purpose: a single shared sentinel would
// pass whichever branch was taken and prove nothing (the #3518 trap). The frame
// itself is then pinned separately on the real function, where UTC is not a
// blindfold because the assertion names the UTC date explicitly.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import TournamentMatches from "@/components/tournament/TournamentMatches";
import { buildMatchList, type MatchListEntry } from "@/lib/matchList";
import type { SlateMatch } from "@/lib/slate";

/** Distinct rendered dates, so the html says WHICH helper the branch asked. */
const LOCAL_FRAME_SENTINEL = "2031-01-02"; // renders "Thursday, Jan 2"
const PLACEHOLDER_FRAME_SENTINEL = "2032-03-04"; // renders "Thursday, Mar 4"

jest.mock("@/lib/slate", () => ({
  ...jest.requireActual("@/lib/slate"),
  localDayKey: jest.fn(() => LOCAL_FRAME_SENTINEL),
  placeholderDayKey: jest.fn(() => PLACEHOLDER_FRAME_SENTINEL),
}));

/* The real functions, reached past this file's own mock. */
const actualSlate = jest.requireActual("@/lib/slate") as {
  localDayKey: (s: string) => string;
  placeholderDayKey: (s: string) => string;
};

/**
 * THE TWO LIVE SPECIMENS, verbatim from `GET /api/tournaments/us-open` at
 * 2026-09-09 13:4xZ — the rows that were on the reader's screen, not a shape
 * invented to suit the assertion.
 */
const MENS_SF_PLACEHOLDER = "2026-09-11T04:00:00+00:00";
const WOMENS_SF_PLACEHOLDER = "2026-09-10T04:00:00+00:00";
/** The control from the SAME payload: a real published start, `tbd=false`. */
const MENS_QF_REAL_START = "2026-09-09T18:00:00+00:00";

function slateRow(over: Partial<SlateMatch> & { scheduled_date: string }): SlateMatch {
  return {
    matchup_key: `key-${over.scheduled_date}-${over.start_is_tbd ? "tbd" : "real"}`,
    draw: "mens-singles",
    draw_label: "Men's Singles",
    round: "SF",
    priced: true,
    live_state: "upcoming",
    status_detail: null,
    sides: [
      { entity_key: "espn:athlete:1", display_name: "Ben Shelton", probability: 0.725 },
      { entity_key: "espn:athlete:2", display_name: "Frances Tiafoe", probability: 0.275 },
    ],
    ...over,
  } as SlateMatch;
}

function render(entries: MatchListEntry[]): string {
  return renderToStaticMarkup(<TournamentMatches entries={entries} />);
}

function cardFor(scheduled: string, startIsTbd: boolean): string {
  return render(
    buildMatchList({ slate: [slateRow({ scheduled_date: scheduled, start_is_tbd: startIsTbd })] })
  );
}

describe("#4344 the frame: placeholderDayKey reads the placeholder's own date", () => {
  it("names the day the venue meant for both live specimens", () => {
    // 04:00Z is midnight at UTC-4. The date the venue meant is the UTC date,
    // and it is the date the backend resolver already compares.
    expect(actualSlate.placeholderDayKey(MENS_SF_PLACEHOLDER)).toBe("2026-09-11");
    expect(actualSlate.placeholderDayKey(WOMENS_SF_PLACEHOLDER)).toBe("2026-09-10");
  });

  it("is a UTC READING of the instant, not a slice of the string", () => {
    // The cheapest wrong implementation — `scheduled.slice(0, 10)` — agrees
    // with the two rows above and disagrees here: this instant is
    // 2026-09-11T04:30Z, so the placeholder's date is the 11th while the
    // string starts "2026-09-10". Routed here so that mutant cannot survive.
    expect(actualSlate.placeholderDayKey("2026-09-10T23:30:00-05:00")).toBe("2026-09-11");
  });

  it("falls back rather than throwing on an unparseable date", () => {
    // Total, like every other formatter on this page: one bad row must not
    // take the tab down.
    expect(actualSlate.placeholderDayKey("nope")).toBe("nope");
  });

  it("CONTROL — the two frames agree under this suite's UTC realm", () => {
    // Stated so the next reader does not mistake the render assertions below
    // for date assertions. This equality is exactly why they cannot be.
    expect(actualSlate.localDayKey(MENS_SF_PLACEHOLDER)).toBe(
      actualSlate.placeholderDayKey(MENS_SF_PLACEHOLDER)
    );
  });
});

describe("#4344 the wiring: which frame each branch asks for", () => {
  it("a TBD row asks the PLACEHOLDER frame", () => {
    const html = cardFor(MENS_SF_PLACEHOLDER, true);
    expect(html).toContain("Mar 4");
    expect(html).toContain("TBD");
    // The defect itself: before the fix this row read the local frame.
    expect(html).not.toContain("Jan 2");
  });

  it("CONTROL — a row with a real published start still asks the READER's frame", () => {
    // The ship must not be paid for by localising less. A published start is
    // an instant, and the reader's timezone is the right answer for it.
    const html = cardFor(MENS_QF_REAL_START, false);
    expect(html).toContain("Jan 2");
    expect(html).not.toContain("Mar 4");
    expect(html).not.toContain("TBD");
  });

  it("the women's specimen takes the same branch as the men's", () => {
    // Both SFs were wrong by one day; a fix that only reached the row with a
    // day token would leave the bare `Time TBD` one standing.
    const html = cardFor(WOMENS_SF_PLACEHOLDER, true);
    expect(html).toContain("Mar 4");
    expect(html).not.toContain("Jan 2");
  });
});
