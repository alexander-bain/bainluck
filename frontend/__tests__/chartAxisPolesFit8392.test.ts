// #8392 — THE TWO TEAM NAMES ON A CHART'S SIDE AXIS NEVER RUN INTO EACH OTHER.
//
// Win Probability (`OddsChart`, a 320px chart) and Score Differential
// (`ScoreDifferentialChart`, 192px) print both team names sideways in a 28px
// gutter. Nothing limited their length. Measured on production at 390px
// (`artifacts/ux-1481/axis-*.png`): "Borussia Mönchengladbach / Union Berlin"
// overlapped by 17px on Win Probability, and on Score Differential the lower
// name was pushed 12px past the bottom of the chart. #5634 keeps a club's whole
// name on purpose, so 87 of 964 soccer labels are now over 18 characters.
//
// The rule (`allocateAxisPoles`): both fit → nothing changes; one fits in half
// → it is whole and the other gets the rest; neither → half each. The clipped
// name ends in an ellipsis and keeps its full text in `title` / the sr-only
// sentence.
//
// The gutter is measured in the browser (`useAxisPoleFit`), which this repo's
// jest (node, no DOM) cannot lay out. So the arms are: the allocation rule over
// the issue's own numbers and a sweep; the measurement over fake layout nodes,
// including the capped-and-remeasured case the hook depends on to settle; the
// uncapped styles byte-for-byte the pre-#8392 ones; and the wiring, read from
// both chart sources.

import { readFileSync } from "fs";
import { join } from "path";
import {
  AXIS_POLE_MIN_GAP_PX,
  allocateAxisPoles,
  axisLabelStyle,
  axisPoleNeed,
  axisPoleStyle,
  readAxisPoleCaps,
  type AxisLayoutNode,
} from "@/lib/axisPoleFit";

// Gutter lengths measured on /events/15297681 at 390px: 320 − 2×12 padding and
// 192 − 2×12.
const WIN_PROB = 296;
const SCORE_DIFF = 168;

describe("allocateAxisPoles — who gets the gutter", () => {
  it("leaves two names that fit exactly as they were (FC Köln / Union Berlin)", () => {
    expect(allocateAxisPoles(WIN_PROB, 70, 101)).toEqual({ home: null, away: null });
    expect(allocateAxisPoles(SCORE_DIFF, 56, 90)).toEqual({ home: null, away: null });
  });

  it("gives the short name all it needs and the long one the rest (Mönchengladbach / Union Berlin)", () => {
    // 195 + 101 = 296 + gap > 296: the long HOME name is capped, the away name is whole.
    const caps = allocateAxisPoles(WIN_PROB, 195, 101);
    expect(caps.away).toBeNull();
    expect(caps.home).toBe(WIN_PROB - AXIS_POLE_MIN_GAP_PX - 101);
    // Mirror: the long name on the AWAY side.
    const mirror = allocateAxisPoles(WIN_PROB, 101, 195);
    expect(mirror).toEqual({ home: null, away: caps.home });
  });

  it("does NOT split half-and-half when one side needs less than half (the tried-and-rejected cap)", () => {
    // Score Differential: "Union Berlin" needs 101 of 168; its opponent 60. A
    // 50% cap (82) clips Union Berlin although 104 px are free for it.
    const caps = allocateAxisPoles(SCORE_DIFF, 60, 110);
    expect(caps.home).toBeNull();
    expect(caps.away).toBe(SCORE_DIFF - AXIS_POLE_MIN_GAP_PX - 60);
    expect(caps.away).toBeGreaterThan(Math.floor((SCORE_DIFF - AXIS_POLE_MIN_GAP_PX) / 2));
  });

  it("halves the gutter when both names are long", () => {
    const half = Math.floor((SCORE_DIFF - AXIS_POLE_MIN_GAP_PX) / 2);
    expect(allocateAxisPoles(SCORE_DIFF, 152, 144)).toEqual({ home: half, away: half });
  });

  it("does nothing on a gutter that has not been laid out or a label it could not read", () => {
    expect(allocateAxisPoles(0, 400, 400)).toEqual({ home: null, away: null });
    expect(allocateAxisPoles(WIN_PROB, NaN, 400)).toEqual({ home: null, away: null });
    expect(allocateAxisPoles(NaN, 400, 400)).toEqual({ home: null, away: null });
  });

  it("over a sweep: the two poles never overlap, and a name that fits its share is never cut", () => {
    let capped = 0;
    for (const avail of [120, SCORE_DIFF, 200, WIN_PROB, 400]) {
      for (let h = 0; h <= 320; h += 7) {
        for (let a = 0; a <= 320; a += 11) {
          const caps = allocateAxisPoles(avail, h, a);
          const hLen = caps.home === null ? h : Math.min(h, caps.home);
          const aLen = caps.away === null ? a : Math.min(a, caps.away);
          if (caps.home !== null || caps.away !== null) {
            capped++;
            expect(hLen + aLen + AXIS_POLE_MIN_GAP_PX).toBeLessThanOrEqual(avail);
          } else {
            expect(h + a + AXIS_POLE_MIN_GAP_PX).toBeLessThanOrEqual(avail);
          }
          const share = Math.floor((avail - AXIS_POLE_MIN_GAP_PX) / 2);
          if (h <= share) expect(caps.home).toBeNull();
          if (a <= share) expect(caps.away).toBeNull();
        }
      }
    }
    expect(capped).toBeGreaterThan(100); // the sweep exercises the capping arms
  });
});

