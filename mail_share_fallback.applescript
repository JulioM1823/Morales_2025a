-- Fallback Mail compose AppleScript used by arxiv-picker.swift
--
-- NOTE: The app generates a concrete script with subject/body/toAddress embedded.
-- This file is a readable reference of the logic.
--
-- Inputs (conceptual):
--   SUBJECT     - email subject
--   BODY        - email content (plain text)
--   TO_ADDRESS  - optional recipient email address

on composeMailMessage(SUBJECT, BODY, TO_ADDRESS)
	tell application "Mail"
		if it is not running then
			launch
		end if
		activate
		set newMessage to make new outgoing message with properties {subject:SUBJECT, content:(BODY & "\n"), visible:true}
		if TO_ADDRESS is not "" then
			try
				make new to recipient at end of to recipients of newMessage with properties {address:TO_ADDRESS}
			end try
		end if
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
				set composeWin to first window whose name contains SUBJECT
			end try
		end if
		if composeWin is missing value then
			set composeWin to front window
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
end composeMailMessage
