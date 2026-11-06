/**
 * @jest-environment jsdom
 */

/**
 * #12102 — the top screen (Alex, Nov 6): one plain answer and three pictures,
 * and no word that needs the glossary anywhere outside a "Show the details" fold.
 *
 * Alex's test, written down: the page's text outside every fold, its picture
 * labels included, is run against the banned-jargon list, and any hit fails.
 * The extractor has its own negative control, so a check that stopped reading
 * would fail rather than pass. Each picture is held to its record: one dot per
 * group in the live curve, one block per planned review, one circle per check.
 *
 * Below the top screen, one topic per question: a plain paragraph, a picture
 * outside the fold, and everything the page carried before inside that topic's
 * "Show the details" fold. The same jargon check covers them, because it reads
 * the whole page outside every fold.
 */

import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { SWRConfig } from "swr";

jest.mock("@/hooks", () => ({
  usePageTracking: () => {},
  useScrollDepth: () => {},
  useEngagementTime: () => {},
}));
jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ children, href, ...rest }: { children: React.ReactNode; href: unknown }) =>
    React.createElement("a", { href: String(href), ...rest }, children),
}));
jest.mock("@/lib/api", () => ({
  ...jest.requireActual("@/lib/api"),
  fetchCalibration: jest.fn(),
}));

import EvalsPage from "@/app/evals/page";
import { fetchCalibration } from "@/lib/api";
import { TERMS, TOP_COPY } from "@/lib/evals/copy";
import { calibrationFixture } from "@/lib/evals/fixtures/calibration";
import { forwardRecordView, type ForwardRecordView } from "@/lib/evals/forwardRecord";
import { loadReviewerResults, reviewerTally } from "@/lib/evals/reviewerResults";
import { loadReviewerStudy } from "@/lib/evals/reviewerStudy";
import { scanEvalsDom } from "@/lib/evals/scanEvalsDom";
import { truthDots, truthExample, truthReading, wholePercent } from "@/lib/evals/topScreen";
import { CHART_THIN_FLOOR } from "@/lib/evals/forwardRecord";
import { loadWatchers, watcherHealth } from "@/lib/evals/watchers";

const fetchCalibrationMock = fetchCalibration as jest.Mock;

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

/**
 * Alex's list (Nov 6), plus "blend" (the reader word is "combined probability")
 * and the US spelling of licence, which is the one this page uses.
 */
const BANNED_JARGON =
  /\b(precision|recall|wilson|held[- ]?out|shards?|fixtures?|contracts?|mutations?|fingerprints?|hash(?:es)?|denominators?|confusion|licen[cs]es?|gates?|verdicts?|blend(?:s|ed|ing)?)\b/gi;

/**
 * What a reader meets without opening a fold: the visible text outside every
 * `<details>`, plus the labels screen readers announce there.
 */
function aboveTheFold(root: Element): string {
  const clone = root.cloneNode(true) as Element;
  clone.querySelectorAll("details").forEach((d) => d.remove());
  const labels = Array.from(clone.querySelectorAll("[aria-label]")).map((el) => el.getAttribute("aria-label") ?? "");
  return [clone.textContent ?? "", ...labels].join(" ").replace(/\s+/g, " ");
}

let root: Root | null = null;
let host: HTMLElement | null = null;

async function mount(node: React.ReactElement): Promise<HTMLElement> {
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  await act(async () => {
    root?.render(node);
  });
  return host;
}

async function mountPage(): Promise<HTMLElement> {
  const page = await mount(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0, shouldRetryOnError: false }}>
      <EvalsPage />
    </SWRConfig>
  );
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
  return page;
}

beforeEach(() => {
  fetchCalibrationMock.mockReset();
  fetchCalibrationMock.mockResolvedValue(calibrationFixture());
});

afterEach(async () => {
  await act(async () => root?.unmount());
  host?.remove();
  root = null;
  host = null;
});

