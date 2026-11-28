import {
  buildSubmissionPayload,
  COUNTRY_OPTIONS,
  DEFAULT_CLAIM_COMPARATORS,
  DEFAULT_CLAIM_HORIZON_KINDS,
  DEFAULT_CLAIM_MEASURES,
  emptyCuDraft,
  formatPayoutDateSentence,
  formatPeerClaimFrame,
  MEASURE_GROUPS,
  normalizeRaterName,
} from "../cuLabeling";

describe("cuLabeling", () => {
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

  it("submits all six canonical writer claim slots and leaves taste null in tiebreak", () => {
    expect(DEFAULT_CLAIM_MEASURES).toContain("wins");
    expect(DEFAULT_CLAIM_COMPARATORS).toContain("gte");
    expect(DEFAULT_CLAIM_HORIZON_KINDS).toContain("annual");

    const draft = emptyCuDraft();
    draft.subjectMode = "candidate";
    draft.selectedCandidates = ["Vermont House Orleans-3"];
    draft.eventDate = "2028-11-07";
    draft.geography = "local";
    draft.structure = "neither";
    draft.claim = {
      measure: "vote_share",
      comparator: "gte",
      value: "50",
      unit: "%",
      horizon_kind: "none_of_these",
      window_date: "",
    };
    draft.stakes = 4;
    draft.breadth = 4;

    const missingEvidence = buildSubmissionPayload({
      split: "sealed",
      role: "tiebreak",
      rater: "Reviewer Three",
      marketId: 70136122,
      draft,
    });
    expect(missingEvidence.ok).toBe(false);

    draft.evidenceNote = "State house seat -> local.";
    const validTiebreak = buildSubmissionPayload({
      split: "sealed",
      role: "tiebreak",
      rater: "Reviewer Three",
      marketId: 70136122,
      draft,
    });
    expect(validTiebreak.ok).toBe(true);
    if (validTiebreak.ok) {
      expect(validTiebreak.payload.stakes).toBeNull();
      expect(validTiebreak.payload.breadth).toBeNull();
      expect(validTiebreak.payload.claim_frame).toEqual({
        measure: "vote_share",
        comparator: "gte",
        value: "50",
        unit: "%",
        horizon_kind: "none_of_these",
      });
      expect(validTiebreak.payload.evidence_note).toBe("State house seat -> local.");
    }
  });

  it("covers all 47 measures in grouped plain-English choices without duplicates", () => {
    const groupedValues = MEASURE_GROUPS.flatMap((g) => g.options.map((o) => o.value));
    expect(new Set(groupedValues).size).toBe(groupedValues.length);
    expect(groupedValues.slice().sort()).toEqual([...DEFAULT_CLAIM_MEASURES].sort());
  });

  it("provides ISO country codes for the country picker and plain payout dates", () => {
    const codes = new Set(COUNTRY_OPTIONS.map((c) => c.code));
    expect(codes.has("CA")).toBe(true);
    expect(codes.has("GB")).toBe(true);
    expect(codes.has("US")).toBe(false);

    expect(formatPayoutDateSentence("2026-11-30T15:00:00+00:00")).toBe(
      "The site pays out on Nov 30, 2026. That is often not the day of the event."
    );
    expect(formatPeerClaimFrame({ measure: "price_high", value: "100,000", unit: "$" })).toBe(
      "measure: price_high · value: 100,000 · unit: $"
    );
  });
});
