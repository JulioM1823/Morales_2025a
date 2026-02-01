(*
arXiv digest browser (Mail -> keyword filter -> robust multi-line metadata parse)
Standalone scan script: returns payload JSON for the app to consume.
*)

use framework "Foundation"
use framework "AppKit"
use scripting additions

property TARGET_ACCOUNT_NAME : "Exchange"
property TARGET_SENDER_EMAIL : "no-reply@arXiv.org"
property KEYWORDS : {"gravity waves", "gravity wave", "buoyancy waves", "buoyancy wave", "atmospheric gravity wave", "atmospheric gravity waves", "agw", "agws", "acoustic", "oscillation", "oscillations", "wave", "waves", "alfven"}
property DEBUG : false
property PROFILE : false
property DEBUG_LOG_PATH : "/tmp/arxiv_debug.log"
property LOOKBACK_DAYS : 60
property MAIL_TOTAL_TIMEOUT_SECONDS : 180
property MAIL_LAUNCH_TIMEOUT_SECONDS : 15
property MAILBOX_TIMEOUT_SECONDS : 25
property MAIL_MESSAGE_TIMEOUT_SECONDS : 20
property MAIL_RECIPIENT_TIMEOUT_SECONDS : 10
property MAIL_RETRY_MAX : 2
property MAIL_RETRY_BASE_DELAY : 0.6

property _whitespaceSet : missing value
property _regexCollapseWS : missing value
property _regexPipeBreak : missing value
property _regexControlChars : missing value
property _regexDoi : missing value
property _regexArxivIdNew : missing value
property _regexArxivIdOld : missing value
property _regexArxivURL : missing value
property _punctuationSet : missing value
property _dateFormatter : missing value
property _perfStartDate : missing value
property _fileManager : missing value
property _scanDeadline : missing value

set DEBUG to (my envVar("ARXIV_MAIL_DEBUG")) is "1"
set PROFILE to (my envVar("ARXIV_MAIL_PROFILE")) is "1"
set _envLogPath to my envVar("ARXIV_MAIL_DEBUG_LOG")
if _envLogPath is not "" then set DEBUG_LOG_PATH to _envLogPath

set _envLookback to my envVar("ARXIV_MAIL_LOOKBACK_DAYS")
if _envLookback is not "" then
	try
		set _days to _envLookback as integer
		if _days > 0 then set LOOKBACK_DAYS to _days
	on error
		-- Keep default LOOKBACK_DAYS on parse error.
	end try
end if

set _envKeywords to my envVar("ARXIV_MAIL_KEYWORDS")
if _envKeywords is not "" then
	set KEYWORDS to my parseKeywordsFromText(_envKeywords)
end if

set modeText to my envVar("ARXIV_MAIL_MODE")
set CHECK_ONLY to (modeText as text) is "check"
set sinceEpochText to my envVar("ARXIV_MAIL_SINCE_EPOCH")
set sinceDate to missing value
if sinceEpochText is not "" then
	try
		set sinceEpoch to sinceEpochText as real
		if sinceEpoch > 0 then set sinceDate to my dateFromEpochSeconds(sinceEpoch)
	on error
		set sinceDate to missing value
	end try
end if

set _runParserTests to false
try
	set _envTest to current application's NSProcessInfo's processInfo()'s environment()'s objectForKey:("ARXIV_TEST")
	if _envTest is not missing value then set _runParserTests to (_envTest as text) is "1"
on error
	set _runParserTests to false
end try

if _runParserTests then
	return my runParserTests()
end if

if DEBUG then my debugLog("=== run start ===")
my perfLog("run start")

-- =========================
-- Scan Mail and build payload
-- =========================
my perfLog("mail scan start")

set matches to {}
set mailboxCount to 0
set candidateCount to 0
set matchCount to 0
set mailboxFailures to 0
set _scanDeadline to (my currentDateValue()) + MAIL_TOTAL_TIMEOUT_SECONDS

my ensureMailRunning()

tell application "Mail"
	-- Scan window: last LOOKBACK_DAYS days
	set nowDate to my currentDateValue()
	set cutoffDate to nowDate - (LOOKBACK_DAYS * days)
	set effectiveCutoff to cutoffDate
	set includeEqual to true
	if sinceDate is not missing value then
		if sinceDate > effectiveCutoff then set effectiveCutoff to sinceDate
		set includeEqual to false
	end if

	-- Locate account (with retry)
	set theAccount to missing value
	repeat with attempt from 1 to MAIL_RETRY_MAX
		try
			with timeout of MAILBOX_TIMEOUT_SECONDS seconds
				repeat with a in accounts
					if (name of a as text) is TARGET_ACCOUNT_NAME then
						set theAccount to a
						exit repeat
					end if
				end repeat
			end timeout
			exit repeat
		on error errMsg number errNum
			set theAccount to missing value
			my debugLog("Account lookup failed (" & errNum & "): " & errMsg)
			my ensureMailRunning()
			my backoffDelay(attempt)
		end try
	end repeat
	if theAccount is missing value then error "Could not find a Mail account named: " & TARGET_ACCOUNT_NAME

	my debugLog("Found account: " & TARGET_ACCOUNT_NAME)
	my debugAlert("Mail", "Found account: " & TARGET_ACCOUNT_NAME)
	set globalQueryOK to false
	set globalCandidates to {}
	try
		with timeout of MAILBOX_TIMEOUT_SECONDS seconds
			if includeEqual then
				set globalCandidates to (messages whose sender contains TARGET_SENDER_EMAIL and date received is greater than or equal to effectiveCutoff)
			else
				set globalCandidates to (messages whose sender contains TARGET_SENDER_EMAIL and date received is greater than effectiveCutoff)
			end if
		end timeout
		set globalQueryOK to true
	on error errMsg number errNum
		my debugLog("Global message query failed (" & errNum & "): " & errMsg)
	end try

	if globalQueryOK then
		set mailboxCount to 1
		set mailboxFailures to 0
		set cCount to count of globalCandidates
		set candidateCount to cCount
		my perfLog("global query candidates=" & cCount)
		my debugLog("global query candidates=" & cCount)

		repeat with i from 1 to cCount
			if my scanDeadlineExceeded() then error "Mail scan exceeded time limit."
			set m to item i of globalCandidates
			try
				set recDate to date received of m
				set recDate to recDate as date
				if includeEqual then
					if recDate is greater than or equal to effectiveCutoff then
						if TARGET_ACCOUNT_NAME is not "" then
							set mb to mailbox of m
							set acc to account of mb
							if acc is not missing value then
								if (name of acc as text) is TARGET_ACCOUNT_NAME then
									set end of matches to {msg:m, recDate:recDate}
									set matchCount to matchCount + 1
								end if
							end if
						else
							set end of matches to {msg:m, recDate:recDate}
							set matchCount to matchCount + 1
						end if
					end if
				else
					if recDate is greater than effectiveCutoff then
						if TARGET_ACCOUNT_NAME is not "" then
							set mb to mailbox of m
							set acc to account of mb
							if acc is not missing value then
								if (name of acc as text) is TARGET_ACCOUNT_NAME then
									set end of matches to {msg:m, recDate:recDate}
									set matchCount to matchCount + 1
								end if
							end if
						else
							set end of matches to {msg:m, recDate:recDate}
							set matchCount to matchCount + 1
						end if
					end if
				end if
			on error errMsg number errNum
				set msgSummary to my safeMessageSummary(m)
				my debugError("Message scan error", "global", msgSummary, errNum, errMsg)
			end try
		end repeat
	end if

	if globalQueryOK is false then

	-- Collect mailboxes with retry
	set accountMailboxes to {}
	repeat with attempt from 1 to MAIL_RETRY_MAX
		try
			with timeout of MAILBOX_TIMEOUT_SECONDS seconds
				set accountMailboxes to mailboxes of theAccount
			end timeout
			exit repeat
		on error errMsg number errNum
			set accountMailboxes to {}
			my debugLog("Mailbox enumeration failed (" & errNum & "): " & errMsg)
			my ensureMailRunning()
			my backoffDelay(attempt)
		end try
	end repeat
	if accountMailboxes is {} then error "Failed to enumerate Mail mailboxes."

	-- Collect candidate messages (last 60 days)
	-- We avoid date comparisons inside whose clauses and keep "date received" on a single line.
	repeat with mb in accountMailboxes
		if my scanDeadlineExceeded() then error "Mail scan exceeded time limit."
		set mailboxCount to mailboxCount + 1

		set mbName to ""
		try
			set mbName to name of mb
		end try

		set useManualSenderFilter to false
		set candidates to {}
		set cCount to 0
		set mailboxOK to false

		repeat with attempt from 1 to MAIL_RETRY_MAX
			if my scanDeadlineExceeded() then exit repeat
			try
				with timeout of MAILBOX_TIMEOUT_SECONDS seconds
					if useManualSenderFilter then
						try
							if includeEqual then
								set candidates to (messages of mb whose date received is greater than or equal to effectiveCutoff)
							else
								set candidates to (messages of mb whose date received is greater than effectiveCutoff)
							end if
						on error
							set candidates to messages of mb
						end try
					else
						if includeEqual then
							set candidates to (messages of mb whose sender contains TARGET_SENDER_EMAIL and date received is greater than or equal to effectiveCutoff)
						else
							set candidates to (messages of mb whose sender contains TARGET_SENDER_EMAIL and date received is greater than effectiveCutoff)
						end if
					end if
					set cCount to count of candidates
				end timeout
				set mailboxOK to true
				exit repeat
			on error errMsg number errNum
				if my isTimeoutError(errNum, errMsg) then
					my debugLog("Mailbox scan timeout for " & mbName & " (" & errNum & "): " & errMsg & " attempt=" & attempt)
					my ensureMailRunning()
					my backoffDelay(attempt)
				else
					if useManualSenderFilter is false then
						set useManualSenderFilter to true
						my debugLog("Whose filter failed for mailbox " & mbName & " (" & errNum & "): " & errMsg & ". Falling back to manual sender check.")
					else
						my debugLog("Mailbox scan failed for " & mbName & " (" & errNum & "): " & errMsg)
						exit repeat
					end if
				end if
			end try
		end repeat

		if mailboxOK is false then
			set mailboxFailures to mailboxFailures + 1
		else
			my perfLog("mailbox scanned: " & mbName & " candidates=" & cCount & " manual=" & useManualSenderFilter)
			my debugLog("mailbox scanned: " & mbName & " candidates=" & cCount & " manual=" & useManualSenderFilter)
			if useManualSenderFilter is false then
				set candidateCount to candidateCount + cCount
			end if

			if cCount > 0 then
				set recDatesOK to false
				set recDates to {}
				try
					with timeout of MAILBOX_TIMEOUT_SECONDS seconds
						set recDates to date received of candidates
						set recDatesOK to true
					end timeout
				on error errMsg number errNum
					my debugLog("Batch date received failed for mailbox " & mbName & " (" & errNum & "): " & errMsg & ". Falling back to per-message date.")
				end try

				set sendersOK to false
				set senderList to {}
				if useManualSenderFilter then
					try
						with timeout of MAILBOX_TIMEOUT_SECONDS seconds
							set senderList to sender of candidates
							set sendersOK to true
						end timeout
					on error errMsg number errNum
						my debugLog("Batch sender failed for mailbox " & mbName & " (" & errNum & "): " & errMsg & ". Falling back to per-message sender.")
					end try
				end if

				repeat with i from 1 to cCount
					if my scanDeadlineExceeded() then exit repeat
					set m to missing value
					try
						set m to item i of candidates
						if recDatesOK then
							set recDate to item i of recDates
						else
							set recDate to date received of m
						end if
						set recDate to recDate as date

						if includeEqual then
							if recDate is greater than or equal to effectiveCutoff then
								if useManualSenderFilter then
									if sendersOK then
										set senderText to item i of senderList
									else
										set senderText to sender of m
									end if
									if senderText does not contain TARGET_SENDER_EMAIL then
										-- skip
									else
										set candidateCount to candidateCount + 1
										set end of matches to {msg:m, recDate:recDate}
										set matchCount to matchCount + 1
									end if
								else
									set end of matches to {msg:m, recDate:recDate}
									set matchCount to matchCount + 1
								end if
							end if
						else
							if recDate is greater than effectiveCutoff then
								if useManualSenderFilter then
									if sendersOK then
										set senderText to item i of senderList
									else
										set senderText to sender of m
									end if
									if senderText does not contain TARGET_SENDER_EMAIL then
										-- skip
									else
										set candidateCount to candidateCount + 1
										set end of matches to {msg:m, recDate:recDate}
										set matchCount to matchCount + 1
									end if
								else
									set end of matches to {msg:m, recDate:recDate}
									set matchCount to matchCount + 1
								end if
							end if
						end if
					on error errMsg number errNum
						set msgSummary to my safeMessageSummary(m)
						my debugError("Message scan error", mbName, msgSummary, errNum, errMsg)
					end try
				end repeat
			end if
		end if
	end repeat
	end if
