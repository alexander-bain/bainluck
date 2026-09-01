// lane1-Q479 — the PAGE-level proof for TOP-PRODUCT-DEFECTS item 13.
//
// The lib test pins the predicate. This one renders the actual
// `app/futures/[id]/page.tsx` against the REAL production payload of market
// 109441 ("Which companies will release a Fully AI-generated multi-episode
// scripted series before 2027?"), captured verbatim on 2026-08-31 into
// `__tests__/fixtures/futuresDetail109441Production.json`, and counts what a
// reader sees.
//
// It exists because the claim is about a PAGE. A predicate returning `true`
// proves nothing if the page never calls it — the field it reads has been on
// this payload the whole time and no surface had ever looked at it.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import {
  INDEPENDENT_OUTCOMES_NOTE_OPEN,
  INDEPENDENT_OUTCOMES_NOTE_SETTLED,
} from "@/lib/outcomeExclusivity";

// eslint-disable-next-line @typescript-eslint/no-var-requires
const PRODUCTION = require("../fixtures/futuresDetail109441Production.json");

const RAW = PRODUCTION as Record<string, unknown>;

let payload: Record<string, unknown> = RAW;

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

jest.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
}));

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => {
    if (key == null) return { data: undefined, error: null, isLoading: false };
    const tag = Array.isArray(key) ? key[0] : key;
    if (tag === "futures-market") return { data: payload, error: null, isLoading: false };
    return { data: undefined, error: null, isLoading: false };
  },
}));

jest.mock("@/hooks", () => ({
  usePageTracking: () => {},
  useScrollDepth: () => {},
  useEngagementTime: () => {},
  usePinnedFutures: () => ({ isPinned: () => false, togglePin: () => {}, pinned: [] }),
}));

jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({}),
}));

import FuturesDetailPage from "@/app/futures/[id]/page";

function render(p: Record<string, unknown>): string {
  payload = p;
  return renderToStaticMarkup(<FuturesDetailPage params={{ id: "109441" }} />);
}

type Outcome = { name: string; probability: number };

describe("the specimen still holds this queue's premise", () => {
  test("109441 is the eight-way bundle whose rows do not add up", () => {
    const outcomes = RAW.outcomes as Outcome[];
    expect(outcomes).toHaveLength(8);
    const sum = outcomes.reduce((t, o) => t + o.probability, 0);
    // Alex's arithmetic, to the cent: 27+7+6+5+5+4+3+3 reads as 60.
    expect(Math.round(sum * 100)).toBe(59);
    expect(sum).toBeLessThan(0.8);
  });

  test("🔴 and production ALREADY served the fact that explains it", () => {
    // The root cause is not a missing field. `mutually_exclusive` is on the
    // payload, and it is Kalshi's own event flag (`services/kalshi_api.py`
    // reads `event_data["mutually_exclusive"]`; the live event answers False).
    // The page simply never read it.
    expect(RAW).toHaveProperty("mutually_exclusive");
    expect(RAW.mutually_exclusive).toBe(false);
  });

  test("the payload ranks them 1..8 in the same breath", () => {
    // The contradiction on one response: a rank ladder over a set the same
    // response says is not a contest.
    const ranks = (RAW.outcomes as { rank: number }[]).map((o) => o.rank);
    expect(ranks).toEqual([1, 2, 3, 4, 5, 6, 7, 8]);
  });
});

describe("the page now says why the numbers do not add up", () => {
  test("the note renders, verbatim, on the real production payload", () => {
    const html = render(RAW);
    expect(html).toContain('data-testid="independent-outcomes-note"');
    expect(html).toContain(escapeHtml(INDEPENDENT_OUTCOMES_NOTE_OPEN));
  });

  test("it sits above the outcome rows, where the adding happens", () => {
    const html = render(RAW);
    const note = html.indexOf('data-testid="independent-outcomes-note"');
    const firstRow = html.indexOf("Peacock");
    expect(note).toBeGreaterThan(-1);
    expect(firstRow).toBeGreaterThan(-1);
    // Order, not containment: a note rendered after the list is a note the
    // reader reaches only once they have already summed the column.
    expect(note).toBeLessThan(firstRow);
  });

  test("every outcome still renders — nothing was hidden to make the sum go away", () => {
    const html = render(RAW);
    for (const o of RAW.outcomes as Outcome[]) {
      expect(html).toContain(escapeHtml(o.name));
    }
  });

  test("🔴 no probability was rewritten — Amazon is still 27%, not 46%", () => {
    // 0.27 / 0.59 = 0.4576. If a future change ever renormalises this set, this
    // is the assertion that catches it: the source denies exclusivity, so a
    // normalised Amazon would be a fabricated number.
    const html = render(RAW);
    expect(html).toContain("27%");
    expect(html).not.toContain("46%");
  });
});

