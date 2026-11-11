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
  ' The script, not the background Python instance, opens the browser.
  ' This also works when the Client was already running before the click.
  shell.Run Chr(34) & exe & Chr(34) & " --no-browser", 0, False
  Dim portFile, stream, portText, port, url, verify, validPort, n, browser
  portFile = fs.BuildPath(shell.ExpandEnvironmentStrings("%LOCALAPPDATA%\UltraLLM\Client"), ".web-client.port")
  Set validPort = CreateObject("VBScript.RegExp")
  validPort.Pattern = "^[0-9]{4,5}$"
  validPort.Global = False
  For n = 1 To 80
    WScript.Sleep 250
    If fs.FileExists(portFile) Then
      On Error Resume Next
      Err.Clear
      portText = ""
      Set stream = fs.OpenTextFile(portFile, 1, False)
      If Err.Number = 0 Then
        portText = Trim(stream.ReadAll)
        stream.Close
      End If
      If Err.Number = 0 And validPort.Test(portText) Then
        port = CLng(portText)
        If port >= 1024 And port <= 65535 Then
          url = "http://127.0.0.1:" & CStr(port) & "/"
          Set verify = CreateObject("WinHttp.WinHttpRequest.5.1")
          verify.SetProxy 1
          verify.SetTimeouts 500, 500, 500, 1000
          verify.Open "GET", url, False
          verify.Send
          If Err.Number = 0 Then
            If verify.Status = 200 And Left(verify.GetResponseHeader("Server"), 12) = "UltraLLMWeb/" Then
              Set browser = CreateObject("Shell.Application")
              browser.ShellExecute url, "", "", "open", 1
              If Err.Number = 0 Then
                WScript.Quit 0
              End If
            End If
          End If
        End If
      End If
      Err.Clear
      On Error GoTo 0
    End If
  Next
  MsgBox "Ultra LLM Client не открыл локальный веб-интерфейс. Проверьте, что программа запущена, и повторите попытку.", vbExclamation, "Ultra LLM Client"
  WScript.Quit 5
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
