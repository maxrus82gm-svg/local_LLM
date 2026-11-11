' Portable double-click Web Client launcher. Path is relative to THIS .vbs file.
' This launcher never opens a console or places credentials on its command line.
Option Explicit
Dim fs, shell, here, target, pyw, checkCommand, rc
Set fs = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
here = fs.GetParentFolderName(WScript.ScriptFullName)
target = fs.BuildPath(here, "web_client.py")
If Not fs.FileExists(target) Then
  MsgBox "Ultra LLM Web Client не найден в папке запуска.", vbCritical, "Ultra LLM Client"
  WScript.Quit 2
End If
pyw = shell.ExpandEnvironmentStrings("%WINDIR%") & "\pyw.exe"
If Not fs.FileExists(pyw) Then
  MsgBox "Требуется Python 3.12. Переносимая сборка без Python будет в следующем этапе.", vbExclamation, "Ultra LLM Client"
  WScript.Quit 3
End If
checkCommand = Chr(34) & shell.ExpandEnvironmentStrings("%WINDIR%") & "\py.exe" & Chr(34) & " -3.12 -V"
rc = shell.Run(checkCommand, 0, True)
If rc <> 0 Then
  MsgBox "Python 3.12 не установлен. Пожалуйста, установите Python 3.12 или используйте будущую переносимую сборку.", vbExclamation, "Ultra LLM Client"
  WScript.Quit 4
End If
shell.CurrentDirectory = here
shell.Run Chr(34) & pyw & Chr(34) & " -3.12 -B " & Chr(34) & target & Chr(34), 0, False
