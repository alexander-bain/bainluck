/**
 * #3358 — the "All Outcomes" row printed `Pe…` where a contender's name goes.
 *
 * ## What was on production, measured, not eyeballed
 *
 * `https://bainluck.com/futures/202` (UFC Bantamweight Title Holder) at 390px,
 * anonymous, 2026-09-09 ~15:05 PT, master `7996dc51`. Nine rows, and the name column
 * on every one of them:
 *
 *   | row | printed | actual name          |
 *   |-----|---------|----------------------|
 *   | 1   | `Pe…`   | Petr Yan             |
 *   | 2   | `Me…`   | Merab Dvalishvili    |
 *   | 3   | `Se…`   | Sean O'Malley        |
 *   | 4   | `So…`   | Song Yadong          |
 *   | 5-9 | `F` `D` `L` `C` and one blank — the rows carrying a rank-change arrow |
 *
 * Alex filed the same thing on `/futures/112996` (Brazil Presidential Election) two
 * days earlier and confirmed it still live on 9/8: `Lu…`, `Flá…`, `Re…`, `Mic…`.
 * Screenshot: `artifacts-live-124/AFTER-4246-bantamweight-390.png`.
 *
 * The mechanism is arithmetic, and it is why this is a layout-allocation bug and not
 * a genuine space shortage. At 390px the row has ~294px of content box and the items
 * that are NOT the name take ~268px of it: checkbox 20 + rank badge 32 + `Open` ~34 +
 * a fixed **`w-20`** `Last move` 80 + `Latest` ~42 + five 12px gaps. The name is
 * `flex-1 min-w-0`, so it takes the remainder — ~26px — and ~10px once a row also
 * carries a rank-change arrow. Both readings match what the page painted.
 *
 * ## What this file can and cannot prove
 *
 * This project's jest runs on `testEnvironment: 'node'` with no jsdom, so there is no
 * layout engine here: it cannot measure 26px and it cannot tell you two boxes
 * intersect. **No assertion below claims a pixel.** The pixel readings are the
 * production screenshots', before and after, and they are in the PR.
 *
 * What IS provable — and is the thing that regressed — is the class contract, because
 * each half of the defect is a CSS combination that cannot work rather than a width
 * that happened not to fit:
 *
 *   - a `w-20 shrink-0` column that renders `–` on every row of a table takes 80px
 *     from the only column carrying an identity, at every viewport, forever;
 *   - a single-line flex row whose fixed children already exceed the viewport starves
 *     its one `flex-1` child no matter what that child's content is.
 *
 * So the assertions read those combinations off the rendered markup, and the
 * population is selected by anchors present on BOTH arms — `data-testid` values that
 * predate this diff (`outcome-row`, `outcome-open`, `outcome-change`) and the served
 * strings themselves — never by a marker this diff introduces. That is the trap
 * `feedCardProbabilityBar.test.tsx` and the #4244/#4245 file both document.
 *
 * Red-first, measured rather than asserted: with the parent's layout properties put
 * back into this component (single-line row, `basis-auto` group, the `w-20` column
 * rendered unconditionally, no `title` on the name), **4 of the 13 fail and 9 pass**
 * — 13 green after. The four are the load-bearing ones, and they are named here so
 * nobody has to re-derive which:
 *
 *   1. `...so no row renders the 80px cell, and the label is nowhere in the markup`
 *   2. `the numeric group takes a full line below sm when it carries Last move`
 *   3. `the row can wrap below sm and cannot wrap above it`
 *   4. `the name still truncates on its own span, so a cut prints an ellipsis`
 *
 * The nine that pass on BOTH arms are the controls and the predicate cases, and that
 * is what a control is for: `outcomeRowPrintsMove` is new code but states a rule the
 * old row already followed, so a control over it SHOULD be green on both sides. A
 * file where everything reds is a file whose controls are not controls.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { FuturesOutcome } from "@/lib/types";

jest.mock("@/components/EntityImage", () => ({
  __esModule: true,
  default: ({ name }: { name: string }) => <img alt={name} />,
}));

import OutcomeRow, { outcomeRowPrintsMove } from "../../components/futures/OutcomeRow";

/** The nine rows `/futures/202` served while the issue was open. */
const BANTAMWEIGHT: Array<[string, number, number | null]> = [
  ["Petr Yan", 0.535, null],
  ["Merab Dvalishvili", 0.405, null],
  ["Sean O'Malley", 0.035, null],
  ["Song Yadong", 0.015, null],
  ["Umar Nurmagomedov", 0.01, 3],
  ["Payton Talbott", 0.01, -1],
  ["Cory Sandhagen", 0.01, -1],
  ["Deiveson Figueiredo", 0.01, null],
  ["Marlon Vera", 0.01, -1],
];

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
    last_updated: "2026-09-09T21:47:54Z",
    ...over,
  } as unknown as FuturesOutcome;
}

