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

/* ───────────────────────────────────────────────────────────────────────────
 * UX-P233 — EVERY NUMBER ON THIS PAGE STATES ITS BASELINE (board item 11).
 *
 * Alex, on /futures/109441: **"Very confusing."** Three numbers about Amazon, all
 * on one screen, none of them saying which window it covers:
 *
 *     hero pill        ↓ 71.5 pts        (no window stated at all)
 *     chart caption    "Amazon up 13.5 pts from opening."
 *     table row        Open: 14%   -71.5%   27%
 *
 * Unlabelled they do not merely under-inform, they look like a contradiction: a
 * hero saying "down 71.5" beside a caption saying "up 13.5" about the same outcome.
 *
 * 🔴 AND THE OBVIOUS LABEL IS THE ONE WE MAY NOT WRITE. The field is
 * `probability_change_24h`, so "in the last 24h" is the tempting caption — and the
 * payload disproves it. CAL-P159 (board item 12) proved all four writers store
 * `new − previous`, a PER-WRITE delta, which then FREEZES when a row stops being
 * written; -0.715 is Amazon's Aug-18 → Aug-28 step. Measured live 2026-08-31 18:51Z,
 * every outcome on that market carries `last_updated: 2026-08-28T20:50Z` — 2.9 days
 * old. Writing "24h" beside a number the same payload dates to three days ago is a
 * claim about the past the payload refutes (gotcha #53), and this board has blocked
 * on that class six times. So the label names what the field IS — the last recorded
 * move — and dates it from `last_updated`.
 *
 * These are pure and unit-tested; the arithmetic fix for the field itself is board
 * item 12's, in the calibration lane. Nothing here changes any number's VALUE.
 * ─────────────────────────────────────────────────────────────────────────── */

/** A price is "current" for a day; past that the page owes the reader an as-of. */
const AS_OF_AFTER_DAYS = 1;

/**
 * How stale a price is, in days, or `null` when we cannot tell. Never 0 for a
 * missing stamp — that would read as "fresh", which is absence dressed as a fact.
 * A stamp in the future clamps to 0 rather than going negative.
 */
export function priceAgeDays(
  lastUpdated: string | null | undefined,
  now: Date = new Date(),
): number | null {
  if (!lastUpdated) return null;
  const then = new Date(lastUpdated);
  if (Number.isNaN(then.getTime())) return null;
  return Math.max(0, (now.getTime() - then.getTime()) / 86_400_000);
}

/* ───────────────────────────────────────────────────────────────────────────
 * UX-P260 (#2624) — A DATE ON AN INSTANT BELONGS TO THE READER, NOT TO UTC.
 *
 * Alex, on `/futures/1` at 20:12 PT on **Sep 1**: the hero pill read
 * **"last move · Sep 2"**. The site was dating a price move TOMORROW. The same
 * page contradicted itself 400px lower — the Probability Trend axis ended at
 * "Sep 1 5 PM", the same instant, formatted correctly.
 *
 * This function used to pin `timeZone: "UTC"`, and its reasoning is preserved
 * here because it was not silly:
 *
 *     "A label built from the machine's local zone is a claim whose answer
 *      depends on where it renders, and a guard for it is a test whose answer
 *      depends on where it runs (the trap CERT-534 named one lane over)."
 *
 * The second half of that is a real hazard and this repo is still paying it —
 * #2462 leaves `discoverTournamentCardTiming` five-red on clean master for
 * anyone outside UTC. But the cure was worse than the disease: it bought a
 * deterministic GUARD by making the SHIPPED LABEL wrong for every reader west
 * of Greenwich, every evening. For US users that is every move after 17:00 PT.
 *
 * 🔵 THE DISTINCTION THAT DECIDES IT, and it is the whole fix: **a calendar date
 * is not an instant.** A tournament runs Sep 3–6 no matter where you stand, so
 * `gameTimeLabel.ts`, `UpcomingTournaments.tsx`, `NextEditionStrip.tsx` and the
 * golf/playoff pages are RIGHT to pin UTC on their date-only values — pinning is
 * what stops "2026-09-05" sliding to Sep 4 in Los Angeles. A price move is the
 * opposite: it happened at one moment, and the only honest name for that moment's
 * day is the day it was where the reader is standing. Those seven sites are
 * deliberately untouched; this one was the only one formatting an instant.
 *
 * So the zone becomes a PARAMETER instead of a constant. That answers the old
 * comment's objection rather than overriding it: the guards below pass an
 * explicit zone and are therefore deterministic wherever they run, while the
 * page passes nothing and gets the reader's own clock — the same thing
 * `FuturesChart` has always done one component away (`FuturesChart.tsx:300`
 * formats with no `timeZone`, which is why the axis was already right).
 *
 * Safe to render locally on this page specifically: the futures detail page
 * takes its payload from `useSWR` behind an early return, so the label is never
 * in the server HTML and there is no hydration boundary to mismatch across. The
 * chart is the standing proof — it has formatted local here for as long as it
 * has existed.
 *
 * Nothing here changes any number's VALUE, or the arithmetic in `priceAgeDays`,
 * which compares epoch milliseconds and never had a zone to get wrong.
 * ─────────────────────────────────────────────────────────────────────────── */

