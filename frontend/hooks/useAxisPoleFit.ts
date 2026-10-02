"use client";

import { useLayoutEffect, useRef, useState } from "react";
import {
  readAxisPoleLayout,
  type AxisGutterNode,
  type AxisPoleCaps,
  type AxisPoleNeedCache,
} from "@/lib/axisPoleFit";

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
 *
 * #10156 — `codes` (from `axisCodePair`) lets a chart print both teams' codes
 * instead of cutting a name; `labels` is what the poles should print. Without
 * `codes`, `labels` is always the names and the caps are #8392's.
 */
export function useAxisPoleFit(
  homeLabel: string,
  awayLabel: string,
  codes: { home: string; away: string } | null = null,
): {
  gutterRef: (el: HTMLElement | null) => void;
  caps: AxisPoleCaps;
  labels: { home: string; away: string };
} {
  const [gutter, setGutter] = useState<HTMLElement | null>(null);
  const [caps, setCaps] = useState<AxisPoleCaps>({ home: null, away: null });
  const [useCodes, setUseCodes] = useState(false);
  const last = useRef(caps);
  const lastUseCodes = useRef(useCodes);
  const needCache = useRef<AxisPoleNeedCache>({});
  const codeHome = codes?.home ?? null;
  const codeAway = codes?.away ?? null;

  useLayoutEffect(() => {
    if (!gutter) return;

    const measure = () => {
      const style = window.getComputedStyle(gutter);
      // The poles' children are HTMLElements; the DOM types them as Element.
      const layout = readAxisPoleLayout(
        gutter as unknown as AxisGutterNode,
        parseFloat(style.paddingTop),
        parseFloat(style.paddingBottom),
        { home: homeLabel, away: awayLabel },
        codeHome !== null && codeAway !== null ? { home: codeHome, away: codeAway } : null,
        needCache.current,
      );
      const next = layout.caps;
      if (next.home !== last.current.home || next.away !== last.current.away) {
        last.current = next;
        setCaps(next);
      }
      if (layout.useCodes !== lastUseCodes.current) {
        lastUseCodes.current = layout.useCodes;
        setUseCodes(layout.useCodes);
      }
    };

    measure();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(gutter);
    return () => observer.disconnect();
  }, [gutter, homeLabel, awayLabel, codeHome, codeAway, useCodes]);

  const labels =
    useCodes && codeHome !== null && codeAway !== null
      ? { home: codeHome, away: codeAway }
      : { home: homeLabel, away: awayLabel };
  return { gutterRef: setGutter, caps, labels };
}
