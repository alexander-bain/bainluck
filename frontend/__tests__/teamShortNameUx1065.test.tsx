// UX-1065 (#2936) — A TEAM IS NEVER CALLED "TOWN".
//
// What the shopper saw, https://bainluck.com/events/15291104 (Ipswich Town v
// Liverpool, EPL): the hero named the home side **"Town"**. Shot again on
// production `75dabbc2` at 2026-09-04 03:4x PT and it is WORSE than filed —
// the same word renders THREE times on that one page:
//
//     hero crest label            "Town"          (vs "Liverpool")
//     hero trend sentence         "-2% Town since open"
//     Bigger Picture season card  "Town"
//
// ...while the "Other Markets" section 700px below prints "Ipswich Town vs
// Liverpool" correctly, and the chart's own y-axis prints "IPS". So the page
// already contains both the defect and two correct renderings of the same team.
//
// ── THE MECHANISM ───────────────────────────────────────────────────────────
//
// `name.split(" ").pop()`. That encodes the AMERICAN convention
// `<place> <nickname>`, where the last word is the distinctive half — "Los
// Angeles Lakers" -> "Lakers" is right and this ship keeps it. It breaks on the
// ENGLISH convention `<place> <club-type>` and on squad qualifiers, where the
// last word identifies nobody: "Ipswich Town" -> "Town", "Austin FC" -> "FC",
// "Argentina W" -> "W", "Chaves B" -> "B".
//
// ── THE POPULATION, RE-MEASURED — AND THE ISSUE'S NUMBER IS THREE THINGS ────
//
// #2936 reports 6,335 of 9,754 teams (65%) as "last word shared with another
// team". That is a true count of a DIFFERENT thing, in two ways:
//
//   (a) it counts table ROWS. `teams` holds 9,757 rows but only 5,546 distinct
//       names — 43% duplicates (#1204 / #1946), e.g. "Bryant Bulldogs" x5.
//   (b) "shared last word" conflates three kinds. Reading the measured buckets:
//
//         FC 115, United 37, State 34, City 32, W 30, Jr 23, B 22, Town 21
//              -> club-type / squad qualifier.  `.pop()` output is NOT A NAME.
//         Bulldogs 60, Eagles 59, Tigers 54, Bears 42, Wildcats 39, Lions 39
//              -> MASCOTS. `.pop()` is the intended compact form.
//         Zhang 22, Cerundolo 21, Fernandez 17, Svitolina 14, Sabalenka 10
//              -> tennis SURNAMES, and each player holds ~10-22 duplicate rows.
//              This class is most of the 6,335 and is not a display defect.
//
// Replaying the shipped rule over the COMPLETE population of 4,701 distinct
// multi-word names (committed as `fixtures/teamNames.ux1065.json`):
//
//     trailing token <= 2 chars   326
//     club-type word              126
//     squad number / U21           19
//     ---------------------------------------------
//     stop being shortened        471   (10.0%)
//     keep `.pop()` unchanged   4,230   (90.0%)
//
// 10.0% is the honest size. It is smaller than the issue's 65% and it is still
// a p1, because the output on those 471 is a word that names nobody, mid-EPL
// season, on the event page.
//
// ── WHY NOT THE FIX THE ISSUE PROPOSES ──────────────────────────────────────
//
// #2936 says "prefer `team_data.abbreviation` (present in the payload)". It is
// present on the REPORTED event and almost nowhere else. Measured over 120 live
// events from `GET /api/events`:
//
//     both sides carry an abbreviation     1
//     exactly one side                     7
//     neither side                       112   (93%)
//
// So that fix repairs 1 event cleanly, renders an asymmetric "IPS vs Liverpool"
// on 7, and changes nothing on 112. The load-bearing half has to be the
// FALLBACK — full name instead of last word — which reaches 100% of them. The
// abbreviation clause is kept (the issue asked for it, and it is the real short
// form) but gated on BOTH sides having one, so the pair stays symmetric. It is
// the half of this diff that ships almost nothing today, and this file says so.
//
// ── AND THE CENSUS IS WRONG IN BOTH DIRECTIONS ──────────────────────────────
//
// The issue lists ~10 call sites "to retire". Four of them are MATCHING, not
// display, and rewriting them would change what matches rather than what
// renders — `RelatedFutures.tsx:170` (box-score name match),
// `RelatedFutures.tsx:552` (dedup filter), `PlayerPropsGrid.tsx:93,96` (assign
// a prop to home/away by parsing the market name), `sportCategories.ts:767,780`
// (classify an outcome as golf/tennis). They are deliberately untouched.
//
// Meanwhile the census does NOT contain `app/events/[id]/page.tsx` — the page
// the issue itself reports. That is where "Town" is printed. Grepping for a
// function finds CALL SITES, not the reported surface.
//
// ── SCOPE SHIPPED HERE, AND WHAT IS MEASURED BUT NOT SHIPPED ────────────────
//
// Shipped: the reported hero (3 sites), the shared `EventCard` (league pages +
// feed), the two "<team> won" sentences on Discover, and the 3-char crest
// FALLBACK badges in the same two Discover components — those took the last
// word too, so an FC-vs-FC card painted two identical "FC" crests, and three
// characters of the short name gives "ALT" / "HAR" instead while leaving
// "Los Angeles Lakers" -> "LAK" untouched.
//
// ~28 further `split(" ").pop()` occurrences remain and are censused onto the
// issue: the four matching sites above, and the `RelatedFutures` display sites,
// which sit in a 2,400-line file whose surfaces this session could not
// photograph.
//
// ── FAILS SAFE BY CONSTRUCTION ──────────────────────────────────────────────
//
// Every branch returns the abbreviation, the last word, or the FULL NAME. The
// helper cannot emit a string the team is not called, and the only direction it
// moves any render is "less short, more correct". That is the property the
// corpus test below asserts over all 4,701 names, and it is what makes a diff
// touching four surfaces gradeable without photographing all of them.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import {
  teamShortName,
  teamShortNames,
  isNonDistinctiveTrailingWord,
} from "@/lib/teamShortName";
import { readFileSync } from "fs";
import { join } from "path";
import corpus from "./fixtures/teamNames.ux1065.json";

