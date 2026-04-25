#if canImport(UIKit)
import UIKit
#elseif canImport(AppKit)
import AppKit
#endif

actor ImageCache {
    static let shared = ImageCache()

    private let cache = NSCache<NSString, PlatformImage>()
    private var inflight: [String: Task<PlatformImage?, Never>] = [:]

    private init() {
        cache.countLimit = 200
        cache.totalCostLimit = 50 * 1024 * 1024  // 50 MB
    }

    func image(for url: URL) async -> PlatformImage? {
        let key = url.absoluteString as NSString

        if let cached = cache.object(forKey: key) {
            return cached
        }

        if let existing = inflight[url.absoluteString] {
            return await existing.value
        }

        let task = Task<PlatformImage?, Never> {
            guard let (data, _) = try? await URLSession.shared.data(from: url),
                  let image = PlatformImage(data: data) else {
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
