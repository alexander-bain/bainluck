import Foundation

let bainLuckFallbackURL = URL(string: "https://bainluck.com") ?? URL(fileURLWithPath: "/")

enum BainLuckShareURLStyle {
    case plain
    case nativeCard
}

func eventShareURL(_ eventID: Int, style: BainLuckShareURLStyle = .plain) -> String {
    let base = "https://bainluck.com/events/\(eventID)"
    switch style {
    case .plain:
        return base
    case .nativeCard:
        return "\(base)?utm_source=share&utm_medium=native&utm_campaign=card&content_type=event&item_id=\(eventID)"
    }
}

/// The sentence a shared game card carries: both sides named, each beside its
/// own percent.
///
/// #4306 — this used to read `"<away> vs <home> — <home>% on Bain Luck"`. The
/// number was the home side's while the first name was the away side's, so a
/// message that left the app and went to other people stated the opposite of
/// the market, and did so with nothing on it to say whose number it was.
///
/// Both sides are named rather than one, because the card being shared draws
/// both (`DiscoverEventCard` prints the away and home percents either side of
/// "Win Probability"). A share that quotes one number a reader cannot attribute
/// is the defect again in a shorter sentence; a share that mirrors the card is
/// checkable against the thing it came from. The percents must therefore be the
/// pair `duelPercents` decided for that card and not a fresh rounding — pass
/// `duel[0]` and `duel[1]` straight in.
///
/// Falls back to the bare fixture when either percent is missing: "no price" is
/// not a price, and half a duel is not a duel.
func eventShareMessage(
    away: String,
    home: String,
    awayPercent: Int?,
    homePercent: Int?
) -> String {
    guard let awayPercent, let homePercent else {
        return "\(away) vs \(home) on Bain Luck"
    }
    return "\(away) \(awayPercent)% vs \(home) \(homePercent)% on Bain Luck"
}

func futuresShareURL(_ marketID: Int, style: BainLuckShareURLStyle = .plain) -> String {
    let base = "https://bainluck.com/futures/\(marketID)"
    switch style {
    case .plain:
        return base
    case .nativeCard:
        return "\(base)?utm_source=share&utm_medium=native&utm_campaign=card&content_type=futures&item_id=\(marketID)"
    }
}
