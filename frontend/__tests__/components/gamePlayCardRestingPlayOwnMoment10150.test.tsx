/**
 * #10150 — the readout at rest names WHEN an earlier scoring play happened.
 *
 * Production 2026-10-02 02:30Z, 390px, live `/events/14780550` (TNF, Steelers
 * @ Browns). The readout read `5:30 - 3rd Quarter · 7:29 PM · 21 - 10 · Field
 * Goal Good · Chris Boswell 31 Yd Field Goal` — the kick was at Q2 0:08, 38
 * minutes before the badge's moment. The point and play below are that page's
 * served `espn_history` tail and `scoring_plays` tail, in shape.
 *
 * Every arm that must label is paired with one that must not.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import GamePlayCard from "../../components/GamePlayCard";
import type { ActiveChartPoint, ScoringPlay } from "../../lib/types";

const boswell: ScoringPlay = {
  timestamp: "2026-10-02T01:51:37.978855+00:00",
  description: "Chris Boswell 31 Yd Field Goal",
  short_text: "",
  team: "Pittsburgh Steelers",
  type: "Field Goal Good",
  home_score: 21,
  away_score: 10,
  period: "2",
  clock: "0:08",
};

const resting: ActiveChartPoint = {
  timestamp: "2026-10-02T02:29:38.416372+00:00",
  homeProb: 0.88,
  awayProb: 0.12,
  homeScore: 21,
  awayScore: 10,
  period: "5:30 - 3rd Quarter",
  clock: "5:30",
  scoringPlay: boswell,
};

function render(props: Partial<React.ComponentProps<typeof GamePlayCard>>): string {
  return renderToStaticMarkup(
    <GamePlayCard
      activePoint={null}
      lastPoint={resting}
      homeTeam="Cleveland Browns"
      awayTeam="Pittsburgh Steelers"
      sportKey="americanfootball_nfl"
      {...props}
    />,
  );
}

function text(html: string): string {
  return html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
}

function moments(html: string): string[] {
  return [...html.matchAll(/data-testid="game-play-card-play-moment"[^>]*>([^<]*)</g)].map((m) => m[1]);
}

describe("#10150 an earlier play at rest names its own moment", () => {
  it("labels the production specimen with the kick's own quarter and clock", () => {
    const html = render({});
    expect(text(html)).toContain("Q2 0:08 · Chris Boswell 31 Yd Field Goal");
    // The badge still says now — the label is beside it, not instead of it.
    expect(text(html)).toContain("5:30 - 3rd Quarter");
  });

  it("does not label a play that just happened (within the chart's attach window)", () => {
    const now: ActiveChartPoint = { ...resting, timestamp: "2026-10-02T01:52:37Z", period: "0:08 - 2nd Quarter", clock: "0:08" };
    const html = render({ lastPoint: now });
    expect(moments(html)).toEqual([]);
    expect(text(html)).toContain("Chris Boswell 31 Yd Field Goal");
  });

  it("does not label the play on a scrubbed point that carries it", () => {
    const scrubbed: ActiveChartPoint = { ...resting, timestamp: "2026-10-02T01:52:00Z", period: "2", clock: "0:08" };
    expect(moments(render({ activePoint: scrubbed }))).toEqual([]);
  });

  it("labels the last play under a Final badge", () => {
    const final: ActiveChartPoint = { ...resting, timestamp: "2026-10-02T03:40:00Z", period: "Final", clock: "Final" };
    expect(moments(render({ lastPoint: final, restingFinalScore: { home: 21, away: 10 } }))).toEqual(["Q2 0:08 · "]);
  });

  it("uses the badge's trust rules: a clockless sport names the inning only", () => {
    const hr: ScoringPlay = { ...boswell, period: "Top 7th", clock: "0:00", type: "Home Run", description: "Harper homered to right" };
    const pt: ActiveChartPoint = { ...resting, period: "Bottom 8th", clock: null, scoringPlay: hr };
    expect(moments(render({ lastPoint: pt, sportKey: "baseball_mlb" }))).toEqual(["Top 7th · "]);
  });

  it("falls back to the play's time of day when it names no period or clock", () => {
    const bare: ScoringPlay = { ...boswell, period: null, clock: null };
    const [m] = moments(render({ lastPoint: { ...resting, scoringPlay: bare } }));
    expect(m).toMatch(/^\d{1,2}:\d{2} [AP]M · $/);
  });

  it("carries the moment on the type line when there is no sentence", () => {
    const silent: ScoringPlay = { ...boswell, description: "", short_text: "" };
    const html = render({ lastPoint: { ...resting, scoringPlay: silent } });
    expect(moments(html)).toEqual(["Q2 0:08 ·"]);
    expect(html).not.toContain('data-testid="game-play-card-description"');
  });
});
