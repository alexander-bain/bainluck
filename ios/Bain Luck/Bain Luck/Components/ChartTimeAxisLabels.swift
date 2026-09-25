import SwiftUI
import Charts

/// The time labels under both stacked event-page charts, drawn by us rather
/// than by the chart framework (#8481, #1833).
///
/// The framework's label placement changed under us: on iOS 27 an
/// `AxisValueLabel(anchor: .top)` no longer centres on its tick but hangs to the
/// right of it, while `.topTrailing` still hangs left — so the end-label rule
/// (#3237) turned the last pair into `3:35 PM3:45 PM` on Alex's phone, on BOTH
/// charts, with no change to our code. No `AxisValueLabel` parameter centres on
/// both OS versions (probed: `anchor` `.top`, `centered` true/false, both,
/// neither), so a label whose position is the reader's only way to read the
/// time cannot be left to it.
///
/// So the framework keeps an INVISIBLE label per tick (`reservedRow`), which
/// holds the row's height and keeps VoiceOver's axis, and this view draws the
/// visible one at `OddsChartView.xAxisLabelCenters` — centred on its tick,
/// clamped inside the plot. The period chips have been placed the same way, in
/// the same overlay, since #3237.
struct ChartTimeAxisLabels: View {
    let ticks: [Date]
    let plan: OddsChartView.XAxisPlan
    let proxy: ChartProxy
    let plotFrame: CGRect

    /// From the plot's bottom edge to a label's vertical centre: the
    /// framework's own offset for a 9pt bottom-axis label, measured off its
    /// render, so the drawn label sits where the reserved one does.
    static let labelCenterOffset: CGFloat = 9.5

    /// The framework's label, kept for its height and its accessibility, never
    /// for its ink.
    static func reservedRow(format: Date.FormatStyle) -> some AxisMark {
        AxisValueLabel(format: format, anchor: .topTrailing)
            .font(.system(size: 9))
            .foregroundStyle(Color.clear)
    }

    var body: some View {
        let placed: [(tick: Date, x: CGFloat)] = ticks.compactMap { tick in
            proxy.position(forX: tick).map { (tick, $0) }
        }
        let centers = OddsChartView.xAxisLabelCenters(
            tickPositions: placed.map(\.x),
            plotWidth: plotFrame.width,
            labelWidth: OddsChartView.xAxisLabelWidth(for: plan.labelStyle))
        ForEach(Array(placed.enumerated()), id: \.offset) { index, item in
            Text(item.tick, format: plan.format)
                .font(.system(size: 9))
                .foregroundStyle(.secondary)
                .lineLimit(1)
                .fixedSize()
                .position(x: plotFrame.minX + centers[index],
                          y: plotFrame.maxY + Self.labelCenterOffset)
                .accessibilityHidden(true)
        }
    }
}
