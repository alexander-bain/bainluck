"use strict";

const { describe, it } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

/**
 * UX-P010 / #1574 acceptance (c) — a bar must mean what the number says.
 *
 * ## The two defects this guard pins, both from Alex's 2026-08-07 Discover eyeball
 *
 * 1. **Tracks of different lengths.** `QuantityGroup` in `wideLabels` mode gave
 *    the label `max-w-[45%]` — a MAX, so the span took its CONTENT width. The
 *    track beside it is `flex-1` over whatever is left, so every row got a
 *    different track length. Two rungs both printing "48%" drew visibly
 *    different bars, because 48% of a short track is shorter than 48% of a long
 *    one. The bar stopped being comparable down the column, which is the only
 *    thing a stacked bar column is for.
 *
 * 2. **Fill that contradicts the printed number.** The `outcome_distribution`
 *    branch of `FuturesCard` computed `width = probability / maxProb` while
 *    printing `probability * 100`. Leader-normalising means the top row ALWAYS
 *    renders a full bar — a 12% leader looked like a certainty — and no row's
 *    fill matched its own label.
 *
 * ## Why the assertions are textual
 *
 * Both defects are CSS/arithmetic in the render path, invisible to a data-level
 * test and (per the standing constraint) not reachable by a browser from an
 * agent session. `e2e-contract` is what `deploy: needs:`, so the assertion that
 * blocks a deploy has to live here, in the dependency-free `node --test` suite.
 * Behavioural coverage of the components belongs in jest.
 */

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const FRONTEND = path.join(REPO_ROOT, "frontend");

const QUANTITY_GROUP = path.join(FRONTEND, "components", "QuantityGroup.tsx");
const FUTURES_CARD = path.join(FRONTEND, "components", "discover", "FuturesCard.tsx");

function read(file) {
  assert.ok(fs.existsSync(file), `${path.relative(REPO_ROOT, file)} must exist`);
  return fs.readFileSync(file, "utf8");
}

describe("UX-P010 #1574(c) — bar tracks align and fills match printed values", () => {
  it("QuantityGroup wideLabels uses a FIXED label width, so every track is equal", () => {
    const src = read(QUANTITY_GROUP);

    assert.ok(
      /w-\[45%\]\s+shrink-0\s+truncate/.test(src),
      "wideLabels must set a fixed `w-[45%] shrink-0 truncate` label width — a " +
        "content-width label makes the flex-1 track a different length per row",
    );
    assert.ok(
      !/max-w-\[45%\]/.test(src),
      "`max-w-[45%]` is the #1574(c) defect itself: it lets the label size to " +
        "its content, so equal percentages draw unequal bars",
    );
  });

  it("QuantityGroup fill width and printed value come from the same probability", () => {
    const src = read(QUANTITY_GROUP);

    // The rung fill is a plain percentage of the rung's own probability, floored
    // at 2% so a genuine long shot still draws a sliver (#1574(c)).
    //
    // This asserts the PROPERTY, not the literal expression. It used to pin the
    // exact source text `Math.max(2, Math.round((rung.probability ?? 0) * 100))`,
    // which meant it also pinned the `?? 0` — and that coercion was the #4660
    // defect: it sorted an ABSENT probability into the same band as one measured
    // at zero, and the floor then painted the result a visible red. A guard that
    // hard-codes an implementation string fails the fix for the bug inside it.
    assert.ok(
      /Math\.max\(2,\s*Math\.round\(rung\.probability!?\s*\*\s*100\)\)/.test(src),
      "rung fill must be `probability * 100`, floored at 2% — anything relative " +
        "(a max, a sum, a leader) decouples the bar from the number printed beside it",
    );
    assert.ok(
      !/rung\.probability\s*\/\s*max/i.test(src),
      "a leader/max-normalised rung fill contradicts its own printed percentage",
    );

    // #4660, the other half: the floor is for a long shot we HAVE priced, never
    // for a rung with no price. Coercing the absent case to 0 puts it in the
    // danger band and the floor makes that claim visible, so the width must be
    // gated on the heat's `known` flag and must not re-introduce the coercion.
    assert.ok(
      /const width = heat\.known \?/.test(src),
      "an unpriced rung must draw NO fill — gate the width on `heat.known` so the " +
        "2% floor cannot paint a near-impossibility claim where there is no number",
    );
    assert.ok(
      !/rung\.probability \?\? 0/.test(src),
      "`rung.probability ?? 0` IS the #4660 defect: it makes an absent price " +
        "indistinguishable from one measured at zero",
    );
  });

  it("FuturesCard distribution fill is absolute, never leader-normalised", () => {
    const src = read(FUTURES_CARD);

    assert.ok(
      /const width = Math\.max\(2, Math\.round\(probability \* 100\)\)/.test(src),
      "the outcome_distribution row fill must be `probability * 100` so it " +
        "matches the `Math.round(probability * 100)` it prints",
    );
    assert.ok(
      !/probability\s*\/\s*maxProb/.test(src),
      "`probability / maxProb` IS the defect — it pins the leader's bar at 100% " +
        "regardless of the leader's actual probability",
    );
    assert.ok(
      !/const maxProb\s*=/.test(src),
      "maxProb must not be reintroduced: a leader-relative basis is what made " +
        "the fill disagree with the printed number",
    );
  });
});
