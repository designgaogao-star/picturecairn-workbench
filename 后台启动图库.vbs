' Gallery Tool - silent background launcher (no console window)
' Uses pythonw.exe so it keeps running without a terminal. Idempotent:
' if the server is already listening on 8765 it simply exits and opens the page.
Option Explicit
Dim fso, ws, dirPath, pyw, server
Set fso = CreateObject("Scripting.FileSystemObject")
Set ws  = CreateObject("WScript.Shell")
dirPath = fso.GetParentFolderName(WScript.ScriptFullName)
server  = dirPath & "\gallery_server.py"

pyw = "C:\Users\79974\AppData\Local\Programs\Python\Python312\pythonw.exe"
If Not fso.FileExists(pyw) Then pyw = "pythonw.exe"

ws.CurrentDirectory = dirPath
ws.Run """" & pyw & """ """ & server & """ --no-open", 0, False
WScript.Sleep 1200
ws.Run "http://127.0.0.1:8765", 1, False
