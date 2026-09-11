/**
 * #5165 — a brand colour is a fill, not a text colour, and 44 teams' numbers
 * were invisible because of it. Plus #2936's ninth call site, in the same strip.
 *
 * ═══ WHAT A READER SAW ═══
 *
 * `https://bainluck.com/events/15298474` — Vancouver Whitecaps FC 3, LA Galaxy
 * 0, Final. The readout under the win-probability chart, photographed at 390px
 * on 2026-09-11 (`artifacts/ux-1191/AFTER-5135-15298474-settled-hero-390.png`):
 *
 *     —    [VAN crest]  -  0 [LA crest]    FC    — Galaxy 0%
 *
 * The home score `3` is not there. The home probability `100%` is not there.
 * The club is called "FC". A 3–0 win reads as `- 0`.
 *
 * ═══ WHY IT SURVIVED EVERY TEST WE ALREADY HAD ═══
 *
 * `GET /api/events/15298474` serves `home_score: 3` and
 * `home_team_data.primary_color: '#ffffff'`. The card painted the score in that
 * colour, and `--surface-card` is `#FFFFFF` — the site is light-mode only.
 *
 * So every character was in the DOM, correct, in the right order, and available
 * to a screen reader. `toHaveTextContent("3")` passes. A text snapshot passes.
 * An accessibility-tree assertion passes. **Only the pixels were wrong.** That
 * is the entire reason the assertions below read the RESOLVED `color`, and why
 * two of them deliberately assert that the text IS present at the same time — a
 * guard for this class that checks text is not a weak guard, it is a guard that
 * cannot fail.
 *
 * ═══ WHY A STANDARD, NOT A TUNED CUTOFF ═══
 *
 * Measured over production `teams` (1,452 rows with a colour, 644 distinct,
 * `truncated: false` — a first pass at `limit: 400` came back truncated and
 * undercounted, and was discarded). The contrast distribution has NO natural
 * gap: 1.00:1 (`#ffffff`, 26 teams) → the yellows (`#ffff00` 1.07, `#FACF08`
 * 1.50) → golds (`#fdb927` 1.73) → pale blues and tans, continuously. Any
 * hand-picked number would have been a number someone picked, so the floor is
 * WCAG's for UI text and the alternatives were costed rather than guessed:
 * 1.5:1 → 39 teams, 2:1 → 83, **3:1 → 146 (chosen)**, 4.5:1 → 240.
 *
 * A recoloured team is not degraded: it falls back to `--text-secondary`, which
 * is already what a team with no stored colour gets on this same card.
 *
 * ═══ RED-FIRST ═══
 *
 * Measured against `f57121f5` rather than reasoned: **8 failed, 4 passed of 12**.
 * The four green-on-both-sides rows are the controls that matter:
 *
 *   1. **the score text is present before AND after** — the row that proves a
 *      text-based test could never have caught this;
 *   2. a dark team colour is still painted, so a "fix" that simply deleted the
 *      team colouring would fail here;
 *   3. a team with no colour at all renders exactly as before;
 *   4. `LA Galaxy` still shortens to `Galaxy` — green on the parent because
 *      `split(" ").pop()` happens to agree there, which is the point: #4250's
 *      guard refuses only a NON-distinctive trailing token, and this fix must
 *      not become "always print the full name".
 */

import { renderToStaticMarkup } from "react-dom/server";
import GamePlayCard from "../../components/GamePlayCard";
import {
  MIN_TEXT_CONTRAST_VS_SURFACE,
  contrastVsCardSurface,
  teamTextColor,
} from "../../lib/teamColors";
import type { ActiveChartPoint } from "../../lib/types";

const WHITECAPS_WHITE = "#ffffff";
const GALAXY_NAVY = "#00235d";

const point: ActiveChartPoint = {
  timestamp: "2026-09-10T04:45:00Z",
  homeProb: 1,
  awayProb: 0,
  homeScore: 3,
  awayScore: 0,
  period: null,
  clock: null,
  scoringPlay: null,
};

function render(homeColor?: string, awayColor?: string) {
  return renderToStaticMarkup(
    <GamePlayCard
      activePoint={null}
      lastPoint={point}
      homeTeam="Vancouver Whitecaps FC"
      awayTeam="LA Galaxy"
      homeTeamColor={homeColor}
      awayTeamColor={awayColor}
    />,
  );
}

