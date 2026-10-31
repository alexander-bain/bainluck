import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the soccer page BEFORE kickoff: Design's approved default story
/// membership (the total goal outlook and the full-match / first-half
/// exact-score map), explicit owner admission of any other card, the same
/// exact-score leaf on the page and in the full-size reader, the host's held
/// scope and score, and another event's markets admitting nothing.
///
/// Built through the host's pure `build` on RETAINED REAL bodies
/// (`SoccerRetained10868`, `SoccerExactRetained10868` — sources, hashes and
/// subset rules are in their own files) with the CONSTRUCTED owner admission
/// `SoccerExactRetained10868.hullBeforeAdmission` (no owner supplies one yet).
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
@MainActor
final class SoccerBeforePage10868Tests: XCTestCase {
    private typealias F = SoccerRetained10868
    private typealias X = SoccerExactRetained10868
    private typealias P = SoccerPageInputAdapter10868
    private typealias R = SoccerPropReadingAdapter10868
    private typealias Host = SoccerEventPageHost10868

    private func built(detail: String = F.hullDetail, history: String? = F.hullHistory,
                       markets: String? = X.hullExactMarkets, admitted: R.Markets = X.hullBeforeAdmission,
                       now: Date = F.hullNow, halvesAdmission: P.HalvesAdmission = .routeDefault,
                       admittedCards: Set<SoccerEventPageCard10868> = [],
                       reading: Host.Reading = Host.Reading()) throws -> Host.Built {
        let event = try F.detail(detail)
        return Host.build(event: event, history: try history.map { try F.history($0) },
                          markets: try markets.map { try F.markets($0) }, admitted: admitted,
                          halvesAdmission: halvesAdmission, admittedCards: admittedCards,
                          probabilityObservedAt: event.heroProbabilityObservedAt?.asDate, now: now,
                          reading: reading, calendar: F.pacific, locale: F.locale)
    }

    // MARK: - Default membership

    func testTheRouteMembershipTable() {
        XCTAssertEqual(P.routeCards(.before), [.goals, .exact])
        XCTAssertEqual(P.routeCards(.live), [.goals, .both, .first])
        XCTAssertEqual(P.routeCards(.final), [.goals, .both, .first, .halves])
        XCTAssertFalse(P.offers(.both, phase: .before, admitted: []))
        XCTAssertFalse(P.offers(.first, phase: .before, admitted: []))
        XCTAssertFalse(P.offers(.halves, phase: .before, admitted: []))
        XCTAssertTrue(P.offers(.both, phase: .before, admitted: [.both]))
        XCTAssertFalse(P.offers(.exact, phase: .live, admitted: []))
        XCTAssertTrue(P.offers(.exact, phase: .final, admitted: [.exact]))
        XCTAssertFalse(P.offers(.history, phase: .before, admitted: [.history]))
    }

