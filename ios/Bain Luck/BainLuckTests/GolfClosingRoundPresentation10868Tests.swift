import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the golf journey's final closing-round card (`golf-journey`, final
/// phase): the field's completed final rounds as one dot distribution on a
/// shared signed strokes-against-par axis, the selected golfer's round, total,
/// placement and own dated earlier win chance together, and the owner's choices,
/// window and chooser.
///
/// PREPARED / NOT RUN. Nothing here claims a compile, a rendered fit, VoiceOver,
/// a native runtime or a live route. What is asserted: the exact retained rows
/// and examples; each row's own baseline and nobody else's; duplicate, foreign,
/// shared, unlinked and unknown identities; the one final admission in both
/// directions; invalid geometry kept reachable; selection, once-only holds, the
/// stream's activation, exact full-size and Back callbacks and a bad future-key
/// control; hosted width and text-size measurements; and 44 pt targets tied to
/// the one control every local touch area uses.
///
/// RETAINED, generated mechanically by `/tmp/golf-closing-fixture-gen.py` from
/// `golfJourney.json` (sha256 1bdd575d…0330fa1) into the "Retained fixture
/// (generated)" section at the end of this file. It is a lossless extraction
/// of the CONSUMED fields only, numbers kept as their source text: the event
/// name, key, start, capture time, terminal observation and policy; the
/// market's id, name, source, external id, status and outcome count; each of
/// the 155 outcomes' id, name, winner flag and resolution source; every one of
/// the 13 history series with every point; every leaderboard row; every round
/// boundary; and the final status fields with every field of all 72 players.
/// The outcomes' quote, rank and clock metadata and the other market and
/// history fields are excluded; nothing here claims anything about them. The
/// test owner below is the host's job done from that capture with the
/// reference's own rules (the closing-field predicate, the unique-name
/// correspondence, the last valid point strictly before the start,
/// final-and-leaderboard agreement); it is not product code.
///
/// CONSTRUCTED cases say so in their names or messages: they edit retained
/// rows to make a geometry, identity or phase case the capture does not carry.
@MainActor
final class GolfClosingRoundPresentation10868Tests: XCTestCase {
    typealias Model = GolfClosingRoundModel10868
    typealias Geometry = GolfClosingRoundGeometry10868
    typealias Presentation = GolfClosingRoundPresentation10868

    // MARK: - Test owner (the host's job, from the retained capture)

    static let fixtureScope = "golf-journey:datagolf:pga:527:final"
    static let fixtureSource = "datagolf"
    static let windowSize = 12
    static let featuredNames = ["Michael Brennan", "Adam Scott", "Min Woo Lee"]
    static let beforeLabel = "Before tournament"
    static let missingBefore = "Not recorded before the tournament"
    static let detailsAction = FieldHistoryAction10868(
        id: "closing.details", label: "Score & source details", spokenLabel: nil, isAvailable: true)
    static let chrome = GolfClosingRoundChrome10868(
        backLabel: "Back to tournament", backHint: nil,
        unavailableWords: "The closing round appears when the final round is complete")

    /// Everything the owner hands the card, editable per case.
    struct Build {
        var rows: [GolfClosingRoundRow10868]
        var catalogue: [FieldChooserOriginal10868]
        var axis: GolfClosingRoundAxis10868
        var selectedRowID: String?
        var featuredRowIDs: [String]
        var details: FieldHistoryAction10868?
        var window: GolfClosingRoundWindow10868?
        var phase: FieldOutlookPhase10868 = .final
        var admitted: Bool = true
    }

    static let isoParser: ISO8601DateFormatter = {
        let parser = ISO8601DateFormatter()
        parser.formatOptions = [.withInternetDateTime]
        return parser
    }()

    /// Seconds since 1970 at full source precision; the source writes UTC with
    /// an optional fraction.
    static func instant(_ iso: String) -> Double? {
        guard iso.count >= 19, iso.hasSuffix("+00:00"),
              let whole = isoParser.date(from: String(iso.prefix(19)) + "Z") else { return nil }
        let body = iso.dropLast(6)
        var fraction = 0.0
        if let dot = body.firstIndex(of: ".") {
            guard let parsed = Double("0" + String(body[dot...])) else { return nil }
            fraction = parsed
        }
        return whole.timeIntervalSince1970 + fraction
    }

    static func pacific(_ iso: String) -> String {
        guard let seconds = instant(iso) else { return "" }
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "America/Los_Angeles")
        formatter.dateFormat = "MMM d, h:mm a"
        return formatter.string(from: Date(timeIntervalSince1970: seconds)) + " PT"
    }

    static func percent(_ probability: Double) -> String {
        String(format: "%.1f%%", probability * 100)
    }

    /// The reference's figure: zero is level, over par carries a plus.
    static func score(_ value: Double) -> String {
        value == 0 ? "E" : value > 0 ? "+\(Int(value))" : "\(Int(value))"
    }

    static func strokesWords(_ value: Double) -> String {
        if value < 0 { return "\(Int(-value)) stroke\(value == -1 ? "" : "s") under par" }
        if value > 0 { return "\(Int(value)) stroke\(value == 1 ? "" : "s") over par" }
        return "Level par"
    }

    /// The reference's closing field, in the final order.
    static func closingField() -> [GolfClosingRetainedPlayer10868] {
        retainedPlayers.filter { player in
            player.currentRound == "4" && player.thru == "18" && (Double(player.todayRaw)?.isFinite ?? false)
        }
    }

    /// The one outcome carrying this exact name, or none.
    static func outcomeNamed(_ name: String) -> GolfClosingRetainedOutcome10868? {
        let matches = retainedOutcomes.filter { $0.name == name }
        return matches.count == 1 ? matches[0] : nil
    }

    static func ref(_ outcomeID: String) -> FieldChooserOriginalRef10868 {
        FieldChooserOriginalRef10868(scope: fixtureScope, source: fixtureSource,
                                     marketID: retainedEvent.marketID, outcomeID: outcomeID)
    }

    /// The owner's row id: the leaderboard's player id when final and
    /// leaderboard agree, else the name.
    static func rowID(_ name: String) -> String {
        let leaders = retainedLeaderboard.filter { $0.name == name }
        let players = retainedPlayers.filter { $0.name == name }
        guard leaders.count == 1, players.count == 1,
              leaders[0].totalScore == players[0].totalScoreRaw,
              leaders[0].todayScore == players[0].todayRaw,
              leaders[0].position == players[0].position
        else { return "name:\(name)" }
        return "dg:\(leaders[0].dgID)"
    }

    /// The reference's baseline: the last valid point strictly before the start.
    static func baselinePoint(outcomeID: String, name: String) -> GolfClosingRetainedPoint10868? {
        let series = retainedSeries.filter { $0.outcomeID == outcomeID && $0.name == name }
        guard series.count == 1, let start = instant(retainedEvent.start) else { return nil }
        let valid = series[0].history.filter { point in
            guard let probability = Double(point.probability) else { return false }
            return probability.isFinite && probability >= 0 && probability <= 1
        }
        return valid.filter { point in (instant(point.timestamp) ?? .infinity) < start }.last
    }

    static func beforeReading(_ point: GolfClosingRetainedPoint10868?) -> FieldChooserReading10868 {
        guard let point, let probability = Double(point.probability) else {
            return FieldChooserReading10868(label: beforeLabel, value: .missing(missingBefore))
        }
        return FieldChooserReading10868(
            label: beforeLabel,
            value: .recorded(text: percent(probability), detail: "\(pacific(point.timestamp)) · DataGolf-derived record"))
    }

    static func ownerCatalogue() -> [FieldChooserOriginal10868] {
        retainedOutcomes.map { outcome -> FieldChooserOriginal10868 in
            let point = baselinePoint(outcomeID: outcome.id, name: outcome.name)
            return FieldChooserOriginal10868(
                ref: ref(outcome.id), name: outcome.name, plan: .single(beforeReading(point)),
                preview: FieldChooserPreview10868(history: nil, absence: "No preview in this card"),
                movement: nil, clock: nil, result: nil,
                browseStatus: point == nil ? "No recorded history" : "Recorded history available")
        }
    }

    static func ownerRows() -> [GolfClosingRoundRow10868] {
        var stacks: [String: Int] = [:]
        return closingField().map { player -> GolfClosingRoundRow10868 in
            let today = Double(player.todayRaw) ?? .nan
            let total = Double(player.totalScoreRaw) ?? .nan
            let stack = stacks[player.todayRaw, default: 0]
            stacks[player.todayRaw] = stack + 1
            let linked = outcomeNamed(player.name)
            let point = linked.flatMap { baselinePoint(outcomeID: $0.id, name: $0.name) }
            var owned: GolfClosingRoundBaseline10868?
            if let linked, let point, let probability = Double(point.probability) {
                owned = GolfClosingRoundBaseline10868(
                    observationID: "\(linked.id)@\(point.timestamp)",
                    chance: FieldOutlookBeforeChance10868(ref: ref(linked.id), probability: probability,
                                                          reading: beforeReading(point)))
            }
            return GolfClosingRoundRow10868(
                id: rowID(player.name), name: player.name, original: linked.map { ref($0.id) },
                round: .reported(relative: today, text: score(today), detail: strokesWords(today)),
                total: score(total), placement: player.position,
                cell: GolfClosingRoundCell10868(bin: today, stack: stack), baseline: owned)
        }
    }

    static func ownerAxis() -> GolfClosingRoundAxis10868 {
        let bins = closingField().compactMap { Double($0.todayRaw) }
        let lower = bins.min() ?? 0
        let upper = bins.max() ?? 0
        var counts: [Double: Int] = [:]
        for bin in bins { counts[bin, default: 0] += 1 }
        return GolfClosingRoundAxis10868(
            lower: lower, upper: upper, stackCeiling: counts.values.max() ?? 1,
            ticks: stride(from: lower, through: upper, by: 1).map { GolfRoundScoreTick10868(value: $0, label: score($0)) },
            underWords: "← Under par", overWords: "Over par →",
            words: "Strokes relative to par in the final round; lower is better")
    }

    static func ownerWindow(page: Int, rows: [GolfClosingRoundRow10868]) -> GolfClosingRoundWindow10868 {
        let start = page * windowSize
        let end = min(start + windowSize, rows.count)
        let ids = start < end ? rows[start..<end].map { $0.id } : []
        let pages = (rows.count + windowSize - 1) / windowSize
        return GolfClosingRoundWindow10868(
            title: "Golfers \(start + 1)–\(end) of \(rows.count)", rowIDs: ids,
            previous: FieldHistoryAction10868(id: "window.previous", label: "Previous golfers", spokenLabel: nil, isAvailable: page > 0),
            next: FieldHistoryAction10868(id: "window.next", label: "Next golfers", spokenLabel: nil, isAvailable: page + 1 < pages))
    }

    static func ownerCopy(count: Int) -> GolfClosingRoundCopy10868 {
        GolfClosingRoundCopy10868(
            eyebrow: "Actual performance · final round", title: "The closing round",
            plotHeading: "Each dot is one golfer", plotCount: "\(count) completed rounds",
            graphicLabel: "Distribution of final-round scores relative to par. A blue ring marks the selected golfer.",
            selectedKey: "Selected golfer", selectedWords: "Selected",
            roundLabel: "Final round", totalLabel: "Total", placementLabel: "Finished",
            baselineLabel: "Before tournament", originalLabel: "Original outcome", gradeLabel: "Market result",
            noSelection: "Choose a golfer to compare", rowUnavailable: "Golfer unavailable in this update",
            valueUnavailable: "Not reported", unplaced: "This round is not placed on the plot",
            baselineUnavailable: "Not recorded before the tournament", unlinked: "No original outcome linked",
            originalUnavailable: "Original outcome unavailable in this update",
            gradeUnavailable: "Not settled in this capture",
            note: "Round score is relative to par, not a predicted score. It does not explain every change in win probability.",
            openLabel: "Open closing round", openHint: "Shows the closing round full size",
            changeGolferLabel: "Change golfer", chooseHint: "Shows this golfer's closing round")
    }

    static func retained() -> Build {
        let ownRows = ownerRows()
        return Build(
            rows: ownRows, catalogue: ownerCatalogue(), axis: ownerAxis(),
            selectedRowID: rowID("Michael Brennan"),
            featuredRowIDs: featuredNames.map { rowID($0) },
            details: detailsAction,
            window: ownerWindow(page: 0, rows: ownRows))
    }

    static func chooserInput(_ build: Build) -> FieldChooserInput10868 {
        let featuredRefs = build.featuredRowIDs.compactMap { id in build.rows.first(where: { $0.id == id })?.original }
        let selectedRef = build.selectedRowID.flatMap { id in build.rows.first(where: { $0.id == id })?.original }
        return FieldChooserInput10868(
            scope: fixtureScope, intro: nil,
            featured: FieldChooserFeatured10868(title: "Compare", badge: nil, refs: featuredRefs, emptyWords: "No featured golfers"),
            context: nil, more: nil, browse: nil, catalogue: build.catalogue, frame: nil,
            selected: selectedRef.map { FieldChooserSelected10868(ref: $0, words: "Selected", unavailableWords: "Golfer unavailable in this update") },
            unavailableWords: "Golfer unavailable in this update", chooseHint: "Shows this golfer's closing round")
    }

    static func ownerInput(_ build: Build) -> GolfClosingRoundInput10868 {
        let content = GolfClosingRoundContent10868(
            originals: chooserInput(build), rows: build.rows, axis: build.axis,
            selectedRowID: build.selectedRowID,
            featured: GolfClosingRoundChoices10868(title: "Compare", rowIDs: build.featuredRowIDs),
            window: build.window, details: build.details, copy: ownerCopy(count: build.rows.count))
        return GolfClosingRoundInput10868(phase: build.phase, admission: build.admitted ? .final(content) : .withheld, chrome: chrome)
    }

    static func ownerModel(_ build: Build) -> Model { Model(ownerInput(build)) }

    static func index(_ build: Build, _ name: String) -> Int {
        build.rows.firstIndex(where: { $0.name == name }) ?? -1
    }

    /// A hosted measurement at an explicit text size and width class.
    static func fitted<V: View>(_ view: V, width: CGFloat, size: DynamicTypeSize,
                                sizeClass: UserInterfaceSizeClass = .compact) -> CGSize {
        hostForMeasurement(view.environment(\.horizontalSizeClass, sizeClass), at: size)
            .sizeThatFits(in: CGSize(width: width, height: .greatestFiniteMagnitude))
    }

    static func activation(log: GolfClosingCallLog10868) -> StoryStreamCardActivation10868 {
        let card = StoryStreamPresentation10868.CardRef(scope: fixtureScope, id: "closing-round")
        return StoryStreamCardActivation10868(card: card, intents: [.interaction(scope: fixtureScope, card: card)]) { intent in
            if case .interaction(_, let held) = intent { log.entries.append("activate:\(held?.id ?? "-")") } else { log.entries.append("other") }
        }
    }

    // MARK: - Tests
    // MARK: Retained rows

    func testRetainedCaptureCarriesTheAdmittedCounts() {
        let event = Self.retainedEvent
        XCTAssertEqual(event.marketID, "64266833")
        XCTAssertEqual(event.marketSource, "datagolf")
        XCTAssertEqual(event.start, "2026-10-08T00:00:00+00:00")
        XCTAssertEqual(event.finalStatus, "completed")
        XCTAssertEqual(event.finalCurrentRound, "4")
        XCTAssertEqual(event.outcomeCount, "155")
        XCTAssertEqual(Self.retainedOutcomes.count, 155)
        XCTAssertEqual(Set(Self.retainedOutcomes.map { $0.id }).count, 155)
        XCTAssertEqual(Set(Self.retainedOutcomes.map { $0.name }).count, 155)
        XCTAssertTrue(Self.retainedOutcomes.allSatisfy { $0.isWinner == nil && $0.resolutionSource == nil },
                      "the capture carries no settlement, so no contract grade is retained")
        XCTAssertEqual(Self.retainedSeries.count, 13)
        XCTAssertEqual(Self.retainedSeries.reduce(0) { $0 + $1.history.count }, 3570)
        XCTAssertTrue(Self.retainedSeries.allSatisfy { series in series.history.allSatisfy { Self.instant($0.timestamp) != nil } },
                      "every point is a readable UTC instant")
        XCTAssertEqual(Self.retainedPlayers.count, 72)
        XCTAssertEqual(Set(Self.retainedPlayers.map { $0.name }).count, 72)
        XCTAssertEqual(Self.retainedLeaderboard.count, 72)

        let field = Self.closingField()
        XCTAssertEqual(field.count, 72, "every final player completed round 4 through 18")
        let rounds = field.compactMap { Int($0.todayRaw) }
        XCTAssertEqual(rounds.count, 72)
        XCTAssertEqual(rounds.min(), -7)
        XCTAssertEqual(rounds.max(), 5)
        XCTAssertTrue(field.allSatisfy { Self.rowID($0.name).hasPrefix("dg:") },
                      "final and leaderboard agree on total, round and position for every row")
        XCTAssertTrue(field.allSatisfy { Self.outcomeNamed($0.name) != nil },
                      "every final player has exactly one original by name")
    }

    func testOwnerRowsAreTheSeventyTwoCompletedRoundsInFinalOrder() {
        let build = Self.retained()
        let model = Self.ownerModel(build)
        XCTAssertTrue(model.isAdmitted)
        XCTAssertEqual(build.rows.map { $0.name }, Self.closingField().map { $0.name })
        XCTAssertEqual(Set(build.rows.map { $0.id }).count, 72)
        XCTAssertEqual(model.placed.count, 72, "every completed round draws exactly one dot")
        XCTAssertEqual(model.placed.map { $0.rowID }, build.rows.map { $0.id }, "dots keep the owner's order")
        for row in build.rows {
            XCTAssertEqual(model.row(row.id), row)
            guard case .reported(let relative, _, _) = row.round else { return XCTFail("reported \(row.name)") }
            XCTAssertEqual(row.cell?.bin, relative, row.name)
        }
        XCTAssertTrue(build.axis.isValid)
        XCTAssertEqual(build.axis.lower, -7)
        XCTAssertEqual(build.axis.upper, 5)
        XCTAssertEqual(build.axis.ticks.map { $0.label },
                       ["-7", "-6", "-5", "-4", "-3", "-2", "-1", "E", "+1", "+2", "+3", "+4", "+5"])
        XCTAssertEqual(Geometry.ticks(build.axis).count, 13)
    }

    func testSelectedExamplesCarryTheirOwnRoundTotalAndPlacement() throws {
        let build = Self.retained()
        let model = Self.ownerModel(build)
        let expected: [(name: String, id: String, relative: Double, round: String, total: String, placement: String)] = [
            ("Michael Brennan", "dg:29197", -3, "-3", "-16", "1"),
            ("Min Woo Lee", "dg:16841", -5, "-5", "-12", "T9"),
            ("Adam Scott", "dg:6430", 1, "+1", "-11", "T13"),
        ]
        for example in expected {
            XCTAssertEqual(Self.rowID(example.name), example.id)
            let row = try XCTUnwrap(model.row(example.id), example.name)
            XCTAssertEqual(row.name, example.name)
            XCTAssertEqual(row.round, .reported(relative: example.relative, text: example.round,
                                                detail: Self.strokesWords(example.relative)))
            XCTAssertEqual(row.total, example.total)
            XCTAssertEqual(row.placement, example.placement)
            XCTAssertEqual(model.entryPairs(row), [
                GolfClosingRoundPair10868(label: "Final round", value: example.round),
                GolfClosingRoundPair10868(label: "Total", value: example.total),
                GolfClosingRoundPair10868(label: "Finished", value: example.placement),
            ])
            let player = try XCTUnwrap(Self.retainedPlayers.first(where: { $0.name == example.name }))
            XCTAssertEqual(player.todayRaw, String(Int(example.relative)), "the row's round is the capture's own")
            XCTAssertEqual(player.totalScoreRaw, example.total)
            XCTAssertEqual(player.position, example.placement)
        }
        XCTAssertEqual(model.selectedRowID, "dg:29197")
        let summary = model.selectedSummary(full: false)
        for words in ["Michael Brennan", "Selected", "Final round: -3, 3 strokes under par", "Total: -16", "Finished: 1",
                      "Before tournament: 2.6%, Oct 6, 6:08 AM PT · DataGolf-derived record"] {
            XCTAssertTrue(summary.contains(words), "selected together: \(words)")
        }
    }

    func testEqualScoresStackWithoutIdentityLoss() throws {
        let build = Self.retained()
        let model = Self.ownerModel(build)
        var byBin: [Double: [Int]] = [:]
        for row in build.rows {
            if let cell = row.cell { byBin[cell.bin, default: []].append(cell.stack) }
        }
        for (bin, stacks) in byBin {
            XCTAssertEqual(stacks, Array(0..<stacks.count), "bin \(bin) stacks from the axis in the owner's order")
        }
        XCTAssertEqual(byBin.values.map { $0.count }.max(), build.axis.stackCeiling)

        let plotHeight = try XCTUnwrap(Geometry.height(build.axis))
        let drawn = Geometry.dots(model.placed, selected: model.selectedRowID, in: CGSize(width: 343, height: plotHeight))
        XCTAssertEqual(drawn.count, 72)
        XCTAssertEqual(Set(drawn.map { $0.rowID }), Set(build.rows.map { $0.id }))
        XCTAssertEqual(Set(drawn.map { "\($0.center.x),\($0.center.y)" }).count, 72, "no two rounds share a position")
        XCTAssertEqual(drawn.filter { $0.isSelected }.map { $0.rowID }, ["dg:29197"], "one ring, on the selected golfer")

        let sameBin = drawn.filter { dot in build.rows.first(where: { $0.id == dot.rowID })?.cell?.bin == -3 }
        XCTAssertGreaterThan(sameBin.count, 1)
        XCTAssertEqual(Set(sameBin.map { $0.center.x }).count, 1, "equal scores share one column")
        let heights = sameBin.map { $0.center.y }.sorted(by: >)
        for (lower, upper) in zip(heights, heights.dropFirst()) {
            XCTAssertEqual(lower - upper, Geometry.pitch, accuracy: 0.0001, "each next golfer one step higher")
        }
    }
    // MARK: Own baselines and identities

    /// A retained row with the named parts replaced; `.some(nil)` clears an optional.
    static func edit(_ row: GolfClosingRoundRow10868, id: String? = nil, name: String? = nil,
                     original: FieldChooserOriginalRef10868?? = nil, round: GolfRoundScoreValue10868? = nil,
                     total: String? = nil, placement: String? = nil,
                     cell: GolfClosingRoundCell10868?? = nil,
                     baseline: GolfClosingRoundBaseline10868?? = nil) -> GolfClosingRoundRow10868 {
        GolfClosingRoundRow10868(
            id: id ?? row.id, name: name ?? row.name, original: original ?? row.original,
            round: round ?? row.round, total: total ?? row.total, placement: placement ?? row.placement,
            cell: cell ?? row.cell, baseline: baseline ?? row.baseline)
    }

    func testOwnBaselinesShowOnlyForTheThirteenWithHistory() throws {
        let build = Self.retained()
        let model = Self.ownerModel(build)
        var recorded: [String: GolfClosingRoundBaselineState10868] = [:]
        for row in build.rows {
            if case .recorded = model.baseline(row) { recorded[row.name] = model.baseline(row) }
        }
        XCTAssertEqual(Set(recorded.keys), Set(Self.retainedSeries.map { $0.name }), "the 13 with history and no one else")
        for series in Self.retainedSeries {
            let point = try XCTUnwrap(Self.baselinePoint(outcomeID: series.outcomeID, name: series.name), series.name)
            XCTAssertEqual(point.timestamp, "2026-10-06T13:08:40.644152+00:00", "last valid point before the start: \(series.name)")
            let probability = try XCTUnwrap(Double(point.probability))
            XCTAssertEqual(recorded[series.name],
                           .recorded(label: "Before tournament", text: Self.percent(probability),
                                     detail: "Oct 6, 6:08 AM PT · DataGolf-derived record"), series.name)
        }
        let unavailable = build.rows.filter { model.baseline($0) == .unavailable }
        XCTAssertEqual(unavailable.count, 59)
        XCTAssertTrue(unavailable.allSatisfy { $0.baseline == nil }, "a missing own history stays unavailable; nothing is borrowed")

        let examples: [(id: String, text: String)] = [("dg:29197", "2.6%"), ("dg:16841", "3.9%"), ("dg:6430", "3.5%")]
        for example in examples {
            let row = try XCTUnwrap(model.row(example.id))
            XCTAssertEqual(model.baseline(row), .recorded(label: "Before tournament", text: example.text,
                                                          detail: "Oct 6, 6:08 AM PT · DataGolf-derived record"), example.id)
        }
    }

    func testABaselineThatIsNotTheRowsOwnIsUnavailable() throws {
        // CONSTRUCTED: retained rows with an edited baseline or catalogue record.
        let build = Self.retained()
        let scott = Self.index(build, "Adam Scott")
        let brennan = Self.index(build, "Michael Brennan")
        let own = try XCTUnwrap(build.rows[scott].baseline)
        let ownReading = own.chance.reading

        func state(_ baseline: GolfClosingRoundBaseline10868?, catalogue: [FieldChooserOriginal10868]? = nil) -> GolfClosingRoundBaselineState10868 {
            var edited = build
            edited.rows[scott] = Self.edit(build.rows[scott], baseline: baseline)
            if let catalogue { edited.catalogue = catalogue }
            return Self.ownerModel(edited).baseline(edited.rows[scott])
        }

        XCTAssertNotEqual(state(own), .unavailable, "positive control: the row's own baseline shows")
        XCTAssertEqual(state(build.rows[brennan].baseline), .unavailable, "another golfer's chance is never borrowed")
        XCTAssertEqual(state(GolfClosingRoundBaseline10868(observationID: "  ", chance: own.chance)), .unavailable,
                       "no readable observation id")
        let reworded = FieldChooserReading10868(label: ownReading.label, value: .recorded(text: "9.9%", detail: "Oct 6, 6:08 AM PT"))
        XCTAssertEqual(state(GolfClosingRoundBaseline10868(
            observationID: own.observationID,
            chance: FieldOutlookBeforeChance10868(ref: own.chance.ref, probability: own.chance.probability, reading: reworded))),
            .unavailable, "a reading that is not the original's own before reading")
        for probability in [1.5, -0.1, Double.nan, Double.infinity] {
            XCTAssertEqual(state(GolfClosingRoundBaseline10868(
                observationID: own.observationID,
                chance: FieldOutlookBeforeChance10868(ref: own.chance.ref, probability: probability, reading: ownReading))),
                .unavailable, "raw value \(probability) is not a chance")
        }

        // An undated reading tied to an equally undated plan: tied, but no readable date.
        let undated = FieldChooserReading10868(label: ownReading.label, value: .recorded(text: "3.5%", detail: " "))
        let catalogue = build.catalogue.map { record -> FieldChooserOriginal10868 in
            guard record.name == "Adam Scott" else { return record }
            return FieldChooserOriginal10868(ref: record.ref, name: record.name, plan: .single(undated), preview: record.preview,
                                             movement: record.movement, clock: record.clock, result: record.result,
                                             browseStatus: record.browseStatus)
        }
        XCTAssertEqual(state(GolfClosingRoundBaseline10868(
            observationID: own.observationID,
            chance: FieldOutlookBeforeChance10868(ref: own.chance.ref, probability: own.chance.probability, reading: undated)),
            catalogue: catalogue), .unavailable, "a figure without a readable date")
        XCTAssertEqual(state(nil), .unavailable)
    }

    func testDuplicateRowIdentityIsNeitherDrawnNorSelectable() throws {
        // CONSTRUCTED: one retained row re-labelled with another's id.
        var build = Self.retained()
        let lee = Self.index(build, "Min Woo Lee")
        build.rows[lee] = Self.edit(build.rows[lee], id: "dg:29197")
        let model = Self.ownerModel(build)
        XCTAssertNil(model.row("dg:29197"))
        XCTAssertNil(model.row("dg:16841"))
        XCTAssertEqual(model.selection, .unavailable)
        XCTAssertNil(model.chooseAction("dg:29197"))
        XCTAssertFalse(model.placed.contains { $0.rowID == "dg:29197" }, "neither twin is drawn")
        XCTAssertEqual(model.placed.count, 70)
        XCTAssertEqual(model.selectedSummary(full: true), "Golfer unavailable in this update")
        XCTAssertNil(model.featured.first(where: { $0.id == "dg:29197" })?.row)
        let presentation = Presentation(input: Self.ownerInput(build), mode: .full, onChooseRow: { _ in })
        XCTAssertFalse(presentation.controls.contains(.choose("dg:29197")))
        XCTAssertTrue(presentation.controls.contains(.choose("dg:6430")), "positive control: an untouched featured golfer")

        var blank = Self.retained()
        let scott = Self.index(blank, "Adam Scott")
        blank.rows[scott] = Self.edit(blank.rows[scott], id: "  ")
        let brennan = Self.index(blank, "Michael Brennan")
        blank.rows[brennan] = Self.edit(blank.rows[brennan], name: "")
        let blankModel = Self.ownerModel(blank)
        XCTAssertNil(blankModel.row("  "), "a blank id is not an identity")
        XCTAssertNil(blankModel.row("dg:29197"), "a row without a readable name is not shown as a golfer")
        XCTAssertEqual(blankModel.placed.count, 70)
    }

    func testForeignSharedAndUnknownOriginalsStayUnavailableButTheRowStaysSelectable() throws {
        // CONSTRUCTED: retained rows with an edited correspondence.
        var foreign = Self.retained()
        let scott = Self.index(foreign, "Adam Scott")
        let scottRef = try XCTUnwrap(foreign.rows[scott].original)
        foreign.rows[scott] = Self.edit(foreign.rows[scott], original: FieldChooserOriginalRef10868(
            scope: "golf-journey:another-event:final", source: scottRef.source, marketID: scottRef.marketID, outcomeID: scottRef.outcomeID))
        let foreignModel = Self.ownerModel(foreign)
        let row = try XCTUnwrap(foreignModel.row("dg:6430"))
        XCTAssertEqual(foreignModel.original(row), .unavailable)
        XCTAssertEqual(foreignModel.baseline(row), .unavailable, "a foreign link carries no earlier chance")
        XCTAssertEqual(foreignModel.chooseAction(row.id), row.id, "the row itself stays selectable")
        XCTAssertTrue(foreignModel.isPlaced(row))

        var shared = Self.retained()
        let lee = Self.index(shared, "Min Woo Lee")
        shared.rows[lee] = Self.edit(shared.rows[lee], original: shared.rows[Self.index(shared, "Michael Brennan")].original)
        let sharedModel = Self.ownerModel(shared)
        for id in ["dg:29197", "dg:16841"] {
            let linked = try XCTUnwrap(sharedModel.row(id))
            XCTAssertEqual(sharedModel.original(linked), .unavailable, "one original claimed by two rows: \(id)")
            XCTAssertEqual(sharedModel.baseline(linked), .unavailable, id)
        }

        var unknown = Self.retained()
        unknown.rows[scott] = Self.edit(unknown.rows[scott], original: Self.ref("999999999"))
        let unknownModel = Self.ownerModel(unknown)
        XCTAssertEqual(unknownModel.original(unknownModel.row("dg:6430")!), .unavailable, "an id the catalogue never carried")

        var duplicated = Self.retained()
        let record = try XCTUnwrap(duplicated.catalogue.first(where: { $0.name == "Adam Scott" }))
        duplicated.catalogue.append(record)
        let duplicatedModel = Self.ownerModel(duplicated)
        XCTAssertEqual(duplicatedModel.original(duplicatedModel.row("dg:6430")!), .unavailable,
                       "the chooser's own resolver refuses a record carried twice")
        let untouched = Self.ownerModel(Self.retained())
        guard case .linked(let resolved) = untouched.original(untouched.row("dg:6430")!) else { return XCTFail("positive control") }
        XCTAssertEqual(resolved.name, "Adam Scott")
        XCTAssertEqual(resolved.ref.outcomeID, "242242537")
    }

    func testAnUnlinkedRowIsSelectableWithoutAFakeOriginal() throws {
        // CONSTRUCTED: the owner links no original for one retained row.
        var build = Self.retained()
        let scott = Self.index(build, "Adam Scott")
        build.rows[scott] = Self.edit(build.rows[scott], original: .some(nil))
        build.selectedRowID = "dg:6430"
        let model = Self.ownerModel(build)
        let row = try XCTUnwrap(model.row("dg:6430"))
        XCTAssertNil(row.original)
        XCTAssertNotNil(row.baseline, "the owner's attached baseline is present but not trusted")
        XCTAssertEqual(model.original(row), .unlinked)
        XCTAssertEqual(model.baseline(row), .unavailable)
        XCTAssertNil(model.grade(row))
        XCTAssertEqual(model.selection, .row(row))
        let summary = model.selectedSummary(full: true)
        for words in ["Adam Scott", "Final round: +1, 1 stroke over par", "Total: -11", "Finished: T13",
                      "Before tournament: Not recorded before the tournament",
                      "Market result: Not settled in this capture", "Original outcome: No original outcome linked"] {
            XCTAssertTrue(summary.contains(words), words)
        }
        XCTAssertFalse(summary.contains("3.5%"))
        XCTAssertNil(Self.chooserInput(build).selected, "the chooser carries no stand-in original")

        var log: [String] = []
        let presentation = Presentation(input: Self.ownerInput(build), mode: .full, onChooseRow: { log.append($0) })
        let entry = try XCTUnwrap(model.featured.first(where: { $0.id == "dg:6430" }))
        presentation.chooseControl(entry)?()
        XCTAssertEqual(log, ["dg:6430"], "the unlinked row hands back its own exact id")
    }
    // MARK: Selection words, admission and geometry

    func testUnknownSelectionAndAFutureKeyChoiceShowTheOwnersWordsAndCallNothing() throws {
        // CONSTRUCTED: ids the retained rows do not carry.
        var build = Self.retained()
        build.selectedRowID = "dg:0000"
        build.featuredRowIDs = ["dg:29197", "dg:future-key"]
        let model = Self.ownerModel(build)
        XCTAssertEqual(model.selection, .unavailable)
        XCTAssertNil(model.selectedRowID)
        XCTAssertEqual(model.selectedSummary(full: false), "Golfer unavailable in this update")
        XCTAssertEqual(model.featured.map { $0.row?.name }, ["Michael Brennan", nil] as [String?])
        XCTAssertNil(model.chooseAction("dg:future-key"))

        var log: [String] = []
        var holds = 0
        let presentation = Presentation(input: Self.ownerInput(build), onChooseRow: { log.append($0) }, onInteraction: { holds += 1 })
        XCTAssertNil(presentation.chooseControl(GolfClosingRoundEntry10868(id: "dg:future-key", row: nil)))
        XCTAssertNil(presentation.chooseControl(GolfClosingRoundEntry10868(id: "dg:future-key", row: build.rows[0])),
                     "bad payload control: an entry is chosen by its own id, never by a row it carries")
        XCTAssertEqual(presentation.controls.filter { control in
            if case .choose = control { return true }
            return false
        }, [.choose("dg:29197")])
        XCTAssertEqual(log, [])
        XCTAssertEqual(holds, 0, "building and reading the card calls nothing")
        presentation.chooseControl(model.featured[0])?()
        XCTAssertEqual(log, ["dg:29197"])
        XCTAssertEqual(holds, 1)

        var unselected = Self.retained()
        unselected.selectedRowID = nil
        let unselectedModel = Self.ownerModel(unselected)
        XCTAssertEqual(unselectedModel.selection, .unselected)
        XCTAssertEqual(unselectedModel.selectedSummary(full: true), "Choose a golfer to compare")
        XCTAssertTrue(Geometry.dots(unselectedModel.placed, selected: unselectedModel.selectedRowID,
                                    in: CGSize(width: 343, height: 200)).allSatisfy { !$0.isSelected })
    }

    func testTheFinalPhaseWithTheOwnersAdmissionShowsTheCardAndItsActions() {
        let build = Self.retained()
        let model = Self.ownerModel(build)
        XCTAssertNotNil(model.admitted)
        XCTAssertNotNil(model.originals)
        XCTAssertEqual(model.placed.count, 72)
        XCTAssertTrue(model.plotSummary.contains("72 completed rounds"))
        let featured: [GolfClosingRoundControl10868] = [.choose("dg:29197"), .choose("dg:6430"), .choose("dg:16841")]
        let window: [GolfClosingRoundControl10868] = build.rows.prefix(12).map { GolfClosingRoundControl10868.choose($0.id) }
        let head: [GolfClosingRoundControl10868] = [.back, .chooser]
        let tail: [GolfClosingRoundControl10868] = [.action("window.next"), .action("closing.details")]
        let compactTail: [GolfClosingRoundControl10868] = [.open, .action("closing.details")]

        let full = Presentation(input: Self.ownerInput(build), mode: .full, onBack: {}, onChooser: {},
                                onChooseRow: { _ in }, onAction: { _ in })
        XCTAssertEqual(full.controls, head + featured + window + tail, "the first window has no previous step")
        let compact = Presentation(input: Self.ownerInput(build), onOpen: {}, onChooseRow: { _ in }, onAction: { _ in })
        XCTAssertEqual(compact.controls, featured + compactTail)
        let chooser = Presentation(input: Self.ownerInput(build), mode: .chooser, onBack: {}, onChooseOriginal: { _ in })
        XCTAssertEqual(chooser.controls, [.back, .chooserList])
        XCTAssertTrue(chooser.chooserListShown)
    }

    func testBeforeAndDuringWithholdEveryActualAndActionButKeepBack() {
        // CONSTRUCTED phases: the retained final content handed over in the wrong phase.
        for phase in [FieldOutlookPhase10868.before, .during] {
            var build = Self.retained()
            build.phase = phase
            let input = Self.ownerInput(build)
            guard case .final = input.admission else { return XCTFail("the owner's final content is present in \(phase)") }
            let model = Model(input)
            XCTAssertNil(model.admitted, "\(phase)")
            XCTAssertNil(model.originals)
            XCTAssertTrue(model.placed.isEmpty)
            XCTAssertNil(model.row("dg:29197"))
            XCTAssertEqual(model.selection, .unselected)
            XCTAssertTrue(model.featured.isEmpty)
            XCTAssertTrue(model.window.isEmpty)
            XCTAssertNil(model.detailsAction)
            XCTAssertNil(model.nextAction)
            XCTAssertEqual(model.plotSummary, Self.chrome.unavailableWords)
            XCTAssertEqual(model.selectedSummary(full: true), Self.chrome.unavailableWords)
            XCTAssertEqual(model.rowSummary(build.rows[0]), "")
            XCTAssertEqual(model.entryPairs(build.rows[0]), [])
            XCTAssertEqual(model.baseline(build.rows[0]), .unavailable)
            XCTAssertNil(model.grade(build.rows[0]))

            var calls: [String] = []
            let full = Presentation(
                input: input, mode: .full,
                onOpen: { calls.append("open") }, onBack: { calls.append("back") }, onChooser: { calls.append("chooser") },
                onChooseRow: { calls.append("row:\($0)") }, onChooseOriginal: { _ in calls.append("original") },
                onChooserControl: { _ in calls.append("control") }, onAction: { calls.append("action:\($0)") },
                onInteraction: { calls.append("hold") })
            XCTAssertEqual(full.controls, [.back], "Back stays; every final action is hidden")
            let wiring = full.wiring
            XCTAssertNil(wiring.open)
            XCTAssertNil(wiring.chooser)
            XCTAssertNil(wiring.chooseRow)
            XCTAssertNil(wiring.action)
            XCTAssertNil(wiring.chooseOriginal)
            XCTAssertNil(wiring.chooserControl)
            XCTAssertEqual(calls, [])
            full.backControl()?()
            XCTAssertEqual(calls, ["back"], "Back is exact, with no hold")

            let chooser = Presentation(input: input, mode: .chooser, onBack: {}, onChooseOriginal: { _ in })
            XCTAssertEqual(chooser.controls, [.back])
            XCTAssertFalse(chooser.chooserListShown)
            let compact = Presentation(input: input, onOpen: {}, onChooseRow: { _ in }, onAction: { _ in }, onInteraction: {})
            XCTAssertEqual(compact.controls, [])
            XCTAssertNil(compact.openControl())
        }
    }

    func testTheFinalPhaseWithoutTheOwnersAdmissionWithholdsToo() {
        // CONSTRUCTED: the final phase with the owner's admission withheld.
        var build = Self.retained()
        build.admitted = false
        let input = Self.ownerInput(build)
        XCTAssertEqual(input.phase, .final)
        XCTAssertEqual(input.admission, .withheld)
        let model = Model(input)
        XCTAssertNil(model.admitted)
        XCTAssertTrue(model.placed.isEmpty)
        XCTAssertEqual(model.plotSummary, "The closing round appears when the final round is complete")
        let full = Presentation(input: input, mode: .full, onBack: {}, onChooser: {}, onChooseRow: { _ in }, onAction: { _ in })
        XCTAssertEqual(full.controls, [.back])

        build.admitted = true
        XCTAssertEqual(Model(Self.ownerInput(build)).placed.count, 72, "positive direction: the same content admitted shows")
    }

    func testInvalidGeometryDrawsNoDotButKeepsTheRowReachable() throws {
        // CONSTRUCTED: edited cells and axes on retained rows.
        let build = Self.retained()
        let brennan = Self.index(build, "Michael Brennan")
        let row = build.rows[brennan]
        let cases: [(String, GolfClosingRoundRow10868)] = [
            ("bin is not the round", Self.edit(row, cell: GolfClosingRoundCell10868(bin: -2, stack: 30))),
            ("bin off the axis", Self.edit(row, round: .reported(relative: -9, text: "-9", detail: nil),
                                           cell: GolfClosingRoundCell10868(bin: -9, stack: 0))),
            ("negative stack", Self.edit(row, cell: GolfClosingRoundCell10868(bin: -3, stack: -1))),
            ("stack at the ceiling", Self.edit(row, cell: GolfClosingRoundCell10868(bin: -3, stack: build.axis.stackCeiling))),
            ("not-a-number bin", Self.edit(row, round: .reported(relative: .nan, text: "-3", detail: nil),
                                           cell: GolfClosingRoundCell10868(bin: .nan, stack: 0))),
            ("unreported round", Self.edit(row, round: .unreported(words: "Round not reported"))),
            ("no cell", Self.edit(row, cell: .some(nil))),
        ]
        for (label, edited) in cases {
            var changed = build
            changed.rows[brennan] = edited
            let model = Self.ownerModel(changed)
            XCTAssertEqual(model.placed.count, 71, label)
            XCTAssertFalse(model.placed.contains { $0.rowID == row.id }, label)
            let reachable = try XCTUnwrap(model.row(row.id), label)
            XCTAssertEqual(model.chooseAction(reachable.id), reachable.id, label)
            XCTAssertTrue(model.selectedSummary(full: false).contains("This round is not placed on the plot"), label)
            XCTAssertEqual(model.window.first(where: { $0.id == row.id })?.row, reachable, label)
        }

        var clash = build
        let other = try XCTUnwrap(build.rows.firstIndex(where: { $0.cell?.bin == -3 && $0.id != row.id }))
        clash.rows[other] = Self.edit(build.rows[other], cell: GolfClosingRoundCell10868(bin: -3, stack: 0))
        let clashModel = Self.ownerModel(clash)
        XCTAssertEqual(clashModel.placed.count, 70, "two rows claiming one cell: neither is drawn over the other")
        XCTAssertNotNil(clashModel.row(build.rows[other].id))

        func axis(lower: Double = -7, upper: Double = 5, ceiling: Int? = nil) -> GolfClosingRoundAxis10868 {
            GolfClosingRoundAxis10868(lower: lower, upper: upper, stackCeiling: ceiling ?? build.axis.stackCeiling,
                                      ticks: build.axis.ticks, underWords: build.axis.underWords,
                                      overWords: build.axis.overWords, words: build.axis.words)
        }
        let axes: [(String, GolfClosingRoundAxis10868)] = [
            ("reversed", axis(lower: 5, upper: -7)),
            ("zero off the axis", axis(lower: 1, upper: 5)),
            ("no room", axis(ceiling: 0)),
            ("not finite", axis(lower: -.infinity)),
        ]
        XCTAssertTrue(axis().isValid, "positive control")
        for (label, bad) in axes {
            var changed = build
            changed.axis = bad
            let model = Self.ownerModel(changed)
            XCTAssertFalse(bad.isValid, label)
            XCTAssertTrue(model.placed.isEmpty, label)
            XCTAssertNil(Geometry.height(bad), label)
            XCTAssertTrue(Geometry.ticks(bad).isEmpty, label)
            XCTAssertNil(Geometry.zeroX(bad, width: 343), label)
            XCTAssertEqual(model.window.compactMap { $0.row }.count, 12, "rows stay reachable: \(label)")
            XCTAssertNotNil(model.chooseAction("dg:29197"), label)
        }

        let model = Self.ownerModel(build)
        XCTAssertTrue(Geometry.dots(model.placed, selected: nil, in: CGSize(width: 10, height: 400)).isEmpty,
                      "narrower than both insets: no dot rather than a clipped one")
        XCTAssertTrue(Geometry.dots(model.placed, selected: nil, in: CGSize(width: 343, height: 5)).isEmpty,
                      "too short for a whole dot")
    }
    // MARK: Geometry, holds and exact callbacks

    func testGeometryPlacesZeroTicksAndDotsOnOneSharedStrip() throws {
        let build = Self.retained()
        let axis = build.axis
        XCTAssertEqual(Geometry.fraction(-7, axis: axis), 0)
        XCTAssertEqual(Geometry.fraction(5, axis: axis), 1)
        XCTAssertEqual(try XCTUnwrap(Geometry.fraction(0, axis: axis)), 7.0 / 12.0, accuracy: 1e-12)
        XCTAssertNil(Geometry.fraction(-8, axis: axis))
        XCTAssertNil(Geometry.fraction(5.5, axis: axis))
        XCTAssertNil(Geometry.fraction(.nan, axis: axis))

        let width: CGFloat = 343
        let inset = Geometry.inset
        XCTAssertEqual(inset, FieldExpectationsGeometry10868.inset(markDiameter: Geometry.ringDiameter + Geometry.ringLine))
        let zero = try XCTUnwrap(Geometry.zeroX(axis, width: width))
        XCTAssertEqual(zero, try XCTUnwrap(FieldFinishGeometry10868.x(of: 7.0 / 12.0, width: width, inset: inset)), accuracy: 1e-9)

        let placedTicks = Geometry.ticks(axis)
        XCTAssertEqual(placedTicks.map { $0.label }, axis.ticks.map { $0.label })
        XCTAssertEqual(placedTicks.first?.fraction, 0)
        XCTAssertEqual(placedTicks.last?.fraction, 1)
        let zeroTick = try XCTUnwrap(placedTicks.first(where: { $0.label == "E" }))
        XCTAssertEqual(zeroTick.fraction, 7.0 / 12.0, accuracy: 1e-12, "the zero tick sits on the zero line")

        let plotHeight = try XCTUnwrap(Geometry.height(axis))
        XCTAssertEqual(plotHeight, CGFloat(axis.stackCeiling - 1) * Geometry.pitch + 2 * inset)
        let model = Self.ownerModel(build)
        let drawn = Geometry.dots(model.placed, selected: model.selectedRowID, in: CGSize(width: width, height: plotHeight))
        let brennan = try XCTUnwrap(drawn.first(where: { $0.rowID == "dg:29197" }))
        XCTAssertEqual(brennan.center.x, try XCTUnwrap(FieldFinishGeometry10868.x(of: 4.0 / 12.0, width: width, inset: inset)), accuracy: 1e-9)
        XCTAssertEqual(brennan.center.y, plotHeight - inset, accuracy: 1e-9, "first in its column sits on the axis")
        XCTAssertTrue(brennan.isSelected)
        XCTAssertLessThan(brennan.center.x, zero, "an under-par round sits on the under-par side")
        let scott = try XCTUnwrap(drawn.first(where: { $0.rowID == "dg:6430" }))
        XCTAssertGreaterThan(scott.center.x, zero, "an over-par round sits on the over-par side")
        XCTAssertFalse(scott.isSelected)
        let top = try XCTUnwrap(drawn.map { $0.center.y }.min())
        XCTAssertEqual(top, inset, accuracy: 1e-9, "the owner's ceiling is exactly the tallest column, drawn whole")
        XCTAssertGreaterThan(Geometry.ringDiameter, Geometry.fieldDiameter, "the selected ring is larger than a field dot")
    }

    func testCompactActionsHoldOnceThenPassTheExactValue() {
        let build = Self.retained()
        let log = GolfClosingCallLog10868()
        let presentation = Presentation(
            input: Self.ownerInput(build),
            onOpen: { log.entries.append("open") }, onBack: { log.entries.append("back") },
            onChooser: { log.entries.append("chooser") },
            onChooseRow: { log.entries.append("row:\($0)") }, onAction: { log.entries.append("action:\($0)") },
            onInteraction: { log.entries.append("hold") })
        XCTAssertEqual(log.entries, [], "building calls nothing")
        _ = presentation.controls
        _ = presentation.wiring
        XCTAssertEqual(log.entries, [], "reading calls nothing")
        XCTAssertNil(presentation.backControl(), "the compact card has no Back")
        XCTAssertNil(presentation.chooserOpenControl(), "the compact card opens no chooser")

        for entry in presentation.model.featured { presentation.chooseControl(entry)?() }
        presentation.openControl()?()
        presentation.actionControl(build.details)?()
        XCTAssertEqual(log.entries, ["hold", "row:dg:29197", "hold", "row:dg:6430", "hold", "row:dg:16841",
                                     "hold", "open", "hold", "action:closing.details"],
                       "exactly one hold before each page action, then its exact value")

        let bare = GolfClosingCallLog10868()
        Presentation(input: Self.ownerInput(build), onOpen: { bare.entries.append("open") }).openControl()?()
        XCTAssertEqual(bare.entries, ["open"], "no hook: the exact callback alone")
    }

    func testAStreamCardUsesTheStreamActivationInsteadOfAPageHold() {
        let build = Self.retained()
        let log = GolfClosingCallLog10868()
        let presentation = Presentation(
            input: Self.ownerInput(build), activation: Self.activation(log: log),
            onOpen: { log.entries.append("open") }, onChooseRow: { log.entries.append("row:\($0)") },
            onAction: { log.entries.append("action:\($0)") }, onInteraction: { log.entries.append("page-hold") })
        presentation.chooseControl(presentation.model.featured[1])?()
        presentation.openControl()?()
        presentation.actionControl(build.details)?()
        XCTAssertEqual(log.entries, ["activate:closing-round", "row:dg:6430", "activate:closing-round", "open",
                                     "activate:closing-round", "action:closing.details"])
        XCTAssertFalse(log.entries.contains("page-hold"), "no second page hold inside the stream")

        let quiet = GolfClosingCallLog10868()
        let inert = StoryStreamCardActivation10868(
            card: StoryStreamPresentation10868.CardRef(scope: Self.fixtureScope, id: "closing-round"), intents: [], send: nil)
        let inertCard = Presentation(input: Self.ownerInput(build), activation: inert, onOpen: { quiet.entries.append("open") },
                                     onInteraction: { quiet.entries.append("page-hold") })
        inertCard.openControl()?()
        XCTAssertEqual(quiet.entries, ["open"], "an inert activation still delivers the exact action once, with no page hold")
    }

    func testFullSizeChooserAndBackCallbacksAreExact() throws {
        let build = Self.retained()
        let log = GolfClosingCallLog10868()
        let full = Presentation(
            input: Self.ownerInput(build), mode: .full, activation: Self.activation(log: log),
            onBack: { log.entries.append("back") }, onChooser: { log.entries.append("chooser") },
            onChooseRow: { log.entries.append("row:\($0)") }, onAction: { log.entries.append("action:\($0)") },
            onInteraction: { log.entries.append("hold") })
        full.backControl()?()
        full.chooserOpenControl()?()
        full.chooseControl(full.model.window[3])?()
        full.actionControl(build.window?.next)?()
        full.actionControl(build.details)?()
        XCTAssertNil(full.openControl(), "full-size content does not open itself")
        XCTAssertEqual(log.entries, ["back", "chooser", "row:\(build.rows[3].id)", "action:window.next", "action:closing.details"],
                       "exact: no hold and no stream activation in full-size content")

        let chosen = GolfClosingCallLog10868()
        var refs: [FieldChooserOriginalRef10868] = []
        var controls: [FieldChooserControl10868] = []
        let chooser = Presentation(input: Self.ownerInput(build), mode: .chooser,
                                   onBack: { chosen.entries.append("back") },
                                   onChooseOriginal: { refs.append($0) }, onChooserControl: { controls.append($0) },
                                   onInteraction: { chosen.entries.append("hold") })
        let scottRef = try XCTUnwrap(build.rows[Self.index(build, "Adam Scott")].original)
        chooser.wiring.chooseOriginal?(scottRef)
        chooser.wiring.chooserControl?(.toggleBrowse(id: "browse"))
        chooser.backControl()?()
        XCTAssertEqual(refs, [scottRef])
        XCTAssertEqual(controls, [.toggleBrowse(id: "browse")])
        XCTAssertEqual(chosen.entries, ["back"], "the chooser's callbacks and Back are exact")
        XCTAssertNil(chooser.wiring.chooseRow)
        XCTAssertNil(chooser.wiring.open)
        let resolver = FieldChooserModel10868(Self.chooserInput(build))
        XCTAssertEqual(resolver.resolve(scottRef).original?.name, "Adam Scott", "the chooser mounts the owner's own catalogue")
        XCTAssertEqual(resolver.selectedRef, build.rows[0].original)
    }

    func testWithoutCallbacksThereAreNoControlsAndOwnerActionsMustBeUniqueAndAvailable() {
        let build = Self.retained()
        for mode in [GolfClosingRoundMode10868.compact, .full, .chooser] {
            XCTAssertEqual(Presentation(input: Self.ownerInput(build), mode: mode).controls, [], "no callback, no control: \(mode)")
        }
        XCTAssertTrue(Presentation(input: Self.ownerInput(build), mode: .chooser).chooserListShown,
                      "the chooser list is still content without a callback")

        // CONSTRUCTED: owner actions that collide, are unavailable or unreadable.
        var colliding = build
        colliding.details = FieldHistoryAction10868(id: "window.next", label: "Details", spokenLabel: nil, isAvailable: true)
        let collidingModel = Self.ownerModel(colliding)
        XCTAssertNil(collidingModel.detailsAction)
        XCTAssertNil(collidingModel.nextAction, "two actions with one id: neither is drawn")
        XCTAssertFalse(Presentation(input: Self.ownerInput(colliding), mode: .full, onAction: { _ in }).controls.contains(.action("window.next")))
        var unavailable = build
        unavailable.details = FieldHistoryAction10868(id: "closing.details", label: "Details", spokenLabel: nil, isAvailable: false)
        XCTAssertNil(Self.ownerModel(unavailable).detailsAction)
        var blank = build
        blank.details = FieldHistoryAction10868(id: "closing.details", label: " ", spokenLabel: nil, isAvailable: true)
        XCTAssertNil(Self.ownerModel(blank).detailsAction)
        XCTAssertEqual(Self.ownerModel(build).detailsAction, Self.detailsAction, "positive control")

        let blankBack = GolfClosingRoundInput10868(
            phase: .final, admission: Self.ownerInput(build).admission,
            chrome: GolfClosingRoundChrome10868(backLabel: " ", backHint: nil, unavailableWords: "Unavailable"))
        XCTAssertNil(Presentation(input: blankBack, mode: .full, onBack: {}).backControl(), "a blank Back label draws no Back")
    }
    // MARK: Reach, targets and spoken words

    func testOwnerWindowsReachAllSeventyTwoRows() {
        let build = Self.retained()
        let pages = (build.rows.count + Self.windowSize - 1) / Self.windowSize
        XCTAssertEqual(pages, 6)
        var reached: [String] = []
        for page in 0..<pages {
            var paged = build
            paged.window = Self.ownerWindow(page: page, rows: build.rows)
            let log = GolfClosingCallLog10868()
            let full = Presentation(input: Self.ownerInput(paged), mode: .full,
                                    onChooseRow: { log.entries.append($0) }, onAction: { log.entries.append("action:\($0)") })
            let entries = full.model.window
            XCTAssertLessThanOrEqual(entries.count, Self.windowSize)
            for entry in entries {
                XCTAssertNotNil(entry.row, entry.id)
                full.chooseControl(entry)?()
            }
            XCTAssertEqual(log.entries, entries.map { $0.id }, "each window row is its own control with its own exact id")
            reached += log.entries
            XCTAssertEqual(full.model.previousAction != nil, page > 0, "page \(page)")
            XCTAssertEqual(full.model.nextAction != nil, page + 1 < pages, "page \(page)")
        }
        XCTAssertEqual(reached, build.rows.map { $0.id }, "all 72 rows reachable, each once, in the owner's order")
        XCTAssertEqual(Self.ownerWindow(page: 5, rows: build.rows).title, "Golfers 61–72 of 72")
    }

    func testEveryNewControlIsAtLeast44AtTheSmallestTextSize() {
        XCTAssertEqual(Geometry.target(17), 44)
        XCTAssertEqual(Geometry.target(44), 44)
        XCTAssertEqual(Geometry.target(61.5), 61.5)
        XCTAssertEqual(Geometry.target(-3), 44)
        XCTAssertEqual(Geometry.target(.nan), 44)
        XCTAssertEqual(Geometry.target(.infinity), 44)
        for size in [DynamicTypeSize.xSmall, .large, .accessibility3] {
            let fit = Self.fitted(GolfClosingRoundButton10868(title: "E", identifier: "probe", action: {}), width: 375, size: size)
            XCTAssertGreaterThanOrEqual(fit.height, 44, "\(size): the one control every local touch area uses")
        }
        let narrowest = hostForMeasurement(GolfClosingRoundButton10868(title: "E", identifier: "probe", action: {}), at: .xSmall)
            .sizeThatFits(in: CGSize(width: 0, height: CGFloat.greatestFiniteMagnitude))
        XCTAssertGreaterThanOrEqual(narrowest.width, 44, "a one-glyph control keeps a 44 pt wide target at the smallest size")
        XCTAssertGreaterThanOrEqual(narrowest.height, 44)
        let paired = Self.fitted(GolfClosingRoundButton10868(
            title: "Min Woo Lee",
            values: [GolfClosingRoundPair10868(label: "Final round", value: "-5"), GolfClosingRoundPair10868(label: "Finished", value: "T9")],
            isSelected: true, identifier: "probe", action: {}), width: 375, size: .xSmall)
        XCTAssertGreaterThanOrEqual(paired.height, 44)
    }

    func testVoiceOverSummariesCarryTheOwnersWords() throws {
        let build = Self.retained()
        let model = Self.ownerModel(build)
        let brennanWords = "Michael Brennan. Selected. Final round: -3, 3 strokes under par. Total: -16. Finished: 1"
        for words in ["Distribution of final-round scores relative to par. A blue ring marks the selected golfer.",
                      "Strokes relative to par in the final round; lower is better", "72 completed rounds", brennanWords] {
            XCTAssertTrue(model.plotSummary.contains(words), words)
        }
        XCTAssertEqual(model.selectedSummary(full: true), [
            brennanWords,
            "Before tournament: 2.6%, Oct 6, 6:08 AM PT · DataGolf-derived record",
            "Market result: Not settled in this capture",
            "Original outcome: Michael Brennan",
        ].joined(separator: ". "))
        XCTAssertFalse(model.selectedSummary(full: false).contains("Market result"), "the compact card carries no grade line")
        let lee = try XCTUnwrap(model.row("dg:16841"))
        XCTAssertEqual(model.rowSummary(lee), "Min Woo Lee. Final round: -5, 5 strokes under par. Total: -12. Finished: T9")

        // CONSTRUCTED: a result from the settlement owner on the selected original.
        var graded = build
        graded.catalogue = build.catalogue.map { record -> FieldChooserOriginal10868 in
            guard record.name == "Michael Brennan" else { return record }
            return FieldChooserOriginal10868(ref: record.ref, name: record.name, plan: record.plan, preview: record.preview,
                                             movement: record.movement, clock: record.clock,
                                             result: FieldChooserResult10868(title: "Market result", words: "Won"),
                                             browseStatus: record.browseStatus)
        }
        let gradedModel = Self.ownerModel(graded)
        let gradedRow = try XCTUnwrap(gradedModel.row("dg:29197"))
        XCTAssertEqual(gradedModel.grade(gradedRow), FieldChooserResult10868(title: "Market result", words: "Won"))
        let gradedWords = gradedModel.selectedSummary(full: true)
        XCTAssertTrue(gradedWords.contains("Market result: Won"))
        XCTAssertTrue(gradedWords.contains("Finished: 1"), "finish and contract grade stay separate lines")
        XCTAssertTrue(gradedWords.contains("Before tournament: 2.6%"), "the earlier chance is unchanged by the grade")
    }
    // MARK: Layout and source

    func testTheCardFitsPhoneWidthsAtEveryTextSize() {
        let input = Self.ownerInput(Self.retained())
        for mode in [GolfClosingRoundMode10868.compact, .full] {
            for width in [CGFloat(375), 393] {
                var heights: [DynamicTypeSize: CGFloat] = [:]
                for size in [DynamicTypeSize.large, .xxxLarge, .accessibility3] {
                    let card = Presentation(input: input, mode: mode, onOpen: {}, onBack: {}, onChooser: {},
                                            onChooseRow: { _ in }, onAction: { _ in })
                    let fit = Self.fitted(card, width: width, size: size)
                    XCTAssertLessThanOrEqual(fit.width, width + 0.5, "\(mode) \(width) \(size): no horizontal overflow")
                    XCTAssertTrue(fit.height.isFinite && fit.height > 0, "\(mode) \(width) \(size)")
                    heights[size] = fit.height
                }
                XCTAssertGreaterThan(heights[.accessibility3] ?? 0, heights[.large] ?? 0,
                                     "\(mode) \(width): larger text grows the card instead of clipping it")
            }
        }
        let withheld = GolfClosingRoundInput10868(phase: .during, admission: input.admission, chrome: Self.chrome)
        let fit = Self.fitted(Presentation(input: withheld, mode: .full, onBack: {}), width: 375, size: .accessibility3)
        XCTAssertLessThanOrEqual(fit.width, 375.5, "CONSTRUCTED phase: Back and the unavailable words fit too")
        XCTAssertGreaterThanOrEqual(fit.height, 44)
    }

    func testWideWidthsTryTheSideBySideArrangementAndAccessibilitySizesStack() {
        XCTAssertEqual(FieldEventPageModel10868.arrangements(sizeClass: .regular, accessibilitySize: false), [.sideBySide, .stacked])
        XCTAssertEqual(FieldEventPageModel10868.arrangements(sizeClass: nil, accessibilitySize: false), [.sideBySide, .stacked],
                       "a Mac window has no size class")
        XCTAssertEqual(FieldEventPageModel10868.arrangements(sizeClass: .compact, accessibilitySize: false), [.stacked])
        XCTAssertEqual(FieldEventPageModel10868.arrangements(sizeClass: .regular, accessibilitySize: true), [.stacked])
        let input = Self.ownerInput(Self.retained())
        for mode in [GolfClosingRoundMode10868.compact, .full] {
            let card = Presentation(input: input, mode: mode, onOpen: {}, onBack: {}, onChooser: {},
                                    onChooseRow: { _ in }, onAction: { _ in })
            let phone = Self.fitted(card, width: 375, size: .large)
            let wide = Self.fitted(card, width: 1024, size: .large, sizeClass: .regular)
            XCTAssertEqual(wide.width, 1024, accuracy: 0.5, "\(mode): the card widens to the iPad or Mac width")
            XCTAssertLessThan(wide.height, phone.height, "\(mode): side by side is shorter than stacked")
            let wideLarge = Self.fitted(card, width: 1024, size: .accessibility3, sizeClass: .regular)
            XCTAssertLessThanOrEqual(wideLarge.width, 1024.5, "\(mode): accessibility sizes stack within the width")
        }
    }

    func testProductSourceCarriesNoSpecimenStateOrSecondControl() throws {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Components/GolfClosingRoundPresentation10868.swift")
        let source = try String(contentsOf: url, encoding: .utf8)
        var banned = Self.retainedPlayers.map { $0.name } + Self.retainedOutcomes.map { $0.name }
        banned += Self.retainedLeaderboard.map { $0.dgID } + Self.retainedOutcomes.map { $0.id }
        banned += [Self.retainedEvent.name, Self.retainedEvent.eventKey, Self.retainedEvent.marketID,
                   Self.retainedEvent.marketName, "datagolf", "DataGolf", "quarter", "Quarter"]
        for word in banned {
            XCTAssertFalse(source.contains(word), "specimen in product source: \(word)")
        }
        for word in ["@State", "@StateObject", "@ObservedObject", "Timer", ".onAppear", ".task", ".onReceive", "withAnimation",
                     "NavigationLink", ".sheet(", "Task {"] {
            XCTAssertFalse(source.contains(word), "no local state, timer, replay, routing or subscription: \(word)")
        }
        XCTAssertEqual(source.components(separatedBy: "Button(").count - 1, 1, "every local touch area is the one control")
        XCTAssertTrue(source.contains(".frame(minWidth: target, maxWidth: .infinity, minHeight: target, alignment: .leading)"))
        XCTAssertTrue(source.contains("scaled.isFinite ? max(44, scaled) : 44"))
    }
}

