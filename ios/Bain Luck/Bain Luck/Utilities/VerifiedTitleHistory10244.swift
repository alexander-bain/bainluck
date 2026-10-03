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
}

nonisolated struct FuturesHistoryOutcome: Decodable, Sendable {
    let outcomeId: Int?
    let name: String
    let history: [FuturesHistoryPoint]
}

nonisolated struct FuturesHistoryPoint: Decodable, Sendable {
    let timestamp: String
    let probability: Double?
}

nonisolated enum VerifiedTitleHistory {
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
    /// `/history` too, so the axis and the sparse caption describe the points drawn.
    static func drawing(_ history: FuturesHistoryResponse,
                        over response: ProbabilityTimelineResponse) -> ProbabilityTimelineResponse {
        let nameById = Dictionary(
            response.outcomes.compactMap { meta in meta.id.map { ($0, meta.name) } },
            uniquingKeysWith: { first, _ in first })
        var byStamp: [String: (date: Date, outcomes: [String: Double])] = [:]
        for line in history.outcomes {
            let name = line.outcomeId.flatMap { nameById[$0] } ?? line.name
            for point in line.history {
                guard let probability = point.probability,
                      let date = point.timestamp.asDate else { continue }
                byStamp[point.timestamp, default: (date, [:])].outcomes[name] = probability
            }
        }
        var drawn = response
        drawn.timeline = byStamp
            .sorted { ($0.value.date, $0.key) < ($1.value.date, $1.key) }
            .map { TimelineEntry(timestamp: $0.key, outcomes: $0.value.outcomes) }
        drawn.coverageHours = history.coverageHours
        drawn.observationTimes = history.observationTimes
        return drawn
    }
}
