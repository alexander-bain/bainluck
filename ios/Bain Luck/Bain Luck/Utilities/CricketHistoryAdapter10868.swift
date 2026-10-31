import SwiftUI

/// #10868 — THE CRICKET TEST-MATCH SCREEN'S PRODUCTION ADAPTER, PART TWO: THE
/// THREE-ORIGINAL WIN-PROBABILITY HISTORY.
///
/// PILLARS: TRUTH / FORMATTING. SHIP: on `cricket-live` the history beside the
/// headline draws only what was recorded for each original — the last pregame
/// reading, then play — leaves every unrecorded stretch blank, never runs a
/// line on to now or to a settled 0% / 100%, and never draws the away side as
/// the remainder after the home side.
///
/// It builds `CricketHistoryInput10868` from the decoded `/api/events/{id}/history`
/// body (`EventHistoryResponse`), the event (`EventDetail`), the page phase and
/// the reader's clock. Every line rule is the hockey candidate's reviewed
/// history rule (`HockeyJourneyHistoryAdapter10868`, source-accepted by Design
/// after H2), reused rather than restated, so the candidate has one rule:
///
///   - which line     `Rules.line` — `OddsChartView.primarySource`: the backend
///                    blend (`aggregate_line`) when served, else the sportsbook
///                    consensus (`history`). Never a client mean.
///   - the rows       `Rules.servedRows`, values as served, then this screen's
///                    one change: no away value is drawn. No channel carries the
///                    producer's positive evidence that a row's away figure is the
///                    away side's own price (part one, "the away side"), so the
///                    away line is that series' own words, never a vertex.
///   - not readings   `Rules.removedIndexes` — the finished game's settlement row,
///                    the blend's pinned edge and carried-forward minutes are
///                    removed outright: no point, no gap.
///   - where a line   `Rules.entries` + `Rules.drawn` — an unreadable or
///     breaks         non-advancing row breaks the run; inside, the production
///                    chart's own gap rule (`OddsChartView.observationSegments`).
///                    Two segments are never joined.
///   - pregame / play `Rules.kickoff` (`OddsChartView.sinceStartCut`, refused when
///                    `startIsTbd`); no confirmed start ⇒ no split and no pregame
///                    mark, the reason said in the context line.
///   - game end       `OddsChartView.gameEndDate` clips a finished game's rows.
///   - axes           `Rules.frame` / `Rules.xTicks` / `Rules.yTickValues` through
///                    `OddsChartView.axisLabel`, in the reader's calendar.
///   - shapes, tints  part one's, by original, so each line matches its headline
///                    key.
///
/// The draw / tie series is always drawn empty with its own words: the server
/// serves `win_prob_history.<venue>[].draw_probability` (events.py), but no app
/// model decodes it (`HistoryPoint` has no draw field). Named dependency.
///
/// No match-progress guides are built (`historyMarkers` stays nil): no cricket
/// score report reaches the app. Inspection, windows and steps are the host's and
/// are nil here; only Full chart acts. Nothing here fetches, subscribes,
/// schedules or holds state.
enum CricketHistoryAdapter10868 {
    typealias Rules = HockeyJourneyHistoryAdapter10868
    typealias Page = CricketEventPageAdapter10868

    enum Words {
        static let title = "Win probability"
        static let pregameKey = "Pregame"
        static let noHistory = "No recorded history"
        /// No history response at all: says nothing about whether readings exist or why.
        static let historyUnavailable = "History unavailable"
        static let expand = "Full chart"
        static let independent = "Each line is that outcome's own chance, recorded at its own times. The lines are not adjusted to add up to 100%."
        static let unconfirmedStart = "The start time is not confirmed, so pregame and play readings are not split."
        static let gapsNote = "Gaps remain blank."
    }

    /// The approved standard plot height (`CricketHistoryGeometry10868.referencePlotHeight`).
    static let plotHeight: CGFloat = 302

    // MARK: - The history

