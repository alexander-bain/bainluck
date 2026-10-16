/**
 * #698 — a settled Polymarket question with no stored result says "Result
 * unknown", not two confident losses.
 *
 * ## What a reader saw
 *
 * `/futures/62134744` (*Marchi vs. Lokoli: Match O/U 21.5*, resolved) at 390px:
 * both rows **Lost · 0% · Settled**, and a chart caption reading **Settled.**
 * The payload held `probability 0.5, is_winner false, resolution_source
 * "clob_authoritative"` on both legs. The 0% was a literal in `OutcomeRow`; the
 * "Lost" came from reading a sourced `false` on a resolved market as a grade
 * with no look at the price. Whether the venue voided that match is UNKNOWN.
 *
 * ## What this file pins
 *
 * The REAL detail page is mounted on the four banked served bodies
 * (`fixtures/settledDisplay698.json`, verbatim) and every assertion reads the
 * row, the hero and the chart caption TOGETHER — a helper-only test cannot see
 * a literal 0% in a cell or a bare "Settled." in a caption. Each specimen runs
 * twice: with the server's explicit `settlement_display` (pinned to the backend
 * serializer by `test_a_settled_coin_flip_is_not_a_loss_698.py`) and without it
 * (an older server mid-deploy), because the absent case must not briefly
 * restore the two losses. Synthetic boards are labelled synthetic.
 */
import React from "react";
import { readFileSync } from "fs";
import { join } from "path";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(""),
  useRouter: () => ({ replace: () => {}, push: () => {} }),
}));

let ACTIVE_MARKET: unknown = null;
let ACTIVE_HISTORY: unknown = undefined;

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => {
    if (key == null) return { data: undefined, error: null, isLoading: false };
    const tag = Array.isArray(key) ? key[0] : key;
    if (tag === "futures-market") {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      return { data: ACTIVE_MARKET as any, error: null, isLoading: false, mutate: () => {} };
    }
    if (tag === "futures-history") {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      return { data: ACTIVE_HISTORY as any, error: null, isLoading: false, mutate: () => {} };
    }
    return { data: undefined, error: null, isLoading: false, mutate: () => {} };
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

import FuturesDetailPage from "../app/futures/[id]/page";
import { outcomeRowVerdict } from "@/components/futures/OutcomeRow";
import {
  boardResultCertainty,
  clientFallbackSettlement,
  effectiveSettlement,
  settledChartCaption,
  withSettledResultCertainty,
} from "@/lib/settledResultDisplay";
import type { FuturesMarket, SettlementDisplay } from "@/lib/types";
import { formatResolvesLabel } from "@/lib/gameTimeLabel";
import FIXTURE from "./fixtures/settledDisplay698.json";

/* ────────────────────────────── the harness ────────────────────────────── */

type Specimen = "62134744" | "13798072" | "12194657" | "113360";
type Mode = "explicit" | "absent";
type Row = Record<string, unknown> & { id: number; name: string };
type Body = Record<string, unknown> & { outcomes: Row[] };

const SPECIMENS = FIXTURE.specimens as unknown as Record<
  Specimen,
  { served: Body; contract: Record<string, SettlementDisplay> }
>;

/** The banked body, optionally carrying the server's new per-row contract. */
function body(sid: Specimen, mode: Mode): Body {
  const spec = SPECIMENS[sid];
  const served = JSON.parse(JSON.stringify(spec.served)) as Body;
  if (mode === "explicit") {
    for (const o of served.outcomes) {
      const c = spec.contract[String(o.id)];
      if (c) o.settlement_display = c;
    }
  }
  return served;
}

/** Enough series to mount the trend card, which is where the caption lives. */
function historyFor(b: Body) {
  return {
    market_id: b.id,
    market_name: b.name,
    hours: 720,
    sparse: false,
    outcomes: b.outcomes.slice(0, 2).map((o) => ({
      outcome_id: o.id,
      name: o.name,
      history: [
        { timestamp: "2026-09-23T20:00:00Z", probability: 0.46, american_odds: null, bookmaker: "polymarket" },
        { timestamp: "2026-09-24T09:57:47Z", probability: 0.5, american_odds: null, bookmaker: "polymarket" },
      ],
    })),
  };
}

function render(b: Body): string {
  ACTIVE_MARKET = b;
  ACTIVE_HISTORY = historyFor(b);
  return renderToStaticMarkup(<FuturesDetailPage params={{ id: String(b.id) }} />);
}

const FOLD = 'data-testid="futures-more-outcomes"';

/** Text of the first element carrying `id`, or null when it is not rendered. */
function testIdText(html: string, id: string): string | null {
  const m = new RegExp(`data-testid="${id}"[^>]*>([\\s\\S]*?)</`).exec(html);
  if (!m) return null;
  let out = "";
  let inTag = false;
  for (const ch of m[1]) {
    if (ch === "<") inTag = true;
    else if (ch === ">") inTag = false;
    else if (!inTag) out += ch;
  }
  return out.trim();
}

/** Each rendered outcome row's own HTML, keyed by its served name. */
function rows(html: string): Map<string, string> {
  const parts = html.split('data-testid="outcome-row"').slice(1);
  const out = new Map<string, string>();
  for (const part of parts) {
    const name = /data-outcome-name="([^"]*)"/.exec(part)?.[1];
    // A row ends where the next section begins; the next row was split off.
    if (name) out.set(name.replace(/&amp;/g, "&"), part.split("</section>")[0]);
  }
  return out;
}

