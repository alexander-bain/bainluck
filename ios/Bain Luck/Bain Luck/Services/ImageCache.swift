import UIKit

/// In-memory image cache backed by NSCache with in-flight request deduplication.
/// NSCache auto-evicts entries under memory pressure.
actor ImageCache {
    static let shared = ImageCache()

    private let cache = NSCache<NSString, UIImage>()
    private var inflight: [String: Task<UIImage?, Never>] = [:]

    private init() {
        cache.countLimit = 200
        cache.totalCostLimit = 50 * 1024 * 1024  // 50 MB
    }

    func image(for url: URL) async -> UIImage? {
        let key = url.absoluteString as NSString

        // Check memory cache
        if let cached = cache.object(forKey: key) {
            return cached
        }

        // Deduplicate in-flight requests for same URL
        if let existing = inflight[url.absoluteString] {
            return await existing.value
        }

        let task = Task<UIImage?, Never> {
            guard let (data, _) = try? await URLSession.shared.data(from: url),
                  let image = UIImage(data: data) else {
                return nil
            }
            cache.setObject(image, forKey: key, cost: data.count)
            return image
        }

        inflight[url.absoluteString] = task
        let result = await task.value
        inflight.removeValue(forKey: url.absoluteString)
        return result
    }
}
