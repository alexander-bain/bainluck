/**
 * #683 — A FULL CHART SAYS OLDER PRICES WERE LEFT OUT EVEN WHEN IT CANNOT DRAW A LINE.
 *
 * PR #11116 @ 192e5a7f15 put `PARTIAL_HISTORY_CAPTION` under the plot, but
 * `FuturesChart` returns early before the plot in two places:
 *
 *   - no displayed outcomes          → "Select outcomes below…"
 *   - empty / one value / equal time → "Limited price history available"
 *
 * so a `range=full` read that said `served_history: "partial"` and left too
 * few prices to draw printed "limited history" and nothing about the history
 * the server held back (Root's witness: 3 fail / 2 pass on the offered head).
 * And four of the five full-range callers hide the chart entirely on an empty
 * or one-value payload before `FuturesChart` is ever reached.
 *
 * The rule, all of it:
 *  - partial + too little to draw ⇒ the sparse state AND the one caption.
 *  - partial + nothing served     ⇒ the caller still reaches the chart, which
 *    says so; complete + nothing served keeps every caller's old absence.
 *  - a selection that draws nothing (the served lines exist, the reader's
 *    choice matches none) keeps its prompt and no caption — that empty chart
 *    is the reader's choice, not the server's.
 *  - mini stays silent; complete/absent stays byte-identical.
 */

import "../helpers/minimalDom";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

let SEARCH = "";
let MARKET: unknown = null;
let HISTORY: unknown = null;

jest.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(SEARCH),
  useRouter: () => ({ replace: () => {}, push: () => {} }),
  usePathname: () => "/",
}));

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => {
    if (key == null) return { data: undefined, error: null, isLoading: false, mutate: () => {} };
    const tag = Array.isArray(key) ? key[0] : key;
    const data =
      tag === "futures-market"
        ? MARKET
        : tag === "futures-history" ||
            tag === "event-settled-path" ||
            tag === "event-twosided" ||
            tag === "event-winner-evolution" ||
            (typeof tag === "string" && tag.startsWith("futures-evolution-"))
          ? HISTORY
          : undefined;
    return { data, error: null, isLoading: false, mutate: () => {} };
  },
}));

jest.mock("@/hooks", () => ({
  usePageTracking: () => {},
  useScrollDepth: () => {},
  useEngagementTime: () => {},
  usePinnedFutures: () => ({ isPinned: () => false, togglePin: () => {}, isMaxReached: false }),
}));

jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({ track: () => {} }),
}));

jest.mock("../../components/event/FighterAvatar", () => ({ __esModule: true, default: () => null }));

import FuturesDetailPage from "../../app/futures/[id]/page";
import { EvolutionView } from "@/components/EvolutionView";
import { FuturesChart } from "@/components/FuturesChart";
import SettledPathChart from "@/components/event/SettledPathChart";
import TwoSidedTimeline from "@/components/event/TwoSidedTimeline";
import WinnerEvolutionChart from "@/components/event/WinnerEvolutionChart";
import { PARTIAL_HISTORY_CAPTION } from "@/lib/historyRange";
import type { FuturesHistoryPoint, FuturesOutcomeHistory } from "@/lib/types";

const CAPTION_ID = 'data-testid="futures-chart-history-partial"';
const SPARSE = "Limited price history available";
const PROMPT = "Select outcomes below to see their probability trends";
const NOW = Date.UTC(2026, 9, 15, 20, 0, 0);

beforeAll(() => {
  jest.useFakeTimers({ doNotFake: ["performance"] });
  jest.setSystemTime(NOW);
});
afterAll(() => jest.useRealTimers());
beforeEach(() => {
  SEARCH = "";
  MARKET = null;
  HISTORY = null;
});

const count = (html: string, needle: string) => html.split(needle).length - 1;
/** The flagged markup with its one caption cut out — what the chart drew around it. */
const withoutCaption = (html: string) =>
  html.replace(/<(p|span)[^>]*data-testid="futures-chart-history-partial"[^>]*>[^<]*<\/\1>/, "");

const pt = (iso: string, probability: number | null): FuturesHistoryPoint => ({
  timestamp: iso,
  probability,
  american_odds: null,
  bookmaker: "consensus",
});
const line = (history: FuturesHistoryPoint[], id = 1, name = "Yes"): FuturesOutcomeHistory => ({
  outcome_id: id,
  name,
  history,
});

