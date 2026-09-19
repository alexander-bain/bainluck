import SwiftUI

/// #7036, third arm — a team colour used as **text**, on surfaces that never had
/// a pair to resolve.
///
/// **Why this is not `cardColorHexes`.** The first two arms floored the places
/// that draw an away/home PAIR, so they route through `ProbabilityBarPalette`,
/// which already owns a default-and-ladder path to fall into. The sites left over
/// have no pair and no palette: they paint ONE stored `primary_color` straight
/// into `foregroundStyle` on a white card, and each already carries its own
/// hardcoded default for a team with no colour at all. So the floor those sites
/// need is not "re-derive the pair", it is "use the default you already have".
///
/// **What a reader sees without it.** `DiscoverView`'s guess card prints the
/// threshold as 46-point black rounded text in the home team's colour — the
/// largest number on the app's default landing surface. `MyStuffView`'s merged
/// future rows print the probability in the matched team's colour. For the 146
/// clubs whose stored colour is under 3:1 (Fulham and Lyon are both `#ffffff`)
/// those numbers are painted white on white: present in the hierarchy, read
/// correctly by VoiceOver, and invisible.
///
/// **The fallback is the caller's existing default, and it has to clear the floor
/// itself** — otherwise this swaps one invisible colour for another. Both real
/// callers were measured before being wired up: `#2563EB` is 5.17:1 and
/// `#6B7280` is 4.83:1 against the white card. That is a property of the
/// argument, not of this function, so it is asserted per-caller in the tests
/// rather than assumed here.
extension TeamTextContrast {

    /// The hex to draw this team's text in: the stored colour when it clears the
    /// floor, otherwise the caller's own default.
    ///
    /// Returns a hex rather than a `Color` because a `Color` cannot be compared
    /// in a test — asserting on the resolved HEX is the only assertion that can
    /// fail when a call site quietly goes back to passing `primaryColor` raw,
    /// which is the mutant this whole arm exists to kill.
    static func textHexOnCard(_ hex: String?, fallback: String) -> String {
        usableForText(hex) ?? fallback
    }

    /// `textHexOnCard` as a `Color` — the form the views take.
    static func textColorOnCard(_ hex: String?, fallback: String) -> Color {
        Color(hex: textHexOnCard(hex, fallback: fallback))
    }
}
