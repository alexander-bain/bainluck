// #10156 — A NAME TOO LONG FOR THE SCORE DIFFERENTIAL AXIS PRINTS AS ITS CODE,
// NOT AS "MEAN G…".
//
// Production, 2026-10-02 03:35Z, 390px, /events/15319855 (North Texas @ Tulsa,
// live): the 192px Score Differential chart printed "GOLDEN … / MEAN G…" while
// the margin maps on the same page said TLSA / UNT, which the event serves as
// `home_team_data.abbreviation` / `away_team_data.abbreviation`.
//
// #8392's rule stays the rule for names that fit and for events with no usable
// code pair. The arms: the code-pair shape; the layout decision over fake
// layout nodes, frame by frame (names → codes → codes again must NOT flip back,
// and a gutter that grows brings the names back); and the chart's wiring, read
// from source because this repo's jest cannot lay out a DOM.

import { readFileSync } from "fs";
import { join } from "path";
import {
  axisCodePair,
  readAxisPoleCaps,
  readAxisPoleLayout,
  type AxisGutterNode,
  type AxisLayoutNode,
  type AxisPoleNeedCache,
} from "@/lib/axisPoleFit";

describe("axisCodePair — which served codes may stand in for the names", () => {
  it("takes the specimen's pair", () => {
    expect(axisCodePair("TLSA", "UNT")).toEqual({ home: "TLSA", away: "UNT" });
    expect(axisCodePair(" PIT ", "CLE")).toEqual({ home: "PIT", away: "CLE" });
  });

  it("refuses a pair a reader could not tell apart, or a field holding a name", () => {
    expect(axisCodePair("UNT", "UNT")).toBeNull();
    expect(axisCodePair("North Texas", "TLSA")).toBeNull();
    expect(axisCodePair("tlsa", "unt")).toBeNull();
    expect(axisCodePair("TLSA", "")).toBeNull();
    expect(axisCodePair(undefined, "UNT")).toBeNull();
    expect(axisCodePair("TULSAX", "UNT")).toBeNull();
  });
});

// A laid-out pole: crest + gap 16, then the label showing `text` at `len` px.
function pole(text: string, len: number): AxisLayoutNode {
  const label: AxisLayoutNode = {
    offsetHeight: len,
    scrollHeight: len,
    textContent: text,
    querySelector: () => null,
  };
  return {
    offsetHeight: 16 + len,
    scrollHeight: 16 + len,
    querySelector: (sel: string) => (sel === "[data-axis-label]" ? label : null),
  };
}
const gutter = (height: number, home: AxisLayoutNode, away: AxisLayoutNode): AxisGutterNode => ({
  clientHeight: height,
  children: [home, away],
});

// Score Differential at 390px: 192 tall, 12px padding top and bottom.
const SD = 192;
const NAMES = { home: "Golden Hurricane", away: "Mean Green" };
const CODES = { home: "TLSA", away: "UNT" };
// Lengths along the gutter at 11px bold uppercase, wide tracking.
const LEN = { "Golden Hurricane": 136, "Mean Green": 85, TLSA: 36, UNT: 28 } as const;
const shown = (h: keyof typeof LEN, a: keyof typeof LEN, height = SD) =>
  gutter(height, pole(h, LEN[h]), pole(a, LEN[a]));

describe("readAxisPoleLayout — names, then codes, and it stays settled", () => {
  it("frame 1 (names on screen, both cut): asks for the codes and keeps #8392's caps meanwhile", () => {
    const cache: AxisPoleNeedCache = {};
    const g = shown("Golden Hurricane", "Mean Green");
    const out = readAxisPoleLayout(g, 12, 12, NAMES, CODES, cache);
    expect(out.useCodes).toBe(true);
    expect(out.caps).toEqual(readAxisPoleCaps(g, 12, 12));
    expect(out.caps.home).not.toBeNull();
  });

  it("frame 2 and after (codes on screen): codes fit, nothing is cut, and it never flips back", () => {
    const cache: AxisPoleNeedCache = {};
    readAxisPoleLayout(shown("Golden Hurricane", "Mean Green"), 12, 12, NAMES, CODES, cache);
    for (let frame = 0; frame < 3; frame++) {
      const out = readAxisPoleLayout(shown("TLSA", "UNT"), 12, 12, NAMES, CODES, cache);
      expect(out).toEqual({ useCodes: true, caps: { home: null, away: null } });
    }
  });

  it("a gutter that grows enough brings the names back (decided from the remembered lengths)", () => {
    const cache: AxisPoleNeedCache = {};
    readAxisPoleLayout(shown("Golden Hurricane", "Mean Green"), 12, 12, NAMES, CODES, cache);
    readAxisPoleLayout(shown("TLSA", "UNT"), 12, 12, NAMES, CODES, cache);
    const out = readAxisPoleLayout(shown("TLSA", "UNT", 320), 12, 12, NAMES, CODES, cache);
    expect(out).toEqual({ useCodes: false, caps: { home: null, away: null } });
  });

  it("new team names are measured afresh, not judged by the last game's lengths", () => {
    const cache: AxisPoleNeedCache = {};
    readAxisPoleLayout(shown("Golden Hurricane", "Mean Green"), 12, 12, NAMES, CODES, cache);
    // Codes on screen, but the labels are now a different pair nobody has measured.
    const out = readAxisPoleLayout(shown("TLSA", "UNT"), 12, 12, { home: "Rams", away: "Jets" }, CODES, cache);
    expect(out.useCodes).toBe(false);
  });
});

describe("readAxisPoleLayout — #8392 unchanged where this does not apply", () => {
  it("names that fit stay names, codes or not", () => {
    const names = { home: "Steelers", away: "Browns" };
    const g = gutter(SD, pole("Steelers", 70), pole("Browns", 56));
    expect(readAxisPoleLayout(g, 12, 12, names, { home: "PIT", away: "CLE" }, {})).toEqual({
      useCodes: false,
      caps: { home: null, away: null },
    });
  });

  it("no usable code pair: the ellipsis caps, exactly as before", () => {
    const g = shown("Golden Hurricane", "Mean Green");
    expect(readAxisPoleLayout(g, 12, 12, NAMES, null, {})).toEqual({
      useCodes: false,
      caps: readAxisPoleCaps(g, 12, 12),
    });
  });
});

describe("ScoreDifferentialChart — the poles print what the layout decided", () => {
  const src = readFileSync(join(__dirname, "../components/ScoreDifferentialChart.tsx"), "utf8");

  it("hands the served codes to the hook through the pair rule", () => {
    expect(src).toMatch(/useAxisPoleFit\(homeShort, awayShort, axisCodePair\(homeTeamAbbrev, awayTeamAbbrev\)\)/);
  });

  it("each pole's label prints the decided label, not the bare short name", () => {
    const labels = src.match(/<span\s+data-axis-label[\s\S]*?<\/span>/g) ?? [];
    expect(labels).toHaveLength(2);
    expect(labels[0]).toContain("{axisPoleLabels.home}");
    expect(labels[1]).toContain("{axisPoleLabels.away}");
    for (const l of labels) expect(l).not.toMatch(/\{(home|away)Short\}/);
  });

  it("a pole showing a code keeps the full name in its title", () => {
    expect(src).toContain("title={axisPoleCaps.home !== null || axisShowsCodes ? homeShort : undefined}");
    expect(src).toContain("title={axisPoleCaps.away !== null || axisShowsCodes ? awayShort : undefined}");
  });
});