const count = (html: string, needle: string) => html.split(needle).length - 1;

/* ───────────────────── 62134744 — the tennis coin flip ───────────────────── */

describe.each<Mode>(["explicit", "absent"])("62134744 (%s contract)", (mode) => {
  const html = () => render(body("62134744", mode));

  it("both rows stay visible, each says Result unknown and Last recorded 50%", () => {
    const r = rows(html());
    expect([...r.keys()].sort()).toEqual(["Over", "Under"]);
    for (const row of r.values()) {
      expect(row).toContain('data-testid="outcome-result-unknown"');
      expect(testIdText(row, "outcome-result-unknown")).toBe("Result unknown");
      expect(row).toContain("Last recorded");
      expect(testIdText(row, "outcome-price")).toBe("50%");
    }
  });

  it("no row states Lost, Won, a final 0%/100% or a Settled chip", () => {
    for (const row of rows(html()).values()) {
      expect(row).not.toContain('data-testid="outcome-verdict"');
      expect(row).not.toContain(">0%<");
      expect(row).not.toContain(">100%<");
      expect(row).not.toContain(">Settled<");
      expect(row).not.toContain("bg-emerald-50");
      expect(row).not.toContain("bg-amber-50");
    }
  });

  it("the hero stays RESOLVED, crowns nobody, prints no live %, and says Result unknown", () => {
    const h = html();
    expect(testIdText(h, "hero-resolved-chip")).toBe("Resolved");
    expect(testIdText(h, "hero-result-unknown")).toBe("Result unknown");
    expect(h).not.toContain('data-testid="hero-resolved-name"');
    expect(h).not.toContain('data-testid="hero-percent"');
  });

  it("the chart caption says Result unknown instead of a bare Settled.", () => {
    expect(testIdText(html(), "futures-settled-caption")).toBe(
      "Result unknown; chart shows recorded prices.",
    );
  });

  it("nothing is folded away", () => {
    expect(html()).not.toContain(FOLD);
  });
});

/* ───────────────── 13798072 — the terminal control is untouched ───────────────── */

describe.each<Mode>(["explicit", "absent"])("13798072 terminal control (%s contract)", (mode) => {
  const html = () => render(body("13798072", mode));

  it("No Won 100%, Yes Lost 0%, hero names No, caption names the winner", () => {
    const h = html();
    const r = rows(h);
    expect(testIdText(r.get("No")!, "outcome-verdict")).toBe("Won");
    expect(r.get("No")).toContain(">100%<");
    expect(testIdText(r.get("Yes")!, "outcome-verdict")).toBe("Lost");
    expect(r.get("Yes")).toContain(">0%<");
    expect(testIdText(h, "hero-resolved-name")).toBe("No");
    expect(testIdText(h, "hero-resolved-chip")).toBe("Won");
    expect(testIdText(h, "futures-settled-caption")).toBe("Settled — No won.");
    expect(h).not.toContain("Result unknown");
  });
});

