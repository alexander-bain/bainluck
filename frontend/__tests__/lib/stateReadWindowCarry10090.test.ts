/**
 * #10090 — a detail payload that lands AFTER the page's held one, at the SAME
 * price revision, must not put the game back: a fresh read that began before
 * kickoff landing after a `live 0-0` poll, a `7-0` becoming `0-0`. The route
 * now stamps when it read the events row (`state_read_not_before`/`_not_after`,
 * PR #11267); `carryNewerHeldState` keeps the held game state only when that
 * window PROVES it newer, and otherwise changes nothing.
 *
 * Contract: LIVE-STATE-WINDOW-CONSUMER-CONTRACT.md v3 (sha256 ad0b0d74…), §7.
 * Every fixture window uses the producer's exact shape: UTC `isoformat()` with
 * microseconds and a `+00:00` offset.
 */
import {
  HELD_STATE_KEYS, carryNewerHeldState, fetchEventWithLiveFrame, heldStateIsNewer, stateReadWindow,
} from "@/lib/reconcileEventPoll";
import { createWriteJournal, rebaseOnCoveringRead, replayJournaledPoll } from "@/lib/reconcileControl";

const E = 15332323;
const at = (second: number, micro = 0) =>
  `2026-10-19T01:00:${String(second).padStart(2, "0")}.${String(micro).padStart(6, "0")}+00:00`;
const window = (from: number, to: number) => ({ state_read_not_before: at(from), state_read_not_after: at(to) });

type Payload = Record<string, unknown> & { id: number; status: string };
const live = (over: Record<string, unknown> = {}): Payload => ({
  id: E, status: "live", home_score: 0, away_score: 0, completed_at: null,
  commence_time: "2026-10-19T00:15:00Z", started_without_result: false,
  hero_probability: 0.55, hero_probability_away: 0.45, hero_probability_source: "blend",
  hero_probability_observed_at: "2026-10-19T01:00:00Z", blend_fold_revision: { [E]: 10 },
  win_probability_sources: { kalshi: { value: 0.55, updated_at: "2026-10-19T01:00:00Z" } },
  current_odds: { home_ml: -120 }, highlight: { reason: "live" },
  ...over,
});
const scheduled = (over: Record<string, unknown> = {}): Payload => {
  const base = live({ status: "scheduled", home_score: null, away_score: null, ...over });
  delete base.started_without_result;
  return base;
};
const final = (over: Record<string, unknown> = {}): Payload => live({
  status: "completed", home_score: 24, away_score: 17, completed_at: "2026-10-19T03:40:00Z",
  hero_probability: 1, hero_probability_away: 0, hero_probability_source: "settled", hero_settled_result: "home",
  prematch_odds: { home_probability: 0.58 }, ...over,
});

function deepFreeze<T>(value: T): T {
  if (value && typeof value === "object") {
    Object.values(value as object).forEach(deepFreeze);
    Object.freeze(value);
  }
  return value;
}
/** Carry with both inputs frozen: the reconcile never mutates what it was given. */
const carry = (cand: Payload, held: Payload | undefined) =>
  carryNewerHeldState(deepFreeze(cand), held && deepFreeze(held));

