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

/// Prepared, not executed. The chooser draws every supplied original as one
/// choice in the owner's order, acts only through the Details' own
/// `content(catalogue:selection:)` contract, hands back the exact scope and
/// identity, and leaves the held selection's Details to the existing view.
///
/// Retained (accepted source packets): T20 KXT20MATCH-26OCT090930WIIND —
/// titles, outcomes, verbatim `rules_primary`/`rules_secondary`, pregame
/// 78/23 (bar ending 12:57:00Z), the 15-over recorded 67/34 (bar ending
/// 16:57:00Z) and the separate settlement 2026-10-09T17:45:23.67777Z (IND No,
/// WI Yes); Test KXTESTMATCH-26OCT090330AUSSA — titles, outcomes,
/// `rules_primary`, pregame 48/47/9, the last recorded frame 1/95/3 and the
/// settlement 2026-10-13T12:35:49.612166Z. Public tickers are provenance only.
/// CONSTRUCTED owner input: the scope, every identity (`constructed:` market
/// keys — no production app ids exist for these rows), choice labels, grade
/// words, empty/unavailable words and calendar lines (EDT is UTC−4 in
/// October), and every malformed/withdrawn/refresh/width case. Taps go
/// through `OriginalMarketChooser9483.action`, the closure the view's buttons
/// run. Geometry, wrapping at 320/375/393/wide, hosting and VoiceOver focus
/// are NOT asserted here.
@MainActor
final class OriginalMarketChooser9483Tests: XCTestCase {
    private typealias C = OriginalMarketChooser9483
    private typealias M = OriginalMarketDetails9483

    private struct Spec {
        let key: String
        let title: String
        let outcome: String
        let rules: [String]
        let pregameText: String
        let pregame: Double
        let pregameProvenance: String
        let laterText: String
        let later: Double
        let laterProvenance: String
        let grade: M.Grade
    }

    private let scope = "constructed:cricket:held-owner-scope"
    private let unavailableChoice = "Outcome unavailable in this update"

    private static let t20Secondary = "If the India vs West Indies men's professional West Indies Tour of India T20s cricket match originally scheduled for Oct 9, 2026 at 9:30 AM EDT ends in a tie, draw, no result (NR), abandonment, or cancellation, and no official winner is declared, all markets will resolve to $0.50.\nIn the event of a forfeit, disqualification, or concession:\n  If it occurs before the match begins, all markets will resolve to $0.50.\n  If it occurs after the match has begun, and the governing body declares an official winner, the market will resolve based on that result.\nIf play begins but insufficient play occurs to determine an official result, all markets will resolve to $0.50.\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners."
    private static let t20Pregame = "Kalshi · 1-minute period ending Fri, Oct 9, 2026, 8:57 AM EDT"
    private static let t20Recorded = "Kalshi · 1-minute period ending Fri, Oct 9, 2026, 12:57 PM EDT · 15 overs"
    private static let t20Settled = "Kalshi settled Fri, Oct 9, 2026, 1:45:23 PM EDT"
    private static let testPregame = "Kalshi · period ending Thu, Oct 8, 2026, 8:00 PM EDT"
    private static let testSettled = "Kalshi settled Tue, Oct 13, 2026, 8:35:49 AM EDT"

    private var t20: [Spec] {
        [
            Spec(key: "t20-india", title: "India wins", outcome: "India",
                 rules: ["If India wins the India vs West Indies men's professional West Indies Tour of India T20s cricket match originally scheduled for Oct 9, 2026 at 9:30 AM EDT, then the market resolves to Yes.",
                         Self.t20Secondary],
                 pregameText: "78%", pregame: 0.78, pregameProvenance: Self.t20Pregame,
                 laterText: "67%", later: 0.67, laterProvenance: Self.t20Recorded,
                 grade: M.Grade(words: "Lost", provenance: Self.t20Settled)),
            Spec(key: "t20-west-indies", title: "West Indies wins", outcome: "West Indies",
                 rules: ["If West Indies wins the India vs West Indies men's professional West Indies Tour of India T20s cricket match originally scheduled for Oct 9, 2026 at 9:30 AM EDT, then the market resolves to Yes.",
                         Self.t20Secondary],
                 pregameText: "23%", pregame: 0.23, pregameProvenance: Self.t20Pregame,
                 laterText: "34%", later: 0.34, laterProvenance: Self.t20Recorded,
                 grade: M.Grade(words: "Won", provenance: Self.t20Settled)),
        ]
    }

    private var threeWay: [Spec] {
        let last = "Day 5 · 85 overs"
        return [
            Spec(key: "test-south-africa", title: "South Africa wins", outcome: "South Africa",
                 rules: ["If South Africa wins the South Africa vs Australia men's professional Test series cricket match originally scheduled for Oct 9, 2026 at 3:30 AM EDT, then the market resolves to Yes."],
                 pregameText: "48%", pregame: 0.48, pregameProvenance: Self.testPregame,
                 laterText: "1%", later: 0.01,
                 laterProvenance: "Kalshi · 1-minute period ending Tue, Oct 13, 2026, 7:09 AM EDT · \(last)",
                 grade: M.Grade(words: "Resolved No", provenance: Self.testSettled)),
            Spec(key: "test-australia", title: "Australia wins", outcome: "Australia",
                 rules: ["If Australia wins the South Africa vs Australia men's professional Test series cricket match originally scheduled for Oct 9, 2026 at 3:30 AM EDT, then the market resolves to Yes."],
                 pregameText: "47%", pregame: 0.47, pregameProvenance: Self.testPregame,
                 laterText: "95%", later: 0.95,
                 laterProvenance: "Kalshi · 1-minute period ending Tue, Oct 13, 2026, 7:11 AM EDT · \(last)",
                 grade: M.Grade(words: "Resolved Yes", provenance: Self.testSettled)),
            Spec(key: "test-draw-tie", title: "Draw/Tie wins", outcome: "Draw/Tie",
                 rules: ["If South Africa and Australia draw or tie in the South Africa vs Australia men's professional Test series cricket match originally scheduled for Oct 9, 2026 at 3:30 AM EDT, then the market resolves to Yes."],
                 pregameText: "9%", pregame: 0.09, pregameProvenance: Self.testPregame,
                 laterText: "3%", later: 0.03,
                 laterProvenance: "Kalshi · 1-minute period ending Tue, Oct 13, 2026, 7:11 AM EDT · \(last)",
                 grade: M.Grade(words: "Resolved No", provenance: Self.testSettled)),
        ]
    }

    /// CONSTRUCTED identity — never looked up from a retained spec.
    private func id(_ key: String, side: String = "Yes") -> M.Identity {
        M.Identity(source: "kalshi", market: "constructed:original:\(key)", side: side)
    }

    private func original(_ s: Spec, _ mode: M.Mode, identity: M.Identity? = nil, title: String? = nil,
                          outcome: String? = nil, pregame: M.Reading? = nil) -> M.Original {
        M.Original(identity: identity ?? id(s.key), title: title ?? s.title, outcome: outcome ?? s.outcome,
                   mode: mode,
                   pregame: pregame ?? .value(s.pregameText, placement: s.pregame, provenance: s.pregameProvenance),
                   later: .value(s.laterText, placement: s.later, provenance: s.laterProvenance),
                   grade: s.grade,
                   about: M.About(source: "Kalshi", rules: .verified(s.rules), provenance: [], historicalQuote: nil))
    }

    private func catalogue(_ originals: [M.Original], scope: String? = nil) -> M.Catalogue {
        M.Catalogue(scope: scope ?? self.scope, originals: originals)
    }

    private func held(_ key: String, scope: String? = nil, side: String = "Yes") -> M.Selection {
        M.Selection(scope: scope ?? self.scope, identity: id(key, side: side))
    }

    private func choices(_ catalogue: M.Catalogue?, _ selection: M.Selection? = nil,
                         labels: [M.Identity: String] = [:]) -> [C.Choice] {
        C.choices(catalogue: catalogue, selection: selection, labels: labels, unavailableChoice: unavailableChoice)
    }

    /// Taps a choice exactly as its button does; nil when it has no button.
    private func tap(_ choice: C.Choice) -> M.Selection? {
        var handed: [M.Selection] = []
        guard let action = C.action(choice, onSelect: { handed.append($0) }) else { return nil }
        action()
        XCTAssertEqual(handed.count, 1, "one tap, one proposal")
        return handed.first
    }

    // MARK: - Every original, in the owner's order

    func testTwoAndThreeRetainedOriginalsAreChoicesInTheOwnersOrderWithTheirOwnTitles() {
        for specs in [t20, threeWay] {
            let all = specs.map { original($0, .pregame) }
            let shown = choices(catalogue(all))
            XCTAssertEqual(shown.map(\.label), specs.map(\.title), "titles verbatim, owner order")
            XCTAssertTrue(shown.allSatisfy(\.isAvailable))
            XCTAssertFalse(shown.contains(where: \.isSelected), "no held selection, no first-row election")
            XCTAssertTrue(shown.allSatisfy { $0.status == nil })

            let reversed = choices(catalogue(all.reversed()))
            XCTAssertEqual(reversed.map(\.label), specs.reversed().map(\.title), "never sorted by name or chance")
        }
        XCTAssertEqual(choices(catalogue(threeWay.map { original($0, .pregame) })).map(\.label),
                       ["South Africa wins", "Australia wins", "Draw/Tie wins"],
                       "no inferred draw, nothing capped")
    }

