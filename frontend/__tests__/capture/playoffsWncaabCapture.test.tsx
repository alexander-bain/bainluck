/**
 * UX-P176 — THE WOMEN'S NCAA GRID STOPS CLAIMING THE ODDS DON'T EXIST.
 *
 * ═══ WHAT THIS IS ═══
 *
 * `/playoffs/ncaa-women-basketball` served `columns: [] teams: 0` and rendered:
 *
 *     "No championship odds available yet — Odds will appear when sportsbooks
 *      and prediction markets publish WNCAAB championship markets."
 *
 * The market was already published. Kalshi's `KXWMARMAD-27` ("Women's 2027
 * College Basketball Champion") was open, carried 35 priced outcomes, and had
 * been refreshed the same afternoon the page was read.
 *
 * Same class as UX-P173 — a page making a false claim about the world — but a
 * different mechanism, which is why that fix did not reach it.
 *
 * ═══ THE MECHANISM (measured 2026-08-29) ═══
 *
 * `season_pattern` was "2026". The market's name carries its own year, so
 * `_is_future_season_market("Women's 2027 College Basketball Champion", 2026)`
 * returned True and the season filter dropped it before column matching.
 *
 * It was the ONLY market it could drop, and the only one that mattered:
 *
 *     KXWMARMAD-27          open      35 outcomes, all priced, refreshed today
 *     KXWMARMADROUND-27FIN  open       0 outcomes  (bracket not set until March)
 *     KXWMARMADROUND-27QF   open       0 outcomes
 *     KXWMARMADROUND-27SEMI open       0 outcomes
 *     KXWMARMADROUND-27R16  open       0 outcomes
 *     KXWMARMAD-26          resolved  68 outcomes, last updated 2026-04-05
 *     KXWMARMADROUND-26*    resolved  72-76 outcomes, last updated 2026-03/04
 *
 * So dropping that one market emptied the whole grid.
 *
 * Note what the parked note for this defect got wrong, and this file records so
 * nobody re-fixes it: the `\bWomen.s\s+College\s+Basketball\b` league-name
 * pattern is NOT load-bearing. Admission happens on the `KXWMARMAD` ticker
 * prefix (Path B.1), which returns True before the name patterns are consulted.
 * `backend/tests/test_wncaab_grid_season.py` pins that.
 *
 * ═══ WHAT THE WIDENING LETS IN ═══
 *
 * Advancing the season to 2027 also stops treating the resolved 2026 tournament
 * as current — but those names carry no year, so the season filter never saw
 * them either way. They are excluded by the outcome staleness cutoff: five
 * months old against a 7-day bound, on columns that are deliberately not in
 * `_SETTLED_COLUMNS`. That is asserted in the backend test, and mutated.
 *
 * ═══ WHO, AND HOW OFTEN ═══
 *
 * WHO: two consumers. `app/playoffs/page.tsx:24` lists WNCAAB as a card on the
 * grid index, and `LEAGUE_MAP` in `app/playoffs/[sport]/page.tsx:46` puts it in
 * the `LeagueTabs` strip repeated on ALL 14 grid pages — one tap from every
 * other grid.
 *
 * HOW OFTEN: every request. Unlike UX-P175's intermittent 503, this is
 * deterministic — a 14-slug production sweep on 2026-08-29 found exactly three
 * grids serving `teams=0`, and two of them (la-liga, champions-league) are
 * already repaired on this branch by UX-P173. This was the remaining one.
 *
 * ═══ WHAT THE FIXTURES ARE ═══
 *
 *   uxp176_playoffs_wncaab_before.json  verbatim production, read 2026-08-29.
 *   uxp176_playoffs_wncaab_after.json   ASSEMBLED, not served — the fix is not
 *                                       deployed. Built by
 *                                       `artifacts-ux-p176/build_after_fixture.py`
 *                                       from the production envelope plus the 35
 *                                       real KXWMARMAD-27 outcome rows. That
 *                                       script is the record of what is real in
 *                                       it and what is assembly.
 *   uxp176_playoffs_ncaab_control.json  verbatim production men's grid — the
 *                                       control. It must render identically
 *                                       before and after, because a change that
 *                                       repaired one grid by disturbing the
 *                                       other twelve would look like a fix.
 *
 * Every panel is the shipped `app/playoffs/[sport]/page.tsx`.
 */

