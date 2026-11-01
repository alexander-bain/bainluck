/** @jest-environment jsdom */
/**
 * #10868 reader I2 — the baseball page's run-total card offers "Open full
 * card": the page-local run slot holds the scope, the chosen key and the
 * reader's open / could-not-open flags, and draws `MlbRunTotalsReader` (I1,
 * over the unchanged `SoccerMatchReader` shell) with the SAME phase-agreed
 * input and the SAME selection as the page card.
 *
 * SHIP: the baseball page offers Open full card; an interested fan can explore
 * its run milestones comfortably, close it, and return to the same choice and
 * page position.
 *
 * Everything is drawn by the ACTUAL `buildMlbGame`, `MlbGamePage` and reader.
 *
 * INPUTS, labelled per test:
 *   - REAL — `../lib/mlbGame10868.fixtures.json` (White Sox at Astros
 *     15321836, final 3–7) and the whole retained FINAL `game_question_matrix`
 *     in `../lib/mlbRunTotals10868.fixtures.json`, joined onto the reduced
 *     markets body in-test (a CONSTRUCTED admission; neither fixture is
 *     edited).
 *   - CONSTRUCTED — every host value and clock; the live and before-first-pitch
 *     events (native `liveEdits` / `beforeEdits`); every before/live quote, pin
 *     and displayed pair; a lagging raw row; partial pairs; withdrawn and
 *     duplicated keys; same-scope passes with no matrix; another event's id;
 *     the page scroll offset. No genuine before/live specimen is claimed.
 *
 * jsdom implements no dialog behaviour; `showModal` / `close` are stubbed the
 * way `soccerMatchReader10868.test.tsx` stubs them (state only). These tests
 * prove state and wiring — what opens, what each view draws, what closes the
 * reader, where scroll and focus are sent — and the DOM order. They do NOT
 * prove real modality, focus containment, scroll locking, layout or fit at
 * 375 / 393 px or 200% text; the browser check is still owed.
 */
import React, { act, useLayoutEffect } from "react";
import { createRoot, type Root } from "react-dom/client";
import fixtures from "../lib/mlbGame10868.fixtures.json";
import runTotalsFixture from "../lib/mlbRunTotals10868.fixtures.json";
import type { EventDetailResponse, EventHistoryResponse } from "@/lib/types";
import type { GameMarketsResponse } from "@/lib/api";
import { HISTORY_WORDS } from "@/lib/eventPage10868/hockeyJourneyHistory";
import { MLB_RUN_TOTAL_WORDS } from "@/lib/eventPage10868/mlbRunTotals";
import type { HockeyJourneyTeam } from "@/lib/eventPage10868/hockeyJourneyTypes";
import { buildMlbGame, type MlbGameHost, type MlbGameModel, type MlbGameView } from "@/lib/eventPage10868/mlbGame";
import MlbGamePage, { MLB_HISTORY_ROW_LABEL } from "@/components/event/eventpage10868/MlbGamePage";
import { MLB_RUN_READER_WORDS } from "@/components/event/eventpage10868/MlbRunTotalsReader";
import { SOCCER_READER_WORDS } from "@/components/event/eventpage10868/SoccerMatchReader";

// ─── Inputs ────────────────────────────────────────────────────────────────

type Json = Record<string, unknown>;
const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x)) as T;
/** A deep copy with keys replaced — a TEST MUTATION (CONSTRUCTED). */
const mutate = <T,>(x: T, patch: Record<string, unknown>): T => ({ ...clone(x), ...patch });

const finalDetail = fixtures.finalDetail as unknown as EventDetailResponse;
const finalHistory = fixtures.finalHistory as unknown as EventHistoryResponse;
const finalMarkets = fixtures.finalMarkets as unknown as GameMarketsResponse;

/** REAL: the capture's retrieval instant. CONSTRUCTED: every other clock. */
const FINAL_NOW = Date.parse("2026-10-11T04:57:23.592725Z");
const LIVE_NOW = Date.parse("2026-10-01T00:16:30Z");
const LIVE_OBSERVED = "2026-10-01T00:15:57.061753Z";
const BEFORE_NOW = Date.parse("2026-09-30T20:59:00Z");
/** REAL: the retained game's listed start. */
const START_MS = Date.parse(finalDetail.commence_time);
const MIN = 60_000;
const iso = (ms: number) => new Date(ms).toISOString();
/** CONSTRUCTED: another event's id. */
const OTHER_ID = 15321837;

/** CONSTRUCTED: native `liveEdits` over the real final (the raw row keeps 3–7). */
const liveDetail = mutate(finalDetail, {
  status: "live",
  completed_at: null,
  hero_settled_result: null,
  hero_probability: null,
  hero_probability_away: null,
  hero_probability_source: null,
});
/** CONSTRUCTED: native `beforeEdits`, one minute before first pitch. */
const beforeDetail = mutate(finalDetail, {
  status: "scheduled",
  completed_at: null,
  home_score: null,
  away_score: null,
  hero_settled_result: null,
  hero_probability: null,
  hero_probability_away: null,
  hero_probability_source: null,
});

