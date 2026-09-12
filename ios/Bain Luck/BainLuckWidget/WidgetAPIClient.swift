import Foundation

// MARK: - Minimal API client for the widget extension
// Widgets cannot share code with the main app target directly,
// so this is a standalone lightweight client.

actor WidgetAPIClient {
    static let shared = WidgetAPIClient()

    private let baseURL = "https://api.bainluck.com"
    private let session: URLSession
    private let decoder: JSONDecoder

    private init() {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 15
        config.timeoutIntervalForResource = 30
        session = URLSession(configuration: config)

        decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
    }

    // MARK: - Fetch live games from the feed

    func fetchLiveGames(limit: Int = 10) async throws -> [WidgetGame] {
        guard let url = URL(string: "\(baseURL)/api/feed?limit=\(limit)&include_futures=false") else {
            throw WidgetAPIError.invalidURL
        }

        let (data, response) = try await session.data(from: url)
        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
            throw WidgetAPIError.httpError
        }

        let feed = try decoder.decode(WidgetFeedResponse.self, from: data)

        return feed.items.compactMap { item -> WidgetGame? in
            guard let event = item.data,
                  event.status == "live",
                  let homeProbability = event.currentOdds?.homeProbability,
                  // #2279 — `Int(_:)` below TRAPS on a non-finite Double, and a
                  // trap in a widget timeline is a blank widget with no log.
                  // JSONDecoder refuses NaN literals by default, so this is a
                  // belt on a closed door; it costs one clause.
                  homeProbability.isFinite else {
                return nil
            }

            let awayProbability = 1.0 - homeProbability
            // #5363 — and this target derives the away side ITSELF, one line up,
            // which on soccer makes it *away win or draw* under the away crest
            // on someone's home screen. `DrawPricedWinner.swift` and
            // `SportVocab.swift` are members of this target for the same reason
            // `PeriodLabel.swift` is: the widget shares the phone's rule rather
            // than carrying a transcription of it (ruling 021).
            let awayIsWithheld = DrawPricedWinner.sportPricesADraw(event.sport)
            // #5709 — AND THE TEAM LABEL WAS A TRANSCRIPTION TOO, four lines
            // under the sentence above. This read
            //
            //     event.homeTeamData?.abbreviation
            //         ?? String(event.homeTeam.split(separator: " ").last ?? "")
            //
            // which labels a club with the kind of club it is whenever the
            // server sends no abbreviation: `Girona FC` → **FC**, `Cádiz CF` →
            // **CF**, `Real Sociedad B` → **B**. Measured on this target's own
            // endpoint (`/api/feed?limit=100`, 2026-09-12): of 186 team slots,
            // 103 carry no served abbreviation and so take the fallback, and 8
            // of those render one or two glyphs onto someone's home screen.
            //
            // It is the same line #4285 fixed on the web chart axis and #5651
            // fixed on the phone — one rule, written independently a fourth
            // time. `TeamShortName` imports nothing but Foundation, so joining
            // this target costs it no dependencies.
            //
            // `abbreviationPair` rather than `abbreviation`, for two reasons: a
            // served abbreviation still wins wherever it exists, exactly as
            // before; and this widget draws BOTH sides of one game, which is the
            // case #3430 is about — two clubs sharing a distinctive tail were
            // each rendering the same label here, and the pair rule grows them
            // apart. A single-name call would have fixed the visible half of
            // this bug and left that one.
            let abbrevs = TeamShortName.abbreviationPair(
                away: event.awayTeam,
                home: event.homeTeam,
                awayServed: event.awayTeamData?.abbreviation,
                homeServed: event.homeTeamData?.abbreviation
            )
            let homeAbbrev = abbrevs.home
            let awayAbbrev = abbrevs.away

            // UX-P114: prefer the server's card-level percents. This widget draws
            // both sides of one question, and `awayProbability` above is
            // `1 - home`, so rounding the two independently printed 101 whenever
            // the blend landed on a half-percent. The band lives on the server
            // precisely so this standalone target does not carry a fourth copy
            // of it.
            //
            // 🔴 #2279 — AND YET THE ONLY THING THAT REACHED THIS TARGET WAS THE
            // PREFERENCE. The fallback stayed the original independent rounding,
            // so the widget printed 101 on exactly the 8.2% of events UX-P114
            // measured whenever the served fields were absent — which is the case
            // the struct comment says they are optional FOR (a cached response, a
            // rollback). It also coalesced PER SIDE, so a payload with one field
            // and not the other printed a served value beside a derived one.
            //
            // BOTH SERVED OR NEITHER, and the fallback now applies the rule
            // instead of the defect. `away = 1 - home` by construction here, so
            // `renderedDuelPercents`' [0.99, 1.01] band test and its
            // divide-by-total are both IDENTITIES on this input; what is left of
            // the shared rule is its entire content for this case — round the
            // FAVOURITE once, derive the underdog as `100 - favourite`. That is
            // transcribed rather than imported because a widget extension is a
            // standalone target, and the transcription is pinned to the shared
            // implementation row-for-row by
            // `frontend/__tests__/ios/duelPercentServedPair.test.ts` so it cannot
            // drift the way an unpinned copy would.
            let leaderIsHome = homeProbability >= awayProbability
            let leaderPct = Int(
                ((leaderIsHome ? homeProbability : awayProbability) * 1000 / 10).rounded()
            )
            let derivedHomePct = leaderIsHome ? leaderPct : 100 - leaderPct
            let derivedAwayPct = leaderIsHome ? 100 - leaderPct : leaderPct
            let servedHomePct = event.currentOdds?.homeRenderedPercent
            let servedAwayPct = event.currentOdds?.awayRenderedPercent
            let bothServed = servedHomePct != nil && servedAwayPct != nil

            return WidgetGame(
                id: event.id,
                homeTeam: event.homeTeam,
                awayTeam: event.awayTeam,
                homeAbbrev: homeAbbrev,
                awayAbbrev: awayAbbrev,
                homeScore: event.homeScore,
                awayScore: event.awayScore,
                homeProb: bothServed ? servedHomePct! : derivedHomePct,
                awayProb: awayIsWithheld ? nil : (bothServed ? servedAwayPct! : derivedAwayPct),
                // #4880 — see `PeriodLabel.liveStatusText`. `PeriodLabel.swift` is
                // a member of this target so the widget shares the phone's rule.
                period: PeriodLabel.liveStatusText(
                    period: event.espn?.period, gameClock: event.espn?.gameClock) ?? "",
                sport: event.sportName ?? event.sport ?? "",
                homeColor: event.homeTeamData?.primaryColor,
                awayColor: event.awayTeamData?.primaryColor
            )
        }
    }

    // MARK: - Fetch top Discover items (futures markets)

    func fetchDiscoverItems(limit: Int = 10) async throws -> [WidgetDiscoverItem] {
        guard let url = URL(string: "\(baseURL)/api/feed?limit=\(limit)&include_events=false") else {
            throw WidgetAPIError.invalidURL
        }

        let (data, response) = try await session.data(from: url)
        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
            throw WidgetAPIError.httpError
        }

        let feed = try decoder.decode(WidgetDiscoverFeedResponse.self, from: data)

        return feed.items.compactMap { item -> WidgetDiscoverItem? in
            guard let futures = item.data,
                  // L2-225: never put a settled market on the home screen. A widget
                  // timeline is cached for hours, so a resolved/past-resolution card
                  // admitted here outlives every other surface's view of it.
                  !WidgetLifecycle.isSettled(futures),
                  let leader = futures.topOutcomes?.first,
                  let probability = leader.probability else {
                return nil
            }

            return WidgetDiscoverItem(
                id: futures.id,
                name: futures.name,
                category: futures.llmSportCategory ?? futures.sport ?? "Prediction",
                leader: leader.name,
                probability: Int((probability * 100).rounded()),
                movement: leader.movement.map { Int(($0 * 100).rounded()) },
                hookDescription: futures.hookDescription,
                headline: item.headline
            )
        }
    }
}

// MARK: - Error

enum WidgetAPIError: LocalizedError {
    case httpError
    case invalidURL

    var errorDescription: String? {
        switch self {
        case .httpError: return "Request failed"
        case .invalidURL: return "Invalid URL"
        }
    }
}

// The feed decode adapter (WidgetFeedResponse / WidgetDiscoverFeedResponse /
// WidgetFeedItem + payloads + the tolerant per-item decoder) lives in
// WidgetFeedDecoding.swift so it can be compiled into the test bundle and
// exercised directly (L2-182).
