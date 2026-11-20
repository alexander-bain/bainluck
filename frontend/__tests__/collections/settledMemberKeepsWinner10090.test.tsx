/**
 * #10090 (Fable, 8:39 AM PT Nov 9): a race the page settled by the official
 * result keeps its winner when the venue resolves the same market later.
 *
 * The served card carries `settled_winner`; the venue's resolved card does not.
 * `pricedCollectionMember` must keep the served member, or the card turns the
 * winner back into the venue's settled prices (100% / 0%).
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { FeedFuturesData, FeedItem } from "@/lib/types";
import snapshot from "./fixtures/midterms2026Presentation.json";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ children, href }: { children: React.ReactNode; href: string }) => <a href={href}>{children}</a>,
}));
jest.mock("@/components/Analytics", () => ({ useAnalyticsContext: () => ({ track: () => {} }) }));

import { CollectionMemberCard } from "@/components/collections/CollectionMemberCard";
import { MidtermsAtlasMemberCard } from "@/components/collections/MidtermsAtlasSection";
import { parseCollection, pricedCollectionMember, servedSettledMember, type CollectionMember } from "@/lib/collections";

const race = () => parseCollection(snapshot, "midterms-2026").members.find(m => m.id === 109085)!;
const withData = (m: CollectionMember, patch: Record<string, unknown>): CollectionMember =>
  ({ ...m, item: { ...m.item, data: { ...m.item.data, ...patch } as FeedFuturesData } });

/** The venue's own resolved card: settled prices, no `settled_winner`. */
const venueResolved = (m: CollectionMember): FeedItem => {
  const { settled_winner: _served, ...data } = m.item.data as FeedFuturesData & { settled_winner?: string };
  return {
    ...m.item,
    data: {
      ...data,
      status: "resolved",
      top_outcomes: data.top_outcomes.map((o, i) => ({ ...o, probability: i ? 0 : 1 })),
    } as FeedFuturesData,
  };
};

test("a served settled_winner card plus a venue-resolved price card still renders the winner", () => {
  const served = withData(race(), { status: "resolved", settled_winner: "Roger Marshall" });
  const shown = pricedCollectionMember(served, new Map([["futures-109085", venueResolved(served)]]));
  expect(shown).toBe(served);
  const html = renderToStaticMarkup(<CollectionMemberCard member={shown} presentation="duel" />);
  expect(html).toContain("Settled - Roger Marshall");
  expect(html).not.toContain("%");
  // The Atlas card names the winner only from `settled_winner` here: the
  // venue card has no graded outcome, so without the served card it prints 100%.
  const atlas = renderToStaticMarkup(<MidtermsAtlasMemberCard member={shown} sectionTitle="Senate" />);
  expect(atlas).toContain("Roger Marshall");
  expect(atlas).not.toContain("100%");
});

test("an open race still takes the stream's card", () => {
  const served = race();
  const fresh = venueResolved(served);
  expect(servedSettledMember(served)).toBe(false);
  expect(pricedCollectionMember(served, new Map([["futures-109085", fresh]])).item).toBe(fresh);
});

test("a blank settled_winner is not a result", () => {
  expect(servedSettledMember(withData(race(), { settled_winner: "  " }))).toBe(false);
  expect(servedSettledMember(withData(race(), { settled_winner: null }))).toBe(false);
});