describe("§1 order: only a strictly later window proves the held state newer", () => {
  it("parses the producer's microsecond stamps to whole milliseconds", () => {
    expect(stateReadWindow(window(1, 2))).toEqual([Date.parse("2026-10-19T01:00:01Z"), Date.parse("2026-10-19T01:00:02Z")]);
    expect(stateReadWindow({ state_read_not_before: at(1, 999), state_read_not_after: at(1, 1999) }))
      .toEqual([Date.parse("2026-10-19T01:00:01.000Z"), Date.parse("2026-10-19T01:00:01.001Z")]);
  });

  it("a later held window orders; a tie, an overlap or the reverse does not", () => {
    const held = live(window(20, 21));
    expect(heldStateIsNewer(held, scheduled(window(10, 11)))).toBe(true);
    expect(heldStateIsNewer(held, scheduled(window(10, 20)))).toBe(false); // tie: not_before == not_after
    expect(heldStateIsNewer(held, scheduled(window(15, 25)))).toBe(false); // overlap
    expect(heldStateIsNewer(held, scheduled(window(30, 31)))).toBe(false); // candidate newer
  });

  it("a gap smaller than a millisecond is a tie (floor_ms), one millisecond orders", () => {
    const cand = scheduled({ state_read_not_before: at(10), state_read_not_after: at(20, 100) });
    expect(heldStateIsNewer(live({ state_read_not_before: at(20, 900), state_read_not_after: at(21) }), cand)).toBe(false);
    expect(heldStateIsNewer(live({ state_read_not_before: at(20, 1000), state_read_not_after: at(21) }), cand)).toBe(true);
  });

  it.each([
    ["held has no window", live(), scheduled(window(10, 11))],
    ["candidate has no window", live(window(20, 21)), scheduled()],
    ["held has half a window", live({ state_read_not_before: at(20) }), scheduled(window(10, 11))],
    ["candidate has half a window", live(window(20, 21)), scheduled({ state_read_not_after: at(11) })],
    ["held's window is unparseable", live({ state_read_not_before: "soon", state_read_not_after: at(21) }), scheduled(window(10, 11))],
    ["candidate's window is not a string", live(window(20, 21)), scheduled({ state_read_not_before: 10, state_read_not_after: 11 })],
    ["held's window is reversed", live({ state_read_not_before: at(22), state_read_not_after: at(21) }), scheduled(window(10, 11))],
    ["another event", live({ ...window(20, 21), id: E + 1 }), scheduled(window(10, 11))],
  ])("unordered when %s: the candidate is returned untouched", (_name, held, cand) => {
    expect(carry(cand, held)).toBe(cand);
  });

  it("no held payload: the candidate is returned untouched", () => {
    const cand = scheduled(window(10, 11));
    expect(carry(cand, undefined)).toBe(cand);
  });
});

describe("§2 the held game state is carried as one unit; the candidate keeps its price", () => {
  it("X1: a scheduled detail never replaces a held live 0-0 read later at the same revision", () => {
    const out = carry(scheduled(window(10, 11)), live(window(20, 21)));
    expect(out).toMatchObject({ status: "live", home_score: 0, away_score: 0, started_without_result: false });
  });

  it("X2: a held 7-0 read later is never replaced by a 0-0", () => {
    const out = carry(live({ ...window(10, 11), home_score: 0 }), live({ ...window(20, 21), home_score: 7 }));
    expect([out.home_score, out.away_score]).toEqual([7, 0]);
  });

  it("the candidate keeps its price, sources, revision, odds and highlight; the window becomes held's", () => {
    const cand = scheduled({
      ...window(10, 11), hero_probability: 0.61, hero_probability_away: 0.39,
      hero_probability_observed_at: "2026-10-19T01:00:09Z", blend_fold_revision: { [E]: 12 },
      win_probability_sources: { kalshi: { value: 0.61, updated_at: "2026-10-19T01:00:09Z" } },
      current_odds: { home_ml: -150 }, highlight: { reason: "moving" },
    });
    const out = carry(cand, live(window(20, 21)));
    for (const key of ["hero_probability", "hero_probability_away", "hero_probability_observed_at", "hero_probability_source",
      "blend_fold_revision", "win_probability_sources", "current_odds", "highlight"]) {
      expect(out[key]).toEqual(cand[key]);
    }
    expect([out.state_read_not_before, out.state_read_not_after]).toEqual([at(20), at(21)]);
  });

  it("C1 presence: held's not-started flag is copied, a flag held lacks is deleted", () => {
    const held = scheduled({ ...window(20, 21), authority_not_started: true });
    const out = carry(live(window(10, 11)), held);
    expect(out.authority_not_started).toBe(true);
    // The candidate's `started_without_result: false` was computed against a live status held does not have.
    expect("started_without_result" in out).toBe(false);
  });

  it("C1 presence: the score provenance pair, the tennis line score and the box score travel whole", () => {
    const held = live({
      ...window(20, 21), home_score: 7, score_source: "statpal", score_observed_at: "2026-10-19T01:00:19Z",
      linescore: { sets: [[6, 4]] }, box_score_data: { players: [{ name: "A" }], periods: { home: [7] } },
    });
    const cand = live({
      ...window(10, 11), score_source: "espn", score_observed_at: "2026-10-19T01:00:05Z",
      box_score_data: { players: [], periods: { home: [0] } },
    });
    const out = carry(cand, held);
    expect(out).toMatchObject({ score_source: "statpal", score_observed_at: "2026-10-19T01:00:19Z",
      linescore: { sets: [[6, 4]] }, box_score_data: held.box_score_data });
    const bare = carry(live({ ...window(10, 11), score_source: "espn", score_observed_at: "x", linescore: { sets: [] } }),
      live(window(20, 21)));
    expect(["score_source", "score_observed_at", "linescore"].filter((key) => key in bare)).toEqual([]);
  });

  it("C1 nested espn: only period and game_clock are held's; the candidate's ESPN price keys survive", () => {
    const held = live({ ...window(20, 21), espn: { espn_id: "401", period: "Q2", game_clock: "4:12", win_probability: 0.3,
      probability_sources: ["held"], broadcast: "CBS" } });
    const cand = live({ ...window(10, 11), espn: { espn_id: "401", period: "Q1", game_clock: "15:00", win_probability: 0.62,
      probability_sources: ["cand"], broadcast: "FOX" } });
    expect(carry(cand, held).espn).toEqual({ espn_id: "401", period: "Q2", game_clock: "4:12", win_probability: 0.62,
      probability_sources: ["cand"], broadcast: "FOX" });
  });

  it("C1 nested espn: held without espn deletes the two clock keys; a candidate without espn gets ONLY the two", () => {
    const cand = live({ ...window(10, 11), espn: { period: "Q1", game_clock: "15:00", win_probability: 0.62 } });
    expect(carry(cand, live(window(20, 21))).espn).toEqual({ win_probability: 0.62 });
    const half = carry(cand, live({ ...window(20, 21), espn: { period: "Half", win_probability: 0.1 } }));
    expect(half.espn).toEqual({ period: "Half", win_probability: 0.62 });
    const created = carry(live(window(10, 11)), live({ ...window(20, 21), espn: { period: "Q3", game_clock: "9:00",
      win_probability: 0.4, probability_sources: ["held"] } }));
    expect(created.espn).toEqual({ period: "Q3", game_clock: "9:00" });
    expect("espn" in carry(live(window(10, 11)), live({ ...window(20, 21), espn: { win_probability: 0.4 } }))).toBe(false);
  });
});

