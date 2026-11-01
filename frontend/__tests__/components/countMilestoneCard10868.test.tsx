/** @jest-environment jsdom */
/**
 * #10868 S2a — `CountMilestoneCard`, the thin exported wrapper over the
 * EXISTING goals milestone leaf in `SoccerMatchStories.tsx` (its private
 * chart, axis, key and strip helpers, unmoved).
 *
 * SHIP: baseball before/live run milestones reuse the approved visual with
 * clear probability phases and no invented first selection. This file proves
 * the seam only; the baseball adapter and page binding are later increments.
 *
 * INPUTS, labelled per test:
 *   - RETAINED — `../lib/soccerMatch10868.fixtures.json`, read-only: the live
 *     Valladolid–Albacete bodies at their own capture clock, built by the real
 *     `buildSoccerMatch` under the fixture's CONSTRUCTED owner admission (no
 *     production owner supplies a story admission), and the bridge's own pass
 *     from the same inputs (`buildSoccerCardPass`).
 *   - CONSTRUCTED — named where made, always on a deep copy of that built
 *     card: the owner default moved to the second milestone or set to null, a
 *     milestone removed, an id duplicated.
 *
 * No fixture is edited and nothing is fetched. jsdom lays nothing out: these
 * prove what is drawn, chosen and offered, never fit or geometry.
 */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import fixtures from "../lib/soccerMatch10868.fixtures.json";
import type { EventDetailResponse, EventHistoryResponse } from "@/lib/types";
import type { GameMarketsResponse } from "@/lib/api";
import { buildSoccerMatch, type SoccerMatchAdmission } from "@/lib/eventPage10868/soccerMatch";
import { buildSoccerCardPass } from "@/lib/eventPage10868/soccerCardOriginals";
import type {
  SoccerCurrent,
  SoccerGoalsCard,
  SoccerGoalsMilestone,
  SoccerPregame,
  SoccerStoryCard,
  SoccerStoryStream,
} from "@/lib/eventPage10868/soccerMatchTypes";
import SoccerMatchStories, { CountMilestoneCard, SOCCER_DETAILS_WORDS } from "@/components/event/eventpage10868/SoccerMatchStories";

// ─── Inputs ────────────────────────────────────────────────────────────────

type BodyKey = keyof typeof fixtures.bodies;
const parsed = (key: BodyKey) => JSON.parse(fixtures.bodies[key].raw) as Record<string, unknown>;
const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x)) as T;
const LIVE_NOW = Date.parse(fixtures.provenance.clocks.liveNow);
/** CONSTRUCTED owner metadata (the fixture's, from the native tests). */
const LIVE = (fixtures.constructed as unknown as { liveAdmission: SoccerMatchAdmission }).liveAdmission;

/** RETAINED live bodies, built ONCE by the real builder, and the bridge's pass from the same inputs. */
function liveBuilt() {
  const event = parsed("liveDetail") as unknown as EventDetailResponse;
  const history = parsed("liveHistory") as unknown as EventHistoryResponse;
  const gameMarkets = parsed("liveMarkets") as unknown as GameMarketsResponse;
  const page = buildSoccerMatch({
    event,
    history,
    gameMarkets,
    admitted: LIVE,
    halvesAdmission: "explicit",
    host: { nowMs: LIVE_NOW, hero: null, probabilityObservedAt: null },
  });
  return { page, pass: buildSoccerCardPass({ event, gameMarkets, admission: LIVE, nowMs: LIVE_NOW, page }) };
}
const BUILT = liveBuilt();

function goalsOf(cards: readonly SoccerStoryCard[]): SoccerGoalsCard {
  for (const c of cards) if (c.id === "goals") return c;
  throw new Error("no goals card");
}
/** The built goal-milestone card (RETAINED). */
const GOALS = goalsOf(BUILT.page.stories.cards);
const IDS = GOALS.milestones.map((m) => m.id);
const LABELS = GOALS.milestones.map((m) => m.label);

