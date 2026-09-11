import SwiftUI

/// Which side, if any, a Player Props card may claim its player plays for.
///
/// #4919 — FIVE NEW ENGLAND PLAYERS LABELLED "AWAY" ON THEIR OWN HOME GAME.
/// Photographed on `bainluck://events/15305028`, and it is not downstream of
/// that row's bad attachment (#3529): the same defect draws 4 of the 20 player
/// cards on `14780143`, a correctly-matched Bucs @ Bengals fixture — and one of
/// the four is Kenny Gainwell, a Bengal, i.e. the HOME side, printed "Away".
///
/// The cause was a default standing in for a measurement:
///
///     let apiTeam = props.first?.prop.playerTeam ?? "away"
///     let teamLabel = apiTeam == "home" ? "Home" : "Away"
///     let color     = apiTeam == "home" ? homeColor : awayColor
///
/// `player_team` is served only when the backend's roster match finds the
/// player; when it misses, the key is absent — 95 of that fixture's 325 prop
/// rows, clustered onto 4 of its players. `"home"` was the only value that
/// yielded "Home", so **every unknown fell one way**, and one missing value
/// produced three separate false claims: the grey word under the name, the
/// colour tinting the whole card, and membership of the away team's filter.
///
/// 🔴 AN ABSENT VALUE IS NOT EVIDENCE FOR THE OTHER SIDE. A card that cannot
/// name its player's team says nothing, takes a neutral tint, and answers only
/// the "All" filter. Against a false claim, no claim is strictly better
/// (standing notice 34) — and a reader who ignores the grey word entirely was
/// still being misled by the colour.
///
/// `.unknown` also absorbs any value that is neither `"home"` nor `"away"`. The
/// serializer emits only those two today (`routes/events.py`, `side = "home" if
/// … else "away"`), but an unrecognised string is not evidence for away either,
/// and the old `!= "home"` spelling would have printed one.
enum PlayerPropsTeam {

    /// The three states `player_team` can actually reach the client in.
    enum Side: Equatable {
        case home
        case away
        /// Served null, absent, or a value this client does not recognise.
        case unknown
    }

    /// Reads the served `player_team`. Anything but the two known values is
    /// `.unknown` — never a side.
    static func side(for served: String?) -> Side {
        switch served {
        case "home": return .home
        case "away": return .away
        default: return .unknown
        }
    }

    /// The grey word under the player's name. `nil` prints nothing at all,
    /// rather than a side we cannot stand behind.
    static func label(for side: Side) -> String? {
        switch side {
        case .home: return "Home"
        case .away: return "Away"
        case .unknown: return nil
        }
    }

    /// The card's tint. The neutral is the third claim the old default made
    /// silently: a reader who never reads the grey word still saw an
    /// unattributed player wearing the away side's colour.
    static func color(for side: Side, home: Color, away: Color) -> Color {
        switch side {
        case .home: return home
        case .away: return away
        case .unknown: return DS.textSecondary
        }
    }

    /// The value the team filter matches on. `nil` matches neither "home" nor
    /// "away", so an unattributed player appears under "All" only — it is not
    /// silently counted into one team's roster.
    static func filterValue(for side: Side) -> String? {
        switch side {
        case .home: return "home"
        case .away: return "away"
        case .unknown: return nil
        }
    }
}
