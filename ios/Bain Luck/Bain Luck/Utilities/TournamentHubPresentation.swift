import Foundation

// MARK: - Tournament hub presentation (pure, testable)
//
// Every decision the hub screen makes about WHAT to show lives here as a value,
// so the contract can be asserted without rendering SwiftUI — the same seam
// `TournamentCardPresentation` opened for the Discover card.
//
// The rule this file exists to keep is D27: **a feed that returned nothing is
// labelled, not omitted.** A section that quietly disappears when its list is
// empty is indistinguishable, on the phone, from a section the app forgot to
// build — and today the US Open hub really does return an empty `bracket`, so
// that case is live, not hypothetical. Each section therefore resolves to
// either rows or a sentence, never to silence.

nonisolated struct TournamentHubPresentation: Equatable, Sendable {

    // MARK: Row values

    nonisolated struct SideRow: Equatable, Sendable, Identifiable {
        let id: String
        let name: String
        let flagUrl: String?
        /// Already formatted — "62%", "<1%", or the em-dash for no price.
        let percentText: String
        let hasPrice: Bool
        let isFavourite: Bool
    }

    nonisolated struct MatchRow: Equatable, Sendable, Identifiable {
        let id: String
        /// Non-nil only when this match resolves to an event page we can open.
        let eventId: Int?
        /// "Men's Singles · R64"
        let headline: String
        /// "4th Set" while live; "11:15 AM" or "Time TBD" before.
        let statusText: String
        let isLive: Bool
        let sides: [SideRow]
        /// Set when the match has no price at all, so the row says why the
        /// numbers are dashes instead of leaving the reader to guess.
        let noPriceNote: String?
    }

    nonisolated struct ResultRow: Equatable, Sendable, Identifiable {
        let id: String
        let eventId: Int?
        /// "Women's Singles · Round 2"
        let headline: String
        let winnerName: String
        let loserName: String
        /// "6-1, 6-4", or nil for a walkover with no scoreline.
        let score: String?
        /// "Retired" / "Walkover". Nil for an ordinary final — a retirement is
        /// not a scoreline and must not be printed as one.
        let completionNote: String?
    }

    nonisolated struct BoardRow: Equatable, Sendable, Identifiable {
        let id: String
        let rank: Int?
        let name: String
        let flagUrl: String?
        let percentText: String
        /// Movement in percentage POINTS over the tracked window, or nil when it
        /// is below a point and would round to a misleading "+0".
        let deltaPoints: Double?
    }

    nonisolated struct BoardSection: Equatable, Sendable, Identifiable {
        let id: String
        let title: String
        let rows: [BoardRow]
        /// "Top 6 of 36 still in the draw" — shown only when rows were trimmed.
        let trimNote: String?
    }

    // MARK: Header

    let title: String
    let subtitle: String?

    // MARK: Sections — rows OR a sentence, never nothing

    let liveMatches: [MatchRow]
    let liveEmptyNote: String?

    let upcomingMatches: [MatchRow]
    let upcomingEmptyNote: String?

    let results: [ResultRow]
    let resultsEmptyNote: String?

    let boards: [BoardSection]
    let boardsEmptyNote: String?

    /// Always present. The bracket is either absent from the feed or present and
    /// undrawn by this screen, and the reader is told which.
    let bracketNote: String

    /// "Match prices last updated 4 hours ago." Nil when the feed reported no
    /// observation age — which is itself different from "fresh", so nothing is
    /// claimed in that case.
    let priceAgeNote: String?

    /// Shown instead of the sections when the whole payload came back empty.
    let wholePayloadEmptyNote: String?

    // MARK: Bounds
    //
    // The response carries 40 slate matches, 256 results and 80 board rows. A
    // phone screen that renders all of them is a scroll nobody finishes, and it
    // is also the shape that made a tall `ImageRenderer` return nil PNG data.
    // These are the display bounds, stated once.

    static let upcomingLimit = 8
    static let resultsLimit = 10
    static let boardRowLimit = 6

    // MARK: - Build

    init(response: TournamentHubResponse) {
        title = response.title ?? "Tournament"
        subtitle = response.subtitle

        let byEspn = response.eventLinks?.byEspn ?? [:]
        let allMatches = response.slate?.matches ?? []

        func eventId(for match: TournamentHubMatch) -> Int? {
            if let direct = match.eventId { return direct }
            guard let espn = match.espnCompetitionId else { return nil }
            return byEspn[espn]
        }

        let live = allMatches
            .filter { $0.isLive }
            .sorted { ($0.scheduledDate ?? "") < ($1.scheduledDate ?? "") }
            .map { Self.matchRow($0, eventId: eventId(for: $0)) }

        let upcoming = allMatches
            .filter { !$0.isLive }
            .sorted { ($0.scheduledDate ?? "") < ($1.scheduledDate ?? "") }
            .prefix(Self.upcomingLimit)
            .map { Self.matchRow($0, eventId: eventId(for: $0)) }

        liveMatches = live
        liveEmptyNote = live.isEmpty ? "No match is being played right now." : nil

        upcomingMatches = Array(upcoming)
        upcomingEmptyNote = upcoming.isEmpty
            ? "Nothing else is scheduled in the order of play." : nil

        // Newest first. The feed serves results oldest-first, and a hub whose
        // "Latest results" opens on a qualifying match from nine days ago is
        // worse than useless — it reads as a dead page.
        let finished = (response.results?.matches ?? [])
            .sorted { ($0.completedAt ?? "") > ($1.completedAt ?? "") }
            .prefix(Self.resultsLimit)
            .compactMap { Self.resultRow($0, eventId: $0.espnCompetitionId.flatMap { byEspn[$0] }) }

        results = Array(finished)
        resultsEmptyNote = finished.isEmpty ? "No completed matches yet." : nil

        let boardSections = response.boards.compactMap { Self.boardSection($0) }
        boards = boardSections
        boardsEmptyNote = boardSections.isEmpty
            ? "Nobody is priced to win the title yet." : nil

        let bracketEntries = response.bracket.values.reduce(0) { $0 + $1.count }
        bracketNote = bracketEntries == 0
            ? "No bracket yet — the tournament feed returned an empty draw."
            : "The feed has a bracket; this screen doesn't draw it yet."

        priceAgeNote = Self.priceAgeNote(hours: response.slate?.ageHours)

        let nothingAtAll = live.isEmpty && upcoming.isEmpty
            && finished.isEmpty && boardSections.isEmpty
        wholePayloadEmptyNote = nothingAtAll
            ? "The tournament feed returned nothing for this event." : nil
    }

    // MARK: - Row builders

    private static func matchRow(_ match: TournamentHubMatch, eventId: Int?) -> MatchRow {
        let priced = match.sides.contains { $0.probability != nil }
        let best = match.sides.compactMap(\.probability).max()

        // UX-P114 / #2279: a row printing two sides of ONE question decides both
        // percents together. Formatting each side on its own is the 101% those
        // fixed — the US Open served `0.845 / 0.155` on 2026-09-04, a complement
        // pair landing on `.5` for both sides at once, and this screen printed
        // 85% beside 16%. A draw with anything other than two sides is not a duel
        // and keeps rendering exactly as before.
        let duelPercents: [Int?] = match.sides.count == 2
            ? renderedDuelPercents(
                away: match.sides[0].probability,
                home: match.sides[1].probability
            )
            : []

        let sides = match.sides.enumerated().map { index, side in
            SideRow(
                id: side.id,
                name: side.displayName,
                flagUrl: side.image?.flagUrl,
                percentText: formatProbabilityOrDash(
                    side.probability,
                    renderedPercent: index < duelPercents.count ? duelPercents[index] : nil
                ),
                hasPrice: side.probability != nil,
                // A two-way match with both sides at the same price has no
                // favourite; marking both would be a claim the numbers do not
                // make.
                isFavourite: priced
                    && side.probability != nil
                    && side.probability == best
                    && match.sides.filter { $0.probability == best }.count == 1
            )
        }

        return MatchRow(
            id: match.id,
            eventId: eventId,
            headline: [match.drawLabel, match.round]
                .compactMap { $0 }
                .filter { !$0.isEmpty }
                .joined(separator: " · "),
            statusText: statusText(for: match),
            isLive: match.isLive,
            sides: sides,
            noPriceNote: priced ? nil : "No price on this match yet."
        )
    }

    private static func statusText(for match: TournamentHubMatch) -> String {
        if match.isLive {
            if let detail = match.statusDetail, !detail.isEmpty { return detail }
            return "Live"
        }
        if match.startIsTbd == true { return "Time TBD" }
        guard let iso = match.scheduledDate, let date = isoDate(iso) else { return "Time TBD" }
        return startTimeFormatter.string(from: date)
    }

    private static func resultRow(_ result: TournamentHubResult, eventId: Int?) -> ResultRow? {
        guard result.players.count == 2 else { return nil }
        let winner = result.players.first { $0.isWinner == true }
            ?? result.players.first { $0.entityKey == result.winnerEntityKey }
        guard let winner else { return nil }
        guard let loser = result.players.first(where: { $0.entityKey != winner.entityKey }) else {
            return nil
        }

        let completion = (result.completion ?? "final").lowercased()
        let note: String?
        switch completion {
        case "retired": note = "Retired"
        case "walkover": note = "Walkover"
        case "final": note = nil
        default: note = completion.capitalized
        }

        let score = (result.score?.isEmpty == false) ? result.score : nil

        return ResultRow(
            id: result.id,
            eventId: eventId,
            headline: [result.drawLabel, result.round]
                .compactMap { $0 }
                .filter { !$0.isEmpty }
                .joined(separator: " · "),
            winnerName: winner.displayName,
            loserName: loser.displayName,
            score: score,
            completionNote: note
        )
    }

    private static func boardSection(_ board: TournamentHubBoard) -> BoardSection? {
        // Someone knocked out is not a contender; the board keeps them so the
        // web page can grey them, but a six-row phone list must spend its rows
        // on players still in the draw.
        let standing = board.rows.filter { ($0.state ?? "live") == "live" }
        guard !standing.isEmpty else { return nil }

        let ordered = standing.sorted { lhs, rhs in
            switch (lhs.rank, rhs.rank) {
            case let (l?, r?): return l < r
            case (nil, _?): return false
            case (_?, nil): return true
            default: return (lhs.probability ?? 0) > (rhs.probability ?? 0)
            }
        }
        let shown = ordered.prefix(boardRowLimit)

        return BoardSection(
            id: board.id,
            title: board.label ?? board.draw,
            rows: shown.map { row in
                BoardRow(
                    id: row.id,
                    rank: row.rank,
                    name: row.displayName,
                    flagUrl: row.image?.flagUrl,
                    percentText: formatProbabilityOrDash(row.probability),
                    deltaPoints: movementPoints(row.trendDelta)
                )
            },
            trimNote: ordered.count > shown.count
                ? "Top \(shown.count) of \(ordered.count) still in the draw"
                : nil
        )
    }

    /// Percentage points, suppressed below one point.
    ///
    /// "+0" reads as a measured non-move rather than as noise, so a sub-point
    /// change is dropped instead of rounded. The Discover feed's cards apply the
    /// same rule to their own payload; the two are deliberately not sharing one
    /// helper, because gotcha #129 cuts both ways — a rule two endpoints happen
    /// to agree on today is a coincidence, not a contract, and coupling them
    /// means a change to one silently rewrites the other.
    private static func movementPoints(_ fraction: Double?) -> Double? {
        guard let fraction else { return nil }
        let points = fraction * 100
        return abs(points) >= 1 ? points : nil
    }

    /// The feed's own observation age, rendered as a sentence.
    ///
    /// Deliberately reads the server's `age_hours` rather than differencing a
    /// timestamp against the device clock: the number is then the same one the
    /// server measured, and the test that pins this copy does not branch on
    /// what time it runs (gotcha #44).
    static func priceAgeNote(hours: Double?) -> String? {
        guard let hours, hours >= 0 else { return nil }
        if hours < 1 / 60.0 { return "Match prices updated just now." }
        if hours < 1 {
            let minutes = max(Int((hours * 60).rounded()), 1)
            return "Match prices last updated \(minutes) minute\(minutes == 1 ? "" : "s") ago."
        }
        let whole = Int(hours.rounded())
        return "Match prices last updated \(whole) hour\(whole == 1 ? "" : "s") ago."
    }
}

// MARK: - Date helpers

private let isoWithFraction: ISO8601DateFormatter = {
    let f = ISO8601DateFormatter()
    f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return f
}()

private let isoPlain: ISO8601DateFormatter = {
    let f = ISO8601DateFormatter()
    f.formatOptions = [.withInternetDateTime]
    return f
}()

/// The hub serves both `2026-09-03T18:25:00+00:00` and
/// `2026-09-03T19:50:02.857675+00:00`; one formatter parses one of them.
private func isoDate(_ value: String) -> Date? {
    isoWithFraction.date(from: value) ?? isoPlain.date(from: value)
}

private let startTimeFormatter: DateFormatter = {
    let f = DateFormatter()
    f.dateStyle = .none
    f.timeStyle = .short
    return f
}()
