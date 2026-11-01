/** @jest-environment jsdom */
/**
 * #10868 — a soccer story card's original Details, FROZEN at the tap
 * (`soccerOriginalDetails.ts` + `SoccerMatchStories` + `SoccerMatchPage`,
 * Design's four-path admission 0a47ebcf).
 *
 * SHIP: a soccer fan opens an original prop's exact Details, keeps that view
 * stable during live updates, refreshes only that same prop and returns to the
 * same card.
 *
 * BODIES — `../lib/soccerMatch10868.fixtures.json`, READ-ONLY: the retained
 * production response bodies copied from the native soccer fixtures, each at
 * its own capture clock (Valladolid–Albacete live and final; Hull–Everton
 * before kickoff). Retained finals are retained data, not live evidence.
 *
 * Labels, per test:
 *   - RETAINED — those bodies unedited, at their own clocks, under the
 *     fixture's shared CONSTRUCTED owner admissions (no production owner
 *     supplies a story admission, so every admission is CONSTRUCTED owner
 *     metadata by nature).
 *   - CONSTRUCTED — named where made: an edited price, a removed row, a
 *     duplicated id, a moved admission, a mutated catalogue object, a reader
 *     body scroll or map pan, a removed dialog method.
 *
 * Expected identities are literal ids from the bridge's tests; nothing here
 * derives an identity, a price, a grade or a clock.
 *
 * jsdom 26 implements NO dialog behaviour, layout or scrolling: the stub below
 * only flips `open`, and `scrollTop` / `scrollLeft` are plain numbers. These
 * tests prove STATE and WIRING (what opens, what it shows, what Refresh may
 * replace, where focus and the recorded positions are sent). They do NOT prove
 * real modality, focus containment, background isolation, scroll locking or a
 * browser's actual restored map pan; only a browser check proves those (owed).
 */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import fixtures from "../lib/soccerMatch10868.fixtures.json";
import type { EventDetailResponse, EventHistoryResponse } from "@/lib/types";
import type { GameMarketsResponse } from "@/lib/api";
import { propVerdictLabel } from "@/lib/propGrade";
import {
  buildSoccerMatch,
  type SoccerHalvesAdmission,
  type SoccerMatchAdmission,
  type SoccerMatchViewModel,
} from "@/lib/eventPage10868/soccerMatch";
import type { SoccerStoryCard, SoccerStoryId } from "@/lib/eventPage10868/soccerMatchTypes";
import type { HockeyJourneyOriginal } from "@/lib/eventPage10868/hockeyJourneyProps";
import {
  buildSoccerCardPass,
  openBoth,
  openGoal,
  soccerCardShown,
  type SoccerCardHold,
  type SoccerCardOpened,
  type SoccerCardPass,
} from "@/lib/eventPage10868/soccerCardOriginals";
import {
  openSoccerDetails,
  refreshSoccerDetails,
  soccerCardPassFor,
  soccerDetailsPass,
  soccerDetailsStatus,
  soccerFrozenCopy,
  soccerOpenSelected,
  type SoccerOriginalDetails,
} from "@/lib/eventPage10868/soccerOriginalDetails";
import SoccerMatchPage from "@/components/event/eventpage10868/SoccerMatchPage";
import SoccerMatchStories, { SOCCER_DETAILS_WORDS, SoccerOriginalDetailsBody } from "@/components/event/eventpage10868/SoccerMatchStories";
import { SOCCER_READER_WORDS } from "@/components/event/eventpage10868/SoccerMatchReader";

// ─── Bodies, clocks, admissions ────────────────────────────────────────────

type BodyKey = keyof typeof fixtures.bodies;
type Json = Record<string, unknown>;
const parsed = (key: BodyKey): Json => JSON.parse(fixtures.bodies[key].raw) as Json;

const LIVE_NOW = Date.parse(fixtures.provenance.clocks.liveNow);
const FINAL_NOW = Date.parse(fixtures.provenance.clocks.finalNow);
const HULL_NOW = Date.parse(fixtures.provenance.clocks.hullNow);

/** CONSTRUCTED owner metadata (the fixture's, from the native tests). */
const C = fixtures.constructed as unknown as {
  liveAdmission: SoccerMatchAdmission;
  hullAdmission: SoccerMatchAdmission;
  fullTotals: number[];
  hullDescriptor: NonNullable<SoccerMatchAdmission["exactScore"]>;
};
const LIVE = C.liveAdmission;
const HULL_BEFORE: SoccerMatchAdmission = { ...C.hullAdmission, goals: C.fullTotals, exactScore: C.hullDescriptor };

const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x)) as T;

