import XCTest
@testable import Bain_Luck

/// #10090 / #11564 — the v3 reader against the shared contract R2
/// (`docs/contracts/dnpl-authority-v3.md` 656d3802, examples 92135a21). The six
/// messages below are the fixture's, verbatim; each test names the fixture
/// transition it pays. Redis lost the history that ordered v1/v2 epochs, so a
/// v3 page enters a durable domain only through a validated open, and the
/// existing singleton/folded rules then order frames inside it.
@MainActor
final class AV3OpenNamesTheDomainAndItsSession10090Tests: XCTestCase {
    private static let singletonOpen = #"{"protocol":3,"event_id":42,"authority":{"incarnation":"1","namespace":"11111111-1111-4111-8111-111111111111"},"stream_session":"aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa","members":[42]}"#
    private static let singletonBlend = #"{"protocol":3,"event_id":42,"authority":{"incarnation":"1","namespace":"11111111-1111-4111-8111-111111111111"},"stream_session":"aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa","frame":{"event_id":42,"p":0.6,"p_away":0.4,"sport":"tennis_atp","status":"live","display_observed_at":"2026-10-25T17:00:00.000Z","preview":{"kind":"blend","epoch":2,"seq":1,"base_rev":10,"ttl_ms":800}}}"#
    private static let singletonRevoke = #"{"protocol":3,"event_id":42,"authority":{"incarnation":"1","namespace":"11111111-1111-4111-8111-111111111111"},"stream_session":"aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa","frame":{"event_id":42,"p":null,"preview":{"kind":"revoke","epoch":2,"seq":2,"through_seq":1}}}"#
    private static let foldedOpen = #"{"protocol":3,"event_id":42,"authority":{"incarnation":"1","namespace":"11111111-1111-4111-8111-111111111111"},"stream_session":"bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb","members":[42,43]}"#
    private static let foldedBlend = #"{"protocol":3,"event_id":42,"authority":{"incarnation":"1","namespace":"11111111-1111-4111-8111-111111111111"},"stream_session":"bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb","frame":{"event_id":42,"p":0.6,"p_away":0.4,"sport":"tennis_atp","status":"live","display_observed_at":"2026-10-25T17:00:00.000Z","preview":{"kind":"blend","folded_version":2,"fold_session":"bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb","fold_seq":1,"base_fold_revision":{"42":10,"43":20},"origin_authority":{"42":{"epoch":2,"seq":1,"state":"pending","ttl_ms":800},"43":{"epoch":3,"seq":1,"state":"pending","ttl_ms":900}},"ttl_ms":800}}}"#
    private static let foldedRevoke = #"{"protocol":3,"event_id":42,"authority":{"incarnation":"1","namespace":"11111111-1111-4111-8111-111111111111"},"stream_session":"bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb","frame":{"event_id":42,"p":null,"preview":{"kind":"revoke","folded_version":2,"fold_session":"bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb","fold_seq":2,"base_fold_revision":{"42":10,"43":20},"origin_authority":{"42":{"epoch":2,"seq":1,"state":"expired"},"43":{"epoch":3,"seq":1,"state":"revoked"}},"ttl_ms":0}}}"#

    private static let one = "11111111-1111-4111-8111-111111111111"
    private static let two = "22222222-2222-4222-8222-222222222222"
    private static let sessionA = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"

    // MARK: - Helpers

    private func page(_ members: Set<String> = ["42"]) -> BlendPreviewReader {
        BlendPreview.readerAfterMembership(.empty, members: members)
    }

    private func open(_ reader: BlendPreviewReader, _ raw: String) throws -> BlendPreviewReader {
        BlendPreview.readerOpenedV3(reader, try XCTUnwrap(PreviewEnvelopeV3.decode(raw, kind: .open, eventId: 42), raw))
    }

