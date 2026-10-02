"use client";

import { useCallback, useEffect, useMemo, useRef } from "react";
import useSWR from "swr";
import { fetchProbabilityTimeline } from "@/lib/api";
import type {
  FuturesHistoryResponse,
  FuturesMarketDetailResponse,
  ProbabilityTimelineResponse,
} from "@/lib/types";
import {
  VERIFIED_TIMELINE_TOP,
  VERIFIED_TITLE,
  chartCurrentAgrees,
  historyBasisLabel,
  isVerifiedTitle,
  timelineToChartHistory,
  verifiedChartVerdict,
  type VerifiedChartVerdict,
} from "@/lib/verifiedTitleDetail";

/** A timeline response with the request it answers, so a reply for another
 *  market or range can never be judged against this detail. */
interface Answered {
  marketId: number;
  hours: number;
  payload: ProbabilityTimelineResponse;
}

export interface VerifiedTitleChart {
  /** The detail is effectively verified, so the chart is this hook's. */
  active: boolean;
  history: FuturesHistoryResponse | undefined;
  error: Error | undefined;
  isLoading: boolean;
  /** "Sportsbooks history" — from the timeline response on screen. */
  label: string | null;
  verdict: VerifiedChartVerdict;
  /** A stream re-read's timeline, for the range it was asked for. */
  adopt: (timeline: ProbabilityTimelineResponse, hours: number) => Promise<unknown>;
  refresh: () => Promise<unknown>;
}

/** How long a mismatch must outlive its own arrival before the one retry
 *  fires. A stream read lands its detail a moment before its paired timeline;
 *  without this, every changed stream read would spend a redundant request. */
export const VERIFIED_CHART_RETRY_SETTLE_MS = 1_500;

/**
 * #10224 — the futures detail chart when its detail is effectively
 * `verified_title`: the opted-in `/probability-timeline`, adapted to
 * `FuturesChart`, labelled by its own `history_basis`.
 *
 * The detail and the chart are two requests and can describe two moments. When
 * the hero and the chart's current column disagree, the chart is re-asked ONCE
 * for this detail object and range; a disagreement after that keeps the
 * history and drops the chart's current metadata. A new detail (a refresh or a
 * stream read) or a new range is a new generation with its own one retry.
 */
export function useVerifiedTitleChart(options: {
  marketId: number;
  market: FuturesMarketDetailResponse | undefined;
  hours: number;
  heroId: number | null;
  retrySettleMs?: number;
}): VerifiedTitleChart {
  const { marketId, market, hours, heroId } = options;
  const settleMs = options.retrySettleMs ?? VERIFIED_CHART_RETRY_SETTLE_MS;
  const active = !!market && market.id === marketId && isVerifiedTitle(market);

  const { data, error, isLoading, isValidating, mutate } = useSWR<Answered, Error>(
    active ? ["futures-verified-timeline", marketId, hours] : null,
    async () => ({
      marketId,
      hours,
      payload: await fetchProbabilityTimeline(marketId, VERIFIED_TIMELINE_TOP, hours, {
        representation: VERIFIED_TITLE,
      }),
    }),
    // Same holding rule as the source chart (#7545): the previous range stays
    // on screen while the next loads, so a chip tap never removes the chips.
    { keepPreviousData: true, revalidateOnFocus: false, revalidateOnReconnect: false },
  );

  // Shown: any answer for this market (incl. the range being left). Judged: only
  // the answer for exactly this market and range.
  const shown = data && data.marketId === marketId ? data : undefined;
  const judged = shown && shown.hours === hours && shown.payload.market_id === marketId ? shown : undefined;

  const retried = useRef<{ market: FuturesMarketDetailResponse; hours: number } | null>(null);
  const retriedThisGeneration =
    !!market && retried.current?.market === market && retried.current.hours === hours;
  const agrees =
    active && judged && market ? chartCurrentAgrees(market, judged.payload, heroId) : null;
  const verdict = verifiedChartVerdict(agrees, retriedThisGeneration);

  useEffect(() => {
    if (verdict !== "retry" || isValidating || !market) return;
    // Cancelled if anything it depends on moves first — e.g. the paired
    // timeline of the same stream read arrives and the two agree.
    const timer = setTimeout(() => {
      retried.current = { market, hours };
      void mutate();
    }, settleMs);
    return () => clearTimeout(timer);
  }, [verdict, isValidating, market, hours, mutate, settleMs]);

  const adopt = useCallback(
    (timeline: ProbabilityTimelineResponse, askedHours: number) =>
      // The SWR key carries the range, so a re-read for a range the reader has
      // since left lands in that range's cache, never on this chart.
      mutate(
        (prior) =>
          askedHours === hours && timeline.market_id === marketId
            ? { marketId, hours: askedHours, payload: timeline }
            : prior,
        { revalidate: false },
      ),
    [mutate, hours, marketId],
  );
  const refresh = useCallback(() => (active ? mutate() : Promise.resolve(undefined)), [active, mutate]);

  const withCurrent = verdict === "agree";
  const payload = active ? shown?.payload : undefined;
  const history = useMemo(
    () => (payload ? timelineToChartHistory(payload, { withCurrent }) : undefined),
    [payload, withCurrent],
  );

  return {
    active,
    history,
    error: active ? error : undefined,
    isLoading: active && isLoading,
    label: active && shown ? historyBasisLabel(shown.payload.history_basis) : null,
    verdict,
    adopt,
    refresh,
  };
}
