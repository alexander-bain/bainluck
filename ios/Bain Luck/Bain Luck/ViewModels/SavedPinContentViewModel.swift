import Combine
import Foundation

/// #10011 — what My Stuff can draw for one saved pin that the team feed did not
/// carry. Build 33 showed pins only when they were ALSO in the followed-team
/// feed (`vm.items.filter(savedIDs)`), so a pinned market or another sport's
/// game had no content anywhere in My Stuff.
nonisolated enum SavedPinContent: Sendable {
    case event(FeedEventData)
    case market(FeedFuturesData)
    /// The server answered 404/410: the item is gone, the pin is not.
    case unavailable
    case failed

    /// The management list's vocabulary, so a fallback row reuses its titles.
    var metadata: PinMetadata? {
        switch self {
        case .event(let e): return .available(title: "\(e.awayTeam) at \(e.homeTeam)")
        case .market(let f): return .available(title: f.name)
        case .unavailable: return .unavailable
        case .failed: return .failed
        }
    }

    var hasCard: Bool {
        switch self {
        case .event, .market: return true
        case .unavailable, .failed: return false
        }
    }

    /// The server said something about the item — a card or "gone". A failed
    /// read said nothing, so it never replaces one of these.
    var isAnswer: Bool {
        if case .failed = self { return false }
        return true
    }

    /// The Pinned section, in saved-pin order. A pin the team feed already
    /// carries keeps that feed card (it has the reason/headline); every other
    /// pin with loaded content becomes the same card family built from its
    /// detail payload. Pins with nothing to draw yet are `fallbacks` — they stay
    /// listed and removable rather than disappearing. A confirmed gone answer
    /// (404/410) outranks a feed card for the same item: the feed can still
    /// carry a deleted row, and that card would read as a live game. A failed
    /// read says nothing about the item, so it never displaces the feed card.
    static func section(
        pins: [SavedPin],
        feed: [FeedItem],
        content: [SavedPin: SavedPinContent]
    ) -> (items: [FeedItem], fallbacks: [SavedPin]) {
        var items: [FeedItem] = []
        var fallbacks: [SavedPin] = []
        for pin in pins {
            if case .unavailable = content[pin] {
                fallbacks.append(pin)
                continue
            }
            if let fed = feed.first(where: { matches($0, pin) }) {
                items.append(fed)
                continue
            }
            switch content[pin] {
            case .event(let e) where pin.type == "event":
                items.append(item(type: "event", event: e, futures: nil))
            case .market(let f) where pin.type == "future":
                items.append(item(type: "futures", event: nil, futures: f))
            default:
                fallbacks.append(pin)
            }
        }
        return (items, fallbacks)
    }

    private static func matches(_ item: FeedItem, _ pin: SavedPin) -> Bool {
        if pin.type == "event", item.type == "event", let e = item.event { return e.id == pin.value }
        if pin.type == "future", item.type == "futures", let f = item.futures { return f.id == pin.value }
        return false
    }

    private static func item(type: String, event: FeedEventData?, futures: FeedFuturesData?) -> FeedItem {
        FeedItem(type: type, score: 0, reason: nil, headline: nil, contextSummary: nil,
                 event: event, futures: futures, tournament: nil, concept: nil, bundle: nil,
                 personalized: nil, baseScore: nil, multiplier: nil, personalizationReasons: nil)
    }
}

/// Hydrates saved pins from their detail endpoints, at most three at once,
/// independent of followed teams, ranking, onboarding and team-feed state.
final class SavedPinContentViewModel: ObservableObject {
    typealias Lookup = @Sendable (SavedPin) async -> SavedPinContent
    @Published private(set) var content: [SavedPin: SavedPinContent] = [:]
    private let lookup: Lookup
    private var generation = UUID()

    init(lookup: @escaping Lookup = SavedPinContentViewModel.lookupPin) {
        self.lookup = lookup
    }

    /// `refresh` re-reads every pin (pull to refresh) while the previous card
    /// stays up; a failed re-read keeps the card it had rather than turning a
    /// shown game into an error row. Otherwise only unread pins (and failed ones
    /// when `retryFailed`) are fetched.
    @MainActor
    func load(_ pins: [SavedPin], refresh: Bool = false, retryFailed: Bool = false) async {
        let token = UUID()
        generation = token
        content = content.filter { pins.contains($0.key) }
        let needed = pins.filter { pin in
            guard let known = content[pin] else { return true }
            if refresh { return true }
            if case .failed = known { return retryFailed }
            return false
        }
        let lookup = lookup
        await withTaskGroup(of: (SavedPin, SavedPinContent).self) { group in
            var iterator = needed.makeIterator()
            for _ in 0..<min(3, needed.count) {
                if let pin = iterator.next() { group.addTask { (pin, await lookup(pin)) } }
            }
            while let (pin, result) = await group.next() {
                guard !Task.isCancelled, generation == token else {
                    group.cancelAll()
                    return
                }
                if case .failed = result, let known = content[pin], known.isAnswer {
                    // keep the last good card, or the confirmed gone answer
                    // that keeps a stale feed card from coming back
                } else {
                    content[pin] = result
                }
                if let next = iterator.next() { group.addTask { (next, await lookup(next)) } }
            }
        }
    }

    /// A different account's pins must not inherit this one's in-flight reads.
    @MainActor
    func reset() {
        generation = UUID()
        content = [:]
    }

