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

  setupFiles: ['<rootDir>/jest.setup.network.js'],

  moduleNameMapper: {
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
