import SwiftUI

// MARK: - Category Gradients
//
// The app-wide card palette, keyed by `llm_sport_category`. Byte-for-byte the
// web's `CATEGORY_GRADIENTS` (`frontend/components/discover/constants.ts`), so a
// card is the same colour in the browser and in the app.
//
// Read by every Discover card kind (futures, event, concept, tournament) and by
// the futures detail hero. It lives here, on its own, rather than at the top of
// whichever card happened to declare it first — `FuturesDetailView` used to keep
// a `private` second copy of this exact table and that is how #4111 happened
// (see `FuturesHero` below).

let sportCategoryGradients: [String: (Color, Color)] = [
    "basketball": (Color(red: 0.49, green: 0.18, blue: 0.07), Color(red: 0.76, green: 0.25, blue: 0.05)),
    "football": (Color(red: 0.08, green: 0.33, blue: 0.18), Color(red: 0.08, green: 0.50, blue: 0.24)),
    "baseball": (Color(red: 0.50, green: 0.11, blue: 0.11), Color(red: 0.73, green: 0.11, blue: 0.11)),
    "hockey": (Color(red: 0.12, green: 0.23, blue: 0.37), Color(red: 0.15, green: 0.39, blue: 0.92)),
    "soccer": (Color(red: 0.02, green: 0.31, blue: 0.23), Color(red: 0.02, green: 0.60, blue: 0.40)),
    "golf": (Color(red: 0.08, green: 0.33, blue: 0.18), Color(red: 0.09, green: 0.40, blue: 0.20)),
    "mma": (Color(red: 0.27, green: 0.04, blue: 0.04), Color(red: 0.60, green: 0.11, blue: 0.11)),
    "economics": (Color(red: 0.18, green: 0.06, blue: 0.40), Color(red: 0.49, green: 0.23, blue: 0.93)),
    "politics": (Color(red: 0.12, green: 0.11, blue: 0.29), Color(red: 0.26, green: 0.22, blue: 0.79)),
    "tech": (Color(red: 0.03, green: 0.20, blue: 0.27), Color(red: 0.03, green: 0.57, blue: 0.70)),
    "culture": (Color(red: 0.51, green: 0.09, blue: 0.26), Color(red: 0.86, green: 0.15, blue: 0.47)),
    "weather": (Color(red: 0.05, green: 0.29, blue: 0.43), Color(red: 0.01, green: 0.52, blue: 0.78)),
    "entertainment": (Color(red: 0.44, green: 0.10, blue: 0.46), Color(red: 0.75, green: 0.15, blue: 0.83)),
    "cricket": (Color(red: 0.07, green: 0.31, blue: 0.29), Color(red: 0.08, green: 0.72, blue: 0.65)),
    "olympics": (Color(red: 0.47, green: 0.21, blue: 0.06), Color(red: 0.85, green: 0.47, blue: 0.02)),
]

let sportDefaultGradient: (Color, Color) = (Color(red: 0.06, green: 0.09, blue: 0.16), Color(red: 0.12, green: 0.16, blue: 0.24))

// MARK: - Futures Hero

/// What a futures hero draws behind its white overlay text (#4111).
///
/// 🔴 THIS EXISTS BECAUSE THE DECISION WAS WRITTEN TWICE AND THE TWO COPIES
/// DISAGREED IN PUBLIC. `FuturesDetailView.heroBackground` and
/// `NativeFuturesDiscoverCard.heroBackground` were the same view — same palette
/// (duplicated verbatim), same 🍀 emoji ladder (duplicated verbatim), same
/// bottom-leading white text — except the detail hero checked `imageUrl` first
/// and the Discover card never did. So `image_url` arrived on 29 of 38 futures
/// cards in `DiscoverFeedProdFixture` and 11 of 12 on production page one, the
/// detail page drew every one of them, and Discover drew a flat gradient:
/// Alex's "cards are colourless with no images" (#4111).
///
/// Two consumers, two verdicts — gotcha #129, and the same reasoning that
/// collapsed the two Discover classifiers into `DiscoverCategory`. The copies
/// are gone rather than tested against each other: there is one hero view now,
/// so a Discover card that silently stops drawing its photo is not something
/// this file can express.
///
/// The decision is split out of the view as a pure value so it can be graded on
/// the real payload without rendering anything — `DiscoverFuturesHeroArtTests`
/// runs it over the production fixture and asserts BOTH arms are populated.
enum FuturesHero {

