import {
  buildSubmissionPayload,
  COUNTRY_OPTIONS,
  emptyCuDraft,
  EVENT_DATE_CANNOT_TELL,
  formatEventStartSentence,
  formatPayoutDateSentence,
  formatPeerEventDate,
  normalizeRaterName,
} from "../cuLabeling";

describe("cuLabeling", () => {
  it("normalizes typed rater names and requires non-empty identity", () => {
    expect(normalizeRaterName("  Grader   One ")).toBe("Grader One");

    const draft = emptyCuDraft();
    draft.subjectMode = "none_of_these";
    draft.eventDateMode = "no_single_day";
    draft.geography = "us";
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

  it("supports Specific day, No single day, and Cannot tell without format or claim fields", () => {
    const draft = emptyCuDraft();
    draft.subjectMode = "candidate";
    draft.selectedCandidates = ["Marvell"];
    draft.eventDateMode = "cannot_tell";
    draft.geography = "us";
    draft.stakes = 2;
    draft.breadth = 2;

    const res = buildSubmissionPayload({
      split: "practice",
      role: "primary",
      rater: "Grader One",
      marketId: 71609185,
      draft,
    });
    expect(res.ok).toBe(true);
    if (res.ok) {
      expect(res.payload.event_date_answer).toBe(EVENT_DATE_CANNOT_TELL);
      expect(res.payload.no_single_day).toBe(false);
      expect("structure_answer" in res.payload).toBe(false);
      expect("claim_frame" in res.payload).toBe(false);
    }
  });

  it("requires an explicit event day choice and leaves taste null in tiebreak", () => {
    const missingDay = emptyCuDraft();
    missingDay.subjectMode = "candidate";
    missingDay.selectedCandidates = ["Vermont House Orleans-3"];
    missingDay.geography = "local";
    missingDay.stakes = 1;
    missingDay.breadth = 1;

    expect(
      buildSubmissionPayload({
        split: "sealed",
        role: "primary",
        rater: "Grader One",
        marketId: 70136122,
        draft: missingDay,
      }).ok
    ).toBe(false);

    const draft = emptyCuDraft();
    draft.subjectMode = "candidate";
    draft.selectedCandidates = ["Vermont House Orleans-3"];
    draft.eventDateMode = "date";
    draft.eventDate = "2028-11-07";
    draft.geography = "local";
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
      expect(validTiebreak.payload.event_date_answer).toBe("2028-11-07");
      expect(validTiebreak.payload.evidence_note).toBe("State house seat -> local.");
    }
  });

  it("provides non-US ISO country codes and plain date formatters", () => {
    const codes = new Set(COUNTRY_OPTIONS.map((c) => c.code));
    expect(codes.has("CA")).toBe(true);
    expect(codes.has("GB")).toBe(true);
    expect(codes.has("US")).toBe(false);

    expect(formatPayoutDateSentence("2026-11-30T15:00:00+00:00", "polymarket")).toBe(
      "Polymarket settles this on Nov 30, 2026. That is often not the day the thing itself happens."
    );
    expect(formatPayoutDateSentence("2026-11-30T15:00:00+00:00", "kalshi")).toBe(
      "Kalshi settles this on Nov 30, 2026. That is often not the day the thing itself happens."
    );
    expect(formatEventStartSentence("2026-11-28T20:30:00+00:00")).toBe(
      "Event starts Nov 28, 2026 (US Eastern)."
    );
    expect(formatPeerEventDate("cannot_tell", false)).toBe("Cannot tell");
    expect(formatPeerEventDate(null, true)).toBe("No single day");
  });
});
