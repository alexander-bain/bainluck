import XCTest
@testable import Bain_Luck

/// #8415 — the phone's first ten are the ten the feed chose, spaced.
///
/// The phone half of web #8413. `FeedInterleave.spaced` replaced a pass that
/// forced one non-sports card after every two sports cards whatever the ranking;
/// on the phone's own 2026-09-24 payload it turned a served 4/6 top ten into
/// 7/3 and pulled NASCAR (#18), the Azerbaijan Grand Prix (#19) and ATP Hangzhou
/// (#20) onto page one. The web's replacement is
/// `frontend/lib/discover/spacedOrder.ts`; its guard is
/// `frontend/__tests__/discover/spacingDefersNeverPromotes8413.test.ts`, and the
/// second test below runs that guard's fixture through the Swift pass so the two
/// platforms are held to the same page.
final class DiscoverSpacingTests: XCTestCase {

    private struct Card: Equatable, Hashable {
        let id: Int
        let name: String
        let cat: String
        let story: String?
        var family: String { story.map { "\(cat)|\($0)" } ?? cat }
    }

    private let sportsCats = DiscoverCategory.sportsCategories

    private func space(_ cards: [Card]) -> [Card] {
        FeedInterleave.spaced(cards, sportsCategories: sportsCats,
                              category: { $0.cat }, family: { $0.family })
    }

    private func cards(_ rows: [(String, String, String?)]) -> [Card] {
        rows.enumerated().map { Card(id: $0.offset + 1, name: $0.element.0, cat: $0.element.1, story: $0.element.2) }
    }

    // MARK: - The production payload

    /// `GET /api/feed?limit=50&offset=0&event_pct=0.15` — the phone's first-page
    /// request — at 2026-09-24 ~20:45Z, reduced to name + the category and story
    /// key `DiscoverCategory` derives. Full payload:
    /// `artifacts/native-327/feed-fixture-2026-09-24.json`.
    private static let served20260924: [(String, String, String?)] = [
        ("Miami Marlins@Chicago Cubs", "baseball", nil),
        ("Arizona Diamondbacks@Colorado Rock", "baseball", nil),
        ("New York Mets@Texas Rangers", "baseball", nil),
        ("MLB World Series Winner", "baseball", nil),
        ("2027 PPA Tour Finals: Player to Qu", "pickleball", nil),
        ("Brazil Presidential Election", "politics", nil),
        ("AI", "tech", nil),
        ("Awards Season", "entertainment", nil),
        ("US x Iran ceasefire continues thro", "geopolitics", "story:middle_east_conflict"),
        ("Fed & Rates", "economics", nil),
        ("St. Louis Cardinals@Pittsburgh Pir", "baseball", nil),
        ("Chicago White Sox@Kansas City Roya", "baseball", nil),
        ("IPOs", "economics", nil),
        ("Will China invade Taiwan by end of", "politics", nil),
        ("Next French Presidential Election", "politics", nil),
        ("Will there be at least 5000 measle", "health", nil),
        ("Where will it rain on September 24", "weather", nil),
        ("NASCAR Cup Series: 2026 Champion", "motorsports", nil),
        ("Azerbaijan Grand Prix: Driver Winn", "motorsports", nil),
        ("ATP Hangzhou Winner", "tennis", nil),
        ("NFL Super Bowl Winner", "football", nil),
        ("WTI Crude Oil (WTI) closes above $", "economics", "story:oil"),
        ("Will Rocket Lab USA, Inc. (RKLB) h", "economics", nil),
        ("2028 Election", "politics", nil),
        ("How long will Trump and Xi shake h", "geopolitics", nil),
        ("When will Apple release the iPhone", "tech", nil),
        ("FedEx Open de France", "golf", nil),
        ("Which party will win the U.S. Sena", "politics", nil),
        ("Russia–Ukraine", "politics", nil),
        ("Dancing with the Stars Season 35 ·", "entertainment", nil),
        ("UFC", "mma", nil),
        ("2026-27 Stanley Cup® Finals Winner", "hockey", nil),
        ("Will the U.S. invade Iran before 2", "politics", "story:middle_east_conflict"),
        ("Iran leadership change?", "politics", "story:middle_east_conflict"),
        ("Which party will win the U.S. Hous", "politics", nil),
        ("NATO x Russia military clash?", "geopolitics", nil),
        ("Cleveland Guardians@Boston Red Sox", "baseball", nil),
        ("Presidents Cup", "golf", nil),
        ("Next James Bond actor?", "entertainment", nil),
        ("Tampa Bay Rays@New York Yankees", "baseball", nil),
        ("Next Mayor of Nelson Mandela Bay (", "politics", nil),
        ("Kanye West performs in Russia by O", "entertainment", nil),
        ("US recession by end of 2026?", "economics", nil),
        ("Prime Minister of Israel after the", "politics", "story:middle_east_conflict"),
        ("Venezuela leader end of 2026?", "politics", nil),
        ("Milwaukee Brewers@Philadelphia Phi", "baseball", nil),
        ("Will Trump buy at least part of Gr", "politics", nil),
        ("2026 Midterms: Congress Balance of", "politics", nil),
        ("Will the US take control of any pa", "politics", nil),
        ("Nobel Peace Prize Winner 2026", "politics", nil),
    ]

