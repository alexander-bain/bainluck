/**
 * #10239 — the projected final points module draws two forecast lines and a
 * quieter actual score, or nothing at all.
 *
 * Rendered with real inputs through `renderToStaticMarkup`. #10539 (Alex's
 * direct correction on 14781135): one taller chart with the game's observed
 * period markers, no slider, and the source explained rather than printed
 * bare in the heading.
 */

import fs from "fs";
import path from "path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ProjectedFinalPointsChart, {
  drawnPeriodMarkers,
  formatProjectionTime,
  LINE_RESCUE_COLORS,
  MIN_LINE_PAIR_DISTANCE,
  projectedTeamStrokes,
} from "../../components/event/ProjectedFinalPointsChart";
import { colorDistance } from "@/lib/probabilityBarPair";
import { hexToRgb, teamTextColor } from "@/lib/teamColors";
import {
  buildProjectedFinalPointsSeries,
  type ProjectedFinalPointsInput,
  type ProjectedFinalPointsSeries,
} from "@/lib/projectedFinalPointsSeries";
import type { PeriodBoundary } from "@/lib/periodMarkers";

const KICKOFF = "2026-09-29T00:16:00Z";
const FINAL = "2026-09-29T03:10:00Z";

function nflInput(over: Partial<ProjectedFinalPointsInput> = {}): ProjectedFinalPointsInput {
  return {
    sportKey: "americanfootball_nfl",
    sourceKey: "draftkings",
    basis: "same_book_same_capture_full_game_spread_and_total",
    pairs: [
      { timestamp: "2026-09-28T23:30:00Z", home: 24.5, away: 20.0, homeProbability: 0.62 },
      { timestamp: "2026-09-29T00:30:00Z", home: 27.5, away: 17.0, homeProbability: 0.75 },
      { timestamp: "2026-09-29T01:00:00Z", home: null, away: null },
      { timestamp: "2026-09-29T01:20:00Z", home: 28.0, away: 13.5, homeProbability: 0.9 },
      { timestamp: "2026-09-29T01:40:00Z", home: Number.NaN, away: 12.0 },
      { timestamp: "2026-09-29T02:30:00Z", home: 27.0, away: 9.5, homeProbability: 0.97 },
      { timestamp: "2026-09-29T03:08:00Z", home: 26.5, away: 8.3, homeProbability: 0.99 },
      { timestamp: "2026-09-29T03:09:00Z", home: 27.0, away: 7.5, homeProbability: 0.99 },
      { timestamp: "2026-09-29T03:11:00Z", home: 27.0, away: 7.0, homeProbability: 0.99 },
    ],
    actuals: [
      { timestamp: "2026-09-28T23:50:00Z", home_score: 0, away_score: 0 },
      { timestamp: "2026-09-29T00:24:00Z", home_score: 7, away_score: 0 },
      { timestamp: "2026-09-29T01:15:00Z", home_score: 14, away_score: 7 },
      { timestamp: "2026-09-29T03:06:00Z", home_score: 27, away_score: 7 },
    ],
    kickoffAt: KICKOFF,
    finalAt: FINAL,
    asOf: "2026-09-29T04:00:00Z",
    ...over,
  };
}

const teams = { homeTeam: "Chicago Bears", awayTeam: "Philadelphia Eagles" };

function render(
  input: ProjectedFinalPointsInput,
  finalScore: { home: number; away: number } | null = null,
  periodBoundaries?: PeriodBoundary[],
): string {
  return renderToStaticMarkup(
    <ProjectedFinalPointsChart input={input} {...teams} finalScore={finalScore} periodBoundaries={periodBoundaries} />,
  );
}

const count = (html: string, needle: string) => html.split(needle).length - 1;

