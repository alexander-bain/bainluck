import XCTest
@testable import Bain_Luck

/// Prepared, not executed. The ladder Details content reads the held card's
/// selected point and nothing else: `Point.chance` / `now` / `result` drive the
/// headline and rail; `Detail` is provenance.
///
/// Real bodies: `event-15320337-game-matrix-9483-nba-final` (Clippers 104–101
/// Warriors, every option settled with no pin and no quote) and
/// `event-15327183-game-matrix-9483-nba-pregame` (Raptors @ Knicks before
/// tip-off). Every other card here is a CONSTRUCTED presentation control, not a
/// provider specimen. Dates go through `SourceAge.preciseStamp`, so nothing
/// depends on the test machine's time zone. Geometry, fit and VoiceOver
/// focus are NOT asserted here.
@MainActor
final class LadderOriginalProbabilityDetails9483Tests: XCTestCase {
    private typealias Model = LadderOriginalProbabilityDetails9483
    private typealias Point = NBALadderCard9483.Point
    private typealias Detail = NBALadderCard9483.Detail

    private struct Body: Decodable {
        let homeScore: Int?
        let awayScore: Int?
        let gameQuestionMatrix: EventQuestionMatrix?
    }

    private func body(_ name: String) throws -> Body {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .appendingPathComponent("Fixtures/\(name)")
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(Body.self, from: Data(contentsOf: url))
    }

    private func date(_ iso: String) -> Date { ISO8601DateFormatter().date(from: iso)! }

    private func finalTotal() throws -> NBALadderCard9483 {
        let b = try body("event-15320337-game-matrix-9483-nba-final.20261015.json")
        return try XCTUnwrap(NBALadderCard9483.total(.init(
            matrix: b.gameQuestionMatrix, status: "completed",
            commenceTime: date("2026-10-04T23:00:00Z"), homeScore: b.homeScore, awayScore: b.awayScore,
            pregameProjection: nil, homeShort: "Clippers", awayShort: "Warriors",
            now: date("2026-10-05T04:00:00Z"))))
    }

    private func pregameMargin() throws -> NBALadderCard9483 {
        let b = try body("event-15327183-game-matrix-9483-nba-pregame.20261015.json")
        return try XCTUnwrap(NBALadderCard9483.margin(.init(
            matrix: b.gameQuestionMatrix, status: "scheduled",
            commenceTime: date("2026-10-15T23:30:00Z"), homeScore: nil, awayScore: nil,
            pregameProjection: nil, homeShort: "Knicks", awayShort: "Raptors",
            now: date("2026-10-15T18:40:00Z"))))
    }

    // MARK: - Constructed controls

    private let t1 = "2026-10-15T23:20:00Z"
    private let t2 = "2026-10-16T01:05:00Z"

    private func detail(marketName: String = "Toronto vs New York: Total Points",
                        quoted: Double? = nil, observedAt: String? = nil, baseline: Double? = nil,
                        baselineAt: String? = nil, result: Bool? = nil) -> Detail {
        Detail(label: "Over 210.5 points", marketName: marketName,
               source: "kalshi", quoted: quoted, observedAt: observedAt,
               baseline: baseline, baselineObservedAt: baselineAt, result: result)
    }

    private func point(_ key: String = "o:1", chance: Double?, now: Double? = nil,
                       observedAt: String? = nil, result: Bool? = nil, detail: Detail? = nil) -> Point {
        Point(optionKey: key, x: 210.5, label: "Over 210.5", side: .game, chance: chance, now: now,
              observedAt: observedAt, result: result, detail: detail ?? self.detail())
    }

    private func card(_ phase: NBALadderCard9483.Phase, _ points: [Point]) -> NBALadderCard9483 {
        NBALadderCard9483(family: .total, phase: phase, points: points, actual: nil, forecast: nil,
                          awayShort: "Raptors", homeShort: "Knicks")
    }

    // MARK: - Real final (15320337)

    func testTheRealFinalPrintsTheProducersResultAndNoFabricatedBaseline() throws {
        let final = try finalTotal()
        let lost = try XCTUnwrap(Model.content(card: final, optionKey: "o:240505185"))
        let lostPoint = try XCTUnwrap(final.points.first { $0.optionKey == "o:240505185" })
        XCTAssertEqual(lost.title, lostPoint.detail.marketName, "the title is the selected original's own market name")
        XCTAssertEqual(lost.selected, "Over 206.5")
        XCTAssertEqual(lost.readings.map(\.label), ["Pregame chance"], "no Current chance after the final")
        XCTAssertNil(lost.readings[0].value, "the capture serves no pin; none is fabricated")
        XCTAssertEqual(lost.readings[0].text, Model.unavailable)
        XCTAssertEqual(lost.readings[0].marker, .hollow)
        XCTAssertTrue(lost.marks.isEmpty, "no reading, no rail")
        XCTAssertEqual(lost.result, .miss)
        XCTAssertTrue(lost.about.contains(Model.Row(label: "Pregame baseline", value: Model.unavailable)))
        XCTAssertFalse(lost.about.contains { $0.label == "Last recorded probability" }, "a result is not a recorded value")

        let won = try XCTUnwrap(Model.content(card: final, optionKey: "o:240505186"))
        let wonPoint = try XCTUnwrap(final.points.first { $0.optionKey == "o:240505186" })
        XCTAssertEqual(won.title, wonPoint.detail.marketName)
        XCTAssertEqual(won.selected, "Over 204.5")
        XCTAssertEqual(won.result, .hit)
        XCTAssertFalse(Model.spoken(won).contains("%"), "a result never becomes 100%")
    }

