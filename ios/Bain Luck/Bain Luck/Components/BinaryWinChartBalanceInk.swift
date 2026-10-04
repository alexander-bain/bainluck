import SwiftUI

// MARK: - Binary win chart balance ink (#10456)
//
// The v24 two-team win chart: one path, read straight up the existing 0–100
// axis, clipped at the 50% line — above it the line and its fill take the
// home team's color, below it the away team's. Beside it, both teams' accepted
// values, side by side.
//
// This file only PRESENTS what the caller already holds. The caller (Native's
// `OddsChartView` mount) supplies:
//   - an explicit admission: only a question the caller has established is a
//     genuine two-outcome game may wear the ink. A draw-priced, multi-contender
//     or threshold question is refused by the caller, never inferred here.
//   - the displayed path segments, one array per observed run, exactly as the
//     chart already draws them as solid known evidence (`observationSegments` /
//     the live-edge split), and an attestation that the caller joins those
//     vertices with straight lines (`.interpolationMethod(.linear)`). A
//     projector maps coordinates; it cannot reproduce a step or a curve, so any
//     other interpolation is refused. A trailing interval the caller styles as
//     unsupported (the live edge) stays the caller's to draw — it is not passed
//     here, so solid ink never extends across it.
//   - the accepted home AND away values for the moment being read (the
//     scrubbed point or the resting one — selection stays the caller's).
//
// Nothing here makes a quote: no new vertices, no smoothing, no interpolated
// crossing point, no bridge between runs, no source selection, no axis change,
// and never `1 − home` for the away side (#5271's class). A plan that cannot
// be honest is `nil`, and the caller keeps today's line exactly.

/// Whether the caller has established the question as a genuine two-outcome
/// game. Supplied, never derived from a sport key or a price here.
enum BinaryWinBalanceAdmission: Equatable {
    case admittedBinary
    case refused
}

/// How the caller joins the vertices it displays. Attested by the caller, never
/// guessed from the vertices: two points say nothing about the line between them.
enum BinaryWinPathInterpolation: Equatable {
    /// Straight segments between observed vertices — the existing primary
    /// `LineMark`'s `.interpolationMethod(.linear)`.
    case linear
    /// Step, curve, or anything the caller cannot attest as linear.
    case nonLinearOrUnknown
}

/// One vertex of the displayed path: the home win probability (0.0–1.0) at a
/// time, verbatim from the point the chart draws.
struct BinaryWinPathVertex: Equatable {
    let date: Date
    let probability: Double
}

extension BinaryWinPathVertex {
    /// The chart's own point, copied — the date and the plotted value, nothing
    /// re-read or re-derived.
    init(_ point: ChartDataPoint) {
        self.init(date: point.date, probability: point.probability)
    }
}

/// What the ink may draw and print, once every input has been checked.
struct BinaryWinBalancePlan: Equatable {
    /// The supplied runs, unchanged and in order.
    let segments: [[BinaryWinPathVertex]]
    /// The supplied values, unchanged.
    let home: Double
    let away: Double
    /// Both values as the game card prints them (`GamePlayCardView.printedLabels`).
    let homeText: String
    let awayText: String
}

enum BinaryWinChartBalanceInk {

    /// v24 `.balance-line { stroke-width: 2.6; stroke-linejoin: round; stroke-linecap: round }`.
    static let lineWidth: CGFloat = 2.6
    /// v24 `.balance-fill` — the team color at ~0x18/0xFF alpha.
    static let fillOpacity: Double = 0.1
    /// The even line, on the chart's 0.0–1.0 home-probability scale.
    static let even: Double = 0.5

    /// The plan the ink draws from, or `nil` to refuse — the caller then keeps
    /// its existing line and readout untouched.
    ///
    /// Refuses when the caller did not admit a binary question; when the caller
    /// cannot attest its displayed path is linear (this ink redraws it with
    /// straight segments, so any other path would be a different path); when either
    /// value is missing, non-finite or off the 0–1 scale (an absent away price
    /// is a refusal, never `1 − home`); when there is no vertex to draw; or when
    /// any vertex is non-finite or off the scale (dropping it would redraw the
    /// path the caller drew, so the whole plan stands down instead).
    static func plan(
        admission: BinaryWinBalanceAdmission,
        segments: [[BinaryWinPathVertex]],
        interpolation: BinaryWinPathInterpolation,
        home: Double?,
        away: Double?,
        gameFinished: Bool = false
    ) -> BinaryWinBalancePlan? {
        guard admission == .admittedBinary else { return nil }
        guard interpolation == .linear else { return nil }
        guard let home, let away, isProbability(home), isProbability(away) else { return nil }
        let runs = segments.filter { !$0.isEmpty }
        guard !runs.isEmpty else { return nil }
        guard runs.allSatisfy({ $0.allSatisfy { isProbability($0.probability) } }) else { return nil }
        let printed = GamePlayCardView.printedLabels(home: home, away: away, gameFinished: gameFinished)
        guard let awayText = printed.away else { return nil }
        return BinaryWinBalancePlan(segments: runs, home: home, away: away,
                                    homeText: printed.home, awayText: awayText)
    }

