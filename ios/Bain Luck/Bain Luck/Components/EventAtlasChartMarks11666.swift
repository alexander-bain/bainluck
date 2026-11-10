import Charts
import Foundation
import SwiftUI

// MARK: - #11666 Step E2: Native Event-Page Atlas Chart Marks

/// Settled result word for the primary series on a finished game (#11666 Step E2).
/// Mirrors web `AtlasResultWordMark` (`frontend/components/atlas/AtlasChartMarks.tsx`).
nonisolated enum EventAtlasSettledResult11666: String, Equatable, Sendable {
    case won
    case lost

    var word: String {
        switch self {
        case .won:
            return "✓ Won"
        case .lost:
            return "✗ Lost"
        }
    }
}

/// Shared mark-grammar legend model for the native event-page chart (#11666 Step E2).
/// Mirrors web `AtlasChartMarkKey` (`frontend/components/atlas/AtlasChartMarks.tsx`):
/// - Hollow (`○`) = Pregame (shown in `All` view)
/// - Solid (`●`) = Recorded reading
/// - Connector (`—`) = Change
/// - `✓ Won` / `✗ Lost` = Result as a word (never a synthetic 100% point)
/// - Any real reading tappable/scrubbable for its exact time in PT
nonisolated struct EventAtlasChartMarkKeyModel11666: Equatable, Sendable {
    let showsOpening: Bool
    let openingLabel: String
    let recordedLabel: String
    let changeLabel: String
    let showsSettledResultWords: Bool
    let settledWonWord: String
    let settledLostWord: String
    let settledExplanation: String
    let tapHint: String

    init(settledResult: EventAtlasSettledResult11666?, includesOpening: Bool, openingLabel: String = "Pregame") {
        self.showsOpening = includesOpening
        self.openingLabel = openingLabel
        self.recordedLabel = "Recorded reading"
        self.changeLabel = "Change"
        self.showsSettledResultWords = settledResult != nil
        self.settledWonWord = EventAtlasSettledResult11666.won.word
        self.settledLostWord = EventAtlasSettledResult11666.lost.word
        self.settledExplanation = "Result as a word"
        self.tapHint = "Tap any reading for exact time (PT)"
    }
}

/// One real observation mark on the primary chart series (#11666 Step E2).
nonisolated struct EventAtlasObservationRow11666: Equatable, Identifiable, Sendable {
    let index: Int
    let date: Date
    let probability: Double
    let isOpening: Bool
    let isVisibleSolid: Bool
    let isSelected: Bool

    var id: String { "\(index)-\(date.timeIntervalSince1970)" }
}

/// Selected reading readout model when the reader scrubs or taps a chart point (#11666 Step E2).
/// Mirrors web `AtlasSelectedReadingReadout` (`frontend/components/atlas/AtlasChartMarks.tsx`).
nonisolated struct EventAtlasSelectedReadingModel11666: Equatable, Sendable {
    let outcomeName: String
    let badgeText: String
    let probabilityText: String
    let timestampTextPT: String
    let isOpening: Bool
}

/// Placement of the settled result word (`✓ Won` or `✗ Lost`) beside the last recorded reading (#11666 Step E2).
nonisolated struct EventAtlasResultWordPlacement11666: Equatable, Sendable {
    let result: EventAtlasSettledResult11666
    let word: String
    let placesLeftOfDot: Bool
    let dotX: CGFloat
    let dotY: CGFloat
    let labelX: CGFloat
    let labelY: CGFloat
}