/** The wrapper's input: a deep copy of the leaf's own card WITHOUT its soccer discriminator, optionally edited (CONSTRUCTED). */
function input(edit?: (card: Omit<SoccerGoalsCard, "id">) => void): Omit<SoccerGoalsCard, "id"> {
  const { id: _discriminator, ...rest } = clone(GOALS);
  if (edit) edit(rest);
  return rest;
}
/** A one-card soccer stream, for the existing consumer. */
const oneCard = (card: SoccerGoalsCard): SoccerStoryStream => ({
  scope: "soccer:one-card",
  heading: "Stories",
  cards: [card],
  manualStatus: null,
  storiesLabel: "Stories",
  emptyWords: "",
});

const pregameWords = (p: SoccerPregame) => (p.kind === "value" ? p.observation.text : p.words);
const currentWords = (c: SoccerCurrent) => (c.kind === "recorded" ? c.observation.text : c.words);
const hasPregameMark = (m: SoccerGoalsMilestone) => m.pregame.kind === "value";

// ─── Harness ───────────────────────────────────────────────────────────────

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
});

const noop = () => undefined;
function show(card: Omit<SoccerGoalsCard, "id">, heldId: string | undefined, onChoose: (id: string) => void = noop) {
  act(() => root.render(<CountMilestoneCard card={card} heldId={heldId} onChoose={onChoose} />));
}
function click(el: Element) {
  act(() => {
    el.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
}
const card = () => host.querySelector('[data-soccer-card="goals"]');
const chips = () => Array.from(host.querySelectorAll<HTMLButtonElement>("li > button[aria-pressed]"));
const chipLabel = (b: HTMLButtonElement) => b.querySelector("span")?.textContent ?? null;
const pressed = () => chips().filter((b) => b.getAttribute("aria-pressed") === "true").map(chipLabel);
const chosenId = () => host.querySelector("[data-soccer-chosen]")?.getAttribute("data-soccer-chosen") ?? null;
const unavailable = () => host.querySelector("[data-soccer-selection-unavailable]");
const markOf = (id: string) => host.querySelector(`[data-milestone="${id}"] [data-mark="pregame"]`);
const axisLabelOf = (i: number) => host.querySelector(`[data-axis-labels="quantity"] [data-axis-label="${i}:${IDS[i]}"]`);
const detailsControls = () =>
  Array.from(host.querySelectorAll("button")).filter((b) => (b.textContent ?? "").startsWith(SOCCER_DETAILS_WORDS.open));

// ─── Tests ─────────────────────────────────────────────────────────────────

describe("CountMilestoneCard: the existing milestone profile through a thin, stateless wrapper", () => {
  it("RETAINED: draws the leaf's profile, phase key, every offered row and the input's names and readings", () => {
    show(input(), IDS[0]);
    // The wrapper supplies the discriminator, so the EXISTING renderer draws it: one card, one plot.
    expect(host.querySelectorAll("[data-soccer-card]")).toHaveLength(1);
    expect(card()).not.toBeNull();
    expect(host.querySelectorAll("[data-goals-plot]")).toHaveLength(1);
    expect(host.querySelector("[data-goals-plot]")?.getAttribute("data-goals-plot")).toBe("chart");
    expect(host.querySelector("h4")?.textContent).toBe(GOALS.title);
    expect(card()?.textContent).toContain(GOALS.eyebrow);
    expect(host.querySelector("figcaption")?.textContent).toBe(GOALS.chartTitle);
    expect(card()?.textContent).toContain(GOALS.quantityAxisTitle);
    // Every offered row on the plot and in the strip, in owner order.
    expect(Array.from(host.querySelectorAll("[data-milestone]")).map((el) => el.getAttribute("data-milestone"))).toEqual(IDS);
    expect(host.querySelectorAll('[data-mark="stem"]')).toHaveLength(GOALS.milestones.filter(hasPregameMark).length);
    expect(host.querySelector("ul[aria-label]")?.getAttribute("aria-label")).toBe(GOALS.name);
    expect(chips().map(chipLabel)).toEqual(LABELS);
    GOALS.milestones.forEach((m, i) => {
      const chip = chips()[i];
      expect(chip.textContent).toContain(pregameWords(m.pregame));
      expect(chip.textContent).toContain(GOALS.titles.pregame);
      if (m.current) expect(chip.textContent).toContain(currentWords(m.current));
      if (m.performance) expect(chip.textContent).toContain(m.performance);
    });
    // The phase key: exactly the marks this plot draws, each in the input's own phase words.
    const count = GOALS.actual?.kind === "count" ? GOALS.actual : null;
    const keyItems = Array.from(host.querySelectorAll("[data-goals-key-item]"));
    const expectedKey = [
      ...(GOALS.milestones.some(hasPregameMark) ? [["pregame", GOALS.titles.pregame]] : []),
      ...(GOALS.milestones.some((m) => m.current?.kind === "recorded") ? [["current", GOALS.currentTitles.recorded]] : []),
      ...(count ? [["actual", count.title]] : []),
    ];
    expect(keyItems.map((el) => [el.getAttribute("data-goals-key-item"), el.textContent])).toEqual(expectedKey);
    // The count is its own rule with its own words, never a chance.
    expect(host.querySelector('[data-axis-labels="actual"] [data-axis-label="actual"]')?.textContent ?? null).toBe(count ? count.ruleLabel : null);
    // The chosen row's readout is the leaf's own, for that exact row.
    expect(chosenId()).toBe(IDS[0]);
    expect(host.querySelector("[data-soccer-chosen]")?.textContent).toContain(LABELS[0]);
  });

  it("RETAINED: the plot and strip are the SAME renderer's markup as the soccer stream's, for the same card and choice (CONSTRUCTED default on row 2)", () => {
    const onRow2 = (c: Omit<SoccerGoalsCard, "id">) => (c.defaultId = IDS[1]);
    act(() => root.render(<SoccerMatchStories stream={oneCard({ ...input(onRow2), id: "goals" })} />));
    const streamFigure = card()?.querySelector("figure")?.outerHTML;
    const streamStrip = card()?.querySelector("ul[aria-label]")?.outerHTML;
    expect(streamFigure).toBeTruthy();
    act(() => root.unmount());
    root = createRoot(host);
    show(input(onRow2), undefined);
    expect(card()?.querySelector("figure")?.outerHTML).toBe(streamFigure);
    expect(card()?.querySelector("ul[aria-label]")?.outerHTML).toBe(streamStrip);
  });
});

describe("the opening choice: the owner default, or nothing — never an invented first row", () => {
  it("no held id + a real default chooses exactly that row, not the first (CONSTRUCTED default on row 2)", () => {
    show(
      input((c) => (c.defaultId = IDS[1])),
      undefined,
    );
    expect(pressed()).toEqual([LABELS[1]]);
    expect(chosenId()).toBe(IDS[1]);
    expect(unavailable()).toBeNull();
  });

  it("no held id + a null default chooses NONE: no pressed row, readout, emphasis or unavailable message (CONSTRUCTED null default)", () => {
    // Baselines from the renderer itself (no CSS string pinned): row 1 chosen, row 2 not.
    show(input(), IDS[0]);
    const chosenMark = markOf(IDS[0])?.className;
    const plainMark = markOf(IDS[1])?.className;
    const chosenLabel = axisLabelOf(0)?.className;
    const plainLabel = axisLabelOf(1)?.className;
    expect(chosenMark).not.toBe(plainMark); // the emphasis is real, so the check below is not vacuous
    expect(chosenLabel).not.toBe(plainLabel);
    show(
      input((c) => (c.defaultId = null)),
      undefined,
    );
    expect(pressed()).toEqual([]);
    expect(chosenId()).toBeNull();
    expect(unavailable()).toBeNull();
    expect(card()?.textContent).not.toContain(GOALS.selectionUnavailable);
    // No row is emphasised: every mark and quantity label wears the unchosen form, the first included.
    GOALS.milestones.forEach((m, i) => {
      if (hasPregameMark(m)) expect({ id: m.id, mark: markOf(m.id)?.className }).toEqual({ id: m.id, mark: plainMark });
      expect({ i, label: axisLabelOf(i)?.className }).toEqual({ i, label: plainLabel });
    });
    // Every row stays choosable.
    expect(chips().every((b) => !b.disabled)).toBe(true);
  });

  it("the existing soccer consumer keeps its first-row opening with a null default (CONSTRUCTED null default in the stream)", () => {
    const nullDefault = { ...input((c) => (c.defaultId = null)), id: "goals" as const };
    act(() => root.render(<SoccerMatchStories stream={oneCard(nullDefault)} />));
    expect(pressed()).toEqual([LABELS[0]]);
    expect(chosenId()).toBe(IDS[0]);
    expect(unavailable()).toBeNull();
  });
});

describe("the held id belongs to the host", () => {
  it("a deliberate tap calls onChoose once; the stateless wrapper moves only when the supplied held id changes", () => {
    const onChoose = jest.fn();
    const nullDefault = input((c) => (c.defaultId = null)); // CONSTRUCTED
    show(nullDefault, undefined, onChoose);
    expect(onChoose).not.toHaveBeenCalled(); // nothing is chosen on the host's behalf
    click(chips()[1]);
    expect(onChoose).toHaveBeenCalledTimes(1);
    expect(onChoose).toHaveBeenLastCalledWith(IDS[1]);
    expect(pressed()).toEqual([]); // the host has not moved yet
    expect(chosenId()).toBeNull();
    show(nullDefault, IDS[1], onChoose);
    expect(pressed()).toEqual([LABELS[1]]);
    expect(chosenId()).toBe(IDS[1]);
    show(nullDefault, IDS[1], onChoose); // a re-render calls nothing
    expect(onChoose).toHaveBeenCalledTimes(1);
  });

  it("a missing or duplicated held id is the leaf's unavailable state with no substitute, and its return restores it exactly once (CONSTRUCTED)", () => {
    const held = IDS[1];
    const missing = input((c) => (c.milestones = c.milestones.filter((m) => m.id !== held)));
    const duplicated = input((c) => (c.milestones[2].id = held));
    show(missing, held);
    expect(unavailable()?.getAttribute("data-soccer-selection-unavailable")).toBe("missing");
    expect(unavailable()?.textContent).toBe(GOALS.selectionUnavailable);
    expect(pressed()).toEqual([]); // never the default or the first
    expect(chosenId()).toBeNull();
    show(input(), held);
    expect(unavailable()).toBeNull();
    expect(pressed()).toEqual([LABELS[1]]);
    show(duplicated, held);
    expect(unavailable()?.getAttribute("data-soccer-selection-unavailable")).toBe("duplicate");
    expect(pressed()).toEqual([]);
    expect(chosenId()).toBeNull();
    // A duplicated id names nobody, so neither copy can be chosen.
    expect(chips().filter((b) => b.disabled).map(chipLabel)).toEqual([LABELS[1], LABELS[2]]);
    show(input(), held);
    expect(unavailable()).toBeNull();
    expect(pressed()).toEqual([LABELS[1]]);
    expect(host.querySelectorAll("[data-soccer-chosen]")).toHaveLength(1);
    expect(chosenId()).toBe(held);
  });
});

describe("no Details through the wrapper", () => {
  it("RETAINED: the soccer stream with this render's pass offers the goal card's Details; the wrapper on the same card, with a row chosen, offers none", () => {
    act(() => root.render(<SoccerMatchStories stream={BUILT.page.stories} cardPass={BUILT.pass} />));
    expect(Array.from(host.querySelectorAll("[data-soccer-details-entry]")).map((e) => e.getAttribute("data-soccer-details-entry"))).toEqual(["goals"]);
    const chosenInStream = chosenId();
    expect(chosenInStream).not.toBeNull();
    act(() => root.unmount());
    root = createRoot(host);
    show(input(), chosenInStream ?? undefined);
    expect(chosenId()).toBe(chosenInStream);
    expect(host.querySelectorAll("[data-soccer-details-entry]")).toHaveLength(0);
    expect(detailsControls()).toHaveLength(0);
    for (const id of IDS) {
      show(input(), id);
      expect(host.querySelectorAll("[data-soccer-details-entry]")).toHaveLength(0);
      expect(detailsControls()).toHaveLength(0);
    }
  });
});
