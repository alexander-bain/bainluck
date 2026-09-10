"use strict";

const { describe, it } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

/**
 * #4651 — a category page must not scroll sideways on a phone.
 *
 * ## The defect
 *
 * `/economics`, `/politics` and `/entertainment` all read a `document.scrollWidth`
 * wider than a 390px viewport, so the WHOLE page slid under the thumb and every
 * section carried a dead strip down its right-hand side. Measured on production:
 * economics 558, politics 485, entertainment 473.
 *
 * `/economics` was its own thing (a grid item's `min-width: auto` flooring its track
 * at a 500px heatmap's min-content — fixed in `5b3e03fe`, guarded by
 * `economicsHeatmapCardShrinks4651.test.tsx`). The other two share ONE shape:
 *
 *   a flex row of [ title/question | controls pushed right by `margin-left: auto` ]
 *   whose controls are chips, and which is never allowed to wrap.
 *
 * Chips are the point. `min-width: 0` is the reflex fix for a flex child that will
 * not shrink, and it does nothing useful here: a chip's text IS its content, so all
 * shrinking buys is a clipped label. The row keeps its width, its right edge lands
 * past the viewport, and the page grows.
 *
 * ## Why the assertions are textual
 *
 * This is CSS in a module file at a media query. jsdom has no layout engine and
 * never loads the stylesheet, so a jest render cannot see it; the only real check is
 * a browser at a real width, which an agent session cannot run against a deploy that
 * does not exist yet. `e2e-contract` is what `deploy: needs:`, so the assertion that
 * blocks a regression has to live here.
 *
 * Each page therefore gets BOTH halves, and the first is what keeps this file honest:
 *
 *   1. the PRECONDITION still exists — the row is still a flex row with an auto
 *      margin pushing its controls right. If someone rebuilds the header as a grid
 *      or drops the auto margin, these rules stop being the fix and this guard
 *      should fail loudly rather than keep passing over a stale claim.
 *   2. the FIX is present, inside the phone media block rather than at top level.
 *
 * Verified before writing by injecting each rule set into the live page and
 * re-reading `scrollWidth` (`tools/overflow-tryfix-4651.mjs`): politics 485 -> 390,
 * entertainment 473 -> 390, both overflow 0. Neither page overflows above ~430px, so
 * both rules ride in the file's existing phone block; no new breakpoint.
 */

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const FRONTEND = path.join(REPO_ROOT, "frontend");

const POLITICS_CSS = path.join(FRONTEND, "app", "politics", "politics.module.css");
const ENTERTAINMENT_CSS = path.join(FRONTEND, "app", "entertainment", "entertainment.module.css");

function read(file) {
  assert.ok(fs.existsSync(file), `${path.relative(REPO_ROOT, file)} must exist`);
  return fs.readFileSync(file, "utf8");
}

/**
 * Return the body of `@media (max-width: <px>px) { … }`, brace-matched.
 *
 * A bare `indexOf('}')` would stop at the first nested rule's closing brace and
 * hand back a fragment, so a rule further down the block would read as absent and
 * the guard would fail for the wrong reason.
 */
function mediaBlock(src, maxWidthPx) {
  const re = new RegExp(`@media\\s*\\(max-width:\\s*${maxWidthPx}px\\s*\\)\\s*\\{`);
  const m = re.exec(src);
  assert.ok(m, `expected a @media (max-width: ${maxWidthPx}px) block`);
  let depth = 1;
  let i = m.index + m[0].length;
  const start = i;
  for (; i < src.length && depth > 0; i++) {
    if (src[i] === "{") depth++;
    else if (src[i] === "}") depth--;
  }
  assert.equal(depth, 0, `unbalanced braces in the ${maxWidthPx}px media block`);
  return src.slice(start, i - 1);
}

/** `.foo { … }` body inside a chunk of CSS, brace-matched the same way. */
function ruleBody(css, selector) {
  const re = new RegExp(`(^|[\\s,}])\\${selector}\\s*(,[^{]*)?\\{`, "m");
  const m = re.exec(css);
  if (!m) return null;
  let depth = 1;
  let i = m.index + m[0].length;
  const start = i;
  for (; i < css.length && depth > 0; i++) {
    if (css[i] === "{") depth++;
    else if (css[i] === "}") depth--;
  }
  return css.slice(start, i - 1);
}

