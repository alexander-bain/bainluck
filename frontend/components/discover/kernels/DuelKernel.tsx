/**
 * DuelKernel — the two-sided card (games + any head-to-head).
 *
 * Design source: "Discover Card System" handoff (2026-07-15), card `2c` (Duel),
 * reconciled with Alex's ruling (2026-07-15): **keep the logo/gradient hero,
 * harmonize the chrome.** So this is the rich game crest (the beloved
 * EventCard treatment) wearing the unified KernelCard chrome — state moves to
 * the header (killing the hero's redundant LIVE pill = the badge-soup fix),
 * category moves to the footer, and one angle badge sits header-right.
 *
 * Shape `duel` → kernel `split` (see lib/marketShape.ts).
 */

import { discoverCrestBadge, teamShortNames } from "@/lib/teamShortName";
import { teamTextColor } from "@/lib/teamColors";
import { KernelCard, type KernelState, type KernelGrade } from "./KernelCard";
import type { AngleValue } from "./AngleBadge";
import { CATEGORY_GRADIENTS } from "../constants";

export interface DuelKernelProps {
  state: KernelState;
  awayTeam: string;
  homeTeam: string;
  awayColor?: string;
  homeColor?: string;
  awayLogo?: string | null;
  homeLogo?: string | null;
  awayScore?: number | null;
  homeScore?: number | null;
  /** 0–1 win probabilities. */
  awayProb?: number | null;
  homeProb?: number | null;
  /**
   * #6238 — may this card print an AWAY figure at all?
   *
   * On a sport whose winner market prices a draw, the served away probability is
   * `1 − home`: "the home team does not win", i.e. away win OR draw, wearing the
   * away team's name. `lib/drawPricedWinner.ts` carries the argument and the
   * production measurements; `sportPricesADraw(sport)` is the value to pass.
   *
   * A PROP rather than a sport key, because this kernel is handed presentation
   * values (`awayProb`, `awayColor`, `stateLabel`) and does not read a payload —
   * its caller is the one that knows what sport it is holding. Today that caller
   * is only `/kernels-preview`, so nothing reader-facing renders this yet; the
   * rule is here so adopting the kernel cannot re-open the defect the rest of
   * the card family just closed.
   *
   * Defaults false, so every existing caller renders exactly as before.
   */
  awayWithheld?: boolean;
  categorySlug: string;
  categoryLabel: string;
  categoryEmoji: string;
  /** Key into CATEGORY_GRADIENTS for the hero background. */
  gradientKey?: string;
  /** Header-left state copy ("Tomorrow 7:05 PM"). */
  stateLabel?: string;
  /** Live pill suffix ("Bot 6"). */
  liveLabel?: string;
  timestamp?: string;
  angle?: AngleValue | null;
  grade?: KernelGrade | null;
  /** Settled winner. Falls back to score comparison when omitted. */
  winner?: "home" | "away" | null;
}

// #4466: the last-word rule is right for `<place> <nickname>` and wrong for
// every `<place> <club-type>` and `<place> <place> <name>` — "Paris Saint
// Germain" painted **GER**, and because the stored spelling is an input the
// same club painted **SAI** on the hyphenated row the same afternoon. This is
// the crest slot, so it takes the initials lever — `teamCrestBadge`, the 64px
// sibling of the `teamCrestInitials` the shared card paints, which carries the
// measurement and the accepted costs. #4537: through `discoverCrestBadge`, so a
// badge in `UNSHIPPABLE_BADGES` ("Avispa Fukuoka" FUK) is never painted.
function abbr(team: string): string {
  return discoverCrestBadge(team);
}

function Crest({ team, color, logo, score, show }: { team: string; color: string; logo?: string | null; score?: number | null; show: boolean }) {
  return (
    <div className="flex flex-col items-center gap-2">
      {logo ? (
        <img src={logo} alt="" aria-hidden="true" className="h-16 w-16 object-contain drop-shadow-lg" />
      ) : (
        <div className="grid h-16 w-16 place-items-center rounded-xl text-lg font-black text-white" style={{ background: color }}>
          {abbr(team)}
        </div>
      )}
      {show && score != null && <span className="text-2xl font-black tabular-nums text-white drop-shadow">{score}</span>}
    </div>
  );
}

