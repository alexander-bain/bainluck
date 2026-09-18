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
    // #6849 — `57%`, not the `56%` this asserted before the pair was rounded
    // once. The number is incidental to this test (its subject is the flag), but
    // it is not arbitrary: trimming `US_OPEN` to two names makes the payload
    // claim a TWO-SIDED contest, and `0.565 + 0.425 = 0.99` is a complement pair
    // at the documented lower edge of the band, so it is normalized and the
    // title totals 100 instead of 99. The unmodified four-competitor `US_OPEN`
    // above still prints 56/43 — that is the guard that this fixture's arity,
    // and not its numbers, is what moved it.
    expect(buildEventConceptShareCopy(strayFlag).title).toContain("57%");
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

// ───────────────────────────────────────────────────────────────────────────
// #6006 — THE LABEL IS A PREFIX, NOT THE OBJECT OF "leads the ___".
//
// None of the four fixtures above reaches the FIELD branch carrying a label:
// UFC/midterms/US Open are all two-priced duels, and the two nine-priced
// fields have their "Winner" dropped by `contestLabel`. That hole is why
// "The Odyssey leads the Best Picture at 42%." shipped and sat on production.
// ───────────────────────────────────────────────────────────────────────────

/**
 * `/event/awards/academy-awards-2027` — REAL, captured 2026-09-13 23:2xZ.
 * 40 priced nominees, so it is a field; the label survives `contestLabel`.
 * Trimmed to six competitors; the tail is more of the same and the branch
 * only ever prints `priced[0]`.
 */
const OSCARS: EventConceptShareSource = {
  event: {
    name: "The Oscars 2027",
    slug: "academy-awards-2027",
    status: "upcoming",
    venue: null,
    location: null,
  },
  primary: {
    label: "Best Picture",
    competitors: [
      { name: "The Odyssey", probability: 0.416, won: false },
      { name: "Dune: Part Three", probability: 0.088, won: false },
      { name: "The Black Ball", probability: 0.08, won: false },
      { name: "Digger", probability: 0.073, won: false },
      { name: "Wild Horse Nine", probability: 0.034, won: false },
      { name: "The Debut", probability: 0.027, won: false },
    ],
  },
};

/**
 * Every label an adapter can put in front of this branch.
 *
 * Read from the eight `"primary"` envelopes in `backend/app/utils/` rather
 * than sampled from pages, so it is the whole population and not a draw from
 * it. "Winner" (golf `event_concept.py:1129`, soccer `event_soccer.py:964`,
 * tennis) is absent on purpose — `contestLabel` drops it before this point,
 * which the two describes above already cover.
 */
const ADAPTER_LABELS: ReadonlyArray<readonly [string, string]> = [
  ["Main event", "event_combat.py:1248,1352"],
  ["Race winner", "event_f1.py:358"],
  ["General Classification", "event_cycling.py:778"],
  ["Best Picture", "event_awards.py:545 clean_category_label()"],
  ["California Governor", "event_election.py:473 clean_race_label()"],
];

/** The OSCARS field, relabelled — the shape every adapter above produces. */
const fieldLabelled = (label: string): EventConceptShareSource => ({
  ...OSCARS,
  primary: { ...OSCARS.primary, label },
});

describe("the #6006 fixture reaches the branch the others miss", () => {
  // Without this the rules below could pass over a shape that never gets
  // there, exactly as the original four fixtures did.
  it("is a field (3+ priced), unlike the three duels", () => {
    const priced = (s: EventConceptShareSource) =>
      (s.primary?.competitors ?? []).filter((c) => (c?.probability ?? 0) > 0)
        .length;
    expect(priced(OSCARS)).toBeGreaterThanOrEqual(3);
    expect([priced(UFC_CARD), priced(MIDTERMS), priced(US_OPEN)]).toEqual([
      2, 2, 2,
    ]);
  });

  it("carries a label that survives `contestLabel`, unlike the two fields", () => {
    // IRISH_OPEN and US_OPEN are fields too, but their label is dropped — so
    // they exercise the `label === null` arm, never this one.
    expect(buildEventConceptShareCopy(OSCARS).description).toContain(
      "Best Picture"
    );
    for (const dropped of [IRISH_OPEN, US_OPEN]) {
      expect(buildEventConceptShareCopy(dropped).description).not.toContain(
        "Winner"
      );
    }
  });
});

describe("a field's label is a prefix, for every label an adapter mints", () => {
  it("the live defect string is gone and the prefix form is published", () => {
    expect(buildEventConceptShareCopy(OSCARS)).toEqual({
      title: "The Oscars 2027: The Odyssey 42%",
      description: "Best Picture. The Odyssey leads at 42%.",
    });
  });

  it.each(ADAPTER_LABELS)(
    "%s reads correctly (%s)",
    (label) => {
      const { description } = buildEventConceptShareCopy(fieldLabelled(label));
      // THE REFUSAL ARM: never the article construction...
      expect(description).not.toContain(`leads the ${label}`);
      // ...AND ITS POSITIVE TWIN: the label is still published, as a prefix,
      // and the leader still gets a sentence. A fix that simply stopped
      // printing the label would satisfy the line above on its own.
      expect(description).toBe(`${label}. The Odyssey leads at 42%.`);
    }
  );

  it("never emits 'leads the' on any adapter label, dropped ones included", () => {
    const every = [
      ...ADAPTER_LABELS.map(([label]) => fieldLabelled(label)),
      fieldLabelled("Winner"),
      OSCARS,
      IRISH_OPEN,
      US_OPEN,
      UFC_CARD,
      MIDTERMS,
    ];
    for (const source of every) {
      expect(buildEventConceptShareCopy(source).description).not.toContain(
        "leads the "
      );
    }
  });

  it("agrees with the duel branch of the same function", () => {
    // The two branches disagreed for #5833's whole life: the duel carried the
    // label as a leading clause while the field inlined it after an article.
    // Same payload, same label, one competitor dropped to make it a duel.
    const duel: EventConceptShareSource = {
      ...OSCARS,
      primary: {
        ...OSCARS.primary,
        competitors: (OSCARS.primary?.competitors ?? []).slice(0, 2),
      },
    };
    const lead = (s: EventConceptShareSource) =>
      buildEventConceptShareCopy(s).description.split(". ")[0];
    expect(lead(duel)).toBe("Best Picture");
    expect(lead(OSCARS)).toBe("Best Picture");
  });

  it("still puts the venue first when a field has both", () => {
    // `where` led the sentence before this change and must keep doing so; the
    // label joins it as a second clause rather than displacing it.
    const withVenue = {
      ...OSCARS,
      event: { ...OSCARS.event, venue: "Dolby Theatre", location: "Hollywood" },
    };
    expect(buildEventConceptShareCopy(withVenue).description).toBe(
      "Dolby Theatre, Hollywood. Best Picture. The Odyssey leads at 42%."
    );
  });

  it("a labelless field is untouched by this change", () => {
    // The `label === null` arm is the one that was already right. Golf is the
    // regression control: byte-identical to the assertion above this block.
    expect(buildEventConceptShareCopy(IRISH_OPEN).description).toBe(
      "Trump International Golf Links & Hotel Ireland, Doonbeg, Ireland. Shane Lowry leads at 85%."
    );
  });
});
