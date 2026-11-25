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
    private var isAX5: Bool { env["BAINLUCK_WATCH_MATCHUP_DT_217"] == "ax5" }

    private var slot: CGSize {
        switch stage {
        case "after-105-41":
            return CGSize(width: 171.5, height: 73)
        case "after-105-45":
            return CGSize(width: 185, height: 79)
        case "after-105-46":
            return CGSize(width: 193, height: 82)
        default:
            break
        }
        // The slot this screen's face would give the big rectangular complication:
        // 41 mm = 171.5×73 pt, 45 mm = 185×79 pt, 49 mm = 199×84.5 pt.
        let w = WKInterfaceDeviceScreen.width
        let h = WKInterfaceDeviceScreen.height
        if h >= 250 { return CGSize(width: 199, height: 84.5) }
        if w >= 204 { return CGSize(width: 193, height: 82) }
        if w >= 190 { return CGSize(width: 185, height: 79) }
        return CGSize(width: 171.5, height: 73)
    }

    var body: some View {
        ZStack(alignment: .top) {
            Color.black.ignoresSafeArea()
            if stage.hasPrefix("small-13430-") {
                tile
            } else {
                VStack(spacing: 6) {
                    Spacer(minLength: 0)
                    tile
                        .frame(width: slot.width, height: slot.height)
                    Spacer(minLength: 0)
                }
            }
        }
        .toolbar(.hidden, for: .navigationBar)
    }

    @ViewBuilder private var tile: some View {
        if stage.hasPrefix("small-13430-") {
            WatchSmallComplicationsSheet13430(page: stage, tinted: tinted, isAX5: isAX5)
        } else if let snapshot = Self.fallbackSnapshot(stage) {
            WatchSavedComplicationContent(snapshot: snapshot)
                .environment(\.widgetRenderingMode, tinted ? .accented : .fullColor)
                .environment(\.dynamicTypeSize, isAX5 ? .accessibility5 : .large)
        } else if let reading = Self.reading(stage, logos: env["BAINLUCK_WATCH_MATCHUP_LOGOS_217"]) {
            if tinted {
                WatchMatchupComplication217(reading: reading)
                    .environment(\.widgetRenderingMode, .accented)
                    .environment(\.dynamicTypeSize, isAX5 ? .accessibility5 : .large)
                    // The face's tint, as a tinted Modular face applies it.
                    .colorMultiply(Color(red: 1.0, green: 0.62, blue: 0.2))
            } else {
                WatchMatchupComplication217(reading: reading)
                    .environment(\.widgetRenderingMode, .fullColor)
                    .environment(\.dynamicTypeSize, isAX5 ? .accessibility5 : .large)
            }
        }
    }

    /// DEBUG-only fallback snapshots for #13144 (teams missing server short names).
    static func fallbackSnapshot(_ stage: String, now: Date = Date()) -> WatchComplicationSnapshot? {
        let observed = now.addingTimeInterval(-30)
        switch stage {
        case "fallback-longest":
            // Longest missing-short-name pair on Thu Nov 19 Sports list (56 chars + score = 64 chars).
            let reading = WatchRectangularReading(
                version: 1, eventID: 15351579, kind: .liveForecast,
                homeName: "Wake Forest Demon Deacons", awayName: "Appalachian St Mountaineers",
                home: nil, away: nil,
                homePercent: 64, homeScore: 71, awayScore: 68, commenceTime: nil,
                stateLabel: "Live", observedAt: observed, scoreObservedAt: observed)
            return WatchComplicationSnapshot(
                eventID: 15351579, title: "Wake Forest Demon Deacons win", detail: "64% · Live",
                observedAt: observed, savedAt: now, rectangularReading: reading)
        case "fallback-live":
            // Longest live neither-short-name pair on Thu Nov 19 Sports list (50 chars + score).
            let reading = WatchRectangularReading(
                version: 1, eventID: 15347849, kind: .liveForecast,
                homeName: "Cal State Fullerton Titans", awayName: "Weber State Wildcats",
                home: nil, away: nil,
                homePercent: 68, homeScore: 54, awayScore: 49, commenceTime: nil,
                stateLabel: "Live", observedAt: observed, scoreObservedAt: observed)
            return WatchComplicationSnapshot(
                eventID: 15347849, title: "Cal State Fullerton Titans win", detail: "68% · Live",
                observedAt: observed, savedAt: now, rectangularReading: reading)
        case "fallback-sac-stan":
            // Alex's reported #13144 game: Sacramento St (no short name) at Stanford (STAN).
            let stan = WatchCompactTeamIdentity(teamID: 24, abbreviation: "STAN")
            let reading = WatchRectangularReading(
                version: 1, eventID: 15351032, kind: .liveForecast,
                homeName: "Stanford Cardinal", awayName: "Sacramento St Hornets",
                home: stan, away: nil,
                homePercent: 71, homeScore: 51, awayScore: 42, commenceTime: nil,
                stateLabel: "Live", observedAt: observed, scoreObservedAt: observed)
            return WatchComplicationSnapshot(
                eventID: 15351032, title: "Stanford Cardinal win", detail: "71% · Live",
                observedAt: observed, savedAt: now, rectangularReading: reading)
        default:
            return nil
        }
    }

    private static func crest(_ abbr: String, in folder: String?) -> Data? {
        guard let folder else { return nil }
        return FileManager.default.contents(atPath: "\(folder)/\(abbr.lowercased()).png")
    }

    /// Builds a published snapshot exactly as the Watch app writes it and draws
    /// it through `WatchMatchupReading217.make`, the same path the complication uses.
    static func reading(_ stage: String, logos: String?, now: Date = Date()) -> WatchMatchupReading217? {
        let teams: [Int: (abbr: String, name: String, primary: String, secondary: String, logo: String)] = [
            1: ("NE", "New England Patriots", "#002a5c", "#c60c30", "ne"),
            2: ("LAC", "Los Angeles Chargers", "#0080c6", "#ffc20e", "lac"),
            3: ("BAL", "Baltimore Ravens", "#241773", "#9e7c0c", "bal"),
            4: ("DET", "Detroit Lions", "#0076b6", "#b0b7bc", "det"),
            8: ("DET", "Detroit Pistons", "#c8102e", "#1d42ba", "det_nba"),
            28: ("TOR", "Toronto Raptors", "#ce1141", "#000000", "tor"),
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
        case "matchup-special":
            // #13144: "&" (TA&M) and "-" (M-OH) short names now qualify for the Matchup look.
            let tam = WatchCompactTeamIdentity(teamID: 245, abbreviation: "TA&M")
            let moh = WatchCompactTeamIdentity(teamID: 193, abbreviation: "M-OH")
            let reading = WatchRectangularReading(
                version: 1, eventID: 21704, kind: .liveForecast,
                homeName: "Texas A&M Aggies", awayName: "Miami (OH) RedHawks", home: tam, away: moh,
                homePercent: 78, homeScore: 62, awayScore: 49, commenceTime: nil,
                stateLabel: "Live", observedAt: observed, scoreObservedAt: observed)
            snapshot = WatchComplicationSnapshot(
                eventID: 21704, title: "Texas A&M Aggies win", detail: "78% · Live",
                observedAt: observed, savedAt: now, rectangularReading: reading,
                matchup: WatchMatchupFacts217(
                    homePrimary: "#500000", homeSecondary: "#ffffff",
                    awayPrimary: "#c41230", awaySecondary: "#ffffff",
                    clock: "2H 8:14"))
        case "after-105-41", "after-105-45", "after-105-46":
            // #13386: 3-digit NBA final (TOR 105–102 DET, TOR pregame · Final) across 41/45/46 mm slots.
            let tor = WatchCompactTeamIdentity(teamID: 28, abbreviation: "TOR")
            let det = WatchCompactTeamIdentity(teamID: 8, abbreviation: "DET")
            let reading = WatchRectangularReading(
                version: 1, eventID: 21705, kind: .finalResult,
                homeName: "Detroit Pistons", awayName: "Toronto Raptors", home: det, away: tor,
                homePercent: nil, homeScore: 102, awayScore: 105, commenceTime: nil,
                stateLabel: "Final", observedAt: observed, scoreObservedAt: observed)
            snapshot = WatchComplicationSnapshot(
                eventID: 21705, title: "Toronto Raptors won", detail: "Final · 105–102",
                observedAt: observed, savedAt: now, rectangularReading: reading,
                matchup: WatchMatchupFacts217(
                    homePrimary: "#c8102e", homeSecondary: "#1d42ba",
                    awayPrimary: "#ce1141", awaySecondary: "#000000",
                    pregameHomePercent: 71, pregameAwayPercent: 29))
        default:
            return nil
        }
        return WatchMatchupReading217.make(snapshot: snapshot, now: now) { teamID in
            teams[teamID].flatMap { crest($0.logo, in: logos) }
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

    static var height: CGFloat {
        #if os(watchOS)
        return WKInterfaceDevice.current().screenBounds.height
        #else
        return 0
        #endif
    }
}

/// #13430 DEBUG sheet rendered on real 41/45/46/49 mm Watch simulators, pairing
/// `WatchSavedCornerComplicationContent` (with its curved label readout) and
/// `WatchSavedCircularComplicationContent` at exact measured face slot sizes.
private struct WatchSmallComplicationsSheet13430: View {
    let page: String
    let tinted: Bool
    let isAX5: Bool

    private var watchSizeLabel: String {
        let w = WKInterfaceDeviceScreen.width
        let h = WKInterfaceDeviceScreen.height
        if h >= 250 { return "49 mm" }
        if w >= 204 { return "46 mm" }
        if w >= 190 { return "45 mm" }
        return "41 mm"
    }

    private var cornerSize: CGFloat {
        let w = WKInterfaceDeviceScreen.width
        let h = WKInterfaceDeviceScreen.height
        if h >= 250 { return 41 }
        if w >= 204 { return 40 }
        if w >= 190 { return 38 }
        return 34
    }

    private var circularSize: CGFloat {
        let w = WKInterfaceDeviceScreen.width
        let h = WKInterfaceDeviceScreen.height
        if h >= 250 { return 48 }
        if w >= 204 { return 47 }
        if w >= 190 { return 45 }
        return 42
    }

    private var now: Date { Date(timeIntervalSinceReferenceDate: 785_500_000) }

    private var rows: [(label: String, snapshot: WatchComplicationSnapshot?)] {
        let obs = now.addingTimeInterval(-30)
        let ne = WatchCompactTeamIdentity(teamID: 1, abbreviation: "NE")
        let lac = WatchCompactTeamIdentity(teamID: 2, abbreviation: "LAC")
        let bal = WatchCompactTeamIdentity(teamID: 3, abbreviation: "BAL")
        let det = WatchCompactTeamIdentity(teamID: 4, abbreviation: "DET")

        let liveReading = WatchRectangularReading(
            version: 1, eventID: 134301, kind: .liveForecast,
            homeName: "Baltimore Ravens", awayName: "Los Angeles Chargers", home: bal, away: lac,
            homePercent: 74, homeScore: 17, awayScore: 10, commenceTime: nil,
            stateLabel: "Live", observedAt: obs, scoreObservedAt: obs
        )
        let liveSnap = WatchComplicationSnapshot(
            eventID: 134301, title: "Baltimore Ravens win", detail: "74% · Live",
            observedAt: obs, savedAt: now, rectangularReading: liveReading
        )

        let start = now.addingTimeInterval(3 * 86_400)
        let schedReading = WatchRectangularReading(
            version: 1, eventID: 134302, kind: .scheduledForecast,
            homeName: "Los Angeles Chargers", awayName: "New England Patriots", home: lac, away: ne,
            homePercent: 56, homeScore: nil, awayScore: nil, commenceTime: start,
            stateLabel: "Scheduled", observedAt: obs, scoreObservedAt: nil
        )
        let schedSnap = WatchComplicationSnapshot(
            eventID: 134302, title: "Los Angeles Chargers win", detail: "56% · Scheduled",
            observedAt: obs, savedAt: now, rectangularReading: schedReading
        )

        let finalReading = WatchRectangularReading(
            version: 1, eventID: 134303, kind: .finalResult,
            homeName: "Detroit Lions", awayName: "New England Patriots", home: det, away: ne,
            homePercent: nil, homeScore: 35, awayScore: 10, commenceTime: nil,
            stateLabel: "Final", observedAt: obs, scoreObservedAt: obs
        )
        let finalSnap = WatchComplicationSnapshot(
            eventID: 134303, title: "Detroit Lions won", detail: "Final · 35–10",
            observedAt: obs, savedAt: now, rectangularReading: finalReading
        )

        let marketSnap = WatchComplicationProjection.futureSnapshot(
            marketID: 9303,
            marketTitle: "2028 Democratic Nominee",
            outcomeName: "Newsom",
            probability: 0.23,
            observedAt: obs,
            savedAt: now
        )

        if page.hasSuffix("-b") {
            return [("Market", marketSnap), ("Fallback", nil)]
        }
        return [("Live", liveSnap), ("Pregame", schedSnap), ("Final", finalSnap)]
    }

    var body: some View {
        VStack(spacing: 4) {
            HStack(spacing: 4) {
                Text("\(watchSizeLabel) · \(tinted ? "Tinted" : "Full")\(isAX5 ? " · AX5" : "")")
                    .font(.system(size: 9.5, weight: .bold))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.65)
                Spacer(minLength: 2)
                Text("Corner / Circle")
                    .font(.system(size: 8.5, weight: .semibold))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.65)
            }
            .padding(.horizontal, 4)

            ForEach(rows, id: \.label) { item in
                let smallModel = item.snapshot?.smallSlotModel(now: now)
                HStack(spacing: 8) {
                    Text(item.label)
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundStyle(.secondary)
                        .frame(width: 50, alignment: .leading)
                        .lineLimit(1)
                        .minimumScaleFactor(0.7)

                    VStack(spacing: 1) {
                        if let cornerLabel = smallModel?.cornerLabel {
                            Text(cornerLabel)
                                .font(.system(size: 8.5, weight: .bold, design: .rounded))
                                .foregroundStyle(.secondary)
                                .lineLimit(1)
                                .minimumScaleFactor(0.6)
                        }
                        WatchSavedCornerComplicationContent(snapshot: item.snapshot, now: now)
                            .environment(\.showsWidgetLabel, true)
                            .environment(\.dynamicTypeSize, isAX5 ? .accessibility5 : .large)
                            .frame(width: cornerSize, height: cornerSize * 0.72)
                    }
                    .frame(width: cornerSize + 8)

                    WatchSavedCircularComplicationContent(snapshot: item.snapshot, now: now)
                        .environment(\.dynamicTypeSize, isAX5 ? .accessibility5 : .large)
                        .frame(width: circularSize, height: circularSize)
                        .background(Circle().fill(Color.white.opacity(0.08)))
                        .clipShape(Circle())
                }
                .padding(.vertical, 1)
            }
        }
        .padding(.horizontal, 4)
        .padding(.top, 2)
        .environment(\.widgetRenderingMode, tinted ? .accented : .fullColor)
        .tint(tinted ? Color(red: 1.0, green: 0.62, blue: 0.2) : .cyan)
        .colorMultiply(tinted ? Color(red: 1.0, green: 0.62, blue: 0.2) : .white)
    }
}
#endif
