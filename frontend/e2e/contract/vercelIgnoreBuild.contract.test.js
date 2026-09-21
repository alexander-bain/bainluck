// Vercel ignored-build-step contract (#4456).
//
// ~20 Vercel deploys/hour, 17 of them PREVIEW builds nobody reads (previews are
// auth-gated, so every lane already shoots production for its LOOK, notice 4).
// `vercel-ignore-build.sh` skips those.
//
// VERCEL'S CONTRACT IS INVERTED, which is the whole reason this file exists:
//
//     exit 0  ->  SKIP the build
//     exit 1  ->  PROCEED with the build
//
// Get that backwards and the failure is not a wasted build, it is that MASTER
// STOPS DEPLOYING and the site quietly freezes at whatever was last shipped.
// The asymmetry is the same one `heroku-release-required.sh` is written around:
//
//   * wrongly SKIP a production build => the site silently stops updating.
//   * wrongly RUN a preview build     => one wasted build. Cheap.
//
// So the invariant is not "the script is clever", it is: the script only ever
// skips when it has positively identified a disposable lane preview, and builds
// in every other circumstance INCLUDING every unknown.
//
// This suite RUNS the real script with real environments rather than asserting
// on its text — CERT-2423 landed on the Heroku half precisely because a
// correct-READING script had an incorrect BEHAVIOUR. The Vercel half was graded
// as holding; this table is what stops it drifting.

const { test, describe } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const SCRIPT = path.join(REPO_ROOT, "frontend", "scripts", "vercel-ignore-build.sh");
const VERCEL_JSON = path.join(REPO_ROOT, "frontend", "vercel.json");

const BUILD = "BUILD";
const SKIP = "SKIP";

// A marker URL that cannot resolve. Injected whenever a case does not declare
// one, so no row in this file can reach bainluck.com: a suite that silently
// depended on the network would go red in CI for a reason that is not the code.
const UNREACHABLE_MARKER = "file:///nonexistent-vercel-ignore-build-marker.json";

/**
 * Run the real hook under `env` and translate Vercel's inverted exit code into
 * a word, so an assertion that reads "BUILD" cannot silently mean exit 0.
 * `cwd` defaults to the repo root; the production half is also exercised from
 * `frontend/`, which is where Vercel actually runs it.
 */
function decide(env, cwd) {
  const res = spawnSync("bash", [SCRIPT], {
    cwd: cwd || REPO_ROOT,
    // A bare environment: only what the case declares is visible, so a case can
    // never pass by inheriting VERCEL_* from the machine running the suite.
    env: {
      PATH: process.env.PATH,
      BUILD_FILTER_MARKER_URL: UNREACHABLE_MARKER,
      ...env,
    },
    encoding: "utf8",
  });
  assert.strictEqual(res.error, undefined, `script failed to run: ${res.error}`);
  if (res.status === 0) return SKIP;
  if (res.status === 1) return BUILD;
  throw new Error(
    `script exited ${res.status}, which is neither SKIP (0) nor BUILD (1): ${res.stderr}`
  );
}

/**
 * `decide`, plus the hook's own log. Used only where two different guards
 * produce the same DECISION and the distinction a reader needs — "shallow
 * clone" versus "rollback" — lives in the sentence the hook printed.
 */
function decideVerbose(env, cwd) {
  const res = spawnSync("bash", [SCRIPT], {
    cwd: cwd || REPO_ROOT,
    env: {
      PATH: process.env.PATH,
      BUILD_FILTER_MARKER_URL: UNREACHABLE_MARKER,
      ...env,
    },
    encoding: "utf8",
  });
  assert.strictEqual(res.error, undefined, `script failed to run: ${res.error}`);
  assert.ok(
    res.status === 0 || res.status === 1,
    `script exited ${res.status}, which is neither SKIP (0) nor BUILD (1): ${res.stderr}`
  );
  return { decision: res.status === 0 ? SKIP : BUILD, stdout: res.stdout };
}

