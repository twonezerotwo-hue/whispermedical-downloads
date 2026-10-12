-- WhisperMedical Installer (Intel Mac). Compiled into "WhisperMedical Installer.app" by build.sh. It only shows a window and a progress bar;
-- the work (download, SHA-256 checks, mounting, copying) is done by install.sh in the same app bundle. Source is public so anyone can read it.

on run
	set scriptPath to POSIX path of (path to resource "install.sh")
	-- a private folder of this user for the progress messages of install.sh
	set workFolder to do shell script "/usr/bin/mktemp -d"
	set progressFile to workFolder & "/progress.txt"
	-- WM_AUTOMATED=1 (set by the automated release test only) answers the two confirmation dialogs by itself and installs into WM_DEST without opening the app
	set automated to ((system attribute "WM_AUTOMATED") is "1")
	set extraArgs to ""
	if automated then set extraArgs to " --no-open --dest " & quoted form of (system attribute "WM_DEST")

	if not automated then
		try
			display dialog "WhisperMedical will download about 3 GB (the program and the Whisper Large-v3 speech model), check every file, and install it in your Applications folder." & return & return & "Nothing is installed unless the download is verified. You can stop at any time and continue later; your progress is kept." buttons {"Cancel", "Install"} default button "Install" cancel button "Cancel" with title "WhisperMedical Installer" with icon note
		on error number -128
			return
		end try
	end if

	do shell script "rm -f " & quoted form of progressFile & "; : > " & quoted form of progressFile
	set pidText to do shell script "/bin/bash " & quoted form of scriptPath & " --progress-file " & quoted form of progressFile & extraArgs & " >/dev/null 2>&1 & echo $!"

	set progress total steps to 1000
	set progress completed steps to 0
	set progress description to "Installing WhisperMedical"
	set progress additional description to "Starting ..."

	set finished to false
	set errorText to ""
	set installedPath to ""
	try
		repeat until finished
			delay 1
			set lastLine to do shell script "tail -n 1 " & quoted form of progressFile & " 2>/dev/null || true"
			set oldDelimiters to AppleScript's text item delimiters
			set AppleScript's text item delimiters to "|"
			set fields to text items of lastLine
			set AppleScript's text item delimiters to oldDelimiters
			if (count of fields) > 0 then
				set kind to item 1 of fields
				if kind is "P" and (count of fields) ≥ 4 then
					set doneBytes to (item 2 of fields) as real
					set totalBytes to (item 3 of fields) as real
					if totalBytes > 0 then
						set progress completed steps to (round (doneBytes / totalBytes * 1000))
						set progress additional description to (item 4 of fields) & "   " & ((round (doneBytes / 1.0E+7)) / 100) & " GB of " & ((round (totalBytes / 1.0E+7)) / 100) & " GB"
					end if
				else if kind is "S" and (count of fields) ≥ 2 then
					set progress additional description to item 2 of fields
				else if kind is "E" then
					set errorText to item 2 of fields
					set finished to true
				else if kind is "D" then
					set installedPath to item 2 of fields
					set finished to true
				end if
			end if
		end repeat
	on error number -128
		do shell script "pkill -P " & pidText & " 2>/dev/null; kill " & pidText & " 2>/dev/null; rm -rf " & quoted form of workFolder & "; true"
		display dialog "Stopped. Your download progress is kept: open WhisperMedical Installer again to continue." buttons {"OK"} default button "OK" with title "WhisperMedical Installer" with icon note
		return
	end try

	do shell script "rm -rf " & quoted form of workFolder
	if errorText is not "" then
		if automated then error errorText number 1
		display dialog errorText buttons {"Close"} default button "Close" with title "WhisperMedical Installer" with icon stop
	else if not automated then
		display dialog "WhisperMedical is installed in your Applications folder and is starting." & return & return & "Whisper Large-v3 is already inside - nothing more will be downloaded." buttons {"Done"} default button "Done" with title "WhisperMedical Installer" with icon note
	end if
end run
