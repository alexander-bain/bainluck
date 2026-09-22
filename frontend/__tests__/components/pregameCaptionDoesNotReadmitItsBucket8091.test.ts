import {
  feedContextSnippet,
  feedExpandedContext,
} from "../../components/discover/utils";

/**
 * #8091 — the "See more" #6567 accidentally minted.
 *
 * #6567 replaced an unsettled game card's caption ("Close matchup") with the two
 * teams' seasons ("TOR 77-80 · BAL 76-81"), on the thesis — which shipped — that
 * the bucket label is the probability bar restated as prose.
 *
 * `feedExpandedContext` decides what "See more" opens to, and it decided it by
 * asking whether a candidate repeats the SNIPPET. While the snippet was the
 * bucket label that question also caught `reason`'s trailing "close matchup"
 * clause, so the card offered no "See more" at all. Once the snippet became the
 * records, the label was no longer anywhere in the comparison set — and the
 * expanded context re-admitted the exact sentence #6567 had just removed.
 *
 * Measured on production 2026-09-22 at 21:4xZ, both MLB cards on page one:
 *
 *   collapsed  TOR 77-80 · BAL 76-81                                [See more]
 *   expanded   TOR 77-80 · BAL 76-81 — Starting soon — close matchup
 *
 * The specimens below are those two cards' served payloads.
 */

const pregameCard = (overrides: Record<string, unknown> = {}) =>
  ({
    type: "event" as const,
    headline: "TOR 77-80 · BAL 76-81",
    reason: "Starting soon — close matchup",
    context_summary: null,
    ...overrides,
    data: {
      status: "scheduled",
      highlight: { label: "Close matchup" },
      ...((overrides.data as Record<string, unknown>) || {}),
    },
  }) as any;

describe("#8091 a pregame card's See more never reopens the bucket it replaced", () => {
  test("the production specimen expands to nothing, so no See more is offered", () => {
    const item = pregameCard();
    const snippet = feedContextSnippet(item);

    expect(snippet).toBe("TOR 77-80 · BAL 76-81");
    // `ExpandableContextText` shows the affordance only when these differ.
    expect(feedExpandedContext(item)).toBe(snippet);
  });

  test("the second specimen behaves the same — this is a class, not one card", () => {
    const item = pregameCard({
      headline: "CLE 81-75 · BOS 84-72",
      data: { highlight: { label: "Close matchup" } },
    });
    expect(feedExpandedContext(item)).toBe(feedContextSnippet(item));
  });

  test("the bucket clause is what is dropped, not the whole reason", () => {
    // "Starting soon" alone adds nothing the reader has not seen either, but the
    // point of the assertion above is the clause that RESTATES THE BAR. Prove it
    // is the label doing the work: strip the label and the sentence comes back.
    const withoutLabel = pregameCard({ data: { highlight: { label: null } } });
    expect(feedExpandedContext(withoutLabel)).toContain("close matchup");
  });

  test("ANTI-VACUITY: a reason that genuinely adds something still expands", () => {
    // If this fix were "event cards never expand", this test would fail — and a
    // guard that only ever asserts an absence cannot tell a fix from a deletion.
    const item = pregameCard({
      reason: "Toronto has taken nine of the last eleven meetings in Baltimore",
    });
    const expanded = feedExpandedContext(item);
    expect(expanded).not.toBe(feedContextSnippet(item));
    expect(expanded).toContain("nine of the last eleven");
  });

  test("ANTI-VACUITY: a futures card is not an event and is untouched", () => {
    const futures = {
      type: "futures" as const,
      headline: "Denny Hamlin leads at 30%",
      reason: "Denny Hamlin moved up 4 points since Sep 1",
      context_summary: null,
      data: { name: "NASCAR Cup Series: 2026 Champion", hook_description: "" },
    } as any;
    expect(feedExpandedContext(futures)).toContain("4 points");
  });

  test("the pre-#6567 shape is still handled — the old snippet caught it too", () => {
    const legacy = pregameCard({ headline: "Close matchup" });
    expect(feedExpandedContext(legacy)).toBe(feedContextSnippet(legacy));
  });

  test("an event card with no highlight block does not throw", () => {
    const bare = { ...pregameCard(), data: { status: "scheduled" } } as any;
    expect(() => feedExpandedContext(bare)).not.toThrow();
  });
});
