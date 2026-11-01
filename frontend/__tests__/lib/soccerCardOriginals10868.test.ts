/**
 * #10868 — a soccer story card's Details open that row's EXACT original
 * (`soccerCardOriginals.ts`, the web port of native
 * `SoccerCardOriginalsAdapter10868`; cases ported from its tests,
 * BainLuckTests/SoccerCardOriginalsAdapter10868Tests.swift, blob f69f60b6).
 *
 * BODIES — `soccerMatch10868.fixtures.json`, READ-ONLY: the production response
 * bodies copied verbatim from the native soccer fixtures (its `provenance`
 * names the commit, files and hashes), each at its own capture clock:
 * Valladolid–Albacete 15325054 live (`liveDetail`/`liveHistory`/`liveMarkets`,
 * `liveNow`) and final (`final*`, `finalNow`); Hull–Everton 15311089 before
 * kickoff with every exact-score row (`hullDetail`/`hullHistory`/
 * `hullExactMarkets`, `hullNow`) and after the final (`hullFinalDetail`/
 * `hullFinalMarkets`, `exactFinalNow`).
 *
 * Labels, per test:
 *   - RETAINED — those bodies unedited, at their own clocks, under the
 *     fixture's shared CONSTRUCTED owner admissions (`constructed.liveAdmission`;
 *     `hullAdmission` + `fullTotals` + `hullDescriptor` = native
 *     `hullBeforeAdmission`) and the page's existing route contexts. No
 *     production owner supplies a story admission, so every admission is
 *     CONSTRUCTED owner metadata by nature.
 *   - CONSTRUCTED — the test adds its own admission, descriptor, body edit,
 *     catalogue splice or pass; each is named CONSTRUCTED where made. The
 *     constructed market id 99000001 names no served market.
 *
 * Every expected market, outcome and identity below is a literal id from the
 * native tests; nothing here derives an identity, a price, a grade or a clock.
 */

import fixtures from "./soccerMatch10868.fixtures.json";
import fs from "node:fs";
import path from "node:path";
import type { EventDetailResponse, EventHistoryResponse } from "@/lib/types";
import type { GameMarketsResponse } from "@/lib/api";
import {
  buildSoccerMatch,
  type SoccerHalvesAdmission,
  type SoccerMatchAdmission,
  type SoccerMatchViewModel,
} from "@/lib/eventPage10868/soccerMatch";
import type { SoccerStoryId } from "@/lib/eventPage10868/soccerMatchTypes";
import {
  buildSoccerCardPass,
  isAdmitted,
  isOffered,
  openBoth,
  openExact,
  openFirst,
  openGoal,
  openHalf,
  resolveOrigin,
  soccerCardOffersDetails,
  soccerCardOpened,
  soccerCardShown,
  type SoccerBothRef,
  type SoccerCardHold,
  type SoccerCardOpened,
  type SoccerCardPass,
  type SoccerOriginalSelection,
} from "@/lib/eventPage10868/soccerCardOriginals";

// ─── Bodies, clocks, admissions ────────────────────────────────────────────

type BodyKey = keyof typeof fixtures.bodies;
type Json = Record<string, unknown>;
const parsed = (key: BodyKey): Json => JSON.parse(fixtures.bodies[key].raw) as Json;

const LIVE_NOW = Date.parse(fixtures.provenance.clocks.liveNow);
const FINAL_NOW = Date.parse(fixtures.provenance.clocks.finalNow);
const HULL_NOW = Date.parse(fixtures.provenance.clocks.hullNow);
const HULL_FINAL_NOW = Date.parse(fixtures.provenance.clocks.exactFinalNow);

/** CONSTRUCTED owner metadata (the fixture's, from the native tests). */
const C = fixtures.constructed as unknown as {
  liveAdmission: SoccerMatchAdmission;
  hullAdmission: SoccerMatchAdmission;
  fullTotals: number[];
  hullDescriptor: NonNullable<SoccerMatchAdmission["exactScore"]>;
};
const LIVE = C.liveAdmission;
/** Native `SoccerExactRetained10868.hullBeforeAdmission`. */
const HULL_BEFORE: SoccerMatchAdmission = { ...C.hullAdmission, goals: C.fullTotals, exactScore: C.hullDescriptor };

const LIVE_SCOPE = "soccer:15325054:live:originals";
const FINAL_SCOPE = "soccer:15325054:final:originals";
const HULL_BEFORE_SCOPE = "soccer:15311089:before:originals";
const HULL_FINAL_SCOPE = "soccer:15311089:final:originals";

const clone = <T>(x: T): T => JSON.parse(JSON.stringify(x)) as T;

/** CONSTRUCTED (native `F.editedRow`): the ONE row of `array` whose contributor ids are exactly `[outcomeId]`, with only `setting` changed. */
function editedRow(body: Json, outcomeId: number, setting: Json, array = "other"): Json {
  const copy = clone(body);
  const rows = copy[array] as Json[];
  const index = rows.findIndex((row) => JSON.stringify(row.contributor_outcome_ids) === JSON.stringify([outcomeId]));
  if (index < 0) throw new Error(`no ${array} row for ${outcomeId}`);
  rows[index] = { ...rows[index], ...setting };
  return copy;
}

/** CONSTRUCTED (native `removingRow`): the body without the ONE row of `array` naming exactly `[outcomeId]`. */
function removingRow(body: Json, outcomeId: number, array = "other"): Json {
  const copy = clone(body);
  const rows = copy[array] as Json[];
  const index = rows.findIndex((row) => JSON.stringify(row.contributor_outcome_ids) === JSON.stringify([outcomeId]));
  if (index < 0) throw new Error(`no ${array} row for ${outcomeId}`);
  rows.splice(index, 1);
  return copy;
}

