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
import GapList from "@/components/evals/GapList";
import SourceList from "@/components/evals/SourceList";
import { issueRef } from "@/lib/evals/truth";
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

  it("in production a refused figure is dropped rather than shown unlabelled, and nothing throws", () => {
    const env = process.env as Record<string, string | undefined>;
    const was = env.NODE_ENV;
    env.NODE_ENV = "production";
    try {
      const planned = renderToStaticMarkup(
        <PlannedItem waitingOn="the exam data">
          <Figure truth={RECORD}>24 of 25</Figure>
        </PlannedItem>
      );
      expect(planned).toContain("PLANNED");
      expect(planned).not.toContain("24 of 25");
      expect(planned).not.toContain("data-evals-figure");
      expect(renderToStaticMarkup(<Figure truth={{ ...RECORD, asOf: "" }}>24 of 25</Figure>)).toBe("");
      // A figure with its label still renders in production.
      expect(renderToStaticMarkup(<Figure truth={RECORD}>24 of 25</Figure>)).toContain("24 of 25");
    } finally {
      env.NODE_ENV = was;
    }
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

describe("SourceList", () => {
  it("an unreadable source date says so instead of leaving a gap in the line", () => {
    const html = renderToStaticMarkup(
      <SourceList
        sources={[{ id: "x", label: "A receipt", date: "2026-13-01", href: "https://example.com/r", usedBy: ["gaps"] }]}
        sectionTitles={{ gaps: "What we have not tested yet" }}
      />
    );
    expect(html).toContain('<time dateTime="2026-13-01">date unreadable</time>');
  });
});

describe("GapList", () => {
  it("a date in a row renders as a <time>, and a missing one says so", () => {
    const html = renderToStaticMarkup(
      <GapList
        gaps={[
          { id: "a", text: "No result since {since}.", dates: { since: "2026-07" }, ref: issueRef(2693) },
          { id: "b", text: "No result since {since}.", ref: issueRef(2693) },
        ]}
      />
    );
    expect(html).toContain('No result since <time dateTime="2026-07">July 2026</time>.');
    expect(html).toContain("No result since <time>date unreadable</time>.");
  });
});
