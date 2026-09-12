import SwiftUI

#if canImport(UIKit)
import UIKit
#elseif canImport(AppKit)
import AppKit
#endif

// MARK: - Category Gradient Palette (shared with DiscoverFuturesCard)

private let shareCardGradients: [String: (Color, Color)] = [
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

private let shareCardDefaultGradient: (Color, Color) = (
    Color(red: 0.06, green: 0.09, blue: 0.16),
    Color(red: 0.12, green: 0.16, blue: 0.24)
)

// MARK: - Shareable Card Views

/// A self-contained futures card view designed for image rendering and sharing.
/// Uses category gradients as background (no external image loading).
/// Fixed at 375x500pt for IG Story friendly aspect ratio.
struct ShareableFuturesCardView: View {
    let marketName: String
    let leaderName: String
    let probability: Double
    let category: String
    let hookDescription: String?
    let outcomes: [(name: String, probability: Double)]

    private var gradient: (Color, Color) {
        shareCardGradients[category.lowercased()] ?? shareCardDefaultGradient
    }

    private var categoryLabel: String {
        sportCategoryDisplayName(category).uppercased()
    }

    private var categoryEmoji: String {
        switch category.lowercased() {
        case "politics": return "🏛"
        case "geopolitics": return "🌍"
        case "economics": return "📈"
        case "tech": return "💻"
        case "entertainment": return "🎬"
        case "culture": return "🎭"
        case "weather": return "🌤"
        case "health": return "🏥"
        case "basketball": return "🏀"
        case "football": return "🏈"
        case "baseball": return "⚾"
        case "hockey": return "🏒"
        case "soccer": return "⚽"
        case "golf": return "⛳"
        case "mma": return "🥊"
        case "cricket": return "🏏"
        case "olympics": return "🏅"
        default: return "🍀"
        }
    }

    private var heroOutcomeLabel: String {
        let trimmed = leaderName.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return "Market probability" }
        if trimmed.count > 44 || trimmed == marketName {
            return "Leading outcome"
        }
        return trimmed
    }

    private var hookLineLimit: Int {
        outcomes.count > 1 ? 4 : 8
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Hero section with gradient background
            ZStack(alignment: .bottomLeading) {
                LinearGradient(
                    colors: [gradient.0, gradient.1],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
                .overlay(
                    Text(categoryEmoji)
                        .font(.system(size: 120))
                        .opacity(0.08)
                        .offset(x: 100, y: -20)
                )

                VStack(alignment: .leading, spacing: 12) {
                    Text(categoryLabel)
                        .font(.system(size: 11, weight: .heavy))
                        .tracking(1.0)
                        .foregroundStyle(.white.opacity(0.78))
                        .padding(.horizontal, 10)
                        .padding(.vertical, 5)
                        .background(.black.opacity(0.24), in: Capsule())

                    Spacer(minLength: 16)

                    Text("\(Int((probability * 100).rounded()))%")
                        .font(.system(size: 64, weight: .black).monospacedDigit())
                        .foregroundStyle(.white)
                        .shadow(color: .black.opacity(0.30), radius: 10, x: 0, y: 4)

                    Text(heroOutcomeLabel)
                        .font(.system(size: 20, weight: .bold))
                        .foregroundStyle(.white.opacity(0.92))
                        .lineLimit(2)
                        .minimumScaleFactor(0.82)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(18)
            }
            .frame(height: 220)
            .clipped()

            // Content section with white/light background
            VStack(alignment: .leading, spacing: 14) {
                Text(marketName)
                    .font(.system(size: 18, weight: .bold))
                    .lineLimit(4)
                    .fixedSize(horizontal: false, vertical: true)
                    .foregroundStyle(Color(red: 0.10, green: 0.10, blue: 0.12))

                if let hook = hookDescription, !hook.isEmpty {
                    Text(hook)
                        .font(.system(size: 14))
                        .foregroundStyle(Color(red: 0.35, green: 0.35, blue: 0.40))
                        .lineLimit(hookLineLimit)
                        .fixedSize(horizontal: false, vertical: true)
                }

                if outcomes.count > 1 {
                    VStack(spacing: 8) {
                        ForEach(Array(outcomes.prefix(3).enumerated()), id: \.offset) { idx, outcome in
                            shareableOutcomeRow(
                                name: outcome.name,
                                probability: outcome.probability,
                                isLeader: idx == 0
                            )
                        }
                    }
                }

                Spacer(minLength: 0)

                // Watermark
                HStack {
                    Spacer()
                    Text("bainluck.com")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(Color(red: 0.55, green: 0.55, blue: 0.60))
                    Text("🍀")
                        .font(.system(size: 12))
                }
            }
            .padding(18)
        }
        .frame(width: 375, height: 500)
        .background(Color.white)
        .clipShape(RoundedRectangle(cornerRadius: 22))
    }

    private func shareableOutcomeRow(name: String, probability: Double, isLeader: Bool) -> some View {
        HStack(spacing: 8) {
            Text(name)
                .font(.system(size: 13, weight: isLeader ? .semibold : .regular))
                .lineLimit(2)
                .foregroundStyle(Color(red: 0.15, green: 0.15, blue: 0.18))
                .frame(width: 130, alignment: .leading)

            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule()
                        .fill(Color(red: 0.90, green: 0.90, blue: 0.92))
                    Capsule()
                        .fill(isLeader
                              ? Color(red: 0.20, green: 0.40, blue: 0.85)
                              : Color(red: 0.70, green: 0.70, blue: 0.75))
                        .frame(width: max(3, geo.size.width * probability))
                }
            }
            .frame(height: 7)

            Text("\(Int((probability * 100).rounded()))%")
                .font(.system(size: 13, weight: .bold).monospacedDigit())
                .foregroundStyle(Color(red: 0.15, green: 0.15, blue: 0.18))
                .frame(width: 36, alignment: .trailing)
        }
    }
}

