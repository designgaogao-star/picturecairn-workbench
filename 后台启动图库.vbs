Option Explicit
Dim fso, ws, launcher
Set fso = CreateObject("Scripting.FileSystemObject")
Set ws = CreateObject("WScript.Shell")
launcher = fso.GetParentFolderName(WScript.ScriptFullName) & "\scripts\start.ps1"
ws.Run "pwsh -NoProfile -File """ & launcher & """", 0, False
