import SwiftUI

/// Whether a team's brand colour is safe to *draw with* on the event page.
///
/// **Why this exists — #7036.** Fulham's stored `primary_color` is `#ffffff`,
/// and the event page is one white surface. So on Liverpool 0–0 Fulham the
/// Championship Path drew Fulham's card entirely in white: the `FUL` crest chip
/// was white letters on a 15%-white fill, the Relegated bar was a white capsule
/// on a near-white track, and `31%` / `3%` / `1%` were white text on a white
/// card. The trend badges are hardcoded red/green, so the card rendered a
/// legible `↓0.5%` next to a blank space where the probability should be —
/// populated-looking and unreadable, which is worse than honestly empty.
///
/// **This is not `ProbabilityBarPalette`'s job, and that is the point.** That
/// type's contract, in its own words, is *"the returned pair is never two
/// indistinguishable colours"* — contrast between **the two sides**. Liverpool
/// `#d11317` and Fulham `#ffffff` are ~253 apart and satisfy it perfectly. What
/// nothing supplied is contrast against **the surface the colour is drawn on**,
/// which is the guarantee a caller painting text, a thin bar or a chart line
/// needs. The two are independent, and a colour can pass one and fail the other.
///
/// **The defect is invisible to almost every test we write** (the lesson #5165
/// wrote down on the web side, restated here because Swift got none of that
/// work): every character is in the view hierarchy, correct and in order. An
/// assertion that `31%` renders passes on the bug, and a screen reader reads the
/// card perfectly. Only the pixels are wrong. A guard for this class has to
/// assert the **resolved colour**, never the text.
///
/// **Why a standard rather than a tuned cutoff.** #5165 measured the production
/// `teams` distribution and found no natural gap to cut on: it runs 1.00:1
/// (`#ffffff`, 26 teams) through the yellows and golds into the pale blues with
/// nothing between. Any hand-picked number would be a number someone picked, so
/// this uses WCAG's floor for UI and large text — the same 3:1 the web arm
/// chose, at the same price it measured (146 teams, 10.1%). Native and web
/// answering this question differently would be its own defect.
///
/// **A recoloured team is not a degraded rendering.** A colour below the floor
/// is reported as *absent*, so `ProbabilityBarPalette` applies the slot default
/// it already gives a team with no stored colour at all — the ordinary
/// appearance, not a new one. That also means the pair contract is re-derived
/// rather than bypassed: the palette re-runs its own collision check and ladder
/// on the substituted value, so flooring one side can never collapse the two
/// sides onto one colour. Both defaults clear this floor themselves
/// (`#64748B` is 4.68:1, `#2563EB` is well under the surface), so the fallback
/// can never itself be the invisible case.
enum TeamTextContrast {

    /// WCAG's minimum contrast for UI components and large text. Raising this to
    /// AA for small text (4.5:1) is a design decision with a measured price —
    /// #5165's table puts it at 240 teams, 16.5% — and one line of code. It is
    /// deliberately not taken inside a bug fix.
    static let minimumRatio = 3.0

    /// The page is light-mode only and every card this feeds is drawn on
    /// `Color.cardBackground`, which is white. Named so that a dark mode — if it
    /// ever arrives — arrives as a compile error here rather than as a second
    /// silent invisibility.
    static let cardSurfaceLuminance = 1.0

    /// WCAG relative luminance of a hex colour, or `nil` when it cannot be
    /// parsed.
    ///
    /// Parsing goes through `ProbabilityBarPalette.rgb` rather than a second
    /// spelling of the same scan: a colour this type calls unparseable and the
    /// palette calls usable would floor a value the palette then paints anyway.
    static func relativeLuminance(_ hex: String?) -> Double? {
        guard let rgb = ProbabilityBarPalette.rgb(hex) else { return nil }
        func channel(_ v: Int) -> Double {
            let c = Double(v) / 255.0
            return c <= 0.04045 ? c / 12.92 : pow((c + 0.055) / 1.055, 2.4)
        }
        return 0.2126 * channel(rgb.r) + 0.7152 * channel(rgb.g) + 0.0722 * channel(rgb.b)
    }

    /// The WCAG contrast ratio of a hex colour against the card surface, or
    /// `nil` when the colour cannot be parsed. `1.0` means identical to the
    /// surface: invisible.
    static func contrastVsCardSurface(_ hex: String?) -> Double? {
        guard let l = relativeLuminance(hex) else { return nil }
        return (cardSurfaceLuminance + 0.05) / (l + 0.05)
    }

    /// Does this colour clear the floor? An absent or unparseable colour is not
    /// "readable" — it has no colour to judge.
    static func readableOnCard(_ hex: String?) -> Bool {
        guard let ratio = contrastVsCardSurface(hex) else { return false }
        return ratio >= minimumRatio
    }

    /// The colour if it is safe to draw with on a card, otherwise `nil`.
    ///
    /// `nil` means **absent**, which is the whole design: it is what a caller
    /// passes to `ProbabilityBarPalette` so the existing default-and-ladder path
    /// runs, rather than a replacement colour chosen here. A floor added under
    /// existing behaviour, not a second palette.
    static func usableForText(_ hex: String?) -> String? {
        readableOnCard(hex) ? hex : nil
    }

    // MARK: - What a card calls

    /// A card's away/home pair: #2902's palette with #7036's floor under it, as
    /// hexes.
    ///
    /// **Named for the surface, not for one page.** This shipped as
    /// `eventPageColorHexes` when the event page was the only caller. It is now
    /// what every white card in the app resolves its pair through — the event
    /// page's Championship Path, the Sports/My Stuff/feed row
    /// (`EventCardView`), and the Discover game card
    /// (`NativeEventDiscoverCard`) — because the defect was never the event
    /// page's: it is one function of the stored colour and the surface, and all
    /// three surfaces are `Color.cardBackground`. A name that says "event page"
    /// on a function three other screens depend on is how the next caller talks
    /// itself into a fourth copy.
    ///
    /// This exists as a named function rather than two lines inside each view
    /// because otherwise **the floor's wiring is the one part of this fix no
    /// test can reach** — the unit tests below would all stay green against a
    /// call site that had quietly gone back to passing raw `primaryColor`, which
    /// is precisely the mutant worth killing. Hoisting it here leaves only a
    /// single-expression delegation in each view, and each view exposes that
    /// delegation so a test can drive it on a real payload.
    static func cardColorHexes(awayHex: String?, homeHex: String?) -> (away: String, home: String) {
        ProbabilityBarPalette.pair(
            awayHex: usableForText(awayHex),
            homeHex: usableForText(homeHex)
        )
    }

    /// `cardColorHexes` as `Color`s, away first — the form the views take.
    static func cardColors(awayHex: String?, homeHex: String?) -> (away: Color, home: Color) {
        let hexes = cardColorHexes(awayHex: awayHex, homeHex: homeHex)
        return (Color(hex: hexes.away), Color(hex: hexes.home))
    }
}
