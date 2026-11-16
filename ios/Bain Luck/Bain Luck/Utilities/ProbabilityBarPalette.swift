import SwiftUI

/// The two segment colours for a two-sided win-probability bar.
///
/// **Why this exists — #2902.** `EventCardView` resolved both sides with
/// `Color(hex: teamData?.primaryColor ?? "#6b7280")`. A tennis player has no
/// team row and therefore no `primary_color`, so *both* segments came back the
/// same grey. The bar still drew two rectangles; they were just one rectangle.
/// On the Sports tab during the US Open that made Tabilo–Popyrin **97/3** and a
/// 58/42 match and a 60/40 match look identical: three cards, three very
/// different questions, three flat grey blocks. Width cannot show a split whose
/// edge is invisible. The same fallback hit golf pairings, MMA, and any team we
/// have not mapped — tennis was only where it was most visible.
///
/// **The contract.** The returned pair is never two indistinguishable colours.
/// That is the whole job, and it is what the guard tests assert; everything
/// below is how the promise is kept:
///
/// 1. Both sides carry a usable brand colour, and they read apart → use them.
///    Real crests always win; this type never repaints a Dodgers/Giants bar.
/// 2. A side has no usable colour → it takes its slot's default first
///    (`awayDefault` / `homeDefault` — the pair `DiscoverEventCard` has always
///    shipped, so Discover's cards do not change), and if that collides with
///    the *other* side's colour, the next distinguishable rung of `ladder`.
/// 3. Both sides carry brand colours that do not read apart (two reds, or the
///    identical hex twice) → home keeps its crest, away is moved off it. A bar
///    you cannot read is worse than a bar in the wrong red.
///
/// A malformed or empty hex is treated as **absent**, not as a colour.
/// `Color(hex:)` scans with `Scanner` and leaves `rgb = 0` when the scan fails,
/// so "" and "not-a-color" both render **black** — a colour nobody chose,
/// silently, and one that reads as deliberate on screen.
enum ProbabilityBarPalette {
    /// The away slot's default. Both defaults are the pair `DiscoverEventCard`
    /// already used, kept so the fix is a change to the cards that were broken
    /// and not to the one card that was right.
    static let awayDefault = "#64748B"  // slate-500
    /// The home slot's default.
    static let homeDefault = "#2563EB"  // blue-600

    /// Tried in order when a slot's own default is already taken by the other
    /// side. Four rungs that read apart from each other and from both defaults.
    static let ladder = ["#64748B", "#2563EB", "#F59E0B", "#8B5CF6", "#111827"]

    /// Below this Euclidean RGB distance two segments do not read as two
    /// segments at bar height (5–10pt). Deliberately low: it separates
    /// "the same colour twice" and near-twins (`#EF4444` vs `#DC2626`, 46) and
    /// leaves genuinely different crests alone (`#552583` vs `#FDB927`, 240).
    static let minimumDistance = 60.0

    /// Ruling 197 — discrete chromatic hue families shared verbatim with the
    /// website (`frontend/lib/teamColors.ts` `colorHueFamily`, `#12757`), so
    /// native and web agree on every matchup:
    /// - neutral/achromatic (`lightness < 6%`, `lightness > 94%`, or HSL
    ///   `saturation < 22%`) returns `nil`
    /// - `red` (`>= 335°` or `< 15°`), `orange` (`15°..<38°`),
    ///   `yellow` (`38°..<70°`), `green` (`70°..<168°`), `teal` (`168°..<196°`),
    ///   `blue` (`196°..<245°`), `purple` (`245°..<305°`), `magenta` (`305°..<335°`).
    enum HueFamily: String, Equatable, Sendable {
        case red, orange, yellow, green, teal, blue, purple, magenta
    }

    // MARK: - Pure colour maths (the part the tests drive)

    /// `(r, g, b)` in 0…255, or `nil` when `hex` is absent or unparseable.
    ///
    /// Accepts `#RRGGBB` and `RRGGBB`. Everything else — three-digit shorthand,
    /// a colour name, a truncated string, `nil` — is *absent*, because a caller
    /// that cannot say what colour it means must not be handed black.
    static func rgb(_ hex: String?) -> (r: Int, g: Int, b: Int)? {
        guard let hex else { return nil }
        let body = hex.trimmingCharacters(in: .whitespaces).hasPrefix("#")
            ? String(hex.trimmingCharacters(in: .whitespaces).dropFirst())
            : hex.trimmingCharacters(in: .whitespaces)
        guard body.count == 6, body.allSatisfy({ $0.isHexDigit }) else { return nil }
        guard let value = UInt32(body, radix: 16) else { return nil }
        return (Int((value >> 16) & 0xFF), Int((value >> 8) & 0xFF), Int(value & 0xFF))
    }

    /// Euclidean distance in RGB between two hex strings. `nil` if either is
    /// unparseable — an unknown colour has no distance, it has no colour.
    static func distance(_ a: String?, _ b: String?) -> Double? {
        guard let x = rgb(a), let y = rgb(b) else { return nil }
        let dr = Double(x.r - y.r), dg = Double(x.g - y.g), db = Double(x.b - y.b)
        return (dr * dr + dg * dg + db * db).squareRoot()
    }

