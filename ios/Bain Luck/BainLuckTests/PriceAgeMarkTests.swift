import XCTest
@testable import Bain_Luck

private extension String {
    /// Swift source with `//` line comments and `/* */` block comments removed.
    ///
    /// Deliberately naive — it does not understand string literals containing
    /// `//`, and it does not need to: its only job is to stop a source scan being
    /// satisfied by the pattern appearing in the commentary that explains the
    /// pattern. Over-removal would make a scan fail closed (a false RED that a
    /// reader investigates), which is the safe direction; the false GREEN is the
    /// one that cost a live defect.
    func strippingComments() -> String {
        var out = ""
        var rest = Substring(self)
        while let open = rest.range(of: "/*") {
            out += rest[rest.startIndex..<open.lowerBound]
            guard let close = rest.range(of: "*/", range: open.upperBound..<rest.endIndex) else {
                rest = rest[rest.endIndex...]
                break
            }
            rest = rest[close.upperBound...]
        }
        out += rest

        return out
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map { line -> Substring in
                guard let slashes = line.range(of: "//") else { return line }
                return line[line.startIndex..<slashes.lowerBound]
            }
            .joined(separator: "\n")
    }
}

/// #6343 — the price-age mark's native half.
///
/// THE DEFECT, measured: `price_observed_at` has been on both futures-card
/// serializers since #5752 and `grep -rn price_observed_at ios/` returned 0 hits,
/// so the phone could not render an age even in principle. On `/api/feed?limit=25`
/// at 2026-09-15 09:5xZ, market `171` drew on a **77.7h** price and `60856903` on a
/// **59.2h** one — marked `● 3d ago` / `● 2d ago` on the website, unmarked here.
///
/// These assertions are about the CONTRACT the two platforms share, not about
/// layout:
///
///   1. **The rungs are web's rungs**, value for value, including the two that are
///      words. A second spelling is how a reader learns that "3d ago" and
///      "3 days ago" are two different facts.
///   2. **The bound is the cadence that should have replaced the price.** The
///      30-minute live bound on an hourly ladder is #5843's defect, and the
///      production read below is what makes that concrete rather than asserted.
///   3. **Absent is not fresh and not stale.** A price we cannot date is one we
///      cannot make a claim about, so nothing draws.
///   4. **The reveal says PRECISELY when** — Alex's word, 2026-08-29 — because the
///      relative age is the half he called ambiguous. The phone has no hover, so
///      it is a tap, and the sentence exists whenever the chip does.
final class PriceAgeMarkTests: XCTestCase {

    /// A fixed instant, so no assertion here branches on the clock (gotcha #44).
    private let now = Date(timeIntervalSince1970: 1_789_000_000)

    private func stamp(hoursAgo: Double) -> String {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f.string(from: now.addingTimeInterval(-hoursAgo * 3600))
    }

    // MARK: - 1. The rungs are web's rungs

    func testTheRungsMatchTheWebValueForValue() {
        // `frontend/lib/sourceAge.ts` `formatAgeFromSeconds`, rung for rung.
        XCTAssertEqual(SourceAge.formatAge(seconds: 0), "just now")
        XCTAssertEqual(SourceAge.formatAge(seconds: 59), "just now")
        XCTAssertEqual(SourceAge.formatAge(seconds: 60), "1m ago")
        XCTAssertEqual(SourceAge.formatAge(seconds: 59 * 60), "59m ago")
        XCTAssertEqual(SourceAge.formatAge(seconds: 60 * 60), "1h ago")
        XCTAssertEqual(SourceAge.formatAge(seconds: 23 * 3600), "23h ago")
        XCTAssertEqual(SourceAge.formatAge(seconds: 24 * 3600), "yesterday")
        XCTAssertEqual(SourceAge.formatAge(seconds: 47 * 3600), "yesterday")
        XCTAssertEqual(SourceAge.formatAge(seconds: 48 * 3600), "2d ago")
    }