interface Built {
  event: EventDetailResponse;
  markets: GameMarketsResponse | null;
  page: SoccerMatchViewModel;
  pass: SoccerCardPass;
}

/** One host pass: the page built ONCE by the real builder, then the bridge's pass from the SAME inputs. */
function built(
  o: {
    detail?: BodyKey;
    history?: BodyKey | null;
    markets?: Json | null;
    admitted?: SoccerMatchAdmission;
    now?: number;
    halves?: SoccerHalvesAdmission;
    cards?: SoccerStoryId[];
  } = {},
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
    halvesAdmission: o.halves ?? "routeDefault",
    admittedCards: o.cards ?? [],
    host: { nowMs, hero: null, probabilityObservedAt: null },
  });
  const pass = buildSoccerCardPass({ event, gameMarkets: markets, admission: admitted, nowMs, page });
  return { event, markets, page, pass };
}

const finalPage = (o: { admitted?: SoccerMatchAdmission } = {}) =>
  built({ detail: "finalDetail", history: "finalHistory", markets: parsed("finalMarkets"), now: FINAL_NOW, ...o });
const hull = (o: { markets?: Json; admitted?: SoccerMatchAdmission } = {}) =>
  built({ detail: "hullDetail", history: "hullHistory", markets: parsed("hullExactMarkets"), admitted: HULL_BEFORE, now: HULL_NOW, ...o });

const sel = (scope: string, market: string, side: string, source = "polymarket"): SoccerOriginalSelection => ({
  scope,
  identity: { source, market, side },
});
const ref = (outcomeId: string, eventId = 15325054, marketId = 64353426): SoccerBothRef => ({ eventId, marketId, outcomeId });
const held = (hold: SoccerCardHold): SoccerCardOpened => ({ kind: "held", hold });
function holdOf(opened: SoccerCardOpened): SoccerCardHold {
  if (opened.kind !== "held") throw new Error(`unresolved ${opened.card}`);
  return opened.hold;
}
const unresolved = (card: SoccerStoryId): SoccerCardOpened => ({ kind: "unresolved", card });
/** The catalogue still lists this selection's original exactly once (the All props row). */
const listed = (b: Built, s: SoccerOriginalSelection) =>
  b.page.originals.scope === s.scope &&
  b.page.originals.originals.filter(
    (o) => o.identity.source === s.identity.source && o.identity.market === s.identity.market && o.identity.side === s.identity.side,
  ).length === 1;
const cardIds = (b: Built) => {
  const card = (id: SoccerStoryId) => b.page.stories.cards.find((c) => c.id === id);
  const goals = card("goals");
  const both = card("both");
  const first = card("first");
  const halves = card("halves");
  const exact = card("exact");
  return {
    goals: goals && goals.id === "goals" ? goals.milestones.map((m) => m.id) : null,
    both: both && both.id === "both" ? both.outcomes.map((o) => o.id) : null,
    first: first && first.id === "first" ? first.rows.map((r) => r.id) : null,
    halves: halves && halves.id === "halves" ? halves.series.flatMap((s) => s.cells.map((c) => c.id)) : null,
    exact: exact && exact.id === "exact" ? exact.scopes.map((s) => ({ id: s.id, originals: s.originals.map((o) => o.id) })) : null,
  };
};

// ─── The pass's scope ──────────────────────────────────────────────────────

describe("each pass serves one event, phase, stream and catalogue", () => {
  it("expects exactly the catalogue scope the page's own builder gives (drift guard)", () => {
    for (const [b, scope] of [
      [built(), LIVE_SCOPE],
      [finalPage(), FINAL_SCOPE],
      [hull(), HULL_BEFORE_SCOPE],
    ] as const) {
      expect(b.page.originals.scope).toBe(scope);
      expect(b.pass.consistent).toBe(true);
      expect(b.pass.catalogue).toBe(b.page.originals);
    }
  });

  it("a foreign event, phase or catalogue makes a pass that resolves nothing (CONSTRUCTED passes)", () => {
    const live = built();
    const final = finalPage();
    const goal = holdOf(openGoal("242143183", live.pass));
    // The final page handed to a live pass (another phase).
    const phase = buildSoccerCardPass({ event: live.event, gameMarkets: live.markets, admission: LIVE, nowMs: LIVE_NOW, page: final.page });
    // The live page under another event id.
    const otherEvent = { ...clone(live.event), id: 15325055 } as EventDetailResponse;
    const event = buildSoccerCardPass({ event: otherEvent, gameMarkets: live.markets, admission: LIVE, nowMs: LIVE_NOW, page: live.page });
    // The live page with the final catalogue spliced in.
    const spliced = { ...live.page, originals: final.page.originals };
    const catalogue = buildSoccerCardPass({ event: live.event, gameMarkets: live.markets, admission: LIVE, nowMs: LIVE_NOW, page: spliced });
    for (const pass of [phase, event, catalogue]) {
      expect(pass.consistent).toBe(false);
      expect(pass.catalogue).toBeNull();
      expect(pass.legsByMarket.size).toBe(0);
      expect(openGoal("242143183", pass)).toEqual(unresolved("goals"));
      expect(soccerCardShown(held(goal), pass)).toBeNull();
      expect(soccerCardOffersDetails("goals", pass)).toBe(false);
    }
  });

  it("another event's markets read as none (CONSTRUCTED: the live body under another event id)", () => {
    const body = { ...parsed("liveMarkets"), event_id: 1 };
    const b = built({ markets: body });
    expect(b.pass.consistent).toBe(true);
    expect([...b.pass.legsByMarket.values()].every((legs) => legs.length === 0)).toBe(true);
    expect(b.pass.servedBySide.size).toBe(0);
    expect(soccerCardOffersDetails("goals", b.pass)).toBe(false);
  });
});

