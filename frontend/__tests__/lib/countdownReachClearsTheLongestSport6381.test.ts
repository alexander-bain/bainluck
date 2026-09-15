/**
 * THE RING'S REACH CLEARS EVERY SPORT THE BACKEND KNOWS — #6381.
 *
 * ═══ WHY THIS FILE EXISTS ═══
 *
 * `REFRESH_COUNTDOWN_MAX_AGE_MS` (`lib/eventKeyStats.ts`) stops the header's
 * "Next update: NN" dial once an event with no reported result is far enough
 * past its own kickoff that nothing is coming. "Far enough" is only defensible
 * against a number somebody measured: `SPORT_MAX_DURATIONS` in
 * `backend/app/tasks/config.py` is how long a match of each sport can plausibly
 * still be running, and the ring must outlive the longest of them — otherwise
 * the fix for a 9-day-old ghost would take the dial off a golf round that is
 * genuinely still being played.
 *
 * The TypeScript constant carries that reasoning in a comment. **A comment is
 * not a mechanism** (#3211's guard, `railGraceMatchesTheBackend3211.test.ts`,
 * is the rule this follows). If someone adds a 14-hour sport, this reddens.
 *
 * ═══ WHY IT IS `>=` AND NOT `===` ═══
 *
 * Unlike #3211's grace, these two numbers are not one number in two languages.
 * The backend's is a match duration; ours is a duration PLUS a reporting margin,
 * because a result lags the final whistle. So the assertion is the relationship
 * that has to hold — ours clears theirs — not an equality that would have to be
 * re-tuned every time a sport is added.
 */

import { readFileSync } from "fs";
import { join } from "path";

import { REFRESH_COUNTDOWN_MAX_AGE_MS } from "@/lib/eventKeyStats";

const PY_SOURCE = join(
  __dirname,
  "..",
  "..",
  "..",
  "backend",
  "app",
  "tasks",
  "config.py",
);

/**
 * Every value in `SPORT_MAX_DURATIONS = { "tennis": 6.0, ... }`, in hours.
 *
 * Throws rather than returning an empty list: a source scan that matches
 * nothing passes vacuously, and "the table is gone" must not look like "every
 * sport is short".
 */
function backendMaxDurationHours(): Record<string, number> {
  const source = readFileSync(PY_SOURCE, "utf8");
  const block = source.match(/^SPORT_MAX_DURATIONS\s*=\s*\{([\s\S]*?)^\}/m);
  if (!block) {
    throw new Error(
      `could not find \`SPORT_MAX_DURATIONS = {...}\` in ${PY_SOURCE}. Either ` +
        "it was renamed or moved — if the backend now expresses match duration " +
        "some other way, this guard has to learn that shape, not be deleted",
    );
  }
  const out: Record<string, number> = {};
  for (const m of block[1].matchAll(/"([\w]+)"\s*:\s*([\d.]+)/g)) {
    out[m[1]] = Number(m[2]);
  }
  if (Object.keys(out).length === 0) {
    throw new Error(
      `found \`SPORT_MAX_DURATIONS\` in ${PY_SOURCE} but parsed no entries out ` +
        "of it — the entry shape changed and this guard is measuring nothing",
    );
  }
  return out;
}

const HOUR_MS = 60 * 60 * 1000;

describe("#6381 · the countdown's reach vs the backend's match durations", () => {
  test("CONTROL: the parse finds real sports in the shipped Python", () => {
    // A source scan that matches nothing passes for free. Prove it bit.
    const durations = backendMaxDurationHours();
    expect(Object.keys(durations).length).toBeGreaterThanOrEqual(5);
    expect(durations.tennis).toBeGreaterThan(0);
    expect(durations.default).toBeGreaterThan(0);
  });

  test("the reach clears EVERY sport's maximum duration", () => {
    const short = Object.entries(backendMaxDurationHours()).filter(
      ([, hours]) => hours * HOUR_MS > REFRESH_COUNTDOWN_MAX_AGE_MS,
    );
    // Named in the failure, so the reader is told WHICH sport outgrew the reach
    // rather than that some number is bigger than some other number.
    expect(short.map(([sport, hours]) => `${sport}=${hours}h`)).toEqual([]);
  });

  test("and leaves a reporting margin over the longest of them", () => {
    // Not just "clears it" — a result lags the final whistle, so the margin is
    // deliberate. Pinned so that shrinking the reach to exactly the longest
    // sport is a decision somebody makes on purpose.
    const longest = Math.max(...Object.values(backendMaxDurationHours()));
    expect(REFRESH_COUNTDOWN_MAX_AGE_MS).toBeGreaterThan(longest * HOUR_MS);
  });

  test("CONTROL: the comparison would notice a reach that was too short", () => {
    // Otherwise "it clears them" could be an artefact of comparing a number to
    // itself through two paths that are really one.
    const longest = Math.max(...Object.values(backendMaxDurationHours()));
    expect(longest * HOUR_MS).toBeLessThan(REFRESH_COUNTDOWN_MAX_AGE_MS);
    expect(1 * HOUR_MS).toBeLessThan(longest * HOUR_MS);
  });
});
