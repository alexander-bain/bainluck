import XCTest
@testable import Bain_Luck

/// #2687 — the SSE wire format, fed the bytes `backend/app/routes/event_stream.py`
/// actually writes.
///
/// Apple ships no `EventSource`, so this parser is code we own on a path a
/// browser normally hides. Every failure it can have is SILENT: a stream that
/// connects and delivers nothing looks, from the outside, exactly like a quiet
/// market — and the controller above it would dutifully degrade to polling and
/// report no error at all. Nothing short of a live match would catch it, which
/// is precisely why it is a pure function with a test rather than four lines
/// inside a `URLSession` loop.
///
/// THE FIXTURES ARE THE SERVER'S OWN OUTPUT. `sse_encode` writes
/// `event: <name>\ndata: <json>\n\n`, and `_stream` emits `retry:`, `open`,
/// `probability`, `heartbeat`, `reconnect` and `closed`. Each is exercised in
/// the shape the server sends it, not a shape convenient to the parser.
final class SSEFrameParserTests: XCTestCase {

    /// Feed a whole wire transcript and collect every frame it completes.
    private func parse(_ wire: String) -> [(event: String, data: String)] {
        var parser = SSEFrameParser()
        var out: [(event: String, data: String)] = []
        // `URLSession.bytes.lines` yields lines WITHOUT their terminators, which
        // is what the parser is written against — so split the same way.
        for line in wire.components(separatedBy: "\n") {
            if let frame = parser.feed(line) { out.append(frame) }
        }
        return out
    }

    func testTheServersOpeningPreamble() {
        // `_stream` writes `retry: 3000\n\n` and then the `open` event. The
        // `retry` line must be READ AND IGNORED — acted on, it would give the
        // transport a second opinion about reconnection, which the controller
        // alone owns. Silently mis-parsed as a frame, it would fire a handler
        // named "message" that nothing listens to.
        let frames = parse("retry: 3000\n\nevent: open\ndata: {\"event_id\": 15293206}\n\n")
        XCTAssertEqual(frames.count, 1)
        XCTAssertEqual(frames.first?.event, "open")
        XCTAssertEqual(frames.first?.data, "{\"event_id\": 15293206}")
    }

    func testAProbabilityFrame() {
        let json = "{\"event_id\": 15293206, \"p\": 0.62, \"status\": \"live\"}"
        let frames = parse("event: probability\ndata: \(json)\n\n")
        XCTAssertEqual(frames.map(\.event), ["probability"])
        XCTAssertEqual(frames.first?.data, json)
    }

    func testASequenceOfFramesInOneStream() {
        // The real shape of a match: a price, two keep-alives, another price.
        // Frames must not bleed into one another — a parser that failed to reset
        // would carry the first payload into the second and the controller would
        // re-deliver a stale price as a fresh one.
        let wire = """
        event: probability
        data: {"event_id": 1, "p": 0.6}

        event: heartbeat
        data: {"t": "2026-09-03T09:00:00Z"}

        event: heartbeat
        data: {"t": "2026-09-03T09:00:20Z"}

        event: probability
        data: {"event_id": 1, "p": 0.7}


        """
        let frames = parse(wire)
        XCTAssertEqual(frames.map(\.event), ["probability", "heartbeat", "heartbeat", "probability"])
        XCTAssertEqual(frames[0].data, "{\"event_id\": 1, \"p\": 0.6}")
        XCTAssertEqual(frames[3].data, "{\"event_id\": 1, \"p\": 0.7}")
    }

    func testTheTwoLifecycleEventsTheControllerBranchesOn() {
        // `reconnect` and `closed` mean opposite things — roll over versus stop
        // forever — so the parser handing back the wrong name is the difference
        // between a fan keeping push for a whole match and losing it at fifteen
        // minutes.
        let frames = parse("""
        event: reconnect
        data: {"reason": "max_age"}

        event: closed
        data: {"reason": "not_live"}


        """)
        XCTAssertEqual(frames.map(\.event), ["reconnect", "closed"])
    }

    func testExactlyOneLeadingSpaceIsFraming() {
        // `data: x` and `data:x` are the same value per the spec; a SECOND space
        // belongs to the payload. Eating both would corrupt any payload that
        // legitimately starts with whitespace.
        XCTAssertEqual(parse("event: a\ndata: v\n\n").first?.data, "v")
        XCTAssertEqual(parse("event: a\ndata:v\n\n").first?.data, "v")
        XCTAssertEqual(parse("event: a\ndata:  v\n\n").first?.data, " v")
    }

    func testMultiLineDataIsJoinedWithNewlines() {
        // The server sends one line today. A JSON payload that ever grew a
        // newline would, under a last-line-wins parser, arrive as half an object
        // and fail to decode — which the controller treats as one bad frame and
        // ignores, so the stream would look healthy and deliver nothing.
        let frames = parse("event: probability\ndata: {\"a\": 1,\ndata: \"b\": 2}\n\n")
        XCTAssertEqual(frames.first?.data, "{\"a\": 1,\n\"b\": 2}")
    }

    func testCommentLinesAreSkipped() {
        // The conventional `: ping` keep-alive. The server deliberately does not
        // send it (a comment fires no handler, so the client could not observe
        // it), but a proxy may inject one and it must not corrupt the frame it
        // lands inside.
        let frames = parse("event: probability\n: keep-alive\ndata: {\"event_id\": 1}\n\n")
        XCTAssertEqual(frames.count, 1)
        XCTAssertEqual(frames.first?.event, "probability")
        XCTAssertEqual(frames.first?.data, "{\"event_id\": 1}")
    }

    func testAnIncompleteFrameProducesNothing() {
        // The terminating blank line has not arrived. Emitting early would hand
        // the controller a truncated payload.
        XCTAssertTrue(parse("event: probability\ndata: {\"event_id\": 1}").isEmpty)
    }

    func testBlankLinesAloneProduceNothing() {
        // Both directions: the parser must not manufacture frames out of the
        // padding between them.
        XCTAssertTrue(parse("\n\n\n").isEmpty)
    }

    func testAFieldWithNoColonIsIgnoredRatherThanCrashing() {
        let frames = parse("garbage\nevent: probability\ndata: {\"event_id\": 1}\n\n")
        XCTAssertEqual(frames.count, 1)
        XCTAssertEqual(frames.first?.event, "probability")
    }
}