    // MARK: - Before tip-off

    func testTheRealPregameMarginReadsTheSelectedTeamsOwnPublishedChance() throws {
        let card = try pregameMargin()
        let selected = try XCTUnwrap(card.points.first { $0.side == .away && $0.chance != nil })
        let content = try XCTUnwrap(Model.content(card: card, optionKey: selected.optionKey))
        let chance = try XCTUnwrap(selected.chance)
        XCTAssertEqual(content.title, selected.detail.marketName, "the title is the selected original's own market name")
        XCTAssertEqual(content.selected, selected.label)
        XCTAssertEqual(content.readings.count, 1)
        XCTAssertEqual(content.readings[0].text, formatProbability(chance))
        XCTAssertEqual(content.readings[0].value, chance, "the raw value, never a complement")
        XCTAssertEqual(content.readings[0].marker, .solid)
        XCTAssertEqual(content.readings[0].time, SourceAge.preciseStamp(selected.observedAt))
        XCTAssertNil(content.result)
    }

    func testBeforeTipOffDetailValuesNeverReplaceOrJoinThePointsChance() {
        // Constructed: Detail disagrees with the Point on purpose.
        let p = point(chance: 0.62, observedAt: t1,
                      detail: detail(quoted: 0.70, observedAt: t2, baseline: 0.40, baselineAt: t1))
        let content = Model.content(card: card(.before, [p]), optionKey: "o:1")!
        XCTAssertEqual(content.readings.map(\.label), ["Pregame chance"])
        XCTAssertEqual(content.readings[0].text, formatProbability(0.62))
        XCTAssertEqual(content.readings[0].time, SourceAge.preciseStamp(t1))
        XCTAssertEqual(content.marks.map(\.value), [0.62])
        XCTAssertFalse(content.about.contains { $0.label == "Pregame baseline" },
                       "no second comparison before tip-off")
        XCTAssertTrue(content.about.contains(Model.Row(
            label: "Last recorded probability",
            value: "\(formatProbability(0.70)), recorded \(SourceAge.preciseStamp(t2)!)")))
        XCTAssertFalse(Model.spoken(content).contains(formatProbability(0.40)))
    }

    func testBeforeTipOffWithoutAChanceSaysSoAndDrawsNoRail() {
        let p = point(chance: nil, observedAt: t1, detail: detail(quoted: 0.70, observedAt: t1))
        let content = Model.content(card: card(.before, [p]), optionKey: "o:1")!
        XCTAssertEqual(content.readings[0].text, Model.noRecentUpdate)
        XCTAssertNil(content.readings[0].time, "an absent reading has no date")
        XCTAssertTrue(content.marks.isEmpty, "the quote is never promoted to a chance")
    }

    // MARK: - During play

    func testDuringPlayPairsTheHollowPregameAndSolidCurrentEachWithItsOwnClock() {
        let p = point(chance: 0.48, now: 0.61, observedAt: t2,
                      detail: detail(quoted: 0.90, observedAt: t1, baseline: 0.30, baselineAt: t1))
        let content = Model.content(card: card(.during, [p]), optionKey: "o:1")!
        XCTAssertEqual(content.readings.map(\.label), ["Pregame chance", "Current chance"])
        XCTAssertEqual(content.readings.map(\.text), [formatProbability(0.48), formatProbability(0.61)])
        XCTAssertEqual(content.readings.map(\.marker), [.hollow, .solid])
        XCTAssertEqual(content.readings.map(\.time), [SourceAge.preciseStamp(t1), SourceAge.preciseStamp(t2)])
        XCTAssertNil(content.result)
        XCTAssertFalse(Model.spoken(content).contains("point"), "no invented delta")
    }

    func testDuringPlayMissingValuesAndDatesStayExplicit() {
        let neither = Model.content(card: card(.during, [point(chance: nil, now: nil)]), optionKey: "o:1")!
        XCTAssertEqual(neither.readings.map(\.text), [Model.unavailable, Model.noRecentUpdate])
        XCTAssertTrue(neither.marks.isEmpty)

        let undated = Model.content(card: card(.during, [point(chance: 0.5, now: 0.55, observedAt: nil)]),
                                    optionKey: "o:1")!
        XCTAssertEqual(undated.readings.map(\.time), [Model.timeUnknown, Model.timeUnknown], "never assumed now")
        XCTAssertEqual(undated.readings[0].dateLine, Model.timeUnknown)
    }

    func testAnExpiredCurrentLosesItsDotButKeepsTheBaseline() {
        let held = card(.during, [point(chance: 0.48, now: 0.61, observedAt: t2,
                                        detail: detail(quoted: 0.61, observedAt: t2, baseline: 0.48, baselineAt: t1))])
        let aged = held.current(at: date("2026-10-17T12:00:00Z"))
        let content = Model.content(card: aged, optionKey: "o:1")!
        XCTAssertEqual(content.readings.map(\.text), [formatProbability(0.48), Model.noRecentUpdate])
        XCTAssertEqual(content.marks.map(\.marker), [.hollow])
        XCTAssertNotNil(aged.points[0].detail.quoted, "retained provenance is not a current chance")
    }