function sourceWithoutComments(relPath: string): string {
  const raw = readFileSync(join(process.cwd(), relPath), "utf8");
  return raw
    .replace(/\/\*[\s\S]*?\*\//g, " ")
    .replace(/^\s*\/\/.*$/gm, " ");
}

const NAMES: string[] = (corpus as { names: string[] }).names;

// ───────────────────────────────────────────────────────────────────────────
// THE SHIP — the reported defect
// ───────────────────────────────────────────────────────────────────────────

describe("UX-1065: the reported defect", () => {
  it("Ipswich Town is never called Town", () => {
    expect(teamShortName("Ipswich Town")).toBe("Ipswich Town");
  });

  it("the reported PAIR renders Ipswich Town against Liverpool", () => {
    const pair = teamShortNames(
      { name: "Ipswich Town", abbreviation: "IPS" },
      { name: "Liverpool", abbreviation: null },
    );
    // The away side has no abbreviation on the real payload, so the
    // abbreviation clause must NOT fire and produce "IPS vs Liverpool".
    expect(pair).toEqual({ home: "Ipswich Town", away: "Liverpool" });
  });

  it("no women's side renders as the single letter W", () => {
    for (const n of ["Argentina W", "Australia W", "Albirex Niigata W", "Barry W"]) {
      expect(teamShortName(n)).toBe(n);
    }
  });

  it("an FC-vs-FC fixture does not print FC beat FC", () => {
    // All 5 same-last-word pairs on the 120-event live sample were FC vs FC.
    const pair = teamShortNames(
      { name: "Altrincham FC" },
      { name: "Hartlepool United FC" },
    );
    expect(pair.home).toBe("Altrincham FC");
    expect(pair.away).toBe("Hartlepool United FC");
    expect(pair.home).not.toBe(pair.away);
  });

  it("two teams sharing a MASCOT both fall back to their full names", () => {
    // The pair clause exists for this and nothing else: 22 distinct teams in
    // the corpus end in "Bulldogs", and both of these are real SEC sides, so
    // this fixture is an ordinary Saturday rather than a hypothetical. Without
    // the clause the card reads "Bulldogs" against "Bulldogs".
    const pair = teamShortNames(
      { name: "Georgia Bulldogs" },
      { name: "Mississippi State Bulldogs" },
    );
    expect(pair).toEqual({
      home: "Georgia Bulldogs",
      away: "Mississippi State Bulldogs",
    });
    expect(NAMES).toContain("Georgia Bulldogs");
    expect(NAMES).toContain("Mississippi State Bulldogs");
  });

  it("squad and suffix markers do not become the whole name", () => {
    expect(teamShortName("Chaves B")).toBe("Chaves B");
    expect(teamShortName("Brian Norman Jr")).toBe("Brian Norman Jr");
    expect(teamShortName("Real Madrid II")).toBe("Real Madrid II");
    expect(teamShortName("Bergischer HC")).toBe("Bergischer HC");
    expect(teamShortName("Brondby IF")).toBe("Brondby IF");
  });
});

// ───────────────────────────────────────────────────────────────────────────
// CONTROLS — green on the parent too. These are what must NOT move.
// ───────────────────────────────────────────────────────────────────────────

describe("UX-1065 CONTROL: the American convention is untouched", () => {
  it("CONTROL a place-plus-nickname team still shortens to its nickname", () => {
    expect(teamShortName("Los Angeles Lakers")).toBe("Lakers");
    expect(teamShortName("Tampa Bay Buccaneers")).toBe("Buccaneers");
    expect(teamShortName("Alabama A&M Bulldogs")).toBe("Bulldogs");
  });

  it("CONTROL a single-word team is returned whole", () => {
    expect(teamShortName("Liverpool")).toBe("Liverpool");
    expect(teamShortName("Arsenal")).toBe("Arsenal");
  });

  it("CONTROL a mascot pair that does NOT collide keeps both nicknames", () => {
    const pair = teamShortNames({ name: "Georgia Bulldogs" }, { name: "Auburn Tigers" });
    expect(pair).toEqual({ home: "Bulldogs", away: "Tigers" });
  });

  it("CONTROL asymmetry is allowed where the short name is genuinely the name", () => {
    // "Wednesday" IS Sheffield Wednesday's distinctive name. Forcing both sides
    // to the full name whenever either falls back would lose it.
    const pair = teamShortNames({ name: "Bradford City" }, { name: "Sheffield Wednesday" });
    expect(pair).toEqual({ home: "Bradford City", away: "Wednesday" });
  });
});

// ───────────────────────────────────────────────────────────────────────────
// THE CORPUS — every number in this file's header, as an assertion
// ───────────────────────────────────────────────────────────────────────────

describe("UX-1065: the measured population", () => {
  it("the fixture is the complete distinct multi-word population", () => {
    expect(NAMES).toHaveLength(4701);
    expect(new Set(NAMES).size).toBe(4701);
  });

  it("471 of 4,701 distinct names (10.0%) stop being shortened", () => {
    const changed = NAMES.filter((n) => teamShortName(n) !== n.split(" ").pop());
    expect(changed).toHaveLength(471);
    expect(Math.round((changed.length / NAMES.length) * 1000) / 10).toBe(10.0);
  });

  it("the other 90% keep split-pop output byte for byte", () => {
    const same = NAMES.filter((n) => teamShortName(n) === n.split(" ").pop());
    expect(same).toHaveLength(4230);
  });

  it("FAILS SAFE: every output is the last word or the full name, never a new string", () => {
    for (const n of NAMES) {
      const out = teamShortName(n);
      expect(out === n || out === n.split(" ").pop()).toBe(true);
    }
  });

  it("no output is a non-distinctive word — that is the whole ship", () => {
    const leaked = NAMES.map(teamShortName).filter(
      (out) => out.split(" ").length === 1 && isNonDistinctiveTrailingWord(out),
    );
    expect(leaked).toEqual([]);
  });

  it("the club-word set is complete: no >=3ch trailing token on >=9 names leaks a non-name", () => {
    // The sanity sweep that closed the curation. Every surviving bucket at this
    // size is a mascot or a surname; if a new club word enters the data this
    // goes red and names it.
    const tally = new Map<string, number>();
    for (const n of NAMES) {
      const out = teamShortName(n);
      if (out === n) continue;
      tally.set(out, (tally.get(out) ?? 0) + 1);
    }
    const big = [...tally.entries()].filter(([, c]) => c >= 9).map(([w]) => w).sort();
    expect(big).toEqual([
      "Bears", "Bulldogs", "Eagles", "Garcia", "Hawks", "Knights", "Lions",
      "Panthers", "Rodriguez", "Silva", "Spartans", "Tigers", "Wildcats",
    ]);
  });
});

// ───────────────────────────────────────────────────────────────────────────
// THE ABBREVIATION CLAUSE — the half that ships almost nothing today
// ───────────────────────────────────────────────────────────────────────────

describe("UX-1065: the abbreviation clause is symmetric or absent", () => {
  it("both sides carrying one uses both (1 of 120 live events)", () => {
    const pair = teamShortNames(
      { name: "Ipswich Town", abbreviation: "IPS" },
      { name: "Liverpool FC", abbreviation: "LIV" },
    );
    expect(pair).toEqual({ home: "IPS", away: "LIV" });
  });

  it("one side alone never produces a mixed pair (7 of 120 live events)", () => {
    const pair = teamShortNames(
      { name: "Ipswich Town", abbreviation: "IPS" },
      { name: "Sheffield Wednesday" },
    );
    expect(pair.home).not.toBe("IPS");
    expect(pair).toEqual({ home: "Ipswich Town", away: "Wednesday" });
  });
});

// ───────────────────────────────────────────────────────────────────────────
// RENDERED MARKUP — the claim is about the page, not about the helper
// ───────────────────────────────────────────────────────────────────────────

function textOf(markup: string): string {
  return markup.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
}

/**
 * The winner label is the content of the one span that ends in " won".
 * Positive extraction rather than a substring search (ux/1023's lesson #5), and
 * it throws rather than returning a wrong row if the card stops emitting
 * exactly one such span.
 */
function winnerLabelOf(markup: string): string {
  const hits = [...markup.matchAll(/>([^<>]*?)\s+won<\/span>/g)].map((m) => m[1].trim());
  if (hits.length !== 1) {
    throw new Error(`expected exactly 1 winner label, found ${hits.length}: ${JSON.stringify(hits)}`);
  }
  return hits[0];
}

describe("UX-1065: the rendered sentence", () => {
  it("a settled duel names the winner, and never says FC won", () => {
    const { DuelKernel } = require("@/components/discover/kernels/DuelKernel");
    const markup = renderToStaticMarkup(
      React.createElement(DuelKernel, {
        state: "settled",
        awayTeam: "Hartlepool United FC",
        homeTeam: "Altrincham FC",
        awayScore: 0,
        homeScore: 2,
        categorySlug: "soccer",
        categoryLabel: "Soccer",
        categoryEmoji: "*",
      }),
    );
    const text = textOf(markup);
    expect(text).toContain("Altrincham FC won");
    expect(text).not.toContain("FC won FC");
    // NOTE the loose form `/(^|\s)FC won/` is UNSATISFIABLE here — the correct
    // sentence "Altrincham FC won" legitimately contains " FC won". The claim is
    // about the WINNER LABEL, so it is asserted as an equality on that label
    // rather than as a substring search over the whole card.
    expect(winnerLabelOf(markup)).toBe("Altrincham FC");
  });

  it("the crest fallback gives two DIFFERENT letters for an FC-vs-FC card", () => {
    const { DuelKernel } = require("@/components/discover/kernels/DuelKernel");
    const markup = renderToStaticMarkup(
      React.createElement(DuelKernel, {
        state: "pre",
        awayTeam: "Hartlepool United FC",
        homeTeam: "Altrincham FC",
        categorySlug: "soccer",
        categoryLabel: "Soccer",
        categoryEmoji: "*",
      }),
    );
    expect(markup).toContain(">HAR<");
    expect(markup).toContain(">ALT<");
    expect(markup).not.toContain(">FC<");
  });

  it("CONTROL the crest fallback is unchanged for a nickname team", () => {
    const { DuelKernel } = require("@/components/discover/kernels/DuelKernel");
    const markup = renderToStaticMarkup(
      React.createElement(DuelKernel, {
        state: "pre",
        awayTeam: "Boston Celtics",
        homeTeam: "Los Angeles Lakers",
        categorySlug: "basketball",
        categoryLabel: "Basketball",
        categoryEmoji: "*",
      }),
    );
    expect(markup).toContain(">LAK<");
    expect(markup).toContain(">CEL<");
  });

  it("CONTROL a settled duel between nickname teams is unchanged", () => {
    const { DuelKernel } = require("@/components/discover/kernels/DuelKernel");
    const markup = renderToStaticMarkup(
      React.createElement(DuelKernel, {
        state: "settled",
        awayTeam: "Auburn Tigers",
        homeTeam: "Georgia Bulldogs",
        awayScore: 10,
        homeScore: 21,
        categorySlug: "football",
        categoryLabel: "Football",
        categoryEmoji: "*",
      }),
    );
    expect(textOf(markup)).toContain("Bulldogs won");
  });
});

// ───────────────────────────────────────────────────────────────────────────
// WIRING — reverting the hero and the shared card produced ZERO red without
// this section, so the two highest-traffic surfaces in the ship were unguarded
// by everything above. Source-level because `app/events/[id]/page.tsx` is a
// client page this harness cannot render (it early-returns on a loading state
// before the hero exists).
//
// These scans STRIP COMMENTS FIRST. The fix's own explanatory comment quotes
// `split(" ").pop()` verbatim to say what was wrong, so a naive
// `not.toContain('split(" ").pop()')` is RED ON THE FIX, and the better the
// comment the likelier it trips (ux/1038's lesson #3). Verified: page.tsx line
// 605 is exactly that comment.
// ───────────────────────────────────────────────────────────────────────────

describe("UX-1065 wiring: the display sites read the helper", () => {
  it("the reported hero no longer shortens either side itself", () => {
    const src = sourceWithoutComments("app/events/[id]/page.tsx");
    expect(src).toContain("heroShortNames");
    expect(src).not.toMatch(/event\.home_team\.split\(" "\)\.pop\(\)/);
    expect(src).not.toMatch(/event\.away_team\.split\(" "\)\.pop\(\)/);
  });

  it("the comment-stripper is real: the raw file DOES still contain the phrase", () => {
    // If this goes red the stripper has become vacuous and the test above would
    // be passing for the wrong reason.
    const raw = readFileSync(join(process.cwd(), "app/events/[id]/page.tsx"), "utf8");
    expect(raw).toContain('split(" ").pop()');
    expect(sourceWithoutComments("app/events/[id]/page.tsx")).not.toContain('split(" ").pop()');
  });

  it("the shared EventCard reads the helper", () => {
    const src = sourceWithoutComments("components/EventCard.tsx");
    expect(src).toContain("teamShortNames(");
    expect(src).not.toMatch(/event\.home_team\.split\(" "\)\.pop\(\)/);
  });

  it("CONTROL the four MATCHING call sites are deliberately untouched", () => {
    // These decide what MATCHES, not what renders. If a later session retires
    // them as the issue suggests, this goes red and says so on purpose.
    expect(sourceWithoutComments("components/PlayerPropsGrid.tsx")).toContain(
      'home_team.split(" ").pop()',
    );
    expect(sourceWithoutComments("lib/sportCategories.ts")).toContain(
      'golfer.split(" ").pop()',
    );
  });
});
