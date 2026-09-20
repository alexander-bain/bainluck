/**
 * #7557 — the two championship grids read the same cell-state vocabulary, or CI says so.
 *
 * THE BUG. The serving payload grew a typed `state` on every grid cell (queue
 * 295 / L2-227), web learned to read it (`lib/gridCellState.ts`, #7387), and
 * the Swift twin did not — `GridCell` never declared the field, so every rung
 * took `LadderRungState`'s default `.open` and printed "—", the app's own
 * NO-MARKET glyph, on 53 already-graded MLB cells. The web grid drew ✓ on the
 * same cell. Nothing failed: both surfaces were internally consistent and
 * neither knew about the other.
 *
 * SO THIS GUARDS THE COUPLING, NOT EITHER READER. It reads both files as source
 * and requires the state VOCABULARY to agree — same five states, same terminal
 * pair, same `clinched` alias. The rendering rules stay where they can be
 * asserted properly: web's in its own component tests, iOS's in
 * `GridCellStateReachesTheRung7557Tests`.
 *
 * Why the vocabulary and not the rendering: a sixth reader state added to the
 * register is the next instance of this bug. Web would handle it; iOS's
 * fail-closed default would swallow it as `unavailable` and a reader would lose
 * a cell with no one noticing. This reddens the moment one surface learns a
 * state the other has not.
 *
 * It lives in jest because jest is a deploy gate here and the Swift test target
 * is not reachable from CI (notice 10's iOS clause exists for that reason).
 */

import { readFileSync } from "fs";
import { join } from "path";

const WEB = join(__dirname, "../../lib/gridCellState.ts");
const IOS = join(
  __dirname,
  "../../../ios/Bain Luck/Bain Luck/Utilities/GridCellRenderState.swift",
);

/**
 * Both files name every state in their headers — the Swift file quotes the web
 * module by name and lists the five, and the web module documents them in its
 * docblock. A raw substring scan would read the prose as the declaration, so
 * comments come out first and the assertions below are made on code only.
 */
function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^[ \t]*\/\/.*$/gm, "");
}

const webSource = stripComments(readFileSync(WEB, "utf8"));
const iosSource = stripComments(readFileSync(IOS, "utf8"));

/** The `export type GridCellState = "live" | "won" | …` union members. */
function webStates(): string[] {
  const decl = webSource.match(/export type GridCellState\s*=([^;]+);/);
  if (!decl) throw new Error("web: `export type GridCellState` not found in gridCellState.ts");
  return [...decl[1].matchAll(/"([a-z_]+)"/g)].map((m) => m[1]).sort();
}

/** The `case live` / `case won` … members of the Swift enum. */
function iosStates(): string[] {
  const decl = iosSource.match(
    /enum GridCellRenderState[^{]*\{([\s\S]*?)\n\}/,
  );
  if (!decl) throw new Error("ios: `enum GridCellRenderState` not found in GridCellRenderState.swift");
  return [...decl[1].matchAll(/^\s*case\s+([a-z][A-Za-z]*)\s*$/gm)]
    .map((m) => m[1])
    .sort();
}

/** `new Set<GridCellState>(["won", "eliminated"])`. */
function webTerminal(): string[] {
  const decl = webSource.match(/TERMINAL_STATES\s*=\s*new Set<GridCellState>\(\[([^\]]*)\]\)/);
  if (!decl) throw new Error("web: TERMINAL_STATES not found in gridCellState.ts");
  return [...decl[1].matchAll(/"([a-z_]+)"/g)].map((m) => m[1]).sort();
}

/** The `isTerminal` computed property's `self == .x` comparisons. */
function iosTerminal(): string[] {
  const decl = iosSource.match(/var isTerminal: Bool \{([^}]*)\}/);
  if (!decl) throw new Error("ios: `isTerminal` not found in GridCellRenderState.swift");
  return [...decl[1].matchAll(/self == \.([a-z]+)/g)].map((m) => m[1]).sort();
}

describe("#7557 — championship grid cell states agree across web and iOS", () => {
  /**
   * The extractors are the load-bearing part of this file: an extractor that
   * silently returns [] makes every comparison below pass on two empty sets.
   * Each throws when its declaration is absent, and this pins the counts so a
   * partial match cannot read as agreement either.
   */
  it("reads a real declaration out of each surface", () => {
    expect(webStates()).toHaveLength(5);
    expect(iosStates()).toHaveLength(5);
    expect(webTerminal()).toHaveLength(2);
    expect(iosTerminal()).toHaveLength(2);
  });

  it("publishes the same five reader states", () => {
    // The five frozen by the C108 contract corpus
    // (backend/tests/evals/fixtures/grid_register_contract.json →
    // application_repair_contract.reader_states).
    const contract = ["eliminated", "live", "missing", "unavailable", "won"];
    expect(webStates()).toEqual(contract);
    expect(iosStates()).toEqual(contract);
    expect(iosStates()).toEqual(webStates());
  });

  it("treats the same two states as terminal", () => {
    expect(webTerminal()).toEqual(["eliminated", "won"]);
    expect(iosTerminal()).toEqual(webTerminal());
  });

  it("accepts `clinched` as the display alias for `won` on both surfaces", () => {
    // Dropping this clause on either surface sends a clinched cell to the
    // fail-closed `unavailable` branch, which renders empty — the same defect
    // this issue is about, arriving by a different door.
    expect(webSource).toMatch(/case "clinched":\s*\n\s*return "won";/);
    expect(iosSource).toMatch(/state == "clinched"\s*\{\s*return \.won \}/);
  });

  it("fails closed on an unrecognised state on both surfaces", () => {
    // Web: `default: return "unavailable"`. iOS: the trailing `return .unavailable`.
    expect(webSource).toMatch(/default:\s*\n\s*return "unavailable";/);
    expect(iosSource).toMatch(/return \.unavailable\s*\n\s*\}/);
  });
});
