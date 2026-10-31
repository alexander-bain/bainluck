import SwiftUI

/// #10868 — THE GOLF TOURNAMENT SCREEN'S PRODUCTION ADAPTER, PART SEVEN:
/// INSPECTING THE "CHANCE TO WIN" HISTORY.
///
/// PILLARS: FORMATTING / TRUTH. SHIP: golf fans inspect exact dated chances and
/// gaps on the existing native chart, step between them accessibly, and keep
/// golfer choice, scale and reader return.
///
/// It fills the shared chart's existing inspection slots
/// (`FieldHistoryInput10868.inspect` / `previous` / `next` / `inspection`) from
/// the drawn history alone. It adds no baseline, currentness, recency,
/// settlement or formatting rule:
///   - observations   the drawn golfers' runs, through the history part's own
///                    calls (`drawnGolfers`, `frameCutoff`, `runs`,
///                    `Field.entries`) — the same observations the chart draws,
///                    so every point id here is a drawn point's id
///                    (`pointID(seriesID, raw timestamp)`), built and only ever
///                    compared by equality, never parsed.
///   - moments        every distinct already-parsed instant (`Observation.date`)
///                    among those observations, in time order. Two golfers share
///                    a moment only at the same exact `Date`; equivalent "Z" and
///                    "+00:00" spellings of one instant are one moment, and each
///                    golfer keeps its own raw-timestamp point id and provenance.
///                    No rounding and no tolerance.
///   - moment ids     the existing source key, the chooser's market-and-phase
///                    scope and the instant's exact stored value, so another
///                    source's, market's or phase's moment at the same time never
///                    resolves.
///   - a tap          exactly on a moment: that moment. Inside a drawn line
///                    segment (two consecutive observations of one run of one
///                    golfer): the nearest moment, the earlier on a tie — a
///                    covering segment's ends are moments, so the snap never
///                    leaves the drawn line. Anywhere else: a gap between the
///                    moments either side. Run breaks stay authoritative; nothing
///                    is interpolated.
///   - readings       at a moment, each golfer's own exact observation
///                    (`figure` / `provenance` of `Field.reading`), or "Not
///                    recorded" — never zero, never a neighbour, never another
///                    golfer's value. A real 0 stays a value. In a gap, no cursor
///                    and no value.
///   - the readout    the shared `.beforeAndInspected` intent only while a valid
///                    inspection resolves, with the base readout's own before
///                    label and before reading; on Done or withdrawal every base
///                    value comes back exactly (Design D-I3).
///   - choices        Design D-I2: the existing wrapping buttons before the start
///                    with one to four moments, the existing discrete slider
///                    otherwise — a presentation choice only.
///   - withdrawal     a held inspection resolves only against the exact evidence
///                    it was chosen on (source key, market and phase scope,
///                    listed start, served market id and every served line as
///                    admitted at the reader's clock) and only while its moment
///                    or gap still exists. The host clears it on the first pass
///                    it no longer resolves on, so matching evidence later never
///                    revives it.
///
/// FINAL (Design D-I4): withheld. The retained final history carries rows no owner
/// has qualified (#11315), and no row classifier or event cutoff is added here.
/// The moment, gap and step machinery is phase-agnostic; only `offers(_:)` gates.
///
/// OWED, NOT PAID: a golf reading-hold owner (without one, refreshed history
/// withdraws an open inspection instead of waiting); the finish, contenders and
/// movement cards following the inspected moment; qualified final history;
/// full-field performance; the production binding named in parts one and three.
///
/// Nothing here fetches, subscribes, schedules, ranks or holds state.
enum GolfFieldHistoryInspectionAdapter10868 {
    typealias History = GolfFieldHistoryAdapter10868
    typealias Field = GolfFieldHistoryAdapter10868.Field
    typealias Host = GolfFieldPageAdapter10868.Host

    enum Words {
        static let inspect = "Inspect history"
        static let done = "Done inspecting"
        static let previous = "Previous recorded moment"
        static let next = "Next recorded moment"
        static let selectedTime = "Selected time"
        static let gapCaption = "No observation here"
        static let note = "Only exact captured observations are shown."
        static let sliderLabel = "Recorded history moment"
        static let buttonsLabel = "Recorded pre-tournament estimates"
        static let notRecorded = History.Words.notRecorded
        static let recorded = History.Words.recorded
    }

