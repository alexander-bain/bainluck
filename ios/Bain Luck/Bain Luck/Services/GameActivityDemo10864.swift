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
        if mode == "tennis250a" {
            // #13000 (Decision 250-A) — live ATP Challenger tennis match with no score feed
            // carrying it: Score column omitted completely, LIVE + Now + Chance time kept.
            return GameActivitySnapshot(
                eventID: eventID + 4,
                homeTeam: "Tristan Boyer",
                awayTeam: "Genaro Alberto Olivieri",
                lifecycle: .live,
                homeScore: nil,
                awayScore: nil,
                homeProbability: 0.624,
                awayProbability: 0.376,
                sport: "tennis_atp",
                scoreObservedAt: nil,
                probabilityObservedAt: now,
                homeAbbreviation: "BOY",
                awayAbbreviation: "OLI",
                homeColorHex: "#1D4ED8",
                awayColorHex: "#B45309",
                periodLabel: nil,
                scoreSourceUnavailable: true)
        }
        if mode == "ncaab12999pushed" {
            // #12999 — decoded directly from the server APNs wire JSON shape
            // (seconds since 2001) to verify pushed updates draw the exact same headline.
            let scoreSec = now.addingTimeInterval(-120).timeIntervalSinceReferenceDate
            let probSec = now.timeIntervalSinceReferenceDate
            let json = """
            {"snapshot":{"eventID":\(eventID + 3),"homeTeam":"Florida Gators","awayTeam":"Houston Cougars",\
            "lifecycle":"live","homeScore":54,"awayScore":58,"homeRenderedPercent":39,"awayRenderedPercent":61,\
            "homeHeadlineTenths":386,"sport":"basketball_ncaab","homeAbbreviation":"FLA","awayAbbreviation":"HOU",\
            "homeColorHex":"#0021A5","awayColorHex":"#C8102E","awaySecondaryColorHex":"#960C22",\
            "periodLabel":"2nd Half","scoreObservedAt":\(scoreSec),"probabilityObservedAt":\(probSec)}}
            """
            return (try? JSONDecoder().decode(GameActivityAttributes.ContentState.self, from: Data(json.utf8)))?.snapshot
        }
        if mode == "ncaab12999live" || mode == "ncaab12999ht" || mode == "ncaab12999final" {
            // #12999 — Houston Cougars at Florida Gators (Alex's exact college
            // basketball game from 2:58 PM Wed Nov 18): schools not mascots,
            // live (two distinct times), halftime, and final with pregame (209).
            let isFinal = mode == "ncaab12999final"
            let isHT = mode == "ncaab12999ht"
            let scoreTime = isHT ? now : now.addingTimeInterval(-120)
            return GameActivitySnapshot(
                eventID: eventID + 2,
                homeTeam: "Florida Gators",
                awayTeam: "Houston Cougars",
                lifecycle: isFinal ? .final : .live,
                homeScore: isFinal ? 78 : (isHT ? 40 : 54),
                awayScore: isFinal ? 74 : (isHT ? 37 : 58),
                homeProbability: isFinal ? nil : (isHT ? 0.632 : 0.386),
                awayProbability: isFinal ? nil : (isHT ? 0.368 : 0.614),
                sport: "basketball_ncaab",
                scoreObservedAt: scoreTime,
                probabilityObservedAt: isFinal ? nil : now,
                homeAbbreviation: "FLA",
                awayAbbreviation: "HOU",
                homeColorHex: "#0021A5",
                awayColorHex: "#C8102E",
                periodLabel: isFinal ? nil : (isHT ? "HT" : "2nd Half"),
                servedResult: isFinal ? "home" : nil,
                awaySecondaryColorHex: "#960C22",
                pregameAwayPercent: isFinal ? 48 : nil,
                pregameHomePercent: isFinal ? 52 : nil)
        }
        if mode == "nfl199pre" || mode == "nfl199final" {
            // #199 — the same game before kickoff (the page's `Chance`) and
            // finished (the page's `Final`, winner ticked from the server's verdict).
            let final = mode == "nfl199final"
            return GameActivitySnapshot(
                eventID: eventID + 1, homeTeam: "Detroit Lions", awayTeam: "New England Patriots",
                lifecycle: final ? .final : .scheduled, homeScore: final ? 27 : nil, awayScore: final ? 20 : nil,
                homeProbability: final ? nil : 0.614, awayProbability: final ? nil : 0.386,
                sport: "americanfootball_nfl",
                scoreObservedAt: final ? now : nil, probabilityObservedAt: final ? nil : now,
                homeAbbreviation: "DET", awayAbbreviation: "NE",
                homeColorHex: "#0076B6", awayColorHex: "#002244", periodLabel: nil,
                servedResult: final ? "home" : nil,
                awaySecondaryColorHex: "#C60C30",
                pregameAwayPercent: final ? 39 : nil, pregameHomePercent: final ? 61 : nil)
        }
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
        let first = mode == "nfl199" || mode == "pair" ? "nfl199"
            : (mode == "nfl199pre" || mode == "nfl199final"
               || mode == "ncaab12999live" || mode == "ncaab12999ht"
               || mode == "ncaab12999final" || mode == "ncaab12999pushed"
               || mode == "tennis250a") ? mode : "live"
        if mode == "pair", let other = snapshot("live") {
            _ = try? Activity<GameActivityAttributes>.request(
                attributes: GameActivityAttributes(eventID: eventID),
                content: ActivityContent(state: GameActivityAttributes.ContentState(snapshot: other),
                                         staleDate: Date().addingTimeInterval(15 * 60)), pushType: nil)
            try? await Task.sleep(nanoseconds: 500_000_000)
        }
        guard let live = snapshot(first) else { return }
        // The crests a real game page would have fetched (GameActivityCrests).
        await GameActivityCrests.prefetch(
            eventID: live.eventID,
            away: EventDetailView.activityCrestURL(served: nil, team: live.awayTeam),
            home: EventDetailView.activityCrestURL(served: nil, team: live.homeTeam))
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
