import XCTest
import SwiftUI
@testable import Bain_Luck

/// #4111 — the Discover futures card draws the photograph the payload carries.
///
/// 🔴 THE DEFECT THIS GUARDS IS AN OMISSION, so it is tested by EXISTENCE, not by
/// a ban. `NativeFuturesDiscoverCard` did not render a wrong image or a wrong
/// colour — it rendered no image at all, while `image_url` sat on the wire and
/// `FuturesDetailView` drew it from the same field. A guard shaped "the hero must
/// not do X" cannot see that (my own #2279: a BAN-shaped guard is blind to an
/// omission). Every assertion here therefore names a photo that MUST be chosen.
///
/// The arithmetic is asserted in both directions. A census that only checks
/// "how many resolved to `.photo`" passes just as happily when the eligible
/// population collapses to one card, so the eligible denominator — how many
/// futures cards the fixture actually holds, and how many of those carry a
/// non-null `image_url` — is asserted first and independently of the outcome.
final class DiscoverFuturesHeroArtTests: XCTestCase {

    private func decodeFixture() throws -> FeedResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let data = try XCTUnwrap(DiscoverFeedProdFixture.json.data(using: .utf8))
        return try decoder.decode(FeedResponse.self, from: data)
    }

    /// Top-level futures cards — the ones that render `NativeFuturesDiscoverCard`.
    /// Bundle children are drawn by the bundle card and are a different surface.
    private func futuresCards() throws -> [FeedFuturesData] {
        try decodeFixture().items.compactMap { $0.futures }
    }

    // MARK: - The census, on the real production payload

    /// Every futures card in the fixture that carries an `image_url` resolves to
    /// a photo, and every card that does not falls back to its category.
    ///
    /// Both arms are required to be populated: a fixture of all-photos or
    /// all-gradients would let half this file pass vacuously.
    func testProductionFixture_everyCardWithAnImageURLResolvesToAPhoto() throws {
        let cards = try futuresCards()

        // Denominator first, on its own terms.
        XCTAssertGreaterThanOrEqual(
            cards.count, 20,
            "The fixture should hold a real production page of futures cards; got \(cards.count)."
        )

        let withURL = cards.filter { ($0.imageUrl?.isEmpty == false) }
        let withoutURL = cards.filter { ($0.imageUrl?.isEmpty != false) }

        XCTAssertFalse(
            withURL.isEmpty,
            "No card in the fixture carries an image_url — the photo arm would pass vacuously."
        )
        XCTAssertFalse(
            withoutURL.isEmpty,
            "No card in the fixture lacks an image_url — the gradient arm would pass vacuously."
        )
        XCTAssertEqual(
            withURL.count + withoutURL.count, cards.count,
            "The two arms must partition the population."
        )

        for card in withURL {
            let resolved = FuturesHero.background(imageURL: card.imageUrl)
            guard case .photo(let url) = resolved else {
                return XCTFail(
                    "\"\(card.name)\" carries image_url \(card.imageUrl ?? "nil") but the hero resolved to \(resolved) — this is #4111."
                )
            }
            XCTAssertTrue(
                url.scheme == "https" || url.scheme == "http",
                "\"\(card.name)\" resolved to a non-web URL: \(url)."
            )
        }

        for card in withoutURL {
            XCTAssertEqual(
                FuturesHero.background(imageURL: card.imageUrl), .category,
                "\"\(card.name)\" has no image_url and must fall back to its category gradient."
            )
        }
    }

    /// The share of the page that gains art. Alex's report was that the cards are
    /// "colourless with no images" — one photo on one card would satisfy the test
    /// above and would not answer the report, so the proportion is pinned too.
    func testProductionFixture_mostOfThePageGainsAPhoto() throws {
        let cards = try futuresCards()
        let photos = cards.filter {
            if case .photo = FuturesHero.background(imageURL: $0.imageUrl) { return true }
            return false
        }

        XCTAssertGreaterThan(
            Double(photos.count) / Double(cards.count), 0.5,
            "Only \(photos.count) of \(cards.count) futures cards resolve to a photo; the page is still mostly colourless."
        )
    }

    // MARK: - The fallback is a decision, not an accident

    func testBackground_isCategoryForNilBlankAndWhitespaceURLs() {
        for raw in [nil, "", "   ", "\n\t "] as [String?] {
            XCTAssertEqual(
                FuturesHero.background(imageURL: raw), .category,
                "\(String(describing: raw)) is not a photograph and must not cost the reader a request."
            )
        }
    }

    /// `URL(string:)` is lenient — it accepts strings that are not fetchable, and
    /// will hand back a scheme-less URL rather than nil. "Non-nil" is therefore
    /// not the same question as "loadable photo", and the hero asks the second one.
    func testBackground_isCategoryForANonWebScheme() {
        for raw in ["file:///etc/passwd", "data:image/png;base64,AAAA", "not a url at all"] {
            XCTAssertEqual(
                FuturesHero.background(imageURL: raw), .category,
                "\(raw) is not a web photo and must fall back to the category gradient."
            )
        }
    }

    /// A padded but otherwise valid URL is still a photo.
    ///
    /// This case exists because mutation testing caught the suite passing for the
    /// wrong reason: with only nil/blank/whitespace inputs, deleting the trim from
    /// `background(imageURL:)` killed no test, because the scheme guard downstream
    /// rejected `"   "` on its own. Every whitespace assertion above was being
    /// satisfied by a different line than the one it was written to protect. This
    /// is the input that separates them — the trim is the only thing that turns
    /// `"  https://…  "` into a loadable photo.
    func testBackground_trimsPaddingAroundAnOtherwiseValidURL() throws {
        let clean = "https://images.pexels.com/photos/3970331/pexels-photo-3970331.jpeg"
        let expected = try XCTUnwrap(URL(string: clean))
        XCTAssertEqual(
            FuturesHero.background(imageURL: "  \(clean)\n"), .photo(expected),
            "A padded image_url must resolve to the same photo the unpadded one does."
        )
    }

    func testBackground_isAPhotoForTheShapeTheFeedActuallyServes() {
        let served = "https://images.pexels.com/photos/3970331/pexels-photo-3970331.jpeg?auto=compress&cs=tinysrgb&h=350"
        XCTAssertEqual(FuturesHero.background(imageURL: served), .photo(URL(string: served)!))
    }

    // MARK: - One palette, one ladder

    /// The gradient and the emoji resolve through one table for every category the
    /// palette names, and an unknown category degrades rather than crashing.
    ///
    /// `FuturesDetailView` used to hold a `private` verbatim copy of both — under a
    /// comment that called them "shared with Discover card". They agreed on the day
    /// they were copied, which is exactly why the divergence that did happen (the
    /// photo branch) went unnoticed.
    func testGradientAndEmoji_answerForEveryCategoryIncludingUnknownOnes() {
        for category in sportCategoryGradients.keys {
            let (start, end) = FuturesHero.gradient(for: category)
            XCTAssertNotEqual(
                [start, end], [sportDefaultGradient.0, sportDefaultGradient.1],
                "\(category) is in the palette but resolved to the default gradient."
            )
            XCTAssertEqual(
                [start, end], [sportCategoryGradients[category]!.0, sportCategoryGradients[category]!.1],
                "\(category) did not resolve to its own palette entry."
            )
        }

        let (unknownStart, unknownEnd) = FuturesHero.gradient(for: "quidditch")
        XCTAssertEqual([unknownStart, unknownEnd], [sportDefaultGradient.0, sportDefaultGradient.1])
        XCTAssertEqual(FuturesHero.emoji(for: "quidditch"), "🍀")
        XCTAssertEqual(FuturesHero.emoji(for: nil), "🍀")
    }

    /// Categories are matched case-insensitively — the feed has served both
    /// `"politics"` and `"Politics"` shapes through `llm_sport_category`.
    func testGradientAndEmoji_areCaseInsensitive() {
        XCTAssertEqual(FuturesHero.emoji(for: "POLITICS"), FuturesHero.emoji(for: "politics"))
        let upper = FuturesHero.gradient(for: "BASEBALL")
        let lower = FuturesHero.gradient(for: "baseball")
        XCTAssertEqual([upper.0, upper.1], [lower.0, lower.1])
    }

    /// There is exactly one category-gradient table in the app target. This is the
    /// only assertion here that reads source, and it matches on the DECLARATION
    /// shape rather than on a mention, so a doc comment naming the table cannot
    /// satisfy or trip it.
    func testExactlyOneCategoryGradientTableIsDeclaredForTheHeroes() throws {
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (source root)
            .appendingPathComponent("Bain Luck")

        let enumerator = try XCTUnwrap(FileManager.default.enumerator(atPath: root.path))
        var declaringFiles: [String] = []

        for case let relative as String in enumerator where relative.hasSuffix(".swift") {
            // The share-image renderer keeps its own palette on purpose: it paints
            // a fixed-size raster for another app's timeline, not a card hero.
            if relative.hasSuffix("ShareCardRenderer.swift") { continue }

            let source = try String(contentsOf: root.appendingPathComponent(relative), encoding: .utf8)
            for line in source.split(separator: "\n") {
                let text = line.trimmingCharacters(in: .whitespaces)
                guard !text.hasPrefix("//"), !text.hasPrefix("///") else { continue }
                if text.contains("[String: (Color, Color)]"), text.contains("=") {
                    declaringFiles.append(relative)
                }
            }
        }

        XCTAssertEqual(
            declaringFiles.sorted(), ["Utilities/DiscoverCardVisuals.swift"],
            "The hero palette must be declared once. Found: \(declaringFiles.sorted())."
        )
    }
}
