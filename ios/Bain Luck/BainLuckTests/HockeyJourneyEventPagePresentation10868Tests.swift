import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the hockey journey screen (`nhl-journey`) composed from the
/// accepted leaves plus its one bounded comparison matrix.
///
/// The view is SwiftUI and is not rasterised here. What is asserted is the
/// composition only: which actual leaf Views the page mounts at each game
/// phase, that each receives the owner's input unchanged, the matrix's typed
/// columns, lead and independent value-or-absence slots, each channel's own
/// clock, the history's guides at or before its frame, the story stream's
/// card-to-leaf wiring, the activation hook before each card action and
/// disclosure write, the full-size history without its expand control, the
/// original catalogue and Details, the arrangement candidates, and that
/// nothing fires passively. Each leaf's own rules stay with its own tests;
/// nothing here claims a rendered fit, a native runtime, VoiceOver behaviour,
/// a stream hold qualification, a production binding, or any other NHL route.
///
/// ARCHIVED raw values come from Minnesota Wild–Boston Bruins, October 3, 2026
/// (event 15169793, ESPN 401891814), as retained in the pinned prototype
/// captures `hockeyLive.json` (sha256 60c5a526…e434), `hockeyContributions.json`
/// (dae3c3ea…de30), the pregame projection read by `totalPregameForecast.ts`
/// (43133159…72e00aa) from `atlas.json` (ff1fbc3e…00a5), and the reference's
/// final-history wire `finalHistoryEvidence.json` (de3ef778…9093, key `nhl`,
/// source `nhl-15169793-history.json`) as qualified by `finalHistoryEvidence.ts`
/// (c1ad39b0…0b97) and scoped by `hockeyJourney.ts` (fc03adcd…aec3):
/// - last pregame blend Minnesota 0.66 / Boston 0.33999999999999997 at
///   2026-10-03T23:59:00Z — Boston is the owner data's documented complement,
///   copied, never computed here;
/// - pregame score forecast Minnesota 4.0, Boston 2.5 goals at 23:46:00Z, one
///   sportsbook; no in-game projected final exists;
/// - listed start 00:00Z; verified period starts P1 00:14:32Z, P2 01:12:10Z,
///   P3 02:09:29Z; goals Jeannot (BOS) 00:18:16Z, Kaprizov 01:22:09Z, Hughes
///   01:38:44Z, Spurgeon 02:13:55Z, Kaprizov 02:45:07Z — known game events;
/// - checkpoints: first intermission 0–1 at 00:53:13Z; late second period,
///   4:09 left, 2–1 at 01:45:25Z (the live example here); early third period,
///   16:36 left, 3–1 at 02:14:50Z; final 4–1 from the ESPN result, with no
///   exact final-score time;
/// - a REDUCED SUBSET of recorded per-minute observations, NOT the complete
///   journey: each run holds only rows consecutive in its source, and an
///   omitted span starts a new run, so no line joins across rows left out
///   here. Minnesota is the recorded blend; Boston is the reference's
///   documented binary-owner relation (`away: 1 - home`), copied as the
///   double it yields, never computed here.
///   · Before (the reference's before-day scope: pregame rows at or after
///     the listed start minus one day, from `finalHistoryEvidence`), Oct 3
///     UTC: 00:01, 00:02, 00:04 | 12:04, 12:05, 12:10 | 17:18, 17:19, 17:21 |
///     17:48, 17:50, 17:51 | 23:56, 23:57, 23:58, 23:59 (hollow, the last
///     pregame row). Five clusters of the reference's 473 before-day rows.
///   · Live (the reference's live scope: the `hockeyLive.json` winner
///     baseline, then its winner rows at or before the checkpoint): 23:59 |
///     00:17, 00:18, 00:19 | 00:53 | 01:21, 01:22, 01:23 | 01:43, 01:44, 01:45.
///   · Final (the reference's `game` scope from `finalHistoryEvidence`: the
///     last pregame row, then in-game rows; its terminal 02:48 row at 1.0,
///     the result witness, is excluded exactly as the reference excludes it):
///     23:59 | 00:17, 00:18, 00:19 | 00:53 | 01:21, 01:22, 01:23 | 01:43,
///     01:44, 01:45 | 02:13, 02:14, 02:15 | 02:45, 02:46, 02:47, 02:48 (the
///     last kept row, 0.98847). 23 of the reference's 165 rows; in the
///     reference these are one unbroken segment, here omitted spans split it;
/// - guides: before none; live every period start and goal at or before
///   its checkpoint (5). The PREPARED final fixture keeps the period starts
///   and one selected goal (P1, P2, P3, Kaprizov 02:45:07Z) and OMITS the
///   Jeannot, Kaprizov 01:22:09Z, Hughes and Spurgeon goal labels so eight
///   labels do not crowd it — a fixture choice, not a rule on the owner's
///   marker array, which this layer passes through unfiltered;
/// - the chart domain follows the reference: before spans its before-day
///   rows; live and final start at the last pregame row. Whether the app's
///   in-game domain starts there or at the verified P1 is the owner's
///   admission, still owed;
/// - contribution records `nhl-15169793-game-markets.json:player_props:N`:
///   points 64/65/66 (Hughes 1+/2+/3+: 0.69 @ 23:55Z, 0.33 @ 23:51Z, none) and
///   59/60/61 (Kaprizov: 0.72 @ 19:22Z, 0.39 @ 19:51Z, none; live 60 0.54 @
///   01:44Z; 1 point at 01:45:25Z); assists 40/41/42 (Hughes: 0.63 @ 23:54Z,
///   0.27 @ 23:58Z, none; no in-game reading; 0 assists at 01:45:25Z). Final:
///   Hughes 2 points (1 goal + 1 assist) and 1 assist; 64/65 and 40 hit,
///   66/41/42 missed; Kaprizov 60 hit.
///
/// CONSTRUCTED owner input (this layer resolves none of it): every display
/// word, figure text, PT clock line, spoken word, colour, shape, tick, story
/// link, copy, phase, result word and difference word; the before example,
/// which is a same-game phase-safety check that carries later inputs only to
/// prove the leaves hide them, and earns no `nhl-before` credit.
final class HockeyJourneyEventPagePresentation10868Tests: XCTestCase {

    // MARK: Archived clocks (epoch seconds)

    private static let baselineX = 1_791_071_940.0      // 2026-10-03T23:59:00Z
    private static let p1X = 1_791_072_872.0            // 2026-10-04T00:14:32Z
    private static let jeannotX = 1_791_073_096.0       // 00:18:16Z
    private static let p2X = 1_791_076_330.0            // 01:12:10Z
    private static let kaprizovGoalX = 1_791_076_929.0  // 01:22:09Z
    private static let hughesGoalX = 1_791_077_924.0    // 01:38:44Z
    private static let lateSecondX = 1_791_078_325.0    // 01:45:25Z — the live checkpoint
    private static let p3X = 1_791_079_769.0            // 02:09:29Z
    private static let spurgeonX = 1_791_080_035.0      // 02:13:55Z
    private static let kaprizovLateX = 1_791_081_907.0  // 02:45:07Z
    private static let lastRowX = 1_791_082_080.0       // 02:48:00Z — the final scope's last kept row
    private static let listedStartX = 1_791_072_000.0   // 2026-10-04T00:00:00Z
    private static let beforeFirstX = 1_790_985_660.0   // 2026-10-03T00:01:00Z — first before-day row here

    private static let homeID = "blend:15169793:home"
    private static let awayID = "blend:15169793:away"
    /// CONSTRUCTED tints.
    private static let homeColor = Color(red: 0.0, green: 0.42, blue: 0.31)
    private static let awayColor = Color(red: 0.78, green: 0.55, blue: 0.0)

    // MARK: Matrix

    private static func value(_ text: String, _ spoken: String) -> HockeyJourneySlot10868 { .value(text, spoken: spoken) }
    private static let noInGameForecast = HockeyJourneySlot10868.absent("No in-game forecast")
    private static let home = HockeyJourneyTeam10868(name: "Minnesota Wild", short: "Wild", tint: homeColor)
    private static let away = HockeyJourneyTeam10868(name: "Boston Bruins", short: "Bruins", tint: awayColor)
    private static let pregameColumn = HockeyJourneyColumn10868(title: "Pregame chance", provenance: "Oct 3, 4:59 PM PT · Bain Luck blend")