    /// Starts a new inspection at the latest moment.
    static let startActionID = "golf.history.inspect"
    /// Ends the open inspection.
    static let doneActionID = "golf.history.inspect.done"
    static let previousActionID = "golf.history.previous"
    static let nextActionID = "golf.history.next"
    static let momentPrefix = "golf.history.moment"
    /// Design D-I2: before the start, this many moments get the wrapping buttons.
    static let buttonMoments = 1...4

    // MARK: - Evidence

    /// One served line exactly as admitted at the reader's clock.
    struct Line: Equatable {
        let outcomeID: Int?
        let entries: [History.Entry]
    }

    /// What a held inspection was chosen on. Any difference withdraws it.
    struct Evidence: Equatable {
        /// The chooser's market-and-phase scope (`golf:<market id>:<phase>`).
        let scope: String
        let sourceKey: String
        let listedStart: Date?
        let servedMarketID: Int?
        /// Every served line, in served order — not only the drawn golfers', so a
        /// golfer choice never changes it.
        let lines: [Line]
    }

    // MARK: - The pass

    /// One golfer's exact observation at a moment.
    struct Mark: Equatable {
        let pointID: String
        let figure: String
        let provenance: String
    }

    /// One exact instant at which at least one drawn golfer was observed.
    struct Moment: Equatable {
        let id: String
        let date: Date
        /// The drawn points' own horizontal position.
        let x: Double
        /// The reader's clock words for the instant.
        let clock: String
        /// By series id; golfers without an observation here are absent.
        var marks: [String: Mark]
    }

    /// One drawn line piece: two consecutive observations of one run.
    struct Segment: Equatable {
        let lower: Double
        let upper: Double
    }

    /// One render path's normalized inspection inputs, built once and reused for
    /// the applied input and every callback.
    struct Pass: Equatable {
        let evidence: Evidence
        let phase: GolfFinishPhase10868
        /// The drawn golfers, in the chart's order.
        let seriesIDs: [String]
        /// In time order, each instant once.
        let moments: [Moment]
        let segments: [Segment]

        var offered: Bool { GolfFieldHistoryInspectionAdapter10868.offers(phase) && !moments.isEmpty }
    }

    /// Design D-I4: final stays withheld.
    static func offers(_ phase: GolfFinishPhase10868) -> Bool {
        phase != .final
    }

    static func pass(_ field: Field, cohort: [Int], host: Host) -> Pass {
        let cutoff = History.frameCutoff(field)
        var seriesIDs: [String] = []
        var drawn: [(series: String, observation: History.Observation)] = []
        var segments: [Segment] = []
        for golfer in History.drawnGolfers(field, cohort: cohort) {
            let id = History.seriesID(field.market, outcomeID: golfer.id)
            seriesIDs.append(id)
            for run in History.runs(field.entries(golfer.id) ?? [], from: cutoff) {
                drawn += run.map { (series: id, observation: $0) }
                segments += zip(run, run.dropFirst()).map {
                    Segment(lower: $0.date.timeIntervalSince1970, upper: $1.date.timeIntervalSince1970)
                }
            }
        }
        var moments: [Moment] = []
        for item in drawn.sorted(by: { $0.observation.date < $1.observation.date }) {
            let date = item.observation.date
            let reading = Field.reading(item.observation)
            let mark = Mark(pointID: History.pointID(item.series, item.observation.timestamp),
                            figure: History.figure(reading),
                            provenance: History.provenance(reading, market: field.market, host: host))
            if let last = moments.last, last.date == date {
                moments[moments.count - 1].marks[item.series] = mark
            } else {
                moments.append(Moment(id: momentID(field, date), date: date, x: date.timeIntervalSince1970,
                                      clock: GolfFieldPageAdapter10868.clockWords(date, host: host),
                                      marks: [item.series: mark]))
            }
        }
        return Pass(evidence: evidence(field), phase: field.phase, seriesIDs: seriesIDs,
                    moments: moments, segments: segments)
    }

