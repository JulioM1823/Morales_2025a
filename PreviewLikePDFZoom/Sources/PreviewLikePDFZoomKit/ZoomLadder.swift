import Foundation

public enum ZoomLadder {
    /// Deterministic Preview-like discrete zoom steps.
    ///
    /// - 10% increments from 10% to 200%
    /// - 25% increments from 200% to 800%
    public static func nextStep(from scale: CGFloat, direction: Direction) -> CGFloat {
        let clamped = max(0.01, scale)

        func roundTo(_ value: CGFloat, quantum: CGFloat) -> CGFloat {
            guard quantum > 0 else { return value }
            return (value / quantum).rounded() * quantum
        }

        // Treat 2.0 as boundary.
        if clamped < 2.0 {
            let q: CGFloat = 0.1
            let v = clamped
            switch direction {
            case .in:
                let next = ((v + 1e-6) / q).rounded(.down) + 1
                return max(q, next * q)
            case .out:
                let prev = ((v - 1e-6) / q).rounded(.up) - 1
                return max(q, prev * q)
            }
        } else {
            let q: CGFloat = 0.25
            let v = roundTo(clamped, quantum: q)
            switch direction {
            case .in:
                return v + q
            case .out:
                return max(0.1, v - q)
            }
        }
    }

    public enum Direction {
        case `in`
        case out
    }
}
