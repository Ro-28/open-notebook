-- Open Notebook launcher (macOS stay-open applet).
-- Launch: starts SurrealDB + API + worker + UI + Learn sidecar via scripts/app/open-notebook.sh and
-- opens the browser. No dialog: the app just sits in the Dock while services run.
-- Quit from the web UI ("Quit Open Notebook" in the sidebar), Cmd-Q, or Dock > Quit stops every service.
-- Clicking the Dock icon again re-opens the UI in the browser.

property projectRoot : "/Users/roberto/Projects/open-notebook"
property uiURL : "http://localhost:3000"
property stopping : false

on ctl(cmd)
	return do shell script "/bin/bash " & quoted form of (projectRoot & "/scripts/app/open-notebook.sh") & " " & cmd & " 2>&1"
end ctl

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
end run

on idle
	-- If the services were stopped from the web UI, exit quietly.
	try
		set st to ctl("status")
		if st contains "api: stopped" then
			set stopping to true
			quit
		end if
	end try
	return 5
end idle

on reopen
	open location uiURL
end reopen

on quit
	if not stopping then
		try
			ctl("stop")
		end try
	end if
	continue quit
end quit
