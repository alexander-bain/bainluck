import Foundation

/// The "who leads the game" markets on a Player Props card: Kalshi's
/// `<matchup>: Most Receiving Yards` / `Most Rushing Yards`, one leg per player.
///
/// #5176 — THE PHONE DROPPED EVERY ONE OF THEM. The card builds its player
/// ladders from outcomes shaped `Player: N+`, so its grouping skips any outcome
/// without a colon — and a field's outcome is a bare name (`Davante Adams`), with
/// no threshold. Measured 2026-09-28 01:20Z on the two NFL pages this was built
/// against: LAR@DEN 14780548 (live) and SEA–WAS 14781702 (final) each serve two
/// such fields of 3–7 players, and the web already prints them under The
/// Divergence ("MOST RECEIVING YARDS · Davante Adams 20% → 89%").
///
/// **A field is not a ladder, so it is not folded into the player cards.** A
/// rung is "at least N" on one player's stat; a field leg is "this player, and
/// nobody else, finishes top", so its legs compete and it is about both teams at
/// once. It gets its own block, which the team filter does not narrow — the
/// served rows carry no `player_team` to narrow it by, and "most in the game"
/// is a question about the whole game.
///
/// **Each leg prints its own price, unnormalised**, as the web does and as every
/// independent-binary leaderboard in the app does (gotcha #23 is honoured by the
/// clamp every percentage already goes through, not by rescaling a venue's
/// number into one it never quoted).
///
/// Admission is deliberately narrow, because the rows the colon guard drops are
/// not all fields. On the same two pages it also drops Polymarket's
/// `<Player>: <Stat> O/U <line>` legs (outcome `Over`/`Under`; all 26 restate a
/// Kalshi ladder already on the card), `Both Teams to Score Points` (`Yes`/`No`),
/// and Kalshi's `Receiving Yards Ladder` / `Escalator` (bare names, no threshold,
/// and no stated meaning to print). None of those may arrive here.
enum PlayerPropsField {

    /// Rows a field shows before its "+N more".
    static let visibleCount = 3

    struct Candidate: Equatable {
        let name: String
        let probability: Double
        let pregameMark: Double?
        /// The server's grade on a finished game: `true` for the leader.
        let hit: Bool?
    }

    struct Field: Identifiable, Equatable {
        /// The served `market_name`, whole — two matchups' fields never merge.
        let id: String
        /// The stat phrase after the matchup: `Most Receiving Yards`.
        let title: String
        let candidates: [Candidate]

        /// Has the server graded any leg? Decides the caption's tense and
        /// whether an unpriced field still has something true to show.
        var isGraded: Bool { candidates.contains { $0.hit != nil } }
    }

    /// The stat phrase of a field market, or nil if this market is not one.
    ///
    /// `Los Angeles Rams vs Denver: Most Receiving Yards` → `Most Receiving Yards`.
    /// Requires the matchup prefix and a word after `Most`, so a bare `Most` or a
    /// market with no colon is not a field.
    static func fieldTitle(marketName: String) -> String? {
        guard let colon = marketName.firstIndex(of: ":") else { return nil }
        let phrase = marketName[marketName.index(after: colon)...]
            .trimmingCharacters(in: .whitespaces)
        guard phrase.lowercased().hasPrefix("most "),
              phrase.count > "most ".count
        else { return nil }
        return phrase
    }

    /// Is this served row one leg of a field?
    static func isFieldLeg(_ prop: GameMarketPlayerProp) -> Bool {
        guard prop.threshold == nil, fieldTitle(marketName: prop.marketName) != nil else {
            return false
        }
        let outcome = prop.outcomeName.trimmingCharacters(in: .whitespaces)
        guard !outcome.isEmpty, !outcome.contains(":") else { return false }
        return !answerWords.contains(outcome.lowercased())
    }

    /// Outcomes that answer a question rather than name a player.
    private static let answerWords: Set<String> = ["yes", "no", "over", "under"]

    /// Every drawable field on the card, in a stable order.
    ///
    /// A leg with no price is dropped (there is no number to print). A field is
    /// drawn when it is graded, or when its legs are a price: two or more legs
    /// all printing the same percentage are the no-book placeholder #5137
    /// describes, not a market's view (#5176's own specimen read 37% · 37% · 37%).
    static func fields(from props: [GameMarketPlayerProp]) -> [Field] {
        var byMarket: [String: (title: String, legs: [Candidate], seen: Set<String>)] = [:]
        for prop in props where isFieldLeg(prop) {
            guard let title = fieldTitle(marketName: prop.marketName),
                  let probability = prop.overProbability, probability.isFinite
            else { continue }
            let name = PropSubject.display(prop.outcomeName.trimmingCharacters(in: .whitespaces))
            var entry = byMarket[prop.marketName] ?? (title, [], [])
            // One leg per person: a second row naming the same player is a
            // duplicate, never a second chance.
            guard entry.seen.insert(name).inserted else { continue }
            entry.legs.append(Candidate(
                name: name,
                probability: min(max(probability, 0), 1),
                pregameMark: prop.pregameMark,
                hit: prop.hit
            ))
            byMarket[prop.marketName] = entry
        }

        return byMarket.map { market, entry in
            Field(id: market, title: entry.title, candidates: ordered(entry.legs))
        }
        .filter { field in
            field.isGraded
                || PlayerPropsPricing.isPricedLadder(field.candidates.map(\.probability))
        }
        .sorted { ($0.title, $0.id) < ($1.title, $1.id) }
    }

    /// The field's caption. Same tense rule as the ladders'
    /// (``EventState/propsChanceCaption(_:commenceTime:now:hasGradedRung:)``),
    /// but a field's legs are not "hitting" anything: each is a chance of being
    /// the one who leads.
    static func caption(
        eventStatus: String?,
        commenceTime: Date?,
        now: Date = Date(),
        isGraded: Bool
    ) -> String {
        if EventState.isSuspendedAndStarted(eventStatus, commenceTime: commenceTime, now: now)
            || (EventState.isFinished(eventStatus) && !isGraded) {
            return "last quoted chance"
        }
        return "chance of leading"
    }

    /// The leader first on a graded field, then the likeliest, then whoever
    /// opened likeliest, then by name so two equal legs cannot swap places
    /// between launches.
    ///
    /// The pregame step is for a finished field: every loser settles at 0%, and
    /// on SEA–WAS alphabetical order put AJ Barner (4% pregame) and Antonio
    /// Williams (3%) under the leader while Terry McLaurin (13%) sat behind
    /// "+4 more". The script says who was expected; that is the order worth reading.
    static func ordered(_ legs: [Candidate]) -> [Candidate] {
        legs.sorted { a, b in
            let aWon = a.hit == true, bWon = b.hit == true
            if aWon != bWon { return aWon }
            if a.probability != b.probability { return a.probability > b.probability }
            let aMark = a.pregameMark ?? -1, bMark = b.pregameMark ?? -1
            if aMark != bMark { return aMark > bMark }
            return a.name < b.name
        }
    }
}
