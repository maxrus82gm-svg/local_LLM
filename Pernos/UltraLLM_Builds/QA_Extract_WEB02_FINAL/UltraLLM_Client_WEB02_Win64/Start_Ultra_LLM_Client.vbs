' Portable, console-free Ultra LLM Client launcher, no Python required in release.
' Copy the entire distribution directory. This file resolves paths relative to itself.
Option Explicit
Dim fs, shell, here, exe, target, pyw, py, checkCommand, rc
Set fs = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
here = fs.GetParentFolderName(WScript.ScriptFullName)
exe = fs.BuildPath(here, "UltraLLMClient.exe")
shell.CurrentDirectory = here

' Portable distribution: use bundled Python runtime, never the system runtime.
If fs.FileExists(exe) Then
  shell.Run Chr(34) & exe & Chr(34), 0, False
  WScript.Quit 0
End If

' Developer source fallback: this is NOT needed by the portable distribution.
target = fs.BuildPath(here, "web_client.py")
If Not fs.FileExists(target) Then
  MsgBox "Ultra LLM Client не найден. Скопируйте всю папку программы целиком.", vbCritical, "Ultra LLM Client"
  WScript.Quit 2
End If
pyw = shell.ExpandEnvironmentStrings("%WINDIR%") & "\pyw.exe"
py = shell.ExpandEnvironmentStrings("%WINDIR%") & "\py.exe"
If Not fs.FileExists(pyw) Or Not fs.FileExists(py) Then
  MsgBox "Для запуска из исходников требуется Python 3.12. Используйте переносимый комплект с UltraLLMClient.exe.", vbExclamation, "Ultra LLM Client"
  WScript.Quit 3
End If
checkCommand = Chr(34) & py & Chr(34) & " -3.12 -V"
rc = shell.Run(checkCommand, 0, True)
If rc <> 0 Then
  MsgBox "Python 3.12 не найден. Используйте переносимую сборку Ultra LLM Client.", vbExclamation, "Ultra LLM Client"
  WScript.Quit 4
End If
shell.Run Chr(34) & pyw & Chr(34) & " -3.12 -B " & Chr(34) & target & Chr(34), 0, False
