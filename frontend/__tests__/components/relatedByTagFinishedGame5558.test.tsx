/**
 * #5558 — A FINISHED GAME IN THE RELATED RAIL IS A RESULT, NOT A PRICE.
 *
 * `RelatedByTag`'s game branch read `current_odds` with no status check. After
 * the final that is the SETTLED market, so a finished game drew a live-looking
 * forecast with no score and no FINAL — and on soccer rails it named the loser
 * as favourite.
 *
 * ## Fixtures
 *
 * - `ux1493_related_football_finished_5558` — PRODUCTION BYTES, unedited:
 *   `GET /api/feed?limit=80&tags=["sport:football"]`, 2026-09-25 18:53Z. Item 11
 *   is `Atlanta Falcons @ Green Bay Packers` (14780546), `status: completed`,
 *   35–14, `current_odds` 0.999 / 0.001 (the settled market), `prematch_odds`
 *   0.31 / 0.69 (kalshi). The rail printed `>99%` / `<1%` for it.
 * - `ux1493_related_soccer_live_5558` — PRODUCTION BYTES, unedited:
 *   `GET /api/feed?limit=9&tags=["sport:soccer"]`, same minute. `Belgium @ Italy`
 *   is LIVE, the control; the draw-sport finished arms derive from that row by
 *   changing status/scores only, and say so.
 *
 * ## The unfixed direction (gotcha #43)
 *
 * The live and scheduled cards in both payloads must print exactly what they
 * printed before — current odds, live dot, no FINAL. ARM 4 pins them.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import FOOTBALL from "../fixtures/ux1493_related_football_finished_5558.20260925.json";
import SOCCER from "../fixtures/ux1493_related_soccer_live_5558.20260925.json";

let swrPayload: unknown;

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({ data: swrPayload, error: undefined, isLoading: false }),
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
const RelatedByTag = require("@/components/RelatedByTag").default;

type Item = { type: string; data: Record<string, unknown> };
type Payload = { items: Item[] };

function render(payload: unknown, limit: number): string {
  swrPayload = payload;
  return renderToStaticMarkup(
    React.createElement(RelatedByTag as React.FC, {
      tags: ["sport:x"],
      limit,
      title: "More",
    } as never),
  );
}

/** One card's markup: the `<a>` whose href is this event, through its `</a>`. */
function eventCard(html: string, id: number): string {
  const start = html.search(new RegExp(`<a [^>]*href="/events/${id}"`));
  if (start < 0) throw new Error(`no card for event ${id}`);
  return html.slice(start, html.indexOf("</a>", start) + 4);
}

function text(fragment: string): string {
  return fragment.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
}

function attr(card: string, name: string): string | null {
  const open = card.slice(0, card.indexOf(">") + 1);
  return open.match(new RegExp(`${name}="([^"]*)"`))?.[1] ?? null;
}

/** Every element carrying this test id: its class and its text. */
function byTestId(card: string, id: string): { className: string; text: string }[] {
  const out: { className: string; text: string }[] = [];
  const re = new RegExp(`<(\\w+)([^>]*data-testid="${id}"[^>]*)>`, "g");
  let m: RegExpExecArray | null;
  while ((m = re.exec(card))) {
    const close = `</${m[1]}>`;
    // Nested same-name tags: walk to the balancing close.
    let depth = 1;
    let i = m.index + m[0].length;
    while (depth > 0) {
      const nextOpen = card.indexOf(`<${m[1]}`, i);
      const nextClose = card.indexOf(close, i);
      if (nextOpen !== -1 && nextOpen < nextClose) {
        depth += 1;
        i = nextOpen + 1;
      } else {
        depth -= 1;
        i = nextClose + close.length;
      }
    }
    out.push({
      className: m[2].match(/class="([^"]*)"/)?.[1] ?? "",
      text: text(card.slice(m.index, i)),
    });
  }
  return out;
}

function rowText(card: string, side: "away" | "home"): string {
  const start = card.indexOf(`data-side="${side}"`);
  if (start < 0) return "";
  return text(card.slice(start, card.indexOf("</li>", start)).replace(/^[^>]*>/, ""));
}

/** A single-item payload built from a production row, with named overrides. */
function derived(row: Record<string, unknown>, overrides: Record<string, unknown>): Payload {
  return { items: [{ type: "event", data: { ...row, ...overrides } }] };
}

const football = FOOTBALL as unknown as Payload;
const soccer = SOCCER as unknown as Payload;
const FALCONS = 14780546;
const falconsRow = football.items.find(
  (item) => item.type === "event" && item.data.id === FALCONS,
)!.data;
const belgiumRow = soccer.items.find(
  (item) => item.type === "event" && item.data.status === "live",
)!.data;

describe("#5558 the specimen is what the fixture says it is", () => {
  it("Falcons @ Packers is completed, 35–14, settled market 0.999, pre-match 0.31/0.69", () => {
    expect(falconsRow.status).toBe("completed");
    expect([falconsRow.away_score, falconsRow.home_score]).toEqual([35, 14]);
    expect((falconsRow.current_odds as { away_probability: number }).away_probability).toBe(0.999);
    const pm = falconsRow.prematch_odds as { away_probability: number; home_probability: number };
    expect([pm.away_probability, pm.home_probability]).toEqual([0.31, 0.69]);
  });
});

