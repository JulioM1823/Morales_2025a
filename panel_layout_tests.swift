#!/usr/bin/env swift
import Foundation

struct TestRunner {
    private(set) var failures: Int = 0

    mutating func assertTrue(_ condition: Bool, _ message: String) {
        if !condition {
            failures += 1
            print("FAIL: \(message)")
        }
    }

    mutating func assertApprox(_ a: Double, _ b: Double, eps: Double = 1e-9, _ message: String) {
        if abs(a - b) > eps {
            failures += 1
            print("FAIL: \(message) (\(a) vs \(b))")
        }
    }
}

func clampRightAuxDividerPosition(
    proposed: Double,
    total: Double,
    divider: Double,
    minPrimary: Double,
    minAux: Double
) -> Double {
    let maxPrimaryNoNegativeAux = max(0, total - divider)
    let minPrimaryFeasible = min(minPrimary, maxPrimaryNoNegativeAux)

    let maxPrimaryFromAuxMin = total - divider - minAux
    let maxPrimary: Double
    if maxPrimaryFromAuxMin >= minPrimaryFeasible {
        maxPrimary = min(maxPrimaryNoNegativeAux, maxPrimaryFromAuxMin)
    } else {
        maxPrimary = maxPrimaryNoNegativeAux
    }

    return min(max(proposed, minPrimaryFeasible), maxPrimary)
}

func auxWidth(total: Double, divider: Double, primary: Double) -> Double {
    max(0, total - divider - primary)
}

func minOuterRightWidth(minRightPanelWidth: Double, rightAuxOpen: Bool, rightAuxDivider: Double, minAuxWidth: Double) -> Double {
    rightAuxOpen ? (minRightPanelWidth + rightAuxDivider + minAuxWidth) : minRightPanelWidth
}

func runTests() -> Int {
    var t = TestRunner()

    // 1) Outer min width calculation
    do {
        let wClosed = minOuterRightWidth(minRightPanelWidth: 260, rightAuxOpen: false, rightAuxDivider: 14, minAuxWidth: 260)
        t.assertApprox(wClosed, 260, "outer_min_right_closed")

        let wOpen = minOuterRightWidth(minRightPanelWidth: 260, rightAuxOpen: true, rightAuxDivider: 14, minAuxWidth: 260)
        t.assertApprox(wOpen, 534, "outer_min_right_open")
    }

    // 2) Inner clamp never yields negative aux width
    do {
        let total = 300.0
        let divider = 14.0
        let pos = clampRightAuxDividerPosition(proposed: 200, total: total, divider: divider, minPrimary: 260, minAux: 260)
        t.assertTrue(pos >= 0 && pos <= (total - divider), "inner_pos_in_bounds")
        let w = auxWidth(total: total, divider: divider, primary: pos)
        t.assertTrue(w >= 0, "inner_aux_nonnegative")
    }

    // 3) When feasible, clamp enforces min aux by limiting max primary
    do {
        let total = 1000.0
        let divider = 14.0
        let minPrimary = 260.0
        let minAux = 260.0
        let proposed = 900.0 // would starve aux
        let pos = clampRightAuxDividerPosition(proposed: proposed, total: total, divider: divider, minPrimary: minPrimary, minAux: minAux)
        let w = auxWidth(total: total, divider: divider, primary: pos)
        t.assertTrue(w + 1e-9 >= minAux, "inner_aux_respects_min_when_feasible")
    }

    // 4) Target position mapping: pos = total - divider - auxWidth
    do {
        let total = 1200.0
        let divider = 14.0
        let targetAux = 420.0
        let pos = total - divider - targetAux
        let w = auxWidth(total: total, divider: divider, primary: pos)
        t.assertApprox(w, targetAux, "target_mapping")
    }

    if t.failures == 0 {
        print("OK")
    }
    return t.failures
}

exit(Int32(runTests()))
