import Foundation

// MARK: - #683 the widest chart asks for the question's whole recovered history
//
// The Evolution chart's widest chip asked for a fixed `hours=4320`. Root's control
// (d58, 10/15): a settled question whose recovered Kalshi intervals are 189 days
// old serves them at 4800h and draws NOTHING at 4320h. A bigger constant only moves
// the cliff, and a window derived from our own `created_at` still misses what the
// venue recorded before we first ingested the market. Only the server knows where
// its history begins (Root ruling B).
//
// THE CONTRACT (calibration PR #11083, web half PR #11089). The widest chip adds
// `range=full` to the request it already makes and keeps sending `hours`:
//
//  - a server that does not know the option ignores it and serves exactly today's
//    window, so a build that ships first loses nothing;
//  - a server that knows it reads the archive with no time bound and our own older
//    captures back to the first one, span-sampled rather than tail-cut, and adds a
//    `history_range` block saying where the drawn history begins and why.
//
// Every shorter chip sends no `range`, so its request is byte-for-byte unchanged.
//
// 🔴 THE EARLIEST DRAWN POINT IS NOT THE QUESTION'S OPEN. `archive_coverage` is
// the import's own word: `complete` only when every charted outcome's import is
// complete. When the drawn span begins at a recovered record whose import is not
// complete, the chart may not say "prices only go back N days" — the venue may hold
// older prices nobody has imported yet.

/// `history_range` on a `range=full` response: metadata only, every key optional.
/// An unknown `window_start_basis` is kept as its raw word and reads as "starts at
/// `window_start`" — the server has added values before (`live_first_capture`,
/// `venue_first_observation`) and will again.
nonisolated struct FuturesHistoryRange: Codable, Sendable, Equatable {
    @TolerantNumeric var requested: String? = nil
    @TolerantNumeric var windowStart: String? = nil
    @TolerantNumeric var windowStartBasis: String? = nil
    @TolerantNumeric var archiveCoverage: String? = nil
    @TolerantNumeric var archiveVenueOpen: String? = nil
    @TolerantNumeric var thinnedOutcomes: [Int]? = nil
    @TolerantNumeric var liveThinned: Bool? = nil

    static func == (lhs: Self, rhs: Self) -> Bool {
        lhs.requested == rhs.requested && lhs.windowStart == rhs.windowStart
            && lhs.windowStartBasis == rhs.windowStartBasis
            && lhs.archiveCoverage == rhs.archiveCoverage
            && lhs.archiveVenueOpen == rhs.archiveVenueOpen
            && lhs.thinnedOutcomes == rhs.thinnedOutcomes && lhs.liveThinned == rhs.liveThinned
    }
}

nonisolated enum EvolutionFullRange {
    /// The one value the option takes.
    static let full = "full"
    /// The import's own word for an outcome whose whole venue history was recovered.
    static let coverageComplete = "complete"
    /// Bases at which the drawn span begins on a venue's record rather than on our
    /// own captures or the requested hours.
    static let recoveredRecordBases: Set<String> = ["archive_first_interval", "venue_first_observation"]

    /// Only the widest chip asks for the whole history.
    static func asksForFullHistory(_ range: EvolutionTimeRange) -> Bool {
        range == .season
    }

    /// `["range": "full"]` for a full read, otherwise nothing — so the default
    /// request stays byte-for-byte what it was.
    static func query(fullRange: Bool) -> [String: String] {
        fullRange ? ["range": full] : [:]
    }

    /// The block, only when the server says it served a full read.
    static func served(_ block: FuturesHistoryRange?) -> FuturesHistoryRange? {
        block?.requested == full ? block : nil
    }

    /// True when the drawn span begins on a recovered venue record whose import is
    /// not known to be complete: the first point drawn is where the RECORD we hold
    /// begins, not where the question's prices begin.
    static func earliestPointIsUnproven(_ block: FuturesHistoryRange?) -> Bool {
        guard let block = served(block), let basis = block.windowStartBasis,
              recoveredRecordBases.contains(basis) else { return false }
        return block.archiveCoverage != coverageComplete
    }
}
