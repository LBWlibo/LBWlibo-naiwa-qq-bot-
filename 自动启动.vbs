' 开机自启入口：隐藏窗口运行 start_bot.bat（自动定位到本文件所在目录）
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
shell.Run """" & folder & "\start_bot.bat""", 0, False
