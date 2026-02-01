#!/usr/bin/env swift
import Foundation

private func readAPIKey() -> String {
    if let env = ProcessInfo.processInfo.environment["ZOTERO_API_KEY"], !env.isEmpty {
        return env
    }
    FileHandle.standardOutput.write(Data("Enter Zotero API key: ".utf8))
    return readLine() ?? ""
}

private let confusableMap: [UnicodeScalar: String] = [
    "\u{0410}": "A", "\u{0430}": "a",
    "\u{0412}": "B", "\u{0432}": "b",
    "\u{0415}": "E", "\u{0435}": "e",
    "\u{041A}": "K", "\u{043A}": "k",
    "\u{041C}": "M", "\u{043C}": "m",
    "\u{041D}": "H", "\u{043D}": "h",
    "\u{041E}": "O", "\u{043E}": "o",
    "\u{0420}": "P", "\u{0440}": "p",
    "\u{0421}": "C", "\u{0441}": "c",
    "\u{0422}": "T", "\u{0442}": "t",
    "\u{0425}": "X", "\u{0445}": "x",
    "\u{0423}": "Y", "\u{0443}": "y"
]

private let zeroWidthScalars: Set<UnicodeScalar> = [
    "\u{200B}", "\u{200C}", "\u{200D}", "\u{2060}", "\u{FEFF}"
]

private func normalizeKey(_ raw: String) -> (key: String, changed: Bool) {
    var out = ""
    out.reserveCapacity(raw.count)
    var changed = false
    for scalar in raw.unicodeScalars {
        if CharacterSet.whitespacesAndNewlines.contains(scalar) {
            changed = true
            continue
        }
        if scalar.value < 0x20 || scalar.value == 0x7F {
            changed = true
            continue
        }
        if zeroWidthScalars.contains(scalar) {
            changed = true
            continue
        }
        if let mapped = confusableMap[scalar] {
            out.append(mapped)
            changed = true
        } else {
            out.append(String(scalar))
        }
    }
    return (out, changed)
}

private func shouldRetry(status: Int, body: String) -> Bool {
    if status == 401 || status == 403 { return true }
    return body.lowercased().contains("invalid key")
}

private func fetchKeyInfo(apiKey: String) -> (status: Int?, body: String, error: Error?) {
    let url = URL(string: "https://api.zotero.org/keys/current")!
    var request = URLRequest(url: url)
    request.httpMethod = "GET"
    request.setValue("ZoteroConnectivityTest", forHTTPHeaderField: "User-Agent")
    request.setValue("3", forHTTPHeaderField: "Zotero-API-Version")
    request.setValue(apiKey, forHTTPHeaderField: "Zotero-API-Key")

    let sem = DispatchSemaphore(value: 0)
    var status: Int?
    var body = ""
    var err: Error?

    let task = URLSession.shared.dataTask(with: request) { data, response, error in
        defer { sem.signal() }
        if let error {
            err = error
            return
        }
        guard let http = response as? HTTPURLResponse else {
            return
        }
        status = http.statusCode
        if let data, !data.isEmpty {
            body = String(data: data, encoding: .utf8) ?? "<non-utf8 response>"
        }
    }
    task.resume()
    _ = sem.wait(timeout: .now() + 30)
    return (status, body, err)
}

let rawInput = readAPIKey()
let trimmed = rawInput.trimmingCharacters(in: .whitespacesAndNewlines)
if trimmed.isEmpty {
    fputs("Missing API key. Set ZOTERO_API_KEY or paste when prompted.\n", stderr)
    exit(1)
}

let normalized = normalizeKey(rawInput)
var candidates: [(mode: String, key: String)] = [("raw", trimmed)]
if normalized.changed, normalized.key != trimmed {
    candidates.append(("normalized", normalized.key))
}

for (idx, candidate) in candidates.enumerated() {
    let result = fetchKeyInfo(apiKey: candidate.key)
    if let error = result.error {
        fputs("Request error: \(error)\n", stderr)
        exit(1)
    }
    let status = result.status ?? -1
    print("HTTP \(status) (\(candidate.mode))")
    if !result.body.isEmpty {
        print(result.body)
    }
    if !(idx + 1 < candidates.count && shouldRetry(status: status, body: result.body)) {
        break
    }
    print("Retrying with normalized key...")
}