    func testOwnerLabelsAreKeyedByExactIdentityAndOtherwiseTheTitleIsUsedVerbatim() {
        let t20All = t20.map { original($0, .pregame) }
        let t20Labels = [id("t20-india"): "India", id("t20-west-indies"): "West Indies"]
        XCTAssertEqual(choices(catalogue(t20All), labels: t20Labels).map(\.label), ["India", "West Indies"])

        let testAll = threeWay.map { original($0, .pregame) }
        let testLabels = [id("test-south-africa"): "South Africa", id("test-australia"): "Australia",
                          id("test-draw-tie"): "Draw/tie"]
        XCTAssertEqual(choices(catalogue(testAll), labels: testLabels).map(\.label),
                       ["South Africa", "Australia", "Draw/tie"])

        // A blank label, or one keyed by another side/market, never replaces the title.
        let partial = [id("test-south-africa"): "  ", id("test-australia", side: "No"): "Australia (No)",
                       id("constructed-invented"): "England"]
        XCTAssertEqual(choices(catalogue(testAll), labels: partial).map(\.label),
                       ["South Africa wins", "Australia wins", "Draw/Tie wins"])

        // An unreadable label and title fall back to the owner's words — no subject invented.
        let untitled = original(threeWay[0], .pregame, title: " ")
        XCTAssertEqual(choices(catalogue([untitled])).map(\.label), [unavailableChoice])
        XCTAssertEqual(C.choices(catalogue: catalogue([untitled]), selection: nil, labels: [:],
                                 unavailableChoice: "").map(\.label), [C.unavailableStatus])
    }

    // MARK: - The held selection and its own Details

    func testTheHeldSelectionIsMarkedAndOpensItsOwnDetailsInEveryMode() {
        for specs in [t20, threeWay] {
            for mode in [M.Mode.pregame, .comparison(.recorded), .result] {
                let all = catalogue(specs.map { original($0, mode) })
                for (index, s) in specs.enumerated() {
                    let selection = held(s.key)
                    let shown = choices(all, selection)
                    XCTAssertEqual(shown.map(\.isSelected), specs.indices.map { $0 == index }, "\(s.key) \(mode)")

                    let c = M.content(catalogue: all, selection: selection)!
                    XCTAssertEqual(c.title, s.title)
                    XCTAssertEqual(c.outcome, s.outcome)
                    XCTAssertEqual(c.rules, .verified(s.rules), "full rules, verbatim")
                    let spoken = M.spoken(c)
                    switch mode {
                    case .pregame:
                        XCTAssertEqual(c.readings.map(\.text), [s.pregameText])
                        XCTAssertEqual(c.readings.map(\.provenance), [s.pregameProvenance])
                        XCTAssertNil(c.result)
                        XCTAssertFalse(spoken.contains(s.laterText + ","), "a supplied later reading stays hidden")
                    case .comparison:
                        XCTAssertEqual(c.readings.map(\.label), [M.pregameLabel, "Recorded chance"])
                        XCTAssertEqual(c.readings.map(\.text), [s.pregameText, s.laterText])
                        XCTAssertEqual(c.readings.map(\.provenance), [s.pregameProvenance, s.laterProvenance])
                        XCTAssertNil(c.result, "a supplied grade stays hidden")
                        XCTAssertFalse(spoken.contains(s.grade.words))
                    case .result:
                        XCTAssertEqual(c.readings.map(\.text), [s.pregameText], "no later chance beside a result")
                        XCTAssertEqual(c.result, M.ShownResult(words: s.grade.words, provenance: s.grade.provenance))
                        XCTAssertFalse(spoken.contains(s.laterProvenance))
                    }
                }
            }
        }
        // Independent Yes contracts: never normalised or complemented.
        let pregame = catalogue(t20.map { original($0, .pregame) })
        XCTAssertEqual(t20.map { M.content(catalogue: pregame, selection: held($0.key))!.readings[0].text },
                       ["78%", "23%"])
        let recorded = catalogue(t20.map { original($0, .comparison(.recorded)) })
        XCTAssertEqual(t20.map { M.content(catalogue: recorded, selection: held($0.key))!.readings[1].text },
                       ["67%", "34%"])
    }

    // MARK: - Actions

    func testATapHandsBackTheExactScopeAndIdentityThroughTheButtonsOwnAction() {
        // CONSTRUCTED: an odd but valid owner scope is copied, never rebuilt.
        let oddScope = "constructed:cricket:held-owner-scope / Test #2 (v3)"
        for specs in [t20, threeWay] {
            let all = catalogue(specs.map { original($0, .result) }, scope: oddScope)
            let heldFirst = M.Selection(scope: oddScope, identity: id(specs[0].key))
            let shown = choices(all, heldFirst)
            for (choice, s) in zip(shown, specs) {
                let handed = tap(choice)
                XCTAssertEqual(handed, M.Selection(scope: oddScope, identity: id(s.key)))
                XCTAssertEqual(handed.flatMap { M.content(catalogue: all, selection: $0) }?.title, s.title,
                               "the handed-back selection opens that original's own Details")
            }
        }

        // Same title twice, distinct identities: each hands back its own identity, not a position.
        let twin = [original(t20[0], .pregame, identity: id("constructed-a")),
                    original(t20[0], .pregame, identity: id("constructed-b"))]
        XCTAssertEqual(choices(catalogue(twin)).map { tap($0)?.identity },
                       [id("constructed-a"), id("constructed-b")])
    }

    func testWithoutACallbackEveryChoiceIsStaticNeverAnInertButton() {
        let all = catalogue(threeWay.map { original($0, .pregame) })
        let shown = choices(all, held("test-australia"))
        for choice in shown {
            XCTAssertNil(C.action(choice, onSelect: nil))
            XCTAssertTrue(choice.isAvailable, "static is not unavailable")
            XCTAssertNil(choice.status)
        }
        XCTAssertEqual(shown.map(\.isSelected), [false, true, false], "the held mark survives without a callback")
    }

    func testMalformedOriginalsStayVisibleAndUnavailableWhileHealthyNeighboursAct() {
        let ind = t20[0], wi = t20[1]
        let originals = [
            original(ind, .pregame),
            original(ind, .pregame, identity: id("constructed-blank-title"), title: "  "),
            original(ind, .pregame, identity: id("constructed-blank-outcome"), outcome: ""),
            original(ind, .pregame, identity: M.Identity(source: " ", market: "constructed:original:x", side: "Yes")),
            original(ind, .pregame, identity: M.Identity(source: "kalshi", market: "", side: "Yes")),
            original(ind, .pregame, identity: id("constructed-blank-side", side: " ")),
            original(wi, .pregame, identity: id("constructed-duplicate")),
            original(ind, .pregame, identity: id("constructed-duplicate")),
            original(wi, .pregame),
        ]
        let labels = [id("constructed-blank-title"): "India (owner label)"]
        let all = catalogue(originals)
        let shown = choices(all, labels: labels)

        XCTAssertEqual(shown.count, originals.count, "nothing silently dropped")
        XCTAssertEqual(shown.map(\.isAvailable), [true, false, false, false, false, false, false, false, true])
        XCTAssertEqual(shown.map(\.label), ["India wins", "India (owner label)", "India wins", "India wins",
                                            "India wins", "India wins", "West Indies wins", "India wins",
                                            "West Indies wins"])
        let unavailable: [String?] = Array(repeating: C.unavailableStatus, count: 7)
        XCTAssertEqual(shown.map(\.status), [nil] + unavailable + [nil])
        XCTAssertEqual(shown.map { tap($0)?.identity }, [id("t20-india"), nil, nil, nil, nil, nil, nil, nil,
                                                         id("t20-west-indies")])

        // The gate is content(), not original(): identity alone resolves the blank-title row.
        let blankTitle = M.Selection(scope: scope, identity: id("constructed-blank-title"))
        XCTAssertNotNil(M.original(in: all, selection: blankTitle))
        XCTAssertNil(M.content(catalogue: all, selection: blankTitle))
        XCTAssertFalse(shown[1].isSelected || choices(all, blankTitle)[1].isSelected,
                       "a held malformed original is never marked")

        // A blank catalogue scope opens nothing, so nothing acts.
        let blankScope = choices(catalogue(t20.map { original($0, .pregame) }, scope: " "))
        XCTAssertTrue(blankScope.allSatisfy { !$0.isAvailable && tap($0) == nil })
        XCTAssertEqual(blankScope.map(\.label), ["India wins", "West Indies wins"])
    }

    // MARK: - Held selection never falls back

    func testANilWithdrawnMismatchedOrAmbiguousHeldSelectionMarksNoNeighbour() {
        let full = threeWay.map { original($0, .pregame) }
        let all = catalogue(full)

        XCTAssertFalse(choices(all, nil).contains(where: \.isSelected))
        XCTAssertNil(M.content(catalogue: all, selection: nil))

        let withdrawn = catalogue(full.filter { $0.identity != id("test-south-africa") })
        let afterWithdrawal = choices(withdrawn, held("test-south-africa"))
        XCTAssertEqual(afterWithdrawal.map(\.label), ["Australia wins", "Draw/Tie wins"])
        XCTAssertFalse(afterWithdrawal.contains(where: \.isSelected), "no replacement elected")
        XCTAssertTrue(afterWithdrawal.allSatisfy(\.isAvailable), "healthy neighbours stay choosable")
        XCTAssertNil(M.content(catalogue: withdrawn, selection: held("test-south-africa")))

        for wrong in [held("test-south-africa", scope: "constructed:cricket:other-scope"),
                      held("test-south-africa", side: "No"), held("constructed-missing")] {
            XCTAssertFalse(choices(all, wrong).contains(where: \.isSelected))
            XCTAssertNil(M.content(catalogue: all, selection: wrong))
        }

        let ambiguous = catalogue(full + [original(threeWay[1], .pregame, identity: id("test-south-africa"))])
        let shown = choices(ambiguous, held("test-south-africa"))
        XCTAssertFalse(shown.contains(where: \.isSelected))
        XCTAssertEqual(shown.map(\.isAvailable), [false, true, true, false])
        XCTAssertNil(M.content(catalogue: ambiguous, selection: held("test-south-africa")))
    }

    func testRenderingAndRefreshNeverProposeASelection() {
        let selection = held("t20-west-indies")
        let full = t20.map { original($0, .comparison(.recorded)) }
        let refreshed = t20.map { original($0, .result) }
        let sequence = [catalogue(full), catalogue(refreshed),
                        catalogue(refreshed.filter { $0.identity != id("t20-west-indies") }),
                        catalogue(refreshed)]
        var marks: [[Bool]] = []
        for update in sequence {
            let shown = choices(update, selection)
            // Building every button's action is what a render does; none may fire.
            _ = shown.map { C.action($0, onSelect: { _ in XCTFail("a passive update proposed a selection") }) }
            marks.append(shown.map(\.isSelected))
        }
        XCTAssertEqual(marks, [[false, true], [false, true], [false], [false, true]],
                       "the mark follows only the host's held selection")
        XCTAssertEqual(M.content(catalogue: sequence[3], selection: selection)?.result?.words, "Won")
    }