describe("the control — an exclusive set is untouched", () => {
  // The ONLY difference from the production payload is the one field. Anything
  // that changes here changes because of the flag and nothing else.
  const EXCLUSIVE = { ...RAW, mutually_exclusive: true };

  test("no note, on either string", () => {
    const html = render(EXCLUSIVE);
    expect(html).not.toContain('data-testid="independent-outcomes-note"');
    expect(html).not.toContain(escapeHtml(INDEPENDENT_OUTCOMES_NOTE_OPEN));
    expect(html).not.toContain(escapeHtml(INDEPENDENT_OUTCOMES_NOTE_SETTLED));
  });

  test("a payload that omits the field entirely also says nothing", () => {
    const withoutField = { ...RAW } as Record<string, unknown>;
    delete withoutField.mutually_exclusive;
    const html = render(withoutField);
    expect(html).not.toContain('data-testid="independent-outcomes-note"');
  });

  test("the rest of the card is byte-identical with and without the flag", () => {
    // The strongest statement of "this does not touch the healthy case": strip
    // the note out of the independent render and the two HTML strings match.
    const independent = render(RAW);
    const exclusive = render(EXCLUSIVE);
    const stripped = independent.replace(
      /<p data-testid="independent-outcomes-note"[^>]*>.*?<\/p>/,
      ""
    );
    expect(stripped).toBe(exclusive);
  });
});

describe("the settled rendering, enumerated rather than assumed", () => {
  const SETTLED = {
    ...RAW,
    status: "resolved",
    outcomes: (RAW.outcomes as Record<string, unknown>[]).map((o, i) => ({
      ...o,
      // Two winners: the very thing the flag says is possible, and the reason
      // "one wins" was never true of this market.
      is_winner: i < 2,
    })),
  };

  test("a settled bundle prints the past tense and not the present", () => {
    const html = render(SETTLED);
    expect(html).toContain(escapeHtml(INDEPENDENT_OUTCOMES_NOTE_SETTLED));
    expect(html).not.toContain(escapeHtml(INDEPENDENT_OUTCOMES_NOTE_OPEN));
  });

  test("and it still renders under the settled heading", () => {
    const html = render(SETTLED);
    expect(html).toContain("Final Results");
    expect(html.indexOf("Final Results")).toBeLessThan(
      html.indexOf('data-testid="independent-outcomes-note"')
    );
  });
});

/** React escapes text nodes; compare against what actually lands in the markup. */
function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#x27;");
}

describe("CERT-609 — the RENDERED page does not print the note off a Polymarket false", () => {
  // The predicate contract lives in `__tests__/lib/outcomeExclusivityQ479.test.ts`.
  // This block is the served-shape half: the cert's finding was that the UI "can
  // print 'Several … can happen' from absent metadata", so the proof has to be on
  // the HTML, not on the helper that feeds it.
  //
  // Polymarket's `polymarket_api.py` turns an ABSENT `negRisk` key into `false`
  // and `tasks/polymarket.py` writes it straight into `mutually_exclusive`. So a
  // Polymarket `false` is indistinguishable from Polymarket saying nothing —
  // ~1,970 open field markets carry it.
  const POLYMARKET = { ...RAW, source: "polymarket" };

  test("same flag, same eight outcomes, different source — and the page stays silent", () => {
    const html = render(POLYMARKET);
    expect(html).not.toContain('data-testid="independent-outcomes-note"');
    expect(html).not.toContain(escapeHtml(INDEPENDENT_OUTCOMES_NOTE_OPEN));
    expect(html).not.toContain(escapeHtml(INDEPENDENT_OUTCOMES_NOTE_SETTLED));
  });

  test("silence is the ONLY difference — the rest of the card is byte-identical", () => {
    // Withholding the claim must not cost the reader anything else. Strip the note
    // from the Kalshi render and the two pages match exactly.
    const kalshi = render(RAW);
    const stripped = kalshi.replace(
      /<p data-testid="independent-outcomes-note"[^>]*>.*?<\/p>/,
      ""
    );
    // `source` is itself rendered nowhere on this card, so the two must agree.
    expect(stripped).toBe(render(POLYMARKET));
  });

  test("and the Kalshi specimen still prints it — the ship is not gated away", () => {
    // The failure mode of an over-tight fix: satisfy the cert by printing nothing
    // anywhere. 109441 is Kalshi, so item 13 must still be fixed on the page.
    expect(RAW.source).toBe("kalshi");
    const html = render(RAW);
    expect(html).toContain('data-testid="independent-outcomes-note"');
    expect(html).toContain(escapeHtml(INDEPENDENT_OUTCOMES_NOTE_OPEN));
  });
});
