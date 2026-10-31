import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the darts match screen (`darts-match`) as a composition of the
/// accepted leaves plus its dated-endpoint card, before, during and after the
/// match.
///
/// The view is SwiftUI and is not rasterised here. What is asserted is the
/// composition the screen defers to: the phase gates, which leaf mounts with
/// which exact owner input, the dated endpoint rules (placement, absence,
/// identity, actions), the reported legs and their tally, the compact
/// probability context and its Chart, the full-size readers, the hold ordering
/// of every action and the arrangement candidates. Nothing here claims a
/// compile, a rendered fit, a pinned header, a native runtime or VoiceOver.
///
/// ARCHIVED values (retained receipts, read by hand; no fixture loader):
/// - Jim McEwan vs Sander van Ockenburg, MODUS Super Series, Week 11 · Group A
///   · Day 1, October 12, 2026 (`dartsMatch.json`, event capture sha256
///   6a8b6612…8a93). Two separate original winner contracts, one per player.
///   Contract rules: Oct 12, 2026 at 8:50 AM EDT; actual start not
///   independently captured (`scheduledBasis`), so there is NO qualified
///   pre-match baseline and the first captured trade is not pre-match.
/// - Kalshi one-minute candle closes, minute ending (`darts-history.json`,
///   sha256 10088752…97ff): McEwan 72% 8:40, 48% 8:43, 45% 8:44, 27% 8:47,
///   2% 8:49, 1% 8:50; van Ockenburg 40% 8:39, 87% 8:47, 89% 8:48, 98% 8:49,
///   99% 8:50 (all AM EDT). At 8:47 the two independent trades read 27% and
///   87% — 114% together, never normalized. At 8:48 McEwan did not trade while
///   van Ockenburg traded 89%.
/// - Final legs (`dartsFinalScore.json`, Darts World report captured
///   2026-10-13T13:29:25Z, sha256 aee417a0…caf1): McEwan 0, van Ockenburg 4,
///   reported "Sander Van Ockenburg-Zwaan 4-0 Jim McEwan"; actualStart,
///   actualEnd and legTimes null — no leg has a clock.
///
/// CONSTRUCTED: every display string, clock word, label, provenance line,
/// change word, tint, scope, id, action id, About sentence and reader heading;
/// the opaque display identities (scope `darts:constructed:winner`, source
/// token `kalshi`, market tokens `winner.mcewan` / `winner.van-ockenburg`,
/// outcome token `yes`) — never a ticker; the horizontal positions (minutes
/// after 8:39 AM); the owner's runs (consecutive traded minutes); the legs
/// played count (4, the owner's explicit input from the reported 4–0); the
/// contract grades' words. The real retained match proves NEITHER a before
/// NOR a live state: the BEFORE snapshot (8:45 AM, legs not reported) and the
/// DURING snapshot (8:48 AM, "In play") are constructed controls, as are every
/// selected minute, every invalid, foreign-scope, duplicate and colliding case,
/// and the arbitrary-identity page.
@MainActor
final class DartsEventPagePresentation10868Tests: XCTestCase {
    private typealias Originals = OriginalMarketDetails9483
    private typealias Tests = DartsEventPagePresentation10868Tests

    // MARK: Minutes, trades and players

    /// One owner minute: its horizontal position and its own clock words.
    private struct Minute: Equatable {
        let x: Double
        let short: String
        let id: String
        var clock: String { "Oct 12, \(short) EDT" }
    }

    private static let m839 = Minute(x: 0, short: "8:39 AM", id: "0839")
    private static let m840 = Minute(x: 1, short: "8:40 AM", id: "0840")
    private static let m843 = Minute(x: 4, short: "8:43 AM", id: "0843")
    private static let m844 = Minute(x: 5, short: "8:44 AM", id: "0844")
    private static let m847 = Minute(x: 8, short: "8:47 AM", id: "0847")
    private static let m848 = Minute(x: 9, short: "8:48 AM", id: "0848")
    private static let m849 = Minute(x: 10, short: "8:49 AM", id: "0849")
    private static let m850 = Minute(x: 11, short: "8:50 AM", id: "0850")

    /// ARCHIVED close; CONSTRUCTED owner figure.
    private struct Trade {
        let minute: Minute
        let probability: Double
        let figure: String
    }

    private struct Player {
        let token: String
        let market: String
        let name: String
        let compact: String
        let keyShape: FieldHeadlineKeyShape10868
        let shape: FieldHistoryShape10868
        let tint: Color
        let trades: [Trade]
        /// The owner's runs: consecutive traded minutes only.
        let runs: [[Minute]]
        let legsWon: Int
        let grade: String
    }

    private static let mcewan = Player(
        token: "mcewan", market: "winner.mcewan", name: "Jim McEwan", compact: "McEwan",
        keyShape: .circle, shape: .circle, tint: Color(red: 0.0, green: 0.36, blue: 0.75),
        trades: [Trade(minute: m840, probability: 0.72, figure: "72%"),
                 Trade(minute: m843, probability: 0.48, figure: "48%"),
                 Trade(minute: m844, probability: 0.45, figure: "45%"),
                 Trade(minute: m847, probability: 0.27, figure: "27%"),
                 Trade(minute: m849, probability: 0.02, figure: "2%"),
                 Trade(minute: m850, probability: 0.01, figure: "1%")],
        runs: [[m840], [m843, m844], [m847], [m849, m850]],
        legsWon: 0, grade: "Resolved No")

    private static let ockenburg = Player(
        token: "van-ockenburg", market: "winner.van-ockenburg", name: "Sander van Ockenburg", compact: "van Ockenburg",
        keyShape: .diamond, shape: .diamond, tint: Color(red: 0.85, green: 0.33, blue: 0.10),
        trades: [Trade(minute: m839, probability: 0.40, figure: "40%"),
                 Trade(minute: m847, probability: 0.87, figure: "87%"),
                 Trade(minute: m848, probability: 0.89, figure: "89%"),
                 Trade(minute: m849, probability: 0.98, figure: "98%"),
                 Trade(minute: m850, probability: 0.99, figure: "99%")],
        runs: [[m839], [m847, m848, m849, m850]],
        legsWon: 4, grade: "Resolved Yes")

    private static let players = [mcewan, ockenburg]

    private static let scope = "darts:constructed:winner"
    private static let noPreMatch = "Pre-match chance unavailable"
    private static let provenance = "Kalshi trade · minute ending"

    private static func ref(_ player: Player, scope: String = Tests.scope) -> FieldChooserOriginalRef10868 {
        FieldChooserOriginalRef10868(scope: scope, source: "kalshi", marketID: player.market, outcomeID: "yes")
    }

    private static func trade(_ player: Player, at minute: Minute) -> Trade? {
        player.trades.first { $0.minute == minute }
    }

    private static func lastTrade(_ player: Player, through cutoff: Minute) -> Trade? {
        player.trades.filter { $0.minute.x <= cutoff.x }.last
    }

    private static func pointID(_ player: Player, _ minute: Minute) -> String { "\(player.token).\(minute.id)" }

    private static func cutoff(_ phase: DartsEventPagePhase10868) -> Minute {
        switch phase {
        case .before: m844
        case .during: m848
        case .final: m850
        }
    }

    // MARK: Headline

    private static let preMatchMissing = FieldChooserReading10868(label: "Pre-match", value: .missing(noPreMatch))

    private static func recordedReading(_ trade: Trade) -> FieldChooserReading10868 {
        FieldChooserReading10868(label: "Last recorded trade",
                                 value: .recorded(text: trade.figure, detail: "\(trade.minute.clock) · Kalshi trade"))
    }

    private static func legsReading(_ player: Player) -> FieldChooserReading10868 {
        FieldChooserReading10868(label: "Final legs", value: .recorded(text: "\(player.legsWon)", detail: "Darts World report · Oct 12"))
    }

    private static func state(_ phase: DartsEventPagePhase10868) -> FieldHeadlineState10868 {
        switch phase {
        case .before:
            return FieldHeadlineState10868(figure: "Not started", unit: nil, caption: "Contract rules: 8:50 AM EDT",
                                           detail: "Actual start not captured",
                                           spoken: "Not started. Contract rules say 8:50 AM EDT. Actual start not captured.",
                                           progress: nil)
        case .during:
            return FieldHeadlineState10868(figure: "In play", unit: nil, caption: "Legs not reported", detail: nil,
                                           spoken: "In play. Legs not reported.", progress: nil)
        case .final:
            return FieldHeadlineState10868(figure: "Final", unit: nil, caption: "McEwan 0–4 van Ockenburg in legs",
                                           detail: "Reported by Darts World",
                                           spoken: "Final. McEwan 0, van Ockenburg 4, in legs. Reported by Darts World.",
                                           progress: nil)
        }
    }

