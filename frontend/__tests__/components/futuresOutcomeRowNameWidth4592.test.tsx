/**
 * #4592 — the futures outcome row still clipped the name, and the year with it.
 *
 * ## What was on production, measured, not eyeballed
 *
 * 2026-09-16, anonymous, 390px, master `e85fa8642`. Read off the layout engine
 * (`scrollWidth` vs `clientWidth` on the name node) rather than off a raster, because
 * an ellipsis is what a clipped node LOOKS like and a node sitting at its track edge
 * looks identical — `.lat452-outcome-name-fit.mjs` and `.lat454-row-budget.mjs`:
 *
 *   | board                          | row | name                | client | needs |
 *   |--------------------------------|-----|---------------------|--------|-------|
 *   | `112854` NATO/EU troops        | 0   | `December 31, 2026` | 92     | 132   |
 *   | `112854`                       | 1   | `June 30, 2026`     | 92     | 94    |
 *   | `112860` Ukraine election      | 0   | `December 31, 2026` | 92     | 132   |
 *   | `25924714` Clarity Act senators| 0   | `Raphael Warnock`   | 92     | 117   |
 *
 * All 3 rows of `112854` clip and all 5 of `112860` clip. `December 31, 2026` prints
 * `December 31, ...` on a board whose entire question is *which year*, with the 2025
 * rung on screen beside it — so the clip eats the answer, not just the polish. This is
 * the FORMATTING pillar's case: the stored `futures_outcomes.name` is complete (this is
 * not #2010 / #2142 / #4087), the column is too narrow.
 *
 * ## Why #3358 did not already cover it
 *
 * #3358 is the same defect on the same row and its change 2 exists to stop exactly
 * this. It is gated on `showLastMove`, and its change 1 had dropped that column on all
 * four boards above — so the arm that re-measures the name against the row was off on
 * precisely the rows still clipping. The budget says the row is not wasting anything:
 * checkbox 20 + rank 32 + name cell 124.3 + numbers 79.7 + three 12px gaps = the 294px
 * content box exactly.
 *
 * The mechanism is `flex-1` = `flex: 1 1 0%`. A zero flex-basis makes the name cell's
 * hypothetical main size 0, and that is the number multi-line flex breaks lines on, so
 * the cell can never push the numbers group onto a second line however long the name
 * is. `flex-auto` = `flex: 1 1 auto` keeps grow and shrink identical and makes the
 * hypothetical size the content — avatar + gap + the full nowrap name — so the row
 * wraps exactly when the name does not fit. Full derivation: the component docstring.
 *
 * ## What this file can and cannot prove
 *
 * Jest here is `testEnvironment: 'node'` with no jsdom, so there is no layout engine:
 * **no assertion below claims a pixel**, for the same reason #3358's file says so. The
 * pixel readings are the rigs' and the 390px production screenshots', in the PR.
 *
 * What is provable is the class contract, and for this defect that is the whole fix —
 * the bug WAS a CSS combination that cannot work (a basis-0 item cannot trigger a wrap)
 * rather than a width that happened not to fit. The population is selected by anchors
 * that predate this diff (`outcome-row`, `outcome-name`, `outcome-numbers`) and by the
 * served strings, never by a marker this diff introduces.
 *
 * Red-first: with `flex-auto` reverted to `flex-1`, **3 of the 10 fail and 7 pass** —
 * the three are `the name cell measures its CONTENT...`, `...so it cannot be basis-0`
 * and `the mechanism survives...`. The seven that pass on both arms are the controls,
 * including the two that pin #3358's own contract, which this diff must NOT move.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { FuturesOutcome } from "@/lib/types";

jest.mock("@/components/EntityImage", () => ({
  __esModule: true,
  default: ({ name }: { name: string }) => <img alt={name} />,
}));

import OutcomeRow from "../../components/futures/OutcomeRow";

/** The rungs `/futures/112854` served while the issue was open, in served order. */
const DATE_RUNGS: Array<[string, number]> = [
  ["December 31, 2026", 0.55],
  ["June 30, 2026", 0.28],
  ["December 31, 2025", 0.17],
];

/** The senator board's rank-1 row, the issue body's own specimen class. */
const SENATORS = ["Raphael Warnock", "Catherine Cortez Masto", "Kirsten Gillibrand"];

function outcome(
  name: string,
  probability: number,
  over: Partial<FuturesOutcome> = {},
): FuturesOutcome {
  return {
    id: name.length + Math.round(probability * 1000),
    name,
    probability,
    opening_probability: 0.19,
    probability_change_24h: null,
    rank_change_24h: null,
    is_winner: null,
    last_updated: "2026-09-16T17:38:00Z",
    ...over,
  } as unknown as FuturesOutcome;
}