/** CONSTRUCTED host answers; every key explicit. The displayed final pair equals the retained row (3–7). */
const finalHost: MlbGameHost = {
  nowMs: FINAL_NOW,
  hero: null,
  probabilityObservedAt: null,
  deliveryInterrupted: false,
  liveClaimUnbacked: false,
  score: { home: 3, away: 7, observedAt: null },
  projectedFinal: null,
};
/** CONSTRUCTED: a displayed 3–6 during play (the raw row says 3–7), with its own clock. */
const liveHost: MlbGameHost = {
  nowMs: LIVE_NOW,
  hero: { homeProb: 0.001, awayProb: 0.999, homePct: 0, awayPct: 100, probSourceLabel: null },
  probabilityObservedAt: LIVE_OBSERVED,
  deliveryInterrupted: false,
  liveClaimUnbacked: false,
  score: { home: 3, away: 6, observedAt: LIVE_OBSERVED },
  projectedFinal: { home: 4, away: 7 },
};
const beforeHost: MlbGameHost = { ...finalHost, nowMs: BEFORE_NOW, score: null };

function model(
  event: EventDetailResponse,
  host: MlbGameHost,
  bodies: { history?: EventHistoryResponse | null; gameMarkets?: GameMarketsResponse | null } = {},
): MlbGameModel {
  return buildMlbGame({
    event,
    history: bodies.history === undefined ? finalHistory : bodies.history,
    gameMarkets: bodies.gameMarkets === undefined ? finalMarkets : bodies.gameMarkets,
    host,
  });
}
const view = (m: MlbGameModel): MlbGameView => {
  if (m.kind !== "game") throw new Error("refused");
  return m;
};

/** REAL: the whole retained matrix, a fresh copy each call. */
const ownMatrix = (): Json => clone(runTotalsFixture.game_question_matrix) as unknown as Json;
/** CONSTRUCTED admission: the reduced markets body with a matrix joined on. */
const withMatrix = (matrix: unknown, body: GameMarketsResponse = finalMarkets): GameMarketsResponse =>
  mutate(body, { game_question_matrix: matrix });
const isFullGameRuns = (q: Json) =>
  q.kind === "count_threshold" && (q.quantity as Json | null)?.key === "runs" && (q.period as Json | null)?.key === "full_game";
const lineOf = (q: Json) => (q.predicate as Json).line;
function overOfLine(m: Json, line: number): Json {
  const found = (m.questions as Json[]).filter((q) => isFullGameRuns(q) && lineOf(q) === line);
  if (found.length !== 1) throw new Error(`expected one full-game question at ${line}`);
  return (found[0].options as Json[])[0];
}
/** TEST MUTATION: one full-game line withdrawn. */
function withoutLine(m: Json, line: number): Json {
  m.questions = (m.questions as Json[]).filter((q) => !(isFullGameRuns(q) && lineOf(q) === line));
  return m;
}
/** TEST MUTATION: `line`'s Over option carrying `key` (the admission drops both copies). */
function carrying(m: Json, line: number, key: string): Json {
  overOfLine(m, line).option_key = key;
  return m;
}
/** CONSTRUCTED: the line's Over option published as a quoted value on its own clock. */
function quoteLine(m: Json, line: number, value: number, observedAt: string): void {
  const o = overOfLine(m, line);
  o.published = { ...(o.published as Json), value, value_state: "quoted", observed_at: observedAt };
}
/** CONSTRUCTED: an admitted pregame pin (comparable baseline). */
function pinLine(m: Json, line: number, probability: number, observedAt: string): void {
  overOfLine(m, line).comparison = {
    state: "comparable",
    reason: null,
    baseline: { basis: "pregame_pin", probability, observed_at: observedAt },
    latest: null,
    delta_points: null,
  };
}
/** CONSTRUCTED live readings over the REAL matrix: pins on 9.5 (40%) and 11.5 (30%); a recorded 20% on 11.5. */
function liveMilestoneMatrix(): Json {
  const m = ownMatrix();
  pinLine(m, 9.5, 0.4, iso(START_MS - 30 * MIN));
  pinLine(m, 11.5, 0.3, iso(START_MS - 30 * MIN));
  quoteLine(m, 11.5, 0.2, iso(LIVE_NOW - 2 * MIN));
  return m;
}
const finalWith = (m: unknown = ownMatrix(), host: MlbGameHost = finalHost) => model(finalDetail, host, { gameMarkets: withMatrix(m) });
const liveWith = (m: unknown = liveMilestoneMatrix(), host: MlbGameHost = liveHost, detail: EventDetailResponse = liveDetail) =>
  model(detail, host, { gameMarkets: withMatrix(m) });
const otherEvent = (detail: EventDetailResponse, host: MlbGameHost, gameMarkets: GameMarketsResponse) =>
  model(mutate(detail, { id: OTHER_ID }), host, { history: mutate(finalHistory, { event_id: OTHER_ID }), gameMarkets });
const otherBody = (matrix?: unknown) =>
  matrix === undefined ? mutate(finalMarkets, { event_id: OTHER_ID }) : withMatrix(matrix, mutate(finalMarkets, { event_id: OTHER_ID }));

const KEY_9_5 = "o:244311417";
const KEY_10_5 = "o:244311422";
const KEY_11_5 = "o:244311421";
const KEY_12_5 = "o:244311420";

// ─── Harness ───────────────────────────────────────────────────────────────

