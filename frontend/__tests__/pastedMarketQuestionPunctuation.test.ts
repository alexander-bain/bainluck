/**
 * CHECK 8 — A PASTED MARKET LINK WHOSE NAME IS A QUESTION.
 *
 * `pastedLinkProbabilityCopy.test.tsx` put the PRICE in the description and is
 * unchanged by this file. It only ever exercised the priced branch, so the two
 * branches that embed `market.name` INSIDE a sentence were never read, and both
 * of them assumed the name was a noun phrase.
 *
 * Most market names are not. Production db-query, 2026-09-13 21:52Z:
 *
 *     status    ends in "?"     count
 *     resolved  true          136,601
 *     resolved  false         859,736
 *     open      true            9,684
 *     open      false          26,714
 *
 * Read off production the same minute, `/futures/60544511` (resolved):
 *
 *   og:title        "77° or above won - Temperature in New York City on
 *                    Sep 3, 2026 at 7pm EDT? | Bain Luck"
 *   og:description  "77° or above won Temperature in New York City on Sep 3,
 *                    2026 at 7pm EDT?. See the full probability board on Bain Luck."
 *
 * Two things wrong in one sentence, and the title is fine in both respects —
 * `futuresTitleText` uses a ` - ` separator, so it never welds the name into a
 * clause. The description did: `?.` is doubled terminal punctuation, and
 * "X won <question>" is not a sentence in English.
 *
 * ═══ WHY THE TWO BRANCHES ARE FIXED DIFFERENTLY ═══
 *
 * Because the shapes demand different things, and both answers are house style
 * rather than new inventions:
 *
 *  - RESOLVED parenthesises the name after the result. `buildBundleShareText`
 *    adopted exactly this for exactly this reason ("a bundle member's name is
 *    very often itself a question ... `"...winner?: J.D. Vance 23%"` is
 *    unreadable"). Parenthesised, the `?` is the market quoting itself and the
 *    sentence's own terminator sits outside it. The winner still LEADS, so
 *    #883 L2-55 / settled-means-settled is untouched.
 *  - The UNPRICED fallback leads with the name, where a trailing `?` is already
 *    correct terminal punctuation, and `endShareSentence` adds the period only
 *    to the names that carry none.
 *
 * ═══ BOTH DIRECTIONS (gotcha #43) ═══
 *
 * The cheap wrong fix is to strip trailing punctuation off the name. That would
 * pass a "no `?.`" assertion and silently rewrite 136,601 markets' own questions
 * into statements — the venue's wording, not ours. So every question case here
 * asserts the `?` SURVIVES as well as that it is not doubled, and every
 * noun-phrase case asserts the period is still ADDED. A fix that deletes
 * terminators fails this file; so does the unfixed code.
 */

import { generateMetadata as futuresMetadata } from "@/app/futures/[id]/layout";
import { endShareSentence } from "@/lib/share";

function respondWith(body: unknown) {
  global.fetch = jest.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => body,
  }) as unknown as typeof fetch;
}

async function descriptionFor(market: Record<string, unknown>): Promise<string> {
  respondWith(market);
  const meta = await futuresMetadata({ params: Promise.resolve({ id: "60544511" }) });
  return String(meta.description ?? "");
}

/** The NYC temperature market, shaped as `/api/futures/{id}` serves it. */
function resolvedQuestionMarket(overrides: Record<string, unknown> = {}) {
  return {
    id: 60544511,
    name: "Temperature in New York City on Sep 3, 2026 at 7pm EDT?",
    status: "resolved",
    outcomes: [
      { name: "77° or above", probability: 1, is_winner: true },
      { name: "Below 77°", probability: 0, is_winner: false },
    ],
    ...overrides,
  };
}

/** A resolved market whose name is a noun phrase — the other half of the split. */
function resolvedNounMarket(overrides: Record<string, unknown> = {}) {
  return resolvedQuestionMarket({
    id: 60393473,
    name: "Amgen Irish Open - Winner",
    outcomes: [
      { name: "Shane Lowry", probability: 1, is_winner: true },
      { name: "Rory McIlroy", probability: 0, is_winner: false },
    ],
    ...overrides,
  });
}

/**
 * A market with no priced outcome at all — the third branch.
 *
 * `formatShareProbability` returns null for 0 and for absent, so an outcome list
 * of unpriced names reaches the fallback exactly as an empty one does.
 */
function unpricedMarket(name: string) {
  return { id: 112921, name, status: "open", outcomes: [] };
}

