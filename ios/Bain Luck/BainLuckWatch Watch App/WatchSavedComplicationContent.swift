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