    func testZeroOneAndCoincidentReadingsAreAllMarked() {
        let ends = Model.content(card: card(.during, [point(chance: 0, now: 1, observedAt: t2)]), optionKey: "o:1")!
        XCTAssertEqual(ends.marks.map(\.value), [0, 1], "zero is a reading, not an absence")
        XCTAssertEqual(ends.readings.map(\.text), [formatProbability(0), formatProbability(1)])
        XCTAssertEqual(Model.railX(0, width: 200, inset: 8), 8)
        XCTAssertEqual(Model.railX(1, width: 200, inset: 8), 192)
        XCTAssertEqual(Model.railX(0.625, width: 200, inset: 8), 123, "raw value, not the rounded 63%")

        // Same value at two clocks: two marks, two dates.
        let same = Model.content(card: card(.during, [point(chance: 0.55, now: 0.55, observedAt: t2,
                                                           detail: detail(baselineAt: t1))]), optionKey: "o:1")!
        XCTAssertEqual(same.marks.map(\.marker), [.hollow, .solid])
        XCTAssertEqual(same.marks.map(\.value), [0.55, 0.55])
        XCTAssertNotEqual(same.readings[0].time, same.readings[1].time)
    }

    // MARK: - After the final

    func testTheFinalNeverPrintsACurrentChanceOrTheDetailsResult() {
        let injected = point(chance: 0.58, now: 0.90, observedAt: t2, result: nil,
                             detail: detail(quoted: 0.99, observedAt: t2, baseline: 0.58, baselineAt: t1, result: true))
        let content = Model.content(card: card(.after, [injected]), optionKey: "o:1")!
        XCTAssertEqual(content.readings.map(\.label), ["Pregame chance"])
        XCTAssertEqual(content.marks.map(\.value), [0.58])
        XCTAssertEqual(content.result, .unavailable, "Detail.result never fills Point.result")
        XCTAssertFalse(Model.spoken(content).contains("Current"))
        XCTAssertFalse(Model.spoken(content).contains("Hit"))

        let missed = point(chance: 0.58, result: false, detail: detail(result: true))
        XCTAssertEqual(Model.content(card: card(.after, [missed]), optionKey: "o:1")?.result, .miss)
    }

    func testNoResultBeforeTheFinal() {
        let leaked = point(chance: 0.5, now: 0.6, observedAt: t2, result: true, detail: detail(result: true))
        for phase in [NBALadderCard9483.Phase.before, .during] {
            let content = Model.content(card: card(phase, [leaked]), optionKey: "o:1")!
            XCTAssertNil(content.result)
            XCTAssertFalse(Model.spoken(content).contains("Result"))
        }
    }

    // MARK: - Identity

    func testOnlyTheExactKeyIsShownAndAWithdrawnKeyNamesNoNeighbour() throws {
        let final = try finalTotal()
        let withdrawn = NBALadderCard9483(
            family: final.family, phase: final.phase,
            points: final.points.filter { $0.optionKey != "o:240505185" }, actual: final.actual,
            forecast: final.forecast, awayShort: final.awayShort, homeShort: final.homeShort)
        XCTAssertNil(Model.content(card: withdrawn, optionKey: "o:240505185"))
        XCTAssertNil(Model.content(card: final, optionKey: nil))
        XCTAssertNil(Model.content(card: final, optionKey: "o:missing"))
        XCTAssertNil(Model.content(card: nil, optionKey: "o:240505185"))
        XCTAssertNil(Model.content(card: card(.before, [point(chance: 0.4), point(chance: 0.6)]), optionKey: "o:1"),
                     "an ambiguous key is no selection")
        let spoken = Model.spoken(nil)
        XCTAssertTrue(spoken.hasPrefix(Model.unavailableTitle))
        XCTAssertFalse(spoken.contains("%"))
    }

    // MARK: - Title

    func testTwoOriginalsOnTheSameLineKeepTheirOwnMarketNames() {
        // Constructed: same family, same line, same label — only the market name differs.
        let full = point("o:1", chance: 0.48, observedAt: t1,
                         detail: detail(marketName: "Toronto vs New York: Total Points"))
        let firstHalf = point("o:2", chance: 0.52, observedAt: t1,
                              detail: detail(marketName: "Toronto vs New York: 1st Half Total Points"))
        let both = card(.before, [full, firstHalf])
        let a = Model.content(card: both, optionKey: "o:1")!
        let b = Model.content(card: both, optionKey: "o:2")!
        XCTAssertEqual(a.title, "Toronto vs New York: Total Points")
        XCTAssertEqual(b.title, "Toronto vs New York: 1st Half Total Points")
        XCTAssertEqual(a.selected, b.selected, "the line is shared; only the market name tells them apart")
        XCTAssertTrue(Model.spoken(a).hasPrefix("Toronto vs New York: Total Points. Selected line: Over 210.5."))
        XCTAssertTrue(Model.spoken(b).hasPrefix("Toronto vs New York: 1st Half Total Points. Selected line: Over 210.5."))
        for content in [a, b] {
            XCTAssertNotEqual(content.title, both.title, "the family title never replaces the market name")
            XCTAssertFalse(Model.spoken(content).contains(both.title))
        }

        // An empty name falls back to the family title as a presentation default.
        for empty in ["", "  "] {
            let unnamed = Model.content(card: card(.before, [point(chance: 0.48, observedAt: t1,
                                                                   detail: detail(marketName: empty))]),
                                        optionKey: "o:1")!
            XCTAssertEqual(unnamed.title, "Scoring expectations")
            XCTAssertTrue(Model.spoken(unnamed).hasPrefix("Scoring expectations. Selected line: Over 210.5."))
        }
    }

