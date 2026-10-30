import SwiftUI

/// #10868 — THE HOCKEY JOURNEY SCREEN'S PRODUCTION ADAPTER, PART TWO: THE
/// TWO-TEAM WIN-PROBABILITY HISTORY.
///
/// PILLARS: TRUTH / FORMATTING. SHIP: on `nhl-journey` the history under the
/// matrix draws only what was recorded — the last pregame reading, then the
/// game — and leaves every unrecorded stretch blank, never a settlement or a
/// line run on to now; the away side of a two-outcome blend is said to be its
/// other side, and is withheld where the sport prices a draw.
///
/// It builds `FieldHistoryInput10868` from the decoded `/api/events/{id}/history`
/// body (`EventHistoryResponse`), the event (`EventDetail`), the page phase and
/// the reader's clock. It decides nothing the app does not already decide. Each
/// part is the output of the authority that owns it:
///
///   - which line       `OddsChartView.primarySource(in: servedPoints(from:))`
///                      (OddsChartView.swift:2803, :3146): the backend blend
///                      (`aggregate_line`) when one is served beside venue
///                      series, else the sportsbook consensus (`history`).
///                      Never a client mean.
///   - the two series   home is the line's served `homeProbability`. Away, on
///                      the consensus, is its served `awayProbability` only. On
///                      the blend — served home-only today (events.py builds
///                      `aggregate_line` rows with `timestamp` + `home_probability`)
///                      — away is the row's served `awayProbability`, else the
///                      documented two-outcome complement `1 − home` OF THAT SAME
///                      ROW, passed through `DrawPricedWinner.printablePair`
///                      (DrawPricedWinner.swift:1-30, :76-96), which withholds it
///                      on a sport whose winner market prices a draw. So the away
///                      trace has the home trace's rows, times, breaks and
///                      removals exactly — never an extra point — and a note says
///                      it is the other side of the same blend. A row with no
///                      value for a team is a gap for that team.
///   - where a line     `OddsChartView.observationSegments` (:3273, floor 600 s,
///     breaks           15× the series' own in-game cadence; pre-match intervals
///                      never judged), applied inside each stretch between
///                      unreadable rows. An unreadable row (no value, outside
///                      0…1, a consensus row priced by 0 books, an unreadable or
///                      non-advancing time) BREAKS the run here, where the chart
///                      would skip it and join across — the one place this file
///                      is stricter than the chart, so no line crosses a row the
///                      server says it could not price.
///   - not readings     removed outright, leaving no point and no gap:
///                      • a finished game's settlement row — the server appends
///                        exactly one, LAST, at the resolved 1 / 0 / 0.5
///                        (events.py terminal append). It is the last served row
///                        when its value is the result `EventOutcome.resolve`
///                        names, or a venue `evidence.kind == "final"` point
///                        (under a readable contract) or ESPN's `Final` row
///                        witnesses it at the same instant and value;
///                      • the blend's pinned edge (`blendEdgePinned`,
///                        HistoryModels.swift:48-53): the hero's current-state
///                        pin re-stamped at read time, not a recorded reading;
///                      • blend minutes that hold only the backend's live-edge
///                        carry-forward, `BlendPreview.carriedForwardMinutes`
///                        (BlendPreview.swift:985).
///   - game end         `OddsChartView.gameEndDate` (:1570) clips a finished
///                      game's rows, exactly as the chart does.
///   - pregame / game   split at `OddsChartView.sinceStartCut` (:1664) — the
///                      listed start only when the payload says it is a kick-off
///                      — and refused outright when `startIsTbd` says the clock
///                      is a placeholder. No start ⇒ no history is drawn (the
///                      owner's plot absence), never a split at a guessed time.
///   - guides           `OddsChartView.periodSightings` (:1827), kept only for
///                      labels `PeriodLabel.columnLabel` (PeriodLabel.swift:168)
///                      admits as a game division (so `Final`, `INT`, `HT` are
///                      not period starts); scoring plays at their served
///                      `timestamp`, worded by `ExpandedRecordedMatchMoment9483.play`
///                      (ExpandedRecordedMatchMoment9483.swift:124). Only guides
///                      inside the frame, at or before its last row.
///   - the axis         `OddsChartView.xAxisPlan` / `xAxisTicks` (:4305, :4352)
///                      on the phone count budget (no plot width is known here),
///                      said with the plan's own format in the reader's calendar,
///                      zone and locale; y ticks through `OddsChartView.axisLabel`
///                      (:3471).
///   - every percent    `formatProbability` (FormattingUtilities.swift:12); a
///                      complement pair's two readouts through
///                      `duelProbabilityStrings(..., complementaryAway: true)`.
///   - clock words      `HockeyJourneyPageAdapter10868.clockWords` (part one).
///   - tints            `TeamTextContrast.cardColors`, as part one's matrix.
///   - source words     mirrored from `OddsChartView.displayNameForSource`
///                      (:4010, private to the View): "Bain Luck" for the blend,
///                      "Sportsbook Consensus (market)" for the consensus.
///
/// Phase scopes (the accepted screen's own, kept):
///   before — readable pregame rows from the listed start less one day up to
///            the last pregame row; no guides.
///   live   — the last pregame row, then the game's rows up to now.
///   final  — the last pregame row, then the game's rows up to the game's end,
///            without the settlement row.
/// Where the in-game frame opens is the host's admission and is still owed: it
/// is the `inGameStart` parameter, defaulting to the screen's last pregame row.
///
/// Nothing here fetches, subscribes, schedules or holds state. The host's held
/// inspection is not built here: `inspection` is nil.
enum HockeyJourneyHistoryAdapter10868 {

