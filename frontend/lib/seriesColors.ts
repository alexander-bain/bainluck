/**
 * seriesColors — the single per-series (per-outcome/competitor) palette registry
 * (L2-157, census class E — the index/outcome-palette half; the source-color half
 * lives in sourceColors.ts / L2-155).
 *
 * These color CHART SERIES BY INDEX — the Nth competitor line in a field/race
 * chart, its legend swatch, and its leaderboard dot — NOT data sources. Before
 * this file, FIVE near-identical index palettes each hardcoded their own hexes
 * and drifted: `DEFAULT_COLORS`/`GOLD_COLORS`/`GREEN_COLORS` in FuturesChart and
 * two identical copies of `EVOLUTION_COLORS` (EvolutionView + EvolutionLeaderboard).
 * The generic index palette even disagreed with itself across surfaces (the field
 * kernel drew a blue-led rainbow while the evolution/race chart drew a crimson-led
 * one for the same "Nth competitor" role). This registry replaces all of them so
 * a line and its sidebar dot always match, and every field chart inherits one map.
 *
 * Canonicalization rule (NOT taste — same discipline as L2-155): where hexes
 * conflicted for the same role, the value used on the FLAGSHIP surface wins. The
 * flagship series surface is the shared FuturesChart field kernel (L2-149) — it
 * renders the event-page hero charts (RaceToTitle / WinnerEvolution / SettledPath)
 * and the most distinct surfaces — so its `DEFAULT_COLORS` become the canonical
 * SERIES_COLORS. The evolution/race chart adopts them (dropping its bespoke
 * crimson-led duplicate). No new colors were invented: SERIES_COLORS extends the
 * flagship's 8 with two hues already present in the old EVOLUTION palette
 * (`#92400e` brown, `#065f46` dark green) so a >8-competitor field keeps distinct
 * lines. GOLD/GREEN are distinct leader THEMES (no conflict) and keep their hexes.
 */

/**
 * Canonical index palette for competitor/outcome series (white-bg optimized).
 * Indices 0–7 are the flagship FuturesChart palette (unchanged); indices 8–9 add
 * headroom for many-competitor fields (e.g. a 10-golfer evolution board) using
 * hues that already existed in the old EVOLUTION_COLORS palette.
 */
export const SERIES_COLORS = [
  "#2563eb", // blue
  "#dc2626", // red
  "#16a34a", // green
  "#9333ea", // purple
  "#ea580c", // orange
  "#0891b2", // cyan
  "#be185d", // pink
  "#4f46e5", // indigo
  "#92400e", // brown  (headroom — reused from old EVOLUTION palette)
  "#065f46", // dark green (headroom — reused from old EVOLUTION palette)
];

/** Gold-leader theme: leader gold + descending grays. Used for a single-leader
 *  field where the frontrunner should read as "gold". Distinct role — kept as-is. */
export const SERIES_COLORS_GOLD = [
  "#D4AF37", // gold (leader)
  "#B8860B", // dark goldenrod
  "#6b7280", // gray-500
  "#9ca3af", // gray-400
  "#d1d5db", // gray-300
  "#6b7280",
  "#9ca3af",
  "#d1d5db",
];

/** Augusta-green leader theme (golf majors): Masters green + descending grays.
 *  Distinct role — kept as-is. */
export const SERIES_COLORS_GREEN = [
  "#006747", // Augusta green (leader)
  "#2d8659", // lighter green
  "#6b7280", // gray-500
  "#9ca3af", // gray-400
  "#d1d5db", // gray-300
  "#6b7280",
  "#9ca3af",
  "#d1d5db",
];

/** Eliminated-outcome line/dot color — a muted grey so a knocked-out contender
 *  stays visible for context without competing with the live field (L2-149). */
export const ELIMINATED_SERIES_COLOR = "#b5b9c3";

/** Combined-probability line color — the summed line reads as a dark neutral so
 *  it never masquerades as one of the contenders (L2-149). */
export const COMBINED_SERIES_COLOR = "#111827";