end tell

my debugLog("Mailboxes scanned: " & mailboxCount)
my debugAlert("Mail", "Mailboxes scanned: " & mailboxCount)
my debugLog("Mailbox failures: " & mailboxFailures)
my debugAlert("Mail", "Mailbox failures: " & mailboxFailures)
my debugLog("Candidate count: " & candidateCount)
my debugAlert("Mail", "Candidate count: " & candidateCount)
my debugLog("Match count: " & matchCount)
my debugAlert("Mail", "Match count: " & matchCount)
my perfLog("mail scan end: matches=" & matchCount)

set recipientName to ""
set recipientEmail to ""
set papers to {}
set matchesSorted to {}
set latestMessageEpoch to missing value

if matchCount is not 0 then
	set matchesSorted to my sortRecordsByDateDesc(matches)
	set firstRec to item 1 of matchesSorted
	set latestMessageEpoch to my epochSecondsFromDate(firstRec's recDate)

	if CHECK_ONLY is false then
		-- Capture recipient (To:) name/address for downstream email template.
		-- Best-effort: if unavailable, keep empty strings.
		set recipientLoaded to false
		repeat with attempt from 1 to MAIL_RETRY_MAX
			try
				with timeout of MAIL_RECIPIENT_TIMEOUT_SECONDS seconds
					tell application "Mail"
						set toList to |to recipients| of (firstRec's msg)
						if (count of toList) > 0 then
							set r to item 1 of toList
							try
								set recipientName to (name of r as text)
							end try
							try
								set recipientEmail to (address of r as text)
							end try
						end if
					end tell
				end timeout
				set recipientLoaded to true
				exit repeat
			on error errMsg number errNum
				if my isTimeoutError(errNum, errMsg) then
					my ensureMailRunning()
					my backoffDelay(attempt)
				else
					exit repeat
				end if
			end try
		end repeat

		-- Parse each arXiv email we found and accumulate matching papers.
		my perfLog("parse start")
		set keywordLowerList to my lowercasedList(KEYWORDS)
		repeat with rec in matchesSorted
			set recEpoch to my epochSecondsFromDate(rec's recDate)
			set rawBodyContent to missing value
			my perfLog("message body load start")
			set bodyLoaded to false
			repeat with attempt from 1 to MAIL_RETRY_MAX
				try
					with timeout of MAIL_MESSAGE_TIMEOUT_SECONDS seconds
						tell application "Mail"
							set rawBodyContent to content of (rec's msg)
						end tell
					end timeout
					set bodyLoaded to true
					exit repeat
				on error errMsg number errNum
					if my isTimeoutError(errNum, errMsg) then
						my ensureMailRunning()
						my backoffDelay(attempt)
					else
						my debugError("Message body load error", missing value, my safeMessageSummary(rec's msg), errNum, errMsg)
						exit repeat
					end if
				end try
			end repeat
			if bodyLoaded is false and rawBodyContent is not missing value then
				-- Ensure we do not log stale content.
				set rawBodyContent to missing value
			end if
			my perfLog("message body load end")

			if rawBodyContent is missing value then
				-- Skip messages we failed to read.
			else
				set normalizedBody to my normalizeNewlines(rawBodyContent as text)
				
				if my looksLikeHTML(normalizedBody) then
					if DEBUG then my debugLog("[parse] HTML body detected")
					try
						set htmlPapers to my parseArxivHTMLDocument(normalizedBody)
						repeat with p in htmlPapers
							set hay to my keywordHaystack(p)
							if my blockMatchesKeywords(hay, keywordLowerList) then
								set p to p & {receivedAtEpoch:recEpoch}
								set end of papers to p
							end if
						end repeat
					on error errMsg number errNum
						my debugLog("[parse] HTML parse error " & errNum & ": " & errMsg)
					end try
				else
					set normalizedBody to my stripInjectedBanner(normalizedBody)
					set normalizedBody to my stripFooter(normalizedBody)

					set entryBlocks to my splitIntoArxivBlocks(normalizedBody)
					repeat with b in entryBlocks
						try
							set bt to (b as text)
							if my blockMatchesKeywords(bt, keywordLowerList) then
								set p to my parseArxivEntryMultiLine(bt)
								if p is not missing value then
									set p to p & {receivedAtEpoch:recEpoch}
									set end of papers to p
								end if
							end if
						on error errMsg number errNum
							my debugLog("[parse] block error " & errNum & ": " & errMsg & " | snippet=" & my debugSnippet(b as text))
						end try
					end repeat
				end if
			end if
		end repeat
		my perfLog("parse end: papers=" & (count of papers))
	else
		my perfLog("parse skipped: check-only")
	end if
else
	my perfLog("parse skipped: no matches")
end if

-- =========================
-- Build wrapper payload JSON
--   { "keywords": [...], "papers": [ {...}, ... ] }
-- =========================

-- keywords array
set keywordsJSON to "["
set kN to count of KEYWORDS
repeat with i from 1 to kN
	set keywordsJSON to keywordsJSON & my jsonString(item i of KEYWORDS as text)
	if i < kN then set keywordsJSON to keywordsJSON & ","
end repeat
set keywordsJSON to keywordsJSON & "]"

-- papers array
set papersJSON to "["
set n to count of papers
repeat with i from 1 to n
	set p to item i of papers
	
	set obj to "{"
	set obj to obj & "\"index\":" & ((i - 1) as text) & ","
	set obj to obj & "\"title\":" & my jsonString(p's title) & ","
	set obj to obj & "\"authors\":" & my jsonString(p's authors) & ","
	set obj to obj & "\"categories\":" & my jsonString(p's categories) & ","
	set obj to obj & "\"dateLine\":" & my jsonString(p's dateLine) & ","
	set obj to obj & "\"url\":" & my jsonString(p's URL) & ","
	set obj to obj & "\"comments\":" & my jsonString(p's comments) & ","
	set obj to obj & "\"doi\":" & my jsonString(p's doi) & ","
	set obj to obj & "\"abstractText\":" & my jsonString(p's abstractText) & ","
	set obj to obj & "\"receivedAtEpoch\":" & my jsonNumberOrNull(p's receivedAtEpoch)
	set obj to obj & "}"
	
	set papersJSON to papersJSON & obj
	if i < n then set papersJSON to papersJSON & ","
end repeat
set papersJSON to papersJSON & "]"

set payloadJSON to "{"
set payloadJSON to payloadJSON & "\"keywords\":" & keywordsJSON & ","
set payloadJSON to payloadJSON & "\"recipientName\":" & my jsonString(recipientName) & ","
set payloadJSON to payloadJSON & "\"recipientEmail\":" & my jsonString(recipientEmail) & ","
set payloadJSON to payloadJSON & "\"messageCount\":" & (matchCount as text) & ","
set payloadJSON to payloadJSON & "\"latestMessageEpoch\":" & my jsonNumberOrNull(latestMessageEpoch) & ","
set payloadJSON to payloadJSON & "\"papers\":" & papersJSON
set payloadJSON to payloadJSON & "}"

return payloadJSON

-- =====================================================================
-- Helpers
-- =====================================================================

on currentNSDate()
	return current application's NSDate's |date|()
end currentNSDate

on currentDateValue()
	return (my currentNSDate()) as date
end currentDateValue

on scanDeadlineExceeded()
	if _scanDeadline is missing value then return false
	return (my currentDateValue()) > _scanDeadline
end scanDeadlineExceeded

on backoffDelay(attempt)
	try
		set delaySec to (MAIL_RETRY_BASE_DELAY as real) * (attempt as real)
		if delaySec > 0 then delay delaySec
	end try
end backoffDelay

on isTimeoutError(errNum, errMsg)
	if errNum is -1712 then return true
	try
		if (errMsg as text) contains "timed out" then return true
	end try
	return false
end isTimeoutError

on ensureMailRunning()
	try
		with timeout of MAIL_LAUNCH_TIMEOUT_SECONDS seconds
			tell application "Mail" to launch
		end timeout
		delay 0.4
	on error
		-- ignore; Mail may already be running or automation may be denied.
	end try
end ensureMailRunning

on sortRecordsByDateDesc(recList)
	set sortedList to recList
	set n to count of sortedList
	repeat with i from 1 to (n - 1)
		set maxIdx to i
		set maxDate to recDate of item i of sortedList
		repeat with j from (i + 1) to n
			set d to recDate of item j of sortedList
			if d > maxDate then
				set maxIdx to j
				set maxDate to d
			end if
		end repeat
		if maxIdx is not i then
			set tmp to item i of sortedList
			set item i of sortedList to item maxIdx of sortedList
			set item maxIdx of sortedList to tmp
		end if
	end repeat
	return sortedList
end sortRecordsByDateDesc

on debugLog(msg)
	if DEBUG is false then return
	set ts to my timestamp()
	set lineText to ts & " " & msg
	my appendLog(lineText)
end debugLog

on debugSnippet(textValue)
	set t to textValue as text
	set t to my trimText(t)
	if (length of t) > 240 then
		return (text 1 thru 240 of t) & "..."
	end if
	return t
end debugSnippet

on debugAlert(titleText, msgText)
	if DEBUG is false then return
	try
		my debugLog(titleText & " | " & msgText)
	end try
end debugAlert

on debugError(contextText, mailboxName, messageSummary, errNum, errMsg)
	set safeMailbox to mailboxName
	if safeMailbox is missing value then set safeMailbox to ""
	set safeMessage to messageSummary
	if safeMessage is missing value then set safeMessage to ""
	set lineText to contextText & " | mailbox=" & (safeMailbox as text) & " | " & (safeMessage as text) & " | " & errNum & ": " & errMsg
	my debugLog(lineText)
	my debugAlert(contextText, "Mailbox: " & (safeMailbox as text) & return & (safeMessage as text) & return & errNum & ": " & errMsg)
end debugError

on safeMessageSummary(m)
	try
		with timeout of MAIL_MESSAGE_TIMEOUT_SECONDS seconds
			tell application "Mail"
				set subj to subject of m
				set msgId to id of m
			end tell
		end timeout
		return "subject=" & subj & ", id=" & msgId
	on error
		return "(message info unavailable)"
	end try
end safeMessageSummary

on perfLog(labelText)
	if PROFILE is false then return
	if _perfStartDate is missing value then set _perfStartDate to my currentDateValue()
	set deltaSec to (my currentDateValue()) - _perfStartDate
	set lineText to my timestamp() & " [perf +" & my formatSeconds(deltaSec) & "s] " & labelText
	my appendLog(lineText)
end perfLog

on formatSeconds(x)
	return (round (x * 1000) / 1000) as text
end formatSeconds

on timestamp()
	set df to my dateFormatter()
	return (df's stringFromDate:(my currentNSDate())) as text
end timestamp

on dateFormatter()
	if _dateFormatter is missing value then
		set _dateFormatter to current application's NSDateFormatter's alloc()'s init()
		_dateFormatter's setLocale:(current application's NSLocale's localeWithLocaleIdentifier:"en_US_POSIX")
		_dateFormatter's setDateFormat:"yyyy-MM-dd HH:mm:ss"
	end if
	return _dateFormatter
end dateFormatter

on appendLog(lineText)
	set fullLine to (lineText as text) & linefeed
	set nsStr to current application's NSString's stringWithString:fullLine
	set dataObj to nsStr's dataUsingEncoding:(current application's NSUTF8StringEncoding)
	set pathText to DEBUG_LOG_PATH as text
	try
		set fm to my fileManager()
		if (fm's fileExistsAtPath:pathText) as boolean then
			set fh to current application's NSFileHandle's fileHandleForWritingAtPath:pathText
			fh's seekToEndOfFile()
			fh's writeData:dataObj
			fh's closeFile()
		else
			dataObj's writeToFile:pathText atomically:true
		end if
	on error
		-- Fail silently; logging must never break the main flow.
	end try
end appendLog

on fileManager()
	if _fileManager is missing value then
		set _fileManager to current application's NSFileManager's defaultManager()
	end if
	return _fileManager
end fileManager

on makeToken()
	set uuidStr to (current application's NSUUID's UUID()'s UUIDString()) as text
	return my replaceText(uuidStr, "-", "")
end makeToken

on isExecutableFile(p)
	set fm to my fileManager()
	return (fm's isExecutableFileAtPath:(p as text)) as boolean
end isExecutableFile

on fileModDate(p)
	set fm to my fileManager()
	set attrs to (fm's attributesOfItemAtPath:(p as text) |error|:(missing value))
	if attrs is missing value then return missing value
	return attrs's objectForKey:(current application's NSFileModificationDate)
end fileModDate

on isNewerThan(pathA, pathB)
	set dA to my fileModDate(pathA)
	set dB to my fileModDate(pathB)
	if dA is missing value or dB is missing value then return false
	set delta to (dA's timeIntervalSinceDate:dB)
	return (delta as real) > 0
end isNewerThan

on removeFileIfExists(p)
	set fm to my fileManager()
	set pathText to p as text
	if (fm's fileExistsAtPath:pathText) as boolean then
		fm's removeItemAtPath:pathText |error|:(missing value)
	end if
end removeFileIfExists

on writeTextToFile(t, p)
	set nsStr to current application's NSString's stringWithString:(t as text)
	nsStr's writeToFile:(p as text) atomically:true encoding:(current application's NSUTF8StringEncoding) |error|:(missing value)
end writeTextToFile

on normalizeNewlines(t)
	set s to t as text
	set s to my replaceText(s, linefeed, return)
	repeat 6 times
		set s to my replaceText(s, return & return & return, return & return)
	end repeat
	return s
end normalizeNewlines

on offsetOf(needle, haystack)
	set nsStr to current application's NSString's stringWithString:(haystack as text)
	set rangeObj to nsStr's rangeOfString:(needle as text)
	set loc to rangeObj's location
	if loc is current application's NSNotFound then return 0
	if (loc as real) > 9.0E+18 then return 0
	return (loc as integer) + 1
end offsetOf

on stripInjectedBanner(t)
	set s to t as text
	if my looksLikeHTML(s) then return s
	
	if s does not contain "WARNING This email originated external" then return s
	
	set p1 to my offsetOf("Submissions to:", s)
	set p2 to my offsetOf("arXiv:", s)
	
	if p1 = 0 and p2 = 0 then return s
	
	if p1 = 0 then
		return text p2 thru -1 of s
	else if p2 = 0 then
		return text p1 thru -1 of s
	else
		if p1 < p2 then
			return text p1 thru -1 of s
		else
			return text p2 thru -1 of s
		end if
	end if
end stripInjectedBanner

on stripFooter(t)
	set s to t as text
	if my looksLikeHTML(s) then return s
	set p to my offsetOf("To unsubscribe", s)
	if p > 1 then
		return text 1 thru (p - 1) of s
	else if p is 1 then
		return ""
	end if
	return s
end stripFooter

on splitIntoArxivBlocks(t)
	set s to my normalizeEntryTextForParsing(t)
	set linesList to paragraphs of (s as text)
	set lineCount to count of linesList
	
	set blocks to {}
	set cur to {}
	set inBlock to false
	
	repeat with i from 1 to lineCount
		set raw to item i of linesList as text
		set lineTrim to my trimText(raw)
		set startLine to ""
		
		if my hasLeadingDoubleBackslash(lineTrim) then
			set afterLine to ""
			if (length of lineTrim) > 2 then set afterLine to my trimText(text 3 thru -1 of lineTrim)
			
			if my startsWithTrimmedCI(afterLine, "arXiv:") then
				set startLine to afterLine
			else
				set nextNonEmpty to my nextNonEmptyLineTrim(linesList, i + 1)
				if nextNonEmpty is not "" and my startsWithTrimmedCI(nextNonEmpty, "arXiv:") then
					-- Boundary marker; do not include this delimiter in the current block.
				else
					if inBlock then set end of cur to raw
				end if
			end if
			
		else if my startsWithTrimmedCI(lineTrim, "arXiv:") then
			set startLine to lineTrim
		else
			if inBlock then set end of cur to raw
		end if
		
		if startLine is not "" then
			if inBlock and (count of cur) > 0 then set end of blocks to my joinLines(cur)
			set cur to {startLine}
			set inBlock to true
		end if
	end repeat
	
	if inBlock and (count of cur) > 0 then set end of blocks to my joinLines(cur)
	
	set cleaned to {}
	repeat with e in blocks
		set et to my trimText(e as text)
		if et is not "" then set end of cleaned to (e as text)
	end repeat
	
	return cleaned
end splitIntoArxivBlocks

on nextNonEmptyLineTrim(linesList, startIndex)
	set lineCount to count of linesList
	if startIndex > lineCount then return ""
	repeat with j from startIndex to lineCount
		set t to my trimText(item j of linesList as text)
		if t is not "" then return t
	end repeat
	return ""
end nextNonEmptyLineTrim

on hasLeadingDoubleBackslash(lineText)
	set t to my trimText(lineText)
	if (length of t) < 2 then return false
	if ((character 1 of t) as text) is "\\" and ((character 2 of t) as text) is "\\" then return true
	return false
end hasLeadingDoubleBackslash

on looksLikeHTML(t)
	set s to my toLower(t as text)
	if s contains "<html" then return true
	if s contains "<body" then return true
	if s contains "<div" then return true
	if s contains "<span" then return true
	if s contains "<dl" then return true
	if s contains "</" and s contains "<" then return true
	return false
end looksLikeHTML

on keywordHaystack(p)
	set parts to {p's title, p's authors, p's categories, p's comments, p's abstractText}
	return my joinWithSpace(parts)
end keywordHaystack

on parseArxivHTMLDocument(htmlText)
	set doc to my htmlDocumentFromString(htmlText)
	if doc is missing value then return {}
	
	set globalDateLine to my extractGlobalDateLine(doc)
	set entryNodes to my arxivEntryNodesFromDocument(doc)
	if (count of entryNodes) is 0 then return {}
	
	set out to {}
	repeat with n in entryNodes
		set p to my parseArxivEntryFromHTMLNode(n, globalDateLine)
		if p is not missing value then set end of out to p
	end repeat
	return out
end parseArxivHTMLDocument

on parseArxivEntryFromHTMLString(htmlText)
	set doc to my htmlDocumentFromString(htmlText)
	if doc is missing value then return missing value
	set globalDateLine to my extractGlobalDateLine(doc)
	set entryNodes to my arxivEntryNodesFromDocument(doc)
	if (count of entryNodes) is 0 then return missing value
	set entryNode to item 1 of entryNodes
	return my parseArxivEntryFromHTMLNode(entryNode, globalDateLine)
end parseArxivEntryFromHTMLString

on parseArxivEntryFromHTMLNode(entryNode, globalDateLine)
	set titleLine to my extractDescriptorValue(entryNode, {"Title"})
	if titleLine is "" then set titleLine to my stripLabelPrefix(my textFromClassSubstring(entryNode, "title"), "Title")
	if titleLine is "" then return missing value
	
	set authorsLine to my extractDescriptorValue(entryNode, {"Authors", "Author"})
	if authorsLine is "" then set authorsLine to my stripLabelPrefix(my textFromClassSubstring(entryNode, "author"), "Authors")
	
	set commentsLine to my extractDescriptorValue(entryNode, {"Comments"})
	if commentsLine is "" then set commentsLine to my stripLabelPrefix(my textFromClassSubstring(entryNode, "comments"), "Comments")
	
	set categoriesRaw to my extractDescriptorValue(entryNode, {"Subjects", "Categories", "Category"})
	if categoriesRaw is "" then set categoriesRaw to my stripLabelPrefix(my textFromClassSubstring(entryNode, "subjects"), "Subjects")
	if categoriesRaw is "" then set categoriesRaw to my stripLabelPrefix(my textFromClassSubstring(entryNode, "categories"), "Categories")
	set categoriesLine to my normalizeCategoriesFromSubjects(categoriesRaw)
	
	set abstractText to my extractAbstractFromEntry(entryNode)
	
	set dateLine to my extractDescriptorValue(entryNode, {"Date"})
	if dateLine is "" then set dateLine to globalDateLine
	if dateLine is "" then set dateLine to my stripLabelPrefix(my textFromClassSubstring(entryNode, "dateline"), "Date")
	set dateLine to my normalizeSpaces(dateLine)
	
	set arxivId to my extractArxivIdFromEntryNode(entryNode)
	set absUrl to ""
	if arxivId is not "" then
		set absUrl to "https://arxiv.org/abs/" & arxivId
	else
		set absUrl to my extractArxivURL(my nodeStringValue(entryNode))
	end if
	
	set doiLine to my extractDOIFromText(my nodeStringValue(entryNode))
	
	return {arxivId:arxivId, title:titleLine, dateLine:dateLine, authors:authorsLine, categories:categoriesLine, comments:commentsLine, doi:doiLine, URL:absUrl, abstractText:abstractText}
end parseArxivEntryFromHTMLNode

on htmlDocumentFromString(htmlText)
	try
		set nsStr to current application's NSString's stringWithString:(htmlText as text)
		set dataObj to nsStr's dataUsingEncoding:(current application's NSUTF8StringEncoding)
		if dataObj is missing value then return missing value
		set options to (current application's NSXMLDocumentTidyHTML)
		set {doc, err} to current application's NSXMLDocument's alloc()'s initWithData:dataObj options:options |error|:(reference)
		if doc is missing value then return missing value
		return doc
	on error
		return missing value
	end try
end htmlDocumentFromString

on arxivEntryNodesFromDocument(doc)
	-- Abstract page
	set absNode to my firstNodeForXPath(doc, "//*[@id='abs']")
	if absNode is not missing value then return {absNode}
	
	set titlePred to my labelTextPredicate("Title")
	set xpathMeta to "//div[contains(concat(' ', normalize-space(@class), ' '), ' meta ') and .//span[contains(concat(' ', normalize-space(@class), ' '), ' descriptor ') and " & titlePred & "]]"
	set nodes to my nodesForXPath(doc, xpathMeta)
	if (count of nodes) > 0 then return nodes
	
	set xpathDD to "//dd[.//span[contains(concat(' ', normalize-space(@class), ' '), ' descriptor ') and " & titlePred & "]]"
	set nodes to my nodesForXPath(doc, xpathDD)
	if (count of nodes) > 0 then return nodes
	
	set xpathLI to "//li[.//span[contains(concat(' ', normalize-space(@class), ' '), ' descriptor ') and " & titlePred & "]]"
	set nodes to my nodesForXPath(doc, xpathLI)
	if (count of nodes) > 0 then return nodes
	
	set xpathAny to "//*[.//span[contains(concat(' ', normalize-space(@class), ' '), ' descriptor ') and " & titlePred & "]]"
	set nodes to my nodesForXPath(doc, xpathAny)
	if (count of nodes) > 0 then return nodes
	
	return {}
end arxivEntryNodesFromDocument

on extractGlobalDateLine(doc)
	set dateLine to my extractDescriptorValue(doc, {"Date"})
	if dateLine is not "" then return dateLine
	
	set dateNode to my firstNodeForXPath(doc, "//*[contains(concat(' ', normalize-space(@class), ' '), ' dateline ') or contains(concat(' ', normalize-space(@class), ' '), ' list-dateline ')]")
	if dateNode is not missing value then
		set dateLine to my stripLabelPrefix(my nodeStringValue(dateNode), "Date")
		return my normalizeSpaces(dateLine)
	end if
	
	set h3Node to my firstNodeForXPath(doc, "//h3[normalize-space(.)!='']")
	if h3Node is not missing value then
		return my normalizeSpaces(my nodeStringValue(h3Node))
	end if
	
	return ""
end extractGlobalDateLine

on extractDescriptorValue(rootNode, labelList)
	repeat with l in labelList
		set val to my extractDescriptorValueSingle(rootNode, l as text)
		if val is not "" then return val
	end repeat
	return ""
end extractDescriptorValue

on extractDescriptorValueSingle(rootNode, labelText)
	set pred to my labelTextPredicate(labelText)
	
	set labelNode to my firstNodeForXPath(rootNode, ".//span[contains(concat(' ', normalize-space(@class), ' '), ' descriptor ') and " & pred & "]")
	if labelNode is missing value then
		set labelNode to my firstNodeForXPath(rootNode, ".//*[self::b or self::strong][" & pred & "]")
	end if
	if labelNode is missing value then
		set labelNode to my firstNodeForXPath(rootNode, ".//*[self::td or self::th][" & pred & "]")
	end if
	if labelNode is missing value then return ""
	
	set val to my valueFromLabelNode(labelNode)
	set val to my stripLabelPrefix(val, labelText)
	return my normalizeSpaces(val)
end extractDescriptorValueSingle

on labelTextPredicate(labelText)
	set lowerLabel to my toLower(labelText as text)
	set lowerNoColon to lowerLabel
	if lowerLabel ends with ":" then
		if (length of lowerLabel) > 1 then
			set lowerNoColon to text 1 thru -2 of lowerLabel
		else
			set lowerNoColon to ""
		end if
	end if
	set expr to "translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')"
	if lowerNoColon is "" then return "(" & expr & "='" & lowerLabel & "')"
	return "(" & expr & "='" & lowerLabel & "' or " & expr & "='" & lowerNoColon & "')"
end labelTextPredicate

on valueFromLabelNode(labelNode)
	set nodeName to ""
	try
		set nodeName to (labelNode's |name|()) as text
	end try
	
	if nodeName is "td" or nodeName is "th" then
		set sibling to my firstNodeForXPath(labelNode, "following-sibling::*[1]")
		if sibling is not missing value then return my normalizeSpaces(my nodeStringValue(sibling))
	end if
	
	set parentNode to missing value
	try
		set parentNode to labelNode's parentNode()
	end try
	if parentNode is missing value then return ""
	
	set val to my textFromParentExcludingNode(parentNode, labelNode)
	if val is not "" then return val
	
	set sibling to my firstNodeForXPath(parentNode, "following-sibling::*[1]")
	if sibling is not missing value then return my normalizeSpaces(my nodeStringValue(sibling))
	return ""
end valueFromLabelNode

on textFromParentExcludingNode(parentNode, skipNode)
	set outText to ""
	set children to {}
	try
		set children to parentNode's childNodes()
	end try
	repeat with ch in children
		if ch is skipNode then
			-- skip
		else
			set chunk to my nodeStringValue(ch)
			if chunk is not "" then set outText to outText & chunk
		end if
	end repeat
	return my normalizeSpaces(outText)
end textFromParentExcludingNode

on nodeStringValue(node)
	if node is missing value then return ""
	try
		return (node's stringValue()) as text
	on error
		return ""
	end try
end nodeStringValue

on nodeAttributeValue(node, attrName)
	if node is missing value then return ""
	try
		set attr to node's attributeForName:(attrName as text)
		if attr is missing value then return ""
		return (attr's stringValue()) as text
	on error
		return ""
	end try
end nodeAttributeValue

on nodesForXPath(rootNode, xpathText)
	try
		set {nodes, err} to rootNode's nodesForXPath:(xpathText as text) |error|:(reference)
		if nodes is missing value then return {}
		return nodes as list
	on error
		return {}
	end try
end nodesForXPath

on firstNodeForXPath(rootNode, xpathText)
	set nodes to my nodesForXPath(rootNode, xpathText)
	if (count of nodes) > 0 then return item 1 of nodes
	return missing value
end firstNodeForXPath

on stripLabelPrefix(textValue, labelText)
	set t to my trimText(textValue)
	if t is "" then return ""
	
	set tLower to my toLower(t)
	set labelLower to my toLower(labelText)
	set labelWithColon to labelLower
	if labelLower ends with ":" then
		set labelWithColon to labelLower
	else
		set labelWithColon to labelLower & ":"
	end if
	
	set lLen to length of labelWithColon
	if tLower begins with labelWithColon then
		if (length of t) > lLen then
			set t to text (lLen + 1) thru -1 of t
		else
			set t to ""
		end if
	else if labelLower is not "" and tLower begins with labelLower then
		set l2Len to length of labelLower
		if (length of t) > l2Len then
			set t to text (l2Len + 1) thru -1 of t
		else
			set t to ""
		end if
	end if
	
	return my trimText(t)
end stripLabelPrefix

on textFromClassSubstring(rootNode, classToken)
	if classToken is "" then return ""
	set xpath to ".//*[contains(@class,'" & classToken & "')]"
	set node to my firstNodeForXPath(rootNode, xpath)
	if node is missing value then return ""
	return my normalizeSpaces(my nodeStringValue(node))
end textFromClassSubstring

on extractAbstractFromEntry(entryNode)
	set absText to my extractDescriptorValue(entryNode, {"Abstract"})
	if absText is not "" then return absText
	
	set absNode to my firstNodeForXPath(entryNode, ".//*[contains(concat(' ', normalize-space(@class), ' '), ' abstract ')]")
	if absNode is missing value then return ""
	
	set xmlText to ""
	try
		set xmlText to (absNode's XMLString()) as text
	end try
	if xmlText is "" then return ""
	
	set absText to my htmlToPlainText(xmlText)
	set absText to my stripLabelPrefix(absText, "Abstract")
	return my trimText(absText)
end extractAbstractFromEntry

on htmlToPlainText(htmlText)
	try
		set nsStr to current application's NSString's stringWithString:(htmlText as text)
		set dataObj to nsStr's dataUsingEncoding:(current application's NSUTF8StringEncoding)
		if dataObj is missing value then return my trimText(htmlText)
		set opts to current application's NSDictionary's dictionaryWithObject:(current application's NSHTMLTextDocumentType) forKey:(current application's NSDocumentTypeDocumentAttribute)
		set {attr, err} to current application's NSAttributedString's alloc()'s initWithData:dataObj options:opts documentAttributes:(missing value) |error|:(reference)
		if attr is missing value then return my trimText(htmlText)
		set outText to (attr's string()) as text
		set outText to my normalizeNewlines(outText)
		return my trimText(outText)
	on error
		return my trimText(htmlText)
	end try
end htmlToPlainText

on normalizeCategoriesFromSubjects(rawText)
	set t to my trimText(rawText)
	if t is "" then return ""
	
	set AppleScript's text item delimiters to " "
	set tokens to text items of t
	set AppleScript's text item delimiters to ""
	
	set cats to {}
	repeat with tok in tokens
		set cleanTok to my trimPunctuationEdges(tok as text)
		if my looksLikeCategoryToken(cleanTok) then set end of cats to cleanTok
	end repeat
	
	set catLine to my normalizeSpaces(my joinWithSpace(cats))
	if catLine is not "" then return catLine
	return my normalizeSpaces(t)
end normalizeCategoriesFromSubjects

on extractArxivIdFromEntryNode(entryNode)
	set linkNode to my firstNodeForXPath(entryNode, ".//a[contains(@href,'/abs/') or contains(@href,'arxiv.org/abs')]")
	if linkNode is not missing value then
		set href to my nodeAttributeValue(linkNode, "href")
		if href is not "" then
			set idCandidate to my extractArxivIdFromText(href)
			if idCandidate is not "" then return idCandidate
		end if
	end if
	return my extractArxivIdFromText(my nodeStringValue(entryNode))
end extractArxivIdFromEntryNode

on startsWithTrimmed(s, prefix)
	set t to my trimText(s as text)
	if (length of t) < (length of prefix) then return false
	return ((text 1 thru (length of prefix) of t) is prefix)
end startsWithTrimmed

on startsWithTrimmedCI(s, prefix)
	set t to my trimText(s as text)
	if (length of t) < (length of prefix) then return false
	set tLower to my toLower(text 1 thru (length of prefix) of t)
	set pLower to my toLower(prefix as text)
	return (tLower is pLower)
end startsWithTrimmedCI

on joinLines(ls)
	set AppleScript's text item delimiters to return
	set joined to ls as text
	set AppleScript's text item delimiters to ""
	return joined
end joinLines

on lowercasedList(ls)
	set out to {}
	repeat with k in ls
		set end of out to my toLower(k as text)
	end repeat
	return out
end lowercasedList

on blockMatchesKeywords(blockText, keywordLowerList)
	set bLower to my toLower(blockText)
	repeat with kLower in keywordLowerList
		if bLower contains (kLower as text) then return true
	end repeat
	return false
end blockMatchesKeywords

(* Parser design notes:
	- Deterministic, delimiter-based parsing (no heuristics).
	- Split by "\\ arXiv:" boundaries, then parse labels by explicit prefixes.
	- Abstract = all lines after the metadata block until the next "\\" or next arXiv line.
	- Tests: see runParserTests() at the bottom; add new entries to the testCases list.
*)
on parseArxivEntryMultiLine(entryText)
	if my looksLikeHTML(entryText) then
		try
			set parsed to my parseArxivEntryFromHTMLString(entryText)
			if parsed is missing value then
				if DEBUG then my debugLog("[parse-html] skipped entry (missing title) | snippet=" & my debugSnippet(entryText))
				return missing value
			end if
			return parsed
		on error errMsg number errNum
			my debugLog("[parse-html] error " & errNum & ": " & errMsg & " | snippet=" & my debugSnippet(entryText))
			return missing value
		end try
	end if
	try
		set parsed to my parseArxivPlaintextBlock(entryText)
		if parsed is missing value then
			if DEBUG then my debugLog("[parse] skipped entry (missing title) | snippet=" & my debugSnippet(entryText))
			return missing value
		end if
		return parsed
	on error errMsg number errNum
		my debugLog("[parse] error " & errNum & ": " & errMsg & " | snippet=" & my debugSnippet(entryText))
		return missing value
	end try
end parseArxivEntryMultiLine

on parseArxivPlaintextBlock(entryText)
	set normalizedEntry to my normalizeEntryTextForParsing(entryText)
	set linesList to paragraphs of (normalizedEntry as text)
	
	set arxivId to ""
	set dateLineParts to {}
	set titleParts to {}
	set authorsParts to {}
	set categoriesParts to {}
	set commentsParts to {}
	set doiParts to {}
	set abstractLines to {}
	
	set metadataStarted to false
	set metadataEnded to false
	set inAbstract to false
	set currentLabel to ""
	
	repeat with ln in linesList
		set raw to ln as text
		set lineT to my trimText(raw)
		
		if lineT is "" then
			if inAbstract and (count of abstractLines) > 0 then
				set end of abstractLines to ""
			else if metadataStarted then
				set metadataEnded to true
				set currentLabel to ""
			end if
		else if my hasLeadingDoubleBackslash(lineT) then
			if inAbstract then
				exit repeat
			else if metadataStarted then
				set inAbstract to true
				set currentLabel to ""
				set metadataEnded to false
			end if
		else if my startsWithTrimmedCI(lineT, "arXiv:") then
			if arxivId is "" then set arxivId to my extractArxivIdFromText(lineT)
			if inAbstract then exit repeat
			if metadataStarted then exit repeat
		else if inAbstract then
			set end of abstractLines to raw
		else
			set labelInfo to my parseMetadataLabelLine(raw)
			set labelName to labelInfo's label
			set labelValue to labelInfo's value
			
			if labelName is "abstract" then
				set metadataStarted to true
				set metadataEnded to false
				set inAbstract to true
				set currentLabel to ""
				if labelValue is not "" then set end of abstractLines to labelValue
				
			else if labelName is not "" then
				set metadataStarted to true
				set metadataEnded to false
				set currentLabel to labelName
				if labelValue is not "" then
					if labelName is "date" then
						set end of dateLineParts to labelValue
					else if labelName is "title" then
						set end of titleParts to labelValue
					else if labelName is "authors" then
						set end of authorsParts to labelValue
					else if labelName is "categories" then
						set end of categoriesParts to labelValue
					else if labelName is "comments" then
						set end of commentsParts to labelValue
					else if labelName is "doi" then
						set end of doiParts to labelValue
					end if
				end if
			else if metadataStarted and currentLabel is not "" and metadataEnded is false then
				if currentLabel is "date" then
					set end of dateLineParts to lineT
				else if currentLabel is "title" then
					set end of titleParts to lineT
				else if currentLabel is "authors" then
					set end of authorsParts to lineT
				else if currentLabel is "categories" then
					set end of categoriesParts to lineT
				else if currentLabel is "comments" then
					set end of commentsParts to lineT
				else if currentLabel is "doi" then
					set end of doiParts to lineT
				end if
			else if metadataStarted then
				set inAbstract to true
				set metadataEnded to false
				if lineT is not "" then set end of abstractLines to raw
			end if
		end if
	end repeat
	
	set dateLine to my normalizeSpaces(my joinWithSpace(dateLineParts))
	set titleLine to my normalizeSpaces(my joinWithSpace(titleParts))
	set authorsLine to my normalizeSpaces(my joinWithSpace(authorsParts))
	set categoriesLine to my normalizeSpaces(my joinWithSpace(categoriesParts))
	set commentsLine to my normalizeSpaces(my joinWithSpace(commentsParts))
	set doiLine to my normalizeSpaces(my joinWithSpace(doiParts))
	
	if titleLine is "" then return missing value
	
	if arxivId is "" then set arxivId to my extractArxivIdFromText(normalizedEntry)
	set absUrl to ""
	if arxivId is not "" then
		set absUrl to "https://arxiv.org/abs/" & arxivId
	else
		set absUrl to my extractArxivURL(normalizedEntry)
	end if
	
	set abstractText to my trimText(my joinLines(abstractLines))
	if DEBUG then my debugLog("[parse] result title=\"" & titleLine & "\" abstractLen=" & (length of abstractText))
	
	return {arxivId:arxivId, title:titleLine, dateLine:dateLine, authors:authorsLine, categories:categoriesLine, comments:commentsLine, doi:doiLine, URL:absUrl, abstractText:abstractText}
end parseArxivPlaintextBlock

on parseMetadataLabelLine(lineText)
	set t to my trimText(lineText)
	if t is "" then return {label:"", value:""}
	
	if my startsWithTrimmedCI(t, "Date:") then return {label:"date", value:my valueAfterPrefix(t, "Date:")}
	if my startsWithTrimmedCI(t, "Title:") then return {label:"title", value:my valueAfterPrefix(t, "Title:")}
	if my startsWithTrimmedCI(t, "Authors:") then return {label:"authors", value:my valueAfterPrefix(t, "Authors:")}
	if my startsWithTrimmedCI(t, "Categories:") then return {label:"categories", value:my valueAfterPrefix(t, "Categories:")}
	if my startsWithTrimmedCI(t, "Category:") then return {label:"categories", value:my valueAfterPrefix(t, "Category:")}
	if my startsWithTrimmedCI(t, "Comments:") then return {label:"comments", value:my valueAfterPrefix(t, "Comments:")}
	if my startsWithTrimmedCI(t, "DOI:") then return {label:"doi", value:my valueAfterPrefix(t, "DOI:")}
	if my startsWithTrimmedCI(t, "Abstract:") then return {label:"abstract", value:my valueAfterPrefix(t, "Abstract:")}
	
	return {label:"", value:""}
end parseMetadataLabelLine

on valueAfterPrefix(trimmedLine, prefixText)
	set prefixLen to length of (prefixText as text)
	if (length of trimmedLine) <= prefixLen then return ""
	return my trimText(text (prefixLen + 1) thru -1 of trimmedLine)
end valueAfterPrefix

on normalizeEntryTextForParsing(t)
	set s to t as text
	set s to my replacePipeBreaksWithNewline(s)
	set s to my removeControlChars(s)
	set s to my normalizeNewlines(s)
	return s
end normalizeEntryTextForParsing

on removeControlChars(s)
	set nsStr to current application's NSString's stringWithString:(s as text)
	set rx to my controlCharRegex()
	if rx is missing value then return s
	set replaced to rx's stringByReplacingMatchesInString:nsStr options:0 range:{0, nsStr's |length|()} withTemplate:" "
	return replaced as text
end removeControlChars

on replacePipeBreaksWithNewline(s)
	set nsStr to current application's NSString's stringWithString:(s as text)
	set rx to my pipeBreakRegex()
	if rx is missing value then return s
	set replaced to rx's stringByReplacingMatchesInString:nsStr options:0 range:{0, nsStr's |length|()} withTemplate:(return as text)
	return replaced as text
end replacePipeBreaksWithNewline

on extractArxivIdFromText(t)
	set textValue to t as text
	set idNew to my regexFirstMatch(textValue, my arxivIdNewRegex())
	if idNew is not "" then return idNew
	set idOld to my regexFirstMatch(textValue, my arxivIdOldRegex())
	return idOld
end extractArxivIdFromText

on extractArxivURL(t)
	set urlMatch to my regexFirstMatch(t as text, my arxivURLRegex())
	if urlMatch is "" then return ""
	if urlMatch contains "/pdf/" then
		set idCandidate to my extractArxivIdFromText(urlMatch)
		if idCandidate is not "" then return "https://arxiv.org/abs/" & idCandidate
	end if
	return urlMatch
end extractArxivURL

on extractDOIFromText(t)
	set doiMatch to my regexFirstMatch(t as text, my doiRegex())
	if doiMatch is "" then return ""
	return my trimPunctuationEdges(doiMatch)
end extractDOIFromText

on looksLikeCategoryToken(tok)
	set t to my trimPunctuationEdges(tok)
	if t is "" then return false
	set tLower to my toLower(t)
	if (tLower contains ".") is false and (tLower contains "-") is false then return false
	if tLower contains "http" then return false
	if tLower contains "doi" then return false
	if tLower contains "/" then return false
	
	set nsStr to current application's NSString's stringWithString:tLower
	set allowed to current application's NSCharacterSet's characterSetWithCharactersInString:"abcdefghijklmnopqrstuvwxyz.-"
	set inverted to allowed's invertedSet()
	set r to nsStr's rangeOfCharacterFromSet:inverted
	if (r's location) is not current application's NSNotFound then return false
	return true
end looksLikeCategoryToken

on trimPunctuationEdges(s)
	set nsStr to current application's NSString's stringWithString:(s as text)
	set trimmed to nsStr's stringByTrimmingCharactersInSet:(my punctuationEdgeSet())
	return trimmed as text
end trimPunctuationEdges

on punctuationEdgeSet()
	if _punctuationSet is missing value then
		set _punctuationSet to current application's NSCharacterSet's characterSetWithCharactersInString:"[](){}<>,.;:|\"'`"
	end if
	return _punctuationSet
end punctuationEdgeSet

on regexFirstMatch(textValue, rx)
	if rx is missing value then return ""
	set nsStr to current application's NSString's stringWithString:(textValue as text)
	set match to rx's firstMatchInString:nsStr options:0 range:{0, nsStr's |length|()}
	if match is missing value then return ""
	set r to match's rangeAtIndex:0
	return (nsStr's substringWithRange:r) as text
end regexFirstMatch

on pipeBreakRegex()
	if _regexPipeBreak is missing value then
		set _regexPipeBreak to current application's NSRegularExpression's regularExpressionWithPattern:"\\s*\\|\\|\\s*" options:0 |error|:(missing value)
	end if
	return _regexPipeBreak
end pipeBreakRegex

on controlCharRegex()
	if _regexControlChars is missing value then
		set _regexControlChars to current application's NSRegularExpression's regularExpressionWithPattern:"[\\x00-\\x08\\x0B\\x0C\\x0E-\\x1F]" options:0 |error|:(missing value)
	end if
	return _regexControlChars
end controlCharRegex

on doiRegex()
	if _regexDoi is missing value then
		set _regexDoi to current application's NSRegularExpression's regularExpressionWithPattern:"10\\.\\d{4,9}/[^\\s]+" options:0 |error|:(missing value)
	end if
	return _regexDoi
end doiRegex

on arxivIdNewRegex()
	if _regexArxivIdNew is missing value then
		set _regexArxivIdNew to current application's NSRegularExpression's regularExpressionWithPattern:"\\b\\d{4}\\.\\d{4,5}(v\\d+)?\\b" options:0 |error|:(missing value)
	end if
	return _regexArxivIdNew
end arxivIdNewRegex

on arxivIdOldRegex()
	if _regexArxivIdOld is missing value then
		set _regexArxivIdOld to current application's NSRegularExpression's regularExpressionWithPattern:"\\b[a-z-]+(\\.[A-Z]{2})?/\\d{7}(v\\d+)?\\b" options:(current application's NSRegularExpressionCaseInsensitive) |error|:(missing value)
	end if
	return _regexArxivIdOld
end arxivIdOldRegex

on arxivURLRegex()
	if _regexArxivURL is missing value then
		set _regexArxivURL to current application's NSRegularExpression's regularExpressionWithPattern:"https?://arxiv\\.org/(abs|pdf)/[^\\s)\\]]+" options:(current application's NSRegularExpressionCaseInsensitive) |error|:(missing value)
	end if
	return _regexArxivURL
end arxivURLRegex

on joinWithSpace(ls)
	if (count of ls) is 0 then return ""
	set AppleScript's text item delimiters to " "
	set joined to ls as text
	set AppleScript's text item delimiters to ""
	return joined
end joinWithSpace

on normalizeSpaces(s)
	set nsStr to current application's NSString's stringWithString:(s as text)
	set rx to my collapseWhitespaceRegex()
	if rx is missing value then return my trimText(s)
	set replaced to rx's stringByReplacingMatchesInString:nsStr options:0 range:{0, nsStr's |length|()} withTemplate:" "
	set trimmed to replaced's stringByTrimmingCharactersInSet:(my whitespaceSet())
	return trimmed as text
end normalizeSpaces

on toLower(s)
	set nsStr to current application's NSString's stringWithString:(s as text)
	return (nsStr's lowercaseString()) as text
end toLower

on trimText(s)
	set nsStr to current application's NSString's stringWithString:(s as text)
	set trimmed to nsStr's stringByTrimmingCharactersInSet:(my whitespaceSet())
	return trimmed as text
end trimText

on whitespaceSet()
	if _whitespaceSet is missing value then
		set _whitespaceSet to current application's NSCharacterSet's whitespaceAndNewlineCharacterSet()
	end if
	return _whitespaceSet
end whitespaceSet

on collapseWhitespaceRegex()
	if _regexCollapseWS is missing value then
		set _regexCollapseWS to current application's NSRegularExpression's regularExpressionWithPattern:"\\s+" options:0 |error|:(missing value)
	end if
	return _regexCollapseWS
end collapseWhitespaceRegex

on envVar(nameText)
	set env to current application's NSProcessInfo's processInfo()'s environment()
	set val to env's objectForKey:(nameText as text)
	if val is missing value then return ""
	return val as text
end envVar

on parseKeywordsFromText(rawText)
	set normalized to my replaceText(rawText, return, ",")
	set normalized to my replaceText(normalized, (ASCII character 10), ",")
	set AppleScript's text item delimiters to ","
	set parts to text items of (normalized as text)
	set AppleScript's text item delimiters to ""
	set out to {}
	repeat with p in parts
		set t to my trimText(p as text)
		if t is not "" then set end of out to t
	end repeat
	return out
end parseKeywordsFromText

on replaceText(theText, searchString, replacementString)
	set AppleScript's text item delimiters to searchString
	set parts to text items of (theText as text)
	set AppleScript's text item delimiters to replacementString
	set newText to parts as text
	set AppleScript's text item delimiters to ""
	return newText
end replaceText

on runParserTests()
	set testCases to my parserTestCases()
	set failures to {}
	
	repeat with tc in testCases
		set caseLabel to tc's caseName
		set inputText to tc's input
		set p to my parseArxivEntryMultiLine(inputText)
		
		if p is missing value then
			set end of failures to caseLabel & ": parse returned missing value"
		else
			set titleExpect to tc's expectTitle
			if titleExpect is not "" and (p's title does not contain titleExpect) then
				set end of failures to caseLabel & ": title mismatch (" & p's title & ")"
			end if
			
			set authorsExpect to tc's expectAuthors
			if authorsExpect is not "" and (p's authors does not contain authorsExpect) then
				set end of failures to caseLabel & ": authors mismatch (" & p's authors & ")"
			end if
			
			set categoriesExpect to tc's expectCategories
			if categoriesExpect is not "" and (p's categories does not contain categoriesExpect) then
				set end of failures to caseLabel & ": categories mismatch (" & p's categories & ")"
			end if
			
			set commentsExpect to tc's expectComments
			if commentsExpect is not "" and (p's comments does not contain commentsExpect) then
				set end of failures to caseLabel & ": comments mismatch (" & p's comments & ")"
			end if
			
			set doiExpect to tc's expectDOI
			if doiExpect is not "" and (p's doi does not contain doiExpect) then
				set end of failures to caseLabel & ": DOI mismatch (" & p's doi & ")"
			end if
			
			set dateExpect to ""
			try
				set dateExpect to tc's expectDate
			end try
			if dateExpect is not "" and (p's dateLine does not contain dateExpect) then
				set end of failures to caseLabel & ": date mismatch (" & p's dateLine & ")"
			end if
			
			set absExpect to tc's expectAbstractContains
			if absExpect is not "" and (p's abstractText does not contain absExpect) then
				set end of failures to caseLabel & ": abstract missing expected text"
			end if
			
			set bannedTokens to tc's expectAbstractNotContains
			repeat with tok in bannedTokens
				set tokenText to tok as text
				if tokenText is not "" and (p's abstractText contains tokenText) then
					set end of failures to caseLabel & ": abstract contains metadata token (" & tokenText & ")"
				end if
			end repeat
			
			set labelIssues to my labelIntegrityFailures(p)
			repeat with issue in labelIssues
				set end of failures to caseLabel & ": " & issue
			end repeat
		end if
	end repeat
	
	if (count of failures) is 0 then
		return "All parser tests passed (" & (count of testCases) & " cases)."
	else
		return "Parser tests failed:" & return & my joinLines(failures)
	end if
end runParserTests

on parserTestCases()
	set bs to character id 92
	set delim to bs & bs
	set banned to {"Categories:", "Comments:", "DOI:", "arXiv:"}
	
	set case1 to {caseName:"delimited-basic", input:my joinLines({"arXiv:2601.21013", "Date: Wed, 28 Jan 2026 20:08:38 GMT (12179kb)", "Title: 27 years of Spaceborne IR Astronomy: An ISO, Spitzer, WISE and NEOWISE", "Survey for Large-Amplitude Variability in Young Stellar Objects", "Authors: A. Alpha, B. Beta", "Categories: astro-ph.SR", "Comments: 69 pages, 11 main figures, accepted for publication in ApJ", delim, "Infrared observations can probe photometric variability across the full", "evolutionary range of young stellar objects (YSOs).", delim & " ( https://arxiv.org/abs/2601.21013 , 12179kb)"}), expectTitle:"27 years of Spaceborne IR Astronomy", expectAuthors:"A. Alpha", expectCategories:"astro-ph.SR", expectComments:"69 pages", expectDOI:"", expectAbstractContains:"Infrared observations can probe", expectAbstractNotContains:(banned & {"https://arxiv.org/abs"})}
	
	set case2 to {caseName:"comments-continuation", input:my joinLines({"arXiv:2601.21101", "Date: Wed, 28 Jan 2026 22:40:19 GMT", "Title: The First Quantitative Study of Tail Regrowth of CME-Driven Disconnection in Comet C/2023 P1 Nishimura", "Authors: Shaheda Begum Shaik, Guillermo Stenborg, Phillip Hess", "Categories: astro-ph.SR astro-ph.EP physics.space-ph", "Comments: 11 pages, 4 figures, Accepted by the Astrophysical Journal,", "Accompanying movie of Figure 2: https://drive.google.com/file/d/1-e8FYs5Z7Z2k0jWGvRJtDwqqHNOjUPyh/view", delim, "Comet C/2023 P1 (Nishimura) was observed by the Solar Orbiter Heliospheric Imager.", "We report the dynamics of the best observed TDE."}), expectTitle:"Tail Regrowth", expectAuthors:"Shaheda Begum Shaik", expectCategories:"astro-ph.SR", expectComments:"Accompanying movie of Figure 2", expectDOI:"", expectAbstractContains:"Comet C/2023 P1", expectAbstractNotContains:(banned & {"https://drive.google.com"})}
	
	set case3 to {caseName:"no-delimiter", input:my joinLines({"arXiv:2601.06759", "Date: Thu, 29 Jan 2026 16:06:12 GMT", "Title: SPHEREx Re-Observation of Interstellar Object 3I/ATLAS in December 2025:", "Detection of Increased Post-Perihelion Activity, Refractory Coma Dust, and New Coma Gas Species", "Authors: C.M. Lisse, Y.P. Bach", "Categories: astro-ph.EP astro-ph.GA astro-ph.SR", "Comments: 7 pages, 1 figure", "", "We report new observations of 3I/ATLAS and characterize the post-perihelion coma."}), expectTitle:"SPHEREx Re-Observation", expectAuthors:"C.M. Lisse", expectCategories:"astro-ph.EP", expectComments:"7 pages", expectDOI:"", expectAbstractContains:"We report new observations", expectAbstractNotContains:banned}
	
	set case4 to {caseName:"revision-line-preamble", input:my joinLines({"arXiv:2505.11263", "replaced with revised version Wed, 28 Jan 2026 22:53:21 GMT (3212kb)", "Title: A Cosmic Miracle: A Remarkably Luminous Galaxy at $z_{\\rm{spec}}=14.44$", "Authors: Rohan P. Naidu, Pascal A. Oesch", "Categories: astro-ph.GA astro-ph.CO astro-ph.SR", "Comments: Published in the Open Journal of Astrophysics", delim, "We report a remarkably luminous galaxy at high redshift and discuss its implications."}), expectTitle:"A Cosmic Miracle", expectAuthors:"Rohan P. Naidu", expectCategories:"astro-ph.GA", expectComments:"Published in the Open Journal of Astrophysics", expectDOI:"", expectAbstractContains:"We report a remarkably luminous galaxy", expectAbstractNotContains:(banned & {"replaced with revised version"})}
	
	set case5 to {caseName:"abstract-label", input:my joinLines({"arXiv:2601.00099", "Title: Abstract Label Example", "Authors: Z. Zeta", "Categories: astro-ph.SR", "Abstract: First paragraph of the abstract begins here.", "Second paragraph continues with more details."}), expectTitle:"Abstract Label Example", expectAuthors:"Z. Zeta", expectCategories:"astro-ph.SR", expectComments:"", expectDOI:"", expectAbstractContains:"First paragraph of the abstract", expectAbstractNotContains:banned}
	
	return {case1, case2, case3, case4, case5}
end parserTestCases

on labelIntegrityFailures(p)
	set issues to {}
	
	if my startsWithTrimmedCI(p's dateLine, "Date:") or my startsWithTrimmedCI(p's dateLine, "te:") then set end of issues to "dateLine has label prefix"
	if my startsWithTrimmedCI(p's title, "Title:") or my startsWithTrimmedCI(p's title, "tle:") then set end of issues to "title has label prefix"
	if my startsWithTrimmedCI(p's authors, "Authors:") or my startsWithTrimmedCI(p's authors, "thors") then set end of issues to "authors has label prefix"
	if my startsWithTrimmedCI(p's comments, "Comments:") or my startsWithTrimmedCI(p's comments, "mments:") then set end of issues to "comments has label prefix"
	if my startsWithTrimmedCI(p's categories, "Categories:") or my startsWithTrimmedCI(p's categories, "ategories:") then set end of issues to "categories has label prefix"
	if my startsWithTrimmedCI(p's abstractText, "Abstract:") or my startsWithTrimmedCI(p's abstractText, "bstract:") then set end of issues to "abstract has label prefix"
	
	return issues
end labelIntegrityFailures

on jsonString(s)
	set t to s as text
	set t to my replaceText(t, "\\", "\\\\")
	set t to my replaceText(t, "\"", "\\\"")
	set t to my replaceText(t, return, "\\n")
	set t to my replaceText(t, linefeed, "\\n")
	return "\"" & t & "\""
end jsonString

on jsonNumberOrNull(v)
	try
		if v is missing value then return "null"
		if (v as text) is "" then return "null"
		return (v as text)
	on error
		return "null"
	end try
end jsonNumberOrNull

on dateFromEpochSeconds(sec)
	set epochBase to (current application's NSDate's dateWithTimeIntervalSince1970:0) as date
	return epochBase + (sec as real)
end dateFromEpochSeconds

on epochSecondsFromDate(d)
	set epochBase to (current application's NSDate's dateWithTimeIntervalSince1970:0) as date
	return (d - epochBase) as real
end epochSecondsFromDate
