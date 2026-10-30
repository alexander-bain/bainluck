import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the soccer exact-score map as a stateless presentation leaf across
/// pregame, live and final.
///
/// The view is SwiftUI and is not rasterised here. What is asserted is the
/// rules it defers to: the exact scope/original identities and coordinates,
/// what each cell carries, which comparison each phase shows, which results
/// are outlined, the exact-id selection, the action each control carries, the
/// spoken text and the map geometry's arithmetic. Nothing here claims a
/// rendered fit, an executed interaction or a VoiceOver pass.
///
/// ARCHIVED values come from Hull City vs Everton, event 15311089, as copied
/// in `shipping-adoption-20261027/EXACT-SCORE-RETAINED-CASES.json` (fixture
/// `native-soccer-phase-composition/FIXTURE.json` 8c43474c…). All 46 originals
/// are below with their fixture key, outcome id, coordinate, raw pregame value,
/// raw quote timestamp and independent result:
///   Full match, market 62939468: 36 grid originals plus Any Other Score
///     245266693. Raw sum 1.0001. 2–2 (237459055) 0.0398, Won; every other
///     original Lost.
///   First half, market 64002155: eight grid originals plus Any Other Score
///     244588610. Raw sum 1.0001. Home 2 / away 2 is NOT listed. Every result
///     Unconfirmed (absent from settlement).
///   Independently captured final score 2–2.
/// The quote timestamps are not period-end, settlement or grade-arrival times.
/// No current exact-score quote, live score, live clock or grade-arrival time
/// was retained, so none is used as archived evidence.
///
/// CONSTRUCTED owner-resolved inputs (this leaf does not resolve them): the
/// opaque scope identities, every display figure (one decimal, no ".0") and
/// its provenance wording, the axis labels, the pregame scales (0–10% full
/// match, 0–40% first half) and their tick labels, the headline, legend and
/// words, the actual-score wording, and every current reading, admitted
/// during-play result, delayed grade, zero, missing, withheld, off-scale,
/// invalid, duplicate, foreign, withdrawn, malformed and long-label case.
/// Geometry tests use CONSTRUCTED text sizes and are arithmetic only — not a
/// measured or rendered fit.
final class ExactScoreMapPresentation10868Tests: XCTestCase {

    // MARK: Archived originals

    private enum ArchivedResult {
        case won
        case lost
        case unconfirmed
    }

    private struct Archived {
        let key: String
        /// 0 = full match, 1 = first half.
        let scope: Int
        /// The original's outcome id, used as its opaque identity.
        let id: String
        let home: Int?
        let away: Int?
        let name: String
        let value: Double
        /// CONSTRUCTED owner figure.
        let text: String
        let observedAt: String
        let result: ArchivedResult
    }

    /// All 46 originals in fixture order (ARCHIVED except `text`).
    private static let archived: [Archived] = [
        Archived(key: "soccer-15311089-game-markets.json:other:30", scope: 0, id: "238846934", home: 0, away: 0, name: "Hull City AFC 0 - 0 Everton FC", value: 0.0599, text: "6%", observedAt: "2026-10-10T23:32:09.860099+00:00", result: .lost),
        Archived(key: "soccer-15311089-game-markets.json:other:29", scope: 0, id: "238846932", home: 0, away: 1, name: "Hull City AFC 0 - 1 Everton FC", value: 0.0811, text: "8.1%", observedAt: "2026-10-10T23:32:09.860099+00:00", result: .lost),
        Archived(key: "soccer-15311089-game-markets.json:other:31", scope: 0, id: "238846939", home: 0, away: 2, name: "Hull City AFC 0 - 2 Everton FC", value: 0.0564, text: "5.6%", observedAt: "2026-10-10T23:32:09.860099+00:00", result: .lost),
        Archived(key: "soccer-15311089-game-markets.json:other:32", scope: 0, id: "242779560", home: 0, away: 3, name: "Hull City AFC 0 - 3 Everton FC", value: 0.0278, text: "2.8%", observedAt: "2026-10-10T23:32:09.860099+00:00", result: .lost),
        Archived(key: "soccer-15311089-game-markets.json:other:33", scope: 0, id: "242779570", home: 0, away: 4, name: "Hull City AFC 0 - 4 Everton FC", value: 0.0095, text: "1%", observedAt: "2026-10-10T23:32:09.860099+00:00", result: .lost),
        Archived(key: "soccer-15311089-game-markets.json:other:35", scope: 0, id: "242779575", home: 0, away: 5, name: "Hull City AFC 0 - 5 Everton FC", value: 0.0039, text: "0.4%", observedAt: "2026-10-10T23:32:09.860099+00:00", result: .lost),
        Archived(key: "soccer-15311089-game-markets.json:other:74", scope: 0, id: "238846938", home: 1, away: 0, name: "Hull City AFC 1 - 0 Everton FC", value: 0.0529, text: "5.3%", observedAt: "2026-10-10T23:32:09.737493+00:00", result: .lost),
        Archived(key: "soccer-15311089-game-markets.json:other:72", scope: 0, id: "238846931", home: 1, away: 1, name: "Hull City AFC 1 - 1 Everton FC", value: 0.0952, text: "9.5%", observedAt: "2026-10-10T23:32:09.860099+00:00", result: .lost),
        Archived(key: "soccer-15311089-game-markets.json:other:73", scope: 0, id: "238846933", home: 1, away: 2, name: "Hull City AFC 1 - 2 Everton FC", value: 0.067, text: "6.7%", observedAt: "2026-10-10T23:32:09.860099+00:00", result: .lost),
        Archived(key: "soccer-15311089-game-markets.json:other:75", scope: 0, id: "242779559", home: 1, away: 3, name: "Hull City AFC 1 - 3 Everton FC", value: 0.0314, text: "3.1%", observedAt: "2026-10-10T23:32:09.860099+00:00", result: .lost),
        Archived(key: "soccer-15311089-game-markets.json:other:76", scope: 0, id: "242779567", home: 1, away: 4, name: "Hull City AFC 1 - 4 Everton FC", value: 0.0113, text: "1.1%", observedAt: "2026-10-10T23:32:09.860099+00:00", result: .lost),
        Archived(key: "soccer-15311089-game-markets.json:other:77", scope: 0, id: "243454866", home: 1, away: 5, name: "Hull City AFC 1 - 5 Everton FC", value: 0.0032, text: "0.3%", observedAt: "2026-10-10T23:32:09.860099+00:00", result: .lost),
        Archived(key: "soccer-15311089-game-markets.json:other:82", scope: 0, id: "242779562", home: 2, away: 0, name: "Hull City AFC 2 - 0 Everton FC", value: 0.0286, text: "2.9%", observedAt: "2026-10-10T23:32:09.860099+00:00", result: .lost),
        Archived(key: "soccer-15311089-game-markets.json:other:80", scope: 0, id: "238846941", home: 2, away: 1, name: "Hull City AFC 2 - 1 Everton FC", value: 0.0458, text: "4.6%", observedAt: "2026-10-10T23:32:09.860099+00:00", result: .lost),
        Archived(key: "soccer-15311089-game-markets.json:other:81", scope: 0, id: "237459055", home: 2, away: 2, name: "Hull City AFC 2 - 2 Everton FC", value: 0.0398, text: "4%", observedAt: "2026-10-10T23:32:09.737493+00:00", result: .won),
        Archived(key: "soccer-15311089-game-markets.json:other:83", scope: 0, id: "242779565", home: 2, away: 3, name: "Hull City AFC 2 - 3 Everton FC", value: 0.0183, text: "1.8%", observedAt: "2026-10-10T23:32:09.860099+00:00", result: .lost),
        Archived(key: "soccer-15311089-game-markets.json:other:84", scope: 0, id: "242779573", home: 2, away: 4, name: "Hull City AFC 2 - 4 Everton FC", value: 0.006, text: "0.6%", observedAt: "2026-10-10T23:32:09.860099+00:00", result: .lost),
        Archived(key: "soccer-15311089-game-markets.json:other:85", scope: 0, id: "243454870", home: 2, away: 5, name: "Hull City AFC 2 - 5 Everton FC", value: 0.0032, text: "0.3%", observedAt: "2026-10-10T23:32:09.860099+00:00", result: .lost),
        Archived(key: "soccer-15311089-game-markets.json:other:89", scope: 0, id: "237498510", home: 3, away: 0, name: "Hull City AFC 3 - 0 Everton FC", value: 0.0099, text: "1%", observedAt: "2026-10-10T23:32:09.860099+00:00", result: .lost),
        Archived(key: "soccer-15311089-game-markets.json:other:87", scope: 0, id: "237498511", home: 3, away: 1, name: "Hull City AFC 3 - 1 Everton FC", value: 0.0162, text: "1.6%", observedAt: "2026-10-10T23:32:09.860099+00:00", result: .lost),
        Archived(key: "soccer-15311089-game-markets.json:other:88", scope: 0, id: "237498512", home: 3, away: 2, name: "Hull City AFC 3 - 2 Everton FC", value: 0.013, text: "1.3%", observedAt: "2026-10-10T23:32:09.860099+00:00", result: .lost),
        Archived(key: "soccer-15311089-game-markets.json:other:90", scope: 0, id: "237459056", home: 3, away: 3, name: "Hull City AFC 3 - 3 Everton FC", value: 0.0074, text: "0.7%", observedAt: "2026-10-10T23:32:09.737493+00:00", result: .lost),
        Archived(key: "soccer-15311089-game-markets.json:other:91", scope: 0, id: "242779577", home: 3, away: 4, name: "Hull City AFC 3 - 4 Everton FC", value: 0.0018, text: "0.2%", observedAt: "2026-10-10T23:32:09.860099+00:00", result: .lost),
        Archived(key: "soccer-15311089-game-markets.json:other:86", scope: 0, id: "242779552", home: 3, away: 5, name: "Hull City AFC 3 - 5 Everton FC", value: 0.0419, text: "4.2%", observedAt: "2026-10-10T23:32:09.860099+00:00", result: .lost),
        Archived(key: "soccer-15311089-game-markets.json:other:95", scope: 0, id: "242779574", home: 4, away: 0, name: "Hull City AFC 4 - 0 Everton FC", value: 0.0032, text: "0.3%", observedAt: "2026-10-10T23:32:09.860099+00:00", result: .lost),
        Archived(key: "soccer-15311089-game-markets.json:other:94", scope: 0, id: "242779572", home: 4, away: 1, name: "Hull City AFC 4 - 1 Everton FC", value: 0.0042, text: "0.4%", observedAt: "2026-10-10T23:32:09.860099+00:00", result: .lost),
        Archived(key: "soccer-15311089-game-markets.json:other:96", scope: 0, id: "237498514", home: 4, away: 2, name: "Hull City AFC 4 - 2 Everton FC", value: 0.0032, text: "0.3%", observedAt: "2026-10-10T23:32:09.860099+00:00", result: .lost),
        Archived(key: "soccer-15311089-game-markets.json:other:97", scope: 0, id: "242779549", home: 4, away: 3, name: "Hull City AFC 4 - 3 Everton FC", value: 0.0014, text: "0.1%", observedAt: "2026-10-10T23:32:09.860099+00:00", result: .lost),
        Archived(key: "soccer-15311089-game-markets.json:other:93", scope: 0, id: "237459057", home: 4, away: 4, name: "Hull City AFC 4 - 4 Everton FC", value: 0.0229, text: "2.3%", observedAt: "2026-10-10T23:32:09.860099+00:00", result: .lost),
        Archived(key: "soccer-15311089-game-markets.json:other:92", scope: 0, id: "242779548", home: 4, away: 5, name: "Hull City AFC 4 - 5 Everton FC", value: 0.0405, text: "4.1%", observedAt: "2026-10-10T23:32:09.860099+00:00", result: .lost),
        Archived(key: "soccer-15311089-game-markets.json:other:100", scope: 0, id: "242779550", home: 5, away: 0, name: "Hull City AFC 5 - 0 Everton FC", value: 0.0409, text: "4.1%", observedAt: "2026-10-10T23:32:09.860099+00:00", result: .lost),
        Archived(key: "soccer-15311089-game-markets.json:other:103", scope: 0, id: "243454850", home: 5, away: 1, name: "Hull City AFC 5 - 1 Everton FC", value: 0.0032, text: "0.3%", observedAt: "2026-10-10T23:32:09.860099+00:00", result: .lost),
        Archived(key: "soccer-15311089-game-markets.json:other:102", scope: 0, id: "237498517", home: 5, away: 2, name: "Hull City AFC 5 - 2 Everton FC", value: 0.0247, text: "2.5%", observedAt: "2026-10-10T23:32:09.737493+00:00", result: .lost),
        Archived(key: "soccer-15311089-game-markets.json:other:99", scope: 0, id: "242779553", home: 5, away: 3, name: "Hull City AFC 5 - 3 Everton FC", value: 0.0423, text: "4.2%", observedAt: "2026-10-10T23:32:09.860099+00:00", result: .lost),
        Archived(key: "soccer-15311089-game-markets.json:other:98", scope: 0, id: "242779554", home: 5, away: 4, name: "Hull City AFC 5 - 4 Everton FC", value: 0.0455, text: "4.6%", observedAt: "2026-10-10T23:32:09.860099+00:00", result: .lost),
        Archived(key: "soccer-15311089-game-markets.json:other:101", scope: 0, id: "237459058", home: 5, away: 5, name: "Hull City AFC 5 - 5 Everton FC", value: 0.0278, text: "2.8%", observedAt: "2026-10-10T23:32:09.860099+00:00", result: .lost),
        Archived(key: "soccer-15311089-game-markets.json:other:34", scope: 0, id: "245266693", home: nil, away: nil, name: "Any Other Score", value: 0.0088, text: "0.9%", observedAt: "2026-10-10T23:32:09.737493+00:00", result: .lost),
        Archived(key: "soccer-15311089-game-markets.json:other:23", scope: 1, id: "244588607", home: 0, away: 0, name: "Hull City AFC 0 - 0 Everton FC", value: 0.307, text: "30.7%", observedAt: "2026-10-10T23:32:31.346701+00:00", result: .unconfirmed),
        Archived(key: "soccer-15311089-game-markets.json:other:24", scope: 1, id: "244588608", home: 0, away: 1, name: "Hull City AFC 0 - 1 Everton FC", value: 0.2096, text: "21%", observedAt: "2026-10-10T23:32:31.346701+00:00", result: .unconfirmed),
        Archived(key: "soccer-15311089-game-markets.json:other:26", scope: 1, id: "242337400", home: 0, away: 2, name: "Hull City AFC 0 - 2 Everton FC", value: 0.0634, text: "6.3%", observedAt: "2026-10-10T23:32:31.225635+00:00", result: .unconfirmed),
        Archived(key: "soccer-15311089-game-markets.json:other:69", scope: 1, id: "242337398", home: 1, away: 0, name: "Hull City AFC 1 - 0 Everton FC", value: 0.1511, text: "15.1%", observedAt: "2026-10-10T23:32:31.225635+00:00", result: .unconfirmed),
        Archived(key: "soccer-15311089-game-markets.json:other:70", scope: 1, id: "242337399", home: 1, away: 1, name: "Hull City AFC 1 - 1 Everton FC", value: 0.0877, text: "8.8%", observedAt: "2026-10-10T23:32:31.346701+00:00", result: .unconfirmed),
        Archived(key: "soccer-15311089-game-markets.json:other:71", scope: 1, id: "242337402", home: 1, away: 2, name: "Hull City AFC 1 - 2 Everton FC", value: 0.0336, text: "3.4%", observedAt: "2026-10-10T23:32:31.346701+00:00", result: .unconfirmed),
        Archived(key: "soccer-15311089-game-markets.json:other:78", scope: 1, id: "242337401", home: 2, away: 0, name: "Hull City AFC 2 - 0 Everton FC", value: 0.0361, text: "3.6%", observedAt: "2026-10-10T23:32:31.346701+00:00", result: .unconfirmed),
        Archived(key: "soccer-15311089-game-markets.json:other:79", scope: 1, id: "243007643", home: 2, away: 1, name: "Hull City AFC 2 - 1 Everton FC", value: 0.0239, text: "2.4%", observedAt: "2026-10-10T23:32:31.225635+00:00", result: .unconfirmed),
        Archived(key: "soccer-15311089-game-markets.json:other:25", scope: 1, id: "244588610", home: nil, away: nil, name: "Any Other Score", value: 0.0877, text: "8.8%", observedAt: "2026-10-10T23:32:31.225635+00:00", result: .unconfirmed),
    ]

    // MARK: Constructed owner inputs

    private static let fullID = "market:62939468"
    private static let firstID = "market:64002155"
    private static let scopeIDs = [fullID, firstID]
    private static let scopeLabels = ["Full match", "First half"]

    private static let twoTwo = "237459055"
    private static let fullOther = "245266693"
    private static let firstOther = "244588610"
    private static let fullZeroZero = "238846934"
    private static let fullZeroOne = "238846932"
    private static let fullZeroTwo = "238846939"
    private static let fullFiveFive = "237459058"
    private static let firstZeroZero = "244588607"
    private static let firstOneZero = "242337398"
    private static let firstOneOne = "242337399"

    private static let won = ExactScoreMapResult10868.won("Won")
    private static let lost = ExactScoreMapResult10868.lost("Lost")
    private static let unconfirmed = ExactScoreMapResult10868.unconfirmed("Unconfirmed")
    private static let liveUnavailable = ExactScoreMapCurrent10868.unavailable("Current chance unavailable")
    private static let finalScore = ExactScoreMapActual10868(title: "Final score", text: "Hull City 2–2 Everton")

    private static let words = ExactScoreMapWords10868(
        pregameTitle: "Pregame chance",
        currentTitle: "Current chance",
        liveResultTitle: "Half result",
        finalResultTitle: "Final result",
        scopeUnavailable: "Selected market unavailable.",
        noSelection: "Choose a score to compare.",
        selectionUnavailable: "Selected score unavailable.",
        recoverSelection: "View first listed score",
        mapUnavailable: "Score map unavailable. Every listed score is below.",
        scaleUnavailable: "Pregame scale unavailable. Cells are not shaded.",
        panHint: "Swipe the map sideways to see every column.",
        notListed: "Not separately listed",
        unavailableMark: "—",
        otherChoicesTitle: "Other listed outcomes",
        previous: "Previous score",
        next: "Next score",
        details: "Details",
        selectedSpoken: "Selected",
        selectScopeHint: "Shows this market's scores",
        selectHint: "Shows this score's chances",
        detailsHint: "Opens the original market"
    )

    private static let legend = ExactScoreMapLegend10868(
        scaleTitle: "Pregame chance · darker is higher",
        offScale: "Hatched: outside the pregame scale",
        notListed: "Dashed: not separately listed",
        unavailable: "—: no pregame chance",
        result: "Dark outline: confirmed result",
        selection: "Corner marks: selected score"
    )

    private static let scales = [
        ExactScoreMapScale10868(lower: 0, upper: 0.1, ticks: [
            ExactScoreMapTick10868(value: 0, text: "0%"),
            ExactScoreMapTick10868(value: 0.05, text: "5%"),
            ExactScoreMapTick10868(value: 0.1, text: "10%"),
        ]),
        ExactScoreMapScale10868(lower: 0, upper: 0.4, ticks: [
            ExactScoreMapTick10868(value: 0, text: "0%"),
            ExactScoreMapTick10868(value: 0.2, text: "20%"),
            ExactScoreMapTick10868(value: 0.4, text: "40%"),
        ]),
    ]

    private static func goals(_ count: Int) -> [ExactScoreMapGoal10868] {
        (0..<count).map { ExactScoreMapGoal10868(value: $0, text: String($0)) }
    }

    private static func detail(_ observedAt: String) -> String {
        "Polymarket · recorded \(observedAt)"
    }

    private static func observation(_ a: Archived) -> ExactScoreMapObservation10868 {
        ExactScoreMapObservation10868(probability: a.value, text: a.text, detail: detail(a.observedAt))
    }

    private static func result(_ a: Archived) -> ExactScoreMapResult10868 {
        switch a.result {
        case .won: won
        case .lost: lost
        case .unconfirmed: unconfirmed
        }
    }

    private static func placement(_ a: Archived) -> ExactScoreMapPlacement10868 {
        if let home = a.home, let away = a.away { return .grid(home: home, away: away) }
        return .nonGrid
    }

    /// The archived originals of one scope, with per-id overrides. By default
    /// every original carries its ARCHIVED final result in every phase — the
    /// supplied "future" data the earlier phases must hide.
    private static func originals(
        _ scope: Int,
        pregame: [String: ExactScoreMapPregame10868] = [:],
        current: [String: ExactScoreMapCurrent10868] = [:],
        result overrides: [String: ExactScoreMapResult10868] = [:],
        placement places: [String: ExactScoreMapPlacement10868] = [:]
    ) -> [ExactScoreMapOriginal10868] {
        archived.filter { $0.scope == scope }.map { a in
            ExactScoreMapOriginal10868(
                id: a.id,
                label: a.name,
                placement: places[a.id] ?? placement(a),
                pregame: pregame[a.id] ?? .recorded(observation(a)),
                current: current[a.id] ?? liveUnavailable,
                result: overrides[a.id] ?? result(a)
            )
        }
    }

    private static func scope(
        _ index: Int,
        originals list: [ExactScoreMapOriginal10868]? = nil,
        rows: [ExactScoreMapGoal10868]? = nil,
        columns: [ExactScoreMapGoal10868]? = nil,
        scale: ExactScoreMapScale10868? = nil,
        actual: ExactScoreMapActual10868?? = nil
    ) -> ExactScoreMapScope10868 {
        let size = index == 0 ? 6 : 3
        return ExactScoreMapScope10868(
            id: scopeIDs[index],
            label: scopeLabels[index],
            rows: rows ?? goals(size),
            columns: columns ?? goals(size),
            originals: list ?? originals(index),
            scale: scale ?? scales[index],
            actual: actual ?? (index == 0 ? finalScore : nil)
        )
    }

    private static func input(
        _ phase: ExactScoreMapPhase10868,
        scopes: [ExactScoreMapScope10868]? = nil,
        scopeID: String? = fullID,
        originalID: String? = twoTwo
    ) -> ExactScoreMapInput10868 {
        ExactScoreMapInput10868(
            phase: phase,
            title: "How might it finish?",
            intro: nil,
            homeLabel: "Hull City",
            awayLabel: "Everton",
            rowsTitle: "Rows: Hull City goals",
            columnsTitle: "Columns: Everton goals",
            scopes: scopes ?? [scope(0), scope(1)],
            selectedScopeID: scopeID,
            selectedOriginalID: originalID,
            legend: legend,
            words: words
        )
    }

    /// During play with the full match still open: its supplied results are
    /// not yet admitted (CONSTRUCTED), the first half's archived Unconfirmed.
    /// No live score was retained, so none is supplied.
    private static func liveScopes(
        current: [String: ExactScoreMapCurrent10868] = [:],
        firstHalfResults: [String: ExactScoreMapResult10868] = [:]
    ) -> [ExactScoreMapScope10868] {
        let open = Dictionary(uniqueKeysWithValues: archived.filter { $0.scope == 0 }.map { ($0.id, unconfirmed) })
        return [
            scope(0, originals: originals(0, current: current, result: open), actual: .some(nil)),
            scope(1, originals: originals(1, current: current, result: firstHalfResults)),
        ]
    }

    private static func original(_ id: String, in scope: ExactScoreMapScope10868) -> ExactScoreMapOriginal10868 {
        scope.originals.first { $0.id == id }!
    }

    private static func cell(_ row: Int, _ column: Int, in input: ExactScoreMapInput10868,
                             scope: ExactScoreMapScope10868) -> ExactScoreMapCell10868 {
        input.cells(scope)[row * scope.columns.count + column]
    }

    private static func intensity(_ fill: ExactScoreMapFill10868) -> Double? {
        if case .intensity(let fraction) = fill { return fraction }
        return nil
    }

    private static func pregame(_ id: String, in scope: ExactScoreMapScope10868) -> ExactScoreMapComparison10868 {
        ExactScoreMapComparison10868(title: words.pregameTitle, reading: .figure(original(id, in: scope).pregame.observation!))
    }

    // MARK: Retained originals

    func testAllFortySixOriginalsKeepTheirExactIdentitiesCoordinatesValuesAndClocks() {
        let input = Self.input(.before)
        XCTAssertEqual(Self.archived.count, 46)
        XCTAssertEqual(Set(Self.archived.map(\.id)).count, 46)
        XCTAssertEqual(Set(Self.archived.map(\.key)).count, 46)
        for (index, scope) in input.scopes.enumerated() {
            XCTAssertEqual(scope.id, Self.scopeIDs[index])
            let rows = Self.archived.filter { $0.scope == index }
            // The owner's order is kept: nothing is sorted, ranked or dropped.
            XCTAssertEqual(scope.originals.map(\.id), rows.map(\.id))
            for a in rows {
                let original = Self.original(a.id, in: scope)
                XCTAssertEqual(original.label, a.name)
                XCTAssertEqual(original.pregame.observation?.probability, a.value)
                XCTAssertEqual(original.pregame.observation?.text, a.text)
                XCTAssertEqual(original.pregame.observation?.detail.contains(a.observedAt), true, a.id)
                if let home = a.home, let away = a.away {
                    XCTAssertEqual(input.position(original, in: scope),
                                   ExactScoreMapPosition10868(row: home, column: away), a.id)
                    let cell = Self.cell(home, away, in: input, scope: scope)
                    XCTAssertEqual(cell.slot, .original(original))
                    XCTAssertEqual(cell.text, a.text)
                } else {
                    XCTAssertNil(input.position(original, in: scope))
                    XCTAssertEqual(input.choices(in: scope).map(\.id), [a.id])
                }
            }
        }
    }

