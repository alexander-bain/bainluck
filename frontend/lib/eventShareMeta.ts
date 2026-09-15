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
 *
 * ═══ #6105 — AND "OVER" IS NOT THE ONLY WAY A FORECAST GOES STALE ═══
 *
 * Everything above is about a game something SAID was over. The other half of the
 * same lie is a match that started and that nothing ever reported on at all: it
 * never reaches `isFinishedForShare`, so it fell all the way through to the
 * present-tense probability copy at the bottom of this file.
 *
 * Measured on production 2026-09-14, `/events/15291351` (NPB), twenty days after
 * its own first pitch:
 *
 *   "Tue, Aug 25. Bain Luck gives Yomiuri Giants a 93% win probability and
 *    Tokyo Yakult Swallows a 7% win probability."
 *
 * 93% is `current_odds` captured 12:58:07Z on the 25th, about four hours into the
 * match, frozen there since. The pre-match reading on the same row is 54/46.
 *
 * `lib/eventState.ts` already owns this state for every card in the app, and its
 * own docstring names this exact failure — an unrecognised status falling through
 * to the branch that speaks about a START. So this module asks that owner rather
 * than growing a third reading of `status`: `hasNoReportedResult` decides, and
 * `suspendedSummary` words it.
 *
 * The import is a VALUE import and not type-only, which is the one thing that
 * changes about this file's purity: `eventState` is itself a leaf of pure
 * functions and string constants with no fetch and no DOM, so "the server can
 * render this" still holds.
 */

import type { SettledOutcome } from "./eventOutcome";
import { liveClaimIsUnbacked } from "./eventLivePush";
import {
  hasNoReportedResult,
  SUSPENDED_DESCRIPTION,
  VENUE_SETTLED_DESCRIPTION,
  suspendedSummary,
  venueSettledSummary,
} from "./eventState";

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
  /** @see hasNoReportedResultForShare — #6113. Served by `/api/events/{id}`. */
  live_probability_pinned?: { pinned?: boolean } | null;
  /** @see EventDetailResponse.venue_settled — #6381. Served on exactly the rows
   *  the branch below fires on, so the preview and the page it opens cannot
   *  disagree about whether a result exists. */
  venue_settled?: boolean;
  /** @see EventDetailResponse.venue_settled — #6381. */
  venue_settled_result?: string | null;
}

/**
 * ═══ #6113 — THE PREVIEW'S OWN ANSWER TO "HAS ANYONE TOLD US ANYTHING?" ═══
 *
 * `hasNoReportedResult` is card vocabulary keyed on status and time alone, and
 * must stay that way — a payload field has no business in it (the same sentence
 * page.tsx:367 is written to). But a link preview has the whole payload in hand,
 * and there is a third way a match goes quiet that status and time cannot see.
 *
 * Measured on production 2026-09-14 08:26Z, `/events/15312053` (ATP, Vishal
 * Balsekar vs Lomakin). The preview read `Live now` and `1% / 99%`; the page that
 * link opens read `No result reported` over a chart that was a flat line. The
 * payload says why:
 *
 *     "live_probability_pinned": { "pinned": true, "probability": 0.99,
 *                                  "observations": 59, "span_seconds": 7105 }
 *
 * The same 0.99 came back 59 times across just under two hours. #5077 serves this
 * flag precisely because the polls never stopped — they write on schedule, they
 * write the same value — so the STAMP is fresh (five minutes old when I read it)
 * while the NUMBER has not moved since 23 minutes after first serve.
 *
 * ── WHY THE BLEND-AGE ARM IS NOT CARRIED HERE ──
 *
 * `liveClaimIsUnbacked` takes `blendAgeMs`, and this passes `null` on purpose
 * rather than deriving a second copy of the page's `freshestSourceStamp`.
 *
 * It is not reachable on this population and that is structural, not lucky: of the
 * 23 rows sitting `live` at 08:26Z, 8 were pinned and ZERO had a blend older than
 * an hour (the oldest was six minutes), because `odds_polling.py` moves a
 * genuinely silent `live` row to `suspended` — which `hasNoReportedResult` already
 * catches one line down, and #6105 already taught both halves of this preview to
 * read. The pinned rows are the ones that net cannot see, by construction.
 *
 * And an unguarded age rule is not free: #5885 is on record for what it does to a
 * page that has not kicked off yet (a 61-minute pregame blend printing "No result
 * reported" ten hours before kickoff). Gating on `status === "live"` sidesteps that
 * entirely — a scheduled row is not live — where a bare age test would reopen it.
 *
 * The helper is still CALLED rather than inlined as `!!pinned`, so the meaning of
 * "this live claim is unbacked" keeps one owner across the page, the caption
 * (#2800) and this preview, and a later change to that rule reaches all three.
 *
 * ── WHY IT WITHHOLDS AND DOES NOT CROWN ──
 *
 * Same asymmetry as the `suspended` branch below: a pinned match can un-pin the
 * moment the price moves again, so this may refuse a forecast and may never assert
 * the match is over. Every rung that crowns someone stays on `isFinishedForShare`.
 */