    // MARK: - Readings stay the Details'

    func testMissingAndZeroReadingsStayQualifiedAndNeverDisableAChoice() {
        let ind = original(t20[0], .pregame, pregame: .value("0%", placement: 0, provenance: Self.t20Pregame))
        let wi = original(t20[1], .pregame, pregame: .missing("Withheld: too few trades"))
        let all = catalogue([ind, wi])
        XCTAssertEqual(choices(all).map(\.isAvailable), [true, true])

        let zero = M.content(catalogue: all, selection: held("t20-india"))!
        XCTAssertTrue(zero.readings[0].isValue, "0% is a reading, not an absence")
        XCTAssertEqual(zero.marks.map(\.placement), [0])
        let withheld = M.content(catalogue: all, selection: held("t20-west-indies"))!
        XCTAssertEqual(withheld.readings.map(\.text), ["Withheld: too few trades"])
        XCTAssertTrue(withheld.marks.isEmpty)

        let noneReadable = catalogue(t20.map { original($0, .pregame, pregame: .missing("Unavailable")) })
        XCTAssertTrue(choices(noneReadable).allSatisfy(\.isAvailable), "a missing reading is not a missing original")
    }

    // MARK: - Arrangement

    func testEmptyAllUnavailableLongAndAccessibilityArrangements() {
        XCTAssertEqual(choices(nil), [])
        XCTAssertEqual(choices(catalogue([])), [])
        XCTAssertEqual(C.arrangement(choices: 0, accessibilitySize: false), .empty)
        XCTAssertEqual(C.arrangement(choices: 0, accessibilitySize: true), .empty)
        // Phone and wide alike: the decision is width-free; FlowLayout wraps at the actual width.
        for count in [1, 2, 3, 9] {
            XCTAssertEqual(C.arrangement(choices: count, accessibilitySize: false), .wrapping)
            XCTAssertEqual(C.arrangement(choices: count, accessibilitySize: true), .stacked)
        }

        let long = "Draw/Tie wins — South Africa vs Australia men's professional Test series, Oct 9, 2026 (CONSTRUCTED long title)"
        let longChoice = choices(catalogue([original(threeWay[2], .pregame, title: long)]))
        XCTAssertEqual(longChoice.map(\.label), [long], "kept whole, never shortened")

        let allUnavailable = choices(catalogue(t20.map { original($0, .pregame) }, scope: ""))
        XCTAssertEqual(allUnavailable.count, 2)
        XCTAssertEqual(C.arrangement(choices: allUnavailable.count, accessibilitySize: false), .wrapping,
                       "unavailable originals stay drawn")
    }

    // MARK: - Spoken

    func testEachChoiceSpeaksItsLabelAndWhyItCannotOpen() {
        let originals = [original(t20[0], .pregame),
                         original(t20[1], .pregame, outcome: " "),
                         original(t20[1], .pregame, identity: id("constructed-untitled"), title: "")]
        let shown = choices(catalogue(originals))
        XCTAssertEqual(shown.map(C.spoken), ["India wins", "West Indies wins, \(C.unavailableStatus)", unavailableChoice])
        for words in shown.map(C.spoken) {
            for banned in ["%", "price", "odds", "quote", "Selected"] {
                XCTAssertFalse(words.contains(banned))
            }
        }
    }
}

/// Prepared, not executed. The handicap card shows, per panel, exactly what the
/// existing Details resolve for that panel's original in `.result` mode, the
/// owner's separately admitted actual and the owner's words, and acts only
/// through `OriginalMarketChooser9483.action`.
///
/// RETAINED (TENNIS-HANDICAP-RETAINED-CASES.json, event 15327291, Fokina–Tiafoe):
/// the three Polymarket originals' market/outcome ids, market names, outcomes,
/// units, pregame consensus 0.67/0.71/0.47 recorded 2026-10-11T12:45:25.328389Z
/// (before the verified 12:50Z start), raw final quotes 0.9995 with their quote
/// clocks, raw original results (true), reported sets 2–1 and games 18–18
/// captured 17:06:47.950466Z. Those raw values live only in `Retained`.
/// CONSTRUCTED owner input: the scope, every identity (built from the packet's
/// `constructed_owner_action_id`, never looked up by title), every display
/// word, figure text, calendar line (PDT is UTC−7 in October), grade word,
/// rules-unavailable words, block states, explanation and every
/// malformed/withdrawn/NaN/contradictory/width case. No rule text is supplied
/// by the retained rows, so none is invented. Taps go through
/// `OriginalHandicapCard9483.action`, the closure the view's buttons run.
/// Geometry, fit at 320/375/393/wide/AX, hosting and VoiceOver focus are NOT
/// asserted here.
@MainActor
final class OriginalHandicapCard9483Tests: XCTestCase {
    private typealias H = OriginalHandicapCard9483
    private typealias M = OriginalMarketDetails9483

    /// The retained row facts for one original — raw values and clocks only.
    private struct Retained {
        let market: Int
        let outcome: Int
        let marketName: String
        let outcomeName: String
        let unit: String
        let pregame: Double
        let pregameAt: String
        let rawFinalQuote: Double
        let quoteObservedAt: String
        let rawResult: Bool
        let constructedActionID: String
    }

    private static let fokinaSets = Retained(
        market: 65123150, outcome: 244876662,
        marketName: "Set Handicap: Frances Tiafoe (-1.5) vs Alejandro Davidovich Fokina (+1.5)",
        outcomeName: "Alejandro Davidovich Fokina", unit: "sets",
        pregame: 0.67, pregameAt: "2026-10-11T12:45:25.328389+00:00",
        rawFinalQuote: 0.9995, quoteObservedAt: "2026-10-11T14:06:15.499070+00:00", rawResult: true,
        constructedActionID: "constructed:15327291:polymarket:65123150:244876662")
    private static let tiafoeSets = Retained(
        market: 65123149, outcome: 244876660,
        marketName: "Set Handicap: Alejandro Davidovich Fokina (-1.5) vs Frances Tiafoe (+1.5)",
        outcomeName: "Frances Tiafoe", unit: "sets",
        pregame: 0.71, pregameAt: "2026-10-11T12:45:25.328389+00:00",
        rawFinalQuote: 0.9995, quoteObservedAt: "2026-10-11T14:54:06.778032+00:00", rawResult: true,
        constructedActionID: "constructed:15327291:polymarket:65123149:244876660")
    private static let fokinaGames = Retained(
        market: 65149801, outcome: 244973047,
        marketName: "Game Spread: Frances Tiafoe (-0.5) vs Alejandro Davidovich Fokina (+0.5)",
        outcomeName: "Alejandro Davidovich Fokina", unit: "games",
        pregame: 0.47, pregameAt: "2026-10-11T12:45:25.328389+00:00",
        rawFinalQuote: 0.9995, quoteObservedAt: "2026-10-11T16:20:15.999040+00:00", rawResult: true,
        constructedActionID: "constructed:15327291:polymarket:65149801:244973047")
    private static let retainedSets = (fokina: 2, tiafoe: 1)
    private static let retainedGames = (fokina: 18, tiafoe: 18)
    private static let scoreCaptureAt = "2026-10-11T17:06:47.950466+00:00"
    private static let verifiedStart = "2026-10-11T12:50:00+00:00"

    // CONSTRUCTED owner words. Readable calendar lines are fixture text, not a
    // production formatter; the raw clocks above stay separate.
    private let scope = "constructed:tennis-final:15327291:handicaps"
    private static let pregameWords = "Polymarket · recorded Sun, Oct 11, 2026, 5:45 AM PDT, before the match"
    private static let actualWords = "ESPN · captured Sun, Oct 11, 2026, 10:06 AM PDT"
    private static let rulesUnavailable = "Rules aren't available for this prop yet."
    private static let laterWords = "Polymarket · recorded Sun, Oct 11, 2026, 7:06 AM PDT"

    private static let words = H.Words(
        eyebrow: "HANDICAPS · EXPECTATIONS, GRADED", title: "Both players took a set",
        explanationTitle: "How these props work",
        explanation: ["For this completed best-of-three match, +1.5 sets means winning at least one set. +0.5 games means finishing level or ahead in total games.",
                      "These are separate outcomes, not a combined prediction."],
        tapInvitation: "Tap a panel to open its original prop.",
        scopeUnavailable: "Handicap props unavailable in this update",
        panelUnavailable: "Prop unavailable in this update",
        comparisonUnavailable: "Pre-match comparison unavailable for this prop")

    /// CONSTRUCTED identity from the packet's constructed action id.
    private func identity(_ r: Retained) -> M.Identity {
        M.Identity(source: "polymarket", market: r.constructedActionID, side: "outcome:\(r.outcome)")
    }

    private func figure(_ r: Retained) -> String { "\(Int((r.pregame * 100).rounded()))%" }

    private func original(_ r: Retained, mode: M.Mode = .result, identity: M.Identity? = nil,
                          pregame: M.Reading? = nil, later: M.Reading? = nil,
                          grade: M.Grade? = M.Grade(words: "Won", provenance: nil),
                          quote: M.HistoricalQuote? = nil) -> M.Original {
        M.Original(identity: identity ?? self.identity(r), title: r.marketName, outcome: r.outcomeName, mode: mode,
                   pregame: pregame ?? .value(figure(r), placement: r.pregame, provenance: Self.pregameWords),
                   later: later, grade: grade,
                   about: M.About(source: "Polymarket", rules: .unavailable(Self.rulesUnavailable),
                                  provenance: [], historicalQuote: quote))
    }

    private var retainedOriginals: [M.Original] {
        [original(Self.fokinaSets), original(Self.tiafoeSets), original(Self.fokinaGames)]
    }

    private func count(figure: String, unit: String, blocks: [Bool], spoken: String,
                       provenance: String? = OriginalHandicapCard9483Tests.actualWords) -> H.Actual {
        .count(H.Count(figure: figure, unit: unit, blocks: blocks, provenance: provenance, spoken: spoken))
    }

