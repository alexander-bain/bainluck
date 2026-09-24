"use client";

import { useLayoutEffect, useRef, useState } from "react";
import { readAxisPoleCaps, type AxisGutterNode, type AxisPoleCaps } from "@/lib/axisPoleFit";

/**
 * #8392 — measures a chart's side gutter and its two team-name poles, and
 * returns the pixel cap for each pole (`readAxisPoleCaps` / `allocateAxisPoles`
 * carry the rule). The gutter's first two children are the poles (home on top,
 * away below); the element inside each marked `data-axis-label` is the name.
 *
 * `gutterRef` is a CALLBACK ref kept in state, not a `useRef`: both charts
 * render an empty state with no gutter first and mount it when data arrives,
 * with the team names unchanged — a ref object would never tell the effect the
 * gutter had appeared, and the long name would overlap exactly as before.
 *
 * Until layout has been measured (server render, first paint) both caps are
 * `null`, which is the chart exactly as it was before this hook existed.
 */
export function useAxisPoleFit(
  homeLabel: string,
  awayLabel: string,
): { gutterRef: (el: HTMLElement | null) => void; caps: AxisPoleCaps } {
  const [gutter, setGutter] = useState<HTMLElement | null>(null);
  const [caps, setCaps] = useState<AxisPoleCaps>({ home: null, away: null });
  const last = useRef(caps);

  useLayoutEffect(() => {
    if (!gutter) return;

    const measure = () => {
      const style = window.getComputedStyle(gutter);
      // The poles' children are HTMLElements; the DOM types them as Element.
      const next = readAxisPoleCaps(
        gutter as unknown as AxisGutterNode,
        parseFloat(style.paddingTop),
        parseFloat(style.paddingBottom),
      );
      if (next.home !== last.current.home || next.away !== last.current.away) {
        last.current = next;
        setCaps(next);
      }
    };

    measure();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(gutter);
    return () => observer.disconnect();
  }, [gutter, homeLabel, awayLabel]);

  return { gutterRef: setGutter, caps };
}