function declares(css, selector, property, value) {
  const body = ruleBody(css, selector);
  if (body === null) return false;
  const re = new RegExp(`(^|;|\\s)${property}\\s*:\\s*${value}\\s*(;|$)`, "m");
  return re.test(body);
}

describe("#4651 — /politics and /entertainment do not scroll sideways on a phone", () => {
  describe("/politics — the presidential hero's control row", () => {
    const src = () => read(POLITICS_CSS);

    it("PRECONDITION: the head is still a flex row whose actions are pushed right", () => {
      const css = src();

      assert.ok(
        declares(css, ".presHeroHead", "display", "flex"),
        ".presHeroHead must still be `display: flex` — if this header is rebuilt " +
          "as a grid or a block, `flex-wrap` is no longer the fix and this guard " +
          "would otherwise keep passing over a claim that stopped being true",
      );
      assert.ok(
        declares(css, ".presHeroActions", "margin-left", "auto"),
        ".presHeroActions must still be pushed right by `margin-left: auto` — that " +
          "is what makes the row a two-column layout with no room at 390px",
      );
    });

    it("the head WRAPS on a phone, so the controls drop to their own line", () => {
      const phone = mediaBlock(src(), 720);

      assert.ok(
        declares(phone, ".presHeroHead", "flex-wrap", "wrap"),
        "`.presHeroHead { flex-wrap: wrap }` must be in the 720px block. Without " +
          "it the actions block holds 345px against ~318px of card interior, its " +
          "right edge lands at 484.9px, and document.scrollWidth reads 485 at a " +
          "390px viewport — the whole page scrolls sideways, not just this card",
      );
    });

    it("the fix is scoped to the phone, not applied at every width", () => {
      const css = src();
      const phone = mediaBlock(css, 720);
      const topLevel = css.replace(phone, "");

      assert.ok(
        !declares(topLevel, ".presHeroHead", "flex-wrap", "wrap"),
        "wrapping at ALL widths would let the desktop header break into two lines " +
          "the moment a question grew; the row fits on one line above ~430px",
      );
    });
  });

  describe("/entertainment — the section header's tab bar", () => {
    const src = () => read(ENTERTAINMENT_CSS);

    it("PRECONDITION: the section head is still a flex row with an auto-margin meta", () => {
      const css = src();

      assert.ok(
        declares(css, ".sectionHead", "display", "flex"),
        ".sectionHead must still be `display: flex`",
      );
      assert.ok(
        declares(css, ".sectionMeta", "margin-left", "auto"),
        ".sectionMeta must still be pushed right by `margin-left: auto`",
      );
      assert.ok(
        ruleBody(css, ".tabBar") !== null && ruleBody(css, ".tabBtn") !== null,
        ".tabBar and .tabBtn must still exist — they are what overflows",
      );
    });

    it("the head wraps, the bar wraps, and a tab never breaks inside its own label", () => {
      const phone = mediaBlock(src(), 600);

      assert.ok(
        declares(phone, ".sectionHead", "flex-wrap", "wrap"),
        "`.sectionHead { flex-wrap: wrap }` must be in the 600px block: the bar " +
          "needs the full column, not the remainder beside a title",
      );
      assert.ok(
        declares(phone, ".tabBar", "flex-wrap", "wrap"),
        "`.tabBar { flex-wrap: wrap }` must be in the 600px block: a bar too wide " +
          "for one line has to break BETWEEN tabs",
      );
      assert.ok(
        declares(phone, ".tabBtn", "white-space", "nowrap"),
        "`.tabBtn { white-space: nowrap }` must be in the 600px block. This is the " +
          "one that is easy to drop as cosmetic and is not: without it the buttons " +
          "still shrink to fit — by wrapping their own text — and 'Spotify Race' " +
          "renders as 'Spotify' over 'Race' in a control whose whole job is to read " +
          "as one word per tab",
      );
    });

    it("the fix is scoped to the phone, not applied at every width", () => {
      const css = src();
      const phone = mediaBlock(css, 600);
      const topLevel = css.replace(phone, "");

      assert.ok(
        !declares(topLevel, ".sectionHead", "flex-wrap", "wrap"),
        "a desktop section header should stay on one line",
      );
    });
  });
});
