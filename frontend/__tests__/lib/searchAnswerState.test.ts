/**
 * #2239 — "no results" is a claim about the world. The search page was making it
 * from requests it had abandoned.
 *
 * `/api/events/search` sheds stages when its 20,000 ms deadline runs out and
 * declares which ones in `degraded`. The backend is explicit about why
 * (`routes/events.py`, at the payload site): "A stage we could not complete must
 * be distinguishable from a stage that honestly found nothing."
 *
 * It was distinguishable on the wire and nowhere else. `SearchResponse` did not
 * carry the field, so `app/search/page.tsx` saw four empty arrays and rendered
 * "No results for X — we couldn't find any teams, games, or markets matching
 * that." A sentence that tells a person the thing does not exist, on the
 * strength of a request that gave up.
 *
 * This is ruling 025 clause 4's distinction, on the one surface that never got
 * it — `lib/leaguePageChrome.ts` has carried it for the league page since
 * UX-P062: "one says 'nothing is happening', the other says 'we failed to look'".
 */

import { searchAnswerState } from "@/lib/searchAnswerState";

const NOTHING = {
  hasEvents: false,
  hasFutures: false,
  hasTeams: false,
  hasEventConcepts: false,
};

describe("searchAnswerState", () => {
  it("calls a shed-everything answer degraded, not empty", () => {
    // THE REGRESSION THIS EXISTS FOR. Every section empty *because* every stage
    // was cut short — the exact payload the route emits when the deadline is spent.
    expect(
      searchAnswerState({ ...NOTHING, degraded: ["events", "futures", "teams"] }),
    ).toBe("degraded");
  });

  it("calls a genuinely empty answer empty", () => {
    // Fails closed. If a complete miss started reading as degraded, every
    // nonsense query would get an outage message and the honest zero-state
    // (with its suggestions and did-you-mean) would be unreachable.
    expect(searchAnswerState({ ...NOTHING })).toBe("empty");
  });

  it.each([
    ["absent", undefined],
    ["null", null],
    ["an empty list", []],
  ])("treats %s degraded as a complete answer", (_label, degraded) => {
    // `degraded` is additive — the route omits the key entirely on a full
    // answer. An empty list must not turn every ordinary miss into an outage.
    expect(searchAnswerState({ ...NOTHING, degraded })).toBe("empty");
  });

  it.each([
    ["events", ["events"]],
    ["event_count", ["event_count"]],
    ["futures", ["futures"]],
    ["did_you_mean", ["did_you_mean"]],
  ])("treats a shed %s stage as degraded when nothing else answered", (_label, degraded) => {
    // The route appends to `degraded` at five sites. None of them is a lesser
    // kind of incomplete when the result is a blank page.
    expect(searchAnswerState({ ...NOTHING, degraded })).toBe("degraded");
  });

  it.each([
    ["events", { hasEvents: true }],
    ["futures", { hasFutures: true }],
    ["teams", { hasTeams: true }],
    ["event concepts", { hasEventConcepts: true }],
  ])("renders normally when %s answered, even if a stage was shed", (_label, present) => {
    // Deliberate, and the narrower half of the fix. A partial answer still shows
    // what it has — the page is only lying when it asserts ABSENCE. Content on
    // screen is not an absence claim, so it is not this bug.
    expect(
      searchAnswerState({ ...NOTHING, ...present, degraded: ["futures"] }),
    ).toBe("present");
  });

  it("never reports degraded for an answer that has content", () => {
    expect(
      searchAnswerState({
        hasEvents: true,
        hasFutures: true,
        hasTeams: true,
        hasEventConcepts: true,
        degraded: ["events", "futures", "teams", "event_count"],
      }),
    ).toBe("present");
  });
});
