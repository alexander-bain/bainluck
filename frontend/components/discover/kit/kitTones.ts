/**
 * Ruling 366: B / #13635 — Light-mode WCAG contrast tokens and mark/tile/bar
 * color helpers for Kit v1 web cards, ported from iOS `KitTones366B.swift`.
 *
 * Floors enforced in `__tests__/components/kitTones366b13635.test.ts`:
 * - Text & tile foreground/background pairs: >= 4.5:1 WCAG AA
 * - Bars, series lines, dots & rings: >= 3.05:1 against card and track surfaces
 */

import {
  relativeLuminance,
  resolveMatchupTeamColors,
  teamColorWithOpacity,
} from "@/lib/teamColors";
import type { KitV1AdaptiveColor, KitV1TileMark } from "./types";

export const KIT_LIGHT_SURFACES = {
  card: "#FFFFFF",
  elevated: "#F5F5F7",
  track: "#F3F4F6",
  uiElevated: "#F0F0F2",
} as const;

export const KIT_LIGHT_TEXT_HEX = {
  primary: "#111827",
  secondary: "#5E6370",
  muted: "#59606D",
  accent: "#047857",
  warn: "#9A4D00",
} as const;

export const KIT_SERIES_FALLBACK_HEX_LIGHT = [
  "#047857", // accent
  "#005CC2", // c2 blue
  "#7C3AED", // c3 purple
  "#B45309", // c4 amber
  "#0891B2", // c5 cyan
  "#DC2626", // c6 red
] as const;

function parseRgbTuple(hex: string | null | undefined): [number, number, number] | null {
  if (!hex) return null;
  const raw = hex.trim().replace(/^#/, "");
  if (!/^[0-9a-fA-F]{6}$/.test(raw)) return null;
  return [
    parseInt(raw.slice(0, 2), 16),
    parseInt(raw.slice(2, 4), 16),
    parseInt(raw.slice(4, 6), 16),
  ];
}

function normalizeSixHex(hex: string | null | undefined): string | null {
  const rgb = parseRgbTuple(hex);
  if (!rgb) return null;
  return (
    "#" +
    rgb
      .map((v) => v.toString(16).padStart(2, "0"))
      .join("")
      .toUpperCase()
  );
}

export function seriesHex(index: number): string {
  const n = KIT_SERIES_FALLBACK_HEX_LIGHT.length;
  const idx = ((index % n) + n) % n;
  return KIT_SERIES_FALLBACK_HEX_LIGHT[idx];
}

export function contrastRatio(fgHex: string, bgHex: string): number | null {
  const l1 = relativeLuminance(fgHex);
  const l2 = relativeLuminance(bgHex);
  if (l1 === null || l2 === null) return null;
  return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
}

/**
 * Clamps any parsed `#RRGGBB` hex so its WCAG contrast against card (`#FFFFFF`),
 * track (`#F3F4F6`), and elevated (`#F0F0F2`) surfaces clears `minRatio`
 * (default `3.05:1`), preserving hue by stepping monotonically toward black.
 */
export function ensureMarkContrast(hex: string, minRatio = 3.05): string {
  const canonical = normalizeSixHex(hex);
  const rgb = parseRgbTuple(canonical);
  if (!canonical || !rgb) {
    return KIT_SERIES_FALLBACK_HEX_LIGHT[0];
  }
  const passes = (cand: string): boolean => {
    const cCard = contrastRatio(cand, KIT_LIGHT_SURFACES.card);
    const cTrack = contrastRatio(cand, KIT_LIGHT_SURFACES.track);
    const cElev = contrastRatio(cand, KIT_LIGHT_SURFACES.uiElevated);
    if (cCard === null || cTrack === null || cElev === null) return false;
    return Math.min(cCard, cTrack, cElev) >= minRatio;
  };
  if (passes(canonical)) return canonical;

  for (let step = 1; step <= 40; step++) {
    const t = step / 40;
    const cand =
      "#" +
      rgb
        .map((c) =>
          Math.min(255, Math.max(0, Math.round(c * (1 - t))))
            .toString(16)
            .padStart(2, "0"),
        )
        .join("")
        .toUpperCase();
    if (passes(cand)) return cand;
  }
  return KIT_SERIES_FALLBACK_HEX_LIGHT[0];
}

export function resolveKitMarkHex(
  color?: KitV1AdaptiveColor | null,
  fallbackIndex = 0,
): string {
  const rawLight = normalizeSixHex(color?.light);
  if (rawLight) {
    return ensureMarkContrast(rawLight);
  }
  return seriesHex(fallbackIndex);
}

export function resolveKitSplitBarHexes(
  left?: KitV1AdaptiveColor | null,
  right?: KitV1AdaptiveColor | null,
): [string, string] {
  const leftRaw = normalizeSixHex(left?.light);
  const rightRaw = normalizeSixHex(right?.light);
  if (leftRaw && rightRaw) {
    const pair = resolveMatchupTeamColors({
      homePrimary: rightRaw,
      awayPrimary: leftRaw,
    });
    return [
      ensureMarkContrast(pair.away ?? leftRaw),
      ensureMarkContrast(pair.home ?? rightRaw),
    ];
  }
  return [resolveKitMarkHex(left, 0), resolveKitMarkHex(right, 1)];
}

export function resolveKitRangeFillStyle(color?: KitV1AdaptiveColor | null): {
  backgroundColor: string;
  borderColor: string;
} {
  const markHex = resolveKitMarkHex(color, 0);
  return {
    backgroundColor: teamColorWithOpacity(markHex, 0.24),
    borderColor: teamColorWithOpacity(markHex, 0.85),
  };
}

export function toneClass(tone?: string): string {
  if (tone === "accent") return "text-kit-accent";
  if (tone === "muted") return "text-kit-muted";
  if (tone === "secondary") return "text-kit-secondary";
  if (tone === "warn") return "text-kit-warn";
  return "text-kit-primary";
}

export interface KitTileToneClasses {
  container: string;
  foreground: string;
  secondaryForeground: string;
}

export function tileClasses(mark: KitV1TileMark): KitTileToneClasses {
  const isOutlinePeak =
    mark.highlight_role === "row_peak" || mark.highlight_role === "column_peak";
  const ringCls = isOutlinePeak ? " ring-2 ring-kit-accent ring-offset-1" : "";

  if (mark.muted) {
    return {
      container: `border-surface-border bg-surface-elevated${ringCls}`,
      foreground: "text-kit-muted",
      secondaryForeground: "text-kit-muted",
    };
  }
  if (mark.highlight_role === "day_peak" || mark.shade >= 0.6) {
    return {
      container: `border-kit-accent bg-kit-accent${ringCls}`,
      foreground: "text-kit-inverse",
      secondaryForeground: "text-kit-inverse",
    };
  }
  if (mark.shade >= 0.3) {
    return {
      container: `border-kit-accent/65 bg-kit-accent/[0.18]${ringCls}`,
      foreground: "text-kit-primary",
      secondaryForeground: "text-kit-secondary",
    };
  }
  if (mark.shade >= 0.12) {
    return {
      container: `border-kit-accent/45 bg-kit-accent/10${ringCls}`,
      foreground: "text-kit-primary",
      secondaryForeground: "text-kit-secondary",
    };
  }
  return {
    container: `border-surface-border bg-surface-elevated${ringCls}`,
    foreground: "text-kit-secondary",
    secondaryForeground: "text-kit-muted",
  };
}
