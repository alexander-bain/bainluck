/**
 * #4250 — the browser and the iPhone shorten a club's name by ONE rule, so
 * their designator sets have to agree, and until this file nothing checked.
 *
 * The defect that bought this guard: `https://bainluck.com/events/15306788` at
 * 390px printed the away side as **"AFC"** beside a full-length "Manchester
 * City FC", while the API served `away_team: "Sunderland AFC"` and the iPhone
 * app rendered it correctly. `TeamShortName.swift` has listed `afc` since
 * #3374; `frontend/lib/teamShortName.ts` relied on its `length <= 2` clause,
 * which is one letter too short for a three-letter club initial. 68 distinct
 * production names end in "AFC".
 *
 * Why the existing guard could not see it: `__tests__/ios/…SingleSource.test.ts`
 * is named for single-sourcing but reads the SWIFT only — it discovers Swift
 * re-implementations and never opens the browser's module. A guard scoped to
 * one client is a guard on one client (standing notice 33's lesson, arrived at
 * independently here).
 *
 * So this file reads BOTH definitions out of source and compares them. It is
 * deliberately not a transcription: a transcribed copy of a set is a third
 * implementation, and a third implementation is the bug this guards.
 */

import { readFileSync } from "fs";
import { join } from "path";

import {
  HAND_PICKED_LABELS,
  handPickedKey,
  isNonDistinctiveTrailingWord,
  namesAPerson,
  teamCrestBadge,
  teamShortName,
  teamShortNames,
} from "@/lib/teamShortName";

const SWIFT = join(
  __dirname,
  "../../ios/Bain Luck/Bain Luck/Utilities/TeamShortName.swift",
);
const WEB = join(__dirname, "../lib/teamShortName.ts");
const SWIFT_PAIR_FIXTURES = join(
  __dirname,
  "../../ios/Bain Luck/BainLuckTests/TeamShortNamePairTests.swift",
);

/**
 * Every `"token"` inside the named bracketed literal, comments stripped.
 *
 * `open`/`close` are parameters because the third definition is PYTHON, whose
 * set literal is braced rather than bracketed (#7798). Defaulted so the Swift
 * and TypeScript call sites above read exactly as they did.
 */
function tokensInLiteral(
  source: string,
  opener: RegExp,
  open: string = "[",
  close: string = "]",
  comment: RegExp = /(^|[^:])\/\/.*$/gm,
): string[] {
  const start = source.search(opener);
  if (start === -1) return [];
  const from = source.indexOf(open, start);
  if (from === -1) return [];
  let depth = 0;
  let end = -1;
  for (let i = from; i < source.length; i += 1) {
    if (source[i] === open) depth += 1;
    if (source[i] === close) {
      depth -= 1;
      if (depth === 0) {
        end = i;
        break;
      }
    }
  }
  if (end === -1) return [];
  const body = source
    .slice(from, end)
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(comment, "$1");
  return Array.from(body.matchAll(/"([^"]+)"/g), (m) => m[1].toLowerCase());
}

const swiftSource = readFileSync(SWIFT, "utf8");
const webSource = readFileSync(WEB, "utf8");

/** Swift source with line comments and block comments removed. Control below. */
function stripSwiftComments(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "");
}
const swiftCode = stripSwiftComments(swiftSource);

const swiftDesignators = tokensInLiteral(
  swiftSource,
  /private static let designators\s*:\s*Set<String>\s*=/,
);
const webSuffixes = tokensInLiteral(
  webSource,
  /const CLUB_TYPE_SUFFIXES\s*:\s*ReadonlySet<string>\s*=/,
);
const swiftUnshippable = tokensInLiteral(
  swiftSource,
  /private static let unshippableBadges\s*:\s*Set<String>\s*=/,
);
const swiftIndividualSports = tokensInLiteral(
  swiftSource,
  /static let individualSportPrefixes\s*:\s*Set<String>\s*=/,
);
const webIndividualSports = tokensInLiteral(
  webSource,
  /const INDIVIDUAL_SPORT_PREFIXES\s*:\s*ReadonlySet<string>\s*=/,
);
const webUnshippable = tokensInLiteral(
  webSource,
  /const UNSHIPPABLE_BADGES\s*:\s*ReadonlySet<string>\s*=/,
);

/**
 * #7798 — the THIRD definition, and the one neither client could have saved us
 * from. `playoffs.py` MINTS `short_name` into the payload; a client can only
 * shorten a name it is handed, so when the server served `Leeds United` as
 * "United" both clients rendered exactly what they were given. The server's
 * copy therefore has to be in this comparison, on the same terms as the Swift:
 * read out of source, never transcribed.
 */
