import Foundation

/// The 2026-08-02 production `/api/calibration` payload, losslessly compacted.
///
/// L2-231 Item 2 asks for native/web parity "on the same fixture". The live
/// payload is 340 KB of 1,606 buckets keyed by
/// source, category, `price_moved` and bucket index. Every metric this surface
/// renders that is NOT per-category — the combined cohort, the activity
/// partitions, and each per-source row — is computed by summing `n`, `winners`
/// and `sum_prob` into bucket-index bins, so pre-summing the category dimension
/// away leaves those numbers bit-identical while cutting the fixture to 68 rows.
/// That equality was verified against the full payload before the fixture was
/// frozen: combined / all-markets / moved / unchanged / not-applicable ECE,
/// MCE and Brier, and all five per-source ECEs, matched to 1e-9.
///
/// WHAT THIS FIXTURE CANNOT PROVE, stated so nobody reads more into it: the
/// per-CATEGORY rows. The category dimension is the one that was summed away, so
/// `category` reads `"agg"` on every row. Category rollup and the sample gate are
/// covered by the synthetic fixtures in `CalibrationSurfaceTests`.
///
/// Frozen deliberately. It is a record of one real server response, not a live
/// feed — regenerating it whenever production moves would destroy the only thing
/// it is for.
enum CalibrationProdFixture {

    /// `population_version` as the server published it in this response. Used to
    /// prove the shipped compatible set accepts the payload production is
    /// actually serving.
    static let publishedPopulationVersion = "q267"

    /// `cache` as served: a dated last-good copy, 86461 s old.
    static let servedCacheStatus = "stale"

    /// The payload, read from the ONE tracked copy: the repo-root
    /// `fixtures/calibration/prod-2026-08-02.json`, built into this test bundle
    /// as a resource (#1778). There is no embedded fallback — a missing,
    /// unreadable or empty resource stops the run by name rather than letting a
    /// test grade something other than the shared payload.
    static let json: String = {
        let bundle = Bundle(for: BundleToken.self)
        guard let url = bundle.url(forResource: resourceName, withExtension: "json") else {
            preconditionFailure(
                "\(resourceName).json is not a resource of \(bundle.bundlePath). "
                    + "BainLuckTests must copy fixtures/calibration/\(resourceName).json "
                    + "(project.pbxproj, BainLuckTests Resources phase)."
            )
        }
        guard let data = try? Data(contentsOf: url),
              let text = String(data: data, encoding: .utf8),
              !text.isEmpty
        else {
            preconditionFailure("\(url.path) is unreadable or empty.")
        }
        return text
    }()

    /// The shared payload's file name, without extension.
    static let resourceName = "prod-2026-08-02"

    private final class BundleToken {}
}
