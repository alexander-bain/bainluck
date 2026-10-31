import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the rugby-match page as a composition of the accepted leaves
/// before, during and after the match.
///
/// The view is SwiftUI and is not rasterised here. What is asserted is the
/// composition the page defers to: the phase gates and the leaves each phase
/// mounts with which exact owner input; the history's own resolved readouts,
/// exact-minute inspection and owner runs; the compact context's resolved
/// slots and hand-offs; the final story's chances and separately reported
/// actual; every original's identity, verbatim rules and result; the reachable
/// text and every hand-off payload of every phase; held omission and exact
/// restoration; the full-size readers; once-only holds; and the arrangement
/// candidates. Nothing here claims a compile, a rendered fit, a pinned header,
/// VoiceOver, a native runtime or a live rugby route.
///
/// ARCHIVED, from `rugbyMatch.json` (sha256 39c60a02…f403f754): event
/// KXSIXNATIONSMATCH-26MAR14ENGFRA, France vs England, Six Nations, Mar 14 2026,
/// listed 20:10Z (1773519000) — a schedule marker, not a verified kickoff; all
/// 347 admitted positive-volume minute closes (France 107, England 201, Draw 39;
/// 57/120/17 strictly before the listed start) as (minute end, close in cents,
/// volume); the three originals' identities, venue outcome names (the venue's
/// "Tie"), titles, primary and secondary rules (verbatim) and contract results;
/// the ESPN header final France 48–46 England (event 602516); the official-report
/// fetch status 403; the withheld kickoff, halftime and score timeline (ESPN
/// commentary ends 41–46); and France's 8:53 PM minute candle (open 63, high 66,
/// low 2, close 2 cents).
///
/// CONSTRUCTED: every display string, GMT clock word (from each close's own
/// minute end), figure, label, tint, scope, id, action id, observation key,
/// heading, Info and source sentence, the history domain (minutes from the listed
/// start), the owner's runs (adjacent traded minutes), windows, readout intents
/// and held inspections, the story and its words, the recorded Details context,
/// and every rejected, withdrawn, omitted, foreign, duplicate and bad-payload
/// case. The DURING page is a constructed snapshot through the minute ending
/// 8:54 PM GMT, labelled constructed on the page: the capture proves no live
/// state, score or period timing.
///
/// PHASE-APPROPRIATE OWNER TEXT AND PAYLOADS. The page shows the owner's text
/// verbatim and hands back the owner's exact original and observation keys, so
/// each constructed owner supplies only what it could know: before the match no
/// later quote, score, lowest close or result; during the match no final report,
/// score or result. The reachable-text guard and the payload guard below check
/// every phase, with final positive controls and a deliberately bad payload.
@MainActor
final class RugbyMatchEventPagePresentation10868Tests: XCTestCase {
    private typealias Tests = RugbyMatchEventPagePresentation10868Tests
    private typealias Originals = OriginalMarketDetails9483
    private typealias Close = (t: Int, cents: Int, volume: Int)

    // MARK: Retained (ARCHIVED)

    private static let listedStart = 1773519000
    /// CONSTRUCTED: the during snapshot's last admitted minute end.
    private static let duringCut = 1773521640
    private static let franceLow = 1773521580
    private static let eventTicker = "KXSIXNATIONSMATCH-26MAR14ENGFRA"
    private static let espnURL = "https://www.espn.com/rugby/matchstats/_/gameId/602516/league/180659"
    /// France's 8:53 PM minute candle in cents: the admitted figure is its close.
    private static let lowCandle = (open: 63, high: 66, low: 2, close: 2)

    private static let franceCloses: [Close] = [
        (1773364620, 83, 10), (1773371580, 83, 1), (1773372660, 83, 5), (1773419280, 83, 61), (1773420000, 83, 2),
        (1773421200, 82, 5), (1773423120, 82, 5), (1773435960, 83, 12), (1773450840, 83, 11), (1773460500, 81, 1),
        (1773462060, 82, 1), (1773463860, 83, 11), (1773468660, 83, 13), (1773486780, 82, 1), (1773489180, 82, 200),
        (1773490380, 82, 6), (1773490800, 82, 1), (1773493260, 82, 18), (1773494400, 82, 2), (1773494520, 82, 273),
        (1773494820, 82, 5), (1773494880, 82, 14), (1773496140, 82, 24), (1773499560, 82, 12), (1773500340, 82, 6),
        (1773500940, 82, 30), (1773503280, 87, 80), (1773504780, 82, 50), (1773505320, 78, 6), (1773505860, 80, 15),
        (1773506100, 80, 3), (1773506160, 81, 15), (1773506340, 78, 16), (1773506400, 78, 5), (1773506460, 78, 5),
        (1773506580, 80, 30), (1773507000, 81, 121), (1773507240, 82, 30), (1773508380, 79, 5), (1773509640, 79, 5),
        (1773510660, 82, 9), (1773510720, 79, 7), (1773511800, 82, 27), (1773511860, 82, 9), (1773512880, 82, 3),
        (1773512940, 84, 1178), (1773514140, 81, 6), (1773514380, 79, 44), (1773514800, 77, 100),
        (1773515520, 81, 24), (1773515760, 78, 20), (1773517140, 83, 17), (1773517200, 83, 116),
        (1773517260, 83, 156), (1773517320, 83, 78), (1773518160, 83, 1190), (1773518880, 81, 6),
        (1773519120, 76, 12), (1773519240, 83, 23), (1773519300, 83, 36), (1773519600, 87, 10), (1773519660, 88, 56),
        (1773519900, 73, 57), (1773520080, 89, 5), (1773520320, 90, 55), (1773520380, 90, 27), (1773520560, 83, 3),
        (1773520620, 74, 16), (1773520680, 80, 9), (1773520920, 71, 60), (1773520980, 69, 47), (1773521580, 2, 173),
        (1773521640, 48, 3), (1773521700, 44, 8), (1773521820, 55, 35), (1773521940, 59, 96), (1773522060, 86, 1),
        (1773522240, 70, 15), (1773522360, 69, 20), (1773522420, 73, 59), (1773523020, 71, 34), (1773523200, 89, 27),
        (1773523260, 89, 27), (1773523320, 82, 8), (1773523560, 90, 65), (1773523620, 85, 9), (1773524220, 88, 1),
        (1773524640, 57, 51), (1773524700, 84, 11), (1773524760, 84, 97), (1773524820, 72, 149),
        (1773524880, 71, 277), (1773525120, 79, 10), (1773525180, 63, 5), (1773525240, 48, 5), (1773525300, 48, 11),
        (1773525480, 64, 17), (1773525540, 6, 9), (1773525600, 72, 1022), (1773525660, 6, 143), (1773525720, 6, 78),
        (1773525780, 84, 115), (1773525840, 61, 35), (1773525900, 99, 2931), (1773525960, 99, 60),
        (1773526020, 99, 78), (1773526260, 99, 20),
    ]

    private static let englandCloses: [Close] = [
        (1773355740, 18, 105), (1773360420, 18, 50), (1773366960, 18, 5), (1773368880, 18, 2), (1773378180, 18, 25),
        (1773384300, 18, 5), (1773388260, 18, 10), (1773396060, 18, 10), (1773402300, 18, 25), (1773402720, 18, 10),
        (1773403440, 18, 15), (1773406980, 16, 27), (1773408060, 18, 150), (1773411420, 18, 15), (1773412740, 20, 47),
        (1773415980, 19, 348), (1773421080, 19, 47), (1773426060, 19, 184), (1773429660, 19, 149),
        (1773432900, 19, 49), (1773433920, 19, 80), (1773437940, 19, 4), (1773438720, 17, 250), (1773440220, 19, 100),
        (1773441840, 17, 250), (1773442500, 19, 45), (1773443100, 19, 124), (1773443400, 19, 95),
        (1773443580, 19, 71), (1773443820, 19, 9), (1773445680, 19, 9), (1773446160, 19, 142), (1773447480, 19, 49),
        (1773448020, 19, 383), (1773448200, 19, 49), (1773448680, 18, 101), (1773451920, 18, 10),
        (1773456840, 19, 132), (1773457020, 15, 383), (1773457080, 18, 36), (1773458160, 19, 511),
        (1773465840, 17, 21), (1773469260, 20, 25), (1773485520, 19, 95), (1773486900, 18, 20), (1773487020, 19, 95),
        (1773488580, 18, 3), (1773494640, 18, 31), (1773494820, 18, 25), (1773495120, 19, 126), (1773495300, 19, 139),
        (1773495360, 19, 33), (1773497280, 19, 128), (1773498120, 19, 24), (1773500040, 16, 12), (1773501240, 19, 99),
        (1773502620, 20, 48), (1773502680, 20, 23), (1773502920, 20, 14), (1773503340, 20, 94), (1773503460, 21, 114),
        (1773503760, 20, 45), (1773504180, 20, 90), (1773504720, 20, 47), (1773504840, 20, 9), (1773505200, 20, 4),
        (1773505320, 20, 473), (1773505860, 18, 15), (1773506160, 17, 8), (1773506340, 19, 5), (1773506460, 19, 41),
        (1773506520, 19, 30), (1773506580, 19, 30), (1773506820, 20, 11), (1773507000, 21, 22), (1773507180, 21, 120),
        (1773507780, 19, 181), (1773507900, 19, 76), (1773508140, 21, 54), (1773508260, 21, 45), (1773508320, 19, 14),
        (1773508680, 21, 45), (1773508860, 20, 10), (1773509040, 21, 45), (1773509520, 22, 265),
        (1773509580, 19, 250), (1773510720, 21, 108), (1773511500, 21, 224), (1773511680, 21, 112),
        (1773511860, 21, 45), (1773511980, 21, 326), (1773512160, 21, 180), (1773512280, 21, 90),
        (1773512400, 21, 356), (1773512640, 21, 22), (1773513180, 20, 681), (1773513240, 21, 52),
        (1773513300, 21, 225), (1773513420, 21, 38), (1773513480, 19, 248), (1773513600, 21, 136),
        (1773513660, 19, 768), (1773513720, 21, 22), (1773514200, 22, 150), (1773515460, 24, 74),
        (1773515520, 19, 24), (1773515760, 23, 20), (1773516240, 21, 45), (1773516900, 21, 221), (1773516960, 21, 83),
        (1773517140, 18, 16), (1773517200, 21, 21), (1773517560, 21, 22), (1773517980, 20, 9), (1773518100, 20, 11),
        (1773518340, 20, 3), (1773518640, 20, 51), (1773518700, 21, 101), (1773518820, 22, 89), (1773518940, 21, 66),
        (1773519120, 22, 57), (1773519180, 43, 66), (1773519240, 19, 194), (1773519300, 18, 36), (1773519360, 41, 7),
        (1773519420, 33, 43), (1773519540, 2, 259), (1773519720, 41, 23), (1773519780, 36, 121),
        (1773519840, 27, 149), (1773519900, 29, 80), (1773519960, 19, 88), (1773520260, 32, 15), (1773520320, 24, 42),
        (1773520500, 26, 663), (1773520560, 25, 10), (1773520620, 27, 16), (1773520680, 22, 216),
        (1773520740, 22, 21), (1773520860, 22, 298), (1773520920, 38, 60), (1773520980, 29, 262),
        (1773521100, 35, 103), (1773521160, 29, 15), (1773521280, 58, 3), (1773521340, 47, 1), (1773521460, 47, 35),
        (1773521520, 49, 171), (1773521580, 38, 39), (1773521640, 60, 61), (1773521700, 57, 129),
        (1773521760, 57, 917), (1773521820, 48, 92), (1773521880, 52, 24), (1773521940, 51, 92),
        (1773522060, 39, 122), (1773522120, 33, 21), (1773522180, 34, 628), (1773522240, 33, 15),
        (1773522300, 34, 71), (1773522360, 34, 294), (1773522420, 29, 57), (1773522540, 34, 56),
        (1773522600, 34, 155), (1773522720, 34, 281), (1773522840, 34, 29), (1773523080, 26, 198),
        (1773523200, 25, 271), (1773523260, 25, 68), (1773523680, 19, 284), (1773523740, 25, 51),
        (1773523800, 45, 551), (1773523860, 45, 10), (1773523920, 60, 33), (1773524040, 59, 32),
        (1773524100, 44, 255), (1773524160, 65, 64), (1773524340, 67, 14), (1773524640, 48, 20), (1773524700, 22, 6),
        (1773524760, 29, 10), (1773524820, 32, 205), (1773524880, 32, 330), (1773524940, 30, 105),
        (1773525000, 20, 10), (1773525060, 27, 88), (1773525120, 41, 97), (1773525180, 54, 171), (1773525240, 71, 62),
        (1773525300, 66, 196), (1773525360, 39, 154), (1773525420, 39, 84), (1773525480, 60, 118),
        (1773525540, 56, 94), (1773525600, 71, 598), (1773525660, 55, 979), (1773525720, 48, 76),
        (1773525780, 34, 66), (1773525840, 71, 138), (1773525900, 1, 1382), (1773525960, 1, 100),
    ]

    private static let drawCloses: [Close] = [
        (1773384000, 4, 83), (1773420840, 2, 3), (1773443700, 4, 166), (1773464220, 4, 585), (1773464280, 4, 585),
        (1773465780, 3, 50), (1773495240, 4, 302), (1773503220, 4, 8), (1773504480, 6, 464), (1773505860, 4, 15),
        (1773506160, 4, 8), (1773506280, 5, 100), (1773506520, 3, 48), (1773515520, 2, 24), (1773515760, 2, 20),
        (1773516720, 4, 250), (1773517140, 2, 16), (1773519120, 1, 12), (1773519240, 1, 23), (1773519300, 1, 36),
        (1773519900, 1, 55), (1773520320, 1, 23), (1773520620, 1, 16), (1773520920, 1, 60), (1773520980, 2, 14),
        (1773521580, 1, 27), (1773521820, 1, 35), (1773521940, 2, 6), (1773522000, 2, 1), (1773522240, 1, 15),
        (1773522360, 1, 20), (1773522420, 1, 57), (1773524640, 1, 20), (1773524700, 1, 6), (1773524760, 1, 4),
        (1773524820, 1, 149), (1773524880, 1, 352), (1773525120, 1, 3), (1773525420, 1, 178),
    ]

    private static let francePrimary = "If France is the winner in the France vs England professional Six Nations Rugby match originally scheduled for Mar 14, 2026, then the market resolves to Yes."
    private static let englandPrimary = "If England is the winner in the France vs England professional Six Nations Rugby match originally scheduled for Mar 14, 2026, then the market resolves to Yes."
    private static let drawPrimary = "If Tie is the result in the France vs England professional Six Nations Rugby match originally scheduled for Mar 14, 2026, then the market resolves to Yes."
    private static let secondaryRules = "The following market refers to the France vs England professional Six Nations Rugby rugby match originally scheduled for Mar 14, 2026. If this game is postponed or delayed, the market will remain open and close after the rescheduled game has finished (within two weeks). If the cancelled game is not played or is rescheduled further than two weeks out, the market will resolve to a fair price for each team in accordance with the rules."
    private static let originalTitle = "France vs England Winner?"

    /// CONSTRUCTED GMT words for every minute a reading names (Mar 14 2026 is before UK summer time).
    private static let clocks: [Int: String] = [
        1773517140: "Mar 14, 7:39 PM GMT",
        1773518880: "Mar 14, 8:08 PM GMT",
        1773518940: "Mar 14, 8:09 PM GMT",
        1773519000: "Mar 14, 8:10 PM GMT",
        1773521580: "Mar 14, 8:53 PM GMT",
        1773521640: "Mar 14, 8:54 PM GMT",
        1773525420: "Mar 14, 9:57 PM GMT",
        1773525900: "Mar 14, 10:05 PM GMT",
        1773525960: "Mar 14, 10:06 PM GMT",
        1773526260: "Mar 14, 10:11 PM GMT",
    ]

    private struct Outcome {
        let key: String
        let ticker: String
        let name: String
        let label: String
        /// The venue's own outcome name, kept on the exact original.
        let venueName: String
        let shape: FieldHistoryShape10868
        let keyShape: FieldHeadlineKeyShape10868
        let tint: Color
        let closes: [Close]
        /// The owner's elected last close strictly before the listed start.
        let baseline: Int
        /// The owner's latest admitted close at the during cut.
        let duringRecorded: Int
        /// The owner's last admitted close.
        let last: Int
        /// The contract's own result.
        let won: Bool
        /// The reported final for this outcome; nil: no score of its own.
        let score: String?
        let primary: String
    }

