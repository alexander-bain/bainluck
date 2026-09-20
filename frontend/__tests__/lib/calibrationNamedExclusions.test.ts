/**
 * #7353 — the exclusion rules the accuracy page publishes but never named.
 *
 * The defect was an absence, so this suite is built around the two ways an
 * absence-guard lies: it can pass because the predicate never fired, and it can
 * pass on a fixture that could not have contained the defect. Both are answered
 * with positive controls that run the SAME function over payloads that must
 * produce the opposite answer.
 *
 * THE FIXTURE IS THE LIVE PAYLOAD'S BLOCKS, NOT A SKETCH. Every count and every
 * shape below was read from `https://api.bainluck.com/api/calibration` on
 * 2026-09-20 ~03:00Z — with one deliberate exception, `identity_quarantine_
 * filter`, which that response does not contain and which is the subject of
 * #7627; see its own note in `ALREADY_BULLETED`. That matters twice over:
 *
 *   - `heuristic_filter` publishes NO flat `excluded` field — only
 *     `excluded_by_source` — and it is the LARGEST of the nine at 66,921. A
 *     module that reads `excluded` alone drops the biggest rule it exists to
 *     surface, and a hand-written fixture that gave every block an `excluded`
 *     would never have noticed. It is the one shape this suite would have got
 *     wrong by guessing.
 *   - `orphan_partition_filter` is a real, measured ZERO. "Fired zero times" and
 *     "not measured" are different answers and the fixture carries the first.
 */

import { readFileSync } from "fs";
import { join } from "path";

import {
  readNamedExclusions,
  NAMED_EXCLUSION_LABELS,
  EXCLUSIONS_WITH_THEIR_OWN_BULLET,
} from "@/lib/calibrationNamedExclusions";

/**
 * #7627 — the payload builder's own source, which is the only honest answer to
 * "which `*_filter` blocks exist".
 *
 * Reading the SERVED payload instead is what put this suite one block short for
 * five days: `precompute_calibration_main` is a HEAVY_TASK and `bainluck-heavy`
 * runs behind master (notice 48), so `api.bainluck.com/api/calibration` is a
 * lagging view of this file and a key master grew on the 14th was still absent
 * from the response on the 20th.
 *
 * Deliberately NOT guarded with a try/catch or a conditional skip: a missing
 * backend file must turn this suite red and say which path it wanted, because
 * the failure a soft read produces is a green closure test over an empty
 * universe — the same fail-open this test exists to close. Precedent for a jest
 * test reading backend source: `__tests__/ios/conceptAdmissionParity.test.ts`.
 */
const PAYLOAD_BUILDER = join(
  __dirname, "..", "..", "..", "backend", "app", "tasks", "precompute_calibration.py"
);

function readBackendPayloadSource(): string {
  return readFileSync(PAYLOAD_BUILDER, "utf8");
}

/**
 * Every `*_filter` key the payload dict literal declares.
 *
 * Anchored to the eight-space indent of `response = {`'s own members, so a
 * `relation_to_liquidity_filter` string nested one level deeper is not mistaken
 * for a block. The character class INCLUDES DIGITS — without them the pattern
 * silently drops `soccer_2way_filter`, which is the sort of near-miss that makes
 * a completeness check read complete.
 */
function backendFilterKeys(): string[] {
  const src = readBackendPayloadSource();
  const found = [...src.matchAll(/^ {8}"([a-z0-9_]+_filter)":/gm)].map(m => m[1]);
  return [...new Set(found)].sort();
}