const A = "2026-03-02T00:00:00Z";
const B = "2026-03-03T00:00:00Z";
const SHAPES: [string, FuturesOutcomeHistory[]][] = [
  ["zero outcomes", []],
  ["one empty series", [line([])]],
  ["one real observation", [line([pt(A, 0.3)])]],
  ["two prices at the same instant", [line([pt(A, 0.3)]), line([pt(A, 0.7)], 2, "No")]],
  ["one price plus nulls", [line([pt(A, 0.3), pt(B, null)])]],
];
const PLOTTED = [line([pt(A, 0.3), pt(B, 0.4)])];

describe("#683 FuturesChart: a sparse full read still says older prices were withheld", () => {
  it.each(SHAPES)("partial + %s ⇒ the sparse state and exactly one caption", (_n, data) => {
    const html = renderToStaticMarkup(<FuturesChart historyData={data} settled historyWithheld />);
    expect(html).toContain(SPARSE);
    expect(count(html, CAPTION_ID)).toBe(1);
    expect(html).toContain(PARTIAL_HISTORY_CAPTION.replace(/'/g, "&#x27;"));
  });

  it.each(SHAPES.filter(([, d]) => d.length > 0))(
    "the flag adds the caption and nothing else to the %s state",
    (_n, data) => {
      const flagged = renderToStaticMarkup(<FuturesChart historyData={data} settled historyWithheld />);
      const plain = renderToStaticMarkup(<FuturesChart historyData={data} settled />);
      expect(withoutCaption(flagged)).toBe(plain);
    },
  );

  it("CONTROL: a populated partial chart keeps its one caption under the plot", () => {
    const html = renderToStaticMarkup(<FuturesChart historyData={PLOTTED} settled historyWithheld />);
    expect(html).not.toContain(SPARSE);
    expect(count(html, CAPTION_ID)).toBe(1);
  });

  it.each(SHAPES)("CONTROL: complete + %s keeps its old state and no caption", (_n, data) => {
    const html = renderToStaticMarkup(<FuturesChart historyData={data} settled />);
    expect(html).not.toContain(CAPTION_ID);
    // Complete and empty is unchanged: the zero-outcome case keeps its prompt.
    expect(html).toContain(data.length === 0 ? PROMPT : SPARSE);
  });

  it("a selection that draws nothing keeps its prompt and is not told the server withheld", () => {
    const html = renderToStaticMarkup(
      <FuturesChart historyData={PLOTTED} selectedOutcomes={new Set([99])} historyWithheld />,
    );
    expect(html).toContain(PROMPT);
    expect(html).not.toContain(CAPTION_ID);
  });

  it.each(SHAPES)("a mini chart stays silent on partial + %s", (_n, data) => {
    expect(renderToStaticMarkup(<FuturesChart historyData={data} mini historyWithheld />)).toBe("");
  });

  it("the cadence line the page already prints is still not repeated", () => {
    const one = SHAPES[2][1];
    const html = renderToStaticMarkup(
      <FuturesChart historyData={one} settled cadenceNoteShown historyWithheld />,
    );
    expect(html).not.toContain("prices no longer update");
    expect(count(html, CAPTION_ID)).toBe(1);
  });
});

// ── The five full-range callers, on the payload a full read can actually serve ──

type Range = "partial" | "complete";
const historyResponse = (outcomes: FuturesOutcomeHistory[], served: Range) => ({
  market_id: 4242,
  market_name: "Who wins?",
  hours: 8760,
  actual_hours: 8760,
  outcomes,
  round_boundaries: null,
  leaderboard: null,
  total_data_points: outcomes.reduce((s, o) => s + o.history.length, 0),
  coverage_start: null,
  coverage_end: null,
  coverage_hours: 0,
  observation_times: 0,
  sparse: true,
  history_range: {
    requested: "full",
    window_start: A,
    window_start_basis: "archive_first_interval",
    archive_coverage: "complete",
    thinned_outcomes: [],
    served_history: served,
  },
});

const market = (status: "resolved" | "open") => ({
  id: 4242,
  name: "Who wins?",
  status,
  source: "kalshi",
  category: "politics",
  llm_sport_category: null,
  market_type: null,
  mutually_exclusive: true,
  outcome_count: 2,
  prices_withheld: 0,
  bookmakers: ["kalshi"],
  resolution_date: "2026-09-27T00:00:00+00:00",
  updated_at: "2026-10-01T12:18:13+00:00",
  outcomes: [
    { id: 1, name: "Yes", probability: status === "open" ? 0.4 : null, rank: 1,
      opening_probability: null, probability_change_24h: null, american_odds: null,
      opening_american_odds: null, is_winner: status === "resolved" ? true : null,
      resolution_source: status === "resolved" ? "api_settlement" : null,
      last_updated: "2026-10-01T12:18:13+00:00" },
    { id: 2, name: "No", probability: status === "open" ? 0.6 : null, rank: 2,
      opening_probability: null, probability_change_24h: null, american_odds: null,
      opening_american_odds: null, is_winner: status === "resolved" ? false : null,
      resolution_source: status === "resolved" ? "api_settlement" : null,
      last_updated: "2026-10-01T12:18:13+00:00" },
  ],
});

const CALLERS: [string, () => React.ReactElement][] = [
  ["the futures page (All)", () => {
    SEARCH = "range=all";
    MARKET = market("resolved");
    return <FuturesDetailPage params={{ id: "4242" }} />;
  }],
  ["EvolutionView", () => <EvolutionView marketId={4242} requireCurrentPrices={false} />],
  ["SettledPathChart", () => <SettledPathChart marketId={4242} />],
  // Only its All rung asks for the full read; the flag is read off the payload
  // whatever rung is lit, so the served body is what this arm varies.
  ["TwoSidedTimeline", () => (
    <TwoSidedTimeline
      competitors={[{ name: "Yes", probability: 0.4 }, { name: "No", probability: 0.6 }] as never}
      label="Head to head"
      evolutionMarketId={4242}
    />
  )],
  ["WinnerEvolutionChart", () => <WinnerEvolutionChart marketId={4242} />],
];

function renderCaller(make: () => React.ReactElement, outcomes: FuturesOutcomeHistory[], served: Range) {
  HISTORY = historyResponse(outcomes, served);
  return renderToStaticMarkup(make());
}

// Inside every caller's default client window (EvolutionView trims by range).
const R1 = "2026-10-15T12:00:00Z";
const R2 = "2026-10-15T18:00:00Z";

describe("#683 every full-range caller reaches the chart when a partial read left too little to draw", () => {
  it.each(CALLERS)("%s: partial + nothing served ⇒ one caption", (_n, make) => {
    const html = renderCaller(make, [], "partial");
    expect(count(html, CAPTION_ID)).toBe(1);
  });

  it.each(CALLERS)("%s: partial + one value ⇒ one caption", (_n, make) => {
    const html = renderCaller(make, [line([pt(R1, 0.3)])], "partial");
    expect(count(html, CAPTION_ID)).toBe(1);
  });

  it.each(CALLERS)("CONTROL %s: complete + nothing served ⇒ no caption, as before", (_n, make) => {
    const html = renderCaller(make, [], "complete");
    expect(html).not.toContain(CAPTION_ID);
  });

  it.each(CALLERS)("CONTROL %s: partial + a drawable history ⇒ one caption under the plot", (_n, make) => {
    const html = renderCaller(make, [line([pt(R1, 0.3), pt(R2, 0.4)]), line([pt(R1, 0.7), pt(R2, 0.6)], 2, "No")], "partial");
    expect(count(html, CAPTION_ID)).toBe(1);
    expect(html).not.toContain(SPARSE);
  });
});

describe("#683 the old absences are kept where the read was complete", () => {
  it("event sections still render nothing on a complete empty read", () => {
    for (const [name, make] of CALLERS.slice(2)) {
      const html = renderCaller(make, [], "complete");
      if (name.startsWith("TwoSidedTimeline")) {
        expect(html).not.toContain(SPARSE);
      } else {
        expect(html).toBe("");
      }
    }
  });

  it("EvolutionView still says it has no history on a complete empty read", () => {
    const html = renderCaller(CALLERS[1][1], [], "complete");
    expect(html).toContain("No history data available");
  });

  it("the futures page keeps its empty-market card, uncaptioned, on a complete empty read", () => {
    const html = renderCaller(CALLERS[0][1], [], "complete");
    expect(html).toContain("Not enough price history yet");
    expect(html).not.toContain(CAPTION_ID);
  });

  it("the futures page's empty card carries the caption on a partial empty read", () => {
    const partial = renderCaller(CALLERS[0][1], [], "partial");
    const complete = renderCaller(CALLERS[0][1], [], "complete");
    expect(withoutCaption(partial)).toBe(complete);
  });

  it("EvolutionView's no-history box changes only by the caption", () => {
    const partial = renderCaller(CALLERS[1][1], [], "partial");
    const complete = renderCaller(CALLERS[1][1], [], "complete");
    expect(partial).toContain("No history data available");
    expect(withoutCaption(partial).replace("flex flex-col gap-1.5 items-center", "flex items-center")).toBe(complete);
  });
});