    /// The two live specimens, by the ages they actually carried.
    func testTheTwoProductionSpecimensRenderTheAgesTheWebRenders() {
        // Market 171 — "Canadian Team to Win the Stanley Cup", 77.7h.
        XCTAssertEqual(SourceAge.format(stamp(hoursAgo: 77.7), now: now), "3d ago")
        // Market 60856903 — a PGA second-round ladder, 59.2h.
        XCTAssertEqual(SourceAge.format(stamp(hoursAgo: 59.2), now: now), "2d ago")
    }

    /// Rounded DOWN, which is the rule every age in this product already follows:
    /// "8 days ago" must never flatter to "7".
    func testAnAgeNeverFlatters() {
        XCTAssertEqual(SourceAge.format(stamp(hoursAgo: 71.9), now: now), "2d ago")
        XCTAssertEqual(SourceAge.format(stamp(hoursAgo: 72.1), now: now), "3d ago")
    }

    // MARK: - 2. The bound is the cadence, not a number tuned here

    func testTheTwoBoundsAreTheBackendsOwnNumbers() {
        XCTAssertEqual(SourceAge.liveStaleAfter, 30 * 60)
        // `STALE_PRICE_HOURS = 6.0` in `utils/tournament_register.py`.
        XCTAssertEqual(SourceAge.futuresStaleAfter, 6 * 60 * 60)
        XCTAssertEqual(SourceAge.Cadence.live.staleAfter, SourceAge.liveStaleAfter)
        XCTAssertEqual(SourceAge.Cadence.futures.staleAfter, SourceAge.futuresStaleAfter)
    }

    /// 🔴 THE #5843 DEFECT, PINNED ON THE REAL POPULATION.
    ///
    /// The feed read this shipped against held sixteen datable futures cards:
    /// fourteen at 0.7h and the two specimens above. Under the live bound the mark
    /// would draw on ALL SIXTEEN and say nothing about the two that matter; under
    /// the futures bound it draws on exactly those two. An age has value exactly
    /// when it is surprising, and this is the assertion that keeps it that way.
    func testTheFuturesBoundDrawsTwoOfSixteenAndTheLiveBoundWouldDrawAll() {
        let population = Array(repeating: 0.7, count: 14) + [77.7, 59.2]

        let futuresDrawn = population.filter {
            SourceAge.isStale(stamp(hoursAgo: $0), now: now, after: SourceAge.futuresStaleAfter)
        }
        XCTAssertEqual(futuresDrawn.count, 2, "the futures bound must mark only the two old ladders")
        XCTAssertEqual(futuresDrawn.sorted(), [59.2, 77.7])

        let liveDrawn = population.filter {
            SourceAge.isStale(stamp(hoursAgo: $0), now: now, after: SourceAge.liveStaleAfter)
        }
        XCTAssertEqual(liveDrawn.count, 16, "0.7h is past 30m — this is why the live bound is wrong here")
    }

    func testTheBoundIsStrictAtItsEdge() {
        let sixHours = stamp(hoursAgo: 6.0)
        XCTAssertFalse(
            SourceAge.isStale(sixHours, now: now, after: SourceAge.futuresStaleAfter),
            "exactly at the bound is not yet past it — mirrors web's strict >"
        )
        XCTAssertTrue(
            SourceAge.isStale(stamp(hoursAgo: 6.1), now: now, after: SourceAge.futuresStaleAfter)
        )
    }

    // MARK: - 3. Absent is not zero

    func testAnUndatableStampIsNeverStaleAndNeverFormats() {
        for raw in [nil, "", "not a date", "2026-13-45T99:99:99Z"] {
            XCTAssertNil(SourceAge.ageSeconds(raw, now: now), "\(raw ?? "nil")")
            XCTAssertNil(SourceAge.format(raw, now: now), "\(raw ?? "nil")")
            XCTAssertNil(SourceAge.reveal(raw), "\(raw ?? "nil")")
            XCTAssertFalse(
                SourceAge.isStale(raw, now: now, after: SourceAge.futuresStaleAfter),
                "an undatable price must fail closed, not read as very old: \(raw ?? "nil")"
            )
        }
    }

