import fs from "node:fs";
import path from "node:path";
import { test as base, type Page, type TestInfo } from "@playwright/test";

import {
  evaluateJourney,
  type JourneyObservation,
  type MainRegionObservation,
  type TelemetryExpectation,
} from "../helpers/journey";
import { sha256, CANONICAL_ORIGINS } from "../helpers/manifest";
import type { JourneyRecord } from "../helpers/manifest";
import { redactText, redactUrl } from "../helpers/redaction";
import { compareSha } from "../helpers/buildAuthority";
import { describeAbort, type AbortPacket } from "../helpers/abortRecord";

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

/** Mirrors `ARTIFACT_ROOT` in `helpers/manifest.js`; a contract test pins them together. */
const ARTIFACT_SUBDIR = "artifacts";

/** The directory the manifest is written to — artifact paths are relative to it. */
function auditOutDir(): string {
  return process.env.AUDIT_OUT_DIR || "audit-out";
}

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
  /**
   * L2-239 — the preferred form. Raw measurements the shared evaluator grades,
   * so a spec cannot decide for itself whether the page was blank. Supply this
   * OR `mainRegionNonBlank`; supplying neither is a failed assertion, not a
   * skipped one.
   */
  mainRegion?: MainRegionObservation | null;
  /** Legacy pre-computed verdict, for surfaces not yet converted. */
  mainRegionNonBlank?: boolean;
  selectedFixtureIds?: string[];
  allowedFailures?: string[];
  /**
   * Console-error substrings this journey EXPECTS, declared one by one.
   * Anything undeclared still fails, and a declared allowance that matches
   * nothing fails too — see `helpers/journey.js` for why both halves matter.
   */
  allowedConsoleErrors?: string[];
  /** `"none"` for journeys whose subject is not the feed (the consent pack). */
  contentMode?: "card" | "none";
  /**
   * What this journey claims about telemetry destinations. Evaluated by the
   * shared ledger, which requires a non-trivial observation window before it
   * believes an absence — see `helpers/journey.js`.
   */
  telemetryExpectation?: TelemetryExpectation | null;
}

export class JourneyRecorder {
  readonly consoleErrors: string[] = [];
  readonly pageErrors: string[] = [];
  readonly failedRequests: Array<{ url: string; method: string; status: number | null; failure: string | null; abort?: AbortPacket }> = [];
  readonly redirectChain: string[] = [];
  readonly telemetry = new Map<string, { host: string; path: string; count: number }>();

