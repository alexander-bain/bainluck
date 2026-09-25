// #8677 — A NATIONAL TEAM'S PAGE PAINTED A WRONG COUNTRY'S LETTERS.
//
// Production, 390px, 2026-09-25: Discover's card for Northern Ireland @ Georgia
// drew Northern Ireland's flag; two taps later `/events/15290672` drew a grey
// `IRE` tile for the same team — Republic of Ireland's code. The payload held
// the flag in `away_team_data.logo_small` the whole time. The hero's image
// ladder was `logo_large` -> `espnTeamLogoByName` -> letters and never read
// `logo_small`, which is the only image a national team carries.
//
// The assertion is on the page's own markup (same harness as #7270): the
// defect was the page not asking, so a helper unit test could not see it.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const NIR_FLAG = "https://flagcdn.com/w80/gb-nir.png";

// The specimen's own fields, from `/api/events/15290672` at 18:25Z. Georgia
// carries no team data at all; Northern Ireland carries only the flag.
const EVENT = {
  id: 15290672,
  sport: "soccer_uefa_nations_league",
  sport_title: "UEFA Nations League",
  sport_name: "UEFA Nations League",
  home_team: "Georgia",
  away_team: "Northern Ireland",
  home_score: null,
  away_score: null,
  status: "live",
  commence_time: "2026-09-25T16:02:00+00:00",
  win_probability_sources: {},
  away_team_data: {
    team_id: 1930,
    slug: "northern-ireland",
    primary_color: null,
    secondary_color: null,
    logo_small: NIR_FLAG,
    logo_large: null,
    record: null,
  },
};

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => {
    const isEvent = Array.isArray(key) && key[0] === "event";
    return {
      data: isEvent ? EVENT_HOLDER.value : undefined,
      error: undefined,
      isLoading: false,
      mutate: () => undefined,
    };
  },
}));

jest.mock("@/hooks", () => ({
  ...jest.requireActual("@/hooks"),
  __esModule: true,
  usePageTracking: () => undefined,
  useScrollDepth: () => undefined,
  useEngagementTime: () => undefined,
  usePinnedEvents: () => ({
    isPinned: () => false,
    togglePin: () => undefined,
    isMaxReached: false,
  }),
}));

jest.mock("@/hooks/useLiveEventStream", () => ({
  __esModule: true,
  useLiveEventStream: () => ({ frame: null, connected: false }),
}));

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: () => {}, replace: () => {}, prefetch: () => {} }),
  usePathname: () => "/events/15290672",
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ id: "15290672" }),
}));

const EVENT_HOLDER: { value: unknown } = { value: EVENT };

// eslint-disable-next-line @typescript-eslint/no-var-requires
const EventDetailPage = require("@/app/events/[id]/page").default;
// eslint-disable-next-line @typescript-eslint/no-var-requires
const { AnalyticsProvider } = require("@/components/Analytics");

function draw(): string {
  return renderToStaticMarkup(
    React.createElement(
      AnalyticsProvider,
      null,
      React.createElement(EventDetailPage, { params: { id: "15290672" } }),
    ),
  );
}


/** Each hero tile: the <img> src it draws (if any) and whether its letters are hidden. */
function heroTiles(html: string): Array<{ src: string | null; letters: string; lettersHidden: boolean }> {
  const tiles = html.split('class="w-14 h-14 rounded-2xl').slice(1);
  return tiles.map(tile => {
    const img = tile.match(/^[^]*?<img[^>]*src="([^"]+)"/);
    const span = tile.match(/<span class="([^"]*font-extrabold[^"]*)"[^>]*>([^<]*)<\/span>/);
    const imgBeforeSpan = img && span && tile.indexOf(img[0]) < tile.indexOf(span[0]) ? img[1] : null;
    return {
      src: imgBeforeSpan,
      letters: span ? span[2].trim() : "",
      lettersHidden: span ? /\bhidden\b/.test(span[1]) : false,
    };
  });
}

describe("#8677 the hero draws a national team's flag, not a letter tile", () => {
  it("draws the logo_small flag for Northern Ireland and hides its letters", () => {
    EVENT_HOLDER.value = EVENT;
    const tiles = heroTiles(draw());
    // Positive first: both tiles exist, so nothing below passes on an empty hero.
    expect(tiles).toHaveLength(2);
    const [home, away] = tiles;
    expect(away.src).toBe(NIR_FLAG);
    expect(away.lettersHidden).toBe(true);
    // Control, same page: Georgia has no image of any kind and keeps its badge.
    expect(home.src).toBeNull();
    expect(home.letters).toBe("GEO");
    expect(home.lettersHidden).toBe(false);
  });

  it("reads logo_small on the HOME tile too", () => {
    EVENT_HOLDER.value = {
      ...EVENT,
      home_team: "Northern Ireland",
      away_team: "Georgia",
      home_team_data: EVENT.away_team_data,
      away_team_data: undefined,
    };
    const [home, away] = heroTiles(draw());
    expect(home.src).toBe(NIR_FLAG);
    expect(home.lettersHidden).toBe(true);
    expect(away.src).toBeNull();
    expect(away.letters).toBe("GEO");
  });

  it("keeps logo_large ahead of logo_small — a tile that drew a picture keeps it", () => {
    const LARGE = "https://example.test/large.png";
    EVENT_HOLDER.value = {
      ...EVENT,
      away_team_data: { ...EVENT.away_team_data, logo_large: LARGE },
    };
    const [, away] = heroTiles(draw());
    expect(away.src).toBe(LARGE);
  });
});