    // MARK: - Spoken

    func testTheSpokenSummaryNamesEachMeaningValueAndDate() {
        let p = point(chance: 0.48, now: 0.61, observedAt: t2, detail: detail(baselineAt: t1))
        let content = Model.content(card: card(.during, [p]), optionKey: "o:1")!
        XCTAssertEqual(Model.spoken(content),
                       "Toronto vs New York: Total Points. Selected line: Over 210.5. "
                       + "Pregame chance \(formatProbability(0.48)), recorded \(SourceAge.preciseStamp(t1)!). "
                       + "Current chance \(formatProbability(0.61)), recorded \(SourceAge.preciseStamp(t2)!).")
        for word in ["price", "odds", "quote", "question"] {
            XCTAssertFalse(Model.spoken(content).lowercased().contains(word))
            XCTAssertFalse(content.about.map { $0.label.lowercased() }.contains { $0.contains(word) })
        }
    }
}

/// Prepared, not executed. The original-market Details read only what the host
/// resolved for the exact held original: `Mode`, the owner's figure text,
/// placement and provenance, the owner's grade words and rules.
///
/// Retained (accepted source packets for KXTESTMATCH-26OCT090330AUSSA): the
/// three originals' titles, outcomes, verbatim `rules_primary`, pregame
/// baselines 48/47/9, the four recorded frames' values, and the separate
/// settlement 2026-10-13T12:35:49.612166Z (SA No / AUS Yes / TIE No). Every
/// display word, figure text, provenance and calendar line, scope, identity and
/// every unknown/void/malformed/width case is CONSTRUCTED owner input — no
/// internal app ids exist for these rows. Geometry, fit at 320/375/393/wide,
/// and VoiceOver focus are NOT asserted here.
@MainActor
final class OriginalMarketDetails9483Tests: XCTestCase {
    private typealias M = OriginalMarketDetails9483

    private struct Frame {
        let text: String
        let value: Double
        let provenance: String
    }

    private struct Retained {
        let side: String
        let title: String
        let outcome: String
        let rules: String
        let pregameText: String
        let pregame: Double
        let gradeWords: String
        let frames: [Frame]
    }

    // CONSTRUCTED scope + owner calendar lines (EDT is UTC−4 in October).
    private let scope = "constructed:cricket-live:KXTESTMATCH-26OCT090330AUSSA:match-winner"
    private let pregameProvenance = "Kalshi · period ending Thu, Oct 8, 2026, 8:00 PM EDT"
    private let settled = "Kalshi settled Tue, Oct 13, 2026, 8:35:49 AM EDT"

    private func frame(_ text: String, _ value: Double, _ clock: String, _ label: String) -> Frame {
        Frame(text: text, value: value,
              provenance: "Kalshi · 1-minute period ending Tue, Oct 13, 2026, \(clock) AM EDT · \(label)")
    }

    private var retained: [Retained] {
        [
            Retained(side: "SA", title: "South Africa wins", outcome: "South Africa",
                     rules: "If South Africa wins the South Africa vs Australia men's professional Test series cricket match originally scheduled for Oct 9, 2026 at 3:30 AM EDT, then the market resolves to Yes.",
                     pregameText: "48%", pregame: 0.48, gradeWords: "Resolved No",
                     frames: [frame("3%", 0.03, "5:11", "Day 5 · 64 overs"),
                              frame("1%", 0.01, "5:46", "Day 5 · lunch"),
                              frame("2%", 0.02, "7:03", "Day 5 · 84 overs"),
                              frame("1%", 0.01, "7:09", "Day 5 · 85 overs")]),
            Retained(side: "AUS", title: "Australia wins", outcome: "Australia",
                     rules: "If Australia wins the South Africa vs Australia men's professional Test series cricket match originally scheduled for Oct 9, 2026 at 3:30 AM EDT, then the market resolves to Yes.",
                     pregameText: "47%", pregame: 0.47, gradeWords: "Resolved Yes",
                     frames: [frame("64%", 0.64, "5:11", "Day 5 · 64 overs"),
                              frame("87%", 0.87, "5:48", "Day 5 · lunch"),
                              frame("79%", 0.79, "7:03", "Day 5 · 84 overs"),
                              frame("95%", 0.95, "7:11", "Day 5 · 85 overs")]),
            Retained(side: "TIE", title: "Draw/Tie wins", outcome: "Draw/Tie",
                     rules: "If South Africa and Australia draw or tie in the South Africa vs Australia men's professional Test series cricket match originally scheduled for Oct 9, 2026 at 3:30 AM EDT, then the market resolves to Yes.",
                     pregameText: "9%", pregame: 0.09, gradeWords: "Resolved No",
                     frames: [frame("35%", 0.35, "5:11", "Day 5 · 64 overs"),
                              frame("17%", 0.17, "5:45", "Day 5 · lunch"),
                              frame("20%", 0.20, "7:02", "Day 5 · 84 overs"),
                              frame("3%", 0.03, "7:11", "Day 5 · 85 overs")]),
        ]
    }