    private func frame(_ reader: BlendPreviewReader, _ raw: String, now: TimeInterval = 0) -> BlendPreviewReader {
        guard let envelope = PreviewEnvelopeV3.decode(raw, kind: .preview, eventId: 42) else { return reader }
        return BlendPreview.readerAfterV3(reader, envelope, eventId: 42, now: now)
    }

    /// `raw` with every `old` replaced.
    private func with(_ raw: String, _ replacements: [String: String]) -> String {
        replacements.reduce(raw) { $0.replacingOccurrences(of: $1.key, with: $1.value) }
    }

    private func newDomain(_ raw: String, session: String = "dddddddd-dddd-4ddd-8ddd-dddddddddddd") -> String {
        with(raw, [#""incarnation":"1""#: #""incarnation":"2""#, Self.one: Self.two, Self.sessionA: session])
    }

    // MARK: - The envelope

    func testEveryFixtureMessageDecodesAsItsOwnKindOnly() {
        for raw in [Self.singletonOpen, Self.foldedOpen] {
            XCTAssertNotNil(PreviewEnvelopeV3.decode(raw, kind: .open, eventId: 42))
            XCTAssertNil(PreviewEnvelopeV3.decode(raw, kind: .preview, eventId: 42))
        }
        for raw in [Self.singletonBlend, Self.singletonRevoke, Self.foldedBlend, Self.foldedRevoke] {
            XCTAssertNotNil(PreviewEnvelopeV3.decode(raw, kind: .preview, eventId: 42))
            XCTAssertNil(PreviewEnvelopeV3.decode(raw, kind: .open, eventId: 42))
            XCTAssertNotNil(PreviewEnvelopeV3.decode(raw, kind: .preview, eventId: 42)?.frame())
        }
        XCTAssertNil(PreviewEnvelopeV3.decode(Self.singletonOpen, kind: .open, eventId: 43), "another page's stream")
    }

    func testTheOuterEnvelopeIsExactWhileTheInnerFrameKeepsItsAdditiveRules() {
        func refused(_ raw: String, _ kind: PreviewEnvelopeV3.Kind = .preview, _ why: String) {
            XCTAssertNil(PreviewEnvelopeV3.decode(raw, kind: kind, eventId: 42), why)
        }
        refused(with(Self.singletonBlend, [#""protocol":3,"#: #""protocol":3,"x":1,"#]), .preview, "unknown outer key")
        refused(with(Self.singletonBlend, [#""namespace":"#: #""x":1,"namespace":"#]), .preview, "unknown authority key")
        refused(with(Self.singletonBlend, [#""protocol":3"#: #""protocol":2"#]), .preview, "another protocol")
        refused(with(Self.singletonBlend, [#""incarnation":"1""#: #""incarnation":1"#]), .preview, "a JSON number")
        refused(with(Self.singletonBlend, [#""incarnation":"1""#: #""incarnation":"01""#]), .preview, "noncanonical")
        refused(with(Self.singletonBlend, [Self.sessionA: Self.sessionA.uppercased()]), .preview, "uppercase session")
        refused(with(Self.singletonBlend, [#""p":0.6,"#: #""p":0.6,"p":0.7,"#]), .preview, "a duplicate inner key")
        refused(with(Self.singletonOpen, ["[42]": "[43,42]"]), .open, "members out of order")
        refused(with(Self.singletonOpen, ["[42]": "[43]"]), .open, "the page row missing")
        refused(with(Self.singletonOpen, ["[42]": "[42,42]"]), .open, "a repeated row")
        refused(with(Self.singletonOpen, ["[42]": "[" + (1...33).map(String.init).joined(separator: ",") + "]"]),
                .open, "33 rows")
        let padded = with(Self.singletonBlend, [#""sport":"#: #""pad":"\#(String(repeating: "x", count: 16 * 1024))","sport":"#])
        refused(padded, .preview, "over 16 KiB")
        // lane1b O1: the bound is inclusive — exactly 16384 bytes is a message.
        func pad(_ count: Int) -> String {
            with(Self.singletonBlend, [#""sport":"#: #""pad":"\#(String(repeating: "x", count: count))","sport":"#])
        }
        let room = BlendPreviewFrame.maxFrameBytes - pad(0).utf8.count
        XCTAssertEqual(pad(room).utf8.count, 16384)
        XCTAssertNotNil(PreviewEnvelopeV3.decode(pad(room), kind: .preview, eventId: 42)?.frame(), "16384 bytes")
        refused(pad(room + 1), .preview, "16385 bytes")
        let additive = with(Self.singletonBlend, [#""kind":"blend","#: #""kind":"blend","pending":{"kalshi":0.6},"#])
        XCTAssertNotNil(PreviewEnvelopeV3.decode(additive, kind: .preview, eventId: 42)?.frame(),
                        "an inner additive key alone refuses nothing")
    }

    // MARK: - Fixture transitions

    func testLegacyMaximumToV3EntersAndPreservesCommittedFloors() throws {
        var reader = page()
        reader.epoch = FoldRevision.maxSafeInteger
        reader = BlendPreview.readerAfterCommitFloor(reader, FoldRevision(["42": 9]))
        let entered = try open(reader, Self.singletonOpen)
        XCTAssertEqual(entered.v3Authority?.incarnation, 1)
        XCTAssertEqual(entered.epoch, -1, "a legacy epoch never orders the v3 domain")
        XCTAssertEqual(entered.floors, FoldRevision(["42": 9]))
        XCTAssertEqual(frame(entered, Self.singletonBlend).held?.p, 0.6)
    }

    func testAFrameWithoutAnOpenIsRefused() {
        XCTAssertNil(frame(page(), Self.singletonBlend).held)
    }

    func testASameDomainReconnectRetiresTheHeldPreviewAndKeepsItsOrderAndDeadline() throws {
        let shown = frame(try open(page(), Self.singletonOpen), Self.singletonBlend, now: 0)
        XCTAssertEqual(shown.held?.expiresAt, 0.8)
        let session = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
        let reopened = try open(BlendPreview.readerReset(shown), with(Self.singletonOpen, [Self.sessionA: session]))
        XCTAssertNil(reopened.held)
        XCTAssertEqual(reopened.v3Session, session)
        let replay = with(Self.singletonBlend, [Self.sessionA: session])
        XCTAssertNil(frame(reopened, replay, now: 0.1).held, "a new session cannot revive the tuple")
        let next = with(replay, [#""seq":1"#: #""seq":2"#])
        XCTAssertEqual(frame(reopened, next, now: 0.1).held?.p, 0.6)
    }

    func testADuplicateOpenOfTheActiveSessionIsANoOp() throws {
        let shown = frame(try open(page(), Self.singletonOpen), Self.singletonBlend)
        XCTAssertEqual(try open(shown, Self.singletonOpen), shown)
    }

    func testANewDomainRetiresPreviewIdentityKeepsFloorsAndRefusesTheOldDomain() throws {
        var reader = frame(try open(page(), Self.singletonOpen), Self.singletonBlend)
        reader = BlendPreview.readerAfterCommitFloor(reader, FoldRevision(["42": 10]))
        XCTAssertNotNil(reader.held)
        let moved = try open(reader, newDomain(Self.singletonOpen))
        XCTAssertNil(moved.held)
        XCTAssertEqual(moved.v3Authority?.incarnation, 2)
        XCTAssertEqual(moved.floors, FoldRevision(["42": 10]), "committed floors stay")
        XCTAssertTrue(moved.originFences.isEmpty && moved.legacyOrders.isEmpty, "old identities go")
        XCTAssertNil(frame(moved, Self.singletonBlend).held, "delayed_old_domain")
        // The new namespace's epochs restart: an old-domain tuple orders nothing.
        let fresh = with(newDomain(Self.singletonBlend), [#""epoch":2"#: #""epoch":1"#])
        XCTAssertEqual(frame(moved, fresh).held?.p, 0.6)
    }

    func testAnEqualIncarnationUnderAnotherNamespaceOrALowerOneIsRefusedUnchanged() throws {
        let entered = try open(page(), Self.singletonOpen)
        XCTAssertEqual(try open(entered, with(Self.singletonOpen, [Self.one: Self.two])), entered)
        let moved = try open(entered, newDomain(Self.singletonOpen))
        XCTAssertEqual(try open(moved, with(Self.singletonOpen, [Self.sessionA: "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"])),
                       moved, "a lower incarnation")
    }

    func testAnUncoveredCommittedFloorRefusesTheBlend() throws {
        let reader = BlendPreview.readerAfterCommitFloor(try open(page(), Self.singletonOpen), FoldRevision(["42": 11]))
        XCTAssertNil(frame(reader, Self.singletonBlend).held)
    }

    func testARetiredTupleIsNeverReplayed() throws {
        let revoked = frame(try open(page(), Self.singletonOpen), Self.singletonRevoke)
        XCTAssertNil(frame(revoked, Self.singletonBlend).held)
    }

    func testTheSameTupleArrivingLaterNeverExtendsItsDeadline() throws {
        let shown = frame(try open(page(), Self.singletonOpen), Self.singletonBlend, now: 0)
        let again = frame(shown, Self.singletonBlend, now: 0.2)
        XCTAssertEqual(again.held?.expiresAt, 0.8)
    }

    func testAnOpenThatDisagreesWithTheDetailMovesNothing() throws {
        let folded = page(["42", "43"])
        XCTAssertEqual(try open(folded, Self.singletonOpen), folded)
        XCTAssertFalse(BlendPreview.membershipReopens(folded, members: ["42", "43"]),
                       "a disagreeing open leaves the page's own membership change to reopen")
    }

    /// lane1b R1 on cb9a5e47d1: an open that arrives before the detail names
    /// any membership activates nothing, and is never replayed. The first
    /// adoption is not a membership change, so the refusal itself is what
    /// makes that adoption reopen the stream — and only the connection that
    /// was refused: a reset (open, close, reconnect) forgets it.
    func testAnOpenBeforeAnyMembershipActivatesNothingAndTheFirstAdoptionReopens() throws {
        let refused = try open(.empty, Self.foldedOpen)
        XCTAssertNil(refused.v3Authority)
        XCTAssertNil(refused.v3Session)
        XCTAssertNil(refused.foldSession)
        XCTAssertEqual(refused.v3Rows, [])
        XCTAssertTrue(refused.v3OpenAwaitingMembership)
        XCTAssertNil(frame(refused, Self.foldedBlend).held, "no session, so no frame")

        XCTAssertFalse(BlendPreview.membershipReopens(.empty, members: ["42", "43"]),
                       "with no refused open, the first membership is not a change")
        XCTAssertTrue(BlendPreview.membershipReopens(refused, members: ["42", "43"]))
        XCTAssertTrue(BlendPreview.membershipReopens(refused, members: ["42"]), "whatever membership it is")
        XCTAssertFalse(BlendPreview.membershipReopens(refused, members: []))
        let adopted = BlendPreview.readerAfterMembership(refused, members: ["42", "43"])
        XCTAssertFalse(adopted.v3OpenAwaitingMembership)
        XCTAssertFalse(BlendPreview.membershipReopens(adopted, members: ["42", "43"]), "it reopens once")
        XCTAssertFalse(BlendPreview.readerReset(refused).v3OpenAwaitingMembership, "the refused connection ended")

        // The reopened connection's open is admitted, never the refused one.
        let reopened = try open(BlendPreview.readerReset(adopted), Self.foldedOpen)
        XCTAssertEqual(reopened.v3Session, "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
        XCTAssertEqual(frame(reopened, Self.foldedBlend, now: 0).held?.p, 0.6)

        var saturated = BlendPreviewReader.empty
        saturated.evidenceSaturated = true
        XCTAssertEqual(try open(saturated, Self.foldedOpen), saturated, "a saturated visit records nothing")
    }

    func testTheShapeMustMatchTheOpensMembership() throws {
        let singleton = try open(page(), Self.singletonOpen)
        let foldedOnSingleton = with(Self.foldedBlend, ["bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb": Self.sessionA])
        XCTAssertNil(frame(singleton, foldedOnSingleton).held, "singleton_open_folded_payload")
        let folded = try open(page(["42", "43"]), Self.foldedOpen)
        let singletonOnFolded = with(Self.singletonBlend, [Self.sessionA: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"])
        XCTAssertNil(frame(folded, singletonOnFolded).held, "folded_open_singleton_payload")
    }

    func testAFoldedOpenAdmitsItsFoldedBlendAndRevoke() throws {
        let shown = frame(try open(page(["42", "43"]), Self.foldedOpen), Self.foldedBlend, now: 0)
        XCTAssertEqual(shown.held?.p, 0.6)
        XCTAssertEqual(shown.held?.baseFoldRevision, FoldRevision(["42": 10, "43": 20]))
        XCTAssertNil(frame(shown, Self.foldedRevoke, now: 0.1).held)
    }

    func testAHigherIncarnationKeepsARetiredMembersFloorAndClearsItsFence() throws {
        var reader = frame(try open(page(["42", "43"]), Self.foldedOpen), Self.foldedBlend)
        reader = BlendPreview.readerAfterCommitFloor(reader, FoldRevision(["42": 11, "43": 25]))
        reader = BlendPreview.readerAfterMembership(reader, members: ["42"])
        let retired = try XCTUnwrap(reader.retiredMembers.first { $0.row == "43" })
        XCTAssertNotNil(retired.fence)
        XCTAssertEqual(retired.floor, 25)
        let moved = try open(reader, newDomain(Self.singletonOpen))
        let kept = try XCTUnwrap(moved.retiredMembers.first { $0.row == "43" })
        XCTAssertNil(kept.fence, "the old domain's identity goes")
        XCTAssertEqual(kept.floor, 25, "its committed floor stays")
        XCTAssertEqual(moved.floors?.rows["42"], 11)
        XCTAssertTrue(moved.originFences.isEmpty)
    }

    func testANewIncarnationNeverResetsTheVisitsRowCount() throws {
        let rows = [42] + Array(1...31)
        let members = Set(rows.map(String.init))
        let list = rows.sorted().map(String.init).joined(separator: ",")
        let first = try open(page(members), with(Self.singletonOpen, ["[42]": "[\(list)]"]))
        XCTAssertEqual(first.v3Rows.count, 32)
        let moved = try open(first, newDomain(with(Self.singletonOpen, ["[42]": "[\(list)]"])))
        XCTAssertEqual(moved.v3Rows.count, 32, "incarnation_cannot_reset_visit_count")
        XCTAssertFalse(moved.evidenceSaturated)
        let changed = BlendPreview.readerAfterMembership(moved, members: ["42", "1000"])
        let joined = try open(changed, newDomain(with(Self.singletonOpen, ["[42]": "[42,1000]"]),
                                                 session: "ffffffff-ffff-4fff-8fff-ffffffffffff"))
        XCTAssertTrue(joined.evidenceSaturated, "a 33rd distinct row ends previews for the visit")
        XCTAssertNil(joined.held)
        XCTAssertNil(frame(joined, with(newDomain(Self.singletonBlend, session: "ffffffff-ffff-4fff-8fff-ffffffffffff"),
                                        [#""epoch":2"#: #""epoch":3"#])).held)
    }

    // MARK: - The controller and the page

    private final class TimedHandle: LiveStreamHandle, @unchecked Sendable {
        private var handlers: [String: [@MainActor (String) -> Void]] = [:]
        var isClosed = false
        var frameReceivedAt: TimeInterval?
        func on(_ event: String, _ handler: @escaping @MainActor (String) -> Void) {
            handlers[event, default: []].append(handler)
        }
        func close() { isClosed = true }
        func fire(_ event: String, _ data: String = "") {
            for handler in handlers[event] ?? [] { handler(data) }
        }
    }

    func testTheControllerRoutesV3AndEndsTheSessionOnReconnectButNotOnResync() {
        let handle = TimedHandle()
        var calls: [String] = []
        var receipts: [TimeInterval?] = []
        let controller = LiveStreamController(
            open: { handle }, now: { 100 }, onFrame: { _ in XCTFail("a preview is not a price") },
            onDeliveringChange: { _ in },
            onPreview: { _ in calls.append("legacy") },
            onPreviewInvalidate: { calls.append("invalidate") },
            onPreviewOpenV3: { _ in calls.append("open3") },
            onPreviewV3: { _, receivedAt in calls.append("preview3"); receipts.append(receivedAt) },
            onPreviewReset: { calls.append("reset") },
            schedule: { _, _ in {} })
        controller.start()
        handle.fire("open")
        handle.fire("preview_open_v3", Self.singletonOpen)
        handle.frameReceivedAt = 12.5
        handle.fire("preview_v3", Self.singletonBlend)
        XCTAssertEqual(calls, ["reset", "open3", "preview3"])
        XCTAssertEqual(receipts, [12.5], "the transport's receipt reaches the owner")
        calls.removeAll()
        handle.fire("resync", #"{"generation":1}"#)
        XCTAssertEqual(calls, ["invalidate"], "a resync withdraws the display and keeps the session")
        calls.removeAll()
        handle.fire("reconnect")
        XCTAssertEqual(calls, ["reset"], "a reconnect ends the session")
        calls.removeAll()
        handle.fire("preview_v3", Self.singletonBlend)
        XCTAssertEqual(calls, [], "the retired handle delivers nothing")
        controller.stop()
    }

    /// Contract D2: a transport `error` ends the v3 session at once — on the
    /// blip the same handle retries by itself as well as on the refusal that
    /// closes it — and so does a stream retired for silence. One reset each;
    /// the retry policy itself is unchanged.
    func testATransportErrorEndsTheSessionAtOnceWhetherOrNotTheHandleRetries() {
        var handles: [TimedHandle] = []
        var calls: [String] = []
        var clock: TimeInterval = 100
        var delivering: [Bool] = []
        let controller = LiveStreamController(
            open: { let h = TimedHandle(); handles.append(h); return h }, now: { clock },
            onFrame: { _ in XCTFail("a preview is not a price") },
            onDeliveringChange: { delivering.append($0) },
            onPreviewOpenV3: { _ in calls.append("open3") },
            onPreviewV3: { _, _ in calls.append("preview3") },
            onPreviewReset: { calls.append("reset") },
            schedule: { _, _ in {} })
        controller.start()
        let handle = handles[0]
        handle.fire("open")
        handle.fire("preview_open_v3", Self.singletonOpen)
        handle.fire("preview_v3", Self.singletonBlend)
        XCTAssertEqual(calls, ["reset", "open3", "preview3"])
        calls.removeAll()

        handle.fire("error")
        XCTAssertEqual(calls, ["reset"], "a blip the handle will retry ends the session now, not at the TTL")
        XCTAssertFalse(handle.isClosed, "the handle keeps retrying by itself")
        XCTAssertEqual(delivering, [true, false])
        XCTAssertEqual(handles.count, 1, "no new handle: the retry policy is unchanged")
        calls.removeAll()

        // The retry's own open on the SAME handle: still delivering, and
        // previews wait for its fresh `preview_open_v3`.
        handle.fire("open")
        handle.fire("preview_open_v3", Self.singletonOpen)
        XCTAssertEqual(calls, ["reset", "open3"])
        calls.removeAll()

        handle.isClosed = true
        handle.fire("error")
        XCTAssertEqual(calls, ["reset"], "a refusal ends it once, through stop()")
        calls.removeAll()
        handle.fire("preview_v3", Self.singletonBlend)
        handle.fire("error")
        XCTAssertEqual(calls, [], "the stopped stream's callbacks stay inert")

        // A second stream retired for transport silence ends its session too.
        var silentCalls: [String] = []
        let silent = TimedHandle()
        let quiet = LiveStreamController(
            open: { silent }, now: { clock }, onFrame: { _ in },
            onDeliveringChange: { _ in },
            onPreviewReset: { silentCalls.append("reset") },
            schedule: { _, _ in {} })
        quiet.start()
        silent.fire("open")
        silentCalls.removeAll()
        clock += LiveStreamTiming.silenceTimeout + 1
        quiet.tick()
        XCTAssertEqual(silentCalls, ["reset"], "silence retires the stream and its session")
        XCTAssertTrue(silent.isClosed)
    }

    /// Contract D2's reset withdraws the held preview and the session only:
    /// ordering, first-seen deadlines, committed floors and saturation stay.
    func testTheResetATransportErrorAppliesKeepsEveryPieceOfEvidence() throws {
        var reader = frame(try open(page(), Self.singletonOpen), Self.singletonBlend, now: 0)
        reader = BlendPreview.readerAfterCommitFloor(reader, FoldRevision(["42": 10]))
        reader.evidenceSaturated = true
        XCTAssertNotNil(reader.held)
        let reset = BlendPreview.readerReset(reader)
        XCTAssertNil(reset.held)
        XCTAssertNil(reset.v3Session, "a fresh open is required")
        XCTAssertEqual(reset.v3Authority, reader.v3Authority, "the domain stays")
        XCTAssertEqual(reset.floors, reader.floors)
        XCTAssertEqual(reset.originFences, reader.originFences, "fences and their first-seen deadlines stay")
        XCTAssertEqual(reset.legacyOrders, reader.legacyOrders)
        XCTAssertEqual(reset.retiredMembers, reader.retiredMembers)
        XCTAssertEqual(reset.epoch, reader.epoch)
        XCTAssertTrue(reset.evidenceSaturated)
    }

    private struct Client: EventDetailProviding {
        struct Declined: Error {}
        let event: EventDetail
        func fetchEvent(id: Int) async throws -> EventDetail { event }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse { throw Declined() }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse { throw Declined() }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse { throw Declined() }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Declined() }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse { throw Declined() }
    }

    private final class Clock { var t: TimeInterval = 1_760_000_000 }

    private static func detail() throws -> EventDetail {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventDetail.self, from: Data("""
        {"id":42,"sport":"tennis_atp","home_team":"Home","away_team":"Away","status":"live",
         "home_score":1,"away_score":0,
         "current_odds":{"home_probability":0.5,"away_probability":0.5},
         "hero_probability":0.5,"hero_probability_source":"blend",
         "hero_probability_observed_at":"2026-10-25T16:59:00Z","blend_fold_revision":{"42":10},
         "win_probability_sources":{"kalshi":{"value":0.5,"updated_at":"2026-10-25T16:59:00Z"}}}
        """.utf8))
    }

    /// The wait between the transport assembling a frame and the page handling
    /// it comes out of the preview's lifetime, never on top of it.
    func testThePageDatesAV3PreviewAtItsReceiptAndShowsItInTheHeadline() async throws {
        let handle = TimedHandle()
        let clock = Clock()
        let vm = EventDetailViewModel(
            eventId: 42, client: Client(event: try Self.detail()),
            makeStreamHandle: { _ in handle }, now: { clock.t },
            sleep: { _ in try? await Task.sleep(nanoseconds: 60_000_000_000) })
        defer { vm.stopRefresh() }
        await vm.load()
        handle.fire("open")
        handle.fire("preview", #"{"event_id":42,"p":0.9,"status":"live","preview":{"kind":"blend","epoch":1,"seq":1,"base_rev":10,"ttl_ms":60000}}"#)
        XCTAssertNil(vm.blendPreview, "a legacy preview is never read")
        handle.fire("preview_open_v3", Self.singletonOpen)
        let arrival = clock.t
        handle.frameReceivedAt = ProcessInfo.processInfo.systemUptime - 0.5
        handle.fire("preview_v3", Self.singletonBlend)
        let shown = try XCTUnwrap(vm.blendPreview)
        XCTAssertEqual(shown.p, 0.6)
        XCTAssertLessThanOrEqual(shown.expiresAt, arrival + 0.3 + 0.05, "800 ms less the 500 ms it waited")
        XCTAssertEqual(vm.headline(try XCTUnwrap(vm.event)).currentOdds?.homeProbability, 0.6)
        clock.t = arrival + 0.4
        XCTAssertEqual(vm.headline(try XCTUnwrap(vm.event)).currentOdds?.homeProbability, 0.5,
                       "expired on the receipt's clock")
        handle.fire("closed")
        XCTAssertNil(vm.blendPreview)
    }

    /// Contract D2 at the page: a transport error on a handle that will retry
    /// withdraws a minute-long preview at once. The retried connection shows
    /// nothing until a fresh `preview_open_v3`, never revives the retired
    /// tuple, and keeps the chart it already had.
    func testATransportErrorWithdrawsTheHeldPreviewAtOnceAndOnlyAFreshOpenResumes() async throws {
        let handle = TimedHandle()
        let clock = Clock()
        let vm = EventDetailViewModel(
            eventId: 42, client: Client(event: try Self.detail()),
            makeStreamHandle: { _ in handle }, now: { clock.t },
            sleep: { _ in try? await Task.sleep(nanoseconds: 60_000_000_000) })
        defer { vm.stopRefresh() }
        await vm.load()
        handle.fire("open")
        handle.fire("preview_open_v3", Self.singletonOpen)
        let minute = with(Self.singletonBlend, [#""ttl_ms":800"#: #""ttl_ms":60000"#])
        handle.fire("preview_v3", minute)
        let event = try XCTUnwrap(vm.event)
        XCTAssertEqual(vm.blendPreview?.p, 0.6)
        XCTAssertEqual(vm.headline(event).currentOdds?.homeProbability, 0.6)
        let chart = vm.liveBlend

        handle.fire("error")
        XCTAssertFalse(handle.isClosed, "the transport retries on this handle")
        XCTAssertNil(vm.blendPreview, "withdrawn at the error, a minute before its TTL")
        XCTAssertEqual(vm.headline(event).currentOdds?.homeProbability, 0.5, "committed truth shows")
        XCTAssertEqual(vm.liveBlend, chart, "the chart's history stays")

        let newer = with(minute, [#""seq":1"#: #""seq":2"#])
        handle.fire("preview_v3", newer)
        XCTAssertNil(vm.blendPreview, "the ended session admits nothing on the same handle")
        handle.fire("open")
        handle.fire("preview_v3", newer)
        XCTAssertNil(vm.blendPreview, "the retry's own open enables no preview")

        let session = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
        handle.fire("preview_open_v3", with(Self.singletonOpen, [Self.sessionA: session]))
        handle.fire("preview_v3", with(minute, [Self.sessionA: session]))
        XCTAssertNil(vm.blendPreview, "the retired tuple never revives: its fence survived the error")
        handle.fire("preview_v3", with(newer, [Self.sessionA: session]))
        XCTAssertEqual(vm.blendPreview?.p, 0.6, "a fresh open and a newer tuple resume")
    }
}
