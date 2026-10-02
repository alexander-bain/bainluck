import XCTest
@testable import Bain_Luck

/// #8651 (build 34) — **every stamp parses to the same moment it always did,
/// without the formatter's cost.**
///
/// `String.asDate` now tries `ISO8601Stamp` first. It is a fast path only: for
/// any stamp it accepts it must return the formatters' value BIT FOR BIT, and
/// for any it declines the formatters answer exactly as before. A fast path
/// that disagreed by a millisecond would move a chart point, reorder a tie
/// (#8509), or flip a freshness comparison (#920) — so these tests compare the
/// raw bit patterns, not a tolerance.
final class AStampParsesAsTheFormatterDid8651Tests: XCTestCase {

    private func assertSameAsFormatter(_ stamp: String, file: StaticString = #filePath, line: UInt = #line) {
        let reference = stamp.asDateByFormatter
        let fast = ISO8601Stamp.date(stamp)
        if let fast {
            XCTAssertNotNil(reference, "fast path accepted a stamp the formatter rejects: \(stamp)", file: file, line: line)
            XCTAssertEqual(fast.timeIntervalSinceReferenceDate.bitPattern,
                           reference?.timeIntervalSinceReferenceDate.bitPattern,
                           "fast path moved \(stamp)", file: file, line: line)
        }
        XCTAssertEqual(stamp.asDate?.timeIntervalSinceReferenceDate.bitPattern,
                       reference?.timeIntervalSinceReferenceDate.bitPattern,
                       "asDate changed its answer for \(stamp)", file: file, line: line)
    }

    /// The shapes the server writes (census of 14780550's history and
    /// game-markets payloads: `+00:00` with no fraction, and with six digits).
    func testTheServersOwnShapesTakeTheFastPathAndAgree() {
        for stamp in ["2026-10-01T23:40:00+00:00", "2026-10-01T23:40:00.123456+00:00",
                      "2026-10-01T23:40:00Z", "2026-10-01T23:40:00.5Z", "2026-10-01T23:40:00.12-07:00",
                      "2026-10-01T23:40:00.999999+05:30", "2024-02-29T12:00:00+00:00",
                      "1969-12-31T23:59:59.999Z", "2000-01-01T00:00:00-12:00"] {
            XCTAssertNotNil(ISO8601Stamp.date(stamp), "the server's shape must take the fast path: \(stamp)")
            assertSameAsFormatter(stamp)
        }
    }

    /// The formatter keeps whole milliseconds; so must the fast path.
    func testTheFractionIsTruncatedToMillisecondsLikeTheFormatter() throws {
        let six = try XCTUnwrap(ISO8601Stamp.date("2026-10-01T23:40:00.123999+00:00"))
        let three = try XCTUnwrap(ISO8601Stamp.date("2026-10-01T23:40:00.123+00:00"))
        XCTAssertEqual(six, three)
        assertSameAsFormatter("2026-10-01T23:40:00.123999+00:00")
    }

    /// Everything outside the strict shape is declined and keeps the
    /// formatter's answer — including the formatter's lenient acceptances.
    func testAnythingElseIsDeclinedAndKeepsTheFormattersAnswer() {
        for stamp in ["2023-02-29T00:00:00Z", "2026-10-01T24:00:00Z", "2026-10-01T23:40:00+0000",
                      "2026-10-01T23:59:60Z", "2026-13-01T00:00:00Z", "2026-10-01 23:40:00Z",
                      "2026-10-01T23:40:00", "2026-10-01T23:40Z", "2026-10-01T23:40:00.Z",
                      "2026-10-01t23:40:00z", "not a time", "", "2026-10-01T23:40:00+00:00 "] {
            XCTAssertNil(ISO8601Stamp.date(stamp), "outside the strict shape: \(stamp)")
            assertSameAsFormatter(stamp)
        }
    }

    /// A seeded sweep across years, offsets and 0–7 fraction digits.
    func testASweepOfWellFormedStampsAgreesBitForBit() {
        var rng = SplitMix64(seed: 8651)
        let zones = ["Z", "+00:00", "-04:00", "+05:30", "-11:45", "+14:00"]
        for _ in 0..<3000 {
            let digits = Int(rng.next() % 8)
            let fraction = digits == 0 ? "" : "." + (0..<digits).map { _ in String(rng.next() % 10) }.joined()
            let stamp = String(format: "%04d-%02d-%02dT%02d:%02d:%02d",
                               1960 + Int(rng.next() % 90), 1 + Int(rng.next() % 12), 1 + Int(rng.next() % 28),
                               Int(rng.next() % 24), Int(rng.next() % 60), Int(rng.next() % 60))
                + fraction + zones[Int(rng.next() % UInt64(zones.count))]
            XCTAssertNotNil(ISO8601Stamp.date(stamp), stamp)
            assertSameAsFormatter(stamp)
        }
    }

    private struct SplitMix64 {
        var state: UInt64
        init(seed: UInt64) { state = seed }
        mutating func next() -> UInt64 {
            state &+= 0x9E37_79B9_7F4A_7C15
            var z = state
            z = (z ^ (z >> 30)) &* 0xBF58_476D_1CE4_E5B9
            z = (z ^ (z >> 27)) &* 0x94D0_49BB_1331_11EB
            return z ^ (z >> 31)
        }
    }
}
