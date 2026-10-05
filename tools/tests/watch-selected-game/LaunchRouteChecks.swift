import Foundation

func checkWatchLaunchRoute() {
    precondition(WatchLaunchRoute.url.absoluteString == "bainluck-watch://selected-game",
                 "The complication opens Your game without supplying a selection")
    precondition(WatchLaunchRoute.accepts(WatchLaunchRoute.url))
    let rejected = [
        "bainluck-watch://selected-game?event_id=1",
        "bainluck-watch://selected-game?id=2",
        "bainluck-watch://selected-game?selected_event_id=3",
        "bainluck-watch://selected-game?",
        "bainluck-watch://selected-game#1",
        "bainluck-watch://selected-game#",
        "bainluck-watch://selected-game/",
        "bainluck-watch://selected-game/1",
        "bainluck-watch://selected-game/events/1",
        "bainluck-watch://selected-game:443",
        "bainluck-watch://user@selected-game",
        "bainluck-watch://user:secret@selected-game",
        "bainluck-watch://other-game",
        "bainluck-watch://SELECTED-GAME",
        "BAINLUCK-WATCH://selected-game",
        "https://selected-game",
        "https://bainluck.com/events/1",
        "bainluck-watch: selected-game",
        "bainluck-watch:selected-game",
        "bainluck-watch:///selected-game",
        "bainluck-watch://selected-game%2F1",
        "selected-game",
        "/selected-game",
    ]
    for raw in rejected {
        if let url = URL(string: raw) {
            precondition(!WatchLaunchRoute.accepts(url), "Reject noncanonical launcher route: \(raw)")
        }
    }
    for id in [Int.min, -1, 0, 1, Int.max] {
        for raw in ["bainluck-watch://selected-game?event_id=\(id)",
                    "bainluck-watch://selected-game/\(id)",
                    "bainluck-watch://selected-game#\(id)"] {
            precondition(!WatchLaunchRoute.accepts(URL(string: raw)!),
                         "Launcher URLs cannot replace the persisted game selection")
        }
    }
    print("PASS: exact stateless Your game launch route, no query/fragment/path/credentials or selection overrides")
}