    private static func catalogue(_ phase: DartsEventPagePhase10868, players: [Player] = Tests.players,
                                  scope: String = Tests.scope) -> [FieldChooserOriginal10868] {
        players.map { player in
            let plan: FieldChooserDisplayPlan10868
            if phase == .during, let last = lastTrade(player, through: cutoff(.during)) {
                plan = .comparison(before: preMatchMissing, later: recordedReading(last))
            } else {
                plan = .single(preMatchMissing)
            }
            return FieldChooserOriginal10868(
                ref: ref(player, scope: scope), name: player.name, plan: plan,
                preview: FieldChooserPreview10868(history: nil, absence: "History in the chart"),
                movement: nil, clock: nil, result: nil, browseStatus: "Recorded trades", accent: player.tint)
        }
    }

    private static func headline(_ phase: DartsEventPagePhase10868,
                                 headlinePhase: FieldOutlookPhase10868? = nil) -> FieldHeadlineInput10868 {
        FieldHeadlineInput10868(
            scope: scope,
            catalogue: catalogue(phase),
            displayed: players.map {
                FieldHeadlineSlot10868(ref: ref($0), name: $0.name, compactName: $0.compact, keyShape: $0.keyShape)
            },
            pairs: players.map { player in
                let later = phase == .during ? lastTrade(player, through: cutoff(.during)) : nil
                return FieldMovementPair10868(
                    ref: ref(player), before: nil,
                    later: later.map { FieldMovementObservation10868(probability: $0.probability, reading: recordedReading($0)) },
                    movement: nil, observation: later.map { pointID(player, $0.minute) })
            },
            finishes: players.map { FieldFinishPlace10868(ref: ref($0), reading: legsReading($0)) },
            state: state(phase),
            phase: headlinePhase ?? DartsEventPageModel10868.headlinePhase(phase),
            copy: FieldHeadlineCopy10868(
                eyebrow: "MODUS Super Series · Week 11 · Group A", title: "Jim McEwan · Sander van Ockenburg",
                graphicLabel: "Match win chances", beforeLabel: "Pre-match", recordedLabel: "Last recorded trade",
                beforeUnavailable: noPreMatch, recordedUnavailable: "No recorded trade",
                finishLabel: "Final legs", finishUnavailable: "Final legs not reported",
                empty: "No players in this update", aboutLabel: "About this match",
                aboutHint: "Opens timing, the reported legs and sources",
                openHint: "Opens this player’s history"),
            unavailableWords: "Player unavailable in this update",
            keyTreatment: .neutralRecorded)
    }

    private static func figures(_ input: FieldHeadlineInput10868) -> [[String]] {
        FieldHeadlineModel10868(input).competitors.map { $0.metrics.compactMap(FieldChaseModel10868.figure) }
    }

    private static func words(_ input: FieldHeadlineInput10868) -> [[String]] {
        FieldHeadlineModel10868(input).competitors.map { $0.metrics.compactMap(FieldChaseModel10868.words) }
    }

    // MARK: History

    private static func action(_ id: String, _ label: String, spoken: String? = nil,
                               available: Bool = true) -> FieldHistoryAction10868 {
        FieldHistoryAction10868(id: id, label: label, spokenLabel: spoken, isAvailable: available)
    }

    private static func point(_ player: Player, _ trade: Trade) -> FieldHistoryPoint10868 {
        FieldHistoryPoint10868(id: pointID(player, trade.minute), x: trade.minute.x, probability: trade.probability, style: .filled)
    }

    private static func runs(_ player: Player, through cutoff: Minute) -> [FieldHistoryRun10868] {
        player.runs.compactMap { minutes in
            let points = minutes.filter { $0.x <= cutoff.x }.compactMap { trade(player, at: $0) }.map { point(player, $0) }
            return points.isEmpty ? nil : FieldHistoryRun10868(id: "run.\(player.token).\(minutes[0].id)", points: points)
        }
    }

    /// `selected`: the owner's held minute. Each original's reading there is
    /// its own trade or its own absence words — never a neighbour's.
    private static func history(_ phase: DartsEventPagePhase10868, selected: Minute? = nil,
                                players: [Player] = Tests.players) -> FieldHistoryInput10868 {
        let cutoff = Self.cutoff(phase)
        let series = players.map { player -> FieldHistorySeries10868 in
            let last = lastTrade(player, through: cutoff)
            let shown = selected.flatMap { trade(player, at: $0) } ?? last
            return FieldHistorySeries10868(
                id: player.token, name: player.name, shape: player.shape, tint: player.tint,
                runs: runs(player, through: cutoff), links: [], labelPointID: last.map { pointID(player, $0.minute) },
                before: .absent(words: noPreMatch),
                recorded: shown.map {
                    FieldHistoryReading10868.observation(pointID: pointID(player, $0.minute), figure: $0.figure,
                                                         provenance: "\($0.minute.clock) · Kalshi trade")
                } ?? FieldHistoryReading10868.absent(words: "No recorded trade"),
                absentWords: "No recorded trades in this update", choose: nil)
        }
        let readout: FieldHistoryReadoutIntent10868
        if phase == .before {
            readout = .singleBefore(label: "Pre-match")
        } else if selected != nil {
            readout = .beforeAndInspected(beforeLabel: "Pre-match", inspectedLabel: "Selected minute")
        } else {
            readout = .beforeAndRecorded(beforeLabel: "Pre-match", recordedLabel: "Last recorded trade")
        }
        var selections: [String: FieldHistorySelection10868] = [:]
        if let selected {
            for player in players {
                if let traded = trade(player, at: selected) {
                    selections[player.token] = FieldHistorySelection10868.point(id: pointID(player, selected), spoken: traded.figure)
                } else {
                    selections[player.token] = FieldHistorySelection10868.absent(words: "Not traded at \(selected.short)")
                }
            }
        }
        return FieldHistoryInput10868(
            title: "Win probability", caption: "Recorded Kalshi trades · times in EDT",
            series: series, selection: .none,
            domain: FieldHistoryDomain10868(lower: 0, upper: cutoff.x), ceiling: 1,
            yTicks: [FieldHistoryTick10868(value: 0, lines: ["0%"]), FieldHistoryTick10868(value: 0.5, lines: ["50%"]),
                     FieldHistoryTick10868(value: 1, lines: ["100%"])],
            xTicks: [FieldHistoryTick10868(value: 0, lines: ["8:39 AM"]), FieldHistoryTick10868(value: cutoff.x, lines: [cutoff.short])],
            guides: [], breaks: [], readout: readout,
            markKey: FieldHistoryMarkKey10868(hollow: nil, filled: "Filled: a recorded trade, minute ending"),
            comparisonExplanation: nil,
            notes: ["Each player’s contract trades on its own; the two chances need not add to 100%."],
            summary: "Each player’s recorded win chance on a zero to 100% scale. Minutes without a trade stay blank.",
            plotHeight: 220, unboundReadingWords: "Unavailable", plotUnavailableWords: "History unavailable",
            windows: nil, scale: nil, moreOriginals: nil, details: nil,
            expand: action("history.expand", "Expand", spoken: "Open darts win probability"),
            inspect: nil,
            previous: action("history.previous", "‹", spoken: "Previous recorded minute"),
            next: action("history.next", "›", spoken: "Next recorded minute"),
            inspection: selected.map {
                FieldHistoryInspection10868(x: $0.x, caption: "Selected minute · \($0.clock)", selections: selections,
                                            choices: [], choicePresentation: .slider(label: "Recorded minute"), note: nil)
            })
    }

    // MARK: Dated endpoints

    private static func endpoint(_ player: Player, _ trade: Trade, label: String) -> DartsDatedEndpoint10868 {
        DartsDatedEndpoint10868(key: "\(player.token).\(trade.minute.id)", label: label, probability: trade.probability,
                                figure: trade.figure, clock: trade.minute.clock, provenance: provenance)
    }

    private static let changes: [String: String] = [
        "mcewan.0847": "−45 pts", "van-ockenburg.0847": "+47 pts", "van-ockenburg.0848": "+49 pts",
    ]

    private static let endpointsCopy = DartsEndpointsCopy10868(
        eyebrow: "Recorded win chances", title: "What changed?", baseline: noPreMatch,
        scaleLower: "0%", scaleLabel: "Win chance", scaleUpper: "100%",
        graphicLabel: "Earlier and later recorded win chances",
        markKey: "Hollow: earlier trade. Filled: later trade. These dated endpoints don’t describe every moment between them.",
        endpointUnavailable: "Unavailable", unavailableWords: "Player unavailable in this update",
        noComparison: "No comparison is available at this selected minute.", selectedWords: nil,
        sourcesLabel: "Comparison & sources", expandLabel: "Expand darts probability movement")

    private static func row(_ player: Player, later minute: Minute, scope: String = Tests.scope) -> DartsEndpointRow10868 {
        let first = player.trades[0]
        let later = trade(player, at: minute)
        return DartsEndpointRow10868(
            ref: ref(player, scope: scope), name: player.name,
            earlier: .endpoint(endpoint(player, first, label: "First captured trade")),
            later: later.map { DartsEndpointSlot10868.endpoint(endpoint(player, $0, label: "Selected minute")) }
                ?? DartsEndpointSlot10868.absent(label: "Selected minute", words: "Not traded at \(minute.short)"),
            change: later == nil ? nil : changes["\(player.token).\(minute.id)"],
            shape: player.shape, tint: player.tint)
    }

