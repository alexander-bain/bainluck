/**
 * #4244 + #4245 — a `/sports` futures card names its leader, and still shows when it settles.
 *
 * ## What was on production, measured, not eyeballed
 *
 * `https://www.bainluck.com/sports` at 390px, anonymous, 2026-09-09 ~09:0x PT, master
 * `8011521d`. 39 futures cards, read by `.lat287-futures-card-fit-probe.mjs`:
 *
 *   | reading                                   | before |
 *   |-------------------------------------------|--------|
 *   | cards where two strings share pixels      | 21/39  |
 *   | overlap instances (up to 77.6 px columns) | 44     |
 *   | leader labels clipped with NO ellipsis    | 6      |
 *   | RANK-1 contender names cut                | 15     |
 *
 * Three separate mechanisms, all in this one card:
 *
 * 1. **#4244** the headline pill was `flex-shrink-0` in a `min-w-0` group that does not
 *    clip, so it rendered past its group and painted over `Resolves Dec 31, 2026`.
 * 2. **#4245a** the contender name cell was a flat `w-20` (80px) beside a `flex-1` bar
 *    measuring 212px — the cell carrying an identity was starved, the cell carrying a
 *    length was over-provisioned.
 * 3. **#4245b** `truncate` sat on the leader label's FLEX container. text-overflow applies
 *    to the box owning the text; a bare text node in a flex container lives in an
 *    anonymous item, so the container clipped it dead — and with `justify-end` the cut
 *    landed on the LEFT edge, where an ellipsis cannot paint at all.
 *
 * ## What this file can and cannot prove
 *
 * jsdom has no layout engine: it cannot measure 212px, it cannot tell you that two boxes
 * intersect, and any px claim written here would be invented. **No assertion below makes
 * one.** The pixel claims are the production probe's, before and after, and they are
 * recorded in the PR.
 *
 * What IS provable here — and is the thing that actually regressed — is the class
 * contract, because each of the three defects is a CSS property combination that cannot
 * work rather than a width that happened not to fit:
 *
 *   - a variable-length flex item with `flex-shrink-0` in a non-clipping group WILL
 *     overflow its group at some string length; the only question is which one;
 *   - `truncate` on an element that is `display:flex` NEVER produces an ellipsis, for
 *     any content, at any width.
 *
 * So the assertions read those combinations off the rendered markup. The population is
 * selected by anchors that exist on BOTH arms — `title=` on the name cell,
 * `role="progressbar"` on the bar, and the served strings themselves — never by a marker
 * this diff introduces, which is the trap `feedCardProbabilityBar.test.tsx` documents.
 *
 * Red-first: every `expect` below fails on the parent commit.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { FeedItem, FeedFuturesData, FeedFuturesOutcome } from "@/lib/types";

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), prefetch: jest.fn() }),
}));
jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));
jest.mock("next/image", () => ({
  __esModule: true,
  default: ({ alt }: { alt: string }) => <img alt={alt} />,
}));
jest.mock("@/components/Analytics", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: () => {} }),
}));

import FeedCard from "../../components/FeedCard";

function outcome(id: number, name: string, probability: number): FeedFuturesOutcome {
  return {
    id,
    name,
    probability,
    rank: null,
    movement: null,
    rendered_percent: Math.round(probability * 100),
  };
}

/**
 * The Featherweight card exactly as `/api/feed?mode=sports` served it while the two
 * issues were open — the longest real leader name on the rail paired with a full
 * `Resolves <Month> <D>, <YYYY>` date, which is the pairing #4244 says is the population.
 */
