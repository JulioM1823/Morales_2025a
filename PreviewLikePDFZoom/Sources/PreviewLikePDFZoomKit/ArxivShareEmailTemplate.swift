import Foundation

public enum ArxivShareEmailTemplate {
    public static func recipientDisplayName(_ recipientName: String?) -> String {
        let trimmed = (recipientName ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? "there" : trimmed
    }

    /// Returns the exact required body template:
    ///
    /// Hey [recipient],
    ///
    /// [arxiv link]
    public static func body(recipientName: String?, arxivAbsURL: String) -> String {
        "Hey \(recipientDisplayName(recipientName)),\n\n\(arxivAbsURL)"
    }
}