/// Pure helpers for #11666 Step E2 chart marks.
nonisolated enum EventAtlasChartMarks11666 {
    /// Stride used to thin visible solid marks when a series has more than 36 points,
    /// matching web `AtlasSeriesReadingMarks` (`points.length <= 36 ? 1 : Math.max(1, Math.ceil(points.length / 28))`).
    static func solidMarkStride(pointCount: Int) -> Int {
        guard pointCount > 36 else { return 1 }
        return max(1, Int(ceil(Double(pointCount) / 28.0)))
    }

    private static let exactTimestampFormatterPT: DateFormatter = {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "America/Los_Angeles") ?? .current
        formatter.dateFormat = "MMM d, h:mm:ss a"
        return formatter
    }()

    private static let exactTimestampLock = NSLock()

    /// Formats a date as an exact PT timestamp with seconds (e.g. `"Nov 6, 4:15:30 PM PT"`),
    /// matching web `formatAtlasTimestampPT(ts, { includeSeconds: true })`.
    static func formatExactTimestampPT(_ date: Date) -> String {
        exactTimestampLock.lock()
        defer { exactTimestampLock.unlock() }
        return "\(exactTimestampFormatterPT.string(from: date)) PT"
    }

    /// Maximum scrub-to-observation snap distance when a series spans at least two points.
    /// Prevents a touch across an empty gap from selecting a distant change-point.
    static func maxSelectionSnapSeconds(first: Date, last: Date) -> TimeInterval {
        let span = max(0, last.timeIntervalSince(first))
        return max(3600, span * 0.5)
    }

    /// Extracts real primary-series observations (`!isLiveEdge`, finite probability),
    /// never inventing a synthetic 0% or 100% settlement point.
    static func observationRows(
        dataPoints: [ChartDataPoint],
        checkpoints: PublicationCheckpointMount4974? = nil,
        includesOpening: Bool,
        selectedDate: Date? = nil,
        gameStart: Date? = nil
    ) -> [EventAtlasObservationRow11666] {
        let primarySource = OddsChartView.primarySource(in: dataPoints)
        let baseSeries: [ChartDataPoint] = (checkpoints?.survivors ?? dataPoints.filter { $0.source == primarySource })
            .filter { !$0.isLiveEdge && $0.probability.isFinite && $0.probability >= 0 && $0.probability <= 1 }
            .sorted { $0.date < $1.date }

        var rawObservations: [(date: Date, probability: Double)] = []
        var prevProb: Double?
        for (idx, pt) in baseSeries.enumerated() {
            let isFirstOrLast = idx == 0 || idx == baseSeries.count - 1
            let isChange = prevProb == nil || abs(pt.probability - (prevProb ?? pt.probability)) > 1e-9
            prevProb = pt.probability
            if isFirstOrLast || isChange {
                rawObservations.append((date: pt.date, probability: pt.probability))
            }
        }

        if let drawnCheckpoints = checkpoints?.drawn, !drawnCheckpoints.isEmpty {
            for cp in drawnCheckpoints where cp.vertex.p.isFinite && cp.vertex.p >= 0 && cp.vertex.p <= 1 {
                rawObservations.append((date: cp.date, probability: cp.vertex.p))
            }
            rawObservations.sort { $0.date < $1.date }
        }

        guard !rawObservations.isEmpty else { return [] }

        let selectedIndex = resolveSelectedIndex(in: rawObservations, selectedDate: selectedDate)
        let count = rawObservations.count
        let stride = solidMarkStride(pointCount: count)

        return rawObservations.enumerated().map { index, obs in
            let isOpening = includesOpening && index == 0 && (gameStart == nil || obs.date <= gameStart!)
            let isLast = index == count - 1
            let isSelected = selectedIndex == index
            let isVisibleSolid = !isOpening && (isLast || isSelected || index % stride == 0)
            return EventAtlasObservationRow11666(
                index: index,
                date: obs.date,
                probability: obs.probability,
                isOpening: isOpening,
                isVisibleSolid: isVisibleSolid,
                isSelected: isSelected
            )
        }
    }

    /// Resolves the nearest observation index within the snap bound for `selectedDate`.
    static func resolveSelectedIndex(
        in observations: [(date: Date, probability: Double)],
        selectedDate: Date?
    ) -> Int? {
        guard let selectedDate, let first = observations.first, let last = observations.last else {
            return nil
        }
        guard let nearest = observations.enumerated().min(by: {
            abs($0.element.date.timeIntervalSince(selectedDate)) < abs($1.element.date.timeIntervalSince(selectedDate))
        }) else {
            return nil
        }
        if observations.count >= 2 {
            let distance = abs(nearest.element.date.timeIntervalSince(selectedDate))
            if distance > maxSelectionSnapSeconds(first: first.date, last: last.date) {
                return nil
            }
        }
        return nearest.offset
    }

    /// Applies `selectedDate` to pre-computed base rows (`selectedDate == nil`) without re-filtering `dataPoints`.
    static func applyingSelection(
        to baseRows: [EventAtlasObservationRow11666],
        selectedDate: Date?
    ) -> [EventAtlasObservationRow11666] {
        guard let selectedDate, !baseRows.isEmpty else { return baseRows }
        let tuples = baseRows.map { (date: $0.date, probability: $0.probability) }
        guard let selectedIndex = resolveSelectedIndex(in: tuples, selectedDate: selectedDate) else {
            return baseRows
        }
        let count = baseRows.count
        let stride = solidMarkStride(pointCount: count)
        return baseRows.map { row in
            let isSelected = row.index == selectedIndex
            guard isSelected != row.isSelected else { return row }
            let isLast = row.index == count - 1
            let isVisibleSolid = !row.isOpening && (isLast || isSelected || row.index % stride == 0)
            return EventAtlasObservationRow11666(
                index: row.index,
                date: row.date,
                probability: row.probability,
                isOpening: row.isOpening,
                isVisibleSolid: isVisibleSolid,
                isSelected: isSelected
            )
        }
    }

    /// Builds the selected reading readout model for the observation nearest `selectedDate`.
    static func selectedReading(
        rows: [EventAtlasObservationRow11666],
        selectedDate: Date?,
        outcomeName: String,
        includesOpening: Bool,
        openingLabel: String = "Pregame"
    ) -> EventAtlasSelectedReadingModel11666? {
        let resolvedRows = rows.contains(where: \.isSelected)
            ? rows
            : applyingSelection(to: rows, selectedDate: selectedDate)
        guard selectedDate != nil, let row = resolvedRows.first(where: \.isSelected) else { return nil }
        let effectiveOpening = includesOpening && row.isOpening
        return EventAtlasSelectedReadingModel11666(
            outcomeName: outcomeName,
            badgeText: effectiveOpening ? openingLabel : "Recorded",
            probabilityText: formatProbability(row.probability),
            timestampTextPT: formatExactTimestampPT(row.date),
            isOpening: effectiveOpening
        )
    }

    /// Determines whether the finished primary line ends on the winning or losing side (`✓ Won` or `✗ Lost`).
    /// Relies strictly on the page's authoritative `EventOutcome.resolve` (`servedSettledResult` +
    /// `homeScoreOverride`/`awayScoreOverride`), never guessing a winner from mid-game history rows
    /// when the page is `final_unresolved` or lacks confirmed scores.
    /// Returns `nil` when the game is not finished, scores are tied/absent, or there is no primary reading.
    static func settledResult(
        dataPoints: [ChartDataPoint],
        checkpoints: PublicationCheckpointMount4974? = nil,
        history: EventHistoryResponse? = nil,
        status: String?,
        sides: ChartProbabilityAxis9483.Sides,
        homeScoreOverride: Int? = nil,
        awayScoreOverride: Int? = nil,
        servedSettledResult: String? = nil
    ) -> EventAtlasSettledResult11666? {
        guard EventState.isFinished(status) else { return nil }
        guard let end = OddsChartView.finishedEnd9483(
            dataPoints: dataPoints,
            checkpoints: checkpoints,
            finished: true
        ), end.probability.isFinite else {
            return nil
        }

        let resolvedOutcome = EventOutcome.resolve(
            status: status,
            homeScore: homeScoreOverride,
            awayScore: awayScoreOverride,
            servedResult: servedSettledResult
        )

        let homeWon: Bool
        switch resolvedOutcome {
        case .home:
            homeWon = true
        case .away:
            homeWon = false
        case .draw, .undecided:
            return nil
        }

        let endIsAway = sides == .homeAndAway && end.probability < 0.5
        let endSideWon = endIsAway ? !homeWon : homeWon
        return endSideWon ? .won : .lost
    }

    /// Computes the placement of the settled result word (`✓ Won` or `✗ Lost`) beside the last recorded dot.
    /// Reserves the top 20pt period-chip band (`OddsChartView.endLabelTopReserve9483`) plus half the badge height
    /// (`minTopY = 28`) when placed left of a right-edge terminal dot so `✓ Won` never overlaps the `Final`
    /// period marker chip at `y = 10`.
    static func resultWordPlacement(
        result: EventAtlasSettledResult11666,
        dotX: CGFloat,
        dotY: CGFloat,
        plotWidth: CGFloat
    ) -> EventAtlasResultWordPlacement11666 {
        let placesLeft = dotX > plotWidth - 56 && dotX - 48 > 0
        let offset: CGFloat = 26
        let labelX = placesLeft ? dotX - offset : dotX + offset
        let minTopY: CGFloat = placesLeft ? 28 : 10
        return EventAtlasResultWordPlacement11666(
            result: result,
            word: result.word,
            placesLeftOfDot: placesLeft,
            dotX: dotX,
            dotY: dotY,
            labelX: labelX,
            labelY: min(max(minTopY, dotY), 210)
        )
    }
}

