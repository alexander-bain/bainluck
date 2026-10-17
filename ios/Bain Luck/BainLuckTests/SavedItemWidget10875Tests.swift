import XCTest
@testable import Bain_Luck

/// #10875 — the saved-item widget's contracts, without WidgetKit: whose saved
/// items the widget may show, what one instance shows when the account, the
/// saved set or the network changes under it, and what it says about a game or
/// market. Each assertion's message names the defect it would catch.
@MainActor
final class SavedItemWidget10875Tests: XCTestCase {

    private let t0 = Date(timeIntervalSince1970: 1_792_000_000) // 2026-10-17T20:26:40Z
    private var suites: [String] = []

    override func tearDown() {
        for suite in suites { UserDefaults().removePersistentDomain(forName: suite) }
        suites = []
        super.tearDown()
    }

    private func defaults() throws -> UserDefaults {
        let name = "SavedItemWidget10875Tests.\(UUID().uuidString)"
        suites.append(name)
        return try XCTUnwrap(UserDefaults(suiteName: name))
    }

    private func iso(_ date: Date) -> String {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f.string(from: date)
    }

    private func game(_ id: Int) -> SavedWidgetSubject10875 { .init(kind: .game, id: id) }
    private func market(_ id: Int) -> SavedWidgetSubject10875 { .init(kind: .market, id: id) }

    // MARK: - Scope: two accounts are told apart without the id

    func testScopeTellsAccountsApartWithoutCarryingTheID() {
        let a = SavedWidgetBridge10875.scope(userID: "4821")
        let b = SavedWidgetBridge10875.scope(userID: "4822")
        XCTAssertEqual(SavedWidgetBridge10875.scope(userID: nil), "guest", "signed out must be the guest scope")
        XCTAssertEqual(SavedWidgetBridge10875.scope(userID: ""), "guest", "an empty id must not mint an account scope")
        XCTAssertNotEqual(a, b, "two accounts share a scope, so one would read the other's widget choices")
        XCTAssertEqual(a, SavedWidgetBridge10875.scope(userID: "4821"), "the scope is not stable across launches")
        XCTAssertTrue(a.hasPrefix("account."), "an account scope lost its prefix")
        XCTAssertFalse(a.contains("4821"), "the raw account id reached the shared container")
    }

    // MARK: - The bridge store

    func testStoreWritesOnlyChangesAndRejectsWhatThisAppDidNotWrite() throws {
        let d = try defaults()
        let store = SavedWidgetBridgeStore10875(defaults: d)
        XCTAssertNil(store.read(), "an empty container must read as unknown, not as an empty saved set")
        let snap = SavedWidgetSnapshot10875(scope: "guest", subjects: [market(9), game(3), game(1), game(3)], pinsConfirmed: true)
        XCTAssertEqual(snap.subjects, [game(1), game(3), market(9)], "order must not depend on Set iteration, or every launch rewrites")
        XCTAssertTrue(store.write(snap), "a first write must report a change so the app asks for a reload")
        XCTAssertFalse(store.write(snap), "an unchanged snapshot must not trigger another reload")
        XCTAssertEqual(store.read(), snap)

        d.set(Data("{\"version\":2,\"scope\":\"guest\",\"subjects\":[],\"pinsConfirmed\":true}".utf8),
              forKey: SavedWidgetBridge10875.storageKey)
        XCTAssertNil(store.read(), "a future version's snapshot must not be read as this one")
        d.set(Data("{\"version\":1,\"scope\":\"user.4821\",\"subjects\":[],\"pinsConfirmed\":true}".utf8),
              forKey: SavedWidgetBridge10875.storageKey)
        XCTAssertNil(store.read(), "a scope this app never mints (a raw id) must be refused")
        // The bound is the server's 25 per kind (`routes/user.py`), which an
        // account's server set can reach; the device's add limit is not it.
        let full = SavedWidgetSnapshot10875(scope: "guest", subjects: (1...25).map(game) + (1...25).map(market),
                                            pinsConfirmed: true)
        XCTAssertTrue(store.write(full))
        XCTAssertEqual(store.read(), full, "a full server set of 25 games and 25 markets was refused by the widget's reader")
        let many = (1...26).map { "{\"kind\":\"game\",\"id\":\($0)}" }.joined(separator: ",")
        d.set(Data("{\"version\":1,\"scope\":\"guest\",\"subjects\":[\(many)],\"pinsConfirmed\":true}".utf8),
              forKey: SavedWidgetBridge10875.storageKey)
        XCTAssertNil(store.read(), "more of one kind than the server keeps is not a snapshot this app wrote")
    }

    func testSelectionStatusAgainstTheCurrentSavedSet() {
        let snap = SavedWidgetSnapshot10875(scope: "account.aa", subjects: [game(1)], pinsConfirmed: true)
        XCTAssertEqual(SavedWidgetSelectionStatus10875.of(scope: "account.aa", subject: game(1), in: snap), .saved)
        XCTAssertEqual(SavedWidgetSelectionStatus10875.of(scope: "account.aa", subject: game(2), in: snap), .removed,
                       "an unpinned item still read as saved")
        XCTAssertEqual(SavedWidgetSelectionStatus10875.of(scope: "account.bb", subject: game(1), in: snap), .otherAccount,
                       "another account's choice matched on the item id alone")
        XCTAssertEqual(SavedWidgetSelectionStatus10875.of(scope: "guest", subject: game(1), in: snap), .otherAccount,
                       "a signed-out choice survived signing in")
        XCTAssertEqual(SavedWidgetSelectionStatus10875.of(scope: "account.aa", subject: game(1), in: nil), .unknown)
    }

