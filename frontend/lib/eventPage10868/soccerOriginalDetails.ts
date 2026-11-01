/**
 * #10868 — a soccer story card's original Details, FROZEN at the tap (web).
 *
 * PILLARS: TRUTH / FORMATTING / DISCOVER. SHIP: a soccer fan opens an original
 * prop's exact Details, keeps that view stable during live updates, refreshes
 * only that same prop and returns to the same card.
 *
 * What a tap holds (Design's four-path admission, 0a47ebcf):
 *   - the IDENTITY TOKEN: the bridge's exact origin + selection
 *     (`SoccerCardHold`, soccerCardOriginals.ts), resolved at the tap. Every
 *     later status and Refresh decision reads ONLY the token, through the
 *     bridge's own revalidation (`soccerCardShown`: still offered, still
 *     admitted, still resolving the SAME full selection, still accepted).
 *   - the FROZEN PAYLOAD: an independent deep copy of THAT pass's catalogue
 *     original (`HockeyJourneyOriginal`), every built field kept and frozen.
 *     Rendering reads ONLY the payload; it never resolves anything.
 *
 * A tap that cannot get an exact accepted original in its own pass is
 * UNRESOLVED for good: no token and no payload, so nothing can later fill it or
 * make it refreshable. A fresh tap opens a new view.
 *
 * Background passes never touch the payload: only `refreshSoccerDetails`, an
 * explicit reader action, replaces it, and only while the status is
 * `current`. A withdrawn, duplicated, rebound or foreign origin keeps the
 * historical payload (`unavailable`); its return to availability makes Refresh
 * possible again, never an automatic replacement.
 *
 * The pass a surface may use is the one built for ITS model on this render:
 * `soccerCardPassFor` (the page boundary: this event, phase, stream scope and
 * this model's own originals catalogue object) and `soccerDetailsPass` (the
 * stream boundary: this stream scope). Anything else reads as no pass.
 *
 * PURE: no React, JSX, fetch, subscription, timer, clock, formatter, price,
 * baseline or grade rule, and no catalogue of its own. Values, words and
 * provenance are the catalogue's, copied unchanged.
 */

import type { HockeyJourneyOriginal } from "./hockeyJourneyProps";
import { soccerStoryScope, type SoccerMatchViewModel } from "./soccerMatch";
import {
  openBoth,
  openExact,
  openFirst,
  openGoal,
  openHalf,
  soccerCardShown,
  type SoccerCardHold,
  type SoccerCardOpened,
  type SoccerCardPass,
} from "./soccerCardOriginals";
import type { SoccerStoryId } from "./soccerMatchTypes";

/** Every nested field read-only, as the frozen payload is at run time. */
export type SoccerDeepReadonly<T> = T extends (infer U)[]
  ? ReadonlyArray<SoccerDeepReadonly<U>>
  : T extends object
    ? { readonly [K in keyof T]: SoccerDeepReadonly<T[K]> }
    : T;

export type SoccerFrozenOriginal = SoccerDeepReadonly<HockeyJourneyOriginal>;

/** Where the Details were opened from: the compact page card, or the full-size reader's card. */
export type SoccerDetailsEntry = "page" | "reader";

/** One opened Details view: a token with its frozen payload, or unresolved for good. */
export type SoccerOriginalDetails =
  | {
      kind: "snapshot";
      /** The stream's reading scope at the tap (`soccer:<event>:<phase>`). */
      scope: string;
      entry: SoccerDetailsEntry;
      card: SoccerStoryId;
      /** The identity token: compared on later passes, never rendered. */
      token: SoccerDeepReadonly<SoccerCardHold>;
      /** The payload: rendered, never compared or resolved. */
      frozen: SoccerFrozenOriginal;
    }
  | { kind: "unresolved"; scope: string; entry: SoccerDetailsEntry; card: SoccerStoryId };

/**
 * `current`: the token still resolves on this pass, so Refresh may run.
 * `unavailable`: a snapshot whose origin no longer resolves; the payload stays.
 * `unresolved`: no exact original was ever opened.
 */
export type SoccerDetailsStatus = "current" | "unavailable" | "unresolved";

/** The selected readout a Details control acts for, by the card's own opaque ids. */
export type SoccerSelectedOriginal =
  | { card: "goals" | "first" | "halves"; id: string }
  | { card: "both"; outcomeId: string }
  | { card: "exact"; scope: string; original: string };