    private func identity(_ side: String, _ outcomeSide: String = "Yes") -> M.Identity {
        M.Identity(source: "kalshi", market: "KXTESTMATCH-26OCT090330AUSSA-\(side)", side: outcomeSide)
    }

    private func about(_ r: Retained, rules: M.Rules? = nil, provenance: [M.Row] = [],
                       quote: M.HistoricalQuote? = nil) -> M.About {
        M.About(source: "Kalshi · KXTESTMATCH-26OCT090330AUSSA-\(r.side)", rules: rules ?? .verified([r.rules]),
                provenance: provenance, historicalQuote: quote)
    }

    private func original(_ r: Retained, _ mode: M.Mode, pregame: M.Reading? = nil, later: M.Reading? = nil,
                          grade: M.Grade? = nil, about: M.About? = nil,
                          title: String? = nil, outcome: String? = nil,
                          identity: M.Identity? = nil) -> M.Original {
        M.Original(identity: identity ?? self.identity(r.side), title: title ?? r.title,
                   outcome: outcome ?? r.outcome, mode: mode,
                   pregame: pregame ?? .value(r.pregameText, placement: r.pregame, provenance: pregameProvenance),
                   later: later, grade: grade, about: about ?? self.about(r))
    }

    private func selection(_ side: String, scope: String? = nil, outcomeSide: String = "Yes") -> M.Selection {
        M.Selection(scope: scope ?? self.scope, identity: identity(side, outcomeSide))
    }

    private func content(_ originals: [M.Original], _ side: String) -> M.Content? {
        M.content(catalogue: M.Catalogue(scope: scope, originals: originals), selection: selection(side))
    }

    private func only(_ o: M.Original) -> M.Content {
        M.content(catalogue: M.Catalogue(scope: scope, originals: [o]),
                  selection: M.Selection(scope: scope, identity: o.identity))!
    }

    private func recorded(_ f: Frame) -> M.Reading { .value(f.text, placement: f.value, provenance: f.provenance) }

    // MARK: - The three retained originals

    func testEachRetainedOriginalOpensWithItsOwnTitleOutcomeAndPregameChance() {
        let all = retained.map { original($0, .pregame) }
        for r in retained {
            let c = content(all, r.side)!
            XCTAssertEqual(c.title, r.title)
            XCTAssertEqual(c.outcome, r.outcome)
            XCTAssertEqual(c.readings.map(\.label), [M.pregameLabel])
            XCTAssertEqual(c.readings[0].text, r.pregameText, "the owner's figure, printed verbatim")
            XCTAssertEqual(c.readings[0].marker, .solid, "a lone published reading is solid")
            XCTAssertEqual(c.readings[0].provenance, pregameProvenance)
            XCTAssertEqual(c.marks.map(\.placement), [r.pregame], "the raw value, never a complement")
            XCTAssertNil(c.result)
            XCTAssertEqual(c.rules, .verified([r.rules]))
        }
        // Three independent Yes contracts: no normalising to 100.
        XCTAssertEqual(retained.map { content(all, $0.side)!.readings[0].text }, ["48%", "47%", "9%"])
    }

    func testFourRecordedFramesEachPairWithTheOriginalsOwnBaseline() {
        for r in retained {
            XCTAssertEqual(r.frames.count, 4)
            for f in r.frames {
                let c = only(original(r, .comparison(.recorded), later: recorded(f)))
                XCTAssertEqual(c.readings.map(\.label), [M.pregameLabel, "Recorded chance"])
                XCTAssertEqual(c.readings.map(\.text), [r.pregameText, f.text])
                XCTAssertEqual(c.readings.map(\.marker), [.hollow, .solid])
                XCTAssertEqual(c.readings.map(\.provenance), [pregameProvenance, f.provenance],
                               "each reading carries its own clock and source")
                XCTAssertEqual(c.marks.map(\.placement), [r.pregame, f.value])
                XCTAssertNil(c.result)
                XCTAssertFalse(M.spoken(c).contains("point"), "no invented delta")
            }
        }
        let live = only(original(retained[1], .comparison(.current), later: recorded(retained[1].frames[3])))
        XCTAssertEqual(live.readings[1].label, "Current chance")
    }

