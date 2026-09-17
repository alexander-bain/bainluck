// #4568, second half — "ALL OUTCOMES appears sorted ascending by probability …
// so on a 'when will X happen' ladder the most likely answer sits at the bottom
// … flagging it in case it is unintentional."
//
// The ascending sort is intentional and stays (a cumulative ladder's prices ARE
// its order). The defect the filing found is one layer down: HALF the rungs are
// tied, and a tie fell back on serve order, which on these markets is scrambled.
//
// THE MEASURED DEFECT (production payloads, 2026-09-17, both captured verbatim
// below). `/futures/108559` serves 22 rungs of which ELEVEN are priced at 1%;
// `/futures/108555` serves 22 of which NINE are at 1% and FIVE are priceless.
// Rendered top-to-bottom, 108559's tied block read:
//
//     Jan 26 · Oct 25 · Apr 26 · Feb 26 · Mar 26 · May 26 · Jul 26 · Aug 26 ·
//     Sep 26 · Oct 26 · Jun 26
//
// Neither serve order NOR outcome id is chronological here (ids 1593130 = Oct 25
// sits after 1593131 = Jan 26), so both available "leave it alone" answers give
// the reader a scrambled timeline.
//
// What these tests pin, in order of how much they would hurt to lose:
//   1. tied rungs come out chronological on BOTH filed specimens;
//   2. rungs that are NOT tied are untouched — the price still decides, so the
//      incoherent quotes on 108559 stay visible instead of being sorted away;
//   3. the three refusals (a label that does not parse, a forward-looking
//      ladder, a mutually-exclusive market) each put serve order back;
//   4. the tie-break can never be reading outcome id.

import { buildOutcomeLadderRungs, parseLadderDate } from "@/lib/futuresLadder";

type Row = { id: number; name: string; probability: number | null };

// `GET /api/futures/108559`, 2026-09-17 21:0xZ, verbatim and in serve order.
const OPENAI_108559: Row[] = [
  { id: 1593120, name: "Before Jun 1, 2027", probability: 0.685 },
  { id: 1593121, name: "Before May 1, 2027", probability: 0.585 },
  { id: 1593122, name: "Before Apr 1, 2027", probability: 0.455 },
  { id: 1593123, name: "Before Mar 1, 2027", probability: 0.405 },
  { id: 1593124, name: "Before Feb 1, 2027", probability: 0.18 },
  { id: 1593125, name: "Before Jan 1, 2027", probability: 0.085 },
  { id: 1593126, name: "Before Dec 1, 2026", probability: 0.055 },
  { id: 1593133, name: "Before Nov 1, 2026", probability: 0.03 },
  { id: 1593128, name: "Before Dec 1, 2025", probability: 0.02 },
  { id: 1593131, name: "Before Jan 1, 2026", probability: 0.01 },
  { id: 1593130, name: "Before Oct 1, 2025", probability: 0.01 },
  { id: 1593140, name: "Before Apr 1, 2026", probability: 0.01 },
  { id: 1593132, name: "Before Feb 1, 2026", probability: 0.01 },
  { id: 1593141, name: "Before Mar 1, 2026", probability: 0.01 },
  { id: 1593138, name: "Before May 1, 2026", probability: 0.01 },
  { id: 1593137, name: "Before Jul 1, 2026", probability: 0.01 },
  { id: 1593136, name: "Before Aug 1, 2026", probability: 0.01 },
  { id: 1593135, name: "Before Sep 1, 2026", probability: 0.01 },
  { id: 1593134, name: "Before Oct 1, 2026", probability: 0.01 },
  { id: 1593139, name: "Before Jun 1, 2026", probability: 0.01 },
  { id: 1593127, name: "Before Nov 1, 2025", probability: null },
  { id: 1593129, name: "Before Sep 1, 2025", probability: null },
];

