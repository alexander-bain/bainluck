"use strict";

/**
 * L2-221 Item 1 — the versioned evidence manifest and its validator.
 *
 * The invariant this file exists to enforce (C96 "Evidence schema"):
 *
 *   A manifest is valid only when schema validation passes, the requested SHA
 *   equals the observed FRONTEND SHA, the selected count is positive, and
 *   every selected journey has a terminal result and required artifacts.
 *
 * Everything else in the rail can be re-implemented; this is the gate that
 * makes "the run was green" mean something. It is deliberately hand-rolled
 * (no ajv, no dependency) so it runs from bare `node` in a workflow step and
 * is trivially unit-testable. `schema/audit-manifest.schema.json` publishes
 * the same contract for interop, and a contract test proves the two agree.
 */

const crypto = require("node:crypto");
const { TERMINAL_RESULTS } = require("./journey");
const { normalizeSha } = require("./buildAuthority");
const { assertRedacted } = require("./redaction");

const SCHEMA_VERSION = "browser-audit/v1";

const REQUIRED_RUN_FIELDS = Object.freeze([
  "run_id",
  "run_url",
  "pack",
  "trigger",
  "started_at_utc",
  "started_at_pt",
  "finished_at_utc",
  "requested_frontend_sha",
  "observed_frontend_sha",
  "base_url",
  "runtime",
  "selected_count",
  "completed_count",
  "failed_count",
  "result",
]);

const REQUIRED_JOURNEY_FIELDS = Object.freeze([
  "journey_id",
  "project",
  "viewport",
  "url_path",
  "started_at_utc",
  "finished_at_utc",
  "duration_ms",
  "assertions",
  "console_errors",
  "page_errors",
  "failed_requests",
  "artifacts",
  "attempt",
  "result",
]);

const REQUIRED_RUNTIME_FIELDS = Object.freeze(["node", "playwright", "browser", "os"]);

const SHA256_RE = /^[0-9a-f]{64}$/;

/** @param {Buffer|string} data */
function sha256(data) {
  return crypto.createHash("sha256").update(data).digest("hex");
}

/** ISO-8601 UTC, and the Pacific rendering Alex reads. */
function stamps(date) {
  const d = date instanceof Date ? date : new Date(date);
  return {
    utc: d.toISOString(),
    pt: new Intl.DateTimeFormat("en-CA", {
      timeZone: "America/Los_Angeles",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    }).format(d),
  };
}

/**
 * Derive the run-level terminal result from the journeys. Never optimistic:
 * one infra_error makes the whole run an infra_error, one fail makes it a
 * fail, and an empty journey list is an infra_error (a rail that collected
 * nothing must never conclude success — the exact defect r323 found in the
 * dead provider's sweep).
 *
 * @param {Array<{result: string}>} journeys
 * @param {{ superseded?: boolean }} [options]
 * @returns {"pass"|"fail"|"infra_error"|"superseded"}
 */
function deriveRunResult(journeys, options) {
  if (options && options.superseded) return "superseded";
  const list = Array.isArray(journeys) ? journeys : [];
  if (list.length === 0) return "infra_error";
  if (list.some((j) => j && j.result === "infra_error")) return "infra_error";
  if (list.some((j) => j && j.result === "superseded")) return "superseded";
  if (list.some((j) => !j || j.result !== "pass")) return "fail";
  return "pass";
}

/**
 * @param {any} input
 * @returns {any} the manifest object (not yet validated — always validate it)
 */