/* ──────────── 12194657 — an independent field of losses stays losses ──────────── */

describe.each<Mode>(["explicit", "absent"])("12194657 field (%s contract)", (mode) => {
  it("ten named candidates each Lost; no winner demanded; no field-wide unknown", () => {
    const h = render(body("12194657", mode));
    const r = rows(h);
    expect(r.size).toBe(10);
    expect([...r.keys()]).not.toContain("Yes");
    expect([...r.keys()]).not.toContain("No");
    for (const row of r.values()) expect(testIdText(row, "outcome-verdict")).toBe("Lost");
    expect(h).not.toContain("Result unknown");
    expect(h).not.toContain('data-testid="hero-resolved-name"');
    expect(testIdText(h, "futures-settled-caption")).toBe("Settled.");
  });
});

/* ───────────────────── 113360 — the open parent is untouched ───────────────────── */

describe("113360 open parent", () => {
  it("stays open: leader 4 at 61%, its date, no settled language", () => {
    const b = body("113360", "explicit");
    const h = render(b);
    // The reader saw "Resolves Dec 31, 2026" in Pacific; this suite pins UTC, so
    // the date is read through the page's own formatter rather than a literal.
    expect(h).toContain(formatResolvesLabel(b.resolution_date as string) as string);
    expect(testIdText(h, "hero-percent")).toBe("61");
    expect(h).not.toContain("Final Results");
    expect(h).not.toContain("Result unknown");
    expect(h).not.toContain('data-testid="outcome-verdict"');
    expect(h).not.toContain('data-testid="hero-resolved-chip"');
  });
});

/* ─────────────────────────── SYNTHETIC boards ─────────────────────────── */

function synthetic(source: string, outcomes: Row[]): Body {
  return {
    ...body("62134744", "absent"),
    id: 990698,
    name: "SYNTHETIC #698 board",
    source,
    outcome_count: outcomes.length,
    outcomes,
  };
}

function leg(id: number, name: string, p: number | null, winner: boolean | null, src: string | null, sd?: SettlementDisplay): Row {
  return {
    id,
    name,
    probability: p,
    american_odds: null,
    rank: null,
    rank_change_24h: null,
    probability_change_24h: null,
    opening_probability: null,
    opening_american_odds: null,
    is_winner: winner,
    resolution_source: src,
    last_updated: "2026-09-24T09:57:47+00:00",
    ...(sd ? { settlement_display: sd } : {}),
  };
}

const UNKNOWN_MID: SettlementDisplay = { verdict: "unknown", basis: "nonterminal_stored_price" };
const LOST_T: SettlementDisplay = { verdict: "lost", basis: "stored_terminal_agreement" };

