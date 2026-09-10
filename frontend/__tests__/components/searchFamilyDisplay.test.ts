// #993 L2-42: composed search family row display logic (D1: probabilities only).

import {
  leaderLabel,
  movementArrow,
  resolutionLabel,
  cleanName,
  familyShownIds,
  familyRowTitles,
  familySharedHead,
  FAMILY_ROW_VISIBLE_CHARS,
} from "../../components/searchFamilyDisplay";

const mkMarket = (over: Record<string, unknown> = {}) => ({
  id: 1,
  name: "NBA: LeBron James Next Team",
  outcome_count: 5,
  resolution_date: null,
  top_outcomes: [
    { id: 1, name: "Cleveland Cavaliers", probability: 0.27, movement: 0.05, american_odds: -160 },
    { id: 2, name: "Other", probability: 0.5, movement: null, american_odds: null },
  ],
  ...over,
}) as any;

describe("searchFamilyDisplay", () => {
  test("leaderLabel shows leader name + probability, NEVER odds (D1)", () => {
    const label = leaderLabel(mkMarket());
    expect(label).toBe("Cleveland Cavaliers 27%");
    // no odds strings (american_odds -160 must not appear)
    expect(label).not.toMatch(/-?\d{3}|\+\d/); // no american-odds patterns
  });

  test("leaderLabel null when no probability outcomes", () => {
    expect(leaderLabel(mkMarket({ top_outcomes: [{ id: 1, name: "x", probability: null }] }))).toBeNull();
  });

  test("movementArrow only fires at >= 2 points", () => {
    expect(movementArrow(0.05)).toEqual({ up: true, points: 5 });
    expect(movementArrow(-0.03)).toEqual({ up: false, points: 3 });
    expect(movementArrow(0.01)).toBeNull(); // below 2pt threshold
    expect(movementArrow(null)).toBeNull();
  });

  test("resolutionLabel only within 30 days", () => {
    const soon = new Date(Date.now() + 5 * 86_400_000).toISOString();
    const far = new Date(Date.now() + 100 * 86_400_000).toISOString();
    const past = new Date(Date.now() - 5 * 86_400_000).toISOString();
    expect(resolutionLabel(soon)).not.toBeNull();
    expect(resolutionLabel(far)).toBeNull();
    expect(resolutionLabel(past)).toBeNull();
    expect(resolutionLabel(null)).toBeNull();
  });

  test("cleanName strips trailing year / question mark", () => {
    expect(cleanName("Democratic Presidential Nominee 2028")).toBe("Democratic Presidential Nominee");
    expect(cleanName("Who will be confirmed as Fed Chair?")).toBe("Who will be confirmed as Fed Chair");
  });

  test("familyShownIds collects headline + member ids (for flat-list dedup)", () => {
    const fam = {
      family_key: "entity:lebron james",
      label: "Lebron James",
      headline: mkMarket({ id: 10 }),
      members: [mkMarket({ id: 11 }), mkMarket({ id: 12 })],
      more_count: 3,
      member_count: 6,
    } as any;
    const ids = familyShownIds([fam]);
    expect([...ids].sort()).toEqual([10, 11, 12]);
  });
});

