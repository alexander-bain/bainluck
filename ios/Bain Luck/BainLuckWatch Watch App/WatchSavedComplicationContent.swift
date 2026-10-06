import SwiftUI
import WidgetKit

/// Shared rectangular content; WidgetKit owns the surrounding widget context.
struct WatchSavedComplicationContent: View {
    let snapshot: WatchComplicationSnapshot?

    var body: some View {
        if let snapshot, let reading = snapshot.validatedCircularReading {
            GeometryReader { geometry in
                ViewThatFits(in: [.horizontal, .vertical]) {
                    namedReading(snapshot, reading: reading, width: geometry.size.width)
                        .fixedSize(horizontal: false, vertical: true)
                    compactReading(snapshot, reading: reading)
                        .fixedSize()
                    savedLauncher(snapshot)
                }
                .frame(width: geometry.size.width, height: geometry.size.height, alignment: .leading)
            }
        } else if let snapshot {
            // Legacy or malformed optional typed data does not earn invented graphics.
            VStack(alignment: .leading, spacing: 1) {
                Text(snapshot.title)
                    .font(.system(size: 12, weight: .semibold))
                    .lineLimit(2)
                    .minimumScaleFactor(0.8)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("watch.complication.title")
                Text("Saved · \(snapshot.detail)")
                    .font(.system(size: 11))
                    .lineLimit(2)
                    .minimumScaleFactor(0.8)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("watch.complication.detail")
                Text("Observed \(snapshot.observedAt.formatted(date: .abbreviated, time: .shortened))")
                    .font(.system(size: 9))
                    .lineLimit(2)
                    .minimumScaleFactor(0.8)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("watch.complication.observed")
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        } else {
            HStack(spacing: 8) {
                Image(systemName: "chart.bar.fill").font(.title2)
                VStack(alignment: .leading) {
                    Text("Your game").font(.headline)
                    Text("Open Bain Luck").font(.caption)
                }
            }
            .accessibilityElement(children: .combine)
            .accessibilityIdentifier("watch.complication.fallback")
        }
    }

    /// Full names wrap at the real proposed width; their full height must fit.
    /// No line limit can silently turn a long name into a fitting candidate.
    private func namedReading(_ snapshot: WatchComplicationSnapshot,
                              reading: WatchCircularReading, width: CGFloat) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack(alignment: .center, spacing: 6) {
                Text(snapshot.title)
                    .font(.system(size: 14, weight: .semibold))
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                Text(prominentValue(reading))
                    .font(.system(size: 28, weight: .bold, design: .rounded))
                    .monospacedDigit().fixedSize()
            }
            if reading.kind == .forecast, let percent = reading.percent {
                probabilityBar(percent)
            }
            metadata(snapshot, reading: reading)
        }
        .frame(width: width, alignment: .leading)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(accessibilityReading(snapshot))
        .accessibilityIdentifier("watch.complication.rectangular.prominent")
    }

    /// Canonical compact identities, never a truncated full name or guessed abbreviation.
    private func compactReading(_ snapshot: WatchComplicationSnapshot,
                                reading: WatchCircularReading) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack(spacing: 6) {
                Text(reading.subject).font(.system(size: 12, weight: .semibold))
                Text(prominentValue(reading))
                    .font(.system(size: 22, weight: .bold, design: .rounded)).monospacedDigit()
            }
            if reading.kind == .forecast, let percent = reading.percent {
                probabilityBar(percent).frame(width: 120)
            }
            metadata(snapshot, reading: reading)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(accessibilityReading(snapshot))
        .accessibilityIdentifier("watch.complication.rectangular.compact")
    }

    private func metadata(_ snapshot: WatchComplicationSnapshot,
                          reading: WatchCircularReading) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            Text("Saved · \(reading.stateLabel)").font(.system(size: 10, weight: .medium))
            Text("As of \(snapshot.observedAt.formatted(.dateTime.month(.abbreviated).day().year().hour().minute()))")
                .font(.system(size: 9))
        }
        .fixedSize(horizontal: false, vertical: true)
    }

    private func prominentValue(_ reading: WatchCircularReading) -> String {
        if reading.kind == .forecast { return reading.value }
        guard let home = reading.homeScore, let away = reading.awayScore else { return "" }
        // Match the named final winner; live/tied matchup scores keep away-home order.
        if reading.kind == .final, home > away { return "\(home)–\(away)" }
        return "\(away)–\(home)"
    }

    private func probabilityBar(_ percent: Int) -> some View {
        GeometryReader { geometry in
            ZStack(alignment: .leading) {
                Capsule().fill(Color.primary.opacity(0.2))
                Capsule().fill(Color.primary)
                    .frame(width: geometry.size.width * CGFloat(percent) / 100)
            }
        }
        .frame(height: 3)
        .accessibilityHidden(true)
    }

    private func savedLauncher(_ snapshot: WatchComplicationSnapshot) -> some View {
        Label("Open saved game", systemImage: "chart.bar.fill").font(.caption)
            .accessibilityLabel("Open your saved game in Bain Luck. \(snapshot.title).")
            .accessibilityIdentifier("watch.complication.rectangular.launcher")
    }

    private func accessibilityReading(_ snapshot: WatchComplicationSnapshot) -> String {
        "Saved reading. \(snapshot.title). \(snapshot.detail). Observed \(snapshot.observedAt.formatted(date: .abbreviated, time: .shortened)). Open your game in Bain Luck."
    }
}