    private static let france = Outcome(
        key: "FRA", ticker: "KXSIXNATIONSMATCH-26MAR14ENGFRA-FRA", name: "France", label: "France to win",
        venueName: "France", shape: .circle, keyShape: .circle, tint: Color(red: 0.15, green: 0.39, blue: 0.92),
        closes: franceCloses, baseline: 1773518880, duringRecorded: 1773521640, last: 1773526260,
        won: true, score: "48", primary: francePrimary)
    private static let england = Outcome(
        key: "ENG", ticker: "KXSIXNATIONSMATCH-26MAR14ENGFRA-ENG", name: "England", label: "England to win",
        venueName: "England", shape: .diamond, keyShape: .diamond, tint: Color(red: 0.05, green: 0.58, blue: 0.53),
        closes: englandCloses, baseline: 1773518940, duringRecorded: 1773521640, last: 1773525960,
        won: false, score: "46", primary: englandPrimary)
    private static let draw = Outcome(
        key: "TIE", ticker: "KXSIXNATIONSMATCH-26MAR14ENGFRA-TIE", name: "Draw", label: "Draw",
        venueName: "Tie", shape: .square, keyShape: .square, tint: Color(red: 0.42, green: 0.44, blue: 0.50),
        closes: drawCloses, baseline: 1773517140, duringRecorded: 1773521580, last: 1773525420,
        won: false, score: nil, primary: drawPrimary)
    private static let outcomes = [france, england, draw]

    private static let scope = "constructed:rugby:602516"
    private static let originalsScope = "constructed:rugby:602516:originals"

    // MARK: Fixture helpers

    private static func close(_ outcome: Outcome, _ t: Int) -> Close? { outcome.closes.first { $0.t == t } }

    private static func probability(_ close: Close) -> Double { Double(close.cents) / 100 }

    private static func figure(_ close: Close) -> String { "\(close.cents)%" }

    private static func provenance(_ t: Int) -> String { "Minute ending \(clocks[t]!) · Kalshi" }

    private static func key(_ outcome: Outcome, _ t: Int) -> String { "constructed:observation:\(outcome.key):\(t)" }

    private static func pointID(_ outcome: Outcome, _ t: Int) -> String { "\(outcome.key).\(t)" }

    private static func seriesID(_ outcome: Outcome) -> String { "series.\(outcome.key)" }

    private static func x(_ t: Int) -> Double { Double(t - listedStart) / 60 }

    private static func ref(_ outcome: Outcome, scope: String = Tests.scope) -> FieldChooserOriginalRef10868 {
        FieldChooserOriginalRef10868(scope: scope, source: "kalshi", marketID: outcome.ticker, outcomeID: "yes")
    }

    /// The minute end an observation key names, by the fixture's own construction.
    private static func observationTime(_ observation: String) -> Int? {
        for outcome in outcomes {
            if let close = outcome.closes.first(where: { key(outcome, $0.t) == observation }) { return close.t }
        }
        return nil
    }

    private static func admits(_ phase: RugbyMatchEventPagePhase10868, _ t: Int) -> Bool {
        switch phase {
        case .before: return t < listedStart
        case .during: return t <= duringCut
        case .final: return true
        }
    }

    private enum Window { case match, all }

    private static func defaultWindow(_ phase: RugbyMatchEventPagePhase10868) -> Window { phase == .before ? .all : .match }

    private static func inWindow(_ window: Window, _ t: Int) -> Bool { window == .all || t >= listedStart - 3600 }

    /// The owner's runs: admitted closes in the window, split wherever the next
    /// traded minute is not the adjacent one.
    private static func runs(_ outcome: Outcome, phase: RugbyMatchEventPagePhase10868, window: Window,
                             idPrefix: String = "", omitting: Int? = nil) -> [FieldHistoryRun10868] {
        let shown = outcome.closes.filter { admits(phase, $0.t) && inWindow(window, $0.t) && $0.t != omitting }
        var groups: [[Close]] = []
        for close in shown {
            if let previous = groups.last?.last, close.t - previous.t == 60 {
                groups[groups.count - 1].append(close)
            } else {
                groups.append([close])
            }
        }
        return groups.map { group in
            FieldHistoryRun10868(id: "\(idPrefix)run.\(outcome.key).\(group[0].t)", points: group.map { close in
                FieldHistoryPoint10868(id: idPrefix + pointID(outcome, close.t), x: x(close.t), probability: probability(close),
                                       style: close.t < listedStart ? .hollow : .filled)
            })
        }
    }

    private static func recordedMinute(_ outcome: Outcome, _ phase: RugbyMatchEventPagePhase10868) -> Int? {
        switch phase {
        case .before: return nil
        case .during: return outcome.duringRecorded
        case .final: return outcome.last
        }
    }

    private static func beforeReading(_ outcome: Outcome) -> FieldChooserReading10868 {
        let close = Self.close(outcome, outcome.baseline)!
        return FieldChooserReading10868(label: "Before match", value: .recorded(text: figure(close), detail: provenance(close.t)))
    }

    private static func recordedReading(_ outcome: Outcome, _ t: Int) -> FieldChooserReading10868 {
        let close = Self.close(outcome, t)!
        return FieldChooserReading10868(label: "Last recorded trade", value: .recorded(text: figure(close), detail: provenance(t)))
    }

    private static func observation(_ outcome: Outcome, _ reading: FieldChooserReading10868, _ t: Int) -> FieldMovementObservation10868 {
        FieldMovementObservation10868(probability: probability(close(outcome, t)!), reading: reading)
    }

    // MARK: Headline

    private static func headlineRecord(_ outcome: Outcome, _ phase: RugbyMatchEventPagePhase10868,
                                       recorded: Int? = nil) -> FieldChooserOriginal10868 {
        let plan: FieldChooserDisplayPlan10868
        if phase == .during, let t = recorded ?? recordedMinute(outcome, .during) {
            plan = .comparison(before: beforeReading(outcome), later: recordedReading(outcome, t))
        } else {
            plan = .single(beforeReading(outcome))
        }
        return FieldChooserOriginal10868(
            ref: ref(outcome), name: outcome.name, plan: plan,
            preview: FieldChooserPreview10868(history: nil, absence: "History in the chart"),
            movement: nil, clock: nil, result: nil, browseStatus: "Original market", accent: outcome.tint)
    }

    private static func finish(_ outcome: Outcome) -> FieldFinishPlace10868 {
        let value: FieldChooserValue10868 = outcome.score.map {
            FieldChooserValue10868.recorded(text: $0, detail: "Reported final · ESPN match header")
        } ?? FieldChooserValue10868.missing("No draw")
        return FieldFinishPlace10868(ref: ref(outcome), reading: FieldChooserReading10868(label: "Final score", value: value))
    }

    private static func headlineState(_ phase: RugbyMatchEventPagePhase10868) -> FieldHeadlineState10868? {
        switch phase {
        case .before:
            return FieldHeadlineState10868(
                figure: "8:10 PM", unit: "GMT", caption: "Listed start · a schedule marker, not a verified kickoff",
                detail: "Saturday, Mar 14, 2026",
                spoken: "Listed start 8:10 PM GMT, Saturday, Mar 14, 2026. A schedule marker, not a verified kickoff.",
                progress: nil)
        case .during:
            return nil
        case .final:
            return FieldHeadlineState10868(
                figure: "48–46", unit: nil, caption: "Reported final", detail: "ESPN match header",
                spoken: "Reported final, France 48, England 46. ESPN match header.", progress: nil)
        }
    }

    private static func eyebrow(_ phase: RugbyMatchEventPagePhase10868) -> String {
        switch phase {
        case .before: return "SIX NATIONS · BEFORE MATCH · MAR 14"
        case .during: return "SIX NATIONS · CONSTRUCTED DURING-MATCH EXAMPLE · MAR 14"
        case .final: return "SIX NATIONS · FINAL · MAR 14"
        }
    }

    private static func headline(_ phase: RugbyMatchEventPagePhase10868, outcomes: [Outcome] = Tests.outcomes,
                                 recorded: [String: Int] = [:]) -> FieldHeadlineInput10868 {
        FieldHeadlineInput10868(
            scope: scope,
            catalogue: outcomes.map { headlineRecord($0, phase, recorded: recorded[$0.key]) },
            displayed: outcomes.map { FieldHeadlineSlot10868(ref: ref($0), name: $0.name, compactName: nil, keyShape: $0.keyShape) },
            pairs: outcomes.map { outcome -> FieldMovementPair10868 in
                let later = phase == .during ? (recorded[outcome.key] ?? recordedMinute(outcome, .during)) : nil
                return FieldMovementPair10868(
                    ref: ref(outcome),
                    before: observation(outcome, beforeReading(outcome), outcome.baseline),
                    later: later.map { observation(outcome, recordedReading(outcome, $0), $0) },
                    movement: nil,
                    observation: later.map { key(outcome, $0) })
            },
            finishes: phase == .final ? outcomes.map(finish) : [],
            state: headlineState(phase),
            phase: RugbyMatchEventPageModel10868.leafPhase(phase),
            copy: FieldHeadlineCopy10868(
                eyebrow: eyebrow(phase), title: "France vs England", graphicLabel: "Team and draw win chances",
                beforeLabel: "Before match", recordedLabel: "Last recorded trade", beforeUnavailable: "Unavailable",
                recordedUnavailable: "No trade recorded", finishLabel: "Final score",
                finishUnavailable: "Final score not confirmed", empty: "No outcomes in this update",
                aboutLabel: "About this rugby match", aboutHint: "Opens timing, sources and the original rules",
                openHint: "Opens this exact original"),
            unavailableWords: "Outcome unavailable in this update")
    }

    // MARK: History

    private enum Inspect: Equatable {
        /// The owner's held minute: each original's own exact close, or words.
        case minute(Int)
        /// The held minute with one original's close withdrawn by the owner.
        case withdrawn(Int, String)

        var minute: Int {
            switch self {
            case .minute(let t), .withdrawn(let t, _): t
            }
        }
    }

    private static func action(_ id: String, _ label: String, spoken: String? = nil) -> FieldHistoryAction10868 {
        FieldHistoryAction10868(id: id, label: label, spokenLabel: spoken, isAvailable: true)
    }

    private static func domain(_ phase: RugbyMatchEventPagePhase10868, _ window: Window) -> FieldHistoryDomain10868 {
        let lower: Double = window == .all ? -2760 : -60
        let upper: Double
        switch phase {
        case .before: upper = 0
        case .during: upper = x(duringCut)
        case .final: upper = 122
        }
        return FieldHistoryDomain10868(lower: lower, upper: upper)
    }

    private static func xTicks(_ phase: RugbyMatchEventPagePhase10868, _ window: Window) -> [FieldHistoryTick10868] {
        if window == .all {
            return [FieldHistoryTick10868(value: -2760, lines: ["Mar 12", "10:10 PM"]),
                    FieldHistoryTick10868(value: 0, lines: ["Mar 14", "8:10 PM"])]
        }
        var ticks = [FieldHistoryTick10868(value: -60, lines: ["7:10 PM"]), FieldHistoryTick10868(value: 0, lines: ["8:10 PM"])]
        if phase == .final {
            ticks += [FieldHistoryTick10868(value: 60, lines: ["9:10 PM"]), FieldHistoryTick10868(value: 120, lines: ["10:10 PM"])]
        }
        return ticks
    }

    private static func history(_ phase: RugbyMatchEventPagePhase10868, window chosen: Window? = nil, inspect: Inspect? = nil,
                                outcomes: [Outcome] = Tests.outcomes, withoutBaseline: String? = nil,
                                joined: Bool = false, choosing: Bool = false, keyContext: Bool = false,
                                selecting: Outcome? = nil) -> FieldHistoryInput10868 {
        let window = chosen ?? defaultWindow(phase)
        let minute = inspect?.minute
        var withdrawn: (Int, String)?
        if case .withdrawn(let t, let keyName)? = inspect { withdrawn = (t, keyName) }
        let series = outcomes.map { outcome -> FieldHistorySeries10868 in
            var ownRuns = runs(outcome, phase: phase, window: window, omitting: withdrawn?.1 == outcome.key ? withdrawn?.0 : nil)
            if joined, !ownRuns.isEmpty {
                ownRuns = [FieldHistoryRun10868(id: "joined.\(outcome.key)", points: ownRuns.flatMap(\.points))]
            }
            let before: FieldHistoryReading10868 = withoutBaseline == outcome.key
                ? .absent(words: "Unavailable")
                : .observation(pointID: pointID(outcome, outcome.baseline), figure: figure(close(outcome, outcome.baseline)!),
                               provenance: provenance(outcome.baseline))
            let recorded: FieldHistoryReading10868
            if let minute, let close = Self.close(outcome, minute) {
                recorded = .observation(pointID: pointID(outcome, minute), figure: figure(close), provenance: provenance(minute))
            } else if minute == nil, let t = recordedMinute(outcome, phase) {
                recorded = .observation(pointID: pointID(outcome, t), figure: figure(close(outcome, t)!), provenance: provenance(t))
            } else {
                recorded = .absent(words: "Current probability unavailable")
            }
            // Key controls on the first original only: its choose action, its own key context.
            let first = outcome.key == outcomes.first?.key
            var built = FieldHistorySeries10868(
                id: seriesID(outcome), name: outcome.name, shape: outcome.shape, tint: outcome.tint, runs: ownRuns,
                links: [], labelPointID: nil, before: before, recorded: recorded,
                absentWords: "No trades in this window",
                choose: choosing && first ? action("choose.\(outcome.key)", outcome.name) : nil)
            if keyContext, first {
                built.keyContext = FieldHistoryKeyContext10868(label: "Original", words: "Kalshi", spoken: nil)
            }
            return built
        }
        let readout: FieldHistoryReadoutIntent10868
        if inspect != nil {
            readout = .beforeAndInspected(beforeLabel: "Before match", inspectedLabel: "Selected minute")
        } else if phase == .before {
            readout = .singleBefore(label: "Before match")
        } else {
            readout = .beforeAndRecorded(beforeLabel: "Before match", recordedLabel: "Last recorded trade")
        }
        var selections: [String: FieldHistorySelection10868] = [:]
        if let minute {
            for outcome in outcomes {
                if let close = Self.close(outcome, minute), admits(phase, minute) {
                    selections[seriesID(outcome)] = .point(id: pointID(outcome, minute), spoken: figure(close))
                } else {
                    selections[seriesID(outcome)] = .absent(words: "No trade in this exact minute")
                }
            }
        }
        let range = domain(phase, window)
        return FieldHistoryInput10868(
            title: "Win probability history",
            caption: phase == .before ? "Last trades before the listed start" : "Last recorded trades",
            series: series,
            selection: selecting.map { FieldHistoryOriginalSelection10868.series(id: seriesID($0), missingWords: "This original isn’t in this history") }
                ?? FieldHistoryOriginalSelection10868.none,
            domain: range, ceiling: 1,
            yTicks: [0, 25, 50, 75, 100].map { FieldHistoryTick10868(value: Double($0) / 100, lines: ["\($0)%"]) },
            xTicks: xTicks(phase, window),
            guides: range.lower < 0 && range.upper > 0 ? [FieldHistoryGuide10868(id: "listed-start", x: 0, label: "Listed start")] : [],
            breaks: [], readout: readout,
            markKey: FieldHistoryMarkKey10868(hollow: "Hollow: traded before the listed start",
                                              filled: "Filled: traded after the listed start"),
            comparisonExplanation: nil,
            notes: ["Lines join adjacent traded minutes only; a gap never invents a probability.",
                    "Each time is the end of a traded minute candle, not a precise trade or scoring time.",
                    "Independent recorded probabilities · never normalized or synchronized."],
            summary: "France circles, England diamonds, draw squares; every line is solid. Hollow marks precede the listed start; filled marks are later recorded trades. Independent recorded probabilities from zero to one hundred percent.",
            plotHeight: 302, unboundReadingWords: "Unavailable", plotUnavailableWords: "History unavailable",
            windows: FieldHistoryWindows10868(groupLabel: "History window", choices: [
                FieldHistoryWindowChoice10868(action: action("window.match", "Around the match"), isSelected: window == .match),
                FieldHistoryWindowChoice10868(action: action("window.all", "All captured trades"), isSelected: window == .all),
            ]),
            scale: nil, moreOriginals: nil,
            details: action("history.details", "History & source details"),
            expand: action("history.expand", "Expand", spoken: "Open the win probability history full size"),
            inspect: nil,
            previous: action("history.previous", "‹", spoken: "Previous traded minute"),
            next: action("history.next", "›", spoken: "Next traded minute"),
            inspection: minute.map { minute in
                FieldHistoryInspection10868(
                    x: x(minute), caption: "Minute ending \(clocks[minute]!)", selections: selections, choices: [],
                    choicePresentation: .slider(label: "Inspect traded minutes"),
                    note: "Only trades in this exact minute · nothing carried forward")
            },
            layout: .cohortAbove)
    }

