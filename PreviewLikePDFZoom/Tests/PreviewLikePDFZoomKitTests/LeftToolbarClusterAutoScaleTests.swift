import XCTest
@testable import PreviewLikePDFZoomKit

final class LeftToolbarClusterAutoScaleTests: XCTestCase {
    func testSweepWidths_FitsContainer_NoOverlapInvariant() {
        let n = 3
        let baseSpacing: CGFloat = 8
        let minSpacing: CGFloat = 4
        let baseBtn: CGFloat = 31.2
        let minBtn: CGFloat = 24
        let baseSym: CGFloat = 16.9
        let minSym: CGFloat = 11

        for w in stride(from: CGFloat(0), through: 600, by: 1) {
            let out = LeftToolbarClusterAutoScale.compute(
                availableWidth: w,
                nButtons: n,
                baseSpacing: baseSpacing,
                minSpacing: minSpacing,
                baseButtonSize: baseBtn,
                minButtonSize: minBtn,
                baseSymbolPointSize: baseSym,
                minSymbolPointSize: minSym
            )
            let extent = CGFloat(n) * out.buttonSize + CGFloat(n - 1) * out.spacing
            XCTAssertLessThanOrEqual(extent, w + 1e-6, "extent must fit: w=\(w) extent=\(extent)")
            XCTAssertGreaterThanOrEqual(out.spacing, 0)
            XCTAssertGreaterThanOrEqual(out.buttonSize, 0)
            XCTAssertGreaterThanOrEqual(out.symbolPointSize, 0)
        }
    }

    func testSweepWidths_MonotonicSizing() {
        let n = 3
        let baseSpacing: CGFloat = 8
        let minSpacing: CGFloat = 4
        let baseBtn: CGFloat = 31.2
        let minBtn: CGFloat = 24
        let baseSym: CGFloat = 16.9
        let minSym: CGFloat = 11

        var last: LeftToolbarClusterAutoScale.Output?
        for w in stride(from: CGFloat(0), through: 600, by: 1) {
            let out = LeftToolbarClusterAutoScale.compute(
                availableWidth: w,
                nButtons: n,
                baseSpacing: baseSpacing,
                minSpacing: minSpacing,
                baseButtonSize: baseBtn,
                minButtonSize: minBtn,
                baseSymbolPointSize: baseSym,
                minSymbolPointSize: minSym
            )
            if let last {
                XCTAssertGreaterThanOrEqual(out.spacing + 1e-6, last.spacing, "spacing must be monotonic")
                XCTAssertGreaterThanOrEqual(out.buttonSize + 1e-6, last.buttonSize, "buttonSize must be monotonic")
                XCTAssertGreaterThanOrEqual(out.symbolPointSize + 1e-6, last.symbolPointSize, "symbolPointSize must be monotonic")
            }
            last = out
        }
    }

    func testNoOscillation_DeterministicAndEpsilonGated() {
        let n = 3
        let baseSpacing: CGFloat = 8
        let minSpacing: CGFloat = 4
        let baseBtn: CGFloat = 31.2
        let minBtn: CGFloat = 24
        let baseSym: CGFloat = 16.9
        let minSym: CGFloat = 11

        let w: CGFloat = 173
        let a = LeftToolbarClusterAutoScale.compute(
            availableWidth: w,
            nButtons: n,
            baseSpacing: baseSpacing,
            minSpacing: minSpacing,
            baseButtonSize: baseBtn,
            minButtonSize: minBtn,
            baseSymbolPointSize: baseSym,
            minSymbolPointSize: minSym
        )
        let b = LeftToolbarClusterAutoScale.compute(
            availableWidth: w,
            nButtons: n,
            baseSpacing: baseSpacing,
            minSpacing: minSpacing,
            baseButtonSize: baseBtn,
            minButtonSize: minBtn,
            baseSymbolPointSize: baseSym,
            minSymbolPointSize: minSym
        )
        XCTAssertEqual(a, b)

        let last: LeftToolbarClusterAutoScale.Output? = a
        let tinyDelta: CGFloat = 0.001
        let w2 = w + tinyDelta
        let next = LeftToolbarClusterAutoScale.compute(
            availableWidth: w2,
            nButtons: n,
            baseSpacing: baseSpacing,
            minSpacing: minSpacing,
            baseButtonSize: baseBtn,
            minButtonSize: minBtn,
            baseSymbolPointSize: baseSym,
            minSymbolPointSize: minSym
        )
        XCTAssertFalse(LeftToolbarClusterAutoScale.shouldApplyChange(last: last, next: next, epsilon: 0.02))
    }
}
