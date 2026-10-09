import Foundation

// Behavioral tests call the actual decoder and presentation used by SwiftUI.
// Producer fixtures are representative test rows; mutations below are explicit
// edge-case controls, not captures or claims about live NFL games.
@main struct NFLRichLandingChecks {
    static func check(_ condition: Bool, _ message: String) { precondition(condition, message) }
    static func main() throws {
        let fixtureDirectory = URL(fileURLWithPath: CommandLine.arguments[1])
        func response(_ name: String) throws -> [String: Any] {
            let envelope = try JSONSerialization.jsonObject(with: Data(contentsOf: fixtureDirectory.appendingPathComponent(name))) as! [String: Any]
            check((envelope["_representative"] as! String).contains("NOT production"), "fixture must retain provenance")
            return envelope["response"] as! [String: Any]
        }
        let index = try response("discovery.json"), hub = try response("week.json")
        let week = try WatchNFLCollectionDecoder.weeks(JSONSerialization.data(withJSONObject: index), season: 2026)[0]
        func membership(_ body: [String: Any]) throws -> WatchNFLMembership {
            try WatchNFLCollectionDecoder.membership(JSONSerialization.data(withJSONObject: body), week: week)
        }
        func game(id: Int = 502, replacing fields: [String: Any] = [:], removing keys: [String] = []) throws -> WatchNFLGame {
            var body = hub
            var sections = body["sections"] as! [[String: Any]]
            var rows = sections[0]["members"] as! [[String: Any]]
            let position = rows.firstIndex { ($0["type"] as? String) == "event" && ($0["id"] as? Int) == id }!
            var row = rows[position], card = rows[position]["card"] as! [String: Any]
            for (key, value) in fields { card[key] = value }
            for key in keys { card.removeValue(forKey: key) }
            row["card"] = card; rows[position] = row; sections[0]["members"] = rows; body["sections"] = sections
            return try membership(body).games.first { $0.id == id }!
        }
        let now = ISO8601DateFormatter().date(from: "2026-10-04T17:00:00Z")!
        func show(_ value: WatchNFLGame) -> WatchNFLGamePresentation { WatchNFLGamePresentation(game: value, now: now) }
        let original = try membership(hub)
        check(original.games.map(\.id) == [502, 501], "published producer order retained")
        check(WatchNFLGamePresentation.availableGamesText(original) == "2 games available on Watch", "count actual available members, not declared total4")
        let live = show(try game())
        check(live.awayName == "Dallas Cowboys" && live.awayScore == "3", "away score tied to full away name")
        check(live.homeName == "Philadelphia Eagles" && live.homeScore == "7", "home score tied to full home name")
        check(live.stateText == "Live" && live.scheduledStart == nil, "only supplied lifecycle, no old kickoff beside live game")
        check(live.scoreContext == "Score observation age unknown", "fixture supplies no score clock")
        check(live.chanceText == "Win chance unavailable" && live.chanceContext == nil, "fixture has no chance")

        let scheduled = show(try game(id: 501))
        check(scheduled.stateText == "Scheduled" && scheduled.scheduledStart != nil, "supplied scheduled date")
        check(scheduled.homeScore == nil && scheduled.awayScore == nil, "scheduled missing scores do not become zeros")
        let scheduledZeros = show(try game(id: 501, replacing: ["home_score": 0, "away_score": 0]))
        check(scheduledZeros.homeScore == nil && scheduledZeros.scoreContext == nil, "scheduled placeholders are not in-play scores")
        let tbd = show(try game(id: 501, replacing: ["start_is_tbd": true]))
        check(tbd.scheduledStart == nil && tbd.startMissingText == "Start time to be announced", "TBD is explicit")
        let badDate = show(try game(id: 501, replacing: ["commence_time": "invalid"]))
        check(badDate.scheduledStart == nil && badDate.startMissingText == "Start time unavailable", "malformed start is not a fabricated date")
        let waiting = show(try game(id: 501, replacing: ["started_without_result": true, "hero_probability": 0.64, "hero_probability_source": "blend"]))
        check(waiting.stateText == "Awaiting game update" && waiting.startLabel == "Listed start" && waiting.chanceText == nil, "producer waiting flag is not inferred live")
        let notStarted = show(try game(id: 501, replacing: ["authority_not_started": true]))
        check(notStarted.stateText == "Not started", "authority not-started retained")

        let dated = show(try game(replacing: ["score_source": "espn", "score_observed_at": "2026-10-04T15:00:00Z", "hero_probability": 0.64, "hero_probability_source": "blend", "current_odds": ["captured_at": "2026-10-04T16:59:59Z"], "hero_probability_observed_at": "2026-10-04T16:59:59Z"]))
        let exactScoreObservation = ISO8601DateFormatter().date(from: "2026-10-04T15:00:00Z")!
        check(dated.scoreContext == "Score observed" && dated.scoreObservedAt == exactScoreObservation,
              "absolute score timestamp is exactly its own supplied clock")
        let sameGame = try game(replacing: ["score_source": "espn", "score_observed_at": "2026-10-04T15:00:00Z"])
        let later = WatchNFLGamePresentation(game: sameGame, now: now.addingTimeInterval(86400))
        check(later.scoreObservedAt == exactScoreObservation && later.scoreContext == dated.scoreContext,
              "keeping the sheet open cannot freeze a relative-age claim; the absolute timestamp remains true")
        check(dated.chanceText == "Philadelphia Eagles win chance: 64%", "one named supplied home chance")
        check(dated.chanceContext == "Chance observation age unknown", "neither bookmaker nor unsupported detail timestamp ages collection chance")
        let invalidClocks: [[String: Any]] = [
            ["score_source": "espn", "score_observed_at": "2026-10-04T17:00:01Z"],
            ["score_source": "espn", "score_observed_at": "invalid"],
            ["score_source": "", "score_observed_at": "2026-10-04T15:00:00Z"],
            ["score_observed_at": "2026-10-04T15:00:00Z"],
            ["score_source": "espn"],
        ]
        for fields in invalidClocks {
            let row = show(try game(replacing: fields))
            check(row.scoreContext == "Score observation age unknown" && row.scoreObservedAt == nil,
                  "partial, invalid or future observation stays unknown and exposes no date")
        }
        let partial = show(try game(replacing: ["home_score": NSNull(), "away_score": 0]))
        check(partial.homeScore == "—" && partial.awayScore == "0", "unknown and literal zero remain distinct")
        let invalidScores: [Any] = [-1, "7", true, 1.25, NSNull()]
        for invalid in invalidScores {
            let row = show(try game(replacing: ["home_score": invalid]))
            check(row.homeScore == "—" && row.awayScore == "3", "bad optional score does not erase valid member or sibling score")
        }
        let noScores = show(try game(replacing: ["home_score": NSNull(), "away_score": NSNull(), "score_source": "espn", "score_observed_at": "2026-10-04T15:00:00Z"]))
        check(noScores.scoreContext == "Score unavailable" && noScores.scoreObservedAt == nil, "a stray clock cannot create a score")

        for (probability, label) in [(0.0, "0%"), (1.0, "100%"), (0.004, "<1%"), (0.996, ">99%"), (0.455, "46%")] {
            let row = show(try game(replacing: ["hero_probability": probability, "hero_probability_source": "blend"]))
            check(row.chanceText == "Philadelphia Eagles win chance: \(label)", "probability boundary formatting")
        }
        let invalidProbabilities: [Any] = [-0.1, 1.1, "0.64", true, NSNull()]
        for invalid in invalidProbabilities {
            let row = show(try game(replacing: ["hero_probability": invalid, "hero_probability_source": "blend"]))
            check(row.chanceText == "Win chance unavailable", "invalid chance is not a number")
        }
        let absentSource = show(try game(replacing: ["hero_probability": 0.64], removing: ["hero_probability_source"]))
        check(absentSource.chanceText == "Win chance unavailable", "unclassified probability is not a forecast")
        for state in ["final", "completed", "closed", "cancelled", "postponed", "suspended", "unrecognized"] {
            let row = show(try game(replacing: ["status": state, "hero_probability": 1.0, "hero_probability_source": "settled", "home_score": 7, "away_score": 7]))
            check(row.chanceText == nil && row.chanceContext == nil, "terminal or unknown state has no forecast")
            if state == "final" || state == "completed" {
                check(row.stateText == "Final" && row.homeScore == "7" && row.awayScore == "7", "no winner inferred from final score or probability")
            }
        }
        let long = "Association Sportive de Saint-Étienne Full Canonical Name"
        check(show(try game(replacing: ["home_team": long])).homeName == long, "full producer name survives")
        let unknownState = show(try game(replacing: ["status": NSNull()]))
        check(unknownState.stateText == "Game state unavailable" && unknownState.chanceText == nil, "missing state is never scheduled or live")
        var withdrawn = hub; withdrawn["state"] = "withdrawn"
        check(WatchNFLGamePresentation.availableGamesText(try membership(withdrawn)) == "This collection is no longer available.", "withdrawn header has no game count")
        print("NFL rich-landing behavioral checks PASS")
    }
}
