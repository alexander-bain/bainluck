import Foundation
import SwiftUI

// MARK: - Watch marquee value types + pure selection
//
// The marquee/my-teams value types and the pure feed→story selection logic live
// here (Foundation + SwiftUI only, no WatchKit) so they can be compiled into the
// iOS test bundle and exercised directly — mirroring `WatchGuessPool`. The
// SwiftUI-bound `WatchHomeView` and its WatchKit-touching view model stay in
// `WatchHomeView.swift`; this file carries no `import WatchKit`.

// MARK: Value types

enum WatchStoryBadge: Equatable {
    case live, final, soon, none
}

struct WatchProbSplit {
    let leftAbbr: String
    let leftPct: Int
    let leftColor: String?
    let rightAbbr: String
    let rightPct: Int
    let rightColor: String?
}

struct WatchTopStory: Identifiable {
    let id: String
    let badge: WatchStoryBadge
    let clock: String?
    let categoryLabel: String?
    let title: String
    let bigLabel: String
    let bigNumber: Int
    let headline: String?
    let split: WatchProbSplit?

    var accentColor: Color {
        switch badge {
        case .live: return .green
        case .final: return .secondary
        default: return .blue
        }
    }
}

struct WatchTeamGame: Identifiable {
    let id: Int
    let matchup: String
    let split: WatchProbSplit
    let live: Bool
    let clock: String?
    let startText: String?
}

// MARK: - Pure marquee/my-teams selection (testable, WatchKit-free)

enum WatchMarquee {

    // MARK: Marquee selection

    /// The top story is the first live game that can render a story, otherwise the
    /// first *renderable* item in rank order (the server already pins marquee
    /// majors to the front).
    ///
    /// L2-200: the old logic tested only `topLive ?? items.first` and returned nil
    /// if that single item was not renderable. A leading concept/tournament (both
    /// unsupported on Watch) or an event without `current_odds` then blanked the
    /// entire marquee even when item two was a perfectly usable event/futures
    /// story. Now we scan: live events take priority (first live event that yields
    /// a story), then the first renderable item of any kind. Concept/tournament
    /// cards carry no Watch-renderable probability, so they are skipped, not fatal.
    static func marquee(from items: [WatchFeedItem], now: Date = Date()) -> WatchTopStory? {
        // Live priority: the first live event that can actually produce a story.
        for item in items where item.event?.isLive == true {
            if let story = story(from: item, now: now) { return story }
        }
        // Otherwise the first renderable item in rank order.
        for item in items {
            if let story = story(from: item, now: now) { return story }
        }
        return nil
    }

    /// Build a marquee story from a single feed item, or nil if it carries nothing
    /// the Watch can render (concept/tournament hubs, or an event/futures card
    /// missing its probability). Pure so `marquee(from:)` can scan for the first
    /// item that qualifies.
    static func story(from item: WatchFeedItem, now: Date = Date()) -> WatchTopStory? {
        if let e = item.event, let home = e.currentOdds?.homeProbability {
            return eventStory(item, e, homeProb: home)
        }
        // L2-225: a settled market carries a normal-looking price and no badge, so
        // without this it could become the wrist's TOP STORY — the single biggest
        // number on the watch face's feed — for a question already decided. Skipped,
        // not fatal: `marquee(from:)` scans on to the next renderable item, the same
        // way it already steps over concept/tournament hubs (L2-200).
        if let f = item.futures, !f.isSettled(now: now),
           let leader = f.topOutcomes?.first, let p = leader.probability {
            let pct = pct(p)
            return WatchTopStory(
                id: item.id,
                badge: .none,
                clock: nil,
                categoryLabel: f.llmSportCategory,
                title: f.name,
                bigLabel: shortName(leader.name),
                bigNumber: pct,
                headline: item.headline,
                split: nil
            )
        }
        return nil
    }

    private static func eventStory(_ item: WatchFeedItem, _ e: WatchFeedEvent, homeProb: Double) -> WatchTopStory {
        let homePct = pct(homeProb)
        let awayPct = 100 - homePct
        let homeAbbr = e.homeAbbrev()
        let awayAbbr = e.awayAbbrev()
        let homeLeads = homePct >= awayPct
        let badge: WatchStoryBadge = e.isLive ? .live : (e.isSettled ? .final : .soon)

        return WatchTopStory(
            id: item.id,
            badge: badge,
            clock: e.clockText,
            categoryLabel: e.sportName ?? e.sport,
            title: "\(awayAbbr) @ \(homeAbbr)",
            bigLabel: homeLeads ? homeAbbr : awayAbbr,
            bigNumber: max(homePct, awayPct),
            headline: item.headline,
            split: WatchProbSplit(
                leftAbbr: awayAbbr, leftPct: awayPct, leftColor: e.awayTeamData?.primaryColor,
                rightAbbr: homeAbbr, rightPct: homePct, rightColor: e.homeTeamData?.primaryColor
            )
        )
    }

    // MARK: My-teams mapping

    static func teamGames(from items: [WatchFeedItem]) -> [WatchTeamGame] {
        items.compactMap { item -> WatchTeamGame? in
            guard let e = item.event, let home = e.currentOdds?.homeProbability else { return nil }
            let homePct = pct(home)
            let awayPct = 100 - homePct
            let homeAbbr = e.homeAbbrev()
            let awayAbbr = e.awayAbbrev()
            return WatchTeamGame(
                id: e.id,
                matchup: "\(awayAbbr) @ \(homeAbbr)",
                split: WatchProbSplit(
                    leftAbbr: awayAbbr, leftPct: awayPct, leftColor: e.awayTeamData?.primaryColor,
                    rightAbbr: homeAbbr, rightPct: homePct, rightColor: e.homeTeamData?.primaryColor
                ),
                live: e.isLive,
                clock: e.clockText,
                // L2-225: a FINISHED game must not advertise a start time. `live` is
                // false once a game settles, so the old expression fell straight
                // through to `startText(commenceTime)` and rendered a completed game
                // with a forward-looking "Tmrw 7:30 PM"-shaped line next to a
                // probability split. Suppress it; the row stays, honestly quiet.
                // (Whether a settled team game should instead show FINAL + score is a
                // product call — `WatchTeamGame` carries no result field — routed to
                // Fable rather than invented here.)
                startText: (e.isLive || e.isSettled) ? nil : startText(e.commenceTime)
            )
        }
    }

    // MARK: Helpers

    static func pct(_ p: Double) -> Int { Int((p * 100).rounded()) }

    static func shortName(_ name: String) -> String {
        name.count <= 16 ? name : String(name.prefix(15)) + "…"
    }

    /// Short "today 7:30 PM" / weekday time from an ISO8601 commence time.
    static func startText(_ iso: String?) -> String? {
        guard let iso, let date = isoFormatter.date(from: iso) ?? isoFormatterNoFraction.date(from: iso) else {
            return nil
        }
        let cal = Calendar.current
        let time = timeFormatter.string(from: date)
        if cal.isDateInToday(date) { return time }
        if cal.isDateInTomorrow(date) { return "Tmrw \(time)" }
        return "\(weekdayFormatter.string(from: date)) \(time)"
    }

    private static let isoFormatter: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()
    private static let isoFormatterNoFraction: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f
    }()
    private static let timeFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "h:mm a"
        return f
    }()
    private static let weekdayFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "EEE"
        return f
    }()
}