    func testTheFullMatchMapsThirtySixScoresAndNamesAnyOtherScore() {
        let input = Self.input(.before)
        let full = input.scopes[0]
        let cells = input.cells(full)
        XCTAssertEqual(cells.count, 36)
        XCTAssertTrue(cells.allSatisfy { if case .original = $0.slot { return true } else { return false } })
        XCTAssertEqual(Set(cells.compactMap { cell -> String? in
            if case .original(let original) = cell.slot { return original.id }
            return nil
        }).count, 36)
        XCTAssertEqual(input.choices(in: full).map(\.id), [Self.fullOther])
        XCTAssertEqual(input.choices(in: full).first?.label, "Any Other Score")
        XCTAssertEqual(input.choices(in: full).first?.pregame.observation?.text, "0.9%")
        XCTAssertFalse(input.keyUse(full).notListed)
    }

    func testTheFirstHalfMapsEightScoresAndNamesTheUnlistedTwoTwo() {
        let input = Self.input(.before, scopeID: Self.firstID, originalID: Self.firstZeroZero)
        let first = input.scopes[1]
        let cells = input.cells(first)
        XCTAssertEqual(cells.count, 9)
        let unlisted = Self.cell(2, 2, in: input, scope: first)
        XCTAssertEqual(unlisted.slot, .notListed)
        XCTAssertEqual(unlisted.text, "")
        XCTAssertEqual(unlisted.fill, .blank)
        XCTAssertTrue(unlisted.isDashed)
        XCTAssertFalse(unlisted.showsResult)
        XCTAssertEqual(cells.filter { $0.slot == .notListed }.count, 1)
        XCTAssertEqual(input.choices(in: first).map(\.id), [Self.firstOther])
        XCTAssertTrue(input.keyUse(first).notListed)
        XCTAssertTrue(input.accessibilityMapValue(first).contains("Hull City 2, Everton 2: Not separately listed"))
        XCTAssertNil(input.tapAction(at: ExactScoreMapPosition10868(row: 2, column: 2), canSelect: true))
    }

    func testEachScopeKeepsItsRawSumAndUnnormalizedShading() {
        let input = Self.input(.before)
        for (index, scope) in input.scopes.enumerated() {
            let rows = Self.archived.filter { $0.scope == index }
            XCTAssertEqual(rows.map(\.value).reduce(0, +), 1.0001, accuracy: 1e-9)
            for a in rows {
                guard let home = a.home, let away = a.away else { continue }
                let fill = Self.cell(home, away, in: input, scope: scope).fill
                XCTAssertEqual(Self.intensity(fill) ?? -1, a.value / Self.scales[index].upper, accuracy: 1e-12, a.id)
            }
        }
        XCTAssertEqual(Self.intensity(Self.cell(2, 2, in: input, scope: input.scopes[0]).fill) ?? -1, 0.398, accuracy: 1e-12)
        XCTAssertEqual(Self.intensity(Self.cell(0, 0, in: input, scope: input.scopes[1]).fill) ?? -1, 0.7675, accuracy: 1e-12)
    }

    // MARK: Phases

    func testBeforeShowsOnlyThePregameChanceWhateverLaterReadingsAreSupplied() {
        let current = ExactScoreMapObservation10868(probability: 0.55, text: "55%", detail: "Polymarket · 5:10 PM")
        let scopes = [Self.scope(0, originals: Self.originals(0, current: [Self.twoTwo: .recorded(current)])), Self.scope(1)]
        let input = Self.input(.before, scopes: scopes)
        let full = input.scopes[0]
        let twoTwo = Self.original(Self.twoTwo, in: full)
        XCTAssertEqual(input.comparisons(twoTwo), [Self.pregame(Self.twoTwo, in: full)])
        XCTAssertNil(input.visibleActual(full))
        XCTAssertFalse(input.cells(full).contains(where: \.showsResult))
        XCTAssertFalse(input.cells(input.scopes[1]).contains(where: \.showsResult))
        XCTAssertFalse(input.keyUse(full).result)
        let spoken = input.accessibilitySummary(twoTwo, in: full)
        XCTAssertFalse(spoken.contains("55%"))
        XCTAssertFalse(spoken.contains("Won"))
        XCTAssertFalse(spoken.contains("Final score"))
        XCTAssertEqual(spoken, "Pregame chance: 4%, Polymarket · recorded 2026-10-10T23:32:09.737493+00:00")
    }

    func testDuringShowsPregameAndCurrentWithTheSameFigureTreatment() {
        let current = ExactScoreMapObservation10868(probability: 0.07, text: "7%", detail: "Polymarket · 5:40 PM")
        let input = Self.input(.during, scopes: Self.liveScopes(current: [Self.twoTwo: .recorded(current)]))
        let full = input.scopes[0]
        let comparisons = input.comparisons(Self.original(Self.twoTwo, in: full))
        XCTAssertEqual(comparisons, [
            Self.pregame(Self.twoTwo, in: full),
            ExactScoreMapComparison10868(title: "Current chance", reading: .figure(current)),
        ])
        XCTAssertEqual(input.accessibilitySummary(Self.original(Self.twoTwo, in: full), in: full),
                       "Pregame chance: 4%, Polymarket · recorded 2026-10-10T23:32:09.737493+00:00; "
                       + "Current chance: 7%, Polymarket · 5:40 PM")
        // The map stays pregame: the current figure is never a cell figure or shade.
        XCTAssertEqual(Self.cell(2, 2, in: input, scope: full).text, "4%")
        XCTAssertEqual(Self.intensity(Self.cell(2, 2, in: input, scope: full).fill) ?? -1, 0.398, accuracy: 1e-12)
    }

    func testDuringMissingAndWithheldCurrentUseOwnerWordsAndNeverAHistoricalQuote() {
        let input = Self.input(.during, scopes: Self.liveScopes(current: [
            Self.twoTwo: .withheld("No update since 5:12 PM"),
            Self.fullZeroZero: .unavailable("Current chance unavailable"),
        ]))
        let full = input.scopes[0]
        XCTAssertEqual(input.comparisons(Self.original(Self.twoTwo, in: full))[1],
                       ExactScoreMapComparison10868(title: "Current chance", reading: .words("No update since 5:12 PM")))
        XCTAssertEqual(input.comparisons(Self.original(Self.fullZeroZero, in: full))[1],
                       ExactScoreMapComparison10868(title: "Current chance", reading: .words("Current chance unavailable")))
        for id in [Self.twoTwo, Self.fullZeroZero] {
            let pregame = Self.original(id, in: full).pregame.observation!
            XCTAssertNotEqual(input.comparisons(Self.original(id, in: full))[1].reading, .figure(pregame))
        }
    }

    func testTheRetainedLiveSnapshotHasNoCurrentChanceForAnyOfTheFortySix() {
        let input = Self.input(.during, scopes: Self.liveScopes())
        var count = 0
        for scope in input.scopes {
            for original in scope.originals {
                XCTAssertEqual(input.comparisons(original), [
                    Self.pregame(original.id, in: scope),
                    ExactScoreMapComparison10868(title: "Current chance", reading: .words("Current chance unavailable")),
                ], original.id)
                count += 1
            }
            XCTAssertFalse(input.cells(scope).contains(where: \.showsResult))
        }
        XCTAssertEqual(count, 46)
    }

    func testAFirstHalfResolvedDuringPlayShowsItsOwnResultWithoutBorrowingFullMatchStatus() {
        // CONSTRUCTED: the first half settled 1–0 while the full match is still open.
        var firstHalf = Dictionary(uniqueKeysWithValues: Self.archived.filter { $0.scope == 1 }.map { ($0.id, Self.lost) })
        firstHalf[Self.firstOneZero] = Self.won
        let input = Self.input(.during, scopes: Self.liveScopes(firstHalfResults: firstHalf),
                               scopeID: Self.firstID, originalID: Self.firstOneZero)
        let first = input.scopes[1]
        let full = input.scopes[0]
        XCTAssertEqual(input.comparisons(Self.original(Self.firstOneZero, in: first)), [
            Self.pregame(Self.firstOneZero, in: first),
            ExactScoreMapComparison10868(title: "Half result", reading: .result(Self.won)),
        ])
        XCTAssertEqual(input.comparisons(Self.original(Self.firstZeroZero, in: first))[1].reading, .result(Self.lost))
        XCTAssertTrue(Self.cell(1, 0, in: input, scope: first).showsResult)
        XCTAssertEqual(input.cells(first).filter(\.showsResult).count, 1)
        // The full match's own 1–0 keeps its own live reading.
        XCTAssertEqual(input.comparisons(Self.original("238846938", in: full))[1],
                       ExactScoreMapComparison10868(title: "Current chance", reading: .words("Current chance unavailable")))
        XCTAssertFalse(input.cells(full).contains(where: \.showsResult))
        XCTAssertNil(input.visibleActual(first))
    }

    func testFinalPairsTheFullMatchTwoTwoPregameChanceWithItsIndependentWin() {
        let input = Self.input(.final)
        let full = input.scopes[0]
        let twoTwo = Self.original(Self.twoTwo, in: full)
        XCTAssertEqual(input.comparisons(twoTwo), [
            Self.pregame(Self.twoTwo, in: full),
            ExactScoreMapComparison10868(title: "Final result", reading: .result(Self.won)),
        ])
        XCTAssertEqual(Self.won.mark, .won)
        XCTAssertEqual(input.visibleActual(full), Self.finalScore)
        XCTAssertEqual(input.accessibilitySummary(twoTwo, in: full),
                       "Pregame chance: 4%, Polymarket · recorded 2026-10-10T23:32:09.737493+00:00; "
                       + "Final result: Won. Final score: Hull City 2–2 Everton")
    }

    func testFinalOutlinesOnlySuppliedWins() {
        let input = Self.input(.final)
        let full = input.scopes[0]
        XCTAssertEqual(input.cells(full).filter(\.showsResult).map(\.position), [ExactScoreMapPosition10868(row: 2, column: 2)])
        XCTAssertFalse(input.cells(input.scopes[1]).contains(where: \.showsResult))
        XCTAssertTrue(input.keyUse(full).result)
        let other = Self.original(Self.fullOther, in: full)
        XCTAssertEqual(input.comparisons(other)[1].reading, .result(Self.lost))
        XCTAssertEqual(Self.lost.mark, .lost)
        XCTAssertFalse(input.showsResult(other))
    }

    func testTheFirstHalfAnyOtherScoreStaysUnconfirmedAfterTheFullMatchFinal() {
        let input = Self.input(.final, scopeID: Self.firstID, originalID: Self.firstOther)
        let first = input.scopes[1]
        let other = Self.original(Self.firstOther, in: first)
        XCTAssertEqual(input.comparisons(other), [
            Self.pregame(Self.firstOther, in: first),
            ExactScoreMapComparison10868(title: "Final result", reading: .result(Self.unconfirmed)),
        ])
        XCTAssertNil(Self.unconfirmed.mark)
        XCTAssertFalse(Self.unconfirmed.isAdmitted)
        XCTAssertFalse(input.keyUse(first).result)
        XCTAssertTrue(input.cells(first).allSatisfy { !$0.showsResult })
        XCTAssertNil(input.visibleActual(first))
        // The full match's settlement does not reach it.
        XCTAssertTrue(input.cells(input.scopes[0]).contains(where: \.showsResult))
    }

    func testAnActualTwoTwoWithoutSettlementMarksNothingWonOrLost() {
        // CONSTRUCTED: the final score has arrived, the grades have not.
        let pending = Dictionary(uniqueKeysWithValues: Self.archived.filter { $0.scope == 0 }.map { ($0.id, Self.unconfirmed) })
        let input = Self.input(.final, scopes: [Self.scope(0, originals: Self.originals(0, result: pending)), Self.scope(1)])
        let full = input.scopes[0]
        XCTAssertEqual(input.visibleActual(full), Self.finalScore)
        XCTAssertFalse(input.cells(full).contains(where: \.showsResult))
        XCTAssertEqual(input.comparisons(Self.original(Self.twoTwo, in: full))[1].reading, .result(Self.unconfirmed))
        XCTAssertEqual(input.comparisons(Self.original(Self.fullZeroZero, in: full))[1].reading, .result(Self.unconfirmed))
        XCTAssertFalse(input.accessibilitySummary(Self.original(Self.fullZeroZero, in: full), in: full).contains("Lost"))
    }

    func testTheActualScoreIsItsOwnInputAndNeverAGrade() {
        let other = ExactScoreMapActual10868(title: "Final score", text: "Hull City 3–1 Everton")
        let a = Self.input(.final)
        let b = Self.input(.final, scopes: [Self.scope(0, actual: .some(other)), Self.scope(1)])
        let c = Self.input(.final, scopes: [Self.scope(0, actual: .some(nil)), Self.scope(1)])
        XCTAssertEqual(a.cells(a.scopes[0]), b.cells(b.scopes[0]))
        XCTAssertEqual(a.cells(a.scopes[0]), c.cells(c.scopes[0]))
        XCTAssertEqual(b.visibleActual(b.scopes[0]), other)
        XCTAssertNil(c.visibleActual(c.scopes[0]))
        XCTAssertEqual(c.comparisons(Self.original(Self.twoTwo, in: c.scopes[0]))[1].reading, .result(Self.won))
        // Supplied during play, labelled as the owner chose; never before.
        let live = Self.input(.during)
        XCTAssertEqual(live.visibleActual(live.scopes[0]), Self.finalScore)
        XCTAssertNil(Self.input(.before).visibleActual(Self.input(.before).scopes[0]))
    }

    func testTheSameFigureAtTwoClocksStaysTwoReadings() {
        let early = ExactScoreMapObservation10868(probability: 0.04, text: "4%", detail: "Polymarket · 5:10 PM")
        let late = ExactScoreMapObservation10868(probability: 0.04, text: "4%", detail: "Polymarket · 5:40 PM")
        let a = Self.input(.during, scopes: Self.liveScopes(current: [Self.twoTwo: .recorded(early)]))
        let b = Self.input(.during, scopes: Self.liveScopes(current: [Self.twoTwo: .recorded(late)]))
        let readA = a.comparisons(Self.original(Self.twoTwo, in: a.scopes[0]))
        let readB = b.comparisons(Self.original(Self.twoTwo, in: b.scopes[0]))
        XCTAssertNotEqual(readA, readB)
        XCTAssertTrue(a.spokenComparisons(Self.original(Self.twoTwo, in: a.scopes[0])).hasSuffix("Current chance: 4%, Polymarket · 5:10 PM"))
        XCTAssertTrue(b.spokenComparisons(Self.original(Self.twoTwo, in: b.scopes[0])).hasSuffix("Current chance: 4%, Polymarket · 5:40 PM"))
    }

    // MARK: Cells

    func testAZeroIsARealQuotedZero() {
        let zero = ExactScoreMapObservation10868(probability: 0, text: "0%", detail: "Polymarket · recorded 2026-10-10T23:32:09.860099+00:00")
        let input = Self.input(.before, scopes: [Self.scope(0, originals: Self.originals(0, pregame: ["242779575": .recorded(zero)])), Self.scope(1)])
        let full = input.scopes[0]
        let cell = Self.cell(0, 5, in: input, scope: full)
        XCTAssertEqual(cell.fill, .intensity(0))
        XCTAssertEqual(cell.text, "0%")
        XCTAssertFalse(cell.isDashed)
        XCTAssertFalse(input.keyUse(full).unavailable)
        XCTAssertFalse(input.keyUse(full).offScale)
    }

    func testAnUnlistedCoordinateIsNotAListedScoreWithoutAReading() {
        let input = Self.input(.before, scopes: [
            Self.scope(0),
            Self.scope(1, originals: Self.originals(1, pregame: [Self.firstOneOne: .unavailable("Pregame chance unavailable")])),
        ], scopeID: Self.firstID, originalID: Self.firstOneOne)
        let first = input.scopes[1]
        let missing = Self.cell(1, 1, in: input, scope: first)
        let unlisted = Self.cell(2, 2, in: input, scope: first)
        XCTAssertEqual(missing.text, "—")
        XCTAssertEqual(missing.fill, .blank)
        XCTAssertFalse(missing.isDashed)
        XCTAssertEqual(missing.slot, .original(Self.original(Self.firstOneOne, in: first)))
        XCTAssertEqual(unlisted.text, "")
        XCTAssertTrue(unlisted.isDashed)
        XCTAssertEqual(input.comparisons(Self.original(Self.firstOneOne, in: first)),
                       [ExactScoreMapComparison10868(title: "Pregame chance", reading: .words("Pregame chance unavailable"))])
        XCTAssertTrue(input.keyUse(first).unavailable)
        XCTAssertTrue(input.keyUse(first).notListed)
        let value = input.accessibilityMapValue(first)
        XCTAssertTrue(value.contains("Hull City 2, Everton 2: Not separately listed"))
        XCTAssertFalse(value.contains("Hull City 1, Everton 1: Not separately listed"))
        XCTAssertNotNil(input.tapAction(at: ExactScoreMapPosition10868(row: 1, column: 1), canSelect: true))
    }

    func testOffScaleAndInvalidReadingsAreHatchedNeverClampedAndKeepTheirFigures() {
        func obs(_ value: Double, _ text: String) -> ExactScoreMapPregame10868 {
            .recorded(ExactScoreMapObservation10868(probability: value, text: text, detail: "constructed"))
        }
        let input = Self.input(.before, scopes: [Self.scope(0, originals: Self.originals(0, pregame: [
            Self.fullZeroZero: obs(0.25, "25%"),
            Self.fullZeroOne: obs(.nan, "8.1%"),
            Self.fullZeroTwo: obs(-0.1, "5.6%"),
            "242779560": obs(1.2, "2.8%"),
            "242779570": obs(0.1, "10%"),
        ])), Self.scope(1)])
        let full = input.scopes[0]
        XCTAssertEqual(Self.cell(0, 0, in: input, scope: full).fill, .offScale)
        XCTAssertEqual(Self.cell(0, 0, in: input, scope: full).text, "25%")
        XCTAssertEqual(Self.cell(0, 1, in: input, scope: full).fill, .offScale)
        XCTAssertEqual(Self.cell(0, 1, in: input, scope: full).text, "8.1%")
        XCTAssertEqual(Self.cell(0, 2, in: input, scope: full).fill, .offScale)
        XCTAssertEqual(Self.cell(0, 3, in: input, scope: full).fill, .offScale)
        XCTAssertEqual(Self.cell(0, 4, in: input, scope: full).fill, .intensity(1))
        XCTAssertTrue(input.keyUse(full).offScale)
    }

    func testAScaleThatIsNotAProbabilityScaleShadesNothing() {
        let bad: [(Double, Double)] = [(0.1, 0.1), (0.2, 0.1), (-0.1, 0.1), (0, 1.5), (0, .nan), (.infinity, 1)]
        for (lower, upper) in bad {
            let scale = ExactScoreMapScale10868(lower: lower, upper: upper, ticks: [ExactScoreMapTick10868(value: 0.05, text: "5%")])
            XCTAssertFalse(scale.isValid)
            let input = Self.input(.before, scopes: [Self.scope(0, scale: scale), Self.scope(1)])
            let full = input.scopes[0]
            XCTAssertTrue(input.cells(full).allSatisfy { $0.fill == .blank }, "\(lower)…\(upper)")
            XCTAssertTrue(input.scaleKey(full).isEmpty)
            XCTAssertEqual(Self.cell(2, 2, in: input, scope: full).text, "4%")
        }
    }

    func testTheScaleKeyLabelsEachPlaceableTickOnce() {
        let scale = ExactScoreMapScale10868(lower: 0, upper: 0.1, ticks: [
            ExactScoreMapTick10868(value: 0, text: "0%"),
            ExactScoreMapTick10868(value: 0.05, text: "5%"),
            ExactScoreMapTick10868(value: 0.05, text: "5% again"),
            ExactScoreMapTick10868(value: 0.2, text: "20%"),
            ExactScoreMapTick10868(value: .nan, text: "?"),
        ])
        let input = Self.input(.before, scopes: [Self.scope(0, scale: scale), Self.scope(1)])
        let key = input.scaleKey(input.scopes[0])
        XCTAssertEqual(key.map(\.text), ["0%", "5%"])
        XCTAssertEqual(key.map(\.fraction), [0, 0.5])
    }

    func testSelectionNeverRescalesOrReordersTheMap() {
        let a = Self.input(.final, originalID: Self.twoTwo)
        let b = Self.input(.final, originalID: Self.fullFiveFive)
        let cellsA = a.cells(a.scopes[0])
        let cellsB = b.cells(b.scopes[0])
        XCTAssertEqual(cellsA.map(\.position), cellsB.map(\.position))
        XCTAssertEqual(cellsA.map(\.text), cellsB.map(\.text))
        XCTAssertEqual(cellsA.map(\.fill), cellsB.map(\.fill))
        XCTAssertEqual(cellsA.map(\.showsResult), cellsB.map(\.showsResult))
        XCTAssertEqual(cellsA.filter(\.isSelected).map(\.position), [ExactScoreMapPosition10868(row: 2, column: 2)])
        XCTAssertEqual(cellsB.filter(\.isSelected).map(\.position), [ExactScoreMapPosition10868(row: 5, column: 5)])
        XCTAssertEqual(a.choices(in: a.scopes[0]), b.choices(in: b.scopes[0]))
    }

    // MARK: Selection and identity

    func testSelectionIsExactAndHeldAcrossPhases() {
        for phase in [ExactScoreMapPhase10868.before, .during, .final] {
            let input = Self.input(phase)
            let full = input.scopes[0]
            XCTAssertEqual(input.scopeSelection, .selected(full))
            XCTAssertEqual(input.originalSelection(in: full), .selected(Self.original(Self.twoTwo, in: full)))
            XCTAssertEqual(input.cells(full).filter(\.isSelected).map(\.position), [ExactScoreMapPosition10868(row: 2, column: 2)])
        }
    }

    func testAWithdrawnOrForeignSelectionIsUnavailableAndOffersOnlyTheOwnersRecovery() {
        // Foreign: the full match's 2–2 asked of the first half.
        let foreign = Self.input(.final, scopeID: Self.firstID, originalID: Self.twoTwo)
        // Withdrawn: the full match without its 2–2.
        let withdrawn = Self.input(.final, scopes: [Self.scope(0, originals: Self.originals(0).filter { $0.id != Self.twoTwo }), Self.scope(1)])
        for input in [foreign, withdrawn] {
            let scope = input.scopeSelection.scope!
            XCTAssertEqual(input.originalSelection(in: scope), .missing(Self.twoTwo))
            XCTAssertFalse(input.cells(scope).contains(where: \.isSelected))
            XCTAssertNil(input.stepAction(1, canSelect: true))
            XCTAssertNil(input.stepAction(-1, canSelect: true))
            XCTAssertFalse(input.showsSteps(canSelect: true))
            XCTAssertFalse(input.isAdjustable(canSelect: true))
            XCTAssertNil(input.detailsAction(canOpen: true))
            XCTAssertEqual(input.recoverAction(canRecover: true), .recover)
            XCTAssertNil(input.recoverAction(canRecover: false))
            XCTAssertTrue(input.accessibilityMapValue(scope).hasPrefix("Selected score unavailable."))
        }
        // Restoring the original restores its exact identity.
        let restored = Self.input(.final)
        XCTAssertEqual(restored.originalSelection(in: restored.scopes[0]).original?.id, Self.twoTwo)
    }

    func testWithNothingSelectedOnlyAnExplicitNextAsksForTheOwnersFirst() {
        let input = Self.input(.before, originalID: nil)
        let full = input.scopes[0]
        XCTAssertEqual(input.originalSelection(in: full), .unselected)
        XCTAssertFalse(input.cells(full).contains(where: \.isSelected))
        XCTAssertEqual(input.stepAction(1, canSelect: true), .selectOriginal(scopeID: Self.fullID, originalID: Self.fullZeroZero))
        XCTAssertNil(input.stepAction(-1, canSelect: true))
        XCTAssertTrue(input.showsSteps(canSelect: true))
        XCTAssertEqual(input.recoverAction(canRecover: true), .recover)
        XCTAssertNil(input.detailsAction(canOpen: true))
        XCTAssertTrue(input.accessibilityMapValue(full).hasPrefix("Choose a score to compare."))
    }

