#!/usr/bin/env node
"use strict";

/**
 * L2-221 Item 2 — bounded wait for the EXACT deployed frontend commit.
 *
 * Usage:
 *   AUDIT_REQUESTED_SHA=<40-hex> TRACE_BASE_URL=https://www.bainluck.com \
 *     node scripts/wait-for-frontend-sha.js [--timeout-ms 600000] [--interval-ms 10000]
 *
 * Writes `AUDIT_OBSERVED_FRONTEND_SHA` (and the separately-labelled
 * `AUDIT_OBSERVED_BACKEND_SHA`) to `$GITHUB_ENV` when running in Actions, and
 * prints them locally.
 *
 * Why this exists (C96 [P1]): Vercel deploys independently of Heroku and of
 * the GitHub SHA. Without reading the frontend's own marker, a post-push run
 * can exercise the PREVIOUS or the NEXT deployment and still be attached as
 * proof for the requested commit. The backend `/health` sha is recorded here
 * too — as a second ledger entry, never as a substitute.
 */

const fs = require("node:fs");
const { waitForFrontendSha, fetchBackendHealthSha } = require("../helpers/buildAuthority");

function arg(name, fallback) {
  const index = process.argv.indexOf(name);
  if (index === -1) return fallback;
  return process.argv[index + 1];
}

function exportEnv(key, value) {
  console.log(`[browser-audit] ${key}=${value}`);
  if (process.env.GITHUB_ENV) {
    fs.appendFileSync(process.env.GITHUB_ENV, `${key}=${value}\n`);
  }
}

async function main() {
  const requestedSha = process.env.AUDIT_REQUESTED_SHA;
  const baseUrl = process.env.TRACE_BASE_URL || "https://www.bainluck.com";
  const apiBaseUrl = process.env.AUDIT_API_BASE_URL || "https://api.bainluck.com";
  const timeoutMs = Number(arg("--timeout-ms", process.env.AUDIT_SHA_TIMEOUT_MS || 600_000));
  const intervalMs = Number(arg("--interval-ms", process.env.AUDIT_SHA_INTERVAL_MS || 10_000));

  console.log(`[browser-audit] waiting for ${baseUrl}/api/frontend-build to report ${requestedSha}`);
  console.log(`[browser-audit] bound: ${timeoutMs}ms, polling every ${intervalMs}ms`);

  const result = await waitForFrontendSha({
    baseUrl,
    requestedSha,
    timeoutMs,
    intervalMs,
    onAttempt: ({ attempt, observed, error }) => {
      console.log(
        `[browser-audit]   attempt ${attempt}: deployed=${observed ?? "unreadable"}` +
          (error ? ` (${error})` : "")
      );
    },
  });

  // Recorded whether or not the frontend matched — a skew is worth seeing.
  const backend = await fetchBackendHealthSha(apiBaseUrl);
  exportEnv("AUDIT_OBSERVED_BACKEND_SHA", backend.observed_backend_sha ?? "unavailable");
  if (backend.error) console.log(`[browser-audit] backend /health unreadable: ${backend.error}`);

  if (!result.ok) {
    console.error(`[browser-audit] FAIL — ${result.reason}`);
    if (result.lastError) console.error(`[browser-audit] last error: ${result.lastError}`);
    console.error(
      "[browser-audit] refusing to run: a browser audit that cannot prove WHICH build it " +
        "exercised is not evidence."
    );
    process.exit(1);
  }

  exportEnv("AUDIT_OBSERVED_FRONTEND_SHA", result.observed);
  console.log(`[browser-audit] frontend deployment confirmed after ${result.attempts} attempt(s)`);
}

main().catch((err) => {
  console.error(`[browser-audit] FAIL — ${err && err.stack ? err.stack : err}`);
  process.exit(1);
});
