export function event(id: number, status = "scheduled", sport = "americanfootball_nfl") {
  return { type: "event", id, question_ids: id === 7 ? [70, 71] : [], destination: { kind: "event", id, web: `/events/${id}`, api: `/api/events/${id}` },
    card: { id, external_id: `fixture:${id}`, sport, sport_name: sport === "baseball_mlb" ? "MLB" : "NFL", home_team: "Kansas City Chiefs", away_team: "Buffalo Bills", commence_time: "2026-10-04T20:00:00Z", status,
      home_score: status === "completed" ? 27 : status === "live" ? 14 : null, away_score: status === "completed" ? 20 : status === "live" ? 10 : null,
      current_odds: { home_probability: 0.60, away_probability: 0.40 }, home_team_data: { primary_color: "#E31837" }, away_team_data: { primary_color: "#00338D" } } };
}
export function question(id: number, eventId: number | null = null, status = "open", sport = "baseball_mlb") {
  return { type: "market", id, event_id: eventId, destination: { kind: "market", id, web: `/futures/${id}`, api: `/api/futures/${id}` },
    card: { id, name: id === 70 ? "Josh Allen: 2+ passing touchdowns?" : id === 71 ? "Buffalo Bills: 24+ points?" : id === 72 ? "Who wins the Super Bowl?" : "Who wins the World Series?", sport, sport_name: sport === "baseball_mlb" ? "MLB" : "NFL", llm_sport_category: sport === "baseball_mlb" ? "baseball" : "americanfootball", source: "kalshi", source_count: 1, market_tier: 1, status, resolution_date: "2026-11-01T00:00:00Z", top_outcomes: [{ id: id * 10, name: "Yes", probability: 0.65, rank: 1, movement: 0.04 }], outcome_count: 1, canonical_market_key: null } };
}
type FixtureMember = ReturnType<typeof event> | ReturnType<typeof question>;
export function nflHub() {
  return { state: "published", slug: "nfl-2026-week-4", revision: 1,
    edition: { kind: "nfl_week", league: "nfl", season: 2026, stage: "Regular Season", week: 4 },
    container: { id: 901, name: "NFL Week 4", slug: "nfl-2026-week-4" }, children: [],
    sections: [{ class: "match_winner", count: 3, members: [event(7), event(8, "live"), event(9, "completed")] as FixtureMember[] },
               { class: "prop", count: 2, members: [question(70, 7, "open", "americanfootball_nfl"), question(71, 8, "open", "americanfootball_nfl")] as FixtureMember[] },
               { class: "title", count: 1, members: [question(72, null, "open", "americanfootball_nfl")] as FixtureMember[] }], member_count: 6, withheld: [], withheld_count: 0 };
}
export function mlbHub() {
  const final = question(81, null, "resolved");
  final.card.top_outcomes = [{ id: 810, name: "Dodgers", probability: 1, rank: 1, movement: 0 }];
  Object.assign(final.card.top_outcomes[0], { is_winner: true, resolution_source: "api_settlement" });
  const missing = question(82);
  Object.assign(missing.card.top_outcomes[0], { probability: null });
  const game = event(80, "completed", "baseball_mlb");
  game.card.home_team = "Los Angeles Dodgers"; game.card.away_team = "New York Yankees";
  return { state: "published", slug: "mlb-2026-postseason", revision: 2,
    edition: { kind: "mlb_postseason", league: "mlb", season: 2026 },
    container: { id: 902, name: "MLB 2026 Postseason", slug: "mlb-2026-postseason" }, children: [],
    sections: [{ class: "match_winner", count: 1, members: [game] }, { class: "title", count: 2, members: [final, missing] }], member_count: 3, withheld: [{ type: "market", id: 90, reason: "row_missing" }], withheld_count: 1 };
}