    func testEntityIDRoundTripsAndRefusesMalformedIDs() throws {
        let sel = SavedWidgetSelection10875(scope: "account.ab12", subject: market(65391342), side: nil, outcomeID: nil)
        XCTAssertEqual(sel.entityID, "account.ab12|market:65391342")
        let parsed = try XCTUnwrap(SavedWidgetSelection10875.parse(entityID: sel.entityID))
        XCTAssertEqual(parsed.scope, "account.ab12")
        XCTAssertEqual(parsed.subject, market(65391342))
        for bad in ["", "guest", "|game:1", "guest|game:", "guest|game:-4", "guest|team:3", "guest|game:x"] {
            XCTAssertNil(SavedWidgetSelection10875.parse(entityID: bad), "\(bad) parsed into a selection")
        }
        XCTAssertNil(SavedWidgetSubject10875(pinType: "team", value: 4), "a pin type the widget cannot show was admitted")
        XCTAssertEqual(SavedWidgetSubject10875(pinType: "future", value: 4), market(4))
    }

    func testTapRoutesAreTheAppsDetailRoutes() {
        XCTAssertEqual(game(15327330).url?.absoluteString, "bainluck://events/15327330")
        XCTAssertEqual(market(65391342).url?.absoluteString, "bainluck://futures/65391342")
    }

    // MARK: - The real pin manager across an account switch

    private func manager(_ d: UserDefaults, loads: @escaping () async throws -> PinsResponse) -> PinManager {
        PinManager(defaults: d, allowLegacyGuestPins: false,
                   initialBinding: PinAccountBinding(userID: nil, authenticated: false),
                   serverLoad: loads, serverSync: { _, _, _ in })
    }

    private func snapshot(_ pins: PinManager) -> SavedWidgetSnapshot10875 {
        .from(boundUserID: pins.boundUserID, savedPins: pins.savedPins, loadState: pins.loadState)
    }

    func testAnAccountSwitchPublishesTheNewAccountsSetNeverTheOld() async throws {
        let d = try defaults()
        var reply = PinsResponse(events: [11, 12], futures: [21])
        let pins = manager(d) { reply }
        let shared = try defaults()
        var reloads = 0
        let publisher = SavedWidgetPublisher10875(store: SavedWidgetBridgeStore10875(defaults: shared), reload: { reloads += 1 })

        pins.bindAccount(PinAccountBinding(userID: "A", authenticated: true))
        await pins.loadPins()
        publisher.publish(snapshot(pins))
        let a = try XCTUnwrap(SavedWidgetBridgeStore10875(defaults: shared).read())
        XCTAssertEqual(a.scope, SavedWidgetBridge10875.scope(userID: "A"))
        XCTAssertEqual(a.subjects, [game(11), game(12), market(21)])
        XCTAssertTrue(a.pinsConfirmed)

        reply = PinsResponse(events: [31], futures: [])
        pins.bindAccount(PinAccountBinding(userID: "B", authenticated: true))
        let mid = snapshot(pins)
        XCTAssertEqual(mid.scope, SavedWidgetBridge10875.scope(userID: "B"))
        XCTAssertTrue(mid.subjects.isEmpty, "B's snapshot carried A's pins before B's own load answered")
        XCTAssertFalse(mid.pinsConfirmed, "an unanswered account load was called confirmed")
        publisher.publish(mid)
        await pins.loadPins()
        publisher.publish(snapshot(pins))
        let b = try XCTUnwrap(SavedWidgetBridgeStore10875(defaults: shared).read())
        XCTAssertEqual(b.subjects, [game(31)])
        XCTAssertEqual(reloads, 3, "each changed snapshot must ask WidgetKit to reload exactly once")

        pins.bindAccount(PinAccountBinding(userID: nil, authenticated: false))
        XCTAssertEqual(snapshot(pins).scope, "guest", "signing out kept the account's scope")
    }

    func testAnAccountsServerSetBeyondTheDeviceLimitReachesTheWidgetWhole() async throws {
        let d = try defaults()
        let pins = manager(d) { PinsResponse(events: Array(1...7), futures: Array(101...106)) }
        pins.bindAccount(PinAccountBinding(userID: "4821", authenticated: true))
        await pins.loadPins()
        let shared = try defaults()
        SavedWidgetPublisher10875(store: SavedWidgetBridgeStore10875(defaults: shared), reload: {}).publish(snapshot(pins))
        let read = try XCTUnwrap(SavedWidgetBridgeStore10875(defaults: shared).read(),
                                 "the widget's reader refused the app's own snapshot, so every widget reads Open Bain Luck")
        XCTAssertEqual(read.subjects, (1...7).map(game) + (101...106).map(market),
                       "saved items were dropped on the way to the widget")
    }

