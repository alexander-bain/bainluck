import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the golf tournament screen composed from the accepted leaves.
///
/// The view is SwiftUI and is not rasterised here. What is asserted is the
/// composition only: which actual leaf Views the page mounts in each
/// golf-reading phase for one selected golfer, that each receives the owner's
/// input unchanged, the "What changed?" signed-change rows and their choose
/// action, the owner's status and its Pause / Resume-updates action, the
/// full-size history without its expand control, the arrangement candidates,
/// and that every host callback reaches its leaf and nothing fires passively.
/// Each leaf's own rules stay with its own tests; nothing here claims a
/// rendered fit, a native runtime, VoiceOver behaviour, a held-reading
/// qualification or a production binding.
///
/// ARCHIVED raw values come from the Baycurrent Classic, October 8–11, 2026
/// (market 64266833 "Baycurrent Classic - Winner", source datagolf):
/// - the before-tournament win records of Michael Brennan (241857512), Xander
///   Schauffele (242242520) and Keith Mitchell (242242559) at the last two
///   clocks they share, 2026-10-05T17:39:14Z and 2026-10-06T13:08:40Z, as kept
///   in `FieldProbabilityHistoryPresentation10868Tests`
///   (FIELD-HISTORY-RETAINED-CASES.json), plus Michael Thorbjornsen
///   (242242545), who has no history in the capture;
/// - `golf-native-ready-composition-20261026/support/finish-expectations-oracle.json`
///   (sha256 2878b5ca…0796): Brennan's finish at Before (case 88), recorded
///   through 2026-10-08T02:01:32Z (case 92) and Final (case 95, position 1);
///   the same recorded clock's win readings for Schauffele (case 4) and
///   Mitchell (case 196); and the last win readings recorded through
///   2026-10-11T06:41:26Z for Brennan (case 93), Schauffele (case 5,
///   06:06:55Z) and Mitchell (case 197).
///
/// CONSTRUCTED owner input (this layer resolves none of it): every scope,
/// id, label, figure text, clock line, key, tint, shape, scale, tick, copy,
/// status and frame word, the change words (the reference's own rounding of
/// the archived changes), the page phase and every phase-leak control.
final class GolfEventPagePresentation10868Tests: XCTestCase {

    // MARK: Retained golfers

    private struct Golfer {
        let outcome: String
        let name: String
        let short: String
        /// ARCHIVED (earlier, later) before-tournament probabilities; nil = no history.
        let before: (Double, Double)?
        /// CONSTRUCTED owner text for those two readings.
        let text: (String, String)?
        /// ARCHIVED Round 1 reading recorded through 2026-10-08T02:01:32Z, with its text.
        let round1: (Double, String)?
        /// ARCHIVED last reading: timestamp/value; CONSTRUCTED figure and its OWN local clock.
        let last: (Double, Double, String, String)?
        /// CONSTRUCTED change words for the before pair.
        let change: String?
    }

    /// ARCHIVED clocks.
    private static let earlierX = 1_791_221_954.507306   // 2026-10-05T17:39:14.507306Z
    private static let laterX = 1_791_292_120.644152     // 2026-10-06T13:08:40.644152Z
    private static let round1X = 1_791_424_892.422514    // 2026-10-08T02:01:32.422514Z
    private static let finalX = 1_791_700_886.165769     // 2026-10-11T06:41:26.165769Z
    private static let schauffeleLastX = 1_791_698_815.965994 // 2026-10-11T06:06:55.965994Z

    private static let brennan = Golfer(
        outcome: "241857512", name: "Michael Brennan", short: "Brennan",
        before: (0.026167, 0.026017), text: ("2.6%", "2.6%"),
        round1: (0.017605, "1.8%"), last: (finalX, 1, "100%", finalClock), change: "↓ <0.1 pts")
    private static let schauffele = Golfer(
        outcome: "242242520", name: "Xander Schauffele", short: "Schauffele",
        before: (0.089, 0.086583), text: ("8.9%", "8.7%"),
        round1: (0.142239, "14.2%"), last: (schauffeleLastX, 0, "0%", "Oct 10, 11:06 PM PT · DataGolf"), change: "↓ 0.2 pts")
    private static let mitchell = Golfer(
        outcome: "242242559", name: "Keith Mitchell", short: "Mitchell",
        before: (0.012467, 0.012733), text: ("1.2%", "1.3%"),
        round1: (0.012546, "1.3%"), last: (finalX, 0, "0%", finalClock), change: "↑ <0.1 pts")
    private static let thorbjornsen = Golfer(
        outcome: "242242545", name: "Michael Thorbjornsen", short: "Thorbjornsen",
        before: nil, text: nil, round1: nil, last: nil, change: nil)
    private static let golfers = [brennan, schauffele, mitchell, thorbjornsen]

    /// CONSTRUCTED clock words.
    private static let earlierTime = "Oct 5, 10:39 AM PT"
    private static let laterTime = "Oct 6, 6:08 AM PT"
    private static let earlierClock = "\(earlierTime) · DataGolf"
    private static let laterClock = "\(laterTime) · DataGolf"
    private static let round1Clock = "Oct 7, 7:01 PM PT · DataGolf"
    private static let finalClock = "Oct 10, 11:41 PM PT · DataGolf"

    private static let scope = "datagolf|pga:527|win"

    private static func ref(_ golfer: Golfer, scope: String = scope) -> FieldChooserOriginalRef10868 {
        FieldChooserOriginalRef10868(scope: scope, source: "datagolf", marketID: "64266833", outcomeID: golfer.outcome)
    }

    private static func seriesID(_ golfer: Golfer) -> String { "datagolf:64266833:\(golfer.outcome)" }

    private static func laterReading(_ golfer: Golfer) -> FieldChooserReading10868 {
        FieldChooserReading10868(
            label: "Before tournament",
            value: golfer.text.map { .recorded(text: $0.1, detail: laterClock) } ?? .missing("No before-tournament estimate")
        )
    }

    // MARK: Constructed leaf inputs

