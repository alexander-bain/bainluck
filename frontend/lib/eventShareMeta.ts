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
 * ═══ THE SECOND AUTHORITY (CERT-1938's block) ═══
 *
 * A score is not the only thing that names a winner, and gating on one is how the
 * first cut of this module still published a probability on a decided match.
 * Measured on production 2026-09-05, `/events/15293846`:
 *
 *   <title>Stan Wawrinka vs Matteo Berrettini: Matteo Berrettini 84%,
 *          Stan Wawrinka 16% | Bain Luck | Bain Luck</title>
 *
 * Berrettini had won it `7-6, 7-6, 6-0` six days earlier. The row is `closed`, so
 * the score rung correctly declines it — but `/api/tournaments/by-event/15293846`
 * carries `result.winner_entity_key = "matteo-berrettini"` and the set line, and
 * the VISIBLE hero on that same page already reads it. Two surfaces on one page,
 * one knowing the result and one publishing a forecast.
 *
 * So this module no longer decides who won. It takes a `SettledOutcome` from
 * `lib/eventOutcome.ts` — the ladder the visible hero uses (rung 1 the event's own
 * score, rung 2 the tournament container, `null` when neither answers) — and only
 * decides how to WORD it. One authority ladder, two renderings; adding a third rung
 * changes neither this file nor the hero.
 *
 * ═══ AND WHEN NOTHING ANSWERS ═══
 *
 * A finished game with no authority gets explicit no-result copy, NOT the last
 * captured probability. "Final." beside a forecast is the defect this module
 * exists to remove; it is not made acceptable by our not knowing the winner.
 *
 * PURE: no fetch, no DOM. The `SettledOutcome` import is TYPE-ONLY and erases at
 * compile time, so this stays a leaf module the server can render.
 */

import type { SettledOutcome } from "./eventOutcome";

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

/**
 * The statuses that mean "this game is over", for the purpose of REFUSING to
 * publish a forecast.
 *
 * Deliberately WIDER than `settled_hero.RESOLVABLE_STATUSES`, and the asymmetry is
 * the point: `closed` is not trustworthy enough to crown a winner FROM THE SCORE,
 * but it is more than enough to know we must not call the game a coin-flip in
 * progress. Trusting a status to withhold a claim is safe in a way trusting it to
 * make one is not.
 */
const FINISHED_STATUSES = new Set(["completed", "closed"]);

export function isFinishedForShare(event: EventShareMetaInput): boolean {
  return FINISHED_STATUSES.has((event.status ?? "").trim().toLowerCase());
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
 * Settled events lead with the winner. Everything else keeps the pre-existing
 * probability copy verbatim — this function may only change what a FINISHED game
 * says.
 *
 * `outcome` is the resolved authority ladder from `resolveEventOutcome`, or
 * `null`/omitted when the caller has none. Omitting it is not the same as passing
 * `null` from a caller that looked: both fall through to the score rung below, so
 * a caller that cannot reach the tournament payload still gets the score-based fix
 * rather than nothing.
 */
export function buildEventShareCopy(
  event: EventShareMetaInput,
  outcome?: SettledOutcome | null,
): EventShareCopy {
  const home = event.home_team ?? "";
  const away = event.away_team ?? "";
  const matchup = `${away} vs ${home}`;

  // ── RUNG 1+2, via the hero's own ladder ────────────────────────────────────
  // The winner's name comes from the EVENT when the ladder could place the
  // winner on a side, because a page title wants "William and Mary Tribe", not
  // the hero's shortened "Tribe". `winnerName` is the fallback for the case the
  // ladder is explicit about: a named winner it could not match to either
  // competitor. Never inferred — an unmatched winner still gets named, it just
  // does not get a side.
  if (outcome) {
    const winner =
      outcome.winnerSide === "home"
        ? home
        : outcome.winnerSide === "away"
          ? away
          : outcome.winnerName;

    // HOW the result is worded follows WHICH rung answered, not what happens to
    // be on the row. On a `closed` tournament match the event carries scores
    // (3 and 0 on 15293846) that the score rung deliberately refused; reading
    // them here would smuggle the untrusted number back in under the trusted
    // rung's answer.
    let line: string | null = null;
    if (outcome.authority === "score") {
      const hs = event.home_score;
      const as_ = event.away_score;
      if (typeof hs === "number" && typeof as_ === "number" && hs !== as_) {
        const homeWon = hs > as_;
        line = `${homeWon ? hs : as_}-${homeWon ? as_ : hs}`;
      }
    }
    line = line ?? outcome.resultLine;

    // The beaten side, only when the ladder placed the winner. An outcome with no
    // side is a winner we could not match to either competitor, and "beat" needs
    // someone to have been beaten — so that case says "won" and names nobody
    // rather than guessing which of the two it was.
    const loser =
      outcome.winnerSide === "home"
        ? away
        : outcome.winnerSide === "away"
          ? home
          : null;

    // Worded exactly as the score rung has always worded it, so adding the second
    // authority does not quietly restyle the copy on every settled team game.
    const sentence = loser
      ? `Final: ${winner} beat ${loser}${line ? ` ${line}` : ""}.`
      : `Final: ${winner} won${line ? ` ${line}` : ""}.`;

    return {
      title: line
        ? `${matchup}: ${winner} won ${line}`
        : `${matchup}: ${winner} won`,
      description: truncate(sentence),
      settled: true,
    };
  }

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

  // ── FINISHED, AND NOTHING NAMED A WINNER ───────────────────────────────────
  // The last rung, and the one that makes the ladder honest. Falling through to
  // the probability copy here is what published "Final. Bain Luck gives Matteo
  // Berrettini a 84% win probability" six days after he had won the match.
  //
  // A forecast on a decided game is not a smaller claim than a wrong result — it
  // is a claim about a question that is closed. So the copy states what we
  // actually hold: it is over, and we do not have the result. This is the same
  // distinction the settled draw draws (`result` present, nobody won) versus a
  // bare 0.5 (#1495 criterion 4) — "nobody won" and "we do not know" must not
  // render as the same sentence.
  if (isFinishedForShare(event)) {
    return {
      title: `${matchup}: Final`,
      description: truncate(
        `Final. Bain Luck does not have a confirmed result for ${matchup} yet.`,
      ),
      settled: false,
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
