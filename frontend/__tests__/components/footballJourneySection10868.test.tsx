/** @jest-environment jsdom */
/**
 * #10868 — the football web headline + history SECTION renders the view
 * `buildFootballJourney` makes, presents it AWAY FIRST without moving any value
 * off its named side, keeps provenance in a working compact Info disclosure,
 * and offers a control only for an admitted destination with a real callback.
 *
 * Bodies: the consumed-field extraction `__tests__/lib/footballJourney10868.fixtures.json`
 * (Rams–Bills 14780558 before; Jaguars–Eagles 14639175 live; Bears–Patriots
 * 14780564 live t0/t1/t2) and the existing `__tests__/fixtures/finalForecast11296.json`
 * `detail_14966179` (Bucs–Steelers final), all documented in the lib test.
 *
 * CONSTRUCTED, and named where used: `now`; the host emulation (the page's own
 * `resolveProbability` call, and `liveClaimUnbacked` = false for every real read);
 * the host callbacks (jest mocks standing in for the host's readers — no reader is
 * built or claimed); and TEST MUTATIONS (a non-NFL sport, a Postponed period, a
 * true `liveClaimUnbacked`, a malformed side pair).
 *
 * JSDOM LAYS NOTHING OUT. Class names such as `min-h-11` / `min-w-11` are checked as
 * the 44 px target's declaration, and the matrix stays on its first (grid)
 * arrangement because every jsdom width is 0. None of this is visual proof of
 * size, fit, wrapping or first-screen position: that is the browser lab's job at
 * 375 / 393 px, normal and 200% text.
 */
import React from "react";
import { createRoot, type Root } from "react-dom/client";
import { act } from "react-dom/test-utils";
import fixtures from "../lib/footballJourney10868.fixtures.json";
import bucsFixture from "../fixtures/finalForecast11296.json";
import type { EventDetailResponse, EventHistoryResponse } from "@/lib/types";
import { resolveProbability } from "@/lib/eventKeyStats";
import { blendCaptionIsStale, hasNoReportedResult, isFinishedStatus, SUSPENDED_LABEL } from "@/lib/eventState";
import { buildFootballJourney, type FootballJourneyHost } from "@/lib/eventPage10868/footballJourney";
import { PAGE_WORDS } from "@/lib/eventPage10868/hockeyJourney";
import FootballJourneySection, {
  FOOTBALL_DISPLAY_ORDER,
  REFUSED_SECTION_LABEL,
  inDisplayOrder,
  type FootballJourneySectionModel,
  type FootballJourneySectionView,
} from "@/components/event/eventpage10868/FootballJourneySection";
import HockeyJourneyMatrix, { matrixArrangements } from "@/components/event/eventpage10868/HockeyJourneyMatrix";

const detail = (x: unknown) => x as EventDetailResponse;
const body = (x: unknown) => x as EventHistoryResponse;
/** A deep copy with keys replaced — a TEST MUTATION. */
const mutate = <T,>(x: T, patch: Record<string, unknown>): T => ({ ...JSON.parse(JSON.stringify(x)), ...patch });

const rams = detail(fixtures.ramsDetail);
const ramsHistory = body(fixtures.ramsHistory);
const jagLive = detail(fixtures.jaguarsLiveDetail);
const jagLiveHistory = body(fixtures.jaguarsLiveHistory);
const jagFinal = detail(fixtures.jaguarsFinalDetail);
const bears = [fixtures.bearsT0Detail, fixtures.bearsT1Detail, fixtures.bearsT2Detail].map(detail);
const bucs = detail(bucsFixture.detail_14966179);

const RAMS_NOW = "2026-10-12T05:46:00Z";
const JAG_LIVE_NOW = "2026-10-11T15:37:30Z";
const JAG_FINAL_NOW = "2026-10-11T19:35:00Z";
const BEARS_NOW = ["2026-10-23T02:43:30Z", "2026-10-23T02:44:00Z", "2026-10-23T02:50:45Z"];
const BUCS_NOW = "2026-10-18T23:05:00Z";

/** HOST EMULATION (CONSTRUCTED) — page.tsx's own `resolveProbability` arguments; see the lib test. */
function pageHost(event: EventDetailResponse, history: EventHistoryResponse | null, nowIso: string, liveClaimUnbacked: boolean): FootballJourneyHost {
  const now = Date.parse(nowIso);
  const start = Date.parse(event.commence_time);
  const isLive = event.status === "live" && Number.isFinite(start) && start <= now;
  const isSuspended =
    hasNoReportedResult(event.status, event.commence_time, now, event.started_without_result) || liveClaimUnbacked;
  const r = resolveProbability(
    event,
    history ?? undefined,
    null,
    isLive,
    isFinishedStatus(event.status),
    isSuspended,
    blendCaptionIsStale(false, liveClaimUnbacked),
    true,
  );
  return {
    liveClaimUnbacked,
    nowMs: now,
    hero: { homeProb: r.homeProb, awayProb: r.awayProb, homePct: r.homePct, awayPct: r.awayPct, probSourceLabel: r.probSourceLabel },
    probabilityObservedAt: r.selectedProbabilitySource === "hero-blend" ? event.hero_probability_observed_at ?? null : null,
  };
}