    /// The phone spaces three times: the page-merge pass in the view model, then
    /// the view's pass before grouping and again after personalization.
    private func asRendered(_ cards: [Card]) -> [Card] { space(space(space(cards))) }

    func testFirstTenAreTheServedTenOnTheProductionPayload() {
        let served = cards(Self.served20260924)
        let firstTen = asRendered(served).prefix(10)
        XCTAssertEqual(firstTen.map(\.name), [
            "Miami Marlins@Chicago Cubs",
            "2027 PPA Tour Finals: Player to Qu",
            "Arizona Diamondbacks@Colorado Rock",
            "Brazil Presidential Election",
            "New York Mets@Texas Rangers",
            "AI",
            "MLB World Series Winner",
            "Awards Season",
            "US x Iran ceasefire continues thro",
            "Fed & Rates",
        ])
        XCTAssertEqual(Set(firstTen.map(\.id)), Set(1...10), "the served ten, and only them")
    }

    func testTheCardsTheOldPassPulledOntoPageOneStayBelowIt() {
        let names = asRendered(cards(Self.served20260924)).prefix(10).map(\.name)
        for pulled in ["NASCAR Cup Series: 2026 Champion", "Azerbaijan Grand Prix: Driver Winn",
                       "ATP Hangzhou Winner", "St. Louis Cardinals@Pittsburgh Pir"] {
            XCTAssertFalse(names.contains(pulled), "\(pulled) is not in the served ten")
        }
    }

    /// The web guard's own fixture (`SERVED_20260924`, `/api/feed?limit=20`), run
    /// through the Swift pass twice as the web page does. Same first ten as the
    /// web asserts — the platforms render one page.
    func testTheWebGuardsFixtureRendersTheWebsFirstTen() {
        let web = cards([
            ("Cardinals@Pirates LIVE", "baseball", nil), ("White Sox@Royals starting soon", "baseball", nil),
            ("Mets@Rangers", "baseball", nil), ("MLB World Series Winner", "baseball", nil),
            ("China invade Taiwan", "politics", nil), ("US invade Iran", "politics", nil),
            ("Xi out before 2027", "geopolitics", nil), ("Brazil Presidential Election", "politics", nil),
            ("Awards Season", "entertainment", nil), ("US x Iran ceasefire", "geopolitics", nil),
            ("Astros@Mariners final", "baseball", nil), ("Kings@Ducks final", "icehockey", nil),
            ("Fed & Rates", "economics", nil), ("IPOs", "economics", nil),
            ("French Presidential Election", "politics", nil), ("Where will it rain", "weather", nil),
            ("NASCAR Cup Champion", "motorsports", nil), ("Worlds 2026", "esports", nil),
            ("Compliance Solutions Championship", "golf", nil), ("FedEx Open de France", "golf", nil),
        ])
        XCTAssertEqual(space(space(web)).prefix(10).map(\.name), [
            "Cardinals@Pirates LIVE", "China invade Taiwan", "White Sox@Royals starting soon",
            "US invade Iran", "Mets@Rangers", "Xi out before 2027", "MLB World Series Winner",
            "Brazil Presidential Election", "Awards Season", "US x Iran ceasefire",
        ])
    }

    // MARK: - Spacing defers, it never promotes

    private func rng(_ seed: UInt64) -> () -> Double {
        var s = seed
        return {
            s = (s &* 1_664_525 &+ 1_013_904_223) % 4_294_967_296
            return Double(s) / 4_294_967_296
        }
    }

    private func randomList(_ seed: UInt64, cats: [String], stories: [String?]) -> [Card] {
        let r = rng(seed)
        let n = 3 + Int(r() * 30)
        return (0..<n).map { i in
            Card(id: i, name: "c\(i)", cat: cats[Int(r() * Double(cats.count))],
                 story: stories[Int(r() * Double(stories.count))])
        }
    }