    private var gamePair: H.Actual {
        .pair(H.Pair(caption: "Final games",
                     first: H.PairSide(figure: "\(Self.retainedGames.fokina)", name: "Fokina"), relation: "level",
                     second: H.PairSide(figure: "\(Self.retainedGames.tiafoe)", name: "Tiafoe"),
                     provenance: Self.actualWords, spoken: "Final games: Fokina 18, Tiafoe 18, level"))
    }

    private func panel(original: M.Identity?, subject: String, predicate: String, condition: String,
                       actual: H.Actual, mark: H.ResultMark? = .positive) -> H.Panel {
        H.Panel(original: original, subject: subject, predicate: predicate, condition: condition, actual: actual,
                resultMark: mark, openHint: "Opens the original \(condition) prop.")
    }

    private var fokinaSetPanel: H.Panel {
        panel(original: identity(Self.fokinaSets), subject: "Fokina", predicate: "Fokina to win at least one set",
              condition: "+1.5 sets",
              actual: count(figure: "\(Self.retainedSets.fokina)", unit: "sets won · final", blocks: [true, true],
                            spoken: "Fokina won 2 sets, final"))
    }

    private var tiafoeSetPanel: H.Panel {
        panel(original: identity(Self.tiafoeSets), subject: "Tiafoe", predicate: "Tiafoe to win at least one set",
              condition: "+1.5 sets",
              actual: count(figure: "\(Self.retainedSets.tiafoe)", unit: "set won · final", blocks: [true, false],
                            spoken: "Tiafoe won 1 set, final"))
    }

    private var gamePanel: H.Panel {
        panel(original: identity(Self.fokinaGames), subject: "Fokina",
              predicate: "Fokina to finish level or ahead on games", condition: "+0.5 games", actual: gamePair)
    }

    private func groups(sets: [H.Panel], games: [H.Panel]) -> [H.Group] {
        [H.Group(heading: "Win at least one set", panels: sets),
         H.Group(heading: "Finish level or ahead on games", panels: games)]
    }

    private func card(phase: H.Phase = .final, originals: [M.Original]? = nil, scope: String? = nil,
                      held: M.Selection? = nil, groups: [H.Group]? = nil, words: H.Words? = nil) -> H.Input {
        H.Input(phase: phase,
                catalogue: M.Catalogue(scope: scope ?? self.scope, originals: originals ?? retainedOriginals),
                held: held,
                groups: groups ?? self.groups(sets: [fokinaSetPanel, tiafoeSetPanel], games: [gamePanel]),
                words: words ?? Self.words)
    }

    private func shown(_ panel: H.Panel, in input: H.Input, file: StaticString = #filePath,
                       line: UInt = #line) -> H.Shown? {
        guard case .shown(let shown)? = H.state(panel, in: input) else {
            XCTFail("expected a shown panel", file: file, line: line)
            return nil
        }
        return shown
    }

    /// Taps a panel exactly as its button does; nil when it has no button.
    private func tap(_ panel: H.Panel, in input: H.Input) -> M.Selection? {
        var handed: [M.Selection] = []
        guard let action = H.action(panel, in: input, onSelect: { handed.append($0) }) else { return nil }
        action()
        XCTAssertEqual(handed.count, 1, "one tap, one proposal")
        return handed.first
    }

    // MARK: - The three retained originals

    func testTheThreeRetainedOriginalsKeepTheirExactIdentitiesUnitsChancesAndOwnResults() {
        let input = card()
        let cases: [(H.Panel, Retained)] = [(fokinaSetPanel, Self.fokinaSets), (tiafoeSetPanel, Self.tiafoeSets),
                                            (gamePanel, Self.fokinaGames)]
        for (panel, r) in cases {
            // Same "+00:00" ISO form, so the strings order as the instants do.
            XCTAssertLessThan(r.pregameAt, Self.verifiedStart, "a before reading")
            guard let placed = shown(panel, in: input) else { continue }
            XCTAssertEqual(placed.chance.label, M.pregameLabel)
            XCTAssertEqual(placed.chance.text, figure(r), "the owner's figure, verbatim")
            XCTAssertTrue(placed.chance.isValue)
            XCTAssertEqual(placed.chance.marker, .hollow, "the historical reading beside a result")
            XCTAssertEqual(placed.chance.placement, r.pregame, "the raw admitted value on the rail")
            XCTAssertEqual(placed.chance.provenance, Self.pregameWords)
            XCTAssertTrue(r.rawResult)
            XCTAssertEqual(placed.result, M.ShownResult(words: "Won", provenance: M.resultTimeUnknown),
                           "no settlement clock is supplied, and no quote clock stands in for one")
            XCTAssertEqual(placed.mark, .positive)

            let selection = H.selection(panel, in: input)
            XCTAssertEqual(selection, M.Selection(scope: scope, identity: identity(r)))
            let details = M.content(catalogue: input.catalogue, selection: selection)
            XCTAssertEqual(details?.title, r.marketName, "the existing Details open that exact original")
            XCTAssertEqual(details?.outcome, r.outcomeName)
            XCTAssertEqual(details?.rules, .unavailable(Self.rulesUnavailable), "no rule text is invented")
        }
        XCTAssertEqual(cases.map { $0.1.unit }, ["sets", "sets", "games"])
        XCTAssertEqual(cases.map { item -> String in
            switch item.0.actual {
            case .count: return "count"
            case .pair: return "pair"
            case .missing: return "missing"
            }
        }, ["count", "count", "pair"], "set panels carry a count, the game panel a named pair")
        XCTAssertEqual(Set(cases.map { identity($0.1) }).count, 3, "three distinct originals")
    }

    func testOverlappingChancesAreNeverNormalizedComplementedOrMultiplied() {
        let input = card()
        let panels = [fokinaSetPanel, tiafoeSetPanel, gamePanel]
        XCTAssertEqual(panels.compactMap { shown($0, in: input)?.chance.text }, ["67%", "71%", "47%"])
        XCTAssertEqual(panels.compactMap { shown($0, in: input)?.chance.placement }, [0.67, 0.71, 0.47],
                       "three independent originals; their sum is not 100%")
        let spoken = panels.map { H.spoken($0, in: input) }
        XCTAssertTrue(spoken[0].contains("67%") && !spoken[0].contains("71%") && !spoken[0].contains("47%"))
        XCTAssertTrue(spoken[1].contains("71%") && !spoken[1].contains("67%") && !spoken[1].contains("29%"),
                      "never the complement of a neighbour")
        XCTAssertTrue(spoken[2].contains("47%") && !spoken[2].contains("53%"))
        for words in spoken {
            for banned in ["combined", "48%", "32%", "22%", "100%"] {
                XCTAssertFalse(words.contains(banned), "\(banned) is no reading of these originals")
            }
        }
    }

    // MARK: - Actual is context, never a grade

    func testActualCountsAndPairStayIndependentOfTheOriginalsGrade() {
        // CONSTRUCTED contradiction: the owner's actual says 0 sets while the
        // original's own grade says Won. Both show verbatim; nothing reconciles them.
        let contradictory = panel(original: identity(Self.fokinaSets), subject: "Fokina",
                                  predicate: "Fokina to win at least one set", condition: "+1.5 sets",
                                  actual: count(figure: "0", unit: "sets won · final", blocks: [false, false],
                                                spoken: "Fokina won 0 sets, final"))
        let won = card(groups: groups(sets: [contradictory], games: []))
        XCTAssertEqual(shown(contradictory, in: won)?.result.words, "Won")
        XCTAssertTrue(H.spoken(contradictory, in: won).contains("Actual: Fokina won 0 sets, final"))

        // The reverse: the actual says 2 sets, the owner's grade says Lost.
        let lostOriginals = [original(Self.fokinaSets, grade: M.Grade(words: "Lost", provenance: nil)),
                             original(Self.tiafoeSets), original(Self.fokinaGames)]
        let lost = card(originals: lostOriginals)
        XCTAssertEqual(shown(fokinaSetPanel, in: lost)?.result.words, "Lost")
        XCTAssertEqual(fokinaSetPanel.actual, count(figure: "2", unit: "sets won · final", blocks: [true, true],
                                                    spoken: "Fokina won 2 sets, final"))

        // A missing grade keeps the game pair whole and never becomes a loss.
        let ungraded = card(originals: [original(Self.fokinaSets), original(Self.tiafoeSets),
                                        original(Self.fokinaGames, grade: nil)])
        XCTAssertEqual(shown(gamePanel, in: ungraded)?.result, M.ShownResult(words: M.resultUnavailable, provenance: nil))
        XCTAssertTrue(H.spoken(gamePanel, in: ungraded).contains("Final games: Fokina 18, Tiafoe 18, level"))
        XCTAssertFalse(H.spoken(gamePanel, in: ungraded).contains("Lost"))
    }

    func testAResultMarkNeedsTheOriginalsOwnSuppliedGrade() {
        for grade in [nil, M.Grade(words: "", provenance: nil), M.Grade(words: " \n", provenance: "x")] {
            let input = card(originals: [original(Self.fokinaSets, grade: grade), original(Self.tiafoeSets),
                                         original(Self.fokinaGames)])
            XCTAssertNil(shown(fokinaSetPanel, in: input)?.mark,
                         "no glyph without the original's grade, whatever the actual or the owner's mark")
            XCTAssertEqual(shown(fokinaSetPanel, in: input)?.result.words, M.resultUnavailable)
        }
        // Graded, but the owner supplies no decoration: none is inferred from the words.
        let undecorated = panel(original: identity(Self.tiafoeSets), subject: "Tiafoe",
                                predicate: "Tiafoe to win at least one set", condition: "+1.5 sets",
                                actual: tiafoeSetPanel.actual, mark: nil)
        let input = card(groups: groups(sets: [fokinaSetPanel, undecorated], games: [gamePanel]))
        XCTAssertNil(shown(undecorated, in: input)?.mark)
        XCTAssertEqual(shown(undecorated, in: input)?.result.words, "Won")
        // The owner's decoration is shown as supplied beside its own grade.
        let negative = panel(original: identity(Self.fokinaGames), subject: "Fokina",
                             predicate: "Fokina to finish level or ahead on games", condition: "+0.5 games",
                             actual: gamePair, mark: .negative)
        let lost = card(originals: [original(Self.fokinaSets), original(Self.tiafoeSets),
                                    original(Self.fokinaGames, grade: M.Grade(words: "Lost", provenance: nil))],
                        groups: groups(sets: [fokinaSetPanel, tiafoeSetPanel], games: [negative]))
        XCTAssertEqual(shown(negative, in: lost)?.mark, .negative)
        XCTAssertEqual(H.ResultMark.positive.symbol, "checkmark.circle.fill")
        XCTAssertFalse(H.spoken(negative, in: lost).contains("checkmark"), "the glyph is decoration, not speech")
    }