    func testALateLoadForThePreviousAccountCannotRepublishIt() async throws {
        let d = try defaults()
        var held: CheckedContinuation<PinsResponse, Error>?
        var answerA = true
        let pins = manager(d) {
            if answerA {
                return try await withCheckedThrowingContinuation { held = $0 }
            }
            return PinsResponse(events: [31], futures: [])
        }
        pins.bindAccount(PinAccountBinding(userID: "A", authenticated: true))
        let loadA = Task { await pins.loadPins() }
        while held == nil { await Task.yield() }

        answerA = false
        pins.bindAccount(PinAccountBinding(userID: "B", authenticated: true))
        await pins.loadPins()
        held?.resume(returning: PinsResponse(events: [11, 12], futures: [21]))
        await loadA.value

        let after = snapshot(pins)
        XCTAssertEqual(after.scope, SavedWidgetBridge10875.scope(userID: "B"))
        XCTAssertEqual(after.subjects, [game(31)], "A's late answer reached the widget snapshot after switching to B")
    }

    // MARK: - One instance's timeline

    private struct Rig {
        var bridge: SavedWidgetSnapshot10875?
        var fetched: [SavedWidgetSubject10875] = []
    }

    private func eventJSON(id: Int = 15327330, status: String = "live", observed: Date?, sport: String = "icehockey_nhl",
                           home: Double = 0.62, away: Double? = 0.38, extra: String = "") -> Data {
        let obs = observed.map { "\"\(iso($0))\"" } ?? "null"
        let awayField = away.map { String($0) } ?? "null"
        return Data("""
        {"id": \(id), "sport": "\(sport)", "home_team": "Colorado Avalanche", "away_team": "Toronto Maple Leafs",
         "status": "\(status)", "commence_time": "\(iso(t0.addingTimeInterval(-3600)))",
         "home_score": 2, "away_score": 1,
         "current_odds": {"home_probability": \(home), "away_probability": \(awayField)},
         "hero_probability_source": "blend", "hero_probability_observed_at": \(obs)\(extra)}
        """.utf8)
    }

    func testNothingAboutAnotherAccountsChoiceIsFetchedOrShown() async throws {
        let cache = SavedWidgetDetailCache10875(defaults: try defaults())
        let a = SavedWidgetBridge10875.scope(userID: "A")
        let b = SavedWidgetBridge10875.scope(userID: "B")
        cache.store(eventJSON(observed: t0), scope: a, subject: game(15327330))
        var fetches = 0
        let sel = SavedWidgetSelection10875(scope: a, subject: game(15327330), side: nil, outcomeID: nil)
        let bridgeB = SavedWidgetSnapshot10875(scope: b, subjects: [game(15327330)], pinsConfirmed: true)
        let content = await SavedWidgetTimeline10875.resolve(sel, readBridge: { bridgeB },
                                                            fetch: { _ in fetches += 1; return Data() }, cache: cache)
        XCTAssertEqual(content, .otherAccount, "an A-chosen widget showed content while B is signed in")
        XCTAssertEqual(fetches, 0, "the widget fetched an item on behalf of an account that is not signed in")
        XCTAssertNil(cache.data(scope: a, subject: game(15327330)), "A's held detail outlived the switch to B")
        XCTAssertEqual(SavedWidgetMessage10875(content).title, "Saved on another account")
    }

    func testRemovedAndUnknownAreDecidedWithoutTheNetwork() async throws {
        let cache = SavedWidgetDetailCache10875(defaults: try defaults())
        var fetches = 0
        let sel = SavedWidgetSelection10875(scope: "guest", subject: game(7), side: nil, outcomeID: nil)
        let empty = SavedWidgetSnapshot10875(scope: "guest", subjects: [], pinsConfirmed: true)
        let removed = await SavedWidgetTimeline10875.resolve(sel, readBridge: { empty },
                                                            fetch: { _ in fetches += 1; return Data() }, cache: cache)
        XCTAssertEqual(removed, .removed(title: nil))
        let unknown = await SavedWidgetTimeline10875.resolve(sel, readBridge: { nil },
                                                            fetch: { _ in fetches += 1; return Data() }, cache: cache)
        XCTAssertEqual(unknown, .openApp, "a widget that does not know the saved set showed something anyway")
        let none = await SavedWidgetTimeline10875.resolve(nil, readBridge: { empty },
                                                         fetch: { _ in fetches += 1; return Data() }, cache: cache)
        XCTAssertEqual(none, .notConfigured)
        XCTAssertEqual(fetches, 0)
    }

    func testAnAnswerThatLandsAfterSignOutOrUnpinIsDiscarded() async throws {
        let cache = SavedWidgetDetailCache10875(defaults: try defaults())
        let a = SavedWidgetBridge10875.scope(userID: "A")
        let sel = SavedWidgetSelection10875(scope: a, subject: game(15327330), side: nil, outcomeID: nil)
        var bridge: SavedWidgetSnapshot10875? = .init(scope: a, subjects: [game(15327330)], pinsConfirmed: true)
        let body = eventJSON(observed: t0)

        let signedOut = await SavedWidgetTimeline10875.resolve(sel, readBridge: { bridge }, fetch: { _ in
            bridge = .init(scope: "guest", subjects: [], pinsConfirmed: true) // signed out mid-request
            return body
        }, cache: cache)
        XCTAssertEqual(signedOut, .otherAccount, "a response fetched for A was shown after A signed out")
        XCTAssertNil(cache.data(scope: a, subject: game(15327330)), "a response fetched for A was cached after A signed out")

        bridge = .init(scope: a, subjects: [game(15327330)], pinsConfirmed: true)
        let unpinned = await SavedWidgetTimeline10875.resolve(sel, readBridge: { bridge }, fetch: { _ in
            bridge = .init(scope: a, subjects: [], pinsConfirmed: true) // unpinned mid-request
            return body
        }, cache: cache)
        XCTAssertEqual(unpinned, .removed(title: nil), "an item unpinned mid-request kept showing its price")
    }

