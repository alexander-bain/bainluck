import Foundation

/// #4265 — the ONE caption chain for a futures Discover card.
///
/// Web resolves a card's caption in `frontend/components/discover/utils.ts`
/// (`feedContextSnippet`). This is the same chain in Swift, and the two are held
/// together by `fixtures/discover/caption-chain-record-2026-09-09.json` — each
/// side asserts in its own runner that it reproduces every row of that record.
///
/// ## What was wrong, and why it was not the ordering
///
/// The issue reported the two clients preferring `headline` and `reason` in
/// opposite orders. Measured against the live payload (`GET /api/feed?limit=250`,
/// 2026-09-09 07:20 PT, 113 futures cards) that turned out to be the smaller
/// half. The wire sends **empty strings far more often than nulls**:
/// `context_summary` was `""` on 23 cards and `reason` on 23, while `headline`
/// was the field that arrived `null` (19).
///
/// Web's `||` treats `""` as absent and falls through. Swift's `??` does not —
/// `""` is a perfectly good non-nil `String`, so
///
///     item.contextSummary ?? item.reason ?? item.headline
///
/// resolved to `""` at the FIRST rung and never consulted the other two. The
/// order under debate did not decide those cards at all.
/// `DiscoverFuturesCard.contextText` then rejected the empty string and fell to
/// `hookDescription`, which rescued most of them but silently promoted `hook`
/// from fourth place to second. What survived on that edition: **three cards
/// captioned on web and BLANK in the app** (Stanley Cup, WTI, Pantoja — all
/// "Well off its opening price"), and one ("Hasan Piker arrested in 2026?")
/// where both clients printed something and they printed different things.
///
/// ## The order, and why this one
///
/// `context_summary → headline → reason → hook_description → ""` — web's.
/// On real strings, `reason` restates the market name the card already prints
/// as its heading:
///
///     headline : "Los Angeles Dodgers leads at 31%"
///     reason   : "Los Angeles Dodgers (31%) leads MLB World Series Winner"
///
/// UX-P045 promoted `reason` above `headline` for **settled events**, where
/// `headline` is a bucket label tensed for a live market ("Line moving", over a
/// game that ended hours ago). For futures `headline` is the specific sentence,
/// so that precedent does not carry across, and this helper is futures-only.
///
/// ## Empty means absent, and so does whitespace
///
/// A string of spaces is an absence wearing a value; captioning a card with one
/// leaves a reader looking at a blank line that the code believes is filled.
/// Both clients trim before deciding, and the record has a row that fails if
/// either stops.
public enum DiscoverCaption {

    /// First rung of `candidates` that carries actual text, trimmed; `""` if none.
    ///
    /// Deliberately NOT `??`. That operator is what this file exists to stop
    /// being used on these fields: it asks "is this nil", and the wire's way of
    /// saying "nothing" is `""`.
    public static func firstMeaningful(_ candidates: [String?]) -> String {
        for candidate in candidates {
            guard let candidate else { continue }
            let trimmed = candidate.trimmingCharacters(in: .whitespacesAndNewlines)
            if !trimmed.isEmpty { return trimmed }
        }
        return ""
    }

    /// The caption under a futures card, resolved exactly as web resolves it.
    public static func feedCaption(
        contextSummary: String?,
        headline: String?,
        reason: String?,
        hookDescription: String?
    ) -> String {
        firstMeaningful([contextSummary, headline, reason, hookDescription])
    }
}