    /// The shortest the Discover card's hero may be drawn — a FLOOR, not a
    /// height (#7074).
    ///
    /// It was `heroBackground.frame(height: 170)`, a fixed-height sibling of an
    /// overlay that is free to be taller, which is how a card came to draw its
    /// own pills off the top of its own photograph. Read by
    /// `NativeFuturesDiscoverCard` as a `minHeight`, so the backdrop is exactly
    /// as tall as whatever the overlay needs and never shorter than the 170 the
    /// card has always drawn. Named here rather than inline because the number
    /// is the card's shape and a test that pins it should not have to read a
    /// `@ViewBuilder` to find it.
    static let discoverCardMinimumHeight: CGFloat = 170

    /// The same floor for the futures detail page's hero (#7074, second
    /// instance). It was `frame(height: 220)` in the identical two-heights
    /// shape, with MORE overlay than the card has — the pill row can carry a
    /// RESOLVED badge and the block under the numeral a winner row. A larger
    /// floor makes the spill rarer, never impossible.
    static let detailPageMinimumHeight: CGFloat = 220

    /// The hero's backdrop for one card.
    enum Background: Equatable {
        /// A photograph from the market's `image_url`.
        case photo(URL)
        /// The category gradient plus its watermark emoji — the honest fallback
        /// when there is no usable photo.
        case category
    }

    /// Resolve a market's `image_url` to what the hero should actually draw.
    ///
    /// Blank and whitespace-only strings are `.category`, not an `AsyncImage`
    /// that fails silently: an empty string is a value the serializer emits, not
    /// a photograph, and a hero that spends a request finding that out shows the
    /// reader a blank box while it waits.
    ///
    /// The scheme test is deliberate. `URL(string:)` is lenient — it accepts
    /// plenty that is not fetchable, and on newer SDKs it will hand back a URL
    /// with no scheme at all rather than nil — so "is this non-nil?" is not the
    /// same question as "is this a photo we can load". Only `http`/`https` are
    /// photos; every `image_url` the feed has ever served is `https`.
    static func background(imageURL: String?) -> Background {
        guard let raw = imageURL?.trimmingCharacters(in: .whitespacesAndNewlines),
              !raw.isEmpty,
              let url = URL(string: raw),
              let scheme = url.scheme?.lowercased(),
              scheme == "http" || scheme == "https"
        else {
            return .category
        }
        return .photo(url)
    }

    /// The category gradient, defaulting to slate for a category with no entry.
    static func gradient(for category: String?) -> (Color, Color) {
        sportCategoryGradients[category?.lowercased() ?? ""] ?? sportDefaultGradient
    }

    /// The watermark emoji for a card with no photo. Drawn at 0.10 opacity and
    /// never read aloud, so it is deliberately not ramped for Dynamic Type
    /// (#1772); the census guard exempts exactly that line.
    static func emoji(for category: String?) -> String {
        switch category?.lowercased() {
        case "politics": return "🏛"
        case "geopolitics": return "🌍"
        case "economics": return "📈"
        case "tech": return "💻"
        case "entertainment": return "🎬"
        case "culture": return "🎭"
        case "weather": return "🌤"
        case "health": return "🏥"
        default: return "🍀"
        }
    }
}

// MARK: - Event Hero