    /// What the host already holds, passed in unchanged.
    struct Host {
        let now: Date
        /// The reader's own calendar, time zone and locale; every clock word and
        /// tick is said in it.
        let calendar: Calendar
        let locale: Locale

        init(now: Date = Date(), calendar: Calendar = .current, locale: Locale = .current) {
            self.now = now
            self.calendar = calendar
            self.locale = locale
        }

        /// Part one's host, so the history says its clocks in the matrix's words.
        var words: HockeyJourneyPageAdapter10868.Host {
            HockeyJourneyPageAdapter10868.Host(probabilityObservedAt: nil, now: now,
                                               calendar: calendar, locale: locale)
        }
    }

    /// Where the live and final frames open. Still owed by the host.
    enum InGameStart: Equatable {
        /// The screen's choice: the last pregame row, drawn hollow.
        case lastPregameRow
        /// The chart's Since Start cut: `ObservedPlayStart.cut` (the first
        /// observed opening period less its lead-in), else the listed kick-off.
        /// The last pregame reading is then said beside the plot, not drawn.
        case observedPlayStart
    }

    /// The one line both series are read from.
    enum Line: String, Equatable {
        case blend = "aggregate"
        case consensus = "consensus"
    }

    enum Side: Equatable {
        case home
        case away
    }

    enum Words {
        static let title = "Win probability"
        static let beforeCaption = "Before game"
        static let gameCaption = "Game history"
        static let pregame = "Pregame"
        static let recorded = "Recorded"
        static let lastPregame = "Last pregame"
        static let notRecorded = "Not recorded"
        static let noHistory = "No recorded history"
        static let hollowKey = "Hollow · last pregame"
        static let gapsNote = "Gaps remain blank."
        static let blendSource = "Source: Bain Luck"
        static let consensusSource = "Source: Sportsbook Consensus (market)"
        static let unconfirmedStart = "Start time not confirmed"
        static let unconfirmedStartWords = "Pregame and game readings are split at a confirmed start, and this game has none yet."
        static let details = "History & source details"
        static let expand = "Full chart"
        static let expandSpoken = "Expand hockey probability history"
        static let inspect = "Inspect history"
    }

    static let detailsActionID = "history.details"
    static let expandActionID = "history.expand"
    static let inspectActionID = "history.inspect"

    /// The before frame reaches back one day from the listed start.
    static let beforeWindow: TimeInterval = 86_400
    static let plotHeight: CGFloat = 230
    static let yTickValues: [Double] = [0, 0.5, 1]

    // MARK: - The history

