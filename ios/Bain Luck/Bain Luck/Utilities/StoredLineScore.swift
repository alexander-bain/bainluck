import Foundation

// MARK: - The stored ESPN line score (#9067)

/// ESPN's per-period scores as the event payload carries them:
/// `box_score_data.home_period_scores` / `away_period_scores`.
///
/// #9067. These arrays were ingested long before any client could see them —
/// the event route served `box_score_data` with `players` only — so Game
/// Segments kept rebuilding the line score from `espn_history`, whose rows lag
/// the scoreboard. Rage #159 (Georgia Tech @ Stanford, live) printed Stanford
/// `7 · 3 · 3` beside a total of 19 because the last polled row predated a
/// touchdown the hero already had; the stored array read `[7, 3, 17, 0]`.
///
/// Decoding NEVER throws. `players` and every other key are ignored, a `null`
/// entry is a hole (the parser does leave some), and a malformed value
/// decodes as absent — a bad line score must not cost the reader the event
/// page it rides on.
nonisolated struct EventBoxScoreData: Decodable, Sendable {
    let homePeriodScores: [Int?]?
    let awayPeriodScores: [Int?]?

    private enum CodingKeys: String, CodingKey {
        // Spelled out: the decoder's `.convertFromSnakeCase` has already
        // turned `home_period_scores` into this before it reaches us.
        case homePeriodScores
        case awayPeriodScores
    }

    init(homePeriodScores: [Int?]?, awayPeriodScores: [Int?]?) {
        self.homePeriodScores = homePeriodScores
        self.awayPeriodScores = awayPeriodScores
    }

    init(from decoder: Decoder) throws {
        guard let container = try? decoder.container(keyedBy: CodingKeys.self) else {
            homePeriodScores = nil
            awayPeriodScores = nil
            return
        }
        homePeriodScores = Self.periods(container, .homePeriodScores)
        awayPeriodScores = Self.periods(container, .awayPeriodScores)
    }

    private static func periods(
        _ container: KeyedDecodingContainer<CodingKeys>, _ key: CodingKeys
    ) -> [Int?]? {
        if let ints = try? container.decodeIfPresent([Int?].self, forKey: key) {
            return ints
        }
        // `7.0` is still seven points; `7.5` is not a score and becomes a hole.
        guard let doubles = try? container.decodeIfPresent([Double?].self, forKey: key) else {
            return nil
        }
        return doubles.map { value in
            guard let value, value >= 0, value.rounded() == value else { return nil }
            return Int(value)
        }
    }
}

/// One cell of the Game Segments table.
nonisolated enum LineScoreCell: Equatable, Sendable {
    /// Points scored in this period (a live game's last one is still running).
    case score(Int)
    /// A period that was played but whose split we do not know — `·`, never `0`.
    case unknown
    /// A live game's period that has not started yet — blank, not a gap.
    case notPlayed
    /// Baseball: the home side never batted in this inning because it had
    /// already won — the scoreboard's `X`.
    case notNeeded

    var text: String {
        switch self {
        case .score(let points): return String(points)
        case .unknown: return "·"
        case .notPlayed: return ""
        case .notNeeded: return "X"
        }
    }

    var points: Int? {
        if case .score(let points) = self { return points }
        return nil
    }
}

nonisolated struct LineScoreColumn: Equatable, Sendable {
    let label: String
    let away: LineScoreCell
    let home: LineScoreCell
}

