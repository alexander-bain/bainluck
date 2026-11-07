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
 * Below the top screen, the whole story in plain words (Alex, 2:04 PM): one
 * chapter per step of the stack, each with at most a picture, then the open
 * gaps, then one "full record" fold holding every section the page carried
 * before. The jargon check covers the chapters because it reads the whole page
 * outside every fold, and a second check keeps our internal names (twin,
 * license, exit exam and the like) off the page entirely, the plain-words
 * glossary of them excepted.
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
import TopScreen from "@/components/evals/TopScreen";
import { fetchCalibration } from "@/lib/api";
import { STORY_COPY, TERMS, TOPIC_COPY, TOP_COPY, WATCHERS_COPY } from "@/lib/evals/copy";
import EXAM_RAW from "@/lib/evals/data/twin-exam-2026-11-05.json";
import { EXAMPLE_AMERICAN_ODDS, EXAMPLE_CONTRACT_CENTS, americanOddsText, americanToPercent } from "@/lib/evals/example";
import { calibrationFixture } from "@/lib/evals/fixtures/calibration";
import { forwardRecordView, type ForwardRecordView } from "@/lib/evals/forwardRecord";
import { loadReviewerResults, reviewerTally } from "@/lib/evals/reviewerResults";
import { loadReviewerStudy } from "@/lib/evals/reviewerStudy";
import { scanEvalsDom } from "@/lib/evals/scanEvalsDom";
import { truthDots, truthExample, truthReading, wholePercent } from "@/lib/evals/topScreen";
import { PASSES } from "@/lib/evals/twinExam";
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

  it("everything the page carried before sits under the one full-record fold, nothing dropped", async () => {
    const page = await mountPage();
    const record = page.querySelector('[data-evals-record] > details[data-evals-fold="record"]');
    expect(record?.querySelector("summary")?.textContent).toContain(STORY_COPY.recordSummary);
    for (const id of ["forward-record", "exam", "confusion", "timeline", "tests-for-tests", "test-library", "watchers", "how-to-read", "sources"]) {
      expect(record?.querySelector(`#${id}`)).not.toBeNull();
    }
    // The planted-change meter sits with the library whose cases it grades.
    expect(page.querySelector('[data-testid="evals-bite"]')?.closest("#test-library")).not.toBeNull();
    // The gaps stay open: each row is plain words and its issue.
    expect(page.querySelector("#gaps")?.closest("details")).toBeNull();
    // And there is no other top-level fold: the story itself hides nothing.
    const topLevel = Array.from(page.querySelectorAll("details[data-evals-fold]"));
    expect(topLevel.map((d) => d.getAttribute("data-evals-fold"))).toEqual(["record"]);
  });
});

/**
 * Alex, Nov 6, 2:04 PM: "avoid meaningless jargon like twins, license,
 * 'Calibration exit exam'". Our records' short names stay off the whole page,
 * folds included. The one exception is the plain-words list that defines them
 * for a reader who follows a link into those records.
 */
const INTERNAL_NAMES = /\b(twins?|licen[cs]es?|licensed|exit exams?|golden sets?|sentinels?|AI judge|running red|bite audit|usage[- ]rated)\b/gi;

function everywhereButTheGlossary(root: Element): string {
  const clone = root.cloneNode(true) as Element;
  clone.querySelectorAll("[data-evals-glossary]").forEach((g) => g.remove());
  const labels = Array.from(clone.querySelectorAll("[aria-label]")).map((el) => el.getAttribute("aria-label") ?? "");
  return [clone.textContent ?? "", ...labels].join(" ").replace(/\s+/g, " ");
}

