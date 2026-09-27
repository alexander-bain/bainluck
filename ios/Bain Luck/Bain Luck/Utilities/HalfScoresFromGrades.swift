import Foundation

/// Each half's SCORE on a finished game, from the grades on its half rows — the
/// fallback for a game whose play history carries no halftime reading. #9108,
/// the iOS twin of web's `settledHalfScoresFromGrades` (`frontend/lib/marketMapUtils.ts`).
///
/// `/events/15315795`, Cruz Azul 3-3 Toluca: `espn_history` empty, so
/// ``HalfScores/split(readings:currentHome:currentAway:isDone:)`` had no boundary
/// and returned `.none`. On the phone that left ALL FOUR half cards without a
/// result — both half-margin cards drew a bare band, the 1st-half goals card drew
/// no `FINAL`, and the 2nd-half goals card (every row unpriced after settlement)
/// drew an empty tile — while the venue had graded every half row
/// `api_settlement`.
///
/// ## THE RULE (web's, unchanged)
///
/// A grade is used only to find a NUMBER, never to grade a rung on its own
/// (#6169: `/events/14637256` served eight Kalshi 2H rows all `is_winner: true`,
/// including `Over 38.5` on a 27-point half). Every way the final can split into
/// two halves (`1H + 2H = final`, per side) is a candidate, and a candidate
/// survives only if it agrees with every graded half row — totals, "wins by more
/// than" margins, and half winners. One survivor is the answer. None (the grades
/// contradict each other or the final) or two or more (they do not decide it)
/// draw nothing.
///
/// On the specimen: 1H `Over 1.5` won, `Over 2.5` lost ⇒ 2 goals; Cruz Azul (home)
/// won the 1H ⇒ 2-0. The 2H's 1-3 agrees with every 2H row.
///
/// ## WHAT FAILS CLOSED
///
///   * a row ``OutcomeVerdict`` will not grade (retraction, null source, null
///     `is_winner`) — the same rule the settled rows on this page use;
///   * an integer line (a push, where `>` and `>=` disagree);
///   * a row naming both sides or neither (``SpreadRungs/side(of:home:away:)``);
///   * a spread row not phrased "… wins … by more than N" — a `+1.5` leg means
///     the opposite of a `-1.5` one, and the sign is not trusted to survive;
///   * the served `threshold` on half spreads and winners: on the specimen it is
///     the HALF NUMBER (`1.0` / `2.0`), so a spread's line is read from its text;
///   * a row whose `period` is not `1H` / `2H`, and a team-scoped half total.
///
/// PURE: no I/O, no SwiftUI.
nonisolated enum HalfScoresFromGrades {
    private struct Vote {
        let first: Bool
        let won: Bool
        let holds: (Int, Int) -> Bool
    }

    static func split(
        rows: [GameMarketOutcome],
        finalHome: Int?,
        finalAway: Int?,
        home: String,
        away: String
    ) -> HalfScores.Pair {
        guard let finalHome, let finalAway, finalHome >= 0, finalAway >= 0 else { return .none }

        var votes: [Vote] = []
        for half in ["1H", "2H"] {
            let first = half == "1H"
            let halfRows = rows.filter { $0.period == half }

            // Totals: one verdict per line; rows that vote must agree.
            var totalGrades: [Double: Set<Bool>] = [:]
            for row in halfRows where row.marketType == "half_total" {
                guard !row.outcomeName.contains(":"), !isTeamScopedHalfTotal(row.marketName),
                      let line = row.threshold, onALine(line),
                      let verdict = verdict(row),
                      let over = overSide(row.outcomeName) else { continue }
                let cleared = over ? verdict == .won : verdict == .lost
                totalGrades[line, default: []].insert(cleared)
            }
            for (line, grades) in totalGrades where grades.count == 1 {
                votes.append(Vote(first: first, won: grades.first!, holds: { h, a in Double(h + a) > line }))
            }

            for row in halfRows {
                guard let verdict = verdict(row) else { continue }
                let won = verdict == .won
                let outcome = row.outcomeName
                if row.marketType == "half_spread" {
                    guard let line = winsByMoreThan(outcome), onALine(line),
                          let side = SpreadRungs.side(of: outcome, home: home, away: away) else { continue }
                    let isHome = side == .home
                    votes.append(Vote(first: first, won: won, holds: { h, a in Double(isHome ? h - a : a - h) > line }))
                } else if row.marketType == "half_winner" {
                    if outcome.range(of: #"^\s*(tie|draw)\b"#, options: [.regularExpression, .caseInsensitive]) != nil {
                        votes.append(Vote(first: first, won: won, holds: { h, a in h == a }))
                    } else if let side = SpreadRungs.side(of: outcome, home: home, away: away) {
                        let isHome = side == .home
                        votes.append(Vote(first: first, won: won, holds: { h, a in isHome ? h > a : a > h }))
                    }
                }
            }
        }
        guard !votes.isEmpty else { return .none }

        var found: (HalfScoreSplit, HalfScoreSplit)?
        for h1Home in 0...finalHome {
            for h1Away in 0...finalAway {
                let h2Home = finalHome - h1Home
                let h2Away = finalAway - h1Away
                let agrees = votes.allSatisfy { v in
                    (v.first ? v.holds(h1Home, h1Away) : v.holds(h2Home, h2Away)) == v.won
                }
                guard agrees else { continue }
                if found != nil { return .none }
                found = (HalfScoreSplit(home: h1Home, away: h1Away), HalfScoreSplit(home: h2Home, away: h2Away))
            }
        }
        guard let found else { return .none }
        return HalfScores.Pair(first: found.0, second: found.1, secondIsComplete: true)
    }

    private static func verdict(_ row: GameMarketOutcome) -> OutcomeVerdict? {
        OutcomeVerdict.verdict(isWinner: row.isWinner, resolutionSource: row.resolutionSource, marketResolved: true)
    }

    private static func onALine(_ x: Double) -> Bool {
        x.isFinite && x.rounded() != x
    }

    /// `true` for an Over row, `false` for an Under row, `nil` for anything else.
    private static func overSide(_ outcome: String) -> Bool? {
        let first = outcome.trimmingCharacters(in: .whitespaces).lowercased()
        if first.hasPrefix("over") { return true }
        if first.hasPrefix("under") { return false }
        return nil
    }

    /// The N in "… wins … by more than N …", or `nil` for any other phrasing.
    private static func winsByMoreThan(_ outcome: String) -> Double? {
        guard let re = try? NSRegularExpression(pattern: #"\bwins\b.*\bby more than (\d+(?:\.\d+)?)"#, options: [.caseInsensitive]),
              let m = re.firstMatch(in: outcome, range: NSRange(outcome.startIndex..., in: outcome)),
              let r = Range(m.range(at: 1), in: outcome) else { return nil }
        return Double(outcome[r])
    }

    /// Web's `isTeamScopedHalfTotal`: `A vs B: A 1st half …` is one side's total.
    private static func isTeamScopedHalfTotal(_ marketName: String) -> Bool {
        let pattern = #"^(.+?)\s+(?:vs\.?|v\.?|at|@)\s+(.+?):\s*(.+?)\s+(?:1st|2nd|first|second)\s+half\b"#
        guard let re = try? NSRegularExpression(pattern: pattern, options: [.caseInsensitive]) else { return false }
        let name = marketName.trimmingCharacters(in: .whitespaces)
        guard let m = re.firstMatch(in: name, range: NSRange(name.startIndex..., in: name)),
              let a = Range(m.range(at: 1), in: name),
              let b = Range(m.range(at: 2), in: name),
              let s = Range(m.range(at: 3), in: name) else { return false }
        let scope = name[s].trimmingCharacters(in: .whitespaces).lowercased()
        return scope == name[a].trimmingCharacters(in: .whitespaces).lowercased()
            || scope == name[b].trimmingCharacters(in: .whitespaces).lowercased()
    }
}