    static func history(_ response: EventHistoryResponse, event: EventDetail,
                        phase: HockeyJourneyPagePhase10868, host: Host,
                        inGameStart: InGameStart = .lastPregameRow) -> FieldHistoryInput10868 {
        let line = Self.line(response)
        let tints = TeamTextContrast.cardColors(awayHex: event.awayTeamData?.primaryColor,
                                                homeHex: event.homeTeamData?.primaryColor)
        guard let kickoff = Self.kickoff(response, event: event) else {
            return absence(response, event: event, line: line, phase: phase, tints: tints,
                           plot: FieldHistoryPlotAbsence10868(title: Words.unconfirmedStart,
                                                             words: Words.unconfirmedStartWords))
        }
        let entries = Self.entries(servedRows(response, line: line, sport: event.sport),
                                   removing: removedIndexes(response, event: event, line: line))
        let end: Date = phase == .final
            ? min(OddsChartView.gameEndDate(status: event.status, history: response) ?? host.now, host.now)
            : host.now
        let opening: Date? = inGameStart == .observedPlayStart
            ? (ObservedPlayStart.cut(scheduled: kickoff, history: response, sportKey: event.sport) ?? kickoff)
            : nil

        let homeID = seriesID(line: line, eventId: response.eventId, side: .home)
        let awayID = seriesID(line: line, eventId: response.eventId, side: .away)
        let home = drawn(entries, side: .home, phase: phase, kickoff: kickoff, end: end, now: host.now,
                         opening: opening, line: line)
        let away = drawn(entries, side: .away, phase: phase, kickoff: kickoff, end: end, now: host.now,
                         opening: opening, line: line)

        let dates = (home.runs + away.runs).flatMap { $0.map(\.date) }
        guard let first = dates.min(), let last = dates.max() else {
            return absence(response, event: event, line: line, phase: phase, tints: tints,
                           plot: FieldHistoryPlotAbsence10868(title: Words.noHistory, words: nil))
        }
        let domain = frame(first, last)
        let complement = Self.drawsComplement(away)
            ? complementNote(away: event.awayTeam, home: event.homeTeam) : nil

        let homeSeries = series(homeID, side: .home, name: event.homeTeam, shape: .circle, tint: tints.home,
                                drawn: home, phase: phase, kickoff: kickoff, host: host)
        let awaySeries = series(awayID, side: .away, name: event.awayTeam, shape: .square, tint: tints.away,
                                drawn: away, phase: phase, kickoff: kickoff, host: host)
        return FieldHistoryInput10868(
            title: Words.title,
            caption: phase == .before ? Words.beforeCaption : Words.gameCaption,
            series: [homeSeries, awaySeries],
            selection: .none,
            domain: FieldHistoryDomain10868(lower: domain.lowerBound.timeIntervalSince1970,
                                            upper: domain.upperBound.timeIntervalSince1970),
            ceiling: 1,
            yTicks: yTicks(),
            xTicks: xTicks(domain, host: host),
            guides: phase == .before ? [] : guides(response, event: event, from: domain.lowerBound, through: last),
            breaks: [],
            readout: phase == .live
                ? .beforeAndRecorded(beforeLabel: Words.pregame, recordedLabel: Words.recorded)
                : .singleBefore(label: Words.pregame),
            markKey: FieldHistoryMarkKey10868(hollow: Words.hollowKey, filled: nil),
            comparisonExplanation: nil,
            notes: [sourceWords(line)] + (complement.map { [$0] } ?? []) + [Words.gapsNote],
            summary: summary([(event.homeTeam, !home.runs.isEmpty), (event.awayTeam, !away.runs.isEmpty)])
                + (complement.map { " \($0)" } ?? ""),
            plotHeight: plotHeight,
            unboundReadingWords: Words.notRecorded,
            plotUnavailableWords: nil,
            windows: nil, scale: nil, moreOriginals: nil,
            details: action(detailsActionID, Words.details),
            expand: action(expandActionID, Words.expand, spoken: Words.expandSpoken),
            inspect: phase == .live ? action(inspectActionID, Words.inspect) : nil,
            previous: nil, next: nil, inspection: nil)
    }

    // MARK: - The line and its rows

    /// The chart's own primary line on this payload.
    static func line(_ response: EventHistoryResponse) -> Line {
        OddsChartView.primarySource(in: OddsChartView.servedPoints(from: response)) == Line.blend.rawValue
            ? .blend : .consensus
    }

    /// One served row of the line, in served order, values as served.
    struct ServedRow: Equatable {
        /// Position in the served array.
        let index: Int
        /// Verbatim.
        let timestamp: String
        let date: Date?
        let home: Double?
        /// Served, or on the blend the printable complement of this row's home.
        let away: Double?
        /// True when `away` is that complement, not a served away value.
        let awayIsComplement: Bool
        /// False for a consensus row priced by 0 books: not a sportsbook reading.
        let priced: Bool
    }

