/**
 * #994 — the drill-in's footer tells a reader the sampled rows are current ones.
 *
 * `/calibration/examples` evaluates futures rows NOW; the chart above can be an
 * earlier published update, and the backend says membership of that update is
 * `"unverified"`. Before this, the page copied only `examples` and `note` into
 * its state, so that disclosure lived in a field no screen read. These guards
 * pin the caption, its plain wording, and that the page actually wires it.
 */

import { readFileSync } from "fs";
import { join } from "path";

import {
  EXAMPLES_FOOTER_CURRENT_ROWS,
  EXAMPLES_FOOTER_DEFAULT,
  examplesFooterCopy,
} from "@/lib/calibrationExamples";

describe("examplesFooterCopy", () => {
  it("says the rows are current when the sample is drawn live and unverified", () => {
    expect(
      examplesFooterCopy({
        basis: "live_canonical_population",
        published_generation_membership: "unverified",
      }),
    ).toBe(EXAMPLES_FOOTER_CURRENT_ROWS);
  });

  it("keeps the existing caption where the endpoint sends no sampling block", () => {
    // Event-sourced and unsupported branches serve `sampling: null`.
    expect(examplesFooterCopy(null)).toBe(EXAMPLES_FOOTER_DEFAULT);
    expect(examplesFooterCopy(undefined)).toBe(EXAMPLES_FOOTER_DEFAULT);
  });

  it("does not claim a difference once membership is verified", () => {
    expect(
      examplesFooterCopy({
        basis: "live_canonical_population",
        published_generation_membership: "verified",
      }),
    ).toBe(EXAMPLES_FOOTER_DEFAULT);
  });

  it("is short, plain and free of implementation words", () => {
    expect(EXAMPLES_FOOTER_CURRENT_ROWS).not.toBe(EXAMPLES_FOOTER_DEFAULT);
    expect(EXAMPLES_FOOTER_CURRENT_ROWS).toMatch(/earlier update/);
    expect(EXAMPLES_FOOTER_CURRENT_ROWS).toMatch(/not the full bucket/);
    for (const word of ["generation", "canonical", "population", "sampling", "cohort", "unverified"]) {
      expect(EXAMPLES_FOOTER_CURRENT_ROWS.toLowerCase()).not.toContain(word);
    }
    expect(EXAMPLES_FOOTER_CURRENT_ROWS.length).toBeLessThan(140);
  });
});

describe("the calibration page wires the caption", () => {
  const page = readFileSync(join(__dirname, "../../app/calibration/page.tsx"), "utf8");

  it("carries the response's sampling block into the drill-in state", () => {
    expect(page).toMatch(/sampling:\s*res\.sampling\s*\?\?\s*null/);
  });

  it("renders the footer from that state, not a fixed sentence", () => {
    expect(page).toContain("{examplesFooterCopy(state.sampling)}");
    expect(page).not.toContain("A representative sample &mdash; not the full bucket.");
  });

  it("gives phone widths a stacked list so price and result are on screen", () => {
    // At 390px the table showed only the market column; the rest scrolled off.
    expect(page).toMatch(/<ul className="sm:hidden[^"]*" data-testid="calibration-examples-list">/);
    expect(page).toContain('<div className="hidden sm:block overflow-x-auto">');
  });
});
