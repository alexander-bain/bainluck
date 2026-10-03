// #10249 — lifting a finger ends an inspection of the chart.
//
// Shopper walk, production `/events/15318028` (Pitt @ VT, live Q1) at 390×844,
// 2026-10-02 23:31Z: after a touch-drag, `.recharts-tooltip-wrapper` stayed
// visible for the full 80 s observed and survived a tap outside the chart. When a
// live update arrived, the latched card moved to a different historical point on
// its own ("13:17 · 68.7%" → "12:42 · 70.1%"). The readout under the chart
// stayed on the scrubbed moment, so two old moments were on screen while the
// game was 14–0 and the hero read 84%.
//
// Recharts 2.15.4 clears its active state only on `mouseleave`. Its `touchend`
// forwards to an `onMouseUp` prop and does nothing else. The first describe
// block pins that premise against the installed library, so an upgrade that
// changes it fails here and gets a look, instead of leaving a fix that does nothing.

import { readFileSync } from "fs";
import { join } from "path";
import { chartInspectionPhase, releaseChartInspection } from "@/components/OddsChart";

const recharts = readFileSync(
  require.resolve("recharts/lib/chart/generateCategoricalChart.js"),
  "utf8",
);
const source = readFileSync(join(process.cwd(), "components/OddsChart.tsx"), "utf8");

describe("#10249 the premise, read from the installed Recharts", () => {
  it("touchend only forwards to onMouseUp; it never deactivates the tooltip", () => {
    const at = recharts.indexOf('_defineProperty(_this, "handleTouchEnd"');
    expect(at).toBeGreaterThan(-1);
    const body = recharts.slice(at, recharts.indexOf("_defineProperty(_this,", at + 10));
    expect(body).toContain("handleMouseUp");
    expect(body).not.toContain("isTooltipActive");
  });

  it("handleMouseLeave is an instance field that sets isTooltipActive false", () => {
    const at = recharts.indexOf('_defineProperty(_this, "handleMouseLeave"');
    expect(at).toBeGreaterThan(-1);
    const body = recharts.slice(at, recharts.indexOf("_defineProperty(_this,", at + 10));
    expect(body).toContain("isTooltipActive: false");
  });
});

describe("#10249 chartInspectionPhase", () => {
  it("the last finger lifting, or a cancelled touch, releases", () => {
    expect(chartInspectionPhase("touchend", { touchesLeft: 0 })).toBe("release");
    expect(chartInspectionPhase("touchcancel", { touchesLeft: 0 })).toBe("release");
    expect(chartInspectionPhase("touchend")).toBe("release");
  });

  it("a finger going down starts an inspection; one of two fingers lifting does not end it", () => {
    expect(chartInspectionPhase("touchstart")).toBe("inspect");
    expect(chartInspectionPhase("touchend", { touchesLeft: 1 })).toBe("none");
    expect(chartInspectionPhase("touchcancel", { touchesLeft: 1 })).toBe("none");
  });

  it("only a MOUSE moving resumes hovering; a touch's pointer events change nothing", () => {
    // Chrome fires `pointercancel` (and touch-typed pointer moves) mid-drag when
    // the drag could become a scroll. Those must not end or restart anything.
    expect(chartInspectionPhase("pointermove", { pointerType: "mouse" })).toBe("inspect");
    expect(chartInspectionPhase("pointermove", { pointerType: "touch" })).toBe("none");
    expect(chartInspectionPhase("pointermove", { pointerType: "pen" })).toBe("none");
  });
});

describe("#10249 releaseChartInspection", () => {
  it("hands the readout back to the current moment and runs the chart's own leave", () => {
    const calls: string[] = [];
    const chart = {
      handleMouseLeave(this: unknown) {
        // Called as a method of the chart, not detached.
        calls.push(this === chart ? "leave:bound" : "leave:unbound");
      },
    };
    const onActive = jest.fn(() => calls.push("readout:null"));
    releaseChartInspection(chart, onActive);
    expect(onActive).toHaveBeenCalledWith(null);
    expect(calls).toEqual(["readout:null", "leave:bound"]);
  });

  it("a chart without the field (or no chart yet) still clears the readout and does not throw", () => {
    const onActive = jest.fn();
    expect(() => releaseChartInspection(null, onActive)).not.toThrow();
    expect(() => releaseChartInspection({}, onActive)).not.toThrow();
    expect(() => releaseChartInspection({ handleMouseLeave: 1 }, undefined)).not.toThrow();
    expect(onActive).toHaveBeenCalledTimes(2);
  });
});

describe("#10249 OddsChart is wired to it", () => {
  const area = source.slice(source.indexOf("{/* Chart area."));

  it("the plot's wrapper reports touch start/end/cancel and mouse moves, and no pointercancel", () => {
    const wrapper = area.slice(0, area.indexOf("<ResponsiveContainer"));
    expect(wrapper).toContain('onTouchStart={() => onChartInspection("touchstart")}');
    expect(wrapper).toContain('onTouchEnd={(e) => onChartInspection("touchend", { touchesLeft: e.touches.length })}');
    expect(wrapper).toContain('onTouchCancel={(e) => onChartInspection("touchcancel", { touchesLeft: e.touches.length })}');
    expect(wrapper).toContain('onPointerMove={(e) => onChartInspection("pointermove", { pointerType: e.pointerType })}');
    // The first build released on pointercancel and hid the tooltip DURING a
    // drag (Chrome cancels the pointer once the drag could be a scroll).
    expect(wrapper).not.toContain("onPointerCancel");
    expect(wrapper).not.toContain("onPointerUp");
  });

  it("the chart's ref is the one the release clears", () => {
    expect(area).toMatch(/<ComposedChart\s+ref=\{chartRef as never\}/);
    expect(source).toContain("releaseChartInspection(chartRef.current, onActivePointChange)");
  });

  it("a released chart's tooltip is held inactive, so later data cannot bring it back", () => {
    expect(area).toMatch(
      /<Tooltip\s+content=\{<CustomTooltip \/>\}\s+filterNull=\{false\}\s+active=\{touchReleased \? false : undefined\}\s*\/>/,
    );
  });

  it("compatibility mouse events after a tap cannot re-latch the readout", () => {
    const move = area.slice(area.indexOf("onMouseMove={"), area.indexOf("onMouseLeave={"));
    const guard = move.indexOf("if (touchReleasedRef.current)");
    const firstReadout = move.indexOf("onActivePointChange({");
    expect(guard).toBeGreaterThan(-1);
    expect(guard).toBeLessThan(firstReadout);
  });
});