/**
 * ── The tag scanner, and why there is one ──
 *
 * Same reason as `futuresCardFitsAt390_4244_4245.test.tsx`: no jsdom, and the claims
 * here are relationships ("the numeric group is the element that takes a full line",
 * "no `Last move` cell exists anywhere in the row") rather than substrings, so the
 * markup is walked into a tree rather than regexed.
 */
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
    const node: Node = { tag, classes: (attrs.class || "").split(/\s+/).filter(Boolean), attrs, children: [], parent: top, text: "" };
    top.children.push(node);
    if (!selfClose && !VOID.has(tag)) stack.push(node);
  }
  return root;
}

function all(root: Node): Node[] {
  const out: Node[] = [];
  const walk = (n: Node) => { for (const c of n.children) { out.push(c); walk(c); } };
  walk(root);
  return out;
}

function render(
  o: FuturesOutcome,
  opts: { showLastMove: boolean; isResolved?: boolean; rankChange?: number | null } = {
    showLastMove: false,
  },
): Node {
  return parse(
    renderToStaticMarkup(
      <OutcomeRow
        outcome={o}
        rank={1}
        isLeader={false}
        isSelected={false}
        onToggleSelect={() => {}}
        hasHistory
        marketCategory="mma"
        marketName="Bantamweight Title Holder on Dec 31, 2026?"
        isResolved={opts.isResolved ?? false}
        rendered={null}
        renderedOpening={null}
        showLastMove={opts.showLastMove}
      />,
    ),
  );
}

/** The whole-table decision, exactly as `/futures/[id]/page.tsx` makes it. */
function tableShowsLastMove(outcomes: FuturesOutcome[], isResolved = false): boolean {
  return outcomes.some((o) => outcomeRowPrintsMove(o, isResolved));
}

const bantamweight = BANTAMWEIGHT.map(([name, p, rc]) =>
  outcome(name, p, { rank_change_24h: rc }),
);

describe("#3358 — an empty `Last move` column buys no width", () => {
  it("the table `/futures/202` served asks for no `Last move` column at all", () => {
    // The defect's own population: nine rows, not one of them with a move to print.
    expect(tableShowsLastMove(bantamweight)).toBe(false);
  });

  it("...so no row renders the 80px cell, and the label is nowhere in the markup", () => {
    const root = render(bantamweight[0], { showLastMove: false });
    const nodes = all(root);

    // The 80px column, by the class that made it 80px.
    expect(nodes.filter((n) => n.classes.includes("w-20"))).toEqual([]);
    // And by the label a reader would see. Read as a whole string, not a substring:
    // the sort control above the table is a different element in a different file.
    expect(root.text).not.toContain("Last move");
    // The dash it printed nine times is gone with it.
    expect(nodes.find((n) => n.attrs["data-testid"] === "outcome-change")).toBeUndefined();
  });

  it("CONTROL — the other two numbers are untouched; only the empty column left", () => {
    const root = render(bantamweight[0], { showLastMove: false });
    const nodes = all(root);
    // UX-P233 labelled all three deliberately. Dropping a LABEL was never the fix.
    expect(nodes.find((n) => n.attrs["data-testid"] === "outcome-open")).toBeDefined();
    expect(root.text).toContain("Open");
    expect(root.text).toContain("Latest");
  });

  it("CONTROL — one real move anywhere in the table brings the column back for EVERY row", () => {
    const withMove = bantamweight.map((o, i) =>
      i === 2 ? ({ ...o, probability_change_24h: 0.041 } as FuturesOutcome) : o,
    );
    expect(tableShowsLastMove(withMove)).toBe(true);

    // ...including on the rows that have nothing to say, which still print the dash.
    const quiet = render(withMove[0], { showLastMove: true });
    expect(all(quiet).find((n) => n.classes.includes("w-20"))).toBeDefined();
    expect(quiet.text).toContain("Last move");

    const mover = render(withMove[2], { showLastMove: true });
    expect(all(mover).find((n) => n.attrs["data-testid"] === "outcome-change")).toBeDefined();
  });

  it("CONTROL — a move too small to print is not a move, so it does not resurrect the column", () => {
    // UX-P275's rule, inherited rather than re-stated: the gate is whether it PRINTS.
    const rounding = bantamweight.map((o, i) =>
      i === 0 ? ({ ...o, probability_change_24h: 0.00004 } as FuturesOutcome) : o,
    );
    expect(tableShowsLastMove(rounding)).toBe(false);
  });

  it("CONTROL — a settled row prints its result, never a movement", () => {
    const settled = [
      outcome("Petr Yan", 1, { is_winner: true, probability_change_24h: 0.2 }),
      outcome("Merab Dvalishvili", 0, { is_winner: false, probability_change_24h: -0.2 }),
    ];
    expect(tableShowsLastMove(settled, true)).toBe(false);
  });
});