    /// Do these two read as two segments? Unparseable input is never "apart".
    static func distinguishable(_ a: String?, _ b: String?) -> Bool {
        guard let d = distance(a, b) else { return false }
        return d >= minimumDistance
    }

    /// Ruling 197 — chromatic hue family of `hex`, matching website
    /// `colorHueFamily` (`frontend/lib/teamColors.ts`, `#12757`).
    static func colorHueFamily(_ hex: String?) -> HueFamily? {
        guard let c = rgb(hex) else { return nil }
        let r = Double(c.r) / 255.0
        let g = Double(c.g) / 255.0
        let b = Double(c.b) / 255.0
        let hi = max(r, g, b)
        let lo = min(r, g, b)
        let lightness = (hi + lo) / 2.0
        let delta = hi - lo
        if delta == 0 || lightness < 0.06 || lightness > 0.94 {
            return nil
        }
        let saturation = lightness > 0.5 ? delta / (2.0 - hi - lo) : delta / (hi + lo)
        if saturation < 0.22 {
            return nil
        }
        let hue: Double
        if hi == r {
            let raw = 60.0 * ((g - b) / delta)
            hue = raw < 0 ? raw + 360.0 : raw
        } else if hi == g {
            hue = 60.0 * (((b - r) / delta) + 2.0)
        } else {
            hue = 60.0 * (((r - g) / delta) + 4.0)
        }
        if hue >= 335.0 || hue < 15.0 { return .red }
        if hue < 38.0 { return .orange }
        if hue < 70.0 { return .yellow }
        if hue < 168.0 { return .green }
        if hue < 196.0 { return .teal }
        if hue < 245.0 { return .blue }
        if hue < 305.0 { return .purple }
        return .magenta
    }

    /// Ruling 197 — whether two parseable chromatic brand colours belong to the
    /// same hue family (for example navy + royal blue in `.blue`, or two reds in
    /// `.red`). Neutral greys/blacks return `false`.
    static func sameHueFamily(_ a: String?, _ b: String?) -> Bool {
        guard let fa = colorHueFamily(a), let fb = colorHueFamily(b) else { return false }
        return fa == fb
    }

    /// The two segment hexes, away first — the order they are drawn in.
    ///
    /// Total: every input, including two nils and two identical hexes, returns
    /// a pair. Deterministic: the same input always returns the same pair, so a
    /// card does not change colour between renders.
    ///
    /// Ruling 197 (when `checkHueFamily == true`): when both primary colours are
    /// usable and either fail `distinguishable` or share a hue family
    /// (`sameHueFamily`), home keeps its primary colour and away switches to
    /// `awaySecondaryHex` when usable, distinguishable from home, and outside
    /// home's hue family; otherwise away switches to
    /// `partner(for: home, preferring: awayDefault)` (slate grey). Callers that
    /// omit `checkHueFamily` preserve existing RGB-distance-only behaviour.
    static func pair(
        awayHex: String?,
        homeHex: String?,
        awaySecondaryHex: String? = nil,
        checkHueFamily: Bool = false
    ) -> (away: String, home: String) {
        let away = usable(awayHex)
        let home = usable(homeHex)

        switch (away, home) {
        case let (a?, h?) where distinguishable(a, h) && (!checkHueFamily || !sameHueFamily(a, h)):
            return (a, h)                                   // rule 1
        case (_?, let h?):
            // rule 3 (+ Ruling 197 when opted in) — two crests that collide.
            // Home keeps its own; away tries its own second colour, else slate grey.
            if let sec = usable(awaySecondaryHex),
               distinguishable(sec, h),
               (!checkHueFamily || !sameHueFamily(sec, h)) {
                return (sec, h)
            }
            return (partner(for: h, preferring: awayDefault), h)
        case let (a?, nil):
            return (a, partner(for: a, preferring: homeDefault))   // rule 2
        case let (nil, h?):
            return (partner(for: h, preferring: awayDefault), h)   // rule 2
        case (nil, nil):
            return (awayDefault, homeDefault)               // rule 2, both slots
        }
    }

    /// A colour that reads apart from `taken`: the slot's own default when that
    /// works, else the first rung of the ladder that does, else — if nothing
    /// clears the bar, which needs a crest sitting on top of every rung — the
    /// furthest rung there is. Never returns `taken`.
    static func partner(for taken: String, preferring preferred: String) -> String {
        if distinguishable(preferred, taken) { return preferred }
        for candidate in ladder where distinguishable(candidate, taken) { return candidate }
        return ladder.max(by: { (distance($0, taken) ?? 0) < (distance($1, taken) ?? 0) })
            ?? preferred
    }

    /// `hex` in canonical `#RRGGBB` form, or `nil` when it is not a colour.
    private static func usable(_ hex: String?) -> String? {
        guard let hex, rgb(hex) != nil else { return nil }
        let t = hex.trimmingCharacters(in: .whitespaces)
        return t.hasPrefix("#") ? t.uppercased() : "#" + t.uppercased()
    }

    // MARK: - What the views call

    /// The two `Color`s, away first.
    static func colors(awayHex: String?, homeHex: String?) -> (away: Color, home: Color) {
        let hexes = pair(awayHex: awayHex, homeHex: homeHex)
        return (Color(hex: hexes.away), Color(hex: hexes.home))
    }
}
