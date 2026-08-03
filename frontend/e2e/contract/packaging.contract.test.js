"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { describe, it } = require("node:test");
const assert = require("node:assert/strict");

/**
 * L2-221 Item 1 — reproducibility and blast-radius contract (C96 [P2]).
 *
 * The old tree carried `"@playwright/test": "^1.48.0"` with `package-lock.json`
 * in `.gitignore`. Two runs could therefore use different runners and browser
 * revisions while claiming to prove the same commit.
 *
 * `npm ci` is the enforcing gate for the lockfile itself — it exits non-zero
 * when the lock is missing or disagrees with package.json, and the workflow
 * uses nothing else. What `npm ci` CANNOT catch is a future edit that
 * reintroduces a range specifier, un-isolates the tree from the Vercel build,
 * or quietly widens the workflow's permissions. That is what this file guards.
 */

const e2eRoot = path.join(__dirname, "..");
const repoRoot = path.join(e2eRoot, "..", "..");

const pkg = JSON.parse(fs.readFileSync(path.join(e2eRoot, "package.json"), "utf8"));

/** Anything that is not a single exact version. */
const RANGE_SPECIFIER = /^[\^~>< ]|[*x]$|\s-\s|\|\|/;

const workflowPath = path.join(repoRoot, ".github", "workflows", "browser-audit.yml");
const workflowRaw = fs.readFileSync(workflowPath, "utf8");

/**
 * Strip `#` comment lines before asserting on content.
 *
 * Learned the hard way in this very file: the first version of these
 * assertions tripped on the workflow's OWN comments, which explain that it
 * uses `npm ci` and never `npm install`, and that `issues: write` belongs to
 * a later job. A prose mention is not a configured behaviour, so the
 * assertions must read the configuration.
 */
const workflowConfig = workflowRaw
  .split("\n")
  .filter((line) => !/^\s*#/.test(line))
  .join("\n");

/**
 * L2-228 — pack parity, derived rather than listed.
 *
 * A pack has to be declared in FOUR places to actually run: the dispatch
 * `options:` dropdown, the input-validation allowlist, the dispatch `case`, and
 * an npm script. L2-227 added `grid` to three of them and missed the
 * allowlist, so the dropdown advertised a pack that died at input validation
 * every time. Nothing caught it, because this file asserted against a
 * hard-coded `["smoke", "consent", "smoke-consent"]` — a list that cannot
 * notice a pack it was never told about.
 *
 * So the expected set is now DERIVED from the workflow's own dropdown, and the
 * other three places are checked against it. Adding a pack to `options:` and
 * nowhere else is now a red contract test rather than a broken dispatch.
 */

/** The packs the dropdown advertises to whoever runs the workflow. */
function advertisedPacks() {
  const block = workflowConfig.match(/options:\n((?:\s*-\s*[^\n]+\n)+)/);
  assert.ok(block, "the workflow must offer a `pack` choice with an options list");
  return block[1]
    .split("\n")
    .map((line) => line.replace(/^\s*-\s*/, "").trim())
    .filter(Boolean);
}

/** The packs the input-validation step will actually let through. */
function allowlistedPacks() {
  const m = workflowConfig.match(/AUDIT_PACK\}"\s*\|\s*grep -Eq '\^\(([^)]*)\)\$'/);
  assert.ok(m, "the workflow must pattern-check AUDIT_PACK before use");
  return m[1].split("|").map((p) => p.replace(/\\/g, "").trim());
}

/** The single `case` dispatch, and the pack → npm script mapping inside it. */
function dispatchBlock() {
  const caseBlock = workflowConfig.match(/case "\$\{AUDIT_PACK\}"[\s\S]*?esac/);
  assert.ok(caseBlock, "pack selection must be a single `case` dispatch");
  const mapping = new Map();
  for (const m of caseBlock[0].matchAll(/^\s*([A-Za-z0-9+_-]+)\)\s*npm run ([A-Za-z0-9_-]+)\b/gm)) {
    mapping.set(m[1], m[2]);
  }
  return { text: caseBlock[0], mapping };
}

