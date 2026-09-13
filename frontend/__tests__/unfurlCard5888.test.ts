/**
 * THE PICTURE A PASTED LINK UNFURLS WITH (#5888).
 *
 * `shareUnfurl.test.ts` owns the route-level ratchet — WHICH routes ship a card
 * of their own. This owns the decisions inside one: the numbers the card draws,
 * and the two places a card can quietly start disagreeing with the words
 * printed directly beneath it.
 *
 * Every rule here was written against a mutant that survived the ratchet.
 * `fraction: 0` in both share-meta modules, and dropping `barWidth`'s clamp, all
 * passed the suite on 2026-09-13 — a card whose every bar renders empty is not a
 * subtle defect, and nothing caught it.
 */

import {
  UnfurlCard,
  accentFor,
  barWidth,
  clampText,
  DEFAULT_ACCENT,
} from "@/components/og/UnfurlCard";
import {
  buildEventConceptShareCopy,
  eventConceptShareFacts,
  type EventConceptShareSource,
} from "@/lib/eventConceptShareMeta";
import {
  buildTournamentShareCopy,
  tournamentShareFacts,
  type TournamentShareSource,
} from "@/lib/tournamentShareMeta";
import { unresolvedMetadata } from "@/lib/unresolvedShareMeta";

/* ───────────────────────────── the bar ───────────────────────────── */

describe("the bar is drawn from the number, and never reads as empty or full", () => {
  it("tracks the probability across the range", () => {
    expect(barWidth(0.57)).toBe(57);
    expect(barWidth(0.5)).toBe(50);
    expect(barWidth(0.96)).toBe(96);
  });

  it("clamps to 3..97, because certainty and near-certainty are different claims", () => {
    // A 99.5% favourite drawing a full bar says the question is closed.
    expect(barWidth(1)).toBe(97);
    expect(barWidth(0.995)).toBe(97);
    // A 0.4% longshot drawing nothing looks like a rendering fault.
    expect(barWidth(0)).toBe(3);
    expect(barWidth(0.004)).toBe(3);
  });

  it("survives a value that is not a number rather than drawing NaN%", () => {
    expect(barWidth(Number.NaN)).toBe(3);
    expect(barWidth(-1)).toBe(3);
    // Infinity floors rather than fills: the non-finite guard runs before the
    // clamp, and a garbage value should read as "we have nothing" rather than
    // as the most confident bar the card can draw.
    expect(barWidth(Number.POSITIVE_INFINITY)).toBe(3);
  });
});

/* ──────────────── the numbers the card and the words share ──────────────── */

const board = (label: string, rows: [string, number][]): TournamentShareSource["boards"] =>
  [{ label, rows: rows.map(([display_name, probability]) => ({ display_name, probability })) }];

describe("a tournament card draws the same leader the title names", () => {
  const source: TournamentShareSource = {
    title: "US Open 2026",
    subtitle: "Flushing Meadows",
    boards: [
      ...board("Men's Singles", [["Ben Shelton", 0.4255], ["Alexander Zverev", 0.57225]])!,
      ...board("Women's Singles", [["Elena Rybakina", 0.99475]])!,
    ],
  };

  it("carries the RAW probability beside the formatted one", () => {
    // The card needs a bar width. Re-deriving it with
    // `Number.parseFloat("57%") / 100` is the seam where the picture and the
    // sentence drift; the module hands over both, from one value.
    const { leaders } = tournamentShareFacts(source);
    expect(leaders.map((l) => [l.name, l.probability, l.fraction])).toEqual([
      ["Alexander Zverev", "57%", 0.57225],
      ["Elena Rybakina", "99%", 0.99475],
    ]);
  });

  it("the fraction is the value the string was made from, not a re-parse", () => {
    const [zverev] = tournamentShareFacts(source).leaders;
    expect(zverev.fraction).toBe(0.57225);
    expect(zverev.fraction).not.toBe(0.57);
    expect(barWidth(zverev.fraction)).toBe(57);
  });

  it("picks by probability, not arrival order — the card cannot name a different leader than the title", () => {
    // Shelton arrives first and Zverev leads. If the card sorted differently
    // from the copy, one would say 57% Zverev and the other 43% Shelton.
    const { title } = buildTournamentShareCopy(source);
    const { leaders } = tournamentShareFacts(source);
    expect(title).toContain("Alexander Zverev 57%");
    expect(leaders[0].name).toBe("Alexander Zverev");
  });

  it("a board whose leader has no price is dropped from both, not drawn at 0%", () => {
    const unpriced: TournamentShareSource = {
      title: "Some Cup",
      boards: board("Singles", [["Nobody", 0]]),
    };
    expect(tournamentShareFacts(unpriced).leaders).toEqual([]);
    expect(buildTournamentShareCopy(unpriced).title).toBe("Some Cup");
  });
});

const concept = (
  competitors: [string, number, boolean | null][],
  status = "upcoming"
): EventConceptShareSource => ({
  event: { name: "Contender Series: Hunt vs Perea", status },
  primary: {
    label: "Main event",
    competitors: competitors.map(([name, probability, won]) => ({ name, probability, won })),
  },
});

