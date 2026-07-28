import XCTest
@testable import Bain_Luck

/// L2-202 / C42 P2 — the native Discover presentation-path efficiency change:
///   1. `FeedInterleave.byCategory` replaces three `Array.removeFirst()`-based
///      interleave drains (O(n²) main-actor shifting) with one linear-traversal
///      core. These tests pin it byte-for-byte against a literal copy of the old
///      algorithm across 0/1/2/3/50/200/500 mixed fixtures, and prove the
///      classification (traversal) op count scales linearly, not quadratically.
///   2. `MemoizedPresentation` rebuilds the interleave+group pipeline only when a
///      semantic signature changes. These tests prove unrelated view-state
///      changes (scroll, impressions) reuse the cache and each named semantic
///      change (feed / dismiss / profile / staleness bucket) rebuilds once.
final class DiscoverInterleaveTests: XCTestCase {

    private struct Stub: Equatable { let id: Int; let cat: String }

    /// A representative sports/non-sports split (mirrors the app's real
    /// `sportsCats`, but the algorithm only cares that some categories are in the
    /// set and some are not).
    private let sportsCats: Set<String> = ["basketball", "football", "baseball", "hockey", "soccer"]

    private func category(_ s: Stub) -> String { s.cat }

    /// Literal copy of the pre-L2-202 interleave (the `removeFirst`/front-mutation
    /// version shared by `DiscoverViewModel.interleave`, `DiscoverView.interleave`,
    /// and `.interleaveGrouped`). This is the ground truth the new linear core must
    /// reproduce exactly. Generic so it runs over the same `Stub` fixtures.
    private func referenceInterleave<T>(
        _ items: [T],
        sportsCategories: Set<String>,
        category: (T) -> String
    ) -> [T] {
        var sports = items.filter { sportsCategories.contains(category($0)) }
        var nonSports = items.filter { !sportsCategories.contains(category($0)) }
        guard !nonSports.isEmpty else { return items }

        var result: [T] = []
        var lastCategory = ""
        var sportsSinceNonSport = 0
        let maxSportsRun = nonSports.count >= 4 ? 2 : 3

        while !sports.isEmpty || !nonSports.isEmpty {
            if !nonSports.isEmpty && (sportsSinceNonSport >= maxSportsRun || sports.isEmpty) {
                let item = nonSports.removeFirst()
                result.append(item)
                sportsSinceNonSport = 0
                lastCategory = category(item)
                continue
            }
            if !sports.isEmpty {
                if category(sports[0]) == lastCategory,
                   let swapIdx = sports.prefix(5).firstIndex(where: { category($0) != lastCategory }) {
                    sports.swapAt(0, swapIdx)
                }
                let item = sports.removeFirst()
                result.append(item)
                lastCategory = category(item)
                sportsSinceNonSport += 1
            } else if !nonSports.isEmpty {
                let item = nonSports.removeFirst()
                result.append(item)
                sportsSinceNonSport = 0
                lastCategory = category(item)
            }
        }
        return result
    }

    /// Deterministic mixed fixture of `n` items with several sports and non-sports
    /// categories, arranged to create category runs (so the look-ahead swap path
    /// is exercised) without any RNG. Every id is unique so equivalence is exact.
    private func makeFixture(_ n: Int) -> [Stub] {
        let cats = ["basketball", "basketball", "economics", "football", "politics",
                    "baseball", "baseball", "baseball", "tech", "soccer", "hockey", "entertainment"]
        return (0..<n).map { Stub(id: $0, cat: cats[$0 % cats.count]) }
    }

    // MARK: - Item 1: byte-for-byte ordered identity vs the old algorithm

    func testByteForByteEquivalenceAcrossSizes() {
        for n in [0, 1, 2, 3, 4, 5, 10, 50, 200, 500] {
            let fixture = makeFixture(n)
            let new = FeedInterleave.byCategory(fixture, sportsCategories: sportsCats, category: category)
            let old = referenceInterleave(fixture, sportsCategories: sportsCats, category: category)
            XCTAssertEqual(new, old, "linear interleave must match the removeFirst algorithm byte-for-byte at n=\(n)")
        }
    }

