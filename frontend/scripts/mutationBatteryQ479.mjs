#!/usr/bin/env node
/**
 * lane1-Q479 mutation battery — TOP-PRODUCT-DEFECTS item 13.
 *
 * Each mutant is a literal string substitution against a target file. For every
 * mutant the script proves THREE things, in this order, because a battery that
 * skips any of them reports a number it did not earn:
 *
 *   1. the substitution APPLIED (the target's sha256 changed);
 *   2. the suite then FAILED (the mutant was killed) — a mutant that survives is
 *      reported as SURVIVED, never quietly counted;
 *   3. the target was RESTORED byte-for-byte (sha256 back to the original), in a
 *      `finally`, so a crash mid-run cannot strand a mutant in the tree.
 *
 * Run from `frontend/`:  node scripts/mutationBatteryQ479.mjs
 */

import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { spawnSync } from "node:child_process";

const PAGE = "app/futures/[id]/page.tsx";
const LIB = "lib/outcomeExclusivity.ts";

const PATTERN = "outcomeExclusivityQ479|futuresDetailIndependentOutcomesQ479";

/** @type {{name: string, file: string, from: string, to: string}[]} */
const MUTANTS = [
  {
    name: "A — the page never reads the field (the blocked bytes)",
    file: PAGE,
    from: "        {independenceNote && (",
    to: "        {false && independenceNote && (",
  },
  {
    name: "B — absence becomes a claim (`=== false` → `!== true`)",
    file: LIB,
    from: "    mutuallyExclusive === false && outcomeCount >= MIN_OUTCOMES_FOR_INDEPENDENCE_NOTE",
    to: "    mutuallyExclusive !== true && outcomeCount >= MIN_OUTCOMES_FOR_INDEPENDENCE_NOTE",
  },
  {
    name: "C — the default-true flag is treated as evidence (predicate inverted)",
    file: LIB,
    from: "    mutuallyExclusive === false && outcomeCount >= MIN_OUTCOMES_FOR_INDEPENDENCE_NOTE",
    to: "    mutuallyExclusive === true && outcomeCount >= MIN_OUTCOMES_FOR_INDEPENDENCE_NOTE",
  },
  {
    name: "D — the outcome-count floor is dropped (a duel gets the note)",
    file: LIB,
    from: "export const MIN_OUTCOMES_FOR_INDEPENDENCE_NOTE = 3;",
    to: "export const MIN_OUTCOMES_FOR_INDEPENDENCE_NOTE = 0;",
  },
  {
    name: "E — the floor is off by one (three outcomes lose the note)",
    file: LIB,
    from: "export const MIN_OUTCOMES_FOR_INDEPENDENCE_NOTE = 3;",
    to: "export const MIN_OUTCOMES_FOR_INDEPENDENCE_NOTE = 4;",
  },
  {
    name: "F — the two tenses collapse into one (the settled rendering lies)",
    file: LIB,
    from:
      'export const INDEPENDENT_OUTCOMES_NOTE_SETTLED =\n  "Several of these could happen — each was priced on its own, so they don\'t add up to 100%.";',
    to:
      'export const INDEPENDENT_OUTCOMES_NOTE_SETTLED =\n  "Several of these can happen — each is priced on its own, so they don\'t add up to 100%.";',
  },
  {
    name: "G — the settled branch never fires (isResolved hard-wired false)",
    file: LIB,
    from: "  return isResolved\n    ? INDEPENDENT_OUTCOMES_NOTE_SETTLED\n    : INDEPENDENT_OUTCOMES_NOTE_OPEN;",
    to: "  return INDEPENDENT_OUTCOMES_NOTE_OPEN;",
  },
  {
    name: "H — no-claim becomes an empty claim (`null` → `\"\"`)",
    file: LIB,
    from: "  if (!outcomesArePricedIndependently(mutuallyExclusive, outcomeCount)) return null;",
    to: '  if (!outcomesArePricedIndependently(mutuallyExclusive, outcomeCount)) return "";',
  },
  {
    name: "I — the copy implies a renormalisation instead of stating the shape",
    file: LIB,
    from: "so they don't add up to 100%.\";\n\n/**\n * The same fact in the past tense",
    to: "so they should add up to 100%.\";\n\n/**\n * The same fact in the past tense",
  },
  {
    name: "J — the note is moved BELOW the outcome list a reader has already summed",
    file: PAGE,
    from:
      '        {independenceNote && (\n          <p\n            data-testid="independent-outcomes-note"\n            className="text-sm text-text-secondary mb-4"\n          >\n            {independenceNote}\n          </p>\n        )}\n',
    to: "",
    also: {
      from: "        {/* Show more button */}",
      to:
        '        {independenceNote && (\n          <p\n            data-testid="independent-outcomes-note"\n            className="text-sm text-text-secondary mb-4"\n          >\n            {independenceNote}\n          </p>\n        )}\n\n        {/* Show more button */}',
    },
  },
  {
    name: "K — the note renders as an EMPTY element (present but wordless)",
    file: PAGE,
    from: "            {independenceNote}\n          </p>",
    to: "          </p>",
  },
  {
    name: "L — the count comes off outcome_count, not the rows on screen",
    file: PAGE,
    from: "    market.outcomes?.length ?? 0,",
    to: "    0,",
  },
];

