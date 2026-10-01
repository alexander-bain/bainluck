import XCTest

/// #9648 — **swiping away two unrelated MLB games does not bury a Red Sox story,
/// in the same sitting or after the app is reopened.**
///
/// Before #9648 a left swipe on any sports card wrote a SPORT-wide penalty
/// (`baseball`) into the local interaction profile, so two dismissed
/// Braves/Phillies-style games quietly sank every baseball card — including the
/// team the reader actually follows. Source now scopes sports negatives to the
/// exact story (`DiscoverSportsNegativesExact9648Tests`); this journey is the
/// installed half, and it needs a REAL signed-in simulator because guest swipes
/// write nothing (#9644). It never injects credentials.
///
/// ## What makes this test able to fail, and what makes it skip
///
/// The Red Sox card seen BEFORE any swipe is the control. No Red Sox card in
/// supply ⇒ SKIP: absence afterwards would prove nothing. Fewer than two
/// unrelated MLB cards ⇒ SKIP: the treatment never happened. After the swipes
/// and after a cold relaunch the same scan depth (plus margin) must find a Red
/// Sox card again; if it does not AND none of the cards that sat beside it came
/// back either, the pool rotated and the run SKIPS rather than blaming ranking.
final class UnrelatedMLBSwipesKeepTheRedSoxStory9648Tests: XCTestCase {

    /// Every MLB club other than the one the journey protects. A card naming any
    /// of these and NOT naming the Red Sox is "unrelated".
    private static let otherClubs = [
        "Yankees", "Orioles", "Rays", "Blue Jays", "Guardians", "Tigers", "Royals",
        "Twins", "White Sox", "Astros", "Mariners", "Rangers", "Angels", "Athletics",
        "Braves", "Phillies", "Mets", "Marlins", "Nationals", "Cubs", "Brewers",
        "Cardinals", "Reds", "Pirates", "Dodgers", "Padres", "Giants", "Diamondbacks",
        "Rockies",
    ]
    /// The protected story. Red Sox by default (the #9648 specimen); an
    /// equivalent baseball control may be named with
    /// `TEST_RUNNER_BL_9648_PROTECTED` when the specimen is out of supply.
    private static let protected =
        ProcessInfo.processInfo.environment["BL_9648_PROTECTED"].flatMap { $0.isEmpty ? nil : $0 } ?? "Red Sox"
    private static let scanScreens = 14

    override func setUp() {
        super.setUp()
        continueAfterFailure = false
    }

