import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { Histogram, sharedBucketPrefix } from "../../components/economics/atoms";

// #2564 clause 3 — a histogram's rows must be tellable apart.
//
// Production, `/economics` at 390px: two of the six inflation blocks render
// eight rows each, and every visible label reads `Exactly …`:
//
//     Exactly …   14.6%        Exactly …   28.6%
//     Exactly …   11.5%        Exactly …   23.2%
//     Exactly …    7.7%        Exactly …   19.1%
//     …                        …
//
// Eight different questions, eight different probabilities, nothing on screen
// telling them apart. The payload is fine — the labels are `Exactly 3.5%`,
// `Exactly 3.6%`, `Exactly 2.1%` — and the shared word is what eats a label
// column fixed at 56px, so the only distinguishing part is the part truncated
// away. The same column ellipsises the range labels that have no shared prefix
// (`1.9 to 2…` for `1.9 to 2.1%`), which is the other half of this file.
//
// These two blocks were not on the card before this ship. Ordering the blocks
// by release date promotes them onto it, so the clause the issue filed as
// "intermittent" becomes two of six blocks — which is why it is fixed here and
// not left for later.

const YOY_SEP_2026: [number, string][] = [
  [14.6, "Exactly 3.5%"],
  [11.5, "Exactly 3.6%"],
  [7.7, "Exactly 2.1%"],
  [7.7, "Exactly 2.2%"],
  [7.7, "Exactly 2.3%"],
  [6.9, "Exactly 3.7%"],
  [5.0, "Exactly 3.4%"],
];

const html = (buckets: [number, string][]) =>
  renderToStaticMarkup(<Histogram buckets={buckets} color="#10B981" />);

describe("the shared prefix", () => {
  it("is found when every label restates it", () => {
    expect(sharedBucketPrefix(YOY_SEP_2026.map(b => b[1]))).toBe("Exactly ");
  });

  it("leaves the distinguishing value in the label the page prints", () => {
    const markup = html(YOY_SEP_2026);
    for (const value of ["3.5%", "3.6%", "2.1%", "2.2%", "2.3%"]) {
      expect(markup).toContain(`>${value}<`);
    }
  });

  it("no two rows print the same label", () => {
    const markup = html(YOY_SEP_2026);
    const labels = [...markup.matchAll(/text-right shrink-0 truncate">([^<]*)</g)].map(m => m[1]);
    expect(labels).toHaveLength(YOY_SEP_2026.length);
    expect(new Set(labels).size).toBe(labels.length);
  });

  it("is not printed on any row", () => {
    // The whole point: the word that was eating the column is gone from the
    // rendered labels, not merely shortened.
    expect(html(YOY_SEP_2026)).not.toContain("Exactly");
  });
});

describe("what the strip refuses", () => {
  it("a single row keeps its label whole", () => {
    // One row is no evidence that a leading word is boilerplate.
    expect(sharedBucketPrefix(["Exactly 3.5%"])).toBe("");
    expect(html([[100, "Exactly 3.5%"]])).toContain("Exactly 3.5%");
  });

  it("labels that merely start alike are left alone", () => {
    // `Above 3%` / `Above or below 3%` share characters, not a whole word
    // boundary shared by all — and `0.5%` / `0.6%` share no leading word.
    expect(sharedBucketPrefix(["0.5%", "0.6%", "0.7%"])).toBe("");
    expect(sharedBucketPrefix(["Above 3%", "Below 3%"])).toBe("");
  });

  it("never strips a label down to nothing", () => {
    expect(sharedBucketPrefix(["Exactly 3.5%", "Exactly "])).toBe("");
  });

  it("never makes two labels that differed read the same", () => {
    // If the prefix is the ONLY thing telling two rows apart, dropping it
    // re-creates the defect it exists to fix.
    expect(sharedBucketPrefix(["At least 5", "Above 5"])).toBe("");
  });

  it("a cumulative bound keeps its word", () => {
    // The oil and rig ladders on this same page carry `At least 370`, `At
    // least 380`. Here the shared word is not boilerplate — it IS the meaning,
    // and both `least 370` and a bare `370` are worse than what they replace.
    // The vocabulary is `economics.py`'s `_CUMULATIVE_PREFIXES`.
    expect(sharedBucketPrefix(["At least 370", "At least 380", "At least 390"])).toBe("");
    expect(sharedBucketPrefix(["Above 2.5", "Above 3.0", "Above 3.5"])).toBe("");
    expect(sharedBucketPrefix(["Under 2%", "Under 3%", "Under 4%"])).toBe("");
    expect(sharedBucketPrefix(["Before 2027", "Before 2028", "Before 2030"])).toBe("");
  });

  it("the bound list is load-bearing, not decorative", () => {
    // The same shapes with a non-bound leading word DO strip, so the refusal
    // above is the bound list doing the work rather than some other guard.
    expect(sharedBucketPrefix(["Exactly 370", "Exactly 380", "Exactly 390"])).toBe("Exactly ");
  });

  it("a rendered ladder still shows its bound", () => {
    const rungs: [number, string][] = [[97, "At least 370"], [57, "At least 450"]];
    expect(html(rungs)).toContain("At least 370");
  });
});

describe("the label column", () => {
  it("sizes to its content instead of pinning at 56px", () => {
    // `1.9 to 2.1%` needs ~72px at 10px mono and was rendering `1.9 to 2…`,
    // so a reader could not tell 2.0% from 2.1% on the modal outcome of the
    // next CPI print. Asserted on the class list because the truncation is a
    // layout fact, and jsdom measures no text.
    const markup = html([[45, "1.9 to 2.1%"], [41.5, "1.6 to 1.8%"]]);
    expect(markup).toContain("min-w-[56px]");
    expect(markup).toContain("max-w-[88px]");
    expect(markup).not.toContain("w-[56px] text-right");
  });

  it("still prints both the label and its probability", () => {
    const markup = html([[45, "1.9 to 2.1%"], [41.5, "1.6 to 1.8%"]]);
    expect(markup).toContain("1.9 to 2.1%");
    expect(markup).toContain("45%");
  });
});
