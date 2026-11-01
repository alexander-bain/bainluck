/**
 * #10868 — THE SOCCER MATCH SCREEN (web): A STORY CARD'S DETAILS OPEN THAT
 * ROW'S EXACT ORIGINAL.
 *
 * PILLARS: FORMATTING / TRUTH. SHIP: a soccer story's Details action opens that
 * exact original market and outcome, never a nearby or replacement prop — goal
 * milestones, both teams to score, first team to score, half by half and the
 * exact-score map each open the original market of the row they were tapped on.
 *
 * The web port of native `SoccerCardOriginalsAdapter10868` (blob d02a347a, 437
 * lines; line refs below as "N:"). It decides nothing the page does not already
 * decide:
 *
 *   - which market   the owner's typed story admission (`SoccerMatchAdmission`,
 *                    and its exact-score descriptor through `admittedDescriptor`)
 *                    — the same input that makes the card exist. A goal, both or
 *                    first origin names its admitted market; a half names the
 *                    owner's half (market AND period); an exact original names
 *                    the owner's scope (id, market AND period). Never a title, a
 *                    position or a label.
 *   - which row      `soccerLegs` of THAT market, kept by EXACT string equality
 *                    between the leg's id and the id the card handed back (the
 *                    card's id is that same leg id, made by the same builder). A
 *                    half cell's id is compared with `halfCellId` — the real cell
 *                    builder's id for that leg. No id is ever split or parsed.
 *   - which original the page's own served catalogue rows (`catalogueMatches`
 *                    over `ownHockeyMarkets`) whose served row IS that leg's row
 *                    and whose identity side is the leg's id, through the soccer
 *                    screen's own identity authority (`soccerOriginalIdentity`)
 *                    — called, never copied — accepted only as ONE served row
 *                    that the page's already-built catalogue lists exactly once
 *                    under its exact scope and full identity (native
 *                    `OriginalMarketDetails9483.original(in:selection:)`,
 *                    LadderOriginalProbabilityDetails9483.swift:433-439, which
 *                    refuses a blank, out-of-scope, withdrawn or duplicated one;
 *                    web has no exported twin, so `accepted` below states that
 *                    rule on the catalogue's identities, field by field).
 *   - what it holds  the typed ORIGIN with the exact selection resolved at the
 *                    tap (`SoccerCardHold`). Every pass shows that original only
 *                    while the origin is still offered (the mounted card draws
 *                    its id exactly once), still admitted (same market, period or
 *                    scope), still resolves to that SAME selection, and the
 *                    catalogue still accepts it. An old original can stay in All
 *                    props after the owner moves the card to another market, so
 *                    the selection alone is never the test. A replacement is
 *                    never adopted; an unresolved opening stays unresolved.
 *
 * PER-PASS INDEX (native 51-59, Design's performance correction):
 * `buildSoccerCardPass` runs ONCE per host pass from that pass's own inputs and
 * holds, immutable: the legs of every admitted market (one `soccerLegs` call per
 * market), the served catalogue rows by identity side (one `catalogueMatches`
 * call), each admitted half's legs with their builder cell ids, the admitted
 * descriptor, the catalogue's originals by identity, and the mounted cards' ids
 * with their counts. Offering, opening and revalidating only read it; none
 * rescans the markets or rebuilds the page per candidate. Nothing is cached
 * across passes, and every duplicate and ambiguity stays in the index so every
 * refusal still happens.
 *
 * SCOPE IS EXPLICIT. A pass serves one event and phase: its page must be built
 * for that event (`eventId`), in the phase `soccerMatchPhase` gives at the
 * pass's clock, with the stream scope `soccerStoryScope` gives and the
 * catalogue scope the soccer originals give for them; any mismatch makes a pass
 * that resolves nothing. Another event's markets read as none
 * (`ownHockeyMarkets`).
 *
 * Reads no probability, grade or clock and formats nothing; an original's
 * values and Details rows are the catalogue's, unchanged. Returns typed
 * resolutions only — no UI, callback or frozen-snapshot state (the later
 * Details host owns those). History is not a story original.
 *
 * PURE: no fetch, subscription, timer, cache or state.
 */

