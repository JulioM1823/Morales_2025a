import AppKit
import WebKit
import PDFKit
import Foundation
import CryptoKit
import QuartzCore
import ImageIO
import CoreImage
import CoreImage.CIFilterBuiltins
import CoreGraphics
import Metal
import CoreText
import os
import Security
import CoreServices
#if canImport(XCTest)
import XCTest
#endif

// MARK: - Model

struct Paper: Equatable, Codable {
    let index: Int
    let title: String
    let authors: String
    let categories: String
    let dateLine: String
    let url: String
    let comments: String
    let abstractText: String
    let receivedAt: Date?
}

// MARK: - Share URL normalization (canonical arXiv /abs/)

enum ArxivShareDebug {
    static let enabled: Bool = (ProcessInfo.processInfo.environment["ARXIV_SHARE_DEBUG"] == "1")
    static func log(_ message: String) {
        guard enabled else { return }
        NSLog("[Share] \(message)")
    }
}

enum ArxivShareURL {
    // Accept both new-style and older arXiv identifiers.
    private static let newStylePattern = #"\b\d{4}\.\d{4,5}(v\d+)?\b"#
    private static let oldStylePattern = #"\b[a-z-]+(\.[A-Z]{2})?/\d{7}(v\d+)?\b"#

    static func canonicalAbsURL(from maybeURL: URL?) -> URL? {
        guard let url = maybeURL else { return nil }
        if url.isFileURL { return nil }
        if let canonical = canonicalAbsURL(fromArxivHostURL: url) { return canonical }
        if let id = extractArxivIdentifier(from: url.absoluteString) {
            return URL(string: "https://arxiv.org/abs/\(id)")
        }
        return nil
    }

    static func canonicalAbsURL(from maybeString: String?) -> URL? {
        guard let raw = maybeString?.trimmingCharacters(in: .whitespacesAndNewlines), !raw.isEmpty else { return nil }
        if let url = URL(string: raw), let canonical = canonicalAbsURL(from: url) {
            return canonical
        }
        if let id = extractArxivIdentifier(from: raw) {
            return URL(string: "https://arxiv.org/abs/\(id)")
        }
        return nil
    }

    private static func canonicalAbsURL(fromArxivHostURL url: URL) -> URL? {
        guard let comps = URLComponents(url: url, resolvingAgainstBaseURL: false),
              let host = comps.host?.lowercased(), host.hasSuffix("arxiv.org") else {
            return nil
        }

        let path = comps.path
        if path.lowercased().hasPrefix("/abs/") {
            let id = String(path.dropFirst("/abs/".count)).trimmingCharacters(in: CharacterSet(charactersIn: "/"))
            guard !id.isEmpty else { return nil }
            guard let canonical = URL(string: "https://arxiv.org/abs/\(id)") else { return nil }
            return canonical
        }
        if path.lowercased().hasPrefix("/pdf/") {
            var rest = String(path.dropFirst("/pdf/".count))
            rest = rest.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
            if rest.lowercased().hasSuffix(".pdf") {
                rest = String(rest.dropLast(4))
            }
            rest = rest.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !rest.isEmpty else { return nil }
            guard isValidArxivIdentifier(rest) else { return nil }
            return URL(string: "https://arxiv.org/abs/\(rest)")
        }

        // Some arxiv.org variants embed the id elsewhere; fallback to regex extraction.
        if let id = extractArxivIdentifier(from: url.absoluteString) {
            return URL(string: "https://arxiv.org/abs/\(id)")
        }
        return nil
    }

    static func extractArxivIdentifier(from text: String) -> String? {
        let candidates = [newStylePattern, oldStylePattern]
        for pattern in candidates {
            if let re = try? NSRegularExpression(pattern: pattern, options: [.caseInsensitive]) {
                let range = NSRange(text.startIndex..<text.endIndex, in: text)
                if let match = re.firstMatch(in: text, options: [], range: range),
                   let r = Range(match.range, in: text) {
                    let id = String(text[r])
                    if isValidArxivIdentifier(id) { return id }
                }
            }
        }
        return nil
    }

    private static func isValidArxivIdentifier(_ id: String) -> Bool {
        // New-style: yymm.nnnn(n) with optional vN. Validate month range.
        if let re = try? NSRegularExpression(pattern: #"^(\d{4})\.(\d{4,5})(v\d+)?$"#, options: []) {
            let s = id.trimmingCharacters(in: .whitespacesAndNewlines)
            let range = NSRange(s.startIndex..<s.endIndex, in: s)
            if let m = re.firstMatch(in: s, options: [], range: range), m.numberOfRanges >= 3,
               let yymmRange = Range(m.range(at: 1), in: s) {
                let yymm = String(s[yymmRange])
                if yymm.count == 4 {
                    let mmStr = String(yymm.suffix(2))
                    if let mm = Int(mmStr), (1...12).contains(mm) {
                        return true
                    }
                }
            }
        }

        // Old-style: archive[.SUB]/yymmnnn with optional vN.
        if let re = try? NSRegularExpression(pattern: #"^[a-z-]+(\.[A-Z]{2})?/\d{7}(v\d+)?$"#, options: [.caseInsensitive]) {
            let s = id.trimmingCharacters(in: .whitespacesAndNewlines)
            let range = NSRange(s.startIndex..<s.endIndex, in: s)
            return (re.firstMatch(in: s, options: [], range: range) != nil)
        }
        return false
    }
}

struct EmailTemplateContext {
    let title: String
    let url: String
    let recipientName: String
    let recipientEmail: String
    let appName: String
}

func renderEmailTemplate(_ template: String, context: EmailTemplateContext) -> String {
    guard !template.isEmpty else { return template }
    var out = template
    let replacements: [(String, String)] = [
        ("{{title}}", context.title),
        ("{{url}}", context.url),
        ("{{recipientName}}", context.recipientName),
        ("{{recipientEmail}}", context.recipientEmail),
        ("{{appName}}", context.appName)
    ]
    for (token, value) in replacements {
        out = out.replacingOccurrences(of: token, with: value)
    }
    return out
}

func buildMailtoURL(toAddress: String?, subject: String, body: String) -> URL? {
    var comps = URLComponents()
    comps.scheme = "mailto"
    let toTrimmed = (toAddress ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
    comps.path = toTrimmed
    comps.queryItems = [
        URLQueryItem(name: "subject", value: subject),
        URLQueryItem(name: "body", value: body)
    ]
    return comps.url
}

func systemDefaultMailtoBundleID() -> String? {
    guard let raw = LSCopyDefaultHandlerForURLScheme("mailto" as CFString)?.takeRetainedValue() else { return nil }
    let trimmed = (raw as String).trimmingCharacters(in: .whitespacesAndNewlines)
    return trimmed.isEmpty ? nil : trimmed
}

func openMailtoURL(_ url: URL, bundleID: String?) {
    let target = (bundleID ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
    if !target.isEmpty,
       let appURL = NSWorkspace.shared.urlForApplication(withBundleIdentifier: target) {
        if #available(macOS 10.15, *) {
            let config = NSWorkspace.OpenConfiguration()
            config.activates = true
            NSWorkspace.shared.open([url], withApplicationAt: appURL, configuration: config, completionHandler: nil)
        } else {
            _ = try? NSWorkspace.shared.open([url], withApplicationAt: appURL, options: [], configuration: [:])
        }
        return
    }
    NSWorkspace.shared.open(url)
}

enum MailShareDiagnostics {
    static let forceAppleScript: Bool = (ProcessInfo.processInfo.environment["ARXIV_SHARE_FORCE_APPLESCRIPT"] == "1")

    static func log(_ message: String) {
        ArxivShareDebug.log(message)
    }
}

func mailAppRunning() -> NSRunningApplication? {
    NSRunningApplication.runningApplications(withBundleIdentifier: "com.apple.mail").first
}

@available(macOS 10.15, *)
func ensureMailLaunchedForShare(activates: Bool, completion: (() -> Void)? = nil) {
    let bundleID = "com.apple.mail"
    if mailAppRunning() != nil {
        completion?()
        return
    }
    guard let mailURL = NSWorkspace.shared.urlForApplication(withBundleIdentifier: bundleID) else {
        completion?()
        return
    }
    let config = NSWorkspace.OpenConfiguration()
    config.activates = activates
    NSWorkspace.shared.openApplication(at: mailURL, configuration: config) { _, _ in
        completion?()
    }
}

func activateMailAppForShare() {
    let bundleID = "com.apple.mail"
    if let running = NSRunningApplication.runningApplications(withBundleIdentifier: bundleID).first {
        // Avoid `.activateAllWindows` which can un-minimize the viewer and cause visible flicker.
        // We prefer an explicit one-shot AppleScript activation+minimize sequence after composing.
        running.activate(options: [])
        return
    }

    guard let mailURL = NSWorkspace.shared.urlForApplication(withBundleIdentifier: bundleID) else {
        return
    }

    if #available(macOS 10.15, *) {
        let config = NSWorkspace.OpenConfiguration()
        config.activates = true
        NSWorkspace.shared.openApplication(at: mailURL, configuration: config) { app, _ in
            app?.activate(options: [])
        }
    } else {
        // Best-effort fallback for older systems.
        NSWorkspace.shared.open(mailURL)
    }
}

func mailActivateAndMinimizeViewerOnceAppleScript(subject: String) -> String {
    // One-shot stabilization script:
    // - activates Mail (to guarantee the compose window is visible)
    // - waits (briefly) so the compose window exists (first press can be slow)
    // - minimizes all Mail windows except the compose window ("New Message" / subject)
    let subj = appleScriptStringLiteral(subject)
    return """
    use framework \"Foundation\"
    use scripting additions

    tell application \"Mail\"
        if it is not running then
            launch
        end if
        activate
        
        -- Wait for the compose window to exist. On first use, NSSharingService may take
        -- a while to create/show the "New Message" window, and minimizing too early is a no-op.
        set composeWin to missing value
        set deadline to ((current application's NSDate's |date|()) as date) + 2.0
        repeat while composeWin is missing value and ((current application's NSDate's |date|()) as date) < deadline
            try
                set composeWin to first window whose name contains \"New Message\"
            end try
            if composeWin is missing value then
                try
                    set composeWin to first window whose name contains \(subj)
                end try
            end if
            if composeWin is missing value then
                delay 0.05
            end if
        end repeat

        repeat with w in windows
            if composeWin is not missing value and w is not composeWin then
                try
                    if miniaturized of w is false then set miniaturized of w to true
                end try
            end if
        end repeat

        if composeWin is not missing value then
            try
                set miniaturized of composeWin to false
                set index of composeWin to 1
            end try
        end if
    end tell
    """
}

