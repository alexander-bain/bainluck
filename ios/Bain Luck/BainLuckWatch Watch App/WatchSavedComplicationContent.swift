import SwiftUI
import WidgetKit

/// Large rectangular (`accessoryRectangular`) selected-game reading for #4933,
/// with honest launcher fallback when no valid shared snapshot exists.
/// Circular and corner families remain explicit launchers.
struct WatchSavedComplicationContent: View {
    let snapshot: WatchComplicationSnapshot?
    var now: Date = Date()
    @Environment(\.widgetRenderingMode) private var renderingMode

    private var accentColor: Color { renderingMode == .fullColor ? .cyan : .primary }

    var body: some View {
        if let snapshot, let reading = snapshot.validatedRectangularReading(now: now) {
            ViewThatFits(in: [.horizontal, .vertical]) {
                readingCard(reading, preferCompact: false)
                readingCard(reading, preferCompact: true)
                wrappingFallbackCard(reading)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(reading.accessibilityDescription(at: now))
            .accessibilityIdentifier("watch.complication.rectangular.reading")
        } else {
            HStack(spacing: 8) {
                Image(systemName: "bookmark").font(.title2)
                VStack(alignment: .leading) {
                    Text("Your game").font(.headline)
                    Text("Open Bain Luck").font(.caption)
                }
            }
            .accessibilityElement(children: .combine)
            .accessibilityLabel("Open your selected game in Bain Luck, or choose a game")
            .accessibilityIdentifier("watch.complication.fallback")
        }
    }

    private func readingCard(_ reading: WatchRectangularReading, preferCompact: Bool) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(reading.headerLine(preferCompact: preferCompact))
                .font(HeadlineStyleTable199.headers(.wristTile, scaledSize: 11))
                .foregroundStyle(.secondary)
                .lineLimit(1)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("watch.complication.rectangular.header")
            Text(reading.primaryLine(preferCompact: preferCompact, at: now))
                .font(HeadlineStyleTable199.secondNumbers(.wristTile, prominent: true, scaledSize: 14))
                .foregroundStyle(
                    (reading.kind == .liveForecast || reading.kind == .scheduledForecast || reading.kind == .futureForecast)
                        ? accentColor : .primary
                )
                .monospacedDigit()
                .lineLimit(preferCompact ? 1 : 2)
                .minimumScaleFactor(0.85)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("watch.complication.rectangular.primary")
            Text(reading.metadataLine(at: now))
                .font(HeadlineStyleTable199.quietText(.wristTile))
                .foregroundStyle(.secondary)
                .lineLimit(1)
                .minimumScaleFactor(0.85)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("watch.complication.rectangular.metadata")
        }
    }

    /// Multi-line fallback when a team lacks a short name so long matchup headers never truncate (#13144).
    /// Inner `ViewThatFits(in: .vertical)` proposes the slot's real width so each tier wraps cleanly
    /// and selects the largest type step whose wrapped height fits inside 41 mm / 45 mm slots.
    private func wrappingFallbackCard(_ reading: WatchRectangularReading) -> some View {
        ViewThatFits(in: .vertical) {
            wrappedReadingCard(reading, headerSize: 10.5, primarySize: 13, metadataSize: 10, spacing: 1.5)
            wrappedReadingCard(reading, headerSize: 9.5, primarySize: 11.5, metadataSize: 9.5, spacing: 1)
            wrappedReadingCard(reading, headerSize: 8.5, primarySize: 10.5, metadataSize: 9, spacing: 1)
            wrappedReadingCard(reading, headerSize: 8, primarySize: 9.5, metadataSize: 8.5, spacing: 0.5)
        }
    }

    private func wrappedReadingCard(
        _ reading: WatchRectangularReading,
        headerSize: CGFloat,
        primarySize: CGFloat,
        metadataSize: CGFloat,
        spacing: CGFloat
    ) -> some View {
        VStack(alignment: .leading, spacing: spacing) {
            Text(reading.headerLine(preferCompact: true).replacingOccurrences(of: " · ", with: "\u{00A0}·\u{00A0}"))
                .font(HeadlineStyleTable199.headers(.wristTile, scaledSize: headerSize))
                .foregroundStyle(.secondary)
                .lineLimit(nil)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("watch.complication.rectangular.header")
            Text(reading.primaryLine(preferCompact: false, at: now))
                .font(HeadlineStyleTable199.secondNumbers(.wristTile, prominent: true, scaledSize: primarySize))
                .foregroundStyle(
                    (reading.kind == .liveForecast || reading.kind == .scheduledForecast || reading.kind == .futureForecast)
                        ? accentColor : .primary
                )
                .monospacedDigit()
                .lineLimit(nil)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("watch.complication.rectangular.primary")
            Text(reading.metadataLine(at: now))
                .font(HeadlineStyleTable199.quietText(.wristTile, scaledSize: metadataSize))
                .foregroundStyle(.secondary)
                .lineLimit(1)
                .minimumScaleFactor(0.8)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("watch.complication.rectangular.metadata")
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct WatchSavedCircularComplicationContent: View {
    let snapshot: WatchComplicationSnapshot?

    var body: some View {
        Image(systemName: "bookmark")
            .font(.system(size: 18))
            .accessibilityLabel("Open your selected game in Bain Luck, or choose a game")
            .accessibilityIdentifier("watch.complication.circular.fallback")
    }
}

struct WatchSavedCornerComplicationContent: View {
    let snapshot: WatchComplicationSnapshot?

    var body: some View {
        Image(systemName: "bookmark")
            .font(.system(size: 18))
            .accessibilityLabel("Open your selected game in Bain Luck, or choose a game")
            .accessibilityIdentifier("watch.complication.corner.fallback")
    }
}
