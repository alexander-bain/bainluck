/**
 * Guard for the class in `compiledCss.ts`: an ABSENT build artifact and a
 * BROKEN one must not arrive at the reader as the same sentence.
 *
 * The defect this protects against is not a wrong assertion — it is a correct
 * assertion whose failure message points at the component when the real cause
 * is the tree. Two capture suites went red at the desk on 2026-09-16 saying
 * `Expected: > 1000 / Received: 0`, which reads as "the desktop rules are not
 * present", when the actual cause was a worktree with no `.next`.
 *
 * So the assertions below are about WHICH sentence comes out, and about the
 * pass/fail set being unchanged — both directions, because a guard that only
 * proves the throw would still pass if the helper threw on everything.
 */

import fs from "fs";

import {
  COMPILED_CSS_DIR,
  MIN_COMPILED_CSS_LENGTH,
  assertCompiledCss,
} from "./compiledCss";

const REAL_CSS = "a".repeat(MIN_COMPILED_CSS_LENGTH + 1);

describe("assertCompiledCss", () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("names the remedy, not the component, when the build output is absent", () => {
    jest.spyOn(fs, "existsSync").mockReturnValue(false);

    // The value the rigs actually receive in an unbuilt tree.
    expect(() => assertCompiledCss("")).toThrow(/npm run build/);
    expect(() => assertCompiledCss("")).toThrow(/cannot run/i);
  });

  it("says the absent case has asserted NOTHING about the component", () => {
    jest.spyOn(fs, "existsSync").mockReturnValue(false);

    // The whole point: a reader of this message must not conclude the
    // component regressed. Without this line the message could name the
    // remedy and still read as a finding.
    expect(() => assertCompiledCss("")).toThrow(/NOT "the rig found something"/);
  });

  it("calls a present-but-empty stylesheet a REAL finding", () => {
    jest.spyOn(fs, "existsSync").mockReturnValue(true);

    expect(() => assertCompiledCss("")).toThrow(/real finding/);
    // And it must NOT tell the reader to build — the build already ran.
    expect(() => assertCompiledCss("")).not.toThrow(/npm run build/);
  });

  it("passes a real stylesheet, so the guard is not vacuous", () => {
    jest.spyOn(fs, "existsSync").mockReturnValue(true);

    expect(() => assertCompiledCss(REAL_CSS)).not.toThrow();
  });

  it("preserves the pass/fail set the rigs asserted inline", () => {
    jest.spyOn(fs, "existsSync").mockReturnValue(true);

    // Exactly the old bar: `> 1000`, so 1000 itself still fails.
    expect(() => assertCompiledCss("a".repeat(MIN_COMPILED_CSS_LENGTH))).toThrow();
    expect(() =>
      assertCompiledCss("a".repeat(MIN_COMPILED_CSS_LENGTH + 1)),
    ).not.toThrow();
  });

  it("honours a caller's own bar, for the rig that wants 10_000", () => {
    jest.spyOn(fs, "existsSync").mockReturnValue(true);

    expect(() => assertCompiledCss("a".repeat(9_000), 10_000)).toThrow();
    expect(() => assertCompiledCss("a".repeat(10_001), 10_000)).not.toThrow();
  });

  it("points at the directory the capture rigs actually read", () => {
    // Three rigs compute this path three ways; if this resolves somewhere
    // else, the existsSync check would be answering about the wrong tree.
    expect(COMPILED_CSS_DIR.endsWith(`.next/static/css`)).toBe(true);
    expect(COMPILED_CSS_DIR).not.toContain("__tests__");
  });
});