    private static var catalogue: [FieldChooserOriginal10868] {
        golfers.map { golfer in
            FieldChooserOriginal10868(
                ref: ref(golfer), name: golfer.name, plan: .single(laterReading(golfer)),
                preview: FieldChooserPreview10868(history: nil, absence: "No captured history"),
                movement: nil, clock: nil, result: nil, browseStatus: ""
            )
        }
    }

    private static var selected: FieldChooserSelected10868 {
        FieldChooserSelected10868(ref: ref(brennan), words: "Pinned", unavailableWords: "Golfer unavailable")
    }

    private static func ticks(_ values: [(Double, String)]) -> [FieldHistoryTick10868] {
        values.map { FieldHistoryTick10868(value: $0.0, lines: [$0.1]) }
    }

    /// The anchor at one phase: before-tournament points always; the Round 1
    /// reading once recorded; the last readings at Final. Same selected golfer.
    private static func history(_ phase: GolfFinishPhase10868) -> FieldHistoryInput10868 {
        let series = golfers.map { golfer -> FieldHistorySeries10868 in
            let id = seriesID(golfer)
            var points: [FieldHistoryPoint10868] = golfer.before.map { pair in
                [FieldHistoryPoint10868(id: "\(id)#earlier", x: earlierX, probability: pair.0, style: .hollow),
                 FieldHistoryPoint10868(id: "\(id)#later", x: laterX, probability: pair.1, style: .filled)]
            } ?? []
            var recorded: FieldHistoryReading10868 = .absent(words: "Not recorded")
            if phase != .before, let round1 = golfer.round1 {
                points.append(FieldHistoryPoint10868(id: "\(id)#round1", x: round1X, probability: round1.0, style: .filled))
                if phase == .recorded {
                    recorded = .observation(pointID: "\(id)#round1", figure: round1.1, provenance: round1Clock)
                }
            }
            if phase == .final, let last = golfer.last {
                points.append(FieldHistoryPoint10868(id: "\(id)#last", x: last.0, probability: last.1, style: .filled))
                recorded = .observation(pointID: "\(id)#last", figure: last.2, provenance: last.3)
            }
            return FieldHistorySeries10868(
                id: id, name: golfer.name, shape: .circle, tint: .blue,
                runs: points.map { FieldHistoryRun10868(id: "\($0.id)#run", points: [$0]) },
                links: [], labelPointID: points.last?.id,
                before: golfer.before.map { _ in .observation(pointID: "\(id)#later", figure: golfer.text!.1, provenance: laterClock) }
                    ?? .absent(words: "No before-tournament estimate"),
                recorded: recorded,
                absentWords: "No captured history",
                choose: FieldHistoryAction10868(id: "choose:\(golfer.outcome)", label: "Choose \(golfer.name)",
                                                spokenLabel: nil, isAvailable: true)
            )
        }
        let caption: String, upper: Double, ceiling: Double, yTicks: [FieldHistoryTick10868], readout: FieldHistoryReadoutIntent10868
        switch phase {
        case .before:
            caption = "Before tournament"; upper = 1_791_417_600; ceiling = 0.10
            yTicks = ticks([(0, "0%"), (0.05, "5%"), (0.10, "10%")])
            readout = .singleBefore(label: "Before tournament · last estimate")
        case .recorded:
            caption = "Recorded · Round 1"; upper = 1_791_504_000; ceiling = 0.15
            yTicks = ticks([(0, "0%"), (0.05, "5%"), (0.10, "10%"), (0.15, "15%")])
            readout = .beforeAndRecorded(beforeLabel: "Before tournament", recordedLabel: "Round 1 · Oct 7, 7:01 PM PT")
        case .final:
            caption = "Recorded · Tournament history"; upper = 1_791_763_200; ceiling = 1
            yTicks = ticks([(0, "0%"), (0.5, "50%"), (1, "100%")])
            readout = .beforeAndRecorded(beforeLabel: "Before tournament", recordedLabel: "Last recorded")
        }
        return FieldHistoryInput10868(
            title: "Chance to win", caption: caption, series: series,
            selection: .series(id: seriesID(brennan), missingWords: "Golfer unavailable"),
            domain: FieldHistoryDomain10868(lower: 1_791_158_400, upper: upper),
            ceiling: ceiling, yTicks: yTicks, xTicks: [], guides: [], breaks: [],
            readout: readout,
            markKey: FieldHistoryMarkKey10868(hollow: "Earlier estimate", filled: "Recorded estimate"),
            comparisonExplanation: nil, notes: ["DataGolf model history · times in Pacific time"],
            summary: "Win probability for the chosen golfers.",
            plotHeight: 240, unboundReadingWords: "Not recorded", plotUnavailableWords: "History unavailable",
            windows: nil, scale: nil,
            moreOriginals: FieldHistoryAction10868(id: "more", label: "More golfers", spokenLabel: nil, isAvailable: true),
            details: FieldHistoryAction10868(id: "details", label: "History details", spokenLabel: nil, isAvailable: true),
            expand: FieldHistoryAction10868(id: "expand", label: "Expand", spokenLabel: "Expand win probability chart", isAvailable: true),
            inspect: nil, previous: nil, next: nil, inspection: nil
        )
    }

    private static func finishSlot(_ selection: String, _ name: String, before: GolfFinishObservation10868?,
                                   recorded: GolfFinishObservation10868? = nil,
                                   actual: GolfFinishResult10868 = GolfFinishResult10868(text: "Unknown", mark: .unknown))
        -> GolfFinishSlot10868 {
        GolfFinishSlot10868(selection: selection, name: name, color: .blue, before: before, recorded: recorded,
                            beforeMissing: "Not recorded before tournament", recordedMissing: "Not recorded during play",
                            actual: actual)
    }

    private static func obs(_ p: Double, _ text: String, _ detail: String) -> GolfFinishObservation10868 {
        GolfFinishObservation10868(probability: p, text: text, accessibilityDetail: detail)
    }

    private static let beforeDetail = "recorded Oct 6, 6:08 AM PT · DataGolf consensus"
    private static let recordedDetail = "recorded Oct 7, 7:01 PM PT · DataGolf consensus"
    private static let won = GolfFinishResult10868(text: "Won", mark: .success)
    private static let inside = GolfFinishResult10868(text: "Inside", mark: .success)