describe("#5558 ARM 1 — the production finished card reads as a result", () => {
  const host = render(football, football.items.length);
  const card = eventCard(host, FALCONS);

  it("carries FINAL and the final state", () => {
    expect(attr(card, "data-state")).toBe("final");
    expect(byTestId(card, "related-card-final").map((f) => f.text)).toEqual(["FINAL"]);
  });

  it("prints the score, bold on the winner", () => {
    const scores = byTestId(card, "related-card-score");
    expect(scores.map((s) => s.text)).toEqual(["35", "14"]);
    expect(scores[0].className).toContain("font-bold");
    expect(scores[1].className).not.toContain("font-bold");
  });

  it("prints the pre-match reading beside each name, not the settled market", () => {
    expect(rowText(card, "away")).toContain("31%");
    expect(rowText(card, "home")).toContain("69%");
    expect(text(card)).not.toMatch(/&gt;99%|&lt;1%|>99%|<1%|99\.9|100%/);
    expect(byTestId(card, "related-card-field")).toHaveLength(0);
  });
});

describe("#5558 ARM 2 — no finished card in the payload prints current_odds", () => {
  it("every completed/closed event renders as a result", () => {
    const host = render(football, football.items.length);
    const finished = football.items.filter(
      (item) => item.type === "event" && ["completed", "closed"].includes(item.data.status as string),
    );
    expect(finished.length).toBeGreaterThan(0);
    for (const item of finished) {
      const card = eventCard(host, item.data.id as number);
      expect(attr(card, "data-state")).toBe("final");
      expect(byTestId(card, "related-card-field")).toHaveLength(0);
    }
  });
});

describe("#5558 ARM 3 — a draw-priced sport", () => {
  it("a finished soccer game prints both pre-match numbers when the pair is not a complement", () => {
    // Belgium @ Italy's own books pre-match pair: 0.2885 / 0.4419 (the ~0.27
    // missing is the draw), so the away number is a real away price.
    const card = eventCard(
      render(derived(belgiumRow, { status: "completed", away_score: 1, home_score: 0 }), 4),
      belgiumRow.id as number,
    );
    expect(rowText(card, "away")).toMatch(/Belgium\s*29%\s*1$/);
    expect(rowText(card, "home")).toMatch(/Italy\s*44%\s*0$/);
    // The live blend (0.5644 / 0.4356) is gone.
    expect(text(card)).not.toMatch(/56%/);
  });

  it("withholds the away pre-match number when it is only 'home does not win' (#6238)", () => {
    const card = eventCard(
      render(
        derived(belgiumRow, {
          status: "completed",
          away_score: 1,
          home_score: 1,
          prematch_odds: { away_probability: 0.6, home_probability: 0.4, source: "kalshi" },
        }),
        4,
      ),
      belgiumRow.id as number,
    );
    expect(byTestId(card, "related-card-prematch")).toHaveLength(1);
    expect(rowText(card, "home")).toContain("40%");
    expect(rowText(card, "away")).not.toContain("%");
    // A draw bolds nobody.
    byTestId(card, "related-card-score").forEach((score) => {
      expect(score.className).not.toContain("font-bold");
    });
  });

  it("with no pre-match reading and no score, prints FINAL and no number", () => {
    const card = eventCard(
      render(
        derived(belgiumRow, {
          status: "closed",
          away_score: null,
          home_score: null,
          prematch_odds: null,
          opening_odds: null,
        }),
        4,
      ),
      belgiumRow.id as number,
    );
    expect(byTestId(card, "related-card-final")).toHaveLength(1);
    expect(text(card)).not.toMatch(/\d/);
  });
});

describe("#5558 ARM 4 — live and scheduled cards are unchanged", () => {
  it("the live soccer card keeps its live price and has no FINAL", () => {
    const card = eventCard(render(soccer, soccer.items.length), belgiumRow.id as number);
    expect(attr(card, "data-state")).toBeNull();
    expect(byTestId(card, "related-card-final")).toHaveLength(0);
    // Italy's live 44% stays. Belgium's served 56% is `1 − home` on a draw-priced sport,
    // withheld since #8702 (this line asserted "56%" until then, which was that defect).
    expect(byTestId(card, "related-card-field")[0]?.text).toMatch(/Belgium.*—.*Italy\s*44%/);
  });

  it("the scheduled football card keeps its current price", () => {
    const scheduled = football.items.find(
      (item) => item.type === "event" && item.data.status === "scheduled",
    )!.data;
    const card = eventCard(render(football, football.items.length), scheduled.id as number);
    expect(byTestId(card, "related-card-final")).toHaveLength(0);
    expect(byTestId(card, "related-card-field")[0]?.text).toMatch(/\d+%.*\d+%/);
  });
});
