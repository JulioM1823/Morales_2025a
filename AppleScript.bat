(*
arXiv digest browser (Mail -> keyword filter -> robust multi-line metadata parse)
Loading UI is handled INSIDE the Swift picker (reliable in Shortcuts).
AppleScript launches picker first in "wait-for-file" mode by setting ARXIV_PAYLOAD_PATH.
*)

use framework "Foundation"
use scripting additions

property TARGET_ACCOUNT_NAME : "Exchange"
property TARGET_SENDER_EMAIL : "no-reply@arXiv.org"
property KEYWORDS : {"gravity waves", "gravity wave", "buoyancy waves", "buoyancy wave", "atmospheric gravity wave", "atmospheric gravity waves", "agw", "agws", "acoustic", "oscillation", "oscillations", "wave", "waves", "alfven"}
property DEBUG : false
property PROFILE : false
property DEBUG_LOG_PATH : "/tmp/arxiv_debug.log"

property _whitespaceSet : missing value
property _regexCollapseWS : missing value
property _dateFormatter : missing value
property _perfStartDate : missing value
property _fileManager : missing value

if DEBUG then my debugLog("=== run start ===")
my perfLog("run start")

-- =========================
-- Launch picker FIRST (shows built-in spinner)
-- =========================
set pickerPathScript to (POSIX path of (path to home folder)) & "bin/arxiv-picker.swift"
set pickerPathBin to (POSIX path of (path to home folder)) & "bin/arxiv-picker.bin"

-- Prefer the prebuilt binary to avoid runtime compilation failures.
set pickerPath to pickerPathScript
if my isExecutableFile(pickerPathBin) then
	set pickerPath to pickerPathBin
else if my isExecutableFile(pickerPathScript) is false then
	display alert "Picker tool not found" message ("Missing or not executable:" & return & pickerPathScript & return & return & "Run:" & return & "chmod +x ~/bin/arxiv-picker.swift")
	return
end if

set token to my makeToken()
set payloadPath to "/tmp/arxiv_payload_" & token & ".json"
my removeFileIfExists(payloadPath)

-- Start picker in background, with env var that tells it what file to watch.
-- IMPORTANT: we do NOT pipe stdin; picker will show spinner until payload file exists.
set envPrefix to "ARXIV_PAYLOAD_PATH=" & quoted form of payloadPath
if DEBUG then set envPrefix to "ARXIV_DEBUG=1 " & envPrefix
if PROFILE then set envPrefix to "ARXIV_PROFILE=1 " & envPrefix

-- Always capture picker logs for post-mortem debugging.
set launchLogPath to "/tmp/arxiv_picker_launch_" & token & ".log"

my perfLog("picker launch start")
do shell script envPrefix & " " & quoted form of pickerPath & " >>" & quoted form of launchLogPath & " 2>&1 &"
my perfLog("picker launched")

-- Small delay so the picker window has time to appear before we hammer Mail.
delay 0.2

-- =========================
-- Scan Mail and build payload
-- =========================
my perfLog("mail scan start")

set matches to {}
set latestRec to missing value
set latestDate to missing value
set mailboxCount to 0
set candidateCount to 0
set matchCount to 0