describe("#3358 — the name is measured against the row, not against the leftovers", () => {
  it("the numeric group takes a full line below `sm` when it carries `Last move`", () => {
    // This is the half that holds when the column CANNOT be dropped. One line at
    // 390px cannot seat four columns and a name; two lines can, and nothing is lost.
    const group = all(render(bantamweight[0], { showLastMove: true })).find(
      (n) => n.attrs["data-testid"] === "outcome-numbers",
    );
    expect(group).toBeDefined();
    expect(group!.classes).toContain("basis-full");
    // ...and gives the line straight back on a viewport that has the room.
    expect(group!.classes).toContain("sm:basis-auto");
  });

  it("the row can wrap below `sm` and cannot wrap above it", () => {
    const row = all(render(bantamweight[0], { showLastMove: true })).find(
      (n) => n.attrs["data-testid"] === "outcome-row",
    );
    expect(row).toBeDefined();
    // `basis-full` on a child does nothing at all inside a `flex-nowrap` parent —
    // the two classes are one mechanism and neither works alone.
    expect(row!.classes).toContain("flex-wrap");
    expect(row!.classes).toContain("sm:flex-nowrap");
  });

  it("with no `Last move` column the row stays on ONE line — the common case is not made taller", () => {
    const group = all(render(bantamweight[0], { showLastMove: false })).find(
      (n) => n.attrs["data-testid"] === "outcome-numbers",
    );
    expect(group).toBeDefined();
    expect(group!.classes).not.toContain("basis-full");
    expect(group!.classes).toContain("basis-auto");
  });

  it("the name still truncates on its own span, so a cut prints an ellipsis", () => {
    // #4245b's rule, which this diff must not undo: `text-overflow` applies to the
    // box owning the text, so `truncate` on the flex container clips it dead.
    const nodes = all(render(bantamweight[1], { showLastMove: false }));
    const name = nodes.find((n) => n.attrs["data-testid"] === "outcome-name");
    expect(name).toBeDefined();
    expect(name!.text).toBe("Merab Dvalishvili");
    expect(name!.classes).toContain("truncate");
    expect(name!.classes).not.toContain("flex");
    // ...and the full string is reachable even when it does cut.
    expect(name!.attrs.title).toBe("Merab Dvalishvili");
  });

  it("CONTROL — no element in the row carries `truncate` on a flex container", () => {
    const offenders = all(render(bantamweight[0], { showLastMove: true }))
      .filter(
        (n) =>
          n.classes.includes("truncate") &&
          (n.classes.includes("flex") || n.classes.includes("inline-flex")),
      )
      .map((n) => `${n.tag}[${n.classes.join(" ")}]`);
    expect(offenders).toEqual([]);
  });

  it("CONTROL — the rank-change arrow rows, which printed a SINGLE letter, render the whole name", () => {
    // Rows 5-9 on production. The arrow is an extra fixed child plus an extra gap,
    // which is the difference between `So…` and `S`.
    const arrowed = bantamweight.filter((o) => o.rank_change_24h);
    expect(arrowed.length).toBeGreaterThan(2);
    for (const o of arrowed) {
      const name = all(render(o, { showLastMove: false })).find(
        (n) => n.attrs["data-testid"] === "outcome-name",
      );
      expect(name!.text).toBe(o.name);
    }
  });

  it("CONTROL — the scan is non-empty, so a rename cannot make this file vacuously green", () => {
    const nodes = all(render(bantamweight[0], { showLastMove: true }));
    expect(nodes.filter((n) => n.attrs["data-testid"]).length).toBeGreaterThan(2);
    expect(nodes.length).toBeGreaterThan(10);
  });
});
