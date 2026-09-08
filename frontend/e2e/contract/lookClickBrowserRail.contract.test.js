"use strict";

const { describe, it } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

/**
 * #4032 — the guard on the guard.
 *
 * ## The problem this solves
 *
 * `browser-rail/lookClickBrowser.test.js` proves the four LOOK behaviours that
 * need a layout engine. It costs a Chromium download, so it cannot live in
 * `e2e-contract` and therefore does not run on every push — it runs only when
 * the paths it guards change.
 *
 * That is the right trade and it opens one hole: **a browser guard that has
 * quietly stopped being invoked reads exactly like a browser guard that
 * passes.** Rename the directory, drop the npm script, edit the workflow's path
 * filter, and nothing anywhere goes red. This file is what closes that, and it
 * is dependency-free `node --test` so it runs in `e2e-contract` on every push
 * and sits in `deploy: needs:` — the same reasoning that puts `jestGate`,
 * `typecheckGate` and `codeqlLanguages` here.
 *
 * ## The second thing it guards, which is subtler
 *
 * A fixture can keep passing while it stops testing anything. The visible-first
 * case is only a test while the HIDDEN `Sports` sits ABOVE the visible one in
 * DOM order — reorder them and the suite still goes green having proved
 * nothing, because `.first()` and `.filter({visible:true}).first()` would then
 * pick the same node. Same for `LandedOnB`: it is evidence of navigation only
 * while it exists on fixture B and NOT on fixture A.
 *
 * Those are assertions about the fixture's SHAPE, and they are the difference
 * between a regression guard and a green light. Both are pinned below.
 */

const E2E_ROOT = path.resolve(__dirname, "..");
const REPO_ROOT = path.resolve(E2E_ROOT, "..", "..");

const BROWSER_RAIL_DIR = path.join(E2E_ROOT, "browser-rail");
const BROWSER_TEST = path.join(BROWSER_RAIL_DIR, "lookClickBrowser.test.js");
const FIXTURE_A = path.join(BROWSER_RAIL_DIR, "fixtures", "fixture-a.html");
const FIXTURE_B = path.join(BROWSER_RAIL_DIR, "fixtures", "fixture-b.html");

const WORKFLOW = path.join(REPO_ROOT, ".github", "workflows", "look-rail-guard.yml");
const CI_YML = path.join(REPO_ROOT, ".github", "workflows", "ci.yml");
const SHOP_SHOT = path.join(REPO_ROOT, "tools", "shop-shot.mjs");
const PACKAGE_JSON = path.join(E2E_ROOT, "package.json");

function read(file) {
  assert.ok(
    fs.existsSync(file),
    `${path.relative(REPO_ROOT, file)} is missing. If it genuinely moved, update this fixture in the same commit rather than leaving it to fail as a mystery.`
  );
  return fs.readFileSync(file, "utf8");
}

