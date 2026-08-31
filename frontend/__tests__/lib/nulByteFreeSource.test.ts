/**
 * UX-P213 — A SOURCE FILE WITH A RAW NUL BYTE IS INVISIBLE TO GREP.
 *
 * ═══ THE MEASUREMENT ═══
 *
 * `__tests__/components/shippedCopyBans.test.ts` held two raw NUL bytes, typed
 * straight into two template literals as a composite-key separator. They were
 * correct JavaScript and the suite was green. They also made the file BINARY to
 * every text tool this repo is searched with:
 *
 *   $ grep -c 'ban' __tests__/components/shippedCopyBans.test.ts
 *   $ echo $?
 *   1                      # "no match" — against 27 real matches
 *   $ git grep -c 'ban' -- __tests__/components/shippedCopyBans.test.ts
 *                          # nothing
 *   $ grep -a -c 'ban' __tests__/components/shippedCopyBans.test.ts
 *   27                     # the file was never the problem
 *
 * UX-P210 found it the expensive way: CERT-507 blocked `ux-150` partly because
 * "its central reproduction is also false here", and the reproduction was false
 * because the grep that checked it had silently declined to read the file.
 *
 * ═══ WHY THIS IS A CLASS AND NOT A TYPO ═══
 *
 * A grep that returns nothing is indistinguishable from a grep that ran and
 * found nothing. Every sweep, census and cert reproduction in this repo is
 * built out of greps, so ONE such file poisons an unbounded number of future
 * measurements — and it does so silently, in the direction of "all clear".
 * The two bytes cost more than any assertion in the file they lived in.
 *
 * The fix is spelling, not behaviour: the escape `\u0000` in the source is the same byte
 * at runtime. So the rule is cheap to keep, and this is what keeps it.
 */

import fs from "node:fs";
import path from "node:path";

/** Repo-relative roots that hold text a person or a grep is expected to read. */
const ROOTS = ["app", "components", "lib", "__tests__", "e2e", "scripts"];

const TEXT_EXTENSIONS = /\.(ts|tsx|js|jsx|mjs|cjs|json|md|css)$/;

/** Directories that are outputs or dependencies, not authored source. */
const SKIP_DIRS = new Set(["node_modules", ".next", "coverage", "dist", "build", ".git"]);

const FRONTEND_ROOT = path.resolve(__dirname, "..", "..");

/**
 * ⚠️ THIS FUNCTION USED TO SWALLOW `readdirSync` ERRORS, AND CERT-539 WAS RIGHT
 * THAT IT MADE THE GUARD THE THING IT WARNS ABOUT.
 *
 * The original body was `try { … } catch { return out; }`. An unreadable or
 * missing root therefore contributed zero files SILENTLY, and the only
 * anti-vacuity assertion was an aggregate floor of 500 against 859 real files
 * — so any one root could disappear entirely and the sweep would still report
 * clean. A check that reports green about bytes it never read is the exact
 * failure this file exists to prevent; it does not get an exemption for being
 * the check.
 *
 * It now throws with the path attached, and the per-root assertion below means
 * no root can silently contribute nothing.
 */
function walk(dir: string, out: string[] = []): string[] {
  let entries: fs.Dirent[];
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch (err) {
    throw new Error(
      `cannot read ${dir} while sweeping for NUL bytes — a sweep that skips a ` +
        `directory reports "clean" about files it never opened, which is the ` +
        `failure this guard is about. Original error: ${(err as Error).message}`
    );
  }
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (SKIP_DIRS.has(entry.name)) continue;
      walk(full, out);
    } else if (entry.isFile() && TEXT_EXTENSIONS.test(entry.name)) {
      out.push(full);
    }
  }
  return out;
}

