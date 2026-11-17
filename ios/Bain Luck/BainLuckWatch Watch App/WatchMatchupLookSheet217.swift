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

    static func reading(_ stage: String, logos: String?) -> WatchMatchupReading217? {
        typealias R = WatchMatchupReading217
        func side(_ abbr: String, _ primary: String, _ secondary: String, score: Int? = nil, winner: Bool = false) -> R.Side {
            R.Side(abbreviation: abbr, inkHex: R.ink(primary: primary, secondary: secondary),
                   crestPNG: crest(abbr, in: logos), score: score, isWinner: winner)
        }
        switch stage {
        case "before":
            // Real: Patriots at Chargers, Sun Nov 29 5:20 PM PT, LAC 56% (production, Nov 16).
            return R(stage: .before,
                     away: side("NE", "#002a5c", "#c60c30"), home: side("LAC", "#0080c6", "#ffc20e"),
                     bigText: "56%", bigIsHome: true, bigLabel: "LAC to win", caption: "Sun 5:20 PM",
                     accessibilityText: "Patriots at Chargers. Chargers 56% to win. Sunday 5:20 PM.")
        case "during":
            // Tonight's game, Chargers at Ravens; example score and chance until kickoff.
            return R(stage: .during,
                     away: side("LAC", "#0080c6", "#ffc20e", score: 10), home: side("BAL", "#29126f", "#000000", score: 17),
                     bigText: "74%", bigIsHome: true, bigLabel: "Now · BAL", caption: "Q3 4:12",
                     accessibilityText: "Chargers 10, Ravens 17, third quarter 4:12. Ravens 74% now.")
        case "after":
            // Real: Patriots 10 at Lions 35, final Nov 15; Lions 58% before the game.
            return R(stage: .after,
                     away: side("NE", "#002a5c", "#c60c30", score: 10), home: side("DET", "#0076b6", "#b0b7bc", score: 35, winner: true),
                     bigText: "58%", bigIsHome: true, bigLabel: "Pregame · DET", caption: "Final",
                     accessibilityText: "Final. Lions 35, Patriots 10. Lions were 58% before the game.")
        default:
            return nil
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
