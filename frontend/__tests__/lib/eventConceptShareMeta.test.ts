/**
 * #5833 — the copy a pasted `/event/<domain>/<slug>` link unfurls with.
 *
 * Every non-settled case below is a REAL payload, trimmed but not reshaped,
 * captured from `GET /api/event/{key}` on production at 2026-09-13 ~06:45Z.
 * The percentages are what `Math.round(p * 100)` actually produces for those
 * floats — checked in node, because Python's banker's rounding disagrees about
 * two of them (0.565 is 56%, not 57%).
 *
 * The two settled branches have no natural specimen: the adapters only
 * synthesize current events, so a finished card answers with an empty envelope,
 * and the one finished-in-real-life field on the site
 * (`event:tennis:us-open-men-s-singles-winner`) still read `status: "live"`
 * with every `won` false. Those two are manufactured, and labelled as such.
 */

import {
  buildEventConceptShareCopy,
  type EventConceptShareSource,
} from "@/lib/eventConceptShareMeta";

// ───────────────────────────────────────────────────────────────────────────
// Real production payloads, trimmed to the fields this copy reads.
// ───────────────────────────────────────────────────────────────────────────

/** `/event/ufc/26sep15` — a fight card. Two priced sides; the name has a colon. */
const UFC_CARD: EventConceptShareSource = {
  event: {
    name: "Contender Series: Hunt vs Perea",
    slug: "contender-series-hunt-vs-perea-26sep15",
    status: "upcoming",
    venue: null,
    location: null,
  },
  primary: {
    label: "Main event",
    competitors: [
      { name: "Zevan Hunt", probability: 0.545 },
      { name: "Mayton Perea", probability: 0.44 },
    ],
  },
};

/**
 * `/event/election/2026-midterms` — the link `BottomNav` and `DesktopNav` carry
 * on every page of the site. 25 competitors, of which exactly two are priced.
 */
const MIDTERMS: EventConceptShareSource = {
  event: {
    name: "2026 Midterm Elections",
    slug: null,
    status: "upcoming",
    venue: null,
    location: null,
  },
  primary: {
    label: "California Governor",
    competitors: [
      { name: "Xavier Becerra", probability: 0.95, won: false },
      { name: "Steve Hilton", probability: 0.046, won: false },
      { name: "Tom Steyer", probability: 0.0, won: false },
      { name: "Butch Ware", probability: 0.0, won: false },
      { name: "Ché Ahn", probability: 0.0, won: false },
    ],
  },
};

/** `/event/tennis/us-open-men-s-singles-winner` — label is the bare role word. */
const US_OPEN: EventConceptShareSource = {
  event: {
    name: "US Open Men's Singles Winner",
    slug: null,
    status: "live",
    venue: null,
    location: null,
  },
  primary: {
    label: "Winner",
    competitors: [
      { name: "Alexander Zverev", probability: 0.565, won: false },
      { name: "Ben Shelton", probability: 0.425, won: false },
      { name: "Cameron Norrie", probability: 0.0, won: false },
      { name: "Karen Khachanov", probability: 0.0, won: false },
    ],
  },
};

/** `/event/golf/amgen-irish-open` — a real FIELD: 138 entrants, 9 priced. */
const IRISH_OPEN: EventConceptShareSource = {
  event: {
    name: "Amgen Irish Open",
    slug: "amgen-irish-open",
    status: "live",
    venue: "Trump International Golf Links & Hotel Ireland",
    location: "Doonbeg, Ireland",
  },
  primary: {
    label: "Winner",
    competitors: [
      { name: "Shane Lowry", probability: 0.847 },
      { name: "Jacob Skov Olesen", probability: 0.117 },
      { name: "Joaquin Niemann", probability: 0.026 },
      { name: "Tom McKibbin", probability: 0.003 },
      { name: "Rasmus Hojgaard", probability: 0.002 },
      { name: "Alex Noren", probability: 0.001 },
      { name: "Adrien Saddier", probability: 0.001 },
      { name: "John Parry", probability: 0.001 },
      { name: "Angel Ayora", probability: 0.001 },
      { name: "Padraig Harrington", probability: 0.0 },
    ],
  },
};

