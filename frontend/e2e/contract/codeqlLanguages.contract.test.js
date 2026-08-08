"use strict";

const { describe, it } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

/**
 * #1591 — CodeQL must actually analyse something.
 *
 * ## What happened
 *
 * `codeql.yml` passed `language:` (singular) to `github/codeql-action/init@v3`,
 * whose input is `languages:` (plural). GitHub Actions does not reject an
 * unknown input; it warns and drops it:
 *
 *   ##[warning]Unexpected input(s) 'language', valid inputs are
 *     [... 'languages' ...]
 *
 * With nothing pinned, init autodetects the whole repo:
 *
 *   Autodetected languages: python, javascript, swift, actions
 *   ##[error]Swift analysis is only supported on macOS runner images.
 *
 * `ios/` makes Swift autodetect; Swift needs macOS; the abort is in `init`,
 * before analysis, so it killed the python and javascript-typescript jobs too.
 * Eight consecutive red runs, both languages unscanned.
 *
 * ## Why a guard, and why THIS guard
 *
 * The tempting assertion is "Swift is not in the matrix". That would be a guard
 * against the symptom, and it would have passed happily throughout the outage —
 * Swift was never in the matrix. The defect was an input name.
 *
 * So the class being guarded is **a silently-ignored workflow input**: a typo
 * that a schema would have caught at author time but a YAML workflow only warns
 * about at run time. The same slip in `queries:`/`query:` or `config-file:`
 * would be equally invisible.
 *
 * ## Why it lives here
 *
 * CodeQL is deliberately NOT a required check (it should not gate deploys), and
 * that is precisely why the breakage lasted days: nothing surfaced its red. A
 * non-blocking workflow cannot guard itself. This suite is dependency-free
 * `node --test`, runs as `e2e-contract` on every push, and `deploy: needs:` it —
 * the same reasoning that puts `jestGate` and `typecheckGate` here.
 *
 * This does NOT make CodeQL's findings block a deploy. It makes CodeQL's
 * *ability to run at all* block a deploy, which is a different and much cheaper
 * promise: a red CodeQL still merges, a structurally dead CodeQL does not.
 *
 * Read as text, matched by indentation, consistent with the sibling fixtures:
 * no dependencies by design, and a rename throws with the rename named.
 */

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const CODEQL_YML = path.join(REPO_ROOT, ".github", "workflows", "codeql.yml");

function readWorkflow() {
  assert.ok(
    fs.existsSync(CODEQL_YML),
    `.github/workflows/codeql.yml is missing. If CodeQL was removed on purpose, delete this fixture in the same commit and say so — do not let it fail as a mystery.`
  );
  return fs.readFileSync(CODEQL_YML, "utf8");
}

/** Strip full-line `#` comments so prose about the bug cannot satisfy a check. */
function codeOf(text) {
  return text
    .split("\n")
    .filter((line) => !/^\s*#/.test(line))
    .join("\n");
}

/**
 * The `with:` inputs of the `codeql-action/init` step, and only those.
 *
 * Scoping matters, and the first draft of this fixture got it wrong: a
 * whole-file search for `language:` also matches the MATRIX KEY
 * (`        language: ["python", "javascript-typescript"]`), which is correct
 * YAML that must stay. Flagging it would have made this guard fail on the fixed
 * workflow — a false positive that would have been "fixed" by deleting the
 * matrix, i.e. by breaking the thing the guard exists to protect.
 *
 * So: find the init step, take its lines up to the next step at the same
 * indent, and assert only inside that.
 */
function initStepInputs(text) {
  const lines = codeOf(text).split("\n");
  const start = lines.findIndex((l) => /uses:\s*github\/codeql-action\/init/.test(l));
  assert.notEqual(
    start,
    -1,
    "no `github/codeql-action/init` step found in codeql.yml — it was renamed or removed; update this fixture in the same commit rather than leaving it to fail as a mystery."
  );
  const rest = lines.slice(start + 1);
  const nextStep = rest.findIndex((l) => /^\s*- (name|uses):/.test(l));
  return (nextStep === -1 ? rest : rest.slice(0, nextStep)).join("\n");
}

describe("#1591: CodeQL analyses the languages it claims to", () => {
  it("passes `languages:` (plural) — the real input name", () => {
    const inputs = initStepInputs(readWorkflow());
    assert.match(
      inputs,
      /^\s+languages:\s*\S/m,
      "the codeql init step does not pass a `languages:` input. Without it, CodeQL autodetects every language in the repo — which includes Swift from ios/, which needs a macOS runner, which aborts init and takes python and javascript-typescript down with it (#1591)."
    );
  });

  it("does NOT pass `language:` (singular) as an input, which is silently ignored", () => {
    const inputs = initStepInputs(readWorkflow());
    const singular = inputs.match(/^\s+language:\s*\S.*$/m);
    assert.equal(
      singular,
      null,
      `the codeql init step passes \`language:\` (singular). That is not an input of github/codeql-action/init — Actions warns and DROPS it, so CodeQL falls back to autodetecting the whole repo and dies on Swift. This is the exact regression #1591 fixed. Offending line: ${singular && singular[0].trim()}`
    );
  });

  it("still declares the language matrix it is named for", () => {
    const code = codeOf(readWorkflow());
    for (const lang of ["python", "javascript-typescript"]) {
      assert.ok(
        code.includes(lang),
        `codeql.yml no longer mentions "${lang}". Restoring these two is the entire point of #1591; if one was dropped deliberately, update this fixture in the same commit.`
      );
    }
  });

  it("does not silently move to a macOS runner to appease Swift", () => {
    const code = codeOf(readWorkflow());
    assert.ok(
      /runs-on:\s*ubuntu-latest/.test(code),
      "codeql.yml left ubuntu-latest. Alex's 2026-08-08 call was to restore python + javascript-typescript on Ubuntu and leave Swift unanalysed; scanning ios/ needs its OWN macOS job, not a runner swap that makes every job pay macOS minutes."
    );
  });
});