// ─── Exact rows (RETAINED) ─────────────────────────────────────────────────

describe("each of the five card families opens its own row's exact original (RETAINED)", () => {
  it("during play every goal milestone, both-teams outcome and first-team row opens its own original", () => {
    const b = built();
    const ids = cardIds(b);
    expect(ids.goals).toEqual(["242143183", "242143187", "242765587"]);
    expect(ids.both).toEqual(["242143190", "242143189"]);
    expect(ids.first).toEqual(["244237963", "244237965", "244237964"]);
    for (const [id, market] of [
      ["242143183", 64353423],
      ["242143187", 64353425],
      ["242765587", 64536538],
    ] as const) {
      const expected = sel(LIVE_SCOPE, String(market), id);
      const opened = openGoal(id, b.pass);
      expect(opened).toEqual(held({ origin: { card: "goals", market, id }, selection: expected }));
      const shown = soccerCardShown(opened, b.pass);
      expect(shown?.selection).toEqual(expected);
      expect(shown?.original.identity).toEqual(expected.identity);
      expect(b.page.originals.originals).toContain(shown?.original);
    }
    for (const outcome of ["242143190", "242143189"]) {
      expect(openBoth(ref(outcome), b.pass)).toEqual(
        held({ origin: { card: "both", market: 64353426, ref: ref(outcome) }, selection: sel(LIVE_SCOPE, "64353426", outcome) }),
      );
    }
    for (const id of ["244237963", "244237965", "244237964"]) {
      expect(openFirst(id, b.pass)).toEqual(
        held({ origin: { card: "first", market: 63178217, id }, selection: sel(LIVE_SCOPE, "63178217", id) }),
      );
    }
  });

  it("under the explicit half admission each cell opens its own half's original; a bare or composed id names no cell", () => {
    const b = built({ halves: "explicit" });
    expect(new Set(cardIds(b).halves)).toEqual(
      new Set([
        "63178219:242338171",
        "63178218:246041831",
        "63178219:242338170",
        "63178218:245875499",
        "63178219:242338172",
        "63178218:245681743",
      ]),
    );
    for (const [cell, market, period, side] of [
      ["63178219:242338171", 63178219, "first", "242338171"],
      ["63178219:242338170", 63178219, "first", "242338170"],
      ["63178219:242338172", 63178219, "first", "242338172"],
      ["63178218:246041831", 63178218, "second", "246041831"],
      ["63178218:245875499", 63178218, "second", "245875499"],
      ["63178218:245681743", 63178218, "second", "245681743"],
    ] as const) {
      expect(openHalf(cell, b.pass)).toEqual(
        held({ origin: { card: "halves", market, period, id: cell }, selection: sel(LIVE_SCOPE, String(market), side) }),
      );
    }
    expect(openHalf("242338171", b.pass)).toEqual(unresolved("halves"));
    expect(openHalf("63178218:242338171", b.pass)).toEqual(unresolved("halves"));
  });

  it("after the final both, first and half cards open their own settled originals; no goals card offers Details", () => {
    const b = built({ detail: "finalDetail", history: "finalHistory", markets: parsed("finalMarkets"), now: FINAL_NOW });
    expect(b.page.originals.scope).toBe(FINAL_SCOPE);
    expect(cardIds(b).goals).toBeNull();
    expect(soccerCardOffersDetails("goals", b.pass)).toBe(false);
    expect(openBoth(ref("242143189"), b.pass)).toEqual(
      held({ origin: { card: "both", market: 64353426, ref: ref("242143189") }, selection: sel(FINAL_SCOPE, "64353426", "242143189") }),
    );
    expect(openFirst("244237963", b.pass)).toEqual(
      held({ origin: { card: "first", market: 63178217, id: "244237963" }, selection: sel(FINAL_SCOPE, "63178217", "244237963") }),
    );
    expect(openHalf("63178219:242338171", b.pass)).toEqual(
      held({
        origin: { card: "halves", market: 63178219, period: "first", id: "63178219:242338171" },
        selection: sel(FINAL_SCOPE, "63178219", "242338171"),
      }),
    );
    expect(openHalf("63178218:246041831", b.pass)).toEqual(
      held({
        origin: { card: "halves", market: 63178218, period: "second", id: "63178218:246041831" },
        selection: sel(FINAL_SCOPE, "63178218", "246041831"),
      }),
    );
    for (const card of ["both", "first", "halves"] as const) expect(soccerCardOffersDetails(card, b.pass)).toBe(true);
    expect(soccerCardOffersDetails("history", b.pass)).toBe(false);
  });

  it("before kickoff the goal outlook and the exact-score map open their served originals, scope by scope", () => {
    const b = hull();
    expect(b.page.originals.scope).toBe(HULL_BEFORE_SCOPE);
    expect(cardIds(b).goals).toEqual(["238847193", "237512062"]);
    for (const [id, market] of [
      ["238847193", 63390534],
      ["237512062", 62958651],
    ] as const) {
      expect(openGoal(id, b.pass)).toEqual(
        held({ origin: { card: "goals", market, id }, selection: sel(HULL_BEFORE_SCOPE, String(market), id) }),
      );
    }
    const full = openExact("full", "238846934", b.pass);
    const first = openExact("first", "244588607", b.pass);
    expect(full).toEqual(
      held({
        origin: { card: "exact", scope: "full", market: 62939468, period: null, original: "238846934" },
        selection: sel(HULL_BEFORE_SCOPE, "62939468", "238846934"),
      }),
    );
    expect(first).toEqual(
      held({
        origin: { card: "exact", scope: "first", market: 64002155, period: "first", original: "244588607" },
        selection: sel(HULL_BEFORE_SCOPE, "64002155", "244588607"),
      }),
    );
    expect(openExact("first", "238846934", b.pass)).toEqual(unresolved("exact"));
    expect(openExact("full", "244588607", b.pass)).toEqual(unresolved("exact"));
    // Every served original of both scopes opens; the owner's held (unserved) ones do not.
    const scopes = cardIds(b).exact ?? [];
    expect(scopes.map((s) => s.id)).toEqual(["full", "first"]);
    const card = b.page.stories.cards.find((c) => c.id === "exact");
    if (!card || card.id !== "exact") throw new Error("no exact card");
    for (const scope of card.scopes) {
      for (const original of scope.originals) {
        expect({ scope: scope.id, original: original.id, opens: openExact(scope.id, original.id, b.pass).kind === "held" }).toEqual({
          scope: scope.id,
          original: original.id,
          opens: !original.held,
        });
      }
    }
    expect(soccerCardOffersDetails("exact", b.pass)).toBe(true);
  });

  it("CONSTRUCTED owner context (admittedCards: exact after the final): unserved first-half originals stay unavailable; the served 2–2 opens", () => {
    const b = built({
      detail: "hullFinalDetail",
      history: null,
      markets: parsed("hullFinalMarkets"),
      admitted: HULL_BEFORE,
      now: HULL_FINAL_NOW,
      cards: ["exact"],
    });
    const first = (cardIds(b).exact ?? []).find((s) => s.id === "first");
    expect(first?.originals.length).toBe(9);
    for (const original of first?.originals ?? []) expect(openExact("first", original, b.pass)).toEqual(unresolved("exact"));
    expect(openExact("full", "237459055", b.pass)).toEqual(
      held({
        origin: { card: "exact", scope: "full", market: 62939468, period: null, original: "237459055" },
        selection: sel(HULL_FINAL_SCOPE, "62939468", "237459055"),
      }),
    );
    expect(soccerCardOffersDetails("exact", b.pass)).toBe(true);
  });

  it("the same outcome name in three markets opens three different originals, never one by its words", () => {
    const b = built({ halves: "explicit" });
    expect(
      [openFirst("244237963", b.pass), openHalf("63178219:242338171", b.pass), openHalf("63178218:246041831", b.pass)].map(
        (o) => holdOf(o).selection,
      ),
    ).toEqual([sel(LIVE_SCOPE, "63178217", "244237963"), sel(LIVE_SCOPE, "63178219", "242338171"), sel(LIVE_SCOPE, "63178218", "246041831")]);
    expect(holdOf(openHalf("63178219:242338170", b.pass)).selection).not.toEqual(holdOf(openHalf("63178218:245875499", b.pass)).selection);
  });
});

