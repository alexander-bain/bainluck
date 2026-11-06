import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ChampionshipOdds from "@/components/MarchMadness/ChampionshipOdds";
import TournamentCard from "@/components/TournamentCard";
import type { MarchMadnessTeam, GolfTournament } from "@/lib/types";

const text = (value: React.ReactElement) => renderToStaticMarkup(value)
  .replace(/<[^>]+>/g, "").replace(/&lt;/g, "<").replace(/&gt;/g, ">");

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
