/**
 * #12102 S1 — `Figure` is the only door a number has onto /evals, and it will
 * not open without its label.
 *
 * Server renders, in jest's default node environment: `renderToStaticMarkup`
 * throws synchronously, which is what proves a refused figure fails the render,
 * and its output is what a prerendered /evals ships before any browser clock.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import Figure, { PlannedItem, figureProblem } from "@/components/evals/Figure";
import TruthChip from "@/components/evals/TruthChip";
import type { MeasuredTruth } from "@/lib/evals/truth";

const RECORD: MeasuredTruth = {
  kind: "last_run",
  asOf: "2026-11-05",
  source: { label: "Exam receipt", href: "https://github.com/alexander-bain/bainluck/pull/11951" },
};

/** React logs a render error before rethrowing it; the throw is the assertion. */
function quietly<T>(fn: () => T): T {
  const spy = jest.spyOn(console, "error").mockImplementation(() => {});
  try {
    return fn();
  } finally {
    spy.mockRestore();
  }
}

describe("Figure", () => {
  it("renders the figure with its kind, as-of time, source and raw value as data", () => {
    const html = renderToStaticMarkup(
      <Figure truth={RECORD} value="24/25">
        24 of 25
      </Figure>
    );
    expect(html).toContain("data-evals-figure");
    expect(html).toContain('data-truth="last_run"');
    expect(html).toContain('data-as-of="2026-11-05"');
    expect(html).toContain(`data-source="${RECORD.source.href}"`);
    expect(html).toContain('data-value="24/25"');
    expect(html).toContain(">24 of 25</span>");
  });

  it("names what is missing: an as-of time, a source link, or a PLANNED scope", () => {
    expect(figureProblem(false, { ...RECORD, asOf: "" })).toMatch(/as of/);
    expect(figureProblem(false, { ...RECORD, source: { label: "x", href: "" } })).toMatch(/link/);
    expect(figureProblem(true, RECORD)).toMatch(/PLANNED/);
    expect(figureProblem(false, RECORD)).toBeNull();
  });

  it("a figure with no as-of time fails the render", () => {
    expect(() =>
      quietly(() => renderToStaticMarkup(<Figure truth={{ ...RECORD, asOf: "" }}>24 of 25</Figure>))
    ).toThrow(/as of/);
  });

  it("a figure inside a PLANNED item fails the render", () => {
    expect(() =>
      quietly(() =>
        renderToStaticMarkup(
          <PlannedItem waitingOn="the exam data">
            <Figure truth={RECORD}>24 of 25</Figure>
          </PlannedItem>
        )
      )
    ).toThrow(/a PLANNED item renders no figure/);
  });

  it("a PLANNED item with words only renders, with its chip and what it waits on", () => {
    const html = renderToStaticMarkup(
      <PlannedItem waitingOn="the exam data">
        <p>Not built.</p>
      </PlannedItem>
    );
    expect(html).toContain("data-planned-item");
    expect(html).toContain("PLANNED");
    expect(html).toContain("waiting on the exam data");
  });
});

describe("TruthChip, as the server renders it", () => {
  it("prints the record's date and no age — there is no reader clock at build time", () => {
    const html = renderToStaticMarkup(<TruthChip truth={RECORD} />);
    expect(html).toContain("LAST RUN · NOV 5");
    expect(html).not.toMatch(/ago|today/);
  });

  it("links the chip to the record it reads", () => {
    const html = renderToStaticMarkup(<TruthChip truth={RECORD} />);
    expect(html).toContain(`href="${RECORD.source.href}"`);
  });

  it("a LIVE chip prints the payload's own time in Pacific", () => {
    const html = renderToStaticMarkup(
      <TruthChip truth={{ ...RECORD, kind: "live", asOf: "2026-11-06T00:19:00Z" }} />
    );
    expect(html).toContain(">LIVE<");
    expect(html).toContain("as of 4:19 PM PT");
  });
});
