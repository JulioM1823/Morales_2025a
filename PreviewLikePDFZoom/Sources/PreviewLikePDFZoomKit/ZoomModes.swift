import Foundation

public enum ZoomMode: Equatable, Sendable {
    case fitToWidth
    case fitToPage
    case actualSize
    case custom(scale: CGFloat)

    public var isFit: Bool {
        switch self {
        case .fitToWidth, .fitToPage: return true
        case .actualSize, .custom: return false
        }
    }

    public var customScale: CGFloat? {
        switch self {
        case .custom(let s): return s
        case .actualSize: return 1.0
        default: return nil
        }
    }
}
