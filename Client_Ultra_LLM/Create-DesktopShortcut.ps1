# Run once to install the Web Client shortcut for the CURRENT copied folder.
# A relocated folder requires a new shortcut; credentials stay in LOCALAPPDATA.
$ErrorActionPreference = 'Stop'
$launcher = Join-Path $PSScriptRoot 'Start_Ultra_LLM_Client.vbs'
if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
    throw 'Portable Web Client launcher is missing'
}
$desktop = [Environment]::GetFolderPath('DesktopDirectory')
$link = Join-Path $desktop 'Ultra LLM Client.lnk'
if (Test-Path -LiteralPath $link) {
    throw 'Desktop shortcut already exists. Review it; refusing to overwrite.'
}
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($link)
$shortcut.TargetPath = Join-Path $env:WINDIR 'System32\wscript.exe'
$shortcut.Arguments = '"' + $launcher + '"'
$shortcut.WorkingDirectory = $PSScriptRoot
$shortcut.Description = 'Ultra LLM Web Client — browser-only local console-free launcher'
$shortcut.IconLocation = (Join-Path $env:WINDIR 'System32\imageres.dll') + ',14'
$shortcut.Save()
Write-Output ('ULTRA_WEB_DESKTOP_SHORTCUT_CREATED='+$link)
