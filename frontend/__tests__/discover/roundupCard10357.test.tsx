/**
 * #10357 — the round-up card ("NFL division front-runners"), pinned against
 * Fable's R4 reference fixture (`roundupCardFixtureR4.json`, copied verbatim
 * from fable-nfl-division-roundup-design-20261006-r4/roundup-card-fixture-r4.json)
 * and Alex's Oct 6 rulings:
 *
 *   rows highest first · whole percents via the product formatter · blue bars ·
 *   the ruled footer · the whole card opens its container · no container or an
 *   unreadable row = no card · age: all-old → one footer mark, some-old → per
 *   row, exactly six hours → none.
 *
 * The fixture's numbers are Oct 6 venue prices kept as fixed test content; the
 * served card carries the blend, which this card never computes.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fixture from "../fixtures/roundupCardFixtureR4.json";
import { buildRoundupCardModel } from "@/lib/discover/roundupCard";
import type { FeedBundleData, FeedItem, FeedRoundupContract, FeedThemeCollectionRef } from "@/lib/types";

jest.mock("next/link", () => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const R = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) =>
      R.createElement("a", { href, ...rest }, children),
  };
});
jest.mock("next/navigation", () => ({ useRouter: () => ({ push: () => {}, replace: () => {}, prefetch: () => {} }) }));
jest.mock("@/components/Analytics", () => ({ useAnalyticsContext: () => ({ track: () => {} }) }));
jest.mock("@/lib/analytics", () => ({ trackEvent: () => {} }));

import DiscoverCard from "@/components/DiscoverCard";
import { RoundupCard } from "@/components/discover/roundup/RoundupCard";

type FixtureCard = (typeof fixture.cards)[number];
const NOW_MS = Date.parse(fixture.age.now);
const FRESH = "2026-10-06T21:30:00Z";
const FOOTER = fixture.footers.only;
const COLLECTION: FeedThemeCollectionRef = { slug: "nfl-division-front-runners-2026-10-06", name: "NFL division front-runners", revision: 1, collection_count: 4 };

function contractFor(card: FixtureCard, observed?: (string | null)[]): FeedRoundupContract {
  return {
    kicker: "Round-up",
    tag: card.tag,
    footer: FOOTER,
    rows: card.rows.map((r, i) => ({
      market_id: 53670 + i + 1,
      label: r.label,
      probability: r.percent / 100,
      rendered_percent: r.percent,
      observed_at: observed ? observed[i] : FRESH,
    })),
  };
}
const card = (id: string) => fixture.cards.find((c) => c.id === id)!;
const ageCase = (id: string) => fixture.age.cases.find((c) => c.id === id)!;

function render(contract: FeedRoundupContract | null, opts: { title?: string; ref?: FeedThemeCollectionRef | null } = {}) {
  return renderToStaticMarkup(
    <RoundupCard
      title={opts.title ?? "NFL division front-runners"}
      contract={contract}
      collectionRef={opts.ref === undefined ? COLLECTION : opts.ref}
      items={[]}
      bundleId="roundup:nfl-division-front-runners"
      nowMs={NOW_MS}
    />,
  );
}
const stripTags = (html: string) => {
  let out = "";
  let inTag = false;
  for (const ch of html) {
    if (ch === "<") inTag = true;
    else if (ch === ">") { inTag = false; out += " "; }
    else if (!inTag) out += ch;
  }
  return out.replace(/\s+/g, " ").trim();
};
const rowLabels = (html: string) =>
  [...html.matchAll(/data-testid="roundup-row-label"[^>]*>([^<]*)</g)].map((m) => m[1]);
const marks = (html: string) =>
  [...html.matchAll(/data-testid="price-age-mark" data-scope="(row|card)"[\s\S]*?<span class="text-\[10px\][^"]*">([^<]*)</g)].map((m) => `${m[1]}:${m[2]}`);

describe("#10357 round-up model", () => {
  it("THE CANONICAL CARD: four rows, highest first, whole percents, the ruled footer", () => {
    const { model } = buildRoundupCardModel("NFL division front-runners", contractFor(card("canonical")), NOW_MS);
    expect(model!.rows.map((r) => `${r.digits}% ${r.label}`)).toEqual([
      "44% NFC East: Cowboys",
      "41% NFC West: 49ers",
      "38% NFC North: Vikings",
      "35% NFC South: Falcons",
    ]);
    expect(model!.footer).toBe("Bain Luck blend · the 4 closest of 8 divisions");
    expect(model!.kicker).toBe("Round-up");
    expect(model!.tag).toBe("NFL");
  });

  it("re-sorts a served order that is not highest first (the order is a ruling)", () => {
    const c = contractFor(card("canonical"));
    c.rows = [c.rows[3], c.rows[1], c.rows[0], c.rows[2]];
    const { model } = buildRoundupCardModel("NFL division front-runners", c, NOW_MS);
    expect(model!.rows.map((r) => r.digits)).toEqual(["44", "41", "38", "35"]);
  });

  it("uses the product formatter: 99.7% prints >99, 0.4% prints <1", () => {
    const c = contractFor(card("extremes"));
    c.rows[0] = { ...c.rows[0], probability: 0.997, rendered_percent: null };
    c.rows[3] = { ...c.rows[3], probability: 0.004, rendered_percent: null };
    const { model } = buildRoundupCardModel("NFL division front-runners", c, NOW_MS);
    expect(`${model!.rows[0].marker}${model!.rows[0].digits}`).toBe(">99");
    expect(`${model!.rows[3].marker}${model!.rows[3].digits}`).toBe("<1");
  });

  it("drops the headline to its long size over 44 characters", () => {
    expect(buildRoundupCardModel(card("long").headline, contractFor(card("long")), NOW_MS).model!.longHeadline).toBe(true);
    expect(buildRoundupCardModel("NFL division front-runners", contractFor(card("canonical")), NOW_MS).model!.longHeadline).toBe(false);
  });

  describe("all-or-nothing: an unreadable contract is no card", () => {
    const base = () => contractFor(card("canonical"));
    it.each([
      ["no contract", null, "no_contract"],
      ["no footer", { ...base(), footer: " " }, "no_footer"],
      ["no kicker", { ...base(), kicker: "" }, "no_kicker"],
      ["two rows", { ...base(), rows: base().rows.slice(0, 2) }, "row_count"],
      ["five rows", { ...base(), rows: [...base().rows, { ...base().rows[0], market_id: 99 }] }, "row_count"],
      ["a row with no number", { ...base(), rows: base().rows.map((r, i) => (i === 2 ? { ...r, probability: NaN } : r)) }, "bad_row"],
      ["a row with no label", { ...base(), rows: base().rows.map((r, i) => (i === 1 ? { ...r, label: "" } : r)) }, "bad_row"],
      ["the same market twice", { ...base(), rows: base().rows.map((r, i) => (i === 1 ? { ...r, market_id: base().rows[0].market_id } : r)) }, "duplicate_market"],
    ])("%s", (_name, contract, refusal) => {
      const res = buildRoundupCardModel("NFL division front-runners", contract as FeedRoundupContract | null, NOW_MS);
      expect(res.model).toBeNull();
      expect(res.refusal).toBe(refusal);
    });
  });

  describe("age, from R4's three fixture cases (now = 2026-10-06T21:41Z, six-hour futures rule)", () => {
    it("old: every row 7–8h old → one footer mark with the oldest age, no row marks", () => {
      const { model } = buildRoundupCardModel("NFL division front-runners", contractFor(card("canonical"), ageCase("old").observed_at), NOW_MS);
      expect(model!.cardMarkObservedAt).toBe(ageCase("old").observed_at[0]);
      expect(model!.rows.every((r) => !r.rowMark)).toBe(true);
    });
    it("mixed: one row a day old → that row marked, the footer not", () => {
      const { model } = buildRoundupCardModel("NFL division front-runners", contractFor(card("canonical"), ageCase("mixed").observed_at), NOW_MS);
      expect(model!.cardMarkObservedAt).toBeNull();
      expect(model!.rows.map((r) => r.rowMark)).toEqual([false, false, true, false]);
    });
    it("edge: exactly six hours is not old → no mark anywhere", () => {
      const { model } = buildRoundupCardModel("NFL division front-runners", contractFor(card("canonical"), ageCase("edge").observed_at), NOW_MS);
      expect(model!.cardMarkObservedAt).toBeNull();
      expect(model!.rows.some((r) => r.rowMark)).toBe(false);
    });
    it("an undatable row is not old, and does not make an all-old card", () => {
      const observed = [...ageCase("old").observed_at] as (string | null)[];
      observed[1] = null;
      const { model } = buildRoundupCardModel("NFL division front-runners", contractFor(card("canonical"), observed), NOW_MS);
      expect(model!.cardMarkObservedAt).toBeNull();
      expect(model!.rows.map((r) => r.rowMark)).toEqual([true, false, true, true]);
    });
  });
});

describe("#10357 round-up card render", () => {
  it("draws kicker, tag, headline, four rows in order and the footer — in that order", () => {
    const html = render(contractFor(card("canonical")));
    const text = stripTags(html);
    expect(text).toBe(
      "Round-up NFL NFL division front-runners 44 % NFC East: Cowboys 41 % NFC West: 49ers 38 % NFC North: Vikings 35 % NFC South: Falcons Bain Luck blend · the 4 closest of 8 divisions",
    );
    expect(rowLabels(html)).toEqual(["NFC East: Cowboys", "NFC West: 49ers", "NFC North: Vikings", "NFC South: Falcons"]);
  });

  it("the whole card is ONE link, to the served container; rows are not links", () => {
    const html = render(contractFor(card("canonical")));
    const anchors = [...html.matchAll(/<a /g)];
    expect(anchors).toHaveLength(1);
    expect(html).toMatch(/<a href="\/collections\/nfl-division-front-runners-2026-10-06"[^>]*data-testid="roundup-card"/);
  });

  it("bars are blue (--series-1) and sized by the probability", () => {
    const html = render(contractFor(card("canonical")));
    const bars = [...html.matchAll(/<i class="([^"]*)" style="width:([^"]*)" data-testid="roundup-row-bar"/g)];
    expect(bars.map((b) => b[2])).toEqual(["44%", "41%", "38%", "35%"]);
    for (const b of bars) {
      expect(b[1]).toContain("bg-[var(--series-1)]");
      expect(b[1]).not.toMatch(/accent-brand|green|emerald/);
    }
  });

  it("the tag uses the new --text-secondary-strong ink; no tag, no pill", () => {
    expect(render(contractFor(card("canonical")))).toMatch(/text-text-secondary-strong"[^>]*data-testid="roundup-tag">NFL</);
    expect(render(contractFor(card("extremes")))).not.toContain('data-testid="roundup-tag"');
  });

  it("nothing inside the card but text and bars: no images, svgs or emoji", () => {
    const html = render(contractFor(card("canonical")));
    const inside = html.slice(html.indexOf('data-testid="roundup-card"'), html.indexOf("</a>"));
    expect(inside).not.toMatch(/<img|<svg/);
    expect(stripTags(inside)).not.toMatch(/\p{Extended_Pictographic}/u);
  });

  it("never says 'question' and names no venue", () => {
    const text = stripTags(render(contractFor(card("canonical"))));
    expect(text).not.toMatch(/question/i);
    expect(text).not.toMatch(/Kalshi|Polymarket|sportsbook/i);
  });

  it("all-old: one footer mark reading the oldest age (R4: '7h ago')", () => {
    const html = render(contractFor(card("canonical"), ageCase("old").observed_at));
    expect(marks(html)).toEqual([`card:${ageCase("old").card_mark}`]);
  });

  it("mixed: the one old row carries 'yesterday' and the footer carries nothing", () => {
    const html = render(contractFor(card("canonical"), ageCase("mixed").observed_at));
    expect(marks(html)).toEqual(["row:yesterday"]);
  });

  it("edge: no mark at all", () => {
    expect(marks(render(contractFor(card("canonical"), ageCase("edge").observed_at)))).toEqual([]);
  });

  it("CONTROL: no container → no card (it must open what it shows)", () => {
    expect(render(contractFor(card("canonical")), { ref: null })).toBe("");
    expect(render(contractFor(card("canonical")), { ref: { ...COLLECTION, collection_count: 0 } })).toBe("");
  });

  it("CONTROL: an unreadable contract → no card, not a partial one", () => {
    const c = contractFor(card("canonical"));
    c.rows[2] = { ...c.rows[2], probability: Number.NaN };
    expect(render(c)).toBe("");
  });

  it("reaches the feed: a kind:'roundup' bundle draws this card, never the grouped-card parts", () => {
    const item: FeedItem = {
      type: "bundle",
      score: 60,
      reason: "NFL division front-runners",
      headline: "NFL division front-runners",
      data: {
        id: "roundup:nfl-division-front-runners",
        title: "NFL division front-runners",
        kind: "roundup",
        item_count: 4,
        member_ids: [53671, 53672, 53673, 53674],
        items: [{ type: "futures", score: 1, reason: "", headline: "x", data: { id: 53671, name: "NFC East Division Winner", top_outcomes: [{ id: 1, name: "Cowboys", probability: 0.44, rank: 1 }] } } as unknown as FeedItem],
        collection_ref: COLLECTION,
        roundup: contractFor(card("canonical")),
      } as FeedBundleData,
    };
    const html = renderToStaticMarkup(<DiscoverCard groupedItem={{ type: "single", item }} positionIndex={0} />);
    expect(html).toContain('data-testid="roundup-card"');
    // The grouped-card header (BundleHeader) draws `bundle-eyebrow` and an
    // `aria-expanded` toggle; neither may appear on a round-up.
    expect(html).not.toContain('data-testid="bundle-eyebrow"');
    expect(html).not.toContain("aria-expanded");
    expect(html).toContain('data-testid="bundle-action-bar"');
  });
});