describe("an event-concept card draws what the title claims, including the refusals", () => {
  it("carries the raw probability beside the formatted one", () => {
    const { priced } = eventConceptShareFacts(
      concept([["Zevan Hunt", 0.545, null], ["Mayton Perea", 0.44, null]])
    );
    expect(priced.map((c) => [c.name, c.probability, c.fraction])).toEqual([
      ["Zevan Hunt", "55%", 0.545],
      ["Mayton Perea", "44%", 0.44],
    ]);
    expect(barWidth(priced[0].fraction)).toBe(55);
  });

  it("NEVER infers a winner from a price — the card cannot call a live fight", () => {
    // The reason this module exists: `event:ufc:26sep12` was `live` with its
    // favourite at 0.99. A card that read the winner off the price would have
    // drawn "won" over a fight in progress.
    const live = concept([["Zevan Hunt", 0.99, null], ["Mayton Perea", 0.01, null]], "live");
    const facts = eventConceptShareFacts(live);
    expect(facts.settled).toBe(false);
    expect(facts.winner).toBeNull();
  });

  it("claims a winner only on the authoritative pair, and the copy agrees", () => {
    const settled = concept(
      [["Zevan Hunt", 0.545, true], ["Mayton Perea", 0.44, false]],
      "settled"
    );
    const facts = eventConceptShareFacts(settled);
    expect(facts.settled).toBe(true);
    expect(facts.winner).toBe("Zevan Hunt");
    expect(buildEventConceptShareCopy(settled).title).toContain("Zevan Hunt won");
  });

  it("settled with nothing flagged is Final and no result — in the card as in the words", () => {
    const settled = concept(
      [["Zevan Hunt", 0.545, false], ["Mayton Perea", 0.44, false]],
      "settled"
    );
    const facts = eventConceptShareFacts(settled);
    expect(facts.settled).toBe(true);
    expect(facts.winner).toBeNull();
    expect(buildEventConceptShareCopy(settled).title).toContain("Final");
  });

  it("drops a 0% longshot rather than printing it", () => {
    const { priced } = eventConceptShareFacts(
      concept([["Xavier Becerra", 0.955, null], ["Tom Steyer", 0, null]])
    );
    expect(priced.map((c) => c.name)).toEqual(["Xavier Becerra"]);
  });
});

/* ─────────────────────── the card's own presentation ─────────────────────── */

describe("the card presents what it is handed", () => {
  it("clamps long text instead of letting satori overflow the canvas", () => {
    expect(clampText("US Open 2026", 72)).toBe("US Open 2026");

    // The boundary itself, both sides. A title of EXACTLY the limit fits and
    // must not be cut — `<=` vs `<` here is a mutant that survived the first
    // pass, because every other case in this test sits far from the edge.
    expect(clampText("A".repeat(20), 20)).toBe("A".repeat(20));
    expect(clampText("A".repeat(21), 20)).toBe(`${"A".repeat(19)}…`);

    const long = "A".repeat(100);
    expect(clampText(long, 20)).toHaveLength(20);
    expect(clampText(long, 20).endsWith("…")).toBe(true);
    expect(clampText("  padded  ", 72)).toBe("padded");
  });

  it("colours by the route's own segment, and falls back rather than throwing", () => {
    expect(accentFor("ufc")).toBe(accentFor("mma"));
    expect(accentFor("UFC")).toBe(accentFor("ufc"));
    expect(accentFor("election")).toBe(accentFor("politics"));
    expect(accentFor(null)).toBe(DEFAULT_ACCENT);
    expect(accentFor("a-domain-we-have-never-seen")).toBe(DEFAULT_ACCENT);
  });

  it("carries no emoji — satori resolves one over the network and the route fails, not degrades", () => {
    // Measured 2026-09-13: with 🍀 in the header, every opengraph-image request
    // answered "failed to pipe response / fetch failed … loadAdditionalAsset"
    // and HTTP 000 wherever egress is blocked. Production has egress, so the
    // four older cards are not broken — but this one renders in CI, which is
    // the only reason #5888's before/after could be shot at all.
    const src = UnfurlCard.toString();
    expect(/\p{Extended_Pictographic}/u.test(src)).toBe(false);
  });
});

/* ─────────── a dead link says the same thing in both namespaces ─────────── */

describe("a link that resolves to nothing previews the same in Slack and on X", () => {
  const own = "https://www.bainluck.com/tournaments/nope/opengraph-image";

  it("names the caller's own card in og: AND twitter: when it ships one", () => {
    // #5888. Next's file convention overrides `og:image` and NOT
    // `twitter:image`, so before this a dead link previewed as the route's own
    // card in Slack and as the HOME PAGE on X. Measured on production
    // 2026-09-13 for the sibling routes, which still do this:
    //   /events/99999999  og:image …/events/99999999/opengraph-image?509a39…
    //                     twitter:image https://www.bainluck.com/opengraph-image
    const meta = unresolvedMetadata("/tournaments/nope", "tournament", "not-found", own);
    expect(meta.openGraph?.images).toEqual([
      { url: own, width: 1200, height: 630, alt: "This tournament isn't on Bain Luck" },
    ]);
    expect(meta.twitter?.images).toEqual([own]);
  });

  it("keeps the site card for a caller with no image route of its own", () => {
    // The argument is optional on purpose: on a route with no
    // `opengraph-image.tsx` the site card really is the picture that ships.
    const meta = unresolvedMetadata("/tournaments/nope", "tournament", "not-found");
    expect(meta.twitter?.images).toEqual(["/opengraph-image"]);
    expect(meta.openGraph?.images).toEqual([
      expect.objectContaining({ url: "/opengraph-image" }),
    ]);
  });

  it("still deindexes a real 404 and still does not deindex a bad minute", () => {
    // The image argument must not disturb what #5861 settled.
    expect(
      unresolvedMetadata("/tournaments/nope", "tournament", "not-found", own).robots
    ).toEqual({ index: false, follow: true });
    expect(
      unresolvedMetadata("/tournaments/nope", "tournament", "unavailable", own).robots
    ).toBeUndefined();
  });
});
