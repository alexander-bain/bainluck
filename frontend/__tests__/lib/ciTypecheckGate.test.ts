/**
 * L2-234 — `tsc --noEmit` is a deploy gate now, and this keeps it one.
 *
 * ## What was wrong
 *
 * TypeScript has never been enforced anywhere in this project. `npm run build`
 * is the ESLint gate; `next.config.mjs` sets `typescript.ignoreBuildErrors:
 * true`, so `next build` passes straight through type errors (gotcha #10), and
 * `ts-jest` runs under `isolatedModules: true`, which transpiles without
 * type-checking. A missing or wrong type could — and did — deploy green.
 *
 * Running `tsc --noEmit` produced 4,612 errors, of which 4,491 were the jest
 * globals: `@types/jest` was undeclared in exactly the way `jest` and `ts-jest`
 * had been before L2-233. `expect` alone accounted for 2,716. Nobody could read
 * that output, so nobody did, so the 89 real errors underneath went unseen.
 *
 * ## Why the gate is fail-on-new rather than clean
 *
 * 89 errors remain after declaring the types. A clean gate today reds every
 * push until all 89 are cleared, and the predictable end of a step that reds
 * every push is `|| true`. So the debt is counted per file in
 * `typecheck-baseline.json`, owned by issue #1521, and frozen — and one error
 * more than that fails.
 *
 * ## What this file guards
 *
 * The ways the gate can come apart while still reporting green: the baseline
 * quietly absorbing new debt, the ratchet slipping upward, the census
 * miscounting, the step being neutered by a flag. Each is a cheap edit, and
 * each leaves a passing badge over an unchecked codebase — worse than no gate,
 * because it is believed.
 *
 * ## Why the workflow shape is ALSO checked from `frontend/e2e/contract`
 *
 * Same circularity as L2-233: a jest test asserting a CI step exists dies with
 * that step. So "ci.yml still runs the typecheck, in a job deploy depends on"
 * is duplicated into `e2e/contract/typecheckGate.contract.test.js`, in the
 * dependency-free `node --test` job that `deploy: needs:` separately lists.
 * Everything below that only matters when the gate IS running lives here alone.
 */
import * as fs from "fs";
import * as path from "path";

const { parse, check } = require("../../scripts/tsc-census.js") as {
  parse: (text: string) => Census;
  check: (current: Census, baseline: Census) => number;
};

type Census = {
  total: number;
  byFile: Record<string, number>;
  byCode: Record<string, number>;
};

const REPO_ROOT = path.resolve(__dirname, "../..", "..");
const FRONTEND = path.resolve(__dirname, "../..");
const CI_YML = path.join(REPO_ROOT, ".github", "workflows", "ci.yml");
const BASELINE = path.join(FRONTEND, "typecheck-baseline.json");

const read = (file: string): string => {
  if (!fs.existsSync(file)) {
    throw new Error(
      `L2-234 gate could not read ${path.relative(REPO_ROOT, file)}. ` +
        "If the file moved, update this guard — do not delete the check.",
    );
  }
  return fs.readFileSync(file, "utf8");
};

/**
 * Drop whole-line YAML comments before any text assertion. L2-233's guards both
 * failed on their own first run by matching their own prose about the flags
 * they forbid; the step this file guards carries the same kind of comment.
 */