import type { GameMarketsResponse } from "@/lib/api";
import type { EventDetailResponse } from "@/lib/types";
import {
  admittedDescriptor,
  halfCellId,
  soccerLegs,
  soccerMatchPhase,
  soccerOriginalIdentity,
  soccerStoryScope,
  type SoccerExactDescriptor,
  type SoccerExactDescriptorScope,
  type SoccerLeg,
  type SoccerMatchAdmission,
  type SoccerMatchViewModel,
} from "./soccerMatch";
import {
  catalogueMatches,
  ownHockeyMarkets,
  type HockeyJourneyMarketRow,
  type HockeyJourneyOriginal,
  type HockeyJourneyOriginalIdentity,
  type HockeyJourneyOriginals,
} from "./hockeyJourneyProps";
import type { SoccerMatchPhase, SoccerStoryCard, SoccerStoryId } from "./soccerMatchTypes";

// ─── Types (native 180-219) ────────────────────────────────────────────────

/** A card that can offer Details, plus the history, which never does (native `Card`). */
export type SoccerDetailsCard = SoccerStoryId | "history";

/** The both-teams card's exact ref: this event, the admitted market, the outcome's own id (native `BothTeamsOutcomeRef10868`). */
export interface SoccerBothRef {
  eventId: number;
  marketId: number;
  outcomeId: string;
}

/** The typed card origin of one Details tap (native `Origin`, 181-204). Every id is opaque. */
export type SoccerCardOrigin =
  | { card: "goals"; market: number; id: string }
  | { card: "both"; market: number; ref: SoccerBothRef }
  | { card: "first"; market: number; id: string }
  | { card: "halves"; market: number; period: string; id: string }
  | { card: "exact"; scope: string; market: number; period: string | null; original: string };

/** An exact identity inside the exact catalogue scope it was chosen in (native `Details.Selection`). */
export interface SoccerOriginalSelection {
  scope: string;
  identity: HockeyJourneyOriginalIdentity;
}

/** The origin together with the exact selection it resolved to when tapped (native `Hold`, 207-210). */
export interface SoccerCardHold {
  origin: SoccerCardOrigin;
  selection: SoccerOriginalSelection;
}

/** What a card's Details tap opened (native `Opened`, 213-219): a hold, or unresolved for good. */
export type SoccerCardOpened = { kind: "held"; hold: SoccerCardHold } | { kind: "unresolved"; card: SoccerStoryId };

/** What a pass may show for a held opening: the selection and the CURRENT pass's own original for it. */
export interface SoccerCardShown {
  selection: SoccerOriginalSelection;
  original: HockeyJourneyOriginal;
}

/** What the host already holds on this pass, passed in unchanged. */
export interface SoccerCardPassInputs {
  event: EventDetailResponse;
  /** The page's own held `/game-markets` body (its `gameMarkets` memo); another event's reads as none. */
  gameMarkets: GameMarketsResponse | null | undefined;
  /** The owner's admission THIS pass's page was built from. */
  admission: SoccerMatchAdmission;
  /** The pass's clock (the page's `host.nowMs`). */
  nowMs: number;
  /** The view model built on this pass from these same inputs: its mounted stream and its originals catalogue. */
  page: SoccerMatchViewModel;
}

interface Served {
  row: HockeyJourneyMarketRow;
  identity: HockeyJourneyOriginalIdentity;
}

interface HalfCell {
  id: string;
  leg: SoccerLeg;
}

/** One mounted card's drawn ids, in drawn order, and how many times each is drawn. */
interface Drawn {
  ids: readonly string[];
  counts: ReadonlyMap<string, number>;
}

/** One render pass's immutable index (native `Pass`, 73-178). Built once per pass; never reused across passes. */
export interface SoccerCardPass {
  readonly event: EventDetailResponse;
  readonly phase: SoccerMatchPhase;
  readonly admission: SoccerMatchAdmission;
  /** False when the page is not this event's, phase's, stream's and catalogue's: then nothing resolves. */
  readonly consistent: boolean;
  /** The page's own catalogue, only on a consistent pass. */
  readonly catalogue: HockeyJourneyOriginals | null;
  /** The owner's exact-score descriptor, only for this event (`admittedDescriptor`). */
  readonly descriptor: SoccerExactDescriptor | null;
  /** `soccerLegs` of every admitted market, one call per market. */
  readonly legsByMarket: ReadonlyMap<number, readonly SoccerLeg[]>;
  /** The catalogue's served rows by their identity's opaque side, duplicates kept. */
  readonly servedBySide: ReadonlyMap<string, readonly Served[]>;
  /** Parallel to `admission.halves` (duplicates included): each half's legs with `halfCellId`. */
  readonly halfCells: readonly (readonly HalfCell[])[];
  /** The catalogue's originals by full identity, duplicates kept. */
  readonly catalogueByIdentity: ReadonlyMap<string, readonly HockeyJourneyOriginal[]>;
  /** The mounted cards' drawn ids (native `model`). A card not mounted exactly once draws nothing. */
  readonly drawn: {
    readonly goals: Drawn | null;
    readonly both: Drawn | null;
    readonly first: Drawn | null;
    readonly halves: Drawn | null;
    /** Scope id → how many mounted scopes carry it, and that scope's drawn original ids (first such scope). */
    readonly exact: ReadonlyMap<string, { count: number; originals: Drawn }> | null;
    /** The exact scopes in drawn order (for offering). */
    readonly exactOrder: readonly string[];
  };
}

