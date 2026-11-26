import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import {
  AwardCategoryPairedCard,
  cleanPairedCardSubtitle,
} from "@/components/discover/forms/AwardCategoryPairedCard";
import { PAIRED_METRIC_REGISTER } from "@/lib/discover/visualForms";
import { findBannedCopy, visibleTextFromHtml } from "@/lib/copyBans";

describe("#13793 Best Animated Feature card subtitle carries no TMDB attribution", () => {
  it("strips TMDB attribution clauses in cleanPairedCardSubtitle", () => {
    expect(
      cleanPairedCardSubtitle(
        "Top 4 animated films by win % (#6330235 + #58492239) · Sourced TMDB credits & posters",
      ),
    ).toBe("Top 4 animated films by win %");
  });

  it("ships clean subtitle on oscars-2027-best-animated and renders no TMDB text", () => {
    const spec = PAIRED_METRIC_REGISTER["oscars-2027-best-animated"];
    expect(spec).toBeDefined();
    expect(spec.subtitle).toBe("Top 4 animated films by win %");
    expect(spec.subtitle).not.toMatch(/tmdb/i);
    expect(findBannedCopy(spec.subtitle)).toEqual([]);

    const html = renderToStaticMarkup(<AwardCategoryPairedCard set={spec} showHeader />);
    const visible = visibleTextFromHtml(html);
    expect(visible).toContain("Top 4 animated films by win %");
    expect(visible).not.toMatch(/\btmdb\b/i);
  });
});
