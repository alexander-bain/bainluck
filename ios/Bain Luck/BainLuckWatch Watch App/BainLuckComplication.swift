import WidgetKit
import SwiftUI

/// Saved public reading or a timeless launcher; the extension never polls.
nonisolated struct BainLuckEntry: TimelineEntry {
    let date: Date
    let snapshot: WatchComplicationSnapshot?
}

nonisolated struct BainLuckProvider: TimelineProvider {
    func placeholder(in context: Context) -> BainLuckEntry { BainLuckEntry(date: Date(), snapshot: nil) }

    func getSnapshot(in context: Context, completion: @escaping (BainLuckEntry) -> Void) {
        completion(entry())
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<BainLuckEntry>) -> Void) {
        completion(Timeline(entries: [entry()], policy: .never))
    }
    private func entry() -> BainLuckEntry {
        let now = Date()
        let directory = FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: "group.com.bainluck.watch")
        return BainLuckEntry(date: now, snapshot: WatchComplicationSnapshot.read(from: directory, now: now))
    }
}

struct BainLuckComplicationView: View {
    let entry: BainLuckEntry
    @Environment(\.widgetFamily) private var family

    var body: some View {
        Group {
            if family == .accessoryRectangular {
                WatchSavedComplicationContent(snapshot: entry.snapshot)
            } else {
                ZStack {
                    AccessoryWidgetBackground()
                    Image(systemName: "chart.bar.fill").font(.title2)
                }
            }
        }
        .containerBackground(.fill.tertiary, for: .widget)
        .widgetURL(WatchLaunchRoute.url)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(accessibilityDescription)
    }
    private var accessibilityDescription: String {
        guard family == .accessoryRectangular, let snapshot = entry.snapshot else {
            return "Open your selected game in Bain Luck, or choose a game"
        }
        return "Saved reading. \(snapshot.title). \(snapshot.detail). Observed \(snapshot.observedAt.formatted(date: .abbreviated, time: .shortened)). Open your game in Bain Luck."
    }
}

@main
struct BainLuckWidget: Widget {
    let kind = "BainLuckComplication"

    var body: some WidgetConfiguration {
        StaticConfiguration(kind: kind, provider: BainLuckProvider()) { entry in
            BainLuckComplicationView(entry: entry)
        }
        .configurationDisplayName("Your game")
        .description("Your last saved game reading, when available. Tap to open Bain Luck.")
        .supportedFamilies([.accessoryCircular, .accessoryRectangular])
    }
}
