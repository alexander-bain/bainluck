import SwiftUI
import Charts

// MARK: - #9436 — the number on the end of the line

/// The hero's current home number, carried to the chart's live edge.
///
/// Built from `LivePriceActivity.displayedLabels(in:)` — the one function the
/// hero pair also prints from — so the label beside the dot cannot disagree
/// with the hero on rounding, the served-or-neither pair (#2085) or the .445
/// complement. Only quote-eligible event phases can mark a current price;
/// the sports LIVE label remains independent.
///
/// `source` is the hero's own provenance (`hero_probability_source`). Only a
/// `"blend"` hero is the number the blend line ends on — the backend pins the
/// aggregate edge to nothing else (`_PINNABLE_HERO_SOURCE`) — so an `opening`
/// or absent source never labels a line, whatever value it happens to share.
nonisolated struct LiveEdgeReading: Equatable {
    let homeProbability: Double
    let homeLabel: String
    var source: String? = "blend"

    static func current(in event: EventDetail) -> LiveEdgeReading? {
        guard EventPriceStreaming.isEligible(event.status),
              let probability = event.currentOdds?.homeProbability,
              let label = LivePriceActivity.displayedLabels(in: event).home else { return nil }
        return LiveEdgeReading(homeProbability: probability, homeLabel: label,
                               source: event.heroProbabilitySource)
    }
}

/// One drawn vertex of the primary line.
nonisolated struct LiveEdgeVertex: Equatable {
    let date: Date
    let probability: Double
}

/// The primary line's last segment, drawn by `LiveChartEdgeMarker` instead of
/// the plot. `from` is nil when the newest vertex opens its own observation
/// run (#7878): nothing joins it, so nothing may glide into it.
nonisolated struct LiveEdgeTail: Equatable {
    let from: LiveEdgeVertex?
    let to: LiveEdgeVertex
}

/// The primary series split for drawing: the plot draws `segments`, the
/// overlay draws `tail`. `continuedRun` is the run whose newest vertex moved
/// to the overlay — its remaining lone vertex, if any, is a line start, not an
/// isolated observation, so it gets no `PointMark`.
struct LiveEdgeSplit {
    let source: String
    let segments: [[ChartDataPoint]]
    let continuedRun: Int
    let tail: LiveEdgeTail
}

enum LiveChartEdgeMarkerPlan {
    /// One accepted change: long enough to follow, short enough that the next
    /// ~2 s update never queues behind it.
    static let glideDuration: TimeInterval = 0.35
    static let dotDiameter: CGFloat = 8
    static let labelGap: CGFloat = 6

    /// The hero's accepted value and the line's newest vertex are one number.
    /// Anything else — a history point the push has not reached, a REST reading
    /// the chart rejected as older — is not labelled current.
    static func isCurrent(tipProbability: Double, reading: LiveEdgeReading) -> Bool {
        abs(tipProbability - reading.homeProbability) < 0.000001
    }

    /// The drawn vertex that carries the hero's number, or nil. Equality alone
    /// never picks a series — each arm names why THIS line is the hero's:
    ///
    /// 1. **A blend line on the chart:** it is the only candidate. The backend
    ///    pins its edge to a `"blend"` hero and pushed frames extend it with
    ///    the same `p` the hero adopts.
    /// 2. **No blend line (a single-venue page):** the venue whose series the
    ///    newest ADOPTED frame extended, and only when that frame's own venue
    ///    reading and its blend are both the hero's value — the frame ties the
    ///    line to the number. A REST-only hero, a frame from another venue or
    ///    a blend that is not the venue's reading draws no number.
    ///
    /// The sportsbook consensus is never labelled: nothing on the payload says
    /// the hero is its value.
    static func edgeVertex(in points: [ChartDataPoint], visible: [String],
                           reading: LiveEdgeReading, latestFrame: LiveBlendPoint?) -> ChartDataPoint? {
        guard reading.source == "blend" else { return nil }
        let newest: ChartDataPoint?
        if points.contains(where: { $0.source == "aggregate" }) {
            newest = OddsChartView.latestPoint(in: points, source: "aggregate")
        } else {
            guard let frame = latestFrame, let venue = frame.source, let venueValue = frame.sourceProbability,
                  isCurrent(tipProbability: frame.homeProbability, reading: reading),
                  isCurrent(tipProbability: venueValue, reading: reading),
                  let tip = OddsChartView.latestPoint(in: points, source: venue),
                  tip.date >= frame.date else { return nil }
            newest = tip
        }
        guard let newest, visible.contains(newest.source),
              isCurrent(tipProbability: newest.probability, reading: reading) else { return nil }
        return newest
    }

