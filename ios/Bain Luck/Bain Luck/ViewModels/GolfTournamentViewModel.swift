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
            state = .loaded(GolfTournamentPresentation(response: response))
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

    /// The field, ranked, favourite first.
    let field: [GolfTournamentFieldRow]

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
                    movement24h: golfer.movement24h
                )
            }
    }
}

nonisolated struct GolfTournamentFieldRow: Equatable, Identifiable, Sendable {
    let name: String
    let probability: Double
    let position: Int
    let movement24h: Double?

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