    static func servedRows(_ response: EventHistoryResponse, line: Line, sport: String?) -> [ServedRow] {
        switch line {
        case .blend:
            return (response.aggregateLine ?? []).enumerated().map { index, point -> ServedRow in
                let away = blendAway(served: point.awayProbability, home: point.homeProbability, sport: sport)
                return ServedRow(index: index, timestamp: point.timestamp, date: point.timestamp.asDate,
                                 home: point.homeProbability, away: away,
                                 awayIsComplement: point.awayProbability == nil && away != nil, priced: true)
            }
        case .consensus:
            return response.history.enumerated().map { index, point in
                ServedRow(index: index, timestamp: point.timestamp, date: point.timestamp.asDate,
                          home: point.homeProbability, away: point.awayProbability, awayIsComplement: false,
                          priced: point.bookmakerCount != 0)
            }
        }
    }

    /// The blend row's away side: its served away value, else the documented
    /// two-outcome complement of the same row's home, through the production pair
    /// rule — nil on a draw-priced sport, where `1 − home` is "home does not win".
    static func blendAway(served: Double?, home: Double, sport: String?) -> Double? {
        DrawPricedWinner.printablePair(away: served ?? (1 - home), home: home, sport: sport)?.away
    }

    /// A team's own served value on a row, or nil when the row is a gap for it.
    static func value(_ row: ServedRow, _ side: Side) -> Double? {
        guard row.priced, let served = side == .home ? row.home : row.away,
              served.isFinite, served >= 0, served <= 1 else { return nil }
        return served
    }

    /// The rows that are not readings at all: the settlement, the pin and the
    /// carried minutes. Removed outright — no point, no gap.
    static func removedIndexes(_ response: EventHistoryResponse, event: EventDetail, line: Line) -> Set<Int> {
        let rows = servedRows(response, line: line, sport: event.sport)
        var removed: Set<Int> = []
        if let terminal = settlementIndex(rows, response: response, event: event) { removed.insert(terminal) }
        guard line == .blend else { return removed }
        if response.blendEdgePinned == true, let pin = rows.last { removed.insert(pin.index) }
        let carried = BlendPreview.carriedForwardMinutes(response)
        if !carried.isEmpty {
            for row in rows {
                guard let date = row.date else { continue }
                let minute = Date(timeIntervalSince1970: (date.timeIntervalSince1970 / 60).rounded(.down) * 60)
                if carried.contains(minute) { removed.insert(row.index) }
            }
        }
        return removed
    }

    /// The finished game's settlement row: the LAST served row, when its value is
    /// the result `EventOutcome.resolve` names or a served witness states it.
    static func settlementIndex(_ rows: [ServedRow], response: EventHistoryResponse, event: EventDetail) -> Int? {
        guard EventState.isFinished(event.status) || EventState.isFinished(response.status),
              let last = rows.last, let home = last.home else { return nil }
        let settled: Double? = switch EventOutcome.resolve(status: event.status, homeScore: event.homeScore,
                                                           awayScore: event.awayScore,
                                                           servedResult: event.heroSettledResult) {
        case .home: 1
        case .away: 0
        case .draw: 0.5
        case .undecided: nil
        }
        return home == settled || witnessesSettlement(last, in: response) ? last.index : nil
    }

    /// A served statement that `row` is the result: a venue point of kind
    /// `final` (read only under a contract this client knows, as the chart reads
    /// `evidence`) or ESPN's `Final` row, at the same instant and value.
    static func witnessesSettlement(_ row: ServedRow, in response: EventHistoryResponse) -> Bool {
        guard let date = row.date, let home = row.home else { return false }
        if response.evidenceContract?.readableResolution != nil {
            for points in (response.winProbHistory ?? [:]).values {
                if points.contains(where: {
                    $0.evidence?.kind == "final" && $0.timestamp.asDate == date && $0.homeProbability == home
                }) { return true }
            }
        }
        return (response.espnHistory ?? []).contains {
            $0.period == "Final" && $0.timestamp.asDate == date && $0.homeProbability == home
        }
    }

    /// One row after the removals, in served order. `date` is nil where the time
    /// cannot be read or does not advance past the row before; such a row is a
    /// gap, never a vertex.
    struct Entry: Equatable {
        let row: ServedRow
        let date: Date?
    }

    static func entries(_ rows: [ServedRow], removing removed: Set<Int>) -> [Entry] {
        var previous: Date?
        var out: [Entry] = []
        for row in rows where !removed.contains(row.index) {
            var date = row.date
            if let current = date, let before = previous, current <= before { date = nil }
            if let current = date { previous = current }
            out.append(Entry(row: row, date: date))
        }
        return out
    }

