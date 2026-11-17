// #5866 (Direction 199 unified headline) — COMPETITOR IDENTITY MAY SHRINK SO NUMERIC
// COLUMNS NEVER PUSH OFF-SCREEN, AND THE GREY PREGAME SUMMARY NEVER WRAPS.

import fs from "fs";
import path from "path";

const HEADLINE = path.resolve(
  __dirname,
  "../../components/event/EventPageHeadline199.tsx",
);
const PAIR = path.resolve(__dirname, "../../components/EventHeroProbabilityPair.tsx");

function executableSource(file: string): string {
  return fs
    .readFileSync(file, "utf8")
    .replace(/\/\*[\s\S]*?\*\//g, " ")
    .split("\n")
    .map((line) => line.replace(/(^|\s)\/\/.*$/, "$1"))
    .join("\n");
}

describe("#5866 the headline rows bound their text so nothing overflows 390px", () => {
  test("competitor identity stack carries min-w-0 flex-1 and truncates cleanly", () => {
    const code = executableSource(HEADLINE);
    expect(code).toContain(
      'className="flex items-center gap-2 min-w-0 flex-1 max-[359px]:basis-full"',
    );
    expect(code).toContain('className="flex flex-col min-w-0"');
  });

  test("the single grey pregame summary never wraps", () => {
    const code = executableSource(HEADLINE);
    expect(code).toContain(
      'className="text-[12px] leading-tight tabular-nums whitespace-nowrap overflow-hidden text-ellipsis"',
    );
  });

  test("EventHeroProbabilityPair keeps its responsive step-downs", () => {
    const code = executableSource(PAIR);
    const sized = code.match(
      /text-\[34px\] min-\[360px\]:text-\[42px\] min-\[390px\]:text-\[48px\] sm:text-\[52px\]/g,
    );
    expect(sized).toHaveLength(2);
  });
});