    /// Before kickoff the page offers the goal outlook and the exact-score map,
    /// composed from the match's own served rows — and not both teams, first
    /// team or half by half, although each has content here.
    func testBeforeKickoffTheDefaultOfferingIsTheGoalOutlookAndTheExactScoreMapAndNothingElse() throws {
        let page = try built()
        let input = page.input
        XCTAssertEqual(input.phase, .before)
        XCTAssertEqual(input.stream.cards.map(\.id), ["goals", "exact"])
        XCTAssertEqual(input.stream.cards.map(\.name), [P.Words.goalOutlook, P.Words.exact])
        XCTAssertEqual(input.stories, [.init(cardID: "goals", card: .goals), .init(cardID: "exact", card: .exact)])
        XCTAssertEqual(input.stream.primary?.id, "goals")
        XCTAssertEqual(input.stream.next?.id, "exact")

        // Composed, not just filtered: the outlook's stems and every listed score.
        XCTAssertEqual(input.goals?.markStyle, .stems)
        XCTAssertEqual(input.goals?.phase, .before)
        XCTAssertEqual(input.goals?.milestones.map(\.quantityLabel), ["1+", "2+"])
        XCTAssertEqual(input.exact?.phase, .before)
        XCTAssertEqual(input.exact?.scopes.map(\.id), ["full", "first"])
        XCTAssertEqual(input.exact?.scopes.map { $0.originals.count }, [37, 9])

        let event = try F.detail(F.hullDetail)
        let markets = try F.markets(X.hullExactMarkets)
        let props = F.propHost(F.hullNow)
        XCTAssertNotNil(SoccerBothTeamsAdapter10868.input(event, markets: markets, admitted: X.hullBeforeAdmission.both,
                                                          host: props))
        XCTAssertNotNil(SoccerFirstTeamAdapter10868.input(event, markets: markets, history: try F.history(F.hullHistory),
                                                          admitted: X.hullBeforeAdmission.first, host: props))
        XCTAssertNotNil(SoccerHalvesAdapter10868.input(event, markets: markets, admitted: X.hullBeforeAdmission.halves,
                                                       host: props))
        XCTAssertNil(input.both)
        XCTAssertNil(input.first)
        XCTAssertNil(input.halves)
        let model = SoccerEventPageModel10868(input)
        for card in [SoccerEventPageCard10868.both, .first, .halves] {
            XCTAssertFalse(model.isMounted(card), "\(card)")
            XCTAssertNil(model.storyCard(card.rawValue), "\(card)")
        }

        // Every original — exact scores of both scopes, both teams, first team —
        // is still in All props.
        let identities = Set(try XCTUnwrap(page.originals.catalogue).originals.map(\.identity))
        for (market, side) in [("62939468", "237459055"), ("62939468", "245266693"), ("64002155", "244588610"),
                               ("63390540", "238847205"), ("62939466", "238846913"), ("62939503", "237498595")] {
            XCTAssertTrue(identities.contains(.init(source: "polymarket", market: market, side: side)), "\(market) \(side)")
        }
    }

    func testAnExplicitAdmissionStillAddsACardBeforeKickoff() throws {
        let both = try built(admittedCards: [.both])
        XCTAssertEqual(both.input.stream.cards.map(\.id), ["goals", "exact", "both"])
        XCTAssertNotNil(both.input.both)
        XCTAssertNil(both.input.first)

        let halves = try built(halvesAdmission: .explicit)
        XCTAssertEqual(halves.input.stream.cards.map(\.id), ["goals", "exact", "halves"])
        XCTAssertNotNil(halves.input.halves)

        let all = try built(halvesAdmission: .explicit, admittedCards: [.first, .both])
        XCTAssertEqual(all.input.stream.cards.map(\.id), ["goals", "exact", "both", "first", "halves"])
    }

    /// During play the live route is unchanged; after the final the map is
    /// offered only when the owner admits it — and then still lists all nine
    /// first-half originals, unconfirmed.
    func testDuringPlayAndAfterTheFinalTheExactMapIsOfferedOnlyWhenAdmitted() throws {
        let live = try built(detail: F.liveDetail, history: F.liveHistory, markets: F.liveMarkets,
                             admitted: F.liveAdmission, now: F.liveNow)
        XCTAssertEqual(live.input.stream.cards.map(\.id), ["goals", "both", "first"])
        XCTAssertNil(live.input.exact)

        let final = try built(detail: X.hullFinalDetail, history: nil, markets: X.hullFinalMarkets, now: X.finalNow)
        XCTAssertEqual(final.input.phase, .final)
        XCTAssertNil(final.input.exact)
        XCTAssertFalse(final.input.stream.cards.map(\.id).contains("exact"))

        let admitted = try built(detail: X.hullFinalDetail, history: nil, markets: X.hullFinalMarkets, now: X.finalNow,
                                 admittedCards: [.exact])
        XCTAssertEqual(admitted.input.stream.cards.map(\.id), ["exact"])
        XCTAssertEqual(admitted.input.exact?.phase, .final)
        XCTAssertEqual(admitted.input.exact?.scopes.map { $0.originals.count }, [37, 9])
        XCTAssertTrue(admitted.input.exact?.scopes[1].originals.allSatisfy {
            $0.result == .unconfirmed(R.Words.resultUnavailable)
        } ?? false)
    }

