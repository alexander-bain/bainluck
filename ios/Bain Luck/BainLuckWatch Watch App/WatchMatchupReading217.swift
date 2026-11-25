import Foundation
import ImageIO
#if canImport(UIKit)
import UIKit
#endif

// Direction 217, wired: what the Watch's big rectangular slot and iPhone
// double-wide Lock Screen widget draw in the Matchup look. Foundation +
// ImageIO only, so the Watch complication, iPhone/Mac widget extension, Watch
// app, and tests compile one single source of truth.

/// The extra facts the Matchup look needs, published beside the rectangular
/// reading by the Watch app. Optional in the snapshot: a snapshot written by an
/// older build has none and keeps today's three-line card.
nonisolated struct WatchMatchupFacts217: Codable, Sendable, Equatable {
    let homePrimary: String?
    let homeSecondary: String?
    let awayPrimary: String?
    let awaySecondary: String?
    /// The crests the event page serves (https only); fetched by the app into
    /// the shared container, never by the complication.
    let homeLogo: String?
    let awayLogo: String?
    /// Each side's chance before the game, rounded the way the app rounds it.
    let pregameHomePercent: Int?
    let pregameAwayPercent: Int?
    /// The game clock as the app prints it ("Q3 4:12"); nil when there is none.
    let clock: String?
    /// Optional 3-way match-winner fields (#13432: soccer Home / Draw / Away).
    let drawPercent: Int?
    let awayPercent: Int?
    let pregameDrawPercent: Int?
    let isThreeWay: Bool?

    init(homePrimary: String? = nil, homeSecondary: String? = nil, awayPrimary: String? = nil,
         awaySecondary: String? = nil, homeLogo: String? = nil, awayLogo: String? = nil,
         pregameHomePercent: Int? = nil, pregameAwayPercent: Int? = nil, clock: String? = nil,
         drawPercent: Int? = nil, awayPercent: Int? = nil, pregameDrawPercent: Int? = nil,
         isThreeWay: Bool? = nil) {
        self.homePrimary = homePrimary
        self.homeSecondary = homeSecondary
        self.awayPrimary = awayPrimary
        self.awaySecondary = awaySecondary
        self.homeLogo = homeLogo
        self.awayLogo = awayLogo
        self.pregameHomePercent = pregameHomePercent
        self.pregameAwayPercent = pregameAwayPercent
        self.clock = clock
        self.drawPercent = drawPercent
        self.awayPercent = awayPercent
        self.pregameDrawPercent = pregameDrawPercent
        self.isThreeWay = isThreeWay
    }
}