describe("no jargon above a fold (Alex, Nov 6)", () => {
  it("the page's text outside every fold has no word from the list", async () => {
    const page = await mountPage();
    const text = aboveTheFold(page);
    expect(text.length).toBeGreaterThan(200);
    expect(text.match(BANNED_JARGON) ?? []).toEqual([]);
  });

  it("no glossary term appears outside a fold either: a word that needs the glossary sits under one", async () => {
    const page = await mountPage();
    const text = aboveTheFold(page).toLowerCase();
    const escape = (w: string) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const hits = TERMS.map((t) => t.term).filter((term) => new RegExp(`\\b${escape(term.toLowerCase())}\\b`).test(text));
    expect(TERMS.length).toBeGreaterThan(10);
    expect(hits).toEqual([]);
  });

  it("the same holds while the live record is loading or unavailable", async () => {
    fetchCalibrationMock.mockReturnValue(new Promise(() => {}));
    let page = await mountPage();
    expect(aboveTheFold(page).match(BANNED_JARGON) ?? []).toEqual([]);
    await act(async () => root?.unmount());
    host?.remove();
    fetchCalibrationMock.mockRejectedValue(new Error("down"));
    page = await mountPage();
    expect(aboveTheFold(page).match(BANNED_JARGON) ?? []).toEqual([]);
  });

  it("the check can fail: a listed word outside a fold is found, the same word inside one is not", async () => {
    const page = await mount(
      <div>
        <p>Our gates held.</p>
        <span aria-label="a confusion matrix" />
        <details>
          <summary>{TOP_COPY.fold}</summary>
          <p>Held-out pairs, the Wilson range and every verdict.</p>
        </details>
      </div>
    );
    const hits = (aboveTheFold(page).match(BANNED_JARGON) ?? []).map((w) => w.toLowerCase());
    expect(hits).toEqual(["gates", "confusion"]);
  });

  it("everything the page carried before sits under a topic's fold, nothing dropped", async () => {
    const page = await mountPage();
    const folded: Record<string, string> = {
      "forward-record": "probabilities",
      exam: "matching",
      confusion: "matching",
      timeline: "matching",
      "tests-for-tests": "reviewer",
      "test-library": "tests",
      watchers: "checks",
      "how-to-read": "more",
      sources: "more",
    };
    for (const [id, topic] of Object.entries(folded)) {
      const fold = page.querySelector(`[data-evals-topic="${topic}"] > details[data-evals-fold="${topic}"]`);
      expect(fold?.querySelector("summary")?.textContent).toContain(TOP_COPY.fold);
      expect(fold?.querySelector(`#${id}`)).not.toBeNull();
    }
    // The planted-change meter sits with the library whose cases it grades, and the about text with how to read the page.
    expect(page.querySelector('[data-testid="evals-bite"]')?.closest("#test-library")).not.toBeNull();
    expect(page.querySelector('[data-testid="evals-about"]')?.closest('details[data-evals-fold="more"]')).not.toBeNull();
    // The gaps stay open: each row is plain words and its issue.
    expect(page.querySelector("#gaps")?.closest("details")).toBeNull();
  });
});

describe("the topics below the top screen", () => {
  it("one topic per question, in the top screen's order, with the gaps before the last", async () => {
    const page = await mountPage();
    const order = Array.from(page.querySelectorAll("[data-evals-topic], #gaps")).map(
      (t) => t.getAttribute("data-evals-topic") ?? t.id
    );
    expect(order).toEqual(["probabilities", "matching", "reviewer", "tests", "checks", "gaps", "more"]);
  });

  it("each opens with a plain paragraph and a picture outside its fold, the picture under its own label", async () => {
    const page = await mountPage();
    for (const id of ["probabilities", "matching", "reviewer", "tests", "checks"]) {
      const topic = page.querySelector(`[data-evals-topic="${id}"]`);
      expect(topic?.querySelector(":scope > h2")?.textContent).toBeTruthy();
      expect((topic?.querySelector(":scope > p")?.textContent ?? "").length).toBeGreaterThan(80);
      const picture = topic?.querySelector("[data-topic-picture]");
      expect(picture).not.toBeNull();
      expect(picture?.closest("details")).toBeNull();
      expect(picture?.getAttribute("data-truth-scope")).toBe(picture?.querySelector("[data-truth-chip]")?.getAttribute("data-truth"));
    }
  });

  it("a topic whose record cannot be read is absent, not empty", async () => {
    // A fresh module registry whose scoreboard cannot be read, with its own React to mount it.
    let parts: {
      R: typeof React;
      client: typeof import("react-dom/client");
      swr: typeof import("swr");
      Page: React.ComponentType;
    } | null = null;
    jest.isolateModules(() => {
      jest.doMock("@/lib/evals/scoreboard", () => ({
        ...jest.requireActual("@/lib/evals/scoreboard"),
        loadScoreboard: () => null,
      }));
      parts = {
        R: require("react"),
        client: require("react-dom/client"),
        swr: require("swr"),
        Page: require("@/app/evals/page").default,
      };
    });
    jest.dontMock("@/lib/evals/scoreboard");
    const { R, client, swr, Page } = parts!;
    const el = document.createElement("div");
    document.body.appendChild(el);
    const isolated = client.createRoot(el);
    await R.act(async () => {
      isolated.render(
        R.createElement(
          swr.SWRConfig,
          { value: { provider: () => new Map(), dedupingInterval: 0, shouldRetryOnError: false } },
          R.createElement(Page)
        )
      );
    });
    const topics = Array.from(el.querySelectorAll("[data-evals-topic]")).map((t) => t.getAttribute("data-evals-topic"));
    expect(topics).toEqual(["probabilities", "matching", "reviewer", "checks", "more"]);
    expect(el.querySelector("#test-library")).toBeNull();
    expect(el.querySelector('[data-testid="evals-bite"]')).toBeNull();
    await R.act(async () => isolated.unmount());
    el.remove();
  });
});