const stripComments = (text: string): string =>
  text
    .split("\n")
    .filter((l) => !/^\s*#/.test(l))
    .join("\n");

function jobBlock(yaml: string, jobName: string): string {
  const lines = yaml.split("\n");
  const start = lines.findIndex((l) => l === `  ${jobName}:`);
  if (start === -1) {
    throw new Error(
      `ci.yml has no top-level job named "${jobName}". If it was renamed, update ` +
        "this guard and e2e/contract/typecheckGate.contract.test.js together.",
    );
  }
  const rest = lines.slice(start + 1);
  let end = rest.findIndex((l) => /^ {2}\S/.test(l));
  if (end === -1) end = rest.length;
  return stripComments(rest.slice(0, end).join("\n"));
}

describe("L2-234: the typecheck gate is wired", () => {
  const ci = read(CI_YML);
  const frontendBuild = jobBlock(ci, "frontend-build");

  it("frontend-build runs `npm run typecheck`", () => {
    expect(frontendBuild).toContain("npm run typecheck");
  });

  it("runs it after the build, so generated route types are in the program", () => {
    // `.next/types/**/*.ts` is in tsconfig's `include` but only exists after a
    // build. Checking before it would silently check a smaller program than a
    // developer does locally, and the two censuses would drift apart.
    const build = frontendBuild.indexOf("npm run build");
    const typecheck = frontendBuild.indexOf("npm run typecheck");
    expect(build).toBeGreaterThanOrEqual(0);
    expect(typecheck).toBeGreaterThan(build);
  });

  it("no step in frontend-build can fail without failing the job", () => {
    expect(frontendBuild).not.toMatch(/continue-on-error/);
  });

  it("deploy authority still depends on the job that runs it", () => {
    const deploy = jobBlock(ci, "deploy");
    const needs = /needs:\s*\[([^\]]*)\]/.exec(deploy);
    expect(needs).not.toBeNull();
    expect(needs![1].split(",").map((s) => s.trim())).toContain("frontend-build");
  });

  it("the script cannot swallow its own exit code", () => {
    // `|| true` is the one edit that leaves every visible line of the gate in
    // place while making it unconditionally green.
    const pkg = JSON.parse(read(path.join(FRONTEND, "package.json")));
    for (const name of ["typecheck", "typecheck:baseline"]) {
      expect(pkg.scripts).toHaveProperty(name);
      expect(pkg.scripts[name]).not.toMatch(/\|\|\s*(true|exit\s+0)|;\s*exit\s+0|--?\bforce\b/);
    }
    // And the CI step invokes the checking script, not the one that REWRITES
    // the baseline — which would make every run green by definition.
    expect(frontendBuild).not.toContain("typecheck:baseline");
  });
});

describe("L2-234: @types/jest is declared, so the census is readable", () => {
  const pkg = JSON.parse(read(path.join(FRONTEND, "package.json")));

  it("package.json declares it", () => {
    // Undeclared, `tsc --noEmit` reports 4,491 missing-global errors across
    // every test file and buries the 89 real ones.
    expect(pkg.devDependencies).toHaveProperty("@types/jest");
  });

  it("the lockfile carries it, so `npm ci` does not fail outright", () => {
    const lock = JSON.parse(read(path.join(FRONTEND, "package-lock.json")));
    expect(Object.keys(lock.packages ?? {})).toContain("node_modules/@types/jest");
  });

  it("its major matches the installed jest, so the globals it declares are real", () => {
    // @types/jest 29 against jest 30 type-checks fine and describes a different
    // runtime — the failure mode is tests that compile and then behave
    // unexpectedly, which no red build would report.
    const lock = JSON.parse(read(path.join(FRONTEND, "package-lock.json")));
    const types = lock.packages["node_modules/@types/jest"].version.split(".")[0];
    const jest = lock.packages["node_modules/jest"].version.split(".")[0];
    expect(types).toBe(jest);
  });
});