// The six cases, as one table so a future edit has to change a ROW rather than
// quietly lose a branch. `why` is the fail-safe claim each row is defending.
const DECISION_TABLE = [
  {
    name: "1. the production deployment always builds",
    env: { VERCEL_ENV: "production", VERCEL_GIT_COMMIT_REF: "master" },
    expect: BUILD,
    why: "the load-bearing guard: if all else were wrong, the site still deploys",
  },
  {
    name: "2. master builds even when Vercel does not call it production",
    env: { VERCEL_ENV: "preview", VERCEL_GIT_COMMIT_REF: "master" },
    expect: BUILD,
    why: "belt and braces if the project's production branch is reconfigured",
  },
  {
    name: "3. a lane branch opts in with 'wants-preview' in the commit message",
    env: {
      VERCEL_ENV: "preview",
      VERCEL_GIT_COMMIT_REF: "program/ux-1165-something",
      VERCEL_GIT_COMMIT_MESSAGE: "fix(#4483): a thing [wants-preview]",
    },
    expect: BUILD,
    why: "the escape hatch has to actually work or lanes lose previews for good",
  },
  {
    name: "4. an unidentifiable branch builds rather than guessing",
    env: { VERCEL_ENV: "preview", VERCEL_GIT_COMMIT_REF: "" },
    expect: BUILD,
    why: "an empty ref is not proof of disposability",
  },
  {
    name: "5. a lane branch with no opt-in is the ONE case that skips",
    env: {
      VERCEL_ENV: "preview",
      VERCEL_GIT_COMMIT_REF: "program/ux-1165-something",
      VERCEL_GIT_COMMIT_MESSAGE: "fix(#4483): a thing",
    },
    expect: SKIP,
    why: "this row is the entire saving; if it flips to BUILD nothing is saved",
  },
  {
    name: "6. a bare environment — nothing set at all — builds",
    env: {},
    expect: BUILD,
    why: "a missing env var must never be the reason master stopped deploying",
  },
];

describe("#4456 — a lane push does not build a Vercel preview", () => {
  test("the decision lives in a FILE that vercel.json actually invokes", () => {
    assert.ok(fs.existsSync(SCRIPT), "vercel-ignore-build.sh must exist");
    const cfg = JSON.parse(fs.readFileSync(VERCEL_JSON, "utf8"));
    assert.strictEqual(
      cfg.ignoreCommand,
      "bash scripts/vercel-ignore-build.sh",
      "vercel.json must invoke the script, or this whole suite grades nothing"
    );
  });

  for (const row of DECISION_TABLE) {
    test(row.name, () => {
      assert.strictEqual(decide(row.env), row.expect, row.why);
    });
  }

  test("the table is not vacuous — the script can say both words", () => {
    // Hard-coding `exit 1` would pass five of the six rows above while
    // disabling the feature; hard-coding `exit 0` would stop master deploying.
    const seen = new Set(DECISION_TABLE.map((r) => decide(r.env)));
    assert.deepStrictEqual([...seen].sort(), [BUILD, SKIP]);
  });

  test("the skip case is reached by BRANCH, not by the commit message alone", () => {
    // A message-only rule would skip master builds whose message happens to
    // lack the opt-in — i.e. all of them.
    assert.strictEqual(
      decide({
        VERCEL_ENV: "preview",
        VERCEL_GIT_COMMIT_REF: "master",
        VERCEL_GIT_COMMIT_MESSAGE: "no opt-in here",
      }),
      BUILD
    );
  });
});

// ============================================================================
// #7846 — a production build only happens when the website actually changed.
//
// Build CPU is ~98% of the Vercel bill and two of the latest five READY
// production builds (21730d011a, 0c58f558f8) changed backend files only. The
// hook now skips those. The danger is exactly inverted from the preview half:
//
//   * wrongly SKIP a production build => a web change never reaches readers.
//   * wrongly RUN one                 => one wasted build. Cheap.
//
// So the table below is mostly BUILD rows. The single most important one is
// "an undeployed web change is never stranded": the comparison base is the
// commit the LIVE WEBSITE reports serving, not HEAD^, so a web change whose
// deploy failed is still in the diff on the next backend-only push.
//
// Every row drives the REAL script against a REAL throwaway git repository and
// a REAL marker document fetched over file://. Nothing is asserted about the
// script's text.
// ============================================================================

const os = require("node:os");

const TMP_DIRS = [];

function tmpdir(prefix) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
  TMP_DIRS.push(dir);
  return dir;
}

function git(cwd, ...args) {
  const res = spawnSync("git", ["-c", "commit.gpgsign=false", ...args], {
    cwd,
    encoding: "utf8",
    env: { ...process.env, GIT_TERMINAL_PROMPT: "0" },
  });
  assert.strictEqual(
    res.status,
    0,
    `git ${args.join(" ")} failed: ${res.stderr || res.stdout}`
  );
  return res.stdout.trim();
}

/** A throwaway repo shaped like this one: web inputs, and the four non-web trees. */
function makeRepo() {
  const dir = tmpdir("vib-repo-");
  git(dir, "init", "-q", "-b", "master");
  git(dir, "config", "user.email", "contract@example.com");
  git(dir, "config", "user.name", "contract");
  return dir;
}