// MARK: - Retained fixture types (values generated below)

struct GolfClosingRetainedPoint10868 {
    let timestamp: String
    let probability: String
    let americanOdds: String?
    let bookmaker: String
}

struct GolfClosingRetainedSeries10868 {
    let outcomeID: String
    let name: String
    let eliminated: Bool
    let eliminatedAt: String?
    let history: [GolfClosingRetainedPoint10868]
}

struct GolfClosingRetainedOutcome10868 {
    let id: String
    let name: String
    let isWinner: Bool?
    let resolutionSource: String?
}

struct GolfClosingRetainedLeader10868 {
    let name: String
    let thru: String
    let dgID: String
    let position: String
    let todayScore: String
    let totalScore: String
    let currentRound: String
}

struct GolfClosingRetainedPlayer10868 {
    let position: String
    let name: String
    let score: String
    let totalScoreRaw: String
    let today: String
    let todayRaw: String
    let thru: String
    let hole: String
    let winProb: String
    let winProbChange: String
    let positionChange: String
    let top5Prob: String?
    let top10Prob: String?
    let top20Prob: String?
    let makeCutProb: String
    let currentRound: String
}

struct GolfClosingRetainedBoundary10868 {
    let timestamp: String
    let label: String
}

struct GolfClosingRetainedEvent10868 {
    let name: String
    let eventKey: String
    let start: String
    let capturedAt: String
    let terminalTimestamp: String
    let terminalProbability: String
    let terminalAmericanOdds: String?
    let terminalBookmaker: String
    let terminalPolicy: String
    let marketID: String
    let marketName: String
    let marketSource: String
    let marketExternalID: String
    let marketStatus: String
    let outcomeCount: String
    let historyMarketID: String
    let coverageStart: String
    let coverageEnd: String
    let finalStatus: String
    let finalEventName: String
    let finalCurrentRound: String
    let finalLastUpdated: String
    let finalTour: String
    let finalPlayerCount: String
    let finalHasSnapshot: Bool
}

final class GolfClosingCallLog10868 {
    var entries: [String] = []
}

// MARK: - Retained fixture (generated)
// @@BEGIN GENERATED FIXTURE@@
// Generated by /tmp/golf-closing-fixture-gen.py from golfJourney.json
// sha256 1bdd575deb988730374dc7e52225bad45b6312671b2eab73a184dd5fa0330fa1: a lossless extraction of the consumed fields only, numbers as
// their source text. Excluded fields are not retained. Do not edit by hand.
extension GolfClosingRoundPresentation10868Tests {
    static let retainedEvent = GolfClosingRetainedEvent10868(
        name: "Baycurrent Classic",
        eventKey: "datagolf:pga:527",
        start: "2026-10-08T00:00:00+00:00",
        capturedAt: "2026-10-12T23:53:53.546490+00:00",
        terminalTimestamp: "2026-10-11T06:41:26.165769+00:00",
        terminalProbability: "1.0",
        terminalAmericanOdds: nil,
        terminalBookmaker: "consensus",
        terminalPolicy: "This frozen specimen ends the tournament journey at the first 100% record for the independently confirmed final winner. This is an observation clock, not an official finish time. Later records remain in original details.",
        marketID: "64266833",
        marketName: "Baycurrent Classic - Winner",
        marketSource: "datagolf",
        marketExternalID: "datagolf:pga:527:win",
        marketStatus: "resolved",
        outcomeCount: "155",
        historyMarketID: "64266833",
        coverageStart: "2026-10-05T01:08:38.821032+00:00",
        coverageEnd: "2026-10-11T22:08:55.891004+00:00",
        finalStatus: "completed",
        finalEventName: "Baycurrent Classic",
        finalCurrentRound: "4",
        finalLastUpdated: "2026-10-12T23:53:53.504473+00:00",
        finalTour: "pga",
        finalPlayerCount: "72",
        finalHasSnapshot: true)

