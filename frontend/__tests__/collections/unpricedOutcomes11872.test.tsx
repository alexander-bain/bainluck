import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { CollectionMember } from "@/lib/collections";
import type { FeedFuturesData } from "@/lib/types";
import specimen from "./fixtures/closestGovernor108629.json";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ children, ...props }: { children: React.ReactNode }) => <a {...props}>{children}</a>,
}));
jest.mock("@/components/Analytics", () => ({ useAnalyticsContext: () => ({ track: () => {} }) }));

import { CollectionMemberCard } from "@/components/collections/CollectionMemberCard";

const member = (patch: Record<string, unknown> = {}): CollectionMember => ({
  key: "market:108629", id: specimen.id, type: "market", href: specimen.destination.web,
  questionIds: [], eventId: null,
  item: { type: "futures", score: 0, reason: "", headline: null,
    data: { ...specimen.card, ...patch } as unknown as FeedFuturesData },
});

describe("#11872: absence of a price is one note, not a wall of unavailable rows", () => {
  test("#11948: a fully priced field keeps 91% and a neutral 19-more preview", () => {
    const prices = [0.91, 0.1205, 0.115, 0.095, 0.0905];
    const rows = Array.from({ length: 24 }, (_, index) => ({
      id: index + 1, name: index === 0 ? "Nebraska" : `State ${index}`,
      probability: prices[index] ?? 0.01,
    }));
    const html = renderToStaticMarkup(<CollectionMemberCard member={member({
      status: "open", outcome_count: 24, top_outcomes: rows,
    })} presentation="field" />);
    expect(html).toContain("Nebraska");
    expect(html).toContain("91%");
    expect(html).not.toContain("68%");
    expect(html).toContain("19 more");
    expect(html).not.toContain("without a price yet");
    expect(html).not.toContain("State 5");
  });

  test.each([undefined, "field"])("the served 5-of-24 market retains sorted whole-number prices (%s)", (presentation) => {
    const input = member({ top_outcomes: [...specimen.card.top_outcomes].reverse() });
    const before = JSON.stringify(input);
    const html = renderToStaticMarkup(<CollectionMemberCard member={input} presentation={presentation} />);
    expect(html).toContain('href="/futures/108629"');
    expect(html).toContain("Closest Governor race in 2026?");
    expect(html).toContain("19 more");
    expect(html).not.toContain("Probability unavailable");
    const priced = ["Georgia", "Kansas", "Texas", "Nevada", "Ohio"];
    for (const name of priced) expect(html).toContain(name);
    for (let i = 1; i < priced.length; i++) expect(html.indexOf(priced[i - 1])).toBeLessThan(html.indexOf(priced[i]));
    for (const outcome of specimen.card.top_outcomes.filter(o => o.probability === null)) expect(html).not.toContain(outcome.name);
    for (const value of ["20%", "9%", "8%", "7%"]) expect(html).toContain(value);
    expect(html).not.toMatch(/\d+\.\d+%/);
    expect(JSON.stringify(input)).toBe(before);
  });

  test("zero is a real price; a single missing outcome is counted once", () => {
    const html = renderToStaticMarkup(<CollectionMemberCard member={member({ outcome_count: 2, top_outcomes: [
      { name: "Georgia", probability: 0 }, { name: "Kansas", probability: null },
    ] })} />);
    expect(html).toContain("Georgia");
    expect(html).toContain("0%");
    expect(html).toContain("1 more");
    expect(html).not.toContain("Kansas");
  });

  test("an entirely unpriced open market gets one honest count and no invented numbers", () => {
    const html = renderToStaticMarkup(<CollectionMemberCard member={member({ top_outcomes: specimen.card.top_outcomes.map(o => ({ ...o, probability: null })) })} />);
    expect(html).toContain("24 outcomes without a price yet");
    expect(html).not.toContain("Probability unavailable");
    expect(html).not.toContain("%");
  });

  test("settled rows keep their results and unknown results stay explicit", () => {
    const html = renderToStaticMarkup(<CollectionMemberCard member={member({ status: "settled", outcome_count: 3, top_outcomes: [
      { name: "Georgia", probability: 0.2, is_winner: true, resolution_source: "api_settlement" },
      { name: "Kansas", probability: null, is_winner: false, resolution_source: "api_settlement" },
      { name: "Texas", probability: null, is_winner: null, resolution_source: null },
    ] })} presentation="field" />);
    for (const label of ["Georgia", "Won", "Kansas", "Lost", "Texas", "Result unavailable"]) expect(html).toContain(label);
    expect(html).not.toContain("without a price yet");
    expect(html).not.toContain("%");
  });

  test("an authoritative result on an open market is retained even without a price", () => {
    const html = renderToStaticMarkup(<CollectionMemberCard member={member({ outcome_count: 3, top_outcomes: [
      { name: "Georgia", probability: 0.2 },
      { name: "Kansas", probability: null, is_winner: true, resolution_source: "api_settlement" },
      { name: "Texas", probability: null },
    ] })} />);
    expect(html).toContain("Georgia");
    expect(html).toContain("20%");
    expect(html).toContain("Kansas");
    expect(html).toContain("Won");
    expect(html).toContain("1 more");
    expect(html).not.toContain("Texas");
  });
});
