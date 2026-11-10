/**
 * @jest-environment jsdom
 * @jest-environment-options {"customExportConditions": ["node", "node-addons"]}
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ChampionshipOdds from "@/components/MarchMadness/ChampionshipOdds";
import TournamentCard from "@/components/TournamentCard";
import type { MarchMadnessTeam, GolfTournament } from "@/lib/types";

function text(value: React.ReactElement): string {
  const container = document.createElement("div");
  container.innerHTML = renderToStaticMarkup(value);
  return container.textContent ?? "";
}

it("reads escaped label text alongside literal boundary markers", () => {
  expect(text(<span>{"A & B <1% >99% <script>"}</span>))
    .toBe("A & B <1% >99% <script>");
});

it("keeps tiny and near-certain allocated March Madness probabilities honest", () => {
  const teams = [
    {team_name:"Tiny",probability:0.003,rendered_percent:0,movement_24h:null,sources:{}},
    {team_name:"Leader",probability:0.997,rendered_percent:100,movement_24h:null,sources:{}},
  ] as unknown as MarchMadnessTeam[];
  const value=text(<ChampionshipOdds teams={teams} almaMaterTeams={null} />);
  expect(value).toContain("<1%");expect(value).toContain(">99%");
});

it("keeps cup-card boundary markers around server allocations", () => {
  const tournament={name:"Presidents Cup",key:"presidents_cup",golfer_count:2,
    status:"upcoming",golfers:[
      {name:"Team USA",probability:0.004,rendered_percent:0,sources:{}},
      {name:"Team World",probability:0.996,rendered_percent:100,sources:{}},
    ]} as unknown as GolfTournament;
  const value=text(<TournamentCard tournament={tournament} />);
  expect(value).toContain("<1%");expect(value).toContain(">99%");
});

it("renders the cup's allocated Tie beside its two teams", () => {
  const tournament = {
    name: "Ryder Cup",
    key: "ryder_cup",
    golfers: [
      { name: "Team Europe", probability: 0.525 / 1.008, rendered_percent: 52, sources: {} },
      { name: "Team USA", probability: 0.43 / 1.008, rendered_percent: 43, sources: {} },
    ],
    overflow_outcomes: [{ name: "Tie", probability: 0.053 / 1.008, rendered_percent: 5 }],
  } as unknown as GolfTournament;
  const container = document.createElement("div");
  container.innerHTML = renderToStaticMarkup(<TournamentCard tournament={tournament} />);
  expect(container.textContent).toContain("Tie5%");
  expect(container.querySelectorAll("a")).toHaveLength(1);
  expect(container.querySelector("a")?.getAttribute("href")).toBe("/event/golf/ryder-cup");
  const widths = [...container.querySelectorAll<HTMLElement>("div[style]")].map(row => row.style.width);
  expect(widths).toEqual(expect.arrayContaining(["52%", "43%", "5%"]));
});

it("renders a settled Tie as its result", () => {
  const tournament = {
    name: "Ryder Cup",
    key: "ryder_cup",
    champion: "Tie",
    golfers: [
      { name: "Team Europe", probability: 0.525, sources: {} },
      { name: "Team USA", probability: 0.43, sources: {} },
    ],
    overflow_outcomes: [{ name: "Tie", probability: 0.053 }],
  } as unknown as GolfTournament;
  expect(text(<TournamentCard tournament={tournament} />)).toContain("TieWon");
});
