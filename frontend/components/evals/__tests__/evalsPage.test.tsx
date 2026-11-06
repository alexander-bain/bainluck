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
 * reviewer squares read NOT RUN with no zero-filling. Each rule has a negative
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
import HeroTiles from "@/components/evals/HeroTiles";
import TestLibrary from "@/components/evals/TestLibrary";
import TestsForTheTests from "@/components/evals/TestsForTheTests";
import { fetchCalibration } from "@/lib/api";
import { compactOutcomeCount, proofCohortFigures } from "@/lib/calibrationProofFigures";
import { ALL_COPY_BANS, SUPPLIER_PROSE_BANS, findBannedCopy } from "@/lib/copyBans";
import { EVALS_COPY_RULES } from "@/lib/evals/copyRules";
import { calibrationFixture, calibrationFixtureBuckets } from "@/lib/evals/fixtures/calibration";
import { GAPS, GAPS_REVIEWED_AT } from "@/lib/evals/gaps";
import { loadReviewerStudy } from "@/lib/evals/reviewerStudy";
import { loadRuns } from "@/lib/evals/runs";
import { familyView, loadScoreboard, type Scoreboard } from "@/lib/evals/scoreboard";
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
    expect(sections).toEqual([
      "timeline",
      "forward-record",
      "test-library",
      "tests-for-tests",
      "gaps",
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
    expect(planned?.textContent).toMatch(/PLANNED\s*waiting on the ranking harness #12100/);
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
    const onPage = ["timeline", "forward-record", "test-library", "tests-for-tests", "gaps"];
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

  it("an AI run names its model and states its replies and its usage-rated cost; a hand-run exam says so", async () => {
    const page = await mountPage();
    const exam = page.querySelector('[data-run-id="twin-judge-exam-run-1"]');
    expect(exam?.querySelector('[data-model="claude-sonnet-5-5"]')?.textContent).toBe("Claude Sonnet 5.5");
    expect(exam?.textContent).toMatch(/360\s*replies/);
    expect(exam?.textContent).toMatch(/\$6\.81\s*usage-rated, including the pilot/);
    const repeat = page.querySelector('[data-run-id="twin-judge-exam-run-2"]');
    expect(repeat?.getAttribute("data-result")).toBe("fail");
    expect(repeat?.textContent).toMatch(/\$7\.74\s*usage-rated/);
    expect(repeat?.textContent).not.toMatch(/including the pilot/);
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

  it("the hero tile carries the staleness notice when the graded inputs are older than the curve", async () => {
    // The payload shape Fable read at 10:17 PM PT: availability "stale",
    // inputs staged ten days before generated_at, frozen over drift.
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
    const notice = page.querySelector('[data-hero-tile="forward-record"] [data-testid="evals-hero-forward-staleness"]');
    const section = page.querySelector('[data-testid="evals-forward-staleness"] strong');
    expect(notice?.textContent).toBeTruthy();
    expect(notice?.textContent).toBe(section?.textContent);
  });

  it("NEGATIVE CONTROL: a fresh payload puts no notice on the tile", async () => {
    fetchCalibrationMock.mockResolvedValue(calibrationFixture({ availability: "fresh" }));
    const page = await mountPage();
    expect(page.querySelector('[data-testid="evals-hero-forward-staleness"]')).toBeNull();
  });

  it("the hero tile shows the same figure, linked to the section", async () => {
    const page = await mountPage();
    const tile = page.querySelector('[data-hero-tile="forward-record"]');
    expect(tile?.getAttribute("href")).toBe("#forward-record");
    expect(tile?.getAttribute("data-truth-scope")).toBe("live");
    expect(tile?.querySelector("a")).toBeNull(); // no link nested in the tile's link
    const figures = Array.from(tile?.querySelectorAll("[data-evals-figure]") ?? []).map((f) => f.textContent);
    expect(figures).toEqual([about?.errorPp.toFixed(1), compactOutcomeCount(about?.outcomes)]);
  });

  it("the meter reads the scorecard: 24 of 53 categories inside the 3-point bar", async () => {
    const page = await mountPage();
    const meter = page.querySelector('[data-testid="evals-forward-categories"]');
    expect(meter?.textContent).toMatch(/^24\s*of\s*53\s*categories are inside the\s*3-point bar\.$/);
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

  it("a failed read says Unavailable right now, in the section and the tile, with no number", async () => {
    fetchCalibrationMock.mockRejectedValue(new Error("network"));
    const page = await mountPage();
    const section = page.querySelector('[data-evals-section="forward-record"]');
    expect(section?.querySelector('[data-testid="evals-forward-unavailable"]')?.textContent).toBe(
      "Unavailable right now."
    );
    expect(section?.querySelector("[data-evals-figure]")).toBeNull();
    expect(section?.getAttribute("data-truth-scope")).toBeNull();
    const tile = page.querySelector('[data-hero-tile="forward-record"]');
    expect(tile?.textContent).toMatch(/Unavailable right now/);
    expect(tile?.querySelector("[data-evals-figure]")).toBeNull();
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

  it("the bug left out of the study links its issue", async () => {
    const page = await mountPage();
    const link = page.querySelector('[data-testid="evals-reviewer"] a[data-evals-ref]');
    expect(link?.getAttribute("href")).toBe(`https://github.com/alexander-bain/bainluck/issues/${study?.dropped?.issue}`);
  });

  it("the hero tile shows the same two numbers, LAST RUN, and jumps to its section", async () => {
    const page = await mountPage();
    const tile = page.querySelector('[data-hero-tile="tests-for-tests"]');
    expect(tile?.getAttribute("href")).toBe("#tests-for-tests");
    expect(tile?.getAttribute("data-truth-scope")).toBe("last_run");
    expect(tile?.querySelector("a")).toBeNull();
    const figures = Array.from(tile?.querySelectorAll("[data-evals-figure]") ?? []).map((f) => f.textContent);
    expect(figures).toEqual(["40", "40", "0", "40"]);
  });

  it("with no readable scoreboard, its tile is absent rather than empty", async () => {
    const page = await mount(<HeroTiles forward={{ status: "loading" }} board={null} />);
    expect(page.querySelector('[data-hero-tile="tests-for-tests"]')).toBeNull();
    expect(page.querySelector('[data-hero-tile="forward-record"]')).not.toBeNull();
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
