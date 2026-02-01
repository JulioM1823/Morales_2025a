import Foundation

enum DenverRefreshSchedule {
    private static let timeZone = TimeZone(identifier: "America/Denver") ?? TimeZone.current

    static func nextRefreshDate(after date: Date) -> Date {
        let calendar = makeCalendar()
        let todayTarget = scheduledDate(on: date, calendar: calendar)
        if date < todayTarget {
            return todayTarget
        }
        return calendar.date(byAdding: .day, value: 1, to: todayTarget) ?? todayTarget
    }

    static func lastRefreshDate(before date: Date) -> Date {
        let calendar = makeCalendar()
        let todayTarget = scheduledDate(on: date, calendar: calendar)
        if date >= todayTarget {
            return todayTarget
        }
        return calendar.date(byAdding: .day, value: -1, to: todayTarget) ?? todayTarget
    }

    private static func scheduledDate(on date: Date, calendar: Calendar) -> Date {
        var components = calendar.dateComponents([.year, .month, .day], from: date)
        components.hour = 23
        components.minute = 0
        components.second = 0
        return calendar.date(from: components) ?? date
    }

    private static func makeCalendar() -> Calendar {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = timeZone
        return calendar
    }
}