/// Complete named saved reading or launcher; no clipped shorthand or currentness claim.
struct WatchSavedCircularComplicationContent: View {
    let snapshot: WatchComplicationSnapshot?

    var body: some View {
        if let snapshot, let reading = snapshot.validatedCircularReading {
            GeometryReader { geometry in
                // A rectangular fit alone cannot prove a fit inside the circle.
                // Reserve 40 points for the three readable lines, and derive the
                // largest centered rectangle whose corners stay inside this slot.
                let diameter = min(geometry.size.width, geometry.size.height)
                let contentHeight: CGFloat = 40
                let safeWidth = sqrt(max(0, diameter * diameter - contentHeight * contentHeight))
                ViewThatFits(in: [.horizontal, .vertical]) {
                    VStack(spacing: 0) {
                        Text("Saved").font(.system(size: 9, weight: .medium))
                            .accessibilityIdentifier("watch.complication.circular.saved")
                        Text(reading.subject).font(.system(size: 10, weight: .semibold))
                            .accessibilityIdentifier("watch.complication.circular.subject")
                        Text(reading.value).font(.system(size: reading.kind == .forecast ? 14 : 10, weight: .bold))
                            .accessibilityIdentifier("watch.complication.circular.value")
                    }
                    .fixedSize()
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel("Saved reading. \(snapshot.title). \(snapshot.detail). Observed \(snapshot.observedAt.formatted(date: .abbreviated, time: .shortened)). Open your game in Bain Luck.")
                    .accessibilityValue("Saved · \(reading.subject) · \(reading.value)")
                    .accessibilityIdentifier("watch.complication.circular.reading")
                    launcher
                }
                .frame(width: safeWidth, height: min(contentHeight, diameter))
                .frame(width: geometry.size.width, height: geometry.size.height)
            }
        } else {
            launcher
        }
    }

    private var launcher: some View {
        Image(systemName: "chart.bar.fill")
            .font(.system(size: 18))
            .accessibilityLabel("Open your selected game in Bain Luck, or choose a game")
            .accessibilityIdentifier("watch.complication.circular.fallback")
    }
}

/// WidgetKit owns the curved label's font and placement. Its complete rendered
/// label is an actual-face acceptance gate, not a runtime presence signal.
struct WatchSavedCornerComplicationContent: View {
    let snapshot: WatchComplicationSnapshot?
    @Environment(\.showsWidgetLabel) private var showsWidgetLabel

    var body: some View {
        if let snapshot, let reading = snapshot.validatedCornerForecast(showsWidgetLabel: showsWidgetLabel) {
            ViewThatFits(in: [.horizontal, .vertical]) {
                Text(reading.value)
                    // Retained Exactograph host provides a 34-point inner slot.
                    // Keep the complete percentage at a legible fixed size;
                    // ViewThatFits still falls back when it cannot fit.
                    .font(.system(size: 16, weight: .bold))
                    .fixedSize()
                    .widgetLabel {
                        Text("Saved · \(reading.subject)")
                            .accessibilityIdentifier("watch.complication.corner.label")
                    }
                    .accessibilityLabel("Saved reading. \(reading.awayName) at \(reading.homeName). \(snapshot.title). \(snapshot.detail). Observed \(snapshot.observedAt.formatted(date: .abbreviated, time: .shortened)). Open your game in Bain Luck.")
                    .accessibilityValue("Saved · \(reading.subject) · \(reading.value)")
                    .accessibilityIdentifier("watch.complication.corner.reading")
                launcher
            }
        } else {
            launcher
        }
    }

    private var launcher: some View {
        Image(systemName: "chart.bar.fill")
            .font(.system(size: 18))
            .accessibilityLabel("Open your selected game in Bain Luck, or choose a game")
            .accessibilityIdentifier("watch.complication.corner.fallback")
    }
}