/**
 * "Aug 28" — the day the given INSTANT fell on, in `timeZone` when one is
 * supplied, otherwise in the zone the code is running in (in the browser: the
 * reader's own). Guards MUST pass an explicit zone; the app deliberately does not.
 */
function instantDayLabel(when: Date, timeZone?: string): string {
  return when.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    ...(timeZone ? { timeZone } : {}),
  });
}

/**
 * The window label for a movement figure: **"last move · Aug 28"**, or plain
 * "last move" when the payload carries no stamp to date it with.
 *
 * The noun does NOT change with the clock. A per-write delta on a row written ten
 * minutes ago is still a per-write delta, so a fresh row does not earn the word
 * "today" and no row ever earns "24h" — see the block comment above.
 */
export function movementWindowLabel(
  lastUpdated: string | null | undefined,
  now: Date = new Date(),
  timeZone?: string,
): string {
  if (priceAgeDays(lastUpdated, now) == null) return "last move";
  return `last move · ${instantDayLabel(new Date(lastUpdated as string), timeZone)}`;
}

/**
 * "as of Aug 28" for a price the payload dates to more than a day ago, else `null`.
 *
 * Null in BOTH unprovable directions: a genuinely fresh price needs no as-of (the
 * label would be noise, not honesty), and a price with no stamp gets no claim about
 * its freshness OR its staleness, because we cannot support either.
 */
export function asOfLabel(
  lastUpdated: string | null | undefined,
  now: Date = new Date(),
  timeZone?: string,
): string | null {
  const age = priceAgeDays(lastUpdated, now);
  if (age == null || age <= AS_OF_AFTER_DAYS) return null;
  return `as of ${instantDayLabel(new Date(lastUpdated as string), timeZone)}`;
}

export type FuturesSortField = "probability" | "change" | "name";
export type FuturesSortDirection = "asc" | "desc";

export interface SortableOutcome {
  name: string;
  probability: number | null;
  probability_change_24h?: number | null;
  /** Grading, on a settled market only. See `sortFuturesOutcomes`'s `resolved`. */
  is_winner?: boolean | null;
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
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * UX-P232 (CERT-598's block) — `resolved`: THE RESULTS ORDER LEADS WITH THE WINNER.
 *
 * On a SETTLED market the hero is not the price leader. `pickHeroOutcome` above
 * deliberately features the GRADED WINNER, whose last-traded probability is frozen
 * at whatever it was when the market closed and is routinely NOT the highest on the
 * board. Production, 2026-08-31: "Arsenal vs Coventry: First Goalscorer" grades Kai
 * Havertz at 21% while two players who did not score are frozen at 99%. Ordering by
 * price alone therefore put a loser at the top of a section headed "Final Results",
 * with the winner at row three — UX-P230's own defect (hero and table disagreeing)
 * surviving into the one state it never rendered.
 *
 * So `resolved` promotes graded winners, and its LIMIT is the point:
 *
 *   - It applies to the RESULTS ORDER only — `probability` + `desc`, the page
 *     default, the one ordering that claims to answer "what happened".
 *   - An explicit `name` or `change` sort, or `probability` ASCENDING, is a request
 *     for a different question and is answered literally. Lifting a 21% winner above
 *     a 2% longshot under a pill reading "Probability ↑" would make the arrow lie.
 *
 * The promotion is written as an ordinary ASCENDING primary key (winner sorts LAST)
 * so the single direction flip at the bottom stays the only reverser in this
 * function. An early `return` here would skip that flip, and a comparator with two
 * exits is how you get one that is not antisymmetric.
 */
export function sortFuturesOutcomes<T extends SortableOutcome>(
  outcomes: readonly T[],
  field: FuturesSortField,
  direction: FuturesSortDirection,
  resolved = false,
): T[] {
  const winnerLeads = resolved && field === "probability" && direction === "desc";

  return [...outcomes].sort((a, b) => {
    let comparison = 0;

    if (winnerLeads) {
      // Ascending like everything else: `is_winner === true` sorts last here, and
      // the flip below lifts it to the top. `false` and `null` are both simply
      // "not the winner" — an ungraded row is never promoted over a graded loser.
      comparison =
        (a.is_winner === true ? 1 : 0) - (b.is_winner === true ? 1 : 0);
    }

    if (comparison === 0) {
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
    }

    return direction === "asc" ? comparison : -comparison;
  });
}
