import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the hockey journey adapter, part four ("All props": the original
/// catalogue and its Details), on REAL served `/game-markets` and
/// `/api/events/{id}` bodies decoded exactly as the app decodes them
/// (`.convertFromSnakeCase`, `APIClient`).
///
/// REDUCED VERBATIM SUBSETS. Each kept value — a market row, a top-level
/// scalar, a served empty family array — is the server's bytes, in source
/// order, asserted as a byte-for-byte substring of its source file by
/// `/tmp/cli-10868-h4/make_subsets.py` (run `python3 -I make_subsets.py
/// <design-dir> <out> <manifest>`). Only the envelope is assembled: which keys
/// are kept, the line breaks between rows, and a family keeps only its listed
/// rows (a family with none kept is omitted). Sources under
/// `artifacts/discovery-containers-release-plan/event-page-design-20261011/`:
/// - `wildBruinsMarkets` — `atlas-v6/raw/nhl-15169793-game-markets.json`
///   (sha256 3abba0f2…06dc), Minnesota Wild 4–1 Boston Bruins, completed:
///   totals[0] of 9, player_props[41, 60, 66] of 83 (the screen author's three
///   originals), team_totals[3] of 10, spreads[0, 2] of 9, other[0, 1] of 38.
///   The full body serves 149 outcomes, the author's "149 retained originals".
/// - `wildBruinsDetail` — `atlas-v6/raw/nhl-15169793-detail.json` (a11c662d…a348),
///   top-level scalars only.
/// - `islandersWildMarkets` — `cli-candidate-20261030/retained-payloads/
///   nhl-15338034-game-markets-20261030T201355Z.json` (0227bebf…29c6), New York
///   Islanders 4–3 Minnesota Wild (Final/OT): player_props[14, 118, 119] of 140,
///   spreads[0] of 14, other[0, 1] of 2.
/// - `islandersWildDetail` — `…/nhl-15338034-detail-20261030T201355Z.json` (4bd4832c…d6e4).
/// - `devilsKnightsMarkets` — `…/nhl-15338496-game-markets-20261030T201355Z.json`
///   (8e475781…cd4a), New Jersey Devils at Vegas Golden Knights, scheduled for
///   22:00Z, captured 20:13:55Z: totals[0] of 9, player_props[60, 61] of 105,
///   team_totals[0] of 10, spreads[0, 1] of 16, other[0–3] of 4.
/// - `devilsKnightsDetail` — `…/nhl-15338496-detail-20261030T201355Z.json` (50fbf467…c1da).
///
/// Every row in all three full bodies serves `_market_id` and exactly one
/// `contributor_outcome_ids` entry, and no two rows share them.
///
/// CONSTRUCTED here, and only here: the reader's calendar (Pacific, en_US),
/// `now`, the tint, the held selection, and — named in each test that does it —
/// a decoded event `status` changed (no live NHL body is retained; a pregame
/// body read as final shows served null settlements), one decoded
/// settlement field on a player-prop row cleared or flipped, the served
/// listed start moved, or one decoded quote clock moved. Expected clock words
/// come from part one's own formatter.
@MainActor
final class HockeyJourneyOriginalsAdapter10868Tests: XCTestCase {
    private typealias A = HockeyJourneyOriginalsAdapter10868
    private typealias Page = HockeyJourneyPageAdapter10868
    private typealias Originals = OriginalMarketDetails9483

    private static let pacific: Calendar = {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "America/Los_Angeles")!
        return calendar
    }()

    /// The screen author's three identities (`HockeyJourneyEventPagePresentation10868Tests`).
    private static let kaprizovTwo = Originals.Identity(source: "kalshi", market: "64871068", side: "243945029")
    private static let hughesTwoAssists = Originals.Identity(source: "kalshi", market: "64870807", side: "243939188")
    private static let hughesThree = Originals.Identity(source: "kalshi", market: "64871068", side: "243945042")

    private func decoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }

    private func detail(_ json: String) throws -> EventDetail {
        try decoder().decode(EventDetail.self, from: Data(json.utf8))
    }

    private func markets(_ json: String) throws -> GameMarketsResponse {
        try decoder().decode(GameMarketsResponse.self, from: Data(json.utf8))
    }

    private func host(_ now: String) -> A.Host {
        A.Host(now: now.asDate!, calendar: Self.pacific, locale: Locale(identifier: "en_US"))
    }

    private func clock(_ iso: String?, _ host: A.Host) -> String {
        Page.clockWords(iso!.asDate!, host: host.page)
    }

    private func original(_ page: HockeyJourneyPageOriginals10868, _ identity: Originals.Identity) throws -> Originals.Original {
        try XCTUnwrap(page.catalogue?.originals.first { $0.identity == identity }, "\(identity)")
    }

    private func original(_ page: HockeyJourneyPageOriginals10868, outcome: String) throws -> Originals.Original {
        try XCTUnwrap(page.catalogue?.originals.first { $0.outcome == outcome }, outcome)
    }

    private func content(_ page: HockeyJourneyPageOriginals10868, _ identity: Originals.Identity) -> Originals.Content? {
        guard let catalogue = page.catalogue else { return nil }
        return Originals.content(catalogue: catalogue,
                                 selection: Originals.Selection(scope: catalogue.scope, identity: identity))
    }

    /// `(source, _market_id, contributor_outcome_ids)` straight off every decoded row.
    private func servedIdentities(_ data: GameMarketsResponse) -> [Originals.Identity] {
        func id(_ source: String?, _ market: Int?, _ outcomes: [Int]?) -> Originals.Identity {
            Originals.Identity(source: source ?? "", market: market.map(String.init) ?? "",
                               side: (outcomes ?? []).map(String.init).joined(separator: "+"))
        }
        let lines = (data.totals ?? []) + (data.spreads ?? []) + (data.teamTotals ?? [])
        return lines.map { id($0.source, $0._marketId, $0.contributorOutcomeIds) }
            + (data.playerProps ?? []).map { id($0.source, $0._marketId, $0.contributorOutcomeIds) }
            + (data.other ?? []).map { id($0.source, $0._marketId, $0.contributorOutcomeIds) }
    }

    // MARK: Membership, order, identity

    func testEveryCatalogueOutcomeIsOneOriginalInTheCataloguesOwnOrderUnderItsServedIds() throws {
        let event = try detail(Self.wildBruinsDetail)
        let served = try markets(Self.wildBruinsMarkets)
        let host = host("2026-10-11T04:56:41Z")
        let page = A.originals(event, markets: served, host: host, tint: .blue)
        let catalogue = try XCTUnwrap(page.catalogue)
        XCTAssertEqual(catalogue.scope, "nhl:15169793:final:originals")

        let groups = QuestionCatalog9483.build(served, status: event.status, now: host.now)
        XCTAssertEqual(catalogue.originals.map { [$0.title, $0.outcome] },
                       groups.flatMap { group in group.outcomes.map { [group.question, $0.label] } })
        XCTAssertEqual(catalogue.originals.map(\.outcome), [
            "Over 1.5 goals scored", "Wild", "Boston wins by over 1.5 goals", "Minnesota over 4.5",
            "Quinn Hughes: 2+", "Kirill Kaprizov: 2+", "Quinn Hughes: 3+", "Tanner Jeannot", "Blake Coleman",
        ], "game lines, team scoring, player props, other — the catalogue's family order")
        XCTAssertEqual(catalogue.originals.count, QuestionCatalog9483.sourceOutcomeCount(served))
        XCTAssertEqual(page.context, "9 originals")

        let identities = catalogue.originals.map(\.identity)
        XCTAssertEqual(Set(identities).count, identities.count, "one original per identity")
        XCTAssertEqual(Set(identities), Set(servedIdentities(served)), "every identity is a row's own served ids")
        for identity in [Self.kaprizovTwo, Self.hughesTwoAssists, Self.hughesThree] {
            XCTAssertTrue(identities.contains(identity), "\(identity)")
        }
        XCTAssertEqual(page.labels[Self.kaprizovTwo], "Kirill Kaprizov 2+ points")
        XCTAssertEqual(page.labels[Self.hughesTwoAssists], "Quinn Hughes 2+ assists")
        XCTAssertEqual(page.labels[Self.hughesThree], "Quinn Hughes 3+ points")
        let total = try original(page, outcome: "Over 1.5 goals scored")
        XCTAssertEqual(page.labels[total.identity], "Over 1.5 goals scored")
        XCTAssertEqual(page.heading, "All props")
        XCTAssertEqual(page.emptyWords, "No retained originals for this game")
        XCTAssertEqual(page.unavailableChoice, "Unnamed original")
    }

    // MARK: Final

    func testAtTheFinalEachOriginalIsGradedByItsOwnSettlementAndNoSettledPriceIsAChance() throws {
        let event = try detail(Self.wildBruinsDetail)
        let served = try markets(Self.wildBruinsMarkets)
        let held = Originals.Selection(scope: "nhl:15169793:final:originals", identity: Self.kaprizovTwo)
        let page = A.originals(event, markets: served, host: host("2026-10-11T04:56:41Z"), tint: .blue, selection: held)
        let originals = try XCTUnwrap(page.catalogue?.originals)
        XCTAssertEqual(page.selection, held, "the held selection is passed through unchanged")
        for o in originals {
            XCTAssertEqual(o.mode, .result, o.outcome)
            XCTAssertNil(o.later)
            // Every row serves a settled 1.0 / 0.0 and no pregame_mark: no pregame chance at all.
            XCTAssertEqual(o.pregame, .missing("No pregame chance"), o.outcome)
            XCTAssertEqual(o.about.rules, .unavailable("Rules unavailable"))
        }
        XCTAssertEqual(originals.map { $0.grade?.words }, ["Won", "Won", "Lost", "Lost", "Lost", "Won", "Lost", "Won", "Lost"])
        XCTAssertEqual(originals.map { $0.grade?.provenance }, [
            "Settled by Kalshi", "Settled by Polymarket", "Settled by Kalshi", "Settled by Kalshi", "Settled by Kalshi",
            "Settled by Kalshi", "Settled by Kalshi", "Settled by Kalshi", "Settled by Kalshi",
        ])
        XCTAssertEqual(OutcomeVerdict.won.label, "Won")

        let shown = try XCTUnwrap(content(page, Self.kaprizovTwo))
        XCTAssertEqual(shown.readings.map(\.text), ["No pregame chance"])
        XCTAssertEqual(shown.result, Originals.ShownResult(words: "Won", provenance: "Settled by Kalshi"))
        XCTAssertEqual(shown.about, [
            Originals.Row(label: "Market", value: "Boston vs Minnesota: Points"),
            Originals.Row(label: "Outcome", value: "Kirill Kaprizov: 2+"),
            Originals.Row(label: "Source", value: "Kalshi"),
            Originals.Row(label: "Market ID", value: "64871068"),
            Originals.Row(label: "Outcome ID", value: "243945029"),
        ])
        XCTAssertEqual(shown.rules, .unavailable("Rules unavailable"))
        for o in originals {
            let readings = content(page, o.identity)?.readings.map(\.text) ?? []
            XCTAssertFalse(readings.contains { [">99%", "<1%", "100%", "0%"].contains($0) }, o.outcome)
        }
    }

    func testUnknownSettlementIsNotYetConfirmedAndNeverLost() throws {
        // CONSTRUCTED: the pregame body read as final. Its rows serve is_winner / resolution_source null.
        var event = try detail(Self.devilsKnightsDetail)
        event.status = "completed"
        let pregame = try markets(Self.devilsKnightsMarkets)
        let page = A.originals(event, markets: pregame, host: host("2026-10-31T06:00:00Z"), tint: .blue)
        let originals = try XCTUnwrap(page.catalogue?.originals)
        XCTAssertEqual(originals.count, 10)
        for o in originals {
            XCTAssertEqual(o.mode, .result)
            XCTAssertEqual(o.grade, Originals.Grade(words: "Not yet confirmed", provenance: "No settlement served"), o.outcome)
        }
        // After the start an over-side player prop keeps its served mark; other rows have none.
        let eichel = try XCTUnwrap(pregame.playerProps?.first { $0.outcomeName == "Jack Eichel: 1+" })
        let mark = try XCTUnwrap(eichel.pregameMark)
        XCTAssertEqual(try original(page, outcome: "Jack Eichel: 1+").pregame,
                       .value(formatProbability(mark), placement: mark, provenance: "Saved before the start · Kalshi"))
        XCTAssertEqual(try original(page, outcome: "Vegas over 1.5").pregame, .missing("No pregame chance"))

        // CONSTRUCTED: one decoded player-prop settlement cleared, retracted, or contradicted by its served hit.
        let event2 = try detail(Self.wildBruinsDetail)
        let base = try markets(Self.wildBruinsMarkets)
        func kaprizovGrade(_ edit: (inout GameMarketPlayerProp) -> Void) throws -> Originals.Grade? {
            var served = base
            let i = try XCTUnwrap(served.playerProps?.firstIndex { $0.outcomeName == "Kirill Kaprizov: 2+" })
            edit(&served.playerProps![i])
            let page = A.originals(event2, markets: served, host: host("2026-10-11T04:56:41Z"), tint: .blue)
            return try original(page, Self.kaprizovTwo).grade
        }
        XCTAssertEqual(try kaprizovGrade { _ in }?.words, "Won")
        XCTAssertEqual(try kaprizovGrade { $0.isWinner = nil },
                       Originals.Grade(words: "Not yet confirmed", provenance: "No settlement served"))
        XCTAssertEqual(try kaprizovGrade { $0.resolutionSource = "ungradeable_result" }?.words, "Not yet confirmed")
        XCTAssertEqual(try kaprizovGrade { $0.isWinner = false },
                       Originals.Grade(words: "Not yet confirmed", provenance: "Served settlement and grade disagree"),
                       "a served loss beside a served hit is not picked either way")
        XCTAssertNil(A.settlement(isWinner: false, resolutionSource: nil))
        XCTAssertEqual(A.settlement(isWinner: false, resolutionSource: "api_settlement"), false)
    }

    func testOncePlayHasStartedThePregameReadingIsTheServedMarkAndIdentitiesHoldAcrossPhases() throws {
        let event = try detail(Self.islandersWildDetail)
        let served = try markets(Self.islandersWildMarkets)
        let finished = A.originals(event, markets: served, host: host("2026-10-30T20:13:55Z"), tint: .blue)
        let originals = try XCTUnwrap(finished.catalogue?.originals)
        XCTAssertEqual(originals.map(\.outcome),
                       ["Wild", "Emil Heineman: 2+", "Kirill Kaprizov: 1+", "Kirill Kaprizov: 2+", "New York Islanders", "Minnesota"])
        for (target, mark) in [("1+", 0.61), ("2+", 0.39)] {
            let o = try original(finished, outcome: "Kirill Kaprizov: \(target)")
            let row = try XCTUnwrap(served.playerProps?.first { $0.outcomeName == "Kirill Kaprizov: \(target)" })
            XCTAssertEqual(row.pregameMark, mark)
            XCTAssertEqual(o.pregame, .value(formatProbability(mark), placement: mark, provenance: "Saved before the start · Kalshi"),
                           "the served mark, never the settled over_probability \(row.overProbability ?? -1)")
        }
        // Heineman 2+ is served with no mark; it borrows nothing.
        XCTAssertEqual(try original(finished, outcome: "Emil Heineman: 2+").pregame, .missing("No pregame chance"))
        XCTAssertEqual(try original(finished, outcome: "Wild").pregame, .missing("No pregame chance"))
        XCTAssertEqual(originals.map { $0.grade?.words }, ["Won", "Lost", "Won", "Lost", "Won", "Lost"])

        // CONSTRUCTED: the same body with its decoded status set to `live`.
        var live = event
        live.status = "live"
        let during = A.originals(live, markets: served, host: host("2026-10-30T01:00:00Z"), tint: .blue)
        XCTAssertEqual(during.catalogue?.originals.map(\.identity), originals.map(\.identity))
        XCTAssertEqual(during.catalogue?.scope, "nhl:15338034:live:originals")
        XCTAssertEqual(finished.catalogue?.scope, "nhl:15338034:final:originals")
        XCTAssertEqual(during.labels, finished.labels)
    }

    // MARK: Before

    func testBeforeTheStartThePregameReadingIsTheCataloguesOwnPriceOnItsOwnRecentClock() throws {
        let event = try detail(Self.devilsKnightsDetail)
        let served = try markets(Self.devilsKnightsMarkets)
        let host = host("2026-10-30T20:13:55Z")
        let page = A.originals(event, markets: served, host: host, tint: .blue)
        let originals = try XCTUnwrap(page.catalogue?.originals)
        XCTAssertEqual(originals.map(\.outcome), ["Over 1.5 goals scored", "Devils", "Golden Knights", "Vegas over 1.5",
                                                  "Jack Eichel: 1+", "Jack Eichel: 2+", "Vegas", "New Jersey",
                                                  "Golden Knights", "Devils"])
        XCTAssertEqual(page.context, "10 originals")
        for o in originals {
            XCTAssertEqual(o.mode, .pregame)
            XCTAssertNil(o.later)
            XCTAssertNil(o.grade)
        }
        let eichel = try XCTUnwrap(served.playerProps?.first { $0.outcomeName == "Jack Eichel: 1+" })
        let price = try XCTUnwrap(eichel.overProbability)
        let first = try original(page, outcome: "Jack Eichel: 1+")
        XCTAssertEqual(first.pregame, .value(formatProbability(price), placement: price,
                                             provenance: "\(clock(eichel.observedAt, host)) · Kalshi"))
        XCTAssertNotEqual(first.pregame.placement, eichel.pregameMark, "the opening-line mark is not the chance before the start")
        XCTAssertEqual(page.labels[first.identity], "Jack Eichel 1+ points")

        // The Polymarket spread was last observed at 15:44Z, hours before this read: no pregame chance.
        let spreadRow = try XCTUnwrap(served.spreads?.first)
        XCTAssertEqual(try original(page, outcome: "Vegas over 1.5").pregame.figure,
                       .value(formatProbability(try XCTUnwrap(served.teamTotals?.first?.overProbability))))
        let devils = try XCTUnwrap(page.catalogue?.originals.first { $0.title == spreadRow.marketName && $0.outcome == "Devils" })
        XCTAssertEqual(devils.pregame, .missing(AllMarketsCatalogView9483.noRecentPrice))
        XCTAssertEqual(devils.identity, Originals.Identity(source: "polymarket", market: "68189231", side: "255929341"))
        let knights = try XCTUnwrap(page.catalogue?.originals.last { $0.outcome == "Golden Knights" })
        let knightsRow = try XCTUnwrap(served.other?.first { $0.source == "polymarket" && $0.outcomeName == "Golden Knights" })
        XCTAssertEqual(knights.pregame, .value(formatProbability(try XCTUnwrap(knightsRow.probability)),
                                               placement: knightsRow.probability,
                                               provenance: "\(clock(knightsRow.observedAt, host)) · Polymarket"))
        XCTAssertEqual(content(page, first.identity)?.readings.map(\.label), ["Pregame chance"])
    }

    // MARK: During play

    func testDuringPlayACurrentPriceIsCurrentAStaleOneIsHistoricalAndASettledOneIsNoChance() throws {
        // CONSTRUCTED: the pregame body with its decoded status set to `live` and its listed start
        // moved from 22:00Z to 15:30Z, read at 20:30Z — so its 20:12Z quotes and its 15:44Z
        // spread are all observed during play. Every served quote byte is unchanged.
        let listed = #""commence_time":"2026-10-30T22:00:00+00:00""#
        let moved = Self.devilsKnightsDetail.replacingOccurrences(
            of: listed, with: #""commence_time":"2026-10-30T15:30:00+00:00""#)
        XCTAssertNotEqual(moved, Self.devilsKnightsDetail)
        var event = try detail(moved)
        XCTAssertEqual(event.commenceTime, "2026-10-30T15:30:00+00:00")
        event.status = "live"
        let served = try markets(Self.devilsKnightsMarkets)
        let host = host("2026-10-30T20:30:00Z")
        let page = A.originals(event, markets: served, host: host, tint: .blue)
        XCTAssertEqual(page.catalogue?.scope, "nhl:15338496:live:originals")

        // Observed at 20:12Z, after the start and 18 minutes before this read: the current chance.
        let eichel = try XCTUnwrap(served.playerProps?.first { $0.outcomeName == "Jack Eichel: 1+" })
        let first = try original(page, outcome: "Jack Eichel: 1+")
        XCTAssertEqual(first.mode, .comparison(.current))
        XCTAssertEqual(first.later, .value(formatProbability(try XCTUnwrap(eichel.overProbability)), placement: eichel.overProbability,
                                           provenance: "Recorded \(clock(eichel.observedAt, host)) · Kalshi"))
        XCTAssertNil(first.about.historicalQuote, "a current chance is not also a historical quote")
        let mark = try XCTUnwrap(eichel.pregameMark)
        XCTAssertEqual(first.pregame, .value(formatProbability(mark), placement: mark, provenance: "Saved before the start · Kalshi"))
        XCTAssertEqual(content(page, first.identity)?.readings.map(\.label), ["Pregame chance", "Current chance"])

        // Observed at 15:44Z — stale for the catalogue: no headline figure, the quote only in Details.
        let spreadRow = try XCTUnwrap(served.spreads?.first)
        let price = try XCTUnwrap(spreadRow.probability)
        let devils = try XCTUnwrap(page.catalogue?.originals.first { $0.title == spreadRow.marketName && $0.outcome == "Devils" })
        XCTAssertEqual(QuestionCatalog9483.build(served, status: "live", now: host.now)
                           .first { $0.question == spreadRow.marketName }?.outcomes.first?.absence, .stale)
        XCTAssertEqual(devils.mode, .comparison(.current))
        XCTAssertEqual(devils.later, .missing(AllMarketsCatalogView9483.noRecentPrice))
        XCTAssertEqual(devils.pregame, .missing("No pregame chance"))
        let recorded = "\(clock(spreadRow.observedAt, host)) · Polymarket"
        XCTAssertEqual(devils.about.historicalQuote, Originals.HistoricalQuote(text: formatProbability(price), recorded: recorded))

        let card = try XCTUnwrap(OriginalMarketCatalogue9483.cards(catalogue: page.catalogue, selection: page.selection,
                                                                   labels: page.labels, unavailableChoice: page.unavailableChoice)
            .first { $0.choice.selection?.identity == devils.identity })
        let face = try XCTUnwrap(card.content)
        XCTAssertEqual(face.readings.map(\.label), ["Pregame chance", "Current chance"])
        XCTAssertEqual(face.readings.map(\.text), ["No pregame chance", "No recent probability update"])
        XCTAssertFalse(face.readings.contains { $0.isValue }, "the catalogue card draws no figure for the stale quote")
        XCTAssertTrue(face.marks.isEmpty)
        XCTAssertEqual(face.about, [
            Originals.Row(label: "Market", value: "Spread: Golden Knights (-1.5)"),
            Originals.Row(label: "Outcome", value: "Devils"),
            Originals.Row(label: "Source", value: "Polymarket"),
            Originals.Row(label: "Market ID", value: "68189231"),
            Originals.Row(label: "Outcome ID", value: "255929341"),
            Originals.Row(label: "Last recorded probability (historical)",
                          value: "\(formatProbability(price)), recorded \(recorded)"),
        ], "the quote, its own clock and its own venue, in Details only")

        // CONSTRUCTED: the 15169793 final body with its decoded status set to `live`. Every row is settled.
        var settledEvent = try detail(Self.wildBruinsDetail)
        settledEvent.status = "live"
        let settled = A.originals(settledEvent, markets: try markets(Self.wildBruinsMarkets),
                                  host: self.host("2026-10-04T02:50:00Z"), tint: .blue)
        XCTAssertEqual(try original(settled, outcome: "Tanner Jeannot").later, .missing("No current chance"),
                       "a settled 1.0 is a result, never a current chance")
        XCTAssertEqual(try original(settled, Self.kaprizovTwo).later, .missing("No current chance"))
        // Coleman serves no price and no clock: the catalogue's own words.
        XCTAssertEqual(try original(settled, outcome: "Blake Coleman").later,
                       .missing(AllMarketsCatalogView9483.unavailablePrice))
        for o in try XCTUnwrap(settled.catalogue?.originals) {
            if case .value? = o.later?.figure { XCTFail("no settled row shows a chance: \(o.outcome)") }
            XCTAssertNil(o.about.historicalQuote, "a settled 1.0 / 0.0 is never saved as a price: \(o.outcome)")
            XCTAssertNil(o.grade, "no grade before the final")
        }
    }

    func testDuringPlayAStillRecentQuoteFromBeforeTheStartIsNotTheCurrentChanceAndStaysHistorical() throws {
        // CONSTRUCTED: the pregame body with its decoded status set to `live`, read at 22:05Z, five
        // minutes after its served 22:00Z start, and one decoded quote clock — Jack Eichel 1+ —
        // moved from 20:12Z to 21:50Z: fifteen minutes old, but observed before the start.
        var event = try detail(Self.devilsKnightsDetail)
        event.status = "live"
        var served = try markets(Self.devilsKnightsMarkets)
        let i = try XCTUnwrap(served.playerProps?.firstIndex { $0.outcomeName == "Jack Eichel: 1+" })
        served.playerProps![i].observedAt = "2026-10-30T21:50:00+00:00"
        let eichel = served.playerProps![i]
        let host = host("2026-10-30T22:05:00Z")
        XCTAssertEqual(event.commenceTime, "2026-10-30T22:00:00+00:00", "the served listed start, unchanged")
        XCTAssertTrue(NFLMilestoneCard9483.isRecent(eichel.observedAt, now: host.now))
        XCTAssertEqual(QuestionCatalog9483.build(served, status: event.status, now: host.now)
                           .flatMap(\.outcomes).first { $0.label == "Jack Eichel: 1+" }?.probability,
                       eichel.overProbability, "the catalogue still admits the quote")
        let page = A.originals(event, markets: served, host: host, tint: .blue)
        XCTAssertEqual(page.catalogue?.scope, "nhl:15338496:live:originals")

        let identity = Originals.Identity(source: "kalshi", market: "68282128", side: "256284771")
        let first = try original(page, identity)
        XCTAssertEqual(first.outcome, "Jack Eichel: 1+")
        XCTAssertEqual(first.mode, .comparison(.current))
        XCTAssertEqual(first.later, .missing("No in-game reading"), "a pregame quote is not the current chance")
        let price = try XCTUnwrap(eichel.overProbability)
        let recorded = "\(clock(eichel.observedAt, host)) · Kalshi"
        XCTAssertEqual(first.about.historicalQuote, Originals.HistoricalQuote(text: formatProbability(price), recorded: recorded))
        let mark = try XCTUnwrap(eichel.pregameMark)
        XCTAssertEqual(first.pregame, .value(formatProbability(mark), placement: mark, provenance: "Saved before the start · Kalshi"),
                       "the served baseline, unchanged")

        let shown = try XCTUnwrap(content(page, identity))
        XCTAssertEqual(shown.readings.map(\.label), ["Pregame chance", "Current chance"])
        XCTAssertEqual(shown.readings.map(\.text), [formatProbability(mark), "No in-game reading"])
        XCTAssertEqual(shown.readings.map(\.isValue), [true, false], "no later chance is borrowed")
        XCTAssertEqual(shown.marks.compactMap(\.placement), [mark])
        XCTAssertEqual(shown.about.last, Originals.Row(label: "Last recorded probability (historical)",
                                                       value: "\(formatProbability(price)), recorded \(recorded)"))

        // Part three refuses the same row for the same reason.
        let h3 = HockeyJourneyContributionAdapter10868.Host(boxScore: nil, now: host.now, calendar: Self.pacific,
                                                            locale: Locale(identifier: "en_US"))
        XCTAssertEqual(HockeyJourneyContributionAdapter10868.inGameReading(eichel, reachedSoFar: false, event: event, host: h3),
                       .unavailable("No in-game reading"))

        // Every quote in this body was observed before the start: none is a current chance,
        // and each keeps its own quote — the 2+ never the 1+'s.
        let second = try original(page, outcome: "Jack Eichel: 2+")
        let secondRow = try XCTUnwrap(served.playerProps?.first { $0.outcomeName == "Jack Eichel: 2+" })
        XCTAssertEqual(second.about.historicalQuote,
                       Originals.HistoricalQuote(text: formatProbability(try XCTUnwrap(secondRow.overProbability)),
                                                 recorded: "\(clock(secondRow.observedAt, host)) · Kalshi"))
        for o in try XCTUnwrap(page.catalogue?.originals) {
            if case .value? = o.later?.figure { XCTFail("no pregame quote is a current chance: \(o.outcome)") }
        }
    }

    // MARK: Empty and selection

    func testNoServedMarketsIsNoCatalogueAndASelectionResolvesOnlyInItsOwnScope() throws {
        let event = try detail(Self.wildBruinsDetail)
        let host = host("2026-10-11T04:56:41Z")
        let empty = A.originals(event, markets: nil, host: host, tint: .blue)
        XCTAssertNil(empty.catalogue)
        XCTAssertNil(empty.context)
        XCTAssertTrue(empty.labels.isEmpty)
        XCTAssertEqual(empty.emptyWords, "No retained originals for this game")

        let page = A.originals(event, markets: try markets(Self.wildBruinsMarkets), host: host, tint: .blue)
        let catalogue = try XCTUnwrap(page.catalogue)
        XCTAssertNotNil(Originals.original(in: catalogue, selection: Originals.Selection(scope: catalogue.scope,
                                                                                        identity: Self.hughesThree)))
        XCTAssertNil(Originals.original(in: catalogue, selection: Originals.Selection(scope: "nhl:15169793:live:originals",
                                                                                     identity: Self.hughesThree)),
                     "a selection held in another phase's scope is no original")
        XCTAssertEqual(A.matched(try markets(Self.wildBruinsMarkets), status: event.status, now: host.now).map(\.source.outcomeName),
                       catalogue.originals.map(\.outcome), "each listed outcome maps back to its own served row")
    }

    // MARK: Retained payloads (reduced verbatim subsets)

    /// `atlas-v6/raw/nhl-15169793-game-markets.json` · sha256 3abba0f2f3c0a4875a394e3f82d7bf14cea76c2dfd690d6b61490b477a7806dc
    static let wildBruinsMarkets = ##"""
{"event_id":15169793,
"home_team":"Minnesota Wild",
"away_team":"Boston Bruins",
"home_score":4,
"away_score":1,
"status":"completed",
"totals":[
{"threshold":1.5,"over_probability":1.0,"source":"kalshi","market_type":"game_total","market_name":"Boston vs Minnesota: Total Goals","outcome_name":"Over 1.5 goals scored","observed_at":"2026-10-04T02:46:43.395259+00:00","contributor_outcome_ids":[239380538],"is_winner":true,"resolution_source":"api_settlement","movement":0.05,"period":null,"_market_id":63539066,"_external_id":"KXNHLTOTAL-26OCT03BOSMIN"}
],
"player_props":[
{"market_name":"Boston vs Minnesota: Assists","outcome_name":"Quinn Hughes: 2+","observed_at":null,"contributor_outcome_ids":[243939188],"threshold":2.0,"over_probability":0.0,"opening_over_probability":null,"pregame_mark":null,"_inverted":false,"source":"kalshi","movement":null,"_market_id":64870807,"actual":1.0,"hit":false,"is_winner":false,"resolution_source":"api_settlement","player_headshot":"https://a.espncdn.com/i/headshots/nhl/players/full/4320548.png","player_team":"home"},
{"market_name":"Boston vs Minnesota: Points","outcome_name":"Kirill Kaprizov: 2+","observed_at":null,"contributor_outcome_ids":[243945029],"threshold":2.0,"over_probability":1.0,"opening_over_probability":null,"pregame_mark":null,"_inverted":false,"source":"kalshi","movement":null,"_market_id":64871068,"actual":2.0,"hit":true,"is_winner":true,"resolution_source":"api_settlement","player_headshot":"https://a.espncdn.com/i/headshots/nhl/players/full/3942335.png","player_team":"home"},
{"market_name":"Boston vs Minnesota: Points","outcome_name":"Quinn Hughes: 3+","observed_at":null,"contributor_outcome_ids":[243945042],"threshold":3.0,"over_probability":0.0,"opening_over_probability":null,"pregame_mark":null,"_inverted":false,"source":"kalshi","movement":null,"_market_id":64871068,"actual":2.0,"hit":false,"is_winner":false,"resolution_source":"api_settlement","player_headshot":"https://a.espncdn.com/i/headshots/nhl/players/full/4320548.png","player_team":"home"}
],
"team_totals":[
{"threshold":4.5,"over_probability":0.0,"source":"kalshi","market_type":"team_total","market_name":"Boston vs Minnesota: Team Total","outcome_name":"Minnesota over 4.5","observed_at":"2026-10-04T02:52:43.848887+00:00","contributor_outcome_ids":[240052021],"is_winner":false,"resolution_source":"api_settlement","movement":-0.265,"period":null,"_market_id":63728034,"_external_id":"KXNHLTEAMTOTAL-26OCT03BOSMIN","team_name":"Minnesota Wild","team_side":"home"}
],
"spreads":[
{"market_name":"Spread: Wild (-1.5)","outcome_name":"Wild","observed_at":"2026-10-04T04:33:39.287544+00:00","contributor_outcome_ids":[238404189],"threshold":null,"probability":1.0,"source":"polymarket","is_winner":true,"resolution_source":"api_settlement","_market_id":63253211},
{"market_name":"Boston vs Minnesota: Spread","outcome_name":"Boston wins by over 1.5 goals","observed_at":"2026-10-04T02:46:43.395259+00:00","contributor_outcome_ids":[239380485],"threshold":1.5,"probability":0.0,"source":"kalshi","is_winner":false,"resolution_source":"api_settlement","_market_id":63539055,"_score_proves_verdict":true}
],
"period_markets":[],
"closed_period_markets":[],
"matchups":[],
"other":[
{"market_name":"Boston vs Minnesota: First Goalscorer","outcome_name":"Tanner Jeannot","observed_at":null,"contributor_outcome_ids":[243940876],"probability":1.0,"source":"kalshi","is_winner":true,"resolution_source":"api_settlement","_market_id":64870910},
{"market_name":"Boston vs Minnesota: First Goalscorer","outcome_name":"Blake Coleman","observed_at":null,"contributor_outcome_ids":[243940844],"probability":null,"source":"kalshi","is_winner":false,"resolution_source":"api_settlement","_market_id":64870910}
],
"during_player_props":null,
"after_player_props":null}
"""##

    /// `atlas-v6/raw/nhl-15169793-detail.json` · sha256 a11c662df1fd7c94c080cf0c7455c6771da9f8f38de3a44517a0a633f03ea348
    static let wildBruinsDetail = ##"""
{"id":15169793,
"external_id":"3a9af73961ea2f2322255a6fca4d421e",
"sport":"icehockey_nhl",
"sport_name":"NHL",
"home_team":"Minnesota Wild",
"away_team":"Boston Bruins",
"commence_time":"2026-10-04T00:00:00+00:00",
"start_is_tbd":false,
"completed_at":"2026-10-04T02:48:56.423990+00:00",
"status":"completed",
"home_score":4,
"away_score":1,
"score_source":"espn",
"score_observed_at":"2026-10-04T05:59:38.451734+00:00"}
"""##

    /// `shipping-adoption-20261027/cli-candidate-20261030/retained-payloads/nhl-15338034-game-markets-20261030T201355Z.json` · sha256 0227bebf7912f86eea5db0f62244702f776f26761daca6afba691ad1a89e29c6
    static let islandersWildMarkets = ##"""
{"event_id":15338034,
"home_team":"Minnesota Wild",
"away_team":"New York Islanders",
"home_score":3,
"away_score":4,
"status":"completed",
"player_props":[
{"market_name":"New York Islanders vs Minnesota: Assists","outcome_name":"Emil Heineman: 2+","observed_at":null,"contributor_outcome_ids":[256051725],"threshold":2.0,"over_probability":0.0,"opening_over_probability":null,"pregame_mark":null,"_inverted":false,"source":"kalshi","movement":null,"_market_id":68152126,"actual":1.0,"hit":false,"is_winner":false,"resolution_source":"api_settlement","player_headshot":"https://a.espncdn.com/i/headshots/nhl/players/full/4697447.png","player_team":"away"},
{"market_name":"New York Islanders vs Minnesota: Points","outcome_name":"Kirill Kaprizov: 1+","observed_at":"2026-10-30T02:42:35.327617+00:00","contributor_outcome_ids":[255781664],"threshold":1.0,"over_probability":1.0,"opening_over_probability":0.61,"pregame_mark":0.61,"_inverted":false,"source":"kalshi","movement":0.39,"_market_id":68152110,"actual":1.0,"hit":true,"is_winner":true,"resolution_source":"api_settlement","player_headshot":"https://a.espncdn.com/i/headshots/nhl/players/full/3942335.png","player_team":"home"},
{"market_name":"New York Islanders vs Minnesota: Points","outcome_name":"Kirill Kaprizov: 2+","observed_at":"2026-10-30T02:42:35.327617+00:00","contributor_outcome_ids":[255781674],"threshold":2.0,"over_probability":0.0,"opening_over_probability":0.39,"pregame_mark":0.39,"_inverted":false,"source":"kalshi","movement":-0.39,"_market_id":68152110,"actual":1.0,"hit":false,"is_winner":false,"resolution_source":"api_settlement","player_headshot":"https://a.espncdn.com/i/headshots/nhl/players/full/3942335.png","player_team":"home"}
],
"spreads":[
{"market_name":"Spread: Islanders (-3.5)","outcome_name":"Wild","observed_at":"2026-10-29T21:57:12.466350+00:00","contributor_outcome_ids":[255531737],"threshold":null,"probability":0.9995,"source":"polymarket","is_winner":true,"resolution_source":"api_settlement","_market_id":68080454}
],
"period_markets":[],
"closed_period_markets":[],
"matchups":[],
"other":[
{"market_name":"New York Islanders vs Minnesota","outcome_name":"New York Islanders","observed_at":"2026-10-30T02:42:35.327617+00:00","contributor_outcome_ids":[251976603],"probability":1.0,"source":"kalshi","is_winner":true,"resolution_source":"api_settlement","market_type":"moneyline","_market_id":67099173},
{"market_name":"New York Islanders vs Minnesota","outcome_name":"Minnesota","observed_at":"2026-10-30T02:42:35.327617+00:00","contributor_outcome_ids":[251976602],"probability":null,"source":"kalshi","is_winner":false,"resolution_source":"api_settlement","market_type":"moneyline","_market_id":67099173}
],
"during_player_props":null,
"after_player_props":null}
"""##

    /// `shipping-adoption-20261027/cli-candidate-20261030/retained-payloads/nhl-15338034-detail-20261030T201355Z.json` · sha256 4bd4832c10c7f31626a9cd31df415ef806db1f5a8c9ac1934aba3386d7fbd6e4
    static let islandersWildDetail = ##"""
{"id":15338034,
"external_id":"5020318cfd7098bd38fae6c907029f0f",
"sport":"icehockey_nhl",
"sport_name":"NHL",
"home_team":"Minnesota Wild",
"away_team":"New York Islanders",
"commence_time":"2026-10-30T00:00:00+00:00",
"start_is_tbd":false,
"completed_at":"2026-10-30T02:43:40.379936+00:00",
"status":"completed",
"home_score":3,
"away_score":4,
"score_source":"espn",
"score_observed_at":"2026-10-30T05:59:37.684442+00:00"}
"""##

    /// `shipping-adoption-20261027/cli-candidate-20261030/retained-payloads/nhl-15338496-game-markets-20261030T201355Z.json` · sha256 8e475781f15a79de89253a56485a4da4a303e2f219d503208267aedd77fecd4a
    static let devilsKnightsMarkets = ##"""
{"event_id":15338496,
"home_team":"Vegas Golden Knights",
"away_team":"New Jersey Devils",
"home_score":null,
"away_score":null,
"status":"scheduled",
"totals":[
{"threshold":1.5,"over_probability":0.985,"source":"kalshi","market_type":"game_total","market_name":"New Jersey vs Vegas: Total Goals","outcome_name":"Over 1.5 goals scored","observed_at":"2026-10-30T20:12:00.557237+00:00","contributor_outcome_ids":[256052503],"is_winner":null,"resolution_source":null,"movement":0.0,"period":null,"_market_id":68223043,"_external_id":"KXNHLTOTAL-26OCT30NJVGK"}
],
"player_props":[
{"market_name":"New Jersey vs Vegas: Points","outcome_name":"Jack Eichel: 1+","observed_at":"2026-10-30T20:12:00.557237+00:00","contributor_outcome_ids":[256284771],"threshold":1.0,"over_probability":0.685,"opening_over_probability":0.645,"pregame_mark":0.645,"_inverted":false,"source":"kalshi","movement":0.04,"_market_id":68282128,"player_headshot":"https://a.espncdn.com/i/headshots/nhl/players/full/3648002.png","player_team":"home"},
{"market_name":"New Jersey vs Vegas: Points","outcome_name":"Jack Eichel: 2+","observed_at":"2026-10-30T20:12:00.557237+00:00","contributor_outcome_ids":[256284786],"threshold":2.0,"over_probability":0.345,"opening_over_probability":0.355,"pregame_mark":0.355,"_inverted":false,"source":"kalshi","movement":-0.01,"_market_id":68282128,"player_headshot":"https://a.espncdn.com/i/headshots/nhl/players/full/3648002.png","player_team":"home"}
],
"team_totals":[
{"threshold":1.5,"over_probability":0.82,"source":"kalshi","market_type":"team_total","market_name":"New Jersey vs Vegas: Team Total","outcome_name":"Vegas over 1.5","observed_at":"2026-10-30T20:12:17.473027+00:00","contributor_outcome_ids":[256052592],"is_winner":null,"resolution_source":null,"movement":-0.005,"period":null,"_market_id":68223052,"_external_id":"KXNHLTEAMTOTAL-26OCT30NJVGK","team_name":"Vegas Golden Knights","team_side":"home"}
],
"spreads":[
{"market_name":"Spread: Golden Knights (-1.5)","outcome_name":"Devils","observed_at":"2026-10-30T15:44:32.991246+00:00","contributor_outcome_ids":[255929341],"threshold":null,"probability":0.705,"source":"polymarket","is_winner":null,"resolution_source":null,"_market_id":68189231},
{"market_name":"Spread: Golden Knights (-1.5)","outcome_name":"Golden Knights","observed_at":"2026-10-30T15:44:32.991246+00:00","contributor_outcome_ids":[255929340],"threshold":null,"probability":0.295,"source":"polymarket","is_winner":null,"resolution_source":null,"_market_id":68189231}
],
"period_markets":[],
"closed_period_markets":[],
"matchups":[],
"other":[
{"market_name":"New Jersey vs Vegas","outcome_name":"Vegas","observed_at":"2026-10-30T20:12:00.557237+00:00","contributor_outcome_ids":[252350463],"probability":0.505,"source":"kalshi","is_winner":null,"resolution_source":null,"market_type":"moneyline","_market_id":67203985},
{"market_name":"New Jersey vs Vegas","outcome_name":"New Jersey","observed_at":"2026-10-30T20:12:00.557237+00:00","contributor_outcome_ids":[252350464],"probability":0.495,"source":"kalshi","is_winner":null,"resolution_source":null,"market_type":"moneyline","_market_id":67203985},
{"market_name":"Devils vs. Golden Knights","outcome_name":"Golden Knights","observed_at":"2026-10-30T20:04:08.736025+00:00","contributor_outcome_ids":[249013789],"probability":0.505,"source":"polymarket","is_winner":null,"resolution_source":null,"market_type":"moneyline","_market_id":66245701},
{"market_name":"Devils vs. Golden Knights","outcome_name":"Devils","observed_at":"2026-10-30T20:05:31.122728+00:00","contributor_outcome_ids":[249013788],"probability":0.495,"source":"polymarket","is_winner":null,"resolution_source":null,"market_type":"moneyline","_market_id":66245701}
],
"during_player_props":null,
"after_player_props":null}
"""##

    /// `shipping-adoption-20261027/cli-candidate-20261030/retained-payloads/nhl-15338496-detail-20261030T201355Z.json` · sha256 50fbf4678a308e40481340e9b998a2a0870795dd8b04dfdfb05e31caf3dcc1da
    static let devilsKnightsDetail = ##"""
{"id":15338496,
"external_id":"5c712e15e1cd4b9283b4bf410fb334f4",
"sport":"icehockey_nhl",
"sport_name":"NHL",
"home_team":"Vegas Golden Knights",
"away_team":"New Jersey Devils",
"commence_time":"2026-10-30T22:00:00+00:00",
"start_is_tbd":false,
"completed_at":null,
"status":"scheduled",
"home_score":null,
"away_score":null}
"""##
}