describe("#5165 the readout never paints a number in a colour you cannot read", () => {
  // ---- the helper ----

  test("a colour identical to the card surface has a contrast ratio of exactly 1", () => {
    expect(contrastVsCardSurface(WHITECAPS_WHITE)).toBeCloseTo(1, 5);
  });

  test("the invisible colours are refused and the readable ones are kept", () => {
    expect(teamTextColor(WHITECAPS_WHITE)).toBeUndefined();
    expect(teamTextColor("#ffff00")).toBeUndefined(); // 1.07:1, five teams
    expect(teamTextColor(GALAXY_NAVY)).toBe(GALAXY_NAVY);
    expect(teamTextColor("#990000")).toBe("#990000"); // 14 teams, comfortably dark
  });

  test("an absent or unparseable colour returns undefined, so the caller's `||` still decides", () => {
    // A floor added UNDER existing behaviour, not a replacement for it.
    expect(teamTextColor(undefined)).toBeUndefined();
    expect(teamTextColor(null)).toBeUndefined();
    expect(teamTextColor("")).toBeUndefined();
    expect(teamTextColor("not-a-colour")).toBeUndefined();
    expect(teamTextColor("#fff")).toBeUndefined(); // 3-char form is not parsed by hexToRgb
  });

  test("the FALLBACK itself clears the floor — otherwise the fix swaps one unreadable colour for another", () => {
    // `--text-secondary` is #6B7280. If this ever fails, the fallback has been
    // changed to something that cannot be read either and the whole guard is
    // circular.
    const ratio = contrastVsCardSurface("#6B7280");
    expect(ratio).not.toBeNull();
    expect(ratio!).toBeGreaterThanOrEqual(MIN_TEXT_CONTRAST_VS_SURFACE);
  });

  // ---- the rendered card ----

  test("the Whitecaps' white score is painted in the fallback, not in white", () => {
    const html = render(WHITECAPS_WHITE, GALAXY_NAVY);
    expect(html).toContain("color:var(--text-secondary)");
    expect(html).not.toContain(`color:${WHITECAPS_WHITE}`);
  });

  test("CONTROL: the text was ALWAYS there — this is why no text assertion could catch it", () => {
    // Green on BOTH sides of the change, and the most important row in the file.
    // The defect was never a missing number; it was a number the same colour as
    // the paper. A guard asserting `toHaveTextContent("3")` passes on the bug.
    const html = render(WHITECAPS_WHITE, GALAXY_NAVY);
    expect(html).toContain(">3<");
    expect(html).toContain(">0<");
  });

  test("CONTROL: a dark team colour is still painted — the floor must not grey everyone out", () => {
    // Green on both sides. Without this, a fix that simply deleted the team
    // colouring would pass every assertion above.
    const html = render(GALAXY_NAVY, GALAXY_NAVY);
    expect(html).toContain(`color:${GALAXY_NAVY}`);
  });

  test("CONTROL: a team with no colour at all renders exactly as before", () => {
    // Green on both sides — the `|| "var(--text-secondary)"` path is untouched.
    const html = render(undefined, undefined);
    expect(html).toContain("color:var(--text-secondary)");
  });

  test("the probability is floored too, not just the score", () => {
    // Two separate call sites in the component, and the reported defect showed
    // BOTH: the score `3` and the winner's `100%` were each invisible. Fixing
    // only the score would leave half the strip lying.
    const html = render(WHITECAPS_WHITE, GALAXY_NAVY);
    expect(html).toContain("100%");
    expect(html).not.toContain(`color:${WHITECAPS_WHITE}`);
    // The away side keeps its readable colour on the same render, so this is not
    // passing merely because nothing is coloured.
    expect(html).toContain(`color:${GALAXY_NAVY}`);
  });
});

describe("#2936 the same strip names the club, not its last word", () => {
  test("the card no longer calls Vancouver Whitecaps FC 'FC'", () => {
    const html = render(GALAXY_NAVY, GALAXY_NAVY);
    expect(html).toContain("Vancouver Whitecaps FC");
    // The exact string the reader saw. `>FC<` rather than `FC` because the
    // correct name ENDS in that token — a negative assertion on the bare
    // substring would be red on the fix and green on the bug.
    expect(html).not.toContain(">FC<");
    expect(html).not.toContain("FC </span>");
  });

  test("the distinctive last word is still shortened — this is not 'always use the full name'", () => {
    // "LA Galaxy" -> "Galaxy" is correct and must survive; #4250's guard only
    // refuses a NON-distinctive trailing token like "FC", "United", "W".
    const html = render(GALAXY_NAVY, GALAXY_NAVY);
    expect(html).toContain("Galaxy");
    expect(html).not.toContain("LA Galaxy");
  });

  test("the pair is decided TOGETHER, so two clubs sharing a last word cannot collide", () => {
    // The contract `teamShortNames` exists for: calling the single-name helper
    // twice would render "FC — FC" for a pair whose last words match, which is
    // the collision the `FC (115 teams)` bucket in #2936 is made of.
    const html = renderToStaticMarkup(
      <GamePlayCard
        activePoint={null}
        lastPoint={point}
        homeTeam="Vancouver Whitecaps FC"
        awayTeam="Toronto FC"
        homeTeamColor={GALAXY_NAVY}
        awayTeamColor={GALAXY_NAVY}
      />,
    );
    expect(html).toContain("Vancouver Whitecaps FC");
    expect(html).toContain("Toronto FC");
    expect(html).not.toContain(">FC<");
  });
});