describe("SYNTHETIC boards", () => {
  it("a midrange TRUE marked unknown crowns nobody and prints no Won", () => {
    const h = render(
      synthetic("polymarket", [
        leg(1, "Alpha Side", 0.62, true, "clob_authoritative", UNKNOWN_MID),
        leg(2, "Beta Side", 0.38, false, "clob_authoritative", UNKNOWN_MID),
      ]),
    );
    expect(h).not.toContain('data-testid="hero-resolved-name"');
    expect(testIdText(h, "hero-resolved-chip")).toBe("Resolved");
    expect(h).not.toContain(">Won<");
    expect(count(h, 'data-testid="outcome-result-unknown"')).toBe(2);
    expect(testIdText(h, "futures-settled-caption")).toBe("Result unknown; chart shows recorded prices.");
  });

  it("a mixed board keeps its definite row and says Some results unknown", () => {
    const h = render(
      synthetic("polymarket", [
        leg(1, "Alpha Side", 0.5, false, "clob_authoritative", UNKNOWN_MID),
        leg(2, "Beta Side", 0, false, "api_settlement", LOST_T),
      ]),
    );
    const r = rows(h);
    expect(testIdText(r.get("Beta Side")!, "outcome-verdict")).toBe("Lost");
    expect(testIdText(r.get("Alpha Side")!, "outcome-result-unknown")).toBe("Result unknown");
    expect(h).not.toContain('data-testid="hero-result-unknown"');
    expect(testIdText(h, "futures-settled-caption")).toBe("Settled. Some results unknown.");
  });

  it("a priceless unknown row is listed by name, not folded, with no price", () => {
    const h = render(
      synthetic("polymarket", [
        leg(1, "Alpha Side", null, false, null, { verdict: "unknown", basis: "missing_grade_source" }),
        leg(2, "Beta Side", null, null, "api_settlement", { verdict: "unknown", basis: "missing_grade" }),
      ]),
    );
    expect(h).not.toContain(FOLD);
    const r = rows(h);
    expect([...r.keys()].sort()).toEqual(["Alpha Side", "Beta Side"]);
    for (const row of r.values()) {
      expect(testIdText(row, "outcome-result-unknown")).toBe("Result unknown");
      expect(row).not.toContain("Last recorded");
      expect(row).not.toContain('data-testid="outcome-price"');
      expect(row).not.toContain(">0%<");
    }
  });

  it("CONTROL: a non-targeted resolved board keeps its legacy Lost (contract absent)", () => {
    const h = render(
      synthetic("kalshi", [
        leg(1, "Alpha Side", 0.5, false, "api_settlement"),
        leg(2, "Beta Side", 0.5, true, "api_settlement"),
      ]),
    );
    expect(h).not.toContain("Result unknown");
    expect(testIdText(rows(h).get("Alpha Side")!, "outcome-verdict")).toBe("Lost");
  });
});

/* ───────────────────────── the helpers, directly ───────────────────────── */

describe("outcomeRowVerdict prefers the contract and keeps every legacy caller", () => {
  it("explicit unknown never falls through to a legacy false", () => {
    expect(
      outcomeRowVerdict(
        { is_winner: false, resolution_source: "clob_authoritative", settlement_display: UNKNOWN_MID },
        true,
      ),
    ).toBeNull();
  });

  it("the retraction is still refused first", () => {
    expect(
      outcomeRowVerdict(
        { is_winner: true, resolution_source: "ungradeable_result", settlement_display: { verdict: "won", basis: "x" } },
        true,
      ),
    ).toBeNull();
  });

  it("a GradedRow with no contract answers exactly as before", () => {
    expect(outcomeRowVerdict({ is_winner: false, resolution_source: "api_settlement" }, true)).toBe("lost");
    expect(outcomeRowVerdict({ is_winner: false, resolution_source: null }, true)).toBeNull();
    // #6082 — an authoritative TRUE on an OPEN parent still crosses.
    expect(outcomeRowVerdict({ is_winner: true, resolution_source: "api_settlement" }, false)).toBe("won");
  });
});

describe("the rollout fallback on served values is conservative", () => {
  const base = { resolution_source: "api_settlement" };
  it.each([
    [0.5, false],
    [0.999, true],
    [0.001, false],
    [1, false],
    [0, true],
    [null, false],
  ])("p=%s winner=%s ⇒ unknown", (p, w) => {
    expect(clientFallbackSettlement({ ...base, probability: p, is_winner: w }).verdict).toBe("unknown");
  });

  it("exact terminal agreement is a result", () => {
    expect(clientFallbackSettlement({ ...base, probability: 1, is_winner: true }).verdict).toBe("won");
    expect(clientFallbackSettlement({ ...base, probability: 0, is_winner: false }).verdict).toBe("lost");
  });

  it("only resolved Polymarket boards are targeted", () => {
    const row = { probability: 0.5, is_winner: false, resolution_source: "api_settlement" };
    expect(effectiveSettlement(row, { source: "polymarket", status: "resolved" })?.verdict).toBe("unknown");
    expect(effectiveSettlement(row, { source: "polymarket", status: "open" })).toBeNull();
    expect(effectiveSettlement(row, { source: "kalshi", status: "resolved" })).toBeNull();
  });

  it("an untouched market keeps its identity; the payload is never mutated", () => {
    const kalshi = synthetic("kalshi", [leg(1, "Alpha Side", 0.5, false, "api_settlement")]);
    expect(withSettledResultCertainty(kalshi as unknown as FuturesMarket)).toBe(kalshi);
    const poly = body("62134744", "explicit");
    const before = JSON.stringify(poly);
    const projected = withSettledResultCertainty(poly as unknown as FuturesMarket);
    expect(JSON.stringify(poly)).toBe(before);
    expect(projected.outcomes?.map((o) => o.probability)).toEqual([0.5, 0.5]);
    expect(projected.outcomes?.map((o) => o.resolution_source)).toEqual([
      "clob_authoritative",
      "clob_authoritative",
    ]);
  });

  it("board certainty and caption agree", () => {
    expect(boardResultCertainty([{ settlement_display: LOST_T }], true)).toBeNull();
    expect(boardResultCertainty([{ settlement_display: UNKNOWN_MID }], false)).toBeNull();
    expect(settledChartCaption(null, "No")).toBe("Settled — No won.");
  });
});

