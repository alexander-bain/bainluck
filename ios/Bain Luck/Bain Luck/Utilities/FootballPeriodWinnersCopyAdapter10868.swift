import Foundation

/// #10868 — THE FOOTBALL PERIOD-WINNER CARD'S READER COPY, in one file.
///
/// PILLARS: FORMATTING. SHIP: the completed `nfl-live` page's quarter-winner
/// card speaks plainly — which side won each quarter by its own contract, what
/// each side's own pregame chance was, and that quarter points are not the
/// running score.
///
/// Prose only. Every period LABEL on the card comes from the app's one period
/// owner (`PeriodLabel.lineScoreColumn`, spoken through `PeriodLabel.spoken`);
/// nothing here reads, parses or labels a clock or period string. The words
/// "quarter" and "overtime" below are the approved design's reader copy
/// (`FinalQuarterOutlooks.tsx`), kept in this one file so the period-label
/// guard's allowlist names exactly the copy and nothing else.
enum FootballPeriodWinnersCopy10868 {
    static let eyebrow = "Quarter winners · final"
    /// Only when an admitted winner's own pregame chance was the lowest of its quarter's.
    static let upsetTitle = "The quarter that broke the script"
    static let title = "Quarter winners against the pregame chances"
    static func upsetSummary(team: String, period: String, chance: String) -> String {
        "\(team) took \(period) with a \(chance) pregame chance."
    }

    static let legendPregame = "Hollow dots · pregame chance"
    static let legendWon = "Won the quarter"
    static let scoreCaption = "Final quarter points"
    static let scaleTop = "100%"
    static let scaleBottom = "0%"

    static let won = "Won"
    static let lost = "Lost"
    static let unconfirmed = "Result unconfirmed"

    static let pregameTitle = "Pregame chance"
    static let resultTitle = "Market result"
    static let unavailable = "Unavailable"
    static let pregameUnavailable = "Pregame trade unavailable"
    static let originalUnavailable = "Original no longer listed"
    static let originalAmbiguous = "Original listed more than once"
    static let noCurrent = "No current chance after the final"

    static let sidesLabel = "Final quarter outcome"
    static let details = "Details"
    static let expand = "Open card"
    static let selectionMissing = "Choose a quarter outcome to compare"
    static let selectPanel = "Select"

    static let pointsNote = "Points shown are for each quarter, not the running score. Each dot has its own trade time."
    static func regulationOnlyNote(period: String) -> String { "\(period) excludes overtime." }
    static let regulationOnly = "No overtime"

    static let tie = "Tie"
    static let tiedPeriod = "Tied quarter"
    static func outscore(team: String) -> String { "\(team) outscore opponent" }
    static func caption(period: String, outcome: String) -> String { "\(period) · \(outcome)" }

    static func minuteEnding(_ clock: String) -> String { "Minute ending \(clock)" }
    static func hourEnding(_ clock: String) -> String { "Hour ending \(clock)" }
    /// The Details' provenance for the same admitted chance.
    static func baselineProvenance(_ clock: String) -> String { "Pregame trade baseline · \(clock)" }

    static let points = "points"
    static let scoreUnavailable = "Quarter points unavailable"
    static func scoreProvenance(recorded clock: String?) -> String {
        clock.map { "Score recorded \($0) · exact quarter-end time unavailable" }
            ?? "Exact quarter-end time unavailable"
    }
    /// A quarter's points never name its winner; each original's own contract does.
    static let winnerByContract = "Each outcome's result is its own contract's"
}