// ─── Building the pass (native 114-154) ────────────────────────────────────

function drawnOf(ids: readonly string[]): Drawn {
  const counts = new Map<string, number>();
  for (const id of ids) counts.set(id, (counts.get(id) ?? 0) + 1);
  return Object.freeze({ ids: Object.freeze([...ids]), counts });
}

/** A full identity as one map key: the three fields as a JSON array — compared field by field, never parsed. */
function identityKey(identity: HockeyJourneyOriginalIdentity): string {
  return JSON.stringify([identity.source, identity.market, identity.side]);
}

/** The single mounted card with this id, or null (none, or more than one). */
function mounted<T extends SoccerStoryCard["id"]>(
  cards: readonly SoccerStoryCard[],
  id: T,
): Extract<SoccerStoryCard, { id: T }> | null {
  const found = cards.filter((card) => card.id === id);
  return found.length === 1 ? (found[0] as Extract<SoccerStoryCard, { id: T }>) : null;
}

/**
 * The catalogue scope the soccer originals give this event and phase (native
 * `SoccerOriginalsAdapter10868` scope, the native tests' "soccer:<id>:<phase>:originals"),
 * composed from the stream scope's exported owner. Pinned against
 * `buildSoccerMatch` by the bridge's tests.
 */
function catalogueScopeFor(eventId: number, phase: SoccerMatchPhase): string {
  return `${soccerStoryScope(eventId, phase)}:originals`;
}

export function buildSoccerCardPass({ event, gameMarkets, admission, nowMs, page }: SoccerCardPassInputs): SoccerCardPass {
  const phase = soccerMatchPhase(event, nowMs);
  const consistent =
    page.eventId === event.id &&
    page.phase === phase &&
    page.stories.scope === soccerStoryScope(event.id, phase) &&
    page.originals.scope === catalogueScopeFor(event.id, phase);
  const descriptor = consistent ? admittedDescriptor(admission, event) : null;
  const catalogue = consistent ? page.originals : null;
  const own = consistent ? ownHockeyMarkets(gameMarkets, event) : null;

  // Legs once per admitted market (goals, both, first, each half, each exact scope).
  const marketIds = new Set<number>(consistent ? admission.goals : []);
  if (consistent) {
    if (admission.both !== null) marketIds.add(admission.both);
    if (admission.first !== null) marketIds.add(admission.first);
    for (const half of admission.halves) marketIds.add(half.marketId);
    for (const scope of descriptor?.scopes ?? []) marketIds.add(scope.marketId);
  }
  const legsByMarket = new Map<number, readonly SoccerLeg[]>();
  for (const marketId of marketIds) legsByMarket.set(marketId, Object.freeze(soccerLegs(marketId, own)));

  // No admitted market or no catalogue: nothing can resolve, so the served rows are not read at all.
  const servedBySide = new Map<string, Served[]>();
  if (own && catalogue && marketIds.size > 0) {
    for (const match of catalogueMatches(own, event.status, nowMs)) {
      const identity = soccerOriginalIdentity(match);
      const bucket = servedBySide.get(identity.side);
      const served = { row: match.source.row, identity };
      if (bucket) bucket.push(served);
      else servedBySide.set(identity.side, [served]);
    }
  }

  const halfCells = consistent
    ? admission.halves.map((half) =>
        Object.freeze((legsByMarket.get(half.marketId) ?? []).map((leg) => ({ id: halfCellId(half, leg), leg }))),
      )
    : [];

  const catalogueByIdentity = new Map<string, HockeyJourneyOriginal[]>();
  for (const original of catalogue?.originals ?? []) {
    const key = identityKey(original.identity);
    const bucket = catalogueByIdentity.get(key);
    if (bucket) bucket.push(original);
    else catalogueByIdentity.set(key, [original]);
  }

  const cards = consistent ? page.stories.cards : [];
  const goals = mounted(cards, "goals");
  const both = mounted(cards, "both");
  const first = mounted(cards, "first");
  const halves = mounted(cards, "halves");
  const exactCard = mounted(cards, "exact");
  let exact: Map<string, { count: number; originals: Drawn }> | null = null;
  if (exactCard) {
    exact = new Map();
    for (const scope of exactCard.scopes) {
      const seen = exact.get(scope.id);
      if (seen) seen.count += 1;
      else exact.set(scope.id, { count: 1, originals: drawnOf(scope.originals.map((o) => o.id)) });
    }
  }

  return Object.freeze({
    event,
    phase,
    admission,
    consistent,
    catalogue,
    descriptor,
    legsByMarket,
    servedBySide: servedBySide as ReadonlyMap<string, readonly Served[]>,
    halfCells: Object.freeze(halfCells),
    catalogueByIdentity: catalogueByIdentity as ReadonlyMap<string, readonly HockeyJourneyOriginal[]>,
    drawn: Object.freeze({
      goals: goals ? drawnOf(goals.milestones.map((m) => m.id)) : null,
      both: both ? drawnOf(both.outcomes.map((o) => o.id)) : null,
      first: first ? drawnOf(first.rows.map((r) => r.id)) : null,
      halves: halves ? drawnOf(halves.series.flatMap((s) => s.cells.map((c) => c.id))) : null,
      exact,
      exactOrder: Object.freeze(exactCard ? exactCard.scopes.map((s) => s.id) : []),
    }),
  });
}

