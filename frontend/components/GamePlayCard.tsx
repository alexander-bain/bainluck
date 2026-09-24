"use client";

import { format, parseISO } from "date-fns";
import { trustedLiveClock } from "@/lib/gameTimeLabel";
import { renderedDuelPercents } from "@/lib/renderedPercent";
import { teamShortNames } from "@/lib/teamShortName";
import { teamTextColor } from "@/lib/teamColors";
import type { ActiveChartPoint } from "@/lib/types";

interface GamePlayCardProps {
  activePoint: ActiveChartPoint | null;
  homeTeam: string;
  awayTeam: string;
  homeTeamColor?: string;
  awayTeamColor?: string;
  homeTeamLogo?: string;
  awayTeamLogo?: string;
  /** Most recent chart point (shown when not hovering) */
  lastPoint?: ActiveChartPoint | null;
  /**
   * #6238 — DON'T DRAW THE AWAY HALF: THIS SPORT'S WINNER MARKET PRICES A DRAW.
   *
   * Every away figure reaching this card is `1 − home` by construction (both
   * producers say so in their own comments). On a two-outcome sport that is
   * exactly right. In soccer, `1 − P(home wins)` is "the home team does not
   * win" — *away win **or** draw* — so the number under the away name silently
   * absorbs the whole draw price.
   *
   * Photographed on production 2026-09-16 at 390px, `/events/15305024` (Daejeon
   * Citizen v Pohang Steelers, **finished 2–2**): this card read
   * **`2 - 2   Citizen 1% — Steelers 99%`**, and the same page's Additional
   * Markets card read `Tie — Won`, `Pohang Steelers — Lost`. The 99% was not
   * stale; it was the freshest reading the match had, and correct arithmetic on
   * the wrong question — the draw took all of it.
   *
   * A BOOLEAN, NOT A NULL `awayProb`, and that is a decision rather than a
   * convenience. `ActiveChartPoint` is also read by `resolveProbability`, where
   * a null away price already means "we hold no reading for this side" and
   * renders an em-dash. Folding "withheld" into that value domain would make
   * one value mean two things a layer up — the mistake `probKnown` exists to
   * undo (#3459). ux/1266 took the same shape for the hero (`awayWithheld`
   * there too), so this follows the sibling rather than inventing a second
   * answer. Native can and does null the field instead
   * (`OddsChartView.swift:1631`); its point type has no second reader.
   *
   * Absent means two-sided, never withhold — the same opt-in polarity
   * `sportPricesADraw` documents.
   */
  awayWithheld?: boolean;
  /**
   * #6684 — so the badge can stop painting `Bottom 8th 0:00` on a live MLB game.
   *
   * The KEY is passed, not a derived boolean, and that is the opposite choice
   * from `awayWithheld` directly above. The difference is where the authority
   * lives: `sportPricesADraw` is consulted by the page because the hero and
   * this card must reach the SAME withholding decision from one derivation.
   * "Does this sport have a clock" has a different authority —
   * `trustedLiveClock`, which already owns the other three rules about which of
   * ESPN's clock fields may be painted. Deriving a boolean here would put the
   * fourth rule outside the function that holds the first three, and the next
   * surface to adopt the helper would re-acquire the defect the helper exists
   * to prevent.
   */
  sportKey?: string | null;
}

/** Format period number into display string */
function formatPeriod(period?: string | null): string {
  if (!period) return "";
  // Already formatted (e.g., "1st Quarter", "Halftime")
  if (period.length > 2) return period;
  // Numeric period
  const num = parseInt(period, 10);
  if (isNaN(num)) return period;
  const suffix = num === 1 ? "st" : num === 2 ? "nd" : num === 3 ? "rd" : "th";
  return `Q${num}`;
}

/**
 * ESPN-style game play card displayed below the odds chart.
 * Updates as the user hovers/scrubs across the chart, showing:
 * - Score (team-colored)
 * - Period and clock
 * - Scoring play description (when hovering over one)
 * - Win probability (when between scoring plays)
 */
