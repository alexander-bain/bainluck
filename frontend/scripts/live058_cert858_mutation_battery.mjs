#!/usr/bin/env node
/**
 * live/058 CERT-858 repair — the mutation battery for the poll rule.
 *
 * A guard suite that goes green is not evidence until something has tried to
 * break the thing it guards. Every mutant below is a defect a reviewer could
 * plausibly ship; each one must turn at least one named test RED.
 *
 * THE EDIT IS PROVEN TO APPLY, never inferred from the result. A mutation that
 * silently fails to land runs the suite against unmutated source, passes, and
 * reads exactly like "caught by nothing" — which would certify a guard that was
 * never tested. Every row asserts the `from` string was present and the `to`
 * string is present afterwards.
 *
 *   node scripts/live058_cert858_mutation_battery.mjs
 */
import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const FRONTEND = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const RULE = path.join(FRONTEND, "lib/liveDetailRefresh.ts");
const PAGE = path.join(FRONTEND, "app/events/[id]/page.tsx");

/** The two suites that stand between these mutants and production. */
const SUITES = "liveDetailRefresh|liveTennisAcquiresItsLine";

const MUTANTS = [
  {
    name: "M1 the shipped CERT-858 defect, restored verbatim",
    why: "no first acquisition: connected + live + tennis + no line scores 0",
    file: RULE,
    from: `  if (linescore) return linescore.state !== LINESCORE_DECIDED;
  return status === "live" && sportKeepsALinescore(sport);`,
    to: `  return Boolean(linescore);`,
  },
  {
    name: "M2 always poll while streaming",
    why: "the lazy repair — undoes live/034 S2 for every sport",
    file: RULE,
    from: `    return streamIsBlindToTheScore({ status, sport, linescore })
      ? LIVE_LINESCORE_REFRESH_INTERVAL
      : 0;`,
    to: `    return LIVE_LINESCORE_REFRESH_INTERVAL;`,
  },
  {
    name: "M3 sport matched by startsWith instead of key prefix",
    why: "claims `tennistable_wtt` as tennis",
    file: RULE,
    from: `  return FINER_GRAIN_SPORT_PREFIXES.includes(String(sport ?? "").split("_")[0]);`,
    to: `  return FINER_GRAIN_SPORT_PREFIXES.some((p) => String(sport ?? "").startsWith(p));`,
  },
  {
    name: "M4 first acquisition without the live gate",
    why: "polls a scheduled tennis page every 15 s for nothing",
    file: RULE,
    from: `  return status === "live" && sportKeepsALinescore(sport);`,
    to: `  return sportKeepsALinescore(sport);`,
  },
  {
    name: "M5 a decided line keeps polling",
    why: "requests forever for a score that cannot change",
    file: RULE,
    from: `  if (linescore) return linescore.state !== LINESCORE_DECIDED;`,
    to: `  if (linescore) return true;`,
  },
  {
    name: "M6 the sport list emptied",
    why: "the registry is the ship; an empty one is the pre-repair behaviour",
    file: RULE,
    from: `export const FINER_GRAIN_SPORT_PREFIXES: readonly string[] = ["tennis"];`,
    to: `export const FINER_GRAIN_SPORT_PREFIXES: readonly string[] = [];`,
  },
  {
    name: "M7 the page passes the WRONG FIELD under the right name",
    why: "the attack a source scan for `sport: data?.sport` cannot see",
    file: PAGE,
    from: `          sport: data?.sport,`,
    to: `          sport: data?.status,`,
  },
  {
    name: "M8 the page stops passing the line at all",
    why: "every payload then looks like a first acquisition",
    file: PAGE,
    from: `          linescore: data?.linescore,`,
    to: `          linescore: undefined,`,
  },
];

function run() {
  try {
    execFileSync("npx", ["jest", "--testPathPatterns", SUITES], {
      cwd: FRONTEND,
      env: { ...process.env, TZ: "UTC" },
      stdio: "pipe",
    });
    return { passed: true, output: "" };
  } catch (err) {
    return { passed: false, output: String(err.stdout ?? "") + String(err.stderr ?? "") };
  }
}

const control = run();
if (!control.passed) {
  console.error("CONTROL IS RED — the battery proves nothing. Fix the suite first.");
  console.error(control.output.slice(-3000));
  process.exit(2);
}
console.log("control: GREEN (unmutated tree)\n");

let killed = 0;
const survivors = [];
for (const m of MUTANTS) {
  const original = readFileSync(m.file, "utf8");
  if (!original.includes(m.from)) {
    console.error(`${m.name}: DID NOT APPLY — anchor absent in ${path.basename(m.file)}`);
    process.exit(2);
  }
  writeFileSync(m.file, original.replace(m.from, m.to));
  const applied = readFileSync(m.file, "utf8");
  if (!applied.includes(m.to) || applied === original) {
    writeFileSync(m.file, original);
    console.error(`${m.name}: DID NOT APPLY — post-write check failed`);
    process.exit(2);
  }

  const result = run();
  writeFileSync(m.file, original);

  if (result.passed) {
    survivors.push(m);
    console.log(`SURVIVED  ${m.name}\n          (${m.why})`);
  } else {
    killed += 1;
    const first = (result.output.match(/● .*/g) ?? ["(unnamed)"])[0].trim();
    console.log(`killed    ${m.name}\n          by ${first}`);
  }
}

console.log(`\n${killed}/${MUTANTS.length} killed`);
if (survivors.length) process.exit(1);