    /// The slot is optional: without the owner's descriptor the before page
    /// offers the outlook alone and nothing else changes.
    func testWithoutADescriptorTheBeforePageOffersTheOutlookAlone() throws {
        var admission = X.hullBeforeAdmission
        admission.exactScore = nil
        let page = try built(admitted: admission)
        XCTAssertEqual(page.input.stream.cards.map(\.id), ["goals"])
        XCTAssertNil(page.input.exact)
        XCTAssertFalse(SoccerEventPageModel10868(page.input).isMounted(.exact))
        XCTAssertFalse(SoccerEventPageModel10868(page.input).readerShows(.exact))
    }

    // MARK: - Another event

    func testAnotherEventsMarketsOrDescriptorAdmitNothing() throws {
        // CONSTRUCTED: the pregame markets body with only `event_id` changed.
        let foreign = try built(markets: try F.edited(X.hullExactMarkets, setting: ["event_id": 15311090]))
        XCTAssertNil(foreign.input.exact)
        XCTAssertNil(foreign.input.goals)
        XCTAssertTrue(foreign.input.stream.cards.isEmpty)
        XCTAssertNil(foreign.originals.catalogue)

        // CONSTRUCTED: the descriptor with only its event id changed.
        var admission = X.hullBeforeAdmission
        admission.exactScore = SoccerExactScoreAdapter10868.Descriptor(eventID: 15311090, scopes: X.hullDescriptor.scopes)
        let elsewhere = try built(admitted: admission)
        XCTAssertNil(elsewhere.input.exact)
        XCTAssertEqual(elsewhere.input.stream.cards.map(\.id), ["goals"])
    }

    // MARK: - All props

    /// CONSTRUCTED live variant: the Hull detail with only `status` changed; the
    /// pregame markets body with only `observed_at` changed on the full-match
    /// 1–1 row and the first-half 0–0 row. The descriptor's first-half market
    /// reaches All props as a period, so its recent quote stays historical.
    func testTheHostTellsAllPropsTheFirstHalfExactMarketIsAPeriod() throws {
        let stamp = "2026-10-11T13:15:00+00:00"
        let detail = try F.edited(F.hullDetail, setting: ["status": "live"])
        var markets = try F.editedRow(X.hullExactMarkets, outcomeID: 238846931, setting: ["observed_at": stamp])
        markets = try F.editedRow(markets, outcomeID: 244588607, setting: ["observed_at": stamp])

        func original(_ built: Host.Built, _ market: String, _ side: String) throws -> OriginalMarketDetails9483.Original {
            try XCTUnwrap(built.originals.catalogue?.originals.first {
                $0.identity == OriginalMarketDetails9483.Identity(source: "polymarket", market: market, side: side)
            })
        }
        let page = try built(detail: detail, markets: markets, now: X.liveNow)
        XCTAssertEqual(try original(page, "64002155", "244588607").later,
                       OriginalMarketDetails9483.Reading.missing(SoccerOriginalsAdapter10868.Words.inPlayUnavailable))
        XCTAssertEqual(try original(page, "64002155", "244588607").about.historicalQuote?.text, formatProbability(0.307))
        let fullMatch = try original(page, "62939468", "238846931").later?.figure
        guard case .value? = fullMatch else {
            return XCTFail("the full-match quote on its own recent clock is the current chance")
        }

        // Without the descriptor nothing says that market is a half.
        var admission = X.hullBeforeAdmission
        admission.exactScore = nil
        let unknown = try built(detail: detail, markets: markets, admitted: admission, now: X.liveNow)
        let unmarked = try original(unknown, "64002155", "244588607").later?.figure
        guard case .value? = unmarked else {
            return XCTFail("no owner said this market is a half")
        }
    }

    // MARK: - Held scope and score