    private static func matrix(_ phase: HockeyJourneyPagePhase10868) -> HockeyJourneyMatrix10868 {
        switch phase {
        case .before:
            return .before(HockeyJourneyBeforeMatrix10868(
                chance: HockeyJourneyColumn10868(title: "Win chance", provenance: "Last pregame · Oct 3, 4:59 PM PT · Bain Luck blend"),
                projectedGoals: HockeyJourneyColumn10868(title: "Projected goals", provenance: "Pregame forecast · Oct 3, 4:46 PM PT · 1 sportsbook"),
                home: HockeyJourneyBeforeRow10868(chance: value("66%", "66 percent"), projectedGoals: value("4", "4 goals")),
                away: HockeyJourneyBeforeRow10868(chance: value("34%", "34 percent"), projectedGoals: value("2.5", "2.5 goals"))))
        case .live:
            return .during(HockeyJourneyDuringMatrix10868(
                pregameChance: pregameColumn,
                currentChance: HockeyJourneyColumn10868(title: "Current chance", provenance: "Recorded Oct 3, 6:45 PM PT · Bain Luck blend"),
                goals: HockeyJourneyColumn10868(title: "Goals", provenance: "ESPN · game state 6:45 PM PT"),
                projectedFinal: HockeyJourneyColumn10868(title: "Projected final", provenance: nil),
                home: HockeyJourneyDuringRow10868(pregameChance: value("66%", "66 percent"), currentChance: value("82%", "82 percent"),
                                                  goals: value("2", "2 goals"), projectedFinal: noInGameForecast),
                away: HockeyJourneyDuringRow10868(pregameChance: value("34%", "34 percent"), currentChance: value("18%", "18 percent"),
                                                  goals: value("1", "1 goal"), projectedFinal: noInGameForecast)))
        case .final:
            return .final(HockeyJourneyFinalMatrix10868(
                pregameChance: pregameColumn,
                finalGoals: HockeyJourneyColumn10868(title: "Final goals", provenance: "ESPN final · final-score time unavailable"),
                pregameForecast: HockeyJourneyColumn10868(title: "Pregame forecast", provenance: "Oct 3, 4:46 PM PT · 1 sportsbook"),
                home: HockeyJourneyFinalRow10868(pregameChance: value("66%", "66 percent"), finalGoals: value("4", "4 goals"),
                                                 pregameForecast: value("4", "4 goals"), result: "Won",
                                                 difference: "Wild: matched forecast"),
                away: HockeyJourneyFinalRow10868(pregameChance: value("34%", "34 percent"), finalGoals: value("1", "1 goal"),
                                                 pregameForecast: value("2.5", "2.5 goals"), result: "Lost",
                                                 difference: "Bruins: 1.5 goals below forecast")))
        }
    }

    private static let historicalForecast = HockeyJourneyHistoricalForecast10868(
        title: "Pregame forecast", reading: "Wild 4 · Bruins 2.5 goals", provenance: "Recorded before play · Oct 3, 4:46 PM PT")

    private static func headline(_ phase: HockeyJourneyPagePhase10868,
                                 matrix: HockeyJourneyMatrix10868? = nil) -> HockeyJourneyHeadlineInput10868 {
        let words: (state: String, context: String?) = switch phase {
        case .before: ("Before game · 5:00 PM PT start", "Sat, Oct 3")
        case .live: ("2nd · 4:09 left", "Game state as of Oct 3, 6:45 PM PT · ESPN")
        case .final: ("Final", "Sat, Oct 3")
        }
        // Supplied in every phase; the model reads it during play only.
        return HockeyJourneyHeadlineInput10868(
            state: words.state, stateContext: words.context, home: home, away: away,
            matrix: matrix ?? Self.matrix(phase), historicalForecast: historicalForecast,
            spokenLabel: "Hockey win chances, score and forecast")
    }

    // MARK: History — both real competitor series, a labelled subset

    /// ARCHIVED (time, Minnesota, Boston) rows. Keys are UTC HHMM; 0001–2359
    /// before the game are Oct 3, 0017–0248 are Oct 4.
    private static let rows: [String: (x: Double, home: Double, away: Double)] = [
        "0001": (beforeFirstX, 0.645, 0.355),
        "0002": (1_790_985_720, 0.645, 0.355),
        "0004": (1_790_985_840, 0.645, 0.355),
        "1204": (1_791_029_040, 0.6464, 0.3536),
        "1205": (1_791_029_100, 0.6458, 0.35419999999999996),
        "1210": (1_791_029_400, 0.6458, 0.35419999999999996),
        "1718": (1_791_047_880, 0.655, 0.345),
        "1719": (1_791_047_940, 0.6507, 0.34930000000000005),
        "1721": (1_791_048_060, 0.6507, 0.34930000000000005),
        "1748": (1_791_049_680, 0.6507, 0.34930000000000005),
        "1750": (1_791_049_800, 0.655, 0.345),
        "1751": (1_791_049_860, 0.655, 0.345),
        "2356": (1_791_071_760, 0.66, 0.33999999999999997),
        "2357": (1_791_071_820, 0.66, 0.33999999999999997),
        "2358": (1_791_071_880, 0.665, 0.33499999999999996),
        "2359": (baselineX, 0.66, 0.33999999999999997),
        "0017": (1_791_073_020, 0.666645, 0.33335499999999996),
        "0018": (1_791_073_080, 0.58786, 0.41213999999999995),
        "0019": (1_791_073_140, 0.551855, 0.448145),
        "0053": (1_791_075_180, 0.484655, 0.5153449999999999),
        "0121": (1_791_076_860, 0.467405, 0.5325949999999999),
        "0122": (1_791_076_920, 0.541215, 0.458785),
        "0123": (1_791_076_980, 0.63359, 0.36641),
        "0143": (1_791_078_180, 0.81795, 0.18205000000000005),
        "0144": (1_791_078_240, 0.818645, 0.18135500000000004),
        "0145": (1_791_078_300, 0.81574, 0.18425999999999998),
        "0213": (1_791_079_980, 0.824265, 0.17573499999999997),
        "0214": (1_791_080_040, 0.86258, 0.13742),
        "0215": (1_791_080_100, 0.941665, 0.058335000000000026),
        "0245": (1_791_081_900, 0.98757, 0.012430000000000052),
        "0246": (1_791_081_960, 0.98757, 0.012430000000000052),
        "0247": (1_791_082_020, 0.98857, 0.011430000000000051),
        "0248": (lastRowX, 0.98847, 0.01153000000000004),
    ]

    private static func spans(_ phase: HockeyJourneyPagePhase10868) -> [[String]] {
        switch phase {
        case .before: [["0001", "0002", "0004"], ["1204", "1205", "1210"], ["1718", "1719", "1721"],
                       ["1748", "1750", "1751"], ["2356", "2357", "2358", "2359"]]
        case .live: [["2359"], ["0017", "0018", "0019"], ["0053"], ["0121", "0122", "0123"], ["0143", "0144", "0145"]]
        case .final: [["2359"], ["0017", "0018", "0019"], ["0053"], ["0121", "0122", "0123"], ["0143", "0144", "0145"],
                      ["0213", "0214", "0215"], ["0245", "0246", "0247", "0248"]]
        }
    }

    private static func pointID(_ series: String, _ key: String) -> String { "\(series)#\(key)" }

    private static func runs(_ series: String, _ phase: HockeyJourneyPagePhase10868) -> [FieldHistoryRun10868] {
        spans(phase).enumerated().map { index, keys in
            FieldHistoryRun10868(id: "\(series)#subset-run-\(index + 1)", points: keys.map { key in
                let row = rows[key]!
                return FieldHistoryPoint10868(id: pointID(series, key), x: row.x,
                                              probability: series == homeID ? row.home : row.away,
                                              style: key == "2359" ? .hollow : .filled)
            })
        }
    }

    /// Every period start and goal in the capture.
    private static let allGuides: [FieldHistoryGuide10868] = [
            FieldHistoryGuide10868(id: "401891814000000520", x: p1X, label: "P1"),
            FieldHistoryGuide10868(id: "401891814000000830", x: jeannotX, label: "Jeannot · BOS goal"),
            FieldHistoryGuide10868(id: "401891814000004360", x: p2X, label: "P2"),
            FieldHistoryGuide10868(id: "401891814000005630", x: kaprizovGoalX, label: "Kaprizov · MIN goal"),
            FieldHistoryGuide10868(id: "401891814000006480", x: hughesGoalX, label: "Hughes · MIN goal"),
            FieldHistoryGuide10868(id: "401891814000007920", x: p3X, label: "P3"),
            FieldHistoryGuide10868(id: "401891814000008260", x: spurgeonX, label: "Spurgeon · MIN goal"),
            FieldHistoryGuide10868(id: "401891814000010330", x: kaprizovLateX, label: "Kaprizov · MIN goal"),
    ]

    /// The prepared final keeps period starts and one selected goal (see the header).
    private static let finalGuideIDs: Set<String> = ["401891814000000520", "401891814000004360",
                                                     "401891814000007920", "401891814000010330"]

    /// Each frame's guides, all at or before it.
    private static func guides(_ phase: HockeyJourneyPagePhase10868) -> [FieldHistoryGuide10868] {
        switch phase {
        case .before: []
        case .live: allGuides.filter { $0.x <= lateSecondX }
        case .final: allGuides.filter { finalGuideIDs.contains($0.id) && $0.x <= lastRowX }
        }
    }

    private static func action(_ id: String, _ label: String, spoken: String? = nil) -> FieldHistoryAction10868 {
        FieldHistoryAction10868(id: id, label: label, spokenLabel: spoken, isAvailable: true)
    }