    /// Move the newest primary vertex out of the plot. Nil when that vertex is
    /// not the last one drawn (the split would leave a gap) — the caller then
    /// draws the full line and no marker.
    static func split(segments: [[ChartDataPoint]], newest: ChartDataPoint, source: String) -> LiveEdgeSplit? {
        guard let lastRun = segments.indices.last, let tip = segments[lastRun].last,
              tip.id == newest.id else { return nil }
        var trimmed = segments
        trimmed[lastRun].removeLast()
        let from = trimmed[lastRun].last.map { LiveEdgeVertex(date: $0.date, probability: $0.probability) }
        if trimmed[lastRun].isEmpty { trimmed.removeLast() }
        return LiveEdgeSplit(
            source: source, segments: trimmed,
            continuedRun: from == nil ? -1 : lastRun,
            tail: LiveEdgeTail(from: from, to: LiveEdgeVertex(date: tip.date, probability: tip.probability)))
    }

    /// A glide moves the tip between two accepted vertices while the overlay
    /// keeps drawing the segment from `new.from` to it, so the dot is the
    /// line's end in every frame. Two shapes qualify:
    ///
    /// - **an append** — the new segment begins exactly where the old tip was;
    /// - **a pin replacement** (`replacesPin`) — a detail+history reread
    ///   (`rereadPricePair`) replaces the response-time pin the backend puts on
    ///   the end of the blend (`_pin_blend_edge`), on the SAME predecessor.
    ///
    /// A segment break, any other replacement, an unchanged tip, a background
    /// scene or Reduce Motion snaps.
    static func glides(from old: LiveEdgeTail, to new: LiveEdgeTail,
                       reduceMotion: Bool, sceneActive: Bool) -> Bool {
        guard !reduceMotion, sceneActive, new.to != old.to else { return false }
        return new.from == old.to || replacesPin(old: old, new: new)
    }

    /// The old pin was not persisted, so the new history ends on the same
    /// last observation with a fresh pin after it. Same predecessor (never a
    /// gap: a nil `from` has no segment) and not earlier than the old pin.
    static func replacesPin(old: LiveEdgeTail, new: LiveEdgeTail) -> Bool {
        guard let from = new.from, from == old.from else { return false }
        return new.to.date >= old.to.date
    }

    /// Which way a changed printed value slides: up (−1) for a rise or an
    /// unknown direction, down (+1) for a fall.
    static func shiftDirection(rising: Bool?) -> CGFloat {
        rising == false ? 1 : -1
    }