    /// Brennan's finish: case 88 at Before, case 92 recorded, case 95 at Final.
    private static func brennanFinish(_ phase: GolfFinishPhase10868) -> GolfFinishExpectationInput10868 {
        func slot(_ id: String, _ name: String, _ before: (Double, String), _ recorded: (Double, String),
                  _ actual: GolfFinishResult10868) -> GolfFinishSlot10868 {
            finishSlot(id, name, before: obs(before.0, before.1, beforeDetail),
                       recorded: phase == .recorded ? obs(recorded.0, recorded.1, recordedDetail) : nil,
                       actual: phase == .final ? actual : GolfFinishResult10868(text: "Unknown", mark: .unknown))
        }
        return GolfFinishExpectationInput10868(
            win: slot("64266833", "Win", (0.026017, "2.6%"), (0.017605, "1.8%"), won),
            top5: slot("64266834", "Top 5", (0.11956, "12%"), (0.11368, "11.4%"), inside),
            top10: slot("64266835", "Top 10", (0.225636, "22.6%"), (0.22588, "22.6%"), inside),
            top20: slot("64266836", "Top 20", (0.411461, "41.1%"), (0.43116, "43.1%"), inside),
            phase: phase, title: "Finish expectations", golferName: "Michael Brennan",
            context: nil, actualSummary: phase == .final ? "Won · −16" : nil,
            selected: phase == .recorded ? "64266833" : nil
        )
    }

    private static let outlookScale = FieldOutlookScale10868(
        ceiling: 0.10,
        ticks: [FieldOutlookTick10868(probability: 0, label: "0%"), FieldOutlookTick10868(probability: 0.05, label: "5%"),
                FieldOutlookTick10868(probability: 0.10, label: "10%")],
        words: "Chance to win · shared scale 0–10%"
    )

    private static func contenders(_ phase: FieldOutlookPhase10868 = .before) -> FieldOutlookInput10868 {
        FieldOutlookInput10868(
            scope: scope, catalogue: catalogue, selected: selected,
            displayed: golfers.map { FieldOutlookSlot10868(ref: ref($0), label: $0.name, shortLabel: $0.short) },
            traversal: golfers.map { ref($0) },
            chances: golfers.compactMap { golfer in
                golfer.before.map { FieldOutlookBeforeChance10868(ref: ref(golfer), probability: $0.1, reading: laterReading(golfer)) }
            },
            scale: outlookScale, phase: phase,
            copy: FieldOutlookCopy10868(
                title: "Who starts strongest?", note: "4 captured golfers · Oct 6, 6:08 AM PT",
                graphicLabel: "Captured contenders", missingChance: "Not shown on this scale",
                offScale: "Above the 10% scale", outsideDisplayed: "Your golfer is not among these bars",
                previousLabel: "Previous golfer", nextLabel: "Next golfer", details: "Contender & source details",
                detailsHint: nil, resultUnknown: "Result unconfirmed"
            ),
            unavailableWords: "Golfer unavailable in this update", chooseHint: "Shows this golfer in the chart"
        )
    }

    /// The owner's displayed order (largest change first, the selected golfer
    /// included), its pairs and its signed scale.
    private static let movementShown = [schauffele, mitchell, brennan]
    private static let movementLimit = 0.003

    private static func movementReading(_ golfer: Golfer, later: Bool) -> FieldChooserReading10868 {
        later
            ? FieldChooserReading10868(label: "Later", value: .recorded(text: golfer.text!.1, detail: laterClock))
            : FieldChooserReading10868(label: "Earlier", value: .recorded(text: golfer.text!.0, detail: earlierClock))
    }

    private static func movement(_ phase: FieldOutlookPhase10868 = .before) -> GolfBeforeMovementInput10868 {
        let catalogue = golfers.map { golfer in
            FieldChooserOriginal10868(
                ref: ref(golfer), name: golfer.name,
                plan: golfer.text == nil
                    ? .single(laterReading(golfer))
                    : .comparison(before: movementReading(golfer, later: false), later: movementReading(golfer, later: true)),
                preview: FieldChooserPreview10868(history: nil, absence: "No captured history"),
                movement: nil, clock: nil, result: nil, browseStatus: ""
            )
        }
        let pairs = movementShown.map { golfer in
            FieldMovementPair10868(
                ref: ref(golfer),
                before: FieldMovementObservation10868(probability: golfer.before!.0, reading: movementReading(golfer, later: false)),
                later: FieldMovementObservation10868(probability: golfer.before!.1, reading: movementReading(golfer, later: true)),
                movement: golfer.change, observation: "\(golfer.outcome)#later"
            )
        }
        return GolfBeforeMovementInput10868(
            movement: FieldMovementInput10868(
                scope: scope, catalogue: catalogue,
                displayed: movementShown.map { FieldOutlookSlot10868(ref: ref($0), label: $0.name, shortLabel: $0.short) },
                pairs: pairs,
                scale: FieldMovementScale10868(
                    limit: movementLimit,
                    ticks: [FieldMovementTick10868(change: -movementLimit, label: "−0.3 pts"),
                            FieldMovementTick10868(change: 0, label: "0"),
                            FieldMovementTick10868(change: movementLimit, label: "+0.3 pts")],
                    words: "Change in chance · −0.3 to +0.3 percentage points"
                ),
                phase: phase,
                copy: FieldMovementCopy10868(
                    title: "What changed?", note: "Win chances across two recorded estimates",
                    graphicLabel: "Change in chance between two recorded estimates",
                    beforeLabel: "Earlier", laterLabel: "Later",
                    endpointUnavailable: "Not recorded for this comparison", changeUnavailable: "Change unavailable",
                    offScale: "Beyond the ±0.3 pts scale", openLabel: "Show in chart",
                    openHint: "Pins this golfer in the win probability chart"
                ),
                unavailableWords: "Golfer unavailable in this update"
            ),
            selected: ref(brennan),
            times: GolfBeforeMovementTimes10868(earlier: earlierTime, later: laterTime)
        )
    }