    /// Production serves both shapes — `…T05:50:00.312657Z` and `…T17:15:00Z` —
    /// and a parser that reads only one of them silently unmarks half the feed.
    func testBothProductionStampShapesParse() {
        let withFraction = "2026-09-15T05:50:00.312657Z"
        let withoutFraction = "2026-09-15T05:50:00Z"
        XCTAssertNotNil(SourceAge.ageSeconds(withFraction, now: now))
        XCTAssertNotNil(SourceAge.ageSeconds(withoutFraction, now: now))
    }

    /// A stamp from the future is a clock disagreement, not a negative age.
    func testAFutureStampClampsToZeroRatherThanWrapping() {
        let ahead = ISO8601DateFormatter().string(from: now.addingTimeInterval(3600))
        XCTAssertEqual(SourceAge.ageSeconds(ahead, now: now), 0)
        XCTAssertEqual(SourceAge.format(ahead, now: now), "just now")
        XCTAssertFalse(SourceAge.isStale(ahead, now: now, after: SourceAge.futuresStaleAfter))
    }

    // MARK: - 4. The reveal says precisely when

    /// 🔴 ASSERTED AS AN EQUALITY, not as "it does not contain 'ago'".
    ///
    /// The negative substring form SURVIVED its mutant: a reveal that prepends a
    /// relative age reading "just now" contains no "ago" and passed. The whole
    /// sentence is three known parts, so the honest assertion is the whole
    /// sentence — that kills any injection, not only the ones spelled with "ago".
    func testTheRevealIsExactlyTheStemAndAnAbsoluteClockTime() throws {
        let iso = stamp(hoursAgo: 77.7)
        let when = try XCTUnwrap(Liquidity.preciseObservedAt(iso.asDate))

        // Alex, 2026-08-29: a relative age is the thing he called ambiguous, so the
        // half that promises "precisely when" must not fall back to one.
        XCTAssertEqual(SourceAge.reveal(iso), "Last number: \(when)")
    }

    /// One precise-stamp formatter on this platform, not two. `SourceAge` delegates
    /// to the illiquidity reveal's rather than copying web's `formatSourceStamp`,
    /// whose field order differs ("Sep 12" vs "12 Sep").
    func testThePreciseStampIsTheOneNativeAlreadyShips() {
        let iso = stamp(hoursAgo: 77.7)
        XCTAssertEqual(SourceAge.preciseStamp(iso), Liquidity.preciseObservedAt(iso.asDate))
    }

    /// A chip can never appear without the sentence that explains it — the two are
    /// gated on the same parse.
    func testWheneverTheChipDrawsTheRevealExists() {
        for hours in [6.1, 12.0, 24.0, 59.2, 77.7, 3000.0] {
            let iso = stamp(hoursAgo: hours)
            guard SourceAge.isStale(iso, now: now, after: SourceAge.futuresStaleAfter) else {
                return XCTFail("\(hours)h should be past the futures bound")
            }
            XCTAssertNotNil(SourceAge.format(iso, now: now), "\(hours)h")
            XCTAssertNotNil(SourceAge.reveal(iso), "\(hours)h")
        }
    }

    // MARK: - The wire, and the settled suppression

    /// The decode is the whole fix: the field was on the wire and the model dropped
    /// it. This reads the shape `routes/feed.py` actually serves.
    func testTheFuturesCardDecodesPriceObservedAtFromTheWire() throws {
        let json = """
        {"type":"futures","score":70,"data":{
          "id":171,"name":"Canadian Team to Win the Stanley Cup",
          "status":"open","source":"kalshi",
          "price_observed_at":"2026-09-12T03:51:07.312657Z"
        }}
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let item = try decoder.decode(FeedItem.self, from: json)

        XCTAssertEqual(item.futures?.priceObservedAt, "2026-09-12T03:51:07.312657Z")
    }

    /// A card with no `price_observed_at` decodes rather than throwing — the whole
    /// futures pool empties if this field is ever required (gotcha #42).
    func testACardWithoutTheFieldStillDecodesAndDrawsNothing() throws {
        let json = """
        {"type":"futures","score":70,"data":{"id":1,"name":"MLB World Series Winner","status":"open"}}
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let item = try decoder.decode(FeedItem.self, from: json)

        XCTAssertNil(item.futures?.priceObservedAt)
        XCTAssertFalse(
            SourceAge.isStale(item.futures?.priceObservedAt, now: now, after: SourceAge.futuresStaleAfter)
        )
    }

