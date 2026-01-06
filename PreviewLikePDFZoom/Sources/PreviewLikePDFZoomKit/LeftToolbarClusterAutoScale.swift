import Foundation

public struct LeftToolbarClusterAutoScale {
    public struct Output: Equatable {
        public let spacing: CGFloat
        public let buttonSize: CGFloat
        public let symbolPointSize: CGFloat

        public init(spacing: CGFloat, buttonSize: CGFloat, symbolPointSize: CGFloat) {
            self.spacing = spacing
            self.buttonSize = buttonSize
            self.symbolPointSize = symbolPointSize
        }
    }

    public static func smoothstep01(_ t: CGFloat) -> CGFloat {
        let x = max(0, min(1, t))
        return x * x * (3 - 2 * x)
    }

    /// Deterministic 2-phase scaling:
    /// 1) Reduce spacing from base -> min (smoothstep easing).
    /// 2) If still too wide, reduce button size base -> min (smoothstep easing).
    /// 3) Scale SF Symbol point size base -> min using the same eased factor as (2).
    ///
    /// Guaranteed invariant for all widths (via a final clamp):
    /// N*btnSize + (N-1)*spacing <= availableWidth
    public static func compute(
        availableWidth: CGFloat,
        nButtons: Int,
        baseSpacing: CGFloat,
        minSpacing: CGFloat,
        baseButtonSize: CGFloat,
        minButtonSize: CGFloat,
        baseSymbolPointSize: CGFloat,
        minSymbolPointSize: CGFloat
    ) -> Output {
        let w = max(0, availableWidth)
        let n = CGFloat(max(1, nButtons))
        let baseSpacing = max(0, baseSpacing)
        let minSpacing = max(0, min(minSpacing, baseSpacing))

        let baseBtn = max(0, baseButtonSize)
        let minBtn = max(0, min(minButtonSize, baseBtn))

        let baseSym = max(0, baseSymbolPointSize)
        let minSym = max(0, min(minSymbolPointSize, baseSym))

        func extent(btn: CGFloat, spacing: CGFloat) -> CGFloat {
            (n * btn) + ((n - 1) * spacing)
        }

        let wBase = extent(btn: baseBtn, spacing: baseSpacing)
        if w >= wBase {
            return Output(spacing: baseSpacing, buttonSize: baseBtn, symbolPointSize: baseSym)
        }

        let wMinSpacing = extent(btn: baseBtn, spacing: minSpacing)
        if w >= wMinSpacing {
            let t = (w - wMinSpacing) / max(0.0001, (wBase - wMinSpacing))
            let eased = smoothstep01(t)
            let candidate = minSpacing + (baseSpacing - minSpacing) * eased

            // Fit clamp (guarantees N*btn + (N-1)*spacing <= w).
            let spacingMaxFit: CGFloat
            if n > 1 {
                spacingMaxFit = max(0, (w - (n * baseBtn)) / (n - 1))
            } else {
                spacingMaxFit = 0
            }

            let spacing = max(0, min(candidate, spacingMaxFit))
            return Output(spacing: spacing, buttonSize: baseBtn, symbolPointSize: baseSym)
        }

        // Phase 2
        var spacing = minSpacing

        // If even min spacing can't fit, shrink spacing below min (final guard).
        if n > 1, w < ((n - 1) * spacing) {
            spacing = w / (n - 1)
            return Output(spacing: spacing, buttonSize: 0, symbolPointSize: 0)
        }

        let btnNeeded = max(0, (w - ((n - 1) * spacing)) / n)

        let btn: CGFloat
        let sym: CGFloat

        if btnNeeded >= baseBtn {
            btn = baseBtn
            sym = baseSym
        } else if btnNeeded >= minBtn {
            let t = (btnNeeded - minBtn) / max(0.0001, (baseBtn - minBtn))
            let eased = smoothstep01(t)
            let btnCandidate = minBtn + (baseBtn - minBtn) * eased
            let symCandidate = minSym + (baseSym - minSym) * eased

            // Fit clamp (guarantees btn <= btnNeeded).
            btn = min(btnCandidate, btnNeeded)
            sym = (btnCandidate > 0) ? (symCandidate * (btn / btnCandidate)) : symCandidate
        } else {
            btn = btnNeeded
            let scale = (minBtn > 0) ? (btn / minBtn) : 0
            sym = minSym * scale
        }

        // Final guard clamp (spec)
        let btnClamped = min(btn, btnNeeded)
        let symClamped = (btn > 0) ? (sym * (btnClamped / btn)) : sym

        return Output(spacing: spacing, buttonSize: btnClamped, symbolPointSize: symClamped)
    }

    public static func shouldApplyChange(last: Output?, next: Output, epsilon: CGFloat) -> Bool {
        guard let last else { return true }
        let eps = max(0, epsilon)
        if abs(last.spacing - next.spacing) > eps { return true }
        if abs(last.buttonSize - next.buttonSize) > eps { return true }
        if abs(last.symbolPointSize - next.symbolPointSize) > eps { return true }
        return false
    }
}