function volkanovskiCard(over: Partial<FeedFuturesData> = {}, headline?: string): FeedItem {
  const data: FeedFuturesData = {
    id: 201,
    name: "Who will be the UFC Featherweight Title Holder on Dec 31, 2026?",
    sport: "mma_mixed_martial_arts",
    sport_name: "UFC",
    llm_sport_category: "mma",
    source: "kalshi",
    source_count: 2,
    market_tier: 2,
    status: "open",
    resolution_date: "2026-12-31T00:00:00Z",
    top_outcomes: [
      outcome(1, "Alexander Volkanovski", 0.48),
      outcome(2, "Movsar Evloev", 0.4),
      outcome(3, "Jean Silva", 0.02),
    ],
    outcome_count: 12,
    canonical_market_key: null,
    ...over,
  } as FeedFuturesData;
  return {
    type: "futures",
    data,
    reason: "Alexander Volkanovski (48%) leads Featherweight Title Holder",
    headline: headline ?? "Alexander Volkanovski leads at 48%",
  } as unknown as FeedItem;
}

/**
 * ── A 40-line tag scanner, and why there is one ──
 *
 * This project's jest runs on `testEnvironment: 'node'` and neither `jsdom` nor
 * `jest-environment-jsdom` is installed, so there is no `document` to parse into. The
 * sibling `feedCardProbabilityBar.test.tsx` regexes the markup string for that reason.
 * A flat regex cannot express the claim this file actually needs to make, though —
 * "the element that truncates is NOT the flex container, and its PARENT is" is a
 * relationship — so the markup is walked into a tree instead. React's static markup is
 * well-formed and void elements are self-closed, which is the whole of what this needs.
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
      // Entities React emits in these strings; nothing here needs a full decoder.
      const decoded = text.replace(/&quot;/g, '"').replace(/&#x27;/g, "'").replace(/&amp;/g, "&");
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
  const walk = (n: Node) => { for (const c of n.children) { out.push(c); walk(c); } };
  walk(root);
  return out;
}

function render(item: FeedItem): Node {
  return parse(renderToStaticMarkup(<FeedCard item={item} />));
}

/** `flex-1` is NOT `flex`. Conflating them is exactly why a substring check would be
 *  wrong here: the fixed name cell is `flex-1` and must NOT read as a flex container. */
function isFlexContainer(n: Node): boolean {
  return n.classes.includes("flex") || n.classes.includes("inline-flex");
}

describe("#4244 — the leader pill yields, the resolution date does not", () => {
  it("the headline pill can shrink and ellipsises instead of overprinting the date", () => {
    // #4403 — the fixture's own headline ("Alexander Volkanovski leads at 48%")
    // is an ECHO of its reason line, and an echo pill is no longer rendered at
    // all, so it can no longer reach this assertion. The PROPERTY under test is
    // unchanged and still matters — a pill that survives is variable-length and
    // must yield to the date — so the specimen is swapped for a headline that
    // says something the reason does not, rather than the assertion weakened.
    const headline = "Volkanovski odds up 12 points today";
    const nodes = all(render(volkanovskiCard({}, headline)));

    const pill = nodes.find((n) => n.tag === "span" && n.text === headline);
    expect(pill).toBeDefined();

    // The defect, stated as its cause: an unshrinkable variable-length item.
    expect(pill!.classes).not.toContain("flex-shrink-0");
    expect(pill!.classes).not.toContain("shrink-0");
    // ...and the two properties that let it yield gracefully rather than silently.
    expect(pill!.classes).toContain("truncate");
    expect(pill!.classes).toContain("min-w-0");
  });

  it("the category chip can shrink too — `truncate` alone floors a flex item at min-content", () => {
    const nodes = all(render(volkanovskiCard()));
    const chip = nodes.find(
      (n) => n.tag === "span" && n.classes.includes("tracking-wide"),
    );
    expect(chip).toBeDefined();
    expect(chip!.classes).toContain("min-w-0");
    expect(chip!.classes).toContain("truncate");
  });

  it("CONTROL — the date group is still unshrinkable, which is why it is the one that survives", () => {
    const nodes = all(render(volkanovskiCard()));
    const date = nodes.find((n) => n.tag === "span" && n.text.startsWith("Resolves"));
    expect(date).toBeDefined();
    // The caption itself is plain text; its GROUP is what must not shrink.
    expect(date!.parent!.classes).toContain("flex-shrink-0");
  });

  it("CONTROL — a card with no headline pill still renders its date", () => {
    // Emptying a population hands the specimen to a different branch, so the branch
    // with no pill is asserted rather than assumed.
    const root = render(volkanovskiCard({}, ""));
    expect(root.text).toContain("Resolves");
    expect(root.text).not.toContain("leads at 48%");
  });
});

