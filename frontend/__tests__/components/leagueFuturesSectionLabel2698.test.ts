/**
 * #2698 follow-up `2698-LEAGUE-FUTURES-FRONTEND-LABEL-GUARD` — the grid-less
 * league page keeps calling its title section "Tournament Winners", above the
 * matchups.
 *
 * ═══ WHY THIS SECTION HAS NO OTHER GUARD ═══
 *
 * #2698 gave 15 grid-less leagues (tennis, boxing, MMA, F1, NASCAR, esports…) a
 * `futures` section carrying the tournament's title market — during the US Open,
 * "US Open Men's Singles Winner" on `/sport/tennis/atp`. The backend half is
 * covered by `backend/tests/integration/test_league_tournament_winners_2698.py`.
 * The frontend half is two values in one object literal:
 *
 *     SECTION_META.futures = { label: "Tournament Winners", order: -1 }
 *
 * and BOTH fail silently.
 *
 *   * Delete the entry and the heading falls through to `?? sectionKey` and
 *     prints the raw string **"futures"** to the reader. No error, no test.
 *   * Change the order and the title sinks below "Upcoming Matches" — on those
 *     pages this section IS the grid, so "who wins the US Open" belongs in the
 *     slot the grid occupies everywhere else.
 *
 * ═══ ⚠️ WHY THE OBVIOUS TEST IS THE WRONG ONE, AND WHY THIS FILE PARSES ═══
 *
 * The tempting guard is `expect(source).toContain("Tournament Winners")`. It is
 * worthless HERE specifically: the entry ships with a six-line comment that
 * explains itself, and that comment contains the string. Delete the code and
 * keep the comment — the ordinary shape of a bad merge — and a substring test
 * stays green over a page printing "futures". The label being quoted in prose
 * two lines above the value is exactly the trap.
 *
 * So this reads the page's real TypeScript AST and pulls the values out of the
 * `SECTION_META` initializer. Comments are not nodes; only shipped code answers.
 *
 * The page cannot be rendered instead: it loads through `useEffect` +
 * `fetchLeagueMarkets`, which `renderToStaticMarkup` never runs (this suite is
 * `testEnvironment: 'node'` and the repo has no jsdom), so a render arm would
 * photograph the loading state. The AST is the honest instrument available.
 *
 * ═══ THE ORDER ARM IS RELATIVE, NOT LITERAL ═══
 *
 * It asserts `futures` sorts strictly FIRST among every key in the map, rather
 * than `order === -1`. The page sorts by `SECTION_META[k]?.order ?? 99`, so what
 * a reader gets is the ranking, not the number; pinning -1 alone would pass a
 * change that moved every OTHER section to -2. A guard should fail when the
 * rendered order changes and not when a constant is renumbered.
 */

import { readFileSync } from "fs";
import { join } from "path";
import * as ts from "typescript";

const PAGE = join(__dirname, "..", "..", "app", "sport", "[sport]", "[league]", "page.tsx");

type SectionMeta = { label: string; order: number };

/**
 * The `SECTION_META` object literal as the compiler sees it.
 *
 * Throws rather than returning empty on every miss. A parser helper that
 * degrades to `{}` turns "the constant was renamed or deleted" — the single
 * most likely regression — into a vacuous pass over an empty map.
 */
function readSectionMeta(): Record<string, SectionMeta> {
  const source = ts.createSourceFile(
    PAGE,
    readFileSync(PAGE, "utf8"),
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TSX,
  );

  let initializer: ts.ObjectLiteralExpression | undefined;
  const visit = (node: ts.Node): void => {
    if (
      ts.isVariableDeclaration(node) &&
      ts.isIdentifier(node.name) &&
      node.name.text === "SECTION_META" &&
      node.initializer &&
      ts.isObjectLiteralExpression(node.initializer)
    ) {
      initializer = node.initializer;
    }
    ts.forEachChild(node, visit);
  };
  visit(source);

  if (!initializer) {
    throw new Error(
      `SECTION_META object literal not found in ${PAGE}. If it was renamed or ` +
        `moved, this guard must move with it — do not delete it.`,
    );
  }

  const out: Record<string, SectionMeta> = {};
  for (const prop of initializer.properties) {
    if (!ts.isPropertyAssignment(prop)) continue;
    const key = ts.isIdentifier(prop.name)
      ? prop.name.text
      : ts.isStringLiteral(prop.name)
        ? prop.name.text
        : undefined;
    if (!key || !ts.isObjectLiteralExpression(prop.initializer)) continue;

    let label: string | undefined;
    let order: number | undefined;
    for (const field of prop.initializer.properties) {
      if (!ts.isPropertyAssignment(field) || !ts.isIdentifier(field.name)) continue;
      if (field.name.text === "label" && ts.isStringLiteral(field.initializer)) {
        label = field.initializer.text;
      }
      if (field.name.text === "order") {
        // `order: -1` is a PrefixUnaryExpression, not a NumericLiteral. Reading
        // only numeric literals would silently skip the one entry this file
        // exists for and leave the map looking well-formed.
        const init = field.initializer;
        if (ts.isNumericLiteral(init)) {
          order = Number(init.text);
        } else if (
          ts.isPrefixUnaryExpression(init) &&
          init.operator === ts.SyntaxKind.MinusToken &&
          ts.isNumericLiteral(init.operand)
        ) {
          order = -Number(init.operand.text);
        }
      }
    }
    if (label !== undefined && order !== undefined) out[key] = { label, order };
  }
  return out;
}

describe("#2698 — the grid-less league page's Tournament Winners section", () => {
  const meta = readSectionMeta();

  it("parses a real map, so the assertions below are not vacuous", () => {
    // The positive control. Every other test here reads `meta.futures`; if the
    // parser silently produced `{}` those would fail confusingly rather than
    // pointing at the parse. `matches` is the neighbour the ordering is against.
    expect(Object.keys(meta).length).toBeGreaterThanOrEqual(5);
    expect(meta.matches).toBeDefined();
  });

  it("labels the section 'Tournament Winners' and not the raw key", () => {
    expect(meta.futures).toBeDefined();
    expect(meta.futures.label).toBe("Tournament Winners");
  });

  it("sorts the title above every other section on the page", () => {
    // The page: `.sort(([a], [b]) => (SECTION_META[a]?.order ?? 99) - (...))`.
    const others = Object.entries(meta).filter(([key]) => key !== "futures");
    expect(others.length).toBeGreaterThan(0);
    for (const [key, { order }] of others) {
      // `key` in the message so a failure names the section that overtook it.
      expect([key, meta.futures.order < order]).toEqual([key, true]);
    }
  });

  it("agrees with the hub, which labels the same key", () => {
    // `/hub/[competition]` renders the same `futures` key for the same markets.
    // Two surfaces naming one thing differently is the bug UX-P167 (#2167)
    // already paid for once on these hubs.
    const hub = join(__dirname, "..", "..", "app", "hub", "[competition]", "page.tsx");
    const hubSource = readFileSync(hub, "utf8");
    expect(hubSource).toContain(`futures: { label: "${meta.futures.label}"`);
  });
});
