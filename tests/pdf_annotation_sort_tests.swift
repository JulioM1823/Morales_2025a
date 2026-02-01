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

    mutating func assertEqual<T: Equatable>(_ a: T, _ b: T, _ message: String) {
        if a != b {
            failures += 1
            print("FAIL: \(message) (\(a) vs \(b))")
        }
    }
}

struct SortItem {
    let pageIndex: Int
    let topOffset: Double
    let timestamp: Double
    let id: String
}

func sortItems(_ items: [SortItem]) -> [SortItem] {
    return items.sorted { lhs, rhs in
        if lhs.pageIndex != rhs.pageIndex { return lhs.pageIndex < rhs.pageIndex }
        if abs(lhs.topOffset - rhs.topOffset) > 0.5 { return lhs.topOffset < rhs.topOffset }
        if lhs.timestamp != rhs.timestamp { return lhs.timestamp < rhs.timestamp }
        return lhs.id < rhs.id
    }
}

func topOffset(pageMaxY: Double, rectMaxY: Double) -> Double {
    max(0, pageMaxY - rectMaxY)
}

func runTests() -> Int {
    var t = TestRunner()

    // 1) Page ordering wins over vertical ordering.
    do {
        let items = [
            SortItem(pageIndex: 1, topOffset: 10, timestamp: 1, id: "b"),
            SortItem(pageIndex: 0, topOffset: 100, timestamp: 1, id: "a")
        ]
        let sorted = sortItems(items)
        t.assertEqual(sorted.first?.pageIndex, 0, "page_ordering_primary")
    }

    // 2) Higher on page (smaller topOffset) sorts first.
    do {
        let pageMaxY = 1000.0
        let topA = topOffset(pageMaxY: pageMaxY, rectMaxY: 920.0) // near top
        let topB = topOffset(pageMaxY: pageMaxY, rectMaxY: 700.0) // lower
        let items = [
            SortItem(pageIndex: 0, topOffset: topB, timestamp: 1, id: "b"),
            SortItem(pageIndex: 0, topOffset: topA, timestamp: 1, id: "a")
        ]
        let sorted = sortItems(items)
        t.assertEqual(sorted.first?.id, "a", "vertical_ordering_top_first")
    }

    // 3) Tie-breaker: timestamp then id for stability.
    do {
        let items = [
            SortItem(pageIndex: 0, topOffset: 20, timestamp: 2, id: "b"),
            SortItem(pageIndex: 0, topOffset: 20, timestamp: 1, id: "c"),
            SortItem(pageIndex: 0, topOffset: 20, timestamp: 1, id: "a")
        ]
        let sorted = sortItems(items)
        t.assertEqual(sorted.map { $0.id }, ["a", "c", "b"], "tie_breaker_timestamp_then_id")
    }

    if t.failures == 0 {
        print("OK")
    }
    return t.failures
}

exit(Int32(runTests()))