    func testScopeSelectionIsExactAndNeverSubstituted() {
        XCTAssertEqual(Self.input(.before, scopeID: nil).scopeSelection, .unselected)
        XCTAssertEqual(Self.input(.before, scopeID: "market:unknown").scopeSelection, .missing("market:unknown"))
        let twice = Self.input(.before, scopes: [Self.scope(0), Self.scope(0), Self.scope(1)])
        XCTAssertEqual(twice.scopeSelection, .duplicate(Self.fullID))
        XCTAssertNil(twice.selectScopeAction(twice.scopes[0], canSelect: true))
        XCTAssertEqual(twice.selectScopeAction(twice.scopes[2], canSelect: true), .selectScope(Self.firstID))
        XCTAssertNil(twice.tapAction(at: ExactScoreMapPosition10868(row: 2, column: 2), canSelect: true))
        XCTAssertNil(twice.recoverAction(canRecover: true))
        let input = Self.input(.before)
        XCTAssertEqual(input.selectScopeAction(input.scopes[1], canSelect: true), .selectScope(Self.firstID))
    }

    func testDuplicatedOriginalIdentitiesOfferNoAction() {
        var list = Self.originals(0)
        for index in list.indices where [Self.fullZeroZero, Self.fullZeroOne].contains(list[index].id) {
            let o = list[index]
            list[index] = ExactScoreMapOriginal10868(id: "dup", label: o.label, placement: o.placement,
                                                     pregame: o.pregame, current: o.current, result: o.result)
        }
        let input = Self.input(.before, scopes: [Self.scope(0, originals: list), Self.scope(1)], originalID: "dup")
        let full = input.scopes[0]
        XCTAssertEqual(input.originalSelection(in: full), .duplicate("dup"))
        XCTAssertFalse(input.cells(full).contains(where: \.isSelected))
        XCTAssertNil(input.tapAction(at: ExactScoreMapPosition10868(row: 0, column: 0), canSelect: true))
        XCTAssertNil(input.tapAction(at: ExactScoreMapPosition10868(row: 0, column: 1), canSelect: true))
        XCTAssertFalse(input.actionableIDs(in: full).contains("dup"))
        XCTAssertEqual(input.actionableIDs(in: full).count, 35)
        XCTAssertNil(input.detailsAction(canOpen: true))
        // Stepping skips them: from 0–2, Previous has nothing left before it.
        let fromZeroTwo = Self.input(.before, scopes: [Self.scope(0, originals: list), Self.scope(1)], originalID: Self.fullZeroTwo)
        XCTAssertNil(fromZeroTwo.stepAction(-1, canSelect: true))
        XCTAssertEqual(fromZeroTwo.stepAction(1, canSelect: true), .selectOriginal(scopeID: Self.fullID, originalID: "242779560"))
    }

    func testDuplicatedCoordinatesAreAmbiguousOnTheMapAndReachableByName() {
        let extra = ExactScoreMapOriginal10868(
            id: "constructed:second-0-0", label: "Hull City 0 – 0 Everton (second listing)", placement: .grid(home: 0, away: 0),
            pregame: .recorded(ExactScoreMapObservation10868(probability: 0.3, text: "30%", detail: "constructed")),
            current: Self.liveUnavailable, result: Self.unconfirmed)
        let input = Self.input(.before, scopes: [Self.scope(0), Self.scope(1, originals: Self.originals(1) + [extra])],
                               scopeID: Self.firstID, originalID: Self.firstZeroZero)
        let first = input.scopes[1]
        let cell = Self.cell(0, 0, in: input, scope: first)
        XCTAssertEqual(cell.slot, .ambiguous)
        XCTAssertEqual(cell.text, "—")
        XCTAssertEqual(cell.fill, .blank)
        XCTAssertFalse(cell.isSelected)
        XCTAssertNil(input.tapAction(at: ExactScoreMapPosition10868(row: 0, column: 0), canSelect: true))
        XCTAssertEqual(input.choices(in: first).map(\.id), [Self.firstZeroZero, Self.firstOther, "constructed:second-0-0"])
        for original in input.choices(in: first) {
            XCTAssertEqual(input.selectAction(original, canSelect: true), .selectOriginal(scopeID: Self.firstID, originalID: original.id))
        }
        XCTAssertTrue(input.keyUse(first).unavailable)
        XCTAssertTrue(input.accessibilityMapValue(first).contains("Hull City 0, Everton 0: —"))
    }

    func testMalformedCoordinatesAndAxesKeepEveryOriginalReachable() {
        // A coordinate off the axes.
        let offAxis = Self.originals(1, placement: [Self.firstOneOne: .grid(home: 7, away: 0)])
        let a = Self.input(.before, scopes: [Self.scope(0), Self.scope(1, originals: offAxis)], scopeID: Self.firstID, originalID: Self.firstOneOne)
        XCTAssertEqual(a.choices(in: a.scopes[1]).map(\.id), [Self.firstOneOne, Self.firstOther])
        XCTAssertEqual(Self.cell(1, 1, in: a, scope: a.scopes[1]).slot, .notListed)
        XCTAssertEqual(a.selectAction(Self.original(Self.firstOneOne, in: a.scopes[1]), canSelect: true),
                       .selectOriginal(scopeID: Self.firstID, originalID: Self.firstOneOne))
        // An axis that names a goal count twice, or no axis at all: no map, every original named.
        let repeated = [ExactScoreMapGoal10868(value: 0, text: "0"), ExactScoreMapGoal10868(value: 1, text: "1"), ExactScoreMapGoal10868(value: 1, text: "1")]
        for scope in [Self.scope(1, rows: repeated), Self.scope(1, columns: [])] {
            let input = Self.input(.before, scopes: [Self.scope(0), scope], scopeID: Self.firstID, originalID: Self.firstZeroZero)
            XCTAssertFalse(input.hasGrid(input.scopes[1]))
            XCTAssertTrue(input.cells(input.scopes[1]).isEmpty)
            XCTAssertEqual(input.choices(in: input.scopes[1]).map(\.id), Self.archived.filter { $0.scope == 1 }.map(\.id))
            XCTAssertEqual(input.stepAction(1, canSelect: true), .selectOriginal(scopeID: Self.firstID, originalID: "244588608"))
        }
    }

    func testPreviousAndNextFollowTheOwnersOrderWithExactIdentities() {
        let first = Self.input(.before, originalID: Self.fullZeroZero)
        XCTAssertNil(first.stepAction(-1, canSelect: true))
        XCTAssertEqual(first.stepAction(1, canSelect: true), .selectOriginal(scopeID: Self.fullID, originalID: Self.fullZeroOne))
        let last = Self.input(.before, originalID: Self.fullOther)
        XCTAssertNil(last.stepAction(1, canSelect: true))
        XCTAssertEqual(last.stepAction(-1, canSelect: true), .selectOriginal(scopeID: Self.fullID, originalID: Self.fullFiveFive))
        XCTAssertNil(first.stepAction(2, canSelect: true))
        XCTAssertTrue(first.isAdjustable(canSelect: true))
    }

    func testEveryOriginalIsReachableWithItsExactIdentity() {
        var reached: [String] = []
        for (index, scopeID) in Self.scopeIDs.enumerated() {
            let input = Self.input(.final, scopeID: scopeID, originalID: nil)
            let scope = input.scopes[index]
            for original in scope.originals {
                let expected = ExactScoreMapAction10868.selectOriginal(scopeID: scopeID, originalID: original.id)
                if let position = input.position(original, in: scope) {
                    XCTAssertEqual(input.tapAction(at: position, canSelect: true), expected)
                } else {
                    XCTAssertTrue(input.choices(in: scope).contains(original))
                }
                XCTAssertEqual(input.selectAction(original, canSelect: true), expected)
                reached.append(original.id)
            }
            // Next from nothing, then Next again, walks every original in order.
            var walked: [String] = []
            var step = input.stepAction(1, canSelect: true)
            while case .selectOriginal(_, let id)? = step {
                walked.append(id)
                step = Self.input(.final, scopeID: scopeID, originalID: id).stepAction(1, canSelect: true)
            }
            XCTAssertEqual(walked, scope.originals.map(\.id))
        }
        XCTAssertEqual(Set(reached), Set(Self.archived.map(\.id)))
    }

    func testDetailsReturnTheExactScopeAndOriginal() {
        let input = Self.input(.final, scopeID: Self.firstID, originalID: Self.firstOther)
        XCTAssertEqual(input.detailsAction(canOpen: true), .details(scopeID: Self.firstID, originalID: Self.firstOther))
        XCTAssertNil(input.detailsAction(canOpen: false))
    }

    func testWithoutCallbacksNothingOffersAnAction() {
        let input = Self.input(.final)
        let full = input.scopes[0]
        XCTAssertNil(input.selectScopeAction(full, canSelect: false))
        XCTAssertNil(input.tapAction(at: ExactScoreMapPosition10868(row: 2, column: 2), canSelect: false))
        XCTAssertNil(input.selectAction(Self.original(Self.fullOther, in: full), canSelect: false))
        XCTAssertNil(input.stepAction(1, canSelect: false))
        XCTAssertFalse(input.showsSteps(canSelect: false))
        XCTAssertFalse(input.isAdjustable(canSelect: false))
        XCTAssertNil(input.detailsAction(canOpen: false))
        XCTAssertNil(Self.input(.final, originalID: nil).recoverAction(canRecover: false))
    }

    func testTheMapIsAdjustableOnlyWhenAStepCanNameAnExactOriginal() {
        XCTAssertTrue(Self.input(.final).isAdjustable(canSelect: true))
        XCTAssertFalse(Self.input(.final, originalID: "missing").isAdjustable(canSelect: true))
        let only = [Self.original(Self.twoTwo, in: Self.scope(0))]
        XCTAssertFalse(Self.input(.final, scopes: [Self.scope(0, originals: only), Self.scope(1)]).isAdjustable(canSelect: true))
    }

    func testTapsLandOnTheirOwnCell() {
        let size = CGSize(width: 240, height: 240)
        XCTAssertEqual(ExactScoreMapGeometry10868.position(at: CGPoint(x: 0, y: 0), rows: 6, columns: 6, in: size),
                       ExactScoreMapPosition10868(row: 0, column: 0))
        XCTAssertEqual(ExactScoreMapGeometry10868.position(at: CGPoint(x: 40, y: 0), rows: 6, columns: 6, in: size),
                       ExactScoreMapPosition10868(row: 0, column: 1))
        XCTAssertEqual(ExactScoreMapGeometry10868.position(at: CGPoint(x: 239.9, y: 239.9), rows: 6, columns: 6, in: size),
                       ExactScoreMapPosition10868(row: 5, column: 5))
        XCTAssertEqual(ExactScoreMapGeometry10868.position(at: CGPoint(x: 100, y: 90), rows: 3, columns: 3, in: size),
                       ExactScoreMapPosition10868(row: 1, column: 1))
        for point in [CGPoint(x: -1, y: 0), CGPoint(x: 240, y: 0), CGPoint(x: 0, y: 240), CGPoint(x: CGFloat.nan, y: 0)] {
            XCTAssertNil(ExactScoreMapGeometry10868.position(at: point, rows: 6, columns: 6, in: size))
        }
        XCTAssertNil(ExactScoreMapGeometry10868.position(at: .zero, rows: 6, columns: 6, in: .zero))
        XCTAssertNil(ExactScoreMapGeometry10868.position(at: .zero, rows: 0, columns: 6, in: size))
        XCTAssertEqual(ExactScoreMapGeometry10868.cellRect(ExactScoreMapPosition10868(row: 2, column: 3), rows: 6, columns: 6, in: size),
                       CGRect(x: 120, y: 80, width: 40, height: 40))
        XCTAssertNil(ExactScoreMapGeometry10868.cellRect(ExactScoreMapPosition10868(row: 6, column: 0), rows: 6, columns: 6, in: size))
    }

    // MARK: VoiceOver and strings

    func testSpokenTextNamesScoreScopeChanceClockAndPhaseReading() {
        let input = Self.input(.final)
        let full = input.scopes[0]
        let twoTwo = Self.original(Self.twoTwo, in: full)
        XCTAssertEqual(input.accessibilityLabel(twoTwo, in: full), "Hull City AFC 2 - 2 Everton FC, Full match")
        XCTAssertEqual(input.accessibilityMapLabel(full),
                       "Full match. Pregame chance · darker is higher. Rows: Hull City goals. Columns: Everton goals")
        XCTAssertEqual(input.accessibilityMapValue(full),
                       "Selected: Hull City AFC 2 - 2 Everton FC. Pregame chance: 4%, "
                       + "Polymarket · recorded 2026-10-10T23:32:09.737493+00:00; Final result: Won")
        XCTAssertEqual(input.spokenCoordinate(ExactScoreMapPosition10868(row: 2, column: 2), in: input.scopes[1]),
                       "Hull City 2, Everton 2")
        XCTAssertEqual(input.spokenCoordinate(ExactScoreMapPosition10868(row: 3, column: 0), in: input.scopes[1]), "")
        let other = Self.original(Self.fullOther, in: full)
        XCTAssertEqual(input.spokenComparisons(other),
                       "Pregame chance: 0.9%, Polymarket · recorded 2026-10-10T23:32:09.737493+00:00; Final result: Lost")
    }

    func testOwnerStringsAndIdentifiersAreVerbatim() {
        let long = ExactScoreMapOriginal10868(
            id: "constructed:long", label: "Kingston upon Hull City Association Football Club 4 – 4 Everton Football Club",
            placement: .nonGrid,
            pregame: .recorded(ExactScoreMapObservation10868(probability: 0.004, text: "<1%", detail: "constructed")),
            current: Self.liveUnavailable, result: Self.unconfirmed)
        let input = Self.input(.before, scopes: [Self.scope(0, originals: Self.originals(0) + [long]), Self.scope(1)],
                               originalID: "constructed:long")
        let full = input.scopes[0]
        XCTAssertEqual(input.choices(in: full).last?.label, long.label)
        XCTAssertEqual(input.comparisons(long).first?.reading, .figure(long.pregame.observation!))
        XCTAssertEqual(input.accessibilityLabel(long, in: full), "\(long.label), Full match")
        XCTAssertEqual(ExactScoreMapAccessibilityID10868.scope(Self.firstID), "exactScoreMap10868.scope.market:64002155")
        XCTAssertEqual(ExactScoreMapAccessibilityID10868.choice(Self.firstOther), "exactScoreMap10868.choice.244588610")
        XCTAssertEqual(ExactScoreMapAccessibilityID10868.map, "exactScoreMap10868.map")
    }

    // MARK: Geometry (arithmetic on constructed sizes)

    private static func sizes(_ count: Int, _ size: CGSize) -> [CGSize] {
        Array(repeating: size, count: count)
    }

    func testPhoneWidthsKeepEqualCellsAndAStableGutterWithoutPanning() {
        // CONSTRUCTED default-size extents: row labels 7 pt + 6 pt clearance,
        // column labels 16 pt + 4 pt clearance, figures up to 30 pt wide.
        var figures = Self.sizes(36, CGSize(width: 22, height: 16))
        figures[7] = CGSize(width: 30, height: 16)
        for width in [CGFloat(288), 343, 361] {   // 320 / 375 / 393 less 16 pt a side
            let plan = ExactScoreMapGeometry10868.plan(
                available: width, rowLabelSizes: Self.sizes(6, CGSize(width: 13, height: 16)),
                columnLabelSizes: Self.sizes(6, CGSize(width: 7, height: 20)), cellLabelSizes: figures, minimumCell: 40)!
            XCTAssertEqual(plan.cell, 40)
            XCTAssertEqual(plan.gutter, 13)
            XCTAssertEqual(plan.header, 20)
            XCTAssertEqual(plan.size, CGSize(width: 253, height: 260))
            XCTAssertFalse(plan.requiresPanning)
            XCTAssertTrue(plan.cellFrames.allSatisfy { $0.width == 40 && $0.height == 40 })
            for (index, frame) in plan.cellFrames.enumerated() {
                XCTAssertGreaterThanOrEqual(frame.width, figures[index].width + 8)
                XCTAssertGreaterThanOrEqual(frame.minX, plan.gutter)
            }
            for row in 0..<6 {
                XCTAssertEqual(plan.rowLabelFrames[row].minY, plan.cellFrames[row * 6].minY)
                XCTAssertEqual(plan.rowLabelFrames[row].maxX, plan.cellFrames[row * 6].minX)
            }
            for column in 0..<6 {
                XCTAssertEqual(plan.columnLabelFrames[column].midX, plan.cellFrames[column].midX)
                XCTAssertEqual(plan.columnLabelFrames[column].maxY, plan.cellFrames[column].minY)
            }
        }
    }

    func testEnlargedTypeGrowsEveryCellAndPansInsteadOfShrinking() {
        // CONSTRUCTED accessibility-size extents.
        let plan = ExactScoreMapGeometry10868.plan(
            available: 343, rowLabelSizes: Self.sizes(6, CGSize(width: 26, height: 34)),
            columnLabelSizes: Self.sizes(6, CGSize(width: 14, height: 40)),
            cellLabelSizes: Self.sizes(36, CGSize(width: 66, height: 34)), minimumCell: 76)!
        XCTAssertEqual(plan.cell, 76)
        XCTAssertEqual(plan.size.width, 26 + 6 * 76)
        XCTAssertTrue(plan.requiresPanning)
        XCTAssertTrue(plan.cellFrames.allSatisfy { $0.width >= 66 + 8 && $0.height >= 34 + 8 })
        // The first half's 3 × 3 at the same sizes still fits.
        let first = ExactScoreMapGeometry10868.plan(
            available: 343, rowLabelSizes: Self.sizes(3, CGSize(width: 26, height: 34)),
            columnLabelSizes: Self.sizes(3, CGSize(width: 14, height: 40)),
            cellLabelSizes: Self.sizes(9, CGSize(width: 66, height: 34)), minimumCell: 76)!
        XCTAssertFalse(first.requiresPanning)
        XCTAssertEqual(first.size.width, 26 + 3 * 76)
    }

    func testALongUnbreakableFigureWidensEveryCellAndReportsTheRequirement() {
        var figures = Self.sizes(36, CGSize(width: 22, height: 16))
        figures[20] = CGSize(width: 120, height: 16)
        let plan = ExactScoreMapGeometry10868.plan(
            available: 361, rowLabelSizes: Self.sizes(6, CGSize(width: 13, height: 16)),
            columnLabelSizes: Self.sizes(6, CGSize(width: 7, height: 20)), cellLabelSizes: figures, minimumCell: 40)!
        XCTAssertEqual(plan.cell, 128)
        XCTAssertTrue(plan.cellFrames.allSatisfy { $0.width == 128 && $0.height == 128 })
        XCTAssertEqual(plan.size.width, 13 + 6 * 128)
        XCTAssertTrue(plan.requiresPanning)
    }

    func testTallOrWideAxisLabelsStillGetSquareCells() {
        let plan = ExactScoreMapGeometry10868.plan(
            available: .infinity, rowLabelSizes: [CGSize(width: 13, height: 16), CGSize(width: 13, height: 50), CGSize(width: 13, height: 16)],
            columnLabelSizes: [CGSize(width: 7, height: 20), CGSize(width: 60, height: 20), CGSize(width: 7, height: 20)],
            cellLabelSizes: Self.sizes(9, CGSize(width: 22, height: 16)), minimumCell: 40)!
        XCTAssertEqual(plan.cell, 68)
        XCTAssertTrue(plan.cellFrames.allSatisfy { $0.width == $0.height })
        XCTAssertFalse(plan.requiresPanning)
        let tall = ExactScoreMapGeometry10868.plan(
            available: .infinity, rowLabelSizes: [CGSize(width: 13, height: 16), CGSize(width: 13, height: 50), CGSize(width: 13, height: 16)],
            columnLabelSizes: Self.sizes(3, CGSize(width: 7, height: 20)),
            cellLabelSizes: Self.sizes(9, CGSize(width: 22, height: 16)), minimumCell: 40)!
        XCTAssertEqual(tall.cell, 50)
    }

    func testMalformedPlanInputsPlaceNothing() {
        let row = CGSize(width: 13, height: 16)
        let column = CGSize(width: 7, height: 20)
        let figure = CGSize(width: 22, height: 16)
        XCTAssertNil(ExactScoreMapGeometry10868.plan(available: 300, rowLabelSizes: [], columnLabelSizes: [column], cellLabelSizes: [], minimumCell: 40))
        XCTAssertNil(ExactScoreMapGeometry10868.plan(available: 300, rowLabelSizes: [row], columnLabelSizes: [], cellLabelSizes: [], minimumCell: 40))
        XCTAssertNil(ExactScoreMapGeometry10868.plan(available: 300, rowLabelSizes: [row], columnLabelSizes: [column], cellLabelSizes: [figure, figure], minimumCell: 40))
        XCTAssertNil(ExactScoreMapGeometry10868.plan(available: 300, rowLabelSizes: [row], columnLabelSizes: [column], cellLabelSizes: [CGSize(width: CGFloat.nan, height: 16)], minimumCell: 40))
        XCTAssertNil(ExactScoreMapGeometry10868.plan(available: 300, rowLabelSizes: [row], columnLabelSizes: [column], cellLabelSizes: [CGSize(width: -1, height: 16)], minimumCell: 40))
        XCTAssertNil(ExactScoreMapGeometry10868.plan(available: 300, rowLabelSizes: [row], columnLabelSizes: [column], cellLabelSizes: [figure], minimumCell: 0))
        XCTAssertNil(ExactScoreMapGeometry10868.plan(available: 300, rowLabelSizes: [row], columnLabelSizes: [column], cellLabelSizes: [figure], minimumCell: .nan))
        let unbounded = ExactScoreMapGeometry10868.plan(available: .infinity, rowLabelSizes: [row], columnLabelSizes: [column], cellLabelSizes: [figure], minimumCell: 40)
        XCTAssertEqual(unbounded?.requiresPanning, false)
    }
}

/// #10868 — the tennis "Exact set finishes" card, composed from the map input
/// above, on the final only.
///
/// What is asserted is the rules the view defers to: which original each tile
/// shows, its chance and own result, the block rows, the unavailable cases,
/// the named originals no tile places, the exact selection, the action each
/// control carries, the spoken text and the tile arrangement's arithmetic.
/// Nothing here claims a rendered fit, an executed interaction or a VoiceOver pass.
///
/// ARCHIVED values come from Davidovich Fokina vs Tiafoe, event 15327291, as
/// copied in `shipping-adoption-20261027/TENNIS-EXACT-FINISH-RETAINED-CASES.json`:
/// Kalshi market 65129363, four originals with their fixture key, outcome id,
/// full outcome name, independent before reading (consensus, recorded
/// 2026-10-11T12:33:25.982332Z, before the verified 12:50:00Z start), is_winner,
/// resolution source and raw final quote (1 or null, observed
/// 2026-10-11T15:21:26.099516Z). The before readings sum to 1.005. Only the
/// Fokina 2–1 original won. The owner association table pairs each outcome id
/// with its player and set counts. The quote time is not a settlement or
/// match-end time.
///
/// CONSTRUCTED owner-resolved inputs (this leaf does not resolve them): the
/// owner action identities (copied from the packet's `constructed_owner_action_id`),
/// the scope and player identities, every display figure and its provenance
/// wording (readable local time: 12:33:25Z is 5:33 AM PDT), the result words,
/// the score, unit and spoken count words, the actual-score wording, the
/// headline and words, and every missing, zero, invalid, unconfirmed, malformed,
/// foreign, withdrawn, repeated, blank, three-sets-to-win and long-name case.
/// Every constructed identity starts with "constructed:". Geometry tests use
/// CONSTRUCTED sizes and are arithmetic only.
final class ExactScoreFinishPresentation10868Tests: XCTestCase {

    // MARK: Archived originals

    private struct Retained {
        let key: String
        let marketID: Int
        let outcomeID: String
        let name: String
        let before: Double
        let beforeAt: String
        let beforeKind: String
        let isWinner: Bool
        let resolutionSource: String
        /// The raw final quote; nil where the packet holds null.
        let finalQuote: Double?
        let finalQuoteAt: String
        /// CONSTRUCTED owner figure.
        let text: String
        /// CONSTRUCTED owner action identity, as written in the packet.
        let ownerID: String
    }

    private static let eventID = 15327291
    private static let start = "2026-10-11T12:50:00+00:00"

    /// In packet order (ARCHIVED except `text` and `ownerID`).
    private static let retained: [Retained] = [
        Retained(key: "tennis-final:other:8", marketID: 65129363, outcomeID: "244894447", name: "Alejandro Davidovich Fokina wins 2-1",
                 before: 0.195, beforeAt: "2026-10-11T12:33:25.982332+00:00", beforeKind: "consensus", isWinner: true,
                 resolutionSource: "api_settlement", finalQuote: 1.0, finalQuoteAt: "2026-10-11T15:21:26.099516+00:00",
                 text: "19.5%", ownerID: "constructed:15327291:kalshi:65129363:244894447"),
        Retained(key: "tennis-final:other:9", marketID: 65129363, outcomeID: "244894448", name: "Frances Tiafoe wins 2-1",
                 before: 0.21, beforeAt: "2026-10-11T12:33:25.982332+00:00", beforeKind: "consensus", isWinner: false,
                 resolutionSource: "api_settlement", finalQuote: nil, finalQuoteAt: "2026-10-11T15:21:26.099516+00:00",
                 text: "21%", ownerID: "constructed:15327291:kalshi:65129363:244894448"),
        Retained(key: "tennis-final:other:10", marketID: 65129363, outcomeID: "244894446", name: "Frances Tiafoe wins 2-0",
                 before: 0.305, beforeAt: "2026-10-11T12:33:25.982332+00:00", beforeKind: "consensus", isWinner: false,
                 resolutionSource: "api_settlement", finalQuote: nil, finalQuoteAt: "2026-10-11T15:21:26.099516+00:00",
                 text: "30.5%", ownerID: "constructed:15327291:kalshi:65129363:244894446"),
        Retained(key: "tennis-final:other:11", marketID: 65129363, outcomeID: "244894445", name: "Alejandro Davidovich Fokina wins 2-0",
                 before: 0.295, beforeAt: "2026-10-11T12:33:25.982332+00:00", beforeKind: "consensus", isWinner: false,
                 resolutionSource: "api_settlement", finalQuote: nil, finalQuoteAt: "2026-10-11T15:21:26.099516+00:00",
                 text: "29.5%", ownerID: "constructed:15327291:kalshi:65129363:244894445"),
    ]

