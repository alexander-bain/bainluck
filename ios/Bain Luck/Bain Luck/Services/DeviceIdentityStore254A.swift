#if os(iOS)
import Foundation
import Security

/// #13052 / 177-A: per-install device identity and 32-byte random secret held in Keychain.
/// Never logged; sent only in `PUT /api/devices/{device_id}` (`X-Device-Secret`) and
/// device-owned ActivityKit registrations (`X-Device-Id` + `X-Device-Secret`).
nonisolated struct DeviceIdentity254A: Equatable, Sendable {
    let deviceID: UUID
    let secret: String

    /// 32 random bytes encoded as 64 lowercase hex characters (`backend/app/dependencies/device_auth.py`).
    static let secretByteCount = 32
    static let secretHexLength = 64

    static func generateSecret() -> String {
        var bytes = [UInt8](repeating: 0, count: secretByteCount)
        let status = SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes)
        if status != errSecSuccess {
            // Cryptographic RNG fallback using SystemRandomNumberGenerator if SecRandom fails.
            var rng = SystemRandomNumberGenerator()
            for i in bytes.indices {
                bytes[i] = UInt8.random(in: 0...255, using: &rng)
            }
        }
        return bytes.map { String(format: "%02x", $0) }.joined()
    }
}

protocol DeviceIdentityStoring254A: Sendable {
    func loadOrCreate() -> DeviceIdentity254A
}

final class KeychainDeviceIdentityStore254A: DeviceIdentityStoring254A {
    static let shared = KeychainDeviceIdentityStore254A()
    private static let idKey = "bainluck.pushDevice.id.v1"
    private static let secretKey = "bainluck.pushDevice.secret.v1"

    func loadOrCreate() -> DeviceIdentity254A {
        if let idData = KeychainHelper.load(key: Self.idKey),
           let idString = String(data: idData, encoding: .utf8),
           let uuid = UUID(uuidString: idString),
           let secretData = KeychainHelper.load(key: Self.secretKey),
           let secret = String(data: secretData, encoding: .utf8),
           secret.count >= 32, secret.count <= 256 {
            return DeviceIdentity254A(deviceID: uuid, secret: secret)
        }

        let uuid = UUID()
        let secret = DeviceIdentity254A.generateSecret()
        _ = KeychainHelper.save(key: Self.idKey, data: Data(uuid.uuidString.lowercased().utf8))
        _ = KeychainHelper.save(key: Self.secretKey, data: Data(secret.utf8))
        return DeviceIdentity254A(deviceID: uuid, secret: secret)
    }
}
#endif