export function hasNoReportedResultForShare(
  event: EventShareMetaInput,
  now: number = Date.now(),
): boolean {
  if (hasNoReportedResult(event.status, event.commence_time, now)) return true;
  if ((event.status ?? "").trim().toLowerCase() !== "live") return false;
  return liveClaimIsUnbacked({
    pinned: event.live_probability_pinned?.pinned,
    blendAgeMs: null,
  });
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

/**
 * ═══ #6119 — THE PAIR THIS PREVIEW IS ALLOWED TO PRINT, OR NOTHING ═══
 *
 * The three predicates above are about a forecast that went STALE. This one is
 * about a forecast we never had.
 *
 * Measured on production 2026-09-14, `/events/15310840` (Bayern Munich vs Bayer
 * Leverkusen, Frauen-Bundesliga) — `current_odds`, `opening_odds` and
 * `win_probability_sources` all null. The words below read it correctly and said
 * nothing numeric ("Follow Bayern Munich vs Bayer Leverkusen with
 * probability-first odds"); the PICTURE drew `50%` against `50%` in 96px over a
 * dead-even bar, off the `?? 0.5` pair at the top of `opengraph-image.tsx`.
 * Same on `/events/15312491` (Saracens vs Leicester Tigers), `live` rather than
 * scheduled. One preview, two claims — and the numeric half was inventing a coin
 * flip out of an absence.
 *
 * This is NOT #5846. That ship found the same `?? 0.5` pair producing 50/50 for a
 * link to a game that does not exist, and fixed it by narrowing `lookup`; its
 * comment says in as many words that the coalesce was left standing for "a row
 * with no price". That was a deferral, and this is the deferred case: a game that
 * really exists and that nobody has quoted.
 *
 * ── WHY THE RULE LIVES HERE AND NOT IN THE PICTURE ──
 *
 * Because the words already had it. `buildEventShareCopy` has always asked
 * `formatProbability` for both sides and fallen back to the non-numeric copy when
 * either came back null. Re-deriving that in the image route is how the two halves
 * of one preview drift, which is the whole of #6049 → #6113. So the rule is lifted
 * out WHOLE and both halves call it — the fourth adoption in this chain rather
 * than a fifth reading of the payload.
 *
 * ── REACH ──
 *
 * A straight random sample (`ORDER BY md5(id::text)`) of 80 of the 2,329 rows
 * sitting `live` or `scheduled` at 09:30Z: **35 served no price at all — 44%, or
 * roughly 1,020 previews.**
 *
 * 🔴 THAT NUMBER IS A CORRECTION, AND THE WAY IT WAS WRONG IS WORTH MORE THAN THE
 * NUMBER. The first pass read 49 of 80 — 61% — because it fetched 80 payloads in
 * a tight loop and `/api/events/{id}` rate-limits at 60/minute. A throttled body
 * is `{"detail": "Rate limit exceeded: 60/minute"}`, which has no `current_odds`
 * key, so every throttled row was counted as a row with no price. The census
 * asked "is this field absent?" of a response that was never a row. Re-measured
 * with a 1.05s spacing and every response validated by `id` before it was
 * counted: 80 of 80 resolved, 35 priceless. Anything that reads a FIELD off a
 * bulk fetch has this failure mode, and it always biases toward "absent".
 *
 * The issue's own figure (1,097, off `win_probability_sources`) was a proxy, and
 * re-measured it is a GOOD one — not the loose one the first pass claimed. Of 40
 * sampled no-source rows, 37 serve no price and 3 do; of 40 sampled with-source
 * rows, 39 are priced and 1 is not. That weights to ~45%, which agrees with the
 * direct sample. The predicate still reads `current_odds` rather than the proxy,
 * because that is the column the card actually draws from — but the proxy was
 * never the thing that was wrong here; the fetch was.
 *
 * Returns the two formatted percents TOGETHER or `null`, rather than a boolean
 * beside two locals, so the copy below cannot print one side of a pair this
 * function has already judged unprintable.
 */
export function shareForecastPercents(
  event: EventShareMetaInput,
): { away: string; home: string } | null {
  const away = formatProbability(event.current_odds?.away_probability);
  const home = formatProbability(event.current_odds?.home_probability);
  if (away === null || home === null) return null;
  return { away, home };
}

/**
 * #6119 — the picture's half, named like its three siblings.
 *
 * ═══ DELIBERATELY NARROWER THAN `shareForecastPercents`, AND THE GAP IS A
 *     STANDING DISAGREEMENT BETWEEN TWO SHIPPED RULINGS ═══
 *
 * The obvious form of this function is `shareForecastPercents(event) === null`,
 * so that the picture withholds on precisely the rows the words go quiet on. I
 * wrote that first. It is wrong, and the suite caught it.
 *
 * `formatProbability` treats an exact 0 as "no number" — inherited from #1495,
 * where it was about a bare 0.5 and never argued for a zero. #4963 then ruled the
 * OPPOSITE for this very card, by name: *"A finished game's loser is 0%, and 0%
 * is a fact, not a missing value."* Its fixture at 1.0/0.0 exists because the
 * card used to print `--` for that loser, and printing `--` was the defect.
 *
 * So the two halves already disagree about an exact zero, and they have since
 * #4963 landed. Resolving that is NOT this ship:
 *
 *   · it has no measured members — across the throttled live/scheduled samples of
 *     2026-09-14, 87 rows served a `current_odds` object and ZERO carried an
 *     exact-0 or a null probability inside it, so there is no specimen to reason
 *     from (and unlike the reach figure, this count was never at risk from the
 *     rate-limit contamination described above: a throttled body has no
 *     `current_odds` object, so it could only ever be skipped, never miscounted
 *     as a priced one);
 *   · the defect that IS measured (61% of 2,329 rows) is the key being ABSENT;
 *   · and adopting the wider rule would silently reverse #4963 on the strength of
 *     a fixture, which is how a repair becomes a regression.
 *
 * This predicate therefore asks the narrow question it can answer from the
 * measurement — IS THERE A NUMBER HERE AT ALL — and leaves the zero exactly as
 * both surfaces treat it today. The containment is asserted in
 * `__tests__/noPriceUnfurl6119.test.tsx` in BOTH directions, so the gap stays
 * visible and a later edit cannot close it by accident: every no-price row is
 * also quiet in the words, and the rows in between are exactly the zeroes.
 *
 * ═══ WITHHOLDS ONLY ═══
 *
 * Like the `suspended` and pinned-live branches: a price can arrive on the next
 * poll, so this licenses a card to stay QUIET and never licenses it to assert
 * anything. It does not touch the status word, it crowns nobody, and no cache
 * window reads it.
 */
export function hasNoPriceForShare(event: EventShareMetaInput): boolean {
  const away = event.current_odds?.away_probability;
  const home = event.current_odds?.home_probability;
  return (
    typeof away !== "number" ||
    typeof home !== "number" ||
    Number.isNaN(away) ||
    Number.isNaN(home)
  );
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
  // #6105 — the surviving "Upcoming" is deliberate and is now only reachable for a
  // row we cannot place on the clock at all. Every started row is intercepted by
  // the `hasNoReportedResult` branch before this is called, and that predicate
  // answers FALSE on an absent or unparseable `commence_time` on purpose: a row we
  // cannot date is one we have no standing to move off the schedule.
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
 *
 * `now` (#6105) is a parameter for the reason `lib/eventState` makes it one: the
 * no-result branch below is the only one here that can change answer without the
 * row changing, because a `scheduled` row crosses `UPCOMING_GRACE_MS` on the clock
 * alone. A caller that omits it gets render time, which is correct; a test pins it
 * and is the only way to assert the boundary at all (gotcha #44).
 */
export function buildEventShareCopy(
  event: EventShareMetaInput,
  outcome?: SettledOutcome | null,
  now: number = Date.now(),
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

  // ── STARTED, AND NOTHING EVER REPORTED ON IT ───────────────────────────────
  // #6105. Sits BELOW every settled branch and ABOVE the probability copy, which
  // is the whole placement: a `suspended` row that a tournament container later
  // grades still gets its result from the rungs above, and one nothing has graded
  // stops here instead of reaching the present tense.
  //
  // NOT folded into `isFinishedForShare`. `suspended` is deliberately non-terminal
  // (live/048, EVENT-GRAPH-DOCTRINE §R) — it can go back to `live` and it can be
  // settled later by something that actually watched — and CERT-752 is what
  // happens when it is treated as over: six US Open matches, one of them 1-2 down
  // in sets, were about to be settled and graded off a partial score. So this
  // branch withholds the forecast WITHOUT asserting the match is finished, which
  // is the same asymmetry the `FINISHED_STATUSES` note 150 lines up describes from
  // the other side.
  //
  // `suspendedSummary` and not a local string: it carries the last score when the
  // row holds one, and that is the substance rather than a decoration — the badge
  // says what is not known, the score says what is. Away-first, because `matchup`
  // is away-vs-home and `opengraph-image.tsx` paints the away side on the left,
  // so the title, the description and the picture stay one order (the same
  // reasoning as the note on the probability title below).
  // #6113 widens this to the pinned-live row rather than adding a branch beside
  // it: to a reader those are one sentence — *this match should have happened and
  // nobody has told us anything* — which is the sentence `SUSPENDED_LABEL` was
  // chosen for, and the same call #5459 made for the page's badge.
  // #6381 — and the venue's own grade outranks all of it. The page this link
  // opens now reads "Settled · Draw 0-0", so a preview still reading "No result
  // reported" would be #6113's defect again, told by the other half of the same
  // pair. `venueSettledSummary` is null on every row the venue has not settled,
  // so the branch is unchanged for them.
  //
  // `settled` STAYS FALSE, and that is not an oversight. It gates the copy that
  // leads with a trusted score (`hero_probability_source === "settled"`, Q441),
  // and a graded market outcome is not that measurement — flipping it here would
  // reach branches this key was never verified against. The words change; the
  // classification does not.
  if (hasNoReportedResultForShare(event, now)) {
    const settledByVenue = venueSettledSummary(
      event.venue_settled,
      event.venue_settled_result,
    );
    const summary =
      settledByVenue ??
      suspendedSummary(event.away_score, event.home_score, "away-home");
    return {
      title: `${matchup}: ${summary}`,
      description: truncate(
        `${summary}. ${settledByVenue ? VENUE_SETTLED_DESCRIPTION : SUSPENDED_DESCRIPTION}`,
      ),
      settled: false,
    };
  }

  // #6119 — the pair, from the owner the PICTURE now asks too. This was two
  // `formatProbability` locals and a `&&` between them; lifting it into
  // `shareForecastPercents` is what lets the image route withhold on exactly the
  // rows this copy already goes quiet on. The branch below is unchanged in
  // behaviour — both sides present, or neither is printed.
  const forecast = shareForecastPercents(event);

  // ── ONE ORDER, THREE SURFACES ──────────────────────────────────────────────
  // `matchup` is AWAY vs HOME (line 161) and `opengraph-image.tsx` draws the away
  // side on the left, so the picture and the matchup already agree. The two
  // percentage lists below used to run HOME-first, which flipped the teams
  // halfway through a single title. Measured on production 2026-09-13 15:31Z,
  // `/events/15297788` (away RC Lens, home Le Mans FC):
  //
  //   og:title  "RC Lens vs Le Mans FC: Le Mans FC 25%, RC Lens 75%"
  //   og:image  RC Lens 75% on the LEFT, Le Mans FC 25% on the right
  //
  // A reader pasting that link sees 75% under the left-hand crest and reads a
  // sentence that opens with the other team on 25%. Nothing was wrong with the
  // numbers — each team carried its own — but the card cannot be read straight
  // through. Away-first here makes the matchup, the title, the description and
  // the picture one order. The settled branches above are unaffected: they name
  // the winner outright, so they never depend on side order.
  const title = forecast
    ? `${matchup}: ${away} ${forecast.away}, ${home} ${forecast.home}`
    : `${matchup} Odds`;

  const description = truncate(
    forecast
      ? `${statusLabel(event)}. Bain Luck gives ${away} a ${forecast.away} win probability and ${home} a ${forecast.home} win probability.`
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