    private static let openEarlier = action("movement.earlier", "Earlier in chart", spoken: "Show the earlier trades in the chart")
    private static let openLater = action("movement.later", "Later in chart", spoken: "Show the later trades in the chart")

    private static func movement(later minute: Minute = Tests.m847,
                                 rows: [DartsEndpointRow10868]? = nil,
                                 catalogue: [FieldChooserOriginal10868]? = nil,
                                 openEarlier: FieldHistoryAction10868? = Tests.openEarlier,
                                 openLater: FieldHistoryAction10868? = Tests.openLater) -> DartsEndpointsInput10868 {
        DartsEndpointsInput10868(
            scope: scope, catalogue: catalogue ?? Tests.catalogue(.final),
            rows: rows ?? players.map { row($0, later: minute) },
            openEarlier: openEarlier, openLater: openLater, copy: endpointsCopy)
    }

    // MARK: Legs

    private static func legs(played: Int? = 4, players: [Player] = Tests.players,
                             scope: String = Tests.scope) -> DartsLegsInput10868 {
        let playedWords = played.map { "\($0)" } ?? "an unreported number of"
        return DartsLegsInput10868(
            label: "Legs won", played: played,
            scores: players.map {
                DartsLegScore10868(ref: ref($0, scope: scope), name: $0.name, won: $0.legsWon, figure: "\($0.legsWon)",
                                   spoken: "\($0.name): \($0.legsWon) legs won, of \(playedWords) played")
            },
            summary: "Final · McEwan 0–4 van Ockenburg",
            provenance: "Reported by Darts World · captured Oct 13",
            markKey: "Filled marks: legs won, out of legs played")
    }

    // MARK: Page

    private static let dartsWorld = DartsEventPageSource10868(
        id: "darts-world", label: "Darts World report",
        url: URL(string: "https://dartsworld.com/2026/10/morris-grabs-early-super-series-lead/")!)

    private static let about = DartsEventPageAbout10868(
        title: "About this match",
        sections: [
            DartsEventPageAboutSection10868(
                title: "Timing",
                paragraphs: ["Both original Kalshi contract rules: Oct 12, 2026 at 8:50 AM EDT. Actual start not independently captured."]),
            DartsEventPageAboutSection10868(
                title: "Final legs",
                paragraphs: ["Sander Van Ockenburg-Zwaan 4-0 Jim McEwan, as reported by Darts World."],
                source: dartsWorld),
        ])

    private static func copy(_ phase: DartsEventPagePhase10868) -> DartsEventPageCopy10868 {
        DartsEventPageCopy10868(
            storiesLabel: "Darts match stories",
            headlineUnavailable: "Match chances unavailable in this update",
            legsUnavailable: "Final legs not reported",
            unavailableWords: "Player unavailable in this update",
            // Before the match each player's own slot already says it.
            context: DartsContextCopy10868(label: "Darts probability context", chartLabel: "Chart",
                                           chartSpokenLabel: "Open darts win probability",
                                           baseline: phase == .before ? nil : noPreMatch))
    }

    private static func reader(_ phase: DartsEventPagePhase10868) -> DartsEventPageReaderHeader10868 {
        switch phase {
        case .before: DartsEventPageReaderHeader10868(title: "McEwan vs van Ockenburg", state: "Not started · Pre-match unavailable")
        case .during: DartsEventPageReaderHeader10868(title: "McEwan vs van Ockenburg", state: "In play · Legs not reported")
        case .final: DartsEventPageReaderHeader10868(title: "McEwan vs van Ockenburg",
                                                     state: "Final · McEwan 0–4 van Ockenburg · Pre-match unavailable")
        }
    }

    /// Every phase carries a movement and legs input, so each phase gate is
    /// what hides them — never their absence.
    private static func page(_ phase: DartsEventPagePhase10868, selected: Minute? = nil,
                             headlinePhase: FieldOutlookPhase10868? = nil,
                             movement: DartsEndpointsInput10868? = Tests.movement(),
                             legs: DartsLegsInput10868? = Tests.legs()) -> DartsEventPageInput10868 {
        DartsEventPageInput10868(
            phase: phase, reader: reader(phase),
            headline: headline(phase, headlinePhase: headlinePhase),
            history: history(phase, selected: selected),
            movement: movement, legs: legs, about: about, copy: copy(phase))
    }

    // MARK: Originals

    private static let originalsScope = "darts:constructed:originals"

    private static func identity(_ player: Player) -> Originals.Identity {
        Originals.Identity(source: "kalshi", market: player.market, side: "yes")
    }

    private static func originals(_ phase: DartsEventPagePhase10868, scope: String = Tests.originalsScope,
                                  duplicate: Bool = false) -> DartsEventPageOriginals10868 {
        var records = players.map { player -> Originals.Original in
            let last = lastTrade(player, through: cutoff(.during))
            let mode: Originals.Mode
            switch phase {
            case .before: mode = .pregame
            case .during: mode = .comparison(.recorded)
            case .final: mode = .result
            }
            return Originals.Original(
                identity: identity(player), title: "Jim McEwan vs Sander van Ockenburg", outcome: player.name,
                mode: mode, pregame: .missing(noPreMatch),
                later: phase == .during
                    ? last.map { Originals.Reading.value($0.figure, placement: $0.probability,
                                                         provenance: "\($0.minute.clock) · Kalshi trade") }
                    : nil,
                grade: phase == .final ? Originals.Grade(words: player.grade, provenance: "Kalshi settlement") : nil,
                about: Originals.About(source: "Kalshi", rules: .omitted,
                                       provenance: [Originals.Row(label: "Contract", value: player.market)],
                                       historicalQuote: nil))
        }
        if duplicate { records.append(records[0]) }
        return DartsEventPageOriginals10868(
            catalogue: Originals.Catalogue(scope: originalsScope, originals: records),
            selection: Originals.Selection(scope: scope, identity: identity(mcewan)),
            labels: [identity(mcewan): "Jim McEwan · Winner", identity(ockenburg): "Sander van Ockenburg · Winner"],
            heading: "Original contracts", context: "Both captured winner contracts",
            emptyWords: "No original contracts for this match", unavailableChoice: "Unnamed original",
            tint: mcewan.tint)
    }

    // MARK: - Phases

    func testBeforeTheMatchShowsOnlyThePreMatchAbsenceTheHistoryAndTheOriginals() {
        let input = Self.page(.before)
        let model = DartsEventPageModel10868(input)

        // The headline at its own phase: each player's explicit pre-match
        // absence, no recorded or final reading, and neutral recorded keys
        // because no qualified start exists.
        XCTAssertEqual(model.headline, input.headline)
        XCTAssertEqual(Self.figures(input.headline), [[], []])
        XCTAssertEqual(Self.words(input.headline), [[Self.noPreMatch], [Self.noPreMatch]])
        XCTAssertFalse(FieldHeadlineModel10868(input.headline).keyIsHollow)
        let spoken = FieldHeadlineModel10868(input.headline).competitors.map {
            FieldHeadlineModel10868(input.headline).competitorSummary($0)
        }
        XCTAssertEqual(spoken, ["Pre-match: Pre-match chance unavailable", "Pre-match: Pre-match chance unavailable"])

        // The owner supplied movement and legs; the before gate hides both.
        XCTAssertNotNil(input.movement)
        XCTAssertNotNil(input.legs)
        XCTAssertNil(model.movement)
        XCTAssertNil(model.legs)
        XCTAssertNil(model.legsUnavailable)
        XCTAssertEqual(model.legRows, [])
        XCTAssertFalse(model.isMounted(.movement))
        XCTAssertFalse(model.readerShows(.movement))
        XCTAssertTrue(model.isMounted(.history))
        let view = DartsEventPagePresentation10868(input: input)
        XCTAssertNil(view.movementContent(reader: false))
        XCTAssertNil(view.legsContent())
        XCTAssertNil(DartsEventPagePresentation10868(input: input, mode: .reader(.movement)).movementContent(reader: true))

        // The history holds only what was recorded by 8:45: nothing later.
        XCTAssertEqual(input.history.series.flatMap { $0.runs.flatMap(\.points) }.map(\.x).max(), 5)
        // The compact context: each player's own pre-match words, no legs, no figure.
        XCTAssertEqual(model.contextReadings.map(\.slot), [
            FieldHistoryReadoutSlot10868(label: "Pre-match", display: .words(Self.noPreMatch)),
            FieldHistoryReadoutSlot10868(label: "Pre-match", display: .words(Self.noPreMatch)),
        ])
        XCTAssertEqual(model.contextFooter, [])
        XCTAssertFalse(model.contextSummary.contains("legs"))
        XCTAssertFalse(model.contextSummary.contains("Final"))

        // Originals before the match: pre-match reading only, no grade.
        let originals = Self.originals(.before)
        let content = Originals.content(catalogue: originals.catalogue, selection: originals.selection)
        XCTAssertNotNil(content)
        XCTAssertNil(content?.result)
    }

