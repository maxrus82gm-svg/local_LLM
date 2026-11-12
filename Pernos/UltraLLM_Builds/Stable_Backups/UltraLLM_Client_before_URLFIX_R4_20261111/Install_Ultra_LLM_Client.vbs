' Double-click to create/update the Ultra LLM Web Client desktop shortcut.
' Portable: the launcher is resolved relative to THIS copied folder.
' Never copies credentials, changes firewall, or installs Python silently.
Option Explicit
Dim shell, fs, folder, launcher, desktop, shortcutPath, link, linkTarget, currentArgs
Set shell = CreateObject("WScript.Shell")
Set fs = CreateObject("Scripting.FileSystemObject")
folder = fs.GetParentFolderName(WScript.ScriptFullName)
launcher = fs.BuildPath(folder, "Start_Ultra_LLM_Client.vbs")
If Not fs.FileExists(launcher) Then
  MsgBox "Запускатор Ultra LLM Client отсутствует в папке.", vbCritical, "Ultra LLM Client"
  WScript.Quit 2
End If
desktop = shell.SpecialFolders("Desktop")
shortcutPath = fs.BuildPath(desktop, "Ultra LLM Client.lnk")
If fs.FileExists(shortcutPath) Then
  Set link = shell.CreateShortcut(shortcutPath)
  linkTarget = LCase(link.TargetPath)
  currentArgs = LCase(link.Arguments)
  If InStr(linkTarget, "wscript.exe") = 0 Or InStr(currentArgs, "start_ultra_llm_client.vbs") = 0 Then
    MsgBox "На рабочем столе уже есть другой ярлык с таким именем. Автоматическая замена запрещена.", vbExclamation, "Ultra LLM Client"
    WScript.Quit 3
  End If
End If
Set link = shell.CreateShortcut(shortcutPath)
link.TargetPath = shell.ExpandEnvironmentStrings("%WINDIR%") & "\System32\wscript.exe"
link.Arguments = Chr(34) & launcher & Chr(34)
link.WorkingDirectory = folder
link.Description = "Ultra LLM Web Client — локальный веб-интерфейс"
link.IconLocation = shell.ExpandEnvironmentStrings("%WINDIR%") & "\System32\imageres.dll,14"
link.Save
MsgBox "Готово! Ярлык Ultra LLM Client создан на рабочем столе." & vbCrLf & _
       "При первом запуске откроется веб-мастер подключения.", vbInformation, "Ultra LLM Client"