/// Builds the Game Segments columns from the stored arrays.
///
/// Returns `nil` — and the card falls back to the `espn_history` inference —
/// when the arrays are absent, the sport's period vocabulary is not known, or
/// the arrays CONTRADICT the scoreboard (they sum past its total). Otherwise
/// every row obeys the card's one promise: **its known cells never add up to
/// something the total disagrees with.**
///
/// The totals stay the scoreboard's (#1831 rule 2), so the card cannot argue
/// with the hero. When a row falls SHORT of its total — the box score is
/// fetched about once a minute and the scoreboard can be ahead of it — the
/// row's last entry is the one that is still moving (every earlier entry is a
/// closed period), so that cell becomes `·` instead of a number that fails to
/// add up.
nonisolated enum StoredLineScore {
    static func columns(
        homePeriods: [Int?]?,
        awayPeriods: [Int?]?,
        sportKey: String?,
        homeTotal: Int?,
        awayTotal: Int?,
        isFinished: Bool
    ) -> [LineScoreColumn]? {
        guard let homePeriods, let awayPeriods,
              !(homePeriods.isEmpty && awayPeriods.isEmpty),
              let vocabulary = Vocabulary(sportKey: sportKey)
        else { return nil }

        let played = max(homePeriods.count, awayPeriods.count)
        guard played <= vocabulary.maxPeriods else { return nil }
        // A live ladder shows the periods still to come, the way a scoreboard
        // does; a finished one shows what was played (plus any gap to the end
        // of regulation, which is then a real hole).
        let count = max(played, vocabulary.regulation)

        guard
            var home = row(homePeriods, count: count, isFinished: isFinished,
                           notNeededAt: vocabulary.isBaseball && isFinished
                               && homePeriods.count == awayPeriods.count - 1
                               ? homePeriods.count : nil),
            var away = row(awayPeriods, count: count, isFinished: isFinished, notNeededAt: nil),
            reconcile(&home, total: homeTotal, lastPlayed: homePeriods.count - 1),
            reconcile(&away, total: awayTotal, lastPlayed: awayPeriods.count - 1)
        else { return nil }

        // A table with no number in it is a row of dots; the fallback may do better.
        guard home.contains(where: { $0.points != nil })
                || away.contains(where: { $0.points != nil })
        else { return nil }

        return (0..<count).map { index in
            LineScoreColumn(label: vocabulary.label(index + 1), away: away[index], home: home[index])
        }
    }

    private static func row(
        _ periods: [Int?], count: Int, isFinished: Bool, notNeededAt: Int?
    ) -> [LineScoreCell]? {
        var cells: [LineScoreCell] = []
        for index in 0..<count {
            if index < periods.count {
                guard let points = periods[index] else {
                    cells.append(.unknown)
                    continue
                }
                guard points >= 0 else { return nil }
                cells.append(.score(points))
            } else if index == notNeededAt {
                cells.append(.notNeeded)
            } else {
                cells.append(isFinished ? .unknown : .notPlayed)
            }
        }
        return cells
    }

    /// `false` when the row cannot be squared with its total at all.
    private static func reconcile(_ cells: inout [LineScoreCell], total: Int?, lastPlayed: Int) -> Bool {
        guard let total else { return true }
        let known = cells.reduce(0) { $0 + ($1.points ?? 0) }
        if known > total { return false }
        let complete = !cells.contains(.unknown)
        if known < total, complete, lastPlayed >= 0 {
            // Only the last played entry can still be moving; it takes the `·`.
            // With no played entry at all the missing points sit in no cell,
            // and a finished row that short already carries its own `·`.
            cells[lastPlayed] = .unknown
        } else if known < total, complete {
            return false
        }
        return true
    }

    /// How a sport divides its game. The column NAMES are `PeriodLabel`'s —
    /// there is one period vocabulary in this app (#1832, #3273).
    private struct Vocabulary {
        let regulation: Int
        /// The most entries whose names we are sure of. Hockey stops at one
        /// extra period: the NHL's fifth entry is a SHOOTOUT in the regular
        /// season and a second extra period in the playoffs, and nothing here
        /// can tell which. Soccer's extra time is not an `OT` either.
        let maxPeriods: Int
        let isBaseball: Bool
        let sportKey: String

        init?(sportKey: String?) {
            let key = sportKey?.lowercased() ?? ""
            guard PeriodLabel.lineScoreColumn(1, sport: key) != nil else { return nil }
            self.sportKey = key
            if key.hasPrefix("baseball_") {
                regulation = 9
                maxPeriods = 30
                isBaseball = true
                return
            }
            guard let entry = PeriodLabel.barePeriodUnit.first(where: { key.hasPrefix($0.prefix) }) else {
                return nil
            }
            regulation = entry.regulation
            isBaseball = false
            if entry.prefix.hasPrefix("soccer_") {
                maxPeriods = entry.regulation
            } else if entry.prefix.hasPrefix("icehockey_") {
                maxPeriods = entry.regulation + 1
            } else {
                maxPeriods = entry.regulation + 9
            }
        }

        func label(_ n: Int) -> String {
            PeriodLabel.lineScoreColumn(n, sport: sportKey) ?? ""
        }
    }
}