/// The Discover GAME card's hero — the third instance of #7074's shape, found
/// by #2095's card-type acceptance pass.
///
/// 🔴 #7074 FIXED TWO HEROES AND THERE WERE THREE. `NativeEventDiscoverCard`
/// wrapped its gradient and its overlay in a `ZStack { … }.frame(height: 160)`
/// — the same defect wearing different clothes. Because the height is on the
/// ZStack rather than on the backdrop alone, the overflow is not spilled onto
/// the card's white body (the futures card's symptom) but CLIPPED by the
/// `clipShape` that follows it, which is worse: the content does not look
/// misplaced, it looks absent.
///
/// MEASURED on master `5e9cc2d5f`, iPhone 17 Pro, anonymous feed, the live card
/// "Miami Marlins @ Chicago Cubs":
///
/// | Dynamic Type | hero BEFORE | AFTER | chip's gap below the hero's top edge |
/// |---|---|---|---|
/// | `large` (default) | 160.0pt | 164.0pt | 12.0pt → **14.0pt** |
/// | `extra-extra-extra-large` | 160.0pt | 185.7pt | 1.3pt → **14.0pt** |
/// | `accessibility-extra-extra-extra-large` | 160.0pt | ≥308.7pt | **chip absent** → **14.0pt** |
///
/// The hero measured 160.0pt at EVERY size, which is the finding: it could not
/// grow, so at the largest accessibility size the `MLB` chip and the `• LIVE`
/// badge were clipped away entirely and the two scores lost their bottoms.
/// Note the default row — the card was already 4pt over its own pin at the
/// DEFAULT text size, so the chip was 2pt short of its padding on every phone.
/// Artifacts: `artifacts/native-301/BEFORE-*` and their `AFTER-*` twins.
///
/// Its sibling card kinds were photographed in the same pass and are well:
/// the futures card (#2095's own `GEOPOLITICS` specimen) and the tournament
/// card both draw their chips whole at the largest size, because #7074 gave
/// one a floor and the other never had a fixed height.
enum EventHero {

    /// The shortest the Discover game card's hero may be drawn — a FLOOR, not a
    /// height. 160 is the value it was pinned at, so a card whose content fits
    /// draws exactly the hero it has always drawn.
    static let discoverCardMinimumHeight: CGFloat = 160
}

/// The one futures hero backdrop, shared by the Discover card and the detail page.
///
/// Layering follows the web (`FuturesCard.tsx`): the gradient is the base layer
/// **always**, so it is the placeholder behind a photo that has not arrived yet
/// rather than a blank box, and the photo is an overlay on top of it. The
/// watermark emoji is drawn only when there is no photo — a 96pt 🍀 floating
/// over a photograph is not a fallback, it is litter.
struct FuturesHeroBackground: View {
    let imageURL: String?
    let category: String?

    var body: some View {
        let gradient = FuturesHero.gradient(for: category)
        return LinearGradient(
            colors: [gradient.0, gradient.1],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
        .overlay(backdrop)
        .clipped()
    }

    @ViewBuilder
    private var backdrop: some View {
        switch FuturesHero.background(imageURL: imageURL) {
        case .photo(let url):
            AsyncImage(url: url) { phase in
                switch phase {
                case .success(let image):
                    image
                        .resizable()
                        .scaledToFill()
                        // The scrim. Both heroes carry white text bottom-leading
                        // — a 52pt numeral on Discover, the market name on the
                        // detail page — and a Pexels photo is as likely to be
                        // bright as dark. Darkening downward keeps that text
                        // legible on every photo instead of on most of them.
                        .overlay(
                            LinearGradient(
                                colors: [.black.opacity(0.08), .black.opacity(0.78)],
                                startPoint: .top,
                                endPoint: .bottom
                            )
                        )
                        .clipped()
                default:
                    // Loading and failed both fall through to the gradient
                    // underneath, which is already drawn.
                    Color.clear
                }
            }
        case .category:
            Text(FuturesHero.emoji(for: category))
                .font(.system(size: 96))
                .opacity(0.10)
        }
    }
}

// MARK: - #12840 Grouped Card Banner, Crest & Monogram Fallback

enum DiscoverBundleVisual12840 {
    static let bannerHeight: CGFloat = 144

    static let blockedPexelsPhotoIDs: Set<String> = [
        "8919548", "6289047", "6289061", "31825810", "3970331",
        "9321371", "8728168", "11460276", "12786869", "6326317",
        "32417524", "8850837", "8850633", "8044086", "18326060",
    ]

    static let monogramPalette: [(bg: String, accent: String)] = [
        ("#1e3a8a", "#2563eb"), // Royal cobalt
        ("#312e81", "#4f46e5"), // Civic indigo
        ("#0f766e", "#14b8a6"), // Editorial teal
        ("#7c2d12", "#ea580c"), // Burnt sienna
        ("#581c87", "#9333ea"), // Deep plum
        ("#831843", "#db2777"), // Crimson rose
        ("#14532d", "#16a34a"), // Forest emerald
        ("#7f1d1d", "#dc2626"), // Arena crimson
        ("#1e293b", "#475569"), // Cinema slate
        ("#78350f", "#d97706"), // Warm amber
    ]

