import Foundation
import os

final class PublicationCacheStore {
    static let shared = PublicationCacheStore()
    static let schemaVersion = 1
    static let defaultLookbackDays = 60

    struct CacheState: Codable, Equatable {
        var lastScanAt: Date? = nil
        var lastScanMessageDate: Date? = nil
        var lastRefreshAttemptAt: Date? = nil
        var lastRefreshSuccessAt: Date? = nil
    }

    struct Snapshot: Codable {
        var schemaVersion: Int
        var savedAt: Date
        var lookbackDays: Int
        var state: CacheState
        var keywords: [String]
        var recipientName: String?
        var recipientEmail: String?
        var papers: [Paper]
    }

    private let log = Logger(subsystem: APP_LOG_SUBSYSTEM, category: "publication-cache")
    private let lock = NSLock()
    private var cached: Snapshot?
    private var loaded = false
    private let fileURL: URL

    private init() {
        self.fileURL = Self.defaultFileURL()
    }

    func cachedPayload() -> Payload? {
        guard let snapshot = loadSnapshot() else { return nil }
        let now = Date()
        let pruned = prunePapers(snapshot.papers,
                                 lookbackDays: snapshot.lookbackDays,
                                 now: now)
        if pruned.count != snapshot.papers.count {
            let updated = update { snap in
                snap.papers = reindex(pruned)
            }
            return payload(from: updated)
        }
        return payload(from: snapshot)
    }

    func cachedState() -> CacheState {
        loadSnapshot()?.state ?? CacheState()
    }

    func recordRefreshAttempt(_ date: Date) {
        _ = update { snapshot in
            snapshot.state.lastRefreshAttemptAt = date
        }
    }

    @discardableResult
    func refreshWithoutScan(at date: Date) -> Snapshot {
        update { snapshot in
            snapshot.state.lastRefreshAttemptAt = date
            snapshot.state.lastRefreshSuccessAt = date
            let pruned = prunePapers(snapshot.papers,
                                     lookbackDays: snapshot.lookbackDays,
                                     now: date)
            snapshot.papers = reindex(pruned)
        }
    }

    func applyScanPayload(_ payload: Payload,
                          scannedAt: Date,
                          lookbackDays: Int) -> Snapshot {
        update { snapshot in
            let effectiveLookback = max(1, lookbackDays)
            snapshot.lookbackDays = effectiveLookback
            snapshot.state.lastScanAt = scannedAt
            snapshot.state.lastRefreshAttemptAt = scannedAt
            snapshot.state.lastRefreshSuccessAt = scannedAt
            if let latest = payload.latestMessageDate {
                if let existing = snapshot.state.lastScanMessageDate {
                    snapshot.state.lastScanMessageDate = max(existing, latest)
                } else {
                    snapshot.state.lastScanMessageDate = latest
                }
            }
            if !payload.keywords.isEmpty {
                snapshot.keywords = payload.keywords
            }
            if let name = payload.recipientName?.trimmingCharacters(in: .whitespacesAndNewlines),
               !name.isEmpty {
                snapshot.recipientName = name
            }
            if let email = payload.recipientEmail?.trimmingCharacters(in: .whitespacesAndNewlines),
               !email.isEmpty {
                snapshot.recipientEmail = email
            }
            let merged = mergePapers(existing: snapshot.papers, new: payload.papers)
            let pruned = prunePapers(merged, lookbackDays: effectiveLookback, now: scannedAt)
            snapshot.papers = reindex(pruned)
        }
    }

    // MARK: - Snapshot access

    private func loadSnapshot() -> Snapshot? {
        lock.lock()
        if !loaded {
            cached = readFromDisk()
            loaded = true
        }
        let snapshot = cached
        lock.unlock()
        return snapshot
    }

    @discardableResult
    private func update(_ mutate: (inout Snapshot) -> Void) -> Snapshot {
        let snapshot: Snapshot
        lock.lock()
        if !loaded {
            cached = readFromDisk()
            loaded = true
        }
        var next = cached ?? Self.emptySnapshot()
        mutate(&next)
        next.savedAt = Date()
        cached = next
        snapshot = next
        lock.unlock()
        writeToDisk(snapshot)
        return snapshot
    }

    private static func emptySnapshot() -> Snapshot {
        Snapshot(schemaVersion: schemaVersion,
                 savedAt: Date(),
                 lookbackDays: defaultLookbackDays,
                 state: CacheState(),
                 keywords: [],
                 recipientName: nil,
                 recipientEmail: nil,
                 papers: [])
    }