    func testDuringTheMatchEachPlayerKeepsItsOwnLastTradeAndClockAndNoLegsAppear() {
        let input = Self.page(.during)
        let model = DartsEventPageModel10868(input)

        // Each player's own last recorded trade, with its own clock — never
        // upgraded to a current chance and never a shared minute.
        XCTAssertEqual(Self.figures(input.headline), [["27%"], ["89%"]])
        XCTAssertEqual(Self.words(input.headline), [[Self.noPreMatch], [Self.noPreMatch]])
        let headline = FieldHeadlineModel10868(input.headline)
        XCTAssertEqual(headline.competitors.map { headline.competitorSummary($0) }, [
            "Pre-match: Pre-match chance unavailable. Last recorded trade: 27%, Oct 12, 8:47 AM EDT · Kalshi trade",
            "Pre-match: Pre-match chance unavailable. Last recorded trade: 89%, Oct 12, 8:48 AM EDT · Kalshi trade",
        ])
        XCTAssertEqual(headline.stateSummary, "In play. Legs not reported.")

        // The movement card applies; the supplied legs stay hidden.
        XCTAssertEqual(model.movement, input.movement)
        XCTAssertTrue(model.isMounted(.movement))
        XCTAssertNil(model.legs)
        XCTAssertNil(model.legsUnavailable)
        XCTAssertNil(DartsEventPagePresentation10868(input: input).legsContent())
        XCTAssertFalse(model.contextFooter.contains("Final · McEwan 0–4 van Ockenburg"))

        // The compact context shows the same independent clocks.
        XCTAssertEqual(model.contextReadings.map(\.slot), [
            FieldHistoryReadoutSlot10868(label: "Last recorded trade",
                                         display: .figure("27%", provenance: "Oct 12, 8:47 AM EDT · Kalshi trade")),
            FieldHistoryReadoutSlot10868(label: "Last recorded trade",
                                         display: .figure("89%", provenance: "Oct 12, 8:48 AM EDT · Kalshi trade")),
        ])
        // No point after the 8:48 snapshot.
        XCTAssertEqual(input.history.series.flatMap { $0.runs.flatMap(\.points) }.map(\.x).max(), 9)
    }

    func testAtTheFinalTheReportedLegsStandApartFromEachContractsResultAndThePreMatchAbsence() {
        let input = Self.page(.final)
        let model = DartsEventPageModel10868(input)

        // The headline: the pre-match absence beside the reported legs.
        XCTAssertEqual(Self.figures(input.headline), [["0"], ["4"]])
        XCTAssertEqual(Self.words(input.headline), [[Self.noPreMatch], [Self.noPreMatch]])
        let headline = FieldHeadlineModel10868(input.headline)
        XCTAssertEqual(headline.competitors.map { headline.competitorSummary($0) }, [
            "Pre-match: Pre-match chance unavailable. Final legs: 0, Darts World report · Oct 12",
            "Pre-match: Pre-match chance unavailable. Final legs: 4, Darts World report · Oct 12",
        ])

        // The legs: each player's reported count, as tally marks out of the
        // owner's legs played.
        XCTAssertEqual(model.legs, input.legs)
        XCTAssertEqual(model.legRows.map(\.name), ["Jim McEwan", "Sander van Ockenburg"])
        XCTAssertEqual(model.legRows.map(\.resolved), [true, true])
        XCTAssertEqual(model.legRows.map(\.score.figure), ["0", "4"])
        XCTAssertEqual(model.legRows.map(\.marks), [[false, false, false, false], [true, true, true, true]])
        XCTAssertEqual(model.legRows.map(\.score.spoken), ["Jim McEwan: 0 legs won, of 4 played",
                                                           "Sander van Ockenburg: 4 legs won, of 4 played"])
        XCTAssertNil(model.legsUnavailable)
        XCTAssertEqual(model.contextFooter, [Self.noPreMatch, "Final · McEwan 0–4 van Ockenburg"])

        // Each original contract's own result stays in its Details, its own
        // words and settlement provenance — not the legs.
        let originals = Self.originals(.final)
        let results = [Self.mcewan, Self.ockenburg].map { player in
            Originals.content(catalogue: originals.catalogue,
                              selection: Originals.Selection(scope: Self.originalsScope, identity: Self.identity(player)))?.result
        }
        XCTAssertEqual(results.map { $0?.words }, ["Resolved No", "Resolved Yes"])
        XCTAssertEqual(results.map { $0?.provenance }, ["Kalshi settlement", "Kalshi settlement"])
        XCTAssertFalse(model.legRows.contains { $0.score.figure.contains("Resolved") })

        // No legs reported at the final: the owner's words, never a zero.
        let unreported = DartsEventPageModel10868(Self.page(.final, legs: nil))
        XCTAssertNil(unreported.legs)
        XCTAssertEqual(unreported.legsUnavailable, "Final legs not reported")
        XCTAssertEqual(unreported.legRows, [])
        XCTAssertEqual(unreported.contextFooter, [Self.noPreMatch])
    }

    func testAHeadlineFromAnotherPhaseIsNotMountedAndTheOwnersWordsStand() {
        let input = Self.page(.final, headlinePhase: .during)
        let model = DartsEventPageModel10868(input)
        XCTAssertNil(model.headline)
        XCTAssertNil(DartsEventPagePresentation10868(input: input).headlineContent())
        XCTAssertEqual(input.copy.headlineUnavailable, "Match chances unavailable in this update")
        // The rest of the final still stands on its own inputs.
        XCTAssertEqual(model.legRows.map(\.score.figure), ["0", "4"])
        XCTAssertNotNil(model.movement)
    }

    // MARK: - Owner identities

    func testArbitraryOwnerIdentitiesAndLabelsDriveThePageWithNoBuiltInPlayers() {
        let alphaMinute = Minute(x: 0, short: "6:00 PM", id: "1800")
        let laterMinute = Minute(x: 3, short: "6:03 PM", id: "1803")
        let alpha = Player(
            token: "alpha", market: "constructed.alpha", name: "Ana Arbitrary", compact: "Arbitrary",
            keyShape: .square, shape: .square, tint: .purple,
            trades: [Trade(minute: alphaMinute, probability: 0.61, figure: "61%"),
                     Trade(minute: laterMinute, probability: 0.55, figure: "55%")],
            runs: [[alphaMinute], [laterMinute]], legsWon: 3, grade: "Graded Yes")
        let zed = Player(
            token: "zed", market: "constructed.zed", name: "Zed Otherwise", compact: "Otherwise",
            keyShape: .circle, shape: .triangle, tint: .green,
            trades: [Trade(minute: alphaMinute, probability: 0.44, figure: "44%")],
            runs: [[alphaMinute]], legsWon: 7, grade: "Graded No")
        let scope = "constructed:any-sport:any-match"

        // An owner that admits qualified pre-match chances: the before
        // headline shows them with the phase's hollow key.
        let preMatch = [alpha.token: alpha.trades[0], zed.token: zed.trades[0]]
        let headline = FieldHeadlineInput10868(
            scope: scope,
            catalogue: [alpha, zed].map { player in
                FieldChooserOriginal10868(
                    ref: Self.ref(player, scope: scope), name: player.name,
                    plan: .single(FieldChooserReading10868(label: "Qualified start",
                                                           value: .recorded(text: preMatch[player.token]!.figure, detail: "Verified 6:00 PM"))),
                    preview: FieldChooserPreview10868(history: nil, absence: "History in the chart"),
                    movement: nil, clock: "Verified 6:00 PM", result: nil, browseStatus: "Qualified", accent: player.tint)
            },
            displayed: [alpha, zed].map {
                FieldHeadlineSlot10868(ref: Self.ref($0, scope: scope), name: $0.name, compactName: $0.compact, keyShape: $0.keyShape)
            },
            pairs: [alpha, zed].map { player in
                FieldMovementPair10868(
                    ref: Self.ref(player, scope: scope),
                    before: FieldMovementObservation10868(
                        probability: preMatch[player.token]!.probability,
                        reading: FieldChooserReading10868(label: "Qualified start",
                                                          value: .recorded(text: preMatch[player.token]!.figure, detail: "Verified 6:00 PM"))),
                    later: nil, movement: nil, observation: nil)
            },
            finishes: [], state: nil, phase: .before,
            copy: FieldHeadlineCopy10868(
                eyebrow: nil, title: "Any match", graphicLabel: "Chances", beforeLabel: "Qualified start",
                recordedLabel: "Recorded", beforeUnavailable: "None", recordedUnavailable: "None",
                finishLabel: "Result", finishUnavailable: "None", empty: "Nobody", aboutLabel: "About",
                aboutHint: nil, openHint: nil),
            unavailableWords: "Not here")
        XCTAssertEqual(Self.figures(headline), [["61%"], ["44%"]])
        XCTAssertTrue(FieldHeadlineModel10868(headline).keyIsHollow)

        let before = DartsEventPageInput10868(
            phase: .before, reader: DartsEventPageReaderHeader10868(title: "Arbitrary vs Otherwise", state: nil),
            headline: headline, history: Self.history(.final, players: [alpha, zed]),
            movement: nil, legs: nil, about: nil, copy: Self.copy(.before))
        let beforeModel = DartsEventPageModel10868(before)
        XCTAssertEqual(beforeModel.headline, headline)
        XCTAssertEqual(beforeModel.contextReadings.map(\.name), ["Ana Arbitrary", "Zed Otherwise"])
        XCTAssertEqual(beforeModel.contextReadings.map(\.shape), [.square, .triangle])

        // The final with arbitrary identities: legs out of the owner's own 10
        // played, endpoint rows resolved by the owner's own scope.
        let catalogue = headline.catalogue
        let rows = [alpha, zed].map { player in
            DartsEndpointRow10868(
                ref: Self.ref(player, scope: scope), name: player.name,
                earlier: .endpoint(DartsDatedEndpoint10868(key: "\(player.token).early", label: "Opening read", probability: player.trades[0].probability,
                                                           figure: player.trades[0].figure, clock: "6:00 PM", provenance: nil)),
                later: .endpoint(DartsDatedEndpoint10868(key: "\(player.token).late", label: "Closing read", probability: 0.5,
                                                         figure: "50%", clock: "6:30 PM", provenance: nil)),
                change: "owner words", shape: player.shape, tint: player.tint)
        }
        let endpoints = DartsEndpointsModel10868(DartsEndpointsInput10868(
            scope: scope, catalogue: catalogue, rows: rows, openEarlier: nil, openLater: nil, copy: Self.endpointsCopy))
        XCTAssertEqual(endpoints.rows.map(\.name), ["Ana Arbitrary", "Zed Otherwise"])
        XCTAssertEqual(endpoints.rows.map(\.isComparison), [true, true])
        XCTAssertEqual(endpoints.rows.map { $0.earlier?.label }, ["Opening read", "Opening read"])
        XCTAssertEqual(endpoints.rows.map { endpoints.change($0) }, ["owner words", "owner words"])

        var legsInput = Self.legs(played: 10, players: [alpha, zed], scope: scope)
        legsInput = DartsLegsInput10868(label: "Frames won", played: legsInput.played, scores: legsInput.scores,
                                        summary: "Final · 3–7", provenance: "Owner report", markKey: nil)
        let final = DartsEventPageInput10868(
            phase: .final, reader: DartsEventPageReaderHeader10868(title: "Arbitrary vs Otherwise", state: "Final"),
            headline: FieldHeadlineInput10868(scope: scope, catalogue: catalogue, displayed: headline.displayed, pairs: [],
                                              finishes: [], state: nil, phase: .final, copy: headline.copy,
                                              unavailableWords: "Not here"),
            history: Self.history(.final, players: [alpha, zed]),
            movement: nil, legs: legsInput, about: nil, copy: Self.copy(.final))
        let finalModel = DartsEventPageModel10868(final)
        XCTAssertEqual(finalModel.legRows.map(\.name), ["Ana Arbitrary", "Zed Otherwise"])
        XCTAssertEqual(finalModel.legRows.map { $0.marks?.count }, [10, 10])
        XCTAssertEqual(finalModel.legRows.map { $0.marks?.filter { $0 }.count }, [3, 7])
        XCTAssertEqual(finalModel.contextFooter, [Self.noPreMatch, "Final · 3–7"])
    }

