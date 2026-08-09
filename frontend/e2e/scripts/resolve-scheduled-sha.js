#!/usr/bin/env node
"use strict";

/**
 * UX-P029 Item 1 — resolve the commit a SCHEDULED browser audit should grade.
 *
 * A dispatched run names the commit it wants to prove; a cron run cannot. The
 * honest scheduled question is "is whatever is live right now healthy?", so this
 * reads the deployed marker and binds the run to it.
 *
 * The binding is NOT weakened by discovering the SHA instead of being told it:
 * the downstream `wait-for-frontend-sha` step still proves requested == observed,
 * and the ancestry step still proves the graded code descends from the audited
 * commit. All this does is supply the value; every gate after it is unchanged.
 *
 * What it must never do is let a scheduled run proceed unbound. An unreadable
 * marker exits non-zero — "audit whatever happens to answer" is precisely the
 * false-green shape this rail exists to prevent.
 *
 *   AUDIT_SHA_SOURCE=dispatch|discovered  is exported so the manifest and the
 *   run summary record HOW the commit was chosen. A reader must never have to
 *   guess whether a green was requested or stumbled upon.
 */

const fs = require("node:fs");
const { fetchFrontendBuild, FULL_SHA_RE } = require("../helpers/buildAuthority");

function exportEnv(key, value) {
  console.log(`[browser-audit] ${key}=${value}`);
  if (process.env.GITHUB_ENV) {
    fs.appendFileSync(process.env.GITHUB_ENV, `${key}=${value}\n`);
  }
}

async function main() {
  const dispatched = String(process.env.AUDIT_REQUESTED_SHA || "").trim();
  const baseUrl = process.env.TRACE_BASE_URL || "https://www.bainluck.com";

  if (dispatched) {
    // A dispatched value is validated by the workflow's own input check; this
    // script must not second-guess or rewrite it.
    exportEnv("AUDIT_SHA_SOURCE", "dispatch");
    return 0;
  }

  console.log(`[browser-audit] scheduled run — resolving the live commit from ${baseUrl}/api/frontend-build`);
  const build = await fetchFrontendBuild(baseUrl);

  if (!build.ok || !build.commit) {
    console.error(
      `[browser-audit] FAIL — could not read the deployed build marker: ${build.error || "no commit field"}`
    );
    console.error("[browser-audit] refusing to run: a scheduled audit that cannot name the commit it graded proves nothing.");
    return 1;
  }
  if (!FULL_SHA_RE.test(build.commit)) {
    console.error(`[browser-audit] FAIL — build marker reported a non-40-hex commit: ${build.commit}`);
    return 1;
  }

  exportEnv("AUDIT_REQUESTED_SHA", build.commit);
  exportEnv("AUDIT_SHA_SOURCE", "discovered");
  return 0;
}

main()
  .then((code) => process.exit(code))
  .catch((err) => {
    console.error(`[browser-audit] FAIL — ${(err && err.stack) || err}`);
    process.exit(1);
  });