/** The six that already have their own sentence on the page, with live counts. */
const ALREADY_BULLETED = {
  liquidity_filter: { applies_to: "kalshi", rule: "…yes_bid > 0…", kalshi_included: 632_525, kalshi_excluded: 43_235 },
  writer_bar_filter: { applies_to: "kalshi", rule: "…", included: 473_290, excluded: 202_470 },
  esports_multi_bundle_filter: { applies_to: "all", rule: "…", excluded: 187_263 },
  soccer_2way_filter: { applies_to: "soccer", rule: "…Soccer h2h is 3-way…", excluded: 67_915 },
  void_filter: { applies_to: "golf", rule: "…did_not_play / withdrew…", excluded: 16_269 },
  nonexclusive_bundle_filter: { applies_to: "all", rule: "…", excluded: 203_906 },
  // #7627 — the seventh, and the ONLY block here whose count is not a live
  // reading, because there is no live reading to take: the served payload has
  // never carried this block (`bainluck-heavy` is behind master, notice 48),
  // which is precisely how it went missing from the map. The shape is
  // transcribed from `precompute_calibration.py`'s `identity_quarantine_filter`
  // literal; the count is a stand-in and NOTHING asserts its magnitude —
  // `identity_quarantine_filter is skipped at any count` runs the same payload
  // at zero and non-zero so a future real number cannot change an answer here.
  identity_quarantine_filter: {
    applies_to: "all",
    rule: "…identity-disputed rows held out pending review…",
    excluded: 1_234,
    excluded_markets: 56,
    excluded_cells: [["kalshi", "politics"]],
  },
};

/** The nine that were named nowhere in `frontend/` before this change. */
const THE_NINE = {
  heuristic_filter: {
    applies_to: "polymarket",
    rule: "Outcomes resolved by legacy heuristic passes (pass2_guess, pass2_loser, all_losers)…",
    excluded_by_source: { kalshi: 22_480, polymarket: 44_441 },
  },
  kalshi_prop_threshold_filter: {
    applies_to: "kalshi",
    rule: "Excludes the corrupt slice of Kalshi player-prop threshold outcomes… llm_sport_category='hockey'…",
    excluded: 45_102,
  },
  poly_placeholder_filter: {
    applies_to: "polymarket",
    rule: "Excludes Polymarket outcomes near 0.50 (cp in [0.45, 0.55]) that never showed a real bid…",
    excluded: 19_697,
    included: 411_705,
  },
  no_winner_filter: {
    applies_to: "all",
    rule: "…is_winner has a False default…",
    excluded: 12_237,
    excluded_markets: 1_653,
  },
  draw_authority_filter: {
    applies_to: "cricket, soccer",
    rule: "…#1011: 7-18pp over-prediction…",
    excluded: 1_805,
    excluded_markets: 967,
  },
  golf_placeholder_filter: {
    applies_to: "golf",
    rule: "…mex probabilities can't have two 80%+ outcomes…",
    excluded: 1_707,
  },
  malformed_binary_filter: {
    applies_to: "all",
    rule: "…",
    excluded: 158,
    both_false_excluded: 154,
    both_winner_excluded: 4,
  },
  weather_wide_spread_filter: {
    applies_to: "kalshi (weather only)",
    rule: "…yes_ask - yes_bid >= 0.50…",
    excluded: 94,
  },
  orphan_partition_filter: {
    applies_to: "all (field shape only)",
    rule: "…",
    excluded: 0,
    excluded_markets: 0,
  },
};

/** The payload, near enough: the sixteen filter blocks plus noise around them. */
const LIVE = {
  total_outcomes: 747_028,
  exclusion_symmetry: { poly_never_traded_in_curve: 19_805 },
  ...ALREADY_BULLETED,
  ...THE_NINE,
};

/** Live counts, largest first — this file's expectation, not the module's output. */
const EXPECTED_ORDER: ReadonlyArray<readonly [string, number]> = [
  ["heuristic_filter", 66_921],
  ["kalshi_prop_threshold_filter", 45_102],
  ["poly_placeholder_filter", 19_697],
  ["no_winner_filter", 12_237],
  ["draw_authority_filter", 1_805],
  ["golf_placeholder_filter", 1_707],
  ["malformed_binary_filter", 158],
  ["weather_wide_spread_filter", 94],
];

