import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { CollectionMember } from "@/lib/collections";
import type { FeedFuturesData } from "@/lib/types";
import snapshot from "./fixtures/midterms2026Presentation.json";
import evidence from "./fixtures/midtermsPartyEvidence.json";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ children, ...props }: { children: React.ReactNode }) => <a {...props}>{children}</a>,
}));
jest.mock("@/components/Analytics", () => ({ useAnalyticsContext: () => ({ track: () => {} }) }));

import CollectionHub from "@/components/collections/CollectionHub";
import { CollectionMemberCard } from "@/components/collections/CollectionMemberCard";
import { forgetAcceptedCollections, parseCollection, settleCollectionRead } from "@/lib/collections";
import { midtermsOutcomeParty } from "@/lib/midtermsParty";

const hub = () => parseCollection(snapshot, "midterms-2026");
const member = (id: number) => hub().members.find(m => m.id === id)!;
const renderCard = (id: number, presentation = "duel", patch: Record<string, unknown> = {}) => {
  const base = member(id);
  const changed: CollectionMember = { ...base, item: { ...base.item, data: { ...base.item.data, ...patch } as FeedFuturesData } };
  return renderToStaticMarkup(<CollectionMemberCard member={changed} presentation={presentation} />);
};
const side = (html: string, party: string) => new RegExp(`data-party="${party}"[^>]*>([\\s\\S]*?)</div>`).exec(html)?.[1] ?? "";

beforeEach(() => forgetAcceptedCollections());

test("the complete served collection has distinct control, balance, race and governor presentations", () => {
  const input = hub(), before = JSON.stringify(input);
  settleCollectionRead(input.slug, { hub: input });
  const html = renderToStaticMarkup(<CollectionHub slug={input.slug} />);
  expect(html.match(/data-midterms-card="control"/g)).toHaveLength(2);
  expect(html.match(/data-midterms-card="balance"/g)).toHaveLength(1);
  expect(html.match(/data-midterms-card="race"/g)).toHaveLength(8);
  expect(html.match(/data-midterms-card="governor"/g)).toHaveLength(2);
  for (const m of input.members) expect(html).toContain(`href="${m.href}"`);
  expect(html).toContain("19 more without a price yet");
  expect(html).not.toContain("Probability unavailable");
  expect(html).not.toMatch(/>[^<]*\d+\.\d+%/);
  expect(JSON.stringify(input)).toBe(before);
});

// These are public provider facts captured before implementation: the -D/-R
// contract names the party and its yes_sub_title names the candidate. Exercise
// the real collection card, including correct binding when the Republican leads.
test.each(evidence.flatMap(event => event.outcomes.map(outcome => ({ ...outcome, market_id: event.market_id }))))(
  "$name keeps its evidenced $party colour on both its number and bar",
  outcome => {
    const html = renderCard(outcome.market_id, outcome.market_id === 108645 ? "auto" : "duel");
    const partySide = side(html, outcome.party);
    expect(partySide).toContain(outcome.name);
    expect(partySide).toContain(`color:var(--party-${outcome.party === "D" ? "democratic" : "republican"})`);
    expect(html).toContain(`data-party-bar="${outcome.party}"`);
  },
);

test("party positions do not move the displayed prices to the wrong candidate", () => {
  const html = renderCard(109088);
  expect(side(html, "D")).toContain("Josh Turek");
  expect(side(html, "D")).toContain("49%");
  expect(side(html, "R")).toContain("Ashley Hinson");
  expect(side(html, "R")).toContain("51%");
});

test("all four balance outcomes retain their own prices in fixed chamber positions", () => {
  const html = renderCard(108619, "field");
  expect([...html.matchAll(/data-balance-parties="([DR]{2})"/g)].map(m => m[1])).toEqual(["DD", "RD", "DR", "RR"]);
  const original = member(108619).item.data as FeedFuturesData;
  for (const outcome of original.top_outcomes) expect(html).toContain(outcome.name);
  for (const label of ["75%", "20%", "5%", "1%", "Democratic House", "Republican Senate"]) expect(html).toContain(label);
  expect(html).toContain("color:var(--party-democratic)");
  expect(html).toContain("color:var(--party-republican)");
});

test("No to a Democratic sweep stays neutral rather than claiming a Republican sweep", () => {
  const html = renderCard(109918, "auto");
  expect(side(html, "D")).toContain("Yes");
  expect(side(html, "D")).toContain("59%");
  expect(side(html, "unknown")).toContain("No");
  expect(side(html, "unknown")).toContain("41%");
  expect(html).not.toContain('data-party="R"');
  expect(html).not.toContain('data-party-bar="R"');
});

test("a missing identity is neutral; neither surnames nor a stale id can assign a party", () => {
  expect(midtermsOutcomeParty(109085, { id: 999, name: "Roger Marshall" })).toBeNull();
  expect(midtermsOutcomeParty(109085, { id: 1595212, name: "Replacement nominee" })).toBeNull();
  expect(midtermsOutcomeParty(109065, { id: 1595212, name: "Adam Hamilton" })).toBeNull();
  expect(midtermsOutcomeParty(108629, { name: "Georgia" })).toBeNull();
  const html = renderCard(109085, "duel", { top_outcomes: [{ name: "New nominee", probability: .5 }, { name: "Another nominee", probability: .5 }] });
  expect(html.match(/data-party="unknown"/g)).toHaveLength(2);
  expect(html).toContain("New nominee");
  expect(html).not.toContain("Independent");
  expect(html).not.toContain("var(--party-democratic)");
  expect(html).not.toContain("var(--party-republican)");
});

test("partial prices and settled results keep their existing truthful branches", () => {
  const base = member(109085).item.data as FeedFuturesData;
  const partial = renderCard(109085, "duel", { top_outcomes: base.top_outcomes.map((o, i) => i ? { ...o, probability: null } : o) });
  expect(partial).toContain("1 more without a price yet");
  expect(partial).toContain("Adam Hamilton");
  expect(partial).toContain("color:var(--party-democratic)");
  expect(partial).not.toContain("Probability unavailable");
  const settled = renderCard(109085, "duel", { status: "settled", settled_winner: "Roger Marshall" });
  expect(settled).toContain("Settled - Roger Marshall");
  expect(settled).not.toContain("%");
  expect(settled).not.toContain("data-midterms-card");
});