    func testResultModePairsThePregameChanceWithTheOriginalsOwnSettledResult() {
        for r in retained {
            let c = only(original(r, .result, grade: M.Grade(words: r.gradeWords, provenance: settled)))
            XCTAssertEqual(c.readings.map(\.label), [M.pregameLabel], "no current chance beside a result")
            XCTAssertEqual(c.readings[0].marker, .hollow)
            XCTAssertEqual(c.marks.map(\.placement), [r.pregame], "the result draws no mark")
            XCTAssertEqual(c.result, M.ShownResult(words: r.gradeWords, provenance: settled))
            let spoken = M.spoken(c)
            XCTAssertTrue(spoken.contains("\(M.resultLabel): \(r.gradeWords), \(settled)"))
            for word in ["100%", "Hit", "Miss", "Winner", "Lost", "7:24", "7:26"] {
                XCTAssertFalse(spoken.contains(word), "\(word) is not this original's result or clock")
            }
        }
    }

    // MARK: - Mode is the market's, not the game's

    func testEachModeSuppressesTheFieldsItDoesNotShow() {
        let r = retained[0]
        let later = recorded(r.frames[2])
        let grade = M.Grade(words: r.gradeWords, provenance: settled)

        let pregame = only(original(r, .pregame, later: later, grade: grade))
        XCTAssertEqual(pregame.readings.count, 1)
        XCTAssertNil(pregame.result)

        let comparison = only(original(r, .comparison(.current), later: later, grade: grade))
        XCTAssertNil(comparison.result, "a supplied later grade stays hidden outside result mode")
        XCTAssertFalse(M.spoken(comparison).contains(r.gradeWords))
        XCTAssertFalse(M.spoken(comparison).contains(settled))

        let result = only(original(r, .result, later: later, grade: grade))
        XCTAssertEqual(result.readings.map(\.label), [M.pregameLabel], "result mode ignores a current chance")
        XCTAssertFalse(M.spoken(result).contains(r.frames[2].provenance))
        XCTAssertFalse(M.spoken(result).contains("Current"))
    }

    func testTheOriginalsGradeIsItsOwnAndNeverTheMatchOutcome() {
        // CONSTRUCTED: the match is over (Australia won by 214 runs) but the
        // owner has not admitted SA's grade — the leaf shows the owner's words.
        let sa = retained[0]
        let pending = only(original(sa, .result, grade: M.Grade(words: "Not yet confirmed", provenance: nil)))
        XCTAssertEqual(pending.result?.words, "Not yet confirmed")
        XCTAssertFalse(M.spoken(pending).contains("Resolved No"))
        XCTAssertFalse(M.spoken(pending).contains("Lost"))

        // CONSTRUCTED: a settled original while its game is still live — the
        // owner chose result mode; nothing here reads a game phase.
        let tie = retained[2]
        let early = only(original(tie, .result, later: recorded(tie.frames[0]),
                                  grade: M.Grade(words: "Resolved No", provenance: settled)))
        XCTAssertEqual(early.result?.words, "Resolved No")

        // CONSTRUCTED: the match finished but the owner keeps the market open.
        let open = only(original(sa, .comparison(.recorded), later: recorded(sa.frames[3]),
                                 grade: M.Grade(words: "Resolved No", provenance: settled)))
        XCTAssertNil(open.result)
    }

    func testUnknownVoidAndMissingGradesAreNeverALossOrZero() {
        let r = retained[2]
        for words in ["Void", "Not yet confirmed", "Unknown"] {
            let c = only(original(r, .result, grade: M.Grade(words: words, provenance: nil)))
            XCTAssertEqual(c.result?.words, words)
            XCTAssertFalse(M.spoken(c).contains("Resolved No"))
            XCTAssertFalse(M.spoken(c).contains("0%"))
        }
        for grade in [nil, M.Grade(words: "", provenance: settled), M.Grade(words: " \n", provenance: nil)] {
            let c = only(original(r, .result, grade: grade))
            XCTAssertEqual(c.result, M.ShownResult(words: M.resultUnavailable, provenance: nil))
        }
    }

    func testAMissingSettlementClockStaysUnknown() {
        let r = retained[1]
        // CONSTRUCTED: the matrix quote clock is in About; it is not a grade clock.
        let c = only(original(r, .result, grade: M.Grade(words: "Resolved Yes", provenance: nil),
                              about: about(r, provenance: [M.Row(label: "Quote observed",
                                                                 value: "Tue, Oct 13, 2026, 7:11 AM EDT")])))
        XCTAssertEqual(c.result?.provenance, M.resultTimeUnknown)
        XCTAssertTrue(M.spoken(c).hasSuffix("\(M.resultLabel): Resolved Yes, \(M.resultTimeUnknown)."))
        XCTAssertFalse(M.spoken(c).contains("7:11"))
    }

    // MARK: - Readings