let host: HTMLDivElement;
let root: Root;
let showModalCalls: number;
/** CONSTRUCTED jsdom dialog stub (see header): state only, no browser modality. */
function stubShowModal(this: HTMLDialogElement) {
  showModalCalls += 1;
  this.setAttribute("open", "");
}
let pageScroll: jest.SpyInstance;
const dialogProto = HTMLDialogElement.prototype as unknown as { showModal?: () => void; close?: () => void };

/**
 * Every committed frame of a root render, read after that commit's DOM work:
 * the section's phase, the page card's scope and how many dialogs exist. A
 * reader left open into a new event or phase would show up here as a frame.
 */
const frames: Array<{ phase: string | null; card: string | null; dialogs: number }> = [];
function FrameProbe({ model: m }: { model: MlbGameModel }) {
  useLayoutEffect(() => {
    const card = Array.from(host.querySelectorAll("[data-mlb-run-totals]")).find((el) => !el.closest("dialog"));
    frames.push({
      phase: host.querySelector("section[data-mlb-game]")?.getAttribute("data-mlb-game") ?? null,
      card: card?.getAttribute("data-mlb-run-totals") ?? null,
      dialogs: document.querySelectorAll("dialog").length,
    });
  }, [m]);
  return null;
}
/** The page, then the probe, in every render (the page keeps one tree position). */
function Screen({ model: m }: { model: MlbGameModel }) {
  return (
    <>
      <MlbGamePage model={m} />
      <FrameProbe model={m} />
    </>
  );
}