    private let mixedCats = ["baseball", "baseball", "baseball", "icehockey", "golf",
                             "politics", "politics", "economics", "tech"]
    private let mixedStories: [String?] = [nil, nil, "story:a", "story:b"]

    /// Stated independently of the implementation: at every slot, find the
    /// strictest rule any remaining card satisfies; the placed card must satisfy
    /// it, and no card ranked above the placed one may.
    func testEveryCardPlacedAheadOfAHigherRankedOneWasHeldBackByARule() {
        for seed in UInt64(1)...400 {
            let input = randomList(seed, cats: mixedCats, stories: mixedStories)
            let out = space(input)
            XCTAssertEqual(out.count, input.count)
            XCTAssertEqual(Set(out), Set(input))

            let cap = input.filter { !sportsCats.contains($0.cat) }.count >= 4 ? 2 : 3
            var remaining = input
            var lastCat = "", lastFam = "", run = 0
            for placed in out {
                let sportsOK: (Card) -> Bool = {
                    !self.sportsCats.contains($0.cat) || (run < cap && $0.cat != lastCat)
                }
                let rules: [(Card) -> Bool] = [
                    { sportsOK($0) && $0.cat != lastCat && $0.family != lastFam },
                    { sportsOK($0) && $0.cat != lastCat },
                    { sportsOK($0) && $0.family != lastFam },
                    sportsOK,
                    { $0.cat != lastCat },
                    { _ in true },
                ]
                let rule = rules.first { r in remaining.contains(where: r) }!
                let idx = remaining.firstIndex(of: placed)!
                XCTAssertTrue(rule(placed), "seed \(seed): placed card breaks the strictest satisfiable rule")
                for skipped in remaining[..<idx] {
                    XCTAssertFalse(rule(skipped), "seed \(seed): \(skipped.name) was allowed and ranked higher")
                }
                remaining.remove(at: idx)
                lastCat = placed.cat
                lastFam = placed.family
                run = sportsCats.contains(placed.cat) ? run + 1 : 0
            }
        }
    }

    /// A literal port of the web's `spaceBySport`. Where no two non-sports cards
    /// share a category (and so no story can repeat either), the phone's extra
    /// rules have nothing to hold back and its order must BE the web's order.
    private func webSpaceBySport(_ items: [Card]) -> [Card] {
        if items.count <= 2 { return items }
        let nonSports = items.filter { !sportsCats.contains($0.cat) }.count
        let maxSportsRun = nonSports >= 4 ? 2 : 3
        var remaining = items, result: [Card] = []
        var lastSport = "", sportsSinceNonSport = 0
        while !remaining.isEmpty {
            var pick = remaining.firstIndex {
                !sportsCats.contains($0.cat) || (sportsSinceNonSport < maxSportsRun && $0.cat != lastSport)
            }
            if pick == nil { pick = remaining.firstIndex { $0.cat != lastSport } }
            let item = remaining.remove(at: pick ?? 0)
            result.append(item)
            if sportsCats.contains(item.cat) {
                lastSport = item.cat
                sportsSinceNonSport += 1
            } else {
                lastSport = ""
                sportsSinceNonSport = 0
            }
        }
        return result
    }

    func testMatchesTheWebWhenNoTwoNonSportsCardsShareACategory() {
        let sports = ["baseball", "baseball", "icehockey", "golf", "football"]
        let others = ["politics", "economics", "tech", "weather", "health", "entertainment"]
        for seed in UInt64(1)...400 {
            let r = rng(seed)
            var pool = others
            let input: [Card] = (0..<(3 + Int(r() * 20))).map { i in
                if !pool.isEmpty && r() < 0.4 {
                    return Card(id: i, name: "c\(i)", cat: pool.removeFirst(), story: nil)
                }
                return Card(id: i, name: "c\(i)", cat: sports[Int(r() * Double(sports.count))], story: nil)
            }
            XCTAssertEqual(space(input), webSpaceBySport(input), "seed \(seed)")
        }
    }

    func testIsIdempotentSoTheSecondAndThirdPassesMoveNothing() {
        for seed in UInt64(1)...400 {
            let once = space(randomList(seed, cats: mixedCats, stories: mixedStories))
            XCTAssertEqual(space(once), once, "seed \(seed)")
        }
    }

    // MARK: - Shape and cost

    func testSmallInputsAreReturnedUnchanged() {
        XCTAssertEqual(space([]), [])
        let pair = cards([("a", "baseball", nil), ("b", "baseball", nil)])
        XCTAssertEqual(space(pair), pair)
    }