    func testOfflineShowsThisAccountsLastDetailReadAtTheEntrysOwnDate() async throws {
        let cache = SavedWidgetDetailCache10875(defaults: try defaults())
        let sel = SavedWidgetSelection10875(scope: "guest", subject: game(15327330), side: nil, outcomeID: nil)
        let bridge = SavedWidgetSnapshot10875(scope: "guest", subjects: [game(15327330)], pinsConfirmed: true)

        let none = await SavedWidgetTimeline10875.resolve(sel, readBridge: { bridge },
                                                         fetch: { _ in throw SavedWidgetFetchError10875.failed }, cache: cache)
        XCTAssertEqual(none, .unreachable, "with nothing held, offline must say so rather than invent a reading")

        let fresh = await SavedWidgetTimeline10875.resolve(sel, readBridge: { bridge },
                                                          fetch: { _ in self.eventJSON(observed: self.t0) }, cache: cache)
        guard case .detail(_, offline: false) = fresh else { return XCTFail("a good answer was not shown: \(fresh)") }

        let offline = await SavedWidgetTimeline10875.resolve(sel, readBridge: { bridge },
                                                            fetch: { _ in throw URLError(.notConnectedToInternet) }, cache: cache)
        guard case .detail(let payload, offline: true) = offline else { return XCTFail("offline lost the held detail: \(offline)") }
        let later = SavedWidgetTimeline10875.reading(payload, selection: sel, at: t0.addingTimeInterval(3 * 3600))
        XCTAssertEqual(later.phase, .lastRecorded, "a held price kept calling itself current hours later")
        XCTAssertEqual(later.observedAt, t0, "the held price's clock was replaced by the time it was read")

        let gone = await SavedWidgetTimeline10875.resolve(sel, readBridge: { bridge },
                                                         fetch: { _ in throw SavedWidgetFetchError10875.notFound }, cache: cache)
        XCTAssertEqual(gone, .gone)
    }

    func testAMarketAnswerForTheWrongIDIsNotShown() async throws {
        let cache = SavedWidgetDetailCache10875(defaults: try defaults())
        let sel = SavedWidgetSelection10875(scope: "guest", subject: market(65391342), side: nil, outcomeID: nil)
        let bridge = SavedWidgetSnapshot10875(scope: "guest", subjects: [market(65391342)], pinsConfirmed: true)
        let body = Data("{\"id\": 999, \"name\": \"Other\", \"status\": \"open\", \"outcomes\": []}".utf8)
        let wrong = await SavedWidgetTimeline10875.resolve(sel, readBridge: { bridge }, fetch: { _ in body }, cache: cache)
        XCTAssertEqual(wrong, .unreachable,
                       "another market's detail was drawn under this widget's choice; the market page refuses it too")
    }

    func testASavedDuplicateGameAdoptsItsCanonicalRowAsTheEventPageDoes() async throws {
        let d = try defaults()
        let cache = SavedWidgetDetailCache10875(defaults: d)
        let sel = SavedWidgetSelection10875(scope: "guest", subject: game(15308290), side: nil, outcomeID: nil)
        let bridge = SavedWidgetSnapshot10875(scope: "guest", subjects: [game(15308290)], pinsConfirmed: true)
        let canonical = eventJSON(id: 15312656, observed: t0)
        let served = await SavedWidgetTimeline10875.resolve(sel, readBridge: { bridge }, fetch: { _ in canonical }, cache: cache)
        guard case .detail(let payload, offline: false) = served else {
            return XCTFail("a proven duplicate served as its canonical row was not shown: \(served)")
        }
        XCTAssertEqual(payload.id, 15312656)
        XCTAssertEqual(cache.data(scope: "guest", subject: game(15308290)), canonical,
                       "the canonical row was not held under the id the reader saved")
        XCTAssertEqual(sel.subject.url?.absoluteString, "bainluck://events/15308290",
                       "the tap must open the saved id, which the event page resolves the same way")
    }

    func testTwoInstancesKeepTheirOwnChoicesAndRoutes() async throws {
        let cache = SavedWidgetDetailCache10875(defaults: try defaults())
        let bridge = SavedWidgetSnapshot10875(scope: "guest", subjects: [game(15327330), market(65391342)], pinsConfirmed: true)
        let one = SavedWidgetSelection10875(scope: "guest", subject: game(15327330), side: .away, outcomeID: nil)
        let two = SavedWidgetSelection10875(scope: "guest", subject: market(65391342), side: nil, outcomeID: 2)
        let marketBody = Data("""
        {"id": 65391342, "name": "DP World India Championship - Winner", "status": "open",
         "outcomes": [{"id": 1, "name": "Eugenio Chacarra", "probability": 0.2, "last_updated": "\(iso(t0))"},
                      {"id": 2, "name": "Thomas Detry", "probability": 0.12, "last_updated": "\(iso(t0))"}]}
        """.utf8)
        func fetch(_ s: SavedWidgetSubject10875) -> Data { s.kind == .game ? eventJSON(observed: t0) : marketBody }
        let c1 = await SavedWidgetTimeline10875.resolve(one, readBridge: { bridge }, fetch: { fetch($0) }, cache: cache)
        let c2 = await SavedWidgetTimeline10875.resolve(two, readBridge: { bridge }, fetch: { fetch($0) }, cache: cache)
        guard case .detail(let p1, _) = c1, case .detail(let p2, _) = c2 else { return XCTFail("an instance lost its detail") }
        XCTAssertEqual(SavedWidgetTimeline10875.reading(p1, selection: one, at: t0).headline?.label, "Toronto Maple Leafs")
        XCTAssertEqual(SavedWidgetTimeline10875.reading(p2, selection: two, at: t0).headline?.label, "Thomas Detry",
                       "the second instance followed the market's leader instead of its chosen outcome")
        XCTAssertNotEqual(one.subject.url, two.subject.url)
    }