// ─── Hold the origin, not just a selection (CONSTRUCTED) ────────────────────

describe("a held origin is revalidated on every pass and never adopts a replacement", () => {
  it("a same-id refresh with reordered rows keeps the resolution, reads the CURRENT pass's original, and mutates no input", () => {
    const before = built();
    const goal = holdOf(openGoal("242143183", before.pass));
    const both = holdOf(openBoth(ref("242143189"), before.pass));
    // CONSTRUCTED refresh: a fresh parse of the same body with every served array in reverse order.
    const body = parsed("liveMarkets");
    for (const key of ["totals", "spreads", "team_totals", "period_markets", "other"]) {
      if (Array.isArray(body[key])) body[key] = [...(body[key] as unknown[])].reverse();
    }
    const snapshot = JSON.stringify(body);
    const after = built({ markets: body, now: LIVE_NOW + 60_000 });
    for (const hold of [goal, both]) {
      const shown = soccerCardShown(held(hold), after.pass);
      expect(shown?.selection).toEqual(hold.selection);
      // The current pass's own original object, not the one the tap saw.
      expect(after.page.originals.originals).toContain(shown?.original);
      expect(before.page.originals.originals).not.toContain(shown?.original);
    }
    expect(JSON.stringify(body)).toBe(snapshot);
    expect(Object.isFrozen(after.pass)).toBe(true);
  });

  it("C1a: a card moved to another market refuses its held original while both originals stay in All props", () => {
    const before = built();
    const goal = holdOf(openGoal("242143183", before.pass));
    const both = holdOf(openBoth(ref("242143189"), before.pass));
    const moved: SoccerMatchAdmission = { ...LIVE, goals: [64536538], both: 64353427 }; // CONSTRUCTED
    const after = built({ admitted: moved });
    expect(listed(after, goal.selection)).toBe(true);
    expect(listed(after, sel(LIVE_SCOPE, "64536538", "242765587"))).toBe(true);
    expect(listed(after, both.selection)).toBe(true);
    expect(listed(after, sel(LIVE_SCOPE, "64353427", "242143192"))).toBe(true);
    expect(cardIds(after).goals).toEqual(["242765587"]);
    expect(isAdmitted(goal.origin, after.pass)).toBe(false);
    expect(isAdmitted(both.origin, after.pass)).toBe(false);
    expect(soccerCardShown(held(goal), after.pass)).toBeNull();
    expect(soccerCardShown(held(both), after.pass)).toBeNull();
    // CONTROL: the pass it was opened in still shows it.
    expect(soccerCardShown(held(goal), before.pass)?.selection).toEqual(goal.selection);
  });

  it("C1b: an exact scope rebound to another market or period refuses its held original", () => {
    const before = hull();
    const full = holdOf(openExact("full", "238846934", before.pass));
    const first = holdOf(openExact("first", "244588607", before.pass));
    const rebind = (id: string, marketId: number, periodId: string | null): SoccerMatchAdmission => ({
      ...HULL_BEFORE,
      exactScore: {
        ...C.hullDescriptor,
        scopes: C.hullDescriptor.scopes.map((s) => (s.id === id ? { ...s, marketId, periodId } : s)),
      },
    }); // CONSTRUCTED
    const market = hull({ admitted: rebind("full", 64002155, null) });
    expect(listed(market, full.selection)).toBe(true);
    expect(isOffered(full.origin, market.pass)).toBe(true);
    expect(isAdmitted(full.origin, market.pass)).toBe(false);
    expect(soccerCardShown(held(full), market.pass)).toBeNull();
    expect(openExact("full", "238846934", market.pass)).toEqual(unresolved("exact"));
    const period = hull({ admitted: rebind("first", 64002155, "second") });
    expect(listed(period, first.selection)).toBe(true);
    expect(isOffered(first.origin, period.pass)).toBe(true);
    expect(isAdmitted(first.origin, period.pass)).toBe(false);
    expect(soccerCardShown(held(first), period.pass)).toBeNull();
    // CONTROL.
    expect(soccerCardShown(held(full), before.pass)?.selection).toEqual(full.selection);
    expect(soccerCardShown(held(first), before.pass)?.selection).toEqual(first.selection);
  });

  it("C1c: each removed admission refuses its held original; a half card off the route refuses too", () => {
    const live = built({ halves: "explicit" });
    const goal = holdOf(openGoal("242143183", live.pass));
    const both = holdOf(openBoth(ref("242143189"), live.pass));
    const first = holdOf(openFirst("244237963", live.pass));
    const half = holdOf(openHalf("63178219:242338171", live.pass));
    const removed: Array<[SoccerMatchAdmission, SoccerCardHold]> = [
      [{ ...LIVE, goals: [] }, goal],
      [{ ...LIVE, both: null }, both],
      [{ ...LIVE, first: null }, first],
      [{ ...LIVE, halves: [] }, half],
    ];
    for (const [admitted, hold] of removed) {
      const after = built({ admitted, halves: "explicit" }); // CONSTRUCTED admissions
      expect(listed(after, hold.selection)).toBe(true);
      expect(soccerCardShown(held(hold), after.pass)).toBeNull();
    }
    const routed = built(); // the route default during play: the half card leaves the page, its admission stays
    expect(cardIds(routed).halves).toBeNull();
    expect(isAdmitted(half.origin, routed.pass)).toBe(true);
    expect(soccerCardShown(held(half), routed.pass)).toBeNull();
    const exact = holdOf(openExact("full", "238846934", hull().pass));
    const gone = hull({ admitted: { ...HULL_BEFORE, exactScore: null } }); // CONSTRUCTED
    expect(cardIds(gone).exact).toBeNull();
    expect(listed(gone, exact.selection)).toBe(true);
    expect(soccerCardShown(held(exact), gone.pass)).toBeNull();
  });

  it("C1d: a multi-market alias keeps one catalogue identity, but the moved origin still refuses; both markets together are ambiguous", () => {
    // CONSTRUCTED body edit: the O/U 2.5 Over row also names market 99000001 under `_market_ids`.
    const body = editedRow(parsed("liveMarkets"), 242143183, { _market_ids: [64353423, 99000001] }, "totals");
    const own = built({ markets: body, admitted: { ...LIVE, goals: [64353423] } });
    const alias = built({ markets: clone(body), admitted: { ...LIVE, goals: [99000001] } });
    expect(cardIds(own).goals).toEqual(["242143183"]);
    expect(cardIds(alias).goals).toEqual(["242143183"]);
    const hold = holdOf(openGoal("242143183", own.pass));
    const reopened = holdOf(openGoal("242143183", alias.pass));
    expect(hold.selection).toEqual(sel(LIVE_SCOPE, "64353423", "242143183"));
    expect(reopened.selection).toEqual(hold.selection);
    expect(reopened.origin).toEqual({ card: "goals", market: 99000001, id: "242143183" });
    expect(isOffered(hold.origin, alias.pass)).toBe(true);
    expect(isAdmitted(hold.origin, alias.pass)).toBe(false);
    expect(listed(alias, hold.selection)).toBe(true);
    expect(soccerCardShown(held(hold), alias.pass)).toBeNull();
    expect(soccerCardShown(held(hold), own.pass)?.selection).toEqual(hold.selection);
    const twice = built({ markets: clone(body), admitted: { ...LIVE, goals: [64353423, 99000001] } });
    expect(cardIds(twice).goals).toEqual(["242143183", "242143183"]);
    expect(openGoal("242143183", twice.pass)).toEqual(unresolved("goals"));
    expect(isAdmitted(hold.origin, twice.pass)).toBe(true);
    expect(resolveOrigin(hold.origin, twice.pass)).toEqual(hold.selection);
    expect(isOffered(hold.origin, twice.pass)).toBe(false);
    expect(soccerCardShown(held(hold), twice.pass)).toBeNull();
  });

  it("each card type: a hold refuses once the mounted card draws its id twice", () => {
    const live = built({ halves: "explicit" });
    const goal = holdOf(openGoal("242143183", live.pass));
    const goals = built({ markets: editedRow(parsed("liveMarkets"), 242143187, { contributor_outcome_ids: [242143183] }, "totals") });
    expect(cardIds(goals).goals).toEqual(["242143183", "242143183", "242765587"]);
    expect(isAdmitted(goal.origin, goals.pass)).toBe(true);
    expect(resolveOrigin(goal.origin, goals.pass)).toEqual(goal.selection);
    expect(isOffered(goal.origin, goals.pass)).toBe(false);
    expect(soccerCardShown(held(goal), goals.pass)).toBeNull();
    expect(openGoal("242143183", goals.pass)).toEqual(unresolved("goals"));

    const both = holdOf(openBoth(ref("242143189"), live.pass));
    const twoYes = built({ markets: editedRow(parsed("liveMarkets"), 242143190, { contributor_outcome_ids: [242143189] }) });
    expect(cardIds(twoYes).both).toEqual(["242143189", "242143189"]);
    expect(isAdmitted(both.origin, twoYes.pass)).toBe(true);
    expect(isOffered(both.origin, twoYes.pass)).toBe(false);
    expect(soccerCardShown(held(both), twoYes.pass)).toBeNull();

    const first = holdOf(openFirst("244237963", live.pass));
    const twoFirst = built({ markets: editedRow(parsed("liveMarkets"), 244237965, { contributor_outcome_ids: [244237963] }) });
    expect(cardIds(twoFirst).first).toEqual(["244237963", "244237963", "244237964"]);
    expect(isOffered(first.origin, twoFirst.pass)).toBe(false);
    expect(soccerCardShown(held(first), twoFirst.pass)).toBeNull();
    expect(openFirst("244237964", twoFirst.pass).kind).toBe("held");

    const half = holdOf(openHalf("63178219:242338171", live.pass));
    const extra: SoccerMatchAdmission = { ...LIVE, halves: [...LIVE.halves, { marketId: 63178219, periodId: "extra", label: "Extra" }] }; // CONSTRUCTED
    const twoCells = built({ admitted: extra, halves: "explicit" });
    expect((cardIds(twoCells).halves ?? []).filter((id) => id === "63178219:242338171")).toHaveLength(2);
    expect(isAdmitted(half.origin, twoCells.pass)).toBe(true);
    expect(resolveOrigin(half.origin, twoCells.pass)).toEqual(half.selection);
    expect(isOffered(half.origin, twoCells.pass)).toBe(false);
    expect(soccerCardShown(held(half), twoCells.pass)).toBeNull();

    const exact = holdOf(openExact("full", "238846934", hull().pass));
    const full = C.hullDescriptor.scopes.find((s) => s.id === "full")!;
    const zeroZero = full.originals.find((o) => JSON.stringify(o.outcomeIds) === "[238846934]")!;
    const listedTwice: SoccerMatchAdmission = {
      ...HULL_BEFORE,
      exactScore: {
        ...C.hullDescriptor,
        scopes: C.hullDescriptor.scopes.map((s) => (s.id === "full" ? { ...s, originals: [...s.originals, zeroZero] } : s)),
      },
    }; // CONSTRUCTED
    const twoScores = hull({ admitted: listedTwice });
    expect(((cardIds(twoScores).exact ?? []).find((s) => s.id === "full")?.originals ?? []).filter((id) => id === "238846934")).toHaveLength(2);
    expect(isAdmitted(exact.origin, twoScores.pass)).toBe(true);
    expect(resolveOrigin(exact.origin, twoScores.pass)).toEqual(exact.selection);
    expect(isOffered(exact.origin, twoScores.pass)).toBe(false);
    expect(soccerCardShown(held(exact), twoScores.pass)).toBeNull();
    expect(openExact("full", "237459055", twoScores.pass).kind).toBe("held");
  });
});

