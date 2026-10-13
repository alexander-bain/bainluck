// A PROP TILE WHOSE STAT THE BOX SCORE DOES NOT CARRY PRINTS NO NUMBER IT
// CANNOT KNOW — not "NaN%", not "PUSH".
//
// Seen on production 2026-10-13 03:48:50Z, `/events/14780558` (Bills 37–34
// Rams, MNF, Final in overtime), 390px, a page opened 14 s after the final:
// "Bigger Picture · GAME PROPS — LIVE" drew row after row of tiles reading
// `Line: 190+`, a full bar, and `NaN%` (Puka Nacua, Jordan Whittington, Keon
// Coleman, James Cook III …). The related-futures response still said `live`
// while the game-markets props above had not loaded, so the rail drew its own
// stat tiles.
//
// The tile looks its stat up as `CATEGORY_TO_STAT[category] || category`. An
// NFL family such as "Receiving Yards (Protected)" or "Touchdowns (Protected)"
// is not in that map, and the box score has no key by that name, so the
// lookup returns `undefined` — which passed the `!== null` test. Live it then
// divided `undefined` by the line (`NaN%`); finished, `undefined > line` and
// `undefined < line` are both false and the tile printed `PUSH`.
//
// The payload is the real one (`GET /api/events/14780558/related-futures`,
// 04:02Z), reduced to three rows and those players' box-score entries. The
// control is the one in-band row whose family IS mapped ("Receiving Yards",
// Khalil Shakir 80+, box score 80): its tile must keep printing its actual.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import banked from "../fixtures/ux_related_futures_14780558.20261013T0402Z.json";

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});

let payload: Record<string, unknown> = {};
jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({ data: payload, error: undefined, isLoading: false }),
}));
jest.mock("@/lib/api", () => ({
  fetchRelatedFutures: jest.fn(),
  formatProbability: (p: number | null) =>
    p === null || p === undefined ? "--" : `${Math.round(p * 100)}%`,
}));

import RelatedFutures from "@/components/RelatedFutures";

function render(eventStatus: "live" | "completed"): string {
  payload = { ...banked, event_status: eventStatus };
  return renderToStaticMarkup(
    <RelatedFutures
      eventId={14780558}
      homeTeam="Los Angeles Rams"
      awayTeam="Buffalo Bills"
      sportKey="americanfootball_nfl"
      eventStatus={eventStatus}
    />,
  );
}

/** One tile's markup, found by the player name in its label's `title`. */
function tile(html: string, player: string): string {
  const at = html.indexOf(`title="${player}"`);
  if (at === -1) return "";
  const end = html.indexOf("</a>", at);
  return html.slice(at, end);
}

const text = (s: string) => s.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();

describe("a stat the box score does not carry", () => {
  it("live: the tile prints no NaN", () => {
    const html = render("live");
    const puka = tile(html, "Puka Nacua");
    const keon = tile(html, "Keon Coleman");
    expect(puka).not.toBe("");
    expect(keon).not.toBe("");
    expect(puka).not.toContain("NaN");
    expect(keon).not.toContain("NaN");
    expect(html).not.toContain("NaN");
  });

  it("finished: the tile does not call the prop a PUSH", () => {
    const html = render("completed");
    const puka = tile(html, "Puka Nacua");
    const keon = tile(html, "Keon Coleman");
    expect(puka).not.toBe("");
    expect(keon).not.toBe("");
    expect(text(puka)).not.toMatch(/\b(PUSH|OVER|UNDER)\b/);
    expect(text(keon)).not.toMatch(/\b(PUSH|OVER|UNDER)\b/);
  });
});

describe("control: a stat the box score does carry", () => {
  it("live: the tile still prints the actual and its pace", () => {
    const shakir = text(tile(render("live"), "Khalil Shakir"));
    expect(shakir).toContain("Line: 80+");
    expect(shakir).toMatch(/\b80\b.*On pace/);
  });

  it("finished: the tile still prints the actual against the line", () => {
    const shakir = text(tile(render("completed"), "Khalil Shakir"));
    expect(shakir).toContain("Line: 80+");
    expect(shakir).toMatch(/\b80\b/);
    expect(shakir).toMatch(/\b(PUSH|OVER|UNDER)\b/);
  });
});