    func testTheHeldScopeAndScoreReachTheMapAndRecoveryNamesTheFirstListedScore() throws {
        let both = ["first": "244588607", "full": "237459055"]
        let held = try built(reading: Host.Reading(exactScope: "first", exactOriginals: both))
        let map = try XCTUnwrap(held.input.exact)
        XCTAssertEqual(map.selectedScopeID, "first")
        XCTAssertEqual(map.selectedOriginalID, "244588607")
        XCTAssertNil(Host.recovery(map))

        // Back to the full match: its own held score comes back with it.
        let back = try built(reading: Host.Reading(exactScope: "full", exactOriginals: both))
        XCTAssertEqual(back.input.exact?.selectedOriginalID, "237459055")

        // A held score the scope does not list stays selected and reads
        // unavailable; the recovery names the owner's first listed score there.
        let stale = try built(reading: Host.Reading(exactScope: "first", exactOriginals: ["first": "237459055"]))
        let staleMap = try XCTUnwrap(stale.input.exact)
        XCTAssertEqual(staleMap.selectedOriginalID, "237459055")
        XCTAssertEqual(staleMap.originalSelection(in: try XCTUnwrap(staleMap.scopeSelection.scope)), .missing("237459055"))
        XCTAssertEqual(Host.recovery(staleMap)?.scope, "first")
        XCTAssertEqual(Host.recovery(staleMap)?.original, "244588607")

        // Nothing held: the owner's first scope, no score chosen.
        let fresh = try XCTUnwrap(try built().input.exact)
        XCTAssertEqual(fresh.selectedScopeID, "full")
        XCTAssertNil(fresh.selectedOriginalID)
        XCTAssertEqual(Host.recovery(fresh)?.original, "238846934")
    }

    // MARK: - The page and the reader

    func testThePageAndTheReaderMountTheSameExactScoreLeafWithTheSameInput() throws {
        let input = try built().input
        let model = SoccerEventPageModel10868(input)
        XCTAssertEqual(model.storyCard("exact"), .exact)
        XCTAssertTrue(model.isMounted(.exact))
        XCTAssertTrue(model.readerShows(.exact))
        XCTAssertNotNil(input.exact)
        XCTAssertEqual(SoccerEventPagePresentation10868(input: input).exactContent()?.input, input.exact)
        XCTAssertEqual(SoccerEventPagePresentation10868(input: input, mode: .reader(.exact)).exactContent()?.input,
                       input.exact)
        XCTAssertEqual(SoccerEventPagePresentation10868(input: input, mode: .reader(.goals)).goalsContent()?.input,
                       input.goals)
        XCTAssertEqual(Host.Presented(mode: .reader(.exact)).id, "reader.exact")
        XCTAssertEqual(SoccerEventPageAccessibilityID10868.card(.exact), "soccerEventPage10868.card.exact")
    }

    func testAMapOfAnotherPhaseIsNotMountedAndTheDefaultSlotIsEmpty() throws {
        let before = try built().input
        let finalMap = try XCTUnwrap(try built(detail: X.hullFinalDetail, history: nil, markets: X.hullFinalMarkets,
                                               now: X.finalNow, admittedCards: [.exact]).input.exact)
        let leaky = SoccerEventPageInput10868(
            phase: .before, header: before.header, headline: before.headline, history: before.history,
            goals: before.goals, both: nil, first: nil, halves: nil, exact: finalMap,
            stream: before.stream, stories: before.stories, copy: before.copy)
        let model = SoccerEventPageModel10868(leaky)
        XCTAssertNil(model.exact)
        XCTAssertFalse(model.isMounted(.exact))
        XCTAssertNil(model.storyCard("exact"))
        XCTAssertNil(SoccerEventPagePresentation10868(input: leaky, mode: .reader(.exact)).exactContent())

        // An existing caller that never names the slot: empty.
        let plain = SoccerEventPageInput10868(
            phase: .before, header: before.header, headline: before.headline, history: before.history,
            goals: before.goals, both: nil, first: nil, halves: nil,
            stream: before.stream, stories: before.stories, copy: before.copy)
        XCTAssertNil(plain.exact)
        XCTAssertFalse(SoccerEventPageModel10868(plain).readerShows(.exact))
    }

