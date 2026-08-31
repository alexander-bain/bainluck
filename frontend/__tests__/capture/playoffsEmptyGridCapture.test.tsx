/**
 * UX-P173 — TWO CHAMPIONSHIP GRIDS STOP CLAIMING THE ODDS DO NOT EXIST.
 *
 * ═══ WHAT THIS IS ═══
 *
 * `/playoffs` draws 14 league cards, and `LeagueTabs` repeats all 14 on every
 * grid page, so each destination is one click from every other. Two of them —
 * La Liga and the Champions League — rendered this:
 *
 *     No championship odds available yet
 *     Odds will appear when sportsbooks and prediction markets publish
 *     La Liga championship markets.
 *
 * That second line is not a shrug, it is a claim about the world, and it was
 * false. At the moment it was read, `La Liga Champion` (id 31834308) was an
 * open, tier-1 Kalshi field market with twenty priced outcomes repriced that
 * same afternoon — Barcelona 56.5%, Real Madrid 42.5%. So were `La Liga
 * Winner`, `La Liga Relegation` and `La Liga Top 4 Finishers`. The Champions
 * League had four of its own, including `Champions League Winner`.
 *
 * The page did not look broken, which is exactly why nobody filed it. An empty
 * state is a claim, and it is checkable against the card that linked to it.
 *
 * ═══ WHY IT WAS EMPTY ═══
 *
 * The grid pushes each league's `league_name_patterns` down to SQL as an ILIKE
 * prefilter. The converter that built those patterns stripped `\b` and `\s` in
 * a single pass:
 *
 *     re.sub(r"\\[bs]", "", r"\bLa\s+Liga\b")   ->  "La+Liga"
 *
 * so `\s+` had already lost its `\s` by the time the `\s+ -> %` rule ran, and
 * was left as a bare `+`. Every multi-word pattern in every league config
 * compiled to an impossible literal. `ILIKE` is total on text, so the condition
 * was simply false for every row: no error, no warning, no log line. Leagues
 * whose markets are reachable only by name — la-liga, champions-league, and
 * EPL's Champion column — had been empty since the converter was written.
 *
 * The single-word patterns (`\bNBA\b`, `\bBundesliga\b`) were unaffected, which
 * is why nine of the fourteen grids looked fine and hid the class.
 *
 * ═══ THE READER COUNT ═══
 *
 * Measured against production on 2026-08-29, one request per destination:
 *
 *     2 of 14 grids served columns: [], teams: [], sources_available: []
 *       (la-liga, champions-league)  -> the empty state above
 *     1 of 14 lost a whole column    (epl: no Champion column at all)
 *     1 of 14 lost its Division column (nfl)
 *     2 of 14 were degraded for other reasons (ncaa-football 503,
 *       ncaa-women-basketball 500) and are NOT addressed here
 *
 * Replaying the full route selection against production market rows, with the
 * broken and repaired converters side by side: la-liga 0 -> 4 markets,
 * champions-league 0 -> 4, epl 3 -> 5, nfl 2 -> 11, ncaa-football 1 -> 106.
 * No league lost a market.
 *
 * ═══ WHAT EVERY ROW HERE IS MADE OF ═══
 *
 * BEFORE is a verbatim production `/api/playoffs/la-liga` body, curled on
 * 2026-08-29 and banked unedited.
 *
 * AFTER cannot be curled — the fix is not deployed — so it is assembled from
 * verbatim production rows: the twenty `La Liga Champion` outcomes, the
 * nineteen `La Liga Relegation` outcomes and the six `La Liga Top 4 Finishers`
 * outcomes, read straight out of `futures_outcomes`, poured into the response
 * shape a WORKING grid (`/api/playoffs/epl`) actually serves. Every team name
 * and every probability is real. The assembly is stated plainly rather than
 * presented as a capture, because it is not one.
 *
 * Both panels are the shipped `app/playoffs/[sport]/page.tsx` component.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import SERVED_BEFORE from "../fixtures/uxp173_playoffs_laliga_before.json";
import SERVED_AFTER from "../fixtures/uxp173_playoffs_laliga_after.json";

// UX-P220, ruling 142: both lines were rewritten because "available yet" and
// "will appear" described a future rather than the grid as it stands. These
// constants track the SHIPPED copy — the rows below are about whether the empty
// state renders at all, not about which words it uses, and they go vacuous if
// the constants are allowed to drift off the component.
const EMPTY_LINE = "No championship odds right now";
const CLAIM = "This grid covers";

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

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: () => {}, replace: () => {}, prefetch: () => {} }),
  usePathname: () => "/playoffs/la-liga",
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ sport: "la-liga" }),
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
const PlayoffGridPage = require("@/app/playoffs/[sport]/page").default;
// eslint-disable-next-line @typescript-eslint/no-var-requires
const { AnalyticsProvider } = require("@/components/Analytics");

/**
 * The progression table calls `useAnalyticsContext`, which throws outside the
 * provider. Wrap in the REAL `AnalyticsProvider` — the same one
 * `app/layout.tsx` wraps the page in — rather than stubbing the hook, so what
 * renders is what ships and not the page with its chrome removed.
 */
