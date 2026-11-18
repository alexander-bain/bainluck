#if DEBUG
import SwiftUI
import WidgetKit
#if os(watchOS)
import WatchKit
#endif

/// Direction 217 look sheet, DEBUG only: one Matchup slot at the size the real
/// Modular face gives it (measured on the simulators Nov 16: 41 mm 171.5×73 pt,
/// 49 mm 199×84.5 pt), on a black face, full colour or tinted. Real games and
/// real numbers except where the launch says "example".
///
/// Env (via SIMCTL_CHILD_): BAINLUCK_WATCH_MATCHUP_LOOK_217 = before|during|after,
/// BAINLUCK_WATCH_MATCHUP_MODE_217 = full|tinted, BAINLUCK_WATCH_MATCHUP_LOGOS_217 = a
/// folder holding <abbr>.png crests.
struct WatchMatchupLookSheet217: View {
    let stage: String
    private let env = ProcessInfo.processInfo.environment

    private var tinted: Bool { env["BAINLUCK_WATCH_MATCHUP_MODE_217"] == "tinted" }

    private var slot: CGSize {
        // The slot this screen's face would give the big rectangular complication.
        WKInterfaceDeviceScreen.width >= 200 ? CGSize(width: 199, height: 84.5) : CGSize(width: 171.5, height: 73)
    }

    var body: some View {
        ZStack(alignment: .top) {
            Color.black.ignoresSafeArea()
            VStack(spacing: 6) {
                Spacer(minLength: 0)
                tile
                    .frame(width: slot.width, height: slot.height)
                Spacer(minLength: 0)
            }
        }
        .toolbar(.hidden, for: .navigationBar)
    }

    @ViewBuilder private var tile: some View {
        if let reading = Self.reading(stage, logos: env["BAINLUCK_WATCH_MATCHUP_LOGOS_217"]) {
            if tinted {
                WatchMatchupComplication217(reading: reading)
                    .environment(\.widgetRenderingMode, .accented)
                    // The face's tint, as a tinted Modular face applies it.
                    .colorMultiply(Color(red: 1.0, green: 0.62, blue: 0.2))
            } else {
                WatchMatchupComplication217(reading: reading)
                    .environment(\.widgetRenderingMode, .fullColor)
            }
        }
    }

    private static func crest(_ abbr: String, in folder: String?) -> Data? {
        guard let folder else { return nil }
        return FileManager.default.contents(atPath: "\(folder)/\(abbr.lowercased()).png")
    }

    /// Builds a published snapshot exactly as the Watch app writes it and draws
    /// it through `WatchMatchupReading217.make`, the same path the complication uses.
    static func reading(_ stage: String, logos: String?, now: Date = Date()) -> WatchMatchupReading217? {
        let teams: [Int: (abbr: String, name: String, primary: String, secondary: String)] = [
            1: ("NE", "New England Patriots", "#002a5c", "#c60c30"),
            2: ("LAC", "Los Angeles Chargers", "#0080c6", "#ffc20e"),
            3: ("BAL", "Baltimore Ravens", "#241773", "#9e7c0c"),
            4: ("DET", "Detroit Lions", "#0076b6", "#b0b7bc"),
        ]
        func id(_ n: Int) -> WatchCompactTeamIdentity { WatchCompactTeamIdentity(teamID: n, abbreviation: teams[n]!.abbr) }
        func facts(away: Int, home: Int, pregameHome: Int? = nil, clock: String? = nil) -> WatchMatchupFacts217 {
            WatchMatchupFacts217(homePrimary: teams[home]!.primary, homeSecondary: teams[home]!.secondary,
                                 awayPrimary: teams[away]!.primary, awaySecondary: teams[away]!.secondary,
                                 pregameHomePercent: pregameHome, pregameAwayPercent: pregameHome.map { 100 - $0 },
                                 clock: clock)
        }
        let observed = now.addingTimeInterval(-30)
        let snapshot: WatchComplicationSnapshot
        switch stage {
        case "before":
            // Real: Patriots at Chargers, Sun Nov 29 5:20 PM PT, LAC 56% (production, Nov 16).
            var calendar = Calendar(identifier: .gregorian)
            calendar.timeZone = .current
            let start = calendar.nextDate(after: now.addingTimeInterval(86_400), matching: DateComponents(hour: 17, minute: 20, weekday: 1),
                                          matchingPolicy: .nextTime) ?? now.addingTimeInterval(3 * 86_400)
            let reading = WatchRectangularReading(
                version: 1, eventID: 21701, kind: .scheduledForecast,
                homeName: teams[2]!.name, awayName: teams[1]!.name, home: id(2), away: id(1),
                homePercent: 56, homeScore: nil, awayScore: nil, commenceTime: start,
                stateLabel: "Scheduled", observedAt: observed, scoreObservedAt: nil)
            snapshot = WatchComplicationSnapshot(eventID: 21701, title: "\(teams[2]!.name) win", detail: "56% · Scheduled",
                                                 observedAt: observed, savedAt: now, rectangularReading: reading,
                                                 matchup: facts(away: 1, home: 2))
        case "during":
            // Chargers at Ravens; example score, chance and clock.
            let reading = WatchRectangularReading(
                version: 1, eventID: 21702, kind: .liveForecast,
                homeName: teams[3]!.name, awayName: teams[2]!.name, home: id(3), away: id(2),
                homePercent: 74, homeScore: 17, awayScore: 10, commenceTime: nil,
                stateLabel: "Live", observedAt: observed, scoreObservedAt: observed)
            snapshot = WatchComplicationSnapshot(eventID: 21702, title: "\(teams[3]!.name) win", detail: "74% · Live",
                                                 observedAt: observed, savedAt: now, rectangularReading: reading,
                                                 matchup: facts(away: 2, home: 3, clock: "Q3 4:12"))
        case "after":
            // Real: Patriots 10 at Lions 35, final Nov 15; Lions 58% before the game.
            let reading = WatchRectangularReading(
                version: 1, eventID: 21703, kind: .finalResult,
                homeName: teams[4]!.name, awayName: teams[1]!.name, home: id(4), away: id(1),
                homePercent: nil, homeScore: 35, awayScore: 10, commenceTime: nil,
                stateLabel: "Final", observedAt: observed, scoreObservedAt: observed)
            snapshot = WatchComplicationSnapshot(eventID: 21703, title: "\(teams[4]!.name) won", detail: "Final · 35–10",
                                                 observedAt: observed, savedAt: now, rectangularReading: reading,
                                                 matchup: facts(away: 1, home: 4, pregameHome: 58))
        default:
            return nil
        }
        return WatchMatchupReading217.make(snapshot: snapshot, now: now) { teamID in
            teams[teamID].flatMap { crest($0.abbr, in: logos) }
        }
    }
}

private enum WKInterfaceDeviceScreen {
    static var width: CGFloat {
        #if os(watchOS)
        return WKInterfaceDevice.current().screenBounds.width
        #else
        return 0
        #endif
    }
}
#endif
