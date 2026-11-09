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

import {
  GROUPING_GRADES,
  GROUPING_GRADE_LABELS,
  KID_PSEUDONYMS,
  resolveGroupingGraderId,
} from "@/lib/ranking/groupingGradeSession";

describe("#12373 grouping grading session helpers", () => {
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
});
