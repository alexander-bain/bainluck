/**
 * ux/1070 item 2 — a fight card leads with its MAIN EVENT, as a bout.
 *
 * A concept card printed the outright shape: one name, one percentage, taken
 * from `leader`, which is the top entry of the card's whole competitor list.
 * On a 30-rider grand tour that is the favourite and the shape is right. On a
 * fight card it is the most lopsided fight of the night, and measured on
 * production 2026-09-04 it was not even in the bout the card is named after —
 * `event:ufc:26sep10`, titled "Alexandre Pantoja vs Joshua Van", led with
 * "Tai Tuivasa 84%".
 *
 * A bout is the GAME archetype: two participants, two numbers, the date.
 */
import { conceptHeadlineBout, boutDateLabel } from "@/lib/eventConceptDisplay";
import { feedItemSuppressionReason } from "@/components/discover/utils";
import type { FeedConceptData, FeedItem } from "@/lib/types";

function concept(over: Partial<FeedConceptData> = {}): FeedConceptData {
  return {
    key: "event:ufc:26sep19",
    name: "Fight Night: Pantoja vs Van",
    domain: "ufc",
    status: "upcoming",
    start_date: "2026-09-20T03:15:00Z",
    is_major: false,
    fight_count: 13,
    ...over,
  } as FeedConceptData;
}

const REAL_BOUT = {
  competitors: [
    { name: "Alexandre Pantoja", probability: 0.63 },
    { name: "Joshua Van", probability: 0.38 },
  ],
  commence_time: "2026-09-20T03:15:00Z",
};

describe("conceptHeadlineBout", () => {
  it("gives both fighters and both numbers", () => {
    const bout = conceptHeadlineBout(concept({ headline_bout: REAL_BOUT }));
    expect(bout).not.toBeNull();
    expect(bout!.sides.map((s) => s.name)).toEqual([
      "Alexandre Pantoja",
      "Joshua Van",
    ]);
  });

  it("prints a pair that sums to 100, not the 101 the raw prices give", () => {
    // 0.63 + 0.38 = 1.01 — this is #2582's class, and the shared
    // `renderedOutcomeRowPercents` treatment is what stops it.
    const bout = conceptHeadlineBout(concept({ headline_bout: REAL_BOUT }))!;
    const [a, b] = bout.sides.map((s) => s.percent);
    expect(a + b).toBe(100);
    expect(a).toBeGreaterThan(b);
  });

  it("carries the date of the bout, not of the card", () => {
    const bout = conceptHeadlineBout(
      concept({
        start_date: "2026-09-19T22:15:00Z",
        headline_bout: REAL_BOUT,
      }),
      "en-US",
    )!;
    expect(bout.dateLabel).toBe(boutDateLabel("2026-09-20T03:15:00Z", "en-US"));
  });

  it("falls back to the card's start when the bout carries no time", () => {
    const bout = conceptHeadlineBout(
      concept({
        headline_bout: { ...REAL_BOUT, commence_time: null },
      }),
      "en-US",
    )!;
    expect(bout.dateLabel).toBe(boutDateLabel("2026-09-20T03:15:00Z", "en-US"));
  });

  it("is null when the card has no bout — the leader arm still owns those", () => {
    expect(conceptHeadlineBout(concept())).toBeNull();
    expect(
      conceptHeadlineBout(concept({ headline_bout: null })),
    ).toBeNull();
  });

  it("refuses half a bout", () => {
    const cases = [
      { competitors: [{ name: "Alexandre Pantoja", probability: 0.63 }] },
      {
        competitors: [
          { name: "Alexandre Pantoja", probability: 0.63 },
          { name: "", probability: 0.38 },
        ],
      },
      {
        competitors: [
          { name: "Alexandre Pantoja", probability: 0.63 },
          { name: "Joshua Van", probability: null },
        ],
      },
      {
        competitors: [
          { name: "A", probability: 0.4 },
          { name: "B", probability: 0.3 },
          { name: "C", probability: 0.3 },
        ],
      },
      {
        competitors: [
          { name: "A", probability: 1.4 },
          { name: "B", probability: -0.4 },
        ],
      },
    ];
    for (const headline_bout of cases) {
      expect(
        conceptHeadlineBout(concept({ headline_bout: headline_bout as never })),
      ).toBeNull();
    }
  });

  it("settled means settled — a WHAT-HIT card leads with the result", () => {
    expect(
      conceptHeadlineBout(
        concept({ marquee_whathit: true, headline_bout: REAL_BOUT }),
      ),
    ).toBeNull();
  });
});

describe("the admitting classifier and the renderer agree", () => {
  const item = (data: FeedConceptData): FeedItem =>
    ({ type: "concept", score: 70, data }) as FeedItem;

  it("admits a card whose only content is a real bout", () => {
    const data = concept({ headline_bout: REAL_BOUT });
    expect(feedItemSuppressionReason(item(data), Date.now())).toBeNull();
    expect(conceptHeadlineBout(data)).not.toBeNull();
  });

  it("still drops a card with neither a bout nor a leader", () => {
    expect(feedItemSuppressionReason(item(concept()), Date.now())).toBe(
      "empty_concept",
    );
  });

  it("still drops a card whose bout is half-priced", () => {
    const data = concept({
      headline_bout: {
        competitors: [
          { name: "Alexandre Pantoja", probability: 0.63 },
          { name: "Joshua Van", probability: null },
        ],
      },
    });
    expect(feedItemSuppressionReason(item(data), Date.now())).toBe(
      "empty_concept",
    );
    expect(conceptHeadlineBout(data)).toBeNull();
  });

  it("keeps admitting a leader-only card — the grand tours are unchanged", () => {
    const vuelta = concept({
      key: "event:cycling:vuelta-2026",
      name: "Vuelta a España 2026",
      domain: "cycling",
      status: "live",
      fight_count: 0,
      leader: { name: "Tadej Pogacar", probability: 0.751, field_size: 30 },
    });
    expect(feedItemSuppressionReason(item(vuelta), Date.now())).toBeNull();
    expect(conceptHeadlineBout(vuelta)).toBeNull();
  });
});