tell application "Mail"
	activate
	
	-- Scan window: last 7 days
	set cutoffDate to (current date) - (7 * days)
	
	-- Locate account
	set theAccount to missing value
	repeat with a in accounts
		if (name of a as text) is TARGET_ACCOUNT_NAME then
			set theAccount to a
			exit repeat
		end if
	end repeat
	if theAccount is missing value then error "Could not find a Mail account named: " & TARGET_ACCOUNT_NAME
	
	my debugLog("Found account: " & TARGET_ACCOUNT_NAME)
	my debugAlert("Mail", "Found account: " & TARGET_ACCOUNT_NAME)
	
	-- Collect candidate messages (last 7 days)
	-- We avoid date comparisons inside whose clauses and keep "date received" on a single line.
	repeat with mb in (mailboxes of theAccount)
		set mailboxCount to mailboxCount + 1
		
		set mbName to ""
		try
			set mbName to name of mb
		end try
		
		set useManualSenderFilter to false
		set candidates to {}
		try
			set candidates to (messages of mb whose sender contains TARGET_SENDER_EMAIL)
		on error errMsg number errNum
			set useManualSenderFilter to true
			set candidates to messages of mb
			my debugLog("Whose filter failed for mailbox " & mbName & " (" & errNum & "): " & errMsg & ". Falling back to manual sender check.")
		end try
		
		set cCount to 0
		try
			set cCount to count of candidates
		end try
		
		if useManualSenderFilter is false then
			set candidateCount to candidateCount + cCount
		end if
		
		if cCount > 0 then
			set recDatesOK to false
			set recDates to {}
			try
				set recDates to date received of candidates
				set recDatesOK to true
			on error errMsg number errNum
				my debugLog("Batch date received failed for mailbox " & mbName & " (" & errNum & "): " & errMsg & ". Falling back to per-message date.")
			end try
			
			set sendersOK to false
			set senderList to {}
			if useManualSenderFilter then
				try
					set senderList to sender of candidates
					set sendersOK to true
				on error errMsg number errNum
					my debugLog("Batch sender failed for mailbox " & mbName & " (" & errNum & "): " & errMsg & ". Falling back to per-message sender.")
				end try
			end if
			
			repeat with i from 1 to cCount
				set m to missing value
				try
					set m to item i of candidates
					if recDatesOK then
						set recDate to item i of recDates
					else
						set recDate to date received of m
					end if
					
					if recDate >= cutoffDate then
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
								if latestDate is missing value or recDate > latestDate then
									set latestDate to recDate
									set latestRec to {msg:m, recDate:recDate}
								end if
							end if
						else
							set end of matches to {msg:m, recDate:recDate}
							set matchCount to matchCount + 1
							if latestDate is missing value or recDate > latestDate then
								set latestDate to recDate
								set latestRec to {msg:m, recDate:recDate}
							end if
						end if
					end if
				on error errMsg number errNum
					set msgSummary to my safeMessageSummary(m)
					my debugError("Message scan error", mbName, msgSummary, errNum, errMsg)
				end try
			end repeat
		end if
	end repeat
end tell

my debugLog("Mailboxes scanned: " & mailboxCount)
my debugAlert("Mail", "Mailboxes scanned: " & mailboxCount)
my debugLog("Candidate count: " & candidateCount)
my debugAlert("Mail", "Candidate count: " & candidateCount)
my debugLog("Match count: " & matchCount)
my debugAlert("Mail", "Match count: " & matchCount)
my perfLog("mail scan end: matches=" & matchCount)

if matchCount is 0 then
	display alert "No arXiv emails found" message ("No messages from " & TARGET_SENDER_EMAIL & " in the last 7 days.")
	return
end if

-- Newest first
if latestRec is missing value then
	set matchesSorted to my sortRecordsByDateDesc(matches)
	set firstRec to item 1 of matchesSorted
else
	set firstRec to latestRec
end if