    private struct Association {
        let player: String
        let winnerSets: Int
        let otherSets: Int
        let outcomeID: String
    }

    /// ARCHIVED explicit owner associations, in the packet's order.
    private static let associations: [Association] = [
        Association(player: "Alejandro Davidovich Fokina", winnerSets: 2, otherSets: 0, outcomeID: "244894445"),
        Association(player: "Alejandro Davidovich Fokina", winnerSets: 2, otherSets: 1, outcomeID: "244894447"),
        Association(player: "Frances Tiafoe", winnerSets: 2, otherSets: 0, outcomeID: "244894446"),
        Association(player: "Frances Tiafoe", winnerSets: 2, otherSets: 1, outcomeID: "244894448"),
    ]

    // MARK: Constructed owner inputs

    private static let scopeID = "constructed:scope:kalshi:65129363"
    private static let fokinaID = "constructed:player:davidovich-fokina"
    private static let tiafoeID = "constructed:player:tiafoe"
    private static let fokina = "Alejandro Davidovich Fokina"
    private static let tiafoe = "Frances Tiafoe"
    private static let fokinaTwoZero = "constructed:15327291:kalshi:65129363:244894445"
    private static let fokinaTwoOne = "constructed:15327291:kalshi:65129363:244894447"
    private static let tiafoeTwoZero = "constructed:15327291:kalshi:65129363:244894446"
    private static let tiafoeTwoOne = "constructed:15327291:kalshi:65129363:244894448"

    private static let won = ExactScoreMapResult10868.won("Won")
    private static let lost = ExactScoreMapResult10868.lost("Lost")
    private static let beforeDetail = "Kalshi · recorded Oct 11, 5:33 AM PDT, before the match"
    private static let finalScore = ExactScoreMapActual10868(title: "Final score", text: "Davidovich Fokina won 2–1 in sets · games 18–18")

    /// (player, tile) positions in the owner's order.
    private static let positions: [(Int, Int)] = [(0, 0), (0, 1), (1, 0), (1, 1)]

    private static let mapWords = ExactScoreMapWords10868(
        pregameTitle: "Pre-match chance",
        currentTitle: "Current chance",
        liveResultTitle: "Set result",
        finalResultTitle: "Final result",
        scopeUnavailable: "Exact match score unavailable.",
        noSelection: "Choose a finish to compare.",
        selectionUnavailable: "Selected finish unavailable.",
        recoverSelection: "View the listed finishes",
        mapUnavailable: "Score map unavailable.",
        scaleUnavailable: "Scale unavailable.",
        panHint: "Swipe sideways.",
        notListed: "Not listed",
        unavailableMark: "—",
        otherChoicesTitle: "Other listed outcomes",
        previous: "Previous finish",
        next: "Next finish",
        details: "Details",
        selectedSpoken: "Selected",
        selectScopeHint: "Shows this market's finishes",
        selectHint: "Shows this finish's chances",
        detailsHint: "Opens the original market"
    )

    /// CONSTRUCTED; required by the map input, unused by the finish card.
    private static let legend = ExactScoreMapLegend10868(
        scaleTitle: "Pre-match chance", offScale: "Hatched: outside the scale", notListed: "Dashed: not listed",
        unavailable: "—: no pre-match chance", result: "Outline: confirmed result", selection: "Corners: selected"
    )

    private static let words = ExactScoreFinishWords10868(
        countsKey: "Sets won · best of 3",
        countsNote: "Blocks count sets won by each player; they do not show playing order.",
        countsUnavailable: "Set blocks unavailable",
        finishUnavailable: "Finish unavailable",
        tapInvitation: "Tap a finish to compare it."
    )

    private static func observation(_ value: Double, _ text: String) -> ExactScoreMapObservation10868 {
        ExactScoreMapObservation10868(probability: value, text: text, detail: beforeDetail)
    }

    /// The raw final quote as an owner might pass it as the current reading —
    /// never a chance on this card.
    private static func finalQuote(_ r: Retained) -> ExactScoreMapCurrent10868 {
        guard let value = r.finalQuote else { return .unavailable("Current chance unavailable") }
        return .recorded(ExactScoreMapObservation10868(probability: value, text: "100%", detail: "Kalshi · Oct 11, 8:21 AM PDT"))
    }

    private static func original(_ r: Retained, pregame: ExactScoreMapPregame10868? = nil,
                                 result: ExactScoreMapResult10868? = nil) -> ExactScoreMapOriginal10868 {
        ExactScoreMapOriginal10868(
            id: r.ownerID,
            label: r.name,
            placement: .nonGrid,
            pregame: pregame ?? .recorded(observation(r.before, r.text)),
            current: finalQuote(r),
            result: result ?? (r.isWinner ? won : lost)
        )
    }

    /// A CONSTRUCTED original with every field explicit.
    private static func constructed(_ id: String, _ label: String, _ value: Double, _ text: String,
                                    result: ExactScoreMapResult10868) -> ExactScoreMapOriginal10868 {
        ExactScoreMapOriginal10868(id: id, label: label, placement: .nonGrid,
                                   pregame: .recorded(ExactScoreMapObservation10868(probability: value, text: text, detail: "constructed")),
                                   current: .unavailable("Current chance unavailable"), result: result)
    }

    /// The four retained originals in packet order.
    private static var originals: [ExactScoreMapOriginal10868] {
        retained.map { original($0) }
    }

    private static func counts(_ slots: Int, _ player: Int, _ opponent: Int) -> ExactScoreFinishSetCounts10868 {
        ExactScoreFinishSetCounts10868(slots: slots, player: player, opponent: opponent)
    }

    private static func tile(_ id: String?, _ score: String, _ counts: ExactScoreFinishSetCounts10868,
                             _ spoken: String, unit: String = "sets") -> ExactScoreFinishTile10868 {
        ExactScoreFinishTile10868(originalID: id, score: score, unit: unit, counts: counts, countsSpoken: spoken)
    }

    private static let fokinaTiles = [
        tile(fokinaTwoZero, "2–0", counts(2, 2, 0), "Alejandro Davidovich Fokina 2 sets, Frances Tiafoe 0 sets"),
        tile(fokinaTwoOne, "2–1", counts(2, 2, 1), "Alejandro Davidovich Fokina 2 sets, Frances Tiafoe 1 set"),
    ]

    private static let tiafoeTiles = [
        tile(tiafoeTwoZero, "2–0", counts(2, 2, 0), "Frances Tiafoe 2 sets, Alejandro Davidovich Fokina 0 sets"),
        tile(tiafoeTwoOne, "2–1", counts(2, 2, 1), "Frances Tiafoe 2 sets, Alejandro Davidovich Fokina 1 set"),
    ]

    private static func players(fokinaTiles first: [ExactScoreFinishTile10868] = fokinaTiles,
                                tiafoeTiles second: [ExactScoreFinishTile10868] = tiafoeTiles,
                                fokinaID firstID: String = fokinaID,
                                tiafoeID secondID: String = tiafoeID) -> [ExactScoreFinishPlayer10868] {
        [
            ExactScoreFinishPlayer10868(id: firstID, name: fokina, tiles: first),
            ExactScoreFinishPlayer10868(id: secondID, name: tiafoe, tiles: second),
        ]
    }

    private static func input(
        _ phase: ExactScoreMapPhase10868 = .final,
        originals list: [ExactScoreMapOriginal10868]? = nil,
        players groups: [ExactScoreFinishPlayer10868]? = nil,
        selected: String? = fokinaTwoOne,
        scopeID selectedScope: String? = scopeID,
        actual: ExactScoreMapActual10868?? = nil,
        extraScopes: [ExactScoreMapScope10868] = []
    ) -> ExactScoreFinishInput10868 {
        let scope = ExactScoreMapScope10868(
            id: scopeID, label: "Exact match score", rows: [], columns: [],
            originals: list ?? originals,
            scale: ExactScoreMapScale10868(lower: 0, upper: 1, ticks: []),
            actual: actual ?? finalScore
        )
        let map = ExactScoreMapInput10868(
            phase: phase, title: "Which finish happened?", intro: nil,
            homeLabel: fokina, awayLabel: tiafoe, rowsTitle: "", columnsTitle: "",
            scopes: [scope] + extraScopes, selectedScopeID: selectedScope, selectedOriginalID: selected,
            legend: legend, words: mapWords
        )
        return ExactScoreFinishInput10868(map: map, players: groups ?? players(), words: words)
    }

    private static func state(_ input: ExactScoreFinishInput10868, _ player: Int, _ tile: Int) -> ExactScoreFinishTileState10868? {
        input.state(input.players[player].tiles[tile], of: input.players[player])
    }

    private static func placed(_ input: ExactScoreFinishInput10868, _ player: Int, _ tile: Int) -> ExactScoreMapOriginal10868? {
        if case .placed(let original)? = state(input, player, tile) { return original }
        return nil
    }

    private static func value(_ input: ExactScoreFinishInput10868, _ player: Int, _ tile: Int) -> String {
        input.accessibilityValue(input.players[player].tiles[tile], of: input.players[player])
    }

    private static func label(_ input: ExactScoreFinishInput10868, _ player: Int, _ tile: Int) -> String {
        input.accessibilityLabel(input.players[player].tiles[tile], of: input.players[player])
    }

    private static func select(_ input: ExactScoreFinishInput10868, _ player: Int, _ tile: Int,
                               canSelect: Bool = true) -> ExactScoreMapAction10868? {
        input.selectAction(input.players[player].tiles[tile], of: input.players[player], canSelect: canSelect)
    }

    private static func selected(_ input: ExactScoreFinishInput10868, _ player: Int, _ tile: Int) -> Bool {
        input.isSelected(input.players[player].tiles[tile], of: input.players[player])
    }

    private static func retainedOwner(_ ownerID: String) -> Retained {
        let matches = retained.filter { $0.ownerID == ownerID }
        precondition(matches.count == 1, "not an archived identity: \(ownerID)")
        return matches[0]
    }

    // MARK: Retained originals

    func testTheFourRetainedOriginalsKeepTheirExactIdentitiesBaselinesAndOwnResults() {
        XCTAssertEqual(Self.retained.count, 4)
        XCTAssertEqual(Set(Self.retained.map(\.outcomeID)).count, 4)
        XCTAssertEqual(Set(Self.retained.map(\.key)).count, 4)
        for r in Self.retained {
            XCTAssertEqual(r.marketID, 65129363)
            XCTAssertEqual(r.ownerID, "constructed:\(Self.eventID):kalshi:\(r.marketID):\(r.outcomeID)")
            XCTAssertEqual(r.beforeKind, "consensus")
            XCTAssertEqual(r.beforeAt, "2026-10-11T12:33:25.982332+00:00")
            // Same UTC ISO-8601 shape, so string order is time order.
            XCTAssertLessThan(r.beforeAt, Self.start)
            XCTAssertEqual(r.resolutionSource, "api_settlement")
        }
        XCTAssertEqual(Self.retained.filter(\.isWinner).map(\.outcomeID), ["244894447"])
        let input = Self.input()
        let expected = [Self.fokinaTwoZero, Self.fokinaTwoOne, Self.tiafoeTwoZero, Self.tiafoeTwoOne]
        for (index, (player, tile)) in Self.positions.enumerated() {
            guard let original = Self.placed(input, player, tile) else { return XCTFail("\(player),\(tile) not placed") }
            XCTAssertEqual(original.id, expected[index])
            let r = Self.retainedOwner(expected[index])
            XCTAssertEqual(original.label, r.name)
            XCTAssertEqual(input.readings(original)?.chance,
                           ExactScoreMapComparison10868(title: "Pre-match chance", reading: .figure(Self.observation(r.before, r.text))))
            XCTAssertEqual(input.readings(original)?.result,
                           ExactScoreMapComparison10868(title: "Final result", reading: .result(r.isWinner ? Self.won : Self.lost)))
        }
    }

    func testEachFinishSitsUnderItsOwnersPlayerInTheOwnersOrderNotByChance() {
        let input = Self.input()
        XCTAssertEqual(input.players.map(\.name), [Self.fokina, Self.tiafoe])
        var placed: [(player: String, id: String)] = []
        for player in input.players {
            for tile in player.tiles {
                if case .placed(let original)? = input.state(tile, of: player) { placed.append((player.name, original.id)) }
            }
        }
        XCTAssertEqual(placed.map { $0.player }, Self.associations.map(\.player))
        XCTAssertEqual(placed.map { $0.id }, Self.associations.map { "constructed:15327291:kalshi:65129363:\($0.outcomeID)" })
        let tiles = input.players.flatMap(\.tiles)
        XCTAssertEqual(tiles.map(\.counts.player), Self.associations.map(\.winnerSets))
        XCTAssertEqual(tiles.map(\.counts.opponent), Self.associations.map(\.otherSets))
        let chances = Self.positions.compactMap { Self.placed(input, $0.0, $0.1)?.pregame.observation?.probability }
        XCTAssertEqual(chances, [0.295, 0.195, 0.305, 0.21])
        XCTAssertNotEqual(chances, chances.sorted(by: >))
        // The scope keeps the packet's order and every original is on a tile.
        XCTAssertEqual(input.scope?.originals.map(\.id), Self.retained.map(\.ownerID))
        XCTAssertTrue(input.unplaced.isEmpty)
    }

    func testTheIndependentChancesSumToOneHundredPointFivePercentAndEachIsKept() {
        XCTAssertEqual(Self.retained.map(\.before).reduce(0, +), 1.005, accuracy: 1e-12)
        let input = Self.input()
        var sum = 0.0
        var texts: [String] = []
        for (player, tile) in Self.positions {
            guard let original = Self.placed(input, player, tile),
                  case .figure(let observation)? = input.readings(original)?.chance.reading else { return XCTFail() }
            sum += observation.probability
            texts.append(observation.text)
            XCTAssertEqual(observation.probability, Self.retainedOwner(original.id).before)
        }
        XCTAssertEqual(sum, 1.005, accuracy: 1e-12)
        XCTAssertEqual(texts, ["29.5%", "19.5%", "30.5%", "21%"])
    }

    // MARK: Results and actual score

    func testEachTileGradesOnlyItsOwnOriginalAndTheActualScoreChangesNothing() {
        let base = Self.input()
        let other = Self.input(actual: .some(ExactScoreMapActual10868(title: "Final score", text: "Tiafoe won 2–0 in sets")))
        let none = Self.input(actual: .some(nil))
        for input in [other, none] {
            for (player, tile) in Self.positions {
                XCTAssertEqual(Self.state(input, player, tile), Self.state(base, player, tile))
                XCTAssertEqual(Self.selected(input, player, tile), Self.selected(base, player, tile))
                XCTAssertEqual(Self.value(input, player, tile), Self.value(base, player, tile))
            }
            XCTAssertEqual(input.selection, base.selection)
        }
        XCTAssertEqual(base.visibleActual, Self.finalScore)
        XCTAssertNil(none.visibleActual)
        let marks = Self.positions.map { position -> ExactScoreMapResultMark10868? in
            guard let original = Self.placed(base, position.0, position.1),
                  case .result(let result)? = base.readings(original)?.result.reading else { return nil }
            return result.mark
        }
        XCTAssertEqual(marks, [.lost, .won, .lost, .lost])
        for (player, tile) in Self.positions {
            let spoken = Self.value(base, player, tile)
            XCTAssertFalse(spoken.contains("18–18"))
            XCTAssertFalse(spoken.contains("Final score"))
            XCTAssertFalse(spoken.contains("22.5"))
        }
    }

    func testAnUnconfirmedOrOtherGradeIsNeverALoss() {
        var list = Self.originals
        list[1] = Self.original(Self.retained[1], result: .unconfirmed("Result unconfirmed"))   // Tiafoe 2–1
        list[2] = Self.original(Self.retained[2], result: .other("Void"))                      // Tiafoe 2–0
        let input = Self.input(originals: list)
        guard let twoOne = Self.placed(input, 1, 1), let twoZero = Self.placed(input, 1, 0) else { return XCTFail() }
        XCTAssertEqual(input.readings(twoOne)?.result.reading, .result(.unconfirmed("Result unconfirmed")))
        XCTAssertEqual(input.readings(twoZero)?.result.reading, .result(.other("Void")))
        XCTAssertNil(ExactScoreMapResult10868.unconfirmed("Result unconfirmed").mark)
        XCTAssertNil(ExactScoreMapResult10868.other("Void").mark)
        XCTAssertTrue(Self.value(input, 1, 1).hasSuffix("Final result: Result unconfirmed"))
        XCTAssertFalse(Self.value(input, 1, 1).contains("Lost"))
        XCTAssertTrue(Self.value(input, 1, 0).hasSuffix("Final result: Void"))
    }

    func testTheRawFinalQuoteNeverBecomesAPreMatchChanceOrAResult() {
        let r = Self.retained[0]   // Fokina 2–1
        XCTAssertEqual(r.finalQuote, 1.0)
        XCTAssertEqual(Self.retained.filter { $0.finalQuote == nil }.count, 3)
        let input = Self.input()
        guard let twoOne = Self.placed(input, 0, 1) else { return XCTFail() }
        XCTAssertEqual(twoOne.current, .recorded(ExactScoreMapObservation10868(probability: 1, text: "100%", detail: "Kalshi · Oct 11, 8:21 AM PDT")))
        XCTAssertEqual(input.readings(twoOne)?.chance.reading, .figure(Self.observation(0.195, "19.5%")))
        // A quote of 1 does not grade: with the grade still pending it stays pending.
        var list = Self.originals
        list[0] = Self.original(r, result: .unconfirmed("Result unconfirmed"))
        let pending = Self.input(originals: list)
        guard let pendingTwoOne = Self.placed(pending, 0, 1) else { return XCTFail() }
        XCTAssertEqual(pending.readings(pendingTwoOne)?.result.reading, .result(.unconfirmed("Result unconfirmed")))
        for card in [input, pending] {
            for (player, tile) in Self.positions {
                let spoken = Self.value(card, player, tile)
                XCTAssertFalse(spoken.contains("100%"))
                XCTAssertFalse(spoken.contains("Current chance"))
                XCTAssertFalse(spoken.contains("8:21"))
            }
            XCTAssertFalse(card.accessibilitySummary(Self.placed(card, 0, 1)!).contains("100%"))
        }
    }

    func testMissingZeroAndInvalidPreMatchReadingsKeepTheOwnersWordsAndTheTile() {
        var list = Self.originals
        list[3] = Self.original(Self.retained[3], pregame: .unavailable("Pre-match chance unavailable"))   // Fokina 2–0
        list[2] = Self.original(Self.retained[2], pregame: .recorded(Self.observation(0, "0%")))           // Tiafoe 2–0
        list[1] = Self.original(Self.retained[1], pregame: .recorded(Self.observation(.nan, "21%")))       // Tiafoe 2–1, CONSTRUCTED invalid raw value
        let input = Self.input(originals: list)
        guard let missing = Self.placed(input, 0, 0), let zero = Self.placed(input, 1, 0),
              let invalid = Self.placed(input, 1, 1) else { return XCTFail() }
        XCTAssertEqual(input.readings(missing)?.chance,
                       ExactScoreMapComparison10868(title: "Pre-match chance", reading: .words("Pre-match chance unavailable")))
        XCTAssertEqual(input.readings(missing)?.result.reading, .result(Self.lost))
        XCTAssertEqual(input.readings(zero)?.chance.reading, .figure(Self.observation(0, "0%")))
        guard case .figure(let shown)? = input.readings(invalid)?.chance.reading else { return XCTFail() }
        XCTAssertEqual(shown.text, "21%")
        XCTAssertTrue(shown.probability.isNaN)
        for (player, tile) in Self.positions {
            XCTAssertNotNil(Self.select(input, player, tile))
        }
        XCTAssertTrue(input.unplaced.isEmpty)
        XCTAssertEqual(Self.value(input, 0, 0),
                       "Alejandro Davidovich Fokina 2 sets, Frances Tiafoe 0 sets; Pre-match chance: Pre-match chance unavailable; Final result: Lost")
    }

    // MARK: Phases

    func testBeforeAndDuringTheFinishCardShowsNothingAndTheMapLifecycleIsUnchanged() {
        for phase in [ExactScoreMapPhase10868.before, .during] {
            let input = Self.input(phase)
            XCTAssertFalse(input.isShown)
            XCTAssertNil(input.scope)
            XCTAssertNil(input.visibleActual)
            XCTAssertTrue(input.unplaced.isEmpty)
            XCTAssertEqual(input.selection, .unselected)
            XCTAssertNil(input.detailsAction(canOpen: true))
            XCTAssertNil(input.recoverAction(canRecover: true))
            XCTAssertFalse(input.showsTapInvitation(canSelect: true))
            for (player, tile) in Self.positions {
                XCTAssertNil(Self.state(input, player, tile))
                XCTAssertNil(Self.select(input, player, tile))
                XCTAssertFalse(Self.selected(input, player, tile))
                XCTAssertEqual(Self.label(input, player, tile), "")
                XCTAssertEqual(Self.value(input, player, tile), "")
            }
            for original in Self.originals {
                XCTAssertTrue(input.comparisons(original).isEmpty)
                XCTAssertNil(input.readings(original))
                XCTAssertNil(input.choiceAction(original, canSelect: true))
                XCTAssertEqual(input.accessibilitySummary(original), "")
            }
        }
        // The wrapped map keeps its own lifecycle readings.
        let twoOne = Self.originals[0]
        let before = Self.input(.before).map
        XCTAssertEqual(before.comparisons(twoOne), [ExactScoreMapComparison10868(title: "Pre-match chance", reading: .figure(twoOne.pregame.observation!))])
        XCTAssertNil(before.visibleActual(before.scopes[0]))
        let during = Self.input(.during).map
        XCTAssertEqual(during.comparisons(twoOne)[1], ExactScoreMapComparison10868(title: "Set result", reading: .result(Self.won)))
        XCTAssertTrue(Self.input(.final).isShown)
    }

    func testAMissingOrRepeatedScopeShowsNoFinish() {
        let missing = Self.input(scopeID: "constructed:scope:missing")
        let unselected = Self.input(scopeID: nil)
        let repeatedScope = ExactScoreMapScope10868(id: Self.scopeID, label: "Exact match score (constructed repeat)", rows: [], columns: [],
                                                    originals: Self.originals, scale: ExactScoreMapScale10868(lower: 0, upper: 1, ticks: []),
                                                    actual: nil)
        let repeated = Self.input(extraScopes: [repeatedScope])
        for input in [missing, unselected, repeated] {
            XCTAssertTrue(input.isShown)
            XCTAssertNil(input.scope)
            XCTAssertTrue(input.unplaced.isEmpty)
            XCTAssertFalse(input.showsTapInvitation(canSelect: true))
            for (player, tile) in Self.positions { XCTAssertNil(Self.state(input, player, tile)) }
        }
    }

    // MARK: Set-count blocks

    func testTwoSetsToWinBlocksCountSetsAndNeverDecideAGrade() {
        XCTAssertEqual(Self.counts(2, 2, 0).blocks, [[.player, .player], [.empty, .empty]])
        XCTAssertEqual(Self.counts(2, 2, 1).blocks, [[.player, .player], [.opponent, .empty]])
        // Swapping the drawn counts between Fokina's tiles moves the blocks only.
        let swapped = [
            Self.tile(Self.fokinaTwoZero, "2–0", Self.counts(2, 2, 1), "constructed swapped counts"),
            Self.tile(Self.fokinaTwoOne, "2–1", Self.counts(2, 2, 0), "constructed swapped counts"),
        ]
        let base = Self.input()
        let moved = Self.input(players: Self.players(fokinaTiles: swapped))
        for (player, tile) in Self.positions {
            XCTAssertEqual(Self.state(moved, player, tile), Self.state(base, player, tile))
            XCTAssertEqual(Self.select(moved, player, tile), Self.select(base, player, tile))
        }
        XCTAssertEqual(moved.selection, base.selection)
        XCTAssertEqual(moved.players[0].tiles[0].counts.blocks, [[.player, .player], [.opponent, .empty]])
        XCTAssertEqual(base.words.countsNote, "Blocks count sets won by each player; they do not show playing order.")
    }

