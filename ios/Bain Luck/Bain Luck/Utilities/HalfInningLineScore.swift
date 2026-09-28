import Foundation

// MARK: - Baseball's Game Segments fallback, read by half-inning (#4961)

/// Builds a baseball line score from polled `espn_history` rows when the event
/// payload serves no stored arrays.
///
/// #4961. The generic fallback takes each inning's LAST polled row as the score
/// "through" that inning. In baseball that row is usually mid-inning: on
/// 15319671 (Guardians 2 @ Royals 3) the last 8th-inning row was `Top 8th` 2–2
/// and the next was `Top 9th` 2–3, so the Royals' bottom-of-the-8th run was
/// printed in the 9th, an inning they never batted. The stored line score
/// reads `KC 1 0 0 0 1 0 0 1 X`.
///
/// The half-inning in the label says when each side's score is closed. The
/// away side cannot score in a Middle or Bottom half, and the home side cannot
/// score in a Top or Middle half:
///
/// | side | inning N is closed at rows labelled   |
/// |------|---------------------------------------|
/// | away | `Middle N`, `Bottom N`, `End N`       |
/// | home | `End N`, `Top N+1`, `Middle N+1`      |
///
/// Scores only go up, so the score closing inning N is at least every reading
/// taken up to that window and at most every reading taken from it on (and
/// the final). When the two bounds meet, the inning's close is known exactly —
/// a reading inside the window pins it, and so does a later reading that has
/// not moved. An inning's runs are printed only when both of its ends are
/// known; anything else is `·`. Sparse, never misplaced.
///
/// Returns `nil` when no row carries a half-inning label (the caller keeps its
/// generic inference for that vocabulary), or when the readings go backwards
/// (they describe two games; the card is not drawn).
nonisolated enum HalfInningLineScore {
    struct Snapshot: Equatable, Sendable {
        let period: String
        let homeScore: Int
        let awayScore: Int
    }

    struct Rows: Equatable, Sendable {
        let home: [LineScoreCell]
        let away: [LineScoreCell]
        /// Index of the last inning a row was polled in (the one that may still
        /// be moving on a live game), for `StoredLineScore.squared`.
        let lastObserved: Int
    }

    private enum Half: Int { case top = 0, middle, bottom, end }

    private struct Reading {
        let inning: Int
        let half: Half
        let home: Int
        let away: Int
        /// Game order: four slots per inning.
        var position: Int { 4 * inning + half.rawValue }
    }

    static func rows(
        _ snapshots: [Snapshot],
        isFinished: Bool,
        homeFinal: Int?,
        awayFinal: Int?
    ) -> Rows? {
        let readings = snapshots.compactMap { snapshot -> Reading? in
            guard let (half, inning) = parse(snapshot.period) else { return nil }
            return Reading(inning: inning, half: half, home: snapshot.homeScore, away: snapshot.awayScore)
        }
        guard let latest = readings.max(by: { $0.position < $1.position }) else { return nil }
        let innings = max(9, latest.inning)
        let finals = isFinished ? (home: homeFinal, away: awayFinal) : (home: nil, away: nil)

        // Each side's score at the close of inning n, when the readings pin it.
        func closed(_ n: Int, home: Bool) -> Int?? {
            if n == 0 { return .some(0) }
            // The window of rows at which inning n is closed for this side.
            let first = home ? 4 * n + Half.end.rawValue : 4 * n + Half.middle.rawValue
            let last = home ? 4 * (n + 1) + Half.middle.rawValue : 4 * n + Half.end.rawValue
            let score: (Reading) -> Int = { home ? $0.home : $0.away }
            let lower = readings.filter { $0.position <= last }.map(score).max() ?? 0
            var uppers = readings.filter { $0.position >= first }.map(score)
            if let final = home ? finals.home : finals.away { uppers.append(final) }
            guard let upper = uppers.min() else { return .some(nil) }
            if lower > upper { return nil }
            return .some(lower == upper ? lower : nil)
        }

        var homeClosed: [Int?] = []
        var awayClosed: [Int?] = []
        for n in 0...innings {
            guard let h = closed(n, home: true), let a = closed(n, home: false) else { return nil }
            homeClosed.append(h)
            awayClosed.append(a)
        }

        var homeUnneededAt: Int?
        if let homeFinal = finals.home, let awayFinal = finals.away,
           homeFinal > awayFinal, homeClosed[innings - 1] == homeFinal {
            // The home side won without scoring after inning L−1, so it led when
            // the away side's last turn ended: the bottom of L was never played
            // (the scoreboard's `X`), and the away total closes L.
            homeUnneededAt = innings
            awayClosed[innings] = awayFinal
        }

        func cell(_ n: Int, closed: [Int?], home: Bool) -> LineScoreCell {
            if home, n == homeUnneededAt { return .notNeeded }
            var after = closed[n]
            if !isFinished {
                if n > latest.inning { return .notPlayed }
                if n == latest.inning, after == nil {
                    // The inning in progress shows its running score, the way the
                    // stored-array path does — once this side has come up.
                    let batted = !home || latest.half == .bottom || latest.half == .end
                    guard batted else { return .notPlayed }
                    after = home ? latest.home : latest.away
                }
            }
            guard let before = closed[n - 1], let after, after >= before else { return .unknown }
            return .score(after - before)
        }

        return Rows(
            home: (1...innings).map { cell($0, closed: homeClosed, home: true) },
            away: (1...innings).map { cell($0, closed: awayClosed, home: false) },
            lastObserved: latest.inning - 1
        )
    }

    /// `Top 8th` / `Middle 8th` / `Mid 8th` / `Bottom 8th` / `End 8th` /
    /// `End of 8th Inning` → (half, 8). Anything else is not a half-inning.
    private static func parse(_ raw: String) -> (Half, Int)? {
        let s = raw.trimmingCharacters(in: .whitespaces).lowercased()
        guard let range = s.range(
            of: #"^(top|middle|mid|bottom|end)\s+(?:of\s+(?:the\s+)?)?(\d+)"#,
            options: .regularExpression
        ) else { return nil }
        let words = s[range].split(whereSeparator: { $0 == " " })
        guard let first = words.first, let digits = words.last.flatMap({ Int($0) }), digits > 0 else {
            return nil
        }
        switch first {
        case "top": return (.top, digits)
        case "middle", "mid": return (.middle, digits)
        case "bottom": return (.bottom, digits)
        default: return (.end, digits)
        }
    }
}
