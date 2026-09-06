-- Open Notebook launcher (macOS stay-open applet).
-- Launch: starts SurrealDB + API + worker + UI via scripts/app/open-notebook.sh and opens the browser.
-- The app stays in the Dock while running. Quit it (Quit button, Cmd-Q, or Dock > Quit) to stop every service.
-- Clicking the Dock icon again re-opens the control dialog.

property projectRoot : "/Users/roberto/Projects/open-notebook"
property uiURL : "http://localhost:3000"

on ctl(cmd)
	return do shell script "/bin/bash " & quoted form of (projectRoot & "/scripts/app/open-notebook.sh") & " " & cmd & " 2>&1"
end ctl

on showControl()
	set r to display dialog "Open Notebook is running." & return & return & uiURL & return & "API: http://localhost:5055" & return & return & "Quitting this app shuts down all services." buttons {"Show Logs", "Quit Open Notebook", "Keep Running"} default button "Keep Running" with title "Open Notebook" with icon note
	set b to button returned of r
	if b is "Quit Open Notebook" then
		quit
	else if b is "Show Logs" then
		do shell script "open " & quoted form of (projectRoot & "/data/app/logs")
	end if
end showControl

on run
	try
		ctl("start")
	on error errMsg
		set r to display dialog "Open Notebook failed to start:" & return & return & errMsg & return & return & "Logs: " & projectRoot & "/data/app/logs" buttons {"Show Logs", "Quit"} default button "Quit" with icon stop with title "Open Notebook"
		if button returned of r is "Show Logs" then do shell script "open " & quoted form of (projectRoot & "/data/app/logs")
		quit
		return
	end try
	open location uiURL
	showControl()
end run

on idle
	return 60
end idle

on reopen
	showControl()
end reopen

on quit
	try
		ctl("stop")
	end try
	continue quit
end quit