    private func payload(from snapshot: Snapshot) -> Payload {
        Payload(papers: snapshot.papers,
                keywords: snapshot.keywords,
                recipientName: snapshot.recipientName,
                recipientEmail: snapshot.recipientEmail,
                messageCount: 0,
                latestMessageDate: snapshot.state.lastScanMessageDate)
    }

    // MARK: - Persistence

    private static func defaultFileURL() -> URL {
        let fm = FileManager.default
        let base = fm.urls(for: .applicationSupportDirectory, in: .userDomainMask).first ?? fm.temporaryDirectory
        let dir = base.appendingPathComponent("AstroStack", isDirectory: true)
        return dir.appendingPathComponent("publication-cache.json")
    }

    private func readFromDisk() -> Snapshot? {
        do {
            let data = try Data(contentsOf: fileURL)
            let decoder = JSONDecoder()
            decoder.dateDecodingStrategy = .secondsSince1970
            let decoded = try decoder.decode(Snapshot.self, from: data)
            guard decoded.schemaVersion == Self.schemaVersion else {
                log.error("publication cache schema mismatch: \(decoded.schemaVersion, privacy: .public)")
                return nil
            }
            return decoded
        } catch {
            return nil
        }
    }

    private func writeToDisk(_ snapshot: Snapshot) {
        let fm = FileManager.default
        let dir = fileURL.deletingLastPathComponent()
        do {
            try fm.createDirectory(at: dir, withIntermediateDirectories: true, attributes: nil)
            let encoder = JSONEncoder()
            encoder.dateEncodingStrategy = .secondsSince1970
            if #available(macOS 10.13, *) {
                encoder.outputFormatting = [.sortedKeys]
            }
            let data = try encoder.encode(snapshot)
            try data.write(to: fileURL, options: [.atomic])
        } catch {
            log.error("publication cache write failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    // MARK: - Merge + prune

    private func mergePapers(existing: [Paper], new: [Paper]) -> [Paper] {
        guard !new.isEmpty else { return existing }
        var seen = Set<String>()
        var merged: [Paper] = []
        var existingByKey: [String: Paper] = [:]
        existing.forEach { existingByKey[$0.stableKey] = $0 }

        for paper in new {
            let key = paper.stableKey
            let mergedPaper: Paper
            if let prior = existingByKey[key] {
                mergedPaper = mergePaper(prior, with: paper)
            } else {
                mergedPaper = paper
            }
            merged.append(mergedPaper)
            seen.insert(key)
        }

        for paper in existing where !seen.contains(paper.stableKey) {
            merged.append(paper)
        }
        return merged
    }

    private func mergePaper(_ existing: Paper, with incoming: Paper) -> Paper {
        let receivedAt = incoming.receivedAt ?? existing.receivedAt
        return Paper(index: incoming.index,
                     title: incoming.title.isEmpty ? existing.title : incoming.title,
                     authors: incoming.authors.isEmpty ? existing.authors : incoming.authors,
                     categories: incoming.categories.isEmpty ? existing.categories : incoming.categories,
                     dateLine: incoming.dateLine.isEmpty ? existing.dateLine : incoming.dateLine,
                     url: incoming.url.isEmpty ? existing.url : incoming.url,
                     comments: incoming.comments.isEmpty ? existing.comments : incoming.comments,
                     abstractText: incoming.abstractText.isEmpty ? existing.abstractText : incoming.abstractText,
                     receivedAt: receivedAt)
    }

    private func prunePapers(_ papers: [Paper], lookbackDays: Int, now: Date) -> [Paper] {
        let cutoff = now.addingTimeInterval(TimeInterval(-lookbackDays * 24 * 60 * 60))
        return papers.filter { paper in
            if let received = paper.receivedAt {
                return received >= cutoff
            }
            if let parsed = parseDateFromDateLine(paper.dateLine) {
                return parsed >= cutoff
            }
            return false
        }
    }

    private func reindex(_ papers: [Paper]) -> [Paper] {
        papers.enumerated().map { idx, paper in
            paper.withIndex(idx)
        }
    }

    private func parseDateFromDateLine(_ raw: String) -> Date? {
        let pattern = #"\b(\d{4}-\d{2}-\d{2})\b"#
        guard let re = try? NSRegularExpression(pattern: pattern, options: []),
              let match = re.firstMatch(in: raw, options: [], range: NSRange(raw.startIndex..<raw.endIndex, in: raw)),
              let range = Range(match.range(at: 1), in: raw) else {
            return nil
        }
        let text = String(raw[range])
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.date(from: text)
    }
}