describe("the top screen: one plain answer, three pictures, each under its own label", () => {
  it("opens with the title and the plain answer, which says AI agents write most of the code (43-J1)", async () => {
    const page = await mountPage();
    const top = page.querySelector("[data-evals-top]");
    expect(top?.querySelector("h1")).not.toBeNull();
    expect(top?.textContent).toContain(TOP_COPY.answer);
    expect(TOP_COPY.answer).toMatch(/^AI agents write most of (the|this site's) code/);
  });

  it("has the three pictures in Alex's order, each with its label and a link to its record", async () => {
    const page = await mountPage();
    const cards = Array.from(page.querySelectorAll("[data-evals-top-card]"));
    expect(cards.map((c) => c.getAttribute("data-evals-top-card"))).toEqual(["truth", "reviewer", "watchers"]);
    for (const card of cards) {
      const chip = card.querySelector("[data-truth-chip]");
      expect(chip).not.toBeNull();
      expect(card.getAttribute("data-truth-scope")).toBe(chip?.getAttribute("data-truth"));
      expect(card.querySelector("[data-evals-exhibit]")?.getAttribute("data-source")).toMatch(/^https:\/\//);
    }
  });

  it("every number on the page is still a labelled, linked figure (the truth scan passes)", async () => {
    const page = await mountPage();
    const scan = scanEvalsDom(page);
    expect(scan.bareNumbers).toEqual([]);
    expect(scan.figuresOutsideScope).toEqual([]);
    expect(scan.figuresInPlanned).toEqual([]);
  });
});

describe("each picture is drawn from its record", () => {
  it("probabilities: one dot per group in the live curve, and the sentence says close only inside the payload's own bar", async () => {
    const page = await mountPage();
    const view = forwardRecordView(calibrationFixture());
    const card = page.querySelector('[data-evals-top-card="truth"]');
    expect(card?.querySelectorAll("[data-truth-dot]").length).toBe(view.curve?.data.length);
    expect(card?.querySelector("[data-truth-line]")).not.toBeNull();
    expect(card?.querySelector("[data-truth-reading]")?.getAttribute("data-truth-reading")).toBe(truthReading(view));
    expect(card?.querySelector('[data-truth-chip][data-truth="live"]')).not.toBeNull();
  });

  it("probabilities: close, far and plain follow the numbers, never a default", () => {
    const view = forwardRecordView(calibrationFixture());
    const withMiss = (errorPp: number, barPp: number): ForwardRecordView => ({
      ...view,
      proof: view.proof && { ...view.proof, errorPp },
      categories: view.categories && { ...view.categories, barPp },
    });
    expect(view.proof && view.categories).toBeTruthy();
    expect(truthReading(withMiss(1, 3))).toBe("close");
    expect(truthReading(withMiss(3, 3))).toBe("close");
    expect(truthReading(withMiss(3.1, 3))).toBe("far");
    expect(truthReading({ ...view, categories: null })).toBe("plain");
    expect(truthReading({ ...view, proof: null })).toBe("plain");
  });

  it("probabilities: when the graded inputs are older than the curve, the first screen says so in the accuracy page's words", async () => {
    fetchCalibrationMock.mockResolvedValue(
      calibrationFixture({
        availability: "stale",
        staged: {
          ...(calibrationFixture().staged as Record<string, unknown>),
          staged_at: "2026-10-27T03:28:13+00:00",
          frozen_over_drift: true,
        },
      })
    );
    const page = await mountPage();
    const notice = page.querySelector('[data-evals-top-card="truth"] [data-testid="evals-top-forward-staleness"]');
    const section = page.querySelector('[data-testid="evals-forward-staleness"] strong');
    expect(notice?.textContent).toBeTruthy();
    expect(notice?.textContent).toBe(section?.textContent);
  });

  it("NEGATIVE CONTROL: a fresh payload puts no notice on the first screen", async () => {
    fetchCalibrationMock.mockResolvedValue(calibrationFixture({ availability: "fresh" }));
    const page = await mountPage();
    expect(page.querySelector('[data-testid="evals-top-forward-staleness"]')).toBeNull();
  });

  it("probabilities: while the record is unavailable the picture says so and draws nothing", async () => {
    fetchCalibrationMock.mockRejectedValue(new Error("down"));
    const page = await mountPage();
    const card = page.querySelector('[data-evals-top-card="truth"]');
    expect(card?.textContent).toContain(TOP_COPY.truthUnavailable);
    expect(card?.querySelector("[data-truth-dot]")).toBeNull();
    expect(card?.querySelector("[data-evals-figure]")).toBeNull();
  });

  it("the AI reviewer: one bug per hidden mistake and one page per decoy, counts from the two records, every decoy grey while none is in", async () => {
    const page = await mountPage();
    const study = loadReviewerStudy()!;
    const results = loadReviewerResults(study)!;
    const tally = reviewerTally(results, study);
    const card = page.querySelector('[data-evals-top-card="reviewer"]');
    const bugs = card?.querySelectorAll('[data-review-marks="mistakes"] [data-review-mark]');
    const decoys = card?.querySelectorAll('[data-review-marks="harmless"] [data-review-mark]');
    expect(bugs?.length).toBe(study.cases.filter((c) => c.kind === "defect").length);
    expect(decoys?.length).toBe(study.cases.filter((c) => c.kind === "control").length);
    const caughtCases = new Set(results.results.filter((r) => r.outcome === "caught").map((r) => r.case)).size;
    expect(card?.querySelectorAll('[data-review-marks="mistakes"] [data-review-mark="right"]').length).toBe(caughtCases);
    const values = Array.from(card?.querySelectorAll('[data-review-kind="mistakes"] [data-evals-figure]') ?? []).map((f) =>
      f.getAttribute("data-value")
    );
    expect(values).toEqual(
      tally.mistakes.reviewed > 0 ? [String(tally.mistakes.right), String(tally.mistakes.reviewed)] : []
    );
    // No decoy is checked yet, so every decoy is grey and the card claims no false-alarm rate.
    if (tally.harmless.reviewed === 0) {
      expect(card?.querySelectorAll('[data-review-marks="harmless"] [data-review-mark="not_yet"]').length).toBe(decoys?.length);
      expect(card?.textContent).not.toMatch(/false alarm/i);
    }
    expect(card?.querySelector('[data-truth-chip][data-truth="last_run"]')?.getAttribute("data-as-of")).toBe(results.asOf);
  });

  it("probabilities: the worked example is the solid group nearest to a typical likely call, its two numbers read from the curve", async () => {
    const page = await mountPage();
    const view = forwardRecordView(calibrationFixture());
    const example = truthExample(truthDots(view.curve!.data, CHART_THIN_FLOOR));
    expect(example).not.toBeNull();
    const card = page.querySelector('[data-evals-top-card="truth"]');
    const figures = Array.from(card?.querySelectorAll("[data-truth-reading] [data-evals-figure]") ?? []);
    expect(figures.map((f) => f.textContent)).toEqual([wholePercent(example!.said), wholePercent(example!.happened)]);
    expect(figures.map((f) => f.getAttribute("data-value"))).toEqual([String(example!.said), String(example!.happened)]);
    expect(card?.querySelector("[data-truth-example]")).not.toBeNull();
  });

  it("the checks: one circle per check, and the count of working ones from the list", async () => {
    const page = await mountPage();
    const list = loadWatchers()!;
    const health = watcherHealth(list);
    const card = page.querySelector('[data-evals-top-card="watchers"]');
    expect(card?.querySelectorAll("[data-watcher-dot]").length).toBe(list.watchers.length);
    expect(card?.querySelectorAll('[data-watcher-dot="unknown"]').length).toBe(health.unknown);
    expect(card?.querySelectorAll('[data-watcher-dot="problems"]').length).toBe(health.foundProblems);
    expect(card?.querySelector("[data-watchers-working]")?.getAttribute("data-watchers-working")).toBe(String(health.working));
    expect(health.working + health.stopped + health.unknown).toBe(health.total);
    expect(card?.querySelector('[data-truth-chip][data-truth="reviewed"]')).not.toBeNull();
  });
});