    // MARK: - Independent chances

    func testTwoIndependentlyTradedChancesAreNeverNormalized() {
        let input = Self.page(.final, selected: Self.m847)
        let model = DartsEventPageModel10868(input)

        // 27% and 87% at one minute: 114% together, shown as traded.
        XCTAssertEqual(model.contextReadings.map(\.slot?.display), [
            .figure("27%", provenance: "Oct 12, 8:47 AM EDT · Kalshi trade"),
            .figure("87%", provenance: "Oct 12, 8:47 AM EDT · Kalshi trade"),
        ])
        let endpoints = DartsEndpointsModel10868(input.movement!)
        let later = endpoints.rows.compactMap { $0.later?.fraction }
        XCTAssertEqual(later, [0.27, 0.87])
        XCTAssertEqual(later.reduce(0, +), 1.14, accuracy: 1e-9)
        XCTAssertEqual(endpoints.rows.map { DartsEndpointGeometry10868.marks($0) }, [
            [DartsEndpointMark10868(fraction: 0.72, hollow: true), DartsEndpointMark10868(fraction: 0.27, hollow: false)],
            [DartsEndpointMark10868(fraction: 0.40, hollow: true), DartsEndpointMark10868(fraction: 0.87, hollow: false)],
        ])
        // The history points carry the archived closes unchanged.
        XCTAssertEqual(input.history.series.map { series in
            series.runs.flatMap(\.points).first { $0.x == Self.m847.x }?.probability
        }, [0.27, 0.87])
    }

    func testASelectedMinuteWithoutATradeKeepsItsOwnWordsAndTheNeighbourKeepsItsFigure() {
        let input = Self.page(.final, selected: Self.m848, movement: Self.movement(later: Self.m848))
        let model = DartsEventPageModel10868(input)

        // The context reads exactly the chart's own readout for the held minute.
        let expected = [
            FieldHistoryReadoutSlot10868(label: "Selected minute", display: .words("Not traded at 8:48 AM")),
            FieldHistoryReadoutSlot10868(label: "Selected minute",
                                         display: .figure("89%", provenance: "Oct 12, 8:48 AM EDT · Kalshi trade")),
        ]
        XCTAssertEqual(model.contextReadings.map(\.slot), expected)
        XCTAssertEqual(input.history.series.map { FieldHistoryGeometry10868.readoutSlots($0, in: input.history).last }, expected)
        XCTAssertEqual(model.contextCaption, "Selected minute · Oct 12, 8:48 AM EDT")

        // The endpoint card: McEwan keeps its earlier trade and its own
        // absence words; van Ockenburg keeps its comparison.
        let endpoints = DartsEndpointsModel10868(input.movement!)
        let rows = endpoints.rows
        XCTAssertEqual(rows[0].earlier?.fraction, 0.72)
        XCTAssertEqual(rows[0].later, .words(label: "Selected minute", words: "Not traded at 8:48 AM"))
        XCTAssertFalse(rows[0].isComparison)
        XCTAssertNil(endpoints.change(rows[0]))
        XCTAssertEqual(DartsEndpointGeometry10868.marks(rows[0]), [DartsEndpointMark10868(fraction: 0.72, hollow: true)])
        XCTAssertNil(DartsEndpointGeometry10868.span(rows[0]))
        XCTAssertEqual(rows[1].later?.fraction, 0.89)
        XCTAssertTrue(rows[1].isComparison)
        XCTAssertEqual(endpoints.change(rows[1]), "+49 pts")
        XCTAssertTrue(endpoints.hasComparison)
        XCTAssertEqual(endpoints.openState(Self.openEarlier, hasCallback: true), .live(id: "movement.earlier"))
    }

    func testTheEarlierEndpointKeepsItsFirstTradeLabelAndNeverBecomesAPreMatchBaseline() {
        let input = Self.page(.final)
        let endpoints = DartsEndpointsModel10868(input.movement!)
        // Each player's first captured trade, with its own clock.
        XCTAssertEqual(endpoints.rows.map { $0.earlier?.label }, ["First captured trade", "First captured trade"])
        guard case .figure(let mcewanFirst, _)? = endpoints.rows[0].earlier,
              case .figure(let ockenburgFirst, _)? = endpoints.rows[1].earlier else {
            return XCTFail("both earlier endpoints are drawn")
        }
        XCTAssertEqual(mcewanFirst.clock, "Oct 12, 8:40 AM EDT")
        XCTAssertEqual(ockenburgFirst.clock, "Oct 12, 8:39 AM EDT")
        // The pre-match words are the owner's own, separate from any endpoint.
        XCTAssertEqual(input.movement?.copy.baseline, Self.noPreMatch)
        XCTAssertFalse(endpoints.rows.contains { ($0.earlier?.label ?? "").contains("Pre-match") })
        XCTAssertEqual(Self.words(input.headline).map(\.first), [Self.noPreMatch, Self.noPreMatch])
        XCTAssertEqual(endpoints.rowSummary(endpoints.rows[0]),
                       "Jim McEwan. First captured trade 72%, Oct 12, 8:40 AM EDT, Kalshi trade · minute ending. "
                       + "Selected minute 27%, Oct 12, 8:47 AM EDT, Kalshi trade · minute ending. −45 pts")

        // With no baseline words the card claims none.
        let silent = DartsEndpointsCopy10868(
            eyebrow: nil, title: "What changed?", baseline: nil, scaleLower: "0%", scaleLabel: "Win chance", scaleUpper: "100%",
            graphicLabel: "Rows", markKey: nil, endpointUnavailable: "Unavailable", unavailableWords: "Gone",
            noComparison: "None", selectedWords: nil, sourcesLabel: nil, expandLabel: "Expand")
        XCTAssertNil(DartsEndpointsModel10868.readable(silent.baseline))
    }

    // MARK: - Endpoint placement