function buildRunManifest(input) {
  const journeys = Array.isArray(input.journeys) ? input.journeys : [];
  const started = stamps(input.startedAt || new Date());
  const finished = stamps(input.finishedAt || new Date());
  const failed = journeys.filter((j) => j && j.result !== "pass").length;

  return {
    schema_version: SCHEMA_VERSION,
    run: {
      run_id: String(input.runId || "local"),
      run_url: String(input.runUrl || "local"),
      pack: String(input.pack || "deploy-smoke"),
      trigger: String(input.trigger || "manual"),
      started_at_utc: started.utc,
      started_at_pt: started.pt,
      finished_at_utc: finished.utc,
      finished_at_pt: finished.pt,
      requested_frontend_sha: normalizeSha(input.requestedFrontendSha),
      observed_frontend_sha: normalizeSha(input.observedFrontendSha),
      // Recorded, never substituted for the frontend authority.
      observed_backend_sha: input.observedBackendSha || null,
      base_url: String(input.baseUrl || ""),
      final_origin: input.finalOrigin || null,
      runtime: {
        node: String((input.runtime && input.runtime.node) || process.version),
        playwright: String((input.runtime && input.runtime.playwright) || "unknown"),
        browser: String((input.runtime && input.runtime.browser) || "unknown"),
        os: String((input.runtime && input.runtime.os) || `${process.platform}-${process.arch}`),
      },
      selected_count: Number.isFinite(input.selectedCount) ? input.selectedCount : 0,
      completed_count: journeys.length,
      failed_count: failed,
      result: input.result || deriveRunResult(journeys, { superseded: input.superseded }),
      superseded_by: input.supersededBy || null,
      notes: Array.isArray(input.notes) ? input.notes : [],
    },
    journeys,
  };
}

function isNonEmptyString(value) {
  return typeof value === "string" && value.trim().length > 0;
}

/**
 * @param {any} manifest
 * @returns {{ ok: boolean, errors: string[] }}
 */