    // MARK: Context, story, Info

    private static func context(_ phase: RugbyMatchEventPagePhase10868, outcomes: [Outcome] = Tests.outcomes,
                                inspectKeys: [String: String] = [:]) -> RugbyMatchEventPageContext10868 {
        let result: String
        switch phase {
        case .before: result = "France vs England"
        case .during: result = "France vs England · constructed during-match example"
        case .final: result = "France vs England · Final 48–46"
        }
        return RugbyMatchEventPageContext10868(
            label: "Match probability context", result: result, caption: "Before match · separate trades",
            chartLabel: "Chart", chartSpokenLabel: "Open match win probability",
            entries: outcomes.map { outcome in
                RugbyMatchEventPageContextEntry10868(
                    seriesID: seriesID(outcome),
                    inspect: FieldMovementOpen10868(ref: ref(outcome), observation: inspectKeys[outcome.key] ?? key(outcome, outcome.baseline)))
            },
            unavailableWords: "Outcome unavailable in this update", inspectHint: "Shows this exact minute in the chart")
    }

    private static func storyReading(_ endpoint: HistoricalChanceEndpointKind10868) -> FieldChooserReading10868 {
        endpoint == .before
            ? beforeReading(france)
            : FieldChooserReading10868(label: "Lowest minute close", value: .recorded(
                text: figure(close(france, franceLow)!),
                detail: "\(provenance(franceLow)) · a minute’s close, not its intraminute low"))
    }

    private static func story(phase: FieldOutlookPhase10868 = .final, without: Set<HistoricalChanceEndpointKind10868> = [],
                              actual: Bool = true) -> HistoricalChanceInput10868 {
        let kinds = HistoricalChanceEndpointKind10868.allCases.filter { !without.contains($0) }
        return HistoricalChanceInput10868(
            scope: scope,
            catalogue: outcomes.map { headlineRecord($0, .final) },
            subject: HistoricalChanceSubject10868(ref: ref(france), name: "France"),
            readings: kinds.map { HistoricalChanceReading10868(ref: ref(france), endpoint: $0, reading: storyReading($0)) },
            observations: kinds.map { kind -> HistoricalChanceObservation10868 in
                let t = kind == .before ? france.baseline : franceLow
                return HistoricalChanceObservation10868(
                    ref: ref(france), endpoint: kind,
                    observation: FieldMovementObservation10868(probability: probability(close(france, t)!), reading: storyReading(kind)),
                    key: key(france, t))
            },
            actuals: actual ? [HistoricalChanceActual10868(
                place: FieldFinishPlace10868(ref: ref(france), reading: FieldChooserReading10868(
                    label: "Reported final score", value: .recorded(text: "France 48–46 England", detail: "ESPN match header · final"))),
                outcome: "France won")] : [],
            scale: FieldOutlookScale10868(
                ceiling: 1,
                ticks: [FieldOutlookTick10868(probability: 0, label: "0%"), FieldOutlookTick10868(probability: 0.5, label: "50%"),
                        FieldOutlookTick10868(probability: 1, label: "100%")],
                words: "0–100% chance · each a separate minute close"),
            phase: phase,
            copy: HistoricalChanceCopy10868(
                eyebrow: "FRANCE’S CHANGING CHANCE", title: "A favourite. Traded at 2%. Still the winner.",
                beforeLabel: "Before match", checkpointLabel: "Lowest minute close",
                endpointUnavailable: "Not recorded for this comparison",
                beforeKey: "Outline: last trade before the listed start",
                checkpointKey: "Filled: France’s lowest minute close in the match window",
                graphicLabel: "France’s pre-match and lowest minute-close chances",
                chanceUnplaced: "Not drawn on this scale", offScale: "Above this scale",
                actualTitle: "ACTUAL RESULT", actualLabel: "Reported final score", actualUnavailable: "Final score not confirmed",
                context: "Each chance is one dated minute close. The lowest is not a chance at the winning kick, at halftime or now. The score was reported separately.",
                expandLabel: "Open France’s chance story full size", expandHint: nil,
                detailsLabel: "How to read this story", detailsHint: nil,
                openHint: "Shows this exact minute in the history"),
            unavailableWords: "Team unavailable in this update")
    }

    private static let espnLink = RugbyMatchEventPageLink10868(id: "espn", label: "ESPN match header", url: URL(string: espnURL)!)

    private static func about(_ phase: RugbyMatchEventPagePhase10868) -> RugbyMatchEventPageAbout10868 {
        var sections = [
            RugbyMatchEventPageSection10868(
                title: "Three outcomes, three independent histories",
                paragraphs: ["Before match uses each outcome’s last traded minute strictly before the listed start, 8:10 PM GMT: France two minutes before it, England one minute before and the draw 31 minutes before. These independently recorded probabilities total 104%; they are not normalized or a simultaneous blend.",
                             "Blue circles identify France, teal diamonds England and neutral squares the draw; every line is solid. Lines connect adjacent traded minutes only, and a selected minute never carries another outcome forward. Each time is the end of a traded minute candle, not a precise trade or scoring time. The listed start is a schedule marker, not a verified kickoff. All captured trades covers a requested 48-hour window, not market inception.",
                             "The venue’s original “Tie” is displayed as “Draw”; its exact original and rules stay available. No projected score or other prop was captured."]),
        ]
        switch phase {
        case .before:
            break
        case .during:
            sections.append(RugbyMatchEventPageSection10868(
                title: "Constructed during-match example",
                paragraphs: ["Built from retained trades through the minute ending 8:54 PM GMT. It is not a live feed: no live score, kickoff or period timing is shown."]))
        case .final:
            sections.append(RugbyMatchEventPageSection10868(
                title: "Reported final",
                paragraphs: ["France 48–46 England is the ESPN match header’s final for event 602516. The retained capture’s request for the official Six Nations report returned 403, so that request did not itself verify the report; its account of Ramos’ decisive penalty with the clock in red is retained provenance from the earlier admission."],
                link: espnLink))
            sections.append(RugbyMatchEventPageSection10868(
                title: "What is withheld",
                paragraphs: ["ESPN commentary ends 41–46 while the header and official final read 48–46, and halftime prose and linescores disagree. Kickoff, halftime, the score timeline and period timing are withheld; no chance is assigned to a kick. The final score stays final while earlier probabilities are inspected.",
                             "The 2% is France’s lowest admitted match-window minute close, not an intraminute low, a current chance, a chance at halftime or the winning kick. Each original’s contract result is separate from the reported score."]))
        }
        sections.append(RugbyMatchEventPageSection10868(
            title: "Original markets", paragraphs: ["Each original keeps its own identity and rules."],
            sourceID: "rules.\(france.key)"))
        return RugbyMatchEventPageAbout10868(title: "About this rugby match", sections: sections)
    }

    private static func sources(_ phase: RugbyMatchEventPagePhase10868) -> [RugbyMatchEventPageSource10868] {
        outcomes.map { outcome -> RugbyMatchEventPageSource10868 in
            var sections = [
                RugbyMatchEventPageSection10868(title: "Primary rules", paragraphs: [outcome.primary]),
                RugbyMatchEventPageSection10868(title: "Secondary rules", paragraphs: [secondaryRules]),
                RugbyMatchEventPageSection10868(title: "Identity",
                                                paragraphs: ["Event \(eventTicker) · market \(outcome.ticker) · venue outcome \(outcome.venueName)"]),
            ]
            if phase == .final {
                sections.append(RugbyMatchEventPageSection10868(
                    title: "Contract result", paragraphs: ["Contract result: \(outcome.won ? "Won" : "Lost") · Kalshi, finalized"]))
            }
            return RugbyMatchEventPageSource10868(id: "rules.\(outcome.key)", title: "\(outcome.label) · original rules", sections: sections)
        }
    }

    private static let copy = RugbyMatchEventPageCopy10868(
        headlineUnavailable: "Match chances unavailable in this update",
        readerUnavailable: "This card is not available in this update.",
        sourceUnavailable: "This source is not available in this update.",
        sourceLabel: "Original rules & identity",
        catalogueLabel: "Original outcomes & rules",
        comparisonLabel: "Each outcome’s chances")

    private static func readerTitle(_ phase: RugbyMatchEventPagePhase10868) -> String {
        switch phase {
        case .before: return "France vs England · Before match"
        case .during: return "France vs England · Constructed during-match example"
        case .final: return "France vs England · Final 48–46"
        }
    }

    /// The owner's page parts for one phase, phase-correct by construction;
    /// tests replace single parts for rejected, withdrawn or bad controls.
    private struct Parts {
        var phase: RugbyMatchEventPagePhase10868
        var notice: String?
        var headline: FieldHeadlineInput10868
        var reader: RugbyMatchEventPageReaderHeader10868
        var history: FieldHistoryInput10868
        var readerPlotHeight: CGFloat?
        var context: RugbyMatchEventPageContext10868?
        var story: HistoricalChanceInput10868?
        var about: RugbyMatchEventPageAbout10868?
        var sources: [RugbyMatchEventPageSource10868]
        var copy: RugbyMatchEventPageCopy10868

        var input: RugbyMatchEventPageInput10868 {
            RugbyMatchEventPageInput10868(
                phase: phase, notice: notice, headline: headline, reader: reader, history: history,
                readerPlotHeight: readerPlotHeight, context: context, story: story, about: about,
                sources: sources, copy: copy)
        }
    }

    private static func parts(_ phase: RugbyMatchEventPagePhase10868, inspect: Inspect? = nil) -> Parts {
        Parts(
            phase: phase,
            notice: phase == .during
                ? "Constructed during-match example from retained trades through the minute ending 8:54 PM GMT · not a live feed"
                : nil,
            headline: headline(phase),
            reader: RugbyMatchEventPageReaderHeader10868(title: readerTitle(phase), state: nil),
            history: history(phase, inspect: inspect),
            readerPlotHeight: 380,
            context: context(phase),
            story: phase == .final ? story() : nil,
            about: about(phase), sources: sources(phase), copy: copy)
    }

    private static func page(_ phase: RugbyMatchEventPagePhase10868, inspect: Inspect? = nil) -> RugbyMatchEventPageInput10868 {
        parts(phase, inspect: inspect).input
    }

    // MARK: Originals

    private static func identity(_ outcome: Outcome) -> Originals.Identity {
        Originals.Identity(source: "kalshi", market: outcome.ticker, side: "Yes")
    }

    private static func mode(_ phase: RugbyMatchEventPagePhase10868) -> Originals.Mode {
        switch phase {
        case .before: return .pregame
        case .during: return .comparison(.recorded)
        case .final: return .result
        }
    }

    private static func pregame(_ outcome: Outcome) -> Originals.Reading {
        let close = Self.close(outcome, outcome.baseline)!
        return .value(figure(close), placement: probability(close),
                      provenance: "\(provenance(close.t)) · last trade before the listed start")
    }

    private static func later(_ outcome: Outcome, _ t: Int) -> Originals.Reading {
        let close = Self.close(outcome, t)!
        return .value(figure(close), placement: probability(close), provenance: provenance(t))
    }

    private static func original(_ outcome: Outcome, _ phase: RugbyMatchEventPagePhase10868,
                                 rules: [String]? = nil) -> Originals.Original {
        Originals.Original(
            identity: identity(outcome), title: originalTitle, outcome: outcome.venueName, mode: mode(phase),
            pregame: pregame(outcome),
            later: phase == .during ? later(outcome, outcome.duringRecorded) : nil,
            grade: phase == .final ? Originals.Grade(words: outcome.won ? "Won" : "Lost", provenance: "Contract result · Kalshi, finalized") : nil,
            about: Originals.About(
                source: "Kalshi", rules: .verified(rules ?? [outcome.primary, secondaryRules]),
                provenance: [Originals.Row(label: "Event", value: eventTicker), Originals.Row(label: "Market", value: outcome.ticker)],
                historicalQuote: nil),
            beforeLabel: "Before match")
    }

    private static func recordedContext(_ phase: RugbyMatchEventPagePhase10868, joined: Bool = false) -> Originals.RecordedHistory {
        let seriesID = "original.series.\(france.key)"
        var ownRuns = runs(france, phase: phase, window: defaultWindow(phase), idPrefix: "original.")
        if joined, !ownRuns.isEmpty {
            ownRuns = [FieldHistoryRun10868(id: "original.joined", points: ownRuns.flatMap(\.points))]
        }
        var mini = FieldHistoryInput10868(
            title: "France to win · recorded trades", caption: nil,
            series: [FieldHistorySeries10868(
                id: seriesID, name: "France to win", shape: .circle, tint: france.tint, runs: ownRuns, links: [],
                labelPointID: nil, before: .absent(words: "Shown above"), recorded: .absent(words: "Shown above"),
                absentWords: "No trades in this window", choose: nil)],
            selection: .series(id: seriesID, missingWords: "This original isn’t in this history"),
            domain: domain(phase, defaultWindow(phase)), ceiling: 1,
            yTicks: [FieldHistoryTick10868(value: 0, lines: ["0%"]), FieldHistoryTick10868(value: 1, lines: ["100%"])],
            xTicks: [], guides: [], breaks: [], readout: .singleBefore(label: "Before match"),
            markKey: FieldHistoryMarkKey10868(hollow: "Hollow: before the listed start", filled: "Filled: after it"),
            comparisonExplanation: nil, notes: [], summary: "France to win: its own recorded trades; adjacent minutes joined only.",
            plotHeight: 160, unboundReadingWords: "Unavailable", plotUnavailableWords: "Original history unavailable",
            windows: nil, scale: nil, moreOriginals: nil, details: nil, expand: nil, inspect: nil,
            previous: nil, next: nil, inspection: nil, layout: .expanded)
        mini.showsKey = false
        var readings = [Originals.RecordedReading(label: "Before match", marker: .hollow, reading: pregame(france))]
        switch phase {
        case .before:
            break
        case .during:
            readings.append(Originals.RecordedReading(label: "Recorded chance", marker: .solid, reading: later(france, france.duringRecorded)))
        case .final:
            readings.append(Originals.RecordedReading(label: "Last recorded trade", marker: .solid, reading: later(france, france.last)))
        }
        return Originals.RecordedHistory(
            selection: Originals.Selection(scope: originalsScope, identity: identity(france)), mode: mode(phase),
            seriesID: seriesID, availability: "Current probability unavailable · recorded trades below",
            readings: readings, movement: nil, history: mini,
            finishLabel: "Reported final score",
            finish: phase == .final ? .reported(words: "France 48–46 England", spoken: nil) : nil,
            preview: nil, expand: nil, explore: action("original.explore", "Explore history"),
            unmatchedWords: "Recorded history unavailable for this original")
    }

    private static func originals(_ phase: RugbyMatchEventPagePhase10868, omitting: String? = nil,
                                  selection: String = "FRA", outcomes: [Outcome] = Tests.outcomes) -> RugbyMatchEventPageOriginals10868 {
        var labels: [Originals.Identity: String] = [:]
        for outcome in outcomes { labels[identity(outcome)] = outcome.label }
        let held = outcomes.first { $0.key == selection } ?? france
        return RugbyMatchEventPageOriginals10868(
            catalogue: Originals.Catalogue(scope: originalsScope,
                                           originals: outcomes.filter { $0.key != omitting }.map { original($0, phase) }),
            selection: Originals.Selection(scope: originalsScope, identity: identity(held)),
            recorded: recordedContext(phase), labels: labels,
            heading: "All \(outcomes.count) original markets", context: "Each original keeps its own identity, rules and result",
            emptyWords: "No original markets in this update", unavailableChoice: "Unnamed original", tint: france.tint)
    }

    // MARK: Reachable text

    private static func endpointText(_ endpoint: FieldMovementEndpoint10868) -> [String] {
        [FieldChaseModel10868.label(endpoint)]
            + [FieldChaseModel10868.figure(endpoint), FieldChaseModel10868.words(endpoint), FieldChaseModel10868.detail(endpoint)]
            .compactMap { $0 }
    }