my perfLog("message body load start")
tell application "Mail"
	set rawBody to content of (firstRec's msg)
end tell
my perfLog("message body load end")

-- Capture recipient (To:) name/address for downstream email template.
-- Best-effort: if unavailable, keep empty strings.
set recipientName to ""
set recipientEmail to ""
try
	tell application "Mail"
		set toList to to recipients of (firstRec's msg)
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
on error
	-- ignore
end try

-- Normalize Mail text and remove injected warnings/headers and footers
set rawBody to my normalizeNewlines(rawBody as text)
set rawBody to my stripInjectedBanner(rawBody)
set rawBody to my stripFooter(rawBody)

-- Split into per-entry blocks (robust delimiter: "arXiv:")
set entryBlocks to my splitIntoEntriesByArxivHeader(rawBody)

-- Parse entries, filter by keywords
my perfLog("parse start")
set keywordLowerList to my lowercasedList(KEYWORDS)
set papers to {}
repeat with b in entryBlocks
	set bt to (b as text)
	if my blockMatchesKeywords(bt, keywordLowerList) then
		set p to my parseArxivEntryMultiLine(bt)
		if p is not missing value then set end of papers to p
	end if
end repeat
my perfLog("parse end: papers=" & (count of papers))

if (count of papers) is 0 then
	display alert "No matches" message "No publications matched your keyword filter."
	return
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
	set obj to obj & "\"abstractText\":" & my jsonString(p's abstractText)
	set obj to obj & "}"
	
	set papersJSON to papersJSON & obj
	if i < n then set papersJSON to papersJSON & ","
end repeat
set papersJSON to papersJSON & "]"

set payloadJSON to "{"
set payloadJSON to payloadJSON & "\"keywords\":" & keywordsJSON & ","
set payloadJSON to payloadJSON & "\"recipientName\":" & my jsonString(recipientName) & ","
set payloadJSON to payloadJSON & "\"recipientEmail\":" & my jsonString(recipientEmail) & ","
set payloadJSON to payloadJSON & "\"papers\":" & papersJSON
set payloadJSON to payloadJSON & "}"

-- =========================
-- Deliver payload to picker (THIS triggers spinner -> real UI)
-- =========================
my perfLog("payload write start")
my writeTextToFile(payloadJSON, payloadPath)
my perfLog("payload write end")

return

-- =====================================================================
-- Helpers
-- =====================================================================

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

on debugAlert(titleText, msgText)
	if DEBUG is false then return
	display alert titleText message msgText
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
		tell application "Mail"
			set subj to subject of m
			set msgId to id of m
		end tell
		return "subject=" & subj & ", id=" & msgId
	on error
		return "(message info unavailable)"
	end try
end safeMessageSummary

on perfLog(labelText)
	if PROFILE is false then return
	if _perfStartDate is missing value then set _perfStartDate to current date
	set deltaSec to (current date) - _perfStartDate
	set lineText to my timestamp() & " [perf +" & my formatSeconds(deltaSec) & "s] " & labelText
	my appendLog(lineText)
end perfLog

on formatSeconds(x)
	return (round (x * 1000) / 1000) as text
end formatSeconds

on timestamp()
	set df to my dateFormatter()
	return (df's stringFromDate:(current date)) as text
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

on stripInjectedBanner(t)
	set s to t as text
	
	if s does not contain "WARNING This email originated external" then return s
	
	set p1 to offset of "Submissions to:" in s
	set p2 to offset of "arXiv:" in s
	
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
	set p to offset of "To unsubscribe" in s
	if p > 0 then
		return text 1 thru (p - 1) of s
	end if
	return s
end stripFooter

on splitIntoEntriesByArxivHeader(t)
	set s to t as text
	set linesList to paragraphs of s
	
	set entries to {}
	set cur to {}
	set seenAny to false
	
	repeat with ln in linesList
		set lineT to ln as text
		
		if my startsWithTrimmed(lineT, "arXiv:") then
			if (count of cur) > 0 then
				set end of entries to my joinLines(cur)
				set cur to {}
			end if
			set seenAny to true
		end if
		
		if seenAny then set end of cur to lineT
	end repeat
	
	if (count of cur) > 0 then set end of entries to my joinLines(cur)
	
	set cleaned to {}
	repeat with e in entries
		set et to my trimText(e as text)
		if et is not "" then set end of cleaned to (e as text)
	end repeat
	
	return cleaned
end splitIntoEntriesByArxivHeader

on startsWithTrimmed(s, prefix)
	set t to my trimText(s as text)
	if (length of t) < (length of prefix) then return false
	return ((text 1 thru (length of prefix) of t) is prefix)
end startsWithTrimmed

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

on parseArxivEntryMultiLine(entryText)
	set linesList to paragraphs of (entryText as text)
	
	set arxivId to ""
	set dateLineParts to {}
	set titleParts to {}
	set authorsParts to {}
	set categoriesParts to {}
	set commentsParts to {}
	set abstractParts to {}
	
	set mode to "none"
	
	repeat with ln in linesList
		set raw to ln as text
		set lineT to my trimText(raw)
		
		if lineT is "" then
			if mode is "abstract" then
				set end of abstractParts to ""
			else if mode is "comments" then
				set mode to "abstract"
				set end of abstractParts to ""
			end if
			
		else if my startsWithTrimmed(lineT, "arXiv:") then
			set arxivId to my trimText(text 7 thru -1 of lineT)
			if arxivId contains " " then set arxivId to text 1 thru ((offset of " " in arxivId) - 1) of arxivId
			set mode to "none"
			
		else if my startsWithTrimmed(lineT, "Date:") then
			set mode to "date"
			set end of dateLineParts to my trimText(text 6 thru -1 of lineT)
			
		else if my startsWithTrimmed(lineT, "Title:") then
			set mode to "title"
			set end of titleParts to my trimText(text 7 thru -1 of lineT)
			
		else if my startsWithTrimmed(lineT, "Authors:") then
			set mode to "authors"
			set end of authorsParts to my trimText(text 9 thru -1 of lineT)
			
		else if my startsWithTrimmed(lineT, "Categories:") then
			set mode to "categories"
			set end of categoriesParts to my trimText(text 12 thru -1 of lineT)
			
		else if my startsWithTrimmed(lineT, "Comments:") then
			set mode to "comments"
			set end of commentsParts to my trimText(text 10 thru -1 of lineT)
			
		else if my isHeaderLine(lineT) then
			set mode to "abstract"
			set end of abstractParts to raw
			
		else
			if mode is "date" then
				set end of dateLineParts to lineT
			else if mode is "title" then
				set end of titleParts to lineT
			else if mode is "authors" then
				set end of authorsParts to lineT
			else if mode is "categories" then
				set end of categoriesParts to lineT
			else if mode is "comments" then
				set mode to "abstract"
				set end of abstractParts to raw
			else
				set mode to "abstract"
				set end of abstractParts to raw
			end if
		end if
	end repeat
	
	set dateLine to my normalizeSpaces(my joinWithSpace(dateLineParts))
	set titleLine to my normalizeSpaces(my joinWithSpace(titleParts))
	set authorsLine to my normalizeSpaces(my joinWithSpace(authorsParts))
	set categoriesLine to my normalizeSpaces(my joinWithSpace(categoriesParts))
	set commentsLine to my normalizeSpaces(my joinWithSpace(commentsParts))
	
	if titleLine is "" then return missing value
	
	set absUrl to ""
	if arxivId is not "" then set absUrl to "https://arxiv.org/abs/" & arxivId
	
	set abstractText to my trimText(my joinLines(abstractParts))
	
	return {arxivId:arxivId, title:titleLine, dateLine:dateLine, authors:authorsLine, categories:categoriesLine, comments:commentsLine, URL:absUrl, abstractText:abstractText}
end parseArxivEntryMultiLine

on isHeaderLine(lineT)
	if my startsWithTrimmed(lineT, "arXiv:") then return true
	if my startsWithTrimmed(lineT, "Date:") then return true
	if my startsWithTrimmed(lineT, "Title:") then return true
	if my startsWithTrimmed(lineT, "Authors:") then return true
	if my startsWithTrimmed(lineT, "Categories:") then return true
	if my startsWithTrimmed(lineT, "Comments:") then return true
	return false
end isHeaderLine

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

on replaceText(theText, searchString, replacementString)
	set AppleScript's text item delimiters to searchString
	set parts to text items of (theText as text)
	set AppleScript's text item delimiters to replacementString
	set newText to parts as text
	set AppleScript's text item delimiters to ""
	return newText
end replaceText

on jsonString(s)
	set t to s as text
	set t to my replaceText(t, "\\", "\\\\")
	set t to my replaceText(t, "\"", "\\\"")
	set t to my replaceText(t, return, "\\n")
	set t to my replaceText(t, linefeed, "\\n")
	return "\"" & t & "\""
end jsonString