    /// The listed start, only when it is a kick-off and not a placeholder.
    static func kickoff(_ response: EventHistoryResponse, event: EventDetail) -> Date? {
        guard event.startIsTbd != true else { return nil }
        return OddsChartView.sinceStartCut(commenceTime: event.commenceTime?.asDate,
                                           commenceTimeIsKickoff: response.commenceTimeIsKickoff)
    }

    // MARK: - One series

    /// One drawn vertex: the row it came from, its time and the team's value.
    struct Vertex: Equatable {
        let entry: Entry
        let date: Date
        let value: Double
    }

    struct Drawn: Equatable {
        /// Separated runs, in time order. Two runs are never joined.
        let runs: [[Vertex]]
        /// The team's last readable pregame row at or before now, drawn or not.
        let lastPregame: Vertex?
        /// Whether `lastPregame` is one of the drawn vertices.
        let pregameDrawn: Bool
    }

    static func drawn(_ entries: [Entry], side: Side, phase: HockeyJourneyPagePhase10868,
                      kickoff: Date, end: Date, now: Date, opening: Date?, line: Line) -> Drawn {
        let lastPregamePosition = entries.lastIndex { entry in
            guard let date = entry.date else { return false }
            return date < kickoff && date <= now && Self.value(entry.row, side) != nil
        }
        let lastPregame = lastPregamePosition.flatMap { position -> Vertex? in
            let entry = entries[position]
            guard let date = entry.date, let reading = Self.value(entry.row, side) else { return nil }
            return Vertex(entry: entry, date: date, value: reading)
        }

        let start: Int?
        let stop: Int?
        switch phase {
        case .before:
            let floor = kickoff.addingTimeInterval(-beforeWindow)
            start = entries.firstIndex { $0.date.map { $0 >= floor } ?? false }
            stop = lastPregamePosition
        case .live, .final:
            if let opening {
                start = entries.firstIndex { $0.date.map { $0 >= opening } ?? false }
            } else {
                start = lastPregamePosition ?? entries.firstIndex { $0.date.map { $0 >= kickoff } ?? false }
            }
            let limit = min(end, now)
            stop = entries.lastIndex { $0.date.map { $0 <= limit } ?? false }
        }
        guard let start, let stop, start <= stop else {
            return Drawn(runs: [], lastPregame: lastPregame, pregameDrawn: false)
        }

        // Stretches between unreadable rows; inside each, the chart's own breaks.
        var stretches: [[Vertex]] = [[]]
        for entry in entries[start...stop] {
            if let date = entry.date, let reading = Self.value(entry.row, side) {
                stretches[stretches.count - 1].append(Vertex(entry: entry, date: date, value: reading))
            } else if !(stretches.last?.isEmpty ?? true) {
                stretches.append([])
            }
        }
        var runs: [[Vertex]] = []
        for stretch in stretches where !stretch.isEmpty {
            var byPoint: [UUID: Vertex] = [:]
            var points: [ChartDataPoint] = []
            for vertex in stretch {
                let point = ChartDataPoint(date: vertex.date, probability: vertex.value, source: line.rawValue)
                byPoint[point.id] = vertex
                points.append(point)
            }
            for segment in OddsChartView.observationSegments(points, gameStart: kickoff) {
                let run = segment.compactMap { byPoint[$0.id] }
                if !run.isEmpty { runs.append(run) }
            }
        }
        let pregameDrawn = lastPregame.map { pregame in
            runs.contains { $0.contains { $0.entry.row.index == pregame.entry.row.index } }
        } ?? false
        return Drawn(runs: runs, lastPregame: lastPregame, pregameDrawn: pregameDrawn)
    }