describe("the fixtures are the payloads they claim to be", () => {
  // Without this, every rule below could be passing over a shape production
  // never serves, and the suite would stay green through a payload change.
  it("carries a colon in exactly one event name, which is what the separator turns on", () => {
    const withColon = [UFC_CARD, MIDTERMS, US_OPEN, IRISH_OPEN].filter((s) =>
      (s.event?.name ?? "").includes(":")
    );
    expect(withColon).toEqual([UFC_CARD]);
  });

  it("carries a 0% tail on the two winner fields, so the drop is exercised", () => {
    for (const source of [US_OPEN, IRISH_OPEN, MIDTERMS]) {
      const zeros = (source.primary?.competitors ?? []).filter(
        (c) => c?.probability === 0
      );
      expect(zeros.length).toBeGreaterThan(0);
    }
  });

  it("gives exactly one specimen three or more priced competitors", () => {
    const priced = (s: EventConceptShareSource) =>
      (s.primary?.competitors ?? []).filter((c) => (c?.probability ?? 0) > 0)
        .length;
    expect(priced(IRISH_OPEN)).toBe(9);
    expect([priced(UFC_CARD), priced(MIDTERMS), priced(US_OPEN)]).toEqual([
      2, 2, 2,
    ]);
  });
});

describe("a duel names both sides", () => {
  it("the fight card, with an em dash because its name already has a colon", () => {
    expect(buildEventConceptShareCopy(UFC_CARD)).toEqual({
      title: "Contender Series: Hunt vs Perea — Zevan Hunt 55%, Mayton Perea 44%",
      description: "Main event. Zevan Hunt 55%, Mayton Perea 44%.",
    });
  });

  it("the title never prints two colons", () => {
    // The whole reason the separator is derived rather than fixed.
    const { title } = buildEventConceptShareCopy(UFC_CARD);
    expect(title.split(":").length - 1).toBe(1);
  });

  it("the midterms, with a colon because its name has none", () => {
    expect(buildEventConceptShareCopy(MIDTERMS)).toEqual({
      title: "2026 Midterm Elections: Xavier Becerra 95%, Steve Hilton 5%",
      description: "California Governor. Xavier Becerra 95%, Steve Hilton 5%.",
    });
  });

  it("drops the 0% tail rather than printing '0%' three times", () => {
    const { title } = buildEventConceptShareCopy(MIDTERMS);
    expect(title).not.toContain("0%,");
    expect(title).not.toContain("Tom Steyer");
  });
});

describe("a label that names only the role is not put in a sentence", () => {
  it("the US Open field says 'leads at', never 'leads the Winner at'", () => {
    expect(buildEventConceptShareCopy(US_OPEN)).toEqual({
      title: "US Open Men's Singles Winner: Alexander Zverev 56%, Ben Shelton 43%",
      description: "Alexander Zverev 56%, Ben Shelton 43%.",
    });
  });

  it("the golf field, same generic label, same silence about it", () => {
    expect(buildEventConceptShareCopy(IRISH_OPEN)).toEqual({
      title: "Amgen Irish Open: Shane Lowry 85%",
      description:
        "Trump International Golf Links & Hotel Ireland, Doonbeg, Ireland. Shane Lowry leads at 85%.",
    });
  });

  it("but a label that names a real contest IS used", () => {
    // The other direction, so the regex cannot quietly widen to swallow
    // "Main event" or "California Governor".
    expect(buildEventConceptShareCopy(UFC_CARD).description).toContain(
      "Main event"
    );
    expect(buildEventConceptShareCopy(MIDTERMS).description).toContain(
      "California Governor"
    );
  });
});

describe("a field names the leader only", () => {
  it("nine priced golfers produce one name in the title", () => {
    const { title } = buildEventConceptShareCopy(IRISH_OPEN);
    expect(title).toBe("Amgen Irish Open: Shane Lowry 85%");
    expect(title).not.toContain("Jacob Skov Olesen");
  });

  it("the leader is chosen by price, not by arrival order", () => {
    const shuffled: EventConceptShareSource = {
      ...IRISH_OPEN,
      primary: {
        ...IRISH_OPEN.primary,
        competitors: [...(IRISH_OPEN.primary?.competitors ?? [])].reverse(),
      },
    };
    expect(buildEventConceptShareCopy(shuffled)).toEqual(
      buildEventConceptShareCopy(IRISH_OPEN)
    );
  });
});