    // MARK: - Missing inputs keep their own words

    func testMissingReadingsActualsGradesAndRulesKeepTheirOwnWords() {
        let withheld = original(Self.tiafoeSets, pregame: .missing("Withheld: too few trades"))
        let zero = original(Self.fokinaGames, pregame: .value("0%", placement: 0, provenance: Self.pregameWords))
        let noActual = panel(original: identity(Self.fokinaSets), subject: "Fokina",
                             predicate: "Fokina to win at least one set", condition: "+1.5 sets",
                             actual: .missing("Set count unavailable"))
        let undated = panel(original: identity(Self.tiafoeSets), subject: "Tiafoe",
                            predicate: "Tiafoe to win at least one set", condition: "+1.5 sets",
                            actual: count(figure: "1", unit: "set won · final", blocks: [true, false],
                                          spoken: "Tiafoe won 1 set, final", provenance: nil))
        let input = card(originals: [original(Self.fokinaSets), withheld, zero],
                         groups: groups(sets: [noActual, undated], games: [gamePanel]))

        let tiafoe = shown(undated, in: input)
        XCTAssertEqual(tiafoe?.chance.text, "Withheld: too few trades")
        XCTAssertEqual(tiafoe?.chance.isValue, false)
        XCTAssertNil(tiafoe?.chance.placement, "no reading, no mark — never zero")
        XCTAssertNotNil(H.selection(undated, in: input), "a missing chance does not close the original")
        XCTAssertTrue(H.spoken(undated, in: input).contains("Actual: Tiafoe won 1 set, final, \(M.timeUnknown)"),
                      "an undated actual stays unknown")

        XCTAssertEqual(shown(gamePanel, in: input)?.chance.placement, 0, "0% is a reading, not an absence")
        XCTAssertNotNil(H.selection(gamePanel, in: input))

        XCTAssertTrue(H.spoken(noActual, in: input).contains("Actual: Set count unavailable"))
        XCTAssertEqual(shown(noActual, in: input)?.chance.text, "67%", "the original stays useful")

        // Rules stay the Details': the owner's words, or no section — never invented text.
        let blankRules = M.Original(identity: identity(Self.fokinaSets), title: Self.fokinaSets.marketName,
                                    outcome: Self.fokinaSets.outcomeName, mode: .result,
                                    pregame: .value("67%", placement: 0.67, provenance: Self.pregameWords),
                                    later: nil, grade: M.Grade(words: "Won", provenance: nil),
                                    about: M.About(source: "Polymarket", rules: .unavailable(" "), provenance: [],
                                                   historicalQuote: nil))
        let rules = card(originals: [blankRules, original(Self.tiafoeSets), original(Self.fokinaGames)])
        XCTAssertEqual(M.content(catalogue: rules.catalogue, selection: H.selection(fokinaSetPanel, in: rules))?.rules,
                       .omitted)
        XCTAssertNotNil(shown(fokinaSetPanel, in: rules), "missing rules never hide the panel")
    }

    func testANonResultModeKeepsTheComparisonUnavailableAndHealthyPanelsUseful() {
        let later = M.Reading.value("99.95%", placement: Self.tiafoeSets.rawFinalQuote, provenance: Self.laterWords)
        for mode in [M.Mode.pregame, .comparison(.recorded), .comparison(.current)] {
            let input = card(originals: [original(Self.fokinaSets), original(Self.tiafoeSets, mode: mode, later: later),
                                         original(Self.fokinaGames)])
            XCTAssertEqual(H.state(tiafoeSetPanel, in: input), .comparisonUnavailable(Self.words.comparisonUnavailable),
                           "\(mode) is never forced into a final comparison")
            let spoken = H.spoken(tiafoeSetPanel, in: input)
            XCTAssertFalse(spoken.contains("99.95%"), "a later chance is never read as final")
            XCTAssertFalse(spoken.contains("71%"))
            XCTAssertTrue(spoken.contains("Actual: Tiafoe won 1 set, final"))
            XCTAssertEqual(tap(tiafoeSetPanel, in: input), M.Selection(scope: scope, identity: identity(Self.tiafoeSets)),
                           "the exact original still opens its own Details in its own mode")
            XCTAssertEqual(shown(fokinaSetPanel, in: input)?.chance.text, "67%", "neighbours stay useful")
            XCTAssertEqual(shown(gamePanel, in: input)?.chance.text, "47%")
        }
    }

    // MARK: - Final only

    func testBeforeAndDuringPlayTheCardShowsAndOffersNothing() {
        for phase in [H.Phase.before, .during] {
            let input = card(phase: phase, held: M.Selection(scope: scope, identity: identity(Self.fokinaSets)))
            XCTAssertFalse(H.isShown(input))
            XCTAssertNil(H.catalogue(input))
            for panel in H.panels(input) {
                XCTAssertNil(H.state(panel, in: input))
                XCTAssertNil(H.selection(panel, in: input))
                XCTAssertFalse(H.isSelected(panel, in: input))
                XCTAssertNil(H.action(panel, in: input, onSelect: { _ in XCTFail("no action before the final") }))
                XCTAssertEqual(H.spoken(panel, in: input), "")
            }
            XCTAssertFalse(H.showsTapInvitation(input, onSelect: { _ in }))
        }
        // The existing Details are untouched by the card's phase.
        let before = card(phase: .before)
        XCTAssertEqual(M.content(catalogue: before.catalogue,
                                 selection: M.Selection(scope: scope, identity: identity(Self.fokinaSets)))?.result?.words,
                       "Won")
        XCTAssertTrue(H.isShown(card()))
    }

    // MARK: - Actions

    func testEachPanelHandsBackItsExactSelectionThroughTheChoosersOwnAction() {
        // CONSTRUCTED: an odd but valid owner scope is copied, never rebuilt.
        let odd = "constructed:tennis-final:15327291 / handicaps (v2)"
        // A fourth original the card does not place stays in the full catalogue.
        let other = M.Identity(source: "polymarket", market: "constructed:15327291:polymarket:65123150:other", side: "outcome:other")
        let extra = M.Original(identity: other, title: Self.fokinaSets.marketName, outcome: "Frances Tiafoe",
                               mode: .result, pregame: .value("33%", placement: 0.33, provenance: Self.pregameWords),
                               later: nil, grade: M.Grade(words: "Lost", provenance: nil),
                               about: M.About(source: "Polymarket", rules: .unavailable(Self.rulesUnavailable),
                                              provenance: [], historicalQuote: nil))
        let input = card(originals: retainedOriginals + [extra], scope: odd)
        let cases: [(H.Panel, Retained)] = [(fokinaSetPanel, Self.fokinaSets), (tiafoeSetPanel, Self.tiafoeSets),
                                            (gamePanel, Self.fokinaGames)]
        for (panel, r) in cases {
            let handed = tap(panel, in: input)
            XCTAssertEqual(handed, M.Selection(scope: odd, identity: identity(r)))
            XCTAssertEqual(handed.flatMap { M.content(catalogue: input.catalogue, selection: $0) }?.title, r.marketName)
        }
        let chooser = OriginalMarketChooser9483.choices(catalogue: input.catalogue, selection: nil, labels: [:],
                                                        unavailableChoice: "Outcome unavailable")
        XCTAssertEqual(chooser.count, 4, "the grouped card never replaces the full catalogue")
        XCTAssertTrue(chooser.allSatisfy(\.isAvailable))

        let ids = [H.accessibilityID(fokinaSetPanel, group: 0, index: 0),
                   H.accessibilityID(tiafoeSetPanel, group: 0, index: 1),
                   H.accessibilityID(gamePanel, group: 1, index: 0)]
        XCTAssertEqual(Set(ids).count, 3, "each panel keeps its own focus id")
        XCTAssertTrue(ids[0].contains(Self.fokinaSets.constructedActionID))
    }

    func testInvalidDuplicateWithdrawnAndClaimedTwiceIdentitiesStayNamedAndOpenNothing() {
        let foreign = M.Identity(source: "polymarket", market: "constructed:15327291:polymarket:0:0", side: "outcome:0")
        let unavailable = H.State.unavailable(Self.words.panelUnavailable)
        func setPanel(_ id: M.Identity?, predicate: String = "Fokina to win at least one set") -> H.Panel {
            panel(original: id, subject: "Fokina", predicate: predicate, condition: "+1.5 sets",
                  actual: fokinaSetPanel.actual)
        }
        let blankIDs = [
            M.Identity(source: " ", market: Self.fokinaSets.constructedActionID, side: "outcome:244876662"),
            M.Identity(source: "polymarket", market: "", side: "outcome:244876662"),
            M.Identity(source: "polymarket", market: Self.fokinaSets.constructedActionID, side: " "),
        ]
        // A blank identity opens nothing even when an original carries the same blank identity.
        var cases: [(H.Panel, [M.Original])] = blankIDs.flatMap { id in
            [(setPanel(id), retainedOriginals), (setPanel(id), retainedOriginals + [original(Self.fokinaSets, identity: id)])]
        }
        cases += [(setPanel(nil), retainedOriginals), (setPanel(foreign), retainedOriginals),
                  (setPanel(identity(Self.fokinaSets), predicate: "  "), retainedOriginals)]
        for (bad, originals) in cases {
            let input = card(originals: originals, groups: groups(sets: [bad, tiafoeSetPanel], games: [gamePanel]))
            XCTAssertEqual(H.state(bad, in: input), unavailable)
            XCTAssertNil(tap(bad, in: input))
            XCTAssertTrue(H.spoken(bad, in: input).contains("Actual: Fokina won 2 sets, final"),
                          "the panel stays named with its own actual")
            XCTAssertEqual(tap(tiafoeSetPanel, in: input)?.identity, identity(Self.tiafoeSets),
                           "a healthy neighbour still acts")
        }

        // Withdrawn: the catalogue no longer holds Fokina's set original.
        let withdrawn = card(originals: [original(Self.tiafoeSets), original(Self.fokinaGames)])
        XCTAssertEqual(H.state(fokinaSetPanel, in: withdrawn), unavailable)
        XCTAssertNil(tap(fokinaSetPanel, in: withdrawn), "no neighbour elected")

        // Duplicated in the catalogue: an ambiguous identity is no original.
        let duplicated = card(originals: retainedOriginals + [original(Self.tiafoeSets, identity: identity(Self.fokinaSets))])
        XCTAssertEqual(H.state(fokinaSetPanel, in: duplicated), unavailable)
        XCTAssertNil(tap(fokinaSetPanel, in: duplicated))

        // Claimed twice on the card: neither panel attaches.
        let twice = setPanel(identity(Self.fokinaSets))
        let claimed = card(groups: groups(sets: [fokinaSetPanel, twice], games: [gamePanel]))
        XCTAssertEqual(H.state(fokinaSetPanel, in: claimed), unavailable)
        XCTAssertEqual(H.state(twice, in: claimed), unavailable)
        XCTAssertEqual(tap(gamePanel, in: claimed)?.identity, identity(Self.fokinaGames))
    }

