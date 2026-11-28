import fs from "fs";
import path from "path";

import { fullGuess, fullPoints, isValidGuess, pointsFor } from "@/lib/guess/engine";
import type { PackCard } from "@/lib/guess/types";

interface ParityCase {
  name: string;
  card: PackCard;
  guess: number;
  valid: boolean;
  full_guess: number;
  full_points: number;
  points: number;
}

describe("Shared scoring parity fixture (server <-> website)", () => {
  const fixturePath = path.resolve(
    __dirname,
    "..",
    "..",
    "..",
    "backend",
    "data",
    "guess",
    "scoring_parity_cases.json",
  );
  const raw = JSON.parse(fs.readFileSync(fixturePath, "utf8")) as { cases: ParityCase[] };

  it("matches every shared case in scoring_parity_cases.json", () => {
    expect(raw.cases.length).toBeGreaterThanOrEqual(12);
    for (const c of raw.cases) {
      expect({ name: c.name, valid: isValidGuess(c.card, c.guess) }).toEqual({
        name: c.name,
        valid: c.valid,
      });
      expect({ name: c.name, fullGuess: fullGuess(c.card) }).toEqual({
        name: c.name,
        fullGuess: c.full_guess,
      });
      expect({ name: c.name, fullPoints: fullPoints(c.card) }).toEqual({
        name: c.name,
        fullPoints: c.full_points,
      });
      expect({ name: c.name, points: pointsFor(c.card, c.guess) }).toEqual({
        name: c.name,
        points: c.points,
      });
    }
  });
});
