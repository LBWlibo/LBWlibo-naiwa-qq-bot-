' Autostart entry: run start_bot.bat hidden in this folder.
' ASCII-only: WSH reads .vbs as ANSI, non-ASCII comments can break it.
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
shell.Run "cmd /c """ & folder & "\start_bot.bat""", 0, False
