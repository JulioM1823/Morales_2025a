import Foundation

enum PayloadDecoder {
    static func decode(_ s: String) -> Payload? {
        let t = s.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !t.isEmpty, let data = t.data(using: .utf8) else { return nil }

        if let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let papersArr = obj["papers"] as? [[String: Any]] {
            let keywords = (obj["keywords"] as? [String]) ?? []
            let recipientName = (obj["recipientName"] as? String)
            let recipientEmail = (obj["recipientEmail"] as? String)
            let messageCount = intValue(obj["messageCount"]) ?? 0
            let latestEpoch = numberValue(obj["latestMessageEpoch"])
            let latestMessageDate = latestEpoch.map { Date(timeIntervalSince1970: $0) }

            let papers: [Paper] = papersArr.enumerated().compactMap { i, d in
                guard let title = d["title"] as? String else { return nil }
                let receivedEpoch = numberValue(d["receivedAtEpoch"])
                let receivedAt = receivedEpoch.map { Date(timeIntervalSince1970: $0) }
                return Paper(
                    index: d["index"] as? Int ?? i,
                    title: title,
                    authors: d["authors"] as? String ?? "",
                    categories: d["categories"] as? String ?? "",
                    dateLine: d["dateLine"] as? String ?? "",
                    url: d["url"] as? String ?? "",
                    comments: d["comments"] as? String ?? "",
                    abstractText: d["abstractText"] as? String ?? "",
                    receivedAt: receivedAt
                )
            }

            return Payload(papers: papers,
                           keywords: keywords,
                           recipientName: recipientName,
                           recipientEmail: recipientEmail,
                           messageCount: messageCount,
                           latestMessageDate: latestMessageDate)
        }

        return nil
    }

    private static func numberValue(_ value: Any?) -> Double? {
        if let n = value as? NSNumber { return n.doubleValue }
        if let s = value as? String { return Double(s.trimmingCharacters(in: .whitespacesAndNewlines)) }
        return nil
    }

    private static func intValue(_ value: Any?) -> Int? {
        if let n = value as? NSNumber { return n.intValue }
        if let s = value as? String { return Int(s.trimmingCharacters(in: .whitespacesAndNewlines)) }
        return nil
    }
}
