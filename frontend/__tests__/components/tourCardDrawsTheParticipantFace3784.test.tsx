/**
 * #3784 — the shared event card draws the player's face, not two grey letters.
 *
 * WHAT A READER SAW. `https://bainluck.com/sports/tennis_atp_us_open`, 390px,
 * production `ce783c6e`, 2026-09-07, during the US Open: every card on the page
 * was a grey initials square — `FC`, `AB`, `KK`, `LT`, `AG`, `BV` — while the
 * `/sports` feed card drew a Wikipedia headshot and an ESPN flag for those same
 * players. Measured on the SAME event (15304939, Medvedev v Tiafoe):
 * `/api/feed` served `home_image_url` + `home_flag_url`; `/api/events` served
 * no image key of any kind.
 *
 * THE RULE IS NOT NEW. #2919 settled the precedence for `FeedCard` — served
 * face, then served flag, then whatever the card already did. This is that rule
 * reaching the SHARED card (`/sports/[key]`, `/search`, `/my-stuff`,
 * `/preferences`, the league rails), in the same order, so the two cannot
 * drift. The backend half is `test_participant_face_on_every_surface_3784.py`,
 * whose last arm pins the two producers to the same answer.
 *
 * BOTH DIRECTIONS, PER GOTCHA #43. Every "draws a face" arm has a control that
 * a payload WITHOUT one still draws what it drew before — otherwise a card that
 * rendered a broken <img> for everybody, or dropped the crest column entirely,
 * would pass the headline assertion. Arm 5 (the unregistered player beside a
 * registered one) is the mixed card that a blanket change cannot fake.
 *
 * ARM 7 IS THE ONE THAT COSTS SOMETHING TO GET WRONG: a headshot is square and
 * a flag is 20x15. Choosing the box by "what sport is this" rather than "what
 * am I actually drawing" squashes a face into a letterbox, which is a worse
 * card than the initials it replaced.
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
jest.mock("../../hooks", () => ({
  useAnalytics: () => ({ trackEventCardClick: () => {}, track: () => {} }),
}));

import EventCard from "@/components/EventCard";
import type { Event } from "@/lib/types";

const IN_THE_FUTURE = new Date(Date.now() + 3 * 3600_000).toISOString();

/** The real values production serves for these two, abbreviated. */
const KHACHANOV_FACE = "https://upload.wikimedia.org/wikipedia/commons/thumb/k/kk/Khachanov.jpg";
const TIEN_FACE = "https://upload.wikimedia.org/wikipedia/commons/thumb/l/lt/Tien.jpg";
const RUS_FLAG = "https://a.espncdn.com/i/teamlogos/countries/500/rus.png";
const USA_FLAG = "https://a.espncdn.com/i/teamlogos/countries/500/usa.png";

/** The 4:00 PM card off Alex's screenshot — drawn `KK` / `LT` before #3784. */
function card(over: Partial<Event> = {}): string {
  const event = {
    id: 15304939,
    external_id: null,
    sport: "tennis_atp_us_open",
    sport_name: "ATP US Open",
    home_team: "Karen Khachanov",
    away_team: "Learner Tien",
    commence_time: IN_THE_FUTURE,
    status: "scheduled",
    home_score: null,
    away_score: null,
    ...over,
  } as unknown as Event;
  return renderToStaticMarkup(<EventCard event={event} />);
}

/** Every `src` the markup actually asks the browser for, in document order. */
function imageSources(html: string): string[] {
  return Array.from(html.matchAll(/<img[^>]*\ssrc="([^"]*)"/g)).map(m => m[1]);
}

/**
 * The `<img>` tag carrying a given src, so its geometry can be read.
 *
 * Deliberately NOT `new RegExp(...src...)`. Building a pattern out of a URL
 * puts a dot-bearing hostname into a regex, which CodeQL flags high-severity
 * (`js/incomplete-hostname-regexp`) — and it was right to, even here where the
 * input is escaped and a literal: a check run reading `fail` kills the sha
 * (notice 13b), and a test helper is not worth arguing with a scanner over.
 * Splitting the tags with one STATIC pattern and comparing strings is both
 * cleaner and unflaggable.
 */
function imgTagFor(html: string, src: string): string {
  const tags = Array.from(html.matchAll(/<img\b[^>]*>/g)).map(m => m[0]);
  return tags.find(tag => tag.includes(`src="${src}"`)) ?? "";
}

// ── the ship ───────────────────────────────────────────────────────────────