    func testAnAbsentOrInvalidEndpointKeepsItsValidSibling() {
        func broken(_ probability: Double, figure: String = "72%") -> DartsEndpointRow10868 {
            DartsEndpointRow10868(
                ref: Self.ref(Self.mcewan), name: "Jim McEwan",
                earlier: .endpoint(DartsDatedEndpoint10868(key: "bad", label: "First captured trade", probability: probability,
                                                           figure: figure, clock: "Oct 12, 8:40 AM EDT", provenance: Self.provenance)),
                later: .endpoint(Self.endpoint(Self.mcewan, Self.mcewan.trades[3], label: "Selected minute")),
                change: "−45 pts", shape: .circle, tint: Self.mcewan.tint)
        }
        for probability in [Double.nan, .infinity, -.infinity, -0.01, 1.2] {
            let model = DartsEndpointsModel10868(Self.movement(rows: [broken(probability), Self.row(Self.ockenburg, later: Self.m847)]))
            let rows = model.rows
            // Never clamped and never printed: the copy's words under the owner's label.
            XCTAssertEqual(rows[0].earlier, .words(label: "First captured trade", words: "Unavailable"), "\(probability)")
            XCTAssertEqual(rows[0].later?.fraction, 0.27)
            XCTAssertFalse(rows[0].isComparison)
            XCTAssertNil(model.change(rows[0]))
            XCTAssertEqual(DartsEndpointGeometry10868.marks(rows[0]), [DartsEndpointMark10868(fraction: 0.27, hollow: false)])
            // The neighbour row is untouched.
            XCTAssertTrue(rows[1].isComparison)
            XCTAssertEqual(model.change(rows[1]), "+47 pts")
            XCTAssertNil(DartsEndpointGeometry10868.fraction(probability))
        }
        // A blank figure is no figure.
        let blank = DartsEndpointsModel10868(Self.movement(rows: [broken(0.72, figure: "  ")]))
        XCTAssertEqual(blank.rows[0].earlier, .words(label: "First captured trade", words: "Unavailable"))
        // Blank absence words fall back to the copy's words, never a figure.
        let blankWords = DartsEndpointsModel10868(Self.movement(rows: [
            DartsEndpointRow10868(ref: Self.ref(Self.mcewan), name: "Jim McEwan",
                                  earlier: .absent(label: "First captured trade", words: " "),
                                  later: .absent(label: "Selected minute", words: "Not traded at 8:48 AM"),
                                  change: "−45 pts", shape: .circle, tint: Self.mcewan.tint),
        ]))
        XCTAssertEqual(blankWords.rows[0].earlier, .words(label: "First captured trade", words: "Unavailable"))
        XCTAssertFalse(blankWords.hasComparison)
        XCTAssertEqual(blankWords.openState(Self.openEarlier, hasCallback: true), .hidden)
    }

    func testZeroAndOneHundredPercentEndpointsArePlacedAndAMissingEndpointIsNot() {
        let zero = DartsDatedEndpoint10868(key: "zero", label: "Earlier", probability: 0, figure: "0%", clock: "8:40 AM", provenance: nil)
        let hundred = DartsDatedEndpoint10868(key: "hundred", label: "Later", probability: 1, figure: "100%", clock: "8:50 AM", provenance: nil)
        let model = DartsEndpointsModel10868(Self.movement(rows: [
            DartsEndpointRow10868(ref: Self.ref(Self.mcewan), name: "Jim McEwan", earlier: .endpoint(zero), later: .endpoint(hundred),
                                  change: "+100 pts", shape: .circle, tint: Self.mcewan.tint),
            DartsEndpointRow10868(ref: Self.ref(Self.ockenburg), name: "Sander van Ockenburg",
                                  earlier: .absent(label: "Earlier", words: "Not traded"), later: .endpoint(hundred),
                                  change: nil, shape: .diamond, tint: Self.ockenburg.tint),
        ]))
        XCTAssertEqual(model.rows[0].earlier, .figure(zero, fraction: 0))
        XCTAssertEqual(model.rows[0].later, .figure(hundred, fraction: 1))
        XCTAssertEqual(DartsEndpointGeometry10868.span(model.rows[0]), 0...1)
        XCTAssertEqual(model.rows[1].earlier, .words(label: "Earlier", words: "Not traded"))
        XCTAssertNil(model.rows[1].earlier?.fraction)
        XCTAssertEqual(DartsEndpointsModel10868.spoken(model.rows[0].earlier!), "Earlier 0%, 8:40 AM")
        XCTAssertEqual(DartsEndpointsModel10868.spoken(model.rows[1].earlier!), "Earlier: Not traded")

        // The absolute track: 0 at the inset, 100% at the far inset.
        XCTAssertEqual(DartsEndpointGeometry10868.x(0, width: 300, inset: 10), 10)
        XCTAssertEqual(DartsEndpointGeometry10868.x(1, width: 300, inset: 10), 290)
        XCTAssertEqual(DartsEndpointGeometry10868.x(0.27, width: 300, inset: 10)!, 85.6, accuracy: 1e-9)
        XCTAssertNil(DartsEndpointGeometry10868.x(1.2, width: 300, inset: 10))
        XCTAssertNil(DartsEndpointGeometry10868.x(0.5, width: 20, inset: 10))
        XCTAssertNil(DartsEndpointGeometry10868.x(0.5, width: .nan, inset: 10))
    }

    func testNothingIsInterpolatedOrConnectedBetweenRecordedObservations() {
        let input = Self.page(.final)
        let history = input.history
        // Lines follow the owner's runs only: no line across an untraded minute.
        let lines = history.series.map { series in
            FieldHistoryGeometry10868.lines(series, in: history).map { $0.map(\.x) }
        }
        XCTAssertEqual(lines, [[[4, 5], [10, 11]], [[8, 9, 10, 11]]])
        XCTAssertEqual(history.series.map { FieldHistoryGeometry10868.marks($0, in: history).count }, [6, 5])
        // Full size draws the same points.
        let reader = DartsEventPageModel10868(input).readerHistory
        XCTAssertEqual(reader.series, history.series)

        // The endpoint card draws its two dated endpoints and the distance
        // between them on the probability axis — no point between them.
        let endpoints = DartsEndpointsModel10868(input.movement!)
        for row in endpoints.rows {
            XCTAssertEqual(DartsEndpointGeometry10868.marks(row).count, 2)
        }
        XCTAssertEqual(endpoints.rows.map { DartsEndpointGeometry10868.span($0) }, [0.27...0.72, 0.40...0.87])
    }

    func testTheSelectedTradeNeverMovesTheLegTally() {
        let selections: [Minute?] = [nil, Self.m847, Self.m848]
        let pages = selections.map { Self.page(.final, selected: $0) }
        let models = pages.map { DartsEventPageModel10868($0) }
        // The selection changes the readouts...
        let readouts = models.map { $0.contextReadings.map(\.slot) }
        XCTAssertNotEqual(readouts[0], readouts[1])
        XCTAssertNotEqual(readouts[1], readouts[2])
        XCTAssertNotEqual(readouts[0], readouts[2])
        // ...and never the legs.
        let tally: [[Bool]?] = [[false, false, false, false], [true, true, true, true]]
        for model in models {
            XCTAssertEqual(model.legRows, models[0].legRows)
            XCTAssertEqual(model.legRows.map(\.marks), tally)
            XCTAssertEqual(model.legRows.map(\.score.figure), ["0", "4"])
            XCTAssertEqual(model.contextFooter.last, "Final · McEwan 0–4 van Ockenburg")
        }
        for page in pages {
            XCTAssertEqual(page.legs, pages[0].legs)
        }
    }

    // MARK: - Full size and the compact context

    func testFullAndPageModesReadTheSameImmutableInputs() {
        let input = Self.page(.final, selected: Self.m848, movement: Self.movement(later: Self.m848))
        let page = input.history
        let reader = DartsEventPagePresentation10868(input: input, mode: .reader(.history)).historyContent(reader: true).input
        XCTAssertEqual(page.layout, .cohortAbove)
        XCTAssertEqual(reader.layout, .expanded)
        XCTAssertNotNil(page.expand)
        XCTAssertNil(reader.expand)
        var restored = reader
        restored.layout = page.layout
        let rebuilt = FieldHistoryInput10868(
            title: restored.title, caption: restored.caption, series: restored.series, selection: restored.selection,
            domain: restored.domain, ceiling: restored.ceiling, yTicks: restored.yTicks, xTicks: restored.xTicks,
            guides: restored.guides, breaks: restored.breaks, readout: restored.readout, markKey: restored.markKey,
            comparisonExplanation: restored.comparisonExplanation, notes: restored.notes, summary: restored.summary,
            plotHeight: restored.plotHeight, unboundReadingWords: restored.unboundReadingWords,
            plotUnavailableWords: restored.plotUnavailableWords, windows: restored.windows, scale: restored.scale,
            moreOriginals: restored.moreOriginals, details: restored.details, expand: page.expand,
            inspect: restored.inspect, previous: restored.previous, next: restored.next,
            inspection: restored.inspection, layout: restored.layout,
            probabilityLowerBound: restored.probabilityLowerBound,
            probabilityRangeExplanation: restored.probabilityRangeExplanation,
            selectedReadout: restored.selectedReadout, inspectionRingShape: restored.inspectionRingShape,
            plotAbsence: restored.plotAbsence, showsKey: restored.showsKey)
        XCTAssertEqual(rebuilt, page)

        // The same selected readout in the page chart, full size and the context.
        let model = DartsEventPageModel10868(input)
        for (index, series) in page.series.enumerated() {
            XCTAssertEqual(FieldHistoryGeometry10868.readoutSlots(series, in: reader),
                           FieldHistoryGeometry10868.readoutSlots(series, in: page))
            XCTAssertEqual(model.contextReadings[index].slot, FieldHistoryGeometry10868.readoutSlots(series, in: reader).last)
        }

        // The movement card full size: the same input, no expand of its own.
        let pageMovement = DartsEventPagePresentation10868(input: input, onReaderOpen: { _ in }).movementContent(reader: false)!
        let readerMovement = DartsEventPagePresentation10868(input: input, mode: .reader(.movement), onReaderOpen: { _ in })
            .movementContent(reader: true)!
        XCTAssertEqual(readerMovement.input, pageMovement.input)
        XCTAssertEqual(readerMovement.model, pageMovement.model)
        XCTAssertNotNil(pageMovement.onExpand)
        XCTAssertNil(readerMovement.onExpand)
        XCTAssertTrue(model.readerShows(.history))
        XCTAssertTrue(model.readerShows(.movement))
    }