    /// Centre of the label, in plot-local points. Beside the dot where the
    /// plot has room to its right (the line ends at the dot, so nothing is
    /// covered). Otherwise right-aligned to the dot and stacked: on the side
    /// away from the plot edge the dot is nearest, unless that side would
    /// cover the last segment (`from`) and the other side would not — the
    /// newest move is the one thing the label must never hide. Clamped inside
    /// the plot at both edges and at 0/100.
    static func labelCenter(tip: CGPoint, from: CGPoint? = nil, label: CGSize, plot: CGSize) -> CGPoint {
        let radius = dotDiameter / 2
        func clamped(_ c: CGPoint) -> CGPoint {
            CGPoint(x: min(max(c.x, label.width / 2), max(plot.width - label.width / 2, label.width / 2)),
                    y: min(max(c.y, label.height / 2), max(plot.height - label.height / 2, label.height / 2)))
        }
        if tip.x + radius + labelGap + label.width <= plot.width {
            return clamped(CGPoint(x: tip.x + radius + labelGap + label.width / 2, y: tip.y))
        }
        let x = tip.x + radius - label.width / 2
        let above = clamped(CGPoint(x: x, y: tip.y - radius - labelGap - label.height / 2))
        let below = clamped(CGPoint(x: x, y: tip.y + radius + labelGap + label.height / 2))
        let (preferred, other) = tip.y > plot.height / 2 ? (above, below) : (below, above)
        guard let from, covers(preferred, label: label, from: from, to: tip),
              !covers(other, label: label, from: from, to: tip) else { return preferred }
        return other
    }

    /// Whether a label centred at `center` lies over the segment `from`→`to`.
    static func covers(_ center: CGPoint, label: CGSize, from: CGPoint, to: CGPoint) -> Bool {
        let rect = CGRect(x: center.x - label.width / 2, y: center.y - label.height / 2,
                          width: label.width, height: label.height)
        let steps = 24
        return (0...steps).contains { i in
            let t = CGFloat(i) / CGFloat(steps)
            return rect.contains(CGPoint(x: from.x + (to.x - from.x) * t, y: from.y + (to.y - from.y) * t))
        }
    }
}

/// The tail the marker last drew, and whether moving to the current one
/// glides. The marker advances it while it draws, so it never waits on a
/// change callback. SwiftUI skips `onChange` actions beyond one per frame, and
/// a skipped callback once left the dot on the vertex before the line's end
/// (#10090). This is a plain reference, so advancing it invalidates nothing.
/// It decides only the motion: the drawn tip is always the current tail's end.
final class LiveEdgeGlideMemory {
    private var tail: LiveEdgeTail?
    private var glides = false

    /// Same tail again (a redraw): the same answer. A tail drawn for the first
    /// time is compared with the one drawn before it, whatever changes in
    /// between were coalesced away.
    func glides(to new: LiveEdgeTail, reduceMotion: Bool, sceneActive: Bool) -> Bool {
        guard new != tail else { return glides }
        glides = tail.map {
            LiveChartEdgeMarkerPlan.glides(from: $0, to: new, reduceMotion: reduceMotion, sceneActive: sceneActive)
        } ?? false
        tail = new
        return glides
    }
}

// MARK: - Changed-digit text

/// A printed accepted value whose CHANGED characters roll, the rest held
/// still: 60.4% -> 60.7% moves only the tenths digit. A rise rolls up, a fall
/// rolls down; nil (direction unknown) rolls up.
///
/// Alex, 2026-10-31: the decimal shows the number is alive, but sliding the
/// whole figure on every tenth made it hard to read. This replaces the
/// whole-string slide (which existed so no mix of old and new digits could
/// show mid-move): only the digits that changed are in motion, for
/// `LiveChartEdgeMarkerPlan.glideDuration`.
///
/// A modifier on the caller's own `Text`; `value` must be the string that
/// `Text` prints. SwiftUI's numeric content transition compares the old and
/// new glyphs itself, so kerning, fonts and width stay the caller's.
///
/// Rolls only in an active scene with motion allowed and `animates` true;
/// otherwise the new value is drawn at once.
extension View {
    func acceptedValueChange(_ value: String, rising: Bool? = nil, animates: Bool = true) -> some View {
        modifier(AcceptedValueChange(value: value, rising: rising, animates: animates))
    }
}

private struct AcceptedValueChange: ViewModifier {
    let value: String
    let rising: Bool?
    let animates: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.scenePhase) private var scenePhase

    private var rolls: Bool { animates && !reduceMotion && scenePhase == .active }

    func body(content: Content) -> some View {
        content
            .contentTransition(rolls ? .numericText(countsDown: rising == false) : .identity)
            .animation(rolls ? .easeOut(duration: LiveChartEdgeMarkerPlan.glideDuration) : nil, value: value)
    }
}

