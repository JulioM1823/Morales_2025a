import Foundation

enum AppLaunchMode: Equatable {
    case normal
    case backgroundRefresh

    static func resolve(arguments: [String]) -> AppLaunchMode {
        if arguments.contains("--refresh") || arguments.contains("--background-refresh") {
            return .backgroundRefresh
        }
        return .normal
    }
}
