import Foundation
// Standalone runner for the same cases as BainLuckTests/SSEFrameParserTests.swift,
// against the REAL SSEFrameParser. Exists only because this sandbox cannot resolve
// the app target's SPM binaries, so XCTest cannot execute here.
var failures = 0, checks = 0
func check(_ ok: Bool, _ n: String) { checks += 1; if !ok { failures += 1; print("  FAIL  \(n)") } else { print("  ok    \(n)") } }
func parse(_ wire: String) -> [(event: String, data: String)] {
    var p = SSEFrameParser(); var out: [(event: String, data: String)] = []
    for line in wire.components(separatedBy: "\n") { if let f = p.feed(line) { out.append(f) } }
    return out
}
@main struct H {
    static func main() {
        print("the server's opening preamble")
        do { let f = parse("retry: 3000\n\nevent: open\ndata: {\"event_id\": 15293206}\n\n")
            check(f.count == 1, "retry line is not a frame")
            check(f.first?.event == "open", "open named")
            check(f.first?.data == "{\"event_id\": 15293206}", "payload intact") }

        print("a probability frame")
        do { let j = "{\"event_id\": 15293206, \"p\": 0.62, \"status\": \"live\"}"
            let f = parse("event: probability\ndata: \(j)\n\n")
            check(f.map(\.event) == ["probability"], "named")
            check(f.first?.data == j, "payload intact") }

        print("a sequence of frames in one stream")
        do { let f = parse("event: probability\ndata: {\"event_id\": 1, \"p\": 0.6}\n\nevent: heartbeat\ndata: {\"t\": \"a\"}\n\nevent: heartbeat\ndata: {\"t\": \"b\"}\n\nevent: probability\ndata: {\"event_id\": 1, \"p\": 0.7}\n\n")
            check(f.map(\.event) == ["probability","heartbeat","heartbeat","probability"], "four frames in order")
            check(f[0].data == "{\"event_id\": 1, \"p\": 0.6}", "first payload")
            check(f[3].data == "{\"event_id\": 1, \"p\": 0.7}", "last payload does not bleed") }

        print("the two lifecycle events the controller branches on")
        do { let f = parse("event: reconnect\ndata: {\"reason\": \"max_age\"}\n\nevent: closed\ndata: {\"reason\": \"not_live\"}\n\n")
            check(f.map(\.event) == ["reconnect","closed"], "reconnect and closed distinguished") }

        print("exactly one leading space is framing")
        do { check(parse("event: a\ndata: v\n\n").first?.data == "v", "one space eaten")
            check(parse("event: a\ndata:v\n\n").first?.data == "v", "no space fine")
            check(parse("event: a\ndata:  v\n\n").first?.data == " v", "second space kept") }

        print("multi-line data is joined with newlines")
        do { check(parse("event: probability\ndata: {\"a\": 1,\ndata: \"b\": 2}\n\n").first?.data == "{\"a\": 1,\n\"b\": 2}", "joined") }

        print("comment lines are skipped")
        do { let f = parse("event: probability\n: keep-alive\ndata: {\"event_id\": 1}\n\n")
            check(f.count == 1 && f.first?.event == "probability" && f.first?.data == "{\"event_id\": 1}", "comment does not corrupt the frame") }

        print("incomplete and empty inputs produce nothing")
        do { check(parse("event: probability\ndata: {\"event_id\": 1}").isEmpty, "no terminator, no frame")
            check(parse("\n\n\n").isEmpty, "blank lines alone make nothing") }

        print("a field with no colon is ignored")
        do { let f = parse("garbage\nevent: probability\ndata: {\"event_id\": 1}\n\n")
            check(f.count == 1 && f.first?.event == "probability", "survives junk") }

        print("\n\(checks - failures)/\(checks) checks passed, \(failures) failed")
        exit(failures == 0 ? 0 : 1)
    }
}
