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
      [
        "six rows",
        {
          ...base(),
          rows: [
            ...base().rows,
            { ...base().rows[0], market_id: 98 },
            { ...base().rows[0], market_id: 99 },
          ],
        },
        "row_count",
      ],
      ["a row with no number", { ...base(), rows: base().rows.map((r, i) => (i === 2 ? { ...r, probability: NaN } : r)) }, "bad_row"],
      ["a row with no label", { ...base(), rows: base().rows.map((r, i) => (i === 1 ? { ...r, label: "" } : r)) }, "bad_row"],
      ["a row with neither market_id nor event_id", { ...base(), rows: base().rows.map((r, i) => (i === 1 ? { label: r.label, probability: r.probability } : r)) }, "bad_row"],
      ["a row with both market_id and event_id", { ...base(), rows: base().rows.map((r, i) => (i === 1 ? { ...r, event_id: 301 } : r)) }, "bad_row"],
      ["the same market twice", { ...base(), rows: base().rows.map((r, i) => (i === 1 ? { ...r, market_id: base().rows[0].market_id } : r)) }, "duplicate_market"],
      [
        "the same event twice",
        {
          ...base(),
          rows: [
            { event_id: 303, label: "Heat at Bucks: Bucks", probability: 0.6 },
            { event_id: 303, label: "Suns at Lakers: Lakers", probability: 0.56 },
            { event_id: 301, label: "Knicks at Celtics: Celtics", probability: 0.52 },
            { event_id: 305, label: "Devils at Rangers: Rangers", probability: 0.51 },
          ],
        },
        "duplicate_market",
      ],
      [
        "an event_id row with outcome_id",
        {
          ...base(),
          rows: [
            { event_id: 303, outcome_id: 1, label: "Heat at Bucks: Bucks", probability: 0.6 } as unknown as FeedRoundupContract["rows"][number],
            { event_id: 304, label: "Suns at Lakers: Lakers", probability: 0.56 },
            { event_id: 301, label: "Knicks at Celtics: Celtics", probability: 0.52 },
            { event_id: 305, label: "Devils at Rangers: Rangers", probability: 0.51 },
          ],
        },
        "bad_row",
      ],
      [
        "the same field_band outcome twice",
        {
          ...base(),
          rows: [
            { market_id: 227, outcome_id: 22705, label: "Penn State", probability: 0.795 },
            { market_id: 227, outcome_id: 22705, label: "Notre Dame", probability: 0.68 },
            { market_id: 227, outcome_id: 22707, label: "Alabama", probability: 0.64 },
            { market_id: 227, outcome_id: 22708, label: "Miami", probability: 0.6 },
          ],
        },
        "duplicate_market",
      ],
    ])("%s", (_name, contract, refusal) => {
      const res = buildRoundupCardModel("NFL division front-runners", contract as FeedRoundupContract | null, NOW_MS);
      expect(res.model).toBeNull();
      expect(res.refusal).toBe(refusal);
    });
  });

  it("admits #11915's event_id rows ('The closest games tonight') and renders the card on Discover", () => {
    const closestGamesContract: FeedRoundupContract = {
      kicker: "Round-up",
      tag: "SPORTS",
      footer: "Bain Luck blend · the 4 closest of 7 games tonight",
      rows: [
        { event_id: 102, label: "Bucks at Celtics: Celtics", probability: 0.61, observed_at: FRESH },
        { event_id: 104, label: "Timberwolves at Nuggets: Nuggets", probability: 0.58, observed_at: FRESH },
        { event_id: 103, label: "Devils at Rangers: Devils", probability: 0.54, observed_at: FRESH },
        { event_id: 101, label: "Suns at Lakers: Lakers", probability: 0.51, observed_at: FRESH },
      ],
    };
    const { model, refusal } = buildRoundupCardModel("The closest games tonight", closestGamesContract, NOW_MS);
    expect(refusal).toBeNull();
    expect(model!.cadence).toBe("live");
    expect(model!.rows.map((r) => r.marketId)).toEqual([102, 104, 103, 101]);
    expect(model!.rows.map((r) => `${r.digits}% ${r.label}`)).toEqual([
      "61% Bucks at Celtics: Celtics",
      "58% Timberwolves at Nuggets: Nuggets",
      "54% Devils at Rangers: Devils",
      "51% Suns at Lakers: Lakers",
    ]);

    const html = render(closestGamesContract, {
      title: "The closest games tonight",
      ref: {
        slug: "roundup-closest-games-tonight",
        name: "The closest games tonight",
        revision: 410023918,
        collection_count: 4,
      },
    });
    expect(stripTags(html)).toBe(
      "Round-up SPORTS The closest games tonight 61 % Bucks at Celtics: Celtics 58 % Timberwolves at Nuggets: Nuggets 54 % Devils at Rangers: Devils 51 % Suns at Lakers: Lakers Bain Luck blend · the 4 closest of 7 games tonight",
    );
    expect(html).toMatch(/<a href="\/collections\/roundup-closest-games-tonight"[^>]*data-testid="roundup-card"/);
  });

  it("admits field_band rows ('College Football Playoff picture') sharing one spine market_id with distinct outcome_ids without normalizing to 100", () => {
    const cfpContract: FeedRoundupContract = {
      kicker: "Round-up",
      tag: "NCAAF",
      footer: "Chance to make the 12-team field · teams between 20% and 80%",
      rows: [
        { market_id: 227, outcome_id: 22705, label: "Penn State", probability: 0.795, observed_at: "2026-10-06T20:30:00Z" },
        { market_id: 227, outcome_id: 22706, label: "Notre Dame", probability: 0.68, observed_at: "2026-10-06T20:30:00Z" },
        { market_id: 227, outcome_id: 22707, label: "Alabama", probability: 0.64, observed_at: "2026-10-06T20:30:00Z" },
        { market_id: 227, outcome_id: 22708, label: "Miami", probability: 0.60, observed_at: "2026-10-06T20:30:00Z" },
      ],
    };
    const { model, refusal } = buildRoundupCardModel("College Football Playoff picture", cfpContract, NOW_MS);
    expect(refusal).toBeNull();
    expect(model!.cadence).toBe("futures");
    expect(model!.rows.map((r) => r.marketId)).toEqual([22705, 22706, 22707, 22708]);
    expect(model!.rows.map((r) => `${r.digits}% ${r.label}`)).toEqual([
      "80% Penn State",
      "68% Notre Dame",
      "64% Alabama",
      "60% Miami",
    ]);

    const html = render(cfpContract, {
      title: "College Football Playoff picture",
      ref: {
        slug: "roundup-cfp-picture",
        name: "College Football Playoff picture",
        revision: 382910412,
        collection_count: 2,
      },
    });
    expect(stripTags(html)).toBe(
      "Round-up NCAAF College Football Playoff picture 80 % Penn State 68 % Notre Dame 64 % Alabama 60 % Miami Chance to make the 12-team field · teams between 20% and 80%",
    );
    expect(html).toMatch(/<a href="\/collections\/roundup-cfp-picture"[^>]*data-testid="roundup-card"/);
  });

  it("admits same_deadline_board five-row cards ('By December 31') with kicker 'SAME DEADLINE', count_line 'Showing 5 of 6', and no venue name or blend claim", () => {
    const dec31Contract: FeedRoundupContract = {
      kicker: "SAME DEADLINE",
      tag: null,
      count_line: "Showing 5 of 6",
      footer: "Separate markets that settle by the same day.",
      rows: [
        { market_id: 62162058, label: "Next Claude Opus (5.6+) released", probability: 0.885, observed_at: FRESH },
        { market_id: 27594137, label: "Trump meets with Putin", probability: 0.83, observed_at: FRESH },
        { market_id: 30587891, label: "Will Banksy create a new mural or street artwork?", probability: 0.47, observed_at: FRESH },
        { market_id: 8422080, label: "Pete Hegseth out as Secretary of Defense", probability: 0.40, observed_at: FRESH },
        { market_id: 13791228, label: "SCOTUS accepts sports event contract case", probability: 0.205, observed_at: FRESH },
      ],
    };
    const { model, refusal } = buildRoundupCardModel("By December 31", dec31Contract, NOW_MS);
    expect(refusal).toBeNull();
    expect(model!.kicker).toBe("SAME DEADLINE");
    expect(model!.tag).toBeNull();
    expect(model!.countLine).toBe("Showing 5 of 6");
    expect(model!.footer).toBe("Separate markets that settle by the same day.");
    expect(model!.rows.map((r) => `${r.digits}% ${r.label}`)).toEqual([
      "89% Next Claude Opus (5.6+) released",
      "83% Trump meets with Putin",
      "47% Will Banksy create a new mural or street artwork?",
      "40% Pete Hegseth out as Secretary of Defense",
      "21% SCOTUS accepts sports event contract case",
    ]);

    const html = render(dec31Contract, {
      title: "By December 31",
      ref: {
        slug: "by-december-31",
        name: "By December 31",
        revision: 91238411,
        collection_count: 6,
      },
    });
    const plain = stripTags(html);
    expect(plain).toBe(
      "SAME DEADLINE By December 31 89 % Next Claude Opus (5.6+) released 83 % Trump meets with Putin 47 % Will Banksy create a new mural or street artwork? 40 % Pete Hegseth out as Secretary of Defense 21 % SCOTUS accepts sports event contract case Showing 5 of 6 Separate markets that settle by the same day.",
    );
    expect(plain).not.toMatch(/\b(kalshi|polymarket|sportsbooks?|blend|question|questions)\b/i);
    expect(html).toContain('data-testid="roundup-count-line">Showing 5 of 6</div>');
    expect(html).not.toContain('data-testid="roundup-tag"');
    expect(html).toMatch(/<a href="\/collections\/by-december-31"[^>]*data-testid="roundup-card"/);
  });

  it("admits sibling_family cards ('Will it snow by November 15?' and 'Will they be featured on GTA VI: The Album?') with the two-part count_line ('Showing X of Y … · No number yet: …')", () => {
    const snowContract: FeedRoundupContract = {
      kicker: "SNOW · NOV 15",
      tag: null,
      count_line: "Showing 5 of 10 cities · No number yet: Detroit, Minneapolis, Pittsburgh",
      footer: "Each city is its own market. They don't add up to 100%.",
      rows: [
        { market_id: 60087431, label: "Indianapolis", probability: 0.485, rendered_percent: 49, observed_at: FRESH },
        { market_id: 60087427, label: "Buffalo", probability: 0.45, rendered_percent: 45, observed_at: FRESH },
        { market_id: 60087426, label: "Boston", probability: 0.38, rendered_percent: 38, observed_at: FRESH },
        { market_id: 60087435, label: "Salt Lake City", probability: 0.34, rendered_percent: 34, observed_at: FRESH },
        { market_id: 60084869, label: "Kansas City", probability: 0.255, rendered_percent: 26, observed_at: FRESH },
      ],
    };
    const { model, refusal } = buildRoundupCardModel("Will it snow by November 15?", snowContract, NOW_MS);
    expect(refusal).toBeNull();
    expect(model!.kicker).toBe("SNOW · NOV 15");
    expect(model!.tag).toBeNull();
    expect(model!.countLine).toBe("Showing 5 of 10 cities · No number yet: Detroit, Minneapolis, Pittsburgh");
    expect(model!.countLine!.split(" · ")).toEqual([
      "Showing 5 of 10 cities",
      "No number yet: Detroit, Minneapolis, Pittsburgh",
    ]);
    expect(model!.footer).toBe("Each city is its own market. They don't add up to 100%.");
    expect(model!.rows.map((r) => `${r.digits}% ${r.label}`)).toEqual([
      "49% Indianapolis",
      "45% Buffalo",
      "38% Boston",
      "34% Salt Lake City",
      "26% Kansas City",
    ]);

    const html = render(snowContract, {
      title: "Will it snow by November 15?",
      ref: {
        slug: "snow-first-flakes-2026",
        name: "Will it snow by November 15?",
        revision: 71829301,
        collection_count: 27,
      },
    });
    const plain = stripTags(html).replace(/&#x27;/g, "'");
    expect(plain).toBe(
      "SNOW · NOV 15 Will it snow by November 15? 49 % Indianapolis 45 % Buffalo 38 % Boston 34 % Salt Lake City 26 % Kansas City Showing 5 of 10 cities · No number yet: Detroit, Minneapolis, Pittsburgh Each city is its own market. They don't add up to 100%.",
    );
    expect(plain).not.toMatch(/\b(kalshi|polymarket|sportsbooks?|blend|question|questions)\b/i);
    expect(html).toContain(
      'data-testid="roundup-count-line">Showing 5 of 10 cities · No number yet: Detroit, Minneapolis, Pittsburgh</div>',
    );
    expect(html).toMatch(/<a href="\/collections\/snow-first-flakes-2026"[^>]*data-testid="roundup-card"/);
  });

  it("accepts a two-row yardstick_pair ('FOR SCALE') card and preserves [target, anchor] order", () => {
    const yardstickContract: FeedRoundupContract = {
      kicker: "FOR SCALE",
      tag: null,
      footer: "Two independent markets at the same probability right now.",
      rows: [
        {
          market_id: 113200,
          label: "The Iranian regime falls before 2027",
          probability: 0.036,
          rendered_percent: 4,
          observed_at: FRESH,
        },
        {
          market_id: 113012,
          label: "US recession by end of 2026",
          probability: 0.055,
          rendered_percent: 6,
          observed_at: FRESH,
        },
      ],
    };
    const title = "The Iranian regime falls before 2027: as likely as a US recession by end of 2026";
    const { model, refusal } = buildRoundupCardModel(title, yardstickContract, NOW_MS);
    expect(refusal).toBeNull();
    expect(model!.kicker).toBe("FOR SCALE");
    expect(model!.rows.map((r) => `${r.digits}% ${r.label}`)).toEqual([
      "4% The Iranian regime falls before 2027",
      "6% US recession by end of 2026",
    ]);
  });

  it("accepts two-row HEAD TO HEAD and 2-4 row THIS WEEK cards (#11936)", () => {
    const headToHeadContract: FeedRoundupContract = {
      kicker: "HEAD TO HEAD",
      tag: "TENNIS",
      footer: "Each player is their own market; both can win 2+.",
      rows: [
        {
          market_id: 66937562,
          outcome_id: 669375622,
          label: "Carlos Alcaraz",
          probability: 0.42,
          rendered_percent: 42,
          observed_at: FRESH,
        },
        {
          market_id: 66937563,
          outcome_id: 669375632,
          label: "Jannik Sinner",
          probability: 0.38,
          rendered_percent: 38,
          observed_at: FRESH,
        },
      ],
    };
    const h2h = buildRoundupCardModel(
      "Who wins 2+ Grand Slams in 2027?",
      headToHeadContract,
      NOW_MS,
    );
    expect(h2h.refusal).toBeNull();
    expect(h2h.model!.kicker).toBe("HEAD TO HEAD");
    expect(h2h.model!.rows.map((r) => `${r.digits}% ${r.label}`)).toEqual([
      "42% Carlos Alcaraz",
      "38% Jannik Sinner",
    ]);

    const golfWeekContract: FeedRoundupContract = {
      kicker: "GOLF · THIS WEEK",
      tag: "GOLF",
      footer: "Each row is the leader in its own tournament.",
      rows: [
        {
          market_id: 28862743,
          label: "World Wide Technology Championship · Nov 5–8 · Ben James",
          probability: 0.313,
          rendered_percent: 31,
          observed_at: FRESH,
        },
        {
          market_id: 28862742,
          label: "Abu Dhabi Aldar Championship · Nov 5–8 · Rory McIlroy",
          probability: 0.19125,
          rendered_percent: 19,
          observed_at: FRESH,
        },
      ],
    };
    const golf = buildRoundupCardModel(
      "Two tournaments",
      golfWeekContract,
      NOW_MS,
    );
    expect(golf.refusal).toBeNull();
    expect(golf.model!.kicker).toBe("GOLF · THIS WEEK");
    expect(golf.model!.rows.map((r) => `${r.digits}% ${r.label}`)).toEqual([
      "31% World Wide Technology Championship · Nov 5–8 · Ben James",
      "19% Abu Dhabi Aldar Championship · Nov 5–8 · Rory McIlroy",
    ]);
  });

  it("preserves chronological sequence order and links to /sport/<sport>/<league>/team/<slug> for subject_sequence (#12232)", () => {
    const seqContract: FeedRoundupContract = {
      kicker: "NEXT 3 GAMES",
      tag: "NBA",
      footer: "Combined win probability · next 3 games in schedule order",
      order: "sequence",
      presentation: "strip",
      relations: ["same_subject", "same_measure", "same_window"],
      level: "member",
      destination_href: "/sport/basketball/nba/team/boston-celtics",
      rows: [
        {
          event_id: 15343971,
          label: "at Bucks · Sun Nov 8",
          opponent_label: "at Bucks",
          date_label: "Sun Nov 8",
          probability: 0.855,
          rendered_percent: 86,
          observed_at: FRESH,
        },
        {
          event_id: 15341912,
          label: "at 76ers · Tue Nov 10",
          opponent_label: "at 76ers",
          date_label: "Tue Nov 10",
          probability: 0.5,
          rendered_percent: 50,
          observed_at: FRESH,
        },
        {
          event_id: 15342527,
          label: "vs Raptors · Wed Nov 11",
          opponent_label: "vs Raptors",
          date_label: "Wed Nov 11",
          probability: 0.64,
          rendered_percent: 64,
          observed_at: FRESH,
        },
      ],
    };

    const { model, refusal } = buildRoundupCardModel(
      "Boston Celtics: next 3 games",
      seqContract,
      NOW_MS,
    );
    expect(refusal).toBeNull();
    expect(model!.order).toBe("sequence");
    expect(model!.presentation).toBe("strip");
    // Must stay in chronological order (86%, 50%, 64%), NOT probability order (86%, 64%, 50%)!
    expect(model!.rows.map((r) => `${r.digits}% ${r.label}`)).toEqual([
      "86% at Bucks · Sun Nov 8",
      "50% at 76ers · Tue Nov 10",
      "64% vs Raptors · Wed Nov 11",
    ]);

    const html = render(seqContract, {
      title: "Boston Celtics: next 3 games",
      ref: {
        slug: "celtics-next-3-games",
        href: "/sport/basketball/nba/team/boston-celtics",
        name: "Boston Celtics: next 3 games",
        revision: 41239812,
        collection_count: 3,
      },
    });
    expect(html).toContain('data-presentation="strip"');
    expect(html).toMatch(
      /<a href="\/sport\/basketball\/nba\/team\/boston-celtics"[^>]*data-testid="roundup-card"/,
    );
  });

  it("ages event_id rows on the 30-minute live cadence while market_id rows keep the 6-hour futures cadence", () => {
    const twoHoursOld = "2026-10-06T19:41:00Z";
    const eventContract: FeedRoundupContract = {
      kicker: "Round-up",
      tag: "SPORTS",
      footer: "Bain Luck blend · the 4 closest of 7 games tonight",
      rows: [
        { event_id: 102, label: "Bucks at Celtics: Celtics", probability: 0.61, observed_at: FRESH },
        { event_id: 104, label: "Timberwolves at Nuggets: Nuggets", probability: 0.58, observed_at: twoHoursOld },
        { event_id: 103, label: "Devils at Rangers: Devils", probability: 0.54, observed_at: FRESH },
        { event_id: 101, label: "Suns at Lakers: Lakers", probability: 0.51, observed_at: FRESH },
      ],
    };
    const marketContract = contractFor(card("canonical"), [FRESH, twoHoursOld, FRESH, FRESH]);

    const { model: eventModel } = buildRoundupCardModel("The closest games tonight", eventContract, NOW_MS);
    expect(eventModel!.rows.map((r) => r.rowMark)).toEqual([false, true, false, false]);
    const eventHtml = render(eventContract, { title: "The closest games tonight" });
    expect(marks(eventHtml)).toEqual(["row:2h ago"]);
    expect(eventHtml).toContain('data-cadence="live"');

    const { model: marketModel } = buildRoundupCardModel("NFL division front-runners", marketContract, NOW_MS);
    expect(marketModel!.rows.map((r) => r.rowMark)).toEqual([false, false, false, false]);
    expect(marks(render(marketContract))).toEqual([]);
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

  it("#11949 Order 6: renders two-bar awards rows (Nominated % alongside Wins %) and refuses invalid secondary probabilities", () => {
    const awardsContract: FeedRoundupContract = {
      kicker: "GOLDEN GLOBES",
      tag: "ENTERTAINMENT",
      footer: "Several nominees are nominated; one wins.",
      rows: [
        {
          market_id: 9100,
          outcome_id: 91001,
          label: "One Battle After Another",
          probability: 0.42,
          rendered_percent: 42,
          secondary_probability: 0.88,
          secondary_rendered_percent: 88,
          primary_bar_label: "Wins",
          secondary_bar_label: "Nominated",
          observed_at: FRESH,
        },
        {
          market_id: 9100,
          outcome_id: 91002,
          label: "Sinners",
          probability: 0.31,
          rendered_percent: 31,
          secondary_probability: 0.79,
          secondary_rendered_percent: 79,
          primary_bar_label: "Wins",
          secondary_bar_label: "Nominated",
          observed_at: FRESH,
        },
        {
          market_id: 9100,
          outcome_id: 91003,
          label: "Hamnet",
          probability: 0.27,
          rendered_percent: 27,
          secondary_probability: 0.74,
          secondary_rendered_percent: 74,
          primary_bar_label: "Wins",
          secondary_bar_label: "Nominated",
          observed_at: FRESH,
        },
      ],
    };
    const html = render(awardsContract, { title: "Best Picture: who's nominated, who wins" });
    expect(html).toContain('data-testid="roundup-row-secondary"');
    expect(html).toContain("Nominated 88% · Wins 42%");
    expect(html).toContain("Nominated 79% · Wins 31%");
    expect(html).toContain("Nominated 74% · Wins 27%");

    const invalidAwards: FeedRoundupContract = {
      ...awardsContract,
      rows: [
        awardsContract.rows[0],
        awardsContract.rows[1],
        { ...awardsContract.rows[2], secondary_probability: 1.2 },
      ],
    };
    expect(buildRoundupCardModel("Best Picture", invalidAwards, NOW_MS)).toEqual({
      model: null,
      refusal: "bad_row",
    });
  });
});