// ─── Pass lookups (native 156-177) ─────────────────────────────────────────

function legsOf(pass: SoccerCardPass, marketId: number): readonly SoccerLeg[] {
  return pass.legsByMarket.get(marketId) ?? [];
}

/** The identity of the ONE served row that IS the leg's row with the leg's id as its side; null for none or more. */
function identityOfLeg(pass: SoccerCardPass, leg: SoccerLeg): HockeyJourneyOriginalIdentity | null {
  const rows = (pass.servedBySide.get(leg.id) ?? []).filter((served) => served.row === leg.row);
  return rows.length === 1 ? rows[0].identity : null;
}

/** The indexes of the admitted halves naming exactly this market and period. */
function halvesNaming(pass: SoccerCardPass, market: number, period: string): number[] {
  return pass.admission.halves.flatMap((half, i) => (half.marketId === market && half.periodId === period ? [i] : []));
}

/** The descriptor's scopes with this exact id. */
function scopesNamed(pass: SoccerCardPass, id: string): SoccerExactDescriptorScope[] {
  return pass.descriptor?.scopes.filter((scope) => scope.id === id) ?? [];
}

const blank = (text: string): boolean => text.trim() === "";

export function sameIdentity(a: HockeyJourneyOriginalIdentity, b: HockeyJourneyOriginalIdentity): boolean {
  return a.source === b.source && a.market === b.market && a.side === b.side;
}

export function sameSelection(a: SoccerOriginalSelection | null, b: SoccerOriginalSelection | null): boolean {
  return a !== null && b !== null && a.scope === b.scope && sameIdentity(a.identity, b.identity);
}

/**
 * The catalogue's ONE original for a selection: a non-blank scope equal to the
 * catalogue's, a non-blank identity, listed exactly once — else null, never the
 * first, a default or a neighbour (native `original(in:selection:)`).
 */
function accepted(pass: SoccerCardPass, selection: SoccerOriginalSelection): HockeyJourneyOriginal | null {
  const catalogue = pass.catalogue;
  if (!catalogue || blank(selection.scope) || selection.scope !== catalogue.scope) return null;
  const { source, market, side } = selection.identity;
  if (blank(source) || blank(market) || blank(side)) return null;
  const found = pass.catalogueByIdentity.get(identityKey(selection.identity)) ?? [];
  return found.length === 1 && sameIdentity(found[0].identity, selection.identity) ? found[0] : null;
}

