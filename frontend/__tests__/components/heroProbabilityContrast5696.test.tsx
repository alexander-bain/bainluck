/**
 * #5696 — THE BIGGEST NUMBER ON THE SITE, PAINTED WHITE ON A WHITE CARD.
 *
 * ═══ WHAT A READER SAW ═══
 *
 * `https://bainluck.com/events/15297678` — Everton at Tottenham Hotspur, live,
 * 76', production, 390px, 2026-09-12. The hero read:
 *
 *     – 37 %
 *
 * Tottenham's 63% was not there. Not blanked, not marked unknown: a dangling
 * en-dash and one number, so a reader saw a single 37% and could not tell whose
 * it was. `Opened 64% – 36%` two lines below printed both sides correctly.
 *
 * The payload was fine (`hero_probability: 0.6286`). Spurs' stored
 * `primary_color` is `#ffffff` and `--surface-card` is `#FFFFFF`. Computed
 * style of the span, measured in the browser: `rgb(255, 255, 255)`, opacity 1,
 * on screen at x=101.
 *
 * ═══ WHY THIS IS #5165'S BUG AND NOT A NEW ONE ═══
 *
 * #5165 shipped `teamTextColor` — the WCAG 3:1 floor against the card surface —
 * for exactly this class, and it guarded four call sites, all in
 * `GamePlayCard`. A census at the time of this fix found the helper adopted in
 * ONE component while 30 team-coloured TEXT sites across 11 other files still
 * took the raw brand colour. This ship converts them.
 *
 * So the interesting assertion here is not "is the hero fixed" — it is the
 * SOURCE SCAN at the bottom. A fix to one component cannot stop the twelfth
 * site being written raw next week; only a tree-level scan can, and the whole
 * history of this class is one implementation of the rule per surface.
 *
 * ═══ WHY EVERY ASSERTION READS A COLOUR AND NEVER THE TEXT ═══
 *
 * Every character was in the DOM, correct, in order, and readable to a screen
 * reader. `toHaveTextContent("63")` passes on the bug. Two tests below assert
 * the number IS present at the same time as the colour, deliberately: a guard
 * for this class that checks text is not a weak guard, it is a guard that
 * cannot fail.
 *
 * ═══ WHY THE AWAY FALLBACK MOVED ═══
 *
 * It was `#94A3B8` (slate-400), which is **2.56:1** against the card — below
 * the very floor that now routes to it. Leaving it would have traded 1.00:1 for
 * 2.56:1 and made the guard circular, which is the failure mode #5165's own
 * suite names. `--text-secondary` (#6B7280, 4.83:1) is what #5165 chose for the
 * same reason, and is still visibly the quieter of the two, so the home/away
 * hierarchy the slate was carrying survives.
 */

import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "fs";
import { join } from "path";
import EventHeroProbabilityPair from "../../components/EventHeroProbabilityPair";
import {
  MIN_TEXT_CONTRAST_VS_SURFACE,
  contrastVsCardSurface,
} from "../../lib/teamColors";

const SPURS_WHITE = "#ffffff";
const EVERTON_BLUE = "#003399";
const HOME_FALLBACK = "#111827";
const AWAY_FALLBACK = "var(--text-secondary)";
/** What the away side used to fall back to. 2.56:1 — the reason it moved. */
const OLD_AWAY_FALLBACK = "#94A3B8";

function hero(homeColor?: string, awayColor?: string) {
  return renderToStaticMarkup(
    <EventHeroProbabilityPair
      homeProb={0.6286}
      awayProb={0.3714}
      homePct={63}
      awayPct={37}
      homeColor={homeColor}
      awayColor={awayColor}
    />,
  );
}

