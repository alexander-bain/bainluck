import Foundation

let bainLuckFallbackURL = URL(string: "https://bainluck.com") ?? URL(fileURLWithPath: "/")

enum BainLuckShareURLStyle {
    case plain
    case nativeCard
}

func eventShareURL(_ eventID: Int, style: BainLuckShareURLStyle = .plain) -> String {
    let base = "https://bainluck.com/events/\(eventID)"
    switch style {
    case .plain:
        return base
    case .nativeCard:
        return "\(base)?utm_source=share&utm_medium=native&utm_campaign=card&content_type=event&item_id=\(eventID)"
    }
}

func futuresShareURL(_ marketID: Int, style: BainLuckShareURLStyle = .plain) -> String {
    let base = "https://bainluck.com/futures/\(marketID)"
    switch style {
    case .plain:
        return base
    case .nativeCard:
        return "\(base)?utm_source=share&utm_medium=native&utm_campaign=card&content_type=futures&item_id=\(marketID)"
    }
}