describe("a settled event leads with the result, and only an authoritative one", () => {
  // Manufactured — see the file header. No finished concept was reachable.
  const settled: EventConceptShareSource = {
    event: {
      name: "Amgen Irish Open",
      slug: "amgen-irish-open",
      status: "settled",
      venue: "Trump International Golf Links & Hotel Ireland",
      location: "Doonbeg, Ireland",
    },
    primary: {
      label: "Winner",
      competitors: [
        { name: "Shane Lowry", probability: 0.847, won: true },
        { name: "Jacob Skov Olesen", probability: 0.117, won: false },
      ],
    },
  };

  it("names the winner and prints no probability", () => {
    const copy = buildEventConceptShareCopy(settled);
    expect(copy).toEqual({
      title: "Amgen Irish Open: Shane Lowry won",
      description: "Final: Shane Lowry won.",
    });
    expect(copy.title).not.toContain("%");
    expect(copy.description).not.toContain("%");
  });

  it("says so when the event is over and nothing flagged a winner", () => {
    const noWinner: EventConceptShareSource = {
      ...settled,
      primary: {
        ...settled.primary,
        competitors: (settled.primary?.competitors ?? []).map((c) => ({
          ...c,
          won: false,
        })),
      },
    };
    const copy = buildEventConceptShareCopy(noWinner);
    expect(copy).toEqual({
      title: "Amgen Irish Open: Final",
      description:
        "Final. Bain Luck does not have a confirmed result for Amgen Irish Open yet.",
    });
    // The #1495 rung: a forecast on a closed question is the thing being
    // refused, so a price must not survive into either string.
    expect(copy.title).not.toContain("%");
    expect(copy.description).not.toContain("%");
    expect(copy.description).not.toContain("Shane Lowry");
  });

  it("a 99% favourite in a LIVE event is never called a winner", () => {
    // Not hypothetical, and the reason `settledChampion()` is not reused here:
    // `event:ufc:26sep12` was `status: "live"` with its favourite at 0.99 while
    // this was written, and that helper's >=0.9 fallback would have unfurled a
    // fight in progress as decided.
    const nearCertain: EventConceptShareSource = {
      event: { name: "Fight Night: Klose vs Gantt", status: "live" },
      primary: {
        label: "Main event",
        competitors: [
          { name: "Amanda Klose", probability: 0.99, won: null },
          { name: "Gabriella Gantt", probability: 0.01, won: null },
        ],
      },
    };
    const copy = buildEventConceptShareCopy(nearCertain);
    expect(copy.title).toBe(
      "Fight Night: Klose vs Gantt — Amanda Klose 99%, Gabriella Gantt 1%"
    );
    expect(copy.title).not.toContain("won");
    expect(copy.description).not.toContain("Final");
  });

  it("a `won` flag on a live event is not enough on its own", () => {
    // Both halves of the authoritative pair are required. A stray flag on a
    // running event must not publish a result.
    const strayFlag: EventConceptShareSource = {
      ...US_OPEN,
      primary: {
        ...US_OPEN.primary,
        competitors: [
          { name: "Alexander Zverev", probability: 0.565, won: true },
          { name: "Ben Shelton", probability: 0.425, won: false },
        ],
      },
    };
    expect(buildEventConceptShareCopy(strayFlag).title).toContain("56%");
    expect(buildEventConceptShareCopy(strayFlag).title).not.toContain("won");
  });
});

describe("an unusable payload claims nothing", () => {
  it("an empty object does not throw and names no competitor", () => {
    expect(buildEventConceptShareCopy({})).toEqual({
      title: "Event",
      description: "Event: every market on this event, as one clean probability.",
    });
  });

  it("a named event with no priced competitor says what the page is", () => {
    expect(
      buildEventConceptShareCopy({
        event: { name: "Amgen Irish Open", venue: "Doonbeg" },
        primary: { label: "Winner", competitors: [] },
      })
    ).toEqual({
      title: "Amgen Irish Open",
      description:
        "Amgen Irish Open, Doonbeg. Every market on this event, as one clean probability.",
    });
  });

  it("survives null competitors and blank names", () => {
    const copy = buildEventConceptShareCopy({
      event: { name: "  ", status: null },
      primary: {
        label: null,
        competitors: [
          null as unknown as { name: string },
          { name: "   ", probability: 0.6 },
          { name: "Real Name", probability: 0.4 },
        ],
      },
    });
    expect(copy.title).toBe("Event: Real Name 40%");
    expect(copy.description).toBe("Real Name leads at 40%.");
  });

  it("the description is truncated rather than run long", () => {
    const copy = buildEventConceptShareCopy({
      event: { name: "Long Event", venue: "V".repeat(400) },
      primary: { label: "Winner", competitors: [] },
    });
    // 182, not 180: `truncateShareText` slices to `maxLength - 1` and then
    // appends three characters, so its own ceiling overshoots by two. Asserted
    // as it behaves rather than as it reads — the helper is shared with
    // `/tournaments/[slug]` and `/events/[id]`, and quietly changing what those
    // two publish is not this ship. A bound, so a later fix still passes.
    expect(copy.description.length).toBeLessThanOrEqual(182);
    expect(copy.description.endsWith("...")).toBe(true);
  });
});
