/**
 * #8280 — a settled game board's hero names the side that won, not the first
 * graded totals line.
 *
 * Specimen: production `GET /api/futures/114108` (Kings vs. Blue Jackets,
 * Polymarket, `market_type: "field"`, `mutually_exclusive: false`), outcomes in
 * served order. The hero read "O/U 5.5 WON"; the Kings won the game.
 */
import {
  gradedWinner,
  isLineOrPropLeg,
  pickHeroOutcome,
} from "@/lib/futuresDetailDisplay";

type Row = { id: number; name: string; is_winner: boolean | null; probability: number };

const SPECIMEN_114108: Row[] = [
  { id: 1632397, name: "O/U 5.5", is_winner: true, probability: 0.9995 },
  { id: 1632396, name: "O/U 6.5", is_winner: true, probability: 0.9995 },
  { id: 1632399, name: "Kings", is_winner: true, probability: 0.9995 },
  { id: 1632398, name: "Spread -1.5", is_winner: false, probability: 0.0005 },
  { id: 1632400, name: "Spread -1.5", is_winner: false, probability: 0.0005 },
];

const leaderOf = (rows: Row[]) =>
  [...rows].sort((a, b) => (b.probability ?? 0) - (a.probability ?? 0))[0];

describe("#8280 the specimen", () => {
  it("features the Kings, not the first graded totals line", () => {
    const hero = pickHeroOutcome(SPECIMEN_114108, leaderOf(SPECIMEN_114108), true, false);
    expect(hero?.id).toBe(1632399);
  });

  it("crowns the Kings through gradedWinner, the path the unfurl title and settled line use", () => {
    const champ = gradedWinner(
      SPECIMEN_114108,
      leaderOf(SPECIMEN_114108),
      "resolved",
      "field",
      false,
    );
    expect(champ?.id).toBe(1632399);
  });
});

describe("#8280 what the rule must not move", () => {
  it("a board whose graded rows are all lines still features the first one (no withholding)", () => {
    const rows: Row[] = [
      { id: 1, name: "Burnley FC vs. Brentford FC: O/U 1.5", is_winner: true, probability: 1 },
      { id: 2, name: "Burnley FC vs. Brentford FC: Both Teams to Score", is_winner: true, probability: 1 },
      { id: 3, name: "Burnley FC vs. Brentford FC: O/U 2.5", is_winner: true, probability: 1 },
    ];
    expect(pickHeroOutcome(rows, leaderOf(rows), true)?.id).toBe(1);
  });

  it("never promotes an UNGRADED side over a graded line", () => {
    const rows: Row[] = [
      { id: 1, name: "O/U 5.5", is_winner: true, probability: 0.9995 },
      { id: 2, name: "Kings", is_winner: false, probability: 0.0005 },
      { id: 3, name: "Blue Jackets", is_winner: null, probability: 0.5 },
    ];
    expect(pickHeroOutcome(rows, leaderOf(rows), true)?.id).toBe(1);
  });

  it("a threshold ladder keeps its loosest graded rung (#6032)", () => {
    const rows: Row[] = [
      { id: 1, name: "77° or above", is_winner: true, probability: 1 },
      { id: 2, name: "78° or above", is_winner: true, probability: 1 },
      { id: 3, name: "82° or above", is_winner: true, probability: 1 },
    ];
    expect(pickHeroOutcome(rows, leaderOf(rows), true)?.id).toBe(1);
  });

  it("a board with nothing graded still falls back to the leader", () => {
    const rows: Row[] = [
      { id: 1, name: "Kings", is_winner: false, probability: 0.2 },
      { id: 2, name: "O/U 5.5", is_winner: false, probability: 0.7 },
    ];
    expect(pickHeroOutcome(rows, leaderOf(rows), true)?.id).toBe(2);
  });

  it("a live board is untouched — the preference is a settled-board rule", () => {
    const rows: Row[] = [
      { id: 1, name: "O/U 5.5", is_winner: null, probability: 0.8 },
      { id: 2, name: "Kings", is_winner: null, probability: 0.6 },
    ];
    expect(pickHeroOutcome(rows, leaderOf(rows), false)?.id).toBe(1);
  });
});

describe("#8280 isLineOrPropLeg over the shapes production serves", () => {
  it.each([
    "O/U 5.5",
    "Clippers vs. Lakers: O/U 223.5",
    "1H O/U 108.5",
    "Luka Dončić: Points O/U 30.5",
    "O/U 1.5 Rounds",
    "Spread -1.5",
    "Spread: Nashville SC (-2.5)",
    "1H Spread: Lakers (-3.5)",
    "Rayo Vallecano de Madrid (-1.5)",
    "Both Teams to Score",
    "Gil Vicente FC vs. Sport Lisboa e Benfica: Both Teams to Sco",
    "Fight won by KO/TKO?",
    "Green vs. Zellhuber",
    "Over 5.5",
  ])("%s is a line or prop", (name) => {
    expect(isLineOrPropLeg(name)).toBe(true);
  });

  it.each([
    "Kings",
    "Southern Illinois Salukis",
    "Coastal Carolina Chanticleers",
    "Maple Leafs",
    "77° or above",
    "Yes",
    "No",
    "Tadej Pogacar",
  ])("%s names a side", (name) => {
    expect(isLineOrPropLeg(name)).toBe(false);
  });
});
