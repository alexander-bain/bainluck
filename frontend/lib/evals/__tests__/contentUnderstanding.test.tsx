/**
 * @jest-environment jsdom
 */

import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";

import ContentUnderstandingSection from "@/components/evals/ContentUnderstandingSection";
import { loadCuScorecard, parseCuScorecard } from "@/lib/evals/contentUnderstanding";
import { scanEvalsDom } from "@/lib/evals/scanEvalsDom";
import { ALL_COPY_BANS, SUPPLIER_PROSE_BANS, findBannedCopy } from "@/lib/copyBans";
import { EVALS_COPY_RULES } from "@/lib/evals/copyRules";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

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
  if (root) {
    await act(async () => {
      root?.unmount();
    });
  }
  root = null;
  host?.remove();
  host = null;
});

describe("Content Understanding section on /evals (#13901)", () => {
  it("renders the checked-in pre-label scorecard as Not measured yet with zero figures or bare numbers", async () => {
    const scorecard = loadCuScorecard();
    expect(scorecard?.status).toBe("not_measured_yet");
    expect(scorecard?.asOf).toBe("2026-11-27");

    const el = await mount(<ContentUnderstandingSection scorecard={scorecard!} />);
    const statusText = el.querySelector('[data-testid="evals-cu-unmeasured"]')?.textContent ?? "";
    expect(statusText).toContain("Not measured yet as of Nov 27");
    expect(el.querySelector("time")?.getAttribute("dateTime")).toBe("2026-11-27");
    expect(el.querySelectorAll("[data-evals-figure]")).toHaveLength(0);
    expect(el.querySelector('[data-cu-group="code"] [data-cu-planned-field="liveness"]')?.textContent).toBe("Trading activity");
    expect(el.querySelector('[data-cu-group="model"] [data-cu-planned-field="topic"]')?.textContent).toBe("Topic");
    for (const sharedField of ["geography", "event_date", "stakes", "breadth", "junk_flags"]) {
      expect(el.querySelector(`[data-cu-group="code"] [data-cu-planned-field="${sharedField}"]`)).not.toBeNull();
      expect(el.querySelector(`[data-cu-group="model"] [data-cu-planned-field="${sharedField}"]`)).not.toBeNull();
    }

    expect(scanEvalsDom(el)).toEqual({ bareNumbers: [], figuresInPlanned: [], figuresOutsideScope: [] });
    const hits = findBannedCopy((el.textContent ?? "").replace(/\s+/g, " "), [
      ...ALL_COPY_BANS,
      ...SUPPLIER_PROSE_BANS,
      ...EVALS_COPY_RULES,
    ]);
    expect(hits).toEqual([]);
    expect(el.textContent).not.toContain("said not known");
  });

  it("renders measured per-field code/model columns, cost, revision and slices under Figure rules", async () => {
    const measured = parseCuScorecard({
      status: "measured",
      as_of: "2026-12-11",
      dataset: "sealed",
      writer_rev: 10,
      model: "gpt-4o-mini",
      market_count: 300,
      cost: { total_usd: 0.14, per_market_usd: 0.000467 },
      decider_totals: {
        code: { right: 590, wrong: 5, blank: 0, said_not_known: 5, total: 600 },
        model: { right: 280, wrong: 12, blank: 4, said_not_known: 4, total: 300 },
      },
      fields: [
        {
          field: "liveness",
          label: "Trading activity",
          decided_by: "code",
          code: { right: 298, wrong: 2, blank: 0, said_not_known: 0, total: 300 },
          model: { right: 0, wrong: 0, blank: 0, said_not_known: 0, total: 0 },
          total: { right: 298, wrong: 2, blank: 0, said_not_known: 0, total: 300 },
        },
        {
          field: "topic",
          label: "Topic",
          decided_by: "model",
          code: { right: 0, wrong: 0, blank: 0, said_not_known: 0, total: 0 },
          model: { right: 280, wrong: 12, blank: 4, said_not_known: 4, total: 300 },
          total: { right: 280, wrong: 12, blank: 4, said_not_known: 4, total: 300 },
        },
      ],
      slices: {
        by_venue: {
          site_a: { market_count: 150, decider_totals: {} },
          site_b: { market_count: 150, decider_totals: {} },
        },
        by_exposure: {
          readers_see: { market_count: 200, decider_totals: {} },
          rest: { market_count: 100, decider_totals: {} },
        },
      },
    });
    expect(measured?.status).toBe("measured");

    const el = await mount(<ContentUnderstandingSection scorecard={measured!} />);
    expect(el.querySelector('[data-truth-scope="last_run"]')).not.toBeNull();
    expect(el.querySelector('[data-cu-row="liveness"] [data-cu-decider="code"]')?.textContent).toContain("298");
    expect(el.querySelector('[data-cu-row="topic"] [data-cu-decider="model"]')?.textContent).toContain("280");
    expect(el.querySelector('[data-cu-slice="by_exposure"]')?.textContent).toContain("What readers see");
    expect(el.textContent).toContain("$0.140");
    expect(el.textContent).toContain("said it did not know");
    expect(scanEvalsDom(el)).toEqual({ bareNumbers: [], figuresInPlanned: [], figuresOutsideScope: [] });
  });
});
