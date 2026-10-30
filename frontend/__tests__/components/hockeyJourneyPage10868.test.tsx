/** @jest-environment jsdom */
/**
 * #10868 — the web hockey journey screen renders its view model and its
 * controls work: About is a real disclosure, the story stream moves only on
 * Previous / Next (no timer), All props opens, and the history draws each run
 * as its own path. PREPARED, NOT RUN (quiet-CPU hold; the lead runs it under a
 * grant). Bodies: the verbatim subsets documented in
 * `__tests__/lib/hockeyJourney10868.test.ts` (15169793, Wild 4–1 Bruins, final;
 * 15338496, Devils at Golden Knights). CONSTRUCTED, and named where used: a
 * missing history response; a live read of 15338496 with one row's
 * `observed_at` changed; the final markets without one player's points rows;
 * a before-phase card carrying a later count, result and in-game reading as a
 * negative control; and forced element widths for the matrix's fit steps
 * (jsdom lays nothing out, so these prove the stepping logic, never real fit —
 * real fit is proved only by browser views at 375 / 393 px, normal and 200%
 * text, under grant I).
 */
import React from "react";
import { createRoot, type Root } from "react-dom/client";
import { act } from "react-dom/test-utils";
import fixtures from "../lib/hockeyJourney10868.fixtures.json";
import type { EventDetailResponse, EventHistoryResponse } from "@/lib/types";
import type { GameMarketsResponse } from "@/lib/api";
import {
  buildHockeyJourney,
  hockeyJourneyContribution,
  hockeyJourneyOriginals,
  NO_HELD_CHOICE,
  type HockeyJourneyContribution,
} from "@/lib/eventPage10868/hockeyJourney";
import HockeyJourneyPage from "@/components/event/eventpage10868/HockeyJourneyPage";
import HockeyJourneyAllProps from "@/components/event/eventpage10868/HockeyJourneyAllProps";
import HockeyJourneyContributionCard from "@/components/event/eventpage10868/HockeyJourneyContributionCard";
import HockeyJourneyMatrix, { matrixArrangements } from "@/components/event/eventpage10868/HockeyJourneyMatrix";

const journey = buildHockeyJourney({
  event: fixtures.finalDetail as unknown as EventDetailResponse,
  history: fixtures.finalHistory as unknown as EventHistoryResponse,
  gameMarkets: fixtures.finalMarkets as unknown as GameMarketsResponse,
  host: { nowMs: Date.parse("2026-10-11T04:56:41Z"), hero: null, probabilityObservedAt: null },
});

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

function button(label: string): HTMLButtonElement {
  const found = Array.from(host.querySelectorAll("button")).find((b) => (b.textContent ?? "").startsWith(label));
  if (!found) throw new Error(`no button "${label}"`);
  return found;
}

