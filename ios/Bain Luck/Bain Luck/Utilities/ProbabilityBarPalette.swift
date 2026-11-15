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

    /// Ruling 197 — maximum circular HSV hue separation (in degrees) at which
    /// two chromatic brand colours still read as the same colour family (for
    /// example Kansas `#0051BA` `214°`, Gonzaga `#041E42` `215°`, Patriots
    /// `#002244` `210°`, Kentucky `#0033A0` `221°`, Duke `#00539B` `208°`, and
    /// Lions `#0076B6` `201°` are all blue within `≤28°`, while claret `#660E36`
    /// `333°` vs red `#EF2F24` `3°` is `30.5°` apart and blue `#00338D` `218°`
    /// vs purple `#4F2683` `267°` is `48°` apart).
    static let sameHueFamilyMaxDegrees = 28.0
    static let chromaticMinimumSaturation = 0.35
    static let chromaticMinimumValue = 0.20

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

    /// HSV `(hueDegrees 0..<360, saturation 0…1, value 0…1)` for a parseable hex.
    static func hsv(_ hex: String?) -> (hue: Double, saturation: Double, value: Double)? {
        guard let c = rgb(hex) else { return nil }
        let r = Double(c.r) / 255.0
        let g = Double(c.g) / 255.0
        let b = Double(c.b) / 255.0
        let hi = max(r, g, b)
        let lo = min(r, g, b)
        let delta = hi - lo
        let saturation = hi == 0 ? 0 : delta / hi
        let hue: Double
        if delta == 0 {
            hue = 0
        } else if hi == r {
            let raw = 60.0 * ((g - b) / delta)
            hue = raw < 0 ? raw + 360.0 : raw
        } else if hi == g {
            hue = 60.0 * (((b - r) / delta) + 2.0)
        } else {
            hue = 60.0 * (((r - g) / delta) + 4.0)
        }
        return (hue: hue, saturation: saturation, value: hi)
    }

    /// Ruling 197 — whether two parseable chromatic brand colours belong to the
    /// same hue family (for example navy + royal blue, or two crimsons). Greys
    /// (`saturation < 0.35`, e.g. `#64748B`) and near-blacks (`value < 0.20`,
    /// e.g. `#111827`) are neutral rather than a hue family.
    static func sameHueFamily(_ a: String?, _ b: String?) -> Bool {
        guard let ha = hsv(a), let hb = hsv(b) else { return false }
        guard ha.saturation >= chromaticMinimumSaturation,
              hb.saturation >= chromaticMinimumSaturation,
              ha.value >= chromaticMinimumValue,
              hb.value >= chromaticMinimumValue
        else { return false }
        let rawDiff = abs(ha.hue - hb.hue).truncatingRemainder(dividingBy: 360.0)
        let circularDiff = min(rawDiff, 360.0 - rawDiff)
        return circularDiff <= sameHueFamilyMaxDegrees
    }

    /// The two segment hexes, away first — the order they are drawn in.
    ///
    /// Total: every input, including two nils and two identical hexes, returns
    /// a pair. Deterministic: the same input always returns the same pair, so a
    /// card does not change colour between renders.
    ///
    /// Ruling 197: when both primary colours are usable and either fail
    /// `distinguishable` or share a hue family (`sameHueFamily`), home keeps its
    /// primary colour and away switches to `awaySecondaryHex` when usable,
    /// distinguishable from home, and outside home's hue family; otherwise away
    /// switches to `partner(for: home, preferring: awayDefault)` (slate grey).
    static func pair(
        awayHex: String?,
        homeHex: String?,
        awaySecondaryHex: String? = nil
    ) -> (away: String, home: String) {
        let away = usable(awayHex)
        let home = usable(homeHex)

        switch (away, home) {
        case let (a?, h?) where distinguishable(a, h) && !sameHueFamily(a, h):
            return (a, h)                                   // rule 1
        case (_?, let h?):
            // rule 3 + Ruling 197 — two crests that collide in RGB distance or
            // hue family. Home keeps its own; away tries its own second colour,
            // else slate grey.
            if let sec = usable(awaySecondaryHex),
               distinguishable(sec, h),
               !sameHueFamily(sec, h) {
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
