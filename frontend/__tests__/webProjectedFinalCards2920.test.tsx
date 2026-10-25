/**
 * #2920 / #9483 — the projected final on the two web game cards: readable,
 * named per team, one admitted pair, and only where it is a real scoreline.
 *
 * WHAT A READER SAW. Alex, 2026-10-19, 49ers v Commanders (`/events/14780563`),
 * before play: the event page printed `Projected final: 30 – 22` in faint 11px
 * type, and the league card printed no forecast at all. The search card's
 * version was `Proj 30-22` — an abbreviation and two numbers tied to nobody.
 *
 * Fixtures are production payloads captured 2026-10-19 22:20–22:30Z
 * (`fixtures/webProjectedFinal2920.json`): the specimen from `/api/events`, its
 * Sports feed row (which carries NO projected pair — release-root holds that
 * producer dependency), and search rows for the format mapping.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

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
jest.mock("@/hooks", () => ({
  useAnalytics: () => ({ trackEventCardClick: () => {}, track: () => {} }),
}));

import EventCard from "@/components/EventCard";
import FeedCard from "@/components/FeedCard";
import { cardProjectedFinal, projectedFinalFormat, projectedFinalLabel } from "@/lib/projectedFinalPair";
import type { Event, FeedEventData, FeedItem } from "@/lib/types";
import FIXTURE from "./fixtures/webProjectedFinal2920.json";

const F = FIXTURE as unknown as Record<string, unknown>;
const FUTURE = new Date(Date.now() + 3 * 3600_000).toISOString();
const PAST = new Date(Date.now() - 40 * 60_000).toISOString();

function specimen(patch: Partial<Event> = {}, odds: Record<string, unknown> = {}): Event {
  const base = F.event_14780563 as Event;
  return {
    ...base,
    commence_time: FUTURE,
    ...patch,
    current_odds: { ...base.current_odds, ...odds } as Event["current_odds"],
  };
}

function searchRow(id: number, patch: Partial<Event> = {}): Event {
  return { ...(F[`search_${id}`] as Event), commence_time: FUTURE, status: "scheduled", home_score: null, away_score: null, ...patch };
}

/** The feed row as served, optionally with the pair the producer will add. */
function feedItem(patch: Partial<FeedEventData> = {}, odds: Record<string, unknown> = {}): FeedItem {
  const base = F.feed_item_14780563 as FeedItem;
  const data = base.data as FeedEventData;
  return {
    ...base,
    data: {
      ...data,
      commence_time: FUTURE,
      ...patch,
      current_odds: { ...data.current_odds!, ...odds },
    },
  } as FeedItem;
}

const card = (e: Event) => renderToStaticMarkup(<EventCard event={e} />);
const feed = (i: FeedItem) => renderToStaticMarkup(<FeedCard item={i} />);
const SERVED_PAIR = { projected_home_score: 29.6, projected_away_score: 22.3 };

function stamp(html: string, testId: string): string | null {
  const m = html.match(new RegExp(`data-testid="${testId}" data-projected-final="(\\d+)-(\\d+)" data-projected-order="([a-z-]+)"`));
  return m ? `${m[1]}-${m[2]} ${m[3]}` : null;
}