    func testABlankOrMissingCatalogueScopeSuppressesEveryPanel() {
        for blank in ["", " ", "\n"] {
            let input = card(scope: blank, held: M.Selection(scope: blank, identity: identity(Self.fokinaSets)))
            XCTAssertTrue(H.isShown(input))
            XCTAssertNil(H.catalogue(input), "the scope-unavailable words replace the panels")
            for panel in H.panels(input) {
                XCTAssertNil(H.state(panel, in: input))
                XCTAssertNil(tap(panel, in: input))
                XCTAssertFalse(H.isSelected(panel, in: input))
            }
            XCTAssertFalse(H.showsTapInvitation(input, onSelect: { _ in }))
        }
        let none = H.Input(phase: .final, catalogue: nil, held: nil,
                           groups: groups(sets: [fokinaSetPanel], games: [gamePanel]), words: Self.words)
        XCTAssertNil(H.catalogue(none))
        XCTAssertNil(H.state(fokinaSetPanel, in: none))
        XCTAssertFalse(H.showsTapInvitation(none, onSelect: { _ in }))
    }

    func testANaNIgnoredValueNeverClosesAValidOriginal() {
        let nanLater = M.Reading.value("—", placement: .nan, provenance: Self.laterWords)
        let nan = original(Self.fokinaSets, later: nanLater, quote: M.HistoricalQuote(text: "99.95%", recorded: nil))
        XCTAssertNotEqual(nan, nan, "whole-payload equality fails on NaN — membership must not use it")
        let input = card(originals: [nan, original(Self.tiafoeSets), original(Self.fokinaGames)])
        XCTAssertEqual(tap(fokinaSetPanel, in: input), M.Selection(scope: scope, identity: identity(Self.fokinaSets)))
        XCTAssertEqual(shown(fokinaSetPanel, in: input)?.chance.text, "67%")

        let nanPregame = original(Self.tiafoeSets, pregame: .value("71%", placement: .nan, provenance: Self.pregameWords))
        let geometry = card(originals: [original(Self.fokinaSets), nanPregame, original(Self.fokinaGames)])
        XCTAssertEqual(shown(tiafoeSetPanel, in: geometry)?.chance.text, "71%", "the figure still shows")
        XCTAssertNil(shown(tiafoeSetPanel, in: geometry)?.chance.placement, "no clamped mark")
        XCTAssertNotNil(tap(tiafoeSetPanel, in: geometry), "invalid geometry never closes the original")
    }

    func testTheRawFinalQuoteNeverBecomesAChanceOrAResult() {
        let rows = [Self.fokinaSets, Self.tiafoeSets, Self.fokinaGames]
        let originals = rows.map { r in
            original(r, later: .value("99.95%", placement: r.rawFinalQuote, provenance: Self.laterWords),
                     quote: M.HistoricalQuote(text: "99.95%", recorded: "Sun, Oct 11, 2026, 7:06 AM PDT"))
        }
        let input = card(originals: originals)
        for (panel, r) in zip([fokinaSetPanel, tiafoeSetPanel, gamePanel], rows) {
            XCTAssertEqual(shown(panel, in: input)?.chance.placement, r.pregame, "the baseline, not \(r.rawFinalQuote)")
            XCTAssertEqual(shown(panel, in: input)?.result.provenance, M.resultTimeUnknown,
                           "a quote clock (\(r.quoteObservedAt)) is not a settlement time")
            let spoken = H.spoken(panel, in: input)
            XCTAssertFalse(spoken.contains("99.95"))
            XCTAssertFalse(spoken.contains("7:06"))
        }
    }

    // MARK: - Static content and the tap invitation

    func testWithoutACallbackThePanelsAreStaticAndNoTapIsInvited() {
        let input = card(held: M.Selection(scope: scope, identity: identity(Self.tiafoeSets)))
        for panel in H.panels(input) {
            XCTAssertNil(H.action(panel, in: input, onSelect: nil))
            XCTAssertNotNil(shown(panel, in: input), "static is not unavailable")
        }
        XCTAssertFalse(H.showsTapInvitation(input, onSelect: nil))
        XCTAssertEqual(H.panels(input).map { H.isSelected($0, in: input) }, [false, true, false],
                       "the held mark survives without a callback")
    }

    func testTheTapInvitationNeedsADisplayedPanelThatCanAct() {
        let some: (M.Selection) -> Void = { _ in }
        XCTAssertTrue(H.showsTapInvitation(card(), onSelect: some))

        let broken = [panel(original: nil, subject: "Fokina", predicate: "Fokina to win at least one set",
                            condition: "+1.5 sets", actual: fokinaSetPanel.actual)]
        XCTAssertFalse(H.showsTapInvitation(card(groups: groups(sets: broken, games: [])), onSelect: some),
                       "no displayed original can open")
        XCTAssertFalse(H.showsTapInvitation(card(groups: []), onSelect: some), "no panels, no invitation")

        let missing = card(originals: [original(Self.fokinaSets, pregame: .missing("Unavailable")),
                                       original(Self.tiafoeSets, pregame: .value("0%", placement: 0, provenance: Self.pregameWords)),
                                       original(Self.fokinaGames)],
                           groups: groups(sets: broken + [fokinaSetPanel, tiafoeSetPanel], games: []))
        XCTAssertTrue(H.showsTapInvitation(missing, onSelect: some), "missing and 0% chances still act")

        let w = Self.words
        let blankWords = H.Words(eyebrow: w.eyebrow, title: w.title, explanationTitle: w.explanationTitle,
                                 explanation: w.explanation, tapInvitation: " ", scopeUnavailable: w.scopeUnavailable,
                                 panelUnavailable: w.panelUnavailable, comparisonUnavailable: w.comparisonUnavailable)
        XCTAssertFalse(H.showsTapInvitation(card(words: blankWords), onSelect: some))
        XCTAssertFalse(Self.words.explanation.joined().lowercased().contains("tap"),
                       "the explanation itself invites no tap")
    }

    // MARK: - Held selection

    func testTheHeldSelectionMarksOnlyItsExactPanelAndRefreshProposesNothing() {
        let held = M.Selection(scope: scope, identity: identity(Self.fokinaGames))
        XCTAssertEqual(H.panels(card(held: held)).map { H.isSelected($0, in: card(held: held)) }, [false, false, true])
        for wrong in [M.Selection(scope: "constructed:other", identity: identity(Self.fokinaGames)),
                      M.Selection(scope: scope, identity: M.Identity(source: "polymarket", market: "x", side: "y"))] {
            let input = card(held: wrong)
            XCTAssertFalse(H.panels(input).contains { H.isSelected($0, in: input) })
        }
        let sequence = [card(held: held), card(originals: [original(Self.fokinaSets), original(Self.tiafoeSets)], held: held),
                        card(held: held)]
        var marks: [[Bool]] = []
        for update in sequence {
            // Building every button's action is what a render does; none may fire.
            _ = H.panels(update).map { H.action($0, in: update, onSelect: { _ in XCTFail("a passive update proposed a selection") }) }
            marks.append(H.panels(update).map { H.isSelected($0, in: update) })
        }
        XCTAssertEqual(marks, [[false, false, true], [false, false, false], [false, false, true]],
                       "a withdrawn held original marks no neighbour")
    }

    // MARK: - Layout and explanation decisions

    func testPanelsShareARowOnlyWhenEveryWholePanelFits() {
        typealias L = OriginalHandicapLayout9483
        XCTAssertEqual(L.sharedWidth(available: 400, ideals: [150, 170], spacing: 10, accessibilitySize: false), 195)
        XCTAssertNil(L.sharedWidth(available: 340, ideals: [150, 170], spacing: 10, accessibilitySize: false),
                     "a share below the wider panel's whole width stacks")
        XCTAssertNil(L.sharedWidth(available: 1000, ideals: [150, 170], spacing: 10, accessibilitySize: true),
                     "accessibility sizes always stack")
        XCTAssertNil(L.sharedWidth(available: 1000, ideals: [150], spacing: 10, accessibilitySize: false),
                     "a lone panel takes the full width")
        XCTAssertEqual(L.sharedWidth(available: .infinity, ideals: [20, 30], spacing: 10, accessibilitySize: false),
                       L.minimumTarget, "never narrower than a 44 pt target")
        let invalid: [[CGFloat]] = [[.nan, 10], [-1, 10], [.infinity, 10]]
        for bad in invalid {
            XCTAssertNil(L.sharedWidth(available: 400, ideals: bad, spacing: 10, accessibilitySize: false))
        }
        XCTAssertNil(L.sharedWidth(available: .nan, ideals: [10, 10], spacing: 10, accessibilitySize: false))
    }

