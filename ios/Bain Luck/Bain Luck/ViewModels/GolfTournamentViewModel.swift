import Combine
import Foundation
import os

private let logger = Logger(subsystem: "com.bainluck", category: "golfTournament")

/// Loads one golf tournament and its field (#1471).
///
/// Shaped after `TournamentHubViewModel` on purpose — same three states, same
/// keep-the-last-good-screen refresh rule — because a reader should not be able
/// to tell which kind of tournament they opened by how the screen behaves.
final class GolfTournamentViewModel: ObservableObject {
    enum State: Equatable {
        case loading
        case loaded(GolfTournamentPresentation)
        case error(String)
    }

    @Published private(set) var state: State = .loading
    @Published private(set) var atlasData: EventAtlasGolfTournament11666.TournamentAtlasData = .init()

    let slug: String

    init(slug: String) {
        self.slug = slug
    }

    @MainActor
    func load() async {
        // A refresh keeps the last good screen up while it runs. Dropping back
        // to a skeleton on every pull-to-refresh is how a live page flickers.
        if case .loaded = state {} else { state = .loading }

        do {
            let response = try await APIClient.shared.fetchGolfTournament(slug: slug)
            let presentation = GolfTournamentPresentation(response: response)
            state = .loaded(presentation)
            if ReleaseSurfaces.isEventPageAtlasEnabled() {
                atlasData = await Self.loadAtlasData(for: response)
            }
            logger.info("Golf tournament \(self.slug, privacy: .public) loaded")
        } catch {
            if case .loaded = state {
                // Keep showing what we had; a failed refresh is not an empty
                // tournament.
                logger.error("Golf tournament \(self.slug, privacy: .public) refresh failed: \(error)")
            } else {
                state = .error(error.localizedDescription)
                logger.error("Golf tournament \(self.slug, privacy: .public) error: \(error)")
            }
        }
    }

    nonisolated static func loadAtlasData(
        for response: GolfTournamentDetailResponse,
        fetchMarket: @Sendable @escaping (Int) async throws -> FuturesMarketDetail = { id in
            try await APIClient.shared.fetchFuturesDetail(id: id)
        },
        fetchTimeline: @Sendable @escaping (Int) async throws -> ProbabilityTimelineResponse = { id in
            try await APIClient.shared.fetchProbabilityTimeline(
                marketId: id,
                top: 20,
                hours: 168,
                fullRange: true
            )
        }
    ) async -> EventAtlasGolfTournament11666.TournamentAtlasData {
        var out = EventAtlasGolfTournament11666.TournamentAtlasData()
        let winnerId = response.evolutionMarketId
            ?? response.markets.first(where: { $0.type == "winner" })?.marketIds.first
        let top5Id = response.markets.first(where: { $0.type == "top_5" })?.marketIds.first
        let top10Id = response.markets.first(where: { $0.type == "top_10" })?.marketIds.first
        let top20Id = response.markets.first(where: { $0.type == "top_20" })?.marketIds.first
        let makeCutId = response.markets.first(where: { $0.type == "make_cut" })?.marketIds.first
        out.hasMakeCutMarket = (makeCutId != nil)

        async let winnerOutcome: (FuturesMarketDetail?, Bool) = {
            guard let id = winnerId else { return (nil, false) }
            do {
                return (try await fetchMarket(id), false)
            } catch {
                logger.error("Golf tournament winner market \(id, privacy: .public) fetch failed: \(error)")
                return (nil, true)
            }
        }()
        async let timelineOutcome: (ProbabilityTimelineResponse?, Bool) = {
            guard let id = winnerId else { return (nil, false) }
            do {
                return (try await fetchTimeline(id), false)
            } catch {
                logger.error("Golf tournament timeline \(id, privacy: .public) fetch failed: \(error)")
                return (nil, true)
            }
        }()
        async let top5Outcome: (FuturesMarketDetail?, Bool) = {
            guard let id = top5Id else { return (nil, false) }
            do {
                return (try await fetchMarket(id), false)
            } catch {
                logger.error("Golf tournament top5 market \(id, privacy: .public) fetch failed: \(error)")
                return (nil, true)
            }
        }()
        async let top10Outcome: (FuturesMarketDetail?, Bool) = {
            guard let id = top10Id else { return (nil, false) }
            do {
                return (try await fetchMarket(id), false)
            } catch {
                logger.error("Golf tournament top10 market \(id, privacy: .public) fetch failed: \(error)")
                return (nil, true)
            }
        }()
        async let top20Outcome: (FuturesMarketDetail?, Bool) = {
            guard let id = top20Id else { return (nil, false) }
            do {
                return (try await fetchMarket(id), false)
            } catch {
                logger.error("Golf tournament top20 market \(id, privacy: .public) fetch failed: \(error)")
                return (nil, true)
            }
        }()
        async let makeCutOutcome: (FuturesMarketDetail?, Bool) = {
            guard let id = makeCutId else { return (nil, false) }
            do {
                return (try await fetchMarket(id), false)
            } catch {
                logger.error("Golf tournament makeCut market \(id, privacy: .public) fetch failed: \(error)")
                return (nil, true)
            }
        }()

        let (winMkt, winFailed) = await winnerOutcome
        let (tlResp, tlFailed) = await timelineOutcome
        let (t5Mkt, t5Failed) = await top5Outcome
        let (t10Mkt, t10Failed) = await top10Outcome
        let (t20Mkt, t20Failed) = await top20Outcome
        let (mcMkt, mcFailed) = await makeCutOutcome

        out.winnerMarket = winMkt
        out.winnerTimeline = tlResp
        out.winnerTimelineFailed = tlFailed
        out.top5Market = t5Mkt
        out.top10Market = t10Mkt
        out.top20Market = t20Mkt
        out.makeCutMarket = mcMkt

        if winFailed { out.failedMarketSlots.insert("win") }
        if t5Failed { out.failedMarketSlots.insert("top5") }
        if t10Failed { out.failedMarketSlots.insert("top10") }
        if t20Failed { out.failedMarketSlots.insert("top20") }
        if mcFailed { out.failedMarketSlots.insert("makeCut") }

        return out
    }
}

