import SwiftUI
import Charts
import Combine

/// #4974 — what a scrub over a finished game's recorded window landed on.
/// Decided by `PublicationCheckpointMount4974.selection(atChartX:…)` and set
/// only while that mount is active; nil on every other chart, which therefore
/// scrubs exactly as before.
enum PublicationCheckpointScrub4974: Equatable {
    /// A stored checkpoint within reach of the finger. The crosshair stands at
    /// the checkpoint's own time, never the cursor's.
    case checkpoint(PublicationJourney4974.Checkpoint)
    /// Inside the recorded window with no checkpoint within reach, or a scrub
    /// whose time could not be resolved: nothing is known here, and the readout
    /// says so instead of falling back to a resting number.
    case withheld
}

/// Finger movement belongs to the small selection layers, not the plot's owner.
/// OddsChartView stores this reference in @State (NOT @StateObject): only the
/// crosshair and readout subscribe, so selecting never rebuilds the data marks.
final class OddsChartSelection: ObservableObject {
    @Published private(set) var date: Date?
    /// #4974 — see `PublicationCheckpointScrub4974`. A withheld scrub may have
    /// no `date` and is still a scrub (`isScrubbing`).
    @Published private(set) var checkpoint: PublicationCheckpointScrub4974?
    private var scrub = ChartScrubState()

    var holdsTheScrollStill: Bool { scrub.scrubs }

    /// A finger is on the chart. Not `date != nil`: a withheld scrub whose time
    /// could not be resolved must not read as idle (#4974).
    var isScrubbing: Bool { date != nil || checkpoint != nil }

    func change(date: Date?, translation: CGSize, checkpoint: PublicationCheckpointScrub4974? = nil) {
        scrub.change(width: translation.width, height: translation.height)
        if scrub.scrubs {
            select(date, checkpoint: checkpoint)
        } else {
            select(nil)
        }
    }

    func hold(date: Date?, checkpoint: PublicationCheckpointScrub4974? = nil) {
        scrub.hold()
        select(date, checkpoint: checkpoint)
    }