function validateManifest(manifest) {
  /** @type {string[]} */
  const errors = [];

  if (!manifest || typeof manifest !== "object") {
    return { ok: false, errors: ["manifest is not an object"] };
  }
  if (manifest.schema_version !== SCHEMA_VERSION) {
    errors.push(`schema_version must be "${SCHEMA_VERSION}" (got ${JSON.stringify(manifest.schema_version)})`);
  }

  const run = manifest.run;
  if (!run || typeof run !== "object") {
    errors.push("run block is missing");
    return { ok: false, errors };
  }

  for (const field of REQUIRED_RUN_FIELDS) {
    const value = run[field];
    if (value === undefined || value === null || value === "") {
      errors.push(`run.${field} is required`);
    }
  }

  if (run.runtime && typeof run.runtime === "object") {
    for (const field of REQUIRED_RUNTIME_FIELDS) {
      if (!isNonEmptyString(run.runtime[field])) errors.push(`run.runtime.${field} is required`);
    }
  }

  if (!TERMINAL_RESULTS.includes(run.result)) {
    errors.push(`run.result must be one of ${TERMINAL_RESULTS.join("|")} (got ${JSON.stringify(run.result)})`);
  }

  // --- Invariant 1: a run that selected nothing is never valid evidence. ---
  if (!(Number.isInteger(run.selected_count) && run.selected_count > 0)) {
    errors.push("run.selected_count must be a positive integer — a run that selected zero journeys proves nothing");
  }

  const journeys = Array.isArray(manifest.journeys) ? manifest.journeys : null;
  if (!journeys) {
    errors.push("journeys must be an array");
    return { ok: false, errors };
  }
  if (journeys.length === 0) {
    errors.push("journeys must not be empty — a run that collected nothing must never validate");
  }
  if (run.completed_count !== journeys.length) {
    errors.push(`run.completed_count (${run.completed_count}) must equal the number of journeys (${journeys.length})`);
  }
  if (Number.isInteger(run.selected_count) && journeys.length > run.selected_count) {
    errors.push(`journeys (${journeys.length}) exceed run.selected_count (${run.selected_count})`);
  }

  // --- Invariant 2: exact frontend build authority. Backend never substitutes. ---
  const requested = normalizeSha(run.requested_frontend_sha);
  const observed = normalizeSha(run.observed_frontend_sha);
  if (!requested) errors.push("run.requested_frontend_sha must be a full 40-hex sha");
  if (!observed) {
    errors.push("run.observed_frontend_sha must be a full 40-hex sha read from the frontend build marker");
  }
  if (requested && observed && requested !== observed && run.result !== "superseded") {
    errors.push(`frontend sha mismatch: requested ${requested}, deployed ${observed}`);
  }
  if (run.result === "superseded" && !isNonEmptyString(run.superseded_by)) {
    errors.push("run.superseded_by is required when run.result is superseded");
  }

  // --- Invariant 3: every journey terminal, evidenced, and consistent. ---
  const seen = new Set();
  journeys.forEach((journey, index) => {
    const where = `journeys[${index}]`;
    if (!journey || typeof journey !== "object") {
      errors.push(`${where} is not an object`);
      return;
    }
    for (const field of REQUIRED_JOURNEY_FIELDS) {
      if (journey[field] === undefined || journey[field] === null) {
        errors.push(`${where}.${field} is required`);
      }
    }
    const key = `${journey.journey_id}::${journey.project}`;
    if (seen.has(key)) errors.push(`${where} duplicates journey id ${key}`);
    seen.add(key);

    if (!TERMINAL_RESULTS.includes(journey.result)) {
      errors.push(`${where}.result must be one of ${TERMINAL_RESULTS.join("|")} (got ${JSON.stringify(journey.result)})`);
    }
    if (!Array.isArray(journey.assertions) || journey.assertions.length === 0) {
      errors.push(`${where}.assertions must be a non-empty array`);
    } else {
      journey.assertions.forEach((a, ai) => {
        if (!a || !isNonEmptyString(a.assertion_id) || typeof a.ok !== "boolean") {
          errors.push(`${where}.assertions[${ai}] needs assertion_id and a boolean ok`);
        }
      });
      const anyFailed = journey.assertions.some((a) => a && a.ok === false);
      if (anyFailed && journey.result === "pass") {
        errors.push(`${where} reports pass while carrying a failed assertion`);
      }
      if (!anyFailed && journey.result === "fail") {
        errors.push(`${where} reports fail with no failed assertion`);
      }
    }
    if (!Array.isArray(journey.artifacts) || journey.artifacts.length === 0) {
      errors.push(`${where}.artifacts must be a non-empty array — a journey with no evidence is not proof`);
    } else {
      journey.artifacts.forEach((artifact, ai) => {
        if (!artifact || !isNonEmptyString(artifact.name)) {
          errors.push(`${where}.artifacts[${ai}].name is required`);
        }
        if (!artifact || !SHA256_RE.test(String(artifact.sha256 || ""))) {
          errors.push(`${where}.artifacts[${ai}].sha256 must be a 64-hex digest`);
        }
      });
    }
  });

  const observedFail = journeys.filter((j) => j && j.result !== "pass").length;
  if (run.failed_count !== observedFail) {
    errors.push(`run.failed_count (${run.failed_count}) must equal the number of non-pass journeys (${observedFail})`);
  }

  // --- Invariant 4: the run result must agree with the journeys it carries. ---
  const derived = deriveRunResult(journeys, { superseded: run.result === "superseded" });
  if (run.result !== derived) {
    errors.push(`run.result (${run.result}) disagrees with the journeys, which derive ${derived}`);
  }

  // --- Invariant 5: nothing sensitive survived redaction. ---
  const redaction = assertRedacted(manifest);
  if (!redaction.ok) {
    errors.push(`redaction failed — manifest contains ${redaction.leaks.join(", ")}`);
  }

  return { ok: errors.length === 0, errors };
}

module.exports = {
  SCHEMA_VERSION,
  REQUIRED_RUN_FIELDS,
  REQUIRED_JOURNEY_FIELDS,
  REQUIRED_RUNTIME_FIELDS,
  sha256,
  stamps,
  deriveRunResult,
  buildRunManifest,
  validateManifest,
};
