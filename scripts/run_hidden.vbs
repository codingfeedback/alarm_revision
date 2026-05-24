Option Explicit

Dim shell
Dim scriptPath
Dim powershellExe
Dim command

If WScript.Arguments.Count = 0 Then
    WScript.Quit 1
End If

scriptPath = WScript.Arguments(0)
powershellExe = "C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe"
command = """" & powershellExe & """ -NoProfile -ExecutionPolicy Bypass -File """ & scriptPath & """"

Set shell = CreateObject("WScript.Shell")
shell.Run command, 0, False