    static func evidence(_ field: Field) -> Evidence {
        Evidence(
            scope: GolfFieldChooserAdapter10868.scope(field),
            sourceKey: GolfFieldPageAdapter10868.sourceKey(field.market),
            listedStart: field.listedStart,
            servedMarketID: field.history?.marketId,
            lines: (field.history?.outcomes ?? []).map {
                Line(outcomeID: $0.outcomeId, entries: History.entries($0.history, now: field.now))
            })
    }

    /// Source key, market-and-phase scope, then the instant's exact stored value.
    static func momentID(_ field: Field, _ date: Date) -> String {
        "\(momentPrefix)|\(GolfFieldPageAdapter10868.sourceKey(field.market))|"
            + "\(GolfFieldChooserAdapter10868.scope(field))|\(date.timeIntervalSinceReferenceDate.bitPattern)"
    }

    // MARK: - The held inspection

    /// Where an inspection points, by exact moment id.
    enum Position: Equatable {
        case moment(String)
        /// A gap between the moments either side (either may be absent).
        case gap(previous: String?, next: String?)
    }

    /// What the host holds: the position and the evidence it was chosen on.
    struct Held: Equatable {
        let evidence: Evidence
        let at: Position
    }

    /// A held position on one pass, by index into its moments.
    enum At: Equatable {
        case moment(Int)
        case gap(previous: Int?, next: Int?)
    }

    struct Resolved: Equatable {
        let held: Held
        let at: At
    }

    /// One render path's inspection: its pass, and the held inspection resolved
    /// against it once.
    struct Snapshot: Equatable {
        let pass: Pass
        let resolved: Resolved?

        init(pass: Pass, held: Held?) {
            self.pass = pass
            resolved = GolfFieldHistoryInspectionAdapter10868.resolve(held, in: pass)
        }
    }

    /// The held inspection on this pass, or nil — withdrawn — when the pass does
    /// not offer inspection, the evidence differs, the moment is not drawn, or a
    /// gap's bounds are no longer adjacent and uncovered. Never a neighbour.
    static func resolve(_ held: Held?, in pass: Pass) -> Resolved? {
        guard let held, pass.offered, held.evidence == pass.evidence else { return nil }
        switch held.at {
        case .moment(let id):
            guard let index = index(id, in: pass) else { return nil }
            return Resolved(held: held, at: .moment(index))
        case .gap(let previousID, let nextID):
            var lower: Int?
            var upper: Int?
            if let previousID {
                guard let found = index(previousID, in: pass) else { return nil }
                lower = found
            }
            if let nextID {
                guard let found = index(nextID, in: pass) else { return nil }
                upper = found
            }
            switch (lower, upper) {
            case let (low?, high?):
                guard high == low + 1, !covers(pass, from: low, to: high) else { return nil }
            case let (low?, nil):
                guard low == pass.moments.count - 1 else { return nil }
            case let (nil, high?):
                guard high == 0 else { return nil }
            case (nil, nil):
                return nil
            }
            return Resolved(held: held, at: .gap(previous: lower, next: upper))
        }
    }

    /// The one moment with exactly this id.
    static func index(_ id: String, in pass: Pass) -> Int? {
        let found = pass.moments.indices.filter { pass.moments[$0].id == id }
        return found.count == 1 ? found[0] : nil
    }

    /// Whether a drawn segment spans the whole interval between two moments.
    static func covers(_ pass: Pass, from low: Int, to high: Int) -> Bool {
        let lower = pass.moments[low].x
        let upper = pass.moments[high].x
        return pass.segments.contains { $0.lower <= lower && $0.upper >= upper }
    }

    // MARK: - Deliberate choices

    /// A new inspection at the latest moment.
    static func start(_ pass: Pass) -> Held? {
        guard pass.offered, let last = pass.moments.last else { return nil }
        return Held(evidence: pass.evidence, at: .moment(last.id))
    }

    /// The moment a choice id names on this pass, by exact equality.
    static func choice(_ id: String, in pass: Pass) -> Held? {
        guard pass.offered, index(id, in: pass) != nil else { return nil }
        return Held(evidence: pass.evidence, at: .moment(id))
    }