/// Crests for the Matchup slot, one PNG per team id in the Watch's shared
/// container. The app fetches; the complication only reads.
nonisolated enum WatchMatchupCrests217 {
    static let appGroup = "group.com.bainluck.watch"
    static let maximumBytes = 256 * 1024
    static let keepFor: TimeInterval = 30 * 24 * 3600
    /// #13339: bounded pixel ceiling for cached Watch crests and WidgetKit complication images.
    /// WatchKit's archival cap for accessoryRectangular on 45 mm is ~91,158 px²; keeping cached
    /// crests at <=96 px and complication thumbnails at <=64 px (@2x -> <=32 pt) stays well under it.
    static let maxPixelSize = 96
    static let complicationMaxPixelSize = 64

    static var directory: URL? {
        FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: appGroup)?
            .appendingPathComponent("MatchupCrests", isDirectory: true)
    }

    static func file(teamID: Int, in directory: URL) -> URL {
        directory.appendingPathComponent("\(teamID).png", isDirectory: false)
    }

    static func data(teamID: Int, directory: URL? = directory) -> Data? {
        guard teamID > 0, let directory,
              let data = try? Data(contentsOf: file(teamID: teamID, in: directory)),
              !data.isEmpty, data.count <= maximumBytes else { return nil }
        return data
    }

    static func pixelDimensions(of bytes: Data) -> (width: Int, height: Int)? {
        guard let source = CGImageSourceCreateWithData(bytes as CFData, nil),
              let props = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any],
              let width = props[kCGImagePropertyPixelWidth] as? Int,
              let height = props[kCGImagePropertyPixelHeight] as? Int,
              width > 0, height > 0 else { return nil }
        return (width, height)
    }

    static func isWithinPixelLimit(_ bytes: Data, maxPixelSize: Int = maxPixelSize) -> Bool {
        guard let dims = pixelDimensions(of: bytes) else { return true }
        return max(dims.width, dims.height) <= maxPixelSize
    }

    static func downsampledPNG(_ bytes: Data, maxPixelSize: Int = maxPixelSize) -> Data? {
        guard let image = complicationCGImage(from: bytes, maxPixelSize: maxPixelSize) else { return nil }
        let out = NSMutableData()
        guard let destination = CGImageDestinationCreateWithData(out, "public.png" as CFString, 1, nil) else { return nil }
        CGImageDestinationAddImage(destination, image, nil)
        guard CGImageDestinationFinalize(destination) else { return nil }
        let png = out as Data
        return png.isEmpty ? nil : png
    }

    static func prepareForCache(_ bytes: Data, maxPixelSize: Int = maxPixelSize) -> Data {
        if isWithinPixelLimit(bytes, maxPixelSize: maxPixelSize) { return bytes }
        return downsampledPNG(bytes, maxPixelSize: maxPixelSize) ?? bytes
    }

    /// Cross-platform bounded CGImage decoder used by Watch, iOS, and macOS widget surfaces.
    static func complicationCGImage(from bytes: Data, maxPixelSize: Int = complicationMaxPixelSize) -> CGImage? {
        guard let source = CGImageSourceCreateWithData(bytes as CFData, nil) else { return nil }
        let options: [CFString: Any] = [
            kCGImageSourceCreateThumbnailFromImageAlways: true,
            kCGImageSourceCreateThumbnailWithTransform: true,
            kCGImageSourceThumbnailMaxPixelSize: maxPixelSize,
            kCGImageSourceShouldCacheImmediately: true,
        ]
        return CGImageSourceCreateThumbnailAtIndex(source, 0, options as CFDictionary)
    }

    #if canImport(UIKit)
    static func complicationImage(from bytes: Data, maxPixelSize: Int = complicationMaxPixelSize) -> UIImage? {
        guard let cgImage = complicationCGImage(from: bytes, maxPixelSize: maxPixelSize) else { return nil }
        return UIImage(cgImage: cgImage, scale: 2.0, orientation: .up)
    }
    #endif

    /// Fetch each missing crest once, and downsample any oversized cached PNGs in place.
    /// Returns true when a new or shrunk crest was saved, so the caller reloads the complication.
    static func fetchMissing(_ wanted: [(teamID: Int, logo: String?)], directory: URL? = directory, now: Date = Date(),
                             fetch: @escaping @Sendable (URL) async -> Data? = download) async -> Bool {
        guard let directory else { return false }
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        var saved = false
        for (teamID, logo) in wanted where teamID > 0 {
            if let existing = data(teamID: teamID, directory: directory) {
                if !isWithinPixelLimit(existing),
                   let shrunk = downsampledPNG(existing),
                   !shrunk.isEmpty, shrunk.count <= maximumBytes,
                   (try? shrunk.write(to: file(teamID: teamID, in: directory), options: .atomic)) != nil {
                    saved = true
                }
                continue
            }
            guard let logo, let url = URL(string: logo), url.scheme == "https",
                  let bytes = await fetch(url), !bytes.isEmpty, bytes.count <= maximumBytes,
                  isImage(bytes) else { continue }
            let prepared = prepareForCache(bytes)
            guard !prepared.isEmpty, prepared.count <= maximumBytes else { continue }
            if (try? prepared.write(to: file(teamID: teamID, in: directory), options: .atomic)) != nil { saved = true }
        }
        prune(directory, now: now)
        return saved
    }

    /// PNG or JPEG signature; anything else (an error page) is not a crest.
    static func isImage(_ bytes: Data) -> Bool {
        let png: [UInt8] = [0x89, 0x50, 0x4E, 0x47]
        let jpeg: [UInt8] = [0xFF, 0xD8, 0xFF]
        return bytes.starts(with: png) || bytes.starts(with: jpeg)
    }

    static func download(_ url: URL) async -> Data? {
        var request = URLRequest(url: url, timeoutInterval: 15)
        request.cachePolicy = .returnCacheDataElseLoad
        guard let (data, response) = try? await URLSession.shared.data(for: request),
              (response as? HTTPURLResponse)?.statusCode == 200 else { return nil }
        return data
    }

    static func prune(_ directory: URL, now: Date) {
        let keys: [URLResourceKey] = [.contentModificationDateKey]
        guard let files = try? FileManager.default.contentsOfDirectory(
            at: directory, includingPropertiesForKeys: keys, options: [.skipsHiddenFiles]) else { return }
        for url in files where url.pathExtension == "png" {
            guard let stamp = try? url.resourceValues(forKeys: Set(keys)).contentModificationDate,
                  now.timeIntervalSince(stamp) > keepFor else { continue }
            try? FileManager.default.removeItem(at: url)
        }
    }
}