    func testTwoUnrelatedMLBSwipesLeaveTheRedSoxCardAcrossARelaunch() throws {
        let app = UITestLaunch.launchApp()
        try XCTSkipUnless(
            try AReaderCanSwipeAndRefreshDiscoverTests.isSignedInForFeedback(in: app),
            "NOT WALKED: #9648 relevance needs a signed-in simulator; guest swipes write no profile (#9644)."
        )
        _ = try JourneyPrecondition.firstCard(in: app)
        JourneyPrecondition.settle(JourneyPrecondition.cards(in: app))

        // ═══ BEFORE: the control ═══
        let before = scan(app, label: "before")
        guard let redSoxBefore = before.redSox else {
            throw XCTSkip(
                "NOT WALKED (no BEFORE control): no card naming '\(Self.protected)' within \(Self.scanScreens) screens "
                + "of Discover on this account. Seen \(before.seen.count) cards, \(before.unrelated.count) unrelated MLB. "
                + "First 12: \(before.seen.prefix(12).map { $0.prefix(60) })"
            )
        }
        snap("9648-01-BEFORE-protected-visible")
        log("BEFORE protected '\(Self.protected)' at ordinal \(before.redSoxOrdinal ?? -1) of \(before.seen.count): \(redSoxBefore)")

        // ═══ SUPPLY, before anything is dismissed ═══
        // Two unrelated MLB games must exist before the first swipe, so a run
        // never leaves the account with one dismissal and no result.
        scrollToTop(app)
        let supply = scan(app, label: "supply", stopOnProtected: false)
        try XCTSkipIf(
            supply.unrelated.count < 2,
            "NOT WALKED (treatment out of supply): \(supply.unrelated.count) unrelated MLB game card(s) in "
            + "\(supply.seen.count) cards; nothing was dismissed. Unrelated: \(supply.unrelated.map { $0.prefix(60) })"
        )

        // ═══ TREATMENT: two unrelated MLB dismissals ═══
        var dismissed: [String] = []
        for n in 1...2 {
            scrollToTop(app)
            guard let victim = findAndRevealUnrelated(app, excluding: dismissed) else {
                throw XCTSkip(
                    "NOT WALKED: only \(dismissed.count) unrelated MLB card(s) could be reached and swiped; "
                    + "the treatment needs two. Unrelated seen BEFORE: \(before.unrelated.map { $0.prefix(60) })"
                )
            }
            let sig = Self.signature(of: victim)
            snap("9648-0\(n + 1)a-unrelated-\(n)-before-swipe")
            victim.swipeLeft()
            try XCTSkipUnless(
                waitGone(sig, in: app),
                "NOT WALKED: the left swipe on unrelated card \(n) did not remove it within 10s (#1773's subject, not #9648's)."
            )
            snap("9648-0\(n + 1)b-unrelated-\(n)-gone")
            log("dismissed unrelated \(n): \(sig)")
            dismissed.append(sig)
        }

        // ═══ AFTER, same sitting ═══
        scrollToTop(app)
        let after = scan(app, label: "after", extraScreens: 2)
        if after.redSox != nil { snap("9648-04-AFTER-protected-still-visible") }
        XCTAssertNotNil(
            after.redSox,
            "Two unrelated MLB swipes removed every '\(Self.protected)' card from Discover in the same sitting "
            + "(BEFORE ordinal \(before.redSoxOrdinal ?? -1); AFTER scanned \(after.seen.count) cards)."
        )
        log("AFTER red sox at ordinal \(after.redSoxOrdinal ?? -1) of \(after.seen.count)")

        // ═══ AFTER a cold relaunch on the same container ═══
        app.terminate()
        let relaunched = UITestLaunch.launchApp()
        try XCTSkipUnless(
            try AReaderCanSwipeAndRefreshDiscoverTests.isSignedInForFeedback(in: relaunched),
            "NOT WALKED: the account did not restore signed-in after relaunch."
        )
        _ = try JourneyPrecondition.firstCard(in: relaunched)
        JourneyPrecondition.settle(JourneyPrecondition.cards(in: relaunched))
        let relaunch = scan(relaunched, label: "relaunch", extraScreens: 2)
        if relaunch.redSox != nil { snap("9648-05-RELAUNCH-protected-still-visible") }

        let survivors = before.seen.filter { relaunch.seen.contains($0) }
        if relaunch.redSox == nil {
            try XCTSkipIf(
                survivors.count < 2,
                "NOT WALKED: after relaunch only \(survivors.count) of \(before.seen.count) BEFORE cards returned, "
                + "so the pool rotated and a missing '\(Self.protected)' card cannot be pinned on the swipes."
            )
        }
        XCTAssertNotNil(
            relaunch.redSox,
            "After a relaunch no '\(Self.protected)' card is in Discover, while \(survivors.count) of the BEFORE cards "
            + "came back — the two unrelated MLB swipes buried a relevant story (#9648)."
        )
        let resurrected = dismissed.filter { relaunch.seen.contains($0) }
        XCTAssertTrue(
            resurrected.isEmpty,
            "A dismissed unrelated MLB card came back after relaunch: \(resurrected.map { $0.prefix(80) })"
        )
        log("RELAUNCH red sox at ordinal \(relaunch.redSoxOrdinal ?? -1) of \(relaunch.seen.count); "
            + "BEFORE survivors \(survivors.count)/\(before.seen.count); dismissed resurrected \(resurrected.count)")
    }

    // MARK: - Scanning

    private struct Scan {
        var seen: [String] = []
        var redSox: String?
        var redSoxOrdinal: Int?
        var unrelated: [String] = []
    }

    /// Walk Discover top-down, recording every card in first-seen order. Stops
    /// on the screen where the Red Sox card is first REACHABLE so the frame taken
    /// next shows it.
    private func scan(_ app: XCUIApplication, label: String, extraScreens: Int = 0, stopOnProtected: Bool = true) -> Scan {
        var result = Scan()
        if topSignature == nil {
            topSignature = JourneyPrecondition.cards(in: app).allElementsBoundByIndex.first.map(Self.signature(of:))
        }
        for _ in 0..<(Self.scanScreens + extraScreens) {
            for card in JourneyPrecondition.cards(in: app).allElementsBoundByIndex where card.exists {
                let text = Self.fullText(of: card)
                let sig = Self.signature(of: card)
                guard !sig.isEmpty else { continue }
                if !result.seen.contains(sig) { result.seen.append(sig) }
                if Self.isRedSox(text) {
                    if result.redSox == nil {
                        log("\(label): red sox card kind=\(Self.isGame(card) ? "game" : "non-game") text=\(text.prefix(160))")
                        result.redSox = sig
                        result.redSoxOrdinal = result.seen.firstIndex(of: sig)
                    }
                    if stopOnProtected, JourneyPrecondition.isReachable(card, in: app) {
                        log("\(label): protected reachable, frame \(card.frame)")
                        logSeen(result, label: label)
                        return result
                    }
                } else if Self.isUnrelatedMLB(text), Self.isGame(card), !result.unrelated.contains(sig) {
                    result.unrelated.append(sig)
                }
            }
            if stopOnProtected, result.redSox != nil {
                // Seen in the tree but not yet in the band: lift it into view.
                if let card = JourneyPrecondition.cards(in: app).allElementsBoundByIndex
                    .first(where: { Self.signature(of: $0) == result.redSox }) {
                    let lift = JourneyPrecondition.liftNeeded(for: card, in: app)
                    if lift > 0 { JourneyPrecondition.liftContent(app, by: lift + 20) }
                    if JourneyPrecondition.isReachable(card, in: app) { logSeen(result, label: label); return result }
                }
            }
            app.swipeUp()
            Thread.sleep(forTimeInterval: 1.0)
        }
        logSeen(result, label: label)
        return result
    }