/// A self-contained event card view designed for image rendering and sharing.
/// Uses team colors as visual anchors on a clean white background.
struct ShareableEventCardView: View {
    let homeTeam: String
    let awayTeam: String

    /// #3430 — the share card draws two crests side by side. Two crests reading
    /// `TIG` is a card that travels off the app saying nothing.
    private var crests: (away: String, home: String) {
        TeamShortName.abbreviationPair(away: awayTeam, home: homeTeam)
    }
    let homeProbability: Double
    /// #5363 — OPTIONAL, and nil means *withheld*, not *absent*.
    ///
    /// On a draw-priced sport (soccer) the away figure is `1 − P(home)`, which is
    /// *away win **or** draw*, so this card — the one artefact of ours that
    /// travels to people who never opened the app and cannot check it against
    /// anything — printed a number under the away crest that no market quoted.
    /// The crest, the team name and the score stay; only the probability goes.
    let awayProbability: Double?
    /// What the BAR's first segment measures when there is no away probability
    /// to print: the remainder, which is a true quantity ("not the home team")
    /// even where it cannot be attributed to the away side. #5271 settled this
    /// on the event page — the segment survives, the away team's colour does not.
    private var awayBarShare: Double { awayProbability ?? (1 - homeProbability) }
    let sportName: String
    let homeColor: Color
    let awayColor: Color
    let status: String?
    let homeScore: Int?
    let awayScore: Int?
    /// #4044 — the clock this view did not have.
    ///
    /// `suspended` is a status, not a phase: event 416569 (Ohio State @ Texas)
    /// carried it four days BEFORE kick-off. Every other iOS surface has asked the
    /// clock since #4021; this one could not, because there was no `commenceTime`
    /// on the view to ask with, and it was pinned as an explicit carve-out in
    /// `eventStatusSingleSource.test.ts` rather than left to be rediscovered.
    let commenceTime: Date?

    private var eyebrow: String {
        Self.eyebrow(status: status, sportName: sportName, commenceTime: commenceTime)
    }

