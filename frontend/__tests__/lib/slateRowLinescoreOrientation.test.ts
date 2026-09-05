/**
 * THE SET LINE STAYS POINTED AT THE RIGHT PLAYER (live/063, #2746).
 *
 * The backend states a line in `home`/`away` columns oriented to the `sides`
 * list IT built the row with, and then two consumers re-order those sides:
 *
 *   * `matchListFromSlate` sorts the favourite first — so on every row where
 *     the underdog was served first, the backend's `home` column is now the
 *     row's SECOND side;
 *   * `matchListFromBracket` joins on an ORDER-INSENSITIVE pair key and then
 *     renders the draw's own top/bottom, so about half of all joins adopt the
 *     opposite order.
 *
 * Carrying a positional score across either is an inverted result: a
 * `6-4, 2-1` printed against the player who is losing, on a live card, with
 * nothing anywhere on the page to contradict it. `espn_tennis_anchor.
 * orient_sides` refuses to guess an orientation upstream; re-introducing the
 * guess two layers later would waste that refusal.
 *
 * So the line names the two entities its columns belong to, and these tests go
 * through the REAL `buildMatchList` — not `orientLinescore` alone. A helper
 * that is green while the path every row takes never calls it is the exact
 * shape CERT-913 blocked this ship for once already.
 */
import { formatLinescore, orientLinescore } from "@/lib/linescore";
import { buildMatchList } from "@/lib/matchList";

const GEA = "espn:athlete:5001";
const ZHENG = "espn:athlete:5002";

/** The line as `tournament_slate._linescore_field` publishes it: Gea leads. */
function line(overrides: Record<string, unknown> = {}) {
  return {
    sets: [
      [6, 4],
      [2, 1],
    ],
    home_games: 8,
    away_games: 5,
    home_entity_key: GEA,
    away_entity_key: ZHENG,
    source: "espn",
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
    observed_at: "2026-09-05T21:25:00+00:00",
  };
}

/**
 * A live scoreboard row. `favourite` decides which player the hub sorts first,
 * and the backend's line always leads with Gea — so `favourite: "zheng"` is
 * the served-order-versus-displayed-order case in one flag.
 */
function slateRow(favourite: "gea" | "zheng", overrides: Record<string, unknown> = {}) {
  const geaP = favourite === "gea" ? 0.56 : 0.44;
  return {
    matchup_key: "espn:182775",
    event_id: null,
    draw: "mens-singles",
    draw_label: "Men's Singles",
    round: "R32",
    scheduled_date: "2026-09-05T20:00:00+00:00",
    live_state: "in_progress",
    status_detail: "1st Set",
    coherent: true,
    priced: true,
    linescore: line(),
    sides: [
      side(GEA, "Arthur Gea", geaP),
      side(ZHENG, "Michael Zheng", 1 - geaP),
    ],
    ...overrides,
  } as never;
}

function entryFor(row: unknown) {
  const entries = buildMatchList({ slate: [row] as never, titleChances: {} as never });
  // A dropped row would make every assertion below vacuous.
  expect(entries).toHaveLength(1);
  return entries[0];
}

describe("the hub's live row carries the games it is being played to", () => {
  it("THE SHIP: a live row's line reaches the entry, in the served order", () => {
    const entry = entryFor(slateRow("gea"));

    expect(entry.sides[0].entityKey).toBe(GEA);
    expect(entry.linescore?.sets).toEqual([
      [6, 4],
      [2, 1],
    ]);
    expect(formatLinescore(entry.linescore)).toBe("6-4, 2-1");
  });

  it("THE DEFECT IT AVOIDS: an underdog-first row flips the columns with it", () => {
    // Zheng is the favourite, so the hub sorts him first — while the backend's
    // line still leads with Gea. Unflipped, this row would print `6-4, 2-1`
    // against the man who has won four games.
    const entry = entryFor(slateRow("zheng"));

    expect(entry.sides[0].entityKey).toBe(ZHENG);
    expect(entry.linescore?.home_entity_key).toBe(ZHENG);
    expect(entry.linescore?.sets).toEqual([
      [4, 6],
      [1, 2],
    ]);
    expect(entry.linescore?.home_games).toBe(5);
    expect(entry.linescore?.away_games).toBe(8);
    expect(formatLinescore(entry.linescore)).toBe("4-6, 1-2");
  });

  it("a row the backend sent no line for has none, not a line of zeroes", () => {
    const entry = entryFor(slateRow("gea", { linescore: undefined }));

    expect(entry.linescore).toBeNull();
    expect(formatLinescore(entry.linescore)).toBe("");
  });

  it("a line naming a player who is not on this row is REFUSED, not drawn", () => {
    // The safe direction: a gap is visibly missing, a mis-attributed score is
    // confidently wrong.
    const entry = entryFor(
      slateRow("gea", { linescore: line({ away_entity_key: "espn:athlete:9999" }) }),
    );

    expect(entry.linescore).toBeNull();
  });

  it("a line with no anchors at all is refused — unchecked is not correct", () => {
    const entry = entryFor(
      slateRow("gea", {
        linescore: line({ home_entity_key: null, away_entity_key: null }),
      }),
    );

    expect(entry.linescore).toBeNull();
  });
});

describe("orientLinescore, at the edges the row path cannot reach", () => {
  it("returns the identical object when it already points the right way", () => {
    const original = line();
    expect(orientLinescore(original, GEA, ZHENG)).toBe(original);
  });

  it("refuses when the ROW's own keys are missing", () => {
    expect(orientLinescore(line(), null, ZHENG)).toBeNull();
    expect(orientLinescore(line(), GEA, undefined)).toBeNull();
  });

  it("null and undefined in, null out", () => {
    expect(orientLinescore(null, GEA, ZHENG)).toBeNull();
    expect(orientLinescore(undefined, GEA, ZHENG)).toBeNull();
  });

  it("a flip is total: every column moves or none does", () => {
    const flipped = orientLinescore(line(), ZHENG, GEA);

    expect(flipped).toEqual({
      sets: [
        [4, 6],
        [1, 2],
      ],
      home_games: 5,
      away_games: 8,
      home_entity_key: ZHENG,
      away_entity_key: GEA,
      source: "espn",
    });
  });

  it("flipping twice is the identity, so the flip cannot be half-written", () => {
    const once = orientLinescore(line(), ZHENG, GEA);
    expect(orientLinescore(once, GEA, ZHENG)).toEqual(line());
  });

  it("formats an empty set list as nothing, never as a stray comma", () => {
    expect(formatLinescore(line({ sets: [] }))).toBe("");
    expect(formatLinescore(null)).toBe("");
  });
});
