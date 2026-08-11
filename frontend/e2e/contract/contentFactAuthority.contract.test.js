"use strict";

/**
 * UX-P059 (#1734, #1733) — a blankness grader grades blankness, and a dead
 * specimen is declared rather than asserted.
 *
 * THE DEFECT (#1734). `content.main_region_nonblank` was computed as
 *
 *   (realConceptFound || (isNotObservable && errorVisible)) && mainText.length > 40
 *
 * — the measurement multiplied by the journey's CLASSIFICATION. Those are two
 * different facts, and conflating them made the rail state something it had not
 * measured. MEASURED, scheduled run 31473736725:
 *
 *   tournament.cycling  desktop  1286 ms  main_region_nonblank = FAIL
 *   tournament.f1       desktop  1769 ms  main_region_nonblank = pass
 *
 * Both landed on the SAME "Event not found" terminal and their terminal
 * screenshots are identical. The only difference is that cycling's route was
 * `static`, so `isNotObservable` was false and the conjunction collapsed — while
 * the region held 75 legible characters. The rail then reported "main region
 * rendered blank" about a page that rendered fine.
 *
 * WHY A GUARD. The issue as filed diagnosed a racing `h1` selector and reasoned
 * from the 1286-vs-1769 ms durations. That diagnosis is wrong — there is no `<h1>`
 * in site chrome at all (the brand is a `<span>`; `ErrorMessage` renders its title
 * as a `<p>`), so no `h1` exists on a 404 concept page for a race to resolve on.
 * A plausible, confidently-written, wrong diagnosis is exactly what a contract
 * test outlives.
 *
 * THE DEFECT (#1733). `tournament.cycling` pointed at `tour-de-france-2026`, which
 * 404s — the 2026 Tour ended in July — while the registry asserted static
 * specimens MUST render. Gotcha #44's class: the fixture had an expiry date.
 *
 * Dependency-free (`node --test`), like every fixture in this directory: it must
 * run before Playwright is installed. The `.ts` sources are read as text for the
 * same reason.
 */

const { describe, it } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const e2eRoot = path.resolve(__dirname, "..");
const specPath = path.join(e2eRoot, "specs", "tournament-inventory.spec.ts");
const routesPath = path.join(e2eRoot, "fixtures", "tournamentRoutes.ts");

const specSrc = fs.readFileSync(specPath, "utf8");
const routesSrc = fs.readFileSync(routesPath, "utf8");

/**
 * The ROUTE DATA only — everything from `TOURNAMENT_ROUTES` onward, excluding the
 * `RouteResolution` type union above it. The union necessarily contains
 * `mode: "unavailable"` and `trackingIssue: string` as a TYPE, and an earlier draft
 * of this file graded that declaration as if it were a route with a malformed
 * issue number. A guard that cannot tell a type from a value is the same mistake
 * as a grader that cannot tell blankness from classification.
 */
function routeDataOnly(text) {
  const i = text.indexOf("export const TOURNAMENT_ROUTES");
  assert.notEqual(i, -1, "the route registry must still export TOURNAMENT_ROUTES");
  return text.slice(i);
}

/**
 * Strip block and line comments. These guards must read CODE, not prose — the
 * first draft of the dated-specimen ratchet below failed on a `//` comment that
 * quoted the very slug it was checking for, which is the same "an assertion that
 * cannot tell two things apart" mistake this file exists to catch.
 */
function codeOnly(text) {
  return text
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n")
    .filter((l) => !l.trim().startsWith("//"))
    .join("\n");
}

/** Every `mainRegionNonBlank:` right-hand side in a source file, comments stripped. */
function blanknessExpressions(text) {
  const withoutComments = codeOnly(text);

  const out = [];
  const re = /mainRegionNonBlank:\s*([^\n]*)/g;
  let m;
  while ((m = re.exec(withoutComments)) !== null) out.push(m[1].trim());
  return out;
}

/**
 * Variables that describe WHICH SURFACE rendered / HOW the journey is classified.
 * None of them is evidence about whether the region is blank, so none of them may
 * appear in the blankness expression.
 */
const CLASSIFICATION_TOKENS = [
  "realConceptFound",
  "isNotObservable",
  "notObservable",
  "errorVisible",
  "heroVisible",
  "loadingVisible",
  "realCardFound",
];