    func testThreeSetsToWinGeometryDrawsThreeBlocksARowAndPlacesEveryFinish() {
        XCTAssertEqual(Self.counts(3, 3, 0).blocks, [[.player, .player, .player], [.empty, .empty, .empty]])
        XCTAssertEqual(Self.counts(3, 3, 1).blocks, [[.player, .player, .player], [.opponent, .empty, .empty]])
        XCTAssertEqual(Self.counts(3, 3, 2).blocks, [[.player, .player, .player], [.opponent, .opponent, .empty]])
        // CONSTRUCTED best-of-five card: six originals, two players, three finishes each.
        let ids = ["a-3-0", "a-3-1", "a-3-2", "b-3-0", "b-3-1", "b-3-2"].map { "constructed:best-of-five:\($0)" }
        let list = ids.map { Self.constructed($0, "Constructed \($0)", 0.1, "10%", result: Self.lost) }
        func finishes(_ offset: Int) -> [ExactScoreFinishTile10868] {
            (0..<3).map { Self.tile(ids[offset + $0], "3–\($0)", Self.counts(3, 3, $0), "constructed counts") }
        }
        let groups = [
            ExactScoreFinishPlayer10868(id: "constructed:player:a", name: "Constructed Player A", tiles: finishes(0)),
            ExactScoreFinishPlayer10868(id: "constructed:player:b", name: "Constructed Player B", tiles: finishes(3)),
        ]
        let base = Self.input(originals: list, players: groups, selected: nil)
        let input = ExactScoreFinishInput10868(map: base.map, players: base.players, words: ExactScoreFinishWords10868(
            countsKey: "Sets won · best of 5", countsNote: base.words.countsNote, countsUnavailable: base.words.countsUnavailable,
            finishUnavailable: base.words.finishUnavailable, tapInvitation: base.words.tapInvitation))
        var placed: [String] = []
        for player in input.players {
            for tile in player.tiles {
                guard case .placed(let original)? = input.state(tile, of: player) else { return XCTFail() }
                placed.append(original.id)
                XCTAssertNotNil(tile.counts.blocks)
            }
        }
        XCTAssertEqual(placed, ids)
        XCTAssertTrue(input.unplaced.isEmpty)
        XCTAssertEqual(input.words.countsKey, "Sets won · best of 5")
    }

    func testMalformedBlockCountsDrawNoBlocksButKeepTheFinish() {
        let malformed = [Self.counts(1, 1, 0), Self.counts(4, 4, 0), Self.counts(0, 0, 0), Self.counts(2, 1, 0),
                         Self.counts(2, 2, 2), Self.counts(2, 2, -1), Self.counts(3, 2, 1), Self.counts(-2, -2, 0)]
        for counts in malformed { XCTAssertNil(counts.blocks, "\(counts)") }
        let bad = [Self.tile(Self.fokinaTwoZero, "2–0", Self.counts(4, 4, 0), "constructed malformed counts"), Self.fokinaTiles[1]]
        let input = Self.input(players: Self.players(fokinaTiles: bad))
        guard let original = Self.placed(input, 0, 0) else { return XCTFail() }
        XCTAssertEqual(original.id, Self.fokinaTwoZero)
        XCTAssertEqual(input.readings(original)?.chance.reading, .figure(Self.observation(0.295, "29.5%")))
        XCTAssertEqual(input.readings(original)?.result.reading, .result(Self.lost))
        XCTAssertNotNil(Self.select(input, 0, 0))
        XCTAssertEqual(Self.value(input, 0, 0),
                       "Set blocks unavailable; Pre-match chance: 29.5%, \(Self.beforeDetail); Final result: Lost")
    }

    // MARK: Associations

    func testAnOriginalNoTileNamesStaysNamedAndReachable() {
        let extra = Self.constructed("constructed:original:unassociated", "Constructed unassociated outcome", 0.01, "1%", result: .other("Void"))
        let input = Self.input(originals: Self.originals + [extra])
        XCTAssertEqual(input.unplaced, [extra])
        XCTAssertEqual(input.choiceAction(extra, canSelect: true), .selectOriginal(scopeID: Self.scopeID, originalID: extra.id))
        for (player, tile) in Self.positions { XCTAssertNotNil(Self.placed(input, player, tile)) }
        let held = Self.input(originals: Self.originals + [extra], selected: extra.id)
        XCTAssertTrue(held.isSelected(extra))
        for (player, tile) in Self.positions { XCTAssertFalse(Self.selected(held, player, tile)) }
        XCTAssertEqual(held.detailsAction(canOpen: true), .details(scopeID: Self.scopeID, originalID: extra.id))
    }

    func testAFinishTheOwnerListsNoOriginalForIsShownAsNotListed() {
        let tiles = [Self.tiafoeTiles[0], Self.tile(nil, "2–1", Self.counts(2, 2, 1), "Frances Tiafoe 2 sets, Alejandro Davidovich Fokina 1 set")]
        let input = Self.input(players: Self.players(tiafoeTiles: tiles))
        XCTAssertEqual(Self.state(input, 1, 1), .notListed("Not listed"))
        XCTAssertNil(Self.select(input, 1, 1))
        XCTAssertEqual(Self.label(input, 1, 1), "Frances Tiafoe, 2–1 sets")
        XCTAssertEqual(Self.value(input, 1, 1), "Not listed")
        // Its original is not dropped: it is named below the groups.
        XCTAssertEqual(input.unplaced.map(\.id), [Self.tiafoeTwoOne])
    }

    func testBlankForeignWithdrawnTwiceClaimedAndRepeatedOriginalsAttachNothing() {
        func fokinaTiles(_ firstID: String) -> [ExactScoreFinishTile10868] {
            [Self.tile(firstID, "2–0", Self.counts(2, 2, 0), "constructed counts"), Self.fokinaTiles[1]]
        }
        let unavailable = ExactScoreFinishTileState10868.unavailable("Finish unavailable")
        // Blank and whitespace identities.
        for blank in ["", "  "] {
            let input = Self.input(players: Self.players(fokinaTiles: fokinaTiles(blank)))
            XCTAssertEqual(Self.state(input, 0, 0), unavailable)
            XCTAssertEqual(input.unplaced.map(\.id), [Self.fokinaTwoZero])
        }
        // Foreign: an identity held only by another scope.
        let foreignID = "constructed:other-scope:244894445"
        let otherScope = ExactScoreMapScope10868(
            id: "constructed:scope:other", label: "Constructed other market", rows: [], columns: [],
            originals: [Self.constructed(foreignID, "Constructed foreign outcome", 0.3, "30%", result: Self.lost)],
            scale: ExactScoreMapScale10868(lower: 0, upper: 1, ticks: []), actual: nil)
        let foreign = Self.input(players: Self.players(fokinaTiles: fokinaTiles(foreignID)), extraScopes: [otherScope])
        XCTAssertEqual(Self.state(foreign, 0, 0), unavailable)
        XCTAssertEqual(foreign.unplaced.map(\.id), [Self.fokinaTwoZero])
        // Withdrawn: the original has left the scope.
        let withdrawn = Self.input(originals: Self.originals.filter { $0.id != Self.fokinaTwoZero })
        XCTAssertEqual(Self.state(withdrawn, 0, 0), unavailable)
        XCTAssertTrue(withdrawn.unplaced.isEmpty)
        // Claimed by two tiles: neither shows it, both stay unavailable.
        let twice = [Self.tile(Self.fokinaTwoZero, "2–0", Self.counts(2, 2, 0), "constructed counts"), Self.tiafoeTiles[1]]
        let claimed = Self.input(players: Self.players(tiafoeTiles: twice))
        XCTAssertEqual(Self.state(claimed, 0, 0), unavailable)
        XCTAssertEqual(Self.state(claimed, 1, 0), unavailable)
        XCTAssertEqual(claimed.unplaced.map(\.id), [Self.tiafoeTwoZero, Self.fokinaTwoZero])
        // Repeated in the scope: no tile and no choice can name it.
        let copy = Self.constructed(Self.fokinaTwoZero, "Constructed second listing", 0.4, "40%", result: Self.lost)
        let repeated = Self.input(originals: Self.originals + [copy])
        XCTAssertEqual(Self.state(repeated, 0, 0), unavailable)
        XCTAssertEqual(repeated.unplaced.map(\.label), ["Alejandro Davidovich Fokina wins 2-0", "Constructed second listing"])
        for original in repeated.unplaced { XCTAssertNil(repeated.choiceAction(original, canSelect: true)) }
        // Never moved to a neighbour.
        for input in [foreign, withdrawn, repeated] {
            XCTAssertEqual(Self.placed(input, 0, 1)?.id, Self.fokinaTwoOne)
            XCTAssertEqual(Self.placed(input, 1, 0)?.id, Self.tiafoeTwoZero)
            XCTAssertEqual(Self.placed(input, 1, 1)?.id, Self.tiafoeTwoOne)
            XCTAssertNil(Self.select(input, 0, 0))
        }
    }

    func testBlankOrRepeatedPlayerIdentitiesPlaceNoFinish() {
        let unavailable = ExactScoreFinishTileState10868.unavailable("Finish unavailable")
        let blank = Self.input(players: Self.players(fokinaID: ""))
        XCTAssertEqual(Self.state(blank, 0, 0), unavailable)
        XCTAssertEqual(Self.state(blank, 0, 1), unavailable)
        XCTAssertEqual(Self.placed(blank, 1, 0)?.id, Self.tiafoeTwoZero)
        XCTAssertEqual(blank.unplaced.map(\.id), [Self.fokinaTwoOne, Self.fokinaTwoZero])
        let same = "constructed:player:same"
        let repeated = Self.input(players: Self.players(fokinaID: same, tiafoeID: same))
        for (player, tile) in Self.positions { XCTAssertEqual(Self.state(repeated, player, tile), unavailable) }
        XCTAssertEqual(repeated.unplaced.map(\.id), Self.retained.map(\.ownerID))
        for original in repeated.unplaced {
            XCTAssertEqual(repeated.choiceAction(original, canSelect: true), .selectOriginal(scopeID: Self.scopeID, originalID: original.id))
        }
    }

    // MARK: Selection and actions

    func testAHeldWithdrawnRepeatedOrBlankSelectionElectsNothing() {
        let withdrawn = Self.input(originals: Self.originals.filter { $0.id != Self.fokinaTwoOne })
        let copy = Self.constructed(Self.fokinaTwoOne, "Constructed second listing", 0.2, "20%", result: Self.lost)
        let repeated = Self.input(originals: Self.originals + [copy])
        let blankOriginal = Self.constructed("", "Constructed blank identity", 0.2, "20%", result: Self.lost)
        let blank = Self.input(originals: Self.originals + [blankOriginal], selected: "")
        XCTAssertEqual(withdrawn.selection, .missing(Self.fokinaTwoOne))
        XCTAssertEqual(repeated.selection, .duplicate(Self.fokinaTwoOne))
        XCTAssertEqual(blank.selection, .missing(""))
        for input in [withdrawn, repeated, blank] {
            for (player, tile) in Self.positions { XCTAssertFalse(Self.selected(input, player, tile)) }
            XCTAssertNil(input.detailsAction(canOpen: true))
            XCTAssertEqual(input.recoverAction(canRecover: true), .recover)
            XCTAssertNil(input.recoverAction(canRecover: false))
        }
        XCTAssertEqual(withdrawn.recoverAction(canRecover: true), withdrawn.map.recoverAction(canRecover: true))
        XCTAssertEqual(Self.state(withdrawn, 0, 1), .unavailable("Finish unavailable"))
        XCTAssertTrue(blank.unplaced.contains(blankOriginal))
        XCTAssertNil(blank.choiceAction(blankOriginal, canSelect: true))
        // Nothing selected: nothing is chosen for the reader.
        let none = Self.input(selected: nil)
        XCTAssertEqual(none.selection, .unselected)
        for (player, tile) in Self.positions { XCTAssertFalse(Self.selected(none, player, tile)) }
        XCTAssertNil(none.detailsAction(canOpen: true))
        XCTAssertEqual(none.recoverAction(canRecover: true), none.map.recoverAction(canRecover: true))
        // Restored, the exact original is held again on exactly one tile.
        let restored = Self.input()
        XCTAssertEqual(restored.selection.original?.id, Self.fokinaTwoOne)
        XCTAssertEqual(Self.positions.filter { Self.selected(restored, $0.0, $0.1) }.map { "\($0.0),\($0.1)" }, ["0,1"])
    }

    func testSelectionAndDetailsUseTheMapsOwnHelpersAndHandBackExactIdentities() {
        let input = Self.input(selected: Self.tiafoeTwoZero)
        for (player, tile) in Self.positions {
            guard let original = Self.placed(input, player, tile) else { return XCTFail() }
            let action = Self.select(input, player, tile)
            XCTAssertEqual(action, input.map.selectAction(original, canSelect: true))
            XCTAssertEqual(action, .selectOriginal(scopeID: Self.scopeID, originalID: original.id))
        }
        XCTAssertEqual(input.detailsAction(canOpen: true), input.map.detailsAction(canOpen: true))
        XCTAssertEqual(input.detailsAction(canOpen: true), .details(scopeID: Self.scopeID, originalID: Self.tiafoeTwoZero))
        var selections: [String] = []
        var details: [String] = []
        var recoveries = 0
        let onSelect: (String, String) -> Void = { selections.append("\($0)|\($1)") }
        let onDetails: (String, String) -> Void = { details.append("\($0)|\($1)") }
        let onRecover: () -> Void = { recoveries += 1 }
        ExactScoreFinishRouting10868.route(Self.select(input, 0, 1), onSelectOriginal: onSelect, onDetails: onDetails, onRecoverSelection: onRecover)
        ExactScoreFinishRouting10868.route(input.detailsAction(canOpen: true), onSelectOriginal: onSelect, onDetails: onDetails, onRecoverSelection: onRecover)
        ExactScoreFinishRouting10868.route(Self.input(selected: nil).recoverAction(canRecover: true), onSelectOriginal: onSelect,
                                           onDetails: onDetails, onRecoverSelection: onRecover)
        XCTAssertEqual(selections, ["\(Self.scopeID)|\(Self.fokinaTwoOne)"])
        XCTAssertEqual(details, ["\(Self.scopeID)|\(Self.tiafoeTwoZero)"])
        XCTAssertEqual(recoveries, 1)
    }

    func testWithoutCallbacksEveryTileIsStaticAndNoTapIsAskedFor() {
        let extra = Self.constructed("constructed:original:unassociated", "Constructed unassociated outcome", 0.01, "1%", result: Self.lost)
        let input = Self.input(originals: Self.originals + [extra])
        for (player, tile) in Self.positions { XCTAssertNil(Self.select(input, player, tile, canSelect: false)) }
        XCTAssertNil(input.choiceAction(extra, canSelect: false))
        XCTAssertFalse(input.showsTapInvitation(canSelect: false))
        XCTAssertNil(input.detailsAction(canOpen: false))
        XCTAssertNil(Self.input(selected: nil).recoverAction(canRecover: false))
        // An action with no callback reaches nothing.
        ExactScoreFinishRouting10868.route(.selectOriginal(scopeID: Self.scopeID, originalID: Self.fokinaTwoOne),
                                           onSelectOriginal: nil, onDetails: nil, onRecoverSelection: nil)
    }

    func testTheTapInvitationNeedsAShownControlThatCanAct() {
        XCTAssertTrue(Self.input().showsTapInvitation(canSelect: true))
        let foreignTiles = (1...4).map { Self.tile("constructed:foreign:\($0)", "2–0", Self.counts(2, 2, 0), "constructed counts") }
        let foreign = Self.players(fokinaTiles: Array(foreignTiles[0..<2]), tiafoeTiles: Array(foreignTiles[2..<4]))
        // A callback, but no shown tile or named original can act.
        let empty = Self.input(originals: [], players: foreign)
        XCTAssertFalse(empty.showsTapInvitation(canSelect: true))
        let doubled = Self.input(originals: Self.originals + Self.originals)
        XCTAssertEqual(doubled.unplaced.count, 8)
        XCTAssertFalse(doubled.showsTapInvitation(canSelect: true))
        // One actionable named original is enough.
        let extra = Self.constructed("constructed:original:unassociated", "Constructed unassociated outcome", 0.01, "1%", result: Self.lost)
        XCTAssertTrue(Self.input(originals: [extra], players: foreign).showsTapInvitation(canSelect: true))
    }

    func testNothingIsCalledPassively() {
        var calls = 0
        let onSelect: (String, String) -> Void = { _, _ in calls += 1 }
        let onDetails: (String, String) -> Void = { _, _ in calls += 1 }
        let onRecover: () -> Void = { calls += 1 }
        ExactScoreFinishRouting10868.route(nil, onSelectOriginal: onSelect, onDetails: onDetails, onRecoverSelection: onRecover)
        ExactScoreFinishRouting10868.route(.selectScope(Self.scopeID), onSelectOriginal: onSelect, onDetails: onDetails, onRecoverSelection: onRecover)
        XCTAssertEqual(calls, 0)
        // A refreshed input with a changed figure keeps the same held tile.
        var list = Self.originals
        list[3] = Self.original(Self.retained[3], pregame: .recorded(Self.observation(0.295, "29.5% (refreshed)")))
        let refreshed = Self.input(originals: list)
        XCTAssertEqual(refreshed.selection, Self.input().selection)
        XCTAssertTrue(Self.selected(refreshed, 0, 1))
    }

    // MARK: VoiceOver and strings

    func testSpokenTextSeparatesCountsChanceClockAndOwnResultFromTheActualScore() {
        let input = Self.input()
        XCTAssertEqual(Self.label(input, 0, 1), "Alejandro Davidovich Fokina wins 2-1, Exact match score")
        XCTAssertEqual(Self.value(input, 0, 1),
                       "Alejandro Davidovich Fokina 2 sets, Frances Tiafoe 1 set; "
                       + "Pre-match chance: 19.5%, Kalshi · recorded Oct 11, 5:33 AM PDT, before the match; Final result: Won")
        XCTAssertEqual(Self.value(input, 1, 0),
                       "Frances Tiafoe 2 sets, Alejandro Davidovich Fokina 0 sets; "
                       + "Pre-match chance: 30.5%, Kalshi · recorded Oct 11, 5:33 AM PDT, before the match; Final result: Lost")
        XCTAssertEqual(input.accessibilitySummary(Self.placed(input, 0, 1)!),
                       "Pre-match chance: 19.5%, Kalshi · recorded Oct 11, 5:33 AM PDT, before the match; Final result: Won. "
                       + "Final score: Davidovich Fokina won 2–1 in sets · games 18–18")
    }

    func testOwnerStringsLongNamesAndIdentifiersAreVerbatim() {
        let longName = "Alejandro Davidovich Fokina de la Constructed Extraordinarily Long Surname"
        let groups = [
            ExactScoreFinishPlayer10868(id: Self.fokinaID, name: longName, tiles: [
                Self.tile(nil, "2–0", Self.counts(2, 2, 0), "constructed counts", unit: "sets won"),
                Self.fokinaTiles[1],
            ]),
            ExactScoreFinishPlayer10868(id: Self.tiafoeID, name: Self.tiafoe, tiles: Self.tiafoeTiles),
        ]
        let input = Self.input(players: groups)
        XCTAssertEqual(input.players[0].name, longName)
        XCTAssertEqual(Self.label(input, 0, 0), "\(longName), 2–0 sets won")
        XCTAssertEqual(input.words.countsKey, "Sets won · best of 3")
        XCTAssertEqual(input.map.title, "Which finish happened?")
        XCTAssertEqual(ExactScoreFinishAccessibilityID10868.tile(Self.fokinaTwoOne),
                       "exactScoreFinish10868.tile.constructed:15327291:kalshi:65129363:244894447")
        XCTAssertEqual(ExactScoreFinishAccessibilityID10868.slot(player: 1, tile: 0), "exactScoreFinish10868.slot.1.0")
        XCTAssertEqual(ExactScoreFinishAccessibilityID10868.choice("constructed:original:unassociated"),
                       "exactScoreFinish10868.choice.constructed:original:unassociated")
        XCTAssertEqual(ExactScoreFinishAccessibilityID10868.summary, "exactScoreFinish10868.summary")
        XCTAssertEqual(ExactScoreFinishAccessibilityID10868.details, "exactScoreFinish10868.details")
        XCTAssertEqual(ExactScoreFinishAccessibilityID10868.recover, "exactScoreFinish10868.recover")
    }

    // MARK: Arrangement (arithmetic on constructed sizes)

    func testTilesShareARowOnlyWhenEveryTileFitsWholeAndStackOtherwise() {
        // CONSTRUCTED default-size extents: each tile's widest whole line 92 pt.
        for width in [CGFloat(288), 343, 361] {   // 320 / 375 / 393 less 16 pt a side
            let tile = ExactScoreFinishGeometry10868.tileWidth(available: width, idealWidths: [92, 92], spacing: 8, accessibilitySize: false)!
            XCTAssertEqual(tile.arrangement, .row)
            XCTAssertEqual(tile.width, (width - 8) / 2)
            let plan = ExactScoreFinishGeometry10868.plan(tile, heights: [132, 128], spacing: 8)!
            XCTAssertEqual(plan.frames.map(\.height), [132, 132])
            XCTAssertEqual(plan.frames[1].minX, tile.width + 8)
            XCTAssertEqual(plan.size, CGSize(width: width, height: 132))
        }
        // Too narrow for two whole tiles: stacked at full width.
        let narrow = ExactScoreFinishGeometry10868.tileWidth(available: 180, idealWidths: [92, 92], spacing: 8, accessibilitySize: false)!
        XCTAssertEqual(narrow, ExactScoreFinishTileWidth10868(arrangement: .stack, width: 180))
        let stacked = ExactScoreFinishGeometry10868.plan(narrow, heights: [132, 128], spacing: 8)!
        XCTAssertEqual(stacked.frames, [CGRect(x: 0, y: 0, width: 180, height: 132), CGRect(x: 0, y: 140, width: 180, height: 128)])
        XCTAssertEqual(stacked.size, CGSize(width: 180, height: 268))
        // Accessibility sizes always stack, even with room.
        XCTAssertEqual(ExactScoreFinishGeometry10868.tileWidth(available: 640, idealWidths: [92, 92], spacing: 8, accessibilitySize: true),
                       ExactScoreFinishTileWidth10868(arrangement: .stack, width: 640))
        // Three sets to win: three tiles share 343 but not 288.
        XCTAssertEqual(ExactScoreFinishGeometry10868.tileWidth(available: 343, idealWidths: [96, 96, 96], spacing: 8, accessibilitySize: false),
                       ExactScoreFinishTileWidth10868(arrangement: .row, width: 109))
        XCTAssertEqual(ExactScoreFinishGeometry10868.tileWidth(available: 288, idealWidths: [96, 96, 96], spacing: 8, accessibilitySize: false)?.arrangement,
                       .stack)
        // One long whole line stacks the group rather than wrapping it in a row.
        XCTAssertEqual(ExactScoreFinishGeometry10868.tileWidth(available: 343, idealWidths: [92, 170], spacing: 8, accessibilitySize: false)?.arrangement,
                       .stack)
        // Unbounded: a row at the widest tile; no tile below the 44 pt target.
        let open = ExactScoreFinishGeometry10868.tileWidth(available: .infinity, idealWidths: [30, 20], spacing: 8, accessibilitySize: false)!
        XCTAssertEqual(open, ExactScoreFinishTileWidth10868(arrangement: .row, width: 44))
        XCTAssertEqual(ExactScoreFinishGeometry10868.plan(open, heights: [20, 30], spacing: 8)?.frames.map(\.height), [44, 44])
    }

    func testMalformedArrangementInputsPlaceNothing() {
        XCTAssertNil(ExactScoreFinishGeometry10868.tileWidth(available: 300, idealWidths: [], spacing: 8, accessibilitySize: false))
        XCTAssertNil(ExactScoreFinishGeometry10868.tileWidth(available: 300, idealWidths: [.nan], spacing: 8, accessibilitySize: false))
        XCTAssertNil(ExactScoreFinishGeometry10868.tileWidth(available: 300, idealWidths: [-1], spacing: 8, accessibilitySize: false))
        XCTAssertNil(ExactScoreFinishGeometry10868.tileWidth(available: 300, idealWidths: [92], spacing: -1, accessibilitySize: false))
        XCTAssertNil(ExactScoreFinishGeometry10868.tileWidth(available: 300, idealWidths: [92], spacing: .nan, accessibilitySize: false))
        XCTAssertNil(ExactScoreFinishGeometry10868.tileWidth(available: .nan, idealWidths: [92], spacing: 8, accessibilitySize: false))
        XCTAssertNil(ExactScoreFinishGeometry10868.tileWidth(available: -1, idealWidths: [92], spacing: 8, accessibilitySize: false))
        XCTAssertNil(ExactScoreFinishGeometry10868.tileWidth(available: 300, idealWidths: [92], spacing: 8, minimumTile: .nan, accessibilitySize: false))
        let row = ExactScoreFinishTileWidth10868(arrangement: .row, width: 100)
        XCTAssertNil(ExactScoreFinishGeometry10868.plan(row, heights: [], spacing: 8))
        XCTAssertNil(ExactScoreFinishGeometry10868.plan(row, heights: [.nan], spacing: 8))
        XCTAssertNil(ExactScoreFinishGeometry10868.plan(row, heights: [-1], spacing: 8))
        XCTAssertNil(ExactScoreFinishGeometry10868.plan(row, heights: [40], spacing: -1))
        XCTAssertNil(ExactScoreFinishGeometry10868.plan(ExactScoreFinishTileWidth10868(arrangement: .stack, width: .infinity), heights: [40], spacing: 8))
        XCTAssertNil(ExactScoreFinishGeometry10868.plan(ExactScoreFinishTileWidth10868(arrangement: .stack, width: -1), heights: [40], spacing: 8))
    }

