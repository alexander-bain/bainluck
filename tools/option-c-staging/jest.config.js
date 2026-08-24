/**
 * Standalone jest config for the option-C staging generator (UX-P122 item C).
 *
 * ## Why jest, for a measurement script
 *
 * The whole point of this sweep is that the numbers come from the SAME functions
 * the page calls — `normalizeCat`, `aggregateBuckets`, `cohortFilterFor`, `ece`.
 * A Python or hand-rolled JS reimplementation would be measuring a copy, and this
 * lane has been bitten by exactly that (a guard that "asserts against a copy of
 * it" is the reason `calibrationCategories.ts` was extracted in the first place).
 * jest + ts-jest is the only TS runtime this repo actually has installed, so it
 * is the runtime that can import the real modules through the `@/` alias.
 *
 * ## Why the suffix is `.sweep.ts` and not `.test.ts`
 *
 * The deploy gate is `cd frontend && npx jest`, whose `testMatch` selects
 * `.test.ts` / `.test.tsx` files under `__tests__`, rooted at `frontend/`. This
 * file lives outside `frontend/`, so it is already unreachable — but the suffix makes
 * it unreachable by construction rather than by directory accident. A measurement
 * script that fails because production data changed must never be able to turn
 * the deploy gate red.
 *
 * `rootDir` is the repo root so `<rootDir>/frontend/$1` can resolve the `@/`
 * alias the frontend's own tsconfig defines; `roots` names both trees so jest
 * will look for the sweep here and still resolve imports over there.
 */
const path = require("path");

const repoRoot = path.resolve(__dirname, "..", "..");
const frontend = path.join(repoRoot, "frontend");

// `rootDir` is the repo root but `node_modules` lives under `frontend/` (it is a
// symlink into the master worktree). jest resolves a bare `preset:` / transformer
// name relative to `rootDir`, which has no `node_modules`, so both are resolved to
// absolute paths from the frontend tree instead. `preset` is dropped entirely —
// all it would supply is the transform and a testMatch, and both are set here.
const tsJest = require.resolve("ts-jest", { paths: [frontend] });

module.exports = {
  testEnvironment: "node",
  rootDir: repoRoot,
  roots: ["<rootDir>/tools/option-c-staging", "<rootDir>/frontend"],
  testMatch: ["**/tools/option-c-staging/**/*.sweep.ts"],
  watchman: false,
  moduleDirectories: ["node_modules", path.join(frontend, "node_modules")],
  moduleNameMapper: {
    "^@/(.*)$": "<rootDir>/frontend/$1",
  },
  transform: {
    "^.+\\.tsx?$": [
      tsJest,
      {
        tsconfig: {
          ...require(path.join(frontend, "tsconfig.json")).compilerOptions,
          jsx: "react-jsx",
          module: "commonjs",
        },
      },
    ],
  },
};