function commit(dir, files, message) {
  for (const [rel, body] of Object.entries(files)) {
    const full = path.join(dir, rel);
    fs.mkdirSync(path.dirname(full), { recursive: true });
    fs.writeFileSync(full, body);
  }
  git(dir, "add", "-A");
  git(dir, "commit", "-q", "-m", message);
  return git(dir, "rev-parse", "HEAD");
}

const BASE_TREE = {
  "frontend/app/page.tsx": "export default function Page() { return null; }\n",
  "frontend/package.json": '{"name":"web"}\n',
  "frontend/package-lock.json": '{"lockfileVersion":3}\n',
  "frontend/next.config.mjs": "export default {};\n",
  "frontend/vercel.json": "{}\n",
  "backend/app/main.py": "app = None\n",
  "ios/Bain Luck/App.swift": "struct App {}\n",
  "docs/PRD.md": "# PRD\n",
  ".claude/handoff/QUEUE.md": "status: idle\n",
  ".github/workflows/ci.yml": "name: CI\n",
  "tools/look.sh": "#!/bin/sh\n",
};

/** Writes a marker document and returns the file:// URL the hook will fetch. */
function markerUrl(payload) {
  const dir = tmpdir("vib-marker-");
  const file = path.join(dir, "frontend-build.json");
  fs.writeFileSync(file, typeof payload === "string" ? payload : JSON.stringify(payload));
  return `file://${file}`;
}

/** The production environment Vercel sets, minus whatever a row overrides. */
function prodEnv(headSha, extra) {
  return {
    VERCEL_ENV: "production",
    VERCEL_GIT_COMMIT_REF: "master",
    VERCEL_GIT_COMMIT_SHA: headSha,
    VERCEL_GIT_COMMIT_MESSAGE: "Merge lane/001 — a thing",
    ...(extra || {}),
  };
}