const PY = join(__dirname, "../../backend/app/utils/team_short_name.py");
const pySource = readFileSync(PY, "utf8");
const pyDesignators = tokensInLiteral(
  pySource,
  /CLUB_TYPE_SUFFIXES\s*:\s*frozenset\[str\]\s*=\s*frozenset\(/,
  "{",
  "}",
  /(^|[^:])#.*$/gm,
);

describe("#4250 — one team-short-name rule, two clients", () => {
  /**
   * The parser is the part of this file that can fail SILENTLY: a regex that
   * matches nothing yields an empty set, and every `for (const t of [])`
   * assertion below then passes having examined nothing. These two are the
   * reachability check, not a fact about football.
   */
  it("both definitions were actually found and read", () => {
    expect(swiftDesignators.length).toBeGreaterThanOrEqual(60);
    expect(webSuffixes.length).toBeGreaterThanOrEqual(30);
    // Anchors that must survive any future edit to either list.
    expect(swiftDesignators).toContain("afc");
    expect(webSuffixes).toContain("afc");
    // The comment-stripping must not eat the tokens themselves.
    expect(new Set(swiftDesignators).size).toBe(swiftDesignators.length);
    expect(new Set(webSuffixes).size).toBe(webSuffixes.length);
  });

  it("every designator the iPhone catches, the browser catches too", () => {
    const missed = swiftDesignators.filter(
      (token) => !isNonDistinctiveTrailingWord(token),
    );
    expect(missed).toEqual([]);
  });

  it("every club word the browser catches is in the iPhone's set", () => {
    const swift = new Set(swiftDesignators);
    const missed = webSuffixes.filter((token) => !swift.has(token));
    expect(missed).toEqual([]);
  });

  /**
   * The browser reaches most short tokens by LENGTH rather than by listing
   * them, which is the right design and also the reason a three-letter club
   * initial slipped through. This pins where each half of the coverage comes
   * from, so shortening the length clause cannot quietly re-open #4250.
   */
  it("the three-letter club initials are listed, not left to the length clause", () => {
    for (const token of ["afc", "wfc", "lfc", "pfk", "nps", "sad", "cfc"]) {
      expect(token.length).toBeGreaterThan(2);
      expect(webSuffixes).toContain(token);
      expect(isNonDistinctiveTrailingWord(token)).toBe(true);
    }
  });

  /**
   * #7798 — the server joins the comparison. The three sets are asserted EQUAL
   * rather than one-way subset, which the two-client pairs above deliberately
   * are not: the Swift carries leading-initial tokens the browser reaches by
   * length, and that asymmetry is load-bearing. The Python was written FROM the
   * browser's set on the same day, so equality is true today and an inequality
   * is drift — which is the only thing this file exists to report.
   */
  it("the server's designator set was actually found and read", () => {
    expect(pyDesignators.length).toBeGreaterThanOrEqual(30);
    expect(pyDesignators).toContain("afc");
    expect(pyDesignators).toContain("united");
    expect(new Set(pyDesignators).size).toBe(pyDesignators.length);
  });

  it("the server and the browser hold the SAME set, token for token", () => {
    expect([...pyDesignators].sort()).toEqual([...webSuffixes].sort());
  });

  it("every designator the server catches, both clients catch too", () => {
    const swift = new Set(swiftDesignators);
    expect(pyDesignators.filter((t) => !isNonDistinctiveTrailingWord(t))).toEqual([]);
    expect(pyDesignators.filter((t) => !swift.has(t))).toEqual([]);
  });

  /**
   * The server's rule has a clause the clients do not: it prefers a stored
   * ABBREVIATION over any name shortening. That is not drift — it is the one
   * thing the server knows and the clients do not — but it must stay visible
   * here, because "the sets are equal" would otherwise read as "the three
   * implementations agree", and they agree only about designators.
   */
  it("the server's extra clause is the abbreviation, and it is stated", () => {
    expect(pySource).toMatch(/if abbreviation:\s*\n\s*return abbreviation/);
  });
});

/**
 * #4271 — the class this file could not see, and now can.
 *
 * #4250 added `state`, `calcio`, `academy`, `sporting` and `wfc` to the Swift
 * designator set. `TeamShortNamePairTests.swift` carries 234 production fixture
 * rows whose expected strings were captured BEFORE that, so 22 of them went on
 * asserting the pre-#4250 outputs and the Swift suite went red the moment #4250
 * landed on master (`ae83f1d1`). Nothing stopped it: **CI compiles no Swift**,
 * so every gate in the merge path — notices 13, 18, 28 and 32 alike — passed a
 * commit whose own test suite was failing 44 assertions.
 *
 * Compiling Swift in CI is the real repair and is not this ship. What IS
 * available is that the defect is a property of the fixture TEXT, checkable by
 * a source scan in jest, which CI does run:
 *
 *     if a fixture's team NAME ends in a Swift designator, that side's expected
 *     label must be the whole name — never a truncation of it
 *
 * because `TeamShortName.short` returns the full name for exactly those, and a
 * pair rule that only ever GROWS a label can never hand back less. Every one of
 * the 21 stale label expectations violates this ("Hove Albion WFC" for
 * "Brighton and Hove Albion WFC", "Calcio" for "Sassuolo Calcio", "Diego State"
 * for "San Diego State"); every corrected one satisfies it.
 *
 * The designator set is READ FROM THE SWIFT, never transcribed — a transcribed
 * copy is the third implementation this whole file exists to prevent — and the
 * check is deliberately scoped to LISTED tokens, so it re-implements no part of
 * `isDesignator` (the trailing-founding-year clause is not mirrored here, and
 * rows like "US Catanzaro 1929" are simply not examined).
 */
interface PairFixture {
  away: string;
  home: string;
  awayLabel: string;
  homeLabel: string;
}

/** Every `(…)` fixture row of the two tables in `TeamShortNamePairTests.swift`. */
function pairFixtures(source: string): PairFixture[] {
  const rows: PairFixture[] = [];
  for (const line of source.split("\n")) {
    if (!line.trim().startsWith('("')) continue;
    const s = Array.from(line.matchAll(/"([^"]*)"/g), (m) => m[1]);
    // `colliding` rows carry the historical shared label in slot 2; `clean`
    // rows do not. Both put the two expected LABELS immediately before the two
    // expected badges, so the labels are always slots -4 and -3.
    if (s.length !== 7 && s.length !== 6) continue;
    rows.push({
      away: s[0],
      home: s[1],
      awayLabel: s[s.length - 4],
      homeLabel: s[s.length - 3],
    });
  }
  return rows;
}

/** The rows that violate the invariant, as readable strings. */
function truncatedDesignatorNames(
  fixtures: PairFixture[],
  designators: ReadonlySet<string>,
): string[] {
  const endsInDesignator = (name: string) => {
    const words = name.trim().split(/\s+/);
    if (words.length < 2) return false;
    const last = words[words.length - 1].replace(/^[().,]+|[().,]+$/g, "");
    return designators.has(last.toLowerCase());
  };
  const bad: string[] = [];
  for (const row of fixtures) {
    if (endsInDesignator(row.away) && row.awayLabel !== row.away) {
      bad.push(`${row.away} → ${row.awayLabel}`);
    }
    if (endsInDesignator(row.home) && row.homeLabel !== row.home) {
      bad.push(`${row.home} → ${row.homeLabel}`);
    }
  }
  return bad;
}

describe("#4271 — the iPhone's pair fixtures agree with the iPhone's designator set", () => {
  const fixtureSource = readFileSync(SWIFT_PAIR_FIXTURES, "utf8");
  const fixtures = pairFixtures(fixtureSource);
  const swift = new Set(swiftDesignators);

  /**
   * The reachability check. A row parser that matches nothing returns `[]`, and
   * the invariant below then passes having examined no fixture at all — the
   * failure mode that let the stale rows survive in the first place.
   */
  it("the fixture tables were actually found and parsed", () => {
    expect(fixtures.length).toBeGreaterThanOrEqual(230);
    expect(fixtures).toContainEqual({
      away: "Clemson Tigers",
      home: "LSU Tigers",
      awayLabel: "Clemson Tigers",
      homeLabel: "LSU Tigers",
    });
    // …and the invariant must have real work to do, or it proves nothing.
    const examined = fixtures.filter((r) =>
      [r.away, r.home].some((n) => {
        const w = n.trim().split(/\s+/);
        return w.length > 1 && swift.has(w[w.length - 1].toLowerCase());
      }),
    );
    expect(examined.length).toBeGreaterThanOrEqual(40);
  });

  it("no fixture expects a designator-ending club to render as a truncation of itself", () => {
    expect(truncatedDesignatorNames(fixtures, swift)).toEqual([]);
  });

  /**
   * The control. An invariant that cannot fail is not an invariant, so the
   * three shapes that actually shipped red are fed back through the same
   * predicate and must all be caught.
   */
  it("catches the rows that shipped red", () => {
    const stale: PairFixture[] = [
      {
        away: "Arsenal WFC",
        home: "Brighton and Hove Albion WFC",
        awayLabel: "Arsenal WFC",
        homeLabel: "Hove Albion WFC",
      },
      {
        away: "Sassuolo Calcio",
        home: "FC Augsburg",
        awayLabel: "Calcio",
        homeLabel: "Augsburg",
      },
      {
        away: "San Diego State",
        home: "Portland State",
        awayLabel: "Diego State",
        homeLabel: "Portland State",
      },
    ];
    expect(truncatedDesignatorNames(stale, swift)).toEqual([
      "Brighton and Hove Albion WFC → Hove Albion WFC",
      "Sassuolo Calcio → Calcio",
      "San Diego State → Diego State",
    ]);
  });
});

/**
 * #4539 — the parity that mattered was never only the SET.
 *
 * #4466 gave the browser a badge rule the iPhone did not have: a name whose
 * distinctive part is three or more words takes their initials, so PSG stops
 * being "GER". It shipped to the browser alone, and for a day the two clients
 * disagreed on the badge for roughly a fifth of all names — this file was green
 * throughout, because it compared the designator sets and the badge rule is not
 * a set.
 *
 * So the checks below are on the RULE. They still read both files out of source
 * rather than transcribing either, for the same reason as everything above: a
 * transcribed copy is a third implementation.
 *
 * WHY THE SWIFT SIDE IS CHECKED STRUCTURALLY AND NOT BY OUTPUT. CI compiles no
 * Swift (#4302), so jest cannot call `TeamShortName.abbreviation` and diff it
 * against `teamCrestBadge` — the only honest output comparison lives in
 * `BainLuckTests/CrestBadgeInitialsTests.swift`, whose every expectation was read
 * off THIS module before being written down. What jest can prove is that the
 * iPhone still has the rule at all, and that the two halves it shares with the
 * browser — the token filter's source set and the unshippable backstop — have
 * not drifted apart again.
 */
describe("#4539 — one badge rule, two clients", () => {
  it("both unshippable-badge sets were actually found and read", () => {
    // The reachability check. A regex that matches nothing yields [], and every
    // assertion below then passes having compared two empty sets — the exact
    // way the set-only version of this file stayed green through #4466.
    expect(swiftUnshippable.length).toBeGreaterThanOrEqual(15);
    expect(webUnshippable.length).toBeGreaterThanOrEqual(15);
    expect(swiftUnshippable).toContain("wtf");
    expect(webUnshippable).toContain("wtf");
  });

  it("the two unshippable-badge sets are identical", () => {
    // A badge banned on one client and not the other is a badge that ships.
    const swift = new Set(swiftUnshippable);
    const web = new Set(webUnshippable);
    expect([...web].filter((t) => !swift.has(t))).toEqual([]);
    expect([...swift].filter((t) => !web.has(t))).toEqual([]);
  });

  it("the comment stripper is load-bearing and works", () => {
    // The scans below read CODE. The Swift's own doc comment names
    // `CLUB_TYPE_SUFFIXES` to explain why it borrows `designators` instead, so a
    // raw scan for that identifier fires on the CORRECT file — which is
    // `discoverCrestBadge4466.test.tsx`'s lesson arriving here by experiment: a
    // guard that reads its target's prose is measuring the prose.
    expect(stripSwiftComments("/// mentions CLUB_TYPE_SUFFIXES\n")).not.toMatch(
      /CLUB_TYPE_SUFFIXES/,
    );
    expect(stripSwiftComments("let x = CLUB_TYPE_SUFFIXES")).toMatch(
      /CLUB_TYPE_SUFFIXES/,
    );
    // …and it must not eat the code it is meant to keep.
    expect(swiftCode).toMatch(/static func abbreviation/);
    expect(swiftCode.length).toBeGreaterThan(1500);
  });

  it("the iPhone still forks on three or more distinctive tokens", () => {
    // Structural, and deliberately narrow: the fork's THRESHOLD and the fact
    // that it filters before counting. Deleting either — the failure mode that
    // silently reopens #4539 — changes both of these.
    expect(swiftCode).toMatch(/distinctiveTokens\s*\(/);
    expect(swiftCode).toMatch(/distinctive\.count\s*>=\s*3/);
    // …and the filter is the one this file already guarantees agrees with the
    // browser, rather than a second transcribed copy of CLUB_TYPE_SUFFIXES.
    expect(swiftCode).toMatch(/designators\.contains\(lower\)/);
    expect(swiftCode).not.toMatch(/CLUB_TYPE_SUFFIXES/);
  });

  it("the browser's own fork is still there to be matched", () => {
    // The other half of the same assertion. If #4466's rule is reverted or
    // rewritten on the web, the iPhone's port is the thing that is now wrong,
    // and this is the line that says so.
    expect(webSource).toMatch(/export function teamCrestBadge/);
    expect(webSource).toMatch(/distinctive\.length\s*<\s*3/);
  });

  it("the token filter agrees with the browser's predicate on the fork corpus", () => {
    // The Swift borrows `designators` in place of CLUB_TYPE_SUFFIXES, which is
    // only sound because containment is asserted BOTH ways above. This pins the
    // clauses that are NOT the set — length, squad marker, bare number, roman
    // numeral — against the browser's predicate, since the Swift restates them
    // rather than sharing them.
    for (const token of ["fc", "u20", "1846", "iii", "al", "sc"]) {
      expect(isNonDistinctiveTrailingWord(token)).toBe(true);
    }
    for (const token of ["paris", "saint", "germain", "lakers", "sadd"]) {
      expect(isNonDistinctiveTrailingWord(token)).toBe(false);
    }
  });

  it("the browser badges the photographed club correctly, under both spellings", () => {
    // The reader-visible anchor, and the pair is the point: the stored name is
    // an input and both spellings were live on production the same afternoon.
    // `CrestBadgeInitialsTests` asserts the identical pair on the iPhone.
    expect(teamCrestBadge("Paris Saint Germain")).toBe("PSG");
    expect(teamCrestBadge("Paris Saint-Germain")).toBe("PSG");
  });
});

/**
 * #4624 — the sport that closes the fork, which is a LIST and therefore the
 * same divergence risk as the two sets above.
 *
 * The fork's own comment says no filter can tell a three-word club from a
 * three-word person from the string. The sport can, both clients hold it, and
 * neither was passing it to the badge — so "Eloy Mendez Alcantara" badged `EMA`
 * on the iPhone and `EMA` on the browser. Identically wrong is still wrong, and
 * the way it stops being identical is one client widening its list alone.
 */
describe("#4624 — one person/club discriminator, two clients", () => {
  it("both prefix sets were actually found and read", () => {
    // The reachability check. A regex that matches nothing yields [], and the
    // comparison below then passes having compared two empty sets.
    expect(swiftIndividualSports.length).toBe(4);
    expect(webIndividualSports.length).toBe(4);
    expect(swiftIndividualSports).toContain("tennis");
    expect(webIndividualSports).toContain("tennis");
  });

  it("the two prefix sets are identical", () => {
    const swift = new Set(swiftIndividualSports);
    const web = new Set(webIndividualSports);
    expect([...web].filter((t) => !swift.has(t))).toEqual([]);
    expect([...swift].filter((t) => !web.has(t))).toEqual([]);
  });

  it("both clients read the key's first SEGMENT, not a substring of it", () => {
    // England's Boxing Day fixtures are a plausible key, and a `contains`
    // matcher would badge every club in it as a person. The browser's predicate
    // is executed; the iPhone's is read out of its source, where the `split` is
    // the whole of the claim.
    expect(namesAPerson("soccer_england_boxing_day_cup")).toBe(false);
    expect(namesAPerson("tennis_atp_us_open")).toBe(true);
    expect(namesAPerson(null)).toBe(false);
    // A point-free `names.map(teamCrestBadge)` hands `map`'s INDEX in as the
    // sport. It is legal, it is in this repo, and before the type test it threw
    // — a blank card, not a wrong badge. `#4466`'s own suite caught it.
    expect(namesAPerson(0 as unknown as string)).toBe(false);
    expect(namesAPerson(1 as unknown as string)).toBe(false);
    // Both halves of that hazard are pinned here. The COMPILER half: delete the
    // directive below and `npm run typecheck` goes red, because the signature
    // does refuse `map`'s index — so the shape cannot reach a shipping call site
    // unnoticed. The RUNTIME half: the badge is still correct when it does,
    // which is why this is a guard and not an outage.
    const pointFree = ["Paris Saint Germain", "Paris Saint-Germain"].map(
      // @ts-expect-error — `map` passes (value, INDEX, array); the index is not
      // a sport key, and `namesAPerson` absorbs it rather than throwing.
      teamCrestBadge,
    );
    expect(pointFree).toEqual(["PSG", "PSG"]);
    expect(swiftCode).toMatch(/key\.split\(separator: "_"\)\.first/);
    expect(swiftCode).toMatch(/individualSportPrefixes\.contains\(sport\)/);
  });

  it("the iPhone closes the fork on a person's sport, and only there", () => {
    // Structural: the gate is inside the fork, so the two clients cannot end up
    // with one of them applying it to every name.
    expect(swiftCode).toMatch(/namesAPerson\(sportKey: sportKey\)/);
    expect(swiftCode).toMatch(/distinctive\.count\s*>=\s*3/);
  });

  it("the two clients badge the issue's own names the same way", () => {
    // The reader-visible anchor, asserted on the browser here and on the iPhone
    // in `CrestBadgeNamesAPerson4624Tests` — the same four names, the same four
    // answers, under a key and without one.
    for (const [name, initials, surname] of [
      ["Eloy Mendez Alcantara", "EMA", "ALC"],
      ["Constantin Bittoun Kouzmine", "CBK", "KOU"],
      ["Sherif Ahmed Abdelaziz", "SAA", "ABD"],
      ["Petr Bar Biryukov", "PBB", "BIR"],
    ]) {
      expect(teamCrestBadge(name)).toBe(initials);
      expect(teamCrestBadge(name, "soccer_epl")).toBe(initials);
      expect(teamCrestBadge(name, "tennis_other")).toBe(surname);
    }
  });

  it("a club keeps its badge under every key, including a person's sport", () => {
    for (const key of [undefined, "soccer_france_ligue_one", "tennis_atp"]) {
      expect(teamCrestBadge("Paris Saint Germain", key)).toBe("PSG");
    }
    expect(teamCrestBadge("Notre Dame Fighting Irish", "americanfootball_ncaaf")).toBe("NDF");
  });

  it("a surname that spells an unshippable badge keeps the initials", () => {
    // The only direction this change can make a badge worse, closed on both
    // clients by the same clause.
    expect(teamCrestBadge("Juan Carlos Assis", "tennis_other")).toBe("JCA");
    expect(teamCrestBadge("Juan Carlos Alves", "tennis_other")).toBe("ALV");
  });

  it("a doubles pair is untouched under a person's sport", () => {
    expect(teamCrestBadge("Siniakova / Townsend", "tennis_wta")).toBe(
      teamCrestBadge("Siniakova / Townsend"),
    );
  });
});

/**
 * #4627 — the hand-picked label, which is a TABLE and therefore the one kind of
 * divergence this file was already shaped to catch.
 *
 * Alex ruled (option B, relayed by Fable-5 Sat 2026-09-12 6:14am PT) that Paris
 * Saint-Germain is "PSG" on both clients: the crest letters, as an explicit
 * entry, not a rule change that would turn the Lakers into "LAL". A list that is
 * the same on both clients is exactly the thing that silently stops being the
 * same, so it is read out of both sources here and transcribed into neither.
 *
 * native/131 wrote the iOS half (PR #5650) and deliberately did NOT write this
 * block: with no web map to compare against it would have passed by comparing
 * one thing to nothing, which is the vacuous guard this file exists to prevent.
 *
 * WEB MEASUREMENT, whole population, 13,630 distinct production team names from
 * 45 days of `events` (ux/1219, 2026-09-12), real module before vs after:
 * **3 labels change — the three PSG spellings — and 0 badges.** Over 24,499
 * distinct (home, away) pairs: **26 move, all PSG fixtures, the opponent's label
 * byte-identical in all 26, 0 new collisions.** The iOS numbers native measured
 * the same day are 3 / 0 / 26 / 0 — the same shape on the same population.
 */
function dictionaryPairs(source: string, opener: RegExp): [string, string][] {
  const start = source.search(opener);
  if (start === -1) return [];
  // The literal begins after the `=`, NOT at the first `[` — Swift writes the
  // dictionary's TYPE in brackets too (`: [String: String] =`), and reading from
  // that one yields the type annotation and no pairs at all. Caught by the
  // reachability check below, which is what it is for.
  const assign = source.indexOf("=", start);
  const from = source.indexOf("[", assign);
  const end = source.indexOf("]", from);
  if (from === -1 || end === -1) return [];
  const body = source
    .slice(from, end)
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(^|[^:])\/\/.*$/gm, "$1");
  return Array.from(body.matchAll(/"([^"]+)"\s*:\s*"([^"]+)"/g), (m) => [
    m[1],
    m[2],
  ]);
}

const swiftHandPicked = dictionaryPairs(
  swiftSource,
  /static let handPickedLabels\s*:\s*\[String\s*:\s*String\]\s*=/,
);

describe("#4627 — one hand-picked label table, two clients", () => {
  it("the iPhone's table was actually found and read", () => {
    // The reachability check this file demands of every parser it adds: a regex
    // that matches nothing yields [], and "the two tables agree" then passes
    // having compared an empty list to a map it never looked at.
    expect(swiftHandPicked.length).toBeGreaterThanOrEqual(1);
    expect(swiftHandPicked).toContainEqual(["paris saint germain", "PSG"]);
    expect(HAND_PICKED_LABELS.size).toBeGreaterThanOrEqual(1);
  });

  it("the two tables are identical, in both directions", () => {
    // A club labelled on one client and not the other is the divergence Alex's
    // ruling was issued to end.
    const swift = new Map(swiftHandPicked);
    expect([...HAND_PICKED_LABELS].filter(([k, v]) => swift.get(k) !== v)).toEqual([]);
    expect(
      [...swift].filter(([k, v]) => HAND_PICKED_LABELS.get(k) !== v),
    ).toEqual([]);
  });

  it("every key is already in the normalised form the lookup produces", () => {
    // The DEAD-ENTRY guard, and the reason `handPickedKey` is exported. A key
    // written "Paris Saint-Germain" is unreachable: nothing would ever look it
    // up, and a test that could only call `teamShortName` would pass over it
    // for as long as the entry existed.
    for (const key of HAND_PICKED_LABELS.keys()) {
      expect(handPickedKey(key)).toBe(key);
    }
    // …and the same rule holds on the iPhone's copy, which is the one a Swift
    // test can check but CI cannot compile (#4302).
    for (const [key] of swiftHandPicked) {
      expect(handPickedKey(key)).toBe(key);
    }
  });

  it("no two clubs claim the same label", () => {
    const labels = [...HAND_PICKED_LABELS.values()];
    expect(new Set(labels).size).toBe(labels.length);
  });

  it("all three live spellings of the club reach the entry", () => {
    // The reader-visible point. These three are all on production — 14, 9 and 9
    // events over 60 days — and they rendered as three different labels: the
    // whole name, "Saint-Germain" and "Germain".
    for (const spelling of [
      "Paris Saint-Germain FC",
      "Paris Saint-Germain",
      "Paris Saint Germain",
    ]) {
      expect(handPickedKey(spelling)).toBe("paris saint germain");
      expect(teamShortName(spelling)).toBe("PSG");
    }
    // The badge has been spelling-independent since #4539 and must not move.
    for (const spelling of [
      "Paris Saint-Germain FC",
      "Paris Saint-Germain",
      "Paris Saint Germain",
    ]) {
      expect(teamCrestBadge(spelling)).toBe("PSG");
    }
  });

  it("CONTROL: a club with no entry is untouched by any of it", () => {
    // An entry-driven override that changed anything else would be the rule
    // change Alex explicitly did not want.
    expect(teamShortName("Los Angeles Lakers")).toBe("Lakers");
    expect(teamShortName("Sunderland AFC")).toBe("Sunderland AFC");
    expect(teamShortName("Paris FC")).toBe("Paris FC");
    expect(HAND_PICKED_LABELS.get(handPickedKey("Paris FC"))).toBeUndefined();
  });

  it("the two-token floor keeps clubs a designator distinguishes apart", () => {
    // Without the floor "Manchester United" keys as `manchester`, which is what
    // "Manchester City" keys as too, and one future entry would relabel both.
    expect(handPickedKey("Manchester United")).toBe("manchester united");
    expect(handPickedKey("Manchester United FC")).toBe("manchester united");
    expect(handPickedKey("Manchester City")).toBe("manchester city");
    expect(handPickedKey("Manchester United")).not.toBe(
      handPickedKey("Manchester City"),
    );
    // The women's side keeps its own key rather than folding into the men's.
    expect(handPickedKey("Arsenal W")).toBe("arsenal w");
    expect(handPickedKey("Arsenal")).toBe("arsenal");
  });

  it("punctuation and accents key the way the iPhone keys them", () => {
    // `alphanumeric` elsewhere in the module is ASCII-only; this key is not, on
    // purpose. One club, one key, means one key across clients, and Swift's
    // `isLetter` keeps the ö.
    expect(handPickedKey("1. FC Köln")).toBe("1 fc köln");
    expect(handPickedKey("Crimson (W)")).toBe("crimson w");
  });

  /**
   * THE HAZARD THE FLOOR DOES NOT COVER, pinned before the list grows.
   *
   * The floor stops at TWO tokens, so a THREE-token name whose third token is a
   * designator strips to a two-token key that another club can share. Measured
   * over the same 13,630 production names: `handPickedKey` produces 13,308 keys,
   * 298 of which are carried by more than one spelling, and **5 of those 298 are
   * not one club spelled two ways**:
   *
   *     new mexico    <- "New Mexico State",  "New Mexico United"
   *     los angeles   <- "Los Angeles FC",    "Los Angeles C/F/R"
   *     new york      <- "New York City FC",  "New York G", "New York J"
   *     bradford park avenue, exmouth town  (one club, bracketed or double suffix)
   *
   * None is in the table today, so nothing is mislabelled. This is the ratchet:
   * adding any of them as an entry would relabel a club nobody named, and it
   * would do so on BOTH clients, since the Swift shares the floor. Whoever wants
   * one of these needs a longer floor or a per-club abbreviation (#3353) first.
   */
  it("no key in the table is one two different clubs share", () => {
    const AMBIGUOUS = new Set(["new mexico", "los angeles", "new york"]);
    const unsafe = [...HAND_PICKED_LABELS.keys()].filter((k) => AMBIGUOUS.has(k));
    expect(unsafe).toEqual([]);
    // POSITIVE CONTROL — the collision is real, not hypothetical, and the two
    // names really do land on one key today.
    expect(handPickedKey("New Mexico State")).toBe("new mexico");
    expect(handPickedKey("New Mexico United")).toBe("new mexico");
    expect(AMBIGUOUS.has(handPickedKey("New Mexico State"))).toBe(true);
  });
});

describe("#4250 — the names a reader sees", () => {
  it("the photographed event hero names the club, not its initials", () => {
    expect(teamShortName("Sunderland AFC")).toBe("Sunderland AFC");
    expect(teamShortNames({ name: "Manchester City FC" }, { name: "Sunderland AFC" })).toEqual({
      home: "Manchester City FC",
      away: "Sunderland AFC",
    });
  });

  it("the rest of the measured population keeps its name", () => {
    for (const name of [
      "Barrow AFC", // AFC, 68 distinct names
      "Ashington AFC",
      "Athlone Town AFC",
      "Arsenal WFC", // WFC, 8
      "Manchester City WFC",
      "Liverpool LFC", // LFC, 2
      "Neftçi PFK", // PFK, 2
      "Volos NPS", // NPS, 2
      "Portimonense SAD", // SAD, 8
      "Ludogorets III", // III, 6 — a reserve side
      "Kai Kamaka III", // and a person's generational suffix
    ]) {
      expect(teamShortName(name)).toBe(name);
    }
  });

  /**
   * The controls. A set that grows without a floor eventually swallows the
   * 90% of names where the last word IS the team, so these have to fail if
   * the change went too far — including the two cases that look like club
   * initials and are not.
   */
  it("a name whose last word identifies the team still shortens", () => {
    expect(teamShortName("Los Angeles Lakers")).toBe("Lakers");
    expect(teamShortName("Baltimore Orioles")).toBe("Orioles");
    expect(teamShortName("Houston Dynamo")).toBe("Dynamo");
    // "FC RFS" and "FK RFS" are Riga Football School's own name (2 distinct
    // names on production), so RFS is deliberately absent from both sets.
    expect(teamShortName("FC RFS")).toBe("RFS");
    expect(isNonDistinctiveTrailingWord("rfs")).toBe(false);
    // Trailing "USA" (8) names somebody.
    expect(isNonDistinctiveTrailingWord("usa")).toBe(false);
  });
});

/**
 * #7163 — one particled-surname rule, two clients.
 *
 * The browser shipped `NAME_PARTICLES` + `particledSurnameStart` in `dc20ddf8f`
 * after ux/1356 photographed "de Minaur" rendering as "Minaur" on the event
 * hero. The iPhone's `short` had the same defect from the same line and got the
 * same rule; without the comparison below the two lists drift the way every
 * other list in this file would have.
 *
 * The GATE is the half worth guarding hardest. Ungated the walk turns "Tigres
 * de la UANL" into "de la UANL", and ux measured that 56.3% of 2,797 multi-word
 * soccer names would move — so both clients reach the walk only through
 * `namesAPerson`, and both are asserted to.
 */
const swiftParticles = tokensInLiteral(
  swiftSource,
  /static let nameParticles\s*:\s*Set<String>\s*=/,
);
const webParticles = tokensInLiteral(
  webSource,
  /const NAME_PARTICLES\s*:\s*ReadonlySet<string>\s*=/,
);

describe("#7163 — one particled-surname rule, two clients", () => {
  it("both particle sets were actually found and read", () => {
    // Reachability: a regex that matches nothing yields [], and every
    // comparison below would then pass having compared two empty sets.
    expect(swiftParticles.length).toBeGreaterThanOrEqual(27);
    expect(webParticles.length).toBeGreaterThanOrEqual(27);
    expect(swiftParticles).toContain("de");
    expect(webParticles).toContain("de");
    // The comment stripper must not have eaten tokens or duplicated them.
    expect(new Set(swiftParticles).size).toBe(swiftParticles.length);
    expect(new Set(webParticles).size).toBe(webParticles.length);
  });

  it("the two particle sets are identical", () => {
    const swift = new Set(swiftParticles);
    const web = new Set(webParticles);
    expect([...web].filter((t) => !swift.has(t))).toEqual([]);
    expect([...swift].filter((t) => !web.has(t))).toEqual([]);
  });

  it("both clients gate the walk on a person's sport", () => {
    // The browser's half is executed; the iPhone's is read out of source, where
    // the gate being INSIDE the fork is the whole of the claim.
    expect(teamShortName("Alex de Minaur", null, "tennis_other")).toBe("de Minaur");
    expect(teamShortName("Alex de Minaur")).toBe("Minaur");
    expect(teamShortName("Tigres de la UANL", null, "soccer_mexico_ligamx")).toBe("UANL");
    expect(teamShortName("Tigres de la UANL", null, "tennis_other")).toBe("de la UANL");
    expect(swiftCode).toMatch(/if namesAPerson\(sportKey: sportKey\) \{/);
    expect(swiftCode).toMatch(/particledSurnameStart\(parts\)/);
  });

  it("both clients WALK rather than take one step", () => {
    // Stacked particles are why this is a loop. A one-step rule hands back "de
    // Zandschulp", which is the same defect one token along.
    expect(teamShortName("Botic van de Zandschulp", null, "tennis_other")).toBe(
      "van de Zandschulp",
    );
    expect(swiftCode).toMatch(/while start > 0, nameParticles\.contains\(/);
  });

  it("the designator refusal still runs FIRST on both clients", () => {
    // Order, not presence: a person-sport name whose tail names nobody is shown
    // whole before the walk can see it, so the two rules never compose.
    //
    // 🪤 "Juan de la Cruz III" does NOT discriminate the two orders and looks
    // like it should — the walk reads the token BEFORE the last, which is
    // "Cruz", so it declines and the refusal answers either way. A mutation
    // battery on the iPhone's copy caught the vacuity. The shape that IS
    // observable is a particle sitting directly in front of a tail that names
    // nobody, the Portuguese "de Sá": whole name shipped, "de Sa" hoisted.
    expect(teamShortName("Joao de Sa", null, "tennis_other")).toBe("Joao de Sa");
    expect(teamShortName("Juan de la Cruz III", null, "boxing_boxing")).toBe(
      "Juan de la Cruz III",
    );
    const web = webSource.indexOf("isNonDistinctiveTrailingWord(words[words.length - 1])");
    const webWalk = webSource.indexOf("particledSurnameStart(words)");
    expect(web).toBeGreaterThan(-1);
    expect(webWalk).toBeGreaterThan(web);
    const swiftRefusal = swiftCode.indexOf("if isNonDistinctiveToken(last)");
    const swiftWalk = swiftCode.indexOf("particledSurnameStart(parts)");
    expect(swiftRefusal).toBeGreaterThan(-1);
    expect(swiftWalk).toBeGreaterThan(swiftRefusal);
  });

  /**
   * The control. A particle set that grows without a gate swallows the club
   * population, so these have to keep their shipped labels on every key.
   */
  it("a club keeps its label under every key, including a person's", () => {
    for (const name of [
      "Sport Lisboa e Benfica",
      "Tigres de la UANL",
      "Deportivo de La Coruna",
      "Los Angeles Lakers",
    ]) {
      const shipped = teamShortName(name);
      // #5634: a soccer key now keeps a club of up to three words whole
      // ("Los Angeles Lakers" under a La Liga key is not a real row), so the
      // soccer arm of this control lives in
      // `teamShortNameSoccerWholeClub5634.test.ts` (Benfica, UANL, Coruna).
      for (const key of [
        null,
        undefined,
        "basketball_nba",
        "americanfootball_nfl",
      ]) {
        expect(teamShortName(name, null, key)).toBe(shipped);
      }
    }
  });
});
