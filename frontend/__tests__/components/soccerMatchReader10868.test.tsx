/** @jest-environment jsdom */
/**
 * #10868 — the soccer match's full-size reader (web): "Open full card" and
 * "Full chart" open ONE local native dialog over the page; the story reader
 * holds the exact opened card id, moves only by its own Previous / Next, and
 * shares the page's held choices; the history reader is the same chart in its
 * expanded layout; Close / Escape / cancel return the page's place.
 *
 * Same harness as `soccerMatchPage10868.test.tsx` (react-dom `createRoot` +
 * `act`; the repo has no @testing-library/react), on the same verbatim native
 * soccer fixtures. CONSTRUCTED, and named where used: the owner's story
 * admissions (no production owner supplies them), single edited payloads
 * (reorder, withdrawal, a duplicated id, another event's scope), a page scroll
 * offset, and the exact map's layout rectangles.
 *
 * jsdom 26 implements NO dialog behaviour: `HTMLDialogElement` has no
 * `showModal` or `close`, no top layer, no inert background, no focus
 * containment and no Escape-to-cancel. The stub below only flips the `open`
 * attribute and fires `close`, so these tests prove the reader's STATE and
 * WIRING (what opens, what it shows, what closes it, where focus and scroll are
 * sent). They do NOT prove real browser focus, background isolation, scroll
 * locking, layout at 375 / 393 px or 200% text, or Back behaviour; only a
 * browser check proves those (owed).
 */
import React from "react";
import { createRoot, type Root } from "react-dom/client";
import { act } from "react-dom/test-utils";
import fixtures from "../lib/soccerMatch10868.fixtures.json";
import type { EventDetailResponse, EventHistoryResponse } from "@/lib/types";
import type { GameMarketsResponse } from "@/lib/api";
import { formatProbabilityPercent } from "@/lib/probabilityDisplay";
import { buildSoccerMatch, type SoccerMatchAdmission, type SoccerMatchViewModel } from "@/lib/eventPage10868/soccerMatch";
import type { SoccerGoalsCard, SoccerStoryCard, SoccerStoryStream } from "@/lib/eventPage10868/soccerMatchTypes";
import SoccerMatchPage from "@/components/event/eventpage10868/SoccerMatchPage";
import SoccerMatchStories from "@/components/event/eventpage10868/SoccerMatchStories";
import { SOCCER_READER_WORDS } from "@/components/event/eventpage10868/SoccerMatchReader";

type BodyKey = keyof typeof fixtures.bodies;
type Json = Record<string, unknown>;
const parsed = (key: BodyKey): Json => JSON.parse(fixtures.bodies[key].raw) as Json;
const detail = (key: BodyKey) => parsed(key) as unknown as EventDetailResponse;
const history = (key: BodyKey) => parsed(key) as unknown as EventHistoryResponse;
const markets = (key: BodyKey) => parsed(key) as unknown as GameMarketsResponse;
const pct = formatProbabilityPercent;

const LIVE_NOW = Date.parse(fixtures.provenance.clocks.liveNow);
const FINAL_NOW = Date.parse(fixtures.provenance.clocks.finalNow);
const EXACT_PRE_NOW = Date.parse(fixtures.provenance.clocks.exactPreKickoffNow);

/** CONSTRUCTED owner metadata (native's ids; no production owner supplies it). */
const C = fixtures.constructed as unknown as {
  liveAdmission: SoccerMatchAdmission;
  hullAdmission: SoccerMatchAdmission;
  fullTotals: number[];
  hullDescriptor: NonNullable<SoccerMatchAdmission["exactScore"]>;
};
/** CONSTRUCTED: Hull before kickoff with the goal totals and the exact-score descriptor admitted. */
const HULL_BEFORE_ADMISSION: SoccerMatchAdmission = { ...C.hullAdmission, goals: C.fullTotals, exactScore: C.hullDescriptor };

