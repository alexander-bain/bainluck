import { readFileSync } from "fs";
import { join } from "path";
import { formatProbabilityPercent } from "@/lib/probabilityDisplay";

const source = readFileSync(join(process.cwd(), "../ios/Bain Luck/BainLuckTests/FuturesProbabilityDisplay11616Tests.swift"), "utf8");
const table = source.split("// FUTURES LABEL CASES BEGIN")[1].split("// FUTURES LABEL CASES END")[0];
const rows = [...table.matchAll(/\(([\d.]+), (nil|\d+), "([^"]+)"\)/g)]
  .map(row => [Number(row[1]), row[2] === "nil" ? null : Number(row[2]), row[3]] as const);
test("Native label table covers both boundaries, scalar rounding and field overrides", () => {
  expect(rows).toHaveLength(21);
  expect(rows.filter(row => row[1] !== null)).toHaveLength(7);
});
test.each(rows)("web and Native contract: %s", (probability, override, expected) => {
  expect(formatProbabilityPercent(probability, { rendered: override })).toBe(expected);
});