    static func series(_ id: String, side: Side, name: String, shape: FieldHistoryShape10868, tint: Color,
                       drawn: Drawn, phase: HockeyJourneyPagePhase10868, kickoff: Date,
                       host: Host) -> FieldHistorySeries10868 {
        let hollow = drawn.pregameDrawn ? drawn.lastPregame?.entry.row.index : nil
        let runs = drawn.runs.enumerated().map { number, run in
            FieldHistoryRun10868(id: "\(id)#run-\(number + 1)", points: run.map { vertex in
                FieldHistoryPoint10868(id: pointID(id, vertex.entry.row.timestamp),
                                       x: vertex.date.timeIntervalSince1970, probability: vertex.value,
                                       style: vertex.entry.row.index == hollow ? .hollow : .filled)
            })
        }

        let before: FieldHistoryReading10868
        if let pregame = drawn.lastPregame {
            let figure = readingFigure(pregame, side: side)
            let provenance = "\(Words.lastPregame) · \(clockWords(pregame.date, host: host))"
            before = drawn.pregameDrawn
                ? .observation(pointID: pointID(id, pregame.entry.row.timestamp), figure: figure, provenance: provenance)
                : .independent(figure: figure, provenance: provenance)
        } else {
            before = .absent(words: Words.notRecorded)
        }

        let recorded: FieldHistoryReading10868
        if phase == .live, let latest = drawn.runs.last?.last, latest.date >= kickoff {
            recorded = .observation(pointID: pointID(id, latest.entry.row.timestamp),
                                    figure: readingFigure(latest, side: side),
                                    provenance: "\(Words.recorded) \(clockWords(latest.date, host: host))")
        } else {
            recorded = .absent(words: Words.notRecorded)
        }

        return FieldHistorySeries10868(id: id, name: name, shape: shape, tint: tint, runs: runs, links: [],
                                       labelPointID: nil, before: before, recorded: recorded,
                                       absentWords: Words.noHistory, choose: nil)
    }

    /// A reading's figure through `formatProbability`. On a blend row whose away
    /// side is the complement, both teams' figures are ONE two-sided decision —
    /// `duelProbabilityStrings(away:home:complementaryAway: true)`, production's
    /// rule for a locally reconstructed pair — so one instant never reads 51% and 50%.
    static func readingFigure(_ vertex: Vertex, side: Side) -> String {
        let row = vertex.entry.row
        guard row.awayIsComplement, let home = row.home, let away = row.away else {
            return formatProbability(vertex.value)
        }
        let pair = duelProbabilityStrings(away: away, home: home, complementaryAway: true)
        return side == .home ? pair.home : pair.away
    }

    static func seriesID(line: Line, eventId: Int, side: Side) -> String {
        "\(line == .blend ? "blend" : "consensus"):\(eventId):\(side == .home ? "home" : "away")"
    }

    /// The served timestamp is unique inside a series: drawn times strictly advance.
    static func pointID(_ seriesID: String, _ timestamp: String) -> String {
        "\(seriesID)#\(timestamp)"
    }

    // MARK: - Guides, frame and axes

    /// Period starts and scoring plays inside the frame, at or before its last row.
    static func guides(_ response: EventHistoryResponse, event: EventDetail,
                       from lower: Date, through frame: Date) -> [FieldHistoryGuide10868] {
        var guides: [(date: Date, guide: FieldHistoryGuide10868)] = []
        for sighting in OddsChartView.periodSightings(response, sportKey: event.sport).sorted
        where !PeriodLabel.columnLabel(sighting.label).isEmpty && sighting.date >= lower && sighting.date <= frame {
            guides.append((sighting.date, FieldHistoryGuide10868(
                id: "period:\(sighting.label)", x: sighting.date.timeIntervalSince1970, label: sighting.label)))
        }
        for (index, play) in (response.scoringPlays ?? []).enumerated() {
            guard let stamp = play.timestamp, let date = stamp.asDate, date >= lower, date <= frame,
                  let words = ExpandedRecordedMatchMoment9483.play(play) else { continue }
            let label = [words.type, words.text].compactMap { $0 }.joined(separator: " · ")
            guides.append((date, FieldHistoryGuide10868(
                id: "play:\(stamp)#\(index)", x: date.timeIntervalSince1970, label: label)))
        }
        return guides.enumerated()
            .sorted { ($0.element.date, $0.offset) < ($1.element.date, $1.offset) }
            .map { $0.element.guide }
    }

    /// First to last drawn row. A single instant opens by the chart's own
    /// minimum padding (`OddsChartView.naturalDomain`), so the domain is valid.
    static func frame(_ first: Date, _ last: Date) -> ClosedRange<Date> {
        guard last > first else { return OddsChartView.naturalDomain(of: [first]) ?? (first...first.addingTimeInterval(60)) }
        return first...last
    }

    static func yTicks() -> [FieldHistoryTick10868] {
        yTickValues.map { FieldHistoryTick10868(value: $0, lines: [OddsChartView.axisLabel(for: $0)]) }
    }

