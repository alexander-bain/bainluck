import WidgetKit
import SwiftUI

/// A timeless launcher; readings and refresh stay in the selected-game app.
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
        BainLuckEntry(date: Date(), snapshot: nil)
    }
}

struct BainLuckComplicationView: View {
    let entry: BainLuckEntry
    @Environment(\.widgetFamily) private var family

    var body: some View {
        Group {
            if family == .accessoryRectangular {
                WatchSavedComplicationContent(snapshot: entry.snapshot)
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel(accessibilityDescription)
            } else if family == .accessoryCorner {
                WatchSavedCornerComplicationContent(snapshot: entry.snapshot)
            } else {
                ZStack {
                    AccessoryWidgetBackground()
                    WatchSavedCircularComplicationContent(snapshot: entry.snapshot)
                }
            }
        }
        .containerBackground(.fill.tertiary, for: .widget)
        .widgetURL(WatchLaunchRoute.url)
    }
    private var accessibilityDescription: String {
        "Open your selected game in Bain Luck, or choose a game"
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
        .description("Open your selected game in Bain Luck, or choose a game.")
        .supportedFamilies([.accessoryCircular, .accessoryRectangular, .accessoryCorner])
    }
}