    private func logSeen(_ result: Scan, label: String) {
        for (i, sig) in result.seen.enumerated() {
            let tag = sig == result.redSox ? "PROTECTED" : (result.unrelated.contains(sig) ? "UNRELATED-MLB" : "-")
            log("\(label) #\(i) [\(tag)] \(sig.prefix(90))")
        }
    }

    private func findAndRevealUnrelated(_ app: XCUIApplication, excluding: [String]) -> XCUIElement? {
        for _ in 0..<Self.scanScreens {
            for card in JourneyPrecondition.cards(in: app).allElementsBoundByIndex where card.exists {
                let sig = Self.signature(of: card)
                guard !sig.isEmpty, !excluding.contains(sig) else { continue }
                let text = Self.fullText(of: card)
                guard Self.isUnrelatedMLB(text), !Self.isRedSox(text), Self.isGame(card) else { continue }
                let lift = JourneyPrecondition.liftNeeded(for: card, in: app)
                if lift > 0 { JourneyPrecondition.liftContent(app, by: lift + 20) }
                if card.frame.minY < 60 { continue }
                if JourneyPrecondition.isReachable(card, in: app) { return card }
            }
            app.swipeUp()
            Thread.sleep(forTimeInterval: 1.0)
        }
        return nil
    }

    private func waitGone(_ sig: String, in app: XCUIApplication) -> Bool {
        let deadline = Date().addingTimeInterval(10)
        while Date() < deadline {
            if !JourneyPrecondition.cards(in: app).allElementsBoundByIndex.contains(where: { Self.signature(of: $0) == sig }) {
                return true
            }
            Thread.sleep(forTimeInterval: 0.5)
        }
        return false
    }

    private var topSignature: String?

    /// Back to the top of the feed: re-tap Discover, then flick down until the
    /// first card this run saw is on screen again (at most 18 flicks).
    private func scrollToTop(_ app: XCUIApplication) {
        JourneyPrecondition.tabBar(of: app).buttons["Discover"].tap()
        Thread.sleep(forTimeInterval: 1.0)
        for _ in 0..<18 {
            let sigs = JourneyPrecondition.cards(in: app).allElementsBoundByIndex.prefix(3).map(Self.signature(of:))
            if let top = topSignature, sigs.contains(top) { break }
            app.swipeDown()
        }
        Thread.sleep(forTimeInterval: 1.0)
    }

    // MARK: - Recognition

    private static func fullText(of card: XCUIElement) -> String {
        ([card.label] + card.staticTexts.allElementsBoundByIndex.map { $0.label }).joined(separator: " | ")
    }

    private static func signature(of card: XCUIElement) -> String {
        card.staticTexts.allElementsBoundByIndex.prefix(6).map { $0.label }.joined(separator: "|")
    }

    /// A GAME card — the treatment is "unrelated MLB games", so futures boards
    /// naming a club are never swiped. Recognised by the game card's own labels
    /// (league chip + "vs"), not by `discover-card-event`: measured on DD0DC456
    /// 2026-10-01, the `SwipeToDismiss` wrapper's `discover-card` identifier
    /// replaces the inner one, so no descendant carries it.
    private static func isGame(_ card: XCUIElement) -> Bool {
        let labels = card.staticTexts.allElementsBoundByIndex.prefix(8).map { $0.label }
        return labels.contains("MLB") && labels.contains("vs")
    }

    private static func isRedSox(_ text: String) -> Bool { text.contains(protected) }

    private static func isUnrelatedMLB(_ text: String) -> Bool {
        guard !isRedSox(text) else { return false }
        // "Giants"/"Rangers"/"Cardinals" are also NFL/NHL clubs; require an MLB
        // marker for those so a hockey card is never the treatment.
        let ambiguous: Set<String> = ["Giants", "Rangers", "Cardinals", "Tigers"]
        let hit = otherClubs.first { text.contains($0) }
        guard let club = hit else { return false }
        if ambiguous.contains(club) { return text.contains("MLB") || text.contains("World Series") }
        return true
    }

    // MARK: - Evidence

    private func snap(_ name: String) {
        let a = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        a.name = name
        a.lifetime = .keepAlways
        add(a)
    }

    private func log(_ line: String) {
        XCTContext.runActivity(named: "9648: " + line) { _ in }
        print("9648-LOG " + line)
    }
}