    private static func history(_ phase: HockeyJourneyPagePhase10868) -> FieldHistoryInput10868 {
        let lastKey = spans(phase).last!.last!
        func series(_ id: String, _ name: String, _ shape: FieldHistoryShape10868, _ tint: Color,
                    before: String, recorded: String) -> FieldHistorySeries10868 {
            FieldHistorySeries10868(
                id: id, name: name, shape: shape, tint: tint, runs: runs(id, phase), links: [], labelPointID: nil,
                before: .observation(pointID: pointID(id, "2359"), figure: before, provenance: "Last pregame · Oct 3, 4:59 PM PT"),
                recorded: phase == .live
                    ? .observation(pointID: pointID(id, lastKey), figure: recorded, provenance: "Recorded Oct 3, 6:45 PM PT")
                    : .absent(words: "Not recorded"),
                absentWords: "No recorded history", choose: nil)
        }
        let first = rows[spans(phase).first!.first!]!.x, last = rows[lastKey]!.x
        let inspection = phase == .live ? FieldHistoryInspection10868(
            x: rows["0145"]!.x, caption: "Recorded Oct 3, 6:45 PM PT",
            selections: [homeID: .point(id: pointID(homeID, "0145"), spoken: "82%"),
                         awayID: .point(id: pointID(awayID, "0145"), spoken: "18%")],
            choices: [
                FieldHistoryInspectionChoice10868(id: "choice.2359", lines: ["4:59 PM"], spoken: "Last pregame, 4:59 PM PT", isSelected: false),
                FieldHistoryInspectionChoice10868(id: "choice.0144", lines: ["6:44 PM"], spoken: "6:44 PM PT", isSelected: false),
                FieldHistoryInspectionChoice10868(id: "choice.0145", lines: ["6:45 PM"], spoken: "Latest recorded, 6:45 PM PT", isSelected: true),
            ],
            choicePresentation: .slider(label: "Recorded observation"),
            note: "A reduced subset of recorded minutes; omitted spans are not joined.") : nil
        return FieldHistoryInput10868(
            title: "Win probability", caption: phase == .before ? "Before game" : "Game history",
            series: [series(homeID, "Minnesota Wild", .circle, homeColor, before: "66%", recorded: "82%"),
                     series(awayID, "Boston Bruins", .square, awayColor, before: "34%", recorded: "18%")],
            selection: .none,
            domain: FieldHistoryDomain10868(lower: first, upper: last), ceiling: 1,
            yTicks: [FieldHistoryTick10868(value: 0, lines: ["0%"]), FieldHistoryTick10868(value: 0.5, lines: ["50%"]),
                     FieldHistoryTick10868(value: 1, lines: ["100%"])],
            xTicks: phase == .before
                ? [FieldHistoryTick10868(value: first, lines: ["Oct 2", "5:01 PM"]),
                   FieldHistoryTick10868(value: 1_791_010_800, lines: ["Oct 3", "12 AM"]),
                   FieldHistoryTick10868(value: 1_791_054_000, lines: ["Noon"]),
                   FieldHistoryTick10868(value: last, lines: ["4:59 PM"])]
                : [FieldHistoryTick10868(value: first, lines: ["4:59 PM"]),
                   FieldHistoryTick10868(value: last, lines: [phase == .live ? "6:45 PM" : "7:48 PM"])],
            guides: guides(phase), breaks: [],
            readout: phase == .live ? .beforeAndRecorded(beforeLabel: "Pregame", recordedLabel: "Recorded") : .singleBefore(label: "Pregame"),
            markKey: FieldHistoryMarkKey10868(hollow: "Hollow · last pregame", filled: nil),
            comparisonExplanation: nil, notes: ["Gaps remain blank."],
            summary: "Minnesota and Boston win probability, recorded observations only.", plotHeight: 230,
            unboundReadingWords: "Not recorded", plotUnavailableWords: nil,
            windows: nil, scale: nil, moreOriginals: nil,
            details: action("history.details", "History & source details"),
            expand: action("history.expand", "Full chart", spoken: "Expand hockey probability history"),
            inspect: phase == .live ? action("history.inspect", "Inspect history") : nil,
            previous: nil, next: nil, inspection: inspection)
    }

    // MARK: Contribution stories

    private static func key(_ index: Int) -> String { "nhl-15169793-game-markets.json:player_props:\(index)" }

    private static func obs(_ probability: Double, _ text: String, _ detail: String) -> PlayerContributionObservation10868 {
        PlayerContributionObservation10868(probability: probability, text: text, accessibilityDetail: detail)
    }

    private static let noReading = PlayerContributionCurrent10868.unavailable("No in-game reading")
    private static let pending = PlayerContributionResult10868.unconfirmed("Result unconfirmed")
    private static let reached = PlayerContributionResult10868.reached("Reached")
    private static let missed = PlayerContributionResult10868.missed("Missed")

    private static func milestone(_ index: Int, _ target: String, _ title: String,
                                  before: PlayerContributionObservation10868?,
                                  current: PlayerContributionCurrent10868 = noReading,
                                  progress: PlayerContributionProgress10868? = nil,
                                  result: PlayerContributionResult10868 = pending) -> PlayerContributionMilestone10868 {
        PlayerContributionMilestone10868(id: key(index), target: target, title: title, before: before,
                                         beforeMissing: "Unavailable", current: current, progress: progress, result: result)
    }

    private static let ticks = [
        PlayerContributionTick10868(value: 0, text: "0%"),
        PlayerContributionTick10868(value: 0.5, text: "50%"),
        PlayerContributionTick10868(value: 1, text: "100%"),
    ]

    private static let chooser = PlayerContributionChooser10868(title: "Choose player · 2", choices: [
        PlayerContributionChoice10868(id: "3942335", name: "Kirill Kaprizov", detail: "Minnesota"),
        PlayerContributionChoice10868(id: "4320548", name: "Quinn Hughes", detail: "Minnesota"),
    ])

    private static func contribution(_ phase: PlayerContributionPhase10868, _ orientation: PlayerContributionOrientation10868,
                                     _ player: PlayerContributionPlayer10868, selected: String,
                                     timing: PlayerContributionTiming10868? = nil) -> PlayerContributionInput10868 {
        PlayerContributionInput10868(
            phase: phase, orientation: orientation,
            eyebrow: orientation == .columns ? "PLAYER POINTS" : "PLAYER ASSISTS",
            title: orientation == .columns ? "Points in context" : "Who creates the goals?",
            definition: orientation == .columns ? "One point for each goal or assist." : "An assist credits a player who helped create a goal.",
            player: player, selectedMilestoneID: selected,
            chartTitle: "Pregame chances · at least this many", ticks: ticks, chooser: chooser, timing: timing)
    }

    private static let hughes1Pts = obs(0.69, "69%", "minute ending Oct 3, 4:55 PM PT · Kalshi")
    private static let hughes2Pts = obs(0.33, "33%", "minute ending Oct 3, 4:51 PM PT · Kalshi")
    private static let hughes1Ast = obs(0.63, "63%", "minute ending Oct 3, 4:54 PM PT · Kalshi")
    private static let hughes2Ast = obs(0.27, "27%", "minute ending Oct 3, 4:58 PM PT · Kalshi")
    private static let kaprizov1Pts = obs(0.72, "72%", "minute ending Oct 3, 12:22 PM PT · Kalshi")
    private static let kaprizov2Pts = obs(0.39, "39%", "minute ending Oct 3, 12:51 PM PT · Kalshi")
    private static let kaprizov2Live = obs(0.54, "54%", "recorded Oct 3, 6:44 PM PT · Kalshi")
    private static let finalBox = "final box score · ESPN"

    private static func hughesPoints(_ phase: HockeyJourneyPagePhase10868) -> PlayerContributionPlayer10868 {
        PlayerContributionPlayer10868(id: "4320548", name: "Quinn Hughes", team: "Minnesota", milestones: [
            milestone(64, "1+", "1+ points", before: hughes1Pts, current: .reached("Reached so far"), result: reached),
            milestone(65, "2+", "2+ points", before: hughes2Pts, result: reached),
            milestone(66, "3+", "3+ points", before: nil, result: missed),
        ], actual: .count(PlayerContributionCount10868(count: "2", unit: "points", breakdown: "1 goal + 1 assist",
                                                       accessibilityDetail: finalBox)))
    }

    private static func hughesAssists(_ phase: HockeyJourneyPagePhase10868) -> PlayerContributionPlayer10868 {
        let live = phase == .live
        return PlayerContributionPlayer10868(id: "4320548", name: "Quinn Hughes", team: "Minnesota", milestones: [
            milestone(40, "1+", "1+ assists", before: hughes1Ast,
                      progress: live ? PlayerContributionProgress10868(status: "1 more for 1+", fraction: 0) : nil,
                      result: live ? pending : reached),
            milestone(41, "2+", "2+ assists", before: hughes2Ast, result: live ? pending : missed),
            milestone(42, "3+", "3+ assists", before: nil, result: live ? pending : missed),
        ], actual: live
            ? .count(PlayerContributionCount10868(count: "0", unit: "assists so far", breakdown: nil,
                                                  accessibilityDetail: "as of 6:45 PM PT, 2nd period, 4:09 left · ESPN"))
            : .count(PlayerContributionCount10868(count: "1", unit: "assist", breakdown: nil, accessibilityDetail: finalBox)))
    }

    /// Late second period: 1+ reached so far, 2+ recorded at 01:44Z, 3+ no reading.
    private static let kaprizovLive = PlayerContributionPlayer10868(id: "3942335", name: "Kirill Kaprizov", team: "Minnesota", milestones: [
        milestone(59, "1+", "1+ points", before: kaprizov1Pts, current: .reached("Reached so far"),
                  progress: PlayerContributionProgress10868(status: "Milestone reached so far", fraction: 1), result: pending),
        milestone(60, "2+", "2+ points", before: kaprizov2Pts,
                  current: .recorded(kaprizov2Live, movement: "+15 percentage points since pregame"),
                  progress: PlayerContributionProgress10868(status: "1 more for 2+", fraction: 0.5), result: pending),
        milestone(61, "3+", "3+ points", before: nil, current: noReading,
                  progress: PlayerContributionProgress10868(status: "2 more for 3+", fraction: 1.0 / 3.0), result: pending),
    ], actual: .count(PlayerContributionCount10868(count: "1", unit: "point so far", breakdown: "1 goal + 0 assists",
                                                   accessibilityDetail: "as of 6:45 PM PT, 2nd period, 4:09 left · ESPN")))

    private static let kaprizovTiming = PlayerContributionTiming10868(
        milestoneID: key(60), title: "Kirill Kaprizov 2+ points · probability timing",
        lines: ["Pregame chance: minute ending Oct 3, 12:51 PM PT · Kalshi",
                "Recorded in-game: Oct 3, 6:44 PM PT · Kalshi",
                "Count so far: as of 6:45 PM PT, 2nd period, 4:09 left · ESPN"])

