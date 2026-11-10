/**
 * #12373 (Epic #12288, Plan #12221 row 6): private grouping grading page
 * (`/grade/groupings`).
 *
 * Verifies:
 * 1. Kid graders (`kid: true`) resolve ONLY to pseudonyms (`kid1`..`kid4`),
 *    never a real name.
 * 2. Adult graders normalize to lowercase alphanumeric ids.
 * 3. Each grade option (`amazing`, `fine`, `no`) carries its plain-English label.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { RoundupCard } from "@/components/discover/roundup/RoundupCard";
import {
  GROUPING_GRADES,
  GROUPING_GRADE_LABELS,
  KID_PSEUDONYMS,
  buildRoundupContractForProposedCard,
  resolveGroupingGraderId,
} from "@/lib/ranking/groupingGradeSession";

describe("#12373 / #9937 grouping grading session helpers and RoundupCard reuse", () => {
  it("resolves kid graders to pseudonyms only and never leaks a typed name", () => {
    expect(resolveGroupingGraderId("Leo", true, "kid1")).toBe("kid1");
    expect(resolveGroupingGraderId("Maya", true, "kid2")).toBe("kid2");
    expect(resolveGroupingGraderId("Sam", true, "kid3")).toBe("kid3");
    expect(resolveGroupingGraderId("Zoe", true, "kid4")).toBe("kid4");
    expect(resolveGroupingGraderId("RealName", true, "not-a-kid" as never)).toBe(
      "kid1",
    );
    expect(KID_PSEUDONYMS).toEqual(["kid1", "kid2", "kid3", "kid4"]);
  });

  it("normalizes adult grader names cleanly", () => {
    expect(resolveGroupingGraderId("Alex", false, "kid2")).toBe("alex");
    expect(resolveGroupingGraderId("  Friend_1 ", false, "kid3")).toBe(
      "friend_1",
    );
  });

  it("exposes the three ruling grades (amazing / fine / no) with plain-English labels", () => {
    expect(GROUPING_GRADES).toEqual(["amazing", "fine", "no"]);
    expect(GROUPING_GRADE_LABELS.amazing).toContain("Amazing");
    expect(GROUPING_GRADE_LABELS.fine).toContain("Fine");
    expect(GROUPING_GRADE_LABELS.no).toContain("No");
  });

  it("reuses RoundupCard in previewOnly mode with 0-100% horizontal blue bars, selection-carrying subtitle, and count line (#9937)", () => {
    const contract = buildRoundupContractForProposedCard({
      kicker: "NHL · SEASON MILESTONE",
      tag: "NHL",
      title: "Connor McDavid and Nathan MacKinnon top the NHL 80-point race at 96%",
      subtitle: "Which NHL players will reach 80+ points in 2026–27?",
      count_line: "Showing 5 of 101 players · No number yet for 9 players",
      footer: "Each player is their own market. They don't add up to 100%.",
      relations: ["same_measure", "same_window", "sibling"],
      level: "member",
      selection_type: "top_5",
      rows: [
        { label: "Connor McDavid", value: "96%", market_id: 63105210, probability: 0.962, rendered_percent: 96 },
        { label: "Nathan MacKinnon", value: "96%", market_id: 63105211, probability: 0.9595, rendered_percent: 96 },
        { label: "Leon Draisaitl", value: "94%", market_id: 63105212, probability: 0.94, rendered_percent: 94 },
        { label: "Kirill Kaprizov", value: "94%", market_id: 63105213, probability: 0.935, rendered_percent: 94 },
        { label: "Macklin Celebrini", value: "90%", market_id: 63105214, probability: 0.90, rendered_percent: 90 },
      ],
    });

    const html = renderToStaticMarkup(
      <RoundupCard
        title="Connor McDavid and Nathan MacKinnon top the NHL 80-point race at 96%"
        contract={contract}
        collectionRef={null}
        items={[]}
        bundleId="grade:nhl-players-80-points-2026-27"
        previewOnly
      />,
    );

    expect(html).toContain('data-testid="roundup-card"');
    expect(html).toContain('data-testid="roundup-subtitle">Which NHL players will reach 80+ points in 2026–27?</p>');
    expect(html).toContain('data-testid="roundup-count-line">Showing 5 of 101 players · No number yet for 9 players</div>');
    const bars = [...html.matchAll(/<i class="([^"]*)" style="width:([^"]*)" data-testid="roundup-row-bar"/g)];
    expect(bars).toHaveLength(5);
    for (const b of bars) {
      expect(b[1]).toContain("bg-[var(--series-1)]");
    }
  });
});
