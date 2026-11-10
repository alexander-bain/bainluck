import CryptoKit
import Foundation
import ImageIO

/// #12466 — what the saved widget draws a game WITH: each side's colours and
/// crest, and the colour rules for the surface they land on. What the widget
/// SAYS stays the reading's (`SavedWidgetReading10875`); nothing here prints a
/// number or a word.
///
/// The colour rules are the app's own, compiled in rather than restated:
/// - On a light surface a bar or stripe resolves exactly as every white card in
///   the app does (`TeamTextContrast.cardColorHexes`): a colour under WCAG's
///   3:1 against the surface is absent, then `ProbabilityBarPalette.pair`
///   keeps the two sides apart.
/// - On a dark surface, which no app card has, the same two rules run against
///   the dark surface, with one step first: a primary colour that fails the
///   floor gives way to the team's own secondary before the slot default, so
///   a navy-and-red team stays red on a dark Home Screen instead of turning
///   slate.
/// - A full-bleed fill IS the surface, so it keeps the team's primary colour
///   (sides kept apart by the palette) and the text on it takes whichever ink
///   reads better.
struct SavedWidgetArt12466: Equatable, Sendable {
    struct Side: Equatable, Sendable {
        let short: String
        let primaryHex: String?
        let secondaryHex: String?
        /// Only an https crest is ever fetched.
        let logoURL: URL?
    }

    let away: Side
    let home: Side
    /// A live game's score, for a look that gives each side its own line. Only
    /// while live and only with both sides held (`EventState`'s partial-line
    /// rule): a finished game's score is already each row's figure.
    var scores: Scores? = nil

    struct Scores: Equatable, Sendable {
        let away: Int
        let home: Int
    }

    static func game(_ event: SavedWidgetEventDetail10875) -> SavedWidgetArt12466 {
        let short = TeamShortName.abbreviationPair(
            away: event.awayTeam, home: event.homeTeam,
            awayServed: event.awayTeamData?.abbreviation, homeServed: event.homeTeamData?.abbreviation)
        func side(_ data: SavedWidgetTeamData10875?, short: String) -> Side {
            let logo = data?.logoSmall.flatMap { URL(string: $0) }
            return Side(short: short, primaryHex: data?.primaryColor, secondaryHex: data?.secondaryColor,
                        logoURL: logo?.scheme == "https" ? logo : nil)
        }
        var scores: Scores?
        if event.status == "live", let away = event.awayScore, let home = event.homeScore {
            scores = Scores(away: away, home: home)
        }
        return SavedWidgetArt12466(away: side(event.awayTeamData, short: short.away),
                                   home: side(event.homeTeamData, short: short.home), scores: scores)
    }

    // MARK: - Surfaces

    /// WCAG relative luminance of the two backgrounds a bar is drawn on: the
    /// widget's light and dark container fills.
    static let lightSurfaceLuminance = 1.0
    static let darkSurfaceLuminance = 0.012

    /// The app's ink, `#111827`, for text on a light fill.
    static let inkHex = "#111827"

    // MARK: - Colours

    /// A bar's or stripe's two colours on a surface, away first.
    func barHexes(surfaceLuminance: Double) -> (away: String, home: String) {
        if surfaceLuminance >= 0.5 {
            return TeamTextContrast.cardColorHexes(awayHex: away.primaryHex, homeHex: home.primaryHex)
        }
        func readable(_ side: Side) -> String? {
            [side.primaryHex, side.secondaryHex].lazy.compactMap { $0 }.first {
                Self.contrast($0, againstLuminance: surfaceLuminance).map { $0 >= TeamTextContrast.minimumRatio } ?? false
            }
        }
        return ProbabilityBarPalette.pair(awayHex: readable(away), homeHex: readable(home))
    }

    /// Two full-bleed fills, away first: each team's primary colour, kept
    /// apart by the palette.
    func fillHexes() -> (away: String, home: String) {
        ProbabilityBarPalette.pair(awayHex: away.primaryHex, homeHex: home.primaryHex)
    }

    /// The text colour for a fill: white or the app's ink, whichever has more
    /// contrast. An unreadable colour is not a colour: white on the default.
    static func ink(on hex: String) -> String {
        guard let onWhite = contrast(hex, againstLuminance: 1.0),
              let onInk = contrast(hex, againstLuminance: TeamTextContrast.relativeLuminance(inkHex) ?? 0)
        else { return "#FFFFFF" }
        return onInk > onWhite ? inkHex : "#FFFFFF"
    }

    /// `hex` mixed toward black by `amount` (0…1), for a fill's darker end.
    static func shaded(_ hex: String, by amount: Double) -> String {
        guard let rgb = ProbabilityBarPalette.rgb(hex) else { return hex }
        let keep = 1 - min(max(amount, 0), 1)
        func channel(_ v: Int) -> Int { Int((Double(v) * keep).rounded()) }
        return String(format: "#%02X%02X%02X", channel(rgb.r), channel(rgb.g), channel(rgb.b))
    }

    /// WCAG contrast of `hex` against a background of luminance `background`.
    static func contrast(_ hex: String, againstLuminance background: Double) -> Double? {
        guard let l = TeamTextContrast.relativeLuminance(hex) else { return nil }
        return (max(l, background) + 0.05) / (min(l, background) + 0.05)
    }