    struct ResolvedBanner: Equatable, Sendable {
        let primaryURL: URL?
        let presentation: String?
        let fallbackCrestURL: URL?
        let monogram: DiscoverImageMonogram
    }

    /// Mirrors `BundleHeader.tsx`: music / Grammys / album / song / Spotify / Billboard
    /// bundles wear `🎵` instead of `🎬`.
    static func eyebrowEmoji(title: String, category: String?) -> String {
        if title.range(
            of: #"\b(?:grammys?|latin\s+grammys?|album|song\s+of\s+the\s+year|spotify|billboard)\b"#,
            options: [.regularExpression, .caseInsensitive]
        ) != nil {
            return "🎵"
        }
        return FuturesHero.emoji(for: category)
    }

    static func validBannerURL(_ raw: String?) -> URL? {
        guard let trimmed = raw?.trimmingCharacters(in: .whitespacesAndNewlines),
              !trimmed.isEmpty,
              let url = URL(string: trimmed),
              let scheme = url.scheme?.lowercased(),
              scheme == "http" || scheme == "https"
        else { return nil }

        if let host = url.host?.lowercased(),
           host == "images.pexels.com" || host.hasSuffix(".pexels.com"),
           let match = trimmed.range(of: #"/photos/(\d+)/"#, options: .regularExpression) {
            let digits = trimmed[match].replacingOccurrences(of: "/photos/", with: "").replacingOccurrences(of: "/", with: "")
            if blockedPexelsPhotoIDs.contains(digits) {
                return nil
            }
        }
        return url
    }

    /// Mirrors `discoverEntityVisual.ts` `computeDiscoverInitials` & `hashPalette`.
    static func deterministicMonogram(
        title: String,
        sharedQuestion: String?,
        category: String?,
        servedMonogram: DiscoverImageMonogram? = nil
    ) -> DiscoverImageMonogram {
        if let served = servedMonogram, !served.initials.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return served
        }

        let cleanTitle = title.trimmingCharacters(in: .whitespacesAndNewlines)
        let label = cleanTitle.isEmpty ? (sharedQuestion?.trimmingCharacters(in: .whitespacesAndNewlines) ?? "Bain Luck") : cleanTitle
        let combined = "\(title) \(sharedQuestion ?? "")"

        let kind: String = {
            if combined.range(of: #"\b(?:grammys?|latin\s+grammys?|album|song|spotify|billboard)\b"#, options: [.regularExpression, .caseInsensitive]) != nil {
                return "song"
            }
            if combined.range(of: #"\b(?:oscars?|academy\s+awards?|emmys?|golden\s+globes?|bafta|best\s+picture|rotten\s+tomatoes|box\s+office|netflix)\b"#, options: [.regularExpression, .caseInsensitive]) != nil {
                return "film"
            }
            let cat = (category ?? "").lowercased()
            if ["basketball", "football", "baseball", "hockey", "soccer"].contains(cat) {
                return "team"
            }
            return "topic"
        }()

        let initials = computeInitials(label: label)
        let colors = hashPalette(label: label, kind: kind)
        return DiscoverImageMonogram(
            initials: initials,
            label: label,
            kind: kind,
            bgHex: colors.bg,
            accentHex: colors.accent
        )
    }

