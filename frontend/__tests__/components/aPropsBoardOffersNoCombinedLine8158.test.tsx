/**
 * #8158 — WHAT THE READER ACTUALLY GETS: no flat 100% line, and no control asking
 * for one.
 *
 * The arithmetic and the measured populations are proven next door in
 * `../combinedLineRefusesAFieldThatIsNotOneQuestion8158.test.ts`. This file proves
 * the rendered consequences, because a policy nothing calls is not a fix:
 *
 *   1. `FuturesChart` draws what it is told and judges nothing. An earlier draft put
 *      a refusal in the component; the union measurement below is why it came out.
 *   2. `EvolutionView` — the only call site that passes `showCombinedProbability` —
 *      does not render the "Combined" checkbox on a props board, does render it on
 *      an exclusive board, and DOES render it on a multi-market union it cannot
 *      honestly judge. A checkbox that visibly does nothing is its own defect, so
 *      the line and the control are refused together; and a control removed for the
 *      wrong reason is the failure the union arm guards.
 *
 * THE DISCRIMINATOR. The union arm and the single-market arm render the SAME 43
 * outcomes and differ only in whether a Stage list makes `activeMarketIds` plural.
 * Each of the two conditions in `combinedLineOffered` is therefore killed by exactly
 * one of them, which is what stops the pair being one assertion written twice.
 *
 * THE STRAWMAN ARM. The combined path is found by `stroke-dasharray="7 4"`, which
 * is unique to it in this component (`4`, `4 3`, `1 5` and `4 2` are the other
 * four). A test that merely failed to find a path would pass if the selector were
 * wrong, so every "absent" assertion is paired with a "present" one on the SAME
 * selector and the same render path.
 *
 * DOES NOT PROVE the hover tooltip's combined row — this project's jest renders to
 * static markup with no jsdom, so no pointer event can be fired. The reader-level
 * proof is the production AFTER frame in the PR.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import { readFileSync, readdirSync, statSync } from "fs";
import { join } from "path";
import { FuturesChart } from "../../components/FuturesChart";
import { EvolutionView } from "../../components/EvolutionView";
import type { PositionOption } from "../../components/EvolutionView";
import { fieldIsOneQuestion } from "@/lib/combinedLinePolicy";
import type { FuturesOutcomeHistory } from "@/lib/types";

const ROOT = join(__dirname, "..", "..");
const HOUR = 3_600_000;
const BASE = Date.UTC(2026, 8, 22, 0, 0, 0);

function series(id: number, name: string, from: number, to: number): FuturesOutcomeHistory {
  return {
    outcome_id: id,
    name,
    history: Array.from({ length: 12 }, (_, k) => ({
      timestamp: new Date(BASE + k * HOUR).toISOString(),
      probability: from + ((to - from) * k) / 11,
    })),
  } as unknown as FuturesOutcomeHistory;
}

/** Market 56775596 "Las Vegas: Team Specials" — served field totals 3.72. */
const VEGAS_PROPS: FuturesOutcomeHistory[] = [
  series(1, "Brock Bowers 3+ TDs", 0.88, 0.94),
  series(2, "Mendoza 300+ passing yards", 0.6, 0.64),
  series(3, "Washington 500+ rushing yards", 0.57, 0.52),
  series(4, "Jeanty 75+ rush and 75+ rec", 0.36, 0.385),
  series(5, "Jeanty 200+ rushing yards", 0.41, 0.38),
  series(6, "Nailor 100+ receiving yards", 0.25, 0.28),
  series(7, "Washington 100+ rushing yards", 0.2, 0.22),
  series(8, "Las Vegas 8+ sacks", 0.135, 0.135),
  series(9, "Las Vegas 400+ passing yards", 0.1, 0.115),
  series(10, "Mendoza 4+ passing TDs", 0.12, 0.105),
];

/** Market 61998713 "Democratic nomination odds leader on October 31?" — 1.000. */
const NOMINATION_LEADER: FuturesOutcomeHistory[] = [
  series(21, "Newsom", 0.48, 0.52),
  series(22, "Harris", 0.24, 0.21),
  series(23, "Shapiro", 0.13, 0.12),
  series(24, "Whitmer", 0.09, 0.09),
  series(25, "Someone else", 0.06, 0.06),
];

/** The combined line's own dash pattern — see the strawman note above. */
const COMBINED_DASH = 'stroke-dasharray="7 4"';

function chartMarkup(data: FuturesOutcomeHistory[], selected = data.slice(0, 3)): string {
  return renderToStaticMarkup(
    <FuturesChart
      historyData={data}
      selectedOutcomes={new Set(selected.map((d) => d.outcome_id))}
      showCombinedProbability
      showAxes
      showLegend={false}
      height={300}
    />,
  );
}