    // MARK: - Games

    private func event(_ json: Data) throws -> SavedWidgetEventDetail10875 {
        try SavedWidgetDetailDecoding10875.decoder().decode(SavedWidgetEventDetail10875.self, from: json)
    }

    func testAFinishedGameShowsItsResultNeverAPrice() throws {
        let e = try event(eventJSON(status: "completed", observed: nil,
                                    extra: ", \"hero_settled_result\": \"away\", \"home_team_data\": {\"abbreviation\": \"COL\"}, \"away_team_data\": {\"abbreviation\": \"TOR\"}"))
        let r = SavedWidgetReadingRules10875.game(e, side: nil, now: t0)
        XCTAssertEqual(r.phase, .result)
        XCTAssertEqual(r.status, "Final · 1–2", "the final score is away–home, as every card prints it")
        XCTAssertEqual(r.headline?.label, "Toronto Maple Leafs")
        XCTAssertEqual(r.headline?.verdict, "Won", "the served result was not the authority")
        XCTAssertNil(r.priceCaption, "a finished game kept a price caption")
        XCTAssertFalse(r.rows.contains { $0.figure?.hasSuffix("%") == true }, "a finished game printed a percentage")
        XCTAssertEqual(SavedWidgetReadingRules10875.game(e, side: .home, now: t0).headline?.verdict, "Lost",
                       "the chosen side's own result was not shown")
        XCTAssertEqual(r.shortSubject, "TOR vs COL")
    }

    func testAFinishedGameWithNoResultNamesNoWinner() throws {
        let body = String(decoding: eventJSON(status: "completed", observed: nil), as: UTF8.self)
            .replacingOccurrences(of: "\"home_score\": 2, \"away_score\": 1,", with: "")
        let r = SavedWidgetReadingRules10875.game(try event(Data(body.utf8)), side: nil, now: t0)
        XCTAssertEqual(r.phase, .noResult, "a scoreless final invented a winner or a draw")
        XCTAssertNil(r.headline)
        XCTAssertEqual(r.status, "Final")
        XCTAssertTrue(r.rows.allSatisfy { $0.figure == nil && $0.verdict == nil }, "a missing score was printed as something")
    }

    func testALevelFinalIsADraw() throws {
        let body = String(decoding: eventJSON(status: "completed", observed: nil, sport: "soccer_epl"), as: UTF8.self)
            .replacingOccurrences(of: "\"home_score\": 2", with: "\"home_score\": 1")
        let r = SavedWidgetReadingRules10875.game(try event(Data(body.utf8)), side: .home, now: t0)
        XCTAssertEqual(r.phase, .result)
        XCTAssertEqual(r.headline?.verdict, "Draw", "a level final named a winner or a loser")
    }

    func testADrawPricedMatchNeverPrintsTheComplementAsTheAwaySide() throws {
        let e = try event(eventJSON(observed: t0.addingTimeInterval(-60), sport: "soccer_epl", home: 0.45, away: 0.55))
        let r = SavedWidgetReadingRules10875.game(e, side: nil, now: t0)
        XCTAssertNil(r.rows[0].figure, "the away slot printed 1 − home on a sport that prices a draw")
        XCTAssertEqual(r.rows[1].figure, "45%")
        XCTAssertEqual(r.headline?.label, "Colorado Avalanche", "a draw-priced headline must name HOME, favourite or not")
        let away = SavedWidgetReadingRules10875.game(e, side: .away, now: t0)
        XCTAssertNil(away.headline?.figure, "the chosen away side printed a number the detail withholds")
        XCTAssertTrue(away.spoken.contains("doesn't show a separate chance"), "the withheld side was not explained")
    }

    func testALivePriceIsCurrentOnlyOnItsOwnClock() throws {
        let observed = t0.addingTimeInterval(-5 * 60)
        let r = SavedWidgetReadingRules10875.game(try event(eventJSON(observed: observed)), side: nil, now: t0)
        XCTAssertEqual(r.phase, .current)
        XCTAssertEqual(r.observedAt, observed, "the observation clock was replaced by the read time")
        XCTAssertEqual(r.becomesLastRecordedAt, observed.addingTimeInterval(30 * 60))
        XCTAssertEqual(r.status, "Live · 1–2")
        XCTAssertEqual(r.headline?.figure, "62%")

        let old = SavedWidgetReadingRules10875.game(try event(eventJSON(observed: t0.addingTimeInterval(-31 * 60))), side: nil, now: t0)
        XCTAssertEqual(old.phase, .lastRecorded, "a 31-minute-old live price was called current")
        let undated = SavedWidgetReadingRules10875.game(try event(eventJSON(observed: nil)), side: nil, now: t0)
        XCTAssertEqual(undated.phase, .lastRecorded, "an undated price was called current")
        XCTAssertNil(undated.becomesLastRecordedAt)
        XCTAssertTrue(undated.spoken.contains("No time was recorded"), "an undated price did not say so")
    }

