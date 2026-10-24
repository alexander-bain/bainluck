import Foundation

/// #9483 tennis (Design C3, 2026-10-20) — the match the full-size chart
/// belongs to, kept in its header: "Zverev · Shelton", and once the match is
/// over "Final · 3–1 sets".
///
/// Kept apart from `TennisChartReading9483` on purpose: a reading prints
/// probabilities and clocks only, and never reads a score. The result here is
/// the page's own scoreboard (`event.homeScore` / `awayScore`), named in the
/// unit that scoreboard counts (`SportVocab.scoreboardUnit`: sets in tennis) —
/// never a games projection, and never a probability.
///
/// Home first, as the reading's columns beneath it are, and the score in the
/// same order as the names.
enum TennisMatchContext9483 {
    static func matchup(home: String, away: String) -> String {
        "\(home) · \(away)"
    }

    /// Nil until the match is finished: a live match's state is the cover's
    /// own live status, and nothing here claims play began. A finished match
    /// with no scoreboard says Final alone, never an invented result.
    static func result(finished: Bool, homeScore: Int?, awayScore: Int?, sportKey: String?) -> String? {
        guard finished else { return nil }
        guard let homeScore, let awayScore else { return "Final" }
        let unit = SportVocab.forSport(sportKey).scoreboardUnit
        let score = "\(homeScore)–\(awayScore)"
        return "Final · " + (unit.isEmpty ? score : "\(score) \(unit)")
    }
}