    // MARK: - The bar

    /// Segment widths for a chance bar `total` points wide, away first. The
    /// reading's integers decide the split. On a draw-priced game the first
    /// segment is the rest ("not the home team"), drawn without the away
    /// team's colour. A side with any chance keeps at least `minimum` points so
    /// it stays visible, and the two segments plus the gap always fill `total`.
    static func barWidths(_ shares: SavedWidgetReading10875.Shares, total: Double, gap: Double = 2,
                          minimum: Double = 3) -> (first: Double, second: Double) {
        let usable = max(total - gap, 0)
        let raw: Double
        switch shares {
        case .game(let away?, let home) where away + home > 0:
            raw = home / (away + home)
        case .game(_, let home):
            raw = home
        case .outcome(let chance):
            raw = chance
        }
        let share = raw.isFinite ? min(max(raw, 0), 1) : 0
        var second = usable * share
        if share > 0 { second = max(second, minimum) }
        if share < 1 { second = min(second, usable - minimum) }
        second = min(max(second, 0), usable)
        return (usable - second, second)
    }
}

/// #12466 — team crests for the saved widget. A widget can't load an image
/// while it draws, so the timeline fetches each crest, shrinks it to the
/// largest size a look draws, and keeps it on disk for 30 days. A crest that
/// can't be fetched is drawn as the team's short name on its colour; a stale
/// crest beats none.
nonisolated enum SavedWidgetLogos12466 {
    struct Pair: Equatable, Sendable {
        var away: Data? = nil
        var home: Data? = nil
    }

    /// 48 pt at 3x: the largest crest any look draws.
    static let maxPixelSize = 144
    static let freshFor: TimeInterval = 30 * 24 * 60 * 60
    static let maxDownloadBytes = 3_000_000

    static let session: URLSession = {
        let config = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForRequest = 8
        config.timeoutIntervalForResource = 12
        return URLSession(configuration: config)
    }()

    /// The extension's own caches folder.
    static var directory: URL? {
        FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask).first?
            .appendingPathComponent("SavedWidgetLogos12466", isDirectory: true)
    }

    static func load(away: URL?, home: URL?, now: Date = Date(), directory: URL? = directory,
                     fetch: @escaping @Sendable (URL) async -> Data? = { await download($0) }) async -> Pair {
        async let a = crest(away, now: now, directory: directory, fetch: fetch)
        async let h = crest(home, now: now, directory: directory, fetch: fetch)
        return Pair(away: await a, home: await h)
    }

    static func crest(_ url: URL?, now: Date, directory: URL?,
                      fetch: @Sendable (URL) async -> Data?) async -> Data? {
        guard let url, url.scheme == "https" else { return nil }
        let file = directory.map { cacheFile(for: url, in: $0) }
        let held = file.flatMap { try? Data(contentsOf: $0) }
        // A stamp from the future (the clock moved back) is an age nobody knows: fetch again.
        if let file, let held, let stamp = modified(file),
           case let age = now.timeIntervalSince(stamp), age >= 0, age < freshFor {
            return held
        }
        guard let raw = await fetch(url), let small = thumbnail(raw) else { return held }
        if let file, let directory {
            try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            try? small.write(to: file, options: .atomic)
        }
        return small
    }

    static func download(_ url: URL) async -> Data? {
        guard let (data, response) = try? await session.data(from: url),
              let http = response as? HTTPURLResponse, http.statusCode == 200,
              data.count <= maxDownloadBytes else { return nil }
        return data
    }

    /// A PNG no larger than `maxPixelSize` on its long side, or nil when the
    /// bytes aren't an image.
    static func thumbnail(_ data: Data) -> Data? {
        guard let source = CGImageSourceCreateWithData(data as CFData, nil) else { return nil }
        let options: [CFString: Any] = [
            kCGImageSourceCreateThumbnailFromImageAlways: true,
            kCGImageSourceCreateThumbnailWithTransform: true,
            kCGImageSourceThumbnailMaxPixelSize: maxPixelSize,
            kCGImageSourceShouldCacheImmediately: true,
        ]
        guard let image = CGImageSourceCreateThumbnailAtIndex(source, 0, options as CFDictionary) else { return nil }
        let out = NSMutableData()
        guard let destination = CGImageDestinationCreateWithData(out, "public.png" as CFString, 1, nil)
        else { return nil }
        CGImageDestinationAddImage(destination, image, nil)
        guard CGImageDestinationFinalize(destination) else { return nil }
        return out as Data
    }

    static func image(_ data: Data?) -> CGImage? {
        guard let data, let source = CGImageSourceCreateWithData(data as CFData, nil) else { return nil }
        return CGImageSourceCreateImageAtIndex(source, 0, nil)
    }

    static func cacheFile(for url: URL, in directory: URL) -> URL {
        let digest = SHA256.hash(data: Data(url.absoluteString.utf8)).map { String(format: "%02x", $0) }.joined()
        return directory.appendingPathComponent(digest).appendingPathExtension("png")
    }

    private static func modified(_ file: URL) -> Date? {
        (try? FileManager.default.attributesOfItem(atPath: file.path))?[.modificationDate] as? Date
    }
}