    private static func headlineText(_ model: FieldHeadlineModel10868) -> [String] {
        let copy = model.input.copy
        var texts = [model.eyebrow, model.title, model.aboutLabel(canAbout: true), copy.aboutHint, model.stateSummary]
            .compactMap { $0 }
        texts.append(copy.graphicLabel)
        if let state = model.state { texts += [state.figure] + [state.unit, state.caption, state.detail].compactMap { $0 } }
        let competitors = model.competitors
        if competitors.isEmpty { texts.append(copy.empty) }
        for competitor in competitors {
            texts += [competitor.slot.name, model.competitorSummary(competitor)]
            texts += [competitor.resolution.original?.name, model.compactName(competitor)].compactMap { $0 }
            if competitor.resolution.original == nil { texts.append(model.input.unavailableWords) }
            texts += competitor.metrics.flatMap(endpointText)
            let hint = model.hint(model.openAction(competitor, canOpen: true))
            if !hint.isEmpty { texts.append(hint) }
        }
        return texts
    }

    private static func historyText(_ history: FieldHistoryInput10868) -> [String] {
        var texts = [history.title, history.summary, history.unboundReadingWords] + history.notes
        texts += [history.caption, history.plotUnavailableWords, history.comparisonExplanation,
                  history.probabilityRangeExplanation, history.plotAbsence?.title, history.plotAbsence?.words,
                  FieldHistoryGeometry10868.selectionWords(history)].compactMap { $0 }
        if FieldHistoryGeometry10868.drawsStyle(.hollow, in: history), let words = history.markKey.hollow { texts.append(words) }
        if FieldHistoryGeometry10868.drawsStyle(.filled, in: history), let words = history.markKey.filled { texts.append(words) }
        texts += history.xTicks.flatMap(\.lines) + history.yTicks.flatMap(\.lines)
        texts += history.guides.map(\.label) + history.breaks.map(\.mark)
        texts.append(FieldHistoryGeometry10868.spokenValue(history))
        switch FieldHistoryGeometry10868.selectedSummary(history) {
        case .none: break
        case .words(let words): texts.append(words)
        case .original(let series, let slots): texts += [series.name] + slots.map(FieldHistoryGeometry10868.spokenSlot)
        }
        for series in history.series {
            texts.append(series.name)
            texts += FieldHistoryGeometry10868.readoutSlots(series, in: history).map(FieldHistoryGeometry10868.spokenSlot)
            texts += [FieldHistoryGeometry10868.keyNote(series, in: history)].compactMap { $0 }
        }
        if let inspection = history.inspection {
            texts += [inspection.caption] + [inspection.note].compactMap { $0 }
            texts += inspection.choices.flatMap { $0.lines + [$0.spoken] }
        }
        if let windows = FieldHistoryGeometry10868.shownWindows(history) { texts.append(windows.groupLabel) }
        texts += FieldHistoryGeometry10868.actions(history).flatMap { [$0.label, $0.spokenLabel].compactMap { $0 } }
        return texts
    }

    /// Everything the composed comparison draws or speaks.
    private static func comparisonText(_ comparison: RugbyMatchEventPageComparisonPresentation10868) -> [String] {
        var texts = [comparison.label]
        for entry in comparison.entries {
            texts += [entry.series.name] + [entry.note].compactMap { $0 }
            for slot in entry.slots {
                texts.append(slot.label)
                switch slot.display {
                case .figure(let figure, let provenance): texts += [figure, provenance]
                case .words(let words): texts.append(words)
                }
            }
            texts.append(RugbyMatchEventPageComparisonPresentation10868.spoken(entry))
        }
        return texts
    }

    private static func contextText(_ model: RugbyMatchEventPageModel10868) -> [String] {
        guard let context = model.input.context else { return [] }
        var texts = [context.label, context.result, context.chartLabel]
            + [context.caption, context.chartSpokenLabel, context.inspectHint].compactMap { $0 }
        for entry in context.entries {
            texts.append(model.contextEntrySummary(entry))
            if let series = model.contextSeries(entry), let slot = model.contextSlot(entry) {
                texts += [series.name, slot.label]
                switch slot.display {
                case .figure(let figure, let provenance): texts += [figure, provenance]
                case .words(let words): texts.append(words)
                }
            } else {
                texts.append(context.unavailableWords)
            }
        }
        return texts
    }

    private static func storyText(_ model: HistoricalChanceModel10868) -> [String] {
        guard model.isShown else { return [] }
        let copy = model.input.copy
        var texts = [model.eyebrow, model.title, model.context, model.subjectName, model.subjectWords, model.outcome]
            .compactMap { $0 }
        texts.append(copy.actualTitle)
        for side in model.sides {
            texts += endpointText(side.endpoint) + [model.barWords(side)].compactMap { $0 }
            texts.append(model.endpointSummary(side))
        }
        if let actual = model.actual { texts += endpointText(actual) }
        if model.showsPlot {
            texts += [model.input.scale.words, copy.beforeKey, copy.checkpointKey] + model.ticks.map(\.label)
        }
        texts += [model.chancesSummary, model.actualSummary, model.summary, copy.expandLabel]
        texts += [copy.expandHint, copy.detailsLabel, copy.detailsHint, copy.openHint].compactMap { $0 }
        return texts
    }

    private static func sectionsText(_ title: String, _ sections: [RugbyMatchEventPageSection10868]) -> [String] {
        var texts = [title]
        for section in sections {
            texts += [section.title] + section.paragraphs + [section.sourceID].compactMap { $0 }
            if let link = section.link { texts += [link.id, link.label, link.url.absoluteString] }
        }
        return texts
    }

    private static func originalsText(_ originals: RugbyMatchEventPageOriginals10868) -> [String] {
        guard let catalogue = originals.catalogue else { return [] }
        var texts = [originals.heading, originals.emptyWords, originals.unavailableChoice] + [originals.context].compactMap { $0 }
        texts += originals.labels.values.sorted()
        let choices = OriginalMarketChooser9483.choices(catalogue: catalogue, selection: originals.selection,
                                                        labels: originals.labels, unavailableChoice: originals.unavailableChoice)
        texts += choices.map(OriginalMarketChooser9483.spoken)
        for original in catalogue.originals {
            let content = Originals.content(catalogue: catalogue,
                                            selection: Originals.Selection(scope: catalogue.scope, identity: original.identity))
            texts.append(Originals.spoken(content))
            guard let content else { continue }
            texts += [content.title, content.outcome] + content.readings.map(\.label) + content.readings.map(\.text)
            texts += content.readings.compactMap(\.provenance) + content.about.map(\.label) + content.about.map(\.value)
            if case .verified(let paragraphs) = content.rules { texts += paragraphs }
            if let result = content.result { texts += [result.words] + [result.provenance].compactMap { $0 } }
        }
        if case .recorded(let shown)? = Originals.recorded(catalogue: catalogue, selection: originals.selection,
                                                          context: originals.recorded, hasCallback: true) {
            texts += [Originals.spoken(shown), shown.availability] + [Originals.resultSpoken(shown), shown.movement].compactMap { $0 }
            if let finish = shown.finish { texts += [finish.label, finish.words, finish.spoken] }
            texts += historyText(shown.history)
        }
        return texts
    }

    /// Every string a reader can reach on this page in its phase — the headline,
    /// notice, comparison and history page and full size, context, story page and full size,
    /// reader words, Info, sources, every original choice and Details — through
    /// the shared models the views draw from.
    private static func reachable(_ input: RugbyMatchEventPageInput10868,
                                  originals: RugbyMatchEventPageOriginals10868?) -> [String] {
        let model = RugbyMatchEventPageModel10868(input)
        var texts: [String] = []
        if let headline = model.headline {
            texts += headlineText(FieldHeadlineModel10868(headline))
        } else {
            texts.append(input.copy.headlineUnavailable)
        }
        texts += [input.notice, input.reader.state].compactMap { $0 } + [input.reader.title]
        texts += historyText(model.presentedHistory) + historyText(model.readerHistory)
        texts += comparisonText(RugbyMatchEventPagePresentation10868(input: input).comparisonContent(reader: false))
        texts += comparisonText(RugbyMatchEventPagePresentation10868(input: input, mode: .reader(.history)).comparisonContent(reader: true))
        texts += contextText(model)
        if let story = model.story { texts += storyText(HistoricalChanceModel10868(story)) }
        if RugbyMatchEventPageCard10868.allCases.contains(where: { !model.readerShows($0) }) {
            texts.append(input.copy.readerUnavailable)
        }
        if let about = model.about { texts += sectionsText(about.title, about.sections) }
        for source in input.sources where model.source(source.id) != nil { texts += sectionsText(source.title, source.sections) }
        texts += [input.copy.sourceLabel] + [input.copy.catalogueLabel].compactMap { $0 }
        if let originals { texts += originalsText(originals) }
        return texts
    }

    /// Facts only an owner after the match could know. Original rules state
    /// conditions known beforehand ("the winner", "resolves to Yes") and are
    /// deliberately not listed.
    private static let finalFacts = ["48–46", "Final score", "Reported final", "France won", "No draw", "official report",
                                     "Official Six Nations", "ESPN match header", "Ramos", "clock in red", "Contract result",
                                     "finalized", "41–46", "commentary", "Lowest", "lowest", "403"]
    /// A result word, not a substring of "winner".
    private static let resultPattern = #"\b(Won|Lost)\b"#
    /// A reported score, by meaning: a score figure on its own, the score pair,
    /// a team's score or points — never a "48%" figure, an "8:48" clock minute
    /// or a "48-hour" window.
    private static let scorePatterns = [
        #"^\s*(48|46)\s*$"#,
        #"(?<![\d.:])(48|46)\s*[–-]\s*(46|48)(?![\d%])"#,
        #"\b(France|England)\s+(48|46)(?![\d%.:])"#,
        #"(?<![\d.:])(48|46)\s+points\b"#,
    ]

    private static func scored(_ text: String) -> Bool {
        scorePatterns.contains { text.range(of: $0, options: .regularExpression) != nil }
    }

    /// Every reading clock after a phase's cut: a quote no owner at that phase could have.
    private static func clocksAfter(_ cut: Int) -> [String] {
        clocks.filter { $0.key > cut }.map(\.value)
    }

    private static func leaks(_ texts: [String], phase: RugbyMatchEventPagePhase10868) -> [String] {
        let cut: Int
        switch phase {
        case .before: cut = listedStart
        case .during: cut = duringCut
        case .final: return []
        }
        let later = clocksAfter(cut)
        return texts.filter { text in
            finalFacts.contains { text.contains($0) } || later.contains { text.contains($0) }
                || text.range(of: resultPattern, options: .regularExpression) != nil
                || scored(text)
        }
    }

    // MARK: Payloads

    /// Every exact original/observation hand-off reachable on this page: the
    /// headline's opens, the context's inspects and the story's endpoints.
    private static func payloads(_ input: RugbyMatchEventPageInput10868) -> [FieldMovementOpen10868] {
        let model = RugbyMatchEventPageModel10868(input)
        var found: [FieldMovementOpen10868] = []
        if let headline = model.headline {
            let leaf = FieldHeadlineModel10868(headline)
            found += leaf.competitors.compactMap { leaf.openAction($0, canOpen: true) }
        }
        if let context = input.context {
            found += context.entries.compactMap { model.contextInspect($0, canInspect: true) }
        }
        if let story = model.story {
            let leaf = HistoricalChanceModel10868(story)
            found += leaf.sides.compactMap { leaf.openAction($0, canOpen: true) }
        }
        return found
    }

    /// A payload names an original of this page and, when it carries an
    /// observation, one admitted at the page's own phase.
    private static func payloadViolations(_ found: [FieldMovementOpen10868], phase: RugbyMatchEventPagePhase10868) -> [String] {
        let refs = outcomes.map { ref($0) }
        return found.compactMap { open -> String? in
            guard refs.contains(open.ref) else { return "foreign original \(open.ref.marketID)" }
            guard let observation = open.observation else { return nil }
            guard let t = observationTime(observation) else { return "unknown observation \(observation)" }
            return admits(phase, t) ? nil : "\(observation) is not admitted \(phase.rawValue)"
        }
    }

    private static func marks(_ history: FieldHistoryInput10868) -> [FieldHistoryPoint10868] {
        history.series.flatMap { FieldHistoryGeometry10868.marks($0, in: history) }
    }

    /// Every drawn line pair that is not one traded minute apart.
    private static func nonAdjacentJoins(_ history: FieldHistoryInput10868) -> [String] {
        history.series.flatMap { series in
            FieldHistoryGeometry10868.lines(series, in: history).flatMap { line in
                zip(line, line.dropFirst()).compactMap { pair -> String? in pair.1.x - pair.0.x == 1 ? nil : "\(pair.0.id)→\(pair.1.id)" }
            }
        }
    }

    private static func slots(_ history: FieldHistoryInput10868, _ outcome: Outcome) -> [FieldHistoryReadoutSlot10868] {
        guard let series = history.series.first(where: { $0.id == seriesID(outcome) }) else { return [] }
        return FieldHistoryGeometry10868.readoutSlots(series, in: history)
    }

    private static func figureSlot(_ label: String, _ outcome: Outcome, _ t: Int) -> FieldHistoryReadoutSlot10868 {
        FieldHistoryReadoutSlot10868(label: label, display: .figure(figure(close(outcome, t)!), provenance: provenance(t)))
    }

    // MARK: - Retained data

    func testAll347RetainedClosesTheThreeIndependentBaselinesAndTheLowestCloseMatchTheCapture() {
        XCTAssertEqual(Self.outcomes.map(\.closes.count), [107, 201, 39])
        XCTAssertEqual(Self.outcomes.map(\.closes.count).reduce(0, +), 347)
        XCTAssertEqual(Self.outcomes.map { $0.closes.filter { $0.t < Self.listedStart }.count }, [57, 120, 17])
        for outcome in Self.outcomes {
            XCTAssertTrue(outcome.closes.allSatisfy { $0.volume > 0 && $0.t % 60 == 0 && (0...100).contains($0.cents) }, outcome.key)
            XCTAssertEqual(outcome.closes.map(\.t), outcome.closes.map(\.t).sorted(), outcome.key)
            XCTAssertEqual(Set(outcome.closes.map(\.t)).count, outcome.closes.count, outcome.key)
            // The owner's elections agree with the retained closes.
            XCTAssertEqual(outcome.closes.last { $0.t < Self.listedStart }?.t, outcome.baseline, outcome.key)
            XCTAssertEqual(outcome.closes.last { $0.t <= Self.duringCut }?.t, outcome.duringRecorded, outcome.key)
            XCTAssertEqual(outcome.closes.last?.t, outcome.last, outcome.key)
        }
        // Three independently timed baselines: 81% at 8:08, 21% at 8:09, 2% at 7:39; 104% in total, never normalized.
        XCTAssertEqual(Self.outcomes.map { Self.close($0, $0.baseline)!.cents }, [81, 21, 2])
        XCTAssertEqual(Self.outcomes.map(\.baseline), [1773518880, 1773518940, 1773517140])
        XCTAssertEqual(Self.outcomes.map { Self.close($0, $0.baseline)!.cents }.reduce(0, +), 104)
        // Last closes: 99% at 10:11, 1% at 10:06, 1% at 9:57.
        XCTAssertEqual(Self.outcomes.map { Self.close($0, $0.last)!.cents }, [99, 1, 1])
        XCTAssertEqual(Self.outcomes.map(\.last), [1773526260, 1773525960, 1773525420])
        // France's lowest match-window minute CLOSE is 2% at 8:53, the minute's close.
        let window = Self.france.closes.filter { $0.t >= Self.listedStart }
        XCTAssertEqual(window.min { $0.cents < $1.cents }?.t, Self.franceLow)
        XCTAssertEqual(Self.close(Self.france, Self.franceLow)?.cents, Self.lowCandle.close)
        XCTAssertNotEqual(Self.lowCandle.open, Self.lowCandle.close)
        XCTAssertEqual(Self.storyReading(.checkpoint).label, "Lowest minute close")
        // The very next France close is 48%: a probability, not a score.
        XCTAssertEqual(Self.close(Self.france, Self.duringCut)?.cents, 48)
    }

    // MARK: - Phase mounts

