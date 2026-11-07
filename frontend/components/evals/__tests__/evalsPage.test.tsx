/**
 * @jest-environment jsdom
 */

/**
 * #12102 — /evals renders its sections and keeps the truth rules.
 *
 * S1's acceptance: tests fail on a bare number or on a figure inside a PLANNED
 * item, and the route is unlisted (`noindex`) until Alex's phone look (Decide
 * 43-A1). S3's: the forward record shows /about's figure under a LIVE label,
 * an older payload shows the staleness sentence, and a failed read shows
 * "Unavailable right now" with no number. S4's: the scoreboard's recorded time
 * and commit render, the bite meter shows both of its numbers, and all fifteen
 * reviewer squares read NOT RUN with no zero-filling. S5's: every watcher row
 * has a source link, its times are worked out in Pacific on the reader's date,
 * and each verdict is the newest on the record. S2's: the exam banner and the
 * matching topic's picture read FAIL, the gate grid's verdicts are the record's
 * (four passed, five failed), licenses are HELD / FAIL / NOT ELIGIBLE as stored,
 * and 0/0 renders as "—". Since Alex's Nov 6 goal the words are plain (no
 * "twin", no "license" on screen) and the summaries live in each topic's
 * picture rather than in hero tiles. Each rule has a negative
 * control, so a scanner that silently stopped reading would fail rather than
 * pass.
 *
 * Rendered with `createRoot` in jsdom, the way a browser runs the page: effects
 * fire, so the ages a reader's clock adds are on screen when the scan runs.
 */

import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { SWRConfig } from "swr";

// The three GA4 hooks read an AnalyticsProvider context a test render does not
// supply; stubbing them is the house idiom (see aboutProofCard…7740.test.tsx).
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
// The page's one network read. Each test decides what it answers.
jest.mock("@/lib/api", () => ({
  ...jest.requireActual("@/lib/api"),
  fetchCalibration: jest.fn(),
}));

import EvalsPage from "@/app/evals/page";
import { metadata } from "@/app/evals/layout";
import EvalsSection from "@/components/evals/EvalsSection";
import Figure from "@/components/evals/Figure";
import TestLibrary from "@/components/evals/TestLibrary";
import TestsForTheTests from "@/components/evals/TestsForTheTests";
import { BreakagesPicture } from "@/components/evals/Topics";
import Watchers from "@/components/evals/Watchers";
import { fetchCalibration } from "@/lib/api";
import { compactOutcomeCount, proofCohortFigures } from "@/lib/calibrationProofFigures";
import { ALL_COPY_BANS, SUPPLIER_PROSE_BANS, findBannedCopy } from "@/lib/copyBans";
import { EVALS_COPY_RULES } from "@/lib/evals/copyRules";
import { calibrationFixture, calibrationFixtureBuckets } from "@/lib/evals/fixtures/calibration";
import { GAPS, GAPS_REVIEWED_AT } from "@/lib/evals/gaps";
import { loadReviewerStudy } from "@/lib/evals/reviewerStudy";
import { loadRuns } from "@/lib/evals/runs";
import { familyView, loadScoreboard, type Scoreboard } from "@/lib/evals/scoreboard";
import EXAM_RAW from "@/lib/evals/data/twin-exam-2026-11-05.json";
import { RELATIONS, loadExam } from "@/lib/evals/twinExam";
import { loadWatchers, type WatcherList } from "@/lib/evals/watchers";
import { EVALS_SOURCES } from "@/lib/evals/sources";
import { pacificDayLabel, type MeasuredTruth } from "@/lib/evals/truth";
import { scanEvalsDom } from "@/lib/evals/scanEvalsDom";

const fetchCalibrationMock = fetchCalibration as jest.Mock;

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const RECORD: MeasuredTruth = {
  kind: "last_run",
  asOf: "2026-11-05",
  source: { label: "Exam receipt", href: "https://github.com/alexander-bain/bainluck/pull/11951" },
};

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

/** The page with a cache of its own, so no test reads another's payload; flushed once the read settles. */
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
  jest.useRealTimers();
});

/**
 * An instant on the Pacific calendar day `days` after the gaps were last
 * reviewed. Derived from `GAPS_REVIEWED_AT`, so re-reviewing the gaps — the
 * intended maintenance — never breaks these tests. 20:00Z is noon or 1 PM in
 * California, inside the same Pacific day whatever the season.
 */
function daysAfterReview(days: number): string {
  const [y, m, d] = GAPS_REVIEWED_AT.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d + days, 20)).toISOString();
}

const REVIEWED_LABEL = (pacificDayLabel(GAPS_REVIEWED_AT) ?? "").toUpperCase();

/** Fake only the clock; faking the queues would stall React's scheduler. */
function freezeClockAt(iso: string) {
  jest.useFakeTimers({
    now: new Date(iso),
    doNotFake: [
      "nextTick",
      "queueMicrotask",
      "setImmediate",
      "clearImmediate",
      "setTimeout",
      "clearTimeout",
      "setInterval",
      "clearInterval",
      "requestAnimationFrame",
      "cancelAnimationFrame",
      "requestIdleCallback",
      "cancelIdleCallback",
      "performance",
      "hrtime",
    ],
  });
}