    /// 🔴 THE SUPPRESSION THAT IS THE CALLER'S JOB, asserted against the predicate
    /// the card actually calls. A settled market's prices are ALL old; the card
    /// already says the question is answered, and "3d ago" on top of that buries
    /// the one case the mark exists for. Web's `SpecialEventMarkets` has the same
    /// rule, and `PriceAgeMarkView`'s header points here.
    func testASettledCardIsSuppressedByTheLifecyclePredicateTheCardUses() throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase

        // Each of the four settlement authorities, with a price old enough to draw.
        let settled: [String] = [
            #""resolved":true"#,
            #""winner":"Florida Panthers""#,
            #""status":"settled""#,
            #""resolution_date":"2026-09-01T00:00:00Z""#,
        ]
        for authority in settled {
            let json = """
            {"type":"futures","score":70,"data":{"id":171,"name":"x",
              "price_observed_at":"\(stamp(hoursAgo: 77.7))",\(authority)}}
            """.data(using: .utf8)!
            let data = try XCTUnwrap(decoder.decode(FeedItem.self, from: json).futures)

            XCTAssertTrue(
                FeedLifecycle.futuresIsSettled(data, now: now),
                "settled by \(authority) — the card must not draw an age"
            )
        }

        // The positive control, and the reason this is not a blanket suppression:
        // an OPEN card with the same old price is exactly what the mark is for.
        let openJSON = """
        {"type":"futures","score":70,"data":{"id":171,"name":"x","status":"open",
          "price_observed_at":"\(stamp(hoursAgo: 77.7))"}}
        """.data(using: .utf8)!
        let open = try XCTUnwrap(decoder.decode(FeedItem.self, from: openJSON).futures)

