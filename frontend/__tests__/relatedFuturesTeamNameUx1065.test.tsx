/**
 * UX-1065 (#2936) — CERT-908 REPAIR: THE BIGGER PICTURE SECTION IS A TEAM NAME.
 *
 * ═══ WHY THIS FILE EXISTS ═══
 *
 * Round one of #2936 shipped `lib/teamShortName.ts` and wired it into the event
 * hero, `EventCard`, the Discover card and `DuelKernel`. CERT-908 withheld the
 * token because the reported page — `/events/15291104` — mounts `RelatedFutures`
 * as its "Bigger Picture" section, and that component still derived
 *
 *     const homeShort = homeTeam.split(" ").pop() || homeTeam;
 *
 * and rendered the result as the two-column team heading. So the page the issue
 * reports still printed `Town` against `Liverpool`, which is the issue's direct
 * acceptance criterion. The fix reached four surfaces and missed the fifth.
 *
 * ═══ WHY ROUND ONE'S GUARDS COULD NOT SEE IT ═══
 *
 * Every assertion in `teamShortNameUx1065.test.tsx` is on the pure helper or on
 * the four wired components. A correct helper and an unwired call site are
 * indistinguishable to it — the helper was never wrong. This file therefore
 * asserts on RENDERED MARKUP from `RelatedFutures` itself, which is the only
 * thing that can tell the two apart.
 *
 * ═══ WHAT IS DELIBERATELY NOT TOUCHED ═══
 *
 * `RelatedFutures` holds fourteen last-word derivations. Three of them are
 * MATCHING, not display, and rewriting them would change what matches:
 *
 *     :171  matchPlayerToBoxScore  last-name match against an ESPN box score
 *     :501  extractOpponent        regex-strips the team name out of a market
 *     :553  GameMarketsGrid        lowercased `includes()` filter predicate
 *
 * `:501` spells the derivation `teamWords[teamWords.length - 1]`, so a grep for
 * `split(" ").pop()` does not find it at all. The control at the bottom of this
 * file pins all three, and goes red if a later session "finishes the job".
 *
 * ═══ ARMS THIS HARNESS CANNOT EXERCISE ═══
 *
 * `teamShortNames` has an abbreviation-rescue arm. `RelatedFutures` receives
 * `homeTeam` / `awayTeam` as bare strings and no abbreviation reaches it, so
 * that arm is UNREACHABLE on this surface and is not asserted here. It is
 * covered by the helper's own suite. Only the club-word arm and the
 * pair-collision arm are live on this component.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import RelatedFutures from "@/components/RelatedFutures";
import type { RelatedFuturesResponse } from "@/lib/types";

// ── The one SWR call the component makes. Empty futures on purpose: the two
// ── column headings are gated on `seasonCount > 0`, which the standings props
// ── below satisfy on their own, so nothing here depends on market fixtures.
const payload = (home: string, away: string): RelatedFuturesResponse => ({
  event_id: 15291104,
  home_team: home,
  away_team: away,
  home_team_futures: [],
  away_team_futures: [],
  series_markets: [],
  total_count: 0,
  summary: null,
  event_status: "scheduled",
  box_score: null,
  league_context: null,
});

let swrPayload: RelatedFuturesResponse = payload("Ipswich Town", "Liverpool");

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({
    data: swrPayload,
    error: undefined,
    isLoading: false,
    mutate: () => undefined,
  }),
}));

const STANDINGS = { wins: 3, losses: 2 };

function renderFor(home: string, away: string): string {
  swrPayload = payload(home, away);
  return renderToStaticMarkup(
    React.createElement(RelatedFutures, {
      eventId: 15291104,
      homeTeam: home,
      awayTeam: away,
      homeStandings: STANDINGS,
      awayStandings: { wins: 5, losses: 1 },
    }),
  );
}

/**
 * The two team headings, as EXACT strings.
 *
 * Anchored on the rendered class rather than on a `data-` attribute, and that
 * is deliberate: this class exists on the PARENT too, so the extractor selects
 * the same population in both arms. A marker added by this repair would match
 * nothing before the repair and the test would pass vacuously on the bug
 * (ux/1040's lesson #3).
 *
 * A whole-document `toContain("Town")` is worse than useless here — the CORRECT
 * output `Ipswich Town` contains it. Every claim below is an equality on an
 * extracted heading.
 */
function teamHeadings(html: string): string[] {
  const re =
    /<div class="font-semibold text-lg leading-tight">([^<]*)<\/div>/g;
  const found: string[] = [];
  let m: RegExpExecArray | null;
  while ((m = re.exec(html)) !== null) found.push(m[1]);

  // The extractor reports its own yield. The component renders exactly two of
  // these — home and away — so a silent under-read cannot be mistaken for a
  // clean page (ux/1040's lesson #4).
  if (found.length !== 2) {
    throw new Error(
      `expected 2 team headings, extracted ${found.length}: ${JSON.stringify(found)}`,
    );
  }
  return found;
}