    private static func points(_ phase: HockeyJourneyPagePhase10868) -> PlayerContributionInput10868 {
        switch phase {
        case .before: contribution(.before, .columns, hughesPoints(.before), selected: key(65))
        case .live: contribution(.during, .columns, kaprizovLive, selected: key(60), timing: kaprizovTiming)
        case .final: contribution(.final, .columns, hughesPoints(.final), selected: key(65))
        }
    }

    private static func assists(_ phase: HockeyJourneyPagePhase10868) -> PlayerContributionInput10868 {
        contribution(phase.contributionPhase, .bars, hughesAssists(phase), selected: key(41))
    }

    // MARK: Stream and page

    private static func scope(_ phase: HockeyJourneyPagePhase10868) -> String { "nhl:15169793:\(phase)" }

    private static func stream(_ phase: HockeyJourneyPagePhase10868, wide: Bool = false) -> StoryStreamPresentation10868 {
        let scope = Self.scope(phase)
        func ref(_ id: String) -> StoryStreamPresentation10868.CardRef { .init(scope: scope, id: id) }
        return StoryStreamPresentation10868(
            scope: scope, eyebrow: nil, heading: "Expectations and performance",
            cards: [StoryStreamPresentation10868.Card(id: "points", name: "Points in context"),
                    StoryStreamPresentation10868.Card(id: "assists", name: "Who creates the goals?")],
            primary: ref("points"), companion: ref("assists"), companionLabel: "Next", wide: wide,
            position: "1 of 2", status: "Cards advance when you’re watching",
            dwellFraction: 0.4, playback: .pause, previous: ref("assists"), next: ref("assists"))
    }

    private static let stories = [
        HockeyJourneyPageStory10868(cardID: "points", card: .points, exploreLabel: "Explore points"),
        HockeyJourneyPageStory10868(cardID: "assists", card: .assists, exploreLabel: "Explore assists"),
    ]

    private static let copy = HockeyJourneyPageCopy10868(
        storiesLabel: "Game stories",
        storyUnavailable: "This story isn’t available for this game state. Every original is still in All props.",
        matrixUnavailable: "Comparison unavailable for this game state",
        allPropsLabel: "All 149 original outcomes")

    private static func header(_ phase: HockeyJourneyPagePhase10868) -> HockeyJourneyPageHeader10868 {
        let title = switch phase {
        case .before: "Minnesota Wild vs Boston Bruins"
        case .live: "Minnesota Wild 2–1 Boston Bruins"
        case .final: "Final: Minnesota Wild 4–1 Boston Bruins"
        }
        return HockeyJourneyPageHeader10868(eyebrow: "NHL · OCT 3 · RECORDED MATCH", title: title,
                                            aboutLabel: "About this hockey journey")
    }

    private static func page(_ phase: HockeyJourneyPagePhase10868, wide: Bool = false,
                             points: PlayerContributionInput10868?? = nil,
                             assists: PlayerContributionInput10868?? = nil,
                             matrix: HockeyJourneyMatrix10868? = nil) -> HockeyJourneyPageInput10868 {
        HockeyJourneyPageInput10868(
            phase: phase, header: header(phase), headline: headline(phase, matrix: matrix), history: history(phase),
            points: points ?? Self.points(phase), assists: assists ?? Self.assists(phase),
            stream: stream(phase, wide: wide), stories: stories, copy: copy)
    }

    // MARK: Phases

    @MainActor
    func testBeforeMountsTheActualLeavesAndTheirOwnPhaseHidesEveryLaterInput() {
        let input = Self.page(.before)
        let view = HockeyJourneyEventPagePresentation10868(input: input)
        XCTAssertEqual(view.mode, .page)
        XCTAssertEqual(view.headlineContent().input, input.headline)
        XCTAssertEqual(view.historyContent(reader: false).input, input.history)
        XCTAssertEqual(view.pointsContent()?.input, input.points)
        XCTAssertEqual(view.assistsContent()?.input, input.assists)
        XCTAssertEqual(view.pointsContent()?.input.orientation, .columns)
        XCTAssertEqual(view.assistsContent()?.input.orientation, .bars)

        // Before play: chance and projected goals only — no score, no current chance.
        let layout = view.headlineContent().model.layout!
        XCTAssertEqual(layout.columns.map(\.title), ["Win chance", "Projected goals"])
        XCTAssertEqual(layout.rows.map { $0.cells.map(\.text) }, [["66%", "4"], ["34%", "2.5"]])
        XCTAssertNil(view.headlineContent().model.historicalForecast, "The forecast is the current projection before play")

        // The fixture carries later inputs; the leaves' own phase hides them.
        for leaf in [input.points!, input.assists!] {
            XCTAssertNil(leaf.actualPresentation, "No count before play, not even a zero")
            for milestone in leaf.milestones {
                XCTAssertNil(leaf.currentReading(milestone))
                XCTAssertNil(leaf.result(milestone))
            }
        }
        XCTAssertEqual(input.points!.milestones.compactMap(\.before?.text), ["69%", "33%"])
        XCTAssertEqual(input.assists!.milestones.compactMap(\.before?.text), ["63%", "27%"])

        // A leaf at another phase, or in the other story's orientation, is not mounted.
        let mismatched = HockeyJourneyEventPagePresentation10868(input: Self.page(
            .before, points: .some(Self.points(.final)), assists: .some(Self.contribution(.before, .columns, Self.hughesAssists(.before), selected: Self.key(41)))))
        XCTAssertNil(mismatched.pointsContent())
        XCTAssertNil(mismatched.assistsContent())
        XCTAssertFalse(HockeyJourneyPageModel10868(mismatched.input).isMounted(.points))
        // History: the reference's before-day rows, ending at the last pregame
        // row, and no game guide.
        XCTAssertEqual(input.history.series.map { $0.runs.flatMap(\.points).count }, [16, 16])
        XCTAssertEqual(input.history.series[0].runs.flatMap(\.points).last?.x, Self.baselineX)
        XCTAssertEqual(input.history.guides, [])
    }

    @MainActor
    func testLateSecondPeriodMountsTheMatrixHistoryPointsAndAssistsFromTheRetainedCheckpoint() {
        let input = Self.page(.live)
        let view = HockeyJourneyEventPagePresentation10868(input: input)
        XCTAssertEqual(view.headlineContent().input, input.headline)
        XCTAssertEqual(view.historyContent(reader: false).input, input.history)
        XCTAssertEqual(view.pointsContent()?.input, input.points)
        XCTAssertEqual(view.assistsContent()?.input, input.assists)

        // Points: Kaprizov's reached 1+ stays performance, 2+ carries its own
        // recorded in-game chance, 3+ keeps its words; 1 point so far.
        let points = view.pointsContent()!.input
        XCTAssertEqual(points.milestones.compactMap { points.currentReading($0) },
                       [.actual("Reached so far"), .chance(Self.kaprizov2Live), .chanceStatus("No in-game reading")])
        XCTAssertEqual(points.actualPresentation?.title, PlayerContributionInput10868.countSoFarTitle)
        XCTAssertTrue(points.milestones.allSatisfy { points.result($0) == nil })

        // Assists: a genuine 0 so far is a count, not an absence, and no
        // in-game reading is invented.
        let assists = view.assistsContent()!.input
        XCTAssertEqual(assists.actualPresentation?.actual, .count(PlayerContributionCount10868(
            count: "0", unit: "assists so far", breakdown: nil,
            accessibilityDetail: "as of 6:45 PM PT, 2nd period, 4:09 left · ESPN")))
        XCTAssertEqual(assists.milestones.compactMap { assists.currentReading($0) },
                       Array(repeating: .chanceStatus("No in-game reading"), count: 3))

        // Two solid competitor series from the same rows; dashed links: none.
        let series = input.history.series
        XCTAssertEqual(series.map(\.name), ["Minnesota Wild", "Boston Bruins"])
        XCTAssertTrue(series.allSatisfy { $0.links.isEmpty })
        XCTAssertEqual(series.map { $0.runs.flatMap(\.points).last?.probability }, [0.81574, 0.18425999999999998])
        XCTAssertEqual(series[1].runs.first?.points.first?.probability, 0.33999999999999997,
                       "Boston's baseline is the owner data's complement, copied")
        XCTAssertEqual(series[0].runs.first?.points.map(\.style), [.hollow])
        XCTAssertTrue(series.flatMap { $0.runs.dropFirst().flatMap(\.points) }.allSatisfy { $0.style == .filled })
    }