    func testBeforeTheMatchMountsThePreMatchReadingsAndHistoryOnly() {
        let input = Self.page(.before)
        let model = RugbyMatchEventPageModel10868(input)
        XCTAssertEqual(model.headline, input.headline)
        XCTAssertNil(model.story)
        XCTAssertFalse(model.readerShows(.story))
        let headline = FieldHeadlineModel10868(model.headline!)
        XCTAssertEqual(headline.competitors.map { $0.metrics.compactMap(FieldChaseModel10868.figure) }, [["81%"], ["21%"], ["2%"]])
        XCTAssertTrue(headline.keyIsHollow)
        XCTAssertEqual(headline.competitors.map { headline.keyShape($0) }, [.circle, .diamond, .square])
        // 194 admitted closes, all hollow and before the listed start; no guide yet.
        let marks = Self.marks(input.history)
        XCTAssertEqual(marks.count, 57 + 120 + 17)
        XCTAssertTrue(marks.allSatisfy { $0.x < 0 && $0.style == .hollow })
        XCTAssertEqual(input.history.guides, [])
        XCTAssertEqual(Self.slots(input.history, Self.france), [Self.figureSlot("Before match", Self.france, Self.france.baseline)])
        XCTAssertNil(RugbyMatchEventPagePresentation10868(input: input).storyContent(reader: false))
    }

    func testTheConstructedDuringPageIsLabelledAndShowsRecordedChancesThroughItsCutOnly() {
        let input = Self.page(.during)
        let model = RugbyMatchEventPageModel10868(input)
        XCTAssertTrue(input.notice!.contains("Constructed"))
        XCTAssertTrue(input.headline.copy.eyebrow!.contains("CONSTRUCTED"))
        XCTAssertNil(model.story)
        let headline = FieldHeadlineModel10868(model.headline!)
        XCTAssertEqual(headline.competitors.map { $0.metrics.compactMap(FieldChaseModel10868.figure) },
                       [["81%", "48%"], ["21%", "60%"], ["2%", "1%"]])
        XCTAssertNil(headline.state)
        XCTAssertTrue(Self.marks(input.history).allSatisfy { $0.x <= Self.x(Self.duringCut) })
        XCTAssertEqual(Self.marks(input.history).count, 24 + 46 + 13)
        XCTAssertEqual(input.history.guides.map(\.label), ["Listed start"])
        XCTAssertEqual(Self.slots(input.history, Self.draw), [
            Self.figureSlot("Before match", Self.draw, Self.draw.baseline),
            Self.figureSlot("Last recorded trade", Self.draw, 1773521580),
        ])
    }

    func testAfterTheMatchMountsTheReportedFinalTheStoryAndEveryContractResultApart() {
        let input = Self.page(.final)
        let model = RugbyMatchEventPageModel10868(input)
        let headline = FieldHeadlineModel10868(model.headline!)
        XCTAssertEqual(headline.competitors.map { $0.metrics.map(FieldChaseModel10868.label) },
                       Array(repeating: ["Before match", "Final score"], count: 3))
        XCTAssertEqual(headline.competitors.map { $0.metrics.compactMap(FieldChaseModel10868.figure) }, [["81%", "48"], ["21%", "46"], ["2%"]])
        XCTAssertEqual(headline.competitors[2].metrics.compactMap(FieldChaseModel10868.words), ["No draw"])
        XCTAssertFalse(headline.keyIsHollow)
        XCTAssertEqual(model.story, input.story)
        XCTAssertTrue(model.readerShows(.story))
        let story = HistoricalChanceModel10868(model.story!)
        XCTAssertEqual(story.sides.map { FieldChaseModel10868.figure($0.endpoint) }, ["81%", "2%"])
        XCTAssertEqual(story.sides.map(\.chance.fraction), [0.81, 0.02])
        XCTAssertEqual(story.actual, .reading(FieldChooserReading10868(
            label: "Reported final score", value: .recorded(text: "France 48–46 England", detail: "ESPN match header · final"))))
        // Each contract's result is its own; the score is never one of them.
        let originals = Self.originals(.final)
        let results = Self.outcomes.map { outcome in
            Originals.content(catalogue: originals.catalogue,
                              selection: Originals.Selection(scope: Self.originalsScope, identity: Self.identity(outcome)))?.result?.words
        }
        XCTAssertEqual(results, ["Won", "Lost", "Lost"])
        // The history ends at the last retained close: no settled endpoint is added.
        XCTAssertFalse(Self.marks(input.history).contains { $0.probability == 0 || $0.probability == 1 })
        XCTAssertEqual(Self.marks(Self.history(.final, window: .all)).count, 347)
    }

    // MARK: - Phase text

    func testEveryReachableBeforeAndLiveTextCarriesNoLaterOrFinalFactWithFinalControlsAndMeaningAwareScores() {
        let finalTexts = Self.reachable(Self.page(.final, inspect: .minute(1773525900)), originals: Self.originals(.final))
        let duringTexts = Self.reachable(Self.page(.during), originals: Self.originals(.during))
        // Positive controls: the guard sees every later fact.
        XCTAssertFalse(Self.leaks(finalTexts, phase: .during).isEmpty)
        XCTAssertFalse(Self.leaks(duringTexts, phase: .before).isEmpty)
        for fact in ["48–46", "Won", "Lowest minute close", "403", "41–46", "No draw", "Mar 14, 10:11 PM GMT"] {
            XCTAssertTrue(finalTexts.contains { $0.contains(fact) }, fact)
        }
        // Meaning-aware: the live 48% is a probability, never the 48 points.
        XCTAssertTrue(duringTexts.contains { $0.contains("48%") })
        for probability in ["48%", "46%", "Mar 14, 8:48 PM GMT", "a requested 48-hour window", "Last recorded trade: 48%, Minute ending Mar 14, 8:54 PM GMT · Kalshi"] {
            XCTAssertFalse(Self.scored(probability), probability)
        }
        for score in ["48", "48–46", "France 48–46 England", "Reported final, France 48, England 46.", "46 points"] {
            XCTAssertTrue(Self.scored(score), score)
        }
        XCTAssertTrue(finalTexts.contains("48"))
        XCTAssertTrue(Self.reachable(Self.page(.before), originals: nil).contains { $0.contains("48-hour") })
        // Original rules carry conditions known beforehand; they are not final facts.
        XCTAssertEqual(Self.leaks([Self.francePrimary, Self.drawPrimary, Self.secondaryRules], phase: .before), [])

        let cases: [(RugbyMatchEventPagePhase10868, Inspect?)] = [
            (.before, nil), (.before, .minute(1773518880)), (.before, .minute(1773517140)),
            (.during, nil), (.during, .minute(1773521580)), (.during, .minute(1773521640)), (.during, .withdrawn(1773521580, "FRA")),
        ]
        for (phase, inspect) in cases {
            let texts = Self.reachable(Self.page(phase, inspect: inspect), originals: Self.originals(phase))
            XCTAssertEqual(Self.leaks(texts, phase: phase), [], "\(phase.rawValue) \(String(describing: inspect))")
            // Never a normalized blend of the three baselines.
            XCTAssertFalse(texts.contains { $0.contains("77.9%") || $0.contains("20.2%") || $0.contains("1.9%") })
        }
        // Full-size history and story readers are the same leaves on the same inputs.
        for phase in [RugbyMatchEventPagePhase10868.before, .during] {
            let model = RugbyMatchEventPageModel10868(Self.page(phase))
            XCTAssertEqual(Self.leaks(Self.historyText(model.readerHistory), phase: phase), [])
            XCTAssertNil(model.story)
        }
    }

    // MARK: - Payloads

    func testEveryHandOffCarriesTheOriginalAndTimeAdmittedInItsOwnPhaseAndABadPayloadIsCaught() {
        for phase in RugbyMatchEventPagePhase10868.allCases {
            let found = Self.payloads(Self.page(phase))
            XCTAssertEqual(Self.payloadViolations(found, phase: phase), [], phase.rawValue)
            XCTAssertFalse(found.isEmpty, phase.rawValue)
        }
        // Before: the headline opens with no observation; the context hands back each pre-match key.
        let before = Self.payloads(Self.page(.before))
        XCTAssertEqual(before, Self.outcomes.map { FieldMovementOpen10868(ref: Self.ref($0), observation: nil) }
            + Self.outcomes.map { FieldMovementOpen10868(ref: Self.ref($0), observation: Self.key($0, $0.baseline)) })
        // During: the headline hands back each recorded key at or before the cut.
        let during = Self.payloads(Self.page(.during))
        XCTAssertEqual(Array(during.prefix(3)), Self.outcomes.map {
            FieldMovementOpen10868(ref: Self.ref($0), observation: Self.key($0, $0.duringRecorded))
        })
        // Final: the story's two endpoints carry their own keys.
        let final = Self.payloads(Self.page(.final))
        XCTAssertEqual(Array(final.suffix(2)), [
            FieldMovementOpen10868(ref: Self.ref(Self.france), observation: Self.key(Self.france, Self.france.baseline)),
            FieldMovementOpen10868(ref: Self.ref(Self.france), observation: Self.key(Self.france, Self.franceLow)),
        ])
        // An earlier owner change is followed exactly, never a default.
        var earlier = Self.parts(.during)
        earlier.headline = Self.headline(.during, recorded: ["FRA": Self.franceLow])
        let earlierFound = Self.payloads(earlier.input)
        XCTAssertEqual(earlierFound.first, FieldMovementOpen10868(ref: Self.ref(Self.france), observation: Self.key(Self.france, Self.franceLow)))
        XCTAssertEqual(Self.payloadViolations(earlierFound, phase: .during), [])
        // A missing baseline: that slot is words and hands back nothing; the others keep theirs.
        var missing = Self.parts(.before)
        missing.history = Self.history(.before, withoutBaseline: "FRA")
        let missingFound = Self.payloads(missing.input)
        XCTAssertFalse(missingFound.contains(FieldMovementOpen10868(ref: Self.ref(Self.france), observation: Self.key(Self.france, Self.france.baseline))))
        XCTAssertTrue(missingFound.contains(FieldMovementOpen10868(ref: Self.ref(Self.england), observation: Self.key(Self.england, Self.england.baseline))))

        // Deliberately bad controls: a final time in before and in live is caught.
        var badBefore = Self.parts(.before)
        badBefore.context = Self.context(.before, inspectKeys: ["FRA": Self.key(Self.france, Self.franceLow)])
        XCTAssertEqual(Self.payloadViolations(Self.payloads(badBefore.input), phase: .before),
                       ["\(Self.key(Self.france, Self.franceLow)) is not admitted before"])
        var badDuring = Self.parts(.during)
        badDuring.headline = Self.headline(.during, recorded: ["FRA": Self.france.last])
        XCTAssertEqual(Self.payloadViolations(Self.payloads(badDuring.input), phase: .during),
                       ["\(Self.key(Self.france, Self.france.last)) is not admitted during"])
        // A foreign original is caught too.
        let foreign = FieldMovementOpen10868(ref: Self.ref(Self.france, scope: "constructed:other"), observation: nil)
        XCTAssertEqual(Self.payloadViolations([foreign], phase: .final), ["foreign original \(Self.france.ticker)"])
    }

    // MARK: - Rules fidelity

    func testEveryOriginalKeepsItsPrimaryAndSecondaryRulesVerbatimAndItsVenueOutcomeName() {
        let originals = Self.originals(.before)
        for outcome in Self.outcomes {
            let content = Originals.content(catalogue: originals.catalogue,
                                            selection: Originals.Selection(scope: Self.originalsScope, identity: Self.identity(outcome)))
            XCTAssertEqual(content?.rules, .verified([outcome.primary, Self.secondaryRules]), outcome.key)
            XCTAssertEqual(content?.title, "France vs England Winner?")
            XCTAssertEqual(content?.outcome, outcome.venueName)
            XCTAssertEqual(Self.sources(.before).first { $0.id == "rules.\(outcome.key)" }?.sections.prefix(2).map(\.paragraphs),
                           [[outcome.primary], [Self.secondaryRules]])
        }
        // Exact text, character for character.
        XCTAssertEqual(Self.drawPrimary.count, 154)
        XCTAssertTrue(Self.drawPrimary.hasPrefix("If Tie is the result in the France vs England professional Six Nations Rugby match"))
        XCTAssertTrue(Self.secondaryRules.contains("Six Nations Rugby rugby match"))
        XCTAssertTrue(Self.secondaryRules.hasSuffix("in accordance with the rules."))
        // The venue's "Tie" is displayed as "Draw" and keeps its exact identity and rules.
        let choices = OriginalMarketChooser9483.choices(catalogue: originals.catalogue, selection: originals.selection,
                                                        labels: originals.labels, unavailableChoice: originals.unavailableChoice)
        XCTAssertEqual(choices.map(\.label), ["France to win", "England to win", "Draw"])
        XCTAssertEqual(choices[2].selection?.identity, Self.identity(Self.draw))
        // A paraphrase is never the verified text.
        let paraphrased = Originals.Catalogue(scope: Self.originalsScope, originals: [
            Self.original(Self.draw, .before, rules: ["Resolves Yes if the match ends level."]),
        ])
        let content = Originals.content(catalogue: paraphrased, selection: Originals.Selection(scope: Self.originalsScope, identity: Self.identity(Self.draw)))
        XCTAssertNotEqual(content?.rules, .verified([Self.drawPrimary, Self.secondaryRules]))
    }

    // MARK: - Exact minutes and lines

    func testAnInspectedMinuteShowsEachOriginalsOwnExactCloseOrWordsAndEqualValuesKeepTheirOwnDates() {
        // The same observation: France's before match IS its 8:08 close — both slots carry one date.
        let same = Self.history(.before, inspect: .minute(1773518880))
        XCTAssertEqual(Self.slots(same, Self.france), [
            Self.figureSlot("Before match", Self.france, 1773518880), Self.figureSlot("Selected minute", Self.france, 1773518880),
        ])
        XCTAssertEqual(Self.slots(same, Self.england).last, FieldHistoryReadoutSlot10868(label: "Selected minute", display: .words("No trade in this exact minute")))
        // An earlier minute: each original's own 7:39 close beside its own separate before match.
        let earlier = Self.history(.before, inspect: .minute(1773517140))
        XCTAssertEqual(Self.slots(earlier, Self.france).last, Self.figureSlot("Selected minute", Self.france, 1773517140))
        XCTAssertEqual(Self.slots(earlier, Self.england).map(\.display), [
            .figure("21%", provenance: Self.provenance(1773518940)), .figure("18%", provenance: Self.provenance(1773517140)),
        ])
        // A sparse minute: the draw did not trade at 8:54 — its words, never its 8:53 close carried forward.
        let sparse = Self.history(.final, inspect: .minute(1773521640))
        XCTAssertEqual(Self.slots(sparse, Self.draw).last, FieldHistoryReadoutSlot10868(label: "Selected minute", display: .words("No trade in this exact minute")))
        XCTAssertNil(FieldHistoryGeometry10868.inspectedPoint(sparse.series[2], in: sparse))
        XCTAssertEqual(Self.slots(sparse, Self.france).last, Self.figureSlot("Selected minute", Self.france, 1773521640))
        // Equal values at different minutes stay two dated observations.
        let first = Self.slots(Self.history(.final, inspect: .minute(1773525900)), Self.england).last
        let second = Self.slots(Self.history(.final, inspect: .minute(1773525960)), Self.england).last
        XCTAssertEqual(first, Self.figureSlot("Selected minute", Self.england, 1773525900))
        XCTAssertEqual(second, Self.figureSlot("Selected minute", Self.england, 1773525960))
        XCTAssertNotEqual(first, second)
        // The 8:53 closes are independent: 2% + 38% + 1% are never made to agree.
        let low = Self.history(.final, inspect: .minute(Self.franceLow))
        XCTAssertEqual(Self.outcomes.map { Self.slots(low, $0).last?.display },
                       [.figure("2%", provenance: Self.provenance(Self.franceLow)),
                        .figure("38%", provenance: Self.provenance(Self.franceLow)),
                        .figure("1%", provenance: Self.provenance(Self.franceLow))])
    }

    func testOnlyAdjacentTradedMinutesConnectInTheMainFullAndOriginalReadersWithAJoinedControl() {
        for phase in RugbyMatchEventPagePhase10868.allCases {
            for window in [Window.match, .all] {
                let history = Self.history(phase, window: window)
                XCTAssertEqual(Self.nonAdjacentJoins(history), [], "\(phase.rawValue) \(window)")
                XCTAssertEqual(Self.nonAdjacentJoins(RugbyMatchEventPageModel10868(Self.page(phase)).readerHistory), [])
                // Every mark is a retained close at its own value; nothing is added.
                for outcome in Self.outcomes {
                    let series = history.series.first { $0.id == Self.seriesID(outcome) }!
                    let shown = FieldHistoryGeometry10868.marks(series, in: history)
                    XCTAssertTrue(shown.allSatisfy { point in
                        outcome.closes.contains { Self.pointID(outcome, $0.t) == point.id && Self.probability($0) == point.probability }
                    })
                }
                // Positive control: one run over the same closes joins real gaps, and the check names them.
                XCTAssertFalse(Self.nonAdjacentJoins(Self.history(phase, window: window, joined: true)).isEmpty)
            }
            // The original's Details chart, through `Originals.recorded`.
            let originals = Self.originals(phase)
            guard case .recorded(let shown)? = Originals.recorded(catalogue: originals.catalogue, selection: originals.selection,
                                                                  context: originals.recorded, hasCallback: true) else {
                XCTFail("the held original shows its recorded history (\(phase.rawValue))")
                continue
            }
            XCTAssertEqual(Self.nonAdjacentJoins(shown.history), [], phase.rawValue)
            XCTAssertFalse(Self.nonAdjacentJoins(Self.recordedContext(phase, joined: true).history).isEmpty, phase.rawValue)
        }
    }

