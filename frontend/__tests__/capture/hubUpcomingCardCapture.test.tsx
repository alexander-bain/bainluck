/**
 * UX-P178 — THE US OPEN STOPS CLAIMING IT STARTS IN TWO WEEKS WHILE SHOWING A
 * LIVE DOT.
 *
 * ═══ WHAT A PERSON SAW ═══
 *
 * `bainluck.com/hub/tennis`, measured live 2026-08-29. The upcoming rail's
 * third card:
 *
 *     ● LIVE                                    (pulsing red dot, no chip)
 *     2026 Women's US Open Winner (Tennis)
 *     Sat, Sep 12
 *
 * Three things are wrong with three lines.
 *
 *  1. **No "★ Marquee" chip.** `is_major` was hardcoded `false` at both tennis
 *     concept sites, so the chip could never render for a Grand Slam. Measured
 *     the same day across every hub: **0 of 48** upcoming cards carried it
 *     (mma 15, boxing 17, golf 4, tennis 12, esports 0). The chip had never
 *     rendered anywhere in production.
 *
 *  2. **A future date under a LIVE pill.** The rail served the winner market's
 *     `resolution_date` — when the tournament ENDS — under the key
 *     `start_date`. Four tennis cards read LIVE with a start date days away.
 *
 *  3. **And the date was a day early anyway.** `formatDate` called
 *     `toLocaleDateString` with no `timeZone`, so a midnight-UTC instant moved
 *     back a day for every reader west of Greenwich:
 *     `2026-09-13T00:00:00+00:00` renders "Sat, Sep 12" in Los Angeles and
 *     "Sun, Sep 13" in UTC. CI runs `TZ=UTC` and could not see it.
 *
 * ═══ WHY THE DATE WAS MISLABELLED, AND HOW WE KNOW ═══
 *
 * The detail page one click away — `/event/tennis/2026-women-s-us-open-winner-tennis`,
 * built by `TennisEventAdapter.build_event` — served that IDENTICAL timestamp as
 * `end_date`, with `start_date: null`. Two layers, one `winner.resolution_date`,
 * opposite names. The adapter's reading is the correct one, so the rail adopted
 * it. That agreement is asserted on one payload driven through both real code
 * paths in `backend/tests/test_event_tennis_identity.py`
 * (`TestTheRailAndTheDetailPageAgreeAboutOneTimestamp`) — this file does not
 * re-prove it, because it is not this component's bug.
 *
 * Tennis was also the only one of the four hub listers doing it: ufc and boxing
 * serve `latest_commence`, golf serves `start_date or commence_time` — all
 * genuine starts. Which is why the mma control below must not move.
 *
 * ═══ THE READER COUNT ═══
 *
 * `/hub/tennis` upcoming rail, live 2026-08-29: 12 cards, 0 marquee, 9 carrying
 * a date, 4 of those under a LIVE pill. Two of the 12 are Grand Slams today; the
 * four slams × two draws means 8 concepts a year pass through this rail and none
 * could ever be flagged. The defect is DETERMINISTIC — every card, every load —
 * so the fixture is the instrument, not Sentry.
 *
 * ═══ WHAT THE FIXTURES ARE ═══
 *
 * `uxp178_hub_tennis_before.json` and `uxp178_hub_mma_control.json` are verbatim
 * production `/api/hub/*` `upcoming` rails from that measurement. The tennis one
 * is the BROKEN payload — every card `is_major: false`, resolution dates sitting
 * in `start_date`. It is used to prove the render was wrong given what the
 * backend actually sent, and the AFTER cases re-shape it exactly as the fixed
 * backend now does.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { UpcomingCard, formatDate } from "@/components/hub/UpcomingCard";
import type { HubUpcoming } from "@/lib/api";

import tennisBefore from "../fixtures/uxp178_hub_tennis_before.json";
import mmaControl from "../fixtures/uxp178_hub_mma_control.json";

/** Render the SHIPPED card to markup. */
function render(card: HubUpcoming): string {
  return renderToStaticMarkup(React.createElement(UpcomingCard, { card }));
}

/** Strip tags so assertions read what a PERSON reads. `renderToStaticMarkup`
 *  escapes entities, so the curly apostrophes in market names come back as
 *  `&#x27;`-style refs and have to be put back before matching. */
function visibleText(markup: string): string {
  return markup
    .replace(/<[^>]*>/g, " ")
    .replace(/&#x27;|&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/&#x2605;/g, "\u2605")
    .replace(/\s+/g, " ")
    .trim();
}

function href(markup: string): string {
  return markup.match(/href="([^"]*)"/)?.[1] ?? "";
}

const TENNIS_BEFORE = tennisBefore.upcoming as HubUpcoming[];
const MMA_CONTROL = mmaControl.upcoming as HubUpcoming[];

/** The production US Open card, exactly as the rail served it before the fix. */
const US_OPEN_BEFORE = TENNIS_BEFORE.find((c) =>
  c.name.includes("Women’s US Open"),
)!;

/** The same concept as the FIXED backend now serves it. */
const US_OPEN_AFTER: HubUpcoming = {
  ...US_OPEN_BEFORE,
  is_major: true,
  start_date: null,
  end_date: US_OPEN_BEFORE.start_date,
};

