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
const path = require("node:path");
const { validateManifest, verifyArtifactBytes } = require("../helpers/manifest");

function fail(message) {
  console.error(`[browser-audit] FAIL — ${message}`);
  process.exit(1);
}

const args = process.argv.slice(2);
const allowNonPass = args.includes("--allow-nonpass");
/**
 * L2-223: re-hash every claimed artifact against the bytes on disk. Only
 * meaningful where the files still exist (the workflow, or a downloaded and
 * unpacked artifact), which is why it is a flag rather than always-on — but
 * the workflow always passes it, so a fictional artifact never survives CI.
 */
const verifyBytes = args.includes("--verify-bytes");
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

if (verifyBytes) {
  const root = path.dirname(path.resolve(manifestPath));
  const bytes = verifyArtifactBytes(manifest, { root });
  if (!bytes.ok) {
    console.error(`[browser-audit] artifact bytes in ${root} do NOT match the manifest:`);
    for (const error of bytes.errors) console.error(`  ✗ ${error}`);
    process.exit(1);
  }
  console.log(`[browser-audit] ${bytes.verified} artifact(s) re-hashed from disk and matched`);
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
