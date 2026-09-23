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