    func testMissingAndWithheldReadingsKeepTheirOwnSlotsAndRealZeroIsAValue() {
        let r = retained[1]
        let f = r.frames[0]
        let withheld = only(original(r, .comparison(.recorded), pregame: .missing("Withheld: too few trades"),
                                     later: recorded(f)))
        XCTAssertEqual(withheld.readings.map(\.text), ["Withheld: too few trades", f.text])
        XCTAssertEqual(withheld.readings.map(\.isValue), [false, true])
        XCTAssertNil(withheld.readings[0].provenance, "a missing reading has no date")
        XCTAssertEqual(withheld.marks.map(\.label), ["Recorded chance"], "neither slot borrows the other")

        let noLater = only(original(r, .comparison(.current), later: nil))
        XCTAssertEqual(noLater.readings.map(\.text), [r.pregameText, M.unavailable])
        XCTAssertEqual(noLater.marks.count, 1)

        for bad in [M.Reading.missing(""), .value("", placement: 0.5, provenance: pregameProvenance),
                    .value("  ", placement: nil, provenance: nil)] {
            let c = only(original(r, .pregame, pregame: bad))
            XCTAssertEqual(c.readings[0].text, M.unavailable)
            XCTAssertFalse(c.readings[0].isValue)
            XCTAssertTrue(c.marks.isEmpty, "no figure, no mark — never zero")
        }

        let zero = only(original(r, .pregame, pregame: .value("0%", placement: 0, provenance: pregameProvenance)))
        XCTAssertTrue(zero.readings[0].isValue, "0% is a reading, not an absence")
        XCTAssertEqual(zero.marks.map(\.placement), [0])

        let undated = only(original(r, .pregame, pregame: .value("47%", placement: 0.47, provenance: nil)))
        XCTAssertEqual(undated.readings[0].provenance, M.timeUnknown, "never assumed now")
    }

    func testEqualValuesFromDistinctObservationsStaySeparate() {
        let r = retained[2]
        let a = "Kalshi · period ending Thu, Oct 8, 2026, 8:00 PM EDT"
        let b = "Kalshi · 1-minute period ending Tue, Oct 13, 2026, 5:45 AM EDT · Day 5 · lunch"
        let c = only(original(r, .comparison(.recorded), pregame: .value("17%", placement: 0.17, provenance: a),
                              later: .value("17%", placement: 0.17, provenance: b)))
        XCTAssertEqual(c.readings.map(\.text), ["17%", "17%"])
        XCTAssertEqual(c.marks.map(\.marker), [.hollow, .solid], "concentric, both drawn")
        XCTAssertEqual(c.readings.map(\.provenance), [a, b])
    }

    func testRailPlacementIsGeometryOnly() {
        let r = retained[0]
        let ends = only(original(r, .comparison(.recorded), pregame: .value("0%", placement: 0, provenance: "a"),
                                 later: .value("100%", placement: 1, provenance: "b")))
        XCTAssertEqual(ends.marks.map(\.placement), [0, 1])
        XCTAssertEqual(LadderOriginalProbabilityDetails9483.railX(0, width: 200, inset: 8), 8, "endpoints drawn whole")
        XCTAssertEqual(LadderOriginalProbabilityDetails9483.railX(1, width: 200, inset: 8), 192)

        let invalid: [Double?] = [Double.nan, Double.infinity, -Double.infinity, -0.01, 1.01, nil]
        for bad in invalid {
            let c = only(original(r, .pregame, pregame: .value("48%", placement: bad, provenance: pregameProvenance)))
            XCTAssertEqual(c.readings[0].text, "48%", "the figure still shows")
            XCTAssertTrue(c.readings[0].isValue)
            XCTAssertNil(c.readings[0].placement, "no clamped mark")
            XCTAssertTrue(c.marks.isEmpty)
        }
        XCTAssertNil(M.railPlacement(1.0000001))
        XCTAssertEqual(M.railPlacement(0.5), 0.5)
    }

    // MARK: - About

    func testTheHistoricalQuoteStaysDatedInAboutAndNeverLeadsOrMarks() {
        let r = retained[0]
        let quote = M.HistoricalQuote(text: "2%", recorded: "Tue, Oct 13, 2026, 7:03 AM EDT")
        let c = only(original(r, .pregame, about: about(r, quote: quote)))
        XCTAssertEqual(c.about.last, M.Row(label: M.historicalLabel, value: "2%, recorded Tue, Oct 13, 2026, 7:03 AM EDT"))
        XCTAssertEqual(c.readings.map(\.text), [r.pregameText])
        XCTAssertEqual(c.marks.map(\.placement), [r.pregame])
        XCTAssertFalse(M.spoken(c).contains("2%"))

        let missing = only(original(r, .comparison(.current), pregame: .missing("Unavailable"), later: nil,
                                    about: about(r, quote: M.HistoricalQuote(text: "2%", recorded: nil))))
        XCTAssertEqual(missing.readings.map(\.text), [M.unavailable, M.unavailable], "the quote fills no slot")
        XCTAssertTrue(missing.marks.isEmpty)
        XCTAssertEqual(missing.about.last?.value, "2%, time unknown")
    }

    func testAboutCarriesTitleOutcomeSourceAndOnlyTheOwnersProvenance() {
        let r = retained[1]
        let rows = [M.Row(label: "Pregame reading", value: pregameProvenance), M.Row(label: "", value: "x"),
                    M.Row(label: "Blank", value: " ")]
        let c = only(original(r, .pregame, about: about(r, provenance: rows)))
        XCTAssertEqual(c.about, [M.Row(label: "Market", value: "Australia wins"),
                                 M.Row(label: "Outcome", value: "Australia"),
                                 M.Row(label: "Source", value: "Kalshi · KXTESTMATCH-26OCT090330AUSSA-AUS"),
                                 M.Row(label: "Pregame reading", value: pregameProvenance)])
        XCTAssertFalse(c.about.contains { $0.value.lowercased().contains("finalized") },
                       "no fetched-later status is admitted by the leaf")
    }