// MARK: - SwiftUI Views (#11666 Step E2)

/// Header above the native chart plot rendering the Atlas mark-grammar key and a fixed-height
/// selected reading readout slot (#11666 Step E2).
///
/// `selection` is observed only by `EventAtlasSelectedReadingSlot11666` (`#8651`), so scrubbing
/// never rebuilds the static mark-grammar key, and the readout slot keeps a stable height so
/// the chart plot below never jumps under the reader's finger.
struct EventAtlasChartHeaderView11666: View {
    let selection: OddsChartSelection
    let dataPoints: [ChartDataPoint]
    let checkpoints: PublicationCheckpointMount4974?
    let history: EventHistoryResponse?
    let status: String?
    let sides: ChartProbabilityAxis9483.Sides
    let includesOpening: Bool
    let homeName: String
    let primaryColor: Color
    var homeScore: Int? = nil
    var awayScore: Int? = nil
    var servedSettledResult: String? = nil
    var gameStart: Date? = nil

    var body: some View {
        let settled = EventAtlasChartMarks11666.settledResult(
            dataPoints: dataPoints,
            checkpoints: checkpoints,
            history: history,
            status: status,
            sides: sides,
            homeScoreOverride: homeScore,
            awayScoreOverride: awayScore,
            servedSettledResult: servedSettledResult
        )
        let keyModel = EventAtlasChartMarkKeyModel11666(
            settledResult: settled,
            includesOpening: includesOpening
        )
        let baseRows = EventAtlasChartMarks11666.observationRows(
            dataPoints: dataPoints,
            checkpoints: checkpoints,
            includesOpening: includesOpening,
            selectedDate: nil,
            gameStart: gameStart
        )

        VStack(alignment: .leading, spacing: 6) {
            FlowLayout(spacing: 10) {
                if keyModel.showsOpening {
                    HStack(spacing: 4) {
                        Circle()
                            .strokeBorder(Color.primary, lineWidth: 1.75)
                            .background(Circle().fill(Color.systemBackground))
                            .frame(width: 8, height: 8)
                        Text(keyModel.openingLabel)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
                HStack(spacing: 4) {
                    Circle()
                        .fill(Color.primary)
                        .frame(width: 8, height: 8)
                    Text(keyModel.recordedLabel)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                HStack(spacing: 4) {
                    RoundedRectangle(cornerRadius: 1)
                        .fill(Color.primary)
                        .frame(width: 12, height: 2)
                    Text(keyModel.changeLabel)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                if keyModel.showsSettledResultWords {
                    HStack(spacing: 3) {
                        Text(keyModel.settledWonWord)
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle(.primary)
                        Text("/")
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                        Text(keyModel.settledLostWord)
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle(.secondary)
                        Text(keyModel.settledExplanation)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    .accessibilityIdentifier("event.atlas.chartKeyResultWord")
                }
            }
            .accessibilityElement(children: .combine)
            .accessibilityIdentifier("event.atlas.chartMarkKey")

            EventAtlasSelectedReadingSlot11666(
                selection: selection,
                baseRows: baseRows,
                outcomeName: homeName,
                includesOpening: includesOpening,
                openingLabel: keyModel.openingLabel,
                tapHint: keyModel.tapHint,
                primaryColor: primaryColor
            )
        }
        .padding(.bottom, 2)
    }
}

/// Fixed-height readout slot that observes `selection` without shifting the chart plot vertically.
private struct EventAtlasSelectedReadingSlot11666: View {
    @ObservedObject var selection: OddsChartSelection
    let baseRows: [EventAtlasObservationRow11666]
    let outcomeName: String
    let includesOpening: Bool
    let openingLabel: String
    let tapHint: String
    let primaryColor: Color

    var body: some View {
        let selectedModel = EventAtlasChartMarks11666.selectedReading(
            rows: baseRows,
            selectedDate: selection.date,
            outcomeName: outcomeName,
            includesOpening: includesOpening,
            openingLabel: openingLabel
        )

        Group {
            if let selectedModel {
                ViewThatFits(in: .horizontal) {
                    singleLineReadout(selectedModel)
                    twoLineReadout(selectedModel)
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .frame(maxWidth: .infinity, minHeight: 28, alignment: .leading)
                .background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 8))
                .accessibilityElement(children: .combine)
                .accessibilityIdentifier("event.atlas.selectedReading")
            } else {
                HStack(spacing: 6) {
                    Text(tapHint)
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                    Spacer(minLength: 0)
                }
                .padding(.horizontal, 2)
                .padding(.vertical, 6)
                .frame(maxWidth: .infinity, minHeight: 28, alignment: .leading)
                .accessibilityIdentifier("event.atlas.selectedReadingPrompt")
            }
        }
    }

    @ViewBuilder
    private func markDot(isOpening: Bool) -> some View {
        if isOpening {
            Circle()
                .strokeBorder(primaryColor, lineWidth: 2)
                .background(Circle().fill(Color.systemBackground))
                .frame(width: 8, height: 8)
        } else {
            Circle()
                .fill(primaryColor)
                .frame(width: 8, height: 8)
        }
    }

    private func singleLineReadout(_ selectedModel: EventAtlasSelectedReadingModel11666) -> some View {
        HStack(spacing: 6) {
            markDot(isOpening: selectedModel.isOpening)
            Text(selectedModel.outcomeName)
                .font(.caption2.weight(.semibold))
                .foregroundStyle(.primary)
                .fixedSize(horizontal: true, vertical: false)
            Text(selectedModel.badgeText.uppercased())
                .font(.system(size: 9, weight: .semibold))
                .foregroundStyle(.secondary)
                .padding(.horizontal, 5)
                .padding(.vertical, 1.5)
                .background(Color.secondary.opacity(0.12), in: RoundedRectangle(cornerRadius: 4))
                .fixedSize(horizontal: true, vertical: false)
            Text(selectedModel.probabilityText)
                .font(.caption2.monospacedDigit().weight(.bold))
                .foregroundStyle(.primary)
                .fixedSize(horizontal: true, vertical: false)
            Text("·")
                .font(.caption2)
                .foregroundStyle(.tertiary)
            Text(selectedModel.timestampTextPT)
                .font(.caption2.monospacedDigit())
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: true, vertical: false)
            Spacer(minLength: 4)
            Button("Clear") {
                selection.end()
            }
            .font(.caption2.weight(.semibold))
            .buttonStyle(.plain)
            .foregroundStyle(.secondary)
            .fixedSize(horizontal: true, vertical: false)
        }
    }

    private func twoLineReadout(_ selectedModel: EventAtlasSelectedReadingModel11666) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 6) {
                markDot(isOpening: selectedModel.isOpening)
                Text(selectedModel.outcomeName)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(.primary)
                Text(selectedModel.badgeText.uppercased())
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 5)
                    .padding(.vertical, 1.5)
                    .background(Color.secondary.opacity(0.12), in: RoundedRectangle(cornerRadius: 4))
                Text(selectedModel.probabilityText)
                    .font(.caption2.monospacedDigit().weight(.bold))
                    .foregroundStyle(.primary)
                Spacer(minLength: 4)
                Button("Clear") {
                    selection.end()
                }
                .font(.caption2.weight(.semibold))
                .buttonStyle(.plain)
                .foregroundStyle(.secondary)
            }
            Text(selectedModel.timestampTextPT)
                .font(.caption2.monospacedDigit())
                .foregroundStyle(.secondary)
        }
    }
}