    // MARK: - Story

    func testTheStoryKeepsTheActualWhenEitherChanceOrTheHistoryIsMissing() {
        let both = HistoricalChanceModel10868(Self.story(without: [.before, .checkpoint]))
        XCTAssertEqual(both.sides.map { FieldChaseModel10868.words($0.endpoint) }, Array(repeating: "Not recorded for this comparison", count: 2))
        XCTAssertFalse(both.showsPlot)
        XCTAssertEqual(both.actualSummary, "ACTUAL RESULT. Reported final score: France 48–46 England, ESPN match header · final. France won")
        let lowOnly = HistoricalChanceModel10868(Self.story(without: [.before]))
        XCTAssertEqual(lowOnly.sides.map { FieldChaseModel10868.figure($0.endpoint) }, [nil, "2%"])
        XCTAssertNotNil(lowOnly.outcome)
        // An unconfirmed actual keeps its panel and removes no chance.
        let noActual = HistoricalChanceModel10868(Self.story(actual: false))
        XCTAssertEqual(noActual.actual, .unavailable(label: "Reported final score", words: "Final score not confirmed"))
        XCTAssertEqual(noActual.sides.map { FieldChaseModel10868.figure($0.endpoint) }, ["81%", "2%"])
        // The history withdrawn by the owner: the headline final and the story actual stay.
        var absent = Self.parts(.final)
        absent.history.plotAbsence = FieldHistoryPlotAbsence10868(title: "No retained trades", words: nil)
        let model = RugbyMatchEventPageModel10868(absent.input)
        XCTAssertFalse(FieldHistoryGeometry10868.showsPlot(model.input.history))
        XCTAssertEqual(FieldHeadlineModel10868(model.headline!).competitors[0].metrics.compactMap(FieldChaseModel10868.figure), ["81%", "48"])
        XCTAssertNotNil(HistoricalChanceModel10868(model.story!).outcome)
        // A story built for another phase is never mounted.
        var early = Self.parts(.final)
        early.story = Self.story(phase: .during)
        XCTAssertNil(RugbyMatchEventPageModel10868(early.input).story)
        var leaked = Self.parts(.during)
        leaked.story = Self.story()
        XCTAssertNil(RugbyMatchEventPageModel10868(leaked.input).story)
    }

    func testTheReportedFinalStaysSeparateFromTheCommentaryAndNothingWithheldIsInvented() {
        let final = Self.page(.final)
        let model = RugbyMatchEventPageModel10868(final)
        // Headline, story and history never carry the commentary's earlier score or a timeline.
        var shown = Self.headlineText(FieldHeadlineModel10868(model.headline!)) + Self.historyText(final.history)
        shown += Self.storyText(HistoricalChanceModel10868(model.story!))
        XCTAssertFalse(shown.contains { $0.contains("41–46") })
        XCTAssertTrue(shown.contains { $0.contains("48–46") })
        for word in ["Kickoff", "kickoff", "Half-time", "Halftime", "halftime", "projected", "Projected"] {
            XCTAssertFalse(Self.headlineText(FieldHeadlineModel10868(model.headline!)).contains { $0.contains(word) && !$0.contains("not a verified kickoff") }, word)
        }
        // No scoring or half marker: the only guide is the listed start.
        XCTAssertEqual(final.history.guides.map(\.id), ["listed-start"])
        // The About names the conflict, the 403 and the withholding without claiming the report was verified.
        let about = model.about!.sections.flatMap(\.paragraphs).joined(separator: " ")
        XCTAssertTrue(about.contains("41–46"))
        XCTAssertTrue(about.contains("returned 403"))
        XCTAssertFalse(about.contains("corroborated by the official"))
        XCTAssertFalse(about.contains("verified the report") && !about.contains("did not itself verify the report"))
    }

    // MARK: - Identity

    func testArbitraryOriginalSetsAndDuplicateForeignOrWithdrawnReferencesNeverBorrowANeighbour() {
        // Two outcomes or four: the page composes whatever the owner admits.
        let pair = [Self.france, Self.england]
        var two = Self.parts(.final)
        two.headline = Self.headline(.final, outcomes: pair)
        two.history = Self.history(.final, outcomes: pair)
        two.context = Self.context(.final, outcomes: pair)
        let twoModel = RugbyMatchEventPageModel10868(two.input)
        XCTAssertEqual(FieldHeadlineModel10868(twoModel.headline!).competitors.count, 2)
        XCTAssertEqual(two.input.context!.entries.compactMap { twoModel.contextInspect($0, canInspect: true) }.count, 2)
        XCTAssertEqual(Self.originals(.final, outcomes: pair).heading, "All 2 original markets")

        // A duplicate slot, a foreign scope and a withdrawn record are unavailable; neighbours keep theirs.
        var headline = Self.headline(.final)
        let duplicated = FieldHeadlineInput10868(
            scope: headline.scope, catalogue: headline.catalogue,
            displayed: headline.displayed + [headline.displayed[0]], pairs: headline.pairs, finishes: headline.finishes,
            state: headline.state, phase: headline.phase, copy: headline.copy, unavailableWords: headline.unavailableWords)
        let duplicateModel = FieldHeadlineModel10868(duplicated)
        XCTAssertEqual(duplicateModel.competitors.map { $0.resolution.original != nil }, [false, true, true, false])
        headline = FieldHeadlineInput10868(
            scope: headline.scope, catalogue: Array(headline.catalogue.dropFirst()),
            displayed: headline.displayed, pairs: headline.pairs, finishes: headline.finishes,
            state: headline.state, phase: headline.phase, copy: headline.copy, unavailableWords: headline.unavailableWords)
        let withdrawnModel = FieldHeadlineModel10868(headline)
        XCTAssertEqual(withdrawnModel.competitors.map { $0.metrics.compactMap(FieldChaseModel10868.figure) }, [[], ["21%", "46"], ["2%"]])
        XCTAssertNil(withdrawnModel.openAction(withdrawnModel.competitors[0], canOpen: true))
        let foreign = Self.history(.final)
        var context = Self.context(.final)
        context = RugbyMatchEventPageContext10868(
            label: context.label, result: context.result, caption: context.caption, chartLabel: context.chartLabel,
            chartSpokenLabel: context.chartSpokenLabel,
            entries: context.entries + [RugbyMatchEventPageContextEntry10868(seriesID: "series.unknown", inspect: nil),
                                        RugbyMatchEventPageContextEntry10868(seriesID: " ", inspect: nil)],
            unavailableWords: context.unavailableWords, inspectHint: context.inspectHint)
        var parts = Self.parts(.final)
        parts.history = foreign
        parts.context = context
        let model = RugbyMatchEventPageModel10868(parts.input)
        XCTAssertEqual(context.entries.map { model.contextSeries($0)?.name }, ["France", "England", "Draw", nil, nil])
        XCTAssertEqual(model.contextEntrySummary(context.entries[3]), "Outcome unavailable in this update")
        // An incomplete hand-off is no control.
        var blank = Self.parts(.before)
        blank.context = Self.context(.before, inspectKeys: ["FRA": " "])
        let blankModel = RugbyMatchEventPageModel10868(blank.input)
        XCTAssertNil(blankModel.contextInspect(blank.input.context!.entries[0], canInspect: true))
        XCTAssertNotNil(blankModel.contextInspect(blank.input.context!.entries[1], canInspect: true))
    }

    // MARK: - Held selections

    func testHeldHistoryCardAndOriginalSelectionsAreOmittedAsUnavailableAndRestoredOnlyByExactIdentity() {
        // History: France's held 8:53 close withdrawn — its words; England and the draw keep their own.
        let gone = Self.history(.final, inspect: .withdrawn(Self.franceLow, "FRA"))
        XCTAssertEqual(Self.slots(gone, Self.france).last, FieldHistoryReadoutSlot10868(label: "Selected minute", display: .words("Unavailable")))
        XCTAssertEqual(Self.slots(gone, Self.england).last, Self.figureSlot("Selected minute", Self.england, Self.franceLow))
        let back = Self.history(.final, inspect: .minute(Self.franceLow))
        XCTAssertEqual(Self.slots(back, Self.france).last, Self.figureSlot("Selected minute", Self.france, Self.franceLow))

        // Card: the story reader while the story is withdrawn shows the owner's words, never the history.
        var withdrawn = Self.parts(.final)
        withdrawn.story = nil
        XCTAssertFalse(RugbyMatchEventPageModel10868(withdrawn.input).readerShows(.story))
        XCTAssertTrue(RugbyMatchEventPageModel10868(withdrawn.input).readerShows(.history))
        XCTAssertNil(RugbyMatchEventPagePresentation10868(input: withdrawn.input, mode: .reader(.story)).storyContent(reader: true))
        XCTAssertTrue(RugbyMatchEventPageModel10868(Self.page(.final)).readerShows(.story))

        // Original: the held France original withdrawn — stays held, resolves nothing; England still selects.
        var log: [String] = []
        let omitted = Self.originals(.final, omitting: "FRA")
        let view = RugbyMatchEventPagePresentation10868(input: Self.page(.final), mode: .original, originals: omitted,
                                                        onOriginalSelect: { log.append("select:\($0.identity.market)") },
                                                        onOriginalHistory: { log.append("history:\($0.actionID)") },
                                                        onInteraction: { log.append("hold") })
        let details = view.originalDetailsContent()!
        XCTAssertEqual(details.selection?.identity, Self.identity(Self.france))
        XCTAssertNil(Originals.original(in: details.catalogue, selection: details.selection))
        XCTAssertNil(Originals.recorded(catalogue: details.catalogue, selection: details.selection, context: details.recorded, hasCallback: true))
        let choices = OriginalMarketChooser9483.choices(catalogue: omitted.catalogue, selection: omitted.selection,
                                                        labels: omitted.labels, unavailableChoice: omitted.unavailableChoice)
        XCTAssertEqual(choices.map(\.label), ["England to win", "Draw"])
        XCTAssertFalse(choices.contains { $0.isSelected })
        let catalogue = RugbyMatchEventPagePresentation10868(input: Self.page(.final), mode: .catalogue, originals: omitted,
                                                             onOriginalSelect: { log.append("select:\($0.identity.market)") },
                                                             onInteraction: { log.append("hold") }).catalogueContent()!
        let cards = OriginalMarketCatalogue9483.cards(catalogue: catalogue.catalogue, selection: catalogue.selection,
                                                      labels: catalogue.labels, unavailableChoice: catalogue.unavailableChoice)
        OriginalMarketCatalogue9483.action(cards[0], onSelect: catalogue.onSelect)?()
        XCTAssertEqual(log, ["hold", "select:\(Self.england.ticker)"])
        // Restored by exact identity: the same Details and recorded history again.
        log = []
        let restored = RugbyMatchEventPagePresentation10868(input: Self.page(.final), mode: .original, originals: Self.originals(.final),
                                                            onOriginalHistory: { log.append("history:\($0.actionID)") },
                                                            onInteraction: { log.append("hold") }).originalDetailsContent()!
        guard case .recorded(let shown)? = Originals.recorded(catalogue: restored.catalogue, selection: restored.selection,
                                                              context: restored.recorded, hasCallback: true),
              let intent = Originals.intent(.explore, in: shown) else {
            return XCTFail("the restored original resolves its recorded Details")
        }
        XCTAssertEqual(intent.selection.identity, Self.identity(Self.france))
        restored.onHistory?(intent)
        XCTAssertEqual(log, ["hold", "history:original.explore"])
    }

    // MARK: - Full size

    func testFullSizeReadersUseTheSameInputsAtTheOwnersFullSizeHeight() {
        let input = Self.page(.final, inspect: .minute(Self.franceLow))
        let model = RugbyMatchEventPageModel10868(input)
        let page = input.history
        let reader = RugbyMatchEventPagePresentation10868(input: input, mode: .reader(.history)).historyContent(reader: true).input
        XCTAssertEqual(page.plotHeight, 302)
        XCTAssertEqual(reader.plotHeight, 380)
        XCTAssertNil(reader.expand)
        XCTAssertEqual(reader.series, page.series)
        XCTAssertEqual(reader.inspection, page.inspection)
        XCTAssertEqual(reader.readout, page.readout)
        XCTAssertEqual(reader.windows, page.windows)
        XCTAssertEqual(reader.domain, page.domain)
        XCTAssertEqual(reader.layout, page.layout)
        XCTAssertEqual(model.readerHistory, reader)
        // An unusable full-size height keeps the owner's own.
        XCTAssertEqual(RugbyMatchEventPageModel10868.readerPlotHeight(nil, history: 302), 302)
        XCTAssertEqual(RugbyMatchEventPageModel10868.readerPlotHeight(-1, history: 302), 302)
        XCTAssertEqual(RugbyMatchEventPageModel10868.readerPlotHeight(0, history: 302), 302)
        XCTAssertEqual(RugbyMatchEventPageModel10868.readerPlotHeight(.infinity, history: 302), 302)
        XCTAssertEqual(RugbyMatchEventPageModel10868.readerPlotHeight(.nan, history: 302), 302)
        // A usable one is used when taller, and never makes full size shorter than the page.
        XCTAssertEqual(RugbyMatchEventPageModel10868.readerPlotHeight(380, history: 302), 380)
        XCTAssertEqual(RugbyMatchEventPageModel10868.readerPlotHeight(150, history: 302), 302)
        XCTAssertEqual(RugbyMatchEventPageModel10868.readerPlotHeight(302, history: 302), 302)
        var shorter = Self.parts(.final, inspect: .minute(Self.franceLow))
        shorter.readerPlotHeight = 150
        let shorterReader = RugbyMatchEventPagePresentation10868(input: shorter.input, mode: .reader(.history)).historyContent(reader: true).input
        XCTAssertEqual(shorterReader.plotHeight, 302)
        XCTAssertEqual(RugbyMatchEventPageModel10868(shorter.input).readerHistory.plotHeight, 302)
        XCTAssertEqual(shorter.input.readerPlotHeight, 150)
        XCTAssertEqual(shorter.input.history.plotHeight, 302)
        var unset = Self.parts(.final)
        unset.readerPlotHeight = nil
        XCTAssertEqual(RugbyMatchEventPageModel10868(unset.input).readerHistory.plotHeight, 302)
        // The story full size reads the same input, without its full-card entry.
        let inline = RugbyMatchEventPagePresentation10868(input: input, onReaderOpen: { _ in }).storyContent(reader: false)!
        let full = RugbyMatchEventPagePresentation10868(input: input, mode: .reader(.story), onReaderOpen: { _ in }).storyContent(reader: true)!
        XCTAssertEqual(inline.input, full.input)
        XCTAssertNotNil(inline.onExpand)
        XCTAssertNil(full.onExpand)
    }

    // MARK: - Holds

