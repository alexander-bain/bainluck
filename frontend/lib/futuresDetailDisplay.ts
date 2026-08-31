// #883 futures-detail blend-only redesign — pure display helpers.
//
// The detail page shows ONE blended number and a plain-language clarification of
// WHY the blend line moved (#871-style). This logic is extracted here so it can
// be unit-tested without rendering the heavy page (SWR/framer/charts), mirroring
// searchFamilyDisplay.ts. D1 binds: probabilities only, no odds, no source names.

export interface MovementLeader {
  name?: string | null;
  probability: number | null;
  opening_probability?: number | null;
  probability_change_24h?: number | null;
}

/**
 * #883 L2-49 (resolved edge state): the outcome the hero features. On a resolved
 * market that's the actual WINNER (is_winner === true), which can differ from the
 * highest-probability outcome — falling back to the leader if none is flagged.
 * On a live market it's just the leader.
 */
export function pickHeroOutcome<T extends { is_winner?: boolean | null }>(
  outcomes: readonly T[],
  leader: T | null,
  resolved: boolean,
): T | null {
  if (!resolved) return leader;
  return outcomes.find((o) => o.is_winner === true) ?? leader;
}

/** Generic binary-style outcome names that read better as "Yes" in a headline. */
export function isGenericOutcomeLabel(name: string | null | undefined): boolean {
  const n = (name || "").trim().toLowerCase();
  return n === "yes" || n === "no" || n === "" || n === "over" || n === "under";
}

/** Display label for the leader outcome — generic binaries become "Yes". */
export function leaderLabel(leader: MovementLeader | null): string | null {
  if (!leader) return null;
  return isGenericOutcomeLabel(leader.name) ? "Yes" : (leader.name as string);
}

/**
 * #883 L2-55: the <title>/SEO text for a futures-detail page. On a SETTLED market
 * the title is "<winner> won - <market>" — NO percentage (the last-traded % read
 * as a bug in the hero, and it was still leaking via metadata). Live markets keep
 * "<leader> <prob>% - <market>". Pure so it's unit-tested.
 */
export function futuresTitleText(opts: {
  marketName: string;
  isResolved: boolean;
  winnerName?: string | null;
  leaderName?: string | null;
  probabilityLabel?: string | null;
}): string {
  if (opts.isResolved && opts.winnerName) {
    return `${opts.winnerName} won - ${opts.marketName}`;
  }
  if (opts.leaderName && opts.probabilityLabel) {
    return `${opts.leaderName} ${opts.probabilityLabel} - ${opts.marketName}`;
  }
  return opts.marketName;
}

/**
 * The clarification that explains the blend line's movement. Deterministic,
 * blend-only (no per-source detail): prefer opening→current ("up X pts from
 * opening"), fall back to the 24h change, else null (nothing to say). Movements
 * under 1 point read as "roughly flat" rather than noisy decimals.
 */
export function movementExplanation(leader: MovementLeader | null): string | null {
  if (!leader) return null;
  const label = leaderLabel(leader);
  const cur = leader.probability;
  const open = leader.opening_probability;

  if (cur != null && open != null) {
    const delta = (cur - open) * 100;
    const mag = Math.abs(delta);
    if (mag >= 1) {
      return `${label} ${delta > 0 ? "up" : "down"} ${mag.toFixed(1)} pts from opening.`;
    }
    return `${label} roughly flat since opening.`;
  }

  const ch = leader.probability_change_24h;
  if (ch != null && Math.abs(ch * 100) >= 1) {
    const d = ch * 100;
    return `${label} ${d > 0 ? "up" : "down"} ${Math.abs(d).toFixed(1)} pts in the last 24h.`;
  }
  return null;
}

export type FuturesSortField = "probability" | "change" | "name";
export type FuturesSortDirection = "asc" | "desc";

export interface SortableOutcome {
  name: string;
  probability: number | null;
  probability_change_24h?: number | null;
}

/**
 * UX-P230 — the "All Outcomes" table's ordering.
 *
 * ONE CONVENTION, and it is the whole point of this function: **every comparator
 * below is written ASCENDING** (a before b when the result is negative), and the
 * direction flip at the bottom is the ONLY place that reverses. `desc` therefore
 * means "biggest first" for probability, "biggest gainer first" for change, and
 * Z→A for name.
 *
 * The detail page previously kept these comparators inline and authored two of
 * the three in reverse (`b - a`) while `name` used the normal convention — so the
 * shared inverter, written for `name`, flipped the other two a SECOND time. Under
 * the default `probability`/`desc` the table rendered ascending: on market 109441
 * the 27% leader the hero is entirely about was the LAST of eight rows, under a
 * pill reading "Probability ↓".
 *
 * Keeping it here rather than inline is not tidying: an inline switch can only be
 * exercised through the page's default state, which is exactly why five of the six
 * field×direction combinations had never been under test.
 */
export function sortFuturesOutcomes<T extends SortableOutcome>(
  outcomes: readonly T[],
  field: FuturesSortField,
  direction: FuturesSortDirection,
): T[] {
  return [...outcomes].sort((a, b) => {
    let comparison = 0;

    switch (field) {
      case "probability":
        comparison = (a.probability ?? 0) - (b.probability ?? 0);
        break;
      case "change": {
        // The signed change, never its magnitude: ascending puts the biggest
        // losers first, descending the biggest gainers.
        const aChange = a.probability_change_24h ?? 0;
        const bChange = b.probability_change_24h ?? 0;
        comparison = aChange - bChange;
        break;
      }
      case "name":
        comparison = a.name.localeCompare(b.name);
        break;
    }

    return direction === "asc" ? comparison : -comparison;
  });
}