    func testTheExplanationShowsExpandedWithoutAHostBinding() {
        XCTAssertEqual(H.explanationStyle(card(), hasBinding: true), .disclosure)
        XCTAssertEqual(H.explanationStyle(card(), hasBinding: false), .expanded, "never an inert disclosure")
        func words(title: String, paragraphs: [String]) -> H.Words {
            H.Words(eyebrow: Self.words.eyebrow, title: Self.words.title, explanationTitle: title,
                    explanation: paragraphs, tapInvitation: Self.words.tapInvitation,
                    scopeUnavailable: Self.words.scopeUnavailable, panelUnavailable: Self.words.panelUnavailable,
                    comparisonUnavailable: Self.words.comparisonUnavailable)
        }
        XCTAssertEqual(H.explanationStyle(card(words: words(title: " ", paragraphs: Self.words.explanation)), hasBinding: true),
                       .expanded, "a disclosure needs a title")
        XCTAssertEqual(H.explanationStyle(card(words: words(title: "How these props work", paragraphs: ["", " "])),
                                          hasBinding: true), .none)
        XCTAssertEqual(H.explanation(card(words: words(title: "t", paragraphs: ["", "Kept whole."]))), ["Kept whole."])
    }

    // MARK: - Spoken and words

    func testSpokenChanceCountScoreResultAndProvenanceStayDistinct() {
        let input = card()
        XCTAssertEqual(H.spoken(fokinaSetPanel, in: input),
                       "Fokina to win at least one set. Pregame chance 67%, \(Self.pregameWords). "
                       + "Actual: Fokina won 2 sets, final, \(Self.actualWords). "
                       + "\(M.resultLabel): Won, \(M.resultTimeUnknown).")
        XCTAssertEqual(H.spoken(gamePanel, in: input),
                       "Fokina to finish level or ahead on games. Pregame chance 47%, \(Self.pregameWords). "
                       + "Actual: Final games: Fokina 18, Tiafoe 18, level, \(Self.actualWords). "
                       + "\(M.resultLabel): Won, \(M.resultTimeUnknown).")
        XCTAssertEqual(H.resultLine(M.ShownResult(words: "Won", provenance: nil), condition: "+1.5 sets"), "Won · +1.5 sets")
        XCTAssertEqual(H.resultLine(M.ShownResult(words: "Won", provenance: nil), condition: " "), "Won")
        for words in H.panels(input).map({ H.spoken($0, in: input) }) {
            for banned in ["price", "odds", "quote", "bookmaker", "Selected"] {
                XCTAssertFalse(words.lowercased().contains(banned.lowercased()))
            }
        }
    }

    func testLongOwnerWordsAreKeptWhole() {
        let long = "Alejandro Davidovich Fokina to win at least one set in this completed best-of-three match (CONSTRUCTED long predicate)"
        let condition = "+1.5 sets (Set Handicap: Frances Tiafoe -1.5 vs Alejandro Davidovich Fokina +1.5)"
        let wordy = panel(original: identity(Self.fokinaSets), subject: "Alejandro Davidovich Fokina", predicate: long,
                          condition: condition, actual: fokinaSetPanel.actual)
        let input = card(groups: groups(sets: [wordy, tiafoeSetPanel], games: [gamePanel]))
        XCTAssertTrue(H.spoken(wordy, in: input).hasPrefix(long + "."), "never shortened")
        guard let result = shown(wordy, in: input)?.result else { return }
        XCTAssertEqual(H.resultLine(result, condition: condition), "Won · \(condition)")
        XCTAssertEqual(wordy.openHint, "Opens the original \(condition) prop.")
    }
}

// MARK: - Live handicap source preparation (NOT_RUN)

/// RETAINED: event 15327807, exact original IDs, 43.5/54.5% observations at
/// 2026-10-12T06:58:25.957874Z before the verified 10:55Z start; score captured
/// 12:20:44.471140Z, sets 0–1, games 8–10. Raw histories and prototype are
/// pinned in TENNIS-LIVE-HANDICAP-RETAINED-CASES.json. Later 99.95/87% quotes
/// and the set market's 47% opening are NOT current/baseline replacements.
/// CONSTRUCTED: scope/identity association, predicate/display copy, formatted
/// provenance, progress statistic and all contradictory/pathology controls.
/// These tests prepare source contracts, not real bindings or native fidelity.
@MainActor
final class OriginalLiveHandicapCard9483Tests: XCTestCase {
    private typealias H = OriginalHandicapCard9483
    private typealias M = OriginalMarketDetails9483
    private let scope = "constructed:tennis-live:15327807:handicaps"
    private let beforeAt = "2026-10-12T06:58:25.957874+00:00"
    private let startAt = "2026-10-12T10:55:00+00:00"
    private let scoreAt = "2026-10-12T12:20:44.471140+00:00"
    private let beforeWords = "Polymarket · recorded Sun, Oct 11, 2026, 11:58 PM PDT, before the match"
    private let actualWords = "ESPN · captured Mon, Oct 12, 2026, 5:20 AM PDT"
    private let setID = M.Identity(source: "polymarket", market: "65197801", side: "245152788")
    private let gameID = M.Identity(source: "polymarket", market: "65212323", side: "245201950")

    private var words: H.Words {
        H.Words(eyebrow: "HANDICAPS · DIFFERENT UNITS", title: "A set secured. Games still unfolding.",
                explanationTitle: "How these props work", explanation: ["These original conditions remain separate."],
                tapInvitation: "Open an original prop.", scopeUnavailable: "Handicap props unavailable in this update",
                panelUnavailable: "Prop unavailable in this update", comparisonUnavailable: "Comparison unavailable")
    }

    private func original(_ game: Bool = false, mode: M.Mode = .comparison(.current),
                          id: M.Identity? = nil, before: M.Reading? = nil,
                          later: M.Reading? = .missing("Unavailable"),
                          grade: M.Grade? = nil) -> M.Original {
        M.Original(identity: id ?? (game ? gameID : setID),
                   title: game ? "Game Spread: Arthur Fils (-4.5) vs Botic van de Zandschulp (+4.5)"
                               : "Set Handicap: Arthur Fils (-1.5) vs Botic van de Zandschulp (+1.5)",
                   outcome: "Botic van de Zandschulp", mode: mode,
                   pregame: before ?? .value(game ? "54.5%" : "43.5%", placement: game ? 0.545 : 0.435,
                                             provenance: beforeWords),
                   later: later, grade: grade,
                   about: M.About(source: "Polymarket", rules: .unavailable("Rules unavailable"), provenance: [],
                                  historicalQuote: M.HistoricalQuote(text: game ? "87%" : "99.95%",
                                                                     recorded: "Historical quote, not current")))
    }

    private func panel(_ game: Bool = false, id: M.Identity? = nil, actual: H.Actual? = nil,
                       pending: String? = "Result pending") -> H.Panel {
        var result = H.Panel(original: id ?? (game ? gameID : setID), subject: "Zandschulp",
                             predicate: game ? "Zandschulp +4.5 games" : "Zandschulp +1.5 sets",
                             condition: game ? "+4.5 games" : "+1.5 sets",
                             actual: actual ?? (game
                                ? .pair(H.Pair(caption: "Games so far", first: H.PairSide(figure: "8", name: "Fils"),
                                               relation: "behind", second: H.PairSide(figure: "10", name: "Zandschulp"),
                                               provenance: actualWords, spoken: "Games so far: Fils 8, Zandschulp 10"))
                                : .count(H.Count(figure: "1", unit: "set won", blocks: [true, false],
                                                 provenance: actualWords, spoken: "Zandschulp 1 set won"))),
                             resultMark: .positive, openHint: "Open the original prop.")
        result.pendingMarketContext = pending
        if game, actual == nil {
            result.liveProgress = H.DisplayStat(figure: "+2", unit: "games ahead", provenance: actualWords,
                                                spoken: "Zandschulp +2 games ahead")
        }
        return result
    }

    private func input(phase: H.Phase = .during, enabled: Bool = true, originals: [M.Original]? = nil,
                       panels: [H.Panel]? = nil, held: M.Selection? = nil, scope: String? = nil) -> H.Input {
        H.Input(phase: phase, catalogue: M.Catalogue(scope: scope ?? self.scope,
                                                    originals: originals ?? [original(), original(true)]),
                held: held, groups: [H.Group(heading: "", panels: panels ?? [panel(), panel(true)])],
                words: words, showsDuringPlay: enabled)
    }

    private func shown(_ panel: H.Panel, _ input: H.Input, file: StaticString = #filePath,
                       line: UInt = #line) throws -> H.LiveShown {
        guard case .live(let value)? = H.state(panel, in: input) else {
            XCTFail("Expected live presentation", file: file, line: line)
            throw NSError(domain: "LiveHandicapPreparation", code: 1)
        }
        return value
    }

    func testExplicitTrueDuringGateAndUnchangedBeforeFinal() throws {
        XCTAssertEqual(input().phase, .during)
        XCTAssertTrue(H.isShown(input()))
        XCTAssertFalse(H.isShown(input(enabled: false)))
        for enabled in [false, true] {
            let before = input(phase: .before, enabled: enabled)
            XCTAssertFalse(H.isShown(before))
            XCTAssertNil(H.state(panel(), in: before))
            XCTAssertNil(H.action(panel(), in: before, onSelect: { _ in XCTFail("passive callback") }))
        }
        let originals = [original(mode: .result, grade: M.Grade(words: "Owner result", provenance: nil))]
        let defaultFinal = input(phase: .final, enabled: false, originals: originals, panels: [panel()])
        let optedFinal = input(phase: .final, originals: originals, panels: [panel()])
        XCTAssertEqual(H.state(panel(), in: defaultFinal), H.state(panel(), in: optedFinal))
        XCTAssertEqual(H.spoken(panel(), in: defaultFinal), H.spoken(panel(), in: optedFinal))
        XCTAssertFalse(H.spoken(panel(), in: optedFinal).contains("Market context"))
    }

