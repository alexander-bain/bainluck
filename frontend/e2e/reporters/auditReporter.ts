import fs from "node:fs";
import path from "node:path";
import type {
  FullConfig,
  FullResult,
  Reporter,
  Suite,
  TestCase,
  TestResult,
} from "@playwright/test/reporter";

import { buildRunManifest, validateManifest, type JourneyRecord } from "../helpers/manifest";
import { ATTACHMENT_NAME } from "../fixtures/audit";

/**
 * L2-221 Item 1 — the run manifest is produced by the runner, not by hand.
 *
 * `selected_count` comes from Playwright's own selection (`suite.allTests()`),
 * so "zero journeys selected" is recorded as a fact rather than inferred from
 * an empty directory. A test that dies before writing its journey attachment
 * is synthesised as an `infra_error` journey — silence is never a pass.
 */
export default class AuditReporter implements Reporter {
  private selected = 0;
  private readonly journeys: JourneyRecord[] = [];
  private readonly startedAt = new Date();
  private outDir = process.env.AUDIT_OUT_DIR || "audit-out";

  onBegin(_config: FullConfig, suite: Suite): void {
    this.selected = suite.allTests().length;
  }

  onTestEnd(test: TestCase, result: TestResult): void {
    const attachment = result.attachments.find((a) => a.name === ATTACHMENT_NAME);
    let record: JourneyRecord | null = null;
    if (attachment?.body) {
      record = JSON.parse(attachment.body.toString("utf8")) as JourneyRecord;
    } else if (attachment?.path && fs.existsSync(attachment.path)) {
      record = JSON.parse(fs.readFileSync(attachment.path, "utf8")) as JourneyRecord;
    }

    if (record) {
      // Retries: keep the last attempt for a given journey+project.
      const key = `${record.journey_id}::${record.project}`;
      const existing = this.journeys.findIndex((j) => `${j.journey_id}::${j.project}` === key);
      if (existing >= 0) this.journeys[existing] = record;
      else this.journeys.push(record);
      return;
    }

    // No journey attachment: the test never reached `journey.finish()`.
    // A timeout, a crash, or a throw in setup all land here. This must not be
    // invisible — synthesise a terminal infra_error so the run cannot be green.
    const journeyId = test.title.replace(/\s+/g, "-").toLowerCase().slice(0, 80) || "unknown-journey";
    this.journeys.push({
      journey_id: journeyId,
      project: test.parent.project()?.name ?? "unknown",
      viewport: null,
      url_path: "",
      redirect_chain: [],
      selected_fixture_ids: [],
      started_at_utc: new Date(result.startTime).toISOString(),
      finished_at_utc: new Date(result.startTime.getTime() + result.duration).toISOString(),
      duration_ms: Math.max(0, Math.round(result.duration)),
      assertions: [
        {
          assertion_id: "evidence.journey_recorded",
          ok: false,
          detail: `test ended "${result.status}" without producing a journey record`,
        },
      ],
      checked_clean: [],
      console_errors: [],
      page_errors: [],
      failed_requests: [],
      telemetry_requests: [],
      first_card_ms: null,
      artifacts: [],
      attempt: result.retry + 1,
      result: "infra_error",
    });
  }

  async onEnd(result: FullResult): Promise<void> {
    fs.mkdirSync(this.outDir, { recursive: true });

    const manifest = buildRunManifest({
      runId: process.env.GITHUB_RUN_ID || "local",
      runUrl:
        process.env.GITHUB_RUN_ID && process.env.GITHUB_REPOSITORY
          ? `https://github.com/${process.env.GITHUB_REPOSITORY}/actions/runs/${process.env.GITHUB_RUN_ID}`
          : "local",
      pack: process.env.AUDIT_PACK || "deploy-smoke",
      trigger: process.env.AUDIT_TRIGGER || "manual",
      startedAt: this.startedAt,
      finishedAt: new Date(),
      requestedFrontendSha: process.env.AUDIT_REQUESTED_SHA || null,
      observedFrontendSha: process.env.AUDIT_OBSERVED_FRONTEND_SHA || null,
      observedBackendSha: process.env.AUDIT_OBSERVED_BACKEND_SHA || null,
      // L2-223: which commit's grading code produced this verdict, and how it
      // relates to the deployed commit. Both are established by the workflow
      // (`git rev-parse` / `git merge-base --is-ancestor`) — the reporter only
      // transcribes them, so it cannot upgrade an unproven relationship.
      checkoutSha: process.env.AUDIT_CHECKOUT_SHA || null,
      checkoutAncestry: process.env.AUDIT_CHECKOUT_ANCESTRY || null,
      // Playwright's process-level verdict. Recorded even when it disagrees
      // with the journeys, because that disagreement is the finding.
      runnerStatus: result.status,
      baseUrl: process.env.TRACE_BASE_URL || "https://www.bainluck.com",
      apiBaseUrl: process.env.AUDIT_API_BASE_URL || null,
      // The origin the browser actually ended on, observed rather than
      // declared. Held to the same allowlist as base_url, so a canonical start
      // that redirects to a preview host cannot be filed as production proof.
      finalOrigin: this.journeys.map((j) => j.final_origin).find((o) => typeof o === "string" && o) ?? null,
      runtime: {
        node: process.version,
        playwright: readPlaywrightVersion(),
        browser: process.env.AUDIT_BROWSER_VERSION || "chromium",
        os: `${process.platform}-${process.arch}`,
      },
      selectedCount: this.selected,
      journeys: this.journeys,
      notes: result.status === "interrupted" ? ["playwright run was interrupted"] : [],
    });

    const manifestPath = path.join(this.outDir, "manifest.json");
    fs.writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");

    const validation = validateManifest(manifest);
    // eslint-disable-next-line no-console
    console.log(
      `[browser-audit] manifest → ${manifestPath}\n` +
        `[browser-audit] selected=${manifest.run.selected_count} completed=${manifest.run.completed_count} ` +
        `failed=${manifest.run.failed_count} result=${manifest.run.result}\n` +
        `[browser-audit] schema=${validation.ok ? "valid" : "INVALID"}` +
        (validation.ok ? "" : `\n${validation.errors.map((e) => `  ✗ ${e}`).join("\n")}`)
    );
  }
}

function readPlaywrightVersion(): string {
  try {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    return require("@playwright/test/package.json").version as string;
  } catch {
    return "unknown";
  }
}