describe("/evals S1 renders the shell", () => {
  it("carries the page marker a served-DOM probe reads, and the title", async () => {
    const page = await mountPage();
    expect(page.querySelector('[data-testid="evals-page"]')).not.toBeNull();
    expect(page.querySelector("h1")?.textContent).toBe("How Bain Luck tests itself");
  });

  it("shows the built sections in order, and no section without data", async () => {
    const page = await mountPage();
    const sections = Array.from(page.querySelectorAll("[data-evals-section]")).map((s) =>
      s.getAttribute("data-evals-section")
    );
    // The gaps close the story; every other section sits in the full record below them.
    expect(sections).toEqual([
      "gaps",
      "forward-record",
      "exam",
      "confusion",
      "timeline",
      "tests-for-tests",
      "test-library",
      "watchers",
      "how-to-read",
      "sources",
    ]);
  });

  it("every gap row links the issue or pull request that owns it", async () => {
    const page = await mountPage();
    const rows = Array.from(page.querySelectorAll("[data-gap-id]"));
    expect(rows.map((r) => r.getAttribute("data-gap-id"))).toEqual(GAPS.map((g) => g.id));
    for (const row of rows) {
      const link = row.querySelector("a[data-evals-ref]");
      expect(link?.getAttribute("href")).toMatch(
        /^https:\/\/github\.com\/alexander-bain\/bainluck\/(issues|pull)\/\d+$/
      );
    }
  });

  it("the gaps carry LAST REVIEWED with its date, and a planned row names what it waits on", async () => {
    freezeClockAt(daysAfterReview(0));
    const page = await mountPage();
    const chip = page.querySelector('[data-evals-section="gaps"] [data-truth-chip]');
    expect(REVIEWED_LABEL).toMatch(/^[A-Z]{3} \d{1,2}$/);
    expect(chip?.getAttribute("data-truth")).toBe("reviewed");
    expect(chip?.textContent?.startsWith(`LAST REVIEWED · ${REVIEWED_LABEL}`)).toBe(true);
    expect(chip?.querySelector("[data-age-days]")?.textContent).toBe("today");
    const planned = page.querySelector('[data-gap-id="ranking-grades"] [data-planned-item]');
    expect(planned?.textContent).toMatch(/PLANNED\s*waiting on the ranking scorer #12100/);
  });

  it("the gaps' age turns amber after two weeks without a review, and not before", async () => {
    freezeClockAt(daysAfterReview(14));
    let page = await mountPage();
    let age = page.querySelector('[data-evals-section="gaps"] [data-age-days]');
    expect(age?.textContent).toBe("14 days ago");
    expect(age?.getAttribute("data-age-amber")).toBe("false");
    await act(async () => root?.unmount());

    freezeClockAt(daysAfterReview(15));
    page = await mountPage();
    age = page.querySelector('[data-evals-section="gaps"] [data-age-days]');
    expect(age?.textContent).toBe("15 days ago");
    expect(age?.getAttribute("data-age-amber")).toBe("true");
  });

  it("lists only the sources a section on the page reads", async () => {
    const page = await mountPage();
    const listed = Array.from(page.querySelectorAll("[data-source-id]")).map((s) =>
      s.getAttribute("data-source-id")
    );
    const onPage = ["exam", "confusion", "timeline", "forward-record", "test-library", "tests-for-tests", "watchers", "gaps"];
    expect(listed).toEqual(
      EVALS_SOURCES.filter((s) => s.usedBy.some((id) => onPage.includes(id))).map((s) => s.id)
    );
    expect(listed.length).toBe(EVALS_SOURCES.length);
  });

  it("the words a render assembles pass the bans too", async () => {
    const page = await mountPage();
    const text = (page.textContent ?? "").replace(/\s+/g, " ");
    const hits = findBannedCopy(text, [...ALL_COPY_BANS, ...SUPPLIER_PROSE_BANS, ...EVALS_COPY_RULES]);
    expect(hits.map((h) => `${h.ban.id}: ${h.context}`)).toEqual([]);
  });
});

describe("the truth rules hold on the rendered page", () => {
  it("no bare number, no figure inside a PLANNED item, every figure under its own label", async () => {
    freezeClockAt(daysAfterReview(15)); // ages on screen, so the scan sees them
    const scan = scanEvalsDom(await mountPage());
    expect(scan).toEqual({ bareNumbers: [], figuresInPlanned: [], figuresOutsideScope: [] });
  });

  it("NEGATIVE CONTROL: a number typed into copy is caught", async () => {
    const scan = scanEvalsDom(
      await mount(
        <EvalsSection id="planted" title="Planted" lead="It found 24 of 25 twins.">
          <p>ok</p>
        </EvalsSection>
      )
    );
    expect(scan.bareNumbers).toHaveLength(2);
  });

  it("NEGATIVE CONTROL: the same number through Figure, under its own label, is clean", async () => {
    const scan = scanEvalsDom(
      await mount(
        <EvalsSection id="planted" title="Planted" lead="It found" truth={RECORD}>
          <Figure truth={RECORD} value="24/25">
            24 of 25
          </Figure>
        </EvalsSection>
      )
    );
    expect(scan).toEqual({ bareNumbers: [], figuresInPlanned: [], figuresOutsideScope: [] });
  });

  it("NEGATIVE CONTROL: a LAST RUN figure under a LIVE label is caught", async () => {
    const live: MeasuredTruth = { ...RECORD, kind: "live", asOf: "2026-11-06T00:19:00Z" };
    const scan = scanEvalsDom(
      await mount(
        <EvalsSection id="planted" title="Planted" lead="Mixed" truth={live}>
          <Figure truth={RECORD}>24 of 25</Figure>
        </EvalsSection>
      )
    );
    expect(scan.figuresOutsideScope).toEqual(["24 of 25"]);
  });

  it("NEGATIVE CONTROL: digits in a worked example are skipped, and the same digits outside one are caught", () => {
    const el = document.createElement("div");
    el.innerHTML =
      '<figure data-evals-example=""><figcaption>For example</figcaption><p>−150 means 60%</p></figure>' +
      "<p>−150 means 60%</p>";
    expect(scanEvalsDom(el).bareNumbers).toHaveLength(2);
    el.querySelectorAll("p")[1].remove();
    expect(scanEvalsDom(el).bareNumbers).toEqual([]);
  });

  it("NEGATIVE CONTROL: the scanner sees a figure inside a PLANNED item in markup", () => {
    // Figure itself refuses to render there (figureRules.test.tsx); this proves
    // the scanner would still see one if markup ever put it there another way.
    const el = document.createElement("div");
    el.innerHTML =
      '<section data-truth-scope="last_run"><div data-planned-item="">' +
      '<span data-evals-figure="" data-truth="last_run">3</span></div></section>';
    expect(scanEvalsDom(el).figuresInPlanned).toEqual(["3"]);
  });
});

describe("S2: the twin exam and its gates", () => {
  const exam = loadExam();
  type Cell = { k: number; n: number; result: string };
  type RawGate = { id: string; by_pass?: Record<string, Cell & Record<string, unknown>>; observed?: Cell };
  const rawGates = EXAM_RAW.gate_results as RawGate[];

  it("the banner reads FAIL, says it may not decide on its own yet, and lists what passed and what failed under it", async () => {
    const page = await mountPage();
    const banner = page.querySelector('[data-testid="evals-exam-banner"]');
    expect(banner?.getAttribute("data-result")).toBe("fail");
    expect(banner?.querySelector('[data-result="fail"]')?.textContent).toBe("FAIL");
    expect(banner?.textContent).toContain("It may not decide on its own yet, so a person still checks every match.");
    expect(banner?.querySelector("[data-gates-passed]")?.getAttribute("data-gates-passed")).toBe("4");
    expect(banner?.querySelector("[data-gates-failed]")?.getAttribute("data-gates-failed")).toBe("5");
    const count = Array.from(page.querySelectorAll('[data-testid="evals-exam-count"] [data-evals-figure]')).map((f) => f.textContent);
    expect(count).toEqual(["4", "5"]);
  });

  it("the grid's rows, cells and verdicts are the record's: a cell per pass, or one spanning cell", async () => {
    const page = await mountPage();
    const rows = Array.from(page.querySelectorAll("[data-gate]"));
    expect(rows.map((r) => r.getAttribute("data-gate"))).toEqual(rawGates.map((g) => g.id));
    expect(rows.filter((r) => r.getAttribute("data-result") === "pass")).toHaveLength(4);
    expect(rows.filter((r) => r.getAttribute("data-result") === "fail")).toHaveLength(5);
    for (const [i, row] of rows.entries()) {
      const raw = rawGates[i];
      const cells = Array.from(row.querySelectorAll("[data-gate-cell]"));
      if (raw.by_pass) {
        expect(cells.map((c) => c.getAttribute("data-gate-cell"))).toEqual(["pass", "pass", "pass"]);
        expect(cells.map((c) => c.getAttribute("data-result")?.toUpperCase())).toEqual(
          ["1", "2", "3"].map((p) => raw.by_pass?.[p].result)
        );
      } else {
        expect(cells).toHaveLength(1);
        expect(cells[0].getAttribute("colspan")).toBe("3");
        expect(cells[0].getAttribute("data-result")?.toUpperCase()).toBe(raw.observed?.result);
        expect(cells[0].querySelector("[data-evals-figure]")?.getAttribute("data-value")).toBe(
          `${raw.observed?.k}/${raw.observed?.n}`
        );
      }
    }
    const twinPass1 = Array.from(
      page.querySelectorAll('[data-gate="twin_detection"] [data-gate-cell]')[0].querySelectorAll("[data-evals-figure]")
    ).map((f) => f.getAttribute("data-value"));
    expect(twinPass1.sort()).toEqual(["0/35", "24/25"]);
  });

  it("the lead says most gates are on unseen pairs, each gate names what it counts, and spanning cells say they span (Fable on #12154)", async () => {
    const page = await mountPage();
    const section = page.querySelector('[data-evals-section="exam"]');
    const text = section?.textContent?.replace(/\s+/g, " ") ?? "";
    expect(text).toContain("it has to pass every test below. Most are scored on pairs it has never seen.");
    expect(text).not.toContain("every test below on pairs it has never seen");
    const scopeOf = (id: string) =>
      section?.querySelector(`[data-gate="${id}"] th details span`)?.textContent?.replace(/\s+/g, " ") ?? "";
    for (const g of rawGates.filter((x) => (x as { scope?: string }).scope === "test")) {
      expect(scopeOf(g.id)).toMatch(/Pairs it had never seen\.$/);
    }
    expect(scopeOf("three_pass_stability")).toMatch(/Every pair, including the ones used to tune it\.$/);
    for (const id of ["unreadable_outputs", "truncated_outputs", "nonverbatim_quotes"]) expect(scopeOf(id)).toMatch(/Every reply\.$/);
    const across = Array.from(section?.querySelectorAll('[data-gate-cell="across"]') ?? []);
    expect(across).toHaveLength(rawGates.filter((g) => !g.by_pass).length);
    for (const cell of across) expect(cell.querySelector("[data-across-passes]")?.textContent).toBe("Across all three tries");
    expect(section?.querySelectorAll('[data-gate-cell="pass"] [data-across-passes]')).toHaveLength(0);
  });

  it("licenses read HELD, FAIL and NOT ELIGIBLE as stored", async () => {
    const page = await mountPage();
    const chips = Object.fromEntries(
      Array.from(page.querySelectorAll("[data-licence]")).map((li) => [li.getAttribute("data-licence"), li.getAttribute("data-result")])
    );
    expect(chips).toEqual(exam?.licences);
    expect(page.querySelector('[data-licence="twin"] [data-result="held"]')?.textContent).toBe("HELD");
    expect(page.querySelector('[data-licence="implies"] [data-result="not_eligible"]')?.textContent).toBe("NOT ELIGIBLE");
  });

  it("the report card opens on held-out pairs, first pass, with a lock and counts only", async () => {
    const page = await mountPage();
    const card = page.querySelector('[data-evals-section="confusion"]');
    expect(card?.querySelector("[data-split]")?.getAttribute("data-split")).toBe("test");
    expect(card?.querySelectorAll("[data-lock]")).toHaveLength(RELATIONS.length);
    expect(card?.querySelector('[data-testid="evals-heldout-note"]')).not.toBeNull();
    for (const r of RELATIONS) {
      const raw = EXAM_RAW.per_pass["1"].test.per_relation[r];
      const recall = card?.querySelector(`[data-relation="${r}"] [data-metric="recall"]`);
      expect([recall?.getAttribute("data-k"), recall?.getAttribute("data-n")]).toEqual([String(raw.recall.k), String(raw.recall.n)]);
    }
    const twin = card?.querySelector('[data-relation="twin"] [data-metric="recall"]');
    expect(twin?.textContent?.replace(/\s+/g, " ")).toContain("24/25 (80.5–99.3%)");
  });

  it("0/0 renders as —, never a zero and never a bar", async () => {
    const page = await mountPage();
    const none = page.querySelector('[data-relation="uncheckable"] [data-metric="precision"]');
    expect([none?.getAttribute("data-k"), none?.getAttribute("data-n")]).toEqual(["0", "0"]);
    expect(none?.querySelector("[data-none]")?.textContent).toBe("—");
    expect(none?.querySelector("[data-evals-figure]")).toBeNull();
  });

  it("the toggles switch to development pairs and to another pass, and the lock goes with held-out", async () => {
    const page = await mountPage();
    const card = page.querySelector('[data-evals-section="confusion"]') as HTMLElement;
    await act(async () => (card.querySelector('[data-testid="evals-confusion-pass"] [data-option="3"]') as HTMLButtonElement).click());
    const p3 = card.querySelector('[data-relation="path_step"] [data-metric="precision"]');
    expect([p3?.getAttribute("data-k"), p3?.getAttribute("data-n")]).toEqual(["0", "1"]);
    await act(async () => (card.querySelector('[data-testid="evals-confusion-split"] [data-option="dev"]') as HTMLButtonElement).click());
    expect(card.querySelector("[data-split]")?.getAttribute("data-split")).toBe("dev");
    expect(card.querySelectorAll("[data-lock]")).toHaveLength(0);
    expect(card.querySelector('[data-testid="evals-heldout-note"]')).toBeNull();
    const devTwin = card.querySelector('[data-relation="twin"] [data-metric="recall"]');
    expect(devTwin?.getAttribute("data-n")).toBe(String(EXAM_RAW.per_pass["3"].dev.per_relation.twin.recall.n));
  });

  it("the matching chapter's picture reads FAIL, under LAST RUN, with the never-seen figures from the record", async () => {
    const page = await mountPage();
    const picture = page.querySelector('[data-evals-chapter="matching"] [data-chapter-picture="exam"]');
    expect(picture?.closest("details")).toBeNull();
    expect(picture?.getAttribute("data-truth-scope")).toBe("last_run");
    expect(picture?.querySelector('[data-result="fail"]')?.textContent).toBe("FAIL");
    expect(picture?.querySelector("[data-truth-chip]")?.textContent?.startsWith("LAST RUN · NOV 5")).toBe(true);
    // The picture itself is an exhibit under the same label; the numbers are the figures inside it:
    // the pairs shown in the tries line, then the green bar's line, then the red bar's.
    const figures = Array.from(picture?.querySelectorAll("[data-evals-figure]:not([data-evals-exhibit])") ?? []).map((f) => f.textContent);
    expect(figures).toEqual(["60", "24", "25", "2", "3"]);
  });
});

describe("S3: the exams on the record", () => {
  it("one row per run, oldest first, each with its verdict and its receipt", async () => {
    const page = await mountPage();
    const rows = Array.from(page.querySelectorAll("[data-run-id]"));
    const runs = loadRuns();
    expect(rows.map((r) => r.getAttribute("data-run-id"))).toEqual(runs.map((r) => r.id));
    expect(rows.map((r) => r.getAttribute("data-result"))).toEqual(runs.map((r) => r.result));
    for (const [i, row] of rows.entries()) {
      expect(row.querySelector(`[data-result="${runs[i].result}"]`)).not.toBeNull();
      expect(row.querySelector(`a[href="${runs[i].receipt.href}"]`)).not.toBeNull();
    }
  });

  it("an AI run names its model and states its replies and its cost at published rates; a hand-run exam says so", async () => {
    const page = await mountPage();
    const exam = page.querySelector('[data-run-id="twin-judge-exam-run-1"]');
    expect(exam?.querySelector('[data-model="claude-sonnet-5-5"]')?.textContent).toBe("Claude Sonnet 5.5");
    expect(exam?.textContent).toMatch(/360\s*replies/);
    expect(exam?.textContent).toMatch(/\$6\.81\s*at published rates, including the trial run/);
    const repeat = page.querySelector('[data-run-id="twin-judge-exam-run-2"]');
    expect(repeat?.getAttribute("data-result")).toBe("fail");
    expect(repeat?.textContent).toMatch(/\$7\.74\s*at published rates/);
    expect(repeat?.textContent).not.toMatch(/including the trial run/);
    expect(repeat?.textContent).toContain("not a fresh blind test");
    expect(page.querySelector('[data-run-id="calibration-exit-exam"]')?.textContent).toMatch(/By hand/);
  });

  it("every number on a row is a figure from that row's run", async () => {
    const page = await mountPage();
    for (const row of Array.from(page.querySelectorAll("[data-run-id]"))) {
      const id = row.getAttribute("data-run-id");
      const run = loadRuns().find((r) => r.id === id);
      for (const fig of Array.from(row.querySelectorAll("[data-evals-figure]"))) {
        expect(fig.getAttribute("data-truth")).toBe("last_run");
        expect(fig.getAttribute("data-as-of")).toBe(run?.date);
        expect(fig.getAttribute("data-source")).toBe(run?.receipt.href);
      }
    }
  });
});

describe("S3: the forward record", () => {
  const about = proofCohortFigures(calibrationFixtureBuckets());

  it("shows /about's figure under a LIVE label stamped with the payload's own time", async () => {
    freezeClockAt("2026-11-06T04:00:00Z"); // 8 PM PT on the payload's own day
    const page = await mountPage();
    const section = page.querySelector('[data-evals-section="forward-record"]');
    expect(section?.getAttribute("data-truth-scope")).toBe("live");
    const chip = section?.querySelector("[data-truth-chip]");
    expect(chip?.getAttribute("data-truth")).toBe("live");
    expect(chip?.textContent).toBe("LIVEas of 7:28 PM PT");
    const proof = section?.querySelector('[data-testid="evals-forward-proof"]');
    const figures = Array.from(proof?.querySelectorAll("[data-evals-figure]") ?? []).map((f) => f.textContent);
    expect(figures).toEqual([compactOutcomeCount(about?.outcomes), about?.errorPp.toFixed(1)]);
  });

  it("a LIVE stamp from another Pacific day carries its day, so yesterday's build never reads as tonight's", async () => {
    freezeClockAt("2026-11-07T20:00:00Z");
    const page = await mountPage();
    const chip = page.querySelector('[data-evals-section="forward-record"] [data-truth-chip]');
    expect(chip?.textContent).toBe("LIVEas of Nov 5, 7:28 PM PT");
  });

  // The first screen's staleness notice is held by topScreen.test.tsx: the
  // section's own words when the inputs are older, and none when fresh.
  it("the first screen's probability card shows the section's figure, under LIVE", async () => {
    const page = await mountPage();
    const card = page.querySelector('[data-evals-top-card="truth"]');
    expect(card?.getAttribute("data-truth-scope")).toBe("live");
    // Its footer holds exactly one figure, the section's own average miss; the
    // traded-outcome count stays with the section (Fable on #12225, Nov 6).
    const footer = Array.from(card?.querySelectorAll("[data-card-footer] [data-evals-figure]") ?? []).map((f) => f.textContent);
    expect(footer).toEqual([about?.errorPp.toFixed(1)]);
  });

  it("the meter reads the scorecard: 24 of 53 kinds of market within 3 points", async () => {
    const page = await mountPage();
    const meter = page.querySelector('[data-testid="evals-forward-categories"]');
    expect(meter?.textContent).toMatch(/^24\s*of\s*53\s*kinds of market come within\s*3\s*points of what happened\.$/);
  });

  it("frozen inputs show the staleness sentence with the date the data was staged", async () => {
    const page = await mountPage();
    const line = page.querySelector('[data-testid="evals-forward-staleness"]');
    expect(line?.getAttribute("data-staleness-kind")).toBe("frozen-inputs");
    expect(line?.textContent).toBe(
      "The curve is current. The data behind it is older. That data was last updated Oct 27, 1:54 PM PT."
    );
    const fresh = await (async () => {
      await act(async () => root?.unmount());
      fetchCalibrationMock.mockResolvedValue(calibrationFixture({ availability: "fresh" }));
      return mountPage();
    })();
    expect(fresh.querySelector('[data-testid="evals-forward-staleness"]')).toBeNull();
  });

  it("the curve is drawn inside a LIVE exhibit, so its axis numbers carry the record's label", async () => {
    const page = await mountPage();
    const exhibit = page.querySelector('[data-evals-section="forward-record"] [data-evals-exhibit]');
    expect(exhibit?.getAttribute("data-truth")).toBe("live");
    expect(exhibit?.querySelector("svg")).not.toBeNull();
  });

  it("a failed read says Unavailable right now, in the section and on the first screen, with no number", async () => {
    fetchCalibrationMock.mockRejectedValue(new Error("network"));
    const page = await mountPage();
    const section = page.querySelector('[data-evals-section="forward-record"]');
    expect(section?.querySelector('[data-testid="evals-forward-unavailable"]')?.textContent).toBe(
      "Unavailable right now."
    );
    expect(section?.querySelector("[data-evals-figure]")).toBeNull();
    expect(section?.getAttribute("data-truth-scope")).toBeNull();
    const card = page.querySelector('[data-evals-top-card="truth"]');
    expect(card?.textContent).toMatch(/Unavailable right now/);
    expect(card?.querySelector("[data-evals-figure]")).toBeNull();
    expect(scanEvalsDom(page).bareNumbers).toEqual([]);
  });

  it("a payload that cannot say when it is true is unavailable, not shown undated", async () => {
    fetchCalibrationMock.mockResolvedValue(calibrationFixture({ generated_at: undefined }));
    const page = await mountPage();
    expect(page.querySelector('[data-testid="evals-forward-unavailable"]')).not.toBeNull();
  });
});

describe("S4: the test library", () => {
  const board = loadScoreboard() as Scoreboard;

  it("prints the record's own time and commit (recorded_at_pt, recorded_source_sha) under LAST RUN", async () => {
    const page = await mountPage();
    const section = page.querySelector('[data-evals-section="test-library"]');
    expect(section?.getAttribute("data-truth-scope")).toBe("last_run");
    expect(section?.querySelector("[data-truth-chip]")?.textContent?.startsWith("LAST RUN · NOV 3")).toBe(true);
    const recorded = section?.querySelector('[data-testid="evals-library-recorded"]');
    const time = recorded?.querySelector("time");
    expect(time?.getAttribute("dateTime")).toBe("2026-11-03");
    expect(time?.textContent).toBe("Nov 3, 8:48 PM PT");
    const sha = recorded?.querySelector("a[data-recorded-sha]");
    expect(sha?.getAttribute("data-recorded-sha")).toBe(board.recordedSourceSha);
    expect(sha?.textContent).toBe(board.recordedSourceSha.slice(0, 10));
    expect(sha?.getAttribute("href")).toBe(
      `https://github.com/alexander-bain/bainluck/commit/${board.recordedSourceSha}`
    );
  });

  it("one row per family, in the record's order and in plain words, each with the family's own case count", async () => {
    const page = await mountPage();
    const rows = Array.from(page.querySelectorAll("[data-family]"));
    expect(rows.map((r) => r.getAttribute("data-family"))).toEqual(board.families.map((f) => f.canonical));
    for (const [i, row] of rows.entries()) {
      const view = familyView(board.families[i]);
      const summary = row.querySelector("summary");
      expect(summary?.textContent).toContain(view.name);
      expect(summary?.textContent).not.toContain(view.canonical);
      expect(summary?.querySelector("[data-evals-figure]")?.getAttribute("data-value")).toBe(String(view.cases));
      expect(summary?.textContent).toContain(view.casesAtLeast ? "or more cases" : " cases");
    }
  });

  it("a family's recorded run counts its unrecorded checks and never reads as a PASS", async () => {
    const page = await mountPage();
    const cache = page.querySelector('[data-family="cache_failure_resilience"] summary');
    expect(cache?.textContent?.replace(/\s+/g, " ")).toMatch(
      /Recorded run: 54 passed, 0 failed\. 15 of its 21 checks have no recorded run\./
    );
    expect(page.querySelector('[data-evals-section="test-library"] [data-result="pass"]')).toBeNull();
  });

  it("one unrecorded check reads 'has', never 'have'", async () => {
    const page = await mountPage();
    const admin = page.querySelector('[data-family="admin_surface_truth_contract"] summary');
    expect(admin?.textContent?.replace(/\s+/g, " ")).toMatch(/\. 1 of its 10 checks has no recorded run\./);
    const library = page.querySelector('[data-evals-section="test-library"]')?.textContent?.replace(/\s+/g, " ");
    expect(library).toMatch(/1 of its 2 checks has no recorded run/);
    expect(library).not.toMatch(/\b1 of its \d+ checks have\b/);
  });

  it("NEGATIVE CONTROL: a family whose recorded run failed shows FAIL beside its name", async () => {
    const failing: Scoreboard = JSON.parse(JSON.stringify(board));
    const first = failing.families[0].members.find((m) => m.last_result);
    if (first?.last_result) first.last_result.failed = 1;
    const page = await mount(<TestLibrary board={failing} />);
    const row = page.querySelector(`[data-family="${failing.families[0].canonical}"]`);
    expect(row?.querySelector('summary [data-result="fail"]')?.textContent).toBe("FAIL");
    expect(page.querySelectorAll('[data-result="fail"]')).toHaveLength(1);
  });

  it("the golden set prints its count, its total and its floor from the record", async () => {
    const page = await mountPage();
    const golden = page.querySelector('[data-testid="evals-golden"]');
    const values = Array.from(golden?.querySelectorAll("[data-evals-figure]") ?? []).map((f) =>
      f.getAttribute("data-value")
    );
    expect(values).toEqual([board.golden.passing, board.golden.total, board.golden.floor].map(String));
    for (const fig of Array.from(golden?.querySelectorAll("[data-evals-figure]") ?? [])) {
      expect(fig.getAttribute("data-source")).toContain(`/blob/${board.recordedSourceSha.slice(0, 10)}/`);
    }
  });
});

describe("S4: the tests for the tests", () => {
  const board = loadScoreboard() as Scoreboard;
  const study = loadReviewerStudy();

  it("the bite meter shows both numbers: 40 of 40 caught and 0 of 40 on the site's own code", async () => {
    const page = await mountPage();
    const bite = page.querySelector('[data-testid="evals-bite"]');
    const values = (part: string) =>
      Array.from(bite?.querySelectorAll(`[data-bite="${part}"] [data-evals-figure]`) ?? []).map((f) => f.textContent);
    expect(values("caught")).toEqual(["40", "40"]);
    expect(values("real-code")).toEqual(["0", "40"]);
    expect(bite?.textContent).toContain("None of these cases runs the site's own code");
    expect(bite?.querySelector("[data-truth-chip]")?.textContent?.startsWith("LAST RUN · NOV 3")).toBe(true);
  });

  it("NEGATIVE CONTROL: once a case runs the site's own code, the page stops saying none does", async () => {
    const some: Scoreboard = { ...board, bite: { ...board.bite, realCode: 3 } };
    const page = await mount(<TestsForTheTests board={some} study={null} />);
    expect(page.textContent).not.toContain("None of these cases");
    expect(page.querySelector('[data-testid="evals-reviewer"]')).toBeNull();
  });

  it("all fifteen reviewer squares read NOT RUN, with no zero-filling", async () => {
    const page = await mountPage();
    const tiles = Array.from(page.querySelectorAll("[data-reviewer-result]"));
    expect(tiles).toHaveLength(study?.cases.length ?? -1);
    expect(tiles).toHaveLength(15);
    for (const tile of tiles) {
      expect(tile.getAttribute("data-reviewer-result")).toBe("not_run");
      expect(tile.querySelector('[data-result="not_run"]')?.textContent).toBe("NOT RUN");
      expect(tile.textContent).not.toMatch(/\d/);
    }
    expect(page.querySelectorAll('[data-reviewer-grid="defect"] [data-reviewer-case]')).toHaveLength(10);
    expect(page.querySelectorAll('[data-reviewer-grid="control"] [data-reviewer-case]')).toHaveLength(5);
  });

  it("tapping a square shows what changed, what our tests did, and the reviewer's result", async () => {
    const page = await mountPage();
    const detail = () => page.querySelector('[data-testid="evals-reviewer-detail"]');
    expect(detail()?.getAttribute("data-detail-case")).toBe(study?.cases[0].id);
    const control = study?.cases.find((c) => c.kind === "control");
    const tile = page.querySelector(`[data-reviewer-case="${control?.id}"]`) as HTMLButtonElement;
    await act(async () => tile.click());
    expect(detail()?.getAttribute("data-detail-case")).toBe(control?.id);
    expect(detail()?.textContent).toContain(control?.text);
    expect(detail()?.textContent).toMatch(/Our tests: passed it/);
    expect(detail()?.querySelector('[data-result="not_run"]')?.textContent).toBe("NOT RUN");
    expect(tile.getAttribute("aria-pressed")).toBe("true");
    expect(page.querySelector(`[data-reviewer-case="${study?.cases[0].id}"]`)?.getAttribute("aria-pressed")).toBe(
      "false"
    );
  });

  it("the squares say the time they are as of, and point at the full study that started after them (Fable on #12130)", async () => {
    const page = await mountPage();
    const grid = page.querySelector('[data-testid="evals-reviewer"]');
    const chip = grid?.querySelector("[data-truth-chip]");
    expect(chip?.textContent).toMatch(/^LAST RUN · NOV 5as of 4:36 PM PT/);
    expect(grid?.textContent).toContain(
      "When these squares were recorded, the AI reviewer had not reviewed any of them, so each reads NOT RUN."
    );
    expect(grid?.textContent).not.toMatch(/has not reviewed/);
    const full = page.querySelector('[data-testid="evals-reviewer-full-study"]');
    expect(full?.textContent?.replace(/\s+/g, " ")).toBe(
      "The reviews started after these squares were recorded. The full study's first result came in at Nov 5, 11:48 PM PT, and each new result follows it on the same thread: results so far."
    );
    expect(full?.querySelector("time")?.getAttribute("dateTime")).toBe(study?.fullStudy?.firstResultAt);
    expect(full?.querySelector("a")?.getAttribute("href")).toBe(
      "https://github.com/alexander-bain/bainluck/pull/11951#issuecomment-6679966474"
    );
  });

  it("NEGATIVE CONTROL: a study with no full-study result shows no pointer to one", async () => {
    const page = await mount(<TestsForTheTests board={board} study={{ ...study!, fullStudy: null }} />);
    expect(page.querySelector('[data-testid="evals-reviewer-full-study"]')).toBeNull();
  });

  it("the bug left out of the study links its issue", async () => {
    const page = await mountPage();
    const link = page.querySelector('[data-testid="evals-reviewer"] a[data-evals-ref]');
    expect(link?.getAttribute("href")).toBe(`https://github.com/alexander-bain/bainluck/issues/${study?.dropped?.issue}`);
  });

  it("the code chapter's picture shows the meter's caught count, LAST RUN, and its limit in words while none runs the site's own code", async () => {
    const page = await mountPage();
    const picture = page.querySelector('[data-evals-chapter="code"] [data-chapter-picture="breakages"]');
    expect(picture?.closest("details")).toBeNull();
    expect(picture?.getAttribute("data-truth-scope")).toBe("last_run");
    // The picture itself is an exhibit under the same label; the numbers are the figures inside it.
    const figures = Array.from(picture?.querySelectorAll("[data-evals-figure]:not([data-evals-exhibit])") ?? []).map((f) => f.textContent);
    expect(figures).toEqual(["40", "40"]);
    expect(picture?.querySelectorAll('[data-breakage="caught"]')).toHaveLength(board.bite.caught);
    expect(picture?.querySelector("[data-breakages-limit]")?.textContent).toContain("rather than the live code");
  });

  it("NEGATIVE CONTROL: once a case runs the site's own code, the picture counts them instead of saying none does", async () => {
    const some: Scoreboard = { ...board, bite: { ...board.bite, realCode: 3 } };
    const page = await mount(<BreakagesPicture board={some} />);
    const limit = page.querySelector("[data-breakages-limit]");
    expect(limit?.textContent).not.toContain("rather than the live code");
    expect(Array.from(limit?.querySelectorAll("[data-evals-figure]") ?? []).map((f) => f.textContent)).toEqual(["3", "40"]);
  });
});

describe("S5: checks that run on their own", () => {
  const list = loadWatchers();
  /** Noon Pacific on a November day (standard time) and on a July day (daylight time). */
  const NOVEMBER = "2026-11-05T20:00:00Z";
  const JULY = "2026-07-15T19:00:00Z";
  const row = (page: HTMLElement, id: string) => page.querySelector(`[data-watcher="${id}"]`);

  it("lists every watcher under LAST REVIEWED, through the day and every night", async () => {
    freezeClockAt(NOVEMBER);
    const page = await mountPage();
    const section = page.querySelector('[data-evals-section="watchers"]');
    expect(section?.getAttribute("data-truth-scope")).toBe("reviewed");
    expect(section?.querySelector("[data-truth-chip]")?.textContent?.startsWith("LAST REVIEWED · NOV 6")).toBe(true);
    const ids = Array.from(section?.querySelectorAll("[data-watcher]") ?? []).map((r) => r.getAttribute("data-watcher"));
    expect(ids).toEqual(list?.watchers.map((w) => w.id));
    expect(section?.querySelectorAll('[data-watcher-group="day"] [data-watcher]')).toHaveLength(2);
    expect(section?.querySelectorAll('[data-watcher-group="night"] [data-watcher]')).toHaveLength(10);
  });

  it("every row links where its check lives", async () => {
    const page = await mountPage();
    const rows = Array.from(page.querySelectorAll("[data-watcher]"));
    expect(rows.length).toBe(list?.watchers.length);
    for (const r of rows) {
      expect(r.querySelector("a[data-watcher-source]")?.getAttribute("href")).toMatch(
        /^https:\/\/github\.com\/alexander-bain\/bainluck\/blob\/[0-9a-f]{10}\/backend\/app\/tasks\//
      );
    }
  });

  it("works out each run's Pacific time on the reader's date: 11:10 PM in November, 12:10 AM in July", async () => {
    freezeClockAt(NOVEMBER);
    let page = await mountPage();
    expect(page.querySelector('[data-schedule="flow-sentinel-daily"]')?.textContent).toBe("Every day at 11:10 PM PT");
    expect(page.querySelector('[data-schedule="matching-reconciliation"]')?.textContent).toBe("Every 15 minutes");
    expect(page.querySelector('[data-schedule="data-quality-watchdog"]')?.textContent).toBe("Every 2 hours");
    expect(page.querySelector('[data-day-strip="flow-sentinel-daily"] [data-run-minute]')?.getAttribute("data-run-minute")).toBe(
      String(23 * 60 + 10)
    );
    await act(async () => root?.unmount());

    freezeClockAt(JULY);
    page = await mountPage();
    expect(page.querySelector('[data-schedule="flow-sentinel-daily"]')?.textContent).toBe("Every day at 12:10 AM PT");
    expect(page.querySelector('[data-day-strip="flow-sentinel-daily"] [data-run-minute]')?.getAttribute("data-run-minute")).toBe(
      "10"
    );
  });

  it("draws a dot for every run in the day: twelve, ninety-six, or one", async () => {
    const page = await mountPage();
    const runs = (id: string) => page.querySelector(`[data-day-strip="${id}"]`)?.getAttribute("data-runs");
    expect(runs("data-quality-watchdog")).toBe("12");
    expect(runs("matching-reconciliation")).toBe("96");
    expect(runs("grid-sentinel-daily")).toBe("1");
  });

  it("shows each verdict with its own date, its chip, and the issues its run posted to", async () => {
    freezeClockAt(NOVEMBER);
    const page = await mountPage();
    const refs = (r: Element | null) => Array.from(r?.querySelectorAll("a[data-evals-ref]") ?? []).map((a) => a.textContent);
    const withVerdict = (list?.watchers ?? []).filter((w) => w.verdict);
    expect(withVerdict.length).toBeGreaterThan(0);
    for (const w of withVerdict) {
      const v = w.verdict!;
      const r = row(page, w.id);
      expect(r?.getAttribute("data-verdict-state")).toBe(v.state);
      expect(r?.querySelector("[data-verdict-chip]")?.textContent).toBe(
        {
          red_reporting: "Found problems, reported",
          red_stopped: "Found problems, not reported",
          closed_fixed: "Found its problem fixed",
        }[v.state]
      );
      const day = (pacificDayLabel(v.runAt) as string).toUpperCase();
      expect(r?.querySelector("[data-truth-chip]")?.textContent?.startsWith(`LAST RUN · ${day}`)).toBe(true);
      const context = [v.earlier, v.fix].filter((n): n is number => n !== null);
      expect(refs(r)).toEqual([...v.issues, ...v.closed, ...context].map((n) => `#${n}`));
      expect(r?.querySelector("a[data-verdict-receipt]")?.getAttribute("href")).toBe(v.receipt.href);
    }
  });

  it("a run that closed issues as fixed says so, and a run that only closed issues is never green", async () => {
    freezeClockAt(NOVEMBER);
    const page = await mountPage();
    const closing = (list?.watchers ?? []).filter((w) => (w.verdict?.closed.length ?? 0) > 0);
    expect(closing.length).toBeGreaterThan(0);
    for (const w of closing) {
      const v = w.verdict!;
      const r = row(page, w.id);
      const text = r?.textContent?.replace(/\s+/g, " ") ?? "";
      const issues = v.closed.map((n) => `#${n}`).join(" ");
      if (v.state === "closed_fixed") {
        const words = v.closed.length === 1 ? "re-checked the problem it had reported, found it fixed, and closed it:" : "re-checked the problems it had reported, found them fixed, and closed them:";
        expect(text).toContain(`${words} ${issues}.`);
        expect(r?.querySelector("[data-verdict-chip]")?.className).not.toMatch(/green/);
      } else {
        expect(text).toContain(`It also found ${issues} fixed, and closed ${v.closed.length === 1 ? "it" : "them"}.`);
      }
    }
    expect(page.querySelector('[data-evals-section="watchers"] [data-result="pass"]')).toBeNull();
  });

  it("NEGATIVE CONTROL: a run that could not post reads found problems, not reported", async () => {
    const stoppedList: WatcherList = JSON.parse(JSON.stringify(list));
    const first = stoppedList.watchers.find((w) => w.verdict)!;
    first.verdict = { ...first.verdict!, state: "red_stopped", issues: [11958], closed: [], earlier: null, fix: null };
    const page = await mount(<Watchers list={stoppedList} />);
    const r = page.querySelector(`[data-watcher="${first.id}"]`);
    expect(r?.getAttribute("data-verdict-state")).toBe("red_stopped");
    expect(r?.querySelector("[data-verdict-chip]")?.textContent).toBe("Found problems, not reported");
    expect(r?.textContent?.replace(/\s+/g, " ")).toContain(
      "found problems but could not report them. The broken reporting is tracked in #11958."
    );
    expect(page.querySelectorAll('[data-verdict-state="red_stopped"]')).toHaveLength(1);
  });

  it("a watcher with no public record of its last result says UNKNOWN, never green", async () => {
    const page = await mountPage();
    const unknown = Array.from(page.querySelectorAll('[data-verdict-state="unknown"]'));
    expect(unknown).toHaveLength((list?.watchers ?? []).filter((w) => !w.verdict).length);
    for (const r of unknown) {
      expect(r.querySelector('[data-result="unknown"]')?.textContent).toBe("UNKNOWN");
      expect(r.querySelector("[data-verdict-chip]")).toBeNull();
    }
    expect(page.querySelector('[data-evals-section="watchers"] [data-result="pass"]')).toBeNull();
  });

  it("links the open alerts without counting them (Decide 43-F1)", async () => {
    const page = await mountPage();
    const link = page.querySelector("a[data-alerts-link]");
    expect(link?.getAttribute("href")).toBe(
      "https://github.com/alexander-bain/bainluck/issues?q=is%3Aopen+label%3Aalert-intake"
    );
    expect(link?.textContent).not.toMatch(/\d/);
  });
});

describe("/evals is unlisted until Alex's phone look (Decide 43-A1)", () => {
  it("noindex, nofollow", () => {
    expect(metadata.robots).toEqual({ index: false, follow: false });
  });

  it("names itself as canonical and og:url, with the default share card", () => {
    expect(metadata.alternates?.canonical).toBe("/evals");
    const og = metadata.openGraph as { url?: string; images?: { url: string }[] };
    expect(og.url).toBe("/evals");
    expect(og.images?.[0]?.url).toBe("/opengraph-image");
  });
});