    private static var chooser: FieldChooserInput10868 {
        FieldChooserInput10868(
            scope: scope, intro: nil,
            featured: FieldChooserFeatured10868(title: "In your chart", badge: nil,
                                                refs: [ref(brennan), ref(schauffele), ref(mitchell)],
                                                emptyWords: "No golfers in your chart"),
            context: nil, more: nil, browse: nil, catalogue: catalogue, frame: nil, selected: selected,
            unavailableWords: "Golfer unavailable in this update", chooseHint: "Shows this golfer in the chart"
        )
    }

    private static func copy(_ phase: GolfFinishPhase10868) -> GolfEventPageCopy10868 {
        let words: (String, String) = switch phase {
        case .before: ("Recorded replay · Before tournament", "History through Oct 6, 6:08 AM PT")
        case .recorded: ("Recorded replay · Round 1", "History through Oct 7, 7:01 PM PT")
        case .final: ("Final · October 8–11", "History through Oct 10, 11:41 PM PT")
        }
        return GolfEventPageCopy10868(
            eyebrow: words.0, title: "Baycurrent Classic", context: words.1, aboutLabel: "About recorded golf replay",
            storiesLabel: "Tournament stories", finishUnavailable: "Finish expectations unavailable for this golfer"
        )
    }

    private static let resume = FieldHistoryAction10868(
        id: "status.resume", label: "Resume updates", spokenLabel: "Resume recorded updates. 3 waiting", isAvailable: true)
    private static let pause = FieldHistoryAction10868(
        id: "status.pause", label: "Pause", spokenLabel: "Pause recorded updates", isAvailable: true)

    private static func held(_ action: FieldHistoryAction10868? = Self.resume) -> GolfEventPageStatus10868 {
        GolfEventPageStatus10868(title: "Recorded replay held", words: "3 recorded updates waiting", action: action)
    }

    private static let beforeTee = "Before the first tee"

    /// The page for one phase. Its default leaves are that phase's own; a test
    /// passes another phase's leaf only as a phase-leak control.
    private static func page(_ phase: GolfFinishPhase10868,
                             status: GolfEventPageStatus10868? = Self.held(),
                             finish: GolfFinishExpectationInput10868? = nil,
                             contenders: FieldOutlookInput10868? = Self.contenders(),
                             movement: GolfBeforeMovementInput10868? = Self.movement(),
                             openLabels: Bool = true) -> GolfEventPageInput10868 {
        GolfEventPageInput10868(
            phase: phase, copy: Self.copy(phase), status: status, history: Self.history(phase),
            finish: finish ?? Self.brennanFinish(phase),
            finishFrame: GolfEventPageCardFrame10868(eyebrow: nil, openLabel: openLabels ? "Expand finish expectations" : "  "),
            contenders: contenders,
            contendersFrame: GolfEventPageCardFrame10868(eyebrow: beforeTee, openLabel: openLabels ? "Expand pre-tournament contenders" : nil),
            movement: movement,
            movementFrame: GolfEventPageCardFrame10868(eyebrow: beforeTee, openLabel: openLabels ? "Expand pre-tournament movement" : nil),
            chooser: Self.chooser
        )
    }

    // MARK: Phases — one selected golfer, each phase's own context

    @MainActor
    func testBeforeMountsTheActualLeavesForOneSelectedGolferAtItsOwnPhase() {
        let input = Self.page(.before)
        let view = GolfEventPagePresentation10868(input: input)
        XCTAssertEqual(view.mode, .page)
        XCTAssertEqual(GolfEventPageModel10868(input).stories, [.finish, .contenders, .movement])

        // The anchor is the history leaf with the owner's input unchanged: only
        // before-tournament points, and Thorbjornsen, with no history, keeps
        // his name and own absence words.
        let anchor: FieldProbabilityHistoryPresentation10868 = view.historyContent(reader: false)
        XCTAssertEqual(anchor.input, input.history)
        XCTAssertEqual(anchor.input.series.map(\.name), Self.golfers.map(\.name))
        XCTAssertTrue(anchor.input.series.flatMap(\.runs).flatMap(\.points).allSatisfy { $0.x <= Self.laterX })
        XCTAssertEqual(anchor.input.series[3].runs, [])
        XCTAssertEqual(anchor.input.series[3].before, .absent(words: "No before-tournament estimate"))
        XCTAssertEqual(anchor.input.plotHeight, 240)

        // The same golfer — Brennan — across the chart, finish, both before
        // cards and the chooser.
        let brennan = Self.ref(Self.brennan)
        XCTAssertEqual(anchor.input.selection, .series(id: Self.seriesID(Self.brennan), missingWords: "Golfer unavailable"))
        let finish: GolfFinishExpectationPresentation10868? = view.finishContent()
        XCTAssertEqual(finish?.input, Self.brennanFinish(.before))
        XCTAssertEqual(finish?.input.golferName, "Michael Brennan")
        XCTAssertEqual(finish?.input.slots.map(\.recorded), [nil, nil, nil, nil])
        let contenders: FieldOutlookBarsPresentation10868? = view.contendersContent()
        XCTAssertEqual(contenders?.input, input.contenders)
        XCTAssertEqual(contenders?.input.selected?.ref, brennan)
        XCTAssertEqual(contenders?.input.displayed.last?.label, "Michael Thorbjornsen")
        let movement: GolfBeforeMovementPresentation10868? = view.movementContent()
        XCTAssertEqual(movement?.input, input.movement)
        XCTAssertEqual(movement?.input.selected, brennan)
        XCTAssertEqual(view.chooserContent()?.input.selected?.ref, brennan)
        XCTAssertEqual(input.copy.context, "History through Oct 6, 6:08 AM PT")
    }

