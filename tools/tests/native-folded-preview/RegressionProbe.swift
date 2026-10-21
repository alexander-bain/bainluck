import Foundation

@main struct RegressionProbe {
    static func main() throws {
        let wire = #"{"event_id":4242,"p":0.6,"p_away":0.2,"sport":"soccer_epl","status":"live","preview":{"kind":"blend","epoch":5,"seq":1,"base_rev":20,"ttl_ms":1000,"folded_version":1,"origin_event_id":4243,"base_fold_revision":{"4242":10,"4243":20}}}"#
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        func detail(_ vector: String) throws -> EventDetail {
            try decoder.decode(EventDetail.self, from: Data("""
            {"id":4242,"sport":"soccer_epl","status":"live","current_odds":{"home_probability":0.5,"away_probability":0.25},"hero_probability":0.5,"hero_probability_source":"blend","blend_fold_revision":\(vector)}
            """.utf8))
        }
        guard let frame = BlendPreviewFrame.decode(wire) else { print("valid folded frame refused"); exit(1) }
        let held = BlendPreview.readerAfter(.empty, frame, eventId: 4242, now: 100).held
        let folded = BlendPreview.displayed(held, held: try detail(#"{"4242":10,"4243":20}"#), now: 100)
        let transition = BlendPreview.displayed(held, held: try detail(#"{"4242":10}"#), now: 100)
        let malformed = BlendPreviewFrame.decode(wire.replacingOccurrences(of: #""folded_version":1"#, with: #""folded_version":9"#))
        print("folded=\(String(describing: folded)); singleton transition=\(String(describing: transition)); unknown version accepted=\(malformed != nil)")
        exit(folded == 0.6 && transition == nil && malformed == nil ? 0 : 1)
    }
}
