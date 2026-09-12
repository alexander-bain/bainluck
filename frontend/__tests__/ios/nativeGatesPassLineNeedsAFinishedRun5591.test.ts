/**
 * #5591 — the native rig offered a notice-10 pass line from a run that died.
 *
 * `tools/native-gates.sh` prints the `Executed N tests, with 0 failures` line
 * that standing notice 10's iOS clause requires verbatim in the PR body of any
 * Tier A change touching `ios/**`. It picked that line with `tail -1`.
 *
 * `xcodebuild` emits that shape once per test CLASS as well as once for the
 * suite — 173 of them in a healthy run of BainLuckTests, exactly ONE the total.
 * So `tail -1` is the total only on a run that reached the end. On a run killed
 * by the #5229 silent hang it is whichever class finished last, and the script
 * handed it over under "paste this line into the PR body" with "it is the count
 * for <sha>" beneath it. native/128 was offered `Executed 5 tests, with 0
 * failures` for a suite killed at 513 of ~2056 tests.
 *
 * ═══ WHY THIS IS WORTH A CI TEST AND NOT JUST A FLAG ═══
 *
 * CI COMPILES NO SWIFT (#4302), so that one string is the entire iOS gate — the
 * only gate in the fleet with no independent check. The script carries its own
 * `--selftest`, but a self-test that only runs when a human remembers to type it
 * is exactly as load-bearing as the human's memory. This file makes the machine
 * type it, on every push, on a Linux runner with no Xcode and no simulator —
 * which `--selftest` is designed to need neither of.
 *
 * IT MUST NEVER SKIP. A guard that quietly opts out when `bash` or the script is
 * missing is the same class of defect one level up: "it returned" is not "it
 * worked". If either is absent that is a failure, not a pass.
 */

import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { join } from "node:path";

const REPO_ROOT = join(__dirname, "..", "..", "..");
const GATE = join(REPO_ROOT, "tools", "native-gates.sh");

function runSelftest(): { status: number; output: string } {
  try {
    const output = execFileSync("bash", [GATE, "--selftest"], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
      timeout: 60_000,
    });
    return { status: 0, output };
  } catch (err) {
    const e = err as { status?: number; stdout?: string; stderr?: string };
    return {
      status: typeof e.status === "number" ? e.status : -1,
      output: `${e.stdout ?? ""}${e.stderr ?? ""}`,
    };
  }
}