describe("#8158 FuturesChart draws what it is told and judges nothing", () => {
  it("draws the combined path when a caller asks for it", () => {
    const html = chartMarkup(NOMINATION_LEADER);
    expect(html).toContain(COMBINED_DASH);
    // …and it is the combined line, not some other dashed stroke.
    expect(html).toContain('stroke="#111827"');
  });

  it("does NOT second-guess its caller on a props field", () => {
    // The floor that used to live here was removed after the union finding: on the
    // multi-market path `historyData` double-counts contenders, so a component-level
    // refusal would strip the line off every league championship chart. The refusal
    // belongs to EvolutionView, which is the only layer that knows how many markets
    // it merged. This arm pins that the chart no longer decides.
    expect(chartMarkup(VEGAS_PROPS)).toContain(COMBINED_DASH);
  });

  it("draws nothing for either field when the control was never asked for", () => {
    for (const data of [VEGAS_PROPS, NOMINATION_LEADER]) {
      const html = renderToStaticMarkup(
        <FuturesChart historyData={data} showAxes showLegend={false} height={300} />,
      );
      expect(html).not.toContain(COMBINED_DASH);
    }
  });

  it("is the only dash pattern this assertion can be reading", () => {
    // If a later ship gives another element `7 4`, every "absent" arm above goes
    // quietly vacuous. This is the tripwire for that.
    const src = readFileSync(join(ROOT, "components", "FuturesChart.tsx"), "utf8");
    expect([...src.matchAll(/strokeDasharray="7 4"/g)]).toHaveLength(1);
  });
});

/* ── The control chip ─────────────────────────────────────────────────────── */

let payload: { outcomes: FuturesOutcomeHistory[] } | undefined;

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({ data: payload, error: undefined, isLoading: false, mutate: () => undefined }),
}));

function viewMarkup(outcomes: FuturesOutcomeHistory[], positionOptions?: PositionOption[]): string {
  payload = { outcomes };
  return renderToStaticMarkup(<EvolutionView marketId={1} positionOptions={positionOptions} />);
}

/** `/api/futures/multi-history?market_ids=40533,86832,129037` — the NFL league page's
 *  default Stage, "2027 Pro Football Champion", exactly as served 2026-09-22. The full
 *  field, because the point of this fixture is its TOTAL: 43 priced rows for 32 teams,
 *  summing to 1.502 purely because each source names the same team its own way
 *  ("Buffalo Bills" 0.1176 beside "Buffalo" 0.115). Trimming it would destroy the
 *  measurement it exists to carry. The last row is served unpriced. */
const NFL_UNION: FuturesOutcomeHistory[] = [
  ["Los Angeles R", 0.125], ["Buffalo Bills", 0.1176], ["Buffalo", 0.115],
  ["Seattle Seahawks", 0.0871], ["San Francisco", 0.085], ["Seattle", 0.075],
  ["Kansas City", 0.075], ["Baltimore", 0.065], ["Cincinnati", 0.055],
  ["Philadelphia", 0.055], ["Detroit Lions", 0.0462], ["Denver Broncos", 0.0431],
  ["Houston Texans", 0.0409], ["Dallas Cowboys", 0.0408], ["New England", 0.035],
  ["Detroit", 0.035], ["Denver", 0.035], ["Dallas", 0.035], ["Chicago Bears", 0.0308],
  ["Jacksonville", 0.025], ["Minnesota", 0.025], ["Green Bay", 0.025],
  ["Houston", 0.025], ["Chicago", 0.025], ["Los Angeles C", 0.015],
  ["New Orleans", 0.015], ["Carolina Panthers", 0.0104], ["Miami", 0.01],
  ["Carolina", 0.01], ["Arizona", 0.01], ["Atlanta", 0.01], ["Tampa Bay", 0.01],
  ["Pittsburgh", 0.01], ["Indianapolis", 0.01], ["Las Vegas", 0.01],
  ["New York G", 0.01], ["Washington", 0.01], ["New York J", 0.01],
  ["Cleveland", 0.01], ["Tennessee", 0.01], ["Atlanta Falcons", 0.0057],
  ["Arizona Cardinals", 0.0032], ["Miami Dolphins", 0.001],
].map(([n, v], i) => series(100 + i, n as string, v as number, v as number));

/** Two Stages, so `activeMarketIds` has more than one id and EvolutionView takes the
 *  `/multi-history` path — the shape the union arm is about. */
const UNION_STAGES: PositionOption[] = [
  { key: "conference", label: "Conference", marketId: 31615, marketIds: [31615, 31616] },
  { key: "championship", label: "Super Bowl", marketId: 40533, marketIds: [40533, 86832, 129037] },
];

