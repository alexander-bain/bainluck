/**
 * #4857 — the Player Props card dealt its players in a different order on every launch.
 *
 * Photographed three times on `bainluck://events/15305028` (Seattle @ New England,
 * 5 Kalshi fantasy-points props) within five minutes by native/098 — TWICE on the
 * same binary, `origin/master` 4f31a25a — and the five players came back in three
 * different orders with identical data and identical percentages:
 *
 *     11:03  … Drake Maye, NE Patriots D/ST, Andy Borregales
 *     11:06  Andy Borregales, Hunter Henry, Jadarian Price, Drake Maye, NE Patriots D/ST
 *     11:08  Drake Maye, Hunter Henry, NE Patriots D/ST, Andy Borregales, Jadarian Price
 *
 * `PlayerPropsCardView` groups props into a Swift `Dictionary` and maps over it.
 * Dictionary iteration order is seeded PER PROCESS, so it differs on every launch.
 * Both levels then sorted on a bare count — total rungs for the cards,
 * `rungs.count` for the stat groups within a card — and neither key is unique. On
 * that specimen every player had one rung, so all five compared equal, `sorted` is
 * not guaranteed stable, and the random order survived the sort to the screen.
 *
 * ═══ WHY THIS FILE EXISTS AND NOT ONLY THE XCTESTS ═══
 *
 * CI COMPILES NO SWIFT. `PlayerPropsOrderTests` proves the comparators are total
 * orders and runs on a laptop. It structurally cannot prove the VIEW asks them —
 * and restoring either bare-count `.sorted` leaves every Swift test in the repo
 * green, because the pure functions still pass and nothing reaches them. That is
 * the same trap `eventStatusSingleSource.test.ts` was built for, on a second surface.
 *
 * ═══ WHAT THIS FILE DOES NOT CLAIM ═══
 *
 * That the chosen order is the RIGHT one for a reader. It asserts only that the same
 * payload always deals the same list. Which prop a card should open on is a product
 * question; the paired screenshots on the PR carry what it looks like.
 */

import { readFileSync, existsSync } from "fs";
import { join } from "path";

const IOS_ROOT = join(__dirname, "../../../ios/Bain Luck/Bain Luck");
const CARD = join(IOS_ROOT, "Components/PlayerPropsCardView.swift");
const ORDER = join(IOS_ROOT, "Utilities/PlayerPropsOrder.swift");

function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^[ \t]*\/\/.*$/gm, "")
    .replace(/(?<!:)\/\/.*$/gm, "");
}

// A path typo would otherwise read as a clean pass — the failure mode a source
// scan is most prone to, and the reason this is a constant and not an inline join.
const present = [CARD, ORDER].every(existsSync);
const d = present ? describe : describe.skip;

d("#4857 — the props card deals a stable order", () => {
  const card = () => stripComments(readFileSync(CARD, "utf8"));
  const order = () => readFileSync(ORDER, "utf8");

  it("the comparators exist and each ends on a key that cannot tie", () => {
    // The whole fix in one assertion pair: the last line of each comparator is a
    // comparison of the DICTIONARY KEY the collection was grouped under. If either
    // ends on anything else, ties are possible again.
    expect(order()).toMatch(/static func cardPrecedes\([\s\S]*?return lhs\.name < rhs\.name\s*\}/);
    expect(order()).toMatch(
      /static func statGroupPrecedes\([\s\S]*?return lhs\.type < rhs\.type\s*\}/,
    );
  });

  describe("THE MUTANTS: the view must ASK, on both levels", () => {
    it("the player cards are sorted through PlayerPropsOrder", () => {
      expect(card()).toMatch(
        /\.sorted \{ PlayerPropsOrder\.cardPrecedes\(\$0\.orderKey, \$1\.orderKey\) \}/,
      );
    });

    it("the stat groups within a card are too", () => {
      expect(card()).toMatch(/PlayerPropsOrder\.statGroupPrecedes\(/);
    });

    it("neither bare-count sort has come back", () => {
      // The two literal expressions this ship removed. Written as their own
      // assertion rather than folded into the two above, because a REPLACEMENT
      // that adds the helper call while leaving an earlier `.sorted` in place
      // would satisfy those and still reshuffle: the last sort wins.
      const source = card();
      expect(source).not.toMatch(/\.sorted \{ \$0\.rungs\.count > \$1\.rungs\.count \}/);
      expect(source).not.toMatch(
        /\.sorted \{ \$0\.statGroups\.map\(\\\.rungs\.count\)\.reduce\(0, \+\) >/,
      );
    });

    it("there are exactly four sorts in the file, and each one is named", () => {
      // A NEW `.sorted` appearing on the cards pipeline would silently take
      // precedence over the helper — the last sort wins — so the tripwire is the
      // count, and the four are enumerated so the next reader can see which is which.
      const source = card();
      expect((source.match(/\.sorted[ (\.{]/g) ?? []).length).toBe(4);

      // 1. the rungs inside one stat group, by threshold — already a total order
      //    (thresholds are distinct within a ladder).
      expect(source).toMatch(/rungs: rungs\.sorted \{ \$0\.threshold < \$1\.threshold \}/);
      // 2. the stat groups, and 3. the cards — the two this ship repaired, asserted above.
      // 4. the source badge list: a Set of strings through the default comparator,
      //    deterministic already and deliberately left alone.
      expect(source).toMatch(/Array\(Set\(playerProps\.compactMap\(\\\.source\)\)\)\.sorted\(\)/);
    });
  });

  it("the sort key reads the probability it claims to, not the threshold", () => {
    // `topProbability` sorting on `\.threshold` by mistake compiles, type-checks,
    // and produces a stable-but-wrong order that no Swift test of the comparator
    // alone would catch, because the comparator would still be a total order.
    expect(card()).toMatch(/topProbability: statGroups\.flatMap\(\\\.rungs\)\.map\(\\\.probability\)\.max\(\)/);
  });
});
