import Foundation

/// #9483 — the recognizable NFL event page (design reference #10868: browser
/// v105, native v107, with v157–v159's reading corrections).
///
/// Alex, build 51: the app "does not resemble the mockups". The reviewed page
/// leads with BOTH competitors' chances, each under its own name and colour
/// with its pregame number beside it, puts the actual score between them, and
/// lets a substantial paired journey — one line per team — anchor the page.
/// This file holds the decisions; the views only draw them.
///
/// NFL and NBA (v328's NBA slice adopts the same headline, paired journey and
/// card deck), by the release brief: no other sport changes shape here, so
/// every gate starts with `applies(sportKey:)`. Player milestone cards stay
/// NFL only (`isNFL`).
nonisolated enum NFLRecognizablePage9483 {
    static let sportKey = "americanfootball_nfl"

    static func applies(sportKey: String?) -> Bool {
        isNFL(sportKey: sportKey) || NBAEventCards9483.applies(sportKey: sportKey)
    }

    static func isNFL(sportKey: String?) -> Bool {
        sportKey == Self.sportKey
    }
}

// MARK: - The paired journey

/// One vertex of the away team's line.
nonisolated struct PairedWinVertex9483: Equatable {
    let date: Date
    let probability: Double
}

/// The chart's second line: the away team's chance, beside the home line.
///
/// IT IS THE BLEND READ FROM THE OTHER SIDE, NOT A SECOND SOURCE. It is admitted
/// exactly where #10456's balance ink is admitted — a served pair on a sport
/// whose winner market prices no draw, one drawn series, team colours known —
/// because that admission is what makes `1 − home` the away chance: the backend
/// serves `current_odds.away_probability` as `round(1 − home, 6)` on those pages
/// (#2085). One number per question is still one number ("the blend is the
/// product"); the page simply draws it for both teams, as its headline prints it.
/// Where the ink is refused (a draw-priced sport, a source set, no served pair)
/// the second line is refused too, and the page keeps today's single line.
/// Main-actor, like `ChartDataPoint` it reads.
enum PairedWinLines9483 {
    static func admits(sportKey: String?, binaryAdmission: BinaryWinBalanceAdmission) -> Bool {
        NFLRecognizablePage9483.applies(sportKey: sportKey) && binaryAdmission == .admittedBinary
    }

    /// The away line over the same observation run, vertex for vertex. A run is
    /// never joined to its neighbour here either (#7878): the caller passes one
    /// run at a time and gives each its own series.
    static func awayRun(_ run: [ChartDataPoint]) -> [PairedWinVertex9483] {
        run.map { PairedWinVertex9483(date: $0.date, probability: 1 - $0.probability) }
    }

    /// The live edge's last segment, read from the away side. The home tail is
    /// the overlay's (`LiveChartEdgeMarker`, which glides it); the away tail is
    /// drawn in the plot without a glide, so its end is the same instant as the
    /// home tail's.
    static func awayTail(_ tail: LiveEdgeTail) -> [PairedWinVertex9483] {
        [tail.from, tail.to].compactMap { $0 }.map {
            PairedWinVertex9483(date: $0.date, probability: 1 - $0.probability)
        }
    }
}

// MARK: - The paired headline

/// What the NFL headline prints, side by side.
///
/// Adopted arms only: a priced pair before or during the game, and a decided
/// final. Everything else — an opening line (#9470), a draw-priced winner, a
/// venue-settled verdict (#6381), a level or unresolved final — returns nil and
/// keeps today's hero, whose wording for those states is settled and tested.
struct NFLPairedHeadline9483: Equatable {
    nonisolated struct Side: Equatable {
        /// The big figure: a percentage, or "Won"/"Lost" at the final.
        let figure: String
        /// The pregame chance under it, or nil where it would repeat the figure
        /// (before kickoff the current price IS the pregame number).
        let pregame: String?
        /// At the final: whether this side won. Nil while it is still a price.
        let won: Bool?
    }

    nonisolated enum Center: Equatable {
        case versus
        case score(away: Int, home: Int, final: Bool)
    }

    let away: Side
    let home: Side
    let center: Center

    /// A side's pregame line, as the hero's baseline caption words it
    /// ("Pre-match" when served, "Opened" when it is the opening fallback).
    static func pregameSides(_ reading: PrematchReading?) -> (away: String, home: String)? {
        guard let reading else { return nil }
        let word = reading.captionWord
        return ("\(word) \(formatProbability(reading.awayProbability, renderedPercent: reading.percents[0]))",
                "\(word) \(formatProbability(reading.homeProbability, renderedPercent: reading.percents[1]))")
    }

    /// The priced arm: before or during the game.
    ///
    /// `awayText`/`homeText` are the hero pair as the existing hero renders it
    /// (#2085's both-served-or-neither percents), so the two headlines can never
    /// print different numbers for one price.
    static func priced(
        awayText: String, homeText: String, live: Bool,
        score: (away: Int, home: Int)?, pregame: PrematchReading?
    ) -> NFLPairedHeadline9483 {
        let sides = live ? pregameSides(pregame) : nil
        return NFLPairedHeadline9483(
            away: Side(figure: awayText, pregame: sides?.away, won: nil),
            home: Side(figure: homeText, pregame: sides?.home, won: nil),
            center: score.map { .score(away: $0.away, home: $0.home, final: false) } ?? .versus)
    }

    /// The final arm: a decided result only. `homeWon` is `EventOutcome`'s
    /// verdict — nil for a draw or an unresolved final, where "Won"/"Lost"
    /// would be false on both sides, so the arm declines.
    static func final(
        homeWon: Bool?, score: (away: Int, home: Int)?, pregame: PrematchReading?
    ) -> NFLPairedHeadline9483? {
        guard let homeWon else { return nil }
        let sides = pregameSides(pregame)
        return NFLPairedHeadline9483(
            away: Side(figure: homeWon ? "Lost" : "Won", pregame: sides?.away, won: !homeWon),
            home: Side(figure: homeWon ? "Won" : "Lost", pregame: sides?.home, won: homeWon),
            center: score.map { .score(away: $0.away, home: $0.home, final: true) } ?? .versus)
    }

    /// The small word under the score.
    var centerCaption: String? {
        switch center {
        case .versus: return nil
        case .score(_, _, let final): return final ? "Final score" : "Score"
        }
    }

    /// One sentence for VoiceOver, in reading order.
    func accessibilityLabel(awayName: String, homeName: String) -> String {
        var parts: [String] = []
        for (name, side) in [(awayName, away), (homeName, home)] {
            var line = "\(name) \(side.figure)"
            if let pregame = side.pregame { line += ", \(pregame)" }
            parts.append(line)
        }
        if case let .score(a, h, final) = center {
            parts.append("\(final ? "Final score" : "Score") \(awayName) \(a), \(homeName) \(h)")
        }
        return parts.joined(separator: ". ")
    }
}
