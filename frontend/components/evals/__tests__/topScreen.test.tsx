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
import { truthReading } from "@/lib/evals/topScreen";
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

  it("everything the page carried before sits under the fold, nothing dropped", async () => {
    const page = await mountPage();
    const fold = page.querySelector("details[data-evals-fold]");
    expect(fold).not.toBeNull();
    expect(fold?.querySelector("summary")?.textContent).toContain(TOP_COPY.fold);
    for (const id of ["exam", "confusion", "timeline", "forward-record", "test-library", "tests-for-tests", "watchers", "gaps", "how-to-read", "sources"]) {
      expect(fold?.querySelector(`#${id}`)).not.toBeNull();
    }
    expect(fold?.querySelector('[data-testid="evals-hero-tiles"]')).not.toBeNull();
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

  it("probabilities: while the record is unavailable the picture says so and draws nothing", async () => {
    fetchCalibrationMock.mockRejectedValue(new Error("down"));
    const page = await mountPage();
    const card = page.querySelector('[data-evals-top-card="truth"]');
    expect(card?.textContent).toContain(TOP_COPY.truthUnavailable);
    expect(card?.querySelector("[data-truth-dot]")).toBeNull();
    expect(card?.querySelector("[data-evals-figure]")).toBeNull();
  });

  it("the AI reviewer: one block per planned review, the counts from the two records, UNKNOWN while no harmless change is in", async () => {
    const page = await mountPage();
    const study = loadReviewerStudy()!;
    const results = loadReviewerResults(study)!;
    const tally = reviewerTally(results, study);
    const card = page.querySelector('[data-evals-top-card="reviewer"]');
    const mistakes = card?.querySelectorAll('[data-review-blocks="mistakes"] [data-review-block]');
    const harmless = card?.querySelectorAll('[data-review-blocks="harmless"] [data-review-block]');
    expect(mistakes?.length).toBe(tally.mistakes.planned);
    expect(harmless?.length).toBe(tally.harmless.planned);
    const values = Array.from(card?.querySelectorAll('[data-review-kind="mistakes"] [data-evals-figure]') ?? []).map((f) =>
      f.getAttribute("data-value")
    );
    expect(values).toEqual(
      tally.mistakes.reviewed > 0 ? [String(tally.mistakes.right), String(tally.mistakes.reviewed)] : []
    );
    if (tally.harmless.reviewed === 0) {
      expect(card?.querySelector('[data-review-kind="harmless"] [data-result="unknown"]')).not.toBeNull();
    }
    expect(card?.querySelector('[data-truth-chip][data-truth="last_run"]')?.getAttribute("data-as-of")).toBe(results.asOf);
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