describe("the served face reaches the shared card", () => {
  it("draws both players' headshots instead of two initials squares", () => {
    const html = card({
      home_image_url: KHACHANOV_FACE,
      away_image_url: TIEN_FACE,
      home_flag_url: RUS_FLAG,
      away_flag_url: USA_FLAG,
    });

    expect(imageSources(html)).toEqual([KHACHANOV_FACE, TIEN_FACE]);
    // ...and the letters they replace are genuinely gone, not merely covered.
    expect(html).not.toContain(">KK<");
    expect(html).not.toContain(">LT<");
  });

  it("falls to the served flag for a registered player with no face", () => {
    // 42 of 378 registered players have a flag and no face (measured
    // 2026-09-03). Alexander Blockx is one of them, and he is on the
    // screenshot as `AB`.
    const html = card({
      home_team: "Alexander Blockx",
      home_image_url: null,
      home_flag_url: RUS_FLAG,
      away_image_url: TIEN_FACE,
      away_flag_url: USA_FLAG,
    });

    expect(imageSources(html)).toEqual([RUS_FLAG, TIEN_FACE]);
    expect(html).not.toContain(">AB<");
  });

  it("prefers the face over the flag when the register holds both", () => {
    // The precedence, asserted as an ORDER rather than as two separate
    // presence checks — a renderer that drew both would pass those.
    const html = card({
      home_image_url: KHACHANOV_FACE,
      home_flag_url: RUS_FLAG,
      away_image_url: TIEN_FACE,
      away_flag_url: USA_FLAG,
    });

    expect(imageSources(html)).toEqual([KHACHANOV_FACE, TIEN_FACE]);
    expect(html).not.toContain(RUS_FLAG);
  });
});

// ── the absence arms ───────────────────────────────────────────────────────

describe("a card with nothing served is unchanged", () => {
  it("still draws initials when the register has never heard of the player", () => {
    // The control arm, and a real one: Arthur Gea is the only player of the
    // eight on the screenshot the register cannot answer for.
    const html = card({
      home_team: "Arthur Gea",
      away_team: "Botic van de Zandschulp",
      home_image_url: null,
      home_flag_url: null,
      away_image_url: null,
      away_flag_url: null,
    });

    expect(imageSources(html)).toEqual([]);
    expect(html).toContain(">AG<");
    expect(html).toContain(">BV<");
  });

  it("draws a face for the registered side and initials for the other", () => {
    // The mixed card. A blanket "always draw an image" or "never draw one"
    // passes both single-sided arms above and fails here.
    const html = card({
      home_team: "Arthur Gea",
      home_image_url: null,
      home_flag_url: null,
      away_image_url: TIEN_FACE,
      away_flag_url: USA_FLAG,
    });

    expect(imageSources(html)).toEqual([TIEN_FACE]);
    expect(html).toContain(">AG<");
  });

  it("leaves a TEAM sport card on its crest, keys absent", () => {
    // `_format_event` omits the four keys entirely for a team sport, so this
    // is the shape an MLB card actually arrives in. A club must never wear
    // somebody's headshot.
    const html = card({
      sport: "baseball_mlb",
      home_team: "Los Angeles Dodgers",
      away_team: "Washington Nationals",
      home_team_data: { logo_small: "https://a.espncdn.com/i/teamlogos/mlb/500/lad.png" },
      away_team_data: { logo_small: "https://a.espncdn.com/i/teamlogos/mlb/500/wsh.png" },
    } as unknown as Partial<Event>);

    expect(imageSources(html)).toEqual([
      "https://a.espncdn.com/i/teamlogos/mlb/500/lad.png",
      "https://a.espncdn.com/i/teamlogos/mlb/500/wsh.png",
    ]);
  });
});

// ── geometry ───────────────────────────────────────────────────────────────

describe("a face is square and a flag is a flag", () => {
  it("never squashes a headshot into a flag's 20x15 letterbox", () => {
    const html = card({
      home_image_url: KHACHANOV_FACE,
      home_flag_url: RUS_FLAG,
      away_image_url: null,
      away_flag_url: USA_FLAG,
    });

    const face = imgTagFor(html, KHACHANOV_FACE);
    const flag = imgTagFor(html, USA_FLAG);

    expect(face).toContain('height="20"');
    expect(face).toContain("w-5 h-5");
    expect(face).not.toContain("h-[15px]");

    expect(flag).toContain('height="15"');
    expect(flag).toContain("h-[15px]");
  });
});