    func testAScheduledPriceStopsBeingCurrentAtTheStart() throws {
        let commence = t0.addingTimeInterval(10 * 60)
        let body = String(decoding: eventJSON(status: "scheduled", observed: t0.addingTimeInterval(-60)), as: UTF8.self)
            .replacingOccurrences(of: iso(t0.addingTimeInterval(-3600)), with: iso(commence))
        let r = SavedWidgetReadingRules10875.game(try event(Data(body.utf8)), side: nil, now: t0)
        XCTAssertEqual(r.phase, .current)
        XCTAssertEqual(r.becomesLastRecordedAt, commence, "a pregame price kept calling itself current past the start")
        XCTAssertTrue(r.status.hasPrefix("Starts "))

        let started = String(decoding: eventJSON(status: "scheduled", observed: t0.addingTimeInterval(-60)), as: UTF8.self)
        XCTAssertEqual(SavedWidgetReadingRules10875.game(try event(Data(started.utf8)), side: nil, now: t0).phase, .lastRecorded,
                       "a game past its start that is not live was called current")
    }

    func testAnOpeningLineIsNamedAndCarriesNoObservationClock() throws {
        let e = try event(eventJSON(status: "scheduled", observed: t0,
                                    extra: ", \"hero_probability\": 0.5996, \"hero_probability_away\": 0.4004")
            .replacingBlendWithOpening())
        let r = SavedWidgetReadingRules10875.game(e, side: .home, now: t0)
        XCTAssertEqual(r.phase, .openingLine)
        XCTAssertEqual(r.headline?.figure, "60%", "the opening hero printed current_odds instead of the server's pair")
        XCTAssertNil(r.observedAt, "an opening line was dated as a fresh observation")
    }

    func testServedIntegersAreUsedBothOrNeither() throws {
        let both = try event(eventJSON(observed: t0, home: 0.505, away: 0.495)
            .replacingOdds(with: "\"home_probability\": 0.505, \"away_probability\": 0.495, \"home_rendered_percent\": 51, \"away_rendered_percent\": 49"))
        let r = SavedWidgetReadingRules10875.game(both, side: nil, now: t0)
        XCTAssertEqual(r.rows.map(\.figure), ["49%", "51%"])
        // One served integer (a deliberately different 52) and no partner: both
        // sides fall back to the local pair, or the card prints 49 + 52.
        let one = try event(eventJSON(observed: t0, home: 0.505, away: 0.495)
            .replacingOdds(with: "\"home_probability\": 0.505, \"away_probability\": 0.495, \"home_rendered_percent\": 52"))
        let figures = SavedWidgetReadingRules10875.game(one, side: nil, now: t0).rows.map(\.figure)
        XCTAssertEqual(figures, ["49%", "51%"], "a served integer was used beside a locally rounded one")
    }

    func testNoOddsMeansNoNumber() throws {
        let body = String(decoding: eventJSON(observed: t0), as: UTF8.self)
            .replacingOccurrences(of: "\"current_odds\": {\"home_probability\": 0.62, \"away_probability\": 0.38},", with: "")
        let r = SavedWidgetReadingRules10875.game(try event(Data(body.utf8)), side: nil, now: t0)
        XCTAssertEqual(r.phase, .unavailable)
        XCTAssertTrue(r.rows.allSatisfy { $0.figure == nil }, "a missing price was printed")
        XCTAssertNil(r.headline)
    }

    func testVenueVerdictsAreQuotedNotParsed() throws {
        let settled = try event(eventJSON(status: "suspended", observed: t0,
                                          extra: ", \"venue_settled\": true, \"venue_settled_result\": \"Maple Leafs win\""))
        let r = SavedWidgetReadingRules10875.game(settled, side: nil, now: t0)
        XCTAssertEqual(r.phase, .result)
        XCTAssertEqual(r.headline?.verdict, "Maple Leafs win")
        let closed = try event(eventJSON(status: "suspended", observed: t0, extra: ", \"venue_closed_no_winner\": true"))
        XCTAssertEqual(SavedWidgetReadingRules10875.game(closed, side: nil, now: t0).status, "Ended · no winner")
    }

    func testATinyPriceIsNeverZero() throws {
        let e = try event(eventJSON(observed: t0, home: 0.996, away: 0.004))
        XCTAssertEqual(SavedWidgetReadingRules10875.game(e, side: .away, now: t0).headline?.figure, "<1%",
                       "a priced side printed 0%")
    }

    // MARK: - Markets

    private func marketDetail(status: String = "open", lead: Int? = nil, legs: String) throws -> SavedWidgetMarketDetail10875 {
        let leadKey = lead.map { "\"lead_outcome_id\": \($0)," } ?? ""
        return try SavedWidgetDetailDecoding10875.decoder().decode(SavedWidgetMarketDetail10875.self, from: Data("""
        {"id": 7, "name": "Winner", "status": "\(status)", \(leadKey) "outcomes": [\(legs)]}
        """.utf8))
    }