/** #3358's tag scanner, same reason: the claims here are relationships, not substrings. */
interface Node {
  tag: string;
  classes: string[];
  attrs: Record<string, string>;
  children: Node[];
  parent: Node | null;
  text: string;
}

const VOID = new Set(["img", "br", "hr", "input", "meta", "link", "path", "circle", "line"]);

function parse(html: string): Node {
  const root: Node = { tag: "#root", classes: [], attrs: {}, children: [], parent: null, text: "" };
  const stack: Node[] = [root];
  const token = /<\/?([a-zA-Z][\w-]*)((?:\s+[\w:-]+(?:="[^"]*")?)*)\s*(\/?)>|([^<]+)/g;
  let m: RegExpExecArray | null;
  while ((m = token.exec(html)) !== null) {
    const [raw, tag, attrText, selfClose, text] = m;
    const top = stack[stack.length - 1];
    if (text !== undefined) {
      const decoded = text
        .replace(/&quot;/g, '"')
        .replace(/&#x27;/g, "'")
        .replace(/&amp;/g, "&");
      for (const n of stack) n.text += decoded;
      continue;
    }
    if (raw.startsWith("</")) {
      if (stack.length > 1) stack.pop();
      continue;
    }
    const attrs: Record<string, string> = {};
    const attrRe = /([\w:-]+)(?:="([^"]*)")?/g;
    let a: RegExpExecArray | null;
    while ((a = attrRe.exec(attrText || "")) !== null) attrs[a[1]] = a[2] ?? "";
    const node: Node = {
      tag,
      classes: (attrs.class || "").split(/\s+/).filter(Boolean),
      attrs,
      children: [],
      parent: top,
      text: "",
    };
    top.children.push(node);
    if (!selfClose && !VOID.has(tag)) stack.push(node);
  }
  return root;
}

function all(root: Node): Node[] {
  const out: Node[] = [];
  const walk = (n: Node) => {
    for (const c of n.children) {
      out.push(c);
      walk(c);
    }
  };
  walk(root);
  return out;
}

function render(
  o: FuturesOutcome,
  opts: { showLastMove?: boolean; showEntityImage?: boolean; rankChange?: number | null } = {},
): Node {
  return parse(
    renderToStaticMarkup(
      <OutcomeRow
        outcome={opts.rankChange === undefined ? o : ({ ...o, rank_change_24h: opts.rankChange } as FuturesOutcome)}
        rank={1}
        isLeader={false}
        isSelected={false}
        onToggleSelect={() => {}}
        hasHistory
        marketCategory="geopolitics"
        marketName="When will NATO/EU troops deploy to Ukraine?"
        isResolved={false}
        showEntityImage={opts.showEntityImage ?? true}
        rendered={null}
        renderedOpening={null}
        showLastMove={opts.showLastMove ?? false}
      />,
    ),
  );
}

/**
 * The cell that holds the picture and the name: the row's only growable child, found
 * by walking UP from the name span rather than by a marker, so the population is the
 * same on both arms of the red-first run.
 */
function nameCell(root: Node): Node {
  const name = all(root).find((n) => n.attrs["data-testid"] === "outcome-name");
  expect(name).toBeDefined();
  let cell = name!.parent;
  while (cell && !cell.classes.includes("flex")) cell = cell.parent;
  expect(cell).not.toBeNull();
  return cell!;
}

describe("#4592 — a row whose name does not fit wraps, instead of cutting the name", () => {
  it("the name cell measures its CONTENT, so a long name can push the numbers to line 2", () => {
    // `flex: 1 1 auto`. The hypothetical main size is the avatar + gap + the full
    // nowrap name, which is the number the flex line break is decided on.
    const cell = nameCell(render(outcome(...DATE_RUNGS[0])));
    expect(cell.classes).toContain("flex-auto");
  });

  it("...so it cannot be `flex-1`, which is basis-0 and measures as nothing", () => {
    // The defect itself, stated as the thing that must never come back. A cell whose
    // hypothetical size is 0 cannot trigger a wrap however long its text is, so every
    // row keeps four columns on one line and the name absorbs the whole shortfall.
    const cell = nameCell(render(outcome(...DATE_RUNGS[0])));
    expect(cell.classes).not.toContain("flex-1");
    expect(cell.classes.filter((c) => /^basis-0$/.test(c))).toEqual([]);
  });

  it("the cell still shrinks and still ellipsises when even a whole line is too small", () => {
    // Why this is `flex-auto` and not a `min-w-[Npx]` floor: a floor clamps the
    // hypothetical size for EVERY row and then refuses to shrink, so a very long name
    // overflows the row instead of truncating. Grow, shrink and min-width are the
    // three parts that keep that from happening, and all three are asserted.
    const cell = nameCell(render(outcome("Democratic Party nominee for President", 0.4)));
    expect(cell.classes).toContain("min-w-0");
    expect(cell.classes).not.toContain("shrink-0");
    expect(cell.classes).not.toContain("grow-0");
  });

  it("the mechanism survives on every rung of the board that clipped, and on the senators", () => {
    // The two populations in the issue: the date rungs (where the clip costs the YEAR)
    // and the wide people-field of the body's own specimen. One class, both arms.
    for (const [name, p] of DATE_RUNGS) {
      const cell = nameCell(render(outcome(name, p)));
      expect(cell.classes).toContain("flex-auto");
      expect(cell.classes).not.toContain("flex-1");
    }
    for (const name of SENATORS) {
      const cell = nameCell(render(outcome(name, 0.3), { rankChange: -2 }));
      expect(cell.classes).toContain("flex-auto");
      expect(cell.classes).not.toContain("flex-1");
    }
  });

  it("CONTROL — the row can still wrap below `sm` and still cannot above it", () => {
    // `flex-auto` on a child does nothing inside a `flex-nowrap` parent: this and the
    // class above are one mechanism, and #3358 owns this half. Neither works alone.
    const row = all(render(outcome(...DATE_RUNGS[0]))).find(
      (n) => n.attrs["data-testid"] === "outcome-row",
    );
    expect(row).toBeDefined();
    expect(row!.classes).toContain("flex-wrap");
    expect(row!.classes).toContain("sm:flex-nowrap");
  });

  it("CONTROL — #3358's contract is untouched: no `Last move` means no forced second line", () => {
    // The density decision #3358 made deliberately. This diff makes the wrap depend on
    // the name's own width, so the common case must still be able to stay on one line;
    // a `basis-full` here would mean every phone row grew, which is what was declined.
    const group = all(render(outcome("Mike Lee", 0.3), { showLastMove: false })).find(
      (n) => n.attrs["data-testid"] === "outcome-numbers",
    );
    expect(group).toBeDefined();
    expect(group!.classes).not.toContain("basis-full");
    expect(group!.classes).toContain("basis-auto");
  });

  it("CONTROL — #3358's other arm is untouched: `Last move` still takes a full line", () => {
    const group = all(render(outcome(...DATE_RUNGS[0]), { showLastMove: true })).find(
      (n) => n.attrs["data-testid"] === "outcome-numbers",
    );
    expect(group).toBeDefined();
    expect(group!.classes).toContain("basis-full");
    expect(group!.classes).toContain("sm:basis-auto");
  });

  it("CONTROL — the name still truncates on its own span and keeps its full title", () => {
    // #4245b's rule: `text-overflow` applies to the box owning the text, so `truncate`
    // on the flex CELL would clip it dead. The cell is the flex box; the span is not.
    const root = render(outcome("Catherine Cortez Masto", 0.44));
    const name = all(root).find((n) => n.attrs["data-testid"] === "outcome-name");
    expect(name!.text).toBe("Catherine Cortez Masto");
    expect(name!.classes).toContain("truncate");
    expect(name!.classes).not.toContain("flex");
    expect(name!.attrs.title).toBe("Catherine Cortez Masto");
    expect(nameCell(root).classes).not.toContain("truncate");
  });

  it("CONTROL — nothing was dropped to buy the width: both numbers and the chart box stay", () => {
    // The directive's preserve list. A width fix that deletes `Open` would pass every
    // assertion above and be a different, unapproved ship.
    const root = render(outcome(...DATE_RUNGS[0]));
    const nodes = all(root);
    expect(nodes.find((n) => n.attrs["data-testid"] === "outcome-open")).toBeDefined();
    expect(root.text).toContain("Open");
    expect(root.text).toContain("Latest");
    expect(nodes.find((n) => n.tag === "button")).toBeDefined();
    expect(nodes.find((n) => n.attrs["data-testid"] === "outcome-rank-badge")).toBeDefined();
  });

  it("CONTROL — the scan is non-empty, so a rename cannot make this file vacuously green", () => {
    const nodes = all(render(outcome(...DATE_RUNGS[0]), { showLastMove: true }));
    expect(nodes.filter((n) => n.attrs["data-testid"]).length).toBeGreaterThan(2);
    expect(nodes.length).toBeGreaterThan(10);
  });
});