    @MainActor
    func testARecordedRoundShowsTheSameGolfersRoundOneHistoryAndFinishButNoBeforeCards() {
        let input = Self.page(.recorded)
        let model = GolfEventPageModel10868(input)
        let view = GolfEventPagePresentation10868(input: input)
        XCTAssertEqual(model.stories, [.finish])
        XCTAssertEqual(input.copy.eyebrow, "Recorded replay · Round 1")

        // The anchor reaches the Round 1 clock and no further; Brennan's
        // recorded readout is his own Round 1 observation.
        let anchor = view.historyContent(reader: false).input
        XCTAssertEqual(anchor.series.flatMap(\.runs).flatMap(\.points).map(\.x).max(), Self.round1X)
        XCTAssertEqual(anchor.series[0].recorded,
                       .observation(pointID: "\(Self.seriesID(Self.brennan))#round1", figure: "1.8%", provenance: Self.round1Clock))
        XCTAssertEqual(anchor.selection, .series(id: Self.seriesID(Self.brennan), missingWords: "Golfer unavailable"))

        let finish = view.finishContent()?.input
        XCTAssertEqual(finish, Self.brennanFinish(.recorded))
        XCTAssertEqual(finish?.slots.compactMap(\.recorded?.probability), [0.017605, 0.11368, 0.22588, 0.43116])
        XCTAssertEqual(finish?.actualSummary, nil)

        // The before cards are supplied with their own before phase, yet a
        // recorded round mounts neither.
        XCTAssertNil(view.contendersContent())
        XCTAssertNil(view.movementContent())
        XCTAssertFalse(model.readerShows(.contenders))
        XCTAssertFalse(model.readerShows(.movement))
        XCTAssertTrue(model.readerShows(.history))
        XCTAssertNil(model.openAction(.movement, canOpen: true))
        XCTAssertEqual(model.openAction(.finish, canOpen: true), .finish)

        // Phase-leak control: Brennan's Final results never reach a recorded round.
        XCTAssertNil(GolfEventPagePresentation10868(input: Self.page(.recorded, finish: Self.brennanFinish(.final))).finishContent())
    }

    @MainActor
    func testFinalCarriesTheSameGolfersSeparatelyAdmittedResultsAndLaterValuesNeverReachAnEarlierPhase() {
        let final = Self.page(.final, status: nil)
        let view = GolfEventPagePresentation10868(input: final)
        XCTAssertEqual(GolfEventPageModel10868(final).stories, [.finish])
        let finish = view.finishContent()
        XCTAssertEqual(finish?.input, Self.brennanFinish(.final))
        XCTAssertEqual(finish?.input.golferName, "Michael Brennan")
        XCTAssertEqual(finish?.input.slots.map(\.actual), [Self.won, Self.inside, Self.inside, Self.inside])
        XCTAssertEqual(finish?.input.slots.map(\.recorded), [nil, nil, nil, nil])
        XCTAssertEqual(finish?.input.actualSummary, "Won · −16")
        // The anchor's last readings are separate recorded observations, not
        // the result substituted as 100%.
        XCTAssertEqual(view.historyContent(reader: false).input.series[0].recorded,
                       .observation(pointID: "\(Self.seriesID(Self.brennan))#last", figure: "100%", provenance: Self.finalClock))
        XCTAssertEqual(view.historyContent(reader: false).input.series[3].runs, [])
        // Schauffele's last recorded win estimate is 35 minutes earlier than
        // Brennan's: its own clock must travel with its own point/readout.
        let schauffeleID = Self.seriesID(Self.schauffele)
        let schauffele = final.history.series.first { $0.id == schauffeleID }
        XCTAssertEqual(schauffele?.recorded,
                       .observation(pointID: "\(schauffeleID)#last", figure: "0%",
                                    provenance: "Oct 10, 11:06 PM PT · DataGolf"))
        XCTAssertTrue(schauffele?.runs.flatMap(\.points).contains { $0.id == "\(schauffeleID)#last" && $0.x == Self.schauffeleLastX } == true)
        XCTAssertNil(GolfEventPageModel10868(final).statusAction(canAct: true))

        // Phase-leak controls at Before: neither Brennan's Final nor his
        // recorded finish, nor before cards whose own phase is later, mount;
        // the finish card keeps the owner's absence words instead.
        for leak in [Self.brennanFinish(.final), Self.brennanFinish(.recorded)] {
            let before = Self.page(.before, finish: leak, contenders: Self.contenders(.final), movement: Self.movement(.during))
            let still = GolfEventPagePresentation10868(input: before)
            XCTAssertNil(still.finishContent())
            XCTAssertNil(still.contendersContent())
            XCTAssertNil(still.movementContent())
            XCTAssertEqual(GolfEventPageModel10868(before).stories, [.finish])
            XCTAssertEqual(before.copy.finishUnavailable, "Finish expectations unavailable for this golfer")
        }
        // A Final page refuses a recorded finish rather than relabelling it.
        XCTAssertNil(GolfEventPagePresentation10868(input: Self.page(.final, finish: Self.brennanFinish(.recorded))).finishContent())
    }

    // MARK: What changed?