describe("§3 keys computed from that response's status or start travel with held's status", () => {
  it("C2: a held live read carries no venue grade the candidate computed; held's pin is kept", () => {
    const cand = scheduled({ ...window(10, 11), venue_settled: true, venue_settled_result: "home", venue_closed_no_winner: false });
    const out = carry(cand, live({ ...window(20, 21), live_probability_pinned: { reason: "blowout" } }));
    expect(["venue_settled", "venue_settled_result", "venue_closed_no_winner"].filter((key) => key in out)).toEqual([]);
    expect(out.live_probability_pinned).toEqual({ reason: "blowout" });
    expect("live_probability_pinned" in carry(live({ ...window(10, 11), live_probability_pinned: { reason: "x" } }),
      scheduled(window(20, 21)))).toBe(false);
  });

  it("C2 v3: a held placeholder start stays TBD beside a prematurely-live candidate", () => {
    const out = carry(live({ ...window(10, 11), start_is_tbd: false }), scheduled({ ...window(20, 21), start_is_tbd: true }));
    expect(out).toMatchObject({ status: "scheduled", start_is_tbd: true });
  });

  it("C2 v3: before commence a held scheduled read publishes no opening line the live candidate froze", () => {
    const out = carry(live({ ...window(10, 11), opening_odds: { spread: -3.5, over_under: 44.5 } }), scheduled(window(20, 21)));
    expect(out.status).toBe("scheduled");
    expect("opening_odds" in out).toBe(false);
  });

  it("C2 v3: the start the held flags were computed against is held's", () => {
    const out = carry(live({ ...window(10, 11), commence_time: "2026-10-19T00:15:00Z" }),
      scheduled({ ...window(20, 21), commence_time: "2026-10-19T02:05:00Z", authority_not_started: true }));
    expect(out).toMatchObject({ commence_time: "2026-10-19T02:05:00Z", authority_not_started: true });
  });

  it("every contracted key is in the carried set, and nothing price-shaped is", () => {
    expect([...HELD_STATE_KEYS].sort()).toEqual([
      "authority_not_started", "away_score", "box_score_data", "commence_time", "completed_at", "home_score",
      "linescore", "live_probability_pinned", "opening_odds", "score_observed_at", "score_source",
      "start_is_tbd", "started_without_result", "state_read_not_after", "state_read_not_before", "status",
      "venue_closed_no_winner", "venue_settled", "venue_settled_result",
    ]);
  });
});

