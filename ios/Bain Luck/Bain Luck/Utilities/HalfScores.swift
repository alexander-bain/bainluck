import Foundation

/// The score one half of a game was actually played to.
///
/// #7943. The event page's half maps — 1st/2nd half margin, 1st/2nd half total —
/// had no notion of a result. On a Final game the full-game Points map above
/// them said `FINAL 34 points`, marked it on its rail and graded its ladder,
/// while all four half cards below drew a forecast-shaped distribution and
/// stopped. Same page, same card family (notice 35), one of them a result and
/// four of them still a forecast of something that had already happened.
///
/// The number is in the payload and is not an inference: `espn_history` carries
/// the CUMULATIVE score against a period label, so the score at the halftime
/// boundary IS the first half. On the 2026-09-21 MNF specimen (event 14780545)
/// `Halftime` is observed twelve times at 14–3 and `Final` at 28–6, and both
/// settled venue ladders independently pin LAR by 11 in each half.
///
/// 🔴 THIS IS A CUMULATIVE READ, NOT A SPLIT. `SegmentBreakdown` (per-QUARTER
/// scoring, `EventDetailView`) cannot report a period whose predecessor was
/// never observed, because a per-period split is a DIFFERENCE of two readings
/// and a gap makes it unattributable. A half score is not a difference — it is
/// one cumulative reading taken at a boundary — so a poller that missed the
/// whole of the 1st quarter still reports the half correctly. The two rules look
/// similar and are not; do not "unify" them.
nonisolated struct HalfScoreSplit: Equatable, Sendable {
    let home: Int
    let away: Int

    /// Home-signed, exactly like every margin the maps plot.
    var margin: Int { home - away }
    var total: Int { home + away }
}

/// One cumulative `espn_history` reading, reduced to what the half rule needs.
nonisolated struct HalfScoreReading: Equatable, Sendable {
    let period: String
    let home: Int
    let away: Int
    let date: Date

    init(period: String, home: Int, away: Int, date: Date) {
        self.period = period
        self.home = home
        self.away = away
        self.date = date
    }
}

/// Which half a map is drawn for.
///
/// An explicit value, never the card's title. The two half maps are told apart
/// by their `id` string elsewhere in `MarketMapView` for grouping, but a RESULT
/// keyed on a display label is a classifier keyed on a name: it breaks silently
/// the day the copy changes, and it cannot be unit-tested without asserting the
/// copy too.
nonisolated enum GameHalf: Equatable, Sendable {
    case first
    case second
}

nonisolated enum HalfScores {
    /// What each half was played to, and whether the second one is over.
    nonisolated struct Pair: Equatable, Sendable {
        /// The first half, once its boundary has been observed. Always complete
        /// when present — a halftime reading means the half is over.
        let first: HalfScoreSplit?
        /// The second half: the game so far, minus the first. `nil` unless the
        /// arithmetic below is sound.
        let second: HalfScoreSplit?
        /// Whether ``second`` is a finished half rather than one in play, so the
        /// caller can pick `FINAL` or `ACTUAL` the way the full-game card does.
        let secondIsComplete: Bool

        static let none = Pair(first: nil, second: nil, secondIsComplete: false)

        /// What this half was played to, if it is knowable.
        func score(_ half: GameHalf) -> HalfScoreSplit? {
            switch half {
            case .first: return first
            case .second: return second
            }
        }

        /// Whether this half is OVER, which is what picks `FINAL` over `ACTUAL`.
        ///
        /// A present `first` is always complete: the only thing that produces
        /// one is the halftime boundary, and reaching it is what ending the
        /// first half means. The second half borrows the game's own verdict.
        func isComplete(_ half: GameHalf) -> Bool {
            switch half {
            case .first: return first != nil
            case .second: return second != nil && secondIsComplete
            }
        }
    }

    /// Split a game's cumulative readings into its two halves.
    ///
    /// Sparse but never wrong: every branch that cannot be computed soundly
    /// returns `nil` for that half rather than a number the reader would have no
    /// way to distrust.
    ///
    /// - Parameters:
    ///   - readings: cumulative `espn_history` points, in any order.
    ///   - currentHome: the scoreboard's home score (the hero's own number).
    ///   - currentAway: the scoreboard's away score.
    ///   - isDone: whether the GAME is over, which is what makes a second half
    ///     complete. The first half's completeness never depends on it.
    static func split(
        readings: [HalfScoreReading],
        currentHome: Int?,
        currentAway: Int?,
        isDone: Bool
    ) -> Pair {
        let ordered = readings.sorted { $0.date < $1.date }

        // The LAST halftime reading, not the first: the boundary is held for
        // several polls (twelve on the specimen) and a late correction to the
        // half's score has to win over the first sighting of it.
        guard let boundaryIndex = ordered.lastIndex(where: {
            PeriodLabel.isFirstHalfBoundary($0.period)
        }) else {
            return .none
        }
        let boundary = ordered[boundaryIndex]
        let first = HalfScoreSplit(home: boundary.home, away: boundary.away)

        // 🔴 OVERTIME FOLDS INTO THE SUBTRACTION AND IS INVISIBLE ONCE IT HAS.
        // `final − halftime` is only the second half when nothing was played
        // after the second half. An OT period anywhere in the readings means the
        // difference is "everything after halftime", which is a different
        // quantity wearing the second half's name.
        guard !ordered.contains(where: { PeriodLabel.isAfterRegulation($0.period) }) else {
            return Pair(first: first, second: nil, secondIsComplete: false)
        }

        // At halftime the second half has not started, and a `0–0` marker for a
        // half nobody has played is noise, not a result. Requiring a reading
        // AFTER the boundary is what distinguishes "not started" from "level".
        let secondHalfUnderway = ordered.indices.contains(where: { $0 > boundaryIndex })
        guard secondHalfUnderway || isDone,
              let nowHome = currentHome, let nowAway = currentAway else {
            return Pair(first: first, second: nil, secondIsComplete: false)
        }

        // A scoreboard behind the history it is paired with would subtract into
        // a negative half. Refuse rather than print one.
        let secondHome = nowHome - boundary.home
        let secondAway = nowAway - boundary.away
        guard secondHome >= 0, secondAway >= 0 else {
            return Pair(first: first, second: nil, secondIsComplete: false)
        }

        return Pair(
            first: first,
            second: HalfScoreSplit(home: secondHome, away: secondAway),
            secondIsComplete: isDone
        )
    }
}