/// Chart plot overlay rendering the hollow opening mark (`○`), solid recorded marks (`●`),
/// selected ring, and settled result word (`✓ Won` / `✗ Lost`) (#11666 Step E2).
///
/// Static marks are drawn without observing `selection`; only `EventAtlasSelectedMarkOverlay11666`
/// subscribes to `selection`, preserving `#8651`'s scrub isolation.
struct EventAtlasChartOverlay11666: View {
    let selection: OddsChartSelection
    let proxy: ChartProxy
    let plotFrame: CGRect
    let dataPoints: [ChartDataPoint]
    let checkpoints: PublicationCheckpointMount4974?
    let history: EventHistoryResponse?
    let status: String?
    let sides: ChartProbabilityAxis9483.Sides
    let includesOpening: Bool
    let primaryColor: Color
    var homeScore: Int? = nil
    var awayScore: Int? = nil
    var servedSettledResult: String? = nil
    var gameStart: Date? = nil
    var settledResult: EventAtlasSettledResult11666? = nil

    var body: some View {
        let baseRows = EventAtlasChartMarks11666.observationRows(
            dataPoints: dataPoints,
            checkpoints: checkpoints,
            includesOpening: includesOpening,
            selectedDate: nil,
            gameStart: gameStart
        )
        let settled = settledResult ?? EventAtlasChartMarks11666.settledResult(
            dataPoints: dataPoints,
            checkpoints: checkpoints,
            history: history,
            status: status,
            sides: sides,
            homeScoreOverride: homeScore,
            awayScoreOverride: awayScore,
            servedSettledResult: servedSettledResult
        )
        let finishedEnd = OddsChartView.finishedEnd9483(
            dataPoints: dataPoints,
            checkpoints: checkpoints,
            finished: EventState.isFinished(status)
        )

        ZStack {
            ForEach(baseRows) { row in
                if let x = proxy.position(forX: row.date),
                   let y = proxy.position(forY: row.probability),
                   x >= 0, x <= plotFrame.width, y >= 0, y <= plotFrame.height {
                    let screenX = plotFrame.minX + x
                    let screenY = plotFrame.minY + y

                    if row.isOpening {
                        Circle()
                            .fill(Color.systemBackground)
                            .overlay(
                                Circle()
                                    .stroke(primaryColor, lineWidth: 2)
                            )
                            .frame(width: 8, height: 8)
                            .position(x: screenX, y: screenY)
                    } else if row.isVisibleSolid {
                        Circle()
                            .fill(primaryColor)
                            .frame(width: 6, height: 6)
                            .position(x: screenX, y: screenY)
                    }
                }
            }

            EventAtlasSelectedMarkOverlay11666(
                selection: selection,
                baseRows: baseRows,
                proxy: proxy,
                plotFrame: plotFrame,
                primaryColor: primaryColor
            )

            if let settled, let end = finishedEnd,
               let x = proxy.position(forX: end.date),
               let y = proxy.position(forY: end.probability),
               x >= 0, x <= plotFrame.width, y >= 0, y <= plotFrame.height {
                let placement = EventAtlasChartMarks11666.resultWordPlacement(
                    result: settled,
                    dotX: x,
                    dotY: y,
                    plotWidth: plotFrame.width
                )
                Text(placement.word)
                    .font(.system(size: 10, weight: .bold))
                    .foregroundStyle(settled == .won ? Color.green : Color.secondary)
                    .padding(.horizontal, 4)
                    .padding(.vertical, 1.5)
                    .background(Color.systemBackground.opacity(0.88), in: RoundedRectangle(cornerRadius: 3))
                    .position(
                        x: plotFrame.minX + placement.labelX,
                        y: plotFrame.minY + placement.labelY
                    )
                    .accessibilityIdentifier("event.atlas.resultWord")
            }
        }
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}

/// Lightweight selection ring overlay that observes `selection` without rebuilding static marks.
private struct EventAtlasSelectedMarkOverlay11666: View {
    @ObservedObject var selection: OddsChartSelection
    let baseRows: [EventAtlasObservationRow11666]
    let proxy: ChartProxy
    let plotFrame: CGRect
    let primaryColor: Color

    var body: some View {
        let rows = EventAtlasChartMarks11666.applyingSelection(to: baseRows, selectedDate: selection.date)
        if let row = rows.first(where: \.isSelected),
           let x = proxy.position(forX: row.date),
           let y = proxy.position(forY: row.probability),
           x >= 0, x <= plotFrame.width, y >= 0, y <= plotFrame.height {
            let screenX = plotFrame.minX + x
            let screenY = plotFrame.minY + y

            ZStack {
                if row.isOpening {
                    Circle()
                        .fill(Color.systemBackground)
                        .overlay(
                            Circle()
                                .stroke(primaryColor, lineWidth: 2.5)
                        )
                        .frame(width: 10, height: 10)
                        .position(x: screenX, y: screenY)
                } else {
                    Circle()
                        .fill(primaryColor)
                        .overlay(
                            Circle()
                                .stroke(Color.systemBackground, lineWidth: 1.5)
                        )
                        .frame(width: 9, height: 9)
                        .position(x: screenX, y: screenY)
                }
                Circle()
                    .stroke(primaryColor.opacity(0.6), lineWidth: 1.5)
                    .frame(width: 14, height: 14)
                    .position(x: screenX, y: screenY)
            }
        }
    }
}
