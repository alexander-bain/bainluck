/**
 * latency/135 — joining the hub's two halves.
 *
 * The hub asks for `?sections=first` (20 KB gzipped) and then `?sections=rest` (67 KB), because 76%
 * of the 87 KB payload renders nothing until a reader scrolls or taps the Bracket tab. This is the
 * join, and it has exactly two ways to be quietly wrong:
 *
 *  • A SPREAD. `{...first, ...rest}` passes every test written against a fresh pair and is wrong on
 *    the case that always happens — the second fragment carries its own `generated_at`, describing
 *    sections BELOW the fold, and would stamp the reader's live numbers with it.
 *  • AN ASSIGNMENT TO `event_links`. Its two channels arrive in different fragments: `by_matchup`
 *    addresses the day's card (#2568), `by_espn` the finished list (#2693 step 2). Whichever a plain
 *    assignment kept, the other list would go inert — two shipped fixes re-broken by one operator.
 *
 * Both are asserted here in the shape they would really fail in, not as string comparisons.
 */

import { mergeTournamentSections, type TournamentPayload } from "@/lib/tournament";

const FIRST = {
  slug: "us-open",
  title: "US Open 2026",
  subtitle: "Flushing Meadows",
  tournament: "us-open",
  season: "2026",
  register_version: 7,
  register_generated_at: "2026-09-03T21:00:00Z",
  draw_released: true,
  boards: [],
  slate: { matches: [], count: 0 },
  props: [],
  bracket: {},
  broadcasts: [],
  event_links: { by_matchup: { "m-1": 41 }, linked: 1, unresolved: {} },
  render_findings: [],
  generated_at: "2026-09-03T22:00:00Z",
} as unknown as TournamentPayload;

const REST = {
  slug: "us-open",
  generated_at: "2026-09-03T22:00:09Z",
  grids: { "mens-singles": { draw: "mens-singles", rows: [], columns: [] } },
  results: { matches: [{ matchup_key: "espn:1" }], count: 1 },
  event_links: { by_espn: { "184739": 99 }, espn_linked: 1, espn_unresolved: {} },
} as unknown as Partial<TournamentPayload>;

describe("mergeTournamentSections", () => {
  it("brings the second half's sections onto the page", () => {
    const merged = mergeTournamentSections(FIRST, REST);
    expect(merged.grids).toBe(REST.grids);
    expect(merged.results).toBe(REST.results);
  });

  it("keeps everything the first screen already rendered", () => {
    const merged = mergeTournamentSections(FIRST, REST);
    expect(merged.title).toBe("US Open 2026");
    expect(merged.slate).toBe(FIRST.slate);
    expect(merged.boards).toBe(FIRST.boards);
    expect(merged.bracket).toBe(FIRST.bracket);
  });

  it("does NOT restamp the page with the second request's clock", () => {
    // Red against `{...first, ...rest}`. `rest.generated_at` is nine seconds
    // later here because it IS a later request; it describes the grid and the
    // finished list, not the numbers a reader is looking at.
    expect(mergeTournamentSections(FIRST, REST).generated_at).toBe(FIRST.generated_at);
  });

  it("keeps BOTH link channels — the day's card and the finished list", () => {
    // Red against `event_links: rest.event_links` in either direction: one of
    // the two lists on this page would render every row as dead text.
    const links = mergeTournamentSections(FIRST, REST).event_links ?? {};
    expect(links.by_matchup).toEqual({ "m-1": 41 });
    expect(links.by_espn).toEqual({ "184739": 99 });
    expect(links.linked).toBe(1);
    expect(links.espn_linked).toBe(1);
  });

  it("is a no-op when the second half never arrived", () => {
    // The `rest` request failing is not a page failure: the reader keeps the
    // chart, the day's card and every live number on it.
    expect(mergeTournamentSections(FIRST, null)).toBe(FIRST);
    expect(mergeTournamentSections(FIRST, undefined)).toBe(FIRST);
  });

  it("does not mutate either fragment", () => {
    const first = JSON.parse(JSON.stringify(FIRST)) as TournamentPayload;
    const rest = JSON.parse(JSON.stringify(REST)) as Partial<TournamentPayload>;
    mergeTournamentSections(first, rest);
    expect(first.grids).toBeUndefined();
    expect(first.event_links?.by_espn).toBeUndefined();
    expect(rest.slate).toBeUndefined();
  });

  it("survives a first fragment that carries no links at all", () => {
    const bare = { ...FIRST, event_links: undefined } as unknown as TournamentPayload;
    expect(mergeTournamentSections(bare, REST).event_links?.by_espn).toEqual({
      "184739": 99,
    });
  });
});
