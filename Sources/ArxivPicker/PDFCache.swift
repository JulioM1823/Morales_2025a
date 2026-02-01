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

// MARK: - PDF Cache
final class PDFCacheManager {
    enum CacheError: Error {
        case badStatus(Int)
        case invalidContentType(String?)
        case invalidPDF
        case missingTempFile
        case fileMoveFailed
        case timeout
        case notEnqueued
    }

    enum LifecycleStage: String {
        case urlKnown = "url-known"
        case prefetchQueued = "prefetch-queued"
        case downloading = "downloading"
        case downloaded = "downloaded"
        case validated = "validated"
        case renderQueued = "render-queued"
        case rendered = "rendered"
        case failed = "failed"
    }

    struct Metadata {
        let url: URL
        let paperIndex: Int?
        let stableID: String?
    }

    struct PrefetchRequest {
        let url: URL
        let metadata: Metadata?
    }

    private struct LifecycleRecord {
        var stage: LifecycleStage
        var timestamp: CFTimeInterval
    }

    struct PreparedPDF {
        let fileURL: URL
        let byteCount: Int64
        let lastModified: Date?
    }

    private struct PendingItem {
        let url: URL
        var priority: Int
        let order: Int
        var callbacks: [(Result<PreparedPDF, Error>) -> Void]
        let attempt: Int
        let resumeData: Data?
        let earliestStart: CFTimeInterval
        let reason: String
    }

    private struct ActiveItem {
        let url: URL
        let priority: Int
        let attempt: Int
        var callbacks: [(Result<PreparedPDF, Error>) -> Void]
        let task: URLSessionDownloadTask
        let startedAt: CFTimeInterval
        let reason: String
        var timeoutWorkItem: DispatchWorkItem?
    }

    private let stateQueue = DispatchQueue(label: "arxiv.pdfcache.state", qos: .utility)
    private let ioQueue = DispatchQueue(label: "arxiv.pdfcache.io", qos: .utility)
    private let ioQueueKey = DispatchSpecificKey<UInt8>()
    private let stateQueueKey = DispatchSpecificKey<UInt8>()
    private let session: URLSession
    private let parentDir: URL
    private let cacheDir: URL
    private let maxConcurrent: Int
    private let maxRetryCount: Int = 3
    private let downloadTimeoutSeconds: TimeInterval = 16.0
    private let debugForceRetryCount: Int
    private var metadataByKey: [String: Metadata] = [:]
    private var lifecycleRecords: [String: LifecycleRecord] = [:]
    private var stageCounters: [LifecycleStage: Int] = [:]

    private var pending: [String: PendingItem] = [:]
    private var active: [String: ActiveItem] = [:]
    private var ready: [String: PreparedPDF] = [:]
    private var failures: [String: Error] = [:]
    private var orderCounter: Int = 0
    private var deferredDrainWorkItem: DispatchWorkItem?

    private var prefetchStartTime: CFTimeInterval?
    private var prefetchSuccessCount: Int = 0
    private var prefetchFailureCount: Int = 0
    private var prefetchBytes: Int64 = 0
    private var prefetchLastLoggedCount: Int = 0
    private var lastSummaryLogTime: CFTimeInterval?
    private var lastFailureMessage: String?

