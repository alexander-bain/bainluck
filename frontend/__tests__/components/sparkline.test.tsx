// SPARKLINE consolidation guard (L2-150 kernel-(c)). One shared single-market line
// renderer replaced five copy-pasted ones (event leaderboard, weather ×2, politics,
// futures hero, story case-study). This test locks the standing chart rulings AND
// guards both directions (gotcha #43): every migrated variant still renders a line,
// and the killed cubic-bezier smoothing never comes back. Node/SSR env
// (renderToStaticMarkup) — no jsdom.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import Sparkline from "../../components/Sparkline";

// Pull the first line <path d="..."> out of the rendered markup.
function firstPathD(html: string): string {
  const m = html.match(/<path[^>]*\sd="([^"]+)"/);
  return m ? m[1] : "";
}

describe("Sparkline — standing rulings", () => {
  test("ruling #1: NO smoothing — line path is only M/L segments, never a bezier (C/Q/S/T)", () => {
    // The weather variant (area + gradient) is the one whose cubic bezier was killed.
    const html = renderToStaticMarkup(
      <Sparkline data={[10, 40, 20, 80, 55]} area="gradient" endDot animate />,
    );
    const d = firstPathD(html);
    expect(d.length).toBeGreaterThan(0);
    expect(d).toMatch(/^M/);
    // No bezier/quadratic curve commands anywhere in the drawn line.
    expect(d).not.toMatch(/[CcQqSsTt]/);
  });

  test("ruling #2: fixed domain pins magnitude — a flat 50 on [0,100] sits at mid-height", () => {
    const html = renderToStaticMarkup(
      <Sparkline data={[50, 50]} domain={[0, 100]} width={100} height={100} padX={0} padTop={0} padBottom={0} />,
    );
    // y = 0 + 100 * (1 - 50/100) = 50 for both points.
    expect(firstPathD(html)).toBe("M0.0,50.0 L100.0,50.0");
  });

  test("renders nothing for fewer than two finite points", () => {
    expect(renderToStaticMarkup(<Sparkline data={[]} />)).toBe("");
    expect(renderToStaticMarkup(<Sparkline data={[42]} />)).toBe("");
    expect(renderToStaticMarkup(<Sparkline data={[NaN, Infinity]} />)).toBe("");
  });
});

describe("Sparkline — trend coloring (event/politics variants)", () => {
  test("rising series is brand, falling is danger, flat is muted", () => {
    const up = renderToStaticMarkup(<Sparkline data={[0.2, 0.8]} domain={[0, 1]} color="trend" />);
    const down = renderToStaticMarkup(<Sparkline data={[0.8, 0.2]} domain={[0, 1]} color="trend" />);
    const flat = renderToStaticMarkup(<Sparkline data={[0.5, 0.5]} domain={[0, 1]} color="trend" />);
    expect(up).toContain("var(--accent-brand)");
    expect(down).toContain("var(--accent-danger)");
    expect(flat).toContain("var(--text-muted)");
  });
});

describe("Sparkline — weather variant (area + gradient + end dot + animation)", () => {
  const html = renderToStaticMarkup(
    <Sparkline data={[30, 55, 40, 70]} color="#10B981" area="gradient" endDot animate width={80} height={24} />,
  );
  test("draws a gradient-filled area", () => {
    expect(html).toContain("<linearGradient");
    expect(html).toContain("<stop");
  });
  test("draws an end dot", () => {
    expect(html).toContain("<circle");
  });
  test("carries a draw-on animation that respects prefers-reduced-motion", () => {
    expect(html).toContain("@keyframes");
    expect(html).toContain("prefers-reduced-motion");
  });
});

describe("Sparkline — futures hero variant (0–1 domain, brand line, end dot)", () => {
  test("renders a line and an end dot", () => {
    const html = renderToStaticMarkup(
      <Sparkline data={[0.4, 0.45, 0.6]} domain={[0, 1]} width={116} height={50} color="var(--accent-brand)" endDot />,
    );
    expect(firstPathD(html)).toMatch(/^M/);
    expect(html).toContain("<circle");
  });
});

describe("Sparkline — case-study line variant (reference line + annotation + caption)", () => {
  const html = renderToStaticMarkup(
    <Sparkline
      data={[84, 82, 78, 90, 96, 98, 40, 95]}
      domain={[0, 100]}
      width={320}
      height={132}
      padX={10}
      padTop={14}
      padBottom={18}
      stroke={2.5}
      color="var(--accent-brand)"
      area="flat"
      referenceValue={50}
      annotation={{ index: 6, label: "The dip" }}
      caption="What the number knew"
      ariaLabel="What the number knew. The dip."
    />,
  );
  test("draws the dashed 50% reference line", () => {
    expect(html).toContain('stroke-dasharray="3 3"');
  });
  test("renders the annotation label and a flat area fill", () => {
    expect(html).toContain("The dip");
    expect(html).toContain('fill-opacity="0.08"');
  });
  test("wraps in a figure with an accessible caption", () => {
    expect(html).toContain("<figure");
    expect(html).toContain("<figcaption");
    expect(html).toContain("What the number knew");
    expect(html).toContain('role="img"');
    expect(html).toContain('aria-label="What the number knew. The dip."');
  });
  test("the annotated case-study line is still smoothing-free", () => {
    expect(firstPathD(html)).not.toMatch(/[CcQqSsTt]/);
  });
});
