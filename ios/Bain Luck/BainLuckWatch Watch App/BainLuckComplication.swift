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
        let current = entry()
        let dates = WatchRectangularReading.timelineDates(for: current.snapshot, now: current.date)
        let entries = dates.map { BainLuckEntry(date: $0, snapshot: current.snapshot) }
        completion(Timeline(entries: entries, policy: dates.count > 1 ? .atEnd : .never))
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
                WatchSavedComplicationContent(snapshot: entry.snapshot, now: entry.date)
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
        if family == .accessoryRectangular,
           let rectangular = entry.snapshot?.validatedRectangularReading(now: entry.date) {
            return rectangular.accessibilityDescription(at: entry.date)
        }
        return "Open your selected game in Bain Luck, or choose a game"
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