describe("the live payload's nine unnamed rules", () => {
  test("every one of the eight non-zero rules becomes a row, largest first", () => {
    const out = readNamedExclusions(LIVE);
    expect(out).not.toBeNull();
    expect(out!.rows.map(r => [r.key, r.outcomes])).toEqual(
      EXPECTED_ORDER.map(([k, n]) => [k, n])
    );
  });

  test("the measured zero is a checked zero, not a row and not a silence", () => {
    const out = readNamedExclusions(LIVE)!;
    expect(out.rows.some(r => r.key === "orphan_partition_filter")).toBe(false);
    expect(out.emptyRules).toBe(1);
    expect(out.unlistedRules).toBe(0);
  });

  test("the largest rule publishes no flat count and is summed from its sources", () => {
    // The shape trap, asserted as a shape: if `heuristic_filter` ever grows an
    // `excluded` field this test still passes, but the fixture proves the module
    // works on the payload as it is TODAY, where the field does not exist.
    expect("excluded" in THE_NINE.heuristic_filter).toBe(false);
    const row = readNamedExclusions(LIVE)!.rows.find(r => r.key === "heuristic_filter");
    expect(row!.outcomes).toBe(22_480 + 44_441);
    // …and it is the biggest one, so reading `excluded` alone loses the most.
    expect(readNamedExclusions(LIVE)!.rows[0].key).toBe("heuristic_filter");
  });

  test("four of them are bigger than a rule the page already spells out in full", () => {
    // The reason this is a defect rather than housekeeping: the silence was not
    // about small rules. If a future payload makes that false, the claim in the
    // issue and the PR is no longer true and someone should reread it.
    const voidExcluded = ALREADY_BULLETED.void_filter.excluded;
    const bigger = EXPECTED_ORDER.filter(([, n]) => n > voidExcluded);
    expect(bigger.map(([k]) => k)).toEqual([
      "heuristic_filter",
      "kalshi_prop_threshold_filter",
      "poly_placeholder_filter",
    ]);
    expect(EXPECTED_ORDER[0][1]).toBeGreaterThan(ALREADY_BULLETED.liquidity_filter.kalshi_excluded);
  });
});

describe("it never prints a count that already has its own bullet", () => {
  test.each([...EXCLUSIONS_WITH_THEIR_OWN_BULLET])("%s is not a row", key => {
    const out = readNamedExclusions(LIVE)!;
    expect(out.rows.some(r => r.key === key)).toBe(false);
  });

  test("identity_quarantine_filter is skipped at any count, and never counted as unnamed", () => {
    // #7627. This one is skipped because the page prints it in full in its own
    // "Held out, under review" section — so the assertion that matters is that
    // the answer does not depend on the number, which the fixture cannot supply
    // honestly. Both ends, plus the middle:
    for (const excluded of [0, 1, 1_234, 500_000]) {
      const out = readNamedExclusions({
        ...LIVE,
        identity_quarantine_filter: { applies_to: "all", rule: "…", excluded },
      })!;
      expect(out.rows.some(r => r.key === "identity_quarantine_filter")).toBe(false);
      expect(out.unlistedRules).toBe(0);
      // Not a folded row AND not a "further rule that set aside nothing":
      // the section below the fold is where a reader is told either way, so
      // crediting a checked zero here would be the double-naming again.
      expect(out.emptyRules).toBe(1); // orphan_partition_filter, and only it
    }
  });

  test("the skip above would be a silent drop if it were not for the count it shares", () => {
    // The whole argument for own-bullet status is that the section which DOES
    // print this count renders on exactly the same condition. In the payload
    // builder both read one variable: `identity_quarantine_filter.excluded` is
    // `identity_disputed_excluded`, and `quarantine` is a row when that same
    // name is `> 0`. If those two ever come apart, a non-zero quarantine can
    // render nothing anywhere and the skip becomes the silent drop Alex's
    // #6275/#1902 ruling is against — so this is pinned at the source rather
    // than argued in a comment.
    const src = readBackendPayloadSource();

    // `indexOf` returns -1 on a miss and `slice(-1)` would hand the assertions a
    // one-character string that fails for the wrong reason, so each offset is
    // checked before it is used. A generous fixed window, not a brace matcher:
    // this is a coupling check, not a parser.
    const quarantineAt = src.indexOf('"quarantine": (');
    expect(quarantineAt).toBeGreaterThan(-1);
    const quarantineBlock = src.slice(quarantineAt, quarantineAt + 1_200);
    expect(quarantineBlock).toContain('"outcomes": identity_disputed_excluded');
    expect(quarantineBlock).toContain("if identity_disputed_excluded > 0");

    const filterAt = src.indexOf('"identity_quarantine_filter": {');
    expect(filterAt).toBeGreaterThan(-1);
    const filterBlock = src.slice(filterAt, filterAt + 2_000);
    expect(filterBlock).toContain('"excluded": identity_disputed_excluded');
  });

  test("and the exclusion is by NAME, not by accident of having no label", () => {
    // Positive control for the skip: every bulleted filter is present in the
    // fixture with a large, readable count, so the only thing keeping them out
    // is the set. Were the skip deleted, they would become rows — not be
    // counted as unlistable — and `unlistedRules` would stay 0 either way.
    const out = readNamedExclusions(LIVE)!;
    expect(out.unlistedRules).toBe(0);
    for (const key of EXCLUSIONS_WITH_THEIR_OWN_BULLET) {
      expect(NAMED_EXCLUSION_LABELS[key]).toBeUndefined();
      expect(LIVE).toHaveProperty(key);
    }
  });
});