/** Terminal punctuation immediately followed by a period — the reported defect. */
const DOUBLED_TERMINATOR = /[?!]\./;

describe("endShareSentence", () => {
  it("adds the period a noun-phrase name does not carry", () => {
    expect(endShareSentence("Amgen Irish Open - Winner")).toBe("Amgen Irish Open - Winner.");
  });

  it("leaves a question's own mark alone rather than appending to it", () => {
    expect(endShareSentence("Will China invade Taiwan by end of 2026?")).toBe(
      "Will China invade Taiwan by end of 2026?",
    );
  });

  it("never STRIPS a terminator — the market's question stays a question", () => {
    // The cheap wrong fix. If this ever returns a statement, 136,601 resolved
    // markets get their own wording edited by us.
    expect(endShareSentence("Rain in Dallas in Sep 2026?")).toContain("?");
    expect(endShareSentence("Really!")).toBe("Really!");
    expect(endShareSentence("Already done.")).toBe("Already done.");
  });

  it("does not double a period either, and trims", () => {
    expect(endShareSentence("  Settled.  ")).toBe("Settled.");
  });
});

describe("a resolved market whose name is a question", () => {
  it("never prints doubled terminal punctuation", async () => {
    const description = await descriptionFor(resolvedQuestionMarket());
    expect(description).not.toMatch(DOUBLED_TERMINATOR);
  });

  it("keeps the market's own question mark", async () => {
    // Direction two: not fixed by deleting the `?`.
    const description = await descriptionFor(resolvedQuestionMarket());
    expect(description).toContain("7pm EDT?");
  });

  it("still leads with the winner — settled means settled", async () => {
    const description = await descriptionFor(resolvedQuestionMarket());
    expect(description.startsWith("77° or above won")).toBe(true);
  });

  it("parenthesises the name so the question sits inside our sentence", async () => {
    const description = await descriptionFor(resolvedQuestionMarket());
    const open = description.indexOf("(");
    const close = description.indexOf(")");
    expect(open).toBeGreaterThan(0);
    expect(close).toBeGreaterThan(open);
    // Positional, not a frozen string: the name is INSIDE the parentheses and
    // the sentence's own terminator is outside them.
    expect(description.slice(open + 1, close)).toBe(
      "Temperature in New York City on Sep 3, 2026 at 7pm EDT?",
    );
    expect(description.charAt(close + 1)).toBe(".");
  });

  it("still sends the reader to the board", async () => {
    const description = await descriptionFor(resolvedQuestionMarket());
    expect(description).toContain("See the full probability board on Bain Luck.");
  });
});

describe("a resolved market whose name is a noun phrase", () => {
  it("still names the winner first and terminates the sentence", async () => {
    const description = await descriptionFor(resolvedNounMarket());
    expect(description.startsWith("Shane Lowry won")).toBe(true);
    expect(description).toContain("(Amgen Irish Open - Winner).");
    expect(description).not.toMatch(DOUBLED_TERMINATOR);
  });
});

describe("an unpriced market falls back without mangling its name", () => {
  it("leads with a question and lets the question mark end the clause", async () => {
    const name = "Will China invade Taiwan by end of 2026?";
    const description = await descriptionFor(unpricedMarket(name));
    expect(description.startsWith(name)).toBe(true);
    expect(description).not.toMatch(DOUBLED_TERMINATOR);
    // The old copy welded the name mid-sentence: "See <question>? translated
    // into ...". Nothing may precede the name now.
    expect(description.indexOf(name)).toBe(0);
  });

  it("supplies the period a noun-phrase name is missing", async () => {
    const description = await descriptionFor(unpricedMarket("Amgen Irish Open - Winner"));
    expect(description.startsWith("Amgen Irish Open - Winner.")).toBe(true);
  });
});

describe("the priced branch is untouched", () => {
  // This file must not be able to pass by breaking the half that already works.
  it("still states the board and never mentions the market name", async () => {
    const description = await descriptionFor({
      id: 109952,
      name: "Brazil Presidential election winner?",
      status: "open",
      outcomes: [
        { name: "Flávio Bolsonaro", probability: 0.52 },
        { name: "Luiz Inácio Lula da Silva", probability: 0.48 },
      ],
    });
    expect(description.startsWith("Flávio Bolsonaro 52%")).toBe(true);
    expect(description).toContain("Luiz Inácio Lula da Silva 48%");
    expect(description).not.toContain("Brazil Presidential election winner");
    expect(description).not.toMatch(DOUBLED_TERMINATOR);
  });
});
