import fs from "node:fs";
import path from "node:path";
import { test as base, type Page, type TestInfo } from "@playwright/test";

import { evaluateJourney, type JourneyObservation } from "../helpers/journey";
import { sha256 } from "../helpers/manifest";
import type { JourneyRecord } from "../helpers/manifest";
import { redactText, redactUrl } from "../helpers/redaction";
import { compareSha } from "../helpers/buildAuthority";

/**
 * L2-221 Item 1 — one evidence collector, installed before navigation.
 *
 * C96's "Evidence collector" requirement: a single fixture installs listeners
 * for console, pageerror, request failures, response status, redirects and
 * telemetry destinations BEFORE the first navigation — listeners attached
 * after `goto` miss exactly the errors worth catching.
 *
 * Every journey ends by calling `journey.finish()`, which takes the terminal
 * screenshot, hashes it, runs the shared evaluator, attaches the journey
 * record, and throws if the verdict is not `pass`. There is no path where a
 * spec decides its own verdict.
 */

export const ATTACHMENT_NAME = "audit-journey.json";

/** Telemetry destinations the consent pack cares about (recorded, not blocked). */
const TELEMETRY_HOSTS = [
  "googletagmanager.com",
  "google-analytics.com",
  "analytics.google.com",
];
const TELEMETRY_PATHS = ["/_vercel/insights", "/_vercel/speed-insights"];

export interface FinishInput {
  /** Stable, machine-readable id — this is half of the defect fingerprint. */
  journeyId: string;
  expectedPath?: string;
  realCardFound: boolean;
  /** Only meaningful when `realCardFound` is true; ignored otherwise. */
  firstCardMs?: number | null;
  emptyState?: { name: string; visible: boolean } | null;
  mainRegionNonBlank: boolean;
  selectedFixtureIds?: string[];
  allowedFailures?: string[];
}

export class JourneyRecorder {
  readonly consoleErrors: string[] = [];
  readonly pageErrors: string[] = [];
  readonly failedRequests: Array<{ url: string; method: string; status: number | null; failure: string | null }> = [];
  readonly redirectChain: string[] = [];
  readonly telemetry = new Map<string, { host: string; path: string; count: number }>();

  private readonly startedAt = new Date();
  private crashed: { crashed: boolean; reason: string } | null = null;

  constructor(
    private readonly page: Page,
    private readonly testInfo: TestInfo,
    private readonly requestedSha: string | null,
    private readonly observedSha: string | null
  ) {}

  install(): void {
    this.page.on("console", (msg) => {
      if (msg.type() === "error") this.consoleErrors.push(redactText(msg.text()));
    });
    this.page.on("pageerror", (err) => {
      this.pageErrors.push(redactText(err?.message ?? String(err)));
    });
    this.page.on("crash", () => {
      this.crashed = { crashed: true, reason: "page crashed" };
    });
    this.page.on("requestfailed", (req) => {
      this.failedRequests.push({
        url: redactUrl(req.url()),
        method: req.method(),
        status: null,
        failure: redactText(req.failure()?.errorText ?? "request failed", { maxLength: 200 }),
      });
    });
    this.page.on("response", (res) => {
      const url = res.url();
      const status = res.status();
      if (status >= 300 && status < 400) this.redirectChain.push(redactUrl(url));
      // Same-origin 4xx/5xx are product defects; third-party noise is not ours.
      if (status >= 400 && this.isSameOrigin(url)) {
        this.failedRequests.push({
          url: redactUrl(url),
          method: res.request().method(),
          status,
          failure: null,
        });
      }
      this.recordTelemetry(url);
    });
    this.page.on("request", (req) => this.recordTelemetry(req.url()));
  }

  private isSameOrigin(url: string): boolean {
    try {
      const target = new URL(url);
      const base = new URL(this.testInfo.project.use?.baseURL ?? "https://www.bainluck.com");
      return target.origin === base.origin;
    } catch {
      return false;
    }
  }

  /**
   * Record only allowlisted telemetry metadata (host + path + count) — never
   * the payload, never the query values. The consent pack asserts on the
   * ABSENCE of these, so presence must be countable but never revealing.
   */
  private recordTelemetry(rawUrl: string): void {
    let parsed: URL;
    try {
      parsed = new URL(rawUrl);
    } catch {
      return;
    }
    const hostMatch = TELEMETRY_HOSTS.some((h) => parsed.hostname === h || parsed.hostname.endsWith(`.${h}`));
    const pathMatch = TELEMETRY_PATHS.some((p) => parsed.pathname.startsWith(p));
    if (!hostMatch && !pathMatch) return;
    const key = `${parsed.hostname}${parsed.pathname}`;
    const existing = this.telemetry.get(key);
    if (existing) existing.count += 1;
    else this.telemetry.set(key, { host: parsed.hostname, path: parsed.pathname, count: 1 });
  }