function render(payload: unknown): string {
  gridPayload = payload;
  return renderToStaticMarkup(
    React.createElement(
      AnalyticsProvider,
      null,
      React.createElement(PlayoffGridPage, { params: { sport: "la-liga" } })
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

describe("BEFORE — the grid claims the odds do not exist", () => {
  it("serves nothing at all", () => {
    expect(SERVED_BEFORE.teams).toHaveLength(0);
    expect(SERVED_BEFORE.columns).toHaveLength(0);
    expect(SERVED_BEFORE.sources_available).toHaveLength(0);
    expect(SERVED_BEFORE.team_count).toBe(0);
  });

  it("renders the empty state, and the empty state makes a claim", () => {
    const text = visibleText(render(SERVED_BEFORE));
    expect(text).toContain(EMPTY_LINE);
    expect(text).toContain(CLAIM);
  });

  it("prints no footer, so nothing on the page contradicts the claim", () => {
    // `team_count > 0` gates the "N teams · N columns · N sources" footer.
    const text = visibleText(render(SERVED_BEFORE));
    expect(text).not.toContain("columns ·");
  });
});

describe("AFTER — the grid shows the markets it always had", () => {
  it("no longer claims the odds are unpublished", () => {
    const text = visibleText(render(SERVED_AFTER));
    expect(text).not.toContain(EMPTY_LINE);
    expect(text).not.toContain(CLAIM);
  });

  it("leads with the real title favourite", () => {
    const text = visibleText(render(SERVED_AFTER));
    expect(text).toContain("Barcelona");
    expect(text).toContain("Real Madrid");
  });

  it("shows every column the league has markets for", () => {
    const text = visibleText(render(SERVED_AFTER));
    expect(text).toContain("Champion");
    expect(text).toContain("Relegated");
    expect(text).toContain("Top 4");
  });

  it("declares its source and its size", () => {
    const text = visibleText(render(SERVED_AFTER));
    // Falsifiable in both directions: a wrong count fails as loudly as none.
    expect(text).toContain("20 teams");
    expect(text).toContain("3 columns");
    expect(text).toContain("1 source");
  });
});

describe("the artifact", () => {
  it("writes a before/after render that asserts its own content", () => {
    const before = render(SERVED_BEFORE);
    const after = render(SERVED_AFTER);

    // The rig refuses to emit a file that does not show the defect and its fix.
    expect(visibleText(before)).toContain(EMPTY_LINE);
    expect(visibleText(after)).not.toContain(EMPTY_LINE);
    expect(visibleText(after)).toContain("Barcelona");

    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const fs = require("fs");
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const path = require("path");
    const out = process.env.UXP173_ARTIFACT_DIR;
    if (!out) return; // opt-in; the assertions above are the gate
    fs.mkdirSync(out, { recursive: true });
    fs.writeFileSync(
      path.join(out, "playoffs-la-liga-before-after.html"),
      `<!doctype html><meta charset="utf-8">
<title>UX-P173 — /playoffs/la-liga</title>
<body style="font-family:system-ui;margin:0;padding:24px;background:#fff">
<h1 style="font:600 18px system-ui">UX-P173 — <code>/playoffs/la-liga</code></h1>
<p style="color:#666;font:14px system-ui;max-width:70ch">
Both panels are the shipped <code>app/playoffs/[sport]/page.tsx</code>.
BEFORE is a verbatim production payload. AFTER is assembled from verbatim
production <code>futures_outcomes</code> rows (20 <b>La Liga Champion</b>,
19 <b>La Liga Relegation</b>, 6 <b>La Liga Top 4 Finishers</b>) in the shape a
working grid serves — the fix is not deployed, so it cannot be curled.</p>
<h2 style="font:600 15px system-ui">BEFORE — <code>teams: []</code>, <code>columns: []</code></h2>
<div style="border:1px solid #ddd;padding:16px;border-radius:8px">${before}</div>
<h2 style="font:600 15px system-ui">AFTER — 20 teams, 3 columns, Barcelona 57%</h2>
<div style="border:1px solid #ddd;padding:16px;border-radius:8px">${after}</div>
</body>`
    );
  });
});