/** CONSTRUCTED: the ONE row of `array` whose contributor ids are exactly `[outcomeId]`, with only `setting` changed. */
function editedRow(body: Json, outcomeId: number, setting: Json, array = "other"): Json {
  const copy = clone(body);
  const rows = copy[array] as Json[];
  const index = rows.findIndex((row) => JSON.stringify(row.contributor_outcome_ids) === JSON.stringify([outcomeId]));
  if (index < 0) throw new Error(`no ${array} row for ${outcomeId}`);
  rows[index] = { ...rows[index], ...setting };
  return copy;
}

/** CONSTRUCTED: the body without the ONE row of `array` naming exactly `[outcomeId]`. */
function removingRow(body: Json, outcomeId: number, array = "other"): Json {
  const copy = clone(body);
  const rows = copy[array] as Json[];
  const index = rows.findIndex((row) => JSON.stringify(row.contributor_outcome_ids) === JSON.stringify([outcomeId]));
  if (index < 0) throw new Error(`no ${array} row for ${outcomeId}`);
  rows.splice(index, 1);
  return copy;
}

interface Built {
  page: SoccerMatchViewModel;
  pass: SoccerCardPass;
}

/** One host render: the page built ONCE by the real builder, then the bridge's pass from the SAME inputs. */
function built(
  o: { detail?: BodyKey; history?: BodyKey | null; markets?: Json | null; admitted?: SoccerMatchAdmission; now?: number; halves?: SoccerHalvesAdmission } = {},
): Built {
  const event = parsed(o.detail ?? "liveDetail") as unknown as EventDetailResponse;
  const historyKey = o.history === undefined ? "liveHistory" : o.history;
  const history = historyKey === null ? null : (parsed(historyKey) as unknown as EventHistoryResponse);
  const markets = (o.markets === undefined ? parsed("liveMarkets") : o.markets) as unknown as GameMarketsResponse | null;
  const admitted = o.admitted ?? LIVE;
  const nowMs = o.now ?? LIVE_NOW;
  const page = buildSoccerMatch({
    event,
    history,
    gameMarkets: markets,
    admitted,
    halvesAdmission: o.halves ?? "explicit",
    host: { nowMs, hero: null, probabilityObservedAt: null },
  });
  return { page, pass: buildSoccerCardPass({ event, gameMarkets: markets, admission: admitted, nowMs, page }) };
}
const finalBuilt = () => built({ detail: "finalDetail", history: "finalHistory", markets: parsed("finalMarkets"), now: FINAL_NOW });
const hullBuilt = () => built({ detail: "hullDetail", history: "hullHistory", markets: parsed("hullExactMarkets"), admitted: HULL_BEFORE, now: HULL_NOW });

/** CONSTRUCTED (the bridge's C1a): the goal card moved to another market and the both card to another market. */
const MOVED: SoccerMatchAdmission = { ...LIVE, goals: [64536538], both: 64353427 };

const LIVE_STREAM = "soccer:15325054:live";
const key = (market: number, side: string) => `polymarket|${market}|${side}`;
/** The literal exact originals per card id (the bridge's tests). */
const EXPECTED: Record<SoccerStoryId, Record<string, string>> = {
  goals: { "242143183": key(64353423, "242143183"), "242143187": key(64353425, "242143187"), "242765587": key(64536538, "242765587") },
  both: { "242143190": key(64353426, "242143190"), "242143189": key(64353426, "242143189") },
  first: { "244237963": key(63178217, "244237963"), "244237965": key(63178217, "244237965"), "244237964": key(63178217, "244237964") },
  halves: {
    "63178219:242338171": key(63178219, "242338171"),
    "63178219:242338170": key(63178219, "242338170"),
    "63178219:242338172": key(63178219, "242338172"),
    "63178218:246041831": key(63178218, "246041831"),
    "63178218:245875499": key(63178218, "245875499"),
    "63178218:245681743": key(63178218, "245681743"),
  },
  exact: { "238846934": key(62939468, "238846934"), "244588607": key(64002155, "244588607") },
};

const originalOf = (b: Built, k: string): HockeyJourneyOriginal => {
  const found = b.page.originals.originals.filter((o) => o.key === k);
  if (found.length !== 1) throw new Error(`expected one original ${k}, found ${found.length}`);
  return found[0];
};
const laterText = (o: HockeyJourneyOriginal): string => (o.later === null ? "" : o.later.kind === "value" ? o.later.text : o.later.words);
const snapshotOf = (d: SoccerOriginalDetails) => {
  if (d.kind !== "snapshot") throw new Error(`unresolved ${d.card}`);
  return d;
};
const holdOf = (opened: SoccerCardOpened): SoccerCardHold => {
  if (opened.kind !== "held") throw new Error(`unresolved ${opened.card}`);
  return opened.hold;
};
const cardOf = (b: Built, id: SoccerStoryId): SoccerStoryCard => {
  const found = b.page.stories.cards.find((c) => c.id === id);
  if (!found) throw new Error(`no ${id} card`);
  return found;
};
/** Every object and array node of a value, for deep-freeze checks. */
function nodes(value: unknown, out: object[] = []): object[] {
  if (value !== null && typeof value === "object") {
    out.push(value);
    for (const item of Object.values(value)) nodes(item, out);
  }
  return out;
}

