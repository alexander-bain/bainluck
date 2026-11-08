/**
 * #12338 — Live event page hero at 390px fits one-decimal win probabilities
 * ("40.4% – 59.6%") between the two 56px team logo boxes without touching or
 * overlapping for any value from 0.1% to 99.9%.
 *
 * On `/events/15340134` (West Virginia Mountaineers @ Texas Tech Red Raiders)
 * while live at 390×844 in WebKit, "Mountaineers" widened the away column to
 * 81.4px, narrowing the centre column to 188.6px (centre x=182.3px, 94.3px from
 * the 56px home logo box). At 35px/24px (`min-[390px]:text-[35px]` /
 * `min-[390px]:text-[24px]`), "40.4% – 59.6%" measured 204.1px wide, overlapping
 * the Red Raiders logo box by 8.4px.
 *
 * Stepping the two-sided tenths fit pair to 28px/18px at 390px (176.0px wide in
 * WebKit, 174.4px in Chromium across every 0.1%–99.9% pair with `minWidth: 2ch`
 * on the whole digits), 26px/17px at 375px, and 23px/15px at 360px keeps
 * positive horizontal clearance on both logo boxes while leaving `tenths={false}`,
 * band pairs (`<1%` / `>99%`), single-number (`awayWithheld`), and `sm:` (640px+)
 * untouched.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import EventHeroProbabilityPair from "@/components/EventHeroProbabilityPair";

describe("#12338 — live event hero one-decimal pair clears both team logos at 390px", () => {
  test("renders 28px/18px at 390px (and 2ch digit reservation) for /events/15340134 40.4% – 59.6% and across 0.5%–99.5%", () => {
    const sampleProbs = [0.005, 0.01, 0.098, 0.404, 0.5, 0.596, 0.888, 0.99, 0.995];

    for (const homeProb of sampleProbs) {
      const awayProb = Number((1 - homeProb).toFixed(4));
      const html = renderToStaticMarkup(
        <EventHeroProbabilityPair
          homeProb={homeProb}
          awayProb={awayProb}
          homePct={Math.round(homeProb * 100)}
          awayPct={Math.round(awayProb * 100)}
          homeColor="#CC0000"
          awayColor="#002855"
          started
          tenths
        />,
      );

      expect(html).toContain(
        "text-[23px] min-[375px]:text-[26px] min-[390px]:text-[28px] sm:text-[44px]",
      );
      expect(html).toContain(
        "text-[15px] min-[375px]:text-[17px] min-[390px]:text-[18px] sm:text-[24px]",
      );
      expect(html).not.toContain("min-[390px]:text-[35px]");
      expect(html).not.toContain("min-[390px]:text-[48px]");
      expect(html.match(/min-width:2ch/g)).toHaveLength(2);
    }
  });
});
