Set WshShell = CreateObject("WScript.Shell")
WshScriptPath = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
WshShell.Run "cmd /c cd /d """ & WshScriptPath & "\bots\widget"" && node index.js", 0, False
WScript.Sleep 1500
WshShell.Run "http://localhost:3000"
