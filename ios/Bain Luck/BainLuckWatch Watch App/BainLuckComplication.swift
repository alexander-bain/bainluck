import WidgetKit
import SwiftUI

/// A timeless launcher; readings and refresh stay in the selected-game app.
nonisolated struct BainLuckEntry: TimelineEntry {
    let date: Date
    let snapshot: WatchComplicationSnapshot?
    var unavailableStatus: WatchFaceStatusPayload13339? = nil

    /// #12316 / 254: A — promote the followed game in the Apple Watch Smart Stack
    /// starting 30 minutes before kickoff and while live, then drop back after final.
    var relevance: TimelineEntryRelevance? {
        let spec = snapshot?.relevanceSpec254A(now: date) ?? .zero
        return TimelineEntryRelevance(score: spec.score, duration: spec.duration)
    }
}

nonisolated struct BainLuckProvider: TimelineProvider {
    func placeholder(in context: Context) -> BainLuckEntry { BainLuckEntry(date: Date(), snapshot: nil) }

    func getSnapshot(in context: Context, completion: @escaping (BainLuckEntry) -> Void) {
        completion(entry())
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<BainLuckEntry>) -> Void) {
        let current = entry()
        var dates: [Date]
        if context.family == .accessoryRectangular,
           let matchupDates = WatchMatchupReading217.timelineDates(for: current.snapshot, now: current.date) {
            dates = matchupDates
        } else {
            dates = WatchRectangularReading.timelineDates(for: current.snapshot, now: current.date)
            // Direction 217 & #13430: a final gives way 3 hours on.
            if let step = WatchMatchupReading217.finalStepAside(for: current.snapshot, now: current.date),
               step > current.date, !dates.contains(step) {
                dates.append(step)
            } else if let reading = current.snapshot?.validatedRectangularReading(now: current.date),
                      reading.kind == .finalResult {
                let step = reading.observedAt.addingTimeInterval(WatchMatchupReading217.finalHoldSeconds)
                if step > current.date, !dates.contains(step) {
                    dates.append(step)
                }
            }
        }
        // #12316 / 254: A: step Smart Stack relevance up before kickoff, at kickoff, and down after final.
        if let relevanceSteps = current.snapshot?.relevanceBoundaryDates254A(now: current.date),
           !relevanceSteps.isEmpty {
            dates.append(contentsOf: relevanceSteps)
        }
        dates = Array(Set(dates)).sorted()
        let entries = dates.map {
            BainLuckEntry(date: $0, snapshot: current.snapshot, unavailableStatus: current.unavailableStatus)
        }
        let policy: TimelineReloadPolicy = dates.count > 1
            ? .atEnd
            : .after(current.date.addingTimeInterval(15 * 60))
        completion(Timeline(entries: entries, policy: policy))
    }
    private func entry() -> BainLuckEntry {
        let now = Date()
        let directory = FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: "group.com.bainluck.watch")
        return BainLuckEntry(
            date: now,
            snapshot: WatchComplicationSnapshot.read(from: directory, now: now),
            unavailableStatus: WatchFaceStatusPayload13339.read(from: directory)
        )
    }
}

struct BainLuckComplicationView: View {
    let entry: BainLuckEntry
    @Environment(\.widgetFamily) private var family

    var body: some View {
        Group {
            if family == .accessoryRectangular {
                if WatchMatchupReading217.finalHasPassed(entry.snapshot, now: entry.date) {
                    // 3 hours after the final: state clearly that the game ended instead of mimicking "Your game".
                    let title = entry.unavailableStatus?.title
                        ?? entry.snapshot?.rectangularReading?.headerLine(preferCompact: true)
                        ?? entry.snapshot?.title
                        ?? "Chosen game"
                    WatchUnavailableComplicationContent13339(
                        status: WatchFaceStatusPayload13339(
                            targetID: entry.unavailableStatus?.targetID ?? entry.snapshot?.eventID ?? 1,
                            title: title,
                            reason: .finalEnded,
                            updatedAt: entry.date
                        )
                    )
                } else if let matchup = WatchMatchupReading217.make(snapshot: entry.snapshot, now: entry.date) {
                    WatchMatchupComplication217(reading: matchup)
                } else if entry.snapshot?.validatedRectangularReading(now: entry.date) != nil {
                    WatchSavedComplicationContent(snapshot: entry.snapshot, now: entry.date)
                        .accessibilityElement(children: .ignore)
                        .accessibilityLabel(accessibilityDescription)
                } else if let status = entry.unavailableStatus {
                    WatchUnavailableComplicationContent13339(status: status)
                } else {
                    WatchSavedComplicationContent(snapshot: nil, now: entry.date)
                        .accessibilityElement(children: .ignore)
                        .accessibilityLabel(accessibilityDescription)
                }
            } else if family == .accessoryCorner {
                WatchSavedCornerComplicationContent(snapshot: entry.snapshot, now: entry.date)
            } else {
                WatchSavedCircularComplicationContent(snapshot: entry.snapshot, now: entry.date)
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
        if let small = entry.snapshot?.smallSlotModel(now: entry.date) {
            return small.accessibilityText
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