describe("unsupported games render nothing", () => {
  it.each(["baseball_mlb", "soccer_epl", "tennis_atp_us_open", "golf_pga_championship_winner"])(
    "%s leaves no empty module behind",
    (sportKey) => {
      expect(renderToStaticMarkup(<ProjectedFinalPointsChart input={nflInput({ sportKey })} {...teams} />)).toBe("");
    },
  );

  it("an NFL game with no usable pair leaves no empty module behind", () => {
    expect(render(nflInput({ pairs: [{ timestamp: "2026-09-29T00:30:00Z", home: null, away: 10 }] }))).toBe("");
  });
});

describe("a finished game", () => {
  const html = render(nflInput(), { home: 27, away: 7 });

  it("draws two forecast series and two quieter actual steps", () => {
    expect(html).toContain("Projected final points");
    expect(html).toContain('data-series="forecast-home"');
    expect(html).toContain('data-series="forecast-away"');
    expect(count(html, 'data-series="actual-home"')).toBe(1);
    expect(count(html, 'data-series="actual-away"')).toBe(1);
    expect(html).toContain('stroke-dasharray="6 5"');
  });

  it("shows the last valid projection with its time, not the final as a forecast", () => {
    expect(html).toContain("Last projection before the final · recorded " + formatProjectionTime(Date.parse("2026-09-29T03:09:00Z")));
    expect(html).toContain(">27.0<");
    expect(html).toContain(">7.5<");
    expect(html).toMatch(/27 final/);
    expect(html).toMatch(/7 final/);
    expect(html).not.toMatch(/current|settled/i);
  });

  it("draws each lone reading as a dot, never stretched toward a gap", () => {
    // 01:20 and 02:30 each sit between two withheld readings, and 03:09 is the
    // last capture before the completion boundary: three dots for each team.
    expect(count(html, 'data-single-point="true"')).toBe(6);
    expect(count(html, 'data-series="forecast-home"')).toBe(4);
  });

  it("marks each withheld reading on the time axis", () => {
    expect(html).toContain('data-withheld="pair_incomplete"');
    expect(html).toContain('data-withheld="not_a_number"');
    expect(html).toContain('data-withheld="below_recorded_score"');
  });

  it("keeps sportsbook jargon off the page", () => {
    expect(html).not.toMatch(/\bbooks?\b|bookmaker/i);
  });
});

describe("#10539 the source is explained, not printed bare in the heading", () => {
  const html = render(nflInput(), { home: 27, away: 7 });

  it("the heading row carries no source name", () => {
    const heading = html.match(/<h3[^>]*>([\s\S]*?)<\/h3>/)!;
    expect(heading[1]).toBe("Projected final points");
    // Nothing between the heading and the readout names the source either.
    const head = html.slice(0, html.indexOf('data-testid="projected-reading"'));
    expect(head).not.toContain("DraftKings");
  });

  it("names the one source inside How to read this, and never calls it a blend", () => {
    const details = html.slice(html.indexOf("<details"), html.indexOf("</details>"));
    expect(details).toContain("How to read this");
    expect(details).toMatch(/data-testid="projected-source"[^>]*>Projection source: DraftKings\. Estimated from that one sportsbook/);
    expect(details).toContain("not an average of sources");
    expect(details).not.toMatch(/\bblend(ed)?\b|consensus/i);
  });
});

describe("#10539 no slider, and the readout still carries both quantities", () => {
  const html = render(nflInput(), { home: 27, away: 7 });

  it("renders no range input, no step-through label and no inspection cursor", () => {
    expect(html).not.toMatch(/<input/);
    expect(html).not.toContain('type="range"');
    expect(html).not.toMatch(/Step through|Back to latest|projected-cursor/);
  });

  it("the readout is text: each team's projection, its score, and the recorded time", () => {
    const readout = html.slice(html.indexOf('data-testid="projected-reading"'), html.indexOf("</p>", html.indexOf('data-testid="projected-stamp"')));
    expect(readout).toMatch(/Chicago Bears<\/span><\/div><div[^>]*>27\.0<\/div><div[^>]*>projected final<\/div><div[^>]*data-actual="home"[^>]*>27 final/);
    expect(readout).toMatch(/Philadelphia Eagles<\/span><\/div><div[^>]*>7\.5<\/div><div[^>]*>projected final<\/div><div[^>]*data-actual="away"[^>]*>7 final/);
    expect(readout).toContain("Last projection before the final · recorded " + formatProjectionTime(Date.parse("2026-09-29T03:09:00Z")));
  });

  it("the component holds no inspection state any more", () => {
    const src = fs.readFileSync(path.join(__dirname, "../../components/event/ProjectedFinalPointsChart.tsx"), "utf8");
    expect(src).not.toMatch(/useState|type="range"|seriesAt|inspectionInstants/);
  });
});

