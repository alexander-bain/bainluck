/**
 * #7780 — both grids agree which way is up for a column, or CI says so.
 *
 * THE BUG. The championship grid paints a 24h move green when it rises. That is
 * right for every column that is a rung toward something a club wants and
 * exactly backwards for `relegation`. Web shipped it, found it (#7745), and
 * fixed it in PR #7769 with `lib/gridColumnPolarity.ts`. `ChampionshipPathView`
 * carried the identical `trend > 0 ? .green : .red` and was not fixed with it —
 * the same two-surface drift #7759 was about, one card over.
 *
 * SO THIS GUARDS THE COUPLING. The adverse-key vocabulary is one fact about the
 * product and it now lives in two files; this requires them to be the same set,
 * pins the app's renderer to it, and pins the one arrangement that makes the
 * sibling renderer safe to leave alone.
 *
 * Each surface's BEHAVIOUR is asserted in its own runner: web's in its own unit
 * tests, iOS's in `GridRelegationPolarity7780Tests`. It lives in jest because
 * jest is a deploy gate here and the Swift target is not reachable from CI
 * (notice 10's iOS clause).
 */

import { readFileSync } from "fs";
import { join } from "path";

const REPO = join(__dirname, "../../..");
const WEB = join(REPO, "frontend/lib/gridColumnPolarity.ts");
const IOS = join(REPO, "ios/Bain Luck/Bain Luck/Utilities/GridColumnPolarity.swift");
const IOS_GRID = join(REPO, "ios/Bain Luck/Bain Luck/Components/ChampionshipPathView.swift");
const IOS_LADDER = join(REPO, "ios/Bain Luck/Bain Luck/Components/LadderCardView.swift");
const CONFIGS = join(REPO, "backend/app/config/league_configs.py");

/**
 * Both files name `relegation` in their PROSE — each header explains the bug
 * using the key — so a raw scan would read the explanation as the declaration.
 */
function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^[ \t]*\/\/.*$/gm, "")
    .replace(/^[ \t]*#.*$/gm, "");
}

function read(file: string): string {
  try {
    return readFileSync(file, "utf8");
  } catch (err) {
    throw new Error(
      `#7780 polarity parity gate could not read ${file}: ${String(err)}. ` +
        `If the file moved, update this guard — do not delete the check.`,
    );
  }
}

/** The quoted members of a `new Set([...])` / a Swift `Set<String> = [...]`. */
function setMembers(source: string, declaration: string): string[] {
  const at = source.indexOf(declaration);
  if (at === -1) throw new Error(`\`${declaration}\` not found`);
  // Anchor on the `=`: the Swift type annotation `Set<String>` carries no
  // bracket, but anchoring on the name would be one refactor away from picking
  // up a generic parameter, and an extractor that returns [] reads as agreement.
  const assign = source.indexOf("=", at);
  const open = source.indexOf("[", assign);
  const close = source.indexOf("]", open);
  if (assign === -1 || open === -1 || close === -1) {
    throw new Error(`\`${declaration}\` is not an assigned bracket literal`);
  }
  return [...source.slice(open + 1, close).matchAll(/"([^"]+)"/g)].map((m) => m[1]).sort();
}

const webKeys = setMembers(stripComments(read(WEB)), "export const ADVERSE_COLUMN_KEYS");
const iosKeys = setMembers(stripComments(read(IOS)), "static let adverseColumnKeys");
const iosGrid = stripComments(read(IOS_GRID));

describe("#7780 — web and iOS agree which columns are adverse", () => {
  /**
   * The extractors are the load-bearing part: one that silently returns []
   * makes the comparison below pass on two empty sets.
   */
  it("reads a real declaration out of each surface", () => {
    expect(webKeys).toHaveLength(1);
    expect(iosKeys).toHaveLength(1);
  });

  it("declares the same adverse vocabulary", () => {
    expect(iosKeys).toEqual(webKeys);
    expect(webKeys).toEqual(["relegation"]);
  });

  it("wires the app's grid badge to it", () => {
    // A helper nobody calls passes everything above. This is the line the bug
    // was: `.foregroundStyle(trend > 0 ? .green : .red)`.
    expect(iosGrid).toMatch(/GridColumnPolarity\.isGoodNews\(\s*trend:\s*trend,\s*columnKey:\s*stage\.key\s*\)/);
    expect(iosGrid).not.toMatch(/\.foregroundStyle\(\s*trend > 0 \? \.green : \.red\s*\)/);
  });

  it("leaves the ARROW following the number", () => {
    // Only the colour flips. Turning the arrow to agree with the colour would
    // misstate which way the probability actually moved — the arrow is a fact,
    // the colour is the reading.
    expect(iosGrid).toMatch(/Image\(systemName: trend > 0 \? "arrow\.up" : "arrow\.down"\)/);
  });

  it("holds the arrangement that lets the ladder card's delta stay polarity-blind", () => {
    // `LadderCardView.deltaValue` is the same `delta > 0 ? green : danger`
    // assumption, and it was deliberately NOT threaded: it is fed by
    // `headlineDelta`, taken from `ordered.last`, and every adverse key is
    // order=1 — so an adverse key can never be the headline. That is an
    // arrangement of the CONFIG, not a property of the renderer, so it is
    // asserted rather than assumed. The day someone reorders a config, this
    // fails instead of the colour silently going wrong on a second surface.
    const ladder = stripComments(read(IOS_LADDER));
    expect(ladder).toMatch(/headlineDelta: trend\.map/);

    // Per CONFIG, not globally: "last" means the highest `order` within the one
    // `columns=[...]` block a grid is built from. A global maximum would compare
    // EPL's relegation against some other league's deepest column and pass for
    // a reason that has nothing to do with the claim.
    const configs = read(CONFIGS);
    const blocks = [...configs.matchAll(/columns=\[([\s\S]*?)\]/g)].map((m) =>
      [...m[1].matchAll(/GridColumn\(key="([a-z0-9_]+)",\s*label="[^"]*",\s*order=(\d+)/g)]
        .map((c) => ({ key: c[1], order: Number(c[2]) })),
    ).filter((cols) => cols.length > 0);

    // The extractor must have found real configs, or every loop below is vacuous.
    expect(blocks.length).toBeGreaterThanOrEqual(3);
    expect(blocks.flat().length).toBeGreaterThan(20);

    const configsHoldingAnAdverseKey = blocks.filter((cols) =>
      cols.some((c) => webKeys.includes(c.key)),
    );
    // `relegation` is in epl, la-liga and bundesliga. If this drops to 0 the
    // loop below proves nothing.
    expect(configsHoldingAnAdverseKey).toHaveLength(3);

    for (const cols of configsHoldingAnAdverseKey) {
      const last = cols.reduce((a, b) => (b.order > a.order ? b : a));
      expect(webKeys).not.toContain(last.key);
    }
  });
});
