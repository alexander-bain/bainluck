import Foundation

// MARK: - #10244 the verified title chart draws the source's own history
//
// The opted-in `/probability-timeline` answers the CURRENT column (one verified
// number per outcome) and names whose history the chart shows. Its history lines,
// though, are a median of each sportsbook's RAW implied price per bucket — the
// margin is still in them. On /futures/86832 the Bills line ended at 13.3% under
// "Sportsbooks history" while the sportsbooks' own de-vigged number was 11.2%.
//
// `/api/futures/{id}/history` serves that market's de-vigged consensus, the
// series the source page has always drawn and the web verified page draws
// (lane1, PR #10245). So the verified chart keeps the timeline's metadata and
// current column and takes its LINES from `/history`. Nothing here blends,
// re-scales or invents a point.

/// `/api/futures/{id}/history`, reduced to what the chart draws.
nonisolated struct FuturesHistoryResponse: Decodable, Sendable {
    let marketId: Int
    let outcomes: [FuturesHistoryOutcome]
    /// Measured off the points served (#7077), like the timeline's.
    let coverageHours: Double?
    let observationTimes: Int?
    /// #683 — the `range=full` block for the lines drawn.
    @LenientDecode var historyRange: FuturesHistoryRange? = nil
}

nonisolated struct FuturesHistoryOutcome: Decodable, Sendable {
    let outcomeId: Int?
    let name: String
    let history: [FuturesHistoryPoint]
}

nonisolated struct FuturesHistoryPoint: Decodable, Sendable {
    let timestamp: String
    let probability: Double?
    /// #683 — `kalshi_archive` on a recorded interval (at its close); absent on a
    /// live point. The interval fields ride beside it.
    @TolerantNumeric var provenance: String? = nil
    @TolerantNumeric var intervalStart: String? = nil
    @TolerantNumeric var periodMinutes: Int? = nil
    @TolerantNumeric var priceBasis: String? = nil
    /// #10955 — `"settlement"` on the point the server adds to a settled line;
    /// a source name on every price. Tolerant, so an unreadable value never
    /// costs the chart its lines (it then reads as a price, exactly as before).
    @TolerantNumeric var bookmaker: String? = nil
    /// #10955 Step 1 — what the settlement point's timestamp was taken from.
    /// Carried as provenance only: no basis earns a time claim (see
    /// `VerifiedTitleHistory.settlementResults`).
    @TolerantNumeric var settlementBasis: String? = nil

    /// #10955 — the server's settlement point: a result, never an observation.
    var isSettlement: Bool { bookmaker == VerifiedTitleHistory.settlementBookmaker }

    /// The point's archive mark, or nil for a live point.
    var archiveMark: TimelineArchiveMark? {
        guard provenance == EvolutionArchiveProvenance.kalshiArchive else { return nil }
        return TimelineArchiveMark(provenance: provenance, intervalStart: intervalStart,
                                   periodMinutes: periodMinutes, priceBasis: priceBasis)
    }
}

/// #10955 — a settled line's result, carried apart from its prices.
///
/// The value is the grade as served (1 = won, 0 = lost) and is never derived or
/// repaired here. The timestamp is kept as served and is never placed on the
/// axis or read out: whatever its `settlementBasis`, it is a schedule, a notice
/// or no time at all, never the moment a price moved.
nonisolated struct SettlementResult: Equatable, Sendable {
    /// The chart's name for the line — the same key `TimelineEntry.outcomes` uses.
    let name: String
    let probability: Double
    let timestamp: String
    let basis: String?
}