        XCTAssertFalse(FeedLifecycle.futuresIsSettled(open, now: now))
        XCTAssertTrue(
            SourceAge.isStale(open.priceObservedAt, now: now, after: SourceAge.futuresStaleAfter),
            "the open card with a 77.7h price MUST draw — suppressing it too would satisfy every negative assertion above and delete the ship"
        )
    }

    // MARK: - The CARD's decision, not just the helpers'

    private func futuresCard(_ fields: String) throws -> FeedFuturesData {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let json = """
        {"type":"futures","score":70,"data":{"id":171,"name":"x",\(fields)}}
        """.data(using: .utf8)!
        return try XCTUnwrap(decoder.decode(FeedItem.self, from: json).futures)
    }

    /// 🔴 THE ASSERTION THE HELPER TESTS ABOVE CANNOT MAKE.
    ///
    /// Everything above passes with the card wired to the LIVE cadence — #5843's
    /// defect, which marks fourteen of sixteen cards and makes the mark worthless
    /// — because `SourceAge` is correct either way. This pins the choice the card
    /// actually makes. 0.7h is the age fourteen of the sixteen production cards
    /// carried: past the live bound, inside the futures one.
    func testTheDiscoverCardUsesTheFuturesCadenceAndNotTheLiveOne() throws {
        let fresh = try futuresCard(#""status":"open","price_observed_at":"\#(stamp(hoursAgo: 0.7))""#)
        XCTAssertNil(
            fresh.discoverPriceAgeMark(now: now),
            "0.7h is past the 30m LIVE bound and inside the 6h futures one — a mark here is #5843"
        )

        let stale = try futuresCard(#""status":"open","price_observed_at":"\#(stamp(hoursAgo: 77.7))""#)
        XCTAssertEqual(stale.discoverPriceAgeMark(now: now)?.age, "3d ago")
    }

    /// The settled gate at the call site, which is where it lives.
    func testTheDiscoverCardDrawsNoAgeOnASettledMarket() throws {
        for authority in [
            #""resolved":true"#,
            #""winner":"Florida Panthers""#,
            #""status":"settled""#,
            #""resolution_date":"2026-09-01T00:00:00Z""#,
        ] {
            let card = try futuresCard(
                #""price_observed_at":"\#(stamp(hoursAgo: 77.7))",\#(authority)"#
            )
            XCTAssertNil(
                card.discoverPriceAgeMark(now: now),
                "settled by \(authority) — the question is answered, so the age is not the reader's question"
            )
        }
    }

    /// A card with nothing to date draws nothing, rather than reading as fresh.
    func testTheDiscoverCardDrawsNothingWhenTheStampIsAbsent() throws {
        let card = try futuresCard(#""status":"open""#)
        XCTAssertNil(card.priceObservedAt)
        XCTAssertNil(card.discoverPriceAgeMark(now: now))
    }

    /// 🔴 AN EMPTY LIQUIDITY PAYLOAD MUST NOT HIDE THIS DISCLOSURE.
    ///
    /// The failing case named in the ship's brief, and the reason this is an
    /// assertion rather than a shrug: the two signals are about ONE price and they
    /// are easy to couple by accident — draw the age inside the illiquidity mark,
    /// or gate it on the same payload branch, and `liquidity: {}` silently deletes
    /// it. That is the exact shape the web hit.
    ///
    /// Here they are independent by construction: `discoverPriceAgeMark` reads
    /// `priceObservedAt` and the lifecycle, and nothing else. This pins that, on
    /// the three payload shapes an empty or unreadable liquidity block can take —
    /// including a level `LiquidityLevel.normalize` refuses, which is the one a
    /// coupled implementation would most plausibly treat as "no mark".
    func testAnEmptyLiquidityPayloadDoesNotHideTheAge() throws {
        let liquidityShapes = [
            #""liquidity":{}"#,
            #""liquidity":null"#,
            #""liquidity":{"level":"unknown"},"liquidity_reasons":[]"#,
        ]

        for shape in liquidityShapes {
            let card = try futuresCard(
                #""status":"open","price_observed_at":"\#(stamp(hoursAgo: 77.7))",\#(shape)"#
            )
            XCTAssertEqual(
                card.discoverPriceAgeMark(now: now)?.age, "3d ago",
                "a 77.7h price must still be disclosed with \(shape) on the payload"
            )
        }

        // The control: it is the STAMP that decides, not the liquidity block. The
        // same empty block with a fresh price still draws nothing, so the three
        // assertions above are not passing because the mark draws unconditionally.
        let fresh = try futuresCard(
            #""status":"open","price_observed_at":"\#(stamp(hoursAgo: 0.7))","liquidity":{}"#
        )
        XCTAssertNil(fresh.discoverPriceAgeMark(now: now))
    }

    /// 🔴 OBSERVATION TIME IS NOT THE ANSWER DATE, AND NOT A FALLBACK FOR IT.
    ///
    /// `resolutionDate` is when the question gets ANSWERED; `priceObservedAt` is
    /// when the number on the card was last seen. They were confused once already
    /// (the US Open final page: a card an hour stale under a hero stamped 20s), so
    /// both directions are pinned — a card that carries only the answer date dates
    /// nothing at all, rather than dating itself off the nearest available time.
    func testTheAgeIsTheObservationTimeAndNeverTheResolutionDate() throws {
        // A future resolution date: the question is open, so the lifecycle gate
        // does not fire and the only thing left to decide the mark is the stamp.
        let answerDate = ISO8601DateFormatter().string(from: now.addingTimeInterval(30 * 86_400))

        let dated = try futuresCard(
            #""status":"open","resolution_date":"\#(answerDate)","price_observed_at":"\#(stamp(hoursAgo: 77.7))""#
        )
        XCTAssertFalse(FeedLifecycle.futuresIsSettled(dated, now: now))
        XCTAssertEqual(
            dated.discoverPriceAgeMark(now: now)?.age, "3d ago",
            "the age is the 77.7h observation, not the 30-day-out answer date"
        )

        let undated = try futuresCard(#""status":"open","resolution_date":"\#(answerDate)""#)
        XCTAssertNil(
            undated.discoverPriceAgeMark(now: now),
            "with no observation stamp there is nothing to date — a resolution date is not a substitute"
        )
    }

    /// 🔴 EVERY FUTURES CARD VIEW DRAWS IT, NOT JUST THE ONE I BUILT IT ON.
    ///
    /// `DiscoverView` routes a futures item to one of FOUR views by
    /// `discover_card.suggested_format`, and the first cut of this ship wired only
    /// the hero card. That left the mark on the MINORITY of the feed: in the read
    /// it shipped against, 11 of 16 datable cards were `outcome_distribution`, and
    /// the 60.2h PGA ladder — one of the two genuinely stale specimens — was one of
    /// them, so the headline defect survived its own fix on the card it was
    /// measured on.
    ///
    /// A source scan, because there is no other way to ask "did every renderer
    /// adopt it": a fifth futures card view that forgets the mark fails here.
    ///
    /// 🔴 IT SCANS CODE, NOT PROSE, AND THE FIRST VERSION DID NOT. Deleting the
    /// whole render block from `DistributionCardView` left the mutant ALIVE,
    /// because the explanatory comment above the block names
    /// `discoverPriceAgeMark` and a whole-file `contains` is satisfied by the
    /// mention. That is the same trap `tools/native-walk.sh` records against
    /// itself (#6342) — a scan whose pattern appears in its own commentary
    /// measures nothing. `strippingComments` is what makes this an assertion
    /// about the code.
    func testEveryFuturesCardViewDrawsTheMark() throws {
        let components = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()      // BainLuckTests
            .deletingLastPathComponent()      // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck/Components")

        // The four views `DiscoverView` can route a `type == "futures"` item to.
        let futuresCardViews = [
            "DiscoverFuturesCard.swift",   // binary_probability + the fallback
            "DistributionCardView.swift",  // outcome_distribution
            "ComparisonCardView.swift",    // cross_source_comparison
            "HeatMapCardView.swift",       // threshold_heatmap
        ]

        for file in futuresCardViews {
            let url = components.appendingPathComponent(file)
            let code = try String(contentsOf: url, encoding: .utf8).strippingComments()

            XCTAssertTrue(
                code.contains("data.discoverPriceAgeMark("),
                "\(file) renders a futures card but never CALLS the price-age mark — #6343 survives there"
            )
            XCTAssertTrue(
                code.contains("LiquidityRevealCaption(sentence: revealedPriceAge)"),
                "\(file) draws the mark but has nowhere to put its tap reveal"
            )
        }
    }

    /// The control for the control: `strippingComments` must actually remove the
    /// mention the first version tripped on, and must NOT remove the call.
    func testTheCommentStripperRemovesProseAndKeepsCode() {
        let sample = """
        // mentions data.discoverPriceAgeMark( in a comment
        let x = 1  // trailing data.discoverPriceAgeMark(
        /* block data.discoverPriceAgeMark( */
        if let mark = data.discoverPriceAgeMark(now: now) { mark }
        """
        let stripped = sample.strippingComments()
        XCTAssertEqual(
            stripped.components(separatedBy: "data.discoverPriceAgeMark(").count - 1, 1,
            "exactly the one real call should survive: \(stripped)"
        )
    }

    /// The scan above is only worth its line if the file it reads can actually be
    /// found — a wrong path makes every `contains` above vacuous in the other
    /// direction. This is its control.
    func testTheCardViewScanIsReadingRealFiles() throws {
        let components = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Components")
        let hero = try String(
            contentsOf: components.appendingPathComponent("DiscoverFuturesCard.swift"),
            encoding: .utf8
        )
        XCTAssertTrue(hero.contains("struct NativeFuturesDiscoverCard"), "scan is not reading the real source")
    }

    /// The mark carries its reveal, so a tap and VoiceOver always have a sentence.
    func testAMarkTheCardDrawsAlwaysCarriesItsPreciseStamp() throws {
        let card = try futuresCard(#""status":"open","price_observed_at":"\#(stamp(hoursAgo: 77.7))""#)
        let mark = try XCTUnwrap(card.discoverPriceAgeMark(now: now))

        XCTAssertEqual(mark.age, "3d ago")
        // Exact, for the reason the reveal test above gives.
        let when = try XCTUnwrap(Liquidity.preciseObservedAt(stamp(hoursAgo: 77.7).asDate))
        XCTAssertEqual(mark.sentence, "Last number: \(when)")
    }
}