    nonisolated static func lookupPin(_ pin: SavedPin) async -> SavedPinContent {
        do {
            if pin.type == "event" {
                return .event(FeedEventData(savedPinDetail: try await APIClient.shared.fetchEvent(id: pin.value)))
            }
            return .market(FeedFuturesData(savedPinDetail: try await APIClient.shared.fetchFuturesDetail(id: pin.value)))
        } catch APIError.httpError(let code, _) where code == 404 || code == 410 {
            return .unavailable
        } catch {
            return .failed
        }
    }
}

extension FeedEventData {
    /// #10011 — the game card for a pin outside the team feed, from the same
    /// event-detail payload the canonical page reads — including the settled
    /// forecast and period, so a saved final compares as it does in Sports
    /// (#11296). Card-only fields the
    /// detail route does not serve (imagery, confidence, `ended_at`) stay nil,
    /// which every card already reads as "not said".
    nonisolated init(savedPinDetail d: EventDetail) {
        self.init(
            id: d.id, externalId: d.externalId, sport: d.sport, sportName: nil,
            homeTeam: d.homeTeam, awayTeam: d.awayTeam, commenceTime: d.commenceTime,
            startIsTbd: d.startIsTbd, status: d.status, homeScore: d.homeScore, awayScore: d.awayScore,
            blendFoldRevision: d.blendFoldRevision, heroProbabilitySource: d.heroProbabilitySource,
            heroProbabilityObservedAt: d.heroProbabilityObservedAt, currentOdds: d.currentOdds,
            openingOdds: d.openingOdds, prematchOdds: d.prematchOdds,
            pregameProjection: d.pregameProjection, finalScorePeriod: d.finalScorePeriod,
            highlight: d.highlight,
            homeTeamData: d.homeTeamData, awayTeamData: d.awayTeamData, metadata: d.metadata,
            espn: d.espn, ei: d.ei, pulse: d.pulse, winProbabilitySources: d.winProbabilitySources,
            confidenceTier: nil, confidenceScore: nil,
            homeImageUrl: nil, awayImageUrl: nil, homeFlagUrl: nil, awayFlagUrl: nil,
            endedAt: nil, discoverMarqueeFinal: nil, venueClosedNoWinner: d.venueClosedNoWinner
        )
    }
}

extension FeedFuturesData {
    /// #10011 — the market card for a pin outside the team feed.
    ///
    /// #11616: every choice here is the market page's own, so the card a reader
    /// saved and the page it opens agree. The hero row leads (#8892's lead leg, the
    /// live rung of an open independent board, a supported winner — or nobody on a
    /// settled board with no supported winner, R1); then supported winners; then
    /// price. Each row
    /// carries the page's decision (`FuturesDetailRowValue`) and its full-field
    /// integer (`futuresDetailRenderedPercents`), so a selected top three is never
    /// re-rounded on its own. A winner is named — which makes
    /// `FeedLifecycle.futuresIsSettled` read the card as settled — only when the
    /// page heroes that row as Won. #698 and the raw-grade rule: `OutcomeVerdict`
    /// decides, so an open `is_winner = true` with no supported source, or a
    /// settled row whose result is unknown, is never crowned.
    nonisolated init(savedPinDetail d: FuturesMarketDetail) {
        let value = { (o: FuturesOutcome) in
            FuturesDetailRowValue.of(o, marketStatus: d.status, marketSource: d.source)
        }
        let won = { (o: FuturesOutcome) in value(o) == .verdict(.won) }
        let hero = futuresDetailHeroOutcome(d)
        let winner = hero.flatMap { won($0) ? $0 : nil }
        let percents = futuresDetailRenderedPercents(d.outcomes)
        let ordered = d.outcomes.enumerated().sorted { lhs, rhs in
            let (a, b) = (lhs.element, rhs.element)
            let aLeads = a.id == hero?.id, bLeads = b.id == hero?.id
            if aLeads != bLeads { return aLeads }
            if won(a) != won(b) { return won(a) }
            let (pa, pb) = (a.probability ?? -1, b.probability ?? -1)
            if pa != pb { return pa > pb }
            return lhs.offset < rhs.offset
        }.map(\.element)
        let leaders = ordered.prefix(3).enumerated().map { index, o in
            FeedFuturesOutcome(id: o.id, name: o.name, probability: o.probability,
                               rank: index + 1, movement: o.probabilityChange24h,
                               detailValue: value(o), detailRenderedPercent: percents[o.id])
        }
        self.init(
            id: d.id, externalId: d.externalId, name: d.name, sport: d.sport, sportName: d.sportName,
            llmSportCategory: d.llmSportCategory, source: d.source, sourceCount: nil, sources: nil,
            marketTier: nil, status: d.status, resolutionDate: d.resolutionDate,
            topOutcomes: leaders, outcomeCount: d.outcomeCount ?? d.outcomes.count,
            canonicalMarketKey: nil, groupId: nil, groupType: nil, imageUrl: d.imageUrl,
            hookDescription: d.hookDescription, matchedOutcomes: nil, discoverCard: nil,
            confidenceTier: nil, confidenceScore: nil, resolved: nil, winner: winner?.name,
            winnerOpeningProbability: winner.flatMap(FuturesReadableOpening8313.of), storyKey: nil,
            priceObservedAt: nil, cardSumReason: nil
        )
    }
}
