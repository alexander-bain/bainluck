// #7949: at phone width the ANSWERS question gets its own full-width line and wraps,
// instead of competing with the answer for ~20 characters of one line.
//
// Production 2026-09-21/25 at 390px: "Wi… ALCS in the 2026 MLB Playoffs — No 76%" (the
// subject truncated away on a mixed Red Sox card) and "Spread: New York … Baltimore
// Orioles 64%" (the -1.5 line, the whole question, cut; a -2.5 card further down read 75%).
//
// This jest setup does logic, not RTL, so it pins the CLASS CONTRACT on comment-stripped
// source, as searchFamilyRowShrinkOrder4518 does (the fix's comment names classes too).

import { readFileSync } from "fs";
import { join } from "path";

const SRC = readFileSync(join(__dirname, "../../components/SearchFamilyCard.tsx"), "utf8");
const CODE = SRC.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

/** The opening tag of the first element whose className contains `needle`. */
const tagWith = (needle: string): string => {
  const at = CODE.indexOf(needle);
  expect(at).toBeGreaterThan(-1);
  const open = CODE.lastIndexOf("<", at);
  return CODE.slice(open, CODE.indexOf(">", at) + 1);
};

describe("#7949 the question wraps on its own line below sm", () => {
  it("NEGATIVE CONTROL: comment prose is stripped", () => {
    expect(SRC).toContain("No split point fixes a line");
    expect(CODE).not.toContain("No split point fixes a line");
  });

  it("the phone title takes the whole row width and WRAPS to two lines, never a one-line truncate", () => {
    const tag = tagWith("sm:hidden basis-full");
    expect(tag).toContain("line-clamp-2");
    expect(tag).toContain("min-w-0");
    expect(tag).not.toMatch(/\btruncate\b/);
  });

  it("the phone title prints head AND tail, the whole question", () => {
    const at = CODE.indexOf("sm:hidden basis-full");
    const body = CODE.slice(at, CODE.indexOf("</div>", at));
    expect(body).toContain("{title.head}");
    expect(body).toContain("{title.tail}");
  });

  it("the one-line head/tail row is desktop only, so a reader never gets both copies", () => {
    expect(tagWith('"flex-1 min-w-0 flex items-center')).toContain("max-sm:hidden");
  });

  it("the row may wrap below sm and stays one line from sm up", () => {
    const tag = tagWith("flex flex-wrap");
    expect(tag).toContain("sm:flex-nowrap");
  });

  it("the answer drops to the second line right-aligned, and gets the full width there", () => {
    const tag = tagWith("min-w-0 max-w-[55%]");
    expect(tag).toContain("ml-auto");
    expect(tag).toContain("max-sm:max-w-full");
  });

  it("the no-price fallback right-aligns the same way", () => {
    const at = CODE.indexOf("market.outcome_count}");
    const open = CODE.lastIndexOf("<span", at);
    expect(CODE.slice(open, at)).toContain("ml-auto");
  });
});
