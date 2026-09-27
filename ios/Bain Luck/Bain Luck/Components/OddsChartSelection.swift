import SwiftUI
import Charts
import Combine

/// Finger movement belongs to the small selection layers, not the plot's owner.
/// OddsChartView stores this reference in @State (NOT @StateObject): only the
/// crosshair and readout subscribe, so selecting never rebuilds the data marks.
final class OddsChartSelection: ObservableObject {
    @Published private(set) var date: Date?
    private var scrub = ChartScrubState()

    var holdsTheScrollStill: Bool { scrub.scrubs }

    func change(date: Date?, translation: CGSize) {
        scrub.change(width: translation.width, height: translation.height)
        select(scrub.scrubs ? date : nil)
    }

    func hold(date: Date?) {
        scrub.hold()
        select(date)
    }

    func select(_ date: Date?) {
        guard self.date != date else { return }
        self.date = date
    }

    func end() {
        scrub.end()
        select(nil)
    }
}

struct OddsChartSelectionReadout: View {
    @ObservedObject var selection: OddsChartSelection
    let readout: GamePlayCardView
    let dataPoints: [ChartDataPoint]
    let sportKey: String?
    /// #9185 — false only for the fullscreen chart's OWN card (the page gave
    /// none), which may rest on a lone venue line; see `fullscreenRestingPoint`.
    var pageGaveCard = true

    var body: some View {
        readout
            .resting(on: OddsChartView.fullscreenRestingPoint(
                in: dataPoints, sportKey: sportKey, pageGaveCard: pageGaveCard))
            .showing(Self.selectedPoint(at: selection.date, in: dataPoints,
                                        sportKey: sportKey, pageGaveCard: pageGaveCard))
    }

    /// The scrubbed moment, on the same series the card rests on (#9185).
    static func selectedPoint(at date: Date?, in points: [ChartDataPoint], sportKey: String?,
                              pageGaveCard: Bool) -> GamePlayPoint? {
        guard let date, let source = OddsChartView.readoutSource(in: points, pageGaveCard: pageGaveCard),
              let nearest = OddsChartView.nearestSnapshot(to: date, in: points, source: source) else { return nil }
        return OddsChartView.playPoint(for: nearest, sportKey: sportKey)
    }
}

/// A line in plot coordinates, not a RuleMark in the data series. Its position
/// can change without asking Swift Charts to lay out every observed point.
struct OddsChartSelectionOverlay: View {
    @ObservedObject var selection: OddsChartSelection
    let proxy: ChartProxy
    let plotFrame: CGRect
    let dataPoints: [ChartDataPoint]
    let homeShort: String
    let awayShort: String
    let moments: [ChartMoment]
    /// #9185 — the readout card's `pageGaveCard`, so VoiceOver speaks the
    /// series the card prints (`readoutSource`).
    var pageGaveCard = true
    /// The game is over: a settled end is spoken as the result, as the card prints it.
    var gameFinished = false
    /// #5271 — a draw-priced sport speaks no away number, as the card prints none.
    var sportKey: String?

    var body: some View {
        ZStack {
            if let date = selection.date, let x = proxy.position(forX: date) {
                Rectangle()
                    .fill(.primary.opacity(0.4))
                    .frame(width: 1, height: plotFrame.height)
                    .position(x: plotFrame.minX + x, y: plotFrame.midY)
            }
            Color.clear
        }
        .allowsHitTesting(false)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Win probability over time")
        .accessibilityValue(OddsChartView.accessibilityValue(
            dataPoints: dataPoints, selectedDate: selection.date,
            homeShort: homeShort, awayShort: awayShort, moments: moments,
            pageGaveCard: pageGaveCard, gameFinished: gameFinished,
            sportKey: sportKey))
    }
}

/// The animation subscribes only to the small selection leaf. Finger movement
/// never observes or invalidates OddsChartView's data marks.
struct LiveChartEndpointFeedback: View {
    @ObservedObject var selection: OddsChartSelection
    let activity: LivePriceActivity?
    let probability: Double
    let isLive: Bool
    let color: Color

    var body: some View {
        LivePriceEndpointPulse(sequence: activity?.sequence ?? 0,
                               valueChanged: activity?.displayedValueChanged ?? false,
                               color: color,
                               isEnabled: isLive && selection.date == nil && matchesAcceptedPrice)
    }

    private var matchesAcceptedPrice: Bool {
        guard let accepted = activity?.homeProbability else { return false }
        return abs(accepted - probability) < 0.000001
    }
}