export function DuelKernel(props: DuelKernelProps) {
  const {
    state, awayTeam, homeTeam, awayScore, homeScore, awayProb, homeProb,
    awayWithheld = false,
  } = props;
  const awayColor = props.awayColor || "#6b7280";
  const homeColor = props.homeColor || "#374151";
  // #5696 — these colours are the split bar's FILL as well as the two
  // percents' text. Only the text takes #5165's contrast floor; a brand
  // colour is a legitimate fill and repainting the bar would be a redesign.
  const awayTextColor = teamTextColor(awayColor) || "#6b7280";
  const homeTextColor = teamTextColor(homeColor) || "#374151";
  const isLive = state === "live";
  const settled = state === "settled";
  const showScores = isLive || settled;

  const winner: "home" | "away" | null =
    props.winner ??
    (settled && homeScore != null && awayScore != null && homeScore !== awayScore
      ? homeScore > awayScore ? "home" : "away"
      : null);

  const gradient = CATEGORY_GRADIENTS[props.gradientKey ?? ""] || `linear-gradient(135deg, ${awayColor}33, ${homeColor}33)`;

  const hero = (
    <div className="relative flex h-44 items-center justify-center gap-6" style={{ background: gradient }}>
      <Crest team={awayTeam} color={awayColor} logo={props.awayLogo} score={awayScore} show={showScores} />
      {!showScores && <span className="text-sm font-semibold text-white/70">{props.stateLabel ?? "vs"}</span>}
      <Crest team={homeTeam} color={homeColor} logo={props.homeLogo} score={homeScore} show={showScores} />
    </div>
  );

  const awayPct = awayProb != null ? Math.round(awayProb * 100) : null;
  const homePct = homeProb != null ? Math.round(homeProb * 100) : null;

  return (
    <KernelCard
      state={state}
      hero={hero}
      stateLabel={settled ? "Final" : props.stateLabel}
      liveLabel={props.liveLabel}
      angle={props.angle}
      grade={props.grade}
      categoryEmoji={props.categoryEmoji}
      categoryLabel={props.categoryLabel}
      timestamp={props.timestamp}
      ariaLabel={`${awayTeam} vs ${homeTeam}`}
    >
      <div className="text-[15px] font-bold leading-tight text-text-primary">
        {awayTeam} {settled ? "vs" : "@"} {homeTeam}
      </div>

      {/* #6238 — the home number survives on its own; only the away one goes.
          The row is `justify-between`, so dropping the away span leaves the home
          figure hard right under the home crest, which is what named it in the
          pair. The bar paints the home share against the neutral track and
          leaves the remainder unattributed, because a two-colour split is the
          same claim in pixels as the numeral above it. */}
      {!settled && homeProb != null && (awayProb != null || awayWithheld) && (
        <div className="mt-0.5">
          <div className="mb-1 flex items-center justify-between text-sm">
            {!awayWithheld && (
              <span className="font-bold" style={{ color: awayTextColor }}>{awayPct}%</span>
            )}
            <span className="text-[10px] text-text-muted">Win Probability</span>
            <span className="font-bold" style={{ color: homeTextColor }}>{homePct}%</span>
          </div>
          <div
            className={`flex h-2.5 overflow-hidden rounded-full ${awayWithheld ? "bg-surface-border/30 justify-end" : ""}`}
            data-away-withheld={awayWithheld ? "true" : undefined}
          >
            {!awayWithheld && (
              <div className="transition-all duration-500" style={{ width: `${awayPct}%`, backgroundColor: awayColor }} />
            )}
            <div className="transition-all duration-500" style={{ width: `${homePct}%`, backgroundColor: homeColor }} />
          </div>
        </div>
      )}

      {settled && winner && (
        <div className="mt-0.5 flex items-center gap-2">
          <span className="text-sm font-semibold text-text-primary">
            {/* UX-1065 (#2936): pair-aware, so this can never read "FC won". */}
            {(() => {
              const pair = teamShortNames({ name: homeTeam }, { name: awayTeam });
              return winner === "home" ? pair.home : pair.away;
            })()} won
          </span>
          <span className="rounded bg-accent-live/15 px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-accent-live">Final</span>
        </div>
      )}
    </KernelCard>
  );
}