    /// The position a tap at domain value `x` names on this pass.
    static func position(_ x: Double, in pass: Pass) -> Held? {
        guard pass.offered, x.isFinite else { return nil }
        let moments = pass.moments
        if let exact = moments.firstIndex(where: { $0.x == x }) {
            return Held(evidence: pass.evidence, at: .moment(moments[exact].id))
        }
        if pass.segments.contains(where: { $0.lower < x && x < $0.upper }) {
            var best = 0
            for index in moments.indices where abs(moments[index].x - x) < abs(moments[best].x - x) {
                best = index
            }
            return Held(evidence: pass.evidence, at: .moment(moments[best].id))
        }
        let previous = moments.lastIndex { $0.x < x }
        let next = moments.firstIndex { $0.x > x }
        return Held(evidence: pass.evidence,
                    at: .gap(previous: previous.map { moments[$0].id }, next: next.map { moments[$0].id }))
    }

    static func previousIndex(_ at: At) -> Int? {
        switch at {
        case .moment(let index): return index > 0 ? index - 1 : nil
        case .gap(let previous, _): return previous
        }
    }

    static func nextIndex(_ at: At, count: Int) -> Int? {
        switch at {
        case .moment(let index): return index + 1 < count ? index + 1 : nil
        case .gap(_, let next): return next
        }
    }

    /// What a history action id asks for.
    enum Intent: Equatable {
        /// A deliberate new inspection: the host asks for its hold first.
        case start(Held)
        /// Another position inside the open inspection.
        case select(Held)
        case end
        /// An inspection control that names nothing on this pass (drawn
        /// unavailable, or not drawn at all).
        case unavailable
    }

    /// The intent of an inspection id on this pass; nil for every other id.
    static func intent(_ id: String, resolved: Resolved?, in pass: Pass) -> Intent? {
        if id == startActionID {
            guard let held = start(pass) else { return .unavailable }
            return resolved == nil ? .start(held) : .select(held)
        }
        if id == doneActionID { return .end }
        if id == previousActionID || id == nextActionID {
            guard let resolved else { return .unavailable }
            let target = id == previousActionID
                ? previousIndex(resolved.at)
                : nextIndex(resolved.at, count: pass.moments.count)
            guard let target else { return .unavailable }
            return .select(Held(evidence: pass.evidence, at: .moment(pass.moments[target].id)))
        }
        return nil
    }

    // MARK: - The applied input

    /// The page input with only its history inspected.
    static func applied(_ input: GolfEventPageInput10868, snapshot: Snapshot) -> GolfEventPageInput10868 {
        GolfEventPageInput10868(
            phase: input.phase, copy: input.copy, status: input.status,
            history: applied(input.history, snapshot: snapshot),
            finish: input.finish, finishFrame: input.finishFrame,
            contenders: input.contenders, contendersFrame: input.contendersFrame,
            movement: input.movement, movementFrame: input.movementFrame,
            chooser: input.chooser)
    }

