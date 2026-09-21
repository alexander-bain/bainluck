"use client";

import { useState, useMemo, useEffect } from "react";
import {
  ComposedChart,
  Line,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";
import Link from "next/link";
import { format, parseISO } from "date-fns";
import {
  makeEnsurePoint,
  toMinuteKey,
  fillMinuteGaps,
  CATEGORY_LABEL_FORMAT,
} from "@/lib/chartTimeline";
// #1003 guard: the single 0–1 ⇄ 0–100 axis conversion (see eventKeyStats).
import {
  homeProbToChartAxis,
  chartAxisToHomeProb,
  chartAxisPercents,
  computeWinProbYAxis,
} from "@/lib/eventKeyStats";
import { chartTooltipPair } from "@/lib/drawPricedWinner";
import { separateLinesLabel, sourceHex, sourceLabel } from "@/lib/sourceColors";
import { teamShortNames } from "@/lib/teamShortName";
import { teamTextColor } from "@/lib/teamColors";
import { useAnalyticsContext } from "@/components/Analytics";
import type {
  OddsHistoryPoint,
  BookmakerHistoryPoint,
  ESPNHistoryPoint,
  WinProbHistoryPoint,
  WinProbSourceMeta,
  ScoringPlay,
  ActiveChartPoint,
} from "@/lib/types";
import type { PeriodBoundary } from "@/lib/periodMarkers";
import {
  dedupePeriodLabels,
  assignPeriodLabelRows,
  anchorPeriodLabels,
  PERIOD_LABEL_ROW_HEIGHT_PX,
} from "@/lib/periodMarkers";

/** Fallback source configs when win_prob_sources metadata isn't available */
// Colors come from the one source-color registry (@/lib/sourceColors) — the
// deliberate dark, high-contrast "betting" slate (L2-131) is now the canonical
// odds_api hex there. Only the display name / dash / type stay local.
const FALLBACK_SOURCE_CONFIG: Record<string, { display_name: string; color: string; dash_pattern: string | null; type: "model" | "market" }> = {
  // #2442: the NAME now comes from the source registry (`sourceLabel`), the
  // same place the colour comes from, so this map no longer carries a second
  // spelling of it. `sourceLabel("betting")` is "Sportsbooks".
  betting: { display_name: sourceLabel("betting"), color: sourceHex("betting"), dash_pattern: null, type: "market" },
  espn: { display_name: "ESPN", color: sourceHex("espn"), dash_pattern: "6 3", type: "model" },
  stat_model: { display_name: "Bain Luck Model", color: sourceHex("stat_model"), dash_pattern: "4 4", type: "model" },
  kalshi: { display_name: "Kalshi", color: sourceHex("kalshi"), dash_pattern: "8 4", type: "market" },
  polymarket: { display_name: "Polymarket", color: sourceHex("polymarket"), dash_pattern: "8 4", type: "market" },
  fangraphs: { display_name: "MLB Model", color: sourceHex("fangraphs"), dash_pattern: "4 4", type: "model" },
};

/** Bain Luck aggregated (blend) line config */
const BAIN_LUCK_CONFIG = {
  color: sourceHex("blend"), // emerald-600 — the one blend line
  displayName: "Bain Luck",
  dataKey: "bainLuckDelta",
};

// ── The current-probability callout's BACKING PLATE (#4338) ──────────────────
//
// #3561 made the callout legible over ONE line by haloing the glyphs — a white
// stroke painted under the fill. #4338 is what that halo cannot do. The label
// sits at the right-hand end of the plot, which is *now*, and is by construction
// the densest ink on the chart: measured on production 2026-09-09 at 390px
// (`/events/15307447`, Andreeva–Gauff), FOUR series paths cross the label's own
// box — the blend, and three source lines. A 1.5px halo traces each glyph's
// outline; it cannot keep four lines out of the counters of a `3` and a `5`, and
// the `%` — the glyph with the most enclosed area — loses outright. At 1× the
// number scanned as `363%`.
//
// So the same white the halo already paints is filled ACROSS the glyph box
// instead of only around each glyph. That is deliberately not a new visual
// element: it reads as a slightly wider halo, not as a chip, because the plot's
// background is this exact white. It is also the only fix available — #3561
// already established that the label must stay on the dot's row at every slope,
// so it cannot be moved out of the ink, only made to sit legibly on top of it.
//
// The plate is SIZED, not guessed. `<text>` has no layout box in SVG, so the
// width comes from the string: measured on the same load, bold 11px monospace
// advances 6.604px per glyph — 0.6004em, exactly the monospace ratio — and the
// glyph box is 13px tall, centred on `y` by `dominantBaseline="central"`.
const CALLOUT_FONT_PX = 11;
// Both rounded UP off those measurements, so the plate is never narrower or
// shorter than the glyphs it has to cover. `chartTextStaysInsideThePlot`
// asserts the cover using the MEASURED numbers, not these — two artifacts
// sharing one constant agree about a wrong input perfectly (that file's header).
const CALLOUT_MONO_ADVANCE_EM = 0.62;
const CALLOUT_GLYPH_BOX_EM = 1.2;
// Horizontal padding also has to clear the text's own 3px halo (1.5px a side).
const CALLOUT_PLATE_PAD_X = 3;
const CALLOUT_PLATE_PAD_Y = 2;
/** Gap between the label's right edge and the dot it labels — #3525's `cx - 12`. */
const CALLOUT_GAP_PX = 12;
/**
 * #5581 — the band at the top of the plot that the period chips paint into,
 * MEASURED on the rendered page rather than derived from the font size.
 *
 * The chips are `ReferenceLine` labels at `insideTopLeft` (see
 * `filteredPeriodBoundaries` below). On `/events/15308045` at 390px, read with
 * `getBBox()` off the live SVG on 2026-09-12: the plot's top edge is `y=15` and
 * every chip's box is `y=16.81..29.81`, so the strip occupies **14.81px**
 * measured DOWN from that edge. 15 is that rounded UP.
 *
 * Rounding up is the safe direction and the direction matters: the number is
 * used to push the callout CLEAR of the chips, so an over-estimate costs a pixel
 * of drop while an under-estimate re-opens the collision. The same reasoning
 * `CALLOUT_MONO_ADVANCE_EM` is rounded up for — and the reason this is 15 and
 * not the 14 a line-box estimate suggests.
 *
 * #7134 — IT IS ONE ROW, AND THE STRIP IS NOT ALWAYS ONE ROW. `/events/15308045`
 * drew every chip on row 0, so this measured the whole strip there. #6882 then
 * taught the chips to stagger onto a second row, and the callout was never told:
 * on `/events/15314181` it cleared row 0 exactly and landed on `T9` on row 1.
 * So this is the depth of ONE row and `calloutLabelCenterY` adds the rest.
 */
const PERIOD_CHIP_BAND_PX = 15;
/**
 * Half the callout label's painted box — the plate, which is the widest thing
 * drawn (the glyphs sit inside it) and so the thing that must clear an edge.
 * Derived from the plate's own geometry below, not restated: `#4338` paints it
 * at `cy - glyphHeight / 2 - CALLOUT_PLATE_PAD_Y` with height
 * `glyphHeight + CALLOUT_PLATE_PAD_Y * 2`.
 */
const CALLOUT_PLATE_HALF_PX =
  (CALLOUT_FONT_PX * CALLOUT_GLYPH_BOX_EM) / 2 + CALLOUT_PLATE_PAD_Y;

/**
 * Where the trailing value label is painted, vertically (#5581).
 *
 * ═══ WHY THE LABEL CANNOT SIMPLY SIT ON `cy` ═══
 *
 * It sat on `cy` — it is labelling the dot, and #3561 ruled out lifting it off
 * the dot's row for a *steeply-arriving* series. That reasoning is still right
 * and is not what this is. At the FRAME the label is not merely awkward, it is
 * cut in half and unreadable, and a label nobody can read marks nothing.
 *
 * The y domain is capped at 100 (`computeWinProbYAxis` snaps with
 * `Math.min(100, …)`, because a probability has nowhere above 100 to go), so a
 * game that finishes at 100% puts the last data point EXACTLY on the plot's top
 * edge. The YAxis carries `allowDataOverflow`, which makes recharts clip every
 * Scatter layer to the plot rect. A box centred on the top edge therefore loses
 * its upper half — by construction, on every blowout, not as a property of one
 * specimen. Measured on `/events/15308045`: plot top `y=15`, callout `cy=15`,
 * label box `y=8.5..21.5` — 6.5px of it cut. 0% does the same at the bottom.
 *
 * ═══ WHY IT IS NOT JUST A CLAMP INTO THE FRAME ═══
 *
 * native/024 recorded the trap when it fixed this chart's twin on iOS (#3237):
 * *the clamp alone was WRONG* — pulling "Final" in off the trailing edge drove
 * it into "9th" and the walk-off chart drew "9Final". A clamp that stops at the
 * frame does not fix a collision, it relocates one. The neighbour here is the
 * period-chip strip, which paints into the first `PERIOD_CHIP_BAND_PX` of the
 * plot at the same x the callout occupies (`T8` and `T9` are the chips the
 * `100%` overprinted in the filed frames). So the top floor clears the strip,
 * not merely the edge.
 *
 * The strip is only consulted when the chart is drawing one. The `Start` marker
 * is deliberately NOT counted: it is anchored `insideTopLeft` at the plot's LEFT
 * edge while the callout is always at the right edge by construction, so it can
 * never be the neighbour, and counting it would spend ~15px of drop on every
 * chipless chart for nothing.
 *
 * ═══ #7134 — AND THE STRIP IS AS DEEP AS THE CHART DREW IT ═══
 *
 * #5581 asked "are there chips?" and answered with one row, because the page it
 * was measured on had one row. #6882 gave the chips a second row for pairs too
 * close to read side by side, and the callout kept clearing one: measured on
 * `/events/15314181` at 390px on 2026-09-19, the callout's box and `T9`'s
 * overlapped by 4×11px, eleven of the callout's thirteen rows of pixels, and the
 * callout's centre sat on `plotTop + PLATE_HALF + PERIOD_CHIP_BAND_PX` to the
 * pixel — cleared row 0 exactly, landed on row 1.
 *
 * So the question is no longer "are there chips" but "how many rows of them",
 * and the band is `PERIOD_CHIP_BAND_PX + (rows - 1) * PERIOD_LABEL_ROW_HEIGHT_PX`
 * — the two constants that already describe the strip, not a third number.
 *
 * The count is the whole chart's deepest row, not the deepest row NEAR the
 * callout. A chart whose only staggered pair sits mid-plot spends 13px of drop
 * it did not need. That is deliberate and it is the direction #5581 already
 * chose for this band: an over-estimate costs a pixel of drop, an under-estimate
 * re-opens the collision. Narrowing it to the chips that horizontally overlap
 * the callout means re-deriving each boundary's x from the renderer's scale
 * inside the shape, which is exactly the drift this function avoids by taking
 * the plot rect from `yAxis` — and it would buy a few pixels on a chart that is
 * already legible.
 *
 * ═══ WHAT THIS DOES NOT MOVE ═══
 *
 * The dot. It marks the data point, and on these pages the data point really is
 * at the ceiling — a half dot on the frame is the value being honest about where
 * it landed. Moving a marker off its own datum is the other half of what
 * native/024 warned against, and #3561's "the label has to stay on the dot's
 * row" says which of the two is the anchor.
 *
 * `cy` is returned unchanged whenever the label already fits, which is every
 * chart whose series does not finish against the frame.
 */
export function calloutLabelCenterY(args: {
  cy: number;
  /** Plot rect, read off the renderer's own `yAxis` — never re-derived from the margin. */
  plotTop: number;
  plotHeight: number;
  /**
   * How many ROWS of period chips the chart is drawing — 0 for none, 1 for the
   * unstaggered strip #5581 measured, 2 once #6882's stagger fires. See the
   * `Start` marker note above for what is not counted.
   *
   * A count rather than a boolean because the strip's depth is the thing the
   * label has to clear, and #7134 is what asking the boolean cost.
   */
  periodChipRows: number;
}): number {
  const { cy, plotTop, plotHeight, periodChipRows } = args;
  if (!Number.isFinite(plotTop) || !Number.isFinite(plotHeight) || plotHeight <= 0) return cy;

  // A NaN or negative count is a caller bug, and the honest answer to one is the
  // no-strip case rather than a NaN floor that would silently return the datum
  // and read exactly like "the label already fitted".
  const rows = Number.isFinite(periodChipRows) ? Math.max(0, Math.floor(periodChipRows)) : 0;
  const band = rows > 0 ? PERIOD_CHIP_BAND_PX + (rows - 1) * PERIOD_LABEL_ROW_HEIGHT_PX : 0;

  const ceiling = plotTop + plotHeight - CALLOUT_PLATE_HALF_PX;
  const insideFrame = plotTop + CALLOUT_PLATE_HALF_PX;
  const clearOfChips = insideFrame + band;

  // A plot too short to hold the label at all has no honest answer; leave the
  // label where the data put it rather than invent a position. native/024's
  // "visibly wrong beats arbitrarily wrong", same call.
  if (insideFrame > ceiling) return cy;
  // Too short to also clear the strip: staying inside the frame is the half that
  // must not be given up, because outside it the label is not drawn at all.
  const floor = clearOfChips > ceiling ? insideFrame : clearOfChips;
  return Math.min(Math.max(cy, floor), ceiling);
}

interface OddsChartProps {
  history: OddsHistoryPoint[];
  homeTeam: string;
  awayTeam: string;
  commenceTime?: string;
  isLive?: boolean;
  bookmakerHistory?: Record<string, BookmakerHistoryPoint[]>;
  /** ESPN win probability history (legacy, used as fallback) */
  espnHistory?: ESPNHistoryPoint[];
  /** Multi-source win probability history */
  winProbHistory?: Record<string, WinProbHistoryPoint[]>;
  /** Source metadata (display names, colors, types) */
  winProbSources?: Record<string, WinProbSourceMeta>;
  /** Scoring plays from StatPal play-by-play for chart annotations */
  scoringPlays?: ScoringPlay[];
  /** Backend-computed aggregate line (weighted median with staleness decay) */
  aggregateLine?: Array<{ timestamp: string; home_probability: number }>;
  /** Event ID for analytics tracking */
  eventId?: number;
  /** Event status - determines default filter: closed/completed defaults to "Since Start", open defaults to "All" */
  eventStatus?: string;
  /** When true, chart fills its parent container height instead of using fixed h-80 */
  fillContainer?: boolean;
  /** Period boundaries for vertical divider annotations (Q1/Q2/Q3/Q4 etc.) */
  periodBoundaries?: PeriodBoundary[];
  /** Home team primary color (hex) for team label styling */
  homeTeamColor?: string;
  /** Away team primary color (hex) for team label styling */
  awayTeamColor?: string;
  /** Home team logo URL (small) */
  homeTeamLogo?: string;
  /** Away team logo URL (small) */
  awayTeamLogo?: string;
  /** Home team abbreviation (e.g. "BOS") from ESPN */
  homeTeamAbbrev?: string;
  /** Away team abbreviation (e.g. "OKC") from ESPN */
  awayTeamAbbrev?: string;
  /** Callback when user hovers/scrubs chart — null when mouse leaves */
  onActivePointChange?: (point: ActiveChartPoint | null) => void;
  /** Callback reporting the chart's actual rendered time domain (first & last timestamps).
   *  Used by ScoreDifferentialChart to match its x-axis exactly. */
  onRenderedDomain?: (startISO: string, endISO: string) => void;
  /** Shared chart domain from parent — when set, overrides internal domain computation
   *  so OddsChart and ScoreDiffChart have identical x-axes. */
  chartStartTime?: string;
  chartEndTime?: string;
  sharedTicks?: string[];
  /** #3419: the format `sharedTicks` were built with. Categories and period
   *  markers must use the SAME string or a tick lands on the wrong column. */
  chartLabelFormat?: string;
  /** External time range from parent — when set, syncs both charts' All/Since Start toggle */
  externalTimeRange?: "all" | "live";
  onTimeRangeChange?: (range: "all" | "live") => void;
  /** Authoritative game end time from the backend (set when any source confirms game over) */
  completedAt?: string;
  /**
   * #6238 — this sport's winner market prices a draw, so the tooltip may not
   * print an away percentage: every one it could print is `100 − home`, which
   * on a three-way market is "the home team does not win" (away win OR draw).
   *
   * Decided ONCE by the page (`awaySlotWithheld`, from `sportPricesADraw`) and
   * handed down, rather than re-derived here from a sport key. Two derivations
   * of one rule is how the hero and the card below this chart came to print
   * different answers in the first place. Absent means two-sided.
   */
  awayWithheld?: boolean;
}

type TimeRange = "all" | "live";

const TIME_RANGE_OPTIONS: { value: TimeRange; label: string }[] = [
  { value: "all", label: "All" },
  { value: "live", label: "Since Start" },
];

interface ChartDataPoint {
  timestamp: string;
  time: string;
  // NOTE: the `*Delta` field names are legacy. As of L2-131 these hold the raw
  // HOME win probability on a single 0–100 axis (not a delta from 50), so the
  // chart reads as one clean 0–100 scale instead of the old mirrored ±50 axis.
  /** Home win probability, 0–100 */
  homeDelta: number | null;
  /** ESPN home win probability, 0–100 (legacy) */
  espnDelta: number | null;
  /** Bain Luck aggregated win probability, 0–100 (multi-source mode) */
  bainLuckDelta: number | null;
  /** Game state carried through for interactive play-by-play card */
  _homeScore?: number | null;
  _awayScore?: number | null;
  _period?: string | null;
  _clock?: string | null;
  /** True when `_clock` was carried forward from an earlier snapshot (#925). */
  _clockApprox?: boolean;
  _scoringPlay?: ScoringPlay | null;
  [key: string]: string | number | boolean | null | undefined | ScoringPlay;
}

/** Resolved source info used for rendering */
interface ResolvedSource {
  key: string;
  dataKey: string;
  displayName: string;
  color: string;
  dashPattern: string | null;
  type: "model" | "market";
  snapshotCount: number;
}

/**
 * ═══ THE FAINT LINES STAY ANONYMOUS ON THE CHART — ALEX RULED 3B (UX-P154) ═══
 *
 * ⚠️ DO NOT REBUILD END-OF-LINE SOURCE LABELS HERE. This paragraph exists
 * because the argument for them is genuinely good and the next lane to read
 * this chart will make it again.
 *
 * UX-P152 read Alex's *"a faint gray line per source behind it, LABELED
 * (Kalshi / Polymarket / ESPN / sportsbook), barely-there but readable"*
 * (2026-08-28) as a request for an annotation ON the plot, built one
 * (`SourceEndLabel`: each series' name written in its own colour at its own
 * last real point), and put it beside the shipped treatment as panels 3A and
 * 3B for Alex to choose between.
 *
 * **Alex ratified 3B — the shipped `+ N sources` press — over 3A** (review of
 * P149/P150/P151/P152, relayed through the UX-P154 runner directive:
 * *"Panel 3B ('+ N sources' press) is RATIFIED over 3A."*). So 3A is reverted
 * in full: the label component, the last-real-point index, and the per-series
 * `label` prop are gone, and the chart is exactly what it was before UX-P152
 * touched it — the blend at width 3 on top, the source lines at width 1 /
 * opacity 0.28 behind it (L2-131, UX-P022), named only inside the legend.
 *
 * WHAT 3A WAS RIGHT ABOUT, so the finding is not lost with the code: an
 * end-of-line label is the only annotation that can carry WHEN a source stopped
 * being quoted — a sportsbook dropping out of a blowout has its line stop, and
 * a legend cannot show that. That remains true and unsurfaced. It is a real
 * gap, and the next attempt at it should start from that gap rather than from
 * "the faint lines are anonymous", which Alex has now considered and accepted.
 */

/**
 * Win probability chart with two display modes:
 *
 * **Mode A (Multi-source):** When multiple probability sources exist
 * (sportsbooks + ESPN/Kalshi/Polymarket/models), shows:
 *   - An aggregated "Bain Luck" line prominently (solid, with area fill)
 *   - Each individual SOURCE as a thin, semi-transparent line with its color
 *   - Individual bookmakers are HIDDEN
 *
 * **Mode B (Sportsbooks-only):** When only sportsbook data exists:
 *   - Sportsbook consensus line shown prominently (solid, with area fill)
 *   - Individual bookmaker lines shown faintly in grey
 */
export default function OddsChart({
  history,
  homeTeam,
  awayTeam,
  commenceTime,
  isLive = false,
  bookmakerHistory,
  espnHistory,
  winProbHistory,
  winProbSources,
  scoringPlays,
  aggregateLine,
  eventId,
  eventStatus,
  fillContainer = false,
  periodBoundaries,
  homeTeamColor,
  awayTeamColor,
  homeTeamLogo,
  awayTeamLogo,
  homeTeamAbbrev,
  awayTeamAbbrev,
  onActivePointChange,
  onRenderedDomain,
  chartStartTime,
  chartEndTime,
  sharedTicks,
  chartLabelFormat,
  externalTimeRange,
  onTimeRangeChange,
  completedAt,
  awayWithheld = false,
}: OddsChartProps) {
  // #3419: the axis is categorical on this label, so it must be spelled the
  // same way the parent spelled its ticks. Absent a parent domain the window is
  // this chart's own min..max, which is what the 12-hour default assumes.
  const labelFormat = chartLabelFormat ?? CATEGORY_LABEL_FORMAT;
  const isClosed = eventStatus === "closed" || eventStatus === "completed";
  const { track } = useAnalyticsContext();

  const hasPostStartData = useMemo(() => {
    if (!commenceTime) return false;
    const cutoffTime = parseISO(commenceTime);
    // Check sportsbook history
    if (history?.some((point) => parseISO(point.timestamp) >= cutoffTime)) return true;
    // Check win prob history (ESPN, Kalshi, stat model, etc.)
    if (winProbHistory) {
      for (const pts of Object.values(winProbHistory)) {
        if (pts?.some((p) => parseISO(p.timestamp) >= cutoffTime)) return true;
      }
    }
    // Check ESPN history
    if (espnHistory?.some((p) => parseISO(p.timestamp) >= cutoffTime)) return true;
    return false;
  }, [history, winProbHistory, espnHistory, commenceTime]);

  const defaultTimeRange: TimeRange =
    (isClosed || isLive) && hasPostStartData ? "live" : "all";
  const [internalTimeRange, setInternalTimeRange] = useState<TimeRange>(defaultTimeRange);

  // Use external time range when provided (syncs both charts), fall back to internal
  const timeRange = externalTimeRange ?? internalTimeRange;
  const handleTimeRangeChange = (range: TimeRange) => {
    if (onTimeRangeChange) onTimeRangeChange(range);
    else setInternalTimeRange(range);
  };

  // Sync timeRange when data loads asynchronously — useState only uses
  // its initial value on mount, so if history arrives after first render
  // the default stays "all" even when it should be "live"
  const [hasUserOverridden, setHasUserOverridden] = useState(false);

  // The 50%-crossing diamonds are OFF by default (L2-131): they clutter the one
  // clean blend line. A toggle surfaces them for the games where they tell a story.
  const [showCrossings, setShowCrossings] = useState(false);

  // Source legend collapses to "Bain Luck + N sources" by default (L2-163 Item 1,
  // Ruling 1/4): the blend is labeled and dominant; the faint source lines stay
  // unlabeled until the reader expands the legend (or isolates one via hover).
  const [legendExpanded, setLegendExpanded] = useState(false);
  useEffect(() => {
    if (!hasUserOverridden && !externalTimeRange && defaultTimeRange === "live") {
      setInternalTimeRange("live");
    }
  }, [defaultTimeRange, hasUserOverridden, externalTimeRange]);

  // For "Since Start" mode, use commenceTime directly as the start cutoff.
  // Previously used a "smartStartTime" that scanned for the first 2% odds
  // change — but with sparse betting data (one point every ~30 min), this
  // often skipped 1-2 hours past the actual game start, showing 6:20 PM
  // instead of 4:30 PM for a game that started at 4:30 PM.
  // commenceTime is the actual game start from ESPN/StatPal/Odds API —
  // use it directly.

  // Determine chart end boundary for completed games.
  // Use last game data point (ESPN/odds), NOT completedAt which is a backend
  // processing timestamp often 30-45 minutes after the game actually ended.
  const smartEndTime = useMemo(() => {
    if (!isClosed) return null;

    const gameEndCandidates: Date[] = [];

    // ESPN history — most reliable game-end signal
    if (espnHistory && espnHistory.length > 0) {
      gameEndCandidates.push(parseISO(espnHistory[espnHistory.length - 1].timestamp));
    }

    // Game-end data sources only — sportsbooks/prediction markets poll late
    const GAME_END_SOURCES = new Set(["espn", "stat_model", "fangraphs", "mlb"]);
    if (winProbHistory) {
      for (const [source, points] of Object.entries(winProbHistory)) {
        if (points.length > 0 && GAME_END_SOURCES.has(source)) {
          gameEndCandidates.push(parseISO(points[points.length - 1].timestamp));
        }
      }
    }

    if (gameEndCandidates.length > 0) {
      const latestGameEnd = gameEndCandidates.reduce((a, b) => (a > b ? a : b));

      // Also check sportsbook data — if it extends slightly beyond game-end
      // sources, include it. This prevents premature cutoff when ESPN data
      // is sparse (e.g., baseball chart cutting off at 8th inning while
      // sportsbooks have data through the 9th).
      let endTime = latestGameEnd;
      const MAX_EXTENSION_MS = 10 * 60 * 1000; // 10 min max extension
      if (history && history.length > 0) {
        const lastBetting = parseISO(history[history.length - 1].timestamp);
        if (lastBetting > latestGameEnd && lastBetting.getTime() - latestGameEnd.getTime() <= MAX_EXTENSION_MS) {
          endTime = lastBetting;
        }
      }

      // End AT the final snapshot — no trailing buffer (L2-131 / gotcha #22).
      // The old +5 min pad forward-filled a flat tail that read like the game
      // kept going after it ended.
      return new Date(endTime.getTime());
    }

    // No game-end sources — end at the last sportsbook snapshot.
    if (history && history.length > 0) {
      const lastBetting = parseISO(history[history.length - 1].timestamp);
      return new Date(lastBetting.getTime());
    }

    // Last resort: completedAt (backend timestamp, not ideal)
    if (completedAt) {
      return new Date(parseISO(completedAt).getTime());
    }

    return null;
  }, [isClosed, completedAt, espnHistory, winProbHistory, history]);

  /**
   * #6987 — THE END CUTOFF IS NOT A PROPERTY OF THE RANGE.
   *
   * `smartEndTime` answers "when did this game actually end". Only the START of
   * the window is a range choice — "All" opens before kick-off, "Since Start"
   * opens at it — because a game ends once, whichever tab you are looking at.
   *
   * It used to be applied inside the `timeRange !== "all"` arm of all five
   * filters below, so "All" drew every point the venues kept quoting after the
   * whistle. Measured on production 2026-09-19 on /events/14638896 (Chiefs
   * 31-10 Broncos, FINAL): ESPN, the stat model and the sportsbooks all stop at
   * 03:16Z with the home side on an exact `1.0`, while Kalshi (`0.99`) and
   * Polymarket (`0.9995`) poll for ten more minutes — which the backend blends
   * into ten trailing `aggregate_line` minutes at `0.999`. So the callout, which
   * reads the last drawn point of `primarySeriesKey`, ended on `1.0` in "Since
   * Start" and printed `100%`, and ended on `0.999` in "All" and printed
   * `>99%`. Not one point served two ways — two different points ten minutes
   * apart, with the tab a reader happened to land on deciding whether the chart
   * was willing to say the Chiefs had won.
   *
   * `GAME_END_SOURCES` above already encodes the reason: prediction markets
   * quote past the final whistle, which is exactly why they are excluded from
   * deriving the end. And `computeSharedChartDomain` already ends a completed
   * game's X-AXIS there in BOTH ranges, so this is the ink catching up with the
   * axis it is drawn on, not a new policy. The flat post-final tail is the one
   * L2-131 / gotcha #22 removed from the other end ("no trailing buffer — the
   * old +5 min pad forward-filled a flat tail that read like the game kept
   * going after it ended"); "All" simply never reached that code.
   *
   * 🔴 THE FLOOR IS LOAD-BEARING, AND IT IS WHY THIS IS A MEMO AND NOT A `&&`.
   * "All" is the window the chart RESETS TO when the live one draws nothing
   * (#6349, `nothingToDrawInLiveWindow`) — nothing rescues an empty "All". The
   * `completedAt` last-resort branch above is a backend processing timestamp
   * that can precede the data entirely (on /events/15300276 the same class of
   * field is a ticker-derived midnight 15h56m before the first point), and the
   * sportsbook-tail branch can too on a game whose only in-play series is a
   * prediction market. A cutoff with no point at or before it would not trim a
   * tail, it would delete the journey — so it is discarded, the same remedy and
   * the same reasoning as `computeSharedChartDomain`'s own FLOOR.
   */
  const rangeEndTime = useMemo(() => {
    if (!smartEndTime) return null;
    const endMs = smartEndTime.getTime();
    const survives = (points?: { timestamp: string }[] | null): boolean =>
      !!points?.some((point) => parseISO(point.timestamp).getTime() <= endMs);
    if (survives(history)) return smartEndTime;
    if (survives(espnHistory)) return smartEndTime;
    if (survives(aggregateLine)) return smartEndTime;
    for (const points of Object.values(winProbHistory ?? {})) {
      if (survives(points)) return smartEndTime;
    }
    for (const points of Object.values(bookmakerHistory ?? {})) {
      if (survives(points)) return smartEndTime;
    }
    return null;
  }, [
    smartEndTime,
    history,
    espnHistory,
    aggregateLine,
    winProbHistory,
    bookmakerHistory,
  ]);

  /**
   * #7161 — THE CAP REACHED THE AXIS AND NEVER REACHED THE INK.
   *
   * The start of the window is the one the PARENT computed, in both tabs, and
   * only falls back to `commenceTime` when no parent supplied one.
   *
   * `computeSharedChartDomain` caps a completed game's "All" start to two hours
   * before kick-off, and builds `sharedTicks` and the `h:mm a` label format on
   * THAT window — deliberately, because a sub-12h window does not need a
   * date-qualified label (L2-163 Item 2c). But the "All" arm here passed `null`
   * for the start, so `chartData` kept every point the payload served while the
   * axis described five hours of it.
   *
   * Measured on production 2026-09-19, /events/14638896 (Chiefs 31-10 Broncos,
   * FINAL, 390px): the served series open 2026-05-12 and 4,017 of 4,607
   * `aggregate_line` points — 87% — fall before the day of the game. So the
   * categorical XAxis carried four MONTHS of categories under a format unique
   * only inside twelve hours, every tick string matched the FIRST category
   * bearing it, and the axis rendered `7:00 PM` at x=21 with `3:15 PM` at
   * x=257. A reader is told the game ran backwards. The ink agreed: 96% of the
   * drawn line's width was flat pre-season drift and the game itself was one
   * spike at the right edge, inside a y-axis (60–80%) scaled by the months, not
   * by the match.
   *
   * 🔴 THE CONTROL WAS ALREADY ON THE PAGE. `ScoreDifferentialChart` prunes its
   * points to `chartStartTime`/`chartEndTime` and, in the same frame, on the same
   * window, drew `3:15 PM · 5:00 PM · 7:00 PM · 8:16 PM` in order. Two charts,
   * one domain, one clipping and one not — which is why this is the ink catching
   * up with the axis it is drawn on, not a new policy.
   *
   * 🔴 THE FLOOR IS LOAD-BEARING, for the same reason `rangeEndTime`'s is. A
   * start cutoff with no point at or after it would not trim a pre-window slab,
   * it would delete the journey — and "All" is the window the chart RESETS TO
   * when the live one draws nothing (#6349), so nothing rescues an empty "All".
   * `computeSharedChartDomain` already declines to cap when nothing survives the
   * cap, and already widens an inverted window back to the full extent; this is
   * the same test applied where the ink is cut, so a domain arriving from
   * anywhere cannot blank the chart.
   */
  const rangeStartTime = useMemo(() => {
    const parentStart = chartStartTime ? parseISO(chartStartTime) : null;
    const fallback =
      timeRange === "all"
        ? null
        : commenceTime
          ? parseISO(commenceTime)
          : new Date();
    const candidate = parentStart ?? fallback;
    if (!candidate || isNaN(candidate.getTime())) return null;
    const startMs = candidate.getTime();
    const survives = (points?: { timestamp: string }[] | null): boolean =>
      !!points?.some((point) => parseISO(point.timestamp).getTime() >= startMs);
    if (survives(history)) return candidate;
    if (survives(espnHistory)) return candidate;
    if (survives(aggregateLine)) return candidate;
    for (const points of Object.values(winProbHistory ?? {})) {
      if (survives(points)) return candidate;
    }
    for (const points of Object.values(bookmakerHistory ?? {})) {
      if (survives(points)) return candidate;
    }
    return null;
  }, [
    chartStartTime,
    timeRange,
    commenceTime,
    history,
    espnHistory,
    aggregateLine,
    winProbHistory,
    bookmakerHistory,
  ]);

  /**
   * The one window every series is cut to, or `null` when there is nothing to
   * cut. Five filters used to spell this rule out for themselves and the end
   * half had already drifted out of one of them (#6987) — a rule written at
   * five call sites is a rule that can be wrong at one of them and right at the
   * other four, which is precisely how two tabs came to disagree about the same
   * finished game.
   */
  const inChartRange = useMemo(() => {
    const startMs = rangeStartTime ? rangeStartTime.getTime() : null;
    const endMs = rangeEndTime ? rangeEndTime.getTime() : null;
    if (startMs === null && endMs === null) return null;
    return (timestamp: string): boolean => {
      const t = parseISO(timestamp).getTime();
      if (startMs !== null && t < startMs) return false;
      if (endMs !== null && t > endMs) return false;
      return true;
    };
  }, [rangeStartTime, rangeEndTime]);

  // Filter history to the chart window
  const filteredHistory = useMemo(() => {
    if (!history || history.length === 0) return [];
    if (!inChartRange) return history;
    return history.filter((point) => inChartRange(point.timestamp));
  }, [history, inChartRange]);

  // Filter bookmaker history to the chart window
  const filteredBookmakerHistory = useMemo(() => {
    if (!bookmakerHistory || Object.keys(bookmakerHistory).length === 0)
      return {};
    if (!inChartRange) return bookmakerHistory;
    const filtered: Record<string, BookmakerHistoryPoint[]> = {};
    for (const [bookmaker, points] of Object.entries(bookmakerHistory)) {
      filtered[bookmaker] = points.filter((point) =>
        inChartRange(point.timestamp)
      );
    }
    return filtered;
  }, [bookmakerHistory, inChartRange]);

  // Build the list of all sources to display (betting + model sources)
  const resolvedSources = useMemo((): ResolvedSource[] => {
    const sources: ResolvedSource[] = [];

    // Always include betting odds as a labeled source
    if (history && history.length > 0) {
      const bettingConfig = FALLBACK_SOURCE_CONFIG.betting;
      sources.push({
        key: "betting",
        dataKey: "homeDelta",
        displayName: bettingConfig.display_name,
        color: bettingConfig.color,
        dashPattern: bettingConfig.dash_pattern,
        type: bettingConfig.type,
        snapshotCount: history.length,
      });
    }

    if (winProbHistory && Object.keys(winProbHistory).length > 0) {
      for (const [key, points] of Object.entries(winProbHistory)) {
        if (points.length === 0) continue;

        // Hide stat model when most data points used wall-clock estimation
        // (imprecise fallback for games where ESPN name matching fails).
        if (key === "stat_model" && points.length >= 3) {
          const wallClockCount = points.filter(
            (p) => p.game_state?.time_source === "wall_clock"
          ).length;
          if (wallClockCount > points.length * 0.5) continue;
        }

        const meta = winProbSources?.[key];
        const fallback = FALLBACK_SOURCE_CONFIG[key];
        sources.push({
          key,
          dataKey: `wp_${key}_delta`,
          // #2442: registry first. The payload serves `"Betting Odds"` for
          // the sportsbook source, and a runtime string is invisible to the
          // shipped-copy scan — so the name is resolved here, not trusted.
          displayName: sourceLabel(key, meta?.display_name ?? fallback?.display_name ?? key),
          color: meta?.color ?? fallback?.color ?? "#6b7280",
          dashPattern: meta?.dash_pattern ?? fallback?.dash_pattern ?? "4 4",
          type: meta?.type ?? fallback?.type ?? "model",
          snapshotCount: points.length,
        });
      }
    } else if (espnHistory && espnHistory.length > 0) {
      sources.push({
        key: "espn",
        dataKey: "espnDelta",
        displayName: "ESPN",
        color: "#f97316",
        dashPattern: "6 3",
        type: "model",
        snapshotCount: espnHistory.length,
      });
    }

    return sources;
  }, [history, winProbHistory, winProbSources, espnHistory]);

  // Non-betting sources
  const nonBettingSources = useMemo(
    () => resolvedSources.filter((s) => s.key !== "betting"),
    [resolvedSources]
  );

  // ── Display mode detection ──
  // Multi-source mode: when we have at least 1 non-betting source with data
  const isMultiSource = nonBettingSources.length > 0;

  // Filter win prob history to the chart window
  const filteredWinProbHistory = useMemo(() => {
    if (!winProbHistory || Object.keys(winProbHistory).length === 0) return {};
    if (!inChartRange) return winProbHistory;
    const filtered: Record<string, WinProbHistoryPoint[]> = {};
    for (const [source, points] of Object.entries(winProbHistory)) {
      filtered[source] = points.filter((point) =>
        inChartRange(point.timestamp)
      );
    }
    return filtered;
  }, [winProbHistory, inChartRange]);

  // Filter ESPN history (legacy fallback) to the chart window
  const filteredEspnHistory = useMemo(() => {
    if (!espnHistory || espnHistory.length === 0) return [];
    if (!inChartRange) return espnHistory;
    return espnHistory.filter((point) => inChartRange(point.timestamp));
  }, [espnHistory, inChartRange]);

  // Filter aggregate line — use commenceTime (not smartStartTime) because the
  // aggregate line is already a clean backend-computed weighted median without
  // the noisy flat pre-game data that smartStartTime is designed to skip.
  const filteredAggregateLine = useMemo(() => {
    if (!aggregateLine || aggregateLine.length === 0) return [];
    if (!inChartRange) return aggregateLine;
    return aggregateLine.filter((point) => inChartRange(point.timestamp));
  }, [aggregateLine, inChartRange]);

  // ── #1003: the blend line is the BACKEND blend, or it is nothing ──
  // `bainLuckDelta` used to fall back to an unweighted frontend mean of whatever
  // per-source series happened to be loaded, and still rendered under the
  // "Bain Luck (aggregated)" name. An unweighted mean is NOT the blend —
  // production weights are betting 3.0, ESPN 1.5, stat_model 1.0,
  // Kalshi/Polymarket/MLB 0.8 — so that line, its tooltip row, its callout and
  // the live hero it feeds via `onActivePointChange` could all print a number
  // the hero and the Discover card never show. Standing ruling #1 is
  // card == hero == chart, one number per question, and a fabricated mean
  // wearing the blend's name is the 57-vs-20 bug with better manners.
  //
  // The two gates disagreed by construction, which is why the path existed:
  // the backend emits `aggregate_line` only when `len(agg_sources) > 1`
  // (bookmaker consensus counts as one), while the chart drew the aggregated
  // line whenever `nonBettingSources.length > 0` (bookmakers do not count).
  //
  // Now: no backend blend, no blend line. The chart falls back to the same
  // primary series it uses in sportsbooks-only mode, which is a real measured
  // source that is labelled as itself.
  const showBlendLine = isMultiSource && filteredAggregateLine.length > 0;

  // The primary series every "what is the number here" reader uses: the fill
  // gradient, the lead-change count, the current-probability callout, and the
  // hover payload sent to the live hero. Single definition so those four can
  // never disagree about which line the chart is actually about.
  const primarySeriesKey: string = showBlendLine
    ? "bainLuckDelta"
    : history && history.length > 0
      ? "homeDelta"
      : nonBettingSources.length > 0
        ? nonBettingSources[0].dataKey
        : "homeDelta";

  /**
   * The primary series' value at one chart point, or null where it has none
   * (#3425).
   *
   * The three readers below each used to test the raw property against `null`,
   * which is not the same question. `ensurePoint` seeds only `homeDelta`,
   * `espnDelta` and `bainLuckDelta`, so when `primarySeriesKey` is a per-source
   * key — every single-source chart, since that branch picks
   * `nonBettingSources[0].dataKey` — a gap-filled minute carries no such
   * property at all and reads `undefined`. Forward-fill does not cover it
   * either: minutes BEFORE the first real point have no `lastKnown` to carry,
   * and a shared domain routinely opens before the data (a ticker-derived
   * `commence_time` put 15h56m of them in front of /events/15300276).
   *
   * `undefined !== null` is true, so the old guards admitted it and a
   * `(v): v is number` annotation asserted it was a number. `Math.max` of that
   * is NaN, which is how every event page emitted
   * `<stop offset="NaN">` — eight-plus console errors a load, and a fill the
   * browser then declined to paint.
   */
  const primaryValueAt = (pt: ChartDataPoint): number | null => {
    const v = pt[primarySeriesKey];
    return typeof v === "number" && Number.isFinite(v) ? v : null;
  };

  const useNewWinProbData = Object.keys(filteredWinProbHistory).length > 0;
  const bookmakers = useMemo(
    () => Object.keys(filteredBookmakerHistory),
    [filteredBookmakerHistory]
  );

  /**
   * Every ChartDataPoint key this chart can draw as a line.
   *
   * One list, two readers: the forward-fill below carries these keys across
   * gap-filled minutes, and `filteredPeriodBoundaries` uses them to find where
   * the ink actually starts. Those two must agree — a key the chart plots but
   * the boundary guard does not know about would let a chip sit left of the
   * line, and a key the guard counts but nothing plots would put one over blank
   * axis (CERT-1984). Keeping them one definition is the guarantee.
   */
  const plottedProbKeys = useMemo(() => {
    const keys = ["homeDelta", "bainLuckDelta", "espnDelta"];
    for (const source of nonBettingSources) keys.push(source.dataKey);
    for (const bookmaker of Object.keys(filteredBookmakerHistory)) {
      keys.push(`${bookmaker}_delta`);
    }
    return keys;
  }, [nonBettingSources, filteredBookmakerHistory]);

  // Transform data: convert probabilities to delta from 50%
  // Bucket by minute so each category label is unique (see `labelFormat`,
  // #3419) — required for
  // Recharts ReferenceLine (period markers) to match categorical XAxis values.
  const chartData: ChartDataPoint[] = useMemo(() => {
    const dataMap = new Map<string, ChartDataPoint>();

    const ensurePoint = makeEnsurePoint<ChartDataPoint>(dataMap, () => ({
      homeDelta: null,
      espnDelta: null,
      bainLuckDelta: null,
    }), labelFormat);

    // Add aggregate data points (betting odds consensus). Values are the raw
    // home win probability on a 0–100 axis (single-axis, not ±50 delta).
    for (const point of filteredHistory) {
      const delta =
        point.home_probability !== null
          ? homeProbToChartAxis(point.home_probability)
          : null;

      const dp = ensurePoint(point.timestamp);
      dp.homeDelta = delta;

      // Expand valid_until
      if (point.valid_until) {
        const endTime = parseISO(point.valid_until);
        const startTime = parseISO(point.timestamp);
        if (endTime.getTime() - startTime.getTime() > 60000) {
          const endDp = ensurePoint(point.valid_until);
          if (endDp.homeDelta === null) endDp.homeDelta = delta;
        }
      }
    }

    // Add bookmaker lines (single line per bookmaker - home prob delta)
    for (const [bookmaker, points] of Object.entries(
      filteredBookmakerHistory
    )) {
      for (const point of points) {
        const delta =
          point.home_probability !== null
            ? homeProbToChartAxis(point.home_probability)
            : null;

        const dp = ensurePoint(point.timestamp);
        dp[`${bookmaker}_delta`] = delta;

        // Expand valid_until
        if (point.valid_until) {
          const endTime = parseISO(point.valid_until);
          const startTime = parseISO(point.timestamp);
          if (endTime.getTime() - startTime.getTime() > 60000) {
            const endDp = ensurePoint(point.valid_until);
            if (endDp[`${bookmaker}_delta`] === undefined) {
              endDp[`${bookmaker}_delta`] = delta;
            }
          }
        }
      }
    }

    // Ensure all bookmaker keys exist on all data points
    const allBookmakers = Object.keys(filteredBookmakerHistory);
    const allPoints = Array.from(dataMap.values());
    for (const point of allPoints) {
      for (const bookmaker of allBookmakers) {
        if (point[`${bookmaker}_delta`] === undefined) {
          point[`${bookmaker}_delta`] = null;
        }
      }
    }

    // Add win probability source data (new multi-source or legacy ESPN)
    if (useNewWinProbData) {
      for (const [sourceKey, points] of Object.entries(filteredWinProbHistory)) {
        const dataKey = `wp_${sourceKey}_delta`;
        for (const point of points) {
          const delta =
            point.home_probability !== null
              ? homeProbToChartAxis(point.home_probability)
              : null;

          const dp = ensurePoint(point.timestamp);
          dp[dataKey] = delta;
        }
      }

      // Ensure all source keys exist on all data points
      const allDataPoints = Array.from(dataMap.values());
      for (const point of allDataPoints) {
        for (const source of nonBettingSources) {
          if (point[source.dataKey] === undefined) {
            point[source.dataKey] = null;
          }
        }
      }
    } else {
      // Legacy ESPN data
      for (const point of filteredEspnHistory) {
        const delta =
          point.home_probability !== null
            ? homeProbToChartAxis(point.home_probability)
            : null;

        const dp = ensurePoint(point.timestamp);
        dp.espnDelta = delta;
      }
    }

    // ── Compute Bain Luck aggregated line (multi-source mode) ──
    // The backend aggregate_line is a weighted median with staleness decay —
    // the same blend the hero and the Discover card render.
    // #1003: ONLY the backend-computed aggregate line. There is deliberately no
    // frontend fallback — see `showBlendLine` above. If the backend did not
    // compute a blend, `bainLuckDelta` stays null and no blend line is drawn.
    if (showBlendLine) {
      for (const point of filteredAggregateLine) {
        const delta = homeProbToChartAxis(point.home_probability);
        const dp = ensurePoint(point.timestamp);
        dp.bainLuckDelta = delta;
      }
    }

    // ── Enrich chart points with game state (score, period, clock) ──
    // Sources: ESPN history (has score/period/clock) and win_prob_history game_state
    // ESPN history is the richest source for game context
    for (const snap of filteredEspnHistory) {
      const dp = dataMap.get(toMinuteKey(snap.timestamp));
      if (dp) {
        if (snap.home_score != null) dp._homeScore = snap.home_score;
        if (snap.away_score != null) dp._awayScore = snap.away_score;
        if (snap.period) dp._period = snap.period;
        if (snap.game_clock) dp._clock = snap.game_clock;
      }
    }

    // Win prob history game_state as secondary source
    if (useNewWinProbData) {
      for (const points of Object.values(filteredWinProbHistory)) {
        for (const pt of points) {
          const gs = pt.game_state;
          if (!gs) continue;
          const dp = dataMap.get(toMinuteKey(pt.timestamp));
          if (!dp) continue;
          if (dp._homeScore == null && gs.home_score != null)
            dp._homeScore = gs.home_score as number;
          if (dp._awayScore == null && gs.away_score != null)
            dp._awayScore = gs.away_score as number;
          if (!dp._period && gs.period) dp._period = gs.period as string;
          if (!dp._clock && gs.clock) dp._clock = gs.clock as string;
        }
      }
    }

    // Map scoring plays onto chart data points
    if (scoringPlays && scoringPlays.length > 0) {
      const sortedPoints = Array.from(dataMap.values()).sort(
        (a, b) => parseISO(a.timestamp).getTime() - parseISO(b.timestamp).getTime()
      );
      for (const play of scoringPlays) {
        if (!play.timestamp) continue;
        const playTime = parseISO(play.timestamp).getTime();
        let closestIdx = 0;
        let closestDist = Infinity;
        for (let i = 0; i < sortedPoints.length; i++) {
          const dist = Math.abs(parseISO(sortedPoints[i].timestamp).getTime() - playTime);
          if (dist < closestDist) {
            closestDist = dist;
            closestIdx = i;
          }
        }
        // Only attach if within 2 minutes
        if (closestDist < 120000) {
          sortedPoints[closestIdx]._scoringPlay = play;
        }
      }
    }

    // Fill missing minutes for uniform x-axis spacing.
    // Both OddsChart and ScoreDifferentialChart use categorical XAxis where
    // each category gets equal pixel width. Without filling gaps, the charts
    // have non-linear x-axes (chunks of time appear compressed or expanded).
    // Filling every minute ensures linear time and identical category sets.
    {
      let first: Date | null = null;
      let last: Date | null = null;

      if (chartStartTime && chartEndTime) {
        // Use shared domain from parent for perfect chart alignment
        first = parseISO(chartStartTime);
        last = parseISO(chartEndTime);
      } else {
        const allTimestamps = Array.from(dataMap.keys()).sort();
        if (allTimestamps.length >= 2) {
          first = parseISO(allTimestamps[0]);
          last = parseISO(allTimestamps[allTimestamps.length - 1]);
        }
      }

      if (first && last) {
        fillMinuteGaps(first, last, ensurePoint);
      }
    }

    // Ensure period boundary timestamps exist as chart data points.
    // ReferenceLine on a categorical x-axis only renders when the x value
    // matches an existing category. Without this, boundaries that fall
    // between data points silently vanish.
    if (periodBoundaries && periodBoundaries.length > 0) {
      for (const b of periodBoundaries) {
        ensurePoint(b.timestamp);
      }
    }

    // Forward-fill probability data: carry last known value through gap-filled
    // minutes so lines appear continuous instead of showing visual gaps.
    // Without this, gap-filled minutes have null deltas and Recharts must rely
    // on connectNulls to draw a thin interpolation — which can look broken
    // when there are many consecutive nulls (e.g., sparse MLB betting data).
    // Forward-filling is semantically correct: the probability IS the last
    // known value until a new data point arrives.
    const sorted = Array.from(dataMap.values()).sort(
      (a, b) => parseISO(a.timestamp).getTime() - parseISO(b.timestamp).getTime()
    );

    // Every key this chart draws (see `plottedProbKeys`) gets forward-filled.
    const probKeys = plottedProbKeys;

    const lastKnown: Record<string, number | null> = {};
    for (const key of probKeys) {
      lastKnown[key] = null;
    }
    for (const pt of sorted) {
      for (const key of probKeys) {
        const val = pt[key];
        if (typeof val === "number") {
          lastKnown[key] = val;
        } else if (lastKnown[key] !== null) {
          pt[key] = lastKnown[key];
        }
      }
    }

    // Forward-fill game state: carry most recent score/period/clock to subsequent points
    let lastScore: { home: number | null; away: number | null } = { home: null, away: null };
    let lastPeriod: string | null = null;
    let lastClock: string | null = null;
    for (const pt of sorted) {
      if (pt._homeScore != null) lastScore.home = pt._homeScore as number;
      else pt._homeScore = lastScore.home;
      if (pt._awayScore != null) lastScore.away = pt._awayScore as number;
      else pt._awayScore = lastScore.away;
      if (pt._period) lastPeriod = pt._period as string;
      else pt._period = lastPeriod;
      // Track clock exactness: a point that carries its OWN clock is exact; a
      // gap-filled minute inherits the last clock and must be flagged approximate
      // so the readout never shows a stale carry-forward as if live (#925).
      if (pt._clock) {
        lastClock = pt._clock as string;
        pt._clockApprox = false;
      } else {
        pt._clock = lastClock;
        pt._clockApprox = lastClock != null;
      }
    }

    return sorted;
  // #1003: `resolvedSources` and `isMultiSource` dropped — both were read only
  // by the naive-mean fallback that no longer exists. `showBlendLine` added: it
  // now decides whether `bainLuckDelta` is written at all. (`timeRange` is also
  // unread here, but it predates this change and is left alone.)
  }, [filteredHistory, filteredBookmakerHistory, filteredWinProbHistory, filteredEspnHistory, useNewWinProbData, nonBettingSources, showBlendLine, filteredAggregateLine, scoringPlays, timeRange, periodBoundaries, plottedProbKeys]);

  // Report the chart's actual rendered time domain to parent so
  // ScoreDifferentialChart can match its x-axis exactly.
  useEffect(() => {
    if (!onRenderedDomain || chartData.length === 0) return;
    const first = chartData[0].timestamp;
    const last = chartData[chartData.length - 1].timestamp;
    onRenderedDomain(first, last);
  }, [chartData, onRenderedDomain]);



  /**
   * The extent of the DRAWN LINE — the first and last category actually
   * carrying a plotted value — as opposed to `chartData`'s extent, which also
   * holds null-valued odds buckets, gap-filled minutes and marker timestamps
   * this component inserts itself (CERT-1984).
   */
  const drawnExtent = useMemo(() => {
    const isDrawn = (p: ChartDataPoint) =>
      plottedProbKeys.some((key) => typeof p[key] === "number");
    const first = chartData.findIndex(isDrawn);
    if (first === -1) return null;
    let last = chartData.length - 1;
    while (last > first && !isDrawn(chartData[last])) last--;
    return {
      firstIdx: first,
      lastIdx: last,
      startMs: parseISO(chartData[first].timestamp).getTime(),
      endMs: parseISO(chartData[last].timestamp).getTime(),
    };
  }, [chartData, plottedProbKeys]);

  // #6349 — THE "SINCE START" SELF-RESET IS AN EFFECT, NOT A RENDER-TIME CALL.
  // It used to sit inside the early return below and call `handleTimeRangeChange`
  // — which on the event page is the PARENT's setter — in the middle of this
  // component's render. That was harmless only because the guard around it could
  // never be true once a shared domain was supplied (see the early return). The
  // honest `drawnExtent` test makes it reachable, and reachable setState-during-
  // render of another component is a React warning and an ordering hazard, so it
  // moves here before anything can return.
  const nothingToDrawInLiveWindow =
    !drawnExtent && timeRange === "live" && !!history && history.length > 0;
  useEffect(() => {
    if (!nothingToDrawInLiveWindow) return;
    handleTimeRangeChange("all");
    setHasUserOverridden(false);
    // `handleTimeRangeChange` is re-created every render; the flag above is the
    // real trigger and it goes false as soon as the wider window draws.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nothingToDrawInLiveWindow]);

  // Compute "Game Start" reference line time (formatted to match chart categories)
  const gameStartTime = useMemo(() => {
    if (!commenceTime || chartData.length === 0 || !drawnExtent) return null;
    const startMs = parseISO(commenceTime).getTime();
    // Bound against the DRAWN LINE, not `chartData`'s extent (CERT-1984, and
    // #3419 for this marker). The old test used chartData[0], which is the
    // chart's own gap fill — and since #3419 made that fill inclusive of the
    // shared domain's start, `commence_time` became chartData[0] BY
    // CONSTRUCTION, so the test could no longer fail. That is the same
    // circularity CERT-1984 removed from the period markers: a marker creates
    // the very category it is then judged to be inside.
    //
    // It matters because `commence_time` is exactly the field that is wrong
    // when a start was never reported. On /events/15300276 it is a
    // ticker-derived midnight 15h56m before the first Kalshi point, so a
    // "Start" flag pinned to it told the reader the match began on a night it
    // had not yet begun. No ink at that instant, no claim about it.
    if (startMs < drawnExtent.startMs || startMs > drawnExtent.endMs) return null;
    // Round to minute for categorical match
    const d = parseISO(commenceTime);
    d.setSeconds(0, 0);
    return format(d, labelFormat);
  }, [commenceTime, chartData, labelFormat, drawnExtent]);

  // Filter period boundaries to match chart time range, deduplicate close markers,
  // and alternate label positions to prevent overlapping text.
  const filteredPeriodBoundaries = useMemo(() => {
    if (!periodBoundaries || periodBoundaries.length === 0 || chartData.length === 0) return [];

    // Bound against the DRAWN LINE, not the chart's data extent (CERT-1984).
    //
    // `chartData` is not the line. It holds a row per odds bucket even when the
    // aggregate probability came back null, plus gap-filled minutes, plus the
    // boundary timestamps this component itself inserts so Recharts can match a
    // categorical ReferenceLine. Measuring the extent of THAT is circular: a
    // boundary over an empty plot creates the very category it is then judged to
    // be inside, which is how a "1H" chip came to hang over a blank chart.
    //
    // So find the first and last point carrying a value we actually plot. The
    // server drops markers no chart can place, but it cannot know which of the
    // two charts sharing this array is the blank one — only we do. Shared with
    // the "Start" marker via `drawnExtent` so the two bounds cannot drift.
    if (!drawnExtent) return [];
    const chartStart = drawnExtent.startMs;
    const chartEnd = drawnExtent.endMs;

    // Label spacing below is a PIXEL problem, so it is measured on the x-axis —
    // the full data extent — and not on the drawn subset above. Narrowing it to
    // the ink would shrink `minSpacing` and let back the label smear UX-P022 fixed.
    const chartDuration =
      parseISO(chartData[chartData.length - 1].timestamp).getTime() -
      parseISO(chartData[0].timestamp).getTime();

    // Minimum spacing before two markers are collapsed into one.
    //
    // UX-P022: this used to be `max(duration * 3%, 2 minutes)`. Label collision
    // is a function of PIXELS, but the 2-minute floor is a function of TIME, and
    // the two only agree at one chart length. On a 3-hour game 2 minutes is
    // ~1% of the width and far too tight; on a 21-minute live game it is ~10% of
    // the width, so two markers 2 minutes apart were both kept and their labels
    // printed on top of each other — the unreadable "T9|1" smear on a live Red
    // Sox chart.
    //
    // Spacing is now purely proportional, so it means the same thing at every
    // chart length: markers must be at least 7% of the visible width apart, which
    // is comfortably wider than a 2–4 character period label at 11px.
    //
    // The rule itself now lives in `dedupePeriodLabels` and is shared with the
    // score differential chart below, which carried a private pre-UX-P022 copy
    // and smeared its inning labels (latency/467). Behaviour here is unchanged.
    const filtered = periodBoundaries
      .filter((b) => {
        const t = parseISO(b.timestamp).getTime();
        if (t < chartStart || t > chartEnd) return false;
        // Drop any "Final"-like boundary — the single explicit Final marker below
        // owns the game-end label, so there is exactly one (L2-131).
        if (/^(final|ft|f|full\s*time)$/i.test(b.label.trim())) return false;
        return true;
      })
      .sort((a, b) => parseISO(a.timestamp).getTime() - parseISO(b.timestamp).getTime());

    // Deduplicate: when two boundaries are too close, keep the later one
    // (e.g., "End of Q2" and "HT" at nearly the same time -> keep "HT")
    const deduped = dedupePeriodLabels(filtered, chartDuration);

    // #6882: a pair can survive the collapse above and STILL be unreadable —
    // NFL's `HT → Q3` clears 7% by 1.6 minutes and then paints 3.4px apart at
    // 390px. Collapsing it would delete `HT` (the rule keeps the LATER marker),
    // so the later label drops a row instead and both stay. Layout only; the set
    // of markers drawn is exactly what `dedupePeriodLabels` returned.
    const rowed = assignPeriodLabelRows(deduped, chartDuration);

    // #7371: every label grows RIGHT out of its rule (UX-P022 — anchoring them
    // all the same way is what makes the gap between two markers the space
    // available to the first one's text). The one marker that cannot is the one
    // sitting ON the last category: a live game's newest half-inning starts at
    // the newest data, so `T10` grew out of the svg and reached the page as a
    // bare `T`. `anchorPeriodLabels` flips exactly those and spaces the flip;
    // it is shared with the score differential chart, which clips identically.
    //
    // The right rule is the LAST CATEGORY, not the drawn extent: a categorical
    // axis places a marker by index, and `chartData`'s last row is the column
    // the rule is painted on.
    const anchored = anchorPeriodLabels(
      rowed,
      chartDuration,
      parseISO(chartData[chartData.length - 1].timestamp).getTime(),
    );

    return anchored.map((b) => ({
      ...b,
      time: format(parseISO(b.timestamp), labelFormat),
    }));
  }, [periodBoundaries, chartData, plottedProbKeys, labelFormat, drawnExtent]);

  /**
   * #7134 — how many ROWS of period chips are painted at the top of the plot.
   *
   * Derived from the same rowed list the `<ReferenceLine>` labels are drawn
   * from, so the depth the callout clears and the depth the chips occupy cannot
   * drift apart. `assignPeriodLabelRows` documents why two rows are provably
   * enough; this does not assume it, it counts.
   */
  const periodChipRowCount = useMemo(
    () =>
      filteredPeriodBoundaries.reduce(
        (deepest, b) => Math.max(deepest, ((b as { labelRow?: number }).labelRow ?? 0) + 1),
        0,
      ),
    [filteredPeriodBoundaries],
  );

  // "Final" marker (settled games only): a single vertical line at the last
  // chart category — i.e. the final snapshot, which is now the chart's right
  // edge (buffer removed). Exactly one, deduped against period boundaries above.
  const finalMarkerTime = useMemo(() => {
    if (!isClosed || chartData.length === 0) return null;
    return chartData[chartData.length - 1].time;
  }, [isClosed, chartData]);

  // Single 0–100 win-probability axis (L2-131): the line is the HOME team's win
  // probability read straight up the scale. This replaces the old mirrored ±50
  // dual-axis where the same "80%" appeared both above and below center.
  //
  // #3973: the SCALE is now the window the line lives in rather than the whole
  // 0–100 range — a tennis market that spends its life inside 4 points drew as
  // a horizontal line on the fixed axis. The direction, the meaning of the
  // numbers and the 50% mark are unchanged; only the zoom moves. The rules and
  // the production measurement behind them are in `computeWinProbYAxis`.
  //
  // Fed from `plottedProbKeys` — the same one list the forward-fill and
  // `filteredPeriodBoundaries` read (see its docstring). That is deliberate: a
  // series the chart draws but the axis did not size would be the one that runs
  // off the plot, which is the exact class of bug this is fixing.
  const { domain: yDomain, ticks: yTicks } = useMemo(() => {
    const values: number[] = [];
    for (const point of chartData) {
      for (const key of plottedProbKeys) {
        const v = point[key];
        if (typeof v === "number") values.push(v);
      }
    }
    return computeWinProbYAxis(values);
  }, [chartData, plottedProbKeys]);

  // ── Count the primary series' crossings of the 50% line ──
  //
  // ═══ #4882: THIS IS NOT A LEAD CHANGE, AND IT USED TO SAY IT WAS ═══
  //
  // It counted the same thing it counts now and called the chip "Lead changes".
  // Alex, watching the NFL opener at 13–10: `Lead changes (9)` on a game with
  // about three. A worse one: `/events/15296797` (Banfield v Central, FINAL
  // 1–1) printed **138** — all of them crossings of a fifteen-day PRE-KICKOFF
  // odds line, on a page carrying zero post-kickoff points. At 9-on-3 a reader
  // can believe the number is merely wrong; at 138 on a 1–1 draw it is
  // impossible as a fact about the score, so the chip was reading market churn
  // in in-game vocabulary.
  //
  // So the fix is the NOUN, not the threshold — no tightening of a crossing
  // count makes "lead changes" true of a pre-game price series. Two nouns that
  // look right and are not, both rejected on the record (#4882):
  //   · "Momentum swings" — a match that has not started has no momentum
  //     either. Half the specimens here are pages reading "Starts in 3h".
  //   · "Favorite flips" — true for NFL and tennis, an overclaim on a THREE-WAY
  //     sport, where this axis is home-win% against everything else: home
  //     crossing 50 means more-likely-than-not became less, while the favourite
  //     may be the draw or the away side. The 138 specimen is soccer.
  //
  // ═══ AND THE WORD IS NOT MINE TO PICK: THE HOUSE ALREADY PICKED IT ═══
  //
  // `highlights.py:1312` ruled this exact class under #5439 (T10-1) — *"'Lead
  // change' named a SPORTING event and was produced by a PRICE one … nobody
  // scored, the favourite swapped"* — for a flag fed by the same 50%-crossing
  // count (`TimeSeriesMetrics.lead_changes`). It prints **"Odds flipped"**, and
  // iOS already classifies that string (`EventCardView.swift:531`). So the chip
  // says "Odds flipped" too: one quantity, one name, on the card, the chart and
  // the app. Inventing a second ("Crossed 50%", which was this branch's first
  // answer) would have been correct English and a second vocabulary.
  //
  // Instead of creating a separate data array (which breaks Recharts categorical
  // X-axis domain), we stamp `crossingDelta` directly onto chartData points.
  const crossingCount = useMemo(() => {
    if (chartData.length < 2) return 0;
    const key = primarySeriesKey;
    // Clear any previous stamps
    for (const pt of chartData) {
      delete pt.crossingDelta;
    }
    let count = 0;
    let prevDelta: number | null = null;
    for (const pt of chartData) {
      const delta = primaryValueAt(pt);
      if (delta === null) continue;
      if (prevDelta !== null) {
        // A crossing is the primary series passing the 50% line (0–100 axis).
        if ((prevDelta > 50 && delta <= 50) || (prevDelta < 50 && delta >= 50)) {
          pt.crossingDelta = 50; // Stamp at y=50 (the 50% line)
          count++;
        }
      }
      prevDelta = delta;
    }
    return count;
  }, [chartData, primarySeriesKey]);

  // ── Current probability callout (last non-null data point) ──
  // Stamp `calloutDelta` directly onto the chartData point (same reason as above).
  const currentCallout = useMemo(() => {
    if (chartData.length === 0) return null;
    const key = primarySeriesKey;
    // Clear any previous stamps
    for (const pt of chartData) {
      delete pt.calloutDelta;
    }
    // Walk backwards to find last non-null value
    for (let i = chartData.length - 1; i >= 0; i--) {
      const delta = primaryValueAt(chartData[i]);
      if (delta !== null) {
        const homeProb = delta; // 0–100 axis: the value IS the home probability
        chartData[i].calloutDelta = delta; // Stamp onto chartData point
        // #3892 — ROUND THE PROBABILITY, NOT THE AXIS VALUE.
        //
        // This label sits directly under the hero and, since #3898 pinned the
        // pre-match edge to the blend, prints THE SAME NUMBER. It was rounding
        // the 0–100 axis value, which is `probability * 100` — and that product
        // is not the quoted decimal. `0.575 * 100` is `57.49999999999999`, so
        // `Math.round` gave 57 while the hero's `renderedPercent` gave 58.
        //
        // Read on production 2026-09-08 on `/events/15307463` (Khachanov, a US
        // Open quarter-final quoted at 0.575): hero **58%**, this callout
        // **57%**, one card, one number, two answers. Going back through the
        // axis recovers the decimal the venue actually quoted, so both arms
        // round the same input under the same rule.
        //
        // `chartAxisPercents` rather than the arithmetic inline: it is the
        // tested home of this rule, it derives the second end so a complement
        // pair cannot print 101, and an expression repeated at two call sites
        // is a rule that can drift at one of them.
        const percents = chartAxisPercents(homeProb);
        // NO CALLOUT RATHER THAN A FALLBACK. The first draft of this kept
        // `?? Math.round(homeProb)` for a non-finite axis value, which reads
        // like a safety net and is not one: `Math.round(NaN)` is `NaN`, so the
        // old code drew the literal text "NaN%" in that case. `null` here means
        // the label is not drawn at all, which is the honest answer when there
        // is no number — and it keeps the one rounding rule unduplicated.
        // `homeLabel` is in the guard so the callout below gets a `string`, not
        // a `string | null` it would have to re-check inside a render shape.
        // The four are null together, so this widens nothing.
        if (
          percents.home === null ||
          percents.away === null ||
          percents.homeLabel === null
        ) {
          return null;
        }
        return {
          time: chartData[i].time,
          // #6987 — the minute this callout is anchored to, in UTC. `time` above
          // is the CATEGORY, a locally formatted clock string, so it answers
          // "which tick" and not "which instant" — and it moves with the reader's
          // timezone, which a guard cannot pin. The defect this carries evidence
          // of was two tabs labelling two points ten minutes apart, so the
          // instant is the thing worth exporting.
          timestamp: chartData[i].timestamp,
          delta,
          homeProb: percents.home,
          awayProb: percents.away,
          // #6858 — the PRINTABLE form, carried from the same call that resolved
          // the pair. The integer above stays for anything that measures (the
          // plate is sized off the label's own length, so `<1%` widens it).
          homeLabel: percents.homeLabel,
        };
      }
    }
    return null;
  }, [chartData, primarySeriesKey]);

  // Early return for empty data across ALL sources (not just sportsbook odds)
  // If "Since Start" filter caused empty data, auto-reset to "all"
  //
  // #6349 — `chartData.length === 0` IS NOT "NOTHING TO DRAW", AND ON THIS PAGE
  // IT NEVER FIRES. `chartData` is padded by this component: `fillMinuteGaps`
  // inserts a category for every minute of the parent's shared domain, and
  // `ensurePoint` adds one per period boundary. So once the event page supplies
  // `chartStartTime`/`chartEndTime` — which it always does — a window holding no
  // odds at all still produces hundreds of value-less rows, the length test is
  // false, and BOTH this guard and the "Since Start" self-reset beneath it are
  // dead code. The reader gets the thing the guard exists to prevent: axes, a
  // "+ 3 sources" control and three `<path>` elements with an empty `d`.
  //
  // `drawnExtent` is already the honest test — the first and last category
  // actually carrying a plotted value, null when there is none — and it is
  // computed above for exactly this distinction (CERT-1984). Measured on
  // /events/15296797, a 1-1 Argentine Primera game whose books closed 19h52m
  // before kickoff: zero post-start points on every odds series, so "Since
  // Start" drew an empty grid while its own pill sat DISABLED.
  if (chartData.length === 0 || !drawnExtent) {
    if (nothingToDrawInLiveWindow) {
      // Data exists but all pre-start — the effect above resets the filter.
      return null; // Will re-render with "all" data
    }
    const isPreGame = eventStatus === "scheduled";
    return (
      <div className="h-64 flex flex-col items-center justify-center bg-surface-elevated rounded-lg text-text-muted gap-2">
        {isPreGame ? (
          <>
            <svg width="48" height="48" viewBox="0 0 48 48" fill="none" className="opacity-30">
              <circle cx="24" cy="24" r="22" stroke="currentColor" strokeWidth="2" strokeDasharray="4 4" />
              <path d="M24 14v10l7 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
            <p className="text-sm font-medium">Chart available at game time</p>
            {/* Ruling 142: "will update … once the game starts" promised a
                future state. Say what the chart plots instead. */}
            <p className="text-xs">This chart plots win probability minute by minute.</p>
          </>
        ) : (
          <p className="text-sm">No history data available</p>
        )}
      </div>
    );
  }

  // Compute gradient offset for area fill-by-value.
  // #1003: reads `primarySeriesKey`. This used to be a second, independently
  // written copy of the same ladder — it fell back to a non-betting source when
  // sportsbooks were missing, while the callout and the hover payload fell back
  // to `homeDelta`. One definition now, so the fill, the callout, the
  // lead-change count and the live hero cannot disagree about which line the
  // chart is actually about.
  // Short team names — #4285. This was `homeTeam.split(" ").pop()`, a THIRD
  // independent shortening rule with no designator list at all, so the axis
  // labelled Manchester City "FC" and Sunderland "AFC" directly under a hero
  // that had just named both clubs correctly.
  //
  // Measured before the change, over all 13,630 distinct production team names
  // on `events` in 45 days: the last-word rule disagreed with what the hero
  // prints on 2,221 names / 20,505 team-slots, and on 3,390 events (3.4%) it
  // gave BOTH ends of this axis the SAME word — `← TOWN` above `→ TOWN` on
  // Mansfield Town v Huddersfield Town, with no way to tell which is which.
  //
  // THE PAIR FORM, not `teamShortName` alone: the collision is the worst of the
  // three symptoms and one side on its own cannot see it. `teamShortNames`
  // already owns that backstop — its docstring names this exact failure
  // ("otherwise the card says 'FC' beat 'FC'") — and it fails safe, since every
  // token it lacks only makes an output LESS short.
  //
  // The abbreviation is passed but is now a RESCUE rather than a preference,
  // which is the helper's rule and a deliberate change from `*Abbrev ||`: it is
  // reached for only once the last-word rule has given up AND both sides carry
  // one. The helper measured the preference form making a card worse
  // ("Dockers / Hawks" -> "FRE / HAW"), and #3353/#4599 have abbreviations
  // actively wrong for hundreds of teams, one shared by up to 50.
  const { home: homeShort, away: awayShort } = teamShortNames(
    { name: homeTeam, abbreviation: homeTeamAbbrev },
    { name: awayTeam, abbreviation: awayTeamAbbrev },
  );

  // Y-axis tick formatter: the value is already the home win probability (0–100).
  const formatYTick = (value: number): string => `${value}%`;

  // Custom tooltip showing actual probabilities
  const CustomTooltip = ({
    active,
    payload,
    label,
  }: {
    active?: boolean;
    payload?: Array<{
      value: number;
      name: string;
      color: string;
      dataKey: string;
    }>;
    label?: string;
  }) => {
    if (active && payload && payload.length) {
      // #6238 — the `100 - homeProb` that stood here is the same subtraction the
      // readout under this chart was making, in a different format: on a
      // draw-priced sport it is "the home team does not win", not the away
      // side's chances. Both callers now read one rule in
      // `drawPricedWinner.ts`, so the tooltip and the readout cannot drift into
      // saying different things about the same match on the same card.
      // `delta` is the 0–100 axis value and IS the home probability.
      const formatProb = (delta: number) =>
        chartTooltipPair(homeTeam, delta, awayTeam, awayWithheld);

      // Look up game state from chartData for this time label
      const matchingPoint = chartData.find((d) => d.time === label);
      const hasGameState = matchingPoint && (matchingPoint._homeScore != null || matchingPoint._period);

      // Bain Luck aggregated line (multi-source mode)
      const bainLuckEntry = showBlendLine
        ? payload.find((e) => e.dataKey === "bainLuckDelta" && e.value !== null)
        : null;

      // Find entries for each resolved source
      const sourceEntries = resolvedSources
        .map((source) => {
          const entry = payload.find(
            (e) => e.dataKey === source.dataKey && e.value !== null
          );
          return entry ? { ...source, value: entry.value } : null;
        })
        .filter((e): e is ResolvedSource & { value: number } => e !== null);

      // Bookmaker entries (only shown in sportsbooks-only mode)
      const bookmakerEntries = !isMultiSource
        ? payload.filter(
            (e) =>
              e.dataKey !== "homeDelta" &&
              e.dataKey !== "bainLuckDelta" &&
              !e.dataKey.startsWith("wp_") &&
              e.dataKey !== "espnDelta" &&
              e.value !== null
          )
        : [];

      return (
        /* #1833 — the width cap has to be read off the VIEWPORT, not the chart.
           This card is absolutely positioned with auto width and its content (score header +
           period + the blend row + one row per source) wants more than a phone gives it, so
           `max-w-sm` never bound: the card simply grew to its containing block, the chart
           wrapper. Recharts then places it with
             translateX = Math.max(coord.x - width - offset, viewBox.x)   (util/tooltip/translate)
           i.e. when the card cannot fit to the left of the cursor it is pinned at `viewBox.x`,
           the y-axis inset — measured 44px on both surfaces. A card as wide as the wrapper
           therefore ends 44px PAST the wrapper's right edge, every time, wherever the reader
           touches. Measured on /events/14780544 at 390px: inline card 306px pinned at left=100
           → right=406 (16px gone) on 4 of 5 positions; the fullscreen modal 330px at left=88 →
           right=418 (28px gone) on 5 of 5. The page does not scroll sideways, so what was
           sheared off is the right-hand column — the period and clock ("Halftime",
           "End of 3rd Quarter") that `justify-between` puts there.
           So bound the card by the space that actually exists: worst-case left inset is
           wrapperLeft(56) + viewBox.x(44) = 100, and 7rem leaves that plus a small margin.
           `min()` keeps the desktop card exactly as it was — the cap only binds under 496px.
           The sibling ScoreDifferentialChart is NOT this bug and is deliberately untouched:
           its tooltip measures 110–187px, well inside the same container (same probe run).
           The underscores are load-bearing: Tailwind turns `_` into a space, and `calc(100vw-7rem)`
           without spaces around the minus is INVALID CSS that the browser drops silently — which
           would look exactly like a shipped fix that changed nothing. Asserted in the guard test. */
        <div className="bg-surface-card p-3 rounded-lg shadow-lg border border-surface-border max-w-[min(24rem,calc(100vw_-_7rem))]">
          {/* Game state header — score, period, clock */}
          {hasGameState ? (
            <div className="mb-2 pb-2 border-b border-surface-border">
              <div className="flex items-center justify-between gap-3">
                {matchingPoint._homeScore != null && matchingPoint._awayScore != null ? (
                  <span className="text-sm font-bold text-text-primary font-mono">
                    {homeShort} {matchingPoint._homeScore as number} – {matchingPoint._awayScore as number} {awayShort}
                  </span>
                ) : (
                  <span className="text-xs text-text-muted">{label}</span>
                )}
                {matchingPoint._period && (
                  <span className="text-xs text-text-muted whitespace-nowrap">
                    {matchingPoint._period as string}
                    {matchingPoint._clock ? ` ${matchingPoint._clock as string}` : ""}
                  </span>
                )}
              </div>
              {!(matchingPoint._homeScore != null && matchingPoint._awayScore != null) && (
                <p className="text-[10px] text-text-muted mt-0.5">{label}</p>
              )}
            </div>
          ) : (
            <p className="text-xs text-text-muted mb-2">{label}</p>
          )}
          {/* Scoring play annotation (tooltip only — no dots on chart) */}
          {matchingPoint?._scoringPlay && (() => {
            const play = matchingPoint._scoringPlay as ScoringPlay;
            return (
              <div className="mb-2 pb-2 border-b border-surface-border">
                <p className="text-xs font-semibold text-amber-400 flex items-center gap-1">
                  <span className="inline-block w-2 h-2 rounded-full bg-amber-400" />
                  {play.description || play.type}
                </p>
              </div>
            );
          })()}

          {/* Multi-source mode: Bain Luck aggregated first, then individual sources */}
          {showBlendLine && bainLuckEntry && (
            <div className="mb-2 pb-2 border-b border-surface-border">
              <p className="text-xs text-text-muted mb-0.5">
                {BAIN_LUCK_CONFIG.displayName}
                <span className="text-text-muted ml-1">(aggregated)</span>
              </p>
              <p className="text-sm font-semibold" style={{ color: BAIN_LUCK_CONFIG.color }}>
                {formatProb(bainLuckEntry.value)}
              </p>
            </div>
          )}

          {/* Individual sources */}
          {sourceEntries.length > 0 && (
            <div className="space-y-1">
              {isMultiSource && (
                <p className="text-xs text-text-muted mb-0.5">Sources:</p>
              )}
              {sourceEntries.map((source) => (
                <div key={source.key}>
                  {/* #2442: the `(market)` / `(model)` suffix is our OWN
                      taxonomy, printed at the reader. It is the same class
                      L2-157 stripped from the hero — "internal ranking taxonomy
                      pills are NOT user information" — and on a tennis page it
                      rendered as `Betting Odds (market)`, one of the six
                      gambling formats Alex counted on one screen. The source
                      NAME is the useful half and it stays; `source.type` is
                      still carried on the object and still drives styling. */}
                  <p className="text-xs text-text-muted mb-0.5">
                    {source.displayName}
                  </p>
                  <p
                    className={`text-xs font-medium ${
                      !isMultiSource && source.key === "betting"
                        ? "text-sm font-semibold text-text-primary"
                        : ""
                    }`}
                    style={
                      isMultiSource || source.key !== "betting"
                        ? { color: source.color }
                        : undefined
                    }
                  >
                    {formatProb(source.value)}
                  </p>
                </div>
              ))}
            </div>
          )}

          {/* Bookmaker breakdown (sportsbooks-only mode) */}
          {bookmakerEntries.length > 0 && (
            <div className="mt-2 pt-2 border-t border-surface-border">
              <p className="text-xs text-text-muted mb-1">By sportsbook:</p>
              {bookmakerEntries.map((entry) => {
                const bookmaker = entry.dataKey.replace("_delta", "");
                const homeProb = entry.value; // 0–100 axis
                // #3892 — same rule as the edge callout above, and for the same
                // reason: `toFixed(0)` on the axis value rounds
                // `57.49999999999999` down to 57 where the contract says 58.
                //
                // It also rounded the two ends INDEPENDENTLY, so a book quoting
                // an exact complement on the half-percent grid could print
                // `57% / 43%` beside `58%` in the hero. Deriving the second end
                // from the first keeps a sportsbook's own pair summing to 100.
                const percents = chartAxisPercents(homeProb);
                // A book with no usable number is omitted rather than listed
                // with a placeholder — same reason as the callout above.
                if (percents.home === null || percents.away === null) return null;
                // #6858 — the same boundary rule as the callout and the hero. A
                // book quoting 0.999 read `100% / 0%` here while the hero on the
                // same page read `>99%`.
                return (
                  <p key={bookmaker} className="text-xs text-text-muted">
                    {bookmaker}: {percents.homeLabel} /{" "}
                    {percents.awayLabel}
                  </p>
                );
              })}
            </div>
          )}
        </div>
      );
    }
    return null;
  };

  return (
    <div
      className={fillContainer ? "flex flex-col h-full gap-1" : "space-y-3"}
      /* HOW MANY PERIOD CHIPS THIS CHART WILL DRAW, on the wrapper (CERT-1984).
         Same reason as ScoreDifferentialChart's `data-*-series`: recharts renders
         nothing inside `ResponsiveContainer` without a viewport, so a server
         render — all a guard or the capture rig can see — cannot observe a
         `<ReferenceLine>`. A guard that looked for the missing "1H" label would
         pass on both arms and be worth nothing. This is the count actually
         rendered below, after the drawn-line bound. */
      data-period-boundaries={filteredPeriodBoundaries.length}
      /* #6882: which row each surviving label lands on, in x order —
         "0,0,1,0" is the NFL shape. recharts draws no <ReferenceLine> in a
         server render (no viewport), so the stagger is unobservable in the
         markup; this is the same channel CERT-1984 opened for the count. */
      data-period-label-rows={filteredPeriodBoundaries.map((b) => (b as { labelRow?: number }).labelRow ?? 0).join(",")}
      /* #6987: the end-callout's printed string, on the wrapper, for the same
         reason as the two above — the label is drawn inside a recharts `shape`,
         which renders nothing without a viewport, so a guard reading the markup
         for "100%" would find nothing on either arm. This is the exact text a
         reader sees beside the dot, not a re-derivation of it: the empty string
         means no callout is drawn at all. */
      data-callout-label={currentCallout?.homeLabel ?? ""}
      /* #6987: the timestamp the callout is anchored to. The defect was never a
         rounding rule — "Since Start" and "All" were labelling two points ten
         minutes apart — so a guard needs to see WHICH point, not only what it
         printed. */
      data-callout-at={currentCallout?.timestamp ?? ""}
      /* #6987: the first and last instant this chart puts INK on, in epoch ms —
         `drawnExtent`, the same bound the period chips and the Start flag are
         judged against, not `chartData`'s extent. The callout above is one
         reader of the window; the trailing flat tail was the whole of the
         defect, and only this says where the line actually stops. Empty when
         nothing is drawn. */
      data-drawn-extent={drawnExtent ? `${drawnExtent.startMs},${drawnExtent.endMs}` : ""}
      /* #7161: the first and last CATEGORY, in epoch ms, and how many there are.
         Deliberately not `data-drawn-extent`: a categorical XAxis places a tick
         by matching its string against the category list, so a category outside
         the parent's window mis-places a tick whether or not it carries ink —
         which is how `7:00 PM` came to sit left of `3:15 PM`. The ink and the
         categories are two different facts and the guard needs both. */
      data-category-span={
        chartData.length > 0
          ? `${parseISO(chartData[0].timestamp).getTime()},${parseISO(chartData[chartData.length - 1].timestamp).getTime()},${chartData.length}`
          : ""
      }
    >
      {/* Time range selector */}
      <div className="flex flex-wrap items-center gap-1 shrink-0">
        {TIME_RANGE_OPTIONS.map((option) => {
          const isDisabled = option.value === "live" && !hasPostStartData;
          return (
          <button
            key={option.value}
            disabled={isDisabled}
            /* #6987: which range is ON, said out loud. These two buttons are a
               toggle group, and the only thing that distinguished the selected
               one was its fill — invisible to a screen reader, and readable by a
               probe only as a Tailwind class it would then be pinned to. */
            aria-pressed={timeRange === option.value}
            onClick={() => {
              if (isDisabled) return;
              const previousRange = timeRange;
              handleTimeRangeChange(option.value);
              setHasUserOverridden(true);
              if (eventId) {
                track('chart_time_range', {
                  chart_type: 'probability_trend',
                  event_id: eventId,
                  range: option.value,
                  previous_range: previousRange,
                  has_data: filteredHistory.length > 0,
                  data_points_count: filteredHistory.length,
                });
              }
            }}
            className={`font-medium rounded-full transition-colors ${
              isDisabled
                ? "opacity-30 cursor-not-allowed px-3 py-1.5 text-xs bg-surface-elevated text-text-secondary"
                : fillContainer
                ? `px-[0.4vw] py-[0.1vh] text-[0.9vh] ${
                    timeRange === option.value
                      ? "bg-surface-card/10 text-white/40"
                      : "text-white/15 hover:text-white/25"
                  }`
                : `px-3 py-1.5 text-xs ${
                    timeRange === option.value
                      ? "bg-text-primary text-surface-deep"
                      : "bg-surface-elevated text-text-secondary hover:bg-surface-border"
                  }`
            }`}
          >
            {option.label}
          </button>
          );
        })}

        {/* Odds-flip toggle — only offered when there are crossings to show.
            Hidden in the compact fillContainer (fullscreen) layout.
            #4882: the label names the market, not the score — see the counter. */}
        {!fillContainer && crossingCount > 0 && (
          <button
            onClick={() => setShowCrossings((v) => !v)}
            className={`ml-auto flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-full transition-colors ${
              showCrossings
                ? "bg-text-primary text-surface-deep"
                : "bg-surface-elevated text-text-secondary hover:bg-surface-border"
            }`}
            title={showCrossings ? "Hide the odds flips" : "Show the odds flips"}
            aria-pressed={showCrossings}
          >
            <svg width="9" height="9" viewBox="0 0 10 10" className="shrink-0">
              <polygon points="5,0 10,5 5,10 0,5" fill="currentColor" />
            </svg>
            Odds flipped ({crossingCount})
          </button>
        )}
      </div>

      {/* Probability Chart with vertical team labels */}
      <div className={`flex ${fillContainer ? "flex-1 min-h-0" : "h-80"}`}>
        {/* ═══ THE GUTTER IS AN AXIS, NOT TWO MORE SERIES NAMES (#2448) ═══

            Alex, on `/events/15293846`: *"the y-axis is labelled with both
            player names vertically, while the single plotted line is labelled
            `Betting Odds` — three labels, one line."*

            He was right about what he saw and the names were not the error. The
            axis genuinely runs from "the away player wins" at 0% to "the home
            player wins at 100%", so both names belong in the gutter — they are
            its two POLES. What was missing is the only thing that turns two
            names into an axis: a DIRECTION. Without it a reader has two names,
            a 0–100 scale and a line, and no rule connecting them; every one of
            the three labels is equally likely to be the line's.

            One caret per pole fixes it and adds no words. `↑ BERRETTINI` at the
            top and `↓ WAWRINKA` at the bottom says "up is Berrettini", which is
            exactly the missing rule, and the section heading above the chart
            ("Win Probability") already names the quantity while the legend
            below names the source. Three ideas, each said once, instead of
            three names competing to be the same one.

            `aria-hidden` on the caret and a real sentence in `sr-only`: a
            screen reader cannot see which end of a gutter a label is at, so the
            glyph carries nothing for it and the sentence carries everything. */}
        <div className="flex flex-col items-center justify-between py-3 shrink-0" style={{ width: 28 }}>
          <div
            className="flex items-center gap-1"
            style={{ writingMode: "vertical-rl", transform: "rotate(180deg)" }}
            data-testid="chart-axis-pole"
            data-pole="home"
          >
            <span className="sr-only">
              The line rises towards {homeShort}: the top of this axis is {homeShort} at 100%.
            </span>
            {homeTeamLogo && (
              <img src={homeTeamLogo} alt="" width={12} height={12} className="object-contain" style={{ transform: "rotate(90deg)" }} />
            )}
            <span
              aria-hidden="true"
              className="text-[11px] font-bold uppercase tracking-wider"
              style={{ color: teamTextColor(homeTeamColor) || "#16a34a" }}
            >
              {"↑"} {homeShort}
            </span>
          </div>
          <div
            className="flex items-center gap-1"
            style={{ writingMode: "vertical-rl", transform: "rotate(180deg)" }}
            data-testid="chart-axis-pole"
            data-pole="away"
          >
            <span className="sr-only">
              The line falls towards {awayShort}: the bottom of this axis is {awayShort} at 100%.
            </span>
            {awayTeamLogo && (
              <img src={awayTeamLogo} alt="" width={12} height={12} className="object-contain" style={{ transform: "rotate(90deg)" }} />
            )}
            <span
              aria-hidden="true"
              className="text-[11px] font-bold uppercase tracking-wider"
              style={{ color: teamTextColor(awayTeamColor) || "#2563eb" }}
            >
              {"↓"} {awayShort}
            </span>
          </div>
        </div>

        {/* Chart area */}
        <div className="flex-1 min-w-0">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart
            data={chartData}
            margin={{ top: 15, right: 10, left: 0, bottom: 5 }}
            onMouseMove={(state: { activeTooltipIndex?: number }) => {
              if (!onActivePointChange) return;
              const idx = state?.activeTooltipIndex;
              if (idx == null || idx < 0 || idx >= chartData.length) {
                onActivePointChange(null);
                return;
              }
              const pt = chartData[idx];
              const delta = pt[primarySeriesKey] as number | null;
              const homeProb = delta != null ? chartAxisToHomeProb(delta) : 0.5; // 0–100 axis → 0–1
              onActivePointChange({
                timestamp: pt.timestamp,
                homeProb,
                awayProb: 1 - homeProb,
                homeScore: pt._homeScore as number | null | undefined,
                awayScore: pt._awayScore as number | null | undefined,
                period: pt._period as string | null | undefined,
                clock: pt._clock as string | null | undefined,
                clockApprox: pt._clockApprox as boolean | undefined,
                scoringPlay: pt._scoringPlay as ScoringPlay | null | undefined,
              });
            }}
            onMouseLeave={() => {
              if (onActivePointChange) onActivePointChange(null);
            }}
          >
            {/*
              #3425: the `probFillGradient-<id>` <defs> block that stood here is
              gone. It was DEAD — one definition, and not a single
              `fill="url(#probFillGradient-…)"` anywhere in the frontend, no
              <Area>, nothing. It painted nothing and never had, but it emitted
              its two <stop offset="NaN"> on every event page (8+ console errors
              a load), because its offset came from a `dataMax / (dataMax -
              dataMin)` written for the old mirrored ±50 delta axis and read
              through a guard that let `undefined` through.

              Deleted rather than repaired: computing a correct split for a
              gradient nothing references would be inventing a visual nobody
              asked for and changing every event page's fill to do it. If the
              two-tone fill is wanted back, it is a design decision with a fresh
              offset — the midpoint on today's 0–100 axis is 50, not 0.
            */}
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.06)" />
            <XAxis
              dataKey="time"
              tick={{ fontSize: 12, fill: "#6B7280" }}
              tickLine={false}
              axisLine={{ stroke: "rgba(0,0,0,0.1)" }}
              {...(sharedTicks
                ? { ticks: sharedTicks }
                : { interval: chartData.length <= 10 ? 0 : "preserveStartEnd", minTickGap: 50 }
              )}
            />
            <YAxis
              domain={yDomain}
              ticks={yTicks}
              // #3973: the domain is now narrower than the data can be, so
              // the handful of samples outside it must be CLIPPED. recharts
              // does not clamp their coordinates — it emits the true y and
              // fits a clip path only when an axis asks for one. With this
              // off, no clip path is fitted and the early spike is painted at
              // its true height: outside the plot, over the card's chrome.
              allowDataOverflow
              width={44}
              tick={{ fontSize: 13, fill: "#4B5563" }}
              tickLine={false}
              axisLine={{ stroke: "rgba(0,0,0,0.1)" }}
              tickFormatter={formatYTick}
            />
            {/* 50% reference line.

                #3525: IT USED TO CARRY A `50%` LABEL AND THAT LABEL WAS NEVER
                ONCE READ BY ANYONE. `position: "right"` puts a label OUTSIDE the
                plot's right edge, and this chart's right margin is 10px against
                a ~22px label, so what actually reached the page was a bare `5`
                clipped at the card boundary, floating beside the dashes at the
                50% gridline with nothing to attach it to. Alex's reading of it —
                a digit a reader can take for a score or a set count — is the
                whole cost, and there was no benefit on the other side of it:
                `yTicks` already includes 50 and the left axis already prints
                `50%` on this exact line, so the label was a duplicate even in the
                world where it rendered. Deleted rather than moved inside, because
                moving it in would put a second `50%` on a chart that already has
                one. The guard is on the class: no rendered text outside a
                chart's plot bounds. */}
            {/* #3973 pins `ifOverflow` rather than leaving it defaulted. The
                axis is no longer always 0–100, so 50 is no longer always on it:
                a market that never approaches 50 has no crossing, nothing
                drawn at 50, and no use for a dashed rule welded to its plot
                frame. `discard` (recharts' default, stated here because it is
                now load-bearing) drops it in that case. The value that must
                never appear is `extendDomain` — it would pull 50 back into the
                domain and silently undo the zoom for every narrow market. Both
                halves of #3525's reasoning below survive: whenever the line
                touches 50, `computeWinProbYAxis` keeps 50 in the domain and on
                the tick set, so the axis is still printing `50%` on this
                exact line. */}
            <ReferenceLine
              y={50}
              ifOverflow="discard"
              stroke="rgba(0,0,0,0.2)"
              strokeWidth={1.5}
              strokeDasharray="4 4"
            />
            <Tooltip content={<CustomTooltip />} />

            {/* ── MODE B: Sportsbooks-only — individual bookmaker lines (thin grey) ── */}
            {!isMultiSource && bookmakers.map((bookmaker) => (
              <Line
                key={`${bookmaker}_delta`}
                type="linear"
                dataKey={`${bookmaker}_delta`}
                stroke="rgba(0,0,0,0.15)"
                strokeWidth={1}
                dot={false}
                activeDot={{ r: 3, fill: "rgba(0,0,0,0.3)" }}
                connectNulls
                legendType="none"
              />
            ))}

            {/* ── MODE A: Multi-source — individual source lines (near-invisible so
                the one blended Bain Luck line clearly dominates, per L2-131) ── */}
            {isMultiSource && resolvedSources.map((source) => {
              const isPrimarySource = source.dataKey === primarySeriesKey;
              return (
              <Line
                key={source.dataKey}
                type="linear"
                dataKey={source.dataKey}
                name={source.displayName}
                stroke={source.color}
                // UX-P022: these were pinned at width 1 / opacity 0.28 in BOTH
                // states. At that weight, on a light card, a source line that
                // tracks the blend closely is invisible — so pressing
                // "+ N sources" listed the sources in the legend and changed
                // NOTHING on the graph. The control looked broken because, as
                // far as the reader could tell, it was.
                //
                // Collapsed still means blend-dominant (L2-131, and "the blend
                // is the product"). Expanding is the reader explicitly asking to
                // see the spread, so the lines become legible — a deliberate
                // comparison surface, entered on purpose, not shown by default.
                //
                // #3151/#3111: de-emphasis is only correct when something else
                // DOMINATES. `isMultiSource` is true at ONE non-betting source
                // (its own comment says so), and `showBlendLine` needs a backend
                // aggregate — so a Kalshi-only match took this branch with no
                // blend line above it, and the only line on the plot was a 1px
                // 28%-opacity dash. Measured in the production DOM for
                // /events/15300276: 559 points, `stroke-opacity: 0.28`, a
                // correct 852px path nobody can see. It reads as an empty chart.
                //
                // `primarySeriesKey` already names the series the lead-change
                // count and the current-probability callout are computed from.
                // Drawing THAT one at full weight is what keeps the line the
                // reader sees and the numbers printed beside it the same line.
                // When a blend IS drawn it owns `primarySeriesKey`, no source
                // matches, and every source stays faint exactly as before.
                strokeWidth={isPrimarySource ? 2.5 : legendExpanded ? 1.75 : 1}
                strokeOpacity={isPrimarySource ? 1 : legendExpanded ? 0.85 : 0.28}
                strokeDasharray={source.dashPattern ?? undefined}
                dot={false}
                activeDot={{ r: isPrimarySource ? 4 : 3, fill: source.color }}
                connectNulls
              />
              );
            })}

            {/* MODE B's non-betting branch used to stand here, drawing
                `nonBettingSources` at strokeWidth 2.5 under `!isMultiSource`.
                It could never run: `isMultiSource` IS `nonBettingSources.length
                > 0`, so `!isMultiSource` guarantees the array it maps is empty.
                The single-source case it was written for always fell into MODE
                A above instead and was drawn faint — which is #3151/#3111.
                Removed rather than left as a second place to fix the same bug;
                MODE A now handles the primary source at full weight. */}

            {/* Legacy ESPN line (when winProbHistory not available and not multi-source) */}
            {!isMultiSource && !useNewWinProbData && filteredEspnHistory.length > 0 && (
              <Line
                type="linear"
                dataKey="espnDelta"
                name="ESPN Model"
                stroke={sourceHex("espn")}
                strokeWidth={2.5}
                strokeDasharray="6 3"
                dot={false}
                activeDot={{ r: 4, fill: sourceHex("espn") }}
                connectNulls
              />
            )}

            {/* Area fill removed — was causing green semi-circle artifacts */}

            {/* ── MODE A: Multi-source — aggregated Bain Luck line (prominent, on top) ── */}
            {showBlendLine && (
              <Line
                type="linear"
                dataKey="bainLuckDelta"
                name={BAIN_LUCK_CONFIG.displayName}
                stroke={BAIN_LUCK_CONFIG.color}
                strokeWidth={3}
                dot={false}
                activeDot={{ r: 5, fill: BAIN_LUCK_CONFIG.color }}
                connectNulls
              />
            )}

            {/* ── MODE B: Sportsbooks-only — betting odds line (solid, prominent, on top).
                Dark slate (#0f172a), NOT the old near-white #e5e7eb that vanished on
                the light-mode card (L2-131 "the blend line absent/gray"). ── */}
            {!isMultiSource && (
              <Line
                type="linear"
                dataKey="homeDelta"
                name={sourceLabel("betting")}
                stroke={sourceHex("betting")}
                strokeWidth={3}
                dot={false}
                activeDot={{ r: 5, fill: sourceHex("betting") }}
                connectNulls
              />
            )}



            {/* Crossing markers — diamonds at 50% crossings (default off) */}
            {showCrossings && crossingCount > 0 && (
              <Scatter
                dataKey="crossingDelta"
                fill="none"
                shape={(props: { cx?: number; cy?: number; payload?: Record<string, unknown> }) => {
                  if (props.payload?.crossingDelta == null) return <g />;
                  const { cx = 0, cy = 0 } = props;
                  return (
                    <g>
                      <polygon
                        points={`${cx},${cy - 6} ${cx + 5},${cy} ${cx},${cy + 6} ${cx - 5},${cy}`}
                        fill="rgba(0,0,0,0.7)"
                        stroke="rgba(0,0,0,0.3)"
                        strokeWidth={1}
                      />
                      <polygon
                        points={`${cx},${cy - 3} ${cx + 2.5},${cy} ${cx},${cy + 3} ${cx - 2.5},${cy}`}
                        fill="#fbbf24"
                      />
                    </g>
                  );
                }}
                legendType="none"
              />
            )}

            {/* Current probability callout — dot at the last data point */}
            {currentCallout && (
              <Scatter
                dataKey="calloutDelta"
                fill="none"
                shape={(props: {
                  cx?: number;
                  cy?: number;
                  payload?: Record<string, unknown>;
                  /* The plot rect, straight from the renderer. recharts hands the
                     shape its resolved `yAxis`, whose `y`/`height` ARE the plot's
                     top and height — so #5581's clamp never re-derives the frame
                     from `margin.top` and cannot drift from the real layout.
                     Optional because the library's types do not promise it; if it
                     ever stops arriving the clamp no-ops back to today's
                     behaviour, and `chartCalloutClearsTheTopStrip5581` goes red,
                     which is how anyone would find out. */
                  yAxis?: { y?: number; height?: number };
                }) => {
                  if (props.payload?.calloutDelta == null) return <g />;
                  const { cx = 0, cy = 0 } = props;
                  const fillColor = showBlendLine
                    ? BAIN_LUCK_CONFIG.color
                    : sourceHex("betting");
                  // #4338 — the plate under the number. Anchored `end` at
                  // `cx - CALLOUT_GAP_PX`, so the glyphs run LEFT from there.
                  // #6858 — the boundary rule's answer, not the bare integer:
                  // `0.001` prints `<1%` here exactly as it does in the hero
                  // directly above. `label.length` still sizes the plate below.
                  const label = currentCallout.homeLabel;
                  const textRight = cx - CALLOUT_GAP_PX;
                  const glyphWidth =
                    label.length * CALLOUT_FONT_PX * CALLOUT_MONO_ADVANCE_EM;
                  const glyphHeight = CALLOUT_FONT_PX * CALLOUT_GLYPH_BOX_EM;
                  // #5581 — the label's row, which is the dot's row on every
                  // chart that does not finish against the frame. See
                  // `calloutLabelCenterY` for why the dot does NOT move with it.
                  const labelY =
                    props.yAxis?.y != null && props.yAxis?.height != null
                      ? calloutLabelCenterY({
                          cy,
                          plotTop: props.yAxis.y,
                          plotHeight: props.yAxis.height,
                          // #7134 — the strip's DEPTH, read off the same rowed
                          // list the `<ReferenceLine>` labels below are drawn
                          // from, so the band can never disagree with the ink.
                          periodChipRows: periodChipRowCount,
                        })
                      : cy;
                  return (
                    <g>
                      {/* Outer glow */}
                      <circle cx={cx} cy={cy} r={8} fill={fillColor} fillOpacity={0.2} />
                      {/* Inner dot */}
                      <circle cx={cx} cy={cy} r={5} fill={fillColor} stroke="#FFFFFF" strokeWidth={2} />
                      {/* Probability label.

                          #3525 (found by its guard, not by the issue): this
                          was `cx + 12`, anchored `start`, and it had NEVER
                          rendered. The callout marks the LAST data point, and
                          since the right-hand buffer was removed the last data
                          point IS the plot's right edge — so `cx + 12` is
                          always past it, and the svg clips its own overflow.
                          What a reader got was the dot with no number, which is
                          the one thing the callout exists to say; it is visible
                          in `artifacts-live-073/sabalenka-townsend.png`, a
                          ringed green dot at 81% with nothing beside it.

                          It goes on the LEFT unconditionally rather than
                          flipping on a measurement, because there is nothing to
                          measure: the anchor point is the right edge by
                          construction, so the right-hand side is never the
                          answer. 12px clears the dot's 8px glow.

                          #3561, THE HALO: once the number rendered, it rendered
                          ON the line. `cy` is the last data point and the series
                          TERMINATES there, so a label centred on `cy` sits
                          exactly where the line arrives — a collision by
                          construction, not a property of one specimen. It
                          bisected the digits and turned `41%` into `41°`.

                          Lifting it vertically is the obvious answer and is
                          wrong: on a steeply-arriving series the line just left
                          of the dot is ABOVE `cy`, so a lift walks the label
                          into the line instead of out of it, and it would need a
                          clamp against the plot ceiling as well. The label has
                          to stay on the dot's row — it is labelling the dot — so
                          it is made legible OVER ink instead. A painted-under
                          white stroke is slope-independent and needs no
                          geometry.

                          #5581 NARROWS THAT LAST SENTENCE AND DOES NOT REVOKE
                          IT. The row is still the answer wherever the label fits
                          on it. It does not fit when the series finishes ON the
                          frame: there the clip takes half the glyphs and the
                          period strip takes what is left, so `labelY` above
                          moves the row by the least that makes it readable.
                          Note this paragraph already named the ceiling clamp
                          such a move would need — that was a reason not to lift
                          the label for a DIFFERENT problem, never a reason to
                          leave the frame case cut in half.

                          #4338, THE THICKET: a halo is enough over ONE line and
                          not over the four that cross this label at the plot's
                          busiest end. See `CALLOUT_MONO_ADVANCE_EM` above for
                          the measurement and for why the answer is to fill the
                          same white across the glyph box rather than to move
                          the label — which #3561 already ruled out. The plate is
                          painted here, immediately under the text and after the
                          dot, so paint order is glow → dot → plate → glyphs. */}
                      <rect
                        x={textRight - glyphWidth - CALLOUT_PLATE_PAD_X}
                        y={labelY - glyphHeight / 2 - CALLOUT_PLATE_PAD_Y}
                        width={glyphWidth + CALLOUT_PLATE_PAD_X * 2}
                        height={glyphHeight + CALLOUT_PLATE_PAD_Y * 2}
                        rx={3}
                        fill="#FFFFFF"
                      />
                      <text
                        x={textRight}
                        y={labelY}
                        textAnchor="end"
                        dominantBaseline="central"
                        fill={fillColor}
                        stroke="#FFFFFF"
                        strokeWidth={3}
                        paintOrder="stroke"
                        fontSize={11}
                        fontWeight={700}
                        fontFamily="monospace"
                      >
                        {/* The same `label` the plate was sized from. Printing
                            `{currentCallout.homeProb}%` here instead would let
                            the string and its backing drift apart silently. */}
                        {label}
                      </text>
                    </g>
                  );
                }}
                legendType="none"
              />
            )}

            {/* ── EVENT MARKERS: LAST CHILDREN ON PURPOSE (#6964) ──────────────

                A reader on `/events/14638444` (Bills–Lions, 390px) saw the `Q3`
                marker on the score-differential chart render as a bare `3`. The
                label text was never wrong: the orange step line ran through the
                same pixels and painted the `Q` out.

                These three blocks used to sit above the series and pass
                `isFront`, with a comment claiming they were "rendered in front of
                data area". `isFront` IS A DEAD PROP. In recharts 2.15.4 it appears
                exactly once per reference component — `isFront: false` in
                defaultProps — and is read nowhere in the library; it is also in
                the `.d.ts`, so it type-checks and nothing ever warned. It is a
                recharts v1 survival.

                SVG has no z-index, so paint order is document order, and
                `renderByOrder` (util/ReactUtils) pushes children in JSX order.
                Measured on production before the move: every reference-line group
                sat at document index 51–69 and every series at 73–127 — markers
                under data on BOTH charts, on every event page, not just this one.

                So the only thing that puts an annotation above the plot is being
                later in this list. Moving these costs nothing and there is no
                prop that substitutes for it.

                The horizontal guide rules (`y=50` here, `y=0` on the score chart)
                deliberately stay above the series: they are background rules a
                reader reads the data AGAINST, not annotations that sit on top.
                `artifacts/ux-1366/paint-order-6964.mjs` re-measures any page. */}
            {/* Game Start marker — solid line at commence_time */}
            {gameStartTime && filteredPeriodBoundaries.length === 0 && (
              <ReferenceLine
                x={gameStartTime}
                stroke="rgba(0,0,0,0.25)"
                strokeWidth={1.5}
                label={{
                  value: "Start",
                  position: "insideTopLeft",
                  style: { fontSize: 11, fill: "rgba(0,0,0,0.6)", fontWeight: 700 },
                }}
              />
            )}
            {/* Period boundary markers (#6882 stagger; #6964 paint order) */}
            {filteredPeriodBoundaries.map((b) => (
              <ReferenceLine
                key={`period-${b.label}-${b.timestamp}`}
                x={b.time}
                stroke="rgba(0,0,0,0.25)"
                strokeWidth={1.5}
                strokeDasharray="6 4"
                label={{
                  value: b.label,
                  position: ((b as { labelPosition?: string }).labelPosition || "insideTopLeft") as "insideTopLeft" | "insideTopRight",
                  // #6882: `dy` shifts the whole text block down from whatever
                  // `position` computed — recharts keeps `dy` through
                  // `filterProps` (it is an SVG text attribute) and `Text` adds it
                  // to y. Row 0 passes 0, so an unstaggered label is byte-identical
                  // to what it rendered before.
                  dy: ((b as { labelRow?: number }).labelRow || 0) * PERIOD_LABEL_ROW_HEIGHT_PX,
                  style: { fontSize: 11, fill: "rgba(0,0,0,0.65)", fontWeight: 700 },
                }}
              />
            ))}
            {/* Final marker — exactly one, at the game-end snapshot (settled only).
                THE LINE, AND DELIBERATELY NO LABEL (#3541).

                It used to carry `value: "Final"` at `insideTopLeft`, and what
                reached every settled event page was a bare `F`. `finalMarkerTime`
                is the LAST chart category, which since the right-hand buffer was
                removed is the plot's right rule — and `insideTopLeft` anchors the
                text `start` there, so it grows out of the svg and is clipped to
                its first glyph. That is structural, not a breakpoint: the same
                orphan `F` is on the 1280px shot as on the 390px one, because the
                svg ends 10px past the rule at every width.

                Anchoring it inside instead is the expensive answer and buys
                nothing. `insideTopRight` grows the text LEFT out of the right
                rule, into the space UX-P022 above reserves for the last period
                boundary — and `minSpacing` (7% of the chart) is sized for labels
                that all grow the same way, while the Final marker is deduped only
                against final-LIKE boundaries, so a `Q4` or `T9` can sit right
                beside it. Making the spacing rule bidirectional would be real
                work to restore a word the page already says twice: the hero
                carries a FINAL chip, and the line's own position at the end of
                the timeline is the part that carries information. So the marker
                keeps its full stop and loses its caption.

                Guarded by `chartTextStaysInsideThePlot.test.tsx`, which pins BOTH
                halves — no text off the right edge, and this line still drawn. */}
            {finalMarkerTime && (
              <ReferenceLine
                x={finalMarkerTime}
                stroke="rgba(0,0,0,0.35)"
                strokeWidth={1.5}
              />
            )}
          </ComposedChart>
        </ResponsiveContainer>
        </div>
      </div>

      {/* Source legend */}
      <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-1 shrink-0">
        {/* Multi-source mode: Bain Luck aggregated line first (always labeled).
            #1003: gated on showBlendLine, not isMultiSource — a legend entry for a
            line the chart did not draw is the same false claim as the line. */}
        {showBlendLine && (
          <div className="flex items-center gap-1.5">
            <svg width="20" height="4" className="shrink-0">
              <line
                x1="0" y1="2" x2="20" y2="2"
                stroke={BAIN_LUCK_CONFIG.color}
                strokeWidth="3"
              />
            </svg>
            <span className="text-xs font-semibold" style={{ color: BAIN_LUCK_CONFIG.color }}>
              {BAIN_LUCK_CONFIG.displayName}
            </span>
          </div>
        )}

        {/* Multi-source: the individual source lines stay collapsed behind an
            expander so the blend dominates (L2-163 Item 1). Sportsbooks-only mode
            keeps its flat legend (there is no blend to dominate). */}
        {isMultiSource && resolvedSources.length > 0 && !legendExpanded && (
          <button
            type="button"
            onClick={() => setLegendExpanded(true)}
            className="flex items-center gap-1 text-xs text-text-muted hover:text-text-secondary transition-colors"
            aria-expanded={false}
          >
            + {resolvedSources.length} source{resolvedSources.length !== 1 ? "s" : ""}
            <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={3} className="shrink-0">
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
            </svg>
          </button>
        )}

        {/* Individual sources — always shown in sportsbooks-only mode; in
            multi-source mode only once the reader expands the legend. */}
        {(!isMultiSource || legendExpanded) && resolvedSources.map((source) => {
          const inner = (
            <>
              <svg width="20" height="4" className="shrink-0">
                <line
                  x1="0" y1="2" x2="20" y2="2"
                  stroke={source.color}
                  strokeWidth={isMultiSource ? "1" : "2.5"}
                  strokeDasharray={source.dashPattern ?? undefined}
                  strokeOpacity={isMultiSource ? 0.4 : 1}
                />
              </svg>
              <span className={`text-xs ${isMultiSource ? "text-text-muted" : "text-text-secondary hover:text-text-primary"}`}>
                {source.displayName}
              </span>
            </>
          );
          return eventId ? (
            <Link
              key={source.key}
              href={`/events/${eventId}/models`}
              className="flex items-center gap-1.5 hover:underline"
            >
              {inner}
            </Link>
          ) : (
            <div key={source.key} className="flex items-center gap-1.5">
              {inner}
            </div>
          );
        })}

        {/* Collapse control when expanded (multi-source only) */}
        {isMultiSource && legendExpanded && resolvedSources.length > 0 && (
          <button
            type="button"
            onClick={() => setLegendExpanded(false)}
            className="flex items-center gap-1 text-xs text-text-muted hover:text-text-secondary transition-colors"
            aria-expanded={true}
          >
            Hide
            <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={3} className="shrink-0 rotate-180">
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
            </svg>
          </button>
        )}

        {/* Bookmaker legend (sportsbooks-only mode) */}
        {!isMultiSource && bookmakers.length > 0 && (
          <div className="flex items-center gap-1.5">
            <svg width="20" height="4" className="shrink-0">
              <line
                x1="0" y1="2" x2="20" y2="2"
                stroke="rgba(0,0,0,0.15)"
                strokeWidth="1"
              />
            </svg>
            {/* #2442: ONE name per supplier. This legend said "Individual
                sportsbooks" while the page footer said "Sportsbooks" and the
                line itself said "Betting Odds" — three names for one source on
                one screen. The registry decides the noun; the qualifier carries
                the only thing this legend adds, which is that these are the
                separate lines rather than their average.
                #3563: that qualifier used to be `Each {label.toLowerCase()}`,
                which composed with the registry's plural into the non-sentence
                "Each sportsbooks" on every sportsbooks-only page. The phrasing
                now agrees with no number at all — see `separateLinesLabel`. */}
            <span className="text-xs text-text-muted">
              {separateLinesLabel("betting")}
            </span>
          </div>
        )}



        {/* Odds-flip legend (only when the toggle is on) */}
        {showCrossings && crossingCount > 0 && (
          <div className="flex items-center gap-1.5">
            <svg width="10" height="10" className="shrink-0">
              <polygon points="5,1 9,5 5,9 1,5" fill="#fbbf24" />
            </svg>
            <span className="text-xs text-text-muted">
              Odds flipped ({crossingCount})
            </span>
          </div>
        )}
      </div>

      {/* #2448: `Tap/hover for details` DELETED.
          Alex read it as body text under a chart, which is what it was — a
          caption whose entire content was an instruction about our own UI. It
          told a mouse user to hover and a phone user to tap, said nothing about
          the match, and sat in the same visual slot the page uses for facts. A
          tooltip that needs a caption announcing tooltips is not made
          discoverable by the caption; it is made noisy. Nothing replaces it. */}
    </div>
  );
}