describe("the specimen, 14780563, before play", () => {
  it("the fixture is the photographed reading: 29.6 / 22.3 rounds to the 30 – 22 Alex saw", () => {
    const e = F.event_14780563 as Event;
    expect(e.home_team).toBe("San Francisco 49ers");
    expect(e.current_odds?.projected_home_score).toBe(29.6);
    expect(e.current_odds?.projected_away_score).toBe(22.3);
  });

  it("EventCard prints the full label and each number beside its own team, home first", () => {
    const html = card(specimen());
    expect(stamp(html, "event-card-projected-final")).toBe("30-22 home-away");
    expect(html).toContain(">Projected final<");
    expect(html).toContain('aria-label="Projected final: 49ers 30, Commanders 22"');
    // The number is the next thing after its own name, never after the other's.
    expect(html).toMatch(/49ers\u00a0<span class="font-mono">30<\/span>/);
    expect(html).toMatch(/Commanders\u00a0<span class="font-mono">22<\/span>/);
    expect(html).not.toMatch(/Proj <span/);
  });

  it("the value is main-value contrast, not muted provenance styling", () => {
    const html = card(specimen());
    const row = html.slice(html.indexOf('data-testid="event-card-projected-final"'));
    expect(row.slice(0, 900)).toContain("text-text-primary");
  });

  it("before play there is no invented 0 – 0", () => {
    const html = card(specimen());
    expect(html).not.toMatch(/>0<\/span>/);
    expect(html).not.toContain("0-0");
  });

  it("the served feed row carries no pair, so FeedCard prints none — it does not compute one", () => {
    const item = feedItem();
    expect((item.data as FeedEventData).current_odds).not.toHaveProperty("projected_home_score");
    expect(stamp(feed(item), "feed-card-projected-final")).toBeNull();
  });

  it("once the feed serves the same pair, FeedCard prints the same scoreline, away first like its rows", () => {
    const html = feed(feedItem({}, SERVED_PAIR));
    expect(stamp(html, "feed-card-projected-final")).toBe("30-22 away-home");
    expect(html).toContain('aria-label="Projected final: Commanders 22, 49ers 30"');
    // Reversed orientation, same binding: Commanders' name sits on 22.
    expect(html.indexOf("Commanders\u00a0<span")).toBeLessThan(html.indexOf("49ers\u00a0<span"));
    expect(html).toMatch(/Commanders\u00a0<span class="font-mono">22<\/span>/);
  });

  it("card and feed agree with each other at the same reading", () => {
    const fromCard = stamp(card(specimen()), "event-card-projected-final")!.split(" ")[0];
    const fromFeed = stamp(feed(feedItem({}, SERVED_PAIR)), "feed-card-projected-final")!.split(" ")[0];
    expect(fromFeed).toBe(fromCard);
  });
});

describe("a missing or broken pair prints nothing", () => {
  it.each([
    ["null halves", { projected_home_score: null, projected_away_score: null }],
    ["one absent half", { projected_home_score: 29.6, projected_away_score: undefined }],
    ["NaN", { projected_home_score: Number.NaN, projected_away_score: 22.3 }],
    ["Infinity", { projected_home_score: Number.POSITIVE_INFINITY, projected_away_score: 22.3 }],
    ["negative half (#9006)", { projected_home_score: 29.6, projected_away_score: -1.8 }],
    ["zero half", { projected_home_score: 29.6, projected_away_score: 0 }],
  ])("%s", (_label, odds) => {
    expect(stamp(card(specimen({}, odds)), "event-card-projected-final")).toBeNull();
    expect(stamp(feed(feedItem({}, odds)), "feed-card-projected-final")).toBeNull();
    expect(card(specimen({}, odds))).not.toContain("NaN");
  });

  it("a level pair in a sport that cannot end level is refused, as the hero refuses it (#8156)", () => {
    const nba = searchRow(15195969);
    expect(cardProjectedFinal({ projected_home_score: 110.4, projected_away_score: 110.2 }, nba.sport)).toBeNull();
    // ...and an NFL tie is a legal result, so it stays.
    expect(cardProjectedFinal({ projected_home_score: 23.6, projected_away_score: 24.2 }, "americanfootball_nfl")).toEqual({ home: 24, away: 24 });
  });
});

describe("only a pre-game reading wears the label", () => {
  it("live: neither card prints a projection, even with a pair on the payload", () => {
    const live = { status: "live", commence_time: PAST, home_score: 7, away_score: 3 } as Partial<Event>;
    expect(stamp(card(specimen(live)), "event-card-projected-final")).toBeNull();
    expect(stamp(feed(feedItem(live as Partial<FeedEventData>, SERVED_PAIR)), "feed-card-projected-final")).toBeNull();
  });

  it("a scheduled row past its kickoff is not 'before play' on the feed card", () => {
    expect(stamp(feed(feedItem({ commence_time: PAST }, SERVED_PAIR)), "feed-card-projected-final")).toBeNull();
  });

  it("suspended: no projection on either card", () => {
    const stopped = { status: "suspended", commence_time: PAST } as Partial<Event>;
    expect(stamp(card(specimen(stopped)), "event-card-projected-final")).toBeNull();
    expect(stamp(feed(feedItem(stopped as Partial<FeedEventData>, SERVED_PAIR)), "feed-card-projected-final")).toBeNull();
  });
});