    @MainActor
    func testFinalComparesEarlierChanceFinalGoalsAndForecastInTheOwnersWordsAndNeverQuotesTheResult() {
        let input = Self.page(.final)
        let view = HockeyJourneyEventPagePresentation10868(input: input)
        let model = view.headlineContent().model
        let layout = model.layout!
        XCTAssertEqual(layout.columns.map(\.title), ["Pregame chance", "Final goals", "Pregame forecast"])
        XCTAssertEqual(layout.lead, 0)
        // Fractional forecast and the matched 4 stay as written; no current chance column.
        XCTAssertEqual(layout.rows.map { $0.cells.map(\.text) }, [["66%", "4", "4"], ["34%", "1", "2.5"]])
        XCTAssertFalse(layout.columns.contains { $0.title.contains("Current") })
        XCTAssertFalse(layout.rows.flatMap { $0.cells.map(\.text) }.contains("100%"))
        XCTAssertEqual(layout.rows.map(\.result), ["Won", "Lost"])
        XCTAssertEqual(model.differences, ["Wild: matched forecast", "Bruins: 1.5 goals below forecast"])
        XCTAssertEqual(layout.spokenTeam(0), "Minnesota Wild, Won")
        XCTAssertEqual(layout.spoken(row: 1, column: 2), "Boston Bruins, Pregame forecast, 2.5 goals")
        XCTAssertNil(model.historicalForecast)

        // Each contract result stays apart from its chance and from the count.
        let points = view.pointsContent()!.input
        XCTAssertEqual(points.milestones.map { points.result($0) }, [Self.reached, Self.reached, Self.missed])
        XCTAssertEqual(points.milestones.compactMap(\.before?.text), ["69%", "33%"])
        XCTAssertEqual(points.actualPresentation?.title, PlayerContributionInput10868.finalCountTitle)
        let assists = view.assistsContent()!.input
        XCTAssertEqual(assists.milestones.map { assists.result($0) }, [Self.reached, Self.missed, Self.missed])

        // The history ends at the final scope's last kept row; the terminal
        // 1.0 result row is excluded, so nothing extends to 100%.
        XCTAssertEqual(input.history.domain.upper, Self.lastRowX)
        XCTAssertEqual(input.history.series[0].runs.flatMap(\.points).last?.probability, 0.98847)
        XCTAssertFalse(input.history.series.flatMap { $0.runs.flatMap(\.points) }.contains { $0.probability == 1 || $0.probability == 0 })
        XCTAssertEqual(input.history.readout, .singleBefore(label: "Pregame"))
    }

    // MARK: Matrix arrangement and channels

    @MainActor
    func testDuringPlayFourAlignedColumnsLeadWithTheCurrentChanceAndTheAbsentProjectionStaysApartFromTheHistoricalForecast() {
        let model = HockeyJourneyHeadlineModel10868(input: Self.headline(.live), phase: .live)
        let layout = model.layout!
        XCTAssertEqual(layout.columns.map(\.title), ["Pregame chance", "Current chance", "Goals", "Projected final"])
        XCTAssertEqual(layout.lead, 1)
        XCTAssertEqual(layout.rows.map(\.team.name), ["Minnesota Wild", "Boston Bruins"])
        XCTAssertTrue(layout.rows.allSatisfy { $0.cells.count == layout.columns.count })
        XCTAssertEqual(layout.rows.map { $0.cells.map(\.text) },
                       [["66%", "82%", "2", "No in-game forecast"], ["34%", "18%", "1", "No in-game forecast"]])
        XCTAssertEqual(layout.rows.map { $0.cells.map(\.isValue) }, [[true, true, true, false], [true, true, true, false]])
        XCTAssertEqual(layout.spoken(row: 0, column: 1), "Minnesota Wild, Current chance, 82 percent")
        XCTAssertEqual(layout.spoken(row: 1, column: 3), "Boston Bruins, Projected final, No in-game forecast")
        XCTAssertEqual(layout.spokenTeam(1), "Boston Bruins")

        // The pregame forecast stays visible as history, never in the projection slot.
        XCTAssertEqual(model.historicalForecast, Self.historicalForecast)
        XCTAssertFalse(layout.rows.flatMap { $0.cells.map(\.text) }.contains("2.5"))

        // A matrix from another phase is not drawn; the owner's words are.
        let stale = HockeyJourneyHeadlineModel10868(input: Self.headline(.live, matrix: Self.matrix(.final)), phase: .live)
        XCTAssertNil(stale.layout)
        XCTAssertNil(stale.historicalForecast)
        XCTAssertEqual(HockeyJourneyEventPagePresentation10868(input: Self.page(.live, matrix: Self.matrix(.before)))
                        .headlineContent().unavailable, "Comparison unavailable for this game state")
    }

    func testScoreStateAndProbabilityKeepTheirOwnClocksAndTheHistoryCarriesOnlyMarkersAtOrBeforeItsFrame() {
        let model = HockeyJourneyHeadlineModel10868(input: Self.headline(.live), phase: .live)
        XCTAssertEqual(model.input.state, "2nd · 4:09 left")
        XCTAssertEqual(model.input.stateContext, "Game state as of Oct 3, 6:45 PM PT · ESPN")
        XCTAssertEqual(model.provenance.map { $0.title }, ["Pregame chance", "Current chance", "Goals"])
        XCTAssertEqual(model.provenance.map { $0.words }, ["Oct 3, 4:59 PM PT · Bain Luck blend",
                                                       "Recorded Oct 3, 6:45 PM PT · Bain Luck blend",
                                                       "ESPN · game state 6:45 PM PT"])
        XCTAssertEqual(model.historicalForecast?.provenance, "Recorded before play · Oct 3, 4:46 PM PT")

        // Live: guides through the late-second-period frame only — no P3, no
        // later goal. The probability reading keeps its own 01:45:00Z row,
        // before the 01:45:25Z game-state checkpoint.
        let live = Self.history(.live)
        XCTAssertEqual(live.guides.map(\.label), ["P1", "Jeannot · BOS goal", "P2", "Kaprizov · MIN goal", "Hughes · MIN goal"])
        XCTAssertTrue(live.guides.allSatisfy { $0.x <= Self.lateSecondX })
        XCTAssertEqual(live.domain.upper, 1_791_078_300)
        XCTAssertLessThan(live.domain.upper, Self.lateSecondX)
        // The verified puck drop, not the listed 00:00Z start, marks P1.
        XCTAssertEqual(live.guides.first?.x, Self.p1X)
        // The prepared final keeps period starts plus one selected goal.
        let final = Self.history(.final)
        XCTAssertEqual(final.guides.map(\.label), ["P1", "P2", "P3", "Kaprizov · MIN goal"])
        XCTAssertEqual(final.guides.last?.x, Self.kaprizovLateX)

        // Omitted spans start new runs; within a run every row advances.
        let runs = live.series[0].runs
        XCTAssertEqual(runs.map(\.points.count), [1, 3, 1, 3, 3])
        XCTAssertEqual(live.inspection?.note, "A reduced subset of recorded minutes; omitted spans are not joined.")

        // Before: a genuine before-day span from the reference's own rows,
        // every one before the listed start and within its day, its own ticks,
        // and the domain ending at the last pregame row — no padded minute.
        let before = Self.history(.before)
        XCTAssertEqual(before.series[0].runs.map(\.points.count), [3, 3, 3, 3, 4])
        let beforePoints = before.series[0].runs.flatMap(\.points)
        XCTAssertTrue(beforePoints.allSatisfy { $0.x < Self.listedStartX && $0.x >= Self.listedStartX - 86_400 })
        XCTAssertEqual(before.domain, FieldHistoryDomain10868(lower: Self.beforeFirstX, upper: Self.baselineX))
        XCTAssertEqual(before.xTicks.map(\.value), [Self.beforeFirstX, 1_791_010_800, 1_791_054_000, Self.baselineX])
        XCTAssertEqual(beforePoints.map(\.probability), [0.645, 0.645, 0.645, 0.6464, 0.6458, 0.6458,
                                                          0.655, 0.6507, 0.6507, 0.6507, 0.655, 0.655,
                                                          0.66, 0.66, 0.665, 0.66])
        XCTAssertEqual(beforePoints.filter { $0.style == .hollow }.map(\.x), [Self.baselineX])

        // Final: the reference's game scope, last pregame row first, its own
        // clocks, and each run separated where rows were left out.
        XCTAssertEqual(final.series[0].runs.map(\.points.count), [1, 3, 1, 3, 3, 3, 4])
        XCTAssertEqual(final.domain, FieldHistoryDomain10868(lower: Self.baselineX, upper: Self.lastRowX))
        XCTAssertEqual(final.series[1].runs.last?.points.map(\.probability),
                       [0.012430000000000052, 0.012430000000000052, 0.011430000000000051, 0.01153000000000004])
        for history in [before, live, final] {
            for series in history.series {
                for run in series.runs { XCTAssertEqual(run.points.map(\.x), run.points.map(\.x).sorted()) }
                let xs = series.runs.flatMap(\.points).map(\.x)
                XCTAssertEqual(xs, xs.sorted())
                XCTAssertEqual(Set(xs).count, xs.count)
            }
        }
    }

    // MARK: Readers and stream wiring