    // MARK: Correction at 830ea403 — usable scope identity, exact-id choice membership

    /// The finish input with the exact-match scope itself carrying `id` and the
    /// same `id` held as the selected scope. Every other field as `input()`.
    private static func input(sharedScopeID id: String, selected: String? = fokinaTwoOne,
                              originals list: [ExactScoreMapOriginal10868]? = nil,
                              players groups: [ExactScoreFinishPlayer10868]? = nil) -> ExactScoreFinishInput10868 {
        let scope = ExactScoreMapScope10868(
            id: id, label: "Exact match score", rows: [], columns: [],
            originals: list ?? originals,
            scale: ExactScoreMapScale10868(lower: 0, upper: 1, ticks: []),
            actual: finalScore
        )
        let map = ExactScoreMapInput10868(
            phase: .final, title: "Which finish happened?", intro: nil,
            homeLabel: fokina, awayLabel: tiafoe, rowsTitle: "", columnsTitle: "",
            scopes: [scope], selectedScopeID: id, selectedOriginalID: selected,
            legend: legend, words: mapWords
        )
        return ExactScoreFinishInput10868(map: map, players: groups ?? players(), words: words)
    }

    /// A CONSTRUCTED unplaced original whose ignored later reading is NaN.
    private static func nanLater(_ id: String, _ label: String, pregame: ExactScoreMapPregame10868,
                                 result: ExactScoreMapResult10868) -> ExactScoreMapOriginal10868 {
        ExactScoreMapOriginal10868(id: id, label: label, placement: .nonGrid, pregame: pregame,
                                   current: .recorded(ExactScoreMapObservation10868(probability: .nan, text: "constructed later NaN",
                                                                                     detail: "constructed later clock")),
                                   result: result)
    }

    /// Every control path the view uses, routed with counting callbacks.
    private static func routedCalls(_ input: ExactScoreFinishInput10868) -> [String] {
        var calls: [String] = []
        let onSelect: (String, String) -> Void = { calls.append("select|\($0)|\($1)") }
        let onDetails: (String, String) -> Void = { calls.append("details|\($0)|\($1)") }
        let onRecover: () -> Void = { calls.append("recover") }
        for player in input.players {
            for tile in player.tiles {
                ExactScoreFinishRouting10868.route(input.selectAction(tile, of: player, canSelect: true), onSelectOriginal: onSelect,
                                                   onDetails: onDetails, onRecoverSelection: onRecover)
            }
        }
        for original in input.map.scopes.flatMap(\.originals) {
            ExactScoreFinishRouting10868.route(input.choiceAction(original, canSelect: true), onSelectOriginal: onSelect,
                                               onDetails: onDetails, onRecoverSelection: onRecover)
        }
        ExactScoreFinishRouting10868.route(input.detailsAction(canOpen: true), onSelectOriginal: onSelect,
                                           onDetails: onDetails, onRecoverSelection: onRecover)
        ExactScoreFinishRouting10868.route(input.recoverAction(canRecover: true), onSelectOriginal: onSelect,
                                           onDetails: onDetails, onRecoverSelection: onRecover)
        return calls
    }

    func testAMatchingEmptyOrWhitespaceScopeIDOffersNoFinishContextOrAction() {
        for id in ["", " ", "\t", " \n "] {
            for selected: String? in [Self.fokinaTwoOne, nil] {
                let input = Self.input(sharedScopeID: id, selected: selected)
                XCTAssertTrue(input.isShown)
                // The old map selector is unchanged: it still resolves the matching blank id.
                XCTAssertEqual(input.map.scopeSelection.scope?.id, id)
                // The finish card does not.
                XCTAssertNil(input.scope)
                XCTAssertNil(input.visibleActual)
                XCTAssertTrue(input.unplaced.isEmpty)
                XCTAssertEqual(input.selection, .unselected)
                for (player, tile) in Self.positions {
                    XCTAssertNil(Self.state(input, player, tile))
                    XCTAssertNil(Self.select(input, player, tile))
                    XCTAssertFalse(Self.selected(input, player, tile))
                    XCTAssertEqual(Self.label(input, player, tile), "")
                }
                for original in Self.originals {
                    XCTAssertNil(input.choiceAction(original, canSelect: true))
                    XCTAssertEqual(input.accessibilitySummary(original), "")
                }
                XCTAssertNil(input.detailsAction(canOpen: true))
                XCTAssertNil(input.recoverAction(canRecover: true))
                XCTAssertFalse(input.showsTapInvitation(canSelect: true))
                XCTAssertEqual(Self.routedCalls(input), [])
            }
        }
    }

    func testAValidNonblankScopeKeepsItsExactCallbackPayloadVerbatim() {
        for id in [Self.scopeID, " constructed:scope:padded ", "\tconstructed:scope:tabbed"] {
            let input = Self.input(sharedScopeID: id, selected: Self.tiafoeTwoZero)
            XCTAssertEqual(input.scope?.id, id)
            XCTAssertEqual(input.visibleActual, Self.finalScore)
            XCTAssertEqual(Self.select(input, 0, 1), .selectOriginal(scopeID: id, originalID: Self.fokinaTwoOne))
            XCTAssertEqual(Self.select(input, 0, 1), input.map.selectAction(Self.placed(input, 0, 1)!, canSelect: true))
            XCTAssertEqual(input.detailsAction(canOpen: true), .details(scopeID: id, originalID: Self.tiafoeTwoZero))
            XCTAssertTrue(input.showsTapInvitation(canSelect: true))
            XCTAssertEqual(Self.routedCalls(input), [
                "select|\(id)|\(Self.fokinaTwoZero)", "select|\(id)|\(Self.fokinaTwoOne)",
                "select|\(id)|\(Self.tiafoeTwoZero)", "select|\(id)|\(Self.tiafoeTwoOne)",
                "select|\(id)|\(Self.retained[0].ownerID)", "select|\(id)|\(Self.retained[1].ownerID)",
                "select|\(id)|\(Self.retained[2].ownerID)", "select|\(id)|\(Self.retained[3].ownerID)",
                "details|\(id)|\(Self.tiafoeTwoZero)",
            ])
        }
    }

    func testAnUnplacedUniqueOriginalWithANaNLaterValueKeepsItsExactAction() {
        let id = "constructed:original:nan-later"
        let original = Self.nanLater(id, "Constructed unplaced outcome", pregame: .recorded(Self.observation(0.01, "1%")), result: Self.lost)
        // The ignored later NaN makes the whole payload unequal to itself; identity is unaffected.
        XCTAssertNotEqual(original, original)
        let foreignTiles = (1...4).map { Self.tile("constructed:foreign:\($0)", "2–0", Self.counts(2, 2, 0), "constructed counts") }
        let foreign = Self.players(fokinaTiles: Array(foreignTiles[0..<2]), tiafoeTiles: Array(foreignTiles[2..<4]))
        for groups in [Self.players(), foreign] {
            let input = Self.input(originals: Self.originals + [original], players: groups)
            XCTAssertEqual(input.unplaced.map(\.id).filter { $0 == id }, [id])
            XCTAssertEqual(input.unplaced.first { $0.id == id }?.label, "Constructed unplaced outcome")
            XCTAssertEqual(input.choiceAction(original, canSelect: true), .selectOriginal(scopeID: Self.scopeID, originalID: id))
            XCTAssertEqual(input.choiceAction(original, canSelect: true), input.map.selectAction(original, canSelect: true))
            XCTAssertNil(input.choiceAction(original, canSelect: false))
            XCTAssertTrue(input.showsTapInvitation(canSelect: true))
            XCTAssertTrue(Self.routedCalls(input).contains("select|\(Self.scopeID)|\(id)"))
            // The later reading never becomes a final chance or a result.
            XCTAssertEqual(input.readings(original)?.chance,
                           ExactScoreMapComparison10868(title: "Pre-match chance", reading: .figure(Self.observation(0.01, "1%"))))
            XCTAssertEqual(input.readings(original)?.result,
                           ExactScoreMapComparison10868(title: "Final result", reading: .result(Self.lost)))
            XCTAssertFalse(input.map.spokenComparisons(original).contains("constructed later"))
            XCTAssertFalse(input.accessibilitySummary(original).contains("Current chance"))
        }
        // Held, it is the selection and Details opens exactly it.
        let held = Self.input(originals: Self.originals + [original], selected: id)
        XCTAssertEqual(held.selection.original?.id, id)
        XCTAssertTrue(held.isSelected(original))
        XCTAssertEqual(held.detailsAction(canOpen: true), .details(scopeID: Self.scopeID, originalID: id))
        XCTAssertNil(held.recoverAction(canRecover: true))
        XCTAssertEqual(Self.routedCalls(held).last, "details|\(Self.scopeID)|\(id)")
    }

    func testAnUnplacedOriginalWithAnInvalidOrMissingBaselineStaysNamedAndExactWhileForeignAndRepeatedIDsAreRefused() {
        let invalidID = "constructed:original:nan-baseline"
        let missingID = "constructed:original:missing-baseline"
        let invalid = Self.nanLater(invalidID, "Constructed invalid baseline", pregame: .recorded(Self.observation(.nan, "constructed owner figure")),
                                    result: Self.won)
        let missing = Self.nanLater(missingID, "Constructed missing baseline", pregame: .unavailable("Pre-match chance unavailable"),
                                    result: .other("Void"))
        let input = Self.input(originals: Self.originals + [invalid, missing])
        XCTAssertEqual(input.unplaced.map(\.id), [invalidID, missingID])
        XCTAssertEqual(input.choiceAction(invalid, canSelect: true), .selectOriginal(scopeID: Self.scopeID, originalID: invalidID))
        XCTAssertEqual(input.choiceAction(missing, canSelect: true), .selectOriginal(scopeID: Self.scopeID, originalID: missingID))
        guard case .figure(let shown)? = input.readings(invalid)?.chance.reading else { return XCTFail() }
        XCTAssertEqual(shown.text, "constructed owner figure")
        XCTAssertTrue(shown.probability.isNaN)
        XCTAssertEqual(input.readings(missing)?.chance,
                       ExactScoreMapComparison10868(title: "Pre-match chance", reading: .words("Pre-match chance unavailable")))
        XCTAssertEqual(input.readings(invalid)?.result.reading, .result(Self.won))
        XCTAssertEqual(input.readings(missing)?.result.reading, .result(.other("Void")))
        let calls = Self.routedCalls(input)
        XCTAssertTrue(calls.contains("select|\(Self.scopeID)|\(invalidID)"))
        XCTAssertTrue(calls.contains("select|\(Self.scopeID)|\(missingID)"))
        // Foreign: not an original of the scope.
        let foreign = Self.nanLater("constructed:original:foreign", "Constructed foreign", pregame: .recorded(Self.observation(0.01, "1%")),
                                    result: Self.lost)
        XCTAssertNil(input.choiceAction(foreign, canSelect: true))
        // Repeated: one id listed twice, with a NaN later reading on each copy.
        let repeatID = "constructed:original:nan-repeat"
        let first = Self.nanLater(repeatID, "Constructed repeat A", pregame: .recorded(Self.observation(0.01, "1%")), result: Self.lost)
        let second = Self.nanLater(repeatID, "Constructed repeat B", pregame: .recorded(Self.observation(0.02, "2%")), result: Self.lost)
        let repeated = Self.input(originals: Self.originals + [first, second])
        XCTAssertEqual(repeated.unplaced.map(\.id), [repeatID, repeatID])
        XCTAssertNil(repeated.choiceAction(first, canSelect: true))
        XCTAssertNil(repeated.choiceAction(second, canSelect: true))
        XCTAssertFalse(Self.routedCalls(repeated).contains { $0.hasSuffix("|\(repeatID)") })
        // Blank: never an action, NaN or not.
        let blank = Self.nanLater(" ", "Constructed blank", pregame: .recorded(Self.observation(0.01, "1%")), result: Self.lost)
        XCTAssertNil(Self.input(originals: Self.originals + [blank]).choiceAction(blank, canSelect: true))
        // Callback-free: static.
        XCTAssertNil(input.choiceAction(invalid, canSelect: false))
        XCTAssertNil(input.choiceAction(missing, canSelect: false))
        XCTAssertFalse(Self.input(originals: [invalid, missing], players: Self.players(fokinaTiles: [], tiafoeTiles: []))
            .showsTapInvitation(canSelect: false))
    }
}

/// #10868 — the tennis "Exact set finishes" card during play: four named lanes
/// composed from the map input above, on one fixed 0–100% scale.
///
/// What is asserted is the rules the view defers to: which original each lane
/// shows, its pre-match chance and fixed-scale bar, its current reading or own
/// words, its own pending or admitted result, the owner's availability kept
/// apart from all three, the unavailable cases, the named originals no lane
/// places, the exact selection, the Details action each control carries, the
/// spoken text and the lane header's arithmetic. Nothing here claims a rendered
/// fit, an executed interaction or a VoiceOver pass.
///
/// ARCHIVED values come from Fils vs van de Zandschulp, event 15327807, as
/// copied in `shipping-adoption-20261027/TENNIS-LIVE-EXACT-FINISH-RETAINED-CASES.json`:
/// Kalshi exact-match-score market 65176060, four originals in the approved lane
/// order with their key, outcome id, approved row label, outcome name, original
/// pre-match reading (recorded 2026-10-12T09:20:32.003997Z, before the verified
/// 10:55:00Z start), historical last quote and its clock, the capture's
/// impossible flag and "Result pending". Every current prop probability is
/// unavailable. The score was captured at 12:20:44.471140Z: match 0–1 sets,
/// first set 5–7 games, second set 3–3. The capture time is not a set-boundary,
/// finish or settlement time, and the last quotes are historical only.
///
/// CONSTRUCTED owner-resolved inputs (this leaf does not resolve them): the scope
/// and original action identities (copied from the packet's
/// `constructed_owner_presentation`), each lane's association, fallback label,
/// tone and availability words (the packet's `availability_words`), every
/// display figure and its provenance wording (readable local time: 09:20:32Z is
/// 2:20 AM PDT, 12:20:44Z is 5:20 AM PDT), the current-unavailable and result
/// words, the actual-score wording, the headline, note and words, the cropped
/// map scale, and every admitted current, admitted result, contradictory,
/// missing, zero, invalid, NaN, foreign, withdrawn, repeated, blank and
/// long-label case. Every constructed identity starts with "constructed:".
/// Geometry tests use CONSTRUCTED sizes and are arithmetic only.
final class ExactScoreFinishLanePresentation10868Tests: XCTestCase {

    // MARK: Archived originals

    private struct Retained {
        let key: String
        let marketID: Int
        let outcomeID: String
        /// The approved row label.
        let label: String
        let outcomeName: String
        let baseline: Double
        let baselineAt: String
        /// Historical only — never a current reading, a baseline or a result.
        let lastQuote: Double
        let lastQuoteAt: String
        /// The capture's score-derived flag; the owner, not this leaf, turns it into availability.
        let impossible: Bool
        let result: String
    }

    private static let eventID = 15327807
    private static let verifiedStart = "2026-10-12T10:55:00+00:00"
    private static let scoreCapturedAt = "2026-10-12T12:20:44.471140+00:00"
    private static let capturedSets = [[5, 7], [3, 3]]
    private static let capturedMatchSets = [0, 1]

    /// In the approved lane order (ARCHIVED).
    private static let retained: [Retained] = [
        Retained(key: "65176060:245059339", marketID: 65176060, outcomeID: "245059339", label: "Fils 2–1",
                 outcomeName: "Arthur Fils wins 2-1", baseline: 0.235, baselineAt: "2026-10-12T09:20:32.003997+00:00",
                 lastQuote: 0.2438, lastQuoteAt: "2026-10-12T12:23:56.174931+00:00", impossible: false, result: "Result pending"),
        Retained(key: "65176060:245059341", marketID: 65176060, outcomeID: "245059341", label: "Zandschulp 2–0",
                 outcomeName: "Botic Van de Zandschulp wins 2-0", baseline: 0.1, baselineAt: "2026-10-12T09:20:32.003997+00:00",
                 lastQuote: 0.6667, lastQuoteAt: "2026-10-12T12:23:56.174931+00:00", impossible: false, result: "Result pending"),
        Retained(key: "65176060:245059340", marketID: 65176060, outcomeID: "245059340", label: "Zandschulp 2–1",
                 outcomeName: "Botic Van de Zandschulp wins 2-1", baseline: 0.105, baselineAt: "2026-10-12T09:20:32.003997+00:00",
                 lastQuote: 0.0796, lastQuoteAt: "2026-10-12T12:23:56.174931+00:00", impossible: false, result: "Result pending"),
        Retained(key: "65176060:245059338", marketID: 65176060, outcomeID: "245059338", label: "Fils 2–0",
                 outcomeName: "Arthur Fils wins 2-0", baseline: 0.56, baselineAt: "2026-10-12T09:20:32.003997+00:00",
                 lastQuote: 0.01, lastQuoteAt: "2026-10-12T11:55:06.745445+00:00", impossible: true, result: "Result pending"),
    ]

    // MARK: Constructed owner inputs

    private static let scopeID = "constructed:15327807:kalshi:65176060:exact-finishes"
    private static let filsTwoOne = "constructed:15327807:kalshi:65176060:245059339"
    private static let zandschulpTwoZero = "constructed:15327807:kalshi:65176060:245059341"
    private static let zandschulpTwoOne = "constructed:15327807:kalshi:65176060:245059340"
    private static let filsTwoZero = "constructed:15327807:kalshi:65176060:245059338"
    /// Index-aligned with `retained` — an explicit owner table, never a lookup.
    private static let ownerIDs = [filsTwoOne, zandschulpTwoZero, zandschulpTwoOne, filsTwoZero]
    private static let figures = ["23.5%", "10%", "10.5%", "56%"]
    private static let beforeDetail = "Kalshi · recorded Oct 12, 2:20 AM PDT, before the match"

    private static let still = ExactScoreFinishLaneAvailability10868.open("Still possible")
    private static let ruledOut = ExactScoreFinishLaneAvailability10868.ruledOut("No longer possible")
    private static let currentUnavailable = ExactScoreMapCurrent10868.unavailable("Current probability unavailable")
    private static let pending = ExactScoreMapResult10868.unconfirmed("Result pending")
    private static let score = ExactScoreMapActual10868(title: "Score · recorded 5:20 AM PDT",
                                                         text: "Sets 0–1 · set 1 5–7 games · set 2 3–3 games")

    private static let mapWords = ExactScoreMapWords10868(
        pregameTitle: "Pre-match chance",
        currentTitle: "Current chance",
        liveResultTitle: "Market result",
        finalResultTitle: "Final result",
        scopeUnavailable: "Exact match score unavailable.",
        noSelection: "Choose a finish.",
        selectionUnavailable: "Selected finish unavailable.",
        recoverSelection: "View the listed finishes",
        mapUnavailable: "Score map unavailable.",
        scaleUnavailable: "Scale unavailable.",
        panHint: "Swipe sideways.",
        notListed: "Not listed",
        unavailableMark: "—",
        otherChoicesTitle: "Other listed outcomes",
        previous: "Previous finish",
        next: "Next finish",
        details: "Details",
        selectedSpoken: "Selected",
        selectScopeHint: "Shows this market's finishes",
        selectHint: "Shows this finish's chances",
        detailsHint: "Opens the original market"
    )

    /// CONSTRUCTED; required by the map input, unused by the lane card.
    private static let legend = ExactScoreMapLegend10868(
        scaleTitle: "Pre-match chance", offScale: "Hatched: outside the scale", notListed: "Dashed: not listed",
        unavailable: "—: no pre-match chance", result: "Outline: confirmed result", selection: "Corners: selected"
    )

    private static let words = ExactScoreFinishLaneWords10868(
        eyebrow: "EXACT FINISH · SETS",
        scaleKey: "Pre-match chances · same 0–100% scale",
        availabilityTitle: "Finish status",
        originalResultTitle: "Original market result",
        laneUnavailable: "Finish unavailable",
        contextNote: "Fils lost set 1, ruling out 2–0. Market results are still pending."
    )

    /// A cropped map shading scale the lanes must never use.
    private static let croppedMapScale = ExactScoreMapScale10868(lower: 0, upper: 0.1, ticks: [ExactScoreMapTick10868(value: 0.1, text: "10%")])

    private static func observation(_ value: Double, _ text: String, _ detail: String = beforeDetail) -> ExactScoreMapObservation10868 {
        ExactScoreMapObservation10868(probability: value, text: text, detail: detail)
    }

    /// Retained original `index` with its owner identity; any field overridable.
    private static func original(_ index: Int, pregame: ExactScoreMapPregame10868? = nil, current: ExactScoreMapCurrent10868? = nil,
                                 result: ExactScoreMapResult10868? = nil) -> ExactScoreMapOriginal10868 {
        let r = retained[index]
        return ExactScoreMapOriginal10868(id: ownerIDs[index], label: r.label, placement: .nonGrid,
                                          pregame: pregame ?? .recorded(observation(r.baseline, figures[index])),
                                          current: current ?? currentUnavailable, result: result ?? pending)
    }

    /// A CONSTRUCTED original with every field explicit.
    private static func constructed(_ id: String, _ label: String, pregame: ExactScoreMapPregame10868,
                                    current: ExactScoreMapCurrent10868 = currentUnavailable,
                                    result: ExactScoreMapResult10868 = pending) -> ExactScoreMapOriginal10868 {
        ExactScoreMapOriginal10868(id: id, label: label, placement: .nonGrid, pregame: pregame, current: current, result: result)
    }

    private static var originals: [ExactScoreMapOriginal10868] {
        (0..<4).map { original($0) }
    }

    private static func lane(_ id: String?, _ fallback: String, _ availability: ExactScoreFinishLaneAvailability10868,
                             _ tone: ExactScoreFinishLaneTone10868) -> ExactScoreFinishLane10868 {
        ExactScoreFinishLane10868(originalID: id, fallbackLabel: fallback, availability: availability, tone: tone)
    }

    /// The approved owner order, availability from the packet's words.
    private static let lanes = [
        lane(filsTwoOne, "Fils wins 2–1", still, .home),
        lane(zandschulpTwoZero, "Zandschulp wins 2–0", still, .away),
        lane(zandschulpTwoOne, "Zandschulp wins 2–1", still, .away),
        lane(filsTwoZero, "Fils wins 2–0", ruledOut, .home),
    ]

    private static func input(
        _ phase: ExactScoreMapPhase10868 = .during,
        originals list: [ExactScoreMapOriginal10868]? = nil,
        lanes laneList: [ExactScoreFinishLane10868]? = nil,
        selected: String? = nil,
        scopeID selectedScope: String? = scopeID,
        sharedScopeID: String? = nil,
        actual: ExactScoreMapActual10868?? = nil,
        extraScopes: [ExactScoreMapScope10868] = []
    ) -> ExactScoreFinishLaneInput10868 {
        let scope = ExactScoreMapScope10868(
            id: sharedScopeID ?? scopeID, label: "Exact match score", rows: [], columns: [],
            originals: list ?? originals, scale: croppedMapScale, actual: actual ?? score
        )
        let map = ExactScoreMapInput10868(
            phase: phase, title: "Three finishes remain", intro: nil,
            homeLabel: "Arthur Fils", awayLabel: "Botic van de Zandschulp", rowsTitle: "", columnsTitle: "",
            scopes: [scope] + extraScopes, selectedScopeID: sharedScopeID ?? selectedScope, selectedOriginalID: selected,
            legend: legend, words: mapWords
        )
        return ExactScoreFinishLaneInput10868(map: map, lanes: laneList ?? lanes, words: words)
    }

    private static func state(_ input: ExactScoreFinishLaneInput10868, _ index: Int) -> ExactScoreFinishLaneState10868? {
        input.state(input.lanes[index])
    }

    private static func placed(_ input: ExactScoreFinishLaneInput10868, _ index: Int) -> ExactScoreMapOriginal10868? {
        if case .placed(let original)? = state(input, index) { return original }
        return nil
    }

    private static func readings(_ input: ExactScoreFinishLaneInput10868, _ index: Int) -> ExactScoreFinishLaneReadings10868? {
        placed(input, index).flatMap { input.readings($0) }
    }

    private static func details(_ input: ExactScoreFinishLaneInput10868, _ index: Int, canOpen: Bool = true) -> ExactScoreMapAction10868? {
        input.detailsAction(input.lanes[index], canOpen: canOpen)
    }

