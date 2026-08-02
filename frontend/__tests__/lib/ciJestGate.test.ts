/**
 * L2-233 — the frontend unit suite is a deploy gate, and this keeps it one.
 *
 * ## What was wrong
 *
 * `frontend/__tests__` holds 116 suites and 1,393 assertions, and until this
 * queue not one of them could stop a bad commit. Two independent reasons, and
 * fixing either alone would have achieved nothing:
 *
 *   1. No workflow ran jest. `ci.yml` ran backend pytest, `npm run build`
 *      (ESLint only — `next.config.mjs` sets `typescript.ignoreBuildErrors:
 *      true`, so it is not even a TypeScript gate), and the browser rail's
 *      `node --test` fixtures.
 *   2. `jest` and `ts-jest` were not declared. They existed in the working
 *      `node_modules` on the development machine but appeared in neither
 *      `package.json` nor `package-lock.json` — the only jest-shaped entry in
 *      the lock was `jest-worker`, a transitive of next/terser. A step running
 *      `npx jest` after `npm ci` would have found no jest at all.
 *
 * ## What this file guards
 *
 * The ways this gate can come back apart while still reporting green. Each is a
 * real, cheap-to-make edit — a flag added to quiet a red build, a `testMatch`
 * typo, an `.only` left in during debugging — and each would leave a passing CI
 * badge over an unrun suite. That is strictly worse than no gate, because it is
 * believed.
 *
 * ## Why the workflow shape is ALSO checked from `frontend/e2e/contract`
 *
 * A jest test that asserts jest runs in CI is circular: delete the CI step and
 * you delete the check that would have caught it. So the one assertion that
 * cannot live only here — "ci.yml still invokes jest, in a job deploy depends
 * on" — is duplicated into `e2e/contract/jestGate.contract.test.js`, which runs
 * in the dependency-free `node --test` job that is separately in `deploy:
 * needs:`. Removing the jest step reddens that fixture. The rest of the
 * invariants below are non-circular (they only matter when jest IS running) and
 * live here alone.
 */
import * as fs from "fs";
import * as path from "path";

const REPO_ROOT = path.resolve(__dirname, "../..", "..");
const FRONTEND = path.resolve(__dirname, "../..");
const CI_YML = path.join(REPO_ROOT, ".github", "workflows", "ci.yml");
const TESTS_DIR = path.join(FRONTEND, "__tests__");

/**
 * Census at authoring (2026-08-02): 116 suites, 1,393 tests, 1.8s cold on the
 * development machine. The floor is deliberately well under the real number —
 * it is a tripwire for "collection broke and the gate silently emptied", not a
 * coverage target that has to be edited every time a file is added or removed.
 */
const MIN_TEST_FILES = 100;

const read = (file: string): string => {
  if (!fs.existsSync(file)) {
    throw new Error(
      `L2-233 gate could not read ${path.relative(REPO_ROOT, file)}. ` +
        "If the file moved, update this guard — do not delete the check.",
    );
  }
  return fs.readFileSync(file, "utf8");
};

/**
 * Drop whole-line YAML comments before any text assertion.
 *
 * Found by this guard on its first run: the CI step added in L2-233 carries a
 * comment saying it must never gain a `--passWithNoTests` or a
 * `continue-on-error`, and the naive scan matched that sentence and failed. A
 * guard that reads prose as configuration is a guard that fires on
 * documentation — including documentation of itself.
 */
const stripComments = (text: string): string =>
  text
    .split("\n")
    .filter((l) => !/^\s*#/.test(l))
    .join("\n");

/** The same, for the JS config file — whose comments also name these flags. */
const stripJsComments = (text: string): string =>
  text
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n")
    .filter((l) => !/^\s*\/\//.test(l))
    .join("\n");

/**
 * Pull one top-level job's block out of a GitHub Actions workflow by
 * indentation. Deliberately not a YAML parse: this suite has no dependencies
 * beyond what the frontend already installs, and the shape being read is two
 * levels deep and stable. A missing job throws rather than yielding "" — a
 * guard that quietly matches nothing is the failure mode this whole file is
 * about.
 */
function jobBlock(yaml: string, jobName: string): string {
  const lines = yaml.split("\n");
  const start = lines.findIndex((l) => l === `  ${jobName}:`);
  if (start === -1) {
    throw new Error(
      `ci.yml has no top-level job named "${jobName}". If it was renamed, update ` +
        "this guard and e2e/contract/jestGate.contract.test.js together.",
    );
  }
  const rest = lines.slice(start + 1);
  let end = rest.findIndex((l) => /^ {2}\S/.test(l));
  if (end === -1) end = rest.length;
  return stripComments(rest.slice(0, end).join("\n"));
}

function testFiles(dir: string, acc: string[] = []): string[] {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) testFiles(full, acc);
    else if (/\.test\.tsx?$/.test(entry.name)) acc.push(full);
  }
  return acc;
}