    func testTheCompactContextReadsTheChartsReadoutAndItsChartOpensTheFullHistory() {
        var log: [String] = []
        let input = Self.page(.final, selected: Self.m847)
        let view = DartsEventPagePresentation10868(input: input, onHistoryAction: { log.append("chart:\($0)") },
                                                   onInteraction: { log.append("hold") })
        let model = view.model
        XCTAssertEqual(model.contextReadings.map(\.seriesID), ["mcewan", "van-ockenburg"])
        XCTAssertEqual(model.contextReadings.map(\.slot),
                       input.history.series.map { FieldHistoryGeometry10868.readoutSlots($0, in: input.history).last })
        XCTAssertEqual(model.contextCaption, "Selected minute · Oct 12, 8:47 AM EDT")
        XCTAssertEqual(model.contextSummary,
                       "Selected minute · Oct 12, 8:47 AM EDT. "
                       + "Jim McEwan: Selected minute 27%, Oct 12, 8:47 AM EDT · Kalshi trade. "
                       + "Sander van Ockenburg: Selected minute 87%, Oct 12, 8:47 AM EDT · Kalshi trade. "
                       + "Pre-match chance unavailable. Final · McEwan 0–4 van Ockenburg")
        // With no inspection held the caption is the history's own.
        XCTAssertEqual(DartsEventPageModel10868(Self.page(.final)).contextCaption, "Recorded Kalshi trades · times in EDT")

        // Chart: the history's own expand id, after the page hook.
        XCTAssertEqual(log, [])
        view.contextContent().onChart?()
        XCTAssertEqual(log, ["hold", "chart:history.expand"])

        // The context belongs to the stacked page; wide keeps the chart beside the stories.
        XCTAssertTrue(DartsEventPageModel10868.showsContext(.stacked))
        XCTAssertFalse(DartsEventPageModel10868.showsContext(.sideBySide))
    }

    // MARK: - Identity resolution

    func testAWrongOrDuplicateOriginalScopeFailsClosedAndValidNeighboursStay() {
        // A row from another scope: unavailable, its own name kept, no figure.
        let foreign = DartsEndpointsModel10868(Self.movement(rows: [
            Self.row(Self.mcewan, later: Self.m847, scope: "darts:another-match"),
            Self.row(Self.ockenburg, later: Self.m847),
        ]))
        XCTAssertEqual(foreign.rows[0].resolution, .unavailable)
        XCTAssertEqual(foreign.rows[0].name, "Jim McEwan")
        XCTAssertNil(foreign.rows[0].earlier)
        XCTAssertNil(foreign.rows[0].later)
        XCTAssertEqual(DartsEndpointGeometry10868.marks(foreign.rows[0]), [])
        XCTAssertEqual(foreign.rowSummary(foreign.rows[0]), "Jim McEwan. Player unavailable in this update")
        XCTAssertNotNil(foreign.rows[1].resolution.original)
        XCTAssertTrue(foreign.rows[1].isComparison)

        // A row listed twice: both unavailable; the neighbour stays.
        let repeated = DartsEndpointsModel10868(Self.movement(rows: [
            Self.row(Self.mcewan, later: Self.m847), Self.row(Self.mcewan, later: Self.m847), Self.row(Self.ockenburg, later: Self.m847),
        ]))
        XCTAssertEqual(repeated.rows.map(\.resolution.original?.name), [nil, nil, "Sander van Ockenburg"])

        // A catalogue with two records for one identity: that identity resolves to none.
        let doubled = Self.catalogue(.final) + [Self.catalogue(.final)[0]]
        let ambiguous = DartsEndpointsModel10868(Self.movement(catalogue: doubled))
        XCTAssertEqual(ambiguous.rows.map(\.resolution.original?.name), [nil, "Sander van Ockenburg"])

        // Legs: a foreign or repeated score borrows nothing; the neighbour keeps its marks.
        var legs = Self.legs()
        legs = DartsLegsInput10868(
            label: legs.label, played: legs.played,
            scores: [DartsLegScore10868(ref: Self.ref(Self.mcewan, scope: "darts:another-match"), name: "Jim McEwan", won: 0,
                                        figure: "0", spoken: "Jim McEwan: 0 legs won")] + [legs.scores[1]],
            summary: legs.summary, provenance: legs.provenance, markKey: legs.markKey)
        let rows = DartsEventPageModel10868(Self.page(.final, legs: legs)).legRows
        XCTAssertEqual(rows.map(\.resolved), [false, true])
        XCTAssertEqual(rows.map(\.marks), [nil, [true, true, true, true]])
        XCTAssertEqual(rows.map(\.name), ["Jim McEwan", "Sander van Ockenburg"])
        let twice = DartsLegsModel10868.rows(Self.legs(players: [Self.ockenburg, Self.ockenburg])) { _ in
            .original(Self.catalogue(.final)[1])
        }
        XCTAssertEqual(twice.map(\.resolved), [false, false])

        // Details: the existing resolver, unchanged — a wrong scope or a
        // duplicated identity is no original.
        let wrongScope = Self.originals(.final, scope: "darts:another-match")
        XCTAssertNil(Originals.original(in: wrongScope.catalogue, selection: wrongScope.selection))
        let duplicated = Self.originals(.final, duplicate: true)
        XCTAssertNil(Originals.original(in: duplicated.catalogue, selection: duplicated.selection))
        let neighbour = Originals.Selection(scope: Self.originalsScope, identity: Self.identity(Self.ockenburg))
        XCTAssertEqual(Originals.original(in: duplicated.catalogue, selection: neighbour)?.outcome, "Sander van Ockenburg")
    }

    // MARK: - Holds

