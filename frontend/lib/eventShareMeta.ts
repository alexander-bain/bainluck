/**
 * eventShareMeta — what a finished game's browser tab, link preview and Google
 * result actually say.
 *
 * Q441 (#1495). Standing ruling: *settled means settled*. The event page metadata
 * did not know that. It printed the last captured win probability next to the word
 * "Final.", so a game that turned late published the losing team as the favorite —
 * to every browser tab, every shared link, and every crawler. Read off production
 * 2026-08-29, both ESPN-verified:
 *
 *   /events/15294037
 *     "Final. Bain Luck gives Villanova Wildcats a 82% win probability and
 *      William and Mary Tribe a 18% win probability."
 *     Villanova LOST 32-35.
 *
 *   /events/15291335
 *     "Final. Bain Luck gives Carolina Panthers a 49% win probability and
 *      Houston Texans a 51% win probability."
 *     Carolina WON 16-13.
 *
 * A settled event leads with the RESULT. A probability on a finished game is not a
 * smaller claim than a wrong result — it is the same claim, dressed as a forecast.
 *
 * The gate is the backend's `hero_probability_source === "settled"`, which is only
 * ever set for `status='completed'` with a real completion timestamp. It is NOT set
 * for `closed`, whose scores are frozen mid-game and invert the winner — so this
 * module cannot print a confident wrong result even when `event.status` says the
 * game is over. See backend/app/utils/settled_hero.py for the measurement.
 *
 * PURE: no fetch, no DOM.
 */

export interface EventShareMetaInput {
  home_team?: string | null;
  away_team?: string | null;
  home_score?: number | null;
  away_score?: number | null;
  status?: string | null;
  commence_time?: string | null;
  hero_probability_source?: string | null;
  hero_settled_result?: string | null;
  current_odds?: { home_probability?: number | null; away_probability?: number | null } | null;
}

export interface EventShareCopy {
  /** Page `<title>` WITHOUT a site suffix — the root layout's `%s | Bain Luck`
   * template adds it. Appending one here is what produced the doubled
   * `| Bain Luck | Bain Luck` on every event page (#1495 secondary). */
  title: string;
  description: string;
  /** True when the copy leads with a result rather than a forecast. */
  settled: boolean;
}

const SITE_SUFFIX = " | Bain Luck";

/** The backend only writes this word for a trustworthily-settled event. */
export function isSettledForShare(event: EventShareMetaInput): boolean {
  return (
    event.hero_probability_source === "settled" &&
    typeof event.home_score === "number" &&
    typeof event.away_score === "number"
  );
}

function statusLabel(event: EventShareMetaInput): string {
  if (event.status === "live") return "Live now";
  if (event.status === "completed" || event.status === "closed") return "Final";
  const start = new Date(event.commence_time ?? "");
  if (Number.isNaN(start.getTime())) return "Upcoming";
  return start.toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

function formatProbability(probability: number | null | undefined): string | null {
  if (
    probability === null ||
    probability === undefined ||
    Number.isNaN(probability) ||
    probability === 0
  ) {
    return null;
  }
  return `${Math.round(probability * 100)}%`;
}

function truncate(text: string, maxLength = 180): string {
  const cleaned = text.replace(/\s+/g, " ").trim();
  if (cleaned.length <= maxLength) return cleaned;
  return `${cleaned.slice(0, maxLength - 1).trim()}...`;
}

/**
 * Build the `<title>` / description pair for an event page.
 *
 * Settled events lead with the winner and the final score. Everything else keeps
 * the pre-existing probability copy verbatim — this function may only change what
 * a FINISHED game says.
 */
export function buildEventShareCopy(event: EventShareMetaInput): EventShareCopy {
  const home = event.home_team ?? "";
  const away = event.away_team ?? "";
  const matchup = `${away} vs ${home}`;

  if (isSettledForShare(event)) {
    const hs = event.home_score as number;
    const as_ = event.away_score as number;
    const result = event.hero_settled_result;

    if (result === "draw") {
      return {
        title: `${matchup}: Final ${hs}-${as_}, a draw`,
        description: truncate(
          `Final: ${home} and ${away} drew ${hs}-${as_}.`,
        ),
        settled: true,
      };
    }

    const homeWon = result === "home";
    const winner = homeWon ? home : away;
    const loser = homeWon ? away : home;
    const winnerScore = homeWon ? hs : as_;
    const loserScore = homeWon ? as_ : hs;

    return {
      title: `${matchup}: ${winner} won ${winnerScore}-${loserScore}`,
      description: truncate(
        `Final: ${winner} beat ${loser} ${winnerScore}-${loserScore}.`,
      ),
      settled: true,
    };
  }

  const homeProbability = formatProbability(event.current_odds?.home_probability);
  const awayProbability = formatProbability(event.current_odds?.away_probability);

  const title =
    homeProbability && awayProbability
      ? `${matchup}: ${home} ${homeProbability}, ${away} ${awayProbability}`
      : `${matchup} Odds`;

  const description = truncate(
    homeProbability && awayProbability
      ? `${statusLabel(event)}. Bain Luck gives ${home} a ${homeProbability} win probability and ${away} a ${awayProbability} win probability.`
      : `${statusLabel(event)}. Follow ${matchup} with probability-first odds on Bain Luck.`,
  );

  return { title, description, settled: false };
}

/**
 * The og:/twitter: title, which bypasses the root layout's template and therefore
 * carries the site suffix itself. Exactly one, from one place.
 */
export function withSiteSuffix(title: string): string {
  return title.endsWith(SITE_SUFFIX) ? title : `${title}${SITE_SUFFIX}`;
}
