// live/122 (#4469) — THE BADGE'S INPUT, pinned at the call site.
//
// `heroFreshness.test.ts` proves the helper picks the older fact. It cannot
// prove the PAGE hands it to the badge, and that is the entire defect: the
// helper can be perfect while `<LiveAgeStamp updatedAt={freshestSourceStamp}>`
// carries on printing a green `live · 6s ago` over an eight-minute-old score,
// with every unit test in the helper's own file still green.
//
// No render harness exists for `app/events/[id]/page.tsx` (it is a client page
// behind SWR and an SSE stream), so this is a source scan. It reads IDENTIFIERS,
// never prose, and strips comments first — this file's own docblock and the
// page's both name `freshestSourceStamp`, and an unstripped scan would pass on a
// comment describing the wiring after the wiring had been reverted.

import fs from "fs";
import path from "path";

const PAGE = path.resolve(__dirname, "../../app/events/[id]/page.tsx");
const BADGE = path.resolve(__dirname, "../../components/event/LiveAgeStamp.tsx");

/** Source with `//` and block comments removed, so only executable text is scanned. */
function executableSource(file: string): string {
  const raw = fs.readFileSync(file, "utf8");
  return raw
    .replace(/\/\*[\s\S]*?\*\//g, " ")
    .split("\n")
    .map((line) => line.replace(/(^|\s)\/\/.*$/, "$1"))
    .join("\n");
}

describe("#4469 the live badge is fed the oldest fact, not the freshest price", () => {
  test("the page computes the hero stamp from both inputs", () => {
    const code = executableSource(PAGE);
    expect(code).toMatch(/heroFreshness\(\{/);
    expect(code).toMatch(/priceStamp:\s*freshestSourceStamp/);
    // Gated on the render condition, not on the field merely existing: an
    // unrendered score must not age the badge.
    expect(code).toMatch(/scoreStamp:\s*liveGamesLine\s*\?\s*event\.linescore\?\.observed_at/);
  });

  test("the badge receives the computed stamp, and the pre-#4469 wiring is gone", () => {
    const code = executableSource(PAGE);
    expect(code).toMatch(/updatedAt=\{heroStamp\.stamp\}/);
    expect(code).toMatch(/oldestFact=\{heroStamp\.fact\}/);
    // The exact call this replaced. This is the regression to catch.
    expect(code).not.toMatch(/updatedAt=\{freshestSourceStamp\}/);
  });

  test("exactly one LiveAgeStamp is rendered — a second could disagree with the first", () => {
    const calls = executableSource(PAGE).match(/<LiveAgeStamp\b/g) ?? [];
    expect(calls).toHaveLength(1);
  });

  test("`freshestSourceStamp` still exists and is still a MAX", () => {
    // It is not dead code and must not be "simplified" into a min: it is the
    // blend's own age, and the blend is right to take the freshest source. The
    // min happens ACROSS facts, in `heroFreshness`, never within the number.
    const code = executableSource(PAGE);
    expect(code).toMatch(/Date\.parse\(a\)\s*>=\s*Date\.parse\(b\)\s*\?\s*a\s*:\s*b/);
  });

  test("the stale sentence is keyed on the fact, so it cannot blame the price", () => {
    const code = executableSource(BADGE);
    expect(code).toMatch(/oldestFact === "score"/);
    // The old unconditional sentence is false on a live tennis hero.
    expect(code).not.toMatch(/stale\s*\?\s*`Last update \$\{label\}\. Waiting for a fresh price\.`/);
  });

  test("the stale BOUNDARY is keyed on the fact too, and reuses the chip's constant", () => {
    const code = executableSource(BADGE);
    // 120s is the price's beat. Applying it to a ten-minute-beat score calls a
    // healthy score stale nearly always, and flickers once the beat tightens.
    expect(code).not.toMatch(/const stale = age > STALE_AFTER_S;/);
    expect(code).toMatch(/STALE_AFTER_S_BY_FACT\[oldestFact \?\? "price"\]/);
    // A third invented number is the regression: it must be the chip's own.
    expect(code).toMatch(/import \{ STALE_MS \} from/);
    expect(code).toMatch(/score:\s*STALE_MS \/ 1000/);
  });
});

describe("#4469 the two thresholds are the two beats, not two opinions", () => {
  test("price keeps 120s and score takes the chip's five minutes", async () => {
    const { STALE_MS } = await import("@/components/event/FreshnessChip");
    expect(STALE_MS).toBe(5 * 60 * 1000);
    const code = executableSource(BADGE);
    expect(code).toMatch(/const STALE_AFTER_S = 120;/);
  });
});
