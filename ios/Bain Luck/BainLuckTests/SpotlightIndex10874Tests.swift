import XCTest
@testable import Bain_Luck

/// #10874 — the Spotlight index's contracts without Core Spotlight: what an
/// entry says, how long it lives, which account it belongs to, and the order
/// writes reach the index in. Each assertion names what it would catch.
@MainActor
final class SpotlightIndex10874Tests: XCTestCase {

    // MARK: - Fixtures

    private let t0 = Date(timeIntervalSince1970: 1_792_000_000) // Sat 2026-10-17 20:26:40Z
    private var clock = Date(timeIntervalSince1970: 1_792_000_000)
    private var suites: [String] = []

    override func tearDown() {
        for suite in suites { UserDefaults().removePersistentDomain(forName: suite) }
        suites = []
        super.tearDown()
    }

    private func defaults() throws -> UserDefaults {
        let name = "SpotlightIndex10874Tests.\(UUID().uuidString)"
        suites.append(name)
        return try XCTUnwrap(UserDefaults(suiteName: name))
    }

    private func makeIndex(_ client: FakeSpotlightClient, defaults: UserDefaults) -> SpotlightIndex10874 {
        SpotlightIndex10874(client: client, store: SpotlightStore10874(defaults: defaults), now: { [unowned self] in self.clock })
    }

    private func game(_ id: Int, _ away: String = "Yankees", _ home: String = "Red Sox",
                      start: String? = "2026-10-18T23:10:00Z") -> SpotlightSubject10874 {
        SpotlightSubject10874.game(id: id, away: away, home: home, sportKey: "baseball_mlb", commenceTime: start)!
    }

    private func market(_ id: Int, _ name: String = "Who will win the 2026 World Series?") -> SpotlightSubject10874 {
        SpotlightSubject10874.market(id: id, name: name, category: "politics")!
    }

    private func id(_ subject: SpotlightSubject10874) -> String { subject.identifier! }
    private let root = SpotlightIndexPlan10874.rootDomain

    // MARK: - What an entry says

    func testAGameIsItsMatchupCompetitionAndDayAndNothingElse() throws {
        let subject = game(15323950)
        XCTAssertEqual(subject.title, "Yankees at Red Sox")
        XCTAssertEqual(subject.competition, "MLB", "a raw sport key reached the index")
        XCTAssertEqual(subject.aliases, ["Yankees", "Red Sox", "MLB"])
        XCTAssertEqual(subject.identifier, "https://bainluck.com/events/15323950")
        let detail = SpotlightIndexPlan10874.detail(subject, locale: Locale(identifier: "en_US"),
                                                    timeZone: TimeZone(identifier: "America/New_York")!)
        XCTAssertEqual(detail, "MLB · Sun, Oct 18, 2026")
    }

    func testTheSameTeamsOnDifferentDaysAreDifferentEntriesTheReaderCanTellApart() {
        let first = game(1, start: "2026-10-18T23:10:00Z"), second = game(2, start: "2026-10-20T23:10:00Z")
        XCTAssertEqual(first.title, second.title)
        XCTAssertNotEqual(first.identifier, second.identifier, "two meetings collapsed into one entry")
        let en = Locale(identifier: "en_US"), utc = TimeZone(identifier: "UTC")!
        XCTAssertNotEqual(SpotlightIndexPlan10874.detail(first, locale: en, timeZone: utc),
                          SpotlightIndexPlan10874.detail(second, locale: en, timeZone: utc),
                          "nothing on the entry tells the two meetings apart")
    }

    func testAMarketIsItsNameAndCategoryWithNoDate() {
        let subject = market(65391342)
        XCTAssertEqual(subject.identifier, "https://bainluck.com/futures/65391342")
        XCTAssertEqual(subject.competition, "Politics")
        XCTAssertNil(subject.date)
        XCTAssertEqual(SpotlightIndexPlan10874.detail(subject), "Politics")
    }