// `GET /api/futures/108555`, same minute. The filing's "five such legs" market.
const STARLINK_108555: Row[] = [
  { id: 1593038, name: "Before Jun 30, 2027", probability: 0.06 },
  { id: 1593040, name: "Before Apr 1, 2027", probability: 0.05 },
  { id: 1593041, name: "Before May 1, 2027", probability: 0.045 },
  { id: 1593044, name: "Before Feb 1, 2027", probability: 0.035 },
  { id: 1593039, name: "Before Mar 1, 2027", probability: 0.035 },
  { id: 1593045, name: "Before Jan 1, 2027", probability: 0.03 },
  { id: 1593037, name: "Before Feb 1, 2026", probability: 0.02 },
  { id: 1593046, name: "Before Dec 1, 2026", probability: 0.02 },
  { id: 1593052, name: "Before May 1, 2026", probability: 0.01 },
  { id: 1593051, name: "Before Apr 1, 2026", probability: 0.01 },
  { id: 1593048, name: "Before Nov 1, 2026", probability: 0.01 },
  { id: 1593049, name: "Before Sep 1, 2026", probability: 0.01 },
  { id: 1593043, name: "Before Oct 1, 2026", probability: 0.01 },
  { id: 1593053, name: "Before Mar 1, 2026", probability: 0.01 },
  { id: 1593047, name: "Before Jul 1, 2026", probability: 0.01 },
  { id: 1593042, name: "Before Aug 1, 2026", probability: 0.01 },
  { id: 1593050, name: "Before Jun 1, 2026", probability: 0.01 },
  { id: 1593034, name: "Before Nov 1, 2025", probability: null },
  { id: 1593033, name: "Before Sep 1, 2025", probability: null },
  { id: 1593035, name: "Before Dec 1, 2025", probability: null },
  { id: 1593032, name: "Before Oct 1, 2025", probability: null },
  { id: 1593036, name: "Before Jan 1, 2026", probability: null },
];

const labelsOf = (rows: Row[]) =>
  buildOutcomeLadderRungs(rows, "cumulative").map((r) => r.label);

/** The rungs of one price, in rendered order. */
function tiedBlock(rows: Row[], price: number | null): string[] {
  const tied = new Set(rows.filter((r) => r.probability === price).map((r) => r.name));
  return labelsOf(rows).filter((l) => tied.has(l));
}

describe("#4568 — a tied date ladder reads as a timeline (the filed specimens)", () => {
  test("108559: the eleven 1% rungs come out chronological, not scrambled", () => {
    // What production rendered before this change, verbatim from the payload's
    // serve order. Kept as the BEFORE so the assertion below cannot be read as
    // "some order came out".
    const before = OPENAI_108559.filter((r) => r.probability === 0.01).map((r) => r.name);
    expect(before).toEqual([
      "Before Jan 1, 2026",
      "Before Oct 1, 2025",
      "Before Apr 1, 2026",
      "Before Feb 1, 2026",
      "Before Mar 1, 2026",
      "Before May 1, 2026",
      "Before Jul 1, 2026",
      "Before Aug 1, 2026",
      "Before Sep 1, 2026",
      "Before Oct 1, 2026",
      "Before Jun 1, 2026",
    ]);

    expect(tiedBlock(OPENAI_108559, 0.01)).toEqual([
      "Before Oct 1, 2025",
      "Before Jan 1, 2026",
      "Before Feb 1, 2026",
      "Before Mar 1, 2026",
      "Before Apr 1, 2026",
      "Before May 1, 2026",
      "Before Jun 1, 2026",
      "Before Jul 1, 2026",
      "Before Aug 1, 2026",
      "Before Sep 1, 2026",
      "Before Oct 1, 2026",
    ]);
  });

  test("108555: nine tied rungs AND five priceless ones each read chronologically", () => {
    expect(tiedBlock(STARLINK_108555, 0.01)).toEqual([
      "Before Mar 1, 2026",
      "Before Apr 1, 2026",
      "Before May 1, 2026",
      "Before Jun 1, 2026",
      "Before Jul 1, 2026",
      "Before Aug 1, 2026",
      "Before Sep 1, 2026",
      "Before Oct 1, 2026",
      "Before Nov 1, 2026",
    ]);
    // The priceless legs #4253 withdrew all tie at +Infinity, so they were
    // scrambled too — and they are the rows #4568 is named for.
    expect(tiedBlock(STARLINK_108555, null)).toEqual([
      "Before Sep 1, 2025",
      "Before Oct 1, 2025",
      "Before Nov 1, 2025",
      "Before Dec 1, 2025",
      "Before Jan 1, 2026",
    ]);
    // "Before Jun 30, 2027" — the day is not always 1, and the parse must not
    // quietly drop it.
    expect(parseLadderDate("Before Jun 30, 2027")).toEqual({ year: 2027, month: 6, day: 30 });
  });

  test("🔴 a rung whose price DIFFERS is never moved — the price still decides", () => {
    // This is the scope assertion, and it is the one that would be lost by
    // "just sort the ladder by date". 108559 prices "Before Dec 1, 2025" at 2%
    // ABOVE "Before Oct 1, 2026" at 1%, which is an arbitrage violation: the
    // earlier window nests inside the later one. That is a data defect for
    // another lane to see, and sorting it away would hide it.
    const labels = labelsOf(OPENAI_108559);
    expect(labels.indexOf("Before Oct 1, 2026")).toBeLessThan(
      labels.indexOf("Before Dec 1, 2025"),
    );
    // And the whole priced spine keeps the exact order the prices give it.
    const priced = OPENAI_108559.filter(
      (r) => r.probability !== null && r.probability > 0.01,
    ).map((r) => r.name);
    expect(labels.filter((l) => priced.includes(l))).toEqual([...priced].reverse());
  });

  test("🔴 the tie-break cannot be reading outcome id", () => {
    // Serve order and id order disagree with each other AND with the calendar on
    // this block, so a mutant that sorts ties by id fails here even though it
    // "reorders the ties". Ascending id would put Jan 2026 (1593131) above
    // Oct 2025 (1593130) — the defect, restored.
    const tied = OPENAI_108559.filter((r) => r.probability === 0.01);
    const byId = [...tied].sort((a, b) => a.id - b.id).map((r) => r.name);
    expect(byId[0]).toBe("Before Oct 1, 2025"); // id ASC starts right...
    expect(byId[1]).toBe("Before Jan 1, 2026"); // ...and then is wrong: Apr 2026 is next
    expect(tiedBlock(OPENAI_108559, 0.01)[2]).toBe("Before Feb 1, 2026");
    expect(byId[2]).toBe("Before Feb 1, 2026");
    // The two agree for three rows and part company at the fourth.
    expect(byId.slice(3)).not.toEqual(tiedBlock(OPENAI_108559, 0.01).slice(3));
  });
});