  private readonly startedAt = new Date();
  private crashed: { crashed: boolean; reason: string } | null = null;
  /**
   * When the telemetry watch began. Set at construction, so the window is the
   * whole journey unless a spec deliberately restarts it (e.g. after a Decline,
   * where only what happens AFTER the choice is evidence).
   */
  private telemetryWatchStart = Date.now();

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
      const failureText = req.failure()?.errorText ?? "request failed";
      const url = req.url();
      const record: { url: string; method: string; status: number | null; failure: string | null; abort?: AbortPacket } = {
        url: redactUrl(url),
        method: req.method(),
        status: null,
        failure: redactText(failureText, { maxLength: 200 }),
      };
      // #1525 Shape A — carry BOUNDED abort timing so a navigation teardown is
      // distinguishable from a client timeout, and so an aborted first-party
      // feed request (invisible to the backend's own metrics) is legible here.
      let frameUrl: string | null = null;
      try {
        frameUrl = req.frame()?.url() ?? null;
      } catch {
        frameUrl = null;
      }
      const abort = describeAbort({
        failureText,
        resourceType: req.resourceType(),
        timing: req.timing(),
        frameUrl,
        isFeed: url.includes("/api/feed"),
      });
      if (abort) record.abort = abort;
      this.failedRequests.push(record);
    });
    this.page.on("response", (res) => {
      const url = res.url();
      const status = res.status();
      if (status >= 300 && status < 400) this.redirectChain.push(redactUrl(url));
      // First-party 4xx/5xx are product defects — that includes the backend
      // API, which is a different origin but entirely ours. Third-party noise
      // is not graded.
      if (status >= 400 && this.isFirstParty(url)) {
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

  /**
   * Origins whose 4xx/5xx are OUR defect.
   *
   * L2-223: this used to be the site origin alone, which quietly discarded the
   * most important failures the rail can see. Bain Luck's frontend renders
   * almost entirely from `api.bainluck.com` — a different origin — so every
   * backend 500 behind a blank Discover was filed as "third-party noise" and
   * the journey went green on the strength of a named empty state. A first
   * party is not defined by matching origins; it is defined by us owning it.
   */
  private firstPartyOrigins(): string[] {
    const origins = new Set<string>();
    const add = (value: string | undefined | null) => {
      if (!value) return;
      try {
        origins.add(new URL(value).origin);
      } catch {
        /* an unparseable base is caught by the manifest origin allowlist */
      }
    };
    add(this.testInfo.project.use?.baseURL ?? "https://www.bainluck.com");
    add(process.env.AUDIT_API_BASE_URL ?? "https://api.bainluck.com");
    return [...origins];
  }

  private isFirstParty(url: string): boolean {
    try {
      return this.firstPartyOrigins().includes(new URL(url).origin);
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

  /**
   * Discard everything seen so far and restart the telemetry window.
   *
   * A grant→revoke journey has to prove "zero requests AFTER the revoke", and
   * the requests from before it are legitimate. Without this, the only way to
   * express that would be to subtract counts by hand in the spec — arithmetic
   * that lives outside the evaluator and can therefore be got wrong silently.
   */
  resetTelemetryWindow(): void {
    this.telemetry.clear();
    this.telemetryWatchStart = Date.now();
  }

  /** Telemetry destinations seen in the current window. */
  telemetrySeen(): Array<{ host: string; path: string; count: number }> {
    return [...this.telemetry.values()];
  }

  async finish(input: FinishInput): Promise<JourneyRecord> {
    const finishedAt = new Date();
    const project = this.testInfo.project.name;
    const artifacts: Array<{ name: string; path: string; sha256: string; bytes: number }> = [];

    // Terminal screenshot: taken for EVERY outcome, not only failures. A pass
    // with no artifact is unverifiable after the fact.
    //
    // L2-223: written into `$AUDIT_OUT_DIR/artifacts/` — beside the manifest,
    // inside the one directory the workflow uploads — and recorded as a
    // relative path. A digest with no fetchable path cannot be re-hashed by a
    // reviewer, which made every artifact claim unfalsifiable.
    const shotName = `${input.journeyId}.${project}.terminal.png`;
    const relativePath = `${ARTIFACT_SUBDIR}/${shotName}`;
    try {
      const shotPath = path.join(auditOutDir(), ARTIFACT_SUBDIR, shotName);
      fs.mkdirSync(path.dirname(shotPath), { recursive: true });
      const buffer = await this.page.screenshot({ fullPage: true, path: shotPath });
      artifacts.push({
        name: shotName,
        path: relativePath,
        sha256: sha256(buffer),
        bytes: buffer.byteLength,
      });
      await this.testInfo.attach(shotName, { path: shotPath, contentType: "image/png" });
    } catch (err) {
      this.markInfraError(`terminal screenshot failed: ${redactText(err)}`);
    }

    // No trace is hashed here, deliberately (L2-223 Item 2). Playwright's trace
    // is a zip of the whole session — request/response bodies, storage, cookie
    // headers — and phase 1 uploads artifacts unconditionally with 90-day
    // retention and no reviewed containment policy. Scrubbing this manifest's
    // JSON fields would do nothing to those bytes, so tracing is off in
    // `playwright.config.ts` and the manifest validator REJECTS a declared
    // trace rather than quietly accepting one.

    const shaVerdict = compareSha(this.requestedSha, this.observedSha);
    const landed = (() => {
      try {
        const parsed = new URL(this.page.url());
        return { path: parsed.pathname, origin: parsed.origin };
      } catch {
        return { path: redactUrl(this.page.url()), origin: null as string | null };
      }
    })();
    const urlPath = landed.path;

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
      finalOrigin: landed.origin,
      canonicalOrigins: [...CANONICAL_ORIGINS],
      redirectChain: this.redirectChain,
      realCardFound: input.realCardFound,
      firstCardMs,
      emptyState: input.emptyState ?? null,
      mainRegion: input.mainRegion ?? null,
      mainRegionNonBlank: input.mainRegionNonBlank,
      consoleErrors: this.consoleErrors,
      pageErrors: this.pageErrors,
      failedRequests: this.failedRequests,
      allowedFailures: input.allowedFailures ?? [],
      allowedConsoleErrors: input.allowedConsoleErrors ?? [],
      artifacts,
      contentMode: input.contentMode ?? "card",
      telemetry: this.telemetrySeen(),
      telemetryExpectation: input.telemetryExpectation ?? null,
      telemetryWindowMs: Date.now() - this.telemetryWatchStart,
    };

    const verdict = evaluateJourney(observation);

    const record: JourneyRecord = {
      journey_id: input.journeyId,
      project,
      viewport: this.page.viewportSize(),
      url_path: urlPath,
      final_origin: landed.origin,
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
      telemetry_requests: this.telemetrySeen(),
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

/**
 * Read the page's content region for the blank-page check, without ever
 * waiting on a landmark that may not exist.
 *
 * L2-229. Every spec used to do this inline as
 * `page.locator("main").first().innerText()`. On the Discover surfaces that is
 * fine — they render a `<main>`. On `/calibration` there is no `<main>` at
 * all, and because Playwright's `actionTimeout` defaulted to unbounded, that
 * one call sat there until the 90s test budget expired. Playwright then tore
 * the context down, so the journey never reached `finish()`: nothing was
 * graded and the terminal screenshot fired against a closed page. Run
 * 30722940887 came back `infra_error` with an empty artifacts array on both
 * projects — a red that proves nothing, which is worse than a red that
 * explains itself.
 *
 * `count()` resolves immediately and never waits, so choosing the fallback
 * costs no budget. `body` is the honest region for a page with no `main`
 * landmark: the caller is testing for blankness, not for semantics. The read
 * is bounded explicitly as well as by the config, because this specific call
 * is the one that has already destroyed a run's evidence once.
 */
export async function readContentRegionText(page: Page, timeoutMs = 5_000): Promise<string> {
  const region =
    (await page.locator("main").count()) > 0
      ? page.locator("main").first()
      : page.locator("body").first();
  return (await region.innerText({ timeout: timeoutMs }).catch(() => "")) || "";
}

/**
 * Measure the main region for `classifyMainRegion` (L2-239).
 *
 * The point of measuring the skeleton's OWN text rather than merely noting that
 * a skeleton exists: `textLength - skeletonTextLength` is the rendered substance
 * that is not a loading placeholder, and it is the same number whether the route
 * segment contributed one shell or two. `/discover` and `/` therefore grade
 * identically for identical rendered content, which they did not before —
 * `app/discover/loading.tsx` gave `/discover` a second `discover-skeleton`
 * marker and the old `!skeletonVisible` clause turned that into a permanent red.
 *
 * Only VISIBLE skeletons are counted and measured. An inert marker Next left in
 * the document but is not painting is not a loading state, and Playwright's
 * `innerText` is visibility-aware for both reads, so the subtraction stays
 * coherent. Incoherent numbers are handled — as `malformed` — by the classifier,
 * not smoothed over here.
 *
 * Every read is bounded explicitly. This function is called at the END of a
 * journey, and an unbounded locator call there has already destroyed a run's
 * evidence once (see `readContentRegionText`).
 */
export async function measureMainRegion(
  page: Page,
  skeletonSelector: string,
  timeoutMs = 5_000
): Promise<MainRegionObservation> {
  const text = await readContentRegionText(page, timeoutMs);

  const skeletons = page.locator(skeletonSelector);
  const total = await skeletons.count().catch(() => 0);

  let visibleSkeletonCount = 0;
  let skeletonTextLength = 0;
  for (let i = 0; i < total; i += 1) {
    const node = skeletons.nth(i);
    const visible = await node.isVisible().catch(() => false);
    if (!visible) continue;
    visibleSkeletonCount += 1;
    const skeletonText = await node.innerText({ timeout: timeoutMs }).catch(() => "");
    skeletonTextLength += skeletonText.trim().length;
  }

  return {
    textLength: text.trim().length,
    skeletonTextLength,
    visibleSkeletonCount,
  };
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