    /// Worst case for a rescan-per-slot pass: one non-sports card and 499 of one
    /// sport. Each classifier runs exactly once per card — the slot loop reads
    /// the precomputed tokens, never the closures.
    func testClassifiersRunOncePerCardEvenOnTheWorstCaseInput() {
        var input = [Card(id: -1, name: "x", cat: "economics", story: nil)]
        input += (0..<499).map { Card(id: $0, name: "b\($0)", cat: "basketball", story: nil) }
        var catCalls = 0, famCalls = 0
        let out = FeedInterleave.spaced(
            input, sportsCategories: sportsCats,
            category: { catCalls += 1; return $0.cat },
            family: { famCalls += 1; return $0.family })
        XCTAssertEqual(Set(out), Set(input))
        XCTAssertEqual(catCalls, input.count)
        XCTAssertEqual(famCalls, input.count)
        XCTAssertEqual(out.first?.id, -1, "the top-ranked card keeps its slot")
    }
}

/// L2-202 Item 2 — the presentation memo. Proves rebuild-only-on-semantic-change
/// deterministically, without needing a live SwiftUI body pass.
final class MemoizedPresentationTests: XCTestCase {

    func testSameSignatureReturnsCachedValueAndBuildsOnce() {
        let memo = MemoizedPresentation<[Int]>()
        var builds = 0
        let a = memo.resolve(signature: "s1") { builds += 1; return [1, 2, 3] }
        let b = memo.resolve(signature: "s1") { builds += 1; return [9, 9, 9] }
        XCTAssertEqual(a, [1, 2, 3])
        XCTAssertEqual(b, [1, 2, 3], "identical signature must reuse the cached value")
        XCTAssertEqual(builds, 1)
        XCTAssertEqual(memo.buildCount, 1)
    }

    func testEachDistinctSignatureRebuildsExactlyOnce() {
        let memo = MemoizedPresentation<[Int]>()
        var builds = 0
        _ = memo.resolve(signature: "s1") { builds += 1; return [1] }
        _ = memo.resolve(signature: "s2") { builds += 1; return [2] }
        _ = memo.resolve(signature: "s2") { builds += 1; return [99] } // cached
        _ = memo.resolve(signature: "s3") { builds += 1; return [3] }
        XCTAssertEqual(builds, 3)
        XCTAssertEqual(memo.buildCount, 3)
    }

    func testInvalidateForcesOneRebuild() {
        let memo = MemoizedPresentation<[Int]>()
        var builds = 0
        _ = memo.resolve(signature: "s1") { builds += 1; return [1] }
        memo.invalidate()
        let after = memo.resolve(signature: "s1") { builds += 1; return [2] }
        XCTAssertEqual(builds, 2)
        XCTAssertEqual(after, [2])
    }

    /// Mirrors `DiscoverView.presentationSignature` semantics: unrelated view
    /// state (scroll, impressions) leaves the signature untouched (no rebuild),
    /// while each named semantic input change rebuilds exactly once.
    func testSignatureInvalidationMatrix() {
        let memo = MemoizedPresentation<Int>()
        var builds = 0
        func sig(_ items: Int, _ dismiss: Int, _ profile: Int, _ bucket: Int) -> String {
            "\(items)|\(dismiss)|\(profile)|\(bucket)"
        }

        // Baseline build.
        _ = memo.resolve(signature: sig(1, 0, 0, 100)) { builds += 1; return builds }
        // Scroll / impression / unrelated @State: signature identical → no rebuild.
        _ = memo.resolve(signature: sig(1, 0, 0, 100)) { builds += 1; return builds }
        _ = memo.resolve(signature: sig(1, 0, 0, 100)) { builds += 1; return builds }
        XCTAssertEqual(builds, 1, "unrelated view-state changes must not rebuild the presentation")

        // Feed change (refresh / pagination merge / account switch — all bump itemsVersion).
        _ = memo.resolve(signature: sig(2, 0, 0, 100)) { builds += 1; return builds }
        // Dismiss store change (swipe / context-menu / refresh clear).
        _ = memo.resolve(signature: sig(2, 1, 0, 100)) { builds += 1; return builds }
        // Interaction profile change (cooldown / personalization).
        _ = memo.resolve(signature: sig(2, 1, 1, 100)) { builds += 1; return builds }
        // Staleness bucket roll (lifecycle / time passing).
        _ = memo.resolve(signature: sig(2, 1, 1, 101)) { builds += 1; return builds }

        XCTAssertEqual(builds, 5, "each named semantic change rebuilds exactly once")
        XCTAssertEqual(memo.buildCount, 5)
    }
}
