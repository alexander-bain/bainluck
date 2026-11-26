/**
 * Item 7 / #13635 (#13599 -> web) — WCAG 2.1 contrast audit for Kit v1 web
 * semantic tokens, adaptive mark clamping, split-bar separation, and tile bands.
 */
import fs from "node:fs";
import path from "node:path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { KitCardRenderer } from "@/components/discover/kit/KitCardRenderer";
import {
  contrastRatio,
  ensureMarkContrast,
  KIT_LIGHT_SURFACES,
  KIT_LIGHT_TEXT_HEX,
  KIT_SERIES_FALLBACK_HEX_LIGHT,
  resolveKitMarkHex,
  resolveKitRangeFillStyle,
  resolveKitSplitBarHexes,
  seriesHex,
  tileClasses,
  toneClass,
} from "@/components/discover/kit/kitTones";
import type { KitV1CardSpec, KitV1TileMark } from "@/components/discover/kit/types";

function blendHex(fg: string, bg: string, alpha: number): string {
  const parse = (h: string): [number, number, number] => {
    const clean = h.replace("#", "");
    return [
      parseInt(clean.slice(0, 2), 16),
      parseInt(clean.slice(2, 4), 16),
      parseInt(clean.slice(4, 6), 16),
    ];
  };
  const f = parse(fg);
  const b = parse(bg);
  return (
    "#" +
    [0, 1, 2]
      .map((i) => Math.round(f[i] * alpha + b[i] * (1 - alpha)))
      .map((v) => Math.min(255, Math.max(0, v)).toString(16).padStart(2, "0"))
      .join("")
      .toUpperCase()
  );
}

