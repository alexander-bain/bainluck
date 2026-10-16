/**
 * #11120 — the NFL "Game stories" deck sometimes opened on its second card.
 * The finish card comes from the projection series and can arrive after the
 * prop cards; it is inserted in front of them, and a `snap-mandatory` row
 * re-snaps to the card it already held, so the new lead sat off-screen to the
 * left (production, /events/14780559 at 390px: 2 of 5 fresh loads opened at
 * scrollLeft 331).
 *
 * The browser's re-snap is simulated by setting the row's `scrollLeft` before
 * the lead card arrives. Controls: a reader who has touched the deck keeps
 * their position, and an update that keeps the same lead never moves the row.
 */

import { minimalDom } from "../helpers/minimalDom";
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";

import { NFLEventCardDeck, deckReturnsToStart } from "@/components/event/NFLEventCards";
import { milestoneCards, type FinishCard, type NflEventCard, type NflPropRow } from "@/lib/nflEventCardDeck";

const KICKOFF = Date.UTC(2026, 9, 16, 0, 15, 0);
const MIN = 60_000;
const iso = (offsetMin: number) => new Date(KICKOFF + offsetMin * MIN).toISOString();
const HOME = "Denver Broncos";
const AWAY = "Seattle Seahawks";

const row = (player: string, line: number, p: number, team: "home" | "away"): NflPropRow => ({
  market_name: "Seattle vs Denver: Receiving Yards",
  outcome_name: `${player}: ${line}+`,
  threshold: line,
  over_probability: p,
  source: "kalshi",
  observed_at: iso(-30),
  pregame_mark: p - 0.05,
  player_team: team,
  actual: 84,
  hit: true,
});
const PROPS = [
  ...[39.5, 49.5, 59.5].map((l, i) => row("Jaxon Smith-Njigba", l, [0.85, 0.71, 0.58][i], "away")),
  ...[29.5, 39.5, 49.5].map((l, i) => row("Courtland Sutton", l, [0.7, 0.5, 0.3][i], "home")),
];
const PROP_CARDS = milestoneCards({
  props: PROPS,
  eventStatus: "completed",
  commenceTime: iso(0),
  homeTeam: HOME,
  awayTeam: AWAY,
  nowMs: KICKOFF + 240 * MIN,
});
const FINISH: FinishCard = {
  kind: "finish",
  id: "finish",
  phase: "after",
  pregame: { away: 21.8, home: 18.8, at: KICKOFF - MIN },
  projectedNow: null,
  final: { away: 14, home: 17, at: KICKOFF + 200 * MIN },
};
const TEAMS = { awayName: AWAY, homeName: HOME, awayShort: "Seahawks", homeShort: "Broncos", awayColor: "#002a5c", homeColor: "#fb4f14" };
const noop = () => undefined;

type El = { childNodes: El[]; class?: string; [k: string]: unknown };

function findRow(node: El): El | null {
  if (typeof node.class === "string" && node.class.includes("snap-x")) return node;
  for (const c of node.childNodes ?? []) {
    const hit = findRow(c);
    if (hit) return hit;
  }
  return null;
}

function reactProps(node: El): Record<string, () => void> {
  const key = Object.keys(node).find((k) => k.startsWith("__reactProps$"));
  if (!key) throw new Error("no React props on the row");
  return node[key] as Record<string, () => void>;
}

let host: El;
let root: Root;

function render(cards: NflEventCard[]) {
  act(() =>
    root.render(<NFLEventCardDeck cards={cards} teams={TEAMS} selection={{}} onSelect={noop} onOpen={noop} openerRef={noop} />),
  );
}

beforeEach(() => {
  host = (minimalDom.document as unknown as { createElement: (t: string) => El }).createElement("div");
  (minimalDom.body as unknown as { appendChild: (n: El) => void }).appendChild(host);
  root = createRoot(host as unknown as Element);
});
afterEach(() => act(() => root.unmount()));

describe("#11120 the deck opens on its lead card", () => {
  it("the fixture has two prop cards behind the finish card", () => {
    expect(PROP_CARDS.length).toBe(2);
  });

  it("a finish card arriving after the prop cards returns the untouched row to its start", () => {
    render(PROP_CARDS);
    const row = findRow(host)!;
    expect(row).not.toBeNull();
    row.scrollLeft = 331; // the browser re-snapping to the card it held
    render([FINISH, ...PROP_CARDS]);
    expect(findRow(host)).toBe(row);
    expect(row.scrollLeft).toBe(0);
  });

  it("CONTROL: a reader who has swiped the deck keeps their position", () => {
    render(PROP_CARDS);
    const row = findRow(host)!;
    act(() => reactProps(row).onPointerDown());
    row.scrollLeft = 331;
    render([FINISH, ...PROP_CARDS]);
    expect(row.scrollLeft).toBe(331);
  });

  it("CONTROL: focus inside the deck (Back restoring an Open control) also keeps the position", () => {
    render(PROP_CARDS);
    const row = findRow(host)!;
    act(() => reactProps(row).onFocus());
    row.scrollLeft = 331;
    render([FINISH, ...PROP_CARDS]);
    expect(row.scrollLeft).toBe(331);
  });

  it("CONTROL: an update that keeps the same lead never moves the row", () => {
    render([FINISH, PROP_CARDS[0]]);
    const row = findRow(host)!;
    row.scrollLeft = 331;
    render([FINISH, ...PROP_CARDS]);
    expect(row.scrollLeft).toBe(331);
  });
});

describe("#11120 deckReturnsToStart", () => {
  it("only a changed lead on an untouched deck returns it to the start", () => {
    expect(deckReturnsToStart("prop-a", "finish", false)).toBe(true);
    expect(deckReturnsToStart("prop-a", "finish", true)).toBe(false);
    expect(deckReturnsToStart("finish", "finish", false)).toBe(false);
    expect(deckReturnsToStart(null, "finish", false)).toBe(false);
    expect(deckReturnsToStart("finish", null, false)).toBe(false);
  });
});