// #4136: two rows in one card that read the same and answer differently.
describe("familyRowTitles (#4136)", () => {
  /** What a reader actually sees: the head is what CSS may cut, the tail never
   *  is. Anything past the visible budget in the head is simply not there. */
  const visible = (t: { head: string; tail: string }) =>
    t.head.slice(0, FAMILY_ROW_VISIBLE_CHARS) + t.tail;

  // The production specimen, verbatim from GET /api/events/search?q=yank
  // (api.bainluck.com, master 81db1afb, 2026-09-09).
  const YANK = [
    "M15 Hurghada: Mayank Sharma vs Luis Klaus",
    "Istanbul 3: Timofey Skatov vs Yanki Erel",
    "Istanbul 3: Yanki Erel vs Radu Albot",
    "Colorado Rockies vs. New York Yankees - First 5 Innings Winner",
    "Colorado Rockies vs. New York Yankees - 9th Inning Winner",
  ];

  test("the filed defect: no two rows of the live `yank` card render the same text", () => {
    const seen = YANK.map((n, i) => visible(familyRowTitles(YANK)[i]));
    expect(new Set(seen).size).toBe(YANK.length);
  });

  test("the two Rockies rows keep the words that tell them apart", () => {
    const t = familyRowTitles(YANK);
    expect(t[3].tail).toBe("First 5 Innings Winner");
    expect(t[4].tail).toBe("9th Inning Winner");
    // and the shared run is what became elidable, in full
    expect(t[3].head).toBe("Colorado Rockies vs. New York Yankees - ");
    expect(t[4].head).toBe("Colorado Rockies vs. New York Yankees - ");
  });

  test("rows that diverge EARLY are left completely alone", () => {
    // `Istanbul 3: ` is 12 shared characters — inside what a row shows, so these
    // two need no help. A separator-keyed rule would have split them for nothing.
    const t = familyRowTitles(YANK);
    expect(t[1]).toEqual({ head: YANK[1], tail: "" });
    expect(t[2]).toEqual({ head: YANK[2], tail: "" });
    // and a row with no sibling at all
    expect(t[0]).toEqual({ head: YANK[0], tail: "" });
  });

  test("a single-row card is never split", () => {
    expect(familyRowTitles([YANK[3]])).toEqual([{ head: YANK[3], tail: "" }]);
  });

  test("a tail too long to reserve is refused rather than eating the row", () => {
    // Shares exactly the 40-char matchup, then diverges immediately into a
    // 46-char suffix. Reserving that would push the matchup off the row —
    // trading one unreadable row for another — so it is refused.
    const long = [
      "Colorado Rockies vs. New York Yankees - Winner Of The Ninth Inning By Any Margin At All",
      "Colorado Rockies vs. New York Yankees - Loser Of The Ninth Inning By Any Margin At All",
    ];
    for (const t of familyRowTitles(long)) expect(t.tail).toBe("");
  });

  test("a reserved tail never starts mid-word", () => {
    // Shared run ends inside "Winner"; the snap must fall back to the space.
    const mid = [
      "Colorado Rockies vs. New York Yankees - Winner A",
      "Colorado Rockies vs. New York Yankees - Winner B",
    ];
    for (const t of familyRowTitles(mid)) {
      expect(t.tail).toMatch(/^Winner [AB]$/);
      expect(t.head.endsWith(" ")).toBe(true);
    }
  });

  test("identical names produce no split (nothing distinguishes them)", () => {
    const same = ["Colorado Rockies vs. New York Yankees", "Colorado Rockies vs. New York Yankees"];
    for (const t of familyRowTitles(same)) expect(t.tail).toBe("");
  });

  test("head + tail always reconstruct the cleaned name — no bytes invented or lost", () => {
    for (const names of [YANK, ["A", "B"], []]) {
      familyRowTitles(names).forEach((t, i) => {
        expect(t.head + t.tail).toBe(cleanName(names[i]));
      });
    }
  });

  test("cleanName still applies through the split", () => {
    const years = [
      "Colorado Rockies vs. New York Yankees - First 5 Innings Winner 2026",
      "Colorado Rockies vs. New York Yankees - 9th Inning Winner 2026",
    ];
    const t = familyRowTitles(years);
    expect(t[0].head + t[0].tail).not.toMatch(/2026/);
    expect(t[1].tail).toBe("9th Inning Winner");
  });
});