    static func computeInitials(label: String) -> String {
        let raw = label.trimmingCharacters(in: .whitespacesAndNewlines)
        if raw.isEmpty { return "BL" }
        if let tickerRange = raw.range(of: #"\(([A-Z]{2,5})\)"#, options: .regularExpression) {
            let inner = String(raw[tickerRange].dropFirst().dropLast())
            return inner.uppercased()
        }
        if raw.range(of: #"\bkimi\b.*\bmoonshot\b"#, options: [.regularExpression, .caseInsensitive]) != nil {
            return "KM"
        }
        let cleaned = raw
            .replacingOccurrences(of: #"\([^)]*\)"#, with: " ", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let abbr = TeamShortName.abbreviation(cleaned.isEmpty ? raw : cleaned)
        return abbr.isEmpty ? "BL" : abbr
    }

    static func hashPalette(label: String, kind: String) -> (bg: String, accent: String) {
        if kind == "film" { return ("#1e293b", "#475569") }
        if kind == "song" { return ("#581c87", "#9333ea") }
        let norm = (label.isEmpty ? kind : label).lowercased().trimmingCharacters(in: .whitespacesAndNewlines)
        var h: UInt32 = 2_166_136_261
        for unit in norm.utf16 {
            h ^= UInt32(unit)
            h = h &* 16_777_619
        }
        let signed = Int32(bitPattern: h)
        let idx = Int(signed == Int32.min ? UInt32(Int32.max) + 1 : UInt32(abs(signed))) % monogramPalette.count
        return monogramPalette[idx]
    }

    static func resolve(
        title: String,
        sharedQuestion: String?,
        category: String?,
        bundleImageUrl: String?,
        bundlePresentation: String?,
        bundleMonogram: DiscoverImageMonogram?,
        items: [FeedItem]
    ) -> ResolvedBanner {
        let primaryFutures = items.first?.futures
        let primaryURL = validBannerURL(bundleImageUrl) ?? validBannerURL(primaryFutures?.imageUrl)
        let presentation = (bundlePresentation?.trimmingCharacters(in: .whitespacesAndNewlines)).flatMap { $0.isEmpty ? nil : $0 }
            ?? (primaryFutures?.imagePresentation?.trimmingCharacters(in: .whitespacesAndNewlines)).flatMap { $0.isEmpty ? nil : $0 }

        let fallbackCrestURL: URL? = {
            for item in items {
                if let ev = item.event {
                    if let u = validBannerURL(ev.homeTeamData?.logoSmall ?? ev.awayTeamData?.logoSmall) {
                        return u
                    }
                }
                if let fut = item.futures,
                   fut.imagePresentation == "logo",
                   let u = validBannerURL(fut.imageUrl),
                   u != primaryURL {
                    return u
                }
            }
            let cat = (category ?? "").lowercased()
            if ["basketball", "football", "baseball", "hockey", "soccer"].contains(cat) {
                let candidates = [title, primaryFutures?.topOutcomes?.first?.name].compactMap { $0 }
                for name in candidates {
                    if let espn = espnTeamLogoURL(for: name), let u = URL(string: espn), u != primaryURL {
                        return u
                    }
                }
            }
            return nil
        }()

        let monogram = deterministicMonogram(
            title: title,
            sharedQuestion: sharedQuestion,
            category: category,
            servedMonogram: bundleMonogram ?? primaryFutures?.imageMonogram
        )

        return ResolvedBanner(
            primaryURL: primaryURL,
            presentation: presentation,
            fallbackCrestURL: fallbackCrestURL,
            monogram: monogram
        )
    }
}

struct DiscoverBundleArtContext12840: Equatable, Sendable {
    var imageUrl: String? = nil
    var imagePresentation: String? = nil
    var imageMonogram: DiscoverImageMonogram? = nil
}

private struct DiscoverBundleArtKey12840: EnvironmentKey {
    static let defaultValue = DiscoverBundleArtContext12840()
}

extension EnvironmentValues {
    var discoverGroupBundleArt12840: DiscoverBundleArtContext12840 {
        get { self[DiscoverBundleArtKey12840.self] }
        set { self[DiscoverBundleArtKey12840.self] = newValue }
    }
}

struct DiscoverGroupBannerView12840: View {
    let resolved: DiscoverBundleVisual12840.ResolvedBanner
    let category: String?
    var preloadedImages: [URL: Image] = [:]

    @Environment(\.colorScheme) private var colorScheme

    private var dividerColor: Color {
        colorScheme == .dark ? Color.white.opacity(0.12) : DS.border
    }

    var body: some View {
        let catGradient = FuturesHero.gradient(for: category)
        ZStack {
            if let url = resolved.primaryURL {
                primaryBanner(url: url, catGradient: catGradient)
            } else if let crestURL = resolved.fallbackCrestURL {
                crestBanner(url: crestURL, catGradient: catGradient)
            } else {
                monogramBanner(resolved.monogram)
            }
        }
        .frame(maxWidth: .infinity)
        .frame(height: DiscoverBundleVisual12840.bannerHeight)
        .clipped()
        .overlay(alignment: .bottom) {
            Rectangle()
                .fill(dividerColor)
                .frame(height: 0.75)
        }
        .accessibilityHidden(true)
    }