    func testRulesAreVerifiedTextOwnerUnavailableWordsOrOmitted() {
        let r = retained[2]
        XCTAssertEqual(only(original(r, .pregame)).rules, .verified([r.rules]), "rules_primary verbatim")
        for empty in [M.Rules.verified([]), .verified(["", "  \n"]), .unavailable(" "), .omitted] {
            XCTAssertEqual(only(original(r, .pregame, about: about(r, rules: empty))).rules, .omitted)
        }
        XCTAssertEqual(only(original(r, .pregame, about: about(r, rules: .verified(["", r.rules])))).rules,
                       .verified([r.rules]))
        let words = "Rules aren't available for this market yet."
        XCTAssertEqual(only(original(r, .pregame, about: about(r, rules: .unavailable(words)))).rules,
                       .unavailable(words))
        let long = Array(repeating: r.rules, count: 40).joined(separator: " ")
        guard case .verified(let kept) = only(original(r, .pregame, about: about(r, rules: .verified([long, r.rules])))).rules
        else { return XCTFail("verified rules expected") }
        XCTAssertEqual(kept.map(\.count), [long.count, r.rules.count], "long rules are kept whole")
    }

    // MARK: - Identity

    func testOnlyTheExactSelectedOriginalInItsScopeIsShown() {
        let all = retained.map { original($0, .pregame) }
        let catalogue = M.Catalogue(scope: scope, originals: all)
        XCTAssertEqual(M.content(catalogue: catalogue, selection: selection("SA"))?.title, "South Africa wins")
        XCTAssertEqual(M.content(catalogue: catalogue, selection: selection("AUS"))?.title, "Australia wins")
        XCTAssertNil(M.content(catalogue: catalogue, selection: nil))
        XCTAssertNil(M.content(catalogue: nil, selection: selection("SA")))
        XCTAssertNil(M.content(catalogue: catalogue, selection: selection("SA", scope: "constructed:other-event")),
                     "a selection from another scope is no selection")
        XCTAssertNil(M.content(catalogue: catalogue, selection: selection("SA", outcomeSide: "No")))
        XCTAssertNil(M.content(catalogue: catalogue, selection: selection("ENG")))

        let withdrawn = M.Catalogue(scope: scope, originals: all.filter { $0.identity != identity("SA") })
        XCTAssertNil(M.content(catalogue: withdrawn, selection: selection("SA")), "withdrawn names no neighbour")

        let duplicated = M.Catalogue(scope: scope, originals: all + [original(retained[1], .pregame,
                                                                               identity: identity("SA"))])
        XCTAssertNil(M.content(catalogue: duplicated, selection: selection("SA")), "an ambiguous identity is no selection")

        let blankScope = M.Catalogue(scope: " ", originals: all)
        XCTAssertNil(M.content(catalogue: blankScope, selection: selection("SA", scope: " ")))
        let blankSide = M.Catalogue(scope: scope, originals: [original(retained[0], .pregame, identity: identity("SA", ""))])
        XCTAssertNil(M.content(catalogue: blankSide, selection: selection("SA", outcomeSide: "")))

        let spoken = M.spoken(nil)
        XCTAssertTrue(spoken.hasPrefix(LadderOriginalProbabilityDetails9483.unavailableTitle))
        XCTAssertFalse(spoken.contains("%"))
    }

    func testAMalformedTitleOrOutcomeIsUnavailableNeverAnotherName() {
        let r = retained[0]
        XCTAssertNil(content([original(r, .pregame, title: "  ")], "SA"))
        XCTAssertNil(content([original(r, .pregame, outcome: "")], "SA"))
    }

    // MARK: - Layout decision

    func testReadingPairsStackAtAccessibilitySizesAndALoneReadingNeverPairs() {
        XCTAssertTrue(ProbabilityDetailsLayout9483.alwaysStacks(readings: 1, accessibilitySize: false))
        XCTAssertTrue(ProbabilityDetailsLayout9483.alwaysStacks(readings: 2, accessibilitySize: true))
        // Two readings at ordinary sizes are left to ViewThatFits (side by side
        // only when both fit whole at 320/375/393/wide) — not asserted here.
        XCTAssertFalse(ProbabilityDetailsLayout9483.alwaysStacks(readings: 2, accessibilitySize: false))
    }

    // MARK: - Spoken

    func testTheSpokenSummaryNamesTitleOutcomeEachReadingAndTheResult() {
        let r = retained[1]
        let f = r.frames[1]
        let comparison = only(original(r, .comparison(.recorded), later: recorded(f)))
        XCTAssertEqual(M.spoken(comparison),
                       "Australia wins. Selected outcome: Australia. "
                       + "Pregame chance 47%, \(pregameProvenance). Recorded chance 87%, \(f.provenance).")
        let result = only(original(r, .result, grade: M.Grade(words: "Resolved Yes", provenance: settled)))
        XCTAssertEqual(M.spoken(result),
                       "Australia wins. Selected outcome: Australia. Pregame chance 47%, \(pregameProvenance). "
                       + "Original market result: Resolved Yes, \(settled).")
        for word in ["price", "odds", "quote", "bookmaker"] {
            XCTAssertFalse(M.spoken(result).lowercased().contains(word))
        }
    }
}