describe("L2-234: the baseline is a real, owned, current inventory", () => {
  const baseline: Census & { _meta?: Record<string, string> } = JSON.parse(read(BASELINE));

  it("names an owner, so the debt is somebody's and not nobody's", () => {
    // A count with no owner is a number that grows. The whole justification for
    // freezing 89 errors instead of fixing them is that an issue tracks them.
    expect(baseline._meta?.owner).toMatch(/github\.com\/.+\/issues\/\d+/);
  });

  it("its total agrees with its own per-file counts", () => {
    const summed: string = Object.values(baseline.byFile).reduce((a, b) => a + b, 0);
    expect(baseline.total).toBe(summed);
  });

  it("holds no entry for a file that no longer exists", () => {
    // A deleted file's allowance would otherwise sit in the baseline forever,
    // and `check` reads a missing file as 0 — which trips the downward ratchet
    // rather than passing silently, but the message would be confusing.
    const missing = Object.keys(baseline.byFile).filter(
      (f) => !fs.existsSync(path.join(FRONTEND, f)),
    );
    expect(missing).toEqual([]);
  });

  it("does not baseline away the calibration guards L2-231..233 added", () => {
    // These are the suites that took the calibration page dark twice on
    // 2026-08-02 and were put on the gate to stop it happening again. They
    // typecheck clean today; letting them acquire a silent allowance here is
    // exactly how that protection would rot.
    const protectedFiles = [
      "__tests__/lib/calibrationContract.test.ts",
      "__tests__/lib/calibrationMath.test.ts",
      "__tests__/components/calibrationAuditHooks.test.tsx",
      "__tests__/lib/ciJestGate.test.ts",
      "__tests__/lib/ciTypecheckGate.test.ts",
    ];
    for (const f of protectedFiles) {
      expect(fs.existsSync(path.join(FRONTEND, f))).toBe(true);
      expect(baseline.byFile[f] ?? 0).toBe(0);
    }
  });
});

describe("L2-234: the census tool counts what it claims to", () => {
  // The gate is only as trustworthy as this parser. A regex that also matched
  // tsc's indented elaboration lines would inflate every count; one that missed
  // a path shape would deflate them, which is the direction that lets real
  // errors through.
  const SAMPLE = [
    "app/foo/page.tsx(12,3): error TS2322: Type 'number' is not assignable to type 'string'.",
    "  Type 'number' is not assignable to type 'string'.",
    "app/foo/page.tsx(40,1): error TS2339: Property 'x' does not exist on type 'Y'.",
    "components/Bar.tsx(7,7): error TS2322: nope",
    "app/with spaces/[id]/page.tsx(1,1): error TS18047: 'items' is possibly 'null'.",
    "",
    "Found 4 errors in 3 files.",
  ].join("\n");

  it("counts one error per anchored line and ignores elaboration", () => {
    const c = parse(SAMPLE);
    expect(c.total).toBe(4);
    expect(c.byFile).toEqual({
      "app/foo/page.tsx": 2,
      "app/with spaces/[id]/page.tsx": 1,
      "components/Bar.tsx": 1,
    });
    expect(c.byCode).toEqual({ TS2322: 2, TS2339: 1, TS18047: 1 });
  });

  it("ignores tsc's trailing summary line", () => {
    // "Found 4 errors in 3 files." must not become a fifth error.
    expect(parse("Found 4 errors in 3 files.").total).toBe(0);
  });

  it("reads clean output as clean", () => {
    expect(parse("").total).toBe(0);
  });

  it("passes when the census matches the baseline exactly", () => {
    const c = parse(SAMPLE);
    expect(check(c, c)).toBe(0);
  });

  it("fails when a file gains an error", () => {
    const baseline = parse(SAMPLE);
    const worse = parse(`${SAMPLE}\ncomponents/Bar.tsx(9,1): error TS2322: new`);
    expect(check(worse, baseline)).toBe(1);
  });

  it("fails when a NEW file has errors, even if the total is unchanged", () => {
    // The reason the comparison is per file and not on the total: otherwise
    // fixing one error in A buys silent room to add one to B.
    const baseline = parse(SAMPLE);
    const shifted = parse(
      SAMPLE.replace("components/Bar.tsx(7,7): error TS2322: nope", "components/New.tsx(7,7): error TS2322: nope"),
    );
    expect(shifted.total).toBe(baseline.total);
    expect(check(shifted, baseline)).toBe(1);
  });

  it("fails when errors are fixed but the baseline still counts them", () => {
    // The upward ratchet. A stale-high baseline is headroom.
    const baseline = parse(SAMPLE);
    const better = parse(SAMPLE.split("\n").filter((l) => !l.startsWith("components/Bar.tsx")).join("\n"));
    expect(check(better, baseline)).toBe(1);
  });
});