    func testEachPageActionHoldsOnceReadersAndPassiveReadsDoNotAndAbsentCallbacksDrawNoControl() {
        var log: [String] = []
        let input = Self.page(.final)
        let originals = Self.originals(.final)
        func view(_ mode: RugbyMatchEventPageMode10868 = .page, hook: Bool = true) -> RugbyMatchEventPagePresentation10868 {
            RugbyMatchEventPagePresentation10868(
                input: input, mode: mode, originals: originals,
                onAbout: { log.append("about") },
                onSource: { log.append("source:\($0)") },
                onLink: { log.append("link:\($0.id)") },
                onCatalogue: { log.append("catalogue") },
                onOriginalSelect: { log.append("select:\($0.identity.market)") },
                onOriginalHistory: { log.append("history:\($0.actionID)") },
                onOriginalOpen: { log.append("open:\($0.ref.marketID):\($0.observation ?? "none")") },
                onInspect: { log.append("inspect:\($0.observation ?? "none")") },
                onHistoryAction: { log.append("chart:\($0)") },
                onHistoryInspectionChoice: { log.append("choice:\($0)") },
                onHistoryPlotPosition: { log.append("plot:\($0)") },
                onReaderOpen: { log.append("reader:\($0.rawValue)") },
                onStoryDetails: { log.append("story-details") },
                onInteraction: hook ? { log.append("hold") } : nil)
        }

        // Building and reading every leaf and mode calls nothing.
        let page = view()
        let headline = page.headlineContent()!
        let anchor = page.historyContent(reader: false)
        let context = page.contextContent()!
        let story = page.storyContent(reader: false)!
        let choices = page.choicesContent()!
        _ = view(.reader(.history)).historyContent(reader: true)
        _ = view(.reader(.story)).storyContent(reader: true)
        _ = view(.catalogue).catalogueContent()
        _ = view(.original).originalDetailsContent()
        _ = view(.about).aboutContent()
        _ = view(.source("rules.FRA")).sourceContent("rules.FRA")
        _ = page.catalogueAction
        _ = page.model.readerHistory
        _ = page.comparisonContent(reader: false).entries
        _ = view(.reader(.history)).comparisonContent(reader: true).entries
        XCTAssertEqual(log, [])

        // Each page action: the hook once, then the exact payload.
        let headlineModel = FieldHeadlineModel10868(headline.input)
        headline.onAbout?()
        if let open = headlineModel.openAction(headlineModel.competitors[1], canOpen: true) { headline.onOpen?(open) }
        anchor.onAction?("window.all")
        anchor.onPlotPosition?(-2)
        context.onChart?()
        let entry = input.context!.entries[0]
        if let inspect = page.model.contextInspect(entry, canInspect: true) { context.onInspect?(inspect) }
        let storyModel = HistoricalChanceModel10868(story.input)
        if let open = storyModel.openAction(storyModel.sides[1], canOpen: true) { story.onOpen?(open) }
        story.onExpand?()
        story.onDetails?()
        let choice = OriginalMarketChooser9483.choices(catalogue: choices.catalogue, selection: choices.selection,
                                                       labels: choices.labels, unavailableChoice: choices.unavailableChoice)[2]
        OriginalMarketChooser9483.action(choice, onSelect: choices.onSelect)?()
        page.catalogueAction?()
        XCTAssertEqual(log, [
            "hold", "about",
            "hold", "open:\(Self.england.ticker):none",
            "hold", "chart:window.all",
            "hold", "plot:-2.0",
            "hold", "chart:history.expand",
            "hold", "inspect:\(Self.key(Self.france, Self.france.baseline))",
            "hold", "inspect:\(Self.key(Self.france, Self.franceLow))",
            "hold", "reader:story",
            "hold", "story-details",
            "hold", "select:\(Self.draw.ticker)",
            "hold", "catalogue",
        ])

        // Already-held full-size content keeps the exact callbacks: no second hold.
        log = []
        view(.reader(.history)).historyContent(reader: true).onAction?("history.next")
        let fullStory = view(.reader(.story)).storyContent(reader: true)!
        if let open = storyModel.openAction(storyModel.sides[0], canOpen: true) { fullStory.onOpen?(open) }
        fullStory.onDetails?()
        view(.reader(.story)).openReaderAbout()
        let about = view(.about).aboutContent()!
        about.sourceAction("rules.FRA")?()
        about.linkAction(Self.espnLink)?()
        XCTAssertEqual(log, ["chart:history.next", "inspect:\(Self.key(Self.france, Self.france.baseline))", "story-details",
                             "about", "source:rules.FRA", "link:espn"])

        // No hook: every page action is the owner's own.
        log = []
        view(hook: false).contextContent()?.onChart?()
        XCTAssertEqual(log, ["chart:history.expand"])

        // Absent callbacks: no control and no hook call.
        log = []
        let bare = RugbyMatchEventPagePresentation10868(input: input, originals: originals, onInteraction: { log.append("hold") })
        XCTAssertNil(bare.headlineContent()?.onAbout)
        XCTAssertNil(bare.headlineContent()?.onOpen)
        XCTAssertNil(bare.historyContent(reader: false).onAction)
        XCTAssertNil(bare.contextContent()?.onChart)
        XCTAssertNil(bare.contextContent()?.onInspect)
        XCTAssertNil(bare.storyContent(reader: false)?.onOpen)
        XCTAssertNil(bare.storyContent(reader: false)?.onExpand)
        XCTAssertNil(bare.storyContent(reader: false)?.onDetails)
        XCTAssertNil(bare.choicesContent()?.onSelect)
        XCTAssertNil(bare.catalogueAction)
        XCTAssertNil(bare.originalDetailsContent()?.onHistory)
        XCTAssertNil(bare.model.contextInspect(entry, canInspect: false))
        XCTAssertNil(bare.model.contextChartID(canOpen: false))
        bare.openReaderAbout()
        XCTAssertEqual(log, [])
        // A source id naming no single document is words only.
        var doubled = Self.parts(.final)
        doubled.sources += Self.sources(.final)
        XCTAssertNil(RugbyMatchEventPageModel10868(doubled.input).source("rules.FRA"))
        XCTAssertEqual(RugbyMatchEventPageModel10868(doubled.input).sourceIDs, [])
    }

    // MARK: - Arrangement

    func testPhoneWideAndAccessibilityArrangementsKeepTheChartHeight() {
        XCTAssertEqual(RugbyMatchEventPageModel10868.arrangements(sizeClass: .compact, accessibilitySize: false), [.stacked])
        XCTAssertEqual(RugbyMatchEventPageModel10868.arrangements(sizeClass: .regular, accessibilitySize: false), [.sideBySide, .stacked])
        XCTAssertEqual(RugbyMatchEventPageModel10868.arrangements(sizeClass: nil, accessibilitySize: false), [.sideBySide, .stacked])
        XCTAssertEqual(RugbyMatchEventPageModel10868.arrangements(sizeClass: .regular, accessibilitySize: true), [.stacked])
        XCTAssertTrue(RugbyMatchEventPageModel10868.showsContext(.stacked))
        XCTAssertFalse(RugbyMatchEventPageModel10868.showsContext(.sideBySide))
        // The accepted leaves' own reflow: headline rows and stacked story readouts at accessibility sizes.
        XCTAssertEqual(FieldHeadlineGeometry10868.arrangement(available: 900, count: 3, figureWidths: [60, 60, 60], spacing: 12,
                                                             accessibilitySize: true), .rows)
        XCTAssertEqual(HistoricalChanceGeometry10868.readoutArrangements(accessibilitySize: true), [.stacked])
        XCTAssertEqual(HistoricalChanceGeometry10868.readoutArrangements(accessibilitySize: false), [.sideBySide, .stacked])
        // The plot height is the owner's in every arrangement: never compressed.
        XCTAssertEqual(Self.page(.before).history.plotHeight, 302)
        XCTAssertEqual(RugbyMatchEventPageModel10868(Self.page(.before)).readerHistory.plotHeight, 380)
        // The comparison: a row's slots side by side where they fit, stacked at accessibility sizes.
        XCTAssertEqual(RugbyMatchEventPageComparisonPresentation10868.slotArrangements(accessibilitySize: false), [.sideBySide, .stacked])
        XCTAssertEqual(RugbyMatchEventPageComparisonPresentation10868.slotArrangements(accessibilitySize: true), [.stacked])
        // Its outcomes: columns while every whole measured name and figure fits an equal share, else rows; rows at
        // accessibility sizes; a figure wider than its share never shrinks into it.
        let spacing = RugbyMatchEventPageComparisonPresentation10868.columnSpacing
        XCTAssertEqual(FieldHeadlineGeometry10868.arrangement(available: 900, count: 3, figureWidths: [96, 96, 96, 78, 78, 78],
                                                             spacing: spacing, accessibilitySize: false), .columns)
        XCTAssertEqual(FieldHeadlineGeometry10868.arrangement(available: 300, count: 3, figureWidths: [96, 96, 96, 78, 78, 78],
                                                             spacing: spacing, accessibilitySize: false), .rows)
        XCTAssertEqual(FieldHeadlineGeometry10868.arrangement(available: 900, count: 3, figureWidths: [96, 96, 96, 78, 78, 78],
                                                             spacing: spacing, accessibilitySize: true), .rows)
        XCTAssertEqual(FieldHeadlineGeometry10868.arrangement(available: 900, count: 3, figureWidths: [96, 300, 96],
                                                             spacing: spacing, accessibilitySize: false), .rows)
    }

    // MARK: - Comparison

    func testTheComparisonShowsEveryOutcomesResolvedReadoutsAtOneFigureSizeInTheSameViewInlineAndFullSize() {
        XCTAssertEqual(RugbyMatchEventPageModel10868.comparisonFigureSize, 26)
        let cases: [(RugbyMatchEventPagePhase10868, Inspect?)] = [
            (.before, nil), (.during, nil), (.final, nil), (.final, .minute(Self.franceLow)), (.final, .minute(1773521640)),
        ]
        for (phase, inspect) in cases {
            let input = Self.page(phase, inspect: inspect)
            let pageView = RugbyMatchEventPagePresentation10868(input: input)
            let readerView = RugbyMatchEventPagePresentation10868(input: input, mode: .reader(.history))
            let inline = pageView.comparisonContent(reader: false)
            let full = readerView.comparisonContent(reader: true)
            // The same View and readouts inline and full size, read from the history copy drawn beside it.
            XCTAssertEqual(inline.entries, full.entries, "\(phase)")
            XCTAssertEqual(inline.label, Self.copy.comparisonLabel)
            XCTAssertEqual(full.label, Self.copy.comparisonLabel)
            XCTAssertEqual(inline.history, pageView.historyContent(reader: false).input)
            XCTAssertEqual(full.history, readerView.historyContent(reader: true).input)
            // Every outcome in the owner's order, by its whole name and shape, resolved by the history itself.
            XCTAssertEqual(inline.entries.map(\.series), input.history.series)
            XCTAssertEqual(inline.entries.map(\.series.name), Self.outcomes.map(\.name))
            XCTAssertEqual(inline.entries.map(\.series.shape), Self.outcomes.map(\.shape))
            for (entry, outcome) in zip(inline.entries, Self.outcomes) {
                XCTAssertEqual(entry.slots, Self.slots(input.history, outcome), "\(phase) \(outcome.key)")
                XCTAssertEqual(entry.note, FieldHistoryGeometry10868.keyNote(entry.series, in: input.history))
                XCTAssertFalse(entry.isSelected)
            }
            let count = phase == .before && inspect == nil ? 1 : 2
            XCTAssertEqual(inline.entries.map(\.slots.count), [count, count, count], "\(phase)")
        }

        // Spoken: the whole name, then each slot with its own label, figure and date.
        let before = RugbyMatchEventPagePresentation10868(input: Self.page(.before)).comparisonContent(reader: false)
        XCTAssertNil(before.entries[0].note)
        XCTAssertEqual(RugbyMatchEventPageComparisonPresentation10868.spoken(before.entries[0]),
                       "\(Self.france.name). Before match \(Self.figure(Self.close(Self.france, Self.france.baseline)!)), \(Self.provenance(Self.france.baseline))")
        XCTAssertEqual(RugbyMatchEventPageComparisonPresentation10868.figures(before.entries),
                       Self.outcomes.map { Self.figure(Self.close($0, $0.baseline)!) })

        // An exact minute the draw did not trade keeps the history's words — no figure, nothing carried forward.
        let sparse = RugbyMatchEventPagePresentation10868(input: Self.page(.final, inspect: .minute(1773521640))).comparisonContent(reader: false)
        XCTAssertEqual(sparse.entries[2].slots.last,
                       FieldHistoryReadoutSlot10868(label: "Selected minute", display: .words("No trade in this exact minute")))
        XCTAssertEqual(RugbyMatchEventPageComparisonPresentation10868.figures([sparse.entries[2]]),
                       [Self.figure(Self.close(Self.draw, Self.draw.baseline)!)])
        XCTAssertTrue(RugbyMatchEventPageComparisonPresentation10868.spoken(sparse.entries[2])
            .hasSuffix("Selected minute: No trade in this exact minute"))

        // One observation in two slots stays two slots; equal values at two minutes keep their own dates.
        let same = RugbyMatchEventPagePresentation10868(input: Self.page(.before, inspect: .minute(1773518880))).comparisonContent(reader: false)
        XCTAssertEqual(same.entries[0].slots, [
            Self.figureSlot("Before match", Self.france, 1773518880), Self.figureSlot("Selected minute", Self.france, 1773518880),
        ])
        XCTAssertEqual(RugbyMatchEventPageComparisonPresentation10868.figures([same.entries[0]]).count, 2)
        let first = RugbyMatchEventPagePresentation10868(input: Self.page(.final, inspect: .minute(1773525900))).comparisonContent(reader: false)
        let second = RugbyMatchEventPagePresentation10868(input: Self.page(.final, inspect: .minute(1773525960)), mode: .reader(.history))
            .comparisonContent(reader: true)
        XCTAssertEqual(first.entries[1].slots.last, Self.figureSlot("Selected minute", Self.england, 1773525900))
        XCTAssertEqual(second.entries[1].slots.last, Self.figureSlot("Selected minute", Self.england, 1773525960))
        XCTAssertNotEqual(RugbyMatchEventPageComparisonPresentation10868.spoken(first.entries[1]),
                          RugbyMatchEventPageComparisonPresentation10868.spoken(second.entries[1]))

        // The history's exact selection is marked on that outcome alone.
        var selected = Self.parts(.final)
        selected.history = Self.history(.final, selecting: Self.england)
        let marked = RugbyMatchEventPagePresentation10868(input: selected.input).comparisonContent(reader: false)
        XCTAssertEqual(marked.entries.map(\.isSelected), [false, true, false])
    }

    func testThePageHidesOnlyTheDuplicateKeyInAPresentationCopyAndTheOwnersHistoryStaysWhole() {
        let owner = Self.history(.final, inspect: .minute(Self.franceLow))
        let input = Self.page(.final, inspect: .minute(Self.franceLow))
        let model = RugbyMatchEventPageModel10868(input)
        let presented = model.presentedHistory
        XCTAssertTrue(model.hidesSharedKey)
        // The owner's input is untouched.
        XCTAssertEqual(input.history, owner)
        XCTAssertEqual(model.input.history, owner)
        XCTAssertTrue(owner.showsKey)
        // The copy differs only in the key: every series, run, readout, inspection, key word, action and plot field is the owner's.
        XCTAssertFalse(presented.showsKey)
        var restored = presented
        restored.showsKey = true
        XCTAssertEqual(restored, owner)
        var fullRestored = model.readerHistory
        fullRestored.showsKey = true
        XCTAssertEqual(fullRestored, RugbyMatchEventPageModel10868.presentationCopy(owner, plotHeight: 380, expand: nil, showsKey: true))
        XCTAssertEqual(FieldHistoryGeometry10868.actions(presented), FieldHistoryGeometry10868.actions(owner))
        XCTAssertEqual(FieldHistoryGeometry10868.drawsStyle(.hollow, in: presented), FieldHistoryGeometry10868.drawsStyle(.hollow, in: owner))
        XCTAssertEqual(FieldHistoryGeometry10868.drawsStyle(.filled, in: presented), FieldHistoryGeometry10868.drawsStyle(.filled, in: owner))
        // Only the readout key block goes, inline and full size; the page draws the copy.
        XCTAssertEqual(FieldHistoryGeometry10868.blocksAbovePlot(owner), [.selectionWords, .key])
        XCTAssertEqual(FieldHistoryGeometry10868.blocksAbovePlot(presented), [.selectionWords])
        XCTAssertEqual(FieldHistoryGeometry10868.blocksAbovePlot(model.readerHistory), [.selectionWords])
        XCTAssertEqual(RugbyMatchEventPagePresentation10868(input: input).historyContent(reader: false).input, presented)

        // A key that carries more than readouts stays: a choose control or the owner's key context.
        for keyed in [Self.history(.final, choosing: true), Self.history(.final, keyContext: true)] {
            var parts = Self.parts(.final)
            parts.history = keyed
            let keyedModel = RugbyMatchEventPageModel10868(parts.input)
            XCTAssertFalse(keyedModel.hidesSharedKey)
            XCTAssertEqual(keyedModel.presentedHistory, keyed)
            XCTAssertTrue(keyedModel.readerHistory.showsKey)
            XCTAssertEqual(FieldHistoryGeometry10868.blocksAbovePlot(keyedModel.presentedHistory), [.selectionWords, .key])
            XCTAssertEqual(RugbyMatchEventPagePresentation10868(input: parts.input).comparisonContent(reader: false).entries.map(\.slots),
                           keyed.series.map { FieldHistoryGeometry10868.readoutSlots($0, in: keyed) })
        }
        // An owner that hides its own key keeps it hidden.
        var ownHidden = Self.parts(.final)
        ownHidden.history.showsKey = false
        XCTAssertFalse(RugbyMatchEventPageModel10868(ownHidden.input).presentedHistory.showsKey)
        XCTAssertFalse(RugbyMatchEventPageModel10868(ownHidden.input).readerHistory.showsKey)
    }