// ─── The three checks (native 286-359) ─────────────────────────────────────

const once = (drawn: Drawn | null, id: string): boolean => drawn?.counts.get(id) === 1;

/**
 * The card is mounted on this pass and draws the origin's own id EXACTLY ONCE
 * (native `isOffered`, 294-311). An id drawn twice is an ambiguous action:
 * offered for neither, and a held origin with that id refuses on this pass.
 * The web both card carries no event or market id of its own (its type is not
 * this bridge's to change): its event is the pass's (the stream scope is
 * checked when the pass is built) and its market is the admission's `both`,
 * from which `soccerBothCard` built it on this same pass.
 */
export function isOffered(origin: SoccerCardOrigin, pass: SoccerCardPass): boolean {
  if (!pass.consistent) return false;
  const { drawn } = pass;
  switch (origin.card) {
    case "goals":
      return once(drawn.goals, origin.id);
    case "both":
      return (
        drawn.both !== null &&
        origin.ref.eventId === pass.event.id &&
        origin.ref.marketId === pass.admission.both &&
        once(drawn.both, origin.ref.outcomeId)
      );
    case "first":
      return once(drawn.first, origin.id);
    case "halves":
      return once(drawn.halves, origin.id);
    case "exact": {
      const scope = drawn.exact?.get(origin.scope);
      return scope !== undefined && scope.count === 1 && once(scope.originals, origin.original);
    }
  }
}

/** The owner's admission on this pass still names the origin's market — and its period or scope — exactly (native 320-335). */
export function isAdmitted(origin: SoccerCardOrigin, pass: SoccerCardPass): boolean {
  if (!pass.consistent) return false;
  const { admission } = pass;
  switch (origin.card) {
    case "goals":
      return admission.goals.includes(origin.market);
    case "both":
      return (
        admission.both === origin.market &&
        origin.ref.marketId === origin.market &&
        origin.ref.eventId === pass.event.id
      );
    case "first":
      return admission.first === origin.market;
    case "halves":
      return halvesNaming(pass, origin.market, origin.period).length === 1;
    case "exact": {
      const scopes = scopesNamed(pass, origin.scope);
      return scopes.length === 1 && scopes[0].marketId === origin.market && scopes[0].periodId === origin.period;
    }
  }
}

/**
 * The origin's exact selection on this pass: its market's ONE leg carrying the
 * card's id, that leg's ONE served row's identity, accepted by the page's
 * catalogue (native `resolve`, 340-359).
 */
export function resolveOrigin(origin: SoccerCardOrigin, pass: SoccerCardPass): SoccerOriginalSelection | null {
  if (!pass.consistent) return null;
  let legs: readonly SoccerLeg[];
  switch (origin.card) {
    case "goals":
    case "first":
      legs = legsOf(pass, origin.market).filter((leg) => leg.id === origin.id);
      break;
    case "both":
      legs = legsOf(pass, origin.market).filter((leg) => leg.id === origin.ref.outcomeId);
      break;
    case "halves": {
      const indexes = halvesNaming(pass, origin.market, origin.period);
      if (indexes.length !== 1) return null;
      legs = (pass.halfCells[indexes[0]] ?? []).filter((cell) => cell.id === origin.id).map((cell) => cell.leg);
      break;
    }
    case "exact":
      legs = legsOf(pass, origin.market).filter((leg) => leg.id === origin.original);
      break;
  }
  const catalogue = pass.catalogue;
  if (legs.length !== 1 || !catalogue) return null;
  const identity = identityOfLeg(pass, legs[0]);
  if (!identity) return null;
  const selection = { scope: catalogue.scope, identity };
  return accepted(pass, selection) ? selection : null;
}

// ─── Opening (native 221-258) ──────────────────────────────────────────────

function sameOrigin(a: SoccerCardOrigin, b: SoccerCardOrigin): boolean {
  switch (a.card) {
    case "goals":
    case "first":
      return b.card === a.card && b.market === a.market && b.id === a.id;
    case "both":
      return (
        b.card === "both" &&
        b.market === a.market &&
        b.ref.eventId === a.ref.eventId &&
        b.ref.marketId === a.ref.marketId &&
        b.ref.outcomeId === a.ref.outcomeId
      );
    case "halves":
      return b.card === "halves" && b.market === a.market && b.period === a.period && b.id === a.id;
    case "exact":
      return (
        b.card === "exact" &&
        b.scope === a.scope &&
        b.market === a.market &&
        b.period === a.period &&
        b.original === a.original
      );
  }
}

