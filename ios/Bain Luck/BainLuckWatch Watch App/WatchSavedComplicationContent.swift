import SwiftUI

/// Shared rectangular content; WidgetKit owns the surrounding widget context.
struct WatchSavedComplicationContent: View {
    let snapshot: WatchComplicationSnapshot?

    var body: some View {
        if let snapshot {
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