    /// The eyebrow word, as a function of the values that decide it.
    ///
    /// Static rather than a `private var` on the view so the suite runs the
    /// PRODUCTION path — `@testable import` does not reach `private`, and this
    /// band is the copy we have the least ability to correct once an image has
    /// left the app. `now` is injected so the clock arm is pinned at a fixed
    /// instant rather than tested against whatever time CI runs at.
    static func eyebrow(
        status: String?, sportName: String, commenceTime: Date?, now: Date = Date()
    ) -> String {
        if status == "live" { return "LIVE" }
        if EventState.isFinished(status) { return "FINAL" }
        // live/048 — a shared share card must not print "FINAL" or fall silently
        // back to the sport name on a match with no reported result. This one
        // leaves the app and is screenshotted, so it is the copy of the claim we
        // have the least ability to correct later.
        //
        // #4044, TWO changes, both deliberate.
        //
        // 1. THE CLOCK. `isSuspended` alone rendered the settled treatment over a
        //    game nobody had started — the denylist shape `isSuspendedAndStarted`
        //    exists to stop. On an image that leaves the app, a future fixture
        //    labelled as stopped is the least correctable copy we ship.
        //
        // 2. THE WORD. It printed its own literal "PAUSED", the #4002 root cause
        //    in miniature. The register is genuinely shorter and reads well on an
        //    image, and #4044 asked for the call to be made rather than delegated
        //    for consistency's sake — so: "PAUSED" is WRONG, on this file's own
        //    published reasoning. `suspendedLabel`'s doc comment says why the
        //    badge is not the bare word "Suspended": the same state covers a
        //    rain-delayed match AND a fixture whose only source went dark, and
        //    telling a reader the latter is paused invents a stoppage nobody
        //    reported. That argument does not weaken on a share card; it is
        //    strongest there, because the image outlives our ability to correct
        //    it. At 11pt over a 375pt card with 22pt padding the longer string
        //    occupies roughly 140 of 331 available points, so nothing is traded
        //    for it but brevity.
        if EventState.isSuspendedAndStarted(status, commenceTime: commenceTime, now: now) {
            return EventState.suspendedLabel.uppercased()
        }
        return sportName.uppercased()
    }

    var body: some View {
        VStack(spacing: 0) {
            // Dark header band
            HStack {
                if status == "live" {
                    Circle()
                        .fill(Color.red)
                        .frame(width: 8, height: 8)
                }
                Text(eyebrow)
                    .font(.system(size: 11, weight: .heavy))
                    .tracking(1.0)
                    .foregroundStyle(status == "live" ? .red : .white.opacity(0.7))
                Spacer()
            }
            .padding(.horizontal, 22)
            .padding(.vertical, 14)
            .background(Color(red: 0.08, green: 0.08, blue: 0.12))

            // Teams section
            VStack(spacing: 24) {
                Spacer(minLength: 12)

                HStack(alignment: .center, spacing: 0) {
                    // Away team
                    VStack(spacing: 10) {
                        RoundedRectangle(cornerRadius: 14)
                            .fill(awayColor)
                            .frame(width: 56, height: 56)
                            .overlay(
                                Text(crests.away)
                                    .font(.system(size: 12, weight: .heavy))
                                    .foregroundStyle(.white)
                            )
                        Text(awayTeam)
                            .font(.system(size: 15, weight: .bold))
                            .multilineTextAlignment(.center)
                            .lineLimit(3)
                            .foregroundStyle(Color(red: 0.10, green: 0.10, blue: 0.12))
                        // #5363 — withheld on a draw-priced sport. The slot is
                        // left empty rather than dashed: this image has no
                        // legend and travels without us, so a mark a stranger
                        // cannot interpret is worse than white space.
                        if let awayProbability {
                            Text(formatProbability(awayProbability))
                                .font(.system(size: 32, weight: .black).monospacedDigit())
                                .foregroundStyle(awayColor)
                        }
                        if let score = awayScore {
                            Text("\(score)")
                                .font(.system(size: 14, weight: .heavy).monospacedDigit())
                                .foregroundStyle(Color(red: 0.45, green: 0.45, blue: 0.50))
                                .padding(.horizontal, 8)
                                .padding(.vertical, 3)
                                .background(Color(red: 0.92, green: 0.92, blue: 0.94))
                                .clipShape(Capsule())
                        }
                    }
                    .frame(maxWidth: .infinity)

                    Text("vs")
                        .font(.system(size: 14, weight: .bold))
                        .foregroundStyle(Color(red: 0.55, green: 0.55, blue: 0.60))
                        .frame(width: 36)

                    // Home team
                    VStack(spacing: 10) {
                        RoundedRectangle(cornerRadius: 14)
                            .fill(homeColor)
                            .frame(width: 56, height: 56)
                            .overlay(
                                Text(crests.home)
                                    .font(.system(size: 12, weight: .heavy))
                                    .foregroundStyle(.white)
                            )
                        Text(homeTeam)
                            .font(.system(size: 15, weight: .bold))
                            .multilineTextAlignment(.center)
                            .lineLimit(3)
                            .foregroundStyle(Color(red: 0.10, green: 0.10, blue: 0.12))
                        Text(formatProbability(homeProbability))
                            .font(.system(size: 32, weight: .black).monospacedDigit())
                            .foregroundStyle(homeColor)
                        if let score = homeScore {
                            Text("\(score)")
                                .font(.system(size: 14, weight: .heavy).monospacedDigit())
                                .foregroundStyle(Color(red: 0.45, green: 0.45, blue: 0.50))
                                .padding(.horizontal, 8)
                                .padding(.vertical, 3)
                                .background(Color(red: 0.92, green: 0.92, blue: 0.94))
                                .clipShape(Capsule())
                        }
                    }
                    .frame(maxWidth: .infinity)
                }

                // Probability bar
                GeometryReader { geo in
                    HStack(spacing: 0) {
                        Rectangle()
                            .fill(awayProbability == nil
                                  ? Color.secondary.opacity(0.25)
                                  : awayColor)
                            .frame(width: max(3, geo.size.width * awayBarShare))
                        Rectangle()
                            .fill(homeColor)
                            .frame(width: max(3, geo.size.width * homeProbability))
                    }
                    .clipShape(Capsule())
                }
                .frame(height: 10)
                .padding(.horizontal, 4)

                Spacer(minLength: 0)

                // Watermark
                HStack {
                    Spacer()
                    Text("bainluck.com")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(Color(red: 0.55, green: 0.55, blue: 0.60))
                    Text("🍀")
                        .font(.system(size: 12))
                }
            }
            .padding(22)
        }
        .frame(width: 375, height: 500)
        .background(Color.white)
        .clipShape(RoundedRectangle(cornerRadius: 22))
    }
}

