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

    // MARK: - The fixed-deck arm (reviewed DEBUG seam)

    /// The reviewed deck's role ids (packet `fixture-manifest.json`).
    private enum Role {
        static let redSox = "event-15317515"
        static let mariners = "event-15316875"
        static let cubsMarlins = "event-15317023"
        static let dodgersPadres = "event-15316961"
        static let hockey = "futures-52755659"
        static let health = "futures-13792418"
        static let politics = "futures-112996"
        static let initialDismissal = "futures-27594131"
        static let fixtureSHA = "7363267d966cd5f040a7f92765f46c811a4a543b5cad94ac4c07019013dc93e9"
        static let profileKey = "discover_interaction_profile_native_v2"
        static let legacyProfileKey = "discover_interaction_profile_native_v1"
        static let dismissKey = "discover_dismissed_v2"
        static let legacyDismissKey = "discover_dismissed"
    }

    /// The same journey on the pinned 36-card deck: CONTROL (seeded) → TREATMENT
    /// (re-seeded to the identical state; swipe ONLY Cubs–Marlins and
    /// Dodgers–Padres) → COLD RELAUNCH (no seed). Supply cannot be missing here,
    /// so nothing in this arm SKIPS for supply: a missing input, an unseeded
    /// store or a signed-out account is a FAILURE of the harness, said by name.
    ///
    /// Armed only when the harness copied the deck and seed into the app's
    /// container and named them (`TEST_RUNNER_BL_9648_FIXED_FEED`,
    /// `TEST_RUNNER_BL_9648_FIXED_SEED`, optional `TEST_RUNNER_BL_9648_FIXED_ANCHOR`).
    func testFixedDeckTwoUnrelatedMLBSwipesKeepTheProtectedStoriesAcrossARelaunch() throws {
        let env = ProcessInfo.processInfo.environment
        guard let feed = env["BL_9648_FIXED_FEED"], !feed.isEmpty,
              let seed = env["BL_9648_FIXED_SEED"], !seed.isEmpty
        else {
            throw XCTSkip("NOT ARMED: the fixed-deck arm runs only when the harness names the deck and seed it placed in the container.")
        }
        let anchor = env["BL_9648_FIXED_ANCHOR"].flatMap { $0.isEmpty ? nil : $0 }
            ?? String(Int(Date().timeIntervalSince1970))
        let fixedArgs = ["-launch_fixed_feed", feed, "-launch_fixed_feed_anchor", anchor]
        let seedArgs = ["-launch_fixed_feed_seed", seed]
        log("FIXED run anchor \(anchor) feed \(feed) seed \(seed)")

        // ═══ A. CONTROL ═══
        var app = UITestLaunch.launchApp(extra: fixedArgs + seedArgs)
        try requireSignedIn(app, arm: "control")
        let control = try receipt(app, arm: "control", seeded: true, anchor: anchor)
        let roles = [Role.redSox, Role.mariners, Role.cubsMarlins, Role.dodgersPadres, Role.hockey, Role.health, Role.politics]
        let controlIds = control.renderedIds
        let missing = roles.filter { !controlIds.contains($0) }
        XCTAssertTrue(missing.isEmpty, "HARNESS: role cards not rendered on the fixed deck: \(missing)")
        XCTAssertFalse(controlIds.contains(Role.initialDismissal), "the seeded exact dismissal must stay hidden")
        log("CONTROL served \(control.served) eligible \(control.eligible) drawn \(control.drawn)")
        logRendered(control, arm: "control")
        for name in ["Red Sox", "Mariners"] { reveal(name, in: app, snapAs: "9648F-01-CONTROL-\(name)") }
        app.terminate()

        // ═══ B. TREATMENT ═══
        app = UITestLaunch.launchApp(extra: fixedArgs + seedArgs)
        try requireSignedIn(app, arm: "treatment")
        let before = try receipt(app, arm: "treatment-before", seeded: true, anchor: anchor)
        XCTAssertEqual(before.stores, control.stores, "control and treatment must start from byte-identical stores")
        XCTAssertEqual(before.renderedIds, controlIds, "control and treatment must start from the same rendered deck")
        snap("9648F-02-TREATMENT-before")
        let armStart = Date().timeIntervalSince1970
        topSignature = nil
        for (n, teams) in [["Cubs", "Marlins"], ["Dodgers", "Padres"]].enumerated() {
            scrollToTop(app)
            guard let card = findAndReveal(app, naming: teams) else {
                return XCTFail("HARNESS: the \(teams.joined(separator: "–")) game card could not be reached on the fixed deck")
            }
            let sig = Self.signature(of: card)
            snap("9648F-03\(n == 0 ? "a" : "c")-swipe-\(teams[0])")
            card.swipeLeft()
            XCTAssertTrue(waitGone(sig, in: app), "the left swipe on \(teams.joined(separator: "–")) did not remove it")
            XCTAssertTrue(app.navigationBars["Discover"].exists, "a swipe must not open the game page")
            snap("9648F-03\(n == 0 ? "b" : "d")-gone-\(teams[0])")
        }
        let after = try receipt(app, arm: "treatment-after", seeded: true, anchor: anchor)
        let armEnd = Date().timeIntervalSince1970
        XCTAssertEqual(
            Set(after.renderedIds), Set(before.renderedIds).subtracting([Role.cubsMarlins, Role.dodgersPadres]),
            "exactly the two swiped cards leave the deck")
        for key in [Role.profileKey, Role.legacyProfileKey, Role.legacyDismissKey] {
            XCTAssertEqual(after.stores[key], before.stores[key], "\(key) must stay byte-equal through two sports swipes")
        }
        let dismissBefore = try decodeDismiss(before.stores[Role.dismissKey])
        let dismissAfter = try decodeDismiss(after.stores[Role.dismissKey])
        XCTAssertEqual(Set(dismissAfter.keys), Set(dismissBefore.keys).union([Role.cubsMarlins, Role.dodgersPadres]),
                       "the dismiss map gains ONLY the two swiped games")
        XCTAssertEqual(dismissAfter[Role.initialDismissal], dismissBefore[Role.initialDismissal],
                       "the initial exact dismissal keeps its timestamp")
        for key in [Role.cubsMarlins, Role.dodgersPadres] {
            let at = dismissAfter[key] ?? 0
            XCTAssertTrue(at >= armStart - 1 && at <= armEnd + 1, "\(key) dismissed at \(at), outside the run interval \(armStart)–\(armEnd)")
        }
        for id in [Role.redSox, Role.mariners, Role.hockey] {
            XCTAssertGreaterThan(after.adjustment(id) ?? 0, 0, "\(id) must keep its positive profile adjustment")
        }
        XCTAssertLessThan(after.adjustment(Role.politics) ?? 0, 0, "the non-sports negative control keeps its penalty")
        logRendered(after, arm: "treatment-after")
        for name in ["Red Sox", "Mariners"] { reveal(name, in: app, snapAs: "9648F-04-TREATMENT-\(name)") }
        app.terminate()

        // ═══ C. COLD RELAUNCH — same container, same deck, NO seed ═══
        app = UITestLaunch.launchApp(extra: fixedArgs)
        try requireSignedIn(app, arm: "relaunch")
        let relaunch = try receipt(app, arm: "relaunch", seeded: false, anchor: nil)
        XCTAssertEqual(relaunch.stores, after.stores, "the cold relaunch must read the treatment's stores unchanged")
        XCTAssertEqual(Set(relaunch.renderedIds), Set(after.renderedIds), "same deck after relaunch")
        for id in [Role.redSox, Role.mariners, Role.hockey, Role.health, Role.politics] {
            XCTAssertTrue(relaunch.renderedIds.contains(id), "\(id) missing after relaunch")
        }
        XCTAssertGreaterThan(relaunch.adjustment(Role.redSox) ?? 0, 0)
        XCTAssertGreaterThan(relaunch.adjustment(Role.mariners) ?? 0, 0)
        logRendered(relaunch, arm: "relaunch")
        for name in ["Red Sox", "Mariners"] { reveal(name, in: app, snapAs: "9648F-05-RELAUNCH-\(name)") }
    }

    private struct Receipt {
        let raw: String
        let served: Int
        let eligible: Int
        let drawn: Int
        let rendered: [[String: Any]]
        let stores: [String: String]
        var renderedIds: [String] { rendered.compactMap { $0["id"] as? String } }
        func adjustment(_ id: String) -> Double? {
            rendered.first { ($0["id"] as? String) == id }?["adjustment"] as? Double
        }
    }

    /// A signed-out or unresolved account is a harness failure here, not a skip.
    private func requireSignedIn(_ app: XCUIApplication, arm: String) throws {
        let signedIn = try AReaderCanSwipeAndRefreshDiscoverTests.isSignedInForFeedback(in: app)
        if !signedIn { XCTFail("HARNESS (\(arm)): the restored account is signed OUT; guest swipes write nothing (#9644).") }
        try XCTSkipUnless(signedIn, "stopped: \(arm) is not signed in")
    }

    /// Reads the app's own read-only receipt once the deck is served to the
    /// signed-in principal, and checks the launch's fixture and seed identity.
    private func receipt(_ app: XCUIApplication, arm: String, seeded: Bool, anchor: String?) throws -> Receipt {
        let element = app.descendants(matching: .any)["discover-fixed-feed-receipt"]
        let deadline = Date().addingTimeInterval(30)
        var last = ""
        while Date() < deadline {
            if element.exists, let text = element.value as? String, !text.isEmpty {
                last = text
                if let body = try? JSONSerialization.jsonObject(with: Data(text.utf8)) as? [String: Any],
                   body["signed_in"] as? Bool == true, (body["served"] as? Int ?? 0) > 0,
                   !((body["rendered"] as? [Any]) ?? []).isEmpty {
                    let fixture = body["fixture"] as? [String: Any] ?? [:]
                    let seed = body["seed"] as? [String: Any] ?? [:]
                    XCTAssertNil(fixture["failure"], "HARNESS (\(arm)): \(fixture["failure"] ?? "")")
                    XCTAssertEqual(fixture["sha256"] as? String, Role.fixtureSHA, "HARNESS (\(arm)): not the reviewed deck")
                    XCTAssertEqual(fixture["cards"] as? Int, 36)
                    XCTAssertEqual(seed["state"] as? String, seeded ? "seeded" : "not_requested", "HARNESS (\(arm)): seed state")
                    if let anchor, let value = seed["anchor"] as? Double {
                        XCTAssertEqual(value, Double(anchor) ?? -1, "HARNESS (\(arm)): seed anchor")
                    }
                    log("RECEIPT \(arm) " + text)
                    let r = Receipt(
                        raw: text,
                        served: body["served"] as? Int ?? 0,
                        eligible: body["eligible"] as? Int ?? 0,
                        drawn: body["drawn"] as? Int ?? 0,
                        rendered: body["rendered"] as? [[String: Any]] ?? [],
                        stores: body["stores"] as? [String: String] ?? [:])
                    let a = XCTAttachment(string: text)
                    a.name = "9648F-receipt-\(arm).json"
                    a.lifetime = .keepAlways
                    add(a)
                    return r
                }
            }
            Thread.sleep(forTimeInterval: 0.5)
        }
        XCTFail("HARNESS (\(arm)): no signed-in fixed-feed receipt within 30 s. Last: \(last.prefix(400))")
        throw XCTSkip("stopped: no receipt for \(arm)")
    }

    private func decodeDismiss(_ text: String?) throws -> [String: Double] {
        guard let text, text != "null" else { return [:] }
        return try XCTUnwrap(try JSONSerialization.jsonObject(with: Data(text.utf8)) as? [String: Double])
    }

    private func logRendered(_ r: Receipt, arm: String) {
        for (i, card) in r.rendered.enumerated() {
            log("\(arm) #\(i) \(card["id"] ?? "") \(card["category"] ?? "") score \(card["score"] ?? "") adj \(card["adjustment"] ?? "")")
        }
    }

    private func findAndReveal(_ app: XCUIApplication, naming teams: [String]) -> XCUIElement? {
        let isTarget: (XCUIElement) -> Bool = { card in
            let text = Self.fullText(of: card)
            return teams.allSatisfy { text.contains($0) } && Self.isGame(card)
        }
        for _ in 0..<Self.scanScreens {
            if let card = bringIntoBand(in: app, where: isTarget) {
                log("find \(teams[0]): reachable frame=\(card.frame) text=\(Self.fullText(of: card).prefix(160))")
                return card
            }
            app.swipeUp()
            Thread.sleep(forTimeInterval: 1.0)
        }
        return nil
    }

    /// Lifts the matching card into the reachable band in bounded steps,
    /// RE-FINDING it after every lift. Two measured traps, run 2 and run 3 on
    /// DD0DC456: one `liftContent` travels at most ~357 pt, and the Cubs–Marlins
    /// card at y 978 needed 548, so a single lift left it under the tab bar and
    /// the next `swipeUp` flung it off the top; and an `allElementsBoundByIndex`
    /// element is bound to its INDEX, so after a lift re-materialises the lazy
    /// list "Element at index 6" can name nothing and the next `frame` read fails
    /// the test. Returns nil when no card matches or it sits above the band.
    private func bringIntoBand(in app: XCUIApplication, where isTarget: (XCUIElement) -> Bool) -> XCUIElement? {
        for _ in 0..<5 {
            guard let card = JourneyPrecondition.cards(in: app).allElementsBoundByIndex
                .first(where: { $0.exists && isTarget($0) })
            else { return nil }
            if card.frame.minY < 60 { return nil }
            if JourneyPrecondition.isReachable(card, in: app) { return card }
            let lift = JourneyPrecondition.liftNeeded(for: card, in: app)
            guard lift > 0 else { return nil }
            JourneyPrecondition.liftContent(app, by: lift + 20)
            Thread.sleep(forTimeInterval: 0.5)
        }
        return nil
    }

    /// Scrolls the named card into the reachable band and photographs it; a
    /// card that cannot be reached is a failure on a deck that contains it.
    private func reveal(_ name: String, in app: XCUIApplication, snapAs: String) {
        topSignature = nil
        scrollToTop(app)
        for _ in 0..<Self.scanScreens {
            if bringIntoBand(in: app, where: { Self.fullText(of: $0).contains(name) && Self.isGame($0) }) != nil {
                snap(snapAs)
                return
            }
            app.swipeUp()
            Thread.sleep(forTimeInterval: 1.0)
        }
        XCTFail("the \(name) game card is on the fixed deck but could not be reached on screen")
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
