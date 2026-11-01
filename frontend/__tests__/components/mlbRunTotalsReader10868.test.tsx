/** @jest-environment jsdom */
/**
 * #10868 reader I1 — `MlbRunTotalsReader`: the run-total card at full size in
 * the EXISTING `SoccerMatchReader` shell (unchanged), drawing the SAME
 * `MlbRunTotalsCard` on the SAME controlled B1 selection, plus the card's
 * optional `layout="expanded"` (Design R-F2).
 *
 * SHIP: a baseball fan can explore the same run-total card at full size
 * without losing the selected line or milestone, then return to the same place.
 *
 * TEST HOST (CONSTRUCTED, test-only, NOT production): `TestHost` below holds
 * `{ scope, key, open, unavailable }` the way the later page slot will (B1's
 * scope + key, cleared with `open` on a new scope while rendering). It draws
 * the on-page card, an opener, a status line, a persistent programmatically
 * focusable local anchor (R-F3's fallback) and, while open, the reader. Nothing
 * here is the page binding (a later, separately admitted increment).
 *
 * INPUTS, labelled per test:
 *   - REAL FINAL CAPTURE — `../lib/mlbRunTotals10868.fixtures.json` (the whole
 *     retained 15321836 `game_question_matrix`, byte-unchanged) through the
 *     ACTUAL `mlbRunLines` / `mlbFinalTotals`; names from
 *     `../lib/mlbGame10868.fixtures.json`. The displayed pair is a CONSTRUCTED
 *     host value equal to the retained final row (Astros 3, White Sox 7).
 *   - CONSTRUCTED — every before/live quote, pin, clock and displayed pair (on
 *     a copy of the REAL matrix, through the ACTUAL `mlbRunMilestones`), every
 *     scope transition (live → final, another event id), withdrawn and
 *     duplicated keys, refreshed pairs, the caller's context strings and the
 *     page scroll offset. No genuine before/live specimen is claimed.
 *
 * jsdom implements no dialog behaviour; `showModal` / `close` are stubbed the
 * way `soccerMatchReader10868.test.tsx` stubs them (state only). These tests
 * prove the reader's state and wiring — what opens, what it draws, what closes
 * it, where scroll and focus are sent — and what the markup states. They do
 * NOT prove real modality, focus containment, scroll locking, layout or fit at
 * 375 / 393 px or 200% text, or pixel parity of the expanded plot; only a
 * browser check proves those (owed).
 */
