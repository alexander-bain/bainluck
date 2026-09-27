// #9133 — A GREEN CLUB'S CREST ON THE GREEN FOOTBALL HERO GETS A LIGHT DISC.
//
// Production `/` at 390px, 2026-09-27 12:17Z: New York Jets @ Detroit Lions
// (event 14781700) drew the Lions crest and, on the left, a green smudge — the
// Jets crest (`#115740`) on football's `#14532d → #15803d` hero. The fixture
// below is that card's served shape: the colours and logo URLs are the ones
// `/api/feed` returned for it.
//
// Both directions are asserted: the Jets side plates and the Lions side does
// not, and a club far from the hero (Texans, near-black; crest has red and
// white) keeps the bare crest — the plate is gated, not a redesign.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { FeedItem, FeedEventData } from "@/lib/types";
import { EventCard } from "../../components/discover/EventCard";
import { CATEGORY_GRADIENTS } from "../../components/discover/constants";
import { crestNeedsPlate, CREST_PLATE_DISTANCE } from "@/lib/discover/crestPlate";

const NYJ = { primary_color: "#115740", logo_small: "https://a.espncdn.com/i/teamlogos/nfl/500/scoreboard/nyj.png" };
const DET = { primary_color: "#0076b6", logo_small: "https://a.espncdn.com/i/teamlogos/nfl/500/scoreboard/det.png" };
const HOU = { primary_color: "#021018", logo_small: "https://a.espncdn.com/i/teamlogos/nfl/500/scoreboard/hou.png" };

function card(away: object, home: object, sport = "americanfootball_nfl"): string {
  const item = {
    type: "event",
    headline: "",
    reason: "",
    context_summary: null,
    score: 40,
    data: {
      id: 14781700,
      status: "scheduled",
      commence_time: "2099-09-27T17:00:00Z",
      away_team: "New York Jets",
      home_team: "Detroit Lions",
      sport,
      away_team_data: away,
      home_team_data: home,
    } as unknown as FeedEventData,
  } as unknown as FeedItem;
  return renderToStaticMarkup(
    <EventCard item={item} data={item.data as FeedEventData} liked={false} setLiked={() => {}} trending={false} />,
  );
}

describe("#9133 crest plate on a same-colour hero", () => {
  test("the Jets crest on the NFL hero sits on a plate; the Lions crest does not", () => {
    const html = card(NYJ, DET);
    expect(html).toContain('data-crest-plate="away"');
    expect(html).not.toContain('data-crest-plate="home"');
    // The plated crest is still the Jets logo, not a replacement.
    const plate = html.slice(html.indexOf('data-crest-plate="away"'));
    expect(plate.slice(0, plate.indexOf("</div>"))).toContain(NYJ.logo_small);
  });

  test("a club far from the hero keeps the bare crest", () => {
    const html = card(HOU, DET);
    expect(html).not.toContain("data-crest-plate");
    expect(html).toContain(HOU.logo_small);
  });

  test("the plate follows the club to the home side", () => {
    const html = card(DET, NYJ);
    expect(html).toContain('data-crest-plate="home"');
    expect(html).not.toContain('data-crest-plate="away"');
  });

  test("the measured population: 80 separates Packers/Jets/Timbers/Eagles from the next club", () => {
    const football = CATEGORY_GRADIENTS.football;
    const soccer = CATEGORY_GRADIENTS.soccer;
    expect(CREST_PLATE_DISTANCE).toBe(80);
    for (const c of ["#204e32", "#115740", "#06424d"]) expect(crestNeedsPlate(c, football)).toBe(true);
    expect(crestNeedsPlate("#2c5234", soccer)).toBe(true); // Portland Timbers
    // Austin FC (89), Broncos (104), Seahawks (119), Texans (141) — no plate.
    expect(crestNeedsPlate("#00b140", soccer)).toBe(false);
    for (const c of ["#0a2343", "#002a5c", "#021018"]) expect(crestNeedsPlate(c, football)).toBe(false);
  });

  test("no colour or no gradient never plates", () => {
    expect(crestNeedsPlate(null, CATEGORY_GRADIENTS.football)).toBe(false);
    expect(crestNeedsPlate("#115740", undefined)).toBe(false);
    expect(crestNeedsPlate("not-a-colour", CATEGORY_GRADIENTS.football)).toBe(false);
    expect(card({ logo_small: NYJ.logo_small }, DET)).not.toContain("data-crest-plate");
  });
});
