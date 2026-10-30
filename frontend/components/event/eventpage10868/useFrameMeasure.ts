"use client";

/**
 * #10868 — the hockey journey's one reading of the reader's layout: a frame's
 * own width and the reader's text size. Shared by the points/assists card (its
 * milestone rail and player chooser) and the history chart (its axis labels),
 * so every part of the screen agrees on when text counts as enlarged.
 *
 * Web has no Dynamic Type category, so an accessibility text size is read the
 * way `usePlotBox` (NFLEventCards.tsx) reads enlarged text — the root font size
 * — at or above `ACCESSIBILITY_ROOT_FONT_PX` (150% of the 16 px default).
 * Imports nothing from lib: it states no verdict and joins no census.
 */

import { useEffect, useLayoutEffect, useState, type RefObject } from "react";

/** Root font size, in CSS px, from which text counts as an accessibility size (150% of 16 px). */
export const ACCESSIBILITY_ROOT_FONT_PX = 24;

/** The browser default the scale is measured against. */
export const DEFAULT_ROOT_FONT_PX = 16;

export const useIsomorphicLayoutEffect = typeof window === "undefined" ? useEffect : useLayoutEffect;

export interface FrameMeasure {
  /** The frame's own width in CSS px; 0 until measured. */
  width: number;
  /** The root font size in CSS px (16 until measured). */
  rootFontPx: number;
  /** Root font at or above `ACCESSIBILITY_ROOT_FONT_PX`. */
  accessibilitySize: boolean;
}

export function readRootFontPx(): number {
  if (typeof document === "undefined" || typeof getComputedStyle !== "function") return DEFAULT_ROOT_FONT_PX;
  const px = parseFloat(getComputedStyle(document.documentElement).fontSize);
  return Number.isFinite(px) && px > 0 ? px : DEFAULT_ROOT_FONT_PX;
}

/** Width and text size of `frame`, read on mount and on every resize; unchanged values bail out. */
export function useFrameMeasure(frame: RefObject<HTMLElement | null>, initialWidth = 0): FrameMeasure {
  const [width, setWidth] = useState(initialWidth);
  const [rootFontPx, setRootFontPx] = useState(DEFAULT_ROOT_FONT_PX);
  useEffect(() => {
    const el = frame.current;
    if (!el) return;
    const read = () => {
      const w = el.clientWidth;
      if (w > 0) setWidth(w);
      setRootFontPx(readRootFontPx());
    };
    read();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(read);
    observer.observe(el);
    return () => observer.disconnect();
  }, [frame]);
  return { width, rootFontPx, accessibilitySize: rootFontPx >= ACCESSIBILITY_ROOT_FONT_PX };
}
