/**
 * #6722 — A FLOOR ON THE TABLE IS A FLOOR ON THE WIDEST CELL.
 *
 * At 390px `bainluck.com/sport/soccer/ucl` showed 36 clubs as pale bars with no
 * column header and no percentages: `#` · `Team` · nothing. The payload was
 * healthy (36 rows, Barcelona 16.8%, column label `Champion`) and the same page
 * at 1280px rendered correctly, so this was render only.
 *
 * ═══ THE MECHANISM, BECAUSE THE OBVIOUS READING PRODUCES THE WRONG FIX ═══
 *
 * The filing read it as "the single-column case keeps the wide Team column and
 * pushes its one data column past the right edge". The symptom is exactly that.
 * The cause is one step further back, and it decides the fix.
 *
 * The table carried `min-w-[500px]` inside a 350px scroller. `table-layout:
 * auto` distributes a table's SURPLUS width — the excess of its used width over
 * its content's width — across columns in proportion to their existing widths.
 * The sticky Team column is always the widest, so it takes the lion's share.
 * Measured on production 2026-09-17 at 390px (scroller clientW=350, edge=370):
 *
 *     grid  cols  tableW  Team   first data col  row-1 numbers the reader sees
 *     nfl    4     542    148px  x=199           2 of 4
 *     epl    3     500    182px  x=242           1 of 3
 *     mls    2     500    211px  x=271           1 of 2
 *     ucl    1     500    285px  x=345           0 of 1
 *
 * Team's NATURAL width is 148px. Every pixel above that is surplus the floor
 * manufactured, and the fewer data columns there are to share it, the more of
 * it lands on Team: +34 at three columns, +63 at two, +137 at one. NFL, whose
 * content genuinely needs 542px, has no surplus at all and shows Team at its
 * natural 148 — which is why four-column grids never exhibited this.
 *
 * 🔴 TWO CANDIDATE FIXES LOOKED EQUIVALENT AND WERE NOT. Measuring both against
 * live production content is what separated them:
 *
 *   A. `w-max min-w-full` (width:max-content). Repairs UCL identically — and
 *      makes NFL 9px WIDER (542 -> 551), because `max-content` stops compressing
 *      the rank column (23px -> its declared `w-8`), which pushed NFL's
 *      `Division` header off the edge. A repair that regressed a working grid.
 *   B. delete the floor, keep `w-full`. Repairs UCL identically and leaves NFL
 *      BYTE-IDENTICAL in every measured field.
 *
 * B is what shipped. "No grid can get wider by construction" was my own claim
 * about A and the measurement refuted it; this comment exists so nobody
 * re-derives A from the same plausible reasoning.
 *
 * ═══ THE FLOOR WAS NEVER STOPPING COLUMNS CRAMPING ═══
 *
 * That is the argument a future reader will reach for when re-adding it. Auto
 * layout cannot shrink a table below its min-content width, so the floor is
 * inert exactly when it would be needed: NFL measures 542px at BOTH 320px and
 * 390px, with the floor and without it. Removing it is a no-op wherever the
 * content already needs 500px and a repair wherever it does not — overflow at
 * 390px went ucl 166->0, mls 166->17, epl 166->69, nfl 208->208. At 1280px the
 * floor never bound and nothing moved.
 *
 * ═══ WHAT THIS SUITE CAN AND CANNOT PROVE ═══
 *
 * jsdom has no layout: `getBoundingClientRect`, `scrollWidth` and `clientWidth`
 * are all 0, so the geometry above cannot be re-measured here and asserting it
 * would be a guard that never ran. The visible-state proof is the production
 * before/after on the issue. What is provable without a browser is the thing
 * that would actually regress — a fixed pixel floor returning to this table —
 * plus the one content cap the whole "Team's natural width is 148px" argument
 * rests on.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

jest.mock("@/hooks/useAnalytics", () => ({
  useAnalytics: () => ({ track: () => {} }),
}));

import TournamentProgressionTable from "@/components/TournamentProgressionTable";
import type { ProgressionResponse } from "../../lib/types";

/**
 * Any fixed pixel floor, not merely the 500px one that was there. Re-adding
 * `min-w-[480px]` would reproduce this defect a hair less severely, and a guard
 * that only knows the old literal would pass on it.
 */
const FIXED_PX_FLOOR = /min-w-\[\d+(?:\.\d+)?px\]/;

