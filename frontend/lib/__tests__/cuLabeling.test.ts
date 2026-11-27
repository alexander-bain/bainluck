import {
  buildSubmissionPayload,
  emptyCuDraft,
  normalizeRaterName,
} from "../cuLabeling";

describe("cuLabeling (#13900)", () => {
  it("normalizes typed rater names and requires non-empty identity", () => {
    expect(normalizeRaterName("  Grader   One ")).toBe("Grader One");

    const draft = emptyCuDraft();
    draft.subjectMode = "none_of_these";
    draft.noSingleDay = true;
    draft.geography = "us";
    draft.structure = "neither";
    draft.stakes = 2;
    draft.breadth = 3;

    const missingName = buildSubmissionPayload({
      split: "sealed",
      role: "primary",
      rater: "   ",
      marketId: 1001,
      draft,
    });
    expect(missingName.ok).toBe(false);
  });

  it("forces taste fields to null and requires written evidence in tiebreak role", () => {
    const draft = emptyCuDraft();
    draft.subjectMode = "candidate";
    draft.selectedCandidates = ["Vermont House Orleans-3"];
    draft.eventDate = "2028-11-07";
    draft.geography = "local";
    draft.structure = "neither";
    draft.stakes = 4;
    draft.breadth = 4;

    const missingEvidence = buildSubmissionPayload({
      split: "sealed",
      role: "tiebreak",
      rater: "Tiebreaker",
      marketId: 70136122,
      draft,
    });
    expect(missingEvidence.ok).toBe(false);

    draft.evidenceNote = "State house seat -> local.";
    const validTiebreak = buildSubmissionPayload({
      split: "sealed",
      role: "tiebreak",
      rater: "Tiebreaker",
      marketId: 70136122,
      draft,
    });
    expect(validTiebreak.ok).toBe(true);
    if (validTiebreak.ok) {
      expect(validTiebreak.payload.stakes).toBeNull();
      expect(validTiebreak.payload.breadth).toBeNull();
      expect(validTiebreak.payload.evidence_note).toBe("State house seat -> local.");
    }
  });
});