/** CONSTRUCTED host flag for every real-specimen read: the page's live claim is backed. */
const CLAIM_BACKED = false;

function model(
  event: EventDetailResponse,
  history: EventHistoryResponse | null,
  nowIso: string,
  unbacked: boolean = CLAIM_BACKED,
): FootballJourneySectionModel {
  return buildFootballJourney({ event, history, host: pageHost(event, history, nowIso, unbacked) });
}

function view(m: FootballJourneySectionModel): FootballJourneySectionView {
  if (m.kind !== "journey") throw new Error("refused");
  return m;
}

let host: HTMLDivElement;
let root: Root;

beforeEach(() => {
  (globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
});

afterEach(() => {
  act(() => root.unmount());
  host.remove();
  jest.restoreAllMocks();
});

function render(element: React.ReactElement) {
  act(() => root.render(element));
}

function click(el: Element) {
  act(() => {
    el.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
}

const section = () => host.querySelector("section[data-football-journey]") as HTMLElement;
const control = (kind: "forecast" | "history") => host.querySelector(`[data-football-control="${kind}"]`) as HTMLButtonElement | null;
const infoToggle = () => host.querySelector("[data-football-info-toggle]") as HTMLButtonElement;
const infoPanel = () => host.querySelector("[data-football-info]") as HTMLElement;
const headerTitles = () => Array.from(host.querySelectorAll("table thead th")).map((th) => th.textContent);
/** Each grid row: the team it is headed by, and its cells' visible texts (aria-hidden figures or words). */
function gridRows() {
  return Array.from(host.querySelectorAll("table tbody tr")).map((tr) => {
    const nameSpan = tr.querySelector("th span span") as HTMLElement;
    return {
      name: tr.querySelector("th")?.textContent?.replace(/(Won|Lost)$/, "") ?? "",
      result: /(Won|Lost)$/.exec(tr.querySelector("th")?.textContent ?? "")?.[1] ?? null,
      color: nameSpan?.style.color ?? "",
      cells: Array.from(tr.querySelectorAll("td")).map((td) => {
        const figure = td.querySelector('[aria-hidden="true"]');
        return (figure ?? td).textContent;
      }),
      spoken: Array.from(tr.querySelectorAll("td .sr-only")).map((s) => s.textContent),
    };
  });
}
/** The chart's line key: each entry's team name, glyph shape and paint, and its readings. */
function lineKey() {
  return Array.from(host.querySelectorAll("[data-line-key] > li")).map((li) => {
    const glyph = li.querySelector("svg circle, svg rect") as SVGElement;
    return {
      name: li.querySelector("p span")?.textContent,
      glyph: glyph?.tagName.toLowerCase(),
      paint: glyph?.getAttribute("style") ?? "",
      text: li.textContent ?? "",
    };
  });
}

describe("display order is away first, presentation-only, by side", () => {
  it("copies a side-tagged pair in FOOTBALL_DISPLAY_ORDER by each item's own side, never by position", () => {
    expect(FOOTBALL_DISPLAY_ORDER).toEqual(["away", "home"]);
    const home = { side: "home" as const, v: 1 };
    const away = { side: "away" as const, v: 2 };
    const input: [typeof home | typeof away, typeof home | typeof away] = [home, away];
    const out = inDisplayOrder(input);
    expect(out).toEqual([away, home]);
    expect(out[0]).toBe(away);
    expect(out).not.toBe(input);
    expect(input).toEqual([home, away]);
    expect(inDisplayOrder<typeof home | typeof away>([away, home])).toEqual([away, home]);
    // TEST MUTATION: a malformed pair (two home rows) is NOT swapped by position.
    const twin = { side: "home" as const, v: 3 };
    expect(inDisplayOrder([home, twin])).toEqual([home, twin]);
  });

  it("never mutates the view it was given", () => {
    const m = model(rams, ramsHistory, RAMS_NOW);
    const before = JSON.stringify(m);
    render(<FootballJourneySection model={m} onOpenForecast={() => {}} onOpenHistory={() => {}} />);
    expect(JSON.stringify(m)).toBe(before);
    expect(view(m).headline.matrix.rows.map((r) => r.side)).toEqual(["home", "away"]);
    expect(view(m).history.series.map((s) => s.side)).toEqual(["home", "away"]);
  });
});

describe("BEFORE — Rams–Bills (retained)", () => {
  const m = model(rams, ramsHistory, RAMS_NOW);
  const v = view(m);

  it("leads with the AWAY team in the grid and the line key, and every value, tint and glyph stays with its side", () => {
    render(<FootballJourneySection model={m} />);
    expect(section().getAttribute("data-football-journey")).toBe("before");
    expect(headerTitles()).toEqual(["Team", "Current chance", "Projected final"]);
    const rows = gridRows();
    expect(rows.map((r) => [r.name, r.cells])).toEqual([
      ["Buffalo Bills", ["38%", "25.4"]],
      ["Los Angeles Rams", ["62%", "29"]],
    ]);
    expect(rows[0].spoken).toEqual(["38 percent", "25.4 points"]);
    // Tint by side: each name keeps its own team's tint (or none), normalised the way jsdom stores a colour.
    const asStyled = (tint: string | null) => {
      const probe = document.createElement("span");
      if (tint) probe.style.color = tint;
      return probe.style.color;
    };
    expect(v.headline.away.tint).not.toBeNull();
    expect(v.headline.home.tint).not.toBeNull();
    expect(rows.map((r) => r.color)).toEqual([asStyled(v.headline.away.tint), asStyled(v.headline.home.tint)]);
    expect(rows[0].color).not.toBe(rows[1].color);
    const key = lineKey();
    expect(key.map((k) => [k.name, k.glyph])).toEqual([
      ["Buffalo Bills", "rect"],
      ["Los Angeles Rams", "circle"],
    ]);
    expect(key[0].text).toContain("38%");
    expect(key[1].text).toContain("62%");
    expect(key[0].paint).toContain(v.headline.away.tint ? "team-away-primary" : "series-2");
    expect(key[1].paint).toContain(v.headline.home.tint ? "team-home-primary" : "series-1");
  });

  it("keeps provenance out of the closed headline and in a compact, working Info control beside the state line", () => {
    render(<FootballJourneySection model={m} />);
    const row = host.querySelector("[data-football-header-row]") as HTMLElement;
    const toggle = infoToggle();
    expect(row.contains(toggle)).toBe(true);
    expect(row.textContent).toContain(v.headline.state);
    expect(toggle.tagName).toBe("BUTTON");
    expect(toggle.getAttribute("type")).toBe("button");
    expect(toggle.querySelector(".sr-only")?.textContent).toBe("About these sources");
    expect(toggle.querySelector('svg[aria-hidden="true"]')).not.toBeNull();
    expect(toggle.className).toMatch(/\bmin-h-11\b/);
    expect(toggle.className).toMatch(/\bmin-w-11\b/);
    const panel = infoPanel();
    expect(toggle.getAttribute("aria-controls")).toBe(panel.id);
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(panel.hidden).toBe(true);
    // Closed: the provenance is only inside the hidden panel, never in the visible headline.
    expect(panel.textContent).toContain("Projected final: Before the start · 22 sportsbooks");
    expect((host.querySelector("[data-hockey-matrix]") as HTMLElement).textContent).not.toContain("sportsbooks");
    click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(panel.hidden).toBe(false);
    click(toggle);
    expect(panel.hidden).toBe(true);
  });

  it("offers each control only with an admitted destination AND a callback, and calls nothing until activated", () => {
    const onOpenForecast = jest.fn();
    const onOpenHistory = jest.fn();
    render(<FootballJourneySection model={m} onOpenForecast={onOpenForecast} onOpenHistory={onOpenHistory} />);
    render(<FootballJourneySection model={m} onOpenForecast={onOpenForecast} onOpenHistory={onOpenHistory} />);
    expect(onOpenForecast).not.toHaveBeenCalled();
    expect(onOpenHistory).not.toHaveBeenCalled();
    expect(control("forecast")?.textContent).toBe("Open forecast comparison");
    expect(control("history")?.textContent).toBe("Open win history");
    expect(control("forecast")?.className).toMatch(/\bmin-h-11\b/);
    expect(control("history")?.className).toMatch(/\bmin-h-11\b/);
    click(control("forecast")!);
    expect(onOpenForecast).toHaveBeenCalledTimes(1);
    expect(onOpenHistory).not.toHaveBeenCalled();
    click(control("history")!);
    expect(onOpenHistory).toHaveBeenCalledTimes(1);
    expect(onOpenForecast).toHaveBeenCalledTimes(1);
  });

  it("no callback (absent or null) means no control, even with an admitted destination", () => {
    expect(v.forecastAction).not.toBeNull();
    expect(v.historyAction).not.toBeNull();
    render(<FootballJourneySection model={m} />);
    expect(control("forecast")).toBeNull();
    expect(control("history")).toBeNull();
    render(<FootballJourneySection model={m} onOpenForecast={null} onOpenHistory={null} />);
    expect(control("forecast")).toBeNull();
    expect(control("history")).toBeNull();
  });
});

describe("LIVE — Bears–Patriots t0 → t1 → t2 (retained)", () => {
  const ms = bears.map((event, i) => model(event, null, BEARS_NOW[i]));

  it("shows the earlier role in its title, all eight values, and the VISIBLE earlier forecast under the matrix, away first", () => {
    render(<FootballJourneySection model={ms[0]} onOpenForecast={() => {}} />);
    expect(headerTitles()).toEqual(["Team", "Opened chance", "Current chance", "Score", "Projected final"]);
    expect(gridRows().map((r) => [r.name, r.cells])).toEqual([
      ["New England Patriots", ["41%", "21%", "21", "28"]],
      ["Chicago Bears", ["59%", "79%", "27", "33"]],
    ]);
    const earlier = host.querySelector("[data-football-earlier-forecast]") as HTMLElement;
    expect(earlier.getAttribute("role")).toBe("group");
    expect(earlier.querySelector("p")?.textContent).toBe("Pregame forecast");
    const entries = Array.from(earlier.querySelectorAll("[data-side]")).map((d) => [
      d.getAttribute("data-side"),
      d.querySelector("dt")?.textContent,
      d.querySelector('dd [aria-hidden="true"]')?.textContent,
      d.querySelector("dd .sr-only")?.textContent,
    ]);
    expect(entries).toEqual([
      ["away", "New England Patriots", "24", "24 points"],
      ["home", "Chicago Bears", "27", "27 points"],
    ]);
    // Reading order (Design FQ1: the forecast action sits under the chart): matrix → earlier forecast → history → actions.
    const order = ["[data-hockey-matrix]", "[data-football-earlier-forecast]", "[data-line-key]", '[data-football-control="forecast"]'].map(
      (sel) => host.querySelector(sel) as Element,
    );
    for (let i = 1; i < order.length; i += 1) {
      expect(order[i - 1].compareDocumentPosition(order[i]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    }
  });

  it("refreshes in place: new values, same open Info, no callback fired by a re-render", () => {
    const onOpenForecast = jest.fn();
    render(<FootballJourneySection model={ms[0]} onOpenForecast={onOpenForecast} />);
    click(infoToggle());
    const cells = () => gridRows().map((r) => r.cells);
    expect(cells()).toEqual([
      ["41%", "21%", "21", "28"],
      ["59%", "79%", "27", "33"],
    ]);
    render(<FootballJourneySection model={ms[1]} onOpenForecast={onOpenForecast} />);
    expect(cells()).toEqual([
      ["41%", "19%", "21", "28"],
      ["59%", "81%", "27", "33"],
    ]);
    render(<FootballJourneySection model={ms[2]} onOpenForecast={onOpenForecast} />);
    expect(cells()).toEqual([
      ["41%", "21%", "21", "26"],
      ["59%", "79%", "27", "32"],
    ]);
    expect(infoToggle().getAttribute("aria-expanded")).toBe("true");
    expect(infoPanel().hidden).toBe(false);
    expect(onOpenForecast).not.toHaveBeenCalled();
    // No history body is held for this game: the chart says so and there is no history control.
    expect(host.textContent).toContain("History unavailable");
    expect(control("history")).toBeNull();
  });

  it("withdrawn live claim (TEST MUTATION: liveClaimUnbacked true on the fresh t0 quote): no live cue, no Current chance, no forecast, no control", () => {
    const onOpenForecast = jest.fn();
    render(<FootballJourneySection model={model(bears[0], null, BEARS_NOW[0], true)} onOpenForecast={onOpenForecast} />);
    expect(host.querySelector("[data-football-header-row] p")?.textContent).toBe(`${SUSPENDED_LABEL} · last score 21-27`);
    expect(headerTitles()).toEqual(["Team", "Opened chance", "Last recorded chance", "Score"]);
    expect(gridRows().map((r) => [r.name, r.cells])).toEqual([
      ["New England Patriots", ["41%", "21%", "21"]],
      ["Chicago Bears", ["59%", "79%", "27"]],
    ]);
    // The withdrawn forecast is stated once for both teams, as words.
    expect(host.querySelector("[data-matrix-shared-absences]")?.textContent).toBe("Both teamsProjected final:Forecast unavailable");
    expect(host.querySelector("[data-football-earlier-forecast]")).toBeNull();
    expect(control("forecast")).toBeNull();
    expect(onOpenForecast).not.toHaveBeenCalled();
  });

  it("suspended (TEST MUTATION: status 'suspended' on t0, unequal 27-21): the bare last score reads in the rows' order, away then home", () => {
    render(<FootballJourneySection model={model(mutate(bears[0], { status: "suspended" }), null, BEARS_NOW[0])} />);
    const rows = gridRows();
    const scoreColumn = headerTitles().indexOf("Score") - 1; // the first header is the team column
    const [first, second] = rows.map((r) => [r.name, r.cells[scoreColumn]]);
    expect(first).toEqual(["New England Patriots", "21"]);
    expect(second).toEqual(["Chicago Bears", "27"]);
    const state = host.querySelector("[data-football-header-row] p")?.textContent;
    expect(state).toBe(`${SUSPENDED_LABEL} · last score ${first[1]}-${second[1]}`);
    expect(state).toBe(`${SUSPENDED_LABEL} · last score 21-27`);
  });
});

describe("LIVE — Jaguars–Eagles with its own history, and with another game's (retained)", () => {
  it("draws its own history away first and offers the history control", () => {
    const onOpenHistory = jest.fn();
    render(<FootballJourneySection model={model(jagLive, jagLiveHistory, JAG_LIVE_NOW)} onOpenHistory={onOpenHistory} />);
    expect(gridRows().map((r) => [r.name, r.cells])).toEqual([
      ["Philadelphia Eagles", ["24%", "54%", "14"]],
      ["Jacksonville Jaguars", ["76%", "46%", "7"]],
    ]);
    expect(lineKey().map((k) => [k.name, k.glyph])).toEqual([
      ["Philadelphia Eagles", "rect"],
      ["Jacksonville Jaguars", "circle"],
    ]);
    expect(host.querySelectorAll('svg[role="img"] path').length).toBeGreaterThan(0);
    expect(control("history")?.textContent).toBe("Open win history");
    expect(onOpenHistory).not.toHaveBeenCalled();
  });

  it("another game's history: chart unavailable, no history control, headline unchanged", () => {
    const onOpenHistory = jest.fn();
    render(<FootballJourneySection model={model(jagLive, ramsHistory, JAG_LIVE_NOW)} onOpenHistory={onOpenHistory} />);
    expect(section().getAttribute("data-history-foreign")).toBe("true");
    expect(host.textContent).toContain("History unavailable");
    expect(host.querySelector('svg[role="img"]')).toBeNull();
    expect(control("history")).toBeNull();
    expect(gridRows().map((r) => r.cells)).toEqual([
      ["24%", "54%", "14"],
      ["76%", "46%", "7"],
    ]);
  });
});

describe("FINAL — Bucs–Steelers (retained) and Jaguars–Eagles (retained)", () => {
  it("prints earlier chance → pregame forecast → final → vs forecast (pts), away first, results with their teams", () => {
    render(<FootballJourneySection model={model(bucs, null, BUCS_NOW)} onOpenForecast={() => {}} />);
    expect(headerTitles()).toEqual(["Team", "Pregame chance", "Pregame forecast", "Final score", "vs forecast (pts)"]);
    const rows = gridRows();
    expect(rows.map((r) => [r.name, r.result, r.cells])).toEqual([
      ["Pittsburgh Steelers", "Won", ["56%", "20.1", "26", "+5.9"]],
      ["Tampa Bay Buccaneers", "Lost", ["44%", "17.8", "19", "+1.2"]],
    ]);
    expect(rows[0].spoken[3]).toBe("5.9 points above forecast");
    expect(rows[1].spoken[3]).toBe("1.2 points above forecast");
    expect(control("forecast")?.textContent).toBe("Open forecast comparison");
  });

  it("with no admitted forecast and no history offers no control, whatever callbacks the host passes", () => {
    const onOpenForecast = jest.fn();
    const onOpenHistory = jest.fn();
    render(<FootballJourneySection model={model(jagFinal, null, JAG_FINAL_NOW)} onOpenForecast={onOpenForecast} onOpenHistory={onOpenHistory} />);
    expect(gridRows().map((r) => [r.name, r.result])).toEqual([
      ["Philadelphia Eagles", "Lost"],
      ["Jacksonville Jaguars", "Won"],
    ]);
    expect(control("forecast")).toBeNull();
    expect(control("history")).toBeNull();
  });
});

describe("refusals (TEST MUTATIONS)", () => {
  it("renders nothing for a non-NFL row, and the authority's word for a stopped one", () => {
    render(<FootballJourneySection model={model(mutate(rams, { sport: "basketball_nba" }), null, RAMS_NOW)} />);
    expect(host.innerHTML).toBe("");
    render(<FootballJourneySection model={model(mutate(rams, { espn: { period: "Postponed", game_clock: null } }), null, RAMS_NOW)} onOpenForecast={() => {}} />);
    const refused = host.querySelector('[data-football-journey="refused"]') as HTMLElement;
    expect(refused.tagName).toBe("SECTION");
    expect(refused.getAttribute("aria-label")).toBe(REFUSED_SECTION_LABEL);
    expect(REFUSED_SECTION_LABEL).toBe("Football game status");
    expect(refused.textContent).toContain("Postponed");
    expect(refused.textContent).toContain(PAGE_WORDS.matrixUnavailable);
    expect(host.querySelector("button")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Design FQ1 — the compact matrix and the action group under the chart.
//
// JSDOM lays nothing out, so a phone is CONSTRUCTED: `clientWidth` is the lab's
// measured 317 px frame at 375, and `scrollWidth` answers per arrangement from
// a rule the test states. This proves the fit STEPPING and the classes, never
// the real fit, which only the browser lab measures.
// ---------------------------------------------------------------------------

/** `fits(arrangement, header cells)` decides each measured frame's overflow. CONSTRUCTED layout. */
function withForcedLayout(fits: (arrangement: string, headerCells: number) => boolean, run: () => void) {
  const proto = HTMLElement.prototype as unknown as Record<string, unknown>;
  Object.defineProperty(proto, "clientWidth", { configurable: true, get: () => 317 });
  Object.defineProperty(proto, "scrollWidth", {
    configurable: true,
    get(this: HTMLElement) {
      const arrangement = this.dataset?.arrangement;
      if (arrangement === undefined) return 0;
      return fits(arrangement, this.querySelectorAll("thead th").length) ? 317 : 1000;
    },
  });
  try {
    run();
  } finally {
    delete proto.clientWidth;
    delete proto.scrollWidth;
  }
}

/** The phone the lab measured: a four-metric table (5 header cells) overflows the full and the short grid; the compact grid fits. */
const PHONE = (arrangement: string, headerCells: number) => arrangement === "compactGrid" || headerCells < 5;
/** A narrower phone: the compact grid overflows too. */
const NARROW = (_arrangement: string, headerCells: number) => headerCells < 5;

const arrangementNow = () => host.querySelector("[data-arrangement]")?.getAttribute("data-arrangement");

function withRootFont(px: number) {
  const real = window.getComputedStyle.bind(window);
  jest.spyOn(window, "getComputedStyle").mockImplementation(((el: Element) =>
    el === document.documentElement ? ({ fontSize: `${px}px` } as unknown as CSSStyleDeclaration) : real(el)) as typeof window.getComputedStyle);
}

/** Each compact/short grid row: the visible label, the spoken full name, and each cell's figure text and class. */
function compactRows() {
  return Array.from(host.querySelectorAll("table tbody tr")).map((tr) => {
    const name = tr.querySelector("th span span") as HTMLElement;
    const visible = name.querySelector("span")?.textContent ?? name.textContent;
    return {
      visible,
      spokenName: name.querySelector(".sr-only")?.textContent ?? visible,
      color: name.style.color,
      cells: Array.from(tr.querySelectorAll("td")).map((td) => (td.querySelector('[aria-hidden="true"]') ?? td).textContent),
      figureClasses: Array.from(tr.querySelectorAll("td")).map((td) => td.querySelector('[aria-hidden="true"]')?.className ?? ""),
      spoken: Array.from(tr.querySelectorAll("td .sr-only")).map((x) => x.textContent),
    };
  });
}

describe("FQ1 — the shared matrix's opt-in compact grid", () => {
  it("lists the arrangements: the default (hockey) path is exactly grid → shortGrid → pairs; only the opt-in adds compactGrid", () => {
    expect(matrixArrangements(false)).toEqual(["grid", "shortGrid", "pairs"]);
    expect(matrixArrangements(true)).toEqual(["pairs"]);
    expect(matrixArrangements(false, false)).toEqual(["grid", "shortGrid", "pairs"]);
    expect(matrixArrangements(false, true)).toEqual(["grid", "shortGrid", "compactGrid", "pairs"]);
    expect(matrixArrangements(true, true)).toEqual(["pairs"]);
  });

  it("the DEFAULT matrix (what hockey renders) never reaches compactGrid and keeps its exact classes", () => {
    const headline = view(model(bears[0], null, BEARS_NOW[0])).headline;
    withForcedLayout(PHONE, () => {
      render(<HockeyJourneyMatrix headline={headline} />);
      expect(arrangementNow()).toBe("pairs");
    });
    // A fresh mount (the fit search keeps its step for unchanged content), where nothing overflows:
    // the full grid with today's exact cell strings.
    act(() => root.unmount());
    root = createRoot(host);
    withForcedLayout(() => true, () => {
      render(<HockeyJourneyMatrix headline={headline} inlineProvenance={false} />);
      expect(arrangementNow()).toBe("grid");
      const th = host.querySelector("table thead th[scope='col']:not(:first-child)") as HTMLElement;
      expect(th.className).toBe("px-1 py-2 text-center align-bottom text-sm font-semibold text-text-secondary");
      expect(th.querySelector("span")?.className).toBe("mx-auto block min-w-16 max-w-[7.5rem]");
      const td = host.querySelector("table tbody td") as HTMLElement;
      expect(td.className).toBe("px-1 py-3 text-center align-middle");
      expect(td.querySelector(":scope > span")?.className).toBe("mx-auto block min-w-16 max-w-[7.5rem]");
    });
  });

  it("Bears t0 at a phone width: compactGrid with all eight values by side, away first, in display order, type sizes unchanged", () => {
    const m = model(bears[0], null, BEARS_NOW[0]);
    const v = view(m);
    withForcedLayout(PHONE, () => {
      render(<FootballJourneySection model={m} onOpenForecast={() => {}} />);
      expect(arrangementNow()).toBe("compactGrid");
      expect(headerTitles()).toEqual(["Team", "Opened chance", "Current chance", "Score", "Projected final"]);
      const rows = compactRows();
      expect(rows.map((r) => [r.visible, r.spokenName, r.cells])).toEqual([
        ["Patriots", "New England Patriots", ["41%", "21%", "21", "28"]],
        ["Bears", "Chicago Bears", ["59%", "79%", "27", "33"]],
      ]);
      expect(rows.flatMap((r) => r.cells)).toHaveLength(8);
      expect(rows[0].spoken).toEqual(["41 percent", "21 percent", "21 points", "28 points"]);
      expect(rows[1].spoken).toEqual(["59 percent", "79 percent", "27 points", "33 points"]);
      // Type sizes unchanged: the lead (Current chance) is the large figure, every other value text-xl, headers text-sm.
      for (const r of rows) {
        expect(r.figureClasses.map((c) => (c.includes("text-3xl") ? "3xl" : c.includes("text-xl") ? "xl" : "?"))).toEqual([
          "xl",
          "3xl",
          "xl",
          "xl",
        ]);
      }
      for (const th of Array.from(host.querySelectorAll("table thead th[scope='col']")).slice(1)) {
        expect(th.className).toMatch(/\btext-sm\b/);
        expect(th.className).toMatch(/\bpx-0\.5\b/);
        expect(th.querySelector("span")?.className).toBe("mx-auto block min-w-0 max-w-[7.5rem]");
      }
      // Identity: each team's tint stays on its own name.
      const asStyled = (tint: string | null) => {
        const probe = document.createElement("span");
        if (tint) probe.style.color = tint;
        return probe.style.color;
      };
      expect(rows.map((r) => r.color)).toEqual([asStyled(v.headline.away.tint), asStyled(v.headline.home.tint)]);
    });
  });

  it("falls back to the readable pairs when the compact grid overflows too, still all eight values by side", () => {
    withForcedLayout(NARROW, () => {
      render(<FootballJourneySection model={model(bears[0], null, BEARS_NOW[0])} />);
      expect(arrangementNow()).toBe("pairs");
      const blocks = Array.from(host.querySelectorAll('[data-arrangement] [role="group"]')).map((g) => [
        g.getAttribute("aria-label"),
        Array.from(g.querySelectorAll("dd")).map((dd) => (dd.querySelector('[aria-hidden="true"]') ?? dd).textContent),
      ]);
      expect(blocks).toEqual([
        ["New England Patriots", ["41%", "21%", "21", "28"]],
        ["Chicago Bears", ["59%", "79%", "27", "33"]],
      ]);
    });
  });

  it("at an accessibility text size (200%: root font 32 px) goes straight to pairs, compact option or not", () => {
    withRootFont(32);
    withForcedLayout(PHONE, () => {
      render(<FootballJourneySection model={model(bears[0], null, BEARS_NOW[0])} />);
      expect(arrangementNow()).toBe("pairs");
    });
  });

  it("re-fits on the SAME mount: content changes reset the search and recover the compact grid when it fits again", () => {
    let compactFits = true;
    withForcedLayout((a, n) => (a === "compactGrid" ? compactFits : n < 5), () => {
      // Narrow content first: two metrics fit the full grid.
      render(<FootballJourneySection model={model(rams, ramsHistory, RAMS_NOW)} />);
      expect(arrangementNow()).toBe("grid");
      // Four metrics on the same mount: steps down to the compact grid.
      render(<FootballJourneySection model={model(bears[0], null, BEARS_NOW[0])} />);
      expect(arrangementNow()).toBe("compactGrid");
      // TEST MUTATION of the layout: the compact grid stops fitting; a content change (t1) re-fits to pairs.
      compactFits = false;
      render(<FootballJourneySection model={model(bears[1], null, BEARS_NOW[1])} />);
      expect(arrangementNow()).toBe("pairs");
      // It fits again; the next content change (t2) starts the search over and recovers the compact grid.
      compactFits = true;
      render(<FootballJourneySection model={model(bears[2], null, BEARS_NOW[2])} />);
      expect(arrangementNow()).toBe("compactGrid");
      expect(compactRows().map((r) => r.cells)).toEqual([
        ["41%", "21%", "21", "26"],
        ["59%", "79%", "27", "32"],
      ]);
      // Three metrics (suspended, TEST MUTATION): the full grid, then back to compact for four.
      render(<FootballJourneySection model={model(mutate(bears[0], { status: "suspended" }), null, BEARS_NOW[0])} />);
      expect(arrangementNow()).toBe("grid");
      render(<FootballJourneySection model={model(bears[0], null, BEARS_NOW[0])} />);
      expect(arrangementNow()).toBe("compactGrid");
    });
  });
});

describe("FQ1 — one action group under the chart, each action behind its own gate", () => {
  const actions = () =>
    Array.from(host.querySelectorAll("[data-football-actions] > button")).map((b) => b.getAttribute("data-football-control"));

  it("orders chart, then 'Open forecast comparison', then 'Open win history', with no action duplicated", () => {
    const onOpenForecast = jest.fn();
    const onOpenHistory = jest.fn();
    render(<FootballJourneySection model={model(rams, ramsHistory, RAMS_NOW)} onOpenForecast={onOpenForecast} onOpenHistory={onOpenHistory} />);
    const group = host.querySelector("[data-football-actions]") as HTMLElement;
    const key = host.querySelector("[data-line-key]") as HTMLElement;
    expect(key.compareDocumentPosition(group) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(actions()).toEqual(["forecast", "history"]);
    expect(Array.from(group.querySelectorAll("button")).map((b) => b.textContent)).toEqual(["Open forecast comparison", "Open win history"]);
    expect(host.querySelectorAll('[data-football-control="forecast"]')).toHaveLength(1);
    expect(host.querySelectorAll('[data-football-control="history"]')).toHaveLength(1);
    expect(group.className).toMatch(/\bflex-wrap\b/);
    for (const b of Array.from(group.querySelectorAll("button"))) expect(b.className).toMatch(/\bmin-h-11\b/);
    // Nothing above the chart is an action any more.
    const matrix = host.querySelector("[data-hockey-matrix]") as HTMLElement;
    for (const b of Array.from(host.querySelectorAll("[data-football-control]"))) {
      expect(matrix.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
      expect(key.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    }
    expect(onOpenForecast).not.toHaveBeenCalled();
    expect(onOpenHistory).not.toHaveBeenCalled();
    click(control("forecast")!);
    click(control("history")!);
    expect([onOpenForecast.mock.calls.length, onOpenHistory.mock.calls.length]).toEqual([1, 1]);
  });

  it("keeps each gate: one callback gives one action; no callback, or no admitted destination, gives no group", () => {
    const m = model(rams, ramsHistory, RAMS_NOW);
    render(<FootballJourneySection model={m} onOpenHistory={() => {}} />);
    expect(actions()).toEqual(["history"]);
    render(<FootballJourneySection model={m} onOpenForecast={() => {}} />);
    expect(actions()).toEqual(["forecast"]);
    render(<FootballJourneySection model={m} />);
    expect(host.querySelector("[data-football-actions]")).toBeNull();
    // Bears holds no history body: only the forecast action, whatever the host passes.
    render(<FootballJourneySection model={model(bears[0], null, BEARS_NOW[0])} onOpenForecast={() => {}} onOpenHistory={() => {}} />);
    expect(actions()).toEqual(["forecast"]);
    // Jaguars final admits neither destination: no group at all.
    render(<FootballJourneySection model={model(jagFinal, null, JAG_FINAL_NOW)} onOpenForecast={() => {}} onOpenHistory={() => {}} />);
    expect(host.querySelector("[data-football-actions]")).toBeNull();
    // Jaguars live with its own history: only the history action.
    render(<FootballJourneySection model={model(jagLive, jagLiveHistory, JAG_LIVE_NOW)} onOpenForecast={() => {}} onOpenHistory={() => {}} />);
    expect(actions()).toEqual(["history"]);
  });
});