    @MainActor
    func testWhatChangedDrawsEachSignedChangeFromZeroAndARowPinsThatExactGolfer() {
        let input = Self.movement()
        let model = GolfBeforeMovementModel10868(input)
        // The inherited card keeps its own gate — no card before the event —
        // and is not forced into another phase; this card keeps `.before`.
        XCTAssertFalse(FieldMovementModel10868(input.movement).isShown)
        XCTAssertEqual(FieldMovementModel10868(input.movement).rows, [])
        XCTAssertTrue(model.isShown)

        let rows = model.rows
        XCTAssertEqual(rows.map(\.slot.label), ["Xander Schauffele", "Keith Mitchell", "Michael Brennan"])

        // Schauffele: the raw later − earlier change on the owner's ±0.3 pt scale.
        let schauffele = (0.086583 - 0.089) / Self.movementLimit
        guard case .value(_, let fraction) = rows[0].change else { return XCTFail("Schauffele has a placed change") }
        XCTAssertEqual(fraction, schauffele, accuracy: 1e-12)
        XCTAssertEqual(model.movement.movementWords(rows[0]), "↓ 0.2 pts")
        let band = CGSize(width: 300, height: 4)
        let plan = FieldMovementGeometry10868.markPlan(fraction: fraction, in: band, orientation: .horizontal)
        let length = 150 * CGFloat(abs(schauffele))
        XCTAssertEqual(plan.fill?.minX ?? .nan, 150 - length, accuracy: 1e-9)
        XCTAssertEqual(plan.fill?.maxX ?? .nan, 150, accuracy: 1e-9)
        XCTAssertEqual(GolfBeforeMovementModel10868.markPosition(rows[0].change) ?? .nan, (1 + schauffele) / 2, accuracy: 1e-12)

        // Mitchell rises: right of the zero line.
        guard case .value(let rise, _) = rows[1].change else { return XCTFail("Mitchell has a placed change") }
        XCTAssertGreaterThan(rise, 0)
        XCTAssertGreaterThan(GolfBeforeMovementModel10868.markPosition(rows[1].change) ?? 0, 0.5)
        XCTAssertEqual(model.movement.movementWords(rows[1]), "↑ <0.1 pts")

        // Brennan prints 2.6% twice, but his raw change is a small fall: a
        // placed, non-zero bar with the owner's "<0.1" words, never "no change".
        guard case .value(let fall, _) = rows[2].change else { return XCTFail("Brennan has a placed change") }
        XCTAssertEqual(fall, 0.026017 - 0.026167)
        XCTAssertLessThan(fall, 0)
        XCTAssertEqual(rows[2].before, .reading(Self.movementReading(Self.brennan, later: false)))
        XCTAssertEqual(rows[2].later, .reading(Self.movementReading(Self.brennan, later: true)))
        XCTAssertEqual(model.movement.movementWords(rows[2]), "↓ <0.1 pts")
        XCTAssertNil(FieldMovementGeometry10868.markPlan(fraction: rows[2].change.fraction, in: band, orientation: .horizontal).zeroMark)
        XCTAssertEqual(model.movement.ticks.map(\.fraction), [-1, 0, 1])

        // The owner's selected golfer is marked; nothing is ranked here.
        XCTAssertEqual(rows.map(model.isSelected), [false, false, true])

        // A row tap pins that exact golfer through the host's choose action.
        var chosen: [FieldChooserOriginalRef10868] = []
        let card = GolfBeforeMovementPresentation10868(input: input, onChoose: { chosen.append($0) })
        XCTAssertEqual(chosen, [])
        card.choose(rows[2])
        card.choose(rows[0])
        XCTAssertEqual(chosen, [Self.ref(Self.brennan), Self.ref(Self.schauffele)])

        // Without a callback, no row acts.
        let still = GolfBeforeMovementPresentation10868(input: input)
        XCTAssertNil(model.chooseRef(rows[2], canChoose: false))
        still.choose(rows[2])
        XCTAssertEqual(chosen.count, 2)

        // During or after the event this card has no rows.
        XCTAssertEqual(GolfBeforeMovementModel10868(Self.movement(.during)).rows, [])
        XCTAssertEqual(GolfBeforeMovementModel10868(Self.movement(.final)).rows, [])
    }

    /// A change of exactly ±scale is drawn whole: the later mark is centred on
    /// the inset edge, the fill reaches it, and the axis labels share that
    /// inset across the row padding. Nothing is clamped or widened.
    @MainActor
    func testTheSignedTrackKeepsAWholeMarkAtExactlyTheScaleAndItsAxisSharesTheInset() {
        let mark: CGFloat = 10
        let inset = GolfBeforeMovementModel10868.inset(markSize: mark)
        XCTAssertEqual(inset, FieldExpectationsGeometry10868.inset(markDiameter: mark))
        let size = CGSize(width: 300, height: 28)
        let ticks: [Double] = [-1, 0, 1]
        func plan(_ change: FieldMovementChange10868, _ size: CGSize = size) -> GolfBeforeMovementTrackPlan10868? {
            GolfBeforeMovementModel10868.trackPlan(change: change, ticks: ticks, in: size, markSize: mark, bandHeight: 4)
        }

        for fraction in [-1.0, 1.0] {
            guard let drawn = plan(.value(change: fraction * Self.movementLimit, fraction: fraction)),
                  let dot = drawn.dot, let fill = drawn.fill
            else { return XCTFail("±scale draws a fill and a mark") }
            XCTAssertEqual(drawn.startX, inset)
            XCTAssertEqual(drawn.endX, size.width - inset)
            XCTAssertEqual(drawn.zeroX, size.width / 2, accuracy: 1e-9)
            XCTAssertEqual(drawn.tickXs, [drawn.startX, drawn.endX])
            let edge = fraction > 0 ? drawn.endX : drawn.startX
            XCTAssertEqual(dot.midX, edge, accuracy: 1e-9)
            XCTAssertEqual(dot.width, mark)
            XCTAssertGreaterThanOrEqual(dot.minX, 0)
            XCTAssertLessThanOrEqual(dot.maxX, size.width)
            XCTAssertEqual(fraction > 0 ? fill.maxX : fill.minX, edge, accuracy: 1e-9)
            XCTAssertEqual(fraction > 0 ? fill.minX : fill.maxX, drawn.zeroX, accuracy: 1e-9)
            XCTAssertNil(drawn.zeroMark)
        }

        // No change: the neutral mark and the later mark on the zero line, no fill.
        guard let zero = plan(.value(change: 0, fraction: 0)), let zeroMark = zero.zeroMark
        else { return XCTFail("zero draws its neutral mark") }
        XCTAssertNil(zero.fill)
        XCTAssertEqual(zeroMark.midX, zero.zeroX, accuracy: 1e-9)
        XCTAssertEqual(zero.dot?.midX ?? .nan, zero.zeroX, accuracy: 1e-9)

        // Off-scale and unavailable keep the line and draw no fill or mark.
        for change in [FieldMovementChange10868.offScale(rising: true), .unavailable] {
            XCTAssertNil(plan(change)?.dot)
            XCTAssertNil(plan(change)?.fill)
            XCTAssertNotNil(plan(change))
        }

        // Small widths: still whole while the span is positive; none at all
        // once the width or height cannot hold a whole mark.
        let narrow = CGSize(width: 2 * inset + 4, height: 28)
        guard let small = plan(.value(change: Self.movementLimit, fraction: 1), narrow), let smallDot = small.dot
        else { return XCTFail("a narrow positive span still draws") }
        XCTAssertGreaterThanOrEqual(smallDot.minX, 0)
        XCTAssertLessThanOrEqual(smallDot.maxX, narrow.width)
        XCTAssertNil(plan(.value(change: Self.movementLimit, fraction: 1), CGSize(width: 2 * inset, height: 28)))
        XCTAssertNil(plan(.value(change: Self.movementLimit, fraction: 1), CGSize(width: 300, height: mark - 1)))

        // The axis: the owner's ticks at the track's own places, across the row padding.
        let model = GolfBeforeMovementModel10868(Self.movement())
        let units = GolfBeforeMovementModel10868.axisUnits(model.movement.ticks)
        XCTAssertEqual(units, [0, 0.5, 1])
        let padding = GolfBeforeMovementModel10868.rowPadding
        let card: CGFloat = 324
        guard let rowTrack = plan(.unavailable, CGSize(width: card - 2 * padding, height: 28))
        else { return XCTFail("the row track draws") }
        let axisXs = units.compactMap { FieldFinishGeometry10868.x(of: $0, width: card, inset: padding + inset) }
        let trackXs = [rowTrack.startX, rowTrack.zeroX, rowTrack.endX].map { $0 + padding }
        XCTAssertEqual(axisXs.count, 3)
        for (axisX, trackX) in zip(axisXs, trackXs) { XCTAssertEqual(axisX, trackX, accuracy: 1e-9) }
    }

