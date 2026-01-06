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

    mutating func assertApprox(_ a: Double, _ b: Double, eps: Double = 1e-6, _ message: String) {
        if abs(a - b) > eps {
            failures += 1
            print("FAIL: \(message) (\(a) vs \(b))")
        }
    }
}

// Keep these in sync with arxiv-picker.swift (ToolbarResizeMotionSpec + SpringTracker).
struct ToolbarResizeMotionSpec {
    let dampingRatio: Double = 0.84
    let omegaSmallDelta: Double = 16.0
    let omegaLargeDelta: Double = 14.0
    let omegaLargeDeltaThreshold: Double = 0.12

    let overshootCapFractionOfTarget: Double = 0.03
    let settle95MaxSeconds: Double = 0.28
}

struct SpringTracker {
    var value: Double
    var velocity: Double
    var target: Double

    mutating func reset(to v: Double) {
        value = v
        velocity = 0
        target = v
    }

    mutating func step(dt rawDt: Double, dampingRatio: Double, omega: Double) {
        let dt = max(1.0 / 240.0, min(1.0 / 30.0, rawDt))
        // x'' + 2ζω x' + ω^2 (x - target) = 0
        let x = value
        let v = velocity
        let a = (-2 * dampingRatio * omega * v) - (omega * omega * (x - target))
        let vNext = v + a * dt
        let xNext = x + vNext * dt
        velocity = vNext
        value = xNext
    }
}

func omega(forDelta delta: Double, spec: ToolbarResizeMotionSpec) -> Double {
    let t = max(0, min(1, delta / max(0.001, spec.omegaLargeDeltaThreshold)))
    return spec.omegaSmallDelta + (spec.omegaLargeDelta - spec.omegaSmallDelta) * t
}

func normalizedScaleMin(toolbarControlScaleBase: Double = 1.3, toolbarControlScaleMin: Double = 1.05) -> Double {
    (toolbarControlScaleMin * 0.85) / toolbarControlScaleBase
}

func runTests() -> Int {
    var t = TestRunner()
    let spec = ToolbarResizeMotionSpec()

    // 1) Sanity: derived min normalized scale matches expectation.
    do {
        let sMin = normalizedScaleMin()
        t.assertTrue(sMin > 0.65 && sMin < 0.70, "normalized_scale_min_in_expected_range")
    }

    // 2) Settle-to-95% time bound (simulate at 60Hz, variable omega based on current delta).
    func timeTo95(from: Double, to: Double) -> Double {
        var tr = SpringTracker(value: from, velocity: 0, target: to)
        var time = 0.0
        let step = 1.0 / 60.0
        let delta0 = abs(to - from)
        let tol = 0.05 * max(1e-6, delta0)

        // Run up to 0.6s to be safe.
        for _ in 0..<Int(0.6 / step) {
            let d = abs(tr.target - tr.value)
            tr.step(dt: step, dampingRatio: spec.dampingRatio, omega: omega(forDelta: d, spec: spec))
            time += step
            if abs(tr.value - tr.target) <= tol {
                return time
            }
        }
        return Double.infinity
    }

    do {
        let sMin = normalizedScaleMin()
        let large = timeTo95(from: 1.0, to: sMin)
        print(String(format: "measured settle95 large=%.3f s (target=%.4f)", large, sMin))
        t.assertTrue(large.isFinite && large <= spec.settle95MaxSeconds, "settle95_large_delta_<=_280ms")

        let small = timeTo95(from: 1.0, to: 0.98)
        print(String(format: "measured settle95 small=%.3f s", small))
        t.assertTrue(small.isFinite && small <= spec.settle95MaxSeconds, "settle95_small_delta_<=_280ms")
    }

    // 3) Overshoot cap <= 3% of target (after stop).
    do {
        let sMin = normalizedScaleMin()
        var tr = SpringTracker(value: 1.0, velocity: 0, target: sMin)
        let step = 1.0 / 60.0
        var minValue = tr.value
        for _ in 0..<Int(0.6 / step) {
            let d = abs(tr.target - tr.value)
            tr.step(dt: step, dampingRatio: spec.dampingRatio, omega: omega(forDelta: d, spec: spec))
            minValue = min(minValue, tr.value)
        }
        // For a downward step, overshoot manifests as going below target.
        let cap = spec.overshootCapFractionOfTarget * max(1e-6, abs(sMin))
        t.assertTrue(minValue >= sMin - cap, "overshoot_cap_<=_3pct_of_target")
    }

    // 4) Tracking stability under continuous resize-like target changes.
    do {
        let sMin = normalizedScaleMin()
        var tr = SpringTracker(value: 1.0, velocity: 0, target: 1.0)
        let step = 1.0 / 60.0

        // Simulate 2 seconds of interactive resize: target ramps down then up.
        for i in 0..<120 {
            let a = Double(i) / 119.0
            tr.target = 1.0 + (sMin - 1.0) * a
            let d = abs(tr.target - tr.value)
            tr.step(dt: step, dampingRatio: spec.dampingRatio, omega: omega(forDelta: d, spec: spec))
            t.assertTrue(tr.value.isFinite && tr.velocity.isFinite, "tracking_down_finite")
            t.assertTrue(tr.value >= sMin - 0.05 && tr.value <= 1.05, "tracking_down_in_reasonable_bounds")
        }
        for i in 0..<120 {
            let a = Double(i) / 119.0
            tr.target = sMin + (1.0 - sMin) * a
            let d = abs(tr.target - tr.value)
            tr.step(dt: step, dampingRatio: spec.dampingRatio, omega: omega(forDelta: d, spec: spec))
            t.assertTrue(tr.value.isFinite && tr.velocity.isFinite, "tracking_up_finite")
            t.assertTrue(tr.value >= sMin - 0.05 && tr.value <= 1.05, "tracking_up_in_reasonable_bounds")
        }
    }

    if t.failures == 0 { print("OK") }
    return t.failures
}

exit(Int32(runTests()))