// ─── Refusals ──────────────────────────────────────────────────────────────

describe("refusals: nothing nearby is ever substituted", () => {
  it("a phase change never carries a held original into the next catalogue (RETAINED live → final)", () => {
    const live = built({ halves: "explicit" });
    const after = finalPage();
    for (const hold of [
      holdOf(openBoth(ref("242143189"), live.pass)),
      holdOf(openFirst("244237963", live.pass)),
      holdOf(openHalf("63178219:242338171", live.pass)),
    ]) {
      expect(isOffered(hold.origin, after.pass)).toBe(true);
      expect(isAdmitted(hold.origin, after.pass)).toBe(true);
      expect(resolveOrigin(hold.origin, after.pass)?.scope).toBe(FINAL_SCOPE);
      expect(soccerCardShown(held(hold), after.pass)).toBeNull();
    }
  });

  it("a re-sourced or withdrawn row refuses the held original; a fresh tap opens only the new identity", () => {
    const live = built();
    const hold = holdOf(openBoth(ref("242143189"), live.pass));
    const resourced = built({ markets: editedRow(parsed("liveMarkets"), 242143189, { source: "kalshi" }) }); // CONSTRUCTED
    expect(soccerCardShown(held(hold), resourced.pass)).toBeNull();
    expect(holdOf(openBoth(ref("242143189"), resourced.pass)).selection).toEqual(sel(LIVE_SCOPE, "64353426", "242143189", "kalshi"));
    const withdrawn = built({ markets: removingRow(parsed("liveMarkets"), 242143189) }); // CONSTRUCTED
    expect(cardIds(withdrawn).both).toEqual(["242143190"]);
    expect(isOffered(hold.origin, withdrawn.pass)).toBe(false);
    expect(soccerCardShown(held(hold), withdrawn.pass)).toBeNull();
    expect(openBoth(ref("242143189"), withdrawn.pass)).toEqual(unresolved("both"));
    expect(openBoth(ref("242143190"), withdrawn.pass).kind).toBe("held");
  });

  it("duplicated ids are ambiguous, and a card whose every drawn id is unresolvable offers no Details", () => {
    const live = built();
    const hold = holdOf(openBoth(ref("242143189"), live.pass));
    const duplicated = built({ markets: editedRow(parsed("liveMarkets"), 242143190, { contributor_outcome_ids: [242143189] }) });
    expect(openBoth(ref("242143189"), duplicated.pass)).toEqual(unresolved("both"));
    expect(soccerCardShown(held(hold), duplicated.pass)).toBeNull();
    expect(soccerCardOffersDetails("both", duplicated.pass)).toBe(false);
    expect(soccerCardOffersDetails("goals", duplicated.pass)).toBe(true);
    let body = parsed("liveMarkets");
    for (const outcome of [244237965, 244237964]) body = editedRow(body, outcome, { contributor_outcome_ids: [244237963] });
    const first = built({ markets: body });
    expect(cardIds(first).first).toEqual(["244237963", "244237963", "244237963"]);
    expect(openFirst("244237963", first.pass)).toEqual(unresolved("first"));
    expect(soccerCardOffersDetails("first", first.pass)).toBe(false);
  });

  it("contributor-set ambiguity: one contributor set served twice refuses; the same set in another order is another opaque id, never a substitute", () => {
    const live = built();
    const hold = holdOf(openBoth(ref("242143189"), live.pass));
    // CONSTRUCTED: both outcomes re-served naming the SAME two contributors, in the same order.
    let same = editedRow(parsed("liveMarkets"), 242143189, { contributor_outcome_ids: [242143189, 242143190] });
    same = editedRow(same, 242143190, { contributor_outcome_ids: [242143189, 242143190] });
    const twice = built({ markets: same });
    expect(cardIds(twice).both).toEqual(["242143189+242143190", "242143189+242143190"]);
    expect(openBoth(ref("242143189+242143190"), twice.pass)).toEqual(unresolved("both"));
    expect(soccerCardShown(held(hold), twice.pass)).toBeNull();
    // CONSTRUCTED: the same set in another order — each id opens only its own row.
    let order = editedRow(parsed("liveMarkets"), 242143189, { contributor_outcome_ids: [242143189, 242143190] });
    order = editedRow(order, 242143190, { contributor_outcome_ids: [242143190, 242143189] });
    const reordered = built({ markets: order });
    const a = holdOf(openBoth(ref("242143189+242143190"), reordered.pass));
    const b = holdOf(openBoth(ref("242143190+242143189"), reordered.pass));
    expect(a.selection.identity.side).toBe("242143189+242143190");
    expect(b.selection.identity.side).toBe("242143190+242143189");
    expect(soccerCardShown(held(hold), reordered.pass)).toBeNull();
  });

  it("duplicate catalogue identities refuse (CONSTRUCTED catalogue listing one original twice)", () => {
    const live = built();
    const hold = holdOf(openFirst("244237963", live.pass));
    const twin = live.page.originals.originals.find((o) => o.identity.side === "244237963")!;
    const page = { ...live.page, originals: { ...live.page.originals, originals: [...live.page.originals.originals, twin] } };
    const pass = buildSoccerCardPass({ event: live.event, gameMarkets: live.markets, admission: LIVE, nowMs: LIVE_NOW, page });
    expect(pass.consistent).toBe(true);
    expect(openFirst("244237963", pass)).toEqual(unresolved("first"));
    expect(soccerCardShown(held(hold), pass)).toBeNull();
    expect(openFirst("244237964", pass).kind).toBe("held");
  });

  it("native's rule: an identical origin named twice counts once; two different origins are ambiguous", () => {
    const live = built();
    const a = { card: "goals" as const, market: 64353423, id: "242143183" };
    const b = { card: "goals" as const, market: 64353425, id: "242143187" };
    expect(soccerCardOpened("goals", [a, { ...a }], live.pass)).toEqual(
      held({ origin: a, selection: sel(LIVE_SCOPE, "64353423", "242143183") }),
    );
    expect(soccerCardOpened("goals", [a, b], live.pass)).toEqual(unresolved("goals"));
    expect(soccerCardOpened("goals", [], live.pass)).toEqual(unresolved("goals"));
  });

  it("foreign refs, descriptors, unknown ids and labels never resolve", () => {
    const live = built();
    expect(openBoth(ref("242143189", 15311089), live.pass)).toEqual(unresolved("both"));
    expect(openBoth(ref("242143189", 15325054, 64353427), live.pass)).toEqual(unresolved("both"));
    expect(openBoth(ref("Yes"), live.pass)).toEqual(unresolved("both"));
    expect(openGoal("999", live.pass)).toEqual(unresolved("goals"));
    expect(openFirst("Real Valladolid CF", live.pass)).toEqual(unresolved("first"));
    expect(openHalf("63178219:242338171", live.pass)).toEqual(unresolved("halves")); // not mounted here
    expect(openExact("full", "238846934", live.pass)).toEqual(unresolved("exact"));
    const before = hull();
    expect(openExact("full", "Hull City AFC 0 - 0 Everton FC", before.pass)).toEqual(unresolved("exact"));
    expect(openExact("missing", "238846934", before.pass)).toEqual(unresolved("exact"));
    const foreign = hull({ admitted: { ...HULL_BEFORE, exactScore: { ...C.hullDescriptor, eventId: 15325054 } } }); // CONSTRUCTED
    expect(cardIds(foreign).exact).toBeNull();
    expect(foreign.pass.descriptor).toBeNull();
    expect(openExact("full", "238846934", foreign.pass)).toEqual(unresolved("exact"));
    expect(soccerCardOffersDetails("exact", foreign.pass)).toBe(false);
  });

  it("an unresolved tap stays unresolved on every later pass, even one where the id resolves", () => {
    const live = built();
    expect(openBoth(ref("242143189"), live.pass).kind).toBe("held");
    expect(soccerCardShown(unresolved("both"), live.pass)).toBeNull();
    const withdrawn = built({ markets: removingRow(parsed("liveMarkets"), 242143189) }); // CONSTRUCTED
    const tapped = openBoth(ref("242143189"), withdrawn.pass);
    expect(tapped).toEqual(unresolved("both"));
    expect(soccerCardShown(tapped, built().pass)).toBeNull();
  });
});