    /// The host holds the exact card in the stream: each of its actions asks
    /// the stream's hold first, then reaches the host's exact callback. The
    /// reader passes the callback straight through; no callback, no action.
    func testAnExactMapActionInTheStreamRequestsTheHoldFirstAndTheReaderPassesItStraightThrough() throws {
        var log: [String] = []
        let input = try built(reading: Host.Reading(story: .exact)).input
        XCTAssertEqual(input.stream.primary?.id, "exact")
        let view = SoccerEventPagePresentation10868(
            input: input,
            onExactSelectScope: { log.append("scope:\($0)") },
            onExactSelectOriginal: { log.append("score:\($0):\($1)") },
            onExactDetails: { log.append("details:\($0):\($1)") },
            onExactRecover: { log.append("recover") })

        let stream = input.stream
        let resolved = stream.resolve(reduceMotion: false, actionable: true)
        let ref = StoryStreamPresentation10868.CardRef(scope: stream.scope, id: "exact")
        let activation = StoryStreamCardActivation10868(
            card: ref, intents: stream.activationIntents(for: ref, resolved: resolved)) { intent in
            if case .interaction(_, let card) = intent { log.append("hold:\(card?.id ?? "-")") } else { log.append("other") }
        }
        XCTAssertTrue(activation.isAvailable)

        // Building the card acts on nothing.
        let card = try XCTUnwrap(view.exactContent(activation: activation))
        XCTAssertEqual(card.input, input.exact)
        XCTAssertEqual(log, [])

        card.onSelectScope?("first")
        card.onSelectOriginal?("first", "244588607")
        card.onDetails?("full", "237459055")
        card.onRecoverSelection?()
        XCTAssertEqual(log, ["hold:exact", "scope:first", "hold:exact", "score:first:244588607",
                             "hold:exact", "details:full:237459055", "hold:exact", "recover"])

        // Full-size content: the host's exact callback, no hold.
        log = []
        let reader = SoccerEventPagePresentation10868(input: input, mode: .reader(.exact),
                                                      onExactSelectOriginal: { log.append("score:\($0):\($1)") })
        reader.exactContent()?.onSelectOriginal?("full", "238846934")
        XCTAssertEqual(log, ["score:full:238846934"])

        // No host callback: no control, even inside the stream.
        let quiet = SoccerEventPagePresentation10868(input: input)
        XCTAssertNil(quiet.exactContent(activation: activation)?.onSelectOriginal)
        XCTAssertNil(quiet.exactContent(activation: activation)?.onSelectScope)
        XCTAssertNil(quiet.exactContent()?.onDetails)
        XCTAssertNil(quiet.exactContent()?.onRecoverSelection)
        XCTAssertEqual(log, ["score:full:238846934"])
    }

    // MARK: - Fit

    /// Hosted through `hostForMeasurement`, so the text size is an argument.
    func testTheBeforePageAndTheFullSizeCardsFitAPhoneWidthAtStandardAndAccessibilityText() throws {
        let input = try built().input
        for size in [DynamicTypeSize.large, .accessibility3] {
            for mode in [SoccerEventPageMode10868.page, .reader(.exact), .reader(.goals)] {
                let host = hostForMeasurement(
                    SoccerEventPagePresentation10868(input: input, mode: mode, onAllProps: {},
                                                     onExactSelectScope: { _ in },
                                                     onExactSelectOriginal: { _, _ in },
                                                     onExactRecover: {})
                        .environment(\.horizontalSizeClass, .compact),
                    at: size)
                let fitted = host.sizeThatFits(in: CGSize(width: 375, height: CGFloat.greatestFiniteMagnitude))
                XCTAssertLessThanOrEqual(fitted.width, 375, "\(mode) at \(size) must not scroll sideways")
            }
        }
    }
}