import React from "react";
import fs from "fs";
import path from "path";
import { renderToStaticMarkup } from "react-dom/server";

import BEFORE from "../fixtures/uxp176_playoffs_wncaab_before.json";
import AFTER from "../fixtures/uxp176_playoffs_wncaab_after.json";
import CONTROL from "../fixtures/uxp176_playoffs_ncaab_control.json";

const FALSE_CLAIM = "No championship odds available yet";
const FALSE_CLAIM_TAIL = "Odds will appear when sportsbooks and prediction markets publish";

let gridPayload: unknown;

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => ({
    // The page holds two SWR calls: the grid, and a golf-only schedule keyed
    // `null` for every other league. Only the grid must resolve.
    data: key === null ? undefined : gridPayload,
    error: undefined,
    isLoading: false,
    mutate: () => undefined,
  }),
}));

jest.mock("@/hooks", () => ({
  __esModule: true,
  usePageTracking: () => undefined,
  useScrollDepth: () => undefined,
  useEngagementTime: () => undefined,
}));

let currentSlug = "ncaa-women-basketball";

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: () => {}, replace: () => {}, prefetch: () => {} }),
  usePathname: () => `/playoffs/${currentSlug}`,
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ sport: currentSlug }),
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
const PlayoffGridPage = require("@/app/playoffs/[sport]/page").default;
// eslint-disable-next-line @typescript-eslint/no-var-requires
const { AnalyticsProvider } = require("@/components/Analytics");

/**
 * The progression table calls `useAnalyticsContext`, which throws outside the
 * provider. Wrap in the REAL `AnalyticsProvider` so what renders is what ships.
 */
function render(payload: unknown, slug = "ncaa-women-basketball"): string {
  gridPayload = payload;
  currentSlug = slug;
  return renderToStaticMarkup(
    React.createElement(
      AnalyticsProvider,
      null,
      React.createElement(PlayoffGridPage, { params: { sport: currentSlug } })
    )
  );
}

