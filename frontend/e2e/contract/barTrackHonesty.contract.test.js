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

    // #8562 — THE 45% IS NOW A CAP, AND THIS GUARD STATES THE PROPERTY, NOT THE LITERAL.
    //
    // A flat `w-[45%]` reserved 114px for "$730"; beside #5659's "▲56.0 pts" slot the track
    // measured 0px on production at 1280 (the Meta card drew no bars at all). The slot is now
    // sized from the ladder's longest label and capped at the same 45%. What #1574(c) needs is
    // untouched and asserted below: ONE width per ladder — computed from `longestLabelChars`,
    // a reduce over the whole ladder, never from the row's own label — so it cannot be a
    // content width, and it can never be wider than it was.
    assert.ok(
      /const longestLabelChars = ordered\.reduce\(/.test(src),
      "the label width must be measured over the whole ladder (`ordered`), not per row",
    );
    const wideWidth = src.match(/const wideLabelWidth = `clamp\(([^`]*)\)`;/);
    assert.ok(wideWidth, "wideLabels must compute one `wideLabelWidth` clamp for the ladder");
    assert.ok(
      /\$\{longestLabelChars\}ch/.test(wideWidth[1]) && !/rung\./.test(wideWidth[1]),
      "the wide slot must be sized from the LADDER's longest label — a per-row width is the " +
        "#1574(c) defect: equal percentages draw unequal bars",
    );
    assert.ok(
      /,\s*45%$/.test(wideWidth[1]),
      "the wide slot is capped at 45%: a wider slot pays for the label out of every bar",
    );
    assert.ok(
      /wideLabels(?:\s*&&\s*!stackMove)?\s*\?\s*\{\s*width:\s*wideLabelWidth\s*\}/.test(src),
      "the wide label must be given `wideLabelWidth` as its width",
    );
    // #8562, second half — a date ladder whose badge cannot share the row prints it UNDER the
    // label, and the stacked CELL carries the width. The same property, one element up: one
    // ladder-wide width (longest label, longest badge, never a rung's own), capped at 45%, on the
    // cell whose parent is the row — on the inner label the 45% resolved against an auto-width
    // cell and each rung sized to its own text (measured 171/156/158px tracks, one ladder).
    const stacked = src.match(/const stackedCellWidth = `clamp\(([^`]*)\)`;/);
    assert.ok(stacked, "a stacked ladder must compute one `stackedCellWidth` clamp for the ladder");
    assert.ok(
      /\$\{longestLabelChars\}ch/.test(stacked[1]) &&
        /\$\{movementSlotChars\}ch/.test(stacked[1]) &&
        !/rung\./.test(stacked[1]),
      "the stacked cell must be sized from the LADDER's longest label and badge, never a row's own",
    );
    assert.ok(/,\s*45%$/.test(stacked[1]), "the stacked cell is capped at 45% like the wide slot");
    assert.ok(
      /style=\{\{\s*width:\s*stackedCellWidth\s*\}\}/.test(src),
      "the stacked cell (not the label inside it) must carry `stackedCellWidth`",
    );
    assert.ok(
      !/max-w-\[45%\]/.test(src),
      "`max-w-[45%]` is the #1574(c) defect itself: it lets the label size to " +
        "its content, so equal percentages draw unequal bars",
    );

    // #7427 — the ellipsis was never this guard's property; see the history in git
    // (`w-[45%] shrink-0 truncate` → the pair below). The wide label keeps its fixed width by
    // WRAPPING, bounded, and may not spend its load-bearing tail to stay on one line. The
    // wide arm is identified by its own face (`text-[12px] font-semibold`), so `truncate` on
    // the #4404 numeric arm in the same file stays allowed.
    const wideClass = [...src.matchAll(/wideLabels\s*\?\s*"([^"]*)"/g)]
      .map((m) => m[1])
      .find((c) => c.includes("text-[12px] font-semibold"));
    assert.ok(wideClass, "the wide-label class string must exist");
    assert.ok(/\bshrink-0\b/.test(wideClass), "the wide label must not shrink below its width");
    assert.ok(
      !/\btruncate\b/.test(wideClass),
      "the wide label must not `truncate`: the slot is narrower than the labels " +
        "the venues write, so the ellipsis lands on the load-bearing tail (#7427)",
    );
    assert.ok(
      /\bline-clamp-2\b/.test(wideClass),
      "the wide label must wrap within its fixed slot, bounded (#7427) — " +
        "unbounded wrapping lets one pathological label grow the row without limit",
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
    // Stated as the PROPERTY — "the width gate opens with `heat.known`" — and not
    // as the whole expression. Pinning `const width = heat.known ?` verbatim made
    // this assertion fail #8167, which ADDS a conjunct to the very gate it is
    // guarding. That is the third time in this file (see the two notes above):
    // a guard that hard-codes an implementation string fails the fix for the bug
    // inside it. `\s*` spans the line break the added conjunct introduces.
    assert.ok(
      /const width =\s*heat\.known\b/.test(src),
      "an unpriced rung must draw NO fill — gate the width on `heat.known` so the " +
        "2% floor cannot paint a near-impossibility claim where there is no number",
    );

    // #8167 — the same floor, the other absent-shaped input. `probabilityHeat(0)`
    // returns `known: true`, so a rung measured at exactly zero walked past the
    // clause above and the floor drew a solid red pill beside a `0%` numeral. The
    // gate is on the PROBABILITY and not on the rounded percent, so a long shot
    // that rounds to 0% (0.004) keeps its sliver.
    assert.ok(
      /heat\.known && rung\.probability!?\s*>\s*0/.test(src),
      "a rung priced at exactly 0 must draw NO fill (#8167) — the 2% floor turns " +
        "a measured zero into a visible claim of a small non-zero value",
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