function page(
  event: EventDetailResponse,
  held: EventHistoryResponse | null,
  body: GameMarketsResponse | null,
  nowMs: number,
  admitted?: SoccerMatchAdmission,
): SoccerMatchViewModel {
  return buildSoccerMatch({
    event,
    history: held,
    gameMarkets: body,
    admitted,
    host: { nowMs, hero: { homeProb: event.hero_probability ?? null, awayProb: null, homePct: null, awayPct: null }, probabilityObservedAt: event.hero_probability_observed_at ?? null },
  });
}

const livePage = page(detail("liveDetail"), history("liveHistory"), markets("liveMarkets"), LIVE_NOW, C.liveAdmission);
const finalPage = page(detail("finalDetail"), history("finalHistory"), markets("finalMarkets"), FINAL_NOW, C.liveAdmission);
const hullPage = page(detail("hullDetail"), history("hullHistory"), markets("hullExactMarkets"), EXACT_PRE_NOW, HULL_BEFORE_ADMISSION);
const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value)) as T;
const names = (stream: SoccerStoryStream) => stream.cards.map((c) => c.name);

// ─── Harness ───────────────────────────────────────────────────────────────

let host: HTMLDivElement;
let root: Root;
let showModalCalls: number;
let pageScroll: jest.SpyInstance;
const dialogProto = HTMLDialogElement.prototype as unknown as { showModal?: () => void; close?: () => void };