describe("§4/§5 finals: a held final is kept whole; a final or newer candidate wins as today", () => {
  it("C3: a held final read later than a live candidate is the result, identical — hero, result and pre-game reading", () => {
    const held = final(window(20, 21));
    const out = carry(live({ ...window(10, 11), blend_fold_revision: { [E]: 30 } }), held);
    expect(out).toBe(held);
    expect(out).toEqual(final(window(20, 21)));
  });

  it("C3 closed counts as final too", () => {
    const held = final({ ...window(20, 21), status: "closed" });
    expect(carry(live(window(10, 11)), held)).toBe(held);
  });

  it("a final candidate older than a held live read is the final owner: returned whole, never spliced", () => {
    const cand = final(window(10, 11));
    expect(carry(cand, live({ ...window(20, 21), home_score: 3 }))).toBe(cand);
  });

  it("a newer-window live candidate after a held final is adopted (a reversal): the order says so", () => {
    const cand = live(window(30, 31));
    expect(carry(cand, final(window(20, 21)))).toBe(cand);
  });

  it("a correction: a newer window with a lower score is adopted", () => {
    const cand = live({ ...window(30, 31), home_score: 0 });
    expect(carry(cand, live({ ...window(20, 21), home_score: 7 }))).toBe(cand);
  });
});

describe("§6 both write sites", () => {
  const frameless = () => null;

  it("the ordinary poll: a stale cached poll (older window) keeps the held fresh read's state (mirror)", async () => {
    const held = live({ ...window(20, 21), home_score: 7 });
    const out = await fetchEventWithLiveFrame(async () => scheduled(window(10, 11)), frameless, frameless, () => held);
    expect(out).toMatchObject({ status: "live", home_score: 7 });
  });

  it("the ordinary poll: held state wins and so does held's newer headline — one coherent live page", async () => {
    const held = live({ ...window(20, 21), blend_fold_revision: { [E]: 12 }, hero_probability: 0.6 });
    const out = await fetchEventWithLiveFrame(
      async () => scheduled({ ...window(10, 11), blend_fold_revision: { [E]: 11 }, hero_probability: 0.5 }),
      frameless, frameless, () => held);
    expect(out).toMatchObject({ status: "live", hero_probability: 0.6, blend_fold_revision: { [E]: 12 } });
  });

  it("the ordinary poll: held is read when the response LANDS, not when it was asked", async () => {
    let held: Payload | undefined = scheduled(window(1, 2));
    let land!: (p: Payload) => void;
    const pending = fetchEventWithLiveFrame(() => new Promise<Payload>((resolve) => { land = resolve; }),
      frameless, frameless, () => held);
    held = live(window(20, 21));
    land(scheduled(window(10, 11)));
    expect((await pending).status).toBe("live");
  });

  it("the ordinary poll: a held final read later is never reopened by a cached live poll", async () => {
    const held = final(window(20, 21));
    const out = await fetchEventWithLiveFrame(async () => live(window(10, 11)), frameless, frameless, () => held);
    expect(out).toEqual(held);
  });

  it("the ordinary poll with no windows anywhere: today's result exactly", async () => {
    const polled = scheduled();
    expect(await fetchEventWithLiveFrame(async () => polled, frameless, frameless, () => live())).toBe(polled);
  });

  it("a journaled poll newer in price but older in state is replayed onto the pair's read with the read's state", () => {
    const read = live({ ...window(30, 31), home_score: 7, blend_fold_revision: { [E]: 12 } });
    const poll = live({ ...window(20, 21), home_score: 0, blend_fold_revision: { [E]: 13 }, hero_probability: 0.63 });
    expect(replayJournaledPoll(poll, read)).toMatchObject({ home_score: 7, hero_probability: 0.63,
      blend_fold_revision: { [E]: 13 }, state_read_not_before: at(30) });
    const journal = createWriteJournal<Payload>();
    journal.record((onto) => replayJournaledPoll(poll, onto));
    expect(rebaseOnCoveringRead(read, journal, live(window(1, 2)))).toMatchObject({ home_score: 7, hero_probability: 0.63 });
  });

  it("a journaled poll with no windows replays exactly as before", () => {
    const poll = live({ blend_fold_revision: { [E]: 13 } });
    expect(replayJournaledPoll(poll, live({ blend_fold_revision: { [E]: 12 } }))).toBe(poll);
  });
});