/// Everything the Matchup slot draws, already decided. Built from the selected
/// game by `WatchMatchupReading217.make` or `SavedLockScreenMatchupAdapter13432`
/// so the view holds no rules.
nonisolated struct WatchMatchupReading217: Equatable, Sendable {
    enum Stage: String, Equatable, Sendable { case before, during, after }

    struct Side: Equatable, Sendable {
        let abbreviation: String
        /// The team's colour as drawn on the black face, already readable (ruling 197:
        /// primary, else secondary, else the slot's neutral).
        let inkHex: String
        /// The crest, PNG bytes cached in the shared container; nil draws the
        /// abbreviation on the team's colour instead, never a blank disc.
        let crestPNG: Data?
        let score: Int?
        let isWinner: Bool
    }

    /// All three match-winner outcomes when a 3-way sport serves Home, Draw, and Away.
    struct ThreeWay: Equatable, Sendable {
        let homeLabel: String
        let homeText: String
        let drawText: String
        let awayLabel: String
        let awayText: String
    }

    let stage: Stage
    let away: Side
    let home: Side
    /// "61%". The one big number.
    let bigText: String
    /// Whose number it is, so it takes that team's colour.
    let bigIsHome: Bool
    /// The one small line under it, naming whose number it is: "LAC · Sun 5:20 PM",
    /// "BAL · Q3 4:12", "DET pregame · Final", or the clock alone when `threeWay` names all 3.
    let smallLine: String
    let accessibilityText: String
    let threeWay: ThreeWay?

    init(
        stage: Stage,
        away: Side,
        home: Side,
        bigText: String,
        bigIsHome: Bool,
        smallLine: String,
        accessibilityText: String,
        threeWay: ThreeWay? = nil
    ) {
        self.stage = stage
        self.away = away
        self.home = home
        self.bigText = bigText
        self.bigIsHome = bigIsHome
        self.smallLine = smallLine
        self.accessibilityText = accessibilityText
        self.threeWay = threeWay
    }

    var bigInkHex: String { bigIsHome ? home.inkHex : away.inkHex }

    /// The neutral a team colour falls back to when neither of its colours reads
    /// on black (ruling 197's grey fallback).
    static let neutralInkHex = "#9CA3AF"

    /// Ruling 221 on the black face (Fable, 5:17 PM Nov 16): the primary if it reads
    /// at 3:1; else the secondary if we have one and it reads; else the primary
    /// lightened just enough to read (same hue and saturation). Never grey unless
    /// the team has no usable colour at all. The same order as Builder C's
    /// `TeamTextContrast.usableOnDarkSurface` (#12839), kept here so the
    /// complication target needs no phone files.
    static func ink(primary: String?, secondary: String?) -> String {
        if let hex = primary, readable(hex) { return normalized(hex) }
        if let hex = secondary, readable(hex) { return normalized(hex) }
        if let hex = primary, let lighter = lightened(hex) { return lighter }
        return neutralInkHex
    }

    static func readable(_ hex: String) -> Bool {
        guard let l = relativeLuminance(hex) else { return false }
        return (l + 0.05) / 0.05 >= minimumRatio
    }

    private static func normalized(_ hex: String) -> String {
        "#" + hex.trimmingCharacters(in: CharacterSet(charactersIn: "#")).lowercased()
    }

    /// The primary with its HSL lightness raised in 1% steps until the quantized
    /// hex reads at 3:1 on black.
    static func lightened(_ hex: String) -> String? {
        let clean = hex.trimmingCharacters(in: CharacterSet(charactersIn: "#"))
        guard clean.count == 6, let value = UInt32(clean, radix: 16) else { return nil }
        let r = Double((value >> 16) & 0xFF) / 255, g = Double((value >> 8) & 0xFF) / 255, b = Double(value & 0xFF) / 255
        let maxC = max(r, g, b), minC = min(r, g, b), l = (maxC + minC) / 2, d = maxC - minC
        var h = 0.0, sat = 0.0
        if d > 0 {
            sat = l > 0.5 ? d / (2 - maxC - minC) : d / (maxC + minC)
            if maxC == r { h = (g - b) / d + (g < b ? 6 : 0) } else if maxC == g { h = (b - r) / d + 2 } else { h = (r - g) / d + 4 }
            h /= 6
        }
        func hue(_ p: Double, _ q: Double, _ t0: Double) -> Double {
            var t = t0
            if t < 0 { t += 1 }
            if t > 1 { t -= 1 }
            if t < 1.0 / 6 { return p + (q - p) * 6 * t }
            if t < 1.0 / 2 { return q }
            if t < 2.0 / 3 { return p + (q - p) * (2.0 / 3 - t) * 6 }
            return p
        }
        var step = l
        while step <= 1.0 {
            let q = step < 0.5 ? step * (1 + sat) : step + sat - step * sat
            let p = 2 * step - q
            let rgb = sat == 0 ? (step, step, step) : (hue(p, q, h + 1.0 / 3), hue(p, q, h), hue(p, q, h - 1.0 / 3))
            let out = String(format: "#%02x%02x%02x", Int((rgb.0 * 255).rounded()), Int((rgb.1 * 255).rounded()), Int((rgb.2 * 255).rounded()))
            if readable(out) { return out }
            step += 0.01
        }
        return nil
    }

    /// WCAG's 3:1 floor for large text, the one `TeamTextContrast` uses on the phone.
    static let minimumRatio = 3.0

    /// WCAG relative luminance of "#RRGGBB"; nil for anything else. The same
    /// formula as `TeamTextContrast.relativeLuminance`, kept here so the
    /// complication target needs no phone files.
    static func relativeLuminance(_ hex: String?) -> Double? {
        guard let hex else { return nil }
        let clean = hex.trimmingCharacters(in: CharacterSet(charactersIn: "#"))
        guard clean.count == 6, let value = UInt32(clean, radix: 16) else { return nil }
        func channel(_ shift: UInt32) -> Double {
            let c = Double((value >> shift) & 0xFF) / 255
            return c <= 0.03928 ? c / 12.92 : pow((c + 0.055) / 1.055, 2.4)
        }
        return 0.2126 * channel(16) + 0.7152 * channel(8) + 0.0722 * channel(0)
    }
}