// ─── The per-pass index ────────────────────────────────────────────────────

describe("each pass builds its index once and keeps every duplicate", () => {
  it("holds the legs of exactly the admitted markets, the half cells, and every served row by identity side", () => {
    const live = built({ halves: "explicit" });
    expect(new Set(live.pass.legsByMarket.keys())).toEqual(new Set([64353423, 64353425, 64536538, 64353426, 63178217, 63178219, 63178218]));
    expect((live.pass.legsByMarket.get(64353426) ?? []).map((leg) => leg.id)).toEqual(["242143190", "242143189"]);
    expect(live.pass.legsByMarket.get(63178228)).toBeUndefined();
    expect(live.pass.halfCells.map((cells) => cells.map((c) => c.id))).toEqual([
      ["63178219:242338171", "63178219:242338172", "63178219:242338170"],
      ["63178218:246041831", "63178218:245875499", "63178218:245681743"],
    ]);
    expect((live.pass.servedBySide.get("242143189") ?? []).map((s) => s.identity)).toEqual([
      { source: "polymarket", market: "64353426", side: "242143189" },
    ]);
    const duplicated = built({ markets: editedRow(parsed("liveMarkets"), 242143190, { contributor_outcome_ids: [242143189] }) });
    expect(duplicated.pass.servedBySide.get("242143189")).toHaveLength(2);
    expect((duplicated.pass.legsByMarket.get(64353426) ?? []).map((leg) => leg.id)).toEqual(["242143189", "242143189"]);
    const none = built({ admitted: { goals: [], both: null, first: null, halves: [], ownClockGoals: [], exactScore: null } });
    expect(none.pass.legsByMarket.size).toBe(0);
    expect(none.pass.servedBySide.size).toBe(0);
    expect(soccerCardOffersDetails("goals", none.pass)).toBe(false);
    const resourced = built({ markets: editedRow(parsed("liveMarkets"), 242143189, { source: "kalshi" }) });
    expect((resourced.pass.servedBySide.get("242143189") ?? []).map((s) => s.identity.source)).toEqual(["kalshi"]);
  });

  it("PERFORMANCE: after a pass is built, hundreds of offers, opens and revalidations read the markets body zero more times", () => {
    // CONSTRUCTED instrument: every served array of the body is a counting proxy.
    let reads = 0;
    const body = parsed("liveMarkets");
    for (const key of ["totals", "spreads", "team_totals", "period_markets", "player_props", "other"]) {
      if (!Array.isArray(body[key])) continue;
      body[key] = new Proxy(body[key] as unknown[], {
        get(target, prop, receiver) {
          reads += 1;
          return Reflect.get(target, prop, receiver);
        },
      });
    }
    const event = parsed("liveDetail") as unknown as EventDetailResponse;
    const markets = body as unknown as GameMarketsResponse;
    const page = buildSoccerMatch({
      event,
      history: parsed("liveHistory") as unknown as EventHistoryResponse,
      gameMarkets: markets,
      admitted: LIVE,
      halvesAdmission: "explicit",
      host: { nowMs: LIVE_NOW, hero: null, probabilityObservedAt: null },
    });
    reads = 0;
    const pass = buildSoccerCardPass({ event, gameMarkets: markets, admission: LIVE, nowMs: LIVE_NOW, page });
    const buildReads = reads;
    expect(buildReads).toBeGreaterThan(0);
    reads = 0;
    let resolved = 0;
    for (let i = 0; i < 100; i += 1) {
      for (const card of ["goals", "both", "first", "halves", "exact", "history"] as const) soccerCardOffersDetails(card, pass);
      for (const id of ["242143183", "242143187", "242765587"]) resolved += soccerCardShown(openGoal(id, pass), pass) ? 1 : 0;
      for (const id of ["242143190", "242143189"]) resolved += soccerCardShown(openBoth(ref(id), pass), pass) ? 1 : 0;
      for (const id of ["244237963", "244237965", "244237964"]) resolved += soccerCardShown(openFirst(id, pass), pass) ? 1 : 0;
      resolved += soccerCardShown(openHalf("63178219:242338171", pass), pass) ? 1 : 0;
    }
    expect(resolved).toBe(900);
    expect(reads).toBe(0);
    // No cross-pass memo: a second pass reads its body again, exactly as much as the first.
    reads = 0;
    buildSoccerCardPass({ event, gameMarkets: markets, admission: LIVE, nowMs: LIVE_NOW, page });
    expect(reads).toBe(buildReads);
  });

  it("recreates no identity, truth, settlement, price or clock logic: the bridge reads none of those row fields", () => {
    const src = fs
      .readFileSync(path.resolve(__dirname, "../../lib/eventPage10868/soccerCardOriginals.ts"), "utf8")
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/^\s*\/\/.*$/gm, "");
    for (const field of [
      "contributor_outcome_ids",
      "_market_id",
      "market_name",
      "outcome_name",
      "probability",
      "observed_at",
      "is_winner",
      "resolution_source",
      "formatProbabilityPercent",
      "clockWords",
    ]) {
      expect({ field, read: src.includes(field) }).toEqual({ field, read: false });
    }
    expect(src).toContain("soccerOriginalIdentity(match)");
  });
});