describe("no internal names anywhere on the page (Alex, Nov 6, 2:04 PM)", () => {
  it("none in the story, the gaps or the full record; only the plain-words list names them", async () => {
    const page = await mountPage();
    expect((everywhereButTheGlossary(page).match(INTERNAL_NAMES) ?? []).map((w) => w.toLowerCase())).toEqual([]);
    // The list itself is on the page, so a reader can still look one up.
    expect(page.querySelector("[data-evals-glossary]")?.textContent).toMatch(/Twin/);
  });

  it("the check can fail: a name outside the list is found, the same name inside it is not", async () => {
    const page = await mount(
      <div>
        <details>
          <summary>x</summary>
          <p>The twin exam and the calibration exit exam.</p>
        </details>
        <div data-evals-glossary="">
          <p>Twin: two listings of one market.</p>
        </div>
      </div>
    );
    expect((everywhereButTheGlossary(page).match(INTERNAL_NAMES) ?? []).map((w) => w.toLowerCase())).toEqual(["twin", "exit exam"]);
  });
});

describe("the story below the top screen (Alex, Nov 6, 2:04 PM)", () => {
  it("tells the whole stack in order: where the numbers come from, matching, combining, coming true, the code, the live site, then the gaps and the full record", async () => {
    const page = await mountPage();
    const order = Array.from(page.querySelectorAll("[data-evals-chapter], #gaps, [data-evals-record]")).map(
      (el) => el.getAttribute("data-evals-chapter") ?? (el.id || "record")
    );
    expect(order).toEqual(["sources", "matching", "combining", "coming-true", "code", "live-checks", "gaps", "record"]);
  });

  it("each chapter is a title and plain sentences, and every picture in it stands outside any fold under its own label", async () => {
    const page = await mountPage();
    for (const chapter of Array.from(page.querySelectorAll("[data-evals-chapter]"))) {
      expect(chapter.querySelector(":scope > h2")?.textContent).toBeTruthy();
      const words = Array.from(chapter.querySelectorAll(":scope > p")).map((p) => p.textContent ?? "").join(" ");
      expect(words.length).toBeGreaterThan(80);
      expect(chapter.querySelector("details")).toBeNull();
      for (const picture of Array.from(chapter.querySelectorAll("[data-chapter-picture]"))) {
        if (picture.getAttribute("data-chapter-picture") === "example") continue;
        expect(picture.getAttribute("data-truth-scope")).toBe(picture.querySelector("[data-truth-chip]")?.getAttribute("data-truth"));
      }
    }
    const pictures = Array.from(page.querySelectorAll("[data-chapter-picture]")).map((p) => [
      p.closest("[data-evals-chapter]")?.getAttribute("data-evals-chapter"),
      p.getAttribute("data-chapter-picture"),
    ]);
    expect(pictures).toEqual([
      ["sources", "example"],
      ["matching", "exam"],
      ["coming-true", "kinds"],
      ["code", "breakages"],
      ["code", "reviewer"],
      ["live-checks", "checks"],
    ]);
  });

  it("the worked example says For example, holds no measured figure, and shows the one chance both sources mean", async () => {
    const page = await mountPage();
    const example = page.querySelector("[data-evals-example]");
    expect(example?.querySelector("figcaption")?.textContent).toBe(STORY_COPY.exampleLabel);
    expect(example?.querySelector("[data-evals-figure]")).toBeNull();
    expect(example?.textContent).toContain(americanOddsText(EXAMPLE_AMERICAN_ODDS));
    expect(example?.textContent).toContain(`${EXAMPLE_CONTRACT_CENTS}¢`);
    expect(example?.textContent).toContain(`${americanToPercent(EXAMPLE_AMERICAN_ODDS)}%`);
  });

  it("the matching picture names its three tries, reads 2 or 3 off the record, and says the rule its red bar counts", async () => {
    const page = await mountPage();
    const picture = page.querySelector('[data-evals-chapter="matching"] [data-chapter-picture="exam"]');
    const text = (el: Element | null | undefined) => el?.textContent?.replace(/\s+/g, " ").trim() ?? "";
    const M = TOPIC_COPY.matching;
    const tries = PASSES.map((p) => EXAM_RAW.per_pass[p].test);
    const found = tries.map((t) => t.per_relation.twin.recall.k);
    const wrong = tries.map((t) => t.wrong_merges);
    // The copy spells the number of tries in words.
    expect(PASSES).toHaveLength(3);
    expect(M.triesAfter).toContain("three separate tries");
    expect(text(picture?.querySelector("[data-exam-tries]"))).toBe(`${M.triesBefore} ${tries[0].expected} ${M.triesAfter}`);
    // The tries agree on the green bar and differ on the red one: one number, then "fewest or most".
    expect(new Set(found).size).toBe(1);
    expect(text(picture)).toContain(`${M.foundBefore} ${found[0]} ${M.foundOf} ${tries[0].per_relation.twin.recall.n} ${M.foundAfter}`);
    expect(text(picture)).toContain(`${M.wrongBefore} ${Math.min(...wrong)} ${M.or} ${Math.max(...wrong)} ${M.wrongAfter}`);
    expect(text(picture)).toContain("joined 2 or 3 pairs it should have kept apart");
    expect(text(picture?.querySelector("[data-exam-why]"))).toBe(M.why);
  });

  it("a chapter whose record cannot be read keeps its words and drops only its picture", async () => {
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
    const chapters = Array.from(el.querySelectorAll("[data-evals-chapter]")).map((c) => c.getAttribute("data-evals-chapter"));
    expect(chapters).toEqual(["sources", "matching", "combining", "coming-true", "code", "live-checks"]);
    const code = el.querySelector('[data-evals-chapter="code"]');
    expect(code?.textContent).toContain(STORY_COPY.code.paragraphs[0]);
    expect(code?.querySelector('[data-chapter-picture="breakages"]')).toBeNull();
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

  it("the reviewer sentence counts tries and the picture counts cases: three caught tries on one mistake read 3 of 3 above one green bug (Fable on #12217)", async () => {
    const study = loadReviewerStudy()!;
    const base = loadReviewerResults(study)!;
    const results = {
      ...base,
      results: [1, 2, 3].map((pass) => ({ case: "r01", pass, outcome: "caught" as const, at: base.asOf, receipt: base.receipt })),
    };
    const page = await mount(<TopScreen forward={{ status: "loading" }} study={study} results={results} watchers={null} />);
    const card = page.querySelector('[data-evals-top-card="reviewer"]');
    const sentence = card?.querySelector('[data-review-kind="mistakes"]');
    expect(Array.from(sentence?.querySelectorAll("[data-evals-figure]") ?? []).map((f) => f.getAttribute("data-value"))).toEqual(["3", "3"]);
    expect(sentence?.textContent).toContain(TOP_COPY.reviewerCaughtAfter);
    expect(TOP_COPY.reviewerCaughtAfter).toMatch(/\btries\b/);
    expect(card?.querySelectorAll('[data-review-marks="mistakes"] [data-review-mark="right"]')).toHaveLength(1);
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

  it("the watchers card says what a watcher is: a program that watches the site (Alex's son, Nov 6)", async () => {
    // Alex's son read the page and did not know what an "automatic check" was.
    // The card names the thing in plain words and never uses the bare term.
    const page = await mountPage();
    const text = page.querySelector('[data-evals-top-card="watchers"]')?.textContent?.replace(/\s+/g, " ") ?? "";
    expect(text).toContain(TOP_COPY.watchersSentenceStart);
    expect(TOP_COPY.watchersSentenceStart).toMatch(/\ba program that watches\b/);
    expect(text).not.toMatch(/automatic checks?/i);
  });

  it("the whole page, record and glossary included, calls them watchers and never automatic checks", async () => {
    const page = await mountPage();
    const text = page.textContent?.replace(/\s+/g, " ") ?? "";
    expect(text).not.toMatch(/automatic checks?/i);
    expect(page.querySelector("#watchers")?.textContent).toContain(WATCHERS_COPY.title);
    expect(WATCHERS_COPY.title).toMatch(/\bwatchers\b/);
    expect(TERMS.find((t) => t.term === "Sentinel")?.meaning).toMatch(/\bsite watcher\b/);
  });
});