describe("dependency pinning", () => {
  it("pins every dependency to an exact version", () => {
    const deps = { ...(pkg.dependencies || {}), ...(pkg.devDependencies || {}) };
    assert.ok(Object.keys(deps).length > 0, "expected at least one dependency");
    for (const [name, range] of Object.entries(deps)) {
      assert.equal(
        RANGE_SPECIFIER.test(String(range)),
        false,
        `${name} must be pinned exactly, got "${range}" — a range lets two runs use different browsers`
      );
    }
  });

  it("uses @playwright/test, pinned", () => {
    const version = (pkg.devDependencies || {})["@playwright/test"];
    assert.ok(version, "@playwright/test must be a devDependency");
    assert.match(version, /^\d+\.\d+\.\d+$/);
  });

  it("no longer ignores the lockfile", () => {
    const entries = fs
      .readFileSync(path.join(e2eRoot, ".gitignore"), "utf8")
      .split("\n")
      .map((line) => line.trim())
      .filter((line) => line && !line.startsWith("#"));
    assert.ok(
      !entries.includes("package-lock.json"),
      "package-lock.json must be committed so `npm ci` can pin the runner"
    );
  });
});

describe("isolation from the Vercel build", () => {
  it("the main frontend tsconfig still excludes e2e", () => {
    // Without this, the audit tree enters `next build` and the deploy path.
    const mainTsconfig = JSON.parse(
      fs.readFileSync(path.join(repoRoot, "frontend", "tsconfig.json"), "utf8")
    );
    assert.ok(
      (mainTsconfig.exclude || []).includes("e2e"),
      "frontend/tsconfig.json must exclude e2e"
    );
  });

  it("the audit tree declares its own package identity", () => {
    assert.equal(pkg.private, true);
    assert.notEqual(pkg.name, "bainluck-frontend");
  });
});