describe("authored source carries no raw NUL byte", () => {
  const byRoot = new Map(ROOTS.map((root) => [root, walk(path.join(FRONTEND_ROOT, root))]));
  const files = [...byRoot.values()].flat();

  /**
   * ═══ CERT-539 — THE AGGREGATE FLOOR WAS NOT AN ANTI-VACUITY CHECK ═══
   *
   * `files.length > 500` was the only thing standing between this guard and a
   * silent no-op, and it could not do the job: the tree has 859 matching files,
   * so deleting the largest root still leaves 551 and the floor stays green.
   * Every root could become unreadable one at a time and the sweep would report
   * clean the whole way down.
   *
   * The real property is PER ROOT — each declared root must exist and must
   * contribute files — and it is asserted first, with the counts printed in the
   * failure so a zero is legible rather than inferred. `scripts` carries only
   * two files, which is precisely why an aggregate could never have noticed it.
   *
   * The floor stays, as the secondary check it always was.
   */
  it("every declared root exists and contributes files — no root can vanish quietly", () => {
    const counts = Object.fromEntries([...byRoot].map(([root, f]) => [root, f.length]));
    const missing = ROOTS.filter((root) => !fs.existsSync(path.join(FRONTEND_ROOT, root)));
    expect([missing, "roots declared but absent from disk"]).toEqual([
      [],
      "roots declared but absent from disk",
    ]);
    const empty = ROOTS.filter((root) => (byRoot.get(root) ?? []).length === 0);
    expect([empty, counts]).toEqual([[], counts]);
  });

  it("finds files to check — an empty sweep is not a passing sweep", () => {
    // The failure this guard is ABOUT is a check that reports clean because it
    // never ran. It would be an unusually poor joke for the guard to do it too.
    // Kept as the SECONDARY check; the per-root assertion above is the real one.
    expect(files.length).toBeGreaterThan(500);
  });

  it("the walker refuses an unreadable directory instead of returning empty", () => {
    // Proves the throw is real. Without this the fix is a comment: a `catch`
    // reintroduced tomorrow would leave every other assertion in this file
    // green, which is exactly how the defect got here the first time.
    expect(() => walk(path.join(FRONTEND_ROOT, "no-such-root-uxp215"))).toThrow(
      /cannot read .*no-such-root-uxp215/
    );
  });

  it("reports the offenders by path, not just a count", () => {
    const offenders: string[] = [];
    for (const file of files) {
      const buf = fs.readFileSync(file);
      const at = buf.indexOf(0);
      if (at !== -1) {
        offenders.push(`${path.relative(FRONTEND_ROOT, file)} (first NUL at byte ${at})`);
      }
    }
    if (offenders.length > 0) {
      throw new Error(
        "raw NUL bytes in authored source — grep and `git grep` will silently " +
          "report NO MATCH on these files, so any sweep that touches them lies:\n  " +
          offenders.join("\n  ") +
          "\n\nWrite the byte as the escape \\u0000 instead. It is identical at runtime."
      );
    }
  });

  it("the check can see a NUL when there is one — the detector is not vacuous", () => {
    // A guard that has never fired is a guard whose predicate is unverified.
    // Same discipline as the RETIRED list in `shippedCopyBans.test.ts`: prove
    // the rule rejects before trusting it to accept.
    const planted = Buffer.from(`const key = \`a${String.fromCharCode(0)}b\`;\n`, "utf8");
    expect(planted.indexOf(0)).toBeGreaterThan(-1);

    // And the escaped spelling — the fix — must NOT be detected, or the guard
    // would forbid its own remedy.
    const fixed = Buffer.from("const key = `a\\u0000b`;\n", "utf8");
    expect(fixed.indexOf(0)).toBe(-1);
  });

  it("the file that caused this guard is itself clean", () => {
    // Named explicitly so a revert of the fix fails HERE, with the history
    // attached, rather than only inside the tree-wide sweep above.
    const subject = path.join(FRONTEND_ROOT, "__tests__/components/shippedCopyBans.test.ts");
    expect(fs.existsSync(subject)).toBe(true);
    expect(fs.readFileSync(subject).indexOf(0)).toBe(-1);
    // …and it still uses NUL as its joiner, spelled as an escape. If someone
    // "fixes" this by switching to a printable separator, a surface or rule id
    // containing that character would collide two debt entries into one.
    expect(fs.readFileSync(subject, "utf8")).toContain("\\u0000");
  });
});