import React, { act, useLayoutEffect, useRef, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import fixture from "../lib/mlbRunTotals10868.fixtures.json";
import mlbFixtures from "../lib/mlbGame10868.fixtures.json";
import {
  MLB_RUN_TOTAL_WORDS,
  mlbFinalTotals,
  mlbRunLines,
  mlbRunMilestones,
  type MlbFinalTotals,
  type MlbRunEvent,
  type MlbRunMilestones,
  type MlbRunTotalsInput,
} from "@/lib/eventPage10868/mlbRunTotals";
import MlbRunTotalsCard, {
  MLB_RUN_PLOT_HEIGHT,
  type MlbRunTotalsColors,
  type MlbRunTotalsSelection,
} from "@/components/event/eventpage10868/MlbRunTotalsCard";
import MlbRunTotalsReader, { MLB_RUN_READER_WORDS, type MlbRunReaderContext } from "@/components/event/eventpage10868/MlbRunTotalsReader";
import { SOCCER_READER_WORDS } from "@/components/event/eventpage10868/SoccerMatchReader";

// ─── Inputs ────────────────────────────────────────────────────────────────

type Json = Record<string, unknown>;
const matrix = (): Json => JSON.parse(JSON.stringify(fixture.game_question_matrix)) as Json;
const questionsOf = (m: Json): Json[] => m.questions as Json[];
const keyOf = (q: Json, field: string): unknown => (q[field] as Json | null | undefined)?.key;
const isFullGameRuns = (q: Json) => q.kind === "count_threshold" && keyOf(q, "quantity") === "runs" && keyOf(q, "period") === "full_game";
function fullGameAt(m: Json, line: number): Json {
  const found = questionsOf(m).filter((q) => isFullGameRuns(q) && (q.predicate as Json).line === line);
  if (found.length !== 1) throw new Error(`expected one full-game question at ${line}`);
  return found[0];
}
const overAt = (m: Json, line: number): Json => (fullGameAt(m, line).options as Json[])[0];

const DETAIL = mlbFixtures.finalDetail;
const NAMES = { home: DETAIL.home_team, away: DETAIL.away_team };
/** CONSTRUCTED host pair, equal to the retained final row. */
const SCORE = { home: DETAIL.home_score, away: DETAIL.away_score };
const FINAL_SCOPE = "mlb:15321836:final";
const LIVE_SCOPE = "mlb:15321836:live";
const BEFORE_SCOPE = "mlb:15321836:before";
/** CONSTRUCTED: another event's final scope. */
const OTHER_FINAL_SCOPE = "mlb:15321837:final";
const KEY_9_5 = "o:244311417";
const KEY_10_5 = "o:244311422";
const KEY_11_5 = "o:244311421";
const KEY_12_5 = "o:244311420";
const COLORS: MlbRunTotalsColors = { home: "var(--series-1)", away: "var(--series-2)" };

/** REAL lines through the ACTUAL helper; `score` is the CONSTRUCTED displayed pair. */
function finalTotals(m: Json = matrix(), score: { home: number | null; away: number | null } = SCORE): MlbFinalTotals {
  const totals = mlbFinalTotals(mlbRunLines(m), score, NAMES);
  if (!totals) throw new Error("no final run totals");
  return totals;
}
/** TEST MUTATION: one full-game line withdrawn. */
function withoutLine(m: Json, line: number): Json {
  m.questions = questionsOf(m).filter((q) => q !== fullGameAt(m, line));
  return m;
}
/** TEST MUTATION: `line`'s Over option carrying `key` (the admission drops both copies). */
function carrying(m: Json, line: number, key: string): Json {
  overAt(m, line).option_key = key;
  return m;
}

/** REAL listed start; every clock below is CONSTRUCTED around it. */
const START = Date.parse(DETAIL.commence_time);
const MIN = 60_000;
const BEFORE_NOW = START - 10 * MIN;
const LIVE_NOW = START + 20 * MIN;
const iso = (ms: number) => new Date(ms).toISOString();
const EVENT: MlbRunEvent = { commence_time: DETAIL.commence_time, sport: DETAIL.sport };
/** CONSTRUCTED displayed pair during play (2 + 3 = 5 runs so far) on its own clock. */
const LIVE_PAIR = { home: 2, away: 3, observedAt: iso(LIVE_NOW - MIN) };
/** CONSTRUCTED: the line's Over option published as a quoted value on its own clock. */
function publish(m: Json, line: number, value: number, observedAt: string): void {
  const o = overAt(m, line);
  o.published = { ...(o.published as Json), value, value_state: "quoted", observed_at: observedAt };
}
/** CONSTRUCTED: an admitted pregame pin (comparable baseline). */
function pinLine(m: Json, line: number, probability: number, observedAt: string): void {
  overAt(m, line).comparison = {
    state: "comparable",
    reason: null,
    baseline: { basis: "pregame_pin", probability, observed_at: observedAt },
    latest: null,
    delta_points: null,
  };
}
/** CONSTRUCTED live readings over the REAL matrix: pins on 9.5 (30%), 10.5 (45%), 12.5 (20%); a recorded 35% on 11.5. */
function liveMatrix(): Json {
  const m = matrix();
  pinLine(m, 9.5, 0.3, iso(START - 30 * MIN));
  pinLine(m, 10.5, 0.45, iso(START - 30 * MIN));
  pinLine(m, 12.5, 0.2, iso(START - 30 * MIN));
  publish(m, 11.5, 0.35, iso(LIVE_NOW - 2 * MIN));
  return m;
}
/** The ACTUAL milestones helper over the ACTUAL admission, with the CONSTRUCTED phase inputs. */
function milestones(m: Json, phase: "before" | "live", now = phase === "before" ? BEFORE_NOW : LIVE_NOW): MlbRunMilestones {
  const built = mlbRunMilestones(mlbRunLines(m), phase, EVENT, phase === "live" ? LIVE_PAIR : null, false, now);
  if (!built) throw new Error("no run milestones");
  return built;
}

/** CONSTRUCTED caller strings for the final (away first, as the page prints them). */
const FINAL_CONTEXT: MlbRunReaderContext = { away: "White Sox", home: "Astros", score: { away: "7", home: "3" }, state: "Final" };

// ─── The test host (CONSTRUCTED, test-only) ────────────────────────────────

type HostState = { scope: string; key: string | null; open: boolean; unavailable: boolean };
const fresh = (scope: string): HostState => ({ scope, key: null, open: false, unavailable: false });
const log = { taps: [] as string[], closes: 0, unavailable: 0, frames: [] as string[] };

/** Records every COMMITTED frame in which the reader is rendered, with the host's scope at that frame. */
function FrameProbe({ scope }: { scope: string }) {
  useLayoutEffect(() => {
    log.frames.push(scope);
  });
  return null;
}

function TestHost({
  totals,
  scope,
  context = FINAL_CONTEXT,
  opener = true,
}: {
  totals: MlbRunTotalsInput | null;
  scope: string;
  context?: MlbRunReaderContext;
  /** CONSTRUCTED: false = the opener has left the page (R-F3's fallback case). */
  opener?: boolean;
}) {
  const [state, setState] = useState<HostState>(() => fresh(scope));
  // A new event or phase: the reader closes and the key clears in THIS render.
  if (state.scope !== scope) setState(fresh(scope));
  const now = state.scope === scope ? state : fresh(scope);
  const entry = useRef<HTMLButtonElement>(null);
  const anchor = useRef<HTMLDivElement>(null);
  const selection: MlbRunTotalsSelection = {
    held: now.key,
    onSelect: (key) => {
      log.taps.push(key);
      setState((s) => (s.scope === scope ? { ...s, key } : s));
    },
  };
  return (
    <section data-test-host={scope}>
      <div ref={anchor} tabIndex={-1} data-test-anchor="">
        {totals && <MlbRunTotalsCard totals={totals} scope={scope} colors={COLORS} selection={selection} />}
        {opener && (
          <button
            ref={entry}
            type="button"
            disabled={now.open}
            onClick={() => setState((s) => ({ ...s, open: true, unavailable: false }))}
            data-test-entry=""
          >
            {SOCCER_READER_WORDS.openCard}
          </button>
        )}
        <p role="status" data-test-status="">
          {now.unavailable ? SOCCER_READER_WORDS.fullSizeUnavailable : null}
        </p>
      </div>
      {now.open && <FrameProbe scope={scope} />}
      {now.open && (
        <MlbRunTotalsReader
          totals={totals}
          scope={scope}
          colors={COLORS}
          selection={selection}
          context={context}
          onClose={() => {
            log.closes += 1;
            setState((s) => ({ ...s, open: false }));
          }}
          onUnavailable={() => {
            log.unavailable += 1;
            setState((s) => ({ ...s, open: false, unavailable: true }));
          }}
          returnTo={() => {
            const own = entry.current;
            return own?.isConnected && !own.disabled ? own : anchor.current;
          }}
        />
      )}
    </section>
  );
}

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

beforeEach(() => {
  (globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  showModalCalls = 0;
  log.taps = [];
  log.closes = 0;
  log.unavailable = 0;
  log.frames = [];
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

const show = (props: React.ComponentProps<typeof TestHost>) => act(() => root.render(<TestHost {...props} />));
/** A render whose commit may close the reader: flushes the shell's focus microtask. */
const showAndSettle = async (props: React.ComponentProps<typeof TestHost>) => {
  await act(async () => {
    root.render(<TestHost {...props} />);
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

const dialogs = () => Array.from(document.querySelectorAll("dialog"));
function reader(): HTMLDialogElement {
  const all = dialogs();
  if (all.length !== 1) throw new Error(`expected one reader, found ${all.length}`);
  return all[0];
}
const outsideReader = (el: Element) => !el.closest("dialog");
const pageCard = () => Array.from(host.querySelectorAll("[data-mlb-run-totals]")).find(outsideReader) ?? null;
const readerCard = () => reader().querySelector("[data-mlb-run-totals]");
const entry = () => host.querySelector<HTMLButtonElement>("[data-test-entry]");
const anchor = () => host.querySelector<HTMLElement>("[data-test-anchor]")!;
const statusText = () => host.querySelector("[data-test-status]")?.textContent ?? null;
function buttonIn(within: ParentNode, label: string): HTMLButtonElement {
  const found = Array.from(within.querySelectorAll("button")).find((b) => (b.textContent ?? "") === label);
  if (!found) throw new Error(`no button "${label}"`);
  return found;
}
const closeButton = () => buttonIn(reader(), SOCCER_READER_WORDS.close);

// The final leaf, inside one instance.
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

// The milestones leaf, inside one instance.
const msChips = (card: Element | null) => Array.from(card?.querySelectorAll<HTMLButtonElement>('[data-soccer-card="goals"] li > button[aria-pressed]') ?? []);
const msLabel = (b: HTMLButtonElement) => b.querySelector("span")?.textContent ?? null;
const msPressed = (card: Element | null) => msChips(card).filter((b) => b.getAttribute("aria-pressed") === "true").map(msLabel);
const msChosen = (card: Element | null) => card?.querySelector("[data-soccer-chosen]")?.getAttribute("data-soccer-chosen") ?? null;
const msUnavailable = (card: Element | null) => card?.querySelector("[data-soccer-selection-unavailable]")?.textContent ?? null;
function msChip(card: Element | null, label: string): HTMLButtonElement {
  const found = msChips(card).filter((b) => msLabel(b) === label);
  if (found.length !== 1) throw new Error(`expected one milestone ${label}`);
  return found[0];
}

/** Any Details or navigation the reader itself offers. */
const readerExtras = () => ({
  details:
    reader().querySelectorAll("[data-soccer-details-entry]").length +
    Array.from(reader().querySelectorAll("button")).filter((b) => (b.textContent ?? "").startsWith("Details")).length,
  nav: reader().querySelectorAll("nav").length,
  position: reader().querySelector("[data-soccer-reader-position]"),
});

/** Every reading, position and control of one final leaf, as data (style positions are the plot's own percentages). */
function finalReading(card: Element | null) {
  if (!card) throw new Error("no final card");
  const all = (selector: string) => Array.from(card.querySelectorAll<HTMLElement>(selector));
  const one = (selector: string) => card.querySelector(selector)?.textContent ?? null;
  return {
    total: one("[data-run-total]"),
    pregame: one("[data-run-pregame]"),
    heading: one("[data-run-heading]"),
    comparison: one("[data-run-comparison]"),
    source: one("[data-run-source]"),
    keys: all("[data-run-key]").map((el) => [el.getAttribute("data-run-key"), el.textContent]),
    segments: all("[data-run-segment]").map((el) => [
      el.getAttribute("data-run-segment"),
      el.getAttribute("data-run-from"),
      el.getAttribute("data-run-to"),
      el.style.left,
      el.style.width,
    ]),
    ticks: all("[data-run-tick]").map((el) => [el.getAttribute("data-run-tick"), el.style.left]),
    axis: all("[data-run-axis-label]").map((el) => [el.textContent, el.style.left]),
    marker: all("[data-run-stem], [data-run-marker]").map((el) => [
      el.getAttribute("data-run-stem") ?? el.getAttribute("data-run-marker"),
      el.style.left,
    ]),
    choices: all("[data-run-choice]").map((el) => [
      el.getAttribute("data-run-choice"),
      el.textContent,
      el.getAttribute("aria-label"),
      el.getAttribute("aria-pressed"),
    ]),
  };
}

// ─── Shared B1 selection ───────────────────────────────────────────────────

describe("one held key, two views: the page card and the reader share the caller's selection", () => {
  it("REAL final: opens on the default; a reader tap emits once and both views move; Close keeps it; reopening shows it", async () => {
    show({ totals: finalTotals(), scope: FINAL_SCOPE });
    expect(dialogs()).toHaveLength(0);
    expect(pressedIn(pageCard())).toEqual([KEY_9_5]); // no choice yet: native's default
    click(entry()!);
    expect(showModalCalls).toBe(1);
    expect(reader().open).toBe(true);
    expect(pressedIn(readerCard())).toEqual([KEY_9_5]);
    click(choiceIn(readerCard(), KEY_10_5));
    expect(log.taps).toEqual([KEY_10_5]);
    expect(pressedIn(readerCard())).toEqual([KEY_10_5]);
    expect(pressedIn(pageCard())).toEqual([KEY_10_5]); // the same key, the same caller
    expect(headingIn(readerCard())).toBe("Over 10.5 runs");
    await clickAndSettle(closeButton());
    expect(dialogs()).toHaveLength(0);
    expect(log.closes).toBe(1);
    expect(pressedIn(pageCard())).toEqual([KEY_10_5]);
    // A page tap emits once too, and the reopened reader shows the caller's choice.
    click(choiceIn(pageCard(), KEY_11_5));
    expect(log.taps).toEqual([KEY_10_5, KEY_11_5]);
    click(entry()!);
    expect(showModalCalls).toBe(2);
    expect(pressedIn(readerCard())).toEqual([KEY_11_5]);
    expect(headingIn(readerCard())).toBe("Over 11.5 runs");
  });

  it("CONSTRUCTED live milestones: the shown default in both views; a reader tap is the page's choice", async () => {
    show({ totals: milestones(liveMatrix(), "live"), scope: LIVE_SCOPE });
    click(entry()!);
    expect(readerCard()?.getAttribute("data-mlb-run-milestones")).toBe("live");
    expect(msChosen(readerCard())).toBe(KEY_10_5); // the shown pin nearest even odds (45%)
    expect(msChosen(pageCard())).toBe(KEY_10_5);
    click(msChip(readerCard(), "13+ runs"));
    expect(log.taps).toEqual([KEY_12_5]);
    expect([msChosen(readerCard()), msChosen(pageCard())]).toEqual([KEY_12_5, KEY_12_5]);
    await clickAndSettle(closeButton());
    expect(msPressed(pageCard())).toEqual(["13+ runs"]);
    click(entry()!);
    expect(msPressed(readerCard())).toEqual(["13+ runs"]);
  });

  it("CONSTRUCTED before first pitch with no shown chance: nothing is chosen in either view until the reader chooses", () => {
    show({ totals: milestones(matrix(), "before"), scope: BEFORE_SCOPE });
    click(entry()!);
    expect(readerCard()?.getAttribute("data-mlb-run-milestones")).toBe("before");
    expect([msChosen(readerCard()), msChosen(pageCard())]).toEqual([null, null]);
    expect([msPressed(readerCard()), msPressed(pageCard())]).toEqual([[], []]);
    expect(msUnavailable(readerCard())).toBeNull();
    click(msChip(readerCard(), "9+ runs"));
    expect(log.taps).toHaveLength(1);
    expect([msPressed(readerCard()), msPressed(pageCard())]).toEqual([["9+ runs"], ["9+ runs"]]);
  });

  it("a withdrawn or duplicated key is unavailable in both views, never a substitute; the exact key's return restores it (TEST MUTATIONS)", () => {
    show({ totals: finalTotals(), scope: FINAL_SCOPE });
    click(entry()!);
    click(choiceIn(readerCard(), KEY_10_5));
    const changed = [withoutLine(matrix(), 10.5), carrying(matrix(), 12.5, KEY_10_5)];
    for (const m of changed) {
      show({ totals: finalTotals(m), scope: FINAL_SCOPE });
      for (const card of [readerCard(), pageCard()]) {
        expect(headingIn(card)).toBe(MLB_RUN_TOTAL_WORDS.selectedUnavailable);
        expect(pressedIn(card)).toEqual([]); // never the 9.5 default or a neighbour
        expect(card?.querySelector("[data-run-marker]")).toBeNull();
        expect(card?.querySelector("[data-run-source]")).toBeNull();
        expect(card?.querySelector(`[data-run-choice="${KEY_10_5}"]`)).toBeNull();
      }
      show({ totals: finalTotals(), scope: FINAL_SCOPE });
      expect([pressedIn(readerCard()), pressedIn(pageCard())]).toEqual([[KEY_10_5], [KEY_10_5]]);
    }
    expect(showModalCalls).toBe(1);
    expect(log.taps).toEqual([KEY_10_5]); // nothing was chosen on the caller's behalf
  });

  it("milestones: a withdrawn or duplicated key says Selected milestone unavailable. in both views; its return restores it (TEST MUTATIONS)", () => {
    show({ totals: milestones(liveMatrix(), "live"), scope: LIVE_SCOPE });
    click(entry()!);
    click(msChip(readerCard(), "13+ runs"));
    const changed = [withoutLine(liveMatrix(), 12.5), carrying(liveMatrix(), 13.5, KEY_12_5)];
    for (const m of changed) {
      show({ totals: milestones(m, "live"), scope: LIVE_SCOPE });
      for (const card of [readerCard(), pageCard()]) {
        expect(msUnavailable(card)).toBe("Selected milestone unavailable.");
        expect(msPressed(card)).toEqual([]);
        expect(msChosen(card)).toBeNull();
      }
      show({ totals: milestones(liveMatrix(), "live"), scope: LIVE_SCOPE });
      expect([msChosen(readerCard()), msChosen(pageCard())]).toEqual([KEY_12_5, KEY_12_5]);
    }
    expect(log.taps).toEqual([KEY_12_5]);
  });

  it("R-F1: the WHOLE input lost keeps the reader open with only the title, Close and the words; no stale figure; its return restores the key", async () => {
    show({ totals: finalTotals(), scope: FINAL_SCOPE });
    click(entry()!);
    click(choiceIn(readerCard(), KEY_10_5));
    const d = reader();
    show({ totals: null, scope: FINAL_SCOPE }); // CONSTRUCTED same-scope pass with no input
    expect(reader()).toBe(d);
    expect(showModalCalls).toBe(1);
    expect(d.querySelector("h2")?.textContent).toBe(MLB_RUN_READER_WORDS.title);
    expect(closeButton()).toBeTruthy();
    expect(d.querySelector("[data-mlb-run-reader-unavailable]")?.textContent).toBe(MLB_RUN_READER_WORDS.storyUnavailable);
    const body = d.querySelector("[data-soccer-reader-body]")!;
    expect(body.textContent).toBe(MLB_RUN_READER_WORDS.storyUnavailable);
    expect(d.querySelector("[data-mlb-run-reader-context]")).toBeNull();
    expect(d.querySelector("[data-mlb-run-totals], [data-run-total], [data-run-choice], [data-soccer-card]")).toBeNull();
    expect(/\d|%/.test(d.textContent ?? "")).toBe(false); // no probability, total or count anywhere in the dialog
    expect(pageCard()).toBeNull();
    // The exact input returns: the key the caller kept, in both views; the context is back.
    show({ totals: finalTotals(), scope: FINAL_SCOPE });
    expect(reader()).toBe(d);
    expect([pressedIn(readerCard()), pressedIn(pageCard())]).toEqual([[KEY_10_5], [KEY_10_5]]);
    expect(d.querySelector("[data-mlb-run-reader-context]")).not.toBeNull();
    expect(log.taps).toEqual([KEY_10_5]);
    // Close still returns while the input is gone.
    show({ totals: null, scope: FINAL_SCOPE });
    await clickAndSettle(closeButton());
    expect(dialogs()).toHaveLength(0);
    expect(pageScroll).toHaveBeenCalledWith(0, 640);
    expect(document.activeElement).toBe(entry());
  });
});

// ─── Live updates and scope ────────────────────────────────────────────────

describe("the caller's updates: same-scope refresh in place; a new event or phase closes and resets", () => {
  it("a same-scope refresh re-reads in place: no second showModal, no refocus, no scroll (CONSTRUCTED pair 4–8)", () => {
    show({ totals: finalTotals(), scope: FINAL_SCOPE });
    click(entry()!);
    const d = reader();
    click(choiceIn(readerCard(), KEY_10_5));
    const chip = choiceIn(readerCard(), KEY_12_5);
    act(() => chip.focus());
    show({ totals: finalTotals(matrix(), { home: 4, away: 8 }), scope: FINAL_SCOPE });
    expect(reader()).toBe(d);
    expect(showModalCalls).toBe(1);
    expect(readerCard()?.querySelector("[data-run-total]")?.textContent).toBe("12");
    expect(pressedIn(readerCard())).toEqual([KEY_10_5]);
    expect(document.activeElement).toBe(chip);
    expect(pageScroll).not.toHaveBeenCalled();
    expect(document.body.style.overflow).toBe("hidden");
  });

  it("CONSTRUCTED live → final in the host: the reader closes in that render (no old-phase frame), the key clears, no scroll, focus to the opener", async () => {
    show({ totals: milestones(liveMatrix(), "live"), scope: LIVE_SCOPE });
    click(entry()!);
    click(msChip(readerCard(), "13+ runs"));
    expect(log.frames.length).toBeGreaterThan(0);
    const focus = jest.spyOn(HTMLElement.prototype, "focus");
    await showAndSettle({ totals: finalTotals(), scope: FINAL_SCOPE });
    expect(dialogs()).toHaveLength(0);
    expect(log.frames.every((s) => s === LIVE_SCOPE)).toBe(true); // never a reader frame under the final scope
    expect(log.closes).toBe(0); // an owner close, not a request
    // KEY_12_5 is also a final line: a leaked key would press it; the final opens on its own default.
    expect(pressedIn(pageCard())).toEqual([KEY_9_5]);
    expect(pageScroll).not.toHaveBeenCalled();
    expect(document.body.style.overflow).toBe("");
    // Focus was inside the dialog, so it was lost: the opener takes it, without a scroll.
    expect(document.activeElement).toBe(entry());
    expect(focus.mock.contexts.at(-1)).toBe(entry());
    expect(focus.mock.calls.at(-1)).toEqual([{ preventScroll: true }]);
  });

  it("CONSTRUCTED another event: the reader closes and the key clears", async () => {
    show({ totals: finalTotals(), scope: FINAL_SCOPE });
    click(entry()!);
    click(choiceIn(readerCard(), KEY_10_5));
    await showAndSettle({ totals: finalTotals(), scope: OTHER_FINAL_SCOPE });
    expect(dialogs()).toHaveLength(0);
    expect(log.frames.includes(OTHER_FINAL_SCOPE)).toBe(false);
    expect(pageCard()?.getAttribute("data-mlb-run-totals")).toBe(OTHER_FINAL_SCOPE);
    expect(pressedIn(pageCard())).toEqual([KEY_9_5]);
    click(entry()!);
    expect(pressedIn(readerCard())).toEqual([KEY_9_5]);
  });

  it.each(["Close", "cancel (Escape)", "the browser's own close"] as const)(
    "%s closes once through the caller, restores the page position and focuses the opener with preventScroll",
    async (how) => {
      document.body.style.overflow = "clip"; // CONSTRUCTED prior page style, kept and given back
      show({ totals: finalTotals(), scope: FINAL_SCOPE });
      click(entry()!);
      expect(document.activeElement).toBe(closeButton()); // the shell focuses Close once per open
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
      expect(log.closes).toBe(1);
      expect(document.body.style.overflow).toBe("clip");
      expect(pageScroll).toHaveBeenCalledTimes(1);
      expect(pageScroll).toHaveBeenCalledWith(0, 640);
      expect(document.activeElement).toBe(entry());
      expect(focus.mock.contexts.at(-1)).toBe(entry());
      expect(focus.mock.calls.at(-1)).toEqual([{ preventScroll: true }]);
      click(entry()!);
      expect(showModalCalls).toBe(2);
      expect(reader().open).toBe(true);
    },
  );

  it("R-F3: with the opener gone (CONSTRUCTED), Close restores the position and focuses the host's persistent local anchor", async () => {
    show({ totals: finalTotals(), scope: FINAL_SCOPE });
    click(entry()!);
    show({ totals: finalTotals(), scope: FINAL_SCOPE, opener: false }); // the opener leaves the page while reading
    expect(entry()).toBeNull();
    const focus = jest.spyOn(HTMLElement.prototype, "focus");
    await clickAndSettle(closeButton());
    expect(dialogs()).toHaveLength(0);
    expect(pageScroll).toHaveBeenCalledWith(0, 640);
    expect(document.activeElement).toBe(anchor());
    expect(focus.mock.contexts.at(-1)).toBe(anchor());
    expect(focus.mock.calls.at(-1)).toEqual([{ preventScroll: true }]);
  });

  it("the owning page going away (returnTo null) releases the page and moves neither scroll nor focus", async () => {
    show({ totals: finalTotals(), scope: FINAL_SCOPE });
    click(entry()!);
    const focus = jest.spyOn(HTMLElement.prototype, "focus");
    await act(async () => {
      root.render(<div />);
    });
    expect(dialogs()).toHaveLength(0);
    expect(document.body.style.overflow).toBe("");
    expect(pageScroll).not.toHaveBeenCalled();
    expect(focus).not.toHaveBeenCalled();
  });
});

// ─── A true modal or nothing ───────────────────────────────────────────────

describe("when the modal cannot open, nothing opens: the caller closes, says so, and the page card still works", () => {
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

  it.each(["missing", "throwing"] as const)("showModal %s: no dialog, overlay or lock; unavailable reported once; focus back unscrolled; a later open works", async (failure) => {
    document.body.style.overflow = "clip"; // CONSTRUCTED prior page style: never replaced by a failed attempt
    show({ totals: finalTotals(), scope: FINAL_SCOPE });
    failures[failure]();
    const focus = jest.spyOn(HTMLElement.prototype, "focus");
    await clickAndSettle(entry()!);
    expect(dialogs()).toHaveLength(0);
    expect(document.querySelector("[open], [aria-modal]")).toBeNull();
    expect(document.body.style.overflow).toBe("clip");
    expect(showModalCalls).toBe(failure === "throwing" ? 1 : 0);
    expect(log.unavailable).toBe(1);
    expect(log.closes).toBe(0);
    expect(statusText()).toBe(SOCCER_READER_WORDS.fullSizeUnavailable);
    expect(entry()!.disabled).toBe(false);
    expect(document.activeElement).toBe(entry());
    expect(focus.mock.calls.at(-1)).toEqual([{ preventScroll: true }]);
    expect(pageScroll).not.toHaveBeenCalled();
    // The on-page card still chooses.
    click(choiceIn(pageCard(), KEY_10_5));
    expect(log.taps).toEqual([KEY_10_5]);
    expect(pressedIn(pageCard())).toEqual([KEY_10_5]);
    // The modal works again: a later attempt opens, on the same key, and the status clears.
    dialogProto.showModal = stubShowModal;
    click(entry()!);
    expect(reader().open).toBe(true);
    expect(pressedIn(readerCard())).toEqual([KEY_10_5]);
    expect(statusText()).toBe("");
  });
});

// ─── One modal, no navigation, unique ids, context, single card ────────────

describe("one modal and nothing else: no history, unique ids, the caller's context only, a single card", () => {
  it("exactly one dialog through taps and refreshes; no history call; every id unique and every label in its own instance", () => {
    const push = jest.spyOn(window.history, "pushState");
    const replace = jest.spyOn(window.history, "replaceState");
    const href = window.location.href;
    for (const [totals, scope] of [
      [finalTotals(), FINAL_SCOPE],
      [milestones(liveMatrix(), "live"), LIVE_SCOPE],
    ] as const) {
      show({ totals, scope });
      click(entry()!);
      expect(dialogs()).toHaveLength(1);
      show({ totals, scope }); // a same-scope refresh
      expect(dialogs()).toHaveLength(1);
      // Both instances are mounted: every id in the document is unique.
      const ids = Array.from(document.querySelectorAll("[id]")).map((el) => el.id);
      expect(ids.length).toBeGreaterThan(1);
      expect(new Set(ids).size).toBe(ids.length);
      // Each labelled element is labelled from inside its own instance.
      for (const labelled of Array.from(document.querySelectorAll("[aria-labelledby]"))) {
        const target = document.getElementById(labelled.getAttribute("aria-labelledby") ?? "");
        expect(target).not.toBeNull();
        expect(target!.closest("dialog")).toBe(labelled.closest("dialog"));
      }
      expect(reader().getAttribute("aria-labelledby")).toBe(reader().querySelector("h2")?.id);
      act(() => root.unmount());
      root = createRoot(host);
    }
    expect(push).not.toHaveBeenCalled();
    expect(replace).not.toHaveBeenCalled();
    expect(window.location.href).toBe(href);
  });

  it("the compact context draws only the caller's strings, away first; no score unless both strings exist; not a heading, no id", () => {
    // CONSTRUCTED strings deliberately unlike the input (the card's own pair is 3–7, total 10): a derived score would show.
    const context: MlbRunReaderContext = { away: "Away Club Name", home: "Home Club Name", score: { away: "8", home: "1" }, state: "CONSTRUCTED state words" };
    show({ totals: finalTotals(), scope: FINAL_SCOPE, context });
    click(entry()!);
    const ctx = reader().querySelector("[data-mlb-run-reader-context]")!;
    const parts = Array.from(ctx.querySelectorAll("[data-mlb-run-reader-team], [data-mlb-run-reader-score]")).map((el) => el.textContent);
    expect(parts).toEqual(["Away Club Name", "8 – 1", "Home Club Name"]);
    expect(ctx.querySelector("[data-mlb-run-reader-state]")?.textContent).toBe("CONSTRUCTED state words");
    expect(ctx.textContent).not.toContain("3 – 7");
    expect(ctx.textContent).not.toContain("7 – 3");
    expect(ctx.querySelector("h1, h2, h3, h4, [id]")).toBeNull();
    // The context sits first in the scrolling body, before the card.
    const body = reader().querySelector("[data-soccer-reader-body]")!;
    expect(body.children[0]).toBe(ctx);
    expect(ctx.compareDocumentPosition(readerCard()!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    // No pair (before first pitch, or a partial pair the caller does not print): names and state only.
    for (const score of [null, { away: "8", home: "" }]) {
      show({ totals: finalTotals(), scope: FINAL_SCOPE, context: { ...context, score } });
      const c = reader().querySelector("[data-mlb-run-reader-context]")!;
      expect(c.querySelector("[data-mlb-run-reader-score]")).toBeNull();
      expect(Array.from(c.querySelectorAll("[data-mlb-run-reader-team]")).map((el) => el.textContent)).toEqual(["Away Club Name", "Home Club Name"]);
      expect(c.textContent).not.toContain("8");
      expect(c.querySelector("[data-mlb-run-reader-state]")?.textContent).toBe("CONSTRUCTED state words");
    }
  });

  it("a single card titled Run totals: no Previous / Next, no place, no Details control, no fake owner ids", () => {
    for (const [totals, scope] of [
      [finalTotals(), FINAL_SCOPE],
      [milestones(liveMatrix(), "live"), LIVE_SCOPE],
    ] as const) {
      show({ totals, scope });
      click(entry()!);
      expect(reader().querySelector("h2")?.textContent).toBe(MLB_RUN_READER_WORDS.title);
      expect(reader().getAttribute("data-soccer-reader")).toBe("story");
      expect(readerExtras()).toEqual({ details: 0, nav: 0, position: null });
      expect(reader().textContent).not.toMatch(/\b1 of 1\b/);
      expect(reader().textContent).not.toContain(SOCCER_READER_WORDS.previous);
      expect(reader().textContent).not.toContain(SOCCER_READER_WORDS.next);
      // The reader card is the page's card, by the caller's scope; its rows are the input's option keys only.
      expect(readerCard()?.getAttribute("data-mlb-run-totals")).toBe(scope);
      const rowIds =
        totals.kind === "final"
          ? Array.from(readerCard()!.querySelectorAll("[data-run-choice]")).map((el) => el.getAttribute("data-run-choice"))
          : Array.from(readerCard()!.querySelectorAll("[data-milestone]")).map((el) => el.getAttribute("data-milestone"));
      const keys = totals.kind === "final" ? totals.lines.map((l) => l.optionKey) : totals.card.milestones.map((m) => m.id);
      expect(rowIds.length).toBeGreaterThan(0);
      expect(rowIds.every((id) => keys.includes(id ?? ""))).toBe(true);
      act(() => root.unmount());
      root = createRoot(host);
    }
  });
});

// ─── R-F2: the expanded final plot ─────────────────────────────────────────

describe("R-F2: the reader's expanded layout gives only the final plot more height; every reading, position and control is the page's", () => {
  it("REAL final: the reader and the page card state the same readings, ticks, axis, bar and marker; a reader tap moves the marker in both, never the scale", () => {
    show({ totals: finalTotals(), scope: FINAL_SCOPE });
    click(entry()!);
    const page = finalReading(pageCard());
    expect(finalReading(readerCard())).toEqual(page);
    // Non-vacuity: the real final's figures are all there.
    expect(page.total).toBe("10");
    expect(page.choices).toHaveLength(13);
    expect(page.ticks).toHaveLength(13);
    expect(page.segments).toHaveLength(2);
    expect(page.axis.length).toBeGreaterThan(1);
    expect(page.marker.map(([line]) => line)).toEqual(["9.5", "9.5"]);
    expect(page.ticks.every(([, left]) => left !== "")).toBe(true);
    // The layouts: the reader's plot is the expanded one, the page's is the page one.
    const readerPlot = readerCard()!.querySelector("[data-run-plot]")!;
    const pagePlot = pageCard()!.querySelector("[data-run-plot]")!;
    expect([readerPlot.getAttribute("data-run-plot"), pagePlot.getAttribute("data-run-plot")]).toEqual(["expanded", ""]);
    expect(readerPlot.firstElementChild?.classList.contains(MLB_RUN_PLOT_HEIGHT.expanded)).toBe(true);
    expect(pagePlot.firstElementChild?.classList.contains(MLB_RUN_PLOT_HEIGHT.page)).toBe(true);
    // Interaction: a reader tap moves the diamond in both instances; the axis, ticks and bar stay put.
    click(choiceIn(readerCard(), KEY_12_5));
    const after = finalReading(readerCard());
    expect(after).toEqual(finalReading(pageCard()));
    expect(after.marker.map(([line]) => line)).toEqual(["12.5", "12.5"]);
    expect({ axis: after.axis, ticks: after.ticks, segments: after.segments }).toEqual({ axis: page.axis, ticks: page.ticks, segments: page.segments });
  });

  it("the default is the page layout, byte for byte; expanded differs ONLY in the plot's own attribute and marks-area height; milestones ignore layout", () => {
    const totals = finalTotals();
    act(() => root.render(<MlbRunTotalsCard totals={totals} scope={FINAL_SCOPE} />));
    const byDefault = host.innerHTML;
    expect(host.querySelector("[data-run-plot]")?.getAttribute("data-run-plot")).toBe("");
    act(() => root.render(<MlbRunTotalsCard totals={totals} scope={FINAL_SCOPE} layout="page" />));
    expect(host.innerHTML).toBe(byDefault);
    act(() => root.render(<MlbRunTotalsCard totals={totals} scope={FINAL_SCOPE} layout="expanded" />));
    const expanded = host.innerHTML;
    expect(expanded).not.toBe(byDefault);
    expect(expanded.replace('data-run-plot="expanded"', 'data-run-plot=""').replace(MLB_RUN_PLOT_HEIGHT.expanded, MLB_RUN_PLOT_HEIGHT.page)).toBe(byDefault);
    // The milestones leaf has no expanded form: the same markup either way.
    const live = milestones(liveMatrix(), "live");
    act(() => root.render(<MlbRunTotalsCard totals={live} scope={LIVE_SCOPE} />));
    const milestonesPage = host.innerHTML;
    expect(host.querySelector('[data-soccer-card="goals"]')).not.toBeNull();
    act(() => root.render(<MlbRunTotalsCard totals={live} scope={LIVE_SCOPE} layout="expanded" />));
    expect(host.innerHTML).toBe(milestonesPage);
  });
});