// MARK: - The marker

private struct LiveEdgeLabelSizeKey: PreferenceKey {
    static let defaultValue = CGSize.zero
    static func reduce(value: inout CGSize, nextValue: () -> CGSize) {
        let next = nextValue()
        if next != .zero { value = next }
    }
}

/// The last segment of the primary line, the dot at its end and the current
/// number beside it (#9436).
///
/// The plot stops one vertex short and this leaf draws the rest, so the dot IS
/// the drawn end of the line in every frame — including while it glides, when
/// the segment grows with it along the straight join the chart would have
/// drawn anyway. The glide is interpolated in DATA space and projected through
/// the proxy each frame: O(1), and it cannot come loose if the axis moves in
/// the same update. The plot itself is never animated.
///
/// Observes only the selection, so a scrub hides the dot and number without
/// rebuilding the plot; the segment stays, because it is part of the line.
/// A scene that is not active hides them the same way, and it or Reduce
/// Motion turning on mid-glide cancels the glide: the segment is drawn to the
/// settled tip at once.
///
/// The tip handed to the layer is always the tail's own end. A glide is that
/// same change, animated (`LiveEdgeGlideMemory`), so no callback has to arrive
/// for the line to reach its newest vertex.
struct LiveChartEdgeMarker: View {
    @ObservedObject var selection: OddsChartSelection
    let proxy: ChartProxy
    let plotFrame: CGRect
    let tail: LiveEdgeTail
    let label: String
    var rising: Bool?
    let lineColor: Color
    let lineStyle: StrokeStyle
    let activity: LivePriceActivity?
    let pulseColor: Color
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.scenePhase) private var scenePhase
    @State private var memory = LiveEdgeGlideMemory()
    @State private var labelSize = CGSize(width: 64, height: 20)
    /// Bumped to cancel an in-flight glide (see `AcceptedValueChange.epoch`).
    @State private var epoch = 0

    var body: some View {
        let glides = memory.glides(to: tail, reduceMotion: reduceMotion, sceneActive: scenePhase == .active)
        LiveEdgeTipLayer(
            tipTime: tail.to.date.timeIntervalSinceReferenceDate,
            tipProbability: tail.to.probability,
            from: tail.from, proxy: proxy, plotFrame: plotFrame,
            label: label, rising: rising, labelSize: labelSize,
            showsMarker: selection.date == nil && scenePhase == .active,
            lineColor: lineColor, lineStyle: lineStyle,
            selection: selection, activity: activity, target: tail.to, pulseColor: pulseColor)
        // A glide animates the layer's tip from where it was drawn. A snap
        // takes no animation, even inside someone else's.
        .animation(glides ? .easeOut(duration: LiveChartEdgeMarkerPlan.glideDuration) : nil, value: tail.to)
        .id(epoch)
        .onPreferenceChange(LiveEdgeLabelSizeKey.self) { size in
            if size != .zero { labelSize = size }
        }
        .onChange(of: scenePhase) { _, phase in
            if phase != .active { cancelGlide() }
        }
        .onChange(of: reduceMotion) { _, on in
            if on { cancelGlide() }
        }
        .allowsHitTesting(false)
    }

    private func cancelGlide() {
        var snap = Transaction()
        snap.disablesAnimations = true
        withTransaction(snap) { epoch += 1 }
    }
}

private struct LiveEdgeTipLayer: View, Animatable {
    var tipTime: TimeInterval
    var tipProbability: Double
    let from: LiveEdgeVertex?
    let proxy: ChartProxy
    let plotFrame: CGRect
    let label: String
    let rising: Bool?
    let labelSize: CGSize
    let showsMarker: Bool
    let lineColor: Color
    let lineStyle: StrokeStyle
    @ObservedObject var selection: OddsChartSelection
    let activity: LivePriceActivity?
    let target: LiveEdgeVertex
    let pulseColor: Color