    func testAMarketOutcomeIsCurrentForSixHoursOnItsOwnStamp() throws {
        let stamp = t0.addingTimeInterval(-60)
        let m = try marketDetail(legs: """
        {"id": 1, "name": "A", "probability": 0.6, "last_updated": "\(iso(stamp))"},
        {"id": 2, "name": "B", "probability": 0.4, "last_updated": "\(iso(stamp))"}
        """)
        let r = SavedWidgetReadingRules10875.market(m, outcomeID: 2, now: t0)
        XCTAssertEqual(r.phase, .current)
        XCTAssertEqual(r.headline?.figure, "40%")
        XCTAssertEqual(r.becomesLastRecordedAt, stamp.addingTimeInterval(6 * 3600))
        XCTAssertEqual(SavedWidgetReadingRules10875.market(m, outcomeID: 2, now: t0.addingTimeInterval(7 * 3600)).phase,
                       .lastRecorded, "a seven-hour-old market price was called current")
        XCTAssertEqual(SavedWidgetReadingRules10875.market(m, outcomeID: nil, now: t0).headline?.label, "A",
                       "with no outcome chosen, the hero leg was not followed")
        XCTAssertEqual(SavedWidgetReadingRules10875.market(m, outcomeID: 99, now: t0).phase, .unavailable,
                       "a vanished outcome was replaced by another one")
    }

    func testAMarketPriceIsNeverCalledCurrentAndPrintsItsOwnClock() throws {
        let stamp = t0.addingTimeInterval(-(6 * 3600 - 60))
        let m = try marketDetail(legs: """
        {"id": 1, "name": "A", "probability": 0.6, "last_updated": "\(iso(stamp))"}
        """)
        let r = SavedWidgetReadingRules10875.market(m, outcomeID: 1, now: t0)
        XCTAssertEqual(r.phase, .current)
        XCTAssertNil(r.priceCaption, "a market leg was given a word the market page never uses for it")
        XCTAssertFalse(r.spoken.localizedCaseInsensitiveContains("current"), "VoiceOver called a market price current")
        XCTAssertEqual(r.observedAt, stamp, "the clock printed must be the price's own")
        let old = SavedWidgetReadingRules10875.market(m, outcomeID: 1, now: t0.addingTimeInterval(120))
        XCTAssertEqual(old.priceCaption, "Last recorded chance", "past the bound the price must say it is last recorded")
    }

    func testOnlyAnOpenMarketReadsOpen() throws {
        let legs = """
        {"id": 1, "name": "A", "probability": 0.6, "last_updated": "\(iso(t0))"}
        """
        for (status, word) in [("withdrawn", "Withdrawn"), ("suspended", "Suspended"), ("closed", "Closed")] {
            let r = SavedWidgetReadingRules10875.market(try marketDetail(status: status, legs: legs), outcomeID: 1, now: t0)
            XCTAssertEqual(r.status, word, "a \(status) market read \(r.status)")
            XCTAssertEqual(r.phase, .lastRecorded, "a \(status) market's price was treated as live")
        }
        XCTAssertEqual(SavedWidgetReadingRules10875.market(try marketDetail(legs: legs), outcomeID: 1, now: t0).status, "Open")
        XCTAssertEqual(SavedWidgetReadingRules10875.marketStatusText(nil), "Status unknown", "a missing status read as Open")
    }

    func testAVanishedChosenOutcomeIsSaidOnScreen() throws {
        let m = try marketDetail(legs: """
        {"id": 1, "name": "A", "probability": 0.6, "last_updated": "\(iso(t0))"}
        """)
        let r = SavedWidgetReadingRules10875.market(m, outcomeID: 99, now: t0)
        XCTAssertEqual(r.phase, .unavailable)
        XCTAssertEqual(r.headline?.verdict, "No longer listed", "the small and Lock Screen widgets do not say the outcome is gone")
        XCTAssertEqual(r.rows.first?.verdict, "No longer listed", "the medium widget does not say the outcome is gone")
        XCTAssertNil(r.headline?.figure, "a number was substituted for a vanished outcome")
        XCTAssertFalse(r.rows.contains { $0.label == "A" }, "another outcome replaced the reader's choice")
    }

    func testAMarketResultIsWonOrLostByTheSettlementRule() throws {
        let legs = """
        {"id": 1, "name": "A", "probability": 0.99, "is_winner": true, "resolution_source": "api_settlement"},
        {"id": 2, "name": "B", "probability": 0.01, "is_winner": false, "resolution_source": "api_settlement"}
        """
        let resolved = try marketDetail(status: "resolved", legs: legs)
        XCTAssertEqual(SavedWidgetReadingRules10875.market(resolved, outcomeID: 1, now: t0).headline?.verdict, "Won")
        XCTAssertEqual(SavedWidgetReadingRules10875.market(resolved, outcomeID: 2, now: t0).headline?.verdict, "Lost")
        XCTAssertNil(SavedWidgetReadingRules10875.market(resolved, outcomeID: 2, now: t0).headline?.figure,
                     "a settled outcome kept printing its last price")
        let open = try marketDetail(status: "open", legs: legs)
        let openLoser = SavedWidgetReadingRules10875.market(open, outcomeID: 2, now: t0)
        XCTAssertNil(openLoser.headline?.verdict, "an open market's default false was read as Lost (#6082)")
        let retracted = try marketDetail(status: "resolved", legs: """
        {"id": 1, "name": "A", "probability": 0.5, "is_winner": true, "resolution_source": "ungradeable_result"}
        """)
        XCTAssertNil(SavedWidgetReadingRules10875.market(retracted, outcomeID: 1, now: t0).headline?.verdict,
                     "a retraction was read as a result")
    }

