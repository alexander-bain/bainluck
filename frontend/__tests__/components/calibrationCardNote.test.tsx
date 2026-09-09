// #4118 / standing notice 34 — the disclosure half of the grey-text sweep.
//
// `calibrationNotice34.test.ts` (beside this file) proves that each of the
// page's method notes is INSIDE a `<CalibrationCardNote>`. That is a source
// slice, and on its own it proves nothing about the reader: a `CardNote` that
// rendered its children as a plain paragraph would satisfy every assertion in
// it while the page looked exactly as it does today.
//
// So the two suites are a pair. This one is the other half — what a
// `CalibrationCardNote` actually puts in the DOM — and it is a render test,
// not a grep, because "closed by default" is a property of the element and not
// of the source. Same `renderToStaticMarkup` rail as `SourceComparisonRow`.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import { CalibrationCardNote } from "../../components/CalibrationCardNote";

const render = (node: React.ReactElement) => renderToStaticMarkup(node);

const NOTE = (
  <CalibrationCardNote label="How these rows are measured">
    <p data-testid="calibration-provider-note">Each row is one data provider.</p>
  </CalibrationCardNote>
);

describe("CalibrationCardNote", () => {
  test("is a disclosure, so the note is not in the page body", () => {
    const html = render(NOTE);
    expect(html).toContain("<details");
    expect(html).toContain("<summary");
  });

  test("is CLOSED by default — the whole point of the sweep", () => {
    // `open` is what would put the paragraph back in front of the reader, and
    // it is one attribute away at all times. React serialises a closed
    // `<details>` with no `open` attribute at all.
    const html = render(NOTE);
    expect(html).not.toContain("open=");
    expect(html).not.toMatch(/<details[^>]*\bopen\b/);
  });

  test("keeps the note in the DOM, verbatim, with its audit hook", () => {
    // Notice 34 sends prose out of the page BODY. It does not ask for it to be
    // destroyed, and half of these sentences exist because Alex asked for them
    // (UX-P075 item (a); the Queue-316 comms pass). `<details>` content stays in
    // the accessibility tree and in `textContent`, so every rail that read the
    // paragraph before still reads it.
    const html = render(NOTE);
    expect(html).toContain("Each row is one data provider.");
    expect(html).toContain('data-testid="calibration-provider-note"');
  });

  test("names its own subject in the summary", () => {
    // A page of six identical "How to read this" lines is its own kind of
    // noise. The label is a prop precisely so each card can say what is behind
    // it, and the default exists only for the card where that is obvious.
    expect(render(NOTE)).toContain("How these rows are measured");
    expect(
      render(<CalibrationCardNote><p>x</p></CalibrationCardNote>),
    ).toContain("How to read this");
  });

  test("publishes a hook so the audit rail can count the disclosures", () => {
    expect(render(NOTE)).toContain('data-testid="calibration-card-note"');
  });
});
