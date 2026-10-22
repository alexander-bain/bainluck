import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// #10090 — the iPhone twin of Speed's web observation readout (PR #11414).
/// The details popover names the displayed probability's own observation time
/// to the millisecond, how many forward observations this page visit has
/// shown, and whether the value on screen arrived as a preview (DNPL) or
/// committed. Driven through the real view model and stream rig, so the clock,
/// the count and the delivery are what the hero's own readers see.
@MainActor
final class ObservationReadout10090Tests: XCTestCase {
    private static let id = 4242

    private static func date(_ stamp: String) -> Date { stamp.asDate! }
    private static func quoted(_ stamp: String) -> String { "\"\(stamp)\"" }

    private static func blendJSON(_ seq: Int, _ p: Double, observed: String?, base: Int = 10,
                                  ttl: Int = 60_000) -> String {
        let clock = observed.map { #""display_observed_at":\#($0),"# } ?? ""
        return """
        {"event_id":\(id),"p":\(p),"status":"live","source":"polymarket","source_value":\(p),
         "observed_at":"2026-10-20T19:00:59+00:00",\(clock)"provisional":true,
         "preview":{"kind":"blend","epoch":1,"seq":\(seq),"base_rev":\(base),"ttl_ms":\(ttl),
                    "pending":{"polymarket":\(p)}}}
        """
    }

    private static func revokeJSON(_ seq: Int, through: Int) -> String {
        """
        {"event_id":\(id),"p":null,"status":"live","provisional":true,
         "preview":{"kind":"revoke","epoch":1,"seq":\(seq),"through_seq":\(through),"reason":"stale"}}
        """
    }

    private static func commit(_ rev: Int, _ p: Double, at: String) -> String {
        """
        {"event_id":\(id),"p":\(p),"source":"polymarket","source_value":\(p),"updated_at":"\(at)",
         "status":"live","rev":{"\(id)":\(rev)}}
        """
    }

    private static let decoder: JSONDecoder = {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }()

    /// Committed 60% at 19:00:00 on a singleton fold revision of this row.
    private static func detail(odds: String = #"{"home_probability":0.6,"away_probability":0.4}"#,
                               status: String = "live", heroSource: String = "blend",
                               sport: String = "basketball_nba") throws -> EventDetail {
        try decoder.decode(EventDetail.self, from: Data("""
        {"id":\(id),"sport":"\(sport)","home_team":"Home","away_team":"Away","status":"\(status)",
         "home_score":50,"away_score":48,"current_odds":\(odds),
         "hero_probability":0.6,"hero_probability_away":0.4,"hero_probability_source":"\(heroSource)",
         "hero_probability_observed_at":"2026-10-20T19:00:00Z","blend_fold_revision":{"4242":10},
         "win_probability_sources":{"polymarket":{"value":0.6,"updated_at":"2026-10-20T19:00:00Z"}}}
        """.utf8))
    }

    private static func history() throws -> EventHistoryResponse {
        let rows = [("2026-10-20T18:20:00Z", 0.5), ("2026-10-20T18:40:00Z", 0.55), ("2026-10-20T19:00:00Z", 0.6)]
        let points = rows.map { #"{"timestamp":"\#($0.0)","home_probability":\#($0.1)}"# }.joined(separator: ",")
        return try decoder.decode(EventHistoryResponse.self, from: Data("""
        {"event_id":\(id),"home_team":"Home","away_team":"Away","status":"live",
         "history":[\(points)],"aggregate_line":[\(points)],"win_prob_history":{"polymarket":[\(points)]}}
        """.utf8))
    }

    // MARK: - The counter

    func testTheCounterCountsTheFirstClockAndOnlyStrictlyNewerOnes() {
        var count = ObservationCount10090()
        count.observe(nil)
        XCTAssertEqual(count.count, 0, "an unknown clock is not an observation")
        count.observe(Self.date("2026-10-20T19:00:00Z"))
        XCTAssertEqual(count.count, 1, "the first valid displayed clock counts once")
        count.observe(Self.date("2026-10-20T19:00:00Z"))
        XCTAssertEqual(count.count, 1, "a repeat")
        count.observe(Self.date("2026-10-20T18:59:00Z"))
        XCTAssertEqual(count.count, 1, "a backwards clock")
        XCTAssertEqual(count.highWater, Self.date("2026-10-20T19:00:00Z"), "and it never lowers the maximum")
        count.observe(Self.date("2026-10-20T19:00:00.001Z"))
        XCTAssertEqual(count.count, 2, "one millisecond newer is newer")
        count.observe(Self.date("2026-10-20T19:00:00Z"))
        count.observe(Self.date("2026-10-20T19:00:00.001Z"))
        XCTAssertEqual(count.count, 2, "a return to the earlier maximum")
        count.observe(nil)
        XCTAssertEqual(count.count, 2)
    }

    // MARK: - The held page

    private final class FakeHandle: LiveStreamHandle, @unchecked Sendable {
        private var handlers: [String: [@MainActor (String) -> Void]] = [:]
        var isClosed = false
        func on(_ event: String, _ handler: @escaping @MainActor (String) -> Void) {
            handlers[event, default: []].append(handler)
        }
        func close() { isClosed = true }
        @MainActor func fire(_ event: String, _ data: String = "") {
            for h in handlers[event] ?? [] { h(data) }
        }
    }

    private struct Client: EventDetailProviding {
        struct Declined: Error {}
        let event: EventDetail
        let history: EventHistoryResponse
        func fetchEvent(id: Int) async throws -> EventDetail { event }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse { history }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse { throw Declined() }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse { throw Declined() }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Declined() }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse { throw Declined() }
    }

    private final class Clock { var t: TimeInterval = 1_760_000_000 }

    private func heldPage() async throws -> (EventDetailViewModel, FakeHandle, Clock) {
        let handle = FakeHandle()
        let clock = Clock()
        let vm = EventDetailViewModel(
            eventId: Self.id,
            client: Client(event: try Self.detail(), history: try Self.history()),
            makeStreamHandle: { _ in handle },
            now: { clock.t },
            sleep: { _ in try? await Task.sleep(nanoseconds: 60_000_000_000) }
        )
        await vm.load()
        let deadline = Date().addingTimeInterval(5)
        while vm.history == nil, Date() < deadline { try? await Task.sleep(nanoseconds: 10_000_000) }
        XCTAssertNotNil(vm.history)
        return (vm, handle, clock)
    }

    /// One hero render, read the way `probabilityDetails` reads it.
    private func render(_ vm: EventDetailViewModel) throws -> ObservationReadout10090 {
        let event = try XCTUnwrap(vm.event)
        return vm.displayedObservation(printsPrice: EventDetailView.heroPrintsPrice(vm.headline(event)))
    }

    private static let committedClock = date("2026-10-20T19:00:00Z")

    /// THE SHIP: the readout follows the displayed value — committed, then an
    /// admitted preview at its own clock, then a newer one — and counts each
    /// forward observation once, however many times the page renders.
    func testTheReadoutDatesCountsAndNamesTheDeliveryOfTheDisplayedValue() async throws {
        let (vm, handle, clock) = try await heldPage()
        defer { vm.stopRefresh() }
        handle.fire("open")
        XCTAssertEqual(try render(vm), ObservationReadout10090(
            observedAt: Self.committedClock, count: 1, delivery: .committed))

        // Age ticks and re-renders of the same value count nothing.
        for _ in 0..<3 { clock.t += 1; _ = try render(vm) }
        XCTAssertEqual(try render(vm).count, 1)

        handle.fire("preview", Self.blendJSON(1, 0.751, observed: Self.quoted("2026-10-20T19:00:04.250Z")))
        XCTAssertEqual(try render(vm), ObservationReadout10090(
            observedAt: Self.date("2026-10-20T19:00:04.250Z"), count: 2, delivery: .dnpl))
        XCTAssertEqual(try render(vm).count, 2, "the same preview rendered again")

        // A replay cannot move the time or the count.
        handle.fire("preview", Self.blendJSON(1, 0.751, observed: Self.quoted("2026-10-20T19:00:40Z")))
        XCTAssertEqual(try render(vm), ObservationReadout10090(
            observedAt: Self.date("2026-10-20T19:00:04.250Z"), count: 2, delivery: .dnpl))

        handle.fire("preview", Self.blendJSON(2, 0.754, observed: Self.quoted("2026-10-20T19:00:09Z")))
        XCTAssertEqual(try render(vm), ObservationReadout10090(
            observedAt: Self.date("2026-10-20T19:00:09Z"), count: 3, delivery: .dnpl))

        // Revoked: the committed value returns on its own OLDER clock, shown
        // honestly and uncounted.
        handle.fire("preview", Self.revokeJSON(3, through: 2))
        XCTAssertEqual(try render(vm), ObservationReadout10090(
            observedAt: Self.committedClock, count: 3, delivery: .committed))

        // A newer commit is a forward observation, delivered committed.
        handle.fire("probability", Self.commit(11, 0.72, at: "2026-10-20T19:00:12Z"))
        XCTAssertEqual(try render(vm), ObservationReadout10090(
            observedAt: Self.date("2026-10-20T19:00:12Z"), count: 4, delivery: .committed))
        XCTAssertEqual(vm.event?.heroProbabilityObservedAt, "2026-10-20T19:00:12Z")
    }

    /// A shown preview with no clock, or a clock behind the maximum, is shown
    /// as what it is: the delivery is still the preview, the time is
    /// unavailable or older, and the count holds.
    func testAnUnknownOrBackwardsPreviewClockIsShownHonestlyAndNotCounted() async throws {
        let (vm, handle, _) = try await heldPage()
        defer { vm.stopRefresh() }
        handle.fire("open")
        XCTAssertEqual(try render(vm).count, 1)

        handle.fire("preview", Self.blendJSON(1, 0.8, observed: nil))
        let unknown = try render(vm)
        XCTAssertEqual(unknown, ObservationReadout10090(observedAt: nil, count: 1, delivery: .dnpl))
        XCTAssertEqual(unknown.timeText(), "Time unavailable")

        handle.fire("preview", Self.blendJSON(2, 0.82, observed: Self.quoted("2026-10-20T18:59:50Z")))
        XCTAssertEqual(try render(vm), ObservationReadout10090(
            observedAt: Self.date("2026-10-20T18:59:50Z"), count: 1, delivery: .dnpl))
    }

    /// The `vs` arm prints no price, so it owns no clock: whatever the
    /// committed or preview clock says, it reads unavailable and unknown and
    /// counts nothing. The page's count so far is kept.
    func testAnArmThatPrintsNoPriceOwnsNoClockAndCountsNothing() async throws {
        let (vm, handle, _) = try await heldPage()
        defer { vm.stopRefresh() }
        handle.fire("open")
        XCTAssertEqual(vm.displayedObservation(printsPrice: false),
                       ObservationReadout10090(observedAt: nil, count: 0, delivery: .unknown))
        handle.fire("preview", Self.blendJSON(1, 0.8, observed: Self.quoted("2026-10-20T19:00:04Z")))
        XCTAssertEqual(vm.displayedObservation(printsPrice: false),
                       ObservationReadout10090(observedAt: nil, count: 0, delivery: .unknown),
                       "not from the preview pipeline being active")
        XCTAssertEqual(try render(vm).count, 1, "the first printed value counts 1")
        XCTAssertEqual(vm.displayedObservation(printsPrice: false).count, 1)
    }

    /// The fallback guard: the readout's clock belongs to a printed priced
    /// pair only. An opening-line hero (a held historical number) and a
    /// missing price never borrow the hero clock.
    func testOnlyAPrintedPricedPairOwnsTheClock() throws {
        XCTAssertTrue(EventDetailView.heroPrintsPrice(try Self.detail()))
        XCTAssertFalse(EventDetailView.heroPrintsPrice(try Self.detail(odds: "null")), "the vs arm")
        XCTAssertFalse(EventDetailView.heroPrintsPrice(
            try Self.detail(status: "scheduled", heroSource: "opening")), "an opening line")
        XCTAssertTrue(EventDetailView.heroPrintsPrice(
            try Self.detail(status: "live", heroSource: "opening")),
                      "the opening arm is pre-game only; a live page prints its pushed price")
        XCTAssertTrue(EventDetailView.heroPrintsPrice(try Self.detail(
            odds: #"{"home_probability":0.6,"away_probability":null}"#, sport: "soccer_epl")),
                      "a draw-priced sport prints its home chance alone")
    }

    // MARK: - The words

    func testTheClockReadsToTheMillisecondInLocalTimeWithItsZone() throws {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = try XCTUnwrap(TimeZone(identifier: "America/Los_Angeles"))
        let locale = Locale(identifier: "en_US")
        let at = Self.date("2026-10-20T19:00:04.250Z")
        let sameDay = ObservationReadout10090.clock(at, now: at.addingTimeInterval(30),
                                                    calendar: calendar, locale: locale)
        XCTAssertTrue(sameDay.contains("12:00:04.250"), sameDay)
        XCTAssertTrue(sameDay.contains("PDT"), sameDay)
        XCTAssertFalse(sameDay.contains("2026"), "today's clock carries no date: \(sameDay)")
        let earlier = ObservationReadout10090.clock(at, now: at.addingTimeInterval(86_400 * 2),
                                                    calendar: calendar, locale: locale)
        XCTAssertTrue(earlier.contains("Oct 20, 2026"), earlier)
        XCTAssertTrue(earlier.contains("12:00:04.250"), earlier)
        XCTAssertEqual(ObservationReadout10090(observedAt: nil, count: 0, delivery: .unknown).timeText(),
                       "Time unavailable")
    }

    /// Web's words, so one recording reads both clients.
    func testTheDeliveryAndCountWordsMatchTheWebReadout() {
        XCTAssertEqual(ObservationDelivery10090.dnpl.label, "DNPL active")
        XCTAssertEqual(ObservationDelivery10090.committed.label, "Committed delivery")
        XCTAssertEqual(ObservationDelivery10090.unknown.label, "Delivery unknown")
        XCTAssertEqual(ObservationReadout10090(observedAt: nil, count: 3, delivery: .dnpl).countText,
                       "3 · first + newer times")
        XCTAssertEqual(ObservationReadout10090.timeLabel, "Probability observed")
        XCTAssertEqual(ObservationReadout10090.countLabel, "Observations shown")
        XCTAssertEqual(ObservationReadout10090.deliveryLabel, "Current probability delivery")
    }

    // MARK: - The rendered popover

    private func renderedText(_ view: some View, name: String) throws -> String {
        let host = hostForMeasurement(view.frame(width: 390).background(Color.white)
            .environment(\.scenePhase, .active).environment(\.colorScheme, .light), at: .large)
        host.view.frame = CGRect(x: 0, y: 0, width: 390, height: 560)
        let window = UIWindow(frame: host.view.frame)
        window.rootViewController = host
        window.isHidden = false
        defer { window.isHidden = true }
        let until = Date().addingTimeInterval(0.15)
        repeat {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: min(until, Date().addingTimeInterval(0.01)))
        } while Date() < until
        let image = UIGraphicsImageRenderer(bounds: host.view.bounds).image { _ in
            host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("readout10090-\(name).png")
        try XCTUnwrap(image.pngData()).write(to: url)
        print("Readout10090 rendered evidence: \(url.path)")
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        try VNImageRequestHandler(cgImage: XCTUnwrap(image.cgImage)).perform([request])
        return (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }.joined(separator: " ")
    }

    func testThePopoverPrintsTheReadoutBelowTheReceiptAndNothingNewWithoutIt() throws {
        let observed = Date().addingTimeInterval(-3)
        let readout = ObservationReadout10090(observedAt: observed, count: 3, delivery: .dnpl)
        let reveal = FreshnessRevealView(status: .live, lastReceivedAt: Date().addingTimeInterval(-2),
                                         confidenceTier: "high")
        let text = try renderedText(reveal.environment(\.observationReadout10090, readout), name: "with")
        for words in ["Received on this device", "Probability observed", "Observations shown",
                      "first + newer times", "Current probability delivery", "DNPL active", "High confidence"] {
            XCTAssertTrue(text.contains(words), "\(words) missing: \(text)")
        }
        let millis = String(format: ".%03d", Int(observed.timeIntervalSince1970 * 1000) % 1000)
        XCTAssertTrue(text.contains(millis), "the observed time to the millisecond (\(millis)): \(text)")
        let order = ["Received on this device", "Probability observed", "High confidence"]
            .compactMap { text.range(of: $0)?.lowerBound }
        XCTAssertEqual(order, order.sorted(), "receipt, then the readout, then confidence: \(text)")

        let plain = try renderedText(reveal, name: "without")
        XCTAssertTrue(plain.contains("Received on this device"), plain)
        for words in ["Probability observed", "Observations shown", "DNPL"] {
            XCTAssertFalse(plain.contains(words), "elsewhere the popover is unchanged: \(plain)")
        }
    }

    // MARK: - The page's wiring

    private static func source(_ relative: String) throws -> String {
        let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        return try String(contentsOf: root.appendingPathComponent(relative), encoding: .utf8)
            .filter { !$0.isWhitespace }
    }

    /// The readout is read in the disclosure's body — on every hero render,
    /// not only when the popover opens — from the headline the hero prints,
    /// and handed to the one popover the page mounts.
    func testTheDisclosureReadsTheHeadlineOnEveryRenderAndHandsItToThePopover() throws {
        let page = try Self.source("Bain Luck/Views/EventDetailView.swift")
        let head = try XCTUnwrap(page.range(
            of: "privatefuncprobabilityDetails(confidenceTier:String?,statusInDetails:Bool=false)->someView{"))
        let tail = try XCTUnwrap(page.range(of: "//MARK:-ChartHeaderBar", range: head.upperBound..<page.endIndex))
        let body = String(page[head.upperBound..<tail.lowerBound])
        let read = try XCTUnwrap(body.range(of:
            "letobservation=vm.displayedObservation(printsPrice:vm.event.map{Self.heroPrintsPrice(vm.headline($0))}??false)"))
        let button = try XCTUnwrap(body.range(of: "returnButton{showProbabilityDetails.toggle()}"))
        XCTAssertLessThan(read.lowerBound, button.lowerBound, "outside the popover's lazy content")
        let popover = try XCTUnwrap(body.range(of: ".popover(isPresented:$showProbabilityDetails"))
        let handed = try XCTUnwrap(body.range(of: ".environment(\\.observationReadout10090,observation)"))
        XCTAssertLessThan(popover.lowerBound, handed.lowerBound)
        XCTAssertEqual(page.components(separatedBy: "vm.displayedObservation(").count - 1, 1)
        XCTAssertEqual(page.components(separatedBy: "FreshnessRevealView(").count - 1, 1, "one popover")

        let feedback = try Self.source("Bain Luck/Components/LivePriceChangeFeedback.swift")
        XCTAssertTrue(feedback.contains("@Environment(\\.observationReadout10090)privatevarobservation"))
        let rows = try XCTUnwrap(feedback.range(of: "ObservationReadoutRows10090(readout:observation,now:.now)"))
        let receipt = try XCTUnwrap(feedback.range(of: "Text(\"Nonewerprobabilityupdatereceivedsinceopeningthispage.\")"))
        let tier = try XCTUnwrap(feedback.range(of: "iflettier=Confidence.normalize(confidenceTier)"))
        XCTAssertLessThan(receipt.lowerBound, rows.lowerBound)
        XCTAssertLessThan(rows.lowerBound, tier.lowerBound)
    }

    /// The view model reads the displayed value's own clock and the
    /// headline's own preview admission — never the rollout flag, a source's
    /// freshness or identity.
    func testTheReadoutReadsTheDisplayedClockAndPreviewAdmissionOnly() throws {
        let model = try Self.source("Bain Luck/ViewModels/EventDetailViewModel.swift")
        let head = try XCTUnwrap(model.range(of: "funcdisplayedObservation(printsPrice:Bool)->ObservationReadout10090{"))
        let tail = try XCTUnwrap(model.range(of: "funcchartFrames(", range: head.upperBound..<model.endIndex))
        let body = String(model[head.upperBound..<tail.lowerBound])
        XCTAssertTrue(body.contains("letobservedAt=displayedProbabilityObservedAt(event)"))
        XCTAssertTrue(body.contains("BlendPreview.displayed(blendPreview,held:event,now:now())!=nil"))
        for forbidden in ["streamDelivering", "foldedPreviews", "winProbabilitySources", "liveUpdateStatus",
                          "priceActivity", "heroProbabilitySource", "receivedAt"] {
            XCTAssertFalse(body.contains(forbidden), forbidden)
        }
    }
}