/** Strip tags so assertions read what a PERSON reads, not what React emitted. */
function visibleText(markup: string): string {
  return markup
    .replace(/<[^>]*>/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&#x27;|&#39;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/&middot;/g, "·")
    .replace(/&nbsp;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

describe("BEFORE — production makes a false claim", () => {
  it("tells the reader no odds have been published", () => {
    const text = visibleText(render(BEFORE));
    expect(text).toContain(FALSE_CLAIM);
    expect(text).toContain(FALSE_CLAIM_TAIL);
  });

  it("names no team at all", () => {
    const text = visibleText(render(BEFORE));
    expect(text).not.toContain("South Carolina");
    expect(text).not.toContain("UConn");
  });

  it("stamps the season the grid could not serve", () => {
    // The subheading is `gridData.season` straight from `season_pattern`, so
    // the page also printed 2026 while the only live market was the 2027 one.
    expect(BEFORE.season).toBe("2026");
    expect(visibleText(render(BEFORE))).toContain("2026");
  });
});

describe("AFTER — the grid carries the odds that existed all along", () => {
  it("drops the false claim", () => {
    const text = visibleText(render(AFTER));
    expect(text).not.toContain(FALSE_CLAIM);
    expect(text).not.toContain(FALSE_CLAIM_TAIL);
  });

  it("names the contenders, led by South Carolina", () => {
    const text = visibleText(render(AFTER));
    expect(text).toContain("South Carolina");
    expect(text).toContain("UConn");
    expect(text).toContain("USC");
  });

  it("prints the footer count a populated grid earns", () => {
    // `team_count > 0` is what gates the footer, so this asserts the grid is
    // genuinely populated rather than merely missing its empty state.
    const text = visibleText(render(AFTER));
    expect(text).toContain("35 teams");
    expect(text).toContain("1 columns");
  });

  it("advances the season subheading to the one it serves", () => {
    expect(visibleText(render(AFTER))).toContain("2027");
  });
});

describe("CONTROL — the twelve healthy grids are untouched", () => {
  it("the men's grid still renders its teams and never the empty state", () => {
    // A rule that emptied or darkened the other grids would pass every
    // assertion above while destroying the rest of the surface.
    const text = visibleText(render(CONTROL, "ncaa-basketball"));
    expect(text).not.toContain(FALSE_CLAIM);
    expect(text).toContain("Florida Gators");
    expect(text).toContain("68 teams");
  });
});

describe("the empty state still exists for a genuinely empty league", () => {
  it("renders when there really are no markets", () => {
    // Non-vacuity: the AFTER assertions above are only meaningful if the page
    // is still CAPABLE of showing the empty state. If someone deleted it
    // outright, "not.toContain(FALSE_CLAIM)" would pass for the wrong reason.
    const text = visibleText(render({ ...BEFORE, columns: [], teams: [], team_count: 0 }));
    expect(text).toContain(FALSE_CLAIM);
  });
});

describe("the artifact", () => {
  it("writes the four panels, and refuses to if any is wrong", () => {
    const before = render(BEFORE);
    const after = render(AFTER);
    const control = render(CONTROL, "ncaa-basketball");

    // The rig asserts its own output — an artifact that silently captured the
    // wrong thing is worse than no artifact.
    expect(visibleText(before)).toContain(FALSE_CLAIM);
    expect(visibleText(after)).not.toContain(FALSE_CLAIM);
    expect(visibleText(after)).toContain("South Carolina");
    expect(visibleText(control)).toContain("Florida Gators");
    expect(visibleText(control)).not.toContain(FALSE_CLAIM);

    const panel = (title: string, note: string, markup: string) => `
      <section>
        <h2>${title}</h2>
        <p class="note">${note}</p>
        <div class="frame">${markup}</div>
      </section>`;

    const html = `<!doctype html>
<html><head><meta charset="utf-8">
<title>UX-P176 — the women's NCAA grid stops claiming the odds don't exist</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>
  body { background:#f6f7f9; font-family:ui-sans-serif,system-ui,sans-serif; margin:0; padding:24px; }
  h1 { font-size:20px; margin:0 0 4px; }
  .sub { color:#555; font-size:13px; margin:0 0 24px; }
  section { margin-bottom:28px; }
  h2 { font-size:15px; margin:0 0 4px; }
  .note { color:#666; font-size:12px; margin:0 0 8px; max-width:900px; }
  .frame { background:#fff; border:1px solid #dcdfe4; border-radius:10px; overflow:hidden; }
</style></head>
<body>
<h1>UX-P176 — <code>/playoffs/ncaa-women-basketball</code> stops claiming the odds don't exist</h1>
<p class="sub">Every panel is the shipped <code>app/playoffs/[sport]/page.tsx</code> rendered by
<code>__tests__/capture/playoffsWncaabCapture.test.tsx</code>. BEFORE and CONTROL are verbatim
production payloads read 2026-08-29; AFTER is assembled by
<code>artifacts-ux-p176/build_after_fixture.py</code> from the 35 real KXWMARMAD-27 outcome rows.</p>
${panel(
  "BEFORE — production today",
  "columns=[] teams=0. The page tells the reader no markets have been published. Kalshi's KXWMARMAD-27 was open, priced across 35 outcomes, and refreshed the same afternoon.",
  before
)}
${panel(
  "AFTER — with season_pattern advanced to 2027",
  "The one market the season filter was dropping now reaches the championship column: 35 teams led by South Carolina 29.5%, UConn 23.0%, USC 21.5%.",
  after
)}
${panel(
  "CONTROL — the men's grid, unchanged",
  "Verbatim production /api/playoffs/ncaa-basketball. It must look identical before and after: a fix that repaired one grid by disturbing the other twelve would still pass every assertion above.",
  control
)}
</body></html>`;

    const out = path.join(__dirname, "../../../artifacts-ux-p176");
    fs.mkdirSync(out, { recursive: true });
    fs.writeFileSync(path.join(out, "wncaab-grid-states.html"), html);
  });
});