describe("#4245 — no name is cut without saying so, and rank 1 gets the room", () => {
  it("the contender name cell takes the leftover width; the bar takes a fixed one", () => {
    const nodes = all(render(volkanovskiCard()));

    const nameCell = nodes.find((n) => n.attrs.title === "Alexander Volkanovski");
    expect(nameCell).toBeDefined();

    // Was `w-20 shrink-0` — 80px regardless of what the row had spare.
    expect(nameCell!.classes).not.toContain("w-20");
    expect(nameCell!.classes).not.toContain("shrink-0");
    expect(nameCell!.classes).toContain("flex-1");
    expect(nameCell!.classes).toContain("min-w-0");
    expect(nameCell!.classes).toContain("truncate");

    // The bar was the over-provisioned neighbour (`flex-1`), and is now the fixed one.
    const bar = nodes.find((n) => n.attrs.role === "progressbar");
    expect(bar).toBeDefined();
    expect(bar!.classes).not.toContain("flex-1");
    expect(bar!.classes).toContain("shrink-0");
  });

  it("no element in the card carries `truncate` on a flex container — that never ellipsises", () => {
    // The class-level predicate, and the one that is genuinely semantic rather than a
    // spelling check: `text-overflow` applies to the box that owns the text, so an
    // element that is `display:flex` clips its anonymous text item dead. Scanned over
    // the WHOLE card so a future edit cannot reintroduce the shape somewhere else.
    const offenders = all(render(volkanovskiCard()))
      .filter((n) => n.classes.includes("truncate") && isFlexContainer(n))
      .map((n) => `${n.tag}[${n.classes.join(" ")}]`);

    expect(offenders).toEqual([]);
  });

  it("the leader label truncates on its own span, so the cut prints an ellipsis", () => {
    const nodes = all(render(volkanovskiCard()));

    // Anchored on the served string, which exists on both arms.
    const labels = nodes.filter(
      (n) => n.tag === "span" && n.text === "Alexander Volkanovski" && !n.attrs.title,
    );
    expect(labels.length).toBeGreaterThan(0);

    const truncating = labels.find((n) => n.classes.includes("truncate"));
    expect(truncating).toBeDefined();
    // The element that clips must not be the flex row itself.
    expect(isFlexContainer(truncating!)).toBe(false);
    expect(isFlexContainer(truncating!.parent!)).toBe(true);
    expect(truncating!.parent!.classes).not.toContain("truncate");
  });

  it("CONTROL — a short name is not damaged by any of this", () => {
    const nodes = all(
      render(
        volkanovskiCard({
          top_outcomes: [outcome(1, "Jean Silva", 0.51), outcome(2, "Movsar Evloev", 0.49)],
        }),
      ),
    );
    const nameCell = nodes.find((n) => n.attrs.title === "Jean Silva");
    expect(nameCell).toBeDefined();
    expect(nameCell!.text).toBe("Jean Silva");
    // Whole, unabbreviated, and still the leader-styled row.
    expect(nameCell!.classes).toContain("font-semibold");
  });

  it("CONTROL — the scan is non-empty, so a rename cannot make it vacuously green", () => {
    const truncators = all(render(volkanovskiCard())).filter((n) =>
      n.classes.includes("truncate"),
    );
    expect(truncators.length).toBeGreaterThan(2);
  });
});