// ─── Pure: the token, the frozen payload, the pass ─────────────────────────

describe("the snapshot: one bridge token and one frozen, independent copy (pure)", () => {
  it("opens with the bridge token and a deep-frozen copy of THIS pass's original, every built field kept", () => {
    const b = built(); // RETAINED live
    const opened = soccerOpenSelected({ card: "both", outcomeId: "242143189" }, b.pass);
    expect(opened).toEqual(openBoth({ eventId: 15325054, marketId: 64353426, outcomeId: "242143189" }, b.pass));
    const original = soccerCardShown(opened, b.pass)!.original;
    const d = snapshotOf(openSoccerDetails(LIVE_STREAM, "page", opened, b.pass));
    expect(d.frozen).toEqual(original);
    expect(d.frozen).not.toBe(original);
    expect(d.token).toEqual(holdOf(opened));
    expect(d.token).not.toBe(holdOf(opened));
    // Non-vacuity: a live original carries nested readings, rows and an identity.
    expect(original.later).not.toBeNull();
    expect(original.about.rows.length).toBeGreaterThan(0);
    const frozenNodes = nodes(d.frozen);
    expect(frozenNodes.length).toBeGreaterThanOrEqual(6);
    for (const node of [...frozenNodes, ...nodes(d.token)]) expect(Object.isFrozen(node)).toBe(true);
    // No node of the payload is shared with the catalogue's object.
    const sourceNodes = new Set(nodes(original));
    expect(frozenNodes.some((node) => sourceNodes.has(node))).toBe(false);

    // CONSTRUCTED: the catalogue's own object is mutated after the tap, nested fields included.
    const before = JSON.stringify(d.frozen);
    const loose = original as unknown as { label: string; identity: { side: string }; about: { rows: Array<{ value: string }> }; later: { text?: string; words?: string } };
    loose.label = "MUTATED";
    loose.identity.side = "MUTATED";
    loose.about.rows[0].value = "MUTATED";
    loose.later.text = "MUTATED";
    loose.later.words = "MUTATED";
    expect(JSON.stringify(d.frozen)).toBe(before);
  });

  it("no exact accepted original at the tap is unresolved for good: no token, no payload, never refreshable, even once the id resolves", () => {
    const withdrawn = built({ markets: removingRow(parsed("liveMarkets"), 242143189) }); // CONSTRUCTED
    const opened = soccerOpenSelected({ card: "both", outcomeId: "242143189" }, withdrawn.pass);
    expect(opened).toEqual({ kind: "unresolved", card: "both" });
    const d = openSoccerDetails(LIVE_STREAM, "reader", opened, withdrawn.pass);
    expect(d).toEqual({ kind: "unresolved", scope: LIVE_STREAM, entry: "reader", card: "both" });
    const valid = built(); // RETAINED: the same id resolves again
    expect(soccerOpenSelected({ card: "both", outcomeId: "242143189" }, valid.pass).kind).toBe("held");
    expect(soccerDetailsStatus(d, valid.pass)).toBe("unresolved");
    expect(refreshSoccerDetails(d, valid.pass)).toBe(d);
    // A held tap offered with no pass, or with a pass serving another scope, keeps no token either.
    const tap = soccerOpenSelected({ card: "both", outcomeId: "242143189" }, valid.pass);
    expect(openSoccerDetails(LIVE_STREAM, "page", tap, null).kind).toBe("unresolved");
    expect(openSoccerDetails(LIVE_STREAM, "page", tap, finalBuilt().pass).kind).toBe("unresolved");
  });

  it("a same-id background update never replaces the payload; explicit Refresh replaces it from the SAME token only", () => {
    const before = built();
    const d = snapshotOf(openSoccerDetails(LIVE_STREAM, "page", soccerOpenSelected({ card: "both", outcomeId: "242143189" }, before.pass), before.pass));
    const opened = JSON.stringify(d.frozen);
    const later = LIVE_NOW + 60_000;
    // CONSTRUCTED: a same-scope refresh with the outcome's price moved and freshly observed.
    const after = built({ markets: editedRow(parsed("liveMarkets"), 242143189, { probability: 0.62, observed_at: new Date(later - 20_000).toISOString() }), now: later });
    const now = originalOf(after, d.frozen.key);
    expect(now.later).not.toEqual(d.frozen.later); // non-vacuity: the update really changed the reading
    expect(soccerDetailsStatus(d, after.pass)).toBe("current");
    expect(JSON.stringify(d.frozen)).toBe(opened);
    const refreshed = snapshotOf(refreshSoccerDetails(d, after.pass));
    expect(refreshed.frozen).toEqual(now);
    expect(refreshed.frozen).not.toBe(now);
    expect(Object.isFrozen(refreshed.frozen.later)).toBe(true);
    expect(refreshed.token).toBe(d.token);
    expect(JSON.stringify(d.frozen)).toBe(opened);
  });

  it("withdrawn, rebound or duplicated: the historical payload stays and Refresh changes nothing, though the old original is still in All props", () => {
    const live = built();
    const goal = snapshotOf(openSoccerDetails(LIVE_STREAM, "page", openGoal("242143183", live.pass), live.pass));
    const both = snapshotOf(openSoccerDetails(LIVE_STREAM, "page", soccerOpenSelected({ card: "both", outcomeId: "242143189" }, live.pass), live.pass));
    expect([soccerDetailsStatus(goal, live.pass), soccerDetailsStatus(both, live.pass)]).toEqual(["current", "current"]); // CONTROL

    const withdrawn = built({ markets: removingRow(parsed("liveMarkets"), 242143189) }); // CONSTRUCTED
    const rebound = built({ admitted: MOVED }); // CONSTRUCTED
    // CONSTRUCTED: another outcome re-identified as 242143189, so the both card draws it twice.
    const duplicated = built({ markets: editedRow(parsed("liveMarkets"), 242143190, { contributor_outcome_ids: [242143189] }) });
    for (const [d, pass] of [
      [both, withdrawn.pass],
      [both, rebound.pass],
      [goal, rebound.pass],
      [both, duplicated.pass],
    ] as const) {
      expect(soccerDetailsStatus(d, pass)).toBe("unavailable");
      expect(refreshSoccerDetails(d, pass)).toBe(d);
    }
    // The rebound originals are still listed in All props: listing alone never revalidates.
    expect(originalOf(rebound, goal.frozen.key).key).toBe(goal.frozen.key);
    expect(originalOf(rebound, both.frozen.key).key).toBe(both.frozen.key);
    // Returning to availability permits Refresh; it replaces nothing by itself.
    const back = built();
    expect(soccerDetailsStatus(both, back.pass)).toBe("current");
    expect(both.frozen).toEqual(originalOf(live, both.frozen.key));
  });

  it("only a pass built for THIS model and render is used: stale, missing and foreign passes read as none", () => {
    const a = built();
    const again = built(); // RETAINED: the same inputs built again, internally consistent
    expect(again.pass.consistent).toBe(true);
    expect(soccerCardPassFor(a.pass, a.page)).toBe(a.pass);
    expect(soccerCardPassFor(again.pass, a.page)).toBeNull();
    expect(soccerCardPassFor(null, a.page)).toBeNull();
    expect(soccerCardPassFor(undefined, a.page)).toBeNull();
    expect(soccerCardPassFor(finalBuilt().pass, a.page)).toBeNull();
    expect(soccerCardPassFor(hullBuilt().pass, a.page)).toBeNull();
    // CONSTRUCTED: a pass whose inputs are another event's page is inconsistent.
    const event = parsed("hullDetail") as unknown as EventDetailResponse;
    const foreign = buildSoccerCardPass({ event, gameMarkets: null, admission: LIVE, nowMs: LIVE_NOW, page: a.page });
    expect(foreign.consistent).toBe(false);
    expect(soccerCardPassFor(foreign, a.page)).toBeNull();
    expect(soccerDetailsPass(a.pass, LIVE_STREAM)).toBe(a.pass);
    expect(soccerDetailsPass(a.pass, "soccer:15325054:final")).toBeNull();

    const d = snapshotOf(openSoccerDetails(LIVE_STREAM, "page", openGoal("242143183", a.pass), a.pass));
    expect(soccerDetailsStatus(d, null)).toBe("unavailable");
    expect(soccerDetailsStatus(d, finalBuilt().pass)).toBe("unavailable");
    expect(refreshSoccerDetails(d, finalBuilt().pass)).toBe(d);
  });

  it("the frozen copy freezes arrays and objects at every depth and leaves primitives as they are", () => {
    const source = { a: [{ b: "x" }, 2], c: { d: null as string | null } };
    const copy = soccerFrozenCopy(source);
    expect(copy).toEqual(source);
    expect(nodes(copy).every((node) => Object.isFrozen(node))).toBe(true);
    expect(copy.a[0]).not.toBe(source.a[0]);
  });
});

