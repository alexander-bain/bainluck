import AppIntents
import RelevanceKit
import WidgetKit
import SwiftUI

/// The face slot: the app's saved reading (the app stays its only writer).
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
        // #12316: with the app closed, this face slot is what keeps the Smart Stack card current.
        // A saved reading past the live threshold asks the card for a new entry (it fetches),
        // and while the game is under way the face asks again soon.
        if let saved = current.snapshot, WatchYourGameRefresh.wantsRefresh(saved, now: current.date) {
            WidgetCenter.shared.reloadTimelines(ofKind: "BainLuckYourGame")
        }
        if let recheck = WatchYourGameRefresh.faceRecheck(current.snapshot, now: current.date) {
            completion(Timeline(entries: entries, policy: .after(recheck)))
            return
        }
        completion(Timeline(entries: entries, policy: dates.count > 1 ? .atEnd : .never))
    }
    private func entry() -> BainLuckEntry {
        let now = Date()
        return BainLuckEntry(date: now, snapshot: Self.saved(now: now))
    }

    /// The one shared-file read behind both the face slot and the Smart Stack card.
    static func saved(now: Date) -> WatchComplicationSnapshot? {
        let directory = FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: "group.com.bainluck.watch")
        return WatchComplicationSnapshot.read(from: directory, now: now)
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
        guard family == .accessoryRectangular, let snapshot = entry.snapshot else {
            return "Open your selected game in Bain Luck, or choose a game"
        }
        if let rectangular = snapshot.validatedRectangularReading(now: entry.date) {
            return rectangular.accessibilityDescription(at: entry.date)
        }
        return "Saved reading. \(snapshot.title). \(snapshot.detail). Saved \(snapshot.savedAt.formatted(date: .abbreviated, time: .shortened)). Open your game in Bain Luck."
    }
}

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

// MARK: - #12316 Smart Stack relevance

/// Names the chosen game for its Smart Stack relevance. The reader never configures it:
/// the game chosen in the watch app supplies the id. Main-actor by default like the app's
/// other intents (a `nonisolated` type cannot hold an `@Parameter`); the members the
/// provider uses are nonisolated.
struct YourGameIntent: WidgetConfigurationIntent {
    nonisolated static let title: LocalizedStringResource = "Your game"
    nonisolated static let description = IntentDescription("The game you chose in Bain Luck on this watch.")

    @Parameter(title: "Game")
    var eventID: Int?

    nonisolated init() {}

    nonisolated init(eventID: Int) {
        self.eventID = eventID
    }
}

nonisolated struct YourGameEntry: RelevanceEntry {
    let date: Date
    let snapshot: WatchComplicationSnapshot?
}

/// Suggests the chosen game's card only inside its game-day window and shows the large
/// face slot's reading (refreshed once mid-game when old). The card gets one entry, not a
/// timeline, so its age is drawn by a clock that keeps counting, never frozen at the entry.
nonisolated struct YourGameRelevanceProvider: RelevanceEntriesProvider {
    func relevance() async -> WidgetRelevance<YourGameIntent> {
        let now = Date()
        guard let saved = BainLuckProvider.saved(now: now), let window = saved.relevanceWindow,
              window.end > now else { return WidgetRelevance([]) }
        // Informational, not scheduled: the Smart Stack treats a scheduled interval as a
        // calendar event and drops the card 15 minutes after the window opens, at the start.
        return WidgetRelevance([
            WidgetRelevanceAttribute(configuration: YourGameIntent(eventID: saved.eventID),
                                     context: .date(interval: window, kind: .informational))
        ])
    }

    func entry(configuration: YourGameIntent, context: Context) async throws -> YourGameEntry {
        let now = Date()
        let saved = BainLuckProvider.saved(now: now)
        // A suggestion made for an earlier choice never shows a different game.
        guard let saved, saved.eventID == configuration.eventID else {
            return YourGameEntry(date: now, snapshot: nil)
        }
        guard !context.isPreview else { return YourGameEntry(date: now, snapshot: saved) }
        // Mid-game with an old saved reading: one bounded fetch of the same game, else the saved one.
        let shown = await WatchYourGameRefresh.reading(saved: saved, now: now)
        return YourGameEntry(date: max(now, shown.savedAt), snapshot: shown)
    }

    func placeholder(context: Context) -> YourGameEntry {
        YourGameEntry(date: Date(), snapshot: nil)
    }
}

struct BainLuckYourGameWidget: Widget {
    let kind = "BainLuckYourGame"

    var body: some WidgetConfiguration {
        RelevanceConfiguration(kind: kind, provider: YourGameRelevanceProvider()) { entry in
            WatchSavedComplicationContent(snapshot: entry.snapshot, now: entry.date, liveAge: true)
                .containerBackground(.fill.tertiary, for: .widget)
                .widgetURL(WatchLaunchRoute.url)
        }
        .configurationDisplayName("Your game")
        .description("Your chosen game on game day, with its saved reading and its age.")
        // The Smart Stack draws rectangular cards; the reading is laid out for no other size.
        .supportedFamilies([.accessoryRectangular])
    }
}

@main
struct BainLuckWidgets: WidgetBundle {
    var body: some Widget {
        BainLuckWidget()
        BainLuckYourGameWidget()
    }
}

#Preview("Your game in the Smart Stack", widget: { BainLuckYourGameWidget() },
         relevanceProvider: { YourGameRelevanceProvider() })