    /// Every control path the view uses, routed with counting callbacks.
    private static func routedCalls(_ input: ExactScoreFinishLaneInput10868, canOpen: Bool = true) -> [String] {
        var calls: [String] = []
        let onSelect: (String, String) -> Void = { calls.append("select|\($0)|\($1)") }
        let onDetails: (String, String) -> Void = { calls.append("details|\($0)|\($1)") }
        let onRecover: () -> Void = { calls.append("recover") }
        for lane in input.lanes {
            ExactScoreFinishRouting10868.route(input.detailsAction(lane, canOpen: canOpen), onSelectOriginal: onSelect,
                                               onDetails: onDetails, onRecoverSelection: onRecover)
        }
        for original in input.unplaced {
            ExactScoreFinishRouting10868.route(input.detailsAction(original, canOpen: canOpen), onSelectOriginal: onSelect,
                                               onDetails: onDetails, onRecoverSelection: onRecover)
        }
        return calls
    }

    private static func chance(_ value: Double, _ text: String) -> ExactScoreMapComparison10868 {
        ExactScoreMapComparison10868(title: "Pre-match chance", reading: .figure(observation(value, text)))
    }

    private static let currentWords = ExactScoreMapComparison10868(title: "Current chance", reading: .words("Current probability unavailable"))
    private static let pendingLine = ExactScoreMapComparison10868(title: "Original market result", reading: .result(pending))

    // MARK: Retained originals

    func testTheFourRetainedOriginalsKeepTheirExactIdentitiesBaselinesClocksAndApprovedOrder() {
        XCTAssertEqual(Self.eventID, 15327807)
        XCTAssertEqual(Self.retained.map(\.outcomeID), ["245059339", "245059341", "245059340", "245059338"])
        XCTAssertEqual(Self.retained.map(\.label), ["Fils 2–1", "Zandschulp 2–0", "Zandschulp 2–1", "Fils 2–0"])
        XCTAssertEqual(Self.retained.map(\.baseline), [0.235, 0.1, 0.105, 0.56])
        XCTAssertEqual(Set(Self.retained.map(\.marketID)), [65176060])
        XCTAssertEqual(Set(Self.retained.map(\.baselineAt)), ["2026-10-12T09:20:32.003997+00:00"])
        // ISO-8601 at one offset: the baseline clock is before the verified start, which is before the score capture.
        XCTAssertLessThan(Self.retained[0].baselineAt, Self.verifiedStart)
        XCTAssertLessThan(Self.verifiedStart, Self.scoreCapturedAt)
        XCTAssertEqual(Self.retained.map(\.impossible), [false, false, false, true])
        XCTAssertEqual(Set(Self.retained.map(\.result)), ["Result pending"])
        XCTAssertEqual(Self.ownerIDs.map { $0.hasPrefix("constructed:") }, [true, true, true, true])
        for (index, r) in Self.retained.enumerated() { XCTAssertTrue(Self.ownerIDs[index].hasSuffix(":\(r.outcomeID)")) }

        let input = Self.input()
        XCTAssertTrue(input.isShown)
        XCTAssertEqual(input.scope?.id, Self.scopeID)
        // Each lane shows exactly its owner's original, in the owner's order — not by chance.
        XCTAssertEqual((0..<4).map { Self.placed(input, $0)?.id }, Self.ownerIDs.map { Optional($0) })
        XCTAssertEqual((0..<4).map { Self.placed(input, $0)?.label }, Self.retained.map { Optional($0.label) })
        XCTAssertNotEqual(Self.retained.map(\.baseline), Self.retained.map(\.baseline).sorted(by: >))
        for index in 0..<4 {
            XCTAssertEqual(Self.readings(input, index)?.chance, Self.chance(Self.retained[index].baseline, Self.figures[index]))
            XCTAssertEqual(Self.readings(input, index)?.chanceBar, .fill(Self.retained[index].baseline))
            XCTAssertEqual(Self.readings(input, index)?.second, Self.currentWords)
            XCTAssertEqual(Self.readings(input, index)?.pendingResult, Self.pendingLine)
            XCTAssertNil(Self.readings(input, index)?.secondBar)
        }
        XCTAssertEqual(input.lanes.map(\.availability), [Self.still, Self.still, Self.still, Self.ruledOut])
        XCTAssertTrue(input.unplaced.isEmpty)
    }

    func testTheRuledOutFilsTwoZeroKeepsItsFiftySixPercentBeforeWhileItsOriginalResultStaysPending() {
        let input = Self.input()
        let lane = input.lanes[3]
        guard let original = Self.placed(input, 3), let readings = Self.readings(input, 3) else { return XCTFail() }
        XCTAssertEqual(original.id, Self.filsTwoZero)
        XCTAssertTrue(lane.availability.isRuledOut)
        XCTAssertEqual(lane.availability.text, "No longer possible")
        // Full-size, labelled, on the common scale — not a footnote, not a zero.
        XCTAssertEqual(readings.chance, Self.chance(0.56, "56%"))
        XCTAssertEqual(readings.chanceBar, .fill(0.56))
        guard let width = ExactScoreFinishLaneGeometry10868.fillWidth(readings.chanceBar, track: 300) else { return XCTFail() }
        XCTAssertEqual(width, 168, accuracy: 1e-9)
        // Current and the original's own result stay separate from the physical status.
        XCTAssertEqual(readings.second, Self.currentWords)
        XCTAssertEqual(readings.pendingResult, Self.pendingLine)
        XCTAssertFalse(original.result.isAdmitted)
        XCTAssertNil(original.result.mark)
        XCTAssertFalse(input.comparisons(original).contains { $0.title.contains("possible") })
        XCTAssertEqual(input.accessibilityValue(lane),
                       "Pre-match chance: 56%, \(Self.beforeDetail); Current chance: Current probability unavailable; "
                       + "Finish status: No longer possible; Original market result: Result pending")
        // It still opens its exact original.
        XCTAssertEqual(Self.details(input, 3), .details(scopeID: Self.scopeID, originalID: Self.filsTwoZero))
    }

    func testHistoricalLastQuotesNeverBecomeACurrentChanceABaselineOrAResult() {
        // The owner withholds every later quote (CONSTRUCTED words naming only the clock).
        let withheld = (0..<4).map { index -> ExactScoreMapOriginal10868 in
            Self.original(index, current: .withheld("No recent price since 5:23 AM PDT"))
        }
        let input = Self.input(originals: withheld)
        for index in 0..<4 {
            let lane = input.lanes[index]
            guard let readings = Self.readings(input, index) else { return XCTFail() }
            XCTAssertEqual(readings.chance, Self.chance(Self.retained[index].baseline, Self.figures[index]))
            XCTAssertEqual(readings.second, ExactScoreMapComparison10868(title: "Current chance", reading: .words("No recent price since 5:23 AM PDT")))
            XCTAssertNil(readings.secondBar)
            XCTAssertEqual(readings.pendingResult, Self.pendingLine)
            let spoken = input.accessibilityValue(lane)
            for quote in ["1%", "24.38", "66.67", "7.96", "0.01"] { XCTAssertFalse(spoken.contains(quote), "\(quote) in \(spoken)") }
            XCTAssertNotNil(Self.details(input, index))
        }
        // The archived 1% quote stays historical evidence only.
        XCTAssertEqual(Self.retained[3].lastQuote, 0.01)
        XCTAssertEqual(Self.retained[3].lastQuoteAt, "2026-10-12T11:55:06.745445+00:00")
        XCTAssertEqual(Self.readings(input, 3)?.chanceBar, .fill(0.56))
    }

    // MARK: Current, result and availability

    func testCurrentResultAndAvailabilityStaySeparateIncludingAdmittedAndContradictoryControls() {
        // CONSTRUCTED: an admitted current on an open lane, an admitted loss on the
        // ruled-out lane, a contradictory admitted win on the ruled-out lane, an
        // admitted loss on an open lane.
        let current = Self.observation(0.3, "30%", "Kalshi · traded 5:22 AM PDT")
        let base = Self.originals
        var list = base
        list[0] = Self.original(0, current: .recorded(current))
        list[3] = Self.original(3, result: .lost("Lost"))
        let input = Self.input(originals: list)
        guard let first = Self.readings(input, 0), let ruled = Self.readings(input, 3) else { return XCTFail() }
        // A current figure is comparably prominent: its own title, figure and bar on the same scale.
        XCTAssertEqual(first.second, ExactScoreMapComparison10868(title: "Current chance", reading: .figure(current)))
        XCTAssertEqual(first.secondBar, .fill(0.3))
        XCTAssertEqual(first.chance, Self.chance(0.235, "23.5%"))
        XCTAssertEqual(first.pendingResult, Self.pendingLine)
        XCTAssertEqual(input.lanes[0].availability, Self.still)
        // An admitted result is the original's own and replaces the pending line, not the availability.
        XCTAssertEqual(ruled.second, ExactScoreMapComparison10868(title: "Market result", reading: .result(.lost("Lost"))))
        XCTAssertNil(ruled.pendingResult)
        XCTAssertNil(ruled.secondBar)
        XCTAssertEqual(ruled.chanceBar, .fill(0.56))
        XCTAssertEqual(input.lanes[3].availability, Self.ruledOut)

        var contradictory = base
        contradictory[3] = Self.original(3, result: .won("Won"))
        contradictory[1] = Self.original(1, result: .lost("Lost"))
        let odd = Self.input(originals: contradictory)
        // Shown as supplied: the leaf reconciles nothing.
        XCTAssertEqual(Self.readings(odd, 3)?.second.reading, .result(.won("Won")))
        XCTAssertTrue(odd.lanes[3].availability.isRuledOut)
        XCTAssertEqual(Self.readings(odd, 1)?.second.reading, .result(.lost("Lost")))
        XCTAssertFalse(odd.lanes[1].availability.isRuledOut)
        XCTAssertEqual(odd.accessibilityValue(odd.lanes[3]),
                       "Pre-match chance: 56%, \(Self.beforeDetail); Market result: Won; Finish status: No longer possible")
        // Swapping the owner's availability changes only the availability.
        var swapped = Self.lanes
        swapped[0] = Self.lane(Self.filsTwoOne, "Fils wins 2–1", Self.ruledOut, .home)
        swapped[3] = Self.lane(Self.filsTwoZero, "Fils wins 2–0", Self.still, .home)
        let other = Self.input(lanes: swapped)
        for index in 0..<4 { XCTAssertEqual(Self.readings(other, index), Self.readings(Self.input(), index)) }
        XCTAssertTrue(other.lanes[0].availability.isRuledOut)
        XCTAssertFalse(other.lanes[3].availability.isRuledOut)
    }

    func testHatchingIsAvailabilityOnlyNeverASelectionALossOrAZero() {
        for held in [Self.filsTwoZero, Self.filsTwoOne] {
            let input = Self.input(selected: held)
            XCTAssertEqual(input.selection.original?.id, held)
            XCTAssertEqual((0..<4).map { input.isSelected(input.lanes[$0]) }, Self.ownerIDs.map { $0 == held })
            // The ruled-out lane is hatched whether or not it is held.
            XCTAssertTrue(input.lanes[3].availability.isRuledOut)
            XCTAssertEqual(Self.readings(input, 3)?.chanceBar, .fill(0.56))
            XCTAssertNil(Self.placed(input, 3)?.result.mark)
        }
        // No held original: nothing is chosen, the hatch stays.
        let none = Self.input(selected: nil)
        XCTAssertEqual(none.selection, .unselected)
        XCTAssertFalse((0..<4).contains { none.isSelected(none.lanes[$0]) })
        XCTAssertTrue(none.lanes[3].availability.isRuledOut)
        // A withdrawn, repeated or blank held identity elects nothing.
        let withdrawn = Self.input(originals: Array(Self.originals.prefix(3)), selected: Self.filsTwoZero)
        XCTAssertEqual(withdrawn.selection, .missing(Self.filsTwoZero))
        let blankOriginal = Self.constructed(" ", "Constructed blank identity", pregame: .recorded(Self.observation(0.2, "20%")))
        XCTAssertEqual(Self.input(originals: Self.originals + [blankOriginal], selected: " ").selection, .missing(" "))
        let copy = Self.constructed(Self.filsTwoOne, "Constructed second listing", pregame: .recorded(Self.observation(0.2, "20%")))
        let repeated = Self.input(originals: Self.originals + [copy], selected: Self.filsTwoOne)
        XCTAssertEqual(repeated.selection, .duplicate(Self.filsTwoOne))
        XCTAssertFalse((0..<4).contains { repeated.isSelected(repeated.lanes[$0]) })
    }

    // MARK: Fixed scale

    func testMissingZeroAndInvalidChancesDrawNoFabricatedFillOnTheFixedScale() {
        XCTAssertEqual(ExactScoreFinishLaneGeometry10868.scale, ExactScoreMapScale10868(lower: 0, upper: 1, ticks: []))
        func bar(_ value: Double) -> ExactScoreFinishLaneBar10868 {
            ExactScoreFinishLaneGeometry10868.bar(.figure(Self.observation(value, "constructed")))
        }
        XCTAssertEqual(bar(0), .fill(0))
        XCTAssertEqual(bar(1), .fill(1))
        XCTAssertEqual(bar(0.56), .fill(0.56))
        for value in [Double.nan, .infinity, -.infinity, 1.2, -0.1] { XCTAssertEqual(bar(value), .noFill, "\(value)") }
        XCTAssertEqual(ExactScoreFinishLaneGeometry10868.bar(.words("Pre-match chance unavailable")), .noFill)
        XCTAssertEqual(ExactScoreFinishLaneGeometry10868.bar(.result(Self.pending)), .noFill)
        XCTAssertEqual(ExactScoreFinishLaneGeometry10868.fillWidth(.fill(0), track: 300), 0)
        XCTAssertEqual(ExactScoreFinishLaneGeometry10868.fillWidth(.fill(1), track: 300), 300)
        XCTAssertNil(ExactScoreFinishLaneGeometry10868.fillWidth(.noFill, track: 300))
        XCTAssertNil(ExactScoreFinishLaneGeometry10868.fillWidth(.fill(0.5), track: .nan))
        XCTAssertNil(ExactScoreFinishLaneGeometry10868.fillWidth(.fill(0.5), track: -1))

        // Through the lanes: missing keeps the owner's words, zero keeps its figure, invalid is never clamped.
        var list = Self.originals
        list[0] = Self.original(0, pregame: .unavailable("Pre-match chance unavailable"))
        list[1] = Self.original(1, pregame: .recorded(Self.observation(0, "0%")))
        list[2] = Self.original(2, pregame: .recorded(Self.observation(1.2, "constructed owner figure")))
        let input = Self.input(originals: list)
        XCTAssertEqual(Self.readings(input, 0)?.chance,
                       ExactScoreMapComparison10868(title: "Pre-match chance", reading: .words("Pre-match chance unavailable")))
        XCTAssertEqual(Self.readings(input, 0)?.chanceBar, ExactScoreFinishLaneBar10868.noFill)
        XCTAssertEqual(Self.readings(input, 1)?.chance, Self.chance(0, "0%"))
        XCTAssertEqual(Self.readings(input, 1)?.chanceBar, .fill(0))
        XCTAssertEqual(Self.readings(input, 2)?.chance, Self.chance(1.2, "constructed owner figure"))
        XCTAssertEqual(Self.readings(input, 2)?.chanceBar, ExactScoreFinishLaneBar10868.noFill)
        // Every lane keeps its exact Details whatever its chance.
        XCTAssertEqual((0..<4).map { Self.details(input, $0) },
                       Self.ownerIDs.map { Optional(ExactScoreMapAction10868.details(scopeID: Self.scopeID, originalID: $0)) })

        // One common scale: the map's cropped 0–10% shading never moves a lane bar,
        // and each fill is its own value of the same track.
        let shown = Self.input()
        XCTAssertNil(ExactScoreMapGeometry10868.fraction(0.56, scale: Self.croppedMapScale))
        let track: CGFloat = 320
        XCTAssertEqual((0..<4).map { ExactScoreFinishLaneGeometry10868.fillWidth(Self.readings(shown, $0)!.chanceBar, track: track) },
                       [track * 0.235, track * 0.1, track * 0.105, track * 0.56])
        // No normalization: the four independent chances are kept as supplied.
        XCTAssertEqual(Self.retained.map(\.baseline).reduce(0, +), 1.0, accuracy: 1e-9)
    }

    // MARK: Phases

    func testBeforePlayAndAfterTheFinalTheLaneCardShowsNothingAndTheOtherCardsAreUnchanged() {
        for phase in [ExactScoreMapPhase10868.before, .final] {
            let input = Self.input(phase, selected: Self.filsTwoZero)
            XCTAssertFalse(input.isShown)
            XCTAssertNil(input.scope)
            XCTAssertNil(input.visibleActual)
            XCTAssertTrue(input.unplaced.isEmpty)
            XCTAssertEqual(input.selection, .unselected)
            for index in 0..<4 {
                XCTAssertNil(Self.state(input, index))
                XCTAssertNil(Self.details(input, index))
                XCTAssertEqual(input.accessibilityLabel(input.lanes[index]), "")
                XCTAssertEqual(input.accessibilityValue(input.lanes[index]), "")
            }
            for original in Self.originals {
                XCTAssertTrue(input.comparisons(original).isEmpty)
                XCTAssertNil(input.readings(original))
                XCTAssertNil(input.detailsAction(original, canOpen: true))
                XCTAssertEqual(input.accessibilityValue(original), "")
            }
            XCTAssertEqual(Self.routedCalls(input), [])
        }
        // The map's own lifecycle is unchanged, and the lane card reads exactly its during comparisons.
        let during = Self.input()
        for original in Self.originals { XCTAssertEqual(during.comparisons(original), during.map.comparisons(original)) }
        let finalMap = Self.input(.final).map
        XCTAssertEqual(finalMap.comparisons(Self.originals[3]).map(\.title), ["Pre-match chance", "Final result"])
        XCTAssertEqual(Self.input(.before).map.comparisons(Self.originals[3]).count, 1)
        // The final finish tiles stay final-only on the same map input.
        let tileWords = ExactScoreFinishWords10868(countsKey: "constructed", countsNote: "constructed", countsUnavailable: "constructed",
                                                   finishUnavailable: "constructed", tapInvitation: "constructed")
        XCTAssertFalse(ExactScoreFinishInput10868(map: during.map, players: [], words: tileWords).isShown)
        XCTAssertTrue(ExactScoreFinishInput10868(map: finalMap, players: [], words: tileWords).isShown)
    }

    func testTheActualScoreIsLabelledContextAndNeverAChanceAnAvailabilityOrAResult() {
        XCTAssertEqual(Self.capturedMatchSets, [0, 1])
        XCTAssertEqual(Self.capturedSets, [[5, 7], [3, 3]])
        let input = Self.input()
        XCTAssertEqual(input.visibleActual, Self.score)
        let elsewhere = Self.input(actual: .some(ExactScoreMapActual10868(title: "constructed", text: "Sets 1–0 · constructed")))
        let absent = Self.input(actual: .some(nil))
        XCTAssertNil(absent.visibleActual)
        for other in [elsewhere, absent] {
            for index in 0..<4 {
                XCTAssertEqual(Self.state(other, index), Self.state(input, index))
                XCTAssertEqual(Self.readings(other, index), Self.readings(input, index))
                XCTAssertEqual(other.accessibilityValue(other.lanes[index]), input.accessibilityValue(input.lanes[index]))
            }
        }
        XCTAssertFalse(input.accessibilityValue(input.lanes[3]).contains("Sets"))
    }

    // MARK: Identity

    func testScopeIdentityIsExactNonblankAndNeverSubstituted() {
        for id in ["", " ", "\t", " \n "] {
            let input = Self.input(sharedScopeID: id)
            XCTAssertEqual(input.map.scopeSelection.scope?.id, id)
            XCTAssertNil(input.scope)
            XCTAssertNil(input.visibleActual)
            XCTAssertTrue(input.unplaced.isEmpty)
            for index in 0..<4 { XCTAssertNil(Self.state(input, index)) }
            XCTAssertEqual(Self.routedCalls(input), [])
        }
        XCTAssertNil(Self.input(scopeID: nil).scope)
        XCTAssertNil(Self.input(scopeID: "constructed:scope:foreign").scope)
        let twin = ExactScoreMapScope10868(id: Self.scopeID, label: "Constructed twin", rows: [], columns: [],
                                           originals: Self.originals, scale: Self.croppedMapScale, actual: nil)
        let duplicated = Self.input(extraScopes: [twin])
        XCTAssertNil(duplicated.scope)
        XCTAssertEqual(Self.routedCalls(duplicated), [])
        for id in [" constructed:scope:padded ", "\tconstructed:scope:tabbed"] {
            let input = Self.input(sharedScopeID: id)
            XCTAssertEqual(input.scope?.id, id)
            XCTAssertEqual(Self.details(input, 3), .details(scopeID: id, originalID: Self.filsTwoZero))
        }
    }

    func testBlankForeignWithdrawnRepeatedAndTwiceClaimedAssociationsAttachNothing() {
        // Not listed: the owner names no original.
        var notListed = Self.lanes
        notListed[1] = Self.lane(nil, "Zandschulp wins 2–0", Self.still, .away)
        let a = Self.input(lanes: notListed)
        XCTAssertEqual(Self.state(a, 1), .notListed("Not listed"))
        XCTAssertEqual(a.unplaced.map(\.id), [Self.zandschulpTwoZero])
        XCTAssertEqual(a.accessibilityLabel(a.lanes[1]), "Zandschulp wins 2–0")
        XCTAssertEqual(a.accessibilityValue(a.lanes[1]), "Not listed; Finish status: Still possible")
        // Blank and foreign lane identities.
        for id in ["", "  ", "constructed:original:foreign"] {
            var list = Self.lanes
            list[0] = Self.lane(id, "Fils wins 2–1", Self.still, .home)
            let input = Self.input(lanes: list)
            XCTAssertEqual(Self.state(input, 0), .unavailable("Finish unavailable"))
            XCTAssertNil(Self.details(input, 0))
            XCTAssertEqual(input.unplaced.map(\.id), [Self.filsTwoOne])
            XCTAssertEqual(input.detailsAction(input.unplaced[0], canOpen: true), .details(scopeID: Self.scopeID, originalID: Self.filsTwoOne))
        }
        // Withdrawn: the original is gone; nothing moves to a neighbour.
        let withdrawn = Self.input(originals: Array(Self.originals.prefix(3)))
        XCTAssertEqual(Self.state(withdrawn, 3), .unavailable("Finish unavailable"))
        XCTAssertEqual(withdrawn.accessibilityValue(withdrawn.lanes[3]), "Finish unavailable; Finish status: No longer possible")
        XCTAssertEqual((0..<3).map { Self.placed(withdrawn, $0)?.id }, Self.ownerIDs.prefix(3).map { Optional($0) })
        // Claimed by two lanes: neither attaches; the original stays reachable by name.
        var twice = Self.lanes
        twice[2] = Self.lane(Self.zandschulpTwoZero, "Zandschulp wins 2–1", Self.still, .away)
        let claimed = Self.input(lanes: twice)
        XCTAssertEqual(Self.state(claimed, 1), .unavailable("Finish unavailable"))
        XCTAssertEqual(Self.state(claimed, 2), .unavailable("Finish unavailable"))
        XCTAssertEqual(claimed.unplaced.map(\.id), [Self.zandschulpTwoZero, Self.zandschulpTwoOne])
        XCTAssertEqual(Self.placed(claimed, 0)?.id, Self.filsTwoOne)
        XCTAssertEqual(Self.placed(claimed, 3)?.id, Self.filsTwoZero)
        // Repeated in the scope: no lane attaches and neither copy has an action.
        let copy = Self.constructed(Self.filsTwoZero, "Constructed second listing", pregame: .recorded(Self.observation(0.3, "30%")))
        let repeated = Self.input(originals: Self.originals + [copy])
        XCTAssertEqual(Self.state(repeated, 3), .unavailable("Finish unavailable"))
        XCTAssertEqual(repeated.unplaced.map(\.label), ["Fils 2–0", "Constructed second listing"])
        XCTAssertTrue(repeated.unplaced.allSatisfy { repeated.detailsAction($0, canOpen: true) == nil })
        XCTAssertFalse(Self.routedCalls(repeated).contains { $0.hasSuffix("|\(Self.filsTwoZero)") })
    }

    func testANaNReadingNeverClosesARealOriginalAndARefreshedInputKeepsItsHeldLane() {
        let nan = Self.observation(.nan, "constructed NaN figure", "constructed clock")
        var list = Self.originals
        list[3] = Self.original(3, current: .recorded(nan))
        list[1] = Self.original(1, pregame: .recorded(nan))
        let input = Self.input(originals: list, selected: Self.filsTwoZero)
        XCTAssertNotEqual(list[3], list[3])
        XCTAssertEqual(Self.placed(input, 3)?.id, Self.filsTwoZero)
        XCTAssertEqual(Self.placed(input, 1)?.id, Self.zandschulpTwoZero)
        XCTAssertEqual(Self.details(input, 3), .details(scopeID: Self.scopeID, originalID: Self.filsTwoZero))
        XCTAssertEqual(Self.details(input, 1), .details(scopeID: Self.scopeID, originalID: Self.zandschulpTwoZero))
        XCTAssertTrue(input.isSelected(input.lanes[3]))
        XCTAssertEqual(Self.readings(input, 3)?.secondBar, ExactScoreFinishLaneBar10868.noFill)
        XCTAssertEqual(Self.readings(input, 1)?.chanceBar, ExactScoreFinishLaneBar10868.noFill)
        XCTAssertTrue(input.unplaced.isEmpty)
        // A NaN extra original stays named and opens exactly itself.
        let extra = Self.constructed("constructed:original:nan-extra", "Constructed NaN outcome", pregame: .recorded(nan), current: .recorded(nan))
        let withExtra = Self.input(originals: Self.originals + [extra])
        XCTAssertEqual(withExtra.unplaced.map(\.id), ["constructed:original:nan-extra"])
        XCTAssertEqual(withExtra.detailsAction(extra, canOpen: true), .details(scopeID: Self.scopeID, originalID: "constructed:original:nan-extra"))
        // Refreshed figures: the same lane, the same held original, the same payload.
        var refreshed = Self.originals
        refreshed[3] = Self.original(3, pregame: .recorded(Self.observation(0.56, "56% (refreshed)")))
        let later = Self.input(originals: refreshed, selected: Self.filsTwoZero)
        XCTAssertEqual(later.selection.original?.id, Self.input(selected: Self.filsTwoZero).selection.original?.id)
        XCTAssertTrue(later.isSelected(later.lanes[3]))
        XCTAssertEqual(Self.details(later, 3), Self.details(Self.input(), 3))
    }