  /** Force an infra_error verdict (browser/runner broke, not the product). */
  markInfraError(reason: string): void {
    this.crashed = { crashed: true, reason };
  }

  async finish(input: FinishInput): Promise<JourneyRecord> {
    const finishedAt = new Date();
    const project = this.testInfo.project.name;
    const artifacts: Array<{ name: string; sha256: string; bytes: number }> = [];

    // Terminal screenshot: taken for EVERY outcome, not only failures. A pass
    // with no artifact is unverifiable after the fact.
    const shotName = `${input.journeyId}.${project}.terminal.png`;
    try {
      const shotPath = this.testInfo.outputPath(shotName);
      const buffer = await this.page.screenshot({ fullPage: true, path: shotPath });
      artifacts.push({ name: shotName, sha256: sha256(buffer), bytes: buffer.byteLength });
      await this.testInfo.attach(shotName, { path: shotPath, contentType: "image/png" });
    } catch (err) {
      this.markInfraError(`terminal screenshot failed: ${redactText(err)}`);
    }

    // Playwright's own trace is attached by the reporter; hash whatever it wrote.
    for (const attachment of this.testInfo.attachments) {
      if (attachment.name === "trace" && attachment.path && fs.existsSync(attachment.path)) {
        const buffer = fs.readFileSync(attachment.path);
        artifacts.push({
          name: path.basename(attachment.path),
          sha256: sha256(buffer),
          bytes: buffer.byteLength,
        });
      }
    }

    const shaVerdict = compareSha(this.requestedSha, this.observedSha);
    const urlPath = (() => {
      try {
        return new URL(this.page.url()).pathname;
      } catch {
        return redactUrl(this.page.url());
      }
    })();

    // A duration is only carried when a card was actually observed. This is
    // the false green being closed: the old spec always recorded elapsed time.
    const firstCardMs = input.realCardFound
      ? typeof input.firstCardMs === "number"
        ? Math.round(input.firstCardMs)
        : null
      : null;

    const observation: JourneyObservation = {
      infra: this.crashed,
      shaMatch: shaVerdict.match,
      shaDetail: shaVerdict.reason,
      expectedPath: input.expectedPath ?? null,
      urlPath,
      realCardFound: input.realCardFound,
      firstCardMs,
      emptyState: input.emptyState ?? null,
      mainRegionNonBlank: input.mainRegionNonBlank,
      consoleErrors: this.consoleErrors,
      pageErrors: this.pageErrors,
      failedRequests: this.failedRequests,
      allowedFailures: input.allowedFailures ?? [],
      artifacts,
    };

    const verdict = evaluateJourney(observation);

    const record: JourneyRecord = {
      journey_id: input.journeyId,
      project,
      viewport: this.page.viewportSize(),
      url_path: urlPath,
      redirect_chain: this.redirectChain,
      selected_fixture_ids: input.selectedFixtureIds ?? [],
      started_at_utc: this.startedAt.toISOString(),
      finished_at_utc: finishedAt.toISOString(),
      duration_ms: finishedAt.getTime() - this.startedAt.getTime(),
      assertions: verdict.assertions,
      checked_clean: verdict.checked_clean,
      console_errors: this.consoleErrors,
      page_errors: this.pageErrors,
      failed_requests: this.failedRequests,
      telemetry_requests: [...this.telemetry.values()],
      first_card_ms: firstCardMs,
      artifacts,
      attempt: this.testInfo.retry + 1,
      result: verdict.result,
    };

    await this.testInfo.attach(ATTACHMENT_NAME, {
      body: JSON.stringify(record, null, 2),
      contentType: "application/json",
    });

    if (record.result !== "pass") {
      const failed = record.assertions.filter((a) => !a.ok);
      throw new Error(
        `journey ${record.journey_id} [${project}] → ${record.result}\n` +
          failed.map((a) => `  ✗ ${a.assertion_id}: ${a.detail ?? "failed"}`).join("\n")
      );
    }
    return record;
  }
}

export const test = base.extend<{ journey: JourneyRecorder }>({
  journey: async ({ page }, use, testInfo) => {
    const recorder = new JourneyRecorder(
      page,
      testInfo,
      process.env.AUDIT_REQUESTED_SHA ?? null,
      process.env.AUDIT_OBSERVED_FRONTEND_SHA ?? null
    );
    recorder.install();
    await use(recorder);
  },
});

export { expect } from "@playwright/test";
