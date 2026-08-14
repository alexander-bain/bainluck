#if canImport(UIKit)
import UIKit
typealias PlatformImage = UIImage
typealias PlatformApp = UIApplication
#elseif canImport(AppKit)
import AppKit
typealias PlatformImage = NSImage
typealias PlatformApp = NSApplication
#endif

import SwiftUI

extension Image {
    init(platformImage: PlatformImage) {
        #if canImport(UIKit)
        self.init(uiImage: platformImage)
        #elseif canImport(AppKit)
        self.init(nsImage: platformImage)
        #endif
    }
}