    func select(_ date: Date?, checkpoint: PublicationCheckpointScrub4974? = nil) {
        if self.date != date { self.date = date }
        if self.checkpoint != checkpoint { self.checkpoint = checkpoint }
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
    /// #4974 — set by `publicationCheckpoints(_:)`. Nil keeps this readout
    /// exactly as it was, resting fallback included.
    var checkpoints: PublicationCheckpointMount4974? = nil

    var body: some View {
        if let checkpoints {
            // Every state names its own point or withholds: the card is never
            // handed nil, so neither its resting `lastPoint` nor the page's
            // can stand in for a moment nobody recorded.
            PublicationCheckpointReadoutSlot4974(
                card: readout,
                readout: checkpoints.readout(date: selection.date, scrub: selection.checkpoint),
                sportKey: sportKey,
                reserve: checkpoints.reservePoint(sportKey: sportKey))
        } else {
            readout
                .resting(on: OddsChartView.fullscreenRestingPoint(
                    in: dataPoints, sportKey: sportKey, pageGaveCard: pageGaveCard))
                .showing(Self.selectedPoint(at: selection.date, in: dataPoints,
                                            sportKey: sportKey, pageGaveCard: pageGaveCard))
        }
    }

    /// #4974 — this readout over a finished game's adopted checkpoints. The
    /// fullscreen chart and the inline overlay take the SAME mount.
    func publicationCheckpoints(_ mount: PublicationCheckpointMount4974?) -> OddsChartSelectionReadout {
        var copy = self
        copy.checkpoints = mount
        return copy
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
    /// #4974 — a finished game's adopted checkpoints, or nil for today's overlay.
    var checkpoints: PublicationCheckpointMount4974? = nil
    /// #5271 — a draw-priced sport speaks no away number, as the card prints none.
    var sportKey: String?
    /// #8651 — the inline chart's scrub tooltip. Build 30 drew a bare crosshair
    /// where the page gave no readout card: "scrubbing is smooth but no tooltip
    /// appears". #9517 — it is the page's card too, which no longer rests above
    /// the plot (`OddsChartView.inlineScrubCard`).
    var floatingCard: GamePlayCardView? = nil

    var body: some View {
        ZStack {
            if let checkpoints {
                // #4974 — a withheld scrub is a scrub even with no time to
                // stand the crosshair on, so this asks `isScrubbing`, not `date`.
                if selection.isScrubbing {
                    let x = selection.date.flatMap { proxy.position(forX: $0) }
                    if let x { crosshair(atX: x) }
                    if let floatingCard {
                        floated(PublicationCheckpointReadoutSlot4974(
                                    card: floatingCard,
                                    readout: checkpoints.readout(date: selection.date,
                                                                 scrub: selection.checkpoint),
                                    sportKey: sportKey),
                                crosshairX: x)
                    }
                }
            } else if let date = selection.date, let x = proxy.position(forX: date) {
                crosshair(atX: x)
                if let floatingCard, let point = OddsChartSelectionReadout.selectedPoint(
                    at: date, in: dataPoints, sportKey: sportKey, pageGaveCard: pageGaveCard) {
                    // Floats, so the plot never moves under the finger (#925), on
                    // the side away from the crosshair so it never covers it.
                    floated(floatingCard.showing(point), crosshairX: x)
                }
            }
            Color.clear
        }
        .allowsHitTesting(false)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Win probability over time")
        .accessibilityValue(checkpoints?.accessibilityValue(
            date: selection.date, scrub: selection.checkpoint,
            homeShort: homeShort, awayShort: awayShort, moments: moments,
            gameFinished: gameFinished, sportKey: sportKey)
            ?? OddsChartView.accessibilityValue(
            dataPoints: dataPoints, selectedDate: selection.date,
            homeShort: homeShort, awayShort: awayShort, moments: moments,
            pageGaveCard: pageGaveCard, gameFinished: gameFinished,
            sportKey: sportKey))
    }

    private func crosshair(atX x: CGFloat) -> some View {
        Rectangle()
            .fill(.primary.opacity(0.4))
            .frame(width: 1, height: plotFrame.height)
            .position(x: plotFrame.minX + x, y: plotFrame.midY)
    }

    /// The floating card's frame, opposite the crosshair. A withheld scrub with
    /// no resolvable time has no crosshair and takes the leading corner.
    private func floated<Card: View>(_ card: Card, crosshairX x: CGFloat?) -> some View {
        card
            .padding(.horizontal, 8)
            .padding(.vertical, 2)
            .frame(width: min(plotFrame.width * 0.62, 240))
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
            .padding(6)
            .frame(width: plotFrame.width, height: plotFrame.height,
                   alignment: x.map { Self.floatingCardAlignment(crosshairX: $0, plotWidth: plotFrame.width) }
                       ?? .topLeading)
            .position(x: plotFrame.midX, y: plotFrame.midY)
    }

    /// The top corner opposite the crosshair.
    static func floatingCardAlignment(crosshairX: CGFloat, plotWidth: CGFloat) -> Alignment {
        crosshairX < plotWidth / 2 ? .topTrailing : .topLeading
    }
}

/// #4974 — the scrub/resting readout while a finished game's checkpoints are
/// mounted, floating inline and above the fullscreen plot alike.
///
/// Three states and no fallback. On a surviving line point outside the
/// recorded window it is the page's card, exactly as a scrub there reads today.
/// On a stored checkpoint it prints that checkpoint's own number, through the
/// same card, beneath its own Pacific minute — no score, period, play or result
/// rides along, because a checkpoint records none. Anywhere else it says no
/// reading is there. The card is never shown `nil`, so neither its resting
/// point nor the page's can fill a moment nobody recorded.
struct PublicationCheckpointReadoutSlot4974: View {
    let card: GamePlayCardView
    let readout: PublicationCheckpointReadout4974
    let sportKey: String?
    /// Fullscreen only: a surviving line point the card would print, held
    /// invisibly behind the checkpoint and withheld rows so the plot beneath
    /// keeps its place as the finger crosses the window's edge (#925).
    var reserve: GamePlayPoint? = nil

    static let withheldText = "No reading here"

    /// The checkpoint clock's zone. A checkpoint is a stored instant; it is
    /// named in one fixed zone with the zone printed, never the device's.
    static let pacific = TimeZone(identifier: "America/Los_Angeles") ?? .gmt

    var body: some View {
        switch readout {
        case .legacy(let point):
            card.showing(OddsChartView.playPoint(for: point, sportKey: sportKey))
        case .checkpoint(let checkpoint):
            reserved {
                VStack(alignment: .leading, spacing: 0) {
                    Text(Self.clock(checkpoint.date, dated: card.floats))
                        .font(.caption2)
                        .monospacedDigit()
                        .foregroundStyle(.tertiary)
                        .lineLimit(1)
                        .fixedSize()
                    card.showing(Self.playPoint(for: checkpoint, sportKey: sportKey))
                }
            }
        case .withheld:
            reserved {
                Text(Self.withheldText)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.vertical, 4)
            }
        }
    }

    private func reserved<Content: View>(@ViewBuilder _ content: () -> Content) -> some View {
        ZStack(alignment: .topLeading) {
            if let reserve {
                card.showing(reserve)
                    .hidden()
                    .accessibilityHidden(true)
            }
            content()
        }
    }

    /// A checkpoint as the card prints it: its HOME probability verbatim and
    /// the away side only where the sport prices no draw (#5271). The
    /// timestamp is empty on purpose — the card would print it in the device's
    /// zone, and the row above prints the checkpoint's own Pacific minute.
    static func playPoint(for checkpoint: PublicationJourney4974.Checkpoint,
                          sportKey: String?) -> GamePlayPoint {
        let probability = checkpoint.vertex.p
        return GamePlayPoint(
            timestamp: "",
            homeProb: probability,
            awayProb: DrawPricedWinner.printablePair(
                away: 1.0 - probability,
                home: probability,
                sport: sportKey)?.away)
    }

    /// "1:15 PM PT" — Pacific, to the minute. `dated` adds the weekday the
    /// floating card's own clock carries ("Sun 1:15 PM PT").
    static func clock(_ date: Date, dated: Bool, locale: Locale = .autoupdatingCurrent) -> String {
        let style = dated
            ? Date.FormatStyle(locale: locale, timeZone: pacific).weekday(.abbreviated).hour().minute()
            : Date.FormatStyle(date: .omitted, time: .shortened, locale: locale, timeZone: pacific)
        return "\(date.formatted(style)) PT"
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