    init() {
        self.maxConcurrent = max(1, PDF_CACHE_MAX_CONCURRENT_DOWNLOADS)
        let fm = FileManager.default
        let base = fm.urls(for: .cachesDirectory, in: .userDomainMask).first ?? fm.temporaryDirectory
        let appDir = base.appendingPathComponent(ProcessInfo.processInfo.processName, isDirectory: true)
        self.parentDir = appDir.appendingPathComponent(PDF_CACHE_DIR_NAME, isDirectory: true)
        self.cacheDir = parentDir
        let rawForceRetry = (ProcessInfo.processInfo.environment["ARXIV_DEBUG_FORCE_RETRY_COUNT"] ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        self.debugForceRetryCount = max(0, Int(rawForceRetry) ?? 0)
        if debugForceRetryCount > 0 {
            NSLog("[PDFEager] debug_force_retry_count=\(debugForceRetryCount)")
        }

        let config = URLSessionConfiguration.default
        config.httpMaximumConnectionsPerHost = maxConcurrent
        config.requestCachePolicy = .reloadIgnoringLocalCacheData
        config.urlCache = nil
        self.session = URLSession(configuration: config)

        ioQueue.setSpecific(key: ioQueueKey, value: 1)
        stateQueue.setSpecific(key: stateQueueKey, value: 1)

        createCacheDirectories()
        purgeOrphanedSessions()

        NSLog("[PDFEager] cache_dir=\(cacheDir.path) concurrent=\(maxConcurrent)")
    }

    deinit {
        session.invalidateAndCancel()
    }

    var sessionDirectory: URL { cacheDir }

    func cacheKey(for url: URL) -> String {
        sha256Hex(url.absoluteString)
    }

    func prefetch(_ requests: [PrefetchRequest], priority: Int, reason: String) {
        enqueue(requests: requests, priority: priority, reason: reason, completion: nil)
    }

    func preparedPDFIfReady(for url: URL) -> PreparedPDF? {
        let key = cacheKey(for: url)
        if let prepared = stateQueue.sync(execute: { ready[key] }) {
            return prepared
        }
        if let prepared = preparedFromDiskIfPresent(forKey: key) {
            stateQueue.async { self.ready[key] = prepared }
            return prepared
        }
        return nil
    }

    func whenPreparedPDF(for url: URL, completion: @escaping (Result<PreparedPDF, Error>) -> Void) {
        let key = cacheKey(for: url)
        if let prepared = preparedFromDiskIfPresent(forKey: key) {
            stateQueue.async { self.ready[key] = prepared }
            DispatchQueue.main.async { completion(.success(prepared)) }
            return
        }
        stateQueue.async { [weak self] in
            guard let self else { return }
            if let prepared = self.ready[key] {
                DispatchQueue.main.async { completion(.success(prepared)) }
                return
            }
            if var activeItem = self.active[key] {
                activeItem.callbacks.append(completion)
                self.active[key] = activeItem
                return
            }
            if var pendingItem = self.pending[key] {
                pendingItem.callbacks.append(completion)
                self.pending[key] = pendingItem
                return
            }
            if let err = self.failures[key] {
                DispatchQueue.main.async { completion(.failure(err)) }
                return
            }
            DispatchQueue.main.async { completion(.failure(CacheError.notEnqueued)) }
        }
    }

    func prune(keepingURLs urls: [URL]) {
        let keepKeys = Set(urls.map { cacheKey(for: $0) })
        ioQueue.async { [cacheDir] in
            let fm = FileManager.default
            let items = (try? fm.contentsOfDirectory(at: cacheDir,
                                                    includingPropertiesForKeys: nil,
                                                    options: [.skipsHiddenFiles])) ?? []
            for url in items where url.pathExtension == "pdf" {
                let key = url.deletingPathExtension().lastPathComponent
                if !keepKeys.contains(key) {
                    try? fm.removeItem(at: url)
                }
            }
        }
    }

    func debugStateDescription(for url: URL) -> String {
        let key = cacheKey(for: url)
        return stateQueue.sync {
            if ready[key] != nil { return "ready" }
            if active[key] != nil { return "downloading" }
            if pending[key] != nil { return "pending" }
            if failures[key] != nil { return "failed" }
            return "unknown"
        }
    }

    func cleanupOnExit(preserveCache: Bool = true) {
        session.invalidateAndCancel()
        stateQueue.sync {
            pending.removeAll()
            active.removeAll()
            ready.removeAll()
            failures.removeAll()
        }
        guard !preserveCache else {
            removePartialFiles()
            return
        }

        let fm = FileManager.default
        let cacheDirPath = cacheDir.path
        let existedBefore = fm.fileExists(atPath: cacheDirPath)
        let removeCacheDir = { [cacheDir] in
            try? FileManager.default.removeItem(at: cacheDir)
        }
        if DispatchQueue.getSpecific(key: ioQueueKey) == 1 {
            removeCacheDir()
        } else {
            ioQueue.sync(execute: removeCacheDir)
        }
        let existsAfter = fm.fileExists(atPath: cacheDirPath)
        NSLog("[PDFEager] cleanup dir=\(cacheDirPath) existed_before=\(existedBefore) exists_after=\(existsAfter)")
    }

    func registerMetadata(_ metadata: Metadata, for url: URL) {
        let key = cacheKey(for: url)
        stateQueue.async {
            self.metadataByKey[key] = metadata
            self.logLifecycleTransition(
                key: key,
                stage: .urlKnown,
                url: url,
                message: "metadata-registered"
            )
        }
    }

    func trackLifecycleStage(_ stage: LifecycleStage,
                             for url: URL,
                             fileURL: URL? = nil,
                             fileSize: Int64? = nil,
                             lastModified: Date? = nil,
                             message: String? = nil) {
        let key = cacheKey(for: url)
        stateQueue.async {
            self.logLifecycleTransition(
                key: key,
                stage: stage,
                url: url,
                fileURL: fileURL,
                fileSize: fileSize,
                lastModified: lastModified,
                message: message
            )
        }
    }

    private func createCacheDirectories() {
        do {
            try FileManager.default.createDirectory(at: parentDir, withIntermediateDirectories: true, attributes: nil)
        } catch {
            NSLog("[PDFEager] cache_dir_create_failed parent=\(parentDir.path) error=\(error)")
        }
        do {
            try FileManager.default.createDirectory(at: cacheDir, withIntermediateDirectories: true, attributes: nil)
        } catch {
            NSLog("[PDFEager] cache_dir_create_failed cache=\(cacheDir.path) error=\(error)")
        }
    }

    private func removePartialFiles() {
        let work = { [cacheDir] in
            let fm = FileManager.default
            let urls = (try? fm.contentsOfDirectory(
                at: cacheDir,
                includingPropertiesForKeys: nil,
                options: [.skipsHiddenFiles]
            )) ?? []
            for url in urls where url.pathExtension == "partial" {
                try? fm.removeItem(at: url)
            }
        }
        if DispatchQueue.getSpecific(key: ioQueueKey) == 1 {
            work()
        } else {
            ioQueue.sync(execute: work)
        }
    }

    private func purgeOrphanedSessions() {
        ioQueue.async { [parentDir, cacheDir] in
            let fm = FileManager.default
            let urls = (try? fm.contentsOfDirectory(
                at: parentDir,
                includingPropertiesForKeys: [.isDirectoryKey],
                options: [.skipsHiddenFiles]
            )) ?? []
            for url in urls {
                guard url != cacheDir else { continue }
                let values = try? url.resourceValues(forKeys: [.isDirectoryKey])
                guard values?.isDirectory == true else { continue }
                try? fm.removeItem(at: url)
            }
        }
    }

    private func cachedFileURL(forKey key: String) -> URL {
        cacheDir.appendingPathComponent(key).appendingPathExtension("pdf")
    }

    private func partialFileURL(forKey key: String) -> URL {
        cacheDir.appendingPathComponent(key).appendingPathExtension("partial")
    }

    private func preparedFromDiskIfPresent(forKey key: String) -> PreparedPDF? {
        let url = cachedFileURL(forKey: key)
        guard FileManager.default.fileExists(atPath: url.path) else { return nil }
        let values = try? url.resourceValues(forKeys: [.fileSizeKey, .contentModificationDateKey])
        let fileSize = Int64(values?.fileSize ?? 0)
        guard fileSize > 0 else { return nil }
        return PreparedPDF(fileURL: url,
                           byteCount: fileSize,
                           lastModified: values?.contentModificationDate)
    }

    private func enqueue(requests: [PrefetchRequest],
                         priority: Int,
                         reason: String,
                         completion: ((Result<PreparedPDF, Error>) -> Void)?) {
        guard !requests.isEmpty else { return }
        stateQueue.async { [weak self] in
            guard let self else { return }

            if self.prefetchStartTime == nil {
                self.prefetchStartTime = monotonicNow()
                NSLog("[PDFEager] metadata_loaded -> eager_download_start count=\(requests.count)")
            }

            for request in requests {
                let url = request.url
                let key = self.cacheKey(for: url)
                if let metadata = request.metadata {
                    self.metadataByKey[key] = metadata
                }
                self.logLifecycleTransition(
                    key: key,
                    stage: .urlKnown,
                    url: url,
                    message: "prefetch-request reason=\(reason)"
                )

                if let prepared = self.preparedFromDiskIfPresent(forKey: key) {
                    self.ready[key] = prepared
                    if let completion {
                        DispatchQueue.main.async { completion(.success(prepared)) }
                    }
                    continue
                }

                if let prepared = self.ready[key] {
                    if let completion {
                        DispatchQueue.main.async { completion(.success(prepared)) }
                    }
                    continue
                }

                if var activeItem = self.active[key] {
                    if let completion { activeItem.callbacks.append(completion) }
                    self.active[key] = activeItem
                    continue
                }

                if var pendingItem = self.pending[key] {
                    if priority < pendingItem.priority { pendingItem.priority = priority }
                    if let completion { pendingItem.callbacks.append(completion) }
                    self.pending[key] = pendingItem
                    continue
                }

                self.failures.removeValue(forKey: key)
                self.orderCounter += 1
                var callbacks: [(Result<PreparedPDF, Error>) -> Void] = []
                if let completion { callbacks.append(completion) }
                let item = PendingItem(
                    url: url,
                    priority: priority,
                    order: self.orderCounter,
                    callbacks: callbacks,
                    attempt: 0,
                    resumeData: nil,
                    earliestStart: 0,
                    reason: reason
                )
                self.pending[key] = item
                self.logLifecycleTransition(
                    key: key,
                    stage: .prefetchQueued,
                    url: url,
                    message: "queued reason=\(reason)"
                )
            }
            self.drainQueueLocked()
        }
    }

    private func drainQueueLocked() {
        deferredDrainWorkItem?.cancel()
        deferredDrainWorkItem = nil

        guard active.count < maxConcurrent else { return }

        let now = monotonicNow()
        var soonestEarliestStart: CFTimeInterval?

        let sortedKeys = pending.keys.sorted { lhs, rhs in
            guard let a = pending[lhs], let b = pending[rhs] else { return false }
            if a.priority != b.priority { return a.priority < b.priority }
            return a.order < b.order
        }

        for key in sortedKeys {
            guard active.count < maxConcurrent else { break }
            guard let item = pending[key] else { continue }
            if item.earliestStart > now {
                soonestEarliestStart = min(soonestEarliestStart ?? item.earliestStart, item.earliestStart)
                continue
            }
            _ = pending.removeValue(forKey: key)
            startDownloadLocked(key: key, item: item)
        }

        if active.count < maxConcurrent, let t = soonestEarliestStart {
            scheduleDeferredDrainLocked(earliestStart: t)
        }
    }

    private func scheduleDeferredDrainLocked(earliestStart: CFTimeInterval) {
        let delay = max(0.02, earliestStart - monotonicNow())
        let work = DispatchWorkItem { [weak self] in
            guard let self else { return }
            self.drainQueueLocked()
        }
        deferredDrainWorkItem = work
        stateQueue.asyncAfter(deadline: .now() + delay, execute: work)
    }

    private func startDownloadLocked(key: String, item: PendingItem) {
        let startedAt = monotonicNow()
        NSLog("[PDFEager] download_start key=\(key.prefix(8)) attempt=\(item.attempt) priority=\(item.priority) reason=\(item.reason)")
        logLifecycleTransition(
            key: key,
            stage: .downloading,
            url: item.url,
            message: "attempt=\(item.attempt) priority=\(item.priority)"
        )

        let completion: (URL?, URLResponse?, Error?) -> Void = { [weak self] location, response, error in
            self?.handleDownloadCompletion(
                key: key,
                url: item.url,
                priority: item.priority,
                attempt: item.attempt,
                startedAt: startedAt,
                location: location,
                response: response,
                error: error,
                callbacks: item.callbacks,
                reason: item.reason
            )
        }

        let task: URLSessionDownloadTask
        if let resumeData = item.resumeData {
            task = session.downloadTask(withResumeData: resumeData, completionHandler: completion)
        } else {
            task = session.downloadTask(with: item.url, completionHandler: completion)
        }

        var activeItem = ActiveItem(
            url: item.url,
            priority: item.priority,
            attempt: item.attempt,
            callbacks: item.callbacks,
            task: task,
            startedAt: startedAt,
            reason: item.reason,
            timeoutWorkItem: nil
        )
        let timeoutWork = DispatchWorkItem { [weak self] in
            guard let self else { return }
            self.handleDownloadTimeout(key: key, url: item.url, startedAt: startedAt)
        }
        activeItem.timeoutWorkItem = timeoutWork
        active[key] = activeItem
        stateQueue.asyncAfter(deadline: .now() + downloadTimeoutSeconds, execute: timeoutWork)
        task.resume()
    }

    private func handleDownloadTimeout(key: String, url: URL, startedAt: CFTimeInterval) {
        guard let activeItem = active[key] else { return }
        activeItem.task.cancel()
        NSLog("[PDFEager] download_timeout key=\(key.prefix(8))")
        finishDownload(
            key: key,
            url: url,
            result: .failure(CacheError.timeout),
            callbacks: activeItem.callbacks,
            startedAt: startedAt
        )
    }

    private func handleDownloadCompletion(key: String,
                                          url: URL,
                                          priority: Int,
                                          attempt: Int,
                                          startedAt: CFTimeInterval,
                                          location: URL?,
                                          response: URLResponse?,
                                          error: Error?,
                                          callbacks: [(Result<PreparedPDF, Error>) -> Void],
                                          reason: String) {
        let work = { [weak self] in
            guard let self else { return }

            let elapsedMs = Int((monotonicNow() - startedAt) * 1000.0)
            let http = response as? HTTPURLResponse

            var effectiveError = error
            if debugForceRetryCount > 0, attempt < debugForceRetryCount {
                if effectiveError == nil {
                    NSLog("[PDFEager] debug_forced_retry key=\(key.prefix(8)) attempt=\(attempt)")
                }
                effectiveError = NSError(
                    domain: NSURLErrorDomain,
                    code: NSURLErrorTimedOut,
                    userInfo: [NSLocalizedDescriptionKey: "debug_forced_retry"]
                )
            }

            if let error = effectiveError {
                let ns = error as NSError
                let resumeData = ns.userInfo[NSURLSessionDownloadTaskResumeData] as? Data
                if self.shouldRetry(error: error, attempt: attempt) {
                    let delay = self.retryDelaySeconds(attempt: attempt)
                    NSLog("[PDFEager] download_retry key=\(key.prefix(8)) attempt=\(attempt + 1) delay=\(String(format: "%.2f", delay)) error=\(error)")
                    self.retryDownload(
                        key: key,
                        url: url,
                        priority: priority,
                        attempt: attempt + 1,
                        resumeData: resumeData,
                        callbacks: callbacks,
                        reason: reason,
                        delaySeconds: delay
                    )
                    return
                }
                NSLog("[PDFEager] download_failed key=\(key.prefix(8)) ms=\(elapsedMs) error=\(error)")
                self.finishDownload(
                    key: key,
                    url: url,
                    result: .failure(error),
                    callbacks: callbacks,
                    startedAt: startedAt
                )
                return
            }

            if let http, !(200...299).contains(http.statusCode) {
                let err = CacheError.badStatus(http.statusCode)
                NSLog("[PDFEager] download_failed key=\(key.prefix(8)) ms=\(elapsedMs) status=\(http.statusCode)")
                self.finishDownload(
                    key: key,
                    url: url,
                    result: .failure(err),
                    callbacks: callbacks,
                    startedAt: startedAt
                )
                return
            }

            guard let location else {
                let err = CacheError.missingTempFile
                NSLog("[PDFEager] download_failed key=\(key.prefix(8)) ms=\(elapsedMs) missing_temp")
                self.finishDownload(
                    key: key,
                    url: url,
                    result: .failure(err),
                    callbacks: callbacks,
                    startedAt: startedAt
                )
                return
            }

            let mimeType = http?.value(forHTTPHeaderField: "Content-Type")
            let mimeOK = pdfMimeTypeLooksValid(mimeType)
            guard let inputHandle = try? FileHandle(forReadingFrom: location) else {
                let err = CacheError.missingTempFile
                NSLog("[PDFEager] download_failed key=\(key.prefix(8)) ms=\(elapsedMs) missing_temp path=\(location.path)")
                self.finishDownload(
                    key: key,
                    url: url,
                    result: .failure(err),
                    callbacks: callbacks,
                    startedAt: startedAt
                )
                return
            }
            defer { try? inputHandle.close() }

            let headerData = inputHandle.readData(ofLength: 5)
            let headerOK = dataHasPDFHeader(headerData)
            guard mimeOK || headerOK else {
                let err = CacheError.invalidContentType(mimeType)
                NSLog("[PDFEager] download_failed key=\(key.prefix(8)) ms=\(elapsedMs) invalid_mime=\(mimeType ?? "nil")")
                self.finishDownload(
                    key: key,
                    url: url,
                    result: .failure(err),
                    callbacks: callbacks,
                    startedAt: startedAt
                )
                return
            }
            guard headerOK else {
                let err = CacheError.invalidPDF
                NSLog("[PDFEager] download_failed key=\(key.prefix(8)) ms=\(elapsedMs) invalid_pdf_header")
                self.finishDownload(
                    key: key,
                    url: url,
                    result: .failure(err),
                    callbacks: callbacks,
                    startedAt: startedAt
                )
                return
            }

            let finalURL = self.cachedFileURL(forKey: key)
            let partialURL = self.partialFileURL(forKey: key)
            self.removeFile(partialURL)
            self.removeFile(finalURL)
            self.createCacheDirectories()

            guard FileManager.default.createFile(atPath: partialURL.path, contents: nil, attributes: nil),
                  let outputHandle = try? FileHandle(forWritingTo: partialURL) else {
                self.removeFile(partialURL)
                self.removeFile(finalURL)
                NSLog("[PDFEager] download_failed key=\(key.prefix(8)) ms=\(elapsedMs) move_failed error=output_create_failed")
                self.finishDownload(
                    key: key,
                    url: url,
                    result: .failure(CacheError.fileMoveFailed),
                    callbacks: callbacks,
                    startedAt: startedAt
                )
                return
            }
            defer { try? outputHandle.close() }

            var fileSize = Int64(headerData.count)
            if !headerData.isEmpty {
                outputHandle.write(headerData)
            }
            let bufferSize = 1 << 20
            while true {
                let chunk = inputHandle.readData(ofLength: bufferSize)
                if chunk.isEmpty { break }
                fileSize += Int64(chunk.count)
                outputHandle.write(chunk)
            }

            do {
                try FileManager.default.moveItem(at: partialURL, to: finalURL)
            } catch {
                self.removeFile(partialURL)
                self.removeFile(finalURL)
                NSLog("[PDFEager] download_failed key=\(key.prefix(8)) ms=\(elapsedMs) move_failed error=\(error)")
                self.finishDownload(
                    key: key,
                    url: url,
                    result: .failure(CacheError.fileMoveFailed),
                    callbacks: callbacks,
                    startedAt: startedAt
                )
                return
            }

            let modified = (try? finalURL.resourceValues(forKeys: [.contentModificationDateKey]))?.contentModificationDate
            self.logLifecycleTransition(
                key: key,
                stage: .downloaded,
                url: url,
                fileURL: finalURL,
                fileSize: fileSize,
                lastModified: modified,
                message: "ms=\(elapsedMs)"
            )

            NSLog("[PDFEager] download_complete key=\(key.prefix(8)) ms=\(elapsedMs) bytes=\(fileSize)")
            let prepared = PreparedPDF(fileURL: finalURL, byteCount: fileSize, lastModified: modified)
            self.finishDownload(
                key: key,
                url: url,
                result: .success(prepared),
                callbacks: callbacks,
                startedAt: startedAt
            )
        }
        if DispatchQueue.getSpecific(key: ioQueueKey) != nil {
            work()
        } else {
            ioQueue.sync(execute: work)
        }
    }

	    private func finishDownload(key: String,
	                                url: URL,
	                                result: Result<PreparedPDF, Error>,
	                                callbacks: [(Result<PreparedPDF, Error>) -> Void],
	                                startedAt: CFTimeInterval) {
	        stateQueue.async { [weak self] in
	            guard let self else { return }
	            let activeItem = self.active.removeValue(forKey: key)
	            activeItem?.timeoutWorkItem?.cancel()
	            let callbacksToFire = activeItem?.callbacks ?? callbacks

	            switch result {
	            case .success(let prepared):
	                self.ready[key] = prepared
	                self.failures.removeValue(forKey: key)
	                self.prefetchSuccessCount += 1
	                self.prefetchBytes += prepared.byteCount
	            case .failure(let error):
	                self.failures[key] = error
	                self.prefetchFailureCount += 1
	                let msg = String(describing: error)
	                self.lastFailureMessage = msg
	                self.logLifecycleTransition(
	                    key: key,
	                    stage: .failed,
	                    url: url,
	                    message: msg
	                )
	            }

	            self.drainQueueLocked()

	            DispatchQueue.main.async {
	                callbacksToFire.forEach { $0(result) }
	            }

	            self.logPrefetchStatsIfNeeded()
	        }
	    }

    private func logPrefetchStatsIfNeeded() {
        let total = prefetchSuccessCount + prefetchFailureCount
        guard total - prefetchLastLoggedCount >= PDF_CACHE_PREFETCH_LOG_EVERY else { return }
        prefetchLastLoggedCount = total

        let elapsed = max(0.1, monotonicNow() - (prefetchStartTime ?? monotonicNow()))
        let mbps = (Double(prefetchBytes) / (1024.0 * 1024.0)) / elapsed
        NSLog("[PDFEager] throughput completed=\(prefetchSuccessCount) failed=\(prefetchFailureCount) rateMBps=\(String(format: "%.2f", mbps))")
    }

    private func shouldRetry(error: Error, attempt: Int) -> Bool {
        guard attempt < maxRetryCount else { return false }
        if error is CacheError { return false }
        let ns = error as NSError
        return ns.domain == NSURLErrorDomain
    }

    private func retryDelaySeconds(attempt: Int) -> TimeInterval {
        let base: TimeInterval = 0.6
        let pow2 = pow(2.0, Double(max(0, attempt)))
        return min(6.0, base * pow2)
    }

	    private func retryDownload(key: String,
	                               url: URL,
	                               priority: Int,
	                               attempt: Int,
	                               resumeData: Data?,
	                               callbacks: [(Result<PreparedPDF, Error>) -> Void],
	                               reason: String,
                                    delaySeconds: TimeInterval) {
        stateQueue.async { [weak self] in
            guard let self else { return }
            // Carry all callbacks currently attached to the active download so none are dropped on retry.
            let callbacksToCarry = self.active.removeValue(forKey: key)?.callbacks ?? callbacks

            self.orderCounter += 1
            let item = PendingItem(
                url: url,
                priority: priority,
                order: self.orderCounter,
                callbacks: callbacksToCarry,
                attempt: attempt,
                resumeData: resumeData,
                earliestStart: monotonicNow() + delaySeconds,
                reason: reason
            )
            self.pending[key] = item
            self.drainQueueLocked()
        }
    }

    private func logLifecycleTransition(key: String,
                                        stage: LifecycleStage,
                                        url: URL,
                                        fileURL: URL? = nil,
                                        fileSize: Int64? = nil,
                                        lastModified: Date? = nil,
                                        message: String? = nil) {
        guard DispatchQueue.getSpecific(key: stateQueueKey) == 1 else {
            stateQueue.async { [weak self] in
                self?.logLifecycleTransition(
                    key: key,
                    stage: stage,
                    url: url,
                    fileURL: fileURL,
                    fileSize: fileSize,
                    lastModified: lastModified,
                    message: message
                )
            }
            return
        }

        let now = monotonicNow()
        let previous = lifecycleRecords[key]
        let deltaMs = previous == nil ? 0 : (now - previous!.timestamp) * 1000.0
        lifecycleRecords[key] = LifecycleRecord(stage: stage, timestamp: now)
        stageCounters[stage, default: 0] += 1

        var components: [String] = []
        components.append("key=\(String(key.prefix(8)))")
        components.append("stage=\(stage.rawValue)")
        components.append("thread=\(Thread.isMainThread ? "main" : "bg")")
        components.append("delta_ms=\(String(format: "%.1f", deltaMs))")
        components.append("url=\(url.absoluteString)")

        if let meta = metadataByKey[key] {
            if let idx = meta.paperIndex {
                components.append("paperIndex=\(idx)")
            }
            if let id = meta.stableID, !id.isEmpty {
                components.append("stableID=\(id)")
            }
        }

        if let localPath = fileURL {
            components.append("local=\"\(localPath.path)\"")
        }
        if let size = fileSize {
            components.append("bytes=\(size)")
        }
        if let modified = lastModified {
            components.append("mtime=\(Int(modified.timeIntervalSince1970))")
        }
        if let note = message {
            components.append("msg=\"\(note)\"")
        }

        NSLog("[PDFLife] \(components.joined(separator: " "))")
        logCacheSummaryIfNeeded()
    }

    private func logCacheSummaryIfNeeded() {
        let now = monotonicNow()
        if let last = lastSummaryLogTime, now - last < 1.5 { return }
        lastSummaryLogTime = now
        let pendingCount = pending.count
        let downloadingCount = active.count
        let readyCount = ready.count
        let queuedTotal = stageCounters[.prefetchQueued] ?? 0
        let downloadedTotal = stageCounters[.downloaded] ?? 0
        let validatedTotal = stageCounters[.validated] ?? 0
        let renderedTotal = stageCounters[.rendered] ?? 0
        let failedTotal = stageCounters[.failed] ?? 0
        let lastError = lastFailureMessage ?? "none"
        NSLog("[PDFEager] cache_summary pending=\(pendingCount) downloading=\(downloadingCount) ready=\(readyCount) queued_total=\(queuedTotal) downloaded_total=\(downloadedTotal) validated_total=\(validatedTotal) rendered_total=\(renderedTotal) failed_total=\(failedTotal) lastError=\(lastError)")
    }

    private func removeFile(_ url: URL) {
        try? FileManager.default.removeItem(at: url)
    }
}
