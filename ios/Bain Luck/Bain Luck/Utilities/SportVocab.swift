import Foundation

// MARK: - Sport scoring vocabulary

/// What a sport's markets are quoted in, and whether its scoreboard counts the
/// same thing.
///
/// This is the Swift half of `frontend/lib/marketMapUtils.ts` (`sportVocab`),
/// ported verbatim in meaning — the phone was the surface that still had none.
/// Alex, on the live Pegula–Fernandez US Open match (2026-09-04, 10:26am PT):
/// the event page offered him "Proj. 13-13", a margin rail reading "Fernandez
/// by 18+ … Pegula by 18+", a "Projected total points" map over a 26.5 **game**
/// line, and an "Actual Score Diff" line that was the SET score (0, −1, 0)
/// drawn on the same ±6 axis as the books' GAME spread.
///
/// Every one of those is the same defect: a number printed in a unit the match
/// is not played in. The web fixed this class in ux/1034 B5 / #2441 and wrote
/// the rule down there — *a number in the wrong unit is worse than an absent
/// one, because it looks sourced.* This type is that rule, on iOS.
struct SportVocab: Equatable {
    /// Title of the margin/spread map, in the sport's own noun.
    let marginTitle: String
    /// Title of the total map.
    let totalTitle: String
    /// Plural unit the MARKET quotes: "games", "runs", "points". Empty for an
    /// undeclared sport, which prints the market's number and no unit.
    let unit: String
    /// Singular of ``unit``.
    let unitSingular: String
    /// The sport's own realistic spread of outcomes — not a round number. A
    /// tennis match is decided by ~6 games in the margin the market quotes; an
    /// NBA game by ~18 points.
    let marginRange: Int
    /// Whether the SCOREBOARD counts ``unit``.
    ///
    /// The default is `true`, deliberately: "the scoreboard counts what the
    /// market quotes" is true of very nearly every sport there is, and false
    /// only where play is scored in nested units and the market quotes the
    /// inner one (tennis: games inside sets). Defaulting false would silently
    /// delete a true, useful line from every sport nobody has declared yet.
    let scoreboardCountsTheUnit: Bool
    /// What the scoreboard counts INSTEAD, plural, when it does not count
    /// ``unit``. Empty where the question does not arise. It exists so a
    /// suppressed widget can say which two units it is refusing to mix — a
    /// widget that just goes quiet reads as broken.
    let scoreboardUnit: String
}

extension SportVocab {
    /// What a sport we have not declared gets.
    ///
    /// Deliberately NOT basketball's entry under another name: the titles avoid
    /// naming a unit at all and the rail is narrow, so an undeclared sport
    /// renders only what a market actually quoted, in the market's own words.
    static let unscoredInPoints = SportVocab(
        marginTitle: "Margin map",
        totalTitle: "Scoring map",
        unit: "",
        unitSingular: "",
        marginRange: 6,
        scoreboardCountsTheUnit: true,
        scoreboardUnit: ""
    )

    /// The declared sports. Substring match against the sport key, in order, so
    /// `basketball_nba` and `basketball_ncaab` share one entry — and so
    /// `tennis_wta_us_open` matches "tennis" without anyone listing the tour.
    private static let table: [(match: [String], vocab: SportVocab)] = [
        (["baseball", "mlb"], SportVocab(
            marginTitle: "Run margin map", totalTitle: "Runs map",
            unit: "runs", unitSingular: "run", marginRange: 5,
            scoreboardCountsTheUnit: true, scoreboardUnit: "")),
        (["hockey", "nhl"], SportVocab(
            marginTitle: "Goal margin map", totalTitle: "Goals map",
            unit: "goals", unitSingular: "goal", marginRange: 5,
            scoreboardCountsTheUnit: true, scoreboardUnit: "")),
        (["soccer", "mls", "epl", "uefa", "fifa"], SportVocab(
            marginTitle: "Goal margin map", totalTitle: "Goals map",
            unit: "goals", unitSingular: "goal", marginRange: 5,
            scoreboardCountsTheUnit: true, scoreboardUnit: "")),
        // A tennis match is scored in GAMES inside SETS; the market quotes a
        // game spread and a game total, and neither is a point. The scoreboard
        // reports sets, which is why this is the one row with
        // `scoreboardCountsTheUnit: false`.
        (["tennis"], SportVocab(
            marginTitle: "Game margin map", totalTitle: "Games map",
            unit: "games", unitSingular: "game", marginRange: 6,
            scoreboardCountsTheUnit: false, scoreboardUnit: "sets")),
        (["basketball", "nba", "wnba", "ncaab"], SportVocab(
            marginTitle: "Margin map", totalTitle: "Points map",
            unit: "points", unitSingular: "point", marginRange: 18,
            scoreboardCountsTheUnit: true, scoreboardUnit: "")),
        (["americanfootball", "nfl", "ncaaf"], SportVocab(
            marginTitle: "Margin map", totalTitle: "Points map",
            unit: "points", unitSingular: "point", marginRange: 18,
            scoreboardCountsTheUnit: true, scoreboardUnit: "")),
    ]

    /// The vocabulary for a sport key (`tennis_wta_us_open`, `baseball_mlb`, …).
    static func forSport(_ sportKey: String?) -> SportVocab {
        let key = (sportKey ?? "").lowercased()
        guard !key.isEmpty else { return .unscoredInPoints }
        for entry in table where entry.match.contains(where: { key.contains($0) }) {
            return entry.vocab
        }
        return .unscoredInPoints
    }

    /// `"33 games"`, or just `"33"` for a sport whose unit we have not declared.
    func withUnit(_ value: String) -> String {
        unit.isEmpty ? value : "\(value) \(unit)"
    }

    /// The sentence a widget owes a reader when it has suppressed the half it
    /// cannot state. Nil whenever the question does not arise, so a caller can
    /// bind it straight to an optional view.
    ///
    /// A map that simply drops its Final tile reads as a map that failed to
    /// load; this says which two units it refuses to mix, in the sport's own
    /// words, so a second set-scored sport declared tomorrow gets it for free.
    var unitMismatchNote: String? {
        guard !scoreboardCountsTheUnit, !scoreboardUnit.isEmpty, !unit.isEmpty else { return nil }
        return "The scoreboard reports \(scoreboardUnit), this market quotes \(unit) — we do not hold the \(unit) played yet."
    }
}