/** An independent deep copy of plain built data, frozen at every level. */
export function soccerFrozenCopy<T>(value: T): SoccerDeepReadonly<T> {
  if (Array.isArray(value)) return Object.freeze(value.map((item) => soccerFrozenCopy(item))) as SoccerDeepReadonly<T>;
  if (value !== null && typeof value === "object") {
    const copy: Record<string, unknown> = {};
    for (const [key, item] of Object.entries(value as Record<string, unknown>)) copy[key] = soccerFrozenCopy(item);
    return Object.freeze(copy) as SoccerDeepReadonly<T>;
  }
  return value as SoccerDeepReadonly<T>;
}

/**
 * The page boundary: the owner's pass only when it was built for THIS model on
 * this render — a consistent pass for this event and phase, whose stream scope
 * is this model's, holding this model's own originals catalogue object. An
 * older pass, even an internally consistent one, reads as none.
 */
export function soccerCardPassFor(pass: SoccerCardPass | null | undefined, model: SoccerMatchViewModel): SoccerCardPass | null {
  if (!pass || !pass.consistent) return null;
  if (pass.event.id !== model.eventId || pass.phase !== model.phase) return null;
  if (model.stories.scope !== soccerStoryScope(pass.event.id, pass.phase)) return null;
  if (pass.catalogue === null || pass.catalogue !== model.originals) return null;
  return pass;
}

/** The stream boundary: a consistent pass serving exactly this stream scope, else none. */
export function soccerDetailsPass(pass: SoccerCardPass | null | undefined, scope: string): SoccerCardPass | null {
  if (!pass || !pass.consistent) return null;
  return soccerStoryScope(pass.event.id, pass.phase) === scope ? pass : null;
}

/** The bridge's opening for a card's selected readout on this pass (each family's own exact origin). */
export function soccerOpenSelected(selected: SoccerSelectedOriginal, pass: SoccerCardPass): SoccerCardOpened {
  switch (selected.card) {
    case "goals":
      return openGoal(selected.id, pass);
    case "first":
      return openFirst(selected.id, pass);
    case "halves":
      return openHalf(selected.id, pass);
    case "both": {
      const market = pass.admission.both;
      if (market === null) return { kind: "unresolved", card: "both" };
      return openBoth({ eventId: pass.event.id, marketId: market, outcomeId: selected.outcomeId }, pass);
    }
    case "exact":
      return openExact(selected.scope, selected.original, pass);
  }
}

const cardOf = (opened: SoccerCardOpened): SoccerStoryId => (opened.kind === "held" ? opened.hold.origin.card : opened.card);

/**
 * Opens Details from a tap: the token and a frozen copy of the original THIS
 * pass shows for it, or unresolved for good when the tap has no exact accepted
 * original in this pass (or the pass does not serve the scope).
 */
export function openSoccerDetails(
  scope: string,
  entry: SoccerDetailsEntry,
  opened: SoccerCardOpened,
  pass: SoccerCardPass | null,
): SoccerOriginalDetails {
  const card = cardOf(opened);
  const serving = soccerDetailsPass(pass, scope);
  if (opened.kind !== "held" || !serving) return { kind: "unresolved", scope, entry, card };
  const shown = soccerCardShown(opened, serving);
  if (!shown) return { kind: "unresolved", scope, entry, card };
  return {
    kind: "snapshot",
    scope,
    entry,
    card,
    token: soccerFrozenCopy(opened.hold),
    frozen: soccerFrozenCopy(shown.original),
  };
}

/** The bridge's revalidation of the token alone on this pass. */
function shownFor(details: Extract<SoccerOriginalDetails, { kind: "snapshot" }>, pass: SoccerCardPass | null) {
  const serving = soccerDetailsPass(pass, details.scope);
  if (!serving) return null;
  const hold = details.token as SoccerCardHold;
  return soccerCardShown({ kind: "held", hold }, serving);
}

/** What this pass allows for the opened view, from the token only. */
export function soccerDetailsStatus(details: SoccerOriginalDetails, pass: SoccerCardPass | null): SoccerDetailsStatus {
  if (details.kind === "unresolved") return "unresolved";
  return shownFor(details, pass) ? "current" : "unavailable";
}

/**
 * The explicit Refresh: a new frozen copy of THIS pass's original for the SAME
 * token, only while it is current. Otherwise the same object, unchanged.
 */
export function refreshSoccerDetails(details: SoccerOriginalDetails, pass: SoccerCardPass | null): SoccerOriginalDetails {
  if (details.kind === "unresolved") return details;
  const shown = shownFor(details, pass);
  if (!shown) return details;
  return { ...details, frozen: soccerFrozenCopy(shown.original) };
}