    static func history(_ response: EventHistoryResponse, event: EventDetail,
                        phase: CricketHeadlinePhase10868, host: Rules.Host) -> CricketHistoryInput10868 {
        // Another event's history never draws here: only a response served under
        // this event's own id reaches the rows. A foreign one reads exactly like a
        // missing one; the rest of the page composes from its own inputs.
        guard response.eventId == event.id else { return unavailable(event) }
        let line = Rules.line(response)
        let rows = Self.rows(response, line: line, event: event)
        let entries = Rules.entries(rows, removing: Rules.removedIndexes(response, event: event, line: line))
        // Nil when the start is not a confirmed kick-off: the readings still draw, unsplit.
        let kickoff = Rules.kickoff(response, event: event)
        let end: Date = phase == .completed
            ? min(OddsChartView.gameEndDate(status: event.status, history: response) ?? host.now, host.now)
            : host.now
        let drawn: [Page.Original: Rules.Drawn] = [
            .home: Rules.drawn(entries, side: .home, phase: rulesPhase(phase), kickoff: kickoff,
                               gapStart: event.commenceTime?.asDate, end: end, now: host.now, opening: nil, line: line),
            .away: Rules.drawn(entries, side: .away, phase: rulesPhase(phase), kickoff: kickoff,
                               gapStart: event.commenceTime?.asDate, end: end, now: host.now, opening: nil, line: line),
        ]
        let dates: [Date] = drawn.values.flatMap { $0.runs.flatMap { run in run.map(\.date) } }
        guard let first = dates.min(), let last = dates.max() else {
            return placeholder(event, words: Words.noHistory, context: sourceWords(line))
        }
        let domain = Rules.frame(first, last)
        let tints = TeamTextContrast.cardColors(awayHex: event.awayTeamData?.primaryColor,
                                                homeHex: event.homeTeamData?.primaryColor)
        var series: [CricketHistorySeries10868] = []
        for original in Page.Original.allCases {
            series.append(Self.series(original, drawn: drawn[original], event: event, line: line, tints: tints))
        }
        // Each part on its own line, so the one large initializer stays cheap to type-check.
        let plotted = CricketHistoryDomain10868(lower: domain.lowerBound.timeIntervalSince1970,
                                                upper: domain.upperBound.timeIntervalSince1970)
        let xTicks: [CricketHistoryTick10868] = Rules.xTicks(domain, host: host).map {
            CricketHistoryTick10868(value: $0.value, lines: $0.lines)
        }
        let hasPregame = series.contains { $0.segments.contains { $0.points.contains(where: \.isPregame) } }
        let context: String = Self.context(line, kickoff: kickoff, host: host)
        let summary: String = Self.summary(event, drawn: drawn)
        return CricketHistoryInput10868(
            title: Words.title,
            series: series,
            domain: plotted,
            yTicks: yTicks(),
            xTicks: xTicks,
            context: context,
            pregameKey: hasPregame ? Words.pregameKey : nil,
            summary: summary,
            plotHeight: plotHeight,
            window: nil,
            inspection: nil,
            previous: nil,
            next: nil,
            expand: CricketHistoryControl10868(label: Words.expand, isAvailable: true))
    }

    /// The reviewed rule's phase for this screen's phase.
    static func rulesPhase(_ phase: CricketHeadlinePhase10868) -> HockeyJourneyPagePhase10868 {
        switch phase {
        case .before: .before
        case .during: .live
        case .completed: .final
        }
    }

    // MARK: - Rows

    /// The served rows of the line with no away value: no channel proves a row's
    /// away figure is the away side's own price (part one, "the away side"). The
    /// home value is untouched.
    static func rows(_ response: EventHistoryResponse, line: Rules.Line, event: EventDetail) -> [Rules.ServedRow] {
        Rules.servedRows(response, line: line, sport: event.sport).map { row in
            Rules.ServedRow(index: row.index, timestamp: row.timestamp, date: row.date, home: row.home,
                            away: nil, awayIsComplement: false, priced: row.priced)
        }
    }

    // MARK: - One series

    static func series(_ original: Page.Original, drawn: Rules.Drawn?, event: EventDetail, line: Rules.Line,
                       tints: (away: Color, home: Color)) -> CricketHistorySeries10868 {
        let id = seriesID(original, event: event, line: line)
        var segments: [CricketHistorySegment10868] = []
        if let drawn {
            let hollow = drawn.pregameDrawn ? drawn.lastPregame?.entry.row.index : nil
            for (number, run) in drawn.runs.enumerated() {
                let points: [CricketHistoryPoint10868] = run.map { vertex in
                    CricketHistoryPoint10868(id: Rules.pointID(id, vertex.entry.row.timestamp),
                                             x: vertex.date.timeIntervalSince1970, probability: vertex.value,
                                             isPregame: vertex.entry.row.index == hollow)
                }
                segments.append(CricketHistorySegment10868(id: "\(id)#run-\(number + 1)", points: points))
            }
        }
        return CricketHistorySeries10868(
            id: id, name: Page.subject(event, original), shape: shape(original),
            tint: Page.tint(original, tints: tints), segments: segments, absentWords: absentWords(original))
    }

