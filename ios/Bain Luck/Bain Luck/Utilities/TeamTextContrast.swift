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

    /// The app's primary pages draw on `Color.cardBackground`, which is white (`1.0`).
    /// Widgets, dark mode, Watch faces, and Live Activities sit on dark surfaces (`0.012`).
    static let cardSurfaceLuminance = 1.0
    static let darkSurfaceLuminance = 0.012

    static func surfaceLuminance(for colorScheme: ColorScheme) -> Double {
        colorScheme == .dark ? darkSurfaceLuminance : cardSurfaceLuminance
    }

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

    /// The WCAG contrast ratio of a hex colour against a surface of arbitrary
    /// relative luminance (`0.0 ... 1.0`), or `nil` when `hex` cannot be parsed.
    static func contrast(_ hex: String?, againstSurfaceLuminance surfaceLuminance: Double) -> Double? {
        guard let l = relativeLuminance(hex) else { return nil }
        let bg = min(max(surfaceLuminance, 0.0), 1.0)
        return (max(l, bg) + 0.05) / (min(l, bg) + 0.05)
    }

    /// Does `hex` clear WCAG's 3:1 floor against `surfaceLuminance`?
    static func readableOnSurface(_ hex: String?, surfaceLuminance: Double) -> Bool {
        guard let ratio = contrast(hex, againstSurfaceLuminance: surfaceLuminance) else { return false }
        return ratio >= minimumRatio
    }

    /// The WCAG contrast ratio of a hex colour against the card surface, or
    /// `nil` when the colour cannot be parsed. `1.0` means identical to the
    /// surface: invisible.
    static func contrastVsCardSurface(_ hex: String?) -> Double? {
        contrast(hex, againstSurfaceLuminance: cardSurfaceLuminance)
    }

    /// Does this colour clear the floor? An absent or unparseable colour is not
    /// "readable" — it has no colour to judge.
    static func readableOnCard(_ hex: String?) -> Bool {
        readableOnSurface(hex, surfaceLuminance: cardSurfaceLuminance)
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
    static func cardColorHexes(
        awayHex: String?,
        homeHex: String?,
        awaySecondaryHex: String? = nil,
        checkHueFamily: Bool = true
    ) -> (away: String, home: String) {
        ProbabilityBarPalette.pair(
            awayHex: usableForText(awayHex),
            homeHex: usableForText(homeHex),
            awaySecondaryHex: usableForText(awaySecondaryHex),
            checkHueFamily: checkHueFamily
        )
    }

    /// `cardColorHexes` as `Color`s, away first — the form the views take.
    static func cardColors(
        awayHex: String?,
        homeHex: String?,
        awaySecondaryHex: String? = nil,
        checkHueFamily: Bool = true
    ) -> (away: Color, home: Color) {
        let hexes = cardColorHexes(
            awayHex: awayHex,
            homeHex: homeHex,
            awaySecondaryHex: awaySecondaryHex,
            checkHueFamily: checkHueFamily
        )
        return (Color(hex: hexes.away), Color(hex: hexes.home))
    }

    /// Ruling 214-A1 (`#12808` Fable note): on quiet pregame/projection lines, a team
    /// whose Ruling-197 colour fell back to slate (`#64748B`) prints one shade darker
    /// (`#475569`, matching the website) on light surfaces — and one shade lighter
    /// (`#94A3B8`, `slate-400`, 6.61:1) on dark surfaces — so it reads distinct from `"Pregame"`.
    static let quietLineSlateFallbackHex = "#475569"
    static let quietDarkLineSlateFallbackHex = "#94A3B8"

    static func quietLineHex(_ resolvedCardHex: String, surfaceLuminance: Double = cardSurfaceLuminance) -> String {
        guard resolvedCardHex.uppercased() == ProbabilityBarPalette.awayDefault.uppercased() else {
            return resolvedCardHex
        }
        return surfaceLuminance >= 0.5 ? quietLineSlateFallbackHex : quietDarkLineSlateFallbackHex
    }

    // MARK: - Ruling 221 (Dark Surfaces: Widgets, Dark Mode, Watch, Live Activity)

    /// Canonical `#RRGGBB` spelling when `hex` parses through `ProbabilityBarPalette.rgb`.
    static func canonicalHex(_ hex: String?) -> String? {
        guard let rgb = ProbabilityBarPalette.rgb(hex) else { return nil }
        return String(format: "#%02X%02X%02X", rgb.r, rgb.g, rgb.b)
    }

    /// Lightens `hex` in HSL space (preserving hue and saturation) by the minimum
    /// lightness increase needed for the quantized `#RRGGBB` result to clear `minimumRatio`
    /// (`3.0:1`) against `surfaceLuminance`. Returns `nil` if `hex` is absent/unparseable.
    static func lightenedForDarkSurface(
        _ hex: String?,
        surfaceLuminance: Double = darkSurfaceLuminance
    ) -> String? {
        guard let rgb = ProbabilityBarPalette.rgb(hex) else { return nil }
        if readableOnSurface(hex, surfaceLuminance: surfaceLuminance) {
            return String(format: "#%02X%02X%02X", rgb.r, rgb.g, rgb.b)
        }
        let r0 = Double(rgb.r) / 255.0
        let g0 = Double(rgb.g) / 255.0
        let b0 = Double(rgb.b) / 255.0
        let hi = max(r0, g0, b0)
        let lo = min(r0, g0, b0)
        let l0 = (hi + lo) / 2.0
        let delta = hi - lo

        let hue: Double
        let sat: Double
        if delta == 0 {
            hue = 0.0
            sat = 0.0
        } else {
            sat = l0 > 0.5 ? delta / (2.0 - hi - lo) : delta / (hi + lo)
            if hi == r0 {
                var h6 = (g0 - b0) / delta
                if h6 < 0 { h6 += 6.0 }
                hue = h6 / 6.0
            } else if hi == g0 {
                hue = (((b0 - r0) / delta) + 2.0) / 6.0
            } else {
                hue = (((r0 - g0) / delta) + 4.0) / 6.0
            }
        }

        func hexAtLightness(_ l: Double) -> String {
            let clampedL = min(max(l, 0.0), 1.0)
            let rf: Double
            let gf: Double
            let bf: Double
            if sat == 0 {
                rf = clampedL
                gf = clampedL
                bf = clampedL
            } else {
                let q = clampedL < 0.5 ? clampedL * (1.0 + sat) : clampedL + sat - clampedL * sat
                let p = 2.0 * clampedL - q
                func hue2rgb(_ tIn: Double) -> Double {
                    var t = tIn
                    if t < 0 { t += 1.0 }
                    if t > 1 { t -= 1.0 }
                    if t < 1.0 / 6.0 { return p + (q - p) * 6.0 * t }
                    if t < 1.0 / 2.0 { return q }
                    if t < 2.0 / 3.0 { return p + (q - p) * (2.0 / 3.0 - t) * 6.0 }
                    return p
                }
                rf = hue2rgb(hue + 1.0 / 3.0)
                gf = hue2rgb(hue)
                bf = hue2rgb(hue - 1.0 / 3.0)
            }
            let ri = Int((min(max(rf, 0.0), 1.0) * 255.0).rounded())
            let gi = Int((min(max(gf, 0.0), 1.0) * 255.0).rounded())
            let bi = Int((min(max(bf, 0.0), 1.0) * 255.0).rounded())
            return String(format: "#%02X%02X%02X", ri, gi, bi)
        }

        var low = l0
        var high = 1.0
        for _ in 0..<24 {
            let mid = (low + high) / 2.0
            let candidate = hexAtLightness(mid)
            if readableOnSurface(candidate, surfaceLuminance: surfaceLuminance) {
                high = mid
            } else {
                low = mid
            }
        }

        var lCursor = high
        while lCursor <= 1.0 {
            let candidate = hexAtLightness(lCursor)
            if readableOnSurface(candidate, surfaceLuminance: surfaceLuminance) {
                return candidate
            }
            lCursor += 1.0 / 512.0
        }
        return "#FFFFFF"
    }

    /// Ruling 221 single-team dark-surface colour:
    /// 1. `primaryHex` when it clears 3:1 against `surfaceLuminance`;
    /// 2. else `secondaryHex` when present and readable (>= 3:1);
    /// 3. else `lightenedForDarkSurface(primaryHex, surfaceLuminance:)` (never grey
    ///    when a valid primary colour exists);
    /// 4. `nil` only when no valid primary or readable secondary colour exists.
    static func usableOnDarkSurface(
        primaryHex: String?,
        secondaryHex: String? = nil,
        surfaceLuminance: Double = darkSurfaceLuminance
    ) -> String? {
        if readableOnSurface(primaryHex, surfaceLuminance: surfaceLuminance) {
            return canonicalHex(primaryHex)
        }
        if readableOnSurface(secondaryHex, surfaceLuminance: surfaceLuminance) {
            return canonicalHex(secondaryHex)
        }
        return lightenedForDarkSurface(primaryHex, surfaceLuminance: surfaceLuminance)
    }

    /// Ruling 221 + Ruling 197 away/home pair on a dark surface.
    static func darkSurfaceColorHexes(
        awayHex: String?,
        homeHex: String?,
        awaySecondaryHex: String? = nil,
        homeSecondaryHex: String? = nil,
        surfaceLuminance: Double = darkSurfaceLuminance,
        checkHueFamily: Bool = true
    ) -> (away: String, home: String) {
        let awayCandidate = usableOnDarkSurface(
            primaryHex: awayHex,
            secondaryHex: awaySecondaryHex,
            surfaceLuminance: surfaceLuminance
        )
        let homeCandidate = usableOnDarkSurface(
            primaryHex: homeHex,
            secondaryHex: homeSecondaryHex,
            surfaceLuminance: surfaceLuminance
        )
        let awayClashAlternate: String? = {
            if readableOnSurface(awayHex, surfaceLuminance: surfaceLuminance) {
                return readableOnSurface(awaySecondaryHex, surfaceLuminance: surfaceLuminance)
                    ? canonicalHex(awaySecondaryHex)
                    : nil
            }
            if readableOnSurface(awaySecondaryHex, surfaceLuminance: surfaceLuminance) {
                // Away switched to its readable secondary (e.g. Ravens gold #9E7C0C); if
                // that clashes with home (e.g. Steelers gold #FFB612), use away's lightened
                // primary (#6450DC purple) before falling back to slate grey.
                return lightenedForDarkSurface(awayHex, surfaceLuminance: surfaceLuminance)
            }
            return nil
        }()
        let raw = ProbabilityBarPalette.pair(
            awayHex: awayCandidate,
            homeHex: homeCandidate,
            awaySecondaryHex: awayClashAlternate,
            checkHueFamily: checkHueFamily
        )
        let safeAway = readableOnSurface(raw.away, surfaceLuminance: surfaceLuminance)
            ? raw.away
            : (lightenedForDarkSurface(raw.away, surfaceLuminance: surfaceLuminance) ?? raw.away)
        let safeHome = readableOnSurface(raw.home, surfaceLuminance: surfaceLuminance)
            ? raw.home
            : (lightenedForDarkSurface(raw.home, surfaceLuminance: surfaceLuminance) ?? raw.home)
        return (safeAway, safeHome)
    }

    /// Unified away/home pair for any surface luminance (`>= 0.5` light card, `< 0.5` dark surface).
    static func surfaceColorHexes(
        awayHex: String?,
        homeHex: String?,
        awaySecondaryHex: String? = nil,
        homeSecondaryHex: String? = nil,
        surfaceLuminance: Double,
        checkHueFamily: Bool = true
    ) -> (away: String, home: String) {
        if surfaceLuminance >= 0.5 {
            return cardColorHexes(
                awayHex: awayHex,
                homeHex: homeHex,
                awaySecondaryHex: awaySecondaryHex,
                checkHueFamily: checkHueFamily
            )
        }
        return darkSurfaceColorHexes(
            awayHex: awayHex,
            homeHex: homeHex,
            awaySecondaryHex: awaySecondaryHex,
            homeSecondaryHex: homeSecondaryHex,
            surfaceLuminance: surfaceLuminance,
            checkHueFamily: checkHueFamily
        )
    }

    /// Unified away/home pair for a SwiftUI `ColorScheme` (`.light` vs `.dark`).
    static func surfaceColorHexes(
        awayHex: String?,
        homeHex: String?,
        awaySecondaryHex: String? = nil,
        homeSecondaryHex: String? = nil,
        colorScheme: ColorScheme,
        checkHueFamily: Bool = true
    ) -> (away: String, home: String) {
        surfaceColorHexes(
            awayHex: awayHex,
            homeHex: homeHex,
            awaySecondaryHex: awaySecondaryHex,
            homeSecondaryHex: homeSecondaryHex,
            surfaceLuminance: surfaceLuminance(for: colorScheme),
            checkHueFamily: checkHueFamily
        )
    }

    static func surfaceColors(
        awayHex: String?,
        homeHex: String?,
        awaySecondaryHex: String? = nil,
        homeSecondaryHex: String? = nil,
        colorScheme: ColorScheme,
        checkHueFamily: Bool = true
    ) -> (away: Color, home: Color) {
        let hexes = surfaceColorHexes(
            awayHex: awayHex,
            homeHex: homeHex,
            awaySecondaryHex: awaySecondaryHex,
            homeSecondaryHex: homeSecondaryHex,
            colorScheme: colorScheme,
            checkHueFamily: checkHueFamily
        )
        return (Color(hex: hexes.away), Color(hex: hexes.home))
    }
}
