/**
 * A SCOREBOARD SLATE ROW OPENS (ux/1048).
 *
 * ═══ WHAT THIS CLOSES ═══
 *
 * ux/1033 made today's matches appear: `build_slate` now walks the ESPN order
 * of play, so a second-round match reaches a card the draw-ceremony register
 * could never have held. Replayed over the live scoreboard 2026-09-03T20:16Z it
 * produced **40 rows, 8 in play** — and all 40 carried `event_id: null`.
 *
 * The backend half is `apply_espn_event_links` (guarded in
 * `backend/tests/test_tournament_slate_event_links_1048.py`). This is the other
 * end of the same wire: that a row carrying the stamp actually becomes an
 * `href`, through the real `buildMatchList` → `matchEventHref` path the page
 * uses, rather than through a component that happens to read the field.
 *
 * ═══ WHY THE FALLBACK IS NOT ENOUGH, WHICH IS THE POINT ═══
 *
 * `matchEventHref` falls back to the published `by_matchup` map. That map is
 * keyed by REGISTER matchup keys and a scoreboard row's key is
 * `espn:<competition id>`, so the fallback cannot fire for these rows — which
 * is exactly why the server stamp had to exist. `test_the_fallback_cannot_save
 * _a_scoreboard_row` pins that, so nobody deletes the backend half believing
 * the client already covers it.
 */
import { buildMatchList } from "@/lib/matchList";
import { matchEventHref } from "@/lib/matchList";

/** ESPN competition 182709 is `events` row 15299856 — ARTIFACT-M-20260903-A. */
const REAL_COMP = "182709";
const REAL_EVENT = 15299856;

/** A scoreboard row in the shape `authority_match_row` publishes. */
function scoreboardRow(overrides: Record<string, unknown> = {}) {
  return {
    matchup_key: `espn:${REAL_COMP}`,
    event_id: null,
    draw: "mens-singles",
    draw_label: "Men's Singles",
    round: "R64",
    scheduled_date: "2026-09-03T18:10:00+00:00",
    live_state: "in_progress",
    status_detail: "3rd Set",
    coherent: true,
    priced: true,
    sides: [
      side("espn:athlete:1", "Alejandro Tabilo", 0.44),
      side("espn:athlete:2", "Alexei Popyrin", 0.56),
    ],
    ...overrides,
  } as never;
}

function side(entityKey: string, displayName: string, probability: number) {
  return {
    entity_key: entityKey,
    display_name: displayName,
    seed: null,
    image: null,
    probability,
    opening_probability: probability,
    move: null,
    liquidity: null,
    liquidity_reasons: null,
    observed_at: "2026-09-03T20:10:00+00:00",
  };
}

function entryFor(row: unknown) {
  const entries = buildMatchList({ slate: [row] as never, titleChances: {} as never });
  // A `buildMatchList` that silently dropped the row would make every
  // assertion below vacuous — `matchEventHref(undefined)` throws rather than
  // returning null, but a future refactor could make it forgiving.
  expect(entries).toHaveLength(1);
  return entries[0];
}

describe("a scoreboard slate row reaches its match page", () => {
  it("THE SHIP: a stamped live row becomes a link to its event", () => {
    const entry = entryFor(scoreboardRow({ event_id: REAL_EVENT }));
    expect(entry.eventId).toBe(REAL_EVENT);
    expect(matchEventHref(entry, {})).toBe(`/events/${REAL_EVENT}`);
  });

  it("THE DEFECT: the same row unstamped has nowhere to go", () => {
    // The measured 2026-09-03T20:16Z state: 40 rows, 0 links. Kept as a test so
    // the null case stays a KNOWN dead end rather than an unnoticed one.
    const entry = entryFor(scoreboardRow());
    expect(entry.eventId).toBeNull();
    expect(matchEventHref(entry, {})).toBeNull();
  });

  it("the fallback cannot save a scoreboard row, which is why the stamp exists", () => {
    // `by_matchup` is keyed by REGISTER matchup keys. Even a fully populated
    // map cannot answer for `espn:182709`.
    const entry = entryFor(scoreboardRow());
    const byMatchup = {
      "mens-singles:alejandro-tabilo-vs-alexei-popyrin:2026-09-03": REAL_EVENT,
    };
    expect(matchEventHref(entry, byMatchup as never)).toBeNull();
  });

  it("a zero or negative stamp is not a link", () => {
    // `/events/0` is a 404 dressed as a working row.
    for (const bad of [0, -1]) {
      const entry = entryFor(scoreboardRow({ event_id: bad }));
      expect(matchEventHref(entry, {})).toBeNull();
    }
  });
});
