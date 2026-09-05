/**
 * `hero_probability_source` — the backend's emitted words and the client's union
 * are ONE contract, and this file is the only thing that makes them one.
 *
 * ═══ WHY THIS EXISTS ═══
 *
 * Q441 shipped `final_unresolved` from `app/utils/settled_hero.py` and through both
 * arms of `routes/events.py` while `EventDetailResponse.hero_probability_source` in
 * `lib/types.ts` still read `"blend" | "opening" | "settled"`. Nothing failed. The
 * TypeScript ratchet cannot see a value that only exists at runtime, every consumer
 * compares narrowly (`=== "blend"`), and the route tests are in Python — so the API
 * and its own client type disagreed for a whole merge, and the only reason it was
 * caught is that a reviewer read both files. CERT-1942's follow-up
 * `Q441-TYPE-FINAL-UNRESOLVED`.
 *
 * ═══ WHY IT READS THE PYTHON ═══
 *
 * A test that restates the four words in TypeScript pins nothing: it is a third copy
 * that drifts with the other two, and it passes on the day the backend adds a fifth.
 * The only version that can fail for the right reason reads the SOURCE OF TRUTH — the
 * Python constants — and asserts the union covers them. Text-matching a source file
 * is ugly; a contract that silently stops being a contract is worse.
 *
 * If this breaks because someone added a legitimate new source word, the fix is to
 * add it to the union in `lib/types.ts` (and decide what the metadata should say for
 * it), NOT to widen the regex below.
 */

import { readFileSync } from "fs";
import { join } from "path";

const REPO_ROOT = join(__dirname, "..", "..", "..");
const SETTLED_HERO_PY = join(
  REPO_ROOT,
  "backend",
  "app",
  "utils",
  "settled_hero.py",
);
const TYPES_TS = join(REPO_ROOT, "frontend", "lib", "types.ts");

/** `NAME = "value"` at module level in the Python module. */
function pyConstant(source: string, name: string): string {
  const match = source.match(new RegExp(`^${name}\\s*=\\s*"([^"]+)"`, "m"));
  if (!match) {
    throw new Error(
      `${name} is no longer a module-level string constant in settled_hero.py — ` +
        `this contract test cannot read it, which means it is no longer guarding ` +
        `anything. Fix the reader, do not delete the test.`,
    );
  }
  return match[1];
}

/** The declared union members of `hero_probability_source`, in declaration order. */
function unionMembers(typesSource: string): string[] {
  const decl = typesSource.match(
    /hero_probability_source\?:\s*([\s\S]*?);/,
  );
  if (!decl) throw new Error("hero_probability_source is not declared in types.ts");
  return [...decl[1].matchAll(/"([^"]+)"/g)].map((m) => m[1]);
}

describe("hero_probability_source: the backend's words and the client's union", () => {
  const py = readFileSync(SETTLED_HERO_PY, "utf8");
  const ts = readFileSync(TYPES_TS, "utf8");
  const members = unionMembers(ts);

  it("the union carries the word the backend writes for a RESOLVED result", () => {
    expect(members).toContain(pyConstant(py, "SETTLED_HERO_SOURCE"));
  });

  it("the union carries the word the backend writes for FINISHED-BUT-UNKNOWN", () => {
    // The one that was missing. Before this test, this assertion failed while every
    // other gate in the repo stayed green.
    expect(members).toContain(pyConstant(py, "FINAL_UNRESOLVED_SOURCE"));
  });

  it("the two backend words are distinct, and both are distinct from 'blend'", () => {
    const settled = pyConstant(py, "SETTLED_HERO_SOURCE");
    const unresolved = pyConstant(py, "FINAL_UNRESOLVED_SOURCE");
    expect(new Set([settled, unresolved, "blend"]).size).toBe(3);
  });

  it("still carries the two words the route emits from its own literals", () => {
    // `blend` and `opening` are spelled inline in routes/events.py rather than in
    // settled_hero.py, so they are pinned here by name. A rename there without a
    // rename here is the same class of drift this file exists to catch.
    expect(members).toEqual(
      expect.arrayContaining(["blend", "opening"]),
    );
  });

  it("the union has EXACTLY the four known members — a fifth must be a decision", () => {
    // Deliberately exact. A new source word changes what every settled surface
    // prints, so it should break here and be reasoned about, not absorbed.
    expect([...members].sort()).toEqual(
      ["blend", "final_unresolved", "opening", "settled"].sort(),
    );
  });
});