function click(el: Element) {
  act(() => {
    el.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
}

it("prints the final matrix's values and verdicts as text", () => {
  act(() => root.render(<HockeyJourneyPage journey={journey} />));
  const table = host.querySelector("table");
  expect(table?.textContent).toContain("66%");
  expect(table?.textContent).toContain("34%");
  expect(table?.textContent).toContain("Won");
  expect(table?.textContent).toContain("Lost");
  expect(table?.textContent).toContain("No pregame forecast");
  expect(host.querySelector("h2")?.textContent).toBe("Final: Minnesota Wild 4–1 Boston Bruins");
});

it("opens and closes About with a real button", () => {
  act(() => root.render(<HockeyJourneyPage journey={journey} />));
  const about = button("About these sources");
  const region = document.getElementById(about.getAttribute("aria-controls") ?? "");
  expect(about.getAttribute("aria-expanded")).toBe("false");
  expect(region?.hidden).toBe(true);
  click(about);
  expect(about.getAttribute("aria-expanded")).toBe("true");
  expect(region?.hidden).toBe(false);
  expect(region?.textContent).toContain("Pregame chance: Pre-match");
  click(about);
  expect(region?.hidden).toBe(true);
});

it("moves between stories only when the reader asks, and runs no interval", () => {
  const interval = jest.spyOn(window, "setInterval");
  act(() => root.render(<HockeyJourneyPage journey={journey} />));
  const storyTitle = () => host.querySelector("article h4")?.textContent;
  expect(storyTitle()).toBe("Points in context");
  click(button("Next"));
  expect(storyTitle()).toBe("Who creates the goals?");
  click(button("Previous"));
  expect(storyTitle()).toBe("Points in context");
  expect(interval).not.toHaveBeenCalled();
});

it("draws each multi-row run of each team as its own path, and opens All props", () => {
  act(() => root.render(<HockeyJourneyPage journey={journey} />));
  // Six home runs, one of them a single row (a mark, not a path); the away side mirrors them.
  expect(host.querySelectorAll('svg[role="img"] path')).toHaveLength(10);
  const entry = button("All 23 original outcomes");
  const list = document.getElementById(entry.getAttribute("aria-controls") ?? "");
  expect(list?.hidden).toBe(true);
  click(entry);
  expect(list?.hidden).toBe(false);
  expect(list?.textContent).toContain("Kirill Kaprizov 2+ points");
});

it("with no history response shows only the chart as unavailable, with no history control", () => {
  const missing = buildHockeyJourney({
    event: fixtures.finalDetail as unknown as EventDetailResponse,
    history: null, // CONSTRUCTED: no history response
    gameMarkets: fixtures.finalMarkets as unknown as GameMarketsResponse,
    host: { nowMs: Date.parse("2026-10-11T04:56:41Z"), hero: null, probabilityObservedAt: null },
  });
  act(() => root.render(<HockeyJourneyPage journey={missing} />));
  expect(host.textContent).toContain("History unavailable");
  expect(host.textContent).not.toContain("No recorded history");
  expect(host.querySelector('svg[role="img"]')).toBeNull();
  const labels = Array.from(host.querySelectorAll("button")).map((b) => b.textContent ?? "");
  expect(labels.some((l) => l.startsWith("History & source details"))).toBe(false);
  expect(labels.some((l) => /retry|try again/i.test(l))).toBe(false);
  // The rest of the page is still there.
  expect(host.querySelector("table")?.textContent).toContain("66%");
  expect(host.querySelector("article h4")?.textContent).toBe("Points in context");
  expect(labels.some((l) => l.startsWith("All 23 original outcomes"))).toBe(true);
});

it("during play a stale original shows no figure on its row; Details show the historical quote", () => {
  const live = { ...(fixtures.pregameDetail as unknown as EventDetailResponse), status: "live" } as EventDetailResponse; // CONSTRUCTED: status only
  const base = fixtures.pregameMarkets as unknown as GameMarketsResponse;
  const markets = {
    ...base,
    player_props: base.player_props.map((row) =>
      row.contributor_outcome_ids?.[0] === 256284771 ? { ...row, observed_at: "2026-10-30T22:05:00Z" } : row,
    ),
  } as GameMarketsResponse; // CONSTRUCTED: one row's observed_at
  const originals = hockeyJourneyOriginals(live, markets, Date.parse("2026-10-30T22:45:00Z"));
  act(() => root.render(<HockeyJourneyAllProps originals={originals} entryLabel="All 18 original outcomes" />));
  const row = Array.from(host.querySelectorAll("li")).find((li) => li.textContent?.includes("Jack Eichel 1+ points"))!;
  const face = row.querySelector("div")!;
  expect(face.textContent).toContain("No recent probability update");
  expect(face.textContent).not.toContain("%");
  const details = Array.from(row.querySelectorAll("button")).find((b) => (b.textContent ?? "").startsWith("Details"))!;
  const region = document.getElementById(details.getAttribute("aria-controls") ?? "");
  expect(region?.hidden).toBe(true);
  click(details);
  expect(region?.hidden).toBe(false);
  expect(region?.textContent).toContain("Last recorded probability (historical)");
  expect(region?.textContent).toContain("69%, recorded ");
  expect(region?.textContent).toContain(" · Kalshi");
});

const FINAL_NOW = Date.parse("2026-10-11T04:56:41Z");
const finalEvent = fixtures.finalDetail as unknown as EventDetailResponse;
const finalHistory = fixtures.finalHistory as unknown as EventHistoryResponse;
const finalMarkets = fixtures.finalMarkets as unknown as GameMarketsResponse;
const finalJourney = (markets: GameMarketsResponse, nowMs = FINAL_NOW) =>
  buildHockeyJourney({
    event: finalEvent,
    history: finalHistory,
    gameMarkets: markets,
    host: { nowMs, hero: null, probabilityObservedAt: null },
  });

function choose(select: HTMLSelectElement, value: string) {
  act(() => {
    select.value = value;
    select.dispatchEvent(new Event("change", { bubbles: true }));
  });
}

it("keeps the reader's held player through a refresh, and says so when that player is no longer served", () => {
  act(() => root.render(<HockeyJourneyPage journey={finalJourney(finalMarkets)} />));
  const card = () => host.querySelector("article")!;
  const select = () => card().querySelector("select") as HTMLSelectElement;
  const group = (name: string) => card().querySelector(`[role="group"][aria-label="${name} milestones"]`);
  // Before any choice: the first player.
  expect(group("Kirill Kaprizov")).not.toBeNull();
  choose(select(), "player:quinn hughes");
  const twoPlus = Array.from(group("Quinn Hughes")!.querySelectorAll("button")).find((b) => b.textContent?.includes("2+"))!;
  click(twoPlus);
  expect(twoPlus.getAttribute("aria-pressed")).toBe("true");

  // An unrelated refresh (same data, a minute later) rewrites nothing.
  act(() => root.render(<HockeyJourneyPage journey={finalJourney(finalMarkets, FINAL_NOW + 60_000)} />));
  const pressed = Array.from(group("Quinn Hughes")!.querySelectorAll('button[aria-pressed="true"]'));
  expect(pressed.map((b) => b.textContent?.includes("2+"))).toEqual([true]);

  // CONSTRUCTED: the same markets without Quinn Hughes's points rows; nothing else changes.
  const withoutHughes = {
    ...finalMarkets,
    player_props: finalMarkets.player_props.filter(
      (row) => !(row.market_name.endsWith(": Points") && row.outcome_name.startsWith("Quinn Hughes:")),
    ),
  } as GameMarketsResponse;
  act(() => root.render(<HockeyJourneyPage journey={finalJourney(withoutHughes)} />));
  expect(card().textContent).toContain("Selected player unavailable.");
  expect(group("Kirill Kaprizov")).toBeNull();
  expect(group("Max Shabanov")).toBeNull();
  // The chooser is still reachable, and shows no one else as chosen.
  expect(select()).not.toBeNull();
  expect(select().value).toBe("");

  // Only a new explicit choice substitutes.
  choose(select(), "player:kirill kaprizov");
  expect(card().textContent).not.toContain("Selected player unavailable.");
  expect(group("Kirill Kaprizov")).not.toBeNull();
});

it("before play shows no count, progress, in-game or result block — even when the input carries them", () => {
  const pregameDetail = fixtures.pregameDetail as unknown as EventDetailResponse;
  const pregameMarkets = fixtures.pregameMarkets as unknown as GameMarketsResponse;
  const built = hockeyJourneyContribution("points", pregameDetail, pregameMarkets, Date.parse("2026-10-30T20:13:55Z"))!;
  expect(built.phase).toBe("before");
  // CONSTRUCTED negative control: a later count, progress, in-game reading and result on a before-phase card.
  const card: HockeyJourneyContribution = {
    ...built,
    players: built.players.map((p, i) =>
      i !== 0
        ? p
        : {
            ...p,
            actual: { kind: "count", count: "7", unit: "points so far", breakdown: "3 goals + 4 assists", detail: "box" } as const,
            milestones: p.milestones.map((m) => ({
              ...m,
              current: { kind: "withheld", words: "No update since goal" } as const,
              progress: { status: "1 more for 2+", fraction: 0.5 },
              result: { kind: "missed", words: "Missed" } as const,
            })),
          },
    ),
  };
  act(() => root.render(<HockeyJourneyContributionCard card={card} held={NO_HELD_CHOICE} onHold={() => {}} />));
  const text = host.textContent ?? "";
  expect(text).toContain("69%");
  for (const banned of ["Count unavailable", "Count so far", "Final count", "points so far", "3 goals + 4 assists",
    "No update since goal", "1 more for 2+", "Missed", "MISS"]) {
    expect(text).not.toContain(banned);
  }
});

it("prints the matrix as aligned columns by default and leaves column sources to About", () => {
  act(() => root.render(<HockeyJourneyPage journey={journey} />));
  const matrix = host.querySelector("[data-hockey-matrix]")!;
  expect(matrix.querySelector("[data-arrangement]")?.getAttribute("data-arrangement")).toBe("grid");
  expect(matrix.querySelector("table")).not.toBeNull();
  expect(matrix.textContent).not.toContain("score observed");
  expect(matrix.textContent).not.toContain("Pre-match");
  const about = button("About these sources");
  click(about);
  const region = document.getElementById(about.getAttribute("aria-controls") ?? "");
  expect(region?.textContent).toContain("Final goals: ESPN · score observed");
  expect(region?.textContent).toContain("Pregame chance: Pre-match");
  // The game state and the result words stay in the headline.
  expect(host.querySelector("header")?.textContent).toContain("Final");
  expect(matrix.textContent).toContain("Won");
});

it("steps to short names, then to labelled pairs, only when the wider arrangement does not fit", () => {
  expect(matrixArrangements(true)).toEqual(["pairs"]);
  expect(matrixArrangements(false)).toEqual(["grid", "shortGrid", "pairs"]);
  const proto = HTMLElement.prototype as unknown as Record<string, unknown>;
  const overflowing = new Set<string>();
  Object.defineProperty(proto, "clientWidth", { configurable: true, get: () => 300 });
  Object.defineProperty(proto, "scrollWidth", {
    configurable: true,
    get(this: HTMLElement) {
      return overflowing.has(this.dataset?.arrangement ?? "") ? 1000 : 300;
    },
  });
  try {
    const { headline } = journey;
    // Only the full-name grid overflows: short names if the owner has any, else pairs.
    overflowing.add("grid");
    act(() => root.render(<HockeyJourneyMatrix key="a" headline={headline} inlineProvenance={false} />));
    const expected = headline.home.short || headline.away.short ? "shortGrid" : "pairs";
    expect(host.querySelector("[data-arrangement]")?.getAttribute("data-arrangement")).toBe(expected);
    if (expected === "shortGrid") {
      const rowHeads = Array.from(host.querySelectorAll('th[scope="row"]')).map((th) => th.textContent ?? "");
      // The short name shows; the full name is still there for a screen reader.
      expect(rowHeads[0]).toContain(headline.home.name);
    }
    // Neither grid fits: one labelled block per team, pairs kept together.
    overflowing.add("shortGrid");
    act(() => root.render(<HockeyJourneyMatrix key="b" headline={headline} inlineProvenance={false} />));
    expect(host.querySelector("[data-arrangement]")?.getAttribute("data-arrangement")).toBe("pairs");
    expect(host.querySelector("table")).toBeNull();
    const blocks = Array.from(host.querySelectorAll('[role="group"]'));
    expect(blocks.map((b) => b.getAttribute("aria-label"))).toEqual([headline.home.name, headline.away.name]);
    expect(blocks[0].querySelectorAll("dl")).toHaveLength(headline.matrix.groups.length);
    expect(Array.from(blocks[0].querySelectorAll("dt")).map((dt) => dt.textContent)).toEqual(
      headline.matrix.columns.map((c) => c.title),
    );
    expect(blocks[0].textContent).toContain("66%");
  } finally {
    delete proto.clientWidth;
    delete proto.scrollWidth;
  }
});