    /// The base history unchanged where inspection is not offered; with only the
    /// start action where nothing resolves; inspected where it does. Every
    /// other field is the base's own.
    static func applied(_ base: FieldHistoryInput10868, snapshot: Snapshot) -> FieldHistoryInput10868 {
        let pass = snapshot.pass
        guard pass.offered, base.plotAbsence == nil else { return base }
        guard let resolved = snapshot.resolved else {
            return copy(base, series: base.series, readout: base.readout,
                        inspect: History.action(startActionID, Words.inspect),
                        previous: base.previous, next: base.next, inspection: base.inspection)
        }
        let moment: Moment? = {
            if case .moment(let index) = resolved.at { return pass.moments[index] }
            return nil
        }()
        let series = base.series.map { line -> FieldHistorySeries10868 in
            guard pass.seriesIDs.contains(line.id) else { return line }
            let reading: FieldHistoryReading10868 = moment?.marks[line.id].map {
                .observation(pointID: $0.pointID, figure: $0.figure, provenance: $0.provenance)
            } ?? .absent(words: Words.notRecorded)
            return copy(line, recorded: reading)
        }
        var selections: [String: FieldHistorySelection10868] = [:]
        for id in pass.seriesIDs {
            let selection: FieldHistorySelection10868 = moment?.marks[id].map {
                .point(id: $0.pointID, spoken: $0.figure)
            } ?? .absent(words: Words.notRecorded)
            selections[id] = selection
        }
        let choices = pass.moments.enumerated().map { index, choice in
            FieldHistoryInspectionChoice10868(id: choice.id, lines: [choice.clock], spoken: caption(choice),
                                              isSelected: resolved.at == .moment(index))
        }
        let inspection = FieldHistoryInspection10868(
            x: moment?.x,
            caption: moment.map { caption($0) } ?? Words.gapCaption,
            selections: selections,
            choices: choices,
            choicePresentation: presentation(pass),
            note: Words.note)
        return copy(base, series: series,
                    readout: .beforeAndInspected(beforeLabel: beforeLabel(base.readout),
                                                 inspectedLabel: Words.selectedTime),
                    inspect: History.action(doneActionID, Words.done),
                    previous: History.action(previousActionID, Words.previous,
                                             available: previousIndex(resolved.at) != nil),
                    next: History.action(nextActionID, Words.next,
                                         available: nextIndex(resolved.at, count: pass.moments.count) != nil),
                    inspection: inspection)
    }

    /// "Recorded Oct 6, 6:08 AM".
    static func caption(_ moment: Moment) -> String {
        "\(Words.recorded) \(moment.clock)"
    }

    /// Design D-I2.
    static func presentation(_ pass: Pass) -> FieldHistoryChoicePresentation10868 {
        pass.phase == .before && buttonMoments.contains(pass.moments.count)
            ? .buttons(groupLabel: Words.buttonsLabel)
            : .slider(label: Words.sliderLabel)
    }

    /// The base readout's own before label.
    static func beforeLabel(_ readout: FieldHistoryReadoutIntent10868) -> String {
        switch readout {
        case .singleBefore(let label): return label
        case .beforeAndRecorded(let label, _): return label
        case .beforeAndInspected(let label, _): return label
        }
    }

    /// The base input with only the inspection fields replaced.
    static func copy(_ base: FieldHistoryInput10868, series: [FieldHistorySeries10868],
                     readout: FieldHistoryReadoutIntent10868, inspect: FieldHistoryAction10868?,
                     previous: FieldHistoryAction10868?, next: FieldHistoryAction10868?,
                     inspection: FieldHistoryInspection10868?) -> FieldHistoryInput10868 {
        FieldHistoryInput10868(
            title: base.title, caption: base.caption, series: series, selection: base.selection,
            domain: base.domain, ceiling: base.ceiling, yTicks: base.yTicks, xTicks: base.xTicks,
            guides: base.guides, breaks: base.breaks, readout: readout, markKey: base.markKey,
            comparisonExplanation: base.comparisonExplanation, notes: base.notes, summary: base.summary,
            plotHeight: base.plotHeight, unboundReadingWords: base.unboundReadingWords,
            plotUnavailableWords: base.plotUnavailableWords, windows: base.windows, scale: base.scale,
            moreOriginals: base.moreOriginals, details: base.details, expand: base.expand,
            inspect: inspect, previous: previous, next: next, inspection: inspection,
            layout: base.layout,
            probabilityLowerBound: base.probabilityLowerBound,
            probabilityRangeExplanation: base.probabilityRangeExplanation,
            selectedReadout: base.selectedReadout, inspectionRingShape: base.inspectionRingShape,
            plotAbsence: base.plotAbsence, showsKey: base.showsKey)
    }

    /// The base series with only its recorded reading replaced.
    static func copy(_ base: FieldHistorySeries10868, recorded: FieldHistoryReading10868) -> FieldHistorySeries10868 {
        FieldHistorySeries10868(
            id: base.id, name: base.name, shape: base.shape, tint: base.tint, runs: base.runs, links: base.links,
            labelPointID: base.labelPointID, before: base.before, recorded: recorded,
            absentWords: base.absentWords, choose: base.choose, keyContext: base.keyContext)
    }
}
