import Foundation

func checkWatchProbabilityFormatting() throws {
    let mlb = try event(extras: ",\"sport_key\":\"baseball_mlb\",\"current_odds\":{\"home_probability\":0.455,\"away_probability\":0.545}")
    precondition(mlb.homeRenderedPercent == 45, "Real complementary sides share the duel rounding contract")
    let homeOnly = try event(extras: ",\"sport_key\":\"baseball_mlb\",\"current_odds\":{\"home_probability\":0.455}")
    precondition(homeOnly.awayProbability == nil && homeOnly.homeRenderedPercent == 46,
                 "A missing away reading stays missing and home uses scalar rounding")
    let unclassified = try event(extras: ",\"hero_probability\":0.455,\"hero_probability_away\":0.545")
    precondition(unclassified.homeRenderedPercent == 46,
                 "An older snapshot without sport classification cannot assume two-way rounding")
    let hero = try event(extras: ",\"sport_key\":\"baseball_mlb\",\"hero_probability\":0.255,\"hero_probability_away\":0.745,\"current_odds\":{\"home_probability\":0.455,\"away_probability\":0.545,\"home_rendered_percent\":45,\"away_rendered_percent\":55}")
    precondition(hero.homeRenderedPercent == 25 && hero.awayProbability == 0.745,
                 "Format the selected hero pair rather than a different odds pair or served percent")
    let heroOnly = try event(extras: ",\"hero_probability\":0.455,\"current_odds\":{\"home_probability\":0.455,\"away_probability\":0.545}")
    precondition(heroOnly.awayProbability == nil && heroOnly.homeRenderedPercent == 46,
                 "Missing hero away must not borrow current odds or synthesize a complement")
    let soccer = try event(extras: ",\"sport\":\"soccer_epl\",\"current_odds\":{\"home_probability\":0.455,\"away_probability\":0.545}")
    precondition(soccer.sportKey == "soccer_epl" && soccer.homeRenderedPercent == 46,
                 "Backend sport alias keeps draw-priced soccer on scalar rounding")
    let legacySoccer = try event(extras: ",\"sport_key\":\"soccer_epl\",\"hero_probability\":0.455,\"hero_probability_away\":0.545")
    precondition(legacySoccer.homeRenderedPercent == 46)
    let canonicalSport = try event(extras: ",\"sport\":\"soccer_epl\",\"sport_key\":\"baseball_mlb\",\"hero_probability\":0.455,\"hero_probability_away\":0.545")
    precondition(canonicalSport.sportKey == "soccer_epl" && canonicalSport.homeRenderedPercent == 46)
    let homeFavourite = try event(extras: ",\"sport\":\"baseball_mlb\",\"hero_probability\":0.545,\"hero_probability_away\":0.455")
    precondition(homeFavourite.homeRenderedPercent == 55, "Keep the favourite's rounded percentage")
    let explicitDraw = try event(extras: ",\"sport_key\":\"unknown\",\"current_odds\":{\"home_probability\":0.455,\"away_probability\":0.545,\"draw_probability\":0.1}")
    precondition(explicitDraw.homeRenderedPercent == 46, "An explicit valid draw keeps scalar rounding even for unknown sport")
    let zeroDraw = try event(extras: ",\"current_odds\":{\"home_probability\":0.455,\"away_probability\":0.545,\"draw_probability\":0}")
    precondition(zeroDraw.homeRenderedPercent == 46, "A zero draw reading still identifies a three-way forecast")
    let zero = try event(extras: ",\"current_odds\":{\"home_probability\":0,\"away_probability\":1}")
    precondition(zero.homeRenderedPercent == 0, "Zero is a valid probability")
    let openingHero = try event(extras: ",\"hero_probability_source\":\"opening\",\"hero_probability\":0.58,\"hero_probability_away\":0.42,\"current_odds\":{\"home_probability\":0.6,\"away_probability\":0.4,\"draw_probability\":0.2}")
    let openingOdds = try event(extras: ",\"current_odds\":{\"quote_kind\":\"opening\",\"home_probability\":0.58,\"away_probability\":0.42,\"draw_probability\":0.2}")
    for reading in [openingHero, openingOdds] {
        precondition(reading.homeProbabilityText == nil && reading.awayProbability == nil && reading.drawProbability == nil,
                     "A tagged opening reading must not supply a Watch forecast")
    }
    let blendWithHistoricalOdds = try event(extras: ",\"hero_probability_source\":\"blend\",\"hero_probability\":0.32,\"hero_probability_away\":0.68,\"hero_probability_observed_at\":\"2026-01-01T00:00:00Z\",\"current_odds\":{\"quote_kind\":\"opening\",\"home_probability\":0.58,\"draw_probability\":0.2}")
    precondition(blendWithHistoricalOdds.homeProbabilityText == "32%" && blendWithHistoricalOdds.awayProbability == 0.68)
    precondition(blendWithHistoricalOdds.probabilityObservedAt != nil && blendWithHistoricalOdds.drawProbability == nil)
    for extras in ["", ",\"current_odds\":{\"away_probability\":0.545}",
                   ",\"current_odds\":{\"home_probability\":-0.1}",
                   ",\"hero_probability\":2,\"current_odds\":{\"home_probability\":2}",
                   ",\"current_odds\":{\"home_probability\":\"unknown\"}"] {
        let missing = try event(extras: extras)
        precondition(missing.homeProbability == nil && missing.homeRenderedPercent == nil,
                     "Missing or invalid home probability cannot display a percentage")
    }
    let scalar = try event(extras: ",\"current_odds\":{\"home_probability\":0.565}")
    precondition(scalar.homeRenderedPercent == 57, "Scalar percentages use the shared epsilon-stable formatter")
    for status in ["final", "completed", "closed"] {
        let settled = try event(extras: ",\"status\":\"\(status)\",\"current_odds\":{\"home_probability\":0.455,\"away_probability\":0.545}")
        precondition(!settled.showsForecast && settled.homeRenderedPercent == nil && settled.homeProbabilityText == nil, "Final and closed readings never present forecasts")
    }
    for reading in [mlb, soccer, hero, homeOnly, explicitDraw, zero, unclassified] {
        let restored = try JSONDecoder().decode(WatchSelectedGame.self, from: JSONEncoder().encode(reading))
        precondition(restored.sportKey == reading.sportKey && restored.homeRenderedPercent == reading.homeRenderedPercent,
                     "Snapshot restoration preserves sport identity and probability formatting")
        precondition(restored.homeProbability == reading.homeProbability && restored.awayProbability == reading.awayProbability)
    }
    let legacyPinsJSON = """
    {
      "1":{"id":1,"home_team":"Celtics","away_team":"Knicks","status":"live",
           "home_score":72,"away_score":68,"hero_probability":0.58,"hero_probability_away":0.42,
           "current_odds":{"home_probability":0.58,"away_probability":0.42}},
      "2":{"id":2,"home_team":"Kings","away_team":"Lakers","status":"scheduled",
           "hero_probability":0.7,"hero_probability_observed_at":"2026-01-01T00:00:00Z"},
      "3":{"id":3,"home_team":"Nets","away_team":"Heat","status":"completed","home_score":94,"away_score":93}
    }
    """
    let legacyPins = try JSONDecoder().decode([Int: WatchSelectedGame.CachedReading].self,
                                               from: Data(legacyPinsJSON.utf8)).mapValues(\.game)
    precondition(legacyPins[1]?.homeProbabilityText == nil && legacyPins[1]?.awayProbability == nil)
    precondition(legacyPins[1]?.homeTeam == "Celtics" && legacyPins[1]?.homeScore == 72 && legacyPins[1]?.awayScore == 68)
    precondition(legacyPins[2]?.homeProbabilityText == "70%" && legacyPins[2]?.probabilityObservedAt != nil)
    precondition(legacyPins[3]?.isFinal == true && legacyPins[3]?.homeScore == 94)
    let freshPins = try JSONEncoder().encode([1: mlb])
    let restoredPins = try JSONDecoder().decode([Int: WatchSelectedGame.CachedReading].self,
                                                 from: freshPins).mapValues(\.game)
    precondition(restoredPins[1]?.homeProbability == mlb.homeProbability && restoredPins[1]?.homeRenderedPercent == 45,
                 "Newly checked Watch Pins prices survive without inventing timestamps")
    print("PASS: selected-pair rounding, opening-line refusal, confirmed blend, valid zero, invalid home, settled forecast suppression and snapshot formatting parity")
}
