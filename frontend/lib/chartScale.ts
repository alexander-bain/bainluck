// Shared px/py linear-scale skeleton for the two hand-rolled "px/py" SVG charts —
// CalibrationChart (predicted-vs-actual reliability diagram) and DisagreementChart
// (multi-source win-prob timeline). Both derive an inner plot box from padding and
// map a numeric domain onto pixel space with the same two linear scales: x grows
// left→right, y is inverted so larger values sit higher (SVG y counts down).
// Extracted verbatim so output is byte-for-byte pixel-identical (L2-152 dedup of
// duplication class D from docs/chart_census.md).
//
// Pure math — no React, no SVG. Only the genuinely-identical primitives live here;
// each chart still owns its own domain (fixed 0–100 vs time / 0–1), grid, marks,
// and legend. Kept deliberately small, mirroring lib/chartTimeline.ts.

export interface PlotDims {
  plotW: number;
  plotH: number;
}

/** Inner plot rectangle after subtracting padding from the SVG box. */
export function plotDims(
  width: number,
  height: number,
  pad: { padL: number; padR: number; padT: number; padB: number },
): PlotDims {
  return {
    plotW: width - pad.padL - pad.padR,
    plotH: height - pad.padT - pad.padB,
  };
}

/**
 * Linear x-scale: domain [domainMin, domainMax] → pixels [padL, padL+plotW]
 * (value grows left→right). Arithmetic mirrors both charts' original inline
 * closures exactly, so the emitted coordinate strings are unchanged.
 */
export function scaleX(
  domainMin: number,
  domainMax: number,
  padL: number,
  plotW: number,
): (v: number) => number {
  return (v: number) => padL + ((v - domainMin) / (domainMax - domainMin)) * plotW;
}

/**
 * Linear y-scale: domain [domainMin, domainMax] → pixels [padT+plotH, padT]
 * (inverted — larger value sits higher). Arithmetic mirrors both charts' original
 * inline closures exactly (Calibration `padT + ((100-v)/100)*plotH`, Disagreement
 * `padT + (1-v)*plotH`), so the emitted coordinate strings are unchanged.
 */
export function scaleY(
  domainMin: number,
  domainMax: number,
  padT: number,
  plotH: number,
): (v: number) => number {
  return (v: number) => padT + ((domainMax - v) / (domainMax - domainMin)) * plotH;
}
