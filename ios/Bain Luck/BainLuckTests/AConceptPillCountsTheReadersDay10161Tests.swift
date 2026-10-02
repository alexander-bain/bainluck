import XCTest
@testable import Bain_Luck

/// #10161 — **a fight card stops saying "Today" when it is tomorrow for the reader.**
///
/// The server words a concept card's `headline` from UTC dates. Specimen:
/// Fahmi–El Sisy, `start_date` 2026-10-02T15:00Z, served "Today" at 04:05Z —
/// 9:05 PM on Oct 1 in Pacific time, for a bout at 8:00 AM on Oct 2. Its own
/// game card said "Tomorrow 8:00 AM". The card now re-counts the three day words
/// on the reader's calendar; every other headline is shown as served.
final class AConceptPillCountsTheReadersDay10161Tests: XCTestCase {

    private func calendar(_ zone: String) -> Calendar {
        var c = Calendar(identifier: .gregorian)
        c.timeZone = TimeZone(identifier: zone)!
        return c
    }

    private func instant(_ iso: String) -> Date {
        parseFlexibleDate(iso)!
    }

    private func pill(_ served: String?, start: String?, now: String, zone: String) -> String? {
        conceptCountdownHeadline(served, startDate: start, now: instant(now), calendar: calendar(zone))
    }

    // MARK: - The specimen

    func testTheSpecimenReadsTomorrowInPacific() {
        XCTAssertEqual(
            pill("Today", start: "2026-10-02T15:00:00+00:00", now: "2026-10-02T04:05:00+00:00",
                 zone: "America/Los_Angeles"),
            "Tomorrow"
        )
    }

    func testTheSpecimenStillReadsTodayForAReaderOnUTC() {
        // Control: where the reader's day IS the UTC day, the served word was right.
        XCTAssertEqual(
            pill("Today", start: "2026-10-02T15:00:00+00:00", now: "2026-10-02T04:05:00+00:00",
                 zone: "UTC"),
            "Today"
        )
    }

    func testEastOfUTCTheServerCanRunADayBehind() {
        // 23:30 in Tokyo on Oct 2; the start is 00:30 on Oct 3 there, same UTC day.
        XCTAssertEqual(
            pill("Today", start: "2026-10-02T15:30:00+00:00", now: "2026-10-02T14:30:00+00:00",
                 zone: "Asia/Tokyo"),
            "Tomorrow"
        )
    }

    // MARK: - The server's thresholds, on the reader's day

    func testThresholds() {
        let now = "2026-10-02T04:05:00+00:00" // Oct 1, 9:05 PM Pacific
        let la = "America/Los_Angeles"
        XCTAssertEqual(pill("Tomorrow", start: "2026-10-02T03:00:00+00:00", now: now, zone: la), "Today",
                       "8 PM Oct 1 Pacific, already begun but not live")
        XCTAssertEqual(pill("This week", start: "2026-10-02T06:00:00+00:00", now: now, zone: la), "Today",
                       "11 PM Oct 1 Pacific")
        XCTAssertEqual(pill("Today", start: "2026-10-03T06:30:00+00:00", now: now, zone: la), "Tomorrow",
                       "11:30 PM Oct 2 Pacific is still one reader-day out")
        XCTAssertEqual(pill("Today", start: "2026-10-03T08:00:00+00:00", now: now, zone: la), "This week",
                       "1 AM Oct 3 Pacific is two reader-days out")
        XCTAssertEqual(pill("This week", start: "2026-10-08T20:00:00+00:00", now: now, zone: la), "This week",
                       "Oct 8 is seven reader-days out")
        XCTAssertNil(pill("This week", start: "2026-10-09T20:00:00+00:00", now: now, zone: la),
                     "eight reader-days out earns no pill")
    }

    // MARK: - Everything else is shown as served

    func testWordsOutsideTheThreeAreUntouched() {
        let start = "2026-10-02T15:00:00+00:00"
        let now = "2026-10-02T04:05:00+00:00"
        XCTAssertEqual(pill("Live", start: start, now: now, zone: "America/Los_Angeles"), "Live")
        XCTAssertEqual(pill("Opens Oct 2", start: start, now: now, zone: "America/Los_Angeles"), "Opens Oct 2")
        XCTAssertNil(pill(nil, start: start, now: now, zone: "America/Los_Angeles"))
    }

    func testAMissingOrUnreadableStartLeavesTheServedWord() {
        let now = "2026-10-02T04:05:00+00:00"
        XCTAssertEqual(pill("Today", start: nil, now: now, zone: "America/Los_Angeles"), "Today")
        XCTAssertEqual(pill("Today", start: "", now: now, zone: "America/Los_Angeles"), "Today")
        XCTAssertEqual(pill("Today", start: "soon", now: now, zone: "America/Los_Angeles"), "Today")
    }
}
