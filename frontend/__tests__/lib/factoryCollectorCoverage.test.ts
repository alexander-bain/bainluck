import { execFileSync } from "node:child_process";
import path from "node:path";

it("exercises every executable line of the Factory collector", () => {
  const script = path.resolve(__dirname, "../../../scripts/factory/check_coverage.py");
  const result = execFileSync("python3", [script], { encoding: "utf-8", timeout: 10_000 });
  expect(result).toMatch(/Covered all \d+ executable collect\.py lines/);
}, 15_000);
