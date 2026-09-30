/**
 * #5811 (consumer half; producer = live's #9728) — A FEED CARD THE VENUE GRADED
 * SAYS WHO WON, AND FILES WHERE RESULTS FILE.
 *
 * ═══ WHAT A READER SAW ═══
 *
 * `/sports` at 390px, 2026-09-30 ~04:00Z: Live & Paused listed Luca Borando /
 * Ian Escuza (15320966) reading "No result reported · Sep 29" four hours after
 * the card ended, while `/events/15320966` read "Settled · Ian Escuza wins".
 * The void control, Erick Visconde / Ilias Bulaid (15320964), has no grade and
 * must keep reading exactly as it does.
 *
 * ═══ THE CORPUS ═══
 *
 * `fixtures/feedDwcsBouts.20260930-5811.json` holds both bouts exactly as
 * production `/api/feed?mode=sports` served them BEFORE #9728 released (the two
 * keys absent), plus the values `/api/events/{id}` served in the same minute —
 * the same shared reader #9728 attaches to the feed. `withGrade` grafts those
 * onto the card; `asServed` is the untouched card, which is also every cached
 * feed page from before the deploy.
 *
 * Every arm that asserts the new behaviour is RED on the parent: the parent's
 * `FeedCard` never reads the keys and its two sectioners called
 * `eventSectionKey(status)`, which returns "live" for any `suspended` row.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import corpus from "../fixtures/feedDwcsBouts.20260930-5811.json";
import FeedCard from "@/components/FeedCard";
import { feedEventSectionKey, groupFeedIntoSections } from "@/lib/feedSections";
import { partitionFinishedGames, buildFinishedSection } from "@/lib/sports/finishedSection";
import { SUSPENDED_LABEL, suspendedSummary } from "@/lib/eventState";
import type { FeedEventData, FeedItem } from "@/lib/types";

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});

jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({ track: () => {} }),
}));

const SETTLED_ID = 15320966;
const VOID_ID = 15320964;
const CAPTURED_AT = new Date(corpus.captured_at_utc).getTime();

type Detail = { venue_settled: boolean; venue_settled_result: string | null };
const DETAIL = corpus.detail as Record<string, Detail>;

function asServed(id: number): FeedItem {
  const item = (corpus.feed_items as unknown as FeedItem[]).find(
    (i) => (i.data as FeedEventData).id === id,
  );
  if (!item) throw new Error(`corpus lost ${id}`);
  return JSON.parse(JSON.stringify(item));
}

function withGrade(id: number): FeedItem {
  const item = asServed(id);
  Object.assign(item.data as FeedEventData, DETAIL[String(id)]);
  return item;
}

const data = (item: FeedItem) => item.data as FeedEventData;
const render = (item: FeedItem) => renderToStaticMarkup(<FeedCard item={item} />);

/** The right-hand status slot's whole text: the sentence, then #6361's date. */
const slotText = (html: string) =>
  html.match(/max-w-\[46%\]"[^>]*>([^<]*)<\/span>/)?.[1] ?? null;
const DATE = / · [A-Z][a-z]{2} \d{1,2}$/;

describe("A · CONTROL — the corpus is the shape every arm assumes", () => {
  test("both bouts are scoreless `suspended` rows with the keys absent as captured", () => {
    for (const id of [SETTLED_ID, VOID_ID]) {
      const d = data(asServed(id));
      expect(d.status).toBe("suspended");
      expect(d.home_score).toBeNull();
      expect(d.away_score).toBeNull();
      expect("venue_settled" in d).toBe(false);
      expect("venue_settled_result" in d).toBe(false);
    }
  });

  test("the detail route graded one and not the other", () => {
    expect(DETAIL[String(SETTLED_ID)]).toEqual({
      venue_settled: true,
      venue_settled_result: "Ian Escuza wins",
    });
    expect(DETAIL[String(VOID_ID)].venue_settled).toBe(false);
  });
});

describe("B · FeedCard — the suspended arm prints the venue's sentence", () => {
  test("the graded bout reads `Settled · Ian Escuza wins`, not `No result reported` (RED on parent)", () => {
    const html = render(withGrade(SETTLED_ID));
    expect(slotText(html)?.replace(DATE, "")).toBe("Settled · Ian Escuza wins");
    expect(html).not.toContain(SUSPENDED_LABEL);
    expect(html).toContain('data-venue-settled="true"');
    // The Link's accessible name says the same sentence as the slot.
    expect(html).toContain('aria-label="Luca Borando at Ian Escuza - Settled · Ian Escuza wins"');
  });

  test("the void control's markup is byte-identical to the card as served", () => {
    // `false` is "asked, nothing graded" — it must render exactly like "never asked".
    const graded = render(withGrade(VOID_ID));
    expect(graded).toBe(render(asServed(VOID_ID)));
    expect(graded).toContain(suspendedSummary(null, null, "away-home"));
    expect(graded).not.toContain("data-venue-settled");
  });

  test("a cached card without the keys is unchanged (the settled bout before #9728)", () => {
    const html = render(asServed(SETTLED_ID));
    expect(slotText(html)?.replace(DATE, "")).toBe(suspendedSummary(null, null, "away-home"));
    expect(html).not.toContain("Settled ·");
  });

  test("a `true` with no result prints the badge alone, never an invented winner", () => {
    const item = withGrade(SETTLED_ID);
    data(item).venue_settled_result = null;
    const html = render(item);
    expect(slotText(html)?.replace(DATE, "")).toBe("Settled");
    expect(html).not.toContain(SUSPENDED_LABEL);
  });
});

describe("C · the section is the card's sentence — one reading (#7112's second half)", () => {
  test("feedEventSectionKey files the graded bout as finished, the void one as live", () => {
    expect(feedEventSectionKey(data(withGrade(SETTLED_ID)))).toBe("finished"); // RED on parent
    expect(feedEventSectionKey(data(withGrade(VOID_ID)))).toBe("live");
    expect(feedEventSectionKey(data(asServed(SETTLED_ID)))).toBe("live");
  });

  test("a stray `venue_settled` cannot move a LIVE row or a scored one", () => {
    const live = withGrade(SETTLED_ID);
    data(live).status = "live";
    expect(feedEventSectionKey(data(live))).toBe("live");
    const scheduled = withGrade(SETTLED_ID);
    data(scheduled).status = "scheduled";
    expect(feedEventSectionKey(data(scheduled))).toBe("upcoming");
  });

  test("groupFeedIntoSections: graded bout under Just Happened, Live & Paused keeps only the void one", () => {
    const sections = groupFeedIntoSections([withGrade(SETTLED_ID), withGrade(VOID_ID)]);
    const byKey = Object.fromEntries(sections.map((s) => [s.key, s]));
    expect(byKey.live.title).toBe("Live & Paused");
    expect(byKey.live.items.map((i) => data(i).id)).toEqual([VOID_ID]);
    expect(byKey.finished.items.map((i) => data(i).id)).toEqual([SETTLED_ID]); // RED on parent
  });

  test("/sports' Finished partition takes the graded bout and the section shows it", () => {
    const { finished, rest } = partitionFinishedGames([withGrade(SETTLED_ID), withGrade(VOID_ID)]);
    expect(finished.map((i) => data(i).id)).toEqual([SETTLED_ID]); // RED on parent
    expect(rest.map((i) => data(i).id)).toEqual([VOID_ID]);
    const section = buildFinishedSection(finished, CAPTURED_AT);
    expect(section.shown.map((i) => data(i).id)).toEqual([SETTLED_ID]);
    expect(section.dropped).toEqual([]);
  });

  test("as served (keys absent) both bouts stay exactly where the parent filed them", () => {
    const { finished } = partitionFinishedGames([asServed(SETTLED_ID), asServed(VOID_ID)]);
    expect(finished).toEqual([]);
    const sections = groupFeedIntoSections([asServed(SETTLED_ID), asServed(VOID_ID)]);
    expect(sections.map((s) => s.key)).toEqual(["live"]);
  });
});
