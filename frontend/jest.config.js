// #2462 — pin the timezone HERE, before anything else, and see
// `jest.setup.timezone.js` for why the suite needs a fixed zone at all.
//
// This line looks like it belongs in the setup file, and it was written there
// first. It does not work there: jest builds each test file's `vm` realm BEFORE
// running `setupFiles`, and that realm's `Date` keeps the zone it was born
// with, so the assignment became a silent no-op (measured: `getTimezoneOffset()`
// still 480 under `TZ=US/Pacific`). This module is evaluated in the main process
// while the config is loaded — before any realm exists and before any worker is
// forked — so both the in-band realm and the forked workers, which inherit
// `process.env`, are born in UTC. `jest.setup.timezone.js` then *proves* that
// inside the realm rather than trusting it.
process.env.TZ = 'UTC';

/** @type {import('ts-jest').JestConfigWithTsJest} */
module.exports = {
  preset: 'ts-jest',
  testEnvironment: 'node',
  roots: ['<rootDir>'],
  testMatch: ['**/__tests__/**/*.test.ts', '**/__tests__/**/*.test.tsx'],

  // L2-233. This suite gates deploys now, so the two settings below are load
  // bearing, and `__tests__/lib/ciJestGate.test.ts` asserts they stay that way.
  //
  // `passWithNoTests` is deliberately ABSENT rather than set to false: jest
  // already exits non-zero when it collects nothing, and the failure mode this
  // guards against is a broken `testMatch` turning the gate into a no-op that
  // still reports success. Absence is the safe default; naming it here would
  // only create a line someone can flip.
  //
  // Watchman is off because it is not a test dependency — it is a filesystem
  // watcher jest probes for even in `--ci` runs. It is absent on the GitHub
  // runner (jest falls back silently) and present-but-sandboxed on the
  // development machine, where the probe fails with an unhandled 'error' event
  // that kills the run before a single test executes. Off means the local and
  // the CI command are the same command.
  watchman: false,

  // #2462: the timezone pin runs FIRST. Three suites assert rendered wall-clock
  // copy and were green only in UTC, so `npx jest` was red for any developer
  // outside it. Both files explain themselves; neither is optional.
  setupFiles: [
    '<rootDir>/jest.setup.timezone.js',
    '<rootDir>/jest.setup.network.js',
  ],

  moduleNameMapper: {
    // MUST precede the `^@/` alias: that alias matches
    // `@/app/politics/politics.module.css` and would hand ts-jest raw CSS,
    // which dies on `Unexpected token '.'`. See the proxy's own header.
    '\\.module\\.css$': '<rootDir>/__tests__/helpers/cssModuleProxy.js',
    '^@/(.*)$': '<rootDir>/$1',
  },
  transform: {
    '^.+\\.tsx?$': ['ts-jest', {
      tsconfig: {
        ...require('./tsconfig.json').compilerOptions,
        jsx: 'react-jsx',
        module: 'commonjs',
      },
    }],
  },
};