/** The UCL shape: one data column, which is the case that broke. */
function singleColumnGrid(): ProgressionResponse {
  return {
    sport: "soccer",
    tournament_name: "Champions League 2026-27",
    stages: [
      { key: "championship", label: "Champion", order: 0, market_id: null, market_name: null, resolved: false },
    ],
    participants: [
      ["Barcelona", 0.168],
      ["Arsenal", 0.121],
      ["Viking FK", 0.008],
    ].map(([name, p]) => ({
      name: name as string,
      team_id: null,
      logo_url: null,
      primary_color: null,
      conference: null,
      region: null,
      seed: null,
      record: null,
      probabilities: { championship: p as number },
      changes_24h: {},
      status: {},
      sources_data: {},
    })),
  };
}

/** The NFL shape: four data columns, the case that must not move. */
function fourColumnGrid(): ProgressionResponse {
  const keys = ["make_playoffs", "division", "conference", "super_bowl"];
  return {
    sport: "americanfootball_nfl",
    tournament_name: "NFL 2026",
    stages: keys.map((key, order) => ({
      key,
      label: key,
      order,
      market_id: null,
      market_name: null,
      resolved: false,
    })),
    participants: [
      {
        name: "Philadelphia Eagles",
        team_id: null,
        logo_url: null,
        primary_color: null,
        conference: null,
        region: null,
        seed: null,
        record: null,
        probabilities: Object.fromEntries(keys.map((k, i) => [k, 0.75 - i * 0.2])),
        changes_24h: {},
        status: {},
        sources_data: {},
      },
    ],
  };
}

function tableTag(data: ProgressionResponse): string {
  const html = renderToStaticMarkup(<TournamentProgressionTable data={data} pageType="league" />);
  const match = html.match(/<table[^>]*>/);
  if (match === null) throw new Error("the component rendered no <table> at all");
  return match[0];
}

describe("#6722 — the progression table declares no fixed pixel width floor", () => {
  it("the matcher fires on a floor, so a clean result means something", () => {
    // 🔴 THE ANTI-VACUITY CONTROL, and the reason it is the first test in the
    // file. Every assertion below is a `not.toMatch`. If `FIXED_PX_FLOOR` were
    // wrong — a stray escape, the wrong bracket — all of them would pass on a
    // table that had the floor back, and the suite would be decoration. This
    // pins the regex against the exact string that shipped the defect.
    expect('<table class="w-full border-collapse text-sm min-w-[500px]">').toMatch(FIXED_PX_FLOOR);
    expect('<table class="min-w-[480px]">').toMatch(FIXED_PX_FLOOR);
    // ...and does not fire on the floors that are legitimate: a floor on a
    // COLUMN is the correct place for one, and `min-w-full` is not a pixel.
    expect('<th class="min-w-[92px] sm:min-w-[140px]">').toMatch(FIXED_PX_FLOOR);
    expect('<table class="w-full min-w-full border-collapse">').not.toMatch(FIXED_PX_FLOOR);
  });

  it("one data column — the Champions League case that was unreadable", () => {
    expect(tableTag(singleColumnGrid())).not.toMatch(FIXED_PX_FLOOR);
  });

  it("four data columns — the case that must keep its 542px and did", () => {
    // The floor is inert here (content needs 542px), so this is not a second
    // instance of the bug. It is the pin on the fix's blast radius: whatever
    // replaces the floor must not reintroduce one for the grids that were fine.
    expect(tableTag(fourColumnGrid())).not.toMatch(FIXED_PX_FLOOR);
  });

  it("the table still fills its container, so a narrow grid does not collapse", () => {
    // Deleting the floor must not become deleting the width. `w-full` is what
    // makes the one-column grid span the card instead of shrinking to its
    // content and leaving the card half empty.
    expect(tableTag(singleColumnGrid())).toContain("w-full");
  });

  it("the scroller survives, because a four-column grid still overflows a phone", () => {
    // Removing the floor narrows three grids; it does not make NFL fit. 542px
    // in a 350px scroller still needs horizontal scroll and its affordance.
    const html = renderToStaticMarkup(
      <TournamentProgressionTable data={fourColumnGrid()} pageType="league" />
    );
    expect(html).toContain("overflow-x-auto");
  });
});

describe("#6722 — the cap the diagnosis rests on", () => {
  it("the Team name stays capped on phones, which is what makes 148px natural", () => {
    // 🔴 THE NON-OBVIOUS COUPLING. The whole argument for deleting the floor is
    // "Team's natural width is 148px, so everything above it was surplus". That
    // is only true while the name span is capped. Remove `max-w-[104px]` and
    // Team grows on content instead of on surplus — the same unreadable screen,
    // reached by a route with no floor to blame and nothing pointing here.
    // #4309 owns the cap; this asserts the dependency, it does not own it.
    const html = renderToStaticMarkup(
      <TournamentProgressionTable data={singleColumnGrid()} pageType="league" />
    );
    expect(html).toContain("max-w-[104px]");
    expect(html).toContain("sm:max-w-[300px]");
  });
});