    var animatableData: AnimatablePair<Double, Double> {
        get { AnimatablePair(tipTime, tipProbability) }
        set { tipTime = newValue.first; tipProbability = newValue.second }
    }

    private func point(_ date: Date, _ probability: Double) -> CGPoint? {
        guard let x = proxy.position(forX: date), let y = proxy.position(forY: probability) else { return nil }
        return CGPoint(x: plotFrame.minX + x, y: plotFrame.minY + y)
    }

    /// The segment's start in plot-local points, for label placement.
    private func start(in plot: CGRect) -> CGPoint? {
        from.flatMap { point($0.date, $0.probability) }.map { CGPoint(x: $0.x - plot.minX, y: $0.y - plot.minY) }
    }

    var body: some View {
        ZStack(alignment: .topLeading) {
            Color.clear
            if let tip = point(Date(timeIntervalSinceReferenceDate: tipTime), tipProbability) {
                if let from, let start = point(from.date, from.probability) {
                    Path { path in
                        path.move(to: start)
                        path.addLine(to: tip)
                    }
                    // Round caps close the notch where this segment meets the
                    // plot's own line end at an angle.
                    .stroke(lineColor, style: StrokeStyle(lineWidth: lineStyle.lineWidth, lineCap: .round,
                                                          lineJoin: .round, dash: lineStyle.dash))
                }
                if showsMarker {
                    // The existing one-shot ring, on the settled target only.
                    LiveChartEndpointFeedback(selection: selection, activity: activity,
                                              probability: target.probability, isLive: true,
                                              color: pulseColor)
                        .position(tip)
                    Circle()
                        .fill(lineColor)
                        .overlay(Circle().stroke(Color.systemBackground, lineWidth: 1.5))
                        .frame(width: LiveChartEdgeMarkerPlan.dotDiameter,
                               height: LiveChartEdgeMarkerPlan.dotDiameter)
                        .position(tip)
                    let local = CGPoint(x: tip.x - plotFrame.minX, y: tip.y - plotFrame.minY)
                    let fromLocal = start(in: plotFrame)
                    let center = LiveChartEdgeMarkerPlan.labelCenter(tip: local, from: fromLocal,
                                                                    label: labelSize, plot: plotFrame.size)
                    Text(label)
                        .acceptedValueChange(label, rising: rising)
                        .font(.system(size: 13, weight: .heavy, design: .rounded).monospacedDigit())
                        .dynamicTypeSize(...DynamicTypeSize.xxLarge)
                        .foregroundStyle(lineColor)
                        .lineLimit(1)
                        .fixedSize()
                        .padding(.horizontal, 3)
                        .background(Color.systemBackground.opacity(0.85),
                                    in: RoundedRectangle(cornerRadius: 4, style: .continuous))
                        .background(GeometryReader { geo in
                            Color.clear.preference(key: LiveEdgeLabelSizeKey.self, value: geo.size)
                        })
                        .position(x: plotFrame.minX + center.x, y: plotFrame.minY + center.y)
                }
            }
        }
        // A new target arrives in the glide's own transaction (`.animation` on
        // this layer). Only the tip interpolates, in data space. Everything
        // drawn from it, the new axis, string and colour takes this frame's
        // value as-is: animated again they would slide in screen space off the
        // line, and the label would crossfade.
        .animation(nil, value: target)
        .accessibilityHidden(true)
    }
}

// MARK: - #9483 v476 the paired away number

/// #9483 v476 — the away line's current number at its newest vertex, beside the
/// home number `LiveChartEdgeMarker` draws. Observes only the selection, so a
/// scrub hides it without rebuilding the plot (#8651), exactly as the home
/// number hides. It takes the side of its vertex away from the home vertex and
/// draws nothing when that spot would cover either line's newest segment, its
/// own vertex, or the home number; the named keys and the headline remain.
struct PairedAwayEndpointLabel9483: View {
    @ObservedObject var selection: OddsChartSelection
    let proxy: ChartProxy
    let plotFrame: CGRect
    let tip: PairedWinVertex9483
    let from: PairedWinVertex9483?
    let homeTail: LiveEdgeTail
    let text: String
    let color: Color
    @Environment(\.scenePhase) private var scenePhase
    @State private var labelSize = CGSize(width: 64, height: 20)

