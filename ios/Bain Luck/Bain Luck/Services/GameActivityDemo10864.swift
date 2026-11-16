#if DEBUG && os(iOS) && canImport(ActivityKit)
import ActivityKit
import Foundation

/// #10864 — DEBUG only, never compiled into a release build. Launched with
/// `-BLLiveActivityDemo live` or `-BLLiveActivityDemo final`, the app starts a
/// Live Activity from a canned reading, so the simulator can show states a real
/// game can't be made to reach on demand: a final, and any text size. The
/// reading goes through the snapshot's own initializer, so the views see
/// nothing a real game couldn't send.
enum GameActivityDemo10864 {
    static let argument = "-BLLiveActivityDemo"
    static let eventID = 99_010_864

    static func runIfAsked(arguments: [String] = ProcessInfo.processInfo.arguments) {
        guard let index = arguments.firstIndex(of: argument), index + 1 < arguments.count else { return }
        let mode = arguments[index + 1]
        Task { @MainActor in
            // A request needs the app in the foreground.
            try? await Task.sleep(nanoseconds: 2_000_000_000)
            await run(mode)
        }
    }

    /// The canned reading: a live third quarter, or the same game finished.
    /// Built through the snapshot's own initializer, which applies every rule a
    /// real reading meets (a final carries no chance).
    static func snapshot(_ mode: String, now: Date = Date()) -> GameActivitySnapshot? {
        if mode == "nfl199" {
            // #199 — the reading #12755's page render shows (Patriots at Lions,
            // Q3 8:14, 17–21, Now 33.8% / 66.2%), so the Lock Screen and the
            // island can be photographed beside that page. Patriots navy shares
            // the Lions' hue family, so ruling 197 gives them their red.
            return GameActivitySnapshot(
                eventID: eventID + 1, homeTeam: "Detroit Lions", awayTeam: "New England Patriots",
                lifecycle: .live, homeScore: 21, awayScore: 17,
                homeProbability: 0.662, awayProbability: 0.338, sport: "americanfootball_nfl",
                scoreObservedAt: now, probabilityObservedAt: now,
                homeAbbreviation: "DET", awayAbbreviation: "NE",
                homeColorHex: "#0076B6", awayColorHex: "#002244", periodLabel: "Q3 8:14",
                awaySecondaryColorHex: "#C60C30")
        }
        let final = mode == "final"
        return GameActivitySnapshot(
            eventID: eventID, homeTeam: "Kansas City Chiefs", awayTeam: "New York Jets",
            lifecycle: final ? .final : .live,
            homeScore: final ? 35 : 21, awayScore: final ? 12 : 10,
            homeProbability: final ? nil : 0.81, awayProbability: final ? nil : 0.19,
            sport: "americanfootball_nfl",
            scoreObservedAt: now, probabilityObservedAt: final ? nil : now,
            homeAbbreviation: "KC", awayAbbreviation: "NYJ",
            homeColorHex: "#E31837", awayColorHex: "#125740",
            periodLabel: final ? nil : "Q3 8:14",
            projectedHomeScore: final ? nil : 31, projectedAwayScore: final ? nil : 17,
            projectionLabel: final ? nil : "Projected final",
            servedResult: final ? "home" : nil)
    }

    @MainActor
    private static func run(_ mode: String) async {
        for activity in Activity<GameActivityAttributes>.activities {
            await activity.end(nil, dismissalPolicy: .immediate)
        }
        // "pair" starts two games at once, so the island shows one compact and
        // one minimal; "nfl199" starts the #12755 page's game alone.
        let first = mode == "nfl199" || mode == "pair" ? "nfl199" : "live"
        if mode == "pair", let other = snapshot("live") {
            _ = try? Activity<GameActivityAttributes>.request(
                attributes: GameActivityAttributes(eventID: eventID),
                content: ActivityContent(state: GameActivityAttributes.ContentState(snapshot: other),
                                         staleDate: Date().addingTimeInterval(15 * 60)), pushType: nil)
            try? await Task.sleep(nanoseconds: 500_000_000)
        }
        guard let live = snapshot(first) else { return }
        let content = ActivityContent(state: GameActivityAttributes.ContentState(snapshot: live),
                                      staleDate: Date().addingTimeInterval(15 * 60))
        let activity: Activity<GameActivityAttributes>
        do {
            activity = try Activity<GameActivityAttributes>.request(
                attributes: GameActivityAttributes(eventID: live.eventID), content: content, pushType: nil)
        } catch {
            NSLog("LADEMO10864 request failed: %@", String(describing: error))
            return
        }
        NSLog("LADEMO10864 started %@ (%@)", activity.id, mode)
        guard mode == "final", let final = snapshot("final") else { return }
        try? await Task.sleep(nanoseconds: 1_500_000_000)
        // Ended with its final reading, as a real game ends; it stays on the Lock Screen.
        await activity.end(ActivityContent(state: GameActivityAttributes.ContentState(snapshot: final), staleDate: nil),
                           dismissalPolicy: .default)
    }
}
#endif
