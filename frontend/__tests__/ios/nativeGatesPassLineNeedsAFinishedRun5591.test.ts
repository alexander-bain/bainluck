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