    // MARK: - Timeline dates

    func testACurrentPriceGetsASecondEntryThatSaysLastRecorded() throws {
        let observed = t0.addingTimeInterval(-5 * 60)
        let sel = SavedWidgetSelection10875(scope: "guest", subject: game(15327330), side: nil, outcomeID: nil)
        let content = SavedWidgetContent10875.detail(.game(try event(eventJSON(observed: observed))), offline: false)
        let dates = SavedWidgetTimeline10875.entryDates(content, selection: sel, now: t0)
        XCTAssertEqual(dates.count, 2, "a current price had no entry for the moment it stops being current")
        guard dates.count == 2, case .detail(let payload, _) = content else { return }
        XCTAssertEqual(SavedWidgetTimeline10875.reading(payload, selection: sel, at: dates[1]).phase, .lastRecorded)
        XCTAssertEqual(SavedWidgetTimeline10875.nextRequest(content, selection: sel, now: t0), t0.addingTimeInterval(15 * 60))

        let final = SavedWidgetContent10875.detail(.game(try event(eventJSON(status: "completed", observed: nil))), offline: false)
        XCTAssertEqual(SavedWidgetTimeline10875.entryDates(final, selection: sel, now: t0), [t0])
        XCTAssertEqual(SavedWidgetTimeline10875.nextRequest(final, selection: sel, now: t0), t0.addingTimeInterval(6 * 3600))
    }

    // MARK: - Wiring (read from source; the extension itself is Native's gate)

    private static let iosRoot = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()

    private func source(_ path: String) throws -> String {
        try String(contentsOf: Self.iosRoot.appendingPathComponent(path), encoding: .utf8)
    }

    func testTheWidgetIsRegisteredAndTheAppPublishesTheBridge() throws {
        XCTAssertTrue(try source("BainLuckWidget/BainLuckWidget.swift").contains("SavedItemWidget10875()"),
                      "the saved-item widget is not in the widget bundle")
        XCTAssertTrue(try source("BainLuckWidget/BainLuckWidget.swift").contains("BainLuckDesktopWidget()"),
                      "the general widget was dropped")
        XCTAssertTrue(try source("Bain Luck/Bain_LuckApp.swift").contains(".savedItemWidgets10875(pins: pinManager)"),
                      "the app root no longer publishes the saved items to the widget")
    }

    func testTheWidgetAsksWhatTheDetailPageAsksAndReadsRetiredAsGone() throws {
        let fetcher = try source("BainLuckWidget/SavedItemWidgetIntent10875.swift")
        XCTAssertTrue(fetcher.contains("/api/futures/\\(subject.id)?representation=verified_title"),
                      "a market widget asks for another representation than the market page draws")
        XCTAssertTrue(fetcher.contains("http.statusCode == 404 || http.statusCode == 410"),
                      "a retired fixture (410) reads as unreachable instead of no longer listed")
    }

    func testBothTargetsDeclareTheOneAppGroup() throws {
        for path in ["Bain Luck/Bain Luck.entitlements", "BainLuckWidget/BainLuckWidget.entitlements"] {
            let plist = try XCTUnwrap(PropertyListSerialization.propertyList(
                from: Data(try source(path).utf8), format: nil) as? [String: Any])
            XCTAssertEqual(plist["com.apple.security.application-groups"] as? [String], [SavedWidgetBridge10875.appGroup],
                           "\(path) does not declare the bridge's app group")
        }
    }

    func testTheSharedRulesAreMembersOfTheWidgetTarget() throws {
        let pbxproj = try source("Bain Luck.xcodeproj/project.pbxproj")
        let start = try XCTUnwrap(pbxproj.range(of: "Exceptions for \"Bain Luck\" folder in \"BainLuckWidget\" target"))
        let end = try XCTUnwrap(pbxproj.range(of: ");", range: start.upperBound..<pbxproj.endIndex))
        let block = String(pbxproj[start.upperBound..<end.lowerBound])
        for file in ["Utilities/EventState.swift", "Utilities/EventOutcome.swift", "Utilities/OutcomeVerdict.swift",
                     "Utilities/FormattingUtilities.swift", "Utilities/ComplementProbabilityDisplay.swift",
                     "Widgets10875/SavedWidgetBridge10875.swift", "Widgets10875/SavedWidgetDetail10875.swift",
                     "Widgets10875/SavedWidgetReading10875.swift", "Widgets10875/SavedWidgetTimeline10875.swift"] {
            XCTAssertTrue(block.contains(file + ","), "\(file) is not a member of BainLuckWidget")
        }
        XCTAssertFalse(block.contains("SavedWidgetPublisher10875"), "the app-only publisher leaked into the widget target")
    }
}

private extension Data {
    func replacingBlendWithOpening() -> Data {
        Data(String(decoding: self, as: UTF8.self)
            .replacingOccurrences(of: "\"hero_probability_source\": \"blend\"", with: "\"hero_probability_source\": \"opening\"").utf8)
    }

    func replacingOdds(with fields: String) -> Data {
        let text = String(decoding: self, as: UTF8.self)
        guard let start = text.range(of: "\"current_odds\": {"),
              let end = text.range(of: "}", range: start.upperBound..<text.endIndex) else { return self }
        return Data(text.replacingCharacters(in: start.upperBound..<end.lowerBound, with: fields).utf8)
    }
}
