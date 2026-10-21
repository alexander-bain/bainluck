import Foundation

/// #9483 tennis — the completed match's headline: each competitor's chance
/// before the match, prominent under their own full name, beside the actual
/// final result in sets.
///
/// Design's adoption finding of 2026-10-20 (the selected compact tennis
/// header, `tennis-headline-probability-adoption-20261020`): the old hero led
/// with "Zverev Win" and small set counts, and both chances sat in one
/// low-contrast caption between the crests ("Pre-match 41% – 59%"), where a
/// reader could not tell whose number was whose. This decides what the
/// adopted header prints; the view only draws it.
///
/// Every value comes from what the old hero already read, in the same way:
///
/// - The chances are `PrematchReading` — the served pre-match reading when it
///   is usable, else the opening line — through `DrawPricedWinner` and the
///   reading's own whole percents, exactly as the old caption printed them.
///   The label names the arm: "Pre-match win chance" for the served reading,
///   "Opening win chance" for the opening fallback. Nothing is derived from
///   the start time, the chart or the result. A side with no usable reading
///   is Unavailable — never 0% or 100% read off who won.
/// - Won/Lost is `EventOutcome`, the old verdict's own input. A tennis match
///   cannot end level, so a level result names no winner here, and neither
///   does an unresolved one.
/// - The result is the scoreboard, away–home like the names, in the unit the
///   scoreboard counts (`SportVocab.scoreboardUnit`, "sets"). No scoreboard,
///   no result row: the FINAL chip above already says the match is over.
///
/// No projection: a finished match's served projection is today's, not one
/// from before the match, and `showsProjection` already withholds it once a
/// match is finished. Nothing here renames it.
struct TennisFinalHeadline9483: Equatable {
    struct Side: Equatable {
        /// The competitor's full name as served.
        let name: String
        /// The whole-percent chance before the match, or nil when unavailable.
        let chance: String?
        /// Whether this side won; nil when the result names no winner.
        let won: Bool?
    }

    struct Result: Equatable {
        let away: Int
        let home: Int
        /// The scoreboard's unit, "sets" in tennis; empty if a sport has none.
        let unit: String

        /// Away first, as the names are.
        var figure: String { "\(away)\u{2013}\(home)" }
        /// The word stays attached to its unit: "Final · sets".
        var caption: String { unit.isEmpty ? "Final" : "Final · \(unit)" }
    }

    let away: Side
    let home: Side
    /// What the chances are, named for the arm that supplied them.
    let chanceLabel: String
    let result: Result?

    static let servedLabel = "Pre-match win chance"
    static let openingLabel = "Opening win chance"
    static let unavailableText = "Unavailable"

    /// Completed tennis only. Before and during a match, and every other
    /// sport, keep today's hero.
    static func applies(sportKey: String?, status: String?) -> Bool {
        sportKey?.hasPrefix("tennis") == true && EventState.isFinished(status)
    }

    static func resolve(
        awayName: String, homeName: String, sportKey: String?,
        outcome: EventOutcome, score: (away: Int, home: Int)?, pregame: PrematchReading?
    ) -> TennisFinalHeadline9483 {
        let pair = pregame.flatMap {
            DrawPricedWinner.printablePair(
                away: $0.awayProbability, home: $0.homeProbability, sport: sportKey)
        }
        let awayChance = pair.flatMap { pair in
            pair.away.map { formatProbability($0, renderedPercent: pregame?.percents[0]) }
        }
        let homeChance = pair.map { formatProbability($0.home, renderedPercent: pregame?.percents[1]) }
        let vocab = SportVocab.forSport(sportKey)
        let homeWon: Bool?
        switch outcome {
        case .home: homeWon = true
        case .away: homeWon = false
        case .draw, .undecided: homeWon = nil
        }
        return TennisFinalHeadline9483(
            away: Side(name: awayName, chance: awayChance, won: homeWon.map { !$0 }),
            home: Side(name: homeName, chance: homeChance, won: homeWon),
            chanceLabel: pregame?.isServed == false ? openingLabel : servedLabel,
            result: score.map { Result(away: $0.away, home: $0.home, unit: vocab.scoreboardUnit) })
    }

    /// One VoiceOver sentence, in reading order, from the values drawn.
    var accessibilityLabel: String {
        var parts = [away, home].map { side -> String in
            var line = side.name
            if let won = side.won { line += ", \(won ? "won" : "lost")" }
            return line + ", \(chanceLabel.lowercased()) \(side.chance ?? Self.unavailableText.lowercased())"
        }
        if let result {
            let unit = result.unit.isEmpty ? "" : " \(result.unit)"
            parts.append("Final\(unit), \(away.name) \(result.away), \(home.name) \(result.home)")
        }
        return parts.joined(separator: ". ")
    }
}