describe("the manual workflow keeps its phase-1 boundary", () => {
  const config = workflowConfig;

  it("the comment-stripped config is not vacuous", () => {
    // Guard: if stripping ever eats the file, every `!includes` below would
    // pass for the wrong reason.
    assert.ok(config.includes("jobs:"), "stripped config lost its jobs block");
    assert.ok(config.length > 500, `stripped config is suspiciously short (${config.length})`);
  });

  it("is dispatch-only — no schedule in phase 1", () => {
    assert.ok(config.includes("workflow_dispatch:"));
    assert.ok(!/^\s{2}schedule:/m.test(config), "phase 1 must not carry a schedule trigger");
  });

  it("installs a browser with its OS dependencies", () => {
    assert.ok(config.includes("playwright install --with-deps chromium"));
  });

  it("installs with npm ci — the lockfile gate — and never npm install", () => {
    assert.ok(config.includes("npm ci"));
    assert.ok(
      !/\bnpm install\b/.test(config),
      "npm install would defeat the lockfile gate"
    );
  });

  it("holds least privilege: no write scope, no issue filing", () => {
    assert.ok(config.includes("contents: read"));
    assert.ok(!config.includes("issues: write"));
    assert.ok(!config.includes("contents: write"));
    assert.ok(!config.includes("gh issue create"));
  });

  it("always uploads artifacts, and does not swallow the upload's failure", () => {
    assert.ok(config.includes("if: always()"));
    assert.ok(
      !config.includes("continue-on-error: true"),
      "a swallowed step can turn a no-evidence run green"
    );
    assert.ok(config.includes("if-no-files-found: error"));
  });

  it("validates the manifest before it can be called green", () => {
    assert.ok(config.includes("npm run validate"));
  });

  /**
   * L2-228. `actions/setup-node` hard-fails its whole step when a configured
   * `cache-dependency-path` does not resolve — "Some specified paths were not
   * resolved, unable to cache dependencies". The workflow pointed that at
   * `frontend/e2e/package-lock.json`, which has never existed, so a pure speed
   * optimisation aborted the job at SETUP and the contract fixtures below
   * never ran at all (run 30721023236).
   *
   * This asserts the invariant rather than the current state, so restoring the
   * cache in the same commit that adds the lockfile passes automatically,
   * while re-adding it without the lockfile stays red.
   */
  it("caches only against a dependency path that actually exists", () => {
    for (const m of config.matchAll(/cache-dependency-path:\s*(\S+)/g)) {
      const target = path.join(repoRoot, m[1].replace(/^["']|["']$/g, ""));
      assert.ok(
        fs.existsSync(target),
        `cache-dependency-path "${m[1]}" does not exist — setup-node will abort the job at setup`
      );
    }
  });

  /**
   * L2-228. The contract script was `node --test "contract/*.test.js"` — the
   * glob QUOTED, so the shell could not expand it and Node had to. Node only
   * learned to glob `--test` arguments in v22; the workflow pins Node 20, where
   * that is `Could not find '.../contract/*.test.js'` and exit 1.
   *
   * So the rail's one always-on, dependency-free gate had never executed in CI
   * — it passed only on developer machines running a newer Node, which is the
   * worst possible split: green everywhere a human looks, never actually run
   * where it counts. Verified against run 30721583936.
   *
   * Unquoted, the shell expands the glob into a file list that every Node
   * version accepts.
   */
  it("lets the shell expand the contract glob, not Node", () => {
    assert.doesNotMatch(
      pkg.scripts.contract,
      /--test\s+["']/,
      "a quoted glob makes Node do the globbing, which Node 20 cannot — the gate silently never runs"
    );
  });

  it("runs the dependency-free contract fixtures before any install", () => {
    // The fixtures are placed ahead of `npm ci` on purpose: a gate that only
    // runs once a package install succeeds is a gate that gets skipped on the
    // day it matters. Reordering them behind the install would silently give
    // that up.
    const fixtures = config.indexOf("npm run contract");
    const install = config.indexOf("npm ci");
    assert.ok(fixtures > -1 && install > -1, "expected both a contract step and an npm ci step");
    assert.ok(fixtures < install, "the contract fixtures must run before npm ci");
  });

  it("pins the Node major the repo builds with", () => {
    assert.match(config, /node-version:\s*["']?20/);
  });

  it("carries no production secret", () => {
    assert.ok(!/secrets\./.test(config), "phase 1 runs anonymously, with no secret");
  });

  /**
   * The reporter writes `$AUDIT_OUT_DIR/manifest.json` unconditionally on every
   * `playwright test` run, so two invocations in one job means the second
   * OVERWRITES the first. The validator would then grade only the last pack
   * while the step summary still implied both had been proven — a green run
   * covering half of what it claimed. Packs are therefore combined into a
   * single invocation, and this pins that.
   */
  it("runs playwright exactly once, so no manifest can be overwritten", () => {
    // Every pack invocation must sit inside ONE `case` dispatch. Two separate
    // steps would each run playwright, and the second manifest would replace
    // the first.
    const { text, mapping } = dispatchBlock();
    assert.ok(mapping.size >= 1, "the dispatch must run at least one pack");

    // L2-228: the stray scan used to look for a hard-coded script list, so a
    // pack added later could be invoked outside the dispatch and go unnoticed
    // — the exact blind spot that let the `grid` allowlist gap survive. The
    // scan now derives its needles from the dispatch's own mapping.
    const scripts = [...new Set(mapping.values())].sort((a, b) => b.length - a.length);
    const needle = new RegExp(`npm run (${scripts.join("|")})\\b`, "g");

    const outsideCase = config.replace(text, "");
    const strays = [...outsideCase.matchAll(needle)];
    assert.deepEqual(
      strays.map((m) => m[0]),
      [],
      "a pack invocation outside the dispatch would clobber the manifest"
    );
  });

  it("offers the consent pack, and defaults to running it", () => {
    assert.ok(config.includes("deploy-smoke+consent"));
    assert.match(config, /default:\s*"deploy-smoke\+consent"/);
  });
});

describe("the pack scripts exist for every workflow choice", () => {
  it("advertises at least the packs this rail is known to ship", () => {
    // A floor, so that deriving from the dropdown can never degenerate into
    // "the dropdown agrees with itself" if someone empties it.
    const advertised = advertisedPacks();
    for (const pack of ["deploy-smoke", "consent", "deploy-smoke+consent", "grid", "calibration"]) {
      assert.ok(advertised.includes(pack), `the workflow no longer offers the "${pack}" pack`);
    }
  });

  it("the input allowlist accepts exactly the advertised packs", () => {
    // The L2-227 defect: `grid` was offered in the dropdown and wired into the
    // dispatch, but the validation step's allowlist never learned about it, so
    // selecting it failed the run before a browser ever opened. An advertised
    // choice that cannot execute is worse than an absent one — it reads as
    // coverage.
    assert.deepEqual(allowlistedPacks().sort(), advertisedPacks().sort());
  });

  it("the dispatch handles exactly the advertised packs", () => {
    assert.deepEqual([...dispatchBlock().mapping.keys()].sort(), advertisedPacks().sort());
  });

  it("every dispatched pack maps to a real script that runs both viewports", () => {
    for (const [pack, script] of dispatchBlock().mapping) {
      assert.ok(pkg.scripts[script], `pack "${pack}" dispatches missing npm script "${script}"`);
      assert.match(
        pkg.scripts[script],
        /--project=desktop --project=mobile/,
        `"${script}" must run both viewports`
      );
    }
  });

  it("the consent spec exists and is picked up by the consent filter", () => {
    const spec = path.join(e2eRoot, "specs", "consent.spec.ts");
    assert.ok(fs.existsSync(spec), "specs/consent.spec.ts must exist");
    const raw = fs.readFileSync(spec, "utf8");
    // The #1453 cases the queue enumerates, by journey id.
    for (const id of [
      "consent.untouched",
      "consent.decline",
      "consent.grant",
      "consent.grant_then_revoke",
      "consent.navigation",
      "consent.two_tabs",
      "consent.storage_failure",
      "consent.deferred_event",
      "consent.identity_after_denial",
      "consent.reachable",
      "consent.my_stuff_denied",
    ]) {
      assert.ok(raw.includes(`journeyId: "${id}"`), `consent pack is missing ${id}`);
    }
  });

  /**
   * L2-228. An npm script is a `playwright test <filter>` — a filter matching
   * NOTHING exits 0 having run no tests, the reporter writes a manifest with
   * zero journeys, and only `deriveRunResult([])` downstream stops that from
   * reading as green. Pinning the file the filter is meant to select keeps the
   * failure at "the spec is gone" rather than "the run proved nothing".
   */
  it("the calibration spec exists and is selected by the calibration filter", () => {
    const spec = path.join(e2eRoot, "specs", "calibration.spec.ts");
    assert.ok(fs.existsSync(spec), "specs/calibration.spec.ts must exist");
    const raw = fs.readFileSync(spec, "utf8");
    assert.ok(
      raw.includes('journeyId: "calibration.anonymous"'),
      "calibration pack is missing calibration.anonymous"
    );
    // The filter token in the npm script must actually match the filename.
    const filter = pkg.scripts.calibration.split(" ").pop();
    assert.ok(
      path.basename(spec).includes(filter),
      `"${filter}" does not select ${path.basename(spec)}`
    );
  });

  it("the grid spec exists and is selected by the grid filter", () => {
    const spec = path.join(e2eRoot, "specs", "championship-grid.spec.ts");
    assert.ok(fs.existsSync(spec), "specs/championship-grid.spec.ts must exist");
    const filter = pkg.scripts.grid.split(" ").pop();
    assert.ok(
      path.basename(spec).includes(filter),
      `"${filter}" does not select ${path.basename(spec)}`
    );
  });

  /**
   * L2-241. The two latency packs — `latency` (Discover) and `sports-latency` —
   * became dispatchable in this queue so a real mobile/desktop first-card trace
   * can be run on demand. Same L2-228 hole as grid/calibration: a `playwright
   * test <filter>` whose filter matches NOTHING exits 0 having run no tests, and
   * only `deriveRunResult([])` downstream stops that reading as green. Pin the
   * file each filter is meant to select AND the journey id its verdict rides on.
   */
  it("the discover-latency spec exists and is selected by the latency filter", () => {
    const spec = path.join(e2eRoot, "specs", "discover-latency.spec.ts");
    assert.ok(fs.existsSync(spec), "specs/discover-latency.spec.ts must exist");
    const filter = pkg.scripts.latency.split(" ").pop();
    assert.ok(
      path.basename(spec).includes(filter),
      `"${filter}" does not select ${path.basename(spec)}`
    );
    const raw = fs.readFileSync(spec, "utf8");
    assert.ok(
      raw.includes("journeyId: `discover.latency"),
      "the latency pack is missing its discover.latency journey id"
    );
  });

  it("the sports-latency spec exists and is selected by the sports-latency filter", () => {
    const spec = path.join(e2eRoot, "specs", "sports-latency.spec.ts");
    assert.ok(fs.existsSync(spec), "specs/sports-latency.spec.ts must exist");
    const filter = pkg.scripts["sports-latency"].split(" ").pop();
    assert.ok(
      path.basename(spec).includes(filter),
      `"${filter}" does not select ${path.basename(spec)}`
    );
    const raw = fs.readFileSync(spec, "utf8");
    assert.ok(
      raw.includes('journeyId: "sports.latency"'),
      "the sports-latency pack is missing its sports.latency journey id"
    );
  });

  /**
   * L2-245. The tournament-inventory pack (C139/C140). Same L2-228 hole guarded
   * for every other pack: a `playwright test <filter>` whose filter matches
   * NOTHING exits 0 having run no tests, and only `deriveRunResult([])` downstream
   * stops that reading as green. Pin the spec the filter selects AND the route
   * registry it is driven from — a spec whose journeys are all deleted, or a
   * registry emptied to zero domains, must be a red contract test, not a run that
   * proved nothing.
   */
  it("the tournament-inventory spec exists and is selected by its filter", () => {
    const spec = path.join(e2eRoot, "specs", "tournament-inventory.spec.ts");
    assert.ok(fs.existsSync(spec), "specs/tournament-inventory.spec.ts must exist");
    const filter = pkg.scripts["tournament-inventory"].split(" ").pop();
    assert.ok(
      path.basename(spec).includes(filter),
      `"${filter}" does not select ${path.basename(spec)}`
    );
    const raw = fs.readFileSync(spec, "utf8");
    // The spec is data-driven from the registry and the hub journey.
    assert.ok(
      raw.includes("TOURNAMENT_ROUTES"),
      "the tournament-inventory spec no longer iterates the route registry"
    );
    assert.ok(
      raw.includes("journeyId: HUB_ROUTE.journeyId"),
      "the tournament-inventory spec is missing its hub/adjacent-regression journey"
    );
  });

  it("the tournament route registry names at least the domains C139 requires", () => {
    // A registry emptied to zero domains would make the pack select a spec whose
    // `for (const route of TOURNAMENT_ROUTES)` loop generates no journeys — the
    // exact zero-journey false green. Pin the C139 domains the map must carry.
    const registry = path.join(e2eRoot, "fixtures", "tournamentRoutes.ts");
    assert.ok(fs.existsSync(registry), "fixtures/tournamentRoutes.ts must exist");
    const raw = fs.readFileSync(registry, "utf8");
    for (const id of [
      "tournament.awards",
      "tournament.election",
      "tournament.soccer",
      "tournament.cycling",
      "tournament.golf",
      "tournament.combat",
      "tournament.tennis",
      "tournament.f1",
      "tournament.hub",
    ]) {
      assert.ok(raw.includes(`"${id}"`), `the route registry no longer defines ${id}`);
    }
  });
});

/**
 * L2-239 Item 1 — the render-states runner.
 *
 * `scripts/l2238-render-states.js` shipped in L2-238 and could not be run:
 * Chromium cannot spawn a renderer in the authoring sandbox, so the three new
 * Discover terminal states were closed on source-level proof. A script that
 * nothing executes is documentation, and documentation is not evidence.
 *
 * These pin the two halves that keep the new workflow from becoming the same
 * thing in a different place: the runner must not be able to go green without
 * grading, and the script must not be able to grade without failing.
 */
describe("the render-states runner cannot be green without evidence", () => {
  const renderWorkflowPath = path.join(repoRoot, ".github", "workflows", "render-states.yml");
  const renderRaw = fs.readFileSync(renderWorkflowPath, "utf8");
  const renderConfig = renderRaw
    .split("\n")
    .filter((line) => !/^\s*#/.test(line))
    .join("\n");

  const scriptPath = path.join(e2eRoot, "scripts", "l2238-render-states.js");
  const script = fs.readFileSync(scriptPath, "utf8");

  it("the stripped config is not vacuous", () => {
    assert.ok(renderConfig.includes("jobs:"));
    assert.ok(renderConfig.length > 500, `suspiciously short (${renderConfig.length})`);
  });

  it("runs the committed script, not an inline reimplementation", () => {
    assert.ok(fs.existsSync(scriptPath), "scripts/l2238-render-states.js must exist");
    assert.ok(renderConfig.includes("scripts/l2238-render-states.js"));
  });

  it("the script exits non-zero when a state fails to render", () => {
    // Without this the workflow reports success on a broken render and the
    // packet's `fail` count is something a reader has to notice for themselves.
    assert.match(script, /process\.exit\(1\)/);
    assert.match(script, /result: failed\.length === 0 && !staleAllowance \? "pass" : "fail"/);
  });

  it("the script refuses a run that graded nothing", () => {
    // The retired provider concluded `success` having collected 0 of 3 modules.
    assert.match(script, /expected \$\{Object\.keys\(STATES\)\.length \* VIEWPORTS\.length\}/);
  });

  it("every state carries expectations, and both viewports are rendered", () => {
    const states = [...script.matchAll(/^\s{2}"?([a-z-]+)"?:\s*\[/gm)].map((m) => m[1]);
    for (const state of [
      "normal",
      "genuine-exhaustion",
      "unavailable-without-last-good",
      "unavailable-with-last-good",
      "unavailable-next-page",
    ]) {
      assert.ok(
        script.includes(`"${state}"`) || states.includes(state),
        `the script no longer renders the ${state} state`
      );
      assert.match(
        script.slice(script.indexOf("const EXPECTATIONS")),
        new RegExp(`["']?${state}["']?:`),
        `${state} has no expectations — it would pass by rendering nothing`
      );
    }
    assert.match(script, /width:\s*390/);
    assert.match(script, /width:\s*1440/);
  });

  it("the last-good state is reached by revalidation, not by a reload", () => {
    // The methodology defect run 30836513085 exposed. A reload is a COLD load,
    // and the web client has no on-disk last-good, so `page.reload()` rendered
    // the cold unavailable state — the assertion that cards survive could never
    // have passed, and closing it on source-level proof would have shipped a
    // fixture that proves the opposite of its own name.
    const block = script.slice(script.indexOf("const STATES"), script.indexOf("const EXPECTATIONS"));
    assert.match(block, /trigger: "swr-refresh"/);
    assert.ok(
      !/page\.reload\(/.test(script),
      "a reload cannot prove last-good survival on a surface with no persisted last-good"
    );
  });

  it("the fixture's own synthetic failures are recorded, not silently dropped", () => {
    // Next prefetches every card's detail route, and a card id that exists only
    // in a stubbed body has no page behind it. That is the fixture's shadow —
    // but the deploy-smoke rail saw the same ERR_ABORTED shape on a REAL id, so
    // the allowance must be narrow and the evidence must survive it.
    assert.match(script, /SYNTHETIC_DETAIL_ROUTE\s*=\s*\/\\\/futures\\\/4242/);
    assert.ok(script.includes("syntheticFailures"), "synthetic failures must reach the packet");
    assert.match(
      script,
      /noFirstPartyHttpErrors = httpErrors\.length === 0/,
      "the console-404 allowance must expire the moment a first-party 4xx appears"
    );
  });

  it("the known-defect allowance is declared, issue-numbered, and self-expiring", () => {
    // #1525 — first-party ERR_ABORTED on Next's RSC prefetches of REAL detail
    // routes. Orthogonal to the terminal feed states this script proves, so it
    // is allowed here rather than left to red the rail forever. The L2-235 rule
    // applies in full: an allowance that stops firing must FAIL, or it outlives
    // its reason and covers the next defect that happens to match.
    assert.match(script, /KNOWN_RSC_PREFETCH_ABORT = \{\s*\n\s*issue: \d+/);
    assert.match(script, /staleAllowance/);
    assert.match(
      script,
      /knownDefectHits === 0/,
      "an allowance that matched nothing must fail the run"
    );
    assert.match(
      script,
      /result: failed\.length === 0 && !staleAllowance \? "pass" : "fail"/,
      "a stale allowance must reach the packet's verdict, not just a log line"
    );
    // Narrow in both directions: only an aborted `?_rsc=` prefetch qualifies.
    assert.match(script, /_rsc=\/\.test\(url\) && \/ERR_ABORTED\//);
  });

  it("card-survival claims are measured against the healthy baseline", () => {
    // Run 30837447932 rendered 10 of 12 served markets in EVERY state including
    // `normal` — Discover's own grouping. An absolute count would have failed
    // the control and the states under test alike, proving nothing about either.
    const block = script.slice(script.indexOf("const EXPECTATIONS"), script.indexOf("function overlaps"));
    assert.match(block, /s\.baseline > 0 && s\.cards === s\.baseline/);
    assert.ok(
      !/s\.cards === 12/.test(block),
      "an absolute card count cannot survive client-side grouping"
    );
    assert.match(script, /if \(state === "normal"\) baseline\[vp\.name\] = seen\.cards/);
  });

  it("the packet carries the build, the viewport and a PT timestamp", () => {
    for (const field of ["commit", "generated_at_pt", "screenshot_sha256", "observed_at_pt"]) {
      assert.ok(script.includes(field), `the evidence packet is missing ${field}`);
    }
  });

  it("holds least privilege and never swallows a failure", () => {
    assert.ok(renderConfig.includes("contents: read"));
    assert.ok(!renderConfig.includes("issues: write"));
    assert.ok(!renderConfig.includes("contents: write"));
    assert.ok(
      !renderConfig.includes("continue-on-error"),
      "a swallowed render failure would turn a broken screen green"
    );
    assert.ok(renderConfig.includes("if-no-files-found: error"));
    assert.ok(!/secrets\./.test(renderConfig), "this rail runs anonymously");
  });

  it("is dispatch-only and binds the evidence to a named deployment", () => {
    assert.ok(renderConfig.includes("workflow_dispatch:"));
    assert.ok(!/^\s{2}schedule:/m.test(renderConfig));
    assert.ok(renderConfig.includes("wait-for-frontend-sha.js"), "unbound evidence names no build");
  });

  it("installs with npm ci against a cache path that exists", () => {
    assert.ok(renderConfig.includes("npm ci"));
    assert.ok(!/\bnpm install\b/.test(renderConfig));
    for (const m of renderConfig.matchAll(/cache-dependency-path:\s*(\S+)/g)) {
      const target = path.join(repoRoot, m[1].replace(/^["']|["']$/g, ""));
      assert.ok(fs.existsSync(target), `cache-dependency-path "${m[1]}" does not exist`);
    }
  });
});