    // MARK: Status

    @MainActor
    func testTheOwnersStatusShowsItsWordsAndOnePauseOrResumeAction() {
        var log: [String] = []
        let input = Self.page(.recorded)
        let model = GolfEventPageModel10868(input)
        let view = GolfEventPagePresentation10868(input: input, onHistoryAction: { log.append("history:\($0)") })
        XCTAssertEqual(input.status?.words, "3 recorded updates waiting")
        XCTAssertEqual(model.statusAction(canAct: true), Self.resume)
        XCTAssertEqual(log, [])
        view.actOnStatus()
        XCTAssertEqual(log, ["history:status.resume"])

        // The owner's Pause, when following.
        let following = Self.page(.recorded, status: GolfEventPageStatus10868(title: "Following Round 1", words: nil, action: Self.pause))
        GolfEventPagePresentation10868(input: following, onHistoryAction: { log.append("history:\($0)") }).actOnStatus()
        XCTAssertEqual(log, ["history:status.resume", "history:status.pause"])

        // Callback-free: the words stay and the action is not drawn.
        XCTAssertNil(model.statusAction(canAct: false))
        GolfEventPagePresentation10868(input: input).actOnStatus()

        // Not eligible now: drawn disabled, never handed back.
        let waiting = FieldHistoryAction10868(id: "status.resume", label: "Resume updates", spokenLabel: nil, isAvailable: false)
        let disabled = Self.page(.recorded, status: Self.held(waiting))
        XCTAssertEqual(GolfEventPageModel10868(disabled).statusAction(canAct: true), waiting)
        GolfEventPagePresentation10868(input: disabled, onHistoryAction: { log.append("history:\($0)") }).actOnStatus()

        // An id a history control also hands back, or blank words, draws no action.
        let clash = FieldHistoryAction10868(id: "expand", label: "Resume updates", spokenLabel: nil, isAvailable: true)
        XCTAssertNil(GolfEventPageModel10868(Self.page(.recorded, status: Self.held(clash))).statusAction(canAct: true))
        let blank = FieldHistoryAction10868(id: "status.resume", label: " ", spokenLabel: nil, isAvailable: true)
        XCTAssertNil(GolfEventPageModel10868(Self.page(.recorded, status: Self.held(blank))).statusAction(canAct: true))
        XCTAssertEqual(log, ["history:status.resume", "history:status.pause"])
    }

    // MARK: Arrangement

    func testCompactAndAccessibilitySizesStackAndAWideWidthTriesSideBySideFirst() {
        XCTAssertEqual(GolfEventPageModel10868.arrangements(sizeClass: .compact, accessibilitySize: false), [.stacked])
        XCTAssertEqual(GolfEventPageModel10868.arrangements(sizeClass: .regular, accessibilitySize: false), [.sideBySide, .stacked])
        XCTAssertEqual(GolfEventPageModel10868.arrangements(sizeClass: .regular, accessibilitySize: true), [.stacked])
        XCTAssertEqual(GolfEventPageModel10868.arrangements(sizeClass: .compact, accessibilitySize: true), [.stacked])
    }

    func testAnUnspecifiedSizeClassLikeAMacWindowTriesSideBySideFirstUnlessAccessibilitySized() {
        // A Mac window reports no size class; its width alone (ViewThatFits
        // against the columns' minimum widths) decides, so it is not stacked up front.
        XCTAssertEqual(GolfEventPageModel10868.arrangements(sizeClass: nil, accessibilitySize: false), [.sideBySide, .stacked])
        XCTAssertEqual(GolfEventPageModel10868.arrangements(sizeClass: nil, accessibilitySize: true), [.stacked])
    }

    // MARK: Callbacks