/**
 * #8095 — a series whose label is a US party name carries a colour meaning of its
 * own, and the index palette can contradict it: "Which party will win the U.S.
 * House?" sorted Republican first, so Republicans drew blue and Democrats red, and
 * a red line pinned at 91% read as the opposite result. A glanceable chart that
 * needs its legend to avoid inverting the answer is not glanceable.
 *
 * The match is on the WHOLE label, deliberately. "Democrats, 5+ pts" is a margin
 * rung, not the party, and "Liberal Democratic Party" / "Social Democratic Party"
 * are other countries' parties with their own colours — none of them match. No new
 * hexes: the two are the palette's own blue and red.
 */
const PARTY_SERIES_COLORS: ReadonlyArray<[RegExp, string]> = [
  [/^(?:the\s+)?(?:democrats?|democratic(?:\s+party)?)$/i, SERIES_COLORS[0]],
  [/^(?:the\s+)?(?:republicans?|republican\s+party|gop)$/i, SERIES_COLORS[1]],
];

/** The conventional colour for a series label, or null when it has none. */
export function conventionalSeriesColor(name: string): string | null {
  const label = name.trim();
  for (const [pattern, color] of PARTY_SERIES_COLORS) {
    if (pattern.test(label)) return color;
  }
  return null;
}

/**
 * Colour each series in order. With no conventional label present this is exactly
 * `palette[i % palette.length]`, so every chart without a party line is unchanged.
 * With one present, the party lines take their colour and the rest walk the
 * palette skipping the hues already taken, so no two lines share a colour.
 */
export function assignSeriesColors(
  names: readonly string[],
  palette: readonly string[],
): string[] {
  const conventional = names.map(conventionalSeriesColor);
  if (conventional.every((c) => c === null)) {
    return names.map((_, i) => palette[i % palette.length]);
  }
  const taken = new Set(conventional.filter((c): c is string => c !== null));
  const free = palette.filter((c) => !taken.has(c));
  const pool = free.length > 0 ? free : palette;
  let next = 0;
  return conventional.map((c) => c ?? pool[next++ % pool.length]);
}

/**
 * #10266 — a colour that belongs to the OUTCOME, not to its slot in the drawn
 * set, so a team keeps it when the reader changes range.
 *
 * Positional colouring changes a line's colour whenever the set around it
 * changes. On `/futures/231` the history response's order moved between 1M and
 * 1W, and on a sparse range a whole series can be missing: with Rams absent,
 * 49ers slid from slot 2 (green) to slot 1 (red).
 *
 * Here each outcome's colour is dealt from its rank in `order`, the caller's
 * fixed list of the board's outcomes (the futures page passes the market's own
 * outcome order), through `assignSeriesColors`, so party labels keep #8095's
 * colours. Ranks inside the palette are distinct, so the top outcomes never
 * move whatever subset is drawn. Two drawn lines can only collide when an
 * outcome ranks beyond the palette (a 30-team board); that one takes the first
 * colour no other drawn line holds, walking the drawn set in rank order, so the
 * lines on screen stay distinguishable. Outcomes `order` does not name are
 * treated the same way, after the named ones. `skip` (eliminated lines, which
 * draw grey) takes no colour.
 */
export function fixedOrderSeriesColors(
  drawn: readonly { outcome_id: number; skip?: boolean }[],
  order: readonly { id: number; name: string }[],
  palette: readonly string[],
): Map<number, string> {
  const base = assignSeriesColors(order.map((o) => o.name), palette);
  const rank = new Map<number, number>();
  const baseById = new Map<number, string>();
  order.forEach((o, i) => {
    if (rank.has(o.id)) return;
    rank.set(o.id, i);
    baseById.set(o.id, base[i]);
  });
  const ranked = drawn
    .filter((o) => !o.skip)
    .map((o, i) => ({ id: o.outcome_id, r: rank.get(o.outcome_id) ?? order.length + i }))
    .sort((a, b) => a.r - b.r);
  const used = new Set<string>();
  const out = new Map<number, string>();
  for (const { id } of ranked) {
    let colour = baseById.get(id);
    if (colour === undefined || used.has(colour)) {
      colour = palette.find((c) => !used.has(c)) ?? colour ?? palette[0];
    }
    used.add(colour);
    out.set(id, colour);
  }
  return out;
}