/** Strip full-line `#` comments — this file's YAML assertions must not be satisfied by prose. */
function codeOf(text) {
  return text
    .split("\n")
    .filter((line) => !/^\s*#/.test(line))
    .join("\n");
}

describe("#4032 — the browser-backed LOOK guard is actually wired up", () => {
  it("every piece of the rail exists", () => {
    for (const p of [BROWSER_TEST, FIXTURE_A, FIXTURE_B, WORKFLOW]) {
      assert.ok(fs.existsSync(p), `missing: ${path.relative(REPO_ROOT, p)}`);
    }
  });

  it("an npm script runs the suite, and it is not swept up by `npm run contract`", () => {
    const pkg = JSON.parse(read(PACKAGE_JSON));

    assert.ok(pkg.scripts["browser-rail"], "package.json lost the `browser-rail` script");
    assert.match(
      pkg.scripts["browser-rail"],
      /node --test browser-rail\/\*\.test\.js/,
      "the browser suite must be run by node --test over browser-rail/"
    );

    // The two suites must stay separate in BOTH directions. If `contract`'s
    // glob ever widened to reach browser-rail/, every push would start
    // downloading Chromium inside a deploy-gating job that exists precisely
    // because it needs no install — and it would fail, because e2e-contract
    // deliberately never runs `npm ci`.
    assert.match(pkg.scripts.contract, /^node --test contract\/\*\.test\.js$/);
    assert.ok(
      !pkg.scripts.contract.includes("browser-rail"),
      "the dependency-free contract job must never reach the browser suite"
    );
  });

  it("the browser suite stays OUT of the deploy path", () => {
    // Not a style preference: `e2e-contract` is in `deploy: needs:`, and its
    // whole safety argument is "no install, no network, no browser download".
    const ci = codeOf(read(CI_YML));
    assert.ok(
      !ci.includes("browser-rail"),
      "ci.yml now references the browser rail — that puts a ~150MB browser download on the deploy path"
    );
  });

  describe("the workflow that invokes it", () => {
    const raw = read(WORKFLOW);
    const config = codeOf(raw);

    it("the comment-stripped config is not vacuous", () => {
      // Without this, every `includes` below could pass or fail for the wrong
      // reason if stripping ever ate the file.
      assert.ok(config.includes("jobs:"), "stripped config lost its jobs block");
      assert.ok(config.length > 400, `stripped config is suspiciously short (${config.length})`);
    });

    it("actually runs the suite, with a browser, from the lockfile", () => {
      assert.match(config, /node --test[^\n]* browser-rail\/\*\.test\.js/, "the workflow must run the suite");
      assert.ok(
        config.includes("playwright install --with-deps chromium"),
        "the suite is worthless without a browser to run it"
      );
      assert.ok(config.includes("npm ci"), "the lockfile is what pins the Chromium build");
      assert.ok(!/\bnpm install\b/.test(config), "npm install would defeat the lockfile gate");
    });

    it("fires on the paths it guards, including the script under test", () => {
      // A path filter that omits the subject is the quietest way for this rail
      // to stop protecting anything: `shop-shot.mjs` could be rewritten and
      // this workflow would never run.
      for (const p of [
        "tools/shop-shot.mjs",
        "tools/shot-click-contract.mjs",
        "frontend/e2e/browser-rail/**",
      ]) {
        assert.ok(config.includes(p), `the workflow's path filter must include ${p}`);
      }
    });

    it("speaks on pull requests, with no base-branch filter", () => {
      // The same trap `ciTriggerCoverage` pins for ci.yml and codeql.yml: a
      // `branches:` filter under `pull_request:` means a PR on any other base
      // matches no trigger and gets NO RUN — an empty checks list, which reads
      // as no objections. `paths:` is a different thing and is deliberate.
      const lines = config.split("\n");
      const start = lines.findIndex((l) => l === "on:");
      assert.notEqual(start, -1, "the workflow has no top-level `on:` block");
      const rest = lines.slice(start + 1);
      let end = rest.findIndex((l) => /^\S/.test(l));
      if (end === -1) end = rest.length;
      const on = rest.slice(0, end);

      const prStart = on.findIndex((l) => l.trim() === "pull_request:");
      assert.notEqual(prStart, -1, "the guard must speak on pull requests");
      const prRest = on.slice(prStart + 1);
      let prEnd = prRest.findIndex((l) => /^ {2}\S/.test(l));
      if (prEnd === -1) prEnd = prRest.length;
      const pr = prRest.slice(0, prEnd);

      const filter = pr.find((l) => /^\s+branches(-ignore)?:/.test(l));
      assert.equal(
        filter,
        undefined,
        `the guard restricts \`pull_request\` by base branch: "${filter && filter.trim()}" — a stacked PR would get no run at all`
      );
    });

    it("files nothing and can push nothing", () => {
      assert.match(config, /permissions:\s*\n\s*contents:\s*read\s*\n/);
      assert.ok(!config.includes("issues: write"));
      assert.ok(!config.includes("contents: write"));
    });

    it("refuses a green that ran no tests", () => {
      // `node --test` exits 0 on a glob that matches nothing, so "the suite was
      // renamed and nobody noticed" would otherwise be indistinguishable from a
      // pass. The workflow reads its own summary; these are the three readings
      // that make an empty run impossible to mistake for a clean one.
      assert.match(config, /# pass \[0-9\]\+/, "the workflow must read the pass count");
      assert.match(config, /# skipped \[0-9\]\+/, "the workflow must read the skip count");
      assert.match(config, /the suite did not run/, "a zero-test green must fail with that reading named");

      // The greps above only work against TAP. Node's DEFAULT reporter is
      // version- and TTY-dependent and emits `ℹ pass 6`, so without this flag
      // the step reads a pass count of 0 out of a green suite and fails every
      // run — measured, on the first cut of this workflow. A permanently red
      // gate is worse than no gate: it gets deleted rather than fixed. These
      // two must move together, so they are pinned together.
      assert.match(
        config,
        /--test-reporter=tap/,
        "the summary greps parse TAP; without the flag they parse the wrong format and the gate can never pass"
      );
    });
  });

  describe("the fixtures still hold the shapes the suite depends on", () => {
    const a = read(FIXTURE_A);
    const b = read(FIXTURE_B);

    it("fixture A hides its decoy behind a media query, as production does", () => {
      assert.match(a, /\.desktop-only\s*\{\s*display:\s*none;?\s*\}/, "the decoy must be hidden");
      assert.match(
        a,
        /@media\s*\(min-width:\s*900px\)/,
        "hidden by RESPONSIVE css, not unconditionally — the media query is what made the real bug subtle"
      );
    });

    it("the HIDDEN `Sports` comes BEFORE the visible one — this is the whole test", () => {
      // If these are ever reordered the suite still goes green having proved
      // nothing at all: `.first()` and `.filter({visible:true}).first()` would
      // then select the same node, so deleting the filter would stop being
      // detectable. The ordering IS the assertion.
      const hidden = a.indexOf('<nav class="desktop-only">');
      const visible = a.indexOf('id="visible-sports"');

      assert.notEqual(hidden, -1, "fixture A lost its hidden decoy nav");
      assert.notEqual(visible, -1, "fixture A lost its visible Sports link");
      assert.ok(
        hidden < visible,
        "the hidden decoy must precede the visible target in DOM order, or the visible-first guard proves nothing"
      );
    });

    it("fixture A's pill carries an emoji, so exact text cannot reach it", () => {
      const pill = a.match(/<button class="pill"[^>]*>([^<]*)<\/button>/);
      assert.ok(pill, "fixture A lost its pill control");
      const label = pill[1];
      assert.ok(/\p{Extended_Pictographic}/u.test(label), `the pill's label must carry an emoji, got "${label}"`);
      assert.notEqual(
        label,
        "NFL",
        "an exactly-`NFL` label would make the failing half of the emoji test pass for the wrong reason"
      );
      assert.ok(label.includes("NFL"), `the label must still contain NFL, got "${label}"`);
    });

    it("`LandedOnB` is on fixture B and NOWHERE on fixture A", () => {
      // It is proof of navigation only while it is unreachable without
      // navigating. If it appeared on A too, the multi-step test would pass
      // without ever leaving the first page.
      assert.match(b, /LandedOnB/, "fixture B lost the landmark the second step targets");
      assert.ok(
        !a.includes("LandedOnB"),
        "fixture A must not contain the landmark, or step 2 stops proving the click navigated"
      );
    });

    it("fixture A's visible Sports link points at fixture B, and the decoy does not", () => {
      assert.match(a, /id="visible-sports" href="fixture-b\.html"/, "the visible target must navigate to B");
      assert.match(
        a,
        /<nav class="desktop-only">\s*<a href="nowhere\.html">/,
        "the decoy must lead nowhere, so clicking it can never be mistaken for success"
      );
    });
  });

  describe("the exit-code vocabulary is single-sourced", () => {
    it("shop-shot.mjs binds its final exit to EXIT_CAMERA, not a literal", () => {
      // Item 5. Two of the three codes came from the shared module and the
      // third was typed here; that is how a vocabulary drifts apart.
      const src = read(SHOP_SHOT);
      assert.match(src, /process\.exit\(ok \? 0 : EXIT_CAMERA\)/, "the camera exit must use the constant");
      assert.ok(
        !/process\.exit\(ok \? 0 : 1\)/.test(src),
        "the literal camera exit is back — renumbering EXIT_CAMERA would silently desynchronise it"
      );
      assert.match(src, /EXIT_CAMERA,?\s*\n?\s*EXIT_CLICK_FAILED/, "EXIT_CAMERA must be imported from the contract module");
    });

    it("the browser suite asserts against the constants, not against bare numbers", () => {
      const src = read(BROWSER_TEST);
      assert.match(src, /EXIT\.EXIT_CLICK_FAILED/);
      assert.match(src, /EXIT\.EXIT_CAMERA/);
      assert.match(src, /EXIT\.EXIT_USAGE/);
      assert.ok(
        !/assert\.equal\(\s*r\.status,\s*[123]\s*\)/.test(src),
        "a hard-coded status literal would survive a renumbering that broke every caller"
      );
    });

    it("the browser suite never skips", () => {
      // A skip is how this suite would go green on a machine with no browser,
      // which is the one circumstance in which its result means nothing.
      const src = read(BROWSER_TEST);
      assert.ok(!/\bit\.skip\b|\bdescribe\.skip\b|\{\s*skip:/.test(src), "this suite must fail rather than skip");
    });
  });
});