    static func xTicks(_ domain: ClosedRange<Date>, host: Host) -> [FieldHistoryTick10868] {
        let plan = OddsChartView.xAxisPlan(for: domain, calendar: host.calendar)
        return OddsChartView.xAxisTicks(for: domain, plan: plan, calendar: host.calendar).map {
            FieldHistoryTick10868(value: $0.timeIntervalSince1970, lines: [tickWords($0, plan: plan, host: host)])
        }
    }

    /// The plan's own label format, said in the reader's calendar, zone and locale.
    static func tickWords(_ date: Date, plan: OddsChartView.XAxisPlan, host: Host) -> String {
        var style = plan.format
        style.locale = host.locale
        style.calendar = host.calendar
        style.timeZone = host.calendar.timeZone
        return date.formatted(style)
    }

    // MARK: - Words

    static func clockWords(_ date: Date, host: Host) -> String {
        HockeyJourneyPageAdapter10868.clockWords(date, host: host.words)
    }

    /// Whether any away reading on show is the complement of the home reading.
    static func drawsComplement(_ away: Drawn) -> Bool {
        let shown = away.runs.flatMap { $0 } + (away.lastPregame.map { [$0] } ?? [])
        return shown.contains { $0.entry.row.awayIsComplement }
    }

    /// "Boston Bruins is the other side of the same blend: 100% − Minnesota Wild."
    static func complementNote(away: String, home: String) -> String {
        "\(away) is the other side of the same blend: 100% − \(home)."
    }

    static func sourceWords(_ line: Line) -> String {
        line == .blend ? Words.blendSource : Words.consensusSource
    }

    /// Each team's name and whether any of its history is drawn.
    static func summary(_ teams: [(String, Bool)]) -> String {
        let shown = teams.filter { $0.1 }.map { $0.0 }
        let missing = teams.filter { !$0.1 }.map { $0.0 }
        guard !shown.isEmpty else { return Words.noHistory }
        let lead = "\(shown.joined(separator: " and ")) win probability, recorded observations only."
        return missing.isEmpty ? lead : "\(lead) No recorded history for \(missing.joined(separator: " or "))."
    }

    static func action(_ id: String, _ label: String, spoken: String? = nil) -> FieldHistoryAction10868 {
        FieldHistoryAction10868(id: id, label: label, spokenLabel: spoken, isAvailable: true)
    }

    /// Nothing to draw, in the owner's words: no point, axis or guide is offered
    /// under it, and the domain is a placeholder the leaf never draws under an absence.
    static func absence(_ response: EventHistoryResponse, event: EventDetail, line: Line,
                        phase: HockeyJourneyPagePhase10868, tints: (away: Color, home: Color),
                        plot: FieldHistoryPlotAbsence10868) -> FieldHistoryInput10868 {
        func empty(_ side: Side, _ name: String, _ shape: FieldHistoryShape10868, _ tint: Color) -> FieldHistorySeries10868 {
            FieldHistorySeries10868(id: seriesID(line: line, eventId: response.eventId, side: side), name: name,
                                    shape: shape, tint: tint, runs: [], links: [], labelPointID: nil,
                                    before: .absent(words: Words.notRecorded), recorded: .absent(words: Words.notRecorded),
                                    absentWords: Words.noHistory, choose: nil)
        }
        return FieldHistoryInput10868(
            title: Words.title,
            caption: phase == .before ? Words.beforeCaption : Words.gameCaption,
            series: [empty(.home, event.homeTeam, .circle, tints.home), empty(.away, event.awayTeam, .square, tints.away)],
            selection: .none,
            domain: FieldHistoryDomain10868(lower: 0, upper: 1),
            ceiling: 1, yTicks: [], xTicks: [], guides: [], breaks: [],
            readout: .singleBefore(label: Words.pregame),
            markKey: FieldHistoryMarkKey10868(hollow: nil, filled: nil),
            comparisonExplanation: nil,
            notes: [sourceWords(line)],
            summary: Words.noHistory,
            plotHeight: plotHeight,
            unboundReadingWords: Words.notRecorded,
            plotUnavailableWords: nil,
            windows: nil, scale: nil, moreOriginals: nil,
            details: action(detailsActionID, Words.details),
            expand: nil, inspect: nil, previous: nil, next: nil, inspection: nil,
            plotAbsence: plot)
    }
}
