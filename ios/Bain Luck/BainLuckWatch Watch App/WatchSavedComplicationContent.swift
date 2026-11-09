import SwiftUI
import WidgetKit

/// Large rectangular (`accessoryRectangular`) selected-game reading for #4933,
/// with honest launcher fallback when no valid shared snapshot exists.
/// Circular and corner families remain explicit launchers.
struct WatchSavedComplicationContent: View {
    let snapshot: WatchComplicationSnapshot?
    var now: Date = Date()
    /// #12316 Smart Stack card: one entry and no timeline, so the age is a clock that keeps
    /// counting. The face slot keeps `false` and redraws its age from its timeline.
    var liveAge: Bool = false
    @Environment(\.widgetRenderingMode) private var renderingMode

    private var accentColor: Color { renderingMode == .fullColor ? .cyan : .primary }

    var body: some View {
        if let snapshot, let reading = snapshot.validatedRectangularReading(now: now) {
            ViewThatFits(in: [.horizontal, .vertical]) {
                readingCard(reading, preferCompact: false)
                readingCard(reading, preferCompact: true)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(liveAge
                ? reading.accessibilityDescription(
                    at: now, observedClock: WatchRectangularReading.spokenClock(observedAt: reading.observedAt))
                : reading.accessibilityDescription(at: now))
            .accessibilityIdentifier("watch.complication.rectangular.reading")
        } else if let snapshot, snapshot.isValid(now: now) {
            legacyCard(snapshot)
                .frame(maxWidth: .infinity, alignment: .leading)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(
                    "Saved reading. \(snapshot.title). \(snapshot.detail). Saved \(snapshot.savedAt.formatted(date: .abbreviated, time: .shortened)). Open your game in Bain Luck."
                )
                .accessibilityIdentifier("watch.complication.rectangular.legacy")
        } else {
            HStack(spacing: 8) {
                Image(systemName: "chart.bar.fill").font(.title2)
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
                .font(.system(size: 11, weight: .semibold))
                .foregroundStyle(.secondary)
                .lineLimit(1)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("watch.complication.rectangular.header")
            Text(reading.primaryLine(preferCompact: preferCompact, at: now))
                .font(.system(size: 14, weight: .bold, design: .rounded))
                .foregroundStyle(
                    (reading.kind == .liveForecast || reading.kind == .scheduledForecast)
                        ? accentColor : .primary
                )
                .monospacedDigit()
                .lineLimit(preferCompact ? 1 : 2)
                .minimumScaleFactor(0.85)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("watch.complication.rectangular.primary")
            if liveAge, let leadIn = reading.metadataLeadIn(at: now) {
                liveMetadata(reading, leadIn: leadIn)
            } else {
                Text(reading.metadataLine(at: now))
                    .font(.system(size: 10, weight: .medium))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.85)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("watch.complication.rectangular.metadata")
            }
        }
    }

    /// #12316 Smart Stack card: the face's words, then an age that keeps counting. A long
    /// line loses its middle, so both "Saved" and the age stay visible.
    private func liveMetadata(_ reading: WatchRectangularReading, leadIn: String) -> some View {
        let age = SystemFormatStyle.DateReference(
            to: reading.observedAt, allowedFields: [.day, .hour, .minute], maxFieldCount: 1)
        return Text("\(leadIn)\(.currentDate, format: age)")
            .font(.system(size: 10, weight: .medium))
            .foregroundStyle(.secondary)
            .lineLimit(1)
            .minimumScaleFactor(0.85)
            .truncationMode(.middle)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityIdentifier("watch.complication.rectangular.metadata")
    }

    private func legacyCard(_ snapshot: WatchComplicationSnapshot) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(snapshot.title)
                .font(.system(size: 12, weight: .semibold))
                .lineLimit(2)
                .minimumScaleFactor(0.85)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("watch.complication.title")
            Text("Saved · \(snapshot.detail)")
                .font(.system(size: 11))
                .lineLimit(2)
                .minimumScaleFactor(0.85)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("watch.complication.detail")
            Text("Saved \(snapshot.savedAt.formatted(date: .abbreviated, time: .shortened))")
                .font(.system(size: 9))
                .foregroundStyle(.secondary)
                .lineLimit(1)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("watch.complication.observed")
        }
    }
}

struct WatchSavedCircularComplicationContent: View {
    let snapshot: WatchComplicationSnapshot?

    var body: some View {
        Image(systemName: "chart.bar.fill")
            .font(.system(size: 18))
            .accessibilityLabel("Open your selected game in Bain Luck, or choose a game")
            .accessibilityIdentifier("watch.complication.circular.fallback")
    }
}

struct WatchSavedCornerComplicationContent: View {
    let snapshot: WatchComplicationSnapshot?

    var body: some View {
        Image(systemName: "chart.bar.fill")
            .font(.system(size: 18))
            .accessibilityLabel("Open your selected game in Bain Luck, or choose a game")
            .accessibilityIdentifier("watch.complication.corner.fallback")
    }
}