// #4583: five rows that all repeated one matchup, each showing one letter of it.
describe("familySharedHead (#4583)", () => {
  // Verbatim from GET /api/events/search?q=yank (api.bainluck.com, 2026-09-09),
  // `futures_families[0]`: headline first, then members in served order. This is
  // the whole card — every row of it — which is what makes it the right specimen
  // for a question that is a property of the SET.
  const YANK_CARD = [
    "Colorado Rockies vs. New York Yankees - 8th Inning Winner",
    "Colorado Rockies vs. New York Yankees - 7th Inning Winner",
    "Colorado Rockies vs. New York Yankees - 9th Inning Winner",
    "Colorado Rockies vs. New York Yankees - 6th Inning Winner",
    "Colorado Rockies vs. New York Yankees - 3rd Inning Winner",
  ];

  test("the filed defect: the matchup is lifted out of the five rows that repeat it", () => {
    expect(familySharedHead(familyRowTitles(YANK_CARD))).toBe(
      "Colorado Rockies vs. New York Yankees",
    );
  });

  test("the trailing join characters do not survive onto a line of their own", () => {
    // The head is `… Yankees - `; on its own line there is nothing to its right
    // for the dash to join it to.
    const s = familySharedHead(familyRowTitles(YANK_CARD))!;
    expect(s.endsWith("-")).toBe(false);
    expect(s).toBe(s.trim());
  });

  test("🔴 THE CLASS: a card that reserves the same tail on every row must hoist", () => {
    // This is the assertion that was missing, and it is worth stating as a rule
    // rather than as five expected strings. When every row of a card reserves a
    // tail AND every head is the same bytes, the matchup exists on the page ONLY
    // inside a head that CSS is explicitly entitled to delete (`shrink-[9999]`)
    // — and at 390px it did delete it, down to `C`. So for any such card the
    // hoist must fire; a null here means the matchup is unreachable on a phone.
    const titles = familyRowTitles(YANK_CARD);
    const everyRowReservesATail = titles.every((t) => t.tail !== "");
    const everyHeadIdentical = new Set(titles.map((t) => t.head)).size === 1;
    expect(everyRowReservesATail && everyHeadIdentical).toBe(true);
    expect(familySharedHead(titles)).not.toBeNull();
  });

  test("what each row shows after the hoist still tells the rows apart", () => {
    // Post-hoist a row renders its tail alone, with the full width of the row.
    const titles = familyRowTitles(YANK_CARD);
    const shown = titles.map((t) => t.tail);
    expect(shown).toEqual([
      "8th Inning Winner",
      "7th Inning Winner",
      "9th Inning Winner",
      "6th Inning Winner",
      "3rd Inning Winner",
    ]);
    expect(new Set(shown).size).toBe(YANK_CARD.length);
  });

  test("no bytes are invented: the subject is a real prefix of every row's name", () => {
    const subject = familySharedHead(familyRowTitles(YANK_CARD))!;
    for (const name of YANK_CARD) expect(cleanName(name).startsWith(subject)).toBe(true);
  });

  test("the #4136 specimen is left completely alone — mixed cards do not hoist", () => {
    // The original filed card: two Rockies rows among three tennis rows. The
    // tennis rows diverge early and reserve no tail, so there is no one subject
    // and lifting the Rockies matchup would put a header on a card most of whose
    // rows are not about it.
    const MIXED = [
      "M15 Hurghada: Mayank Sharma vs Luis Klaus",
      "Istanbul 3: Timofey Skatov vs Yanki Erel",
      "Istanbul 3: Yanki Erel vs Radu Albot",
      "Colorado Rockies vs. New York Yankees - First 5 Innings Winner",
      "Colorado Rockies vs. New York Yankees - 9th Inning Winner",
    ];
    expect(familySharedHead(familyRowTitles(MIXED))).toBeNull();
  });

  test("heads that differ are per-row information and are never hoisted", () => {
    // Two matchups, two rows each: every row reserves a tail, but the heads are
    // not the same bytes, so a single header would be a lie about half the card.
    const TWO = [
      "Colorado Rockies vs. New York Yankees - 8th Inning Winner",
      "Colorado Rockies vs. New York Yankees - 9th Inning Winner",
      "Los Angeles Dodgers vs. Cincinnati Reds - 8th Inning Winner",
      "Los Angeles Dodgers vs. Cincinnati Reds - 9th Inning Winner",
    ];
    const titles = familyRowTitles(TWO);
    expect(titles.every((t) => t.tail !== "")).toBe(true); // all split...
    expect(familySharedHead(titles)).toBeNull(); // ...but not all the same
  });

  test("a single-row card has no shared subject to lift", () => {
    expect(familySharedHead(familyRowTitles([YANK_CARD[0]]))).toBeNull();
    expect(familySharedHead([])).toBeNull();
  });

  test("a head that is only separators never becomes a header", () => {
    expect(familySharedHead([{ head: " - ", tail: "A" }, { head: " - ", tail: "B" }])).toBeNull();
  });

  test("an unsplit row among identical heads blocks the hoist — its name would vanish", () => {
    // Found by mutation: dropping the every-row-has-a-tail check failed nothing,
    // because `familyRowTitles` cannot currently produce identical heads with an
    // empty tail among them — the heads-differ check always fires first. The
    // check is still the one that holds the contract of THIS function, which is
    // exported and takes the pair shape from any caller: a row with no tail
    // renders its head as its whole title, so hoisting that head into the card
    // header would leave that row displaying nothing at all.
    expect(
      familySharedHead([
        { head: "Rockies vs. Yankees - ", tail: "9th Inning Winner" },
        { head: "Rockies vs. Yankees - ", tail: "" },
      ]),
    ).toBeNull();
  });
});
