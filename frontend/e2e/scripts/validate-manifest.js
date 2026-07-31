#!/usr/bin/env node
"use strict";

/**
 * L2-221 Item 2 — the manifest gate, as a plain-node CLI.
 *
 * Usage:
 *   node scripts/validate-manifest.js audit-out/manifest.json
 *   node scripts/validate-manifest.js audit-out/manifest.json --allow-nonpass
 *
 * Exit 0 ONLY when the manifest is structurally valid AND the run result is
 * `pass`. Everything else — a missing file, unparseable JSON, a schema error,
 * a SHA mismatch, zero selected journeys, a non-pass result — exits 1.
 *
 * A missing manifest is the important case: if the runner died before writing
 * one, there is nothing to read, and "nothing to read" must be a hard failure
 * rather than a step that quietly succeeds. That is precisely how the retired
 * provider's sweep reported `success` with 0 of 3 modules collected.
 */

const fs = require("node:fs");
const { validateManifest } = require("../helpers/manifest");

function fail(message) {
  console.error(`[browser-audit] FAIL — ${message}`);
  process.exit(1);
}

const args = process.argv.slice(2);
const allowNonPass = args.includes("--allow-nonpass");
const manifestPath = args.find((a) => !a.startsWith("--")) || "audit-out/manifest.json";

if (!fs.existsSync(manifestPath)) {
  fail(`no manifest at ${manifestPath} — the run produced no evidence, which is never a pass`);
}

let manifest;
try {
  manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
} catch (err) {
  fail(`manifest at ${manifestPath} is not valid JSON: ${err.message}`);
}

const { ok, errors } = validateManifest(manifest);
if (!ok) {
  console.error(`[browser-audit] manifest ${manifestPath} is INVALID:`);
  for (const error of errors) console.error(`  ✗ ${error}`);
  process.exit(1);
}

const run = manifest.run;
console.log(
  `[browser-audit] manifest valid — pack=${run.pack} result=${run.result} ` +
    `selected=${run.selected_count} completed=${run.completed_count} failed=${run.failed_count}`
);
console.log(`[browser-audit] frontend sha  ${run.observed_frontend_sha} (requested ${run.requested_frontend_sha})`);
console.log(`[browser-audit] backend sha   ${run.observed_backend_sha ?? "not recorded"} (recorded only — never frontend authority)`);

for (const journey of manifest.journeys) {
  const failedAssertions = journey.assertions.filter((a) => !a.ok);
  const mark = journey.result === "pass" ? "✓" : "✗";
  console.log(`  ${mark} ${journey.journey_id} [${journey.project}] → ${journey.result}`);
  for (const assertion of failedAssertions) {
    console.log(`      ✗ ${assertion.assertion_id}: ${assertion.detail ?? "failed"}`);
  }
}

if (run.result !== "pass" && !allowNonPass) {
  fail(`run result is "${run.result}" — only "pass" is GREEN`);
}

console.log("[browser-audit] PASS");