    /// The words beside a series with nothing to place.
    static func absentWords(_ original: Page.Original) -> String {
        switch original {
        case .home: Words.noHistory
        case .away: Page.Words.winChanceUnavailable
        case .draw: Page.Words.drawChanceUnavailable
        }
    }

    /// Part one's key for the same original.
    static func shape(_ original: Page.Original) -> CricketHistoryShape10868 {
        switch Page.shape(original) {
        case .circle: .circle
        case .diamond: .diamond
        case .square: .square
        }
    }

    static func seriesID(_ original: Page.Original, event: EventDetail, line: Rules.Line) -> String {
        "\(line.rawValue):\(event.id):\(original.rawValue)"
    }

    // MARK: - Axes and words

    static func yTicks() -> [CricketHistoryTick10868] {
        Rules.yTickValues.map { CricketHistoryTick10868(value: $0, lines: [OddsChartView.axisLabel(for: $0)]) }
    }

    /// Source, the independence of the lines, the split and the reader's zone.
    static func context(_ line: Rules.Line, kickoff: Date?, host: Rules.Host) -> String {
        var parts = [sourceWords(line), Words.independent]
        if kickoff == nil { parts.append(Words.unconfirmedStart) }
        parts.append(Words.gapsNote)
        if let zone = host.calendar.timeZone.localizedName(for: .shortGeneric, locale: host.locale) {
            parts.append("Times in \(zone).")
        }
        return parts.joined(separator: " ")
    }

    /// "Source: Bain Luck." / "Source: Sportsbook Consensus (market)." — the
    /// production chart's own names for its two lines.
    static func sourceWords(_ line: Rules.Line) -> String {
        "\(Rules.sourceWords(line))."
    }

    /// Who is drawn and who is not, in plain words.
    static func summary(_ event: EventDetail, drawn: [Page.Original: Rules.Drawn]) -> String {
        var shown: [String] = []
        var missing: [String] = []
        for original in Page.Original.allCases {
            let runs = drawn[original]?.runs ?? []
            let name = Page.subject(event, original)
            if runs.isEmpty { missing.append(name) } else { shown.append(name) }
        }
        guard !shown.isEmpty else { return Words.noHistory }
        let lead = "Recorded win probability for \(shown.joined(separator: " and "))."
        return missing.isEmpty ? lead : "\(lead) Chance unavailable for \(missing.joined(separator: " and "))."
    }

    // MARK: - Absence

    /// No history response at all — not arrived yet, or failed; the host does
    /// not say which, so neither is claimed. Each series says "History
    /// unavailable", no source is named, nothing is placed and no control is
    /// offered. The rest of the page composes from its own inputs. The real
    /// load/error/retry contract stays Native's.
    static func unavailable(_ event: EventDetail) -> CricketHistoryInput10868 {
        placeholder(event, words: Words.historyUnavailable, context: nil)
    }

    /// Nothing to place, in the owner's words, with a placeholder domain the
    /// leaf never draws a point under.
    static func placeholder(_ event: EventDetail, words: String, context: String?) -> CricketHistoryInput10868 {
        let tints = TeamTextContrast.cardColors(awayHex: event.awayTeamData?.primaryColor,
                                                homeHex: event.homeTeamData?.primaryColor)
        var series: [CricketHistorySeries10868] = []
        for original in Page.Original.allCases {
            let absent = original == .home ? words : (words == Words.noHistory ? absentWords(original) : words)
            series.append(CricketHistorySeries10868(
                id: "history:\(event.id):\(original.rawValue)", name: Page.subject(event, original),
                shape: shape(original), tint: Page.tint(original, tints: tints), segments: [], absentWords: absent))
        }
        return CricketHistoryInput10868(
            title: Words.title,
            series: series,
            domain: CricketHistoryDomain10868(lower: 0, upper: 1),
            yTicks: [], xTicks: [],
            context: context,
            pregameKey: nil,
            summary: words,
            plotHeight: plotHeight,
            window: nil, inspection: nil, previous: nil, next: nil, expand: nil)
    }
}