extension WatchMatchupReading217 {
    /// A final keeps the slot for 3 hours; then the launcher stands in until the
    /// app publishes the next game.
    static let finalHoldSeconds: TimeInterval = 3 * 3600

    /// When a Matchup final gives way to the launcher; nil for anything else.
    static func finalStepAside(for snapshot: WatchComplicationSnapshot?, now: Date) -> Date? {
        guard let snapshot, snapshot.matchup != nil,
              let reading = snapshot.validatedRectangularReading(now: now),
              reading.kind == .finalResult else { return nil }
        return reading.observedAt.addingTimeInterval(finalHoldSeconds)
    }

    /// True once a Matchup final is more than 3 hours old: draw the launcher.
    static func finalHasPassed(_ snapshot: WatchComplicationSnapshot?, now: Date) -> Bool {
        guard let step = finalStepAside(for: snapshot, now: now) else { return false }
        return now >= step
    }

    /// Resolve two-way vs three-way odds for `.scheduledForecast` or `.liveForecast`.
    static func resolveOutcomePresentation(
        homePercent: Int,
        homeName: String,
        awayName: String,
        homeAbbreviation: String,
        awayAbbreviation: String,
        isThreeWay: Bool,
        drawPercent: Int?,
        awayPercent: Int?
    ) -> (bigText: String, bigIsHome: Bool, ownerAbbr: String, ownerName: String, threeWay: ThreeWay?) {
        if isThreeWay {
            if let drawPct = drawPercent, (0...100).contains(drawPct),
               let awayPct = awayPercent, (0...100).contains(awayPct) {
                let threeWay = ThreeWay(
                    homeLabel: homeAbbreviation,
                    homeText: "\(homePercent)%",
                    drawText: "\(drawPct)%",
                    awayLabel: awayAbbreviation,
                    awayText: "\(awayPct)%"
                )
                if awayPct > homePercent && awayPct >= drawPct {
                    return ("\(awayPct)%", false, awayAbbreviation, awayName, threeWay)
                }
                if drawPct > homePercent && drawPct > awayPct {
                    return ("\(drawPct)%", true, "Draw", "Draw", threeWay)
                }
                return ("\(homePercent)%", true, homeAbbreviation, homeName, threeWay)
            }
            // #5271: Draw-priced without explicit draw/away — home stands alone, never invent 1 - home.
            return ("\(homePercent)%", true, homeAbbreviation, homeName, nil)
        }
        let homeLeads = homePercent >= 50
        let pct = homeLeads ? homePercent : 100 - homePercent
        return (
            "\(pct)%",
            homeLeads,
            homeLeads ? homeAbbreviation : awayAbbreviation,
            homeLeads ? homeName : awayName,
            nil
        )
    }