/// What the screen draws, reduced from the response.
///
/// The reduction lives here rather than in the view so the rules below are
/// unit-testable without a network or a rendered surface — the field ordering
/// and the "is this worth showing" tests are the whole content of the screen.
nonisolated struct GolfTournamentPresentation: Equatable, Sendable {
    let name: String
    let venue: String?
    let location: String?
    let dateRange: String?
    let isMajor: Bool
    let tourLabel: String?
    var scheduleStatus: String? = nil
    var commenceTime: String? = nil
    var evolutionMarketId: Int? = nil
    var markets: [GolfTournamentMarketGroup] = []
    var roundTopGroups: [GolfRoundTopGroup] = []

    /// The field, ranked, favourite first.
    let field: [GolfTournamentFieldRow]
    let overflowOutcomes: [GolfGolferData]

    /// How many of `field` to draw before the reader asks for the rest.
    static let initiallyShown = 12

    init(response: GolfTournamentDetailResponse) {
        let t = response.tournament
        name = properTitleCase(t.name)
        venue = t.venue
        location = t.location
        dateRange = formatDateRange(start: t.startDate, end: t.endDate)
        isMajor = t.isMajor == true
        tourLabel = t.tourLabel
        scheduleStatus = t.scheduleStatus
        commenceTime = t.commenceTime ?? t.startDate
        evolutionMarketId = response.evolutionMarketId
        markets = response.markets
        roundTopGroups = response.roundTopGroups
        overflowOutcomes = response.overflowOutcomes

        // ORDERED HERE, NOT TRUSTED FROM THE WIRE. The server sends rank 1..n
        // today, but a field sorted by anything else would print a 6.1%
        // favourite below a 2.7% golfer with no error anywhere — the kind of
        // wrong that reads as a data outage. Sorting on the number we PRINT
        // makes the order and the page agree by construction.
        //
        // `rank` breaks ties so two golfers on the same probability keep a
        // stable order between renders rather than swapping under the thumb.
        field = response.golfers
            .sorted {
                if $0.probability != $1.probability { return $0.probability > $1.probability }
                return ($0.rank ?? Int.max) < ($1.rank ?? Int.max)
            }
            .enumerated()
            .map { index, golfer in
                GolfTournamentFieldRow(
                    name: golfer.name,
                    probability: golfer.probability,
                    // The printed position is our own ordering's, not the
                    // server's `rank`: showing a "3" beside the second row is
                    // the disagreement this whole sort exists to prevent.
                    position: index + 1,
                    movement24h: golfer.movement24h,
                    renderedPercent: golfer.renderedPercent,
                    openingProbability: golfer.openingProbability,
                    isWinner: (golfer.isWinner == true) || (golfer.won == true) ? true : golfer.isWinner
                )
            }
    }
}

nonisolated struct GolfTournamentFieldRow: Equatable, Identifiable, Sendable {
    let name: String
    let probability: Double
    let position: Int
    let movement24h: Double?
    var renderedPercent: Int? = nil
    var openingProbability: Double? = nil
    var isWinner: Bool? = nil

    var probabilityLabel: String {
        renderedPercent.map { formatProbability(probability, renderedPercent: $0) } ?? String(format: "%.1f%%", probability * 100)
    }

    var id: String { name }

    /// Whether the 24h move is worth drawing an arrow for.
    ///
    /// Half a point, matching `TournamentHeroCard` — one threshold for one
    /// quantity, so the card and the page it opens never disagree about whether
    /// a golfer moved.
    var hasMeaningfulMovement: Bool {
        guard let movement = movement24h else { return false }
        return abs(movement) >= 0.005
    }
}
