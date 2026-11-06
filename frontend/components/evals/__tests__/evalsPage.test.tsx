/**
 * @jest-environment jsdom
 */

/**
 * #12102 S1 — /evals renders its shell and keeps the truth rules.
 *
 * The plan's acceptance for S1: tests fail on a bare number or on a figure
 * inside a PLANNED item, and the route is unlisted (`noindex`) until Alex's
 * phone look (Decide 43-A1). Each rule has a negative control here, so a
 * scanner that silently stopped reading would fail rather than pass.
 *
 * Rendered with `createRoot` in jsdom, the way a browser runs the page: effects
 * fire, so the ages a reader's clock adds are on screen when the scan runs.
 */

import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";

// The three GA4 hooks read an AnalyticsProvider context a test render does not
// supply; stubbing them is the house idiom (see aboutProofCard…7740.test.tsx).
jest.mock("@/hooks", () => ({
  usePageTracking: () => {},
  useScrollDepth: () => {},
  useEngagementTime: () => {},
}));

import EvalsPage from "@/app/evals/page";
import { metadata } from "@/app/evals/layout";
import EvalsSection from "@/components/evals/EvalsSection";
import Figure from "@/components/evals/Figure";
import { ALL_COPY_BANS, SUPPLIER_PROSE_BANS, findBannedCopy } from "@/lib/copyBans";
import { EVALS_COPY_RULES } from "@/lib/evals/copyRules";
import { GAPS, GAPS_REVIEWED_AT } from "@/lib/evals/gaps";
import { EVALS_SOURCES } from "@/lib/evals/sources";
import { pacificDayLabel, type MeasuredTruth } from "@/lib/evals/truth";
import { scanEvalsDom } from "@/lib/evals/scanEvalsDom";

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
    const page = await mount(<EvalsPage />);
    expect(page.querySelector('[data-testid="evals-page"]')).not.toBeNull();
    expect(page.querySelector("h1")?.textContent).toBe("How Bain Luck tests itself");
  });

  it("shows the gaps, the reading guide and the sources, and no section without data", async () => {
    const page = await mount(<EvalsPage />);
    const sections = Array.from(page.querySelectorAll("[data-evals-section]")).map((s) =>
      s.getAttribute("data-evals-section")
    );
    expect(sections).toEqual(["gaps", "how-to-read", "sources"]);
  });

  it("every gap row links the issue or pull request that owns it", async () => {
    const page = await mount(<EvalsPage />);
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
    const page = await mount(<EvalsPage />);
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
    let page = await mount(<EvalsPage />);
    let age = page.querySelector('[data-evals-section="gaps"] [data-age-days]');
    expect(age?.textContent).toBe("14 days ago");
    expect(age?.getAttribute("data-age-amber")).toBe("false");
    await act(async () => root?.unmount());

    freezeClockAt(daysAfterReview(15));
    page = await mount(<EvalsPage />);
    age = page.querySelector('[data-evals-section="gaps"] [data-age-days]');
    expect(age?.textContent).toBe("15 days ago");
    expect(age?.getAttribute("data-age-amber")).toBe("true");
  });

  it("lists only the sources a section on the page reads", async () => {
    const page = await mount(<EvalsPage />);
    const listed = Array.from(page.querySelectorAll("[data-source-id]")).map((s) =>
      s.getAttribute("data-source-id")
    );
    expect(listed).toEqual(EVALS_SOURCES.filter((s) => s.usedBy.includes("gaps")).map((s) => s.id));
  });

  it("the words a render assembles pass the bans too", async () => {
    const page = await mount(<EvalsPage />);
    const text = (page.textContent ?? "").replace(/\s+/g, " ");
    const hits = findBannedCopy(text, [...ALL_COPY_BANS, ...SUPPLIER_PROSE_BANS, ...EVALS_COPY_RULES]);
    expect(hits.map((h) => `${h.ban.id}: ${h.context}`)).toEqual([]);
  });
});

describe("the truth rules hold on the rendered page", () => {
  it("no bare number, no figure inside a PLANNED item, every figure under its own label", async () => {
    freezeClockAt(daysAfterReview(15)); // ages on screen, so the scan sees them
    const scan = scanEvalsDom(await mount(<EvalsPage />));
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
