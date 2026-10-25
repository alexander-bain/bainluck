// Minimal assertion runner for the exact reader XCTest methods. This is not
// XCTest discovery, an app build, model qualification or UI verification.
import Foundation
class XCTestCase {}
enum ReaderChecks { nonisolated(unsafe) static var failures = 0; nonisolated(unsafe) static var assertions = 0 }
func check(_ pass: Bool, _ message: String, file: StaticString, line: UInt) {
    ReaderChecks.assertions += 1
    if !pass { ReaderChecks.failures += 1; print("FAIL \(file):\(line) \(message)") }
}
func XCTAssertEqual<T: Equatable>(_ lhs: @autoclosure () throws -> T, _ rhs: @autoclosure () throws -> T,
                                  _ message: String = "", file: StaticString = #filePath, line: UInt = #line) {
    do { let l = try lhs(), r = try rhs(); check(l == r, "\(message) \(l) != \(r)", file: file, line: line) }
    catch { check(false, "\(error)", file: file, line: line) }
}
func XCTAssertNotEqual<T: Equatable>(_ lhs: @autoclosure () throws -> T, _ rhs: @autoclosure () throws -> T,
                                     _ message: String = "", file: StaticString = #filePath, line: UInt = #line) {
    do { check(try lhs() != rhs(), message, file: file, line: line) }
    catch { check(false, "\(error)", file: file, line: line) }
}
func XCTAssertNil<T>(_ value: @autoclosure () throws -> T?, _ message: String = "",
                      file: StaticString = #filePath, line: UInt = #line) {
    do { check(try value() == nil, message, file: file, line: line) }
    catch { check(false, "\(error)", file: file, line: line) }
}
func XCTUnwrap<T>(_ value: @autoclosure () throws -> T?) throws -> T {
    guard let result = try value() else { throw NSError(domain: "ReaderCheck.unwrap", code: 1) }
    return result
}