beforeEach(() => {
  (globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  // CONSTRUCTED jsdom dialog stub (see header): state only, no browser modality.
  showModalCalls = 0;
  dialogProto.showModal = function (this: HTMLDialogElement) {
    showModalCalls += 1;
    this.setAttribute("open", "");
  };
  dialogProto.close = function (this: HTMLDialogElement) {
    if (!this.hasAttribute("open")) return;
    this.removeAttribute("open");
    this.dispatchEvent(new Event("close"));
  };
  pageScroll = jest.spyOn(window, "scrollTo").mockImplementation(() => undefined);
  // CONSTRUCTED: the page is scrolled 640 px down when a reader opens.
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

function button(label: string, within: ParentNode = host): HTMLButtonElement {
  const found = Array.from(within.querySelectorAll("button")).find((b) => (b.textContent ?? "").startsWith(label));
  if (!found) throw new Error(`no button "${label}"`);
  return found;
}

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

const dialogs = () => Array.from(document.querySelectorAll("dialog"));
const reader = () => {
  const all = dialogs();
  if (all.length !== 1) throw new Error(`expected one reader, found ${all.length}`);
  return all[0];
};
/** The page outside the reader: its own story card, header and controls. */
const pageCard = () => Array.from(host.querySelectorAll("[data-soccer-card]")).find((el) => !el.closest("dialog"))!;
const opener = () => host.querySelector<HTMLButtonElement>('[data-soccer-reader-entry="story"]')!;
const chartEntry = () => host.querySelector<HTMLButtonElement>('[data-soccer-reader-entry="history"]');
const streamNav = () => Array.from(host.querySelectorAll<HTMLButtonElement>("nav button")).filter((b) => !b.closest("dialog"));
const readerTitle = () => reader().querySelector("h2")?.textContent;
const readerPosition = () => reader().querySelector("[data-soccer-reader-position]")?.textContent ?? null;
const readerCardId = () => reader().querySelector("[data-soccer-card]")?.getAttribute("data-soccer-card") ?? null;
const readerNav = () => Array.from(reader().querySelectorAll("nav button")).map((b) => b.textContent);
const goalChip = (within: ParentNode, label: string) =>
  Array.from(within.querySelectorAll<HTMLButtonElement>('[data-soccer-card="goals"] li > button')).find((b) => b.querySelector("span")?.textContent === label)!;
const readout = (within: ParentNode, id: string) =>
  within.querySelector(`[data-soccer-card="${id}"] [data-soccer-chosen]`)?.getAttribute("data-soccer-chosen") ?? null;
const ids = () => Array.from(document.querySelectorAll("[id]")).map((el) => el.id);

const showPage = (match: SoccerMatchViewModel) => act(() => root.render(<SoccerMatchPage match={match} />));
const showStream = (stream: SoccerStoryStream) => act(() => root.render(<SoccerMatchStories stream={stream} />));

// ─── Open, close, reopen ──────────────────────────────────────────────────

describe("Open full card: one modal reader over the page, and Close returns the page's place", () => {
  it("opens the shown story full size under the compact context, and the page's controls rest", () => {
    showPage(livePage);
    expect(dialogs()).toHaveLength(0);
    expect(opener().getAttribute("aria-label")).toBe(`${SOCCER_READER_WORDS.openCard}: ${livePage.stories.cards[0].name}`);
    expect(opener().textContent).toBe(SOCCER_READER_WORDS.openCard);
    click(opener());
    const d = reader();
    expect(d.open).toBe(true);
    expect(showModalCalls).toBe(1);
    expect(d.getAttribute("data-soccer-reader")).toBe("story");
    expect(d.getAttribute("aria-labelledby")).toBe(d.querySelector("h2")?.id);
    expect(readerTitle()).toBe(livePage.stories.cards[0].name);
    expect(readerPosition()).toBe(`1 of ${livePage.stories.cards.length}`);
    expect(readerCardId()).toBe("goals");
    // Compact context: both names, the held score's spoken words, and the state words; not a heading.
    const context = d.querySelector("[data-soccer-reader-context]")!;
    expect(context.textContent).toContain(livePage.header.home);
    expect(context.textContent).toContain(livePage.header.away);
    expect(context.textContent).toContain(livePage.header.state);
    expect(context.querySelector("h1, h2, h3, h4, [id]")).toBeNull();
    // Close is focused once; the page holds still; its stream and entries rest.
    expect(document.activeElement).toBe(button(SOCCER_READER_WORDS.close, d));
    expect(document.body.style.overflow).toBe("hidden");
    expect(streamNav().length).toBe(2);
    expect(streamNav().every((b) => b.disabled)).toBe(true);
    expect(opener().disabled).toBe(true);
    expect(chartEntry()?.disabled).toBe(true);
  });

  it("Close restores the page scroll, then focuses the opener without scrolling; the reader reopens", async () => {
    document.body.style.overflow = "clip"; // CONSTRUCTED prior page style, kept and given back
    showPage(livePage);
    click(opener());
    const focus = jest.spyOn(HTMLElement.prototype, "focus");
    await clickAndSettle(button(SOCCER_READER_WORDS.close, reader()));
    expect(dialogs()).toHaveLength(0);
    expect(document.body.style.overflow).toBe("clip");
    expect(pageScroll).toHaveBeenCalledTimes(1);
    expect(pageScroll).toHaveBeenCalledWith(0, 640);
    expect(document.activeElement).toBe(opener());
    expect(focus.mock.contexts.at(-1)).toBe(opener());
    expect(focus.mock.calls.at(-1)).toEqual([{ preventScroll: true }]);
    expect(streamNav().every((b) => !b.disabled)).toBe(true);
    // Reopen: a fresh modal open, Close focused again.
    click(opener());
    expect(showModalCalls).toBe(2);
    expect(document.activeElement).toBe(button(SOCCER_READER_WORDS.close, reader()));
    expect(document.body.style.overflow).toBe("hidden");
  });

  it("dialog cancel (Escape) is cancelled and closed through the reader's own state, with the same return", async () => {
    showPage(livePage);
    click(opener());
    const cancel = new Event("cancel", { cancelable: true });
    await act(async () => {
      reader().dispatchEvent(cancel);
    });
    expect(cancel.defaultPrevented).toBe(true);
    expect(dialogs()).toHaveLength(0);
    expect(pageScroll).toHaveBeenCalledWith(0, 640);
    expect(document.activeElement).toBe(opener());
  });

  it("a close the browser makes on its own is synced: the reader leaves the page state too", async () => {
    showPage(livePage);
    click(opener());
    await act(async () => {
      reader().close();
    });
    expect(dialogs()).toHaveLength(0);
    expect(opener().disabled).toBe(false);
    click(opener());
    expect(reader().open).toBe(true);
  });

  it("without showModal the dialog opens by its attribute and Escape closes it", async () => {
    delete dialogProto.showModal;
    showPage(livePage);
    click(opener());
    expect(reader().hasAttribute("open")).toBe(true);
    const escape = new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true });
    await act(async () => {
      button(SOCCER_READER_WORDS.close, reader()).dispatchEvent(escape);
    });
    expect(escape.defaultPrevented).toBe(true);
    expect(dialogs()).toHaveLength(0);
    expect(document.activeElement).toBe(opener());
  });

  it("the page going away while a reader is open releases the page and moves nothing", async () => {
    showPage(livePage);
    click(opener());
    await act(async () => {
      root.render(<div />);
    });
    expect(dialogs()).toHaveLength(0);
    expect(document.body.style.overflow).toBe("");
    expect(pageScroll).not.toHaveBeenCalled();
  });
});

// ─── Reader-local navigation ───────────────────────────────────────────────

describe("reader Previous / Next: by name and place, in the offered order with wrap; the page stays where it was", () => {
  const [first, second, third] = names(livePage.stories);

  it("moves only the reader; Close returns to the page's own shown story", async () => {
    expect(livePage.stories.cards.map((c) => c.id)).toEqual(["goals", "both", "first"]);
    showPage(livePage);
    click(opener());
    expect(readerNav()).toEqual([`${SOCCER_READER_WORDS.previous} · ${third}`, `${SOCCER_READER_WORDS.next} · ${second}`]);
    expect(reader().querySelector("nav")?.getAttribute("aria-label")).toBe(livePage.stories.storiesLabel);
    click(button(SOCCER_READER_WORDS.next, reader()));
    expect(readerTitle()).toBe(second);
    expect(readerPosition()).toBe("2 of 3");
    expect(readerCardId()).toBe("both");
    expect(readerNav()).toEqual([`${SOCCER_READER_WORDS.previous} · ${first}`, `${SOCCER_READER_WORDS.next} · ${third}`]);
    // The page underneath has not moved.
    expect(pageCard().getAttribute("data-soccer-card")).toBe("goals");
    expect(host.querySelector('[aria-live="polite"]')?.textContent).toBe(`1 of 3 · ${first}`);
    // Back past the first wraps to the last.
    click(button(SOCCER_READER_WORDS.previous, reader()));
    click(button(SOCCER_READER_WORDS.previous, reader()));
    expect(readerTitle()).toBe(third);
    expect(readerPosition()).toBe("3 of 3");
    expect(showModalCalls).toBe(1);
    await clickAndSettle(button(SOCCER_READER_WORDS.close, reader()));
    expect(pageCard().getAttribute("data-soccer-card")).toBe("goals");
    expect(document.activeElement).toBe(opener());
  });

  it("opens on the story the page moved to, and the page keeps it after the reader roams", async () => {
    showPage(livePage);
    click(button(SOCCER_READER_WORDS.next));
    expect(pageCard().getAttribute("data-soccer-card")).toBe("both");
    click(opener());
    expect(readerCardId()).toBe("both");
    click(button(SOCCER_READER_WORDS.next, reader()));
    expect(readerCardId()).toBe("first");
    await clickAndSettle(button(SOCCER_READER_WORDS.close, reader()));
    expect(pageCard().getAttribute("data-soccer-card")).toBe("both");
  });
});

// ─── Shared held choices ───────────────────────────────────────────────────

describe("held choices are the page's: one reading, two views", () => {
  it("a choice made in the reader is the page's choice on return", async () => {
    showPage(livePage);
    click(button(SOCCER_READER_WORDS.next));
    click(opener());
    expect(readout(reader(), "both")).toBe("242143189");
    click(button("No", reader().querySelector('[data-soccer-card="both"]')!));
    expect(readout(reader(), "both")).toBe("242143190");
    await clickAndSettle(button(SOCCER_READER_WORDS.close, reader()));
    expect(readout(host, "both")).toBe("242143190");
    expect(button("No", pageCard()).getAttribute("aria-pressed")).toBe("true");
  });

  it("a choice made on the page opens in the reader", () => {
    showPage(livePage);
    click(goalChip(pageCard(), "5+ goals"));
    click(opener());
    expect(readout(reader(), "goals")).toBe("242143187");
  });
});

// ─── Identity: same-id update, reorder, withdrawal, duplicate ──────────────

describe("the reader holds the exact opened card id against every live update", () => {
  it("a same-id live update re-reads the card in place: no reopen, no refocus, no scroll", () => {
    showPage(livePage);
    click(opener());
    click(goalChip(reader(), "6+ goals"));
    const d = reader();
    const next = button(SOCCER_READER_WORDS.next, d);
    act(() => next.focus());
    // CONSTRUCTED refresh: the 6+ pre-match pin re-read at a new value, same id.
    const refreshed = clone(livePage);
    const goals = refreshed.stories.cards.find((c) => c.id === "goals") as SoccerGoalsCard;
    goals.milestones[2].pregame = { kind: "value", observation: { probability: 0.08, text: pct(0.08), clock: null, detail: "CONSTRUCTED" } };
    showPage(refreshed);
    expect(reader()).toBe(d);
    expect(showModalCalls).toBe(1);
    expect(readout(d, "goals")).toBe("242765587");
    expect(Array.from(d.querySelector("[data-soccer-chosen]")!.querySelectorAll("dd")).map((dd) => dd.textContent)[0]).toBe(pct(0.08));
    expect(document.activeElement).toBe(next);
    expect(pageScroll).not.toHaveBeenCalled();
  });

  it("CONSTRUCTED reorder keeps the same card at its new place, with its new neighbours", () => {
    showPage(livePage);
    click(opener());
    const reordered = clone(livePage);
    reordered.stories.cards.reverse(); // first, both, goals
    showPage(reordered);
    expect(readerCardId()).toBe("goals");
    expect(readerPosition()).toBe("3 of 3");
    const [first, second] = names(reordered.stories);
    expect(readerNav()).toEqual([`${SOCCER_READER_WORDS.previous} · ${second}`, `${SOCCER_READER_WORDS.next} · ${first}`]);
  });

  it("CONSTRUCTED withdrawal says the story is unavailable and shows no other card; Close stays; the same id returns", async () => {
    showPage(livePage);
    click(button(SOCCER_READER_WORDS.next));
    click(opener());
    const withdrawn = clone(livePage);
    withdrawn.stories.cards = withdrawn.stories.cards.filter((c) => c.id !== "both");
    showPage(withdrawn);
    const d = reader();
    expect(d.querySelector("[data-soccer-reader-unavailable]")?.textContent).toBe(SOCCER_READER_WORDS.storyUnavailable);
    expect(d.querySelector("[data-soccer-reader-unavailable]")?.getAttribute("data-soccer-reader-unavailable")).toBe("missing");
    expect(d.querySelector("[data-soccer-card]")).toBeNull();
    expect(d.querySelector("nav")).toBeNull();
    expect(readerPosition()).toBeNull();
    expect(readerTitle()).toBe(livePage.stories.heading);
    expect(button(SOCCER_READER_WORDS.close, d)).toBeTruthy();
    // Served again with the same id: the same card, never chosen on the reader's behalf before that.
    showPage(livePage);
    expect(readerCardId()).toBe("both");
    expect(readerPosition()).toBe("2 of 3");
    await clickAndSettle(button(SOCCER_READER_WORDS.close, reader()));
    expect(document.activeElement).toBe(opener());
  });

  it("CONSTRUCTED duplicated card id resolves nobody: unavailable, no card, no neighbour", () => {
    showPage(livePage);
    click(opener());
    const twice = clone(livePage);
    (twice.stories.cards[1] as { id: SoccerStoryCard["id"] }).id = "goals";
    showPage(twice);
    const d = reader();
    expect(d.querySelector("[data-soccer-reader-unavailable]")?.getAttribute("data-soccer-reader-unavailable")).toBe("duplicate");
    expect(d.querySelector("[data-soccer-card]")).toBeNull();
    expect(d.querySelector("nav")).toBeNull();
  });
});

// ─── Scope change ──────────────────────────────────────────────────────────

describe("a new event or phase closes the reader and starts a new reading", () => {
  it("kickoff-to-final closes the open reader: choices reset, no scroll back, focus on this match's surviving entry", async () => {
    expect(livePage.stories.scope).not.toBe(finalPage.stories.scope);
    showPage(livePage);
    click(button(SOCCER_READER_WORDS.next));
    click(opener());
    click(button("No", reader().querySelector('[data-soccer-card="both"]')!));
    const focus = jest.spyOn(HTMLElement.prototype, "focus");
    await act(async () => {
      root.render(<SoccerMatchPage match={finalPage} />);
    });
    expect(dialogs()).toHaveLength(0);
    expect(document.body.style.overflow).toBe("");
    expect(pageScroll).not.toHaveBeenCalled();
    // The final's own reading: first story, the owner's default outcome.
    expect(pageCard().getAttribute("data-soccer-card")).toBe("both");
    expect(readout(host, "both")).toBe("242143189");
    expect(document.activeElement?.getAttribute("data-soccer-reader-entry")).toBe("story");
    expect(focus.mock.calls.at(-1)).toEqual([{ preventScroll: true }]);
    expect(streamNav().every((b) => !b.disabled)).toBe(true);
  });

  it("CONSTRUCTED new scope with no story left: focus goes to the history entry that survives", async () => {
    showPage(livePage);
    click(opener());
    const empty = clone(finalPage);
    empty.stories.cards = [];
    await act(async () => {
      root.render(<SoccerMatchPage match={empty} />);
    });
    expect(dialogs()).toHaveLength(0);
    expect(opener()).toBeNull();
    expect(document.activeElement).toBe(chartEntry());
  });

  it("CONSTRUCTED the same cards under another event's scope (stream alone) reset the reader too", () => {
    showStream(livePage.stories);
    click(opener());
    expect(readerCardId()).toBe("goals");
    showStream({ ...clone(livePage.stories), scope: "soccer:999999:live" });
    expect(dialogs()).toHaveLength(0);
    expect(opener().disabled).toBe(false);
  });
});

// ─── History reader ────────────────────────────────────────────────────────

describe("Full chart: the same history inputs in the expanded layout, under the compact context and the headline", () => {
  const xs = (d: string | null) => (d ?? "").split(/[ML]/).filter((s) => s.trim()).map((s) => s.trim().split(/\s+/)[0]);

  it("draws every run, mark, key and note the page draws; only the plot is taller", () => {
    showPage(livePage);
    const entry = chartEntry()!;
    expect(entry.textContent).toBe(SOCCER_READER_WORDS.fullChart);
    expect(entry.getAttribute("aria-label")).toBe(`${SOCCER_READER_WORDS.fullChart}: ${livePage.history.title}`);
    click(entry);
    const d = reader();
    expect(d.getAttribute("data-soccer-reader")).toBe("history");
    expect(readerTitle()).toBe(livePage.history.title);
    expect(d.querySelector("nav")).toBeNull();
    // Compact context first, then the same three-outcome headline, then the chart.
    const body = d.querySelector("[data-soccer-reader-body]")!;
    expect(body.children[0].hasAttribute("data-soccer-reader-context")).toBe(true);
    expect(d.querySelectorAll("[data-soccer-outcome]")).toHaveLength(3);
    const inline = Array.from(host.querySelectorAll("[data-soccer-history]")).find((el) => !el.closest("dialog"))!;
    const expanded = d.querySelector("[data-soccer-history]")!;
    expect(expanded.getAttribute("data-soccer-history")).toBe(inline.getAttribute("data-soccer-history"));
    const paths = (el: Element) => Array.from(el.querySelectorAll('svg[role="img"] path')).map((p) => p.getAttribute("d"));
    expect(paths(expanded)).toHaveLength(paths(inline).length);
    expect(paths(expanded).map(xs)).toEqual(paths(inline).map(xs));
    expect(expanded.querySelectorAll("svg circle").length).toBe(inline.querySelectorAll("svg circle").length);
    for (const part of ["[data-line-key]", "[data-history-basis]", "[data-axis-tick]", "ul[hidden]"]) {
      expect(Array.from(expanded.querySelectorAll(part)).map((el) => el.textContent)).toEqual(Array.from(inline.querySelectorAll(part)).map((el) => el.textContent));
    }
    expect(expanded.querySelector('svg[role="img"]')?.getAttribute("aria-label")).toBe(inline.querySelector('svg[role="img"]')?.getAttribute("aria-label"));
    // Height only: the expanded plot is 130 px taller (360 vs 230).
    const height = (el: Element) => Number(el.querySelector('svg[role="img"]')?.getAttribute("height"));
    expect(height(expanded) - height(inline)).toBe(130);
    // No inspection control and no second Full chart inside.
    expect(d.querySelector("[data-soccer-reader-entry]")).toBeNull();
    expect(Array.from(d.querySelectorAll("button")).map((b) => b.textContent)).not.toContain("Inspect history");
  });

  it("no plotted history, no Full chart; a plot lost while open stays in the reader as the chart's own absence", () => {
    const missing = page(detail("liveDetail"), null, markets("liveMarkets"), LIVE_NOW, C.liveAdmission);
    showPage(missing);
    expect(chartEntry()).toBeNull();
    showPage(livePage);
    click(chartEntry()!);
    // CONSTRUCTED refresh in the same scope: the history response is gone.
    showPage(missing);
    const d = reader();
    const absence = d.querySelector("[data-soccer-history] [style]") as HTMLElement;
    expect(absence.textContent).toContain(missing.history.absence?.title ?? "∅");
    expect(absence.style.minHeight).toBe("360px");
    expect(button(SOCCER_READER_WORDS.close, d)).toBeTruthy();
  });

  it("Close returns to Full chart with the page scroll", async () => {
    showPage(livePage);
    click(chartEntry()!);
    await clickAndSettle(button(SOCCER_READER_WORDS.close, reader()));
    expect(dialogs()).toHaveLength(0);
    expect(pageScroll).toHaveBeenCalledWith(0, 640);
    expect(document.activeElement).toBe(chartEntry());
  });
});

// ─── One shell, one reader, unique ids ─────────────────────────────────────

describe("one reader at a time, and no duplicate ids", () => {
  it("story reader open: the history entry rests; every id in the document is unique", () => {
    showPage(livePage);
    click(opener());
    expect(dialogs()).toHaveLength(1);
    expect(chartEntry()?.disabled).toBe(true);
    click(chartEntry()!);
    expect(dialogs()).toHaveLength(1);
    expect(reader().getAttribute("data-soccer-reader")).toBe("story");
    expect(new Set(ids()).size).toBe(ids().length);
  });

  it("history reader open: the story entry and the stream rest; every id in the document is unique", async () => {
    showPage(livePage);
    click(chartEntry()!);
    expect(opener().disabled).toBe(true);
    expect(streamNav().every((b) => b.disabled)).toBe(true);
    click(opener());
    expect(dialogs()).toHaveLength(1);
    expect(reader().getAttribute("data-soccer-reader")).toBe("history");
    expect(new Set(ids()).size).toBe(ids().length);
    await clickAndSettle(button(SOCCER_READER_WORDS.close, reader()));
    expect(opener().disabled).toBe(false);
  });
});

// ─── Exact map inside the reader ───────────────────────────────────────────
//
// The reader must leave the exact map's own keyboard focus reveal, contained
// horizontal scroll and tab stop alone. jsdom has no layout: the rectangles are
// CONSTRUCTED in the shape of the 375/200 capture used by the page tests; they
// guard the wiring inside the dialog, NOT visual behaviour or touch panning.

describe("the exact map in the reader keeps its focus reveal, its tab stop and its keys", () => {
  const SCROLLER_LEFT = 100;
  const SCROLLER_WIDTH = 211;
  const ROW_NUMBERS_RIGHT = 130;
  const cellLeft = (column: number, scrollLeft: number) => 133 + 83 * column - scrollLeft;

  function withMapGeometry(run: () => void) {
    const scrolled = new WeakMap<Element, number>();
    const proto = HTMLElement.prototype as unknown as Record<string, unknown>;
    Object.defineProperty(proto, "scrollLeft", {
      configurable: true,
      get(this: Element) {
        return scrolled.get(this) ?? 0;
      },
      set(this: Element, value: number) {
        scrolled.set(this, value);
      },
    });
    Object.defineProperty(proto, "clientWidth", {
      configurable: true,
      get(this: HTMLElement) {
        return this.hasAttribute("data-exact-scroller") ? SCROLLER_WIDTH : 0;
      },
    });
    Object.defineProperty(proto, "scrollWidth", {
      configurable: true,
      get(this: HTMLElement) {
        return this.hasAttribute("data-exact-scroller") ? 528 : 0;
      },
    });
    const boxes = jest.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
      const box = (left: number, width: number) => ({ left, width, right: left + width, top: 0, bottom: 80, height: 80, x: left, y: 0, toJSON: () => ({}) }) as DOMRect;
      if (this.hasAttribute("data-exact-scroller")) return box(SCROLLER_LEFT, SCROLLER_WIDTH);
      if (this.matches('th[scope="row"]')) return box(SCROLLER_LEFT, ROW_NUMBERS_RIGHT - SCROLLER_LEFT);
      const td = this.closest("td");
      if (this instanceof HTMLButtonElement && td?.parentElement) {
        const column = Array.from(td.parentElement.children).indexOf(td) - 1;
        const scroller = this.closest("[data-exact-scroller]") as HTMLElement;
        return box(cellLeft(column, scroller.scrollLeft), 80);
      }
      return box(0, 0);
    });
    try {
      run();
    } finally {
      boxes.mockRestore();
      delete proto.scrollLeft;
      delete proto.clientWidth;
      delete proto.scrollWidth;
    }
  }

  it("reached by reader Next, the map scrolls only itself to show a focused cell whole; arrows are not taken", () => {
    expect(hullPage.stories.cards.map((c) => c.id)).toEqual(["goals", "exact"]);
    withMapGeometry(() => {
      showStream(hullPage.stories);
      click(opener());
      click(button(SOCCER_READER_WORDS.next, reader()));
      const d = reader();
      expect(readerCardId()).toBe("exact");
      const scroller = d.querySelector("[data-exact-scroller]") as HTMLElement;
      expect(scroller.tabIndex).toBe(0);
      expect(scroller.getAttribute("role")).toBe("region");
      const target = d.querySelector('td[data-cell="242779560"] button') as HTMLButtonElement; // 0–3
      act(() => target.focus());
      expect(scroller.scrollLeft).toBe(153);
      const box = target.getBoundingClientRect();
      expect(box.left - 2 >= ROW_NUMBERS_RIGHT && box.right + 2 <= SCROLLER_LEFT + SCROLLER_WIDTH).toBe(true);
      expect(document.activeElement).toBe(target);
      expect(target.getAttribute("aria-pressed")).toBe("false");
      // The page's own map (behind the reader) did not move.
      const pageScroller = Array.from(host.querySelectorAll<HTMLElement>("[data-exact-scroller]")).find((el) => !el.closest("dialog"));
      expect(pageScroller?.scrollLeft ?? 0).toBe(0);
      // An arrow key in the map is not the dialog's: not cancelled, reader still open.
      const arrow = new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true, cancelable: true });
      act(() => {
        scroller.dispatchEvent(arrow);
      });
      expect(arrow.defaultPrevented).toBe(false);
      expect(dialogs()).toHaveLength(1);
    });
    expect(pageScroll).not.toHaveBeenCalled();
  });
});