describe("#5696 the event hero never paints a probability in a colour you cannot read", () => {
  test("the reported page: Spurs' white 63% is painted in the fallback, not in white", () => {
    const html = hero(SPURS_WHITE, EVERTON_BLUE);
    expect(html).not.toContain(`color:${SPURS_WHITE}`);
    expect(html).toContain(`color:${HOME_FALLBACK}`);
  });

  test("CONTROL: the 63 was ALWAYS there — this is why no text assertion could catch it", () => {
    // Green on BOTH sides of the change, and the most important row in the
    // file. The defect was never a missing number; it was a number the same
    // colour as the paper.
    const html = hero(SPURS_WHITE, EVERTON_BLUE);
    expect(html).toContain(">63<");
    expect(html).toContain(">37<");
  });

  test("CONTROL: a dark club colour is still painted — the floor must not grey the league out", () => {
    // Without this, a fix that simply deleted the team colouring from the hero
    // would pass every assertion above.
    const html = hero(EVERTON_BLUE, EVERTON_BLUE);
    expect(html).toContain(`color:${EVERTON_BLUE}`);
  });

  test("CONTROL: a club with no colour at all renders exactly as before the floor", () => {
    const html = hero(undefined, undefined);
    expect(html).toContain(`color:${HOME_FALLBACK}`);
    expect(html).toContain(`color:${AWAY_FALLBACK}`);
  });

  test("the AWAY side is floored too — fixing only the home half leaves the hero half-lying", () => {
    const html = hero(EVERTON_BLUE, SPURS_WHITE);
    expect(html).not.toContain(`color:${SPURS_WHITE}`);
    expect(html).toContain(`color:${AWAY_FALLBACK}`);
    // The home side keeps its readable colour on the same render, so this is
    // not passing merely because nothing is coloured.
    expect(html).toContain(`color:${EVERTON_BLUE}`);
  });

  test("two white clubs: neither number is white, and the pair is still told apart", () => {
    const html = hero(SPURS_WHITE, SPURS_WHITE);
    expect(html).not.toContain(`color:${SPURS_WHITE}`);
    expect(html).toContain(`color:${HOME_FALLBACK}`);
    expect(html).toContain(`color:${AWAY_FALLBACK}`);
    expect(HOME_FALLBACK).not.toBe(AWAY_FALLBACK);
  });

  test("BOTH fallbacks clear the floor — otherwise the fix swaps one unreadable colour for another", () => {
    // The home fallback, and the away fallback's resolved value. If either ever
    // fails, the floor routes to a colour that cannot be read either and the
    // whole guard is circular.
    for (const hex of [HOME_FALLBACK, "#6B7280" /* --text-secondary */]) {
      const ratio = contrastVsCardSurface(hex);
      expect(ratio).not.toBeNull();
      expect(ratio!).toBeGreaterThanOrEqual(MIN_TEXT_CONTRAST_VS_SURFACE);
    }
  });

  test("the away fallback moved BECAUSE the old one failed the floor", () => {
    // Pins the reason rather than the edit: slate-400 is 2.56:1. If someone
    // restores it, this fails and says why.
    const old = contrastVsCardSurface(OLD_AWAY_FALLBACK)!;
    expect(old).toBeLessThan(MIN_TEXT_CONTRAST_VS_SURFACE);
    expect(old).toBeCloseTo(2.56, 2);
  });
});

/**
 * ═══ THE SCAN THAT IS ACTUALLY LOAD-BEARING ═══
 *
 * One implementation of this rule per surface is how the class survived #5165.
 * The hero test above protects the hero; this protects the tree.
 *
 * It reads every `style={{ ... color: X ... }}` whose value mentions a team
 * colour and asserts the value goes through `teamTextColor`. FILLS are
 * deliberately not in scope — `backgroundColor`, `borderColor`, `stroke` and
 * gradients are what a brand colour is FOR, and flooring them would be a
 * redesign. That is #5165's sentence: a brand colour is a fill, it is not a
 * text colour.
 *
 * `components/discover/EventCard.tsx` is NOT in the list, deliberately. Its two
 * percents take their colour from `probabilityBarPair`, which already applies
 * its own surface floor (`MIN_SURFACE_CONTRAST = 1.5`, chosen by replay and
 * measured on the COMPOSITED pixel: 1.5 rescues 60 of 1,445 coloured teams,
 * 3:1 would override 256). So a white club is already rescued there — the
 * defect does not reach that card. Raising it from "visible at all" to the text
 * floor would re-brand ~196 teams on Discover, which is a design change with a
 * measured price and belongs to whoever owns that surface, not to a p1 bug fix.
 */