    @ViewBuilder
    private func primaryBanner(url: URL, catGradient: (Color, Color)) -> some View {
        if let preloaded = preloadedImages[url] {
            ZStack {
                LinearGradient(colors: [catGradient.0, catGradient.1], startPoint: .topLeading, endPoint: .bottomTrailing)
                styledBannerImage(preloaded, url: url, presentation: resolved.presentation)
            }
        } else {
            AsyncImage(url: url) { phase in
                switch phase {
                case .success(let image):
                    ZStack {
                        LinearGradient(colors: [catGradient.0, catGradient.1], startPoint: .topLeading, endPoint: .bottomTrailing)
                        styledBannerImage(image, url: url, presentation: resolved.presentation)
                    }
                case .failure:
                    if let crestURL = resolved.fallbackCrestURL {
                        crestBanner(url: crestURL, catGradient: catGradient)
                    } else {
                        monogramBanner(resolved.monogram)
                    }
                case .empty:
                    LinearGradient(colors: [catGradient.0, catGradient.1], startPoint: .topLeading, endPoint: .bottomTrailing)
                @unknown default:
                    monogramBanner(resolved.monogram)
                }
            }
        }
    }

    @ViewBuilder
    private func crestBanner(url: URL, catGradient: (Color, Color)) -> some View {
        if let preloaded = preloadedImages[url] {
            ZStack {
                LinearGradient(colors: [catGradient.0, catGradient.1], startPoint: .topLeading, endPoint: .bottomTrailing)
                preloaded
                    .resizable()
                    .scaledToFit()
                    .frame(width: 96, height: 96)
                    .padding(.vertical, 12)
                    .shadow(color: .black.opacity(0.28), radius: 6, x: 0, y: 2)
            }
        } else {
            AsyncImage(url: url) { phase in
                switch phase {
                case .success(let image):
                    ZStack {
                        LinearGradient(colors: [catGradient.0, catGradient.1], startPoint: .topLeading, endPoint: .bottomTrailing)
                        image
                            .resizable()
                            .scaledToFit()
                            .frame(width: 96, height: 96)
                            .padding(.vertical, 12)
                            .shadow(color: .black.opacity(0.28), radius: 6, x: 0, y: 2)
                    }
                default:
                    monogramBanner(resolved.monogram)
                }
            }
        }
    }

    @ViewBuilder
    private func styledBannerImage(_ image: Image, url: URL, presentation: String?) -> some View {
        let mode = presentation?.lowercased() ?? "photo"
        if mode == "logo" {
            image
                .resizable()
                .scaledToFit()
                .frame(width: 96, height: 96)
                .padding(.vertical, 12)
                .shadow(color: .black.opacity(0.28), radius: 6, x: 0, y: 2)
        } else if mode == "cover" {
            image
                .resizable()
                .scaledToFit()
                .frame(width: 112)
                .padding(.vertical, 10)
                .shadow(color: .black.opacity(0.35), radius: 8, x: 0, y: 3)
        } else if mode == "portrait", url.absoluteString.contains("espncdn.com/i/headshots/") {
            VStack(spacing: 0) {
                Spacer(minLength: 8)
                image
                    .resizable()
                    .scaledToFit()
                    .frame(width: 160)
                    .shadow(color: .black.opacity(0.32), radius: 8, x: 0, y: 2)
            }
        } else if mode == "portrait" {
            GeometryReader { geo in
                image
                    .resizable()
                    .scaledToFill()
                    .frame(width: geo.size.width, height: geo.size.height, alignment: .top)
                    .clipped()
            }
        } else {
            GeometryReader { geo in
                image
                    .resizable()
                    .scaledToFill()
                    .frame(width: geo.size.width, height: geo.size.height, alignment: .center)
                    .clipped()
            }
        }
    }

    private func monogramBanner(_ monogram: DiscoverImageMonogram) -> some View {
        LinearGradient(
            colors: [Color(hex: monogram.bgHex), Color(hex: monogram.accentHex)],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
        .overlay {
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .fill(Color.white.opacity(0.14))
                .frame(width: 60, height: 60)
                .overlay(
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .strokeBorder(Color.white.opacity(0.26), lineWidth: 1)
                )
                .overlay(
                    Text(monogram.initials)
                        .font(.system(size: 20, weight: .bold, design: .monospaced))
                        .foregroundStyle(.white)
                )
                .shadow(color: .black.opacity(0.22), radius: 6, x: 0, y: 2)
        }
    }
}
