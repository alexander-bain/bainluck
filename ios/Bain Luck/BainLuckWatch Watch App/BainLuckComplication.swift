import WidgetKit
import SwiftUI

/// Timeless launcher content: no polling, personal data, or cached live readings.
nonisolated struct BainLuckEntry: TimelineEntry {
    let date: Date
}

nonisolated struct BainLuckProvider: TimelineProvider {
    func placeholder(in context: Context) -> BainLuckEntry { BainLuckEntry(date: Date()) }

    func getSnapshot(in context: Context, completion: @escaping (BainLuckEntry) -> Void) {
        completion(BainLuckEntry(date: Date()))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<BainLuckEntry>) -> Void) {
        completion(Timeline(entries: [BainLuckEntry(date: Date())], policy: .never))
    }
}

struct BainLuckComplicationView: View {
    @Environment(\.widgetFamily) private var family

    var body: some View {
        Group {
            if family == .accessoryRectangular {
                HStack(spacing: 8) {
                    Image(systemName: "chart.bar.fill").font(.title2)
                    VStack(alignment: .leading) {
                        Text("Your game").font(.headline)
                        Text("Open Bain Luck").font(.caption)
                    }
                }
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
        .accessibilityLabel("Open your selected game in Bain Luck, or choose a game")
    }
}

@main
struct BainLuckWidget: Widget {
    let kind = "BainLuckComplication"

    var body: some WidgetConfiguration {
        StaticConfiguration(kind: kind, provider: BainLuckProvider()) { _ in
            BainLuckComplicationView()
        }
        .configurationDisplayName("Your game")
        .description("Open your selected game, or choose one. Probability, not betting.")
        .supportedFamilies([.accessoryCircular, .accessoryRectangular])
    }
}
