/**
 * #8028 — the two sides of a golf cup, folded to one spelling and given a colour.
 *
 * ═══ THE DEFECT ═══
 *
 * `/categories/golf` at 390px, 2026-09-22: BOTH live cup cards drew their
 * probability bar as a single undifferentiated grey block.
 *
 *     Presidents Cup   Team USA 81.5%  v  Team World 14.5%
 *     Ryder Cup        Team Europe 53.5%  v  Team USA 40.0%
 *
 * Read off the live DOM (`tools/cup-bar-colours-8028.mjs`), all four segments:
 *
 *     rgb(107, 114, 128) [bg-text-secondary]  ×4        <- one colour, two teams
 *
 * `CupCard` keyed its colour map on `teamA.name.toLowerCase()`, and the map's
 * keys are bare side names — `"usa"`, `"europe"`, `"international"`. Every side
 * a venue actually serves carries the `"Team "` prefix, so NOTHING matched and
 * both sides took the identical fallback. The Ryder Cup case is the worse read
 * of the two: 53.5 against 40.0, a near coin-flip, painted as one 93.5% bar.
 *
 * ═══ WHY A SHARED FOLDING AND NOT SIX MORE KEYS ═══
 *
 * Adding `"team usa"` and `"team world"` to the map would have fixed the two
 * cards on the page today and left the next spelling to fail the same way —
 * `"U.S.A."`, `"Great Britain & Ireland"` v `"GB and I"`, `"Rest of the World"`.
 * The vocabulary is not this component's to invent: `backend/app/utils/
 * golf_event_format.py` already owns it as `TEAM_SIDE_NAMES`, and it is the
 * predicate that decides which h2h matchup gets promoted onto this very card.
 *
 * So this module is the frontend twin of that file's `normalize_team_side_name`
 * — same folding, same vocabulary — and `cupTeamSidesStayInSyncWithTheBackend
 * 8028.test.ts` reads the Python source and fails if a side is added there and
 * not coloured here. A copied list that can drift silently would be the same
 * bug one release later.
 *
 * ═══ THE DISTINCTNESS RULE ═══
 *
 * A colour map cannot be complete: the day a cup names a side this file has
 * never heard of, both sides fall back and the bar is one grey block again —
 * the exact defect, returned. So the fallback is a PAIR of distinct neutrals
 * rather than one colour used twice, and `resolveCupSideColors` guarantees the
 * two segments never paint the same value. Neutral on purpose: an unknown side
 * gets a readable split, not an invented team identity.
 */

/** The four side identities a cup can have, and the palette each one paints. */
export interface CupSideColors {
  /** The side's name, as text. */
  text: string;
  /** The side's segment of the probability bar. */
  bar: string;
}

const USA: CupSideColors = { text: "text-blue-800", bar: "bg-blue-500" };
const EUROPE: CupSideColors = { text: "text-amber-800", bar: "bg-amber-500" };
const INTERNATIONAL: CupSideColors = { text: "text-emerald-800", bar: "bg-emerald-500" };
const GB_AND_I: CupSideColors = { text: "text-red-800", bar: "bg-red-500" };

/**
 * An unknown side keeps the body text colour — a name this file does not
 * recognise gets a readable bar, never a borrowed team's identity.
 */
const UNKNOWN_PRIMARY: CupSideColors = {
  text: "text-text-primary",
  bar: "bg-text-secondary",
};

/**
 * The SECOND unknown side. Differs from `UNKNOWN_PRIMARY` in the bar alone
 * (`--text-muted` #9CA3AF against `--text-secondary` #6B7280), which is the
 * whole job: two unknown sides still show a reader where the split falls.
 */
const UNKNOWN_SECONDARY: CupSideColors = {
  text: "text-text-primary",
  bar: "bg-text-muted",
};

/**
 * Every member of the backend's `TEAM_SIDE_NAMES`, in that file's folded
 * spelling, mapped to the side it names.
 *
 * Keys are the OUTPUT of `normalizeCupSideName`, so `"U.S.A."`, `"Team USA"`
 * and `"usa"` all arrive here as `"usa"`. Adding a name to the backend set
 * without adding it here is what the sync test catches.
 */
const SIDE_COLORS: Readonly<Record<string, CupSideColors>> = {
  // Presidents Cup, Ryder Cup, Solheim Cup, Walker Cup — the American side.
  usa: USA,
  us: USA,
  "united states": USA,
  america: USA,
  // Presidents Cup — Kalshi writes "Team World"; the tour says "International".
  world: INTERNATIONAL,
  international: INTERNATIONAL,
  "rest of the world": INTERNATIONAL,
  // Ryder Cup and Solheim Cup.
  europe: EUROPE,
  // Walker Cup.
  "great britain and ireland": GB_AND_I,
  "gb and i": GB_AND_I,
};

/** Strips the optional "Team " that every venue prefixes its sides with. */
const TEAM_SIDE_PREFIX_RE = /^team\s+/i;

/**
 * Fold a served side name to the spelling `SIDE_COLORS` is keyed in.
 *
 * The twin of `golf_event_format.normalize_team_side_name`: drops the optional
 * `"Team "` prefix, drops periods (`U.S.A.` -> `usa`), spells `&`, and collapses
 * whitespace. Returns `""` for an absent name, which is not a key, so a missing
 * name can never borrow a team's colour.
 */
export function normalizeCupSideName(name: string | null | undefined): string {
  if (!name) return "";
  const folded = name.trim().toLowerCase().replace(/\./g, "").replace(/&/g, " and ");
  return folded.replace(TEAM_SIDE_PREFIX_RE, "").replace(/\s+/g, " ").trim();
}

/**
 * The palette a single side name resolves to, or `null` when this file does not
 * recognise it.
 *
 * Exported for the backend-sync test, which asks the question one name at a
 * time. Rendering never uses it: a card must resolve its two sides TOGETHER
 * (see below), because the property #8028 is about belongs to the pair.
 */
export function cupSideColorFor(name: string | null | undefined): CupSideColors | null {
  return SIDE_COLORS[normalizeCupSideName(name)] ?? null;
}

/**
 * The palettes for a cup's two sides, GUARANTEED to paint different bars.
 *
 * Taken as a pair rather than one side at a time because the property that
 * matters is a property of the pair: #8028 is not "USA is the wrong colour",
 * it is "both segments are the same colour, so there is no visible split".
 * Resolving each side alone cannot state that, which is how the defect lived
 * behind a map that was individually correct for every key it had.
 *
 * Both unknown, or two names that fold to one side, fall to the two distinct
 * neutrals.
 */
export function resolveCupSideColors(
  nameA: string | null | undefined,
  nameB: string | null | undefined,
): [CupSideColors, CupSideColors] {
  const a = SIDE_COLORS[normalizeCupSideName(nameA)];
  const b = SIDE_COLORS[normalizeCupSideName(nameB)];

  // Distinct known sides: the ordinary case, and the only one that paints team
  // colours at all.
  if (a && b && a.bar !== b.bar) return [a, b];

  // One side known, the other not: keep the known team's identity and give the
  // other the neutral whose bar cannot collide with it.
  if (a && !b) return [a, UNKNOWN_PRIMARY];
  if (!a && b) return [UNKNOWN_PRIMARY, b];

  // Neither known, or both fold to the same side (a data defect the backend's
  // `select_team_side_matchup` refuses, guarded here because this component
  // does not go through it). Two neutrals, so the split is still visible.
  return [UNKNOWN_PRIMARY, UNKNOWN_SECONDARY];
}