    func testAnUnplacedOriginalShowsReadingsOnlyWhenItsOwnIdentityIsExact() {
        // The existing duplicate control: Fils 2–0 listed twice (56% and a constructed 30%),
        // plus a blank identity, beside a valid unique extra and a unique extra with NaN readings.
        let copy = Self.constructed(Self.filsTwoZero, "Constructed second listing", pregame: .recorded(Self.observation(0.3, "30%")),
                                    result: .won("Won"))
        let blank = Self.constructed("  ", "Constructed blank identity", pregame: .recorded(Self.observation(0.2, "20%")))
        let valid = Self.constructed("constructed:original:valid-extra", "Constructed valid extra", pregame: .recorded(Self.observation(0.04, "4%")))
        let nan = Self.observation(.nan, "constructed NaN figure", "constructed clock")
        let nanExtra = Self.constructed("constructed:original:nan-extra", "Constructed NaN extra", pregame: .recorded(nan), current: .recorded(nan))
        let input = Self.input(originals: Self.originals + [copy, blank, valid, nanExtra])
        // Every supplied record stays named, in the owner's order.
        XCTAssertEqual(input.unplaced.map(\.label), ["Fils 2–0", "Constructed second listing", "Constructed blank identity",
                                                     "Constructed valid extra", "Constructed NaN extra"])
        XCTAssertEqual(Self.state(input, 3), .unavailable("Finish unavailable"))
        // Ambiguous and blank: no figure, bar, result or action — only the owner's unavailable words.
        for record in input.unplaced.prefix(3) {
            XCTAssertFalse(input.isExact(record))
            XCTAssertNil(input.readings(record))
            XCTAssertEqual(input.channels(record, availability: nil), [])
            XCTAssertEqual(input.channels(record, availability: Self.ruledOut), [])
            XCTAssertEqual(input.accessibilityValue(record), "Finish unavailable")
            XCTAssertNil(input.detailsAction(record, canOpen: true))
            XCTAssertEqual(input.map.accessibilityLabel(record, in: input.scope!), "\(record.label), Exact match score")
        }
        for spoken in input.unplaced.prefix(3).map({ input.accessibilityValue($0) }) {
            for figure in ["56%", "30%", "20%", "Won", "Result pending"] { XCTAssertFalse(spoken.contains(figure)) }
        }
        // The valid extra path is unchanged: titled rows, its own bar, its own result, exact Details.
        XCTAssertTrue(input.isExact(valid))
        XCTAssertEqual(input.channels(valid, availability: nil).map(\.title), ["Pre-match chance", "Current chance", "Original market result"])
        XCTAssertEqual(input.channels(valid, availability: nil).first?.bar, .fill(0.04))
        XCTAssertEqual(input.accessibilityValue(valid),
                       "Pre-match chance: 4%, \(Self.beforeDetail); Current chance: Current probability unavailable; Original market result: Result pending")
        XCTAssertEqual(input.detailsAction(valid, canOpen: true), .details(scopeID: Self.scopeID, originalID: valid.id))
        // NaN in a real unique original never closes it: named, exact, actionable, no fabricated fill.
        XCTAssertNotEqual(nanExtra, nanExtra)
        XCTAssertTrue(input.isExact(nanExtra))
        XCTAssertEqual(input.channels(nanExtra, availability: nil).map(\.bar), [ExactScoreFinishLaneBar10868.noFill, .noFill, nil])
        XCTAssertEqual(input.detailsAction(nanExtra, canOpen: true), .details(scopeID: Self.scopeID, originalID: nanExtra.id))
        // Exactly the two exact extras route; nothing is elected for the ambiguous records.
        XCTAssertEqual(Self.routedCalls(input).filter { !Self.ownerIDs.prefix(3).contains(String($0.split(separator: "|").last!)) },
                       ["details|\(Self.scopeID)|\(valid.id)", "details|\(Self.scopeID)|\(nanExtra.id)"])
        // Foreign and withdrawn records are not originals of the scope: not exact, nothing shown.
        let foreign = Self.constructed("constructed:original:foreign", "Constructed foreign", pregame: .recorded(Self.observation(0.1, "10%")))
        XCTAssertFalse(input.isExact(foreign))
        XCTAssertEqual(input.channels(foreign, availability: nil), [])
        XCTAssertFalse(Self.input(originals: Array(Self.originals.prefix(3))).isExact(Self.originals[3]))
        // Restored to one listing, Fils 2–0 is exact again and back in its lane.
        let restored = Self.input()
        XCTAssertTrue(restored.isExact(Self.originals[3]))
        XCTAssertEqual(Self.placed(restored, 3)?.id, Self.filsTwoZero)
    }

    // MARK: Actions

    func testDetailsAreExactRealAndNeverPassive() {
        let input = Self.input()
        XCTAssertEqual(Self.routedCalls(input), Self.ownerIDs.map { "details|\(Self.scopeID)|\($0)" })
        // Membership is the map's exact-id uniqueness.
        for index in 0..<4 {
            guard let original = Self.placed(input, index) else { return XCTFail() }
            XCTAssertTrue(input.map.isUniqueOriginal(original.id, in: input.scope!))
            XCTAssertEqual(Self.details(input, index), input.detailsAction(original, canOpen: true))
        }
        // Without a callback every lane and named original is static.
        let extra = Self.constructed("constructed:original:unassociated", "Constructed unassociated outcome",
                                     pregame: .recorded(Self.observation(0.01, "1%")))
        let static_ = Self.input(originals: Self.originals + [extra])
        for index in 0..<4 { XCTAssertNil(Self.details(static_, index, canOpen: false)) }
        XCTAssertNil(static_.detailsAction(extra, canOpen: false))
        XCTAssertEqual(Self.routedCalls(static_, canOpen: false), [])
        // A foreign original has no action.
        let foreign = Self.constructed("constructed:original:foreign", "Constructed foreign", pregame: .recorded(Self.observation(0.1, "10%")))
        XCTAssertNil(input.detailsAction(foreign, canOpen: true))
        // Nothing is called passively, and no action reaches a missing callback.
        var calls = 0
        let onDetails: (String, String) -> Void = { _, _ in calls += 1 }
        ExactScoreFinishRouting10868.route(nil, onSelectOriginal: nil, onDetails: onDetails, onRecoverSelection: nil)
        ExactScoreFinishRouting10868.route(.selectScope(Self.scopeID), onSelectOriginal: nil, onDetails: onDetails, onRecoverSelection: nil)
        ExactScoreFinishRouting10868.route(.selectOriginal(scopeID: Self.scopeID, originalID: Self.filsTwoOne),
                                           onSelectOriginal: nil, onDetails: onDetails, onRecoverSelection: nil)
        XCTAssertEqual(calls, 0)
        ExactScoreFinishRouting10868.route(Self.details(input, 3), onSelectOriginal: nil, onDetails: nil, onRecoverSelection: nil)
    }

    func testEveryAdditionalScopeOriginalStaysNamedAndReachable() {
        let extras = (1...8).map { index in
            Self.constructed("constructed:original:extra-\(index)", "Constructed listed outcome \(index)",
                             pregame: .recorded(Self.observation(Double(index) / 100, "\(index)%")))
        }
        let input = Self.input(originals: Self.originals + extras)
        XCTAssertEqual(input.unplaced.map(\.id), extras.map(\.id))
        XCTAssertEqual((0..<4).map { Self.placed(input, $0)?.id }, Self.ownerIDs.map { Optional($0) })
        XCTAssertEqual(Self.routedCalls(input).count, 12)
        for extra in extras {
            XCTAssertEqual(input.detailsAction(extra, canOpen: true), .details(scopeID: Self.scopeID, originalID: extra.id))
            // A named original carries no availability: none was supplied for it.
            let spoken = input.accessibilityValue(extra)
            XCTAssertFalse(spoken.contains("possible"))
            XCTAssertFalse(spoken.contains("Finish status"))
            XCTAssertFalse(input.channels(extra, availability: nil).contains { $0.title == "Finish status" })
            XCTAssertTrue(spoken.hasSuffix("; Original market result: Result pending"))
        }
    }

    // MARK: VoiceOver and strings

    func testSpokenTextNamesChanceClockCurrentAvailabilityAndOwnResult() {
        let input = Self.input()
        XCTAssertEqual(input.accessibilityLabel(input.lanes[0]), "Fils 2–1, Exact match score")
        XCTAssertEqual(input.accessibilityValue(input.lanes[0]),
                       "Pre-match chance: 23.5%, \(Self.beforeDetail); Current chance: Current probability unavailable; "
                       + "Finish status: Still possible; Original market result: Result pending")
        XCTAssertEqual(input.accessibilityLabel(input.lanes[3]), "Fils 2–0, Exact match score")
        let extra = Self.constructed("constructed:original:named", "Constructed named outcome", pregame: .unavailable("Pre-match chance unavailable"))
        let named = Self.input(originals: Self.originals + [extra])
        XCTAssertEqual(named.accessibilityValue(extra),
                       "Pre-match chance: Pre-match chance unavailable; Current chance: Current probability unavailable; "
                       + "Original market result: Result pending")
    }

    func testOwnerStringsLongLabelsAndIdentifiersAreVerbatim() {
        let long = "Botic van de Zandschulp wins two sets to one — constructed extraordinarily long finish label"
        var list = Self.lanes
        list[2] = Self.lane("constructed:original:absent", long, Self.still, .away)
        let input = Self.input(lanes: list)
        XCTAssertEqual(input.accessibilityLabel(input.lanes[2]), long)
        XCTAssertEqual(input.words.eyebrow, "EXACT FINISH · SETS")
        XCTAssertEqual(input.words.scaleKey, "Pre-match chances · same 0–100% scale")
        XCTAssertEqual(input.words.contextNote, "Fils lost set 1, ruling out 2–0. Market results are still pending.")
        XCTAssertEqual(input.map.title, "Three finishes remain")
        XCTAssertEqual(input.lanes.map(\.tone), [.home, .away, .away, .home])
        XCTAssertEqual(ExactScoreFinishLaneAccessibilityID10868.lane(Self.filsTwoZero),
                       "exactScoreFinishLane10868.lane.constructed:15327807:kalshi:65176060:245059338")
        XCTAssertEqual(ExactScoreFinishLaneAccessibilityID10868.slot(2), "exactScoreFinishLane10868.slot.2")
        XCTAssertEqual(ExactScoreFinishLaneAccessibilityID10868.choice("constructed:original:absent"),
                       "exactScoreFinishLane10868.choice.constructed:original:absent")
    }

    // MARK: Titled rows (feedback: every channel named)

    func testEveryRowNamesItsOwnChannelSoNoReadingDependsOnPositionOrReasonWording() {
        // Retained: four titled rows per lane, the ruled-out lane hatched only on its bar and its availability mark.
        let input = Self.input()
        for index in 0..<4 {
            let rows = input.channels(input.lanes[index])
            XCTAssertEqual(rows.map(\.title), ["Pre-match chance", "Current chance", "Finish status", "Original market result"])
            XCTAssertEqual(rows[0].value, .figure(Self.observation(Self.retained[index].baseline, Self.figures[index])))
            XCTAssertEqual(rows[0].bar, .fill(Self.retained[index].baseline))
            XCTAssertEqual(rows[1].value, .words("Current probability unavailable"))
            XCTAssertNil(rows[1].bar)
            XCTAssertEqual(rows[2].value, .availability(input.lanes[index].availability))
            XCTAssertNil(rows[2].bar)
            XCTAssertEqual(rows[3].value, .result(Self.pending))
            XCTAssertNil(rows[3].bar)
            XCTAssertFalse(rows[1].hatched)
            XCTAssertFalse(rows[3].hatched)
            XCTAssertEqual(rows[0].hatched, index == 3)
            XCTAssertEqual(rows[2].hatched, index == 3)
        }
        // An owner reason that does not say "current" is still named by its title.
        for reason in ["Unavailable", "No recent price"] {
            var list = Self.originals
            list[0] = Self.original(0, current: .withheld(reason))
            let named = Self.input(originals: list).channels(Self.lanes[0])
            XCTAssertEqual(named[1], ExactScoreFinishLaneChannel10868(title: "Current chance", value: .words(reason), bar: nil, hatched: false))
        }
        // An admitted current figure gets its own titled row and its own bar on the same scale.
        let current = Self.observation(0.3, "30%", "Kalshi · traded 5:22 AM PDT")
        var withCurrent = Self.originals
        withCurrent[3] = Self.original(3, current: .recorded(current))
        let two = Self.input(originals: withCurrent).channels(Self.lanes[3])
        XCTAssertEqual(two.map(\.title), ["Pre-match chance", "Current chance", "Finish status", "Original market result"])
        XCTAssertEqual(two[0].bar, .fill(0.56))
        XCTAssertEqual(two[1].value, .figure(current))
        XCTAssertEqual(two[1].bar, .fill(0.3))
        XCTAssertEqual(two.filter { $0.bar != nil }.map(\.title), ["Pre-match chance", "Current chance"])
        // An admitted result takes the current row under its own title; there is no pending row.
        var settled = Self.originals
        settled[3] = Self.original(3, result: .lost("Lost"))
        let graded = Self.input(originals: settled).channels(Self.lanes[3])
        XCTAssertEqual(graded.map(\.title), ["Pre-match chance", "Market result", "Finish status"])
        XCTAssertEqual(graded[1].value, .result(.lost("Lost")))
        XCTAssertFalse(graded[1].hatched)
        // A missing chance keeps its title, the owner's words and a no-fill bar — never a 0%.
        var missing = Self.originals
        missing[1] = Self.original(1, pregame: .unavailable("Pre-match chance unavailable"))
        let absent = Self.input(originals: missing).channels(Self.lanes[1])
        XCTAssertEqual(absent[0], ExactScoreFinishLaneChannel10868(title: "Pre-match chance", value: .words("Pre-match chance unavailable"),
                                                                   bar: .noFill, hatched: false))
        // An unavailable lane keeps only the owner's titled availability; a named original has none.
        var foreign = Self.lanes
        foreign[3] = Self.lane("constructed:original:foreign", "Fils wins 2–0", Self.ruledOut, .home)
        let lonely = Self.input(lanes: foreign)
        XCTAssertEqual(lonely.channels(lonely.lanes[3]),
                       [ExactScoreFinishLaneChannel10868(title: "Finish status", value: .availability(Self.ruledOut), bar: nil, hatched: true)])
        XCTAssertEqual(lonely.unplaced.map(\.id), [Self.filsTwoZero])
        XCTAssertEqual(lonely.channels(lonely.unplaced[0], availability: nil).map(\.title),
                       ["Pre-match chance", "Current chance", "Original market result"])
        XCTAssertFalse(lonely.channels(lonely.unplaced[0], availability: nil).contains { $0.hatched })
        // Outside play there are no rows.
        for phase in [ExactScoreMapPhase10868.before, .final] {
            let hidden = Self.input(phase)
            XCTAssertTrue(hidden.channels(hidden.lanes[0]).isEmpty)
            XCTAssertTrue(hidden.channels(Self.originals[0], availability: Self.still).isEmpty)
        }
    }

    // MARK: Row geometry (arithmetic on constructed sizes)

    func testEachRowSitsBesideItsTitleOnlyWhenWholeAndOtherwiseWrapsWithinTheLane() {
        // CONSTRUCTED default-size extents: title 96×16, figure 52×28.
        let title = CGSize(width: 96, height: 16)
        let figure = CGSize(width: 52, height: 28)
        for width in [CGFloat(280), 335, 353] {   // 320 / 375 / 393 less 20 pt a side
            let plan = ExactScoreFinishLaneGeometry10868.rowPlan(available: width, labelIdeal: title, labelStackedHeight: 16,
                                                                 valueIdeal: figure, valueStackedHeight: 28, spacing: 8, accessibilitySize: false)!
            XCTAssertEqual(plan.arrangement, .row)
            XCTAssertEqual(plan.label, CGRect(x: 0, y: 6, width: width - 60, height: 16))
            XCTAssertEqual(plan.value, CGRect(x: width - 52, y: 0, width: 52, height: 28))
            XCTAssertEqual(plan.size, CGSize(width: width, height: 28))
        }
        // Design's case: a 340 pt value in a 264 pt lane is bounded to the lane and wraps there.
        let bounded = ExactScoreFinishLaneGeometry10868.rowPlan(available: 264, labelIdeal: title, labelStackedHeight: 16,
                                                                valueIdeal: CGSize(width: 340, height: 28), valueStackedHeight: 56,
                                                                spacing: 8, accessibilitySize: false)!
        XCTAssertEqual(bounded.arrangement, .stack)
        XCTAssertEqual(bounded.label, CGRect(x: 0, y: 0, width: 264, height: 16))
        XCTAssertEqual(bounded.value, CGRect(x: 0, y: 24, width: 264, height: 56))
        XCTAssertEqual(bounded.size, CGSize(width: 264, height: 80))
        // Accessibility sizes always stack, even with room; nothing shrinks or widens the lane.
        let ax = ExactScoreFinishLaneGeometry10868.rowPlan(available: 640, labelIdeal: CGSize(width: 180, height: 30), labelStackedHeight: 30,
                                                           valueIdeal: CGSize(width: 120, height: 64), valueStackedHeight: 64,
                                                           spacing: 8, accessibilitySize: true)!
        XCTAssertEqual(ax.arrangement, .stack)
        XCTAssertEqual(ax.value, CGRect(x: 0, y: 38, width: 120, height: 64))
        XCTAssertEqual(ax.size, CGSize(width: 640, height: 102))
        // Unbounded: side by side at the content width, or stacked at accessibility sizes.
        XCTAssertEqual(ExactScoreFinishLaneGeometry10868.rowPlan(available: .infinity, labelIdeal: title, labelStackedHeight: 16, valueIdeal: figure,
                                                                 valueStackedHeight: 28, spacing: 8, accessibilitySize: false)?.size,
                       CGSize(width: 156, height: 28))
        XCTAssertEqual(ExactScoreFinishLaneGeometry10868.rowPlan(available: .infinity, labelIdeal: title, labelStackedHeight: 16, valueIdeal: figure,
                                                                 valueStackedHeight: 28, spacing: 8, accessibilitySize: true)?.size,
                       CGSize(width: 96, height: 52))
        // Malformed inputs place nothing.
        let ok = CGSize(width: 10, height: 10)
        XCTAssertNil(ExactScoreFinishLaneGeometry10868.rowPlan(available: .nan, labelIdeal: ok, labelStackedHeight: 10, valueIdeal: ok, valueStackedHeight: 10, spacing: 8, accessibilitySize: false))
        XCTAssertNil(ExactScoreFinishLaneGeometry10868.rowPlan(available: -1, labelIdeal: ok, labelStackedHeight: 10, valueIdeal: ok, valueStackedHeight: 10, spacing: 8, accessibilitySize: false))
        XCTAssertNil(ExactScoreFinishLaneGeometry10868.rowPlan(available: 300, labelIdeal: CGSize(width: .nan, height: 10), labelStackedHeight: 10, valueIdeal: ok, valueStackedHeight: 10, spacing: 8, accessibilitySize: false))
        XCTAssertNil(ExactScoreFinishLaneGeometry10868.rowPlan(available: 300, labelIdeal: ok, labelStackedHeight: -1, valueIdeal: ok, valueStackedHeight: 10, spacing: 8, accessibilitySize: false))
        XCTAssertNil(ExactScoreFinishLaneGeometry10868.rowPlan(available: 300, labelIdeal: ok, labelStackedHeight: 10, valueIdeal: CGSize(width: 10, height: -1), valueStackedHeight: 10, spacing: 8, accessibilitySize: false))
        XCTAssertNil(ExactScoreFinishLaneGeometry10868.rowPlan(available: 300, labelIdeal: ok, labelStackedHeight: 10, valueIdeal: ok, valueStackedHeight: .infinity, spacing: 8, accessibilitySize: false))
        XCTAssertNil(ExactScoreFinishLaneGeometry10868.rowPlan(available: 300, labelIdeal: ok, labelStackedHeight: 10, valueIdeal: ok, valueStackedHeight: 10, spacing: .nan, accessibilitySize: false))
    }

    func testANarrowAccessibilityLaneKeepsBothReadingsEqualTitledAndInsideTheLane() {
        // CONSTRUCTED: an admitted current beside the pre-match chance, long owner
        // captions, and AX-size extents in a 280 pt lane (320 pt phone less 20 pt a side).
        let long = ExactScoreMapWords10868(
            pregameTitle: "Pre-match chance recorded before the first serve",
            currentTitle: "Current chance from an independently admitted trade",
            liveResultTitle: "Market result", finalResultTitle: "Final result",
            scopeUnavailable: "Exact match score unavailable.", noSelection: "Choose a finish.", selectionUnavailable: "Selected finish unavailable.",
            recoverSelection: "View the listed finishes", mapUnavailable: "Score map unavailable.", scaleUnavailable: "Scale unavailable.",
            panHint: "Swipe sideways.", notListed: "Not listed", unavailableMark: "—", otherChoicesTitle: "Other listed outcomes",
            previous: "Previous finish", next: "Next finish", details: "Details", selectedSpoken: "Selected",
            selectScopeHint: "Shows this market's finishes", selectHint: "Shows this finish's chances", detailsHint: "Opens the original market"
        )
        let current = Self.observation(0.3, "30%", "Kalshi · traded 5:22 AM PDT")
        var list = Self.originals
        list[3] = Self.original(3, current: .recorded(current))
        let base = Self.input(originals: list)
        let map = ExactScoreMapInput10868(phase: .during, title: base.map.title, intro: nil, homeLabel: base.map.homeLabel, awayLabel: base.map.awayLabel,
                                          rowsTitle: "", columnsTitle: "", scopes: base.map.scopes, selectedScopeID: Self.scopeID,
                                          selectedOriginalID: nil, legend: Self.legend, words: long)
        let input = ExactScoreFinishLaneInput10868(map: map, lanes: Self.lanes, words: Self.words)
        let rows = input.channels(input.lanes[3])
        XCTAssertEqual(rows.filter { $0.bar != nil }.map(\.title), [long.pregameTitle, long.currentTitle])
        XCTAssertEqual(rows[0].value, .figure(Self.observation(0.56, "56%")))
        XCTAssertEqual(rows[1].value, .figure(current))
        XCTAssertTrue(rows[0].hatched)
        XCTAssertTrue(rows[1].hatched)
        // Both figures use one size (CONSTRUCTED AX extent 70×53 for either figure); both long captions wrap to three lines.
        let figure = CGSize(width: 70, height: 53)
        let plans = [CGSize(width: 520, height: 22), CGSize(width: 560, height: 22)].map { caption in
            ExactScoreFinishLaneGeometry10868.rowPlan(available: 280, labelIdeal: caption, labelStackedHeight: 66,
                                                      valueIdeal: figure, valueStackedHeight: 53, spacing: 8, accessibilitySize: true)!
        }
        for plan in plans {
            XCTAssertEqual(plan.arrangement, .stack)
            XCTAssertEqual(plan.label, CGRect(x: 0, y: 0, width: 280, height: 66))
            XCTAssertEqual(plan.value, CGRect(x: 0, y: 74, width: 70, height: 53))
            XCTAssertLessThanOrEqual(plan.size.width, 280)
        }
        XCTAssertEqual(plans[0].value.size, plans[1].value.size)
        // At an ordinary size the same long captions still do not fit beside the figure: they wrap above it.
        let ordinary = ExactScoreFinishLaneGeometry10868.rowPlan(available: 280, labelIdeal: CGSize(width: 330, height: 16), labelStackedHeight: 32,
                                                                 valueIdeal: CGSize(width: 52, height: 28), valueStackedHeight: 28,
                                                                 spacing: 8, accessibilitySize: false)!
        XCTAssertEqual(ordinary.arrangement, .stack)
        XCTAssertEqual(ordinary.size, CGSize(width: 280, height: 68))
        // The bars stay on the one fixed scale whatever the captions.
        XCTAssertEqual(rows[0].bar, .fill(0.56))
        XCTAssertEqual(rows[1].bar, .fill(0.3))
    }
}