// ─── Render harness ────────────────────────────────────────────────────────

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

beforeEach(() => {
  (globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  showModalCalls = 0;
  dialogProto.showModal = stubShowModal;
  dialogProto.close = function (this: HTMLDialogElement) {
    if (!this.hasAttribute("open")) return;
    this.removeAttribute("open");
    this.dispatchEvent(new Event("close"));
  };
  pageScroll = jest.spyOn(window, "scrollTo").mockImplementation(() => undefined);
  // CONSTRUCTED: the page is scrolled 640 px down.
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

function click(el: Element) {
  act(() => {
    el.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
}
/** A press whose close returns focus after the commit: flushes the reader's microtask. */
async function clickAndSettle(el: Element) {
  await act(async () => {
    el.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
}

const showPage = (b: Built, pass: SoccerCardPass | null = b.pass) => act(() => root.render(<SoccerMatchPage match={b.page} cardPass={pass} />));
const dialogs = () => Array.from(document.querySelectorAll("dialog"));
const reader = () => {
  const all = dialogs();
  if (all.length !== 1) throw new Error(`expected one dialog, found ${all.length}`);
  return all[0];
};
const outside = (el: Element) => !el.closest("dialog");
const pageCard = () => Array.from(host.querySelectorAll("[data-soccer-card]")).find(outside) ?? null;
const pageCardId = () => pageCard()?.getAttribute("data-soccer-card") ?? null;
const pageEntries = () => Array.from(host.querySelectorAll<HTMLButtonElement>("[data-soccer-details-entry]")).filter(outside);
const readerEntries = () => Array.from(reader().querySelectorAll<HTMLButtonElement>("[data-soccer-reader-card] [data-soccer-details-entry]"));
const opener = () => Array.from(host.querySelectorAll<HTMLButtonElement>('[data-soccer-reader-entry="story"]')).find(outside)!;
const streamNext = () => Array.from(host.querySelectorAll<HTMLButtonElement>("nav button")).filter(outside).find((b) => (b.textContent ?? "").startsWith("Next"))!;
const view = () => reader().querySelector<HTMLElement>("[data-soccer-details]");
const viewKey = () => view()?.getAttribute("data-soccer-details-original") ?? null;
const viewReading = (slot: "pregame" | "later" | "result") => view()?.querySelector(`[data-soccer-details-reading="${slot}"]`)?.textContent ?? null;
const refreshButton = () => reader().querySelector<HTMLButtonElement>("[data-soccer-details-refresh]");
const backButton = () => reader().querySelector<HTMLButtonElement>("[data-soccer-details-back]");
const closeButton = () => Array.from(reader().querySelectorAll<HTMLButtonElement>("header button")).find((b) => b.textContent === SOCCER_READER_WORDS.close)!;
const readerBody = () => reader().querySelector<HTMLElement>("[data-soccer-reader-body]")!;
const readerCardBox = () => reader().querySelector<HTMLElement>("[data-soccer-reader-card]");
const readerTitle = () => reader().querySelector("h2")?.textContent ?? null;
const chosenIn = (within: ParentNode, card: SoccerStoryId) =>
  within.querySelector(`[data-soccer-card="${card}"] ${card === "exact" ? "[data-soccer-exact-chosen]" : "[data-soccer-chosen]"}`)?.getAttribute(card === "exact" ? "data-soccer-exact-chosen" : "data-soccer-chosen") ?? null;

function goTo(card: SoccerStoryId) {
  for (let i = 0; i < 6 && pageCardId() !== card; i += 1) click(streamNext());
  if (pageCardId() !== card) throw new Error(`no ${card} card on the page`);
}

/** Choose a row by its own id through the card's existing chooser (the page's card unless `within` says otherwise). */
function choose(b: Built, card: SoccerStoryId, id: string, within: ParentNode = pageCard()!) {
  const model = cardOf(b, card);
  let target: HTMLButtonElement | null | undefined = null;
  if (model.id === "goals") target = Array.from(within.querySelectorAll<HTMLButtonElement>("li > button"))[model.milestones.findIndex((m) => m.id === id)];
  if (model.id === "both") target = Array.from(within.querySelectorAll<HTMLButtonElement>("li > button"))[model.outcomes.findIndex((o) => o.id === id)];
  if (model.id === "first") target = within.querySelector<HTMLButtonElement>(`[data-first-row="${id}"] > button`);
  if (model.id === "halves") target = Array.from(within.querySelectorAll<HTMLButtonElement>('[role="group"] button'))[model.series.findIndex((s) => s.id === id)];
  if (model.id === "exact") target = within.querySelector<HTMLButtonElement>(`td[data-cell="${id}"] button`);
  if (!target) throw new Error(`no chooser for ${card} ${id}`);
  click(target);
}

// ─── Render: entry, frozen view, Refresh, return ───────────────────────────

describe("the page boundary offers Details only with this model's own pass", () => {
  it("no pass or a stale pass offers no Details control; this render's pass offers the selected readout's", () => {
    const b = built();
    showPage(b, null);
    expect(pageEntries()).toHaveLength(0);
    showPage(b, built().pass); // RETAINED inputs, but another render's pass
    expect(pageEntries()).toHaveLength(0);
    showPage(b);
    expect(pageCardId()).toBe("goals");
    expect(pageEntries().map((e) => e.getAttribute("data-soccer-details-entry"))).toEqual(["goals"]);
    const goals = cardOf(b, "goals");
    const label = goals.id === "goals" ? goals.milestones.find((m) => m.id === chosenIn(host, "goals"))?.label : null;
    expect(pageEntries()[0].textContent).toBe(`${SOCCER_DETAILS_WORDS.open}: ${label}`);
  });
});

describe("all five families: the selected original, default or not, opens exactly itself; the held choice never moves", () => {
  /** Opens from the page, checks the original, closes, and checks focus and the held choice. */
  async function openAndClose(card: SoccerStoryId, expected: string, entry = 0) {
    const chosen = chosenIn(host, card);
    const control = pageEntries()[entry];
    click(control);
    expect(dialogs()).toHaveLength(1);
    expect(viewKey()).toBe(expected);
    expect(backButton()).toBeNull(); // from a compact card: no Back that opens a reader
    expect(reader().querySelector("nav")).toBeNull();
    expect(opener().disabled).toBe(true);
    await clickAndSettle(closeButton());
    expect(dialogs()).toHaveLength(0);
    expect(document.activeElement).toBe(control);
    expect(chosenIn(host, card)).toBe(chosen);
  }

  it("goals, both, first and halves during play (RETAINED live, explicit halves), each on its default and on a non-default row", async () => {
    const b = built();
    showPage(b);
    for (const [card, other] of [
      ["goals", "242765587"],
      ["both", "242143190"],
      ["first", "244237964"],
      ["halves", "away"],
    ] as const) {
      goTo(card);
      const model = cardOf(b, card);
      const defaultId = chosenIn(host, card)!;
      expect(defaultId).not.toBe(other);
      if (model.id === "halves") {
        const series = model.series.find((s) => s.id === defaultId)!;
        expect(pageEntries()).toHaveLength(series.cells.length);
        for (const [i, cell] of series.cells.entries()) await openAndClose(card, EXPECTED.halves[cell.id], i);
        choose(b, card, other);
        const chosenSeries = model.series.find((s) => s.id === other)!;
        for (const [i, cell] of chosenSeries.cells.entries()) await openAndClose(card, EXPECTED.halves[cell.id], i);
        continue;
      }
      await openAndClose(card, EXPECTED[card][defaultId]);
      choose(b, card, other);
      expect(chosenIn(host, card)).toBe(other);
      await openAndClose(card, EXPECTED[card][other]);
    }
  });

  it("exact before kickoff (RETAINED Hull): a chosen score in each scope opens its own original", async () => {
    const b = hullBuilt();
    showPage(b);
    goTo("exact");
    expect(pageEntries()).toHaveLength(0); // no default score: nothing selected, nothing offered
    choose(b, "exact", "238846934");
    await openAndClose("exact", EXPECTED.exact["238846934"]);
    const scopes = Array.from(pageCard()!.querySelectorAll<HTMLButtonElement>('[role="group"] button'));
    click(scopes[1]);
    choose(b, "exact", "244588607");
    await openAndClose("exact", EXPECTED.exact["244588607"]);
  });
});

describe("the view stays what was opened until Refresh", () => {
  it("a same-scope live update leaves the view unchanged; Refresh shows the same original's new values", () => {
    const before = built();
    showPage(before);
    goTo("both");
    choose(before, "both", "242143189");
    click(pageEntries()[0]);
    const dialog = reader();
    const opened = originalOf(before, EXPECTED.both["242143189"]);
    expect(viewReading("later")).toContain(laterText(opened));
    const text = reader().textContent ?? "";
    expect(text.split(SOCCER_DETAILS_WORDS.fixedView)).toHaveLength(2); // shown once
    expect(text).toContain(SOCCER_DETAILS_WORDS.recordedInGame);
    expect(text).not.toContain("Current chance");
    const shownBefore = view()!.textContent;

    const later = LIVE_NOW + 60_000;
    // CONSTRUCTED: the same outcome's price moved and freshly observed, same scope.
    const after = built({ markets: editedRow(parsed("liveMarkets"), 242143189, { probability: 0.62, observed_at: new Date(later - 20_000).toISOString() }), now: later });
    const now = originalOf(after, EXPECTED.both["242143189"]);
    expect(JSON.stringify(now.later)).not.toBe(JSON.stringify(opened.later)); // non-vacuity
    showPage(after);
    expect(reader()).toBe(dialog);
    expect(view()!.textContent).toBe(shownBefore);
    expect(view()!.getAttribute("data-soccer-details")).toBe("current");
    expect(refreshButton()!.getAttribute("aria-disabled")).toBe("false");
    click(refreshButton()!);
    expect(viewKey()).toBe(EXPECTED.both["242143189"]);
    expect(view()!.textContent).not.toBe(shownBefore);
    expect(viewReading("later")).toContain(laterText(now));
    expect(showModalCalls).toBe(1);
  });

  it("a withdrawn or rebound original keeps the opened view, says the latest details are unavailable and refuses Refresh", () => {
    for (const changed of [
      built({ markets: removingRow(parsed("liveMarkets"), 242143189) }), // CONSTRUCTED withdrawal
      built({ admitted: MOVED }), // CONSTRUCTED rebind
    ]) {
      const b = built();
      showPage(b);
      goTo("both");
      choose(b, "both", "242143189");
      click(pageEntries()[0]);
      const shownBefore = view()!.querySelector("div.space-y-2")!.textContent;
      showPage(changed);
      expect(view()!.getAttribute("data-soccer-details")).toBe("unavailable");
      expect(reader().querySelector('[data-soccer-details-status="unavailable"]')?.textContent).toBe(SOCCER_DETAILS_WORDS.latestUnavailable);
      expect(refreshButton()!.getAttribute("aria-disabled")).toBe("true");
      click(refreshButton()!);
      expect(viewKey()).toBe(EXPECTED.both["242143189"]);
      expect(view()!.querySelector("div.space-y-2")!.textContent).toBe(shownBefore);
      act(() => root.unmount());
      root = createRoot(host);
    }
  });

  it("after the final the opened Details print the catalogue's own canonical HIT and MISS words (RETAINED final)", async () => {
    const b = finalBuilt();
    showPage(b);
    goTo("both");
    const words: Record<string, string> = {};
    for (const id of ["242143190", "242143189"]) {
      choose(b, "both", id);
      click(pageEntries()[0]);
      words[id] = view()!.querySelector("[data-soccer-details-grade]")!.textContent ?? "";
      expect(view()!.textContent).not.toMatch(/\bWon\b|\bLost\b/);
      await clickAndSettle(closeButton());
    }
    const hit = originalOf(b, EXPECTED.both["242143190"]).grade;
    const miss = originalOf(b, EXPECTED.both["242143189"]).grade;
    // Non-vacuity: one admitted HIT and one admitted MISS, in different words.
    expect([hit?.hit, miss?.hit]).toEqual([true, false]);
    expect(words).toEqual({ "242143190": propVerdictLabel(true), "242143189": propVerdictLabel(false) });
    expect(words["242143190"]).toBe(hit?.words);
    expect(words["242143189"]).toBe(miss?.words);
    expect(words["242143190"]).not.toBe(words["242143189"]);
  });

  it("an opening with no exact original shows only its short unavailable words: no probability and no Refresh", () => {
    const onRefresh = jest.fn();
    act(() =>
      root.render(
        <SoccerOriginalDetailsBody
          details={{ kind: "unresolved", scope: LIVE_STREAM, entry: "page", card: "both" }}
          status="unresolved"
          onRefresh={onRefresh}
          back={null}
        />,
      ),
    );
    expect(host.textContent).toBe(SOCCER_DETAILS_WORDS.unresolved);
    expect(host.querySelector("button")).toBeNull();
    expect(host.textContent).not.toMatch(/%/);
  });
});

describe("one modal: Details over the full-size card, Back to the card, Close out of everything", () => {
  it("from the reader, Details is a content mode of the SAME dialog; Back restores the card, its scroll and focus", () => {
    const b = built();
    showPage(b);
    click(pageEntries()[0]);
    const fromPage = viewKey();
    act(() => {
      closeButton().dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    click(opener());
    const dialog = reader();
    expect(showModalCalls).toBe(2);
    const position = reader().querySelector("[data-soccer-reader-position]")?.textContent;
    const body = readerBody();
    body.scrollTop = 300; // CONSTRUCTED reader-body position
    const control = readerEntries()[0];
    click(control);
    expect(reader()).toBe(dialog);
    expect(showModalCalls).toBe(2);
    expect(viewKey()).toBe(fromPage); // compact and full-size entries open the same original
    expect(readerCardBox()!.hidden).toBe(true);
    expect(readerTitle()).toBe(originalOf(b, fromPage!).label);
    expect(reader().querySelector("nav")).toBeNull();
    expect(document.activeElement).toBe(backButton());
    expect(body.scrollTop).toBe(0);

    click(backButton()!);
    expect(reader()).toBe(dialog);
    expect(view()).toBeNull();
    expect(readerCardBox()!.hidden).toBe(false);
    expect(reader().querySelector("[data-soccer-card]")?.getAttribute("data-soccer-card")).toBe("goals");
    expect(readerTitle()).toBe(cardOf(b, "goals").name);
    expect(reader().querySelector("[data-soccer-reader-position]")?.textContent).toBe(position);
    expect(body.scrollTop).toBe(300);
    expect(document.activeElement).toBe(control);
    expect(chosenIn(reader(), "goals")).toBe(chosenIn(host, "goals"));
  });

  it("Back restores the exact map's own pan even when hiding lost it (CONSTRUCTED pan loss)", () => {
    const b = hullBuilt();
    showPage(b);
    goTo("exact");
    click(opener());
    choose(b, "exact", "238846934", reader());
    const scroller = reader().querySelector<HTMLElement>("[data-soccer-reader-card] [data-exact-scroller]")!;
    scroller.scrollLeft = 120; // CONSTRUCTED map pan
    click(readerEntries()[0]);
    expect(viewKey()).toBe(EXPECTED.exact["238846934"]);
    scroller.scrollLeft = 0; // CONSTRUCTED: a browser dropping the hidden map's pan
    click(backButton()!);
    expect(reader().querySelector("[data-soccer-reader-card] [data-exact-scroller]")).toBe(scroller);
    expect(scroller.scrollLeft).toBe(120);
    expect(chosenIn(reader(), "exact")).toBe("238846934");
  });

  it("the shell's Close from Details leaves the whole view to the unchanged page and its opener", async () => {
    const b = built();
    showPage(b);
    const chosen = chosenIn(host, "goals");
    click(opener());
    click(readerEntries()[0]);
    await clickAndSettle(closeButton());
    expect(dialogs()).toHaveLength(0);
    expect(document.activeElement).toBe(opener());
    expect(pageScroll).toHaveBeenLastCalledWith(0, 640);
    expect(chosenIn(host, "goals")).toBe(chosen);
    click(opener()); // the reader opens on its card again, never on stale Details
    expect(view()).toBeNull();
    expect(readerCardBox()!.hidden).toBe(false);
  });

  it("if the reader's card goes away under Details, Back shows that card's unavailable words, never another card, with focus kept in the modal", () => {
    const b = built();
    showPage(b);
    click(opener());
    click(readerEntries()[0]);
    const gone = built({ admitted: { ...LIVE, goals: [] } }); // CONSTRUCTED: no goal markets admitted
    showPage(gone);
    expect(view()!.getAttribute("data-soccer-details")).toBe("unavailable");
    click(backButton()!);
    expect(reader().querySelector("[data-soccer-card]")).toBeNull();
    expect(reader().querySelector("[data-soccer-reader-unavailable]")?.textContent).toBe(SOCCER_READER_WORDS.storyUnavailable);
    expect(document.activeElement).toBe(readerCardBox());
    expect(reader().contains(document.activeElement)).toBe(true);
  });

  it("a compact card's Close falls back to the surviving entry when its Details control is gone (CONSTRUCTED withdrawal)", async () => {
    const b = built();
    showPage(b);
    goTo("both");
    choose(b, "both", "242143189");
    click(pageEntries()[0]);
    showPage(built({ markets: removingRow(parsed("liveMarkets"), 242143189) }));
    await clickAndSettle(closeButton());
    expect(dialogs()).toHaveLength(0);
    expect(document.activeElement).toBe(opener());
  });

  it("a new event or phase closes Details and the reader with no old-event scroll", () => {
    const b = built();
    showPage(b);
    click(pageEntries()[0]);
    expect(dialogs()).toHaveLength(1);
    showPage(finalBuilt()); // RETAINED final: a new phase
    expect(dialogs()).toHaveLength(0);
    expect(pageScroll).not.toHaveBeenCalled();
    showPage(b);
    expect(dialogs()).toHaveLength(0);
    click(opener());
    click(readerEntries()[0]);
    showPage(finalBuilt());
    expect(dialogs()).toHaveLength(0);
    expect(pageScroll).not.toHaveBeenCalled();
  });

  it("no true modal: no dialog, no body lock, both flags released and the inline status by the entry (CONSTRUCTED: showModal removed)", async () => {
    delete dialogProto.showModal;
    const b = built();
    showPage(b);
    const control = pageEntries()[0];
    await clickAndSettle(control);
    expect(dialogs()).toHaveLength(0);
    expect(document.body.style.overflow).toBe("");
    expect(host.querySelector('[data-soccer-reader-status="story"]')?.textContent).toBe(SOCCER_READER_WORDS.fullSizeUnavailable);
    expect(control.disabled).toBe(false);
    expect(opener().disabled).toBe(false);
    expect(document.activeElement).toBe(control);
  });
});

describe("the stream itself takes only a pass serving its own scope", () => {
  it("a pass for another phase offers nothing even when rendered straight into the stream", () => {
    const b = built();
    act(() => root.render(<SoccerMatchStories stream={b.page.stories} cardPass={finalBuilt().pass} />));
    expect(pageEntries()).toHaveLength(0);
    act(() => root.render(<SoccerMatchStories stream={b.page.stories} cardPass={b.pass} />));
    expect(pageEntries()).toHaveLength(1);
  });
});
