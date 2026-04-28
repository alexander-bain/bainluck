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
  posOnRail,
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
}: MarketMapSectionProps) {
  const hAbbr = deriveAbbr(homeTeam, homeAbbr);
  const aAbbr = deriveAbbr(awayTeam, awayAbbr);
  const vocab = sportVocab(sportKey);

  const isLive = eventStatus === "live";
  const isDone = eventStatus === "completed" || eventStatus === "closed";
  const status = isLive ? "live" : isDone ? "done" : "pre";

  const homeScore = gameMarkets.home_score;
  const awayScore = gameMarkets.away_score;

  // ── Margin Map ──
  const marginData = useMemo(() => {
    const fullGameSpreads = (gameMarkets.spreads || []).filter((s) =>
      isFullGameSpread(s.market_name || "")
    );
    if (fullGameSpreads.length === 0) return null;

    const parsed = fullGameSpreads
      .map((s) => parseSpreadOutcome(s.outcome_name, s.probability ?? 0, s.source, homeTeam, awayTeam))
      .filter((p): p is NonNullable<typeof p> => p != null);

    if (parsed.length === 0) return null;

    const sportKey_ = (sportKey || "").toLowerCase();
    const isLowScoring = sportKey_.includes("baseball") || sportKey_.includes("hockey") || sportKey_.includes("soccer");
    const maxMargin = isLowScoring ? 5 : 18;
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

    let projValue = homeSpread != null ? -homeSpread : null;
    if (projValue == null && parsed.length > 0) {
      const closest = parsed.reduce((best, s) =>
        Math.abs(s.probability - 0.5) < Math.abs(best.probability - 0.5) ? s : best
      );
      projValue = closest.isHome ? closest.threshold : -closest.threshold;
    }
    const projTeamAbbr = projValue != null ? (projValue > 0 ? hAbbr : projValue < 0 ? aAbbr : "TIE") : null;
    const projLogo = projValue != null ? (projValue > 0 ? homeLogo : awayLogo) : undefined;

    function formatMargin(val: number, team: string): string {
      if (val === 0) return "Tied";
      return `${team} +${Math.abs(val) % 1 === 0 ? Math.abs(val) : Math.abs(val).toFixed(1)}`;
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
        label: `${aAbbr} +${s.threshold}`,
        probability: Math.round(s.probability * 100),
        side: "left",
      });
    }
    for (const s of homeSorted) {
      ladder.push({
        label: `${hAbbr} +${s.threshold}`,
        probability: Math.round(s.probability * 100),
        side: "right",
      });
    }

    return {
      title: vocab.marginTitle,
      subtitle: `Final ${vocab.unit === "runs" ? "run-" : vocab.unit === "goals" ? "goal-" : ""}margin distribution`,
      headline,
      rangeMin,
      rangeMax,
      density,
      accentRgb: "37,99,235",
      axisLabels: {
        left: `${aAbbr} by ${maxMargin}+`,
        mid: "Tie",
        right: `${hAbbr} by ${maxMargin}+`,
      },
      zeroPosition: 0,
      markers,
      ladder,
    };
  }, [gameMarkets.spreads, status, homeScore, awayScore, homeWinProb, awayWinProb, homeSpread, homeTeam, awayTeam, hAbbr, aAbbr, homeLogo, awayLogo, sportKey, vocab]);

  // ── Total Map ──
  const totalData = useMemo(() => {
    const gameTotals = (gameMarkets.totals || [])
      .filter((t) => t.market_type === "game_total" && isGameTotal(t.outcome_name))
      .sort((a, b) => a.threshold - b.threshold);

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
          displayValue: `${scored} ${vocab.unit}`,
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
          displayValue: `${scored} ${vocab.unit}`,
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
      title: vocab.totalTitle,
      subtitle: `Final ${vocab.unit} distribution`,
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

  // ── Period Margin Maps (half spreads) ──
  const halfMarginMaps = useMemo(() => {
    const halfSpreads = (gameMarkets.spreads || []).filter((s) => !isFullGameSpread(s.market_name || ""));
    const halfGroups: Record<string, typeof halfSpreads> = {};
    for (const s of halfSpreads) {
      const on = s.outcome_name.toLowerCase();
      const key = on.includes("1h") || on.includes("1st") || on.includes("first") ? "1H" : "2H";
      if (!halfGroups[key]) halfGroups[key] = [];
      halfGroups[key].push(s);
    }

    type MapData = Parameters<typeof MarketMap>[0] & { status: "pre" | "live" | "done" };
    const maps: Array<{ key: string; data: MapData }> = [];

    for (const half of ["1H", "2H"] as const) {
      const spreads = halfGroups[half];
      if (!spreads || spreads.length === 0) continue;

      const rawParsed = spreads
        .map((s) => parseSpreadOutcome(s.outcome_name, s.probability ?? 0, s.source, homeTeam, awayTeam))
        .filter((p): p is NonNullable<typeof p> => p != null);
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

      const sportKey_ = (sportKey || "").toLowerCase();
      const isLowScoring = sportKey_.includes("baseball") || sportKey_.includes("hockey");
      const maxM = isLowScoring ? 5 : 18;
      const density = buildDensityFromSpreads(parsed, -maxM, maxM, 12);

      // Ladder: sort sequentially along number line (away big → tie → home big)
      const allSorted = [...parsed].sort((a, b) => {
        const marginA = a.isHome ? a.threshold : -a.threshold;
        const marginB = b.isHome ? b.threshold : -b.threshold;
        return marginA - marginB;
      });
      const ladder: MarketMapLadderRow[] = allSorted.map((s) => ({
        label: `${s.isHome ? hAbbr : aAbbr} +${s.threshold}`,
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
          markers: [{
            key: "proj",
            value: projMargin,
            type: "proj" as const,
            label: "Projection",
            displayValue: `${projTeam} +${Math.abs(closest50.threshold)}`,
            logoFallback: projTeam,
            hideTile: true,
          }],
          ladder,
          status,
        },
      });
    }
    return maps;
  }, [gameMarkets.spreads, status, homeTeam, awayTeam, hAbbr, aAbbr, sportKey]);

  // ── Period Total Maps (half totals) ──
  const halfTotalMaps = useMemo(() => {
    const allPeriod = gameMarkets.period_markets || [];
    type MapData = Parameters<typeof MarketMap>[0] & { status: "pre" | "live" | "done" };
    const maps: Array<{ key: string; data: MapData }> = [];

    for (const halfKey of ["1H", "2H"] as const) {
      const pattern = halfKey === "1H" ? /1h/i : /2h/i;
      const halfItems = allPeriod.filter(
        (p) => p.market_type === "half_total" && pattern.test(p.outcome_name) && isGameTotal(p.outcome_name)
      );
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

      maps.push({
        key: `total-${halfKey}`,
        data: {
          variant: "total" as const,
          title: `${label} ${vocab.totalTitle.toLowerCase()}`,
          subtitle: `${label} ${vocab.unit} distribution`,
          headline: `O/U ${Math.round(ouLine.threshold)}`,
          rangeMin,
          rangeMax,
          density,
          accentRgb: "124,58,237",
          axisLabels: { left: String(rangeMin), mid: midLabel, right: `${rangeMax}+` },
          markers: [{ key: "ou", value: ouLine.threshold, type: "pre" as const, label: "O/U", displayValue: String(Math.round(ouLine.threshold)), hideTile: true }],
          ladder,
          status,
        },
      });
    }
    return maps;
  }, [gameMarkets.period_markets, status, vocab]);

  const hasMargin = marginData || halfMarginMaps.length > 0;
  const hasTotal = totalData || halfTotalMaps.length > 0;

  if (!hasMargin && !hasTotal) return null;

  return (
    <div className="grid grid-cols-2 gap-3">
      {/* Left column: Margin maps grouped */}
      {hasMargin && (
        <div className="rounded-2xl border border-surface-border bg-surface-card/50 p-2 space-y-2">
          <div className="px-2 pt-1 text-[10px] font-black uppercase tracking-widest text-text-muted">
            Margin maps
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
            Total maps
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
