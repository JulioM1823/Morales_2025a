import AppKit
import XCTest

private final class SnapshotTestingBundleToken: NSObject {}

enum SnapshotTesting {
    struct DiffResult {
        let maxAbs: UInt8
        let meanAbs: Double
    }

    static func pngData(of view: NSView) -> Data {
        let bounds = view.bounds
        let rep = view.bitmapImageRepForCachingDisplay(in: bounds)!
        rep.size = bounds.size
        view.cacheDisplay(in: bounds, to: rep)
        return rep.representation(using: .png, properties: [:])!
    }

    static func diffRGBA8(_ a: Data, _ b: Data) throws -> DiffResult {
        // Use NSBitmapImageRep to access raw pixels.
        guard let repA = NSBitmapImageRep(data: a),
              let repB = NSBitmapImageRep(data: b) else {
            throw NSError(domain: "Snapshot", code: 1)
        }
        guard repA.pixelsWide == repB.pixelsWide,
              repA.pixelsHigh == repB.pixelsHigh else {
            throw NSError(domain: "Snapshot", code: 2)
        }

        guard let dataA = repA.bitmapData,
              let dataB = repB.bitmapData else {
            throw NSError(domain: "Snapshot", code: 3)
        }

        let bytesPerRowA = repA.bytesPerRow
        let bytesPerRowB = repB.bytesPerRow
        let w = repA.pixelsWide
        let h = repA.pixelsHigh

        var maxAbs: UInt8 = 0
        var sumAbs: Double = 0
        var count: Double = 0

        // Compare RGBA channels.
        for y in 0..<h {
            let rowA = dataA.advanced(by: y * bytesPerRowA)
            let rowB = dataB.advanced(by: y * bytesPerRowB)
            for x in 0..<w {
                let i = x * 4
                for c in 0..<4 {
                    let da = rowA[i + c]
                    let db = rowB[i + c]
                    let d = da > db ? (da - db) : (db - da)
                    if d > maxAbs { maxAbs = d }
                    sumAbs += Double(d)
                    count += 1
                }
            }
        }

        return DiffResult(maxAbs: maxAbs, meanAbs: sumAbs / max(1, count))
    }

    static func assertSnapshot(
        named name: String,
        data: Data,
        record: Bool,
        file: StaticString = #filePath,
        line: UInt = #line
    ) throws {
        let fm = FileManager.default
        let baselineURL = Bundle(for: SnapshotTestingBundleToken.self).resourceURL!.appendingPathComponent("\(name).png")

        if record {
            try data.write(to: baselineURL)
            XCTFail("Recorded snapshot baseline: \(baselineURL.path)", file: file, line: line)
            return
        }

        guard fm.fileExists(atPath: baselineURL.path) else {
            XCTFail("Missing baseline snapshot \(baselineURL.lastPathComponent). Run with SNAPSHOT_RECORD=1 to generate.", file: file, line: line)
            return
        }

        let baseline = try Data(contentsOf: baselineURL)
        let diff = try diffRGBA8(baseline, data)

        // Strict by default; allow very small AA differences.
        // meanAbs is in [0,255].
        XCTAssertLessThanOrEqual(diff.maxAbs, 8, "Pixel max diff too large: \(diff.maxAbs)", file: file, line: line)
        XCTAssertLessThanOrEqual(diff.meanAbs, 0.50, "Pixel mean diff too large: \(diff.meanAbs)", file: file, line: line)
    }
}
