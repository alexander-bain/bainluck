import Foundation

/// What a Player Props stat group calls itself.
///
/// #5113 — THE STAT NAME TRUNCATES BECAUSE THE LABEL SPENDS ITS WIDTH ON THE
/// MATCHUP. Photographed on `bainluck://events/15308637`:
///
///     TAMPA BAY VS ATLANTA: HITS + RUNS + R…   chance of hitting   Final 2
///
/// The reader is already on the Tampa Bay vs Atlanta page and the teams are in
/// the nav bar two inches above. Repeating them inside every stat label on
/// every card spends the width the actual stat name needs, so "Hits + Runs +
/// RBIs" truncates on all nine cards in the shot while "Total Bases" and
/// "Earned Runs" survive only by being short.
///
/// 🔴 STRIP A PREFIX ONLY WHEN THE READER CAN ALREADY SEE IT. The prefix is
/// dropped when it names *this event's two teams* — not when it merely holds a
/// separator. Cutting blindly at the first colon is the tempting version and it
/// is wrong: the Polymarket ladder puts the **player** there
/// (`"Cole Young: Total Bases O/U 2.5"`), and a market whose stat name simply
/// contains a colon would lose its own name.
///
/// Measured before choosing the rule (19 events, production, 2026-09-11):
/// every one of 3,974 rendered props carried a matchup prefix, all from Kalshi,
/// and the only separator in 2,136 sampled prefixes was `vs` — no `@`, no
/// `at`, no `v.`. The known-team test below fired on **100%** of them,
/// including the abbreviated shapes `"Dallas vs New York G"` and
/// `"New York J vs Tennessee"`. The Polymarket player-prefix shape did not
/// appear at all in the rendered population, so it is handled on the strength
/// of the serializer, not of a sample — which is why it is a separate, explicit
/// branch rather than a widening of the matchup one.
///
/// The group key is untouched: `PlayerPropsCardView` keys stat groups on the
/// full served `marketName`, and only the *display* passes through here. Two
/// stats that differ solely in their prefix therefore remain two groups, so
/// #4857's ordering is unaffected.
enum PlayerPropsStatLabel {

    /// Prefixes that are noise wherever they appear, stripped after the
    /// redundant-prefix test. Pre-existing behaviour, kept verbatim.
    private static let noisePrefixes = ["Player ", "Batter ", "Pitcher "]

    /// The label drawn above a stat group's rungs.
    ///
    /// - Parameters:
    ///   - marketName: the served `market_name`, used verbatim as the group key.
    ///   - homeTeam: this event's home team, as the page already shows it.
    ///   - awayTeam: this event's away team.
    ///   - player: the card's player, or `nil` when unknown.
    static func display(
        marketName: String,
        homeTeam: String,
        awayTeam: String,
        player: String?
    ) -> String {
        let raw = marketName.trimmingCharacters(in: .whitespaces)

        var label = raw
        if let colon = raw.firstIndex(of: ":") {
            let prefix = String(raw[raw.startIndex..<colon])
                .trimmingCharacters(in: .whitespaces)
            let remainder = String(raw[raw.index(after: colon)...])
                .trimmingCharacters(in: .whitespaces)

            // A prefix may only be dropped if something else on screen already
            // says it. An empty remainder never qualifies: a card with no stat
            // name is worse than a long one.
            if !remainder.isEmpty,
               namesBothTeams(prefix, homeTeam: homeTeam, awayTeam: awayTeam)
                || namesThePlayer(prefix, player: player) {
                label = remainder
            }
        }

        for prefix in noisePrefixes where label.hasPrefix(prefix) {
            label = String(label.dropFirst(prefix.count))
        }

        let trimmed = label.trimmingCharacters(in: .whitespaces)
        // Never render nothing. If every rule above ate the string, the served
        // name — matchup and all — is still the honest answer.
        return trimmed.isEmpty ? raw : trimmed
    }

    /// The nav bar already names both teams, so a prefix that names them too is
    /// spending width on a fact the reader has. Requires a token from **each**
    /// side: one alone is a team name that could belong to the stat.
    private static func namesBothTeams(
        _ prefix: String,
        homeTeam: String,
        awayTeam: String
    ) -> Bool {
        let prefixTokens = tokens(prefix)
        guard !prefixTokens.isEmpty else { return false }
        return shares(prefixTokens, with: homeTeam)
            && shares(prefixTokens, with: awayTeam)
    }

    /// The card header already names the player.
    private static func namesThePlayer(_ prefix: String, player: String?) -> Bool {
        guard let player, !player.isEmpty else { return false }
        return prefix.compare(
            player.trimmingCharacters(in: .whitespaces),
            options: [.caseInsensitive, .diacriticInsensitive]
        ) == .orderedSame
    }

    private static func shares(_ prefixTokens: Set<String>, with team: String) -> Bool {
        !tokens(team).isEmpty && !tokens(team).isDisjoint(with: prefixTokens)
    }

    /// Words of three letters or more, lowercased and unpunctuated. Matching on
    /// whole tokens rather than substrings keeps `"Bay"` out of `"Bayern"`, and
    /// the length floor drops the joiners (`vs`, `at`, `@`) that would
    /// otherwise let one team's name satisfy both sides.
    private static func tokens(_ text: String) -> Set<String> {
        Set(
            text.lowercased()
                .components(separatedBy: CharacterSet.alphanumerics.inverted)
                .filter { $0.count >= 3 }
        )
    }
}