describe("#5591 native-gates.sh only offers a pass line from a finished run", () => {
  it("the gate script is present — its absence is a failure, never a skip", () => {
    expect(existsSync(GATE)).toBe(true);
  });

  it("--selftest exits 0 and needs no Xcode, no simulator and no git tree", () => {
    const { status, output } = runSelftest();
    // Gotcha #54: read the exit code's VALUE. 1 is a result; anything else is a
    // story about the harness and must not be read as a passing gate.
    expect({ status, output }).toMatchObject({ status: 0 });
    expect(output).not.toMatch(/^ {2}FAIL/m);
  });

  it("still covers the killed-run case that #5591 was filed for", () => {
    const { output } = runSelftest();
    // The case itself...
    expect(output).toMatch(/ok {4}killed at exit 137 \(#5229\) -> PARTIAL/);
    // ...and the proof it is not vacuous: the fixture must still contain a
    // per-class count for the old `tail -1` to have taken. Without this line the
    // case above would pass on an empty log and assert nothing at all.
    expect(output).toMatch(/the bait is present: old tail -1 would have offered/);
  });

  it("is not fooled by the 'All tests' STARTED line a real killed log carries", () => {
    // xcodebuild prints "Test Suite 'All tests' started" on the way IN, so a
    // genuinely truncated log DOES contain that name — only the summary is
    // followed by an Executed total. Matching the bare name would read a killed
    // run as a finished one. Case verified against a real 6,453-line log cut at
    // 2,417; the first synthetic fixture omitted the started line and was
    // therefore easier than reality.
    const { output } = runSelftest();
    expect(output).toMatch(
      /ok {4}killed, but 'All tests' STARTED is in the log -> PARTIAL/,
    );
  });

  it("covers the finished-but-failing and never-ran shapes too", () => {
    const { output } = runSelftest();
    expect(output).toMatch(/ok {4}completed run, 3 failures -> SUITE_FAILED/);
    expect(output).toMatch(/ok {4}suite never ran -> NEVER_RAN/);
    expect(output).toMatch(/ok {4}exit 0, no '\*\* TEST SUCCEEDED \*\*' -> SUITE_FAILED/);
  });

  it("offers the SUITE total, not whichever count came last", () => {
    const { output } = runSelftest();
    expect(output).toMatch(
      /ok {4}total not last in the log -> PASS_LINE, offered "Executed 2083 tests, with 0 failures/,
    );
  });
});

/**
 * #5635 — the recompile proof must read the log that COULD hold the file.
 *
 * `--selftest` exiting 0 does not prove these cases exist: delete them and it
 * still exits 0. So each case is asserted BY NAME, the same way #5591's are
 * above. Without this block the guard would pass on a script that had quietly
 * dropped the whole section.
 */
describe("#5635 native-gates.sh proves test sources against the TEST log", () => {
  it("does not call a BainLuckTests file unseen just because the macOS log lacks it", () => {
    const { output } = runSelftest();
    // Both directions. The first alone would pass for a proof that matches
    // nothing at all; the second alone would pass for the original bug.
    expect(output).toMatch(
      /ok {4}call site: test sources vs the macOS log are UNSEEN \(the #5635 bug\) -> 1/,
    );
    expect(output).toMatch(
      /ok {4}call site: test sources vs the TEST log are proved -> 0/,
    );
  });

  it("requires the target clause, so a file merely named in the log is not 'compiled'", () => {
    const { output } = runSelftest();
    expect(output).toMatch(/ok {4}mentioned-but-not-compiled, clause required -> 0/);
    // Anti-vacuity: the fixture must actually contain the bait, or the case
    // above proves nothing about the clause.
    expect(output).toMatch(
      /ok {4}\.\.\.and WITHOUT the clause it would have read as compiled -> 2/,
    );
    expect(output).toMatch(
      /ok {4}call site: mentioned-but-not-compiled stays unseen -> 1/,
    );
  });

  it("routes on the path, not the filename, and matches basenames literally", () => {
    const { output } = runSelftest();
    expect(output).toMatch(/ok {4}routing: BainLuckTests\/ path -> test log -> yes/);
    expect(output).toMatch(
      /ok {4}routing: app file merely NAMED \*Tests -> macOS log -> yes/,
    );
    // A basename is full of dots; both grep branches carry their own -F and a
    // case that exercises one leaves the other free to regress.
    expect(output).toMatch(
      /ok {4}basename is literal, not a regex \(clause branch\) -> 0/,
    );
    expect(output).toMatch(
      /ok {4}basename is literal, not a regex \(bare branch\) -> 0/,
    );
  });

  it("keeps the one line --selftest cannot execute pinned to the TEST log", () => {
    // Section 3a needs a real build, so this case reads the script's own source.
    // Weaker than the behavioural cases above, and here because the alternative
    // for that specific regression is no guard at all.
    const { output } = runSelftest();
    expect(output).toMatch(
      /ok {4}section 3a hands prove_test_sources the TEST log -> yes/,
    );
  });

  it("reports nothing at all when no test file changed", () => {
    const { output } = runSelftest();
    expect(output).toMatch(
      /ok {4}call site: no changed test files -> nothing unproved -> 0/,
    );
    // The count alone cannot see a phantom empty filename — `grep -F ""` matches
    // every line, so an empty entry reads as "compiled". The output assertion is
    // what makes that case non-vacuous.
    expect(output).toMatch(
      /ok {4}call site: no changed test files -> and no verdict lines printed -> 0/,
    );
  });
});