describe("#7846 — a production build is skipped only when the live website is current", () => {
  test.after(() => {
    for (const dir of TMP_DIRS) fs.rmSync(dir, { recursive: true, force: true });
  });

  // --- the saving: changes that cannot affect `npm run build` ---------------
  const SKIPPABLE = [
    ["backend only", { "backend/app/main.py": "app = 1\n" }],
    ["iOS/Swift only", { "ios/Bain Luck/App.swift": "struct App { let a = 1 }\n" }],
    ["docs only", { "docs/PRD.md": "# PRD v2\n" }],
    ["lane handoff files only", { ".claude/handoff/QUEUE.md": "status: running\n" }],
    ["CI workflow only", { ".github/workflows/ci.yml": "name: CI v2\n" }],
    [
      "backend + CI workflow, the shape of the real 21730d011a build",
      { "backend/app/main.py": "app = 1\n", ".github/workflows/ci.yml": "name: CI v2\n" },
    ],
    // #7846 part b — repo-TOP-level directories, outside the `frontend/` root
    // Vercel builds in. Same class as the five above; they were just missed.
    ["lane measurement artifacts only", { "artifacts/d385/probe.py": "x = 1\n" }],
    ["repo-root lane tooling only", { "tools/look.sh": "#!/bin/sh\necho hi\n" }],
    ["repo-root scripts only", { "scripts/claim_lane_lock.py": "x = 1\n" }],
    [
      "backend + artifacts + tools, the shape of a real measurement push",
      {
        "backend/app/main.py": "app = 1\n",
        "artifacts/d385/probe.py": "x = 1\n",
        "tools/look.sh": "#!/bin/sh\necho hi\n",
      },
    ],
    // #7846 part c — INSIDE the `frontend/` root, so the "Vercel cannot read it"
    // argument does not apply; these are excluded on the measured evidence
    // recorded beside them in the hook.
    ["jest unit tests only", { "frontend/__tests__/lib/chartCeiling.test.ts": "it('x', () => {});\n" }],
    ["e2e/contract suites only", { "frontend/e2e/contract/abortRecord.contract.test.js": "// x\n" }],
    [
      "a jest test + repo-root tooling, the exact shape of the 19:41Z a3b5626f4 build",
      {
        "frontend/__tests__/teamDesignatorParityAcrossClients.test.ts": "it('x', () => {});\n",
        "tools/chart-fixture-replay-7569.mjs": "export const x = 1;\n",
      },
    ],
  ];

  for (const [label, changes] of SKIPPABLE) {
    test(`skips a production build for a ${label} change`, () => {
      const repo = makeRepo();
      const live = commit(repo, BASE_TREE, "base");
      const head = commit(repo, changes, "non-web change");
      assert.strictEqual(
        decide(prodEnv(head, { BUILD_FILTER_MARKER_URL: markerUrl({ commit: live, env: "production" }) }), repo),
        SKIP,
        "this row is the entire saving; if it flips to BUILD nothing is saved"
      );
    });
  }

  test("the pathspecs are repo-relative, so it decides the same way from frontend/", () => {
    // Vercel's root directory is `frontend/`, so this is the cwd the hook really
    // runs in. A cwd-relative pathspec would silently match nothing here and
    // every commit would look non-web — i.e. it would skip everything.
    const repo = makeRepo();
    const live = commit(repo, BASE_TREE, "base");
    const backendOnly = commit(repo, { "backend/app/main.py": "app = 1\n" }, "backend");
    const frontendSha = path.join(repo, "frontend");
    assert.strictEqual(
      decide(prodEnv(backendOnly, { BUILD_FILTER_MARKER_URL: markerUrl({ commit: live, env: "production" }) }), frontendSha),
      SKIP
    );
    const webChange = commit(repo, { "frontend/app/page.tsx": "export default function P() { return 1; }\n" }, "web");
    assert.strictEqual(
      decide(prodEnv(webChange, { BUILD_FILTER_MARKER_URL: markerUrl({ commit: live, env: "production" }) }), frontendSha),
      BUILD,
      "from frontend/ the hook must still SEE a frontend change"
    );
  });

  // --- every web build input forces a build ---------------------------------
  const MUST_BUILD_INPUTS = [
    ["frontend source", { "frontend/app/page.tsx": "export default function P() { return 1; }\n" }],
    ["a dependency manifest", { "frontend/package.json": '{"name":"web","dependencies":{}}\n' }],
    ["the dependency lockfile", { "frontend/package-lock.json": '{"lockfileVersion":3,"x":1}\n' }],
    ["the Next.js config", { "frontend/next.config.mjs": "export default { reactStrictMode: true };\n" }],
    ["the Vercel config", { "frontend/vercel.json": '{"installCommand":"npm ci"}\n' }],
    // Not a build input in any obvious sense — and that is the point. The
    // exclusion list names what is PROVABLY irrelevant; everything else,
    // including paths nobody has thought about, lands on the expensive side.
    // (`tools/` used to be this row's example; #7846 part b excluded it by name,
    // so the doctrine is pinned here by a path that is genuinely unlisted.)
    ["an unlisted top-level path", { "unlisted-top-level/x.txt": "hi\n" }],
    ["a brand-new top-level directory", { "webcomponents/x.ts": "export const x = 1;\n" }],
    // 🪤 The `:(top,exclude)scripts/` pathspec added by part b anchors at the
    // repo root. If it were ever written without `top` it would also swallow
    // `frontend/scripts/` — i.e. a change to THIS HOOK would stop forcing a
    // build and the filter could never be corrected by deploying a fix to it.
    [
      "frontend/scripts/, which top-level scripts/ must not swallow",
      { "frontend/scripts/vercel-ignore-build.sh": "#!/usr/bin/env bash\nexit 1\n" },
    ],
    // 🪤 #7846 part c excludes two directories INSIDE the build root. A commit
    // that edits a test AND the source it covers is the common case, and it is
    // the one where an over-broad exclusion strands a real web change.
    [
      "real source alongside its jest test",
      {
        "frontend/__tests__/lib/chartCeiling.test.ts": "it('x', () => {});\n",
        "frontend/lib/chartCeiling.ts": "export const ceiling = 2;\n",
      },
    ],
    // 🪤 And the mirror of the frontend/scripts/ row above: the hook's own
    // contract suite lives in `frontend/e2e/`, so part c means a contract-only
    // commit skips. That is correct — a test is not a build input — but only
    // because the hook ITSELF is still an input. If both were excluded the
    // filter could never be corrected by deploying a fix to it.
    [
      "the hook alongside the e2e suite that covers it",
      {
        "frontend/e2e/contract/vercelIgnoreBuild.contract.test.js": "// x\n",
        "frontend/scripts/vercel-ignore-build.sh": "#!/usr/bin/env bash\nexit 1\n",
      },
    ],
  ];

  for (const [label, changes] of MUST_BUILD_INPUTS) {
    test(`builds when ${label} changed`, () => {
      const repo = makeRepo();
      const live = commit(repo, BASE_TREE, "base");
      const head = commit(repo, changes, "web-relevant change");
      assert.strictEqual(
        decide(prodEnv(head, { BUILD_FILTER_MARKER_URL: markerUrl({ commit: live, env: "production" }) }), repo),
        BUILD
      );
    });
  }

  // --- the premise under part c's two in-root exclusions --------------------
  //
  // `frontend/__tests__/` and `frontend/e2e/` are excluded because `next build`
  // provably never reads them — measured by injecting a parse error into one
  // file in each and watching `npm run build` still exit 0. That is a statement
  // about THREE properties of the real repo, not about the hook. If any of them
  // changes, the exclusion starts stranding real web changes and the site
  // silently stops updating. So the premise is pinned here rather than trusted.
  test("part c's premise still holds: next build cannot read the excluded test dirs", () => {
    const nextConfig = fs.readFileSync(path.join(REPO_ROOT, "frontend", "next.config.mjs"), "utf8");

    // 1. Type-checking is off at build time, so tsconfig's `**/*.ts` — which
    //    DOES match frontend/__tests__/**/*.ts — never runs. Turn this back on
    //    and a type error in a test file fails the production build.
    assert.match(
      nextConfig,
      /ignoreBuildErrors:\s*true/,
      "next.config.mjs no longer sets typescript.ignoreBuildErrors — frontend/__tests__/ is a build input again and must come OFF the exclusion list"
    );

    // 2. No `eslint.dirs` override. Absent one, `next build` lints its defaults
    //    (app, pages, components, lib, src) and neither excluded directory is
    //    among them. Adding one that names them makes them build inputs.
    const eslintDirs = nextConfig.match(/eslint:\s*\{[^}]*dirs:\s*\[([^\]]*)\]/s);
    if (eslintDirs) {
      assert.doesNotMatch(
        eslintDirs[1],
        /__tests__|e2e/,
        "next.config.mjs now lints an excluded directory — it is a build input again"
      );
    }

    // 3. No import edge out of the build graph into either directory. A single
    //    `import ... from "../__tests__/fixtures"` in app/, components/ or lib/
    //    would pull test files into the bundle.
    const offenders = [];
    const walk = (dir) => {
      for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
        const full = path.join(dir, entry.name);
        if (entry.isDirectory()) walk(full);
        else if (/\.(ts|tsx|js|jsx|mjs)$/.test(entry.name)) {
          const src = fs.readFileSync(full, "utf8");
          if (/(?:from|require\()\s*['"][^'"]*(?:__tests__|\/e2e\/)/.test(src)) offenders.push(full);
        }
      }
    };
    for (const dir of ["app", "components", "lib"]) {
      const full = path.join(REPO_ROOT, "frontend", dir);
      if (fs.existsSync(full)) walk(full);
    }
    assert.deepStrictEqual(
      offenders,
      [],
      "build-graph source now imports from an excluded test directory, which makes it a build input"
    );
  });

  // --- the reason this compares against the LIVE commit and not HEAD^ -------
  test("an undeployed web change is never stranded by a later backend-only push", () => {
    const repo = makeRepo();
    const live = commit(repo, BASE_TREE, "base");
    // A web change whose production deploy failed or was canceled: the marker
    // still reports `live`, because nothing newer ever served.
    commit(repo, { "frontend/app/page.tsx": "export default function P() { return 1; }\n" }, "web change that never deployed");
    const backendOnly = commit(repo, { "backend/app/main.py": "app = 1\n" }, "backend only");
    const url = markerUrl({ commit: live, env: "production" });

    assert.strictEqual(
      decide(prodEnv(backendOnly, { BUILD_FILTER_MARKER_URL: url }), repo),
      BUILD,
      "HEAD^..HEAD is backend-only, but the WEBSITE is still missing the web change"
    );

    // And once more, two backend commits later: a skip never moves the live
    // commit, so the base does not drift away from the undeployed change.
    const laterBackend = commit(repo, { "backend/app/main.py": "app = 2\n" }, "more backend");
    assert.strictEqual(decide(prodEnv(laterBackend, { BUILD_FILTER_MARKER_URL: url }), repo), BUILD);
  });

  test("a genuine web deployment reaches production after a skipped commit", () => {
    const repo = makeRepo();
    const live = commit(repo, BASE_TREE, "base");
    const url = markerUrl({ commit: live, env: "production" });
    const skipped = commit(repo, { "backend/app/main.py": "app = 1\n" }, "backend only");
    assert.strictEqual(decide(prodEnv(skipped, { BUILD_FILTER_MARKER_URL: url }), repo), SKIP);
    const web = commit(repo, { "frontend/app/page.tsx": "export default function P() { return 2; }\n" }, "web");
    assert.strictEqual(
      decide(prodEnv(web, { BUILD_FILTER_MARKER_URL: url }), repo),
      BUILD,
      "the next real web change must still deploy"
    );
  });

  // --- every way of not knowing builds --------------------------------------
  test("builds when the live marker is unreachable", () => {
    const repo = makeRepo();
    commit(repo, BASE_TREE, "base");
    const head = commit(repo, { "backend/app/main.py": "app = 1\n" }, "backend");
    assert.strictEqual(
      decide(prodEnv(head, { BUILD_FILTER_MARKER_URL: `file://${path.join(repo, "no-such-marker.json")}` }), repo),
      BUILD
    );
  });

  test("builds when the marker is not a production deployment", () => {
    const repo = makeRepo();
    const live = commit(repo, BASE_TREE, "base");
    const head = commit(repo, { "backend/app/main.py": "app = 1\n" }, "backend");
    assert.strictEqual(
      decide(prodEnv(head, { BUILD_FILTER_MARKER_URL: markerUrl({ commit: live, env: "preview" }) }), repo),
      BUILD
    );
  });

  test("builds on the first deployment, when the marker reports no commit", () => {
    const repo = makeRepo();
    commit(repo, BASE_TREE, "base");
    const head = commit(repo, { "backend/app/main.py": "app = 1\n" }, "backend");
    assert.strictEqual(
      decide(prodEnv(head, { BUILD_FILTER_MARKER_URL: markerUrl({ commit: null, env: "production" }) }), repo),
      BUILD
    );
  });

  test("builds when the marker carries an abbreviation rather than a full sha", () => {
    const repo = makeRepo();
    const live = commit(repo, BASE_TREE, "base");
    const head = commit(repo, { "backend/app/main.py": "app = 1\n" }, "backend");
    assert.strictEqual(
      decide(prodEnv(head, { BUILD_FILTER_MARKER_URL: markerUrl({ commit: live.slice(0, 10), env: "production" }) }), repo),
      BUILD
    );
  });

  test("builds when the marker is not JSON at all", () => {
    const repo = makeRepo();
    commit(repo, BASE_TREE, "base");
    const head = commit(repo, { "backend/app/main.py": "app = 1\n" }, "backend");
    assert.strictEqual(
      decide(prodEnv(head, { BUILD_FILTER_MARKER_URL: markerUrl("<html>502 Bad Gateway</html>") }), repo),
      BUILD
    );
  });

  test("builds when the live commit is missing from a shallow clone", () => {
    // Vercel clones shallow. This is the expected way for the filter to decline
    // on a real deployment, so the DECISION is not the whole assertion — the log
    // line is, or a reader debugging "why does it never skip" gets the wrong
    // story. Dropping the cat-file guard leaves the decision right (the ancestry
    // check errors on an unknown rev too) and the diagnosis wrong.
    const repo = makeRepo();
    commit(repo, BASE_TREE, "base");
    const head = commit(repo, { "backend/app/main.py": "app = 1\n" }, "backend");
    const absent = "0".repeat(39) + "1";
    const run = decideVerbose(
      prodEnv(head, { BUILD_FILTER_MARKER_URL: markerUrl({ commit: absent, env: "production" }) }),
      repo
    );
    assert.strictEqual(run.decision, BUILD);
    assert.match(run.stdout, /is not in this clone \(shallow or rewritten history\)/);
  });

  test("builds when the live commit is not an ancestor of HEAD (a rollback)", () => {
    // The web inputs of the rolled-back commit are IDENTICAL to HEAD's, so the
    // diff alone says "nothing changed". Only ancestry can tell that the site is
    // serving a tree off a branch we have not reasoned about, and a skip would
    // pin production there indefinitely.
    const repo = makeRepo();
    const base = commit(repo, BASE_TREE, "base");
    git(repo, "checkout", "-q", "-b", "sidebranch");
    const sideCommit = commit(repo, { "backend/app/main.py": "app = 99\n" }, "side backend");
    git(repo, "checkout", "-q", "master");
    git(repo, "reset", "-q", "--hard", base);
    const head = commit(repo, { "backend/app/main.py": "app = 1\n" }, "backend");
    const url = markerUrl({ commit: sideCommit, env: "production" });
    assert.strictEqual(
      git(repo, "diff", "--name-only", sideCommit, head, "--", ":(top,exclude)backend/"),
      "",
      "the case is only load-bearing if the web-input diff is empty"
    );
    const run = decideVerbose(prodEnv(head, { BUILD_FILTER_MARKER_URL: url }), repo);
    assert.strictEqual(run.decision, BUILD);
    assert.match(run.stdout, /is not an ancestor of HEAD/);
  });

  test("builds a redeploy of the commit the website is already serving", () => {
    const repo = makeRepo();
    const live = commit(repo, BASE_TREE, "base");
    assert.strictEqual(
      decide(prodEnv(live, { BUILD_FILTER_MARKER_URL: markerUrl({ commit: live, env: "production" }) }), repo),
      BUILD,
      "a manual redeploy is somebody asking for this exact tree to be rebuilt"
    );
  });

  test("builds when the deployed commit cannot be resolved in this checkout", () => {
    const repo = makeRepo();
    const live = commit(repo, BASE_TREE, "base");
    assert.strictEqual(
      decide(
        prodEnv("0".repeat(39) + "2", { BUILD_FILTER_MARKER_URL: markerUrl({ commit: live, env: "production" }) }),
        repo
      ),
      BUILD
    );
  });

  test("builds when there is no git repository to compare against", () => {
    const repo = makeRepo();
    const live = commit(repo, BASE_TREE, "base");
    const head = commit(repo, { "backend/app/main.py": "app = 1\n" }, "backend");
    const notARepo = tmpdir("vib-norepo-");
    assert.strictEqual(
      decide(prodEnv(head, { BUILD_FILTER_MARKER_URL: markerUrl({ commit: live, env: "production" }) }), notARepo),
      BUILD
    );
  });

  test("builds when the comparison itself fails — a partial clone with no tree", () => {
    // THE failure direction this whole section has to get right. Vercel clones
    // are shallow and can be object-filtered: the commit resolves, ancestry
    // resolves, and `git diff` still cannot read the tree. An empty result from
    // a crashed diff is indistinguishable from "nothing changed" unless the exit
    // status is checked — and reading it as "nothing changed" would skip the
    // build. Constructed by deleting the live commit's root tree object, which
    // leaves the two cheaper guards passing.
    const repo = makeRepo();
    const live = commit(repo, BASE_TREE, "base");
    const head = commit(repo, { "backend/app/main.py": "app = 1\n" }, "backend");
    const tree = git(repo, "rev-parse", `${live}^{tree}`);
    fs.rmSync(path.join(repo, ".git", "objects", tree.slice(0, 2), tree.slice(2)));

    // The case only grades the diff guard if the two cheaper guards still pass.
    assert.strictEqual(
      spawnSync("git", ["cat-file", "-e", `${live}^{commit}`], { cwd: repo }).status,
      0,
      "the live commit object must still resolve, or this tests the wrong guard"
    );
    assert.strictEqual(
      spawnSync("git", ["merge-base", "--is-ancestor", live, head], { cwd: repo }).status,
      0,
      "ancestry must still resolve, or this tests the wrong guard"
    );

    const run = decideVerbose(
      prodEnv(head, { BUILD_FILTER_MARKER_URL: markerUrl({ commit: live, env: "production" }) }),
      repo
    );
    assert.strictEqual(run.decision, BUILD);
    assert.match(run.stdout, /git diff against live commit .* failed -> BUILD \(fail-safe\)/);
  });

  test("builds when the comparison fails against VERCEL_GIT_PREVIOUS_SHA too", () => {
    // Same corruption, but on the second gate: the live diff succeeds and says
    // "clean", so only the previous-sha diff's exit status stands between a
    // broken comparator and a skipped production build.
    const repo = makeRepo();
    const c0 = commit(repo, BASE_TREE, "base");
    const live = commit(repo, { "backend/app/main.py": "app = 1\n" }, "backend");
    const head = commit(repo, { "backend/app/main.py": "app = 2\n" }, "more backend");
    const tree = git(repo, "rev-parse", `${c0}^{tree}`);
    fs.rmSync(path.join(repo, ".git", "objects", tree.slice(0, 2), tree.slice(2)));

    const run = decideVerbose(
      prodEnv(head, {
        BUILD_FILTER_MARKER_URL: markerUrl({ commit: live, env: "production" }),
        VERCEL_GIT_PREVIOUS_SHA: c0,
      }),
      repo
    );
    assert.strictEqual(run.decision, BUILD);
    assert.match(run.stdout, /git diff against VERCEL_GIT_PREVIOUS_SHA .* failed -> BUILD \(fail-safe\)/);
  });

  test("builds when VERCEL_GIT_COMMIT_SHA is absent", () => {
    const repo = makeRepo();
    const live = commit(repo, BASE_TREE, "base");
    const env = prodEnv("", { BUILD_FILTER_MARKER_URL: markerUrl({ commit: live, env: "production" }) });
    delete env.VERCEL_GIT_COMMIT_SHA;
    assert.strictEqual(decide(env, repo), BUILD);
  });

  // --- VERCEL_GIT_PREVIOUS_SHA: an extra gate, never the authority ----------
  test("Vercel's previous-deployment sha can only add a build, never remove one", () => {
    // live = c1, previous = c0, and a web change sits between them. The marker
    // alone would skip; the disagreement is information, so we build. This is
    // why the env var's unverified failed/canceled semantics cannot cost us a
    // deploy: it is only ever read as a second reason to build.
    const repo = makeRepo();
    const c0 = commit(repo, BASE_TREE, "base");
    const c1 = commit(repo, { "frontend/app/page.tsx": "export default function P() { return 3; }\n" }, "web");
    const head = commit(repo, { "backend/app/main.py": "app = 1\n" }, "backend");
    const url = markerUrl({ commit: c1, env: "production" });
    assert.strictEqual(decide(prodEnv(head, { BUILD_FILTER_MARKER_URL: url }), repo), SKIP);
    assert.strictEqual(
      decide(prodEnv(head, { BUILD_FILTER_MARKER_URL: url, VERCEL_GIT_PREVIOUS_SHA: c0 }), repo),
      BUILD
    );
  });

  test("builds when the previous-deployment sha is unresolvable history", () => {
    const repo = makeRepo();
    const live = commit(repo, BASE_TREE, "base");
    const head = commit(repo, { "backend/app/main.py": "app = 1\n" }, "backend");
    assert.strictEqual(
      decide(
        prodEnv(head, {
          BUILD_FILTER_MARKER_URL: markerUrl({ commit: live, env: "production" }),
          VERCEL_GIT_PREVIOUS_SHA: "0".repeat(39) + "3",
        }),
        repo
      ),
      BUILD
    );
  });

  test("an agreeing previous-deployment sha does not block the saving", () => {
    const repo = makeRepo();
    const live = commit(repo, BASE_TREE, "base");
    const head = commit(repo, { "backend/app/main.py": "app = 1\n" }, "backend");
    assert.strictEqual(
      decide(
        prodEnv(head, {
          BUILD_FILTER_MARKER_URL: markerUrl({ commit: live, env: "production" }),
          VERCEL_GIT_PREVIOUS_SHA: live,
        }),
        repo
      ),
      SKIP
    );
  });

  // --- the override has to outrank the cleverness ---------------------------
  test("'force-build' in the commit message builds a commit that would be skipped", () => {
    const repo = makeRepo();
    const live = commit(repo, BASE_TREE, "base");
    const head = commit(repo, { "backend/app/main.py": "app = 1\n" }, "backend");
    const url = markerUrl({ commit: live, env: "production" });
    assert.strictEqual(decide(prodEnv(head, { BUILD_FILTER_MARKER_URL: url }), repo), SKIP);
    assert.strictEqual(
      decide(
        prodEnv(head, { BUILD_FILTER_MARKER_URL: url, VERCEL_GIT_COMMIT_MESSAGE: "chore: nudge [force-build]" }),
        repo
      ),
      BUILD
    );
  });

  test("master is filtered even when Vercel does not call the environment production", () => {
    const repo = makeRepo();
    const live = commit(repo, BASE_TREE, "base");
    const head = commit(repo, { "backend/app/main.py": "app = 1\n" }, "backend");
    const env = prodEnv(head, { BUILD_FILTER_MARKER_URL: markerUrl({ commit: live, env: "production" }) });
    env.VERCEL_ENV = "preview";
    assert.strictEqual(decide(env, repo), SKIP);
  });

  test("a lane preview never reaches the production filter", () => {
    // The preview half must stay exactly as it was: no marker fetch, no git.
    const repo = makeRepo();
    const live = commit(repo, BASE_TREE, "base");
    const head = commit(repo, { "frontend/app/page.tsx": "export default function P() { return 4; }\n" }, "web");
    assert.strictEqual(
      decide(
        {
          VERCEL_ENV: "preview",
          VERCEL_GIT_COMMIT_REF: "latency/lat874-something",
          VERCEL_GIT_COMMIT_SHA: head,
          VERCEL_GIT_COMMIT_MESSAGE: "fix(#7846): a thing",
          BUILD_FILTER_MARKER_URL: markerUrl({ commit: live, env: "production" }),
        },
        repo
      ),
      SKIP,
      "a frontend change on a lane branch is still a disposable preview"
    );
  });
});