beforeEach(() => {
  (globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  showModalCalls = 0;
  frames.length = 0;
  dialogProto.showModal = stubShowModal;
  dialogProto.close = function (this: HTMLDialogElement) {
    if (!this.hasAttribute("open")) return;
    this.removeAttribute("open");
    this.dispatchEvent(new Event("close"));
  };
  pageScroll = jest.spyOn(window, "scrollTo").mockImplementation(() => undefined);
  // CONSTRUCTED: the page is scrolled 640 px down when the reader opens.
  window.scrollY = 640;
  document.body.style.overflow = "";
});

afterEach(() => {
  act(() => root.unmount());
  host.remove();
  delete dialogProto.showModal;
  delete dialogProto.close;
  window.scrollY = 0;
  jest.restoreAllMocks();
});

const render = (m: MlbGameModel) => act(() => root.render(<Screen model={m} />));
/** A render whose commit may close the reader: flushes the shell's focus microtask. */
const renderSettled = async (m: MlbGameModel) => {
  await act(async () => {
    root.render(<Screen model={m} />);
  });
};
function click(el: Element) {
  act(() => {
    el.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
}
async function clickAndSettle(el: Element) {
  await act(async () => {
    el.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
}

const outside = (el: Element) => !el.closest("dialog");
const dialogs = () => Array.from(document.querySelectorAll("dialog"));
function reader(): HTMLDialogElement {
  const all = dialogs();
  if (all.length !== 1) throw new Error(`expected one reader, found ${all.length}`);
  return all[0];
}
function buttonIn(within: ParentNode, label: string): HTMLButtonElement {
  const found = Array.from(within.querySelectorAll("button")).find((b) => (b.textContent ?? "") === label);
  if (!found) throw new Error(`no button "${label}"`);
  return found;
}
const closeButton = () => buttonIn(reader(), SOCCER_READER_WORDS.close);
const pageCard = () => Array.from(host.querySelectorAll("[data-mlb-run-totals]")).find(outside) ?? null;
const readerCard = () => reader().querySelector("[data-mlb-run-totals]");
const entry = () => host.querySelector<HTMLButtonElement>("[data-mlb-run-reader-entry]");
const statusEl = () => host.querySelector("[data-mlb-run-reader-status]");
const historyRow = () => host.querySelector<HTMLElement>("[data-mlb-history-row]");
/** The row's children in order: each item by name, anything else by tag (the open dialog). */
const rowParts = () =>
  Array.from(historyRow()?.children ?? []).map((el) => el.getAttribute("data-mlb-row-item") ?? el.tagName.toLowerCase());
const historyChart = () => historyRow()?.children[0]?.querySelector("section") ?? null;
const historyDisclosure = () =>
  Array.from(host.querySelectorAll("button")).find((b) => outside(b) && b.textContent === HISTORY_WORDS.details) ?? null;
function allPropsEntry(): HTMLButtonElement {
  const found = Array.from(host.querySelectorAll("button")).find((b) => outside(b) && /original outcome/.test(b.textContent ?? ""));
  if (!found) throw new Error("no All props entry");
  return found;
}
const detailsButtons = () =>
  Array.from(host.querySelectorAll("button")).filter((b) => outside(b) && (b.textContent ?? "").startsWith("Details"));
const openDetails = () => detailsButtons().filter((b) => b.getAttribute("aria-expanded") === "true");

// The final leaf, inside one view.
const pressedIn = (card: Element | null) =>
  Array.from(card?.querySelectorAll("[data-run-choice]") ?? [])
    .filter((b) => b.getAttribute("aria-pressed") === "true")
    .map((b) => b.getAttribute("data-run-choice"));
function choiceIn(card: Element | null, key: string): HTMLButtonElement {
  const found = card?.querySelector<HTMLButtonElement>(`[data-run-choice="${key}"]`);
  if (!found) throw new Error(`no run line ${key}`);
  return found;
}
const headingIn = (card: Element | null) => card?.querySelector("[data-run-heading]")?.textContent ?? null;

// The milestones leaf, inside one view.
const msChips = (card: Element | null) =>
  Array.from(card?.querySelectorAll<HTMLButtonElement>('[data-soccer-card="goals"] li > button[aria-pressed]') ?? []);
const msLabel = (b: HTMLButtonElement) => b.querySelector("span")?.textContent ?? null;
const msChosen = (card: Element | null) => card?.querySelector("[data-soccer-chosen]")?.getAttribute("data-soccer-chosen") ?? null;
const msUnavailable = (card: Element | null) => card?.querySelector("[data-soccer-selection-unavailable]")?.textContent ?? null;
function msChip(card: Element | null, label: string): HTMLButtonElement {
  const found = msChips(card).filter((b) => msLabel(b) === label);
  if (found.length !== 1) throw new Error(`expected one milestone ${label}`);
  return found[0];
}

// The reader's compact context.
const context = () => reader().querySelector("[data-mlb-run-reader-context]");
const contextParts = () =>
  Array.from(context()?.querySelectorAll("[data-mlb-run-reader-team], [data-mlb-run-reader-score]") ?? []).map((el) => el.textContent);
const contextState = () => context()?.querySelector("[data-mlb-run-reader-state]")?.textContent ?? null;
const shown = (team: HockeyJourneyTeam) => team.short ?? team.name;

// ─── One held key, two views ───────────────────────────────────────────────

describe("one held key: the page card and the reader share the page's selection", () => {
  it("REAL final: the entry sits in the run-total item; a page choice opens chosen; a reader choice is the page's; Close and reopen keep it", async () => {
    render(finalWith());
    expect(dialogs()).toHaveLength(0);
    const e = entry()!;
    expect(e.textContent).toBe(SOCCER_READER_WORDS.openCard);
    expect(e.getAttribute("aria-label")).toBe(`${SOCCER_READER_WORDS.openCard}: ${MLB_RUN_READER_WORDS.title}`);
    expect(e.closest("[data-mlb-row-item]")?.getAttribute("data-mlb-row-item")).toBe("runTotals");
    expect(pageCard()!.compareDocumentPosition(e) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(pageCard()!.contains(e)).toBe(false); // the card itself still offers no reader or Details
    click(choiceIn(pageCard(), KEY_10_5));
    click(e);
    expect(showModalCalls).toBe(1);
    expect(reader().open).toBe(true);
    expect(e.disabled).toBe(true);
    expect(pressedIn(readerCard())).toEqual([KEY_10_5]);
    expect(readerCard()?.querySelector("[data-run-plot]")?.getAttribute("data-run-plot")).toBe("expanded");
    click(choiceIn(readerCard(), KEY_11_5));
    expect([pressedIn(readerCard()), pressedIn(pageCard())]).toEqual([[KEY_11_5], [KEY_11_5]]);
    expect([headingIn(readerCard()), headingIn(pageCard())]).toEqual(["Over 11.5 runs", "Over 11.5 runs"]);
    await clickAndSettle(closeButton());
    expect(dialogs()).toHaveLength(0);
    expect(e.disabled).toBe(false);
    expect(pressedIn(pageCard())).toEqual([KEY_11_5]);
    click(e);
    expect(showModalCalls).toBe(2);
    expect(pressedIn(readerCard())).toEqual([KEY_11_5]);
  });

  it("same-scope updates re-read in place: one showModal, the key kept, no refocus, no scroll (CONSTRUCTED refresh, then a displayed 4–8)", () => {
    render(finalWith());
    click(entry()!);
    const d = reader();
    click(choiceIn(readerCard(), KEY_10_5));
    const chip = choiceIn(readerCard(), KEY_12_5);
    act(() => chip.focus());
    render(finalWith(ownMatrix(), { ...finalHost, nowMs: FINAL_NOW + MIN }));
    render(finalWith(ownMatrix(), { ...finalHost, score: { home: 4, away: 8, observedAt: null } }));
    expect(reader()).toBe(d);
    expect(showModalCalls).toBe(1);
    expect(readerCard()?.querySelector("[data-run-total]")?.textContent).toBe("12");
    expect(pageCard()?.querySelector("[data-run-total]")?.textContent).toBe("12");
    expect([pressedIn(readerCard()), pressedIn(pageCard())]).toEqual([[KEY_10_5], [KEY_10_5]]);
    expect(document.activeElement).toBe(chip);
    expect(pageScroll).not.toHaveBeenCalled();
    expect(document.body.style.overflow).toBe("hidden");
  });

  it("CONSTRUCTED live: the reader draws this phase's milestones on the shown default; a reader choice is the page's", () => {
    render(liveWith());
    click(entry()!);
    expect(readerCard()?.getAttribute("data-mlb-run-milestones")).toBe("live");
    expect(pageCard()?.getAttribute("data-mlb-run-milestones")).toBe("live");
    expect([msChosen(readerCard()), msChosen(pageCard())]).toEqual([KEY_9_5, KEY_9_5]); // the 40% pin, nearest even odds
    click(msChip(readerCard(), "12+ runs"));
    expect([msChosen(readerCard()), msChosen(pageCard())]).toEqual([KEY_11_5, KEY_11_5]);
  });

  it("no shown pregame chance (CONSTRUCTED before, and live without pins): nothing is chosen in either view", async () => {
    for (const m of [model(beforeDetail, beforeHost, { gameMarkets: withMatrix(ownMatrix()) }), liveWith(ownMatrix())]) {
      render(m);
      click(entry()!);
      expect([msChosen(readerCard()), msChosen(pageCard())]).toEqual([null, null]);
      expect([msUnavailable(readerCard()), msUnavailable(pageCard())]).toEqual([null, null]);
      await clickAndSettle(closeButton());
    }
  });

  it("R-F1: the WHOLE input gone while open — no page row item, the reader keeps only its title, Close and words; the exact return restores the key", () => {
    render(finalWith());
    click(entry()!);
    click(choiceIn(readerCard(), KEY_10_5));
    const d = reader();
    // CONSTRUCTED same-scope passes with NO matrix: the member removed (the reduced body), then a null member.
    for (const gameMarkets of [finalMarkets, withMatrix(null)]) {
      render(model(finalDetail, { ...finalHost, nowMs: FINAL_NOW + MIN }, { gameMarkets }));
      expect(reader()).toBe(d);
      expect(showModalCalls).toBe(1);
      expect(rowParts()).toEqual(["history", "dialog"]); // no row item, card, entry or placeholder on the page
      expect([pageCard(), entry()]).toEqual([null, null]);
      expect(d.querySelector("h2")?.textContent).toBe(MLB_RUN_READER_WORDS.title);
      expect(closeButton()).toBeTruthy();
      expect(d.querySelector("[data-soccer-reader-body]")?.textContent).toBe(MLB_RUN_READER_WORDS.storyUnavailable);
      expect(d.querySelector("[data-mlb-run-reader-context], [data-mlb-run-totals], [data-run-total], [data-soccer-card]")).toBeNull();
      expect(/\d|%/.test(d.textContent ?? "")).toBe(false);
    }
    render(finalWith());
    expect(reader()).toBe(d);
    expect(rowParts()).toEqual(["history", "runTotals", "dialog"]);
    expect([pressedIn(readerCard()), pressedIn(pageCard())]).toEqual([[KEY_10_5], [KEY_10_5]]);
    expect(entry()!.disabled).toBe(true);
    expect(context()).not.toBeNull();
  });

  it("a withdrawn or duplicated key is unavailable in both views, never a substitute; its exact return restores it (TEST MUTATIONS)", () => {
    render(finalWith());
    click(entry()!);
    click(choiceIn(readerCard(), KEY_10_5));
    for (const changed of [withoutLine(ownMatrix(), 10.5), carrying(ownMatrix(), 12.5, KEY_10_5)]) {
      render(finalWith(changed));
      for (const card of [readerCard(), pageCard()]) {
        expect(headingIn(card)).toBe(MLB_RUN_TOTAL_WORDS.selectedUnavailable);
        expect(pressedIn(card)).toEqual([]);
        expect(card?.querySelector("[data-run-marker]")).toBeNull();
      }
      render(finalWith());
      expect([pressedIn(readerCard()), pressedIn(pageCard())]).toEqual([[KEY_10_5], [KEY_10_5]]);
    }
    // The milestones say so in their own words.
    render(liveWith());
    click(entry()!);
    click(msChip(readerCard(), "12+ runs"));
    render(liveWith(withoutLine(liveMilestoneMatrix(), 11.5)));
    expect([msUnavailable(readerCard()), msUnavailable(pageCard())]).toEqual(["Selected milestone unavailable.", "Selected milestone unavailable."]);
    expect([msChosen(readerCard()), msChosen(pageCard())]).toEqual([null, null]);
    render(liveWith());
    expect([msChosen(readerCard()), msChosen(pageCard())]).toEqual([KEY_11_5, KEY_11_5]);
    expect(showModalCalls).toBe(2);
  });
});

// ─── Scope ─────────────────────────────────────────────────────────────────

describe("a new event or phase closes the reader in the same render and starts a new reading", () => {
  it("CONSTRUCTED final → live while open: no frame shows the reader under live; the key clears; no scroll; lost focus goes to the entry", async () => {
    render(finalWith());
    click(entry()!);
    click(choiceIn(readerCard(), KEY_11_5));
    const focus = jest.spyOn(HTMLElement.prototype, "focus");
    frames.length = 0;
    await renderSettled(liveWith());
    expect(frames.length).toBeGreaterThan(0);
    expect(frames.filter((f) => f.phase === "live" && f.dialogs > 0)).toEqual([]);
    expect(dialogs()).toHaveLength(0);
    // KEY_11_5 is also a live milestone: a leaked key would be chosen; the live default (9.5's pin) opens instead.
    expect(msChosen(pageCard())).toBe(KEY_9_5);
    expect(pageScroll).not.toHaveBeenCalled();
    expect(document.body.style.overflow).toBe("");
    expect(document.activeElement).toBe(entry());
    expect(focus.mock.calls.at(-1)).toEqual([{ preventScroll: true }]);
    expect(entry()!.disabled).toBe(false);
  });

  it("an owner close never steals valid focus (CONSTRUCTED: focus on the page's row when the phase changes)", async () => {
    render(finalWith());
    click(entry()!);
    act(() => historyRow()!.focus()); // jsdom has no inert background, so the page can hold focus here
    await renderSettled(liveWith());
    expect(dialogs()).toHaveLength(0);
    expect(document.activeElement).toBe(historyRow());
    expect(pageScroll).not.toHaveBeenCalled();
  });

  it("CONSTRUCTED another event while open: closed in that render, the key cleared", async () => {
    render(finalWith());
    click(entry()!);
    click(choiceIn(readerCard(), KEY_10_5));
    frames.length = 0;
    await renderSettled(otherEvent(finalDetail, finalHost, otherBody(ownMatrix())));
    expect(frames.filter((f) => f.card === "mlb:15321837:final" && f.dialogs > 0)).toEqual([]);
    expect(dialogs()).toHaveLength(0);
    expect(pressedIn(pageCard())).toEqual([KEY_9_5]);
  });

  it("closes and resets on a phase or event change even while the card is absent", async () => {
    render(finalWith());
    click(entry()!);
    click(choiceIn(readerCard(), KEY_10_5));
    render(model(finalDetail, finalHost, { gameMarkets: finalMarkets })); // CONSTRUCTED: absent, same scope, still open
    expect(reader().querySelector("[data-mlb-run-reader-unavailable]")).not.toBeNull();
    frames.length = 0;
    await renderSettled(model(liveDetail, liveHost)); // a new phase, still no matrix
    expect(frames.filter((f) => f.phase === "live" && f.dialogs > 0)).toEqual([]);
    expect(dialogs()).toHaveLength(0);
    render(liveWith());
    expect(dialogs()).toHaveLength(0);
    expect(msChosen(pageCard())).toBe(KEY_9_5);
    expect(entry()!.disabled).toBe(false);
    // The same through another event: open, lose the matrix, change event while absent, return.
    render(finalWith());
    click(entry()!);
    click(choiceIn(readerCard(), KEY_10_5));
    render(model(finalDetail, finalHost, { gameMarkets: finalMarkets }));
    await renderSettled(otherEvent(finalDetail, finalHost, otherBody()));
    expect(dialogs()).toHaveLength(0);
    render(otherEvent(finalDetail, finalHost, otherBody(ownMatrix())));
    expect(pageCard()?.getAttribute("data-mlb-run-totals")).toBe("mlb:15321837:final");
    expect(pressedIn(pageCard())).toEqual([KEY_9_5]);
  });

  it("the reader's form is always the page's phase: before and live milestones, the final leaf after (CONSTRUCTED phases)", async () => {
    const before = ownMatrix();
    quoteLine(before, 9.5, 0.45, iso(BEFORE_NOW - 5 * MIN)); // CONSTRUCTED recent quote
    const cases: Array<[string, MlbGameModel]> = [
      ["before", model(beforeDetail, beforeHost, { gameMarkets: withMatrix(before) })],
      ["live", liveWith()],
      ["final", finalWith()],
    ];
    for (const [phase, m] of cases) {
      render(m);
      click(entry()!);
      expect(host.querySelector("section[data-mlb-game]")?.getAttribute("data-mlb-game")).toBe(phase);
      if (phase === "final") {
        expect(readerCard()?.querySelector("[data-run-total]")?.textContent).toBe("10");
        expect(readerCard()?.hasAttribute("data-mlb-run-milestones")).toBe(false);
      } else {
        expect(readerCard()?.getAttribute("data-mlb-run-milestones")).toBe(phase);
        expect(readerCard()?.querySelector("[data-run-total]")).toBeNull();
      }
      expect(readerCard()?.getAttribute("data-mlb-run-totals")).toBe(pageCard()?.getAttribute("data-mlb-run-totals"));
      await clickAndSettle(closeButton());
    }
  });
});

// ─── Closing returns the page's place ──────────────────────────────────────

describe("closing returns the page's place: position restored, focus with preventScroll", () => {
  it.each(["Close", "cancel (Escape)", "the browser's own close"] as const)(
    "%s closes once, restores the opening position and focuses the entry without scrolling",
    async (how) => {
      document.body.style.overflow = "clip"; // CONSTRUCTED prior page style, kept and given back
      render(finalWith());
      click(entry()!);
      expect(document.activeElement).toBe(closeButton());
      const focus = jest.spyOn(HTMLElement.prototype, "focus");
      if (how === "Close") {
        await clickAndSettle(closeButton());
      } else if (how === "cancel (Escape)") {
        // jsdom has no Escape-to-cancel: the dialog's cancel event is dispatched directly (CONSTRUCTED).
        const cancel = new Event("cancel", { cancelable: true });
        await act(async () => {
          reader().dispatchEvent(cancel);
        });
        expect(cancel.defaultPrevented).toBe(true);
      } else {
        await act(async () => {
          reader().close();
        });
      }
      expect(dialogs()).toHaveLength(0);
      expect(document.body.style.overflow).toBe("clip");
      expect(pageScroll).toHaveBeenCalledTimes(1);
      expect(pageScroll).toHaveBeenCalledWith(0, 640);
      expect(document.activeElement).toBe(entry());
      expect(focus.mock.contexts.at(-1)).toBe(entry());
      expect(focus.mock.calls.at(-1)).toEqual([{ preventScroll: true }]);
      click(entry()!);
      expect(showModalCalls).toBe(2);
    },
  );

  it("R-F3: with the entry gone while the page remains, Close focuses the history row — the persistent local anchor — not nothing", async () => {
    render(finalWith());
    click(entry()!);
    render(model(finalDetail, finalHost, { gameMarkets: finalMarkets })); // CONSTRUCTED: the input (and with it the entry) leaves
    expect(entry()).toBeNull();
    const row = historyRow()!;
    expect(row.isConnected).toBe(true);
    expect(row.tabIndex).toBe(-1); // focusable by script, never a Tab stop
    // A named group, so a returned focus says where it landed.
    expect([row.getAttribute("role"), row.getAttribute("aria-label")]).toEqual(["group", MLB_HISTORY_ROW_LABEL]);
    expect(MLB_HISTORY_ROW_LABEL).toBe("Win probability and run totals");
    expect(row.contains(reader())).toBe(true);
    const focus = jest.spyOn(HTMLElement.prototype, "focus");
    await clickAndSettle(closeButton());
    expect(dialogs()).toHaveLength(0);
    expect(pageScroll).toHaveBeenCalledWith(0, 640);
    expect(document.activeElement).toBe(row);
    expect(document.activeElement).not.toBe(document.body);
    expect([document.activeElement?.getAttribute("role"), document.activeElement?.getAttribute("aria-label")]).toEqual([
      "group",
      MLB_HISTORY_ROW_LABEL,
    ]);
    expect(focus.mock.contexts.at(-1)).toBe(row);
    expect(focus.mock.calls.at(-1)).toEqual([{ preventScroll: true }]);
  });

  it("the owning page gone: nothing is focused or scrolled, and no disconnected element is targeted", async () => {
    render(finalWith());
    click(entry()!);
    const oldEntry = entry()!;
    const oldRow = historyRow()!;
    const focus = jest.spyOn(HTMLElement.prototype, "focus");
    await act(async () => {
      root.render(<div />);
    });
    expect(dialogs()).toHaveLength(0);
    expect([oldEntry.isConnected, oldRow.isConnected]).toEqual([false, false]);
    expect(focus).not.toHaveBeenCalled();
    expect(pageScroll).not.toHaveBeenCalled();
    expect(document.body.style.overflow).toBe("");
  });
});

// ─── A true modal or nothing ───────────────────────────────────────────────

describe("when the modal cannot open: no overlay, the page says so beside the entry, and the card still works", () => {
  const failures = {
    missing: () => {
      delete dialogProto.showModal;
    },
    throwing: () => {
      dialogProto.showModal = function () {
        showModalCalls += 1;
        throw new DOMException("CONSTRUCTED opening failure", "InvalidStateError");
      };
    },
  };

  it.each(["missing", "throwing"] as const)("showModal %s: nothing opens; the status says so; chips choose; a retry or a new scope clears it", async (failure) => {
    document.body.style.overflow = "clip"; // CONSTRUCTED prior page style: never replaced by a failed attempt
    render(finalWith());
    failures[failure]();
    const focus = jest.spyOn(HTMLElement.prototype, "focus");
    await clickAndSettle(entry()!);
    expect(dialogs()).toHaveLength(0);
    expect(document.querySelector("[open], [aria-modal]")).toBeNull();
    expect(document.body.style.overflow).toBe("clip");
    expect(showModalCalls).toBe(failure === "throwing" ? 1 : 0);
    expect(statusEl()?.getAttribute("role")).toBe("status");
    expect(statusEl()?.textContent).toBe(SOCCER_READER_WORDS.fullSizeUnavailable);
    expect(entry()!.parentElement?.contains(statusEl())).toBe(true);
    expect(entry()!.disabled).toBe(false);
    expect(document.activeElement).toBe(entry());
    expect(focus.mock.calls.at(-1)).toEqual([{ preventScroll: true }]);
    expect(pageScroll).not.toHaveBeenCalled();
    // The page card still chooses, and says only what it holds.
    click(choiceIn(pageCard(), KEY_10_5));
    expect(pressedIn(pageCard())).toEqual([KEY_10_5]);
    expect(headingIn(pageCard())).toBe("Over 10.5 runs");
    // A retry once the modal works: it opens on the same key, and the status clears.
    dialogProto.showModal = stubShowModal;
    click(entry()!);
    expect(reader().open).toBe(true);
    expect(pressedIn(readerCard())).toEqual([KEY_10_5]);
    expect(statusEl()?.textContent).toBe("");
    await clickAndSettle(closeButton());
    // A new scope clears a standing status too.
    failures[failure]();
    await clickAndSettle(entry()!);
    expect(statusEl()?.textContent).toBe(SOCCER_READER_WORDS.fullSizeUnavailable);
    render(otherEvent(finalDetail, finalHost, otherBody(ownMatrix())));
    expect(statusEl()?.textContent).toBe("");
  });
});

// ─── Compact context ───────────────────────────────────────────────────────

describe("the compact context comes only from the built headline", () => {
  it("REAL final: away first, short names, both runs texts of the final column, then the state", () => {
    const m = finalWith();
    render(m);
    click(entry()!);
    const { headline } = view(m);
    const runs = (side: "home" | "away") => headline.matrix.rows.find((r) => r.side === side)!.values[1];
    expect([runs("away").text, runs("home").text]).toEqual(["7", "3"]);
    expect(contextParts()).toEqual([shown(headline.away), "7 – 3", shown(headline.home)]);
    expect(contextState()).toBe(headline.state);
    expect(context()?.querySelector("h1, h2, h3, h4, [id]")).toBeNull();
  });

  it("CONSTRUCTED live: the displayed pair's texts (6 – 3), never the raw row (3–7) or a lagging row (1–0)", () => {
    for (const detail of [liveDetail, mutate(liveDetail, { home_score: 1, away_score: 0 })]) {
      const m = liveWith(liveMilestoneMatrix(), liveHost, detail);
      render(m);
      click(entry()!);
      const { headline } = view(m);
      expect(contextParts()).toEqual([shown(headline.away), "6 – 3", shown(headline.home)]);
      expect(contextState()).toBe(headline.state);
      act(() => root.unmount());
      root = createRoot(host);
    }
  });

  it("no pair before first pitch (even with a displayed 0–0), nor for a partial or missing pair: names and state only, no figure", () => {
    const cases: MlbGameModel[] = [
      model(beforeDetail, { ...beforeHost, score: { home: 0, away: 0, observedAt: null } }, { gameMarkets: withMatrix(ownMatrix()) }), // CONSTRUCTED
      finalWith(ownMatrix(), { ...finalHost, score: { home: 3, away: null, observedAt: null } }), // CONSTRUCTED partial
      finalWith(ownMatrix(), { ...finalHost, score: null }), // CONSTRUCTED missing
      liveWith(liveMilestoneMatrix(), { ...liveHost, score: null }), // CONSTRUCTED missing
    ];
    for (const m of cases) {
      render(m);
      click(entry()!);
      const { headline } = view(m);
      expect(context()?.querySelector("[data-mlb-run-reader-score]")).toBeNull();
      expect(contextParts()).toEqual([shown(headline.away), shown(headline.home)]);
      expect(contextState()).toBe(headline.state);
      // The names line holds no figure at all: no 0, no half pair (the state line is the headline's own words).
      expect(/\d/.test(context()?.querySelector("p")?.textContent ?? "")).toBe(false);
      act(() => root.unmount());
      root = createRoot(host);
    }
  });
});

// ─── One modal, nothing else ───────────────────────────────────────────────

describe("one modal and nothing else", () => {
  it("one dialog, unique ids, labels inside their own view, no history call or URL change, no navigation or Details in the reader", () => {
    const push = jest.spyOn(window.history, "pushState");
    const replace = jest.spyOn(window.history, "replaceState");
    const href = window.location.href;
    render(finalWith());
    click(entry()!);
    click(choiceIn(readerCard(), KEY_12_5));
    render(finalWith(ownMatrix(), { ...finalHost, nowMs: FINAL_NOW + MIN }));
    expect(dialogs()).toHaveLength(1);
    expect(showModalCalls).toBe(1);
    const ids = Array.from(document.querySelectorAll("[id]")).map((el) => el.id);
    expect(ids.length).toBeGreaterThan(2);
    expect(new Set(ids).size).toBe(ids.length);
    for (const labelled of Array.from(document.querySelectorAll("[aria-labelledby]"))) {
      const target = document.getElementById(labelled.getAttribute("aria-labelledby") ?? "");
      expect(target).not.toBeNull();
      expect(target!.closest("dialog")).toBe(labelled.closest("dialog"));
    }
    const d = reader();
    expect(d.querySelector("h2")?.textContent).toBe(MLB_RUN_READER_WORDS.title);
    expect(d.querySelectorAll("nav")).toHaveLength(0);
    expect(d.querySelector("[data-soccer-reader-position], [data-soccer-details-entry]")).toBeNull();
    expect(Array.from(d.querySelectorAll("button")).filter((b) => (b.textContent ?? "").startsWith("Details"))).toHaveLength(0);
    expect(d.textContent).not.toMatch(/\b1 of 1\b/);
    expect(push).not.toHaveBeenCalled();
    expect(replace).not.toHaveBeenCalled();
    expect(window.location.href).toBe(href);
  });
});

// ─── The page around it ────────────────────────────────────────────────────

describe("the page around the reader survives: history first, its chart and disclosure, an original's Details", () => {
  it("open, input lost, input back, close: the history row's first item, chart, open disclosure and open Details are the same elements", async () => {
    render(finalWith());
    const chart = historyChart();
    const disclosure = historyDisclosure();
    expect(chart).not.toBeNull();
    expect(disclosure).not.toBeNull();
    click(disclosure!);
    click(allPropsEntry());
    const original = detailsButtons()[0];
    click(original);
    expect(openDetails()).toEqual([original]);
    click(entry()!);
    expect(rowParts()).toEqual(["history", "runTotals", "dialog"]);
    render(model(finalDetail, finalHost, { gameMarkets: finalMarkets })); // CONSTRUCTED: the input lost while open
    expect(rowParts()).toEqual(["history", "dialog"]);
    render(finalWith()); // and back
    expect(rowParts()).toEqual(["history", "runTotals", "dialog"]);
    await clickAndSettle(closeButton());
    expect(rowParts()).toEqual(["history", "runTotals"]);
    expect(historyChart()).toBe(chart);
    expect(historyDisclosure()).toBe(disclosure);
    expect(disclosure!.getAttribute("aria-expanded")).toBe("true");
    expect(openDetails()).toHaveLength(1);
    expect(openDetails()[0]).toBe(original);
    expect(document.getElementById(original.getAttribute("aria-controls") ?? "")?.hidden).toBe(false);
    expect(document.activeElement).toBe(entry());
  });
});