describe("#4568 — the three refusals put serve order back", () => {
  test("one unparseable label refuses the WHOLE ladder (all-or-nothing)", () => {
    // A timeline with three rungs placed and one guessed reads as authoritative
    // and is not — the backend parser's own rule, mirrored.
    const rows: Row[] = [
      { id: 1, name: "Before Oct 1, 2026", probability: 0.01 },
      { id: 2, name: "Some other answer", probability: 0.01 },
      { id: 3, name: "Before Jan 1, 2026", probability: 0.01 },
    ];
    expect(labelsOf(rows)).toEqual([
      "Before Oct 1, 2026",
      "Some other answer",
      "Before Jan 1, 2026",
    ]);
  });

  test("a forward-looking ladder refuses — ascending date would be backwards", () => {
    // On "after"/"or later" rungs a LATER date is a SMALLER probability, so the
    // chronological tie-break points the wrong way. We do not reverse it; we
    // leave the ladder alone.
    const later: Row[] = [
      { id: 1, name: "2029 or later", probability: 0.05 },
      { id: 2, name: "2027 or later", probability: 0.05 },
    ];
    expect(labelsOf(later)).toEqual(["2029 or later", "2027 or later"]);
    const after: Row[] = [
      { id: 1, name: "After June 2026", probability: 0.05 },
      { id: 2, name: "After March 2026", probability: 0.05 },
    ];
    expect(labelsOf(after)).toEqual(["After June 2026", "After March 2026"]);
  });

  test("a mutually-exclusive market is never reordered at all", () => {
    // `served` is the whole ladder's order, and disjoint date bins carry no
    // probability ordering. The tie-break must not sneak in under it.
    const bins: Row[] = [
      { id: 1, name: "Before Oct 1, 2026", probability: 0.4 },
      { id: 2, name: "Before Jan 1, 2026", probability: 0.4 },
    ];
    expect(
      buildOutcomeLadderRungs(bins, "served").map((r) => r.label),
    ).toEqual(["Before Oct 1, 2026", "Before Jan 1, 2026"]);
  });
});