    func testRetainedIndependentBaselinesAndClocksDoNotBorrowHistoricalQuotes() throws {
        XCTAssertLessThan(beforeAt, startAt)
        XCTAssertLessThan(startAt, scoreAt)
        let values = try [shown(panel(), input()), shown(panel(true), input())]
        XCTAssertEqual(values.map { $0.readings[0].text }, ["43.5%", "54.5%"])
        XCTAssertEqual(try XCTUnwrap(values[0].readings[0].placement), 0.435, accuracy: 0.000001)
        XCTAssertEqual(try XCTUnwrap(values[1].readings[0].placement), 0.545, accuracy: 0.000001)
        for value in values {
            XCTAssertEqual(value.readings[0].provenance, beforeWords)
            XCTAssertEqual(value.readings[1].label, "Current chance")
            XCTAssertEqual(value.readings[1].text, "Unavailable")
            XCTAssertNil(value.readings[1].placement)
            XCTAssertNil(value.result)
            XCTAssertNil(value.mark)
            XCTAssertEqual(value.pendingMarketContext, "Result pending")
        }
        let spoken = H.spoken(panel(), in: input())
        XCTAssertFalse(spoken.contains("99.95%"))
        XCTAssertFalse(spoken.contains("47%"))
        XCTAssertTrue(spoken.contains(beforeWords))
        XCTAssertTrue(spoken.contains(actualWords))
    }

    func testAllOwnerModesUseTheirExactContentWithoutCoercion() throws {
        let modes: [M.Mode] = [.pregame, .comparison(.current), .comparison(.recorded), .result]
        for mode in modes {
            let supplied = original(mode: mode, later: .value("62%", placement: 0.62, provenance: "Later clock"),
                                    grade: M.Grade(words: "Resolved No", provenance: "Settlement clock"))
            let card = input(originals: [supplied], panels: [panel()])
            let live = try shown(panel(), card)
            let content = try XCTUnwrap(M.content(catalogue: card.catalogue, selection: H.selection(panel(), in: card)))
            XCTAssertEqual(card.catalogue?.originals.first?.mode, mode)
            XCTAssertEqual(live.readings, content.readings)
            XCTAssertEqual(live.result, content.result)
            switch mode {
            case .comparison:
                XCTAssertEqual(live.pendingMarketContext, "Result pending")
                XCTAssertNil(live.result)
                XCTAssertNil(live.mark)
            case .pregame:
                XCTAssertEqual(live.readings.count, 1)
                XCTAssertNil(live.pendingMarketContext)
                XCTAssertNil(live.mark)
            case .result:
                XCTAssertEqual(live.readings.count, 1)
                XCTAssertNil(live.pendingMarketContext)
                XCTAssertEqual(live.result?.words, "Resolved No")
                XCTAssertEqual(live.mark, .positive, "decoration remains owner supplied, never inferred")
            }
        }
    }

    func testPhysicalUnitsAndPendingMarketRemainSeparateInSpeech() {
        let setWords = H.spoken(panel(), in: input())
        let gameWords = H.spoken(panel(true), in: input())
        XCTAssertTrue(setWords.contains("+1.5 sets"))
        XCTAssertTrue(setWords.contains("Actual: Zandschulp 1 set won"))
        XCTAssertTrue(gameWords.contains("+4.5 games"))
        XCTAssertTrue(gameWords.contains("Actual: Zandschulp +2 games ahead"))
        for value in [setWords, gameWords] {
            XCTAssertTrue(value.contains("Current chance: Unavailable"))
            XCTAssertTrue(value.contains("Market context: Result pending"))
            XCTAssertFalse(value.contains("Original market result:"))
            XCTAssertFalse(value.contains("100%"))
        }
    }

    func testMissingOriginalAndMissingScopeKeepConditionAndActualWithoutMarketAction() {
        let missing = input(originals: [])
        let noScope = input(scope: " \n")
        let noCatalogue = H.Input(phase: .during, catalogue: nil, held: nil,
                                  groups: input().groups, words: words, showsDuringPlay: true)
        for card in [missing, noScope, noCatalogue] {
            XCTAssertNil(H.selection(panel(), in: card))
            XCTAssertNotNil(H.state(panel(), in: card))
            let value = H.spoken(panel(), in: card)
            XCTAssertTrue(value.contains("+1.5 sets"))
            XCTAssertTrue(value.contains("1 set won"))
            XCTAssertFalse(value.contains("43.5%"))
            XCTAssertFalse(value.contains("Result pending"))
            XCTAssertNil(H.action(panel(), in: card, onSelect: { _ in XCTFail("unavailable action") }))
        }
    }

    func testMissingActualKeepsOriginalChanceAndMissingBeforeKeepsProgress() throws {
        let missingActual = panel(actual: .missing("Score unavailable"))
        let card = input(panels: [missingActual])
        XCTAssertEqual(try shown(missingActual, card).readings[0].text, "43.5%")
        XCTAssertTrue(H.spoken(missingActual, in: card).contains("Actual: Score unavailable"))
        let missingBefore = input(originals: [original(before: .missing("Before unavailable"))], panels: [panel()])
        XCTAssertEqual(try shown(panel(), missingBefore).readings[0].text, "Before unavailable")
        XCTAssertTrue(H.spoken(panel(), in: missingBefore).contains("1 set won"))
        XCTAssertNotNil(H.selection(panel(), in: missingBefore))
    }

    func testZeroAndInvalidGeometryRetainOwnTextAndAction() throws {
        let positions: [Double?] = [0, nil, .nan, .infinity, -0.1, 1.1]
        for position in positions {
            let card = input(originals: [original(before: .value("0%", placement: position, provenance: nil))],
                             panels: [panel()])
            let reading = try shown(panel(), card).readings[0]
            XCTAssertEqual(reading.text, "0%")
            XCTAssertTrue(reading.isValue)
            if position == 0 { XCTAssertEqual(reading.placement, 0) } else { XCTAssertNil(reading.placement) }
            XCTAssertNotNil(H.action(panel(), in: card, onSelect: { _ in }))
        }
    }

    func testExactIdentityUniqueAssociationAndWithdrawalFailClosed() {
        let foreign = M.Identity(source: "polymarket", market: "foreign", side: "245152788")
        let blank = M.Identity(source: " ", market: "65197801", side: "245152788")
        let cases: [(H.Panel, H.Input)] = [
            (panel(), input(originals: [original(), original()], panels: [panel()])),
            (panel(), input(panels: [panel(), panel()])),
            (panel(), input(originals: [original(true)], panels: [panel()])),
            (panel(id: foreign), input(panels: [panel(id: foreign)])),
            (panel(id: blank), input(originals: [original(id: blank)], panels: [panel(id: blank)]))
        ]
        for (item, card) in cases {
            XCTAssertNil(H.selection(item, in: card))
            XCTAssertNil(H.action(item, in: card, onSelect: { _ in XCTFail("borrowed action") }))
            XCTAssertFalse(H.spoken(item, in: card).contains("43.5%"))
            XCTAssertTrue(H.spoken(item, in: card).contains("1 set won"))
        }
    }

    func testIgnoredNaNLaterDoesNotClosePregameOrResultOriginal() throws {
        let modes: [M.Mode] = [.pregame, .result]
        for mode in modes {
            let card = input(originals: [original(mode: mode,
                                                 later: .value("Ignored", placement: .nan, provenance: nil))],
                             panels: [panel()])
            XCTAssertNotNil(H.selection(panel(), in: card))
            XCTAssertEqual(try shown(panel(), card).readings.count, 1)
            XCTAssertFalse(H.spoken(panel(), in: card).contains("Ignored"))
        }
    }

    func testHeldRefreshUsesSameIdentityAndRealCallbackOnly() throws {
        let held = M.Selection(scope: scope, identity: setID)
        let card = input(held: held)
        var calls: [M.Selection] = []
        let action = try XCTUnwrap(H.action(panel(), in: card, onSelect: { calls.append($0) }))
        XCTAssertTrue(calls.isEmpty, "rendering/action construction is passive")
        XCTAssertTrue(H.isSelected(panel(), in: card))
        action()
        XCTAssertEqual(calls, [held])
        XCTAssertNil(H.action(panel(), in: card, onSelect: nil))
        XCTAssertFalse(H.showsTapInvitation(card, onSelect: nil))
        XCTAssertTrue(H.showsTapInvitation(card, onSelect: { _ in }))
        let refreshed = input(originals: [original(later: .value("60%", placement: 0.6, provenance: "Own new clock"))],
                              panels: [panel()], held: held)
        XCTAssertTrue(H.isSelected(panel(), in: refreshed))
        XCTAssertEqual(try shown(panel(), refreshed).readings[1].text, "60%")
        XCTAssertEqual(try shown(panel(), refreshed).readings[1].provenance, "Own new clock")
        let withdrawn = input(originals: [], panels: [panel()], held: held)
        XCTAssertFalse(H.isSelected(panel(), in: withdrawn))
        XCTAssertFalse(H.isSelected(panel(), in: input(held: M.Selection(scope: "other", identity: setID))))
    }

    func testPendingWithdrawalAndResultWithoutGradeHaveNoDecoration() throws {
        let noNote = panel(pending: " \n")
        XCTAssertNil(try shown(noNote, input(panels: [noNote])).pendingMarketContext)
        let result = try shown(panel(), input(originals: [original(mode: .result)], panels: [panel()]))
        XCTAssertEqual(result.result?.words, M.resultUnavailable)
        XCTAssertNil(result.mark)
        XCTAssertNil(result.pendingMarketContext)
    }

    func testLayoutPlanningStacksWholePanelsAtNarrowAndAccessibilitySizes() {
        XCTAssertEqual(OriginalHandicapLayout9483.minimumTarget, 44)
        XCTAssertNil(OriginalHandicapLayout9483.sharedWidth(available: 280, ideals: [180, 190], spacing: 10,
                                                           accessibilitySize: false))
        XCTAssertNil(OriginalHandicapLayout9483.sharedWidth(available: 900, ideals: [180, 190], spacing: 10,
                                                           accessibilitySize: true))
        XCTAssertEqual(OriginalHandicapLayout9483.sharedWidth(available: 500, ideals: [180, 190], spacing: 10,
                                                             accessibilitySize: false), 245)
        XCTAssertTrue(ProbabilityDetailsLayout9483.alwaysStacks(readings: 1, accessibilitySize: false))
        // Arithmetic only: actual compact/wide/AX rendering, VoiceOver and 44pt
        // hit-area qualification remain NOT_RUN, as do all tests in this appendix.
    }
}
