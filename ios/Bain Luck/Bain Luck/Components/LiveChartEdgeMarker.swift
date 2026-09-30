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

    /// The tip actually drawn this frame: the held one while it belongs to the
    /// new segment — one of its ends, or the replaced pin hanging off the same
    /// predecessor (`shownFrom`) — otherwise the target. The overlay always
    /// draws from `tail.from` to this tip, so it is never detached.
    static func drawnTip(shown: LiveEdgeVertex?, shownFrom: LiveEdgeVertex? = nil,
                         tail: LiveEdgeTail) -> LiveEdgeVertex {
        guard let shown else { return tail.to }
        if shown == tail.to || shown == tail.from { return shown }
        if let from = tail.from, shownFrom == from, shown.date >= from.date { return shown }
        return tail.to
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

// MARK: - Whole-value text

/// A printed accepted value that changes as a WHOLE string: the old one
/// leaves, the new one arrives, each complete. No per-digit roll and no
/// crossfade in place, either of which can put a mix of the two on screen —
/// a third number nobody quoted. A rise slides up, a fall slides down; nil
/// (direction unknown) slides up.
///
/// A modifier on the caller's own `Text`, so the text and its fonts stay
/// where they were; `value` must be the string that `Text` prints. The
/// leaving copy inherits the same environment (font, colour) from outside.
///
/// Both strings are moved by this modifier's own state, not by an insertion /
/// removal transition: SwiftUI plays a removed view's transition as it was
/// captured BEFORE the change, so the leaving string would slide the way the
/// previous update went while the arriving one slid this way.
///
/// Slides only in an active scene with motion allowed and `animates` true. If
/// any of those turns off mid-slide the slide is CANCELLED, not left to run:
/// the leaving string goes and the arriving one is drawn settled.
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
    @State private var outgoing: String?
    @State private var progress: CGFloat = 1
    /// −1 moves up (a rise), +1 moves down (a fall).
    @State private var direction: CGFloat = -1
    /// Which change a finishing slide belongs to, so the first of two quick
    /// updates cannot clear the second's leaving string.
    @State private var generation = 0
    /// Bumped to cancel: a new identity drops the in-flight interpolation,
    /// which re-setting `progress` to the 1 it is already heading for cannot.
    @State private var epoch = 0

    private var slides: Bool { animates && !reduceMotion && scenePhase == .active }

    func body(content: Content) -> some View {
        ZStack {
            if let outgoing {
                Text(outgoing)
                    .modifier(VerticalShift(fraction: direction * progress))
                    .accessibilityHidden(true)
            }
            content
                .modifier(VerticalShift(fraction: -direction * (1 - progress)))
        }
        .clipped()
        .id(epoch)
        .onChange(of: slides) { _, allowed in
            if !allowed { cancel() }
        }
        .onChange(of: value) { old, _ in
            guard slides else {
                cancel()
                return
            }
            var still = Transaction()
            still.disablesAnimations = true
            generation += 1
            let mine = generation
            withTransaction(still) {
                outgoing = old
                direction = LiveChartEdgeMarkerPlan.shiftDirection(rising: rising)
                progress = 0
            }
            // Next turn of the run loop, or SwiftUI coalesces 0 and 1 into
            // the end state and nothing moves.
            DispatchQueue.main.async {
                withAnimation(.easeOut(duration: LiveChartEdgeMarkerPlan.glideDuration)) {
                    progress = 1
                } completion: {
                    if generation == mine { outgoing = nil }
                }
            }
        }
    }

    private func cancel() {
        var still = Transaction()
        still.disablesAnimations = true
        generation += 1
        withTransaction(still) {
            outgoing = nil
            progress = 1
            epoch += 1
        }
    }
}

/// Translate by a fraction of the view's own height — the one number the
/// text knows and its caller does not.
private struct VerticalShift: GeometryEffect {
    var fraction: CGFloat
    var animatableData: CGFloat {
        get { fraction }
        set { fraction = newValue }
    }
    func effectValue(size: CGSize) -> ProjectionTransform {
        ProjectionTransform(CGAffineTransform(translationX: 0, y: fraction * size.height))
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
    @State private var shownTip: LiveEdgeVertex?
    /// The `from` of the tail `shownTip` was set on — lets a replaced pin keep
    /// being drawn off the same predecessor until its glide starts.
    @State private var shownFrom: LiveEdgeVertex?
    @State private var labelSize = CGSize(width: 64, height: 20)
    /// Bumped to cancel an in-flight glide (see `AcceptedValueChange.epoch`).
    @State private var epoch = 0

    var body: some View {
        let tip = LiveChartEdgeMarkerPlan.drawnTip(shown: shownTip, shownFrom: shownFrom, tail: tail)
        LiveEdgeTipLayer(
            tipTime: tip.date.timeIntervalSinceReferenceDate,
            tipProbability: tip.probability,
            from: tail.from, proxy: proxy, plotFrame: plotFrame,
            label: label, rising: rising, labelSize: labelSize,
            showsMarker: selection.date == nil && scenePhase == .active,
            lineColor: lineColor, lineStyle: lineStyle,
            selection: selection, activity: activity, target: tail.to, pulseColor: pulseColor)
        .id(epoch)
        .onPreferenceChange(LiveEdgeLabelSizeKey.self) { size in
            if size != .zero { labelSize = size }
        }
        .onAppear { shownTip = tail.to; shownFrom = tail.from }
        .onChange(of: tail) { old, new in
            if LiveChartEdgeMarkerPlan.glides(from: old, to: new, reduceMotion: reduceMotion,
                                              sceneActive: scenePhase == .active) {
                shownFrom = new.from
                withAnimation(.easeOut(duration: LiveChartEdgeMarkerPlan.glideDuration)) {
                    shownTip = new.to
                }
            } else {
                settle(cancelling: false)
            }
        }
        .onChange(of: scenePhase) { _, phase in
            if phase != .active { settle(cancelling: true) }
        }
        .onChange(of: reduceMotion) { _, on in
            if on { settle(cancelling: true) }
        }
        .allowsHitTesting(false)
    }

    private func settle(cancelling: Bool) {
        var snap = Transaction()
        snap.disablesAnimations = true
        withTransaction(snap) {
            shownTip = tail.to
            shownFrom = tail.from
            if cancelling { epoch += 1 }
        }
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
        .accessibilityHidden(true)
    }
}