    /// The Matchup reading for this snapshot, or nil when the slot should keep
    /// today's card: an older snapshot without facts, a market pin, a missing
    /// team, a game whose kickoff has passed without a new reading, an unpriced
    /// tie, or a final with no pregame chance to show.
    static func make(snapshot: WatchComplicationSnapshot?, now: Date, timeZone: TimeZone = .current,
                     crest: (Int) -> Data? = { WatchMatchupCrests217.data(teamID: $0) }) -> WatchMatchupReading217? {
        guard let snapshot, let facts = snapshot.matchup,
              let r = snapshot.validatedRectangularReading(now: now),
              let homeID = r.home, let awayID = r.away, homeID.isValid, awayID.isValid else { return nil }
        func side(_ id: WatchCompactTeamIdentity, _ primary: String?, _ secondary: String?,
                  score: Int?, winner: Bool) -> Side {
            Side(abbreviation: id.abbreviation, inkHex: ink(primary: primary, secondary: secondary),
                 crestPNG: crest(id.teamID), score: score, isWinner: winner)
        }
        let matchup = "\(r.awayName) at \(r.homeName)"
        switch r.kind {
        case .scheduledForecast:
            guard let homePct = r.homePercent, (0...100).contains(homePct) else { return nil }
            let when: String
            if let start = r.commenceTime {
                guard start > now else { return nil } // The card says "Open to update".
                when = WatchRectangularReading.upcomingStartClock(start, now: now, timeZone: timeZone)
            } else {
                when = "Pregame"
            }
            let out = resolveOutcomePresentation(
                homePercent: homePct,
                homeName: r.homeName,
                awayName: r.awayName,
                homeAbbreviation: homeID.abbreviation,
                awayAbbreviation: awayID.abbreviation,
                isThreeWay: facts.isThreeWay == true,
                drawPercent: facts.drawPercent,
                awayPercent: facts.awayPercent
            )
            let smallLine = out.threeWay == nil ? "\(out.ownerAbbr) · \(when)" : when
            let speech: String = {
                if let tw = out.threeWay {
                    return "\(matchup). \(r.homeName) \(tw.homeText), Draw \(tw.drawText), \(r.awayName) \(tw.awayText). \(when). Open your game in Bain Luck."
                }
                return "\(matchup). \(out.ownerName) \(out.bigText) to win. \(when). Open your game in Bain Luck."
            }()
            return WatchMatchupReading217(
                stage: .before,
                away: side(awayID, facts.awayPrimary, facts.awaySecondary, score: nil, winner: false),
                home: side(homeID, facts.homePrimary, facts.homeSecondary, score: nil, winner: false),
                bigText: out.bigText, bigIsHome: out.bigIsHome, smallLine: smallLine,
                accessibilityText: speech, threeWay: out.threeWay)
        case .liveForecast:
            guard let homePct = r.homePercent, (0...100).contains(homePct) else { return nil }
            let when: String
            if r.isAgedLive(at: now) {
                when = "As of \(WatchRectangularReading.asOfClock(r.observedAt, timeZone: timeZone))"
            } else if let clock = facts.clock?.trimmingCharacters(in: .whitespacesAndNewlines), !clock.isEmpty {
                when = clock
            } else {
                when = "Live"
            }
            let out = resolveOutcomePresentation(
                homePercent: homePct,
                homeName: r.homeName,
                awayName: r.awayName,
                homeAbbreviation: homeID.abbreviation,
                awayAbbreviation: awayID.abbreviation,
                isThreeWay: facts.isThreeWay == true,
                drawPercent: facts.drawPercent,
                awayPercent: facts.awayPercent
            )
            let smallLine = out.threeWay == nil ? "\(out.ownerAbbr) · \(when)" : when
            let score: String = {
                guard let a = r.awayScore, let h = r.homeScore else { return "" }
                return " \(r.awayName) \(a), \(r.homeName) \(h)."
            }()
            let speech: String = {
                if let tw = out.threeWay {
                    return "\(matchup).\(score) \(r.homeName) \(tw.homeText), Draw \(tw.drawText), \(r.awayName) \(tw.awayText). \(when). Open your game in Bain Luck."
                }
                return "\(matchup).\(score) \(out.ownerName) \(out.bigText) to win now. \(when). Open your game in Bain Luck."
            }()
            return WatchMatchupReading217(
                stage: .during,
                away: side(awayID, facts.awayPrimary, facts.awaySecondary, score: r.awayScore, winner: false),
                home: side(homeID, facts.homePrimary, facts.homeSecondary, score: r.homeScore, winner: false),
                bigText: out.bigText, bigIsHome: out.bigIsHome, smallLine: smallLine,
                accessibilityText: speech, threeWay: out.threeWay)
        case .finalResult:
            guard let h = r.homeScore, let a = r.awayScore,
                  now.timeIntervalSince(r.observedAt) < finalHoldSeconds else { return nil }
            if h == a {
                guard let drawPre = facts.pregameDrawPercent, (0...100).contains(drawPre) else { return nil }
                return WatchMatchupReading217(
                    stage: .after,
                    away: side(awayID, facts.awayPrimary, facts.awaySecondary, score: a, winner: false),
                    home: side(homeID, facts.homePrimary, facts.homeSecondary, score: h, winner: false),
                    bigText: "\(drawPre)%", bigIsHome: true, smallLine: "Draw pregame · Final",
                    accessibilityText: "Final. \(r.awayName) \(a), \(r.homeName) \(h). Draw had \(drawPre)% before the game. Open your game in Bain Luck.")
            }
            let homeWon = h > a
            guard let pct = homeWon ? facts.pregameHomePercent : facts.pregameAwayPercent,
                  (0...100).contains(pct) else { return nil }
            let abbr = homeWon ? homeID.abbreviation : awayID.abbreviation
            let name = homeWon ? r.homeName : r.awayName
            let loser = homeWon ? r.awayName : r.homeName
            return WatchMatchupReading217(
                stage: .after,
                away: side(awayID, facts.awayPrimary, facts.awaySecondary, score: a, winner: !homeWon),
                home: side(homeID, facts.homePrimary, facts.homeSecondary, score: h, winner: homeWon),
                bigText: "\(pct)%", bigIsHome: homeWon, smallLine: "\(abbr) pregame · Final",
                accessibilityText: "Final. \(name) \(max(h, a)), \(loser) \(min(h, a)). \(name) had \(pct)% before the game. Open your game in Bain Luck.")
        case .futureForecast:
            return nil
        }
    }