    @MainActor
    func testTheFullSizeHistoryDropsOnlyItsExpandControlAndStoriesResolveOnlyExactLinks() {
        for phase in [HockeyJourneyPagePhase10868.live, .final] {
            let input = Self.page(phase)
            let view = HockeyJourneyEventPagePresentation10868(input: input, mode: .reader(.history))
            XCTAssertEqual(view.historyContent(reader: false).input.expand?.id, "history.expand")
            let reader = view.historyContent(reader: true).input
            XCTAssertNil(reader.expand)
            XCTAssertEqual(reader.layout, .expanded)
            let page = Mirror(reflecting: input.history).children.map { ($0.label ?? "", String(describing: $0.value)) }
            let full = Mirror(reflecting: reader).children.map { ($0.label ?? "", String(describing: $0.value)) }
            XCTAssertEqual(page.map(\.0), full.map(\.0))
            for (owner, shown) in zip(page, full) where owner.0 != "expand" && owner.0 != "layout" {
                XCTAssertEqual(owner.1, shown.1, "\(phase) \(owner.0)")
            }
            XCTAssertEqual(FieldHistoryGeometry10868.actions(reader).map(\.id),
                           FieldHistoryGeometry10868.actions(input.history).map(\.id).filter { $0 != "history.expand" })
            // The history reader keeps the same matrix input.
            XCTAssertEqual(view.headlineContent().input, input.headline)
        }
        XCTAssertNotNil(HockeyJourneyPageModel10868(Self.page(.live)).readerHistory.inspection)

        let live = HockeyJourneyPageModel10868(Self.page(.live))
        XCTAssertEqual(live.storyCard("points"), .points)
        XCTAssertEqual(live.storyCard("assists"), .assists)
        XCTAssertNil(live.storyCard("scorers"))
        XCTAssertNil(live.storyCard("Points"))
        let base = Self.page(.live)
        let ambiguous = HockeyJourneyPageModel10868(HockeyJourneyPageInput10868(
            phase: .live, header: base.header, headline: base.headline, history: base.history,
            points: base.points, assists: nil, stream: base.stream,
            stories: [HockeyJourneyPageStory10868(cardID: "points", card: .points, exploreLabel: nil),
                      HockeyJourneyPageStory10868(cardID: "points", card: .assists, exploreLabel: nil),
                      HockeyJourneyPageStory10868(cardID: "chart", card: .history, exploreLabel: nil),
                      HockeyJourneyPageStory10868(cardID: "assists", card: .assists, exploreLabel: nil)],
            copy: base.copy))
        XCTAssertNil(ambiguous.storyCard("points"))
        XCTAssertNil(ambiguous.storyCard("chart"))
        XCTAssertNil(ambiguous.storyCard("assists"), "Linked, but no assists input this snapshot")
        XCTAssertFalse(ambiguous.readerShows(.assists))

        let input = Self.page(.final)
        for card in HockeyJourneyPageCard10868.allCases {
            XCTAssertTrue(HockeyJourneyPageModel10868(input).readerShows(card), "\(card)")
        }
        XCTAssertEqual(HockeyJourneyEventPagePresentation10868(input: input, mode: .reader(.points)).pointsContent()?.input, input.points)
        XCTAssertEqual(HockeyJourneyEventPagePresentation10868(input: input, mode: .reader(.assists)).assistsContent()?.input, input.assists)
    }

    @MainActor
    func testAStreamCardActionRequestsTheHoldBeforeTheExactOwnerCallbackAndNothingFiresPassively() {
        var log: [String] = []
        let input = Self.page(.live, wide: true)
        let view = HockeyJourneyEventPagePresentation10868(
            input: input,
            onAbout: { log.append("about") },
            onAllProps: { log.append("allProps") },
            onStoryIntent: { _ in log.append("stream") },
            onOpenStory: { log.append("open:\($0.rawValue)") },
            onHistoryAction: { log.append("history:\($0)") },
            onHistoryInspectionChoice: { log.append("inspect:\($0)") },
            onHistoryPlotPosition: { log.append("plot:\($0)") },
            onPointsSelect: { log.append("points:\($0)") },
            onPointsChoosePlayer: { log.append("pointsPlayer:\($0)") },
            onPointsDetails: { log.append("pointsDetails:\($0)") },
            onAssistsSelect: { log.append("assists:\($0)") },
            onAssistsChoosePlayer: { log.append("assistsPlayer:\($0)") },
            onAssistsDetails: { log.append("assistsDetails:\($0)") }
        )

        // The activation the real stream hands each displayed card: points as
        // primary and, in the owner's wide presentation, assists as companion.
        let stream = input.stream
        let resolved = stream.resolve(reduceMotion: false, actionable: true)
        func activation(_ id: String) -> StoryStreamCardActivation10868 {
            let ref = StoryStreamPresentation10868.CardRef(scope: stream.scope, id: id)
            return StoryStreamCardActivation10868(card: ref, intents: stream.activationIntents(for: ref, resolved: resolved)) { intent in
                if case .interaction(_, let card) = intent { log.append("hold:\(card?.id ?? "-")") } else { log.append("other") }
            }
        }
        XCTAssertTrue(activation("points").isAvailable)
        XCTAssertTrue(activation("assists").isAvailable)

        // Building every leaf, in stream, page and reader form, acts on nothing.
        let points = view.pointsContent(activation: activation("points"))!
        let assists = view.assistsContent(activation: activation("assists"))!
        let explorePoints = view.exploreAction(Self.stories[0], activation: activation("points"))!
        let exploreAssists = view.exploreAction(Self.stories[1], activation: activation("assists"))!
        let anchor = view.historyContent(reader: false)
        let readerHistory = view.historyContent(reader: true)
        _ = view.headlineContent()
        _ = view.pointsContent()
        XCTAssertEqual(log, [])

        // In the stream: the hold first, then the exact owner action.
        points.onSelect?(Self.key(60))
        points.onChoosePlayer?("4320548")
        points.onDetails?(Self.key(60))
        assists.onSelect?(Self.key(41))
        assists.onDetails?(Self.key(40))
        explorePoints()
        exploreAssists()
        XCTAssertEqual(log, ["hold:points", "points:\(Self.key(60))", "hold:points", "pointsPlayer:4320548",
                             "hold:points", "pointsDetails:\(Self.key(60))",
                             "hold:assists", "assists:\(Self.key(41))", "hold:assists", "assistsDetails:\(Self.key(40))",
                             "hold:points", "open:points", "hold:assists", "open:assists"])

        // Full-size content and the anchor: the exact callback, no hold.
        log = []
        let reader = HockeyJourneyEventPagePresentation10868(input: input, mode: .reader(.points),
                                                             onPointsSelect: { log.append("points:\($0)") })
        reader.pointsContent()?.onSelect?(Self.key(59))
        view.assistsContent()?.onChoosePlayer?("3942335")
        anchor.onAction?("history.expand")
        readerHistory.onAction?("history.details")
        anchor.onInspectionChoice?("choice.0144")
        anchor.onPlotPosition?(Self.hughesGoalX)
        view.openAbout()
        view.openAllProps()
        XCTAssertEqual(log, ["points:\(Self.key(59))", "assistsPlayer:3942335", "history:history.expand",
                             "history:history.details", "inspect:choice.0144", "plot:\(Self.hughesGoalX)",
                             "about", "allProps"])

        // Without host callbacks nothing acts, even inside the stream.
        let quiet = HockeyJourneyEventPagePresentation10868(input: input)
        XCTAssertNil(quiet.pointsContent(activation: activation("points"))?.onSelect)
        XCTAssertNil(quiet.assistsContent(activation: activation("assists"))?.onDetails)
        XCTAssertNil(quiet.pointsContent()?.onChoosePlayer)
        XCTAssertNil(quiet.exploreAction(Self.stories[0], activation: activation("points")))
        XCTAssertNil(quiet.historyContent(reader: false).onAction)
        XCTAssertNil(view.exploreAction(HockeyJourneyPageStory10868(cardID: "points", card: .points, exploreLabel: " "),
                                        activation: activation("points")))
        log = []
        quiet.openAbout()
        quiet.openAllProps()
        XCTAssertEqual(log, [])
    }

    @MainActor
    func testChooserAndTimingDisclosuresInTheStreamRequestTheHoldBeforeTheyWriteAndReadersPassBindingsThrough() {
        var log: [String] = []
        var expanded = ["pointsChoices": false, "pointsTiming": true, "assistsChoices": false, "assistsTiming": false]
        func owner(_ key: String) -> Binding<Bool> {
            Binding(get: { expanded[key]! }, set: { log.append("\(key):\($0)"); expanded[key] = $0 })
        }
        let input = Self.page(.live, wide: true)
        let view = HockeyJourneyEventPagePresentation10868(
            input: input,
            pointsChoicesExpanded: owner("pointsChoices"), pointsTimingExpanded: owner("pointsTiming"),
            assistsChoicesExpanded: owner("assistsChoices"), assistsTimingExpanded: owner("assistsTiming"))
        let stream = input.stream
        let resolved = stream.resolve(reduceMotion: false, actionable: true)
        func activation(_ id: String) -> StoryStreamCardActivation10868 {
            let ref = StoryStreamPresentation10868.CardRef(scope: stream.scope, id: id)
            return StoryStreamCardActivation10868(card: ref, intents: stream.activationIntents(for: ref, resolved: resolved)) { intent in
                if case .interaction(_, let card) = intent { log.append("hold:\(card?.id ?? "-")") } else { log.append("other") }
            }
        }

        // The bindings the actual child Views receive. Building and reading acts on nothing.
        let points = view.pointsContent(activation: activation("points"))!
        let assists = view.assistsContent(activation: activation("assists"))!
        XCTAssertEqual([points.choicesExpanded!.wrappedValue, points.timingExpanded!.wrappedValue,
                        assists.choicesExpanded!.wrappedValue, assists.timingExpanded!.wrappedValue],
                       [false, true, false, false])
        XCTAssertEqual(points.input.timingPresentation(hasBinding: true), .disclosure(Self.kaprizovTiming))
        XCTAssertEqual(log, [])

        // Opening or closing: the hold first, then the exact new value to the owner.
        points.choicesExpanded!.wrappedValue = true
        points.timingExpanded!.wrappedValue = false
        assists.choicesExpanded!.wrappedValue = true
        assists.timingExpanded!.wrappedValue = true
        XCTAssertEqual(log, ["hold:points", "pointsChoices:true", "hold:points", "pointsTiming:false",
                             "hold:assists", "assistsChoices:true", "hold:assists", "assistsTiming:true"])
        XCTAssertEqual(expanded, ["pointsChoices": true, "pointsTiming": false, "assistsChoices": true, "assistsTiming": true])

        // Full-size content: the owner's binding passes straight through, no hold.
        log = []
        let reader = HockeyJourneyEventPagePresentation10868(
            input: input, mode: .reader(.points),
            pointsChoicesExpanded: owner("pointsChoices"), pointsTimingExpanded: owner("pointsTiming"))
        reader.pointsContent()!.timingExpanded!.wrappedValue = true
        reader.pointsContent()!.choicesExpanded!.wrappedValue = false
        XCTAssertEqual(log, ["pointsTiming:true", "pointsChoices:false"])

        // No owner binding: none, in the stream or full size.
        let quiet = HockeyJourneyEventPagePresentation10868(input: input)
        XCTAssertNil(quiet.pointsContent(activation: activation("points"))?.timingExpanded)
        XCTAssertNil(quiet.assistsContent()?.choicesExpanded)
        XCTAssertEqual(log, ["pointsTiming:true", "pointsChoices:false"])
    }