describe("UX-1065 / CERT-908 — RelatedFutures renders a team's NAME", () => {
  it("the reported fixture: Ipswich Town is never headed 'Town'", () => {
    const [home, away] = teamHeadings(renderFor("Ipswich Town", "Liverpool"));

    // The exact defect CERT-908 blocked on.
    expect(home).not.toBe("Town");
    expect(home).toBe("Ipswich Town");

    // The other side is a single word and must be untouched.
    expect(away).toBe("Liverpool");
  });

  it("CONTROL: an American <place> <mascot> pair still shortens", () => {
    const [home, away] = teamHeadings(
      renderFor("Los Angeles Lakers", "Boston Celtics"),
    );

    // This is the 90% of the population `.pop()` gets RIGHT, and the repair
    // must not cost it. If this goes red the fix has become "never shorten".
    expect(home).toBe("Lakers");
    expect(away).toBe("Celtics");
  });

  it("CONTROL: the club word is the discriminator, not the sport", () => {
    // Sheffield Wednesday is an English club whose last word IS its
    // distinctive name, so it must still shorten — asymmetrically, against a
    // side that cannot. Proves the rule keys on the WORD, not on "is soccer".
    const [home, away] = teamHeadings(
      renderFor("Bradford City", "Sheffield Wednesday"),
    );
    expect(home).toBe("Bradford City");
    expect(away).toBe("Wednesday");
  });

  it("two clubs that shorten to the same word both keep their full names", () => {
    // The pair-collision arm. One side alone cannot see this: each of these
    // would independently shorten to a two-letter token, and the card would
    // read "FC" against "FC".
    const [home, away] = teamHeadings(
      renderFor("Austin FC", "Charlotte FC"),
    );
    expect(home).toBe("Austin FC");
    expect(away).toBe("Charlotte FC");
    expect(home).not.toBe(away);
  });

  it("a squad qualifier is not a team name either", () => {
    const [home, away] = teamHeadings(renderFor("Argentina W", "Brazil W"));
    expect(home).toBe("Argentina W");
    expect(away).toBe("Brazil W");
  });
});

describe("UX-1065 / CERT-908 — the MATCHING derivations stay untouched", () => {
  const source = require("fs").readFileSync(
    require("path").join(__dirname, "..", "components", "RelatedFutures.tsx"),
    "utf8",
  ) as string;

  /**
   * Strip comments before scanning. This file's own prose quotes the defective
   * spelling to explain it, and so does the repair's comment in the component —
   * a naive source ban is RED ON THE FIX for that reason alone (ux/1038's
   * lesson #3, and ux/1065 hit it once already).
   */
  const code = source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "");

  it("the stripper did not go vacuous", () => {
    // If the comment stripper ate the file, every ban below would pass for
    // entirely the wrong reason. The RAW source must still contain the phrase.
    expect(source).toContain('split(" ").pop()');
    expect(code.length).toBeGreaterThan(source.length * 0.5);
  });

  it("exactly three last-word derivations remain, and all three are matching", () => {
    const popCalls = code.match(/split\(" "\)\.pop\(\)/g) ?? [];
    const indexCalls = code.match(/teamWords\[teamWords\.length - 1\]/g) ?? [];

    // :171 player box score · :553 lowercased filter predicate
    expect(popCalls).toHaveLength(2);
    // :501 extractOpponent — the spelling a `.pop()` grep cannot see
    expect(indexCalls).toHaveLength(1);

    // Each survivor is a matching use, pinned by the shape that makes it one.
    expect(code).toContain('const lastName = norm.split(" ").pop() || "";');
    expect(code).toContain(
      'const teamShort = teamName.split(" ").pop()?.toLowerCase() || "";',
    );
    expect(code).toContain(
      "const shortName = teamWords[teamWords.length - 1] || teamName;",
    );
  });

  it("every display derivation goes through the helper", () => {
    expect(code).toContain(
      'import { teamShortName, teamShortNames } from "@/lib/teamShortName";',
    );
    // Six display sites: title odds, playoff cards, season outlook, the dead
    // MatchupGrid, trade destinations, and the main two-column card.
    const pairCalls = code.match(/teamShortNames\(/g) ?? [];
    expect(pairCalls).toHaveLength(5);
    expect(code).toContain("const shortName = teamShortName(teamName);");
  });

  it("WinTotalsGauge's shortName prop has no default", () => {
    // The two gauges render side by side, so the compact name is a decision
    // about the PAIR and only the parent can make it. A default would let the
    // next call site silently re-acquire `.pop()` with every test still green
    // (ux/1010's lesson #3).
    expect(code).toMatch(/shortName: string;/);

    // Scoped to WinTotalsGauge's own parameter list. A repo-wide ban on
    // `shortName =` is the wrong claim: other components legitimately declare
    // `const shortName = ...` as a local, and two call sites pass the JSX prop
    // `shortName={homeShort}`. The claim is only that THIS destructuring has no
    // fallback.
    const start = code.indexOf("function WinTotalsGauge({");
    expect(start).toBeGreaterThan(-1);
    const params = code.slice(start, code.indexOf("}) {", start));
    expect(params).toMatch(/^\s*shortName,\s*$/m);
    expect(params).not.toMatch(/shortName\s*=/);
  });
});