describe("#10539 the plot is taller", () => {
  it("is 256px on a phone and 320px from sm, up from 192px", () => {
    const html = render(nflInput());
    expect(html).toMatch(/class="relative h-64 sm:h-80[^"]*" data-testid="projected-plot"/);
    expect(html).not.toMatch(/class="relative mt-3 h-48"/);
  });

  it("spends the height on the lines: the gutter below the baseline only fits the gap marks", () => {
    // The plot stretches to its box, so every viewBox unit of gutter grows with the taller plot.
    // At 262/300 the 390px render showed an empty strip between the gap marks and the time labels.
    const html = render(nflInput());
    const viewH = Number(html.match(/viewBox="0 0 \d+ (\d+)"/)?.[1]);
    const gridYs = [...html.matchAll(/<line[^>]*\by1="([\d.]+)"[^>]*\by2="\1"/g)].map((m) => Number(m[1]));
    const baseline = Math.max(...gridYs);
    const gaps = [...html.matchAll(/<line[^>]*data-withheld="[^"]+"[^>]*>/g)].map((m) => ({
      y1: Number(m[0].match(/\by1="([\d.]+)"/)?.[1]),
      y2: Number(m[0].match(/\by2="([\d.]+)"/)?.[1]),
    }));
    expect(viewH).toBe(300);
    expect(gaps.length).toBeGreaterThan(0);
    for (const g of gaps) {
      expect(g.y1).toBeGreaterThan(baseline);
      expect(g.y2).toBeLessThanOrEqual(viewH);
    }
    expect(viewH - baseline).toBeLessThanOrEqual(16);
  });
});

describe("a finished game whose last recorded score is not the page's final", () => {
  it("calls the last row recorded and prints the final apart, never as a step", () => {
    const html = render(nflInput(), { home: 28, away: 7 });
    expect(html).toMatch(/data-actual="home"[^>]*>27 last recorded/);
    expect(html).toMatch(/data-final="home"[^>]*>28 final/);
    expect(html).toMatch(/data-final="away"[^>]*>7 final/);
    expect(html).not.toMatch(/27 final/);
  });

  it("with no recorded score at all, the page's final is still shown, not hidden behind a dash", () => {
    const html = render(nflInput({ kickoffAt: null }), { home: 27, away: 7 });
    expect(html).not.toContain("data-actual=");
    expect(html).toMatch(/data-final="home"[^>]*>27 final/);
    expect(html).not.toMatch(/—\s*final/);
  });

  it("the page's final never appears before the game is over", () => {
    const html = render(nflInput({ finalAt: null, asOf: "2026-09-29T02:00:00Z" }), { home: 27, away: 7 });
    expect(html).not.toContain("data-final=");
    expect(html).not.toMatch(/\d+ final</);
  });
});

describe("before kickoff", () => {
  const html = render(nflInput({ kickoffAt: null, finalAt: null, asOf: "2026-09-29T00:00:00Z" }));

  it("has no actual score anywhere", () => {
    expect(html).not.toContain("data-actual=");
    expect(html).not.toContain('data-series="actual-');
    expect(html).toContain("Latest projection · recorded " + formatProjectionTime(Date.parse("2026-09-28T23:30:00Z")));
  });
});