    // MARK: Arrangement

    func testCompactWideAndAccessibilitySizesChooseTheirArrangementsWithoutShrinking() {
        XCTAssertEqual(HockeyJourneyPageModel10868.arrangements(sizeClass: .compact, accessibilitySize: false), [.stacked])
        XCTAssertEqual(HockeyJourneyPageModel10868.arrangements(sizeClass: .regular, accessibilitySize: false), [.sideBySide, .stacked])
        XCTAssertEqual(HockeyJourneyPageModel10868.arrangements(sizeClass: nil, accessibilitySize: false), [.sideBySide, .stacked])
        XCTAssertEqual(HockeyJourneyPageModel10868.arrangements(sizeClass: .regular, accessibilitySize: true), [.stacked])
        XCTAssertEqual(HockeyJourneyPageModel10868.arrangements(sizeClass: nil, accessibilitySize: true), [.stacked])

        // The matrix: full names, then the owner's short names, then labelled
        // pairs; accessibility sizes go straight to labelled pairs.
        XCTAssertEqual(HockeyJourneyHeadlineModel10868.arrangements(accessibilitySize: false), [.grid, .shortGrid, .labelledPairs])
        XCTAssertEqual(HockeyJourneyHeadlineModel10868.arrangements(accessibilitySize: true), [.labelledPairs])
        // Long names and every absence survive whole in the input the layout reads.
        let layout = HockeyJourneyHeadlineModel10868(input: Self.headline(.live), phase: .live).layout!
        XCTAssertEqual(layout.rows.map(\.team.name), ["Minnesota Wild", "Boston Bruins"])
        XCTAssertEqual(layout.rows.map(\.team.short), ["Wild", "Bruins"])
        XCTAssertEqual(layout.rows.map { $0.cells[3] }, [Self.noInGameForecast, Self.noInGameForecast])
        // The labelled-pairs fallback keeps comparisons together: each pair
        // tries side by side before single lines, and no cell is lost.
        let pairs = layout.pairs(row: 1)
        XCTAssertEqual(pairs.map { $0.values.map(\.title) }, [["Pregame chance", "Current chance"], ["Goals", "Projected final"]])
        XCTAssertEqual(pairs.map(\.arrangements), [[.adjacent, .single], [.adjacent, .single]])
        XCTAssertEqual(pairs.flatMap(\.values).map(\.slot), layout.rows[1].cells)
    }

    @MainActor
    func testTheNarrowFallbackGivesEachTeamItsComparisonsAsLabelledPairsAndSplitsOnlyAPairThatCannotFit() {
        func pairs(_ phase: HockeyJourneyPagePhase10868, row: Int) -> [HockeyJourneyMatrixPair10868] {
            HockeyJourneyEventPagePresentation10868(input: Self.page(phase)).headlineContent().model.layout!.pairs(row: row)
        }

        // During play: pregame and current chance together, then goals beside
        // the projected final or its whole absence words. The current chance leads.
        let live = pairs(.live, row: 0)
        XCTAssertEqual(live.map { $0.values.map(\.title) }, [["Pregame chance", "Current chance"], ["Goals", "Projected final"]])
        XCTAssertEqual(live.map { $0.values.map(\.slot.text) }, [["66%", "82%"], ["2", "No in-game forecast"]])
        XCTAssertEqual(live.map { $0.values.map(\.lead) }, [[false, true], [false, false]])
        XCTAssertEqual(live[0].values[1].spoken, "Minnesota Wild, Current chance, 82 percent")
        XCTAssertEqual(pairs(.live, row: 1)[1].values.map(\.spoken),
                       ["Boston Bruins, Goals, 1 goal", "Boston Bruins, Projected final, No in-game forecast"])

        // Before play: the chance and projection pair.
        let before = pairs(.before, row: 1)
        XCTAssertEqual(before.map { $0.values.map(\.title) }, [["Win chance", "Projected goals"]])
        XCTAssertEqual(before.map { $0.values.map(\.slot.text) }, [["34%", "2.5"]])

        // Final: the pregame chance on its own, then final goals beside the forecast.
        let final = pairs(.final, row: 1)
        XCTAssertEqual(final.map { $0.values.map(\.title) }, [["Pregame chance"], ["Final goals", "Pregame forecast"]])
        XCTAssertEqual(final.map { $0.values.map(\.slot.text) }, [["34%"], ["1", "2.5"]])
        XCTAssertEqual(final.map(\.arrangements), [[.single], [.adjacent, .single]])

        // Every column appears once, in order, for both teams in every phase.
        for phase in [HockeyJourneyPagePhase10868.before, .live, .final] {
            let layout = HockeyJourneyHeadlineModel10868(input: Self.headline(phase), phase: phase).layout!
            XCTAssertEqual(layout.groups.flatMap { $0 }, Array(layout.columns.indices), "\(phase)")
            for row in layout.rows.indices {
                XCTAssertEqual(layout.pairs(row: row).flatMap(\.values).map(\.slot), layout.rows[row].cells, "\(phase)")
                XCTAssertTrue(layout.pairs(row: row).allSatisfy { $0.values.count <= 2 })
            }
        }
    }

    // MARK: About

    @MainActor
    func testSourceClocksMoveBehindAReadableAboutEntryStayInlineWithoutOneAndTheAboutContentActsOnNothing() {
        var log: [String] = []
        let input = Self.page(.live)
        let columnLines = [
            HockeyJourneySupportLine10868(title: "Pregame chance", words: "Oct 3, 4:59 PM PT · Bain Luck blend"),
            HockeyJourneySupportLine10868(title: "Current chance", words: "Recorded Oct 3, 6:45 PM PT · Bain Luck blend"),
            HockeyJourneySupportLine10868(title: "Goals", words: "ESPN · game state 6:45 PM PT"),
        ]
        let forecastLine = HockeyJourneySupportLine10868(title: "Pregame forecast", words: "Recorded before play · Oct 3, 4:46 PM PT")

        // No About entry: every support line stays inline.
        let unbound = HockeyJourneyEventPagePresentation10868(input: input).headlineContent()
        XCTAssertFalse(unbound.aboutAvailable)
        XCTAssertEqual(unbound.model.inlineProvenance(aboutAvailable: unbound.aboutAvailable), columnLines)
        XCTAssertEqual(unbound.model.inlineForecastProvenance(aboutAvailable: unbound.aboutAvailable), forecastLine.words)

        // A readable About entry: the support lines leave the headline; the
        // figures, the forecast reading, the state and its context stay.
        let view = HockeyJourneyEventPagePresentation10868(input: input, onAbout: { log.append("about") },
                                                           onAllProps: { log.append("allProps") },
                                                           onHistoryAction: { log.append("history:\($0)") })
        let bound = view.headlineContent()
        XCTAssertTrue(bound.aboutAvailable)
        XCTAssertEqual(bound.model.inlineProvenance(aboutAvailable: bound.aboutAvailable), [])
        XCTAssertNil(bound.model.inlineForecastProvenance(aboutAvailable: bound.aboutAvailable))
        XCTAssertEqual(bound.model.historicalForecast?.reading, "Wild 4 · Bruins 2.5 goals")
        XCTAssertEqual(bound.model.layout?.rows.map { $0.cells.map(\.text) },
                       [["66%", "82%", "2", "No in-game forecast"], ["34%", "18%", "1", "No in-game forecast"]])
        XCTAssertEqual([bound.input.state, bound.input.stateContext], ["2nd · 4:09 left", "Game state as of Oct 3, 6:45 PM PT · ESPN"])

        // The About content holds each column's own clock and the forecast's.
        XCTAssertEqual(view.aboutContent().lines, columnLines + [forecastLine])
        let finalView = HockeyJourneyEventPagePresentation10868(input: Self.page(.final), onAbout: {})
        XCTAssertEqual(finalView.aboutContent().lines.map(\.title), ["Pregame chance", "Final goals", "Pregame forecast"])
        XCTAssertEqual(finalView.aboutContent().lines[1].words, "ESPN final · final-score time unavailable")
        XCTAssertEqual(finalView.headlineContent().model.differences, ["Wild: matched forecast", "Bruins: 1.5 goals below forecast"])

        // The full-size history keeps the matrix and the About entry; other
        // modes show no matrix and no entry.
        let model = HockeyJourneyPageModel10868(input)
        XCTAssertTrue(HockeyJourneyEventPagePresentation10868(input: input, mode: .reader(.history), onAbout: {})
                        .headlineContent().aboutAvailable)
        XCTAssertTrue(model.aboutEntry(mode: .page, canOpen: true))
        XCTAssertTrue(model.aboutEntry(mode: .reader(.history), canOpen: true))
        for mode in [HockeyJourneyPageMode10868.reader(.points), .reader(.assists), .catalogue, .original, .about] {
            XCTAssertFalse(model.aboutEntry(mode: mode, canOpen: true), "\(mode)")
        }
        XCTAssertFalse(model.aboutEntry(mode: .page, canOpen: false))

        // An unreadable About label is no entry: the lines stay inline.
        let blank = HockeyJourneyPageInput10868(
            phase: .live, header: HockeyJourneyPageHeader10868(eyebrow: input.header.eyebrow, title: input.header.title, aboutLabel: " "),
            headline: input.headline, history: input.history, points: input.points, assists: input.assists,
            stream: input.stream, stories: input.stories, copy: input.copy)
        let blankHeadline = HockeyJourneyEventPagePresentation10868(input: blank, onAbout: { log.append("about") }).headlineContent()
        XCTAssertFalse(blankHeadline.aboutAvailable)
        XCTAssertEqual(blankHeadline.model.inlineProvenance(aboutAvailable: blankHeadline.aboutAvailable), columnLines)

        // Building the About content or the About mode acts on nothing; it is
        // static words with no action of its own. Only the entry opens About.
        let aboutMode = HockeyJourneyEventPagePresentation10868(input: input, mode: .about, onAbout: { log.append("about") })
        _ = aboutMode.aboutContent()
        _ = view.aboutContent()
        XCTAssertEqual(Mirror(reflecting: view.aboutContent()).children.map(\.label), ["lines"])
        XCTAssertEqual(log, [])
        view.openAbout()
        XCTAssertEqual(log, ["about"])
    }
}

