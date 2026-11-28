import SwiftUI
import WidgetKit

/// Selected-game and saved-market complication views (`#4933`, `#13430`):
/// circular and corner slots follow the iPhone small Lock Screen rules (`LockScreenSmallSlotFit13430`),
/// falling back to the bookmark launcher only when no fresh reading exists.
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
    var now: Date = Date()

    var body: some View {
        if let model = snapshot?.smallSlotModel(now: now) {
            Group {
                if let share = model.gaugeShare, model.isGame {
                    Gauge(value: min(max(share, 0), 1)) {
                        Text(model.subjectLabel)
                            .lineLimit(1)
                            .minimumScaleFactor(0.55)
                    } currentValueLabel: {
                        Text(model.value)
                            .font(.system(size: 14, weight: .bold).monospacedDigit())
                            .lineLimit(1)
                            .minimumScaleFactor(0.5)
                            .padding(.horizontal, 1)
                    }
                    .gaugeStyle(.accessoryCircular)
                    .widgetAccentable()
                } else {
                    ZStack {
                        AccessoryWidgetBackground()
                        VStack(spacing: 0) {
                            Text(model.subjectLabel)
                                .font(.system(size: 9, weight: .semibold))
                                .lineLimit(1)
                                .minimumScaleFactor(0.6)
                            Text(model.value)
                                .font(.system(size: 15, weight: .bold).monospacedDigit())
                                .lineLimit(1)
                                .minimumScaleFactor(0.5)
                                .widgetAccentable()
                        }
                        .padding(4)
                    }
                }
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(model.accessibilityText)
            .accessibilityIdentifier("watch.complication.circular.reading")
        } else {
            ZStack {
                AccessoryWidgetBackground()
                Image(systemName: "bookmark")
                    .font(.system(size: 18))
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("Open your selected game in Bain Luck, or choose a game")
            .accessibilityIdentifier("watch.complication.circular.fallback")
        }
    }
}

struct WatchSavedCornerComplicationContent: View {
    let snapshot: WatchComplicationSnapshot?
    var now: Date = Date()
    @Environment(\.showsWidgetLabel) private var showsWidgetLabel

    var body: some View {
        if let model = snapshot?.smallSlotModel(now: now) {
            Group {
                if showsWidgetLabel {
                    Text(model.value)
                        .font(.system(size: 20, weight: .bold, design: .rounded).monospacedDigit())
                        .minimumScaleFactor(0.55)
                        .lineLimit(1)
                        .widgetCurvesContent()
                        .widgetAccentable()
                        .widgetLabel {
                            Text(model.cornerLabel)
                                .lineLimit(1)
                                .minimumScaleFactor(0.6)
                        }
                } else {
                    VStack(spacing: 0) {
                        Text(model.subjectLabel)
                            .font(.system(size: 8.5, weight: .semibold))
                            .lineLimit(1)
                            .minimumScaleFactor(0.55)
                        Text(model.value)
                            .font(.system(size: 14, weight: .bold, design: .rounded).monospacedDigit())
                            .lineLimit(1)
                            .minimumScaleFactor(0.55)
                            .widgetAccentable()
                    }
                    .padding(2)
                }
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(model.accessibilityText)
            .accessibilityIdentifier("watch.complication.corner.reading")
        } else {
            Image(systemName: "bookmark")
                .font(.system(size: 18))
                .accessibilityLabel("Open your selected game in Bain Luck, or choose a game")
                .accessibilityIdentifier("watch.complication.corner.fallback")
        }
    }
}

/// #13339 — Distinct rectangular slot view when the reader has chosen a game or market
/// that cannot currently appear on the Watch face, so "no game chosen" and "cannot show your game"
/// never look the same.
struct WatchUnavailableComplicationContent13339: View {
    let status: WatchFaceStatusPayload13339
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    var body: some View {
        let isA11y = dynamicTypeSize.isAccessibilitySize
        HStack(alignment: .center, spacing: 6) {
            Image(systemName: "exclamationmark.circle")
                .font(.system(size: 18, weight: .semibold))
                .foregroundStyle(.secondary)
            VStack(alignment: .leading, spacing: 1) {
                Text(status.title)
                    .font(isA11y ? .system(size: 10.5, weight: .semibold) : .caption2.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.8)
                Text(status.reason.complicationHeadline)
                    .font(isA11y ? .system(size: 13.5, weight: .semibold) : .headline)
                    .lineLimit(isA11y ? 2 : 1)
                    .minimumScaleFactor(isA11y ? 0.75 : 0.8)
                Text(status.reason.complicationDetail)
                    .font(isA11y ? .system(size: 11) : .caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.85)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(status.reason.accessibilityDescription(title: status.title))
        .accessibilityIdentifier("watch.complication.unavailable")
    }
}
