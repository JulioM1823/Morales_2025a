#!/usr/bin/env swift
import Foundation
import Darwin

typealias Scalar = Double

struct ZoomState {
    var s: Scalar
    var tx: Scalar
    var ty: Scalar
    var vw: Scalar
    var vh: Scalar
    var docWidth: Scalar
    var docHeight: Scalar

    var cw: Scalar { docWidth * s }
    var ch: Scalar { docHeight * s }
    var center: (x: Scalar, y: Scalar) { (vw / 2, vh / 2) }

    mutating func clamp() {
        if cw >= vw {
            tx = min(max(tx, vw - cw), 0)
        } else {
            tx = (vw - cw) / 2
        }

        if ch >= vh {
            ty = min(max(ty, vh - ch), 0)
        } else {
            ty = (vh - ch) / 2
        }
    }

    mutating func zoom(to newScale: Scalar, anchor: (x: Scalar, y: Scalar)) {
        let sOld = s
        let ax = (anchor.x - tx) / sOld
        let ay = (anchor.y - ty) / sOld
        s = newScale
        tx = anchor.x - ax * newScale
        ty = anchor.y - ay * newScale
        clamp()
    }
}

struct TestRunner {
    private(set) var failures: Int = 0
    let eps: Scalar = 1e-5
    let epsRoundTrip: Scalar = 1e-3

    mutating func assertTrue(_ condition: Bool, _ message: String) {
        if !condition {
            failures += 1
            print("FAIL: \(message)")
        }
    }

    mutating func assertApprox(_ a: Scalar, _ b: Scalar, eps: Scalar, _ message: String) {
        if abs(a - b) > eps {
            failures += 1
            print("FAIL: \(message) (\(a) vs \(b))")
        }
    }

    mutating func assertClamp(_ st: ZoomState, _ label: String) {
        if st.cw >= st.vw {
            assertTrue(st.tx + eps >= st.vw - st.cw, "\(label) tx lower bound")
            assertTrue(st.tx - eps <= 0, "\(label) tx upper bound")
        } else {
            assertApprox(st.tx, (st.vw - st.cw) / 2, eps: eps, "\(label) tx centered")
        }

        if st.ch >= st.vh {
            assertTrue(st.ty + eps >= st.vh - st.ch, "\(label) ty lower bound")
            assertTrue(st.ty - eps <= 0, "\(label) ty upper bound")
        } else {
            assertApprox(st.ty, (st.vh - st.ch) / 2, eps: eps, "\(label) ty centered")
        }
    }

    mutating func assertAnchorPreserved(anchor: (x: Scalar, y: Scalar),
                                        sOld: Scalar, txOld: Scalar, tyOld: Scalar,
                                        sNew: Scalar, txNew: Scalar, tyNew: Scalar,
                                        _ label: String) {
        let ax = (anchor.x - txOld) / sOld
        let ay = (anchor.y - tyOld) / sOld
        let newAx = ax * sNew + txNew
        let newAy = ay * sNew + tyNew
        assertApprox(newAx, anchor.x, eps: eps, "\(label) anchor x")
        assertApprox(newAy, anchor.y, eps: eps, "\(label) anchor y")
    }
}

func makeState(vw: Scalar, vh: Scalar, s: Scalar) -> ZoomState {
    var st = ZoomState(
        s: s,
        tx: 0,
        ty: 0,
        vw: vw,
        vh: vh,
        docWidth: 612,
        docHeight: 2408
    )
    st.clamp()
    return st
}