// MARK: - All props and the selected original's Details

/// The catalogue and Details content modes, made of the existing
/// `OriginalMarketCatalogueView9483` and `OriginalMarketDetailsView9483`,
/// asserted the same way as their own tests: those actual leaves are mounted
/// with the owner's originals group and exact callbacks unchanged, and each
/// original keeps its own pregame chance, in-game reading and grade apart.
///
/// A SMALL, explicitly labelled SUBSET of the 149 retained originals — NOT the
/// catalogue obligation; it proves no full native fit:
/// - Kirill Kaprizov 2+ points, `64871068` outcome 243945029: pregame 0.39 at
///   19:51Z; in-game 0.54 at 01:44Z (current at the 01:45:25Z checkpoint);
///   hit;
/// - Quinn Hughes 2+ assists, `64870807` outcome 243939188: pregame 0.27 at
///   23:58Z; no in-game reading; missed;
/// - Quinn Hughes 3+ points, `64871068` outcome 243945042: no pregame
///   reading; no in-game reading; missed.
/// Rules are the retained rule text. CONSTRUCTED: scope, labels, figure text,
/// grade words, heading, context and tint.
@MainActor
extension HockeyJourneyEventPagePresentation10868Tests {
    private typealias Originals = OriginalMarketDetails9483

    private static let kaprizovTwo = Originals.Identity(source: "kalshi", market: "64871068", side: "243945029")
    private static let hughesTwoAssists = Originals.Identity(source: "kalshi", market: "64870807", side: "243939188")
    private static let hughesThree = Originals.Identity(source: "kalshi", market: "64871068", side: "243945042")

    private static func originalsScope(_ phase: HockeyJourneyPagePhase10868) -> String { "\(scope(phase)):originals" }

    private static func original(_ identity: Originals.Identity, market: String, outcome: String,
                                 pregame: Originals.Reading, later: Originals.Reading, grade: String,
                                 rules: String, phase: HockeyJourneyPagePhase10868) -> Originals.Original {
        Originals.Original(
            identity: identity, title: market, outcome: outcome,
            mode: phase == .final ? .result : phase == .live ? .comparison(.current) : .pregame,
            pregame: pregame, later: phase == .live ? later : nil,
            grade: phase == .final ? Originals.Grade(words: grade, provenance: nil) : nil,
            about: Originals.About(source: "Kalshi", rules: .verified([rules]),
                                   provenance: [Originals.Row(label: "Market ID", value: identity.market)],
                                   historicalQuote: nil))
    }

    private static func originals(_ phase: HockeyJourneyPagePhase10868,
                                  holding held: Originals.Identity? = HockeyJourneyEventPagePresentation10868Tests.kaprizovTwo)
        -> HockeyJourneyPageOriginals10868 {
        let rows = [
            original(kaprizovTwo, market: "Boston vs Minnesota: Points", outcome: "Kirill Kaprizov: 2+",
                     pregame: .value("39%", placement: 0.39, provenance: "Oct 3, 12:51 PM PT · Kalshi"),
                     later: .value("54%", placement: 0.54, provenance: "Recorded Oct 3, 6:44 PM PT · Kalshi"), grade: "Won",
                     rules: "If Kirill Kaprizov records 2+ points in the Boston vs Minnesota NHL game originally scheduled for Oct 3, 2026, then the market resolves to Yes.",
                     phase: phase),
            original(hughesTwoAssists, market: "Boston vs Minnesota: Assists", outcome: "Quinn Hughes: 2+",
                     pregame: .value("27%", placement: 0.27, provenance: "Oct 3, 4:58 PM PT · Kalshi"),
                     later: .missing("No in-game reading"), grade: "Lost",
                     rules: "If Quinn Hughes records 2+ assists in the Boston vs Minnesota NHL game originally scheduled for Oct 3, 2026, then the market resolves to Yes.",
                     phase: phase),
            original(hughesThree, market: "Boston vs Minnesota: Points", outcome: "Quinn Hughes: 3+",
                     pregame: .missing("No retained pregame chance"), later: .missing("No in-game reading"), grade: "Lost",
                     rules: "If Quinn Hughes records 3+ points in the Boston vs Minnesota NHL game originally scheduled for Oct 3, 2026, then the market resolves to Yes.",
                     phase: phase),
        ]
        let scope = originalsScope(phase)
        return HockeyJourneyPageOriginals10868(
            catalogue: Originals.Catalogue(scope: scope, originals: rows),
            selection: held.map { Originals.Selection(scope: scope, identity: $0) },
            labels: [kaprizovTwo: "Kirill Kaprizov 2+ points", hughesTwoAssists: "Quinn Hughes 2+ assists",
                     hughesThree: "Quinn Hughes 3+ points"],
            heading: "All props", context: "149 retained originals",
            emptyWords: "No retained originals for this game", unavailableChoice: "Unnamed original", tint: homeColor)
    }

    private static func cards(_ view: OriginalMarketCatalogueView9483) -> [OriginalMarketCatalogue9483.Card] {
        OriginalMarketCatalogue9483.cards(catalogue: view.catalogue, selection: view.selection,
                                          labels: view.labels, unavailableChoice: view.unavailableChoice)
    }

    func testAllPropsAndDetailsMountTheExistingOriginalLeavesWithEachOriginalsOwnReadingsAndGrades() {
        var log: [String] = []
        let originals = Self.originals(.live)
        let view = HockeyJourneyEventPagePresentation10868(
            input: Self.page(.live), mode: .catalogue, originals: originals,
            onOriginalSelect: { log.append("select:\($0.identity.side)") },
            onOriginalHistory: { log.append("history:\($0.actionID)") })
        let catalogue = view.catalogueContent()!
        let details = view.originalDetailsContent()!
        XCTAssertEqual(catalogue.catalogue, originals.catalogue)
        XCTAssertEqual(catalogue.selection, originals.selection)
        XCTAssertEqual(details.catalogue, originals.catalogue)
        XCTAssertNil(details.recorded)

        // One card per supplied original, in the owner's order, each with its own readings.
        let cards = Self.cards(catalogue)
        XCTAssertEqual(cards.map(\.choice.label), ["Kirill Kaprizov 2+ points", "Quinn Hughes 2+ assists", "Quinn Hughes 3+ points"])
        XCTAssertEqual(cards.map { $0.content!.readings.map(\.text) },
                       [["39%", "54%"], ["27%", "No in-game reading"], ["No retained pregame chance", "No in-game reading"]])
        let held = Originals.content(catalogue: details.catalogue, selection: details.selection)!
        XCTAssertEqual(held.readings.map(\.label), ["Pregame chance", "Current chance"])
        XCTAssertEqual(held.rules, .verified(["If Kirill Kaprizov records 2+ points in the Boston vs Minnesota NHL game originally scheduled for Oct 3, 2026, then the market resolves to Yes."]))
        XCTAssertEqual(log, [], "Entering either mode selects nothing and opens no history")

        // A card tap hands the owner the exact scope and identity.
        for card in cards { OriginalMarketCatalogue9483.action(card, onSelect: catalogue.onSelect)?() }
        XCTAssertEqual(log, ["select:243945029", "select:243939188", "select:243945042"])

        // Final: each separately admitted grade beside its own pregame chance.
        func shown(_ identity: Originals.Identity) -> Originals.Content? {
            let final = HockeyJourneyEventPagePresentation10868(input: Self.page(.final), mode: .original,
                                                                originals: Self.originals(.final, holding: identity))
            let mounted = final.originalDetailsContent()!
            return Originals.content(catalogue: mounted.catalogue, selection: mounted.selection)
        }
        XCTAssertEqual(shown(Self.kaprizovTwo)?.result?.words, "Won")
        XCTAssertEqual(shown(Self.kaprizovTwo)?.readings.map(\.text), ["39%"])
        XCTAssertEqual(shown(Self.hughesThree)?.result?.words, "Lost")
        XCTAssertEqual(shown(Self.hughesThree)?.readings.map(\.text), ["No retained pregame chance"])

        // No callbacks: static; no originals group: no content.
        let quiet = HockeyJourneyEventPagePresentation10868(input: Self.page(.live), mode: .catalogue, originals: originals)
        XCTAssertNil(quiet.catalogueContent()?.onSelect)
        XCTAssertNil(quiet.originalDetailsContent()?.onHistory)
        XCTAssertNil(HockeyJourneyEventPagePresentation10868(input: Self.page(.live), mode: .catalogue).catalogueContent())
        XCTAssertNil(HockeyJourneyEventPagePresentation10868(input: Self.page(.live), mode: .original).originalDetailsContent())
    }
}
