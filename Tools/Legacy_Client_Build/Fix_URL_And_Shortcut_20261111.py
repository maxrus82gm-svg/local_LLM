from pathlib import Path
root=Path(r"M:\GitHub\local_LLM_GPT_docs\Client_Ultra_LLM")
web=root/"web_client.py"
s=web.read_text(encoding="utf-8-sig")
old='''            path = self.path
            if path in _STATIC_FILES:'''
new='''            # Tracking parameters added by browsers/link wrappers must not
            # turn the homepage into a 404. Ignore queries ONLY for "/".
            # API routes retain their exact validation/CSRF requirements.
            path = "/" if self.path.startswith("/?") and len(self.path) <= 2048 else self.path
            if path in _STATIC_FILES:'''
assert s.count(old)==1,s.count(old)
web.write_text(s.replace(old,new,1),encoding="utf-8",newline="\n")

vbs=root/"Start_Ultra_LLM_Client.vbs"
s=vbs.read_text(encoding="utf-8-sig")
start=s.index("If fs.FileExists(exe) Then")
end=s.index("\n' Developer source fallback",start)
newbranch=r'''If fs.FileExists(exe) Then
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
'''
assert s.count("If fs.FileExists(exe) Then")==1
vbs.write_text(s[:start]+newbranch+s[end:],encoding="utf-8",newline="\r\n")

t=root/"test_web_client.py"
s=t.read_text(encoding="utf-8-sig")
needle='''    def test_server_never_offers_mutating_remote_operations(self):'''
repl='''    def test_homepage_accepts_tracker_query_but_api_paths_stay_strict(self):
        normal, html, headers = self.request("/")
        self.assertEqual(normal, 200)
        for suffix in ("?utm_source=chatgpt.com", "?utm_campaign=test&x=1"):
            code, body, queried = self.request("/" + suffix)
            self.assertEqual(code, 200)
            self.assertEqual(body, html)
            self.assertEqual(queried.get("Content-Type"), headers.get("Content-Type"))
        self.assertEqual(self.request("/api/session?utm_source=chatgpt.com")[0], 404)
        self.assertEqual(self.request("/not_a_page?utm_source=chatgpt.com")[0], 404)

    def test_launcher_uses_stable_local_browser_route_not_python_browser(self):
        launcher = (Path(web_client.__file__).parent /
                    "Start_Ultra_LLM_Client.vbs").read_text(encoding="utf-8")
        self.assertIn(' " --no-browser"', launcher)
        self.assertIn('WinHttp.WinHttpRequest.5.1', launcher)
        self.assertIn('verify.SetProxy 1', launcher)
        self.assertIn('UltraLLMWeb/', launcher)
        self.assertIn('browser.ShellExecute url', launcher)

    def test_server_never_offers_mutating_remote_operations(self):'''
assert s.count(needle)==1
t.write_text(s.replace(needle,repl,1),encoding="utf-8",newline="\n")

t=root/"test_chat_client.py"
s=t.read_text(encoding="utf-8-sig")
s=s.replace('''        # A detached chat uses a URL fragment. A query on "/" would be
        # rejected by the local Client router before the web page could load.
''','''        # Detached chat selection uses a URL fragment, not a chat query
        # argument. The homepage now tolerates unrelated tracking queries.
''')
t.write_text(s,encoding="utf-8",newline="\n")
print("PATCHED root query / VBS browser opening / regression tests")
