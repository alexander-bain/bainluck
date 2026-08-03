import Foundation

/// Aggregated calibration metrics for one probability bucket.
nonisolated struct CalibrationBucket: Decodable, Sendable {
    let bucketIdx: Int
    let source: String
    let category: String
    let priceMoved: Bool?
    let n: Int
    let winners: Int
    let sumProb: Double
    let sumSqErr: Double
    let ciLower: Double?
    let ciUpper: Double?
    let avgProb: Double?
}

/// A market category held out of the published curve because it hasn't cleared
/// the minimum-sample bar yet. Powers the "niche & long-shot" honest note.
///
/// Queue 299 (#1012) made the disposition machine-readable: a cohort whose
/// defective rows were excluded read-side can legitimately fall UNDER the bar,
/// and the honest answer then is "parked", not a quietly missing chart. The
/// three added fields are optional — a leaner or older payload carries only
/// category + outcomes, and native must not hard-require the rest.
nonisolated struct SmallSampleCategory: Decodable, Sendable, Identifiable {
    let category: String
    let outcomes: Int
    let disposition: String?
    let publishBar: Int?
    let ece: Double?
    var id: String { category }

    /// Queue 299's declared value. Compared as data, never inferred from the count.
    static let parkedBelowPublishBar = "parked_below_publish_bar"

    var isParked: Bool { disposition == Self.parkedBelowPublishBar }
}

/// Queue 297: how fresh the served snapshot is.
///
/// Absent — or present with a status other than `stale` — means the payload is
/// current. When it IS stale the surface MUST say so and date it: a dated
/// last-good is honest, an undated one presented as live is not. Native had no
/// decode for this at all, so every degraded payload rendered as though it were
/// current (L2-231 Item 0's web/native divergence).
nonisolated struct CalibrationCacheState: Decodable, Sendable {
    let status: String
    let reason: String?
    let generatedAt: String?
    let ageS: Double?

    var isStale: Bool { status == "stale" }
}

/// One entry in the data-corrections trust log (payload v2 `corrections[]`).
nonisolated struct CalibrationCorrection: Decodable, Sendable, Identifiable {
    let date: String
    let title: String
    let rows: Int?
    let description: String
    var id: String { date + "|" + title }
}

/// The date span the calibration payload covers.
nonisolated struct CalibrationDateRange: Decodable, Sendable {
    let start: String?
    let end: String?
}

/// Decodes an array element by element, keeping the good ones and counting the
/// bad ones instead of throwing the whole array away.
///
/// L2-231 Item 1 — ALL-OR-NOTHING BUCKET LOSS. `/api/calibration` ships ~1,600
/// buckets. Every one of them was decoded into a struct whose fields are all
/// non-optional, inside a non-optional `[CalibrationBucket]`, so a single row
/// with a null `n` — one row in sixteen hundred — threw, and the entire
/// calibration screen became a generic error. That is gotcha #42's rule ("one
/// bad item must never wipe a whole pass") on the client side.
///
/// The drop is COUNTED, never silent: quietly rendering a curve built from 1,200
/// of 1,606 buckets, with no way for the reader to know, is the same class of
/// dishonesty as rendering a stale snapshot as current. `CalibrationViewModel`
/// surfaces a non-zero count.
///
/// The element is decoded through a never-failing wrapper rather than with
/// `try? container.decode(Element.self)` deliberately: a throwing element decode
/// is not guaranteed to advance the unkeyed container's cursor, which turns a
/// malformed row into an infinite loop. A wrapper that always succeeds always
/// advances.
nonisolated struct LossyArray<Element: Decodable & Sendable>: Decodable, Sendable {
    let elements: [Element]
    /// How many array entries failed to decode and were skipped.
    let dropped: Int

    private struct Skippable: Decodable {
        let value: Element?
        init(from decoder: Decoder) throws { value = try? Element(from: decoder) }
    }

    init(from decoder: Decoder) throws {
        var container = try decoder.unkeyedContainer()
        var kept: [Element] = []
        kept.reserveCapacity(container.count ?? 0)
        var dropped = 0
        while !container.isAtEnd {
            if let value = try container.decode(Skippable.self).value {
                kept.append(value)
            } else {
                dropped += 1
            }
        }
        self.elements = kept
        self.dropped = dropped
    }

    init(elements: [Element], dropped: Int = 0) {
        self.elements = elements
        self.dropped = dropped
    }
}

