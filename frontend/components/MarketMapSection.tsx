"use client";

import { useMemo } from "react";
import MarketMap from "./MarketMap";
import type { MarketMapMarker, MarketMapLadderRow } from "./MarketMap";
import type { GameMarketsResponse } from "@/lib/api";
import {
  parseSpreadOutcome,
  isFullGameSpread,
  isGameTotal,
  buildDensityFromSpreads,
  buildDensityFromThresholds,
  sportVocab,
  withUnit,
  unitPhrase,
  posOnRail,
  collapseDuplicateRungs,
} from "@/lib/marketMapUtils";

interface MarketMapSectionProps {
  gameMarkets: GameMarketsResponse;
  eventStatus: string;
  homeTeam: string;
  awayTeam: string;
  homeAbbr?: string;
  awayAbbr?: string;
  homeColor?: string;
  awayColor?: string;
  homeLogo?: string;
  awayLogo?: string;
  homeWinProb?: number;
  awayWinProb?: number;
  homeSpread?: number | null;
  overUnder?: number | null;
  sportKey?: string;
  espnHistory?: Array<{ period?: string; home_score?: number; away_score?: number; timestamp?: string }>;
}

interface HalfScores {
  h1Home: number;
  h1Away: number;
  h2Home: number;
  h2Away: number;
}

function deriveHalfScores(
  espnHistory: MarketMapSectionProps["espnHistory"],
  finalHome: number | null,
  finalAway: number | null
): HalfScores | null {
  if (!espnHistory || espnHistory.length === 0) return null;
  if (finalHome == null || finalAway == null) return null;

  const htEntry = [...espnHistory].reverse().find(
    (e) => e.period && /halftime|^ht$|end of 2nd/i.test(e.period) && e.home_score != null
  );
  if (!htEntry || htEntry.home_score == null || htEntry.away_score == null) return null;

  return {
    h1Home: htEntry.home_score,
    h1Away: htEntry.away_score,
    h2Home: finalHome - htEntry.home_score,
    h2Away: finalAway - htEntry.away_score,
  };
}

/**
 * Determine which half the game is currently in from ESPN history.
 * Returns "1H" or "2H" (null if unknown).
 */
function detectCurrentHalf(
  espnHistory: MarketMapSectionProps["espnHistory"]
): "1H" | "2H" | null {
  if (!espnHistory || espnHistory.length === 0) return null;
  const latest = espnHistory[espnHistory.length - 1];
  if (!latest.period) return null;
  const p = latest.period.toLowerCase();
  if (/1st quarter|1st half|first half|^q1\b|^q2\b|2nd quarter/i.test(p)) return "1H";
  if (/halftime|^ht$/i.test(p)) return "1H";
  return "2H";
}

/**
 * Derive live half scores for in-progress games.
 * - In the 1st half: h1 = current game scores, h2 = null
 * - In the 2nd half: h1 = halftime scores, h2 = current - halftime
 */
function deriveLiveHalfScores(
  espnHistory: MarketMapSectionProps["espnHistory"],
  currentHome: number | null,
  currentAway: number | null,
  currentHalf: "1H" | "2H" | null
): { h1Home: number; h1Away: number; h2Home: number | null; h2Away: number | null } | null {
  if (currentHome == null || currentAway == null || !currentHalf) return null;

  if (currentHalf === "1H") {
    return { h1Home: currentHome, h1Away: currentAway, h2Home: null, h2Away: null };
  }

  // 2nd half: need halftime scores
  if (!espnHistory || espnHistory.length === 0) return null;
  const htEntry = espnHistory.find(
    (e) => e.period && /halftime|^ht$/i.test(e.period) && e.home_score != null
  );
  if (!htEntry || htEntry.home_score == null || htEntry.away_score == null) return null;

  return {
    h1Home: htEntry.home_score,
    h1Away: htEntry.away_score,
    h2Home: currentHome - htEntry.home_score,
    h2Away: currentAway - htEntry.away_score,
  };
}