function node(offsetHeight: number, scrollHeight: number, label: AxisLayoutNode | null = null): AxisLayoutNode {
  return {
    offsetHeight,
    scrollHeight,
    querySelector: (sel: string) => (sel === "[data-axis-label]" ? label : null),
  };
}

describe("readAxisPoleCaps — measuring the laid-out gutter", () => {
  // Crest 12 + gap 4 + a name 179 long: the pole needs 195.
  const longPole = () => node(195, 195, node(179, 179));
  const shortPole = () => node(101, 101, node(101, 101));

  it("reads each pole's need as crest + gap + the name's full length", () => {
    expect(axisPoleNeed(longPole())).toBe(195);
    expect(axisPoleNeed(shortPole())).toBe(101);
  });

  it("reads the SAME need once the cap has clipped the name — so the hook settles in one pass", () => {
    // After the cap: the pole is 187 tall, the name's box 171, its content still 179.
    const clipped = node(187, 187, node(171, 179));
    expect(axisPoleNeed(clipped)).toBe(axisPoleNeed(longPole()));
    const gutter = (home: AxisLayoutNode) => ({ clientHeight: 320, children: [home, shortPole()] });
    expect(readAxisPoleCaps(gutter(clipped), 12, 12)).toEqual(readAxisPoleCaps(gutter(longPole()), 12, 12));
  });

  it("subtracts the gutter's padding and caps the long pole", () => {
    const caps = readAxisPoleCaps({ clientHeight: 320, children: [longPole(), shortPole()] }, 12, 12);
    expect(caps).toEqual({ home: WIN_PROB - AXIS_POLE_MIN_GAP_PX - 101, away: null });
  });

  it("caps nothing when a pole has no marked name (a chart that never wired the label)", () => {
    const unmarked = node(195, 195, null);
    expect(readAxisPoleCaps({ clientHeight: 320, children: [unmarked, shortPole()] }, 12, 12)).toEqual({ home: null, away: null });
    expect(readAxisPoleCaps({ clientHeight: 320, children: [] }, 12, 12)).toEqual({ home: null, away: null });
  });
});

describe("styles — a name that fits renders exactly as before", () => {
  it("an uncapped pole carries only the sideways writing, and an uncapped name stays on one line", () => {
    expect(axisPoleStyle(null)).toEqual({ writingMode: "vertical-rl", transform: "rotate(180deg)" });
    // The one change to a name that fits: it may no longer WRAP. Production drew
    // "Barracas Central" as two stacked sideways words that ran into its
    // opponent (/events/15306110) — a fitting name was never wrapped, so this
    // changes nothing for it.
    expect(axisLabelStyle(null)).toEqual({ whiteSpace: "nowrap" });
  });

  it("a capped pole may shrink and clips; its name ends in an ellipsis", () => {
    expect(axisPoleStyle(120)).toEqual({
      writingMode: "vertical-rl",
      transform: "rotate(180deg)",
      maxHeight: 120,
      minHeight: 0,
      overflow: "hidden",
    });
    expect(axisLabelStyle(120)).toEqual({
      whiteSpace: "nowrap",
      minHeight: 0,
      overflow: "hidden",
      textOverflow: "ellipsis",
    });
  });
});

describe("wiring — both charts measure their gutter and cap both poles", () => {
  const read = (f: string) => readFileSync(join(__dirname, "..", "components", f), "utf8");

  for (const file of ["OddsChart.tsx", "ScoreDifferentialChart.tsx"]) {
    describe(file, () => {
      const src = read(file);
      const gutterAt = src.indexOf("ref={axisGutterRef}");

      it("hangs the measuring ref on the 28px axis gutter", () => {
        expect(gutterAt).toBeGreaterThan(-1);
        const gutterTag = src.slice(gutterAt, src.indexOf(">", gutterAt));
        expect(gutterTag).toContain("width: 28");
        expect(gutterTag).toContain("justify-between");
      });

      it("caps each pole with its own side's cap, and marks each name", () => {
        const gutter = src.slice(gutterAt, src.indexOf("{/* Chart area */}", gutterAt));
        expect(gutter.match(/style=\{axisPoleStyle\(axisPoleCaps\.home\)\}/g)).toHaveLength(1);
        expect(gutter.match(/style=\{axisPoleStyle\(axisPoleCaps\.away\)\}/g)).toHaveLength(1);
        expect(gutter.match(/\.\.\.axisLabelStyle\(axisPoleCaps\.home\)/g)).toHaveLength(1);
        expect(gutter.match(/\.\.\.axisLabelStyle\(axisPoleCaps\.away\)/g)).toHaveLength(1);
        expect(gutter.match(/data-axis-label\b/g)).toHaveLength(2);
        // Home is the first pole, away the second — the order readAxisPoleCaps assumes.
        expect(gutter.indexOf("axisPoleCaps.home")).toBeLessThan(gutter.indexOf("axisPoleCaps.away"));
        // The old unconditional sideways style is gone from the gutter.
        expect(gutter).not.toContain('style={{ writingMode: "vertical-rl"');
      });
    });
  }

  it("OddsChart calls the hook above its empty-chart return (a hook after it would break on the first data arrival)", () => {
    const src = read("OddsChart.tsx");
    const hookAt = src.indexOf("useAxisPoleFit(");
    expect(hookAt).toBeGreaterThan(-1);
    expect(hookAt).toBeLessThan(src.indexOf("if (chartData.length === 0 || !drawnExtent)"));
  });
});
