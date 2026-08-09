#!/usr/bin/env node
"use strict";

/**
 * UX-P029 Item 2 — the manifest consumer.
 *
 * Reads every manifest the triggering browser-audit run produced, asks the pure
 * decision layer what to do about each finding, and does exactly that via `gh`.
 *
 * All judgement lives in `helpers/sweepFiling.js` (pure, contract-tested); this
 * file is the side-effecting shell. Keeping the split sharp is what lets
 * "UNKNOWN no-ops" and "two concurrent consumers do not duplicate" be proven by
 * unit fixtures rather than by watching production.
 */

const fs = require("node:fs");
const path = require("node:path");
const { execFileSync } = require("node:child_process");

const { ACTIONS, findingsFromManifest, decide } = require("../helpers/sweepFiling");

const MARKER_KEY = "browser-sweep-fingerprint";
const LABELS = ["type:bug", "area:frontend", "alert-intake", "program:ux"];
const ROOT = process.env.AUDIT_ARTIFACT_ROOT || "audit-artifacts";
const RUN_URL = process.env.AUDIT_RUN_URL || "";
const HEAD_SHA = process.env.AUDIT_HEAD_SHA || "";

function gh(args, options) {
  return execFileSync("gh", args, { encoding: "utf8", ...(options || {}) });
}

/** Every `manifest.json` under the downloaded artifact tree. */
function findManifests(dir) {
  const out = [];
  if (!fs.existsSync(dir)) return out;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...findManifests(full));
    else if (entry.name === "manifest.json") out.push(full);
  }
  return out;
}

function readJson(file) {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch {
    return null;
  }
}

/** Open issues that already declare a browser-sweep fingerprint. */
function openIssuesByFingerprint() {
  const map = new Map();
  let raw = "[]";
  try {
    raw = gh([
      "issue", "list",
      "--state", "open",
      "--label", "alert-intake",
      "--limit", "200",
      "--json", "number,title,body",
    ]);
  } catch (err) {
    // A failed read is UNKNOWN dedup state. Returning an empty map would make
    // every finding look new and file duplicates, so signal it instead.
    console.error(`[filer] could not list open issues: ${err.message}`);
    return null;
  }
  for (const issue of JSON.parse(raw || "[]")) {
    const body = String(issue.body || "");
    const re = new RegExp(`${MARKER_KEY}:([a-z0-9._:/-]{1,240})`, "g");
    let m;
    while ((m = re.exec(body)) !== null) map.set(m[1], issue.number);
  }
  return map;
}

function issueBody(finding, manifestPath) {
  return [
    "## What the browser audit saw",
    "",
    `**${finding.assertion_id}** failed on \`${finding.journey_id}\` [${finding.project}].`,
    "",
    finding.detail ? `> ${finding.detail}` : "> (no detail recorded)",
    "",
    "| field | value |",
    "|---|---|",
    `| journey | \`${finding.journey_id}\` |`,
    `| project | ${finding.project} |`,
    `| url | ${finding.url || "unrecorded"} |`,
    `| reason code | \`${finding.reason_code}\` |`,
    `| audited commit | \`${HEAD_SHA || "unrecorded"}\` |`,
    `| run | ${RUN_URL || "unrecorded"} |`,
    `| manifest | \`${path.basename(path.dirname(manifestPath))}\` |`,
    "",
    "Screenshots and the full manifest are attached to the run above as artifacts.",
    "",
    "---",
    "",
    `\`${MARKER_KEY}:${finding.fingerprint}\` (dedupe key — do not edit)`,
  ].join("\n");
}

function main() {
  const manifests = findManifests(ROOT);
  const summary = [];

  if (manifests.length === 0) {
    // No manifest is ARTIFACT_UNAVAILABLE, not "all clear".
    console.error("[filer] no manifest found in the triggering run's artifacts — refusing.");
    summary.push("", "**Refused:** no manifest in the triggering run's artifacts (`ARTIFACT_UNAVAILABLE`).");
    fs.writeFileSync("filer-summary.md", summary.join("\n"));
    return 1;
  }

  const open = openIssuesByFingerprint();
  if (open === null) {
    console.error("[filer] dedup state unknown — refusing to file rather than risk duplicates.");
    summary.push("", "**Refused:** could not read open issues, so dedup state is unknown.");
    fs.writeFileSync("filer-summary.md", summary.join("\n"));
    return 1;
  }

  summary.push("", `| manifest | journey | reason | action |`, "|---|---|---|---|");
  let failures = 0;

  for (const manifestPath of manifests) {
    const manifest = readJson(manifestPath);
    const manifestValid = Boolean(manifest && manifest.run && Array.isArray(manifest.journeys));
    const shaBound = Boolean(
      manifest && manifest.run && manifest.run.observed_frontend_sha
    );

    for (const finding of findingsFromManifest(manifest)) {
      // Infra findings are graded INFRA so the state machine no-ops them; a
      // dead runner is never a product defect.
      const verdict = finding.infra ? "INFRA" : "FAIL";
      const decision = decide({
        verdict,
        manifestValid,
        shaBound,
        fingerprint: finding.fingerprint,
        openIssue: open.has(finding.fingerprint),
      });

      const label = `${finding.journey_id} · ${finding.reason_code} → **${decision.action}**`;
      console.log(`[filer] ${label}`);
      summary.push(
        `| \`${path.basename(path.dirname(manifestPath))}\` | ${finding.journey_id} | \`${finding.reason_code}\` | ${decision.action}${decision.reason_codes.length ? ` (${decision.reason_codes.join(", ")})` : ""} |`
      );

      try {
        if (decision.action === ACTIONS.FILE) {
          const title = `Browser audit: ${finding.reason_code} on ${finding.journey_id}`;
          gh([
            "issue", "create",
            "--title", title,
            "--body", issueBody(finding, manifestPath),
            ...LABELS.flatMap((l) => ["--label", l]),
          ]);
          // Record it immediately so a second finding with the same fingerprint
          // in this same run comments rather than files again.
          open.set(finding.fingerprint, -1);
          failures += 1;
        } else if (decision.action === ACTIONS.COMMENT) {
          const number = open.get(finding.fingerprint);
          if (number && number > 0) {
            gh([
              "issue", "comment", String(number),
              "--body", `Still failing on \`${HEAD_SHA || "unknown"}\` — ${RUN_URL}`,
            ]);
          }
          failures += 1;
        }
      } catch (err) {
        console.error(`[filer] action ${decision.action} failed: ${err.message}`);
        return 1;
      }
    }
  }

  if (failures === 0) summary.push("| — | — | — | nothing to file |");
  fs.writeFileSync("filer-summary.md", summary.join("\n"));
  console.log(`[filer] ${manifests.length} manifest(s), ${failures} finding(s) acted on.`);
  return 0;
}

process.exit(main());