describe("#5696 no surface paints team-coloured TEXT without the floor", () => {
  /** Every file the census found a team-coloured text site in. */
  const FILES = [
    "components/EventHeroProbabilityPair.tsx",
    "components/GamePlayCard.tsx",
    "components/RelatedFutures.tsx",
    "components/SeriesProbability.tsx",
    "components/OddsChart.tsx",
    "components/ScoreDifferentialChart.tsx",
    "components/TeamGameCards.tsx",
    "components/TeamSeasonJourney.tsx",
    "components/TeamChampionshipPath.tsx",
    "components/discover/kernels/DuelKernel.tsx",
    "app/events/[id]/page.tsx",
    "app/events/[id]/opengraph-image.tsx",
    "app/sport/[sport]/[league]/team/[team]/page.tsx",
  ];

  /**
   * A value that names a team colour. Matches the names the codebase actually
   * uses — `teamColor`, `homeColor`, `hColor`, `primary_color` — and the
   * derived `*TextColor` consts that ARE the floored form.
   */
  const TEAM_COLOUR_VALUE =
    /\b(?:[a-zA-Z]*[Tt]eamColor|home[Cc]olor|away[Cc]olor|[ha]Color|primary_color)\b/;

  /** `color:` inside a style object, capturing the value up to `,` or `}`. */
  const COLOR_PROP = /(?<![a-zA-Z-])color: *([^,}\n]+)/g;

  /**
   * THE SCAN HAS TO FOLLOW ONE ALIAS, AND THIS IS NOT A REFINEMENT — IT IS THE
   * WHOLE BUG.
   *
   * The line #5696 was filed about is `style={{ color: home }}`, and `home` is
   * `const home = homeColor || "#111827"`. A scan that only matches values
   * NAMING a team colour reads `home`, sees no team colour in it, and passes —
   * on the exact defect it was written for. So a bare identifier is resolved
   * back to its `const` in the same file and that definition is tested instead.
   * The CONTROL below drives the real pre-fix text through this and requires it
   * flagged; without the resolution step that control fails, which is how the
   * hole was found.
   */
  function rawTeamColourTextSites(src: string): string[] {
    const consts = new Map<string, string>();
    for (const m of src.matchAll(/\bconst +([A-Za-z_$][\w$]*) *= *([^;\n]+)/g)) {
      consts.set(m[1], m[2]);
    }

    const raw: string[] = [];
    for (const m of src.matchAll(COLOR_PROP)) {
      const value = m[1];
      // Resolve `color: home` / `color: homeTextColor` to what that const IS.
      const bare = value.trim().match(/^([A-Za-z_$][\w$]*)\b/);
      const resolved =
        bare && consts.has(bare[1]) ? `${value} ⟵ ${consts.get(bare[1])}` : value;

      if (!TEAM_COLOUR_VALUE.test(resolved)) continue;
      if (resolved.includes("teamTextColor")) continue;
      raw.push(value.trim());
    }
    return raw;
  }

  test.each(FILES)("%s routes every team-coloured text value through teamTextColor", (rel) => {
    const src = readFileSync(join(process.cwd(), rel), "utf8");
    expect(rawTeamColourTextSites(src)).toEqual([]);
  });

  test("CONTROL: the scan flags the ACTUAL pre-fix hero line, one alias deep", () => {
    // A scan that matches nothing passes forever. This is the real text of
    // `EventHeroProbabilityPair` before this ship, and both shapes — the alias
    // and the direct reference — have to be flagged.
    const preFix =
      'const home = homeColor || "#111827";\n' +
      '  const away = awayColor || "#94A3B8";\n' +
      "        style={{ color: home }}\n" +
      "        style={{ color: away }}\n" +
      "        style={{ color: teamColor }}";
    expect(rawTeamColourTextSites(preFix)).toEqual(["home", "away", "teamColor"]);
  });

  test("CONTROL: the scan clears the POST-fix hero line — it is not flagging everything", () => {
    const postFix =
      'const home = teamTextColor(homeColor) || "#111827";\n' +
      "        style={{ color: home }}";
    expect(rawTeamColourTextSites(postFix)).toEqual([]);
  });

  test("CONTROL: an alias that only LOOKS floored is still flagged", () => {
    // A const called `homeTextColor` that is just the raw colour must not buy
    // an exemption from its own name.
    const liar =
      'const homeTextColor = homeColor || "#111827";\n' +
      "        style={{ color: homeTextColor }}";
    expect(rawTeamColourTextSites(liar)).toEqual(["homeTextColor"]);
  });

  test("CONTROL: the scan does NOT flag a fill — flooring those would be a redesign", () => {
    const fills =
      "backgroundColor: teamColor,\n borderColor: homeColor,\n background: `${teamColor}15`";
    expect(rawTeamColourTextSites(fills)).toEqual([]);
  });
});