describe("a rule the module cannot name is counted, never rendered and never dropped", () => {
  test("an unknown *_filter lands in unlistedRules", () => {
    const out = readNamedExclusions({
      ...LIVE,
      some_new_filter: { applies_to: "all", rule: "…", excluded: 5_000 },
    })!;
    expect(out.rows.some(r => r.key === "some_new_filter")).toBe(false);
    expect(out.unlistedRules).toBe(1);
    expect(out.rows).toHaveLength(EXPECTED_ORDER.length);
  });

  test("a named rule whose count is unreadable lands there too", () => {
    for (const bad of [{ excluded: "1,805" }, { excluded: -1 }, { excluded: 1.5 }, {}]) {
      const out = readNamedExclusions({
        ...LIVE,
        draw_authority_filter: { applies_to: "soccer", rule: "…", ...bad },
      })!;
      expect(out.rows.some(r => r.key === "draw_authority_filter")).toBe(false);
      expect(out.unlistedRules).toBe(1);
    }
  });

  test("a per-source breakdown with a bad member is not half-summed", () => {
    const out = readNamedExclusions({
      ...LIVE,
      heuristic_filter: { excluded_by_source: { kalshi: 22_480, polymarket: null } },
    })!;
    expect(out.rows.some(r => r.key === "heuristic_filter")).toBe(false);
    expect(out.unlistedRules).toBe(1);
  });

  test("an absent or null block is neither a row nor an unlisted rule", () => {
    // A payload banked before a rule existed must read as "this artifact
    // predates the rule", never as a rule the page failed to name.
    const out = readNamedExclusions({ ...LIVE, weather_wide_spread_filter: null })!;
    expect(out.unlistedRules).toBe(0);
    expect(out.rows).toHaveLength(EXPECTED_ORDER.length - 1);
  });
});

describe("it renders nothing rather than an empty fold", () => {
  test.each([
    ["no payload at all", null],
    ["a non-object", 7],
    ["a payload with no filters", { total_outcomes: 10 }],
    ["only bulleted filters", ALREADY_BULLETED],
    ["every remaining rule at zero", { orphan_partition_filter: { excluded: 0 } }],
  ])("%s gives null", (_name, payload) => {
    expect(readNamedExclusions(payload)).toBeNull();
  });
});

describe("the labels are this module's words, not the payload's", () => {
  test("no label repeats any phrase from the rule string beside it", () => {
    // #4067 / CERT-2295: the failure mode is not a banned WORD, it is rendering
    // prose the page does not own. So the test is structural — no six-word run
    // of a payload `rule` may appear in the label the page shows instead of it.
    for (const [key, block] of Object.entries(THE_NINE)) {
      const label = NAMED_EXCLUSION_LABELS[key];
      expect(typeof label).toBe("string");
      const words = (block as { rule: string }).rule.split(/\s+/);
      for (let i = 0; i + 6 <= words.length; i += 1) {
        expect(label).not.toContain(words.slice(i, i + 6).join(" "));
      }
    }
  });

  test("and carry none of the auditor vocabulary those rules are written in", () => {
    const AUDITOR = [
      "yes_bid", "yes_ask", "is_winner", "llm_sport_category", "cp ", "mex",
      "#", "Queue", "gotcha", "census", "pass2", "condition_id", "h2h",
    ];
    for (const label of Object.values(NAMED_EXCLUSION_LABELS)) {
      for (const token of AUDITOR) expect(label.toLowerCase()).not.toContain(token.toLowerCase());
    }
  });

  test("the predicate above can fire", () => {
    // The control: run the same two checks over a label that IS the payload's
    // prose. Both must fail, or neither test above is worth anything.
    const stolen = THE_NINE.poly_placeholder_filter.rule;
    const words = stolen.split(/\s+/);
    expect(stolen).toContain(words.slice(0, 6).join(" "));
    expect(stolen.toLowerCase()).toContain("cp ");
  });

  test("every listable rule has a label and every label is listable", () => {
    // Keeps the closed map closed: a label with no rule behind it is dead copy,
    // a rule with no label is the omission this whole issue is about.
    expect(Object.keys(NAMED_EXCLUSION_LABELS).sort()).toEqual(Object.keys(THE_NINE).sort());
  });
});

