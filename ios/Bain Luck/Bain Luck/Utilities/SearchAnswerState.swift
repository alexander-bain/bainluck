import Foundation

/// Did this search find nothing, or did we fail to finish it? (#1740 site 2)
///
/// The native mirror of `frontend/lib/searchAnswerState.ts`, and it exists for
/// the same reason `SearchGrouping` does: the web and the phone must answer the
/// same question the same way, or one query reads as "that doesn't exist here"
/// on one surface and "we ran out of time" on the other.
///
/// `/api/events/search` carries a 20,000 ms deadline and sheds stages rather
/// than erroring when it runs out, declaring each one it dropped in `degraded`.
/// The route states the contract at the payload site:
///
///     A stage we could not complete must be distinguishable from a stage that
///     honestly found nothing.
///
/// It was distinguishable on the wire and nowhere on this client. `SearchResponse`
/// did not model the field, so `SearchView` saw six empty collections and drew
/// "No results found for X". That is a claim about the world, made from a request
/// we abandoned — #2239's web user answered it by retyping the same word four
/// times, which is the behaviour this prevents on the phone.
///
/// Kept free of SwiftUI so the decision is unit-testable: left as a `if` inside a
/// `List` builder it could not be tested at all, which is how the six-way
/// condition below went four years without one.
enum SearchAnswerState: String, Sendable {
    /// There is something to draw. Draw it.
    case present
    /// Nothing to draw, and the server told us it could not finish looking.
    case degraded
    /// Nothing to draw, and the answer was complete. The entity really is absent.
    case empty

    /// Which of the three `SearchView` should render.
    ///
    /// CONTENT WINS OVER `degraded`, deliberately, and it is the narrower half of
    /// the fix. A partial answer still renders what it has: the page only lies
    /// when it asserts ABSENCE, and showing three markets while silently omitting
    /// a shed futures stage is incomplete rather than false. Widening this to
    /// warn on every partial answer is a real question, and a different one — it
    /// would put an outage banner over screens that are visibly working.
    ///
    /// SIX flags, where the web has four. That is not drift: the phone draws two
    /// sections the web page does not — tournament hubs and server-composed
    /// futures families — and both already counted as content in the condition
    /// this replaces. A hub row under the words "No Results" was the page
    /// contradicting itself; a family can carry a headline the flat `futures`
    /// slice had no room for. Dropping either to match the web's arity would
    /// reintroduce a bug that is already fixed here.
    static func resolve(
        hasEvents: Bool,
        hasFutures: Bool,
        hasFamilies: Bool,
        hasConcepts: Bool,
        hasTeams: Bool,
        hasHubs: Bool,
        degraded: [String]?
    ) -> SearchAnswerState {
        if hasEvents || hasFutures || hasFamilies || hasConcepts || hasTeams || hasHubs {
            return .present
        }
        // Nothing to show. WHY there is nothing is the entire question, and
        // `degraded` is the only thing that can answer it. Additive on the wire,
        // so absent — or an empty list — means the answer really was complete.
        return (degraded?.isEmpty == false) ? .degraded : .empty
    }
}
