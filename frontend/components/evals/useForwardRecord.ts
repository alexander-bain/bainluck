"use client";

import { useMemo } from "react";
import useSWR from "swr";

import { fetchCalibration } from "@/lib/api";
import { forwardRecordView, type ForwardRecordView } from "@/lib/evals/forwardRecord";
import type { MeasuredTruth } from "@/lib/evals/truth";

export type ForwardRecordState =
  | { status: "loading" }
  | { status: "unavailable" }
  | { status: "ready"; view: ForwardRecordView; truth: MeasuredTruth };

const SOURCE = { label: "The live calibration record", href: "https://api.bainluck.com/api/calibration" };

/**
 * The live record, read once when the page opens.
 *
 * The SWR key is `/calibration`'s own, so a reader arriving from the accuracy
 * page reuses the payload it already holds and the hero tile and the section
 * share one request. The payload is about 612 KB (94 KB on the wire); the hero
 * tile needs it on the first screen, so it is read at open, as `/about` reads it.
 *
 * Fail closed: a failed read — including a failed refresh of a payload already
 * in hand — is "Unavailable right now", never an older number (the plan's LIVE
 * rule). A payload without its own `generated_at` cannot say when it is true,
 * so it is unavailable too.
 */
export function useForwardRecord(): ForwardRecordState {
  const { data, error } = useSWR("calibration-data", fetchCalibration, { revalidateOnFocus: false });
  return useMemo(() => {
    if (error) return { status: "unavailable" };
    if (!data) return { status: "loading" };
    const view = forwardRecordView(data);
    if (!view.generatedAt) return { status: "unavailable" };
    return { status: "ready", view, truth: { kind: "live", asOf: view.generatedAt, source: SOURCE } };
  }, [data, error]);
}