describe("a final is compared only with a genuine pre-game baseline — none is served yet", () => {
  // Production 15328569 (NCAAF, kickoff 17:00Z): `current_odds` 31.2 / 23.8 was
  // captured at 20:25Z, four minutes before the end — an IN-GAME reading. Shown
  // beside the 31 – 38 final as a "pregame projection" it would be false.
  const final = () => ({ ...(F.search_15328569 as Event) });

  it("the fixture's pair really is in-game: captured after kickoff", () => {
    const e = final();
    expect(Date.parse(e.current_odds!.captured_at)).toBeGreaterThan(Date.parse(e.commence_time));
  });

  it("the finished card prints no projection and no 'Pregame projection'", () => {
    const html = card(final());
    expect(html).not.toContain("projected-final");
    expect(html).not.toContain("Pregame projection");
    expect(html).not.toContain("Projected final");
  });

  it("the finished feed card prints none either, whatever pair rides on it", () => {
    const html = feed(feedItem({ status: "completed", commence_time: PAST, home_score: 31, away_score: 38 }, SERVED_PAIR));
    expect(html).not.toContain("projected-final");
    expect(html).not.toContain("Pregame projection");
  });
});

describe("format admission — real fixtures, one answer per sport", () => {
  it("admits points sports and soccer, each in its own unit", () => {
    expect(projectedFinalFormat("americanfootball_nfl")).toEqual({ unit: "points", label: "Projected final" });
    expect(projectedFinalFormat("americanfootball_ncaaf_fcs")?.unit).toBe("points");
    expect(projectedFinalFormat("basketball_nba")?.unit).toBe("points");
    expect(projectedFinalFormat("basketball_euroleague")?.unit).toBe("points");
    expect(projectedFinalFormat("soccer_epl")).toEqual({ unit: "goals", label: "Projected final (90 min)" });
  });

  it.each([
    "baseball_mlb", // ±1.5 run line (#8617)
    "icehockey_nhl", // ±1.5 puck line — 15333056
    "icehockey_ahl",
    "tennis_atp_shanghai_masters", // games under a sets scoreboard — 15326853
    "mma_mixed_martial_arts", // rounds (#9006)
    "boxing_boxing",
    "golf_masters_tournament_winner",
    "cricket_ipl",
    "esports_cs2",
    "rugbyleague_nrl",
    "aussierules_afl",
    "",
  ])("%s is not admitted", (sport) => {
    expect(projectedFinalFormat(sport)).toBeNull();
  });

  it("an NHL card with the served puck-line pair prints nothing", () => {
    const nhl = searchRow(15333056);
    expect(nhl.current_odds?.spread).toBe(-1.5);
    expect(stamp(card(nhl), "event-card-projected-final")).toBeNull();
  });

  it("a tennis card with the served games pair prints nothing (it printed `Proj 11-11` before)", () => {
    expect(stamp(card(searchRow(15326853)), "event-card-projected-final")).toBeNull();
  });

  it("an MLB card prints nothing (control for #8617, which this keeps)", () => {
    expect(stamp(card(searchRow(15317977)), "event-card-projected-final")).toBeNull();
  });

  it("an NBA card prints its pair; soccer prints its 90-minute label", () => {
    expect(stamp(card(searchRow(15195969)), "event-card-projected-final")).toBe("120-115 home-away");
    const epl = card(searchRow(15315510));
    expect(stamp(epl, "event-card-projected-final")).toBe("1-1 home-away");
    expect(epl).toContain(">Projected final (90 min)<");
    expect(projectedFinalLabel("soccer_epl")).toBe("Projected final (90 min)");
  });
});