    // MARK: - Shared control targets (prepared for the 44pt correction; NOT RUN)

    func testEveryRugbyControlTargetIsFlooredAt44AndGrowsWithLargerText() {
        typealias Target = RugbyMatchEventPageControlTarget10868
        XCTAssertEqual(Target.minimum, 44)
        // The hit length: never below 44, the scaled metric above it, 44 when not finite.
        let scaled: [CGFloat] = [30, 44, 62, 0, -4, .nan, .infinity, -.infinity]
        XCTAssertEqual(scaled.map { Target.length($0) }, [44, 44, 62, 44, 44, 44, 44, 44])

        func fitted<V: View>(_ view: V, at size: DynamicTypeSize) -> CGSize {
            hostForMeasurement(view.fixedSize(), at: size)
                .sizeThatFits(in: CGSize(width: CGFloat.greatestFiniteMagnitude, height: .greatestFiniteMagnitude))
        }
        var heights: [CGFloat] = []
        for size in [DynamicTypeSize.xSmall, .large, .accessibility3] {
            // Both axes: at least 44 by 44 with a one-letter label at every text size.
            let both = fitted(Text("X").font(.caption2).modifier(Target()), at: size)
            XCTAssertTrue(both.width.isFinite && both.height.isFinite, "\(size)")
            XCTAssertGreaterThanOrEqual(both.width, 44, "\(size)")
            XCTAssertGreaterThanOrEqual(both.height, 44, "\(size)")
            heights.append(both.height)
            // Height only: the width stays the label's own.
            let tall = fitted(Text("X").font(.caption2).modifier(Target(width: false)), at: size)
            XCTAssertGreaterThanOrEqual(tall.height, 44, "\(size)")
            XCTAssertLessThan(tall.width, 44, "\(size)")
            // Width only: the height stays the label's own.
            let wide = fitted(Text("X").font(.caption2).modifier(Target(height: false)), at: size)
            XCTAssertGreaterThanOrEqual(wide.width, 44, "\(size)")
            XCTAssertLessThan(wide.height, 44, "\(size)")
        }
        // The default size is exactly the old 44; larger text still grows the target.
        XCTAssertEqual(heights[1], 44, accuracy: 0.5)
        XCTAssertGreaterThan(heights[2], heights[0] + 1)

        // Filling the width spans what is offered; without it the label keeps its own width.
        let offered = CGSize(width: 200, height: CGFloat.greatestFiniteMagnitude)
        let spanning = hostForMeasurement(Text("X").modifier(Target(width: false, fillsWidth: true, alignment: .topLeading)),
                                          at: .xSmall).sizeThatFits(in: offered)
        XCTAssertEqual(spanning.width, 200, accuracy: 0.5)
        XCTAssertGreaterThanOrEqual(spanning.height, 44)
        let own = hostForMeasurement(Text("X").modifier(Target(width: false)), at: .xSmall).sizeThatFits(in: offered)
        XCTAssertLessThan(own.width, 44)
        XCTAssertGreaterThanOrEqual(own.height, 44)
    }

    func testInfoSourceAndLinkControlsKeep44PointTargetsWithShortLabelsAtEveryTextSize() {
        var log: [String] = []
        let link = RugbyMatchEventPageLink10868(id: "x", label: "X", url: URL(string: Self.espnURL)!)
        func content(source: Bool = false, linked: Bool = false, callbacks: Bool = true) -> RugbyMatchEventPageSectionsContent10868 {
            RugbyMatchEventPageSectionsContent10868(
                title: "",
                sections: [RugbyMatchEventPageSection10868(title: "", paragraphs: ["W"], link: linked ? link : nil,
                                                           sourceID: source ? "rules.R" : nil)],
                sourceIDs: ["rules.R"], sourceLabel: "R",
                onLink: callbacks ? { log.append("link:\($0.id):\($0.url.absoluteString)") } : nil,
                onSource: callbacks ? { log.append("source:\($0)") } : nil)
        }
        func height(_ view: RugbyMatchEventPageSectionsContent10868, at size: DynamicTypeSize) -> CGFloat {
            hostForMeasurement(view.frame(width: 320), at: size)
                .sizeThatFits(in: CGSize(width: 320, height: CGFloat.greatestFiniteMagnitude)).height
        }
        func width(_ view: RugbyMatchEventPageSectionsContent10868, at size: DynamicTypeSize) -> CGFloat {
            hostForMeasurement(view.fixedSize(), at: size)
                .sizeThatFits(in: CGSize(width: CGFloat.greatestFiniteMagnitude, height: .greatestFiniteMagnitude)).width
        }

        // A one-letter source or link label still gives a 44pt-wide control at the smallest size.
        XCTAssertGreaterThanOrEqual(width(content(source: true), at: .xSmall), 44)
        XCTAssertGreaterThanOrEqual(width(content(linked: true), at: .xSmall), 44)
        // Words only without callbacks: the same short labels stay narrower than a control.
        XCTAssertLessThan(width(content(source: true, linked: true, callbacks: false), at: .xSmall), 44)

        // Each control adds at least its 44pt target plus the section's 6pt spacing, growing with larger text.
        var sourceAdded: [CGFloat] = []
        var linkAdded: [CGFloat] = []
        for size in [DynamicTypeSize.xSmall, .large, .accessibility3] {
            let base = height(content(), at: size)
            XCTAssertTrue(base.isFinite && base > 0, "\(size)")
            sourceAdded.append(height(content(source: true), at: size) - base)
            linkAdded.append(height(content(linked: true), at: size) - base)
            XCTAssertGreaterThanOrEqual(sourceAdded.last!, 44 + 6 - 0.5, "source \(size)")
            XCTAssertGreaterThanOrEqual(linkAdded.last!, 44 + 6 - 0.5, "link \(size)")
            // No callback: no source control at all, and the link is its own words, not a dead 44pt row.
            XCTAssertEqual(height(content(source: true, callbacks: false), at: size), base, accuracy: 0.5, "\(size)")
        }
        XCTAssertGreaterThan(sourceAdded[2], sourceAdded[0] + 1)
        XCTAssertGreaterThan(linkAdded[2], linkAdded[0] + 1)
        let wordsAdded = height(content(linked: true, callbacks: false), at: .xSmall) - height(content(), at: .xSmall)
        XCTAssertGreaterThan(wordsAdded, 0)
        XCTAssertLessThan(wordsAdded, 44 + 6 - 0.5)
        // Building and laying out called nothing.
        XCTAssertEqual(log, [])

        // The exact payloads, unchanged: the same link and the same resolving source id.
        let live = content(source: true, linked: true)
        live.linkAction(link)?()
        live.sourceAction("rules.R")?()
        XCTAssertNil(live.linkAction(nil))
        XCTAssertNil(live.sourceAction(nil))
        XCTAssertNil(live.sourceAction("rules.other"))
        XCTAssertNil(content(source: true, linked: true, callbacks: false).linkAction(link))
        XCTAssertNil(content(source: true, linked: true, callbacks: false).sourceAction("rules.R"))
        XCTAssertEqual(log, ["link:x:\(link.url.absoluteString)", "source:rules.R"])
    }

    func testChartEntryCatalogueAndReaderInfoKeepTheirExactHoldsAndPayloadsWithTheFlooredTargets() throws {
        var log: [String] = []
        let input = Self.page(.final)
        let originals = Self.originals(.final)
        func view(_ mode: RugbyMatchEventPageMode10868 = .page) -> RugbyMatchEventPagePresentation10868 {
            RugbyMatchEventPagePresentation10868(
                input: input, mode: mode, originals: originals,
                onAbout: { log.append("about") },
                onSource: { log.append("source:\($0)") },
                onLink: { log.append("link:\($0.id)") },
                onCatalogue: { log.append("catalogue") },
                onInspect: { log.append("inspect:\($0.observation ?? "none")") },
                onHistoryAction: { log.append("chart:\($0)") },
                onInteraction: { log.append("hold") })
        }
        func fitted<V: View>(_ view: V, width: CGFloat) -> CGSize {
            hostForMeasurement(view.frame(width: width), at: .xSmall)
                .sizeThatFits(in: CGSize(width: width, height: CGFloat.greatestFiniteMagnitude))
        }
        func line<V: View>(_ view: V) -> CGFloat {
            hostForMeasurement(view.fixedSize(), at: .xSmall)
                .sizeThatFits(in: CGSize(width: CGFloat.greatestFiniteMagnitude, height: .greatestFiniteMagnitude)).height
        }

        // Every mode hosts at the smallest size with finite geometry, and laying out calls nothing.
        for mode in [RugbyMatchEventPageMode10868.page, .reader(.history), .reader(.story), .catalogue, .about] {
            let host = hostForMeasurement(view(mode).environment(\.horizontalSizeClass, .compact), at: .xSmall)
            host.view.frame = CGRect(x: 0, y: 0, width: 393, height: 2000)
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            let size = host.sizeThatFits(in: CGSize(width: 393, height: CGFloat.greatestFiniteMagnitude))
            XCTAssertTrue(size.width.isFinite && size.height.isFinite && size.height > 0, "\(mode)")
            XCTAssertLessThanOrEqual(size.width, 393.5, "\(mode)")
        }
        XCTAssertEqual(log, [])

        // Chart: the header row is the 44pt target, not the shorter result line beside it.
        let model = RugbyMatchEventPageModel10868(input)
        let finalContext = Self.context(.final)
        let resultLine = line(Text(finalContext.result).font(.subheadline.weight(.semibold)))
        XCTAssertLessThan(resultLine, 44)
        let withChart = fitted(RugbyMatchEventPageContextPresentation10868(model: model, context: finalContext,
                                                                            onChart: { log.append("chart") }), width: 393)
        let withoutChart = fitted(RugbyMatchEventPageContextPresentation10868(model: model, context: finalContext), width: 393)
        XCTAssertGreaterThanOrEqual(withChart.height - withoutChart.height + resultLine, 44 - 0.5)

        // Reader Info: the full-size header is the 44pt target, not the one-line title beside it.
        let titleLine = line(Text(input.reader.title).font(.headline))
        XCTAssertLessThan(titleLine, 44)
        let withInfo = fitted(RugbyMatchEventPagePresentation10868(input: input, mode: .reader(.history), originals: originals,
                                                                    onAbout: { log.append("about") }), width: 393)
        let withoutInfo = fitted(RugbyMatchEventPagePresentation10868(input: input, mode: .reader(.history), originals: originals),
                                 width: 393)
        XCTAssertGreaterThanOrEqual(withInfo.height - withoutInfo.height + titleLine, 44 - 0.5)

        // Catalogue entry: at least 44pt plus the 16pt spacing above it in the stacked page.
        let withCatalogue = fitted(RugbyMatchEventPagePresentation10868(input: input, originals: originals,
                                                                         onCatalogue: { log.append("catalogue") })
                                       .environment(\.horizontalSizeClass, .compact), width: 393)
        let withoutCatalogue = fitted(RugbyMatchEventPagePresentation10868(input: input, originals: originals)
                                          .environment(\.horizontalSizeClass, .compact), width: 393)
        XCTAssertGreaterThanOrEqual(withCatalogue.height - withoutCatalogue.height, 44 + 16 - 0.5)
        XCTAssertEqual(log, [])

        // Each action, unchanged: the page hook once, then the exact payload; full-size and About exact, no hold.
        let page = view()
        let context = try XCTUnwrap(page.contextContent())
        context.onChart?()
        let entry = try XCTUnwrap(input.context?.entries.first)
        let inspect = try XCTUnwrap(page.model.contextInspect(entry, canInspect: true))
        context.onInspect?(inspect)
        page.catalogueAction?()
        view(.reader(.history)).openReaderAbout()
        let about = try XCTUnwrap(view(.about).aboutContent())
        about.sourceAction("rules.FRA")?()
        about.linkAction(Self.espnLink)?()
        XCTAssertEqual(log, [
            "hold", "chart:history.expand",
            "hold", "inspect:\(Self.key(Self.france, Self.france.baseline))",
            "hold", "catalogue",
            "about", "source:rules.FRA", "link:espn",
        ])

        // No callbacks: still no control anywhere.
        log = []
        let bare = RugbyMatchEventPagePresentation10868(input: input, originals: originals, onInteraction: { log.append("hold") })
        XCTAssertNil(bare.contextContent()?.onChart)
        XCTAssertNil(bare.contextContent()?.onInspect)
        XCTAssertNil(bare.catalogueAction)
        XCTAssertNil(bare.aboutOpener())
        XCTAssertNil(bare.aboutContent()?.linkAction(Self.espnLink))
        XCTAssertNil(bare.aboutContent()?.sourceAction("rules.FRA"))
        bare.openReaderAbout()
        XCTAssertEqual(log, [])

        // A STATIC entry is not a control and is not floored: at the smallest size it keeps its raw scaled frame,
        // below 44pt, whether or not the page can inspect. Its height is isolated by swapping its one-line words for
        // words long enough to set their own height: everything else in the two contexts is identical.
        let column: CGFloat = 240
        let words = "Outcome unavailable in this update"
        let longWords = Array(repeating: words, count: 6).joined(separator: " ")
        func unresolved(_ unavailable: String) -> RugbyMatchEventPageContext10868 {
            RugbyMatchEventPageContext10868(
                label: finalContext.label, result: finalContext.result, caption: finalContext.caption,
                chartLabel: finalContext.chartLabel, chartSpokenLabel: finalContext.chartSpokenLabel,
                entries: [RugbyMatchEventPageContextEntry10868(seriesID: "series.none", inspect: nil)],
                unavailableWords: unavailable, inspectHint: finalContext.inspectHint)
        }
        func contextHeight(_ context: RugbyMatchEventPageContext10868, inspects: Bool, width: CGFloat) -> CGFloat {
            fitted(RugbyMatchEventPageContextPresentation10868(
                model: model, context: context,
                onInspect: inspects ? { log.append("inspect:\($0.observation ?? "none")") } : nil), width: width).height
        }
        func wordsHeight<V: View>(_ text: V) -> CGFloat {
            hostForMeasurement(text, at: .xSmall).sizeThatFits(in: CGSize(width: column, height: CGFloat.greatestFiniteMagnitude)).height
        }
        let oneLine = wordsHeight(Text(words).font(.footnote).fixedSize(horizontal: false, vertical: true))
        let manyLines = wordsHeight(Text(longWords).font(.footnote).fixedSize(horizontal: false, vertical: true))
        XCTAssertLessThan(oneLine, 44)
        XCTAssertGreaterThan(manyLines, 50)
        XCTAssertNil(model.contextInspect(unresolved(words).entries[0], canInspect: true))
        var staticEntries: [CGFloat] = []
        for inspects in [false, true] {
            let staticEntry = manyLines - (contextHeight(unresolved(longWords), inspects: inspects, width: column)
                                           - contextHeight(unresolved(words), inspects: inspects, width: column))
            XCTAssertGreaterThanOrEqual(staticEntry, oneLine - 0.5, "inspects: \(inspects)")
            XCTAssertLessThan(staticEntry, 44 - 0.5, "a static entry is not floored; inspects: \(inspects)")
            staticEntries.append(staticEntry)
        }
        XCTAssertEqual(contextHeight(unresolved(words), inspects: true, width: column),
                       contextHeight(unresolved(words), inspects: false, width: column), accuracy: 0.5)
        // Entries already taller than 44pt measure the same static and inspectable: the floor moves nothing there.
        XCTAssertEqual(contextHeight(finalContext, inspects: true, width: 393),
                       contextHeight(finalContext, inspects: false, width: 393), accuracy: 0.5)
        XCTAssertEqual(log, [])

        // Final positive control: the inspect path's floor on the same one-line words, measured the same way, is 44pt
        // or more, so the static entry's smaller height above is the unfloored frame and not the measurement.
        let floored = wordsHeight(Text(words).font(.footnote).fixedSize(horizontal: false, vertical: true)
            .modifier(RugbyMatchEventPageControlTarget10868(width: false, fillsWidth: true, alignment: .topLeading)))
        XCTAssertGreaterThanOrEqual(floored, 44)
        XCTAssertGreaterThan(floored, (staticEntries.max() ?? 44) + 0.5)
    }
}