    func testAHalfLoadedSubjectIndexesNothing() {
        XCTAssertNil(SpotlightSubject10874.game(id: 1, away: " ", home: "Red Sox", sportKey: nil, commenceTime: nil))
        XCTAssertNil(SpotlightSubject10874.game(id: 0, away: "A", home: "B", sportKey: nil, commenceTime: nil))
        XCTAssertNil(SpotlightSubject10874.market(id: 5, name: "", category: nil))
        XCTAssertNil(SpotlightSubject10874.market(id: -5, name: "A market", category: nil))
    }

    func testNoItemEverCarriesAProbabilityPriceOrScore() {
        let entries = [SpotlightEntry10874(subject: game(1), viewedAt: t0),
                       SpotlightEntry10874(subject: market(2, "Fed cuts in December?"), viewedAt: t0)]
        let items = SpotlightIndexPlan10874.items(entries, saved: [], scope: "guest", now: t0)
        XCTAssertEqual(items.count, 2)
        for item in items {
            for text in [item.title, item.detail] + item.keywords {
                XCTAssertFalse(text.contains("%"), "a cached percentage was advertised: \(text)")
                XCTAssertNil(text.range(of: #"\d+\s*[-–]\s*\d+"#, options: .regularExpression),
                             "a score was advertised: \(text)")
            }
        }
        let source = (try? String(contentsOf: Self.appDir.appendingPathComponent("Spotlight/SpotlightHooks10874.swift"),
                                  encoding: .utf8)) ?? ""
        let written = Set(source.split(separator: "\n").compactMap { line -> String? in
            let text = line.trimmingCharacters(in: .whitespaces)
            guard text.hasPrefix("attributes."), let name = text.dropFirst(11).split(separator: " ").first else { return nil }
            return String(name)
        })
        XCTAssertEqual(written, ["title", "contentDescription", "keywords"],
                       "the system item gained a field (a rating, imagery, a value, a start clock) beyond the stable description")
    }

    /// N1 (#10874): on the simulator Spotlight printed the game's `startDate`
    /// as "Sun 10:00 AM" under its title. A placeholder start has an unreal
    /// clock, so the system item carries no date at all; the day stays in the
    /// description, and nothing the reader sees names a time of day.
    func testAGameResultShowsItsDayButNoClock() throws {
        let entries = [SpotlightEntry10874(subject: game(1, start: "2026-10-18T17:00:00Z"), viewedAt: t0)]
        let item = try XCTUnwrap(SpotlightIndexPlan10874.items(entries, saved: [], scope: "guest", now: t0).first)
        let day = SpotlightIndexPlan10874.detail(game(1, start: "2026-10-18T17:00:00Z"))
        XCTAssertEqual(item.detail, day, "the game's day left the description")
        XCTAssertTrue(day.contains("2026"), "the description no longer names the day: \(day)")
        for text in [item.title, item.detail] + item.keywords {
            XCTAssertNil(text.range(of: #"\d{1,2}:\d{2}"#, options: .regularExpression), "a clock was advertised: \(text)")
            XCTAssertNil(text.range(of: #"\b(AM|PM)\b"#, options: .regularExpression), "a clock was advertised: \(text)")
        }
        #if canImport(CoreSpotlight)
        let attributes = SpotlightSystemIndexClient10874.searchableItem(item).attributeSet
        XCTAssertNil(attributes.startDate, "Spotlight will print this date as a clock under the title")
        XCTAssertNil(attributes.endDate)
        XCTAssertEqual(attributes.contentDescription, day)
        #endif
    }

    // MARK: - Opening a result

    func testATappedResultOpensExactlyItsCanonicalPage() {
        let action = "com.apple.corespotlightitem"
        for subject in [game(15323950), market(65391342)] {
            XCTAssertEqual(SpotlightActivation10874.url(activityType: action, actionType: action,
                                                         identifier: subject.identifier)?.absoluteString,
                           subject.identifier)
        }
    }

    func testAnythingThatIsNotExactlyOurIdentifierOpensNothing() {
        let action = "com.apple.corespotlightitem"
        let refused: [Any?] = [nil, 15323950, "", "15323950", "https://bainluck.com/events/0",
                               "https://bainluck.com/events/15323950?x=1", "https://bainluck.com/events/15323950/props",
                               "https://evil.example/events/15323950", "bainluck://events/15323950",
                               "https://bainluck.com/team/red-sox", "https://bainluck.com/events/abc"]
        for identifier in refused {
            XCTAssertNil(SpotlightActivation10874.url(activityType: action, actionType: action, identifier: identifier),
                         "opened something for \(String(describing: identifier))")
        }
        XCTAssertNil(SpotlightActivation10874.url(activityType: "com.bainluck.view-story", actionType: action,
                                                   identifier: game(1).identifier), "another activity type")
    }

    func testTheRootRoutesATappedResultThroughTheExistingRouter() throws {
        let hooks = try String(contentsOf: Self.appDir.appendingPathComponent("Spotlight/SpotlightHooks10874.swift"),
                               encoding: .utf8)
        XCTAssertTrue(hooks.contains(".onContinueUserActivity(CSSearchableItemActionType)"))
        XCTAssertTrue(hooks.contains("_ = navigation.handleURL(url)"), "a second router for Spotlight")
        let app = try String(contentsOf: Self.appDir.appendingPathComponent("Bain_LuckApp.swift"), encoding: .utf8)
        XCTAssertTrue(app.contains(".spotlight10874(userID: authManager.activeFeedUserId, pins: pinManager, navigation: navCoordinator)"),
                      "the root no longer installs the Spotlight lifecycle")
    }

    // MARK: - Retention

    private func viewed(_ subject: SpotlightSubject10874, ago seconds: TimeInterval) -> SpotlightEntry10874 {
        SpotlightEntry10874(subject: subject, viewedAt: t0.addingTimeInterval(-seconds))
    }

    func testRecentEntriesLiveFourteenDays() {
        let day: TimeInterval = 86_400
        let kept = SpotlightIndexPlan10874.prune(
            [viewed(game(1), ago: 13 * day + 3_000), viewed(game(2), ago: 14 * day), viewed(game(3), ago: 20 * day)],
            saved: [], now: t0)
        XCTAssertEqual(kept.map(\.subject.id), [1], "an entry outlived the 14-day window, or died inside it")
    }

    func testOnlyTheNewestTwentyFiveRecentEntriesAreKept() {
        let entries = (1...30).map { viewed(game($0), ago: TimeInterval($0) * 60) }
        let kept = SpotlightIndexPlan10874.prune(entries, saved: [], now: t0)
        XCTAssertEqual(kept.count, SpotlightIndexPlan10874.recentLimit)
        XCTAssertEqual(Set(kept.map(\.subject.id)), Set(1...25), "the limit kept the oldest, not the newest")
    }

    func testASavedEntryOutlivesTheRecentWindowAndTheLimitAndGoesWhenUnsaved() {
        let old = viewed(market(99), ago: 90 * 86_400)
        let neverViewed = SpotlightEntry10874(subject: game(98), viewedAt: nil)
        let crowd = (1...30).map { viewed(game($0), ago: TimeInterval($0)) }
        let saved: Set<StoryContinuationDestination> = [.futures(99), .event(98)]
        let kept = SpotlightIndexPlan10874.prune([old, neverViewed] + crowd, saved: saved, now: t0)
        XCTAssertTrue(kept.contains(old), "a saved market expired")
        XCTAssertTrue(kept.contains(neverViewed), "a saved, never-viewed game was dropped")
        XCTAssertEqual(kept.count, 27)
        // A saved entry viewed a moment ago must not use up a recent slot.
        let savedRecent = viewed(market(97), ago: 0)
        let withSavedRecent = SpotlightIndexPlan10874.prune([savedRecent] + crowd, saved: [.futures(97)], now: t0)
        XCTAssertEqual(withSavedRecent.count, SpotlightIndexPlan10874.recentLimit + 1, "a saved entry took a recent slot")
        let unsaved = SpotlightIndexPlan10874.prune([old, neverViewed], saved: [], now: t0)
        XCTAssertTrue(unsaved.isEmpty, "an unsaved entry outside the window stayed")
    }

    func testExpiryIsWrittenIntoTheItemSoSpotlightDropsItEvenIfTheAppNeverRuns() {
        let recent = viewed(game(1), ago: 3_600)
        let item = SpotlightIndexPlan10874.items([recent], saved: [], scope: "guest", now: t0)[0]
        XCTAssertEqual(item.expiration, recent.viewedAt!.addingTimeInterval(SpotlightIndexPlan10874.recentWindow))
        let saved = SpotlightIndexPlan10874.items([recent], saved: [.event(1)], scope: "guest", now: t0)[0]
        XCTAssertGreaterThan(saved.expiration, t0.addingTimeInterval(29 * 86_400))
        let laterSameDay = SpotlightIndexPlan10874.items([recent], saved: [.event(1)], scope: "guest",
                                                         now: t0.addingTimeInterval(60))[0]
        XCTAssertEqual(saved, laterSameDay, "a saved entry would be rewritten on every sync")
    }

    func testTheDiffWritesOnlyWhatChanged() {
        let a = SpotlightIndexPlan10874.items([viewed(game(1), ago: 60)], saved: [], scope: "guest", now: t0)[0]
        let b = SpotlightIndexPlan10874.items([viewed(game(2), ago: 60)], saved: [], scope: "guest", now: t0)[0]
        let renamed = SpotlightIndexPlan10874.items([viewed(game(1, "Mets"), ago: 60)], saved: [], scope: "guest", now: t0)[0]
        let unchanged = SpotlightIndexPlan10874.diff(applied: [a.identifier: a], desired: [a])
        XCTAssertTrue(unchanged.upserts.isEmpty && unchanged.deletes.isEmpty)
        let changed = SpotlightIndexPlan10874.diff(applied: [a.identifier: a], desired: [renamed, b])
        XCTAssertEqual(changed.upserts.map(\.title), ["Mets at Red Sox", "Yankees at Red Sox"])
        XCTAssertTrue(changed.deletes.isEmpty)
        let removed = SpotlightIndexPlan10874.diff(applied: [a.identifier: a, b.identifier: b], desired: [b])
        XCTAssertEqual(removed.deletes, [a.identifier])
    }

    func testScopesAreOnePerAccountAndCannotEscapeTheRoot() {
        XCTAssertEqual(SpotlightIndexPlan10874.scope(userID: nil), "guest")
        XCTAssertEqual(SpotlightIndexPlan10874.scope(userID: ""), "guest")
        XCTAssertEqual(SpotlightIndexPlan10874.scope(userID: "42"), "user-42")
        XCTAssertEqual(SpotlightIndexPlan10874.scope(userID: "a.b/c"), "user-a-b-c", "a dot would open a sub-domain")
        XCTAssertTrue(SpotlightIndexPlan10874.domain(scope: "user-42").hasPrefix(root + "."))
    }

    // MARK: - The indexer: add, update, delete, expiry

    func testBindingPurgesTheRootBeforeWritingAnything() async throws {
        let client = FakeSpotlightClient(), index = makeIndex(client, defaults: try defaults())
        await index.bind(userID: "42")?.value
        await index.savedChanged([], pinUserID: "42")?.value
        await index.recordViewed(game(1))?.value
        XCTAssertEqual(client.calls, [.purge(root), .index([id(game(1))])])
        XCTAssertEqual(Set(client.system.keys), [id(game(1))])
    }

    func testViewingAgainUpdatesAndUnsavedOldEntriesAreDeletedOnRefresh() async throws {
        let client = FakeSpotlightClient(), index = makeIndex(client, defaults: try defaults())
        await index.bind(userID: nil)?.value
        await index.savedChanged([], pinUserID: nil)?.value
        await index.recordViewed(game(1))?.value
        clock = clock.addingTimeInterval(86_400)
        await index.recordViewed(game(1, start: "2026-10-21T18:05:00Z"))?.value
        let rescheduled = SpotlightIndexPlan10874.detail(game(1, start: "2026-10-21T18:05:00Z"))
        XCTAssertNotEqual(rescheduled, SpotlightIndexPlan10874.detail(game(1)), "fixture: the two days must differ")
        XCTAssertEqual(client.system[id(game(1))]?.detail, rescheduled, "a rescheduled game kept its old day")
        clock = clock.addingTimeInterval(15 * 86_400)
        await index.refresh()?.value
        XCTAssertTrue(client.system.isEmpty, "an expired recent entry stayed in Spotlight")
        XCTAssertEqual(client.calls.last, .delete([id(game(1))]))
    }

    func testUnpinningANeverViewedSubjectRemovesIt() async throws {
        let client = FakeSpotlightClient(), index = makeIndex(client, defaults: try defaults())
        await index.bind(userID: "42")?.value
        await index.savedChanged([SavedPin(type: "future", value: 7)], pinUserID: "42")?.value
        await index.learnSaved([.futures(7): .described(market(7))], pinUserID: "42")?.value
        XCTAssertNotNil(client.system[id(market(7))], "a saved, described market was not indexed")
        await index.savedChanged([], pinUserID: "42")?.value
        XCTAssertNil(client.system[id(market(7))], "an unpinned, never-viewed market stayed in Spotlight")
    }

    func testAGoneAnswerRemovesTheEntryEvenIfItWasViewed() async throws {
        let client = FakeSpotlightClient(), index = makeIndex(client, defaults: try defaults())
        await index.bind(userID: "42")?.value
        await index.savedChanged([SavedPin(type: "event", value: 3)], pinUserID: "42")?.value
        await index.recordViewed(game(3))?.value
        await index.learnSaved([.event(3): .gone], pinUserID: "42")?.value
        XCTAssertTrue(client.system.isEmpty, "deleted content stayed searchable")
        XCTAssertTrue(index.entries.isEmpty)
    }

    func testMyStuffCannotDescribeAnUnsavedPin() async throws {
        let client = FakeSpotlightClient(), index = makeIndex(client, defaults: try defaults())
        await index.bind(userID: "42")?.value
        await index.savedChanged([SavedPin(type: "event", value: 3)], pinUserID: "42")?.value
        await index.learnSaved([.event(4): .described(game(4))], pinUserID: "42")?.value
        XCTAssertTrue(client.system.isEmpty, "an unsaved subject was indexed")
    }

    /// Between `bind` and the account's pins arriving, nothing counts as saved:
    /// a lookup landing in that window (a late one from the former account
    /// included) adds nothing, not even to disk.
    func testBeforeTheAccountsPinsArriveMyStuffAddsNothing() async throws {
        let client = FakeSpotlightClient(), index = makeIndex(client, defaults: try defaults())
        await index.bind(userID: "42")?.value
        await index.learnSaved([.event(4): .described(game(4))], pinUserID: "42")?.value
        XCTAssertTrue(index.entries.isEmpty, "a description was kept before the account's pins were known")
        await index.savedChanged([SavedPin(type: "event", value: 4)], pinUserID: "42")?.value
        XCTAssertTrue(client.system.isEmpty, "a pre-pins description surfaced once the pins arrived")
    }

    func testAViewedPagesDescriptionIsNotRewrittenByMyStuff() async throws {
        let client = FakeSpotlightClient(), index = makeIndex(client, defaults: try defaults())
        await index.bind(userID: "42")?.value
        await index.savedChanged([SavedPin(type: "future", value: 7)], pinUserID: "42")?.value
        await index.recordViewed(market(7, "Verified title"))?.value
        await index.learnSaved([.futures(7): .described(market(7, "Source title"))], pinUserID: "42")?.value
        XCTAssertEqual(client.system[id(market(7))]?.title, "Verified title", "the two sources took turns")
    }

    func testBeforeTheAccountsPinsArriveASavedOnlyDescriptionSurvivesOnDisk() async throws {
        let store = try defaults()
        let first = makeIndex(FakeSpotlightClient(), defaults: store)
        await first.bind(userID: "42")?.value
        await first.savedChanged([SavedPin(type: "future", value: 7)], pinUserID: "42")?.value
        await first.learnSaved([.futures(7): .described(market(7))], pinUserID: "42")?.value
        // Next launch: a view is recorded before PinManager's set arrives.
        let second = makeIndex(FakeSpotlightClient(), defaults: store)
        await second.bind(userID: "42")?.value
        await second.recordViewed(game(1))?.value
        XCTAssertTrue(second.entries.contains { $0.subject.id == 7 }, "pruned as unsaved before the pins were known")
    }

    func testAnEmptyPinSetStillCountsAsKnownSoAnUnpinnedDescriptionLeavesDisk() async throws {
        let store = try defaults()
        let first = makeIndex(FakeSpotlightClient(), defaults: store)
        await first.bind(userID: "42")?.value
        await first.savedChanged([SavedPin(type: "future", value: 7)], pinUserID: "42")?.value
        await first.learnSaved([.futures(7): .described(market(7))], pinUserID: "42")?.value
        // Unpinned elsewhere; this launch's pins arrive empty.
        let second = makeIndex(FakeSpotlightClient(), defaults: store)
        await second.bind(userID: "42")?.value
        await second.savedChanged([], pinUserID: "42")?.value
        await second.recordViewed(game(1))?.value
        XCTAssertFalse(second.entries.contains { $0.subject.id == 7 }, "an empty pin set was treated as not yet known")
    }

    // MARK: - Accounts

    func testAPinSetOrDescriptionFromAnotherAccountIsRefused() async throws {
        let client = FakeSpotlightClient(), index = makeIndex(client, defaults: try defaults())
        await index.bind(userID: "B")?.value
        XCTAssertNil(index.savedChanged([SavedPin(type: "future", value: 7)], pinUserID: "A"), "A's pins accepted under B")
        XCTAssertNil(index.learnSaved([.futures(7): .described(market(7))], pinUserID: "A"))
        XCTAssertTrue(index.saved.isEmpty)
        XCTAssertTrue(client.system.isEmpty)
    }

    func testSwitchingAccountsRemovesTheFormerAccountsEntriesEverywhere() async throws {
        let store = try defaults()
        let client = FakeSpotlightClient(), index = makeIndex(client, defaults: store)
        await index.bind(userID: "A")?.value
        await index.savedChanged([SavedPin(type: "event", value: 1)], pinUserID: "A")?.value
        await index.recordViewed(game(1))?.value
        await index.recordViewed(market(2))?.value
        XCTAssertEqual(client.system.count, 2)
        await index.bind(userID: "B")?.value
        XCTAssertTrue(client.system.isEmpty, "A's saved/recent entries survived the switch")
        XCTAssertNil(store.data(forKey: SpotlightStore10874.keyPrefix + "user-A"), "A's descriptions stayed on disk")
        await index.bind(userID: nil)?.value
        XCTAssertNil(store.data(forKey: SpotlightStore10874.keyPrefix + "user-B"))
        XCTAssertEqual(client.calls.filter { $0 == .purge(root) }.count, 3)
    }

    func testAnAccountChangeWhileTheAppWasClosedStillPurgesTheFormerAccount() async throws {
        let store = try defaults()
        let first = makeIndex(FakeSpotlightClient(), defaults: store)
        await first.bind(userID: "A")?.value
        await first.recordViewed(game(1))?.value
        let client = FakeSpotlightClient()
        client.system[id(game(1))] = SpotlightIndexItem10874(identifier: id(game(1)), domain: root + ".user-A",
                                                             title: "", detail: "", keywords: [],
                                                             expiration: t0)
        let second = makeIndex(client, defaults: store)
        await second.bind(userID: "B")?.value
        XCTAssertTrue(client.system.isEmpty)
        XCTAssertNil(store.data(forKey: SpotlightStore10874.keyPrefix + "user-A"), "A's descriptions outlived a relaunch as B")
        XCTAssertEqual(store.string(forKey: SpotlightStore10874.lastScopeKey), "user-B")
    }

    func testTheSameAccountKeepsItsEntriesAcrossLaunches() async throws {
        let store = try defaults()
        let first = makeIndex(FakeSpotlightClient(), defaults: store)
        await first.bind(userID: "A")?.value
        await first.recordViewed(game(1))?.value
        let client = FakeSpotlightClient(), second = makeIndex(client, defaults: store)
        await second.bind(userID: "A")?.value
        XCTAssertEqual(second.entries.map(\.subject), [game(1)])
        XCTAssertEqual(client.calls, [.purge(root), .index([id(game(1))])], "a relaunch did not rebuild from disk")
    }

    // MARK: - Late completions

    /// The old account's write was already in flight when the account changed.
    /// It completes AFTER the switch; the purge queued behind it must still
    /// run after it, so nothing of the old account survives.
    func testAWriteInFlightAcrossASwitchCannotOutliveIt() async throws {
        let client = FakeSpotlightClient(), index = makeIndex(client, defaults: try defaults())
        await index.bind(userID: "A")?.value
        await index.savedChanged([], pinUserID: "A")?.value
        client.holdNextIndex = true
        let write = index.recordViewed(game(1))
        try await client.waitUntilHolding()
        let switched = index.bind(userID: "B")
        client.release()
        await write?.value
        await switched?.value
        XCTAssertEqual(client.calls, [.purge(root), .index([id(game(1))]), .purge(root)])
        XCTAssertTrue(client.system.isEmpty, "A's late write resurrected A's entry under B")
        XCTAssertTrue(index.applied.isEmpty, "the index believes A's entry is still written")
    }

    /// The old account's write had been queued but had not started when the
    /// account changed. A pass reads the state when it runs, after the new
    /// account's purge, so nothing of the old account is written.
    func testAWriteQueuedButNotStartedForTheFormerAccountWritesNothingOfIt() async throws {
        let client = FakeSpotlightClient(), index = makeIndex(client, defaults: try defaults())
        await index.bind(userID: "A")?.value
        await index.savedChanged([], pinUserID: "A")?.value
        client.holdNextIndex = true
        let first = index.recordViewed(game(1))
        try await client.waitUntilHolding()
        let second = index.recordViewed(game(2))
        let switched = index.bind(userID: "B")
        client.release()
        await first?.value
        await second?.value
        await switched?.value
        XCTAssertFalse(client.calls.contains { if case .index(let ids) = $0 { return ids.contains(id(game(2))) }; return false },
                       "a queued write of the former account ran after the switch")
        XCTAssertTrue(client.system.isEmpty)
    }

    /// A purge for the former account was still running when the account
    /// changed: it is not the new account's purge.
    func testAPurgeInFlightAcrossASwitchIsFollowedByTheNewAccountsOwn() async throws {
        let store = try defaults()
        let seed = makeIndex(FakeSpotlightClient(), defaults: store)
        await seed.bind(userID: "B")?.value
        await seed.recordViewed(game(2))?.value
        store.set("user-A", forKey: SpotlightStore10874.lastScopeKey)
        let client = FakeSpotlightClient(), index = makeIndex(client, defaults: store)
        client.holdNextPurge = true
        let first = index.bind(userID: "A")
        try await client.waitUntilHolding()
        let switched = index.bind(userID: "B")
        client.release()
        await first?.value
        await switched?.value
        XCTAssertEqual(client.calls.filter { $0 == .purge(root) }.count, 2, "the former account's purge stood in for the new one's")
        XCTAssertFalse(client.system.isEmpty)
        XCTAssertTrue(client.system.values.allSatisfy { $0.domain == root + ".user-B" },
                      "an item was filed under the former account's domain")
    }

    func testAFailedWriteMakesTheNextPassAFullRebuild() async throws {
        let client = FakeSpotlightClient(), index = makeIndex(client, defaults: try defaults())
        await index.bind(userID: nil)?.value
        await index.savedChanged([], pinUserID: nil)?.value
        client.failNext = true
        await index.recordViewed(game(1))?.value
        XCTAssertTrue(client.system.isEmpty)
        await index.refresh()?.value
        XCTAssertEqual(Array(client.calls.suffix(2)), [.purge(root), .index([id(game(1))])],
                       "a failed write was trusted, or never retried")
        XCTAssertNotNil(client.system[id(game(1))])
    }

    // MARK: - Hooks stay where a reader actually looked

    func testViewsRecordOnlyTheirOwnLoadedSubject() throws {
        let event = try String(contentsOf: Self.appDir.appendingPathComponent("Views/EventDetailView.swift"), encoding: .utf8)
        XCTAssertTrue(event.contains("event.id == eventId ? SpotlightSubject10874.game("),
                      "the event page could record a subject other than its own")
        let futures = try String(contentsOf: Self.appDir.appendingPathComponent("Views/FuturesDetailView.swift"), encoding: .utf8)
        XCTAssertTrue(futures.contains("market.id == marketId ? SpotlightSubject10874.market("))
        let hooks = try String(contentsOf: Self.appDir.appendingPathComponent("Spotlight/SpotlightHooks10874.swift"), encoding: .utf8)
        XCTAssertTrue(hooks.contains("try? await Task.sleep(for: .seconds(SpotlightIndexPlan10874.viewDwell))"))
        XCTAssertTrue(hooks.contains("guard SpotlightIndex10874.isEnabledOnThisPlatform, let subject, scenePhase == .active"),
                      "a page in the background or still loading would count as viewed")
        let prefetchers = ["Services/APIClient.swift", "ViewModels/EventDetailViewModel.swift",
                           "ViewModels/FuturesDetailViewModel.swift", "ViewModels/SavedPinContentViewModel.swift"]
        for path in prefetchers {
            let source = try String(contentsOf: Self.appDir.appendingPathComponent(path), encoding: .utf8)
            XCTAssertFalse(source.contains("recordViewed"), "\(path) records a view from a request, not a page")
        }
    }

    func testCopyUsesTheSubjectNotQuestion() throws {
        for file in ["SpotlightIndexPlan10874.swift", "SpotlightHooks10874.swift", "SpotlightIndex10874.swift"] {
            let source = try String(contentsOf: Self.appDir.appendingPathComponent("Spotlight/\(file)"), encoding: .utf8)
            let quoted = source.split(separator: "\"").enumerated().filter { $0.offset % 2 == 1 }.map(\.element)
            XCTAssertFalse(quoted.contains { $0.localizedCaseInsensitiveContains("question") },
                           "\"question\" is not the product's noun (#10877)")
        }
    }

    // MARK: - Paths

    private static var appDir: URL {
        URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Bain Luck")
    }
}

/// Records calls in order and keeps a model of what the system index holds.
@MainActor
private final class FakeSpotlightClient: SpotlightIndexClient10874 {
    enum Call: Equatable {
        case index([String])
        case delete([String])
        case purge(String)
    }

    struct Failure: Error {}

    var calls: [Call] = []
    var system: [String: SpotlightIndexItem10874] = [:]
    var holdNextIndex = false
    var holdNextPurge = false
    var failNext = false
    private var held: CheckedContinuation<Void, Never>?

    func index(_ items: [SpotlightIndexItem10874]) async throws {
        calls.append(.index(items.map(\.identifier)))
        if holdNextIndex {
            holdNextIndex = false
            await withCheckedContinuation { held = $0 }
        }
        if failNext {
            failNext = false
            throw Failure()
        }
        for item in items { system[item.identifier] = item }
    }

    func delete(identifiers: [String]) async throws {
        calls.append(.delete(identifiers))
        for identifier in identifiers { system[identifier] = nil }
    }

    func deleteDomain(_ domain: String) async throws {
        calls.append(.purge(domain))
        if holdNextPurge {
            holdNextPurge = false
            await withCheckedContinuation { held = $0 }
        }
        system = system.filter { $0.value.domain != domain && !$0.value.domain.hasPrefix(domain + ".") }
    }

    func waitUntilHolding() async throws {
        for _ in 0..<1_000 where held == nil { await Task.yield() }
        if held == nil { throw Failure() }
    }

    func release() {
        held?.resume()
        held = nil
    }
}