    /// A projector for a plot laid out linearly over `xDomain` × `yDomain`
    /// inside `plotRect` (y grows downward). The caller may pass its own
    /// `ChartProxy`-backed projector instead; this one matches the chart's
    /// `chartYScale(domain: 0...1)` and is what the pure tests use.
    static func linearProjector(
        xDomain: ClosedRange<Date>,
        yDomain: ClosedRange<Double> = 0...1,
        plotRect: CGRect
    ) -> (Date, Double) -> CGPoint? {
        let span = xDomain.upperBound.timeIntervalSince(xDomain.lowerBound)
        let ySpan = yDomain.upperBound - yDomain.lowerBound
        return { date, value in
            guard span > 0, ySpan > 0 else { return nil }
            let fx = date.timeIntervalSince(xDomain.lowerBound) / span
            let fy = (value - yDomain.lowerBound) / ySpan
            return CGPoint(x: plotRect.minX + CGFloat(fx) * plotRect.width,
                           y: plotRect.maxY - CGFloat(fy) * plotRect.height)
        }
    }

    private static func isProbability(_ value: Double) -> Bool {
        value.isFinite && value >= 0 && value <= 1
    }
}

// MARK: - Geometry

/// The plan projected onto the plot: the same runs as points, and where the
/// even line falls. Pure, so the drawing rules are testable without a render.
struct BinaryWinBalanceGeometry: Equatable {
    /// One array of projected vertices per supplied run, in order.
    let runs: [[CGPoint]]
    /// The projected y of 50%.
    let evenY: CGFloat
    /// Whether each single-vertex run sits on the home side (v24's tip rule:
    /// `home >= 50` is the home side), parallel to `singletons`.
    let singletonIsHomeSide: [Bool]

    /// `nil` when the projector cannot place a vertex or the even line — the
    /// ink then draws nothing rather than a partial path.
    init?(plan: BinaryWinBalancePlan, project: (Date, Double) -> CGPoint?) {
        guard let anchor = plan.segments.first?.first,
              let even = project(anchor.date, BinaryWinChartBalanceInk.even) else { return nil }
        var runs: [[CGPoint]] = []
        var sides: [Bool] = []
        for segment in plan.segments {
            var run: [CGPoint] = []
            for vertex in segment {
                guard let point = project(vertex.date, vertex.probability) else { return nil }
                run.append(point)
            }
            runs.append(run)
            if segment.count == 1 { sides.append(segment[0].probability >= BinaryWinChartBalanceInk.even) }
        }
        self.runs = runs
        self.evenY = even.y
        self.singletonIsHomeSide = sides
    }

    /// Runs of two or more vertices — the ones a line can join.
    var lineRuns: [[CGPoint]] { runs.filter { $0.count >= 2 } }

    /// A lone observation no line can draw; it stays visible as a dot.
    var singletons: [CGPoint] { runs.filter { $0.count == 1 }.map { $0[0] } }

    /// One closed polygon per line run, v24's `points="x0,50 … xN,50"`: down to
    /// the even line at the run's OWN first x, along its vertices, back to the
    /// even line at its OWN last x. Never joined to a neighbouring run.
    var fillPolygons: [[CGPoint]] {
        lineRuns.map { run in
            [CGPoint(x: run[0].x, y: evenY)] + run + [CGPoint(x: run[run.count - 1].x, y: evenY)]
        }
    }

    /// Everything above the even line, widened by `pad` so a stroke at 100%
    /// keeps its full width.
    func homeClip(in bounds: CGRect, pad: CGFloat) -> CGRect {
        CGRect(x: bounds.minX - pad, y: bounds.minY - pad,
               width: bounds.width + 2 * pad, height: max(0, evenY - bounds.minY + pad))
    }