    @MainActor
    func testEveryHostCallbackReachesItsLeafExactlyAndNothingFiresPassively() {
        var log: [String] = []
        let input = Self.page(.before)
        let view = GolfEventPagePresentation10868(
            input: input,
            onAbout: { log.append("about") },
            onOpenCard: { log.append("open:\($0)") },
            onHistoryAction: { log.append("history:\($0)") },
            onHistoryInspectionChoice: { log.append("inspect:\($0)") },
            onHistoryPlotPosition: { log.append("plot:\($0)") },
            onSelectFinish: { log.append("finish:\($0)") },
            onFinishDetails: { log.append("finishDetails:\($0)") },
            onChoose: { log.append("choose:\($0.outcomeID)") },
            onChooserControl: { log.append("control:\($0)") },
            onOpenOriginal: { log.append("original:\($0.outcomeID)") }
        )

        // Building every leaf, in every mode, acts on nothing.
        let anchor = view.historyContent(reader: false)
        let reader = view.historyContent(reader: true)
        let finish = view.finishContent()!
        let contenders = view.contendersContent()!
        let movement = view.movementContent()!
        let chooser = view.chooserContent()!
        _ = GolfEventPagePresentation10868(input: input, mode: .reader(.movement)).movementContent()
        _ = GolfEventPagePresentation10868(input: input, mode: .chooser).chooserContent()
        XCTAssertEqual(log, [])

        anchor.onAction?("more")
        reader.onAction?("details")
        anchor.onInspectionChoice?("c1")
        anchor.onPlotPosition?(Self.laterX)
        finish.onSelectFinish?("64266834")
        finish.onDetails?("64266833")
        contenders.onChoose?(Self.ref(Self.mitchell))
        contenders.onOpenOriginal?(Self.ref(Self.schauffele))
        movement.choose(GolfBeforeMovementModel10868(input.movement!).rows[2])
        chooser.onChoose?(Self.ref(Self.thorbjornsen))
        chooser.onControl?(.toggleMore(id: "more"))
        view.actOnStatus()
        view.open(.movement)
        view.openAbout()

        XCTAssertEqual(log, [
            "history:more", "history:details", "inspect:c1", "plot:\(Self.laterX)",
            "finish:64266834", "finishDetails:64266833",
            "choose:242242559", "original:242242520",
            "choose:241857512",
            "choose:242242545", "control:\(FieldChooserControl10868.toggleMore(id: "more"))",
            "history:status.resume", "open:movement", "about",
        ])

        // Without callbacks every leaf is static and no page control acts.
        let quiet = GolfEventPagePresentation10868(input: input)
        XCTAssertNil(quiet.historyContent(reader: false).onAction)
        XCTAssertNil(quiet.historyContent(reader: true).onInspectionChoice)
        XCTAssertNil(quiet.historyContent(reader: false).onPlotPosition)
        XCTAssertNil(quiet.finishContent()?.onSelectFinish)
        XCTAssertNil(quiet.finishContent()?.onDetails)
        XCTAssertNil(quiet.contendersContent()?.onChoose)
        XCTAssertNil(quiet.contendersContent()?.onOpenOriginal)
        XCTAssertNil(quiet.movementContent()?.onChoose)
        XCTAssertNil(quiet.chooserContent()?.onChoose)
        XCTAssertNil(quiet.chooserContent()?.onControl)
        let model = GolfEventPageModel10868(input)
        for card in GolfEventPageCard10868.allCases {
            XCTAssertNil(model.openAction(card, canOpen: false), "\(card)")
        }
        XCTAssertFalse(model.aboutAvailable(canOpen: false))
        XCTAssertNil(model.statusAction(canAct: false))
        // The anchor opens only through its own expand action, never a page control.
        XCTAssertNil(model.openAction(.history, canOpen: true))

        // Blank or missing open words draw no open control even with a callback.
        var opened: [GolfEventPageCard10868] = []
        let blank = Self.page(.before, openLabels: false)
        let silent = GolfEventPagePresentation10868(input: blank, onOpenCard: { opened.append($0) })
        for card in GolfEventPageCard10868.allCases {
            XCTAssertNil(GolfEventPageModel10868(blank).openAction(card, canOpen: true), "\(card)")
            silent.open(card)
        }
        XCTAssertEqual(opened, [])
    }

    // MARK: Reader and chooser content

    @MainActor
    func testTheFullSizeHistoryDropsOnlyItsExpandControlAndOtherReadersReuseTheirLeaves() {
        var log: [String] = []
        let input = Self.page(.before)
        let view = GolfEventPagePresentation10868(input: input, mode: .reader(.history),
                                                  onHistoryAction: { log.append("history:\($0)") })
        XCTAssertEqual(view.mode, .reader(.history))

        // The page's anchor keeps its expand control; the reader has none and
        // its child layout is the real expanded composition.
        XCTAssertEqual(view.historyContent(reader: false).input.expand?.id, "expand")
        let reader = view.historyContent(reader: true).input
        XCTAssertNil(reader.expand)
        XCTAssertEqual(reader.layout, .expanded)
        XCTAssertEqual(input.history.layout, .cohortAbove)

        // Every other field is the owner's, unchanged — series, selection,
        // readouts, plot height and range, guides, breaks, absence, window,
        // scale and other controls.
        let page = Mirror(reflecting: input.history).children.map { ($0.label ?? "", String(describing: $0.value)) }
        let full = Mirror(reflecting: reader).children.map { ($0.label ?? "", String(describing: $0.value)) }
        XCTAssertEqual(page.map(\.0), full.map(\.0))
        for (owner, shown) in zip(page, full) where owner.0 != "expand" && owner.0 != "layout" {
            XCTAssertEqual(owner.1, shown.1, owner.0)
        }
        XCTAssertEqual(FieldHistoryGeometry10868.actions(reader).map(\.id),
                       FieldHistoryGeometry10868.actions(input.history).map(\.id).filter { $0 != "expand" })

        // The reader's history interactions still reach the host.
        view.historyContent(reader: true).onAction?("details")
        view.historyContent(reader: true).onAction?("choose:\(Self.brennan.outcome)")
        XCTAssertEqual(log, ["history:details", "history:choose:241857512"])

        // The other readers and the chooser are the page's own leaves.
        let model = GolfEventPageModel10868(input)
        for card in GolfEventPageCard10868.allCases {
            XCTAssertTrue(model.readerShows(card), "\(card)")
        }
        XCTAssertEqual(GolfEventPagePresentation10868(input: input, mode: .reader(.finish)).finishContent()?.input, input.finish)
        XCTAssertEqual(GolfEventPagePresentation10868(input: input, mode: .reader(.contenders)).contendersContent()?.input, input.contenders)
        XCTAssertEqual(GolfEventPagePresentation10868(input: input, mode: .reader(.movement)).movementContent()?.input, input.movement)
        let chooser = GolfEventPagePresentation10868(input: input, mode: .chooser).chooserContent()
        XCTAssertEqual(chooser?.input, Self.chooser)
        XCTAssertEqual(chooser?.input.selected?.ref, Self.ref(Self.brennan))

        // No chooser input: no chooser content is invented.
        let none = GolfEventPageInput10868(
            phase: input.phase, copy: input.copy, status: input.status, history: input.history, finish: input.finish,
            finishFrame: input.finishFrame, contenders: input.contenders, contendersFrame: input.contendersFrame,
            movement: input.movement, movementFrame: input.movementFrame, chooser: nil)
        XCTAssertNil(GolfEventPagePresentation10868(input: none, mode: .chooser).chooserContent())
    }
}
