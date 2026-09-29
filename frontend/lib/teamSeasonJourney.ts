/**
 * Pure helper for the team page's "Season journey" chart (L2-162).
 *
 * The chart plots ONE season-long line: the team's own championship (or best
 * available) probability from opening day → today, on a fixed 0–100% axis with
 * no smoothing (the consolidated FuturesChart handles the rendering). We need a
 * (market_id, outcome_id) pair to fetch that outcome's history; the team futures
 * list already carries both. This picks the most meaningful line: the highest
 * signal tier the team actually has — Championship (1) > Conference (2) >
 * Division (4) — so the journey mirrors the hero's headline number.
 *
 * Side-effect-free + SSR-safe so it is unit-testable.
 */
import type { ChampionshipPathEntry, TeamFutureItem } from "./api";

// Tier preference for the single journey line. Lower array index = preferred.
const JOURNEY_TIER_PRIORITY = [1, 2, 4];

// #9113: a player's destination market ("Neymar: Next Club", "Kevin Durant's
// Next Team", Polymarket's "Where will Cristiano Ronaldo go next?") lists teams
// as its outcomes, so the team futures list carries it — but the number is the
// chance a PLAYER joins, not anything about this team's season. With no tier
// 1/2/4 market it used to win the fallback and LAFC's hero read
// `CHAMPIONSHIP 1%` (Neymar to LAFC) above a "Season journey" of that prop.
// Matched on the NAME because the name is what the payload serves for every
// row; the venue's canonical key filed all 80+ open ones as `championship`.
// "Next Team to Score" is a game prop, not a destination — hence the `to` guard.
const PLAYER_DESTINATION_RE = /\bnext\s+(?:club|team)\b(?!\s+to\b)|\bgo\s+next\b/i;

export function isPlayerDestinationMarket(marketName: string | null | undefined): boolean {
  return PLAYER_DESTINATION_RE.test(marketName ?? "");
}

/**
 * The championship-path step a team page leads with: the tier-1 step, else the
 * strongest one — or null when the path is empty or that step has no number.
 * `teamHeadline` and the journey both read the headline through this, so the
 * chart can never name a different question than the number above it.
 */
export function headlinePathEntry(
  championshipPath: ChampionshipPathEntry[] | null | undefined,
): ChampionshipPathEntry | null {
  const path = championshipPath ?? [];
  const entry = path.find((e) => e.tier === 1) ?? path[0] ?? null;
  return entry && entry.probability !== null ? entry : null;
}

export interface JourneyPick {
  marketId: number;
  outcomeId: number;
  marketName: string;
  probability: number | null;
}

/**
 * Choose the futures outcome whose season-long history best represents the
 * team's year, or null when the team has no eligible season future.
 *
 * With a `championshipPath`, the page's headline step decides (#9569): the
 * Warriors' hero read CHAMPIONSHIP 1% (the path, market 2 "NBA Championship
 * Winner") while the journey under it charted "NBA: 2026 NBA Cup Winner" at 2%
 * — the Cup is tier 1 too (`\bwinner\b`) and out-priced the title on the
 * tie-break below. The path never admitted it (its key is a prior season), so
 * the chart follows the path's market and prints the path's number. The tier
 * rule is the fallback for pages with no path.
 */
export function pickJourneyFuture(
  futures: TeamFutureItem[] | null | undefined,
  championshipPath?: ChampionshipPathEntry[] | null,
): JourneyPick | null {
  if (!futures || futures.length === 0) return null;

  // Only season-long markets with a real probability are eligible, and only
  // ones that have NOT already been graded a winner (#7396).
  //
  // A settled "✓ Won" outcome is a RESULT, not a price. Its probability is
  // parked at ~0.995, which beats every live market on the tie-break below, so
  // without this clause the one team in a league that actually won last season
  // leads its page with `CHAMPIONSHIP 100%` — Arsenal read that five games into
  // a Premier League it had not yet played (and Barcelona the same in La Liga),
  // while the SEASON FUTURES list one component down correctly rendered the
  // same outcome as `What hit / ✓ Won` and the live market at 47%. One page,
  // two answers to one question. Measured on production 2026-09-20: 2 of 507
  // teams cleared the tie-break this way, and the settled row is only ever the
  // higher number, which is why it looked like nothing site-wide.
  //
  // This mirrors the backend's own rule one layer down: `_championship_path_stmt`
  // (routes/teams.py) already drops markets with a graded winner via
  // `~graded.exists()`, which is why the preferred `championship_path` branch of
  // `teamHeadline` never had this bug — only the futures fallback did.
  //
  // `is_winner !== true` and not a market-level test on purpose: the payload
  // carries `false` for a graded LOSER and for an ungraded row alike (never
  // null, measured), so `true` is the only value that unambiguously means
  // settled. Graded losers are parked near 0 and lose the tie-break anyway.
  const eligible = futures.filter(
    (f) =>
      f.probability !== null &&
      f.market_id != null &&
      f.outcome_id != null &&
      f.is_winner !== true &&
      !isPlayerDestinationMarket(f.market_name),
  );
  if (eligible.length === 0) return null;

  const headline = headlinePathEntry(championshipPath);
  const onHeadline = headline
    ? eligible
        .filter((f) => f.market_id === headline.market_id)
        .sort((a, b) => (b.probability ?? 0) - (a.probability ?? 0))[0]
    : undefined;
  if (headline && onHeadline) {
    return {
      marketId: onHeadline.market_id,
      outcomeId: onHeadline.outcome_id,
      marketName: onHeadline.market_name,
      probability: headline.probability,
    };
  }

  const rank =(tier: number | null): number => {
    const idx = tier == null ? -1 : JOURNEY_TIER_PRIORITY.indexOf(tier);
    // Unknown/other tiers rank after the known preference order.
    return idx === -1 ? JOURNEY_TIER_PRIORITY.length : idx;
  };

  const best = [...eligible].sort((a, b) => {
    const ra = rank(a.market_tier);
    const rb = rank(b.market_tier);
    if (ra !== rb) return ra - rb;
    // Tie-break: higher probability wins (the more relevant line for the team).
    return (b.probability ?? 0) - (a.probability ?? 0);
  })[0];

  return {
    marketId: best.market_id,
    outcomeId: best.outcome_id,
    marketName: best.market_name,
    probability: best.probability,
  };
}