describe("#13635 web Kit contrast tones (WCAG 2.1 parity with iOS KitTones366B)", () => {
  const goldenPath = path.resolve(
    process.cwd(),
    "..",
    "backend",
    "data",
    "discover",
    "kit_v1_golden_examples.json",
  );
  const golden = JSON.parse(fs.readFileSync(goldenPath, "utf-8")) as {
    items: KitV1CardSpec[];
  };

  test("all text tones clear 4.5:1 WCAG AA across card, deep, track, and elevated surfaces", () => {
    const tones = ["primary", "secondary", "muted", "accent", "warn"] as const;
    const surfaces = Object.entries(KIT_LIGHT_SURFACES);
    for (const tone of tones) {
      const fg = KIT_LIGHT_TEXT_HEX[tone];
      for (const [, bg] of surfaces) {
        const ratio = contrastRatio(fg, bg);
        expect(ratio).not.toBeNull();
        expect(ratio!).toBeGreaterThanOrEqual(4.5);
      }
    }
    expect(toneClass(undefined)).toBe("text-kit-primary");
    expect(toneClass("warn")).toBe("text-kit-warn");
    expect(toneClass("muted")).toBe("text-kit-muted");
    expect(toneClass("accent")).toBe("text-kit-accent");
  });

  test("all 6 fallback series colors and every mark color in all 17 golden specs clear 3.05:1", () => {
    for (let i = 0; i < KIT_SERIES_FALLBACK_HEX_LIGHT.length; i++) {
      const hex = seriesHex(i);
      for (const bg of [
        KIT_LIGHT_SURFACES.card,
        KIT_LIGHT_SURFACES.track,
        KIT_LIGHT_SURFACES.uiElevated,
      ]) {
        expect(contrastRatio(hex, bg)!).toBeGreaterThanOrEqual(3.05);
      }
    }

    const markColors: Array<{ light: string; dark: string }> = [];
    const visit = (node: unknown) => {
      if (Array.isArray(node)) {
        node.forEach(visit);
      } else if (node && typeof node === "object") {
        const rec = node as Record<string, unknown>;
        if (rec.color && typeof rec.color === "object" && "light" in (rec.color as object)) {
          markColors.push(rec.color as { light: string; dark: string });
        }
        if (
          rec.fill_color &&
          typeof rec.fill_color === "object" &&
          "light" in (rec.fill_color as object)
        ) {
          markColors.push(rec.fill_color as { light: string; dark: string });
        }
        Object.values(rec).forEach(visit);
      }
    };
    golden.items.forEach(visit);
    expect(markColors.length).toBeGreaterThan(0);

    for (const c of markColors) {
      const resolved = resolveKitMarkHex(c, 0);
      expect(contrastRatio(resolved, KIT_LIGHT_SURFACES.card)!).toBeGreaterThanOrEqual(3.05);
      expect(contrastRatio(resolved, KIT_LIGHT_SURFACES.track)!).toBeGreaterThanOrEqual(3.05);
    }
  });

  test("ensureMarkContrast darkens pale hexes and splitBar separates colliding hues", () => {
    for (const pale of ["#FACC15", "#86EFAC", "#FFFFFF", "#FDE047"]) {
      const clamped = ensureMarkContrast(pale);
      expect(contrastRatio(clamped, KIT_LIGHT_SURFACES.card)!).toBeGreaterThanOrEqual(3.05);
      expect(contrastRatio(clamped, KIT_LIGHT_SURFACES.uiElevated)!).toBeGreaterThanOrEqual(3.05);
    }
    expect(ensureMarkContrast("#008348")).toBe("#008348");
    expect(ensureMarkContrast("#005CC2")).toBe("#005CC2");

    // Two identical team blues -> separated cleanly & contrast floored >= 3.05:1
    const [leftHex, rightHex] = resolveKitSplitBarHexes(
      { light: "#005CC2", dark: "#60A5FA" },
      { light: "#005CC2", dark: "#60A5FA" },
    );
    expect(leftHex).not.toBe(rightHex);
    expect(contrastRatio(leftHex, KIT_LIGHT_SURFACES.card)!).toBeGreaterThanOrEqual(3.05);
    expect(contrastRatio(rightHex, KIT_LIGHT_SURFACES.card)!).toBeGreaterThanOrEqual(3.05);
  });

  test("tile foreground/background bands and peak tiles all clear 4.5:1 WCAG AA", () => {
    const shade12Bg = blendHex(KIT_LIGHT_TEXT_HEX.accent, KIT_LIGHT_SURFACES.card, 0.1);
    const shade30Bg = blendHex(KIT_LIGHT_TEXT_HEX.accent, KIT_LIGHT_SURFACES.card, 0.18);

    expect(contrastRatio("#FFFFFF", KIT_LIGHT_TEXT_HEX.accent)!).toBeGreaterThanOrEqual(4.5);
    expect(contrastRatio(KIT_LIGHT_TEXT_HEX.muted, KIT_LIGHT_SURFACES.uiElevated)!).toBeGreaterThanOrEqual(4.5);
    expect(contrastRatio(KIT_LIGHT_TEXT_HEX.secondary, KIT_LIGHT_SURFACES.uiElevated)!).toBeGreaterThanOrEqual(4.5);
    expect(contrastRatio(KIT_LIGHT_TEXT_HEX.primary, shade12Bg)!).toBeGreaterThanOrEqual(4.5);
    expect(contrastRatio(KIT_LIGHT_TEXT_HEX.secondary, shade12Bg)!).toBeGreaterThanOrEqual(4.5);
    expect(contrastRatio(KIT_LIGHT_TEXT_HEX.primary, shade30Bg)!).toBeGreaterThanOrEqual(4.5);
    expect(contrastRatio(KIT_LIGHT_TEXT_HEX.secondary, shade30Bg)!).toBeGreaterThanOrEqual(4.5);

    const mutedTile = tileClasses({
      mark: "tile",
      center_label: "—",
      shade: 0,
      muted: true,
    } as KitV1TileMark);
    expect(mutedTile.foreground).toBe("text-kit-muted");

    const dayPeakTile = tileClasses({
      mark: "tile",
      center_label: "9",
      shade: 0.72,
      highlight_role: "day_peak",
    } as KitV1TileMark);
    expect(dayPeakTile.container).toContain("bg-kit-accent");
    expect(dayPeakTile.foreground).toBe("text-kit-inverse");
  });

  test("KitCardRenderer uses readable warn tone and translucent range fill behind dark label", () => {
    const rangeStyle = resolveKitRangeFillStyle({ light: "#005CC2", dark: "#60A5FA" });
    expect(rangeStyle.backgroundColor).toContain("rgba(");
    expect(rangeStyle.borderColor).toContain("rgba(");

    const html = renderToStaticMarkup(
      <KitCardRenderer
        spec={{
          kit_version: 1,
          id: "test-warn-and-range",
          layout: "stack",
          variant: null,
          refusal_reason: null,
          kicker: "MACRO",
          common_headline: "Test warn tone & range contrast",
          source_mark: { label: "Kalshi", count: 1 },
          body: {
            items: [
              {
                id: "r1",
                marks: [
                  { mark: "word", text: "CPI peak window", tone: "warn", width: "flex" },
                  {
                    mark: "bar",
                    bar_style: "range",
                    lo: 0.25,
                    hi: 0.65,
                    pct_label: "25%–65%",
                    fill_color: { light: "#005CC2", dark: "#60A5FA" },
                  },
                ],
              },
            ],
          },
        }}
      />,
    );
    expect(html).toContain("text-kit-warn");
    expect(html).toContain("bg-kit-track");
    expect(html).toContain("text-kit-primary");
    expect(html).toContain("rgba(0, 92, 194, 0.24)");
  });
});