    static let retainedOutcomes: [GolfClosingRetainedOutcome10868] = [
        GolfClosingRetainedOutcome10868(id: "242242520", name: "Xander Schauffele", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "242242522", name: "Wyndham Clark", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "242242527", name: "Collin Morikawa", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "242242528", name: "Justin Thomas", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "242242532", name: "Ryan Gerard", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "242242534", name: "Hideki Matsuyama", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857513", name: "Doug Ghim", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "242242535", name: "Min Woo Lee", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "242242537", name: "Adam Scott", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857514", name: "Maverick McNealy", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "242242539", name: "Jacob Bridgeman", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857512", name: "Michael Brennan", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "242242545", name: "Michael Thorbjornsen", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "242242546", name: "Sungjae Im", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "242242542", name: "Kurt Kitayama", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857515", name: "Matt Wallace", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857522", name: "Johnny Keefer", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "242242549", name: "Keegan Bradley", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857519", name: "Kevin Yu", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857517", name: "Jackson Suber", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "242242554", name: "Rickie Fowler", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "242242553", name: "Alex Smalley", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "242242555", name: "Keita Nakajima", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "242242557", name: "Ryo Hisatsune", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "242242559", name: "Keith Mitchell", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857545", name: "Steven Fisk", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857538", name: "Zach Bauchou", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857527", name: "Max Homa", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857524", name: "Kristoffer Ventura", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "242242563", name: "Jordan Spieth", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857518", name: "Jordan Smith", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "242242564", name: "Michael Kim", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857534", name: "Max Greyserman", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857520", name: "Davis Thompson", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "242242568", name: "Brian Harman", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857521", name: "Mac Meissner", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857531", name: "Kevin Roy", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857548", name: "Stephan Jaeger", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857549", name: "Lee Hodges", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857530", name: "Pierceson Coody", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857525", name: "Beau Hossler", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "242242573", name: "Ricky Castillo", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "242242578", name: "Sahith Theegala", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857533", name: "Ben Kohles", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857543", name: "Christiaan Bezuidenhout", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857540", name: "Billy Horschel", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857536", name: "Rasmus Neergaard-Petersen", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857556", name: "Taylor Moore", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857544", name: "John Parry", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857542", name: "Nick Taylor", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857550", name: "Matt McCarty", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857571", name: "Takumi Kanaya", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857562", name: "Aldrich Potgieter", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "242242596", name: "Nico Echavarria", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857551", name: "Chandler Phillips", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "242242594", name: "Taylor Pendrith", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857567", name: "Tony Finau", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857561", name: "Denny McCarthy", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857576", name: "Patrick Rodgers", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "242242598", name: "Jinichiro Kozuma", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "242242604", name: "Hiroshi Iwata", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857577", name: "Andrew Putnam", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857591", name: "David Lipsky", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "242242600", name: "Yusaku Hosono", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857574", name: "Tom Hoge", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "242242602", name: "Sang-hee Lee", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "242242609", name: "Aguri Iwasaki", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "242242613", name: "Kosuke Sunagawa", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "242242616", name: "Yoshinori Fujimoto", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "242242611", name: "Ren Yonezawa", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "242242614", name: "Tomohiro Ishizaka", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "242242618", name: "Koshin Nagasaki", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857553", name: "Patrick Fishburn", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857622", name: "Brendon Todd", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857612", name: "C.T. Pan", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857564", name: "Hayden Springer", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857566", name: "Jesper Svensson", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857582", name: "Luke Clanton", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857589", name: "Kevin Streelman", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857587", name: "Ben Silverman", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857595", name: "Adam Svensson", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857625", name: "David Lingmerth", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857559", name: "Sudarshan Yellamaraju", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857539", name: "Emiliano Grillo", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857541", name: "Mackenzie Hughes", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857554", name: "Max McGreevy", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857573", name: "John VanDerLaan", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857575", name: "Mark Hubbard", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857594", name: "Joe Highsmith", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857617", name: "Nick Dunlap", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857586", name: "Erik Van Rooyen", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857606", name: "Alejandro Tosti", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857628", name: "Zach J. Johnson", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857526", name: "Chris Kirk", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857607", name: "Dylan Wu", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857569", name: "Isaiah Salinda", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857572", name: "Chandler Blanchet", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857581", name: "Davis Chatfield", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857603", name: "Harry Higgs", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857511", name: "Ben James", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857529", name: "Harry Hall", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857532", name: "Rasmus Hojgaard", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857535", name: "Neal Shipley", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857537", name: "Zecheng Dou", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857546", name: "Matthieu Pavon", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857547", name: "William Mouw", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857552", name: "Austin Smotherman", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857565", name: "Joel Dahmen", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857570", name: "Gordon Sargent", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857579", name: "Lucas Glover", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857580", name: "Pontus Nyholm", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857583", name: "Garrick Higgo", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857584", name: "Tyler Duncan", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857592", name: "Hank Lebioda", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857593", name: "David Skinns", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857600", name: "Danny Walker", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857602", name: "Peter Malnati", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857609", name: "Rafael Campos", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857613", name: "Patton Kizzire", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857614", name: "Vince Whaley", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857615", name: "Michael Thompson", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857619", name: "Boston Bracken", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857620", name: "Christo Lamprecht", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857621", name: "Carson Lundell", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857626", name: "Rhett Rasmussen", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857629", name: "Bowen Mauss", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857599", name: "Davis Riley", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857510", name: "Jackson Koivun", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857597", name: "Aaron Wise", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857616", name: "Kensei Hirata", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857623", name: "Matt Snyder", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857598", name: "Kihei Akina", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857578", name: "A.J. Ewart", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857596", name: "Ben Martin", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857516", name: "Marco Penge", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857523", name: "Eric Cole", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857528", name: "Rico Hoey", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857555", name: "Haotong Li", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857557", name: "David Ford", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857558", name: "Trace Crowe", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857563", name: "Zac Blair", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857585", name: "Adrien Dumont De Chassart", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857588", name: "Justin Lower", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857590", name: "Paul Peterson", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857604", name: "Jimmy Stanger", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857605", name: "Brice Garnett", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857608", name: "Jeffrey Kang", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857618", name: "Marcelo Rozo", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857601", name: "Will Gordon", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857568", name: "Chad Ramey", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857610", name: "Adam Schenk", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857611", name: "Cam Davis", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857560", name: "Seamus Power", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857627", name: "Seonghyeon An", isWinner: nil, resolutionSource: nil),
        GolfClosingRetainedOutcome10868(id: "241857624", name: "Tyson Shelley", isWinner: nil, resolutionSource: nil),
    ]

    static let retainedSeries: [GolfClosingRetainedSeries10868] = [
        GolfClosingRetainedSeries10868(outcomeID: "241857512", name: "Michael Brennan", eliminated: false, eliminatedAt: nil, history: [
            GolfClosingRetainedPoint10868(timestamp: "2026-10-05T01:08:38.821032+00:00", probability: "0.043067", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-05T17:39:14.507306+00:00", probability: "0.026167", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-06T13:08:40.644152+00:00", probability: "0.026017", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:02:03.231914+00:00", probability: "0.024326", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:11:13.058928+00:00", probability: "0.026065", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:16:55.542752+00:00", probability: "0.025622", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:23:03.133505+00:00", probability: "0.014292", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:27:33.145591+00:00", probability: "0.015469", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:32:03.148937+00:00", probability: "0.014907", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:36:33.267676+00:00", probability: "0.015422", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:42:33.349212+00:00", probability: "0.015924", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:47:03.467275+00:00", probability: "0.015264", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:56:03.237230+00:00", probability: "0.01351", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:01:38.226778+00:00", probability: "0.013155", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:06:08.309734+00:00", probability: "0.013972", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:12:08.303481+00:00", probability: "0.014164", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:16:30.062412+00:00", probability: "0.021297", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:21:08.558032+00:00", probability: "0.020149", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:27:08.639061+00:00", probability: "0.017398", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:31:26.916892+00:00", probability: "0.018913", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:36:08.458334+00:00", probability: "0.019577", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:42:08.462936+00:00", probability: "0.018772", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:46:26.904828+00:00", probability: "0.018064", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:51:08.591737+00:00", probability: "0.015852", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:57:08.492012+00:00", probability: "0.016457", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:01:32.422514+00:00", probability: "0.017605", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:06:08.863154+00:00", probability: "0.017295", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:12:08.442006+00:00", probability: "0.017733", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:16:33.390446+00:00", probability: "0.017894", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:21:08.578066+00:00", probability: "0.025937", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:27:08.700847+00:00", probability: "0.026399", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:36:13.310618+00:00", probability: "0.027463", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:46:29.234103+00:00", probability: "0.025836", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:51:08.598563+00:00", probability: "0.028484", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:57:08.575077+00:00", probability: "0.035296", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:01:38.486948+00:00", probability: "0.036006", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:07:38.415236+00:00", probability: "0.036872", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:12:08.483856+00:00", probability: "0.035702", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:16:38.372037+00:00", probability: "0.033618", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:21:08.495213+00:00", probability: "0.035061", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:27:08.684216+00:00", probability: "0.035695", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:31:38.545519+00:00", probability: "0.033726", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:36:08.436708+00:00", probability: "0.032565", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:42:08.398714+00:00", probability: "0.024206", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:46:38.504366+00:00", probability: "0.027172", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:51:08.444107+00:00", probability: "0.025616", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:57:08.415687+00:00", probability: "0.023154", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:01:38.448606+00:00", probability: "0.021505", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:06:08.459731+00:00", probability: "0.024229", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:12:08.572694+00:00", probability: "0.025786", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:16:38.638257+00:00", probability: "0.026243", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:21:08.445056+00:00", probability: "0.029748", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:27:08.423388+00:00", probability: "0.02785", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:31:38.695212+00:00", probability: "0.030076", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:36:08.476578+00:00", probability: "0.025378", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:42:08.515784+00:00", probability: "0.024745", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:46:38.487589+00:00", probability: "0.023758", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:51:09.005838+00:00", probability: "0.024747", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:57:08.971709+00:00", probability: "0.02152", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:06:09.189943+00:00", probability: "0.018676", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:12:09.189349+00:00", probability: "0.019196", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:16:39.126639+00:00", probability: "0.019371", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:21:09.103878+00:00", probability: "0.01897", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:27:09.192337+00:00", probability: "0.017318", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:31:39.251792+00:00", probability: "0.019122", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:36:09.226450+00:00", probability: "0.01898", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:42:09.098398+00:00", probability: "0.019235", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:46:39.390867+00:00", probability: "0.019022", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:51:09.148688+00:00", probability: "0.020022", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:57:09.366348+00:00", probability: "0.016974", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:01:30.800138+00:00", probability: "0.019823", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:06:01.132593+00:00", probability: "0.018587", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:12:01.029217+00:00", probability: "0.018815", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:16:30.978149+00:00", probability: "0.020218", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:22:31.080453+00:00", probability: "0.019735", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:27:01.043399+00:00", probability: "0.019431", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:31:30.973790+00:00", probability: "0.020688", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:37:31.205466+00:00", probability: "0.020526", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:42:01.216854+00:00", probability: "0.019168", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:46:31.004456+00:00", probability: "0.020802", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:51:00.993924+00:00", probability: "0.020509", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:57:01.285974+00:00", probability: "0.019481", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T07:01:31.228243+00:00", probability: "0.019221", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T07:07:31.021816+00:00", probability: "0.018817", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:01:54.271593+00:00", probability: "0.019567", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:06:24.569832+00:00", probability: "0.020507", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:11:16.020101+00:00", probability: "0.019935", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:16:54.121527+00:00", probability: "0.018983", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:21:24.361544+00:00", probability: "0.020187", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:27:24.299799+00:00", probability: "0.021141", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:31:54.432306+00:00", probability: "0.019021", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:36:24.206129+00:00", probability: "0.020662", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:41:07.477710+00:00", probability: "0.019858", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:51:24.151362+00:00", probability: "0.018297", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:57:24.059847+00:00", probability: "0.020071", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:01:54.411616+00:00", probability: "0.020958", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:06:24.117663+00:00", probability: "0.018327", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:11:05.714663+00:00", probability: "0.021633", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:16:52.306605+00:00", probability: "0.021518", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:21:24.221027+00:00", probability: "0.020433", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:27:24.425662+00:00", probability: "0.020939", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:31:54.571872+00:00", probability: "0.020079", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:36:24.532871+00:00", probability: "0.019258", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:42:24.709592+00:00", probability: "0.019686", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:46:55.026284+00:00", probability: "0.009928", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:51:24.654444+00:00", probability: "0.015098", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:57:24.715348+00:00", probability: "0.016251", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:01:59.282505+00:00", probability: "0.016105", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:06:24.836570+00:00", probability: "0.017211", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:11:11.909513+00:00", probability: "0.017338", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:16:57.222706+00:00", probability: "0.020614", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:21:24.867456+00:00", probability: "0.018947", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:27:24.676035+00:00", probability: "0.02188", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:31:55.452236+00:00", probability: "0.016831", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:36:24.689467+00:00", probability: "0.016593", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:41:20.080252+00:00", probability: "0.017069", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:46:48.365847+00:00", probability: "0.015992", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:51:24.713585+00:00", probability: "0.031423", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:57:24.801333+00:00", probability: "0.031209", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:01:54.854394+00:00", probability: "0.028342", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:06:24.928070+00:00", probability: "0.030343", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:11:12.860871+00:00", probability: "0.02643", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:16:53.653676+00:00", probability: "0.027183", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:21:25.008971+00:00", probability: "0.02494", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:27:24.817660+00:00", probability: "0.024563", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:31:54.901607+00:00", probability: "0.028417", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:36:24.817000+00:00", probability: "0.022007", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:41:13.090598+00:00", probability: "0.024576", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:46:53.727811+00:00", probability: "0.023996", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:51:24.732031+00:00", probability: "0.024593", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:57:24.797035+00:00", probability: "0.024317", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:01:54.833885+00:00", probability: "0.023501", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:06:24.758254+00:00", probability: "0.021421", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:11:15.242501+00:00", probability: "0.022897", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:16:54.757109+00:00", probability: "0.039376", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:21:24.742441+00:00", probability: "0.042106", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:27:24.789808+00:00", probability: "0.040647", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:31:54.822029+00:00", probability: "0.044382", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:36:24.971616+00:00", probability: "0.067809", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:41:09.040738+00:00", probability: "0.070929", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:46:49.098542+00:00", probability: "0.068298", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:51:24.875685+00:00", probability: "0.090157", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:57:24.779033+00:00", probability: "0.100494", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:01:54.933191+00:00", probability: "0.095096", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:06:25.123480+00:00", probability: "0.095574", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:12:24.939797+00:00", probability: "0.091321", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:16:54.854142+00:00", probability: "0.092997", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:21:24.981246+00:00", probability: "0.094494", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:27:25.121923+00:00", probability: "0.084846", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:32:05.421227+00:00", probability: "0.085788", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:36:24.993990+00:00", probability: "0.084573", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:42:24.976809+00:00", probability: "0.085246", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:46:54.961700+00:00", probability: "0.090809", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:51:24.941083+00:00", probability: "0.081919", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:57:25.853387+00:00", probability: "0.083479", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:01:55.007660+00:00", probability: "0.078887", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:06:25.056796+00:00", probability: "0.078658", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:12:24.917957+00:00", probability: "0.076175", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:16:55.057037+00:00", probability: "0.079064", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:21:25.519889+00:00", probability: "0.078511", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:27:25.086697+00:00", probability: "0.033885", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:31:54.980387+00:00", probability: "0.032847", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:36:24.977474+00:00", probability: "0.034472", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:42:43.024481+00:00", probability: "0.032713", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:46:54.836301+00:00", probability: "0.032874", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:51:25.119887+00:00", probability: "0.031789", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T07:01:55.134023+00:00", probability: "0.033262", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T07:06:24.990357+00:00", probability: "0.033478", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T07:12:24.978448+00:00", probability: "0.032282", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T11:03:25.396420+00:00", probability: "0.032022", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:01:32.121700+00:00", probability: "0.033625", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:07:32.296237+00:00", probability: "0.030661", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:12:02.146122+00:00", probability: "0.032517", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:16:38.233711+00:00", probability: "0.033268", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:22:36.878874+00:00", probability: "0.032561", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:27:02.254196+00:00", probability: "0.03131", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:31:32.393467+00:00", probability: "0.032338", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:37:36.325422+00:00", probability: "0.031946", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:42:02.397711+00:00", probability: "0.02962", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:46:32.201718+00:00", probability: "0.03186", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:52:32.230383+00:00", probability: "0.030473", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:57:02.292294+00:00", probability: "0.030924", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:01:44.967297+00:00", probability: "0.032088", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:07:40.922682+00:00", probability: "0.031637", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:11:31.557654+00:00", probability: "0.031166", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:16:32.368568+00:00", probability: "0.032676", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:22:32.457644+00:00", probability: "0.02872", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:27:02.328365+00:00", probability: "0.029426", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:31:30.766239+00:00", probability: "0.028067", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:37:29.853954+00:00", probability: "0.026812", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:42:03.894288+00:00", probability: "0.024681", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:46:32.499339+00:00", probability: "0.020435", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:52:30.103758+00:00", probability: "0.022602", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:57:02.295932+00:00", probability: "0.024775", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:01:32.388551+00:00", probability: "0.024336", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:07:30.589268+00:00", probability: "0.022995", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:12:02.539866+00:00", probability: "0.025624", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:16:32.509056+00:00", probability: "0.026254", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:22:29.118118+00:00", probability: "0.017763", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:31:36.176169+00:00", probability: "0.016318", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:41:10.306614+00:00", probability: "0.01573", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:46:29.373474+00:00", probability: "0.013814", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:52:25.547135+00:00", probability: "0.013275", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:57:02.515905+00:00", probability: "0.01301", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:01:32.475241+00:00", probability: "0.01272", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:07:27.584475+00:00", probability: "0.012513", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:12:09.791890+00:00", probability: "0.015715", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:16:32.467564+00:00", probability: "0.028462", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:22:28.900262+00:00", probability: "0.031867", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:27:02.467693+00:00", probability: "0.030362", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:31:32.355628+00:00", probability: "0.028533", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:37:24.925694+00:00", probability: "0.024332", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:42:02.599933+00:00", probability: "0.02315", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:46:32.528698+00:00", probability: "0.024348", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:52:32.323694+00:00", probability: "0.025766", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:57:02.721177+00:00", probability: "0.049227", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:01:32.667681+00:00", probability: "0.049619", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:07:32.604608+00:00", probability: "0.048805", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:12:02.392117+00:00", probability: "0.04674", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:16:32.504599+00:00", probability: "0.045167", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:22:29.559191+00:00", probability: "0.02374", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:27:02.372895+00:00", probability: "0.023854", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:31:32.369451+00:00", probability: "0.023337", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:37:32.480772+00:00", probability: "0.034495", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:42:02.586740+00:00", probability: "0.026826", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:46:32.643579+00:00", probability: "0.026164", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:57:02.421912+00:00", probability: "0.039714", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:01:29.696997+00:00", probability: "0.039231", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:07:35.495038+00:00", probability: "0.038718", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:12:29.682303+00:00", probability: "0.039912", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:16:32.524509+00:00", probability: "0.034392", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:22:32.710013+00:00", probability: "0.062316", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:27:02.718901+00:00", probability: "0.060441", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:31:32.787975+00:00", probability: "0.051189", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:37:32.795010+00:00", probability: "0.05239", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:42:02.797854+00:00", probability: "0.065375", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:46:35.986461+00:00", probability: "0.06609", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:52:32.606932+00:00", probability: "0.065073", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:57:02.608225+00:00", probability: "0.068153", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:01:32.642953+00:00", probability: "0.068377", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:07:32.662386+00:00", probability: "0.110941", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:12:02.573288+00:00", probability: "0.111349", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:16:33.417463+00:00", probability: "0.122032", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:22:32.896568+00:00", probability: "0.134204", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:27:02.942302+00:00", probability: "0.152409", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:31:32.642402+00:00", probability: "0.165546", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:37:32.753311+00:00", probability: "0.158014", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:41:27.690470+00:00", probability: "0.164414", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:46:46.608343+00:00", probability: "0.158622", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:52:32.921891+00:00", probability: "0.16228", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:57:03.118947+00:00", probability: "0.16165", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T07:01:33.168803+00:00", probability: "0.16103", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T07:07:32.955805+00:00", probability: "0.161659", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T11:22:35.155437+00:00", probability: "0.162848", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:02:37.532470+00:00", probability: "0.161117", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:07:07.544047+00:00", probability: "0.16231", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:12:00.122315+00:00", probability: "0.160562", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:18:14.003636+00:00", probability: "0.16009", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:21:55.871409+00:00", probability: "0.162364", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:27:46.592637+00:00", probability: "0.16203", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:32:25.882164+00:00", probability: "0.161347", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:36:48.896569+00:00", probability: "0.162033", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:42:03.732719+00:00", probability: "0.16111", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:47:42.984192+00:00", probability: "0.159715", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:51:54.681637+00:00", probability: "0.161742", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:56:25.710971+00:00", probability: "0.159316", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:02:25.829089+00:00", probability: "0.160828", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:06:47.216580+00:00", probability: "0.159677", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:11:25.894787+00:00", probability: "0.158856", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:17:25.996026+00:00", probability: "0.166451", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:21:51.113011+00:00", probability: "0.165099", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:27:55.889037+00:00", probability: "0.164868", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:32:25.929155+00:00", probability: "0.192953", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:36:55.765217+00:00", probability: "0.185964", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:41:50.635611+00:00", probability: "0.160633", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:47:26.043890+00:00", probability: "0.164559", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:51:55.909934+00:00", probability: "0.171994", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:56:18.272058+00:00", probability: "0.164446", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:02:25.797469+00:00", probability: "0.176499", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:06:49.546752+00:00", probability: "0.170413", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:11:25.914867+00:00", probability: "0.168429", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:17:26.184322+00:00", probability: "0.167284", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:21:46.781176+00:00", probability: "0.157481", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:27:55.905318+00:00", probability: "0.146401", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:36:56.174519+00:00", probability: "0.151558", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:41:27.839983+00:00", probability: "0.119334", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:47:26.204894+00:00", probability: "0.119814", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:51:48.376763+00:00", probability: "0.122406", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:56:25.933285+00:00", probability: "0.167158", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:02:26.039667+00:00", probability: "0.166147", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:06:49.491181+00:00", probability: "0.165353", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:11:38.956586+00:00", probability: "0.126804", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:17:26.084407+00:00", probability: "0.140962", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:21:48.518176+00:00", probability: "0.14379", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:27:57.815530+00:00", probability: "0.137681", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:32:25.820139+00:00", probability: "0.176915", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:36:56.232276+00:00", probability: "0.179586", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:41:25.890612+00:00", probability: "0.158702", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:47:26.160310+00:00", probability: "0.166027", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:51:50.533672+00:00", probability: "0.162545", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:56:26.064918+00:00", probability: "0.138153", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:02:26.587145+00:00", probability: "0.127325", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:06:56.215374+00:00", probability: "0.126113", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:11:37.607125+00:00", probability: "0.129158", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:17:26.043707+00:00", probability: "0.044956", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:21:56.168662+00:00", probability: "0.054213", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:27:55.803030+00:00", probability: "0.055791", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:32:25.858478+00:00", probability: "0.089611", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:36:56.195550+00:00", probability: "0.213213", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:41:25.968157+00:00", probability: "0.224169", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:47:26.137402+00:00", probability: "0.22529", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:51:49.540257+00:00", probability: "0.2057", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:56:26.068260+00:00", probability: "0.427755", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:02:25.929267+00:00", probability: "0.432251", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:06:48.547245+00:00", probability: "0.499296", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:11:25.974142+00:00", probability: "0.425359", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:17:25.818931+00:00", probability: "0.443319", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:21:56.090554+00:00", probability: "0.467451", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:27:50.421885+00:00", probability: "0.507311", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:32:25.965758+00:00", probability: "0.500797", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:36:55.848422+00:00", probability: "0.559045", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:41:26.109476+00:00", probability: "0.54438", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:47:26.024631+00:00", probability: "0.500976", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:51:55.997823+00:00", probability: "0.482769", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:56:25.840963+00:00", probability: "0.569662", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T06:02:25.916250+00:00", probability: "0.634128", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T06:06:55.965994+00:00", probability: "0.699176", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T06:11:34.934252+00:00", probability: "0.692617", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T06:17:26.152308+00:00", probability: "0.695028", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T06:21:56.159202+00:00", probability: "0.672089", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T06:27:55.986139+00:00", probability: "0.739941", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T06:32:25.936365+00:00", probability: "0.746772", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T06:36:56.060523+00:00", probability: "0.74375", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T06:41:26.165769+00:00", probability: "1.0", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T22:08:55.891004+00:00", probability: "0.026017", americanOdds: nil, bookmaker: "consensus"),
        ]),
        GolfClosingRetainedSeries10868(outcomeID: "241857514", name: "Maverick McNealy", eliminated: false, eliminatedAt: nil, history: [
            GolfClosingRetainedPoint10868(timestamp: "2026-10-05T01:08:38.821032+00:00", probability: "0.037783", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-05T17:39:14.507306+00:00", probability: "0.031467", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-06T13:08:40.644152+00:00", probability: "0.031583", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:02:03.231914+00:00", probability: "0.030758", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:06:33.172825+00:00", probability: "0.030312", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:11:13.058928+00:00", probability: "0.031597", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:16:55.542752+00:00", probability: "0.031242", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:23:03.133505+00:00", probability: "0.031862", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:27:33.145591+00:00", probability: "0.030378", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:36:33.267676+00:00", probability: "0.027848", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:42:33.349212+00:00", probability: "0.028519", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:47:03.467275+00:00", probability: "0.027329", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:51:33.222200+00:00", probability: "0.027769", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:56:03.237230+00:00", probability: "0.024753", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:01:38.226778+00:00", probability: "0.025035", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:06:08.309734+00:00", probability: "0.022899", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:12:08.303481+00:00", probability: "0.024869", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:16:30.062412+00:00", probability: "0.023289", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:21:08.558032+00:00", probability: "0.02834", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:27:08.639061+00:00", probability: "0.027043", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:31:26.916892+00:00", probability: "0.024415", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:42:08.462936+00:00", probability: "0.034876", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:46:26.904828+00:00", probability: "0.036241", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:51:08.591737+00:00", probability: "0.03497", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:57:08.492012+00:00", probability: "0.036344", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:01:32.422514+00:00", probability: "0.037729", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:06:08.863154+00:00", probability: "0.038531", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:12:08.442006+00:00", probability: "0.039801", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:16:33.390446+00:00", probability: "0.038317", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:21:08.578066+00:00", probability: "0.037431", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:27:08.700847+00:00", probability: "0.021481", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:31:38.648207+00:00", probability: "0.01936", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:36:13.310618+00:00", probability: "0.020744", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:42:08.507576+00:00", probability: "0.019358", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:46:29.234103+00:00", probability: "0.012041", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:51:08.598563+00:00", probability: "0.011718", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:57:08.575077+00:00", probability: "0.011557", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:01:38.486948+00:00", probability: "0.009155", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:07:38.415236+00:00", probability: "0.00944", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:12:08.483856+00:00", probability: "0.009234", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:16:38.372037+00:00", probability: "0.010846", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:21:08.495213+00:00", probability: "0.010342", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:27:08.684216+00:00", probability: "0.011547", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:31:38.545519+00:00", probability: "0.010161", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:42:08.398714+00:00", probability: "0.0105", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:46:38.504366+00:00", probability: "0.011449", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:51:08.444107+00:00", probability: "0.01124", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:57:08.415687+00:00", probability: "0.011061", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:01:38.448606+00:00", probability: "0.009933", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:06:08.459731+00:00", probability: "0.010297", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:12:08.572694+00:00", probability: "0.010928", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:21:08.445056+00:00", probability: "0.011469", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:27:08.423388+00:00", probability: "0.011243", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:31:38.695212+00:00", probability: "0.00866", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:36:08.476578+00:00", probability: "0.007724", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:42:08.515784+00:00", probability: "0.009091", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:46:38.487589+00:00", probability: "0.00858", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:51:09.005838+00:00", probability: "0.002161", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:57:08.971709+00:00", probability: "0.002504", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:01:39.221294+00:00", probability: "0.002702", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:06:09.189943+00:00", probability: "0.003559", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:12:09.189349+00:00", probability: "0.003695", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:21:09.103878+00:00", probability: "0.004436", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:27:09.192337+00:00", probability: "0.001982", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:31:39.251792+00:00", probability: "0.001838", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:36:09.226450+00:00", probability: "0.001638", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:42:09.098398+00:00", probability: "0.002018", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:46:39.390867+00:00", probability: "0.001918", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:57:09.366348+00:00", probability: "0.001798", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:01:30.800138+00:00", probability: "0.001899", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:06:01.132593+00:00", probability: "0.002118", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:12:01.029217+00:00", probability: "0.001923", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:16:30.978149+00:00", probability: "0.001738", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:22:31.080453+00:00", probability: "0.001897", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:27:01.043399+00:00", probability: "0.00174", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:31:30.973790+00:00", probability: "0.001917", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:37:31.205466+00:00", probability: "0.002121", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:46:31.004456+00:00", probability: "0.001721", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T07:01:31.228243+00:00", probability: "0.001919", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:01:54.271593+00:00", probability: "0.001237", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:06:24.569832+00:00", probability: "0.002079", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:31:54.432306+00:00", probability: "0.001918", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:36:24.206129+00:00", probability: "0.002441", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:41:07.477710+00:00", probability: "0.002298", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:46:54.210856+00:00", probability: "0.002039", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:51:24.151362+00:00", probability: "0.001898", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:57:24.059847+00:00", probability: "0.00154", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:01:54.411616+00:00", probability: "0.002101", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:06:24.117663+00:00", probability: "0.001501", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:11:05.714663+00:00", probability: "0.002419", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:16:52.306605+00:00", probability: "0.002658", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:21:24.221027+00:00", probability: "0.001938", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:27:24.425662+00:00", probability: "0.002117", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:31:54.571872+00:00", probability: "0.002341", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:36:24.532871+00:00", probability: "0.002559", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:42:24.709592+00:00", probability: "0.002174", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:46:55.026284+00:00", probability: "0.001881", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:51:24.654444+00:00", probability: "0.002296", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:57:24.715348+00:00", probability: "0.002006", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:01:59.282505+00:00", probability: "0.002601", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:06:24.836570+00:00", probability: "0.001281", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:16:57.222706+00:00", probability: "0.001097", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:21:24.867456+00:00", probability: "0.00094", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:27:24.676035+00:00", probability: "0.001159", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:36:24.689467+00:00", probability: "0.000701", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:41:20.080252+00:00", probability: "0.000859", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:46:48.365847+00:00", probability: "0.000696", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:51:24.713585+00:00", probability: "0.000899", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:01:54.854394+00:00", probability: "0.001159", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:06:24.928070+00:00", probability: "0.001759", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:11:12.860871+00:00", probability: "0.000399", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:16:53.653676+00:00", probability: "0.00058", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:27:24.817660+00:00", probability: "0.0011", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:31:54.901607+00:00", probability: "0.000399", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:41:13.090598+00:00", probability: "0.000159", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:01:54.833885+00:00", probability: "4e-05", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:11:15.242501+00:00", probability: "0.000199", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:16:54.757109+00:00", probability: "3.9e-05", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:46:49.098542+00:00", probability: "0.000199", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:51:24.875685+00:00", probability: "2.2e-05", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:27:25.121923+00:00", probability: "0.00014", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:36:24.993990+00:00", probability: "3.9e-05", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:46:54.961700+00:00", probability: "0.00024", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:57:25.853387+00:00", probability: "0.0001", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:01:55.007660+00:00", probability: "0.0", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T22:08:55.891004+00:00", probability: "0.031583", americanOdds: nil, bookmaker: "consensus"),
        ]),
        GolfClosingRetainedSeries10868(outcomeID: "241857513", name: "Doug Ghim", eliminated: false, eliminatedAt: nil, history: [
            GolfClosingRetainedPoint10868(timestamp: "2026-10-05T01:08:38.821032+00:00", probability: "0.037983", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-05T17:39:14.507306+00:00", probability: "0.0399", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-06T13:08:40.644152+00:00", probability: "0.04045", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:02:03.231914+00:00", probability: "0.040895", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:06:33.172825+00:00", probability: "0.039664", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:11:13.058928+00:00", probability: "0.04034", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:23:03.133505+00:00", probability: "0.041314", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:27:33.145591+00:00", probability: "0.04011", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:32:03.148937+00:00", probability: "0.042237", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:36:33.267676+00:00", probability: "0.040761", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:42:33.349212+00:00", probability: "0.042776", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:47:03.467275+00:00", probability: "0.040059", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:51:33.222200+00:00", probability: "0.039133", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:56:03.237230+00:00", probability: "0.038189", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:01:38.226778+00:00", probability: "0.038663", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:06:08.309734+00:00", probability: "0.039916", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:12:08.303481+00:00", probability: "0.038097", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:16:30.062412+00:00", probability: "0.04059", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:21:08.558032+00:00", probability: "0.037916", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:27:08.639061+00:00", probability: "0.03759", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:31:26.916892+00:00", probability: "0.036939", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:36:08.458334+00:00", probability: "0.035695", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:42:08.462936+00:00", probability: "0.03544", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:46:26.904828+00:00", probability: "0.037149", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:51:08.591737+00:00", probability: "0.034674", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:57:08.492012+00:00", probability: "0.034926", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:01:32.422514+00:00", probability: "0.036262", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:06:08.863154+00:00", probability: "0.034157", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:12:08.442006+00:00", probability: "0.033844", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:16:33.390446+00:00", probability: "0.032978", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:21:08.578066+00:00", probability: "0.044308", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:27:08.700847+00:00", probability: "0.046166", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:31:38.648207+00:00", probability: "0.044962", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:36:13.310618+00:00", probability: "0.045232", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:42:08.507576+00:00", probability: "0.04408", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:46:29.234103+00:00", probability: "0.043031", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:51:08.598563+00:00", probability: "0.044776", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:57:08.575077+00:00", probability: "0.046112", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:01:38.486948+00:00", probability: "0.046942", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:07:38.415236+00:00", probability: "0.047891", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:12:08.483856+00:00", probability: "0.046014", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:16:38.372037+00:00", probability: "0.046287", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:21:08.495213+00:00", probability: "0.046129", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:27:08.684216+00:00", probability: "0.045266", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:31:38.545519+00:00", probability: "0.03177", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:36:08.436708+00:00", probability: "0.031138", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:42:08.398714+00:00", probability: "0.011483", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:46:38.504366+00:00", probability: "0.011185", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:51:08.444107+00:00", probability: "0.012448", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:57:08.415687+00:00", probability: "0.01369", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:01:38.448606+00:00", probability: "0.00708", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:06:08.459731+00:00", probability: "0.006658", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:12:08.572694+00:00", probability: "0.006816", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:16:38.638257+00:00", probability: "0.01099", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:21:08.445056+00:00", probability: "0.011182", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:27:08.423388+00:00", probability: "0.010398", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:36:08.476578+00:00", probability: "0.018108", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:42:08.515784+00:00", probability: "0.017694", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:46:38.487589+00:00", probability: "0.017496", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:51:09.005838+00:00", probability: "0.016075", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:57:08.971709+00:00", probability: "0.018508", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:01:39.221294+00:00", probability: "0.011129", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:06:09.189943+00:00", probability: "0.008743", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:12:09.189349+00:00", probability: "0.00802", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:16:39.126639+00:00", probability: "0.004909", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:21:09.103878+00:00", probability: "0.005088", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:27:09.192337+00:00", probability: "0.005471", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:31:39.251792+00:00", probability: "0.007657", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:36:09.226450+00:00", probability: "0.007133", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:42:09.098398+00:00", probability: "0.007537", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:46:39.390867+00:00", probability: "0.008234", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:51:09.148688+00:00", probability: "0.007554", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:57:09.366348+00:00", probability: "0.007942", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:01:30.800138+00:00", probability: "0.008417", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:06:01.132593+00:00", probability: "0.00729", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:12:01.029217+00:00", probability: "0.01171", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:16:30.978149+00:00", probability: "0.010586", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:22:31.080453+00:00", probability: "0.012314", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:27:01.043399+00:00", probability: "0.00913", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:31:30.973790+00:00", probability: "0.011654", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:42:01.216854+00:00", probability: "0.011542", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:46:31.004456+00:00", probability: "0.010906", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:51:00.993924+00:00", probability: "0.009748", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:57:01.285974+00:00", probability: "0.010146", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T07:01:31.228243+00:00", probability: "0.010842", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T07:07:31.021816+00:00", probability: "0.018944", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:01:54.271593+00:00", probability: "0.019466", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:11:16.020101+00:00", probability: "0.019351", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:16:54.121527+00:00", probability: "0.020604", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:21:24.361544+00:00", probability: "0.019588", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:27:24.299799+00:00", probability: "0.020078", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:31:54.432306+00:00", probability: "0.020996", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:36:24.206129+00:00", probability: "0.019186", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:41:07.477710+00:00", probability: "0.018919", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:46:54.210856+00:00", probability: "0.021764", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:51:24.151362+00:00", probability: "0.019389", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:57:24.059847+00:00", probability: "0.02036", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:01:54.411616+00:00", probability: "0.010914", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:06:24.117663+00:00", probability: "0.009673", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:11:05.714663+00:00", probability: "0.010765", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:16:52.306605+00:00", probability: "0.010287", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:27:24.425662+00:00", probability: "0.010393", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:31:54.571872+00:00", probability: "0.011575", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:36:24.532871+00:00", probability: "0.011823", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:42:24.709592+00:00", probability: "0.010753", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:46:55.026284+00:00", probability: "0.009965", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:51:24.654444+00:00", probability: "0.014538", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:57:24.715348+00:00", probability: "0.015149", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:01:59.282505+00:00", probability: "0.014474", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:06:24.836570+00:00", probability: "0.01674", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:11:11.909513+00:00", probability: "0.016962", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:16:57.222706+00:00", probability: "0.01788", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:21:24.867456+00:00", probability: "0.029297", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:31:55.452236+00:00", probability: "0.025802", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:36:24.689467+00:00", probability: "0.024184", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:41:20.080252+00:00", probability: "0.026011", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:46:48.365847+00:00", probability: "0.025621", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:51:24.713585+00:00", probability: "0.014971", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:57:24.801333+00:00", probability: "0.012938", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:01:54.854394+00:00", probability: "0.014155", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:06:24.928070+00:00", probability: "0.013314", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:11:12.860871+00:00", probability: "0.020681", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:16:53.653676+00:00", probability: "0.020288", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:21:25.008971+00:00", probability: "0.021716", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:27:24.817660+00:00", probability: "0.021142", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:31:54.901607+00:00", probability: "0.014702", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:36:24.817000+00:00", probability: "0.012965", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:41:13.090598+00:00", probability: "0.014996", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:46:53.727811+00:00", probability: "0.016259", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:51:24.732031+00:00", probability: "0.017129", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:57:24.797035+00:00", probability: "0.01533", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:01:54.833885+00:00", probability: "0.014697", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:06:24.758254+00:00", probability: "0.007197", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:11:15.242501+00:00", probability: "0.007527", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:16:54.757109+00:00", probability: "0.004711", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:21:24.742441+00:00", probability: "0.005519", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:27:24.789808+00:00", probability: "0.005155", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:31:54.822029+00:00", probability: "0.006014", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:36:24.971616+00:00", probability: "0.00503", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:41:09.040738+00:00", probability: "0.004699", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:46:49.098542+00:00", probability: "0.0064", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:51:24.875685+00:00", probability: "0.012134", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:57:24.779033+00:00", probability: "0.011818", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:01:54.933191+00:00", probability: "0.012815", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:06:25.123480+00:00", probability: "0.012018", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:12:24.939797+00:00", probability: "0.01412", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:16:54.854142+00:00", probability: "0.012298", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:21:24.981246+00:00", probability: "0.007723", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:27:25.121923+00:00", probability: "0.021978", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:32:05.421227+00:00", probability: "0.024182", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:36:24.993990+00:00", probability: "0.021882", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:42:24.976809+00:00", probability: "0.016807", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:46:54.961700+00:00", probability: "0.016978", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:51:24.941083+00:00", probability: "0.013199", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:57:25.853387+00:00", probability: "0.012611", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:01:55.007660+00:00", probability: "0.012035", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:06:25.056796+00:00", probability: "0.011255", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:12:24.917957+00:00", probability: "0.011064", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:16:55.057037+00:00", probability: "0.012155", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:21:25.519889+00:00", probability: "0.011352", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:27:25.086697+00:00", probability: "0.013277", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:31:54.980387+00:00", probability: "0.013456", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:42:43.024481+00:00", probability: "0.01308", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:46:54.836301+00:00", probability: "0.0126", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:51:25.119887+00:00", probability: "0.013083", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:57:24.994475+00:00", probability: "0.01198", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T07:01:55.134023+00:00", probability: "0.013317", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T07:12:24.978448+00:00", probability: "0.01303", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T11:03:25.396420+00:00", probability: "0.012495", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:01:32.121700+00:00", probability: "0.011925", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:07:32.296237+00:00", probability: "0.012483", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:16:38.233711+00:00", probability: "0.011339", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:22:36.878874+00:00", probability: "0.012277", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:27:02.254196+00:00", probability: "0.011556", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:31:32.393467+00:00", probability: "0.012461", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:37:36.325422+00:00", probability: "0.009846", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:42:02.397711+00:00", probability: "0.009025", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:46:32.201718+00:00", probability: "0.010345", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:52:32.230383+00:00", probability: "0.016011", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:57:02.292294+00:00", probability: "0.015393", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:01:44.967297+00:00", probability: "0.014136", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:07:40.922682+00:00", probability: "0.013359", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:22:32.457644+00:00", probability: "0.0284", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:27:02.328365+00:00", probability: "0.02988", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:31:30.766239+00:00", probability: "0.0317", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:37:29.853954+00:00", probability: "0.033311", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:42:03.894288+00:00", probability: "0.025939", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:46:32.499339+00:00", probability: "0.026942", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:52:30.103758+00:00", probability: "0.029321", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:57:02.295932+00:00", probability: "0.03395", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:01:32.388551+00:00", probability: "0.032321", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:07:30.589268+00:00", probability: "0.034019", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:12:02.539866+00:00", probability: "0.017778", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:16:32.509056+00:00", probability: "0.017428", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:22:29.118118+00:00", probability: "0.022074", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:27:02.431908+00:00", probability: "0.02158", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:31:36.176169+00:00", probability: "0.021006", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:37:36.275556+00:00", probability: "0.017578", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:41:10.306614+00:00", probability: "0.014155", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:46:29.373474+00:00", probability: "0.013755", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:52:25.547135+00:00", probability: "0.013174", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:57:02.515905+00:00", probability: "0.011217", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:01:32.475241+00:00", probability: "0.012805", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:07:27.584475+00:00", probability: "0.012665", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:12:09.791890+00:00", probability: "0.003156", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:16:32.467564+00:00", probability: "0.00219", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:22:28.900262+00:00", probability: "0.00279", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:27:02.467693+00:00", probability: "0.007944", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:31:32.355628+00:00", probability: "0.002373", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:37:24.925694+00:00", probability: "0.003209", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:42:02.599933+00:00", probability: "0.002985", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:46:32.528698+00:00", probability: "0.003913", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:52:32.323694+00:00", probability: "0.001407", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:57:02.721177+00:00", probability: "0.001243", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:01:32.667681+00:00", probability: "0.001063", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:07:32.604608+00:00", probability: "0.000341", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:12:02.392117+00:00", probability: "0.000561", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:22:29.559191+00:00", probability: "0.00028", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:27:02.372895+00:00", probability: "0.000381", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:31:32.369451+00:00", probability: "0.000601", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:42:02.586740+00:00", probability: "0.00038", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:46:32.643579+00:00", probability: "0.000201", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:31:32.787975+00:00", probability: "0.000101", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:46:35.986461+00:00", probability: "0.00024", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:57:02.608225+00:00", probability: "0.00042", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:01:32.642953+00:00", probability: "2e-05", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:07:32.662386+00:00", probability: "0.000201", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:12:02.573288+00:00", probability: "6e-05", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:22:32.896568+00:00", probability: "0.000341", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:27:02.942302+00:00", probability: "0.00016", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:31:32.642402+00:00", probability: "0.000339", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:41:27.690470+00:00", probability: "0.000442", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:57:03.118947+00:00", probability: "0.00034", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:21:55.871409+00:00", probability: "4e-05", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:27:46.592637+00:00", probability: "0.000182", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:32:25.882164+00:00", probability: "8e-05", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T22:08:55.891004+00:00", probability: "0.04045", americanOdds: nil, bookmaker: "consensus"),
        ]),
        GolfClosingRetainedSeries10868(outcomeID: "242242532", name: "Ryan Gerard", eliminated: false, eliminatedAt: nil, history: [
            GolfClosingRetainedPoint10868(timestamp: "2026-10-05T17:39:14.507306+00:00", probability: "0.039667", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-06T13:08:40.644152+00:00", probability: "0.040733", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:02:03.231914+00:00", probability: "0.038362", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:06:33.172825+00:00", probability: "0.039158", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:11:13.058928+00:00", probability: "0.039947", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:23:03.133505+00:00", probability: "0.039738", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:27:33.145591+00:00", probability: "0.038653", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:32:03.148937+00:00", probability: "0.040362", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:36:33.267676+00:00", probability: "0.041664", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:47:03.467275+00:00", probability: "0.038534", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:51:33.222200+00:00", probability: "0.037652", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:56:03.237230+00:00", probability: "0.037499", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:06:08.309734+00:00", probability: "0.03717", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:12:08.303481+00:00", probability: "0.038075", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:16:30.062412+00:00", probability: "0.037068", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:21:08.558032+00:00", probability: "0.036834", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:27:08.639061+00:00", probability: "0.035433", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:31:26.916892+00:00", probability: "0.035293", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:36:08.458334+00:00", probability: "0.035529", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:42:08.462936+00:00", probability: "0.05244", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:46:26.904828+00:00", probability: "0.051926", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:51:08.591737+00:00", probability: "0.050235", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:57:08.492012+00:00", probability: "0.049632", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:01:32.422514+00:00", probability: "0.050188", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:06:08.863154+00:00", probability: "0.049421", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:12:08.442006+00:00", probability: "0.054854", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:16:33.390446+00:00", probability: "0.053872", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:21:08.578066+00:00", probability: "0.053625", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:27:08.700847+00:00", probability: "0.052638", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:31:38.648207+00:00", probability: "0.053025", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:36:13.310618+00:00", probability: "0.053842", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:42:08.507576+00:00", probability: "0.054741", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:46:29.234103+00:00", probability: "0.051008", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:51:08.598563+00:00", probability: "0.048655", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:57:08.575077+00:00", probability: "0.046526", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:01:38.486948+00:00", probability: "0.047868", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:07:38.415236+00:00", probability: "0.047299", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:12:08.483856+00:00", probability: "0.048118", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:16:38.372037+00:00", probability: "0.047768", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:21:08.495213+00:00", probability: "0.040657", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:27:08.684216+00:00", probability: "0.040193", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:31:38.545519+00:00", probability: "0.041453", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:36:08.436708+00:00", probability: "0.04118", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:42:08.398714+00:00", probability: "0.041764", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:46:38.504366+00:00", probability: "0.046074", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:51:08.444107+00:00", probability: "0.042737", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:57:08.415687+00:00", probability: "0.042573", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:01:38.448606+00:00", probability: "0.040597", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:06:08.459731+00:00", probability: "0.042356", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:12:08.572694+00:00", probability: "0.045386", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:16:38.638257+00:00", probability: "0.04558", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:21:08.445056+00:00", probability: "0.047389", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:27:08.423388+00:00", probability: "0.045909", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:31:38.695212+00:00", probability: "0.045347", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:36:08.476578+00:00", probability: "0.045532", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:42:08.515784+00:00", probability: "0.062738", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:46:38.487589+00:00", probability: "0.058654", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:51:09.005838+00:00", probability: "0.055388", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:57:08.971709+00:00", probability: "0.056121", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:06:09.189943+00:00", probability: "0.05444", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:12:09.189349+00:00", probability: "0.084245", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:16:39.126639+00:00", probability: "0.083977", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:21:09.103878+00:00", probability: "0.089188", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:27:09.192337+00:00", probability: "0.084482", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:31:39.251792+00:00", probability: "0.080325", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:36:09.226450+00:00", probability: "0.079863", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:42:09.098398+00:00", probability: "0.081574", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:46:39.390867+00:00", probability: "0.078281", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:51:09.148688+00:00", probability: "0.063423", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:57:09.366348+00:00", probability: "0.062471", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:01:30.800138+00:00", probability: "0.066349", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:06:01.132593+00:00", probability: "0.066882", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:12:01.029217+00:00", probability: "0.06531", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:16:30.978149+00:00", probability: "0.086512", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:22:31.080453+00:00", probability: "0.088947", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:27:01.043399+00:00", probability: "0.085602", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:31:30.973790+00:00", probability: "0.03299", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:37:31.205466+00:00", probability: "0.031932", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:42:01.216854+00:00", probability: "0.031616", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:46:31.004456+00:00", probability: "0.032023", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:51:00.993924+00:00", probability: "0.032588", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:57:01.285974+00:00", probability: "0.031167", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T07:01:31.228243+00:00", probability: "0.030693", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T07:07:31.021816+00:00", probability: "0.032925", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:01:54.271593+00:00", probability: "0.032504", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:06:24.569832+00:00", probability: "0.033951", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:11:16.020101+00:00", probability: "0.033518", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:16:54.121527+00:00", probability: "0.031342", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:21:24.361544+00:00", probability: "0.033124", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:27:24.299799+00:00", probability: "0.032293", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:31:54.432306+00:00", probability: "0.032401", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:36:24.206129+00:00", probability: "0.030588", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:41:07.477710+00:00", probability: "0.028815", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:46:54.210856+00:00", probability: "0.029608", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:51:24.151362+00:00", probability: "0.026834", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:57:24.059847+00:00", probability: "0.023643", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:01:54.411616+00:00", probability: "0.024534", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:06:24.117663+00:00", probability: "0.026467", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:11:05.714663+00:00", probability: "0.02592", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:16:52.306605+00:00", probability: "0.025044", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:21:24.221027+00:00", probability: "0.029178", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:27:24.425662+00:00", probability: "0.029401", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:31:54.571872+00:00", probability: "0.032512", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:36:24.532871+00:00", probability: "0.0307", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:42:24.709592+00:00", probability: "0.028914", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:46:55.026284+00:00", probability: "0.027028", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:51:24.654444+00:00", probability: "0.028552", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:57:24.715348+00:00", probability: "0.029848", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:01:59.282505+00:00", probability: "0.030236", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:06:24.836570+00:00", probability: "0.031328", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:11:11.909513+00:00", probability: "0.030893", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:16:57.222706+00:00", probability: "0.024541", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:21:24.867456+00:00", probability: "0.026327", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:27:24.676035+00:00", probability: "0.026019", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:31:55.452236+00:00", probability: "0.03217", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:36:24.689467+00:00", probability: "0.031978", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:41:20.080252+00:00", probability: "0.034508", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:51:24.713585+00:00", probability: "0.034324", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:57:24.801333+00:00", probability: "0.047097", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:01:54.854394+00:00", probability: "0.048651", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:06:24.928070+00:00", probability: "0.052604", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:11:12.860871+00:00", probability: "0.050215", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:16:53.653676+00:00", probability: "0.0496", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:21:25.008971+00:00", probability: "0.02994", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:27:24.817660+00:00", probability: "0.032917", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:31:54.901607+00:00", probability: "0.034041", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:36:24.817000+00:00", probability: "0.034521", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:41:13.090598+00:00", probability: "0.037075", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:51:24.732031+00:00", probability: "0.050611", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:57:24.797035+00:00", probability: "0.049524", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:06:24.758254+00:00", probability: "0.049039", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:11:15.242501+00:00", probability: "0.031195", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:16:54.757109+00:00", probability: "0.030555", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:21:24.742441+00:00", probability: "0.028296", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:27:24.789808+00:00", probability: "0.029741", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:31:54.822029+00:00", probability: "0.016982", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:36:24.971616+00:00", probability: "0.015306", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:41:09.040738+00:00", probability: "0.016209", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:46:49.098542+00:00", probability: "0.017267", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:51:24.875685+00:00", probability: "0.015185", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:57:24.779033+00:00", probability: "0.014908", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:01:54.933191+00:00", probability: "0.015045", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:06:25.123480+00:00", probability: "0.024677", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:12:24.939797+00:00", probability: "0.023438", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:16:54.854142+00:00", probability: "0.023885", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:21:24.981246+00:00", probability: "0.024842", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:27:25.121923+00:00", probability: "0.016289", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:32:05.421227+00:00", probability: "0.014473", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:36:24.993990+00:00", probability: "0.014847", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:42:24.976809+00:00", probability: "0.012245", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:46:54.961700+00:00", probability: "0.0146", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:51:24.941083+00:00", probability: "0.013218", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:57:25.853387+00:00", probability: "0.012561", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:01:55.007660+00:00", probability: "0.011101", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:06:25.056796+00:00", probability: "0.01066", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:12:24.917957+00:00", probability: "0.012069", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:16:55.057037+00:00", probability: "0.012356", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:21:25.519889+00:00", probability: "0.011583", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:27:25.086697+00:00", probability: "0.012936", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:31:54.980387+00:00", probability: "0.013371", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:36:24.977474+00:00", probability: "0.013572", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:42:43.024481+00:00", probability: "0.012992", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:46:54.836301+00:00", probability: "0.013198", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:51:25.119887+00:00", probability: "0.012575", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:57:24.994475+00:00", probability: "0.012338", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T07:01:55.134023+00:00", probability: "0.01201", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T07:06:24.990357+00:00", probability: "0.012762", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T07:12:24.978448+00:00", probability: "0.012271", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T11:03:25.396420+00:00", probability: "0.011351", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:01:32.121700+00:00", probability: "0.012572", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:07:32.296237+00:00", probability: "0.012189", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:12:02.146122+00:00", probability: "0.013345", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:16:38.233711+00:00", probability: "0.011325", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:22:36.878874+00:00", probability: "0.012195", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:27:02.254196+00:00", probability: "0.012351", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:37:36.325422+00:00", probability: "0.017958", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:42:02.397711+00:00", probability: "0.019317", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:46:32.201718+00:00", probability: "0.019159", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:52:32.230383+00:00", probability: "0.015296", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:57:02.292294+00:00", probability: "0.015711", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:01:44.967297+00:00", probability: "0.014158", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:07:40.922682+00:00", probability: "0.013484", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:11:31.557654+00:00", probability: "0.014826", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:16:32.368568+00:00", probability: "0.013049", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:22:32.457644+00:00", probability: "0.013755", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:27:02.328365+00:00", probability: "0.014827", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:31:30.766239+00:00", probability: "0.015466", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:37:29.853954+00:00", probability: "0.01665", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:42:03.894288+00:00", probability: "0.023909", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:46:32.499339+00:00", probability: "0.024409", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:52:30.103758+00:00", probability: "0.029845", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:57:02.295932+00:00", probability: "0.032978", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:01:32.388551+00:00", probability: "0.033669", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:07:30.589268+00:00", probability: "0.031903", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:12:02.539866+00:00", probability: "0.036132", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:16:32.509056+00:00", probability: "0.035981", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:22:29.118118+00:00", probability: "0.040188", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:27:02.431908+00:00", probability: "0.03812", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:31:36.176169+00:00", probability: "0.038367", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:37:36.275556+00:00", probability: "0.03742", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:41:10.306614+00:00", probability: "0.057179", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:46:29.373474+00:00", probability: "0.052931", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:52:25.547135+00:00", probability: "0.052824", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:57:02.515905+00:00", probability: "0.047207", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:01:32.475241+00:00", probability: "0.048427", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:07:27.584475+00:00", probability: "0.049602", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:12:09.791890+00:00", probability: "0.015679", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:16:32.467564+00:00", probability: "0.017207", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:22:28.900262+00:00", probability: "0.018007", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:27:02.467693+00:00", probability: "0.017296", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:31:32.355628+00:00", probability: "0.001223", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:42:02.599933+00:00", probability: "0.003467", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:46:32.528698+00:00", probability: "0.003051", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:52:32.323694+00:00", probability: "0.007823", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:57:02.721177+00:00", probability: "0.006837", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:01:32.667681+00:00", probability: "0.007102", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:07:32.604608+00:00", probability: "0.009912", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:12:02.392117+00:00", probability: "0.010119", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:16:32.504599+00:00", probability: "0.022948", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:22:29.559191+00:00", probability: "0.018621", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:27:02.372895+00:00", probability: "0.019227", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:37:32.480772+00:00", probability: "0.022684", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:42:02.586740+00:00", probability: "0.018313", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:46:32.643579+00:00", probability: "0.016367", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:57:02.421912+00:00", probability: "0.016973", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:01:29.696997+00:00", probability: "0.01658", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:07:35.495038+00:00", probability: "0.013777", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:12:29.682303+00:00", probability: "0.015217", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:16:32.524509+00:00", probability: "0.011977", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:22:32.710013+00:00", probability: "0.01043", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:27:02.718901+00:00", probability: "0.011673", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:31:32.787975+00:00", probability: "0.012033", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:37:32.795010+00:00", probability: "0.012559", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:42:02.797854+00:00", probability: "0.017094", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:46:35.986461+00:00", probability: "0.017653", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:57:02.608225+00:00", probability: "0.019117", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:01:32.642953+00:00", probability: "0.016907", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:07:32.662386+00:00", probability: "0.016635", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:12:02.573288+00:00", probability: "0.016266", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:16:33.417463+00:00", probability: "0.018613", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:22:32.896568+00:00", probability: "0.022547", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:27:02.942302+00:00", probability: "0.021183", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:31:32.642402+00:00", probability: "0.025178", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:37:32.753311+00:00", probability: "0.02355", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:41:27.690470+00:00", probability: "0.024516", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:46:46.608343+00:00", probability: "0.024192", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:52:32.921891+00:00", probability: "0.024294", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:57:03.118947+00:00", probability: "0.023761", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T07:01:33.168803+00:00", probability: "0.027507", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T07:07:32.955805+00:00", probability: "0.028512", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T11:22:35.155437+00:00", probability: "0.0288", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:02:37.532470+00:00", probability: "0.027374", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:07:07.544047+00:00", probability: "0.027035", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:12:00.122315+00:00", probability: "0.028721", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:18:14.003636+00:00", probability: "0.028175", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:21:55.871409+00:00", probability: "0.028847", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:27:46.592637+00:00", probability: "0.027837", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:32:25.882164+00:00", probability: "0.029266", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:36:48.896569+00:00", probability: "0.026896", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:42:03.732719+00:00", probability: "0.027573", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:47:42.984192+00:00", probability: "0.027319", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:51:54.681637+00:00", probability: "0.026612", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:56:25.710971+00:00", probability: "0.0264", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:06:47.216580+00:00", probability: "0.027938", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:11:25.894787+00:00", probability: "0.027766", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:17:25.996026+00:00", probability: "0.019083", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:21:51.113011+00:00", probability: "0.018892", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:32:25.929155+00:00", probability: "0.018318", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:41:50.635611+00:00", probability: "0.013393", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:47:26.043890+00:00", probability: "0.013145", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:51:55.909934+00:00", probability: "0.014546", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:56:18.272058+00:00", probability: "0.017604", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:02:25.797469+00:00", probability: "0.01772", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:06:49.546752+00:00", probability: "0.022605", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:11:25.914867+00:00", probability: "0.022738", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:17:26.184322+00:00", probability: "0.028917", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:21:46.781176+00:00", probability: "0.026632", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:27:55.905318+00:00", probability: "0.021007", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:36:56.174519+00:00", probability: "0.020847", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:41:27.839983+00:00", probability: "0.029407", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:47:26.204894+00:00", probability: "0.028146", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:51:48.376763+00:00", probability: "0.031122", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:56:25.933285+00:00", probability: "0.018862", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:02:26.039667+00:00", probability: "0.017575", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:06:49.491181+00:00", probability: "0.017167", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:11:38.956586+00:00", probability: "0.006778", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:21:48.518176+00:00", probability: "0.007115", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:27:57.815530+00:00", probability: "0.006528", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:32:25.820139+00:00", probability: "0.020315", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:36:56.232276+00:00", probability: "0.021176", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:41:25.890612+00:00", probability: "0.024546", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:47:26.160310+00:00", probability: "0.020903", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:51:50.533672+00:00", probability: "0.019814", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:56:26.064918+00:00", probability: "0.022479", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:02:26.587145+00:00", probability: "0.018193", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:06:56.215374+00:00", probability: "0.016822", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:11:37.607125+00:00", probability: "0.012828", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:17:26.043707+00:00", probability: "0.014661", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:21:56.168662+00:00", probability: "0.019274", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:27:55.803030+00:00", probability: "0.012924", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:32:25.858478+00:00", probability: "0.025849", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:36:56.195550+00:00", probability: "0.025274", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:41:25.968157+00:00", probability: "0.027765", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:47:26.137402+00:00", probability: "0.028986", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:51:49.540257+00:00", probability: "0.010369", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:56:26.068260+00:00", probability: "0.006987", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:02:25.929267+00:00", probability: "0.007299", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:06:48.547245+00:00", probability: "0.048931", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:11:25.974142+00:00", probability: "0.056928", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:17:25.818931+00:00", probability: "0.065237", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:21:56.090554+00:00", probability: "0.067392", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:27:50.421885+00:00", probability: "0.040707", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:32:25.965758+00:00", probability: "0.041983", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:36:55.848422+00:00", probability: "0.02597", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:41:26.109476+00:00", probability: "0.023781", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:47:26.024631+00:00", probability: "0.024306", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:51:55.997823+00:00", probability: "0.022182", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:56:25.840963+00:00", probability: "0.0", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T06:02:25.916250+00:00", probability: "0.00012", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T06:06:55.965994+00:00", probability: "0.000421", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T06:11:34.934252+00:00", probability: "0.000202", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T06:17:26.152308+00:00", probability: "0.0", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T22:08:55.891004+00:00", probability: "0.040733", americanOdds: nil, bookmaker: "consensus"),
        ]),
        GolfClosingRetainedSeries10868(outcomeID: "242242537", name: "Adam Scott", eliminated: false, eliminatedAt: nil, history: [
            GolfClosingRetainedPoint10868(timestamp: "2026-10-05T17:39:14.507306+00:00", probability: "0.03295", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-06T13:08:40.644152+00:00", probability: "0.034717", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:02:03.231914+00:00", probability: "0.032775", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:06:33.172825+00:00", probability: "0.032923", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:11:13.058928+00:00", probability: "0.032534", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:16:55.542752+00:00", probability: "0.032817", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:23:03.133505+00:00", probability: "0.032571", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:27:33.145591+00:00", probability: "0.03294", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:32:03.148937+00:00", probability: "0.032708", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:36:33.267676+00:00", probability: "0.036005", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:42:33.349212+00:00", probability: "0.032775", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:47:03.467275+00:00", probability: "0.031825", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:51:33.222200+00:00", probability: "0.031413", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:56:03.237230+00:00", probability: "0.032063", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:01:38.226778+00:00", probability: "0.031072", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:12:08.303481+00:00", probability: "0.030616", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:16:30.062412+00:00", probability: "0.030954", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:21:08.558032+00:00", probability: "0.03107", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:27:08.639061+00:00", probability: "0.028611", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:31:26.916892+00:00", probability: "0.028959", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:36:08.458334+00:00", probability: "0.028335", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:42:08.462936+00:00", probability: "0.02821", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:46:26.904828+00:00", probability: "0.027668", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:51:08.591737+00:00", probability: "0.027883", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:57:08.492012+00:00", probability: "0.025278", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:01:32.422514+00:00", probability: "0.026801", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:06:08.863154+00:00", probability: "0.022718", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:12:08.442006+00:00", probability: "0.024468", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:21:08.578066+00:00", probability: "0.022801", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:27:08.700847+00:00", probability: "0.022576", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:31:38.648207+00:00", probability: "0.023802", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:36:13.310618+00:00", probability: "0.024473", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:42:08.507576+00:00", probability: "0.027343", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:46:29.234103+00:00", probability: "0.024594", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:51:08.598563+00:00", probability: "0.021585", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:57:08.575077+00:00", probability: "0.021441", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:01:38.486948+00:00", probability: "0.021091", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:07:38.415236+00:00", probability: "0.015274", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:12:08.483856+00:00", probability: "0.016782", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:16:38.372037+00:00", probability: "0.015554", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:21:08.495213+00:00", probability: "0.026666", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:27:08.684216+00:00", probability: "0.027235", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:31:38.545519+00:00", probability: "0.024579", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:36:08.436708+00:00", probability: "0.022644", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:42:08.398714+00:00", probability: "0.021515", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:46:38.504366+00:00", probability: "0.023852", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:51:08.444107+00:00", probability: "0.021458", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:57:08.415687+00:00", probability: "0.021807", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:01:38.448606+00:00", probability: "0.023092", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:06:08.459731+00:00", probability: "0.024388", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:12:08.572694+00:00", probability: "0.023444", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:16:38.638257+00:00", probability: "0.015226", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:21:08.445056+00:00", probability: "0.016223", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:27:08.423388+00:00", probability: "0.014619", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:31:38.695212+00:00", probability: "0.024665", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:36:08.476578+00:00", probability: "0.025582", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:42:08.515784+00:00", probability: "0.024448", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:46:38.487589+00:00", probability: "0.025714", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:57:08.971709+00:00", probability: "0.025102", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:01:39.221294+00:00", probability: "0.02583", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:06:09.189943+00:00", probability: "0.029299", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:12:09.189349+00:00", probability: "0.028749", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:16:39.126639+00:00", probability: "0.030663", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:27:09.192337+00:00", probability: "0.029275", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:31:39.251792+00:00", probability: "0.029986", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:36:09.226450+00:00", probability: "0.031078", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:42:09.098398+00:00", probability: "0.02643", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:46:39.390867+00:00", probability: "0.024603", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:51:09.148688+00:00", probability: "0.025285", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:57:09.366348+00:00", probability: "0.015179", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:01:30.800138+00:00", probability: "0.016566", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:06:01.132593+00:00", probability: "0.015058", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:12:01.029217+00:00", probability: "0.016515", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:16:30.978149+00:00", probability: "0.015122", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:22:31.080453+00:00", probability: "0.014885", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:27:01.043399+00:00", probability: "0.013045", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:31:30.973790+00:00", probability: "0.013968", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:37:31.205466+00:00", probability: "0.015651", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:46:31.004456+00:00", probability: "0.016073", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:51:00.993924+00:00", probability: "0.016933", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:57:01.285974+00:00", probability: "0.015644", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T07:07:31.021816+00:00", probability: "0.016435", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:06:24.569832+00:00", probability: "0.016124", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:11:16.020101+00:00", probability: "0.015969", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:16:54.121527+00:00", probability: "0.016357", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:21:24.361544+00:00", probability: "0.015932", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:27:24.299799+00:00", probability: "0.016848", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:31:54.432306+00:00", probability: "0.016524", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:36:24.206129+00:00", probability: "0.014805", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:41:07.477710+00:00", probability: "0.015626", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:46:54.210856+00:00", probability: "0.015484", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:51:24.151362+00:00", probability: "0.015196", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:57:24.059847+00:00", probability: "0.015022", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:01:54.411616+00:00", probability: "0.015179", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:06:24.117663+00:00", probability: "0.014997", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:11:05.714663+00:00", probability: "0.01607", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:16:52.306605+00:00", probability: "0.016595", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:21:24.221027+00:00", probability: "0.014729", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:27:24.425662+00:00", probability: "0.01557", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:31:54.571872+00:00", probability: "0.015242", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:36:24.532871+00:00", probability: "0.020574", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:42:24.709592+00:00", probability: "0.021603", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:46:55.026284+00:00", probability: "0.022886", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:51:24.654444+00:00", probability: "0.021663", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:57:24.715348+00:00", probability: "0.021975", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:01:59.282505+00:00", probability: "0.022304", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:06:24.836570+00:00", probability: "0.025433", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:11:11.909513+00:00", probability: "0.023024", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:16:57.222706+00:00", probability: "0.024047", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:21:24.867456+00:00", probability: "0.023017", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:27:24.676035+00:00", probability: "0.02069", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:31:55.452236+00:00", probability: "0.020105", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:36:24.689467+00:00", probability: "0.021108", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:41:20.080252+00:00", probability: "0.0348", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:46:48.365847+00:00", probability: "0.032557", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:51:24.713585+00:00", probability: "0.035019", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:57:24.801333+00:00", probability: "0.033705", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:01:54.854394+00:00", probability: "0.019415", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:06:24.928070+00:00", probability: "0.020673", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:11:12.860871+00:00", probability: "0.017595", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:16:53.653676+00:00", probability: "0.018192", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:21:25.008971+00:00", probability: "0.018771", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:27:24.817660+00:00", probability: "0.019908", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:31:54.901607+00:00", probability: "0.021557", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:36:24.817000+00:00", probability: "0.022422", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:41:13.090598+00:00", probability: "0.011414", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:46:53.727811+00:00", probability: "0.012475", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:51:24.732031+00:00", probability: "0.00923", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:57:24.797035+00:00", probability: "0.009682", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:01:54.833885+00:00", probability: "0.009849", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:06:24.758254+00:00", probability: "0.008807", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:11:15.242501+00:00", probability: "0.009813", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:16:54.757109+00:00", probability: "0.010839", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:21:24.742441+00:00", probability: "0.011058", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:27:24.789808+00:00", probability: "0.01026", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:31:54.822029+00:00", probability: "0.018131", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:36:24.971616+00:00", probability: "0.017606", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:41:09.040738+00:00", probability: "0.016931", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:51:24.875685+00:00", probability: "0.010155", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:57:24.779033+00:00", probability: "0.020158", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:01:54.933191+00:00", probability: "0.020532", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:06:25.123480+00:00", probability: "0.020218", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:12:24.939797+00:00", probability: "0.02749", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:16:54.854142+00:00", probability: "0.02613", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:21:24.981246+00:00", probability: "0.029344", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:27:25.121923+00:00", probability: "0.023895", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:32:05.421227+00:00", probability: "0.023437", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:36:24.993990+00:00", probability: "0.024063", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:42:24.976809+00:00", probability: "0.022502", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:46:54.961700+00:00", probability: "0.022855", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:51:24.941083+00:00", probability: "0.022377", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:57:25.853387+00:00", probability: "0.021759", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:01:55.007660+00:00", probability: "0.019265", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:06:25.056796+00:00", probability: "0.019466", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:12:24.917957+00:00", probability: "0.019822", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:16:55.057037+00:00", probability: "0.019022", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:21:25.519889+00:00", probability: "0.020065", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:27:25.086697+00:00", probability: "0.021424", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:31:54.980387+00:00", probability: "0.020992", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:36:24.977474+00:00", probability: "0.021327", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:42:43.024481+00:00", probability: "0.019307", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:46:54.836301+00:00", probability: "0.022398", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:51:25.119887+00:00", probability: "0.019757", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:57:24.994475+00:00", probability: "0.019982", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T07:01:55.134023+00:00", probability: "0.020782", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T07:06:24.990357+00:00", probability: "0.021003", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T07:12:24.978448+00:00", probability: "0.019916", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T11:03:25.396420+00:00", probability: "0.0196", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:01:32.121700+00:00", probability: "0.020298", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:12:02.146122+00:00", probability: "0.020881", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:16:38.233711+00:00", probability: "0.020143", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:22:36.878874+00:00", probability: "0.019955", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:31:32.393467+00:00", probability: "0.020129", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:42:02.397711+00:00", probability: "0.01862", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:46:32.201718+00:00", probability: "0.019966", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:52:32.230383+00:00", probability: "0.018401", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:57:02.292294+00:00", probability: "0.019589", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:01:44.967297+00:00", probability: "0.020984", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:07:40.922682+00:00", probability: "0.020458", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:11:31.557654+00:00", probability: "0.03203", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:16:32.368568+00:00", probability: "0.031317", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:22:32.457644+00:00", probability: "0.031959", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:27:02.328365+00:00", probability: "0.030851", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:31:30.766239+00:00", probability: "0.030137", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:37:29.853954+00:00", probability: "0.025713", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:42:03.894288+00:00", probability: "0.023987", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:46:32.499339+00:00", probability: "0.023298", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:52:30.103758+00:00", probability: "0.025752", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:57:02.295932+00:00", probability: "0.028777", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:01:32.388551+00:00", probability: "0.027053", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:07:30.589268+00:00", probability: "0.016403", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:12:02.539866+00:00", probability: "0.016708", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:16:32.509056+00:00", probability: "0.0186", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:22:29.118118+00:00", probability: "0.020207", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:27:02.431908+00:00", probability: "0.019177", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:31:36.176169+00:00", probability: "0.020743", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:37:36.275556+00:00", probability: "0.033561", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:41:10.306614+00:00", probability: "0.032887", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:46:29.373474+00:00", probability: "0.058806", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:52:25.547135+00:00", probability: "0.060603", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:57:02.515905+00:00", probability: "0.05369", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:01:32.475241+00:00", probability: "0.029695", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:07:27.584475+00:00", probability: "0.02933", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:12:09.791890+00:00", probability: "0.028911", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:16:32.467564+00:00", probability: "0.032249", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:22:28.900262+00:00", probability: "0.034295", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:27:02.467693+00:00", probability: "0.0528", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:31:32.355628+00:00", probability: "0.08975", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:37:24.925694+00:00", probability: "0.091329", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:42:02.599933+00:00", probability: "0.092973", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:46:32.528698+00:00", probability: "0.09879", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:52:32.323694+00:00", probability: "0.111166", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:57:02.721177+00:00", probability: "0.100349", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:01:32.667681+00:00", probability: "0.097485", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:07:32.604608+00:00", probability: "0.09723", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:12:02.392117+00:00", probability: "0.09803", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:16:32.504599+00:00", probability: "0.105077", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:22:29.559191+00:00", probability: "0.094763", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:27:02.372895+00:00", probability: "0.097219", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:31:32.369451+00:00", probability: "0.089656", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:37:32.480772+00:00", probability: "0.072085", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:42:02.586740+00:00", probability: "0.059799", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:46:32.643579+00:00", probability: "0.085978", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:52:29.927815+00:00", probability: "0.086161", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:57:02.421912+00:00", probability: "0.079462", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:01:29.696997+00:00", probability: "0.08496", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:07:35.495038+00:00", probability: "0.086183", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:12:29.682303+00:00", probability: "0.086449", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:16:32.524509+00:00", probability: "0.075555", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:22:32.710013+00:00", probability: "0.058755", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:27:02.718901+00:00", probability: "0.053921", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:31:32.787975+00:00", probability: "0.060483", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:37:32.795010+00:00", probability: "0.058608", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:42:02.797854+00:00", probability: "0.068852", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:46:35.986461+00:00", probability: "0.073485", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:52:32.606932+00:00", probability: "0.07236", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:57:02.608225+00:00", probability: "0.069874", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:01:32.642953+00:00", probability: "0.065884", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:07:32.662386+00:00", probability: "0.06498", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:12:02.573288+00:00", probability: "0.072718", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:16:33.417463+00:00", probability: "0.07944", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:22:32.896568+00:00", probability: "0.091857", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:27:02.942302+00:00", probability: "0.091081", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:31:32.642402+00:00", probability: "0.101258", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:37:32.753311+00:00", probability: "0.100056", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:41:27.690470+00:00", probability: "0.100197", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:46:46.608343+00:00", probability: "0.098834", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:52:32.921891+00:00", probability: "0.100112", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:57:03.118947+00:00", probability: "0.098693", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T07:01:33.168803+00:00", probability: "0.113848", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T07:07:32.955805+00:00", probability: "0.113106", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T11:22:35.155437+00:00", probability: "0.113459", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:02:37.532470+00:00", probability: "0.110869", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:07:07.544047+00:00", probability: "0.113129", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:12:00.122315+00:00", probability: "0.113789", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:18:14.003636+00:00", probability: "0.111473", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:21:55.871409+00:00", probability: "0.11099", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:27:46.592637+00:00", probability: "0.113365", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:32:25.882164+00:00", probability: "0.110399", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:36:48.896569+00:00", probability: "0.113447", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:42:03.732719+00:00", probability: "0.113247", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:47:42.984192+00:00", probability: "0.1121", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:51:54.681637+00:00", probability: "0.113292", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:56:25.710971+00:00", probability: "0.112797", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:02:25.829089+00:00", probability: "0.111658", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:06:47.216580+00:00", probability: "0.110168", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:11:25.894787+00:00", probability: "0.109514", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:17:25.996026+00:00", probability: "0.115647", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:21:51.113011+00:00", probability: "0.113943", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:27:55.889037+00:00", probability: "0.112907", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:32:25.929155+00:00", probability: "0.106439", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:36:55.765217+00:00", probability: "0.103692", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:41:50.635611+00:00", probability: "0.110045", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:47:26.043890+00:00", probability: "0.09595", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:51:55.909934+00:00", probability: "0.099408", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:56:18.272058+00:00", probability: "0.087236", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:02:25.797469+00:00", probability: "0.086595", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:06:49.546752+00:00", probability: "0.108964", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:11:25.914867+00:00", probability: "0.109967", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:17:26.184322+00:00", probability: "0.105492", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:21:46.781176+00:00", probability: "0.10164", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:27:55.905318+00:00", probability: "0.120016", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:32:26.238967+00:00", probability: "0.121439", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:36:56.174519+00:00", probability: "0.119989", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:41:27.839983+00:00", probability: "0.143205", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:47:26.204894+00:00", probability: "0.144485", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:51:48.376763+00:00", probability: "0.146319", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:56:25.933285+00:00", probability: "0.099714", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:02:26.039667+00:00", probability: "0.099473", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:06:49.491181+00:00", probability: "0.109148", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:11:38.956586+00:00", probability: "0.078627", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:17:26.084407+00:00", probability: "0.079677", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:21:48.518176+00:00", probability: "0.078984", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:27:57.815530+00:00", probability: "0.028552", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:32:25.820139+00:00", probability: "0.07459", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:36:56.232276+00:00", probability: "0.074832", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:41:25.890612+00:00", probability: "0.080899", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:47:26.160310+00:00", probability: "0.063789", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:51:50.533672+00:00", probability: "0.066532", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:56:26.064918+00:00", probability: "0.064236", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:02:26.587145+00:00", probability: "0.142378", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:06:56.215374+00:00", probability: "0.145527", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:11:37.607125+00:00", probability: "0.144747", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:17:26.043707+00:00", probability: "0.158335", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:21:56.168662+00:00", probability: "0.056477", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:27:55.803030+00:00", probability: "0.058382", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:32:25.858478+00:00", probability: "0.092455", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:36:56.195550+00:00", probability: "0.092141", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:41:25.968157+00:00", probability: "0.025129", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:47:26.137402+00:00", probability: "0.026244", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:51:49.540257+00:00", probability: "0.021259", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:56:26.068260+00:00", probability: "0.018435", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:02:25.929267+00:00", probability: "0.017465", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:06:48.547245+00:00", probability: "0.00024", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:21:56.090554+00:00", probability: "6e-05", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:32:25.965758+00:00", probability: "0.00018", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:36:55.848422+00:00", probability: "0.00034", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:41:26.109476+00:00", probability: "0.00016", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:51:55.997823+00:00", probability: "0.0", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:56:25.840963+00:00", probability: "0.00012", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T06:11:34.934252+00:00", probability: "0.0", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T22:08:55.891004+00:00", probability: "0.034717", americanOdds: nil, bookmaker: "consensus"),
        ]),
        GolfClosingRetainedSeries10868(outcomeID: "242242534", name: "Hideki Matsuyama", eliminated: false, eliminatedAt: nil, history: [
            GolfClosingRetainedPoint10868(timestamp: "2026-10-05T17:39:14.507306+00:00", probability: "0.038917", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-06T13:08:40.644152+00:00", probability: "0.040733", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:02:03.231914+00:00", probability: "0.038534", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:06:33.172825+00:00", probability: "0.038875", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:11:13.058928+00:00", probability: "0.035425", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:16:55.542752+00:00", probability: "0.040074", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:23:03.133505+00:00", probability: "0.042075", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:27:33.145591+00:00", probability: "0.040528", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:32:03.148937+00:00", probability: "0.039964", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:36:33.267676+00:00", probability: "0.040491", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:42:33.349212+00:00", probability: "0.038177", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:47:03.467275+00:00", probability: "0.037649", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:51:33.222200+00:00", probability: "0.038378", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:56:03.237230+00:00", probability: "0.039275", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:01:38.226778+00:00", probability: "0.038601", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:06:08.309734+00:00", probability: "0.038709", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:12:08.303481+00:00", probability: "0.037413", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:16:30.062412+00:00", probability: "0.036911", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:21:08.558032+00:00", probability: "0.039475", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:27:08.639061+00:00", probability: "0.036117", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:36:08.458334+00:00", probability: "0.034489", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:42:08.462936+00:00", probability: "0.034092", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:46:26.904828+00:00", probability: "0.033978", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:51:08.591737+00:00", probability: "0.033819", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:57:08.492012+00:00", probability: "0.050318", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:06:08.863154+00:00", probability: "0.051885", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:12:08.442006+00:00", probability: "0.047564", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:16:33.390446+00:00", probability: "0.046589", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:21:08.578066+00:00", probability: "0.042315", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:27:08.700847+00:00", probability: "0.065571", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:31:38.648207+00:00", probability: "0.063354", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:36:13.310618+00:00", probability: "0.064254", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:42:08.507576+00:00", probability: "0.073435", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:46:29.234103+00:00", probability: "0.070591", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:51:08.598563+00:00", probability: "0.071619", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:57:08.575077+00:00", probability: "0.070398", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:01:38.486948+00:00", probability: "0.041209", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:07:38.415236+00:00", probability: "0.043399", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:12:08.483856+00:00", probability: "0.043253", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:16:38.372037+00:00", probability: "0.043946", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:21:08.495213+00:00", probability: "0.032876", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:27:08.684216+00:00", probability: "0.033797", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:31:38.545519+00:00", probability: "0.030831", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:36:08.436708+00:00", probability: "0.029758", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:42:08.398714+00:00", probability: "0.030382", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:46:38.504366+00:00", probability: "0.016889", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:51:08.444107+00:00", probability: "0.017802", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:57:08.415687+00:00", probability: "0.017279", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:01:38.448606+00:00", probability: "0.019244", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:06:08.459731+00:00", probability: "0.015241", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:12:08.572694+00:00", probability: "0.018368", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:16:38.638257+00:00", probability: "0.017578", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:21:08.445056+00:00", probability: "0.018713", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:27:08.423388+00:00", probability: "0.017737", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:31:38.695212+00:00", probability: "0.018332", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:36:08.476578+00:00", probability: "0.017226", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:42:08.515784+00:00", probability: "0.017719", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:46:38.487589+00:00", probability: "0.019292", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:51:09.005838+00:00", probability: "0.017948", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:57:08.971709+00:00", probability: "0.016612", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:01:39.221294+00:00", probability: "0.029755", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:06:09.189943+00:00", probability: "0.028132", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:12:09.189349+00:00", probability: "0.023969", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:16:39.126639+00:00", probability: "0.026591", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:21:09.103878+00:00", probability: "0.022298", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:27:09.192337+00:00", probability: "0.024923", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:31:39.251792+00:00", probability: "0.022796", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:42:09.098398+00:00", probability: "0.023074", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:46:39.390867+00:00", probability: "0.011896", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:51:09.148688+00:00", probability: "0.013187", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:57:09.366348+00:00", probability: "0.029727", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:01:30.800138+00:00", probability: "0.029853", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:06:01.132593+00:00", probability: "0.031138", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:12:01.029217+00:00", probability: "0.032932", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:16:30.978149+00:00", probability: "0.031426", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:22:31.080453+00:00", probability: "0.031102", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:27:01.043399+00:00", probability: "0.027059", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:31:30.973790+00:00", probability: "0.028612", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:37:31.205466+00:00", probability: "0.029903", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:42:01.216854+00:00", probability: "0.02835", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:46:31.004456+00:00", probability: "0.050705", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:51:00.993924+00:00", probability: "0.052715", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:57:01.285974+00:00", probability: "0.05083", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T07:01:31.228243+00:00", probability: "0.055022", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T07:07:31.021816+00:00", probability: "0.051481", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:01:54.271593+00:00", probability: "0.052041", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:06:24.569832+00:00", probability: "0.050751", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:11:16.020101+00:00", probability: "0.052829", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:16:54.121527+00:00", probability: "0.052485", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:21:24.361544+00:00", probability: "0.053185", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:27:24.299799+00:00", probability: "0.052089", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:31:54.432306+00:00", probability: "0.05179", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:36:24.206129+00:00", probability: "0.053621", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:41:07.477710+00:00", probability: "0.053088", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:46:54.210856+00:00", probability: "0.079819", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:51:24.151362+00:00", probability: "0.078141", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:57:24.059847+00:00", probability: "0.078784", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:01:54.411616+00:00", probability: "0.079207", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:06:24.117663+00:00", probability: "0.076098", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:11:05.714663+00:00", probability: "0.05264", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:16:52.306605+00:00", probability: "0.053944", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:21:24.221027+00:00", probability: "0.051105", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:27:24.425662+00:00", probability: "0.048637", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:31:54.571872+00:00", probability: "0.048861", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:36:24.532871+00:00", probability: "0.050807", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:42:24.709592+00:00", probability: "0.04923", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:46:55.026284+00:00", probability: "0.043108", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:51:24.654444+00:00", probability: "0.040871", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:57:24.715348+00:00", probability: "0.041132", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:01:59.282505+00:00", probability: "0.043592", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:06:24.836570+00:00", probability: "0.029338", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:11:11.909513+00:00", probability: "0.028061", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:16:57.222706+00:00", probability: "0.027194", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:21:24.867456+00:00", probability: "0.02439", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:27:24.676035+00:00", probability: "0.02505", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:31:55.452236+00:00", probability: "0.023237", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:36:24.689467+00:00", probability: "0.013178", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:41:20.080252+00:00", probability: "0.015079", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:46:48.365847+00:00", probability: "0.01451", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:51:24.713585+00:00", probability: "0.014027", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:57:24.801333+00:00", probability: "0.021151", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:01:54.854394+00:00", probability: "0.019655", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:06:24.928070+00:00", probability: "0.021919", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:11:12.860871+00:00", probability: "0.035403", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:16:53.653676+00:00", probability: "0.037975", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:21:25.008971+00:00", probability: "0.039136", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:27:24.817660+00:00", probability: "0.039403", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:31:54.901607+00:00", probability: "0.04215", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:36:24.817000+00:00", probability: "0.040719", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:41:13.090598+00:00", probability: "0.043777", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:46:53.727811+00:00", probability: "0.046", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:51:24.732031+00:00", probability: "0.043099", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:57:24.797035+00:00", probability: "0.043623", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:01:54.833885+00:00", probability: "0.03543", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:06:24.758254+00:00", probability: "0.034375", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:16:54.757109+00:00", probability: "0.032984", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:21:24.742441+00:00", probability: "0.034258", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:27:24.789808+00:00", probability: "0.022407", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:31:54.822029+00:00", probability: "0.024868", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:36:24.971616+00:00", probability: "0.023866", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:41:09.040738+00:00", probability: "0.021415", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:46:49.098542+00:00", probability: "0.019644", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:51:24.875685+00:00", probability: "0.017216", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:57:24.779033+00:00", probability: "0.02144", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:01:54.933191+00:00", probability: "0.0206", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:06:25.123480+00:00", probability: "0.00684", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:12:24.939797+00:00", probability: "0.005436", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:21:24.981246+00:00", probability: "0.006599", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:27:25.121923+00:00", probability: "0.004932", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:32:05.421227+00:00", probability: "0.004113", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:36:24.993990+00:00", probability: "0.004294", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:42:24.976809+00:00", probability: "0.003286", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:46:54.961700+00:00", probability: "0.002846", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:51:24.941083+00:00", probability: "0.002707", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:57:25.853387+00:00", probability: "0.002909", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:01:55.007660+00:00", probability: "0.001887", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:06:25.056796+00:00", probability: "0.002189", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:12:24.917957+00:00", probability: "0.002529", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:16:55.057037+00:00", probability: "0.002644", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:21:25.519889+00:00", probability: "0.002967", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:27:25.086697+00:00", probability: "0.003109", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:31:54.980387+00:00", probability: "0.003213", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:36:24.977474+00:00", probability: "0.002831", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:42:43.024481+00:00", probability: "0.002665", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:46:54.836301+00:00", probability: "0.002564", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:51:25.119887+00:00", probability: "0.002747", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T07:01:55.134023+00:00", probability: "0.002487", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T07:06:24.990357+00:00", probability: "0.002763", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T07:12:24.978448+00:00", probability: "0.003171", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T11:03:25.396420+00:00", probability: "0.002969", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:07:32.296237+00:00", probability: "0.002164", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:12:02.146122+00:00", probability: "0.002725", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:16:38.233711+00:00", probability: "0.002086", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:22:36.878874+00:00", probability: "0.002207", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:27:02.254196+00:00", probability: "0.001344", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:31:32.393467+00:00", probability: "0.002827", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:37:36.325422+00:00", probability: "0.002148", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:42:02.397711+00:00", probability: "0.002626", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:46:32.201718+00:00", probability: "0.006439", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:52:32.230383+00:00", probability: "0.006737", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:57:02.292294+00:00", probability: "0.007228", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:01:44.967297+00:00", probability: "0.007505", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:07:40.922682+00:00", probability: "0.012335", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:16:32.368568+00:00", probability: "0.012753", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:22:32.457644+00:00", probability: "0.013604", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:27:02.328365+00:00", probability: "0.013285", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:31:30.766239+00:00", probability: "0.014775", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:37:29.853954+00:00", probability: "0.027131", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:42:03.894288+00:00", probability: "0.024837", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:46:32.499339+00:00", probability: "0.02732", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:52:30.103758+00:00", probability: "0.026152", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:57:02.295932+00:00", probability: "0.02629", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:01:32.388551+00:00", probability: "0.024655", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:07:30.589268+00:00", probability: "0.021662", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:12:02.539866+00:00", probability: "0.026442", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:16:32.509056+00:00", probability: "0.02477", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:22:29.118118+00:00", probability: "0.030221", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:27:02.431908+00:00", probability: "0.016952", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:31:36.176169+00:00", probability: "0.016224", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:37:36.275556+00:00", probability: "0.033887", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:41:10.306614+00:00", probability: "0.030076", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:46:29.373474+00:00", probability: "0.015287", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:52:25.547135+00:00", probability: "0.016148", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:57:02.515905+00:00", probability: "0.013659", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:01:32.475241+00:00", probability: "0.014735", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:07:27.584475+00:00", probability: "0.005196", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:12:09.791890+00:00", probability: "0.006284", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:16:32.467564+00:00", probability: "0.004598", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:22:28.900262+00:00", probability: "0.005424", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:27:02.467693+00:00", probability: "0.005014", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:31:32.355628+00:00", probability: "0.004793", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:42:02.599933+00:00", probability: "0.001265", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:46:32.528698+00:00", probability: "0.003869", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:52:32.323694+00:00", probability: "0.00329", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:57:02.721177+00:00", probability: "0.003509", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:01:32.667681+00:00", probability: "0.003292", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:07:32.604608+00:00", probability: "0.002966", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:12:02.392117+00:00", probability: "0.000922", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:16:32.504599+00:00", probability: "0.000663", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:27:02.372895+00:00", probability: "0.000962", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:31:32.369451+00:00", probability: "0.000561", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:42:02.586740+00:00", probability: "0.00018", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:52:29.927815+00:00", probability: "8e-05", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:46:35.986461+00:00", probability: "0.0002", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:57:02.608225+00:00", probability: "6e-05", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:52:32.921891+00:00", probability: "0.00018", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T07:01:33.168803+00:00", probability: "2e-05", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:02:37.532470+00:00", probability: "0.00018", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:12:00.122315+00:00", probability: "0.000581", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:18:14.003636+00:00", probability: "0.000261", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:21:55.871409+00:00", probability: "0.00016", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:36:48.896569+00:00", probability: "0.000321", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:42:03.732719+00:00", probability: "0.00018", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:02:25.829089+00:00", probability: "0.000402", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:06:47.216580+00:00", probability: "0.00012", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:32:25.929155+00:00", probability: "0.00036", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:36:55.765217+00:00", probability: "0.000565", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:41:50.635611+00:00", probability: "0.000943", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:47:26.043890+00:00", probability: "0.000422", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:51:55.909934+00:00", probability: "0.000722", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:56:18.272058+00:00", probability: "0.000982", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:02:25.797469+00:00", probability: "0.000644", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:06:49.546752+00:00", probability: "0.000948", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:17:26.184322+00:00", probability: "0.000843", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:21:46.781176+00:00", probability: "0.002632", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:27:55.905318+00:00", probability: "0.001829", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:32:26.238967+00:00", probability: "0.001616", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:36:56.174519+00:00", probability: "0.00199", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:41:27.839983+00:00", probability: "0.002337", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:47:26.204894+00:00", probability: "0.00318", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:51:48.376763+00:00", probability: "0.002773", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:56:25.933285+00:00", probability: "0.001182", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:02:26.039667+00:00", probability: "0.000867", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:06:49.491181+00:00", probability: "0.000542", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:11:38.956586+00:00", probability: "0.000282", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:17:26.084407+00:00", probability: "0.0", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T22:08:55.891004+00:00", probability: "0.040733", americanOdds: nil, bookmaker: "consensus"),
        ]),
        GolfClosingRetainedSeries10868(outcomeID: "242242522", name: "Wyndham Clark", eliminated: false, eliminatedAt: nil, history: [
            GolfClosingRetainedPoint10868(timestamp: "2026-10-05T17:39:14.507306+00:00", probability: "0.053783", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-06T13:08:40.644152+00:00", probability: "0.053967", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:02:03.231914+00:00", probability: "0.052477", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:06:33.172825+00:00", probability: "0.055269", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:11:13.058928+00:00", probability: "0.053125", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:16:55.542752+00:00", probability: "0.054196", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:27:33.145591+00:00", probability: "0.057036", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:32:03.148937+00:00", probability: "0.054589", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:36:33.267676+00:00", probability: "0.053449", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:42:33.349212+00:00", probability: "0.055168", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:47:03.467275+00:00", probability: "0.053182", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:51:33.222200+00:00", probability: "0.05084", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:56:03.237230+00:00", probability: "0.054722", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:01:38.226778+00:00", probability: "0.049943", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:06:08.309734+00:00", probability: "0.052183", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:12:08.303481+00:00", probability: "0.050937", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:16:30.062412+00:00", probability: "0.05209", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:21:08.558032+00:00", probability: "0.053035", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:27:08.639061+00:00", probability: "0.049424", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:31:26.916892+00:00", probability: "0.048702", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:36:08.458334+00:00", probability: "0.04518", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:42:08.462936+00:00", probability: "0.048282", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:46:26.904828+00:00", probability: "0.047685", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:51:08.591737+00:00", probability: "0.045534", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:57:08.492012+00:00", probability: "0.044989", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:01:32.422514+00:00", probability: "0.061597", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:06:08.863154+00:00", probability: "0.065196", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:12:08.442006+00:00", probability: "0.06359", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:16:33.390446+00:00", probability: "0.059608", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:21:08.578066+00:00", probability: "0.055819", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:27:08.700847+00:00", probability: "0.057814", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:31:38.648207+00:00", probability: "0.063088", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:36:13.310618+00:00", probability: "0.064178", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:46:29.234103+00:00", probability: "0.056393", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:51:08.598563+00:00", probability: "0.059048", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:57:08.575077+00:00", probability: "0.055988", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:01:38.486948+00:00", probability: "0.05728", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:07:38.415236+00:00", probability: "0.060292", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:12:08.483856+00:00", probability: "0.064961", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:16:38.372037+00:00", probability: "0.070109", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:21:08.495213+00:00", probability: "0.070456", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:27:08.684216+00:00", probability: "0.067303", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:31:38.545519+00:00", probability: "0.066761", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:36:08.436708+00:00", probability: "0.056434", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:42:08.398714+00:00", probability: "0.058766", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:46:38.504366+00:00", probability: "0.063182", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:51:08.444107+00:00", probability: "0.085029", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:57:08.415687+00:00", probability: "0.086711", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:01:38.448606+00:00", probability: "0.087015", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:06:08.459731+00:00", probability: "0.088477", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:12:08.572694+00:00", probability: "0.0914", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:16:38.638257+00:00", probability: "0.060369", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:21:08.445056+00:00", probability: "0.064663", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:27:08.423388+00:00", probability: "0.062758", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:31:38.695212+00:00", probability: "0.062399", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:36:08.476578+00:00", probability: "0.065252", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:42:08.515784+00:00", probability: "0.061777", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:46:38.487589+00:00", probability: "0.062633", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:51:09.005838+00:00", probability: "0.060826", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:57:08.971709+00:00", probability: "0.064061", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:01:39.221294+00:00", probability: "0.063782", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:06:09.189943+00:00", probability: "0.057819", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:12:09.189349+00:00", probability: "0.04638", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:16:39.126639+00:00", probability: "0.048767", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:21:09.103878+00:00", probability: "0.050712", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:27:09.192337+00:00", probability: "0.049382", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:31:39.251792+00:00", probability: "0.049841", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:36:09.226450+00:00", probability: "0.047479", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:42:09.098398+00:00", probability: "0.047671", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:46:39.390867+00:00", probability: "0.04051", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:51:09.148688+00:00", probability: "0.041456", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:57:09.366348+00:00", probability: "0.041592", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:01:30.800138+00:00", probability: "0.044221", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:06:01.132593+00:00", probability: "0.041521", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:12:01.029217+00:00", probability: "0.043346", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:16:30.978149+00:00", probability: "0.043508", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:22:31.080453+00:00", probability: "0.02412", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:27:01.043399+00:00", probability: "0.021869", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:31:30.973790+00:00", probability: "0.024356", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:37:31.205466+00:00", probability: "0.015674", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:42:01.216854+00:00", probability: "0.015796", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:46:31.004456+00:00", probability: "0.015245", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:51:00.993924+00:00", probability: "0.014101", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:57:01.285974+00:00", probability: "0.016758", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T07:01:31.228243+00:00", probability: "0.016329", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T07:07:31.021816+00:00", probability: "0.015359", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:01:54.271593+00:00", probability: "0.016859", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:06:24.569832+00:00", probability: "0.016436", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:11:16.020101+00:00", probability: "0.016704", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:16:54.121527+00:00", probability: "0.015431", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:27:24.299799+00:00", probability: "0.015729", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:31:54.432306+00:00", probability: "0.01629", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:36:24.206129+00:00", probability: "0.015811", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:41:07.477710+00:00", probability: "0.015392", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:46:54.210856+00:00", probability: "0.015837", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:51:24.151362+00:00", probability: "0.015596", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:57:24.059847+00:00", probability: "0.014892", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:01:54.411616+00:00", probability: "0.015665", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:06:24.117663+00:00", probability: "0.014096", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:11:05.714663+00:00", probability: "0.015965", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:16:52.306605+00:00", probability: "0.016303", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:21:24.221027+00:00", probability: "0.008332", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:27:24.425662+00:00", probability: "0.007552", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:31:54.571872+00:00", probability: "0.012704", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:36:24.532871+00:00", probability: "0.011359", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:42:24.709592+00:00", probability: "0.012337", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:46:55.026284+00:00", probability: "0.012569", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:51:24.654444+00:00", probability: "0.011701", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:57:24.715348+00:00", probability: "0.011344", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:01:59.282505+00:00", probability: "0.012878", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:06:24.836570+00:00", probability: "0.013312", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:11:11.909513+00:00", probability: "0.013008", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:16:57.222706+00:00", probability: "0.010897", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:21:24.867456+00:00", probability: "0.020713", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:31:55.452236+00:00", probability: "0.019674", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:36:24.689467+00:00", probability: "0.020148", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:41:20.080252+00:00", probability: "0.018547", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:46:48.365847+00:00", probability: "0.017688", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:51:24.713585+00:00", probability: "0.018419", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:57:24.801333+00:00", probability: "0.017985", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:01:54.854394+00:00", probability: "0.017273", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:06:24.928070+00:00", probability: "0.01861", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:11:12.860871+00:00", probability: "0.017073", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:16:53.653676+00:00", probability: "0.017445", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:21:25.008971+00:00", probability: "0.016801", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:27:24.817660+00:00", probability: "0.006038", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:31:54.901607+00:00", probability: "0.006439", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:36:24.817000+00:00", probability: "0.005635", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:41:13.090598+00:00", probability: "0.009321", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:46:53.727811+00:00", probability: "0.011674", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:51:24.732031+00:00", probability: "0.00846", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:57:24.797035+00:00", probability: "0.007713", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:01:54.833885+00:00", probability: "0.008262", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:06:24.758254+00:00", probability: "0.007754", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:11:15.242501+00:00", probability: "0.002447", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:27:24.789808+00:00", probability: "0.002248", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:31:54.822029+00:00", probability: "0.000682", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:36:24.971616+00:00", probability: "0.000801", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:46:49.098542+00:00", probability: "0.001084", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:51:24.875685+00:00", probability: "0.000744", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:57:24.779033+00:00", probability: "0.002231", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:01:54.933191+00:00", probability: "0.00243", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:12:24.939797+00:00", probability: "0.001344", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:16:54.854142+00:00", probability: "0.001064", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:21:24.981246+00:00", probability: "0.001466", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:32:05.421227+00:00", probability: "0.00032", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:57:25.853387+00:00", probability: "0.00048", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:06:25.056796+00:00", probability: "0.00024", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:31:54.980387+00:00", probability: "0.00042", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:36:24.977474+00:00", probability: "0.00026", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:22:36.878874+00:00", probability: "0.000504", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:31:32.393467+00:00", probability: "0.000261", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:42:02.397711+00:00", probability: "0.000402", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:07:40.922682+00:00", probability: "0.000261", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:11:31.557654+00:00", probability: "0.0004", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:16:32.368568+00:00", probability: "0.0002", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:22:32.457644+00:00", probability: "0.000321", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:31:30.766239+00:00", probability: "0.000442", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:37:29.853954+00:00", probability: "0.00028", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:52:30.103758+00:00", probability: "0.00038", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:01:32.388551+00:00", probability: "0.00014", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:27:02.431908+00:00", probability: "0.0", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T22:08:55.891004+00:00", probability: "0.053967", americanOdds: nil, bookmaker: "consensus"),
        ]),
        GolfClosingRetainedSeries10868(outcomeID: "242242535", name: "Min Woo Lee", eliminated: false, eliminatedAt: nil, history: [
            GolfClosingRetainedPoint10868(timestamp: "2026-10-05T17:39:14.507306+00:00", probability: "0.037017", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-06T13:08:40.644152+00:00", probability: "0.038683", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:02:03.231914+00:00", probability: "0.035632", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:06:33.172825+00:00", probability: "0.036222", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:11:13.058928+00:00", probability: "0.03687", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:16:55.542752+00:00", probability: "0.036142", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:23:03.133505+00:00", probability: "0.038624", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:27:33.145591+00:00", probability: "0.035244", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:32:03.148937+00:00", probability: "0.037116", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:36:33.267676+00:00", probability: "0.032897", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:42:33.349212+00:00", probability: "0.035122", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:47:03.467275+00:00", probability: "0.031813", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:51:33.222200+00:00", probability: "0.033514", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:56:03.237230+00:00", probability: "0.031217", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:01:38.226778+00:00", probability: "0.020824", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:06:08.309734+00:00", probability: "0.021015", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:12:08.303481+00:00", probability: "0.024276", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:16:30.062412+00:00", probability: "0.02206", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:21:08.558032+00:00", probability: "0.021879", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:27:08.639061+00:00", probability: "0.026449", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:31:26.916892+00:00", probability: "0.025205", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:36:08.458334+00:00", probability: "0.02567", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:42:08.462936+00:00", probability: "0.027447", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:46:26.904828+00:00", probability: "0.028431", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:51:08.591737+00:00", probability: "0.028838", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:57:08.492012+00:00", probability: "0.029962", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:01:32.422514+00:00", probability: "0.023447", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:06:08.863154+00:00", probability: "0.021822", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:12:08.442006+00:00", probability: "0.016678", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:16:33.390446+00:00", probability: "0.014888", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:21:08.578066+00:00", probability: "0.015522", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:27:08.700847+00:00", probability: "0.016113", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:31:38.648207+00:00", probability: "0.013183", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:36:13.310618+00:00", probability: "0.014296", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:42:08.507576+00:00", probability: "0.014171", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:46:29.234103+00:00", probability: "0.014049", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:51:08.598563+00:00", probability: "0.015831", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:57:08.575077+00:00", probability: "0.014055", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:07:38.415236+00:00", probability: "0.010794", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:12:08.483856+00:00", probability: "0.020031", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:16:38.372037+00:00", probability: "0.018571", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:21:08.495213+00:00", probability: "0.018264", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:27:08.684216+00:00", probability: "0.019938", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:31:38.545519+00:00", probability: "0.017248", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:36:08.436708+00:00", probability: "0.017783", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:42:08.398714+00:00", probability: "0.018722", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:46:38.504366+00:00", probability: "0.020238", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:51:08.444107+00:00", probability: "0.019141", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:57:08.415687+00:00", probability: "0.023119", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:01:38.448606+00:00", probability: "0.022747", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:06:08.459731+00:00", probability: "0.02368", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:12:08.572694+00:00", probability: "0.020967", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:21:08.445056+00:00", probability: "0.021941", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:27:08.423388+00:00", probability: "0.020335", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:31:38.695212+00:00", probability: "0.023342", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:36:08.476578+00:00", probability: "0.02366", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:42:08.515784+00:00", probability: "0.023372", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:46:38.487589+00:00", probability: "0.023549", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:51:09.005838+00:00", probability: "0.020994", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:57:08.971709+00:00", probability: "0.03363", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:01:39.221294+00:00", probability: "0.031007", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:06:09.189943+00:00", probability: "0.030325", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:12:09.189349+00:00", probability: "0.041797", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:16:39.126639+00:00", probability: "0.041412", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:21:09.103878+00:00", probability: "0.042756", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:27:09.192337+00:00", probability: "0.042245", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:31:39.251792+00:00", probability: "0.043752", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:36:09.226450+00:00", probability: "0.042898", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:46:39.390867+00:00", probability: "0.041791", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:51:09.148688+00:00", probability: "0.042394", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:57:09.366348+00:00", probability: "0.041414", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:01:30.800138+00:00", probability: "0.04349", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:06:01.132593+00:00", probability: "0.042131", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:12:01.029217+00:00", probability: "0.040335", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:16:30.978149+00:00", probability: "0.043053", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:22:31.080453+00:00", probability: "0.043974", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:27:01.043399+00:00", probability: "0.042219", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:31:30.973790+00:00", probability: "0.043223", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:37:31.205466+00:00", probability: "0.043485", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:42:01.216854+00:00", probability: "0.045001", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:46:31.004456+00:00", probability: "0.042085", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:51:00.993924+00:00", probability: "0.044802", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:57:01.285974+00:00", probability: "0.04349", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T07:01:31.228243+00:00", probability: "0.043626", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T07:07:31.021816+00:00", probability: "0.044299", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:01:54.271593+00:00", probability: "0.042931", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:06:24.569832+00:00", probability: "0.042619", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:11:16.020101+00:00", probability: "0.04412", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:16:54.121527+00:00", probability: "0.043581", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:21:24.361544+00:00", probability: "0.043922", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:27:24.299799+00:00", probability: "0.043267", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:31:54.432306+00:00", probability: "0.042639", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:36:24.206129+00:00", probability: "0.043087", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:41:07.477710+00:00", probability: "0.046219", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:46:54.210856+00:00", probability: "0.044506", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:51:24.151362+00:00", probability: "0.044234", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:57:24.059847+00:00", probability: "0.042557", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:01:54.411616+00:00", probability: "0.042321", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:06:24.117663+00:00", probability: "0.043216", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:11:05.714663+00:00", probability: "0.04858", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:16:52.306605+00:00", probability: "0.047605", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:21:24.221027+00:00", probability: "0.044419", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:27:24.425662+00:00", probability: "0.047529", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:31:54.571872+00:00", probability: "0.048336", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:36:24.532871+00:00", probability: "0.045351", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:46:55.026284+00:00", probability: "0.044828", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:51:24.654444+00:00", probability: "0.045579", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:57:24.715348+00:00", probability: "0.025173", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:06:24.836570+00:00", probability: "0.02211", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:11:11.909513+00:00", probability: "0.023298", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:16:57.222706+00:00", probability: "0.023814", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:21:24.867456+00:00", probability: "0.021817", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:27:24.676035+00:00", probability: "0.022792", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:31:55.452236+00:00", probability: "0.026192", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:36:24.689467+00:00", probability: "0.027161", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:41:20.080252+00:00", probability: "0.028417", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:46:48.365847+00:00", probability: "0.025561", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:51:24.713585+00:00", probability: "0.038098", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:57:24.801333+00:00", probability: "0.034374", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:01:54.854394+00:00", probability: "0.036696", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:06:24.928070+00:00", probability: "0.041499", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:11:12.860871+00:00", probability: "0.040006", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:16:53.653676+00:00", probability: "0.036515", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:27:24.817660+00:00", probability: "0.03997", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:31:54.901607+00:00", probability: "0.056841", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:36:24.817000+00:00", probability: "0.058189", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:41:13.090598+00:00", probability: "0.05874", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:46:53.727811+00:00", probability: "0.05837", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:51:24.732031+00:00", probability: "0.032275", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:01:54.833885+00:00", probability: "0.030392", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:06:24.758254+00:00", probability: "0.032049", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:11:15.242501+00:00", probability: "0.029858", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:16:54.757109+00:00", probability: "0.029415", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:21:24.742441+00:00", probability: "0.029667", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:27:24.789808+00:00", probability: "0.029409", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:31:54.822029+00:00", probability: "0.032627", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:36:24.971616+00:00", probability: "0.033631", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:41:09.040738+00:00", probability: "0.033426", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:46:49.098542+00:00", probability: "0.051726", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:51:24.875685+00:00", probability: "0.050193", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:57:24.779033+00:00", probability: "0.056791", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:01:54.933191+00:00", probability: "0.045155", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:06:25.123480+00:00", probability: "0.046562", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:12:24.939797+00:00", probability: "0.042805", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:16:54.854142+00:00", probability: "0.044335", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:21:24.981246+00:00", probability: "0.043468", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:27:25.121923+00:00", probability: "0.044981", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:32:05.421227+00:00", probability: "0.043083", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:36:24.993990+00:00", probability: "0.062098", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:42:24.976809+00:00", probability: "0.065244", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:46:54.961700+00:00", probability: "0.064725", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:51:24.941083+00:00", probability: "0.062476", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:57:25.853387+00:00", probability: "0.063127", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:01:55.007660+00:00", probability: "0.061062", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:06:25.056796+00:00", probability: "0.058274", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:12:24.917957+00:00", probability: "0.058437", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:16:55.057037+00:00", probability: "0.059436", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:21:25.519889+00:00", probability: "0.062217", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:27:25.086697+00:00", probability: "0.062714", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:31:54.980387+00:00", probability: "0.063243", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:36:24.977474+00:00", probability: "0.062131", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:42:43.024481+00:00", probability: "0.070469", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:46:54.836301+00:00", probability: "0.071641", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:51:25.119887+00:00", probability: "0.06665", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:57:24.994475+00:00", probability: "0.068996", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T07:01:55.134023+00:00", probability: "0.06651", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T07:06:24.990357+00:00", probability: "0.069569", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T07:12:24.978448+00:00", probability: "0.068056", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T11:03:25.396420+00:00", probability: "0.068396", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:01:32.121700+00:00", probability: "0.069267", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:07:32.296237+00:00", probability: "0.068772", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:12:02.146122+00:00", probability: "0.06934", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:16:38.233711+00:00", probability: "0.068209", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:22:36.878874+00:00", probability: "0.066453", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:27:02.254196+00:00", probability: "0.067129", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:31:32.393467+00:00", probability: "0.067713", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:37:36.325422+00:00", probability: "0.068889", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:42:02.397711+00:00", probability: "0.067154", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:46:32.201718+00:00", probability: "0.065373", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:52:32.230383+00:00", probability: "0.067728", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:57:02.292294+00:00", probability: "0.066553", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:01:44.967297+00:00", probability: "0.07166", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:07:40.922682+00:00", probability: "0.067685", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:11:31.557654+00:00", probability: "0.067317", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:16:32.368568+00:00", probability: "0.0679", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:27:02.328365+00:00", probability: "0.06909", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:31:30.766239+00:00", probability: "0.061262", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:37:29.853954+00:00", probability: "0.056679", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:42:03.894288+00:00", probability: "0.056275", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:46:32.499339+00:00", probability: "0.053857", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:52:30.103758+00:00", probability: "0.056347", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:57:02.295932+00:00", probability: "0.05273", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:01:32.388551+00:00", probability: "0.051465", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:07:30.589268+00:00", probability: "0.050277", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:12:02.539866+00:00", probability: "0.05715", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:16:32.509056+00:00", probability: "0.055553", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:22:29.118118+00:00", probability: "0.058918", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:27:02.431908+00:00", probability: "0.059115", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:31:36.176169+00:00", probability: "0.038796", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:37:36.275556+00:00", probability: "0.04112", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:41:10.306614+00:00", probability: "0.037625", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:46:29.373474+00:00", probability: "0.037968", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:52:25.547135+00:00", probability: "0.038597", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:57:02.515905+00:00", probability: "0.029289", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:01:32.475241+00:00", probability: "0.030546", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:07:27.584475+00:00", probability: "0.030267", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:12:09.791890+00:00", probability: "0.017982", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:16:32.467564+00:00", probability: "0.018877", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:22:28.900262+00:00", probability: "0.021374", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:27:02.467693+00:00", probability: "0.01995", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:31:32.355628+00:00", probability: "0.019539", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:37:24.925694+00:00", probability: "0.017765", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:42:02.599933+00:00", probability: "0.01822", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:46:32.528698+00:00", probability: "0.017853", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:52:32.323694+00:00", probability: "0.016367", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:57:02.721177+00:00", probability: "0.013559", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:01:32.667681+00:00", probability: "0.014251", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:07:32.604608+00:00", probability: "0.014829", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:12:02.392117+00:00", probability: "0.014553", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:22:29.559191+00:00", probability: "0.011184", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:27:02.372895+00:00", probability: "0.012545", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:31:32.369451+00:00", probability: "0.006045", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:37:32.480772+00:00", probability: "0.004623", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:42:02.586740+00:00", probability: "0.003539", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:46:32.643579+00:00", probability: "0.003219", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:52:29.927815+00:00", probability: "0.001239", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:57:02.421912+00:00", probability: "0.000719", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:01:29.696997+00:00", probability: "0.001999", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:07:35.495038+00:00", probability: "0.001879", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:12:29.682303+00:00", probability: "0.001219", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:22:32.710013+00:00", probability: "0.001118", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:37:32.795010+00:00", probability: "0.001301", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:42:02.797854+00:00", probability: "0.00184", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:46:35.986461+00:00", probability: "0.00146", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:52:32.606932+00:00", probability: "0.000857", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:57:02.608225+00:00", probability: "0.001382", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:01:32.642953+00:00", probability: "0.000998", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:07:32.662386+00:00", probability: "0.000457", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:12:02.573288+00:00", probability: "0.00082", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:27:02.942302+00:00", probability: "0.00096", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:31:32.642402+00:00", probability: "0.001098", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:37:32.753311+00:00", probability: "0.001299", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:41:27.690470+00:00", probability: "0.00148", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:46:46.608343+00:00", probability: "0.001059", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:52:32.921891+00:00", probability: "0.001238", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:57:03.118947+00:00", probability: "0.001022", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T07:01:33.168803+00:00", probability: "0.0012", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T07:07:32.955805+00:00", probability: "0.001462", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T11:22:35.155437+00:00", probability: "0.001237", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:18:14.003636+00:00", probability: "0.001519", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:27:46.592637+00:00", probability: "0.001179", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:32:25.882164+00:00", probability: "0.002819", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:36:48.896569+00:00", probability: "0.002241", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:47:42.984192+00:00", probability: "0.001901", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:51:54.681637+00:00", probability: "0.001624", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:56:25.710971+00:00", probability: "0.001763", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:02:25.829089+00:00", probability: "0.003163", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:06:47.216580+00:00", probability: "0.002623", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:11:25.894787+00:00", probability: "0.002884", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:17:25.996026+00:00", probability: "0.002644", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:21:51.113011+00:00", probability: "0.003308", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:27:55.889037+00:00", probability: "0.003986", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:32:25.929155+00:00", probability: "0.005909", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:36:55.765217+00:00", probability: "0.005252", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:41:50.635611+00:00", probability: "0.00633", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:47:26.043890+00:00", probability: "0.005388", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:51:55.909934+00:00", probability: "0.005189", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:56:18.272058+00:00", probability: "0.006033", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:02:25.797469+00:00", probability: "0.006936", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:06:49.546752+00:00", probability: "0.010128", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:11:25.914867+00:00", probability: "0.01098", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:17:26.184322+00:00", probability: "0.008482", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:21:46.781176+00:00", probability: "0.007771", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:27:55.905318+00:00", probability: "0.007154", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:32:26.238967+00:00", probability: "0.006873", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:36:56.174519+00:00", probability: "0.004866", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:41:27.839983+00:00", probability: "0.006755", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:47:26.204894+00:00", probability: "0.004999", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:56:25.933285+00:00", probability: "0.002753", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:02:26.039667+00:00", probability: "0.001084", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:06:49.491181+00:00", probability: "0.001721", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:11:38.956586+00:00", probability: "0.000924", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:17:26.084407+00:00", probability: "0.000642", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:21:48.518176+00:00", probability: "0.000822", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:27:57.815530+00:00", probability: "0.000563", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:36:56.232276+00:00", probability: "0.000682", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:47:26.160310+00:00", probability: "0.000262", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:06:56.215374+00:00", probability: "0.000481", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:11:37.607125+00:00", probability: "0.000322", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:17:26.043707+00:00", probability: "0.000444", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:21:56.168662+00:00", probability: "0.000662", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:27:55.803030+00:00", probability: "4e-05", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:32:25.858478+00:00", probability: "0.00022", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:41:25.968157+00:00", probability: "0.000462", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:47:26.137402+00:00", probability: "0.000262", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:51:49.540257+00:00", probability: "1.9e-05", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:56:26.068260+00:00", probability: "0.000161", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:06:48.547245+00:00", probability: "0.0", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T22:08:55.891004+00:00", probability: "0.038683", americanOdds: nil, bookmaker: "consensus"),
        ]),
        GolfClosingRetainedSeries10868(outcomeID: "242242528", name: "Justin Thomas", eliminated: false, eliminatedAt: nil, history: [
            GolfClosingRetainedPoint10868(timestamp: "2026-10-05T17:39:14.507306+00:00", probability: "0.042083", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-06T13:08:40.644152+00:00", probability: "0.042317", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:02:03.231914+00:00", probability: "0.041227", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:06:33.172825+00:00", probability: "0.042028", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:11:13.058928+00:00", probability: "0.041099", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:16:55.542752+00:00", probability: "0.03846", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:23:03.133505+00:00", probability: "0.041863", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:27:33.145591+00:00", probability: "0.043609", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:32:03.148937+00:00", probability: "0.041639", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:42:33.349212+00:00", probability: "0.04088", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:47:03.467275+00:00", probability: "0.04237", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:51:33.222200+00:00", probability: "0.040235", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:56:03.237230+00:00", probability: "0.038687", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:01:38.226778+00:00", probability: "0.039542", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:06:08.309734+00:00", probability: "0.040233", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:12:08.303481+00:00", probability: "0.038334", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:16:30.062412+00:00", probability: "0.039457", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:21:08.558032+00:00", probability: "0.035861", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:27:08.639061+00:00", probability: "0.034963", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:31:26.916892+00:00", probability: "0.036157", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:36:08.458334+00:00", probability: "0.033955", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:42:08.462936+00:00", probability: "0.036086", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:46:26.904828+00:00", probability: "0.036207", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:51:08.591737+00:00", probability: "0.034686", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:57:08.492012+00:00", probability: "0.034244", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:01:32.422514+00:00", probability: "0.03326", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:06:08.863154+00:00", probability: "0.031206", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:12:08.442006+00:00", probability: "0.032056", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:16:33.390446+00:00", probability: "0.032223", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:21:08.578066+00:00", probability: "0.028304", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:27:08.700847+00:00", probability: "0.028736", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:31:38.648207+00:00", probability: "0.031536", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:36:13.310618+00:00", probability: "0.032823", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:42:08.507576+00:00", probability: "0.032588", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:46:29.234103+00:00", probability: "0.032482", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:51:08.598563+00:00", probability: "0.029371", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:57:08.575077+00:00", probability: "0.027758", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:01:38.486948+00:00", probability: "0.029369", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:07:38.415236+00:00", probability: "0.028276", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:12:08.483856+00:00", probability: "0.019997", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:16:38.372037+00:00", probability: "0.022859", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:21:08.495213+00:00", probability: "0.021705", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:27:08.684216+00:00", probability: "0.020844", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:31:38.545519+00:00", probability: "0.02042", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:36:08.436708+00:00", probability: "0.027353", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:42:08.398714+00:00", probability: "0.029291", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:46:38.504366+00:00", probability: "0.031098", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:51:08.444107+00:00", probability: "0.026442", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:01:38.448606+00:00", probability: "0.028334", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:06:08.459731+00:00", probability: "0.02849", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:12:08.572694+00:00", probability: "0.016722", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:16:38.638257+00:00", probability: "0.019681", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:21:08.445056+00:00", probability: "0.020408", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:27:08.423388+00:00", probability: "0.020053", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:31:38.695212+00:00", probability: "0.018881", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:36:08.476578+00:00", probability: "0.020026", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:42:08.515784+00:00", probability: "0.018014", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:46:38.487589+00:00", probability: "0.019055", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:51:09.005838+00:00", probability: "0.017649", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:57:08.971709+00:00", probability: "0.018177", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:01:39.221294+00:00", probability: "0.019647", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:06:09.189943+00:00", probability: "0.016958", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:12:09.189349+00:00", probability: "0.022635", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:16:39.126639+00:00", probability: "0.023787", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:21:09.103878+00:00", probability: "0.023932", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:27:09.192337+00:00", probability: "0.024286", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:31:39.251792+00:00", probability: "0.023939", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:36:09.226450+00:00", probability: "0.022154", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:42:09.098398+00:00", probability: "0.019948", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:46:39.390867+00:00", probability: "0.018807", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:51:09.148688+00:00", probability: "0.018299", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:57:09.366348+00:00", probability: "0.012904", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:01:30.800138+00:00", probability: "0.012561", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:06:01.132593+00:00", probability: "0.012219", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:12:01.029217+00:00", probability: "0.011467", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:16:30.978149+00:00", probability: "0.010656", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:22:31.080453+00:00", probability: "0.011588", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:27:01.043399+00:00", probability: "0.009535", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:31:30.973790+00:00", probability: "0.010347", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:37:31.205466+00:00", probability: "0.020152", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:42:01.216854+00:00", probability: "0.020291", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:46:31.004456+00:00", probability: "0.01946", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:51:00.993924+00:00", probability: "0.021031", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:57:01.285974+00:00", probability: "0.021251", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T07:01:31.228243+00:00", probability: "0.020388", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T07:07:31.021816+00:00", probability: "0.020808", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:01:54.271593+00:00", probability: "0.021765", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:06:24.569832+00:00", probability: "0.022797", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:11:16.020101+00:00", probability: "0.021407", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:21:24.361544+00:00", probability: "0.019933", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:27:24.299799+00:00", probability: "0.020795", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:31:54.432306+00:00", probability: "0.02198", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:36:24.206129+00:00", probability: "0.019306", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:41:07.477710+00:00", probability: "0.019853", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:46:54.210856+00:00", probability: "0.018776", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:51:24.151362+00:00", probability: "0.019139", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:57:24.059847+00:00", probability: "0.018627", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:01:54.411616+00:00", probability: "0.019685", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:06:24.117663+00:00", probability: "0.019267", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:11:05.714663+00:00", probability: "0.020555", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:16:52.306605+00:00", probability: "0.020708", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:21:24.221027+00:00", probability: "0.018027", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:27:24.425662+00:00", probability: "0.019773", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:36:24.532871+00:00", probability: "0.027214", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:42:24.709592+00:00", probability: "0.02734", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:46:55.026284+00:00", probability: "0.028701", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:51:24.654444+00:00", probability: "0.027324", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:57:24.715348+00:00", probability: "0.026758", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:01:59.282505+00:00", probability: "0.027211", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:06:24.836570+00:00", probability: "0.030621", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:11:11.909513+00:00", probability: "0.027632", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:16:57.222706+00:00", probability: "0.028452", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:21:24.867456+00:00", probability: "0.02558", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:27:24.676035+00:00", probability: "0.026545", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:31:55.452236+00:00", probability: "0.025492", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:36:24.689467+00:00", probability: "0.026827", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:41:20.080252+00:00", probability: "0.023857", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:46:48.365847+00:00", probability: "0.024683", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:57:24.801333+00:00", probability: "0.022098", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:01:54.854394+00:00", probability: "0.040299", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:06:24.928070+00:00", probability: "0.039598", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:11:12.860871+00:00", probability: "0.036239", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:16:53.653676+00:00", probability: "0.037538", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:21:25.008971+00:00", probability: "0.040534", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:27:24.817660+00:00", probability: "0.043596", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:31:54.901607+00:00", probability: "0.045198", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:36:24.817000+00:00", probability: "0.045617", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:41:13.090598+00:00", probability: "0.043676", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:46:53.727811+00:00", probability: "0.04711", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:51:24.732031+00:00", probability: "0.039677", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:57:24.797035+00:00", probability: "0.036351", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:01:54.833885+00:00", probability: "0.037459", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:06:24.758254+00:00", probability: "0.037154", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:11:15.242501+00:00", probability: "0.038706", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:16:54.757109+00:00", probability: "0.043246", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:21:24.742441+00:00", probability: "0.045284", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:27:24.789808+00:00", probability: "0.044528", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:31:54.822029+00:00", probability: "0.039395", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:41:09.040738+00:00", probability: "0.038532", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:46:49.098542+00:00", probability: "0.04272", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:51:24.875685+00:00", probability: "0.041762", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:57:24.779033+00:00", probability: "0.048197", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:01:54.933191+00:00", probability: "0.043091", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:06:25.123480+00:00", probability: "0.043452", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:12:24.939797+00:00", probability: "0.058192", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:16:54.854142+00:00", probability: "0.05546", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:21:24.981246+00:00", probability: "0.06025", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:27:25.121923+00:00", probability: "0.062062", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:32:05.421227+00:00", probability: "0.086966", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:36:24.993990+00:00", probability: "0.082776", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:42:24.976809+00:00", probability: "0.085265", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:46:54.961700+00:00", probability: "0.081256", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:51:24.941083+00:00", probability: "0.079693", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:57:25.853387+00:00", probability: "0.074485", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:01:55.007660+00:00", probability: "0.07172", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:06:25.056796+00:00", probability: "0.072463", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:12:24.917957+00:00", probability: "0.071085", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:16:55.057037+00:00", probability: "0.073486", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:21:25.519889+00:00", probability: "0.076708", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:27:25.086697+00:00", probability: "0.077839", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:31:54.980387+00:00", probability: "0.075805", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:36:24.977474+00:00", probability: "0.076754", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:42:43.024481+00:00", probability: "0.077621", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:51:25.119887+00:00", probability: "0.075973", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:57:24.994475+00:00", probability: "0.074845", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T07:01:55.134023+00:00", probability: "0.075416", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T07:06:24.990357+00:00", probability: "0.073309", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T07:12:24.978448+00:00", probability: "0.076185", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T11:03:25.396420+00:00", probability: "0.078001", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:01:32.121700+00:00", probability: "0.075574", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:07:32.296237+00:00", probability: "0.07374", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:12:02.146122+00:00", probability: "0.07546", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:16:38.233711+00:00", probability: "0.075145", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:22:36.878874+00:00", probability: "0.076596", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:27:02.254196+00:00", probability: "0.078024", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:31:32.393467+00:00", probability: "0.074655", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:37:36.325422+00:00", probability: "0.073078", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:42:02.397711+00:00", probability: "0.074488", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:46:32.201718+00:00", probability: "0.073016", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:52:32.230383+00:00", probability: "0.074133", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:57:02.292294+00:00", probability: "0.074581", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:01:44.967297+00:00", probability: "0.075177", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:07:40.922682+00:00", probability: "0.076668", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:11:31.557654+00:00", probability: "0.075091", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:16:32.368568+00:00", probability: "0.077502", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:22:32.457644+00:00", probability: "0.075404", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:27:02.328365+00:00", probability: "0.074869", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:31:30.766239+00:00", probability: "0.068215", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:37:29.853954+00:00", probability: "0.066277", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:42:03.894288+00:00", probability: "0.061708", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:46:32.499339+00:00", probability: "0.058501", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:52:30.103758+00:00", probability: "0.063482", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:57:02.295932+00:00", probability: "0.059738", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:01:32.388551+00:00", probability: "0.058087", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:07:30.589268+00:00", probability: "0.055257", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:12:02.539866+00:00", probability: "0.059852", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:16:32.509056+00:00", probability: "0.06033", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:22:29.118118+00:00", probability: "0.066751", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:27:02.431908+00:00", probability: "0.067709", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:31:36.176169+00:00", probability: "0.076874", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:46:29.373474+00:00", probability: "0.072938", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:52:25.547135+00:00", probability: "0.075205", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:57:02.515905+00:00", probability: "0.103458", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:01:32.475241+00:00", probability: "0.109472", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:07:27.584475+00:00", probability: "0.105134", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:12:09.791890+00:00", probability: "0.118859", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:16:32.467564+00:00", probability: "0.125989", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:22:28.900262+00:00", probability: "0.132498", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:27:02.467693+00:00", probability: "0.129856", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:31:32.355628+00:00", probability: "0.123837", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:37:24.925694+00:00", probability: "0.189081", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:42:02.599933+00:00", probability: "0.194152", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:46:32.528698+00:00", probability: "0.190104", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:52:32.323694+00:00", probability: "0.114408", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:57:02.721177+00:00", probability: "0.174392", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:01:32.667681+00:00", probability: "0.172301", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:07:32.604608+00:00", probability: "0.184465", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:12:02.392117+00:00", probability: "0.18043", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:16:32.504599+00:00", probability: "0.1767", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:22:29.559191+00:00", probability: "0.155469", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:27:02.372895+00:00", probability: "0.15747", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:31:32.369451+00:00", probability: "0.179562", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:37:32.480772+00:00", probability: "0.145852", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:42:02.586740+00:00", probability: "0.128721", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:46:32.643579+00:00", probability: "0.125803", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:52:29.927815+00:00", probability: "0.117246", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:57:02.421912+00:00", probability: "0.113376", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:01:29.696997+00:00", probability: "0.117857", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:07:35.495038+00:00", probability: "0.120146", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:12:29.682303+00:00", probability: "0.162402", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:16:32.524509+00:00", probability: "0.143815", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:22:32.710013+00:00", probability: "0.14107", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:27:02.718901+00:00", probability: "0.138427", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:31:32.787975+00:00", probability: "0.143701", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:42:02.797854+00:00", probability: "0.167417", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:46:35.986461+00:00", probability: "0.147423", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:52:32.606932+00:00", probability: "0.14755", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:57:02.608225+00:00", probability: "0.151218", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:01:32.642953+00:00", probability: "0.153087", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:07:32.662386+00:00", probability: "0.14656", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:12:02.573288+00:00", probability: "0.144792", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:16:33.417463+00:00", probability: "0.076839", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:22:32.896568+00:00", probability: "0.089139", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:27:02.942302+00:00", probability: "0.089529", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:31:32.642402+00:00", probability: "0.100454", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:37:32.753311+00:00", probability: "0.107959", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:41:27.690470+00:00", probability: "0.109987", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:46:46.608343+00:00", probability: "0.109098", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:52:32.921891+00:00", probability: "0.10836", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:57:03.118947+00:00", probability: "0.110126", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T07:01:33.168803+00:00", probability: "0.123009", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T07:07:32.955805+00:00", probability: "0.119975", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T11:22:35.155437+00:00", probability: "0.122502", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:02:37.532470+00:00", probability: "0.121332", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:07:07.544047+00:00", probability: "0.1226", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:12:00.122315+00:00", probability: "0.122078", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:21:55.871409+00:00", probability: "0.123357", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:27:46.592637+00:00", probability: "0.124101", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:32:25.882164+00:00", probability: "0.125004", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:36:48.896569+00:00", probability: "0.122475", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:42:03.732719+00:00", probability: "0.121761", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:47:42.984192+00:00", probability: "0.125082", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:51:54.681637+00:00", probability: "0.120952", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:56:25.710971+00:00", probability: "0.120637", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:02:25.829089+00:00", probability: "0.122409", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:06:47.216580+00:00", probability: "0.119126", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:11:25.894787+00:00", probability: "0.123028", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:17:25.996026+00:00", probability: "0.125649", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:21:51.113011+00:00", probability: "0.128012", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:27:55.889037+00:00", probability: "0.126452", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:32:25.929155+00:00", probability: "0.0226", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:36:55.765217+00:00", probability: "0.022301", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:41:50.635611+00:00", probability: "0.024921", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:47:26.043890+00:00", probability: "0.020652", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:51:55.909934+00:00", probability: "0.021026", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:56:18.272058+00:00", probability: "0.016201", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:02:25.797469+00:00", probability: "0.017", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:06:49.546752+00:00", probability: "0.021728", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:11:25.914867+00:00", probability: "0.020808", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:17:26.184322+00:00", probability: "0.01946", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:21:46.781176+00:00", probability: "0.019774", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:27:55.905318+00:00", probability: "0.024016", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:32:26.238967+00:00", probability: "0.023869", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:36:56.174519+00:00", probability: "0.023736", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:41:27.839983+00:00", probability: "0.026622", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:47:26.204894+00:00", probability: "0.028065", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:51:48.376763+00:00", probability: "0.026541", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:56:25.933285+00:00", probability: "0.017179", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:02:26.039667+00:00", probability: "0.017907", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:06:49.491181+00:00", probability: "0.005474", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:11:38.956586+00:00", probability: "0.002935", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:17:26.084407+00:00", probability: "0.002354", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:21:48.518176+00:00", probability: "0.002533", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:32:25.820139+00:00", probability: "0.002429", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:36:56.232276+00:00", probability: "0.00203", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:41:25.890612+00:00", probability: "0.001747", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:47:26.160310+00:00", probability: "0.001587", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:51:50.533672+00:00", probability: "0.001226", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:02:26.587145+00:00", probability: "0.000621", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:17:26.043707+00:00", probability: "0.000762", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:21:56.168662+00:00", probability: "0.001288", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:27:55.803030+00:00", probability: "0.000886", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:32:25.858478+00:00", probability: "0.001262", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:36:56.195550+00:00", probability: "0.001483", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:41:25.968157+00:00", probability: "6e-05", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T22:08:55.891004+00:00", probability: "0.042317", americanOdds: nil, bookmaker: "consensus"),
        ]),
        GolfClosingRetainedSeries10868(outcomeID: "242242520", name: "Xander Schauffele", eliminated: false, eliminatedAt: nil, history: [
            GolfClosingRetainedPoint10868(timestamp: "2026-10-05T17:39:14.507306+00:00", probability: "0.089", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-06T13:08:40.644152+00:00", probability: "0.086583", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:02:03.231914+00:00", probability: "0.084473", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:06:33.172825+00:00", probability: "0.090287", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:11:13.058928+00:00", probability: "0.087947", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:16:55.542752+00:00", probability: "0.089341", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:23:03.133505+00:00", probability: "0.087687", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:27:33.145591+00:00", probability: "0.090256", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:32:03.148937+00:00", probability: "0.089011", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:36:33.267676+00:00", probability: "0.089834", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:42:33.349212+00:00", probability: "0.0919", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:47:03.467275+00:00", probability: "0.115002", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:51:33.222200+00:00", probability: "0.111329", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:56:03.237230+00:00", probability: "0.111221", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:01:38.226778+00:00", probability: "0.114425", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:06:08.309734+00:00", probability: "0.114726", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:12:08.303481+00:00", probability: "0.118509", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:16:30.062412+00:00", probability: "0.11657", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:21:08.558032+00:00", probability: "0.116169", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:27:08.639061+00:00", probability: "0.160178", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:31:26.916892+00:00", probability: "0.160471", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:36:08.458334+00:00", probability: "0.1602", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:42:08.462936+00:00", probability: "0.14433", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:46:26.904828+00:00", probability: "0.142725", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:51:08.591737+00:00", probability: "0.145432", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:57:08.492012+00:00", probability: "0.137534", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:01:32.422514+00:00", probability: "0.142239", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:06:08.863154+00:00", probability: "0.139947", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:12:08.442006+00:00", probability: "0.125048", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:16:33.390446+00:00", probability: "0.121193", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:21:08.578066+00:00", probability: "0.088455", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:27:08.700847+00:00", probability: "0.087233", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:31:38.648207+00:00", probability: "0.083536", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:36:13.310618+00:00", probability: "0.087832", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:42:08.507576+00:00", probability: "0.083744", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:46:29.234103+00:00", probability: "0.084936", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:51:08.598563+00:00", probability: "0.085271", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:57:08.575077+00:00", probability: "0.081213", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:01:38.486948+00:00", probability: "0.084551", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:07:38.415236+00:00", probability: "0.083523", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:12:08.483856+00:00", probability: "0.082963", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:16:38.372037+00:00", probability: "0.085172", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:21:08.495213+00:00", probability: "0.075502", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:27:08.684216+00:00", probability: "0.075068", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:31:38.545519+00:00", probability: "0.076701", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:36:08.436708+00:00", probability: "0.067438", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:42:08.398714+00:00", probability: "0.065647", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:46:38.504366+00:00", probability: "0.072096", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:51:08.444107+00:00", probability: "0.067341", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:57:08.415687+00:00", probability: "0.068126", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:01:38.448606+00:00", probability: "0.073825", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:06:08.459731+00:00", probability: "0.051775", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:12:08.572694+00:00", probability: "0.054268", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:16:38.638257+00:00", probability: "0.055573", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:21:08.445056+00:00", probability: "0.031712", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:31:38.695212+00:00", probability: "0.029744", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:36:08.476578+00:00", probability: "0.029279", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:42:08.515784+00:00", probability: "0.033229", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:46:38.487589+00:00", probability: "0.033466", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:51:09.005838+00:00", probability: "0.030539", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:57:08.971709+00:00", probability: "0.030731", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:01:39.221294+00:00", probability: "0.032539", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:06:09.189943+00:00", probability: "0.014877", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:12:09.189349+00:00", probability: "0.015032", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:16:39.126639+00:00", probability: "0.013723", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:21:09.103878+00:00", probability: "0.022021", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:27:09.192337+00:00", probability: "0.021245", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:31:39.251792+00:00", probability: "0.020846", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:36:09.226450+00:00", probability: "0.021232", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:42:09.098398+00:00", probability: "0.022514", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:46:39.390867+00:00", probability: "0.021122", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:51:09.148688+00:00", probability: "0.020325", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:57:09.366348+00:00", probability: "0.022445", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:01:30.800138+00:00", probability: "0.022747", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:06:01.132593+00:00", probability: "0.020885", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:12:01.029217+00:00", probability: "0.021027", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:16:30.978149+00:00", probability: "0.021387", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:22:31.080453+00:00", probability: "0.022011", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:27:01.043399+00:00", probability: "0.020009", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:31:30.973790+00:00", probability: "0.021857", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:37:31.205466+00:00", probability: "0.021721", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:42:01.216854+00:00", probability: "0.023125", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:46:31.004456+00:00", probability: "0.020731", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:51:00.993924+00:00", probability: "0.021009", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:57:01.285974+00:00", probability: "0.022282", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T07:01:31.228243+00:00", probability: "0.022484", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T07:07:31.021816+00:00", probability: "0.021285", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:01:54.271593+00:00", probability: "0.022474", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:06:24.569832+00:00", probability: "0.021344", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:11:16.020101+00:00", probability: "0.023106", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:16:54.121527+00:00", probability: "0.020985", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:21:24.361544+00:00", probability: "0.023005", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:27:24.299799+00:00", probability: "0.02156", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:31:54.432306+00:00", probability: "0.022277", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:36:24.206129+00:00", probability: "0.021807", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:41:07.477710+00:00", probability: "0.022256", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:46:54.210856+00:00", probability: "0.022398", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:57:24.059847+00:00", probability: "0.020581", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:01:54.411616+00:00", probability: "0.021853", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:06:24.117663+00:00", probability: "0.021609", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:11:05.714663+00:00", probability: "0.022851", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:16:52.306605+00:00", probability: "0.023299", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:21:24.221027+00:00", probability: "0.022435", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:27:24.425662+00:00", probability: "0.02348", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:31:54.571872+00:00", probability: "0.024683", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:36:24.532871+00:00", probability: "0.023221", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:42:24.709592+00:00", probability: "0.024717", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:46:55.026284+00:00", probability: "0.024123", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:51:24.654444+00:00", probability: "0.013548", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:57:24.715348+00:00", probability: "0.012906", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:01:59.282505+00:00", probability: "0.014", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:06:24.836570+00:00", probability: "0.020734", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:11:11.909513+00:00", probability: "0.02023", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:16:57.222706+00:00", probability: "0.017859", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:21:24.867456+00:00", probability: "0.016704", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:27:24.676035+00:00", probability: "0.018495", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:31:55.452236+00:00", probability: "0.017907", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:36:24.689467+00:00", probability: "0.017164", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:41:20.080252+00:00", probability: "0.021452", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:46:48.365847+00:00", probability: "0.020218", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:51:24.713585+00:00", probability: "0.021381", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:57:24.801333+00:00", probability: "0.019507", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:01:54.854394+00:00", probability: "0.020319", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:06:24.928070+00:00", probability: "0.02884", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:11:12.860871+00:00", probability: "0.025616", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:16:53.653676+00:00", probability: "0.027543", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:21:25.008971+00:00", probability: "0.031007", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:27:24.817660+00:00", probability: "0.028139", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:31:54.901607+00:00", probability: "0.031027", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:36:24.817000+00:00", probability: "0.029935", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:41:13.090598+00:00", probability: "0.033662", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:46:53.727811+00:00", probability: "0.027226", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:51:24.732031+00:00", probability: "0.026563", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:57:24.797035+00:00", probability: "0.02755", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:01:54.833885+00:00", probability: "0.021961", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:06:24.758254+00:00", probability: "0.021368", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:11:15.242501+00:00", probability: "0.023081", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:16:54.757109+00:00", probability: "0.022753", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:21:24.742441+00:00", probability: "0.021411", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:27:24.789808+00:00", probability: "0.020412", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:31:54.822029+00:00", probability: "0.022684", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:36:24.971616+00:00", probability: "0.012671", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:41:09.040738+00:00", probability: "0.012065", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:46:49.098542+00:00", probability: "0.012857", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:51:24.875685+00:00", probability: "0.011754", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:01:54.933191+00:00", probability: "0.013063", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:06:25.123480+00:00", probability: "0.011732", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:12:24.939797+00:00", probability: "0.010755", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:16:54.854142+00:00", probability: "0.0088", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:21:24.981246+00:00", probability: "0.009417", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:32:05.421227+00:00", probability: "0.008689", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:36:24.993990+00:00", probability: "0.008215", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:46:54.961700+00:00", probability: "0.007227", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:51:24.941083+00:00", probability: "0.006071", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:57:25.853387+00:00", probability: "0.006632", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:01:55.007660+00:00", probability: "0.005774", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:12:24.917957+00:00", probability: "0.006075", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:16:55.057037+00:00", probability: "0.005537", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:21:25.519889+00:00", probability: "0.005781", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:27:25.086697+00:00", probability: "0.003219", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:31:54.980387+00:00", probability: "0.002897", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:46:54.836301+00:00", probability: "0.002664", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:51:25.119887+00:00", probability: "0.005804", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:57:24.994475+00:00", probability: "0.005547", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T07:01:55.134023+00:00", probability: "0.006829", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T07:12:24.978448+00:00", probability: "0.006581", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T11:03:25.396420+00:00", probability: "0.006787", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:01:32.121700+00:00", probability: "0.002314", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:07:32.296237+00:00", probability: "0.004669", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:16:38.233711+00:00", probability: "0.006425", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:22:36.878874+00:00", probability: "0.007475", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:27:02.254196+00:00", probability: "0.006103", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:31:32.393467+00:00", probability: "0.006837", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:37:36.325422+00:00", probability: "0.014284", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:42:02.397711+00:00", probability: "0.013579", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:52:32.230383+00:00", probability: "0.014175", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:57:02.292294+00:00", probability: "0.014803", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:01:44.967297+00:00", probability: "0.003102", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:07:40.922682+00:00", probability: "0.002516", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:11:31.557654+00:00", probability: "0.002077", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:16:32.368568+00:00", probability: "0.002272", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:22:32.457644+00:00", probability: "0.005315", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:27:02.328365+00:00", probability: "0.006001", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:31:30.766239+00:00", probability: "0.006619", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:42:03.894288+00:00", probability: "0.004275", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:46:32.499339+00:00", probability: "0.003783", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:52:30.103758+00:00", probability: "0.007613", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:57:02.295932+00:00", probability: "0.008389", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:01:32.388551+00:00", probability: "0.009034", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:07:30.589268+00:00", probability: "0.008679", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:12:02.539866+00:00", probability: "0.01205", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:16:32.509056+00:00", probability: "0.011903", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:22:29.118118+00:00", probability: "0.013556", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:27:02.431908+00:00", probability: "0.013665", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:31:36.176169+00:00", probability: "0.014043", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:46:29.373474+00:00", probability: "0.012653", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:52:25.547135+00:00", probability: "0.010207", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:57:02.515905+00:00", probability: "0.008091", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:01:32.475241+00:00", probability: "0.009057", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:07:27.584475+00:00", probability: "0.009645", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:12:09.791890+00:00", probability: "0.021017", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:16:32.467564+00:00", probability: "0.01963", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:22:28.900262+00:00", probability: "0.021607", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:27:02.467693+00:00", probability: "0.02146", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:31:32.355628+00:00", probability: "0.040874", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:37:24.925694+00:00", probability: "0.041635", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:42:02.599933+00:00", probability: "0.063896", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:46:32.528698+00:00", probability: "0.063779", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:52:32.323694+00:00", probability: "0.073898", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:57:02.721177+00:00", probability: "0.058606", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:01:32.667681+00:00", probability: "0.057851", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:07:32.604608+00:00", probability: "0.056027", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:12:02.392117+00:00", probability: "0.057513", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:16:32.504599+00:00", probability: "0.042055", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:22:29.559191+00:00", probability: "0.038495", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:27:02.372895+00:00", probability: "0.037835", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:31:32.369451+00:00", probability: "0.03914", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:37:32.480772+00:00", probability: "0.014573", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:42:02.586740+00:00", probability: "0.011677", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:52:29.927815+00:00", probability: "0.010858", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:57:02.421912+00:00", probability: "0.011794", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:01:29.696997+00:00", probability: "0.011343", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:07:35.495038+00:00", probability: "0.011706", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:12:29.682303+00:00", probability: "0.01086", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:16:32.524509+00:00", probability: "0.009207", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:22:32.710013+00:00", probability: "0.008996", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:27:02.718901+00:00", probability: "0.00751", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:31:32.787975+00:00", probability: "0.008399", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:37:32.795010+00:00", probability: "0.00925", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:42:02.797854+00:00", probability: "0.01221", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:46:35.986461+00:00", probability: "0.011071", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:52:32.606932+00:00", probability: "0.012319", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:57:02.608225+00:00", probability: "0.013419", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:01:32.642953+00:00", probability: "0.01188", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:07:32.662386+00:00", probability: "0.010742", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:16:33.417463+00:00", probability: "0.011885", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:22:32.896568+00:00", probability: "0.016548", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:27:02.942302+00:00", probability: "0.014759", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:31:32.642402+00:00", probability: "0.017211", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:37:32.753311+00:00", probability: "0.016523", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:41:27.690470+00:00", probability: "0.017335", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:46:46.608343+00:00", probability: "0.016851", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:52:32.921891+00:00", probability: "0.017034", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:57:03.118947+00:00", probability: "0.016117", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T07:01:33.168803+00:00", probability: "0.018514", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T07:07:32.955805+00:00", probability: "0.018832", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T11:22:35.155437+00:00", probability: "0.019872", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:02:37.532470+00:00", probability: "0.019508", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:07:07.544047+00:00", probability: "0.020276", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:12:00.122315+00:00", probability: "0.01933", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:18:14.003636+00:00", probability: "0.018703", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:21:55.871409+00:00", probability: "0.019702", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:27:46.592637+00:00", probability: "0.018329", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:32:25.882164+00:00", probability: "0.018688", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:36:48.896569+00:00", probability: "0.018483", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:42:03.732719+00:00", probability: "0.019504", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:47:42.984192+00:00", probability: "0.018036", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:51:54.681637+00:00", probability: "0.018928", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:56:25.710971+00:00", probability: "0.019301", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:02:25.829089+00:00", probability: "0.019579", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:06:47.216580+00:00", probability: "0.029543", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:11:25.894787+00:00", probability: "0.027346", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:17:25.996026+00:00", probability: "0.030858", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:21:51.113011+00:00", probability: "0.052975", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:27:55.889037+00:00", probability: "0.05523", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:32:25.929155+00:00", probability: "0.053281", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:36:55.765217+00:00", probability: "0.049877", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:41:50.635611+00:00", probability: "0.055407", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:47:26.043890+00:00", probability: "0.057972", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:51:55.909934+00:00", probability: "0.060965", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:56:18.272058+00:00", probability: "0.067389", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:02:25.797469+00:00", probability: "0.037065", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:06:49.546752+00:00", probability: "0.047043", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:11:25.914867+00:00", probability: "0.046436", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:17:26.184322+00:00", probability: "0.041808", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:21:46.781176+00:00", probability: "0.08527", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:27:55.905318+00:00", probability: "0.079116", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:32:26.238967+00:00", probability: "0.07636", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:36:56.174519+00:00", probability: "0.077988", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:41:27.839983+00:00", probability: "0.048867", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:47:26.204894+00:00", probability: "0.046493", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:51:48.376763+00:00", probability: "0.043329", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:56:25.933285+00:00", probability: "0.0257", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:02:26.039667+00:00", probability: "0.025383", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:06:49.491181+00:00", probability: "0.050176", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:11:38.956586+00:00", probability: "0.034131", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:17:26.084407+00:00", probability: "0.022317", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:21:48.518176+00:00", probability: "0.02178", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:32:25.820139+00:00", probability: "0.031833", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:36:56.232276+00:00", probability: "0.025371", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:41:25.890612+00:00", probability: "0.029441", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:47:26.160310+00:00", probability: "0.027318", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:51:50.533672+00:00", probability: "0.02874", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:56:26.064918+00:00", probability: "0.072332", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:02:26.587145+00:00", probability: "0.06695", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:06:56.215374+00:00", probability: "0.065603", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:11:37.607125+00:00", probability: "0.066843", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:17:26.043707+00:00", probability: "0.060082", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:21:56.168662+00:00", probability: "0.068626", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:27:55.803030+00:00", probability: "0.068825", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:32:25.858478+00:00", probability: "0.116957", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:36:56.195550+00:00", probability: "0.061903", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:41:25.968157+00:00", probability: "0.066997", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:47:26.137402+00:00", probability: "0.071754", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:51:49.540257+00:00", probability: "0.056875", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:56:26.068260+00:00", probability: "0.050176", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:02:25.929267+00:00", probability: "0.046169", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:06:48.547245+00:00", probability: "0.031306", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:11:25.974142+00:00", probability: "0.038401", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:17:25.818931+00:00", probability: "0.040507", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:21:56.090554+00:00", probability: "0.043822", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:27:50.421885+00:00", probability: "0.039308", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:32:25.965758+00:00", probability: "0.040492", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:36:55.848422+00:00", probability: "0.031663", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:41:26.109476+00:00", probability: "0.073262", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:47:26.024631+00:00", probability: "0.081199", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:51:55.997823+00:00", probability: "0.071211", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:56:25.840963+00:00", probability: "0.120761", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T06:02:25.916250+00:00", probability: "0.095147", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T06:06:55.965994+00:00", probability: "0.0", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T22:08:55.891004+00:00", probability: "0.086583", americanOdds: nil, bookmaker: "consensus"),
        ]),
        GolfClosingRetainedSeries10868(outcomeID: "242242527", name: "Collin Morikawa", eliminated: false, eliminatedAt: nil, history: [
            GolfClosingRetainedPoint10868(timestamp: "2026-10-05T17:39:14.507306+00:00", probability: "0.048933", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-06T13:08:40.644152+00:00", probability: "0.04975", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:02:03.231914+00:00", probability: "0.050024", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:11:13.058928+00:00", probability: "0.047803", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:16:55.542752+00:00", probability: "0.050429", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:23:03.133505+00:00", probability: "0.051017", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:27:33.145591+00:00", probability: "0.05025", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:36:33.267676+00:00", probability: "0.05207", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:42:33.349212+00:00", probability: "0.050634", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:47:03.467275+00:00", probability: "0.066606", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:51:33.222200+00:00", probability: "0.068002", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:56:03.237230+00:00", probability: "0.06307", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:01:38.226778+00:00", probability: "0.06867", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:06:08.309734+00:00", probability: "0.064944", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:12:08.303481+00:00", probability: "0.047375", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:16:30.062412+00:00", probability: "0.045237", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:21:08.558032+00:00", probability: "0.045606", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:27:08.639061+00:00", probability: "0.043083", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:31:26.916892+00:00", probability: "0.044524", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:36:08.458334+00:00", probability: "0.046489", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:42:08.462936+00:00", probability: "0.03705", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:46:26.904828+00:00", probability: "0.038313", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:51:08.591737+00:00", probability: "0.037717", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:57:08.492012+00:00", probability: "0.057616", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:01:32.422514+00:00", probability: "0.05942", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:06:08.863154+00:00", probability: "0.057495", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:12:08.442006+00:00", probability: "0.075475", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:16:33.390446+00:00", probability: "0.07258", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:21:08.578066+00:00", probability: "0.1173", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:27:08.700847+00:00", probability: "0.116408", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:31:38.648207+00:00", probability: "0.11716", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:36:13.310618+00:00", probability: "0.116836", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:42:08.507576+00:00", probability: "0.11124", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:46:29.234103+00:00", probability: "0.11164", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:51:08.598563+00:00", probability: "0.115315", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:57:08.575077+00:00", probability: "0.112373", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:01:38.486948+00:00", probability: "0.116891", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:07:38.415236+00:00", probability: "0.114146", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:12:08.483856+00:00", probability: "0.114348", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:16:38.372037+00:00", probability: "0.111922", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:21:08.495213+00:00", probability: "0.10171", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:27:08.684216+00:00", probability: "0.103327", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:31:38.545519+00:00", probability: "0.104208", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:36:08.436708+00:00", probability: "0.092075", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:42:08.398714+00:00", probability: "0.097243", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:46:38.504366+00:00", probability: "0.067117", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:51:08.444107+00:00", probability: "0.06668", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:57:08.415687+00:00", probability: "0.063573", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:01:38.448606+00:00", probability: "0.064143", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:06:08.459731+00:00", probability: "0.067141", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:12:08.572694+00:00", probability: "0.075134", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:16:38.638257+00:00", probability: "0.077704", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:21:08.445056+00:00", probability: "0.106851", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:27:08.423388+00:00", probability: "0.103827", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:31:38.695212+00:00", probability: "0.106316", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:36:08.476578+00:00", probability: "0.107822", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:42:08.515784+00:00", probability: "0.075051", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:46:38.487589+00:00", probability: "0.073181", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:51:09.005838+00:00", probability: "0.044875", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:57:08.971709+00:00", probability: "0.046121", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:01:39.221294+00:00", probability: "0.046914", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:06:09.189943+00:00", probability: "0.063039", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:12:09.189349+00:00", probability: "0.058449", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:16:39.126639+00:00", probability: "0.058779", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:21:09.103878+00:00", probability: "0.052308", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:27:09.192337+00:00", probability: "0.054305", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:31:39.251792+00:00", probability: "0.053122", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:36:09.226450+00:00", probability: "0.053684", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:42:09.098398+00:00", probability: "0.052998", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:46:39.390867+00:00", probability: "0.055357", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:51:09.148688+00:00", probability: "0.052743", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:57:09.366348+00:00", probability: "0.053223", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:01:30.800138+00:00", probability: "0.056752", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:06:01.132593+00:00", probability: "0.05309", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:12:01.029217+00:00", probability: "0.054242", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:16:30.978149+00:00", probability: "0.051963", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:22:31.080453+00:00", probability: "0.056397", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:27:01.043399+00:00", probability: "0.053601", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:31:30.973790+00:00", probability: "0.054235", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:37:31.205466+00:00", probability: "0.056843", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:42:01.216854+00:00", probability: "0.0561", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:46:31.004456+00:00", probability: "0.053991", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:51:00.993924+00:00", probability: "0.053869", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:57:01.285974+00:00", probability: "0.05488", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T07:01:31.228243+00:00", probability: "0.055722", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T07:07:31.021816+00:00", probability: "0.055238", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:01:54.271593+00:00", probability: "0.056483", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:06:24.569832+00:00", probability: "0.053428", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:11:16.020101+00:00", probability: "0.055949", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:16:54.121527+00:00", probability: "0.055053", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:21:24.361544+00:00", probability: "0.055245", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:27:24.299799+00:00", probability: "0.056428", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:31:54.432306+00:00", probability: "0.055345", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:41:07.477710+00:00", probability: "0.056339", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:46:54.210856+00:00", probability: "0.05614", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:51:24.151362+00:00", probability: "0.055636", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:57:24.059847+00:00", probability: "0.057277", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:01:54.411616+00:00", probability: "0.056978", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:06:24.117663+00:00", probability: "0.051903", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:11:05.714663+00:00", probability: "0.05908", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:16:52.306605+00:00", probability: "0.058529", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:21:24.221027+00:00", probability: "0.060471", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:27:24.425662+00:00", probability: "0.060612", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:31:54.571872+00:00", probability: "0.059743", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:36:24.532871+00:00", probability: "0.059237", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:42:24.709592+00:00", probability: "0.060116", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:46:55.026284+00:00", probability: "0.06284", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:51:24.654444+00:00", probability: "0.053912", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:57:24.715348+00:00", probability: "0.057306", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:01:59.282505+00:00", probability: "0.058576", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:06:24.836570+00:00", probability: "0.053827", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:11:11.909513+00:00", probability: "0.052254", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:16:57.222706+00:00", probability: "0.077407", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:21:24.867456+00:00", probability: "0.074224", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:27:24.676035+00:00", probability: "0.07676", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:31:55.452236+00:00", probability: "0.074473", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:36:24.689467+00:00", probability: "0.07377", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:41:20.080252+00:00", probability: "0.08686", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:46:48.365847+00:00", probability: "0.087723", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:51:24.713585+00:00", probability: "0.089209", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:57:24.801333+00:00", probability: "0.081788", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:01:54.854394+00:00", probability: "0.084637", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:06:24.928070+00:00", probability: "0.075495", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:11:12.860871+00:00", probability: "0.069232", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:16:53.653676+00:00", probability: "0.069102", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:21:25.008971+00:00", probability: "0.048509", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:27:24.817660+00:00", probability: "0.047946", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:31:54.901607+00:00", probability: "0.052443", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:36:24.817000+00:00", probability: "0.051792", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:41:13.090598+00:00", probability: "0.043837", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:46:53.727811+00:00", probability: "0.04343", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:51:24.732031+00:00", probability: "0.045288", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:57:24.797035+00:00", probability: "0.046159", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:01:54.833885+00:00", probability: "0.065063", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:06:24.758254+00:00", probability: "0.064756", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:11:15.242501+00:00", probability: "0.065328", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:16:54.757109+00:00", probability: "0.06069", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:21:24.742441+00:00", probability: "0.063385", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:27:24.789808+00:00", probability: "0.058466", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:31:54.822029+00:00", probability: "0.062824", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:36:24.971616+00:00", probability: "0.066753", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:41:09.040738+00:00", probability: "0.067926", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:46:49.098542+00:00", probability: "0.065358", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:51:24.875685+00:00", probability: "0.063495", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:57:24.779033+00:00", probability: "0.069121", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:01:54.933191+00:00", probability: "0.064532", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:06:25.123480+00:00", probability: "0.064779", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:16:54.854142+00:00", probability: "0.030252", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:21:24.981246+00:00", probability: "0.030012", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:27:25.121923+00:00", probability: "0.032313", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:32:05.421227+00:00", probability: "0.016784", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:36:24.993990+00:00", probability: "0.01739", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:42:24.976809+00:00", probability: "0.016043", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:46:54.961700+00:00", probability: "0.015099", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:51:24.941083+00:00", probability: "0.01372", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:01:55.007660+00:00", probability: "0.00586", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:06:25.056796+00:00", probability: "0.005615", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:16:55.057037+00:00", probability: "0.00612", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:21:25.519889+00:00", probability: "0.005902", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:27:25.086697+00:00", probability: "0.002809", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:31:54.980387+00:00", probability: "0.002948", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:36:24.977474+00:00", probability: "0.002673", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:42:43.024481+00:00", probability: "0.002334", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:51:25.119887+00:00", probability: "0.000823", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:57:24.994475+00:00", probability: "0.001402", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T11:03:25.396420+00:00", probability: "0.001066", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:01:32.121700+00:00", probability: "0.001405", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:07:32.296237+00:00", probability: "0.001664", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:12:02.146122+00:00", probability: "0.001221", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:16:38.233711+00:00", probability: "0.002656", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:22:36.878874+00:00", probability: "0.003126", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:27:02.254196+00:00", probability: "0.002829", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:31:32.393467+00:00", probability: "0.001325", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:37:36.325422+00:00", probability: "0.001607", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:42:02.397711+00:00", probability: "0.000863", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:46:32.201718+00:00", probability: "0.001405", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:52:32.230383+00:00", probability: "0.001303", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:57:02.292294+00:00", probability: "0.001043", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:07:40.922682+00:00", probability: "0.000843", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:11:31.557654+00:00", probability: "0.002086", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:22:32.457644+00:00", probability: "0.001942", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:27:02.328365+00:00", probability: "0.001727", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:37:29.853954+00:00", probability: "0.001286", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:46:32.499339+00:00", probability: "0.000483", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:57:02.295932+00:00", probability: "0.000603", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:07:30.589268+00:00", probability: "0.001245", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:12:02.539866+00:00", probability: "0.001626", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:16:32.509056+00:00", probability: "0.001327", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:22:29.118118+00:00", probability: "0.001465", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:31:36.176169+00:00", probability: "0.001622", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:37:36.275556+00:00", probability: "0.001368", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:41:10.306614+00:00", probability: "0.000604", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:52:25.547135+00:00", probability: "0.000802", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:57:02.515905+00:00", probability: "0.000623", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:01:32.475241+00:00", probability: "0.000723", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:07:27.584475+00:00", probability: "0.000881", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:12:09.791890+00:00", probability: "0.00048", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:16:32.467564+00:00", probability: "0.001044", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:22:28.900262+00:00", probability: "0.000843", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:27:02.467693+00:00", probability: "0.000584", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:31:32.355628+00:00", probability: "0.000781", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:37:24.925694+00:00", probability: "0.001126", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:46:32.528698+00:00", probability: "0.000986", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:52:32.323694+00:00", probability: "0.001463", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:57:02.721177+00:00", probability: "0.000643", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:01:32.667681+00:00", probability: "0.00026", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:16:32.504599+00:00", probability: "1.9e-05", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:52:32.921891+00:00", probability: "0.00014", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:57:03.118947+00:00", probability: "0.0", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T22:08:55.891004+00:00", probability: "0.04975", americanOdds: nil, bookmaker: "consensus"),
        ]),
        GolfClosingRetainedSeries10868(outcomeID: "242242539", name: "Jacob Bridgeman", eliminated: false, eliminatedAt: nil, history: [
            GolfClosingRetainedPoint10868(timestamp: "2026-10-05T17:39:14.507306+00:00", probability: "0.031583", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-06T13:08:40.644152+00:00", probability: "0.030317", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:02:03.231914+00:00", probability: "0.030437", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:06:33.172825+00:00", probability: "0.031918", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:11:13.058928+00:00", probability: "0.032499", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:16:55.542752+00:00", probability: "0.030501", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:23:03.133505+00:00", probability: "0.03247", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:27:33.145591+00:00", probability: "0.031927", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:32:03.148937+00:00", probability: "0.03259", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:36:33.267676+00:00", probability: "0.030873", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:42:33.349212+00:00", probability: "0.033551", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:47:03.467275+00:00", probability: "0.028132", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:51:33.222200+00:00", probability: "0.027119", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:56:03.237230+00:00", probability: "0.028834", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:01:38.226778+00:00", probability: "0.025581", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:06:08.309734+00:00", probability: "0.028967", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:12:08.303481+00:00", probability: "0.03117", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:16:30.062412+00:00", probability: "0.030911", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:21:08.558032+00:00", probability: "0.028989", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:27:08.639061+00:00", probability: "0.02704", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:31:26.916892+00:00", probability: "0.028587", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:36:08.458334+00:00", probability: "0.029103", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:42:08.462936+00:00", probability: "0.037536", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:51:08.591737+00:00", probability: "0.038574", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:57:08.492012+00:00", probability: "0.03771", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:01:32.422514+00:00", probability: "0.036979", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:12:08.442006+00:00", probability: "0.050256", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:16:33.390446+00:00", probability: "0.050596", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:21:08.578066+00:00", probability: "0.048475", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:27:08.700847+00:00", probability: "0.052914", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:31:38.648207+00:00", probability: "0.049369", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:36:13.310618+00:00", probability: "0.051008", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:42:08.507576+00:00", probability: "0.049966", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:46:29.234103+00:00", probability: "0.050325", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:51:08.598563+00:00", probability: "0.051321", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:57:08.575077+00:00", probability: "0.049519", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:01:38.486948+00:00", probability: "0.077084", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:12:08.483856+00:00", probability: "0.076209", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:16:38.372037+00:00", probability: "0.066837", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:21:08.495213+00:00", probability: "0.069468", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:27:08.684216+00:00", probability: "0.070924", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:31:38.545519+00:00", probability: "0.073059", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:36:08.436708+00:00", probability: "0.098778", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:46:38.504366+00:00", probability: "0.099951", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:51:08.444107+00:00", probability: "0.102115", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:57:08.415687+00:00", probability: "0.100755", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:01:38.448606+00:00", probability: "0.105575", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:06:08.459731+00:00", probability: "0.104938", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:12:08.572694+00:00", probability: "0.079616", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:16:38.638257+00:00", probability: "0.081493", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:21:08.445056+00:00", probability: "0.085499", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:27:08.423388+00:00", probability: "0.11055", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:31:38.695212+00:00", probability: "0.112863", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:36:08.476578+00:00", probability: "0.110099", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:42:08.515784+00:00", probability: "0.118846", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:46:38.487589+00:00", probability: "0.118404", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:51:09.005838+00:00", probability: "0.173018", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:57:08.971709+00:00", probability: "0.17384", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:01:39.221294+00:00", probability: "0.171538", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:06:09.189943+00:00", probability: "0.215476", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:12:09.189349+00:00", probability: "0.212756", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:16:39.126639+00:00", probability: "0.201992", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:21:09.103878+00:00", probability: "0.194162", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:27:09.192337+00:00", probability: "0.196914", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:31:39.251792+00:00", probability: "0.197745", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:36:09.226450+00:00", probability: "0.197011", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:42:09.098398+00:00", probability: "0.202305", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:46:39.390867+00:00", probability: "0.195274", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:51:09.148688+00:00", probability: "0.201102", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:57:09.366348+00:00", probability: "0.19756", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:01:30.800138+00:00", probability: "0.204693", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:06:01.132593+00:00", probability: "0.195129", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:12:01.029217+00:00", probability: "0.194885", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:16:30.978149+00:00", probability: "0.197676", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:22:31.080453+00:00", probability: "0.19876", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:27:01.043399+00:00", probability: "0.198916", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:31:30.973790+00:00", probability: "0.199882", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:37:31.205466+00:00", probability: "0.197637", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:42:01.216854+00:00", probability: "0.196454", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:46:31.004456+00:00", probability: "0.196342", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:51:00.993924+00:00", probability: "0.197985", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:57:01.285974+00:00", probability: "0.199379", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T07:01:31.228243+00:00", probability: "0.20324", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T07:07:31.021816+00:00", probability: "0.198977", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:01:54.271593+00:00", probability: "0.207032", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:06:24.569832+00:00", probability: "0.20057", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:11:16.020101+00:00", probability: "0.203232", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:16:54.121527+00:00", probability: "0.20745", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:21:24.361544+00:00", probability: "0.203534", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:31:54.432306+00:00", probability: "0.201481", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:36:24.206129+00:00", probability: "0.204877", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:41:07.477710+00:00", probability: "0.207991", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:46:54.210856+00:00", probability: "0.202998", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:51:24.151362+00:00", probability: "0.201298", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:57:24.059847+00:00", probability: "0.204919", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:01:54.411616+00:00", probability: "0.202326", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:06:24.117663+00:00", probability: "0.203126", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:11:05.714663+00:00", probability: "0.211015", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:16:52.306605+00:00", probability: "0.214104", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:21:24.221027+00:00", probability: "0.21148", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:27:24.425662+00:00", probability: "0.212425", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:31:54.571872+00:00", probability: "0.215369", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:36:24.532871+00:00", probability: "0.211774", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:42:24.709592+00:00", probability: "0.216482", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:46:55.026284+00:00", probability: "0.224216", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:51:24.654444+00:00", probability: "0.291878", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:57:24.715348+00:00", probability: "0.294273", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:01:59.282505+00:00", probability: "0.293789", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:06:24.836570+00:00", probability: "0.279532", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:11:11.909513+00:00", probability: "0.284797", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:16:57.222706+00:00", probability: "0.272481", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:21:24.867456+00:00", probability: "0.268969", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:27:24.676035+00:00", probability: "0.267584", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:31:55.452236+00:00", probability: "0.260864", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:36:24.689467+00:00", probability: "0.258973", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:41:20.080252+00:00", probability: "0.216146", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:46:48.365847+00:00", probability: "0.210122", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:51:24.713585+00:00", probability: "0.216375", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:57:24.801333+00:00", probability: "0.204946", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:01:54.854394+00:00", probability: "0.205528", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:06:24.928070+00:00", probability: "0.192222", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:11:12.860871+00:00", probability: "0.180535", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:16:53.653676+00:00", probability: "0.178822", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:21:25.008971+00:00", probability: "0.194973", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:27:24.817660+00:00", probability: "0.202026", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:31:54.901607+00:00", probability: "0.207571", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:36:24.817000+00:00", probability: "0.206434", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:41:13.090598+00:00", probability: "0.187438", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:46:53.727811+00:00", probability: "0.196221", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:51:24.732031+00:00", probability: "0.195238", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:57:24.797035+00:00", probability: "0.172392", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:01:54.833885+00:00", probability: "0.177038", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:06:24.758254+00:00", probability: "0.176224", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:11:15.242501+00:00", probability: "0.178406", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:16:54.757109+00:00", probability: "0.169524", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:21:24.742441+00:00", probability: "0.169399", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:27:24.789808+00:00", probability: "0.166155", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:31:54.822029+00:00", probability: "0.175606", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:36:24.971616+00:00", probability: "0.188095", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:41:09.040738+00:00", probability: "0.191227", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:46:49.098542+00:00", probability: "0.186107", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:51:24.875685+00:00", probability: "0.184446", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:57:24.779033+00:00", probability: "0.124562", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:01:54.933191+00:00", probability: "0.121792", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:06:25.123480+00:00", probability: "0.123118", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:12:24.939797+00:00", probability: "0.119371", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:16:54.854142+00:00", probability: "0.159545", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:21:24.981246+00:00", probability: "0.160543", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:27:25.121923+00:00", probability: "0.163973", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:32:05.421227+00:00", probability: "0.166311", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:36:24.993990+00:00", probability: "0.161465", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:42:24.976809+00:00", probability: "0.158689", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:46:54.961700+00:00", probability: "0.160141", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:51:24.941083+00:00", probability: "0.207685", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:57:25.853387+00:00", probability: "0.208372", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:01:55.007660+00:00", probability: "0.196929", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:06:25.056796+00:00", probability: "0.210618", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:12:24.917957+00:00", probability: "0.209328", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:16:55.057037+00:00", probability: "0.210572", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:21:25.519889+00:00", probability: "0.216945", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:27:25.086697+00:00", probability: "0.221103", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:31:54.980387+00:00", probability: "0.220791", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:36:24.977474+00:00", probability: "0.221611", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:42:43.024481+00:00", probability: "0.223266", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:46:54.836301+00:00", probability: "0.220578", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:51:25.119887+00:00", probability: "0.242714", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:57:24.994475+00:00", probability: "0.238542", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T07:01:55.134023+00:00", probability: "0.241981", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T07:06:24.990357+00:00", probability: "0.236361", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T11:03:25.396420+00:00", probability: "0.237994", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:01:32.121700+00:00", probability: "0.237664", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:07:32.296237+00:00", probability: "0.239744", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:12:02.146122+00:00", probability: "0.239616", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:16:38.233711+00:00", probability: "0.240146", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:22:36.878874+00:00", probability: "0.238697", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:27:02.254196+00:00", probability: "0.236368", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:31:32.393467+00:00", probability: "0.237447", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:37:36.325422+00:00", probability: "0.237773", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:42:02.397711+00:00", probability: "0.238215", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:46:32.201718+00:00", probability: "0.233842", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:52:32.230383+00:00", probability: "0.238046", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:57:02.292294+00:00", probability: "0.23264", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:01:44.967297+00:00", probability: "0.241588", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:07:40.922682+00:00", probability: "0.243873", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:11:31.557654+00:00", probability: "0.235424", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:16:32.368568+00:00", probability: "0.241528", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:22:32.457644+00:00", probability: "0.238146", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:27:02.328365+00:00", probability: "0.239129", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:31:30.766239+00:00", probability: "0.237562", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:37:29.853954+00:00", probability: "0.237733", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:42:03.894288+00:00", probability: "0.235527", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:46:32.499339+00:00", probability: "0.23957", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:52:30.103758+00:00", probability: "0.216413", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:57:02.295932+00:00", probability: "0.230119", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:01:32.388551+00:00", probability: "0.222769", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:07:30.589268+00:00", probability: "0.223095", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:12:02.539866+00:00", probability: "0.152315", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:16:32.509056+00:00", probability: "0.155511", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:22:29.118118+00:00", probability: "0.144711", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:27:02.431908+00:00", probability: "0.14667", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:31:36.176169+00:00", probability: "0.148885", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:37:36.275556+00:00", probability: "0.141434", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:41:10.306614+00:00", probability: "0.144257", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:46:29.373474+00:00", probability: "0.140005", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:52:25.547135+00:00", probability: "0.138993", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:57:02.515905+00:00", probability: "0.153286", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:01:32.475241+00:00", probability: "0.154184", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:07:27.584475+00:00", probability: "0.152727", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:12:09.791890+00:00", probability: "0.164358", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:16:32.467564+00:00", probability: "0.175951", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:22:28.900262+00:00", probability: "0.18031", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:27:02.467693+00:00", probability: "0.181767", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:31:32.355628+00:00", probability: "0.177774", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:37:24.925694+00:00", probability: "0.102095", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:42:02.599933+00:00", probability: "0.110123", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:46:32.528698+00:00", probability: "0.105735", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:52:32.323694+00:00", probability: "0.121083", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:57:02.721177+00:00", probability: "0.107858", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:01:32.667681+00:00", probability: "0.16917", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:07:32.604608+00:00", probability: "0.161116", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:12:02.392117+00:00", probability: "0.162765", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:16:32.504599+00:00", probability: "0.223864", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:22:29.559191+00:00", probability: "0.210795", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:27:02.372895+00:00", probability: "0.206312", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:31:32.369451+00:00", probability: "0.212753", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:37:32.480772+00:00", probability: "0.297206", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:42:02.586740+00:00", probability: "0.263489", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:46:32.643579+00:00", probability: "0.254716", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:52:29.927815+00:00", probability: "0.257827", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:57:02.421912+00:00", probability: "0.274469", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:01:29.696997+00:00", probability: "0.281993", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:07:35.495038+00:00", probability: "0.283468", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:12:29.682303+00:00", probability: "0.269937", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:16:32.524509+00:00", probability: "0.246287", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:22:32.710013+00:00", probability: "0.244992", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:27:02.718901+00:00", probability: "0.242829", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:31:32.787975+00:00", probability: "0.215619", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:37:32.795010+00:00", probability: "0.210616", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:42:02.797854+00:00", probability: "0.239331", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:46:35.986461+00:00", probability: "0.244484", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:52:32.606932+00:00", probability: "0.245645", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:57:02.608225+00:00", probability: "0.252887", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:01:32.642953+00:00", probability: "0.253096", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:07:32.662386+00:00", probability: "0.216947", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:12:02.573288+00:00", probability: "0.333154", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:16:33.417463+00:00", probability: "0.351089", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:22:32.896568+00:00", probability: "0.252342", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:27:02.942302+00:00", probability: "0.24731", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:31:32.642402+00:00", probability: "0.259602", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:37:32.753311+00:00", probability: "0.255357", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:41:27.690470+00:00", probability: "0.249327", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:46:46.608343+00:00", probability: "0.244938", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:52:32.921891+00:00", probability: "0.245209", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:57:03.118947+00:00", probability: "0.245758", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T07:01:33.168803+00:00", probability: "0.168421", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T07:07:32.955805+00:00", probability: "0.1699", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T11:22:35.155437+00:00", probability: "0.169585", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:02:37.532470+00:00", probability: "0.16971", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:12:00.122315+00:00", probability: "0.167744", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:18:14.003636+00:00", probability: "0.168714", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:21:55.871409+00:00", probability: "0.170176", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:27:46.592637+00:00", probability: "0.170616", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:32:25.882164+00:00", probability: "0.166641", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:36:48.896569+00:00", probability: "0.167586", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:42:03.732719+00:00", probability: "0.166685", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:47:42.984192+00:00", probability: "0.167269", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:51:54.681637+00:00", probability: "0.167138", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:56:25.710971+00:00", probability: "0.168506", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:06:47.216580+00:00", probability: "0.163584", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:11:25.894787+00:00", probability: "0.165744", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:17:25.996026+00:00", probability: "0.173965", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:21:51.113011+00:00", probability: "0.173345", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:27:55.889037+00:00", probability: "0.171612", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:32:25.929155+00:00", probability: "0.202898", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:36:55.765217+00:00", probability: "0.159603", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:41:50.635611+00:00", probability: "0.167215", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:47:26.043890+00:00", probability: "0.173361", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:51:55.909934+00:00", probability: "0.158434", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:56:18.272058+00:00", probability: "0.174025", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:02:25.797469+00:00", probability: "0.180032", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:06:49.546752+00:00", probability: "0.084168", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:11:25.914867+00:00", probability: "0.084821", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:17:26.184322+00:00", probability: "0.081315", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:21:46.781176+00:00", probability: "0.07676", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:27:55.905318+00:00", probability: "0.071369", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:32:26.238967+00:00", probability: "0.069574", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:36:56.174519+00:00", probability: "0.075035", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:41:27.839983+00:00", probability: "0.053039", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:47:26.204894+00:00", probability: "0.057185", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:51:48.376763+00:00", probability: "0.049511", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:56:25.933285+00:00", probability: "0.07946", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:02:26.039667+00:00", probability: "0.079204", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:06:49.491181+00:00", probability: "0.078755", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:11:38.956586+00:00", probability: "0.062339", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:17:26.084407+00:00", probability: "0.062564", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:21:48.518176+00:00", probability: "0.06327", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:27:57.815530+00:00", probability: "0.021618", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:32:25.820139+00:00", probability: "0.030411", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:36:56.232276+00:00", probability: "0.028207", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:41:25.890612+00:00", probability: "0.023039", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:51:50.533672+00:00", probability: "0.023154", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:56:26.064918+00:00", probability: "0.016403", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:02:26.587145+00:00", probability: "0.014572", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:11:37.607125+00:00", probability: "0.013767", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:17:26.043707+00:00", probability: "0.045007", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:21:56.168662+00:00", probability: "0.054236", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:27:55.803030+00:00", probability: "0.05588", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:32:25.858478+00:00", probability: "0.088342", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:36:56.195550+00:00", probability: "0.022499", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:41:25.968157+00:00", probability: "0.025185", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:47:26.137402+00:00", probability: "0.024823", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:51:49.540257+00:00", probability: "0.071178", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:56:26.068260+00:00", probability: "0.059801", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:02:25.929267+00:00", probability: "0.056858", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:06:48.547245+00:00", probability: "0.0706", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:11:25.974142+00:00", probability: "0.08451", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:17:25.818931+00:00", probability: "0.050047", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:21:56.090554+00:00", probability: "0.051987", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:27:50.421885+00:00", probability: "0.059508", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:32:25.965758+00:00", probability: "0.062", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:36:55.848422+00:00", probability: "0.054168", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:41:26.109476+00:00", probability: "0.048734", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:47:26.024631+00:00", probability: "0.056417", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:51:55.997823+00:00", probability: "0.139097", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:56:25.840963+00:00", probability: "0.17586", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T06:02:25.916250+00:00", probability: "0.162562", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T06:06:55.965994+00:00", probability: "0.190156", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T06:11:34.934252+00:00", probability: "0.190636", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T06:17:26.152308+00:00", probability: "0.180851", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T06:21:56.159202+00:00", probability: "0.205769", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T06:27:55.986139+00:00", probability: "0.125838", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T06:32:25.936365+00:00", probability: "0.122725", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T06:36:56.060523+00:00", probability: "0.12132", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T06:41:26.165769+00:00", probability: "0.0", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T22:08:55.891004+00:00", probability: "0.030317", americanOdds: nil, bookmaker: "consensus"),
        ]),
        GolfClosingRetainedSeries10868(outcomeID: "242242559", name: "Keith Mitchell", eliminated: false, eliminatedAt: nil, history: [
            GolfClosingRetainedPoint10868(timestamp: "2026-10-05T17:39:14.507306+00:00", probability: "0.012467", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-06T13:08:40.644152+00:00", probability: "0.012733", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:02:03.231914+00:00", probability: "0.020489", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:06:33.172825+00:00", probability: "0.019386", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:11:13.058928+00:00", probability: "0.020805", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:16:55.542752+00:00", probability: "0.019325", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:23:03.133505+00:00", probability: "0.012128", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:27:33.145591+00:00", probability: "0.013422", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:36:33.267676+00:00", probability: "0.008341", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:42:33.349212+00:00", probability: "0.008132", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:47:03.467275+00:00", probability: "0.006796", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:51:33.222200+00:00", probability: "0.009467", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T00:56:03.237230+00:00", probability: "0.00859", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:01:38.226778+00:00", probability: "0.009037", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:06:08.309734+00:00", probability: "0.010117", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:12:08.303481+00:00", probability: "0.011786", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:16:30.062412+00:00", probability: "0.009573", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:21:08.558032+00:00", probability: "0.009949", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:27:08.639061+00:00", probability: "0.008052", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:31:26.916892+00:00", probability: "0.008851", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:36:08.458334+00:00", probability: "0.009449", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:42:08.462936+00:00", probability: "0.008911", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:46:26.904828+00:00", probability: "0.009343", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:51:08.591737+00:00", probability: "0.014248", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T01:57:08.492012+00:00", probability: "0.013996", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:01:32.422514+00:00", probability: "0.012546", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:06:08.863154+00:00", probability: "0.012885", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:12:08.442006+00:00", probability: "0.013647", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:16:33.390446+00:00", probability: "0.01255", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:21:08.578066+00:00", probability: "0.012252", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:27:08.700847+00:00", probability: "0.014273", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:31:38.648207+00:00", probability: "0.019011", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:36:13.310618+00:00", probability: "0.019861", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:42:08.507576+00:00", probability: "0.021525", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:46:29.234103+00:00", probability: "0.032088", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:51:08.598563+00:00", probability: "0.03226", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T02:57:08.575077+00:00", probability: "0.028595", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:01:38.486948+00:00", probability: "0.029309", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:07:38.415236+00:00", probability: "0.028396", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:12:08.483856+00:00", probability: "0.028541", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:16:38.372037+00:00", probability: "0.029898", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:21:08.495213+00:00", probability: "0.036137", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:27:08.684216+00:00", probability: "0.035311", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:31:38.545519+00:00", probability: "0.049596", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:36:08.436708+00:00", probability: "0.045702", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:42:08.398714+00:00", probability: "0.051259", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:46:38.504366+00:00", probability: "0.053115", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:51:08.444107+00:00", probability: "0.036765", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T03:57:08.415687+00:00", probability: "0.037202", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:01:38.448606+00:00", probability: "0.040509", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:06:08.459731+00:00", probability: "0.039599", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:12:08.572694+00:00", probability: "0.040792", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:16:38.638257+00:00", probability: "0.03996", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:21:08.445056+00:00", probability: "0.042342", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:27:08.423388+00:00", probability: "0.03759", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:31:38.695212+00:00", probability: "0.037172", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:36:08.476578+00:00", probability: "0.036838", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:42:08.515784+00:00", probability: "0.037082", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:46:38.487589+00:00", probability: "0.033919", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:51:09.005838+00:00", probability: "0.034154", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T04:57:08.971709+00:00", probability: "0.032491", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:01:39.221294+00:00", probability: "0.033075", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:06:09.189943+00:00", probability: "0.030615", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:12:09.189349+00:00", probability: "0.030497", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:16:39.126639+00:00", probability: "0.029358", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:21:09.103878+00:00", probability: "0.031695", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:27:09.192337+00:00", probability: "0.030443", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:31:39.251792+00:00", probability: "0.031827", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:36:09.226450+00:00", probability: "0.030647", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:42:09.098398+00:00", probability: "0.030333", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:46:39.390867+00:00", probability: "0.028935", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:51:09.148688+00:00", probability: "0.031211", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T05:57:09.366348+00:00", probability: "0.029731", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:01:30.800138+00:00", probability: "0.032268", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:06:01.132593+00:00", probability: "0.031229", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:16:30.978149+00:00", probability: "0.030257", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:22:31.080453+00:00", probability: "0.030951", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:27:01.043399+00:00", probability: "0.029903", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:31:30.973790+00:00", probability: "0.032064", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:37:31.205466+00:00", probability: "0.029881", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:42:01.216854+00:00", probability: "0.031498", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:46:31.004456+00:00", probability: "0.032154", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:51:00.993924+00:00", probability: "0.030822", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T06:57:01.285974+00:00", probability: "0.033737", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T07:01:31.228243+00:00", probability: "0.03058", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-08T07:07:31.021816+00:00", probability: "0.031973", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:01:54.271593+00:00", probability: "0.030854", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:06:24.569832+00:00", probability: "0.030558", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:11:16.020101+00:00", probability: "0.031816", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:16:54.121527+00:00", probability: "0.031495", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:21:24.361544+00:00", probability: "0.031837", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:27:24.299799+00:00", probability: "0.03297", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:31:54.432306+00:00", probability: "0.032179", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:36:24.206129+00:00", probability: "0.03311", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:41:07.477710+00:00", probability: "0.032704", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:46:54.210856+00:00", probability: "0.032583", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:51:24.151362+00:00", probability: "0.031822", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T00:57:24.059847+00:00", probability: "0.03127", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:06:24.117663+00:00", probability: "0.048961", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:11:05.714663+00:00", probability: "0.051075", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:16:52.306605+00:00", probability: "0.050593", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:21:24.221027+00:00", probability: "0.075613", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:27:24.425662+00:00", probability: "0.075041", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:31:54.571872+00:00", probability: "0.069707", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:36:24.532871+00:00", probability: "0.067309", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:42:24.709592+00:00", probability: "0.067826", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:46:55.026284+00:00", probability: "0.069285", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T01:51:24.654444+00:00", probability: "0.069068", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:01:59.282505+00:00", probability: "0.053144", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:06:24.836570+00:00", probability: "0.055905", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:11:11.909513+00:00", probability: "0.055598", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:16:57.222706+00:00", probability: "0.079768", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:21:24.867456+00:00", probability: "0.07997", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:27:24.676035+00:00", probability: "0.081382", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:31:55.452236+00:00", probability: "0.084322", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:36:24.689467+00:00", probability: "0.082644", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:41:20.080252+00:00", probability: "0.081898", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:46:48.365847+00:00", probability: "0.083832", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:51:24.713585+00:00", probability: "0.083952", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T02:57:24.801333+00:00", probability: "0.111555", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:01:54.854394+00:00", probability: "0.110064", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:06:24.928070+00:00", probability: "0.116894", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:11:12.860871+00:00", probability: "0.15042", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:16:53.653676+00:00", probability: "0.14325", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:21:25.008971+00:00", probability: "0.145856", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:27:24.817660+00:00", probability: "0.154638", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:31:54.901607+00:00", probability: "0.098273", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:36:24.817000+00:00", probability: "0.101351", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:41:13.090598+00:00", probability: "0.103196", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:46:53.727811+00:00", probability: "0.105345", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:51:24.732031+00:00", probability: "0.110319", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T03:57:24.797035+00:00", probability: "0.120074", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:01:54.833885+00:00", probability: "0.117466", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:06:24.758254+00:00", probability: "0.115011", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:11:15.242501+00:00", probability: "0.118901", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:16:54.757109+00:00", probability: "0.114607", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:21:24.742441+00:00", probability: "0.112146", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:27:24.789808+00:00", probability: "0.100817", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:31:54.822029+00:00", probability: "0.10827", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:36:24.971616+00:00", probability: "0.106155", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:41:09.040738+00:00", probability: "0.109112", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:46:49.098542+00:00", probability: "0.108048", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:51:24.875685+00:00", probability: "0.101106", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T04:57:24.779033+00:00", probability: "0.109635", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:01:54.933191+00:00", probability: "0.152905", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:06:25.123480+00:00", probability: "0.158989", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:12:24.939797+00:00", probability: "0.149859", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:16:54.854142+00:00", probability: "0.147719", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:21:24.981246+00:00", probability: "0.106453", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:27:25.121923+00:00", probability: "0.108517", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:32:05.421227+00:00", probability: "0.107437", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:36:24.993990+00:00", probability: "0.104142", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:42:24.976809+00:00", probability: "0.10062", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:46:54.961700+00:00", probability: "0.101714", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:51:24.941083+00:00", probability: "0.093066", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T05:57:25.853387+00:00", probability: "0.093966", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:01:55.007660+00:00", probability: "0.156898", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:06:25.056796+00:00", probability: "0.158857", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:12:24.917957+00:00", probability: "0.161415", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:16:55.057037+00:00", probability: "0.165212", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:21:25.519889+00:00", probability: "0.162096", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:27:25.086697+00:00", probability: "0.168546", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:31:54.980387+00:00", probability: "0.168977", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:36:24.977474+00:00", probability: "0.168515", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:42:43.024481+00:00", probability: "0.170724", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:46:54.836301+00:00", probability: "0.17027", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:51:25.119887+00:00", probability: "0.165591", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T06:57:24.994475+00:00", probability: "0.16824", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T07:01:55.134023+00:00", probability: "0.167406", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T07:06:24.990357+00:00", probability: "0.165217", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T07:12:24.978448+00:00", probability: "0.168476", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-09T11:03:25.396420+00:00", probability: "0.167383", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:01:32.121700+00:00", probability: "0.167576", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:07:32.296237+00:00", probability: "0.165373", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:12:02.146122+00:00", probability: "0.166297", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:16:38.233711+00:00", probability: "0.165634", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:22:36.878874+00:00", probability: "0.164558", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:27:02.254196+00:00", probability: "0.165313", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:31:32.393467+00:00", probability: "0.166252", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:37:36.325422+00:00", probability: "0.163551", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:42:02.397711+00:00", probability: "0.16529", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:46:32.201718+00:00", probability: "0.164455", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:52:32.230383+00:00", probability: "0.165006", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T00:57:02.292294+00:00", probability: "0.164847", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:01:44.967297+00:00", probability: "0.167459", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:07:40.922682+00:00", probability: "0.169744", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:11:31.557654+00:00", probability: "0.168141", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:16:32.368568+00:00", probability: "0.164722", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:22:32.457644+00:00", probability: "0.166414", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:27:02.328365+00:00", probability: "0.163693", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:31:30.766239+00:00", probability: "0.171364", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:37:29.853954+00:00", probability: "0.167654", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:42:03.894288+00:00", probability: "0.158279", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:46:32.499339+00:00", probability: "0.165638", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:52:30.103758+00:00", probability: "0.150851", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T01:57:02.295932+00:00", probability: "0.159622", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:01:32.388551+00:00", probability: "0.156437", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:07:30.589268+00:00", probability: "0.157056", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:12:02.539866+00:00", probability: "0.162703", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:16:32.509056+00:00", probability: "0.16595", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:22:29.118118+00:00", probability: "0.155909", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:27:02.431908+00:00", probability: "0.158847", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:37:36.275556+00:00", probability: "0.154439", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:41:10.306614+00:00", probability: "0.155785", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:46:29.373474+00:00", probability: "0.155479", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:52:25.547135+00:00", probability: "0.154788", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T02:57:02.515905+00:00", probability: "0.171226", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:01:32.475241+00:00", probability: "0.170735", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:07:27.584475+00:00", probability: "0.168959", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:12:09.791890+00:00", probability: "0.178939", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:16:32.467564+00:00", probability: "0.113156", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:22:28.900262+00:00", probability: "0.122413", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:27:02.467693+00:00", probability: "0.119742", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:31:32.355628+00:00", probability: "0.114674", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:37:24.925694+00:00", probability: "0.117003", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:42:02.599933+00:00", probability: "0.070015", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:46:32.528698+00:00", probability: "0.074022", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:52:32.323694+00:00", probability: "0.080326", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T03:57:02.721177+00:00", probability: "0.071648", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:01:32.667681+00:00", probability: "0.037591", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:07:32.604608+00:00", probability: "0.033422", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:12:02.392117+00:00", probability: "0.036659", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:16:32.504599+00:00", probability: "0.014616", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:22:29.559191+00:00", probability: "0.012376", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:27:02.372895+00:00", probability: "0.011438", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:31:32.369451+00:00", probability: "0.01285", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:37:32.480772+00:00", probability: "0.022235", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:42:02.586740+00:00", probability: "0.01684", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:46:32.643579+00:00", probability: "0.01724", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:52:29.927815+00:00", probability: "0.018391", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T04:57:02.421912+00:00", probability: "0.017931", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:01:29.696997+00:00", probability: "0.019322", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:07:35.495038+00:00", probability: "0.019116", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:12:29.682303+00:00", probability: "0.017618", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:16:32.524509+00:00", probability: "0.015348", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:22:32.710013+00:00", probability: "0.015079", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:27:02.718901+00:00", probability: "0.015501", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:31:32.787975+00:00", probability: "0.023814", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:37:32.795010+00:00", probability: "0.023257", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:42:02.797854+00:00", probability: "0.02735", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:46:35.986461+00:00", probability: "0.030183", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T05:57:02.608225+00:00", probability: "0.032461", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:01:32.642953+00:00", probability: "0.02954", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:07:32.662386+00:00", probability: "0.049688", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:12:02.573288+00:00", probability: "0.048507", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:16:33.417463+00:00", probability: "0.050914", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:22:32.896568+00:00", probability: "0.060447", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:27:02.942302+00:00", probability: "0.058984", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:31:32.642402+00:00", probability: "0.064866", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:41:27.690470+00:00", probability: "0.0592", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:46:46.608343+00:00", probability: "0.060794", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:52:32.921891+00:00", probability: "0.059026", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T06:57:03.118947+00:00", probability: "0.058007", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T07:01:33.168803+00:00", probability: "0.075154", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T07:07:32.955805+00:00", probability: "0.07628", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-10T11:22:35.155437+00:00", probability: "0.075281", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:02:37.532470+00:00", probability: "0.074947", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:07:07.544047+00:00", probability: "0.073789", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:12:00.122315+00:00", probability: "0.075553", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:18:14.003636+00:00", probability: "0.076932", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:21:55.871409+00:00", probability: "0.076038", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:27:46.592637+00:00", probability: "0.075446", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:42:03.732719+00:00", probability: "0.075767", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:47:42.984192+00:00", probability: "0.076862", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:51:54.681637+00:00", probability: "0.075382", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T00:56:25.710971+00:00", probability: "0.076928", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:02:25.829089+00:00", probability: "0.076555", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:06:47.216580+00:00", probability: "0.075549", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:11:25.894787+00:00", probability: "0.074565", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:17:25.996026+00:00", probability: "0.055839", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:21:51.113011+00:00", probability: "0.05528", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:27:55.889037+00:00", probability: "0.057188", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:32:25.929155+00:00", probability: "0.063935", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:36:55.765217+00:00", probability: "0.057926", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:41:50.635611+00:00", probability: "0.049977", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:47:26.043890+00:00", probability: "0.051666", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:51:55.909934+00:00", probability: "0.053106", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T01:56:18.272058+00:00", probability: "0.060989", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:02:25.797469+00:00", probability: "0.061831", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:06:49.546752+00:00", probability: "0.076331", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:11:25.914867+00:00", probability: "0.076662", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:17:26.184322+00:00", probability: "0.095224", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:21:46.781176+00:00", probability: "0.091179", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:27:55.905318+00:00", probability: "0.167635", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:32:26.238967+00:00", probability: "0.174139", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:36:56.174519+00:00", probability: "0.178587", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:41:27.839983+00:00", probability: "0.217417", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:47:26.204894+00:00", probability: "0.218842", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:51:48.376763+00:00", probability: "0.224277", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T02:56:25.933285+00:00", probability: "0.349543", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:02:26.039667+00:00", probability: "0.362227", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:06:49.491181+00:00", probability: "0.353701", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:11:38.956586+00:00", probability: "0.469575", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:17:26.084407+00:00", probability: "0.471013", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:21:48.518176+00:00", probability: "0.464103", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:27:57.815530+00:00", probability: "0.469608", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:32:25.820139+00:00", probability: "0.268695", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:36:56.232276+00:00", probability: "0.2677", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:41:25.890612+00:00", probability: "0.288578", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:47:26.160310+00:00", probability: "0.292203", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:51:50.533672+00:00", probability: "0.295734", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T03:56:26.064918+00:00", probability: "0.296626", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:02:26.587145+00:00", probability: "0.275234", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:06:56.215374+00:00", probability: "0.273814", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:11:37.607125+00:00", probability: "0.27264", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:17:26.043707+00:00", probability: "0.294284", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:21:56.168662+00:00", probability: "0.325316", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:27:55.803030+00:00", probability: "0.324929", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:32:25.858478+00:00", probability: "0.205167", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:36:56.195550+00:00", probability: "0.203083", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:41:25.968157+00:00", probability: "0.220654", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:47:26.137402+00:00", probability: "0.219294", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:51:49.540257+00:00", probability: "0.126104", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T04:56:26.068260+00:00", probability: "0.103585", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:02:25.929267+00:00", probability: "0.1064", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:06:48.547245+00:00", probability: "0.150508", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:11:25.974142+00:00", probability: "0.169246", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:17:25.818931+00:00", probability: "0.186516", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:21:56.090554+00:00", probability: "0.193495", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:27:50.421885+00:00", probability: "0.156802", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:32:25.965758+00:00", probability: "0.158817", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:36:55.848422+00:00", probability: "0.143678", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:41:26.109476+00:00", probability: "0.137956", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:47:26.024631+00:00", probability: "0.147702", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:51:55.997823+00:00", probability: "0.134923", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T05:56:25.840963+00:00", probability: "0.09471", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T06:02:25.916250+00:00", probability: "0.076834", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T06:06:55.965994+00:00", probability: "0.098442", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T06:11:34.934252+00:00", probability: "0.106962", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T06:17:26.152308+00:00", probability: "0.122442", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T06:21:56.159202+00:00", probability: "0.122143", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T06:27:55.986139+00:00", probability: "0.134161", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T06:32:25.936365+00:00", probability: "0.130462", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T06:36:56.060523+00:00", probability: "0.13489", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T06:41:26.165769+00:00", probability: "0.0", americanOdds: nil, bookmaker: "consensus"),
            GolfClosingRetainedPoint10868(timestamp: "2026-10-11T22:08:55.891004+00:00", probability: "0.012733", americanOdds: nil, bookmaker: "consensus"),
        ]),
    ]

    static let retainedLeaderboard: [GolfClosingRetainedLeader10868] = [
        GolfClosingRetainedLeader10868(name: "Michael Brennan", thru: "18", dgID: "29197", position: "1", todayScore: "-3", totalScore: "-16", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Jackson Suber", thru: "18", dgID: "29279", position: "T41", todayScore: "-1", totalScore: "-5", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Keita Nakajima", thru: "18", dgID: "21074", position: "T50", todayScore: "-3", totalScore: "-4", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Adam Scott", thru: "18", dgID: "6430", position: "T13", todayScore: "1", totalScore: "-11", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Stephan Jaeger", thru: "18", dgID: "16394", position: "T4", todayScore: "-1", totalScore: "-13", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Rickie Fowler", thru: "18", dgID: "12965", position: "71", todayScore: "5", totalScore: "9", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Jacob Bridgeman", thru: "18", dgID: "29433", position: "T2", todayScore: "-2", totalScore: "-15", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Keith Mitchell", thru: "18", dgID: "17365", position: "T2", todayScore: "-3", totalScore: "-15", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Ryan Gerard", thru: "18", dgID: "29767", position: "T4", todayScore: "-3", totalScore: "-13", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Brian Harman", thru: "18", dgID: "8825", position: "T4", todayScore: "-4", totalScore: "-13", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Xander Schauffele", thru: "18", dgID: "19895", position: "T4", todayScore: "-4", totalScore: "-13", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Kevin Roy", thru: "18", dgID: "18424", position: "T13", todayScore: "-3", totalScore: "-11", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Jordan Smith", thru: "18", dgID: "18586", position: "T4", todayScore: "-1", totalScore: "-13", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Zach Bauchou", thru: "18", dgID: "19846", position: "T9", todayScore: "1", totalScore: "-12", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Sungjae Im", thru: "18", dgID: "17488", position: "T9", todayScore: "-3", totalScore: "-12", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Min Woo Lee", thru: "18", dgID: "16841", position: "T9", todayScore: "-5", totalScore: "-12", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Ren Yonezawa", thru: "18", dgID: "25739", position: "T9", todayScore: "-7", totalScore: "-12", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Jordan Spieth", thru: "18", dgID: "14636", position: "T13", todayScore: "-4", totalScore: "-11", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Christiaan Bezuidenhout", thru: "18", dgID: "18103", position: "T17", todayScore: "-3", totalScore: "-10", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Nico Echavarria", thru: "18", dgID: "22833", position: "T33", todayScore: "-2", totalScore: "-6", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Mac Meissner", thru: "18", dgID: "28159", position: "T23", todayScore: "2", totalScore: "-8", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Lee Hodges", thru: "18", dgID: "25157", position: "T33", todayScore: "-1", totalScore: "-6", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Michael Kim", thru: "18", dgID: "17543", position: "T17", todayScore: "-1", totalScore: "-10", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Ben Kohles", thru: "18", dgID: "16395", position: "T17", todayScore: "-3", totalScore: "-10", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Billy Horschel", thru: "18", dgID: "11276", position: "T21", todayScore: "-4", totalScore: "-9", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Hideki Matsuyama", thru: "18", dgID: "13562", position: "T21", todayScore: "-4", totalScore: "-9", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Takumi Kanaya", thru: "18", dgID: "19729", position: "T23", todayScore: "-2", totalScore: "-8", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Rasmus Neergaard-Petersen", thru: "18", dgID: "23841", position: "T23", todayScore: "-4", totalScore: "-8", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Patrick Rodgers", thru: "18", dgID: "16283", position: "T29", todayScore: "-1", totalScore: "-7", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "John Parry", thru: "18", dgID: "13764", position: "T23", todayScore: "-3", totalScore: "-8", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Kosuke Sunagawa", thru: "18", dgID: "19682", position: "T23", todayScore: "-1", totalScore: "-8", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Justin Thomas", thru: "18", dgID: "14139", position: "T23", todayScore: "4", totalScore: "-8", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Ricky Castillo", thru: "18", dgID: "27819", position: "T29", todayScore: "-3", totalScore: "-7", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Tomohiro Ishizaka", thru: "18", dgID: "25538", position: "T29", todayScore: "-4", totalScore: "-7", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Denny McCarthy", thru: "18", dgID: "19870", position: "T29", todayScore: "-2", totalScore: "-7", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Max Homa", thru: "18", dgID: "17538", position: "T13", todayScore: "-1", totalScore: "-11", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Yoshinori Fujimoto", thru: "18", dgID: "11773", position: "T33", todayScore: "-5", totalScore: "-6", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Doug Ghim", thru: "18", dgID: "24550", position: "T17", todayScore: "-4", totalScore: "-10", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Ryo Hisatsune", thru: "18", dgID: "22760", position: "T41", todayScore: "1", totalScore: "-5", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Matt Wallace", thru: "18", dgID: "20706", position: "T50", todayScore: "-1", totalScore: "-4", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Jinichiro Kozuma", thru: "18", dgID: "14209", position: "T41", todayScore: "-3", totalScore: "-5", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Andrew Putnam", thru: "18", dgID: "14704", position: "T33", todayScore: "-1", totalScore: "-6", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Michael Thorbjornsen", thru: "18", dgID: "26649", position: "T33", todayScore: "0", totalScore: "-6", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Keegan Bradley", thru: "18", dgID: "13872", position: "T41", todayScore: "1", totalScore: "-5", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Tony Finau", thru: "18", dgID: "11676", position: "T41", todayScore: "-3", totalScore: "-5", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Beau Hossler", thru: "18", dgID: "15470", position: "T41", todayScore: "1", totalScore: "-5", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "David Lipsky", thru: "18", dgID: "15980", position: "T54", todayScore: "-1", totalScore: "-3", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Collin Morikawa", thru: "18", dgID: "22085", position: "T33", todayScore: "-2", totalScore: "-6", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Taylor Moore", thru: "18", dgID: "21944", position: "T41", todayScore: "-1", totalScore: "-5", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Nick Taylor", thru: "18", dgID: "13126", position: "T41", todayScore: "-2", totalScore: "-5", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Kristoffer Ventura", thru: "18", dgID: "15651", position: "T41", todayScore: "0", totalScore: "-5", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Pierceson Coody", thru: "18", dgID: "28309", position: "T50", todayScore: "-3", totalScore: "-4", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Matt McCarty", thru: "18", dgID: "28635", position: "T50", todayScore: "-6", totalScore: "-4", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Tom Hoge", thru: "18", dgID: "15575", position: "70", todayScore: "0", totalScore: "7", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Johnny Keefer", thru: "18", dgID: "32457", position: "T33", todayScore: "-4", totalScore: "-6", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Yusaku Hosono", thru: "18", dgID: "25797", position: "T33", todayScore: "-1", totalScore: "-6", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Max Greyserman", thru: "18", dgID: "23465", position: "T61", todayScore: "-3", totalScore: "-1", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Aguri Iwasaki", thru: "18", dgID: "28203", position: "T54", todayScore: "-4", totalScore: "-3", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Taylor Pendrith", thru: "18", dgID: "17780", position: "T54", todayScore: "-4", totalScore: "-3", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Chandler Phillips", thru: "18", dgID: "27164", position: "T54", todayScore: "-2", totalScore: "-3", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Davis Thompson", thru: "18", dgID: "27364", position: "T54", todayScore: "-2", totalScore: "-3", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Maverick McNealy", thru: "18", dgID: "18634", position: "T59", todayScore: "-4", totalScore: "-2", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Kevin Yu", thru: "18", dgID: "17881", position: "T59", todayScore: "-2", totalScore: "-2", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Kurt Kitayama", thru: "18", dgID: "21891", position: "T61", todayScore: "-5", totalScore: "-1", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Koshin Nagasaki", thru: "18", dgID: "31582", position: "69", todayScore: "2", totalScore: "6", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Wyndham Clark", thru: "18", dgID: "23604", position: "T63", todayScore: "-2", totalScore: "1", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Alex Smalley", thru: "18", dgID: "18474", position: "T63", todayScore: "-2", totalScore: "1", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Sang-hee Lee", thru: "18", dgID: "13923", position: "65", todayScore: "-1", totalScore: "2", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Steven Fisk", thru: "18", dgID: "26657", position: "T66", todayScore: "-4", totalScore: "3", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Hiroshi Iwata", thru: "18", dgID: "9099", position: "T66", todayScore: "-1", totalScore: "3", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Sahith Theegala", thru: "18", dgID: "23014", position: "68", todayScore: "0", totalScore: "5", currentRound: "4"),
        GolfClosingRetainedLeader10868(name: "Aldrich Potgieter", thru: "18", dgID: "27900", position: "72", todayScore: "3", totalScore: "11", currentRound: "4"),
    ]

    static let retainedPlayers: [GolfClosingRetainedPlayer10868] = [
        GolfClosingRetainedPlayer10868(position: "1", name: "Michael Brennan", score: "-16", totalScoreRaw: "-16", today: "-3", todayRaw: "-3", thru: "18", hole: "H18", winProb: "100.0", winProbChange: "0.0", positionChange: "0", top5Prob: "100.0", top10Prob: "100.0", top20Prob: "100.0", makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T2", name: "Jacob Bridgeman", score: "-15", totalScoreRaw: "-15", today: "-2", todayRaw: "-2", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: "100.0", top10Prob: "100.0", top20Prob: "100.0", makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T2", name: "Keith Mitchell", score: "-15", totalScoreRaw: "-15", today: "-3", todayRaw: "-3", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: "100.0", top10Prob: "100.0", top20Prob: "100.0", makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T4", name: "Stephan Jaeger", score: "-13", totalScoreRaw: "-13", today: "-1", todayRaw: "-1", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: "100.0", top10Prob: "100.0", top20Prob: "100.0", makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T4", name: "Ryan Gerard", score: "-13", totalScoreRaw: "-13", today: "-3", todayRaw: "-3", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: "100.0", top10Prob: "100.0", top20Prob: "100.0", makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T4", name: "Brian Harman", score: "-13", totalScoreRaw: "-13", today: "-4", todayRaw: "-4", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: "100.0", top10Prob: "100.0", top20Prob: "100.0", makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T4", name: "Xander Schauffele", score: "-13", totalScoreRaw: "-13", today: "-4", todayRaw: "-4", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: "100.0", top10Prob: "100.0", top20Prob: "100.0", makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T4", name: "Jordan Smith", score: "-13", totalScoreRaw: "-13", today: "-1", todayRaw: "-1", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: "100.0", top10Prob: "100.0", top20Prob: "100.0", makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T9", name: "Zach Bauchou", score: "-12", totalScoreRaw: "-12", today: "+1", todayRaw: "1", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: "100.0", top20Prob: "100.0", makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T9", name: "Sungjae Im", score: "-12", totalScoreRaw: "-12", today: "-3", todayRaw: "-3", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: "100.0", top20Prob: "100.0", makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T9", name: "Min Woo Lee", score: "-12", totalScoreRaw: "-12", today: "-5", todayRaw: "-5", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: "100.0", top20Prob: "100.0", makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T9", name: "Ren Yonezawa", score: "-12", totalScoreRaw: "-12", today: "-7", todayRaw: "-7", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: "100.0", top20Prob: "100.0", makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T13", name: "Adam Scott", score: "-11", totalScoreRaw: "-11", today: "+1", todayRaw: "1", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: "100.0", makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T13", name: "Kevin Roy", score: "-11", totalScoreRaw: "-11", today: "-3", todayRaw: "-3", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: "100.0", makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T13", name: "Jordan Spieth", score: "-11", totalScoreRaw: "-11", today: "-4", todayRaw: "-4", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: "100.0", makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T13", name: "Max Homa", score: "-11", totalScoreRaw: "-11", today: "-1", todayRaw: "-1", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: "100.0", makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T17", name: "Christiaan Bezuidenhout", score: "-10", totalScoreRaw: "-10", today: "-3", todayRaw: "-3", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: "100.0", makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T17", name: "Michael Kim", score: "-10", totalScoreRaw: "-10", today: "-1", todayRaw: "-1", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: "100.0", makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T17", name: "Ben Kohles", score: "-10", totalScoreRaw: "-10", today: "-3", todayRaw: "-3", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: "100.0", makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T17", name: "Doug Ghim", score: "-10", totalScoreRaw: "-10", today: "-4", todayRaw: "-4", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: "100.0", makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T21", name: "Billy Horschel", score: "-9", totalScoreRaw: "-9", today: "-4", todayRaw: "-4", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: nil, makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T21", name: "Hideki Matsuyama", score: "-9", totalScoreRaw: "-9", today: "-4", todayRaw: "-4", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: nil, makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T23", name: "Mac Meissner", score: "-8", totalScoreRaw: "-8", today: "+2", todayRaw: "2", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: nil, makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T23", name: "Takumi Kanaya", score: "-8", totalScoreRaw: "-8", today: "-2", todayRaw: "-2", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: nil, makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T23", name: "Rasmus Neergaard-Petersen", score: "-8", totalScoreRaw: "-8", today: "-4", todayRaw: "-4", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: nil, makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T23", name: "John Parry", score: "-8", totalScoreRaw: "-8", today: "-3", todayRaw: "-3", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: nil, makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T23", name: "Kosuke Sunagawa", score: "-8", totalScoreRaw: "-8", today: "-1", todayRaw: "-1", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: nil, makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T23", name: "Justin Thomas", score: "-8", totalScoreRaw: "-8", today: "+4", todayRaw: "4", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: nil, makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T29", name: "Patrick Rodgers", score: "-7", totalScoreRaw: "-7", today: "-1", todayRaw: "-1", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: nil, makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T29", name: "Ricky Castillo", score: "-7", totalScoreRaw: "-7", today: "-3", todayRaw: "-3", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: nil, makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T29", name: "Tomohiro Ishizaka", score: "-7", totalScoreRaw: "-7", today: "-4", todayRaw: "-4", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: nil, makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T29", name: "Denny McCarthy", score: "-7", totalScoreRaw: "-7", today: "-2", todayRaw: "-2", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: nil, makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T33", name: "Nico Echavarria", score: "-6", totalScoreRaw: "-6", today: "-2", todayRaw: "-2", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: nil, makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T33", name: "Lee Hodges", score: "-6", totalScoreRaw: "-6", today: "-1", todayRaw: "-1", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: nil, makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T33", name: "Yoshinori Fujimoto", score: "-6", totalScoreRaw: "-6", today: "-5", todayRaw: "-5", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: nil, makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T33", name: "Andrew Putnam", score: "-6", totalScoreRaw: "-6", today: "-1", todayRaw: "-1", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: nil, makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T33", name: "Michael Thorbjornsen", score: "-6", totalScoreRaw: "-6", today: "E", todayRaw: "0", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: nil, makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T33", name: "Collin Morikawa", score: "-6", totalScoreRaw: "-6", today: "-2", todayRaw: "-2", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: nil, makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T33", name: "Johnny Keefer", score: "-6", totalScoreRaw: "-6", today: "-4", todayRaw: "-4", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: nil, makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T33", name: "Yusaku Hosono", score: "-6", totalScoreRaw: "-6", today: "-1", todayRaw: "-1", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: nil, makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T41", name: "Jackson Suber", score: "-5", totalScoreRaw: "-5", today: "-1", todayRaw: "-1", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: nil, makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T41", name: "Ryo Hisatsune", score: "-5", totalScoreRaw: "-5", today: "+1", todayRaw: "1", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: nil, makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T41", name: "Jinichiro Kozuma", score: "-5", totalScoreRaw: "-5", today: "-3", todayRaw: "-3", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: nil, makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T41", name: "Keegan Bradley", score: "-5", totalScoreRaw: "-5", today: "+1", todayRaw: "1", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: nil, makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T41", name: "Tony Finau", score: "-5", totalScoreRaw: "-5", today: "-3", todayRaw: "-3", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: nil, makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T41", name: "Beau Hossler", score: "-5", totalScoreRaw: "-5", today: "+1", todayRaw: "1", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: nil, makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T41", name: "Taylor Moore", score: "-5", totalScoreRaw: "-5", today: "-1", todayRaw: "-1", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: nil, makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T41", name: "Nick Taylor", score: "-5", totalScoreRaw: "-5", today: "-2", todayRaw: "-2", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: nil, makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T41", name: "Kristoffer Ventura", score: "-5", totalScoreRaw: "-5", today: "E", todayRaw: "0", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: nil, makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T50", name: "Keita Nakajima", score: "-4", totalScoreRaw: "-4", today: "-3", todayRaw: "-3", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: nil, makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T50", name: "Matt Wallace", score: "-4", totalScoreRaw: "-4", today: "-1", todayRaw: "-1", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: nil, makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T50", name: "Pierceson Coody", score: "-4", totalScoreRaw: "-4", today: "-3", todayRaw: "-3", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: nil, makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T50", name: "Matt McCarty", score: "-4", totalScoreRaw: "-4", today: "-6", todayRaw: "-6", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: nil, makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T54", name: "David Lipsky", score: "-3", totalScoreRaw: "-3", today: "-1", todayRaw: "-1", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: nil, makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T54", name: "Aguri Iwasaki", score: "-3", totalScoreRaw: "-3", today: "-4", todayRaw: "-4", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: nil, makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T54", name: "Taylor Pendrith", score: "-3", totalScoreRaw: "-3", today: "-4", todayRaw: "-4", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: nil, makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T54", name: "Chandler Phillips", score: "-3", totalScoreRaw: "-3", today: "-2", todayRaw: "-2", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: nil, makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T54", name: "Davis Thompson", score: "-3", totalScoreRaw: "-3", today: "-2", todayRaw: "-2", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: nil, makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T59", name: "Maverick McNealy", score: "-2", totalScoreRaw: "-2", today: "-4", todayRaw: "-4", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: nil, makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T59", name: "Kevin Yu", score: "-2", totalScoreRaw: "-2", today: "-2", todayRaw: "-2", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: nil, makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T61", name: "Max Greyserman", score: "-1", totalScoreRaw: "-1", today: "-3", todayRaw: "-3", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: nil, makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T61", name: "Kurt Kitayama", score: "-1", totalScoreRaw: "-1", today: "-5", todayRaw: "-5", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: nil, makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T63", name: "Wyndham Clark", score: "+1", totalScoreRaw: "1", today: "-2", todayRaw: "-2", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: nil, makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T63", name: "Alex Smalley", score: "+1", totalScoreRaw: "1", today: "-2", todayRaw: "-2", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: nil, makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "65", name: "Sang-hee Lee", score: "+2", totalScoreRaw: "2", today: "-1", todayRaw: "-1", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: nil, makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T66", name: "Steven Fisk", score: "+3", totalScoreRaw: "3", today: "-4", todayRaw: "-4", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: nil, makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "T66", name: "Hiroshi Iwata", score: "+3", totalScoreRaw: "3", today: "-1", todayRaw: "-1", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: nil, makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "68", name: "Sahith Theegala", score: "+5", totalScoreRaw: "5", today: "E", todayRaw: "0", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: nil, makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "69", name: "Koshin Nagasaki", score: "+6", totalScoreRaw: "6", today: "+2", todayRaw: "2", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: nil, makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "70", name: "Tom Hoge", score: "+7", totalScoreRaw: "7", today: "E", todayRaw: "0", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: nil, makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "71", name: "Rickie Fowler", score: "+9", totalScoreRaw: "9", today: "+5", todayRaw: "5", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: nil, makeCutProb: "100.0", currentRound: "4"),
        GolfClosingRetainedPlayer10868(position: "72", name: "Aldrich Potgieter", score: "+11", totalScoreRaw: "11", today: "+3", todayRaw: "3", thru: "18", hole: "H18", winProb: "0.0", winProbChange: "0.0", positionChange: "0", top5Prob: nil, top10Prob: nil, top20Prob: nil, makeCutProb: "100.0", currentRound: "4"),
    ]

    static let retainedBoundaries: [GolfClosingRetainedBoundary10868] = [
        GolfClosingRetainedBoundary10868(timestamp: "2026-10-08T00:02:03.231914+00:00", label: "R1"),
        GolfClosingRetainedBoundary10868(timestamp: "2026-10-09T00:02:01.806162+00:00", label: "R2"),
        GolfClosingRetainedBoundary10868(timestamp: "2026-10-10T00:01:32.121700+00:00", label: "R3"),
        GolfClosingRetainedBoundary10868(timestamp: "2026-10-11T00:02:37.532470+00:00", label: "R4"),
    ]
}
// @@END GENERATED FIXTURE@@