/* ───────── Root counterexample on b0e37eb2b1: the fallback must fail CLOSED ───────── */

const AUTHORITY_PY = join(__dirname, "..", "..", "backend", "app", "utils", "resolution_authority.py");

/** Members of a named `frozenset({...})` literal (same reader as the #6082 mirror test). */
function pythonFrozenset(source: string, name: string): Set<string> {
  const block = new RegExp(
    `${name}\\s*:\\s*frozenset\\[str\\]\\s*=\\s*frozenset\\(\\{([\\s\\S]*?)\\}\\)`,
  ).exec(source);
  if (!block) throw new Error(`could not find ${name} in resolution_authority.py`);
  return new Set((block[1].match(/"([^"]+)"/g) ?? []).map((m) => m.slice(1, -1)));
}

/** The server's rule (`settlement_display.py`) over its OWN `KNOWN_SOURCES`. */
function serverVerdict(p: number | null, w: boolean | null, src: string | null, known: Set<string>) {
  if (src === "ungradeable_result" || !src || !known.has(src) || w === null || p === null) return "unknown";
  if (p > 0 && p < 1) return "unknown";
  if (p === 1 && w === true) return "won";
  if (p === 0 && w === false) return "lost";
  return "unknown";
}

describe("absent-contract fallback never says more than the server", () => {
  it.each([
    [1, true],
    [0, false],
  ])("Root's counterexample: p=%s winner=%s with an unrecognised source is unknown", (p, w) => {
    expect(
      clientFallbackSettlement({ probability: p, is_winner: w, resolution_source: "unrecognized_future_source" })
        .verdict,
    ).toBe("unknown");
  });

  it("the same row renders Result unknown, never Won, on a resolved Polymarket board", () => {
    const h = render(
      synthetic("polymarket", [
        leg(1, "Alpha Side", 1, true, "unrecognized_future_source"),
        leg(2, "Beta Side", 0, false, "unrecognized_future_source"),
      ]),
    );
    expect(h).not.toContain('data-testid="outcome-verdict"');
    expect(h).not.toContain('data-testid="hero-resolved-name"');
    expect(count(h, 'data-testid="outcome-result-unknown"')).toBe(2);
  });

  it("over every backend source and every terminal/midrange/null shape, a definite client verdict equals the server's", () => {
    const py = readFileSync(AUTHORITY_PY, "utf8");
    const known = new Set(
      ["AUTHORITATIVE_SOURCES", "DETERMINISTIC_SOURCES", "TERMINAL_SOURCES", "GUESS_FAMILY_SOURCES"].flatMap(
        (n) => [...pythonFrozenset(py, n)],
      ),
    );
    expect(known.size).toBeGreaterThan(20);
    const sources: (string | null)[] = [...known, "unrecognized_future_source", "", null];
    let definite = 0;
    for (const src of sources)
      for (const p of [0, 1, 0.5, 0.001, 0.999, null])
        for (const w of [true, false, null]) {
          const client = clientFallbackSettlement({ probability: p, is_winner: w, resolution_source: src }).verdict;
          if (client !== "unknown") {
            definite += 1;
            expect([src, p, w, client]).toEqual([src, p, w, serverVerdict(p, w, src, known)]);
          }
        }
    // Not vacuous: the tier-3 subset still yields definite results on terminal rows.
    expect(definite).toBeGreaterThan(0);
  });
});