    func testAllSportsInputReturnedUnchanged() {
        // No non-sports to interleave with → input preserved exactly (the old
        // `nonSports.isEmpty` guard). Even a long same-category run is untouched.
        let fixture = (0..<300).map { Stub(id: $0, cat: "basketball") }
        let new = FeedInterleave.byCategory(fixture, sportsCategories: sportsCats, category: category)
        XCTAssertEqual(new, fixture)
    }

    func testEmptyAndSingleAndPairPreserveOldBehavior() {
        XCTAssertEqual(FeedInterleave.byCategory([Stub](), sportsCategories: sportsCats, category: category), [])
        let one = [Stub(id: 1, cat: "economics")]
        XCTAssertEqual(FeedInterleave.byCategory(one, sportsCategories: sportsCats, category: category),
                       referenceInterleave(one, sportsCategories: sportsCats, category: category))
        let pair = [Stub(id: 1, cat: "basketball"), Stub(id: 2, cat: "economics")]
        XCTAssertEqual(FeedInterleave.byCategory(pair, sportsCategories: sportsCats, category: category),
                       referenceInterleave(pair, sportsCategories: sportsCats, category: category))
    }

    func testOutputIsAlwaysAPermutationOfInput() {
        for n in [3, 50, 200, 500] {
            let fixture = makeFixture(n)
            let out = FeedInterleave.byCategory(fixture, sportsCategories: sportsCats, category: category)
            XCTAssertEqual(out.count, fixture.count, "no card dropped or duplicated at n=\(n)")
            XCTAssertEqual(Set(out.map(\.id)), Set(fixture.map(\.id)), "same id set at n=\(n)")
        }
    }

    // MARK: - Item 1: operation-count proof of linear traversal (not timing)

    func testClassificationOperationsScaleLinearly() {
        var opCounts: [Int: Int] = [:]
        for n in [50, 200, 500] {
            let fixture = makeFixture(n)
            var ops = 0
            _ = FeedInterleave.byCategory(fixture, sportsCategories: sportsCats) { ops += 1; return $0.cat }
            opCounts[n] = ops
        }
        // Absolute linear bound: partition (n) + a bounded (≤ ~7) look-ahead per
        // emitted item. A quadratic (rescan-per-item) algorithm would blow past this.
        for (n, ops) in opCounts {
            XCTAssertLessThanOrEqual(ops, 10 * n, "≤10 classifications/item at n=\(n) — linear, not quadratic")
        }
        // Growth ratio: 10× the input → ~10× the ops, not ~100×.
        let ratio = Double(opCounts[500]!) / Double(opCounts[50]!)
        XCTAssertLessThan(ratio, 15, "op count grows ~linearly with input size (got \(ratio)×)")
    }

    /// Worst case for the look-ahead swap: one non-sports item plus a long run of
    /// identical-category sports, forcing the `== lastCategory` window scan on
    /// nearly every iteration. Still linear, and still a faithful permutation.
    func testSwapHeavyInputStaysLinearAndCorrect() {
        var fixture = [Stub(id: -1, cat: "economics")]
        fixture += (0..<499).map { Stub(id: $0, cat: "basketball") }
        var ops = 0
        let out = FeedInterleave.byCategory(fixture, sportsCategories: sportsCats) { ops += 1; return $0.cat }
        XCTAssertEqual(Set(out.map(\.id)), Set(fixture.map(\.id)))
        XCTAssertLessThanOrEqual(ops, 10 * fixture.count, "swap-heavy input still linear")
        XCTAssertEqual(out, referenceInterleave(fixture, sportsCategories: sportsCats, category: category),
                       "swap-heavy order still matches the old algorithm")
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