describe("UX-P059 · content.main_region_nonblank grades blankness ALONE", () => {
  const expressions = blanknessExpressions(specSrc);

  it("the tournament pack still supplies the assertion at all", () => {
    // Non-vacuity: if the field is renamed or dropped, the loop below would pass
    // by iterating nothing. Two journeys supply it — per-domain, and the hub.
    assert.equal(
      expressions.length,
      2,
      `expected 2 mainRegionNonBlank expressions in tournament-inventory.spec.ts, found ${expressions.length}: ${JSON.stringify(expressions)}`
    );
  });

  for (const token of CLASSIFICATION_TOKENS) {
    it(`no blankness expression consults \`${token}\``, () => {
      for (const expr of expressions) {
        assert.ok(
          !new RegExp(`\\b${token}\\b`).test(expr),
          `\`${token}\` is a classification fact, not a blankness measurement, but it ` +
            `appears in: mainRegionNonBlank: ${expr}\n` +
            `See #1734 — this conjunction reported "main region rendered blank" about a ` +
            `page rendering 75 legible characters.`
        );
      }
    });
  }

  it("each expression is a length measurement", () => {
    for (const expr of expressions) {
      assert.ok(
        /mainText|nonBlank/.test(expr),
        `blankness must be measured from the region's text, got: ${expr}`
      );
    }
  });

  it("the classification is still asserted, on its own line", () => {
    // Coverage is not reduced: a static specimen that 404s must still red. The
    // pass-bar expect is what does it, and this pins that it survives.
    assert.ok(
      /expect\(\s*realConceptFound,/.test(specSrc),
      "the BROKEN detector (a real concept must render) must remain a separate expect"
    );
    assert.ok(
      /expect\(\s*errorVisible,/.test(specSrc),
      "the NOT-OBSERVABLE bar (the honest terminal must render) must remain a separate expect"
    );
  });
});

describe("UX-P059 · a dead specimen is DECLARED, never asserted as live", () => {
  it("cycling no longer points at the expired 2026 Tour slug", () => {
    assert.ok(
      !/tour-de-france-2026/.test(codeOnly(routesSrc)),
      "the expired tour-de-france-2026 slug must not remain as a live route target (#1733)"
    );
  });

  it("every `unavailable` route carries a reason and an open tracking issue", () => {
    const blocks = routeDataOnly(codeOnly(routesSrc))
      .split(/\n {2}\{/)
      .filter((b) => /mode:\s*"unavailable"/.test(b));
    assert.ok(blocks.length >= 1, "expected at least one declared-unavailable route");

    for (const b of blocks) {
      const reason = /reason:\s*\n?\s*("(?:[^"\\]|\\.)*")/.test(b) || /reason:\s*$/m.test(b);
      assert.ok(
        reason || /reason:/.test(b),
        "an unavailable route must state WHY — a NOT-OBSERVABLE with no reason is " +
          "indistinguishable from a domain that is merely between editions"
      );
      assert.ok(
        /trackingIssue:\s*"#\d+"/.test(b),
        "an unavailable route must name the issue that stays open while it is unproven — " +
          "that is what makes it a declared gap rather than a mute button"
      );
    }
  });

  it("an unavailable route resolves to null, taking the shared NOT-OBSERVABLE path", () => {
    assert.ok(
      /mode === "unavailable"\)\s*return null;/.test(specSrc),
      "an unavailable domain must resolve to null so it reuses the existing " +
        "no-live-specimen probe, its declared 404 allowance, and the honest terminal — " +
        "a separate branch would be a second way to pass"
    );
  });

  /**
   * THE RATCHET. `election/2026-midterms` and `soccer/world-cup-2026` still resolve
   * today but carry the same expiry shape that killed cycling. This is an EQUALITY,
   * not an allowlist: a new dated static specimen reds here and forces the decision
   * at authoring time, and removing one when it is fixed is likewise required.
   *
   * Deliberately not "fixed" by an `expires` date — that makes the rail
   * clock-dependent, and gotcha #44 plus Q329 (#1729) say that needs a
   * clock_sweep-grade proof rather than a side effect of this queue.
   */
  it("the set of dated static specimens is exactly the two known ones", () => {
    const staticPaths = [...routeDataOnly(codeOnly(routesSrc)).matchAll(/mode:\s*"static",\s*path:\s*"([^"]+)"/g)].map(
      (m) => m[1]
    );
    assert.ok(staticPaths.length > 0, "expected static routes to still exist");

    const dated = staticPaths.filter((p) => /\b(19|20)\d{2}\b/.test(p)).sort();
    assert.deepEqual(
      dated,
      ["/event/election/2026-midterms", "/event/soccer/world-cup-2026"],
      "A static specimen whose slug carries a year WILL expire and red the sweep " +
        "forever (#1733, gotcha #44). Adding one requires a decision; fixing one " +
        "requires updating this list. Neither may happen silently."
    );
  });
});