describe("a finished game with no admitted score (#10239 '— final')", () => {
  const html = render(nflInput({ kickoffAt: null }));

  it("prints no placeholder result beside the projection", () => {
    expect(html).not.toContain("data-actual=");
    expect(html).not.toMatch(/—\s*final/);
    expect(html).toContain("Last projection before the final");
  });
});

describe("a live game whose newest reading was unusable", () => {
  it("says so once, without repeating the time", () => {
    const html = render(nflInput({ finalAt: null, asOf: "2026-09-29T01:50:00Z" }));
    expect(html).toContain("Latest projection · recorded " + formatProjectionTime(Date.parse("2026-09-29T01:20:00Z")));
    expect(html).toContain("No usable projection since then");
  });
});

/**
 * #10539 — the game's own period boundaries on the projected plot. Fixture
 * boundaries are in the shape `derivePeriodBoundaries` hands every chart on
 * the page, with the provenance the server serves.
 */
describe("#10539 period markers at their evidenced times", () => {
  const observed = (timestamp: string, label: string, precision = "first_seen"): PeriodBoundary => ({
    timestamp,
    label,
    source: "espn_state",
    precision,
  });
  const NFL_BOUNDARIES: PeriodBoundary[] = [
    observed("2026-09-29T01:05:00Z", "Q2"),
    observed("2026-09-29T01:50:00Z", "HT"),
    observed("2026-09-29T02:05:00Z", "Q3"),
    observed("2026-09-29T02:40:00Z", "Q4"),
  ];
  const supported = (input: ProjectedFinalPointsInput): ProjectedFinalPointsSeries => {
    const s = buildProjectedFinalPointsSeries(input);
    if (!s.supported) throw new Error("expected supported");
    return s;
  };

  it("draws each observed boundary as a rule and a label at its own timestamp, HT and Q3 both kept", () => {
    const html = render(nflInput(), { home: 27, away: 7 }, NFL_BOUNDARIES);
    for (const label of ["Q2", "HT", "Q3", "Q4"]) {
      expect(count(html, `data-period-marker="${label}"`)).toBe(1);
      expect(count(html, `data-period-label="${label}"`)).toBe(1);
    }
    // Rules sit where the plot's own x puts each timestamp, so a label and its rule cannot part.
    const s = supported(nflInput());
    const xOf = (iso: string) => (64 + ((Date.parse(iso) - s.start) / (s.end - s.start)) * (990 - 64)).toFixed(1);
    const rule = (label: string) => Number(html.match(new RegExp(`data-period-marker="${label}" x1="([\\d.]+)"`))![1]).toFixed(1);
    expect(rule("Q2")).toBe(xOf("2026-09-29T01:05:00Z"));
    expect(rule("Q4")).toBe(xOf("2026-09-29T02:40:00Z"));
    const left = (label: string) => Number(html.match(new RegExp(`data-period-label="${label}"[^>]*left:([\\d.]+)%`))![1]);
    expect(left("HT")).toBeCloseTo((Number(xOf("2026-09-29T01:50:00Z")) / 1000) * 100, 1);
  });

  it("the crowded HT → Q3 pair staggers onto two rows instead of smearing", () => {
    const placed = drawnPeriodMarkers(supported(nflInput()), NFL_BOUNDARIES);
    const row = (label: string) => placed.find((m) => m.label === label)!.labelRow;
    expect(placed.map((m) => m.label)).toEqual(["Q2", "HT", "Q3", "Q4"]);
    expect(row("HT")).not.toBe(row("Q3"));
  });

  it("leaves off an estimated boundary rather than drawing schedule arithmetic as timing", () => {
    const html = render(nflInput(), null, [...NFL_BOUNDARIES, { timestamp: "2026-09-29T02:55:00Z", label: "OT", source: "estimated" }]);
    expect(html).not.toContain('data-period-marker="OT"');
    expect(html).not.toContain("~OT");
  });

  it("draws nothing it has no evidence for: no boundaries means no markers and no label rows", () => {
    const html = render(nflInput());
    expect(html).not.toContain("data-period-marker");
    expect(html).not.toContain('data-testid="projected-period-labels"');
    expect(html).not.toMatch(/quarter, halftime or overtime/);
  });

  it("never marks a boundary outside the drawn span, and never stretches the span to reach one", () => {
    const live = nflInput({ finalAt: null, asOf: "2026-09-29T02:00:00Z" });
    const s = supported(live);
    const placed = drawnPeriodMarkers(s, NFL_BOUNDARIES);
    // Q3 and Q4 are after "now" on a live game: not drawn.
    expect(placed.map((m) => m.label)).toEqual(["Q2", "HT"]);
    expect(supported(live).end).toBe(s.end);
    expect(drawnPeriodMarkers(s, [observed("2026-09-28T20:00:00Z", "Q1")])).toEqual([]);
    expect(drawnPeriodMarkers(s, [observed("not a time", "Q2")])).toEqual([]);
  });

  it("before the game marks nothing, even when the history retains a boundary", () => {
    const pregame = nflInput({ kickoffAt: null, finalAt: null, asOf: "2026-09-29T00:00:00Z" });
    expect(drawnPeriodMarkers(supported(pregame), [observed("2026-09-28T23:45:00Z", "Q1")])).toEqual([]);
  });

  it("tells a screen reader each marker is a first observed state, not a guaranteed start", () => {
    const html = render(nflInput(), null, [observed("2026-09-29T01:05:00Z", "Q2"), observed("2026-09-29T02:40:00Z", "Q4", "boundary_observed")]);
    expect(html).toContain(
      `Game state marked on the chart: Q2 first seen in progress ${formatProjectionTime(Date.parse("2026-09-29T01:05:00Z"))}, Q4 began ${formatProjectionTime(Date.parse("2026-09-29T02:40:00Z"))}.`,
    );
    expect(html).toContain("where it was first seen in progress, which can be a little after it began");
  });
});