// MARK: - Share Card Renderer

@MainActor
enum ShareCardRenderer {

    /// Render a futures Discover card as a shareable image.
    static func renderFuturesCard(
        marketName: String,
        leaderName: String,
        probability: Double,
        category: String,
        hookDescription: String?,
        outcomes: [(name: String, probability: Double)] = []
    ) -> PlatformImage? {
        let view = ShareableFuturesCardView(
            marketName: marketName,
            leaderName: leaderName,
            probability: probability,
            category: category,
            hookDescription: hookDescription,
            outcomes: outcomes
        )
        let renderer = ImageRenderer(content: view)
        #if canImport(UIKit)
        renderer.scale = UIScreen.main.scale
        return renderer.uiImage
        #elseif canImport(AppKit)
        renderer.scale = NSScreen.main?.backingScaleFactor ?? 2.0
        return renderer.nsImage
        #endif
    }

    /// Render an event Discover card as a shareable image.
    static func renderEventCard(
        homeTeam: String,
        awayTeam: String,
        homeProbability: Double,
        /// #5363 — nil withholds the away number. No default, for the reason
        /// `commenceTime` has none: a caller that forgets it would silently
        /// restore the old reading on the one surface whose output leaves the app.
        awayProbability: Double?,
        sportName: String,
        homeColor: Color,
        awayColor: Color,
        status: String?,
        homeScore: Int?,
        awayScore: Int?,
        // #4044 — no default. A caller that forgets it would silently restore the
        // clockless behaviour on the one surface whose output leaves the app.
        commenceTime: Date?
    ) -> PlatformImage? {
        let view = ShareableEventCardView(
            homeTeam: homeTeam,
            awayTeam: awayTeam,
            homeProbability: homeProbability,
            awayProbability: awayProbability,
            sportName: sportName,
            homeColor: homeColor,
            awayColor: awayColor,
            status: status,
            homeScore: homeScore,
            awayScore: awayScore,
            commenceTime: commenceTime
        )
        let renderer = ImageRenderer(content: view)
        #if canImport(UIKit)
        renderer.scale = UIScreen.main.scale
        return renderer.uiImage
        #elseif canImport(AppKit)
        renderer.scale = NSScreen.main?.backingScaleFactor ?? 2.0
        return renderer.nsImage
        #endif
    }

    /// Copy a rendered image to the system clipboard.
    static func copyImageToClipboard(_ image: PlatformImage) {
        #if canImport(UIKit)
        UIPasteboard.general.image = image
        #elseif canImport(AppKit)
        let pasteboard = NSPasteboard.general
        pasteboard.clearContents()
        pasteboard.writeObjects([image])
        #endif
    }

    /// Save a rendered image to the photo library (iOS only).
    static func saveImageToPhotos(_ image: PlatformImage) {
        #if canImport(UIKit)
        UIImageWriteToSavedPhotosAlbum(image, nil, nil, nil)
        #endif
    }
}