    /// Minimal timeline dates for a Matchup look so WidgetKit only archives the
    /// entries where the Matchup face actually changes text or hands back.
    static func timelineDates(
        for snapshot: WatchComplicationSnapshot?,
        now: Date,
        timeZone: TimeZone = .current
    ) -> [Date]? {
        guard now.timeIntervalSinceReferenceDate.isFinite,
              make(snapshot: snapshot, now: now, timeZone: timeZone) != nil,
              let snapshot,
              let r = snapshot.validatedRectangularReading(now: now) else { return nil }
        var dates = [now]
        switch r.kind {
        case .scheduledForecast:
            if let start = r.commenceTime, start > now {
                var cal = Calendar(identifier: .gregorian)
                cal.timeZone = timeZone
                if !cal.isDate(start, inSameDayAs: now),
                   let tomorrow = cal.date(byAdding: .day, value: 1, to: cal.startOfDay(for: now)),
                   tomorrow > now, tomorrow < start {
                    dates.append(tomorrow)
                }
                let startDay = cal.startOfDay(for: start)
                if startDay > now, startDay < start {
                    dates.append(startDay)
                }
                dates.append(start)
            }
        case .liveForecast:
            let ageSwitch = r.observedAt.addingTimeInterval(WatchRectangularReading.liveAgeThresholdSeconds + 1)
            if ageSwitch > now {
                dates.append(ageSwitch)
            }
        case .finalResult:
            if let step = finalStepAside(for: snapshot, now: now), step > now {
                dates.append(step)
            }
        case .futureForecast:
            return nil
        }
        return Array(Set(dates)).sorted()
    }
}