    private func local(_ date: Date, _ probability: Double) -> CGPoint? {
        guard let x = proxy.position(forX: date), let y = proxy.position(forY: probability) else { return nil }
        return CGPoint(x: x, y: y)
    }

    var body: some View {
        ZStack(alignment: .topLeading) {
            Color.clear
            if selection.date == nil, scenePhase == .active,
               let tipPoint = local(tip.date, tip.probability),
               let homeTip = local(homeTail.to.date, homeTail.to.probability),
               let center = Self.placement(
                   tip: tipPoint, from: from.flatMap { local($0.date, $0.probability) },
                   homeTip: homeTip,
                   homeFrom: homeTail.from.flatMap { local($0.date, $0.probability) },
                   label: labelSize, plot: plotFrame.size) {
                Text(text)
                    .font(.system(size: 13, weight: .heavy, design: .rounded).monospacedDigit())
                    .dynamicTypeSize(...DynamicTypeSize.xxLarge)
                    .foregroundStyle(color)
                    .lineLimit(1)
                    .fixedSize()
                    .padding(.horizontal, 3)
                    .background(Color.systemBackground.opacity(0.85),
                                in: RoundedRectangle(cornerRadius: 4, style: .continuous))
                    .onGeometryChange(for: CGSize.self) { $0.size } action: { size in
                        if size != .zero, size != labelSize { labelSize = size }
                    }
                    .position(x: plotFrame.minX + center.x, y: plotFrame.minY + center.y)
            }
        }
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }

    /// The label's centre in plot-local points, or nil where no truthful spot
    /// exists. The home number's box is estimated at this label's size (same
    /// font, same "ABC 00%" shape) and placed by the marker's own rule.
    static func placement(tip: CGPoint, from: CGPoint?, homeTip: CGPoint, homeFrom: CGPoint?,
                          label: CGSize, plot: CGSize) -> CGPoint? {
        guard tip.x >= 0, tip.x <= plot.width, tip.y >= 0, tip.y <= plot.height,
              abs(tip.y - homeTip.y) >= 44 else { return nil }
        let radius = LiveChartEdgeMarkerPlan.dotDiameter / 2
        let gap = LiveChartEdgeMarkerPlan.labelGap
        let outward: CGFloat = tip.y > homeTip.y ? 1 : -1
        let raw = CGPoint(x: tip.x + radius - label.width / 2,
                          y: tip.y + outward * (radius + gap + label.height / 2))
        let center = CGPoint(
            x: min(max(raw.x, label.width / 2), max(plot.width - label.width / 2, label.width / 2)),
            y: min(max(raw.y, label.height / 2), max(plot.height - label.height / 2, label.height / 2)))
        let box = CGRect(x: center.x - label.width / 2, y: center.y - label.height / 2,
                         width: label.width, height: label.height)
        if box.insetBy(dx: -radius, dy: -radius).contains(tip) { return nil }
        if let from, LiveChartEdgeMarkerPlan.covers(center, label: label, from: from, to: tip) { return nil }
        if let homeFrom, LiveChartEdgeMarkerPlan.covers(center, label: label, from: homeFrom, to: homeTip) { return nil }
        let homeCenter = LiveChartEdgeMarkerPlan.labelCenter(tip: homeTip, from: homeFrom, label: label, plot: plot)
        let homeBox = CGRect(x: homeCenter.x - label.width / 2, y: homeCenter.y - label.height / 2,
                             width: label.width, height: label.height)
        if box.insetBy(dx: -2, dy: -2).intersects(homeBox) { return nil }
        return center
    }
}
