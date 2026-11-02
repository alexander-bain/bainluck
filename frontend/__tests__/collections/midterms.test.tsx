import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import CollectionHub from "@/components/collections/CollectionHub";
import { forgetAcceptedCollections, parseCollection, settleCollectionRead, collectionRefreshInterval, activeCollectionPin } from "@/lib/collections";

const ids = [[108620, 108621], [108619], [109085, 109088, 109082, 109095, 109065, 109072, 109068, 109081], [108645, 109918, 108629]];
const titles = ["Congress control", "Balance of power", "The closest Senate races", "Governors"];
function fixture() {
  return { state: "published", slug: "midterms-2026", revision: 1,
    edition: { kind: "midterms", league: "politics", season: 2026 },
    subtitle: "Who controls Congress, the closest Senate races and the governors' mansions - updated live, settled as results come in.",
    container: { id: 901, name: "Midterms 2026", slug: "midterms-2026" }, children: [],
    sections: ids.map((section, index) => ({ class: ["congress_control", "balance_of_power", "senate_races", "governors"][index], title: titles[index], layout: ["party", "field", "duel", "auto"][index], count: section.length,
      members: section.map(id => ({ type: "market", id, event_id: null,
        destination: { kind: "market", id, web: `/futures/${id}`, api: `/api/futures/${id}` },
        card: { id, name: index === 0 ? "Party control" : "Maine Senate winner?", status: "open", source: "kalshi", outcome_count: index === 1 ? 4 : 2,
          top_outcomes: (index === 0 ? ["Republican", "Democratic"] : index === 1 ? ["D Senate / D House", "R Senate / D House", "R Senate / R House", "D Senate / R House"] : ["Susan Collins", "Graham Platner"]).map((name, n) => ({ name, probability: index === 1 ? [.4, .3, .2, .1][n] : [.585, .415][n] })) } })) })),
    member_count: 14, withheld: [], withheld_count: 0 };
}

beforeEach(() => forgetAcceptedCollections());

test("the phone page shows the curated sections with both names, whole numbers and attribution", () => {
  const raw = fixture();
  const hub = parseCollection(raw, raw.slug);
  settleCollectionRead(hub.slug, { hub });
  const html = renderToStaticMarkup(<CollectionHub slug={hub.slug} />);
  expect(html).toContain("Midterms 2026");
  expect(html).toContain("governors&#x27; mansions");
  expect(html.indexOf("Congress control")).toBeLessThan(html.indexOf("Balance of power"));
  expect(html.indexOf("Balance of power")).toBeLessThan(html.indexOf("The closest Senate races"));
  expect(html).toContain("Susan Collins");
  expect(html).toContain("Graham Platner");
  expect(html).toContain("59%");
  expect(html).toContain("41%");
  expect(html).toContain("Kalshi");
  expect(html.replace(/<[^>]*>/g, "")).not.toMatch(/\d\.\d+%/);
  expect(html).not.toMatch(/\bquestions?\b/i);
  expect(collectionRefreshInterval(hub)).toBe(30000);
});

test("a settled race says Settled and winner, with no live number", () => {
  const raw = fixture();
  const race = raw.sections[2].members[0].card;
  Object.assign(race, { status: "resolved", settled_winner: "Graham Platner" });
  race.top_outcomes.forEach(o => Object.assign(o, { probability: null }));
  const hub = parseCollection(raw, raw.slug);
  settleCollectionRead(hub.slug, { hub });
  const html = renderToStaticMarkup(<CollectionHub slug={hub.slug} />);
  const raceHtml = html.split('data-collection-member="market:109085"')[1].split('data-collection-member="market:109088"')[0];
  expect(raceHtml).toContain("Settled - Graham Platner");
  expect(raceHtml).not.toMatch(/\d+%/);
});

test("the pin uses the fresh public headline and expires at the end of Nov 6 Pacific", () => {
  const raw = { ...fixture(), discover_pin: { slug: "midterms-2026", name: "Midterms 2026", href: "/collections/midterms-2026", subtitle: "Senate 41% D - House 78% D", pin_until: "2026-11-07T08:00:00+00:00" } };
  const hub = parseCollection(raw, raw.slug);
  expect(activeCollectionPin(hub, Date.parse("2026-11-07T07:59:59Z"))?.subtitle).toBe("Senate 41% D - House 78% D");
  expect(activeCollectionPin(hub, Date.parse("2026-11-07T08:00:00Z"))).toBeNull();
  expect(activeCollectionPin({ ...hub, state: "withdrawn" }, Date.parse("2026-11-03T00:00:00Z"))).toBeNull();
});

test("Senate rows name the two leading candidates without inventing the rest of a wider field", () => {
  const raw = fixture();
  const race = raw.sections[2].members[0].card;
  race.outcome_count = 3;
  race.top_outcomes[0].probability = .5;
  race.top_outcomes[1].probability = .48;
  race.top_outcomes.push({ name: "Minor candidate", probability: .02 });
  const hub = parseCollection(raw, raw.slug);
  settleCollectionRead(hub.slug, { hub });
  const html = renderToStaticMarkup(<CollectionHub slug={hub.slug} />);
  const row = html.split('data-collection-member="market:109085"')[1].split('data-collection-member="market:109088"')[0];
  expect(row).toContain("Susan Collins");
  expect(row).toContain("Graham Platner");
  expect(row).toContain("50%");
  expect(row).toContain("48%");
  expect(row).not.toContain("Leader");
  expect(row).not.toContain("Minor candidate");
});