describe("UX-P178 — the fixture is a real broken payload, not a strawman", () => {
  it("the production rail really did flag nothing marquee", () => {
    expect(TENNIS_BEFORE).toHaveLength(12);
    expect(TENNIS_BEFORE.filter((c) => c.is_major)).toHaveLength(0);
  });

  it("the production rail really did put an END date in start_date", () => {
    expect(US_OPEN_BEFORE.start_date).toBe("2026-09-13T00:00:00+00:00");
    expect(US_OPEN_BEFORE.status).toBe("live");
  });

  it("four cards claimed LIVE with a date still ahead of them", () => {
    const measuredAt = new Date("2026-08-29T00:00:00Z");
    const contradictory = TENNIS_BEFORE.filter(
      (c) => c.status === "live" && c.start_date && new Date(c.start_date) > measuredAt,
    );
    expect(contradictory).toHaveLength(4);
  });
});

describe("UX-P178 — BEFORE: what that payload rendered", () => {
  it("no marquee chip on a Grand Slam", () => {
    expect(visibleText(render(US_OPEN_BEFORE))).not.toMatch(/Marquee/);
  });

  it("an unlabelled future date under a LIVE pill", () => {
    const text = visibleText(render(US_OPEN_BEFORE));
    expect(text).toContain("Live");
    // Bare — nothing tells the reader this is when the tournament ENDS.
    expect(text).toContain("Sun, Sep 13");
    expect(text).not.toMatch(/Ends/);
  });
});

describe("UX-P178 — AFTER: the shipped card on the fixed payload", () => {
  it("the Grand Slam is marquee", () => {
    expect(visibleText(render(US_OPEN_AFTER))).toContain("★ Marquee");
  });

  it("the date says what it is", () => {
    expect(visibleText(render(US_OPEN_AFTER))).toContain("Ends Sun, Sep 13");
  });

  it("LIVE and a labelled end date no longer contradict each other", () => {
    const text = visibleText(render(US_OPEN_AFTER));
    expect(text).toContain("Live");
    expect(text).toContain("Ends Sun, Sep 13");
  });

  it("still links to the concept it names", () => {
    const h = href(render(US_OPEN_AFTER));
    expect(h).toBe("/event/tennis/2026-women-s-us-open-winner-tennis");
    expect(h).not.toContain("undefined");
  });

  it("an ordinary tournament stays plain", () => {
    const wta = TENNIS_BEFORE.find((c) => c.name === "WTA Cincinnati Winner")!;
    const text = visibleText(render({ ...wta, start_date: null, end_date: null }));
    expect(text).not.toMatch(/Marquee/);
    expect(text).toContain("TBD");
  });
});

describe("UX-P178 — the date is the date the data states, in every timezone", () => {
  /**
   * ⚠️ NOT an in-process `process.env.TZ` swap — jest has already warmed V8's
   * zone cache by the time a test body runs, so that proves nothing. These
   * assert a FIXED LITERAL, and the mutation harness runs the whole file under
   * both `TZ=UTC` and `TZ=America/Los_Angeles`. Under the old un-pinned
   * `formatDate` the LA run rendered "Sat, Sep 12" and went red here.
   */
  it("midnight UTC renders as its own day, not the day before", () => {
    expect(formatDate("2026-09-13T00:00:00+00:00")).toBe("Sun, Sep 13");
  });

  it("the rendered card agrees", () => {
    expect(visibleText(render(US_OPEN_AFTER))).toContain("Ends Sun, Sep 13");
  });

  it("an absent date is absent, not epoch", () => {
    expect(formatDate(null)).toBe("");
    expect(formatDate(undefined)).toBe("");
    expect(formatDate("not a date")).toBe("");
  });
});

describe("UX-P178 — CONTROL: the domains that already knew their start date", () => {
  /**
   * This is the half that matters most. ufc/boxing/golf serve a GENUINE start,
   * and a "fix" that relabels every hub card "Ends …" would pass every assertion
   * above while breaking three hubs. These cards must render exactly as before.
   */
  it("the control fixture is a real rail with real start dates", () => {
    expect(MMA_CONTROL).toHaveLength(15);
    expect(MMA_CONTROL.every((c) => c.start_date)).toBe(true);
    expect(MMA_CONTROL.every((c) => c.end_date === undefined)).toBe(true);
  });

  it("a combat card still prints its start date bare", () => {
    const card = MMA_CONTROL[0];
    const text = visibleText(render(card));
    expect(text).toContain(formatDate(card.start_date));
    expect(text).not.toMatch(/Ends/);
  });

  it("no control card gains an 'Ends' label, and none loses its date", () => {
    for (const card of MMA_CONTROL) {
      const text = visibleText(render(card));
      expect(text).not.toMatch(/Ends/);
      expect(text).not.toMatch(/TBD/);
    }
  });

  it("a start date always wins over an end date", () => {
    // Belt and braces: if a domain ever serves both, the start is what a fixture
    // card means by a date, and the end must not shadow it.
    const text = visibleText(
      render({
        ...MMA_CONTROL[0],
        start_date: "2026-07-11T23:00:00+00:00",
        end_date: "2026-09-13T00:00:00+00:00",
      }),
    );
    expect(text).toContain("Sat, Jul 11");
    expect(text).not.toMatch(/Ends/);
  });

  it("the fight count still renders", () => {
    const withFights = MMA_CONTROL.find((c) => (c.fight_count ?? 0) > 0)!;
    expect(visibleText(render(withFights))).toContain(`${withFights.fight_count} fights`);
  });
});
