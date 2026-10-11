import SwiftUI
import WidgetKit

/// 1.0.3 complications are launchers only. Saved readings remain in the app.
/// Keep the existing interfaces and family identities for installed configurations.
struct WatchSavedComplicationContent: View {
    let snapshot: WatchComplicationSnapshot?

    var body: some View {
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
