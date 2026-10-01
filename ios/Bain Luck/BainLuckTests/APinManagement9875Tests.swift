import XCTest
@testable import Bain_Luck

@MainActor
final class APinManagement9875Tests: XCTestCase {
    private struct Failed: Error {}
    private var defaults: UserDefaults!
    private var suite = ""
    override func setUp() {
        super.setUp()
        suite = "APinManagement9875.\(UUID())"
        defaults = UserDefaults(suiteName: suite)!
    }
    override func tearDown() {
        defaults.removePersistentDomain(forName: suite)
        defaults = nil
        super.tearDown()
    }
    private func bind(_ manager: PinManager, _ id: String?, authenticated: Bool = true) {
        manager.bindAccount(PinAccountBinding(userID: id, authenticated: authenticated))
    }

    func testSavedIDsAbsentFromFeedAreAllReachableAndRemovable() async {
        let m = PinManager(defaults: defaults, serverLoad: { PinsResponse(events: [11, 22], futures: [33]) }, serverSync: { _, _, _ in })
        bind(m, "A")
        await m.loadPins()
        XCTAssertEqual(Set(m.savedPins.map(\.id)), ["event:11", "event:22", "future:33"])
        await m.togglePin(type: "event", id: 22)?.value
        await m.togglePin(type: "future", id: 33)?.value
        XCTAssertEqual(m.savedPins.map(\.id), ["event:11"])
    }
    func testLimitOpensIndependentPresentationAndTimeoutCannotDismissIt() {
        let m = PinManager(defaults: defaults)
        for id in 1...6 { m.togglePin(type: "event", id: id) }
        m.togglePin(type: "event", id: 7)
        XCTAssertEqual(m.feedback?.managementType, "event")
        XCTAssertNil(PinFeedbackToast.displaySeconds(for: m.feedback!))
        m.presentManagement(type: m.feedback?.managementType)
        let requestID = m.managementPresentation?.id
        XCTAssertEqual(m.managementPresentation?.focusType, "event")
        XCTAssertNil(m.feedback)
        m.feedback = nil
        XCTAssertEqual(m.managementPresentation?.id, requestID)
    }
    func testLimitReportsActualServerCountWithoutIncreasingCap() async {
        let m = PinManager(defaults: defaults, serverLoad: { PinsResponse(events: Array(1...8), futures: []) })
        bind(m, "A")
        await m.loadPins()
        XCTAssertNil(m.togglePin(type: "event", id: 9))
        XCTAssertTrue(m.feedback?.message.contains("8 pinned games") == true)
        XCTAssertEqual(m.savedPins.count, 8)
        XCTAssertEqual(PinManager.maxPinsPerType, 6)
    }
    func testFailedUnpinRestoresVisibleRowAndTruthfulFeedback() async {
        let m = PinManager(defaults: defaults, serverLoad: { PinsResponse(events: [42], futures: []) }, serverSync: { _, _, _ in throw Failed() })
        bind(m, "A")
        await m.loadPins()
        await m.togglePin(type: "event", id: 42)?.value
        XCTAssertEqual(m.savedPins.map(\.value), [42])
        XCTAssertEqual(m.feedback?.message, "Couldn't remove pin. Try again.")
        XCTAssertTrue(m.isPinned(type: "event", id: 42))
    }
    func testPendingRemovalKeepsRowAndCapacityThenAllowsNewPinAfterConfirmation() async {
        var release: CheckedContinuation<Void, Never>?
        let m = PinManager(defaults: defaults, serverLoad: { PinsResponse(events: Array(1...6), futures: []) }, serverSync: { _, id, pinned in
            if id == 1 && !pinned { await withCheckedContinuation { release = $0 } }
        })
        bind(m, "A")
        await m.loadPins()
        let removing = m.togglePin(type: "event", id: 1)
        while release == nil { await Task.yield() }
        XCTAssertTrue(m.savedPins.contains(SavedPin(type: "event", value: 1)))
        XCTAssertFalse(m.canPin(type: "event"))
        XCTAssertNil(m.togglePin(type: "event", id: 7))
        release?.resume()
        await removing?.value
        await m.togglePin(type: "event", id: 7)?.value
        XCTAssertTrue(m.isPinned(type: "event", id: 7))
        XCTAssertFalse(m.isPinned(type: "event", id: 1))
        XCTAssertEqual(m.savedPins.count, 6)
    }
    /// Sol's paid bug bash (artifact `sol-pin-bugbash-9875-20261001T134928Z`): the
    /// stored cache already dropped pin 1 while its removal was unconfirmed, so a
    /// cold restart whose first load failed lost a pin the server still held.
    func testAnUnconfirmedRemovalSurvivesColdOfflineRestoreForEachType() async {
        for type in ["event", "future"] {
            var release: CheckedContinuation<Void, Never>?
            let warm = PinManager(defaults: defaults,
                initialBinding: PinAccountBinding(userID: "fake-A", authenticated: true),
                serverLoad: { PinsResponse(events: type == "event" ? Array(1...6) : [],
                                           futures: type == "future" ? Array(1...6) : []) },
                serverSync: { _, _, _ in await withCheckedContinuation { release = $0 }; throw Failed() })
            await warm.loadPins()
            let removal = warm.togglePin(type: type, id: 1)
            while release == nil { await Task.yield() }
            XCTAssertTrue(warm.savedPins.contains(SavedPin(type: type, value: 1)))
            let cold = PinManager(defaults: defaults, allowLegacyGuestPins: false,
                initialBinding: PinAccountBinding(userID: "fake-A", authenticated: true),
                serverLoad: { throw Failed() }, serverSync: { _, _, _ in })
            await cold.loadPins()
            XCTAssertEqual(cold.loadState, .failed)
            XCTAssertTrue(cold.savedPins.contains(SavedPin(type: type, value: 1)),
                          "\(type): an unconfirmed removal hid the last-confirmed pin after a cold failed restore")
            XCTAssertTrue(cold.isPinned(type: type, id: 1), "\(type): the known pin stays removable")
            XCTAssertFalse(cold.canPin(type: type), "\(type): a pending removal must not free the slot")
            release?.resume()
            await removal?.value
            XCTAssertTrue(warm.isPinned(type: type, id: 1), "\(type): warm failed-remove control")
            XCTAssertEqual(warm.feedback?.message, "Couldn't remove pin. Try again.")
            defaults.removePersistentDomain(forName: suite)
        }
    }
    func testAConfirmedRemovalIsWhatAColdOfflineRestoreRemembers() async {
        for type in ["event", "future"] {
            let warm = PinManager(defaults: defaults,
                initialBinding: PinAccountBinding(userID: "fake-A", authenticated: true),
                serverLoad: { PinsResponse(events: type == "event" ? Array(1...6) : [],
                                           futures: type == "future" ? Array(1...6) : []) },
                serverSync: { _, _, _ in })
            await warm.loadPins()
            await warm.togglePin(type: type, id: 1)?.value
            XCTAssertEqual(warm.feedback?.message, "Removed from My Stuff")
            let cold = PinManager(defaults: defaults, allowLegacyGuestPins: false,
                initialBinding: PinAccountBinding(userID: "fake-A", authenticated: true),
                serverLoad: { throw Failed() }, serverSync: { _, _, _ in })
            await cold.loadPins()
            XCTAssertEqual(Set(cold.savedPins.map(\.value)), Set(2...6), "\(type): the confirmed removal is persisted")
            XCTAssertTrue(cold.canPin(type: type))
            defaults.removePersistentDomain(forName: suite)
        }
    }
    func testAPendingRemovalInAccountAIsNeitherWrittenToBNorReplayedThere() async {
        var release: CheckedContinuation<Void, Never>?
        var syncs: [Int] = []
        let m = PinManager(defaults: defaults, serverLoad: { PinsResponse(events: [1, 2], futures: []) }, serverSync: { _, id, _ in
            syncs.append(id)
            if id == 1 { await withCheckedContinuation { release = $0 } }
        })
        bind(m, "A")
        await m.loadPins()
        let oldRemove = m.togglePin(type: "event", id: 1)
        while release == nil { await Task.yield() }
        bind(m, "B")
        release?.resume()
        await oldRemove?.value
        XCTAssertEqual(syncs, [1])
        XCTAssertNil(defaults.data(forKey: "bainluck_pins.user.B.Events"))
        let coldB = PinManager(defaults: defaults, allowLegacyGuestPins: false,
            initialBinding: PinAccountBinding(userID: "B", authenticated: true),
            serverLoad: { throw Failed() }, serverSync: { _, _, _ in })
        await coldB.loadPins()
        XCTAssertTrue(coldB.savedPins.isEmpty)
        let coldA = PinManager(defaults: defaults, allowLegacyGuestPins: false,
            initialBinding: PinAccountBinding(userID: "A", authenticated: true),
            serverLoad: { throw Failed() }, serverSync: { _, _, _ in })
        await coldA.loadPins()
        XCTAssertEqual(coldA.pinnedEventIDs, [1, 2], "A's answer arrived after the switch, so A keeps its last confirmed pins")
    }
    func testDelayedLoadFromAccountACannotPublishIntoB() async {
        var release: CheckedContinuation<PinsResponse, Never>?
        var calls = 0
        let m = PinManager(defaults: defaults, serverLoad: {
            calls += 1
            if calls == 1 { return await withCheckedContinuation { release = $0 } }
            return PinsResponse(events: [200], futures: [])
        })
        bind(m, "A")
        let oldLoad = Task { await m.loadPins() }
        while release == nil { await Task.yield() }
        bind(m, "B")
        await m.loadPins()
        release?.resume(returning: PinsResponse(events: [100], futures: [101]))
        await oldLoad.value
        XCTAssertEqual(m.pinnedEventIDs, [200])
        XCTAssertTrue(m.pinnedFuturesIDs.isEmpty)
    }
    func testDelayedFailedSaveCannotRollbackOrShowFeedbackInB() async {
        var release: CheckedContinuation<Void, Never>?
        let m = PinManager(defaults: defaults, serverLoad: { PinsResponse(events: [1], futures: []) }, serverSync: { _, _, _ in
            await withCheckedContinuation { release = $0 }
            throw Failed()
        })
        bind(m, "A")
        await m.loadPins()
        let oldRemove = m.togglePin(type: "event", id: 1)
        while release == nil { await Task.yield() }
        bind(m, "B")
        release?.resume()
        await oldRemove?.value
        XCTAssertTrue(m.savedPins.isEmpty)
        XCTAssertNil(m.feedback)
        XCTAssertTrue(m.savingKeys.isEmpty)
    }
    func testDelayedSuccessfulSaveCannotShowConfirmationInB() async {
        var release: CheckedContinuation<Void, Never>?
        let m = PinManager(defaults: defaults, serverLoad: { PinsResponse(events: [], futures: []) }, serverSync: { _, _, _ in
            await withCheckedContinuation { release = $0 }
        })
        bind(m, "A")
        await m.loadPins()
        let oldSave = m.togglePin(type: "event", id: 4)
        while release == nil { await Task.yield() }
        bind(m, "B")
        release?.resume()
        await oldSave?.value
        XCTAssertTrue(m.savedPins.isEmpty)
        XCTAssertNil(m.feedback)
    }
    func testLogoutRestoresGuestPinsWithoutAccountPins() async {
        let m = PinManager(defaults: defaults, serverLoad: { PinsResponse(events: [99], futures: []) })
        bind(m, nil, authenticated: false)
        m.togglePin(type: "event", id: 5)
        bind(m, "A")
        await m.loadPins()
        XCTAssertEqual(m.pinnedEventIDs, [99])
        bind(m, nil, authenticated: false)
        XCTAssertEqual(m.pinnedEventIDs, [5])
    }
    func testRestoreIdentityIsNotGuestAndFailureDoesNotExposeAccountPins() async {
        let m = PinManager(defaults: defaults, serverLoad: { PinsResponse(events: [99], futures: []) })
        bind(m, "A")
        await m.loadPins()
        bind(m, "A", authenticated: false)
        XCTAssertNil(m.togglePin(type: "event", id: 99))
        XCTAssertTrue(m.isPinned(type: "event", id: 99))
        bind(m, nil, authenticated: false)
        XCTAssertTrue(m.savedPins.isEmpty)
    }
    func testLoadFailureIsNotEmptyAndRetainsOnlySameAccountCache() async {
        var fail = false
        let m = PinManager(defaults: defaults, serverLoad: {
            if fail { throw Failed() }
            return PinsResponse(events: [42], futures: [])
        })
        bind(m, "A")
        await m.loadPins()
        fail = true
        await m.loadPins()
        XCTAssertEqual(m.loadState, .failed)
        XCTAssertEqual(m.pinnedEventIDs, [42])
        bind(m, "B")
        await m.loadPins()
        XCTAssertEqual(m.loadState, .failed)
        XCTAssertTrue(m.savedPins.isEmpty)
    }
    func testLegacyAccountCacheIsNotImportedIntoGuestOrOtherAccount() {
        defaults.set(try! JSONEncoder().encode([77]), forKey: "bainluck_pinnedEvents")
        let m = PinManager(defaults: defaults, allowLegacyGuestPins: false)
        bind(m, nil, authenticated: false)
        XCTAssertTrue(m.savedPins.isEmpty)
        bind(m, "B")
        XCTAssertTrue(m.savedPins.isEmpty)
    }
    func testLegacyGuestPinsArePreservedOnDeviceWithNoRememberedAccount() {
        defaults.set(try! JSONEncoder().encode([77]), forKey: "bainluck_pinnedEvents")
        let m = PinManager(defaults: defaults, allowLegacyGuestPins: true)
        bind(m, nil, authenticated: false)
        XCTAssertEqual(m.pinnedEventIDs, [77])
    }
    func testRefreshKeepsUnrelatedPinsAndDoesNotUndoRemovalDuringRead() async {
        var release: CheckedContinuation<PinsResponse, Never>?
        var calls = 0
        let m = PinManager(defaults: defaults, serverLoad: {
            calls += 1
            if calls == 1 { return PinsResponse(events: [1], futures: []) }
            return await withCheckedContinuation { release = $0 }
        }, serverSync: { _, _, _ in })
        bind(m, "A")
        await m.loadPins()
        let refresh = Task { await m.loadPins() }
        while release == nil { await Task.yield() }
        await m.togglePin(type: "event", id: 1)?.value
        release?.resume(returning: PinsResponse(events: [1, 2], futures: [3]))
        await refresh.value
        XCTAssertEqual(m.pinnedEventIDs, [2])
        XCTAssertEqual(m.pinnedFuturesIDs, [3])
    }
    func testMissingAndFailedMetadataDoNotEraseSavedIDsOrDisableRemoval() async {
        let m = PinManager(defaults: defaults)
        m.togglePin(type: "event", id: 1)
        m.togglePin(type: "event", id: 2)
        let vm = PinManagementViewModel(lookup: { $0.value == 1 ? .unavailable : .failed })
        await vm.load(m.savedPins)
        XCTAssertEqual(vm.metadata[SavedPin(type: "event", value: 1)], .unavailable)
        XCTAssertEqual(vm.metadata[SavedPin(type: "event", value: 2)], .failed)
        XCTAssertEqual(m.savedPins.count, 2)
        m.togglePin(type: "event", id: 1)
        m.togglePin(type: "event", id: 2)
        XCTAssertTrue(m.savedPins.isEmpty)
    }
    func testMetadataConcurrencyIsBoundedToThreeAndEverySiblingCompletes() async {
        let probe = MetadataProbe()
        let vm = PinManagementViewModel(lookup: { await probe.lookup($0) })
        await vm.load((1...12).map { SavedPin(type: "event", value: $0) })
        let maximum = await probe.maximum
        XCTAssertLessThanOrEqual(maximum, 3)
        XCTAssertEqual(vm.metadata.count, 12)
    }
    func testColdRestoreStartsWithAccountCacheRatherThanLegacySharedIDs() {
        defaults.set(try! JSONEncoder().encode([77]), forKey: "bainluck_pinnedEvents")
        defaults.set(try! JSONEncoder().encode([42]), forKey: "bainluck_pins.user.A.Events")
        let m = PinManager(defaults: defaults, allowLegacyGuestPins: false,
                           initialBinding: PinAccountBinding(userID: "A", authenticated: false))
        XCTAssertEqual(m.pinnedEventIDs, [42])
        XCTAssertEqual(m.loadState, .loading)
    }
    func testNewAccountCannotAddUntilServerPinsAreKnown() async {
        var fail = true
        let m = PinManager(defaults: defaults, serverLoad: {
            if fail { throw Failed() }
            return PinsResponse(events: [], futures: [])
        }, serverSync: { _, _, _ in })
        bind(m, "A")
        XCTAssertNil(m.togglePin(type: "event", id: 1))
        await m.loadPins()
        XCTAssertNil(m.togglePin(type: "event", id: 1))
        fail = false
        await m.loadPins()
        await m.togglePin(type: "event", id: 1)?.value
        XCTAssertTrue(m.isPinned(type: "event", id: 1))
    }
    func testLimitWarningHasAccessibleDismissalAndKeepsDirectManagement() throws {
        let m = PinManager(defaults: defaults)
        for id in 1...6 { m.togglePin(type: "event", id: id) }
        m.togglePin(type: "event", id: 7)
        let warning = m.feedback!
        XCTAssertEqual(warning.managementType, "event")
        XCTAssertEqual(warning.managementAlertTitle, "Pin limit reached")
        m.dismissFeedback(id: warning.id)
        XCTAssertNil(m.feedback)
        m.togglePin(type: "event", id: 7)
        XCTAssertEqual(m.feedback?.managementType, "event", "a new limit tap still opens management")
        let sourceRoot = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent().appendingPathComponent("Bain Luck")
        let toast = try String(contentsOf: sourceRoot.appendingPathComponent("Components/PinFeedbackToast.swift"), encoding: .utf8)
        XCTAssertTrue(toast.contains("pinManager.dismissFeedback(id: feedback.id)"))
        XCTAssertTrue(toast.contains(".accessibilityLabel(\"Dismiss pin message\")"))
        XCTAssertTrue(toast.contains("Button(\"Manage pins\")"))
    }
    func testDismissalCannotClearNewerFeedbackOrManagementDestination() {
        let m = PinManager(defaults: defaults)
        m.togglePin(type: "event", id: 1)
        let oldID = m.feedback!.id
        m.togglePin(type: "event", id: 2)
        let newID = m.feedback!.id
        m.dismissFeedback(id: oldID)
        XCTAssertEqual(m.feedback?.id, newID)
        m.presentManagement(type: "event")
        let destinationID = m.managementPresentation?.id
        m.dismissFeedback(id: newID)
        XCTAssertEqual(m.managementPresentation?.id, destinationID)
    }
    func testUnknownPinCountShowsRefreshTitleRatherThanLimit() {
        let m = PinManager(defaults: defaults)
        bind(m, "A")
        m.togglePin(type: "event", id: 1)
        XCTAssertEqual(m.feedback?.managementAlertTitle, "Refresh saved pins")
        XCTAssertEqual(m.feedback?.managementType, "event")
        XCTAssertNotEqual(m.feedback?.managementAlertTitle, "Pin limit reached")
    }
    func testVisibleAndVoiceOverLabelsUseLoadedTitlesWithoutInternalIDs() {
        for type in ["event", "future"] {
            let pin = SavedPin(type: type, value: 15320964)
            XCTAssertEqual(pin.displayTitle(for: .available(title: "Yankees at Red Sox")), "Yankees at Red Sox")
            XCTAssertEqual(pin.removeLabel(for: .available(title: "Yankees at Red Sox")), "Remove Yankees at Red Sox")
            let cases: [PinMetadata?] = [nil, .unavailable, .failed, .available(title: "  ")]
            for metadata in cases {
                XCTAssertFalse(pin.displayTitle(for: metadata).contains("15320964"))
                XCTAssertFalse(pin.removeLabel(for: metadata).contains("15320964"))
            }
        }
        XCTAssertEqual(SavedPin(type: "event", value: 1).displayTitle(for: .unavailable), "A saved game that's no longer listed")
        XCTAssertEqual(SavedPin(type: "future", value: 1).displayTitle(for: .unavailable), "A saved market that's no longer listed")
    }
    func testEntryAndModalActionDoNotDependOnSelectedTabOrFeedRows() throws {
        let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent().appendingPathComponent("Bain Luck")
        let myStuff = try String(contentsOf: root.appendingPathComponent("Views/MyStuffView.swift"), encoding: .utf8)
        let button = try String(contentsOf: root.appendingPathComponent("Components/PinButton.swift"), encoding: .utf8)
        let list = try String(contentsOf: root.appendingPathComponent("Views/PinManagementView.swift"), encoding: .utf8)
        XCTAssertTrue(myStuff.contains("myStuffManagePins"))
        // #10011 superseded the feed-only `pinnedItems`: every saved pin now has
        // content, and a pin the feed carries still keeps its live feed card
        // (`testAPinTheFeedAlreadyCarriesKeepsItsFeedCard`).
        XCTAssertTrue(myStuff.contains("SavedPinContent.section(pins: pinManager.savedPins, feed: vm.items"), "pins in the feed keep their existing live cards")
        XCTAssertTrue(myStuff.contains("feedSection(title: \"Pinned\""))
        XCTAssertTrue(button.contains("if isPresented, let feedback"))
        XCTAssertTrue(button.contains("Button(\"Manage pins\") { showPinManagement = true }"))
        XCTAssertTrue(list.contains("pinManager.savedPins.filter"))
        XCTAssertFalse(list.contains("vm.items"))
        XCTAssertTrue(list.contains(".accessibilityLabel(pin.removeLabel(for: vm.metadata[pin]))"))
        XCTAssertTrue(button.contains(".alert(managementAlertTitle,"))
        XCTAssertTrue(button.contains("managementAlertTitle = feedback.managementAlertTitle"))
    }
}

private actor MetadataProbe {
    private var active = 0
    private(set) var maximum = 0
    func lookup(_ pin: SavedPin) async -> PinMetadata {
        active += 1
        maximum = max(maximum, active)
        try? await Task.sleep(nanoseconds: 1_000_000)
        active -= 1
        return pin.value == 1 ? .failed : .available(title: pin.fallbackTitle)
    }
}
