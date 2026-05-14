import SwiftUI
import WidgetKit

// MARK: - Timeline Provider

struct BainLuckWidgetProvider: TimelineProvider {
    func placeholder(in context: Context) -> BainLuckWidgetEntry {
        .placeholder
    }

    func getSnapshot(in context: Context, completion: @escaping (BainLuckWidgetEntry) -> Void) {
        if context.isPreview {
            completion(.placeholder)
            return
        }
        Task {
            let entry = await fetchEntry()
            completion(entry)
        }
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<BainLuckWidgetEntry>) -> Void) {
        Task {
            let entry = await fetchEntry()

            // Refresh more frequently when there are live games (every 5 min),
            // less frequently when idle (every 15 min).
            let interval = entry.liveGames.isEmpty ? 15 : 5
            let nextUpdate = Calendar.current.date(byAdding: .minute, value: interval, to: Date())!

            completion(Timeline(entries: [entry], policy: .after(nextUpdate)))
        }
    }

    private func fetchEntry() async -> BainLuckWidgetEntry {
        async let gamesResult = fetchGames()
        async let discoverResult = fetchDiscover()

        let games = await gamesResult
        let discover = await discoverResult

        return BainLuckWidgetEntry(
            date: Date(),
            liveGames: games,
            discoverItems: discover
        )
    }

    private func fetchGames() async -> [WidgetGame] {
        do {
            return try await WidgetAPIClient.shared.fetchLiveGames(limit: 10)
        } catch {
            return []
        }
    }

    private func fetchDiscover() async -> [WidgetDiscoverItem] {
        do {
            return try await WidgetAPIClient.shared.fetchDiscoverItems(limit: 5)
        } catch {
            return []
        }
    }
}

// MARK: - Widget View (delegates to size-specific views)

struct BainLuckWidgetView: View {
    @Environment(\.widgetFamily) var family
    let entry: BainLuckWidgetEntry

    var body: some View {
        switch family {
        case .systemSmall:
            SmallLiveGameView(entry: entry)
        case .systemMedium:
            MediumLiveGamesView(entry: entry)
        default:
            SmallLiveGameView(entry: entry)
        }
    }
}

// MARK: - Widget Configuration

struct BainLuckDesktopWidget: Widget {
    let kind = "BainLuckWidget"

    var body: some WidgetConfiguration {
        StaticConfiguration(kind: kind, provider: BainLuckWidgetProvider()) { entry in
            BainLuckWidgetView(entry: entry)
                .containerBackground(.fill.tertiary, for: .widget)
        }
        .configurationDisplayName("Bain Luck")
        .description("Live game probabilities and trending prediction markets at a glance.")
        .supportedFamilies([.systemSmall, .systemMedium])
    }
}

// MARK: - Widget Bundle (entry point)

@main
struct BainLuckWidgetBundle: WidgetBundle {
    var body: some Widget {
        BainLuckDesktopWidget()
    }
}

// MARK: - Previews

#if DEBUG
#Preview("Small", as: .systemSmall) {
    BainLuckDesktopWidget()
} timeline: {
    BainLuckWidgetEntry.placeholder
}

#Preview("Medium", as: .systemMedium) {
    BainLuckDesktopWidget()
} timeline: {
    BainLuckWidgetEntry.placeholder
}

#Preview("Small - No Games", as: .systemSmall) {
    BainLuckDesktopWidget()
} timeline: {
    BainLuckWidgetEntry(date: Date(), liveGames: [], discoverItems: [])
}
#endif