describe("#10547 — each team keeps one colour that its line can be told apart by", () => {
  const BILLS = "#00338D";
  const PATRIOTS = "#002244";
  const dist = (a: string, b: string) => {
    const [pa, pb] = [a, b].map((h) => hexToRgb(h)!.split(" ").map(Number));
    return colorDistance([pa[0], pa[1], pa[2]], [pb[0], pb[1], pb[2]]);
  };
  const paint = (homeColor: string | null, awayColor: string | null) =>
    renderToStaticMarkup(
      <ProjectedFinalPointsChart
        input={nflInput()}
        homeTeam="New England Patriots"
        awayTeam="Buffalo Bills"
        homeColor={homeColor}
        awayColor={awayColor}
        finalScore={{ home: 27, away: 7 }}
      />,
    );
  /** Every colour this side is painted in: its name, its key, its solid and dashed lines. */
  const sideColours = (html: string, side: "home" | "away") => {
    const name = html.match(new RegExp(`data-side="${side}"><div[^>]*style="color:([^";]+)`))![1];
    const key = html.match(new RegExp(`data-team-key="${side}"[^>]*style="background-color:([^";]+)`))![1];
    const strokes = Array.from(
      html.matchAll(new RegExp(`data-series="(?:forecast|actual)-${side}"[^>]*?stroke="([^"]+)"`, "g")),
      (m) => m[1],
    );
    return { name, key, strokes };
  };

  it("the specimen: two navies were one line (131 apart), so the home side moves and the away side keeps its own", () => {
    expect(dist(BILLS, PATRIOTS)).toBeLessThan(MIN_LINE_PAIR_DISTANCE);
    const pair = projectedTeamStrokes(PATRIOTS, BILLS);
    expect(pair.away).toBe(BILLS);
    expect(pair.home).not.toBe(PATRIOTS);
    expect(LINE_RESCUE_COLORS).toContain(pair.home);
    expect(dist(pair.home, pair.away)).toBeGreaterThanOrEqual(MIN_LINE_PAIR_DISTANCE);
  });

  it("the name above the plot, its key, its projection and its score all wear the same colour", () => {
    const html = paint(PATRIOTS, BILLS);
    const pair = projectedTeamStrokes(PATRIOTS, BILLS);
    for (const side of ["home", "away"] as const) {
      const c = sideColours(html, side);
      // forecast segments + the one dashed actual step, never zero of either
      expect(c.strokes.length).toBeGreaterThanOrEqual(2);
      expect(html).toContain(`data-series="actual-${side}"`);
      expect(new Set([c.name, c.key, ...c.strokes])).toEqual(new Set([pair[side]]));
    }
    // solid forecast vs dashed actual is still the QUANTITY, not the team
    expect(count(html, 'stroke-dasharray="6 5"')).toBe(2);
  });

  it.each([
    ["Eagles green / Bears orange", "#C83803", "#004C54"],
    ["Bills blue / Packers green (164 apart)", "#203731", BILLS],
    ["stored without a hash", "C83803", "004C54"],
  ])("a pair already apart is drawn exactly as supplied: %s", (_label, home, away) => {
    const pair = projectedTeamStrokes(home, away);
    expect(pair).toEqual({ home: `#${home.replace("#", "")}`, away: `#${away.replace("#", "")}` });
    const html = paint(home, away);
    expect(sideColours(html, "home").strokes.every((s) => s === pair.home)).toBe(true);
    expect(sideColours(html, "away").strokes.every((s) => s === pair.away)).toBe(true);
  });

  it("with no colours at all, the teams keep the two text colours they always had", () => {
    expect(projectedTeamStrokes(null, null)).toEqual({ home: "#111827", away: "#6B7280" });
    expect(projectedTeamStrokes(undefined, "not-a-colour")).toEqual({ home: "#111827", away: "#6B7280" });
  });

  it("an unreadable colour counts as none: a white team is not drawn white on the card", () => {
    expect(projectedTeamStrokes("#ffffff", BILLS)).toEqual({ home: "#111827", away: BILLS });
  });

  it("a real colour beside a missing one keeps its own; the fallback side is the one that moves", () => {
    // a real home grey sits on top of the away side's fallback grey
    const grey = "#5B6270";
    expect(dist(grey, "#6B7280")).toBeLessThan(MIN_LINE_PAIR_DISTANCE);
    const pair = projectedTeamStrokes(grey, null);
    expect(pair.home).toBe(grey);
    expect(pair.away).not.toBe("#6B7280");
    expect(dist(pair.home, pair.away)).toBeGreaterThanOrEqual(MIN_LINE_PAIR_DISTANCE);
    // and the mirror: a real away colour beside the home fallback
    const ink = "#1F2937";
    const mirror = projectedTeamStrokes(null, ink);
    expect(mirror.away).toBe(ink);
    expect(dist(mirror.home, mirror.away)).toBeGreaterThanOrEqual(MIN_LINE_PAIR_DISTANCE);
  });

  it("every rescue colour can be printed as a team name (clears the 3:1 text floor)", () => {
    for (const c of LINE_RESCUE_COLORS) expect(teamTextColor(c)).toBe(c);
  });

  it("over every readable colour on a 16-step grid, the pair always ends at least the threshold apart", () => {
    const steps = Array.from({ length: 16 }, (_, i) => (i * 17).toString(16).padStart(2, "0"));
    let checked = 0;
    for (const r of steps)
      for (const g of steps)
        for (const b of steps) {
          const c = `#${r}${g}${b}`;
          if (!teamTextColor(c)) continue;
          for (const partner of [c, PATRIOTS, null]) {
            const pair = projectedTeamStrokes(partner, c);
            expect(dist(pair.home, pair.away)).toBeGreaterThanOrEqual(MIN_LINE_PAIR_DISTANCE);
          }
          checked++;
        }
    expect(checked).toBeGreaterThan(1000);
  });
});
