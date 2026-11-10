import XCTest
@testable import Bain_Luck

/// #12317 (VoiceOver) — section titles on the game page, Discover, Search and
/// My Stuff are headings, so a VoiceOver reader can jump section to section
/// with the Headings rotor instead of swiping through every row.
final class SectionHeadings12317Tests: XCTestCase {

    // MARK: - Every section title carries it

    /// Each title, in the file that draws it. A title that loses the trait
    /// fails here by name.
    static let titles: [(file: String, title: String)] = [
        ("Views/EventDetailView.swift", #"Text("Win Probability")"#),
        ("Views/EventDetailView.swift", #"Text("Game Info")"#),
        ("Views/EventDetailView.swift", #"Text("Game Segments")"#),
        ("Components/OddsChartView.swift", #"Text("Win Probability")"#),
        ("Components/NFLEventCards9483.swift", #"Text("Game stories")"#),
        ("Components/ProjectedFinalPointsChartView.swift", #"Text("Projected final points")"#),
        ("Components/PlayerPropsCardView.swift", #"Text("Player Props")"#),
        ("Components/EventPropsMatrixView.swift", #"Text("Player Props")"#),
        ("Views/SearchView.swift", #"Text("Recent")"#),
        ("Views/SearchView.swift", #"Text("Tournaments")"#),
        ("Views/SearchView.swift", #"Text("Browse by Sport")"#),
        ("Views/SearchView.swift", #"Text("Categories")"#),
        ("Views/SearchView.swift", #"Text(viewModel.trendingSearches.isEmpty ? "Explore" : "Trending")"#),
    ]

    func testEverySectionTitleIsMarkedAsAHeading() throws {
        for (file, title) in Self.titles {
            let source = try Self.source(file)
            guard let at = source.range(of: title) else { XCTFail("\(file): \(title) not found"); continue }
            // The trait sits in the title's own modifier chain: within the next few lines.
            let chain = source[at.upperBound...].prefix(260)
            XCTAssertTrue(chain.contains(".accessibilityAddTraits(.isHeader)"), "\(file): \(title) is not a heading")
        }
    }

    func testMyStuffsPinnedTitleIsAHeadingOutsideTheList() throws {
        // Inside the List the section header is a heading by itself; the
        // scroll-view version needs the trait.
        let source = try Self.source("Views/MyStuffView.swift")
        let stack = try XCTUnwrap(source.range(of: "private var pinnedStack: some View {"))
        XCTAssertTrue(source[stack.upperBound...].prefix(400).contains(".accessibilityAddTraits(.isHeader)"))
    }

    // MARK: - Helpers


    static func source(_ relative: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/\(relative)")
        return try String(contentsOf: url, encoding: .utf8)
    }
}