describe("#8158 EvolutionView offers the control only where the line can be drawn", () => {
  it("shows no Combined checkbox on the props board", () => {
    const html = viewMarkup(VEGAS_PROPS);
    expect(html).not.toContain(">Combined<");
    expect(html).not.toContain('type="checkbox"');
  });

  it("shows it on the exclusive board — the same strings, present", () => {
    const html = viewMarkup(NOMINATION_LEADER);
    expect(html).toContain(">Combined<");
    expect(html).toContain('type="checkbox"');
  });

  it("puts nothing in its place: no explanation of a control the reader never saw", () => {
    // D102 / notice 34 — a reader gets the numbers, not a paragraph about what is
    // missing. The chart's other controls are untouched by the removal.
    const props = viewMarkup(VEGAS_PROPS);
    for (const word of ["Combined", "independent", "cannot", "meaningless", "not a probability"]) {
      expect(props).not.toContain(word);
    }
    // The removal is surgical: the controls either side of it are untouched.
    expect(props).toContain(">24 Hours<");
    expect(props).toContain(">8 of 10<");
  });
});

describe("#8158 the union path keeps its control — the duplication is not this line's bug", () => {
  it("the NFL Stage field only exceeds the ceiling because teams are doubled", () => {
    // 1.502 served on a question with exactly one winner, and dedupe-by-name cannot
    // see why: "Buffalo" is not "Buffalo Bills". This is the measurement that moved
    // the decision out of the chart.
    const total = NFL_UNION.reduce((a, o) => a + (o.history.at(-1)!.probability ?? 0), 0);
    expect(total).toBeCloseTo(1.502, 3);
    expect(fieldIsOneQuestion(NFL_UNION)).toBe(false);
    const names = NFL_UNION.map((o) => o.name);
    expect(new Set(names).size).toBe(names.length); // no exact-duplicate names to drop…
    // …yet eleven teams are present twice, which is the whole inflation.
    const doubled = names.filter((n) => names.some((m) => m !== n && m.startsWith(`${n} `)));
    expect(doubled.length).toBeGreaterThanOrEqual(10);
  });

  it("keeps the Combined control anyway when more than one market was merged", () => {
    const html = viewMarkup(NFL_UNION, UNION_STAGES);
    expect(html).toContain(">Combined<");
    expect(html).toContain('type="checkbox"');
  });

  it("refuses the SAME rows when they are one market's field — the discriminator is the path", () => {
    // Same outcomes, no Stage list, so `activeMarketIds` is a single id. The only
    // thing that changed is whether the rows are a union, which is exactly the
    // condition. A fix that dropped the single-market guard passes the arm above
    // and fails here; one that dropped the field test fails the arm above.
    const html = viewMarkup(NFL_UNION);
    expect(html).not.toContain(">Combined<");
  });
});

describe("#8158 EvolutionView also forwards its verdict, and that is not redundant", () => {
  /**
   * The chart's own floor judges `historyData`, which EvolutionView hands it
   * WINDOWED by the time-range picker. Windowing only removes probability mass, so
   * the floor can never refuse a field the card admitted — but it CAN admit one the
   * card refused. A props board whose 24h window leaves only two cheap rows priced
   * totals 0.25 inside the window and 3.72 as served: the floor says draw, and only
   * the forwarded verdict says don't.
   *
   * It is reachable exactly once — a reader who ticks "Combined" on an exclusive
   * Stage, then switches Stage to a props board — because `showCombinedProbability`
   * survives the switch while the control vanishes. That needs two interactions, and
   * this project's jest renders to static markup with no jsdom to fire them. So the
   * conjunction is asserted at the source, and the arithmetic it relies on is
   * asserted for real.
   */
  it("the windowed field really can admit what the served field refuses", () => {
    const served = VEGAS_PROPS;
    const windowed = [VEGAS_PROPS[7], VEGAS_PROPS[8]];
    expect(fieldIsOneQuestion(served)).toBe(false);
    expect(fieldIsOneQuestion(windowed)).toBe(true);
  });

  it("passes the verdict to the chart rather than the raw checkbox state", () => {
    const src = readFileSync(join(ROOT, "components", "EvolutionView.tsx"), "utf8");
    expect(src).toContain("showCombinedProbability={showCombinedProbability && combinedLineOffered}");
    // …and judges it on the SERVED outcomes, not the windowed ones the chart gets.
    expect(src).toContain("fieldIsOneQuestion(data?.outcomes ?? [])");
    expect(src).not.toContain("fieldIsOneQuestion(windowedOutcomes)");
  });
});

describe("#8158 the wiring: only one call site asks for this line", () => {
  it("EvolutionView is the sole passer of showCombinedProbability", () => {
    // The component floor above protects the other seven call sites; this census
    // is what says there are only seven to protect, and fails loudly if an
    // eighth starts requesting the line without hiding its own control.
    const hits: string[] = [];
    const walk = (dir: string) => {
      for (const entry of readdirSync(dir)) {
        if (entry === "node_modules" || entry === ".next") continue;
        const p = join(dir, entry);
        if (statSync(p).isDirectory()) walk(p);
        else if (/\.tsx?$/.test(entry) && readFileSync(p, "utf8").includes("showCombinedProbability")) {
          hits.push(p.slice(ROOT.length + 1));
        }
      }
    };
    walk(join(ROOT, "app"));
    walk(join(ROOT, "components"));
    expect(hits.sort()).toEqual(["components/EvolutionView.tsx", "components/FuturesChart.tsx"]);
  });
});