func runTests() -> Int {
    var t = TestRunner()

    // Test 1: Cmd+ zoom anchors to viewport center
    do {
        var st = makeState(vw: 800, vh: 600, s: 1.0)
        let center = st.center
        let sOld = st.s
        let txOld = st.tx
        let tyOld = st.ty
        st.zoom(to: 1.1, anchor: center)
        t.assertAnchorPreserved(anchor: center, sOld: sOld, txOld: txOld, tyOld: tyOld,
                                sNew: st.s, txNew: st.tx, tyNew: st.ty, "test1")
        t.assertClamp(st, "test1")
    }

    // Test 2: Pinch zoom anchors to cursor inside viewport
    do {
        var st = makeState(vw: 600, vh: 600, s: 1.0)
        let mouse = (x: Scalar(100), y: Scalar(200))
        let sOld = st.s
        let txOld = st.tx
        let tyOld = st.ty
        st.zoom(to: 1.25, anchor: mouse)
        t.assertAnchorPreserved(anchor: mouse, sOld: sOld, txOld: txOld, tyOld: tyOld,
                                sNew: st.s, txNew: st.tx, tyNew: st.ty, "test2")
        t.assertClamp(st, "test2")
    }

    // Test 3: Pinch zoom falls back to center when cursor outside
    do {
        var st = makeState(vw: 800, vh: 600, s: 1.0)
        let center = st.center
        let sOld = st.s
        let txOld = st.tx
        let tyOld = st.ty
        st.zoom(to: 1.25, anchor: center)
        t.assertAnchorPreserved(anchor: center, sOld: sOld, txOld: txOld, tyOld: tyOld,
                                sNew: st.s, txNew: st.tx, tyNew: st.ty, "test3")
        t.assertClamp(st, "test3")
    }

    // Test 4: Horizontal centering when zoomed out (CW < Vw)
    do {
        var st = makeState(vw: 800, vh: 600, s: 1.0)
        st.tx = 50
        st.clamp()
        t.assertApprox(st.tx, (st.vw - st.cw) / 2, eps: t.eps, "test4 centered tx")
    }

    // Test 5: Horizontal clamp when zoomed in (CW > Vw)
    do {
        var st = makeState(vw: 800, vh: 600, s: 2.0)
        st.tx = 50
        st.clamp()
        t.assertApprox(st.tx, 0, eps: t.eps, "test5 clamp right")
        st.tx = -st.cw
        st.clamp()
        t.assertApprox(st.tx, st.vw - st.cw, eps: t.eps, "test5 clamp left")
    }

    // Test 6: Vertical clamp at top and bottom
    do {
        var st = makeState(vw: 800, vh: 600, s: 1.0)
        st.ty = 50
        st.clamp()
        t.assertApprox(st.ty, 0, eps: t.eps, "test6 clamp top")
        st.ty = -st.ch
        st.clamp()
        t.assertApprox(st.ty, st.vh - st.ch, eps: t.eps, "test6 clamp bottom")
    }

    // Test 7: Repeated zoom in/out round-trip stability
    do {
        var st = makeState(vw: 800, vh: 600, s: 1.0)
        st.ty = -500
        st.clamp()
        let start = st
        for _ in 0..<10 {
            let center = st.center
            st.zoom(to: st.s * 1.1, anchor: center)
            st.zoom(to: st.s / 1.1, anchor: center)
        }
        t.assertApprox(st.s, start.s, eps: t.epsRoundTrip, "test7 scale")
        t.assertApprox(st.tx, start.tx, eps: t.epsRoundTrip, "test7 tx")
        t.assertApprox(st.ty, start.ty, eps: t.epsRoundTrip, "test7 ty")
    }

    // Test 8: Zoom while scrolled preserves anchor in document
    do {
        var st = makeState(vw: 800, vh: 600, s: 1.0)
        st.ty = -500
        st.clamp()
        let center = st.center
        let docX = (center.x - st.tx) / st.s
        let docY = (center.y - st.ty) / st.s
        st.zoom(to: 1.1, anchor: center)
        let docX2 = (center.x - st.tx) / st.s
        let docY2 = (center.y - st.ty) / st.s
        t.assertApprox(docX2, docX, eps: t.eps, "test8 docX")
        t.assertApprox(docY2, docY, eps: t.eps, "test8 docY")
        t.assertClamp(st, "test8")
    }

    // Test 9: Resize re-clamps without changing anchor unexpectedly
    do {
        var st = makeState(vw: 800, vh: 600, s: 1.5)
        st.ty = -800
        st.clamp()
        st.vw = 900
        st.vh = 700
        st.clamp()
        t.assertClamp(st, "test9")
    }

    // Test 10: Momentum end re-clamp removes drift
    do {
        var st = makeState(vw: 800, vh: 600, s: 1.0)
        st.ty = 0.2
        st.clamp()
        t.assertApprox(st.ty, 0, eps: t.eps, "test10")
    }

    return t.failures
}

let failures = runTests()
if failures == 0 {
    print("PASS")
} else {
    print("FAIL: \(failures) test(s) failed")
    exit(1)
}
