// ux/1052 item 5 (#2919) — a tennis card draws a face, not two letters.
//
// Alex, shopping /sports at phone width 2026-09-03: three live tennis cards, all
// initials (IB/BB, HS/CB, YP/QZ), beside soccer cards drawing real crests.
//
// The backend half puts four fields on the event card. This is the half that
// makes them visible, and the arms below are the ones that were actually wrong:
//
//   * a served HEADSHOT renders, square;
//   * a served FLAG renders when there is no headshot — 42 of 378 registered
//     players are in exactly that position, and a flag beats initials;
//   * a player we have nothing for still falls back to initials;
//   * a TEAM sport is untouched, because the server never fills these for one.
//
// Both arms every time. "No initials" alone passes for a card that renders
// nothing at all.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

jest.mock("next/image", () => ({
  __esModule: true,
  default: ({ src, alt, width, height }: { src: string; alt: string; width?: number; height?: number }) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={src} alt={alt} width={width} height={height} />
  ),
}));

jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({ track: () => {} }),
}));

jest.mock("@/lib/analytics", () => ({ trackEvent: jest.fn() }));

import FeedCard from "../../components/FeedCard";
import type { FeedItem } from "@/lib/types";

const FACE = "https://upload.wikimedia.org/wikipedia/commons/thumb/x/bucsa.jpg";
const FLAG = "https://a.espncdn.com/i/teamlogos/countries/500/esp.png";
const AWAY_FACE = "https://upload.wikimedia.org/wikipedia/commons/thumb/y/saka.jpg";
const AWAY_FLAG = "https://a.espncdn.com/i/teamlogos/countries/500/jpn.png";

function tennisCard(over: Record<string, unknown> = {}): FeedItem {
  return {
    type: "event",
    score: 90,
    data: {
      id: 15299477,
      external_id: "espn:1",
      sport: "tennis_wta_us_open",
      sport_name: "WTA US Open",
      home_team: "Cristina Bucsa",
      away_team: "Himeno Sakatsume",
      commence_time: "2026-09-03T18:00:00+00:00",
      status: "live",
      home_score: 1,
      away_score: 0,
      current_odds: {
        home_probability: 0.62,
        away_probability: 0.38,
        source: "kalshi",
      },
      ...over,
    },
  } as unknown as FeedItem;
}

/** The two-letter fallback the card draws when it has no picture. */
function initials(name: string) {
  return name.split(" ").map((w) => w.charAt(0)).join("").slice(0, 2).toUpperCase();
}

describe("FeedCard participant images (ux/1052 item 5, #2919)", () => {
  test("THE SHIP — a served headshot is drawn for both players", () => {
    const html = renderToStaticMarkup(
      <FeedCard
        item={tennisCard({
          home_image_url: FACE,
          away_image_url: AWAY_FACE,
          home_flag_url: FLAG,
          away_flag_url: AWAY_FLAG,
        })}
      />
    );

    expect(html).toContain(FACE);
    expect(html).toContain(AWAY_FACE);
    // The face wins over the flag when both are served — the flag is the
    // fallback, not a co-equal.
    expect(html).not.toContain(FLAG);
    expect(html).not.toContain(AWAY_FLAG);
  });

  test("a headshot is drawn SQUARE, not squashed into a flag's 20x15", () => {
    const html = renderToStaticMarkup(
      <FeedCard item={tennisCard({ home_image_url: FACE, home_flag_url: FLAG })} />
    );

    const img = html.match(/<img[^>]*bucsa\.jpg[^>]*>/)?.[0] ?? "";
    expect(img).toContain('width="20"');
    expect(img).toContain('height="20"');
  });

  test("a player with a FLAG and no face gets the flag, not initials", () => {
    // 42 of 378 registered players are exactly here. Ignacio Buse is one.
    const html = renderToStaticMarkup(
      <FeedCard
        item={tennisCard({
          home_image_url: null,
          home_flag_url: FLAG,
          away_image_url: null,
          away_flag_url: AWAY_FLAG,
        })}
      />
    );

    expect(html).toContain(FLAG);
    expect(html).toContain(AWAY_FLAG);
    const flagImg = html.match(/<img[^>]*esp\.png[^>]*>/)?.[0] ?? "";
    expect(flagImg).toContain('height="15"');
  });

  test("CONTROL — with all four null the card still shows initials", () => {
    // Without this arm every assertion above passes for a card that has been
    // reduced to rendering images unconditionally, and the two players we have
    // nothing for (Joel Schwaerzler, Tomas Barrios) would render broken.
    const html = renderToStaticMarkup(
      <FeedCard
        item={tennisCard({
          home_image_url: null,
          away_image_url: null,
          home_flag_url: null,
          away_flag_url: null,
        })}
      />
    );

    expect(html).toContain(`>${initials("Cristina Bucsa")}<`);
    expect(html).toContain(`>${initials("Himeno Sakatsume")}<`);
    expect(html).not.toContain("upload.wikimedia.org");
  });

  test("CONTROL — a payload with no image keys at all is the pre-#2919 build", () => {
    // `undefined` is not `null`. A card served by an older backend must behave
    // exactly as it did before this shipped.
    const html = renderToStaticMarkup(<FeedCard item={tennisCard()} />);

    expect(html).toContain(`>${initials("Cristina Bucsa")}<`);
  });

  test("a TEAM sport is untouched by these fields", () => {
    // The server only fills them for individual sports, but the card must not
    // depend on that: a crest is never displaced by a participant image.
    const crest = "https://a.espncdn.com/i/teamlogos/nfl/500/chi.png";
    const html = renderToStaticMarkup(
      <FeedCard
        item={tennisCard({
          sport: "americanfootball_nfl",
          sport_name: "NFL",
          home_team: "Chicago Bears",
          away_team: "Green Bay Packers",
          home_team_data: { logo_small: crest, primary_color: "#0B162A" },
          home_image_url: null,
          away_image_url: null,
          home_flag_url: null,
          away_flag_url: null,
        })}
      />
    );

    expect(html).toContain(crest);
  });
});