export default function GamePlayCard({
  activePoint,
  homeTeam,
  awayTeam,
  homeTeamColor,
  awayTeamColor,
  homeTeamLogo,
  awayTeamLogo,
  lastPoint,
  awayWithheld = false,
  sportKey,
}: GamePlayCardProps) {
  const point = activePoint || lastPoint;
  if (!point) return null;

  const hasScore = point.homeScore != null && point.awayScore != null;
  const hasScoringPlay = !!point.scoringPlay;
  const showsPair = !hasScoringPlay && point.probKnown !== false;
  /* #6496 — the play sentence is rendered BELOW the badge/score row, not inside
     it. Measured on production at 390px (live frontend `2ede802a7`): the row's
     other two children are `shrink-0`, so the text column settles at exactly
     159px on every game, while an NFL scoring play needs 375-472px on one line.
     Four of four most-recent completed NFL games clipped, losing 58-66% of the
     string, and the lost half is the informative one — the type label above
     already says "Passing Touchdown", so what `Kenneth Walker III 2 Yd pa…`
     dropped was "ss from Patrick Mahomes". There was no `title` attribute, so
     the text was unreachable by any reader, and a phone reader could not hover
     one anyway.
     Full width here is 334px, so two lines hold 668px — every measured play
     fits, worst case 472px. Keeping it in the column and merely clamping would
     NOT have worked: 2 x 159px = 318px still clips the 418px specimen. */
  const scoringPlayText = point.scoringPlay
    ? point.scoringPlay.description || point.scoringPlay.short_text || ""
    : "";
  /* #3295 — THE NINTH INSTANCE OF THE #2452 SHAPE, on the live event page.
     Seen on production during US Open R32, event 15304209, while Fritz was in
     his fourth set: the hero printed `62% – 38%` and this card, one scroll
     below it, printed **`Fritz 62% — Cerundolo 39%`**. Same page, same instant,
     two different numbers for the same player, and 101 between them.

     `OddsChart`'s scrub handler emits `awayProb: 1 - homeProb`, so this is an
     exact complement pair by construction. Rounding each side independently
     with half-up sends BOTH up whenever `p * 100` lands on `.5`: a blend of
     0.615 renders `Math.round(61.5) = 62` and `Math.round(38.5) = 39`. It
     never prints 99; it prints 101 or it prints right.

     `renderedDuelPercents` is the product's standing answer, contract-backed
     across web, server and Swift (`contracts/rendered_percent.json`) and
     already used by the hero directly above this card, the Discover card, the
     feed card and the tournament match list. It rounds the favourite once and
     derives the other as `100 -` that, and it leaves a pair that is genuinely
     NOT complementary alone rather than normalising it into a fiction. This
     card was simply the surface still calling a bare per-side `Math.round`,
     which is why it was the one disagreeing with the hero. */
  const [awayPct, homePct] = renderedDuelPercents(point.awayProb, point.homeProb);
  const homeProb = homePct ?? Math.round(point.homeProb * 100);
  const awayProb = awayPct ?? Math.round(point.awayProb * 100);

  // #2936 — the ninth copy of the last-word rule, and the one directly under a
  // hero that had already been fixed. `split(" ").pop()` collapses 6,335 of
  // 9,754 teams onto a shared final word: this card called Vancouver Whitecaps
  // FC "FC" three inches below a hero correctly reading "Vancouver Whitecaps FC"
  // (`/events/15298474`, 2026-09-11). `FC` alone is 115 teams and `W` is every
  // women's side in the database.
  //
  // Decided for BOTH sides at once, which is the contract and not a convenience:
  // `teamShortNames` is what stops a pair rendering "FC — FC". Calling the
  // single-name helper twice would reintroduce exactly the collision the buckets
  // in #2936 are made of.
  //
  // #2936 stays OPEN — this is one call site of many, not the fix for the class.
  //
  // #8442 — the sport goes in too. Without it the #5634 football rule never
  // ran here, so on `/events/15305207` this card read "Hotspur 0%" under a hero
  // and axis that both said "Tottenham Hotspur". The key was already a prop
  // (for the clock); a readout naming the club differently from the hero above
  // it is the same defect #2936 was, one rule later.
  const { home: homeShort, away: awayShort } = teamShortNames(
    { name: homeTeam },
    { name: awayTeam },
    sportKey,
  );

  // live/055 (#2815) — THE EIGHTH INSTANCE OF THE #1620 SHAPE, and the first one
  // this card noticed. It composed `[period, clock].join(" ")` raw, so it never
  // had the trust rules the other four surfaces share: on production event
  // 15293206 the wire ships `period: "Final"` AND `game_clock: "Final"`, and the
  // footer read **"Final Final  3 - 8"**. `trustedLiveClock` is the authority for
  // "which of ESPN's two clock fields may be painted"; adopting it fixes the
  // duplicate here and means the next surface cannot re-acquire it.
  //
  // `formatPeriod` still runs FIRST and is still this card's own: the numeric
  // "3" -> "Q3" rendering is a display choice no other surface makes. The trust
  // decision is taken over the string the reader will actually see, which is the
  // only string a duplicate can be visible in.
  const trusted = trustedLiveClock(formatPeriod(point.period), point.clock, sportKey);
  // Game clock is shown only when genuinely observed; a value carried forward from
  // an earlier snapshot is marked approximate ("~") rather than shown as exact, and
  // when there's no clock at all we fall back to the period, then to "—" (#925).
  const clockText = trusted.gameClock
    ? `${point.clockApprox ? "~" : ""}${trusted.gameClock}`
    : "";
  // #925 — A CARRIED READOUT SAYS HOW OLD IT IS. A gap-filled minute inherits
  // the last observed period / clock / score, and until now the only mark was
  // the `~` on the clock: `Q4 ~1:09` under `7:44 PM` reads as "1:09 left at
  // 7:44" when the clock was last seen at 7:41. Two rules, and they are chosen
  // together so the badge never carries two tildes:
  //
  //   1. The `~` marks the ODD ONE OUT. The clock keeps the mark it has had
  //      since `8bf2bf8d`. The period takes one only when it is the stale half
  //      of a badge whose clock is fresh, or when it is alone (baseball, where
  //      there is no clock to carry the mark).
  //   2. The line under the badge names the OLDEST observation among the
  //      components actually on screen that were carried here. Oldest, not
  //      per-field: it is the one choice that can never make a stale readout
  //      look fresher than it is, and the `~` already says which half is old.
  //
  // Each field is dated by the row that observed IT (`lib/chartGameState.ts`);
  // a clock-only row must not refresh the age of the period it never saw.
  const periodIsCarried = point.periodApprox === true && !!trusted.period;
  const clockIsCarried = point.clockApprox === true && !!trusted.gameClock;
  const periodText = trusted.period
    ? `${periodIsCarried && !clockIsCarried ? "~" : ""}${trusted.period}`
    : "";
  const gameState =
    [periodText, clockText].filter(Boolean).join(" ") || (hasScore ? "—" : "");
  let timeOfDay = "";
  try {
    timeOfDay = format(parseISO(point.timestamp), "h:mm a");
  } catch {
    timeOfDay = "";
  }

  // The observations behind whatever the badge is showing. A score joins the
  // set only when the badge has nothing else — then the "—" and the score ARE
  // the readout being dated. A fresh field contributes nothing; a field with
  // no observation timestamp contributes nothing (a producer that does not
  // date its state leaves the card exactly as it was before this ship).
  const carriedObservations: string[] = [];
  if (periodIsCarried && point.periodObservedAt) {
    carriedObservations.push(point.periodObservedAt);
  }
  if (clockIsCarried && point.clockObservedAt) {
    carriedObservations.push(point.clockObservedAt);
  }
  if (!trusted.period && !trusted.gameClock && hasScore && point.scoreApprox && point.scoreObservedAt) {
    carriedObservations.push(point.scoreObservedAt);
  }
  let stateAsOf = "";
  if (carriedObservations.length > 0) {
    try {
      const oldest = carriedObservations.reduce((a, b) =>
        parseISO(a).getTime() <= parseISO(b).getTime() ? a : b,
      );
      const observed = format(parseISO(oldest), "h:mm a");
      // Minute-keyed rows, so a carry never spans less than a minute; when the
      // two read the same minute the line would only repeat the time above it.
      if (observed !== timeOfDay) stateAsOf = observed;
    } catch {
      stateAsOf = "";
    }
  }

  return (
    <div className="mt-3 border-t border-surface-border pt-3">
      <div className="flex items-start gap-3 gap-y-1 flex-wrap">
        {/* Game-state badge: period + clock (top), time of day (bottom) */}
        {(gameState || timeOfDay) && (
          <div className="shrink-0 flex flex-col items-start gap-0.5">
            {gameState && (
              <span className="text-xs text-text-primary font-semibold tabular-nums bg-surface-secondary px-2 py-1 rounded">
                {gameState}
              </span>
            )}
            {timeOfDay && (
              <span className="text-[10px] text-text-muted px-2 tabular-nums">
                {timeOfDay}
              </span>
            )}
            {stateAsOf && (
              <span
                className="text-[10px] text-text-muted px-2 tabular-nums"
                data-testid="game-play-card-state-as-of"
              >
                as of {stateAsOf}
              </span>
            )}
          </div>
        )}

        {/* Score */}
        {hasScore && (
          <div className="shrink-0 flex items-center gap-2 text-sm font-bold tabular-nums">
            <span className="flex items-center gap-1">
              {homeTeamLogo && (
                <img src={homeTeamLogo} alt="" width={14} height={14} className="w-3.5 h-3.5 object-contain" />
              )}
              <span style={{ color: teamTextColor(homeTeamColor) || "var(--text-secondary)" }}>
                {point.homeScore}
              </span>
            </span>
            <span className="text-text-muted text-xs">-</span>
            <span className="flex items-center gap-1">
              <span style={{ color: teamTextColor(awayTeamColor) || "var(--text-secondary)" }}>
                {point.awayScore}
              </span>
              {awayTeamLogo && (
                <img src={awayTeamLogo} alt="" width={14} height={14} className="w-3.5 h-3.5 object-contain" />
              )}
            </span>
          </div>
        )}

        {/* Play description or probability context.
            #8433 — the pair asks for the width it needs before it shares the
            row. At 390px the badge and score (both `shrink-0`) left this
            column ~80px, and "Cowboys 66% — Commanders 34%" broke as
            `Commanders` / `34%`, a name on one line and its number on the
            next (`/events/14781697`). `basis-48` (192px, the width a common
            pair takes at text-xs) lets the row wrap the pair onto its own
            full-width line when the row cannot give it that; a wide card keeps
            it beside the score. The other two branches are short labels, so
            they keep `flex-1` and do not move. */}
        <div className={showsPair ? "min-w-0 grow basis-48" : "flex-1 min-w-0"}>
          {hasScoringPlay ? (
            <div>
              <p className="text-xs font-semibold text-red-600 flex items-center gap-1">
                <span className="inline-block w-1.5 h-1.5 rounded-full bg-red-500 shrink-0" />
                {point.scoringPlay!.type && (
                  <span className="text-text-muted font-normal">
                    {point.scoringPlay!.type}
                  </span>
                )}
              </p>
            </div>
          ) : point.probKnown === false ? (
            /* #3459 — no source has a probability for this event, so there is no
               number to print. Saying nothing is the honest reading; printing the
               placeholder was how "Ram/Salisbury 50% — Arribage/Olivetti 50%"
               appeared under a chart that said "Tracking will begin when odds are
               available". The score, period and clock above still render, so a
               live game with no price keeps everything we DO know. */
            <p className="text-xs text-text-muted" data-testid="game-play-card-no-probability">
              No price yet
            </p>
          ) : (
            <p className="text-xs text-text-muted" data-testid="game-play-card-probability">
              {/* #8433 — each side is one `inline-block` unit, so the line can
                  only break BETWEEN sides. `whitespace-nowrap` was tried and
                  clipped (`— Commanders 3`); an inline-block still wraps
                  inside itself if a single side is wider than the card. */}
              <span className="inline-block" data-testid="game-play-card-side">
                {homeShort}{" "}
                <span className="font-semibold" style={{ color: teamTextColor(homeTeamColor) || "var(--text-secondary)" }}>
                  {homeProb}%
                </span>
              </span>
              {/* #6238 — the separator belongs to the slot it separates. Left
                  behind, this reads `Citizen 1% —` and a reader takes it for a
                  half-loaded card rather than a decision (#5696 caught the same
                  thing on the hero, where the em-dash at `text-[48px]` drew a
                  41px redaction bar). The home half still names its side, so
                  one number alone is still attributed. */}
              {!awayWithheld && (
                <>
                  {" "}
                  <span className="inline-block" data-testid="game-play-card-side">
                    {"— "}
                    {awayShort}{" "}
                    <span className="font-semibold" style={{ color: teamTextColor(awayTeamColor) || "var(--text-secondary)" }}>
                      {awayProb}%
                    </span>
                  </span>
                </>
              )}
            </p>
          )}
        </div>
      </div>

      {/* #6496 — the play sentence, at the card's full width.
          `line-clamp-2`, NEVER `truncate`: the two cannot be combined, because
          `truncate` sets `white-space: nowrap` and silently defeats the clamp,
          which would ship back the exact bug this fixes. That is #4342's finding
          on the golf list (`UpcomingTournaments.tsx:96`), the same shape — a
          `min-w-0` text column squeezed by `shrink-0` siblings — and
          `line-clamp-2` is already the house idiom. The clamp keeps a
          pathological string from growing the card without bound; nothing
          measured reaches it. */}
      {hasScoringPlay && scoringPlayText && (
        <p
          className="text-xs text-text-primary mt-1 line-clamp-2"
          data-testid="game-play-card-description"
        >
          {scoringPlayText}
        </p>
      )}
    </div>
  );
}
