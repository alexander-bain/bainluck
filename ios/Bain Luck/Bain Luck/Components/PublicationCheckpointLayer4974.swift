import SwiftUI
import Charts

/// #4974 — what the iPhone chart draws for a finished game whose recorded
/// checkpoints were adopted (`PublicationJourney4974.adopt`).
///
/// Three kinds of element and nothing else:
///
/// 1. **Checkpoint dots** — one per stored vertex, at `(date, vertex.p)`, id =
///    `rev`. `p` is the server's HOME probability verbatim: no complement, no
///    rounding, no normalization. Two revisions at one instant are two dots.
/// 2. **Legacy lines** — the caller's existing aggregate observation runs, with
///    every point inside the CLOSED recorded window removed and every remaining
///    connection that `Journey.permitsLegacySegment` refuses cut. A surviving
///    point is the caller's own object (same id, date, probability, source),
///    in the caller's order.
/// 3. **Legacy dots** — a surviving run of one real reading, which no
///    `LineMark` can draw. A synthetic live edge left alone is not a reading
///    and is dropped (`ChartDataPoint.isLiveEdge`).
///
/// ## What this never draws
///
/// Nothing connects two checkpoints — no line, step or area — because nothing
/// proves two recorded rows were adjacent (`PublicationJourney4974`'s header).
/// Nothing is drawn at the window's edges that was not served: a cut leaves the
/// gap empty. Two incoming runs are never joined, even when they meet.
///
/// The plan takes no visible domain on purpose. The window applies whether or
/// not the parent's x domain shows any checkpoint, so a clipped dot can never
/// re-admit a legacy segment across the recorded interval.
///
/// The parent chart owns axes, domain, scale, selection, period/source/score/
/// settlement markers, and whether this layer is mounted at all; the plan does
/// not compute observation runs, cadence, status or source eligibility.
struct PublicationCheckpointRenderPlan4974 {
    /// A retained legacy run of two or more points, drawn as one series.
    struct LegacyLine: Identifiable {
        /// The series value: unique per incoming run AND per output part, and
        /// prefixed so it cannot collide with another layer's series.
        let id: String
        let points: [ChartDataPoint]
    }

    /// A retained legacy run of exactly one real reading.
    struct LegacyDot: Identifiable {
        let id: String
        let point: ChartDataPoint
    }

    /// One stored vertex. `id` is its `rev`.
    struct CheckpointDot: Identifiable {
        let id: Int64
        let date: Date
        let probability: Double
    }

    /// Prefix of every legacy series value this layer emits.
    static let seriesPrefix = "publication-checkpoint-4974-legacy"

    let lines: [LegacyLine]
    let dots: [LegacyDot]
    let checkpoints: [CheckpointDot]

    /// `observationRuns` are the caller's ALREADY computed aggregate runs
    /// (`OddsChartView.observationSegments`), never raw history.
    init(journey: PublicationJourney4974.Journey, observationRuns: [[ChartDataPoint]]) {
        var lines: [LegacyLine] = []
        var dots: [LegacyDot] = []
        for (runIndex, run) in observationRuns.enumerated() {
            // Filter BEFORE partitioning: `legacyRuns` alone keeps every point,
            // including those inside the window.
            let outside = run.filter { !journey.contains($0.date) }
            let parts = journey.legacyRuns(outside, date: \.date)
            for (partIndex, part) in parts.enumerated() {
                let id = "\(Self.seriesPrefix)#\(runIndex).\(partIndex)"
                if part.count >= 2 {
                    lines.append(LegacyLine(id: id, points: part))
                } else if let only = part.first, !only.isLiveEdge {
                    dots.append(LegacyDot(id: id, point: only))
                }
            }
        }
        self.lines = lines
        self.dots = dots
        self.checkpoints = journey.checkpoints.map {
            CheckpointDot(id: $0.vertex.rev, date: $0.date, probability: $0.vertex.p)
        }
    }
}

/// The plan's marks, in the caller's blend color and stroke. Mounted inside the
/// parent `Chart`; it renders no chart, axis, legend or caption of its own.
struct PublicationCheckpointLayer4974: ChartContent {
    let plan: PublicationCheckpointRenderPlan4974
    let color: Color
    let stroke: StrokeStyle

    /// An AREA in square points — the chart's existing lone-observation dot.
    static let symbolArea: CGFloat = 18

    var body: some ChartContent {
        ForEach(plan.lines) { line in
            ForEach(line.points) { point in
                LineMark(
                    x: .value("Time", point.date),
                    y: .value("Win probability", point.probability),
                    series: .value("Source", line.id)
                )
                .foregroundStyle(color)
                .lineStyle(stroke)
                .interpolationMethod(.linear)
            }
        }

        ForEach(plan.dots) { dot in
            PointMark(
                x: .value("Time", dot.point.date),
                y: .value("Win probability", dot.point.probability)
            )
            .foregroundStyle(color)
            .symbolSize(Self.symbolArea)
        }

        // Each checkpoint is its own mark; none shares a series with anything.
        ForEach(plan.checkpoints) { checkpoint in
            PointMark(
                x: .value("Time", checkpoint.date),
                y: .value("Win probability", checkpoint.probability)
            )
            .foregroundStyle(color)
            .symbolSize(Self.symbolArea)
        }
    }
}