describe("the map is closed over the BACKEND, not over this file's fixture (#7627)", () => {
  // The test above closes the map against `THE_NINE`, and `THE_NINE` was
  // transcribed from the served payload — so for five days the map, the fixture
  // and the test that checked one against the other were all short the same
  // block, and agreed with each other perfectly. The universe has to come from
  // somewhere neither the map nor the fixture can be wrong about.

  test("the key scan finds a real set, not an empty one", () => {
    // Every assertion below is of the form "this set is covered", and an empty
    // set is covered by anything. A regex that stops matching — the file is
    // reformatted, the dict is renamed, the indent changes — would turn the two
    // tests after this one green while covering nothing. So the scan is checked
    // for plausibility BEFORE it is used as an authority.
    const keys = backendFilterKeys();
    expect(keys.length).toBeGreaterThanOrEqual(15);
    // Three specimens the scan must find, chosen for what each one proves:
    // a plain key, the digit-bearing key a naive `[a-z_]` class drops, and the
    // key whose absence from the served payload is this issue.
    expect(keys).toContain("heuristic_filter");
    expect(keys).toContain("soccer_2way_filter");
    expect(keys).toContain("identity_quarantine_filter");
    // …and it must not be scooping up nested members: `relation_to_liquidity_
    // filter` lives inside `writer_bar_filter` at a deeper indent and is a
    // sentence, not a block.
    expect(keys).not.toContain("relation_to_liquidity_filter");
  });

  test("every *_filter the payload builder emits is either labelled or bulleted", () => {
    const unnamed = backendFilterKeys().filter(
      key => NAMED_EXCLUSION_LABELS[key] === undefined
        && !EXCLUSIONS_WITH_THEIR_OWN_BULLET.has(key)
    );
    // Named in the message because the next person to see this red will be
    // adding a rule, and the fix is one line in one of two places.
    expect({ unnamedInFrontend: unnamed }).toEqual({ unnamedInFrontend: [] });
  });

  test("and nothing in the frontend names a rule the payload builder does not emit", () => {
    // The other direction, which the served payload could never have caught
    // either: a label left behind by a removed rule is copy for a row that can
    // never render, and the page would keep promising to explain it.
    const emitted = new Set(backendFilterKeys());
    const dead = [
      ...Object.keys(NAMED_EXCLUSION_LABELS),
      ...EXCLUSIONS_WITH_THEIR_OWN_BULLET,
    ].filter(key => !emitted.has(key)).sort();
    expect({ namedButNeverEmitted: dead }).toEqual({ namedButNeverEmitted: [] });
  });

  test("the two checks above can fail", () => {
    // Positive control. Both run over `backendFilterKeys()`, so neither can be
    // exercised by a fixture — this re-runs the same two set operations against
    // a universe with one extra member and one missing one, and requires each
    // to report it. Without this, a refactor that made either filter always
    // return [] would look like a clean bill of health forever.
    const emitted = new Set([...backendFilterKeys(), "brand_new_filter"]);
    const unnamed = [...emitted].filter(
      key => NAMED_EXCLUSION_LABELS[key] === undefined
        && !EXCLUSIONS_WITH_THEIR_OWN_BULLET.has(key)
    );
    expect(unnamed).toEqual(["brand_new_filter"]);

    const shrunk = new Set(backendFilterKeys());
    shrunk.delete("void_filter");
    const dead = [
      ...Object.keys(NAMED_EXCLUSION_LABELS),
      ...EXCLUSIONS_WITH_THEIR_OWN_BULLET,
    ].filter(key => !shrunk.has(key)).sort();
    expect(dead).toEqual(["void_filter"]);
  });
});
