/**
 * #3119 — a Discover hero prints a percent only once it is counting toward one.
 *
 * THE SPECIMEN, production 2026-09-05, phone width, page one of Discover:
 *
 *     🏌️ GOLF        0%        Thriston Lawrence        ▲ 17%
 *     Omega European Masters · Crans-sur-Sierre GC · Started Thu, Sep 3
 *
 * while `GET /api/feed` said `{"probability": 0.252, "movement_24h": 0.1704}`
 * for that same golfer and the card's own reason line said "leads at 25.2% (up
 * 17.0% today)". The counter starts at 0 and only counts up when the span is
 * 50% visible, so every card below the fold rendered a confident zero.
 *
 * WHY THE GUARD IS ON A PURE FUNCTION AND NOT ON THE COMPONENT: this project's
 * jest runs `testEnvironment: 'node'` (`jest.config.js`). There is no DOM, no
 * `IntersectionObserver` and no effect to drive, so a test that rendered
 * `AnimatedProbability` could not reach the decision at all. Extracting the
 * decision is what makes it testable — and the component now has exactly one
 * branch, delegated here.
 */

import { animatedProbabilityReading } from "@/lib/animatedProbabilityReading";

const LAWRENCE = 25; // the whole percent the real card should have been showing

describe("a hero that has not been seen yet", () => {
  it("says nothing rather than zero", () => {
    // The exact frame the screenshot caught: a real value, no animation yet.
    expect(
      animatedProbabilityReading({
        value: LAWRENCE,
        started: false,
        displayed: 0,
      })
    ).toEqual({ kind: "unknown" });
  });

  it("says nothing even when the counter is mid-flight but not started", () => {
    // Defensive: `displayed` is only ever moved by the animation, but a future
    // caller that seeds it must not be able to publish a reading this way.
    expect(
      animatedProbabilityReading({ value: LAWRENCE, started: false, displayed: 12 })
    ).toEqual({ kind: "unknown" });
  });
});

describe("once it is counting", () => {
  it("prints the current frame", () => {
    expect(
      animatedProbabilityReading({ value: LAWRENCE, started: true, displayed: 12 })
    ).toEqual({ kind: "percent", percent: 12 });
  });

  it("prints the real number at the end of the count", () => {
    expect(
      animatedProbabilityReading({
        value: LAWRENCE,
        started: true,
        displayed: LAWRENCE,
      })
    ).toEqual({ kind: "percent", percent: LAWRENCE });
  });
});

describe("the zero that was always handled correctly", () => {
  it("is still unknown on an unresolved market, seen or not", () => {
    for (const started of [false, true]) {
      expect(
        animatedProbabilityReading({ value: 0, started, displayed: 0 })
      ).toEqual({ kind: "unknown" });
    }
  });

  it("is a real reading on a settled one", () => {
    // Settled means settled: a losing outcome at 0% is a RESULT, and the
    // count-up has to be allowed to land on it.
    expect(
      animatedProbabilityReading({
        value: 0,
        resolved: true,
        started: true,
        displayed: 0,
      })
    ).toEqual({ kind: "percent", percent: 0 });
  });

  it("is still not printed on a settled market nobody has scrolled to", () => {
    expect(
      animatedProbabilityReading({
        value: 0,
        resolved: true,
        started: false,
        displayed: 0,
      })
    ).toEqual({ kind: "unknown" });
  });
});

describe("the component delegates the decision", () => {
  it("has no zero-printing branch of its own left", () => {
    // A source pin, because the defect can come back by re-adding the branch
    // rather than by changing this function. `started` must be STATE — the
    // existing `animated` ref cannot re-render, so a fix that only flipped the
    // ref would compile, pass this file, and still print 0%.
    const fs = require("fs") as typeof import("fs");
    const path = require("path") as typeof import("path");
    const src = fs.readFileSync(
      path.join(__dirname, "../../components/discover/shared.tsx"),
      "utf8"
    );
    expect(src).toContain("const [started, setStarted] = useState(false)");
    expect(src).toContain("setStarted(true)");
    expect(src).toContain("animatedProbabilityReading({ value, resolved, started, displayed })");
    expect(src).not.toContain("{displayed}<span className=\"text-3xl\">%</span>");
  });
});