describe("L2-233: the jest deploy gate is wired", () => {
  const ci = read(CI_YML);
  const frontendBuild = jobBlock(ci, "frontend-build");

  it("frontend-build runs the suite through `npm run test:ci`", () => {
    expect(frontendBuild).toContain("npm run test:ci");
  });

  it("runs the suite only AFTER the lockfile install, so jest exists", () => {
    const install = frontendBuild.indexOf("npm ci");
    const test = frontendBuild.indexOf("npm run test:ci");
    expect(install).toBeGreaterThanOrEqual(0);
    expect(test).toBeGreaterThan(install);
  });

  it("deploy authority still depends on the job that runs it", () => {
    const deploy = jobBlock(ci, "deploy");
    const needs = /needs:\s*\[([^\]]*)\]/.exec(deploy);
    expect(needs).not.toBeNull();
    expect(needs![1].split(",").map((s) => s.trim())).toContain("frontend-build");
  });

  it("no step in frontend-build can fail without failing the job", () => {
    // `continue-on-error: true` is the single edit that turns any gate into
    // decoration while leaving every other line of it in place.
    expect(frontendBuild).not.toMatch(/continue-on-error/);
  });
});

describe("L2-233: the gate cannot report success on nothing", () => {
  const pkg = JSON.parse(read(path.join(FRONTEND, "package.json")));
  const jestConfig = read(path.join(FRONTEND, "jest.config.js"));
  const ci = stripComments(read(CI_YML));

  it("declares jest and ts-jest, so `npm ci` installs them", () => {
    // This is the defect that made the suite laptop-only. `npx jest` on a
    // clean checkout without these two resolves nothing.
    expect(pkg.devDependencies).toHaveProperty("jest");
    expect(pkg.devDependencies).toHaveProperty("ts-jest");
  });

  it("the lockfile carries them, so `npm ci` does not fail outright", () => {
    // package.json and package-lock.json disagreeing is not a soft problem:
    // `npm ci` exits non-zero, which reds frontend-build on every push.
    const lock = JSON.parse(read(path.join(FRONTEND, "package-lock.json")));
    expect(Object.keys(lock.packages ?? {})).toEqual(
      expect.arrayContaining(["node_modules/jest", "node_modules/ts-jest"]),
    );
  });

  it("nothing anywhere passes --passWithNoTests", () => {
    // The one flag that makes "collected zero tests" a green run.
    for (const [name, source] of [
      ["ci.yml", ci],
      ["package.json scripts", JSON.stringify(pkg.scripts)],
      ["jest.config.js", stripJsComments(jestConfig)],
    ] as const) {
      expect(`${name}: ${source}`).not.toMatch(/passWithNoTests/);
    }
  });

  it("the CI script does not watch, and does not rewrite snapshots", () => {
    const script: string = pkg.scripts["test:ci"];
    expect(script).toContain("--ci");
    expect(script).not.toMatch(/--watch\b|--watchAll\b/);
    expect(script).not.toMatch(/(^|\s)(-u|--updateSnapshot)(\s|$)/);
  });

  it("collection still finds the suite", () => {
    const files = testFiles(TESTS_DIR);
    expect(files.length).toBeGreaterThanOrEqual(MIN_TEST_FILES);
  });

  it("every test file on disk is matched by testMatch", () => {
    // A `testMatch` edit that stops matching a subdirectory does not fail —
    // jest just collects less and still reports green. This compares the
    // pattern's own extensions and root against what is actually there.
    const relative = testFiles(TESTS_DIR).map((f) =>
      path.relative(FRONTEND, f).split(path.sep).join("/"),
    );
    const unmatched = relative.filter((f) => !/^__tests__\/.+\.test\.tsx?$/.test(f));
    expect(unmatched).toEqual([]);
    expect(jestConfig).toContain("'**/__tests__/**/*.test.ts'");
    expect(jestConfig).toContain("'**/__tests__/**/*.test.tsx'");
  });

  it("no suite is focused", () => {
    // `.only` left in after debugging silently reduces a 1,393-test gate to
    // one test, and reports green for it.
    const offenders: string[] = [];
    for (const file of testFiles(TESTS_DIR)) {
      const source = fs.readFileSync(file, "utf8");
      // This guard's own prose names the patterns; skip self-matching.
      if (file === __filename) continue;
      if (/\b(describe|it|test)\.only\b|\bfdescribe\s*\(|\bfit\s*\(/.test(source)) {
        offenders.push(path.relative(FRONTEND, file));
      }
    }
    expect(offenders).toEqual([]);
  });

  it("the network guard is installed", () => {
    expect(jestConfig).toContain("setupFiles");
    expect(jestConfig).toContain("jest.setup.network.js");
    expect(fs.existsSync(path.join(FRONTEND, "jest.setup.network.js"))).toBe(true);
    // And it is live in THIS process — the assertion the config check cannot
    // make. If setupFiles ever silently stops loading, this is what says so.
    expect(() => (globalThis as unknown as { fetch: () => void }).fetch()).toThrow(
      /Network access is blocked/,
    );
  });
});