    /// Everything at and below the even line, widened by `pad`.
    func awayClip(in bounds: CGRect, pad: CGFloat) -> CGRect {
        CGRect(x: bounds.minX - pad, y: evenY,
               width: bounds.width + 2 * pad, height: max(0, bounds.maxY - evenY + pad))
    }

    var linePath: Path {
        var path = Path()
        for run in lineRuns { path.addLines(run) }
        return path
    }

    var fillPath: Path {
        var path = Path()
        for polygon in fillPolygons {
            path.addLines(polygon)
            path.closeSubpath()
        }
        return path
    }
}

// MARK: - Views

/// The balance ink itself. Mount it over the chart's plot frame (e.g. inside
/// `.chartOverlay`) with a projector in the same coordinate space and the same
/// domains as the chart, and hide ONLY the primary line it replaces — the runs
/// and lone dots passed in the plan. Source comparisons, markers, the live
/// edge and anything not passed here stay the caller's. Decorative to VoiceOver: the chart's own
/// accessibility value carries the reading. No animation.
struct BinaryWinChartBalanceInkLayer: View {
    let plan: BinaryWinBalancePlan
    let project: (Date, Double) -> CGPoint?
    let homeColor: Color
    let awayColor: Color

    var body: some View {
        Canvas { context, size in
            guard let geometry = BinaryWinBalanceGeometry(plan: plan, project: project) else { return }
            let bounds = CGRect(origin: .zero, size: size)
            let pad = BinaryWinChartBalanceInk.lineWidth
            let stroke = StrokeStyle(lineWidth: BinaryWinChartBalanceInk.lineWidth,
                                     lineCap: .round, lineJoin: .round)
            let halves = [(geometry.homeClip(in: bounds, pad: pad), homeColor),
                          (geometry.awayClip(in: bounds, pad: pad), awayColor)]
            for (clip, color) in halves {
                context.drawLayer { half in
                    half.clip(to: Path(clip))
                    half.fill(geometry.fillPath,
                              with: .color(color.opacity(BinaryWinChartBalanceInk.fillOpacity)))
                    half.stroke(geometry.linePath, with: .color(color), style: stroke)
                }
            }
            let d = BinaryWinChartBalanceInk.lineWidth * 2
            for (point, isHome) in zip(geometry.singletons, geometry.singletonIsHomeSide) {
                let dot = Path(ellipseIn: CGRect(x: point.x - d / 2, y: point.y - d / 2, width: d, height: d))
                context.fill(dot, with: .color(isHome ? homeColor : awayColor))
            }
        }
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}

/// Both teams' accepted values, v24's two-team key: a color swatch, the team,
/// the value. Side by side while it fits; stacked once Dynamic Type (or a
/// narrow width) needs the room. Never truncates a value.
struct BinaryWinPairedReadout: View {
    let plan: BinaryWinBalancePlan
    let homeLabel: String
    let awayLabel: String
    let homeColor: Color
    let awayColor: Color

    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    var body: some View {
        Group {
            if dynamicTypeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 4) { entries }
            } else {
                ViewThatFits(in: .horizontal) {
                    HStack(spacing: 16) { entries }
                    VStack(alignment: .leading, spacing: 4) { entries }
                }
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(Text(Self.spokenPair(plan: plan, homeLabel: homeLabel, awayLabel: awayLabel)))
    }

    @ViewBuilder private var entries: some View {
        entry(label: homeLabel, value: plan.homeText, color: homeColor)
        entry(label: awayLabel, value: plan.awayText, color: awayColor)
    }

    private func entry(label: String, value: String, color: Color) -> some View {
        HStack(alignment: .center, spacing: 6) {
            Circle()
                .fill(color)
                .frame(width: 7, height: 7)
            Text(label)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondary)
            Text(value)
                .font(.headline)
                .monospacedDigit()
                .foregroundStyle(DS.textPrimary)
        }
        .fixedSize(horizontal: false, vertical: true)
    }

    /// Home first, as the line reads top-down: "NYY 62%, BOS 38%".
    static func spokenPair(plan: BinaryWinBalancePlan, homeLabel: String, awayLabel: String) -> String {
        "\(homeLabel) \(plan.homeText), \(awayLabel) \(plan.awayText)"
    }
}