const sha = (p) => createHash("sha256").update(readFileSync(p)).digest("hex");

function runSuite() {
  const r = spawnSync("npx", ["jest", "--testPathPatterns", PATTERN], {
    encoding: "utf8",
    env: { ...process.env, TZ: "UTC" },
  });
  return r.status;
}

const originals = new Map([
  [PAGE, readFileSync(PAGE, "utf8")],
  [LIB, readFileSync(LIB, "utf8")],
]);
const originalShas = new Map([...originals.keys()].map((f) => [f, sha(f)]));

const baseline = runSuite();
if (baseline !== 0) {
  console.error(`BASELINE IS NOT GREEN (exit ${baseline}) — battery aborted.`);
  process.exit(2);
}
console.log("baseline: GREEN\n");

let killed = 0;
let survived = 0;
let notApplied = 0;

for (const m of MUTANTS) {
  const targets = new Set([m.file]);
  try {
    let src = originals.get(m.file);
    if (!src.includes(m.from)) {
      console.log(`NOT-APPLIED  ${m.name}  (anchor not found)`);
      notApplied += 1;
      continue;
    }
    src = src.replace(m.from, m.to);
    if (m.also) {
      if (!src.includes(m.also.from)) {
        console.log(`NOT-APPLIED  ${m.name}  (second anchor not found)`);
        notApplied += 1;
        continue;
      }
      src = src.replace(m.also.from, m.also.to);
    }
    writeFileSync(m.file, src);

    // (1) prove it applied
    if (sha(m.file) === originalShas.get(m.file)) {
      console.log(`NOT-APPLIED  ${m.name}  (sha unchanged)`);
      notApplied += 1;
      continue;
    }

    // (2) prove it dies
    const status = runSuite();
    if (status === 0) {
      console.log(`🔴 SURVIVED  ${m.name}`);
      survived += 1;
    } else if (status === 1) {
      console.log(`killed       ${m.name}`);
      killed += 1;
    } else {
      // Anything other than 1 is a story about the harness, not a result.
      console.log(`⚠️ HARNESS   ${m.name}  (jest exit ${status}, not an assertion failure)`);
      survived += 1;
    }
  } finally {
    // (3) restore, always, and prove it
    for (const f of targets) writeFileSync(f, originals.get(f));
    for (const f of targets) {
      if (sha(f) !== originalShas.get(f)) {
        console.error(`RESIDUE: ${f} did not restore byte-for-byte`);
        process.exit(3);
      }
    }
  }
}

for (const [f, s] of originalShas) {
  if (sha(f) !== s) {
    console.error(`RESIDUE at exit: ${f}`);
    process.exit(3);
  }
}

console.log(
  `\n${killed}/${MUTANTS.length} killed · ${survived} survived · ${notApplied} not-applied · residue clean`
);
process.exit(survived === 0 && notApplied === 0 ? 0 : 1);