/// Top-level calibration response with bucket data and summary error metrics.
///
/// Payload v2 (#999 §F) carries the sample gate, the held-out categories, and the
/// corrections log so web + native render the same story from the same numbers.
/// All added fields are optional: the in-request route fallback ships a leaner
/// payload than the precompute cache, so native must not hard-require them.
///
/// L2-231 Item 1 decodes this BY HAND rather than by synthesis. The synthesized
/// initializer is all-or-nothing in both directions — one unparseable field kills
/// the payload, and one absent required field kills it too — and this response is
/// assembled from many independent server-side stages, any one of which can ship
/// a malformed slice while the rest is perfectly good. Each field is now
/// independent, and a field that cannot be read stays `nil` (unknown) rather than
/// collapsing to `0`, which would be a NUMBER the reader cannot distinguish from
/// a measured one.
nonisolated struct CalibrationData: Decodable, Sendable {
    let buckets: [CalibrationBucket]
    let totalMarkets: Int?
    let totalOutcomes: Int?
    let totalWinners: Int?
    let mceCiLower: Double?
    let mceCiUpper: Double?
    let mceClosingLine: Double?
    let mceOpeningPrice: Double?
    let generatedAt: String?
    // Payload v2 additions (all optional — see route fallback note above).
    let minCategoryOutcomes: Int?
    let smallSampleCategories: [SmallSampleCategory]?
    let corrections: [CalibrationCorrection]?
    let dateRange: CalibrationDateRange?
    // L2-231 Item 2 / Queue 297 §3: the freshness envelope and the payload's own
    // population contract. Both optional so a lean route-fallback payload still
    // decodes — but a payload that omits `populationVersion` is treated as
    // UNVERIFIED rather than assumed compatible (see `CalibrationViewModel`).
    let cache: CalibrationCacheState?
    let populationVersion: String?

    // MARK: - Partial-decode provenance (L2-231 Item 1)

    /// Whether the payload carried a readable `buckets` ARRAY at all.
    ///
    /// `false` covers both "the key is missing" and "the key is there but is not
    /// an array". Either way there is no curve, and that is a different fact from
    /// a served-but-empty `[]`. Neither may render as a 0.0pp result.
    let bucketsPresent: Bool
    /// Buckets the server sent that this build could not read. Non-zero means the
    /// rendered curve is built from less than the payload offered.
    let droppedBuckets: Int

    private enum CodingKeys: String, CodingKey {
        case buckets, totalMarkets, totalOutcomes, totalWinners
        case mceCiLower, mceCiUpper, mceClosingLine, mceOpeningPrice
        case generatedAt, minCategoryOutcomes, smallSampleCategories
        case corrections, dateRange, cache, populationVersion
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)

        let lossy = try? c.decode(LossyArray<CalibrationBucket>.self, forKey: .buckets)
        buckets = lossy?.elements ?? []
        droppedBuckets = lossy?.dropped ?? 0
        bucketsPresent = lossy != nil

        totalMarkets = try? c.decodeIfPresent(Int.self, forKey: .totalMarkets)
        totalOutcomes = try? c.decodeIfPresent(Int.self, forKey: .totalOutcomes)
        totalWinners = try? c.decodeIfPresent(Int.self, forKey: .totalWinners)
        mceCiLower = try? c.decodeIfPresent(Double.self, forKey: .mceCiLower)
        mceCiUpper = try? c.decodeIfPresent(Double.self, forKey: .mceCiUpper)
        mceClosingLine = try? c.decodeIfPresent(Double.self, forKey: .mceClosingLine)
        mceOpeningPrice = try? c.decodeIfPresent(Double.self, forKey: .mceOpeningPrice)
        generatedAt = try? c.decodeIfPresent(String.self, forKey: .generatedAt)
        minCategoryOutcomes = try? c.decodeIfPresent(Int.self, forKey: .minCategoryOutcomes)
        smallSampleCategories = (try? c.decode(LossyArray<SmallSampleCategory>.self,
                                               forKey: .smallSampleCategories))?.elements
        corrections = (try? c.decode(LossyArray<CalibrationCorrection>.self,
                                     forKey: .corrections))?.elements
        dateRange = try? c.decodeIfPresent(CalibrationDateRange.self, forKey: .dateRange)
        cache = try? c.decodeIfPresent(CalibrationCacheState.self, forKey: .cache)
        populationVersion = try? c.decodeIfPresent(String.self, forKey: .populationVersion)
    }
}