func mailShareBody(recipientName: String?, arxivAbsURL: String) -> String {
    let trimmed = (recipientName ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
    let name = trimmed.isEmpty ? "there" : trimmed
    // Requirement: exactly
    // Hey [recipient],
    // [arxiv link]
    // (with two line breaks)
    return "Hey \(name),\n\n\(arxivAbsURL)"
}

func appleScriptStringLiteral(_ s: String) -> String {
    // AppleScript string escaping: backslash, quote, and newlines.
    var out = s
    out = out.replacingOccurrences(of: "\\", with: "\\\\")
    out = out.replacingOccurrences(of: "\"", with: "\\\"")
    out = out.replacingOccurrences(of: "\r\n", with: "\n")
    out = out.replacingOccurrences(of: "\r", with: "\n")
    out = out.replacingOccurrences(of: "\n", with: "\\n")
    return "\"\(out)\""
}

func appleScriptPOSIXFile(_ url: URL) -> String {
    "POSIX file \(appleScriptStringLiteral(url.path))"
}

func runAppleScriptAsync(_ source: String, label: String) {
    DispatchQueue.global(qos: .userInitiated).async {
        let start = monotonicNow()
        var errorDict: NSDictionary?
        let script = NSAppleScript(source: source)
        let result = script?.executeAndReturnError(&errorDict)
        let elapsedMs = Int(((monotonicNow() - start) * 1000.0).rounded())
        if let errorDict {
            MailShareDiagnostics.log("AppleScript(\(label)) error ms=\(elapsedMs) err=\(errorDict)")
        } else {
            _ = result
            MailShareDiagnostics.log("AppleScript(\(label)) ok ms=\(elapsedMs)")
        }
    }
}

func mailComposeAppleScript(subject: String,
                                    body: String,
                                    toAddress: String?,
                                    fromAddress: String?,
                                    attachments: [URL] = []) -> String {
    let subj = appleScriptStringLiteral(subject)
    let content = appleScriptStringLiteral(body + "\n")
    let toAddr = appleScriptStringLiteral((toAddress ?? "").trimmingCharacters(in: .whitespacesAndNewlines))
    let fromAddr = appleScriptStringLiteral((fromAddress ?? "").trimmingCharacters(in: .whitespacesAndNewlines))
    let attachmentList = attachments.map { appleScriptPOSIXFile($0) }.joined(separator: ", ")
    let attachmentScript: String = attachments.isEmpty ? "" : """
        repeat with f in {\(attachmentList)}
            try
                make new attachment with properties {file name:f} at after the last paragraph of newMessage
            end try
        end repeat
"""
    return """
    tell application \"Mail\"
        if it is not running then
            launch
        end if
        activate
        set newMessage to make new outgoing message with properties {subject:\(subj), content:\(content), visible:true}
        if \(fromAddr) is not \"\" then
            try
                set sender of newMessage to \(fromAddr)
            end try
        end if
        if \(toAddr) is not \"\" then
            try
                make new to recipient at end of to recipients of newMessage with properties {address:\(toAddr)}
            end try
        end if
        \(attachmentScript)
        open newMessage
        delay 0.05
        -- IMPORTANT: Mail may keep a viewer window frontmost even after creating a new message.
        -- Heuristic: identify the compose window by title ("New Message" or subject substring).
        set composeWin to missing value
        try
            set composeWin to first window whose name contains "New Message"
        end try
        if composeWin is missing value then
            try
                set composeWin to first window whose name contains \(subj)
            end try
        end if
        if composeWin is missing value then
            try
                set composeWin to front window
            end try
        end if
        repeat with w in windows
            if w is not composeWin then
                try
                    set miniaturized of w to true
                end try
            end if
        end repeat
        try
            set miniaturized of composeWin to false
            set index of composeWin to 1
        end try
    end tell
    """
}

func mailMinimizeNonFrontWindowsAppleScript() -> String {
    return """
    tell application \"Mail\"
        if it is not running then return
        try
            -- Prefer keeping a compose window visible if one exists.
            set keepWin to missing value
            try
                set keepWin to first window whose name contains \"New Message\"
            end try
            if keepWin is missing value then set keepWin to front window
            repeat with w in windows
                if w is not keepWin then
                    try
                        set miniaturized of w to true
                    end try
                end if
            end repeat
            try
                set miniaturized of keepWin to false
                set index of keepWin to 1
            end try
        end try
    end tell
    """
}

func runShareSelfTestIfEnabled() {
    guard ProcessInfo.processInfo.environment["ARXIV_SHARE_SELF_TEST"] == "1" else { return }

    // This self-test must not open Mail or invoke sharing; it only validates string generation and script syntax.
    let recipientName = ProcessInfo.processInfo.environment["ARXIV_SHARE_TEST_RECIPIENT_NAME"]
    let url = ProcessInfo.processInfo.environment["ARXIV_SHARE_TEST_URL"] ?? "https://arxiv.org/abs/1234.56789"
    let expectedRecipient = (recipientName ?? "").trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? "there" : recipientName!.trimmingCharacters(in: .whitespacesAndNewlines)
    let expectedBody = "Hey \(expectedRecipient),\n\n\(url)"
    let actualBody = mailShareBody(recipientName: recipientName, arxivAbsURL: url)

    var failures = 0
    if actualBody != expectedBody {
        failures += 1
        MailShareDiagnostics.log("self_test_body_mismatch expected=\(expectedBody.debugDescription) actual=\(actualBody.debugDescription)")
    } else {
        MailShareDiagnostics.log("self_test_body_ok")
    }

    let hasComposeService = (NSSharingService(named: .composeEmail) != nil)
    MailShareDiagnostics.log("self_test_sharing_service_available=\(hasComposeService)")

    // Compile (do not execute) the AppleScript fallback to catch syntax errors early.
    let scriptSource = mailComposeAppleScript(subject: "arXiv paper", body: actualBody, toAddress: nil, fromAddress: nil)
    let script = NSAppleScript(source: scriptSource)
    var compileError: NSDictionary?
    let compiledOk = (script?.compileAndReturnError(&compileError) ?? false)
    if !compiledOk {
        failures += 1
        MailShareDiagnostics.log("self_test_applescript_compile_error err=\(compileError ?? [:])")
    } else {
        MailShareDiagnostics.log("self_test_applescript_compile_ok")
    }

    MailShareDiagnostics.log("self_test_done failures=\(failures)")
    // Exit deterministically so this can be used as a launch-check style harness.
    launchExit(failures == 0 ? 0 : 2, reason: "share_self_test failures=\(failures)")
}

struct Payload {
    let papers: [Paper]
    let keywords: [String]
    let recipientName: String?
    let recipientEmail: String?
    let messageCount: Int
    let latestMessageDate: Date?
}

struct PaperKey: Hashable {
    let index: Int
    let url: String
}

extension Paper {
    var key: PaperKey { PaperKey(index: index, url: url) }

    func withIndex(_ newIndex: Int) -> Paper {
        Paper(index: newIndex,
              title: title,
              authors: authors,
              categories: categories,
              dateLine: dateLine,
              url: url,
              comments: comments,
              abstractText: abstractText,
              receivedAt: receivedAt)
    }

    var stableKey: String {
        if let canonical = ArxivShareURL.canonicalAbsURL(from: url) {
            return canonical.absoluteString.lowercased()
        }
        let trimmed = url.trimmingCharacters(in: .whitespacesAndNewlines)
        if !trimmed.isEmpty { return trimmed.lowercased() }
        let titleKey = title.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let authorKey = authors.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return "\(titleKey)|\(authorKey)"
    }
}

final class PublicationStore {
    private(set) var all: [Paper] = []
    private(set) var filtered: [Paper] = []

    func setAll(_ papers: [Paper]) {
        all = papers
        filtered = papers
    }

    func setFiltered(_ papers: [Paper]) {
        filtered = papers
    }
}

// Maps filtered-list indices to visible “pages”.
//
// Pagination mapping contract:
// - Pages are computed greedily to fit within the available height for the left list.
// - Page boundaries are stable for a given available height + wrap width because they depend only on measured row heights.
// - Table rows (header + page slice) always map back to exactly one filtered index via `globalIndex(forTableRow:)`.
struct Paginator {
    private(set) var pageRanges: [Range<Int>] = []

    var pageCount: Int { pageRanges.count }

    func range(forPage pageIndex: Int) -> Range<Int> {
        guard !pageRanges.isEmpty else { return 0..<0 }
        let p = max(0, min(pageRanges.count - 1, pageIndex))
        return pageRanges[p]
    }

    func pageIndex(containingGlobalFilteredIndex index: Int) -> Int? {
        guard index >= 0 else { return nil }
        for (i, r) in pageRanges.enumerated() where r.contains(index) { return i }
        return nil
    }

    mutating func recompute(itemCount: Int,
                            availableHeight: CGFloat,
                            minTopBottomInset: CGFloat,
                            headerRowHeight: CGFloat,
                            rowHeightForFilteredIndex: (Int) -> CGFloat) {
        pageRanges.removeAll(keepingCapacity: true)
        guard itemCount > 0 else { return }

        // Account for symmetric padding inside the scroll view so we never overflow the visible card.
        let contentMax = max(0, availableHeight - (2 * minTopBottomInset))
        guard contentMax > 1 else {
            pageRanges = [0..<min(1, itemCount)]
            return
        }

        var start = 0
        while start < itemCount {
            var used = headerRowHeight
            var end = start

            while end < itemCount {
                let rh = max(1, rowHeightForFilteredIndex(end))
                if end == start {
                    used += rh
                    end += 1
                    if used > contentMax {
                        // Always include at least one row per page, even if it is taller than the viewport.
                        break
                    }
                } else {
                    if used + rh <= contentMax {
                        used += rh
                        end += 1
                    } else {
                        break
                    }
                }
            }

            if end <= start { end = min(itemCount, start + 1) }
            pageRanges.append(start..<end)
            start = end
        }
    }
}

struct SearchSuggestion: Equatable {
    let paperKey: PaperKey
    let allIndex: Int
    let title: String
    let subtitle: String
    let score: Double
}

enum MenuItemKind: Equatable {
    case summary
    case separator
    case page
    case action
}

enum MenuAction: Equatable {
    case page(Int)
    case annotationColor(Int)
    case annotationEditText
    case annotationConvertStyle(AnnotationMarkupStyle)
    case annotationEditPage
    case annotationDelete
}

struct MenuItem {
    let kind: MenuItemKind
    let title: String
    let isEnabled: Bool
    let isChecked: Bool
    let action: MenuAction?
    let swatchColor: NSColor?

    var isSelectable: Bool {
        isEnabled && kind != .separator
    }
}

final class SearchIndex {
    private struct Doc {
        let key: PaperKey
        let allIndex: Int
        let title: String
        let subtitle: String
        let haystack: String
    }

    private let lock = NSLock()
    private var docs: [Doc] = []

    func rebuild(from all: [Paper]) {
        let nextDocs = all.enumerated().map { (i, p) in
            let title = decodeTeXAccents(p.title).replacingOccurrences(of: "\n", with: " ")
            let authorYear = decodeTeXAccents(leftAuthorYearText(paper: p)).replacingOccurrences(of: "\n", with: " ")
            let cats = decodeTeXAccents(stripLeadingLabel(p.categories, label: "Categories")).replacingOccurrences(of: "\n", with: " ")
            let subtitle = authorYear.isEmpty ? cats : authorYear
            let abs = decodeTeXAccents(p.abstractText).replacingOccurrences(of: "\n", with: " ")
            let hay = "\(title) \(authorYear) \(cats) \(abs)".lowercased()
            return Doc(key: p.key, allIndex: i, title: title, subtitle: subtitle, haystack: hay)
        }
        lock.lock()
        docs = nextDocs
        lock.unlock()
    }

    func suggest(query raw: String, maxResults: Int) -> [SearchSuggestion] {
        let q = raw.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !q.isEmpty else { return [] }

        // Simple Safari-like scoring:
        // - Prefer title prefix, then title contains, then other-field contains.
        // - Earlier matches rank higher; shorter titles get a small boost.
        var matches: [SearchSuggestion] = []
        matches.reserveCapacity(min(maxResults, 12))

        let snapshot: [Doc]
        lock.lock()
        snapshot = docs
        lock.unlock()

        for d in snapshot {
            guard let range = d.haystack.range(of: q) else { continue }
            let pos = d.haystack.distance(from: d.haystack.startIndex, to: range.lowerBound)

            let titleLower = d.title.lowercased()
            let titlePos = titleLower.range(of: q).map { titleLower.distance(from: titleLower.startIndex, to: $0.lowerBound) }
            let titlePrefixBoost: Double = titleLower.hasPrefix(q) ? 1000 : 0
            let titleContainsBoost: Double = titlePos != nil ? 250 : 0
            let positionPenalty: Double = Double(min(600, pos))
            let lengthBoost: Double = Double(max(0, 90 - min(90, d.title.count))) * 0.15

            let score = titlePrefixBoost + titleContainsBoost + lengthBoost - positionPenalty
            matches.append(SearchSuggestion(paperKey: d.key,
                                           allIndex: d.allIndex,
                                           title: d.title,
                                           subtitle: d.subtitle,
                                           score: score))
        }

        matches.sort { a, b in
            if a.score != b.score { return a.score > b.score }
            if a.title.count != b.title.count { return a.title.count < b.title.count }
            return a.allIndex < b.allIndex
        }

        if matches.count > maxResults { matches.removeLast(matches.count - maxResults) }
        return matches
    }
}


// MARK: - Utilities

func monotonicNow() -> CFTimeInterval {
    CACurrentMediaTime()
}

func perfLog(_ message: String) {
    NSLog("[Perf] \(message)")
}

func sha256Hex(_ string: String) -> String {
    let data = Data(string.utf8)
    let digest = SHA256.hash(data: data)
    return digest.map { String(format: "%02x", $0) }.joined()
}

func reportingHash(_ string: String) -> String {
    let digest = sha256Hex(string)
    return "hash:\(digest.prefix(16))"
}

func reportingDocumentID(for url: URL) -> String {
    reportingHash(url.absoluteString)
}

func reportingDocumentID(for doc: PDFDocument) -> String {
    if let url = doc.documentURL {
        return reportingDocumentID(for: url)
    }
    let token = String(describing: ObjectIdentifier(doc).hashValue)
    return reportingHash("doc:\(token)")
}

func pdfMimeTypeLooksValid(_ mimeType: String?) -> Bool {
    guard let raw = mimeType?.lowercased(), !raw.isEmpty else { return false }
    if raw.contains("pdf") { return true }
    return raw == "application/octet-stream"
}

func dataHasPDFHeader(_ data: Data) -> Bool {
    let prefix = data.prefix(5)
    return prefix == Data("%PDF-".utf8)
}

func fileHasPDFHeader(_ url: URL) -> Bool {
    guard let handle = try? FileHandle(forReadingFrom: url) else { return false }
    defer { try? handle.close() }
    let data = handle.readData(ofLength: 5)
    return dataHasPDFHeader(data)
}

func stripLeadingLabel(_ value: String, label: String) -> String {
    let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
    let lower = trimmed.lowercased()
    let prefix = (label.lowercased() + ":")
    if lower.hasPrefix(prefix) {
        return trimmed.dropFirst(prefix.count).trimmingCharacters(in: .whitespacesAndNewlines)
    }
    return trimmed
}

func regexReplace(_ s: String,
                          _ pattern: String,
                          _ repl: String,
                          options: NSRegularExpression.Options = []) -> String {
    guard let re = try? NSRegularExpression(pattern: pattern, options: options) else { return s }
    let range = NSRange(location: 0, length: (s as NSString).length)
    return re.stringByReplacingMatches(in: s, options: [], range: range, withTemplate: repl)
}

func htmlEscape(_ s: String) -> String {
    var out = s
    out = out.replacingOccurrences(of: "&", with: "&amp;")
    out = out.replacingOccurrences(of: "<", with: "&lt;")
    out = out.replacingOccurrences(of: ">", with: "&gt;")
    out = out.replacingOccurrences(of: "\"", with: "&quot;")
    return out
}

func jsStringEscape(_ s: String) -> String {
    var out = s
    out = out.replacingOccurrences(of: "\\", with: "\\\\")
    out = out.replacingOccurrences(of: "\"", with: "\\\"")
    out = out.replacingOccurrences(of: "\n", with: "\\n")
    out = out.replacingOccurrences(of: "\r", with: "")
    out = out.replacingOccurrences(of: "\u{2028}", with: "\\u2028")
    out = out.replacingOccurrences(of: "\u{2029}", with: "\\u2029")
    return out
}

func cssRGBA(_ color: NSColor) -> String {
    let c = (color.usingColorSpace(.deviceRGB) ?? color)
    return String(format: "rgba(%.0f,%.0f,%.0f,%.3f)",
                  (c.redComponent * 255.0),
                  (c.greenComponent * 255.0),
                  (c.blueComponent * 255.0),
                  c.alphaComponent)
}

func hexFromColor(_ color: NSColor, includeAlpha: Bool) -> String {
    let c = (color.usingColorSpace(.deviceRGB) ?? color)
    let r = Int(round(max(0.0, min(1.0, c.redComponent)) * 255.0))
    let g = Int(round(max(0.0, min(1.0, c.greenComponent)) * 255.0))
    let b = Int(round(max(0.0, min(1.0, c.blueComponent)) * 255.0))
    if includeAlpha {
        let a = Int(round(max(0.0, min(1.0, c.alphaComponent)) * 255.0))
        return String(format: "#%02X%02X%02X%02X", r, g, b, a)
    }
    return String(format: "#%02X%02X%02X", r, g, b)
}

func colorFromHex(_ hex: String) -> NSColor? {
    let trimmed = hex.trimmingCharacters(in: .whitespacesAndNewlines)
    guard trimmed.hasPrefix("#") else { return nil }
    let hexBody = String(trimmed.dropFirst())
    guard hexBody.count == 6 || hexBody.count == 8 else { return nil }

    var value: UInt64 = 0
    guard Scanner(string: hexBody).scanHexInt64(&value) else { return nil }

    let r: CGFloat
    let g: CGFloat
    let b: CGFloat
    let a: CGFloat

    if hexBody.count == 6 {
        r = CGFloat((value >> 16) & 0xFF) / 255.0
        g = CGFloat((value >> 8) & 0xFF) / 255.0
        b = CGFloat(value & 0xFF) / 255.0
        a = 1.0
    } else {
        r = CGFloat((value >> 24) & 0xFF) / 255.0
        g = CGFloat((value >> 16) & 0xFF) / 255.0
        b = CGFloat((value >> 8) & 0xFF) / 255.0
        a = CGFloat(value & 0xFF) / 255.0
    }

    return NSColor(srgbRed: r, green: g, blue: b, alpha: a)
}

enum ThemeContrastLog {
    static let log = OSLog(subsystem: APP_LOG_SUBSYSTEM, category: "theme-contrast")

    static func error(_ message: String) {
        os_log("%{public}@", log: log, type: .error, message)
    }
}

enum ThemeContrast {
    static let wcagNormalTextContrast: CGFloat = 4.5
    static let wcagLargeTextContrast: CGFloat = 3.0
    static let iconMinimumContrast: CGFloat = 4.5

    static func relativeLuminance(_ color: NSColor) -> CGFloat {
        let c = (color.usingColorSpace(.deviceRGB) ?? color)
        func channel(_ v: CGFloat) -> CGFloat {
            if v <= 0.03928 { return v / 12.92 }
            return CGFloat(pow(Double((v + 0.055) / 1.055), 2.4))
        }
        let r = channel(c.redComponent)
        let g = channel(c.greenComponent)
        let b = channel(c.blueComponent)
        return (0.2126 * r) + (0.7152 * g) + (0.0722 * b)
    }

    static func contrastRatio(_ foreground: NSColor, _ background: NSColor) -> CGFloat {
        let bg = resolvedOpaque(background)
        let fg = flattened(foreground, over: bg)
        let l1 = relativeLuminance(fg) + 0.05
        let l2 = relativeLuminance(bg) + 0.05
        return max(l1, l2) / min(l1, l2)
    }

    static func meetsWCAGAA(_ foreground: NSColor, _ background: NSColor, isLargeText: Bool = false) -> Bool {
        let threshold = isLargeText ? wcagLargeTextContrast : wcagNormalTextContrast
        return contrastRatio(foreground, background) >= threshold
    }

    static func bestContrastingMonochrome(on background: NSColor,
                                          minimumContrast: CGFloat = iconMinimumContrast) -> NSColor {
        let bg = resolvedOpaque(background)
        let black = NSColor.black
        let white = NSColor.white
        let blackRatio = contrastRatio(black, bg)
        let whiteRatio = contrastRatio(white, bg)
        let best = blackRatio >= whiteRatio ? black : white
        let bestRatio = max(blackRatio, whiteRatio)
        if bestRatio < minimumContrast {
            let message = String(format: "Contrast fallback: best monochrome %.2f < %.2f", bestRatio, minimumContrast)
            ThemeContrastLog.error(message)
            #if DEBUG
            assertionFailure(message)
            #endif
        }
        return best
    }

    static func ensureContrast(_ foreground: NSColor,
                               on background: NSColor,
                               minimumContrast: CGFloat,
                               context: String? = nil) -> NSColor {
        let ratio = contrastRatio(foreground, background)
        guard ratio < minimumContrast else { return foreground }
        let fallback = bestContrastingMonochrome(on: background, minimumContrast: minimumContrast)
        let label = context ?? "icon"
        let message = String(format: "Contrast violation (%@): %.2f < %.2f", label, ratio, minimumContrast)
        ThemeContrastLog.error(message)
        #if DEBUG
        assertionFailure(message)
        #endif
        return fallback
    }

    private static func resolvedOpaque(_ color: NSColor) -> NSColor {
        (color.usingColorSpace(.deviceRGB) ?? color).withAlphaComponent(1.0)
    }

    private static func flattened(_ foreground: NSColor, over background: NSColor) -> NSColor {
        let fg = (foreground.usingColorSpace(.deviceRGB) ?? foreground)
        let bg = resolvedOpaque(background)
        let alpha = max(0.0, min(1.0, fg.alphaComponent))
        if alpha <= 0.0001 { return bg }
        if alpha >= 0.999 { return fg.withAlphaComponent(1.0) }
        let fgLin = (srgbToLinear(fg.redComponent),
                     srgbToLinear(fg.greenComponent),
                     srgbToLinear(fg.blueComponent))
        let bgLin = (srgbToLinear(bg.redComponent),
                     srgbToLinear(bg.greenComponent),
                     srgbToLinear(bg.blueComponent))
        let outLin = compositeRGBLinear(sourceRGB: fgLin, sourceAlpha: alpha, destRGB: bgLin)
        return NSColor(srgbRed: linearToSrgb(outLin.0),
                       green: linearToSrgb(outLin.1),
                       blue: linearToSrgb(outLin.2),
                       alpha: 1.0)
    }
}

enum ContrastDebug {
    static let enabled: Bool = {
        ProcessInfo.processInfo.environment["ARXIV_CONTRAST_DEBUG"] == "1"
    }()

    private static let log = OSLog(subsystem: APP_LOG_SUBSYSTEM, category: "contrast.debug")
    private static let epsilon: CGFloat = 0.004
    private static var lastSearchBackground: NSColor?
    private static var lastSearchText: NSColor?

    static func recordSearchBar(background: NSColor, textColor: NSColor, context: String) {
        guard enabled else { return }
        lastSearchBackground = background
        lastSearchText = textColor
        logResolved(context: context,
                    role: .primaryText,
                    background: background,
                    foreground: textColor,
                    note: "search_bar")
    }

    static func logResolved(context: String,
                            role: ForegroundRole,
                            background: NSColor,
                            foreground: NSColor,
                            note: String = "") {
        guard enabled else { return }
        let bgHex = hexFromColor(background, includeAlpha: true)
        let fgHex = hexFromColor(foreground, includeAlpha: true)
        let ratio = ThemeContrast.contrastRatio(foreground, background)
        os_log("[ContrastResolved] ctx=%{public}@ role=%{public}@ bg=%{public}@ fg=%{public}@ ratio=%.2f %{public}@",
               log: log,
               type: .info,
               context,
               String(describing: role),
               bgHex,
               fgHex,
               ratio,
               note)
    }

    static func logApplied(context: String,
                           role: ForegroundRole?,
                           background: NSColor?,
                           foreground: NSColor,
                           note: String = "") {
        guard enabled else { return }
        let fgHex = hexFromColor(foreground, includeAlpha: true)
        let roleStr = role.map { String(describing: $0) } ?? "-"
        var bgHex = "-"
        var ratio: CGFloat = -1
        if let background {
            bgHex = hexFromColor(background, includeAlpha: true)
            ratio = ThemeContrast.contrastRatio(foreground, background)
        }
        os_log("[ContrastApplied] ctx=%{public}@ role=%{public}@ bg=%{public}@ fg=%{public}@ ratio=%.2f %{public}@",
               log: log,
               type: .info,
               context,
               roleStr,
               bgHex,
               fgHex,
               ratio,
               note)
    }

    static func assertForegroundMatchesSearch(foreground: NSColor,
                                              background: NSColor,
                                              role: ForegroundRole,
                                              context: String) -> Bool {
        guard enabled else { return true }
        guard let searchBG = lastSearchBackground,
              let searchText = lastSearchText else { return true }
        guard colorsClose(background, searchBG, epsilon: epsilon) else { return true }

        let iconRatio = ThemeContrast.contrastRatio(foreground, background)
        let textRatio = ThemeContrast.contrastRatio(searchText, searchBG)
        let iconHex = hexFromColor(foreground, includeAlpha: true)
        let textHex = hexFromColor(searchText, includeAlpha: true)
        let bgHex = hexFromColor(background, includeAlpha: true)

        let matches = colorsClose(foreground, searchText, epsilon: epsilon)
        let iconContrastOK = iconRatio >= (role == .primaryText ? ThemeContrast.wcagNormalTextContrast : ThemeContrast.iconMinimumContrast)
        let textContrastOK = textRatio >= ThemeContrast.wcagNormalTextContrast

        if !matches || !iconContrastOK || !textContrastOK {
            let stack = Thread.callStackSymbols.joined(separator: "\n")
            let message = String(format: "Contrast mismatch ctx=%@ role=%@ bg=%@ fg=%@ search=%@ fgRatio=%.2f searchRatio=%.2f",
                                 context, String(describing: role), bgHex, iconHex, textHex, iconRatio, textRatio)
            os_log("%{public}@", log: log, type: .error, message)
            os_log("%{public}@", log: log, type: .error, stack)
            #if DEBUG
            assertionFailure(message)
            #endif
            return false
        }
        return true
    }

    private static func colorsClose(_ a: NSColor, _ b: NSColor, epsilon: CGFloat) -> Bool {
        colorsClose(a, b, epsilon: epsilon)
    }
}

func relativeLuminance(_ color: NSColor) -> CGFloat {
    ThemeContrast.relativeLuminance(color)
}

func contrastRatio(_ a: NSColor, _ b: NSColor) -> CGFloat {
    ThemeContrast.contrastRatio(a, b)
}

func blend(_ a: NSColor, _ b: NSColor, t: CGFloat) -> NSColor {
    let ca = (a.usingColorSpace(.deviceRGB) ?? a)
    let cb = (b.usingColorSpace(.deviceRGB) ?? b)
    let tt = max(0.0, min(1.0, t))
    let r = ca.redComponent + (cb.redComponent - ca.redComponent) * tt
    let g = ca.greenComponent + (cb.greenComponent - ca.greenComponent) * tt
    let b = ca.blueComponent + (cb.blueComponent - ca.blueComponent) * tt
    let aComp = ca.alphaComponent + (cb.alphaComponent - ca.alphaComponent) * tt
    return NSColor(srgbRed: r, green: g, blue: b, alpha: aComp)
}

func flattenedSystemAccentColor(base: NSColor, alpha: CGFloat) -> NSColor {
    let baseRGB = (base.usingColorSpace(.deviceRGB) ?? base).withAlphaComponent(1.0)
    let accent = resolvedAppAccentDisplayColor()
    let accentRGB = (accent.usingColorSpace(.deviceRGB) ?? accent).withAlphaComponent(1.0)
    let t = max(0.0, min(1.0, alpha))
    let blended = blend(baseRGB, accentRGB, t: t)
    return blended.withAlphaComponent(1.0)
}

func adjustedForContrast(_ color: NSColor, background: NSColor, target: CGFloat) -> NSColor {
    var candidate = color
    var ratio = contrastRatio(candidate, background)
    guard ratio < target else { return candidate }

    let toward = relativeLuminance(background) > 0.5 ? NSColor.black : NSColor.white
    var t: CGFloat = 0.0
    while ratio < target && t < 0.85 {
        t += 0.08
        candidate = blend(color, toward, t: t)
        ratio = contrastRatio(candidate, background)
    }
    return candidate
}

func adjustedTintForBackgroundContrast(base: NSColor,
                                              tint: NSColor,
                                              target: CGFloat,
                                              maxAlpha: CGFloat) -> NSColor {
    let baseRGB = (base.usingColorSpace(.deviceRGB) ?? base).withAlphaComponent(1.0)
    let tintRGB = (tint.usingColorSpace(.deviceRGB) ?? tint)
    let maxA = max(0.0, min(1.0, maxAlpha))
    var alpha = max(0.0, min(maxA, tintRGB.alphaComponent))
    var candidate = tintRGB.withAlphaComponent(alpha)
    var blended = effectiveBackgroundColor(base: baseRGB, tint: candidate)
    var ratio = contrastRatio(blended, baseRGB)
    if ratio >= target { return candidate }

    while ratio < target && alpha < maxA {
        alpha = min(maxA, alpha + 0.04)
        candidate = tintRGB.withAlphaComponent(alpha)
        blended = effectiveBackgroundColor(base: baseRGB, tint: candidate)
        ratio = contrastRatio(blended, baseRGB)
    }
    if ratio >= target { return candidate }

    let toward = relativeLuminance(baseRGB) > 0.5 ? NSColor.black : NSColor.white
    var t: CGFloat = 0.0
    while ratio < target && t < 0.85 {
        t += 0.08
        let adjusted = blend(tintRGB.withAlphaComponent(1.0), toward, t: t)
        candidate = adjusted.withAlphaComponent(alpha)
        blended = effectiveBackgroundColor(base: baseRGB, tint: candidate)
        ratio = contrastRatio(blended, baseRGB)
    }
    return candidate
}

func ensureMinimumContrast(_ color: NSColor,
                                   backgrounds: [NSColor],
                                   target: CGFloat) -> NSColor {
    let resolvedBackgrounds = backgrounds.map { ($0.usingColorSpace(.deviceRGB) ?? $0).withAlphaComponent(1.0) }
    guard let worst = resolvedBackgrounds.min(by: { contrastRatio(color, $0) < contrastRatio(color, $1) }) else {
        return color
    }
    var candidate = color
    if contrastRatio(candidate, worst) < target {
        candidate = adjustedForContrast(candidate, background: worst, target: target)
    }
    if contrastRatio(candidate, worst) >= target {
        return candidate
    }
    let black = NSColor.black
    let white = NSColor.white
    let blackWorst = resolvedBackgrounds.map { contrastRatio(black, $0) }.min() ?? 0
    let whiteWorst = resolvedBackgrounds.map { contrastRatio(white, $0) }.min() ?? 0
    return blackWorst >= whiteWorst ? black : white
}

func srgbToLinear(_ v: CGFloat) -> CGFloat {
    let x = max(0.0, min(1.0, v))
    if x <= 0.04045 { return x / 12.92 }
    return CGFloat(pow(Double((x + 0.055) / 1.055), 2.4))
}

func linearToSrgb(_ v: CGFloat) -> CGFloat {
    let x = max(0.0, min(1.0, v))
    if x <= 0.0031308 { return x * 12.92 }
    return CGFloat(1.055 * pow(Double(x), 1.0 / 2.4) - 0.055)
}

func compositeRGBLinear(sourceRGB: (CGFloat, CGFloat, CGFloat),
                               sourceAlpha: CGFloat,
                               destRGB: (CGFloat, CGFloat, CGFloat)) -> (CGFloat, CGFloat, CGFloat) {
    let a = max(0.0, min(1.0, sourceAlpha))
    let r = a * sourceRGB.0 + (1.0 - a) * destRGB.0
    let g = a * sourceRGB.1 + (1.0 - a) * destRGB.1
    let b = a * sourceRGB.2 + (1.0 - a) * destRGB.2
    return (r, g, b)
}

func inverseCompositeRGBLinear(targetRGB: (CGFloat, CGFloat, CGFloat),
                                      underRGB: (CGFloat, CGFloat, CGFloat),
                                      sourceAlpha: CGFloat) -> (CGFloat, CGFloat, CGFloat) {
    // Solve C_tint_needed = (C_target - (1 - a) * C_under) / a per channel.
    let a = max(0.0001, min(1.0, sourceAlpha))
    let r = (targetRGB.0 - (1.0 - a) * underRGB.0) / a
    let g = (targetRGB.1 - (1.0 - a) * underRGB.1) / a
    let b = (targetRGB.2 - (1.0 - a) * underRGB.2) / a
    return (max(0.0, min(1.0, r)), max(0.0, min(1.0, g)), max(0.0, min(1.0, b)))
}

func averageColor(from image: NSImage, sampleSize: Int = 16) -> NSColor? {
    guard let cgImage = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else { return nil }
    let width = max(1, sampleSize)
    let height = max(1, sampleSize)
    let bytesPerPixel = 4
    let bytesPerRow = width * bytesPerPixel
    var data = [UInt8](repeating: 0, count: width * height * bytesPerPixel)
    let space = CGColorSpaceCreateDeviceRGB()
    guard let ctx = CGContext(data: &data,
                              width: width,
                              height: height,
                              bitsPerComponent: 8,
                              bytesPerRow: bytesPerRow,
                              space: space,
                              bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else {
        return nil
    }
    ctx.interpolationQuality = .medium
    ctx.draw(cgImage, in: CGRect(x: 0, y: 0, width: width, height: height))

    var r: CGFloat = 0
    var g: CGFloat = 0
    var b: CGFloat = 0
    var aSum: CGFloat = 0

    for i in stride(from: 0, to: data.count, by: 4) {
        let a = CGFloat(data[i + 3]) / 255.0
        if a <= 0 { continue }
        r += (CGFloat(data[i]) / 255.0) * a
        g += (CGFloat(data[i + 1]) / 255.0) * a
        b += (CGFloat(data[i + 2]) / 255.0) * a
        aSum += a
    }

    guard aSum > 0 else { return nil }
    return NSColor(srgbRed: r / aSum, green: g / aSum, blue: b / aSum, alpha: 1.0)
}

func averageLuminance(from image: NSImage, sampleSize: Int = 16) -> CGFloat? {
    guard let avg = averageColor(from: image, sampleSize: sampleSize) else { return nil }
    return relativeLuminance(avg)
}

func rgbToHSV(_ r: CGFloat, _ g: CGFloat, _ b: CGFloat) -> (h: CGFloat, s: CGFloat, v: CGFloat) {
    let maxV = max(r, max(g, b))
    let minV = min(r, min(g, b))
    let delta = maxV - minV
    let v = maxV
    let s: CGFloat = (maxV <= 0.00001) ? 0.0 : (delta / maxV)
    var h: CGFloat = 0.0
    if delta > 0.00001 {
        if maxV == r {
            h = (g - b) / delta
        } else if maxV == g {
            h = 2.0 + (b - r) / delta
        } else {
            h = 4.0 + (r - g) / delta
        }
        h /= 6.0
        if h < 0 { h += 1.0 }
        if h >= 1.0 { h -= 1.0 }
    }
    return (h, s, v)
}

func dominantHueColor(from image: NSImage, sampleSize: Int = 72, hueBins: Int = 36) -> NSColor? {
    // Dominant-hue estimate (for titlebar tinting): downsample, hue-histogram (weighted), then average RGB of the winning bin.
    guard hueBins > 0 else { return nil }
    guard let cgImage = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else { return nil }

    let width = max(1, sampleSize)
    let height = max(1, sampleSize)
    let bytesPerPixel = 4
    let bytesPerRow = width * bytesPerPixel
    var data = [UInt8](repeating: 0, count: width * height * bytesPerPixel)
    let space = CGColorSpaceCreateDeviceRGB()
    guard let ctx = CGContext(data: &data,
                              width: width,
                              height: height,
                              bitsPerComponent: 8,
                              bytesPerRow: bytesPerRow,
                              space: space,
                              bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else {
        return nil
    }
    ctx.interpolationQuality = .medium
    ctx.draw(cgImage, in: CGRect(x: 0, y: 0, width: width, height: height))

    var binWeights = [Double](repeating: 0.0, count: hueBins)
    var rSums = [Double](repeating: 0.0, count: hueBins)
    var gSums = [Double](repeating: 0.0, count: hueBins)
    var bSums = [Double](repeating: 0.0, count: hueBins)

    for i in stride(from: 0, to: data.count, by: 4) {
        let a = CGFloat(data[i + 3]) / 255.0
        if a < 0.05 { continue }

        let r = CGFloat(data[i]) / 255.0
        let g = CGFloat(data[i + 1]) / 255.0
        let b = CGFloat(data[i + 2]) / 255.0
        let hsv = rgbToHSV(r, g, b)

        // Ignore near-grayscale pixels where hue is unstable.
        if hsv.s < 0.08 || hsv.v < 0.05 { continue }

        let hue = max(0.0, min(0.999999, hsv.h))
        let bin = max(0, min(hueBins - 1, Int(hue * CGFloat(hueBins))))
        let weight = Double(a * hsv.s * (0.25 + 0.75 * hsv.v))

        binWeights[bin] += weight
        rSums[bin] += Double(r) * weight
        gSums[bin] += Double(g) * weight
        bSums[bin] += Double(b) * weight
    }

    guard let maxIndex = binWeights.enumerated().max(by: { $0.element < $1.element })?.offset else { return nil }
    let w = binWeights[maxIndex]
    if w <= 0.00001 {
        // Fall back to average color when there isn't a meaningful dominant hue (e.g., grayscale wallpaper).
        return averageColor(from: image, sampleSize: max(12, sampleSize / 6))
    }
    let rr = CGFloat(rSums[maxIndex] / w)
    let gg = CGFloat(gSums[maxIndex] / w)
    let bb = CGFloat(bSums[maxIndex] / w)
    return NSColor(srgbRed: rr, green: gg, blue: bb, alpha: 1.0)
}

struct TextPalette {
    let primary: NSColor
    let secondary: NSColor
    let muted: NSColor
    let link: NSColor
    let rule: NSColor
    let codeText: NSColor
    let codeBackground: NSColor
}

func adaptiveTextPalette(baseColor: NSColor, linkHex: String) -> TextPalette {
    let base = baseColor.usingColorSpace(.deviceRGB) ?? baseColor
    let isLight = relativeLuminance(base) > 0.55

    let primarySeed = isLight
        ? NSColor(srgbRed: 0.10, green: 0.11, blue: 0.12, alpha: 1.0)
        : NSColor(srgbRed: 0.94, green: 0.94, blue: 0.95, alpha: 1.0)
    let secondarySeed = isLight
        ? NSColor(srgbRed: 0.26, green: 0.28, blue: 0.30, alpha: 1.0)
        : NSColor(srgbRed: 0.82, green: 0.83, blue: 0.84, alpha: 1.0)
    let mutedSeed = isLight
        ? NSColor(srgbRed: 0.39, green: 0.40, blue: 0.42, alpha: 1.0)
        : NSColor(srgbRed: 0.70, green: 0.71, blue: 0.72, alpha: 1.0)
    let linkSeed = colorFromHex(linkHex)
        ?? (isLight
            ? NSColor(srgbRed: 0.17, green: 0.43, blue: 0.86, alpha: 1.0)
            : NSColor(srgbRed: 0.36, green: 0.62, blue: 0.96, alpha: 1.0))
    let ruleSeed = (isLight ? NSColor.black : NSColor.white).withAlphaComponent(isLight ? 0.14 : 0.18)
    let codeBackground = (isLight ? NSColor.black : NSColor.white).withAlphaComponent(isLight ? 0.06 : 0.10)
    let codeTextSeed = isLight
        ? NSColor(srgbRed: 0.16, green: 0.18, blue: 0.20, alpha: 1.0)
        : NSColor(srgbRed: 0.88, green: 0.89, blue: 0.90, alpha: 1.0)

    return TextPalette(
        primary: adjustedForContrast(primarySeed, background: base, target: 4.5),
        secondary: adjustedForContrast(secondarySeed, background: base, target: 3.0),
        muted: adjustedForContrast(mutedSeed, background: base, target: 2.5),
        link: adjustedForContrast(linkSeed, background: base, target: 4.5),
        rule: ruleSeed,
        codeText: adjustedForContrast(codeTextSeed, background: base, target: 4.5),
        codeBackground: codeBackground
    )
}

func loadBackgroundImage(from path: String) -> NSImage? {
    let trimmed = path.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return nil }
    var isDir: ObjCBool = false
    guard FileManager.default.fileExists(atPath: trimmed, isDirectory: &isDir), !isDir.boolValue else {
        NSLog("[Background] Image file not found: \(trimmed)")
        return nil
    }
    // Load via ImageIO so we can optionally downsample large still images to keep startup smooth.
    return loadBackgroundImage(from: trimmed, maxPixelDim: nil, preserveAnimated: true)
}

func loadBackgroundImage(from trimmedPath: String,
                                 maxPixelDim: Int?,
                                 preserveAnimated: Bool) -> NSImage? {
    let url = URL(fileURLWithPath: trimmedPath)
    guard let src = CGImageSourceCreateWithURL(url as CFURL, nil) else {
        // Fallback to NSImage for any unsupported formats.
        return NSImage(contentsOfFile: trimmedPath)
    }

    let frameCount = CGImageSourceGetCount(src)
    if preserveAnimated, frameCount > 1 {
        // Preserve animation (GIF/APNG): NSImage keeps frames; downsampling animated images robustly is non-trivial.
        return NSImage(contentsOfFile: trimmedPath)
    }

    var pixelW = 0
    var pixelH = 0
    if let props = CGImageSourceCopyPropertiesAtIndex(src, 0, nil) as? [CFString: Any] {
        pixelW = (props[kCGImagePropertyPixelWidth] as? Int) ?? 0
        pixelH = (props[kCGImagePropertyPixelHeight] as? Int) ?? 0
    }

    let maxDim = max(pixelW, pixelH)
    let requestedCap = maxPixelDim ?? maxDim
    let hardCap = max(0, BACKGROUND_IMAGE_HARD_MAX_PIXEL_DIM)
    let effectiveCap = (BACKGROUND_IMAGE_DOWNSCALE_ENABLED && hardCap > 0) ? min(requestedCap, hardCap) : maxDim

    // If the image is already within bounds (or we can't read pixel size), use the simple path.
    if maxDim <= 0 || effectiveCap <= 0 || maxDim <= effectiveCap {
        let image = NSImage(contentsOfFile: trimmedPath)
        if image == nil { NSLog("[Background] Failed to load image: \(trimmedPath)") }
        return image
    }

    let options: [CFString: Any] = [
        kCGImageSourceCreateThumbnailFromImageAlways: true,
        kCGImageSourceShouldCacheImmediately: true,
        kCGImageSourceCreateThumbnailWithTransform: true,
        kCGImageSourceThumbnailMaxPixelSize: effectiveCap
    ]

    guard let thumb = CGImageSourceCreateThumbnailAtIndex(src, 0, options as CFDictionary) else {
        return NSImage(contentsOfFile: trimmedPath)
    }

    let out = NSImage(cgImage: thumb, size: NSSize(width: thumb.width, height: thumb.height))
    if out.size.width <= 0 || out.size.height <= 0 {
        NSLog("[Background] Image has invalid size after downsample: \(trimmedPath)")
        return nil
    }
    NSLog("[Background] Downsampled \(url.lastPathComponent) maxDim=\(maxDim) -> \(effectiveCap)")
    return out
}

func recommendedBackgroundMaxPixelDim(for window: NSWindow?) -> Int? {
    // Enough pixels for crisp rendering at current backing scale, plus a small headroom for resizing.
    guard let window else { return nil }
    let scale = window.screen?.backingScaleFactor ?? NSScreen.main?.backingScaleFactor ?? 2.0
    let size = window.contentView?.bounds.size ?? window.frame.size
    let px = Int(ceil(max(size.width, size.height) * scale * 1.15))
    return max(512, px)
}

func arxivID(fromAbsURL url: String) -> String? {
    let u = stripLeadingLabel(url, label: "URL")
        .trimmingCharacters(in: .whitespacesAndNewlines)
    guard !u.isEmpty else { return nil }

    if let re = try? NSRegularExpression(pattern: #"arxiv\.org/abs/([^?#\s]+)"#, options: [.caseInsensitive]) {
        let ns = u as NSString
        let range = NSRange(location: 0, length: ns.length)
        if let m = re.firstMatch(in: u, range: range), m.numberOfRanges >= 2 {
            let id = ns.substring(with: m.range(at: 1))
            return id.trimmingCharacters(in: .whitespacesAndNewlines)
        }
    }
    return nil
}

func arxivPDFFromAbs(url: String) -> String? {
    guard let id = arxivID(fromAbsURL: url), !id.isEmpty else { return nil }
    return "https://arxiv.org/pdf/\(id).pdf"
}

// TeX accent decoding
let texAccentMap: [String: String] = [
    "\\'A":"Á","\\'a":"á","\\'E":"É","\\'e":"é","\\'I":"Í","\\'i":"í","\\'O":"Ó","\\'o":"ó","\\'U":"Ú","\\'u":"ú","\\'Y":"Ý","\\'y":"ý",
    "\\`A":"À","\\`a":"à","\\`E":"È","\\`e":"è","\\`I":"Ì","\\`i":"ì","\\`O":"Ò","\\`o":"ò","\\`U":"Ù","\\`u":"ù",
    "\\^A":"Â","\\^a":"â","\\^E":"Ê","\\^e":"ê","\\^I":"Î","\\^i":"î","\\^O":"Ô","\\^o":"ô","\\^U":"Û","\\^u":"û",
    "\\\"A":"Ä","\\\"a":"ä","\\\"E":"Ë","\\\"e":"ë","\\\"I":"Ï","\\\"i":"ï","\\\"O":"Ö","\\\"o":"ö","\\\"U":"Ü","\\\"u":"ü","\\\"Y":"Ÿ","\\\"y":"ÿ",
    "\\~A":"Ã","\\~a":"ã","\\~N":"Ñ","\\~n":"ñ","\\~O":"Õ","\\~o":"õ",
    "\\cC":"Ç","\\cc":"ç"
]

func decodeTeXAccents(_ s: String) -> String {
    var out = s
    for (k, v) in texAccentMap { out = out.replacingOccurrences(of: k, with: v) }
    out = out.replacingOccurrences(of: "\\\\'", with: "")
    out = out.replacingOccurrences(of: "\\'", with: "")
    return out
}

// Lightweight LaTeX → readable Unicode conversion for abstracts (no external deps)
let latexSymbolMap: [String: String] = [
    "\\alpha":"α","\\beta":"β","\\gamma":"γ","\\delta":"δ","\\epsilon":"ε","\\varepsilon":"ε","\\zeta":"ζ","\\eta":"η","\\theta":"θ","\\vartheta":"ϑ","\\iota":"ι","\\kappa":"κ","\\lambda":"λ","\\mu":"μ","\\nu":"ν","\\xi":"ξ","\\pi":"π","\\varpi":"ϖ","\\rho":"ρ","\\varrho":"ϱ","\\sigma":"σ","\\varsigma":"ς","\\tau":"τ","\\upsilon":"υ","\\phi":"φ","\\varphi":"ϕ","\\chi":"χ","\\psi":"ψ","\\omega":"ω",
    "\\Gamma":"Γ","\\Delta":"Δ","\\Theta":"Θ","\\Lambda":"Λ","\\Xi":"Ξ","\\Pi":"Π","\\Sigma":"Σ","\\Upsilon":"Υ","\\Phi":"Φ","\\Psi":"Ψ","\\Omega":"Ω",
    "\\mathbb{R}":"ℝ","\\mathbb{Z}":"ℤ","\\mathbb{Q}":"ℚ","\\mathbb{N}":"ℕ","\\mathbb{C}":"ℂ",
    "\\leq":"≤","\\geq":"≥","\\neq":"≠","\\pm":"±","\\mp":"∓","\\times":"×","\\cdot":"·","\\infty":"∞","\\approx":"≈","\\propto":"∝","\\sim":"∼","\\to":"→","\\rightarrow":"→","\\leftarrow":"←","\\Rightarrow":"⇒","\\Leftarrow":"⇐","\\leftrightarrow":"↔","\\mapsto":"↦","\\partial":"∂","\\nabla":"∇","\\int":"∫","\\sum":"∑","\\prod":"∏","\\exists":"∃","\\forall":"∀","\\in":"∈","\\notin":"∉","\\cup":"∪","\\cap":"∩","\\subset":"⊂","\\subseteq":"⊆","\\supset":"⊃","\\supseteq":"⊇","\\setminus":"∖","\\oplus":"⊕","\\otimes":"⊗","\\perp":"⊥","\\angle":"∠","\\deg":"°"
]

let superscriptMap: [Character: Character] = [
    "0":"⁰","1":"¹","2":"²","3":"³","4":"⁴","5":"⁵","6":"⁶","7":"⁷","8":"⁸","9":"⁹",
    "+":"⁺","-":"⁻","=":"⁼","(":"⁽",")":"⁾","n":"ⁿ","i":"ⁱ","j":"ʲ","k":"ᵏ","l":"ˡ","m":"ᵐ","x":"ˣ","y":"ʸ","z":"ᶻ","a":"ᵃ","b":"ᵇ","c":"ᶜ","d":"ᵈ","e":"ᵉ","f":"ᶠ","g":"ᵍ","h":"ʰ","o":"ᵒ","p":"ᵖ","r":"ʳ","s":"ˢ","t":"ᵗ","u":"ᵘ","v":"ᵛ","w":"ʷ","q":"ᑫ"
]

let subscriptMap: [Character: Character] = [
    "0":"₀","1":"₁","2":"₂","3":"₃","4":"₄","5":"₅","6":"₆","7":"₇","8":"₈","9":"₉",
    "+":"₊","-":"₋","=":"₌","(":"₍",")":"₎","i":"ᵢ","j":"ⱼ","k":"ₖ","l":"ₗ","m":"ₘ","n":"ₙ","p":"ₚ","r":"ᵣ","s":"ₛ","t":"ₜ","u":"ᵤ","v":"ᵥ","x":"ₓ","a":"ₐ","e":"ₑ","o":"ₒ","h":"ₕ","q":"ᵩ"
]

func mapScript(_ s: String, table: [Character: Character]) -> String {
    return String(s.map { table[$0] ?? $0 })
}

func replaceLatexSymbols(in text: String) -> String {
    var out = text
    for (k, v) in latexSymbolMap {
        out = out.replacingOccurrences(of: k, with: v)
    }
    return out
}

func renderScriptGroup(_ group: String, table: [Character: Character], prefix: String) -> String {
    let replaced = replaceLatexSymbols(in: group).trimmingCharacters(in: .whitespacesAndNewlines)
    guard !replaced.isEmpty else { return prefix }
    var mapped = ""
    var allMapped = true
    for ch in replaced {
        if let mappedChar = table[ch] {
            mapped.append(mappedChar)
        } else {
            mapped.append(ch)
            allMapped = false
        }
    }
    return allMapped ? mapped : "\(prefix)\(mapped)"
}

func replaceRegex(_ pattern: String, in text: String, options: NSRegularExpression.Options = [], transform: (NSTextCheckingResult, NSString) -> String) -> String {
    guard let re = try? NSRegularExpression(pattern: pattern, options: options) else { return text }
    let ns = text as NSString
    var out = ""
    var last = 0
    for m in re.matches(in: text, options: [], range: NSRange(location: 0, length: ns.length)) {
        if m.range.location > last {
            out += ns.substring(with: NSRange(location: last, length: m.range.location - last))
        }
        out += transform(m, ns)
        last = m.range.location + m.range.length
    }
    if last < ns.length {
        out += ns.substring(from: last)
    }
    return out
}

func renderLatexReadable(_ s: String) -> String {
    var out = s

    // Remove common math delimiters while keeping content.
    out = replaceRegex(#"(?s)\$\$(.+?)\$\$"#, in: out, options: [.dotMatchesLineSeparators]) { m, ns in
        ns.substring(with: m.range(at: 1))
    }
    out = replaceRegex(#"(?s)\\\[(.+?)\\\]"#, in: out, options: [.dotMatchesLineSeparators]) { m, ns in
        ns.substring(with: m.range(at: 1))
    }
    out = replaceRegex(#"(?s)\\\((.+?)\\\)"#, in: out, options: [.dotMatchesLineSeparators]) { m, ns in
        ns.substring(with: m.range(at: 1))
    }
    out = replaceRegex(#"(?s)\$(.+?)\$"#, in: out, options: [.dotMatchesLineSeparators]) { m, ns in
        ns.substring(with: m.range(at: 1))
    }

    // Strip simple formatting wrappers.
    out = replaceRegex(#"\\text\{([^}]*)\}"#, in: out) { m, ns in ns.substring(with: m.range(at: 1)) }
    out = replaceRegex(#"\\mathrm\{([^}]*)\}"#, in: out) { m, ns in ns.substring(with: m.range(at: 1)) }
    out = replaceRegex(#"\\mathbf\{([^}]*)\}"#, in: out) { m, ns in ns.substring(with: m.range(at: 1)) }

    // Convert superscripts/subscripts (preserve readable fallbacks when unsupported).
    out = replaceRegex(#"\^\{([^}]+)\}"#, in: out) { m, ns in
        renderScriptGroup(ns.substring(with: m.range(at: 1)), table: superscriptMap, prefix: "^")
    }
    out = replaceRegex(#"\^\\([A-Za-z]+)"#, in: out) { m, ns in
        renderScriptGroup("\\" + ns.substring(with: m.range(at: 1)), table: superscriptMap, prefix: "^")
    }
    out = replaceRegex(#"\^([A-Za-z0-9\+\-\=\(\)]+)"#, in: out) { m, ns in
        renderScriptGroup(ns.substring(with: m.range(at: 1)), table: superscriptMap, prefix: "^")
    }
    out = replaceRegex(#"_\{([^}]+)\}"#, in: out) { m, ns in
        renderScriptGroup(ns.substring(with: m.range(at: 1)), table: subscriptMap, prefix: "_")
    }
    out = replaceRegex(#"_\\([A-Za-z]+)"#, in: out) { m, ns in
        renderScriptGroup("\\" + ns.substring(with: m.range(at: 1)), table: subscriptMap, prefix: "_")
    }
    out = replaceRegex(#"_([A-Za-z0-9\+\-\=\(\)]+)"#, in: out) { m, ns in
        renderScriptGroup(ns.substring(with: m.range(at: 1)), table: subscriptMap, prefix: "_")
    }

    // Replace simple symbol macros.
    out = replaceLatexSymbols(in: out)

    return out
}


// MARK: - Abstract cleanup

func cleanAbstract(_ raw: String) -> String {
    var s = raw
        .replacingOccurrences(of: "\r\n", with: "\n")
        .replacingOccurrences(of: "\r", with: "\n")

    s = regexReplace(
        s,
        #"\n\s*\\\\\s*\(\s*https?://arxiv\.org/abs/[^)]*\)\s*\n\s*[-–—]{5,}\s*\n\s*\\\\\s*(?:\n|$)"#,
        "\n",
        options: [.caseInsensitive]
    )

    s = regexReplace(s, #"(?m)^([ \t]*)\\\\([ \t]*)$"#, " ", options: [])
    s = s.replacingOccurrences(of: "\t", with: "    ")
    s = regexReplace(s, #"[ ]{16,}"#, "    ")

    return s.trimmingCharacters(in: .whitespacesAndNewlines)
}

func extractYear(from dateLine: String) -> String {
    let s = stripLeadingLabel(dateLine, label: "Date")
    if let re = try? NSRegularExpression(pattern: #"\b(19|20)\d{2}\b"#) {
        let range = NSRange(location: 0, length: (s as NSString).length)
        if let m = re.firstMatch(in: s, range: range) {
            return (s as NSString).substring(with: m.range)
        }
    }
    return ""
}

func dateOnlyDisplayString(from dateLine: String) -> String {
    // Date header should show only the date portion (no time-of-day / timezone).
    var s = decodeTeXAccents(stripLeadingLabel(dateLine, label: "Date"))
        .replacingOccurrences(of: "\n", with: " ")
        .trimmingCharacters(in: .whitespacesAndNewlines)
    guard !s.isEmpty else { return "" }

    if let pipe = s.firstIndex(of: "|") {
        s = String(s[..<pipe]).trimmingCharacters(in: .whitespacesAndNewlines)
    }

    if let re = try? NSRegularExpression(pattern: #"\b\d{1,2}:\d{2}(?::\d{2})?\b"#) {
        let ns = s as NSString
        let r = NSRange(location: 0, length: ns.length)
        if let m = re.firstMatch(in: s, range: r) {
            let prefix = ns.substring(to: m.range.location)
            let trimmed = prefix.trimmingCharacters(in: .whitespacesAndNewlines)
            if !trimmed.isEmpty { return trimmed }
        }
    }

    return s
}


// MARK: - Author formatting

func parseAuthorList(from authorsField: String) -> [String] {
    let s = decodeTeXAccents(stripLeadingLabel(authorsField, label: "Authors"))
        .replacingOccurrences(of: "\n", with: " ")
        .trimmingCharacters(in: .whitespacesAndNewlines)

    guard !s.isEmpty else { return [] }

    var parts = s.split(separator: ",").map { String($0).trimmingCharacters(in: .whitespacesAndNewlines) }
    if parts.count == 1, s.lowercased().contains(" and ") {
        parts = s.components(separatedBy: " and ").map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
    }
    return parts.filter { !$0.isEmpty }
}

func formatAuthorInitialsLast(_ full: String) -> String {
    let cleaned = decodeTeXAccents(full)
        .replacingOccurrences(of: "  ", with: " ")
        .trimmingCharacters(in: .whitespacesAndNewlines)
    if cleaned.isEmpty { return cleaned }

    let tokens = cleaned.split(separator: " ").map { String($0) }.filter { !$0.isEmpty }
    guard tokens.count >= 1 else { return cleaned }

    let last = tokens.last!

    func initial(from token: String) -> String? {
        let t = token.trimmingCharacters(in: .punctuationCharacters)
        guard let ch = t.first else { return nil }
        if t.count == 2, t.last == "." { return t }
        return "\(ch)."
    }

    let firstInit = initial(from: tokens[0]) ?? ""
    var middleInit = ""
    if tokens.count >= 3 {
        let mid = tokens[1]
        let low = mid.lowercased()
        if low != "de" && low != "van" && low != "von" {
            if let mi = initial(from: mid) { middleInit = mi }
        }
    }

    let initials = [firstInit, middleInit].filter { !$0.isEmpty }.joined(separator: " ")
    if initials.isEmpty { return last }
    return "\(initials) \(last)"
}

func leftAuthorYearText(paper: Paper) -> String {
    let authors = parseAuthorList(from: paper.authors).map(formatAuthorInitialsLast)
    let year = extractYear(from: paper.dateLine)

    if authors.isEmpty {
        return year.isEmpty ? "Unknown authors" : "Unknown authors \(year)"
    }
    if authors.count == 1 {
        return year.isEmpty ? authors[0] : "\(authors[0]) \(year)"
    }

    let a1 = authors[0]
    let a2 = authors[1]
    let etal = (authors.count >= 3) ? " et al." : ""
    let yr = year.isEmpty ? "" : " \(year)"
    return "\(a1) & \(a2)\(etal)\(yr)"
}


// MARK: - Keyword presence

func paperSearchCorpus(_ p: Paper) -> String {
    let absClean = cleanAbstract(p.abstractText)
    let corpus = [
        p.title, p.authors, p.categories, p.dateLine, p.url, p.comments, absClean
    ].joined(separator: "\n")
    return decodeTeXAccents(corpus).lowercased()
}

func keywordsPresent(in paper: Paper, keywords: [String]) -> [String] {
    let corpus = paperSearchCorpus(paper)
    var seen = Set<String>()
    var out: [String] = []

    for kw in keywords {
        let k = kw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !k.isEmpty else { continue }
        let kl = k.lowercased()
        if corpus.contains(kl), !seen.contains(kl) {
            seen.insert(kl)
            out.append(k)
        }
    }

    out.sort { $0.localizedCaseInsensitiveCompare($1) == .orderedAscending }
    return out
}

func dedupePluralKeywordsForDisplay(_ keywords: [String]) -> [String] {
    guard keywords.count > 1 else { return keywords }
    let normalized = keywords.map { $0.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() }
    let normalizedSet = Set(normalized)

    func hasSingularVariant(_ lower: String) -> Bool {
        // Drop plural forms when a singular keyword is also present.
        if lower.hasSuffix("ies"), lower.count > 3 {
            let candidate = String(lower.dropLast(3)) + "y"
            if normalizedSet.contains(candidate) { return true }
        }
        if lower.hasSuffix("es"), lower.count > 2 {
            let candidate = String(lower.dropLast(2))
            if normalizedSet.contains(candidate) { return true }
        }
        if lower.hasSuffix("s"), lower.count > 1 {
            let candidate = String(lower.dropLast(1))
            if normalizedSet.contains(candidate) { return true }
        }
        return false
    }

    var out: [String] = []
    for (idx, kw) in keywords.enumerated() {
        let lower = normalized[idx]
        if hasSingularVariant(lower) { continue }
        out.append(kw)
    }
    return out
}


// MARK: - Topic inference (abstracts)

enum AstroTopic: String, CaseIterable {
    case planets
    case galaxies
    case blackHoles
    case stars
    case cosmology
    case ism
    case instrumentation

    var displayName: String {
        switch self {
        case .planets: return "Planets / Exoplanets"
        case .galaxies: return "Galaxies / Extragalactic"
        case .blackHoles: return "Black Holes / Compact Objects"
        case .stars: return "Sun / Stars / Stellar Physics"
        case .cosmology: return "Cosmology / Large-scale Structure"
        case .ism: return "ISM / Star Formation"
        case .instrumentation: return "Instrumentation / Methods"
        }
    }
}

struct HTMLImageTheme: Equatable {
    let leftPath: String
    let centerPath: String
    let rightPath: String
}

struct AstroTopicDefinition {
    let topic: AstroTopic
    let terms: [String]
    let theme: HTMLImageTheme
}

struct TopicTermPattern {
    let raw: String
    let stemmedPattern: String
    let isPhrase: Bool
    let weight: Double
}

struct TopicScore {
    let topic: AstroTopic
    var score: Int
    var distinctTermCount: Int
    var weightedScore: Double
    var matchedTerms: [String: Int]
}

struct TopicInferenceResult {
    let ranked: [TopicScore]
    let winner: TopicScore?
    let isStrong: Bool
}

struct TopicThemeSelection {
    let topic: AstroTopic
    let theme: HTMLImageTheme
    let score: Int
    let distinctTermCount: Int
    let weightedScore: Double
}

final class HTMLThemeInferenceStore {
    static let shared = HTMLThemeInferenceStore()
    private let lock = NSLock()
    private var selection: TopicThemeSelection?

    func update(_ next: TopicThemeSelection?) {
        lock.lock()
        selection = next
        lock.unlock()
    }

    func current() -> TopicThemeSelection? {
        lock.lock()
        let value = selection
        lock.unlock()
        return value
    }
}

let astroTopicDefinitions: [AstroTopicDefinition] = [
    AstroTopicDefinition(
        topic: .planets,
        terms: [
            "exoplanet", "exoplanets", "planet", "planets", "planetary", "super earth", "super-earth",
            "hot jupiter", "transit", "transiting", "radial velocity", "habitable zone", "biosignature",
            "direct imaging", "microlensing", "occultation", "kepler", "tess", "k2"
        ],
        theme: HTMLImageTheme(
            leftPath: HTML_THEME_EXOPLANETS_LEFT_PATH,
            centerPath: HTML_THEME_EXOPLANETS_CENTER_PATH,
            rightPath: HTML_THEME_EXOPLANETS_RIGHT_PATH
        )
    ),
    AstroTopicDefinition(
        topic: .galaxies,
        terms: [
            "galaxy", "galaxies", "galactic", "extragalactic", "galaxy cluster", "galaxy clusters",
            "dwarf galaxy", "spiral galaxy", "elliptical galaxy", "intergalactic", "halo", "bulge",
            "active galactic nucleus", "agn", "quasar", "seyfert", "blazar", "starburst"
        ],
        theme: HTMLImageTheme(
            leftPath: HTML_THEME_GALAXIES_LEFT_PATH,
            centerPath: HTML_THEME_GALAXIES_CENTER_PATH,
            rightPath: HTML_THEME_GALAXIES_RIGHT_PATH
        )
    ),
    AstroTopicDefinition(
        topic: .blackHoles,
        terms: [
            "black hole", "black holes", "supermassive black hole", "event horizon", "accretion", "accreting",
            "accretion disk", "accretion disc", "compact object", "neutron star", "neutron stars", "pulsar",
            "magnetar", "x-ray binary", "gravitational wave", "merger", "tidal disruption", "tde", "ligo", "lisa"
        ],
        theme: HTMLImageTheme(
            leftPath: HTML_THEME_BLACKHOLES_LEFT_PATH,
            centerPath: HTML_THEME_BLACKHOLES_CENTER_PATH,
            rightPath: HTML_THEME_BLACKHOLES_RIGHT_PATH
        )
    ),
    AstroTopicDefinition(
        topic: .stars,
        terms: [
            "star", "stars", "stellar", "sun", "solar", "stellar evolution", "main sequence",
            "red giant", "supernova", "supernovae", "white dwarf", "flare", "corona", "coronal",
            "chromosphere", "photosphere", "helioseismology", "stellar rotation"
        ],
        theme: HTMLImageTheme(
            leftPath: HTML_THEME_STARS_LEFT_PATH,
            centerPath: HTML_THEME_STARS_CENTER_PATH,
            rightPath: HTML_THEME_STARS_RIGHT_PATH
        )
    ),
    AstroTopicDefinition(
        topic: .cosmology,
        terms: [
            "cosmology", "cosmic microwave background", "cmb", "large scale structure",
            "dark matter", "dark energy", "inflation", "baryon acoustic", "bao", "hubble constant",
            "reionization", "primordial", "big bang", "expansion rate"
        ],
        theme: HTMLImageTheme(
            leftPath: HTML_THEME_COSMOLOGY_LEFT_PATH,
            centerPath: HTML_THEME_COSMOLOGY_CENTER_PATH,
            rightPath: HTML_THEME_COSMOLOGY_RIGHT_PATH
        )
    ),
    AstroTopicDefinition(
        topic: .ism,
        terms: [
            "interstellar medium", "ism", "molecular cloud", "star formation", "protostar",
            "protostellar", "young stellar object", "yso", "nebula", "h ii region", "dust",
            "molecular gas", "feedback", "filament", "cloud collapse"
        ],
        theme: HTMLImageTheme(
            leftPath: HTML_THEME_ISM_LEFT_PATH,
            centerPath: HTML_THEME_ISM_CENTER_PATH,
            rightPath: HTML_THEME_ISM_RIGHT_PATH
        )
    ),
    AstroTopicDefinition(
        topic: .instrumentation,
        terms: [
            "instrument", "instrumentation", "telescope", "observatory", "spectrograph", "detector",
            "camera", "survey", "catalog", "pipeline", "calibration", "data reduction", "algorithm",
            "method", "technique", "simulation", "numerical", "machine learning", "neural network"
        ],
        theme: HTMLImageTheme(
            leftPath: HTML_THEME_INSTRUMENTATION_LEFT_PATH,
            centerPath: HTML_THEME_INSTRUMENTATION_CENTER_PATH,
            rightPath: HTML_THEME_INSTRUMENTATION_RIGHT_PATH
        )
    )
]

let astroTopicThemeByTopic: [AstroTopic: HTMLImageTheme] = {
    var map: [AstroTopic: HTMLImageTheme] = [:]
    for def in astroTopicDefinitions {
        map[def.topic] = def.theme
    }
    return map
}()

let topicStopwords: Set<String> = [
    "the", "and", "or", "but", "if", "in", "on", "at", "for", "to", "from", "by", "with", "without",
    "of", "a", "an", "is", "are", "was", "were", "be", "been", "being", "this", "that", "these", "those",
    "we", "our", "their", "it", "its", "as", "such", "via", "using", "use", "used", "based", "show", "shows",
    "result", "results", "analysis", "model", "models", "data", "observation", "observations", "observed",
    "survey", "simulation", "simulations", "method", "methods", "approach", "study", "paper", "work", "new"
]

let topicDownweightTerms: Set<String> = [
    "model", "observation", "observ", "simulation", "survey", "data", "analysis", "method", "instrument", "pipeline", "catalog"
]

let topicStemOverrides: [String: String] = [
    "galaxies": "galaxy",
    "stars": "star",
    "stellar": "stellar",
    "accretion": "accret",
    "accreting": "accret",
    "accreted": "accret",
    "supernovae": "supernova"
]

func normalizeTopicText(_ raw: String) -> String {
    let folded = raw.folding(options: [.diacriticInsensitive, .widthInsensitive, .caseInsensitive], locale: .current)
    var scalars: [UnicodeScalar] = []
    scalars.reserveCapacity(folded.unicodeScalars.count)
    for scalar in folded.unicodeScalars {
        if CharacterSet.alphanumerics.contains(scalar) {
            scalars.append(scalar)
        } else if CharacterSet.whitespacesAndNewlines.contains(scalar) {
            scalars.append(" ")
        } else {
            scalars.append(" ")
        }
    }
    let normalized = String(String.UnicodeScalarView(scalars))
    let collapsed = regexReplace(normalized, #"\s+"#, " ", options: [])
    return collapsed.trimmingCharacters(in: .whitespacesAndNewlines)
}

func tokenizeTopicText(_ raw: String) -> [String] {
    let normalized = normalizeTopicText(raw)
    guard !normalized.isEmpty else { return [] }
    return normalized.split(separator: " ").map { String($0) }
}

func stemTopicToken(_ token: String) -> String {
    let lower = token.lowercased()
    if let override = topicStemOverrides[lower] {
        return override
    }
    var out = lower
    if out.count > 4 {
        if out.hasSuffix("ies") {
            out = String(out.dropLast(3)) + "y"
        } else if out.hasSuffix("sses") {
            out = String(out.dropLast(2))
        } else if out.hasSuffix("xes") || out.hasSuffix("zes") {
            out = String(out.dropLast(2))
        }
    }
    if out.count > 4, out.hasSuffix("ing") {
        out = String(out.dropLast(3))
    } else if out.count > 3, out.hasSuffix("ed") {
        out = String(out.dropLast(2))
    }
    if out.count > 3, out.hasSuffix("s"), !out.hasSuffix("ss") {
        out = String(out.dropLast(1))
    }
    return out
}

func makeTopicTermPattern(_ raw: String) -> TopicTermPattern {
    let tokens = tokenizeTopicText(raw)
    let stemmedTokens = tokens.map(stemTopicToken)
    let stemmedPattern = stemmedTokens.joined(separator: " ")
    let isPhrase = stemmedTokens.count > 1
    let weight = (!isPhrase && topicDownweightTerms.contains(stemmedPattern)) ? 0.5 : 1.0
    return TopicTermPattern(raw: raw, stemmedPattern: stemmedPattern, isPhrase: isPhrase, weight: weight)
}

let astroTopicPatterns: [AstroTopic: [TopicTermPattern]] = {
    var map: [AstroTopic: [TopicTermPattern]] = [:]
    for def in astroTopicDefinitions {
        map[def.topic] = def.terms.map { makeTopicTermPattern($0) }
    }
    return map
}()

func countOccurrences(of needle: String, in haystack: String) -> Int {
    guard !needle.isEmpty, !haystack.isEmpty else { return 0 }
    var count = 0
    var searchRange = haystack.startIndex..<haystack.endIndex
    while let range = haystack.range(of: needle, options: [], range: searchRange) {
        count += 1
        searchRange = range.upperBound..<haystack.endIndex
    }
    return count
}

func inferAstroTopic(from abstracts: [String]) -> TopicInferenceResult {
    let minScoreThreshold = 3
    let nearTieFraction = 0.15

    var accumulators: [AstroTopic: (score: Int, weighted: Double, matchedTerms: [String: Int], distinct: Set<String>)] = [:]
    for topic in AstroTopic.allCases {
        accumulators[topic] = (0, 0.0, [:], Set<String>())
    }

    for raw in abstracts {
        let cleaned = renderLatexReadable(decodeTeXAccents(cleanAbstract(raw)))
        if cleaned.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { continue }
        let tokens = tokenizeTopicText(cleaned)
        guard !tokens.isEmpty else { continue }
        let stemmedTokens = tokens.map(stemTopicToken)
        let stemmedText = " " + stemmedTokens.joined(separator: " ") + " "
        let filteredTokens = stemmedTokens.filter { !topicStopwords.contains($0) }
        var tokenCounts: [String: Int] = [:]
        for tok in filteredTokens {
            tokenCounts[tok, default: 0] += 1
        }

        for (topic, patterns) in astroTopicPatterns {
            guard var acc = accumulators[topic] else { continue }
            for pattern in patterns {
                let count: Int
                if pattern.isPhrase {
                    let needle = " " + pattern.stemmedPattern + " "
                    count = countOccurrences(of: needle, in: stemmedText)
                } else {
                    count = tokenCounts[pattern.stemmedPattern] ?? 0
                }
                if count > 0 {
                    acc.score += count
                    acc.weighted += Double(count) * pattern.weight
                    acc.matchedTerms[pattern.raw, default: 0] += count
                    acc.distinct.insert(pattern.raw)
                }
            }
            accumulators[topic] = acc
        }
    }

    var scores: [TopicScore] = []
    for topic in AstroTopic.allCases {
        guard let acc = accumulators[topic] else { continue }
        scores.append(TopicScore(
            topic: topic,
            score: acc.score,
            distinctTermCount: acc.distinct.count,
            weightedScore: acc.weighted,
            matchedTerms: acc.matchedTerms
        ))
    }

    let ranked = scores.sorted {
        if $0.score != $1.score { return $0.score > $1.score }
        if $0.distinctTermCount != $1.distinctTermCount { return $0.distinctTermCount > $1.distinctTermCount }
        if abs($0.weightedScore - $1.weightedScore) > 0.0001 { return $0.weightedScore > $1.weightedScore }
        return $0.topic.displayName < $1.topic.displayName
    }

    guard let top = ranked.first else {
        return TopicInferenceResult(ranked: ranked, winner: nil, isStrong: false)
    }

    var winner = top
    if ranked.count > 1 {
        let second = ranked[1]
        let tieDelta = max(1, Int(round(Double(top.score) * nearTieFraction)))
        if top.score - second.score <= tieDelta {
            if second.distinctTermCount > top.distinctTermCount {
                winner = second
            } else if second.distinctTermCount == top.distinctTermCount,
                      second.weightedScore > top.weightedScore {
                winner = second
            }
        }
    }

    let isStrong = winner.score >= minScoreThreshold
    return TopicInferenceResult(ranked: ranked, winner: winner, isStrong: isStrong)
}

func updateAutoHTMLThemeSelection(from abstracts: [String]) -> TopicInferenceResult {
    let result = inferAstroTopic(from: abstracts)
    if result.isStrong, let winner = result.winner, let theme = astroTopicThemeByTopic[winner.topic] {
        let selection = TopicThemeSelection(
            topic: winner.topic,
            theme: theme,
            score: winner.score,
            distinctTermCount: winner.distinctTermCount,
            weightedScore: winner.weightedScore
        )
        HTMLThemeInferenceStore.shared.update(selection)
    } else {
        HTMLThemeInferenceStore.shared.update(nil)
    }
    return result
}

#if DEBUG
func logTopicInference(_ result: TopicInferenceResult) {
    guard let top = result.ranked.first else {
        print("[TopicInference] no_topics")
        return
    }
    let entries = result.ranked
    print("[TopicInference] top=\(top.topic.displayName) score=\(top.score) distinct=\(top.distinctTermCount) weighted=\(String(format: "%.2f", top.weightedScore)) strong=\(result.isStrong)")
    if entries.count > 1 {
        let next = entries[1]
        print("[TopicInference] next=\(next.topic.displayName) score=\(next.score)")
    }
    if entries.count > 2 {
        let third = entries[2]
        print("[TopicInference] third=\(third.topic.displayName) score=\(third.score)")
    }
    if let winner = result.winner {
        let topTerms = winner.matchedTerms.sorted { a, b in
            if a.value != b.value { return a.value > b.value }
            return a.key < b.key
        }.prefix(6).map { "\($0.key)(\($0.value))" }
        if !topTerms.isEmpty {
            print("[TopicInference] top_terms=\(topTerms.joined(separator: ", "))")
        }
    }
}
#endif

// MARK: - HTML rendering (details)

func buildDetailsHTML(paper: Paper,
                      keywordsForHighlight: [String],
                      highlightCSS: String,
                      textPalette: TextPalette,
                      paperIndex: Int,
                      paperTotal: Int) -> String {
	    let title = paper.title
	    let authors = stripLeadingLabel(paper.authors, label: "Authors")
	    let authorHeader = decodeTeXAccents(authors)
	        .replacingOccurrences(of: "\n", with: " ")
	        .components(separatedBy: .whitespacesAndNewlines)
	        .filter { !$0.isEmpty }
	        .joined(separator: " ")
	    let categories = stripLeadingLabel(paper.categories, label: "Categories")
	    let dateHeader = dateOnlyDisplayString(from: paper.dateLine)
	    let url = stripLeadingLabel(paper.url, label: "URL")
	    let comments = stripLeadingLabel(paper.comments, label: "Comments")
	    let abstract = renderLatexReadable(decodeTeXAccents(cleanAbstract(paper.abstractText)))

    let htmlImages = AppSettingsStore.shared.current.appearance.htmlImages
    func resolvedImagePath(_ override: String, fallback: String) -> String {
        let trimmed = override.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? fallback : trimmed
    }
    func resolvedAutoThemePath(_ candidate: String, fallback: String) -> String {
        let trimmed = candidate.trimmingCharacters(in: .whitespacesAndNewlines)
        let path = trimmed.isEmpty ? fallback : trimmed
        let expanded = (path as NSString).expandingTildeInPath
        if FileManager.default.fileExists(atPath: expanded) {
            return path
        }
        return fallback
    }
    let hasManualOverrides = [
        htmlImages.leftPath,
        htmlImages.centerPath,
        htmlImages.rightPath
    ].contains { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
    let autoTheme = HTMLThemeInferenceStore.shared.current()
    let useAutoTheme = (!hasManualOverrides && autoTheme != nil)

    let leftImagePath: String
    let centerImagePath: String
    let rightImagePath: String
    if useAutoTheme, let selection = autoTheme {
        leftImagePath = resolvedAutoThemePath(selection.theme.leftPath, fallback: HEADER_IMAGE_LEFT_PATH)
        centerImagePath = resolvedAutoThemePath(selection.theme.centerPath, fallback: HEADER_IMAGE_CENTER_PATH)
        rightImagePath = resolvedAutoThemePath(selection.theme.rightPath, fallback: HEADER_IMAGE_RIGHT_PATH)
    } else {
        leftImagePath = resolvedImagePath(htmlImages.leftPath, fallback: HEADER_IMAGE_LEFT_PATH)
        centerImagePath = resolvedImagePath(htmlImages.centerPath, fallback: HEADER_IMAGE_CENTER_PATH)
        rightImagePath = resolvedImagePath(htmlImages.rightPath, fallback: HEADER_IMAGE_RIGHT_PATH)
    }

    func cssFontFamily(_ name: String) -> String {
        name.replacingOccurrences(of: "'", with: "\\'")
    }

    let fontOverride = resolvedHTMLFontOverride()
    let bodyFontCSS: String
    let abstractFontCSS: String
    if let override = fontOverride {
        let family = cssFontFamily(override.familyName)
        let sizePx = max(10.0, override.font.pointSize)
        let abstractSize = max(10.0, sizePx - 1.0)
        bodyFontCSS = "font-family: '\(family)', -apple-system, BlinkMacSystemFont, \"SF Pro Text\", \"Helvetica Neue\", Helvetica, Arial, sans-serif; font-size: \(String(format: "%.0f", sizePx))px;"
        abstractFontCSS = "font-family: '\(family)'; font-size: \(String(format: "%.0f", abstractSize))px;"
    } else {
        bodyFontCSS = "font-family: -apple-system, BlinkMacSystemFont, \"SF Pro Text\", \"Helvetica Neue\", Helvetica, Arial, sans-serif;"
        abstractFontCSS = "font-family: Georgia, \"Times New Roman\", Times, serif; font-size: 14px;"
    }

    func imgTag(_ path: String, isSide: Bool) -> String {
        let p = path.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !p.isEmpty else { return "" }
        let expanded = (p as NSString).expandingTildeInPath
        guard FileManager.default.fileExists(atPath: expanded) else { return "" }
        let u = URL(fileURLWithPath: expanded)
        let klass = isSide ? "header-img header-img-side" : "header-img header-img-center"
        return #"<img class="\#(klass)" src="\#(htmlEscape(u.absoluteString))" alt="header"/>"#
    }

    let centerTag = imgTag(centerImagePath, isSide: false)
    let headerHTML = centerTag.isEmpty ? "" : """
    <div class="logo-row">\(centerTag)</div>
    """

    let kwJSArray = "[" + keywordsForHighlight.map { "\"\(jsStringEscape($0))\"" }.joined(separator: ",") + "]"
    let detailsLightBG = DETAILS_PANEL_LIGHT_BG
    let detailsDarkBG = DETAILS_PANEL_DARK_BG
    let lightPalette = adaptiveTextPalette(baseColor: detailsLightBG, linkHex: RIGHT_LINK_COLOR_HEX)
    let darkPalette = adaptiveTextPalette(baseColor: detailsDarkBG, linkHex: RIGHT_LINK_COLOR_HEX)
    let clampedTotal = max(0, paperTotal)
    let clampedIndex = clampedTotal == 0 ? 0 : max(1, min(clampedTotal, paperIndex))

    return """
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <style>
    :root {
      --bg: \(cssRGBA(detailsLightBG));
      --text-primary: \(cssRGBA(lightPalette.primary));
      --text-secondary: \(cssRGBA(lightPalette.secondary));
      --text-muted: \(cssRGBA(lightPalette.muted));
      --text-link: \(cssRGBA(lightPalette.link));
      --rule: \(cssRGBA(lightPalette.rule));
      --code-fg: \(cssRGBA(lightPalette.codeText));
      --code-bg: \(cssRGBA(lightPalette.codeBackground));
      --kwbg: \(highlightCSS);
      --page-pad-x: 18px;
      --page-pad-top: 18px;
      --page-pad-bottom: 28px;
    }

    @media (prefers-color-scheme: dark) {
      :root {
        --bg: \(cssRGBA(detailsDarkBG));
        --text-primary: \(cssRGBA(darkPalette.primary));
        --text-secondary: \(cssRGBA(darkPalette.secondary));
        --text-muted: \(cssRGBA(darkPalette.muted));
        --text-link: \(cssRGBA(darkPalette.link));
        --rule: \(cssRGBA(darkPalette.rule));
        --code-fg: \(cssRGBA(darkPalette.codeText));
        --code-bg: \(cssRGBA(darkPalette.codeBackground));
      }
    }

    html, body { height: 100%; background: var(--bg); overflow-x: hidden; overscroll-behavior: none; overscroll-behavior-y: none; }
    body {
      margin: 0;
      color: var(--text-primary);
      \(bodyFontCSS)
      line-height: 1.35;
    }

    .page-shell {
      min-height: 100vh;
      background: var(--bg);
      border-radius: \(PANEL_CORNER_RADIUS)px;
      overflow: hidden;
      position: relative;
      padding: var(--page-pad-top) var(--page-pad-x) var(--page-pad-bottom) var(--page-pad-x);
      box-sizing: border-box;
      display: flex;
      flex-direction: column;
    }

    .content {
      flex: 1 1 auto;
    }

    * { overflow-wrap: anywhere; word-break: break-word; }

		    /* Static page header: stays at the top of the document and scrolls away (not fixed/sticky). */
		    .page-header {
		      display: grid;
		      grid-template-columns: minmax(0, 1fr) minmax(0, 2fr) minmax(0, 1fr);
		      align-items: start;
		      column-gap: 12px;
		      margin: 0 0 12px 0;
		    }

		    .chrome-left,
		    .chrome-center,
		    .chrome-right {
		      font-size: 11px;
		      font-weight: 500;
		      letter-spacing: 0.1px;
		      color: var(--text-muted);
		      opacity: 0.95;
		      user-select: none;
		      pointer-events: none;
		      font-variant-numeric: tabular-nums;
		      min-width: 0;
		    }

		    .chrome-left {
		      text-align: left;
		      white-space: nowrap;
		      overflow: hidden;
		      text-overflow: ellipsis;
		    }

		    .chrome-center {
		      text-align: center;
		      white-space: normal;
		      overflow-wrap: anywhere;
		      word-break: break-word;
		      line-height: 1.25;
		    }

		    .chrome-right {
		      text-align: right;
		      white-space: nowrap;
		      overflow: hidden;
		      text-overflow: ellipsis;
		    }

	    .title-row {
	      display: flex;
	      align-items: center;
	      justify-content: center;
	      gap: 12px;
	      margin: 0 0 6px 0;
	    }

	    .logo-row {
	      display: flex;
	      align-items: center;
	      justify-content: center;
	      margin: 0 0 6px 0;
	    }

	    .title-link {
	      color: inherit !important;
	      text-decoration: none !important;
	    }
	    .title-link:hover {
	      color: var(--text-link) !important;
	      text-decoration: underline !important;
	    }

	    .header-img {
	      max-height: \(HEADER_IMAGE_MAX_HEIGHT)px;
	      height: auto; width: auto;
	      transform-origin: center;
	      display: block;
    }
    .header-img-center { transform: scale(\(HEADER_IMAGE_SCALE)); }
    .header-img-side   { transform: scale(\(HEADER_IMAGE_SIDE_SCALE)); }

	    h1 { font-size: 20px; margin: 0; font-weight: 700; text-align: center; color: var(--text-primary); }
	    .rule {
	      height: 1px;
	      background: var(--rule);
	      margin: 10px 0 16px 0;
	      width: calc(100% + (2 * var(--page-pad-x)));
	      margin-left: calc(-1 * var(--page-pad-x));
	      margin-right: calc(-1 * var(--page-pad-x));
	    }
	    .row { margin: 0 0 10px 0; color: var(--text-primary); }
	    .label { font-weight: 700; margin-right: 6px; color: var(--text-muted); }

    a { color: var(--text-link); text-decoration: underline; }

    .abstract-label { font-weight: 700; margin-top: 10px; text-align: center; color: var(--text-secondary); }
    .abstract {
      \(abstractFontCSS)
      width: 100%;
      max-width: none;
      box-sizing: border-box;
      white-space: normal;
      overflow-wrap: anywhere;
      word-break: break-word;
      text-align: center;
      color: var(--text-primary);
    }

	    .abstract-end {
	      /* Intentionally unused (footer has the only divider). */
	      display: none;
	    }

    .footer {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 14px;
      margin: 14px 0 0 0;
      padding: 10px 0 0 0;
      border-top: none;
      position: relative;
      color: var(--text-muted);
      font-size: 11px;
      font-weight: 500;
      letter-spacing: 0.1px;
    }
    .footer-left,
    .footer-right {
      flex: 1;
      min-width: 0;
      display: flex;
      align-items: center;
      white-space: nowrap;
      overflow: hidden;
    }
    .footer::before {
      content: "";
      position: absolute;
      top: 0;
      left: calc(-1 * var(--page-pad-x));
      right: calc(-1 * var(--page-pad-x));
      height: 1px;
      background: var(--rule);
    }
	    .footer-left { text-align: left; justify-content: flex-start; }
	    .footer-right { text-align: right; justify-content: flex-end; }
	    .meta-value {
	      display: inline-block;
	      max-width: 100%;
	      vertical-align: baseline;
	      white-space: nowrap;
	      overflow: hidden;
	    }

	    .header-divider {
	      border-top: 1px solid var(--rule);
	      margin: 12px 0 0 0;
	      width: calc(100% + (2 * var(--page-pad-x)));
	      margin-left: calc(-1 * var(--page-pad-x));
	      margin-right: calc(-1 * var(--page-pad-x));
	    }

    code, pre {
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
      color: var(--code-fg);
      background: var(--code-bg);
      border-radius: 6px;
    }
    code { padding: 0 4px; }
    pre { padding: 10px; }

    .kw {
      background-color: var(--kwbg);
      color: inherit;
      padding: 0 2px;
      border-radius: 4px;
      box-decoration-break: clone;
      -webkit-box-decoration-break: clone;
    }
	  </style>

	  <script>
		    function escapeRegExp(s) { return s.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&'); }

    function highlightKeywords(container, keywords) {
      if (!container || !keywords || !keywords.length) return;
      const uniq = Array.from(new Set(keywords.map(k => (k || '').trim()).filter(Boolean)));
      if (!uniq.length) return;
      uniq.sort((a,b) => b.length - a.length);
      const pattern = uniq.map(k => escapeRegExp(k)).join('|');
      const re = new RegExp(pattern, 'gi');

      const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT, null);
      const nodes = [];
      while (walker.nextNode()) nodes.push(walker.currentNode);

      for (const node of nodes) {
        const text = node.nodeValue;
        if (!text || !re.test(text)) continue;
        re.lastIndex = 0;

        const frag = document.createDocumentFragment();
        let last = 0, m;

        while ((m = re.exec(text)) !== null) {
          const start = m.index;
          const end = start + m[0].length;

          if (start > last) frag.appendChild(document.createTextNode(text.slice(last, start)));

          const span = document.createElement('span');
          span.className = 'kw';
          span.textContent = text.slice(start, end);
          frag.appendChild(span);

          last = end;
        }

        if (last < text.length) frag.appendChild(document.createTextNode(text.slice(last)));
        node.parentNode.replaceChild(frag, node);
      }
    }

    const PAPER_KEYWORDS = \(kwJSArray);
    let __footerTruncLastWidth = 0;
    let __footerTruncCanvas = null;
    function footerMeasureText(text, el) {
      if (!__footerTruncCanvas) __footerTruncCanvas = document.createElement('canvas');
      const ctx = __footerTruncCanvas.getContext('2d');
      if (!ctx) return text.length;
      const style = window.getComputedStyle(el);
      const font = style.font && style.font.length
        ? style.font
        : [
            style.fontStyle,
            style.fontVariant,
            style.fontWeight,
            style.fontSize,
            '/',
            style.lineHeight,
            style.fontFamily
          ].join(' ');
      ctx.font = font;
      return ctx.measureText(text).width;
    }
    function truncateMetaValue(el) {
      if (!el) return;
      const full = el.getAttribute('data-full-text') || el.textContent || '';
      if (!el.getAttribute('data-full-text')) {
        el.setAttribute('data-full-text', full);
        el.setAttribute('title', full);
      }
      el.textContent = full;
      const parent = el.parentElement;
      if (!parent) return;
      const parentRect = parent.getBoundingClientRect();
      if (!parentRect || !isFinite(parentRect.width) || parentRect.width <= 1) return;
      const label = parent.querySelector('.label');
      let labelWidth = 0;
      let labelGap = 0;
      if (label) {
        const labelRect = label.getBoundingClientRect();
        labelWidth = labelRect ? labelRect.width : 0;
        const labelStyle = window.getComputedStyle(label);
        labelGap = parseFloat(labelStyle.marginRight) || 0;
      }
      const available = Math.max(0, parentRect.width - labelWidth - labelGap);
      if (available <= 1) return;
      if (footerMeasureText(full, el) <= available) return;
      const ellipsis = '...';
      const ellipsisWidth = footerMeasureText(ellipsis, el);
      if (ellipsisWidth >= available) {
        el.textContent = ellipsis;
        return;
      }
      let lo = 0;
      let hi = full.length;
      while (lo < hi) {
        const mid = Math.floor((lo + hi + 1) / 2);
        const slice = full.slice(0, mid);
        if (footerMeasureText(slice, el) + ellipsisWidth <= available) {
          lo = mid;
        } else {
          hi = mid - 1;
        }
      }
      let trimmed = full.slice(0, lo).replace(/[\\.\\s]+$/, '');
      if (!trimmed) trimmed = full.slice(0, lo);
      el.textContent = trimmed + ellipsis;
    }
    function truncateFooterMeta() {
      const footer = document.querySelector('.footer');
      if (!footer) return;
      const w = footer.clientWidth || 0;
      if (Math.abs(w - __footerTruncLastWidth) < 0.5) return;
      __footerTruncLastWidth = w;
      const nodes = document.querySelectorAll('.meta-value');
      for (let i = 0; i < nodes.length; i++) truncateMetaValue(nodes[i]);
    }
    window.addEventListener('resize', truncateFooterMeta);
  </script>
	</head>
		<body>
			  <div class="page-shell">
				  <div class="page-header">
				    <div class="chrome-left">\(htmlEscape(dateHeader))</div>
				    <div class="chrome-center">\(htmlEscape(authorHeader))</div>
				    <div class="chrome-right">Paper \(clampedIndex)/\(clampedTotal)</div>
					  </div>
				  <div class="title-row">
				    \(imgTag(leftImagePath, isSide: true))
				    <h1 id="titleText"><a class="title-link" href="\(htmlEscape(url))">\(htmlEscape(title))</a></h1>
				    \(imgTag(rightImagePath, isSide: true))
				  </div>
				  \(headerHTML)
				  <div class="header-divider"></div>

		  <div class="content">
		    <div class="abstract-label"><span class="label">Abstract</span></div>
		    <div id="abstractText" class="abstract">\(htmlEscape(abstract))</div>
		  </div>

		  <div class="footer">
		    <div class="footer-left"><span class="label">Comments:</span><span class="meta-value">\(htmlEscape(comments))</span></div>
		    <div class="footer-right"><span class="label">Categories:</span><span class="meta-value">\(htmlEscape(categories))</span></div>
		  </div>

				  <script>
				    try { highlightKeywords(document.getElementById('titleText'), PAPER_KEYWORDS); } catch(e) {}
				    try { highlightKeywords(document.getElementById('abstractText'), PAPER_KEYWORDS); } catch(e) {}
				    try { truncateFooterMeta(); } catch(e) {}
				  </script>
		  </div>
		</body>
		</html>
"""

}
