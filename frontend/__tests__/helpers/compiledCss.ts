/**
 * One question, asked once: "is the compiled stylesheet actually here?"
 *
 * Several capture rigs assert through `appStylesheet()`, which reads the real
 * CSS out of `.next/static/css` so a captured artifact is judged styled rather
 * than bare. That helper returns `""` when the directory is missing, which is
 * the right thing for it to do — but it means an ABSENT build artifact and a
 * BROKEN one arrive at the assertion as the same value, and the assertion that
 * used to follow was:
 *
 *     expect(css.length).toBeGreaterThan(1000);
 *
 * In a tree that has never been built — `git worktree add --detach`, a clean
 * runner, a fresh clone — that fails with `Expected: > 1000 / Received: 0`,
 * which reads as *"the desktop rules are not present"*, i.e. as a failed fix.
 * It happened at the desk on 2026-09-16 (integrator/385): two capture suites
 * went red on a composed tree, neither touching a changed file, and the desk
 * had to diagnose the tree before it could trust the merge. A desk that reads
 * that as a composition red bounces two correct ships; one that waves it
 * through has no idea which it had.
 *
 * So this names the cause instead. THE PASS/FAIL SET IS DELIBERATELY
 * UNCHANGED: every input that failed before still fails, and nothing that
 * passed before now fails. Only the message a human reads is different.
 *
 * It does NOT skip on an absent bundle, and that is the house rule rather than
 * an oversight — `ci.yml`'s jest step carries the reasoning at length for
 * `shippedCopyBans`: *"Making it tolerate an absent bundle would restore
 * exactly the blindness it exists to remove, so the step moved instead."* The
 * fix for "the rig cannot run here" is to build first, not to look away.
 */

import fs from "fs";
import path from "path";

/**
 * The compiled-CSS directory every capture rig reads.
 *
 * Resolved from this file rather than from each caller: the rigs compute the
 * frontend root three different ways (`FRONTEND`, `FRONTEND_ROOT`,
 * `__dirname/../..`), and all three mean this one directory.
 */
export const COMPILED_CSS_DIR = path.join(
  __dirname,
  "..",
  "..",
  ".next",
  "static",
  "css",
);

/** The default bar the capture rigs have always used for "a real stylesheet". */
export const MIN_COMPILED_CSS_LENGTH = 1000;

/**
 * Assert the compiled stylesheet is present and non-trivial.
 *
 * Throws with the remedy when the build output is absent; otherwise defers to
 * the same length bar the rigs asserted inline before.
 *
 * @param css        what `appStylesheet()` returned
 * @param minLength  the length bar, for the one rig that wants a different one
 */
export function assertCompiledCss(
  css: string,
  minLength: number = MIN_COMPILED_CSS_LENGTH,
): void {
  if (!fs.existsSync(COMPILED_CSS_DIR)) {
    throw new Error(
      `No compiled CSS at ${COMPILED_CSS_DIR}.\n` +
        `This rig reads the BUILD OUTPUT, so it cannot run in a tree that has ` +
        `never been built — run \`npm run build\` first, then re-run jest.\n` +
        `This is "the rig cannot run here", NOT "the rig found something": ` +
        `nothing has been asserted about the component yet.`,
    );
  }

  if (css.length <= minLength) {
    throw new Error(
      `The compiled stylesheet at ${COMPILED_CSS_DIR} is present but only ` +
        `${css.length} characters (expected > ${minLength}).\n` +
        `The build output EXISTS, so this one is a real finding: the CSS was ` +
        `built and came out empty or near-empty.`,
    );
  }
}