nonisolated enum VerifiedTitleHistory {
    /// The `bookmaker` the server writes on a settlement point (`routes/futures.py`).
    static let settlementBookmaker = "settlement"

    /// Whether the chart draws `/history`'s lines: only in verified context — the
    /// detail OR the timeline response actually answered `verified_title`, the same
    /// context that earns the "Sportsbooks history" caption. The page ASKS for
    /// verified on every futures market, so the request alone decides nothing; an
    /// ineligible board answers in source mode and its chart is unchanged.
    static func drawsSourceHistory(detail: FuturesRepresentation?,
                                   response: FuturesRepresentation?) -> Bool {
        detail == .verifiedTitle || response == .verifiedTitle
    }

    /// The timeline response with its lines replaced by `/history`'s.
    ///
    /// A line joins its row by outcome id and takes the row's name, because the
    /// chart keys lines by the names in `outcomes`; a line with no id falls back
    /// to its own name. A row `/history` has no line for draws none — an empty
    /// line is honest, the raw median is the defect. Coverage comes from
    /// `/history` too, so the axis and the sparse caption describe the points drawn;
    /// so does the `range=full` block (#683), which describes those same lines.
    ///
    /// #10955 — a settlement point is not drawn here at all, whatever its basis:
    /// as a timeline value it joined the solid run (a stroke from the last price
    /// to 0%/100% at a scheduled close nobody observed), the crosshair, the axis,
    /// the Sum line and the sparse counts. `settlementResults` carries it instead.
    /// When one was set aside, coverage is re-measured off the prices that remain,
    /// because the server measured it with the settlement point included.
    static func drawing(_ history: FuturesHistoryResponse,
                        over response: ProbabilityTimelineResponse) -> ProbabilityTimelineResponse {
        let nameById = Self.nameById(response)
        var byStamp: [String: (date: Date, outcomes: [String: Double],
                               archive: [String: TimelineArchiveMark])] = [:]
        var setAside = false
        var priced: [Date] = []
        for line in history.outcomes {
            let name = line.outcomeId.flatMap { nameById[$0] } ?? line.name
            for point in line.history {
                if point.isSettlement { setAside = true; continue }
                if let date = point.timestamp.asDate { priced.append(date) }
                guard let probability = point.probability,
                      let date = point.timestamp.asDate else { continue }
                byStamp[point.timestamp, default: (date, [:], [:])].outcomes[name] = probability
                // #683: an archived point keeps its mark on the line it joins, so
                // the chart labels it here exactly as it does on the timeline.
                byStamp[point.timestamp]?.archive[name] = point.archiveMark
            }
        }
        var drawn = response
        drawn.timeline = byStamp
            .sorted { ($0.value.date, $0.key) < ($1.value.date, $1.key) }
            .map { TimelineEntry(timestamp: $0.key, outcomes: $0.value.outcomes,
                                 archive: $0.value.archive.isEmpty ? nil : $0.value.archive) }
        if setAside {
            // `_measure_history_coverage`'s arithmetic, over the prices only.
            let first = priced.min(), last = priced.max()
            drawn.coverageHours = first.flatMap { first in
                last.map { ($0.timeIntervalSince(first) / 3600 * 100).rounded() / 100 }
            }
            drawn.observationTimes = Set(priced).count
        } else {
            drawn.coverageHours = history.coverageHours
            drawn.observationTimes = history.observationTimes
        }
        drawn.historyRange = history.historyRange
        return drawn
    }

    /// #10955 — every settlement point `drawing` set aside, one per line (the
    /// last served wins), keyed by the same name its line is drawn under. The
    /// admission is a price's: a value and a readable stamp, nothing wider.
    static func settlementResults(_ history: FuturesHistoryResponse,
                                  over response: ProbabilityTimelineResponse) -> [SettlementResult] {
        let nameById = Self.nameById(response)
        var results: [SettlementResult] = []
        for line in history.outcomes {
            let name = line.outcomeId.flatMap { nameById[$0] } ?? line.name
            for point in line.history where point.isSettlement {
                guard let probability = point.probability, point.timestamp.asDate != nil else { continue }
                results.removeAll { $0.name == name }
                results.append(SettlementResult(name: name, probability: probability,
                                                timestamp: point.timestamp, basis: point.settlementBasis))
            }
        }
        return results
    }

    private static func nameById(_ response: ProbabilityTimelineResponse) -> [Int: String] {
        Dictionary(
            response.outcomes.compactMap { meta in meta.id.map { ($0, meta.name) } },
            uniquingKeysWith: { first, _ in first })
    }
}