/**
 * Exactly one candidate origin, with its exact selection, or unresolved. An
 * identical candidate named twice counts once; two different origins are
 * ambiguous (native `opened`, 249-258).
 */
export function soccerCardOpened(
  card: SoccerStoryId,
  candidates: readonly SoccerCardOrigin[],
  pass: SoccerCardPass,
): SoccerCardOpened {
  const holds: SoccerCardHold[] = [];
  for (const origin of candidates) {
    if (!isOffered(origin, pass) || !isAdmitted(origin, pass)) continue;
    const selection = resolveOrigin(origin, pass);
    if (!selection) continue;
    if (!holds.some((h) => sameOrigin(h.origin, origin) && sameSelection(h.selection, selection))) {
      holds.push({ origin, selection });
    }
  }
  return holds.length === 1 ? { kind: "held", hold: holds[0] } : { kind: "unresolved", card };
}

export function openGoal(id: string, pass: SoccerCardPass): SoccerCardOpened {
  return soccerCardOpened("goals", pass.admission.goals.map((market) => ({ card: "goals", market, id })), pass);
}

export function openBoth(ref: SoccerBothRef, pass: SoccerCardPass): SoccerCardOpened {
  const market = pass.admission.both;
  return soccerCardOpened("both", market === null ? [] : [{ card: "both", market, ref }], pass);
}

export function openFirst(id: string, pass: SoccerCardPass): SoccerCardOpened {
  const market = pass.admission.first;
  return soccerCardOpened("first", market === null ? [] : [{ card: "first", market, id }], pass);
}

export function openHalf(id: string, pass: SoccerCardPass): SoccerCardOpened {
  return soccerCardOpened(
    "halves",
    pass.admission.halves.map((half) => ({ card: "halves", market: half.marketId, period: half.periodId, id })),
    pass,
  );
}

export function openExact(scope: string, original: string, pass: SoccerCardPass): SoccerCardOpened {
  return soccerCardOpened(
    "exact",
    scopesNamed(pass, scope).map((s) => ({ card: "exact", scope, market: s.marketId, period: s.periodId, original })),
    pass,
  );
}

// ─── Revalidation (native 260-273) ─────────────────────────────────────────

/**
 * What the Details may show on this pass: the held selection — with THIS
 * pass's own original for it — only while its origin is still offered and
 * admitted, still resolves to that SAME selection, and the catalogue accepts
 * it. Otherwise null: the Details' own unavailable view, never a replacement.
 * An unresolved opening stays null on every pass.
 */
export function soccerCardShown(opened: SoccerCardOpened, pass: SoccerCardPass): SoccerCardShown | null {
  if (opened.kind !== "held") return null;
  const { origin, selection } = opened.hold;
  if (!isOffered(origin, pass) || !isAdmitted(origin, pass)) return null;
  if (!sameSelection(resolveOrigin(origin, pass), selection)) return null;
  const original = accepted(pass, selection);
  return original ? { selection, original } : null;
}

// ─── Offering (native 361-392) ─────────────────────────────────────────────

/**
 * A card offers Details only when at least one id it draws on this pass opens
 * an exact original — no control that would only ever say "unavailable". The
 * history never offers one.
 */
export function soccerCardOffersDetails(card: SoccerDetailsCard, pass: SoccerCardPass): boolean {
  const { drawn } = pass;
  const held = (opened: SoccerCardOpened) => opened.kind === "held";
  switch (card) {
    case "history":
      return false;
    case "goals":
      return (drawn.goals?.ids ?? []).some((id) => held(openGoal(id, pass)));
    case "both": {
      const market = pass.admission.both;
      if (drawn.both === null || market === null) return false;
      return drawn.both.ids.some((outcomeId) => held(openBoth({ eventId: pass.event.id, marketId: market, outcomeId }, pass)));
    }
    case "first":
      return (drawn.first?.ids ?? []).some((id) => held(openFirst(id, pass)));
    case "halves":
      return (drawn.halves?.ids ?? []).some((id) => held(openHalf(id, pass)));
    case "exact":
      return drawn.exactOrder.some((scope) =>
        (drawn.exact?.get(scope)?.originals.ids ?? []).some((original) => held(openExact(scope, original, pass))),
      );
  }
}