/**
 * `BER by 4.5+` — a MARGIN, not a handicap (#2442).
 *
 * This printed `BER +4.5`: a competitor abbreviation followed by a signed
 * number, which is a betting line and nothing else. Alex quoted it first among
 * the six gambling formats he counted on one screen.
 *
 * The number does not change and neither does what it means. `by N+` states the
 * thing the reader actually wants — how far ahead — in the sport's own units,
 * and it is the wording `MARGIN_LADDER_LABEL` below now shares, so the headline
 * and the ladder cannot drift into two grammars.
 */
function formatMarginLabel(margin: number, teamAbbr: string, threshold: number): string {
  if (margin === 0) return "Tied";
  const val = threshold % 1 === 0 ? Math.abs(threshold) : Math.abs(threshold).toFixed(1);
  return marginLadderLabel(teamAbbr, val);
}

/** One grammar for "this competitor, this far ahead", used by every ladder. */
function marginLadderLabel(teamAbbr: string, threshold: number | string): string {
  return `${teamAbbr} by ${threshold}+`;
}

function deriveAbbr(team: string, provided?: string): string {
  if (provided) return provided;
  const words = team.split(" ");
  return words[words.length - 1].slice(0, 3).toUpperCase();
}

export default function MarketMapSection({
  gameMarkets,
  eventStatus,
  homeTeam,
  awayTeam,
  homeAbbr,
  awayAbbr,
  homeColor,
  awayColor,
  homeLogo,
  awayLogo,
  homeWinProb,
  awayWinProb,
  homeSpread,
  overUnder,
  sportKey,
  espnHistory,
}: MarketMapSectionProps) {
  const hAbbr = deriveAbbr(homeTeam, homeAbbr);
  const aAbbr = deriveAbbr(awayTeam, awayAbbr);
  const vocab = sportVocab(sportKey);

  const isLive = eventStatus === "live";
  const isDone = eventStatus === "completed" || eventStatus === "closed";
  const status = isLive ? "live" : isDone ? "done" : "pre";

  const homeScore = gameMarkets.home_score;
  const awayScore = gameMarkets.away_score;

  const halfScores = useMemo(
    () => deriveHalfScores(espnHistory, homeScore, awayScore),
    [espnHistory, homeScore, awayScore]
  );

  const currentHalf = useMemo(
    () => (isLive ? detectCurrentHalf(espnHistory) : null),
    [isLive, espnHistory]
  );

  const liveHalfScores = useMemo(
    () => (isLive ? deriveLiveHalfScores(espnHistory, homeScore, awayScore, currentHalf) : null),
    [isLive, espnHistory, homeScore, awayScore, currentHalf]
  );

  // ── Margin Map ──
  const marginData = useMemo(() => {
    const fullGameSpreads = (gameMarkets.spreads || []).filter((s) =>
      isFullGameSpread(s.market_name || "")
    );
    if (fullGameSpreads.length === 0) return null;

    const parsedRaw = fullGameSpreads
      .map((s) => parseSpreadOutcome(s.outcome_name, s.probability ?? 0, s.source, homeTeam, awayTeam))
      .filter((p): p is NonNullable<typeof p> => p != null);

    // One rung per (side, threshold). Duplicates arrive when several games'
    // markets are linked to one event; see collapseDuplicateRungs.
    const parsed = collapseDuplicateRungs(
      parsedRaw,
      (p) => `${p.isHome ? "H" : "A"}|${p.threshold}`,
      (p) => p.probability,
    ).rows;

    if (parsed.length === 0) return null;

    // #2441: the rail's reach is DECLARED by the sport, not inferred from a
    // three-name low-scoring list with basketball as the else. That else is
    // what labelled a tennis rail `WAW by 18+ / BER by 18+`.
    const maxMargin = vocab.marginRange;
    const rangeMin = -maxMargin;
    const rangeMax = maxMargin;

    const density = buildDensityFromSpreads(parsed, rangeMin, rangeMax, 12);

    const homeFavored = (homeWinProb ?? 0) > 0.5;
    const favoredAbbr = homeFavored ? hAbbr : aAbbr;
    const favoredProb = homeFavored ? homeWinProb : awayWinProb;
    const headline = favoredProb != null
      ? `${favoredAbbr} ${Math.round(favoredProb * 100)}%`
      : "";

    const markers: MarketMapMarker[] = [];

    // #2441: `homeSpread` is a POINTS figure derived from the moneyline by a
    // model that assumes interchangeable points. On the Berrettini match it
    // produced -4.3 and the page printed `BER +4.5` over a sport with no
    // points. A sport that does not declare `hasDerivedSpread` keeps every
    // market a venue actually quoted and loses only the number we made up —
    // the fallback below still finds the closest-to-50% REAL rung.
    let projValue = vocab.hasDerivedSpread && homeSpread != null ? -homeSpread : null;
    if (projValue == null && parsed.length > 0) {
      const closest = parsed.reduce((best, s) =>
        Math.abs(s.probability - 0.5) < Math.abs(best.probability - 0.5) ? s : best
      );
      projValue = closest.isHome ? closest.threshold : -closest.threshold;
    }
    const projTeamAbbr = projValue != null ? (projValue > 0 ? hAbbr : projValue < 0 ? aAbbr : "TIE") : null;
    const projLogo = projValue != null ? (projValue > 0 ? homeLogo : awayLogo) : undefined;

    // #2442: the SECOND margin formatter on this page, and the one the sweep
    // for `formatMarginLabel` missed — the render guard caught it printing
    // `LAL +4.5` on the projection mark after the ladder had already been
    // fixed. Both now route through `marginLadderLabel`, so there is one
    // grammar and a third copy cannot quietly disagree with the other two.
    function formatMargin(val: number, team: string): string {
      if (val === 0) return "Tied";
      return marginLadderLabel(
        team,
        Math.abs(val) % 1 === 0 ? Math.abs(val) : Math.abs(val).toFixed(1)
      );
    }

    if (status === "pre") {
      if (projValue != null) {
        markers.push({
          key: "proj",
          value: projValue,
          type: "proj",
          label: "Projection",
          displayValue: formatMargin(projValue, projTeamAbbr || ""),
          logoUrl: projLogo,
          logoFallback: projTeamAbbr || "",
        });
      }
    } else if (status === "live") {
      const actualMargin = homeScore != null && awayScore != null ? homeScore - awayScore : null;
      if (actualMargin != null) {
        const actualTeam = actualMargin > 0 ? hAbbr : actualMargin < 0 ? aAbbr : "TIE";
        markers.push({
          key: "actual",
          value: actualMargin,
          type: "actual",
          label: "Actual",
          displayValue: formatMargin(actualMargin, actualTeam),
        });
      }
      if (projValue != null) {
        markers.push({
          key: "pre",
          value: projValue,
          type: "pre",
          label: "Pre-game",
          displayValue: formatMargin(projValue, projTeamAbbr || ""),
        });
        markers.push({
          key: "proj",
          value: projValue,
          type: "proj",
          label: "Projection",
          displayValue: formatMargin(projValue, projTeamAbbr || ""),
          logoUrl: projLogo,
          logoFallback: projTeamAbbr || "",
        });
      }
    } else {
      const finalMargin = homeScore != null && awayScore != null ? homeScore - awayScore : null;
      if (projValue != null) {
        markers.push({
          key: "pre",
          value: projValue,
          type: "pre",
          label: "Pre-game",
          displayValue: formatMargin(projValue, projTeamAbbr || ""),
        });
      }
      if (finalMargin != null) {
        const finalTeam = finalMargin > 0 ? hAbbr : finalMargin < 0 ? aAbbr : "TIE";
        markers.push({
          key: "final",
          value: finalMargin,
          type: "final",
          label: "Final",
          displayValue: formatMargin(finalMargin, finalTeam),
        });
      }
    }

    const ladder: MarketMapLadderRow[] = [];
    const homeSorted = parsed.filter((p) => p.isHome).sort((a, b) => a.threshold - b.threshold);
    const awaySorted = parsed.filter((p) => !p.isHome).sort((a, b) => a.threshold - b.threshold);

    for (const s of awaySorted.reverse()) {
      ladder.push({
        label: marginLadderLabel(aAbbr, s.threshold),
        probability: Math.round(s.probability * 100),
        side: "left",
      });
    }
    for (const s of homeSorted) {
      ladder.push({
        label: marginLadderLabel(hAbbr, s.threshold),
        probability: Math.round(s.probability * 100),
        side: "right",
      });
    }

    return {
      // L2-131 Item 4: a settled game grades the distribution — actual final
      // margin vs the pregame mass — so it reads "expected vs final".
      title: status === "done"
        ? "Margin: expected vs final"
        // #2441: the title is the DECLARED one, not "Full game " + it.
        // Prefixing stuttered the moment a sport's unit was the word "game"
        // ("Full game game margin map"), and every declared title already
        // names the scope. The half maps below carry their own period label,
        // so the contrast this prefix used to draw is still drawn.
        : vocab.marginTitle,
      subtitle: status === "done"
        // #2442: "the pregame spread" is a betting line. What the sentence
        // means is the distribution the market had before play, which is
        // what the reader is looking at on the rail beside it.
        ? "Where it landed vs what was expected"
        : `Final ${vocab.unit === "runs" ? "run-" : vocab.unit === "goals" ? "goal-" : ""}margin distribution`,
      headline,
      rangeMin,
      rangeMax,
      density,
      accentRgb: "37,99,235",
      axisLabels: {
        left: `${aAbbr} by ${maxMargin}+`,
        mid: "0",
        right: `${hAbbr} by ${maxMargin}+`,
      },
      zeroPosition: 0,
      markers,
      ladder,
    };
  }, [gameMarkets.spreads, status, homeScore, awayScore, homeWinProb, awayWinProb, homeSpread, homeTeam, awayTeam, hAbbr, aAbbr, homeLogo, awayLogo, sportKey, vocab]);

  // ── Total Map ──
  const totalData = useMemo(() => {
    const rawTotals = (gameMarkets.totals || [])
      .filter((t) => t.market_type === "game_total" && isGameTotal(t.outcome_name))
      .sort((a, b) => a.threshold - b.threshold);

    if (rawTotals.length === 0) return null;

    // Dedup by threshold (keep highest-volume source), then enforce monotonicity
    const byThresh = new Map<number, typeof rawTotals[0]>();
    for (const t of rawTotals) {
      const existing = byThresh.get(t.threshold);
      if (!existing || (t.bookmaker_count ?? 0) > (existing.bookmaker_count ?? 0)) {
        byThresh.set(t.threshold, t);
      }
    }
    // Filter out resolved/stale thresholds (0% over probability)
    const deduped = [...byThresh.values()]
      .filter((t) => t.over_probability > 0)
      .sort((a, b) => a.threshold - b.threshold);
    // Over probability must decrease as threshold increases.
    // Use a loop so each item is compared against the *corrected* previous
    // value, not the original.
    const gameTotals: typeof deduped = [];
    for (const t of deduped) {
      if (gameTotals.length === 0) {
        gameTotals.push(t);
      } else {
        const prevProb = gameTotals[gameTotals.length - 1].over_probability;
        if (t.over_probability > prevProb) {
          gameTotals.push({ ...t, over_probability: prevProb });
        } else {
          gameTotals.push(t);
        }
      }
    }

    if (gameTotals.length === 0) return null;

    const ouLine = gameTotals.reduce((closest, t) =>
      Math.abs(t.over_probability - 0.5) < Math.abs(closest.over_probability - 0.5) ? t : closest
    );

    const minThresh = gameTotals[0].threshold;
    const maxThresh = gameTotals[gameTotals.length - 1].threshold;
    const actualTotal = homeScore != null && awayScore != null ? homeScore + awayScore : null;
    const paceProj = gameMarkets.pace?.projected_total ?? null;
    const allValues = [minThresh, maxThresh];
    if (actualTotal != null) allValues.push(actualTotal);
    if (paceProj != null) allValues.push(paceProj);
    if (overUnder != null) allValues.push(overUnder);
    const dataMin = Math.min(...allValues);
    const dataMax = Math.max(...allValues);
    const span = dataMax - dataMin;
    const pad = Math.max(span * 0.15, 3);
    const rangeMin = Math.max(0, Math.floor(dataMin - pad));
    const rangeMax = Math.ceil(dataMax + pad);

    const density = buildDensityFromThresholds(
      gameTotals.map((t) => ({ threshold: t.threshold, overProbability: t.over_probability })),
      rangeMin,
      rangeMax,
      12
    );

    const pace = gameMarkets.pace;
    const scored = pace?.total_scored ?? (homeScore != null && awayScore != null ? homeScore + awayScore : null);
    const projected = pace?.projected_total ?? null;
    const ouVal = overUnder ?? ouLine.threshold;

    const headlineValue = status === "pre"
      ? `Projected ${Math.round(ouVal)}`
      : status === "live" && projected != null
      ? `Projected ${Math.round(projected)}`
      : "";

    const markers: MarketMapMarker[] = [];

    if (status === "pre") {
      markers.push({
        key: "proj",
        value: ouVal,
        type: "proj",
        label: "Projection",
        displayValue: String(Math.round(ouVal)),
        hideTile: true,
      });
    } else if (status === "live") {
      if (scored != null) {
        markers.push({
          key: "actual",
          value: scored,
          type: "actual",
          label: "Actual",
          displayValue: withUnit(scored, vocab),
        });
      }
      markers.push({
        key: "pre",
        value: ouVal,
        type: "pre",
        label: "Pre-game",
        displayValue: String(Math.round(ouVal)),
      });
      if (projected != null) {
        markers.push({
          key: "proj",
          value: projected,
          type: "proj",
          label: "Projection",
          displayValue: String(projected.toFixed(1)),
          logoFallback: String(projected.toFixed(1)),
        });
      }
    } else {
      markers.push({
        key: "pre",
        value: ouVal,
        type: "pre",
        label: "Pre-game",
        displayValue: String(Math.round(ouVal)),
      });
      if (scored != null) {
        markers.push({
          key: "final",
          value: scored,
          type: "final",
          label: "Final",
          displayValue: withUnit(scored, vocab),
        });
      }
    }

    const ladder: MarketMapLadderRow[] = gameTotals.map((t) => ({
      label: `Over ${t.threshold}`,
      probability: Math.round(t.over_probability * 100),
      side: "right" as const,
    }));

    const midLabel = String(Math.round((rangeMin + rangeMax) / 2));

    return {
      // L2-131 Item 4: settled totals grade expected vs final, same as margins.
      title: status === "done"
        ? "Total: expected vs final"
        : vocab.totalTitle,
      subtitle: status === "done"
        // #2442's wording, through #2441's unit helper: an undeclared sport
        // has no unit to interpolate, and inlining it produced "Final
        // distribution" with a double space.
        ? "Where it landed vs what was expected"
        : unitPhrase("Final", vocab, "distribution"),
      headline: headlineValue,
      rangeMin,
      rangeMax,
      density,
      accentRgb: "124,58,237",
      axisLabels: { left: String(rangeMin), mid: midLabel, right: `${rangeMax}+` },
      markers,
      ladder,
    };
  }, [gameMarkets.totals, gameMarkets.pace, status, homeScore, awayScore, overUnder, vocab, sportKey]);

  // Helper: derive period from backend "period" field, falling back to text matching.
  function derivePeriod(item: { period?: string | null; outcome_name: string; market_name: string }): string {
    if (item.period) return item.period;
    const text = `${item.outcome_name} ${item.market_name || ""}`.toLowerCase();
    if (text.includes("1h") || text.includes("1st") || text.includes("first")) return "1H";
    if (text.includes("2h") || text.includes("2nd") || text.includes("second")) return "2H";
    return "2H"; // default
  }

  // ── Period Margin Maps (half spreads) ──
  const halfMarginMaps = useMemo(() => {
    const halfSpreads = (gameMarkets.period_markets || []).filter((s) => s.market_type === "half_spread");
    const halfGroups: Record<string, typeof halfSpreads> = {};
    for (const s of halfSpreads) {
      const key = derivePeriod(s);
      if (!halfGroups[key]) halfGroups[key] = [];
      halfGroups[key].push(s);
    }

    type MapData = Parameters<typeof MarketMap>[0] & { status: "pre" | "live" | "done" };
    const maps: Array<{ key: string; data: MapData }> = [];

    for (const half of ["1H", "2H"] as const) {
      const spreads = halfGroups[half];
      if (!spreads || spreads.length === 0) continue;

      const rawParsedAll = spreads
        .map((s) => parseSpreadOutcome(s.outcome_name, s.probability ?? 0, s.source, homeTeam, awayTeam))
        .filter((p): p is NonNullable<typeof p> => p != null);
      // Collapse before the monotonicity pass: equal duplicates satisfy
      // `prob <= lastProb` trivially, so that guard cannot remove them.
      const rawParsed = collapseDuplicateRungs(
        rawParsedAll,
        (p) => `${p.isHome ? "H" : "A"}|${p.threshold}`,
        (p) => p.probability,
      ).rows;
      if (rawParsed.length === 0) continue;

      // Enforce monotonicity per team: P(team wins by X) >= P(team wins by X+Y)
      const enforceMonotonic = (items: typeof rawParsed): typeof rawParsed => {
        const sorted = [...items].sort((a, b) => a.threshold - b.threshold);
        const clean: typeof rawParsed = [];
        let lastProb = 1.0;
        for (const s of sorted) {
          if (s.probability <= lastProb) {
            clean.push(s);
            lastProb = s.probability;
          }
        }
        return clean;
      };

      const homeClean = enforceMonotonic(rawParsed.filter((p) => p.isHome));
      const awayClean = enforceMonotonic(rawParsed.filter((p) => !p.isHome));
      const parsed = [...homeClean, ...awayClean];
      if (parsed.length === 0) continue;

      // #2441: same declared reach as the full-game rail above.
      const maxM = vocab.marginRange;
      const density = buildDensityFromSpreads(parsed, -maxM, maxM, 12);

      // Ladder: sort sequentially along number line (away big → tie → home big)
      const allSorted = [...parsed].sort((a, b) => {
        const marginA = a.isHome ? a.threshold : -a.threshold;
        const marginB = b.isHome ? b.threshold : -b.threshold;
        return marginA - marginB;
      });
      const ladder: MarketMapLadderRow[] = allSorted.map((s) => ({
        label: marginLadderLabel(s.isHome ? hAbbr : aAbbr, s.threshold),
        probability: Math.round(s.probability * 100),
        side: (s.isHome ? "right" : "left") as "left" | "right",
      }));

      // Find the closest-to-50% spread as the projection marker
      const closest50 = parsed.reduce((best, s) =>
        Math.abs(s.probability - 0.5) < Math.abs(best.probability - 0.5) ? s : best
      );
      const projMargin = closest50.isHome ? closest50.threshold : -closest50.threshold;
      const projTeam = projMargin > 0 ? hAbbr : projMargin < 0 ? aAbbr : "TIE";

      const label = half === "1H" ? "1st half" : "2nd half";

      const halfMarkers: MarketMapMarker[] = [];

      // Live actual for in-progress games (first, matching full game order)
      if (isLive && liveHalfScores) {
        const hs = half === "1H"
          ? { home: liveHalfScores.h1Home, away: liveHalfScores.h1Away }
          : liveHalfScores.h2Home != null && liveHalfScores.h2Away != null
            ? { home: liveHalfScores.h2Home, away: liveHalfScores.h2Away }
            : null;
        if (hs) {
          const margin = hs.home - hs.away;
          const team = margin > 0 ? hAbbr : margin < 0 ? aAbbr : "TIE";
          halfMarkers.push({
            key: "actual",
            value: margin,
            type: "actual",
            label: "Actual",
            displayValue: margin === 0 ? "Tied" : `${team} +${Math.abs(margin)}`,
          });
        }
      }

      // Projection / Pre-game spread
      halfMarkers.push({
        key: "proj",
        value: projMargin,
        type: isDone ? "pre" : "proj",
        label: isDone ? "Pre-game" : "Projection",
        displayValue: formatMarginLabel(projMargin, projTeam, closest50.threshold),
        logoFallback: projTeam,
      });

      // Final actual for completed games
      if (isDone && halfScores) {
        const hs = half === "1H"
          ? { home: halfScores.h1Home, away: halfScores.h1Away }
          : { home: halfScores.h2Home, away: halfScores.h2Away };
        const margin = hs.home - hs.away;
        const team = margin > 0 ? hAbbr : margin < 0 ? aAbbr : "TIE";
        halfMarkers.push({
          key: "final",
          value: margin,
          type: "final",
          label: "Final",
          displayValue: margin === 0 ? "Tied" : `${team} +${Math.abs(margin)}`,
        });
      }

      maps.push({
        key: `margin-${half}`,
        data: {
          variant: "margin" as const,
          title: `${label} margin`,
          subtitle: `${label} margin distribution`,
          headline: "",
          rangeMin: -maxM,
          rangeMax: maxM,
          density,
          accentRgb: "37,99,235",
          axisLabels: { left: `${aAbbr} by ${maxM}+`, mid: "Tie", right: `${hAbbr} by ${maxM}+` },
          zeroPosition: 0,
          markers: halfMarkers,
          ladder,
          status,
        },
      });
    }
    return maps;
  }, [gameMarkets.period_markets, status, homeTeam, awayTeam, hAbbr, aAbbr, sportKey, isDone, isLive, halfScores, liveHalfScores, homeLogo, awayLogo]);

  // ── Period Total Maps (half totals) ──
  const halfTotalMaps = useMemo(() => {
    const allPeriod = gameMarkets.period_markets || [];
    type MapData = Parameters<typeof MarketMap>[0] & { status: "pre" | "live" | "done" };
    const maps: Array<{ key: string; data: MapData }> = [];

    // Group half_total markets by period using backend-supplied "period"
    // field (derived from ticker prefix).  Falls back to name-based
    // matching via derivePeriod() for older data without the field.
    const halfTotalAll = allPeriod.filter(
      (p) => p.market_type === "half_total" && isGameTotal(p.outcome_name)
    );
    const halfTotalGroups: Record<string, typeof halfTotalAll> = {};
    for (const item of halfTotalAll) {
      const key = derivePeriod(item);
      if (!halfTotalGroups[key]) halfTotalGroups[key] = [];
      halfTotalGroups[key].push(item);
    }

    for (const halfKey of ["1H", "2H"] as const) {
      const halfItemsRaw = halfTotalGroups[halfKey] || [];
      // One rung per threshold, before the monotonicity pass and before the
      // density/O-U reduce that duplicated points would skew.
      const halfItems = collapseDuplicateRungs(
        halfItemsRaw,
        (t) => String(t.threshold ?? 0),
        (t) => t.over_probability ?? t.probability ?? 0,
      ).rows;
      if (halfItems.length < 2) continue;

      const sorted = [...halfItems].sort((a, b) => (a.threshold ?? 0) - (b.threshold ?? 0));

      // Enforce monotonicity: over_probability should decrease as threshold increases
      const cleaned: Array<{ threshold: number; overProbability: number }> = [];
      let lastProb = 1.0;
      for (const t of sorted) {
        const prob = t.over_probability ?? t.probability ?? 0;
        if (prob <= lastProb) {
          cleaned.push({ threshold: t.threshold ?? 0, overProbability: prob });
          lastProb = prob;
        }
      }
      if (cleaned.length < 2) continue;

      const ouLine = cleaned.reduce((best, t) =>
        Math.abs(t.overProbability - 0.5) < Math.abs(best.overProbability - 0.5) ? t : best
      );

      const dataMin = cleaned[0].threshold;
      const dataMax = cleaned[cleaned.length - 1].threshold;
      const span = dataMax - dataMin;
      const pad = Math.max(span * 0.15, 3);
      const rangeMin = Math.max(0, Math.floor(dataMin - pad));
      const rangeMax = Math.ceil(dataMax + pad);
      const density = buildDensityFromThresholds(cleaned, rangeMin, rangeMax, 12);

      const ladder = cleaned.map((t) => ({
        label: `Over ${t.threshold}`,
        probability: Math.round(t.overProbability * 100),
        side: "right" as const,
      }));

      const midLabel = String(Math.round((rangeMin + rangeMax) / 2));
      const label = halfKey === "1H" ? "1st half" : "2nd half";

      const halfTotalMarkers: MarketMapMarker[] = [];

      // Live actual for in-progress games (first, matching full game order)
      if (isLive && liveHalfScores) {
        const ht = halfKey === "1H"
          ? liveHalfScores.h1Home + liveHalfScores.h1Away
          : liveHalfScores.h2Home != null && liveHalfScores.h2Away != null
            ? liveHalfScores.h2Home + liveHalfScores.h2Away
            : null;
        if (ht != null) {
          halfTotalMarkers.push({
            key: "actual",
            value: ht,
            type: "actual",
            label: "Actual",
            displayValue: withUnit(ht, vocab),
          });
        }
      }

      // Pre-game O/U
      halfTotalMarkers.push({
        key: "pre",
        value: ouLine.threshold,
        type: "pre",
        label: "Pre-game",
        displayValue: String(Math.round(ouLine.threshold)),
      });

      // Final actual for completed games
      if (isDone && halfScores) {
        const ht = halfKey === "1H"
          ? halfScores.h1Home + halfScores.h1Away
          : halfScores.h2Home + halfScores.h2Away;
        halfTotalMarkers.push({
          key: "final",
          value: ht,
          type: "final",
          label: "Final",
          displayValue: withUnit(ht, vocab),
        });
      }

      // Compute range that includes all marker values
      const allVals = halfTotalMarkers.map((m) => m.value);
      const effectiveMin = Math.max(0, Math.floor(Math.min(dataMin, ...allVals) - Math.max(span * 0.15, 3)));
      const effectiveMax = Math.ceil(Math.max(dataMax, ...allVals) + Math.max(span * 0.15, 3));
      const effectiveDensity = buildDensityFromThresholds(cleaned, effectiveMin, effectiveMax, 12);
      const effectiveMid = String(Math.round((effectiveMin + effectiveMax) / 2));

      const headlineVal = isDone ? "" : `O/U ${Math.round(ouLine.threshold)}`;

      maps.push({
        key: `total-${halfKey}`,
        data: {
          variant: "total" as const,
          title: `${label} ${vocab.totalTitle.toLowerCase()}`,
          subtitle: unitPhrase(label, vocab, "distribution"),
          headline: headlineVal,
          rangeMin: effectiveMin,
          rangeMax: effectiveMax,
          density: effectiveDensity,
          accentRgb: "124,58,237",
          axisLabels: { left: String(effectiveMin), mid: effectiveMid, right: `${effectiveMax}+` },
          markers: halfTotalMarkers,
          ladder,
          status,
        },
      });
    }
    return maps;
  }, [gameMarkets.period_markets, status, vocab, isDone, isLive, halfScores, liveHalfScores]);

  const hasMargin = marginData || halfMarginMaps.length > 0;
  const hasTotal = totalData || halfTotalMaps.length > 0;

  if (!hasMargin && !hasTotal) return null;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      {/* Left column: Margin maps grouped */}
      {hasMargin && (
        <div className="rounded-2xl border border-surface-border bg-surface-card/50 p-2 space-y-2">
          <div className="px-2 pt-1 text-[10px] font-black uppercase tracking-widest text-text-muted">
            {/* #2442, CERT-642's second finding. "Total maps" is the betting
                noun for an over/under and it survived the first sweep because
                the guard's fixture supplied no totals, so this column never
                rendered. Both headings now come from the sport's declared
                vocabulary, like the titles inside them.

                #2441 adds the empty-unit arm: an UNDECLARED sport has no unit
                to build a heading from, and interpolating one produces " maps".
                So it falls back to the plain noun rather than to a guess. */}
            {vocab.unit ? `${vocab.marginTitle.replace(/ map$/, "")} maps` : "Margin maps"}
          </div>
          {marginData && (
            <MarketMap variant="margin" {...marginData} status={status} />
          )}
          {halfMarginMaps.map((pm) => (
            <MarketMap key={pm.key} {...pm.data} />
          ))}
        </div>
      )}

      {/* Right column: Total maps grouped */}
      {hasTotal && (
        <div className="rounded-2xl border border-surface-border bg-surface-card/50 p-2 space-y-2">
          <div className="px-2 pt-1 text-[10px] font-black uppercase tracking-widest text-text-muted">
            {vocab.unit ? `${vocab.totalTitle.replace(/ map$/, "")} maps` : "Scoring maps"}
          </div>
          {totalData && (
            <MarketMap variant="total" {...totalData} status={status} />
          )}
          {halfTotalMaps.map((pm) => (
            <MarketMap key={pm.key} {...pm.data} />
          ))}
        </div>
      )}
    </div>
  );
}