describe("#4568 — parseLadderDate mirrors the backend grammar", () => {
  test("the four shapes the house parser accepts, plus the day this one adds", () => {
    expect(parseLadderDate("Before October")).toEqual({ year: null, month: 10, day: 1 });
    expect(parseLadderDate("Before 2027")).toEqual({ year: 2027, month: 1, day: 1 });
    expect(parseLadderDate("March 2027")).toEqual({ year: 2027, month: 3, day: 1 });
    expect(parseLadderDate("2029 or later")).toEqual({ year: 2029, month: 1, day: 1 });
    // The one deliberate difference from `_parse_date_bucket`: every Kalshi IPO
    // rung carries a day, which the Python grammar rejects outright.
    expect(parseLadderDate("Before Jun 1, 2027")).toEqual({ year: 2027, month: 6, day: 1 });
    expect(parseLadderDate("Before Sept 9, 2025")).toEqual({ year: 2025, month: 9, day: 9 });
  });

  test("the refusals are the load-bearing half", () => {
    // A lone month is a label, not a cutoff — the Python requires the framing too.
    expect(parseLadderDate("October")).toBeNull();
    expect(parseLadderDate("≥ 80")).toBeNull();
    expect(parseLadderDate("Scottie Scheffler")).toBeNull();
    expect(parseLadderDate("Before Jun 32, 2027")).toBeNull();
    expect(parseLadderDate("Before 1800")).toBeNull();
    expect(parseLadderDate("Before Smarch 2027")).toBeNull();
    expect(parseLadderDate("")).toBeNull();
    expect(parseLadderDate(null)).toBeNull();
  });

  test("a bare-month ladder anchors to the year before its earliest dated rung", () => {
    // 109435 ("Will the U.S. confirm that aliens exist?") mixes "Before October"
    // with "Before 2027": the months must precede the dated rung, or the ladder
    // claims October 2027 comes before January 2027.
    const aliens: Row[] = [
      { id: 1, name: "Before September", probability: 0 },
      { id: 2, name: "Before July", probability: 0 },
      { id: 3, name: "Before August", probability: 0 },
      { id: 4, name: "Before 2027", probability: 0.049 },
      { id: 5, name: "Before 2028", probability: 0.125 },
    ];
    expect(labelsOf(aliens)).toEqual([
      "Before July",
      "Before August",
      "Before September",
      "Before 2027",
      "Before 2028",
    ]);
  });

  test("two tied rungs in the SAME month are ordered by their day", () => {
    // 108555 serves "Before Jun 30, 2027" beside "Before Jun 1, 2026", so the day
    // is real Kalshi vocabulary — it just happens to carry a distinct price
    // there. Constructed here because the population has no same-month TIE
    // today, and without it the sort key could drop the day and nothing would
    // notice until one arrived.
    const sameMonth: Row[] = [
      { id: 1, name: "Before Jun 30, 2027", probability: 0.01 },
      { id: 2, name: "Before Jun 1, 2027", probability: 0.01 },
    ];
    expect(labelsOf(sameMonth)).toEqual(["Before Jun 1, 2027", "Before Jun 30, 2027"]);
  });

  test("a tie that MIXES a dated rung with a bare month is where the anchor shows", () => {
    // The anchor ("a bare month means the year before the earliest dated rung")
    // is invisible while a tie group is all-months or all-dated, because it is
    // then a constant offset. It decides the order only here. Constructed: the
    // live ladders tie within one kind. Without the -1, "Before October" would
    // claim to fall after "Before 2027", which is the reading the backend parser
    // rejected for the same reason.
    const mixed: Row[] = [
      { id: 1, name: "Before 2027", probability: 0.04 },
      { id: 2, name: "Before October", probability: 0.04 },
    ];
    expect(labelsOf(mixed)).toEqual(["Before October", "Before 2027"]);
  });

  test("a ladder with no year anywhere still orders its months", () => {
    const months: Row[] = [
      { id: 1, name: "Before October", probability: 0.02 },
      { id: 2, name: "Before April", probability: 0.02 },
      { id: 3, name: "Before July", probability: 0.02 },
    ];
    expect(labelsOf(months)).toEqual([
      "Before April",
      "Before July",
      "Before October",
    ]);
  });

  test("Q478's own specimen is unchanged — April before July, still", () => {
    // 109349, the market the ladder was built for. Its 1% tie was already right
    // by luck of serve order; it must still be right by rule.
    const iphone: Row[] = [
      { id: 1596638, name: "Before 2027", probability: 0.15 },
      { id: 1596639, name: "Before October", probability: 0.065 },
      { id: 1596641, name: "Before April", probability: 0.01 },
      { id: 1596640, name: "Before July", probability: 0.01 },
    ];
    expect(labelsOf(iphone)).toEqual([
      "Before April",
      "Before July",
      "Before October",
      "Before 2027",
    ]);
  });
});