    func testEachPageActionHoldsOnceThenReachesItsExactOwnerValueAndReadersAndPassiveReadsDoNot() {
        var log: [String] = []
        let originals = Self.originals(.final)
        func view(_ mode: DartsEventPageMode10868 = .page, hook: Bool = true) -> DartsEventPagePresentation10868 {
            DartsEventPagePresentation10868(
                input: Self.page(.final, selected: Self.m847), mode: mode, originals: originals,
                onAbout: { log.append("about") },
                onAboutSource: { log.append("source:\($0.id)") },
                onOriginalSelect: { log.append("select:\($0.identity.market)") },
                onOriginalHistory: { log.append("history:\($0.actionID)") },
                onHeadlineOpen: { log.append("headline:\($0.ref.marketID)|\($0.ref.outcomeID)|\($0.observation ?? "none")") },
                onHistoryAction: { log.append("chart:\($0)") },
                onHistoryInspectionChoice: { log.append("inspect:\($0)") },
                onHistoryPlotPosition: { log.append("plot:\($0)") },
                onMovementOpen: { log.append("movement:\($0)") },
                onReaderOpen: { log.append("reader:\($0.rawValue)") },
                onInteraction: hook ? { log.append("hold") } : nil)
        }

        // Building and reading every leaf and content mode calls nothing.
        let page = view()
        let headline = page.headlineContent()!
        let anchor = page.historyContent(reader: false)
        let movement = page.movementContent(reader: false)!
        let context = page.contextContent()
        let catalogue = page.catalogueContent()!
        let details = view(.original).originalDetailsContent()!
        _ = page.legsContent()
        _ = page.model.contextSummary
        _ = movement.model.rows.map { movement.model.rowSummary($0) }
        _ = view(.about).aboutContent()
        _ = view(.reader(.history)).historyContent(reader: true)
        _ = view(.reader(.movement)).movementContent(reader: true)
        XCTAssertEqual(log, [])

        // Each page action: the hook once, then the exact owner value.
        headline.onOpen?(FieldMovementOpen10868(ref: Self.ref(Self.ockenburg), observation: nil))
        headline.onAbout?()
        anchor.onAction?("history.previous")
        anchor.onInspectionChoice?("van-ockenburg.0848")
        anchor.onPlotPosition?(9)
        context.onChart?()
        movement.openAction(movement.input.openEarlier)?()
        movement.openAction(movement.input.openLater)?()
        movement.sourcesAction?()
        movement.onExpand?()
        XCTAssertEqual(log, ["hold", "headline:winner.van-ockenburg|yes|none", "hold", "about",
                             "hold", "chart:history.previous", "hold", "inspect:van-ockenburg.0848", "hold", "plot:9.0",
                             "hold", "chart:history.expand", "hold", "movement:movement.earlier",
                             "hold", "movement:movement.later", "hold", "about", "hold", "reader:movement"])

        // Catalogue selection and a Details history intent: the hook once, then the exact value.
        log = []
        let card = OriginalMarketCatalogue9483.cards(catalogue: catalogue.catalogue, selection: catalogue.selection,
                                                     labels: catalogue.labels, unavailableChoice: catalogue.unavailableChoice)[1]
        OriginalMarketCatalogue9483.action(card, onSelect: catalogue.onSelect)?()
        details.onHistory?(Originals.HistoryIntent(selection: originals.selection!, entry: .explore, actionID: "constructed.explore"))
        XCTAssertEqual(log, ["hold", "select:winner.van-ockenburg", "hold", "history:constructed.explore"])

        // Already-held full-size content keeps the exact callbacks: no second hold.
        log = []
        view(.reader(.history)).historyContent(reader: true).onAction?("history.next")
        let readerMovement = view(.reader(.movement)).movementContent(reader: true)!
        readerMovement.openAction(readerMovement.input.openLater)?()
        readerMovement.sourcesAction?()
        XCTAssertNil(readerMovement.onExpand)
        view(.reader(.history)).openReaderAbout()
        view(.about).aboutContent()?.sourceAction(Self.dartsWorld)?()
        XCTAssertEqual(log, ["chart:history.next", "movement:movement.later", "about", "about", "source:darts-world"])

        // No hook: every page action is the owner's own.
        log = []
        let plain = view(hook: false)
        plain.contextContent().onChart?()
        plain.headlineContent()?.onAbout?()
        plain.historyContent(reader: false).onAction?("history.next")
        XCTAssertEqual(log, ["chart:history.expand", "about", "chart:history.next"])
    }

    func testUnavailableCallbacksAndActionsDrawNoEnabledControl() {
        var log: [String] = []
        let input = Self.page(.final, selected: Self.m847)
        let bare = DartsEventPagePresentation10868(input: input, originals: Self.originals(.final),
                                                   onInteraction: { log.append("hold") })
        XCTAssertNil(bare.headlineContent()?.onAbout)
        XCTAssertNil(bare.headlineContent()?.onOpen)
        XCTAssertNil(bare.historyContent(reader: false).onAction)
        XCTAssertNil(bare.contextContent().onChart)
        let movement = bare.movementContent(reader: false)!
        XCTAssertNil(movement.onOpen)
        XCTAssertNil(movement.onSources)
        XCTAssertNil(movement.onExpand)
        XCTAssertNil(movement.openAction(movement.input.openEarlier))
        XCTAssertNil(movement.sourcesAction)
        // Without a callback an open action is words, never a control.
        XCTAssertEqual(movement.model.openState(Self.openEarlier, hasCallback: false), .shownStatic)
        XCTAssertNil(bare.catalogueContent()?.onSelect)
        XCTAssertNil(bare.originalDetailsContent()?.onHistory)
        XCTAssertNil(bare.aboutOpener())
        XCTAssertNil(DartsEventPageAboutContent10868(about: Self.about).sourceAction(Self.dartsWorld))
        bare.openReaderAbout()
        XCTAssertEqual(log, [])

        // An unavailable, blank-id or colliding action stays words.
        let unavailable = DartsEndpointsModel10868(Self.movement(openEarlier: Self.action("movement.earlier", "Earlier in chart", available: false)))
        XCTAssertEqual(unavailable.openState(unavailable.input.openEarlier, hasCallback: true), .shownStatic)
        XCTAssertEqual(unavailable.openState(unavailable.input.openLater, hasCallback: true), .live(id: "movement.later"))
        let blankID = DartsEndpointsModel10868(Self.movement(openEarlier: Self.action(" ", "Earlier in chart")))
        XCTAssertEqual(blankID.openState(blankID.input.openEarlier, hasCallback: true), .shownStatic)
        let colliding = DartsEndpointsModel10868(Self.movement(openEarlier: Self.action("same", "Earlier in chart"),
                                                               openLater: Self.action("same", "Later in chart")))
        XCTAssertEqual(colliding.openState(colliding.input.openEarlier, hasCallback: true), .shownStatic)
        XCTAssertEqual(colliding.openState(colliding.input.openLater, hasCallback: true), .shownStatic)
        let blankLabel = DartsEndpointsModel10868(Self.movement(openEarlier: Self.action("movement.earlier", "")))
        XCTAssertEqual(blankLabel.openState(blankLabel.input.openEarlier, hasCallback: true), .hidden)
        XCTAssertEqual(DartsEndpointsModel10868(Self.movement(openEarlier: nil)).openState(nil, hasCallback: true), .hidden)

        // The context's Chart: only for the history's own live, available expand.
        let model = DartsEventPageModel10868(input)
        XCTAssertEqual(model.contextChartID(canOpen: true), "history.expand")
        XCTAssertNil(model.contextChartID(canOpen: false))
        var withoutPlot = input.history
        withoutPlot.plotAbsence = FieldHistoryPlotAbsence10868(title: "History not drawn", words: nil)
        let absentPlot = DartsEventPageInput10868(phase: .final, reader: input.reader, headline: input.headline,
                                                  history: withoutPlot, movement: input.movement, legs: input.legs,
                                                  about: input.about, copy: input.copy)
        XCTAssertNil(DartsEventPageModel10868(absentPlot).contextChartID(canOpen: true))

        // About: only with readable text and a callback.
        XCTAssertTrue(model.aboutAvailable(canOpen: true))
        XCTAssertFalse(model.aboutAvailable(canOpen: false))
        let emptyAbout = DartsEventPageInput10868(
            phase: .final, reader: input.reader, headline: input.headline, history: input.history, movement: input.movement,
            legs: input.legs, about: DartsEventPageAbout10868(title: " ", sections: []), copy: input.copy)
        XCTAssertFalse(DartsEventPageModel10868(emptyAbout).aboutAvailable(canOpen: true))
        XCTAssertFalse(model.aboutEntry(mode: .page, canOpen: true))
        XCTAssertTrue(model.aboutEntry(mode: .reader(.history), canOpen: true))
        XCTAssertFalse(model.aboutEntry(mode: .about, canOpen: true))
    }

    // MARK: - Layout plans

    func testCompactWideAndAccessibilityPlans() {
        XCTAssertEqual(DartsEventPageModel10868.arrangements(sizeClass: .compact, accessibilitySize: false), [.stacked])
        XCTAssertEqual(DartsEventPageModel10868.arrangements(sizeClass: .compact, accessibilitySize: true), [.stacked])
        XCTAssertEqual(DartsEventPageModel10868.arrangements(sizeClass: .regular, accessibilitySize: false), [.sideBySide, .stacked])
        XCTAssertEqual(DartsEventPageModel10868.arrangements(sizeClass: nil, accessibilitySize: false), [.sideBySide, .stacked])
        XCTAssertEqual(DartsEventPageModel10868.arrangements(sizeClass: .regular, accessibilitySize: true), [.stacked])
        // Legs: one column per player, one at accessibility sizes.
        XCTAssertEqual(DartsLegsModel10868.columns(count: 2, accessibilitySize: false), 2)
        XCTAssertEqual(DartsLegsModel10868.columns(count: 2, accessibilitySize: true), 1)
        XCTAssertEqual(DartsLegsModel10868.columns(count: 0, accessibilitySize: false), 1)
    }

    func testTheTallyIsDrawnOnlyFromTheOwnersConsistentCounts() {
        XCTAssertEqual(DartsLegsModel10868.marks(won: 4, played: 4), [true, true, true, true])
        XCTAssertEqual(DartsLegsModel10868.marks(won: 0, played: 4), [false, false, false, false])
        XCTAssertEqual(DartsLegsModel10868.marks(won: 2, played: 5), [true, true, false, false, false])
        // Never a literal denominator and never inferred.
        XCTAssertNil(DartsLegsModel10868.marks(won: 4, played: nil))
        XCTAssertNil(DartsLegsModel10868.marks(won: 5, played: 4))
        XCTAssertNil(DartsLegsModel10868.marks(won: -1, played: 4))
        XCTAssertNil(DartsLegsModel10868.marks(won: 0, played: 0))
        let unplayed = DartsEventPageModel10868(Self.page(.final, legs: Self.legs(played: nil)))
        XCTAssertEqual(unplayed.legRows.map(\.marks), [nil, nil])
        XCTAssertEqual(unplayed.legRows.map(\.score.figure), ["0", "4"])
    }
}
